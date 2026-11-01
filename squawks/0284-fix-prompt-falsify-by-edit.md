# Squawk 0284: The fix prompt should require falsifying a new test by edit, not by a whole-file restore

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-29
**Completed**: 2026-10-29

## Report
In Mission 33 Flight 2's Batch B review fixes, a fix Developer had to prove
its new tests could fail. It removed its fix, ran the tests, and then put
both whole JS files back from backup copies. In the shared working tree,
where other crew and the Flight Director keep uncommitted edits, a
whole-file restore can silently drop a concurrent edit. None was lost this
time. The FD added "put the fix back by editing — do not restore from a
backup copy of the whole file" by hand to the next fix prompt, and that
worked.

## Evidence
- The Developer's report: "I then restored both files from backups."
- `missions/33-routines/flights/02-agent-routines/flight-debrief.md`,
  Methodology Observation 3 and Recommendation 5.
- `.flightops/agent-crews/leg-execution.md`, "Developer: Fix Review Issues".
  The prompt asks for tests and forbids `git stash`, `checkout --`,
  `restore`, `reset` and `clean`, but it says nothing on how to falsify.

## Corrective Action
The "Developer: Fix Review Issues" prompt in `.flightops/agent-crews/leg-execution.md` now says a falsification removes the fix by editing and puts it back by editing, never by restoring a whole file or a backup copy. The Implement prompt does not ask for falsification, so it is unchanged.

## Verification
The prompt states the rule (read `.flightops/agent-crews/leg-execution.md`, "Developer: Fix Review Issues").

## Sign-Off
**Reviewer**: Flight 3 Batch A Reviewer (Sonnet), independent of the implementing Developer; Accessibility Reviewer (Sonnet) for 0273
**Verdict**: confirmed (the batch's only blocking item, a lint failure in another file, was fixed in the review-fix pass)
**Commit**: the Mission 33 Flight 3 Batch A commit, `flight/3: Batch A - routes moved, caps and retention, recurrence core, date and time controls`
