# Squawk 0037: Telegram bot token appears in httpx INFO log lines

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

## Report

The Telegram Bot API places the token in the URL path (`/bot<token>/method`), and
httpx's INFO-level "HTTP Request:" lines — active in the current logging setup —
print the full request URL, so the token lands in the host log on every poll
cycle. Observed live during Flight 4's HAT (dev-instance log). Discord is
unaffected (token in a header). Log files are local and gitignored, so exposure
is bounded, but a token should never be logged. Fix shape (Flight 4 flight-end
review's own suggestion): quiet the httpx logger
(`logging.getLogger("httpx").setLevel(logging.WARNING)`) at app logging setup,
or redact the token from the client's own logging; one new test pinning that a
poll cycle logs no token substring.

## Evidence

- `.the-one.8485.log` (local): `HTTP Request: GET https://api.telegram.org/bot887...` lines during HAT step 1
- Flight 4 flight-end review, non-blocking note 2
- `the_one/connectors/telegram/_api.py` — token-in-path construction

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
