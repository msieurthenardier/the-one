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

## Disposition
**Deferred**: the cap exists because tzdata 2026.5 (uploaded 2026-10-03) was
under the 14-day soak window. It is still under it on 2026-10-11. Revisit
**on or after 2026-10-17**: remove the `<2026.5` bound, re-lock, check that
`the-one doctor` reports `time zones: OK`, and complete this squawk.
**Trigger fired** (2026-10-30): the revisit date has passed and tzdata 2026.6 is on PyPI; the cap is still `<2026.5` (`pyproject.toml:31`). Waiting on the operator's approval to lift ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** **operator approved lifting the cap.** Next turnaround: remove `<2026.5`, re-lock, check that `the-one doctor` reports `time zones: OK`, and batch it with 0226/0227 (same `pyproject.toml`).
