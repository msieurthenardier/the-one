# Squawk 0166: confirm-lapse browser test is flaky under host load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-10
**Completed**: —

## Report
`tests/browser/test_confirm_contract.py::test_lapse_is_visually_distinct_and_clears_on_next_interaction`
fails intermittently in the parallel `shared` lane when the host is loaded
(load average about 20). It passes 3/3 in isolation on a quiet host. Seen in
Mission 27 Flight 1, gate run 2. It uses a test-only `revertMs: 50`, so the
lapse timer can fire before the next Playwright step observes the armed state.

## Evidence
- `tests/browser/test_confirm_contract.py:115` (`def test_lapse_is_visually_distinct_and_clears_on_next_interaction`);
  `:129` and `:150` (`App.confirmDelete(el, function () {}, { revertMs: 50 })`).
- The Mission 27 Flight 1 flight log, "Gate run 2": it failed during a
  Developer's lane run at a load average of about 20, then passed 3/3 in
  isolation.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
