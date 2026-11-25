# Squawk 0410: Crew prompts need the `pgrep -f` self-match trap and a logs-in-the-scratchpad rule

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-24

## Report

In Mission 36 Flight 5, crew agents again wrote `pgrep -f` wait loops that matched their own
command line, so they never ended, and one left a log file in the home folder. The leg-execution
crew prompts already forbid "`pgrep` wait loops", but not why one never ends, and they say nothing
about where logs go. This is the same class as Flight 4. Found by the Flight 5 debrief
(Developer and Architect).

## Evidence
- `.flightops/agent-crews/leg-execution.md:190`: "Do not start backgrounded `sleep N` timers or
  `pgrep` wait loops."
- Flight 5 flight log: the Reviewer and a fix Developer each used a self-matching `pgrep -f` wait,
  and a stray log was written under `$HOME`.

## Corrective Action
In `.flightops/agent-crews/leg-execution.md`:
- "Developer: Implement": extended the "Waiting on a long run" paragraph with the reason a
  `pgrep -f` wait never ends (it matches the agent's own shell command) and the
  scratchpad-only rule for logs and scratch files.
- "Developer: Fix Review Issues": added a short "Waiting on a long run" paragraph with the
  same two points.
- "Reviewer: Review": added one sentence, since the Reviewer runs tests itself and the
  Flight 5 Reviewer hit the same trap.

## Verification
The Implement and Fix Review Issues prompts say:
- `pgrep -f <pattern>` matches the agent's own shell command, so a wait loop on it never ends;
  wait for the run's completion notification instead;
- logs and scratch files go only in the session scratchpad, never the repo or `$HOME`.

This is an operator-owned methodology file, so the operator approves the wording.
- Wording approved by the operator, 2026-11-24 (all three passages, including the Reviewer prompt).

## Sign-Off
**Reviewer**: Reviewer agent (Haiku), batch review of squawks 0403, 0404, 0405, 0407, 0408, 0409 and 0410; wording approved by the operator
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-24` on squawk/turnaround-2026-11-24
