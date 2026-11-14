# Squawk 0362: a widget-lifecycle contract test reads the frame's load count before the load is counted

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: —

## Report
`tests/browser/test_ui_widget_lifecycle_contract.py::test_nine_loaded_unloads_the_oldest_visible_paused_auto[webkit]` failed once in a full `--parallel 3` browser run and passes when run alone. The product is not at fault; the test has a race.

After scrolling the first card back into view, the test waits for `__cards[0].state() === 'running'` and then at once asserts `__cards[0]._frame().loads() == 1`. A card's state reads `running` as soon as it mounts, before its frame's `load` event has been counted, so under load the count is still 0.

Failure: `AssertionError: assert 0 == 1` at the `_frame().loads()` assertion.

Reproduce: run the full gate (`make test-browser`) on a busy host. It does not reproduce alone.

Expected: the test waits for the load to be counted (for example `wait_for_function("() => __cards[0]._frame().loads() === 1")`) before asserting it.

## Evidence
- `tests/browser/test_ui_widget_lifecycle_contract.py::test_nine_loaded_unloads_the_oldest_visible_paused_auto` — the `wait_for_function` on `state() === 'running'` followed immediately by `assert p.evaluate("() => __cards[0]._frame().loads()") == 1`.
- Sortie 16's debrief gate (2026-11-14, commit `1a458bcf`): `PARALLEL_RESULT rc=1 total=2180s lanes=20 failed=contracts-widget-lifecycle` (1 failed, 112 passed); the test then passed 3 of 3 alone, both engines, in about 2.4 s.
- Sortie 16 changed no file in this area (`git diff 7d6ab953..1a458bcf` touches neither `js/ui/widget*.js` nor this test file).
- The same root cause, "state reads `running` as soon as it mounts", is recorded for another test in this lane in squawk 0351.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*

## Disposition
**Deferred**: found at sortie 16's debrief gate, in code and tests the sortie did not touch — revisit at the next squawk turnaround, with 0359 (the same kind of race in the `agents` lane). Check the lane's other tests for the same "running, then read the frame" pattern while there.
