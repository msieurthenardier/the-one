# Squawk 0057: Encryption-rotation endpoint catches `Exception`; the write-lock guard rolls back on `BaseException`

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-09-15

## Report

`rotate_encryption_key` wraps its `write_transaction` block in `except Exception`, while `write_transaction` itself rolls back on `BaseException`. A `CancelledError`/`KeyboardInterrupt` during the row rewrite is rolled back by the guard but bypasses the endpoint's own failure branch — `except Exception: encryptor.discard_pending_key(); raise` — so the staged pending key is never discarded. Fix: `except BaseException` on that branch (it already re-raises), so the pending key is discarded on every failure the guard rolls back. **Qualification note**: this is a credential surface, so the completion review runs at the Sonnet tier per the crew file; the fix is confined to the one `except` clause and its re-raise — anything wider escalates.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/interfaces/web/api.py:5009` — `async with write_transaction(conn):`; `:5045` — `except Exception:` (the failure branch); `:5053` — `encryptor.install_key(new_key)` after the block.
- `the_one/db/_write_lock.py:73` — `except BaseException:` (rollback path).
- Flight 2 flight log, "flight-end review, cycle 1": squawk candidate.

## Corrective Action

Changed the failure branch around the `write_transaction` block in
`rotate_encryption_key` (`the_one/interfaces/web/api.py:5047`) from
`except Exception:` to `except BaseException:`, matching
`write_transaction`'s own rollback guard (`the_one/db/_write_lock.py:73`).
The clause already re-raised (`raise` with no argument), so no other
behavior changes — a `CancelledError`/`KeyboardInterrupt` mid-transaction
now runs `encryptor.discard_pending_key()` before propagating, same as
any other failure. Added a one-line comment above the clause citing the
guard's `BaseException` catch and this squawk. No other line in the
function was touched; the "NO await between commit and install_key"
invariant (`:5051`-`:5055`) and the DML-only rule above the transaction
block are both outside this branch and unaffected.

## Verification

Added `test_rotate_discards_pending_key_on_cancellation` to
`tests/test_provider_api.py::TestEncryptionRotation` (sibling to the
existing `test_rotate_preserves_key_on_db_failure`, which patches
`aiosqlite.Connection.commit` with `side_effect=RuntimeError(...)`). The
new test patches the same seam with `side_effect=asyncio.CancelledError()`
— a `BaseException`, not an `Exception` subclass — and asserts: the
on-disk key file is unchanged, the staged `.next` sidecar
(`next_key_path`) does not exist, the exception propagates
(`pytest.raises(asyncio.CancelledError)`), and the cached encryptor still
decrypts the untouched provider row. Confirmed the new test fails without
the fix (temporarily reverted the `except` clause to `Exception`, reran
just that test — `AssertionError: assert not True` on the sidecar-exists
check — then restored the fix and reran, green).

Ran `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_api.py tests/test_db_write_lock.py -x --timeout 60 -q`:
184 passed. Ran `ruff check the_one/ tests/` and
`ruff format --check the_one/ tests/` (full repo, both check-only): all
checks passed, 423 files already formatted — no drift introduced anywhere,
including the pre-existing uncommitted squawk 0054–0056 changes.

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet (credential-surface tier), batch review of squawk/turnaround-2026-09-15
**Verdict**: confirmed
**Commit**: ba46d62
