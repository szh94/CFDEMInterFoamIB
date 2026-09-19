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
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .reader import FileText, Resolved, Span


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

    @property
    def changed(self) -> bool:
        return bool(self.replacements)


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
            if param.readonly or r.status not in ("ok", "disabled"):
                errors[edit.param_id] = f"Parameter is not writable ({r.status})"
                continue
        ft = files.get(param.file)
        if ft is None or not ft.ok:
            errors[edit.param_id] = ft.error if ft else "File not loaded"
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

    return Plan(planned, errors)


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
        rendered[rel] = ft.render(by_line)
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
