# Squawk 0405: The debrief's gate-reuse rule treats a doc under `the_one/` as code

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-23
**Completed**: 2026-11-24

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
In `.flightops/agent-crews/flight-debrief.md` "Test metrics: reuse the flight's gate": the reuse
check now also ignores Markdown under `the_one/` (`the_one/agents.md` and other developer docs).
Code, tests and scripts stay triggers. The app guide `the_one/gleepglorp/guide/*.md` stays a
trigger: it is shipped product text with a drift test (`tests/test_gleepglorp_guide.py`). A new
bullet covers the operator-deferred timing re-measure: reuse the gate's counts, record its timings
as reference only, cite the deferral (gap recorded at the Mission 36 Flight 3 debrief).

## Verification
The rule's wording exempts Markdown under `the_one/` except the app guide (and keeps code and tests
as triggers). This is an operator-owned methodology file, so the operator approves the wording.
Wording approved by the operator, 2026-11-24 (as drafted; the app guide stays a trigger).

## Sign-Off
**Reviewer**: Reviewer agent (Haiku), batch review of squawks 0403, 0404, 0405, 0407, 0408, 0409 and 0410; wording approved by the operator
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-24` on squawk/turnaround-2026-11-24
