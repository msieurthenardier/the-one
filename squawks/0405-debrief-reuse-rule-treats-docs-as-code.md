# Squawk 0405: The debrief's gate-reuse rule treats a doc under `the_one/` as code

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-23
**Completed**: —

## Report

`.flightops/agent-crews/flight-debrief.md` "Test metrics: reuse the flight's gate" allows reuse
only when the diff since the gate touches nothing under `the_one/`, `tests/` or `scripts/`, except
the lane-budget table. A closing re-budget always edits `the_one/agents.md` (its budget history and
gate target), which is a doc. So the rule forces a fresh unit run at every debrief.

At the Mission 36 Flight 4 debrief that run matched the gate exactly (11898 passed / 15 skipped)
and cost about 6.5 minutes. Exempt Markdown under `the_one/` (at least `the_one/agents.md`) from the
trigger. Found by the Flight 4 debrief.

## Evidence
- `.flightops/agent-crews/flight-debrief.md`: "`git diff <gate commit>..HEAD` touches nothing under
  `the_one/`, `tests/` or `scripts/` except the lane-budget table in `scripts/run-tests.sh`".
- Flight 4: the gate at `3178ae7d` gave unit 11898/15 in 387 s; the fresh run at `604e052c` gave
  11898/15 in 384 s.

## Corrective Action
*(written at completion)*

## Verification
The rule's wording exempts `*.md` under `the_one/` (and keeps code and tests as triggers). This is
an operator-owned methodology file, so the operator approves the wording.
