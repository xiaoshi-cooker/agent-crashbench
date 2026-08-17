# Retro: Phase 1 — substrate skeleton

Closed at tag `substrate-v1` (2026-08-18, ~2 weeks ahead of plan).

## Shipped

15 commits, 86 tests, CI green on every push. Roughly 1,700 lines of
source and 1,000 lines of tests across:

- **core**: canonical JSON + content addressing; frozen contracts
  (Task/Turn/ToolCall/ToolResult/Event/Checkpoint/MemoryEntry/Skill/
  Fault/Scenario/LedgerEntry); integer-microsecond UTC timestamps.
- **trace**: append-only JSONL per run; reopen-continues (boot is resume);
  WAL-style torn-tail tolerance on read, truncation repair on reopen.
- **llm**: narrow backend protocol; scripted mock as a first-class
  deterministic backend; record/replay cassette (fail-closed replay,
  per-key FIFO for repeated requests).
- **tools**: single-entry gate; failures are classified data, never
  exceptions; timeout budget = min(registered, per-call), with
  internal-TimeoutError disambiguation.
- **loop**: explicit `step()` as the atomic unit; every boundary emits an
  event; the trace alone reconstructs a run (asserted in tests).
- **checkpoint**: content-addressed store, atomic replace, fail-closed
  verification; `select()` as the single checkpoint selection strategy
  function; restore + continue_run.
- **faults** (bench side): declarative FaultPlan, occurrence-based
  matching, chokepoint wrappers; injections always visible in the trace.
- **oracle** (bench side): out-of-process verdict envelope with
  verdict/exit-code interlock (exit 1 deliberately unused) and a
  mandatory identity block.

Flagship integration test: stop a run mid-flight, restore in a "fresh
process", finish — the already-executed tool call does not run again and
the trace stays one contiguous sequence across both lives.

## Design vs. reality

- Message assembly stayed inline in the loop; the context module slipped
  from "later in P1" (loop.md) to P2. Right call: P1's job was the
  crash-recovery substrate, not context management.
- `llm_call` events digest `messages` only, while the cassette keys on
  `messages + tools`. Two digests, two purposes today — unify when
  replay-based state reconstruction lands (P2), because then the event
  digest must equal the memoization key.
- Loop type hints name concrete classes (`ToolRegistry`, `TraceWriter`)
  but the fault wrappers duck-type them. Introduce explicit Protocols in
  the P2 API pass rather than now.
- Several contract types (MemoryEntry, Skill, Scenario, LedgerEntry) are
  defined but not yet consumed — contracts deliberately ahead of use.

## Measurements

- 86 tests, ~0.4 s locally; CI 12–17 s per push on ubuntu.
- 15 commits over 3 calendar days; every push passed the external
  content guard (25-term list, 53 files, zero hits).

## Failures worth keeping

- Windows GBK subprocess decoding broke the content-guard script on its
  first run (UTF-8 commit message, GBK-decoding subprocess pipe). Fix:
  explicit `encoding="utf-8", errors="replace"` on every subprocess call.
- The torn-tail corner: tolerating a torn line on read while keeping the
  reader strict elsewhere only works if the *writer* repairs (truncates)
  the tear on reopen — read-side tolerance alone would have forced the
  reader to accept garbage mid-file after the next append.
- A tool that raises `TimeoutError` internally is indistinguishable from
  a budget overrun unless you check `future.done()` — without that, tools
  could masquerade their own bugs as infrastructure timeouts.

## Seeds

- Blog: "Boot is resume: WAL discipline for agent traces" (trace design).
- Blog: "Your mock is a product: deterministic backends and fail-closed
  cassettes for agent CI."
- Blog: "Exit code 1 means nothing: designing an oracle protocol whose
  crashes can't be mistaken for verdicts."
- README claim now honest at skeleton level: interrupted runs resume
  without re-executing completed tool calls (single-process, mock-backed;
  process-kill sweeps arrive with the bench runner in P2).
