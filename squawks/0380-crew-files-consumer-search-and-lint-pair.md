# Squawk 0380: Crew files do not ask for a recorded consumer search or for the lint pair

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
Two lines are missing from the project's crew files; each cost sortie 18 a review finding (flight debrief, recommendations 1 and 2).

1. `.flightops/agent-crews/flight-design.md`, the Architect's design review: when a design replaces or removes a control, an element id or a selector, the review should list the patterns and folders it searched before a "nothing else uses it" prerequisite is ticked. The patterns are the id, the attribute in quoted and unquoted forms, the control's owned classes and its testids; the folders are `tests/`, `scripts/`, `docs/`, `evals/` and `tests/behavior/`. Sortie 18 ticked "the capture script has no selector on the args chips" after a search for two spellings; the script used a third (`[data-field=args]`).
2. `.flightops/agent-crews/leg-execution.md`, the Developer "Implement" prompt: before `[LAND:leg]`, run `ruff check` and `ruff format --check` on the files the leg touched. Sortie 18's leg 1 added two contract test files that failed the format check, which is a CI gate; the flight Reviewer caught it.

Both are wording additions to project crew prompts. No source change.

## Evidence
- `.flightops/agent-crews/flight-design.md` — the review checklist has "Prerequisites — are they accurate?" and no line about recording a search.
- `.flightops/agent-crews/leg-execution.md` — no mention of `ruff` or lint.
- `sorties/18-mcp-arguments-as-rows/flight-debrief.md` — "What Could Be Improved / Process", and recommendations 1 and 2.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
