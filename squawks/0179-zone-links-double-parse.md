# Squawk 0179: `zone_links()` re-parses `tzdata.zi` separately from `_parse_tzdata_zi()`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
Mission 28 F2 leg 1 added `zone_links()` as a second cached parser of the same tzdata file (deliberately, so `_parse_tzdata_zi`'s return arity didn't change). Two parsers of one file can drift.

## Evidence
`the_one/time_zones.py` `_parse_tzdata_zi`, `zone_links`. The fix: one parser returning canonical names, the name set and the links, with `canonical_zones`/`zone_names`/`zone_links` as thin cached views. `tests/test_time_zones.py` covers the behaviour.

Logged from the Mission 28 flight debriefs.

## Corrective Action
`_parse_tzdata_zi()` now returns (canonical tuple, name frozenset, links dict) from one pass over `tzdata.zi`, links resolved transitively as before. `canonical_zones`, `zone_names`, `zone_links` are thin views; the second parser and its cache were removed.

## Verification
Added `TestSingleParse` (cache misses == 1 across the three views). Existing zone-link tests unchanged and passing in the same 219-passed batch; ruff clean; `doctor` `time zones: OK`.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
