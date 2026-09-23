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

``repeats`` is the one rule that is a *table* rather than a value: every line
the pattern matches inside the scope is a row of its own (the ``vertices`` list
of ``blockMeshDict``), so "exactly one match" would be the wrong safety rail --
there the count *is* the shape of the thing being read.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple, Union

SCALAR_TYPES = ("float", "int", "bool", "string", "enum", "text")
TRIPLE_TYPES = ("float3", "int3")
ALL_TYPES = SCALAR_TYPES + TRIPLE_TYPES


@dataclass(frozen=True)
class Column:
    """One column of a ``Param.repeats`` table's row.

    The default row is the triple's own ``valx`` / ``valy`` / ``valz``; a rule
    whose row is spread over several lines declares its columns explicitly (see
    ``Param.row_columns`` / ``Param.row_lines``).  ``vtype`` decides how the
    token is read and written: ``text`` and ``enum`` are copied through as
    strings, numbers are parsed.  ``label``/``unit`` are what the panel prints
    above the column.
    """

    name: str
    vtype: str = "float"
    label: str = ""
    unit: str = ""
    #: The values an ``enum`` column offers.  A cell the file spells differently
    #: is still shown and still written -- the panel appends it, as it does for
    #: an ``enum`` param -- so the list is a convenience, never a filter.
    options: Optional[Tuple[str, ...]] = None
    #: A cell the row does not spell on its own line: the row *belongs to* the
    #: nearest preceding line matching this regex, captured through a group
    #: named after the column.  ``mesh.faces``'s patch name is one -- a face
    #: line says its four corners and nothing else, and which patch it faces
    #: is written once, above it.  The cell is shown for context and never
    #: written: the line it came from is some other rule's to change.
    context: Optional[str] = None
    #: A CSS length the panel gives the column's boxes, in place of the width it
    #: would pick for the cell's type.  A *fixed* one is what lines the boxes up
    #: across the rows of a table whose cells are of no fixed size -- a patch
    #: name, a short run of corner numbers -- and it is declared here because
    #: the rule is what knows what its own column holds.  ``None`` -> the
    #: panel's default width.
    width: Optional[str] = None


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
    #: Regex locating an enclosing block, e.g. ``^IBProps\\s*$``.  A *list* of
    #: them narrows the search one block at a time -- the phase ``water { ... }``
    #: and then the ``BirdCarreauCoeffs { ... }`` inside it -- which is how a
    #: rule reaches a sub-dictionary of the block that names it.
    scope: Optional[Union[str, List[str]]] = None
    scope_style: str = "brace"
    #: The keyword this rule anchors on.  A rule usually reads it off its own
    #: pattern; it is spelled out here for the rules whose line may have to be
    #: *created*, where there is no matched text to take it from.
    key: str = ""
    #: Dimension set of a created dimensioned entry, written between the
    #: brackets -- ``"0 2 -1 0 0 0 0"`` for a kinematic viscosity.
    dims: str = ""
    #: The parameter that decides whether this one is live at all: a phase's
    #: ``transportModel``, say, which is what gives its coefficients a meaning.
    owner: Optional[str] = None
    #: The value of ``owner`` under which this parameter applies.
    model: Optional[str] = None
    #: Name of the sub-dictionary this parameter lives in
    #: (``"BirdCarreauCoeffs"``), or ``None`` when it is written directly in the
    #: owner's own block.  A case is free not to have that sub-dictionary at all
    #: -- a Newtonian case has no coefficients -- and then the writer builds it,
    #: which is the whole reason "no line matched" can be a legitimate state
    #: rather than a broken rule (see ``Param.owner``).
    block: Optional[str] = None
    #: Where a created parameter's opening value comes from: the id of another
    #: parameter.  ``None`` -> ``default``.  Used so that a block built for a
    #: model switch reproduces the viscosity the case already had instead of
    #: silently changing the physics.
    seed_from: Optional[str] = None
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
    #: The row's boxes sit behind a fold: on screen the row is its label and a
    #: count, and the boxes appear when it is unfolded.  For a grouped row
    #: (``partners``) it is the whole set that folds -- the blockMeshDict macros
    #: the corners are built from -- so the mesh card opens with one line where
    #: six boxes would be, and the fold lists them by the names the file uses.
    #: Purely a display choice: every id keeps its own rule, line and edit, and a
    #: folded row is written exactly as an unfolded one.
    collapsible: bool = False
    #: The rule matches a *list*: every hit inside the scope is one row of a
    #: table rather than a second, ambiguous copy of one value.  The shape stays
    #: the triple's, so the boxes read as they do everywhere else; what changes
    #: is the cardinality and the write: the reader collects all of them in file
    #: order and the writer splices each row's components separately, so an
    #: untouched component keeps whatever the file spelled there (a ``$macro``
    #: included) instead of being rewritten as the number it resolves to.
    repeats: bool = False
    #: The columns the *anchor* line of a ``repeats`` row contributes.  Unset
    #: falls back to the shape the value type implies -- one ``val``, or the
    #: ``valx``/``valy``/``valz`` of a triple -- which is what the vertex table
    #: uses.  A row spread over several lines sets it, so the anchor can be a
    #: line that carries columns of its own (the ``#notes_pN:`` lead line of a
    #: DEM particle).
    row_columns: Optional[Tuple[Column, ...]] = None
    #: ``(regex, columns)`` for each line *after* the anchor that belongs to the
    #: same row.  Empty for the ordinary one-line table.  A DEM particle is
    #: three lines -- the note, ``create_atoms`` and ``set atom`` -- and this is
    #: what says so: the reader looks for each pattern on the lines following
    #: the anchor, and the writer copies those lines when it adds a particle.
    #: A regex may capture a ``valid`` group, which is not a column: the writer
    #: writes the row's own ordinal there, which is how the particle number in
    #: ``#notes_pN`` and ``set atom N`` stays right after an add or a remove.
    row_lines: Tuple[Tuple[str, Tuple[Column, ...]], ...] = ()
    #: What a row starts at when the panel adds one (see ``resolved_to_api``).
    #: ``None`` -> the last row's own numbers, with text columns blank.
    row_seed: Optional[List[Any]] = None
    #: Whether a row can be added to the end of this table, and the last one
    #: taken off it.  False for a table whose rows are not self-contained: a
    #: patch header introduces a parenthesised block of faces that the writer
    #: can neither synthesize nor delete from the header alone, so those rows
    #: are edited where they are and the panel offers no Add/Remove.  The
    #: writer refuses a row count that changed either way -- the buttons are
    #: the affordance, not the rail.
    row_append: bool = True
    #: How many of the table's rows the panel puts on one line.  A row of a few
    #: narrow cells -- a patch header, a face -- leaves most of the card empty,
    #: so several of them read better side by side than one per line; a row that
    #: needs the width (a block's five columns) keeps a line to itself.
    row_per_line: int = 1
    #: Free-form note rendered next to the field.
    note: str = ""
    #: Display order inside a group.
    order: int = 100

    def __post_init__(self) -> None:
        if self.vtype not in ALL_TYPES:
            raise ValueError(f"{self.id}: unknown vtype {self.vtype!r}")
        if self.vtype == "enum" and not self.options:
            raise ValueError(f"{self.id}: enum needs options")
        if self.model is not None and self.owner is None:
            raise ValueError(f"{self.id}: a model to be read against needs an owner")
        if self.row_lines and not self.repeats:
            raise ValueError(f"{self.id}: companion lines need repeats")
        if not self.label:
            self.label = self.id.rsplit(".", 1)[-1]

    @property
    def is_triple(self) -> bool:
        return self.vtype in TRIPLE_TYPES

    @property
    def row_specs(self) -> List[Tuple[str, Tuple[Column, ...]]]:
        """``(regex, columns)`` for every line of a row, anchor first."""
        if self.row_columns is not None:
            anchor = tuple(self.row_columns)
        elif self.is_triple:
            anchor = tuple(Column(n) for n in ("valx", "valy", "valz"))
        else:
            anchor = (Column("val", self.vtype),)
        return [(self.pattern, anchor), *self.row_lines]

    @property
    def value_groups(self) -> List[str]:
        return [c.name for c in self.row_specs[0][1]]

    @property
    def columns(self) -> List[Column]:
        """Every column of a row, across all its lines.  Empty when not a table."""
        if not self.repeats:
            return []
        return [col for _, cols in self.row_specs for col in cols]

    @property
    def row_groups(self) -> List[str]:
        """Every column name of a row, the anchor's first (see ``columns``)."""
        return [c.name for c in self.columns]


@dataclass
class ParamGroup:
    id: str
    label: str
    blurb: str = ""
    params: List[Param] = dc_field(default_factory=list)
    #: What the tab shows.  ``params`` is the ordinary case -- the fields below
    #: -- while ``scripts`` marks a tab whose content is a fact about the case
    #: rather than a dictionary to edit.  Declared here rather than hard-coded
    #: in the frontend for the same reason ``card``/``partners`` are: the tab
    #: list is the backend's, and a second copy of it in React would be the one
    #: that drifts.
    kind: str = "params"
