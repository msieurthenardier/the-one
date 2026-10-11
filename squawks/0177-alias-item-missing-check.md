# Squawk 0177: A stored alias zone shows no check mark in its own search result

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
With `Europe/Oslo` stored, searching "oslo" shows the Oslo alias item with no check, while the "Selected: Oslo" line names it. The Berlin row doesn't match the query, so `syncActive` targets `Europe/Berlin` (not in the results) and the first row becomes active.

## Evidence
`static/js/areas/admin/date-time-page.js` `source()`: alias items always get `checkLead(false)`. The fix: compare the alias name with the stored zone for the check, and make `setActive` target `alias:<stored>` when the stored zone is an alias. Add a case to `tests/browser/test_flow_settings_date_time.py`.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
