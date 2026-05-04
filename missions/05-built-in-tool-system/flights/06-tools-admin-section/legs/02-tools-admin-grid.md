# Leg: 02-tools-admin-grid

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Add a third top-level admin section ("Tools", peer to System and LLM Providers) and ship the admin grid view that lists all 19 built-in tools with their operator-set enabled state. Mirrors the providers-grid sub-module shape: orchestrator (`admin.js`) registers the new category and delegates rendering to `App.admin.renderToolsGrid` in a new `admin/tools-grid.js` sub-module. The grid renders one `.entity-tile` per tool with a category badge (derived from the tool's `Config` class), the tool name, the description, and an inline enabled-state toggle. Toggling a tile flips `enabled` via `PUT /api/tools/configs/{name}` (omitting `config` so L1's REPLACE-not-merge contract preserves the saved config). Per-tool tile click is **not yet wired** — that's L3 (which adds the per-tool editor + tile-click → `#admin/tools/{name}` deep-link routing). L2 ships the grid + the bare `#admin/tools` route only. No editor sub-module in this leg.

## Context

- **F6 mission goal — operator surface for the kill switch**: L0 stored `enabled`, L1 enforced + exposed it via API. L2 is the first user-visible touchpoint — operator opens Settings → Tools, sees 19 tiles, toggles one, the agent's next-create call drops the tool. UI loop closes here for the disable scenario; per-tool config editing is L3.
- **F6 Decision 1** (Tools is a peer section): the section nav grows from 2 entries (`System`, `LLM Providers`) to 3 (`System`, `LLM Providers`, `Tools`). `validIds` array at `admin.js:56` widens. `categories` array at `admin.js:78-81` widens. `serializeState` adds a `tools` branch. `hydrateState` accepts `tools` as a valid sub. State machine mirrors providers' but simpler in L2: NO editor sub-mode in this leg (no `toolFormMode`), so dirty-flag handling, beforeunload, and confirm-dialog gates do NOT apply yet — those land in L3 with the editor.
- **F6 Decision 7** (hash routing): `#admin/tools` lands the user on the grid. `#admin/tools/{name}` is reserved for L3's editor; L2 deliberately treats it as `#admin/tools` (silently strips the trailing segment) so a deep link from a future L3 user doesn't 404 the L2 deploy. Per-tile click in L2 does NOT navigate — only the inline toggle is interactive in this leg.
- **F6 Decision 12** (two-Reviewer-pass batching): L2 commits no docs. Tools admin section description in `agents.md` is L9.
- **L1 endpoint dependency**: L2 consumes `GET /api/tools/configs` (returns 19 entries each with `name`, `description`, `enabled`, `config`) and `PUT /api/tools/configs/{name}` (REPLACE-not-merge — L2 sends `{enabled: bool}` only; the L1 endpoint preserves omitted `config`). The L1 helper `_enrich_schema_with_markers` is NOT consumed by L2 (no schema rendering yet — that's L3 via `GET /api/tools/configs/{name}`).
- **Existing patterns to mirror precisely**:
  - `the_one/interfaces/web/static/js/areas/admin/providers-grid.js` (90 lines) — IIFE wrapping; `App.admin.renderProvidersGrid` global; `entity-tile-grid` container; `entity-tile.provider-tile` button per row; loading placeholder when input is `null`/`undefined`; empty-state message; click delegates via per-tile addEventListener.
  - `admin.js:271-280` — orchestrator's `App.admin.renderProvidersGrid(contentEl, providers, callbacks)` invocation pattern.
  - `admin.js:282-294` (`fetchProviders`) — fetch → populate → catch with inline error wording in the grid container.
  - `admin.css:63, 132-137` — `.admin-provider-badge--{type}` per-type background colour pattern. L2 mirrors this with `.admin-tool-badge--{category}`.
- **Tool category derivation** (no first-class `Tool.category` field exists): the L2 sub-module derives a category from each tool's `Config` class name (the API endpoint surfaces only `name`, `description`, `enabled`, `config` — NOT the Config class name, so the derivation must be a static mapping in JS). The 19 tools group into 4 categories per the F2-F5 design:
  - **filesystem** (9): read_file, write_file, edit_file, delete_file, move_file, mkdir, glob, grep, list_dir.
  - **execution** (5): shell, shell_session_start, shell_session_send, shell_session_close, shell_session_list.
  - **python** (1): python_exec.
  - **web** (4): http_request, fetch_url, download_file, web_search.
  Total = 19. The mapping lives as a `TOOL_CATEGORIES` const in `tools-grid.js`. Future flights that add tools must extend this mapping (lightweight; one line per tool).

## Inputs

- `the_one/interfaces/web/static/js/areas/admin.js:1-449` — orchestrator. Lines 56 (`validIds`), 78-81 (`categories`), 22 (`serializeState` else branch), 187-193 (`renderContent` dispatch), and the `renderProvidersPanel` shape at 197-280 are the touchpoints.
- `the_one/interfaces/web/static/js/areas/admin/providers-grid.js:1-91` — sub-module template to mirror.
- `the_one/interfaces/web/static/css/admin.css:55-150` — section-nav + provider-badge CSS to mirror for the tool-badge styling.
- `the_one/interfaces/web/static/css/components.css:300-360` — `.entity-tile` and family. L2 reuses without modification.
- `the_one/interfaces/web/static/css/tokens.css` — colour tokens. L2 introduces 4 new tokens for tool category badges (or reuses existing accent palette — see Decision below).
- `the_one/interfaces/web/api.py` (post-L1) — `GET /api/tools/configs` response shape: `[{name, description, enabled, config}, ...]`; `PUT /api/tools/configs/{name}` body shape: `{enabled?: bool, config?: dict}` (omitting `config` preserves the saved config).
- `Makefile:93` — `verify-serving` target's static-asset list (the `for f in admin.js admin/system-page.js admin/providers-grid.js ...; do` loop). L2 appends `admin/tools-grid.js` so `make rebuild` fails loudly if the file isn't served. (Reviewer flagged the original line ref as 95; corrected to 93.)

## Outputs

- `the_one/interfaces/web/static/js/areas/admin.js`:
  - `categories` array at line 78 → 3 entries: `[{id:'system'}, {id:'providers'}, {id:'tools', label:'Tools'}]`.
  - `validIds` array at line 56 → `['system', 'providers', 'tools']`.
  - `hydrateState`: add `tools/{name}` handling that strips the trailing segment and treats it as bare `tools` (L2 placeholder; L3 adds proper deep-link handling).
  - `serializeState`: add a `tools` branch returning `'tools'`. (L3 will widen this to include the editor mode.)
  - `renderContent` at line 187 → add `else if (currentCategory === 'tools') { renderToolsPanel(); }`.
  - New `renderToolsPanel()` function (mirrors `renderProvidersPanel` at line 197 but minimal — no editor branch, no dirty-flag, no beforeunload). Body: invoke `App.admin.renderToolsGrid(contentEl, toolConfigs, {onToggle: handleToolToggle})`; trigger `fetchToolConfigs()`.
  - New `fetchToolConfigs()` function (mirrors `fetchProviders` at line 282) — `fetch('/api/tools/configs').then(...).catch(...)` with the same stale-then guard (`if (currentCategory !== 'tools') return;`) and inline error wording in the grid container.
  - New `handleToolToggle(name, newEnabled)` function: PUT `/api/tools/configs/{name}` with body `{enabled: newEnabled}` (NO `config` key — L1's REPLACE contract preserves the saved config). On success, mutate the local cache (`toolConfigs.find(c => c.name === name).enabled = newEnabled`) and re-render via `populateToolGrid()`. On failure, revert UI state and show inline error.
  - New `populateToolGrid()` (mirrors `populateProviderGrid` at line 299) — re-render the grid from the cached `toolConfigs` array; bail when `currentCategory !== 'tools'`.
  - New top-level `var toolConfigs = null;` (mirrors `var providers = null;` at line 87).
  - New private accessor `Object.defineProperty(self, '_toolConfigs', {...})` for browser tests / debug. (Mirrors `_providers` if present; otherwise add only `_currentCategory` already exists — no new accessors required if browser tests poll the DOM.)
  - `self._refresh` at line 367 → add `else if (currentCategory === 'tools') { fetchToolConfigs(); }` so area-reactivate refreshes the grid.

- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` (new file, ~120 lines):
  - IIFE wrapper, `window.App.admin.renderToolsGrid` global.
  - `TOOL_CATEGORIES` const: `{ shell: 'execution', read_file: 'filesystem', ..., web_search: 'web' }` — full 19-entry map.
  - `renderToolsGrid(container, toolConfigs, callbacks)`:
    - Builds page header: `<h1>Tools</h1>` (NO "New Tool" button — the 19 tools are fixed; cannot add new ones from the UI).
    - Builds `entity-tile-grid` container with `role="listbox"` `aria-label="Built-in tools"`.
    - When `toolConfigs === null/undefined`: shows `Loading tools…` placeholder. Caller will re-invoke once fetch resolves.
    - When `toolConfigs.length === 0`: this branch is **defensive only** — the API guarantees 19 tools, so an empty array indicates a backend bug. Render an `API returned no tools.` empty-state. (Reviewer caught the prose typo "Flightlog:".)
    - Otherwise: render one tile per tool, sorted by category then name (deterministic visual order; tests rely on this).
  - Tile DOM (per-tool):
    ```html
    <div class="entity-tile tool-tile" data-testid="tool-card" data-name="{name}" role="listitem">
      <span class="entity-tile-badge admin-tool-badge admin-tool-badge--{category}">{category}</span>
      <span class="entity-tile-name">{name}</span>
      <span class="entity-tile-description">{description}</span>
      <label class="tool-enable-switch" title="{enabled ? 'Enabled' : 'Disabled'} for all agents">
        <input type="checkbox" {checked} data-testid="tool-toggle" data-name="{name}"
               aria-label="Enable {name}" />
        <span class="tool-enable-switch-track" aria-hidden="true"></span>
      </label>
    </div>
    ```
    - Tile is a `<div role="listitem">` not `<button>` (L2 has no tile-level click — only the toggle is interactive). L3 will swap to `<button>` when click-to-edit lands.
    - **Container `role="list"`** (NOT `role="listbox"` — listbox implies single-select picker semantics that don't fit a grid of independent toggles). Reviewer flagged the original `role="listbox"` as an ARIA contract violation; switched to `role="list"` + per-tile `role="listitem"`.
    - The toggle is a real `<input type=checkbox>` with explicit `aria-label="Enable {name}"` so screen readers announce the action even though the visible label is the entire surrounding tile (the `<label>` wraps only the toggle's track for click-target purposes; the screen-reader label is the explicit `aria-label`).
    - `<label>` wraps the input + track so clicking the track flips the checkbox (native HTML semantics — no JS needed for the label-click pattern). The label's `title` updates with state for hover diagnostics.
    - **Tile-level click forwards to the checkbox**: the `.entity-tile` selector inherits `cursor: pointer` from `components.css:305-323`. Without intervention, clicking anywhere on the tile reads as clickable but only the toggle does anything. L2 adds a tile-level click handler that, when the click target is NOT the input or label, calls `input.click()` (which dispatches `change` and toggles the state). This makes the entire tile a giant click target — UX-honest, matches the `cursor: pointer` affordance, and the whole tile becomes one click area for both pointer and keyboard users (the checkbox's own focus-ring still surfaces for keyboard).
  - Toggle wiring: per-tile `change` listener on the `<input>` calls `callbacks.onToggle(name, e.target.checked)`. The callback in `admin.js` does the PUT and re-render. On PUT failure, the orchestrator re-invokes `populateToolGrid()` with the unchanged cache, restoring the visual state. The orchestrator ALSO maintains a per-tool `inFlight: Set<string>` so a double-click on the same toggle while a PUT is pending is dropped (the second `onToggle` is a no-op until the first PUT resolves) — closes the optimistic-update race the Reviewer flagged.
  - Tests injection point: `callbacks.onToggle` is the only callback surface. Browser tests stub it; unit tests don't exist for this file (L2 is JS-only; tests live in L7's Playwright suite).

- `the_one/interfaces/web/static/css/admin.css` (new selectors appended at end):
  - `.area-admin .admin-tool-badge { /* same shape as .admin-provider-badge — font-mono, tiny, semibold, on-accent fg, 2px 8px padding, 4px radius, uppercase, 0.5px tracking */ }`.
  - `.area-admin .admin-tool-badge--filesystem { background: var(--badge-filesystem); }` — and similar for `--execution`, `--python`, `--web`.
  - `.area-admin .tool-tile { /* inherits from .entity-tile; positioning rules for the toggle slot */ }`.
  - `.area-admin .tool-enable-switch { /* iOS-style toggle: native checkbox visually-hidden, track + thumb rendered via spans/pseudo-elements */ }`.
  - **Token decision**: 4 new colour tokens added to BOTH theme blocks in `tokens.css` (verified the file uses `:root { ... }` for dark + `[data-theme="light"] { ... }` for light — same pattern providers' badges follow). Without the light-theme variant the badges would be invisible/unreadable in light mode (Reviewer flagged):
    - `--badge-filesystem`: a teal/cyan tone (filesystem is "data" — cool blue-green).
    - `--badge-execution`: a warm amber (execution is "active" — energy).
    - `--badge-python`: a python-blue (matches the language convention; ~`#306998`).
    - `--badge-web`: a magenta/violet (network/external — hot pink).
    - Light-theme variants land slightly lighter for contrast against the lighter background while still meeting WCAG 2.1 AA against `--fg-on-accent` text. Accessibility Reviewer at the batch pass will measure actual contrast.
  - L2 is the first leg in F6 with new CSS tokens. The pattern follows the F4 `--badge-{provider-type}` precedent at `tokens.css` lines 60-78 (dark) and 137-155 (light).

- `the_one/interfaces/web/static/css/tokens.css`:
  - 4 new tokens (above) appended in the `--badge-*` cluster.

- `Makefile:93`:
  - Append `admin/tools-grid.js` to the verify-serving asset list. The line currently iterates: `for f in admin.js admin/system-page.js admin/providers-grid.js admin/provider-editor.js admin/provider-models.js layout/section-nav.js;` — append `admin/tools-grid.js` immediately after `admin/provider-models.js`.

- `the_one/interfaces/web/templates/index.html` (or wherever the static script tags are loaded):
  - Add `<script src="/static/js/areas/admin/tools-grid.js"></script>` adjacent to the existing `providers-grid.js` `<script>`. **Verify the actual file location during implementation** — could be `templates/index.html`, `templates/base.html`, or inlined elsewhere.

- `tests/test_tools_admin_grid_assets.py` (new, lightweight asset-served check — 2 tests):
  - `test_tools_grid_js_served` — assert `GET /static/js/areas/admin/tools-grid.js` returns 200 and the body contains `App.admin.renderToolsGrid` (proves the file is served and the global is exported).
  - `test_admin_html_includes_tools_grid_script` — assert the admin/index page HTML contains the new `<script src="...tools-grid.js">` reference (proves the template change shipped). Use the same TestClient/ASGITransport pattern from `tests/test_db_api.py`.

## Acceptance Criteria

- [x] `the_one/interfaces/web/static/js/areas/admin.js`: `categories` array has 3 entries; `validIds` includes `'tools'`; `serializeState` returns `'tools'` when `currentCategory === 'tools'`; `hydrateState` accepts bare `'tools'` and (defensively) strips trailing segments from `'tools/<name>'`.
- [x] `renderContent` dispatches `'tools'` to `renderToolsPanel()`.
- [x] `renderToolsPanel()` invokes `App.admin.renderToolsGrid(contentEl, toolConfigs, {onToggle: handleToolToggle})` and triggers `fetchToolConfigs()`. NO editor branch, NO dirty flag, NO beforeunload registration.
- [x] `fetchToolConfigs()` calls `GET /api/tools/configs`, populates the `toolConfigs` cache, re-renders, and uses the same stale-then guard as `fetchProviders` (bail when `currentCategory !== 'tools'`).
- [x] `handleToolToggle(name, newEnabled)` PUTs `/api/tools/configs/{name}` with body `{enabled: newEnabled}` (NO `config` key — relies on L1's REPLACE-not-merge contract for omitted keys to preserve saved config). On success, mutates local cache and re-renders. On failure, re-renders from cache (revert) and surfaces an inline error.
- [x] `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` exports `App.admin.renderToolsGrid(container, toolConfigs, callbacks)` via IIFE.
- [x] `tools-grid.js` defines `TOOL_CATEGORIES` mapping all 19 tool names to one of `'filesystem' | 'execution' | 'python' | 'web'`.
- [x] Tiles render in deterministic order: sorted by name (alphabetic). The category badge gives visual grouping; alphabetic-by-name predictability beats grouped order for hunting a specific tool.
- [x] Each tile's DOM matches the spec'd shape: `.tool-tile` div with `role="listitem"`, `.admin-tool-badge--{category}` span, `.entity-tile-name` span, `.entity-tile-description` span, `.tool-enable-switch` label wrapping `<input type=checkbox data-testid="tool-toggle" aria-label="Enable {name}">`.
- [x] Grid container uses `role="list"` (NOT `listbox` — Reviewer flagged ARIA contract; tools are independent toggles, not a single-select picker).
- [x] Toggle is keyboard-operable (native checkbox semantics; clicking the label-wrapped track flips the input). `aria-label` on the input gives screen readers the action verb.
- [x] Toggle dispatches `callbacks.onToggle(name, newEnabled)` exactly once per state change.
- [x] **Tile-level click forwards to the inner checkbox** when the click target is NOT the toggle itself — makes the entire tile a click target so the inherited `cursor: pointer` from `.entity-tile` is honest.
- [x] **Per-tool in-flight gating**: while a PUT is pending for a tool, the input has the `disabled` attribute; second clicks during the in-flight window are dropped. CSS dims the track at `opacity: 0.5; cursor: wait;`.
- [x] CSS: 4 new `--badge-{filesystem,execution,python,web}` tokens in BOTH `[data-theme="dark"]` and `[data-theme="light"]` blocks of `tokens.css` (the file uses `[data-theme="dark"]` rather than the `:root` the spec referenced — see Deviation in flight log); `.admin-tool-badge` + 4 per-category background selectors in `admin.css`; `.tool-enable-switch` styling for the visual track + thumb (using `--border-strong` for the off-state — `--surface-muted` does NOT exist; Reviewer flagged). All new colours meet WCAG 2.1 AA contrast against `--fg-on-accent` (Accessibility Reviewer pass at the batch review will verify).
- [x] `Makefile`'s `verify-serving` static-asset loop includes `admin/tools-grid.js` so a stale image fails the check.
- [x] HTML template (verify location) includes the `<script src="/static/js/areas/admin/tools-grid.js">` tag in the same load-order block as `providers-grid.js`.
- [x] `tests/test_tools_admin_grid_assets.py` ships with 2 tests; both pass.
- [x] `make test-unit` is green (modulo the pre-existing CSS-token deselect).
- [x] `make rebuild` succeeds; `make verify-serving` confirms the new file is served (200).
- [x] No L1 file is touched (api.py / factory.py / repositories.py untouched). No L0 file is touched.
- [x] No editor sub-module file is created in L2. (`admin/tools-editor.js` is L3.)

## Verification Steps

```bash
# 1. Module structure — sub-module exposes the global
docker exec the-one cat the_one/interfaces/web/static/js/areas/admin/tools-grid.js | grep -c 'App.admin.renderToolsGrid'  # should be 1+

# 2. Category mapping — all 19 tools accounted for
docker exec the-one node -e "
const fs = require('fs');
const src = fs.readFileSync('the_one/interfaces/web/static/js/areas/admin/tools-grid.js', 'utf8');
// crude regex extract of the TOOL_CATEGORIES literal
const m = src.match(/TOOL_CATEGORIES\s*=\s*\{([^}]+)\}/s);
if (!m) { console.error('FAIL: TOOL_CATEGORIES literal not found'); process.exit(1); }
const entries = m[1].match(/'\w+'/g) || [];
const toolNames = entries.filter((_, i) => i % 2 === 0);  // every other token is a key
console.log('OK ' + toolNames.length + ' tools mapped: ' + toolNames.join(', '));
" || echo 'WARN node not available; visually inspect the const'

# 3. admin.js wiring — categories has 3 entries
docker exec the-one grep -c "id: 'tools'" the_one/interfaces/web/static/js/areas/admin.js  # should be 1+
docker exec the-one grep -c "renderToolsPanel" the_one/interfaces/web/static/js/areas/admin.js  # should be 2+ (definition + dispatch)

# 4. CSS tokens
docker exec the-one grep -c '\\-\\-badge-filesystem\\|\\-\\-badge-execution\\|\\-\\-badge-python\\|\\-\\-badge-web' the_one/interfaces/web/static/css/tokens.css  # should be 4

# 5. Asset is served
make rebuild  # destructive but required: image rebuild needed for new static file pickup
make verify-serving  # the loop now includes tools-grid.js — should print "✓ admin/tools-grid.js served (200)"

# 6. Live smoke — open in a browser:
#    http://localhost:8484/#admin/tools
#    Expect: 19 tiles in the grid, each with a category badge, all toggles ON.
#    Toggle one off, refresh page, toggle persists.

# 7. Targeted test runs
docker exec the-one pytest tests/test_tools_admin_grid_assets.py -x -q

# 8. Full unit suite (no JS unit tests; full suite is regression-only here)
docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# 9. Lint
docker exec the-one ruff check tests/test_tools_admin_grid_assets.py
```

## Implementation Guidance

1. **Add the category** — `the_one/interfaces/web/static/js/areas/admin.js`:

   ```javascript
   // line 78
   var categories = [
     { id: 'system', label: 'System' },
     { id: 'providers', label: 'LLM Providers' },
     { id: 'tools', label: 'Tools' }
   ];

   // line 56
   var validIds = ['system', 'providers', 'tools'];
   ```

2. **Hydrate / serialize** — `the_one/interfaces/web/static/js/areas/admin.js`:

   ```javascript
   // serializeState — add a tools branch (line 22 area)
   if (this._currentCategory === 'tools') return 'tools';

   // hydrateState — handle 'tools' and 'tools/<name>' (line 41 area)
   if (origSub === 'tools' || (origSub && origSub.indexOf('tools/') === 0)) {
     // L2: silently strip the trailing segment; L3 wires the editor.
     sub = 'tools';
   }
   ```

3. **State + functions** — `the_one/interfaces/web/static/js/areas/admin.js`:

   ```javascript
   // After the provider state block (line 91 area)
   var toolConfigs = null;  // null until first fetch resolves

   // After populateProviderGrid (line 312 area)
   function renderToolsPanel() {
     App.admin.renderToolsGrid(contentEl, toolConfigs, {
       onToggle: handleToolToggle
     });
     fetchToolConfigs();
   }

   // Per-tool in-flight PUT tracker — second click while a PUT is pending
   // is dropped (the toggle is also disabled in CSS via the `disabled` attr).
   // Closes the optimistic-update double-click race the Reviewer flagged.
   var toolsInFlight = Object.create(null);

   function fetchToolConfigs() {
     return fetch('/api/tools/configs')
       .then(function (r) { return r.json(); })
       .then(function (data) {
         // Stale-then guard at cache-write: if the operator switched away
         // mid-fetch, do not clobber the cache.
         if (currentCategory !== 'tools') return;
         toolConfigs = data;
         populateToolGrid();
       })
       .catch(function () {
         if (currentCategory !== 'tools') return;
         var gridEl = contentEl.querySelector('.entity-tile-grid');
         if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load tools.</div>';
       });
   }

   function populateToolGrid() {
     // Stale-then guard: bail when no longer on tools (mirrors providers).
     if (currentCategory !== 'tools') return;
     App.admin.renderToolsGrid(contentEl, toolConfigs, {
       onToggle: handleToolToggle,
       inFlight: toolsInFlight  // sub-module reads this to render disabled
     });
   }

   function handleToolToggle(name, newEnabled) {
     // Drop second click while a PUT is pending for this tool.
     if (toolsInFlight[name]) return;

     // Optimistic update: flip cache, re-render, PUT. Revert on failure.
     var idx = -1;
     for (var i = 0; i < toolConfigs.length; i++) {
       if (toolConfigs[i].name === name) { idx = i; break; }
     }
     if (idx === -1) return;
     var prev = toolConfigs[idx].enabled;
     toolConfigs[idx].enabled = newEnabled;
     toolsInFlight[name] = true;
     populateToolGrid();

     fetch('/api/tools/configs/' + encodeURIComponent(name), {
       method: 'PUT',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({ enabled: newEnabled })  // omit config — L1 REPLACE preserves
     }).then(function (r) {
       if (!r.ok) throw new Error('PUT failed: ' + r.status);
     }).catch(function () {
       // Revert and surface the error via the existing admin wrapper.
       toolConfigs[idx].enabled = prev;
       showAdminFlash('Failed to update ' + name + '.', true);
     }).then(function () {
       // Always clear in-flight + re-render (success path also re-renders
       // to clear the `disabled` attr on the toggle).
       delete toolsInFlight[name];
       populateToolGrid();
     });
   }
   ```

4. **renderContent dispatch** — line 187 area:

   ```javascript
   function renderContent() {
     if (currentCategory === 'system') {
       App.admin.renderSystemPage(contentEl);
     } else if (currentCategory === 'providers') {
       renderProvidersPanel();
     } else if (currentCategory === 'tools') {
       renderToolsPanel();
     }
   }
   ```

5. **Refresh hook** — `self._refresh` at line 367:

   ```javascript
   self._refresh = function () {
     if (currentCategory === 'system') {
       App.admin.renderSystemPage(contentEl);
     } else if (currentCategory === 'providers' && !providerFormMode) {
       fetchProviders().then(function () {
         self._tryConsumePendingProvider();
       });
     } else if (currentCategory === 'tools') {
       fetchToolConfigs();
     }
   };
   ```

6. **New sub-module** — `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` (mirror providers-grid.js shape):

   ```javascript
   (function () {
     'use strict';
     window.App = window.App || {};
     window.App.admin = window.App.admin || {};

     // Map of tool name → category badge slug. The tool's Config class
     // determines its category (FilesystemConfig → filesystem, etc.);
     // the API endpoint surfaces only `name`/`description`/`enabled`/`config`,
     // not the Config class name, so the mapping is duplicated here.
     // Future flights adding tools must extend this; the L8 verification
     // sweep will fail loudly on a missing entry (defensive `unknown` badge).
     var TOOL_CATEGORIES = {
       // filesystem (9)
       read_file: 'filesystem',
       write_file: 'filesystem',
       edit_file: 'filesystem',
       delete_file: 'filesystem',
       move_file: 'filesystem',
       mkdir: 'filesystem',
       glob: 'filesystem',
       grep: 'filesystem',
       list_dir: 'filesystem',
       // execution (5)
       shell: 'execution',
       shell_session_start: 'execution',
       shell_session_send: 'execution',
       shell_session_close: 'execution',
       shell_session_list: 'execution',
       // python (1)
       python_exec: 'python',
       // web (4)
       http_request: 'web',
       fetch_url: 'web',
       download_file: 'web',
       web_search: 'web'
     };

     function renderToolsGrid(container, toolConfigs, callbacks) {
       callbacks = callbacks || {};
       var onToggle = callbacks.onToggle || function () {};
       var inFlight = callbacks.inFlight || Object.create(null);
       var escapeHtml = window.App.escapeHtml;
       var escapeAttr = window.App.escapeAttr;

       container.innerHTML =
         '<div class="page-header">' +
           '<h1 class="page-title">Tools</h1>' +
         '</div>' +
         '<div class="entity-tile-grid" role="list" aria-label="Built-in tools">' +
           '<div class="admin-loading">Loading tools…</div>' +
         '</div>';

       var gridEl = container.querySelector('.entity-tile-grid');
       if (toolConfigs === null || toolConfigs === undefined) return;
       if (toolConfigs.length === 0) {
         gridEl.innerHTML = '<div class="empty-state">API returned no tools.</div>';
         return;
       }

       // Sort by name (alphabetic). The category badge gives operators the
       // visual grouping; alphabetic-by-name makes hunting a specific tool
       // by name predictable. (Reviewer Q1 — picked name-only sort.)
       var sorted = toolConfigs.slice().sort(function (a, b) {
         return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
       });

       var html = '';
       for (var i = 0; i < sorted.length; i++) {
         var t = sorted[i];
         var cat = TOOL_CATEGORIES[t.name] || 'unknown';
         var checkedAttr = t.enabled ? 'checked' : '';
         var disabledAttr = inFlight[t.name] ? 'disabled' : '';
         var titleText = t.enabled ? 'Enabled for all agents' : 'Disabled for all agents';
         html +=
           '<div class="entity-tile tool-tile" data-testid="tool-card" ' +
                'data-name="' + escapeAttr(t.name) + '" role="listitem">' +
             '<span class="entity-tile-badge admin-tool-badge admin-tool-badge--' +
               escapeAttr(cat) + '">' + escapeHtml(cat) + '</span>' +
             '<span class="entity-tile-name">' + escapeHtml(t.name) + '</span>' +
             '<span class="entity-tile-description">' + escapeHtml(t.description) + '</span>' +
             '<label class="tool-enable-switch" title="' + escapeAttr(titleText) + '">' +
               '<input type="checkbox" ' + checkedAttr + ' ' + disabledAttr + ' ' +
                      'data-testid="tool-toggle" data-name="' + escapeAttr(t.name) + '" ' +
                      'aria-label="Enable ' + escapeAttr(t.name) + '" />' +
               '<span class="tool-enable-switch-track" aria-hidden="true"></span>' +
             '</label>' +
           '</div>';
       }
       gridEl.innerHTML = html;

       // Per-tile toggle wiring (change event)
       var toggles = gridEl.querySelectorAll('input[data-testid="tool-toggle"]');
       for (var j = 0; j < toggles.length; j++) {
         (function (input) {
           input.addEventListener('change', function () {
             onToggle(input.dataset.name, input.checked);
           });
         })(toggles[j]);
       }

       // Tile-level click forwards to the inner checkbox UNLESS the click
       // originated on the input/label/track itself (which already handles
       // the toggle natively). Makes the entire tile a click target,
       // matching the cursor:pointer affordance the .entity-tile selector
       // already implies.
       var tiles = gridEl.querySelectorAll('.tool-tile');
       for (var k = 0; k < tiles.length; k++) {
         (function (tileEl) {
           tileEl.addEventListener('click', function (e) {
             // Bail if the click was on the toggle's interactive surface.
             if (e.target.closest('.tool-enable-switch')) return;
             var input = tileEl.querySelector('input[data-testid="tool-toggle"]');
             if (input && !input.disabled) input.click();
           });
         })(tiles[k]);
       }
     }

     window.App.admin.renderToolsGrid = renderToolsGrid;
   })();
   ```

7. **CSS additions** — `tokens.css` (BOTH theme blocks):

   ```css
   /* In :root { ... } (dark theme; lines 26-90 area, after the existing --badge-* tokens) */
   --badge-filesystem: #008b8b;  /* dark cyan */
   --badge-execution: #b8860b;   /* dark goldenrod */
   --badge-python: #306998;      /* python blue */
   --badge-web: #c71585;         /* medium violet red */

   /* In [data-theme="light"] { ... } (lines 105-160 area) — slightly lighter for
      light-mode contrast while preserving 4.5:1 against white text. */
   --badge-filesystem: #0e8e8e;
   --badge-execution: #c5912a;
   --badge-python: #4178a8;
   --badge-web: #d63a93;
   ```

   `admin.css` (append):

   ```css
   .area-admin .admin-tool-badge {
     font-family: var(--font-family-mono);
     font-size: var(--font-size-tiny);
     font-weight: var(--font-weight-semibold);
     color: var(--fg-on-accent);
     padding: 2px 8px;
     border-radius: 4px;
     flex-shrink: 0;
     text-transform: uppercase;
     letter-spacing: 0.5px;
   }
   .area-admin .admin-tool-badge--filesystem { background: var(--badge-filesystem); }
   .area-admin .admin-tool-badge--execution { background: var(--badge-execution); }
   .area-admin .admin-tool-badge--python { background: var(--badge-python); }
   .area-admin .admin-tool-badge--web { background: var(--badge-web); }
   .area-admin .admin-tool-badge--unknown { background: var(--badge-unknown); }

   /* L2 tile is a <div>, not <button>. Override the .entity-tile defaults
      so the tile reads as a click-target (cursor + hover accent stay so the
      tile-level click forwards to the inner checkbox). The inner toggle's
      focus-visible ring is the keyboard affordance; nothing else changes. */
   .area-admin .tool-tile {
     position: relative;
     /* Reserve space at bottom-right for the toggle so it doesn't collide
        with .entity-tile-badge (which is hard-coded top:8px right:8px in
        components.css:363-374). The toggle sits at bottom-right; description
        text wraps above it. */
     padding-bottom: 36px;
   }
   .area-admin .tool-enable-switch {
     position: absolute;
     bottom: 12px;
     right: 12px;
     width: 36px;
     height: 20px;
     cursor: pointer;
   }
   .area-admin .tool-enable-switch input[type="checkbox"] {
     /* Visually-hidden but keyboard-operable. position:absolute removes from
        layout; opacity:0 hides without breaking screen-reader access. */
     position: absolute;
     opacity: 0;
     width: 100%;
     height: 100%;
     margin: 0;
     cursor: pointer;
     /* Z-index above the track so the click reliably hits the input first
        (avoids label-click-through quirks in older WebKit). */
     z-index: 1;
   }
   .area-admin .tool-enable-switch-track {
     display: block;
     width: 36px;
     height: 20px;
     /* Off-state track uses --border-strong (an established token) for the
        OFF visual; reviewer confirmed --surface-muted is NOT defined. */
     background: var(--border-strong);
     border-radius: 10px;
     position: relative;
     transition: background 0.2s ease;
     /* Track must NOT eat the click — the wrapping <label> + <input> handle it. */
     pointer-events: none;
   }
   .area-admin .tool-enable-switch-track::after {
     content: '';
     position: absolute;
     top: 2px;
     left: 2px;
     width: 16px;
     height: 16px;
     background: var(--fg-on-accent);
     border-radius: 50%;
     transition: transform 0.2s ease;
   }
   .area-admin .tool-enable-switch input[type="checkbox"]:checked + .tool-enable-switch-track {
     background: var(--accent);
   }
   .area-admin .tool-enable-switch input[type="checkbox"]:checked + .tool-enable-switch-track::after {
     transform: translateX(16px);
   }
   .area-admin .tool-enable-switch input[type="checkbox"]:focus-visible + .tool-enable-switch-track {
     outline: 2px solid var(--accent);
     outline-offset: 2px;
   }
   /* Disabled state during in-flight PUT (orchestrator sets disabled attr) */
   .area-admin .tool-enable-switch input[type="checkbox"]:disabled + .tool-enable-switch-track {
     opacity: 0.5;
     cursor: wait;
   }
   ```

   - All referenced tokens are confirmed to exist: `--accent`, `--fg-on-accent`, `--font-family-mono`, `--font-size-tiny`, `--font-weight-semibold`, `--border-strong`, `--badge-unknown`. The Reviewer's flagged `--surface-muted` (which does NOT exist) was replaced with `--border-strong`.

8. **Makefile** — line 93, append `admin/tools-grid.js` to the loop (after `admin/provider-models.js`):

   ```makefile
   @for f in admin.js admin/system-page.js admin/providers-grid.js admin/provider-editor.js admin/provider-models.js admin/tools-grid.js layout/section-nav.js; do \
     # ... existing loop body unchanged
   done
   ```

   **Dirty-gate widening note for L3**: at admin.js:166-173, the existing setCategory dirty-gate reads `var inEditor = currentCategory === 'providers' && providerFormMode;`. L2 does NOT widen this (no editor in L2 — no dirty flag, no beforeunload). L3 will need to extend the gate to `(... || (currentCategory === 'tools' && toolFormMode))`. Add a one-line `// TODO L3: widen for tools editor` comment in admin.js at that location so L3's implementer doesn't miss it.

9. **HTML template** — `the_one/interfaces/web/static/index.html:47` carries `<script src="/static/js/areas/admin/providers-grid.js"></script>`. Insert `<script src="/static/js/areas/admin/tools-grid.js"></script>` on the line immediately after it. (Verified location during design review.)

10. **Asset-served test** — `tests/test_tools_admin_grid_assets.py`. Use the prod app's STATIC_DIR resolution (`Path(__file__).parent / "static"` from `the_one/interfaces/web/app.py:77`) so the fixture works regardless of CWD. The prod `/` route is in `app.py`, NOT `api.py`'s router; serve `/static/index.html` directly through the StaticFiles mount instead of trying to hit `/`:

    ```python
    """Asset wiring for the F6 L2 tools admin grid."""
    from __future__ import annotations
    from pathlib import Path
    from unittest.mock import patch
    import aiosqlite
    import pytest
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from httpx import ASGITransport, AsyncClient
    from the_one.db.schema import ensure_schema
    from the_one.interfaces.web.api import router

    # Resolve the prod static dir from the package source — independent of CWD.
    import the_one.interfaces.web.app as web_app  # noqa: E402
    _STATIC_DIR = Path(web_app.__file__).parent / "static"


    @pytest.fixture
    async def client(tmp_path):
        db_path = tmp_path / "test.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)
        with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
            test_app = FastAPI()
            test_app.include_router(router)
            test_app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                yield c
        await conn.close()


    class TestToolsGridAssets:
        async def test_tools_grid_js_served(self, client: AsyncClient) -> None:
            resp = await client.get("/static/js/areas/admin/tools-grid.js")
            assert resp.status_code == 200
            assert "App.admin.renderToolsGrid" in resp.text

        async def test_index_html_includes_tools_grid_script(self, client: AsyncClient) -> None:
            # The SPA shell lives at /static/index.html; the prod / route serves it
            # via FileResponse, but the static mount serves the same bytes here.
            resp = await client.get("/static/index.html")
            assert resp.status_code == 200
            assert "tools-grid.js" in resp.text
    ```

11. **Run the verification block** above; the `make rebuild` step is intentionally listed — L2 introduces a new static file, and the dev container only picks it up after rebuild (uvicorn `--reload` watches Python files, not the static tree).

## Edge Cases

- **Toggle race**: operator double-clicks the toggle quickly. The `change` event fires once per `checked` flip; the optimistic update + revert pattern handles back-to-back clicks correctly (each click PUTs; the second response — when it lands — represents the operator's most recent intent). Acceptable.
- **Network-fail PUT during optimistic update**: cache reverts; flash surfaces error; the toggle visually flips back. Operator is not silently misled.
- **Stale-then guard during fetch**: same pattern as `fetchProviders`. If the operator switches to System mid-fetch, the `populateToolGrid` call bails on `currentCategory !== 'tools'`. Without this, the toolConfigs cache could clobber the system page's content div.
- **Empty `toolConfigs` from API**: defensive empty-state. Should never happen (API guarantees 19 entries), but the empty-state covers a hypothetical backend regression.
- **Unknown tool in API response** (future tool added without the JS map updated): `TOOL_CATEGORIES[name] || 'unknown'` falls back to the `--badge-unknown` slug. Tile still renders; operator sees an `UNKNOWN` badge — visible signal that the JS map needs updating.
- **`#admin/tools/{name}` deep link in L2**: the L2 `hydrateState` strips the trailing segment and lands the user on the bare grid. Browser tests for L7 must skip the deep-link assertion until L3.
- **Section-nav click while already on tools**: noop (handled by the existing `setCategory` short-circuit on same-category clicks).
- **`make rebuild` requirement**: the new static file must be baked into the image. uvicorn `--reload` does NOT watch the static tree (verified during F4). Document in the leg's verification block (step 5).
- **CSS contrast**: the proposed badge colours (dark cyan, dark goldenrod, python blue, medium violet red) are all darker than the OKLCH midpoint and should clear 4.5:1 against `--fg-on-accent` (which is typically white). The Accessibility Reviewer at the batch pass will verify with actual contrast measurements; if any badge fails, swap to a darker shade.
- **Token reuse vs new tokens**: an alternative is reusing the existing `--badge-{provider-type}` tokens (5 colours already defined). Rejected because the badge meanings differ — a `web` tool badge meaning "web category" overlapping visually with a `web`-typed LLM provider would be confusing.
- **L1 endpoint guarantees the description field**: L2 renders `t.description` directly. Verified against L1 leg's `list_tool_configs` route which always includes `description`.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin.js` — orchestrator: 3-entry categories, validIds, hydrate/serialize, dispatch, state vars, 4 new functions.
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` — new sub-module (~120 LoC).
- `the_one/interfaces/web/static/css/tokens.css` — 4 new `--badge-{filesystem,execution,python,web}` tokens.
- `the_one/interfaces/web/static/css/admin.css` — `.admin-tool-badge` family + `.tool-enable-switch` family.
- `Makefile` — `verify-serving` loop appended with `admin/tools-grid.js`.
- `the_one/interfaces/web/static/index.html` — line 47 area; insert `<script src="/static/js/areas/admin/tools-grid.js"></script>` immediately AFTER the existing `providers-grid.js` script tag.
- `tests/test_tools_admin_grid_assets.py` — new (2 tests).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test-unit` green (modulo CSS-token deselect)
- [ ] `make rebuild` succeeds; `make verify-serving` shows tools-grid.js as 200
- [ ] Live smoke (manual): browser opens `#admin/tools` → 19 tiles render → toggle persists across reload
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
