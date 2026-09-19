"""The parameter list, and the groups the panels are laid out in.

There is one list, not one per case: any directory holding
``CFD/system/controlDict`` gets the same rules applied to it.  A rule that does
not match its file is simply reported ``unresolved`` by the reader -- it is
shown, explained and left read-only -- so pointing the dashboard at a case it
was not written for degrades into "these N parameters could not be located"
rather than refusing to open it.

Every ``file`` path is relative to the case directory.  ``system/controlDict.foam``
is deliberately absent from the list: it is a stale, inconsistent copy of the
active dictionary and writing to it would silently change nothing.

Every string here is English: this module is the bottom layer, and the panel's
optional Chinese layer lives in the frontend, keyed by parameter id.
"""

from __future__ import annotations

from typing import Dict, List

from .schema import Param, ParamGroup

NUM = r"[0-9.eE+\-]+"
REAL_NUM = r"[0-9.eE+\-]+"


def _scalar(pid: str, group: str, file: str, key: str, **kw) -> Param:
    """Rule for ``key <value>;`` with an optional trailing comment."""
    return Param(
        id=pid,
        group=group,
        file=file,
        pattern=rf"^(?P<pre>\s*{key}\s+)(?P<val>{NUM})(?P<post>\s*;.*)$",
        **kw,
    )


def _triple(pid: str, group: str, file: str, head: str, tail: str, sep, **kw) -> Param:
    """Rule for three numbers inside one line.

    ``head``/``tail`` anchor the fragment, ``sep`` is the pair of patterns
    between x/y and y/z.  Keeping the separators inside the pattern instead of
    simplifying them to ``\\s+`` is what makes each edit land on exactly the
    intended token.
    """
    a, b = sep
    return Param(
        id=pid,
        group=group,
        file=file,
        pattern=(
            rf"^(?P<pre>{head})(?P<valx>{NUM})(?P<mid1>{a})"
            rf"(?P<valy>{NUM})(?P<mid2>{b})(?P<valz>{NUM})(?P<post>{tail})$"
        ),
        **kw,
    )


# --------------------------------------------------------------------------
# 1. mesh
# --------------------------------------------------------------------------

#: The blockMeshDict half of the fluid side: the six extents and the cell
#: counts.  Declaration order doubles as display order, and an extent's two ends
#: are shown on one row: each ``co1`` names its ``co2`` through ``partners``, so
#: the panel puts the min and max boxes side by side and the grid reads one axis
#: per row.  The grouping only works while the named partners follow their owner
#: in this list -- it is declared on the first of the group and the panel folds
#: in whichever params the names point at -- so keep ``co2`` right after its
#: ``co1``.
#:
#: The initial field and the decomposition live in ``FIELD_PARAMS`` below rather
#: than here for one reason: a card follows the order of the parameters in its
#: group, and the physical properties are meant to sit between the mesh and
#: everything else.
MESH_PARAMS: List[Param] = [
    _scalar(
        "mesh.xco1", "fluid", "CFD/system/blockMeshDict", "xco1",
        vtype="float", unit="m", label="Domain x min/max", default=0.0,
        partners=("mesh.xco2",),
        help="blockMeshDict vertex macro; must equal the DEM region's xmin.",
    ),
    _scalar(
        "mesh.yco1", "fluid", "CFD/system/blockMeshDict", "yco1",
        vtype="float", unit="m", label="Domain y min/max", default=0.0,
        partners=("mesh.yco2",),
    ),
    _scalar(
        "mesh.zco1", "fluid", "CFD/system/blockMeshDict", "zco1",
        vtype="float", unit="m", label="Domain z min/max", default=0.2,
        partners=("mesh.zco2",),
        help="The demo case's domain does not start at 0; setFields/DEM coordinates are absolute.",
    ),
    _scalar(
        "mesh.xco2", "fluid", "CFD/system/blockMeshDict", "xco2",
        vtype="float", unit="m", label="Domain x max", default=0.1,
    ),
    _scalar(
        "mesh.yco2", "fluid", "CFD/system/blockMeshDict", "yco2",
        vtype="float", unit="m", label="Domain y max", default=0.1,
    ),
    _scalar(
        "mesh.zco2", "fluid", "CFD/system/blockMeshDict", "zco2",
        vtype="float", unit="m", label="Domain z max", default=0.4,
    ),
    Param(
        id="mesh.cells", group="fluid", file="CFD/system/blockMeshDict",
        pattern=(
            rf"^(?P<pre>\s*hex\s*\(\s*[\d\s]+\)\s*\(\s*)"
            rf"(?P<valx>\d+)(?P<mid1>\s+)(?P<valy>\d+)(?P<mid2>\s+)"
            rf"(?P<valz>\d+)(?P<post>\s*\)\s*.*)$"
        ),
        vtype="int3", label="Cell counts", default=[45, 45, 90],
        compact=True,
        help="Changing this also changes the cell size, cells/diameter and the total cell count.",
    ),
]

# --------------------------------------------------------------------------
# 2. physical properties
# --------------------------------------------------------------------------

_FILE_TP = "CFD/constant/transportProperties"
_FILE_TURB = "CFD/constant/turbulenceProperties"
_FILE_G = "CFD/constant/g"

#: One card for the three ``constant/`` dictionaries that say what the fluid
#: *is*: viscosity and density per phase, surface tension, the turbulence model
#: and gravity.  Three files, but one concern -- splitting them would put three
#: cards of two numbers each next to one another.
_CARD_PHYS = "Physical properties"

#: The viscosity models this dictionary can name.  A case using one that is not
#: listed still opens: the panel appends the value it cannot offer, and the
#: writer only ever refuses a value that was not in the list to begin with.
_VISCOSITY_MODELS = [
    "Newtonian", "CrossPowerLaw", "BirdCarreau", "powerLaw",
    "HerschelBulkley", "generalizedNewtonian", "strainRateFunction",
]

def _transport(pid: str, key: str, phase: str = "", **kw) -> Param:
    """Rule for a dimensioned entry of ``transportProperties``.

    An OpenFOAM dimensioned entry repeats its keyword as the name of the
    dimension set -- ``rho   rho [ 1 -3 0 0 0 0 0 ] 1000;`` -- so the pattern
    pins the repeated keyword and carries the bracketed dimensions along in
    ``pre``; only the number after them is editable.

    ``phase`` pins the rule inside ``water { ... }`` or ``air { ... }``.  Both
    blocks define ``nu`` and ``rho``, so an unscoped rule would be as free to
    land on the air value as on the water one.  ``sigma`` is a top-level entry
    and has no phase.
    """
    return Param(
        id=pid, group="fluid", file=_FILE_TP, card=_CARD_PHYS,
        scope=rf"^{phase}\s*$" if phase else None,
        pattern=(
            rf"^(?P<pre>\s*{key}\s+{key}\s+\[[^\]]*\]\s+)"
            rf"(?P<val>{NUM})(?P<post>\s*;.*)$"
        ),
        **kw,
    )


def _transport_model(pid: str, phase: str, label: str, **kw) -> Param:
    """The phase's ``transportModel`` line, which names a model rather than a
    dimensioned number and so needs its own pattern."""
    return Param(
        id=pid, group="fluid", file=_FILE_TP, card=_CARD_PHYS,
        scope=rf"^{phase}\s*$",
        pattern=r"^(?P<pre>\s*transportModel\s+)(?P<val>\w+)(?P<post>\s*;.*)$",
        vtype="enum", label=label, options=_VISCOSITY_MODELS, default="Newtonian",
        help="A non-Newtonian choice also needs its own coefficients in this block.",
        **kw,
    )


PHYS_PARAMS: List[Param] = [
    _transport_model("phys.water.transportModel", "water", "Water transport model"),
    _transport(
        "phys.water.nu", "nu", "water",
        vtype="float", unit="m2/s", label="Water kinematic viscosity", default=1e-06,
        range=[1e-12, 1.0],
        help="1e-06 m2/s is water at about 20 C; it sets the viscous time scale, "
             "and through it how small deltaT has to be.",
    ),
    _transport(
        "phys.water.rho", "rho", "water",
        vtype="float", unit="kg/m3", label="Water density", default=1000.0,
        range=[1e-06, 1e06],
    ),
    _transport_model("phys.air.transportModel", "air", "Air transport model"),
    _transport(
        "phys.air.nu", "nu", "air",
        vtype="float", unit="m2/s", label="Air kinematic viscosity", default=1.78e-05,
        range=[1e-12, 1.0],
    ),
    _transport(
        "phys.air.rho", "rho", "air",
        vtype="float", unit="kg/m3", label="Air density", default=1.2,
        range=[1e-06, 1e06],
        help="The water/air ratio drives the buoyancy the free surface feels.",
    ),
    _transport(
        "phys.sigma", "sigma",
        vtype="float", unit="N/m", label="Surface tension", default=0.07,
        range=[0.0, 10.0],
        help="The only inter-phase force in interFoam; together with the cell "
             "size it sets the capillary time step limit.",
    ),
    Param(
        id="phys.turbulence", group="fluid", file=_FILE_TURB, card=_CARD_PHYS,
        pattern=r"^(?P<pre>\s*simulationType\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="enum", label="Turbulence model",
        options=["laminar", "RAS", "LES"], default="laminar",
        help="laminar goes with turbulenceModelType=turbulenceProperties in "
             "couplingProperties; RAS and LES need a sub-dictionary of their own "
             "in this file, which the panel does not write.",
    ),
    _triple(
        "phys.g", "fluid", _FILE_G,
        head=r"\s*value\s+\(\s*", tail=r"\s*\)\s*;.*", sep=(r"\s+", r"\s+"),
        card=_CARD_PHYS,
        vtype="float3", unit="m/s2", label="Gravity", default=[0.0, 0.0, -9.81],
        compact=True,
        help="Read every time step; the z component is negative, which is what "
             "makes the water settle and the particle fall through it.",
    ),
]

# --------------------------------------------------------------------------
# 3. initial field and parallel decomposition
# --------------------------------------------------------------------------

def _box_corner(pid: str, axis: int, label: str, **kw) -> Param:
    """Rule for component ``axis`` (0=x, 1=y, 2=z) of the box's *lower* corner.

    ``setFieldsDict`` spells the water box as ``box (x0 y0 z0) ($xmax $ymax $zmax);``
    -- the upper corner goes through macros the three ``*max`` rules below own,
    but the lower one is written out as three bare literals, so no key names them
    and a key-anchored rule cannot reach them.  This builds a rule that anchors on
    the ``box (`` head, skips the components before it without capturing them, and
    captures only this one; the skipped ones are matched as literals rather than
    ``\\S+`` so a line that is not three plain numbers does not match at all.

    All three are ``optional``: a case may write the box differently or omit the
    line, and then the box simply starts at the origin, which is what the solver
    does with a missing component -- hence ``default_when_absent``, so the panel
    shows 0 rather than a blank and the water-depth metric still computes.
    """
    before = r"\s+".join([NUM] * axis)
    after = r"\s+".join([NUM] * (2 - axis))
    pre = r"\s*box\s+\(\s*" + (before + r"\s+" if axis else "")
    post = (r"\s+" + after if after else "") + r"\s*\).*$"
    return Param(
        id=pid,
        group="fluid",
        file="CFD/system/setFieldsDict",
        pattern=rf"^(?P<pre>{pre})(?P<val>{NUM})(?P<post>{post})",
        vtype="float",
        unit="m",
        label=label,
        default=0.0,
        optional=True,
        default_when_absent=True,
        **kw,
    )


#: Neither is a property of the mesh, but both are per-run geometry that is
#: duplicated elsewhere -- the water box against the domain, the decomposition
#: against the DEM's own processor grid -- which is what the panel compares.
#:
#: The box is one volume with six bounds, so each axis gets a row: the lower
#: bound names its upper through ``partners`` and the two boxes share a line,
#: exactly as the domain extents above do.  The lower/upper ids stay separate --
#: the coverage checks read each bound on its own -- it is only the row that is
#: shared, which is also why the upper bound of an axis is declared right after
#: its lower one rather than in a block of its own.
FIELD_PARAMS: List[Param] = [
    _box_corner(
        "mesh.sf.xmin", 0, "Water box x lower/upper",
        partners=("mesh.sf.xmax",),
    ),
    _scalar(
        "mesh.sf.xmax", "fluid", "CFD/system/setFieldsDict", "xmax",
        vtype="float", unit="m", label="Initial water box x upper bound", default=0.101,
        help="0.101 is slightly larger than the 0.1 domain width, for full coverage; only >= xco2 is required.",
    ),
    _box_corner(
        "mesh.sf.ymin", 1, "Water box y lower/upper",
        partners=("mesh.sf.ymax",),
    ),
    _scalar(
        "mesh.sf.ymax", "fluid", "CFD/system/setFieldsDict", "ymax",
        vtype="float", unit="m", label="Initial water box y upper bound", default=0.101,
    ),
    _box_corner(
        "mesh.sf.zmin", 2, "Water box z lower/upper",
        partners=("mesh.sf.zmax",),
        help="The box's own floor, so together with zmax it sets the initial water depth; it need not sit on the domain floor.",
    ),
    _scalar(
        "mesh.sf.zmax", "fluid", "CFD/system/setFieldsDict", "zmax",
        vtype="float", unit="m", label="Initial water box z upper bound", default=0.301,
        help="The initial water surface, and so whether the particle starts underwater; "
             "it may sit above the domain lid to start the case full of water.",
    ),
    #: One decomposition, three numbers: the x count names y and z through
    #: ``partners`` so all three share a row, as the box's bounds share one per
    #: axis.  Keeping them side by side is the point -- the product on the line
    #: below only looks right when its three factors are read together.
    _scalar(
        "mesh.prox", "fluid", "CFD/system/decomposeParDict", "prox",
        vtype="int", label="Decomposition x|y|z", default=1, range=[1, 512],
        partners=("mesh.proy", "mesh.proz"),
    ),
    _scalar(
        "mesh.proy", "fluid", "CFD/system/decomposeParDict", "proy",
        vtype="int", label="Decomposition in y", default=1, range=[1, 512],
    ),
    _scalar(
        "mesh.proz", "fluid", "CFD/system/decomposeParDict", "proz",
        vtype="int", label="Decomposition in z", default=4, range=[1, 512],
    ),
    #: Derived, not an input: the three directions above are the single source of
    #: truth, so this line is recomputed and written by the server on every plan.
    #: No ``range`` -- it is a product, and clamping it would block the sync.
    _scalar(
        "mesh.numberOfSubdomains", "fluid", "CFD/system/decomposeParDict",
        "numberOfSubdomains",
        vtype="int", label="Total subdomains", default=4,
        product_of=("mesh.prox", "mesh.proy", "mesh.proz"),
        help="Derived from the product of the x/y/z decomposition; shown read-only and synced to the file on write.",
    ),
    Param(
        id="mesh.method", group="fluid", file="CFD/system/decomposeParDict",
        pattern=r"^(?P<pre>\s*method\s+)(?P<val>\w+)(?P<post>\s*;.*)$",
        vtype="enum", label="Decomposition method",
        options=["simple", "hierarchical", "scotch", "metis", "manual"],
        default="simple",
    ),
]

# --------------------------------------------------------------------------
# 4. run control
# --------------------------------------------------------------------------

RUN_PARAMS: List[Param] = [
    #: The run's span, written as two lines and shown as one row: the start names
    #: the end through ``partners``, the same treatment the domain extents get.
    _scalar(
        "run.startTime", "fluid", "CFD/system/controlDict", "startTime",
        vtype="float", unit="s", label="Start/end time", default=0.0,
        partners=("run.endTime",),
    ),
    _scalar(
        "run.endTime", "fluid", "CFD/system/controlDict", "endTime",
        vtype="float", unit="s", label="End time", default=0.3,
        help="Physical run length; together with deltaT it sets the number of CFD steps.",
    ),
    _scalar(
        "run.deltaT", "fluid", "CFD/system/controlDict", "deltaT",
        vtype="float", unit="s", label="CFD time step", default=0.0002,
        help="Fixed step when adjustTimeStep = no; the coupling period must be an integer multiple of it.",
    ),
    #: How often a frame lands, which is a fact about the step just above it --
    #: so it is declared beside the step, ahead of the `writeControl` enum that
    #: only says what the interval is counted in.
    _scalar(
        "run.writeInterval", "fluid", "CFD/system/controlDict", "writeInterval",
        vtype="float", unit="s", label="Write interval", default=0.01,
        help="When writeControl is a time unit, frames = endTime / writeInterval.",
    ),
    Param(
        id="run.writeControl", group="fluid", file="CFD/system/controlDict",
        pattern=r"^(?P<pre>\s*writeControl\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="enum", label="Write control",
        options=["timeStep", "runTime", "adjustableRunTime", "clockTime", "cpuTime"],
        default="adjustableRunTime",
        help="The trailing ;//timeStep;// is a historical alternative; it is preserved verbatim on write.",
    ),
    _scalar(
        "run.purgeWrite", "fluid", "CFD/system/controlDict", "purgeWrite",
        vtype="int", label="Time directories kept", default=0, range=[0, 10000],
    ),
    _scalar(
        "run.writePrecision", "fluid", "CFD/system/controlDict", "writePrecision",
        vtype="int", label="Write precision", default=12, range=[1, 20],
    ),
    Param(
        id="run.runTimeModifiable", group="fluid", file="CFD/system/controlDict",
        pattern=r"^(?P<pre>\s*runTimeModifiable\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="bool", label="Modifiable at runtime", default=False,
        help="Note that it is only read at start-up; a server-side write is always allowed.",
    ),
    Param(
        id="run.adjustTimeStep", group="fluid", file="CFD/system/controlDict",
        pattern=r"^(?P<pre>\s*adjustTimeStep\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="bool", label="Adaptive time step", default=False,
        bool_true="yes", bool_false="no",
        help="When no, maxCo / maxAlphaCo / maxDeltaT have no effect at all.",
    ),
    _scalar(
        "run.maxCo", "fluid", "CFD/system/controlDict", "maxCo",
        vtype="float", label="Max Courant number", default=0.5,
        help="Takes effect only when adjustTimeStep = yes.",
    ),
    _scalar(
        "run.maxAlphaCo", "fluid", "CFD/system/controlDict", "maxAlphaCo",
        vtype="float", label="Max interface Courant number", default=0.5,
        help="Takes effect only when adjustTimeStep = yes.",
    ),
    _scalar(
        "run.maxDeltaT", "fluid", "CFD/system/controlDict", "maxDeltaT",
        vtype="float", unit="s", label="Max time step limit", default=0.01,
        help="Takes effect only when adjustTimeStep = yes.",
    ),
    #: The launch count is the subdomain count under another name -- `mpirun -np`
    #: has to equal the number of subdomains -- so it is the same product as
    #: ``mesh.numberOfSubdomains``, written into a second file.  Derived from the
    #: three directions rather than from `mesh.numberOfSubdomains`: the same
    #: number either way, but sources that are real inputs, so a pending edit
    #: reaches it directly and there is no product-of-a-product to resolve.  No
    #: ``range`` -- it is a product, and clamping it would block the sync.
    Param(
        id="run.nrProcs", group="fluid", file="parCFDDEMrun.sh",
        pattern=r'^(?P<pre>\s*nrProcs=")(?P<val>\d+)(?P<post>".*)$',
        vtype="int", label="MPI process count", default=4,
        product_of=("mesh.prox", "mesh.proy", "mesh.proz"),
        help="Passed to mpirun -np and must equal the total subdomain count; derived from the product of the x/y/z decomposition and synced to this file on write.",
    ),
    Param(
        id="run.solverName", group="fluid", file="parCFDDEMrun.sh",
        pattern=r'^(?P<pre>\s*solverName=")(?P<val>[^"]*)(?P<post>".*)$',
        vtype="string", label="Solver executable", default="solverInterIB20",
        readonly=True,
    ),
]

# --------------------------------------------------------------------------
# 5. coupling and immersed boundary
# --------------------------------------------------------------------------

_FILE_CP = "CFD/constant/couplingProperties"


def _cp(pid: str, key: str, **kw) -> Param:
    return _scalar(pid, "coupling", _FILE_CP, key, **kw)


COUPLING_PARAMS: List[Param] = [
    Param(
        id="coupling.verbose", group="coupling", file=_FILE_CP,
        pattern=r"^(?P<pre>\s*verbose\s+)(?P<val>\S+)(?P<post>\s*;.*)$",
        vtype="bool", label="Verbose output", default=True,
    ),
    Param(
        id="coupling.modelType", group="coupling", file=_FILE_CP,
        pattern=r"^(?P<pre>\s*modelType\s+)(?P<val>\S+)(?P<post>\s*;.*)$",
        vtype="enum", label="Coupling model", options=["none", "A", "B"], default="none",
    ),
    _cp(
        "coupling.couplingInterval", "couplingInterval",
        vtype="int", label="Coupling interval (DEM steps)", default=100, range=[1, 1000000],
        help="Must equal couple_every in in.liggghts_run.",
    ),
    _cp(
        "coupling.depth", "depth",
        vtype="int", label="Particle search depth", default=0, range=[0, 100],
    ),
    Param(
        id="coupling.voidFractionModel", group="coupling", file=_FILE_CP,
        pattern=r"^(?P<pre>\s*voidFractionModel\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="enum", label="Void fraction model",
        options=["IB", "bigParticle", "centre", "divided"], default="IB",
    ),
    Param(
        id="coupling.locateModel", group="coupling", file=_FILE_CP,
        pattern=r"^(?P<pre>\s*locateModel\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="enum", label="Locate model", options=["engineIB", "standard"], default="engineIB",
    ),
    Param(
        id="coupling.meshMotionModel", group="coupling", file=_FILE_CP,
        pattern=r"^(?P<pre>\s*meshMotionModel\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="enum", label="Mesh motion model",
        options=["noMeshMotion", "meshMotion"], default="noMeshMotion",
    ),
    Param(
        id="coupling.dataExchangeModel", group="coupling", file=_FILE_CP,
        pattern=r"^(?P<pre>\s*dataExchangeModel\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="enum", label="Data exchange model",
        options=["twoWayMPI", "twoWayFiles"], default="twoWayMPI",
    ),
    Param(
        id="coupling.turbulenceModelType", group="coupling", file=_FILE_CP,
        pattern=r"^(?P<pre>\s*turbulenceModelType\s+)(?P<val>[^\s;]+)(?P<post>\s*;.*)$",
        vtype="enum", label="Turbulence model file",
        options=["turbulenceProperties", "RASProperties", "LESProperties"],
        default="turbulenceProperties",
    ),
    # --- IBProps block: maxCellsPerParticle/alphaMin also exist in
    # bigParticleProps and dividedProps, hence the scope pinning.
    Param(
        id="coupling.IBProps.maxCellsPerParticle", group="coupling", file=_FILE_CP,
        scope=r"^IBProps\s*$", scope_style="brace",
        pattern=r"^(?P<pre>\s*maxCellsPerParticle\s+)(?P<val>\d+)(?P<post>\s*;.*)$",
        vtype="int", label="IB max cells per particle", default=10000, range=[1, 100000000],
    ),
    Param(
        id="coupling.IBProps.alphaMin", group="coupling", file=_FILE_CP,
        scope=r"^IBProps\s*$", scope_style="brace",
        pattern=rf"^(?P<pre>\s*alphaMin\s+)(?P<val>{REAL_NUM})(?P<post>\s*;.*)$",
        vtype="float", label="IB alphaMin", default=0.30, range=[0.0, 1.0],
        help="alphaMin appears four times in the file; this rule is pinned inside the IBProps block.",
    ),
    Param(
        id="coupling.IBProps.scaleUpVol", group="coupling", file=_FILE_CP,
        scope=r"^IBProps\s*$", scope_style="brace",
        pattern=rf"^(?P<pre>\s*scaleUpVol\s+)(?P<val>{REAL_NUM})(?P<post>\s*;.*)$",
        vtype="float", label="IB volume scale factor", default=1.0, range=[0.0, 100.0],
    ),
    # --- the immersed-boundary force integration -----------------------------
    #: The exponent of the void-fraction map the cell weight comes from:
    #: forceInterIB weights a cell at 1 - void**voidExp.  The solver rejects an
    #: exponent below 0, so that is where the range starts.  1 means the weight
    #: is the exact fluid fraction, which is the indicator function the
    #: divergence theorem needs to turn the volume integral back into a surface
    #: integral over the particle; above 1 the interface cells count for more,
    #: and 0 flattens the weight to zero everywhere, i.e. no IB force at all.
    #: 2 is the value the decks are tuned around.
    Param(
        id="coupling.voidExp", group="coupling", file=_FILE_CP,
        scope=r"^forceInterIBProps\s*$", scope_style="brace",
        pattern=rf"^(?P<pre>\s*voidExp\s+)(?P<val>{REAL_NUM})(?P<post>\s*;.*)$",
        vtype="float", label="IB void exponent (flow-regime dependent)",
        default=2.0, range=[0.0, 10.0],
        help="forceInterIB weights each cell of the particle's cell list at "
             "1 - void**voidExp. 1 gives the exact fluid fraction, which is the "
             "indicator the divergence theorem needs -- the cell list is larger than "
             "the particle, and only this weight shrinks the volume integral back onto "
             "the particle. The exponent is a flow-regime knob: the interface cells it "
             "up-weights sit in the diffuse transition band around the particle, and how "
             "much of that band has to count depends on the regime the case runs in, not "
             "on the grid alone, so the value has to be retuned when Re changes rather "
             "than carried across regimes. Going down to 0 is allowed and is a valid "
             "degenerate setting: void**0 is 1 in every cell, so the weight is "
             "identically 0 and the particles feel no IB force; the solver only refuses "
             "a negative exponent, which flips the map and gives near-solid cells a "
             "weight above 1. 2 is the value the decks here are tuned around.",
        optional=True,
    ),
    # --- coefficients the solver has a default for ---------------------------
    #: These three are read only when they are there: the coupling model falls
    #: back on the numbers in ``default`` when the line is missing, so a case is
    #: free to leave any of them out and the deck still runs.  Which is what
    #: ``Param.optional`` says -- absent reads as a grey "Optional" row rather
    #: than the red "Not found" that would ask for a line nobody needs.  Left
    #: out, none of them is written.
    _cp(
        "coupling.Coe_V_local", "Coe_V_local",
        vtype="float", label="IB local velocity coefficient", default=0.6, range=[0.0, 1.0],
        help="Used when the particle is in the free-surface region (0.02 < alpha < 0.98).",
        optional=True,
    ),
    _cp(
        "coupling.Coe_V_global", "Coe_V_global",
        vtype="float", label="IB global velocity coefficient", default=0.85, range=[0.0, 1.0],
        help="Used outside the free-surface region; a change alters particle forces and trajectory directly.",
        optional=True,
    ),
    #: This one is a 0/1 flag, not a quantity, so it reads as a switch rather
    #: than as a box you can type any number into.  The spelling is the file's
    #: own ``1``/``0`` -- not the usual ``on``/``off`` of ``bool_true`` /
    #: ``bool_false`` -- so leaving the switch alone leaves its line byte-identical.
    _cp(
        "coupling.doDivCor", "doDivCor",
        vtype="bool", label="Divergence correction", default=True,
        bool_true="1", bool_false="0",
        help="1 projects the corrected particle velocity back onto a divergence-free field; requires phiIB in 0/phiIB and fvSolution.",
        optional=True,
    ),
]

# --------------------------------------------------------------------------
# 6. DEM particles
# --------------------------------------------------------------------------

_FILE_DEM = "DEM/in.liggghts_run"

#: The walls live in the same LIGGGHTS input as the particles, but they are a
#: separate concern (they mirror the CFD domain), so they get their own card.
_CARD_WALL = "Wall settings"

#: How the particles come into existence.  The two tutorial cases use two
#: mutually exclusive ways -- a single ``create_atoms``/``set atom`` pair, or a
#: ``particletemplate/multisphere`` + ``insert/pack`` chain -- so the card has to
#: show both without reporting the route a case does not use as a broken rule.
_CARD_CREATE = "Particle type and creation"

#: LIGGGHTS ``variable <name> equal <value>`` definitions.  They are constants
#: for the rest of the deck rather than commands in their own right, so they get
#: their own card instead of being mixed in with the region and fix lines they
#: feed.
_CARD_VAR = "Variables"

#: The two rates that decide how much of the run leaves the process: what
#: LIGGGHTS prints and what it dumps.  Neither is a particle property, and the
#: dump interval is not even a line of its own -- it is the ``outSteps`` variable
#: the ``dump`` command reads -- so the pair is pulled out of Variables into a
#: card of its own rather than left filed under geometry.
_CARD_OUT = "Output control"


def _var(pid: str, key: str, card: str = _CARD_VAR, **kw) -> Param:
    return Param(
        id=pid, group="particle", file=_FILE_DEM, card=card,
        pattern=rf"^(?P<pre>\s*variable\s+{key}\s+equal\s+)(?P<val>{NUM})(?P<post>.*)$",
        **kw,
    )


def _wall(pid: str, fix_name: str, plane: str, **kw) -> Param:
    """One LIGGGHTS wall plane, switchable on and off.

    The pattern pins both the fix name and the plane keyword, so the only token
    that can move is the coordinate itself.  The optional ``flag`` group makes
    the ``#`` that comments the whole line part of the match: dropping it
    (enable) puts the wall back in the deck, adding it (disable) takes it out,
    and the coordinate stays readable either way -- which is what lets the
    domain consistency check skip a wall that is not there.
    """
    return Param(
        id=pid, group="particle", file=_FILE_DEM, card=_CARD_WALL,
        pattern=(
            rf"^(?P<flag>#\s*)?(?P<pre>\s*fix\s+{fix_name}\s+.*\s+{plane}\s+)"
            rf"(?P<val>{NUM})(?P<post>\s*)$"
        ),
        vtype="float", unit="m", toggle=True, **kw,
    )


def _ms(pid: str, head: str, val: str, tail: str, **kw) -> Param:
    """One rule of the multisphere (``particletemplate`` + ``insert/pack``) route.

    Every anchor pins a keyword or a whole ``fix <name> ...`` at the start of the
    line.  That is what keeps the chain -- which spans three ``fix`` blocks -- to
    exactly one match each, and what keeps the commented-out alternatives
    (``# scale``, ``# fix ins all insert/pack/custom ...``) out: ``\\s*`` cannot
    eat a ``#``.
    """
    return Param(
        id=pid, group="particle", file=_FILE_DEM, card=_CARD_CREATE,
        alt="multisphere",
        pattern=rf"^(?P<pre>{head})(?P<val>{val})(?P<post>{tail})$",
        **kw,
    )


def _gen_region(axis: str, side: str, **kw) -> Param:
    """One number on the ``region generate_re block xlo xhi ylo yhi zlo zhi`` line.

    The six numbers alternate by axis, so "the three lower bounds" would run into
    x's upper bound; the only way to land on a single number is to count how many
    precede it.  The numbers after it go into ``post`` (which is never written),
    otherwise the trailing ``&`` would only ever land on the last one.
    """
    order = ["xmin", "xmax", "ymin", "ymax", "zmin", "zmax"]
    before = order.index(f"{axis}{side}")
    after = len(order) - 1 - before
    head = (r"\s*region\s+generate_re\s+block\s+"
            + (rf"(?:{NUM}\s+){{{before}}}" if before else ""))
    tail = (rf"(?:\s+{NUM}){{{after}}}" if after else "") + r"\s*&.*"
    return Param(
        id=f"dem.ms.reg.{axis}{side}", group="particle", file=_FILE_DEM,
        card=_CARD_CREATE, alt="multisphere",
        pattern=rf"^(?P<pre>{head})(?P<val>{NUM})(?P<post>{tail})$", **kw,
    )


DEM_PARAMS: List[Param] = [
    #: Not an input either, and the order matters: CFDEM pairs DEM rank i with
    #: CFD subdomain i, so this grid has to mirror the decomposition axis by
    #: axis, not merely multiply out to the same total.  Typed once, in
    #: decomposeParDict, and copied here on write -- a hand-write is rejected.
    _triple(
        "dem.processors", "particle", _FILE_DEM,
        head=r"\s*processors\s+", tail=r"\s*", sep=(r"\s+", r"\s+"),
        vtype="int3", label="Process layout", default=[1, 1, 4], compact=True,
        product_of=("mesh.prox", "mesh.proy", "mesh.proz"),
        help="Follows Decomposition in x/y/z in decomposeParDict, which is where the grid is typed; written into this deck on apply.",
    ),
    #: Not an input: this is ``couplingInterval`` under the DEM deck's own name,
    #: and the two files have to carry the same number or every coupling step
    #: covers a different physical time on each side.  LIGGGHTS decides nothing
    #: here, so the interval is typed once, on the coupling tab, and the writer
    #: puts the line into the deck -- a hand-write of this one is rejected.  The
    #: label stays the LIGGGHTS keyword because that is what the file says.
    Param(
        id="dem.couple_every", group="particle", file=_FILE_DEM,
        pattern=(
            r"^(?P<pre>\s*fix\s+cfd\s+all\s+couple/cfd\s+couple_every\s+)"
            r"(?P<val>\d+)(?P<post>\s+mpi.*)$"
        ),
        vtype="int", label="couple_every (DEM steps)", default=100, range=[1, 1000000],
        product_of=("coupling.couplingInterval",),
        help="Follows Coupling interval (DEM steps) in couplingProperties, which is where it is typed; written into this deck on apply.",
    ),
    # --- variables ----------------------------------------------------------
    #: The DEM region is the same six extents as the mesh's, so each axis gets
    #: the same one-row treatment: the min names its max through ``partners``.
    #: The two ids stay separate -- the domain consistency check reads each one
    #: on its own -- it is only the row that is shared.
    _var("dem.xmin", "xmin", vtype="float", unit="m", label="Region x min/max",
         default=0.0, partners=("dem.xmax",)),
    _var("dem.xmax", "xmax", vtype="float", unit="m", label="Region x max", default=0.1),
    _var("dem.ymin", "ymin", vtype="float", unit="m", label="Region y min/max",
         default=0.0, partners=("dem.ymax",)),
    _var("dem.ymax", "ymax", vtype="float", unit="m", label="Region y max", default=0.1),
    _var("dem.zmin", "zmin", vtype="float", unit="m", label="Region z min/max",
         default=0.2, partners=("dem.zmax",)),
    _var("dem.zmax", "zmax", vtype="float", unit="m", label="Region z max", default=0.4),
    _var(
        "dem.timestep", "timestep", vtype="float", unit="s", label="DEM time step",
        default=0.00001,
        help="DEM time step × couple_every = coupling period, which must be divisible by deltaT.",
    ),
    # --- particle type and creation ----------------------------------------
    #: Deliberately *not* ``alt``: the two cases differ in what they create, but
    #: both integrate their particles, so this line is live either way -- it is
    #: the integral counterpart of which kind of particle is being created.
    Param(
        id="dem.integr", group="particle", file=_FILE_DEM, card=_CARD_CREATE,
        pattern=r"^(?P<pre>\s*fix\s+integr\s+all\s+)(?P<val>\S+)(?P<post>\s*)$",
        vtype="enum", label="Integration",
        options=["multisphere", "nve/sphere"], default="nve/sphere",
        help="Use nve/sphere for a single sphere and multisphere for a clump.",
    ),
    # -- single-sphere route: create_atoms + set atom -----------------------
    _triple(
        "dem.pos", "particle", _FILE_DEM,
        head=r"\s*create_atoms\s+1\s+single\s+", tail=r"\s+units\s+box.*",
        sep=(r"\s+", r"\s+"),
        card=_CARD_CREATE, alt="single",
        vtype="float3", unit="m", label="Initial position", default=[0.05, 0.05, 0.33],
        compact=True,
        help="Absolute coordinates; should lie inside the DEM region and usually below the water surface.",
    ),
    Param(
        id="dem.diameter", group="particle", file=_FILE_DEM,
        card=_CARD_CREATE, alt="single",
        pattern=(
            rf"^(?P<pre>\s*set\s+atom\s+1\s+diameter\s+)(?P<val>{NUM})"
            rf"(?P<post>\s+density\s+{NUM}\s+vx.*)$"
        ),
        vtype="float", unit="m", label="Diameter", default=0.0167,
        help="Determines cells/diameter and whether the particle spans mesh cells.",
    ),
    Param(
        id="dem.density", group="particle", file=_FILE_DEM,
        card=_CARD_CREATE, alt="single",
        pattern=(
            rf"^(?P<pre>\s*set\s+atom\s+1\s+diameter\s+{NUM}\s+density\s+)(?P<val>{NUM})"
            rf"(?P<post>\s+vx.*)$"
        ),
        vtype="float", unit="kg/m3", label="Density", default=1500,
    ),
    _triple(
        "dem.velocity", "particle", _FILE_DEM,
        head=rf"\s*set\s+atom\s+1\s+diameter\s+{NUM}\s+density\s+{NUM}\s+vx\s+",
        tail=r"\s*",
        sep=(r"\s+vy\s+", r"\s+vz\s+"),
        card=_CARD_CREATE, alt="single",
        vtype="float3", unit="m/s", label="Initial velocity", default=[0.0, 0.0, 0.0],
        compact=True,
    ),
    # -- multisphere route: particletemplate/multisphere + insert/pack -------
    _ms(
        "dem.ms.seed", r"\s*fix\s+pts1\s+all\s+particletemplate/multisphere\s+",
        NUM, r"\s*&.*",
        vtype="int", label="Template random seed", default=15485863,
        help="Random seed used when generating the clump template.",
    ),
    _ms(
        "dem.ms.atom_type", r"\s*atom_type\s+", NUM, r"\s*&.*",
        vtype="int", label="Atom type", default=1,
        help="Atom type used by template-generated particles; must match the wall/pair parameters.",
    ),
    _ms(
        "dem.ms.density", r"\s*density\s+constant\s+", NUM, r"\s*&.*",
        vtype="float", unit="kg/m3", label="Density", default=1010,
    ),
    _ms(
        "dem.ms.nspheres", r"\s*nspheres\s+", r"\d+", r"\s*&.*",
        vtype="int", label="Spheres per clump", default=13, range=[1, 1000000],
        help="How many spheres make up one clump.",
    ),
    _ms(
        "dem.ms.ntry", r"\s*ntry\s+", r"\d+", r"\s*&.*",
        vtype="int", label="Template attempts", default=1000000,
    ),
    _ms(
        "dem.ms.spheres", r"\s*spheres\s+file\s+", r"\S+", r"\s*&.*",
        vtype="string", label="Sphere layout file", default="../DEM/data/fish",
        help="Template file describing the sphere arrangement inside a clump.",
    ),
    _ms(
        "dem.ms.scale", r"\s*scale\s+", NUM, r"\s*&.*",
        vtype="float", label="Scale factor", default=0.0004,
        help="Template scaling; together with the template file it determines the actual particle size.",
    ),
    _ms(
        "dem.ms.type", r"\s*type\s+", NUM, r"\s*$",
        vtype="int", label="Template output type", default=1,
    ),
    _ms(
        "dem.ms.dist_seed", r"\s*fix\s+pdd1\s+all\s+particledistribution/discrete\s+",
        r"\d+", r"\s*&.*",
        vtype="int", label="Distribution random seed", default=15485867,
    ),
    _ms(
        "dem.ms.fraction", r"\s*1\s+pts1\s+", NUM, r"\s*$",
        vtype="float", label="Distribution volume fraction", default=1.0, readonly=True,
        note="There is only one template, so the volume fraction must be 1.",
    ),
    _gen_region("x", "min", vtype="float", unit="m", label="Generation region x min", default=0.04),
    _gen_region("x", "max", vtype="float", unit="m", label="Generation region x max", default=0.06),
    _gen_region("y", "min", vtype="float", unit="m", label="Generation region y min", default=0.04),
    _gen_region("y", "max", vtype="float", unit="m", label="Generation region y max", default=0.06),
    _gen_region("z", "min", vtype="float", unit="m", label="Generation region z min", default=0.32),
    _gen_region("z", "max", vtype="float", unit="m", label="Generation region z max", default=0.34),
    _ms(
        "dem.ms.insert_seed", r"\s*fix\s+ins1\s+all\s+insert/pack\s+seed\s+",
        r"\d+", r"\s*&.*",
        vtype="int", label="Insertion random seed", default=32452843,
    ),
    _ms(
        "dem.ms.maxattempt", r"\s*maxattempt\s+", r"\d+",
        r"\s+insert_every\s+\S+\s*&.*",
        vtype="int", label="Max attempts", default=100000,
    ),
    _ms(
        "dem.ms.insert_every", r"\s*maxattempt\s+\d+\s+insert_every\s+", r"\S+",
        r"\s*&.*",
        vtype="string", label="Insertion frequency", default="once",
        help="once means insert a single time at the beginning.",
    ),
    _ms(
        "dem.ms.orientation", r"\s*orientation\s+", r"\S+", r"\s*&.*",
        vtype="enum", label="Initial orientation", options=["random", "fixed"], default="random",
    ),
    _triple(
        "dem.ms.vel", "particle", _FILE_DEM,
        head=r"\s*vel\s+constant\s+", tail=r"\s*&.*", sep=(r"\s+", r"\s+"),
        card=_CARD_CREATE, alt="multisphere",
        vtype="float3", unit="m/s", label="Insertion initial velocity", default=[0.0, 0.0, 0.0],
    ),
    _ms(
        "dem.ms.overlapcheck", r"\s*overlapcheck\s+", r"\w+",
        r"\s+all_in\s+\w+\s*&.*",
        vtype="bool", label="Overlap check", default=True,
        bool_true="yes", bool_false="no",
    ),
    _ms(
        "dem.ms.all_in", r"\s*overlapcheck\s+\w+\s+all_in\s+", r"\w+", r"\s*&.*",
        vtype="bool", label="Must all fall inside the region", default=False,
        bool_true="yes", bool_false="no",
        help="no allows a particle to partly fall outside the generation region.",
    ),
    _ms(
        "dem.ms.region", r"\s*region\s+", r"\S+", r"\s*&\s*$",
        vtype="string", label="Insertion target region name", default="generate_re",
        help="Must correspond to the region defined by the region generate_re block above.",
    ),
    _ms(
        "dem.ms.particles_in_region", r"\s*particles_in_region\s+", r"\d+", r"\s*&.*",
        vtype="int", label="Particles in region", default=1,
    ),
    _ms(
        "dem.ms.ntry_mc", r"\s*ntry_mc\s+", r"\d+", r"\s*$",
        vtype="int", label="Monte Carlo attempts", default=10000,
    ),
    # Walls mirror the CFD domain; they are the DEM side of the domain
    # consistency check.  One axis is one row, as the domain extents are: the
    # lower wall names the upper through ``partners``, and each box keeps its
    # own Off/On control beside it -- a deck routinely drops just one of the
    # pair.  The label is the axis alone (the card says what the rows are, and
    # the deck's own ``xplane``/``yplane``/``zplane`` keyword is already there),
    # which is what buys the second switch its room in one track: "bound" would
    # not fit beside two boxes and their two Off/On pairs in one column.
    _wall("dem.wall.x1", "xwalls1", "xplane", label="x lower/upper",
          partners=("dem.wall.x2",)),
    _wall("dem.wall.x2", "xwalls2", "xplane", label="x upper bound"),
    _wall("dem.wall.y1", "ywalls1", "yplane", label="y lower/upper",
          partners=("dem.wall.y2",)),
    _wall("dem.wall.y2", "ywalls2", "yplane", label="y upper bound"),
    _wall("dem.wall.z1", "zwalls1", "zplane", label="z lower/upper",
          partners=("dem.wall.z2",)),
    _wall("dem.wall.z2", "zwalls2", "zplane", label="z upper bound"),
    # --- screen output and dumping -----------------------------------------
    #: ``thermo`` is anchored by the whitespace after the keyword, which is what
    #: keeps it off ``thermo_style``, ``thermo_modify`` and ``thermo_log`` -- the
    #: three lines that begin with the same eight characters.
    Param(
        id="dem.thermo", group="particle", file=_FILE_DEM, card=_CARD_OUT,
        pattern=r"^(?P<pre>\s*thermo\s+)(?P<val>\d+)(?P<post>\s*)$",
        vtype="int", label="DEM screen print interval (steps)", default=1000,
        range=[0, 100000000],
        help="How often LIGGGHTS writes a thermo line to the screen and the log; "
             "0 turns that output off entirely.",
    ),
    #: The dump period, named by the variable the ``dump`` line interpolates.
    #: Editing the variable rather than the command is the only way to keep the
    #: two in step: ``dump dmp all custom ${outSteps} ...`` would go on reading
    #: whatever the variable holds.
    _var(
        "dem.outSteps", "outSteps", card=_CARD_OUT,
        vtype="int", label="DEM dump interval (steps)", default=1000,
        range=[1, 100000000],
        help="How often a dump frame is written; in physical time that is this "
             "many DEM steps, i.e. timestep × outSteps.",
    ),
]

ALL_PARAMS: List[Param] = (
    MESH_PARAMS + PHYS_PARAMS + FIELD_PARAMS + RUN_PARAMS + COUPLING_PARAMS + DEM_PARAMS
)


def _files_of(params: List[Param]) -> List[str]:
    seen: List[str] = []
    for p in params:
        if p.file not in seen:
            seen.append(p.file)
    return seen


#: Every dictionary the reader opens, in first-appearance order.  A file a case
#: does not have is not an error: it resolves to a load failure and its params
#: come back ``unresolved``, which is what the panel reports.
FILES: List[str] = _files_of(ALL_PARAMS)

#: Panels are split by physics, not by file: the fluid side spans five files
#: but a single quantity (domain size, parallel layout) is repeated across them,
#: and that duplication is exactly what the panel is meant to make visible.
GROUPS: List[ParamGroup] = [
    ParamGroup(
        id="fluid", label="Fluid",
        blurb=(
            "blockMeshDict · transportProperties · turbulenceProperties · g · "
            "setFieldsDict · decomposeParDict · controlDict · parCFDDEMrun.sh"
        ),
        params=MESH_PARAMS + PHYS_PARAMS + FIELD_PARAMS + RUN_PARAMS,
    ),
    ParamGroup(
        id="particle", label="Particle",
        blurb="in.liggghts_run",
        params=DEM_PARAMS,
    ),
    ParamGroup(
        id="coupling", label="Coupling",
        blurb="couplingProperties · immersed boundary and coupling interval",
        params=COUPLING_PARAMS,
    ),
    #: Not a parameter group at all: the case's ``step*.sh`` pipeline, each
    #: script against what it has already produced.  It carries no params, and
    #: the panel renders it from ``/api/steps`` instead of ``/api/case`` -- but
    #: it is a tab like any other, so it is declared beside the other three.
    ParamGroup(
        id="steps", label="Steps", kind="scripts",
        blurb="step*.sh · what each script has already produced",
        params=[],
    ),
]

#: What each dictionary is *for*, so a card header can read
#: `Mesh and domain (CFD/system/blockMeshDict)` instead of a bare path.  The UI
#: falls back to the path alone, so a file that is not listed still renders.
FILE_LABELS: Dict[str, str] = {
    "CFD/system/blockMeshDict": "Mesh and domain",
    "CFD/system/setFieldsDict": "Initial field (water box)",
    "CFD/system/decomposeParDict": "Parallel decomposition",
    "CFD/system/controlDict": "Solver control",
    "CFD/constant/transportProperties": "Viscosity, density and surface tension",
    "CFD/constant/turbulenceProperties": "Turbulence",
    "CFD/constant/g": "Gravity",
    "parCFDDEMrun.sh": "Parallel launch script",
    "CFD/constant/couplingProperties": "Coupling and immersed boundary",
    "DEM/in.liggghts_run": "Particle scene",
}
