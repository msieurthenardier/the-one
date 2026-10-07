# Squawk 0124: Pin the Windows test-copy helper's CI-closure commands by test

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: 2026-10-06

## Report

`scripts/windows_test_copy.py` `setup` installs the same dependency closure as the CI
Windows build:
- `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format
  requirements-txt`;
- then `pip install -r … --no-deps`;
- then `pip install -e . --no-deps`.

The helper copies these commands from `ci/tasks/windows-installer-build.yml`, but no test
ties the two together. If the CI task's closure changes, the test copy silently drifts
from what ships. The `NEEDLES` list already has such a pin
(`tests/test_windows_test_copy.py::test_needles_match_ci_foreach_list`). The closure
should have one too.

Source: the Mission 25 Flight 5 debrief, recommendation 1.

## Evidence

- `scripts/windows_test_copy.py`: the `uv export` arguments (around line 2238).
- `ci/tasks/windows-installer-build.yml`: the closure steps (around lines 65–90).

## Corrective Action

`scripts/windows_test_copy.py` gains three module constants beside `NEEDLES`:
`CLOSURE_UV_EXPORT_ARGS`, `CLOSURE_PIP_REQUIREMENTS_ARGS` (with a `{requirements}`
placeholder for the exported file) and `CLOSURE_PIP_EDITABLE_ARGS`; `setup`'s `uv export` and
the two `--no-deps` installs now build their command lists from them. The new
`tests/test_windows_test_copy.py::test_closure_commands_match_ci_task` parses the three
commands from `ci/tasks/windows-installer-build.yml` and asserts each equals its constant.

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_windows_test_copy.py -x
  --timeout 60`: 157 passed.
- Changing one side alone fails it: a temporary edit of `all-llms` to `all-llmz` in the
  helper's constant failed the new test, and reverting it passed.

## Sign-Off

**Reviewer**: Developer agent, Mission 25 Flight 6 leg 3 (the flight-end review confirms)
**Verdict**: confirmed
**Commit**: pending the Flight 6 legs 1-3 commit
