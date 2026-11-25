# Squawk 0410: Crew prompts need the `pgrep -f` self-match trap and a logs-in-the-scratchpad rule

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

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
*(written at completion)*

## Verification
The Implement and Fix Review Issues prompts say:
- `pgrep -f <pattern>` matches the agent's own shell command, so a wait loop on it never ends;
  wait for the run's completion notification instead;
- logs and scratch files go only in the session scratchpad, never the repo or `$HOME`.

This is an operator-owned methodology file, so the operator approves the wording.
