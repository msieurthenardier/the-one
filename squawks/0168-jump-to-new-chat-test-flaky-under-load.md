# Squawk 0168: jump-to "New chat" browser test is flaky under parallel load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-10
**Completed**: —

## Report
`tests/browser/test_flow_jump_to.py::test_new_chat_opens_the_agent_picker`
failed once in the `shared` lane in two of Mission 27's four parallel gates
(Flight 1 re-run; Flight 3 HAT gate). The whole file passes 24/24 three times
in isolation. It appears to be a timing race under host load, not a
regression; it never failed on its own.

## Evidence
- Flight 3 HAT gate: `PARALLEL_RESULT rc=1 … failed=shared`, the only
  failure. Re-runs of `test_flow_jump_to.py` in isolation: 24 passed, ×3.
- Mission 27 Flight 1 flight log, "Gate run 2": the same test, 3/3 in
  isolation.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
