# Squawk 0136: The KB watcher's sub-second drain test fails under load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-08

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
Test-only change in `tests/test_kb_watcher.py`; no production code touched. The test's fake (`_QueueFactory`) polls every 20 ms and honours the stop sentinel, so the `time.sleep(3.0)` named in the report belongs to a different test (`test_stop_bounded_by_drain_timeout_when_factory_ignores_stop`). The property this test protects is that `drain()` ends each watch through its stop sentinel rather than by running into `drain_timeout` (the cancel fallback).

- Renamed to `test_drain_three_live_entries_stops_via_sentinel_not_timeout`. `drain_timeout` is now 30 s and the elapsed-time bound is half of it (15 s): a drain that waited on a watcher ignoring the sentinel would take the full 30 s, while load cannot plausibly stretch a 20 ms-poll drain to 15 s.
- Found a second, real flake while verifying under load: the assertion that the `the-one-watch-f*` threads are gone sampled `threading.enumerate()` immediately, but the watch task ends when the thread posts its terminal `_Done`, a moment before the thread is reaped (4 of 50 runs failed under load). It now waits per thread with the existing `_wait_thread_gone` helper (10 s deadline) before asserting.

## Verification
- 50 of 50 consecutive runs pass with `nproc` busy-loop processes running (PIDs recorded and killed, none left). Before the thread-reap wait was added, the same loop failed 2 of 50 and 5 of 50 in two attempts, all at the thread-gone assertion.
- Falsified: with the fake watcher replaced by a generator that sleeps 35 s and ignores the stop event, the elapsed-time assertion fails (30.31 s run); reverted.
- `tests/test_kb_watcher.py` whole file: 39 passed.
- `make test-unit` is run once at batch end by the Flight Director.
- `ruff check` and `ruff format --check` are clean.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
