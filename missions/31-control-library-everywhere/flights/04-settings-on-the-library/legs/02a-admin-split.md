# Leg: admin-split

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Move the Built-in tools page controller out of `static/js/areas/admin.js` into a new module, `static/js/areas/admin/tools-page.js` (`App.admin.toolsPage.create(ctx)`), with **no behaviour change**, and make the content shell DOM-built (sink 1 → 0).

## Context
- **Flight decisions:** DD1 (one flight), DD10 (lanes and pins; `test_router_core.py:487-510` spies `admin.serializeState`/`hydrateState`), DD11 (standing rules), DD12 (no allowance increase).
- **Mission criterion:** each area entry module is ≤ 800 lines, and the area code is organised by surface. `admin.js` is 760 lines today, and leg 06 and leg 07 would push it past the limit if the tools controller stayed in it.
- **Precedents:**
  - `studio.js`'s split (M31 F2 L01-03): the area object keeps its seams and delegates to section modules through `create(ctx)`;
  - `App.studio.providersSection.create(ctx)`, where a section module reaches the area only through `ctx`.
- **The boundary, from the planning survey** (`f4-survey-pages.md` §1.4 and `f4-survey-tools.md` §1). Re-check it against the code.
  - **The tools half (moves out):**
    - state at about `:171-193`: `scaffold`, `openIntent`, `toolEditorApi`, `toolConfigs`, `toolsInFlight`, `toolFormMode`, `editingTool`, `pendingToolName`, `pendingToolFormMode`;
    - scaffold, flashes and reveal at about `:241-307` (`mountScaffold`, `rescueFlashes`, `revealItem`);
    - the tools panel, list, item, select, fetch and toggle at about `:309-512` (`renderToolsPanel` … `mountToolItem`, `selectTool`, `fetchToolConfigs`, `handleToolToggle`);
    - the open/close click delegation at about `:514-577`;
    - the tools branches of `serializeState` (`:15-24`) and `hydrateState` (`:54-69`, `:81-108`);
    - `_syncItemSelection`, `_setOpenIntent`, `_closeOpenItem` and `_tryConsumePendingTool` (about `:715-746`).
  - **Stays in `admin.js`:** the descriptor (`GENERAL_SUBS`, `serializeState`, `hydrateState`, `init`, `activate`, `deactivate`), the Settings nav (`App.ui.navGroups` from `App.settingsPages`), the content shell, `GENERAL_RENDERERS`/`renderContent`, the Knowledge indexing bridge (`renderKnowledgePanel`), `_refresh`, the `App.nav` dirty source and `_discardEditor`, the shared part of `_setCategory`, `_syncNavSelection`, and the `ROUTE_SECTION` literal.
  - **Shared across the boundary:** `currentCategory`, `dirty`, `editorGen`, `editorDomStale`, `contentEl`, `settingsNav`, `self`. Pass them through `ctx` (getters and setters, or callbacks). The new module never reads `admin.js` closure variables directly.

## Inputs
- Leg 01 landed (the capture tool, the line guard, dead `admin.css` gone). The line guard must stay green.
- `admin.js` 760 lines; `HTML_SINK_ALLOWANCE["areas/admin.js"] == 1` (`:214`); `OWNERSHIP_ALLOWANCE` rows for `js/areas/admin.js`: `api:App.showFlash(` 2, `app-flash` 1, `editor-breadcrumb-link` 1, `editor-header` 1, `editor-title` 1 (all tools code).

## Outputs
- `static/js/areas/admin/tools-page.js` (new): `App.admin.toolsPage.create(ctx)` returns a handle, for example `{render(listEl, itemEl), open(name, opts), close(), refresh(), serialize(), hydrate(rest, opts), isOpen(), discard(), syncSelection()}`. The exact shape is the Developer's, recorded in `agents.md`.
- `admin.js` at about 320-420 lines, delegating to the handle.
- `index.html`: the new `<script>` tag in the admin group, before `admin.js` (the shell-before rule below).
- **Retargeted pins** (never relaxed):
  - `HTML_SINK_ALLOWANCE` (exact counts, fails on any difference): the `"areas/admin.js": 1` row is removed. No sink moves; `tools-page.js` adds none.
  - `OWNERSHIP_ALLOWANCE` (exact, file-keyed): the five `admin.js` rows (`api:App.showFlash(` 2 at `:443`/`:594`, `app-flash` 1 `:275`, `editor-breadcrumb-link` 1 `:570`, `editor-header` 1 `:303`, `editor-title` 1 `:304`) become `tools-page.js` rows with the same counts. `admin.js` ends with **zero** rows. Run the test and paste its printed dict into the flight log; the whole-app total is unchanged.
- `tests/test_settings_pages_static.py`: the label-literal check adds `areas/admin/tools-page.js` to its scanned set, and only that file. Five other admin files already hold page labels (`system-page.js:45`/`:141`/`:192`, `date-time-page.js:66`, `tools-editor.js:211`); their pages move to `App.settingsPages` labels in legs 07a-09. The moved code reads its label through a `ctx.pageLabel(category)` callback and never copies 'Built-in tools'.
- `tests/test_index_asset_cache_busting.py`: add `("js/areas/admin.js", "js/areas/admin/")` to the shell-before tuple list (`:90-97`, today only `studio.js` and `chat.js`). In `index.html`, `tools-page.js` goes after `tools-grid.js`/`tools-editor.js` and before `admin.js`.
- `the_one/agents.md` "Settings item pages" and CLAUDE.md's "Settings item pages" paragraph name the new module.

## Acceptance Criteria
1. Both files are under the 800-line guard with no new allowance entry; this is the gate. Targets, not gates: `admin.js` about 330-400, `tools-page.js` about 480-520.
2. **No behaviour change.** Every test in the `settings` and `routing` lanes passes unchanged except for path pins: no test asserts a new behaviour, and no assertion is weakened. `test_router_core.py`'s `admin.serializeState`/`hydrateState` spy passes unchanged.
3. The area object keeps every seam a test reads: `_dirty`, `_currentCategory`, `_toolFormMode`, `_editingTool`, `_pendingToolName`, `_pendingToolFormMode`, `_setCategory`, `_closeOpenItem`, `_tryConsumePendingTool`, `_syncItemSelection`, `_syncNavSelection`, `_setOpenIntent`, `_refresh`, `_discardEditor`. Those owned by the tools page become delegates (property getters and setters that forward to the handle). `git grep -n "_toolFormMode\|_editingTool\|_pendingTool" tests/` shows every reader, and each still passes.
4. **The content shell** (`admin.js:214`, `content.innerHTML = '<div class="admin-content"></div>'`) is built with `App.ui.util.el` or `replaceChildren`. `HTML_SINK_ALLOWANCE` has no `areas/admin.js` row.
5. `tools-page.js` reaches `admin.js` state only through `ctx`. A static check in the leg's own test (or a review grep recorded in the flight log) shows no `admin.js` closure name used in it.
6. `ROUTE_SECTION` and `App.settingsPages` stay in `admin.js` (`test_settings_pages_static.py`), and the label-literal check passes with `tools-page.js` added to its scanned set.
7. The `index.html` order test passes with the new rule, and `make verify-serving` lists the new file (its list is derived from disk; `tests/test_makefile_verify_serving.py` passes).
8. Lanes `settings`, `routing` and `shared` pass under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`. The unit tier passes.

## Verification Steps
- `wc -l` on both files.
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_settings_pages_static.py tests/test_index_asset_cache_busting.py tests/test_makefile_verify_serving.py tests/test_area_module_size.py tests/test_store_static.py -q -x --timeout 120`.
- Lanes: `settings`, `routing` and `shared`, each with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane> -q`. At most 3 at once, never alongside the unit suite.
- **A DOM dump compare** (Flight 3 leg 02's method): before the move, record `#main-content` `outerHTML` and the tool tile list for `#settings/tools`, `#settings/tools/read_file` and `#settings/appearance` on a scratch instance (`scripts/ui_capture.py --keep-running`, port ≥ 8490). Repeat after the move. They match byte for byte. Record this in the flight log.
- `make test-unit` once at the end.

## Implementation Guidance
1. Read `admin.js` end to end, and `areas/studio/providers-section.js` for the `create(ctx)` precedent.
2. Move code verbatim first: same function bodies, closure variables turned into module-local state inside `create`, and admin-owned state passed through `ctx`. Do not refactor behaviour; legs 06 and 07 rebuild this code.
3. Keep every `self._…` seam on the area object as a delegate.
4. Update `index.html` (it is lru-cached: a scratch instance needs a restart to see the tag).
5. Update the pins (sink and ownership row moves), the static tests and the docs.
6. Run the DOM dump compare, then the lanes.

## Edge Cases
- **`hydrateState` runs before `init`** in some router paths, which is why it guards `this._setCategory`. Keep those guards; the handle may not exist yet.
- **`editorGen` is bumped by `_discardEditor`** and read by the tools save path. It must stay one counter, shared through `ctx`, not two copies.
- **`_refresh` (activate) re-renders the General pages and the tools page.** The order of the calls must not change.
- **The Knowledge indexing page** uses the same `dirty` mirror and `editorOpen()`. Don't move any of that.

## Files Affected
- `static/js/areas/admin.js`, `static/js/areas/admin/tools-page.js` (new), `static/index.html`.
- `tests/test_ui_guards.py` (`HTML_SINK_ALLOWANCE`), `tests/_ui_ownership_allowance.py`, `tests/test_settings_pages_static.py`, `tests/test_index_asset_cache_busting.py`.
- `the_one/agents.md`, CLAUDE.md.
- The flight log.

## Citation Audit
Checked at `512616b`:
- `admin.js:214` sink: verified (FD read).
- State variables at `:161-193`: verified (FD read; `dirty`, `editorGen`, `editorDomStale`, `scaffold`, `openIntent`, `toolEditorApi`, `toolConfigs`, `toolsInFlight`, `toolFormMode`, `editingTool`, `pendingToolName`, `pendingToolFormMode`).
- Seams `Object.defineProperty(self, '_dirty' …)` and the rest at about `:651-679`: verified (FD grep).
- The rest of the line ranges come from the survey and drift by a few lines; the Developer re-reads them.


## Design Review Amendments (cycle 1, 2026-10-23)
These override anything above they contradict.

**Ownership of `serializeState` and `hydrateState`.** The area methods stay on the area object (`test_router_core.py:487-510` spies them) and keep the shared glue: `GENERAL_SUBS`, `validIds`, the `_setCategory`/`_closeOpenItem` choice, `_setOpenIntent`, `_syncNavSelection`. They call `tools.serialize()` for the `tools…` string and `tools.parseSub(origSub)` (the `tools/<name>` parsing, moved verbatim) to get `{pendingName, pendingMode}`.

**The `ctx` the tools page receives** (one table, recorded in `agents.md`):

| ctx member | Why |
|---|---|
| `getCategory()` | `scaffoldFor`, `selectTool`, `fetchToolConfigs`, `closingItem` read `currentCategory` |
| `setDirty(bool)` | writes at `:343`, `:355`, `:384`, `:387` (the editor bridge), `:435` (the 404 path), `:732` (`_closeOpenItem`) |
| `getGen()` / `bumpGen()` | one `editorGen` counter; `_closeOpenItem` bumps it (`:727`), and `revealItem`, `mountToolItem` and `selectTool` read it; `_setCategory` and `_discardEditor` bump it from `admin.js` |
| `setDomStale(bool)` | the write at `:312`; `_discardEditor` and `_setCategory` keep their own reads and writes in `admin.js` |
| `contentEl()` | `mountScaffold`, `rescueFlashes`, `showAdminFlash` |
| `content` | the click-delegation target (`:561`), a different element from `contentEl` |
| `serializeState()` | `selectTool` calls `App.router.sync('admin', self.serializeState())` (`:421`); keep that exact call and never the `{ name: updated.name }` variant `test_store_static.py:390` forbids |
| `pageLabel(category)` | the scaffold page header label |
| `syncNavSelection()` | the item paths that re-mark the nav |

**The handle** (`App.admin.toolsPage.create(ctx)`):
- `reset()`: replaces `renderContent`'s direct resets of `scaffold` and `toolEditorApi` (the Knowledge and General branches call it);
- `onCategoryChange(category)` and `scaffoldFor(category)`: replace `_setCategory`'s direct writes at `:688-706`;
- `render()`, `refresh()` (keeps `fetchToolConfigs` then `selectTool`, in order), `isOpen()` (for `editorOpen()`), `serialize()`, `parseSub(sub)`, `closeOpenItem()`, `tryConsumePending()`, `syncItemSelection()`, `setOpenIntent(bool)`;
- state accessors for the seams.

`showAdminFlash`, `selectedToolName` and `focusClosedItem` move with the tools code. The `App.nav` source and `editorOpen()` stay in `admin.js`, and `_refresh` stays one body in `admin.js` that calls `tools.refresh()` (Knowledge stays `!dirty`-gated).

**Pre-init contract.** `hydrateState` can run before `init`, and today it assigns plain `this._pendingToolName` data properties that `init`'s `defineProperty` later overwrites. Keep the `if (this._setCategory)` guards. Define the `_*` accessors in `init` before anything can reach the handle. Getters return `null` when the handle is absent, and `serializeState` still returns `'tools'` or `GENERAL_SUBS[0]` when `_toolFormMode` is undefined.

**AC5 becomes a static test.** A small test parses `tools-page.js` for the names `currentCategory`, `contentEl`, `editorGen`, `editorDomStale`, `settingsNav` and a bare `self`, and fails if any appears.

**The DOM-dump fallback.** If leg 01's `--keep-running` is not available, use any scratch instance on port 8490 or higher (started after the `index.html` change, since `index.html` is lru-cached), grab `outerHTML` with Playwright, and wait for `tool-card` before reading, so the loading placeholder is never captured. Normalise flash nodes and timestamps.

**`test_store_static.py:390`** is an affected reader: it scans `admin.js`. Extend it to scan `tools-page.js` too, since that is where the `App.router.sync` call now lives.

## Design Review Amendments (cycle 2, 2026-10-23)
- **The handle shape is the cycle-1 amendment's list.** The body's Outputs bullet example (`render(listEl, itemEl)`, `open`, `close`, `discard`, `syncSelection`) is superseded. The seam accessors on the handle: `toolFormMode`, `editingTool`, `pendingToolName` and `pendingToolFormMode` (get/set). The area's `_toolFormMode`, `_editingTool`, `_pendingToolName` and `_pendingToolFormMode` forward to them.
- **`isOpen()` is exactly `!!toolFormMode`.** `editorOpen()` in `admin.js` stays `(currentCategory === 'tools' && tools.isOpen()) || currentCategory === 'knowledge'`.
- **The AC5 static test** bans each closure name only when it is not a `ctx.` member access: the regex `(?<!ctx\.)\b(currentCategory|contentEl|editorGen|editorDomStale|settingsNav)\b`, and a bare `self` not preceded by `ctx.`.
- **`test_store_static.py`** also gains a positive assertion: `tools-page.js` contains `App.router.sync('admin', ctx.serializeState())`.
- **Line numbers re-checked** by the cycle-2 review: the `dirty` writes are at `:343`, `:354`, `:384`, `:387`, `:435` and `:733`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
