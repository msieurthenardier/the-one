# Squawk 0286: Crew prompts should forbid helper scripts that rewrite source files

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-29
**Completed**: —

## Report
In Mission 33 Flight 3 leg 4a, a Developer wrote a falsification helper
script that rewrote `the_one/routines/scheduler.py` and truncated it. It
then rebuilt the file from `git show HEAD:` plus its edits. Squawk 0284's
falsify-by-edit rule was already in the "Fix Review Issues" prompt, but:
- the "Implement" prompt does not carry it;
- the rule says nothing about scripts.

The Batch B Reviewer's line-by-line diff against HEAD proved nothing was
lost; the tests alone could not. Several fix-pass Developers also reported
new tests they had not falsified. The operator chose a hard rule at the
Flight 3 debrief.

## Evidence
- `missions/33-routines/flights/03-schedules-and-limits/flight-log.md`, the
  "Incident" note after leg 4a, and the Batch B review entry.
- `missions/33-routines/flights/03-schedules-and-limits/flight-debrief.md`,
  Methodology Observation 3 and Recommendation 1.
- `.flightops/agent-crews/leg-execution.md`: "Developer: Implement" has no
  edit-mechanism rule; "Developer: Fix Review Issues" has the 0284 rule,
  which covers only whole-file restores.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

The "Developer: Implement" and "Developer: Fix Review Issues" prompts both
state the following:
- never write or run a helper script that writes a source or test file;
- edit source and test files only through the edit tool;
- a file that had to be rebuilt is reported with a diff against HEAD;
- a fix pass records, for each new test, whether it was falsified (yes or
  no).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
