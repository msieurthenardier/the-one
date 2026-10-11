# Squawk 0180: Widen the static local-time guard's patterns

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
`tests/test_time_getters_static.py` bans `getHours|getMinutes|getDay(|getDate(|getMonth(|getFullYear(|toLocale` outside `js/time.js`. It misses other local-time paths: local-time `new Date(y, m, d…)` construction, `getTimezoneOffset`, the `set*` local mutators and a bare `Intl.DateTimeFormat(`.

## Evidence
`tests/test_time_getters_static.py`. The fix: extend the regex, and confirm the only hits are inside `time.js`.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
