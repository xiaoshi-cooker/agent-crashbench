# Design doc: llm (backend protocol, mock, cassette)

## Goal

The loop talks to one narrow backend protocol. CI never needs a network:
a scripted mock drives unit tests, and a record/replay cassette memoizes
real-model responses so any recorded run replays deterministically —
memoization is a correctness mechanism for replay-based recovery, not just
a test convenience.

## Contract

- `LLMResponse` — `content: str`, `tool_calls: list[ToolCall]`,
  `usage: dict[str, int]`, `model: str`.
- `LLMBackend` (Protocol) — `complete(messages: list[dict],
  tools: list[dict] | None = None) -> LLMResponse`.
- `MockBackend(script: list[LLMResponse])` — returns scripted responses in
  order; records every call in `.calls` for assertions; raises
  `ScriptExhausted` when over-called (fail-closed, never silent).
- `Cassette(backend, path, mode)` (P1 tail / early P2) — key =
  `digest(messages + tools)`; `record` mode appends key→response JSONL;
  `replay` mode returns the recorded response and raises on a miss.

## Alternatives considered

- LiteLLM dependency — broad surface, version churn; we speak plain
  OpenAI-compatible HTTP ourselves in P2 (router module).
- Mock as monkeypatching in tests — leaves no reusable deterministic
  backend for bench scenarios; a first-class mock does.

## Decision

Protocol + dataclass response; mock is a first-class backend usable by the
bench, not a test fixture; cassette wraps any backend and is itself a
backend (composition).

## Out of scope

Real HTTP backend, streaming, multi-backend routing, cost tracking (P2,
router design doc).

## Test plan

- Unit: scripted order; exhaustion raises; call recording; response
  roundtrip via to/from dict (cassette persistence); cassette replay miss
  raises.

## Status log

| Date | State | Note |
|------|-------|------|
| 2026-08-17 | building | mock first; cassette next commit |
| 2026-08-18 | shipped (P1 scope) | mock + cassette landed; HTTP backend is P2 (router) |
