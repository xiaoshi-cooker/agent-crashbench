# Design doc: <module name>

> Copy this template to `docs/design/<module>.md` and fill it in **before**
> writing the module's code. Keep it under ~2 pages: it exists so that work
> can stop at any point and be resumed later — by anyone — with the intent
> intact.

## Goal

What this module must make true, in one or two sentences. Include the user-
visible symptom of it working.

## Contract

The public interface: core types consumed/produced, function signatures
(2–5), events emitted, invariants guaranteed. Reference `harness/core/types.py`
rather than redefining types.

## Alternatives considered

2–3 options with one line each on why they were not chosen. Name prior art
borrowed from (framework, paper, or system) — borrowing is encouraged and
must be cited.

## Decision

The chosen design and the reason it wins. Note anything deliberately deferred
and where the extension point lives.

## Out of scope

What this module intentionally does NOT do in this phase.

## Test plan

- Unit: the 3–5 behaviors that must have tests before merge.
- Fault: how this module misbehaves under injected faults, and which
  scenario/bench case will cover it.

## Status log

| Date | State | Note |
|------|-------|------|
| YYYY-MM-DD | draft / building / shipped | |
