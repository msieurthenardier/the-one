# Squawk 0187: agent-rules failed-toggle focus test is flaky under host load

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
`tests/browser/test_flow_agent_rules.py::test_failed_toggle_and_failed_save_restore_focus`
failed once in the sortie 02 leg 1 `--parallel 3` gate (agents lane, 474/510 s wall):
after a failed toggle it found no focused element. It passed in isolation and in a
re-run of its file. Not related to sortie 02's change (the Rules and notes tab is untouched).

## Evidence
- `tests/browser/test_flow_agent_rules.py:232` (`def test_failed_toggle_and_failed_save_restore_focus`).
- `sorties/02-model-providers-in-library/flight-log.md`, leg `library-and-providers`, Part B gate.

## Deferral
Found mid-flight in sortie 02, out of scope. Revisit trigger: the next squawk turnaround,
or the next time the Rules and notes tab or `App.focusAfter` is touched, whichever comes first.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
