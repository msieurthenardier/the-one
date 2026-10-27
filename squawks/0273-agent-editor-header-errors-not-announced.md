# Squawk 0273: Agent editor header errors are not announced to screen readers

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-27
**Completed**: —

## Report
In the agent editor, any save error that lands in the header error slot (a non-name server error, `refuseBlockingOverride_`'s message, a failed PUT after a rename) is shown visually but not announced: the editor shell is built without `errorRole`, so `span.editor-error` has no live role. Only name refusals are announced, because they go to the Name field (`App.ui.field.setError`, `role=alert`). Found by sortie 06's accessibility review; pre-existing. The sortie's load-failure line deliberately has no role (its toast announces it), so a fix must keep that line silent or accept a double announcement.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — the `ui.editorShell(Ellipsis)` call passes no `errorRole`.
- `the_one/interfaces/web/static/js/ui/editor.js` — `errorRole: 'alert'` (the only value) puts `role=alert` on `span.editor-error`.
- `sorties/06-safe-names/flight-debrief.md`, What Could Be Improved › Technical.

## Corrective Action
*(written at completion)*

## Verification
A browser test that a non-name save error in the agent editor is in a `role=alert` region (or is announced through `App.ui.flash(..., {error: true})`), while the load-failure header line stays role-less.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
