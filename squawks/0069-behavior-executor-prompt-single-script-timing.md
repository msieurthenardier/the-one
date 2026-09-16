# Squawk 0069: Executor prompt: measure "within N s of an API call" with the trigger and the first poll in one process; capture HTTP status

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: —

## Report

Behavior test `kb-folder-watch-round-trip` Step 4 went INCONCLUSIVE on its
first attempt because the Executor issued the settings PUT and started its
1 s poll loop as separate tool calls, leaving ~9 s with no sample inside the
5 s window; the rerun bundled both in one shell script (first sample 4 ms
after the response) and the rule was written into that spec's Row
conventions. The Validator also noted that early steps' evidence files
carried response bodies without a captured HTTP status line. Both rules
belong in the project's Executor prompt
(`.flightops/agent-crews/behavior-tests-execution.md`) so every spec
inherits them rather than re-learning them.

## Evidence

- `.flightops/agent-crews/behavior-tests-execution.md:183` — `### Executor: Initial` (no timing-measurement or status-capture guidance)
- `tests/behavior/kb-folder-watch-round-trip.md`, Row conventions, "Measurement conventions (adopted after the first run)"
- `tests/behavior/kb-folder-watch-round-trip/runs/2026-09-16-21-49-20.md`, Checkpoint 4 and the Validator closing

## Corrective Action

*(written at completion)*

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition

*(only for deferred or escalated squawks)*
