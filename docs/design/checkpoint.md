# Design doc: checkpoint (persist + resume)

## Goal

A crashed run can be reopened and continued from its last saved state, and
the store can prove the state was not corrupted in between: every
checkpoint is content-addressed (`payload_sha256`) and verified on load.
Together with the trace's reopen-continues behavior, this makes "boot is
resume" real end to end.

## Contract

- `FileCheckpointStore(base_dir)`
  - `save(run_id, step, payload, meta=None) -> Checkpoint` — atomic write
    (`tmp` + `os.replace`) of canonical JSON to
    `<base>/<run_id>/<step:06d>.json`.
  - `load(run_id, ckpt_id) / select(run_id, ckpt_id=None) -> Checkpoint` —
    `select` is the **single internal checkpoint selection strategy
    function**: given an id it restores that checkpoint, otherwise the
    latest stored (highest step). Returns None when the run has no
    checkpoints. Every load verifies the content address and raises
    `CheckpointIntegrityError` on mismatch (fail closed, no silent
    fallback to older checkpoints).
- `AgentLoop` integration
  - optional `checkpoints=` store; after every completed step the loop
    saves `snapshot()` and emits a `checkpoint` event.
  - `AgentLoop.restore(backend, tools, trace, checkpoints, ckpt_id=None)`
    rebuilds a loop from the selected checkpoint and emits
    `run_start {resumed: true}`; `continue_run()` finishes the task.
    No checkpoint → `CheckpointNotFound` (caller decides on a fresh start).

## Alternatives considered

- Pickled state — opaque, unhashable, version-fragile; violates the
  plain-dicts rule.
- Log-position checkpoints (state rebuilt by replaying the event log with
  memoized model calls) — the durable-execution end state; P2 builds it on
  top of this store, at which point the payload shrinks to a cursor.

## Decision

Per-step full-state snapshots in canonical JSON with content addressing;
atomic replace so a crash mid-save can only ever lose the newest
checkpoint, never corrupt a committed one.

## Out of scope

Compaction/retention, replay-based rebuild (P2), remote stores, additional
selection strategies (the strategy surface stays one function).

## Test plan

Store: save/load roundtrip; atomic write leaves no tmp files; tamper →
integrity error; select latest/by-id/empty. Integration: run one step,
abandon the loop, restore from checkpoint with a fresh backend script and
finish — the first tool call must NOT re-execute (no duplicate side
effect), trace seq stays contiguous across the reopen, and the resumed
run_start is recorded.

## Status log

| Date | State | Note |
|------|-------|------|
| 2026-08-18 | shipped (P1 scope) | |
