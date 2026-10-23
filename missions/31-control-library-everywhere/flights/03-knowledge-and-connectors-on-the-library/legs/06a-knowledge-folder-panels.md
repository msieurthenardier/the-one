# Leg: knowledge-folder-panels

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Move the knowledge-base Folders section onto the library:
- Add folder through `field`/`textInput`/`button`;
- each folder panel and the "Other items" panel as an `App.ui.disclosure` (bordered), with chips as `meta` and the delete as an action;
- file rows keyed by item id and patched in place (fix DD8-4: the poll no longer steals focus or closes a menu);
- the standalone badge as the warning chip;
- the folder delete through `App.ui.confirm` on the summary, with its error in the header.

The 0088 armed-confirm invariant holds throughout. The item menu and the chunks and source panels are leg 06b's: this leg keeps the existing menu builder and only stops closing it on refresh.

## Context
- **Flight DD4** (disclosure, chip warning), **DD6** (the folder panels are `disclosure`; error feedback goes to the header), **DD7** (ledger), **DD8-4**, **DD10**, **DD11.**
- **Leg 03a's disclosure:**
  - `variant: 'bordered'`, `summary` (a string), `summaryTextTestid`, `meta` (named, non-interactive nodes), `actions` (interactive), `onToggle`, `testid`, `dataset`;
  - `summaryText` carries `data-confirm-title`;
  - `setSummary` is a no-op while armed;
  - `App.ui.confirm` is armed on `ctl.summary`.
- **Leg 03b's chip:** `dataset` and `tone: 'warning'` (it mirrors danger; a small visible change, in the ledger).
- **Leg 02** moved this code to `knowledge-folders.js`, and **05a/05b** to the frame and status. Re-read their flight-log entries and cite by function name.
- **Today's code** (from `knowledge-section.js` at `332496d`):
  - **Add folder** (about `:606-640`):
    - the section "Folders";
    - the cascade hint `kb-folders-cascade-hint` (`field-hint`);
    - the input `kb-folder-path-input` (`data-field=path`, label "Folder path", placeholder `/path/to/folder`);
    - the error `kb-folder-add-error` (`field-error`; the refusal for a folder inside the data directory renders here);
    - the button `kb-add-folder-btn` "Add folder";
    - the list `kb-folders-list` with the empty state "No folders registered.".
  - **`buildFolderPanel(f)`** (about `:945-1034`):
    - `details.mcp-tool-item[data-testid=kb-folder-panel][data-folder-id]`;
    - `summary.mcp-tool-summary.kb-folder-summary`;
    - the path span `kb-folder-path` with `data-confirm-title`;
    - the chips `chip kb-folder-status` ("status: X") and `chip kb-folder-watch` ("watch: X");
    - the delete button `kv-remove-row-btn kb-folder-delete-btn` (testid `kb-folder-delete-btn`, aria-label "Delete folder {path} (press twice to confirm)", `title` "Delete folder", a trash icon through `_appendIcon`) calling `App.confirmDelete(summary, …deleteFolder…)`;
    - the chevron "▸";
    - the body `mcp-tool-body` holding `kb-folder-meta` and `kb-folder-files` (empty state "No files indexed from this folder yet.");
    - `toggle` closes any open menu when the panel collapses.
  - **`updateFolderMeta`** (about `:1044-1080`) runs on **every poll tick**:
    - it sets the chip texts;
    - it rebuilds `kb-folder-meta`: `kb-folder-indexed-at`, `kb-folder-skip-counts`, `kb-folder-status-error`, `kb-folder-watch-error`;
    - it never writes the path span, because the 0088 rule says nothing else may write the armed title.
  - **`renderFolders`** (about `:1082-1112`) reconciles panels keyed by folder id (moves, removes stale).
  - **`buildOtherItemsPanel`/`renderOtherItems`** (about `:1117-1165`): `kb-other-items-panel`, summary "Other items ({n})" written through `summaryText.textContent`, and the files rebuilt.
  - **`buildFileItemRow`** (about `:866-918`):
    - `kb-item-row[data-item-id]` holds `kb-item-path` (relative to the folder; `title` is the full path), `kb-item-status`, `kb-item-error` (on failure, `field-error`), `kb-item-indexed-at` "Indexed: {iso}" (`title` is the content hash), the standalone badge `chip kb-item-standalone-badge` "standalone (in {path})" (testid `kb-item-standalone-badge`), and the menu `buildItemMenu(item)`.
  - **`renderAllItems`** (about `:1184-1213`) calls `closeAnyOpenItemMenu()`, then rebuilds every row of every panel (`renderFolderFiles` clears `filesEl.textContent`). This is DD8-4.
  - **`deleteFolder`** (about `:925-943`):
    - it disables the button and sends the DELETE;
    - on OK, `refreshStatusNow()` and `refreshItemsListNow()`;
    - on failure it re-enables, calls `revertFn()` and `App.showFlash(container, 'Error: …', true)`.
- **CSS** (`studio.css`, `@layer areas`):
  - the borrowed `.mcp-tool-*` rules (stay for the MCP editor);
  - `.kb-folder-delete-btn svg` (about `:969`);
  - the armed rules (about `:984-996`, the `confirm-delete: 3` allowance rows);
  - `.kb-item-standalone-badge` (about `:903`);
  - the `.kb-*` layout rules (about `:837-933`), which are area layout and stay.
- **Tests** (`test_flow_studio_knowledge_inventory.py`, `library` lane):
  - `.kb-folder-path` (about `:480`, `:913`, `:985`, `:1335`, `:1355`) and `.kb-folder-summary`;
  - `confirm-delete`/`confirm-lapsed` on the summary (about `:902-903`, `:1272`, `:1334`, `:1354`, `:1387-1397`);
  - summary clicks (about `:350`, `:420`, `:501`, `:780`, `:1105`, `:1176`);
  - `.kb-item-path` (about `:369`, `:526`, `:532`, `:543`) and `.kb-folder-watch` (about `:481`);
  - `el.open` stays False after a delete click (about `:899`, `:912`);
  - `.empty-state` (about `:435`);
  - the armed-across-poll 0088 test;
  - the menu keyboard test (about `:1109-1139`; the menu is unchanged here).

  Also `tests/behavior/kb-studio-round-trip.md` steps 2-8 (`kb-item-indexed-at` scoped to the file's DOM group).

## Inputs
- Legs 02, 03a, 03b, 05a and 05b landed.

## Outputs
- **Add folder:**
  - `section` content: the cascade hint as the section description or a field hint (text unchanged);
  - `App.ui.field({label: 'Folder path', control: App.ui.textInput({testid: 'kb-folder-path-input', dataset: {field: 'path'}, placeholder: '/path/to/folder'})})`;
  - its error through `field.setError` (keeping the testid `kb-folder-add-error` on the error node: confirm `field` supports an error testid, else keep a separate `status` line with that testid, and record which);
  - `App.ui.button` `kb-add-folder-btn`;
  - the empty state as `App.ui.emptyState`.
- **Folder panels:** `App.ui.disclosure({variant: 'bordered', summary: f.path, summaryTextTestid: 'kb-folder-path', testid: 'kb-folder-panel', dataset: {folderId: f.id}, meta: [statusChip, watchChip], actions: [deleteBtn], onToggle})`.
  - **The chips** are `App.ui.chip({label: 'status: …', testid: 'kb-folder-status'})` and `App.ui.chip({label: 'watch: …', testid: 'kb-folder-watch'})`. Both testids are new and registered.
  - **The delete button** is `App.ui.button({variant: 'ghost', iconOnly: true, icon: 'trash', ariaLabel: 'Delete folder {path} (press twice to confirm)', testid: 'kb-folder-delete-btn'})`. Its click calls `App.ui.confirm(ctl.summary, …)`.
  - **The body** holds the meta and files containers (area layout classes kept).
  - `updateFolderMeta` patches the chip texts (`textContent` on the chip nodes) and each meta line **only when its text changes**, and never calls `setSummary` (0088). It does not rebuild the meta container on every tick.
- **Other items:** a bordered disclosure (`testid: 'kb-other-items-panel'`) whose "Other items ({n})" text goes through `setSummary`. It is never armed, so the armed no-op does not apply.
- **File rows are keyed:**
  - each panel keeps a map from item id to `{row, pathEl, statusEl, …}`;
  - `renderAllItems(nextItems)` adds rows for new ids, removes rows for gone ids, moves kept rows into order, and patches each kept row's status, error, indexed-at and badge, only on change;
  - **the `closeAnyOpenItemMenu()` call on refresh is removed.** A menu closes only when its own row is removed (the removal path calls the row's menu close before detaching);
  - the empty state shows only when a panel has no rows.
- **The standalone badge** is `App.ui.chip({tone: 'warning', label: …, testid: 'kb-item-standalone-badge'})`, and the `.kb-item-standalone-badge` rule goes.
- **The folder delete:**
  - on failure: `revert()`, the button re-enabled, and `shell.setError('Couldn’t remove the folder: …')` through the detail's shell (passed through ctx) instead of `App.showFlash` (DD6);
  - on success, as today;
  - one DELETE per confirm;
  - writes after `destroy` are gated.
- **Remove the studio.css rules that are now dead:** `.kb-folder-delete-btn svg` (the disclosure owns the svg rule), the three armed rules (the disclosure owns the armed look) and their `confirm-delete` allowance rows, and `.kb-item-standalone-badge`. Run `scripts/unused_selectors.py css/studio.css` and act on the `kb-*` entries.
- **Aliases:** no `App.confirmDelete`, `App.showFlash` or `App.icon(` remains in `knowledge-folders.js`. If `_appendIcon` has no user left, it goes from `knowledge-shared.js`.
- **The module's `destroy`** releases the panel controls (`disclosure.destroy`) and the row menus.
- **Tests:**
  - the class locators move to testids (`kb-folder-path`, `kb-folder-status`, `kb-folder-watch`) or roles; `.kb-item-path` stays (an area class on caller-built row nodes);
  - `confirm-delete`/`confirm-lapsed` checks keep reading the summary (`App.ui.confirm` arms the summary, as today);
  - **new:**
    - (a) **DD8-4, test-first:** focus the menu trigger of a file row, let the items signature change (stub `/status` so the chunk count moves, then wait for the items refetch), and focus is still on that trigger and an open menu is still open;
    - (b) a row's DOM node identity survives a poll refresh where only its status changes;
    - (c) a removed item's row disappears, and its open menu closes;
    - (d) the summary's accessible name is the path plus the two chip texts, with no "Delete folder";
    - (e) a failed folder DELETE shows the header error and the summary reverts;
    - (f) the armed-across-poll 0088 test passes unchanged.

## Design review amendments (binding; they supersede earlier text where they differ)
Design review cycle 1 (Sonnet Developer): approve with changes. **The citations after the split** (all in `knowledge-folders.js`):
- Add folder `create()` `:82-112`, with its click handler `:588-624`;
- `buildFileItemRow` `:240-291`;
- `deleteFolder` `:299-317`;
- `buildFolderPanel` `:319-407`;
- `updateFolderMeta` `:418-450`;
- `renderFolders` `:456-483`;
- `buildOtherItemsPanel`/`renderOtherItems` `:491-535`;
- `renderFolderFiles` `:541-556`;
- `renderAllItems` `:558-586` (the menu close is at `:562`);
- `buildItemMenu` `:144-227`.

The menu keyboard test starts at `:1075`.

1. **Never re-append an attached node (a high finding).** `appendChild` of an already-attached node blurs a focused descendant (verified in Chromium). Today `renderFolders` (`:471`) re-appends every panel on **every** 5 s status tick, and `renderOtherItems` (`:529`) on every items refresh, so a focused summary, delete button or menu trigger already loses focus every tick.
   - Reconcile by reference: walk the target order and call `insertBefore` only when `list.children[i] !== node`, keeping the empty-state node separate.
   - Apply this to the folder panels, the Other items panel and the rows.
   - Rewrite the L6-D3 header comment: 0088 means "never recreate"; moving is the focus hazard.
   - **Tests:**
     - (a1) the trigger stays focused across an items refresh;
     - (a2) an open menu stays open;
     - (a3) a focused folder summary or delete button keeps focus across a status tick.

     All are recorded failing first. To make the items signature change, keep a `page.route` on `/status` that bumps `chunks` for the whole test.
2. **Library options from 03b** (amended into 03b): `field` gains `errorTestid` (symmetric with `hintTestid`), and `section` gains `descriptionTestid`.
   - `kb-folder-add-error` uses `field.setError` with `errorTestid: 'kb-folder-add-error'`. That keeps `aria-invalid` and `aria-describedby`; the test reads it only while an error shows.
   - The cascade hint is the Folders `section`'s description with `descriptionTestid: 'kb-folders-cascade-hint'`, text unchanged (pinned at `test_flow_studio_knowledge_inventory.py` about `:864-869`).
3. **Every remaining element is assigned:**
   - `kb-folder-status-error`, `kb-folder-watch-error` and `kb-item-error` become `App.ui.status({state: 'danger', led: false, live: 'off', textTone: true, testid})`;
   - the two "No files indexed from this folder yet." empty states and "No folders registered." are `App.ui.emptyState`;
   - the meta lines are keyed nodes, each patched only on a text change.

   After 06a the folders module's expected residual rows are only those of the old item menu (`kb-item-menu*`, if counted), which 06b removes. State the actual residual in the flight log.
4. **Summary locators:** `summaryTestid: 'kb-folder-summary'` (a new registry row) replaces `.kb-folder-summary` at about `:902`, `:1272` and `:1387`. `.kb-folder-path` at about `:480`, `:913`, `:985`, `:1335`, `:1355`, `:1399` and `:1408` moves to the `kb-folder-path` testid, and `.kb-folder-watch` (about `:481`) to `kb-folder-watch`.
5. **Path styling.** The disclosure text has no medium weight (`.kb-folder-path` had `font-weight: medium` and `word-break`, `studio.css:863-866`), and it ellipsises. **No consumer CSS on library internals**, so record both, and the new summary `:focus-visible` ring, as ledger rows for the HAT.
6. **The folders ctx gains `setError(text)` and `isCurrent()`** from the detail (05a). The header error is cleared at the start of the next folder action (add or delete). Add folder's `.then`/`.catch` and the delete are gated by `isCurrent`.
7. **Teardown:**
   - a stale panel removed in `renderFolders` calls `disclosure.destroy()` and its rows' menu close;
   - the Other items panel, when it empties, clears its row map and closes its menus;
   - a removed armed summary's pending confirm timer is harmless, because confirm reverts a detached node with no announcement. Verify this and record it.
8. **After a successful folder delete,** focus goes to the Add-folder input (a ledger row).
9. **The interim menu interface:** `buildItemMenu` returns `{el, close}`, and each row-map entry keeps it. Leg 06b replaces only that interface.
10. **Poll-driven tests** drive the 5 s interval with `page.clock.install()` and `run_for(5000)`, rather than real waits, to protect the `library` lane budget (301 of 300 s at leg 02).
11. **Test (b)** stubs `/items` (and `/status`) with `page.route`. **Test (c)** may use the real `DELETE …/items/{id}`. The behavior spec names no `.kb-*` classes, so amending it is expected to be a no-op; say so.

## Acceptance Criteria
- [ ] Every Output is in place. `knowledge-folders.js` builds no `<details>`, `<summary>`, chip, button or field markup by hand.
- [ ] Tests (a)-(f) pass. (a) is recorded as failing before the fix. The existing knowledge tests pass, with any change a locator move listed in the flight log.
- [ ] **The 0088 invariant:** no code path writes the summary text while armed (a grep of `setSummary`/`textContent` on the summary in the folders module shows only the Other-items `setSummary`). Test (f) passes.
- [ ] The `studio.css` `confirm-delete` allowance rows are gone, the ownership allowance shrinks with no row added, and the dead CSS listed above is removed.
- [ ] `tests/behavior/kb-studio-round-trip.md` still matches the UI; amend any step that names a changed class.
- [ ] The `library`, `mcp`, `routing` and `shared` lanes pass under `THE_ONE_TEST_NETNS=1`, and so do `make test-unit` and the static guards (`test_ui_guards.py` including the registry).
- [ ] **Ledger rows:**
  - the folder delete as a library ghost icon button (any computed difference);
  - the standalone badge in the warning chip look (DD4/03b);
  - the folder-delete failure in the header instead of a flash (DD6);
  - the panels via the disclosure (no change expected; record the parity).
- [ ] The `library` lane's time is reported against its budget.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_studio_knowledge_inventory.py -x --timeout 90`; the four lanes; `make test-unit`; the 0088 grep.

## Implementation Guidance
1. **Log a start line.** Write test (a) and see it fail.
2. **Add folder,** then the folder panel on `disclosure`, then `updateFolderMeta` patching, then Other items.
3. **Keyed rows in `renderAllItems`;** remove the menu close on refresh.
4. **The folder delete** on `App.ui.confirm` with the header error.
5. **CSS removal, tests, registry, allowances, ledger, flight log.**

## Edge Cases
- **A folder renamed on disk** (a path change for the same id) never happens; the id is the key. If the path differed, the summary would be stale, which is acceptable and recorded.
- **An item moving between folders** (a `parent_id` change): remove it from the old panel's map and add it to the new one (a new row; any open menu closes).
- **An Other-items panel that empties:** it is removed from the DOM but kept for reuse, as today.
- **The meta lines' order** stays: indexed-at, skip counts, status error, watch error.

## Files Affected
- `js/areas/studio/knowledge-folders.js`, `knowledge-shared.js` (if `_appendIcon` goes), `knowledge-detail.js` (ctx: the shell's `setError`)
- `css/studio.css`
- `tests/browser/test_flow_studio_knowledge_inventory.py`, `tests/_ui_ownership_allowance.py`, `docs/ui-testid-registry.md`, `tests/behavior/kb-studio-round-trip.md` (if needed)
- The flight log

## Citation Audit
Drafted at `332496d` from `knowledge-section.js:606-660,866-1240` (FD read). **Re-cited by module and function after leg 02 lands,** before this leg goes `ready`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
