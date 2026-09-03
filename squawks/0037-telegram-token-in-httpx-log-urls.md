# Squawk 0037: Telegram bot token appears in httpx INFO log lines

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-03

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

Quieted the `httpx` and `httpcore` loggers to `WARNING` in
`the_one/logging_config.py::configure_logging()` (the app's single
established logging-setup spot, called once from the web app's
`lifespan()`), via a new `_QUIETED_THIRD_PARTY_LOGGERS = ("httpx",
"httpcore")` tuple, unconditionally re-asserted on every call (not
gated behind the existing handler-attachment idempotency check).

Root-caused why the leak reached INFO in the first place despite root
logger's own default level being WARNING: the `anthropic`/`openai`
Python SDKs call `setup_logging()` at import time
(`anthropic/_utils/_logs.py`, `openai/_utils/_logs.py`), which — when
`ANTHROPIC_LOG=info`/`OPENAI_LOG=info` is set in the environment —
explicitly sets the shared `httpx` logger's own level to `INFO` (and
adds a root `StreamHandler` via `logging.basicConfig()`), overriding
the ambient default. Those imports happen at module load (before
`the_one`'s own `configure_logging()` ever runs in `lifespan()`), so
re-asserting `WARNING` there wins and holds for the life of the
process. `httpcore` is quieted alongside `httpx` for the same class of
risk (its `httpcore.http11`/`httpcore.connection` etc. sub-loggers
inherit the parent's WARNING level once set).

Redaction-in-the-client was considered and rejected in favor of the
simpler logger-level fix, per the squawk's own preference — it also
covers any other library that logs a Telegram-token-bearing URL
(anything routed through `httpx`), not just `_api.py`'s own call
sites.

Discord's REST client (`the_one/connectors/discord/_rest.py`) sends
its token in a header, never the URL — httpx's INFO line logs only
method/URL/status, never headers — so it was never exposed by this and
required no change. Verified no regression in
`tests/test_discord_gateway.py`, `tests/test_discord_plugin.py`,
`tests/test_discord_rest.py`, `tests/test_discord_sever_route.py`.

Files changed:
- `the_one/logging_config.py` — added `_QUIETED_THIRD_PARTY_LOGGERS`
  and the quieting loop in `configure_logging()`; updated its
  docstring.
- `tests/test_telegram_logging.py` (new) — regression test.

## Verification

New test `tests/test_telegram_logging.py::
test_telegram_poll_and_send_cycle_logs_no_token_at_info` runs a full
Telegram `connect()` (getMe + getUpdates poll loop, dispatching one
scheduled update) + `send()` cycle against
`tests._telegram_api_fixture.FakeTelegramApi`'s `httpx.MockTransport`
with a distinctive fake token, and asserts (under `caplog.at_level
(logging.DEBUG)`) that the token substring never appears in captured
log output and that zero `httpx`/`httpcore` INFO log records are
emitted at all. The test deliberately sets `httpx`/`httpcore` to
`INFO` (reproducing the hostile precondition an `ANTHROPIC_LOG=info`-
style import-time setter would leave) *before* calling
`configure_logging()`, so it proves the fix wins over that precondition
rather than passing vacuously.

Confirmed the test fails without the fix: temporarily commented out
the quieting loop in `configure_logging()` and reran the new test in
isolation — it failed on the effective-level assertion (`httpx`
logger stayed at `INFO`, 20, not `WARNING`, 30). Restored the fix
before finishing.

Commands run (all green):
```
PYTHON=.venv/bin/python bash scripts/run-tests.sh \
  tests/test_telegram_api.py tests/test_telegram_plugin.py \
  tests/test_telegram_render.py tests/test_logging_config.py \
  tests/test_telegram_logging.py tests/test_discord_gateway.py \
  tests/test_discord_plugin.py tests/test_discord_rest.py \
  tests/test_discord_sever_route.py -x --timeout 30
# 152 passed at verification time (155 after squawks 0038/0040 added tests to the same files later in the batch)

.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check the_one/ tests/
# All checks passed! / 401 files already formatted
```

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet — security tier for 0037), squawk/turnaround-2026-09-03
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03 batch commit (PR follows)
