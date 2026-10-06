# Squawk 0124: Pin the Windows test-copy helper's CI-closure commands by test

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: —

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

*(written at completion)*

Add a unit test that parses the `uv export` argument list (and the two `--no-deps`
installs) from `ci/tasks/windows-installer-build.yml` and asserts the helper builds the
same lists, sourced from a module constant rather than inline literals.

## Verification

The new test passes. Changing either side alone makes it fail.

## Sign-Off

*(written at completion)*
