"""Byte-level regression tests for the case dashboard backend.

Run from the repository root::

    python -m caseDashboard.server.selftest

The dashboard's one non-negotiable promise is that a write touches *only* the
value span it was asked to touch: trailing comments, ``&`` continuations and
CRLF endings must survive.  Most of what follows exists to protect that.

No test framework -- this must run on a stock Windows Python with no pip.
Checks execute at decoration time, so every helper must be defined above them.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Tuple

REPO_DIR = Path(__file__).resolve().parents[2]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from caseDashboard.server import app, derived, reader, writer  # noqa: E402
from caseDashboard.server.profiles import ALL_PARAMS, FILES  # noqa: E402

CASE = REPO_DIR / "tutorial" / "single_sphere"
#: The multisphere case.  It is only ever *read* here -- nothing in this suite
#: writes to ``tutorial/``.
FISH = REPO_DIR / "tutorial" / "multi_sphere_fish"
DEM = "DEM/in.liggghts_run"
CP = "CFD/constant/couplingProperties"

#: The settings the solver defaults, so a case may leave them out (see
#: ``Param.optional``).  Named here because two checks below are about them and
#: writing the list twice would let the two drift apart.
OPTIONAL_CP = (
    "coupling.Coe_V_local",
    "coupling.Coe_V_global",
    "coupling.doDivCor",
    "coupling.Exdrag",
    "coupling.dragcorrcoe",
)

_results: List[Tuple[str, bool, str]] = []


def check(name: str) -> Callable:
    def wrap(fn: Callable[[], None]) -> Callable:
        try:
            fn()
        except AssertionError as exc:
            _results.append((name, False, str(exc)))
        except Exception:  # noqa: BLE001 - a crash is a failure too
            _results.append((name, False, traceback.format_exc(limit=3)))
        else:
            _results.append((name, True, ""))
        return fn

    return wrap


def eq(actual, expected, what: str = "") -> None:
    assert actual == expected, f"{what}: expected {expected!r}, got {actual!r}"


def truthy(value, what: str) -> None:
    assert value, what


def read() -> Tuple[Dict[str, reader.Resolved], Dict[str, reader.FileText]]:
    return reader.read_case(CASE)


def render_all(plan, files) -> Dict[str, str]:
    """``render`` only returns files it changed; fill the rest with the original."""
    rendered = writer.render(files, plan)
    return {rel: rendered.get(rel, ft.text) for rel, ft in files.items()}


def copy_case(tmp: Path) -> Path:
    """Copy only the files the parameter list reads, preserving bytes."""
    dest = tmp / "single_sphere"
    dest.mkdir(parents=True)
    for rel in FILES:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CASE / rel, target)
    return dest


# ---------------------------------------------------------------------------
# schema safety
# ---------------------------------------------------------------------------


@check("no parameter points at system/controlDict.foam")
def _() -> None:
    for p in ALL_PARAMS:
        truthy(
            not p.file.endswith("controlDict.foam"),
            f"{p.id} points at the stale copy {p.file}",
        )


@check("parameter ids are unique")
def _() -> None:
    ids = [p.id for p in ALL_PARAMS]
    dupes = {i for i in ids if ids.count(i) > 1}
    eq(dupes, set(), "duplicate ids")


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------


@check("every editable parameter resolves")
def _() -> None:
    resolved, _files = read()
    bad = [
        (pid, r.status, r.reason)
        for pid, r in resolved.items()
        # A toggle param is resolved whether its line is live or commented out;
        # only "unresolved" means the regex failed to find it.  "unused" is the
        # other mutually exclusive route (``Param.alt``) -- located, just not
        # what this case does -- and "optional" is a setting the solver
        # defaults, which a case is equally free to leave out.
        if not r.param.readonly
        and r.status not in ("ok", "disabled", "unused", "optional")
    ]
    eq(bad, [], "unresolved editable parameters")


@check("a setting the tutorial does write is not quietly optional")
def _() -> None:
    # The failure this guards against is a pattern that stopped matching: the
    # parameter would go on being shown, greyed as "Optional", and a case that
    # does set it would look like one that does not.  So where the line *is*
    # there, the rule has to reach it.
    resolved, _files = read()
    bad = [
        (pid, resolved[pid].status)
        for pid in OPTIONAL_CP
        if not resolved[pid].param.optional or resolved[pid].status != "ok"
    ]
    eq(bad, [], "optional parameters that did not resolve in single_sphere")


@check("an optional setting the case leaves out reads optional, not unresolved")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        path = target / CP
        kept = "".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
            if "Exdrag" not in line
        )
        # Bytes, not text: the file's own line endings are part of what the
        # reader sees.
        path.write_bytes(kept.encode("utf-8"))

        resolved, files = reader.read_case(target)
        r = resolved["coupling.Exdrag"]
        eq(r.status, "optional", "status")
        eq(r.value, None, "value")
        eq(reader.resolved_to_api(r)["editable"], False, "editable")
        # The point of the status: a case that omits it is not a case with a
        # problem to report.
        eq([u["id"] for u in app.recognition(resolved, files)["unrecognized"]], [],
           "an absent optional parameter was reported as unrecognized")
        # And the rest of the block is untouched by its absence.
        eq([resolved[pid].status for pid in OPTIONAL_CP if pid != "coupling.Exdrag"],
           ["ok"] * 4, "the neighbouring optional parameters")

        plan = writer.plan_edits(resolved, files, [writer.Edit("coupling.Exdrag", 1.0)])
        truthy("coupling.Exdrag" in plan.errors,
               "a line the case does not have was accepted for writing")


@check("the scoped alphaMin lands inside IBProps")
def _() -> None:
    resolved, files = read()
    r = resolved["coupling.IBProps.alphaMin"]
    eq(r.status, "ok", "status")
    eq(r.matches, 1, "match count")
    ft = files[r.param.file]
    truthy("alphaMin" in ft.contents[r.line - 1], "the matched line does not contain alphaMin")
    scoped = reader.scope_line_indices(
        ft.contents, re.compile(r.param.scope), r.param.scope_style
    )
    truthy(scoped, "the IBProps block was not located")
    truthy(r.line in scoped, f"line {r.line} is not inside the IBProps block {sorted(scoped)}")


# ---------------------------------------------------------------------------
# byte-level round trip -- the critical guarantee
# ---------------------------------------------------------------------------


@check("a zero-change plan is byte-identical to the original")
def _() -> None:
    resolved, files = read()
    plan = writer.plan_edits(resolved, files, [])
    eq(plan.changed_files, [], "a zero-change plan reported changed files")
    for rel, text in render_all(plan, files).items():
        eq(text.encode("utf-8"), files[rel].raw, f"{rel} differs after a zero-change plan")


@check("writing each value back is byte-identical")
def _() -> None:
    resolved, files = read()
    # Echo every editable param's current value back at itself.  Any regex that
    # over-captures will show up here as a changed byte.  Derived params are left
    # out of the echo -- the writer injects their value itself -- which is how
    # this check also proves the injected edit is a no-op on a consistent file.
    edits = [
        writer.Edit(pid, r.value)
        for pid, r in resolved.items()
        if r.status == "ok" and not r.param.readonly and not r.param.product_of
    ]
    truthy(len(edits) > 50, f"too few parameters took part in the echo: {len(edits)}")
    plan = writer.plan_edits(resolved, files, edits)
    for rel, text in render_all(plan, files).items():
        eq(text.encode("utf-8"), files[rel].raw, f"{rel} differs after echoing its values back")


@check("the multisphere case writes each value back byte-identically")
def _() -> None:
    # The echo above runs on single_sphere, where the whole multisphere route is
    # unused and therefore unwritable -- so it cannot see those rules at all.
    # This one echoes the fish deck's own values back at it, which is what
    # catches a regex over-capturing an ``&`` continuation, a ``${rhop}`` or
    # another token sharing the line.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "multi_sphere_fish"
        (target / "DEM").mkdir(parents=True)
        shutil.copyfile(FISH / DEM, target / DEM)
        resolved, files = reader.read_case(target)
        edits = [
            writer.Edit(pid, r.value)
            for pid, r in resolved.items()
            if r.status == "ok" and not r.param.readonly and not r.param.product_of
        ]
        truthy(len(edits) >= 30, f"too few multisphere parameters took part in the echo: {len(edits)}")
        plan = writer.plan_edits(resolved, files, edits)
        eq(plan.errors, {}, "a multisphere echo was rejected")
        for rel, text in render_all(plan, files).items():
            eq(text.encode("utf-8"), files[rel].raw, f"{rel} differs after echoing its values back")


@check("each transportProperties rule is read from its own phase block")
def _() -> None:
    # ``nu`` and ``rho`` appear once per phase, so the scope is the only thing
    # that says which fluid a value belongs to -- and a rule pinned to the wrong
    # block reads the *other* phase's number, which an echo of the same value
    # back at itself would never notice.
    resolved, files = read()
    for pid, want in (
        ("phys.water.nu", 1e-06),
        ("phys.water.rho", 1000.0),
        ("phys.air.nu", 1.78e-05),
        ("phys.air.rho", 1.2),
    ):
        r = resolved[pid]
        eq(r.status, "ok", f"{pid} status")
        eq(r.value, want, f"{pid} value")
        ft = files[r.param.file]
        scoped = reader.scope_line_indices(
            ft.contents, re.compile(r.param.scope), r.param.scope_style
        )
        truthy(scoped, f"{pid}: the block {r.param.scope!r} was not located")
        # ``Resolved.line`` is 1-based (it is what the panel shows), while
        # ``scope_line_indices`` hands back 0-based indices into the split lines.
        truthy(
            r.line - 1 in scoped,
            f"{pid} landed outside the block {r.param.scope!r}",
        )

    # ``sigma`` is a top-level entry, so what has to hold is the other way round:
    # no scope, and exactly one line in the file carries the keyword.
    sigma = resolved["phys.sigma"]
    eq(sigma.status, "ok", "phys.sigma status")
    eq(sigma.value, 0.07, "phys.sigma value")
    eq(sigma.matches, 1, "phys.sigma match count")
    g = resolved["phys.g"]
    eq(g.value, [0.0, 0.0, -9.81], "phys.g value")


@check("changing sigma rewrites the number and not the dimensions")
def _() -> None:
    # The matched span is the number alone: everything before it -- the repeated
    # keyword and the bracketed dimension set -- has to survive verbatim, or the
    # dictionary comes back with a different dimension attached to the value.
    resolved, files = read()
    rel = "CFD/constant/transportProperties"
    before = files[rel].text.split("\n")
    plan = writer.plan_edits(resolved, files, [writer.Edit("phys.sigma", 0.05)])
    eq(plan.errors, {}, "writing sigma was rejected")
    after = render_all(plan, files)[rel].split("\n")
    eq(len(after), len(before), "the line count changed")
    changed = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    eq(len(changed), 1, f"the number of changed lines is not 1: {[after[i] for i in changed]}")
    eq(after[changed[0]], before[changed[0]].replace("0.07", "0.05"),
       "something other than the value moved")

    # The water/air pair again, this time through the writer: asking for the
    # water value must leave the air line exactly where it was.
    water, air = resolved["phys.water.nu"], resolved["phys.air.nu"]
    plan = writer.plan_edits(resolved, files, [writer.Edit("phys.water.nu", 2e-06)])
    after = render_all(plan, files)[rel].split("\n")
    eq([i for i, (b, a) in enumerate(zip(before, after)) if b != a], [water.line - 1],
       "a write to the water viscosity moved a line other than its own")
    eq(after[air.line - 1], before[air.line - 1], "the air viscosity was rewritten")


@check("a trailing comment and other tokens on the line are untouched")
def _() -> None:
    resolved, files = read()
    rel = "CFD/system/controlDict"
    plan = writer.plan_edits(resolved, files, [writer.Edit("run.writeControl", "clockTime")])
    rendered = render_all(plan, files)[rel]
    truthy("clockTime" in rendered, "the new value was not written")

    before = [l for l in files[rel].text.split("\n") if "writeControl" in l]
    after = [l for l in rendered.split("\n") if "writeControl" in l]
    eq(len(after), len(before), "the number of writeControl lines changed")
    for b, a in zip(before, after):
        tail_b = b.split(";", 1)[1] if ";" in b else ""
        tail_a = a.split(";", 1)[1] if ";" in a else ""
        eq(tail_a.strip(), tail_b.strip(), "what follows the semicolon changed")


@check("changing the diameter leaves density/velocity on the same line alone")
def _() -> None:
    resolved, files = read()
    before = [l for l in files[DEM].text.split("\n") if "diameter" in l and "density" in l]
    truthy(before, "the particle definition line was not found")
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.diameter", 0.02)])
    after = [
        l for l in render_all(plan, files)[DEM].split("\n") if "diameter" in l and "density" in l
    ]
    eq(len(after), len(before), "the number of particle definition lines changed")
    for b, a in zip(before, after):
        eq(a.split("diameter", 1)[0], b.split("diameter", 1)[0], "the diameter prefix changed")
        eq(
            a.split("density", 1)[1],
            b.split("density", 1)[1],
            "what follows density changed",
        )
    truthy(any("0.02" in l for l in after), "the new diameter was not written")


@check("changing the diameter does not disturb the density beside it")
def _() -> None:
    resolved, files = read()
    plan = writer.plan_edits(
        resolved, files, [writer.Edit("dem.diameter", 0.02), writer.Edit("dem.density", 2500)]
    )
    lines = [l for l in render_all(plan, files)[DEM].split("\n") if "diameter" in l and "density" in l]
    truthy(lines, "the particle definition line was not found")
    truthy("0.02" in lines[0] and "2500" in lines[0], f"both values were not written: {lines[0]!r}")


@check("CRLF endings are preserved")
def _() -> None:
    resolved, files = read()
    eq(files[DEM].endings[2], "\r\n", "line 3 is not CRLF")
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.diameter", 0.02)])
    rendered = render_all(plan, files)[DEM]
    eq(rendered.count("\r\n"), files[DEM].text.count("\r\n"), "the CRLF count changed")
    truthy("\n" not in rendered.replace("\r\n", ""), "a bare LF was produced")


@check("the value read back after apply equals the one written")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        resolved, files = reader.read_case(target)
        plan = writer.plan_edits(resolved, files, [writer.Edit("dem.diameter", 0.02)])
        writer.apply_plan(target, files, plan)
        after, _ = reader.read_case(target)
        eq(after["dem.diameter"].value, 0.02, "the diameter read back")


@check("untouched files keep their original bytes after a write")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        resolved, files = reader.read_case(target)
        untouched = target / "CFD/system/blockMeshDict"
        before = untouched.read_bytes()
        plan = writer.plan_edits(resolved, files, [writer.Edit("dem.diameter", 0.02)])
        writer.apply_plan(target, files, plan)
        eq(untouched.read_bytes(), before, "an untouched file was rewritten")


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@check("an out-of-range write is rejected")
def _() -> None:
    resolved, files = read()
    plan = writer.plan_edits(
        resolved, files, [writer.Edit("coupling.IBProps.alphaMin", 5.0)]
    )
    truthy(plan.errors, "alphaMin=5.0 was not rejected")


@check("an unknown parameter id is rejected")
def _() -> None:
    resolved, files = read()
    plan = writer.plan_edits(resolved, files, [writer.Edit("no.such.param", 1)])
    truthy(plan.errors, "an unknown id was not rejected")


@check("disabling/enabling only moves the comment prefix")
def _() -> None:
    # The deck may ship this wall either way, so the check flips whatever is
    # there rather than assuming it starts live.
    resolved, files = read()
    r = resolved["dem.wall.z2"]
    line_no = r.line - 1
    before = files[DEM].text.split("\n")

    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.wall.z2", r.value, not r.enabled)])
    after = render_all(plan, files)[DEM].split("\n")
    eq(len(after), len(before), "the line count changed")
    eq([i for i, (b, a) in enumerate(zip(before, after)) if b != a], [line_no],
       "the number of changed lines is not 1")
    if r.enabled:
        truthy(after[line_no].startswith("#"), f"no comment prefix after disabling: {after[line_no]!r}")
        eq(after[line_no][1:].lstrip(" "), before[line_no], "content beyond the comment prefix changed")
    else:
        truthy(before[line_no].startswith("#"), f"the comment is not at the start of the line: {before[line_no]!r}")
        eq(after[line_no], before[line_no][1:].lstrip(" "), "the line is wrong after enabling")

    # Disabling and a new coordinate in one edit: two spans on the same line, the
    # marker at column 0 and the number further right.
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.wall.z2", 0.9, False)])
    after = render_all(plan, files)[DEM].split("\n")
    eq([i for i, (b, a) in enumerate(zip(before, after)) if b != a], [line_no],
       "the number of changed lines is not 1")
    truthy(after[line_no].startswith("#"), f"no comment prefix after disabling: {after[line_no]!r}")
    truthy(after[line_no].rstrip().endswith("0.9"), f"the new coordinate was not written: {after[line_no]!r}")


@check("a disabled wall stays readable and drops out of the domain comparison")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        resolved, files = reader.read_case(target)
        value = resolved["dem.wall.z2"].value
        plan = writer.plan_edits(resolved, files, [writer.Edit("dem.wall.z2", value, False)])
        writer.apply_plan(target, files, plan)
        off, _ = reader.read_case(target)
        got = off["dem.wall.z2"]
        eq(got.status, "disabled", "status after disabling")
        eq(got.enabled, False, "enabled after disabling")
        eq(got.value, value, "the value should still be readable after disabling")

        # Commented out, the wall is out of the deck, so a deliberately wrong
        # coordinate must not raise a domain warning.
        wrong, files2 = reader.read_case(target)
        plan = writer.plan_edits(wrong, files2, [writer.Edit("dem.wall.z2", 0.9)])
        eq(plan.errors, {}, "a write was rejected while disabled")
        writer.apply_plan(target, files2, plan)
        off2, _ = reader.read_case(target)
        eq(off2["dem.wall.z2"].value, 0.9, "the new value was not written while disabled")
        z = next(c for c in derived.compute_consistency(derived.Ctx(off2)) if c["id"] == "domain.z")
        eq(z["level"], derived.OK, f"the disabled upper wall is still compared: {z['message']}")
        truthy("disabled" in z["message"], f"the disabled wall is not mentioned: {z['message']}")


@check("disable then enable is byte-identical to the original")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        base = (target / DEM).read_bytes()
        start, _ = reader.read_case(target)
        r = start["dem.wall.z2"]
        # Flip, then flip back -- whatever the deck's initial state was.
        for want in (not r.enabled, r.enabled):
            live, live_files = reader.read_case(target)
            plan = writer.plan_edits(
                live, live_files, [writer.Edit("dem.wall.z2", r.value, want)]
            )
            writer.apply_plan(target, live_files, plan)
        eq((target / DEM).read_bytes(), base, "flipping back and forth did not restore the bytes")


@check("a read-only parameter refuses writes")
def _() -> None:
    resolved, files = read()
    # The walls used to be the read-only example here; they are editable now, so
    # the solver name is the one parameter that still must never be written.
    plan = writer.plan_edits(resolved, files, [writer.Edit("run.solverName", "otherSolver")])
    truthy(plan.errors, "a read-only parameter was not rejected")


# ---------------------------------------------------------------------------
# derived (product) params
# ---------------------------------------------------------------------------


@check("changing a decomposition direction syncs the subdomain and process counts")
def _() -> None:
    resolved, files = read()
    rel = "CFD/system/decomposeParDict"
    before = files[rel].text.split("\n")

    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.proz", 6)])
    eq(plan.errors, {}, "writing proz was rejected")
    rendered = render_all(plan, files)
    after = rendered[rel].split("\n")
    eq(len(after), len(before), "the line count changed")

    # Two spans, on two lines: the direction that was asked for, and the count it
    # implies.  Nothing else in the dictionary may move.
    changed = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    eq(len(changed), 2, f"the number of changed lines is not 2: {[after[i] for i in changed]}")
    truthy(all("proz" in after[i] or "numberOfSubdomains" in after[i] for i in changed),
           f"other lines were hit by mistake: {[after[i] for i in changed]}")
    subs = next(after[i] for i in changed if "numberOfSubdomains" in after[i])
    eq(subs.split(";", 1)[0].split()[-1], "6", f"the subdomain count was not synced: {subs!r}")

    # The launch count is the same number under another name, so it has to move
    # in the same plan -- not wait for a second manual edit plus the warning
    # that the two disagree in the meantime.
    script = "parCFDDEMrun.sh"
    was, now = files[script].text.split("\n"), rendered[script].split("\n")
    eq(len(now), len(was), "the launch script line count changed")
    moved = [i for i, (b, a) in enumerate(zip(was, now)) if b != a]
    eq(len(moved), 1, f"the number of launch script changes is not 1: {[now[i] for i in moved]}")
    truthy('nrProcs="6"' in now[moved[0]], f"the launch script was not synced: {now[moved[0]]!r}")


@check("writing the subdomain count by hand is rejected")
def _() -> None:
    resolved, files = read()
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.numberOfSubdomains", 9)])
    truthy(plan.errors, "a manual write of the subdomain count was not rejected")
    rendered = render_all(plan, files)["CFD/system/decomposeParDict"]
    written = rendered.split("numberOfSubdomains", 1)[1].split(";", 1)[0].strip()
    eq(written, "4", "a rejected value still landed on disk")


@check("consistent directions produce no write")
def _() -> None:
    # The whole point of deriving it: a file that already agrees with itself
    # stays byte-identical, so the dashboard never rewrites the deck to say the
    # same thing.
    resolved, files = read()
    plan = writer.plan_edits(resolved, files, [])
    eq(plan.changed_files, [], "a consistent case was rewritten")
    eq(plan.is_noop, True, "is_noop")


@check("the subdomain count is the product of the three directions")
def _() -> None:
    resolved, _files = read()
    # The deck ships 1×1×4, so a pending proy=3 has to read as 12 straight away --
    # before the debounced derive, and long before anything is written.
    ctx = derived.Ctx(resolved, [{"id": "mesh.proy", "value": 3}])
    eq(ctx.integer("mesh.numberOfSubdomains"), 12, "it did not follow the direction change")
    d = derived.compute(resolved, [{"id": "mesh.proz", "value": 8}])
    metrics = {m["id"]: m for m in d["metrics"]}
    truthy("8" in str(metrics["parallel.subdomains"]["value"]), metrics["parallel.subdomains"])


# ---------------------------------------------------------------------------
# derived metrics
# ---------------------------------------------------------------------------


@check("derived metrics match the documented reference values")
def _() -> None:
    resolved, _files = read()
    m = {x["id"]: x for x in derived.compute(resolved, [])["metrics"]}

    def close(mid: str, want: float, tol: float = 5e-3) -> None:
        truthy(mid in m, f"missing metric {mid}")
        # Some metrics report a pre-formatted string (e.g. "7.51" or
        # "4 (DEM 1×1×4, nrProcs 4)"); the leading number is the value.
        text = str(m[mid]["value"])
        found = re.match(r"\s*(-?[0-9.]+(?:[eE][-+]?[0-9]+)?)", text)
        truthy(found, f"{mid}: cannot parse a number out of {text!r}")
        got = float(found.group(1))
        truthy(
            abs(got - want) <= tol * max(1.0, abs(want)),
            f"{mid}: expected ≈{want}, got {got} ({text!r})",
        )

    # These three describe the single_sphere mesh, so they move whenever its
    # blockMeshDict does (45x45x90 over a 0.1 m cube at the time of writing).
    close("mesh.ncells", 250000, 1e-9)
    # The merged card reports "Δx × Δy × Δz"; the leading number is Δx.
    close("mesh.delta", 2.0, 5e-3)         # mm
    close("mesh.cells_per_diameter", 8.35, 0.02)
    close("coupling.steps_per_period", 5, 1e-9)
    close("run.cfd_steps", 1500, 1e-9)
    close("run.frames", 30, 1e-9)
    close("parallel.subdomains", 4, 1e-9)


@check("changing the coupling interval moves couple_every with it")
def _() -> None:
    # ``couple_every`` is ``couplingInterval`` under the DEM deck's own name and
    # the two files have to agree, so the CFD side is the only copy that is
    # typed into.  The check that used to police the pair went with the freedom
    # to disagree; what has to hold now is that one edit moves both files.
    resolved, files = read()
    rel = "DEM/in.liggghts_run"
    before = files[rel].text.split("\n")

    plan = writer.plan_edits(resolved, files, [writer.Edit("coupling.couplingInterval", 250)])
    eq(plan.errors, {}, "writing the coupling interval was rejected")
    after = render_all(plan, files)[rel].split("\n")
    eq(len(after), len(before), "the line count changed")

    # One span, on the one line: the interval implies exactly this line.
    changed = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    eq(len(changed), 1, f"the number of changed lines is not 1: {[after[i] for i in changed]}")
    truthy(
        "couple_every 250" in after[changed[0]],
        f"the DEM deck was not synced: {after[changed[0]]!r}",
    )


@check("writing couple_every by hand is rejected")
def _() -> None:
    resolved, files = read()
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.couple_every", 200)])
    truthy(plan.errors, "a manual write of couple_every was not rejected")
    rendered = render_all(plan, files)["DEM/in.liggghts_run"]
    written = rendered.split("couple_every", 1)[1].split("\n", 1)[0].split()[0]
    eq(written, "100", "a rejected value still landed on disk")


@check("an unchanged coupling interval leaves the DEM deck alone")
def _() -> None:
    # The point of deriving it: a deck that already carries the right number is
    # not rewritten to tell it what it already says.
    resolved, files = read()
    plan = writer.plan_edits(resolved, files, [writer.Edit("coupling.couplingInterval", 100)])
    eq(plan.changed_files, [], "the DEM deck was rewritten to the same value")


@check("the default configuration has no errors")
def _() -> None:
    resolved, _files = read()
    d = derived.compute(resolved, [])
    eq(d["summary"]["errors"], 0, "the default configuration has an error")


@check("a derived triple names one source per component")
def _() -> None:
    # The shape rule `product_of` turns on: a scalar takes the product of any
    # number of sources, a triple takes exactly three, one per component.  A
    # triple with two or four sources has no meaning, and the writer and the
    # derive pass both silently skip it -- so it would be a rule that simply
    # never fires rather than a visible mistake.
    for p in ALL_PARAMS:
        if p.product_of and p.is_triple:
            eq(len(p.product_of), 3, f"{p.id}: a vector is not a product")


@check("changing a decomposition direction moves the DEM processor grid with it")
def _() -> None:
    # The DEM grid used to be the one copy of the parallel layout that had to be
    # kept in step by hand, and the check that policed it is gone with that
    # freedom.  What has to hold now is that one edit in decomposeParDict moves
    # it -- axis by axis, since CFDEM pairs rank i with subdomain i.
    resolved, files = read()
    rel = "DEM/in.liggghts_run"
    before = files[rel].text.split("\n")

    # x, and the deck says 1 1 4: a component-by-component copy lands on 2 1 4,
    # where anything that merely multiplied the directions out would have put the
    # total in every slot it could fill.  That is the whole point of the rule.
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.prox", 2)])
    eq(plan.errors, {}, "writing a decomposition direction was rejected")
    after = render_all(plan, files)[rel].split("\n")
    eq(len(after), len(before), "the line count changed")

    changed = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    eq(len(changed), 1, f"the number of changed lines is not 1: {[after[i] for i in changed]}")
    eq(after[changed[0]].split(), ["processors", "2", "1", "4"], after[changed[0]])


@check("writing the DEM processor grid by hand is rejected")
def _() -> None:
    resolved, files = read()
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.processors", [1, 1, 8])])
    truthy(plan.errors, "a manual write of the DEM processor grid was not rejected")
    rendered = render_all(plan, files)["DEM/in.liggghts_run"]
    line = next(l for l in rendered.split("\n") if l.strip().startswith("processors"))
    eq(line.split(), ["processors", "1", "1", "4"], "a rejected value still landed on disk")


@check("changing the domain size reports a cross-file mismatch")
def _() -> None:
    resolved, _files = read()
    d = derived.compute(resolved, [{"id": "mesh.xco2", "value": 0.2}])
    bad = [c for c in d["consistency"] if c["level"] in ("warn", "error")]
    truthy(bad, "the domain size change triggered no warning")


# ---------------------------------------------------------------------------
# the folder browser and the no-process rule
# ---------------------------------------------------------------------------


@check("nothing under server/ starts a process")
def _() -> None:
    # The dashboard's contract is that it reads and writes dictionaries and does
    # nothing else.  The OS folder dialog used to be a deliberate, narrow
    # exception to that; the folder browser is served out of the same handler as
    # every other endpoint, so there is no exception left and this can be
    # absolute.  A read-only WSL health probe once grew a subprocess here and had
    # to be deleted -- this is what would catch it coming back.
    launch = re.compile(
        r"\b(subprocess\.|os\.system|os\.popen|Popen\(|os\.startfile|ShellExecute)"
    )
    # The tests are not the server -- and this very check contains the pattern it
    # searches for, so it has to exempt itself.
    exempt = {"selftest.py", "e2e.py"}
    offenders = [
        path.name
        for path in sorted((REPO_DIR / "caseDashboard" / "server").glob("*.py"))
        if path.name not in exempt and launch.search(path.read_text(encoding="utf-8"))
    ]
    truthy(not offenders, f"these files start a process too: {offenders}")


@check("the folder browser lists subfolders and flags the cases among them")
def _() -> None:
    listing = app.browse_dir("tutorial")
    eq(listing["path"], "tutorial", "wrong path echoed back")
    eq(listing["parent"], "", "the parent of tutorial should be the repository root")
    truthy(not listing["is_case"], "tutorial holds cases but is not one")
    flagged = {e["name"]: e["is_case"] for e in listing["entries"]}
    truthy(flagged.get("single_sphere"), "single_sphere was not flagged as a case")
    truthy(flagged.get("multi_sphere_fish"), "multi_sphere_fish was not flagged as a case")

    # The repository root is where browsing starts, but it is not a ceiling: its
    # parent is an ordinary directory outside.  `parent` is None only at a
    # filesystem root, and that is the one place the browser disables "up".
    root = app.browse_dir("")
    eq(root["path"], "", "the root should report an empty relative path")
    eq(root["parent"], app.path_id(REPO_DIR.parent), "the root's parent is the directory above it")
    truthy(not root["is_case"], "the repository root must never be selectable")
    truthy(
        all(not e["name"].startswith(".") for e in root["entries"]),
        "a dot-directory leaked into the listing",
    )

    # Files are not browsable targets and a directory that does not exist is not
    # an answer either; both have to come back as errors rather than empty lists.
    for raw in ("README.md", "nope"):
        try:
            app.browse_dir(raw)
        except app.ApiError as exc:
            eq(exc.status, 404, f"{raw} should have been refused with 404")
        else:
            raise AssertionError(f"{raw} should have been refused")


@check("a case outside the repository opens, and the browser can walk out to it")
def _() -> None:
    # A case is a directory holding a controlDict.  Nothing about that says it was
    # cloned next to this dashboard, so the repository is not a boundary any more
    # -- but it is still where browsing starts and where the trail anchors, which
    # is what `inside_repo` and `crumbs` are for.
    above = app.browse_dir("..")
    eq(above["inside_repo"], False, "a directory above the repository counts as inside it")
    eq(above["crumbs"][-1]["path"], above["path"], "the trail should end where it is")
    truthy(
        above["crumbs"][0]["path"].endswith("/"),
        f"outside the repository the trail should start at a filesystem root: {above['crumbs']}",
    )

    root = app.browse_dir("")
    eq(root["inside_repo"], True, "the repository root is inside the repository")
    eq(root["crumbs"][0]["path"], "", "the trail starts at the repository itself")
    eq(
        [c["path"] for c in app.browse_dir("tutorial")["crumbs"]],
        ["", "tutorial"],
        "a trail inside the repository should be repository-relative throughout",
    )

    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp) / "run_elsewhere"
        (outside / "CFD" / "system").mkdir(parents=True)
        (outside / "CFD" / "system" / "controlDict").write_text("", encoding="utf-8")

        resolved = app.resolve_case(str(outside))
        eq(resolved, outside.resolve(), "a case outside the repository was not resolved")
        # Named absolutely, because there is no relative name to give it -- and
        # the same spelling has to survive the round trip back in.
        eq(
            app.path_id(resolved),
            str(outside.resolve()).replace("\\", "/"),
            "an outside case should be named by its absolute path",
        )
        eq(
            [e["is_case"] for e in app.browse_dir(str(outside.parent))["entries"]],
            [True],
            "the browser did not offer the outside case",
        )

    # The one rule that is left still bites, and the empty string is not a path.
    with tempfile.TemporaryDirectory() as tmp:
        try:
            app.resolve_case(tmp)
        except app.ApiError as exc:
            eq(exc.status, 400, "a directory without a controlDict should be rejected")
        else:
            raise AssertionError("a directory without a controlDict should be refused")


@check("opening and saving unchanged in the panel does not alter bytes")
def _() -> None:
    # The editor is the one write path that does not splice a known span, so its
    # guarantee is a different one: it must not reformat.  A CRLF dictionary goes
    # through a textarea, which only speaks LF, so the line endings have to come
    # back from the file rather than from the text.
    for rel in ("CFD/system/controlDict", "DEM/in.liggghts_run"):
        raw = (CASE / rel).read_bytes()
        opened = app.file_payload(rel, raw)
        eq(opened["text"].count("\r"), 0, f"{rel} left a CR in the text handed to the editor")
        eq(app.encode_like(opened["text"], raw), raw, f"{rel} saving unchanged altered the bytes")
        added = app.encode_like(opened["text"] + "\nnew line\n", raw)
        truthy(
            added.endswith(b"\r\n" if opened["eol"] == "crlf" else b"\n"),
            f"{rel} an added line did not follow the file's ending convention",
        )


# ---------------------------------------------------------------------------


def main() -> int:
    print(f"repo: {REPO_DIR}")
    print(f"case: {CASE}\n")

    width = max(len(name) for name, _, _ in _results) + 2
    failed = 0
    for name, ok, detail in _results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}")
        if not ok:
            failed += 1
            for line in detail.strip().splitlines():
                print(f"         {line}")

    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
