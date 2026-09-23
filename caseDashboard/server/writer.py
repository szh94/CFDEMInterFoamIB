"""Splice edits into files without disturbing anything else.

Two invariants drive the whole module:

1. **Only the matched span changes.**  The plan records ``(line, col_start,
   col_end)`` for each editable token and ``FileText.render`` rebuilds the line
   around it, so trailing ``;//timeStep;//`` comments, ``&`` continuations and
   other tokens on the same line survive verbatim.
2. **Line endings are preserved, not normalised.**  The real case files are
   CRLF (one of them mixed CRLF/LF).  Decoding to text and re-encoding with
   ``newline=''``-style handling would rewrite every line; instead the original
   ending of each line is stored next to it and re-attached unchanged.

A value equal to what is already in the file is dropped from the plan, so
"preview with no changes" and "write the current value back" are both
byte-identical by construction.
"""

from __future__ import annotations

import difflib
import hashlib
import math
import os
import re
import time
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .reader import FileText, Resolved, _strip_hash, seed_value, zone_bounds


class WriteError(Exception):
    pass


#: Prepended to a line to disable it (see ``Param.toggle``).  LIGGGHTS uses
#: ``#`` for comments, and one space keeps ``# fix`` readable.
DISABLE_MARKER = "# "


# --------------------------------------------------------------------------
# value formatting
# --------------------------------------------------------------------------


def format_float(value: float) -> str:
    if value != value or value in (float("inf"), float("-inf")):
        raise WriteError("Value must be a finite real number")
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    text = repr(float(value))
    if "e" not in text and "E" not in text:
        return text
    return f"{float(value):.12g}"


def format_scalar(param, value) -> str:
    vtype = param.vtype
    if vtype == "bool":
        if isinstance(value, str):
            low = value.strip().lower()
            value = low in ("1", "true", "yes", "on", "y", "t")
        return param.bool_true if value else param.bool_false
    if vtype == "int":
        return str(int(value))
    if vtype in ("string", "enum"):
        text = str(value)
        if param.options and text not in param.options:
            raise WriteError(
                f"Value {text!r} is not in the allowed list {param.options}"
            )
        if re.search(r"[\s;\"'{}]", text):
            raise WriteError(f"Value {text!r} contains illegal characters")
        return text
    if vtype == "float":
        return format_float(float(value))
    raise WriteError(f"Unknown type {vtype}")


def format_triple(param, value) -> List[str]:
    if isinstance(value, str):
        parts = value.replace(",", " ").split()
        if len(parts) != 3:
            raise WriteError(f"Expected 3 numbers, got {value!r}")
        value = parts
    if not hasattr(value, "__len__") or len(value) != 3:
        raise WriteError(f"Expected 3 numbers, got {value!r}")
    caster = int if param.vtype == "int3" else float
    out = []
    for component in value:
        if param.vtype == "int3":
            out.append(str(caster(component)))
        else:
            out.append(format_float(float(component)))
    return out


def format_row(param, value) -> List[str]:
    """One row of a ``repeats`` table, as the text of each of its columns.

    The row's shape is the rule's own (``Param.columns``), not the triple's:
    the vertex table's three numbers and the particle table's note plus eight
    numbers go through the same function, each column formatted by its type.
    """
    cols = param.columns
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    if not hasattr(value, "__len__") or len(value) != len(cols):
        raise WriteError(f"Expected {len(cols)} values, got {value!r}")
    out: List[str] = []
    for col, cell in zip(cols, value):
        if col.vtype == "text":
            out.append(str(cell))
        elif col.vtype == "int":
            out.append(str(int(cell)))
        else:
            out.append(format_float(float(cell)))
    return out


def _cell_equal(new_text: str, old) -> bool:
    """Whether the file already holds this cell, whatever the spelling."""
    if isinstance(old, str):
        return new_text == old
    try:
        return float(new_text) == float(old)
    except (TypeError, ValueError):
        return False


def _numerically_equal(param, old_texts: List[str], new_texts: List[str]) -> bool:
    """True when the file already holds this value, whatever the spelling."""
    try:
        if param.vtype in ("string", "enum"):
            return [t for t in old_texts] == [t for t in new_texts]
        if param.vtype == "bool":
            def as_bool(t: str) -> bool:
                return t.strip().lower() in ("1", "true", "yes", "on", "y", "t")
            return as_bool(old_texts[0]) == as_bool(new_texts[0])
        if param.vtype == "int":
            return int(old_texts[0]) == int(new_texts[0])
        if param.vtype == "int3":
            return [int(t) for t in old_texts] == [int(t) for t in new_texts]
        if param.vtype == "float3":
            return [float(t) for t in old_texts] == [float(t) for t in new_texts]
        return float(old_texts[0]) == float(new_texts[0])
    except (TypeError, ValueError):
        return False


def check_range(param, value) -> Optional[str]:
    """Return a validation message, or None when the value is acceptable."""
    rng = param.range
    if not rng:
        return None
    try:
        if param.is_triple:
            numbers = [float(v) for v in value]
        elif param.vtype in ("string", "enum"):
            return None
        elif param.vtype == "bool":
            return None
        else:
            numbers = [float(value)]
    except (TypeError, ValueError):
        return f"Cannot parse as a number: {value!r}"
    lo, hi = float(rng[0]), float(rng[1])
    for n in numbers:
        if n < lo or n > hi:
            return f"Outside the allowed range [{_num(lo)}, {_num(hi)}]"
    return None


def _num(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------


@dataclass
class Edit:
    param_id: str
    value: object
    #: Requested line state for a ``Param.toggle``; ``None`` leaves it as-is.
    enabled: Optional[bool] = None
    #: Set on the edits the server derives itself (a ``Param.product_of`` param).
    #: They are the only ones allowed to write a param the UI holds read-only.
    implicit: bool = False


@dataclass
class PlannedFile:
    rel: str
    replacements: List[Tuple[int, int, int, str]]  # line, col_start, col_end, text
    skipped: List[str]
    errors: List[str]
    #: Lines to drop outright, ending and all -- see ``FileText.render``.  Only
    #: a table can ask for this: taking a row off the end of the vertex list is
    #: the one edit that is not a rewrite of a span.
    deletions: List[int] = dc_field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.replacements or self.deletions)


@dataclass
class Plan:
    files: Dict[str, PlannedFile]
    errors: Dict[str, str]

    @property
    def changed_files(self) -> List[str]:
        return [rel for rel, pf in self.files.items() if pf.changed]

    @property
    def is_noop(self) -> bool:
        return not self.changed_files


def product_edits(
    resolved: Dict[str, Resolved], edits: List[Edit]
) -> List[Edit]:
    """The implicit edits that keep every ``product_of`` param equal to its sources.

    The panel shows such a param read-only, so nothing else would ever write it:
    changing a decomposition direction would leave the file's subdomain count
    behind while the panel already displayed the product -- the silent drift this
    dashboard exists to prevent.  Sources are taken from the pending edits first,
    so the value written is the one the user is looking at.

    A triple target takes one source per component instead of a product, which
    is what keeps the DEM's processor grid pointing the same way as the CFD's.
    """
    override = {e.param_id: e.value for e in edits}
    out: List[Edit] = []
    for pid, r in resolved.items():
        sources = r.param.product_of
        if not sources:
            continue
        raw = [
            override[src]
            if src in override
            else (resolved[src].value if src in resolved else None)
            for src in sources
        ]
        try:
            numbers = [int(value) for value in raw]
        except (TypeError, ValueError):
            # An unresolved source has no value to combine; leave the line as
            # the file has it rather than inventing a number for it.
            continue
        if r.param.is_triple:
            if len(numbers) != 3:
                continue
            out.append(Edit(pid, numbers, implicit=True))
        else:
            out.append(Edit(pid, math.prod(numbers), implicit=True))
    return out


def owner_selects(
    param, resolved: Dict[str, Resolved], override: Dict[str, object]
) -> bool:
    """Whether ``param``'s owner is set to the model ``param`` belongs to.

    The pending value wins over the one on disk, which is the whole point: a
    model switched in the panel but not yet written is still the model the user
    is looking at, and its coefficients are live from that moment.

    A parameter named by an owner but not tied to a ``model`` -- the phase's
    density -- is selected whenever its owner is there at all: no switch can
    turn it off, which is exactly why it is read under every model.
    """
    if param.model is None:
        return True
    owner = resolved.get(param.owner or "")
    raw = override.get(param.owner, owner.value if owner else None)
    return raw is not None and str(raw) == param.model


def _plan_rows(
    param,
    edit: Edit,
    r: Resolved,
    ft: FileText,
    planned: Dict[str, PlannedFile],
    errors: Dict[str, str],
) -> None:
    """Plan a ``Param.repeats`` table, one component at a time.

    The ordinary path zips the rule's spans against the new value, which is
    right for a value that *is* the line.  A table is not that: the edit
    carries the whole list of rows, and most of them are expected to equal what
    the file already says.  So each component is compared against the row's own
    resolved number and skipped when it agrees -- which is what keeps an
    untouched ``$yco1`` spelled as the file spells it instead of being written
    out as the ``0.1`` it stands for.  Changing one box therefore moves one
    token, and writing the table back unchanged writes nothing at all.

    A table may also grow or shrink, but only at the end: the panel adds a row
    to the bottom and takes one off the bottom, and a row is named by its
    position, so there is nothing a removal in the middle could be expressed
    as.  The rows the edit and the file still share therefore line up
    one-to-one from the front, whatever the difference in length -- the rows
    past the end of the file become new lines, and the rows past the end of the
    edit are dropped.
    """
    new_rows = edit.value
    if not isinstance(new_rows, (list, tuple)):
        errors[edit.param_id] = f"Expected a list of rows, got {new_rows!r}"
        return

    kept = min(len(r.rows), len(new_rows))
    # Validated in full before a single replacement is recorded: a rejected
    # edit must not leave half a table behind in the plan.
    pending: List[Tuple[int, int, int, str]] = []
    for row, new_row in zip(r.rows[:kept], new_rows[:kept]):
        try:
            texts = format_row(param, new_row)
        except WriteError as exc:
            errors[edit.param_id] = str(exc)
            return
        for span, text, old in zip(row.spans, texts, row.values):
            if _cell_equal(text, old):
                continue
            pending.append((span.line, span.col_start, span.col_end, text))

    fresh: List[str] = []
    for index, new_row in enumerate(new_rows[kept:], start=kept):
        try:
            texts = format_row(param, new_row)
        except WriteError as exc:
            errors[edit.param_id] = str(exc)
            return
        fresh.extend(_appended_row(ft, r, texts, index))

    # A row's own ``line`` is the one the panel shows, counting from 1; what
    # the file is indexed by is the span's, counting from 0.  A row of several
    # lines is spanned on all of them (see ``Param.row_lines``), so removing a
    # particle takes its whole three-line block rather than just the first one.
    dropped = sorted({span.line for row in r.rows[kept:] for span in row.spans})

    pf = planned.setdefault(param.file, PlannedFile(param.file, [], [], []))
    if not pending and not fresh and not dropped:
        pf.skipped.append(edit.param_id)
        return
    pf.replacements.extend(pending)
    pf.deletions.extend(dropped)
    if fresh:
        # Spliced in right after the last line the file's last row spans, so
        # they join the corners where the file keeps them rather than landing
        # anywhere else inside ``vertices (...)`` -- and, for a particle, so
        # the whole three-line block lands after the previous particle's
        # ``set atom`` line.
        anchor = max(span.line for span in r.rows[-1].spans)
        ending = ft.endings[anchor] or "\n"
        pf.replacements.append(
            (anchor + 1, 0, 0, "".join(line + ending for line in fresh))
        )


#: The index a case writes after each vertex -- ``($xco1 $yco1 $zco1) //0``.
#: Only ever reproduced, never required: a file that numbers its corners gets
#: its new ones numbered the same way, and one that does not is left alone.
_VERTEX_INDEX = re.compile(r"\)(\s*//\s*)\d+\s*$")


def _appended_row(ft: FileText, r: Resolved, texts: List[str], index: int) -> List[str]:
    """One new row of a table, spelled like the rows it is joining.

    The indent and the trailing index comment are both read off the file's own
    last row rather than invented here: a created line should look like the
    lines it is added to (the same instinct as ``_indent_of``), and the number
    is the row's position, which is what the case wrote it to mean.

    A row of several lines (``Param.row_lines``) is built the same way, one
    line at a time, off the *last row's corresponding line*: every column's
    own span on that template is replaced and everything else -- the keyword,
    the spacing, the trailing comment -- is copied verbatim.  A line whose
    regex captures ``valid`` gets the row's 1-based ordinal written there,
    which is what renumbers ``#notes_pN`` and ``set atom N`` after an add.
    """
    param = r.param
    specs = param.row_specs
    if len(specs) == 1:
        last = ft.contents[r.rows[-1].spans[0].line]
        body = f"({texts[0]} {texts[1]} {texts[2]})"
        tail = _VERTEX_INDEX.search(last)
        if tail:
            body += f"{tail.group(1)}{index}"
        return [f"{last[: len(last) - len(last.lstrip())]}{body}"]

    template_row = r.rows[-1]
    lines: List[str] = []
    offset = 0
    for pos, (pattern, cols) in enumerate(specs):
        template = ft.contents[template_row.lines[pos]]
        m = re.compile(pattern).search(template)
        repls: List[Tuple[int, int, str]] = []
        for col in cols:
            start, end = m.span(col.name)
            repls.append((start, end, texts[offset]))
            offset += 1
        if "valid" in m.groupdict() and m.group("valid") is not None:
            start, end = m.span("valid")
            repls.append((start, end, str(index + 1)))
        buf = template
        for start, end, new in sorted(repls, key=lambda t: t[0], reverse=True):
            buf = buf[:start] + new + buf[end:]
        lines.append(buf)
    return lines


def _plan_text(
    param,
    edit: Edit,
    r: Resolved,
    ft: FileText,
    planned: Dict[str, PlannedFile],
    errors: Dict[str, str],
) -> None:
    """Rewrite the particle block's own comment lines.

    A text block is neither a value nor a table: the lines *are* the thing, so
    an edit replaces them in place, drops the ones that are gone and appends
    the ones that are new.  Blank lines are refused rather than written -- a
    blank line is what ends the block (see ``reader.zone_bounds``), so one
    would take the particles with it.
    """
    value = edit.value
    if value is None:
        return
    if isinstance(value, str):
        value = value.split("\n")
    if not isinstance(value, (list, tuple)):
        errors[param.id] = f"Expected lines of text, got {value!r}"
        return
    wanted = [str(v).strip() for v in value]
    while wanted and not wanted[-1]:
        wanted.pop()
    if any(not line for line in wanted):
        errors[param.id] = "A blank line would end the particle block; leave it out"
        return

    bounds = zone_bounds(ft)
    if bounds is None:
        errors[param.id] = "The particle block is not in this file"
        return
    marker, old = bounds
    rendered = [f"# {line}" for line in wanted]
    pending: List[Tuple[int, int, int, str]] = []
    kept = min(len(old), len(rendered))
    for i in range(kept):
        # Compared against the text the line *reads as*, not against the bytes:
        # the file may spell the hash with no space after it, and echoing the
        # value back is meant to be a no-write (see ``_strip_hash``).
        if _strip_hash(ft.contents[old[i]]).strip() == wanted[i]:
            continue
        pending.append((old[i], 0, len(ft.contents[old[i]]), rendered[i]))
    gone = old[kept:]
    extra = rendered[kept:]

    pf = planned.setdefault(param.file, PlannedFile(param.file, [], [], []))
    if not pending and not gone and not extra:
        pf.skipped.append(param.id)
        return
    pf.replacements.extend(pending)
    pf.deletions.extend(gone)
    if extra:
        # In front of the line after the note -- never at the end of the note's
        # own last line, where ``render`` would apply it before that line's own
        # replacement and the two would run into each other.  Nothing is ever
        # deleted alongside an insertion (a block only grows or only shrinks),
        # so the line this lands on is a live one.
        anchor = (old[-1] if old else marker) + 1
        ending = ft.endings[anchor - 1] or "\n"
        pf.replacements.append(
            (anchor, 0, 0, "".join(line + ending for line in extra))
        )


def plan_edits(
    resolved: Dict[str, Resolved],
    files: Dict[str, FileText],
    edits: List[Edit],
) -> Plan:
    """Turn requested edits into concrete span replacements.

    Every edit is validated first; a rejected edit never produces a partial
    write, it is reported in ``Plan.errors`` and ignored.
    """
    planned: Dict[str, PlannedFile] = {}
    errors: Dict[str, str] = {}
    edits = list(edits) + product_edits(resolved, edits)
    override = {e.param_id: e.value for e in edits}

    for edit in edits:
        r = resolved.get(edit.param_id)
        if r is None:
            errors[edit.param_id] = "Unknown parameter"
            continue
        param = r.param
        # ``disabled`` only ever arises for a toggle param, and writing one is
        # how it gets switched back on.  A ``product_of`` param is the mirror
        # image of ``readonly``: only the server writes it, and it does so from
        # the sources it is derived from.
        if not edit.implicit:
            if param.product_of:
                # A triple is copied source by source, so listing it with " × "
                # would name an arithmetic that is not the one being done.
                joined = (
                    ", ".join(param.product_of)
                    if param.is_triple
                    else " × ".join(param.product_of)
                )
                errors[edit.param_id] = (
                    f"Computed from {joined}; it cannot be written by hand"
                )
                continue
            if param.readonly or r.status not in ("ok", "disabled", "create", "inactive"):
                errors[edit.param_id] = f"Parameter is not writable ({r.status})"
                continue
            # A coefficient belongs to whichever model its owner names, and is
            # written only while that is the one in force -- which is also the
            # condition under which the reader called it inactive rather than
            # broken.
            if param.owner is not None and not owner_selects(param, resolved, override):
                errors[edit.param_id] = f"Only applies while {param.owner} is {param.model}"
                continue
            if r.status == "create":
                # There is no span to splice: the line is not in the file, and
                # ``plan_creations`` below is what puts it there.  Falling
                # through would zip an empty span list against the new value and
                # drop the edit without a word.
                continue
        ft = files.get(param.file)
        if ft is None or not ft.ok:
            errors[edit.param_id] = ft.error if ft else "File not loaded"
            continue

        if param.repeats:
            _plan_rows(param, edit, r, ft, planned, errors)
            continue

        if param.vtype == "text":
            _plan_text(param, edit, r, ft, planned, errors)
            continue

        try:
            if param.is_triple:
                new_texts = format_triple(param, edit.value)
            else:
                new_texts = [format_scalar(param, edit.value)]
        except WriteError as exc:
            errors[edit.param_id] = str(exc)
            continue

        message = check_range(param, edit.value)
        if message:
            errors[edit.param_id] = message
            continue

        pf = planned.setdefault(param.file, PlannedFile(param.file, [], [], []))

        # Switching a toggle param on or off edits the comment marker, which is
        # a different span from the value; both can move in the same edit, and
        # ``FileText.render`` applies same-line replacements right-to-left.
        flip = (
            param.toggle
            and edit.enabled is not None
            and edit.enabled != r.enabled
            and r.flag_span is not None
        )
        if flip:
            pf.replacements.append(
                (
                    r.flag_span.line,
                    r.flag_span.col_start,
                    r.flag_span.col_end,
                    "" if edit.enabled else DISABLE_MARKER,
                )
            )

        old_texts = [ft.contents[s.line][s.col_start:s.col_end] for s in r.spans]
        if _numerically_equal(param, old_texts, new_texts):
            # An implicit edit reporting "skipped" would only be noise: the user
            # never asked for it, and it is *supposed* to be a no-op whenever the
            # file already agrees with the directions.
            if not flip and not edit.implicit:
                pf.skipped.append(edit.param_id)
            continue

        for span, text in zip(r.spans, new_texts):
            pf.replacements.append((span.line, span.col_start, span.col_end, text))

    plan_creations(resolved, files, edits, planned, errors)
    return Plan(planned, errors)


# --------------------------------------------------------------------------
# creation -- the lines a case does not have yet
# --------------------------------------------------------------------------

#: One level of nesting, when there is no sibling line to copy an indent from.
INDENT = "    "

#: Where a keyword is padded to before its value, which is how the dictionaries
#: here spell a dimensioned entry: ``nu              nu [ 0 2 -1 ... ] 1e-06;``.
KEY_COLUMN = 16


def _indent_of(contents: List[str], indices: List[int], fallback: str = INDENT) -> str:
    """The leading whitespace of the last non-blank line among ``indices``.

    A created line should look like the lines it is joining rather than like the
    writer's idea of a nice indent, and every dictionary here indents by four
    spaces anyway -- so the file is asked, and ``INDENT`` only answers for a
    block that has nothing in it to copy.
    """
    for idx in reversed(indices):
        line = contents[idx]
        if line.strip():
            return line[: len(line) - len(line.lstrip())]
    return fallback


def creation_value(param, resolved: Dict[str, Resolved], override: Dict[str, object]):
    """What a line the case does not have yet should be written with.

    The pending edit first, so a box the user typed into is what lands; then
    ``Param.seed_from``, again with the pending value ahead of the one on disk,
    so switching a model *and* editing the viscosity in the same write still
    seeds the new block from the number on screen; and finally the default.
    """
    if param.id in override:
        return override[param.id]
    if param.seed_from and param.seed_from in override:
        return override[param.seed_from]
    return seed_value(param, resolved)


def dimensioned_line(param, value, indent: str) -> str:
    """One created dimensioned entry, in the dictionaries' own spelling."""
    keyword = param.key or param.label
    return f"{indent}{keyword:<{KEY_COLUMN}}{keyword} [ {param.dims} ] {format_scalar(param, value)};"


def plan_creations(
    resolved: Dict[str, Resolved],
    files: Dict[str, FileText],
    edits: List[Edit],
    planned: Dict[str, PlannedFile],
    errors: Dict[str, str],
) -> None:
    """Insert the lines this case does not have.

    ``plan_edits`` can only replace text a pattern matched, so a parameter whose
    line is absent has nothing for it to work on.  That is not an odd corner
    here: OpenFOAM keeps a non-Newtonian model's coefficients in a
    ``<model>Coeffs`` sub-dictionary of their own, so a case running Newtonian
    has none of them, and switching the model in the panel is meant to bring the
    whole block into being.  Two shapes, decided by how much of ``Param.scope``
    the reader located:

    * the enclosing block is there and only the line is missing -> add the line;
    * the block is missing too -> add the block, with its members inside it.

    Members sharing an insertion point are written as one replacement, so a
    block is spelled out in the order the parameter list declares it rather than
    in whatever order ``FileText.render`` would apply zero-width inserts.

    Only a parameter whose owner *selects* it is created -- a coefficient of a
    model nobody asked for has no business in the file -- and only where the
    case really does not have it, which ``Resolved.absent`` says; a rule that
    matched twice is a malformed file, and reporting that is ``plan_edits``'
    job, not something to paper over with a third copy of the line.
    """
    override = {e.param_id: e.value for e in edits}
    pending: Dict[Tuple[str, int, Optional[str]], dict] = {}
    for r in resolved.values():
        p = r.param
        if not p.owner or not r.absent or not owner_selects(p, resolved, override):
            continue
        ft = files.get(p.file)
        if ft is None or not ft.ok:
            continue
        specs = [p.scope] if isinstance(p.scope, str) else list(p.scope or [])
        # The innermost level the reader reached.  One short of the chain means
        # the block ``Param.block`` names is the thing to build; shorter than
        # that means there is nowhere to build it.
        if len(r.scopes) == len(specs):
            block = None
            base = _indent_of(ft.contents, r.scopes[-1].body)
        elif len(r.scopes) == len(specs) - 1 and p.block and r.scopes:
            block = p.block
            base = _indent_of(ft.contents, r.scopes[-1].body)
        else:
            errors[p.id] = (
                f"Not in {p.file} yet, and the block it belongs to was not found"
            )
            continue
        close_line = r.scopes[-1].close
        if close_line is None:
            errors[p.id] = f"Not in {p.file} yet, and there is no block to add it to"
            continue
        value = creation_value(p, resolved, override)
        message = check_range(p, value)
        if message:
            errors[p.id] = message
            continue
        try:
            line = dimensioned_line(p, value, base if block is None else base + INDENT)
        except WriteError as exc:
            errors[p.id] = str(exc)
            continue
        entry = pending.setdefault(
            (p.file, close_line, block), {"indent": base, "lines": []}
        )
        entry["lines"].append(line)

    for (rel, close_line, block), entry in pending.items():
        ft = files[rel]
        # The line ending is the file's own, taken from the line being inserted
        # in front of -- creating a line must not be the one thing in this
        # module that rewrites the file's convention.
        ending = ft.endings[close_line] or "\n"
        indent = entry["indent"]
        lines = list(entry["lines"])
        if block:
            lines = [f"{indent}{block}", f"{indent}{{", *lines, f"{indent}}}"]
        pf = planned.setdefault(rel, PlannedFile(rel, [], [], []))
        pf.replacements.append(
            (close_line, 0, 0, "".join(line + ending for line in lines))
        )


# --------------------------------------------------------------------------
# rendering and diffing
# --------------------------------------------------------------------------


def render(files: Dict[str, FileText], plan: Plan) -> Dict[str, str]:
    rendered: Dict[str, str] = {}
    for rel in plan.changed_files:
        pf = plan.files[rel]
        ft = files[rel]
        by_line: Dict[int, List[Tuple[int, int, str]]] = {}
        for line, start, end, text in pf.replacements:
            by_line.setdefault(line, []).append((start, end, text))
        rendered[rel] = ft.render(by_line, pf.deletions)
    return rendered


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unified_diff(rel: str, old: str, new: str, context: int = 3) -> str:
    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
        lineterm="",
        n=context,
    )
    return "\n".join(diff)


def structured_diff(old: str, new: str, context: int = 3) -> List[dict]:
    """Grouped opcodes for side-by-side rendering."""
    a = old.splitlines()
    b = new.splitlines()
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    opcodes = matcher.get_opcodes()

    # Expand opcodes into rows, pairing replacements left/right.
    rows: List[dict] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append(_row("equal", a[i1 + k], b[j1 + k], i1 + k, j1 + k))
        elif tag == "delete":
            for k in range(i2 - i1):
                rows.append(_row("delete", a[i1 + k], None, i1 + k, None))
        elif tag == "insert":
            for k in range(j2 - j1):
                rows.append(_row("insert", None, b[j1 + k], None, j1 + k))
        else:  # replace
            na, nb = i2 - i1, j2 - j1
            paired = min(na, nb)
            for k in range(paired):
                rows.append(_row("replace", a[i1 + k], b[j1 + k], i1 + k, j1 + k))
            for k in range(paired, na):
                rows.append(_row("delete", a[i1 + k], None, i1 + k, None))
            for k in range(paired, nb):
                rows.append(_row("insert", None, b[j1 + k], None, j1 + k))

    return _group_hunks(rows, context)


def _row(kind: str, a_text, b_text, a_idx, b_idx) -> dict:
    return {
        "type": kind,
        "a": a_text,
        "b": b_text,
        "a_no": None if a_idx is None else a_idx + 1,
        "b_no": None if b_idx is None else b_idx + 1,
    }


def _group_hunks(rows: List[dict], context: int) -> List[dict]:
    changed = [i for i, r in enumerate(rows) if r["type"] != "equal"]
    if not changed:
        return []
    windows: List[Tuple[int, int]] = []
    for idx in changed:
        lo, hi = max(0, idx - context), min(len(rows), idx + context + 1)
        if windows and lo <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], hi))
        else:
            windows.append((lo, hi))

    hunks: List[dict] = []
    for lo, hi in windows:
        slice_rows = rows[lo:hi]
        hunks.append(
            {
                "a_start": next((r["a_no"] for r in slice_rows if r["a_no"]), None),
                "b_start": next((r["b_no"] for r in slice_rows if r["b_no"]), None),
                "rows": slice_rows,
            }
        )
    return hunks


def diff_files(files: Dict[str, FileText], rendered: Dict[str, str]) -> List[dict]:
    out: List[dict] = []
    for rel, new_text in rendered.items():
        ft = files[rel]
        new_bytes = new_text.encode("utf-8")
        out.append(
            {
                "file": rel,
                "unified": unified_diff(rel, ft.text, new_text),
                "hunks": structured_diff(ft.text, new_text),
                "byte_identical": new_bytes == ft.raw,
                "added": sum(1 for h in structured_diff(ft.text, new_text) for r in h["rows"] if r["type"] == "insert"),
                "removed": sum(1 for h in structured_diff(ft.text, new_text) for r in h["rows"] if r["type"] == "delete"),
            }
        )
    return out


# --------------------------------------------------------------------------
# atomic write
# --------------------------------------------------------------------------


def atomic_write(path: Path, data: bytes, attempts: int = 6) -> None:
    """Write via a sibling temp file + ``os.replace``.

    The solver may briefly hold a handle on ``/mnt/d`` while running, which
    surfaces as ``PermissionError``; a short backoff handles that without ever
    leaving a half-written dictionary behind.
    """
    tmp = path.with_name(path.name + ".dash_tmp")
    delay = 0.15
    last: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            with open(tmp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(delay)
            delay *= 2
        except OSError as exc:
            last = exc
            time.sleep(delay)
            delay *= 2
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    raise WriteError(f"Failed to write {path.name}: {last}")


def apply_plan(
    case_dir: Path, files: Dict[str, FileText], plan: Plan
) -> List[dict]:
    """Write every planned file.  Returns before/after digests."""
    written: List[dict] = []
    rendered = render(files, plan)
    for rel, new_text in rendered.items():
        path = case_dir / rel
        before = files[rel].raw
        after = new_text.encode("utf-8")
        if after == before:
            continue
        atomic_write(path, after)
        written.append(
            {
                "file": rel,
                "before_sha": sha256(before),
                "after_sha": sha256(after),
                "bytes_before": len(before),
                "bytes_after": len(after),
            }
        )
    return written
