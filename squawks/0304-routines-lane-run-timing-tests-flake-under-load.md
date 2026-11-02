# Squawk 0304: two Routines browser tests fail intermittently inside the lane

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-31
**Completed**: 2026-11-02

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
Both tests now wait on a state, not a race. Test-only; no product change.
- **Run now conflict** (`test_flow_agent_routines.py`): after the API start returns 202, the test polls `GET .../runs` (100 ms steps, 10 s monotonic deadline) until a run row has `outcome == "running"`, and only then clicks Run now and asserts the 409 sentence. The 4 s mock delay is unchanged.
- **Immediately repeating** (`test_flow_agent_routines_form.py`): `_wait_runs` loops to a 20 s monotonic deadline instead of a fixed 40 × 500 ms; callers' assertions are unchanged.

## Verification
Each test passed 10 of 10 isolated runs, and `--lane agent-routines` passed three times (83 passed in each: the `--parallel 3` run's lane, then two solo runs). Not falsified (race fixes).

## Sign-Off
**Reviewer**: Mission 34 Flight 1 flight review (Reviewer agent, Sonnet)
**Verdict**: confirmed
**Commit**: the Mission 34 Flight 1 commit on branch flight/01-test-suite-runtime-ii (see the flight PR)

## Disposition
- **Deferred** (2026-10-31, Flight Director, sortie 07 closing gate): out of the sortie's scope, and the failure reproduces on the base. **Revisit trigger:** Mission 34 Flight 1's `browser-lane-budgets-and-flakes` leg, or the next squawk turnaround, whichever comes first. Until then, a failure of one of these two tests alone in `agent-routines` is accepted as this squawk when an isolated re-run passes.
