# Squawk 0095: A timed-out shutdown flush is not reported as cancelled, so the vector-store hook re-flushes it

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: 2026-10-13

## Report

`IndexingManager.stop()` records the cancel verdict **before** it runs the
shutdown flush. If that flush times out, the kb_id is left out of
`cancelled_kb_ids()`, and `close_vector_store()` then flushes it a second time
while the first `index.save` thread may still be running — the exact torn-index
race DD-3a exists to prevent, reached through the other arm of the same
`if/elif`.

Cancelling an `await asyncio.to_thread(...)` releases the `async with` lock but
does **not** stop the pool thread, so a second flusher can acquire the lock and
call `index.save` concurrently, writing the same fixed temp path
(`_tmp_path_for` → `{kb_id}.usearch.tmp`).

Found during the Mission 24 debrief; no flight caught it.

## Evidence

- `the_one/knowledge/manager.py:259` — `self._cancel_report[kb_id] = cancelled`
  runs before the flush.
- `the_one/knowledge/manager.py:266-271` — `elif entry.awaiting_flush:` →
  `await asyncio.wait_for(self._flush(kb_id, entry), self._shutdown_flush_timeout)`
  wrapped in `except Exception:` which **logs only**. `TimeoutError` is an
  `Exception`, so expiry is swallowed and `cancelled` stays `False`.
- `the_one/knowledge/manager.py:276` — `cancelled_kb_ids()` is what
  `close_vector_store()` reads to decide whom to skip.
- **The instrument gap has the same shape as the hole**: `shutdown_flush_timeout`
  has 7 occurrences across `the_one/` and `tests/`, and the only test one
  (`tests/test_kb_manager.py:787`) sets it to `5.0` and asserts the run finishes
  in under 3 s — i.e. it exercises the **non**-timeout path. No test drives it to
  expiry.

## Corrective Action

In `IndexingManager.stop()` (`the_one/knowledge/manager.py`), the shutdown-flush `except` arm now sets `self._cancel_report[kb_id] = True` when the failure is a `TimeoutError`. Cancelling the awaiting `to_thread` leaves the `index.save` pool thread running, so `close_vector_store()` must skip that kb_id exactly as for the cancel fallback. Non-timeout flush failures are not marked (the thread has finished). `stop()` is not restructured; the `cancelled_kb_ids()` docstring, the comment at the write site and the agents.md DD-3a text now describe the report as "the most recent stop left a possibly-running mutation".

Expected shape, one line: the report should answer "did the most recent stop
leave a possibly-running mutation?", which is true of **both** arms — so set
`_cancel_report[kb_id] = True` on the shutdown-flush timeout as well as on the
cancel fallback. Same mechanism, same rationale, same recovery (the items never
reached `indexed`, so `requeue_stranded()` re-indexes them).

## Verification

Add a test that drives `shutdown_flush_timeout` to expiry and asserts the kb_id
appears in `cancelled_kb_ids()`. Falsify it by removing the new line and
confirming it fails — the discipline Flight 7 Leg 1 used for AC-4c and AC-7a.

### Verification results

- Added `tests/test_kb_manager.py::TestCooperativeStopAndCancelFallback::test_shutdown_flush_timeout_is_reported_as_cancelled` (flush blocks on an Event, `shutdown_flush_timeout=0.1`, Event released in `finally`).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_manager.py -x --timeout 60`: 29 passed.
- Falsified: with `manager.py` stashed (fix removed) the new test fails; restored, passes. `git stash list` empty.
- `ruff check` / `ruff format --check` on `the_one/knowledge` and the test file: clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.
