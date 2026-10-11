# Squawk 0180: Widen the static local-time guard's patterns

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
`tests/test_time_getters_static.py` bans `getHours|getMinutes|getDay(|getDate(|getMonth(|getFullYear(|toLocale` outside `js/time.js`. It misses other local-time paths: local-time `new Date(y, m, d…)` construction, `getTimezoneOffset`, the `set*` local mutators and a bare `Intl.DateTimeFormat(`.

## Evidence
`tests/test_time_getters_static.py`. The fix: extend the regex, and confirm the only hits are inside `time.js`.

Logged from the Mission 28 flight debriefs.

## Corrective Action
Widened `BANNED` in tests/test_time_getters_static.py: `getTimezoneOffset`, local `set*` mutators (not `setUTC*`), `new Date(a, b…)` with 2+ args, bare `Intl.DateTimeFormat(`; comments are now stripped before matching. The one outside hit (date-time-page.js browser-zone lookup) moved into `App.time.browserZone()` in time.js; the page's helper delegates. Added a test that the patterns catch each path and spare UTC/one-arg forms.

## Verification
Static guard passes with every hit inside time.js; date-time browser tests pass; ruff clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
