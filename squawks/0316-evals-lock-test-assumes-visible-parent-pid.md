# Squawk 0316: an evals lock test assumes the parent process is visible, so it fails in a CI container

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-14

## Report
`tests/test_evals_env.py::test_refuses_a_run_dir_owned_by_another_live_process` writes `os.getppid()` into `owner.lock` as "a live process that is not us" and expects `startup()` to refuse with "in use by process". In a Concourse task container the test process's parent is outside its PID namespace, so `getppid()` returns 0. `pid_alive(0)` is false, the lock counts as stale, and nothing raises ("DID NOT RAISE"). The test passes on the host (unit tier: 8738 passed). The product's `acquire_lock` (`evals/env.py:278`) behaves correctly: 0 is not a live owner.

## Evidence
- One-off `fly execute -c ci/tasks/test.yml` (build 795949, 2026-11-03, the 2026-11-02-2 turnaround tree): 1 failed, 8727 passed, 25 skipped. This was the only failure.
- The `the-one/ci` pipeline last built on 2026-10-09 (build 73), before Mission 30 added `tests/test_evals_env.py`. This is the test's first Concourse run, not a regression.

## Corrective Action
`tests/test_evals_env.py::test_refuses_a_run_dir_owned_by_another_live_process` now starts its own short-lived child (`subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])`), writes that PID to `owner.lock`, and terminates and waits for the child in a `finally`.

## Verification
The file passed 5 runs in a row on the host (with the two 0358 files, 87 tests each run). Not run in a Concourse container (`fly execute`); not falsified (the failure needs a PID namespace where `getppid()` is 0). Original plan:
- Use a live process the test owns: start a short-lived child (`subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])`), write its PID, assert the refusal, then terminate and wait for the child in a `finally`.
- The test passes on the host and in a one-off `fly execute -c ci/tasks/test.yml`.

Not proven inside a CI container: the failure needs a PID namespace where `getppid()` is 0, and no `fly execute` was run.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
