# Design doc: tools (registry + governed execution)

## Goal

Every tool call in the system goes through one gate. The gate is where
side effects become observable (events), classifiable (error kinds), and —
in P2 — idempotent (keys) and journaled (intent log). If a call can bypass
the gate, the bench cannot trust its ledger; single-entry execution is a
correctness requirement, not a style choice.

## Contract

- `ToolRegistry`
  - `register(name, fn, description="", parameters=None, timeout_s=30.0)` —
    duplicate names raise.
  - `invoke(call: ToolCall) -> ToolResult` — never raises for tool failures:
    exceptions become classified `ToolResult`s (`ToolError.kind` honored,
    anything else `fatal`); unknown tool → `schema` error kind; wall time
    recorded in `elapsed_ms`.
  - `specs() -> list[dict]` — OpenAI-style function specs for the model.
- `ToolError(message, kind: ErrorKind)` — tools raise this to self-classify
  (e.g. a transient network failure is `retryable`).

## Alternatives considered

- Decorator auto-registration (global registry) — hides the wiring and makes
  per-scenario tool sets awkward; the bench builds registries per scenario.
- LangChain-style Tool classes — heavier surface than needed; specs are
  plain dicts here.

## Decision

Explicit instance registry; classification at the boundary; results are
data, never exceptions — the loop and the bench treat failures as ordinary
observable outcomes (they are the subject matter of this project).

## Out of scope (this commit → later P1/P2)

JSON-Schema argument validation, retry-with-backoff for `retryable`,
idempotency keys, intent journal, MCP client. The signature already carries
`parameters` so these land without interface breaks.

Timeout semantics (shipped): effective budget = min(registered `timeout_s`,
call `timeout_s`); overruns return `TIMEOUT`/`retryable`. CPython cannot
kill the worker thread, so an overrun tool may keep running in the
background — the gate reports honestly; hard isolation is process-level and
belongs to the bench (and the v0.2 sandbox).

## Test plan

Register/invoke happy path; unknown tool → schema kind; `ToolError`
classification honored; plain exception → fatal; duplicate registration
raises; specs shape; elapsed_ms recorded.

## Status log

| Date | State | Note |
|------|-------|------|
| 2026-08-18 | building | registry + classification first |
| 2026-08-18 | shipped (P1 scope) | timeout enforcement landed same day |
