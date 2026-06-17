# Leg: any-llm-evaluation

**Status**: landed
**Flight**: [Recon & Root-Cause Spike](../flight.md)

> **Outcome: HAND-ROLL.** any-llm (`any-llm-sdk` v1.17.0) fixes neither #122 nor
> #105 — its Anthropic adapter copies only `properties`/`required` (silently drops
> top-level combinators) and its Ollama adapter reads only structured `tool_calls`
> (no text-form recovery). Clean SDK-wrapper but stacks a second abstraction +
> adds dependency surface for no fix. Optional steal: its Anthropic usage mapping
> (cache tokens). See flight-log "any-llm evaluation (Leg 3)".

## Objective

Decide the mission's one remaining build-vs-adopt question: keep hand-rolling the
provider adapters, or delegate them to `any-llm` (Mozilla AI) behind the existing
`LLMProvider` seam — judged against whether any-llm solves the REAL bugs (#122
Anthropic schema sanitization, #105 text-form tool-call recovery) for free.

## Context

- Read-only source evaluation of an external library (no install). Delegated to a
  research agent with web access.
- Re-targeted from the mission's original framing: the evaluation now tests
  any-llm against the confirmed bugs (#122, #105), not the falsified thinking hole.
- Default lean (mission constraint): **hand-roll** — lowest dependency surface,
  full control, matches the reference tools (pi / openclaw).

## Acceptance Criteria

- [x] #122 sanitization — **no** (copies only `properties`/`required`, drops
      top-level combinators). Evidence: `anthropic/utils.py::_convert_tool_spec`.
- [x] #105 text-form recovery — **no** (reads only structured `tool_calls`).
      Evidence: `ollama/utils.py`.
- [x] Fit/maturity — clean SDK-wrapper, good streaming/usage; but 3.11+ floor +
      fat provider-dep surface; healthy project (active, Apache-2.0).
- [x] Recommendation: **hand-roll**.

## Verification Steps

- Agent's structured findings recorded in the flight log; decision noted for the
  synthesis leg to fold into the mission.

## Files Affected

- None (evaluation only; conclusion → flight log + synthesis).

---

## Post-Completion Checklist

- [ ] any-llm assessed against #122 and #105 with source evidence
- [ ] Recommendation recorded in flight log
- [ ] Leg status `landed`
