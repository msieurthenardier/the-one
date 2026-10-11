# Squawk 0173: Stale CLAUDE.md lines in the Mission 28 time-zone paragraphs

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
The CLAUDE.md "Time zone setting (M28 F1 L1)" paragraph still ends "Nothing here changes how agents are built yet", which has been false since Flight 1 leg 2. The next paragraph says `current_time` is "seeded into every turn"; it means the starting toolset.

## Evidence
`CLAUDE.md`, the Architecture section's M28 paragraphs (~lines 236-238). Found by the M28 F1 debrief Architect.

Logged from the Mission 28 flight debriefs.

## Corrective Action
CLAUDE.md M28 paragraphs: removed 'Nothing here changes how agents are built yet'; 'seeded into every turn' became 'part of every agent's starting toolset'. Added one clause each for time_tool_available failing closed (0182), App.time.onChange(fn, ownerEl) and applySettings/effective.offset_minutes (0176, 0183; the Date and time page now says applySettings) and the global [hidden] reset (0178, in the App shell paragraph). agents.md already covered 0176/0182/0183; it lacked 0178, so one bullet was added under 'App shell — invariants'.

## Verification
Read the edited paragraphs back against agents.md lines on time_tool_available and App.time; ran tests/test_run_tests_lanes.py and tests/test_ui_guards.py (34 passed).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
