# Squawk 0416: Discord's transport error chains the httpx cause; Telegram's does not

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

`DiscordTransportError` is raised `from exc`, so a logged traceback carries the httpx exception and its request URL. Discord authenticates with a header, so no token is in the URL, and the exposure is at most the endpoint path. Telegram, whose token is in the URL path, raises `from None` deliberately. Making Discord match is cheap hardening and keeps the two connectors consistent. Found by the 2026-11-24 routine maintenance (Security Reviewer).

## Evidence
- `the_one/connectors/discord/_rest.py` (about line 126): `raise DiscordTransportError(f"{method} {path} failed: {type(exc).__name__}") from exc`.
- `the_one/connectors/telegram/_api.py` (about lines 83-86) raises `from None`.

## Corrective Action
*(written at completion)*

## Verification
The Discord raise uses `from None`. A unit test asserts that `__cause__` is None and `__suppress_context__` is set on a transport error, as Telegram's test does if one exists.
