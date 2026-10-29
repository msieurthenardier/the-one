# Squawk 0287: Name the approval and migration patterns in agents.md Project Conventions

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-29
**Completed**: —

## Report
Mission 33 Flight 3 introduced two reusable patterns. Both are described
only inside the routines sections of `the_one/agents.md`, not in its
"Project Conventions" list of named patterns:
- **Verbatim stored pair plus re-render at apply.** A proposal stores the
  normalized value with its exact instant (`schedule` plus `anchor_at`).
  Approval applies it verbatim, re-rendering only the display (`rezone`),
  and never re-normalizes against approval time.
- **Frozen migration converter with a guarded failure row.** A data
  migration carries its own converter, not the live normalizer. An
  unreadable row is turned off with one guarded history row instead of
  failing startup (v48).

## Evidence
- `missions/33-routines/flights/03-schedules-and-limits/flight-debrief.md`,
  Recommendation 5.
- `the_one/routines/service.py` (the approval pair and `rezone`) and the
  `the_one/db/schema.py` v48 block.
- `the_one/agents.md` "Project Conventions" has no entry for either.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

`the_one/agents.md` "Project Conventions" has a named entry for each
pattern. Each entry gives one example citation and the reason for the
pattern.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
