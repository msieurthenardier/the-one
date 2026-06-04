# Leg: narrow-broad-except

**Status**: completed
**Flight**: [Connector Error-Handling Correctness](../flight.md)

## Objective
Narrow the collapsed `except (ConnectorClientError, Exception)` in the `_save_warm_background` task (`api.py:2455`, post-Flight-02 reformat) so it catches only connector errors and lets programming errors surface loudly via a separate log-and-reraise path rather than being recorded as connection failures (resolves finding T2).

## Context
- Maintenance report 2026-06-04, finding **T2**: `ConnectorClientError` is a subclass of `Exception`, so `except (ConnectorClientError, Exception)` collapses to a bare `except Exception`. The save-warm background path records the caught error into `_connect_error_store`, so an `AttributeError` or other programming bug surfaces to the operator as a connection "error" with a misleading message instead of failing loudly.
- **The `# noqa: BLE001` was already removed by Flight 02 Leg 1** — only the bare `except (ConnectorClientError, Exception)` remains. This leg is the narrowing, not the noqa removal.
- **Design-review findings (applied):** the broad-except is now at `api.py:2455` inside `_save_warm_background` (lines ~2429–2462). The connect path (`_evict_all_for_account` + `account_acquire`) can legitimately raise the `ConnectorClientError` subtypes (`ConnectorConnectionError`, `ConnectorConfigError`, `ConnectorRateLimitError`, `ConnectorRegistrationError`); catching the base `ConnectorClientError` covers them all. Unexpected types it must NOT record: `KeyError` (DB miss in `_load_account`), `AttributeError`/`TypeError` (programming bugs), `asyncio.TimeoutError` (eviction stall). The task is launched via `asyncio.create_task` with no exception-retrieving callback and no global asyncio exception handler — so a propagating programming error would only surface as a GC-time "Task exception was never retrieved" warning with no `account_id` context. Therefore a **dedicated log-and-reraise path is required**, not optional.

## Inputs
- `the_one/interfaces/web/api.py` — `_save_warm_background` (~2429–2462), the `except (ConnectorClientError, Exception)` at 2455, and the `_connect_error_store[account_id] = mapped` write at ~2457.
- The connector error hierarchy in `the_one/connectors/errors.py`.

## Outputs
- Narrowed `except ConnectorClientError` records connection errors; a separate `except Exception` logs (with `account_id`) and re-raises without recording.

## Acceptance Criteria
- [x] The connection-error recording path catches only `ConnectorClientError` (its subtypes), not bare `Exception`
- [x] A separate `except Exception:` clause logs the unexpected error **with `account_id` context** (`logger.exception(...)`) and `raise`s it — it does NOT write to `_connect_error_store`
- [x] A regression test calls `_save_warm_background` directly with `account_acquire` patched to raise `AttributeError`, asserts BOTH `pytest.raises(AttributeError)` AND `_connect_error_store` has no entry (`test_save_warm_background_unexpected_error_not_recorded`)
- [x] Full suite green (2935 passed)

## Verification Steps
- Read the diff: the except is split into `except ConnectorClientError` (records) and `except Exception` (logs + re-raises, no record)
- New test green: `docker exec the-one pytest tests/test_connector_status_endpoint.py -q -k save_warm` (or the chosen test file/name)
- `docker exec the-one ruff check the_one/ tests/` → 0

## Implementation Guidance

1. **Split the except into two clauses** (replace the single `except (ConnectorClientError, Exception)`):
   ```python
   except ConnectorClientError as exc:
       mapped = _map_connect_error(exc)
       _connect_error_store[account_id] = mapped
       logger.warning(
           "save-warm background reconnect failed for account=%r: %s",
           account_id, mapped["message"],
       )
   except Exception:
       logger.exception(
           "save-warm background: unexpected error for account=%r; not recorded as connection error",
           account_id,
       )
       raise
   ```
   `asyncio.CancelledError` (a `BaseException`) correctly bypasses both. `asyncio.TimeoutError` is an `Exception` → logged, not recorded (correct).
2. **Add the regression test** (model on the monkeypatch pattern in `test_lifespan.py`): patch `the_one.connectors._pool.account_acquire` to raise `AttributeError` (the function-local import rebinds at call time), `await _save_warm_background("acct")` inside `pytest.raises(AttributeError)`, assert `"acct" not in _connect_error_store`. Test file: `tests/test_connector_status_endpoint.py` (where the save-warm path is exercised).

## Edge Cases
- **The background task must not crash the event loop** — the `except Exception` re-raise still ends the *coroutine* loudly (now with an `account_id` log line) rather than silently; it does not take down the loop. That's the intended louder failure.

## Files Affected
- `the_one/interfaces/web/api.py` - split except at ~2455 (`_save_warm_background`); no noqa to remove (already gone)
- `tests/test_connector_status_endpoint.py` - regression test

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight: (not final)
- [x] Commit all changes together (code + artifacts)
