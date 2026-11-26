# Squawk 0435: the unit tier has no per-test timeout

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: —

## Report

The `Makefile` `test-unit` target passes `-n $(UNIT_WORKERS) --dist load -v --tb=short` and no `--timeout`. `pyproject.toml` `addopts` sets none either. A single hung test therefore runs until the whole-tier watchdog (`TEST_TIMEOUT`, 1200 s by default) kills the process group. The run then reports "killed at 98%" instead of a failed test with a stack. This happened twice in Mission 37 Flight 2 (squawk 0434). CLAUDE.md already asks every autonomous pytest run to pass a timeout; the canonical target does not.

## Evidence
- The `Makefile` `test-unit` recipe shows no `--timeout`. `pytest-timeout>=2.4` is already a dev dependency.
- The Flight 2 debrief run hit the 3600 s kill with 0 FAILED lines.

## Corrective Action
*(written at completion)* Add a per-test `--timeout` to `test-unit`, generous enough for the slowest legitimate test under load. Check `--durations` from a loaded run first. Then confirm the expected 15 skips and the counts.

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
