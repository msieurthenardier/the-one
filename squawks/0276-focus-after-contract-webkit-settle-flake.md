# Squawk 0276: `App.focusAfter` contract test flakes in WebKit under load (fixed 60 ms settle)

**Status**: in-progress
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-27
**Completed**: —

## Report
`tests/browser/test_ui_focus_after_contract.py::test_cancel_after_restore_before_the_timer_cancels_the_focus[webkit]` failed once in Mission 31 Flight 6 leg 09b's quiet-host run, with `assert 'btn' == 'BODY'`. The run's result line was `PARALLEL_RESULT rc=1 total=1763s lanes=16 failed=contracts-overlay`.

- It passed 3 of 3 runs in isolation.
- A solo `--lane contracts-overlay` re-run passed (544 passed, 1 skipped).
- The failure depends on host load. The product code is not at fault.

## Evidence
- The test focuses `#btn` (`start`), then disables it and calls `restore` + `cancel`. It then waits through `settle()`, which is `page.wait_for_timeout(60)`, and asserts `document.activeElement` is `BODY`.
- `activeElement` still reading `btn` means the disabled button had not lost focus yet. WebKit blurs a focused element that becomes disabled lazily, at its next style or layout update, not synchronously.
- On a loaded host, that update can land after the fixed 60 ms wait. Several tests in the file share the same `settle()` + `active(...) == "BODY"` shape after disabling `#btn`, for example `test_disabled_or_detached_target_is_left_alone`.

## Corrective Action
Likely: make the wait deterministic.
- Either blur explicitly before asserting, since the test is about `focusAfter` and not about WebKit's disable-blur timing,
- or have `settle()` wait for two animation frames plus the `setTimeout(0)` focus.

Then wait for the condition (`wait_for_function`) instead of a fixed timeout. Apply this to every test in the file with the same shape.

Done: `settle()` in `tests/browser/test_ui_focus_after_contract.py` now waits 60 ms for the helper's timer and then waits (`wait_for_function`) until `document.activeElement` is not a disabled element, so every test sharing the shape is covered and WebKit's lazy blur is no longer a race. Test-only; no product code changed.

## Verification
- The file passes repeatedly in WebKit and Chromium under load. For example, run the `contracts-overlay` lane with `--count`, or loop the file 20 times alongside two other lanes.
- Each test still fails when `cancel()` is made a no-op, which proves the assertion still bites.

Result: the file passed 5 of 5 runs under both engines (24 passed each). With `App.focusAfter.cancel` a no-op, the three cancel tests failed in Chromium and WebKit (6 failed, 18 passed); reverted. The leg 09b quiet-host `--parallel 3` re-run, which includes this file in `contracts-overlay`, passed: `rc=0 total=1662s lanes=16`.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
