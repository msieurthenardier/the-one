# Squawk 0038: Telegram 429 retry_after is slept on with no upper clamp

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-03

## Report

`the_one/connectors/telegram/_api.py`'s one-shot 429 handling reads `retry_after` from
the response and sleeps that long with no upper bound — a misbehaving or malicious
server value would park the poll loop (and, on send, the caller) arbitrarily long.
Clamp to a sane ceiling (mirror Discord's REST discipline if it has one; otherwise
~60s), log when clamped, and add one test with an absurd retry_after asserting the
clamp. Flight 4 flight-end review flagged it "trivial at personal-bot scale."

## Evidence

- `the_one/connectors/telegram/_api.py:88-89` — the unclamped sleep
- Flight 4 flight-end review, non-blocking note (2026-09-02)

## Corrective Action

`the_one/connectors/telegram/_api.py`: added a module constant
`_MAX_RETRY_AFTER_SECONDS = 60.0` (DD-citing comment: Discord's REST
client, `connectors/discord/_rest.py`, DD-3, has no analogous clamp to
mirror -- capped in Telegram's client instead). `send_message`'s one-shot
429 handler now parses `retry_after`, catching non-numeric values, and
clamps to the ceiling whenever the parsed value is negative, out of range,
or unparseable (non-numeric/negative values are treated as the ceiling, not
a small default -- documented in the module comment); a `logger.warning`
fires whenever the value is clamped. Net +14 lines in the subpackage.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_telegram_api.py tests/test_telegram_plugin.py -x --timeout 30`
  -- 56 passed, including two new tests: an absurd `retry_after=99999` and
  a malformed `retry_after="soon"`, both asserting (via a monkeypatched
  `asyncio.sleep` seam) the sleep is clamped to `_MAX_RETRY_AFTER_SECONDS`.
- `.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check the_one/ tests/`
  -- both clean.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet — security tier for 0037), squawk/turnaround-2026-09-03
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03 batch commit (PR follows)
