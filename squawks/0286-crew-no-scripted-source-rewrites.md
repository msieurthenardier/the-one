# Squawk 0286: Crew prompts should forbid helper scripts that rewrite source files

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-29
**Completed**: 2026-10-29

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
Edited `.flightops/agent-crews/leg-execution.md` only:
- "Developer: Implement": added a paragraph before "If a test hangs": no helper
  script that writes a source or test file, edit tools only, the falsify-by-edit
  rule (0284) restated, a rebuilt file reported with `git diff HEAD -- <path>`, and
  a per-new-test falsified yes/no where the leg asks for falsification.
- "Developer: Fix Review Issues": kept the squawk 0284 sentence and added the
  same rule beside it (squawk 0286), with the per-new-test falsified yes/no.

## Verification
The "Developer: Implement" and "Developer: Fix Review Issues" prompts both
state the following:
- never write or run a helper script that writes a source or test file;
- edit source and test files only through the edit tool;
- a file that had to be rebuilt is reported with a diff against HEAD;
- a fix pass records, for each new test, whether it was falsified (yes or
  no).

Checked by reading the edited file: both prompt blocks now contain "Never write or
run a helper script ... that writes a source or test file; edit source and test
files only through the edit tool (squawk 0286)", "A file that had to be rebuilt is
reported with a diff against HEAD (`git diff HEAD -- <path>`)", and a per-new-test
falsified (yes or no) report line. The 0286 change touches only the crew file and
this squawk.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku), scoped to the diff of the 0286/0287
batch, `[HANDOFF:confirmed]`. Both prompts meet every Verification bullet, the
0284 sentence is preserved and no other prompt changed. Its two non-blocking
notes were on this artifact (a duplicated criteria list and a `git diff --stat`
claim true only before 0287's edits); the FD applied both.
**Verdict**: confirmed
**Commit**: (this commit, `squawk: turnaround 2026-10-29`, on `squawk/turnaround-2026-10-29`)
