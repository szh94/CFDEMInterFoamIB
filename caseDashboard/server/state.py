"""Per-case locks and the undo snapshot stack.

Writes to a case are serialised by a per-case lock so two concurrent requests
cannot interleave a read-modify-write over the same file.

Undo snapshots are held in memory and mirrored to ``.cache/undo`` so a restart
of the dashboard does not lose the ability to revert the last write.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Snapshot:
    index: int
    label: str
    created: float
    files: Dict[str, bytes] = dc_field(default_factory=dict)
    written: List[str] = dc_field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "index": self.index,
            "label": self.label,
            "created": self.created,
            "files": {rel: len(data) for rel, data in self.files.items()},
            "written": list(self.written),
        }


class CaseState:
    def __init__(self, case_dir: Path, cache_dir: Path, slug: str) -> None:
        self.case_dir = case_dir
        self.slug = slug
        self.lock = threading.RLock()
        self.undo: List[Snapshot] = []
        self._undo_dir = cache_dir / "undo" / slug
        self._counter = 0

    # -- undo ---------------------------------------------------------------
    def push_snapshot(self, label: str, originals: Dict[str, bytes], written: List[str]) -> Snapshot:
        self._counter += 1
        snap = Snapshot(self._counter, label, time.time(), dict(originals), list(written))
        self.undo.append(snap)
        self._persist(snap)
        # Keep the stack shallow; the dashboard is for tuning, not archaeology.
        if len(self.undo) > 20:
            dropped = self.undo.pop(0)
            self._discard(dropped)
        return snap

    def _persist(self, snap: Snapshot) -> None:
        try:
            target = self._undo_dir / str(snap.index)
            for rel, data in snap.files.items():
                path = target / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (target / "_meta.json").write_text(
                json.dumps(snap.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            # Memory copy is authoritative; a failed mirror only costs
            # durability across restarts.
            pass

    def _discard(self, snap: Snapshot) -> None:
        import shutil

        try:
            shutil.rmtree(self._undo_dir / str(snap.index), ignore_errors=True)
        except OSError:
            pass

    def pop_snapshot(self) -> Optional[Snapshot]:
        if not self.undo:
            return None
        snap = self.undo.pop()
        self._discard(snap)
        return snap

    def peek(self) -> Optional[Snapshot]:
        return self.undo[-1] if self.undo else None

    def stack_view(self) -> List[dict]:
        return [s.to_json() for s in reversed(self.undo)]


class Registry:
    def __init__(self, cache_dir: Path) -> None:
        self._cache = cache_dir
        self._states: Dict[str, CaseState] = {}
        self._lock = threading.Lock()

    def get(self, case_dir: Path) -> CaseState:
        key = str(case_dir.resolve()).lower()
        with self._lock:
            state = self._states.get(key)
            if state is None:
                # Two cases can share a directory name -- all the more easily now
                # that a case can live anywhere, since copying one under the same
                # name is the obvious thing to do.  The slug names a directory on
                # disk, so it has to be unique, and a digest of the full path is
                # the only part of it that is.  The name is kept for legibility.
                digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
                state = CaseState(case_dir, self._cache, f"{case_dir.name}-{digest}")
                self._states[key] = state
            return state
