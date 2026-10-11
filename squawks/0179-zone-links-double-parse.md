# Squawk 0179: `zone_links()` re-parses `tzdata.zi` separately from `_parse_tzdata_zi()`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
Mission 28 F2 leg 1 added `zone_links()` as a second cached parser of the same tzdata file (deliberately, so `_parse_tzdata_zi`'s return arity didn't change). Two parsers of one file can drift.

## Evidence
`the_one/time_zones.py` `_parse_tzdata_zi`, `zone_links`. The fix: one parser returning canonical names, the name set and the links, with `canonical_zones`/`zone_names`/`zone_links` as thin cached views. `tests/test_time_zones.py` covers the behaviour.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
