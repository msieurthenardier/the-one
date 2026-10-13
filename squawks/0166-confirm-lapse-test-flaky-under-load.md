# Squawk 0166: confirm-lapse browser test is flaky under host load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-10
**Completed**: 2026-10-13

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
Test-only change in `tests/browser/test_confirm_contract.py`: the two `revertMs: 50` arms in `test_lapse_is_visually_distinct_and_clears_on_next_interaction` are now `revertMs: 1500`, so the armed state is observable between Playwright steps on a loaded host (the timer used to race the `to_have_class(confirm-delete)` and `not_to_have_class(confirm-lapsed)` reads). The bounded wait for the lapse went from 2000 to 6000 ms (it is an auto-retrying `expect`, so it returns as soon as the lapse lands). `confirm.js` is untouched. The other tiny-`revertMs` use (`revertMs: 30` in `test_missing_title_element_does_not_throw`) reads the armed state inside the same synchronous `evaluate`, so it cannot race and was left alone; the 60000 ms one is already long.

## Verification
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_confirm_contract.py -m browser -x --timeout 60`, 5 runs: 6 passed each time (about 12.2 s pytest, 13.4 s wall each). Wall time before: not measured with the old value (same run structure; the lapse wait was already about 50 ms, so the change adds about 1.5 s for the lapse wait only, and the 1.5 s second arm is not waited on).
- Same command with 12 background busy loops (PIDs recorded, killed): 6 passed in 18.5 s.
- `ruff check` and `ruff format --check` on the file: clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. Flake fix: the original failure was not reproduced, so there is no fails-without-fix demonstration.
