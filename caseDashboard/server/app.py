"""HTTP API and static host for the case dashboard.

Standard library only -- no pip installs.  ``ThreadingHTTPServer`` keeps the
console usable while a slow request is in flight.  (The ``cgi`` module was
removed in 3.13, so query parsing is done by hand.)

Binds to loopback only, and every ``path`` parameter is resolved and checked to
live inside the repository before anything touches the filesystem.

Nothing here leaves the Windows side: the dashboard reads and writes case
dictionaries and never runs a solver, a mesher or any other WSL command.  It
starts no process at all -- the folder browser behind ``/api/browse`` is an
ordinary directory listing served out of this handler, not a dialog.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import posixpath
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from . import derived as derived_mod
from . import writer as writer_mod
from .profiles import ALL_PARAMS, FILE_LABELS, FILES, GROUPS
from .reader import FileText, Resolved, read_case, resolved_to_api
from .state import Registry

REPO_DIR = Path(__file__).resolve().parents[2]
DASH_DIR = REPO_DIR / "caseDashboard"
CACHE_DIR = DASH_DIR / ".cache"
WEB_DIR = DASH_DIR / "web"
DIST_DIR = WEB_DIR / "dist"

HOST = "127.0.0.1"
PORT = 8765


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# --------------------------------------------------------------------------
# path hygiene
# --------------------------------------------------------------------------


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_case(raw: str) -> Path:
    """The case directory a request names.

    A case may sit anywhere the dashboard can read -- in the repository or not --
    because the parameter list is about the *case*, and a case does not stop
    being one because it was cloned somewhere else.  What is still required is the
    single thing that makes a directory openable at all: a
    ``CFD/system/controlDict``.  Every write stays inside whatever directory this
    returns, which `case_file` enforces and nothing else has to.
    """
    if not raw:
        raise ApiError(400, "Missing path parameter")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = REPO_DIR / raw
    candidate = candidate.resolve()
    if not (candidate / "CFD" / "system" / "controlDict").is_file():
        raise ApiError(400, f"Not a valid case (missing CFD/system/controlDict): {raw}")
    return candidate


def rel_to_repo(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_DIR.resolve())).replace("\\", "/")


def path_id(path: Path) -> str:
    """How the dashboard names a directory: repository-relative where that is
    possible, absolute where it is not.

    One spelling either way, so the string that goes out is the string that comes
    back -- a case outside the repository is named by its absolute path, and
    nothing downstream has to know which kind it is holding.
    """
    if path == REPO_DIR:
        return ""
    if is_under(path, REPO_DIR):
        return rel_to_repo(path)
    return str(path).replace("\\", "/")


#: Directory names the folder browser never descends into.  Version control and
#: dependency trees are thousands of entries of noise, and no case lives in one.
HIDDEN_DIRS = {"node_modules", "__pycache__"}


def resolve_dir(raw: str) -> Path:
    """A directory for the folder browser to list.

    Browsing is not confined to the repository: a case the dashboard can open may
    live anywhere, so the walk to it has to be able to leave.  The empty string is
    still the repository root, which is where the browser opens.
    """
    candidate = REPO_DIR if not raw else Path(raw)
    if not candidate.is_absolute():
        candidate = REPO_DIR / raw
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise ApiError(404, f"Folder not found: {raw}")
    return candidate


def crumbs(here: Path) -> List[dict]:
    """Every level from the browsing anchor down to `here`, each with the path
    that jumps back to it.

    Inside the repository the anchor is the repository, so the trail reads in the
    same relative terms everything else does.  Outside it the anchor is the drive
    (or the filesystem root), because there is no shorter name for where you are
    any more.
    """
    if is_under(here, REPO_DIR):
        parts = [] if here == REPO_DIR else rel_to_repo(here).split("/")
        out = [{"label": REPO_DIR.name, "path": ""}]
        for i, name in enumerate(parts):
            out.append({"label": name, "path": "/".join(parts[: i + 1])})
        return out
    chain = [here, *here.parents]
    chain.reverse()
    # `Path("D:/").name` is empty, and so is `Path("/").name` -- the drive letter
    # is all there is to call that level.
    return [{"label": p.name or p.drive or str(p), "path": path_id(p)} for p in chain]


def browse_dir(raw: str) -> dict:
    """One directory's subfolders, for the folder browser.

    Only the level asked for is listed: the browser walks down a click at a time
    rather than being handed the whole tree.  A subfolder that is itself a case is
    flagged so the browser can offer it as a target; nothing here decides what may
    be *opened* -- `resolve_case` still does that when the path comes back.
    """
    here = resolve_dir(raw)
    is_case = (here / "CFD" / "system" / "controlDict").is_file()
    entries = []
    for child in sorted(here.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith(".") or child.name in HIDDEN_DIRS or not child.is_dir():
            continue
        entries.append(
            {
                "name": child.name,
                "path": path_id(child),
                "is_case": (child / "CFD" / "system" / "controlDict").is_file(),
            }
        )
    return {
        "repo": str(REPO_DIR),
        "path": path_id(here),
        # Outside the repository the trail no longer starts at the repository, so
        # the browser needs to know whether to offer it as a shortcut back.
        "inside_repo": is_under(here, REPO_DIR),
        "crumbs": crumbs(here),
        "name": here.name,
        # `None` only where there is genuinely nothing above: a filesystem root.
        # That is the one place the browser disables its up control.
        "parent": None if here.parent == here else path_id(here.parent),
        "is_case": is_case,
        "entries": entries,
    }


def case_file(case_dir: Path, rel: str) -> Path:
    """One file inside ``case_dir`` -- the only files the editor can touch."""
    target = (case_dir / rel).resolve()
    if not rel or not is_under(target, case_dir):
        raise ApiError(403, f"Only files inside the case directory can be opened: {rel}")
    if not target.is_file():
        raise ApiError(404, f"File not found: {rel}")
    return target


def file_payload(rel: str, raw: bytes) -> dict:
    """A file as the in-dashboard editor sees it.

    The editor works in LF like every browser textarea does, so the file's own
    convention is carried alongside rather than baked into the text -- otherwise
    opening and saving a CRLF dictionary would silently rewrite every line.
    """
    crlf = raw.count(b"\r\n")
    lf_only = raw.count(b"\n") - crlf
    return {
        "file": rel,
        "text": raw.decode("utf-8").replace("\r\n", "\n"),
        "eol": "crlf" if crlf > lf_only else "lf",
        "bytes": len(raw),
        "sha": hashlib.sha256(raw).hexdigest(),
    }


def encode_like(text: str, original: bytes) -> bytes:
    crlf = original.count(b"\r\n")
    body = text.replace("\r\n", "\n")
    if crlf > original.count(b"\n") - crlf:
        body = body.replace("\n", "\r\n")
    return body.encode("utf-8")


#: The case the parameter list was written for, as a repository-relative path.
#: Recognition alone no longer singles it out -- every tutorial now matches the
#: whole list -- so the reference case is named here and the UI opens on it.
DEFAULT_CASE = "tutorial/single_sphere"


def discover_cases() -> List[dict]:
    """Every directory in the repository that looks like a case.

    The only thing asked of it is a ``CFD/system/controlDict``; there is no
    naming convention to satisfy.  Each entry carries how much of the parameter
    list it matched, so the list can say what an unfamiliar case got without
    having to open it first.
    """
    out: List[dict] = []
    seen = set()
    for depth in (1, 2, 3):
        for control in REPO_DIR.glob("/".join(["*"] * depth) + "/CFD/system/controlDict"):
            case_dir = control.parent.parent.parent
            if case_dir in seen:
                continue
            seen.add(case_dir)
            resolved, files = read_case(case_dir)
            counts = recognition(resolved, files)
            out.append(
                {
                    "path": rel_to_repo(case_dir),
                    "name": case_dir.name,
                    "recognized": counts["recognized"],
                    "total": counts["total"],
                }
            )
    # Best match first, so the case the list was written for stays the default
    # one -- which is also the one the UI opens on start-up.  `DEFAULT_CASE`
    # leads even when another case ties with it on recognition, and a repository
    # without it just falls back to the ordering below.
    out.sort(
        key=lambda item: (
            item["path"] != DEFAULT_CASE,
            -item["recognized"],
            item["path"],
        )
    )
    return out


def recognition(resolved: Dict[str, Resolved], files: Dict[str, FileText]) -> dict:
    """How much of the parameter list this case actually matched.

    A case is openable because it has a ``controlDict``, not because it looks
    like the one the list was written for -- so what is left to say is how many
    rules landed, and which ones did not.  That is the prompt for everything the
    dashboard could not locate; the field itself carries the per-parameter
    reason, this is the case-level summary of it.
    """
    located = [r for r in resolved.values() if r.status != "unresolved"]
    return {
        "total": len(resolved),
        "recognized": len(located),
        "editable": sum(
            1 for r in resolved.values() if r.status == "ok" and not r.param.product_of
        ),
        "unrecognized": [
            {
                "id": r.param.id,
                "label": r.param.label,
                "file": r.param.file,
                "matches": r.matches,
                "reason": r.reason,
            }
            for r in resolved.values()
            if r.status == "unresolved"
        ],
        "missing_files": [
            {"file": rel, "error": ft.error} for rel, ft in files.items() if not ft.ok
        ],
    }


# --------------------------------------------------------------------------
# application
# --------------------------------------------------------------------------


class Dashboard:
    def __init__(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.registry = Registry(CACHE_DIR)

    # -- case --------------------------------------------------------------
    def case_payload(self, case_dir: Path, include_resolved=True) -> dict:
        resolved, files = read_case(case_dir)
        params = [resolved_to_api(resolved[p.id]) for p in ALL_PARAMS]
        return {
            "path": path_id(case_dir),
            "abs_path": str(case_dir),
            "groups": [
                {"id": g.id, "label": g.label, "blurb": g.blurb,
                 "param_ids": [p.id for p in g.params]}
                for g in GROUPS
            ],
            "params": params,
            "files": FILES,
            "file_labels": FILE_LABELS,
            "recognition": recognition(resolved, files),
            "writable": True,
        }

    # -- preview / apply ---------------------------------------------------
    def _load_and_plan(self, case_dir: Path, edits: List[dict]):
        resolved, files = read_case(case_dir)
        plan = writer_mod.plan_edits(
            resolved,
            files,
            [
                writer_mod.Edit(e.get("id"), e.get("value"), e.get("enabled"))
                for e in edits or []
            ],
        )
        return resolved, files, plan

    def preview(self, case_dir: Path, edits: List[dict]) -> dict:
        resolved, files, plan = self._load_and_plan(case_dir, edits)
        rendered = writer_mod.render(files, plan)
        diffs = writer_mod.diff_files(files, rendered)
        return {
            "diffs": diffs,
            "validations": plan.errors,
            "skipped": {rel: pf.skipped for rel, pf in plan.files.items()},
            "derived": derived_mod.compute(resolved, edits),
            "params": [resolved_to_api(resolved[p.id]) for p in ALL_PARAMS],
            "changed_files": plan.changed_files,
            "is_noop": plan.is_noop,
        }

    def apply(self, case_dir: Path, edits: List[dict]) -> dict:
        state = self.registry.get(case_dir)
        with state.lock:
            resolved, files, plan = self._load_and_plan(case_dir, edits)
            if plan.errors and not plan.changed_files:
                return {
                    "diffs": [],
                    "validations": plan.errors,
                    "written": [],
                    "is_noop": True,
                    "derived": derived_mod.compute(resolved, edits),
                    "params": [resolved_to_api(resolved[p.id]) for p in ALL_PARAMS],
                    "changed_files": [],
                }

            originals = {rel: files[rel].raw for rel in plan.changed_files}
            written = writer_mod.apply_plan(case_dir, files, plan)
            if written:
                state.push_snapshot("apply", originals, [w["file"] for w in written])

            resolved_after, _ = read_case(case_dir)
            return {
                "diffs": writer_mod.diff_files(files, writer_mod.render(files, plan)),
                "validations": plan.errors,
                "written": written,
                "is_noop": not written,
                "derived": derived_mod.compute(resolved_after, []),
                "params": [resolved_to_api(resolved_after[p.id]) for p in ALL_PARAMS],
                "changed_files": [w["file"] for w in written],
            }

    def revert(self, case_dir: Path) -> dict:
        state = self.registry.get(case_dir)
        with state.lock:
            snap = state.pop_snapshot()
            if snap is None:
                raise ApiError(409, "There is no snapshot to revert to")
            restored = []
            for rel, data in snap.files.items():
                target = case_dir / rel
                # The case, not the repository, is what a snapshot can name: a
                # case outside the repository has snapshots too, and a `rel` that
                # climbs out of the case is refused either way.
                if not is_under(target, case_dir):
                    continue
                writer_mod.atomic_write(target, data)
                restored.append(rel)
            resolved, _ = read_case(case_dir)
            return {
                "restored": restored,
                "snapshot": snap.to_json(),
                "params": [resolved_to_api(resolved[p.id]) for p in ALL_PARAMS],
                "derived": derived_mod.compute(resolved, []),
                "stack": state.stack_view(),
            }

    # -- raw file editor ---------------------------------------------------
    def read_file(self, case_dir: Path, rel: str) -> dict:
        """The text of one case file, for a parameter the rules cannot place.

        The dashboard can write a value it has a rule for; a line it has no rule
        for is not something it can help with.  So for those it hands over the
        text, and takes back whatever the user typed -- the write path below is
        the only thing that knows how to put that on disk, and it does it the
        same way a parameter write does: atomically, and behind a snapshot.
        """
        raw = case_file(case_dir, rel).read_bytes()
        try:
            return file_payload(rel, raw)
        except UnicodeDecodeError as exc:
            raise ApiError(400, f"{rel} is not UTF-8 text; it cannot be edited in the panel: {exc}")

    def save_file(self, case_dir: Path, rel: str, text: str, sha: str) -> dict:
        target = case_file(case_dir, rel)
        state = self.registry.get(case_dir)
        with state.lock:
            raw = target.read_bytes()
            # The file may have moved on since it was read -- a parameter write
            # can land in between.  Refusing beats overwriting that.
            if sha and sha != hashlib.sha256(raw).hexdigest():
                raise ApiError(409, f"{rel} changed after it was opened; close it and reopen to edit.")

            data = encode_like(text, raw)
            if data == raw:
                return {"file": rel, "is_noop": True, "bytes": len(raw), "sha": sha}
            writer_mod.atomic_write(target, data)
            state.push_snapshot("manual edit", {rel: raw}, [rel])
            return {
                "file": rel,
                "is_noop": False,
                "bytes": len(data),
                "sha": hashlib.sha256(data).hexdigest(),
            }


APP = Dashboard()


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "caseDashboard"
    protocol_version = "HTTP/1.1"

    #: Names that mean "this machine".  The dashboard binds to loopback and is
    #: only ever reached as one of these.
    LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

    # -- plumbing ----------------------------------------------------------
    def log_message(self, fmt, *args):  # quieter console
        if os.environ.get("CASE_DASHBOARD_VERBOSE"):
            super().log_message(fmt, *args)

    def _foreign_request(self) -> str:
        """Why this request did not come from the dashboard's own page, or "".

        Letting a case live anywhere on disk moves the threat model.  The
        dashboard reads and writes whatever it is pointed at, and *any page the
        browser is showing* can reach 127.0.0.1 -- so without this, a page you
        happen to visit could ask the dashboard to list the disk and then edit
        what it found.  While cases were confined to the repository the worst
        that bought was repository files; it is now worth refusing.

        Browsers label their cross-site traffic and a rebound hostname shows up
        in ``Host``, so those two headers are enough to separate the dashboard's
        own pages from somebody else's.  Requests from something that is not a
        browser at all (a script, a probe, the end-to-end suite) carry neither
        and are let through.
        """
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return "it came from another site"
        origin = self.headers.get("Origin")
        if origin and (urlparse(origin).hostname or "") not in self.LOCAL_HOSTS:
            return f"it came from {origin}"
        host = self.headers.get("Host") or ""
        # `[::1]:8765` -- the port is after the bracket, the address inside it.
        host = host.split("]")[0].lstrip("[") if host.startswith("[") else host.split(":")[0]
        if host and host.lower() not in self.LOCAL_HOSTS:
            return f"the dashboard was reached as {host!r}"
        return ""

    def _send_json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(400, f"Request body is not valid JSON: {exc}")

    def _query(self) -> Dict[str, str]:
        parsed = urlparse(self.path)
        flat = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        return flat

    def _route(self) -> Tuple[str, List[str]]:
        parsed = urlparse(self.path)
        parts = [unquote(p) for p in parsed.path.split("/") if p]
        return parsed.path, parts

    # -- GET ---------------------------------------------------------------
    def do_GET(self) -> None:
        path, parts = self._route()
        try:
            foreign = self._foreign_request()
            if foreign:
                raise ApiError(403, f"Refused: {foreign}.")
            if path.startswith("/api/"):
                return self._api_get(path, parts)
            return self._serve_static(path)
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:  # noqa: BLE001 - surface, never crash the server
            traceback.print_exc()
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self) -> None:
        path, parts = self._route()
        try:
            foreign = self._foreign_request()
            if foreign:
                raise ApiError(403, f"Refused: {foreign}.")
            return self._api_post(path, parts)
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # -- API: GET ----------------------------------------------------------
    def _api_get(self, path: str, parts: List[str]) -> None:
        q = self._query()

        if path == "/api/cases":
            return self._send_json({"cases": discover_cases(), "repo": str(REPO_DIR)})

        if path == "/api/case":
            case_dir = resolve_case(q.get("path", ""))
            return self._send_json(APP.case_payload(case_dir))

        if path == "/api/browse":
            # Deliberately *not* validated as a case: this is the walk to one.
            return self._send_json(browse_dir(q.get("path", "")))

        if path == "/api/file":
            case_dir = resolve_case(q.get("path", ""))
            return self._send_json(APP.read_file(case_dir, q.get("file", "")))

        raise ApiError(404, f"Unknown endpoint {path}")

    # -- API: POST ---------------------------------------------------------
    def _api_post(self, path: str, parts: List[str]) -> None:
        if path == "/api/case/preview":
            body = self._read_json()
            case_dir = resolve_case(body.get("path", ""))
            return self._send_json(APP.preview(case_dir, body.get("edits") or []))

        if path == "/api/case/apply":
            body = self._read_json()
            case_dir = resolve_case(body.get("path", ""))
            return self._send_json(APP.apply(case_dir, body.get("edits") or []))

        if path == "/api/case/revert":
            body = self._read_json()
            case_dir = resolve_case(body.get("path", ""))
            return self._send_json(APP.revert(case_dir))

        if path == "/api/case/derive":
            body = self._read_json()
            case_dir = resolve_case(body.get("path", ""))
            resolved, _ = read_case(case_dir)
            return self._send_json(
                derived_mod.compute(resolved, body.get("edits") or [])
            )

        if path == "/api/file/save":
            body = self._read_json()
            case_dir = resolve_case(body.get("path", ""))
            text = body.get("text")
            if not isinstance(text, str):
                raise ApiError(400, "Missing text")
            return self._send_json(
                APP.save_file(
                    case_dir, str(body.get("file") or ""), text, str(body.get("sha") or "")
                )
            )

        raise ApiError(404, f"Unknown endpoint {path}")

    # -- static ------------------------------------------------------------
    def _serve_static(self, path: str) -> None:
        if not DIST_DIR.is_dir():
            return self._send_json(
                {
                    "error": "Frontend not built yet",
                    "hint": "In development, open the Vite port (5173 by default); "
                            "otherwise run `python caseDashboard/run.py --prod` to build first.",
                    "dist": str(DIST_DIR),
                },
                200,
            )
        rel = posixpath.normpath(path.lstrip("/"))
        if rel in (".", ""):
            rel = "index.html"
        target = (DIST_DIR / rel).resolve()
        if not is_under(target, DIST_DIR) or not target.is_file():
            target = DIST_DIR / "index.html"  # SPA fallback
        if not target.is_file():
            raise ApiError(404, "Static asset not found")
        body = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if target.name == "index.html":
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(body)


def serve(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


if __name__ == "__main__":
    httpd = serve()
    print(f"caseDashboard API on http://{HOST}:{PORT}")
    httpd.serve_forever()
