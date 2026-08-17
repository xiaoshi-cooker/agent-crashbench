# Design doc: oracle protocol (out-of-process verdict envelope)

## Goal

The scorer that judges a run must live outside the system it judges: a
separate process, no imports from harness code, and an output envelope that
is self-identifying and impossible to misread. This contract defines the
envelope only — what a specific oracle checks (ledger comparison, invariant
checks) is P2; shipping the envelope first means every future oracle,
including private extensions, speaks the same protocol from day one.

## Contract

- Three-state verdict with an exit-code interlock:
  `pass` ↔ 0, `mismatch` ↔ 2, `error` ↔ 3. The verdict inside the report
  and the process exit status must agree; the runner checks both. Exit 1 is
  deliberately unused (it is what crashing interpreters produce by
  accident — a crash must never look like a verdict).
- `OracleReport` — `verdict`, `details` (free-form dict), `identity`:
  `protocol_version`, `oracle_source_sha256` (the oracle binds its own
  source), `input_sha256` (what it judged). Serialized as canonical JSON.
- `write_report(report, path)` / `parse_report(text)`. Parsing is
  fail-closed: unknown verdicts, a broken interlock, missing identity
  fields, or unknown top-level keys all raise `OracleProtocolError` —
  a report that cannot be fully understood is no verdict at all.
- `source_sha256(path)` helper so an oracle can self-bind in one line.

## Alternatives considered

- Import the oracle as a library — one shared interpreter state and one
  accidental import away from judging with the defendant's own code.
- pytest-as-oracle — exit codes conflate collection errors with failures
  and reports are not machine-stable.

## Decision

Plain JSON envelope + POSIX exit statuses; strict schema; identity block
mandatory. Boring on purpose — the protocol must be implementable in any
language in an afternoon.

## Out of scope

The actual comparison logic (ledger/invariants, P2), subprocess runner
integration (P2 bench runner), report signing.

## Test plan

Verdict/exit interlock mapping; roundtrip; parse rejects wrong exit code,
unknown verdict, missing identity keys, unknown top-level keys; helper
digest stability; write/read through a file.

## Status log

| Date | State | Note |
|------|-------|------|
| 2026-08-18 | shipped (P1 scope) | |
