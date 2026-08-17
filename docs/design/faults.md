# Design doc: faults (declarative injection at the harness chokepoints)

## Goal

Faults are data, not test code: a bench scenario declares *what* fails,
*where*, and *how often*, and the injector makes it happen deterministically
at the two chokepoints the harness owns — the tool gate and the model
backend. Determinism is the point: the same fault plan against the same
scripted run must produce the same trace, bit for bit.

## Contract

- `Fault` (core type): `family`, `target`, `step`, `seed`. For in-process
  injection, `step` means **the Nth occurrence (1-based) of the target**:
  for tool families the Nth invocation of that tool, for `api_throttle`
  the Nth model call. Each fault fires exactly once (consumed).
- `FaultPlan(faults)` — matching engine with consumed-tracking;
  `match_tool(name, occurrence)` / `match_llm(occurrence)`;
  `unconsumed()` lets the bench assert the plan was fully exercised.
- `InjectedToolRegistry(inner, plan, trace=None)` — same surface as
  `ToolRegistry`. On a match it substitutes a synthetic classified result
  (`tool_error` → ERROR/retryable "injected transport failure";
  `tool_timeout` → TIMEOUT/retryable) **without executing the tool**, and
  emits a `fault_injected` event when a trace is attached.
- `InjectedBackend(inner, plan, trace=None)` — same surface as a backend.
  On a match raises `ApiThrottleError` (status_code 429). The loop has no
  backend retry yet, so an unhandled throttle kills the run — which is
  itself a legitimate crash mode for the bench to measure.

## Alternatives considered

- Monkeypatching in scenario code — invisible in the trace, not portable to
  external adapters, and impossible to audit.
- Proxy at the HTTP layer — right for external runtimes later (adapters),
  overkill for the reference harness whose chokepoints we own.

## Decision

Wrapper objects around the two chokepoints, driven by a declarative plan;
injection is always visible in the trace (`fault_injected` sits between
`tool_start` and `tool_end`).

## Out of scope

Process kill (the bench runner does real kills at the process level — a
simulated in-process "crash" would test less than the real thing); faults
of the class "effect happened but the result was lost" (P2, needs the
intent journal); clock skew injection (hook point reserved at the gate).

## Test plan

Plan matching fires on exact occurrence, once; wrapped registry substitutes
without executing; timeout family maps to TIMEOUT; specs passthrough;
throttle raises at the Nth model call; loop integration: injected tool
error is fed back and the run recovers, with `fault_injected` in the trace.

## Status log

| Date | State | Note |
|------|-------|------|
| 2026-08-18 | building | |
