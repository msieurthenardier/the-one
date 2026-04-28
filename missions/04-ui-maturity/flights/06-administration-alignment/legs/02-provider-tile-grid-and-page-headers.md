# Leg: 02-provider-tile-grid-and-page-headers

**Status**: landed
**Flight**: [Administration Alignment](../flight.md)

## Objective

Replace admin's row-based provider card list with a CSS-grid of canonical `.entity-tile` tiles, lift two F5 per-area primitives to canonical names with breaking renames (`.agent-tile` family → `.entity-tile` family; `.studio-page-header`/`.studio-page-title`/`.new-agent-btn` → `.page-header`/`.page-title`/`.new-entity-btn`), add a "+ New Provider" button on the LLM Providers page, and extend admin's hash routing to deep-link provider detail (`#admin/providers/{id}`) and create mode (`#admin/providers/new`).

## Context

This leg is the visual + URL-layer transformation of admin's LLM Providers page. Three concurrent changes:

1. **Two breaking renames lift studio-specific class names to canonical**:
   - `.agent-tile` / `.agent-tile-grid` / `.agent-tile-name` / `.agent-tile-description` / `.agent-tile-meta` → `.entity-tile` / `.entity-tile-grid` / `.entity-tile-name` / `.entity-tile-description` / `.entity-tile-meta` (all in `components.css`)
   - `.studio-page-header` / `.studio-page-title` / `.new-agent-btn` → `.page-header` / `.page-title` / `.new-entity-btn` (lifted from `studio.css` to `components.css`)
   
   Per F6 flight spec, **no composition aliases are retained** — legacy class names cease to exist in any layer (markup, CSS, tests).

2. **Provider tile grid replaces the row-based card list**: today's `.admin-provider-card` rows (each containing badge + name + inline `[Edit][Delete]` buttons) become `<button class="entity-tile provider-tile" data-testid="provider-card" data-id="{id}" aria-selected="...">` tiles in a CSS-grid. Tile content: type badge (top-right corner via NEW `.entity-tile-badge` slot, composing with existing `.admin-provider-badge--{type}` color classes), provider name (`.entity-tile-name`), base_url snippet (`.entity-tile-meta`, mono caption, truncate-ellipsis; `mock` type with empty base_url shows "—"). NO per-tile X-button; NO inline action buttons. Click → editor (via hash route).

3. **Hash routing extension to provider detail**: extend admin's `serializeState`/`hydrateState` to encode and parse the editor sub-state. URL hierarchy after this leg:
   - `#admin/providers` → tile grid (no editor open)
   - `#admin/providers/new` → editor in create mode
   - `#admin/providers/{provider-id}` → editor in edit mode for the named provider
   
   Refresh on every URL returns to that exact view. Hydrate-vs-fetch race protection (mirrors F5 leg 03's `_pendingSelectName` pattern): if hydrate fires before providers list has loaded, store `pendingProviderId` and consume it after `fetchProviders` resolves.

4. **"+ New Provider" page-header button**: top-right header button on the LLM Providers page, mirroring chat's `.new-chat-header` and studio's `.new-agent-btn` (post-rename: `.new-entity-btn`). Same `square-pen` icon, same `.btn-outlined-cyan` composition. Renames `data-testid="add-provider-btn"` → `data-testid="new-provider-btn"`.

5. **`.page-header` lift consumed by System AND LLM Providers pages**: the merged System page (introduced by leg 01) currently uses `.admin-header` + `.admin-title`. Leg 02 migrates BOTH the System page and the new LLM Providers grid page to canonical `.page-header` + `.page-title`. The provider editor's `.admin-header` (in `_renderProviderFormImpl` for "Add Provider" / "Edit Provider" titles) stays untouched in this leg; leg 03 will replace it with `.editor-header`.

Subsequent legs depend on this leg's foundations:
- **Leg 03** consumes the URL contract (`#admin/providers/{id}`, `#admin/providers/new`) — the editor restructure inherits the hash routing wired here.
- **Leg 03** lifts the `.admin-header` → `.editor-header` for the editor surface; that lift only makes sense after this leg has freed the page-header concept for canonical use.
- **Leg 04** depends on the closure-state shape (no inline tile delete) for the dirty-gate's tile-click route.

Key prior context:
- F5 leg 02 introduced `.agent-tile` as the canonical CSS-grid tile primitive but kept the studio-specific name pending a second consumer (F5 flight.md design decision: "agents.md describes it as 'CSS-grid tile primitive for studio's agent inventory'" — admin is the imminent F6 consumer).
- F5 HAT removed the per-tile X-button (centralizing destruction in the editor's Danger Zone). Provider tiles inherit the post-HAT shape: single-click tile, no X.
- F5 debrief Action Item #2 ("audit area init() bottom block for legacy auto-selects against new URL contracts") — leg 02 introduces `#admin/providers/{id}` deep links; verify no legacy auto-select-first-provider exists in admin.js post-leg-01 (currently `init()` ends with `fetchProviderTypes(); App.layout.renderSectionNav(...)` + initial `renderContent()` — no auto-select; safe).
- F5 debrief Recommendation 1 (update agents.md for stale tile X-button content at lines 263-264) — DEFERRED to leg 05 (HAT) per F6 flight spec; this leg does NOT touch agents.md.

## Inputs

What exists before this leg runs (state at end of leg 01):

- `the_one/interfaces/web/static/js/areas/admin.js` (1037 LOC) — has 2-category sidebar, combined System page sub-module, existing `renderProvidersPanel()` row-list rendering, `_renderProviderFormImpl()` editor form, no hash routing for provider detail/create.
- `the_one/interfaces/web/static/js/areas/admin/system-page.js` — renders combined System page using `.admin-header` + `.admin-title` markup (created in leg 01).
- `the_one/interfaces/web/static/js/areas/layout/section-nav.js` — generic helper consumed by both studio + admin.
- `the_one/interfaces/web/static/css/components.css` (634 LOC) — has `.agent-tile` / `.agent-tile-name` / `.agent-tile-description` / `.agent-tile-meta` rules (lines 285-343).
- `the_one/interfaces/web/static/css/studio.css` (77 LOC) — has `.studio-page-header` / `.studio-page-title` / `.new-agent-btn` rules (lines 9-12) and `.area-studio .agent-tile-grid` layout rule (line 17).
- `the_one/interfaces/web/static/css/admin.css` (134 LOC) — has `.admin-provider-card`, `.admin-provider-badge`, `.admin-provider-badge--{type}`, `.admin-provider-name`, `.admin-provider-actions`, `.admin-provider-edit-btn`, `.admin-provider-delete-btn`, `.admin-provider-add-btn`, `.admin-provider-list`, `.admin-provider-empty`, `.admin-header`, `.admin-title`, etc.
- `the_one/interfaces/web/static/css/chat.css` — has `.area-chat .new-chat-header` (line 24-25); chat's pattern is the model for the canonical `.new-entity-btn`. **NOT touched in this leg** (chat keeps its own `.new-chat-header` class — it's chat-specific markup that mirrors but does not consume the canonical `.new-entity-btn`).
- `the_one/interfaces/web/static/js/areas/studio.js` — at line 173-181 emits `.studio-page-header` + `.studio-page-title` + `.new-agent-btn` markup; at lines 296-314 emits `.agent-tile` + `.agent-tile-name` + `.agent-tile-description` + `.agent-tile-meta` markup; at line 179-180 emits `.agent-tile-grid` container.
- `the_one/interfaces/web/static/js/areas/studio/stub-knowledge.js:10-11` — emits `.studio-page-header` + `.studio-page-title` markup.
- `the_one/interfaces/web/static/js/areas/studio/stub-tools.js:10-11` — emits `.studio-page-header` + `.studio-page-title` markup.
- 5 test files reference the soon-to-be-renamed studio classes:
  - `tests/browser/test_flow_agent_tile.py` — 8 selectors (`.agent-tile-grid`, `button.agent-tile`, `.agent-tile-name`)
  - `tests/browser/test_flow_keyboard.py:120-121` — 1 selector (`.agent-tile-grid`)
  - `tests/browser/test_flow_agent_tabs.py:43` — 1 selector (`button.agent-tile`)
  - `tests/browser/test_flow_dirty_confirm.py:51,137` — 2 selectors (`button.agent-tile`, `.agent-tile-grid`)
  - (No tests reference `.studio-page-header` / `.studio-page-title` / `.new-agent-btn` directly per leg 01's verified grep.)
- `tests/browser/test_flow_admin_navigation.py` — created in leg 01; admin tests assert `.admin-title` text. Leg 02 updates these to `.page-title`.
- `tests/browser/test_flow_hash_routing.py` — admin tests assert `.admin-title`. Update to `.page-title`.
- `tests/browser/test_flow_provider_setup.py` — has 4 admin assertions: line 47 (`.admin-title` text "Edit Provider" — STAYS, editor untouched in leg 02), line 35 (`[data-testid="add-provider-btn"]` — RENAMES to `[data-testid="new-provider-btn"]`), line 60 (`.admin-provider-name` — RENAMES to `.entity-tile-name`), line 63 (`.admin-provider-badge` text "mock" — STAYS, badge composes both classes), line 57 (`.admin-pf-cancel` — STAYS, leg 03 territory), line 62 (`[data-testid="provider-card"]` — testid preserved, element type changes from div to button).
- `tests/browser/test_visual_snapshots.py:267-270` — asserts `[data-testid="provider-card"]` is visible. Testid preserved; element type changes from `div` to `button.entity-tile`.

## Outputs

What exists after this leg completes:

- **MODIFIED** `the_one/interfaces/web/static/css/components.css`:
  - **Breaking rename** of `.agent-tile` → `.entity-tile`, `.agent-tile-name` → `.entity-tile-name`, `.agent-tile-description` → `.entity-tile-description`, `.agent-tile-meta` → `.entity-tile-meta` (lines 285-343). Add `position: relative` to `.entity-tile` so the badge can absolute-position. Update the inline comment block to reference "entity inventory" generally (not "agent inventory").
  - **NEW** `.entity-tile-badge` rule — top-right absolute-positioned slot for tile badges (provider type, future entity types). Inherits font/casing tokens from existing `.admin-provider-badge` patterns; admin per-area `.admin-provider-badge--{type}` rules compose for color.
  - **NEW** `.entity-tile-grid` rule (lifted + canonicalized from `.area-studio .agent-tile-grid` in studio.css, now studio-area-agnostic). `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))` — slightly wider than studio's previous 240px to accommodate provider tiles' badge + url content. Studio's tiles get the wider min-width too (acceptable; agent-tile-name is short enough to look fine at 280px).
  - **NEW** `.page-header` / `.page-title` / `.new-entity-btn` rules (lifted from `studio.css` lines 9-12). `.page-header` carries padding + flex layout; `.page-title` carries h1 sizing; `.new-entity-btn` carries `margin-left: auto` + icon-with-text flex-inline composition.
- **DELETED from `the_one/interfaces/web/static/css/studio.css`**: `.area-studio .studio-page-header`, `.area-studio .studio-page-title`, `.area-studio .new-agent-btn`, `.area-studio .new-agent-btn svg`, `.area-studio .agent-tile-grid` rules (lines 9-12, 17, plus their inline comments). Net `studio.css` LOC delta: −10 to −15.
- **DELETED from `the_one/interfaces/web/static/css/admin.css`**: `.admin-provider-add-btn` (line 47), `.admin-provider-list` (line 48), `.admin-provider-card` (line 49), `.admin-provider-card:hover` (line 50), `.admin-provider-name` (line 52), `.admin-provider-actions` (line 53), `.admin-provider-edit-btn` (line 54), `.admin-provider-delete-btn.admin-provider-delete-confirm` selector — keep the delete-confirm rule but retarget it to `.admin-pf-model-delete.admin-pf-model-delete-confirm` only (the row-level delete is gone; only the Ollama lifecycle delete-confirm remains for leg 02). Lines 55 split: keep the Ollama branch, delete the provider branch.
- **PRESERVED in `the_one/interfaces/web/static/css/admin.css`**: `.admin-provider-badge` (font/padding/text-transform), `.admin-provider-badge--{type}` color rules (lines 51, 128-133), `.admin-pf-*` rules (entire provider editor + Ollama lifecycle — leg 03 territory), `.admin-system-*` rules (System page — but `.admin-header` and `.admin-title` still need to stay because the editor still uses them in leg 02; deleted in leg 03).
- **NEW** `the_one/interfaces/web/static/js/areas/admin/providers-grid.js` — `App.admin.renderProvidersGrid(container, providers, callbacks)` renders the LLM Providers page-header + tile grid. Callbacks: `onSelectProvider(id)` (tile click), `onCreateProvider()` ("+ New Provider" click), and `onEmptyState()` (no-providers message — currently inline; can stay inline). Tile DOM: `<button class="entity-tile provider-tile" data-testid="provider-card" data-id="{id}" aria-selected="{true|false}">` containing `.entity-tile-badge`, `.entity-tile-name`, `.entity-tile-meta`. The active tile (when an editor is open for that id) carries `aria-selected="true"`; others carry `aria-selected="false"`.
- **MODIFIED** `the_one/interfaces/web/static/js/areas/admin.js`:
  - `renderProvidersPanel()` (admin.js:98-121 post-leg-01): replace inline HTML with `App.admin.renderProvidersGrid(contentEl, providers, callbacks)` call. Keep the `if (providerFormMode) { renderProviderForm(editingProvider); return; }` early-return — editor renders the existing form unchanged.
  - `renderProviderList()` (admin.js:136-187 post-leg-01): delete entirely (its work moves to providers-grid.js).
  - `serializeState()` (admin.js:8-10): extend to encode editor state. Returns `'system'`, `'providers'`, `'providers/new'` (when `providerFormMode === 'add'`), or `'providers/{id}'` (when `providerFormMode === 'edit'` AND `editingProvider`). Pending-id branch: when `_pendingProviderId` is set (hydrate before fetch race), return `'providers/' + _pendingProviderId`.
  - `hydrateState(sub)` (admin.js:11-18): parse the new sub-paths. `'providers/new'` → set `currentCategory='providers'`, queue `pendingFormMode='add'`. `'providers/{id}'` → set `currentCategory='providers'`, lookup provider in cache; if found, set `providerFormMode='edit'` + `editingProvider`; if not (race), store `_pendingProviderId` and let `_tryConsumePendingProvider()` pick it up after fetch. Legacy `'general'` redirect preserved from leg 01. **Critical**: hydrateState must call `this._tryConsumePendingProvider()` AFTER `_setCategory(sub)` returns — because `_setCategory` (admin.js:1014-1022) early-returns when `currentCategory === sub` (no-op when category unchanged), the consume call must fire unconditionally to handle the within-admin sub-state transitions (e.g., `#admin/providers` → `#admin/providers/new` does not change category but DOES need a re-render).
  - Add `_tryConsumePendingProvider()` method on `self`: invoked from (a) end of `hydrateState` to handle within-admin sub-state changes; (b) the `fetchProviders().then(...)` callback to handle hydrate-before-fetch race. If `pendingFormMode === 'add'`, transition to create mode + clear pending. If `pendingFormMode === 'edit' && pendingProviderId`, look up provider in cache; if found, transition to edit mode + clear pending; if not (still racing), keep pending. Always re-render (`renderProvidersPanel()`) when state actually transitions. **No-op safe**: if no pending state, return without rendering.
  - Replace existing tile click handler (was `editBtns[e].addEventListener` in renderProviderList, admin.js:165-176 post-leg-01) with the providers-grid.js callback path: `onSelectProvider(id)` calls a new `selectProvider(id)` function that sets `providerFormMode='edit'`, `editingProvider=foundProvider`, calls `App.router.replaceSub(self.serializeState())`, and re-renders.
  - Replace `addBtn.onclick` (admin.js:114 post-leg-01): `onCreateProvider()` callback calls a new `enterCreateMode()` function that sets `providerFormMode='add'`, `editingProvider=null`, calls `App.router.replaceSub(self.serializeState())`, and re-renders.
  - Replace existing delete-button handler in `renderProviderList` (admin.js:179-187 post-leg-01) — gone (no per-tile delete in leg 02; deletion moves to detail Danger Zone in leg 03). The existing `handleProviderDelete` function (admin.js:200-261 post-leg-01) **is preserved as scaffolding for leg 03**: the agent-usage check (`/api/providers/{id}/agents` lookup that hard-blocks delete with "Used by: ..." text) is the right gate before the new Danger Zone Delete fires `App.confirmDelete`; leg 03 will rewire it onto the Danger Zone Delete button. **Provider deletion is temporarily unavailable in leg 02** (the inline tile-row delete is removed; the Danger Zone delete arrives in leg 03). This is acceptable because no human user interacts with the build between autonomous legs (defer-commit policy). Documented in the F6 flight log under "Decisions" at landing.
  - The `findProvider(id)` helper (admin.js:189-194 post-leg-01) is preserved (used by both selectProvider and pending-id consumption).
  - The provider editor (`_renderProviderFormImpl` admin.js:274-354, `wireProviderFormEvents` admin.js:356-525 post-leg-01) is UNCHANGED in leg 02. Its Cancel button (admin.js:402-406 post-leg-01) still routes back to the grid via `providerFormMode = null; renderProvidersPanel()`. Update Cancel to ALSO call `App.router.replaceSub('providers')` so the URL reflects the grid view after Cancel.
  - **`fetchProviders()` refactor** (admin.js:123-133 post-leg-01): change to `return fetch(...).then(...)` so the call site can chain. Inside `.then`, replace the existing `providers = data; renderProviderList();` with `providers = data; populateProviderGrid(); self._tryConsumePendingProvider();`. The new `populateProviderGrid()` helper (added inline in admin.js) renders the tile grid in-place WITHOUT re-firing fetch — it just calls `App.admin.renderProvidersGrid(contentEl, providers, callbacks)`. **Critical**: do NOT call `renderProvidersPanel()` from `.then` — that would loop (renderProvidersPanel itself calls fetchProviders). The `.then` callback's job is "populate the grid AFTER fetch resolves"; the panel-level orchestration (decide editor vs grid based on providerFormMode) belongs to `renderProvidersPanel`.
  - **`renderProvidersPanel()` flow** (admin.js:98-121 post-leg-01): replace inline HTML with two-branch logic:
    1. If `providerFormMode` is set → call existing `renderProviderForm(editingProvider)` (editor branch — unchanged in leg 02).
    2. Else → render the page-header + grid skeleton via `App.admin.renderProvidersGrid(contentEl, providers, callbacks)` AND fire `fetchProviders()` to (re-)populate. The helper handles both the initial null/empty state ("Loading providers…") and the populated state (tiles).
  - **Initialize `providers = null`** (NOT `[]`) so `App.admin.renderProvidersGrid` correctly shows the loading placeholder on first render. After `fetchProviders.then` resolves, `providers = data` and the helper re-renders with tiles.
- **MODIFIED** `the_one/interfaces/web/static/js/areas/admin/system-page.js`: replace `<div class="admin-header"><span class="admin-title">System</span></div>` with `<div class="page-header"><h1 class="page-title">System</h1></div>`.
- **MODIFIED** `the_one/interfaces/web/static/js/areas/studio.js`: rename `.studio-page-header` → `.page-header`, `.studio-page-title` → `.page-title`, `.new-agent-btn` → `.new-entity-btn`, `.agent-tile-grid` → `.entity-tile-grid`, `.agent-tile` → `.entity-tile` (preserved compose with `.agent-item` for selector continuity? Verify: F5 markup line 296 is `'agent-tile agent-item' + (isActive ? ' active' : '')`. After rename: `'entity-tile agent-item' + ...` — `.agent-item` stays as a selector hook; only the tile primitive class renames. Tests using `[data-testid="agent-item"]` selectors continue to match. Tests using `.agent-tile` selectors (5 files, ~12 selectors) update to `.entity-tile`).
  - Lines 173-181: page-header markup rename + grid container rename (`.agent-tile-grid` → `.entity-tile-grid`).
  - Lines 296-314: tile element class names rename.
  - Verify there are no other emit-sites (`grep -n 'agent-tile\|studio-page' static/js/areas/studio.js static/js/areas/studio/*.js`).
- **MODIFIED** `the_one/interfaces/web/static/js/areas/studio/stub-knowledge.js:10-11`: `studio-page-header` → `page-header`, `studio-page-title` → `page-title`.
- **MODIFIED** `the_one/interfaces/web/static/js/areas/studio/stub-tools.js:10-11`: same rename.
- **MODIFIED** `the_one/interfaces/web/static/index.html`: add `<script src="/static/js/areas/admin/providers-grid.js"></script>` BEFORE `admin.js` (after the existing `admin/system-page.js` line from leg 01).
- **MODIFIED** 5 studio test files: bulk-update class selectors. Specific changes:
  - `test_flow_agent_tile.py`: 8 selector updates (`.agent-tile-grid` → `.entity-tile-grid`; `button.agent-tile` → `button.entity-tile`; `.agent-tile-name` → `.entity-tile-name`). Line ranges: 36, 39, 53, 71, 74, 77, 78, 79, 80.
  - `test_flow_keyboard.py:120-121`: `.agent-tile-grid` → `.entity-tile-grid`.
  - `test_flow_agent_tabs.py:43`: `button.agent-tile` → `button.entity-tile`.
  - `test_flow_dirty_confirm.py:51,137`: same rename.
  - `test_flow_studio_navigation.py`: re-grep to verify it doesn't reference these classes (none expected per leg 01 grep).
- **MODIFIED** admin test files for the page-header lift + new-provider-btn rename:
  - `test_flow_admin_navigation.py`: update assertions on `.admin-title` → `.page-title` (text assertions stay unchanged: "System", "LLM Providers"). The keyboard nav test's section-nav-item assertions stay — that's leg 01 territory, unchanged here.
  - `test_flow_hash_routing.py`: update `.admin-title` → `.page-title` for all admin assertions (lines 36, 51, 217, 228 — "System" or "LLM Providers"); the `.admin-title` "General Settings" assertion was renamed to "System" in leg 01, so the text is fine; only the SELECTOR changes from `.admin-title` to `.page-title`.
  - `test_flow_provider_setup.py`:
    - Line 35: `[data-testid="add-provider-btn"]` → `[data-testid="new-provider-btn"]`.
    - Line 47 (`.admin-title` text "Edit Provider"): STAYS — the editor still uses `.admin-header` / `.admin-title` until leg 03.
    - Line 60 (`.admin-provider-name`): → `.entity-tile-name`.
    - Line 63 (`.admin-provider-badge` text "mock"): STAYS — the badge composes `entity-tile-badge admin-provider-badge admin-provider-badge--mock`, so `.admin-provider-badge` selector still matches. (Verify during impl that the type-suffix subselector also still matches.)
    - Line 62 (`[data-testid="provider-card"]`): STAYS — testid preserved; element type changes from div to button (selectors via testid match either).
  - `test_visual_snapshots.py:267-270`: `[data-testid="provider-card"]` STAYS. The visual snapshot itself will drift (gitignored regen).
- **NEW** `tests/browser/test_flow_provider_grid.py` — new tests covering the tile grid + page-header + hash routing for provider detail/create. Scope: page-header renders title + "+ New Provider" button; tile grid renders tiles with name/badge/url; clicking tile navigates to `#admin/providers/{id}`; refresh on `#admin/providers/{id}` returns to that editor (via hydrate-vs-fetch race protection); clicking "+ New Provider" navigates to `#admin/providers/new`; refresh on that URL returns to create mode; clicking Cancel from create returns to `#admin/providers` grid; pending-id with unknown provider id falls back gracefully (URL stays at the unknown id; grid renders with no tile selected). Target: 6-8 new tests.
- **STATE**: `admin.js` shrinks (renderProviderList extraction = ~50 LOC out, hash routing additions = ~30 LOC in, net ~ −20 LOC; target ≤ 1020 LOC). `admin.css` shrinks (~30 LOC out for provider-card/list/actions/edit/delete/add-btn rules + 1 LOC for provider-delete-confirm split; net ~−30 LOC; target ≤ 105 LOC). `components.css` grows (~20 LOC for new `.entity-tile-badge`, `.entity-tile-grid`, `.page-header` family rules; ~5 LOC for inline-comment updates; net ~+25 LOC; target ≤ 660 LOC). `studio.css` shrinks (~10 LOC out for the lifted rules; target ≤ 65 LOC).

## Acceptance Criteria

- [ ] `.entity-tile`, `.entity-tile-name`, `.entity-tile-description`, `.entity-tile-meta` exist in `components.css` as canonical rules; `.agent-tile`, `.agent-tile-name`, `.agent-tile-description`, `.agent-tile-meta` no longer exist anywhere in `static/css/`. (`grep -rn 'agent-tile' static/css/` returns 0 matches.)
- [ ] `.entity-tile-grid` exists in `components.css` as a canonical rule; `.agent-tile-grid` no longer exists. (`grep -rn 'agent-tile-grid' static/css/` returns 0 matches.)
- [ ] `.entity-tile-badge` exists in `components.css` as a NEW canonical rule for the top-right corner badge slot. `.entity-tile` includes `position: relative`.
- [ ] `.page-header`, `.page-title`, `.new-entity-btn` exist in `components.css` as canonical rules; `.studio-page-header`, `.studio-page-title`, `.new-agent-btn` no longer exist anywhere in `static/css/`. (`grep -rn 'studio-page-header\|studio-page-title\|new-agent-btn' static/css/` returns 0 matches.)
- [ ] `studio.js`, `studio/stub-knowledge.js`, `studio/stub-tools.js` emit canonical class names in their markup strings (`page-header`, `page-title`, `new-entity-btn`, `entity-tile-grid`, `entity-tile`, `entity-tile-name`, `entity-tile-description`, `entity-tile-meta`). (`grep -rn 'agent-tile\|studio-page-header\|studio-page-title\|new-agent-btn' static/js/areas/studio.js static/js/areas/studio/` returns 0 matches.)
- [ ] Studio still renders correctly: navigate to `#studio`, observe page-header + tile grid + tiles; keyboard nav works; click a tile to enter editor; click Back to return to grid; existing studio tests pass.
- [ ] LLM Providers page renders a `.page-header` with `<h1 class="page-title">LLM Providers</h1>` and a `<button class="btn-outlined-cyan new-entity-btn" data-testid="new-provider-btn">{App.icon('square-pen')} New Provider</button>`.
- [ ] System page (`#admin/system`) renders a `.page-header` with `<h1 class="page-title">System</h1>` (no button next to title — System has no primary action). The `.admin-header` + `.admin-title` selectors no longer apply to the System page (verified by grep on `system-page.js`).
- [ ] Provider editor (`#admin/providers/{id}` and `#admin/providers/new`) STILL renders `.admin-header` + `.admin-title` (untouched in leg 02; restructure is leg 03 territory).
- [ ] Provider tile grid renders at `#admin/providers`: each tile is `<button class="entity-tile provider-tile" data-testid="provider-card" data-id="{id}" aria-selected="{true|false}">` containing `.entity-tile-badge` (composed with `.admin-provider-badge` + `.admin-provider-badge--{type}` color class), `.entity-tile-name` (provider name), `.entity-tile-meta` (base_url snippet, mono caption, truncate-ellipsis; "—" for empty base_url).
- [ ] Empty state (no providers): tile grid container renders the existing empty-state message ("No providers configured. Add one to get started.") via `.empty-state` class.
- [ ] No per-tile X-button; no inline `[Edit][Delete]` action cluster.
- [ ] Clicking a tile navigates to `#admin/providers/{provider-id}` and opens the existing editor (`_renderProviderFormImpl`) in edit mode for that provider.
- [ ] Clicking "+ New Provider" navigates to `#admin/providers/new` and opens the editor in create mode.
- [ ] Refresh on `#admin/providers/{provider-id}` returns to the editor for that provider (with hydrate-vs-fetch race protection: pending id is consumed after providers fetch resolves).
- [ ] Refresh on `#admin/providers/new` returns to create mode.
- [ ] Refresh on `#admin/providers` (no editor) returns to the tile grid.
- [ ] **Within-admin URL transitions**: clicking "+ New Provider" while at `#admin/providers` updates URL to `#admin/providers/new` AND opens the create editor (no full reload). Clicking a tile while at `#admin/providers` updates URL to `#admin/providers/{id}` AND opens the edit editor. Clicking Cancel from the editor updates URL back to `#admin/providers` AND renders the grid. Clicking section-nav "System" while in any admin sub-state updates URL to `#admin/system` AND clears pending provider state.
- [ ] **POST 201 URL upgrade**: in create mode at `#admin/providers/new`, after Create succeeds, URL upgrades to `#admin/providers/{newly-created-id}` AND the form auto-switches to edit mode.
- [ ] Cancel button in the editor (still uses existing `.admin-pf-cancel` selector for leg 02) returns to `#admin/providers` (URL updates via `App.router.replaceSub('providers')`); the grid renders.
- [ ] Existing Save flow: clicking Create in create mode POSTs to `/api/providers`, on 201 the URL upgrades from `#admin/providers/new` to `#admin/providers/{id}` (the form auto-switches to edit mode via existing flow + new `App.router.replaceSub`).
- [ ] Existing Save flow: clicking Save in edit mode PUTs to `/api/providers/{id}`, on 200 the URL stays at `#admin/providers/{id}`; the form re-renders in edit mode with updated data.
- [ ] Hydrate-vs-fetch race protection: `_pendingProviderId` is set when `hydrateState` parses `'providers/{id}'` before providers are loaded; it is consumed in `fetchProviders().then(...)` after the providers array populates.
- [ ] Unknown-id fallback: refresh on `#admin/providers/{nonexistent-id}` keeps URL at the unknown id, renders the grid with no tile selected, and surfaces no error (defensive — race may resolve later if the id is actually a not-yet-known new provider; otherwise the URL stays "stale" until the user clicks something).
- [ ] `add-provider-btn` test selector renamed to `new-provider-btn` in `test_flow_provider_setup.py:35`. Existing test still passes.
- [ ] 5 studio test files updated for breaking renames; all studio tests still pass.
- [ ] Admin tests (`test_flow_admin_navigation.py`, `test_flow_hash_routing.py`) updated `.admin-title` → `.page-title` selectors; tests still pass.
- [ ] `test_flow_provider_setup.py` updated: line 35 selector, line 60 selector (`.admin-provider-name` → `.entity-tile-name`); other admin selectors stay.
- [ ] **NEW** `test_flow_provider_grid.py` exists with 6-8 tests covering tile grid render + page-header + hash routing for `#admin/providers/{id}` and `#admin/providers/new` + Cancel-returns-to-grid + unknown-id fallback.
- [ ] Test counts: `pytest tests/` passes ≥ 407; `pytest -m browser tests/browser/` passes ≥ 184 (leg 01 brought it to 178; +6-8 new tests in test_flow_provider_grid.py).
- [ ] No new pyright/ruff errors introduced.
- [ ] `flight-log.md` updated with a `### 02-provider-tile-grid-and-page-headers` entry under Leg Progress.
- [ ] Leg status in this file's header updates from `planning` → `in-flight` → `landed` (don't commit).
- [ ] **No edits to `agents.md` in this leg** (deferred to leg 05 HAT per F6 flight spec).
- [ ] CSS comment text references to legacy class names updated: components.css:101 (cross-reference comment about `.agent-tile`) → `.entity-tile`; components.css:286 comment text in the entity-tile block (`<button class="agent-tile">`) → `<button class="entity-tile">`.
- [ ] Test docstring text references to legacy class names updated: `test_flow_agent_tile.py:5,6,29` (module + function docstrings) and `test_flow_keyboard.py:109,120` (function docstring + inline comment) updated from `agent-tile`/`agent-tile-grid` to `entity-tile`/`entity-tile-grid`.
- [ ] `pendingProviderId` cleared on category change (cross-category nav: clicking System clears any pending provider state).
- [ ] **No commit** (per `/agentic-workflow` defer-commit policy).

## Verification Steps

How to confirm each criterion is met:

- **CSS rename completeness**: 
  - `grep -rn 'agent-tile\|studio-page-header\|studio-page-title\|new-agent-btn' static/css/ static/js/areas/` — returns 0 matches.
  - `grep -n 'entity-tile\|page-header\|page-title\|new-entity-btn' static/css/components.css` — returns the new canonical rules.
- **Studio still works**: navigate to `#studio`, observe page-header + tile grid + tiles; keyboard nav (Tab → arrow keys → Enter); click a tile; refresh on the editor URL; all studio tests pass via `pytest -m browser tests/browser/test_flow_agent_*.py tests/browser/test_flow_studio_*.py`.
- **Admin LLM Providers page**: navigate to `#admin/providers`, observe page-header with title + "+ New Provider" button; observe tile grid (or empty state if no providers); click "+ New Provider" → URL becomes `#admin/providers/new`; click Cancel → URL becomes `#admin/providers`; click a tile → URL becomes `#admin/providers/{id}`; refresh on each URL works.
- **System page**: navigate to `#admin/system`, observe `.page-header` with title "System"; existing 3 sections (Environment + Appearance + Encryption) render unchanged.
- **Editor unchanged**: navigate to `#admin/providers/{id}`, observe `.admin-header` + `.admin-title` "Edit Provider" (UNCHANGED — leg 03 territory); existing form, fields, Test button, etc. all work.
- **Hash routing**: 
  - `page.evaluate('location.hash')` after each navigation matches expected.
  - Refresh on each URL preserves state.
- **Tests**: `docker exec the-one pytest tests/ -m 'not browser' --timeout=120` (≥ 407); `docker exec the-one pytest -m browser tests/browser/ --timeout=120` (≥ 184).
- **No agents.md edits**: `git diff main -- the_one/agents.md` returns no diff (no edits to that file in this leg).

## Implementation Guidance

### Step 1: Lift CSS rules to canonical names (components.css + studio.css)

In `static/css/components.css`:

1. Find the "Agent Tile" comment block + rules (lines ~285-343). Apply these edits:
   - Rename comment header from `=== Agent Tile (CSS-grid tile primitive for studio's agent inventory) ===` to `=== Entity Tile (CSS-grid tile primitive for entity inventories) ===`
   - Rename comment text inside the block (line 286): `<button class="agent-tile">` → `<button class="entity-tile">`.
   - Rename `.agent-tile` → `.entity-tile` (5 occurrences within the block)
   - Rename `.agent-tile-name` → `.entity-tile-name`
   - Rename `.agent-tile-description` → `.entity-tile-description`
   - Rename `.agent-tile-meta` → `.entity-tile-meta`
   - **Also** update the cross-reference comment at components.css:101 (inside the `.list-item-delete` comment block) — `.agent-tile (CSS-grid cell) in F5 leg 02; .agent-tile is a sibling` → `.entity-tile (CSS-grid cell) in F5 leg 02; .entity-tile is a sibling`. This is a comment text update, not a selector.
   - Add `position: relative;` to `.entity-tile` body (so the absolute-positioned `.entity-tile-badge` anchors correctly)
   - **NEW** rule after `.entity-tile-meta`:
     ```css
     /* Entity-tile badge slot — absolute-positioned top-right corner.
        Composes with per-area color classes (e.g. .admin-provider-badge--ollama). */
     .entity-tile-badge {
       position: absolute;
       top: 8px;
       right: 8px;
       font-family: var(--font-family-mono);
       font-size: var(--font-size-tiny);
       font-weight: var(--font-weight-semibold);
       padding: 2px 8px;
       border-radius: 4px;
       text-transform: uppercase;
       letter-spacing: 0.5px;
       /* Color comes from per-area .admin-provider-badge--{type} composition. */
     }
     ```
   - **NEW** rule for the grid (lifted from studio.css):
     ```css
     /* Tile-grid layout container. Used by entity inventories that render
        tiles as the primary view. Lifted from studio's .agent-tile-grid in
        F6 leg 02; admin's provider grid is the second consumer. */
     .entity-tile-grid {
       flex: 1;
       overflow-y: auto;
       padding: 8px;
       display: grid;
       grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
       gap: 8px;
       align-content: start;
     }
     ```

2. **NEW** rules block (lifted from studio.css lines 9-12) — place near the existing `.section-nav` block (around components.css:353):
   ```css
   /* === Page header (entity-list / area-page header with optional primary action) === */
   /* Mirrors chat's .header + .new-chat-header pattern. Used by studio's
      Agents/Knowledge/Tools pages and admin's System + LLM Providers pages.
      Lifted from per-area .studio-page-header in F6 leg 02. */
   .page-header {
     padding: 14px 20px;
     display: flex;
     align-items: center;
     gap: 12px;
   }
   .page-title {
     font-size: var(--font-size-h2);
     font-weight: var(--font-weight-semibold);
     color: var(--fg);
     margin: 0;
   }
   .new-entity-btn {
     margin-left: auto;
     white-space: nowrap;
     flex-shrink: 0;
     display: inline-flex;
     align-items: center;
     gap: 6px;
   }
   .new-entity-btn svg {
     width: 14px;
     height: 14px;
   }
   ```

In `static/css/studio.css`:

3. Delete lines 9-12 (`.area-studio .studio-page-header`, `.studio-page-title`, `.new-agent-btn`, `.new-agent-btn svg`).
4. Delete the `.area-studio .agent-tile-grid` rule (line 17).
5. Delete the now-orphaned comment block above (`/* Tile grid: studio-area override... */`).

In `static/css/admin.css`:

6. Delete `.admin-provider-add-btn` (line 47).
7. Delete `.admin-provider-list` (line 48).
8. Delete `.admin-provider-card` (line 49).
9. Delete `.admin-provider-card:hover` (line 50).
10. Delete `.admin-provider-name` (line 52).
11. Delete `.admin-provider-actions` (line 53).
12. Delete `.admin-provider-edit-btn` (line 54).
13. Edit line 55 (`.admin-provider-delete-btn.admin-provider-delete-confirm, .admin-pf-model-delete.admin-pf-model-delete-confirm`): split into just `.admin-pf-model-delete.admin-pf-model-delete-confirm` (keep the Ollama lifecycle delete-confirm; drop the per-row provider delete-confirm). The provider editor's Delete (Danger Zone, leg 03) will get its own rule.
14. Keep `.admin-provider-badge` (line 51) and `.admin-provider-badge--{type}` color rules (lines 128-133).
15. Keep `.admin-provider-empty` (if it exists — verify via grep).

### Step 2: Update studio markup strings

In `static/js/areas/studio.js`:

- Line 173: `'<div class="studio-page-header">'` → `'<div class="page-header">'`
- Line 174: `'<h1 class="studio-page-title">Agents</h1>'` → `'<h1 class="page-title">Agents</h1>'`
- Line 175: `'<button class="btn-outlined-cyan new-agent-btn" type="button" data-testid="new-agent-btn">'` → `'<button class="btn-outlined-cyan new-entity-btn" type="button" data-testid="new-agent-btn">'` (testid stays — studio's New Agent testid is unique to studio)
- Line 179: `'<div class="agent-tile-grid" role="listbox" aria-label="Agents"></div>'` → `'<div class="entity-tile-grid" role="listbox" aria-label="Agents"></div>'`
- Line 180: `agentsContentEl.querySelector('.agent-tile-grid')` → `agentsContentEl.querySelector('.entity-tile-grid')`
- Line 181: `agentsContentEl.querySelector('.new-agent-btn')` → `agentsContentEl.querySelector('.new-entity-btn')`
- Line 296: `tileEl.className = 'agent-tile agent-item' + (isActive ? ' active' : '')` → `tileEl.className = 'entity-tile agent-item' + (isActive ? ' active' : '')` (preserving `.agent-item` composition; only the primitive class renames)
- Line 304: `nameSpan.className = 'agent-tile-name'` → `nameSpan.className = 'entity-tile-name'`
- Line 309: `descSpan.className = 'agent-tile-description'` → `descSpan.className = 'entity-tile-description'`
- Line 314: `metaSpan.className = 'agent-tile-meta'` → `metaSpan.className = 'entity-tile-meta'`

In `static/js/areas/studio/stub-knowledge.js`:
- Line 10: `'<div class="studio-page-header">'` → `'<div class="page-header">'`
- Line 11: `'<h1 class="studio-page-title">Knowledge</h1>'` → `'<h1 class="page-title">Knowledge</h1>'`

In `static/js/areas/studio/stub-tools.js`:
- Same renames.

### Step 3: Migrate System page markup

In `static/js/areas/admin/system-page.js` — find the `<div class="admin-header">` block (the line beginning `'<div class="admin-header">'` near the top of `renderSystemPage`'s innerHTML template). Replace:
```js
'<div class="admin-header">' +
  '<span class="admin-title">System</span>' +
'</div>' +
```
with:
```js
'<div class="page-header">' +
  '<h1 class="page-title">System</h1>' +
'</div>' +
```

### Step 4: Create admin/providers-grid.js sub-module

`mkdir -p static/js/areas/admin` (already exists from leg 01).

Create `static/js/areas/admin/providers-grid.js`:

```js
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Renders the LLM Providers page-header + tile grid.
  //
  // Tile DOM (post-leg-02 canonical):
  //   <button class="entity-tile provider-tile"
  //           data-testid="provider-card"
  //           data-id="{provider.id}"
  //           aria-selected="{true|false}">
  //     <span class="entity-tile-badge admin-provider-badge admin-provider-badge--{type}">{type}</span>
  //     <span class="entity-tile-name">{name}</span>
  //     <span class="entity-tile-meta">{base_url || '—'}</span>
  //   </button>
  //
  // The active tile (when an editor is open for that id) carries
  // aria-selected="true"; others carry aria-selected="false".

  var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'mock'];

  function renderProvidersGrid(container, providers, callbacks) {
    callbacks = callbacks || {};
    var onSelectProvider = callbacks.onSelectProvider || function () {};
    var onCreateProvider = callbacks.onCreateProvider || function () {};
    var selectedId = callbacks.selectedId || null;

    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;

    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">LLM Providers</h1>' +
        '<button class="btn-outlined-cyan new-entity-btn" type="button" data-testid="new-provider-btn">' +
          window.App.icon('square-pen') + '<span>New Provider</span>' +
        '</button>' +
      '</div>' +
      '<div class="entity-tile-grid" role="listbox" aria-label="LLM providers">' +
        '<div class="admin-loading">Loading providers…</div>' +
      '</div>';

    var newProviderBtn = container.querySelector('.new-entity-btn');
    newProviderBtn.addEventListener('click', function () { onCreateProvider(); });

    var gridEl = container.querySelector('.entity-tile-grid');
    if (providers === null || providers === undefined) {
      // Loading state — caller will re-invoke with populated array
      return;
    }

    if (providers.length === 0) {
      gridEl.innerHTML =
        '<div class="empty-state admin-provider-empty">' +
          'No providers configured. Add one to get started.' +
        '</div>';
      return;
    }

    var html = '';
    for (var i = 0; i < providers.length; i++) {
      var p = providers[i];
      var typeSuffix = KNOWN_BADGE_TYPES.indexOf(p.type) >= 0 ? p.type : 'unknown';
      var displayUrl = p.base_url ? p.base_url : '—';
      var isActive = selectedId === p.id;
      html +=
        '<button class="entity-tile provider-tile" type="button" role="option" ' +
            'data-testid="provider-card" data-id="' + escapeAttr(p.id) + '" ' +
            'aria-selected="' + (isActive ? 'true' : 'false') + '">' +
          '<span class="entity-tile-badge admin-provider-badge admin-provider-badge--' +
            escapeAttr(typeSuffix) + '">' + escapeHtml(p.type) + '</span>' +
          '<span class="entity-tile-name">' + escapeHtml(p.name) + '</span>' +
          '<span class="entity-tile-meta">' + escapeHtml(displayUrl) + '</span>' +
        '</button>';
    }
    gridEl.innerHTML = html;

    var tiles = gridEl.querySelectorAll('.provider-tile');
    for (var t = 0; t < tiles.length; t++) {
      (function (tileEl) {
        tileEl.addEventListener('click', function () {
          var id = tileEl.dataset.id;
          if (id) onSelectProvider(id);
        });
      })(tiles[t]);
    }
  }

  window.App.admin.renderProvidersGrid = renderProvidersGrid;
})();
```

**ARIA decision**: the grid container uses `role="listbox"` (matches studio's tile-grid post-F5) and tiles use `role="option"` + `aria-selected="true|false"`. This is the WAI-ARIA-correct combo: `aria-selected` is only valid on items inside `role="listbox"`/`role="grid"`/etc. parents. An earlier draft used `role="list"` + `aria-selected` which is invalid ARIA — fixed.

### Step 5: Update admin.js for hash routing + sub-module consumption

Open `static/js/areas/admin.js`. Apply these edits:

1. **`serializeState()` extension** (around lines 8-10):
   ```js
   serializeState: function () {
     if (this._currentCategory === 'system') return 'system';
     if (this._currentCategory === 'providers') {
       if (this._providerFormMode === 'add') return 'providers/new';
       if (this._providerFormMode === 'edit' && this._editingProvider) {
         return 'providers/' + encodeURIComponent(this._editingProvider.id);
       }
       // Hydrate-vs-fetch race: pending id known but provider not yet loaded.
       if (this._pendingProviderId) {
         return 'providers/' + encodeURIComponent(this._pendingProviderId);
       }
       return 'providers';
     }
     return this._currentCategory || 'system';
   }
   ```
   
   Note: closure-locals `currentCategory`, `providerFormMode`, `editingProvider` are exposed via `Object.defineProperty(self, '_currentCategory', ...)` etc. (mirrors leg 01's pattern at admin.js:1226-1229). Add new exposures for `_providerFormMode`, `_editingProvider`, `_pendingProviderId`.

2. **`hydrateState(sub)` extension** (admin.js:11-18 post-leg-01):
   ```js
   hydrateState: function (sub) {
     var origSub = sub;
     if (sub === 'general') sub = 'system';  // legacy redirect

     var pendingId = null;
     var pendingFormMode = null;
     if (origSub === 'providers/new') {
       sub = 'providers';
       pendingFormMode = 'add';
     } else if (origSub && origSub.indexOf('providers/') === 0) {
       sub = 'providers';
       pendingFormMode = 'edit';
       // Strip trailing slash defensively; decodeURIComponent the id.
       var rest = origSub.slice('providers/'.length);
       if (rest.charAt(rest.length - 1) === '/') rest = rest.slice(0, -1);
       // Defensive: if extra path segments, take only the first.
       var slashIdx = rest.indexOf('/');
       if (slashIdx !== -1) rest = rest.slice(0, slashIdx);
       pendingId = rest ? decodeURIComponent(rest) : null;
     }

     var validIds = ['system', 'providers'];
     if (validIds.indexOf(sub) === -1) return;

     // Always overwrite pending state — including with nulls when the new
     // sub does not match providers/... — so navigating from
     // #admin/providers/new → #admin/system clears pending state.
     this._pendingProviderId = pendingId;
     this._pendingFormMode = pendingFormMode;

     if (this._setCategory) this._setCategory(sub);

     // Sub-state changes within the same category (e.g.,
     // #admin/providers → #admin/providers/new) do NOT trigger _setCategory's
     // re-render path because currentCategory is unchanged. Fire consume
     // unconditionally so within-admin sub navigation actually opens the
     // editor.
     if (this._tryConsumePendingProvider) this._tryConsumePendingProvider();
   }
   ```

3. **Closure-state additions** in `init` (admin.js:30-32 post-leg-01 — where `providers`, `providerFormMode`, `editingProvider` are declared):
   - **Change** `var providers = [];` to `var providers = null;` so the helper's loading-placeholder branch fires on initial render.
   - Add `var pendingProviderId = null;` and `var pendingFormMode = null;` (the hydrate-time parsed values; consumed during/after fetch).
   - Add `Object.defineProperty(self, '_providerFormMode', {get: function () { return providerFormMode; }, set: function (v) { providerFormMode = v; }, configurable: true});` (mirrors the existing `_currentCategory` defineProperty pattern at admin.js:1010-1013 post-leg-01).
   - Same for `_editingProvider`, `_pendingProviderId`, `_pendingFormMode`.
   - The setters let `hydrateState` mutate via `this._pendingProviderId = pendingId` (descriptor setter writes through to the closure local). Mutations from inside the closure (e.g., from `selectProvider`, `enterCreateMode`, `_tryConsumePendingProvider`) write directly to the local — no need to go through the setter when already inside the closure scope.
   - Two-tier access discipline: outer `this.*` methods (serializeState, hydrateState, _setCategory, _refresh, _tryConsumePendingProvider) read/write through the property; inner closure functions (selectProvider, enterCreateMode, fetchProviders.then, cancelBtn handler, saveBtn handler) read/write the local directly.

4. **`renderProvidersPanel()` rewrite** (lines 314-337): replace inline HTML with sub-module call:
   ```js
   function renderProvidersPanel() {
     // Editor branch: renders existing form (untouched leg 02).
     if (providerFormMode) {
       renderProviderForm(editingProvider);
       return;
     }
     // Grid branch: delegate to providers-grid sub-module.
     App.admin.renderProvidersGrid(contentEl, providers, {
       selectedId: editingProvider ? editingProvider.id : null,
       onSelectProvider: selectProvider,
       onCreateProvider: enterCreateMode
     });
     // The sub-module renders a "Loading providers…" placeholder if providers
     // is null/undefined; it auto-populates the grid otherwise. Trigger fetch
     // (matches existing behavior at line 336):
     fetchProviders();
   }
   ```

5. **NEW `selectProvider(id)` function** (replaces inline edit-button handler at lines 383-391):
   ```js
   function selectProvider(id) {
     var provider = findProvider(id);
     if (!provider) return; // pending-id race; will be re-attempted after fetch
     providerFormMode = 'edit';
     editingProvider = provider;
     pendingProviderId = null;
     pendingFormMode = null;
     if (window.App && window.App.router) {
       App.router.replaceSub(self.serializeState());
     }
     renderProvidersPanel();
   }
   ```

6. **NEW `enterCreateMode()` function** (replaces inline addBtn handler at line 330):
   ```js
   function enterCreateMode() {
     providerFormMode = 'add';
     editingProvider = null;
     pendingProviderId = null;
     pendingFormMode = null;
     if (window.App && window.App.router) {
       App.router.replaceSub(self.serializeState());
     }
     renderProvidersPanel();
   }
   ```

7. **NEW `_tryConsumePendingProvider()` method** on `self` (placed near `_setCategory`):
   ```js
   self._tryConsumePendingProvider = function () {
     if (!pendingProviderId && !pendingFormMode) return;
     if (pendingFormMode === 'add') {
       providerFormMode = 'add';
       editingProvider = null;
       pendingFormMode = null;
       renderProvidersPanel();
       return;
     }
     if (pendingFormMode === 'edit' && pendingProviderId) {
       var found = findProvider(pendingProviderId);
       if (found) {
         providerFormMode = 'edit';
         editingProvider = found;
         pendingProviderId = null;
         pendingFormMode = null;
         renderProvidersPanel();
       }
       // else: provider not in cache (unknown or fetch race not yet resolved);
       // _tryConsumePendingProvider re-fires after fetchProviders.then.
     }
   };
   ```

8. **`fetchProviders` integration**: in `.then` callback (line 343-345), after `providers = data; renderProviderList();` — actually, after this leg, `renderProviderList()` is gone (its work moved to providers-grid.js). The new flow: `providers = data; renderProvidersPanel(); self._tryConsumePendingProvider();`. The pending consumption fires after providers populate; if there's no pending state, the call is a no-op.

9. **Delete `renderProviderList()` function** (lines 352-403). Its work is now in `providers-grid.js`.

10. **Cancel button hash sync**: in `wireProviderFormEvents` cancelBtn handler (line 618-622), add `App.router.replaceSub('providers')` before/after `renderProvidersPanel()`:
    ```js
    cancelBtn.addEventListener('click', function () {
      providerFormMode = null;
      editingProvider = null;
      if (window.App && window.App.router) App.router.replaceSub('providers');
      renderProvidersPanel();
    });
    ```

11. **POST 201 URL upgrade**: in saveBtn handler's create branch (lines 686-705), after `editingProvider = created; providerFormMode = 'edit'`, add `App.router.replaceSub(self.serializeState())` so the URL upgrades from `#admin/providers/new` to `#admin/providers/{id}`:
    ```js
    .then(function (created) {
      showAdminFlash('Provider created');
      providerFormMode = 'edit';
      editingProvider = created;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderProviderForm(created);
    })
    ```

12. **`_setCategory` update** (admin.js:1014-1022 post-leg-01): when category changes (cross-category navigation), reset provider form state. Lines 1017-1018 already do `providerFormMode = null; editingProvider = null;`; add `pendingProviderId = null; pendingFormMode = null;` to keep state clean. The early-return short-circuit (when `currentCategory === sub`) STAYS — within-category sub-state changes are handled by `hydrateState`'s explicit `_tryConsumePendingProvider` call instead.

13. **`_refresh` update** (admin.js:1003-1008 post-leg-01): the `'providers'` branch currently does `if (currentCategory === 'providers' && !providerFormMode) fetchProviders();`. After leg 02, `fetchProviders()` returns its promise; chain `.then(function () { self._tryConsumePendingProvider(); })` so re-activation can pick up a stale pending id. (Note: `fetchProviders` itself already calls `_tryConsumePendingProvider` in its own `.then`, but `_refresh` may be called when there's no pending state — the chain is defensive.)

### Step 6: Update index.html

Add `<script src="/static/js/areas/admin/providers-grid.js"></script>` BEFORE `<script src="/static/js/areas/admin.js">` (after the existing `admin/system-page.js` line from leg 01). Order:
```html
<script src="/static/js/areas/admin/system-page.js"></script>
<script src="/static/js/areas/admin/providers-grid.js"></script>
<script src="/static/js/areas/admin.js"></script>
```

### Step 7: Test sweep

Bulk-update studio tests:

```bash
# Run these in the project root to sanity-check (do not auto-apply):
grep -rn 'agent-tile\|studio-page-header\|studio-page-title\|new-agent-btn' tests/
```

Apply selector + docstring renames per the Outputs section:
- `test_flow_agent_tile.py` (file name stays — it tests agent-grid behavior, not the canonical primitive):
  - Line 5 docstring: `.agent-tile-grid` → `.entity-tile-grid`
  - Line 6 docstring: `<button class="agent-tile">` → `<button class="entity-tile">`
  - Line 29 function docstring: `.agent-tile-grid` → `.entity-tile-grid` and `<button class="agent-tile">` → `<button class="entity-tile">`
  - Line 36 selector: `.agent-tile-grid` → `.entity-tile-grid`
  - Line 39 selector: `button.agent-tile` → `button.entity-tile`
  - Line 53 selector: `button.agent-tile` → `button.entity-tile`
  - Line 71 selector: `.agent-tile-grid` → `.entity-tile-grid`
  - Line 74 selector: `button.agent-tile` → `button.entity-tile`
  - Line 77 selector: `button.agent-tile` → `button.entity-tile`
  - Line 78 selector: `.agent-tile-name` → `.entity-tile-name`
  - Line 79 selector: `button.agent-tile` → `button.entity-tile`
  - Line 80 selector: `.agent-tile-name` → `.entity-tile-name`
  - (12 changes total — 3 docstring lines + 9 selector lines)
- `test_flow_keyboard.py`:
  - Line 109 docstring: `<button class="agent-tile">` → `<button class="entity-tile">`
  - Line 120 inline comment: `.agent-tile-grid` → `.entity-tile-grid`
  - Line 121 selector: `.agent-tile-grid` → `.entity-tile-grid`
- `test_flow_agent_tabs.py:43` selector: `button.agent-tile` → `button.entity-tile`.
- `test_flow_dirty_confirm.py`:
  - Line 51 selector: `button.agent-tile` → `button.entity-tile`
  - Line 137 selector: `.agent-tile-grid` → `.entity-tile-grid`

Update admin tests (enumerated lines):
- `test_flow_admin_navigation.py`: `.admin-title` → `.page-title` at lines 20, 27, 45, 47, 54, 56, 64, 78 (8 occurrences). Text assertions stay.
- `test_flow_hash_routing.py`: `.admin-title` → `.page-title` at lines 36, 41, 51, 217, 228, 239 (6 occurrences). Text assertions stay (already updated to "System"/"LLM Providers" in leg 01).
- `test_flow_provider_setup.py`:
  - Line 35: `[data-testid="add-provider-btn"]` → `[data-testid="new-provider-btn"]`
  - Line 47: `.admin-title` text "Edit Provider" — **STAYS** (editor uses `.admin-header` until leg 03)
  - Line 62: `.admin-provider-name` → `.entity-tile-name`
  - Line 63: `.admin-provider-badge` text "mock" — **STAYS** (badge composes both classes; selector still matches)
  - Line 57: `.admin-pf-cancel` — **STAYS** (leg 03 territory)
  - Line 60: `[data-testid="provider-card"]` — **STAYS** (testid preserved; element type changes div→button, selector via testid matches either)

### Step 8: Create test_flow_provider_grid.py

Create `tests/browser/test_flow_provider_grid.py`:

```python
"""Provider tile grid + page-header + hash routing tests for F6 leg 02.

Covers:
- LLM Providers page renders .page-header with title + "+ New Provider" button.
- Tile grid renders provider tiles with name + badge + url.
- Click tile navigates to #admin/providers/{id}; refresh preserves.
- "+ New Provider" navigates to #admin/providers/new; refresh preserves.
- Cancel from create returns to #admin/providers grid.
- Unknown provider id keeps URL stable; grid renders.
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_provider_grid_page_header(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".page-header")).to_be_visible(timeout=8000)
    expect(page.locator(".page-title")).to_have_text("LLM Providers")
    expect(page.locator('[data-testid="new-provider-btn"]')).to_be_visible()


@pytest.mark.browser
def test_provider_grid_empty_state(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".admin-provider-empty")).to_be_visible(timeout=8000)
    expect(page.locator(".admin-provider-empty")).to_contain_text("No providers configured")


@pytest.mark.browser
def test_provider_grid_renders_tiles(app_with_provider: SeededApp, page: Page) -> None:
    """The seed_mock_provider helper creates a provider named 'mock' (default)."""
    page.goto(f"{app_with_provider.base_url}#admin/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    import re
    expect(tile).to_have_class(re.compile(r"\bentity-tile\b"))
    expect(tile.locator(".entity-tile-name")).to_have_text("mock")
    # Type badge
    expect(tile.locator(".entity-tile-badge")).to_be_visible()
    # Provider type badge text
    expect(tile.locator(".entity-tile-badge")).to_have_text("mock")


@pytest.mark.browser
def test_new_provider_button_navigates_to_new_url(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator('[data-testid="new-provider-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="new-provider-btn"]').click()
    # Editor opens (existing form still uses .admin-title in leg 02).
    expect(page.locator(".admin-title")).to_have_text("Add Provider", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers/new"


@pytest.mark.browser
def test_create_url_refresh_preserves_create_mode(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".admin-title")).to_have_text("Add Provider", timeout=8000)
    page.reload()
    expect(page.locator(".admin-title")).to_have_text("Add Provider", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/providers/new"


@pytest.mark.browser
def test_tile_click_navigates_to_provider_detail(app_with_provider: SeededApp, page: Page) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    tile.click()
    expect(page.locator(".admin-title")).to_have_text("Edit Provider", timeout=5000)
    current_hash = page.evaluate("location.hash")
    assert current_hash.startswith("#admin/providers/"), f"expected /providers/<id>, got {current_hash}"
    # The id portion should not be 'new' (we clicked an existing tile)
    suffix = current_hash[len("#admin/providers/"):]
    assert suffix != "new"


@pytest.mark.browser
def test_provider_detail_url_refresh_preserves_editor(app_with_provider: SeededApp, page: Page) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    tile.click()
    expect(page.locator(".admin-title")).to_have_text("Edit Provider", timeout=5000)
    saved_hash = page.evaluate("location.hash")
    page.reload()
    expect(page.locator(".admin-title")).to_have_text("Edit Provider", timeout=8000)
    assert page.evaluate("location.hash") == saved_hash


@pytest.mark.browser
def test_cancel_from_create_returns_to_grid(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".admin-title")).to_have_text("Add Provider", timeout=8000)
    page.locator(".admin-pf-cancel").click()
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_unknown_provider_id_falls_back_to_grid(app_clean: str, page: Page) -> None:
    """Unknown id keeps URL stable; grid renders with no tile selected."""
    page.goto(f"{app_clean}#admin/providers/00000000-bogus-id-0000-000000000000")
    # No providers exist (app_clean), so the grid renders empty state and
    # the unknown id is held in pending-state pending future fetch resolution.
    # The page should NOT crash; either grid or empty-state should show.
    expect(page.locator(".page-header, .admin-pf-error").first).to_be_visible(timeout=8000)
    # URL is not silently overwritten — the pending-id is held
    current_hash = page.evaluate("location.hash")
    # Either the URL stays at the unknown id, or the F3 router replaceState
    # rewrites to #admin/providers (no editor open). Both are acceptable.
    assert current_hash in (
        "#admin/providers/00000000-bogus-id-0000-000000000000",
        "#admin/providers",
    )
```

Note: `app_with_provider` fixture confirmed at `tests/browser/conftest.py:223-226`; `SeededApp` dataclass at `tests/browser/seeders.py:20-29` has fields `base_url`, `provider_id`, `agent_name` (no `provider_name` field — the seeded provider is named "mock" by default per `seed_mock_provider(base_url, name="mock")` at seeders.py:32-36; tests use `"mock"` literally).

### Step 9: Verify

Run the full suite:

```bash
docker exec the-one pytest tests/ -m 'not browser' --timeout=120
docker exec the-one pytest -m browser tests/browser/ --timeout=120
```

Targets: ≥ 407 unit, ≥ 184 browser.

### Step 10: Update flight log

Append to `flight-log.md` under `## Leg Progress`:

```markdown
### 02-provider-tile-grid-and-page-headers
**Status**: landed
**Started**: <ISO timestamp>
**Completed**: <ISO timestamp>

#### Changes Made
- Breaking-renamed `.agent-tile`/`.agent-tile-name`/`.agent-tile-description`/`.agent-tile-meta`/`.agent-tile-grid` → `.entity-tile`/`.entity-tile-name`/`.entity-tile-description`/`.entity-tile-meta`/`.entity-tile-grid` in `components.css`. NO composition aliases.
- Breaking-renamed `.studio-page-header`/`.studio-page-title`/`.new-agent-btn` → `.page-header`/`.page-title`/`.new-entity-btn`; lifted from `studio.css` to `components.css`. Studio markup updated.
- NEW `.entity-tile-badge` canonical rule (top-right corner badge slot in `components.css`).
- NEW `App.admin.renderProvidersGrid` sub-module at `areas/admin/providers-grid.js`.
- LLM Providers page: page-header with title + `+ New Provider` button (`square-pen` icon, `data-testid="new-provider-btn"`); tile grid replaces row list.
- Hash routing: `#admin/providers/new` (create mode), `#admin/providers/{id}` (edit mode); refresh preserves on each.
- Hydrate-vs-fetch race protection via `_pendingProviderId` + `_tryConsumePendingProvider` (mirrors F5 leg 03's studio pattern).
- System page: `.admin-header` → `.page-header`, `.admin-title` → `.page-title`.
- Bulk-updated 5 studio test files for breaking renames; 3 admin test files for `.admin-title` → `.page-title` and selector renames.
- NEW `test_flow_provider_grid.py` with 8 tests.
- admin.js: 1037 → ~1010 LOC; admin.css: 134 → ~104 LOC; components.css: 634 → ~660 LOC; studio.css: 77 → ~65 LOC.

#### Test Results
- `pytest tests/`: <count> passed (target ≥ 407)
- `pytest -m browser tests/browser/`: <count> passed (target ≥ 184)

#### Notes
<runtime decisions, gotchas, deviations>
```

## Edge Cases

- **Empty providers list**: tile grid container renders the existing `.empty-state` message via `.empty-state.admin-provider-empty`. No tile elements emitted.
- **Hydrate fires before fetch resolves**: `_pendingProviderId` holds the id; `_tryConsumePendingProvider` runs after `fetchProviders().then`. If the id matches a known provider, the editor opens; if not, the id stays in pending state (no spurious render); if a subsequent fetch surfaces the id (e.g., a fresh provider was created in another tab), the consumer fires.
- **Unknown id (no race, just bogus URL)**: falls into the same pending-state path — the URL stays as the unknown id; the grid renders. No crash. Acceptable until HAT decides if a more aggressive cleanup is needed.
- **Provider deletion temporarily unavailable** (cross-leg dependency: leg 02 removes inline tile-row delete; leg 03 wires the editor Danger Zone): provider deletion works only via direct DB / API access during the leg-02 → leg-03 transition. **Acceptable** — no human user is interacting with the build between autonomous legs (the agentic-workflow defer-commit policy means no commit until all legs land). Documented in flight log.
- **Cancel from edit mode**: existing behavior at `_renderProviderFormImpl`'s cancelBtn returns to the grid. Add `App.router.replaceSub('providers')` so the URL syncs.
- **Test selector clash between studio and admin**: both areas now use `.entity-tile-grid` and `.entity-tile`. Tests must scope by `.area-studio` or `.area-admin` ancestor when the active panel could be ambiguous (in practice, only one panel has `.active` at a time, so tests typically navigate to the area first via `page.goto(f"{base}#area")` and then assert on `.entity-tile-grid`).
- **Visual snapshot drift**: the LLM Providers page changes from row-list to tile grid; snapshots will fail. Per user-global instructions, snapshots are gitignored and locally regenerated; not part of the regression net.
- **Existing `agent-item` class on studio tiles**: preserved as composition (`'entity-tile agent-item'`) so studio's `[data-testid="agent-item"]` selectors and `.agent-item.active` state class continue to work.
- **`.admin-provider-badge` selector continuity**: the badge span carries BOTH `.entity-tile-badge` (canonical position) AND `.admin-provider-badge` (admin-specific style + per-type color via `.admin-provider-badge--{type}`). Existing tests that select `.admin-provider-badge` continue to match.
- **`role="listbox"` on studio's grid stays**: studio's tile grid keeps `role="listbox"` (set in F5 leg 02); admin's grid uses `role="list"`. The roles differ because admin tiles aren't a single-selection set in the same way studio's are. Re-evaluate during HAT if screen-reader testing surfaces an issue.

## Files Affected

- `the_one/interfaces/web/static/css/components.css` — breaking renames (.agent-tile family → .entity-tile family); new .entity-tile-badge rule; new .entity-tile-grid rule; new .page-header/.page-title/.new-entity-btn rules. Net +20-25 LOC.
- `the_one/interfaces/web/static/css/studio.css` — delete .area-studio .studio-page-header/.studio-page-title/.new-agent-btn/.agent-tile-grid rules + comments. Net −10 to −15 LOC; target ≤ 65 LOC.
- `the_one/interfaces/web/static/css/admin.css` — delete .admin-provider-add-btn/.admin-provider-list/.admin-provider-card/.admin-provider-name/.admin-provider-actions/.admin-provider-edit-btn rules; split .admin-provider-delete-btn.admin-provider-delete-confirm out of the multi-selector. Net −30 LOC; target ≤ 104 LOC.
- `the_one/interfaces/web/static/js/areas/studio.js` — markup string renames (page-header / page-title / new-agent-btn → new-entity-btn / agent-tile-grid → entity-tile-grid / agent-tile / agent-tile-name / agent-tile-description / agent-tile-meta).
- `the_one/interfaces/web/static/js/areas/studio/stub-knowledge.js` — markup string renames.
- `the_one/interfaces/web/static/js/areas/studio/stub-tools.js` — markup string renames.
- `the_one/interfaces/web/static/js/areas/admin.js` — serializeState/hydrateState extension; new selectProvider + enterCreateMode + _tryConsumePendingProvider; renderProvidersPanel rewrite; renderProviderList deletion; cancelBtn + saveBtn URL sync. Net −20 LOC; target ≤ 1020 LOC.
- `the_one/interfaces/web/static/js/areas/admin/system-page.js` — `.admin-header`/`.admin-title` → `.page-header`/`.page-title`/`<h1>`.
- `the_one/interfaces/web/static/js/areas/admin/providers-grid.js` — NEW; ~80 LOC.
- `the_one/interfaces/web/static/index.html` — NEW `<script>` for providers-grid.js.
- `tests/browser/test_flow_agent_tile.py` — bulk selector renames (8 selectors).
- `tests/browser/test_flow_keyboard.py` — 1 selector rename.
- `tests/browser/test_flow_agent_tabs.py` — 1 selector rename.
- `tests/browser/test_flow_dirty_confirm.py` — 2 selector renames.
- `tests/browser/test_flow_admin_navigation.py` — `.admin-title` → `.page-title`.
- `tests/browser/test_flow_hash_routing.py` — `.admin-title` → `.page-title`.
- `tests/browser/test_flow_provider_setup.py` — 2 selector updates (line 35 testid, line 60 class), other selectors stay.
- `tests/browser/test_flow_provider_grid.py` — NEW; 8 tests.
- `the_one/interfaces/web/api.py` — UNCHANGED.
- `the_one/agents.md` — UNCHANGED (deferred to leg 05).
- `missions/04-ui-maturity/flights/06-administration-alignment/flight-log.md` — updated with leg progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (commit deferred to flight end per `/agentic-workflow` defer-commit policy):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/` ≥ 407 + `pytest -m browser tests/browser/` ≥ 184)
- [ ] Update `flight-log.md` with leg progress entry under `### 02-provider-tile-grid-and-page-headers`
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] **Do NOT** check off this leg in `flight.md` yet (per `/agentic-workflow` defer-commit policy)
- [ ] **Do NOT** commit (per `/agentic-workflow` defer-commit policy)
- [ ] Signal `[HANDOFF:review-needed]` only after all of the above are verified
