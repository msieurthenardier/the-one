# Leg: knowledge-frame

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Move the knowledge-base create form and the detail editor's frame onto the library, mounted once through `mountSlot`:
- the header through `editorShell`;
- the Name and Description fields through `field`;
- dirty state from a value model;
- Save patches in place with no remount;
- Cancel patches in place;
- the handle gains `destroy`.

This leg owns `knowledge-glue.js`'s mount path: the host clear, the remount on Save, the handle teardown, the focus restore, and the loading and failure sinks. Status, Search and the Danger zone are leg 05b's. Folders are 06a and 06b's.

## Context
- **Flight DD5** (mount once; identity is the knowledge-base id, or create; Save patches in place so expanded folders, open panels, search results and scroll survive; the value model, not DOM queries; `setBusy`; the glue's mount path; host clears become `replaceChildren()` on an identity change after `destroy`; both handles gain `destroy`). **DD6** (the canonical knowledge-base forms; create keeps `kb-create-error` as its one error surface; detail errors go to the header). **DD7.** **DD10** (lanes `library`, `mcp`, `routing`, `shared`). **DD11.**
- **Leg 02 split the file.** The create form is in `knowledge-create.js` (`App.studio.renderKnowledgeCreate(container, callbacks)`). The detail frame is in `knowledge-detail.js` (`App.studio.renderKnowledgeDetail(container, kb, {status, items}, callbacks)`, returning `{updateStatus, updateItems}`), with the folders, inspect, status and search modules created through ctx. **Re-read leg 02's flight-log entry for the landed names and boundaries before starting**, and re-cite by function name.
- **The precedents:**
  - `provider-editor.js` (Flight 1): `editorShell` through `mountSlot`, `field`, `focusAfter`, `fetchJson`;
  - `connector-editor.js` after leg 07a, if it has landed first: the same patterns for a Library editor and its glue's identity key. Legs 05a and 07a are independent; use whichever has landed as a reference, else the provider editor.
- **Today's create form** (in `knowledge-create.js`, formerly `knowledge-section.js:335-447`):
  - **header:** the hand-built breadcrumb `_breadcrumb()` ("Library / Knowledge bases", link `editor-breadcrumb-link`); `h1.editor-title` "New knowledge base" (`tabindex -1`); the caption `editor-unsaved`; Cancel `kb-create-cancel-btn`; Create `kb-create-submit-btn`, enabled from the first render;
  - **fields:** Name (`data-field=name`, testid `kb-create-name-input`, with the 43-code-point hint `kb-create-name-hint`, hidden until needed); Description (textarea, `kb-create-description-input`); the body error `kb-create-error` (`field-error`, `role=alert`);
  - **dirty:** non-empty fields;
  - **Create:** an empty name gives "Name is required." with no request; else Create is disabled, a POST is sent, `invalidate('knowledge-bases')`, the caption cleared, then `onCreateSuccess(kb)`; on failure Create is re-enabled and the error goes in `kb-create-error`.
- **Today's detail frame** (in `knowledge-detail.js`, formerly `:449-604`):
  - **header:** breadcrumb, `h1.editor-title` (`kb.name`), `p.editor-subtitle` (the description), the caption, Cancel `cancel-knowledge-btn`, Save `save-knowledge-btn` (both disabled), and `span.editor-error`;
  - **fields:** Name (`kb-name-input`, hint `kb-name-hint`) and Description (`kb-description-input`) in an `editor-section`;
  - **dirty:** a JSON snapshot of the two values (`fieldsSnapshot`/`checkDirty`/`recapture`);
  - **Cancel:** restores from `kb` and recaptures, with focus to the title;
  - **Save:** an empty name gives the header error "Name is required."; else a PUT, then `invalidate('knowledge-bases')` and `invalidate('agents')`, then `App.focusAfter.defer(saveTok, liveTitleEl)`, then `onSaveSuccess(updated)`. The glue **remounts** the detail (`mountKnowledgeDetail(updatedKb)`), which re-fetches status and items and flushes the focus.
- **Today's glue** (`knowledge-glue.js`):
  - `renderKnowledgeSection` (about `:71`) clears `sectionContentEl.innerHTML = ''` (`:72`) on every render;
  - the create and detail views set `state.knowledgeDetailHandle = null` without destroying;
  - `mountKnowledgeDetail` (about `:188`) writes `'<div class="admin-loading">Loading knowledge base…</div>'` (`:189`) and the failure markup (`:263`);
  - it mounts on `Promise.all([status, items])` with stale-then guards (`_activeSection`/`_selectedKbId`, `kbGen`), sets `state.dirty = false`, then the handle, then `startKnowledgePoll`, then `kbFocusFolderFor` focus, then `App.focusAfter.flush()`;
  - `onSaveSuccess` calls `reloadLibrary` and `mountKnowledgeDetail(updatedKb)` (`:233-237`);
  - the poll (`startKnowledgePoll`, about `:280-336`) calls `handle.updateStatus`/`updateItems`;
  - `reset()` (about `:340`) clears the poll and nulls the handle.
- **Pins:**
  - `tests/test_store_static.py`: the create row and the rename row (in `knowledge-create.js`/`knowledge-detail.js` after leg 02). Retarget them if this leg's `fetchJson` changes the anchored literals; keep the order PUT → `invalidate('knowledge-bases')`/`invalidate('agents')` → `onSaveSuccess`;
  - `test_flow_studio_library_list.py` about `:481` and `test_flow_studio_knowledge_inventory.py` about `:192` (an empty Create shows "Name is required." in `kb-create-error`);
  - the router and guard tests in `routing`/`shared` (KB open, dirty leave, no list refetch on open: `test_router_items.py` about `:579`);
  - `test_agents_library_isolation.py` about `:273` (the poll stops).

## Inputs
- Legs 01, 02, 03b (`editorShell` `save.enabledWhenClean`, `errorRole`) and 04 landed.

## Outputs
- **The create form:**
  - `App.ui.editorShell` with breadcrumb "Library / Knowledge bases" (link testid kept), the title "New knowledge base", `cancel` (`kb-create-cancel-btn`, `enabledWhenClean: true`) and `save` (`kb-create-submit-btn`, label "Create", `enabledWhenClean: true`);
  - fields through `App.ui.field` with `textInput`/`textarea`. The hint is the field's hint (`hintTestid: 'kb-create-name-hint'`), hidden until the name passes 43 code points. Keep `data-field`, the testids and the label text;
  - `kb-create-error` stays the body error, as its one surface (DD6);
  - Create calls `shell.setBusy(true)` during the request and keeps it busy on success (the create remount replaces the form); on failure `setBusy(false)`;
  - dirty means either field is non-empty, through `shell.setDirty` and `onDirtyChange`.
- **The detail frame:**
  - `editorShell` with the breadcrumb, the title `kb.name`, the subtitle `kb.description`, `cancel` (`cancel-knowledge-btn`), `save` (`save-knowledge-btn`) and `errorRole: 'alert'`;
  - Name and Description through `field` (hint `kb-name-hint`);
  - the sections composed after the shell in today's order: fields, Folders, Status, Search, Danger zone.
- **The value model:** `readValues()` gives `{name, description}` from the controls. `snapshot` is taken at mount and after Save; dirty is a comparison; Cancel restores from `stored` (the last saved record). No `querySelector` reads of values.
- **Save patches in place:**
  - `shell.setBusy(true)`, then the PUT through `App.api.fetchJson`;
  - on OK: `stored = updated`, then `shell.setTitle(updated.name)` and `setSubtitle(updated.description || '')`, then the snapshot reset and `setDirty(false)`, then `invalidate('knowledge-bases')` and `invalidate('agents')`, then `onSaveSuccess(updated)`, then `focusAfter.restore` to the title (no defer);
  - on failure: `setBusy(false)`, `shell.setError(text)`, focus back to Save.
- **The glue** (`knowledge-glue.js`):
  - it keeps `handleKey` (`'create'` or `'kb:' + id`);
  - `renderKnowledgeSection` remounts only on a key change: `handle.destroy()`, then `sectionContentEl.replaceChildren()`, then the mount. A same-key render keeps the editor and its unsaved edits;
  - `onSaveSuccess` calls `reloadLibrary('knowledge-bases')` and **no** remount;
  - the poll is untouched, apart from going through the kept handle;
  - `reset()`, `leaveKnowledgeDetail_`/`discardOpen_` and the create and root branches call `handle.destroy()` and null it;
  - the loading line `'Loading knowledge base…'` and the failure line `'Failed to load knowledge base.'` become `App.ui.status` lines (pending/danger, `led: false`, `live: 'off'` for loading) placed with `replaceChildren()`. That removes the two sinks plus the clear. The `admin-loading` class goes (check that no test reads it on this path);
  - `kbFocusFolderFor` focus after a create, and `App.focusAfter.flush()` on mount, stay for the create → detail remount.
- **The detail handle** returns `{updateStatus, updateItems, destroy}`. `destroy` releases the `mountSlot`, calls each sub-module's destroy (add a no-op `destroy` to the modules that have none yet; 05b, 06a and 06b fill them), and marks the mount not current, so late Save, search or panel responses do nothing.
- **Pins and docs:**
  - the `HTML_SINK_ALLOWANCE` row for `knowledge-glue.js` is removed (3 → 0);
  - ownership rows for the classes these frames stop emitting are removed (`editor-header*`, `editor-title`, `editor-breadcrumb*`, `editor-unsaved`, `form-actions`, `btn-*` for the header buttons, `field-hint`/`field-error` where moved);
  - `test_store_static.py` is retargeted where needed;
  - the `docs/ui-testid-registry.md` manual-exception rows for `save/cancel-knowledge-btn` and `kb-create-*` move to the literal table;
  - `agents.md`'s knowledge section notes that Save patches in place.
- **New browser tests:**
  - (a) Save keeps the editor mounted (a marker on the shell `el`), keeps an expanded folder panel open, and keeps a typed search query and its results;
  - (b) Save updates the title, the subtitle and the Library row;
  - (c) type and revert, and it is clean;
  - (d) Cancel restores from the last saved record (after a Save, then an edit, Cancel shows the saved values);
  - (e) a double-click on Create makes one knowledge base;
  - (f) leaving for the Library root during a Save in flight: nothing writes after `destroy`, and the route stays at the root;
  - (g) focus after Save is on the title, and after a failed Save it is on Save.

## Design review amendments (binding; they supersede earlier text where they differ)
Design review cycle 1 (Sonnet Developer): approve with changes. **The citations after the split:**
- `renderKnowledgeCreate` is at `knowledge-create.js:36-142` (`reportDirty` about `:93`, the Create click about `:110`);
- `renderKnowledgeDetail` is at `knowledge-detail.js:48-300`: header about `:59-78`, dirty about `:111-148`, Cancel `:150`, Save `:160-205`, composition about `:207-260`, danger `:262-299`;
- in the glue: the clear `:72`, the sinks `:189` and `:263`, `onSaveSuccess` `:233-237`, the poll `:276-335`, `reset` `:339-342`;
- `test_store_static.py` rows `:265`, `:282-299`; `HTML_SINK_ALLOWANCE` `knowledge-glue.js: 3` at `tests/test_ui_guards.py:156`.

1. **Leaving the area tears the editor down.** `studio.js`'s `deactivate` (about `:735-745`) calls `knowledgeGlue.reset()`, which destroys the handle and nulls the key, so a Library → Chats → Library return is a fresh mount, as today, and the poll restarts. Add a test: open the detail, go to Chats, return, and the `/status` requests resume.
2. **One `mountSlot` in `knowledge-glue.js`** covers both the create and detail handles. `isCurrent(token)` replaces `kbGen` and the stale-then checks.
   - **Keys:** `'create'`, `'kb:' + id`, or `null` (the root). The key is set before the async load.
   - **`reset()` nulls the key and destroys the handle.** `discardOpen_` reaches it through `closeOpenItem`.
   - A failed load (the "Failed to load" branch) and a load resolving as gone release the key, so a same-route render retries.
   - **A same-key render** runs only `syncLibrarySelection(false)`. It does not touch `state.dirty`, consume `_kbFresh`, or clear the host.
   - The precedent for `destroy` and late-write gating is leg 07a's amendments (5, 6), not the provider editor, whose slot has a no-op destroy.
3. **Semantic test changes, listed in the flight log as such:**
   - **invert** `test_flow_studio_library_list.py::test_kb_breadcrumb_survives_a_save_remount_and_the_poll_keeps_running` (about `:874-895`): the breadcrumb mark now survives a Save, and the poll check stays. Rename it, for example `…_survives_a_save_in_place_…`;
   - update the stale comments at about `:1034` and `test_router_items.py` about `:581`.
4. **Save while typing.** While busy, the two inputs are disabled as well as the shell buttons. On success:
   - `stored = updated`;
   - the fields are written from `updated` (the trimmed name);
   - the 43-code-point hint is refreshed;
   - `snapshot = readValues()`;
   - dirty is recomputed;
   - the inputs are re-enabled.
5. **No write after `destroy`.** All of these check `isCurrent`:
   - `callbacks.onDirtyChange` (the shared `state.dirty`);
   - `refreshStatusNow`/`refreshItemsListNow`;
   - `triggerReindex`;
   - the search handler;
   - the Save and Create handlers;
   - `focusAfter` restores, with `App.focusAfter.cancel()` called in `destroy`.

   Every sub-module returns a real object with `destroy` (`knowledgeSearch.create` returns nothing today).
6. **`App.focusAfter.flush()` in `mountKnowledgeDetail` is removed:** nothing defers into it once Save stops remounting. `kbFocusFolderFor` keeps its own focus call.
7. **Test (e)** is a regression pin: the double Create is already pinned at `test_flow_studio_library_list.py` `:486-491`. The new behaviour is that Cancel is disabled during an in-flight Create (`setBusy`); add a ledger row and a test. **Test (a)** counts `/items` requests only (the poll fetches `/status` by itself).
8. **`kb-create-error`** is `App.ui.status({state: 'danger', led: false, role: 'alert', textTone: true, testid: 'kb-create-error'})`, using 03b's new `textTone` option (amended into 03b), placed where it is today. Its text is empty until an error.
9. **Sections:**
   - the fields block is a title-less `App.ui.section`, as a direct child of the root wrapper;
   - `div.knowledge-inventory.knowledge-detail[data-testid=studio-knowledge-inventory]` stays (tests key on it, and the order test uses `.editor-section > .section-title`);
   - `shell.titleEl` replaces the `liveTitleEl` global query;
   - after this leg, the dead helpers in `knowledge-shared.js` (`breadcrumb`, `unsaved`, `showUnsaved`, and `input`/`textarea`/`fieldGroup` if unused) are deleted with their allowance rows, which live in `knowledge-shared.js`;
   - fix the stale "Status → Folders" header comment in `knowledge-detail.js`.
10. **`fetchJson`:** the `test_store_static.py` create anchor changes to the `fetchJson` form, so retarget it. Keep the `invalidate` calls between the request and the callbacks. Non-JSON errors now read "Server error N …": a ledger row.
11. **Loading and failure lines:** loading is `status` pending with `live:'off'` and `led:false`; failure is `status` danger with `role:'alert'`, `led:false` and `textTone:true`.
12. **Edge case:** if `open()` bails after a successful Create (the user moved, or a guard is deciding), the form stays busy, as today. Record it.

## Acceptance Criteria
- [ ] The create form and the detail frame are built from `editorShell` and `field`. `knowledge-create.js` and `knowledge-detail.js` hold no hand-built header, breadcrumb, caption or field group.
- [ ] New tests (a)-(g) pass. The existing knowledge, Library-list, router and guard tests pass; any test change is a selector or locator move, listed in the flight log.
- [ ] `HTML_SINK_ALLOWANCE` has no `knowledge-glue.js` row, and `git grep -n innerHTML -- the_one/interfaces/web/static/js/areas/studio/knowledge-*.js` is empty.
- [ ] The ownership allowance shrinks for the knowledge modules, with no row added.
- [ ] A Save no longer re-fetches `/status` and `/items` (count the requests in test (a)).
- [ ] The `library`, `mcp`, `routing` and `shared` lanes pass under `THE_ONE_TEST_NETNS=1`, and so do `make test-unit` and the static guards.
- [ ] **Ledger rows:** the header via `editorShell` (if any computed difference); the loading and failure lines as status lines; revert-to-clean (already true here: none); any other difference, with a reason.
- [ ] The `library` lane's time is reported against its budget.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_flow_studio_knowledge_inventory.py -x --timeout 60`
- `--lane library`, `--lane mcp`, `--lane routing`, `--lane shared`; `make test-unit`.

## Implementation Guidance
1. **Log a start line.** Read leg 02's entry and the provider editor (and 07a's landed code if present).
2. **Write tests (a), (e) and (f) first;** (a) and (e) fail today.
3. **Rebuild the create form,** then the detail frame and value model, then Save and Cancel.
4. **Change the glue's mount path,** then the loading and failure lines.
5. **`destroy` wiring**, then pins, docs, ledger and the flight log, with in-progress lines.

## Edge Cases
- **Save while the poll is updating:** `updateStatus`/`updateItems` run between Save's request and its response. The patch must not touch the folder or status nodes, only the shell and the fields.
- **A rename and the agents' Knowledge tab:** `invalidate('agents')` stays, because a rename rewrites `kb_ids` and tool names (DD8 of Mission 24).
- **The breadcrumb close during a dirty edit:** the router guard asks once (`App.nav`). `onDirtyChange` must report every transition.
- **A same-key render with the list notification** (`syncLibrarySelection`) must not reset the fields.

## Files Affected
- `js/areas/studio/knowledge-create.js`, `knowledge-detail.js` (and no-op `destroy` stubs in the other knowledge modules), `knowledge-glue.js`
- `css/studio.css`: rules only these frames used (grep; the cascade-layer rule)
- `tests/browser/test_flow_studio_knowledge_inventory.py` (new tests; locators)
- `tests/test_store_static.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`, `docs/ui-testid-registry.md`, `the_one/agents.md`
- The flight log

## Citation Audit
Drafted at `332496d` against the pre-split file and `knowledge-glue.js:60-345` (FD read). **Re-checked after leg 02 lands:** the FD replaces the old line references with the landed module and function names before this leg goes `ready`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
