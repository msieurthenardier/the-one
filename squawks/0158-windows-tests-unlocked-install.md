# Squawk 0158: windows-tests CI task still installs unlocked with pip

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: 2026-10-09

## Report
Mission 26 F01 moved every Linux CI task to `uv sync --locked` from `uv.lock`. `windows-tests` was left on `pip install -e ".[all-llms,dev]"` because a uv install could not be validated on `windows-worker` within the flight. So the Windows lane can still test a different dependency set than the lockfile.

## Evidence
- `ci/tasks/windows-tests.yml:53`: `& $py -m pip install -e ".[all-llms,dev]" --quiet`.
- Flight log Deviations (leg 5): `windows-tests` reverted to pip. A pinned `uv==0.9.30` via the choco Python was drafted but never run.
- Verify with one `fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=<clean export>` on `windows-worker`, run when no local test run is going.

## Corrective Action
`ci/tasks/windows-tests.yml` now installs from `uv.lock`: `pip install uv==0.9.30` (the Linux image's uv version) into the choco Python 3.11, then `uv sync --locked --extra all-llms --extra dev` with `UV_PYTHON` set to that interpreter, `UV_PYTHON_DOWNLOADS=never`, `UV_LINK_MODE=copy` and `UV_CACHE_DIR` on a new `uv-cache` task cache. Pytest runs from `.venv\Scripts\python.exe`; the curated test list and flags are unchanged. `tests/test_run_tests_lanes.py::test_ci_tasks_install_from_the_lockfile` now covers `windows-tests` (it allows only the `pip install uv==0.9.30` line). `ci/README.md` install section updated.

## Verification
One `fly execute` of `windows-tests.yml` on `windows-worker` (build 692683, clean export, cold cache): `uv sync --locked` resolved 137 packages, installed 119, 36s for the step; total wall 177s; result 1 failed, 549 passed, 21 skipped, 1 deselected, 2 xfailed. The single failure, `tests/test_api_credential.py::TestFileCreation::test_malformed_credential_file_raises_named_error` ("bad escape \T": `match=str(path)` is an unescaped Windows path used as a regex), is pre-existing: pipeline build ci/72 (pip install) shows the identical failure and identical counts (549 passed, 21 skipped). Not caused by the install change; out of scope here. `tests/test_run_tests_lanes.py`: 14 passed; ruff check and format clean on tests/.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the self-configuration credential-isolation tests and a CI install script). Confirmed `$LASTEXITCODE` is checked after each native command, the curated test list and flags are unchanged against `main`, and the pin test allows only `pip install uv==0.9.30`. Windows build 692683: `uv sync --locked` took 36 s. The 1 failure there is pre-existing squawk 0092.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-09` on branch `squawk/turnaround-2026-10-09`
