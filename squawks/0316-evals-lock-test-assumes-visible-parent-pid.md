# Squawk 0316: an evals lock test assumes the parent process is visible, so it fails in a CI container

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
`tests/test_evals_env.py::test_refuses_a_run_dir_owned_by_another_live_process` writes `os.getppid()` into `owner.lock` as "a live process that is not us" and expects `startup()` to refuse with "in use by process". In a Concourse task container the test process's parent is outside its PID namespace, so `getppid()` returns 0. `pid_alive(0)` is false, the lock counts as stale, and nothing raises ("DID NOT RAISE"). The test passes on the host (unit tier: 8738 passed). The product's `acquire_lock` (`evals/env.py:278`) behaves correctly: 0 is not a live owner.

## Evidence
- One-off `fly execute -c ci/tasks/test.yml` (build 795949, 2026-11-03, the 2026-11-02-2 turnaround tree): 1 failed, 8727 passed, 25 skipped. This was the only failure.
- The `the-one/ci` pipeline last built on 2026-10-09 (build 73), before Mission 30 added `tests/test_evals_env.py`. This is the test's first Concourse run, not a regression.

## Corrective Action
*(written at completion)*

## Verification
- Use a live process the test owns: start a short-lived child (`subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])`), write its PID, assert the refusal, then terminate and wait for the child in a `finally`.
- The test passes on the host and in a one-off `fly execute -c ci/tasks/test.yml`.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
