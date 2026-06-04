# Leg: narrow-broad-except

**Status**: ready
**Flight**: [Connector Error-Handling Correctness](../flight.md)

## Objective
Narrow the collapsed `except (ConnectorClientError, Exception)` at `api.py:2463` so it catches only the expected connector error types and lets programming errors propagate, and remove the dead `# noqa: BLE001` (resolves finding T2).

## Context
- Maintenance report 2026-06-04, finding **T2**: `ConnectorClientError` is a subclass of `Exception`, so `except (ConnectorClientError, Exception)` collapses to a bare `except Exception`. The save-warm background path records the caught error into `_connect_error_store`, so an `AttributeError` or other programming bug surfaces to the operator as a connection "error" with a misleading message instead of failing loudly.
- The line carries `# noqa: BLE001`, which is a no-op (BLE is not in the selected ruleset) — a crutch implying typed handling that isn't happening.

## Inputs
- `the_one/interfaces/web/api.py` around line 2463 (the save-warm background task's except block) and line 2465 (write to `_connect_error_store`).
- The connector error hierarchy in `the_one/connectors/errors.py`.

## Outputs
- Narrowed except catching specific connector error types; programming errors propagate.
- `# noqa: BLE001` removed.

## Acceptance Criteria
- [ ] The except catches only the connector error types the save-warm path can legitimately produce (e.g. `ConnectorClientError` and/or its specific subclasses), not bare `Exception`
- [ ] An unexpected exception (e.g. `AttributeError`) raised inside the warmed path is NOT recorded as a connection error — it propagates (and is logged by the task's outer handler if one exists)
- [ ] `# noqa: BLE001` is removed from this site
- [ ] A regression test asserts a non-connector exception is not swallowed into `_connect_error_store`

## Verification Steps
- Read the diff: the except tuple no longer includes bare `Exception`
- `grep -n "noqa: BLE001" the_one/interfaces/web/api.py` → this site gone
- New test: inject a path that raises a non-connector error and assert `_connect_error_store` is not populated with it / the error surfaces — `docker exec the-one pytest tests/ -q -k connect_error` green

## Implementation Guidance

1. **Identify what the warmed path actually raises** — trace the `save_warm` / connect path for the connector error types it can throw (`ConnectorConnectionError`, `ConnectorConfigError`, `ConnectorRateLimitError`, etc.). Catch the common base `ConnectorClientError` or the specific subset.
2. **Let everything else propagate** — remove `Exception` from the tuple; if the surrounding task needs to not crash silently, keep a separate outer log-and-reraise rather than recording into the error store.
3. **Remove the dead noqa.**
4. **Add the regression test** — assert that a deliberately-injected `AttributeError` (or similar) in the warmed path does not end up in `_connect_error_store` as a connection error.

## Edge Cases
- **The background task must still not crash the event loop** on an unexpected error — ensure there's a log path; just don't classify it as a connection error.

## Files Affected
- `the_one/interfaces/web/api.py` - narrowed except at ~2463, noqa removed
- `tests/test_connectors_*.py` (or the relevant API test file) - regression test

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: (not final)
- [ ] Commit all changes together (code + artifacts)
