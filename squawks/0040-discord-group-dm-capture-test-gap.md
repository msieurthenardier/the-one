# Squawk 0040: Discord group-DM (type=3) channel-name capture is untested

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

## Report

Flight 4's Discord channel-name directory capture (in `_resolve_channel_type`'s
cache-miss path) has tests for guild channels and threads but none for a group DM
(channel `type=3`), which has no `name` field in the same shape. Add one fixture test
pinning the behavior (whatever it is — capture with a fallback name, or skip) so the
edge is a decision, not an accident.

## Evidence

- `the_one/connectors/discord/plugin.py` — channel capture at the cache-miss site
- Flight 4 flight-end review, non-blocking note (2026-09-02)

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
