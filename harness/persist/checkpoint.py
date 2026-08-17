"""File-backed checkpoint store with content addressing.

Design: docs/design/checkpoint.md. Atomic replace on save; verification on
every load; ``select`` is the single checkpoint selection strategy function
(by id, or latest stored).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from harness.core.canonical import canonical_json
from harness.core.types import Checkpoint

__all__ = ["FileCheckpointStore", "CheckpointIntegrityError", "CheckpointNotFound"]


class CheckpointIntegrityError(Exception):
    """A stored checkpoint no longer matches its content address."""


class CheckpointNotFound(Exception):
    """The requested checkpoint (or any checkpoint) does not exist."""


class FileCheckpointStore:
    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self.base_dir = Path(base_dir)

    def _run_dir(self, run_id: str) -> Path:
        return self.base_dir / run_id

    def save(
        self,
        run_id: str,
        step: int,
        payload: dict[str, Any],
        meta: dict[str, Any] | None = None,
    ) -> Checkpoint:
        ck = Checkpoint.create(run_id=run_id, step=step, payload=payload, meta=meta)
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        final = run_dir / f"{step:06d}.json"
        tmp = run_dir / f"{step:06d}.json.tmp"
        tmp.write_text(canonical_json(ck.to_dict()) + "\n", encoding="utf-8")
        os.replace(tmp, final)  # atomic: a crash mid-save never corrupts a committed file
        return ck

    def _load_file(self, path: Path) -> Checkpoint:
        ck = Checkpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if not ck.verify():
            raise CheckpointIntegrityError(f"{path}: payload does not match its content address")
        return ck

    def steps(self, run_id: str) -> list[int]:
        run_dir = self._run_dir(run_id)
        if not run_dir.is_dir():
            return []
        return sorted(int(p.stem) for p in run_dir.glob("*.json"))

    def load(self, run_id: str, ckpt_id: str) -> Checkpoint:
        run_dir = self._run_dir(run_id)
        for step in self.steps(run_id):
            ck = self._load_file(run_dir / f"{step:06d}.json")
            if ck.ckpt_id == ckpt_id:
                return ck
        raise CheckpointNotFound(f"run {run_id}: no checkpoint {ckpt_id}")

    def select(self, run_id: str, ckpt_id: str | None = None) -> Checkpoint | None:
        """Checkpoint selection strategy: explicit id, else latest stored."""
        if ckpt_id is not None:
            return self.load(run_id, ckpt_id)
        steps = self.steps(run_id)
        if not steps:
            return None
        return self._load_file(self._run_dir(run_id) / f"{steps[-1]:06d}.json")
