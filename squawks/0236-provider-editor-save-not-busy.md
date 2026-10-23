# Squawk 0236: Provider editor Save is not busy during its request

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: —

## Report
The provider editor's Save stays enabled while its POST/PUT is in flight, so a double-click on Create can create the provider twice. Found in Mission 31 Flight 3's planning survey beside the same gap in the connector editor (that one is fixed in Flight 3, DD8-2). `App.ui.editorShell` already has `setBusy(bool)`, which disables Save, Cancel and Test until the request settles. No editor calls it yet.

## Evidence
- `the_one/interfaces/web/static/js/ui/editor.js:62-63`: "setBusy(true) disables Save, Cancel and Test and setBusy(false) restores the dirty-derived state."
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`: the Save handler sends the request without calling `setBusy`.

## Corrective Action

## Verification

## Sign-Off
