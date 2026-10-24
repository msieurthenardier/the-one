# Squawk 0246: Docs and comments left stale by the Mission 31 Flight 3 HAT

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: 2026-10-23

## Report
The M31 F3 HAT changed the knowledge folders and connector code, but several docs and comments still describe the earlier state. Bring them in line with the code; no code change. Found in the M31 F3 debrief.

## Evidence
- **`the_one/agents.md`:**
  - ~:2157 still calls `buildItemMenu(getItem)` "an interim interface; leg 06b replaces it"; 06b did replace it with `App.ui.menu`.
  - ~:2153 lists `openItemMenu` as per-mount state; it is gone.
  - The connector frame paragraph omits the post-Save `runHeaderProbe` and `resetDoctorResult`.
- **`docs/ui-control-inventory.md`** ~:46 (copy) and ~:98 (editorShell) still list `connector-editor.js` and `knowledge-shared.js` `_breadcrumb()` as hand-built sites.
- **`knowledge-folders.js`** ~:62 says "The two never call each other", and ~:783 says "Never called from `renderFolders`". Since the HAT, `renderFolders` calls `renderAllItems` when a panel is added or removed (described at ~:64-67).
- **`the_one/interfaces/web/static/css/studio.css`:**
  - ~:143 names `buildOtherItemsPanel`;
  - `.connector-setup-steps-doc-ref` is declared twice (~:799 and ~:810).

## Corrective Action
Comments and docs only: `the_one/agents.md` (the item menu is `App.ui.menu`, `openItemMenu` removed from the per-mount state, the connector frame paragraph names `resetDoctorResult()` and `runHeaderProbe()` after a Save); `docs/ui-control-inventory.md` (copy row: only `markdown.js` is hand-built; editorShell row: only `mcp-server-editor.js` and `tools-editor.js`); `knowledge-folders.js` header and `renderAllItems` comments say `renderFolders` does call it on a panel add/remove; `studio.css` names `buildIndividualFilesPanel` and the duplicate `.connector-setup-steps-doc-ref` rule is merged into one.

## Verification
No code change: `git diff` shows comments, docs and the one CSS merge (identical computed declarations). Static guards pass.

## Sign-Off
