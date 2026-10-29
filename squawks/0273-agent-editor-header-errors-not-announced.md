# Squawk 0273: Agent editor header errors are not announced to screen readers

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-27
**Completed**: 2026-10-29

## Report
In the agent editor, any save error that lands in the header error slot (a non-name server error, `refuseBlockingOverride_`'s message, a failed PUT after a rename) is shown visually but not announced: the editor shell is built without `errorRole`, so `span.editor-error` has no live role. Only name refusals are announced, because they go to the Name field (`App.ui.field.setError`, `role=alert`). Found by sortie 06's accessibility review; pre-existing. The sortie's load-failure line deliberately has no role (its toast announces it), so a fix must keep that line silent or accept a double announcement.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — the `ui.editorShell(Ellipsis)` call passes no `errorRole`.
- `the_one/interfaces/web/static/js/ui/editor.js` — `errorRole: 'alert'` (the only value) puts `role=alert` on `span.editor-error`.
- `sorties/06-safe-names/flight-debrief.md`, What Could Be Improved › Technical.

## Corrective Action
`agent-editor.js` builds the editor shell with `errorRole: 'alert'`, so header save errors are announced. `setLoadError` removes the role while the load-failure line (`agent-load-error`) shows and puts it back when the line clears. Test: `test_header_save_error_is_announced_and_load_line_is_silent` in `tests/browser/test_flow_agent_editor_frame.py`.

## Verification
The new browser test checks a 500 on Save puts the message in a `role=alert` header slot and that `agent-load-error` has no role; it fails with the `errorRole` line removed by editing and passes with it back.

## Sign-Off
**Reviewer**: Flight 3 Batch A Reviewer (Sonnet), independent of the implementing Developer; Accessibility Reviewer (Sonnet) for 0273
**Verdict**: confirmed (the batch's only blocking item, a lint failure in another file, was fixed in the review-fix pass)
**Commit**: the Mission 33 Flight 3 Batch A commit, `flight/3: Batch A - routes moved, caps and retention, recurrence core, date and time controls`
