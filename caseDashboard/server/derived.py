"""Derived metrics and cross-file consistency checks.

The single most useful property of this module is that it runs on *edited but
unwritten* values: the UI debounces edits and calls it before anything touches
disk, so a broken combination (``couple_every 200`` against
``couplingInterval 100``) is visible while it is still free to fix.

Everything here is pure: it takes resolved values plus a list of pending edits
and returns plain data.  No file is read or written.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .reader import Resolved

OK, INFO, WARN, ERROR = "ok", "info", "warn", "error"

_LEVEL_RANK = {OK: 0, INFO: 1, WARN: 2, ERROR: 3}


def worst(levels: Iterable[str]) -> str:
    out = OK
    for level in levels:
        if _LEVEL_RANK[level] > _LEVEL_RANK[out]:
            out = level
    return out


def _fmt(value: Optional[float], digits: int = 6) -> str:
    if value is None:
        return "—"
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.{digits}g}"


class Ctx:
    """Effective parameter values: file contents overlaid with pending edits."""

    def __init__(self, resolved: Dict[str, Resolved], edits: Optional[List[dict]] = None):
        self.resolved = resolved
        self.values: Dict[str, Any] = {pid: r.value for pid, r in resolved.items()}
        self.enabled: Dict[str, bool] = {pid: r.enabled for pid, r in resolved.items()}
        for edit in edits or []:
            pid = edit.get("id")
            if pid in self.values:
                self.values[pid] = edit.get("value")
            if pid in self.enabled and edit.get("enabled") is not None:
                self.enabled[pid] = bool(edit["enabled"])
        self._apply_products()

    def _apply_products(self) -> None:
        """Recompute every ``product_of`` param from its sources.

        Such a param is computed, not typed in, so an edit to one of its sources
        has to move it here too -- otherwise every debounced derive would report
        the very inconsistency the writer is about to fix.  A source that is
        unresolved leaves the file's value alone rather than inventing one.

        A triple is read one source per component rather than multiplied, so the
        DEM's processor grid tracks the CFD decomposition axis by axis.
        """
        for pid, r in self.resolved.items():
            sources = r.param.product_of
            if not sources:
                continue
            numbers = [self.num(src) for src in sources]
            if any(n is None for n in numbers):
                continue
            if r.param.is_triple:
                if len(numbers) != 3:
                    continue
                self.values[pid] = [int(n) for n in numbers]
            else:
                self.values[pid] = int(math.prod(numbers))

    # -- accessors ---------------------------------------------------------
    def raw(self, pid: str) -> Any:
        return self.values.get(pid)

    def num(self, pid: str) -> Optional[float]:
        value = self.values.get(pid)
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def integer(self, pid: str) -> Optional[int]:
        value = self.num(pid)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def triple(self, pid: str) -> Optional[List[float]]:
        value = self.values.get(pid)
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return None
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return None

    def rows(self, pid: str) -> Optional[List[List]]:
        """The rows of a ``repeats`` table, in file order.

        ``None`` for a value that is not one -- including a triple, which is a
        list of numbers rather than a list of rows, so the two shapes cannot be
        confused by accident.
        """
        value = self.values.get(pid)
        if not isinstance(value, (list, tuple)) or not value:
            return None
        if not all(isinstance(row, (list, tuple)) for row in value):
            return None
        return [list(row) for row in value]

    def live(self, pid: str) -> bool:
        """False for a toggle param whose line has been commented out."""
        return self.enabled.get(pid, True)

    def truthy(self, pid: str) -> Optional[bool]:
        value = self.values.get(pid)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on", "y", "t")
        return None

    def source(self, pid: str) -> dict:
        r = self.resolved.get(pid)
        if not r:
            return {"file": "", "line": None}
        return {"file": r.param.file, "line": r.line}

    def label(self, pid: str) -> str:
        r = self.resolved.get(pid)
        return r.param.label if r else pid


def _display(value) -> str:
    """Readable rendering; the raw number stays available as ``value``."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return _fmt(value)
    return str(value)


def metric(mid, label, value, unit="", status=OK, message="", formula="", sources=None,
           detail="") -> dict:
    """One card: ``display`` is what the header shows, ``detail`` is an optional
    line under the name for a value that does not fit one right-aligned slot
    (three components, each wanting its own axis letter)."""
    return {
        "id": mid,
        "label": label,
        "value": value,
        "display": _display(value),
        "unit": unit,
        "status": status,
        "message": message,
        "formula": formula,
        "detail": detail,
        "source_refs": sources or [],
    }


def check(cid, level, title, message, sources=None, param_ids=None) -> dict:
    return {
        "id": cid,
        "level": level,
        "title": title,
        "message": message,
        "sources": sources or [],
        "param_ids": param_ids or [],
    }


def _src(ctx: Ctx, pid: str, label: str = "") -> dict:
    s = ctx.source(pid)
    return {
        "param_id": pid,
        "label": label or ctx.label(pid),
        "file": s["file"],
        "line": s["line"],
        "value": ctx.raw(pid),
    }


def _resolve_refs(ctx: Ctx, m: dict) -> dict:
    """Metric call sites list bare param ids for brevity; the UI needs the
    label and ``file:line`` too, so expand them into full refs here."""
    return {**m, "source_refs": [_src(ctx, pid) for pid in m["source_refs"]]}


def _close(a: Optional[float], b: Optional[float], tol: float = 1e-9) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


#: The DEM block's particle table, by the column names ``profiles`` gives it.
PARTICLES = "dem.particles"

#: ``blockMeshDict``'s block list -- the same kind of table, with its own
#: column names (``vkind``/``vnodes``/``vcells``/``vgrade``).
BLOCKS = "mesh.blocks"


def _particles(ctx: Ctx) -> List[Dict[str, Any]]:
    """Every particle of the single-sphere route, one dict per row.

    The keys are the table's own column names (``valx``/``vald``/``valrho``
    ...), with a 1-based ``n`` added so a message can say *which* particle it
    is about -- the block is renumbered by position on every write, so the
    position is the only name a particle has.
    """
    rows = ctx.rows(PARTICLES)
    if not rows:
        return []
    r = ctx.resolved.get(PARTICLES)
    names = r.param.row_groups if r else []
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        item = dict(zip(names, row))
        item["n"] = i
        out.append(item)
    return out


def _pnum(p: Dict[str, Any], name: str) -> Optional[float]:
    try:
        return float(p[name])
    except (KeyError, TypeError, ValueError):
        return None


def _plabel(p: Dict[str, Any]) -> str:
    return f"particle {p['n']}"


def _blocks(ctx: Ctx) -> List[Dict[str, Any]]:
    """Every block of ``blockMeshDict``, one dict per row, keyed by column."""
    rows = ctx.rows(BLOCKS)
    if not rows:
        return []
    r = ctx.resolved.get(BLOCKS)
    names = r.param.row_groups if r else []
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        item = dict(zip(names, row))
        item["n"] = i
        out.append(item)
    return out


def _divisions(block: Dict[str, Any]) -> List[int]:
    """A block's division counts as three integers, or ``[]``.

    The cell is the file's own text -- ``"50 50 100"`` -- because the panel
    writes the whole string back verbatim; the metrics are the one place that
    has to read numbers out of it.
    """
    try:
        return [int(t) for t in str(block.get("vcells") or "").split()]
    except ValueError:
        return []


# ---------------------------------------------------------------- metrics


def compute_metrics(ctx: Ctx) -> List[dict]:
    metrics: List[dict] = []

    x1, x2 = ctx.num("mesh.xco1"), ctx.num("mesh.xco2")
    y1, y2 = ctx.num("mesh.yco1"), ctx.num("mesh.yco2")
    z1, z2 = ctx.num("mesh.zco1"), ctx.num("mesh.zco2")
    # One block is the case here, and a mesh split into several is judged by
    # its first: the cell size, the anisotropy and the cells/diameter verdict
    # are read off block 1, and the message on the cell-size card says so.
    blocks = _blocks(ctx)
    counts = [_divisions(b) for b in blocks]
    cells = counts[0] if counts and len(counts[0]) == 3 else None
    particles = _particles(ctx)
    # The diameter the *worst* particle has: cells/diameter is a resolution
    # verdict, so the smallest particle is the one it has to be judged by.
    diameters = [d for d in (_pnum(p, "vald") for p in particles) if d]
    diameter = min(diameters) if diameters else None

    if None in (x1, x2, y1, y2, z1, z2) or cells is None:
        metrics.append(metric("mesh.size", "Domain size", None, status=WARN,
                              message="Mesh parameters are incomplete; cannot compute"))
        return metrics

    nx, ny, nz = (int(c) for c in cells)
    lx, ly, lz = x2 - x1, y2 - y1, z2 - z1
    dx = lx / nx if nx else None
    dy = ly / ny if ny else None
    dz = lz / nz if nz else None

    def mm(v):
        return None if v is None else v * 1000.0

    metrics.append(metric(
        "mesh.domain", "Domain size (x×y×z)",
        f"{_fmt(mm(lx), 4)} × {_fmt(mm(ly), 4)} × {_fmt(mm(lz), 4)}", "mm",
        formula="xco2-xco1, yco2-yco1, zco2-zco1",
        sources=["mesh.xco1", "mesh.xco2", "mesh.yco1", "mesh.yco2", "mesh.zco1", "mesh.zco2"],
    ))
    # One card, not three.  Δx/Δy/Δz are a single quantity read along three
    # axes, and as three cards they pushed the metrics that actually differ off
    # the top of the panel.  The axis letters go on the detail line, so the
    # header keeps a short name and every direction is still spelled out.
    metrics.append(metric(
        "mesh.delta", "Cell size",
        f"{_fmt(mm(dx), 4)} × {_fmt(mm(dy), 4)} × {_fmt(mm(dz), 4)}", "mm",
        detail=" · ".join(
            f"Δ{axis} {_fmt(mm(delta), 4)}" for axis, delta in zip("xyz", (dx, dy, dz))
        ) + " mm",
        message="" if len(blocks) == 1 else
        f"From block 1 of {len(blocks)}; the other blocks are not measured",
        formula="(xco2-xco1)/nx, (yco2-yco1)/ny, (zco2-zco1)/nz",
        sources=["mesh.blocks"],
    ))

    dims = [d for d in (dx, dy, dz) if d]
    if dims and min(dims) > 0:
        ratio = max(dims) / min(dims)
        is_uniform = ratio <= 1.0001
        metrics.append(metric(
            "mesh.uniformity", "Cell isotropy",
            f"{ratio:.4f}", "max/min",
            status=OK if is_uniform else WARN,
            message="" if is_uniform else
            "Cell sizes differ by direction; the interface will be resolved anisotropically",
            formula="max(Δx,Δy,Δz)/min(Δx,Δy,Δz)",
            sources=["mesh.blocks"],
        ))

    # Every block's own cell count: a mesh of several blocks has more cells
    # than the first one implies, and the run's cost follows the total.
    metrics.append(metric(
        "mesh.ncells", "Total cells",
        sum(c[0] * c[1] * c[2] for c in counts if len(c) == 3), "cells",
        formula="nx·ny·nz" if len(blocks) == 1 else "Σ nx·ny·nz",
        sources=["mesh.blocks"],
    ))

    if diameter and dx:
        per_diameter = diameter / dx
        level = OK if per_diameter >= 5 else (INFO if per_diameter >= 3 else WARN)
        worst = next(
            (p for p in particles if _pnum(p, "vald") == diameter), None
        )
        suffix = ""
        if len(diameters) > 1:
            suffix = f" ({_plabel(worst)} of {len(diameters)}; the smallest decides)"
        metrics.append(metric(
            "mesh.cells_per_diameter", "cells / particle diameter",
            f"{per_diameter:.2f}", "cells",
            status=level,
            message="" if level == OK else
            "The particle diameter spans too few cells; immersed-boundary forces "
            "will be dominated by discretisation noise" + suffix,
            formula="diameter / Δx",
            sources=["dem.particles", "mesh.blocks", "mesh.xco1", "mesh.xco2"],
        ))

        # The span is per particle -- each sits somewhere of its own -- and the
        # card reports the worst of them, named, since only one number fits.
        widest = None
        for p in particles:
            center = [_pnum(p, a) for a in ("valx", "valy", "valz")]
            dd = _pnum(p, "vald") or diameter
            if None in center:
                continue
            radius = dd / 2.0
            spans: Dict[str, int] = {}
            # Axes that landed on the same placement share one clause; the
            # sentence is the *reason* the spans are not simply diameter/Δ, and
            # saying it three times says nothing the third time.
            placement: Dict[str, List[str]] = {}
            for axis, (coord, delta, lo) in zip(
                "xyz",
                ((center[0], dx, x1), (center[1], dy, y1), (center[2], dz, z1)),
            ):
                if not delta:
                    continue
                offset = (coord - lo) / delta
                where = "a mesh vertex" if abs(offset - round(offset)) < 1e-6 else "a cell interior"
                left = math.floor((coord - radius - lo) / delta)
                right = math.floor((coord + radius - lo) / delta)
                spans[axis] = right - left + 1
                placement.setdefault(where, []).append(f"{axis}={_fmt(coord, 4)}")
            ordered = [axis for axis in "xyz" if axis in spans]
            if not ordered:
                continue
            here = (max(spans[a] for a in ordered), p, spans, ordered, placement)
            if widest is None or here[0] > widest[0]:
                widest = here

        if widest is not None:
            _, p, spans, ordered, placement = widest
            who = f"{_plabel(p)} of {len(particles)}; " if len(particles) > 1 else ""
            metrics.append(metric(
                "mesh.span", "Cells spanned by the diameter",
                " × ".join(str(spans[a]) for a in ordered), "cells",
                detail=" · ".join(f"{a} {spans[a]}" for a in ordered) + " cells",
                status=OK if all(spans[a] <= per_diameter + 3 for a in ordered) else WARN,
                message=who + "centre " + "; ".join(
                    f"{', '.join(names)} on {where}"
                    for where, names in placement.items()
                ),
                formula="floor((c+r-lo)/Δ) - floor((c-r-lo)/Δ) + 1",
                sources=["dem.particles", "mesh.blocks"],
            ))

    # --- coupling period --------------------------------------------------
    dem_dt = ctx.num("dem.timestep")
    couple_every = ctx.integer("dem.couple_every")
    cfd_dt = ctx.num("run.deltaT")
    if dem_dt and couple_every and cfd_dt:
        period = dem_dt * couple_every
        steps = period / cfd_dt
        whole = abs(steps - round(steps)) < 1e-6
        metrics.append(metric(
            "coupling.period", "Coupling period", _fmt(period), "s",
            status=OK,
            formula="dem.timestep × couple_every",
            sources=["dem.timestep", "dem.couple_every"],
        ))
        metrics.append(metric(
            "coupling.steps_per_period", "CFD steps per coupling period",
            _fmt(steps, 8), "steps",
            status=OK if whole else ERROR,
            message="" if whole else
            f"{_fmt(period)} is not divisible by deltaT={_fmt(cfd_dt)}; CFD and DEM "
            "will drift out of phase",
            formula="coupling_period / deltaT",
            sources=["dem.timestep", "dem.couple_every", "run.deltaT"],
        ))
        # The same period counted the other way round.  It is `couple_every`
        # itself -- LIGGGHTS couples every N DEM steps by definition -- but
        # stated next to the CFD count it is what makes the two rates legible
        # together: one period is this many DEM steps and that many CFD steps.
        metrics.append(metric(
            "coupling.dem_steps_per_period", "DEM steps per coupling period",
            couple_every, "steps",
            status=OK,
            formula="couple_every",
            sources=["dem.couple_every"],
        ))

    # --- run length -------------------------------------------------------
    start = ctx.num("run.startTime") or 0.0
    end = ctx.num("run.endTime")
    if end is not None and cfd_dt:
        span = end - start
        steps = span / cfd_dt
        metrics.append(metric(
            "run.cfd_steps", "Total CFD steps",
            round(steps), "steps",
            status=OK if abs(steps - round(steps)) < 1e-6 else INFO,
            message="" if abs(steps - round(steps)) < 1e-6 else
            "endTime is not an integer multiple of deltaT; the last step will be truncated",
            formula="(endTime - startTime) / deltaT",
            sources=["run.endTime", "run.deltaT", "run.startTime"],
        ))

        write_control = ctx.raw("run.writeControl")
        interval = ctx.num("run.writeInterval")
        if interval:
            if write_control == "timeStep":
                frames = steps / interval
                formula = "steps / writeInterval"
            else:
                frames = span / interval
                formula = "(endTime - startTime) / writeInterval"
            metrics.append(metric(
                "run.frames", "Total number of output steps", round(frames), "frames",
                status=OK if frames >= 1 else WARN,
                message="" if frames >= 1 else
                "writeInterval exceeds the run length; no time directories will be written",
                formula=f"{formula}   [writeControl={write_control}]",
                sources=["run.writeInterval", "run.endTime", "run.writeControl"],
            ))

    # --- water level, and the particles against it ------------------------
    # One card for the two: the depth and where the particles sit against it
    # are the same question about the initial state -- a level on its own does
    # not say whether the run starts with the particles already wet, and a
    # placement is only legible beside the level it was measured to.  They read
    # off the same two numbers, so they are one answer.
    #
    # The depth is the box's own height, not its distance above the domain
    # floor: `zmin` is editable, so a box that floats above `zco1` still holds
    # exactly `zmax - zmin` of water.  An absent `zmin` reads as 0 rather than
    # as nothing (see `Param.default_when_absent`), so this metric survives a
    # case that writes only the upper corner.
    sf_zmax = ctx.num("mesh.sf.zmax")
    sf_zmin = ctx.num("mesh.sf.zmin")

    # --- particle placement ----------------------------------------------
    wet: List[Dict[str, Any]] = []
    for p in particles:
        z = _pnum(p, "valz")
        if z is not None:
            p["z"] = z
            wet.append(p)

    if sf_zmax is not None and sf_zmin is not None:
        depth = sf_zmax - sf_zmin
        high = [p for p in wet if p["z"] >= sf_zmax]
        state = (
            "below the water surface" if not high
            else ("above the water surface" if len(high) == len(wet)
                  else "partly above the water surface")
        ) if wet else ""
        warnings = []
        if depth <= 0:
            warnings.append(
                "The initial water box has no height (zmax is not above zmin); "
                "the initial field will have no water"
            )
        if high:
            warnings.append("; ".join(
                f"{_plabel(p)} centre z={_fmt(p['z'], 4)} is above the initial water "
                f"surface z={_fmt(sf_zmax, 4)}"
                for p in high
            ) + "; it will fall through air into the water")
        metrics.append(metric(
            "mesh.water_depth", "Initial water depth and particle state",
            depth, "m",
            status=WARN if depth <= 0 else (INFO if high else OK),
            message=" ".join(warnings),
            # The state is the half that does not fit the header slot, and a
            # metric that has a detail line prints nothing but its name up
            # there -- so the depth comes down here with it.  A case that
            # creates no particles has no state to report and is left as it
            # was: the depth alone, right-aligned against the name.
            detail=f"{_fmt(depth, 4)} m · {state}" if state else "",
            formula="setFields.zmax - setFields.zmin" + (
                " · pos.z < setFields.zmax" if wet else ""
            ),
            sources=["mesh.sf.zmax", "mesh.sf.zmin"] + (["dem.particles"] if wet else []),
        ))

    # --- parallel layout --------------------------------------------------
    procs = ctx.triple("dem.processors")
    # ``Ctx`` recomputes the subdomain count from prox×proy×proz, so this already
    # tracks a pending edit to any of the three directions.
    subs = ctx.integer("mesh.numberOfSubdomains")
    nr = ctx.integer("run.nrProcs")
    if subs is not None:
        metrics.append(metric(
            "parallel.subdomains", "Parallel processes",
            subs if (procs is None or nr is None) else f"{subs} (DEM {int(procs[0])}×{int(procs[1])}×{int(procs[2])}, nrProcs {nr})",
            "procs",
            status=OK,
            formula="numberOfSubdomains = nrProcs = ∏ DEM processors",
            sources=["mesh.numberOfSubdomains", "dem.processors", "run.nrProcs"],
        ))

    return metrics


# ------------------------------------------------------------ consistency


def _axis_rows(ctx: Ctx, axis: str) -> List[dict]:
    # ``blockMeshDict xco1`` / ``DEM xmin`` are file identifiers rather than
    # prose, so they stay as they are; the wall rows carry a word each.
    wanted = [
        (f"mesh.{axis}co1", f"blockMeshDict {axis}co1"),
        (f"mesh.{axis}co2", f"blockMeshDict {axis}co2"),
        (f"dem.{axis}min", f"DEM {axis}min"),
        (f"dem.{axis}max", f"DEM {axis}max"),
        (f"dem.wall.{axis}1", f"DEM wall {axis}plane lower"),
        (f"dem.wall.{axis}2", f"DEM wall {axis}plane upper"),
    ]
    return [_src(ctx, pid, label) for pid, label in wanted if pid in ctx.resolved]


def compute_consistency(ctx: Ctx) -> List[dict]:
    out: List[dict] = []

    # --- domain agreement across blockMeshDict / in.liggghts_run / walls ---
    for axis in ("x", "y", "z"):
        lo_cfd, hi_cfd = ctx.num(f"mesh.{axis}co1"), ctx.num(f"mesh.{axis}co2")
        lo_dem, hi_dem = ctx.num(f"dem.{axis}min"), ctx.num(f"dem.{axis}max")
        # A case that does not carry these rules at all resolves to ``None`` on
        # both sides; comparing two absences would report a mismatch for every
        # axis.  Nothing readable means there is nothing to say -- the missing
        # parameters are already reported as unrecognized.
        if None in (lo_cfd, hi_cfd, lo_dem, hi_dem):
            continue
        # A wall that has been commented out (disabled) is not part of the deck
        # any more, so it must not be demanded to agree with the CFD domain.
        lower, upper = f"dem.wall.{axis}1", f"dem.wall.{axis}2"
        lo_wall = ctx.num(lower) if ctx.live(lower) else None
        hi_wall = ctx.num(upper) if ctx.live(upper) else None
        off = [
            name
            for pid, name in ((lower, "lower"), (upper, "upper"))
            if not ctx.live(pid)
        ]
        problems = []
        if not _close(lo_cfd, lo_dem):
            problems.append(f"DEM {axis}min={_fmt(lo_dem)} ≠ blockMesh {axis}co1={_fmt(lo_cfd)}")
        if not _close(hi_cfd, hi_dem):
            problems.append(f"DEM {axis}max={_fmt(hi_dem)} ≠ blockMesh {axis}co2={_fmt(hi_cfd)}")
        if lo_wall is not None and not _close(lo_wall, lo_cfd):
            problems.append(f"DEM wall {_fmt(lo_wall)} ≠ blockMesh {_fmt(lo_cfd)}")
        if hi_wall is not None and not _close(hi_wall, hi_cfd):
            problems.append(f"DEM wall {_fmt(hi_wall)} ≠ blockMesh {_fmt(hi_cfd)}")
        if problems:
            message = "; ".join(problems)
        else:
            message = "blockMeshDict / DEM region / DEM walls agree"
            if off:
                message += (
                    f" ({', '.join(off)} walls disabled; excluded from the comparison)"
                )
        out.append(check(
            f"domain.{axis}", WARN if problems else OK,
            # The title is what the UI shows first, so it must state the
            # outcome -- "agrees" on a warning reads as a contradiction.
            f"Domain mismatch in {axis}" if problems else f"Domain agrees in {axis}",
            message,
            sources=_axis_rows(ctx, axis),
            param_ids=[f"mesh.{axis}co1", f"mesh.{axis}co2", f"dem.{axis}min",
                       f"dem.{axis}max", f"dem.wall.{axis}1", f"dem.wall.{axis}2"],
        ))

    # --- setFields box covers the domain and sits inside it ---------------
    for axis in ("x", "y"):
        hi_sf = ctx.num(f"mesh.sf.{axis}max")
        hi_dom = ctx.num(f"mesh.{axis}co2")
        if hi_sf is None or hi_dom is None:
            # Same reason as the domain check: an absent pair is not a verdict.
            continue
        if hi_sf < hi_dom:
            out.append(check(
                f"setfields.cover.{axis}", WARN,
                f"Initial water box does not cover the full {axis} extent",
                f"setFields {axis}max={_fmt(hi_sf)} < blockMesh {axis}co2={_fmt(hi_dom)}; "
                "a dry region will remain near the water surface",
                sources=[_src(ctx, f"mesh.sf.{axis}max"), _src(ctx, f"mesh.{axis}co2")],
                param_ids=[f"mesh.sf.{axis}max"],
            ))
        else:
            out.append(check(
                f"setfields.cover.{axis}", OK,
                f"Initial water box covers the {axis} direction",
                f"setFields {axis}max={_fmt(hi_sf)} ≥ domain upper bound {_fmt(hi_dom)}",
                sources=[_src(ctx, f"mesh.sf.{axis}max")],
            ))

    # The box's own z bounds are deliberately not checked against the domain.
    # A box that reaches past the lid (`zmax` above `zco2`, which is how a case
    # starts full of water) or under the floor (`zmin` below `zco1`) is a choice,
    # not a mistake, and the panel should not argue with it.  Only the above
    # `setfields.cover.*` checks remain: they compare the box against the *upper*
    # extent, where falling short leaves a dry corner rather than a wet one.
    #
    # `level` is still read here because the particle/water check below needs it.
    level = ctx.num("mesh.sf.zmax")

    # --- parallel layout --------------------------------------------------
    # Nothing to police here any more.  All three copies of the layout -- the
    # subdomain count, parCFDDEMrun.sh's nrProcs and the DEM's own processor grid
    # -- are ``product_of`` the three directions, so `Ctx` recomputes each of
    # them before this function ever runs.  The grid in particular is copied
    # component by component, which is the part that used to need a check: CFDEM
    # pairs rank i with subdomain i, so a grid that mirrored the directions as a
    # set rather than axis by axis was a real, silent failure mode.  It cannot be
    # written that way now -- see the comment on ``dem.processors``.

    # --- coupling interval ------------------------------------------------
    # Nothing to police here any more.  ``couple_every`` is a ``product_of`` the
    # CFD side's ``couplingInterval``, so `Ctx` recomputes it from that value
    # before this function ever runs, and the two can no longer be caught
    # disagreeing.  The interval is typed once, on the coupling tab, and the DEM
    # deck is written from it -- see the comment on ``dem.couple_every``.
    every = ctx.integer("dem.couple_every")

    dem_dt = ctx.num("dem.timestep")
    cfd_dt = ctx.num("run.deltaT")
    if dem_dt and every and cfd_dt:
        period = dem_dt * every
        steps = period / cfd_dt
        whole = abs(steps - round(steps)) < 1e-6
        out.append(check(
            "coupling.divisible", OK if whole else ERROR,
            "Coupling period is divisible by the CFD time step" if whole
            else "Coupling period is not divisible by the CFD time step",
            f"DEM {_fmt(dem_dt)} × {every} = {_fmt(period)} s, / deltaT {_fmt(cfd_dt)} = {_fmt(steps, 8)}"
            if whole else
            f"Coupling period {_fmt(period)} s is not an integer multiple of deltaT "
            f"{_fmt(cfd_dt)} s (= {_fmt(steps, 8)} steps); CFD and DEM will drift "
            "out of phase every period",
            sources=[_src(ctx, "dem.timestep"), _src(ctx, "dem.couple_every"), _src(ctx, "run.deltaT")],
            param_ids=["dem.timestep", "dem.couple_every", "run.deltaT"],
        ))

    # --- particles inside the DEM region ---------------------------------
    # Per particle, since each sits somewhere of its own.  A particle whose
    # coordinates are not readable is skipped rather than reported: the table
    # rule that could not read it is already an unresolved parameter, and one
    # block's rule failing should not put a second, louder error on top.
    placed: List[Dict[str, Any]] = []
    for p in _particles(ctx):
        center = [_pnum(p, a) for a in ("valx", "valy", "valz")]
        if None in center:
            continue
        p["pos"] = center
        placed.append(p)
    lo = [ctx.num("dem.xmin"), ctx.num("dem.ymin"), ctx.num("dem.zmin")]
    hi = [ctx.num("dem.xmax"), ctx.num("dem.ymax"), ctx.num("dem.zmax")]
    if placed and all(v is not None for v in lo + hi):
        outside = [
            f"{_plabel(p)}: " + ", ".join(
                f"{axis}={_fmt(c)} ∉ [{_fmt(a)}, {_fmt(b)}]"
                for axis, c, a, b in zip("xyz", p["pos"], lo, hi)
                if not (a <= c <= b)
            )
            for p in placed
            if any(not (a <= c <= b) for c, a, b in zip(p["pos"], lo, hi))
        ]
        out.append(check(
            "dem.inside", WARN if outside else OK,
            "Particles start outside the DEM region" if outside
            else "Particles start inside the DEM region",
            "; ".join(outside) if outside else
            f"All {len(placed)} particle(s) lie inside the region",
            sources=[_src(ctx, PARTICLES), _src(ctx, "dem.xmin"), _src(ctx, "dem.xmax"),
                     _src(ctx, "dem.ymin"), _src(ctx, "dem.ymax"),
                     _src(ctx, "dem.zmin"), _src(ctx, "dem.zmax")],
            param_ids=[PARTICLES],
        ))

        clipped: List[str] = []
        radii: List[float] = []
        for p in placed:
            radius = _pnum(p, "vald")
            if not radius:
                continue
            radii.append(radius / 2.0)
            axes = [
                axis
                for axis, c, a, b in zip("xyz", p["pos"], lo, hi)
                if c - radius / 2.0 < a or c + radius / 2.0 > b
            ]
            if axes:
                clipped.append(f"{_plabel(p)} ({', '.join(axes)})")
        if radii:
            out.append(check(
                "dem.wall_clearance", WARN if clipped else OK,
                "Particles penetrate the wall" if clipped
                else "Particles do not penetrate the wall",
                "The particle radius pushes " + ", ".join(clipped) + " beyond the "
                "region boundary; the initial configuration already overlaps wall/gran"
                if clipped else
                f"The largest radius {_fmt(max(radii), 4)} m leaves clearance in every direction",
                sources=[_src(ctx, PARTICLES)],
                param_ids=[PARTICLES],
            ))

    # --- particles vs initial water level --------------------------------
    if placed and level is not None:
        wet = [p for p in placed if p["pos"][2] >= level]
        out.append(check(
            "dem.submerged", OK if not wet else INFO,
            "Particles and initial water surface",
            "; ".join(
                f"{_plabel(p)} centre z={_fmt(p['pos'][2], 4)} is above the initial "
                f"water surface {_fmt(level, 4)}"
                for p in wet
            ) + "; it will pass through air before entering the water" if wet else
            f"Every particle centre is below the initial water surface {_fmt(level, 4)}",
            sources=[_src(ctx, PARTICLES), _src(ctx, "mesh.sf.zmax")],
            param_ids=[PARTICLES, "mesh.sf.zmax"],
        ))

    # --- adaptive time step makes its own controls inert ------------------
    adjust = ctx.truthy("run.adjustTimeStep")
    if adjust is False:
        out.append(check(
            "run.adaptivestep", INFO,
            "Adaptive time step is off",
            "adjustTimeStep = no, so maxCo / maxAlphaCo / maxDeltaT take no part "
            "and deltaT stays fixed.",
            sources=[_src(ctx, "run.adjustTimeStep"), _src(ctx, "run.maxCo"),
                     _src(ctx, "run.maxAlphaCo"), _src(ctx, "run.maxDeltaT")],
            param_ids=["run.maxCo", "run.maxAlphaCo", "run.maxDeltaT"],
        ))

    return out


def inactive_params(ctx: Ctx) -> List[str]:
    """Params that currently have no effect, so the UI can grey them out."""
    inactive: List[str] = []
    if ctx.truthy("run.adjustTimeStep") is False:
        inactive += ["run.maxCo", "run.maxAlphaCo", "run.maxDeltaT"]
    method = ctx.raw("mesh.method")
    if method != "simple":
        inactive += ["mesh.prox", "mesh.proy", "mesh.proz"]
    return inactive


def compute(
    resolved: Dict[str, Resolved],
    edits: Optional[List[dict]] = None,
) -> dict:
    ctx = Ctx(resolved, edits)
    metrics = [_resolve_refs(ctx, m) for m in compute_metrics(ctx)]
    consistency = compute_consistency(ctx)
    levels = [m["status"] for m in metrics] + [c["level"] for c in consistency]
    return {
        "metrics": metrics,
        "consistency": consistency,
        "inactive_params": inactive_params(ctx),
        "values": {pid: ctx.raw(pid) for pid in ctx.values},
        "summary": {
            "level": worst(levels),
            "errors": sum(1 for level in levels if level == ERROR),
            "warnings": sum(1 for level in levels if level == WARN),
        },
    }
