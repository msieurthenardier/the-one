# Squawk 0416: Discord's transport error chains the httpx cause; Telegram's does not

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

`DiscordTransportError` is raised `from exc`, so a logged traceback carries the httpx exception and its request URL. Discord authenticates with a header, so no token is in the URL, and the exposure is at most the endpoint path. Telegram, whose token is in the URL path, raises `from None` deliberately. Making Discord match is cheap hardening and keeps the two connectors consistent. Found by the 2026-11-24 routine maintenance (Security Reviewer).

## Evidence
- `the_one/connectors/discord/_rest.py` (about line 126): `raise DiscordTransportError(f"{method} {path} failed: {type(exc).__name__}") from exc`.
- `the_one/connectors/telegram/_api.py` (about lines 83-86) raises `from None`.

## Corrective Action
In `the_one/connectors/discord/_rest.py` the `DiscordTransportError` raise now uses `from None`, matching Telegram's `_api.py`. Added `test_transport_error_does_not_chain_the_httpx_cause` to `tests/test_discord_visuals.py`.

## Verification
The new test asserts `__cause__ is None` and `__suppress_context__ is True`. Falsified: with `from exc` restored the test failed; with `from None` back it passes. `tests/test_discord_visuals.py` passes, ruff check and format clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; connector token surface), batch review of squawks 0411-0419
**Verdict**: confirmed. Nothing in `the_one/` reads `__cause__` or relies on the chain.
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
