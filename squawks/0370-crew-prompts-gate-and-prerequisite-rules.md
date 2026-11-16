# Squawk 0370: Crew prompts lack four rules sortie 17 showed are needed

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-15
**Completed**: —

## Report
Sortie 17 pushed a commit with a red unit tier, marked its PR ready, and lost two HAT steps to an unverified prerequisite. Four additions to the project crew files (`.flightops/agent-crews/`) would have prevented each. They are project configuration, not plugin files.

1. **`leg-execution.md`, Developer "Implement" and "Fix Review Issues" prompts**: any edit after your gate run voids that run, including a test-only edit; re-run the unit tier after your last edit.
2. **Same prompts**: an edit under `tests/browser/` needs the unit tier's guards (`tests/test_nav_helper.py` at least) as well as the owning browser lane; the lane alone cannot see them.
3. **`leg-execution.md`, Reviewer prompt**: no background wait timers or polling loops; deliver one report. (A Reviewer re-sent its report four times as leftover timers fired.) Also: when the diff touches `tests/browser/`, run `tests/test_nav_helper.py`.
4. **`flight-design.md`, Interaction Protocol and the Architect prompt**: a prerequisite that depends on something only the operator has (a model, a server, an account, a token) needs evidence of one real use recorded in the flight artifact before it is ticked; the Architect flags a ticked box with no evidence as high severity.

Also worth a line in the Interaction Protocol of `leg-execution.md`: before a flight is marked landed, the Flight Director runs `THE_ONE_TEST_NETNS=1 make test-unit` on the committed tree and records its result line in the flight log.

Why now: the second flight in a row with an unverified HAT prerequisite (sortie 16, then 17), and the first red commit to reach a ready PR since the gate rules were written.

## Evidence
- `sorties/17-thinking-follows-the-model/flight-log.md` — "debrief found the unit tier red; fix pass" and "HAT walked; flight landed".
- `sorties/17-thinking-follows-the-model/flight-debrief.md` — recommendations 1 and 2, methodology observations 1, 2 and 6.
- `sorties/16-turn-work-group/flight-debrief.md` — recommendation 4 and methodology observation 4 (the same prerequisite miss).
- `.flightops/agent-crews/leg-execution.md` — the "no sleep timers" paragraph is in the Developer "Implement" prompt only.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
