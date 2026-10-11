# Squawk 0183: The client falls back to browser-local time for an unknown zone, and parses a display label as data

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
(c) When `App.time.setZone` gets a key the browser engine's `Intl` rejects (`RangeError`, for example an older WebKitGTK/ICU), it falls back to **browser-local** with only a `console.warn`. That silently breaks "the app and its agents agree". It should retry with the server's fixed offset. (d) `App.time.zoneFromSettings` regex-parses the display label `effective.offset` (`UTC+05:30`) to get a machine key, so any wording change to `offset_label()` breaks the unnamed-system-zone path.

## Evidence
`static/js/time.js` (`setZone`, `zoneFromSettings`); `the_one/time_zones.py::offset_label`; the `api.py` time-settings response. The fix: add an additive `effective.offset_minutes` (or `client_key`) field, use it in `zoneFromSettings`, and make the `RangeError` fallback use it. Cover it in `tests/browser/test_ui_time_contract.py`.

Logged from the Mission 28 mission debrief (mission Architect).

## Corrective Action
Server: additive `effective.offset_minutes` (int) in `/api/time-settings` GET/PUT via new `time_zones.offset_minutes(now, eff)`, from the same `utcnow()` instant. Client `time.js`: `setZone(key, fallbackOffsetMinutes?)` falls back to the fixed-offset key on `RangeError` (browser-local only when no fallback); `zoneFromSettings` builds the offset key from `offset_minutes` (label parse only for an older server); new `App.time.applySettings(s)` = setZone(zoneFromSettings, offset minutes), now used by app.js boot and date-time-page.js. Public API otherwise unchanged. agents.md App.time / Time zones sections updated.

## Verification
tests/test_time_settings_api.py: offset_minutes for -420 (default LA), +330, -360 and an unnamed system zone (static guards run: 358 passed, 1 skipped). test_ui_time_contract: offset_minutes preferred over label; RangeError with fallback follows the offset (parts and zone() = +05:30, one warn); existing no-fallback test still falls to local. Browser run 45 passed. ruff clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
