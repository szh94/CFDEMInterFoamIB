"""End-to-end HTTP checks against a throwaway copy of the case.

Run from the repository root::

    python -m caseDashboard.server.e2e

``selftest`` covers the writer at the byte level; this covers what only the
HTTP layer can show -- that a preview does not touch disk, that apply/revert
round-trips exactly, and that the path guards hold.

The case is staged under ``caseDashboard/.cache/e2e/`` (gitignored) so the real
tutorial files are never written to.
"""

from __future__ import annotations

import http.client
import json
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Tuple

REPO_DIR = Path(__file__).resolve().parents[2]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from caseDashboard.server import app as backend  # noqa: E402
from caseDashboard.server.profiles import FILES  # noqa: E402

SRC_CASE = REPO_DIR / "tutorial" / "two_phase_sphere_settling"
#: A second, read-only case the parameter list was *not* written for.  It is only
#: ever read -- nothing in this suite writes to tutorial/.
OTHER_CASE = REPO_DIR / "tutorial" / "multi_sphere_fish"
STAGE_ROOT = REPO_DIR / "caseDashboard" / ".cache" / "e2e"
STAGE = STAGE_ROOT / "two_phase_sphere_settling"
CASE_REL = "caseDashboard/.cache/e2e/two_phase_sphere_settling"
DEM_REL = "DEM/in.liggghts_run"

PORT = backend.PORT + 2

#: The one particle row of ``two_phase_sphere_settling``, as ``dem.particles``
#: reads it: note, x, y, z, diameter, density, vx, vy, vz.  Spelled out because
#: a table value is a whole row, and a preview/apply that moved a cell has to
#: send the rest of it back unchanged.
PARTICLE_ROW = ["single sphere", 0.05, 0.05, 0.12, 0.0167, 1250.0, 0.0, 0.0, 0.0]


def particle_edit(diameter: float) -> dict:
    """An edit of the diameter cell, carrying the row it lives in."""
    row = list(PARTICLE_ROW)
    row[4] = diameter
    return {"id": "dem.particles", "value": [row]}


_results: List[Tuple[str, bool, str]] = []


def t(name: str, condition, extra: str = "") -> None:
    _results.append((name, bool(condition), "" if condition else str(extra)))


def stage_case() -> None:
    """Copy the parameter list's files byte for byte, plus the step scripts."""
    if STAGE_ROOT.exists():
        shutil.rmtree(STAGE_ROOT)
    STAGE.mkdir(parents=True)
    for rel in FILES:
        target = STAGE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SRC_CASE / rel, target)
    # The step scripts are not parameters, so they are not in FILES -- but they
    # are what `/api/steps` is about, and the staged copy has to have them.
    for script in sorted(SRC_CASE.glob("step*.sh")):
        shutil.copyfile(script, STAGE / script.name)


class Client:
    def __init__(self, base: str) -> None:
        self.base = base

    def get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=60) as r:
            return json.loads(r.read())

    def post(self, path: str, body: dict):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())


def run() -> None:
    stage_case()
    dem = STAGE / DEM_REL
    original = dem.read_bytes()
    original_crlf = original.count(b"\r\n")

    httpd = backend.serve("127.0.0.1", PORT)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    api = Client(f"http://127.0.0.1:{PORT}")

    try:
        _read(api)
        _steps(api)
        _derive(api)
        _preview(api, dem, original)
        _apply(api, dem, original, original_crlf)
        _revert(api, dem, original)
        _product(api)
        _toggle(api, dem, original)
        _noop(api, dem, original)
        _guards(api)
        _browse(api)
        _outside_case(api)
        _foreign_origin(api)
        _file_editor(api, dem)
        _unfamiliar(api)
    finally:
        httpd.shutdown()
        httpd.server_close()
        shutil.rmtree(STAGE_ROOT, ignore_errors=True)


def _read(api: Client) -> None:
    payload = api.get(f"/api/case?path={CASE_REL}")
    t("every parameter resolved", len(payload["params"]) == 144, len(payload["params"]))
    # The `vertices` rule is the one that is a *table* rather than a value, so
    # what is worth pinning over HTTP is the three things that make it one: the
    # flag the panel branches on, the coordinates themselves -- resolved through
    # the macros at the top of the file, not the `$xco1` the file spells -- and
    # the parameter each component came from, which is how an edit of the domain
    # extent reaches a row the panel is not touching.
    verts = next(p for p in payload["params"] if p["id"] == "mesh.vertices")
    t(
        "the blockMeshDict vertex table arrives as eight rows of resolved coordinates",
        verts["type"] == "float3"
        and verts["repeats"] is True
        and verts["value"]
        == [
            [0.0, 0.0, 0.0],
            [0.0, 0.1, 0.0],
            [0.0, 0.0, 0.2],
            [0.0, 0.1, 0.2],
            [0.1, 0.0, 0.0],
            [0.1, 0.1, 0.0],
            [0.1, 0.0, 0.2],
            [0.1, 0.1, 0.2],
        ]
        and verts["macros"][0] == ["mesh.xco1", "mesh.yco1", "mesh.zco1"],
        (verts["type"], verts["repeats"], verts["value"], verts["macros"]),
    )
    t(
        "panel is fluid / particle / coupling / steps",
        [g["id"] for g in payload["groups"]] == ["fluid", "particle", "coupling", "steps"],
        [g["id"] for g in payload["groups"]],
    )
    # Only the last of them is a script list; the three physics tabs hold fields,
    # and the panel picks which to render off this rather than off the id.
    t(
        "only the steps tab is a script list",
        [g["kind"] for g in payload["groups"]] == ["params", "params", "params", "scripts"],
        [g.get("kind") for g in payload["groups"]],
    )
    # Script state is a fact about the directory, not a dictionary: it is served
    # by `/api/steps` and must not creep into the per-case payload, which several
    # things (the case list, the derived panel) take whole.
    t(
        "the case payload has no steps / active_run (script state is /api/steps)",
        not any(k in payload for k in ("steps", "active_run")),
        [k for k in payload if k in ("steps", "active_run")],
    )

    # Particle type and creation: this case creates a single particle, so the
    # whole multisphere route is unused -- located, not wanted -- and must not
    # turn into a warning about rules that could not be found.
    ms = [p for p in payload["params"] if p["id"].startswith("dem.ms.")]
    t(
        "single-sphere case marks the multisphere parameters unused and read-only",
        len(ms) == 26 and all(p["status"] == "unused" and p["editable"] is False for p in ms),
        [(p["id"], p["status"], p["editable"]) for p in ms if p["status"] != "unused"],
    )
    single = [
        p
        for p in payload["params"]
        if p["id"] in ("dem.zone_notes", "dem.particles")
    ]
    t(
        "single-sphere case has no unrecognized parameters and its single-particle ones stay writable",
        payload["recognition"]["unrecognized"] == []
        and len(single) == 2
        and all(p["status"] == "ok" and p["editable"] for p in single),
        payload["recognition"]["unrecognized"] or [p["id"] for p in single if not p["editable"]],
    )
    # The particle block arrives as a note line plus a one-row table spread over
    # three lines, each column typed and labelled for the panel's own boxes.
    notes = next(p for p in payload["params"] if p["id"] == "dem.zone_notes")
    particles = next(p for p in payload["params"] if p["id"] == "dem.particles")
    t(
        "the particle block arrives as its notes plus one row per particle",
        notes["type"] == "text"
        and notes["value"] == ["create single partciles"]
        and particles["repeats"] is True
        and particles["value"]
        == [["single sphere", 0.05, 0.05, 0.12, 0.0167, 1250.0, 0.0, 0.0, 0.0]]
        and [c["label"] for c in particles["columns"]]
        == ["note", "x", "y", "z", "diameter", "density", "vx", "vy", "vz"],
        (notes["value"], particles["value"], particles["columns"]),
    )

    # The physical-properties card is one card over three `constant/` dictionaries,
    # which is why the header reads the files off its items: what is worth pinning
    # is that they are grouped as one and that all three are writable.
    #
    # It also carries everything a phase *has* that follows from its
    # `transportModel` line -- its `nu`, the coefficients of any other model,
    # and its density -- and the panel unfolds those from that row rather than
    # laying them out in the card.  Both phases here run Newtonian, so the 20
    # coefficients each of the other five models would need are all `inactive`:
    # located, belonging to a model nobody selected, and neither editable nor
    # written.
    phys = [p for p in payload["params"] if p["card"] == "Physical properties"]
    owned = [p for p in phys if p["owner"]]
    coeffs = [p for p in owned if p["block"]]
    plain = [p for p in phys if not p["owner"]]
    t(
        "the physical properties are one card over three dictionaries",
        len(plain) == 5
        and {p["source"]["file"] for p in plain}
        == {
            "CFD/constant/transportProperties",
            "CFD/constant/turbulenceProperties",
            "CFD/constant/g",
        }
        and all(p["status"] == "ok" and p["editable"] for p in plain),
        [(p["id"], p["status"]) for p in plain] or len(plain),
    )
    t(
        "each phase's parameters follow from its transportModel line",
        len(owned) == 44
        and all(
            p["owner"]
            == ("phys.water.transportModel" if p["id"].startswith("phys.water.") else "phys.air.transportModel")
            for p in owned
        ),
        [(p["id"], p["owner"]) for p in owned],
    )
    t(
        "none of the coefficients is live while both phases run Newtonian",
        len(coeffs) == 40
        and all(p["status"] == "inactive" and p["editable"] is False for p in coeffs),
        [(p["id"], p["status"]) for p in coeffs if p["status"] != "inactive"] or len(coeffs),
    )
    t(
        "every coefficient names the model and block it belongs to",
        all(p["model"] in p["id"] and p["block"] == f"{p['model']}Coeffs" for p in coeffs)
        and {p["id"]: p["model"] for p in owned if p["block"] is None}
        == {
            "phys.water.nu": "Newtonian",
            "phys.air.nu": "Newtonian",
            # Density is owned but model-less: it belongs to the row and is read
            # under every model, so no switch can turn it off.
            "phys.water.rho": None,
            "phys.air.rho": None,
        },
        [p["id"] for p in coeffs if not p["model"]],
    )
    t(
        "every dictionary the panel can show has a label to title its card with",
        all(f in payload["file_labels"] for f in payload["files"]),
        [f for f in payload["files"] if f not in payload["file_labels"]],
    )

    # The output card is the second one that is a concern rather than a file, and
    # it holds a line the deck does not name either: the dump period is the
    # `outSteps` variable the dump command interpolates.
    out = [p for p in payload["params"] if p["card"] == "Output control"]
    t(
        "the two output rates share one card",
        [p["id"] for p in out] == ["dem.thermo", "dem.outSteps"]
        and all(p["status"] == "ok" and p["editable"] for p in out),
        [(p["id"], p["status"]) for p in out] or len(out),
    )


def _steps(api: Client) -> None:
    """The run-steps tab: where the pipeline has got to, read off the disk.

    The staged case was copied from the tutorial *without* its artifacts, so
    every state below is one this test creates -- which is what lets it walk the
    pipeline from "nothing has run" to "everything has" one artifact at a time,
    and check the guard rails in between.
    """

    def scripts() -> dict:
        return {s["id"]: s for s in api.get(f"/api/steps?path={CASE_REL}")["scripts"]}

    def statuses() -> dict:
        return {name: s["status"] for name, s in scripts().items()}

    def evidence(name: str) -> dict:
        return {row["path"]: row for row in scripts()[name]["evidence"]}

    ids = [
        "step1_allclean.sh",
        "step2_blockmeshsetfields.sh",
        "step3_Allrun.sh",
        "step4_reconstruct.sh",
        "step5_ani.sh",
        "step5_draw_curve.sh",
    ]
    listed = scripts()
    t(
        "the step page lists the six scripts in pipeline order",
        list(listed) == ids,
        list(listed),
    )
    t(
        "each script carries the step number and its check",
        [(listed[i]["step"], listed[i]["check"]) for i in ids]
        == [(1, "clean"), (2, "mesh"), (3, "run"), (4, "reconstruct"), (5, "gif"), (5, "curve")],
        [(listed[i]["step"], listed[i]["check"]) for i in ids],
    )

    st = statuses()
    t(
        "with no artifacts the case is clean and nothing has run",
        st["step1_allclean.sh"] == "clean"
        and all(v == "pending" for k, v in st.items() if k != "step1_allclean.sh"),
        st,
    )

    # One mesh file is not a mesh, but it is already something the cleanup
    # step would delete -- which is how the first card turns from "clean" to
    # "artifacts still present" while the second stays unstarted.
    mesh = STAGE / "CFD" / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    (mesh / "points").write_bytes(b"x")
    st = statuses()
    t("a partial mesh does not complete the setup step", st["step2_blockmeshsetfields.sh"] == "pending", st)
    t("and the case is no longer clean", st["step1_allclean.sh"] == "dirty", st)

    for name in ("faces", "owner", "neighbour", "boundary"):
        (mesh / name).write_bytes(b"x")
    st = statuses()
    t("the full mesh set completes the setup step", st["step2_blockmeshsetfields.sh"] == "done", st)
    t("the solver step is then ready to run", st["step3_Allrun.sh"] == "ready", st)

    log_dir = STAGE / "log"
    log_dir.mkdir(parents=True)
    log = log_dir / "log_CFDEM_IB"
    log.write_bytes(b"")
    st = statuses()
    t(
        "an empty solver log is not a run",
        st["step3_Allrun.sh"] != "done",
        st,
    )
    log.write_bytes(b"solver output\n")
    st = statuses()
    t("a log with content completes the run", st["step3_Allrun.sh"] == "done", st)

    # `parCFDDEMrun.sh` names where the log goes, and the two cases in this
    # repository spell it differently -- the multi-sphere one writes it at the
    # case root.  Either place has to count.
    log.unlink()
    (STAGE / "log_CFDEM_IB").write_bytes(b"solver output\n")
    st = statuses()
    t("a solver log at the case root counts too", st["step3_Allrun.sh"] == "done", st)

    cfd = STAGE / "CFD"
    (cfd / "0").mkdir(exist_ok=True)
    st = statuses()
    t("the initial field is not a reconstructed time", st["step4_reconstruct.sh"] != "done", st)
    t(
        "nor is it something the cleanup step would remove",
        evidence("step1_allclean.sh")["CFD/<time>"]["state"] == "absent",
        evidence("step1_allclean.sh")["CFD/<time>"],
    )
    (cfd / "0.01").mkdir()
    (cfd / "0.01" / "U").write_bytes(b"x")
    st = statuses()
    t("a time directory completes the reconstruction", st["step4_reconstruct.sh"] == "done", st)
    # The same directory is a leftover for step1 to clean -- which is what makes
    # the first card read "artifacts still present" after a run.
    t(
        "and the reconstructed time is a leftover for the cleanup step",
        evidence("step1_allclean.sh")["CFD/<time>"]
        == {"path": "CFD/<time>", "state": "present", "detail": "1"},
        evidence("step1_allclean.sh")["CFD/<time>"],
    )

    ani = STAGE / "ani"
    ani.mkdir()
    (ani / "x.0000.png").write_bytes(b"x")
    st = statuses()
    t("frames alone mean the GIF can be built", st["step5_ani.sh"] == "ready", st)
    (ani / "x.gif").write_bytes(b"x")
    st = statuses()
    t("the GIF completes the animation step", st["step5_ani.sh"] == "done", st)

    post = STAGE / "DEM" / "post"
    post.mkdir(parents=True)
    (post / "dump0.liggghts").write_bytes(b"x")
    st = statuses()
    t("a dump alone means the curve can be drawn", st["step5_draw_curve.sh"] == "ready", st)
    results = STAGE / "results"
    results.mkdir()
    (results / f"{STAGE.name}_vz_vs_time.png").write_bytes(b"x")
    st = statuses()
    t("the plot completes the curve step", st["step5_draw_curve.sh"] == "done", st)

    payload = api.get(f"/api/case?path={CASE_REL}")
    t(
        "script state stays out of the case payload",
        not any(k in payload for k in ("steps", "active_run")),
        [k for k in payload if k in ("steps", "active_run")],
    )
    try:
        api.get("/api/steps?path=README.md")
    except urllib.error.HTTPError as exc:
        t("the step page refuses a path that is not a case", exc.code == 400, exc.code)
    else:
        t("the step page refuses a path that is not a case", False, "no error raised")


def _derive(api: Client) -> None:
    d = api.post("/api/case/derive", {"path": CASE_REL, "edits": []})
    refs = [r for m in d["metrics"] for r in m["source_refs"]]
    t("metrics carry source_refs", bool(refs), "metrics reference no parameters")
    # The UI renders `label` and `file:line` straight from these; a bare param
    # id here used to crash <MetricCard> and blank the whole page.
    t(
        "source_refs are expanded to objects",
        all(isinstance(r, dict) and r.get("file") and r.get("param_id") for r in refs),
        [r for r in refs if not (isinstance(r, dict) and r.get("file"))][:3],
    )


def _preview(api: Client, dem: Path, original: bytes) -> None:
    pv = api.post(
        "/api/case/preview",
        {"path": CASE_REL, "edits": [particle_edit(0.02)]},
    )
    changed = [d for d in pv["diffs"] if not d["byte_identical"]]
    t("preview reports exactly 1 changed file", len(changed) == 1, [d["file"] for d in pv["diffs"]])
    t("preview writes nothing", dem.read_bytes() == original, "the file was modified by the preview")
    if not changed:
        return
    rows = [r for h in changed[0]["hunks"] for r in h["rows"] if r["type"] != "equal"]
    t("diff has exactly 1 changed row", len(rows) == 1, len(rows))
    t("diff carries the new value", rows and "0.02" in (rows[0]["b"] or ""), rows)


def _apply(api: Client, dem: Path, original: bytes, original_crlf: int) -> None:
    ap = api.post(
        "/api/case/apply",
        {"path": CASE_REL, "edits": [particle_edit(0.02)]},
    )
    t("apply writes 1 file", len(ap["written"]) == 1, ap["written"])
    t("apply is not a no-op", ap["is_noop"] is False)

    after = dem.read_bytes()
    t("the file changed", after != original)
    t("CRLF count unchanged", after.count(b"\r\n") == original_crlf,
      f"{after.count(b'\r\n')} vs {original_crlf}")
    t("no bare LF introduced", b"\n" not in after.replace(b"\r\n", b""), "a bare LF appeared")
    t(
        "density and everything after it untouched",
        after.split(b"density", 1)[1] == original.split(b"density", 1)[1],
    )
    t("line count unchanged", len(after.split(b"\n")) == len(original.split(b"\n")))

    reread = api.get(f"/api/case?path={CASE_REL}")
    got = next(p["value"] for p in reread["params"] if p["id"] == "dem.particles")
    t("read-back equals the written value", abs(float(got[0][4]) - 0.02) < 1e-12, got)


def _revert(api: Client, dem: Path, original: bytes) -> None:
    rv = api.post("/api/case/revert", {"path": CASE_REL})
    t("revert restores byte for byte", dem.read_bytes() == original, "bytes differ from the original")
    t("revert reports the restored file", len(rv["restored"]) == 1, rv["restored"])

    reread = api.get(f"/api/case?path={CASE_REL}")
    got = next(p["value"] for p in reread["params"] if p["id"] == "dem.particles")
    t("read-back after revert shows the original value", abs(float(got[0][4]) - 0.0167) < 1e-9, got)


def _product(api: Client) -> None:
    """Derived params over HTTP: read-only in the payload, and the writer
    re-syncs the lines from the directions without being asked."""
    payload = api.get(f"/api/case?path={CASE_REL}")
    subs = next(p for p in payload["params"] if p["id"] == "mesh.numberOfSubdomains")
    t("subdomain total is not editable", subs["editable"] is False, subs["editable"])
    t(
        "subdomain total declares its sources",
        subs["product_of"] == ["mesh.prox", "mesh.proy", "mesh.proz"],
        subs["product_of"],
    )
    # `mpirun -np` is the subdomain count under another name, so the launch
    # script is derived the same way rather than being a second line to keep in
    # step by hand.
    nr = next(p for p in payload["params"] if p["id"] == "run.nrProcs")
    t("MPI process count is not editable", nr["editable"] is False, nr["editable"])
    t("MPI process count shares its sources with the subdomain total", nr["product_of"] == subs["product_of"], nr["product_of"])
    # The DEM's processor grid is the third copy.  It is the one where order
    # matters -- CFDEM pairs DEM rank i with CFD subdomain i -- so it follows the
    # three directions component by component rather than as a product.
    procs = next(p for p in payload["params"] if p["id"] == "dem.processors")
    t("DEM process layout is not editable", procs["editable"] is False, procs["editable"])
    t(
        "DEM process layout declares the three directions as its sources",
        procs["product_of"] == ["mesh.prox", "mesh.proy", "mesh.proz"],
        procs["product_of"],
    )

    pv = api.post(
        "/api/case/preview",
        {"path": CASE_REL, "edits": [{"id": "mesh.prox", "value": 2}]},
    )
    t(
        "changing a decomposition direction syncs all three copies of the layout",
        sorted(pv["changed_files"])
        == ["CFD/system/decomposeParDict", "DEM/in.liggghts_run", "parCFDDEMrun.sh"],
        pv["changed_files"],
    )

    def rows_of(payload_: dict, rel: str) -> list:
        diff = next(d for d in payload_["diffs"] if d["file"] == rel)
        return [r["b"] for h in diff["hunks"] for r in h["rows"] if r["type"] != "equal"]

    rows = rows_of(pv, "CFD/system/decomposeParDict")
    t("the preview syncs exactly the direction and the subdomain total", len(rows) == 2, rows)
    t(
        "the preview already computes the subdomain total as 8",
        any(r and "numberOfSubdomains" in r and "8" in r for r in rows),
        rows,
    )
    t(
        "the preview already computes the process count as 8",
        rows_of(pv, "parCFDDEMrun.sh") == ['nrProcs="8"'],
        rows_of(pv, "parCFDDEMrun.sh"),
    )
    # x doubled against a deck that says 1 1 4: the copy lands on 2 1 4, where
    # multiplying the directions out would have written 8.
    deck = rows_of(pv, "DEM/in.liggghts_run")
    t(
        "the DEM processor grid follows the direction it was changed in",
        len(deck) == 1 and deck[0].split() == ["processors", "2", "1", "4"],
        deck,
    )

    # The coupling interval is the same quantity under two names, one per file,
    # and the two have to agree or each coupling step covers a different span of
    # physical time.  So it is typed once, on the coupling tab, and the DEM deck
    # carries a copy the writer maintains.
    every = next(p for p in payload["params"] if p["id"] == "dem.couple_every")
    t("couple_every is not editable", every["editable"] is False, every["editable"])
    t(
        "couple_every declares the coupling interval as its source",
        every["product_of"] == ["coupling.couplingInterval"],
        every["product_of"],
    )

    cpv = api.post(
        "/api/case/preview",
        {"path": CASE_REL, "edits": [{"id": "coupling.couplingInterval", "value": 250}]},
    )
    t(
        "changing the coupling interval writes the DEM deck too",
        sorted(cpv["changed_files"]) == ["CFD/constant/couplingProperties", "DEM/in.liggghts_run"],
        cpv["changed_files"],
    )
    deck = next(d for d in cpv["diffs"] if d["file"] == "DEM/in.liggghts_run")
    drow = [r["b"] for h in deck["hunks"] for r in h["rows"] if r["type"] != "equal"]
    t(
        "the DEM line is computed from the new interval",
        len(drow) == 1 and "couple_every 250" in drow[0],
        drow,
    )

    after = [
        p["value"]
        for p in api.get(f"/api/case?path={CASE_REL}")["params"]
        if p["id"] in ("mesh.numberOfSubdomains", "run.nrProcs")
    ]
    t("preview writes nothing: read-back still matches the originals", after == [4, 4], after)

    ap = api.post(
        "/api/case/apply",
        {"path": CASE_REL, "edits": [{"id": "mesh.numberOfSubdomains", "value": 9}]},
    )
    t("an explicit write of the subdomain total is rejected", bool(ap["validations"]), ap["validations"])
    t("a rejected write touches no file", ap["written"] == [], ap["written"])


def _toggle(api: Client, dem: Path, original: bytes) -> None:
    """Disabling/enabling travels as `enabled` and must survive the HTTP layer.

    The deck ships this wall commented out, so the check reads the current state
    and flips it rather than assuming either way; it ends by restoring it.
    """
    start = next(
        p
        for p in api.get(f"/api/case?path={CASE_REL}")["params"]
        if p["id"] == "dem.wall.z2"
    )
    value = float(start["value"])
    was_live = bool(start["enabled"])

    def wall_line() -> str:
        hits = [l for l in dem.read_text(encoding="utf-8").split("\n") if "zwalls2" in l]
        t("only one zwalls2 line", len(hits) == 1, hits)
        return hits[0] if hits else ""

    def apply(want: bool) -> dict:
        return api.post(
            "/api/case/apply",
            {"path": CASE_REL, "edits": [{"id": "dem.wall.z2", "value": value, "enabled": want}]},
        )

    def bare(text: str) -> str:
        return text[1:].lstrip(" ") if text.startswith("#") else text

    before_line = wall_line()
    want = not was_live
    off = apply(want)
    t("flipping the toggle writes 1 file", len(off["written"]) == 1, off["written"])
    line = wall_line()
    t("the line's comment state follows the toggle", line.startswith("#") is not want, line)
    t(
        "only the comment prefix moved",
        bare(line) == bare(before_line) and line != before_line,
        f"{line!r} vs {before_line!r}",
    )

    param = next(
        p
        for p in api.get(f"/api/case?path={CASE_REL}")["params"]
        if p["id"] == "dem.wall.z2"
    )
    t("status follows the toggle", (param["status"] == "disabled") is not want, param["status"])
    t("enabled follows the toggle", bool(param["enabled"]) is want, param["enabled"])
    t("a commented-out wall still reads its value", abs(float(param["value"]) - value) < 1e-12, param["value"])

    back = apply(was_live)
    t("flipping the toggle back writes 1 file", len(back["written"]) == 1, back["written"])
    t("flipping back restores byte for byte", dem.read_bytes() == original, "bytes differ from the original")


def _noop(api: Client, dem: Path, original: bytes) -> None:
    ap = api.post(
        "/api/case/apply",
        {"path": CASE_REL, "edits": [particle_edit(0.0167)]},
    )
    t("writing the original value back is a no-op", ap["is_noop"] is True, ap["changed_files"])
    t("bytes unchanged after the no-op", dem.read_bytes() == original)


def _guards(api: Client) -> None:
    pv = api.post(
        "/api/case/preview",
        {"path": CASE_REL, "edits": [{"id": "coupling.IBProps.alphaMin", "value": 9.0}]},
    )
    t("an out-of-range value is rejected", bool(pv["validations"]), pv["validations"])

    try:
        api.get("/api/case?path=../../etc")
    except urllib.error.HTTPError as exc:
        t("directory traversal is blocked", exc.code in (400, 403), exc.code)
    else:
        t("directory traversal is blocked", False, "no error raised")

    try:
        api.get("/api/case?path=README.md")
    except urllib.error.HTTPError as exc:
        t("a non-case path is rejected", exc.code == 400, exc.code)
    else:
        t("a non-case path is rejected", False, "no error raised")

    try:
        api.get(f"/api/file?path={CASE_REL}&file=../../../../README.md")
    except urllib.error.HTTPError as exc:
        t("only files inside the case directory can be opened", exc.code == 403, exc.code)
    else:
        t("only files inside the case directory can be opened", False, "no error raised")

    try:
        api.get(f"/api/file?path={CASE_REL}&file=DEM/nope")
    except urllib.error.HTTPError as exc:
        t("opening a missing file is rejected", exc.code == 404, exc.code)
    else:
        t("opening a missing file is rejected", False, "no error raised")


def _browse(api: Client) -> None:
    """The folder browser: one level per request, cases flagged, bounds held.

    The browser is what replaced the OS folder dialog, so what matters here is
    that it is an ordinary read-only endpoint -- it answers straight away, it can
    walk through directories that are not cases, and it refuses anything outside
    the repository exactly like every other path parameter.
    """
    root = api.get("/api/browse?path=")
    t("the browser starts at the repository root", root["path"] == "", root["path"])
    t("the root is not a ceiling", root["parent"], root["parent"])
    t("the root is not selectable as a case", not root["is_case"], root)
    t(
        "a dot-directory never reaches the listing",
        all(not e["name"].startswith(".") for e in root["entries"]),
        [e["name"] for e in root["entries"]],
    )

    listing = api.get("/api/browse?path=tutorial")
    by_name = {e["name"]: e for e in listing["entries"]}
    t("a subfolder reports the repository as its parent", listing["parent"] == "", listing)
    t("a container of cases is not itself a case", not listing["is_case"], listing)
    t(
        "a case is flagged so the browser can offer it",
        by_name.get("two_phase_sphere_settling", {}).get("is_case") is True,
        listing["entries"],
    )

    # The staged case sits under a dot-directory, which is hidden from *listings*
    # but must still be reachable when walked into explicitly -- otherwise the
    # browser could not descend past its own filter.
    staged = api.get("/api/browse?path=caseDashboard/.cache/e2e")
    t(
        "an explicitly named hidden directory still opens",
        {e["name"] for e in staged["entries"]} == {"two_phase_sphere_settling"},
        staged["entries"],
    )

    above = api.get("/api/browse?path=..")
    t("the browser can leave the repository", above["inside_repo"] is False, above)
    t(
        "outside the repository the trail starts at a filesystem root",
        above["crumbs"][0]["path"].endswith("/"),
        above["crumbs"],
    )

    try:
        api.get("/api/browse?path=README.md")
    except urllib.error.HTTPError as exc:
        t("a file cannot be browsed as a folder", exc.code == 404, exc.code)
    else:
        t("a file cannot be browsed as a folder", False, "no error raised")


def _outside_case(api: Client) -> None:
    """Read, edit and undo a case that lives nowhere near the repository.

    The dashboard used to confine every path to the repository; a case is a
    directory with a ``controlDict`` and nothing about that ties it to where this
    repository happens to be checked out.  So the whole write path has to work out
    there too, and the case has to come back named by an absolute path -- there is
    no relative one to give it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp) / "run_elsewhere"
        for rel in FILES:
            target = outside / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SRC_CASE / rel, target)

        rel_path = str(outside.resolve()).replace("\\", "/")
        payload = api.get(f"/api/case?path={urllib.parse.quote(str(outside))}")
        t("a case outside the repository opens", payload["path"] == rel_path, payload["path"])
        t(
            "an outside case is recognized like any other",
            payload["recognition"]["recognized"] == payload["recognition"]["total"],
            payload["recognition"],
        )

        # Snapshot every file the parameter list knows about, so the assertions
        # below can name whatever the edit actually landed in rather than guess.
        before = {rel: (outside / rel).read_bytes() for rel in FILES}
        edit = {"id": "coupling.IBProps.alphaMin", "value": 0.4}

        pv = api.post("/api/case/preview", {"path": str(outside), "edits": [edit]})
        t("an outside case previews a diff", bool(pv["diffs"]), pv["diffs"])

        ap = api.post("/api/case/apply", {"path": str(outside), "edits": [edit]})
        t("an outside case is written", bool(ap["written"]), ap["written"])
        t(
            "the write landed on disk outside the repository",
            all(before[rel] != (outside / rel).read_bytes() for rel in ap["changed_files"]),
            ap["changed_files"],
        )

        rv = api.post("/api/case/revert", {"path": str(outside)})
        t("an outside case reverts", bool(rv["restored"]), rv)
        t(
            "the revert restored the bytes",
            all(before[rel] == (outside / rel).read_bytes() for rel in rv["restored"]),
            rv["restored"],
        )


def _foreign_origin(api: Client) -> None:
    """Another site's page must not be able to drive this one.

    Widening cases to the whole filesystem is what makes this worth checking: the
    dashboard reads and writes whatever it is pointed at, and any page the browser
    is showing can reach 127.0.0.1.  These are the headers a browser puts on such
    a request.  Testing them needs `http.client` rather than `urllib`, which fills
    in `Host` itself and would quietly undo the one case that matters most.
    """
    host, _, port = api.base.removeprefix("http://").partition(":")
    for headers, why in (
        ({"Origin": "https://evil.example"}, "a cross-site origin"),
        ({"Sec-Fetch-Site": "cross-site"}, "a cross-site fetch"),
        ({"Host": "evil.example"}, "a rebound hostname"),
    ):
        conn = http.client.HTTPConnection(host, int(port), timeout=60)
        try:
            conn.request("GET", "/api/browse?path=", headers=headers)
            code = conn.getresponse().status
        finally:
            conn.close()
        t(f"{why} is refused", code == 403, code)


def _file_editor(api: Client, dem: Path) -> None:
    """The panel's own editor: read a file, write it back, undo it.

    This is the second write path, and unlike a parameter write it replaces the
    whole file -- so most of what is worth pinning down is that it still refuses
    to touch a file that moved on underneath it.
    """
    before = dem.read_bytes()
    f = api.get(f"/api/file?path={CASE_REL}&file={DEM_REL}")
    t("reads the case file's text", "couple_every" in f["text"], f["file"])
    t("the text handed to the editor is LF-normalised", "\r" not in f["text"], repr(f["text"][:40]))

    same = api.post(
        "/api/file/save",
        {"path": CASE_REL, "file": DEM_REL, "text": f["text"], "sha": f["sha"]},
    )
    t("saving unchanged is a no-op", same["is_noop"] is True, same)
    t("bytes unchanged after saving unchanged", dem.read_bytes() == before)

    try:
        api.post(
            "/api/file/save",
            {"path": CASE_REL, "file": DEM_REL, "text": "x", "sha": "stale"},
        )
    except urllib.error.HTTPError as exc:
        t("writing is refused when the file moved on", exc.code == 409, exc.code)
    else:
        t("writing is refused when the file moved on", False, "no error raised")
    t("a refused write leaves the file alone", dem.read_bytes() == before)

    edited = api.post(
        "/api/file/save",
        {"path": CASE_REL, "file": DEM_REL, "text": f["text"] + "# manual add\n", "sha": f["sha"]},
    )
    t("a manual edit can be written", edited["is_noop"] is False, edited)
    t("the written text is in the file", b"manual add" in dem.read_bytes())

    api.post("/api/case/revert", {"path": CASE_REL})
    t("revert undoes the manual edit", dem.read_bytes() == before)


def _unfamiliar(api: Client) -> None:
    """A case the parameter list was not written for still opens.

    ``multi_sphere_fish`` used to be refused outright ("no matching profile"),
    which made the one case in the repository that is *not* the tutorial the one
    case the dashboard could not show.  It is only ever read here; nothing in
    this suite writes to ``tutorial/``.
    """
    other = "tutorial/multi_sphere_fish"
    payload = api.get(f"/api/case?path={other}")
    t("an unfamiliar case opens too", payload["path"] == other, payload.get("path"))

    rec = payload.get("recognition") or {}
    t("it reports how many parameters were recognized", rec.get("recognized", 0) > 0, rec)
    t(
        "the recognized count is consistent with the total",
        rec.get("recognized", 0) + len(rec.get("unrecognized") or []) == rec.get("total"),
        rec,
    )
    # Everything the dashboard could not locate has to say why -- that message is
    # the whole prompt the user gets for it.
    t(
        "every unrecognized parameter carries a reason",
        all(u.get("reason") for u in rec.get("unrecognized") or []),
        [u for u in rec.get("unrecognized") or [] if not u.get("reason")][:3],
    )
    t(
        "unrecognized parameters are not editable in the panel",
        all(
            p["editable"] is False for p in payload["params"] if p["status"] == "unresolved"
        ),
    )

    # The mirror image of two_phase_sphere_settling: the multisphere route is live and
    # editable here, and the single-particle lines the deck has commented out are
    # unused rather than unlocatable.
    nspheres = next(p for p in payload["params"] if p["id"] == "dem.ms.nspheres")
    unused_ids = {p["id"] for p in payload["params"] if p["status"] == "unused"}
    unrecognized_ids = {u["id"] for u in rec.get("unrecognized") or []}
    t(
        "the multisphere case puts each route where it belongs",
        nspheres["status"] == "ok"
        and nspheres["editable"] is True
        and all(
            p["status"] == "unused"
            for p in payload["params"]
            if p["id"] in ("dem.zone_notes", "dem.particles")
        )
        and not (unused_ids & unrecognized_ids),
        sorted(unused_ids & unrecognized_ids) or nspheres,
    )
    # Adding the card must *raise* recognition: an unused group counts as
    # located, while the four single-particle lines it replaces no longer count
    # as unrecognized.  63 was the figure before the multisphere rules existed.
    t("the multisphere case recognizes more than before the change", rec.get("recognized", 0) > 63, rec.get("recognized"))

    listing = api.get("/api/cases")["cases"]
    t(
        "the case listing includes that case",
        any(c["path"] == other for c in listing),
        [c["path"] for c in listing],
    )


def main() -> int:
    print(f"repo: {REPO_DIR}")
    print(f"stage: {STAGE}\n")

    try:
        run()
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        _results.append(("the end-to-end flow raised no exception", False, str(exc)))

    width = max(len(n) for n, _, _ in _results) + 2
    failed = 0
    for name, ok, detail in _results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}")
        if not ok:
            failed += 1
            if detail:
                print(f"         {detail}")

    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
