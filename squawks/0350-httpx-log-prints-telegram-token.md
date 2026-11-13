# Squawk 0350: httpx INFO log prints the Telegram bot token

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: —

## Report
httpx logs each request at INFO with its full URL. The Telegram Bot API puts the bot token in the URL path (`/bot{token}/{method}`), so every Telegram request (`getUpdates` polls, `sendMessage`, and since M35 F3 `sendPhoto`) writes the token into the app log whenever INFO logging is on for `httpx`. It predates Mission 35 Flight 3. It was found in Leg 4, whose token-safety tests deliberately check only `the_one.*` log records.

## Evidence
- `the_one/connectors/telegram/_api.py` `TelegramApiClient._post`: `path = f"/bot{self._token}/{method}"` on an `httpx.AsyncClient`.
- The Leg 4 report in `missions/35-rich-visuals-in-chat/flights/03-visuals-on-chat-platforms/flight-log.md`: "httpx's own INFO request log prints the full URL, token included, on every request".
- `the_one/logging_config.py` sets up the app's logging.

## Corrective Action
*(written at completion)*

## Verification
A `caplog` test at INFO across **all** loggers: a Telegram request through `TelegramApiClient` (mock transport) must leave no record whose message contains the token. Falsify it by restoring httpx's INFO level.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
