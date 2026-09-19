"""Read-only probe of a case's ``step*.sh`` pipeline.

Around the parameters a case has a pipeline: one script cleans the previous run
away, one builds the mesh and the initial field, one runs the solver, one
reconstructs the parallel results, and one or two turn the output into an
animation and a curve.  Those scripts are run by hand outside the dashboard, so
nothing here runs them -- all this module does is say what each one has already
left on disk, and the panel renders that.

Two rules keep it honest and cheap:

* **Nothing opens a file.**  Every answer is a ``stat``, a ``glob`` or a
  directory listing; the solver log is megabytes and only its size is wanted.
* **Nothing starts a process.**  That is the whole dashboard's contract, and
  ``selftest`` scans this directory for anything that would break it.

Nothing here parses a shell script either.  What a script deletes or produces
is declared below, because a case's cleanup is a known quantity and reading it
out of the text would make this module's answers depend on shell syntax.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: ``step1``, ``step 2``, ``STEP_3`` -- the marker, however a case spells it.
_STEP_RE = re.compile(r"step\s*(\d+)", re.I)

#: What ``blockMesh`` writes.  All five are what "the mesh is built" means;
#: ``polyMesh`` existing is not the same thing as it being complete.
_MESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")

#: The cleanup step's targets, as the two spellings in this repository use them
#: -- ``step1_allclean.sh`` against ``allclean_step1``.  This is the *union* of
#: the two, fixed rather than worked out per case: a case whose cleanup never
#: touched ``CFD/ani.*`` -- or the reconstructed times, which only the longer
#: spelling deletes -- simply reports that path as missing, which is true and
#: harmless.  ``log/`` is deliberately not here -- the cleanup recreates it.
_CLEAN_TARGETS: Tuple[Tuple[str, str], ...] = (
    ("CFD/constant/polyMesh", "dir"),
    ("CFD/processor*", "dirs"),
    ("DEM/post", "contents"),
    ("log_CFDEM_IB", "file"),
    ("CFD/ani.*", "files"),
    ("CFD/log.liggghts", "file"),
    ("CFD/<time>", "times"),
)

#: Stem -> which check it gets.  A stem this table has never seen is not an
#: error: the naming is not uniform between cases, and a script the dashboard
#: cannot describe says so instead of guessing.
CHECK_BY_TOKEN: Dict[str, str] = {
    "allclean": "clean",
    "blockmeshsetfields": "mesh",
    "allrun": "run",
    "reconstruct": "reconstruct",
    "ani": "gif",
    "draw_curve": "curve",
}

#: English fallbacks; the panel translates by ``check`` id, not by this text.
TITLES: Dict[str, str] = {
    "clean": "Cleanup",
    "mesh": "Mesh and initial field",
    "run": "Solver run",
    "reconstruct": "Reconstruct parallel results",
    "gif": "Build the animation GIF",
    "curve": "Plot the DEM curve",
    "unknown": "Unrecognized script",
}


# ---------------------------------------------------------------------------
# naming
# ---------------------------------------------------------------------------


def parse_script(name: str) -> Tuple[Optional[int], str]:
    """``(step number, stem)`` for a script name; ``(None, "")`` if it is not one.

    The order matters and is why this is not a one-liner.  ``.sh`` is stripped
    *first*, so the ``.sh`` in ``Allrun.sh_step3`` survives the removal of the
    step marker and can be cleaned up last -- the marker sits *after* the
    extension in that spelling, which is the whole peculiarity.
    """
    stem = name[:-3] if name.lower().endswith(".sh") else name
    match = _STEP_RE.search(stem)
    if not match:
        return None, ""
    token = (stem[: match.start()] + stem[match.end() :]).strip(" _-.")
    if token.lower().endswith(".sh"):
        token = token[:-3].strip(" _-.")
    return int(match.group(1)), token


def find_scripts(case_dir: Path) -> List[dict]:
    """Every ``step<number>`` script in the case directory, in pipeline order.

    Only files directly in the case directory are looked at: a subdirectory
    holds something else -- ``multi_sphere_fish/new/`` is a template copy, not
    part of the pipeline -- and a name has to carry a step number to count.
    """
    found = []
    for child in _entries(case_dir):
        if not child.is_file():
            continue
        step, token = parse_script(child.name)
        if step is None:
            continue
        found.append({"script": child.name, "step": step, "token": token})
    found.sort(key=lambda s: (s["step"], s["token"].lower(), s["script"]))
    return found


# ---------------------------------------------------------------------------
# small read-only helpers
# ---------------------------------------------------------------------------


def _entries(path: Path) -> List[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []


def _glob(case_dir: Path, pattern: str, want: str = "file") -> List[Path]:
    try:
        paths = list(case_dir.glob(pattern))
    except OSError:
        return []
    keep = Path.is_dir if want == "dir" else Path.is_file
    return [p for p in paths if keep(p)]


def _file_size(path: Path) -> Optional[int]:
    """The path's size, or ``None`` when there is no file there."""
    try:
        return path.stat().st_size if path.is_file() else None
    except OSError:
        return None


def _size(n: int) -> str:
    """Bytes as a short human figure -- the only unit detail rows ever carry."""
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


def _row(path: str, state: str, detail: str = "") -> dict:
    """One evidence line: what was looked for, how it turned out, and a number."""
    return {"path": path, "state": state, "detail": detail}


def _time_dirs(case_dir: Path) -> List[str]:
    """The reconstructed time directories under ``CFD/``.

    A time is a directory whose name is a number, which is what keeps
    ``constant``, ``system`` and ``processor0`` out.  ``0`` is the initial field
    written by the setup step, not a reconstruction, so it does not count.
    """
    out = []
    for path in _entries(case_dir / "CFD"):
        if not path.is_dir() or path.name == "0":
            continue
        try:
            float(path.name)
        except ValueError:
            continue
        out.append(path.name)
    return sorted(out, key=float)


def _facts(case_dir: Path) -> dict:
    """The few things more than one check needs, measured once per probe."""
    mesh_files = [
        name
        for name in _MESH_FILES
        if (case_dir / "CFD" / "constant" / "polyMesh" / name).is_file()
    ]
    log_sizes = [
        _file_size(case_dir / rel) for rel in ("log/log_CFDEM_IB", "log_CFDEM_IB")
    ]
    return {
        "mesh_files": mesh_files,
        "mesh_done": len(mesh_files) == len(_MESH_FILES),
        "run_done": max((s for s in log_sizes if s is not None), default=0) > 0,
    }


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------


def check_clean(case_dir: Path, facts: dict) -> Tuple[str, List[dict]]:
    """Whether the previous run's artifacts are gone.

    Neutral by design: this step is a script that removes things, so "there is
    nothing here" is the answer it wants, and a case that has not been cleaned
    yet is the ordinary state before a run rather than a problem.
    """
    rows = [_clean_row(case_dir, pattern, kind) for pattern, kind in _CLEAN_TARGETS]
    clean = all(row["state"] == "absent" for row in rows)
    return ("clean" if clean else "dirty"), rows


def _clean_row(case_dir: Path, pattern: str, kind: str) -> dict:
    if kind == "file":
        size = _file_size(case_dir / pattern)
        if size is None:
            return _row(pattern, "absent")
        return _row(pattern, "partial" if size == 0 else "present", _size(size))
    if kind == "dir":
        return _row(pattern, "present" if (case_dir / pattern).is_dir() else "absent")
    if kind == "contents":
        # The directory itself is recreated empty by the cleanup, so what says
        # "gone" is an empty or missing directory, not a missing one.
        count = len(_entries(case_dir / pattern))
        return _row(pattern, "present" if count else "absent", str(count) if count else "")
    if kind == "times":
        # The reconstructed times, which no glob can isolate -- ``0`` sits among
        # them and is the initial field, so it is not this step's to remove.
        # Counted rather than listed, for the reason ``check_reconstruct`` gives.
        count = len(_time_dirs(case_dir))
        return _row(pattern, "present" if count else "absent", str(count) if count else "")
    hits = _glob(case_dir, pattern, "dir" if kind == "dirs" else "file")
    if not hits:
        return _row(pattern, "absent")
    return _row(pattern, "present", str(len(hits)))


def check_mesh(case_dir: Path, facts: dict) -> Tuple[str, List[dict]]:
    """Whether the mesh and the initial field have been built."""
    found = facts["mesh_files"]
    total = len(_MESH_FILES)
    if len(found) == total:
        mesh_state = "present"
    elif found:
        mesh_state = "partial"
    else:
        mesh_state = "absent"
    rows = [
        _row(
            "CFD/constant/polyMesh",
            mesh_state,
            f"{len(found)}/{total}" if found else "",
        )
    ]
    alpha = _file_size(case_dir / "CFD" / "0" / "alpha.water")
    rows.append(
        _row(
            "CFD/0/alpha.water",
            "absent" if alpha is None else "present",
            _size(alpha) if alpha else "",
        )
    )
    return ("done" if len(found) == total else "pending"), rows


def check_run(case_dir: Path, facts: dict) -> Tuple[str, List[dict]]:
    """Whether the solver has run, judged by the log it writes.

    Which of the two places that log lands in is the case's own choice -- the
    launch script names it -- so both are looked at, and either one counts.
    Only "it has content" is asked: a log is not read to see how the run ended.
    """
    rows = []
    for rel in ("log/log_CFDEM_IB", "log_CFDEM_IB"):
        size = _file_size(case_dir / rel)
        if size is None:
            rows.append(_row(rel, "absent"))
        else:
            rows.append(_row(rel, "partial" if size == 0 else "present", _size(size)))

    dumps = _glob(case_dir, "DEM/post/dump*.liggghts")
    rows.append(
        _row(
            "DEM/post/dump*.liggghts",
            "present" if dumps else "absent",
            str(len(dumps)) if dumps else "",
        )
    )
    procs = _glob(case_dir, "CFD/processor*", "dir")
    rows.append(
        _row(
            "CFD/processor*",
            "present" if procs else "absent",
            str(len(procs)) if procs else "",
        )
    )

    if facts["run_done"]:
        return "done", rows
    return ("ready" if facts["mesh_done"] else "pending"), rows


def check_reconstruct(case_dir: Path, facts: dict) -> Tuple[str, List[dict]]:
    """Whether the parallel results have been merged back into one case.

    The time directories are counted, not listed.  A run of any length leaves
    dozens of them, and one row each would make this card taller than the page
    and push the other five out of sight -- while the number alone already says
    that the merge happened.
    """
    times = _time_dirs(case_dir)
    rows = [
        _row(
            "CFD/<time>",
            "present" if times else "absent",
            str(len(times)) if times else "",
        )
    ]
    if times:
        return "done", rows
    return ("ready" if facts["run_done"] else "pending"), rows


def check_gif(case_dir: Path, facts: dict) -> Tuple[str, List[dict]]:
    """Whether the animation exists, or at least its frames do.

    The frames are exported from ParaView by hand, so a directory of PNGs with
    no GIF is the normal state after a run -- "ready" rather than "not started".
    """
    gifs = _glob(case_dir, "ani/*.gif")
    frames = _glob(case_dir, "ani/*.png")
    rows = [
        _row("ani/*.gif", "present" if gifs else "absent", str(len(gifs)) if gifs else ""),
        _row(
            "ani/*.png",
            "present" if frames else "absent",
            str(len(frames)) if frames else "",
        ),
    ]
    if gifs:
        return "done", rows
    return ("ready" if frames else "pending"), rows


def check_curve(case_dir: Path, facts: dict) -> Tuple[str, List[dict]]:
    """Whether the DEM velocity curve has been drawn from the dumps."""
    png = _file_size(case_dir / "results" / "vz_vs_time.png")
    dumps = _glob(case_dir, "DEM/post/dump*.liggghts")
    rows = [
        _row(
            "results/vz_vs_time.png",
            "absent" if png is None else "present",
            _size(png) if png else "",
        ),
        _row(
            "DEM/post/dump*.liggghts",
            "present" if dumps else "absent",
            str(len(dumps)) if dumps else "",
        ),
    ]
    if png is not None:
        return "done", rows
    return ("ready" if dumps else "pending"), rows


def check_unknown(case_dir: Path, facts: dict) -> Tuple[str, List[dict]]:
    """A script whose step number is there but whose name means nothing here."""
    return "unknown", []


_CHECKS = {
    "clean": check_clean,
    "mesh": check_mesh,
    "run": check_run,
    "reconstruct": check_reconstruct,
    "gif": check_gif,
    "curve": check_curve,
    "unknown": check_unknown,
}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def probe(case_dir: Path) -> dict:
    """Every step script the case has, and what each one has produced so far."""
    facts = _facts(case_dir)
    scripts = []
    for found in find_scripts(case_dir):
        check = CHECK_BY_TOKEN.get(found["token"].lower(), "unknown")
        status, evidence = _CHECKS[check](case_dir, facts)
        scripts.append(
            {
                "id": found["script"],
                "script": found["script"],
                "step": found["step"],
                "token": found["token"],
                "check": check,
                "title": TITLES[check],
                "status": status,
                "evidence": evidence,
            }
        )
    return {"scripts": scripts}
