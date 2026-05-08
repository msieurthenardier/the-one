# Flight Log: Per-agent MCP attach + tool-routing in agent loop

**Flight**: [Per-agent MCP attach + tool-routing in agent loop](flight.md)

## Summary

In-flight. Orchestration started 2026-05-08 via `/agentic-workflow`. Branch `flight/06-mcp-attach-and-tool-routing` created from F5 branch tip (F4 + F5 stacked, both unmerged at PRs #31 + #32).

---

## Leg Progress

(append per leg as legs complete)

---

## Decisions

(append as runtime decisions surface)

---

## Deviations

(append as planned-vs-actual gaps surface)

---

## Anomalies

(append as unexpected issues surface)

---

## Session Notes

### 2026-05-08 — Flight start

Branch created. Flight artifact transitioned `ready` → `in-flight`. F5 + F4 stacked beneath; F6 PR will target F5 branch and rebase onto main once F4/F5 merge.

---

## Flight Director Notes

Transparency log for orchestration decisions. Per `agentic-workflow/SKILL.md` — "anyone reviewing the flight log can understand not just what the crew did, but why the Flight Director made the orchestration choices it did."

### 2026-05-08 — Phase 1: context loading + branch setup

- **Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project-side, NOT default fallback). Validated structure: `## Crew`, `## Interaction Protocol`, `## Prompts` all present; all prompt subsections have fenced code blocks.
- **Crew extracted**: Developer (Sonnet) for design-review + implement + fix + commit; Reviewer (Haiku) for code review; Accessibility Reviewer (Sonnet, optional) for UI legs only — F6 has zero UI surface, so the A11y Reviewer will NOT be spawned in this flight.
- **Branch strategy**: stacked. F4 PR #31 and F5 PR #32 are both open and unmerged; F6 builds on top of F5 (which builds on F4). Branch `flight/06-mcp-attach-and-tool-routing` created from current HEAD (F5 branch tip). PR will target the F5 branch initially; rebase to main once F4 + F5 land.
- **Total legs**: 5 required (L0, L1, L2, L3, L5) + 2 optional (L4 default-fold-into-L2, L6 default-fold-into-L5). HAT precedent says L5 is interactive — does NOT use autonomous Developer agent; the Flight Director guides the human through it step-by-step.

### Orchestration cadence reminder

Per F5 debrief recommendation #4 (Process #4 — context-budget pressure): after every 2 legs OR every ~3 hours of active orchestration, the Flight Director MUST checkpoint to the user. F6 has 5 implementation legs; expected checkpoint after L1 (post-2-legs) and after L3 (post-2-more-legs). L5 is human-interactive and naturally interrupts.

