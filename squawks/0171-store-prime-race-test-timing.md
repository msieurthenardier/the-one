# Squawk 0171: `test_store.py` prime-supersedes test is timing-sensitive under parallel load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
`tests/browser/test_store.py::test_prime_supersedes_a_racing_older_get`
failed once in the `routing` lane of a parallel `make gate` (Mission 28
Flight 2 leg 1). `assert len(held) == 1` saw 0. The test's
`page.wait_for_function("() => true")` does not wait for the route handler
to capture the held request, so under 3-lane load the assertion can run
before the handler fires. It passed in isolation and in 3 whole-file runs
(21 passed each).

## Evidence
- M28 F2 leg 1 gate: `PARALLEL_RESULT rc=1 total=982s lanes=8 failed=routing,shared`;
  routing's only failure was this test.
- The likely fix: wait on the capture itself (`page.wait_for_function` on a
  flag the handler sets, or `expect.poll(lambda: len(held))`), not on
  `() => true`.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

## Disposition
**Deferred**: a test-only timing fix, outside Mission 28's scope. Revisit
at the next squawk turnaround, or the next time `tests/browser/test_store.py`
is touched.
