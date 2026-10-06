# Leg: settings-nav-and-general (5a)

**Status**: completed
**Flight**: [List and Detail](../flight.md)

## Objective

Give Settings the grouped nav of links drawn in reference spec §8.1, split General into
its three pages, and put every Settings page under the §4 page header (DD6, DD13). The
leg covers six changes:

- **Nav.** `App.ui.navGroups` replaces the "Settings sections" button nav.
- **Section-nav retired.** `areas/layout/section-nav.js` loses its last caller and is
  deleted.
- **General split.** General becomes three pages, each with a route: Appearance, Prompts
  and Encryption.
- **Redirects.** `#settings/general` redirects to `#settings/appearance`, and so does the
  legacy `#admin/system`, directly.
- **Rail root.** The rail's Settings root becomes `#settings/appearance`.
- **Page headers.** Every Settings page renders a page header, with the board's labels.

## Context

- **Flight decisions:**
  - DD6: the nav, the groups and the General split. Read the whole "Owned entirely by leg
    5a" list.
  - DD13: A2 (260px), A3 (heading indent), A12 (`aria-current`).
  - DD1: `--settings-nav-w` has been live since leg 1. **This leg** applies
    `padding-top: 0` for settings.
- **Leg 1 shipped `App.ui.navGroups`.** The leg 1 flight-log entry has its API.
- **Settings code today** (`areas/admin.js`, 842 lines):
  - **Categories and nav.** `init` at `:139` builds the categories (`:141-157`). These
    are General, LLM Providers, Built-in Tools and Knowledge, plus Design Language in dev
    mode. The nav is rendered with `App.layout.renderSectionNav` at `:255-262` inside
    `<nav class="admin-section-nav">` (`:241`). `CATEGORY_ROUTE_SECTION` (`:248`) maps
    `knowledge` to `knowledge-indexing`.
  - **Page dispatch.** `renderContent` (`:270-283`) dispatches by category. General
    calls `App.admin.renderSystemPage` (`areas/admin/system-page.js`, 124 lines). That
    file has three blocks: Appearance (theme radiogroup), Base Prompt (read-only) and
    Encryption (the rotate flow).
  - **Serialize and hydrate.** `serializeState` and `hydrateState` (`:7-110`) handle
    `general` (and the legacy `system` → `general` mapping at `:60`), `providers…`,
    `tools…`, `knowledge` and `design-language`.
- **Router:**
  - `router.js` `SECTIONS` has a `general` row (`:71`).
  - `DESTINATIONS.settings.root` is `settings/general` (`:61`).
  - The legacy redirect table maps `admin/system` to `settings/general` (around
    `:12, :234`; re-grep).
  - `lastRoutes` is an **in-memory object** (`router.js:~301`). It is written only from
    an already-resolved route (`:~498`, `:~635`), and nothing persists it: `router.js`
    has no `sessionStorage` or `localStorage`, and `app.js:19-43` only reads
    `lastRoute()`. A stored `settings/general` therefore cannot occur, and there is no
    persisted-state case (design review, issue 1).
- **The Architect's enumerated `settings/general` references** (DD6) are:
  - `router.js:12,61,71,234`;
  - `tests/browser/_nav.py`, `tests/test_nav_helper.py`, `test_shell_rail.py`,
    `test_router_core.py`, `test_flow_hash_routing.py`, `test_nav_guard.py`,
    `test_flow_admin_navigation.py`, `test_flow_admin_rotate_flash.py`,
    `test_theme_cross_tab_sync.py`;
  - the specs `workbench-navigation.md` and `shell-navigation-smoke.md`.
  
  Re-grep at leg start: `settings/general`, `'general'`, and the "Settings sections"
  label.

- **Ground truth after legs 3–4b** (Flight Director, 2026-10-02):
  - **Prerequisite met.** Studio no longer calls `renderSectionNav` or
    `updateActiveSection`. The only callers left are `admin.js:~255` and `:~774`, plus
    the design-language sample at `surfaces-section.js:~71`. Leg 4b landed, so the "stop
    and report" condition in Outputs §4 does not apply.
  - **The retired-selector allow-list holds 15 files,** every remaining hit a Settings
    selector:
    - `test_flow_admin_knowledge_settings`
    - `test_flow_admin_navigation`
    - `test_flow_admin_openrouter`
    - `test_flow_admin_tools_editor`
    - `test_flow_admin_tools_grid`
    - `test_flow_hash_routing`
    - `test_flow_keyboard`
    - `test_flow_provider_dirty_confirm`
    - `test_flow_provider_grid`
    - `test_flow_provider_setup`
    - `test_router_announce`
    - `test_router_guard`
    - `test_router_items`
    - `test_shell_rail`
    - `test_visual_snapshots`

    A file leaves when its `section-nav-item` hits are gone and it has no `provider-card`,
    `tool-card`, `back-provider-btn` or `back-tool-btn` hits, which are leg 5b's.
  - **Leg 4b's `_lists.close_item` and `breadcrumb_link` helpers** exist. Settings
    breadcrumbs are leg 5b's, not this leg's.

## Inputs

- `static/js/router.js`
- `areas/admin.js`, `areas/admin/system-page.js`
- `areas/layout/section-nav.js` (to delete), `index.html` (its tag),
  `tests/test_index_asset_cache_busting.py`
- `css/admin.css`, `css/base.css`, `css/components.css` (section-nav CSS to remove)
- `docs/ui-control-inventory.md` (section-nav row), `docs/ui-testid-registry.md`
- the test and spec files in Context
- `tests/browser/_nav.py`, `tests/browser/_lists.py`

## Outputs

**1. The Settings nav.**
- **Factory.** `admin.js` builds one `App.ui.navGroups`:
  - `label: 'Settings'`, `heading: 'Settings'`;
  - testid `settings-nav`;
  - item testids `settings-nav-{id}`.
- **Groups and items.** Each item's `href` comes from `App.router.href`.

  | Group | Items |
  |---|---|
  | General | Appearance, Prompts, Encryption |
  | Models | Providers |
  | Defaults for agents | Built-in tools, Knowledge indexing |
  | Developer (dev mode only) | Design language |

- **`setSelected`** runs on every hydrate, including item routes. For example, at
  `#settings/providers/{id}` "Providers" stays selected.
- **The `<nav class="admin-section-nav">` wrapper is replaced.** The sidebar panel keeps
  its `.area-admin` class. `navGroups` mounts on a child, never on the panel itself.
- **CSS.** `#app-sidebar[data-destination="settings"] { padding-top: 0 }`, plus the
  §8.1 column padding (`14px 10px`) on the nav host.
- **No click handlers.** Items are plain links, so the router and `App.nav` guard them.
  `CATEGORY_ROUTE_SECTION` and `setCategory` go.

**2. General split into three pages.**
- **Router `SECTIONS`.**
  - Replace the `general` row with three rows: `appearance`, `prompts` and `encryption`,
    all `dest: 'settings'`, `area: 'admin'`, `create: false`.
  - Their area subs are `appearance`, `prompts` and `encryption`.
  - `SECTION_LABELS` (`router.js:350-354`) and `describeRoute` give "Appearance",
    "Prompts" and "Encryption". They replace the `general: 'General'` entry.
  - `tools: 'Tools'` becomes **"Built-in tools"**, to match the page header. Update the
    titles `test_router_announce.py` pins.
  - The other labels ("Providers", "Knowledge indexing", "Design language") already
    match the board.
- **Redirects.**
  - **Mechanism** (design review, issue 1, high). `resolve()` only redirects legacy
    `chat|studio|admin` heads (`router.js:233-238`). Once the `general` row is gone, a
    `settings/general` route falls to `unknownOrElement` at the SECTIONS lookup
    (`:272-276`). So:
    - Add an **explicit alias in `resolve`**: when `head === 'settings'` and
      `segs[1] === 'general'`, the route becomes `settings/appearance` with
      `redirected = true`.
    - Any trailing segments are **dropped**, so `#settings/general/x` goes to
      `#settings/appearance`.
    - `go()` and boot both resolve through `resolve` (`:33-34`), so the alias covers the
      cold-load and in-app cases.
  - **Legacy redirects.** Change the `admin/system` special case (`:237`) to
    `settings/appearance`. Add the same special case for `admin/general`, so both
    redirect **directly**, with no chained redirect.
  - **No persisted state.** The `lastRoutes` case is replaced by two checks:
    - `App.router.lastRoute('settings')` never returns `settings/general` after a visit
      to the redirect;
    - a rail click before any Settings visit lands on `settings/appearance`, which is
      `rootOf` (`router.js:~746`).
- **Root.** `DESTINATIONS.settings.root` becomes `settings/appearance`, so the rail's
  Settings href defaults there.
- **`admin.js`** (design review, issue 6). The `'general'` hard-codes are at:
  - `:8` (`serializeState` returns `'general'`);
  - the `:31` fallback;
  - `:42` and `:46` (the bare sub reset);
  - `:60` (the legacy `system` map);
  - `:94` (`validIds`);
  - `:159` (the `currentCategory` default);
  - `:271` and `:656-657` (`_refresh`), which both call `renderSystemPage`. Update both.

  Use a `GENERAL_SUBS = ['appearance', 'prompts', 'encryption']` helper. The legacy
  `general` and `system` subs map to `appearance`.
- **Selection.** `_setCategory` (`:758-775`) calls
  `App.layout.updateActiveSection(categoryListEl, …)` at `:774`. Replace it with
  `navGroups.setSelected(sectionId)`, and drop `categoryListEl` (`:158`, `:262`). On an
  item route, pass the **section** id, never the item id.
  `renderContent` dispatches:
  - `appearance` → `App.admin.renderAppearancePage`;
  - `prompts` → `renderPromptsPage`;
  - `encryption` → `renderEncryptionPage`.
- **`system-page.js`** (design review, issue 5). Split it into those three exported
  renderers, keeping each block's existing markup and testids: the theme radios, the
  base prompt view and `rotate-key-btn`.
  - Each block's helper takes `container` and shares no state with the others. Call each
    one **only on its own page**: `wireEncryptionRotate` dereferences the rotate button,
    and `mountThemeToggle` passes a mount element that may be null.
  - Remove `renderSystemPage`.
  - **Keep the theme radiogroup's accessible name.** Its
    `aria-labelledby="admin-appearance-heading"` (`system-page.js:18, 21, 63`) points at
    the in-page "Appearance" title this leg removes. Give the Appearance page's `h1`
    `id="admin-appearance-heading"`.

**3. Page headers (§4).** Every Settings page renders
`<div class="page-header"><h1 class="page-title">{Label}</h1>…</div>` with the board's
labels:
- Appearance, Prompts, Encryption;
- **Providers** (was "LLM Providers"). Its primary action becomes "Add provider" (was
  "New Provider", `providers-grid.js:38`); keep the testid `new-provider-btn`, and grep
  tests for the "New Provider" text;
- **Built-in tools** (was "Built-in Tools");
- **Knowledge indexing** (was "Knowledge");
- **Design language** (was "Design Language").

Every Settings page already renders `div.page-header > h1.page-title`:
- `system-page.js:13-14`;
- `providers-grid.js:33-34`;
- `tools-grid.js:108-135`, in three places;
- `knowledge-settings-page.js:32-33`;
- `design-language-page.js:18-19`.

So this output is mostly a label change plus the primary action (design review,
issue 4).

Rules:
- **No border-bottom and no breadcrumb** on page headers.
- **Scope the §4 geometry to Settings.** Use `.area-admin .page-header` and
  `.area-admin .admin-form` for `padding: 0 32px` and `max-width: 880px`.
  - `.page-header` is a shared rule (`components.css:987-1009`). Agents and Library
    headers use it (`studio.js:379`, `knowledge-section.js:311`, `mcp-servers-grid.js:43`,
    `connector-editor.js:222`), and leg 3 and leg 4 own those.
  - `.area-admin .admin-form` is `padding: 16px 20px 40px` today (`admin.css:18`).
- **One `h1` per page.** The in-page `.section-title` blocks are not `h1`s. Drop the ones
  that now repeat the page title (the "Appearance", "Base prompt" and "Encryption"
  titles each become their page's `h1`).
- **Providers and tools.** Their item editors stay as they are in this leg: grid,
  editor and Back are unchanged until 5b. Only their page header is added.

**4. Section-nav retired.**
- Delete `areas/layout/section-nav.js` once its last caller (Settings) is gone. Library's
  caller was removed in leg 4a. If 4a has not landed, **stop and report**.
- Remove:
  - its `index.html` tag (`:52`);
  - the cache-busting count in `tests/test_index_asset_cache_busting.py:62`, with a
    comment naming this leg;
  - its CSS (`components.css:1014-1060`, `.section-nav`, `.section-nav-item`);
  - its inventory row.
- **The design-language page** (design review, issue 2, high).
  `design-language/surfaces-section.js:66-71` builds a `.section-nav` sample with
  `<button>`s. **Remove that sample.** The `navGroups` demo in `ui-lists-section.js`
  replaces it, and the surfaces section may say so in one line.
- **Comments** that name section-nav: `dialog.js:5`, `chat.js:447`, `studio.css:3-4`,
  `provider-editor.js:671` and `admin.js:233-238`.
  - Rewrite those that describe live behaviour.
  - Historical notes may stay, as long as they do not use the code identifiers that
    AC5's grep looks for.
- The leg 1 guard bans `section-nav-item`, so files migrated here leave the allow-list.

**5. Tests and specs.**
- Update every `settings/general` reference in the Context list, plus these, which the
  design review found:
  - `test_flow_admin_knowledge_settings.py`, `test_flow_provider_dirty_confirm.py`,
    `test_flow_admin_tools_grid.py`;
  - `test_router_announce.py`;
  - `the_one/agents.md`.

  Leave the `tests/behavior/*/runs/` logs alone; they are history.
- **Label churn** (design review, issue 3): about 15 files. Most hits are
  `.section-nav-item` locators, which the leg 1 guard already makes this leg migrate.
  - `test_router_guard.py:325-335`
  - `test_flow_admin_knowledge_settings.py:37-61, 294-313, 309`
  - `test_router_core.py:601, 608`
  - `test_flow_hash_routing.py:40-56, 221-232`
  - `test_flow_provider_plan_signin.py:317`
  - `test_flow_admin_tools_editor.py:345, 360, 370`
  - `test_flow_admin_tools_grid.py:44, 71`
  - `test_flow_admin_navigation.py:43-111`
  - `test_flow_provider_setup.py:42`
  - `test_flow_keyboard.py:165-189`
  - `test_flow_cross_area_dirty_gate.py:54`
  - `test_flow_provider_grid.py`, `test_flow_provider_editor.py`
  - candidates: `test_flow_provider_dirty_confirm.py`, `test_flow_admin_openrouter.py`,
    `test_visual_snapshots.py`

  Locators of the form `.area-admin .section-nav-item … "General"` and
  `.section-nav[aria-label="Settings sections"]` move to `settings-nav-*` testids and the
  Appearance page.
- **`test_flow_keyboard.py:165-189`** tests roving tabindex and arrow keys on the old
  button nav. `navGroups` has no roving tabindex (by design, leg 1), so **rewrite the
  test**:
  - Tab reaches each nav link in group order;
  - Enter on a focused link navigates and moves `aria-current`.

  Keyboard coverage stays; the behaviour under test changes with the control.
- Migrate the Settings half of each shared allow-list file to `_lists.py` and
  `settings-nav-*` testids.
- **New tests**, in **`test_flow_admin_settings_nav.py`**. The name matches the settings
  lane's `test_flow_admin_*` glob (`scripts/run-tests.sh:72`), so `run-tests.sh` does not
  change.
  - **Nav structure.** The groups in order, with links and `aria-current`. The heading
    indent aligns with the item text (±1px). Item height is 28px ±1.
  - **Routing.** Each item navigates. The three General pages each render one block and
    one `h1`.
  - **Redirects:**
    - `#settings/general` → `#settings/appearance`, cold and in-app;
    - `#admin/system` and `#admin/general` → `#settings/appearance` directly, with no
      intermediate entry;
    - `#settings/general/x` → `#settings/appearance`;
    - `lastRoute('settings')` never returns `settings/general`;
    - the rail's first-use Settings href is `#settings/appearance`.
  - **Leave guard.** A dirty editor plus a nav-link click asks once. Use the provider
    editor, which still exists in 5a.
- Specs `workbench-navigation.md` and `shell-navigation-smoke.md`: update their Settings
  routes and labels. Only the text changes; leg 6 runs them.

**6. Docs.**
- `agents.md`: the Settings nav, the routes table (the three new pages and the
  redirects), the retired section-nav, and page headers.
- `CLAUDE.md`: the destination router line lists the Settings sections. Update it to
  `appearance|prompts|encryption|providers|tools|knowledge-indexing|design-language`.
- `docs/ui-testid-registry.md`: the new `settings-nav*` testids.

## Acceptance Criteria

- [ ] **AC1 — Nav.**
  - **Markup.** At `#settings/appearance`, the Settings column shows
    `<nav aria-label="Settings">` with the heading "Settings" and the four groups (three
    without dev mode), all with `<a>` items.
  - **Selection.** Exactly one item has `aria-current="page"`, and it follows navigation,
    including at `#settings/providers/{id}`.
  - **Geometry.** Items are 28px ±1, and the heading aligns with the item text (±1px).
  - **Width.** The column is 260px at 1440 and at 1024.
- [ ] **AC2 — General split.**
  - **Pages.** Appearance, Prompts and Encryption each render at their own route, with one
    `h1` and their existing controls and testids.
  - **Theme flip.** Light, Dark and Auto still work on Appearance.
  - **Rotate key.** The rotate-key flow still works on Encryption (its existing test).
- [ ] **AC3 — Redirects.**
  - `#settings/general` → `#settings/appearance` (cold and in-app).
  - `#admin/system` and `#admin/general` → `#settings/appearance`, with no chained
    intermediate.
  - `#settings/general/x` → `#settings/appearance`, with the suffix dropped.
  - `lastRoute('settings')` never returns `settings/general`.
  - The rail's Settings href is `#settings/appearance` on first use.
  - Each case is tested.
- [ ] **AC4 — Page headers.** Every Settings page has a page header with the board's label
  and no second `h1`. "Add provider" is the Providers action (`new-provider-btn`).
- [ ] **AC5 — Section-nav gone.**
  - `section-nav.js` is deleted, along with its tag, CSS and inventory row.
  - This code-reference grep returns nothing:
    `grep -rnE "renderSectionNav|updateActiveSection|section-nav-item|class=\"section-nav|\.section-nav\b" the_one/interfaces/web/static/`.
  - Comments are covered by the Outputs §4 rule, not by this grep.
  - The design-language page renders with no section-nav sample.
  - The guard's allow-list no longer lists files fully migrated off `section-nav-item`.
- [ ] **AC6 — Tests and specs.**
  - Every enumerated `settings/general` reference is updated. A grep shows no
    `settings/general` outside redirect tests and the redirect table.
  - The settings lane and all touched shared files are green.
- [ ] **AC7 — Gates.**
  - `make lint` and `make test-unit`;
  - all five lanes, one at a time, with `THE_ONE_TEST_NETNS=1`;
  - the `test_ui_*` contracts in both engines;
  - the WebKitGTK probe at `#settings/appearance`, with `--root-selector '#app-sidebar'`
    and again with `'#main-content'`.

## Verification Steps

- AC1–AC4: the settings-lane files and the new nav test.
- AC5 and AC6: the greps and the guard.
- AC7: the gates.

## Implementation Guidance

1. **Router.** Add the rows, the redirects and the root; then the round-trip and redirect
   tests, including `lastRoutes`.
2. **`admin.js`.** Update serialize, hydrate and dispatch. Split `system-page.js`.
3. **The `navGroups` nav**, then delete the section-nav call and `setCategory`.
4. **Page headers and labels.**
5. **Delete section-nav.** Remove its tag, cache-busting entry, CSS and inventory row.
6. **Tests and specs.** Migrate the references and labels, add the new test, and prune
   the allow-list.
7. **Docs, then the gates and the probe.**

## Edge Cases

- **`#settings` bare.** It goes to the root, `#settings/appearance`, through the existing
  bare-destination rule.
- **Dev mode off.** The Developer group is absent, and `#settings/design-language`
  behaves as it does today (redirect or not found). Keep the current behaviour.
- **Theme sync across tabs** (`test_theme_cross_tab_sync.py`). It navigates to the theme
  control, so update it to `#settings/appearance`.
- **A dirty provider editor, then a click on "Appearance".** The router guard asks once.
  This is the Flight 2 behaviour through links; verify it.
- **The `admin-section-nav` class** has no CSS selector (design review, issue 7). Grep
  tests for it.
- **The sidebar panel scrolls.** `.sidebar-panel` is `overflow: hidden`
  (`base.css:53`), so the `navGroups` host must be its own scroll container
  (`overflow-y: auto; min-height: 0`), or the Developer group clips at 1024×768. Put the
  `data-destination="settings"` padding rule after `base.css:52`.

## Files Affected

- `static/js/router.js`
- `areas/admin.js`, `areas/admin/system-page.js`
- `areas/layout/section-nav.js` (deleted), `index.html`,
  `tests/test_index_asset_cache_busting.py`
- `css/admin.css`, `css/base.css`, `css/components.css`
- `tests/browser/_nav.py` and `tests/test_nav_helper.py`
- the enumerated test files and the label-churn list
- new `tests/browser/test_flow_admin_settings_nav.py` (in the settings lane through its
  existing glob)
- `areas/admin/design-language/surfaces-section.js` (the section-nav sample removed)
- `areas/admin/providers-grid.js`, `tools-grid.js`, `knowledge-settings-page.js`,
  `design-language-page.js` (labels and the primary action)
- `tests/behavior/workbench-navigation.md`, `tests/behavior/shell-navigation-smoke.md`
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`,
  `CLAUDE.md`
- `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`

## Citation Audit

The Flight Director checked these against `508fc83`. Legs 2–4 may shift lines, so
re-grep.

| Citation | Status |
|---|---|
| `admin.js:7-110` serialize and hydrate (`:60` legacy `system`); `:139-157` categories; `:241` nav wrapper; `:248` `CATEGORY_ROUTE_SECTION`; `:255-262` `renderSectionNav`; `:270-283` `renderContent` | verified |
| `system-page.js` 124 lines, three blocks | verified |
| `router.js:61` settings root; `:71` general row; `:12, :234` `settings/general` references | verified (Architect) |
| From the leg design review: `router.js:33-34, 233-238, 272-276, ~301, 350-354, ~746`; `admin.js:8, 31, 42-46, 60, 94, 158-159, 262, 271, 656-657, 758-775`; `system-page.js:13-14, 18, 21, 63`; `surfaces-section.js:66-71`; `components.css:987-1009, 1014-1060`; `admin.css:18`; `base.css:52-53`; `index.html:52`; `test_index_asset_cache_busting.py:62`; `run-tests.sh:72` | verified (leg design review; legs 3–4 will shift lines, so re-grep) |

---

## Post-Completion

Status transitions, the flight-log update, checking off in the parent flight, and the
commit are Flight Control protocol, driven by the execution workflow. They are not
repeated here.
