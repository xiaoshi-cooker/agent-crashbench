"""JSONL event log: one append-only file per run.

Design: docs/design/trace.md. Key properties:

- canonical-JSON lines (byte-stable, hashable);
- writer-assigned contiguous ``seq`` starting at 0;
- reopening a writer continues the sequence — boot is resume;
- a torn final line (crash mid-write) is tolerated and flagged on read;
  on writer reopen it is truncated away (standard WAL recovery), so history
  before the tear is never rewritten and the reader can stay strict;
- any other corruption or sequence anomaly raises ``TraceIntegrityError``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.core.canonical import canonical_json
from harness.core.types import Event, EventType

__all__ = ["TraceWriter", "TraceReadResult", "TraceIntegrityError", "read_events"]


class TraceIntegrityError(Exception):
    """The trace file is corrupt beyond the WAL-tolerated torn tail."""


@dataclass
class TraceReadResult:
    events: list[Event] = field(default_factory=list)
    truncated_tail: bool = False

    @property
    def last_seq(self) -> int:
        return self.events[-1].seq if self.events else -1


def _parse_line(line: str, lineno: int, path: Path) -> Event:
    try:
        d = json.loads(line)
    except json.JSONDecodeError as exc:
        raise TraceIntegrityError(f"{path}:{lineno}: unparseable line") from exc
    try:
        return Event.from_dict(d)
    except (KeyError, ValueError, TypeError) as exc:
        raise TraceIntegrityError(f"{path}:{lineno}: invalid event: {exc}") from exc


def read_events(path: str | os.PathLike[str]) -> TraceReadResult:
    """Read a trace file, tolerating (and flagging) a torn final line."""
    p = Path(path)
    result = TraceReadResult()
    if not p.exists():
        return result

    # Only "\n" delimits records; canonical JSON escapes control characters,
    # so no raw newline can appear inside a line.
    raw_lines = p.read_text(encoding="utf-8").split("\n")
    # A well-formed file ends with "\n", so the final split element is "".
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()

    for i, line in enumerate(raw_lines):
        is_last = i == len(raw_lines) - 1
        try:
            event = _parse_line(line, i + 1, p)
        except TraceIntegrityError:
            if is_last:
                result.truncated_tail = True
                break
            raise
        expected = result.last_seq + 1
        if event.seq != expected:
            raise TraceIntegrityError(
                f"{p}:{i + 1}: seq {event.seq}, expected {expected} (gap or disorder)"
            )
        result.events.append(event)
    return result


def _truncate_torn_tail(path: Path, valid_line_count: int) -> None:
    """Cut the file back to the end of its last complete line (WAL recovery)."""
    raw = path.read_bytes()
    offset = 0
    for _ in range(valid_line_count):
        offset = raw.index(b"\n", offset) + 1
    with open(path, "r+b") as fh:
        fh.truncate(offset)


class TraceWriter:
    """Single-writer, append-only event emitter for one run."""

    def __init__(
        self,
        base_dir: str | os.PathLike[str],
        run_id: str,
        fsync: bool = False,
    ) -> None:
        self.run_id = run_id
        self.path = Path(base_dir) / f"{run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fsync = fsync

        existing = read_events(self.path)
        self.recovered_torn_tail = existing.truncated_tail
        if existing.truncated_tail:
            _truncate_torn_tail(self.path, len(existing.events))
        self._next_seq = existing.last_seq + 1

        self._fh = open(self.path, "a", encoding="utf-8", newline="")

    def emit(self, type: EventType, payload: dict[str, Any] | None = None) -> Event:
        if self._fh.closed:
            raise ValueError("TraceWriter is closed")
        event = Event(
            run_id=self.run_id,
            seq=self._next_seq,
            type=type,
            payload=payload or {},
        )
        self._fh.write(canonical_json(event.to_dict()) + "\n")
        self._fh.flush()
        if self._fsync:
            os.fsync(self._fh.fileno())
        self._next_seq += 1
        return event

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
