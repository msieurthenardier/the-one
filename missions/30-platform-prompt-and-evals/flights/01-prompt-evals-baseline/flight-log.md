# Flight Log: Prompt evals and baseline

**Flight**: [Prompt evals and baseline](flight.md)

## Summary
Planning. The operator directed fully agentic execution with the data as the gates (2026-10-13).

---

## Leg Progress

---

## Decisions

### Haiku 4.5, not 5.5
**Context**: The plan token is refused (bare 429) for every Claude model except `claude-haiku-4-5-20251001` (sortie 03).
**Decision**: Haiku evals and the judge use `claude-haiku-4-5-20251001` (operator, 2026-10-13).

### Plan-token probe at planning
**Context**: External limits change without notice.
**Decision**: Status-only probe, 2026-10-13: one Haiku 4.5 call through `get_provider("anthropic-plan-token", …)` succeeded (14 input tokens). The token file has mode 600. Re-probe at the start of each live leg.

### Design review (two Architect cycles)
**Context**: The Flight Director drafted the spec from a read-only code interrogation and a debrief sweep.
**Decision**: Both cycles returned approve with changes, and every finding was applied.
- Cycle 1 added: distinct variants (DD9), a bare size target on prompt sections only (DD11), the sequence-scripted provider (DD18), containment (DD19), environment pinning (DD4), run-outcome rules (DD5), rendered-output fingerprints (DD15), and the split into four legs.
- Cycle 2 added: a guard → token → HOME start-up order, owner-locked sweeps, a cold Ollama count, `--measure-prompt` determinism, the safety fail on excluded runs, and a Verification table that expects today's prompt to fail its own improve bars.
- Carried to Flight 2: any `safety` cell below 20/20 at baseline becomes a hard gate with no divert path.

---

## Flight Director Notes

- **2026-10-13:** Loaded `.flightops/agent-crews/leg-execution.md`, which has all the required sections. The flight is now `in-flight`.
- **Leg 1 `runner-core`: high risk.** It is the surface that handles the plan token and enforces containment (scratch data directory and home, refusal of the operator's real data directory, tool allowlists). A Developer design review runs before implementation, and the flight-end Reviewer is Sonnet (security-sensitive tier).
- **Leg 1 design review:** approve with changes, all applied, no second cycle. They were targeted fixes, not a redesign. I kept the leg as one slice with an ordered build (a → b → c) instead of splitting it: the parts share one harness and their tests, and a split would mean three hand-offs over the same files.
