# Squawk 0177: A stored alias zone shows no check mark in its own search result

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
With `Europe/Oslo` stored, searching "oslo" shows the Oslo alias item with no check, while the "Selected: Oslo" line names it. The Berlin row doesn't match the query, so `syncActive` targets `Europe/Berlin` (not in the results) and the first row becomes active.

## Evidence
`static/js/areas/admin/date-time-page.js` `source()`: alias items always get `checkLead(false)`. The fix: compare the alias name with the stored zone for the check, and make `setActive` target `alias:<stored>` when the stored zone is an alias. Add a case to `tests/browser/test_flow_settings_date_time.py`.

Logged from the Mission 28 flight debriefs.

## Corrective Action
`date-time-page.js` `source()`: an alias item's lead is `checkLead(alias === storedZone())`. `syncActive()` also calls `list.setActive('alias:' + stored)` when the stored zone is an alias (setActive ignores absent ids; an alias item exists only while its canonical row is out of the results, so at most one target is present).

## Verification
New `test_a_stored_alias_item_carries_the_check_and_is_active` (Europe/Oslo stored, search "oslo": item has `aria-selected=true` and a check icon). Browser files test_ui_time_contract, test_flow_settings_date_time, test_flow_chat_time_zone: 45 passed (Chromium+WebKit contracts). ruff clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
