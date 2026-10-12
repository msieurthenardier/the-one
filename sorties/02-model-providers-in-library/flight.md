# Sortie: Model providers in Library

**Status**: landed

## Charter

### Outcome
Model providers live in Library as a fourth group, "Model providers", listed and edited like knowledge bases, MCP servers and connectors, and Settings no longer has a Models section.

### Why Now
Operator request (2026-10-11): providers are things agents use, like the other Library items, not app-wide preferences.

### Success Criteria
- [ ] Library's list shows a "Model providers" group, first (above Knowledge bases), whose rows (type badge, "used by" agents) open the provider editor in the detail pane at `#library/providers[/~new|/{id}]`.
- [ ] `#library` is Library's own route, showing the start page with a Model providers card first; the start page, breadcrumbs, router and docs no longer present it as the knowledge section; the Add menu and the Jump to palette create and reach providers through the Library routes.
- [ ] The Settings nav has no Models group, and `#settings/providers…` is no longer a route (old links are dropped, not redirected).
- [ ] Unit tests and every browser lane pass, with the provider tests reaching providers through the Library routes and helpers; no `settings/providers` route remains in tests.

### Constraints
- No backend or API change: `/api/providers`, the `__MASKED__` key contract and the `anthropic-plan` OAuth sign-in work unchanged from the new location.
- The provider editor's behaviour (Test, models list, OAuth, leave guard, focus after an action) is preserved; only its location and breadcrumb ("Library / Model providers") change.
- Route slug is `providers` (operator-confirmed); the visible label is "Model providers".
- Model providers come first in Library (operator, 2026-10-11: "the most fundamental part"): first group in the list, and first in the Add menu and on the start page.

---

## Pre-Flight

### Objective
Make Library the home of model providers and give Library a real front door, in two product states.
- **Leg 1, additive:** `#library` becomes Library's own route, rendering the start page, and the bare section URLs become silent aliases for it. Providers appear as Library's first group, "Model providers", with the provider editor in the detail pane at `#library/providers[/~new|/{id}]`. They are reachable from the Add menu, the start page and Jump to. Settings still hosts providers too, and the gate is green.
- **Leg 2, subtractive:** providers leave Settings: the Models group, `#settings/providers…` (no redirect) and every admin-area provider branch. The interim Settings host path in the editor is deleted, the old provider tests are migrated to the Library routes, and their testids are retired and fenced.

### Open Questions
- [x] Library group label and route slug → "Model providers", `providers` (charter; operator, 2026-10-11)
- [x] Group order → Model providers first everywhere (charter; operator)
- [x] Presentation → list rows; the Settings tile grid retires (charter; operator)
- [x] Old `#settings/providers` links → dropped, no redirect (charter; operator)
- [x] Library root → a real `#library` route, with bare section URLs redirecting to it (DD1, DD2; operator)
- [x] Code home → new studio section module (DD4; operator)
- [x] Test lane → a new `providers` lane (DD9; operator)
- [x] HAT → none; the code review plus the unit and browser gates are acceptance (operator)
- [x] Leg shape → two legs, additive then subtractive (operator, after Architect cycle 1)
- [x] Does the `system` lane alias include providers? → yes: `system` = `settings` + `providers`, since the pre-M25 System area held providers (DD9)
- [x] After Cancel or Delete lands on `#library`, scroll to the closed item's group? → no separate scroll. The DD8 focus rule (the neighbour row, or the group's first row) brings the row into view, and the "scroll to group at a section root" branch (`studio.js` ~l.731-742) is removed (DD2)
- [x] Provider tile contrast audit (`test_design_tokens_a11y.py` ~l.963-984) → retired with the tiles in leg 2. The list-row type badge is `App.ui.badge`; if its provider-type kinds are not already in the badge contrast audit, leg 1 adds them (DD5)

### Design Decisions

**DD1 — `#library` is a real route, and studio's pseudo-section `library` represents it.**
- **Router:** the Library destination's `root` becomes `library`. In `resolve()`, a bare `library` is handled like `agents`, as a route of its own: it resolves to `{route:'library', sub:'library'}`, not redirected. The generic "bare destination redirects to its root section" branch (`router.js` ~l.334-338) then applies only to Settings, and cannot recurse. `areaSubToRoute('studio', 'library')` → `library`. `describeRoute` speaks "Library" with no section. `lastRoute('library')` defaults to `library`; its consumer is the rail (`app.js` ~l.35, 61).
- **Studio:** at the root, `_activeSection === 'library'`, a pseudo-section. Every helper that assumes one of the group sections gets an explicit branch:
  - `hydrateState`: sub `library` → `closeOpenItem()` then `setActiveSection('library')`, like every root sub today (~l.171-173, 196-198, 207-209; contract at ~l.135-138). This bumps `editorGen`, so an in-flight save that lands after a breadcrumb go fails its generation check and cannot sync the URL back to the item (~l.1535, `router.js:728`). It must not fall to the `'agents'` default at ~l.308-311.
  - `serializeState` returns `library` when nothing is open in any group.
  - `isLibrarySection('library')` is true.
  - `atLibraryRoot()` is true when `_activeSection === 'library'`. Its old per-section meaning ("nothing open or pending in this section") is audited at leg design. Any remaining caller, such as a pending deep link, gets a separately named helper rather than an overloaded one.
  - `librarySelection()` → none.
  - `renderLibraryEmpty` renders the start page with no group argument; the early return at ~l.944-945 goes.
  - `setActiveSection`'s dispatch (~l.1847-1855) renders the start page for `library`.
  - Studio activate's `isLibrarySection` check (~l.3992) includes `library`.
  - `editorOpen` (~l.4012-4017) is false at `library`.
- **`focusClosedItem_` (~l.1765):** its guard `_activeSection !== closing.section` becomes "still at the Library root (`_activeSection === 'library'`) and no item open". `closingItem_` already records the group (~l.1754-1757), so the DD8 focus rule (the closed item's row, or the nearest visible) is unchanged.
- Rationale: the root is a page in its own right (M25 F6 L4c's start page), not a view of one section. Today's `root: 'library/knowledge'` is what led planning (and readers of `agents.md:2264`) to describe it as the knowledge section.
- Trade-off: one more pseudo-section in studio's state, and one more special case in `resolve()`.

**DD2 — Bare section URLs are aliases for `#library`, and nothing produces them.**
- `#library/knowledge`, `#library/mcp`, `#library/connectors` and `#library/providers`, with no id and no `~new`, resolve to `library` with `redirected: true`. This is the `settings/general` → `settings/appearance` mechanism: a single `replaceState`, and the alias is never written.
- Every producer of a bare section URL or sub changes to `library`:
  - the breadcrumb (DD3);
  - the create-form Cancel;
  - the Delete callbacks' `go(... replace)`;
  - `closeOpenItem`'s root;
  - the agent-editor tab links `mcps-tab.js` ~l.62 and `knowledge-tab.js` ~l.93, which go to `#library`, or to the attached item where they name one;
  - studio's heal and poll syncs `App.router.sync('studio', 'knowledge'|'mcp-sources'|'connectors')` (~l.1133, 1211, 1639, 1652) become `setActiveSection('library')`, whose `writeUrl_` syncs through `serializeState` (~l.1856, 1882-1886). A bare `sync` writes the URL without hydrating (`router.js:722-755`), which would leave `_activeSection` naming a section while the URL says `#library`. The providers module heals the same way, through `ctx.showRoot()` (DD4).
- A unit static check pins that no `static/js` file produces a bare Library section, either as an `href({destination:'library', section:X})` without an id or create, or as a bare-section `sync('studio', …)` sub.
- The "scroll to group at a section root" branch (~l.731-742) is removed, since every root is one page.
- **The browser-test resolver:** `tests/browser/_nav.py::canonical` folds `library` → `library` (it currently folds to `library/knowledge`, ~l.159-160) and bare `library/{section}` → `library`. The router parity corpus (`test_router_core.py` ~l.248-256, 271) is updated. The roughly 59 `expect_route(..., "library/<section>")` asserts in about 13 files are **migrated to `"library"`**, so none passes vacuously through the fold. `test_flow_studio_navigation.py` ~l.118's raw-hash compare is updated.
- Rationale: keeps old bookmarks working while making `#library` the only root.
- Trade-off: a section URL no longer means "this section's root". No surface depended on that, since every root shows the same page.

**DD3 — Item breadcrumb: "Library" is the link.**
- Every Library editor's breadcrumb becomes `Library / {Group}`, with "Library" the `editor-breadcrumb-link` to `#library` and the group name plain text. This covers the knowledge-base detail and its `~new` form, MCP, connectors and providers.
- Studio's click routing (a guarded go) and DD1's `focusClosedItem_` give the same focus behaviour as today.
- The testid keeps its meaning, "the header's link to its root"; `docs/ui-testid-registry.md:141` is rewritten.

**DD4 — Provider code moves to the studio area through a section module with a defined interface.**
- **The move (leg 1):** `git mv areas/admin/provider-editor.js` → `areas/studio/provider-editor.js`, and `git mv areas/admin/provider-models.js` → `areas/studio/provider-models.js`.
  - Namespaces: `App.admin.renderProviderEditor`, `renderProviderModels` and `renderCapabilityChips` become `App.studio.*`, and every caller follows: admin's interim host, `studio.js` ~l.3107, and the editor's own internal `renderProviderModels` calls (~l.165, 168, 921-933).
  - The `index.html` script tags move into the studio block, before `studio.js` (~l.72-84), with `providers-section.js` beside them.
  - These unit pins follow the paths: `test_store_static.py` ~l.237 and ~l.315, `test_ui_guards.py`'s sink baseline (~l.107-113), and `test_admin_reasoning_effort_field.py:25`.
- **Interim host option (leg 1, removed in leg 2):** `renderProviderEditor(container, provider, providerTypes, callbacks)` (`provider-editor.js:53`) gains `callbacks.host: 'library' | 'settings'`.
  - `'library'` gives the DD7 chrome.
  - `'settings'` keeps today's `h2`, the "Settings / Providers" breadcrumb and admin's reveal.
  - Leg 2 deletes the option and the `'settings'` path.
- **New `areas/studio/providers-section.js`:** a factory `App.studio.providersSection.create(ctx)`, called once in studio's init, which returns a handle. It plugs into the existing `PENDING_KINDS` shape (`studio.js` ~l.1625-1656).
  - It does not port admin's `fetchProvidersNow`/`_tryConsumePendingProvider` path. Pending ids use studio's `resolvePendingLibraryItem`, and the list uses studio's Library cache.
  - It owns `PROVIDER_TYPES`/`fetchProviderTypes` and `TYPE_DEFAULTS`, copied from admin in leg 1, with the admin copies deleted in leg 2.
- **`ctx`, studio → module:**
  - `host()` (`sectionContentEl`);
  - `getDirty()`/`setDirty(b)`;
  - `editorGen()`/`bumpEditorGen()`;
  - `isActive()` (`_activeSection === 'providers'`);
  - `discardOpen()`;
  - `reloadLibrary(name)`;
  - `syncLibrarySelection(force)`;
  - `libraryRowIndex(id)`;
  - `focusLibraryRowNear(idx)`;
  - `focusLibraryGroupStart(groupId)`;
  - `cache()` (the providers array);
  - `showRoot()` (`setActiveSection('library')`: the start page plus the URL heal).
- **Handle, module → studio:**
  - `formMode()` (`'add'|'edit'|null`);
  - `editingId()`;
  - `pendingMode()`, `pendingId()`, `setPending(mode, id)`;
  - `consume(allowCache) → bool` (the `PENDING_KINDS` consumer's real signature, `studio.js` ~l.1453, 1588, 1631-1655);
  - `heal()`;
  - `render()`;
  - `reset()` (for `closeOpenItem`, `discardOpen_`, section cleanup and hydrateState's same-section close path, the `_closeConnectorForm` equivalent at ~l.276-281). It also clears the editor's module-level `pendingAutoSignInId` (~l.344), so an abandoned create-to-edit hand-off cannot fire later;
  - `selectionId()`;
  - `createOpen()`;
  - `editorOpen()`;
  - `focusCreate()`;
  - `serialize()` (the `providers[/new|/{id}]` sub, or null at no item).
- **Studio's side:** `studio.js` adds the `LIBRARY_GROUPS` row and one-line delegates to the handle in the helpers that hard-code sections. `libraryItem`'s meta gets an explicit `providers` → `App.usage.providerAgents` branch; today any group that is not knowledge or MCP falls through to `connectorAgents` (~l.664-666). It also adds an ungated `providers` store subscription that feeds the Library cache and calls `renderLibraryList()` and the pending consume. The Library cache becomes the single studio copy of providers. The Agents list's `self._allProviders` (gated subscription ~l.2305-2314) reads it, or, if the gating must stay, the leg documents why two copies exist.
- **The shared `dirty` flag** is reused through `ctx`. The provider create path checks `editorGen()` unchanged and the route still `library/providers/~new` before clearing `dirty` and syncing (the save-create staleness guard, `agents.md:2050`).
- **Divert:** if the module needs studio state beyond `ctx`, stop and re-plan the interface (Adaptation Criteria).
- **Leg 2:** `admin.js` loses every provider branch: the category, the scaffold's provider half, the subscriptions, `openItemLink`'s provider case, `fetchProvidersNow`, `revealItem`'s provider use and the pending state. `areas/admin/providers-list.js` is deleted.
- Rationale: the operator's choice. Provider code belongs to the destination that shows it, and `studio.js` does not absorb about 600 lines (the M25 F3 debrief).

**DD5 — List rows, group order and fetch policy.**
- `LIBRARY_GROUPS` gains a first row: `{id:'providers', section:'providers', route:'providers', collection:'providers', label:'Model providers', emptyText:'No model providers yet.', failText:'Couldn’t load model providers.', icon:<an existing icon key>, testid:'provider-card', prefix:'provider:'}`.
- The order is Model providers, Knowledge bases, MCP servers, Connectors, in the list, the Add menu and the start page.
- A row shows the name, a type badge (`badges:[{text, kind}]` through `App.ui.badge`; the `KNOWN_BADGE_TYPES` fallback from `providers-list.js` ~l.44, copied in leg 1), and "used by" meta from `App.usage.providerAgents`. A row is an `<a href="#library/providers/{id}">`.
- If the badge's provider-type kinds are not already in the contrast audit, leg 1 adds them.
- **Fetch policy:** pane creation and studio activate force-get four collections (`studio.js` ~l.513-517, 758-778). This is an intended change to pinned contracts:
  - `test_store.py` ~l.362-369 (Agents ↔ Library made 0 `/api/providers` reads, now 1);
  - `test_store_library.py` ~l.30 (the collection set);
  - `agents.md`'s request-count table.

**DD6 — Add menu, start page, Jump to, labels and copy.**
- **Add menu:** a first item "Model provider", testid `library-add-provider`, going to `#library/providers/~new`.
- **Start page:**
  - The page testid becomes `library-start`.
  - The card Add buttons become `library-start-{group}-add`, with `library-start-providers-add` first. The whole `library-empty-` prefix retires (DD8).
  - The Model providers card's copy says what a model provider is: the connection an agent uses to reach a model.
- **Router labels:** Library labels move to a destination-keyed table, `LIBRARY_LABELS`, consulted by `describeRoute` for `library/*`. Adding `providers` to the route-keyed `SECTION_LABELS` would win over the still-live Settings "Providers" label (lazy merge, existing key wins, `router.js` ~l.425-442) and break `test_router_announce.py` ~l.83-84, 285, 292-293 in leg 1. Library's root announces "Library". `test_router_announce.py` ~l.75-76 and 205-206 ("Library — Knowledge" root) are updated. `ITEM_COLLECTIONS` gains `'library/providers': {collection:'providers', noun:'Model provider'}`. Leg 2 removes the `settings/providers` entry.
- **Jump to:**
  - Providers become Library candidates: `COLLECTIONS` (`jump-to.js` ~l.61) gains `providers` and `LIBRARY` (~l.63-66) a row (`where: 'Library · Model provider'`), placed before knowledge bases in board order. Their `data-kind` is named in the registry's `jump-to-result` row.
  - This adds a `/api/providers` read on palette open and shifts the empty-query fill. `test_flow_jump_to.py` ~l.54 and 659-661 are updated deliberately.
  - The `providers` special case in `jump-to.js` (~l.122) is removed in leg 2, with the Settings row.
- **Copy:**
  - The chat guidance in `chat-pane.js` ~l.79-89 becomes "Add a model provider in [Library]", linking `#library/providers/~new`.
  - The plain-text copies in `chat.js` ~l.1446 and `session-state.js` ~l.57 say "Library".
  - `general-tab.js` ~l.60's "No provider — configure in Admin" points at Library.
- Rationale: a provider is reachable everywhere the other Library types are, and the user-facing noun matches the group label.

**DD7 — The provider editor in Library adopts Library editor chrome.**
- The title is the pane's only `h1` (DD11, `studio.js` ~l.930-935).
- The breadcrumb is `Library / Model providers` (DD3).
- There is no reveal-on-open: focus stays on the row, as in the other Library editors.
- A click on the open row goes through the router (admin's `openItemLink` short-circuit is not carried over).
- **The create-to-edit re-mount stays.** The anthropic-plan hand-off depends on `onCreateSuccess` running before `onSaveSuccess` (`provider-editor.js` ~l.846-850) and the re-mount rendering the created row in edit mode, which consumes `pendingAutoSignInId` (~l.665-668). Leg 1 adds a Library-route browser test that pins it.
- `App.focusAfter` begin and restore are kept for Save, Cancel and Test.
- **Flashes:** a flash across a re-mount (e.g. "Provider created") is **dropped**, as in the connector convention (`renderConnectorsSection` clears the host on the create re-mount, ~l.1487). Tests asserting one are adjusted.
- **CSS:** the provider editor and model-list rules in `admin.css` (~l.137-289) are copied to `studio.css` re-scoped to `.area-studio` in leg 1. Leg 2 deletes the admin copies, except those still used outside providers:
  - `.cap-chip*` (~l.243-245) is used by the agent editor and pinned by `test_design_tokens_a11y.py` ~l.411-430. It moves to an unscoped shared location, and that pin follows it.
  - The provider tile rules and their audit (~l.963-984) retire in leg 2.
- **Naming debt:** the `admin-pf-*` class names move into `studio.css` as they are, and are accepted naming debt (renaming them would churn the editor and its tests for no user-visible gain). This is recorded for the debrief.
- **Asset count:** `index.html` gains `providers-section.js` in leg 1 (88) and loses `providers-list.js` in leg 2 (87). `test_index_asset_cache_busting.py` ~l.83 is updated in each leg, with a comment history entry. No new CSS file.

**DD8 — Settings loses providers; old links drop; retired ids are fenced.**
- **Leg 2:**
  - `settings-pages.js` loses the `providers` row, and the Settings "Models" group disappears with it. `test_settings_pages_static.py` drops to seven rows.
  - `router.js` loses the Settings `providers` row.
  - `#settings/providers[/…]` and `#admin/providers[/…]` then resolve as unknown routes, by the operator's decision. The router tests pinning the old `#admin/providers` redirect (`test_router_core.py` ~l.264-266, 333-337) are re-pinned to unknown.
  - `#studio/providers[/…]` will map to `library/providers` through `areaSubToRoute`. This is accepted as harmless.
- **Retired testids** (per `test_retired_selectors_cover_the_registry_retired_table`, `test_nav_helper.py` ~l.578-582, which fails when a retired id starts with a prefix that is still live):
  - **Leg 1:** the prefix `library-empty-` goes into `RETIRED_SELECTORS` and the registry's Retired table, since every `library-empty-*` id is renamed (DD6).
  - **Leg 2:** `new-provider-btn`, `providers-empty` (which covers `providers-empty-add`, `providers-list.js` ~l.172) and `back-provider-btn` (already retired) go into `RETIRED_SELECTORS` and the Retired table.
  - **`settings-nav-providers`** is fenced in `RETIRED_SELECTORS` only and left out of the Retired table, because `settings-nav-` stays live. The pin needs only the table to be a subset of the fenced ids.
  - The Developer runs the pin after each addition.

**DD9 — A `providers` browser lane (leg 1).**
- `scripts/run-tests.sh` gains a ninth canonical lane, `providers`. `providers_pat` is `test_flow_provider_*` (the six existing files, plus the new Library-route tests and leg 2's split-out `test_flow_provider_items.py`, the provider half of `test_flow_settings_items.py`).
- Plumbing:
  - `settings_pat` drops `test_flow_provider_*`;
  - `shared`'s `_assigned` complement list (~l.218-220) includes `providers_pat`;
  - `LANE_LIST` (~l.54) and `CANON_LANES` (~l.55);
  - `BUDGET`: providers starts at 300 s, then is set from the leg's `--parallel 3` measurement plus about 25%, and `settings` is re-measured in leg 2;
  - the `case` branch;
  - the alias `system` = `settings` + `providers`;
  - `--help`;
  - the "eight lanes" wording in `ci/tasks/browser.yml` ~l.10 and `ci/README.md` ~l.35;
  - the `LANES` tuple in `tests/test_run_tests_lanes.py` ~l.24 (nine lanes, pairwise disjoint, complete union);
  - `CLAUDE.md`'s lane list and budget table.
- **Files outside `test_flow_provider_*`:**
  - Provider-only scenarios move to `providers`: `test_flow_admin_openrouter.py` becomes `test_flow_provider_openrouter.py`, and the provider half of `test_flow_settings_items.py` becomes `test_flow_provider_items.py`.
  - Files that test Settings itself and only touch providers incidentally stay in `settings`: `test_flow_admin_settings_nav.py`, `test_flow_settings_visible_fixes.py`, `test_flow_settings_focus_after.py`. Their provider references are migrated in leg 2, or removed where they asserted the Models group.
  - The renames happen in leg 2, with the migration.
- Rationale: library runs at 233/300 s (78%), and its explicit list would need re-budgeting. `settings` would otherwise hold Library tests.

**DD10 — Test reachability contract.** Tests reach providers through `library/providers[/~new|/{id}]` via `_nav`, and rows through `_lists`.
- **Leg 1:**
  - `LISTS["library/providers"]` uses `provider-card` scoped under `[data-testid="library-list"]`, with the Library row matching (`filter(has=name)`, badge text excluded). `LISTS["settings/providers"]` is scoped under `.area-admin` for the interim. Today `LISTS` selectors are page-global (`_lists.py` ~l.125-133), and `provider-card` exists on both surfaces in leg 1. The registry's `provider-card` row says "studio, admin" until leg 2.
  - `LIBRARY_KINDS` gains `providers`, so `library_add(page, "providers")` and `expect_selected(page, "library/providers", name)` work.
  - `_lists.library_start(page)` replaces `library_empty_state(page, kind)`, and every caller migrates (about 11).
  - `library_add`'s kind map (~l.216-218) gains `providers` explicitly and raises on an unknown kind instead of falling back to the connector.
  - `tests/test_nav_helper.py` ~l.77 (`canonical("library")`) and `DD2_ROWS` (~l.34-43) are updated.
- **Leg 2:**
  - `LISTS["settings/providers"]`, `providers_list`, the provider use of `settings_item` and `SETTINGS_PAGE_TITLES["providers"]` retire.
  - `tests/test_nav_helper.py` gains a guard that fails on any `settings/providers` route literal in `tests/browser/`, including `test_visual_snapshots.py` (pixel-only, no lane), which is migrated rather than exempted.
  - `_nav._from_legacy` (~l.236-241) gains a providers branch if `#studio/providers` is pinned in the parity corpus.
  - `test_store_static.py` ~l.344's pin of admin's provider-save `sync` moves to the section module's `sync('studio', 'providers/' + id, {name})`.
- **Behavior specs** naming these routes or testids are re-authored deliberately in the leg that changes them. Leg 1: the `#library/{section}` roots and `library-empty-*` (e.g. `list-and-detail`, `workbench-navigation`). Leg 2: `#settings/providers`, `#admin/providers` and the Settings page list (`shell-navigation-smoke` steps 8-9, `anthropic-plan-signin`, `system-provider-config` and others found by grep).

**DD11 — The leg-1 interim: both hosts are editable, tests never cross them.**
- Between the legs, providers are editable in both Settings (admin, `host: 'settings'`) and Library (studio). The interim never ships: the flight merges as one PR after leg 2, and no release is cut between the legs.
- Both editors mounted in one page would duplicate element ids (`pf-*`, `provider-editor.js` ~l.188-215) and testids, because `mountArea` only hides panels (`app.js` ~l.149-174). The leg-1 constraint is therefore that **no test opens a provider editor in both hosts in one page**: the old tests use Settings, and the new tests use Library.
- `LISTS` scoping (DD10) keeps the row helpers from cross-matching.
- The shared `App.store` `providers` collection, and both hosts' invalidations, are already the cross-area contract. Each host keeps its own `App.nav` dirty source, which is the existing per-area model.
- Rationale: making Settings read-only, or a pointer to Library, in leg 1 would force the old provider tests to migrate in leg 1, which collapses the additive/subtractive split.
- Trade-off: a dev instance between legs can show both editors. That is acceptable, because it is never released.

### Citation Audit

Verified against the working tree at `30195e6` (Flight Director plus Architect cycle 1 spot-checks):

| Citation | Status |
|---|---|
| `router.js` DESTINATIONS l.72 — Library `root: 'library/knowledge'` | verified |
| `router.js::resolve` l.334-338 — bare destination resolves `dest.root`, `redirected = true` | verified |
| `router.js` SECTIONS l.81-97 — Library rows `create:true`; Settings `providers` row l.93 | verified |
| `router.js::sectionLabel` l.425-442 — Library `SECTION_LABELS`; Settings labels merged lazily, existing key wins | verified |
| `router.js` ITEM_COLLECTIONS l.449-454 | verified |
| `router.js::areaSubToRoute` l.244-253 and legacy branch l.296-321 | verified |
| `studio.js` LIBRARY_GROUPS l.518-531; l.939/961/968 testids; `serializeState` l.48-79 bare-section returns | verified |
| `studio.js` `hydrateState` unknown sub → `'agents'` ~l.308-311; `renderLibraryEmpty` early return ~l.944-945; `focusClosedItem_` guard ~l.1765; `closingItem_` records group ~l.1754-1757 | verified (Architect) |
| `studio.js` bare-section `sync` calls ~l.1133, 1211, 1639, 1652; `PENDING_KINDS` ~l.1625-1656 | verified (Architect) |
| `provider-editor.js` h2 l.64; breadcrumb l.130-147; `pendingAutoSignInId` l.344 (set l.522, consumed l.665); `onCreateSuccess` before `onSaveSuccess` l.846-850 | verified (Architect) |
| `admin.js` provider panel l.433-~682; l.1037-1208; `revealItem` l.418-427; `openItemLink` l.938 | verified (Architect) |
| `chat-pane.js::guidance` l.77-92; `chat.js` l.1446; `session-state.js` l.57 | verified |
| `tests/test_nav_helper.py` l.383 `RETIRED_EXACT`; l.578-582 Retired-table coverage pin | verified (Architect) |
| `tests/browser/_nav.py::canonical` l.159-160 folds `library` → `library/knowledge` | verified (Architect) |
| `scripts/run-tests.sh` l.54-55, 173, 189, 218-220 | verified (Architect) |
| `test_store.py` l.362-369; `test_store_library.py` l.30; `test_index_asset_cache_busting.py` l.83 | verified (Architect) |

### Prerequisites
- [x] Charter agreed (2026-10-11).
- [x] `main` clean at `30195e6`.
- [ ] Each leg's Developer re-checks the cited line numbers at leg design (they drift).
- [ ] Every browser run uses `THE_ONE_TEST_NETNS=1` (this WSL host) and `THE_ONE_REQUIRE_WEBKIT=1` (the contracts lane covers the start page and list rows).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified (per-leg re-checks remain in Prerequisites)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
**Leg 1 (additive)** first lands the `#library` root (DD1-DD3) and its test and doc migration. It then brings providers into Library (DD4-DD7, DD9, DD10's leg-1 half):
- moves the editor modules with the interim `host` option;
- adds `providers-section.js` and the studio hooks;
- adds the group, the Add item, the start-page card, Jump to and the router's Library providers row;
- copies the CSS;
- creates the `providers` lane with new Library-route tests (list rows, create, edit, delete, the anthropic-plan auto sign-in after a create, Jump to).

Settings still works unchanged through `host: 'settings'`.

**In-leg checkpoint:** the root half (DD1-DD3, the `library-start` rename, the `_nav`, parity, announcer and `expect_route` migrations, docs) is green on unit and on the routing, library, mcp, agents, chats, shared and contracts lanes before any provider work starts. That way a provider failure cannot obscure the root work. The leg's final gate is the full `make gate`.

**Leg 2 (subtractive)** removes providers from Settings (DD8):
- admin's provider branches, `providers-list.js`, the `settings` host path, the Settings router row, `settings-pages.js`'s row and Jump to's special case;
- the admin CSS copies (the `.cap-chip*` rules move to a shared location);
- the old provider browser tests are migrated to the Library routes (about 28 files across the providers, routing, chats and shared lanes, plus `test_visual_snapshots.py`), and `test_flow_settings_items.py` is split;
- the testids are retired and fenced, the `settings/providers` guard is added, and the `settings` budget is re-measured.

**Docs** move with each leg's change: `the_one/agents.md` ("Library list and detail", "Settings nav and pages", "Settings item pages", "Hash routing" incl. l.2264 and l.2281, the `_lists` doc l.167, and the request-count table), `CLAUDE.md` (route scheme, Library and Settings paragraphs, lanes, the `_nav` example), `docs/ui-testid-registry.md` and `docs/ui-control-inventory.md`. Narrative goes to `agents.md`; `CLAUDE.md` keeps invariants only.

### Checkpoints
- [x] Leg 1 root half green (in-leg checkpoint) before provider work starts.
- [x] Leg 1 landed: `#library` is the root, providers work in Library and in Settings, and `make gate` is green.
- [x] Leg 2 landed: Settings has no providers, no `settings/providers` route remains anywhere, and `make gate` is green.

### Adaptation Criteria

**Divert if**:
- `providers-section.js` needs studio state beyond DD4's `ctx`. Stop and re-plan the interface with the operator.
- The provider tests' migration reveals editor behaviour that depended on the Settings layout beyond DD7's list.

**Acceptable variations**:
- Exact lane budgets, icon key, start-page copy, helper names and `ctx`/handle method names (not their count or kind).
- Splitting a mixed test file differently from DD9's example, as long as each provider test lands in the `providers` lane.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `library-and-providers` - Additive: `#library` real root with section aliases, breadcrumbs and producers; then providers appear in Library (first group, Add menu, start-page card, Jump to, editor in the detail pane through `providers-section.js`); Settings still hosts providers; new `providers` lane; full gate green (DD1-DD7, DD9, DD10 leg 1)
- [x] `retire-settings-providers` - Subtractive: Settings Models group and `#settings/providers` removed; admin provider code, the tile list and the interim host path deleted; old provider tests migrated to Library routes; testids retired and fenced; `settings/providers` guard; full gate green (DD8, DD10 leg 2)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged (PR open; merge is the operator's call)
- [x] Tests passing (`make test-unit`; `make gate` with `THE_ONE_TEST_NETNS=1` and `THE_ONE_REQUIRE_WEBKIT=1`)
- [x] Documentation updated (`agents.md`, `CLAUDE.md`, `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`, re-authored behavior specs)

### Verification
- The charter's four criteria, each by an automated test:
  - **The Library group:** Library-route provider tests in the `providers` lane (rows, badge, "used by", item routes, create, edit, delete, the anthropic-plan hand-off).
  - **Root, Add menu and Jump to:** router unit tests for `#library` and the section aliases; browser tests for the start page's four cards in order, `library_add(page, "providers")` and Jump to providers.
  - **Settings:** the `test_settings_pages_static.py` seven-row table, and router tests for `#settings/providers` and `#admin/providers` resolving unknown.
  - **Tests:** the gate, plus the `settings/providers` literal guard and DD2's bare-section producer check.
- No behavior test is authored. With no HAT (operator decision), the re-authored existing specs (DD10) are the real-environment record.
