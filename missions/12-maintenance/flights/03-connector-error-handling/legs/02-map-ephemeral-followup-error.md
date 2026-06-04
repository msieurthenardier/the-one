# Leg: map-ephemeral-followup-error

**Status**: ready
**Flight**: [Connector Error-Handling Correctness](../flight.md)

## Objective
Map the ephemeral-followup non-401 failure path in `_discord.py` to a typed `ConnectorConnectionError` instead of bare-raising the raw `discord.errors.HTTPException`, so every Discord send path honors the "all connector send errors are typed `ConnectorClientError`s" contract (resolves finding T1).

## Context
- Maintenance report 2026-06-04, finding **T1**: the ephemeral-followup non-401 branch (`_discord.py:~547`) does a bare `raise` of the SDK `HTTPException`, unlike every other send path which maps to a typed error (Forbidden→ConfigError `:571`, NotFound→ConnectionError `:584`, 429→RateLimitError `:610`, generic HTTPException→ConnectionError `:622`).
- The F4 send tool (`tools/connector_send.py:199`) catches only `ConnectorClientError`, which `discord.errors.HTTPException` is NOT. Currently latent — the only callers (`_inbound.py:789,834`) sit inside broad `except Exception` that swallow it — but it violates the contract and relies on the caller's safety net.

## Inputs
- `the_one/connectors/_discord.py` around line 547 (the ephemeral-followup non-401 branch) and the existing mapping ladder at ~571–622.
- `the_one/connectors/errors.py` (`ConnectorConnectionError`).

## Outputs
- The non-401 path raises `ConnectorConnectionError(...) from exc`.

## Acceptance Criteria
- [ ] The ephemeral-followup non-401 branch raises a `ConnectorClientError` subtype (`ConnectorConnectionError`), chained `from exc`, matching the channel-ladder mapping
- [ ] No Discord send path bare-raises a raw SDK `HTTPException` anymore
- [ ] A regression test asserts the ephemeral-followup non-401 path yields a typed connector error, not `discord.errors.HTTPException`

## Verification Steps
- Read the diff: the bare `raise` is replaced with the typed mapping
- `grep -n "raise$" the_one/connectors/_discord.py` near the ephemeral path → no bare raise of the SDK exception remains
- New test: simulate a non-401 `HTTPException` on the ephemeral followup and assert a `ConnectorConnectionError` (or `ConnectorClientError`) is raised — `docker exec the-one pytest tests/test_connectors_discord.py -q -k ephemeral` green

## Implementation Guidance

1. **Locate the branch** at `_discord.py:~547` — the non-401 case of the ephemeral-followup error handling.
2. **Apply the same mapping the channel ladder uses** — `raise ConnectorConnectionError(<message including status code / exception type, no token>) from exc`. Reuse the message style of the generic-HTTPException mapping at ~622.
3. **Add the regression test** — drive the ephemeral followup to a non-401 HTTPException (via the test double / FakeLLM-style Discord stub) and assert the typed error.

## Edge Cases
- **Do not interpolate the token** into the error message (the path has a `del token` discipline elsewhere) — keep to status code + exception type.
- **401 still has its own branch** — only the non-401 case changes; don't disturb the 401 handling.

## Files Affected
- `the_one/connectors/_discord.py` - typed mapping at the ephemeral-followup non-401 branch (~547)
- `tests/test_connectors_discord.py` - regression test

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
