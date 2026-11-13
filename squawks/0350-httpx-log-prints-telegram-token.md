# Squawk 0350: httpx INFO log prints the Telegram bot token

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: 2026-11-13

## Report
httpx logs each request at INFO with its full URL. The Telegram Bot API puts the bot token in the URL path (`/bot{token}/{method}`), so every Telegram request (`getUpdates` polls, `sendMessage`, and since M35 F3 `sendPhoto`) writes the token into the app log whenever INFO logging is on for `httpx`. It predates Mission 35 Flight 3. It was found in Leg 4, whose token-safety tests deliberately check only `the_one.*` log records.

## Evidence
- `the_one/connectors/telegram/_api.py` `TelegramApiClient._post`: `path = f"/bot{self._token}/{method}"` on an `httpx.AsyncClient`.
- The Leg 4 report in `missions/35-rich-visuals-in-chat/flights/03-visuals-on-chat-platforms/flight-log.md`: "httpx's own INFO request log prints the full URL, token included, on every request".
- `the_one/logging_config.py` sets up the app's logging.

## Corrective Action
No code change. The defect was already fixed by squawk 0037: `the_one/logging_config.py::configure_logging` (called from the web app's `lifespan`, `interfaces/web/app.py`) pins `httpx`, `httpcore`, `httpx2`, `httpcore2` and `mcp` to WARNING on every call, with a comment naming the Telegram token leak. The Leg 4 observation came from a test process that never runs the lifespan, so httpx was at its default INFO there; a running app (`the-one serve` / `app`) does not emit the line. No project path relies on httpx INFO logs (grep found none).

## Verification
`tests/test_telegram_logging.py` already does the planned check: it sets httpx/httpcore to INFO, calls `configure_logging()`, asserts both are effectively WARNING, runs a full Telegram connect/poll/send cycle through `TelegramApiClient` on a mock transport at root DEBUG capture, and asserts the token is in no record and no httpx/httpcore INFO record exists. Run: `tests/test_telegram_logging.py tests/test_logging_config.py` 7 passed. Falsified by removing `"httpx"` and `"httpcore"` from `_QUIETED_THIRD_PARTY_LOGGERS` (test failed at the WARNING assertion), then restored (7 passed).

## Sign-Off
**Reviewer**: batch Reviewer (Haiku), independent of the implementers. It confirmed the defect was already fixed (squawk 0037):
- `configure_logging()` pins `httpx`, `httpcore`, `httpx2`, `httpcore2` and `mcp` to WARNING;
- the web lifespan calls it (`interfaces/web/app.py:318`);
- `tests/test_telegram_logging.py` covers it and passed in the unit run.

No code change.
**Verdict**: confirmed (resolved as already fixed)
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13` (artifact only)
