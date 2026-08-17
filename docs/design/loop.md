# Design doc: loop (agent core)

## Goal

A minimal, event-transparent ReAct loop: given a Task and a backend, run
model→tools→model until a final answer or `max_steps`, emitting an Event for
every state change so the trace alone can reconstruct the run. The loop is
the primary object under test for the bench — it must be boring, observable,
and interruptible at every boundary.

## Contract

- `AgentLoop(backend, tools, trace_writer, max_steps=20)`
  - `run(task: Task) -> RunResult` — drives the loop to completion.
  - `step() -> bool` — executes one turn (one model call plus its tool
    calls); returns False when the run is finished. `run` is just
    `while step(): pass` — the bench kills processes between/within steps.
- `RunResult` — `task_id`, `status: TaskStatus`, `final_answer: str`,
  `steps: int`.
- Events emitted: `run_start`, `llm_call` (request digest + response
  summary), `tool_start`/`tool_end` per call, `run_end` (status). Message
  assembly is inlined in P1 (system + goal + turn history) and moves to the
  context module in a later P1 commit.
- State lives in plain fields (`turns`, `step_count`) rebuilt from
  checkpoint payloads (P1) and later from log replay (P2).

## Alternatives considered

- Graph/state-machine engine (LangGraph-style) — more expressive, but the
  bench needs a transparent reference loop whose every transition is an
  event; graphs are one of the *external* subjects, via adapters.
- Callback/hook framework (CrewAI-style) — hooks hide control flow and
  swallow errors (course-project experience); explicit `step()` keeps
  crash points enumerable, which the crash-point sweep requires.

## Decision

Plain-Python explicit loop with `step()` as the atomic unit; every boundary
double-bracketed by events; no hidden state.

## Out of scope

Planning modes, reflection, subagents, context compression, streaming —
all later phases; interfaces stay open via events and the tools registry.

## Test plan

- Unit (mock backend): completes a 2-tool scripted task; honors max_steps;
  emits the full event sequence in order; tool error surfaces in events and
  turns.
- Fault: killing between any two events leaves a readable trace (torn tail
  at worst) — bench scenarios build on this.

## Status log

| Date | State | Note |
|------|-------|------|
| 2026-08-17 | draft | implement after trace + mock land |
