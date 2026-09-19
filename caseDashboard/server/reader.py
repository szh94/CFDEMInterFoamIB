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
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .profiles import ALL_PARAMS, FILES
from .schema import Param

# Comment markers used by OpenFOAM dictionaries and LIGGGHTS input files.
_LINE_COMMENT = ("//", "#")


@dataclass
class Span:
    line: int
    col_start: int
    col_end: int


@dataclass
class Resolved:
    param: Param
    value: object
    status: str  # ok | unresolved | readonly | disabled | unused | optional
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

    def render(self, edits: Dict[int, List[Tuple[int, int, str]]]) -> str:
        """Apply ``{line: [(col_start, col_end, replacement), ...]}``."""
        out: List[str] = []
        for idx, content in enumerate(self.contents):
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


def scope_line_indices(contents: List[str], scope_re: re.Pattern, style: str) -> Optional[List[int]]:
    """Line indices inside the block whose header matches ``scope_re``."""
    for i, line in enumerate(contents):
        if not scope_re.search(line):
            continue
        if style != "brace":
            return [i]
        depth = 0
        started = False
        collected: List[int] = []
        for j in range(i, len(contents)):
            for ch in strip_comment(contents[j]):
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
                    if started and depth <= 0:
                        return collected
            if started:
                collected.append(j)
        return collected
    return None


def _to_number(text: str, vtype: str):
    if vtype == "int":
        return int(text)
    if vtype == "bool":
        return None  # handled by caller
    return float(text)


def _parse_bool(text: str, param: Param) -> bool:
    low = text.strip().strip(";").lower()
    if low in ("on", "yes", "true", "1", "y", "t"):
        return True
    if low in ("off", "no", "false", "0", "n", "f"):
        return False
    raise ValueError(f"Unrecognized boolean value {text!r}")


def resolve_param(param: Param, files: Dict[str, FileText]) -> Resolved:
    ft = files.get(param.file)
    if ft is None or not ft.ok:
        return Resolved(param, None, "unresolved", [], None, 0,
                        ft.error if ft else "File not loaded")

    pattern = re.compile(param.pattern)
    indices: List[int]
    if param.scope:
        scope_re = re.compile(param.scope)
        scope = scope_line_indices(ft.contents, scope_re, param.scope_style)
        if scope is None:
            return Resolved(param, None, "unresolved", [], None, 0,
                            f"Scope block {param.scope!r} not found")
        indices = scope
    else:
        indices = list(range(len(ft.contents)))

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
            return Resolved(param, None, "optional", [], None, 0,
                            "Optional: this case leaves the line out")
        return Resolved(param, None, "unresolved", [], None, 0, "No line matched")
    if len(hits) > 1:
        return Resolved(
            param, None, "unresolved", [], None, len(hits),
            "Matched {n} places; not unique (lines {lines})".format(
                n=len(hits),
                lines=", ".join(str(h[0] + 1) for h in hits[:6]),
            ),
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
        return Resolved(param, None, "unresolved", [], idx + 1, 1, str(exc))

    if param.readonly:
        status = "readonly"
    elif not enabled:
        status = "disabled"
    else:
        status = "ok"
    return Resolved(param, value, status, spans, idx + 1, 1, "", enabled, flag_span)


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
    return resolved, files


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
        # A ``product_of`` param is shown but never typed into, so it is not
        # editable no matter how healthy its match is.
        "editable": r.status == "ok" and not p.product_of,
        "product_of": list(p.product_of),
        "toggle": p.toggle,
        "enabled": r.enabled,
        "reason": r.reason,
        "matches": r.matches,
        "source": {"file": p.file, "line": r.line} if r.line else {"file": p.file, "line": None},
        "scope": p.scope,
    }
