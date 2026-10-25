# Squawk 0236: Provider editor Save is not busy during its request

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: 2026-10-23

## Report
The provider editor's Save stays enabled while its POST/PUT is in flight, so a double-click on Create can create the provider twice. Found in Mission 31 Flight 3's planning survey beside the same gap in the connector editor (that one is fixed in Flight 3, DD8-2). `App.ui.editorShell` already has `setBusy(bool)`, which disables Save, Cancel and Test until the request settles. No editor calls it yet.

## Evidence
- `the_one/interfaces/web/static/js/ui/editor.js:62-63`: "setBusy(true) disables Save, Cancel and Test and setBusy(false) restores the dirty-derived state."
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`: the Save handler sends the request without calling `setBusy`.

## Corrective Action
Mission 31 Flight 4 leg 04f: `performSave` in `provider-editor.js` calls `shell.setBusy(true)` after validation passes and `setBusy(false)` on an edit success and on failure; a create stays busy until the create-to-edit remount replaces the shell. A local `saving` flag also guards the create-mode plan sign-in button, which shares `performSave` but sits outside the shell. 
## Verification
`tests/browser/test_flow_provider_editor.py`: double-click on Create with the POST held sends exactly one POST (fails on the prior code: Save stayed enabled), a 500 restores Save and Cancel, an edit Save is busy then restored, and the plan sign-in button posts once. Providers lane: see the flight log.

## Sign-Off
