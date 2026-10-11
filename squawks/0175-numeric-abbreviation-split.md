# Squawk 0175: Numeric zone abbreviations are dropped in the tool, but returned raw by the time-settings API

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
Mission 28 F1 leg 4 made `tool_lines` omit numeric abbreviations (`+14`, `-03`, `+0545`). `/api/time-settings` `effective.abbreviation` and `/api/time-zones` `abbreviation` still return the raw `tzname()`, and the page drops them again on the client (F2 DD4). The rule lives in two places with no pin.

## Evidence
`the_one/time_zones.py` `_NUMERIC_ABBREVIATION` / `_abbreviation`, `zone_rows`, `api.py` time-settings response. The fix: apply the same rule server-side to both API fields (empty string when numeric), drop the client duplicate, and add a test.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
