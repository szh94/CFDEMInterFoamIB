"""Declarative parameter definitions.

One rule drives both reading and writing.  Each ``pattern`` must match a line
(or, for triple-valued parameters, a fragment of a line) exactly once and must
expose the editable text through named groups:

* scalar types -> ``pre`` / ``val`` / ``post``
* ``float3`` / ``int3`` -> ``pre`` / ``valx`` / ``valy`` / ``valz`` / ``post``

The surrounding text is never rewritten: applying an edit means
``pre + new_value + post``, so semicolons, trailing ``//...//`` comments,
``&`` continuations and any other token sharing the line survive byte-for-byte.

``scope`` handles keys that repeat inside a dictionary file.  ``alphaMin``
appears four times in ``couplingProperties`` and matching the wrong block would
silently corrupt the case, so the rule is pinned to a brace-delimited block and
"exactly one match" is enforced as a safety rail.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple

SCALAR_TYPES = ("float", "int", "bool", "string", "enum")
TRIPLE_TYPES = ("float3", "int3")
ALL_TYPES = SCALAR_TYPES + TRIPLE_TYPES


@dataclass
class Param:
    id: str
    group: str
    file: str
    pattern: str
    #: Card title, for params that deserve their own card inside a file rather
    #: than being lumped in with everything else in it.  ``None`` -> the panel
    #: groups by ``file`` and titles the card from ``FILE_LABELS``.
    card: Optional[str] = None
    #: Mutually exclusive particle-creation routes ("single" / "multisphere").
    #: When the whole group fails to match, it is reported as "unused" rather
    #: than each rule being reported as "could not be located".
    alt: Optional[str] = None
    #: A setting the solver has a default for, so a case may leave the line out
    #: altogether.  Absent is then a legitimate state, not a broken rule: the
    #: parameter reads "optional" (a grey row, no value, never written) instead
    #: of "unresolved" (the red *Not found* that asks the user to add the line).
    #: Only the no-match case is excused -- a line that matches twice is still a
    #: malformed file, and one in a file that could not be read is still a gap.
    optional: bool = False
    #: For an ``optional`` param whose absent state still has a definite value:
    #: no line does not mean "unknown", it means ``default`` applies -- a water
    #: box with no lower corner written down starts at the origin.  The panel
    #: then shows that number (greyed out, still never written) and the derived
    #: metrics compute with it, instead of reading a blank and skipping the
    #: metric.  Without the flag an absent optional stays blank: the solver's
    #: fallback for a coefficient is not necessarily the value the panel
    #: suggests, so printing it would dress a guess up as a reading.
    default_when_absent: bool = False
    vtype: str = "float"
    label: str = ""
    unit: str = ""
    options: Optional[List[str]] = None
    range: Optional[List[float]] = None
    help: str = ""
    default: Any = None
    #: Regex locating an enclosing block, e.g. ``^IBProps\\s*$``.
    scope: Optional[str] = None
    scope_style: str = "brace"
    #: Spellings used when writing a bool; keeps the file's own dialect.
    bool_true: str = "on"
    bool_false: str = "off"
    #: Shown but not editable (hard-coded values used by consistency checks).
    readonly: bool = False
    #: Line-level switch: the whole line can be commented out to disable the
    #: setting and un-commented to bring it back.  Such a param's ``pattern``
    #: must expose the comment marker as ``flag``, and it stays writable while
    #: disabled -- that is the only way to switch it back on.
    toggle: bool = False
    #: Ids of params this one is always derived from, e.g. the subdomain count
    #: against ``prox*proy*proz``.  Such a param is never typed into: the panel
    #: shows the live value, and the writer recomputes the line on every plan so
    #: the file cannot drift from the numbers it is derived from.
    #:
    #: How the sources combine follows from the target's shape, and only from
    #: that: a scalar takes their product, a triple takes them one per component.
    #: A vector is not the product of anything -- it is the three numbers it is
    #: made of -- and a grid that has to line up with another grid has to line up
    #: axis by axis.  That is the same rule as the single-source case, an
    #: "equals" rather than a "product of", which is how ``couple_every`` follows
    #: ``couplingInterval``; there are just three copies instead of one.
    #: ``selftest`` pins the counts that rule implies.
    product_of: Tuple[str, ...] = ()
    #: The rest of a set of sibling lines that belong together on one row -- the
    #: min and max of one domain extent (``mesh.xco1`` -> ``mesh.xco2``), or the
    #: x/y/z of one decomposition (``mesh.prox`` -> ``mesh.proy``,
    #: ``mesh.proz``).  Only the first of a group carries it; the panel folds the
    #: named params into this one's row and skips rendering them on their own.
    #: Purely a display grouping: every id keeps its own rule, line and edit.
    partners: Tuple[str, ...] = ()
    #: A triple laid out to fit inside one column of the panel grid: three
    #: narrow boxes with the label grown to fill the gap in front of them,
    #: rather than the full-width boxes of a row that spans two columns.  The
    #: point is the right edge: the last of the three boxes then lines up with
    #: the single box of the rows above it.  Purely a display choice.
    compact: bool = False
    #: Free-form note rendered next to the field.
    note: str = ""
    #: Display order inside a group.
    order: int = 100

    def __post_init__(self) -> None:
        if self.vtype not in ALL_TYPES:
            raise ValueError(f"{self.id}: unknown vtype {self.vtype!r}")
        if self.vtype == "enum" and not self.options:
            raise ValueError(f"{self.id}: enum needs options")
        if not self.label:
            self.label = self.id.rsplit(".", 1)[-1]

    @property
    def is_triple(self) -> bool:
        return self.vtype in TRIPLE_TYPES

    @property
    def value_groups(self) -> List[str]:
        return ["valx", "valy", "valz"] if self.is_triple else ["val"]


@dataclass
class ParamGroup:
    id: str
    label: str
    blurb: str = ""
    params: List[Param] = dc_field(default_factory=list)
