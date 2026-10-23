# Leg: knowledge-split

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Split `static/js/areas/studio/knowledge-section.js` (1493 lines) into the DD3 modules of at most 800 lines each, with **no change in behaviour or DOM**. Retarget every static pin that names the file.

## Context
- **Flight DD3:** the module table, the ctx precedent (`providers-section.js`), the pins to retarget. **DD11:** pins are retargeted, never relaxed; and the in-progress log lines.
- **Flight 2 DD1 is the precedent:** the `studio.js` split, legs 02a/02b/03.
  - Each new module is an ES5 IIFE that attaches a factory under `window.App.studio`.
  - It reaches the editor only through a ctx object it is given.
  - No module keeps a module-level copy of per-mount state.
- This is a pure restructure. **Any visible change, any changed testid or DOM, and any test that has to change behaviour (as opposed to a path pin) is a defect.** Per the flight's adaptation criteria, divert if that happens.
- Leg 05a will put `mountSlot`, `destroy` and the library frame onto these modules. **This leg does not.**

## Inputs
- `knowledge-section.js` at the branch tip (as at `08562ec`). Its top-level functions:
  - the helpers `_el` (`:146`), `_appendIcon` (`:163`), `_btn` (`:171`), `_breadcrumb` (`:185`), `_unsaved`/`_showUnsaved` (`:199-209`), `_input` (`:210`), `_textarea` (`:222`), `_fieldGroup` (`:234`), `_section` (`:245`), `_errorMessageFromResponse` (`:252`), `_containingFolder` (`:277`), `_relativeItemPath` (`:307`), `STATUS_LABELS` (`:142`);
  - `renderKnowledgeCreate(container, callbacks)` (`:335`);
  - `renderKnowledgeDetail(container, kb, state, callbacks)` (`:449`), which holds:
    - the snapshot and dirty functions (`:514-547`);
    - the item-menu machinery `closeAnyOpenItemMenu`/`buildItemMenu` (`:664-762`);
    - the chunks and source panels (`:768-853`);
    - the file rows and folder panels (`:866-1182`);
    - `renderAllItems` (`:1184`);
    - `refreshStatusNow`/`refreshItemsListNow` (`:1215-1240`);
    - the status summary and re-index (`:1295-1374`);
    - search (`:1395-1441`);
    - the danger zone (about `:1446-1480`).
  - Exports at `:1491-1492`: `App.studio.renderKnowledgeCreate`/`renderKnowledgeDetail`.
- `index.html:79` loads the file. `knowledge-glue.js` (`:107`) is the only caller.
- **Pins that name the file:**
  - `tests/test_store_static.py:265` (`("areas/studio/knowledge-section.js", 2)`, the invalidate count) and `:283`, `:289`, `:295` (the `INVALIDATION_ROWS`);
  - `tests/_ui_ownership_allowance.py:128-…` (27 rows);
  - `docs/ui-control-inventory.md` (the rows naming it, about `:55`, `:101`, `:118`);
  - `the_one/agents.md` (its references);
  - a docstring reference in `tests/browser/test_flow_studio_knowledge_inventory.py:1220`;
  - `HTML_SINK_ALLOWANCE` has no row: the file has 0 sinks.
- **Requires leg 01 to have landed** (its squawk 0233 replaces the exact `len(refs) == 93` pin, so seven added scripts and one deleted need only a valid order). If 0233 is not in the tree, stop and report rather than bumping the count.
- **The `state` parameter** of `renderKnowledgeDetail` is the glue's initial-fetch snapshot `{status, items}` (`knowledge-glue.js` about `:214`), not the studio `state` object. It is read only at construction. `initialStatus.folders` is shared by reference into `currentFolders`; keep that.
- **The Makefile's `verify-serving`** derives only `admin/` files (`ADMIN_JS_ROOT`, about `:158`), so it needs no change here.

## Outputs
- **New modules** under `static/js/areas/studio/`, each ≤ 800 lines. Names and boundaries come from DD3 and may vary within its table:
  - `knowledge-shared.js`: `STATUS_LABELS`, the element helpers, `_containingFolder`, `_relativeItemPath`, `_errorMessageFromResponse`, exposed as `App.studio.knowledgeShared`;
  - `knowledge-create.js`: `renderKnowledgeCreate`;
  - `knowledge-detail.js`: `renderKnowledgeDetail`, the frame, the fields, dirty tracking, the danger zone and the composition. It creates the other modules with a ctx and returns `{updateStatus, updateItems}` exactly as today;
  - `knowledge-folders.js`: add folder, the folder panels, Other items, file rows, the item menu, folder delete, `renderAllItems`, `renderFolders`;
  - `knowledge-inspect.js`: the chunks and source panels;
  - `knowledge-status.js`: the status summary and re-index;
  - `knowledge-search.js`: search.
- **`knowledge-section.js`** is deleted, or reduced to nothing but the two exports if that keeps the glue untouched. Prefer deleting it and exporting from the new modules, with `App.studio.renderKnowledgeCreate`/`renderKnowledgeDetail` keeping the same names and signatures.
- **`index.html`** loads the new scripts in place of `knowledge-section.js` (about `:79`), all before `knowledge-glue.js` (`:107`), in this order: shared, create, inspect, status, search, folders, detail.
- **Pins retargeted:**
  - **`test_store_static.py`:**
    - `:265` `("…/knowledge-section.js", 2)` becomes `knowledge-detail.js`, 2 (both agents invalidations, rename and delete, stay in the detail);
    - the create row (`fetch('/api/knowledge-bases', {` … `onCreateSuccess(kb)`) moves to `knowledge-create.js`;
    - the rename and delete rows move to `knowledge-detail.js`;
  - **the ownership allowance:** each literal moves with its call site, and the totals stay the same (the ratchet test prints the corrected rows). Rows from shared helpers land where the helper lives: `api:App.icon(` is in `_appendIcon`; `empty-state`, `field-error` and `field-hint` spread across modules;
  - **`docs/ui-control-inventory.md`:**
    - `:55` (the `_el`/`_btn`/`_fieldGroup` copies) and `:101` (`_breadcrumb()`) go to `knowledge-shared.js`;
    - `:118` (`buildItemMenu`) goes to `knowledge-folders.js`;
  - **`the_one/agents.md`:** grep for `knowledge-section`. Known references:
    - `:1381` `buildFileItemRow`, `:1382` `updateFolderMeta` and `:1432` `renderAllItems` go to folders;
    - `:2152` the `checkDirty` list goes to detail;
    - `:2163` `_breadcrumb()` goes to shared;
    - `:2167` `renderKnowledgeCreate` goes to create;
    - `:2299-2300` the invalidation map goes to create and detail;
  - **the docstring** at `tests/browser/test_flow_studio_knowledge_inventory.py:1220`, which cites `knowledge-section.js:1111`, becomes the new file plus the function name, with no line number;
  - **finally,** `git grep -n knowledge-section -- ':!missions' ':!sorties' ':!tests/behavior/*/runs'` is empty.
- **`agents.md`'s "Studio area modules" section** gains a short "Knowledge modules (M31 F3 L02)" paragraph: the module list, the ctx, and which module owns which state.

## Acceptance Criteria
- [ ] `wc -l` shows every new knowledge module ≤ 800 lines. `knowledge-section.js` is gone, or holds only the exports.
- [ ] **The rendered DOM is unchanged.** The before dumps are taken from a pre-edit checkout (a `git worktree` at the leg's start commit), because they cannot be recreated once the file is split. Make them deterministic: fulfil `/api/knowledge-bases/{id}`, `/status` and `/items` with fixed JSON through Playwright `page.route`, or normalise ids and timestamps. Dump:
  - (a) the create form;
  - (b) the detail after mount, with a folder expanded, a file in it, and an Other items panel holding a standalone-badged file;
  - (c) the same detail after one `handle.updateStatus(…)` and one `handle.updateItems(…)` with changed data;
  - (d) with the chunks and source panels open.

  `diff` of before against after is empty for all four. The dumps and the script are not committed.
- [ ] `tests/test_store_static.py`, `tests/test_ui_ownership.py`, `tests/test_ui_guards.py`, `tests/test_ui_control_inventory.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass. Ownership-allowance totals are unchanged: the same row sum, only file keys moved.
- [ ] The `library` lane passes (`THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane library --tb=short`), and so do the `mcp` lane (`test_flow_studio_library_list.py`), `routing` and `shared`. **No browser test file changes**, apart from the docstring path.
- [ ] `make test-unit` passes (12 skipped off netns, or 14 under netns).
- [ ] The full gate: `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` exits 0.
- [ ] No module keeps per-mount state at module level. Each module's state lives inside its `create(ctx)` call or the detail's closure, and nothing is cached across mounts.

## Verification Steps
- `wc -l the_one/interfaces/web/static/js/areas/studio/knowledge-*.js`
- The DOM dumps compared with `diff`.
- The listed unit tests, the four lanes, then `make gate` with the env above.
- `git diff --stat tests/browser`: only the docstring path line.

## Implementation Guidance
1. **Log a start line** in the flight log (DD11).
2. **Move the pure helpers first** (`knowledge-shared.js`). Run `library`.
3. **Move `renderKnowledgeCreate`** (`knowledge-create.js`).
4. **Extract the detail's inner sections one at a time** into factories: inspect, then status, search and folders.
   - **The composition order in the detail must reproduce today's DOM order:** header, fields, Folders, Status, Search, Danger Zone. `_section` appends at call time. So `inspect.create` comes first (it appends nothing yet), then `folders.create`, then `status.create`, then `search.create`, then the danger zone. The detail then appends the inspect panels to `foldersSection` after `foldersListEl`, where they are today.
   - **Cross-module calls use lazy wrappers,** for example `openChunks: function (i) { return inspect.openChunks(i); }` and `refreshStatus: function () { return refreshStatusNow(); }`. Never pass a handle that does not exist yet, and never pass a value copy.
   - **The detail keeps `refreshStatusNow`/`refreshItemsListNow`** (they need both status and folders). `updateStatus(s)` stays `status.update(s)` then `folders.renderFolders(s.folders || [])`, in that order.
   - **Per-mount state** (`openItemMenu`, `folderPanels`, `currentFolders`, `otherItemsPanel`, `chunksPanel`, `sourcePanel`, `summaryEl`, …) lives inside each `create(ctx)`. Only `STATUS_LABELS` and pure helpers sit at IIFE scope. Modules read `App.studio.knowledgeShared.*` directly (it loads first).
   - **The 143-line header comment** is split across the modules: the L6-D2/D3 notes go to folders, so folders stays well under 800.
   - Each takes a ctx with exactly what it reads. For example, the folders module needs `kb`, `container` nodes, `openChunks`/`openSource`, `refreshStatus`, `refreshItems` and the flash helper.
   - Each returns the functions the detail calls (`renderFolders`, `renderAllItems`, `updateStatus`, …).
   - Keep the call order and the timing of DOM insertion identical. Where a function referenced a closure variable of `renderKnowledgeDetail`, pass a getter or the object through ctx, never a copy of a primitive that later changes.
5. **What the detail keeps:** the snapshot and dirty logic, the header and fields, the danger zone and the composition.
6. **After each step:** a log line, and the `library` lane.
7. **Retarget the pins,** update `index.html`, `verify-serving` and the docs, then run the DOM-dump comparison and the full gate.

## Edge Cases
- **`renderStatusSummary` is used at `:1222` and declared at `:1295`.** Today `refreshStatusNow`/`updateStatus` run only from promises and the returned handle, never during construction. After the split, `status.create` must have run before the detail returns. The detail's `refreshStatus`/`updateStatus` read the status handle lazily.
- **The armed-confirm invariant (0088):** `renderAllItems` and `renderFolders` must not rebuild a folder's armed `<summary>`. Keep the keyed-panel reconcile exactly as is. The browser test that pins it (`test_flow_studio_knowledge_inventory.py`, the armed-across-poll test) must pass unchanged.
- **The item menu's document listeners** (`:732-733`) move with the menu, unchanged. Leg 06b replaces them.
- **Gate sequencing.** Run the full gate only when no other leg's gate is running on this host (host policy: three lanes at once).

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js` (deleted or reduced)
- New: `knowledge-{shared,create,detail,folders,inspect,status,search}.js`
- `the_one/interfaces/web/static/index.html`, `Makefile` (if it lists modules)
- `tests/test_store_static.py`, `tests/_ui_ownership_allowance.py`, `tests/browser/test_flow_studio_knowledge_inventory.py` (docstring only)
- `docs/ui-control-inventory.md`, `the_one/agents.md`
- The flight log

## Citation Audit
Checked at `332496d` on 2026-10-22 (FD grep). The design review (Sonnet Developer, cycle 1: approve with changes) verified every line and added the leg-01 dependency, the composition order and lazy ctx, the deterministic dump method, and the exact pin and doc targets:
- `knowledge-section.js:142-335,449,514-547,664,679,768-866,945,1082,1117,1167,1184,1215,1230,1295,1351,1395,1491-1492`;
- `index.html:79,107`;
- `test_store_static.py:265,283,289,295`;
- `_ui_ownership_allowance.py:128-…`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
