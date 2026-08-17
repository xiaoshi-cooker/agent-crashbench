# Roadmap

The project ships in phases, each closed by a tag and a retro note under
`docs/retro/`. Modules get a design doc under `docs/design/` **before** they
get code. Dates are indicative; phases close on deliverables, not on the
calendar.

## Core claim this project works toward

> Kill the agent at any step. Resume it. The ledger proves nothing ran twice
> and nothing verified was lost.

Mainstream agent frameworks snapshot loop state, but tool side effects
between snapshots remain at-least-once: a crash mid-tool-call (did the email
go out?) is exactly where duplicates and silent losses happen. This repo
imports battle-tested recovery engineering from databases and distributed
systems into the agent loop — and builds the rig that measures whether any
runtime (including this one) actually meets the bar.

- **Intent journal (WAL for tool calls)** — journal the intent before a
  side-effecting call; reconcile journal vs. effect ledger on resume.
- **Idempotency keys** at the tool gateway — duplicate execution becomes a
  no-op at the effect boundary.
- **Replay-based state reconstruction** — checkpoints address positions in
  the event log; LLM responses are memoized so rebuilds are deterministic
  (durable-execution style).
- **Crash-only design** — there is no graceful path: every start is a
  recovery (an empty log means a fresh run), so recovery code is the
  most-exercised code in the repo.
- **Crash-point sweep** — faults are swept across every step boundary, not
  sampled; correctness means the recovered effect trace is equivalent to
  some fault-free run.

## Phases

### Phase 0 — Foundations (done)
Repo, Apache-2.0, frozen core contracts (canonical JSON, content-addressed
checkpoints, integer-microsecond timestamps), CI, content guard.

### Phase 1 — Walking skeleton (~2 weeks)
Mock-first loop with JSONL trace, tool registry (schema validation, timeout,
retry classification), record/replay layer, checkpoint/resume
(restore-latest), first skill-defined scenario, effect-ledger MVP.
Internal milestone; every module lands with its design doc.

### Phase 2 — Prove it (→ v0.1, ~1 month mark)
Intent journal + idempotency keys + resume reconciliation. Fault injector
(process kill / tool timeout & error / API throttling) with crash-point
sweep. Three scenarios, two baselines (restart-from-zero, naive-resume).
Static HTML flight recorder (timeline, crash-vs-resume diff). Minimal
LangGraph adapter. First real-model report.

### Phase 3 — Compare and show (v0.2)
Scenario suite 8–12, regression suite in CI, multi-model leaderboard,
LangGraph recovery-behavior report (+ upstream issues where warranted),
live flight-recorder viewer (FastAPI) started.

### Phase 4 — Measure the field (v0.3)
Second external adapter, arXiv measurement paper draft, viewer polish,
companion-library evaluation for external checkpointers.

### Phase 5 — Evolve (v1.0)
Gated self-improvement loops: failure attribution → config/skill patch
proposals → bench-gated acceptance with an audit trail. Additional recovery
policies behind the checkpoint selection strategy interface.
