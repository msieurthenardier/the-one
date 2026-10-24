# Leg: knowledge-rows-split

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Split `static/js/areas/studio/knowledge-folders.js` (897 lines) so every knowledge module is ≤ 800 lines, with **no behaviour change**. Fix its stale invariant comments, unify the duplicated `baseName`, and land squawk 0245 (the connector pairing expiry shows a raw ISO timestamp), the leg's one visible change.

## Context
- **Flight decisions:** DD2 (the line guard), DD9 (0245 absorbed here), DD11; the Flight 3 debrief, Technical ("`knowledge-folders.js` is 897 lines") and recommendation 3.
- **The natural seam** (Flight 3 debrief, recon item 1):
  - **row building and patching:** `buildFileItemRow` `:236`, `patchFileItemRow` `:302`, `renderRows` `:390`, `removeFile` `:430`, `focusAfterRemove` `:467`;
  - **the Individual files panel:** `buildIndividualFilesPanel` `:741`, `renderIndividualFiles` `:758`;
  - **what stays:** panels and grouping (`buildFolderPanel`, `renderFolders`, `renderAllItems`, `addFolder`, `deleteFolder`).

  It is **not mechanical**:
  - `removeFile` calls `renderAllItems` (`:453`);
  - rows share `syncChildren` (`:101`), `setTextIfChanged`, `setAttrIfChanged`, `newGroup` and `releaseRow`, and per-mount state (`removedIds`, tombstones, the `group.order` arrays, `isCurrent`).

  The new module gets that state through a `ctx` or a returned handle, never through shared closure variables.
- **`syncChildren` moves to `knowledge-shared.js`** in this leg, so both modules can use it. Leg 03b then promotes it to `App.ui.util.syncChildren`. Do not promote it here.
- **Squawk 0245:** `connector-editor.js:457` shows `'Expires ' + result.expires_at` (a raw ISO string). Show "Expires {date}, {time}" with the ISO value in `title` on `span.connector-pairing-expiry`. DD14 as worded since the M31 F3 HAT. This is ledger row 42.
  - **The formatter:** promote `App.time.formatDateTime(iso)` in `time.js` (the only module allowed to call the Date getters). It is `formatDate + ', ' + formatClock`, and returns the raw string for an invalid date. `knowledgeShared.formatStamp` delegates to it, and the connector editor calls it. This keeps the connector free of a knowledge-module dependency. Add a `time.js` test beside its existing tests.
  - **WebKit:** `expires_at` is `datetime.now(timezone.utc).isoformat()` (microseconds, `+00:00`; `api.py` about `:4327`). Cover WebKit's parse of 6-digit fractional seconds in the test, both engines. Silently falling back to the raw string is the failure to catch.
  - It is a one-shot render; no `App.time.onChange` listener.
  - **Tests:** the existing `to_contain_text("Expires")` assertions (`test_studio_connector_editor.py:224/267`, `test_flow_studio_library_list.py:1419/1425`) still pass. Add a regex on the text (`Expires [A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2} (AM|PM)`) and `title` equal to the ISO value. Re-run the bounding-box gap test at about `:230`.
  - **Behavior spec:** `tests/behavior/stub-connector-round-trip.md:123` ("`Expires <ISO8601>`") is amended.
- **Duplicated `baseName`:** keep `knowledge-shared.js`'s implementation unchanged (single-separator rule, trailing separator stripped). It is consistent with its siblings `_containingFolder` and `_relativeItemPath`. `knowledge-search.js` uses it. This changes search hit titles only for mixed-separator or trailing-separator paths, which real hit paths never are; ledger row 44 records it. Pin it with a `page.evaluate` on `App.studio.knowledgeShared.baseName` in `test_flow_studio_knowledge_inventory.py` (the `knowledge` lane): a Windows path `C:\a\b.txt`, a trailing-separator path, and a plain path. `knowledge-search.js:66`'s private `el(tag, cls, text)` has a different signature from the shared `el(tag, {className, text})`, so rewrite each of its call sites, rather than moving it.
- **Stale comments:** leg 01's squawk 0246 work already rewrote `:62` and `:783`. What remains:
  - the header's "Poll-vs-mutation split" paragraph, which contradicts the next one about `renderFolders` re-running `renderAllItems`;
  - the module's one-line description;
  - the `create(ctx)` handle documentation.

  Split the roughly 80-line header between the two files. Also update `knowledge-detail.js:4`'s module list. Re-grep every function name rather than trusting the line numbers: the file is being edited.

## Inputs
- Leg 01 landed: the line guard lists `knowledge-folders.js` with ceiling 897.
- `knowledge-folders.js` exports `App.studio.knowledgeFolders = {create}`, and its handle is used by `knowledge-detail.js`. The handle's public shape must not change.

## Outputs
- `static/js/areas/studio/knowledge-rows.js` (new): the row and Individual-files code, as `App.studio.knowledgeRows.create(ctx)` or another pattern that matches the existing knowledge modules (read `knowledge-detail.js` for how they are wired).
- `knowledge-folders.js` ≤ 650 lines; `knowledge-rows.js` ≤ 450 lines.
- `knowledge-shared.js`: `syncChildren`, the one `baseName`, and `el` (it already has `el`).
- `index.html`: the new tag in the knowledge group, in load order before `knowledge-folders.js`.
- The line guard's `knowledge-folders.js` entry removed (it is under 800 now).
- `connector-editor.js`: the pairing expiry humanised (0245); squawk 0245 completed.
- `the_one/agents.md`'s knowledge module map names the new module; the ledger row for 0245 is added.

## Acceptance Criteria
1. No knowledge module is over 800 lines. The line guard has no `knowledge-folders.js` entry and passes.
2. **No behaviour change in the knowledge editor.** The `knowledge` lane passes with no assertion weakened or behaviour added (path pins only). The `library` lane passes.
3. **A DOM dump compare** for the `kb-detail` surface with a folder expanded and the Individual files panel showing (`scripts/ui_capture.py --keep-running` seed) matches before and after, byte for byte.
4. The **Flight 3 HAT invariants still hold**, each proven by its existing test:
   - the tombstones;
   - one DELETE per remove;
   - the focus chain after a remove;
   - the orphan hold-out;
   - the 0088 armed-summary invariant;
   - the no-re-append `syncChildren` rule.

   List each test name in the flight log.
5. One `baseName` and one `el` across the knowledge modules (`git grep -n "function baseName\|function el(" static/js/areas/studio/knowledge-*.js` shows only `knowledge-shared.js`). The separator behaviour is pinned by a test.
6. **Squawk 0245:**
   - The pairing expiry reads "Expires {date}, {time}" in the operator zone, with `title` holding the ISO value. A test asserts the text format (not the time) and the `title`.
   - Squawk 0245's Corrective Action and Verification are written, with status `completed`.
   - Ledger row 42 is added.
7. Pins retargeted, not relaxed:
   - `tests/test_store_static.py` has no `knowledge-folders.js` pin (none expected); `tests/test_area_module_size.py`'s entry is removed, and the guard checks the new file too;
   - `docs/ui-control-inventory.md`, `the_one/agents.md` and `studio.css` comments that name moved functions get their path refreshed;
   - the testid registry is unchanged (no testid added or removed);
   - `scripts/run-tests.sh` `knowledge_pat` is unchanged (no new test file) unless one is added.
8. The static guards and the unit tier pass.

## Verification Steps
- `wc -l static/js/areas/studio/knowledge-*.js`.
- `.venv/bin/python -m pytest tests/test_area_module_size.py tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_store_static.py tests/test_index_asset_cache_busting.py -q -x --timeout 120`.
- Lanes `knowledge` and `library` under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`. Also the connector editor file for 0245: `tests/browser/test_studio_connector_editor.py` is in `library`.
- The DOM dump compare (criterion 3).
- `make test-unit` once at the end.

## Implementation Guidance
1. Read `knowledge-folders.js` end to end, then `knowledge-detail.js`, `knowledge-shared.js` and `knowledge-search.js`.
2. Take the DOM dump "before" first.
3. Move the helpers to `knowledge-shared.js`, then move the row code verbatim into the new module. The cycle between `removeFile` and `renderAllItems` goes through a `ctx` callback (`ctx.renderAll()`) supplied by `knowledge-folders.js`.
4. Fix the stale comments to describe the code as it is.
5. Do 0245 last, separately (the only visible change).

## Edge Cases
- **`renderAllItems` is re-entered** from `removeFile`'s success path. The callback must call the folders module's current function, not a captured stale one.
- **Tombstones (`removedIds`) are per mount.** A remount (a new identity) gets fresh state, the same as today.
- **Late responses after an unmount** must still fail `isCurrent()` in both modules.

## Files Affected
- `static/js/areas/studio/knowledge-folders.js`, `knowledge-rows.js` (new), `knowledge-shared.js`, `knowledge-search.js`, `connector-editor.js`, `static/index.html`.
- `tests/test_area_module_size.py` (the allowance entry removed), `tests/test_store_static.py` (if pinned literals moved), browser tests for 0245 and `baseName`.
- `the_one/agents.md`, `squawks/0245-*`, the flight log.

## Citation Audit
Checked at `512616b`:
- `knowledge-folders.js` functions at `:101` `syncChildren`, `:236` `buildFileItemRow`, `:302` `patchFileItemRow`, `:390` `renderRows`, `:430` `removeFile`, `:467` `focusAfterRemove`, `:741` `buildIndividualFilesPanel`, `:758` `renderIndividualFiles`, `:789` `renderAllItems`, `:896` the export: verified (FD grep).
- `connector-editor.js:457` `'Expires ' + result.expires_at`: verified (FD read).
- `knowledge-shared.js:98` `baseName`, `:111` `formatStamp`; `knowledge-search.js:66`, `:75`: from the recon, not re-read.


## Design Review Amendments (cycle 1, 2026-10-23)
These override anything above they contradict.

**The real seam is two-way.** Write this contract into the code's header comments.
- **Moving to `knowledge-shared.js`** (used by both modules): `syncChildren` (keep its `(parent, nodes, offset)` signature here; leg 03b changes its roughly 8 call sites), `setTextIfChanged`, `setAttrIfChanged`. `skipText` stays in folders.
- **The rows module's handle** (`App.studio.knowledgeRows.create(ctx)`):
  - `newGroup`, `releaseGroup`, `closeGroupMenus` (the folder panels use them: `buildFolderPanel`, the stale-panel path, `destroy`);
  - `renderRows`, `removeFile`, `focusAfterRemove`;
  - the Individual files panel: `buildIndividualFilesPanel`, `renderIndividualFiles`, and `individualSummary()` for `focusAfterInspect`;
  - `destroy()`.
- **`ctx` from folders to rows:**
  - `isCurrent` (the same closure for both modules, so late `removeFile` responses are dropped);
  - `folders()`, a getter for `currentFolders`. It is reassigned on every `renderFolders`, so never pass the array;
  - `markRemoved(id)`, which owns the tombstone;
  - `renderAll()`, a thin wrapper `if (lastItems) renderAllItems(lastItems)`, never a captured function, because `renderAllItems` is re-entered;
  - `attachIndividual(detailsEl | null)`, so `syncPanelList` keeps owning `foldersListEl`'s order;
  - `focusAddFolder()`;
  - the existing `setHeaderError`, `refreshStatus`, `refreshItems`, `openChunks` and `openSource`.
- **Rule:** `removedIds` and `lastItems` live in folders only. Rows never read them.
- **`focusAfterInspect` stays in folders** and reads the Individual files summary through `rows.individualSummary()`.
- **Initialisation order:** `rows = knowledgeRows.create(...)` runs before the inline `renderFolders(currentFolders)` call (about `:822`). Callbacks tolerate being called before `lastItems` and `folderPanels` are assigned.

**The DOM dump** is the `outerHTML` of the Folders section, not a screenshot. It is taken in a throwaway Playwright script, or through leg 01's `--keep-running` instance. The fallback, if leg 01 has not delivered that flag: any scratch instance on port 8490 or higher, seeded through the API. The seed must reach every branch:
- an indexed row and a pending or failed row with an error;
- a folder-relative row;
- an Individual file;
- an Individual file inside a registered folder (the DD-9 chip).

Timestamps are normalised by shape. Compare before and after.

## Design Review Amendments (cycle 2, 2026-10-23)
- **Who owns the Individual files state.** Rows owns `individualPanel` and the attached flag, and calls `ctx.attachIndividual(detailsEl | null)` when it changes. Folders stores only the element, for `syncPanelList`'s ordering (with `lastFolderOrder`, which stays in folders). `focusAfterRemove` uses rows' own panel and flag. Folders' `destroy` calls `rows.destroy()`.
- **The `group.order` arrays belong to rows.** Folders never reads them. Folders calls `rows.renderRows(group, …)` from `renderAllItems`, and `rows.releaseGroup` on the stale and destroy paths.
- **AC5's grep** is `git grep -nE "function (_?el|baseName|_baseName)\(" -- 'the_one/interfaces/web/static/js/areas/studio/knowledge-*.js'`, and it shows only `knowledge-shared.js`. `knowledge-search.js` calls `K.el(tag, {className, text})`, with its call sites rewritten.
- **The 0245 test** keeps the explicit cross-engine `App.time.formatDateTime` case and the NaN fallback case, in `tests/browser/test_ui_time_contract.py` (the existing `time.js` tests).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
