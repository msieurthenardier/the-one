# Squawk 0183: The client falls back to browser-local time for an unknown zone, and parses a display label as data

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
(c) When `App.time.setZone` gets a key the browser engine's `Intl` rejects (`RangeError`, for example an older WebKitGTK/ICU), it falls back to **browser-local** with only a `console.warn`. That silently breaks "the app and its agents agree". It should retry with the server's fixed offset. (d) `App.time.zoneFromSettings` regex-parses the display label `effective.offset` (`UTC+05:30`) to get a machine key, so any wording change to `offset_label()` breaks the unnamed-system-zone path.

## Evidence
`static/js/time.js` (`setZone`, `zoneFromSettings`); `the_one/time_zones.py::offset_label`; the `api.py` time-settings response. The fix: add an additive `effective.offset_minutes` (or `client_key`) field, use it in `zoneFromSettings`, and make the `RangeError` fallback use it. Cover it in `tests/browser/test_ui_time_contract.py`.

Logged from the Mission 28 mission debrief (mission Architect).

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
