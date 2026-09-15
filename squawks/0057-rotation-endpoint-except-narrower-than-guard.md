# Squawk 0057: Encryption-rotation endpoint catches `Exception`; the write-lock guard rolls back on `BaseException`

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

`rotate_encryption_key` wraps its `write_transaction` block in `except Exception`, while `write_transaction` itself rolls back on `BaseException`. A `CancelledError`/`KeyboardInterrupt` during the row rewrite is rolled back by the guard but bypasses the endpoint's own failure branch — `except Exception: encryptor.discard_pending_key(); raise` — so the staged pending key is never discarded. Fix: `except BaseException` on that branch (it already re-raises), so the pending key is discarded on every failure the guard rolls back. **Qualification note**: this is a credential surface, so the completion review runs at the Sonnet tier per the crew file; the fix is confined to the one `except` clause and its re-raise — anything wider escalates.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/interfaces/web/api.py:5009` — `async with write_transaction(conn):`; `:5045` — `except Exception:` (the failure branch); `:5053` — `encryptor.install_key(new_key)` after the block.
- `the_one/db/_write_lock.py:73` — `except BaseException:` (rollback path).
- Flight 2 flight log, "flight-end review, cycle 1": squawk candidate.

## Corrective Action
*(written at completion)*

## Verification
Existing rotation tests (`tests/test_db_api.py` / the rotation failure test that patches `commit`) still green; a new test that raises `asyncio.CancelledError` from inside the transaction and asserts no sidecar key file remains and the stored key is unchanged; `make test-unit` green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
