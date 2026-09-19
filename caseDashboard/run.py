#!/usr/bin/env python3
"""One-command launcher for the case dashboard.

    python caseDashboard/run.py            # dev:  backend 8765 + Vite 5173
    python caseDashboard/run.py --prod     # prod: build once, serve on 8765

Node is a *build tool only* -- it never runs at serve time.  Everything stays on
the Windows side: the dashboard reads and writes the case dictionaries and never
launches a WSL command, an OpenFOAM tool or a solver.

Kept dependency-free on purpose (stdlib only, like the rest of ``pyScript/``).
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

DASH_DIR = Path(__file__).resolve().parent
REPO_DIR = DASH_DIR.parent
WEB_DIR = DASH_DIR / "web"
DIST_DIR = WEB_DIR / "dist"

HOST = "127.0.0.1"
API_PORT = 8765
VITE_PORT = 5173
API_URL = f"http://{HOST}:{API_PORT}/"

_IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------
# port hygiene
# --------------------------------------------------------------------------


def port_busy(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def dashboard_running() -> bool:
    """True when the thing answering on the API port is a dashboard of ours.

    Double-clicking the launcher a second time is the ordinary way to find the
    port taken, and that is not a failure -- the instance already serving is the
    one being asked for.  The ``Server`` header is what tells it apart from an
    unrelated program that happens to hold 8765.

    A free port refuses the connection immediately, so this doubles as the
    liveness test; there is no separate ``port_busy`` probe first.
    """
    try:
        with urllib.request.urlopen(API_URL, timeout=1.0) as reply:
            server = reply.headers.get("Server", "")
    except urllib.error.HTTPError as exc:
        # Still a reply from our handler; only the status was unkind.
        server = exc.headers.get("Server", "")
    except OSError:
        return False
    return server.startswith("caseDashboard")


def require_free(port: int, label: str) -> None:
    if port_busy(port):
        die(
            f"port {port} is held by another program ({label}).\n"
            f"End that process first, or change "
            f"{'PORT in caseDashboard/server/app.py' if port == API_PORT else 'server.port in caseDashboard/web/vite.config.ts'}."
        )


def die(message: str) -> None:
    print(f"\n[caseDashboard] error: {message}\n", file=sys.stderr)
    raise SystemExit(1)


# --------------------------------------------------------------------------
# node toolchain
# --------------------------------------------------------------------------


def npm_command() -> str:
    """Resolve npm on Windows.

    A bare ``"npm"`` fails under ``subprocess`` because Windows resolves it to
    ``npm.cmd``, which is not an executable image; ``shutil.which`` finds the
    real shim.
    """
    for name in (("npm.cmd", "npm") if _IS_WINDOWS else ("npm",)):
        found = shutil.which(name)
        if found:
            return found
    die("npm not found. Install Node.js first (https://nodejs.org).")


def run_npm(args: list[str], label: str) -> None:
    print(f"[caseDashboard] {label} ...")
    proc = subprocess.run([npm_command(), *args], cwd=str(WEB_DIR))
    if proc.returncode != 0:
        die(f"{label} failed (exit code {proc.returncode}).")


def ensure_deps() -> None:
    if not (WEB_DIR / "package.json").is_file():
        die(f"frontend project missing: {WEB_DIR / 'package.json'}")
    if (WEB_DIR / "node_modules").is_dir():
        return
    run_npm(["install", "--no-audit", "--no-fund"], "first run: installing frontend dependencies")


def ensure_build() -> None:
    if (DIST_DIR / "index.html").is_file():
        return
    run_npm(["run", "build"], "building the frontend")


# --------------------------------------------------------------------------
# processes
# --------------------------------------------------------------------------


def spawn(cmd: list[str], cwd: Path, label: str) -> subprocess.Popen:
    print(f"[caseDashboard] starting {label}: {' '.join(cmd)}")
    creationflags = 0
    if _IS_WINDOWS:
        # Own process group so Ctrl+C can be routed to both children.
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(cmd, cwd=str(cwd), creationflags=creationflags)


def terminate(proc: subprocess.Popen, label: str) -> None:
    if proc.poll() is not None:
        return
    print(f"[caseDashboard] stopping {label} ...")
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
    except OSError:
        pass


_OPEN_BROWSER = True


def open_later(url: str, delay: float = 1.5) -> None:
    if not _OPEN_BROWSER:
        return
    threading.Timer(delay, lambda: webbrowser.open(url)).start()


def reuse_running() -> bool:
    """Send the browser to a dashboard that is already up.

    Returns True when the API port answered as one of ours, which means there is
    nothing left to start and the caller should stop.  Only a *foreign* occupant
    is an error; that is left to ``require_free``.
    """
    if not dashboard_running():
        return False
    print(f"\n[caseDashboard] the dashboard is already running -> {API_URL}\n")
    if _OPEN_BROWSER:
        webbrowser.open(API_URL)
    return True


# --------------------------------------------------------------------------
# modes
# --------------------------------------------------------------------------


def serve_prod() -> None:
    if reuse_running():
        return
    require_free(API_PORT, "backend API")
    ensure_deps()
    ensure_build()

    from caseDashboard.server import app as backend

    httpd = backend.serve(HOST, API_PORT)
    print(f"\n[caseDashboard] prod mode ready -> {API_URL}\n")
    open_later(API_URL)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[caseDashboard] shutting down ...")
    finally:
        httpd.shutdown()
        httpd.server_close()
    print("[caseDashboard] stopped.")


def serve_dev() -> None:
    if reuse_running():
        return
    require_free(API_PORT, "backend API")
    require_free(VITE_PORT, "Vite dev server")
    ensure_deps()

    backend = spawn(
        [sys.executable, "-m", "caseDashboard.server.app"],
        cwd=REPO_DIR,
        label="backend API",
    )
    vite = spawn(
        [npm_command(), "run", "dev", "--", "--port", str(VITE_PORT)],
        cwd=WEB_DIR,
        label="Vite",
    )

    url = f"http://localhost:{VITE_PORT}/"
    print(f"\n[caseDashboard] dev mode ready -> {url}\n")
    open_later(url)

    try:
        while True:
            time.sleep(0.4)
            for proc, label in ((backend, "backend API"), (vite, "Vite")):
                if proc.poll() is not None:
                    print(
                        f"\n[caseDashboard] {label} exited (exit code {proc.returncode}),"
                        " stopping the other process ..."
                    )
                    return
    except KeyboardInterrupt:
        print("\n[caseDashboard] shutting down ...")
    finally:
        terminate(vite, "Vite")
        terminate(backend, "backend API")
    print("[caseDashboard] stopped.")


def main() -> None:
    # Progress must appear immediately; a piped stdout would otherwise buffer
    # the whole startup behind a long `npm install`.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(
        prog="run.py",
        description="CFDEMInterFoamIB case parameter dashboard",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="build the frontend and serve it from the backend on one port "
        "(default is Vite dev mode with hot reload)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the browser",
    )
    args = parser.parse_args()

    if args.no_browser:
        global _OPEN_BROWSER
        _OPEN_BROWSER = False

    # `from caseDashboard.server import app` needs the repo root on sys.path.
    sys.path.insert(0, str(REPO_DIR))

    print("[caseDashboard] repo:", REPO_DIR)
    if args.prod:
        serve_prod()
    else:
        serve_dev()


if __name__ == "__main__":
    main()
