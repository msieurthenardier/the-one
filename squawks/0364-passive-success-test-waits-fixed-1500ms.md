# Squawk 0364: a queue test waits a fixed 1500 ms and never checks the last refetch ran

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: —

## Report
`test_passive_success_leaves_a_real_action_error` ends with a fixed `page.wait_for_timeout(1500)` and then asserts the action error is still showing. It never checks that the final passive refetch ran. If the refetch is slow or never happens, the assertion holds anyway, so the test can pass without testing anything.

Expected: count the route calls, as `test_repeated_failed_return_refetch_announces_once` does, and wait until the final refetch has been seen before the assertion.

## Evidence
- `tests/browser/test_studio_self_configuration_queue.py::test_passive_success_leaves_a_real_action_error`: the last lines are `page.evaluate("() => window.dispatchEvent(new Event('focus'))")`, `page.wait_for_timeout(1500)`, `expect(error).to_contain_text("Failed to enable")`.
- The pattern to copy: `test_repeated_failed_return_refetch_announces_once` in the same file.
- Found by the review of squawk 0318 (2026-11-14 turnaround).
