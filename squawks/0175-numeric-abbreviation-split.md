# Squawk 0175: Numeric zone abbreviations are dropped in the tool, but returned raw by the time-settings API

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
Mission 28 F1 leg 4 made `tool_lines` omit numeric abbreviations (`+14`, `-03`, `+0545`). `/api/time-settings` `effective.abbreviation` and `/api/time-zones` `abbreviation` still return the raw `tzname()`, and the page drops them again on the client (F2 DD4). The rule lives in two places with no pin.

## Evidence
`the_one/time_zones.py` `_NUMERIC_ABBREVIATION` / `_abbreviation`, `zone_rows`, `api.py` time-settings response. The fix: apply the same rule server-side to both API fields (empty string when numeric), drop the client duplicate, and add a test.

Logged from the Mission 28 flight debriefs.

## Corrective Action
`time_zones._abbreviation` became public `abbreviation()` and is now the single rule: `tool_lines`, `zone_rows` (`/api/time-zones`) and `_time_settings_response` (`effective.abbreviation`) all use it, returning "" for numeric (`+14`, `-03`, `+0545`) or `UTC±…` names. The client duplicate in `date-time-page.js` `metaFor` was removed; it shows `{offset}` alone when the abbreviation is empty, else `{offset} · {abbr}`.

## Verification
Added tests: Kiritimati/Kathmandu rows "" and Kolkata "IST" (test_time_zones.py), the same rows plus `effective.abbreviation == ""` for Kiritimati (test_time_settings_api.py). Unit batch 219 passed/1 skipped; browser test_flow_settings_date_time.py 17 passed; ruff check/format clean; `doctor` shows `time zones: OK`.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
