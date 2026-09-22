# Squawk 0095: A timed-out shutdown flush is not reported as cancelled, so the vector-store hook re-flushes it

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: —

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

*(written at completion)*

Expected shape, one line: the report should answer "did the most recent stop
leave a possibly-running mutation?", which is true of **both** arms — so set
`_cancel_report[kb_id] = True` on the shutdown-flush timeout as well as on the
cancel fallback. Same mechanism, same rationale, same recovery (the items never
reached `indexed`, so `requeue_stranded()` re-indexes them).

## Verification

Add a test that drives `shutdown_flush_timeout` to expiry and asserts the kb_id
appears in `cancelled_kb_ids()`. Falsify it by removing the new line and
confirming it fails — the discipline Flight 7 Leg 1 used for AC-4c and AC-7a.

## Sign-Off

*(written at completion)*
