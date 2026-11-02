# Squawk 0309: the routine log line vocabulary has no single guard and its scheduler formatting is repeated

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

## Report
Mission 34 Flight 2 made the routine log lines an operator-facing contract (`the_one/agents.md` "Routine log lines"; the behavior test `routine-run-observable-from-logs` greps them). The decision lines in `the_one/routines/scheduler.py::_handle` repeat the `routine decision=… routine=%s agent=%r … late_s=%.1f` formatting in four branches, and nothing pins the vocabulary as a whole: a renamed key or decision word breaks operator grep recipes and the behavior test while each unit test, asserting its own line, is edited along with it. Extract a `_log_decision(...)` helper (as `service.py::_log_proposal` already does for proposals) and add one unit test that pins the decision words and key order of every routine line family (`decision=`, `run=… started|outcome=`, `proposal=… decision=`, `purge sweep`).

## Evidence
- `the_one/routines/scheduler.py:223` (`unreadable_due`), `:242` (`skip_changed`), `:268` (`missed`), `:288` (spawn / still_running_skip) — four inline format strings.
- `the_one/routines/service.py::_log_proposal` — the existing single-helper pattern.
- Mission 34 Flight 2 debrief (Developer interview), Action Items.

## Corrective Action
*(written at completion)*

## Verification
- One helper formats every scheduler decision line; the emitted text is byte-identical to today's (existing caplog tests pass unchanged).
- A new vocabulary test fails when a decision word or key is renamed (falsified by editing, then restored by editing); `make test-unit` passes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
