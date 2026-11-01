# Squawk 0304: two Routines browser tests fail intermittently inside the lane

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-31
**Completed**: —

## Report
Two run-timing tests in the `agent-routines` lane fail intermittently when the whole lane runs, and pass when run alone:
- `tests/browser/test_flow_agent_routines.py::test_run_now_conflict_shows_inline_message`. `routine-error` stays empty (`unexpected value ""`, `:679`). The test starts a run over the API against a 4 s mock delay, then clicks Run now and expects the 409 sentence. If the tab refreshes first and the click is not refused, nothing renders.
- `tests/browser/test_flow_agent_routines_form.py::test_immediately_runs_a_repeating_routine_at_once`. `_wait_runs` (`:1327`) polls 40 × 500 ms for a finished run.

## Evidence
Runs on 2026-10-31, from the sortie 07 worktree and its base `64519296`:
- Sortie 07 closing gate (`--parallel 3`, start load 1.23): the `agent-routines` lane failed only `test_run_now_conflict_shows_inline_message`, with 82 passed.
- Branch lane re-run (load 1.26, falling from 4.41): failed only `test_immediately_runs_a_repeating_routine_at_once`. A second branch re-run: 83 passed.
- **Base** lane (`64519296`, without the sortie): failed `test_run_now_conflict_shows_inline_message`, so the flake is not from the sortie.
- Isolated: each test passed 5/5 on the branch. On the base, the first test passed 5/5 and the second 3/3.

## Corrective Action
*(to be done)* Make both tests wait on a state, not a race:
- **Run now conflict:** hold the run in progress until the click lands, with a longer mock delay or by waiting for `routine-last` "Running…" before clicking. Then assert the 409 sentence.
- **Immediately repeating:** poll on a deadline, not a fixed 40 × 500 ms, or wait on the row's last-run text.

Test-only.

## Verification
*(to be done)* Each test passes 10 isolated runs in a row and three `--lane agent-routines` runs.

## Sign-Off
*(written at completion)*

## Disposition
- **Deferred** (2026-10-31, Flight Director, sortie 07 closing gate): out of the sortie's scope, and the failure reproduces on the base. **Revisit trigger:** Mission 34 Flight 1's `browser-lane-budgets-and-flakes` leg, or the next squawk turnaround, whichever comes first. Until then, a failure of one of these two tests alone in `agent-routines` is accepted as this squawk when an isolated re-run passes.
