# Squawk 0135: Move the project's Python target from 3.11 to 3.12

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-11-03

## Report

Local development runs on Python 3.12, but CI, the Windows installer and the project metadata all target 3.11. That split has bitten twice:
- **Sortie 01's design** found that a `typing.TypedDict` route annotation would pass on the 3.12 dev venv and crash `api.py` at import everywhere else.
- **Sortie 01 leg 1:** a 3.11 import check rebuilt the repo `.venv` as 3.11.

The operator decided on 2026-10-07 to move the project to 3.12 permanently, so dev, CI and the shipped Windows build run one interpreter line. Pin the **minor** version (`3.12`), not a patch release. The local venv is CPython 3.12.3, the system Python on the dev host.

Raised mid-flight during sortie 01 and deferred until that sortie lands (out of its scope).

## Evidence

- **Project metadata:** `pyproject.toml:5` `requires-python = ">=3.11"`, `pyproject.toml:183` `target-version = "py311"` (ruff), and `uv.lock` header `requires-python = ">=3.11"`.
- **Concourse:** `ci/tasks/test.yml:17`, `bwrap.yml:38` and `lint.yml:13` have `tag: "3.11"`, and `browser.yml:21` has `tag: "3.11-bookworm"`.
- **Windows:** `ci/tasks/windows-tests.yml`, `windows-installer-build.yml` and `windows-vector-bench.yml` install choco Python 3.11. `packaging/windows/README.md:33` says "Python 3.11".
- **GitHub Actions** (break-glass and release): `.github/workflows/test.yml` (lines 26, 66, 92), `pr-lint.yml` (34, 48), `lint.yml` (20) and `windows-installer.yml` (38) set `python-version: "3.11"`.

## Corrective Action
Moved every target pin to 3.12 (2026-11-02, Developer crew):
- `pyproject.toml`: `requires-python = ">=3.12"`, ruff `target-version = "py312"`. `uv lock` re-resolved (`uv lock --check` clean).
- Concourse: `ci/tasks/{test,bwrap,lint,browser}.yml` image tag `0.9.30-python3.12-bookworm` (tag verified with `docker manifest inspect`). Windows tasks `windows-tests.yml`, `windows-installer-build.yml`, `windows-vector-bench.yml` now `choco install python312` and `C:\Python312\python.exe` (the tasks install Python themselves; no worker-host change needed). `ci/the-one.pipeline.yml` had no pin.
- `packaging/windows/build.ps1` requires `Python 3.12.`; Linux `build.Dockerfile` uses CPython 3.12.12; macOS and all `.github/workflows/*.yml` `python-version: "3.12"`.
- Docs/comments: `README.md`, `CLAUDE.md`, `Makefile`, `ci/README.md`, `packaging/*/README.md`, `packaging/render.py`, `the-one.spec`, `build.sh`. `tests/test_windows_build_recipe.py` pin updated to `python312`.
- Left alone on purpose: `scripts/windows_test_copy.py` and its test (`C:\Python311` is the operator's own Windows desktop install), `the_one/platform/interpreter.py` message (about the agent's external runtime), historical prose.
- After review: fixed `build.Dockerfile` line 53 (`uv venv --python 3.12.12 /opt/venv`, a space had been lost); re-read the packaging/CI/.github diff, no other mangling; added `test_linux_build_dockerfile_pins_python_312_with_separated_args` in `tests/test_packaging_metadata.py` (falsified: space removed by editing, failed; restored, passed). `the_one/db/schema.py` comment now says "Python ≥3.12 floor".

## Verification
- `ruff check` / `ruff format --check` on the_one tests scripts evals: clean.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 8729 passed, 15 skipped.
- **Concourse one-off builds NOT run:** `fly -t the-one` reports "not authorized" (token expired). Needs the operator to run `! fly -t the-one login`; then `fly -t the-one execute` of `ci/tasks/lint.yml`, `test.yml`, `windows-tests.yml` (and the installer build) with `-i repo=.`.
- `grep -rn '3\.11\|py311' pyproject.toml uv.lock ci/ .github/workflows/ packaging/windows/` shows no remaining target pins. Historical prose in mission or flight artifacts is left alone.
- `make test-unit` is green on 3.12, and `ruff check` and `ruff format --check` are clean under `target-version = "py312"`, including any new ruff findings.
- The Concourse test, lint, bwrap and browser lanes are green on the 3.12 images.
- A Windows installer build on 3.12 succeeds, and `the-one doctor` passes in the packaged smoke run. PyInstaller and the `pywinpty` wheel are the likely snags.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. Concourse one-off `fly execute` builds on the batch tree, uploaded without `env.sh`: lint build 795944 passed; unit build 795949 had 8727 passed, 25 skipped and 1 failed (`tests/test_evals_env.py::test_refuses_a_run_dir_owned_by_another_live_process`, which is environment-only: `getppid()` is 0 in a CI container, and that test had never run on Concourse; new squawk 0316); `windows-tests` build 795947 passed on CPython 3.12.10 from `C:\Python312` (576 passed, 21 skipped); `windows-installer-build` build 795963 passed (`BUILD OK: the-one-setup-0.13.0.exe`). The Dockerfile's missing space was fixed after review, and a test now pins it.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** burn-down in the next turnaround. The operator confirmed that local Concourse is up with a Windows worker, so the CI lanes and a Windows installer build can verify it. Sequence it after 0138 and 0241 (all touch `pyproject.toml`/`uv.lock`), in one dependency commit sequence.
