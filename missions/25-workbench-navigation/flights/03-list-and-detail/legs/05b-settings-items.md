# Leg: settings-items (5b)

**Status**: completed
**Flight**: [List and Detail](../flight.md)

## Objective

Settings item pages keep their list visible (DD7):
- **Providers:**
  - **List.** The provider grid becomes the reference spec §8.2 **table** (Name · Type ·
    Used by).
  - **Editor.** Opening a provider, or "Add provider", renders the provider editor
    **below the table** on the same page.
- **Built-in tools.** The tool editor opens **below the tool list**. The tool name is the
  link, and the enable toggle never navigates.
- **Editor chrome.** Both editors carry the breadcrumb, lose their Back control, and show
  the unsaved indicator (DD2).

## Context

- **Flight decisions:**
  - DD7: the table stays and the item opens under it, with its acceptance rules for
    scroll, toggle and focus.
  - DD2: the breadcrumb inside the editor's own header; Back retired; the unsaved
    indicator.
  - DD8: create, Cancel, delete and the focus rule. Leg 2's `sync` announcement already
    covers provider save-create.
  - DD9: "used by" from `App.usage.providerAgents`.
  - §13 D1 and D2: the Status column and the health banner are omitted.
- **Leg 5a** put each page under a page header with the board's labels. Providers has
  "Add provider" (`new-provider-btn`).
- **Providers today** (`areas/admin.js`):
  - `renderProvidersPanel` (`:286-360`) **replaces** `contentEl` with either the grid
    (`populateProviderGrid` `:405`, `providers-grid.js` `renderProvidersGrid` `:23`, tiles
    with `provider-card`) or the editor (`App.admin.renderProviderEditor`).
  - `selectProvider` (`:422`) and `enterCreateMode` (`:427`) are `go` intents.
  - `onSaveSuccess` calls `sync` with the name hint (`:321-334`).
  - `onDeleteSuccess` replaces to the root (`:342-348`).
  - `onBack` uses `go` (`:309-310`), and `onCancel` replaces with bypass (`:312-318`).
- **Provider editor header.** `provider-editor.js:50-70` is string-built:
  `h1.editor-title`, then `.form-actions` holding `back-provider-btn`,
  `cancel-provider-btn`, `save-provider-btn` and `test-connection-btn`.
- **Tools today:**
  - `renderToolsPanel` (`admin.js:441`) replaces `contentEl` with either the grid
    (`tools-grid.js` `renderToolsGrid` `:96`, category tabs plus `tool-card` tiles,
    `role=listitem tabindex=0`, with a `tool-toggle` checkbox, `:60-94`) or the editor
    (`tools-editor.js`).
  - The tools editor header is at `:120-140`, string-built, with `back-tool-btn`,
    `cancel-tool-btn` and `save-tool-btn`.
  - `selectTool` (`admin.js:514`) loads the tool's detail. The tool route is
    `#settings/tools/{name}`. Tools cannot be created.
- **Legs 3 and 4b** set the patterns this leg reuses: the breadcrumb insertion after
  `innerHTML`, the stable unsaved-indicator span, and the focus rule.

## Inputs

- `areas/admin.js`, `areas/admin/providers-grid.js`, `areas/admin/provider-editor.js`,
  `areas/admin/tools-grid.js`, `areas/admin/tools-editor.js`
- `css/admin.css`
- Settings-lane tests:
  - `test_flow_provider_*`;
  - `test_flow_admin_tools_grid`, `test_flow_admin_tools_editor`,
    `test_flow_admin_openrouter`, `test_flow_admin_knowledge_settings`;
  - the shared allow-list files with provider or tool usage.

- **Ground truth after leg 5a** (Flight Director, 2026-10-02; read the leg 5a flight-log
  entry):
  - **Allow-list: 7 files,** every remaining hit this leg's:
    - `test_flow_admin_openrouter`
    - `test_flow_admin_tools_editor`
    - `test_flow_provider_dirty_confirm`
    - `test_flow_provider_grid`
    - `test_flow_provider_setup`
    - `test_router_guard`
    - `test_router_items`

    The goal is an empty allow-list at the end of this leg, and leg 6 asserts it.
  - **Page headers already exist** with the board's labels. The Providers header
    ("Providers", with "Add provider", plus icon, testid `new-provider-btn`) is built with
    DOM APIs in `providers-grid.js`. The §4 geometry is scoped to `.area-admin`, while the
    grids keep 20px padding until this leg.
  - **The grid listbox still reads "LLM providers"** (`providers-grid.js:~45`). Leg 5a
    reverted its rename because `test_store.py:~233, ~251` select it by that name. The
    table replaces the listbox here, so update those two tests to select the table, for
    example `get_by_role("table", name="Providers")`, or through `_lists`.
  - **`Makefile` `verify-serving` lists static files** (`Makefile:~154`). Deleting
    `admin/providers-grid.js` without removing it there breaks `make restart`; leg 5a hit
    exactly that with `section-nav.js`. Remove any file you delete from that list.
  - **`_lists.py` already has Settings helpers** from leg 5a: `settings_nav`,
    `settings_nav_link`, `open_settings_page`, `expect_settings_selected`,
    `settings_page_title`, `SETTINGS_PAGES`. Leg 4b's `close_item` and `breadcrumb_link`
    are there too. Extend them; don't duplicate.
  - **`admin.js`** now has `GENERAL_SUBS` on the area descriptor, a `navGroups` nav, and
    `_setCategory` → `setSelected`, ending in `_syncNavSelection()`. Re-grep every
    `admin.js` line this leg cites, because leg 5a moved them.

## Outputs

**0. A page scaffold** (design review, issue 1, high). Today every panel render replaces
`contentEl` wholesale. The sites are:
- `providers-grid.js:34, 50, 88`;
- `tools-grid.js:112, 122, 178`;
- `provider-editor.js:109`;
- `tools-editor.js:211`, and its Cancel re-mount at `:428`;
- the callers at `admin.js:304, 358, 413, 451, 499, 582`.

This leg changes that:
- **Scaffold.** On each **category** render (Providers, Built-in tools), build the page
  scaffold once: the page header from 5a, then **`.settings-list`**, then
  **`.settings-item`**.
- **Targets.**
  - Table and grid renders target `.settings-list` only, never `contentEl`.
  - `renderProviderEditor` and `renderToolsEditor` receive `.settings-item` as their
    container, so their own `innerHTML` and Cancel re-mounts stay inside it.
- **Close.** **"Close item" clears `.settings-item`.** `_discardEditor` sets
  `editorDomStale` (`admin.js:691`), and `_setCategory` (`:762`) re-renders only on a
  category change, an open item or `editorDomStale`. Make the close and discard path
  empty the section, so a discarded editor never lingers under the table.
- **Guards that suppress list refresh while an editor is open are removed:**
  - `populateProviderGrid`'s early return when `providerFormMode` is set (`:406`);
  - `populateToolGrid`'s early return when `toolFormMode` is set (`:581`).

  The list must refresh while the editor is open.
- **Failure messages.** `fetchProvidersNow` (`:397`) and `fetchToolConfigs` (`:572`)
  write their failure text into `contentEl.querySelector('.entity-tile-grid')`. Retarget
  them to `.settings-list`.
- **Flashes.** `showAdminFlash` and `App.showFlash` append to `contentEl` (`:645`;
  `app.js:192`). That is still valid. The provider editor's flashes go to its own
  container, which is now the item section, so verify they still render.
- **Lifecycle guards.** `editorGen`, `editorDomStale` and the discard path
  (`:684-693`, `:762`) hold state only and assume nothing about `contentEl`. Keep them.

**1. The Providers table** (§8.2).

- **Replaces the grid.** `providers-grid.js` is retired: delete it, or rewrite it as
  `renderProvidersTable`.
- **Page content.** The Providers page content is:
  - the page header ("Providers", "Add provider");
  - the intro: "A provider is an account or server that runs models. Agents pick one in
    their Model section.";
  - a `<table class="providers-table">` with columns **Name · Type · Used by**:
    - **Name.** A **weight-600** `<a href="#settings/providers/{id}">`, carrying the kept
      testid `provider-card` (now on the link).
    - **Type.** A `.badge.badge--{type}` showing the type slug.
    - **Used by.** "{n} agents" from `App.usage.providerAgents`, with "1 agent" in the
      singular.
- **Styling.** Head cells are 11px, `--fg-muted`, weight 500, `padding: 12px`, with a
  border-bottom. Body cells are `padding: 12px` with a border-bottom.
- **Open provider row.** It carries `aria-current="page"` on its link and the selected
  wash on the row.
- **Empty state.** Zero providers shows a pane-size `emptyState`, "No providers yet.",
  with "Add provider", and a **new testid `providers-empty`**. Today's markup has no
  testid: tests use `.admin-provider-empty` and `.empty-canvas .empty-canvas-cta`
  (`test_flow_provider_grid.py:44, 61`; `test_visual_snapshots.py:255`). Update those
  tests.
- **The Name link keeps `data-id`.** `test_router_items.py:191` uses
  `[data-id=…]`.
  - Tests that read `.entity-tile`, `.entity-tile-name` or `.entity-tile-badge` from
    `provider-card` change to read the table cells: `test_flow_provider_grid.py:69-76`
    and `test_flow_admin_openrouter.py:100-103`.
  - `test_flow_provider_grid.py:~140` asserts "LLM Providers". Leg 5a renames it; if 5a
    has not updated it, this leg does.
- **Data** (design review, issue 5).
  - The admin area never reads agents today, so the table mount explicitly calls
    `App.store.get('agents')` and `get('providers')`, and subscribes to both.
  - **While agents are not loaded**, or after a failure, the "Used by" cells show "—",
    never "0 agents".
  - The leg 2 flight-log entry confirms that the list shape carries
    `provider_config_id` (`store.js` `providerAgents`).
  - **The subscription re-renders the table body only.** It never calls
    `renderProvidersPanel`, and never touches `.settings-item`. Leg 2 makes OAuth sign-in
    and sign-out invalidate `providers` (`provider-editor.js:410, ~425`), so the table
    refreshes and the editor stays.

**2. Provider item below the table.**
- **Routes.** `#settings/providers/{id}` and `#settings/providers/~new` keep the table
  and render the provider editor in an **item section** (`.settings-item`) **below the
  table**.
  - `renderProvidersPanel` no longer replaces the page.
  - The editor mounts into the item section, and switching items re-mounts only the
    section.
- **On open:**
  - The page scrolls the editor header into view (`block: 'nearest'`).
  - Focus moves to the editor's `h1`. Add `tabindex="-1"` to `.editor-title` in both
    string-built headers; nothing focuses it today.
  - **Intent opens only.** Focus and scroll happen only when the open came from an
    intent: a row or name-link click, Add provider, or a deep-link boot. They never
    happen on a hydrate refresh, a `_refresh` re-fetch or a store notification. A flag
    passed from the intent path into `_tryConsumePendingProvider` or `selectTool`
    controls this.
  - **Visibility (DD7).** At 1440×900 with up to 6 providers, the selected row and the
    editor header are visible together.
- **Breadcrumb.** "Settings / Providers", inserted into the editor header after
  `innerHTML` (the leg 3 pattern).
  - The section segment is a link to `#settings/providers` (the DD2 refinement from
    leg 4a; testid `editor-breadcrumb-link`).
- **Back retired.** `back-provider-btn` and its wiring are deleted.
- **Unsaved indicator.** A stable `<span class="editor-unsaved" role="status"
  data-testid="editor-unsaved">` inside `.form-actions`, toggled by the editor's dirty
  callback (the leg 3 pattern).
- **Cancel.**
  - **On `~new`:** discard, then `go(href(providers root), { replace: true, bypassGuard: true })`.
    Focus goes to "Add provider", because no row exists.
  - **On an item:** revert in place (unchanged).
- **Delete.** Replace to the root (unchanged). Focus goes to the nearest surviving row's
  link, else "Add provider". Capture the index before the delete.
- **Save-create** (design review, issue 6). It is `sync` with the name hint (leg 2), which
  announces the new provider.
  - The `isCreate` branch's `renderProvidersPanel()` call (`admin.js:337`) is changed to
    re-mount **only the item section** in edit mode.
  - `providerFormMode` is set to `'edit'` and the editing provider is set **before** the
    store notification lands, so the new row renders selected.
- **Back removal includes the wiring.** Delete the `onBack` callback at `admin.js:312`
  and the handler at `provider-editor.js:732`.

**3. Built-in tools: item below the list.**
- **The list stays.** The category tabs and tool tiles keep their card shape (an
  accepted variation in the flight).
- **Name is the link.** In each tile, the **tool name** becomes
  `<a class="entity-tile-name" href="…">`, built with
  `escapeAttr(App.router.href({ destination: 'settings', section: 'tools', id: name }))`.
  - The tile itself is no longer a click target. Remove its `tabindex="0"` and the
    tile-level click and keydown handlers (`tools-grid.js:195-218`), so the link is the
    single focusable target. Those handlers' `.tool-enable-switch` bail-out goes with
    them.
  - The `tool-card` testid stays on the tile.
  - **HTML-sink baseline.** `tools-grid.js` already has three entries in the
    `test_ui_guards` baseline (`test_ui_guards.py:139-143`). Adding the anchor inside
    `tileHtml` keeps the assignment lines. If the list and tab renders are restructured,
    re-pin the baseline strings. If `providers-grid.js` is deleted, remove its baseline
    entry (`:123`), its `index.html` tag (`:74`) and its cache-busting entry.
- **The toggle never navigates.** Its click and change events stay on the toggle, with
  no bubbling to a navigation handler. Pinned by a test.
- **A toggle while a tool editor is open** (design review, issue 2, high).
  - `handleToolToggle` calls `populateToolGrid()` before and after the PUT
    (`admin.js:600, 621`). Today that is unreachable with an editor open; after this leg
    it is reachable.
  - With the `toolFormMode` guard removed, `populateToolGrid` re-renders
    **`.settings-list` only**, never the editor.
  - If the toggled tool is the open one, update the editor's enabled control **in
    place**, without re-mounting. If that is impractical, state "stale until reopened"
    in the flight log as an accepted variation.
  - Focus loss on the toggle after re-render already happens today. If cheap, restore
    focus to the same tool's toggle by name.
- **No list rebuild on refresh.** `selectTool` ends with `renderToolsPanel()` (`:559`),
  which would rebuild the list on every `_refresh` (`:~655`). Render only the item
  section there.
- **Category on deep link** (design review, issue 4). `activeCategory` is module-level
  (`tools-grid.js:62`) and is set only by the tab `onChange` (`:162`).
  - `renderToolsGrid` gains a `selectedName` option. When it is set, it assigns
    `activeCategory = TOOL_CATEGORIES[selectedName]` before the `App.tabs` init (`:152`).
  - An unknown tool keeps the current tab.
  - A deep link to `#settings/tools/web_search` therefore opens on its category.
- **Opening a tool.** `#settings/tools/{name}` keeps the tabs and tiles, and renders the
  tools editor **below them** in a `.settings-item` section.
  - The open tool's tile is marked selected: `aria-current="page"` on its link plus the
    selected wash.
  - The active category tab switches to the tool's category.
  - The editor header scrolls into view, and focus moves to its `h1` on open.
- **Breadcrumb.** "Settings / Built-in tools". The section segment is a link to
  `#settings/tools` (the DD2 refinement from leg 4a; testid `editor-breadcrumb-link`).
- **Back retired.** `back-tool-btn` is deleted, together with the `onBack` at
  `admin.js:455` and the handler at `tools-editor.js:412`.
- **Unsaved indicator.** As for providers.
- **Close.** There is no create. Cancel reverts in place (unchanged). Closing a tool
  means navigating to `#settings/tools`, through the Settings nav or another tool link.

**4. Tests.**
- **Migration** (about 12–15 files; design review counts):
  - `provider-card` ×14;
  - `back-provider-btn` ×16, 10 of them in `test_flow_provider_dirty_confirm.py`;
  - `back-tool-btn` ×7;
  - `tool-card` ×11;
  - `test_flow_admin_tools_grid.py:214-228` presses Enter on a focused tile, so rewrite
    it to focus the name link (and change the tile clicks at `:132` and `:222` too).

  Migrate the settings-lane files and the Settings halves of shared files to
  `_lists.py`:
  - drop `back-provider-btn` and `back-tool-btn`;
  - replace provider-grid tile clicks with table links;
  - replace tool-tile clicks with name links.
- **Allow-list.** Prune it; files leave only when fully clean.
- **New tests** in the settings lane:
  - **Table.** Its anatomy; the "Used by" counts against seeded agents; the row selected
    when open.
  - **Opening an item.** It renders below the table, with the table still visible, and
    the visibility check at 1440×900 passes.
  - **Add provider.** The create form appears below the table. Save-create keeps it in
    place (the URL becomes the id and the name is announced). Cancel-on-create returns
    focus to "Add provider".
  - **Delete.** Focus moves to the nearest row.
  - **Tool editor.** It opens below the list.
  - **Toggle isolation.** Clicking a tool's toggle changes enablement and does **not**
    navigate (the URL is unchanged and no editor opens). With a tool's editor open,
    toggling **another** tool refreshes the list and leaves the editor mounted, with its
    dirty state intact.
  - **Deep link to a non-default category.** The tool's tab is active and its tile is
    selected.
  - **Focus discipline.** A store notification or refresh while an item is open does not
    move focus.
  - **Breadcrumbs, no Back, and the unsaved indicator** for both editors.

**5. Docs.**
- `agents.md`: the Settings item-below-list pattern, the Providers table, and tool name
  links.
- `docs/ui-testid-registry.md`: retire `back-provider-btn` and `back-tool-btn`; note that
  `provider-card` moved to the name link.

## Acceptance Criteria

- [ ] **AC1 — Providers table.** At `#settings/providers` with 3 providers and seeded
  agents:
  - the intro and the table (Name · Type · Used by) render;
  - the counts match;
  - there is no Status column and no health banner;
  - the zero-provider empty state works.
- [ ] **AC2 — Provider item below.**
  - Clicking a name opens the editor below the table, and the table is still rendered
    above it.
  - At 1440×900 the selected row and the editor header are both inside the viewport, and
    focus is on the editor `h1`.
  - The breadcrumb reads "Settings / Providers", and there is no Back.
  - With the editor dirty, clicking another provider's link asks once (the router
    guard).
- [ ] **AC3 — Provider create, Cancel and delete.**
  - "Add provider" opens the create form below the table.
  - Save keeps the editor in place: the URL becomes `/{id}`, the announcement is
    "Settings — Providers — {name}", and the new row appears.
  - Cancel-on-create returns to the root with focus on "Add provider".
  - Delete focuses the nearest row, else "Add provider".
- [ ] **AC4 — Tools.**
  - The tool name is a link and opens the editor below the list.
  - The open tool's tile carries `aria-current="page"` on its link.
  - The toggle changes enablement without navigating.
  - The breadcrumb reads "Settings / Built-in tools", and there is no Back.
  - The editor header is scrolled into view and focused on open.
- [ ] **AC5 — Unsaved indicator.** For both editors, the indicator shows on any edit and
  clears on Save or Cancel. It is a stable node, never re-created.
- [ ] **AC6 — Tests and guard.**
  - The settings lane and every touched shared file are green.
  - The allow-list is pruned.
  - No `back-provider-btn` or `back-tool-btn` remains in the code or tests.
- [ ] **AC7 — Gates.**
  - `make lint` and `make test-unit`;
  - all five lanes, one at a time, with `THE_ONE_TEST_NETNS=1`;
  - the `test_ui_*` contracts in both engines;
  - the WebKitGTK probe at `#settings/providers/{id}` (`--root-selector '#main-content'`).

## Verification Steps

- AC1–AC5: the settings-lane files plus the new tests.
- AC6 and AC7: the gates.

## Implementation Guidance

1. **The Providers table**, then **the item section**:
   - change `renderProvidersPanel` to mount the table once per page, and the editor into
     the item section;
   - add the breadcrumb;
   - remove Back;
   - add the indicator;
   - wire Cancel, delete and focus.
2. **Tools.** Make the name a link and remove the tile-level click and tabindex. Mount
   the editor below the list, with selection, the breadcrumb, Back removed and the
   indicator.
3. **Tests.** Migrate the files, add the new tests, and prune the allow-list.
4. **Docs, then the gates and the probe.**

## Edge Cases

- **OAuth sign-in on an `anthropic-plan` provider** (`provider-editor.js:375-427`). With
  the editor now below a table that re-renders on store notifications, sign-in must not
  re-mount the editor. The table re-renders its body only.
- **A provider renamed while open.** The table row updates through the store. The
  editor's title updates on save, which is its existing behaviour.
- **A tool toggle while that tool's editor is open below.** The editor reflects the new
  enablement through its existing refresh path. Verify that nothing is clobbered.
- **Long provider names** in the table. The Name cell ellipsizes, with no overflow. The
  tile/badge overlap problem goes away with the table.
- **Keyboard.** Tab moves through the table's name links in order, then into the editor.
  The tool name links are in Tab order; the toggles remain separately focusable.

## Files Affected

- `areas/admin.js`, `areas/admin/providers-grid.js` (retired or replaced),
  `areas/admin/provider-editor.js`, `areas/admin/tools-grid.js`,
  `areas/admin/tools-editor.js`
- `index.html` and the cache-busting count (if a file is removed or added)
- `css/admin.css`
- `tests/browser/_lists.py`, the settings-lane files, the shared files (their Settings
  halves), `test_flow_settings_items.py` (new; add it to the settings lane),
  `tests/test_nav_helper.py` (allow-list)
- `docs/ui-testid-registry.md`, `the_one/agents.md`
- `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`

## Citation Audit

The Flight Director checked these against `508fc83`. Earlier legs shift lines, so
re-grep.

| Citation | Status |
|---|---|
| `admin.js:286-360` `renderProvidersPanel` (`:309-348` callbacks); `:405` `populateProviderGrid`; `:422-428` select and create; `:441` `renderToolsPanel`; `:514` `selectTool` | verified |
| `provider-editor.js:50-70` header and Back; `:375-427` OAuth | verified |
| `tools-editor.js:120-140` header and Back; `tools-grid.js:60-96` tile and toggle | verified |
| `providers-grid.js:23, 82` | verified |
| From the leg design review: `admin.js:304, 312, 337, 358, 397, 406, 413, 451, 455, 499, 559, 572, 581-621, 645, 684-693, 762`; `tools-grid.js:62, 112-218`; `provider-editor.js:109, 410, 732, 927`; `tools-editor.js:211, 412, 428`; `test_ui_guards.py:123, 139-143`; `index.html:74` | verified (leg design review) |

---

## Post-Completion

Status transitions, the flight-log update, checking off in the parent flight, and the
commit are Flight Control protocol, driven by the execution workflow. They are not
repeated here.
