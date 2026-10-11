# Squawk 0172: Lift the `tzdata<2026.5` cap

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
`pyproject.toml` pins `tzdata>=2025.2,<2026.5` because 2026.5 was under 14 days old at lock time (Mission 28 F1 L1 soak rule). Zone data that isn't updated goes stale (DST rule changes), and on Linux the name set comes from tzdata while the rules come from the host.

## Evidence
`pyproject.toml:~30` (the comment says "lift the cap later"); `uv.lock` resolves tzdata 2026.4. The fix: remove the upper bound once 2026.5 is 14 or more days old, re-lock, and confirm `the-one doctor` `time zones: OK`.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
