# agent-crashbench

A self-built agent harness, plus a proving ground that answers one question
with numbers: **after a crash, does your agent resume correctly — or does it
send the email twice?**

Two packages, one contract:

- **`harness/`** — a compact, white-box agent runtime built from first
  principles: agent loop, context management, short/long-term memory, tool
  governance (schema validation / timeout / retry classification), declarative
  skills, workflow pipeline, multi-backend LLM routing, checkpoint/resume,
  and a JSONL event trace.
- **`crashbench/`** — a fault-injection rig for long-horizon tool tasks:
  kill the agent mid-task (process kill, tool timeout/error, API throttling),
  resume it the official way, and measure what actually happened against an
  **out-of-process side-effect ledger**: task completion, duplicate side
  effects, and retained progress — compared to restart-from-zero and
  blind-resume baselines. Scenarios are defined as skills; adding a scenario
  means writing a `SKILL.md`, not patching the runner.

> Status: pre-v0.1, under active development. Interfaces change without
> notice. Deterministic mock mode is the primary CI target; real-model runs
> use any OpenAI-compatible endpoint.

## Why

Most agent frameworks treat "it resumed" as success. The interesting question
is whether the resumed run is *correct*: no duplicated external effects, no
lost verified progress, no silently rebuilt state. This repo makes that
measurable, first for its own harness, then for external runtimes via
adapters (LangGraph first).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
