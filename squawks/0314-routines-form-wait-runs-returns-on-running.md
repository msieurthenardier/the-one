# Squawk 0314: the routines form tests' `_wait_runs` returns while a run is still running

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-03

## Report
In `tests/browser/test_flow_agent_routines_form.py`, two "Start immediately" tests failed every time in the 2026-11-02-2 turnaround's `agent-routines` lane, even when run alone: `test_immediately_runs_a_repeating_routine_at_once` and `test_immediately_runs_a_one_off_once_and_it_is_done`. Each failed on `'running' == 'ok'`. The cause is in `_wait_runs`, which returns as soon as every run has a truthy `outcome`. A run row is created with `outcome="running"` (`the_one/routines/models.py:35`), and that value is truthy. So the test read the row mid-run. It passed before only when the run finished before the first poll.

## Evidence
- A worktree of `main` at 76834305 reproduces the same failure, so it predates the turnaround.
- The likely trigger is a timing change: the venv now has playwright 1.64.0 and Chromium 156 (squawk 0138).

## Corrective Action
`_wait_runs` now waits for a terminal outcome: `all(x.get("outcome") and x["outcome"] != "running" for x in runs)`. The change is test-only and no product code changed.

## Verification
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agent-routines`: 86 passed in 229 s, including both tests.
- This is a wait-only fix, so there was no falsification.
- The worktree used for the check was removed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. Logged mid-turnaround. It reproduced on clean `main` in a separate worktree, so the failure predates this batch.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
