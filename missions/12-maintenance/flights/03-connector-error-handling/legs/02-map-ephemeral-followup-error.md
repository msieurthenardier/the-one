# Leg: map-ephemeral-followup-error

**Status**: completed
**Flight**: [Connector Error-Handling Correctness](../flight.md)

## Objective
Map the ephemeral-followup non-401 failure path in `_discord.py` to a typed `ConnectorConnectionError` instead of bare-raising the raw `discord.errors.HTTPException`, so every Discord send path honors the "all connector send errors are typed `ConnectorClientError`s" contract (resolves finding T1).

## Context
- Maintenance report 2026-06-04, finding **T1**: the ephemeral-followup non-401 branch does a bare `raise` of the SDK `HTTPException`, unlike every other send path which maps to a typed error.
- **Post-Flight-02 line numbers (design-review confirmed):** the bare `raise` is at **`_discord.py:551`** (the `else` of the 401/NotFound check in the ephemeral followup's `except (NotFound, HTTPException)` block, ~517–551). The channel-ladder mappings to reuse: Forbidden→`ConnectorConfigError` `:568`, NotFound→`ConnectorConnectionError` `:581`, 429→`ConnectorRateLimitError` `:607`, generic HTTPException→`ConnectorConnectionError(f"Discord send failed: {exc}") from exc` `:619`. There is also an aspirational comment at ~539–541 ("surface it via the channel ladder's mapping") that currently lies — update it when fixing.
- The F4 send tool (`tools/connector_send.py:190`) catches only `ConnectorClientError`, which `discord.errors.HTTPException` is NOT. Latent — the `_inbound.py` callers (~791, 834) sit inside broad `except Exception` that swallow it — but it violates the contract and relies on the caller's safety net.

## Inputs
- `the_one/connectors/_discord.py` — bare `raise` at line 551; mapping ladder at ~568–619; `ConnectorConnectionError` imported at line 80.
- `the_one/connectors/errors.py` (`ConnectorConnectionError`).

## Outputs
- The non-401 path raises `ConnectorConnectionError(...) from exc`.

## Acceptance Criteria
- [x] The ephemeral-followup non-401 branch raises `ConnectorConnectionError(...) from exc`, matching the channel-ladder mapping
- [x] No Discord send path bare-raises a raw SDK `HTTPException` anymore (only remaining bare `raise` is the unrelated reconnect-cleanup path)
- [x] A regression test asserts the ephemeral-followup non-401 path yields a typed connector error (`test_send_ephemeral_followup_non_401_http_error_raises_connection_error`)

## Verification Steps
- Read the diff: the bare `raise` at line 551 is replaced with `raise ConnectorConnectionError(...) from exc`; the ~539–541 comment is updated to match
- `grep -n "raise$" the_one/connectors/_discord.py` near the ephemeral path → no bare raise of the SDK exception remains
- New test green: `docker exec the-one pytest tests/test_connectors_discord.py -q -k ephemeral`

## Implementation Guidance

1. **Locate the branch** at `_discord.py:551` — the `else` (non-401, non-NotFound) case of the ephemeral-followup `except (NotFound, HTTPException)` block.
2. **Apply the channel-ladder mapping** — replace the bare `raise` with `raise ConnectorConnectionError(f"Discord send failed: {exc}") from exc` (reuse the generic-HTTPException style at line 619; status/exc only, **no token**). Update the aspirational comment at ~539–541 to describe the new typed-raise behavior.
3. **Add the regression test** — model on `test_send_ephemeral_token_expired_falls_back_to_channel` (which drives the 401/NotFound fallback). Build the exception with `_make_http_exception(discord.errors.HTTPException, status=500)` (non-401, non-404 → takes the `else` branch), attach via `webhook.send = AsyncMock(side_effect=...)` + `monkeypatch.setattr(discord.Webhook, "from_state", ...)`. **Do NOT use `_StubErrors.HTTPException`** — it has no `status` attribute and can't drive the `getattr(exc, "status", None) == 401` check. Assert `pytest.raises(ConnectorConnectionError)` and that the channel-send fallback was NOT invoked. Suggested name: `test_send_ephemeral_followup_non_401_http_error_raises_connection_error`.

## Edge Cases
- **Do not interpolate the token** into the error message (the path has a `del token` discipline elsewhere) — keep to status code + exception type.
- **401 still has its own branch** — only the non-401/non-NotFound `else` changes; don't disturb the 401 fallback handling.
- **Out of scope (note only):** the `401-as-HTTPException` fallback sub-case has no dedicated test (only the `NotFound` fallback does) — a follow-up, not this leg.

## Files Affected
- `the_one/connectors/_discord.py` - typed mapping replacing the bare raise at line 551 (+ comment at ~539–541)
- `tests/test_connectors_discord.py` - regression test

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
