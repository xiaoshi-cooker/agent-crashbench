# Design doc: trace (JSONL event log)

## Goal

Every run leaves a durable, append-only event log that (a) reconstructs the
full order of model calls, tool calls, checkpoints, and faults after the
fact, and (b) survives a crash mid-write. The trace is the ground truth the
bench scores against and the substrate replay-based recovery reads from.

## Contract

- `TraceWriter(base_dir, run_id, fsync=False)` — opens (or reopens)
  `<base_dir>/<run_id>.jsonl` for append. On reopen it scans existing events
  and continues the sequence: **boot is resume** (crash-only design).
  - `emit(type: EventType, payload: dict) -> Event` — assigns the next `seq`,
    stamps `ts_us`, writes one canonical-JSON line, flushes (fsync optional).
  - Context manager; `close()`.
- `read_events(path) -> TraceReadResult` with `events: list[Event]`,
  `truncated_tail: bool`. A torn final line (crash mid-write) is tolerated
  and flagged, never raised. Corruption anywhere else raises
  `TraceIntegrityError`, as does any gap or disorder in `seq`.
- Single-writer per run (mirrors the repo-wide single-writer rule); `seq` is
  writer-assigned, contiguous from 0.

## Alternatives considered

- SQLite store — transactional, but harder to eyeball/diff, and a separate
  reader dependency for the flight recorder; JSONL keeps the log greppable
  and diffable (Jepsen-style artifacts).
- In-memory bus with periodic dump — loses exactly the events nearest to the
  crash, which are the ones the bench needs most.
- OTel-first — interop before correctness; deferred to P3 as an exporter on
  top of this log.

## Decision

One JSONL file per run; canonical JSON lines (stable bytes → hashable);
line-buffered flush per event by default, `fsync` opt-in for
durability-critical bench runs; WAL-style torn-tail tolerance on read.

## Out of scope

Rotation/compaction, OTel export, cross-run indexing (flight recorder's job).

## Test plan

- Unit: roundtrip; seq continuity across writer reopen; torn tail tolerated
  and flagged; mid-file corruption raises; seq gap raises; unicode payloads;
  byte-stable line for identical event dicts.
- Fault: kill between write and flush → at most the final line is torn;
  covered later by the proc-kill scenario in the bench.

## Status log

| Date | State | Note |
|------|-------|------|
| 2026-08-17 | shipped (P1 scope) | |
