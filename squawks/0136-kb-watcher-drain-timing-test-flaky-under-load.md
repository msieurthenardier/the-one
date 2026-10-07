# Squawk 0136: The KB watcher's sub-second drain test fails under load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

`tests/test_kb_watcher.py::TestStopAndDrain::test_drain_three_live_entries_under_a_second` failed once in a full `make test-unit` run on 2026-10-07 (sortie 01 branch, freshly synced 3.12 venv). That run had 1 failed, 5580 passed and 10 skipped. The class then passed 5 times in a row in isolation, and sortie 01 touches no knowledge code.

The test asserts a wall-clock bound, `time.monotonic() - start < 1.0`, around draining three live watcher entries. On a loaded host the drain can overrun the bound even when it is correct.

Like squawk 0134, a gate that goes red for no reason trains people to wave off a real failure. Find what the bound is actually protecting: that the drain does not wait on the 3 s blocking watcher (`time.sleep(3.0)` in the test's fake). Assert that directly, for example by confirming the drain did not wait for the sleeper, or with a bound clearly below 3 s that load cannot reach. Do not add retries, `xfail` or skips.

Distinct from squawk 0134 (the self-configuration surface tests) and squawk 0132 (the watcher's self-probe *skips*).

## Evidence

- **The timing assertion:** `tests/test_kb_watcher.py:986-988`, `start = time.monotonic()` … `assert time.monotonic() - start < 1.0`.
- **The fake watcher** blocks with `time.sleep(3.0)` (`tests/test_kb_watcher.py:1000`).
- **Rate:** 1 failure in one full run on 2026-10-07; 5 of 5 passes in isolation.
- **Possibly the same failure** as the unidentified "12th failure" in sortie 01 leg 1's first full run (the flight log).

## Corrective Action
*(written at completion)*

## Verification
- The test passes 50 repeats in a row under forced CPU load (squawk 0132's busy-loop approach).
- The assertion still fails if the drain is made to wait on the blocking watcher (falsify, then revert).
- `make test-unit` is green.
- `ruff check` and `ruff format --check` are clean.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
