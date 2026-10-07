# Squawk 0126: The connector editor's title keeps the old name after a rename

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: 2026-10-06

## Report

When a connector is renamed and saved in the Library connector editor (edit mode), the
save succeeds, the Library list shows the new name, and the form reads clean. The
editor's `h1` (`.editor-title`), however, still shows the old name until the editor is
re-opened.

The leg 1b Developer found it while pinning focus after Save (Mission 25 Flight 6). The
defect predates that leg.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js`:
  - `renderConnectorEditor` builds `connTitle` once (about line 250: `text: isCreate ?
    'New Connector' : (cfg.name || '')`);
  - the Save handler's edit branch (about line 704: `if (!isCreate) { unsavedEl.textContent
    = ''; …}`) never updates `connTitle` from the saved row (`updated`).
- An edit Save keeps the same editor DOM (the comment at about line 701), so nothing else
  repaints the title.

## Corrective Action

`connector-editor.js`: the edit-save branch now sets `connTitle.textContent` from the saved row
(`updated.name`) beside clearing the unsaved caption, so the `h1` follows a rename at once.
The other editors were checked for the same gap:
- agent editor: no gap (a save re-renders the editor from the saved row, `renderEditor`);
- knowledge-base detail: no gap (`onSaveSuccess` re-mounts the detail from the saved object);
- MCP server editor: **the same gap** (edit save keeps the DOM). Fixed with the same one-line
  change in `mcp-server-editor.js` (the title is set from `updated.name` in the edit branch).

## Verification

`tests/browser/test_studio_connector_editor.py::test_connector_rename_updates_the_editor_title`
(library lane) renames a seeded connector, saves, and asserts the `h1` reads the new name
without re-opening. The library lane and the unit suite pass (see the Flight 6 flight log, leg 4c).

## Sign-Off
**Reviewer**: Flight 6 leg 4c developer (agent)
**Verdict**: confirmed
**Commit**: pending the Flight 6 legs commit
