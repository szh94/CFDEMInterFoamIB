"""Read a case's parameters with anchored regexes.

Guarantees that make this safe enough to drive a writer:

* A parameter resolves only if its pattern matches **exactly once** in its file
  (or inside its ``scope`` block).  Zero or multiple matches mark the parameter
  ``unresolved`` and the UI renders it read-only, so an ambiguous rule can never
  silently edit the wrong line.
* Match offsets are reported as ``(line, col_start, col_end)`` so writing is a
  pure splice that leaves every other byte -- trailing comments, ``&``
  continuations, CRLF endings -- untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Collection, Dict, List, Optional, Tuple

from .profiles import ALL_PARAMS, FILES, PARTICLE_ZONE, _MACRO_PARAMS
from .schema import Column, Param

# Comment markers used by OpenFOAM dictionaries and LIGGGHTS input files.
_LINE_COMMENT = ("//", "#")

#: A macro definition: ``xco1 0;``.  Only used to resolve the ``$name`` tokens a
#: ``Param.repeats`` table is written with (see ``file_scalars``).
_MACRO_DEF = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*)\s+(?P<val>[0-9.eE+\-]+)\s*;")


@dataclass
class Span:
    line: int
    col_start: int
    col_end: int


@dataclass
class Row:
    """One row of a ``Param.repeats`` table, and where its components are.

    ``values`` is what the row *means* -- a ``$xco1`` resolved through the
    file's own macro definitions, so the panel shows the number the mesh will
    actually be built with -- while ``spans`` and ``sources`` point back at how
    it is written: the column ranges to splice and, per component, which
    parameter defines the macro it came from (``None`` for a plain number).
    The two are kept apart so an edit to one component can replace that one
    token and leave the neighbouring ``$yco1`` exactly as the file spells it.

    ``spans``/``values``/``sources`` are laid out column by column across the
    whole row, which may be several lines (see ``Param.row_lines``); ``lines``
    is the 0-based index of each of those lines, anchor first, so the writer
    knows which line to copy when it adds a row.
    """

    values: List[object]
    spans: List[Span]
    line: int
    sources: List[Optional[str]]
    lines: List[int] = dc_field(default_factory=list)


@dataclass
class ScopeLevel:
    """One enclosing block a ``Param.scope`` regex landed on.

    ``body`` is the lines strictly inside the braces -- what a nested scope is
    searched in, and what the innermost level's pattern is searched in.
    ``close`` is the line holding the ``}``: where the writer inserts a line the
    case does not have yet.  It is ``None`` for a scope style that is not a
    brace block, where there is no inside to insert into.
    """

    header: int
    body: List[int]
    close: Optional[int]


#: The delimiter pair each ``Param.scope_style`` counts, and the character that
#: closes it.  ``brace`` is the dictionaries' ``name { ... }``; ``paren`` is a
#: list's ``name ( ... )``, whose ``(`` may sit on the line after the header --
#: the depth count starts at the header, so it does not care.
_DELIMS = {"brace": ("{", "}"), "paren": ("(", ")")}


def brace_block(
    contents: List[str], pattern: str, candidates: List[int], style: str
) -> Optional[ScopeLevel]:
    """The first block among ``candidates`` whose header matches ``pattern``.

    ``candidates`` is what makes this nestable: the outer scope is searched over
    the whole file, the inner one only over the outer block's body.
    """
    regex = re.compile(pattern)
    header = next((i for i in candidates if regex.search(contents[i])), None)
    if header is None:
        return None
    delims = _DELIMS.get(style)
    if delims is None:
        return ScopeLevel(header, [header], None)
    opener, closer = delims
    depth = 0
    open_line: Optional[int] = None
    for j in range(header, len(contents)):
        for ch in strip_comment(contents[j]):
            if ch == opener:
                depth += 1
                if open_line is None:
                    open_line = j
            elif ch == closer:
                depth -= 1
                if open_line is not None and depth <= 0:
                    return ScopeLevel(header, list(range(open_line + 1, j)), j)
    return None


@dataclass
class Resolved:
    param: Param
    value: object
    #: ok | unresolved | readonly | disabled | unused | optional | create |
    #: inactive.  ``create`` and ``inactive`` are the two faces of a parameter
    #: that belongs to a model (see ``Param.owner``): the line is not in the
    #: file and will be written on apply, or it is in the file for a model the
    #: case is not using.
    status: str
    spans: List[Span]
    line: Optional[int]
    matches: int
    reason: str = ""
    #: For a ``Param.toggle``: whether its line is live.  Always true otherwise,
    #: and a disabled param still reports its value -- it is commented out, not
    #: gone.
    enabled: bool = True
    #: Span covering the comment marker, so the writer can add or drop it.
    #: Zero-width at the start of the line while the param is live.
    flag_span: Optional[Span] = None
    #: How much of ``Param.scope`` was located, outermost first.  A short chain
    #: says which block is missing, which is what the writer needs to build it
    #: (and what stops it from writing into the wrong one).
    scopes: List[ScopeLevel] = dc_field(default_factory=list)
    #: No line was located -- because there is none, not because the file is
    #: malformed.  A rule that matched *twice* is a different thing and is not
    #: absent, so it is never treated as a line waiting to be created.
    absent: bool = False
    #: The rows of a ``Param.repeats`` table, in file order.  Empty for every
    #: other rule; ``value`` is their list of triples, so the panel and the
    #: derive pass read one shape either way.  Declared last, and so out of the
    #: way of the positional ``Resolved(...)`` calls above it.
    rows: List[Row] = dc_field(default_factory=list)


@dataclass
class FileText:
    """A file split into content and its original line ending.

    Splitting only on ``\\r\\n`` / ``\\n`` / ``\\r`` (never ``str.splitlines``,
    which also breaks on ``\\x0b``, ``\\x0c`` and friends) and keeping the ending
    beside the content is what allows a byte-identical round trip: an edit
    replaces a column range inside the content and the ending is re-attached
    verbatim.
    """

    rel: str
    raw: bytes
    text: str
    contents: List[str]
    endings: List[str]
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def render(
        self,
        edits: Dict[int, List[Tuple[int, int, str]]],
        deleted: Collection[int] = (),
    ) -> str:
        """Apply ``{line: [(col_start, col_end, replacement), ...]}``.

        ``deleted`` names whole lines to drop, ending and all.  A replacement
        can only rewrite a span *inside* a line -- blanking its contents would
        leave the ending behind and the file would grow a blank line -- so
        removing one outright needs its own channel.
        """
        out: List[str] = []
        for idx, content in enumerate(self.contents):
            if idx in deleted:
                continue
            repls = edits.get(idx)
            if repls:
                buf = content
                for start, end, new in sorted(repls, key=lambda r: r[0], reverse=True):
                    buf = buf[:start] + new + buf[end:]
                out.append(buf)
            else:
                out.append(content)
            out.append(self.endings[idx])
        return "".join(out)


def split_lines(text: str) -> Tuple[List[str], List[str]]:
    contents: List[str] = []
    endings: List[str] = []
    i = 0
    n = len(text)
    start = 0
    while i < n:
        ch = text[i]
        if ch == "\r":
            if i + 1 < n and text[i + 1] == "\n":
                contents.append(text[start:i])
                endings.append("\r\n")
                i += 2
            else:
                contents.append(text[start:i])
                endings.append("\r")
                i += 1
            start = i
        elif ch == "\n":
            contents.append(text[start:i])
            endings.append("\n")
            i += 1
            start = i
        else:
            i += 1
    if start < n:
        contents.append(text[start:])
        endings.append("")
    return contents, endings


def load_file(case_dir: Path, rel: str) -> FileText:
    path = case_dir / rel
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return FileText(rel, b"", "", [], [], error=f"Cannot read: {exc}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return FileText(rel, raw, "", [], [], error=f"Not UTF-8 text: {exc}")
    contents, endings = split_lines(text)
    return FileText(rel, raw, text, contents, endings)


def strip_comment(line: str, markers=_LINE_COMMENT) -> str:
    """Remove a trailing comment, respecting simple quoted strings.

    Used only for brace counting, so a slight over-strip in exotic cases is
    harmless -- it can never change what gets written.
    """
    quote: Optional[str] = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        else:
            for marker in markers:
                if line.startswith(marker, i):
                    return line[:i]
        i += 1
    return line


def _to_number(text: str, vtype: str):
    if vtype == "int":
        return int(text)
    if vtype == "bool":
        return None  # handled by caller
    return float(text)


def file_scalars(contents: List[str]) -> Dict[str, float]:
    """Every ``name value;`` definition in the file, by name.

    ``blockMeshDict`` writes its corners as macros -- ``xco1 0;`` -- and then
    spells the vertex table with ``$xco1``; resolving those is what lets the
    panel show the coordinates the mesh will actually be built with.  This is a
    deliberately small scanner, not a dictionary parser: it reads the flat
    ``name value;`` lines at the top of the file and nothing else, which is
    exactly how these definitions are written.  Anything it cannot read is
    simply absent from the map, and the token that wanted it is reported
    unresolved rather than guessed at.
    """
    out: Dict[str, float] = {}
    for line in contents:
        m = _MACRO_DEF.match(strip_comment(line))
        if not m:
            continue
        try:
            out[m.group("name")] = float(m.group("val"))
        except ValueError:
            continue
    return out


def _parse_bool(text: str, param: Param) -> bool:
    low = text.strip().strip(";").lower()
    if low in ("on", "yes", "true", "1", "y", "t"):
        return True
    if low in ("off", "no", "false", "0", "n", "f"):
        return False
    raise ValueError(f"Unrecognized boolean value {text!r}")


def _read_cells(
    param: Param,
    m: re.Match,
    cols: Tuple[Column, ...],
    idx: int,
    scalars: Dict[str, float],
    values: List[object],
    spans: List[Span],
    sources: List[Optional[str]],
    context: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Append one line's columns to a row.  Returns a reason, or ``None``.

    A ``text`` column and an ``enum`` one are both copied through as the file
    spells them (a note is not a number and has no macro to resolve, and an
    ``enum``'s list is a convenience rather than a filter); every other column
    is a number, or a ``$macro`` the file defines.  Neither is guessed at: an
    unreadable token makes the whole rule unresolved, naming it.

    A ``context`` column is not on the line at all (see ``Column.context``): it
    takes the value resolved for the block the row sits in, and a row with no
    such block above it is unresolved rather than silently blank.
    """
    for col in cols:
        if col.context is not None:
            found = (context or {}).get(col.name)
            if found is None:
                return f"the {col.label or col.name} this row belongs to is not above it"
            # Zero-width: the cell is never written (see ``writer._plan_rows``),
            # so the span only has to keep the value lists aligned.
            values.append(found)
            spans.append(Span(idx, 0, 0))
            sources.append(None)
            continue
        token = m.group(col.name)
        span = m.span(col.name)
        if col.vtype in ("text", "enum"):
            values.append(token)
            sources.append(None)
        elif token.startswith("$"):
            name = token[1:]
            if name not in scalars:
                return f"the macro ${name} is not defined in this file"
            values.append(scalars[name])
            # Which parameter owns that macro, so the panel can carry a pending
            # edit of it straight into the box.  A name no rule claims is still
            # shown -- as a number, just not one that follows the domain extent
            # as it is typed into.
            sources.append(_MACRO_PARAMS.get((param.file, name)))
        else:
            try:
                values.append(int(token) if col.vtype == "int" else float(token))
            except ValueError:
                return f"{token!r} is neither a number nor a $macro"
            sources.append(None)
        spans.append(Span(idx, span[0], span[1]))
    return None


def _context_values(
    param: Param,
    ft: FileText,
    hits: List[Tuple[int, re.Match]],
    levels: List[ScopeLevel],
) -> Dict[int, Dict[str, str]]:
    """What each row inherits from the block it sits in, by the row's line.

    One pass over the scope, keeping the last match of each ``context`` column
    seen so far: a row takes whatever was in force on the line before it, which
    is what makes a list of faces group under the headers above them in the
    order the file wrote them.  The order matters at a line that is *both* a
    row and a header -- the row takes the block it is in, not itself, so the
    value is recorded before the line's own match is.

    A file that leaves the row before any header has nothing to record for it,
    and ``_read_cells`` reports the row unresolved rather than guessing.
    """
    cols = [col for col in param.columns if col.context is not None]
    if not cols:
        return {}
    patterns = [(col, re.compile(col.context)) for col in cols]
    anchors = {idx for idx, _ in hits}
    body = levels[-1].body if levels else list(range(len(ft.contents)))
    out: Dict[int, Dict[str, str]] = {}
    latest: Dict[str, str] = {}
    for i in body:
        if i in anchors:
            out[i] = dict(latest)
        for col, pattern in patterns:
            m = pattern.search(ft.contents[i])
            if m:
                latest[col.name] = m.group(col.name)
    return out


def _resolve_repeats(
    param: Param, ft: FileText, hits: List[Tuple[int, re.Match]], levels: List[ScopeLevel]
) -> Resolved:
    """Every hit becomes one row -- the "exactly once" rail does not apply.

    That rail exists because a second match means the rule cannot tell which
    line it was written for.  A table is the case where the count *is* the
    answer, so all of them are collected in file order, and each component is
    resolved on its own: a ``$macro`` through the file's own definitions, a
    plain number as itself.  A component that resolves to neither is not
    guessed at -- the whole rule is reported unresolved, naming the line and
    token, and the panel leaves it read-only.

    A row may be several lines (``Param.row_lines``).  The anchor's hit is the
    row, and each pattern after it is looked for on the lines that follow --
    down to the next anchor, and never past a blank line, so a row that is
    missing its companion is reported rather than quietly borrowing the next
    particle's.  Every line of the row is spanned, so a removal takes all of
    them (see ``writer._plan_rows``).

    A column may also be inherited from a line *above* the row (``Column.
    context``): a face line says its four corners and leaves the patch it faces
    to the header written once over it.  Those values are collected in one pass
    over the scope before the rows are built, so which block a row belongs to
    is decided by the file's own order rather than by a second search per row.
    """
    scalars = file_scalars(ft.contents)
    specs = param.row_specs
    compiled = [(re.compile(text), cols) for text, cols in specs[1:]]
    context = _context_values(param, ft, hits, levels)
    rows: List[Row] = []
    for pos, (idx, m) in enumerate(hits):
        values: List[object] = []
        spans: List[Span] = []
        sources: List[Optional[str]] = []
        lines = [idx]
        reason = _read_cells(param, m, specs[0][1], idx, scalars, values, spans, sources,
                             context.get(idx))
        if reason:
            return Resolved(param, None, "unresolved", [], idx + 1, len(hits),
                            f"Line {idx + 1}: {reason}", scopes=levels)
        # The next anchor is where this row's lines must have ended by; a blank
        # line ends the block (see ``Param.dem.zone_notes``).
        limit = hits[pos + 1][0] if pos + 1 < len(hits) else len(ft.contents)
        cursor = idx
        for pattern, cols in compiled:
            found = None
            for j in range(cursor + 1, limit):
                if not ft.contents[j].strip():
                    break
                mm = pattern.search(ft.contents[j])
                if mm:
                    found = (j, mm)
                    break
            if found is None:
                return Resolved(
                    param, None, "unresolved", [], idx + 1, len(hits),
                    f"Line {idx + 1}: the row is missing its {cols[0].label or 'second'} line",
                    scopes=levels,
                )
            j, mm = found
            reason = _read_cells(param, mm, cols, j, scalars, values, spans, sources,
                                 context.get(idx))
            if reason:
                return Resolved(param, None, "unresolved", [], j + 1, len(hits),
                                f"Line {j + 1}: {reason}", scopes=levels)
            lines.append(j)
            cursor = j
        rows.append(Row(values, spans, idx + 1, sources, lines))
    return Resolved(
        param, [row.values for row in rows], "ok", [], rows[0].line, len(rows), "",
        scopes=levels, rows=rows,
    )


#: The lead line of one particle inside the zone: ``#notes_p1: ...``.
_ZONE_NOTE = re.compile(rf"^\s*#\s*notes_p\d+\s*:")
_ZONE_MARKER = re.compile(rf"^\s*#\s*{PARTICLE_ZONE}\s*$")


def zone_bounds(ft: FileText) -> Optional[Tuple[int, List[int]]]:
    """The particle block's marker line and its note lines, or ``None``.

    ``None`` means there is no ``#create_atoms_zone`` line at all -- the case
    creates its particles another way -- which is what separates "this route
    does not apply" from "the block is there but says nothing".  The note lines
    are the comment lines between the marker and the first particle; the
    ``create_atoms`` / ``set atom`` lines after them are not part of it.  The
    block ends at the first blank line, which is why a note of its own may not
    contain one.
    """
    marker = next((i for i, line in enumerate(ft.contents) if _ZONE_MARKER.match(line)), None)
    if marker is None:
        return None
    out: List[int] = []
    for i in range(marker + 1, len(ft.contents)):
        line = ft.contents[i]
        if not line.strip() or _ZONE_NOTE.match(line):
            break
        if not line.lstrip().startswith("#"):
            break
        out.append(i)
    return marker, out


def _strip_hash(line: str) -> str:
    """One note line's text: the ``#`` and one space after it taken off."""
    body = line.lstrip()
    if body.startswith("#"):
        body = body[1:]
    return body[1:] if body.startswith(" ") else body


def _resolve_zone_notes(param: Param, ft: FileText) -> Resolved:
    """The particle block's free-form comment lines, one entry per line."""
    bounds = zone_bounds(ft)
    if bounds is None:
        return Resolved(param, None, "unresolved", [], None, 0, "No line matched",
                        absent=True)
    _, lines = bounds
    value = [_strip_hash(ft.contents[i]) for i in lines]
    spans = [Span(i, 0, len(ft.contents[i])) for i in lines]
    return Resolved(param, value, "ok", spans,
                    (lines[0] + 1) if lines else None, len(lines), "")


def resolve_param(param: Param, files: Dict[str, FileText]) -> Resolved:
    ft = files.get(param.file)
    if ft is None or not ft.ok:
        return Resolved(param, None, "unresolved", [], None, 0,
                        ft.error if ft else "File not loaded")

    if param.vtype == "text":
        return _resolve_zone_notes(param, ft)

    pattern = re.compile(param.pattern)
    specs = [param.scope] if isinstance(param.scope, str) else list(param.scope or [])
    levels: List[ScopeLevel] = []
    indices = list(range(len(ft.contents)))
    for spec in specs:
        level = brace_block(ft.contents, spec, indices, param.scope_style)
        if level is None:
            return Resolved(
                param, None, "unresolved", [], None, 0,
                f"Scope block {spec!r} not found",
                scopes=levels, absent=True,
            )
        levels.append(level)
        # The next scope -- and, at the end of the chain, the param's own
        # pattern -- is searched inside this block and nowhere else.
        indices = level.body

    hits: List[Tuple[int, re.Match]] = []
    for idx in indices:
        m = pattern.search(ft.contents[idx])
        if m:
            hits.append((idx, m))

    if not hits:
        # An optional setting is one the solver defaults, so no line is a state
        # of its own rather than a rule that failed.  Only this branch is
        # excused: a scope block that is missing, a file that could not be read
        # and a pattern that matched twice all still mean the file is not what
        # the rule expects, which is a real thing to report.
        if param.optional:
            # Some optional settings have a settled value in the absent state as
            # well (``Param.default_when_absent``): the line says nothing, but
            # the meaning is still "0", not "unknown".  Reporting the default
            # here -- rather than only in the UI -- is what lets the derived
            # metrics compute with it.  It is still not writable, so the value
            # stays a reading of the case rather than a pending change.
            if param.default_when_absent and param.default is not None:
                return Resolved(param, param.default, "optional", [], None, 0,
                                "Optional: this case leaves the line out; the default applies",
                                scopes=levels, absent=True)
            return Resolved(param, None, "optional", [], None, 0,
                            "Optional: this case leaves the line out",
                            scopes=levels, absent=True)
        return Resolved(param, None, "unresolved", [], None, 0, "No line matched",
                        scopes=levels, absent=True)
    if param.repeats:
        return _resolve_repeats(param, ft, hits, levels)
    if len(hits) > 1:
        return Resolved(
            param, None, "unresolved", [], None, len(hits),
            "Matched {n} places; not unique (lines {lines})".format(
                n=len(hits),
                lines=", ".join(str(h[0] + 1) for h in hits[:6]),
            ),
            scopes=levels,
        )

    idx, m = hits[0]
    spans: List[Span] = []
    texts: List[str] = []
    for gname in param.value_groups:
        span = m.span(gname)
        spans.append(Span(idx, span[0], span[1]))
        texts.append(m.group(gname))

    # A toggle param's ``flag`` group holds the comment marker (``# ``) when the
    # line is disabled and does not participate in the match when it is live --
    # which reads the same as a param whose pattern has no such group at all.
    flag = m.groupdict().get("flag")
    enabled = flag is None
    flag_span = Span(idx, 0, 0) if enabled else Span(idx, m.start("flag"), m.end("flag"))

    try:
        if param.vtype == "bool":
            value = _parse_bool(texts[0], param)
        elif param.is_triple:
            caster = int if param.vtype == "int3" else float
            value = [caster(t) for t in texts]
        elif param.vtype in ("string", "enum"):
            value = texts[0]
        else:
            value = _to_number(texts[0], param.vtype)
    except ValueError as exc:
        return Resolved(param, None, "unresolved", [], idx + 1, 1, str(exc), scopes=levels)

    if param.readonly:
        status = "readonly"
    elif not enabled:
        status = "disabled"
    else:
        status = "ok"
    return Resolved(param, value, status, spans, idx + 1, 1, "", enabled, flag_span, levels)


def read_case(case_dir: Path) -> Tuple[Dict[str, Resolved], Dict[str, FileText]]:
    """Resolve the whole parameter list against ``case_dir``.

    Nothing here decides whether ``case_dir`` is the *right* kind of case: a
    parameter whose file or line is absent comes back ``unresolved`` and is
    reported as such, so a case the list was not written for still opens with
    the subset that does line up.
    """
    files: Dict[str, FileText] = {}
    for rel in FILES:
        files[rel] = load_file(case_dir, rel)
    resolved: Dict[str, Resolved] = {}
    for param in ALL_PARAMS:
        resolved[param.id] = resolve_param(param, files)

    # Mutually exclusive routes (``Param.alt``): a whole group that matched
    # nothing means this case creates its particles the *other* way, not that
    # every rule in the group is broken -- so it reads "unused" rather than
    # "could not be located"
    # and the panel does not raise a warning for a route the case never took.
    # Only the group as a whole is downgraded: one that matched in part really is
    # missing lines, and those stay unresolved.  And only when the file itself
    # was read: a file that is absent is reported as such, not excused.
    for alt in {p.alt for p in ALL_PARAMS if p.alt}:
        members = [r for r in resolved.values() if r.param.alt == alt]
        if (
            members
            and all(r.status == "unresolved" for r in members)
            and files[members[0].param.file].ok
        ):
            for r in members:
                r.status = "unused"
                r.reason = "This case creates its particles another way; this group does not apply"

    # Model-owned parameters (``Param.owner``): a phase's viscosity coefficients
    # only mean anything while the phase's ``transportModel`` names the model
    # they belong to, and the answer is not in the file -- the case may be
    # running Newtonian and simply not have a coefficients block, which is a
    # perfectly ordinary case and not a rule that failed to match.  So "nothing
    # matched" splits in two:
    #
    #   * the owner selects it -> ``create``: editable, valued from its seed, and
    #     written into the file on apply (``writer.plan_creations``);
    #   * it does not          -> ``inactive``: not shown, and not writable,
    #     until the owner is switched to it.
    #
    # A line that *is* there takes the same split: read normally under the model
    # that owns it, ``inactive`` under any other -- which is what keeps a stale
    # block from being reported as a broken rule while the case runs Newtonian.
    #
    # ``model`` is the exception, for a parameter that *belongs* to a row
    # without being turned on by it: a phase's density sits in the same block
    # and is read under every ``transportModel``, so it is owned -- the panel
    # folds it into that row -- but no model can switch it off.
    #
    # Only the absence is excused.  A file that could not be read, and a pattern
    # that matched twice, stay ``unresolved``: those are real gaps or malformed
    # files, and neither is a line to be created.
    for r in resolved.values():
        p = r.param
        if not p.owner:
            continue
        owner = resolved.get(p.owner)
        selected = p.model is None or (
            owner is not None and owner.value is not None and str(owner.value) == p.model
        )
        if r.absent and files[p.file].ok:
            # Either way the value is the one the line would be created with --
            # that is what the *absence* says, and it does not depend on which
            # model the case runs.  It is what the panel shows the moment the
            # model is switched, before anything has been written.
            r.value = seed_value(p, resolved)
            if selected:
                r.status = "create"
                r.reason = "Not in the file yet; it is written when applied"
            else:
                r.status = "inactive"
                r.reason = f"Only applies while {p.owner} is {p.model}"
        elif not selected:
            r.status = "inactive"
            r.reason = f"Only applies while {p.owner} is {p.model}"
    return resolved, files


def seed_value(param: Param, resolved: Dict[str, Resolved]) -> object:
    """What a parameter the file does not have yet should start at.

    ``Param.seed_from`` is the case's own number for the same quantity under the
    model it is running now -- a phase's ``nu`` for the coefficients that *are*
    a viscosity.  Taking it is what makes creating the block a no-op physically:
    the model changes, the fluid does not.
    """
    if param.seed_from:
        source = resolved.get(param.seed_from)
        if source is not None and source.value is not None:
            return source.value
    return param.default


def _row_seed(p: Param, r: Resolved) -> Optional[list]:
    """What the panel's Add button starts a new row at.

    ``Param.row_seed`` when the rule spells one out (the vertex table, which
    has always started a new corner at the origin); otherwise the last row's
    own values, with the string columns blank -- a new particle starts where
    the previous one did, since that is the only placement the file knows
    about, and a new note starts empty.
    """
    if not p.repeats:
        return None
    if p.row_seed is not None:
        return list(p.row_seed)
    if not r.rows:
        return [
            "" if col.vtype in ("text", "enum") else 0
            for col in p.columns
        ]
    last = r.rows[-1].values
    return [
        "" if getattr(col, "vtype", "float") in ("text", "enum") else value
        for col, value in zip(p.columns, last)
    ]


def resolved_to_api(r: Resolved) -> dict:
    p = r.param
    return {
        "id": p.id,
        "group": p.group,
        "card": p.card,
        "label": p.label,
        "value": r.value,
        "unit": p.unit,
        "type": p.vtype,
        "options": p.options,
        "range": p.range,
        "help": p.help,
        "note": p.note,
        "default": p.default,
        "status": r.status,
        "readonly": p.readonly,
        # Whether an absent line still has a value worth showing (see `Param`).
        "default_when_absent": p.default_when_absent,
        # A ``product_of`` param is shown but never typed into, so it is not
        # editable no matter how healthy its match is.  A ``create`` one has no
        # line to edit yet, but it is exactly as editable as one that does: the
        # writer adds it (see ``Param.block``).
        "editable": r.status in ("ok", "create") and not p.product_of,
        # The model a parameter belongs to, and the one it is live under (see
        # ``Param.owner``): the panel shows a row's coefficients inside it.
        "owner": p.owner,
        "model": p.model,
        "block": p.block,
        "product_of": list(p.product_of),
        # What the file spells this line's keyword as.  Display-only: it is the
        # name a marker macro goes by in the fold that lists the handful of them
        # the mesh is built from -- ``xco1`` where the row is "Key marker points".
        "key": p.key,
        # Display-only grouping: the panel folds the named params into this row.
        "partners": list(p.partners),
        # Display-only layout: a triple that stays inside one column.
        "compact": p.compact,
        # Display-only layout: a row whose boxes are behind a fold, so what is
        # on screen until it is opened is the label and a count.
        "collapsible": p.collapsible,
        # A rule that reads as a table (see `Param.repeats`): `value` is then
        # one triple per line the pattern matched, and `macros` names -- per
        # row, per component -- the parameter whose value is written there, so
        # the panel can carry a pending edit to, say, the domain width into the
        # vertex boxes as it is typed.  `None` for every other rule.
        "repeats": p.repeats,
        "macros": [list(row.sources) for row in r.rows] if p.repeats else None,
        # What each column of a table's row is: the panel labels the boxes from
        # this rather than assuming the triple's own x/y/z, which is what lets
        # the vertex table and the particle table share one renderer.  Empty
        # for everything that is not a table.
        "columns": [
            {
                "name": col.name, "type": col.vtype, "label": col.label,
                "unit": col.unit,
                "options": list(col.options) if col.options else None,
                # Shown for context, never written (see ``Column.context``).
                "derived": col.context is not None,
                # The box's width, when the rule fixes one (see
                # ``Column.width``); ``None`` -> the panel's own default.
                "width": col.width,
            }
            for col in p.columns
        ],
        # Whether the panel draws one box per column or the triple's own
        # x/y/z.  It is the rule's declaration that decides, not the count:
        # the vertex table's three columns *are* the axes, and a two-column
        # table of its own (the patch headers) is not a triple.
        "per_column": p.row_columns is not None,
        # The row the Add button writes (see ``_row_seed``).
        "row_seed": _row_seed(p, r),
        # Whether rows may be added or taken off the end at all (see
        # ``Param.row_append``).
        "row_append": p.row_append,
        # How many of the table's rows share one line (see ``Param.row_per_line``).
        "row_per_line": p.row_per_line,
        "toggle": p.toggle,
        "enabled": r.enabled,
        "reason": r.reason,
        "matches": r.matches,
        "source": {"file": p.file, "line": r.line} if r.line else {"file": p.file, "line": None},
        # A nested scope is the reader's business, not the panel's: the field is
        # published for the reader's own tests, so a chain of them reports as
        # the single-scope shape it always was rather than as a list.
        "scope": p.scope if isinstance(p.scope, str) else None,
    }
