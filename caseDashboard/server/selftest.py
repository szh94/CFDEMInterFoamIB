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

from caseDashboard.server import app, derived, reader, steps, writer  # noqa: E402
from caseDashboard.server.profiles import ALL_PARAMS, FILES  # noqa: E402

CASE = REPO_DIR / "tutorial" / "two_phase_sphere_settling"
#: The multisphere case.  It is only ever *read* here -- nothing in this suite
#: writes to ``tutorial/``.
FISH = REPO_DIR / "tutorial" / "multi_sphere_fish"
#: The one case with *two* particles in the zone, so the one that exercises a
#: table row spread over three lines.  Read-only, like ``FISH``.
TWO_SPHERE = REPO_DIR / "tutorial" / "single_phase_2_sphere_falling_Re100"
DEM = "DEM/in.liggghts_run"
CP = "CFD/constant/couplingProperties"
SF = "CFD/system/setFieldsDict"
TP = "CFD/constant/transportProperties"
BM = "CFD/system/blockMeshDict"

#: The water box's lower corner.  It has no key of its own -- it is the three
#: literals in ``box (x y z) ($xmax $ymax $zmax)`` -- so it is the one part of
#: the file the key-anchored rules cannot reach, and the one worth watching.
BOX_LOWER = ("mesh.sf.xmin", "mesh.sf.ymin", "mesh.sf.zmin")

#: The settings the solver defaults, so a case may leave them out (see
#: ``Param.optional``).  Named here because two checks below are about them and
#: writing the list twice would let the two drift apart.
OPTIONAL_CP = (
    "coupling.Coe_V_local",
    "coupling.Coe_V_global",
    "coupling.doDivCor",
    "coupling.voidExp",
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
    dest = tmp / "two_phase_sphere_settling"
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


@check("a grouped parameter names real partners of its own file")
def _() -> None:
    # `partners` is display-only: the panel folds the named params into this
    # one's row and skips them on their own.  Nothing about writing breaks if a
    # name is wrong, which is exactly the risk -- a typo silently stops the
    # grouping and just leaves extra rows on screen.  So the structure is
    # checked here: every name resolves, owner and partners live in the same
    # card (a row cannot span two), the parts agree on being switchable -- a
    # toggle row carries one Off/On control per box, so a mixed row would show a
    # control for one box and nothing for the other -- no partner declares a
    # group of its own (a chain would have the middle param claimed twice and
    # rendered nowhere) and no param is claimed by two rows, which would show one
    # box twice and hide the other owner's row behind it.
    by_id = {p.id: p for p in ALL_PARAMS}
    owners: Dict[str, str] = {}
    for p in ALL_PARAMS:
        if not p.partners:
            continue
        eq(p.is_triple, False, f"{p.id}: a triple is already three boxes")
        for name in p.partners:
            q = by_id.get(name)
            truthy(q is not None, f"{p.id}: partner {name!r} is not a parameter")
            eq(q.group, p.group, f"{p.id}: partner {q.id} is in another group")
            eq(q.file, p.file, f"{p.id}: partner {q.id} is in another file")
            eq(q.toggle, p.toggle, f"{p.id}: partner {q.id} does not agree on being switchable")
            truthy(not q.partners, f"{p.id}: partner {q.id} is itself grouped")
            truthy(
                name not in owners,
                f"{name} is claimed by both {owners.get(name)} and {p.id}",
            )
            owners[name] = p.id


@check("a compact row is a triple")
def _() -> None:
    # `compact` says "fit these three boxes in one column", so it means nothing
    # on a param that has no three boxes -- but costs nothing at write time
    # either, which is exactly why a stray one would go unnoticed.
    for p in ALL_PARAMS:
        if p.compact:
            truthy(p.is_triple, f"{p.id}: compact, but it is not a triple")


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
        # defaults, which a case is equally free to leave out.  "create" and
        # "inactive" are the model-owned coefficients (``Param.owner``): this
        # case runs both phases Newtonian, so it has no coefficient block at
        # all -- the ones belonging to the models it is not running are simply
        # not part of the case, and are created the moment one is picked.
        if not r.param.readonly
        and r.status not in ("ok", "disabled", "unused", "optional", "create", "inactive")
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
    eq(bad, [], "optional parameters that did not resolve in two_phase_sphere_settling")


@check("an optional setting the case leaves out reads optional, not unresolved")
def _() -> None:
    absent = "coupling.voidExp"
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        path = target / CP
        kept = "".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
            if "voidExp" not in line
        )
        # Bytes, not text: the file's own line endings are part of what the
        # reader sees.
        path.write_bytes(kept.encode("utf-8"))

        resolved, files = reader.read_case(target)
        r = resolved[absent]
        eq(r.status, "optional", "status")
        eq(r.value, None, "value")
        eq(reader.resolved_to_api(r)["editable"], False, "editable")
        # The point of the status: a case that omits it is not a case with a
        # problem to report.
        eq([u["id"] for u in app.recognition(resolved, files)["unrecognized"]], [],
           "an absent optional parameter was reported as unrecognized")
        # And the rest of the block is untouched by its absence.  The count comes
        # off OPTIONAL_CP rather than being written out, for the reason that
        # list's own comment gives.
        eq([resolved[pid].status for pid in OPTIONAL_CP if pid != absent],
           ["ok"] * (len(OPTIONAL_CP) - 1), "the neighbouring optional parameters")

        plan = writer.plan_edits(resolved, files, [writer.Edit(absent, 2.0)])
        truthy(absent in plan.errors,
               "a line the case does not have was accepted for writing")


@check("the water box's lower corner is found where it is written as literals")
def _() -> None:
    # `box (x y z) ($xmax $ymax $zmax)` names the *upper* corner through macros
    # the three `*max` rules own; the lower one is three bare numbers with no key
    # of their own, so these rules anchor on the `box (` head instead.  What that
    # must not cost is precision: each rule has to span its own number and no
    # other, so that editing one component leaves the other two alone.
    resolved, files = read()
    line = resolved["mesh.sf.xmin"].line
    eq([resolved[pid].status for pid in BOX_LOWER], ["ok"] * 3, "status")
    eq([resolved[pid].line for pid in BOX_LOWER], [line] * 3, "line")
    spans = [resolved[pid].spans[0] for pid in BOX_LOWER]
    eq(len({(s.col_start, s.col_end) for s in spans}), 3, "distinct spans")
    outer = files[SF].contents[line - 1]
    eq([outer[s.col_start:s.col_end] for s in spans], ["0.0"] * 3,
       "the text each rule would replace")

    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.sf.ymin", 0.03)])
        eq(plan.errors, {}, "plan errors")
        writer.apply_plan(target, files, plan)
        after = (target / SF).read_bytes().decode("utf-8")
        eq(after, files[SF].text.replace(outer, outer.replace("0.0 0.0 0.0", "0.0 0.03 0.0", 1)),
           "one component moved and the other two, plus the macro corner, did not")


@check("the vertex table reads as the eight corners with their macros resolved")
def _() -> None:
    # `vertices` is the one rule that is a *table* rather than a value (see
    # `Param.repeats`): every line the pattern matches inside the parenthesised
    # scope is a row, so the "exactly one match" rail is the wrong shape here --
    # the count is the answer.  Each component is normally a `$macro`, resolved
    # through the definitions at the top of the same file, which is what makes
    # the boxes show the coordinates the mesh will really be built with.
    resolved, _files = read()
    r = resolved["mesh.vertices"]
    eq(r.status, "ok", "status")
    eq(r.matches, 8, "row count")
    eq(r.line, r.rows[0].line, "the reported line is the first vertex")
    eq(
        r.value,
        [
            [0.0, 0.0, 0.0],
            [0.0, 0.1, 0.0],
            [0.0, 0.0, 0.2],
            [0.0, 0.1, 0.2],
            [0.1, 0.0, 0.0],
            [0.1, 0.1, 0.0],
            [0.1, 0.0, 0.2],
            [0.1, 0.1, 0.2],
        ],
        "the corner coordinates",
    )
    # The scope has to have kept the reader inside `vertices (...)`; the file
    # has three more parenthesised lists after it (`blocks` in particular is a
    # line that looks a lot like a vertex).
    truthy(
        all(row.line - 1 in r.scopes[-1].body for row in r.rows),
        "a row came from outside the vertices block",
    )
    for row in r.rows:
        eq(len({(s.col_start, s.col_end) for s in row.spans}), 3, f"line {row.line}: spans")
    # Which parameter each macro belongs to.  This is the link the panel uses to
    # carry an edit of the domain extent into the boxes that mention it, so a
    # rule that is renamed without this following it would show up here.
    eq(
        [row.sources for row in r.rows],
        [
            ["mesh.xco1", "mesh.yco1", "mesh.zco1"],
            ["mesh.xco1", "mesh.yco2", "mesh.zco1"],
            ["mesh.xco1", "mesh.yco1", "mesh.zco2"],
            ["mesh.xco1", "mesh.yco2", "mesh.zco2"],
            ["mesh.xco2", "mesh.yco1", "mesh.zco1"],
            ["mesh.xco2", "mesh.yco2", "mesh.zco1"],
            ["mesh.xco2", "mesh.yco1", "mesh.zco2"],
            ["mesh.xco2", "mesh.yco2", "mesh.zco2"],
        ],
        "the macro each component came from",
    )


@check("an optional setting with a definite absent value reads as that value")
def _() -> None:
    # The mirror of the check above.  Some absent optional settings are not
    # "unknown" but "the default" -- a water box with no lower corner written
    # down starts at the origin -- so the panel has a number to show and the
    # metrics have one to compute with.  It stays unwritable either way: the
    # absence is what the file says, and there is no line to replace.
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        path = target / SF
        kept = "".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
            if not line.lstrip().startswith("box (")
        )
        path.write_bytes(kept.encode("utf-8"))

        resolved, files = reader.read_case(target)
        for pid in BOX_LOWER:
            r = resolved[pid]
            truthy(r.param.default_when_absent, f"{pid} does not declare an absent value")
            eq(r.status, "optional", f"{pid} status")
            eq(r.value, 0.0, f"{pid} value")
            eq(reader.resolved_to_api(r)["editable"], False, f"{pid} editable")
        eq([u["id"] for u in app.recognition(resolved, files)["unrecognized"]], [],
           "an absent optional parameter was reported as unrecognized")

        depth = [
            m for m in derived.compute_metrics(derived.Ctx(resolved))
            if m["id"] == "mesh.water_depth"
        ]
        eq(len(depth), 1, "the water-depth metric was dropped along with the line")
        eq(depth[0]["value"], resolved["mesh.sf.zmax"].value, "depth = zmax - <absent zmin=0>")


@check("a water box reaching outside the domain is not an error")
def _() -> None:
    # Deliberately unchecked.  `zmax` above `zco2` is how a case starts full of
    # water and `zmin` below `zco1` is the mirror of that, so a bound outside the
    # mesh is a choice, not a mistake.  Only the x/y coverage checks remain, and
    # those are about a *short* box leaving a dry corner.  Pinning the exact list
    # is the point: a re-added bounds check changes it.
    resolved, _files = read()
    ctx = derived.Ctx(resolved, [
        {"id": "mesh.sf.zmax", "value": 2.0},
        {"id": "mesh.sf.zmin", "value": -1.0},
    ])
    ids = [c["id"] for c in derived.compute_consistency(ctx)
           if c["id"].startswith("setfields.")]
    eq(ids, ["setfields.cover.x", "setfields.cover.y"], "setfields checks")


@check("the scoped alphaMin lands inside IBProps")
def _() -> None:
    resolved, files = read()
    r = resolved["coupling.IBProps.alphaMin"]
    eq(r.status, "ok", "status")
    eq(r.matches, 1, "match count")
    ft = files[r.param.file]
    truthy("alphaMin" in ft.contents[r.line - 1], "the matched line does not contain alphaMin")
    truthy(r.scopes, "the IBProps block was not located")
    truthy(
        r.line - 1 in r.scopes[-1].body,
        f"line {r.line} is not inside the IBProps block {r.scopes[-1].body}",
    )


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


@check("changing one vertex box writes one number and leaves the macros alone")
def _() -> None:
    # The whole point of reading the macros through: a box shows `0`, but the
    # file says `$xco1`.  The two other components of the row are `$macro`s as
    # well, and the row after it is nothing but macros -- so the only legal
    # write is the one token that was touched.  Rewriting the neighbours as the
    # numbers they resolve to would be this panel editing six tokens to change
    # one, and it would silently freeze the vertex to a domain that has since
    # moved.
    resolved, files = read()
    rows = [list(row) for row in resolved["mesh.vertices"].value]
    rows[0][0] = 0.05
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.vertices", rows)])
    eq(plan.errors, {}, "the vertex edit was rejected")
    rendered = render_all(plan, files)[BM]
    eq(
        rendered,
        files[BM].text.replace("($xco1 $yco1 $zco1)", "(0.05 $yco1 $zco1)", 1),
        "the one token did not change, or something else did",
    )
    eq(rendered.count("\r\n"), files[BM].text.count("\r\n"), "the CRLF count changed")


@check("a vertex added at the end becomes one line, spelled like the ones above it")
def _() -> None:
    # The two controls at the end of the fold-out are the only edits that are
    # not a rewrite of a span: a ninth corner is a line the file does not have,
    # and it has to look like the eight it joins -- the same indent, the same
    # `//<n>` tail, and the file's own line ending rather than the writer's.
    resolved, files = read()
    rows = [list(row) for row in resolved["mesh.vertices"].value] + [[0.0, 0.0, 0.0]]
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.vertices", rows)])
    eq(plan.errors, {}, "appending a vertex was rejected")
    rendered = render_all(plan, files)[BM]
    eq(
        rendered,
        files[BM].text.replace(
            "    ($xco2 $yco2 $zco2) //7\r\n",
            "    ($xco2 $yco2 $zco2) //7\r\n    (0 0 0) //8\r\n",
            1,
        ),
        "the appended line is not what a ninth corner should look like",
    )


@check("the last vertex can be taken off the end of the table")
def _() -> None:
    resolved, files = read()
    rows = [list(row) for row in resolved["mesh.vertices"].value][:-1]
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.vertices", rows)])
    eq(plan.errors, {}, "removing the last vertex was rejected")
    rendered = render_all(plan, files)[BM]
    eq(
        rendered,
        files[BM].text.replace("    ($xco2 $yco2 $zco2) //7\r\n", "", 1),
        "the corner's line was not dropped whole",
    )


@check("writing the vertex table back unchanged is a no-write")
def _() -> None:
    # Every component of the table is compared against the number the row
    # resolved to, not against the token the file spells.  That is what makes
    # the echo -- which is the whole table, macros and all -- a no-op rather
    # than a rewrite of all eight rows into literals.
    resolved, files = read()
    plan = writer.plan_edits(
        resolved, files, [writer.Edit("mesh.vertices", resolved["mesh.vertices"].value)]
    )
    eq(plan.changed_files, [], "echoing the vertex table back changed a file")
    eq(plan.files[BM].skipped, ["mesh.vertices"], "the vertex table was not skipped")


@check("the block list reads as the block type, corners, divisions and grading")
def _() -> None:
    # `blocks` is the second table of blockMeshDict and the one that says how
    # the mesh is *divided* -- which is what the cell-size and cells/diameter
    # metrics are built from.  The corner numbers should go in and out exactly
    # as the file spells them, double spaces included.
    #
    # The grading is two cells, not one: the descriptor is an `enum` the panel
    # offers as a choice and its arguments are free text beside it.  Splitting
    # them is what keeps `(1 1 1)` editable while the keyword is picked from a
    # list -- and the split has to land between the word and its bracket, not
    # inside the word.
    #
    # The case has one block, but the rule is a table like `vertices` -- the
    # count is the answer, not an ambiguity -- and the row has its own five
    # columns rather than a triple's three.
    resolved, _files = read()
    r = resolved["mesh.blocks"]
    eq(r.status, "ok", "status")
    eq(r.matches, 1, "row count")
    eq(
        r.value,
        [["hex", "0  4  5  1  2  6  7  3", "50 50 100", "simpleGrading", "(1 1 1)"]],
        "the block's five cells",
    )
    eq(
        [c.vtype for c in r.param.columns],
        ["text", "text", "text", "enum", "text"],
        "the column types",
    )
    eq(
        list(r.param.columns[3].options or ()),
        ["simpleGrading", "edgeGrading"],
        "the grading descriptors the panel offers",
    )
    # The scope has to have kept the reader inside `blocks (...)`; `edges` and
    # `patches` hold lines that look like a block at a glance.
    truthy(
        r.rows[0].line - 1 in r.scopes[-1].body,
        "the row came from outside the blocks block",
    )


@check("writing the block list back unchanged is a no-write")
def _() -> None:
    resolved, files = read()
    plan = writer.plan_edits(
        resolved, files, [writer.Edit("mesh.blocks", resolved["mesh.blocks"].value)]
    )
    eq(plan.changed_files, [], "echoing the block list back changed a file")
    eq(plan.files[BM].skipped, ["mesh.blocks"], "the block list was not skipped")


@check("changing one division count rewrites that cell and leaves the row its width")
def _() -> None:
    # The three counts live in one cell, so an edit is a whole-string
    # replacement -- `50 50 100` -> `60 50 100` -- and nothing else on the line
    # moves: not the corners, not the grading, not the row count.
    resolved, files = read()
    rows = [list(row) for row in resolved["mesh.blocks"].value]
    rows[0][2] = "60 50 100"
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.blocks", rows)])
    eq(plan.errors, {}, "the division edit was rejected")
    rendered = render_all(plan, files)[BM]
    eq(
        rendered,
        files[BM].text.replace("(50 50 100) simpleGrading", "(60 50 100) simpleGrading", 1),
        "the one cell did not change, or something else did",
    )
    eq(len(rendered.split("\n")), len(files[BM].text.split("\n")), "the line count changed")


@check("a block added at the end becomes one line inside the list")
def _() -> None:
    # A second block is a line the file does not have, and it joins the list
    # *before* `);` -- not after it.  It is spelled like the block above it: the
    # template is the file's own last block line, with only the declared cells
    # swapped, so the indent, the spacing and the line ending come from the file
    # rather than from the writer.
    resolved, files = read()
    aside = resolved["mesh.blocks"].param
    rows = [list(row) for row in resolved["mesh.blocks"].value] + [list(aside.row_seed)]
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.blocks", rows)])
    eq(plan.errors, {}, "appending a block was rejected")
    rendered = render_all(plan, files)[BM]
    eq(
        rendered,
        files[BM].text.replace(
            "    hex ( 0  4  5  1  2  6  7  3 ) (50 50 100) simpleGrading (1 1 1)\r\n);\r\n",
            "    hex ( 0  4  5  1  2  6  7  3 ) (50 50 100) simpleGrading (1 1 1)\r\n"
            "    hex ( 0  4  5  1  2  6  7  3 ) (1 1 1) simpleGrading (1 1 1)\r\n"
            ");\r\n",
            1,
        ),
        "the appended block is not what a second block should look like",
    )


@check("the last block can be taken off the end of the list")
def _() -> None:
    resolved, files = read()
    rows = [list(row) for row in resolved["mesh.blocks"].value][:-1]
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.blocks", rows)])
    eq(plan.errors, {}, "removing the last block was rejected")
    rendered = render_all(plan, files)[BM]
    eq(
        rendered,
        files[BM].text.replace(
            "    hex ( 0  4  5  1  2  6  7  3 ) (50 50 100) simpleGrading (1 1 1)\r\n", "", 1
        ),
        "the block's line was not dropped whole",
    )


@check("the patch table reads one row per patch header")
def _() -> None:
    # A patch is a header line -- the type and the name -- and then a
    # parenthesised block of faces.  The header is one table here and the faces
    # another: a patch holds one face or twenty, and a table row is a line, so
    # the faces cannot ride along with the header they belong to.
    resolved, _files = read()
    r = resolved["mesh.patches"]
    eq(r.status, "ok", "status")
    eq(
        [row.values for row in r.rows],
        [["wall", "x1"], ["wall", "walls"], ["wall", "z2"], ["wall", "x2"]],
        "the patches, by type and name",
    )
    eq(
        list(r.param.columns[0].options or ()),
        ["patch", "wall", "empty", "symmetryPlane", "symmetry", "cyclic", "wedge",
         "processor"],
        "the patch types the panel offers",
    )
    # The rows are edited where they are: a header cannot be added or dropped
    # without the block of faces under it, so the panel is offered no controls
    # for either (see `Param.row_append`).
    eq(r.param.row_append, False, "the patch table must not offer Add/Remove")
    # A type and a name is a short row, so three of them share a line and the
    # name's box is ten characters (see `Param.row_per_line`, `Column.width`).
    eq(r.param.row_per_line, 3, "the patch rows are not packed")
    eq(
        reader.resolved_to_api(r)["columns"][1]["width"],
        "calc(10ch + 1.25rem)",
        "the patch name box is not ten characters",
    )


@check("a face row carries the patch it sits under, which it does not spell itself")
def _() -> None:
    # The face line says its four corner numbers and nothing else; which patch
    # it faces is written once, above it.  The cell is therefore *inherited*
    # (`Column.context`) rather than captured off the line -- and it has to
    # follow the file's own order, so that the three faces of `walls` all take
    # `walls` and not the `x1` above them.
    resolved, _files = read()
    r = resolved["mesh.faces"]
    eq(r.status, "ok", "status")
    eq(
        [row.values for row in r.rows],
        [
            ["x1", "0 2 3 1"],
            ["walls", "0 4 6 2"],
            ["walls", "3 7 5 1"],
            ["walls", "0 1 5 4"],
            ["z2", "2 6 7 3"],
            ["x2", "4 5 7 6"],
        ],
        "the faces, each under its own patch",
    )
    # Both boxes are declared fixed, which is what lines the two columns up
    # down the table: a patch name is short, and a run of corner numbers is
    # short, so neither wants a box that grows with what it holds.
    eq(
        [reader.resolved_to_api(r)["columns"][j]["width"] for j in range(2)],
        ["6rem", "6rem"],
        "the face boxes are not fixed",
    )
    eq(r.param.row_per_line, 3, "the face rows are not packed")
    # The inherited cell is a reading, not a setting: it must not be written
    # back onto the header line it came from.
    rows = [list(row) for row in r.value]
    rows[1][0] = "not-a-patch"
    _, files = read()
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.faces", rows)])
    eq(plan.errors, {}, "the face edit was rejected")
    eq(render_all(plan, files)[BM], files[BM].text, "an inherited cell was written back")


@check("renaming a patch changes its header and nothing else")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        resolved, files = reader.read_case(target)
        rows = [list(row) for row in resolved["mesh.patches"].value]
        rows[0][1] = "inlet"
        plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.patches", rows)])
        eq(plan.errors, {}, "the rename was rejected")
        rendered = render_all(plan, files)[BM]
        eq(
            rendered,
            # The trailing space the header has after its name is outside the
            # captured span, so it survives -- only the name itself moves.
            files[BM].text.replace("    wall x1 \r\n", "    wall inlet \r\n", 1),
            "the one name did not change, or something else did",
        )
        # The faces under it follow without a byte moving: the name they show
        # is read off the header, so the two tables cannot drift apart.
        writer.apply_plan(target, files, plan)
        after, _ = reader.read_case(target)
        eq(after["mesh.faces"].value[0][0], "inlet",
           "the face under the renamed patch still shows the old name")


@check("a face added at the end joins the last patch")
def _() -> None:
    # The only place this table can grow is the end, which here means the last
    # patch's own block -- the appended line lands before its `)`, where a face
    # of that patch belongs, not after the list.
    resolved, files = read()
    rows = [list(row) for row in resolved["mesh.faces"].value]
    rows.append(list(resolved["mesh.faces"].param.row_seed or []))
    plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.faces", rows)])
    eq(plan.errors, {}, "appending a face was rejected")
    rendered = render_all(plan, files)[BM]
    eq(
        rendered,
        files[BM].text.replace(
            "        (4 5 7 6)\r\n    )", "        (4 5 7 6)\r\n        (0 1 2 3)\r\n    )", 1
        ),
        "the appended face is not inside the patch it was added to",
    )


@check("the patch table refuses a row that was added or dropped")
def _() -> None:
    # The panel hides its Add/Remove for this table, but the rail is here: a
    # header written without the block of faces under it -- or dropped and
    # leaving one behind -- is a file blockMesh cannot read.
    resolved, files = read()
    rows = [list(row) for row in resolved["mesh.patches"].value]
    for changed, what in ((rows + [["wall", "extra"]], "added"), (rows[:-1], "dropped")):
        plan = writer.plan_edits(resolved, files, [writer.Edit("mesh.patches", changed)])
        truthy("mesh.patches" in plan.errors, f"a {what} patch row was accepted")
        eq(plan.changed_files, [], f"a {what} patch row reached the plan")


@check("the multisphere case writes each value back byte-identically")
def _() -> None:
    # The echo above runs on two_phase_sphere_settling, where the whole multisphere route is
    # unused and therefore unwritable -- so it cannot see those rules at all.
    # This one echoes the fish deck's own values back at it, which is what
    # catches a regex over-capturing an ``&`` continuation or the token beside
    # it -- ``spheres file ../DEM/data/fish`` shares its line with the rest of
    # the fix block.
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
        ("phys.water.nu", 1.004e-06),
        ("phys.water.rho", 998.2),
        ("phys.air.nu", 1.48e-05),
        ("phys.air.rho", 1.2),
    ):
        r = resolved[pid]
        eq(r.status, "ok", f"{pid} status")
        eq(r.value, want, f"{pid} value")
        truthy(r.scopes, f"{pid}: the block {r.param.scope!r} was not located")
        # ``Resolved.line`` is 1-based (it is what the panel shows), while the
        # scope levels index the split lines from 0.
        truthy(
            r.line - 1 in r.scopes[-1].body,
            f"{pid} landed outside the block {r.param.scope!r}",
        )

    # ``sigma`` is a top-level entry, so what has to hold is the other way round:
    # no scope, and exactly one line in the file carries the keyword.
    sigma = resolved["phys.sigma"]
    eq(sigma.status, "ok", "phys.sigma status")
    eq(sigma.value, 0.07275, "phys.sigma value")
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
    # Built by swapping the number out of the line as it is on disk, so what is
    # compared is *what else* survived -- the repeated keyword and the bracketed
    # dimension set -- and the expectation does not have to be retyped whenever
    # the case's own sigma changes.
    eq(after[changed[0]], re.sub(r"[0-9.eE+\-]+(?=;)", "0.05", before[changed[0]]),
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


def particle_rows(resolved) -> List[list]:
    """``dem.particles`` as plain lists, which is what an edit carries."""
    return [list(row) for row in resolved["dem.particles"].value]


@check("changing one particle's diameter leaves the rest of its line alone")
def _() -> None:
    # One particle is three lines: the anchor comment, ``create_atoms``, and
    # ``set atom``.  The diameter is one token on the last of them, and the
    # density, the velocity and the coordinate line beside it are all `set`
    # tokens sharing that line -- so only the one span may move.
    resolved, files = read()
    before = [l for l in files[DEM].text.split("\n") if "diameter" in l and "density" in l]
    truthy(before, "the particle definition line was not found")
    rows = particle_rows(resolved)
    rows[0][4] = 0.02  # the diameter column of the first particle
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.particles", rows)])
    eq(plan.errors, {}, "the particle edit was rejected")
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
    # The coordinate line feeding `create_atoms` is a different line of the same
    # row, so it must not have been rewritten with the resolved numbers.
    eq(
        [l for l in render_all(plan, files)[DEM].split("\n") if "create_atoms" in l],
        [l for l in files[DEM].text.split("\n") if "create_atoms" in l],
        "the create_atoms line changed",
    )


@check("changing the diameter does not disturb the density beside it")
def _() -> None:
    resolved, files = read()
    rows = particle_rows(resolved)
    rows[0][4] = 0.02  # diameter
    rows[0][5] = 2500  # density, the very next column on the same line
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.particles", rows)])
    eq(plan.errors, {}, "the particle edit was rejected")
    lines = [l for l in render_all(plan, files)[DEM].split("\n") if "diameter" in l and "density" in l]
    truthy(lines, "the particle definition line was not found")
    truthy("0.02" in lines[0] and "2500" in lines[0], f"both values were not written: {lines[0]!r}")


@check("CRLF endings are preserved")
def _() -> None:
    resolved, files = read()
    eq(files[DEM].endings[2], "\r\n", "line 3 is not CRLF")
    rows = particle_rows(resolved)
    rows[0][4] = 0.02
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.particles", rows)])
    rendered = render_all(plan, files)[DEM]
    eq(rendered.count("\r\n"), files[DEM].text.count("\r\n"), "the CRLF count changed")
    truthy("\n" not in rendered.replace("\r\n", ""), "a bare LF was produced")


@check("the value read back after apply equals the one written")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        resolved, files = reader.read_case(target)
        rows = particle_rows(resolved)
        rows[0][4] = 0.02
        plan = writer.plan_edits(resolved, files, [writer.Edit("dem.particles", rows)])
        writer.apply_plan(target, files, plan)
        after, _ = reader.read_case(target)
        eq(after["dem.particles"].value[0][4], 0.02, "the diameter read back")


@check("untouched files keep their original bytes after a write")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        resolved, files = reader.read_case(target)
        untouched = target / "CFD/system/blockMeshDict"
        before = untouched.read_bytes()
        rows = particle_rows(resolved)
        rows[0][4] = 0.02
        plan = writer.plan_edits(resolved, files, [writer.Edit("dem.particles", rows)])
        writer.apply_plan(target, files, plan)
        eq(untouched.read_bytes(), before, "an untouched file was rewritten")


# ---------------------------------------------------------------------------
# the particle zone -- a table row spread over three lines, plus its notes
# ---------------------------------------------------------------------------


@check("the particle table reads one row per particle, across its three lines")
def _() -> None:
    # Unlike `mesh.vertices` (one line per row), a particle is written on three:
    # the `#notes_pN:` anchor, its `create_atoms` coordinate line and its
    # `set atom` property line.  `Row.spans` already carries a line per span, so
    # the reader stitches the three into one row -- and every line of it moves
    # together when the row is edited.
    resolved, _files = reader.read_case(TWO_SPHERE)
    r = resolved["dem.particles"]
    eq(r.status, "ok", "status")
    eq(r.matches, 2, "row count")
    eq(
        r.value,
        [
            [
                "trailing particle -- the single-sphere case's own starting point",
                0.005, 0.005, 0.035, 0.00167, 1140.0, 0.0, 0.0, 0.0,
            ],
            [
                "leading particle -- 0.002 m (2 diameters) below it",
                0.005, 0.005, 0.0316, 0.00167, 1140.0, 0.0, 0.0, 0.0,
            ],
        ],
        "the particles",
    )
    for row in r.rows:
        eq(len(set(row.lines)), 3, f"line {row.line}: the row is not three lines")
        eq(row.line, row.lines[0] + 1, "the reported line is not the anchor comment")
    eq(
        reader.resolved_to_api(r)["row_seed"],
        ["", 0.005, 0.005, 0.0316, 0.00167, 1140.0, 0.0, 0.0, 0.0],
        "a new particle should start where the last one is",
    )


@check("a particle added at the end becomes three lines, renumbered like the ones above it")
def _() -> None:
    # The controls at the end of the fold-out write a whole particle, not a
    # line, and the id is not the user's to type: the anchor's `#notes_pN` and
    # the `set atom <id>` are renumbered from the row's position.
    resolved, files = reader.read_case(TWO_SPHERE)
    seed = reader.resolved_to_api(resolved["dem.particles"])["row_seed"]
    rows = particle_rows(resolved) + [list(seed)]
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.particles", rows)])
    eq(plan.errors, {}, "appending a particle was rejected")
    rendered = render_all(plan, files)[DEM]
    eq(
        rendered,
        files[DEM].text.replace(
            "set                atom 2 diameter 0.00167 density 1140 vx 0 vy 0 vz 0\r\n",
            "set                atom 2 diameter 0.00167 density 1140 vx 0 vy 0 vz 0\r\n"
            "# notes_p3: \r\n"
            "create_atoms       1 single 0.005 0.005 0.0316  units box\r\n"
            "set                atom 3 diameter 0.00167 density 1140 vx 0 vy 0 vz 0\r\n",
            1,
        ),
        "the appended particle is not three lines with a fresh id",
    )
    eq(rendered.count("\r\n"), files[DEM].text.count("\r\n") + 3, "the CRLF count changed wrongly")


@check("the last particle can be taken off the end of the table")
def _() -> None:
    resolved, files = reader.read_case(TWO_SPHERE)
    rows = particle_rows(resolved)[:-1]
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.particles", rows)])
    eq(plan.errors, {}, "removing the last particle was rejected")
    rendered = render_all(plan, files)[DEM]
    eq(
        rendered,
        files[DEM].text.replace(
            "# notes_p2: leading particle -- 0.002 m (2 diameters) below it\r\n"
            "create_atoms       1 single 0.005 0.005 0.0316  units box\r\n"
            "set                atom 2 diameter 0.00167 density 1140 vx 0 vy 0 vz 0\r\n",
            "",
            1,
        ),
        "all three of the particle's lines should have gone",
    )


@check("the zone notes are the comment lines above the first particle")
def _() -> None:
    resolved, _files = reader.read_case(TWO_SPHERE)
    r = resolved["dem.zone_notes"]
    eq(r.status, "ok", "status")
    eq(
        r.value,
        [
            "create two particles, in tandem along the fall direction z: the leading "
            "one sits two diameters below the trailing one, so its wake acts on it",
        ],
        "the zone notes",
    )
    eq(reader.resolved_to_api(r)["columns"], [], "the notes are not a table")
    # The single-particle case has its one comment line in the same place.
    one, _ = read()
    eq(one["dem.zone_notes"].value, ["create single partciles"], "the one-particle notes")


@check("rewriting the zone notes touches only that block")
def _() -> None:
    resolved, files = reader.read_case(TWO_SPHERE)
    notes = list(resolved["dem.zone_notes"].value)
    notes[0] = "the leading one sits two diameters below it"
    plan = writer.plan_edits(resolved, files, [writer.Edit("dem.zone_notes", notes)])
    eq(plan.errors, {}, "the zone-note edit was rejected")
    eq(
        render_all(plan, files)[DEM],
        files[DEM].text.replace(
            "# create two particles, in tandem along the fall direction z: the leading "
            "one sits two diameters below the trailing one, so its wake acts on it",
            "# the leading one sits two diameters below it",
            1,
        ),
        "the note block was not rewritten in place",
    )


@check("the zone notes can grow and shrink, and only that block moves")
def _() -> None:
    resolved, files = reader.read_case(TWO_SPHERE)
    plan = writer.plan_edits(
        resolved, files, [writer.Edit("dem.zone_notes", ["one line", "two lines"])]
    )
    eq(plan.errors, {}, "the zone-note edit was rejected")
    rendered = render_all(plan, files)[DEM]
    eq(
        rendered,
        files[DEM].text.replace(
            "# create two particles, in tandem along the fall direction z: the leading "
            "one sits two diameters below the trailing one, so its wake acts on it\r\n",
            "# one line\r\n# two lines\r\n",
            1,
        ),
        "the note block was not rewritten",
    )
    eq(
        rendered.count("\r\n"),
        files[DEM].text.count("\r\n") + 1,
        "the note block grew by one line and nothing else moved",
    )


@check("a blank line in the zone notes is refused")
def _() -> None:
    # The zone ends at the first blank line, so one inside the notes would cut
    # the block in two and orphan the particles below it.
    resolved, files = reader.read_case(TWO_SPHERE)
    plan = writer.plan_edits(
        resolved, files, [writer.Edit("dem.zone_notes", ["above", "", "below"])]
    )
    eq(set(plan.errors), {"dem.zone_notes"}, "a blank note line was accepted")


# ---------------------------------------------------------------------------
# creating the lines a case does not have -- the model coefficient blocks
# ---------------------------------------------------------------------------


def block_body(text: str, header: str) -> List[str]:
    """The stripped lines between a ``header {`` and its closing brace."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    truthy(start is not None, f"{header} was not created")
    out: List[str] = []
    for line in lines[start + 1:]:
        if line.strip() == "}":
            return out
        out.append(line.strip())
    raise AssertionError(f"{header} is never closed")


def coeffs_of(text: str, header: str) -> Dict[str, str]:
    """The ``keyword -> value`` pairs of a created coefficient block."""
    return {
        line.split()[0]: line.split("]")[1].strip().rstrip(";")
        for line in block_body(text, header)
        if line.endswith(";")
    }


def changed_rows(plan, files, rel: str) -> List[str]:
    """The opcode kinds of a plan, one per changed line, in file order."""
    after = render_all(plan, files)[rel]
    return [
        row["type"]
        for hunk in writer.structured_diff(files[rel].text, after)
        for row in hunk["rows"]
        if row["type"] != "equal"
    ]


@check("choosing a model the case never ran builds its coefficient block")
def _() -> None:
    # The whole point of the feature: OpenFOAM keeps a non-Newtonian model's
    # coefficients in a ``<Model>Coeffs`` sub-dictionary, so a case running
    # Newtonian has none of them -- and picking one in the panel is meant to
    # bring the block into being.  What lands has to be the *same* fluid, so
    # every viscosity-dimensioned coefficient is seeded from the phase's nu and
    # the rest degenerate to the model's Newtonian limit.
    resolved, files = read()
    plan = writer.plan_edits(
        resolved, files, [writer.Edit("phys.water.transportModel", "BirdCarreau")]
    )
    eq(plan.errors, {}, "switching the viscosity model was rejected")
    rows = changed_rows(plan, files, TP)
    # One rewritten line -- the model -- and the block: header, brace, four
    # coefficients, brace.  Nothing deleted, and nothing else in the file moved.
    eq(rows.count("replace"), 1, f"more than the model line was rewritten: {rows}")
    eq(rows.count("delete"), 0, f"a line was deleted: {rows}")
    eq(rows.count("insert"), 7, f"the block is not seven lines: {rows}")

    rendered = render_all(plan, files)[TP]
    eq(
        coeffs_of(rendered, "BirdCarreauCoeffs"),
        # k's dimension is seconds, not m2/s, so it degenerates to 0 rather than
        # being seeded from nu -- the distinction the whole table exists for.
        {"nu0": "1.004e-06", "nuInf": "1.004e-06", "k": "0", "n": "1"},
        "the seeded coefficients",
    )
    # The phase's own lines survive: `nu` says nothing to a BirdCarreau case, but
    # it is what the block was just seeded from, and removing it would be this
    # panel inventing a rule the solver does not have.
    for line in (
        "    transportModel  BirdCarreau;",
        "    nu              nu [ 0 2 -1 0 0 0 0 ] 1.004e-06;",
        "    rho             rho [ 1 -3 0 0 0 0 0 ] 998.2;",
    ):
        truthy(line in rendered, f"the phase line {line!r} did not survive")


@check("a created block keeps the file's own line endings")
def _() -> None:
    resolved, files = read()
    eq(files[TP].endings[23], "\r\n", "the water block's closing brace is not CRLF")
    plan = writer.plan_edits(
        resolved, files, [writer.Edit("phys.water.transportModel", "BirdCarreau")]
    )
    rendered = render_all(plan, files)[TP]
    eq(
        rendered.count("\r\n"),
        files[TP].text.count("\r\n") + 7,
        "the inserted lines did not follow the file's ending convention",
    )
    truthy("\n" not in rendered.replace("\r\n", ""), "a bare LF was produced")


@check("a switched model round-trips, and switching back leaves the block alone")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        start, files = reader.read_case(target)
        # Newtonian is what the case runs, so another model's coefficients are
        # simply not part of it rather than a rule that failed.
        eq(start["phys.water.BirdCarreau.nu0"].status, "inactive", "before the switch")
        eq(start["phys.water.nu"].status, "ok", "before the switch")

        plan = writer.plan_edits(
            start, files, [writer.Edit("phys.water.transportModel", "BirdCarreau")]
        )
        writer.apply_plan(target, files, plan)

        after, files2 = reader.read_case(target)
        eq(after["phys.water.transportModel"].value, "BirdCarreau", "the model")
        for keyword, want in (("nu0", 1.004e-06), ("nuInf", 1.004e-06),
                              ("k", 0.0), ("n", 1.0)):
            r = after[f"phys.water.BirdCarreau.{keyword}"]
            eq(r.status, "ok", f"{keyword} status")
            eq(r.value, want, f"{keyword} value")
        # Only the water phase switched, and ``nu`` belongs to the model it left.
        eq(after["phys.air.BirdCarreau.nu0"].status, "inactive", "the air phase")
        eq(after["phys.water.nu"].status, "inactive", "nu is Newtonian's")
        # Density is listed under the same model but belongs to no model, so the
        # switch must leave it exactly where it was.
        eq(after["phys.water.rho"].status, "ok", "density followed the model")
        eq(after["phys.water.rho"].value, start["phys.water.rho"].value, "density value")

        # Switching back renames the model and nothing else.  The block stays
        # where it is: deleting it would throw away coefficients the case now
        # carries, and switching back and forth again would lose them.
        back = writer.plan_edits(
            after, files2, [writer.Edit("phys.water.transportModel", "Newtonian")]
        )
        eq(back.errors, {}, "switching back was rejected")
        eq(back.changed_files, [TP], "switching back touched another file")
        eq(changed_rows(back, files2, TP), ["replace"],
           "switching back did more than rename the model")
        truthy(
            "BirdCarreauCoeffs" in (target / TP).read_text(encoding="utf-8"),
            "the block was removed",
        )


@check("a coefficient typed while its block is being created keeps what was typed")
def _() -> None:
    # A number the user is looking at wins over the seed, so a block that comes
    # into being and a coefficient edited in the same write do not fight: the
    # one box they typed into lands, and the rest is still the phase's nu.
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        path = target / TP
        path.write_bytes(
            path.read_text(encoding="utf-8")
            .replace("transportModel  Newtonian;", "transportModel  powerLaw;", 1)
            .encode("utf-8")
        )
        resolved, files = reader.read_case(target)
        plan = writer.plan_edits(
            resolved, files, [writer.Edit("phys.water.powerLaw.n", 0.8)]
        )
        eq(plan.errors, {}, "writing a coefficient of a block being created was rejected")
        eq(
            coeffs_of(render_all(plan, files)[TP], "powerLawCoeffs"),
            {"k": "1.004e-06", "n": "0.8", "nuMin": "1.004e-06", "nuMax": "1.004e-06"},
            "the seeded coefficients",
        )


@check("a model named in the file with no coefficients to back it reads as create")
def _() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = copy_case(Path(tmp))
        path = target / TP
        path.write_bytes(
            path.read_text(encoding="utf-8")
            .replace("transportModel  Newtonian;", "transportModel  Casson;", 1)
            .encode("utf-8")
        )
        resolved, _files = reader.read_case(target)
        for keyword, want in (("m", 1.004e-06), ("tau0", 0.0),
                              ("nuMin", 1.004e-06), ("nuMax", 1.004e-06)):
            r = resolved[f"phys.water.Casson.{keyword}"]
            eq(r.status, "create", f"{keyword} status")
            eq(r.value, want, f"{keyword} value")
            # Editable, and *only* because the model is the one in force: the
            # panel has to be able to type into a box whose line does not exist.
            eq(reader.resolved_to_api(r)["editable"], True, f"{keyword} editable")
        # Everything the case is not running stays out of the way, including the
        # model the phase just left.
        for pid in ("phys.water.nu", "phys.water.BirdCarreau.n", "phys.air.Casson.m"):
            eq(resolved[pid].status, "inactive", pid)
        eq(resolved["phys.air.nu"].status, "ok", "the air phase is still Newtonian")

        # ``nu`` is Newtonian's coefficient and this phase is not Newtonian, so
        # it is neither shown nor writable -- which is also what stops the old
        # line from being quietly edited into a number nothing reads.
        plan = writer.plan_edits(resolved, _files, [writer.Edit("phys.water.nu", 2e-06)])
        truthy("phys.water.nu" in plan.errors, "a coefficient of another model was writable")


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

    # These three describe the two_phase_sphere_settling mesh, so they move whenever its
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
    # `server/` is the dashboard's read/write layer: it reads and writes
    # dictionaries and starts nothing.  The OS folder dialog used to be a
    # deliberate, narrow exception to that; the folder browser is served out of
    # the same handler as every other endpoint, so there is no exception left
    # and this can be absolute.  A read-only WSL health probe once grew a
    # subprocess here and had to be deleted -- this is what would catch it
    # coming back.
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
    truthy(flagged.get("two_phase_sphere_settling"), "two_phase_sphere_settling was not flagged as a case")
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
# the step scripts
# ---------------------------------------------------------------------------


@check("a step script's name resolves to its number and the stem after it")
def _() -> None:
    # The two spellings in the repository put the marker in different places,
    # and one of them puts it *after* the extension -- which is why the `.sh`
    # has to be stripped before the marker is cut out rather than after.
    for name, want in {
        "step1_allclean.sh": (1, "allclean"),
        "step2_blockmeshsetfields.sh": (2, "blockmeshsetfields"),
        "step3_Allrun.sh": (3, "Allrun"),
        "step4_reconstruct.sh": (4, "reconstruct"),
        "step5_ani.sh": (5, "ani"),
        "step5_draw_curve.sh": (5, "draw_curve"),
        "allclean_step1": (1, "allclean"),
        "blockmeshsetfields_step2": (2, "blockmeshsetfields"),
        "Allrun.sh_step3": (3, "Allrun"),
        "parCFDDEMrun.sh": (None, ""),
        "new": (None, ""),
    }.items():
        eq(steps.parse_script(name), want, f"{name} parsed as {steps.parse_script(name)!r}")


@check("a case's step scripts are found in pipeline order")
def _() -> None:
    eq(
        [(s["step"], s["token"], s["script"]) for s in steps.find_scripts(CASE)],
        [
            (1, "allclean", "step1_allclean.sh"),
            (2, "blockmeshsetfields", "step2_blockmeshsetfields.sh"),
            (3, "Allrun", "step3_Allrun.sh"),
            (4, "reconstruct", "step4_reconstruct.sh"),
            (5, "ani", "step5_ani.sh"),
            (5, "draw_curve", "step5_draw_curve.sh"),
        ],
        "the two_phase_sphere_settling step scripts",
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
