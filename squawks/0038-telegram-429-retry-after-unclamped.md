# Squawk 0038: Telegram 429 retry_after is slept on with no upper clamp

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
