# Squawk 0238: A key-value table cell error is not announced

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
`App.ui.keyValueTable`'s `setError` shows a `div.ui-kv-error` linked to the cell through `aria-describedby` and `aria-invalid`. The element has no role and no live attribute, so a screen-reader user hears the error only by focusing the invalid input (WCAG 2.1 SC 4.1.3). No consumer calls `setError` today: the connector channel map does not. Fix before a consumer uses it. Either focus the invalid cell, or give the error element `role="alert"`. Found in the Mission 31 Flight 3 accessibility review.

## Evidence
- `the_one/interfaces/web/static/js/ui/key-value-table.js`: `setError` (about line 270).
- Flight 3 flight log, the flight review entry.

## Corrective Action

## Verification

## Sign-Off
