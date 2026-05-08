# Leg: 05-settings-nav-and-grid

**Status**: completed
**Flight**: [Encrypted MCP Source Persistence + Settings Page](../flight.md)

## Objective

Land the Settings sidebar entry "MCP Servers" and the MCP-source tile grid sub-module, mirroring the LLM Providers section's structural shape. After L5, an operator can navigate to `#admin/mcp-sources`, see a tile grid of registered MCP sources (or an empty-canvas CTA when none exist), and click a tile to land on a (yet-unbuilt) editor route — the L6 editor renders the actual editor surface, but L5 stages the URL routing, the closure-mirror state slots, and the navigation lifecycle hooks so L6 only adds the editor sub-module.

## Context

The flight spec (`flight.md:129`) enumerates six closure-mirror parallel-extension points (a–f) plus the new sub-module file and a browser test. The admin orchestrator at `the_one/interfaces/web/static/js/areas/admin.js` hosts ALL of admin's state in `init()` closure-locals exposed via `Object.defineProperty` getter/setter pairs to the area's `self`. Adding a new category is NOT a single-point change — every state slot the providers and tools branches use has a parallel slot for MCP sources, every reset block (`doSetCategory`, `_setCategory`) wipes it, every URL serializer/hydrator has a branch for it, and every consumer flow has a `_tryConsumePendingMcpSource` companion.

Critical invariants from the existing code:

- **Sub-state changes within the same category do NOT trigger `_setCategory`'s reset/re-render** because `currentCategory` is unchanged. `hydrateState` therefore fires `_tryConsumePendingProvider` (and `_tryConsumePendingTool`) UNCONDITIONALLY at the end. L5 adds `_tryConsumePendingMcpSource` to that unconditional fire-list.
- **Stale-then guard at `populateProviderGrid` / `populateToolGrid`**: a `fetch().then(populate)` that resolves AFTER the user has navigated away (e.g., to a different category mid-fetch) would clobber the new category's content. The guard is `if (currentCategory !== 'providers') return`. L5 mirrors this in `populateMcpSourcesGrid`.
- **`set()` getter on the closure-local var** vs a direct re-assignment: `Object.defineProperty(self, '_pendingMcpSourceId', { get, set })` allows external code (this area's own functions accessed via `self`) to mutate the closure local through `self._pendingMcpSourceId = X`. The pattern is duplicated for every closure-local with cross-function lifetime — L5 follows it for all 5 new MCP state slots.
- **Beforeunload listener at admin.js:185-191** registers ONCE at init. The closure `dirty` flag is the gate; it's already shared with the (yet-unbuilt) MCP editor's onDirtyChange callback in L6. L5 does NOT modify the listener.
- **Dirty gate in `setCategory` at admin.js:218-225** checks `(currentCategory === 'providers' && providerFormMode) || (currentCategory === 'tools' && toolFormMode)` to gate the confirmDialog. L5 extends this to include `(currentCategory === 'mcp-sources' && mcpSourceFormMode)` — even though the editor is L6, the gate must be in place when L5 lands so a future L6 lands a working dirty-flag flow without orphan-state.

L5 does NOT touch:
- The L6 editor sub-module (that lands separately)
- The L6 transport-aware form fields, sensitive checkbox, OAuth client config section, Danger Zone delete
- The dirty-flag onDirtyChange bridge (the closure-local `dirty` already exists; the bridge wires up in L6's editor mount)
- Any backend code (L1-L4 supplied the API surface; L5 is pure frontend)

## Inputs

- L1 + L2 + L3 + L4 have landed
- `the_one/interfaces/web/static/js/areas/admin.js` (701 lines total) — the orchestrator. Anchor points by line number (verify with `wc -l` and `grep -n` before edits — the file is post-L4-stable, line numbers should hold):
  - `serializeState` at lines 8–33
  - `hydrateState` at lines 34–105
  - `validIds` array at line 83
  - `init` opens at line 107
  - `categories` array at lines 108–115
  - Provider state declarations (`var providers = null;` etc.) at lines 120–125
  - Tools state declarations at lines 140–151
  - `dirty` declaration at line 133
  - Beforeunload listener at lines 185–191
  - `doSetCategory` reset block at lines 199–213
  - `setCategory` dirty gate at lines 214–225
  - `renderSectionNav` invocation at lines 226–232
  - `renderContent` dispatch at lines 240–248
  - `renderProvidersPanel` at lines 252–335 (delegates to grid + editor sub-modules)
  - `fetchProviders` at lines 337–349 (note the `populateProviderGrid` + `_tryConsumePendingProvider` post-fetch fire pattern)
  - `populateProviderGrid` (stale-then guard) at lines 354–367
  - `selectProvider` / `enterCreateMode` at lines 369–391
  - `findProvider` at lines 393–399
  - `_refresh` at lines 581–595
  - `Object.defineProperty` slots at lines 596–639
  - `_setCategory` at lines 640–654
  - `_tryConsumePendingProvider` at lines 655–677
  - `_tryConsumePendingTool` at lines 678–686
  - `Init` block (calls `fetchProviderTypes(); renderContent();`) at lines 688–691
- `the_one/interfaces/web/static/js/areas/admin/providers-grid.js` (100 lines) — the structural template for `mcp-servers-grid.js`. Mirrors: `KNOWN_BADGE_TYPES` constant; `renderProvidersGrid(container, providers, callbacks)` signature; loading state when `providers === null`; empty-canvas CTA when `providers.length === 0`; tile loop with `data-testid="provider-card"`, `data-id`, `aria-selected`, three spans (badge / name / meta).
- `the_one/interfaces/web/static/index.html` — the script registration list. Lines 47–53 register existing admin sub-modules. L5 inserts `<script src="/static/js/areas/admin/mcp-servers-grid.js"></script>`.
- `tests/browser/test_flow_admin_navigation.py` — pattern reference for section-nav + hash-routing tests. Anchors:
  - `test_admin_redirect_root_to_system` (line 18)
  - `test_admin_legacy_general_redirects_to_system` (line 25)
  - `test_admin_section_nav_renders_three_sections` (line 47)
  - `test_admin_section_nav_click_changes_url` (line 66)
  - `test_admin_refresh_preserves_section` (line 75)
  - `test_admin_section_nav_keyboard` (line 84)
- `tests/browser/test_flow_admin_tools_grid.py` — pattern for grid-empty-state and grid-tile interaction tests. Implementer: regrep before edits.
- `tests/browser/conftest.py` — `app_clean` fixture and seeders that the tests use. Implementer: re-read for fixture wiring.

## Outputs

- `the_one/interfaces/web/static/js/areas/admin.js` extended at the six enumerated parallel-extension points + four supporting points:
  - (a) `var mcpSources = null;`, `var mcpSourceFormMode = null;`, `var editingMcpSource = null;`, `var pendingMcpSourceId = null;`, `var pendingMcpSourceFormMode = null;` — five new state slots
  - (b) Four new `Object.defineProperty(self, '_<name>', ...)` getter/setter exposures (the `mcpSources` cache var is closure-private, mirroring `providers` / `toolConfigs`)
  - (c) Reset blocks in BOTH `doSetCategory` AND `_setCategory` extended to wipe the five new slots
  - (d) `_tryConsumePendingMcpSource` function added (mirrors `_tryConsumePendingProvider`)
  - (e) `hydrateState` parsing branch for `mcp-sources/new` and `mcp-sources/{id}`
  - (f) `serializeState` branch for the three sub-states (`mcp-sources`, `mcp-sources/new`, `mcp-sources/{id}`)
  - Plus: `categories` array entry, `validIds` array entry, `renderContent` dispatch branch, `renderMcpSourcesPanel` function, `fetchMcpSources`, `populateMcpSourcesGrid` (with stale-then guard), `selectMcpSource`, `enterCreateMcpSourceMode`, `findMcpSource`, `_refresh` branch, `setCategory` dirty-gate extension, unconditional `_tryConsumePendingMcpSource` fire in `hydrateState`
- `the_one/interfaces/web/static/js/areas/admin/mcp-servers-grid.js` (NEW, ~110 lines) — the grid sub-module mirroring `providers-grid.js`
- `the_one/interfaces/web/static/index.html` — adds one `<script>` tag for the new sub-module
- `tests/browser/test_flow_admin_mcp_navigation.py` (NEW) — Playwright tests covering: section-nav now lists 4 items (General, LLM Providers, Built-in Tools, MCP Servers); section-nav click on "MCP Servers" updates URL to `#admin/mcp-sources`; direct-load of `#admin/mcp-sources` lands on grid; direct-load of `#admin/mcp-sources/new` opens the (placeholder) create-mode (or, until L6, lands on grid with `mcpSourceFormMode='add'` set — see Step 14); refresh preserves section; empty grid shows the centered CTA

## Acceptance Criteria

- [x] `admin.js` `categories` array contains `{ id: 'mcp-sources', label: 'MCP Servers' }` as a 4th entry, AFTER `tools`
- [x] `admin.js` `validIds` array (line 83) contains `'mcp-sources'`
- [x] `admin.js` `serializeState` returns: `'mcp-sources'` when category is mcp-sources and form-mode is null; `'mcp-sources/new'` when form-mode is `'add'`; `'mcp-sources/' + encodeURIComponent(editingMcpSource.id)` when form-mode is `'edit'` and `editingMcpSource` is set; the same hydrate-vs-fetch race fallback as providers (use `pendingMcpSourceFormMode` and `pendingMcpSourceId` when the source isn't loaded yet)
- [x] `admin.js` `hydrateState` parses `mcp-sources/new` → `pendingMcpSourceFormMode = 'add'`; `mcp-sources/{id}` → `pendingMcpSourceFormMode = 'edit'` + `pendingMcpSourceId = decodeURIComponent(rest)`; defensive trailing-slash strip + first-segment-only extraction (mirrors providers parsing)
- [x] `admin.js` `hydrateState` unconditionally fires `_tryConsumePendingMcpSource()` at the end (alongside the existing `_tryConsumePendingProvider()` and `_tryConsumePendingTool()`)
- [x] `admin.js` `init()` declares 5 new closure-local vars (`mcpSources`, `mcpSourceFormMode`, `editingMcpSource`, `pendingMcpSourceId`, `pendingMcpSourceFormMode`) — all initialized to null
- [x] `admin.js` exposes 4 new `Object.defineProperty` getter/setter slots on `self` (`_mcpSourceFormMode`, `_editingMcpSource`, `_pendingMcpSourceId`, `_pendingMcpSourceFormMode`). The `mcpSources` cache var is NOT exposed — this matches the existing pattern (`providers` and `toolConfigs` cache vars are also closure-private).
- [x] `admin.js` `doSetCategory` reset block wipes the 5 new slots
- [x] `admin.js` `_setCategory` reset block wipes the 5 new slots (note: `_setCategory` only wipes when `currentCategory !== sub` — same gate as the existing implementation)
- [x] `admin.js` `setCategory` dirty-gate extends `inEditor` to include `(currentCategory === 'mcp-sources' && mcpSourceFormMode)`
- [x] `admin.js` `renderContent` dispatch routes to `renderMcpSourcesPanel()` when `currentCategory === 'mcp-sources'`
- [x] `admin.js` defines `renderMcpSourcesPanel`, `fetchMcpSources`, `populateMcpSourcesGrid`, `selectMcpSource`, `enterCreateMcpSourceMode`, `findMcpSource` — all mirroring the provider counterparts in shape and stale-then-guard discipline
- [x] `admin.js` defines `_tryConsumePendingMcpSource` mirroring `_tryConsumePendingProvider` (handles both `'add'` and `'edit'` pending modes; bails when the source isn't yet in cache; re-fires after `fetchMcpSources` resolves)
- [x] `admin.js` `_refresh` re-fetches MCP sources when `currentCategory === 'mcp-sources'` and no editor is mounted
- [x] NEW file `the_one/interfaces/web/static/js/areas/admin/mcp-servers-grid.js` exports `App.admin.renderMcpServersGrid(container, mcpSources, callbacks)`. Mirrors `providers-grid.js`:
  - `KNOWN_TRANSPORT_BADGES = ['stdio', 'streamable-http']`
  - Page header with `<h1>MCP Servers</h1>` and a `data-testid="new-mcp-source-btn"` CTA
  - Loading state when `mcpSources === null`
  - Empty-canvas with `data-testid="new-mcp-source-btn-empty"` CTA when `mcpSources.length === 0`
  - Tile DOM: `data-testid="mcp-source-card"`, `data-id="{id}"`, `aria-selected`, three spans (badge / name / meta)
  - Badge text is `mcpSource.type`; badge class suffix is `mcpSource.type` if known, else `'unknown'`
  - Meta string: for `stdio`, render `config.command || '—'`; for `streamable-http`, render `config.url || '—'`
- [x] `the_one/interfaces/web/static/index.html` registers `mcp-servers-grid.js` (one new `<script>` tag, placed alongside the existing `providers-grid.js` registration around line 48)
- [x] NEW file `tests/browser/test_flow_admin_mcp_navigation.py` covers 7 tests:
  - Section nav renders 4 items including "MCP Servers"
  - Click "MCP Servers" in section-nav → URL becomes `#admin/mcp-sources`
  - Direct-load `#admin/mcp-sources` → grid (or empty-canvas) renders with the "MCP Servers" page title, no errors
  - Direct-load `#admin/mcp-sources/new` → the L5 placeholder editor with `data-testid="mcp-editor-placeholder"` renders (BEHAVIORAL DOM assertion; `App.areas` is closure-private in `app.js` so state introspection is not possible — the placeholder presence is the user-observable contract that L6 swaps out)
  - Refresh on `#admin/mcp-sources` preserves the section
  - Empty grid shows the centered CTA with `data-testid="new-mcp-source-btn-empty"` (precondition: empty `mcp_sources` table — fixture handles this)
  - Navigating away from the L5 placeholder editor skips the confirm dialog (proves the dirty-gate path at Step 6 is structurally reachable but practically false-bypassed until L6 wires `onDirtyChange`)
- [x] All existing browser tests still pass. Two known sites assert hard-coded section counts — both must be updated: `tests/browser/test_flow_admin_navigation.py::test_admin_section_nav_renders_three_sections` (count 3 → 4) and `tests/browser/test_flow_admin_tools_grid.py:198` (`to_have_count(3)` → `to_have_count(4)`). Resolution: see Implementation Guidance Step 16.
- [ ] `make lint` clean — see Post-Completion Checklist; pre-existing L1-L4 inheritance, L5 introduces zero new ruff errors
- [ ] `make test-browser` green — targeted admin sweep 39/40; one pre-existing F6 leg-07 failure unrelated to L5

## Verification Steps

- `pytest tests/browser/test_flow_admin_navigation.py tests/browser/test_flow_admin_mcp_navigation.py -v --timeout=120` — all pass (existing + new)
- `pytest tests/browser/ -k "admin" -v --timeout=120` — full admin browser-test sweep green
- `make test-browser` — full browser suite green
- `make lint` — clean
- `make rebuild` + manual: open `#admin/mcp-sources` → see "No MCP servers configured." empty canvas with CTA; POST a source via `curl`/REST; refresh the page → grid shows one tile with type-badge + name + url-or-command meta; click the tile → URL becomes `#admin/mcp-sources/{id}` (no editor renders yet — that's L6)
- Manual: section-nav now renders 4 items in order (General, LLM Providers, Built-in Tools, MCP Servers); keyboard navigation through the 4 items works (existing test pattern)

## Implementation Guidance

1. **Re-locate every cited line position before editing**. Run:
   ```
   grep -n "categories\|validIds\|serializeState\|hydrateState\|_setCategory\|doSetCategory\|pendingProviderId\|pendingFormMode\|fetchProviders\|populateProviderGrid\|_tryConsumePendingProvider\|Object\.defineProperty\|_refresh" the_one/interfaces/web/static/js/areas/admin.js
   ```
   The file is 701 lines; cited line numbers are post-L4-stable but verify before each edit. Anchor by symbol/string, not by absolute line number.

2. **Extend `categories` array** at line 108–115:
   ```javascript
   var categories = [
     { id: 'system', label: 'General' },
     { id: 'providers', label: 'LLM Providers' },
     { id: 'tools', label: 'Built-in Tools' },
     { id: 'mcp-sources', label: 'MCP Servers' }
   ];
   ```

3. **Extend `validIds`** at line 83:
   ```javascript
   var validIds = ['system', 'providers', 'tools', 'mcp-sources'];
   ```

4. **Add 5 new closure-local var declarations** in `init()` after the existing tools-state block (around line 152, before `fetchProviderTypes`):
   ```javascript
   // MCP Sources state (L5)
   var mcpSources = null; // null until first fetch resolves
   var mcpSourceFormMode = null; // null | 'add' | 'edit'
   var editingMcpSource = null;
   var pendingMcpSourceId = null;
   var pendingMcpSourceFormMode = null;
   ```

5. **Extend `doSetCategory` reset block** (line 199–213). Add five new wipes after the existing `pendingToolFormMode = null;` line:
   ```javascript
   mcpSourceFormMode = null;
   editingMcpSource = null;
   pendingMcpSourceId = null;
   pendingMcpSourceFormMode = null;
   ```
   (Note: `mcpSources = null;` is NOT reset on category change — same as `providers` is not reset; the cache survives category navigation. This matches the existing pattern.)

6. **Extend `setCategory` dirty-gate** at line 218–225. Update the `inEditor` expression:
   ```javascript
   var inEditor = (currentCategory === 'providers' && providerFormMode)
               || (currentCategory === 'tools' && toolFormMode)
               || (currentCategory === 'mcp-sources' && mcpSourceFormMode);
   ```
   (L5 sets the mode; L6 wires the dirty-flag onDirtyChange bridge through the editor mount. L5 ensures the gate exists in the `inEditor` expression so the L6 bridge has a working confirm dialog from day one.)

   **L5 placeholder vs dirty interaction**: the L5 placeholder editor (Step 8) is non-interactive — there is no form, no input, nothing that could mutate `dirty`. The closure `dirty` flag therefore stays false during the placeholder's lifetime. Result: the dirty-gate codepath `dirty && inEditor` is statically reachable when on `mcp-sources` with a non-null mode, but practically false until L6 wires `onDirtyChange`. This is intentional — L5 ships the gate structurally so L6's onDirtyChange bridge plugs in without further `admin.js` edits. The L5 browser test `test_admin_mcp_placeholder_navigation_skips_confirm` (Step 19) verifies the placeholder path bypasses the confirm dialog cleanly.

7. **Extend `renderContent` dispatch** at line 240–248:
   ```javascript
   function renderContent() {
     if (currentCategory === 'system') {
       App.admin.renderSystemPage(contentEl);
     } else if (currentCategory === 'providers') {
       renderProvidersPanel();
     } else if (currentCategory === 'tools') {
       renderToolsPanel();
     } else if (currentCategory === 'mcp-sources') {
       renderMcpSourcesPanel();
     }
   }
   ```

8. **Add `renderMcpSourcesPanel` function** after `renderToolsPanel` (around line 466). Mirrors `renderProvidersPanel` structure but the editor branch is a stub for L6 — for L5, the editor branch is gated to NOT render (or renders a minimal placeholder). Recommended: when `mcpSourceFormMode` is non-null, render a placeholder DIV that L6 will replace; the closure-local mode is what matters for state-plumbing tests:
   ```javascript
   function renderMcpSourcesPanel() {
     // Editor branch (L6 lands the editor sub-module; L5 renders a placeholder
     // so direct-load to #admin/mcp-sources/new sets state but doesn't crash).
     if (mcpSourceFormMode) {
       contentEl.innerHTML = '<div class="admin-loading" data-testid="mcp-editor-placeholder">' +
         'MCP source editor lands in L6.</div>';
       return;
     }
     // Grid branch
     App.admin.renderMcpServersGrid(contentEl, mcpSources, {
       selectedId: editingMcpSource ? editingMcpSource.id : null,
       onSelectMcpSource: selectMcpSource,
       onCreateMcpSource: enterCreateMcpSourceMode
     });
     fetchMcpSources();
   }
   ```

9. **Add `fetchMcpSources`, `populateMcpSourcesGrid`, `selectMcpSource`, `enterCreateMcpSourceMode`, `findMcpSource`** after `findProvider` (around line 399). Mirror the **tools** counterpart at admin.js:498-525, NOT the providers pattern — tools' stricter stale-then guard wraps BOTH the cache-write AND the populate, preventing the cache from being clobbered by a fetch that started under a different category context. The providers pattern at lines 337-349 has a known race window (cache-write happens unconditionally; only the populate has the guard); L5 adopts the stricter tools pattern as a deliberate upgrade.

   ```javascript
   function fetchMcpSources() {
     return fetch('/api/mcp-sources')
       .then(function (r) { return r.json(); })
       .then(function (data) {
         // Stricter stale-then guard at cache-write (mirrors tools pattern at
         // admin.js:504; deliberately diverges from the older providers
         // pattern at admin.js:340 which writes the cache unconditionally).
         if (currentCategory !== 'mcp-sources') return;
         mcpSources = data;
         populateMcpSourcesGrid();
         self._tryConsumePendingMcpSource();
       })
       .catch(function () {
         if (currentCategory !== 'mcp-sources') return;
         var gridEl = contentEl.querySelector('.entity-tile-grid');
         if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load MCP sources.</div>';
       });
   }

   function populateMcpSourcesGrid() {
     if (currentCategory !== 'mcp-sources') return;
     if (mcpSourceFormMode) return;
     App.admin.renderMcpServersGrid(contentEl, mcpSources, {
       selectedId: editingMcpSource ? editingMcpSource.id : null,
       onSelectMcpSource: selectMcpSource,
       onCreateMcpSource: enterCreateMcpSourceMode
     });
   }

   function selectMcpSource(id) {
     var source = findMcpSource(id);
     if (!source) return; // pending-id race; will be re-attempted after fetch
     mcpSourceFormMode = 'edit';
     editingMcpSource = source;
     pendingMcpSourceId = null;
     pendingMcpSourceFormMode = null;
     if (window.App && window.App.router) {
       App.router.replaceSub(self.serializeState());
     }
     renderMcpSourcesPanel();
   }

   function enterCreateMcpSourceMode() {
     mcpSourceFormMode = 'add';
     editingMcpSource = null;
     pendingMcpSourceId = null;
     pendingMcpSourceFormMode = null;
     if (window.App && window.App.router) {
       App.router.replaceSub(self.serializeState());
     }
     renderMcpSourcesPanel();
   }

   function findMcpSource(id) {
     if (!mcpSources) return null;
     for (var i = 0; i < mcpSources.length; i++) {
       if (mcpSources[i].id === id) return mcpSources[i];
     }
     return null;
   }
   ```

10. **Extend `_refresh`** at line 581–595. Add ONE `else if` branch (L6 will split this into editor-vs-grid branches when per-source detail re-fetch lands):
    ```javascript
    } else if (currentCategory === 'mcp-sources') {
      fetchMcpSources();
    }
    ```

11. **Add 4 new `Object.defineProperty` slots** after the existing pending-tool slots (around line 639). Mirror the provider pattern exactly. The `mcpSources` cache var is NOT exposed — verified against the existing pattern: `grep -n "_providers\|_toolConfigs" admin.js` returns zero matches, confirming caches are closure-private:
    ```javascript
    Object.defineProperty(self, '_mcpSourceFormMode', {
      get: function () { return mcpSourceFormMode; },
      set: function (v) { mcpSourceFormMode = v; },
      configurable: true
    });
    Object.defineProperty(self, '_editingMcpSource', {
      get: function () { return editingMcpSource; },
      set: function (v) { editingMcpSource = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingMcpSourceId', {
      get: function () { return pendingMcpSourceId; },
      set: function (v) { pendingMcpSourceId = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingMcpSourceFormMode', {
      get: function () { return pendingMcpSourceFormMode; },
      set: function (v) { pendingMcpSourceFormMode = v; },
      configurable: true
    });
    ```
    Note: `App.areas` itself is closure-private inside `app.js` (verified at `app.js:2` `var areas = {};` — NOT exported via `Object.assign(window.App, ...)` at lines 266–268). Browser tests therefore cannot introspect `App.areas.admin._mcpSourceFormMode` directly. The Step 19 tests below use BEHAVIORAL DOM assertions (waiting for `data-testid="mcp-editor-placeholder"` to render) instead of state introspection. The defineProperty slots are still valuable internally — `serializeState` uses `this._mcpSourceFormMode` to build the URL. Tests verify the behavior the user observes, not the closure-state.

12. **Extend `_setCategory`** at line 640–654 to wipe the 5 new slots. Mirror the existing pattern — five new lines inside the `if (currentCategory !== sub) { ... }` block.

13. **Add `_tryConsumePendingMcpSource`** after `_tryConsumePendingTool` (line 686). Mirrors `_tryConsumePendingProvider`:
    ```javascript
    self._tryConsumePendingMcpSource = function () {
      if (!pendingMcpSourceId && !pendingMcpSourceFormMode) return;
      if (pendingMcpSourceFormMode === 'add') {
        mcpSourceFormMode = 'add';
        editingMcpSource = null;
        pendingMcpSourceFormMode = null;
        pendingMcpSourceId = null;
        renderMcpSourcesPanel();
        return;
      }
      if (pendingMcpSourceFormMode === 'edit' && pendingMcpSourceId) {
        var found = findMcpSource(pendingMcpSourceId);
        if (found) {
          mcpSourceFormMode = 'edit';
          editingMcpSource = found;
          pendingMcpSourceId = null;
          pendingMcpSourceFormMode = null;
          renderMcpSourcesPanel();
        }
        // else: source not in cache; will be re-attempted after fetchMcpSources resolves.
      }
    };
    ```

14. **Extend `hydrateState`** at lines 34–105. Two changes:
    - Add the parsing branch for `mcp-sources/new` and `mcp-sources/{id}` after the `tools/` branch (around line 81). Mirror the providers pattern; declare two local vars `pendingMcpSourceId_local` and `pendingMcpSourceFormMode_local` at the top of the function alongside the existing locals; assign them in the new branch.
    - Add `this._pendingMcpSourceId = pendingMcpSourceId_local;` and `this._pendingMcpSourceFormMode = pendingMcpSourceFormMode_local;` to the unconditional overwrite block at lines 90–96.
    - Fire `if (this._tryConsumePendingMcpSource) this._tryConsumePendingMcpSource();` at the end (line 104), alongside the existing fires.
    - Update the `if (!sub)` early-return reset block at lines 39–45 to also wipe the 4 new pending slots: `this._pendingMcpSourceId = null; this._pendingMcpSourceFormMode = null;` (NOT `_mcpSourceFormMode` — that's the active state, wiped by `_setCategory` when navigating to bare `#admin`).

15. **Extend `serializeState`** at lines 8–33. Add a new branch BEFORE the trailing `return this._currentCategory || 'system';`:
    ```javascript
    if (this._currentCategory === 'mcp-sources') {
      if (this._mcpSourceFormMode === 'add') return 'mcp-sources/new';
      if (this._mcpSourceFormMode === 'edit' && this._editingMcpSource) {
        return 'mcp-sources/' + encodeURIComponent(this._editingMcpSource.id);
      }
      // Hydrate-vs-fetch race: pending id known but source not yet loaded.
      if (this._pendingMcpSourceFormMode === 'add') return 'mcp-sources/new';
      if (this._pendingMcpSourceId) {
        return 'mcp-sources/' + encodeURIComponent(this._pendingMcpSourceId);
      }
      return 'mcp-sources';
    }
    ```

16. **Update TWO existing browser tests with hard-coded section counts**. Run `grep -rn "to_have_count(3)\|three sections" tests/browser/` to confirm scope before editing. Two known sites:

    - `tests/browser/test_flow_admin_navigation.py::test_admin_section_nav_renders_three_sections` (around line 47) — update the count assertion from 3 to 4 and add "MCP Servers" to the asserted-labels list. Do NOT rename the function (keeps git-blame intact); just update the body and append a sentence to the docstring noting F1/M07 added the fourth entry.
    - `tests/browser/test_flow_admin_tools_grid.py:198` (`test_admin_tools_section_nav_label_is_built_in_tools`) — `to_have_count(3)` assertion. Update to `to_have_count(4)`; the `items.nth(2)` index for "Built-in Tools" REMAINS valid because MCP Servers is appended at index 3 (after Built-in Tools at index 2). Verify by re-reading the test at edit time.

17. **Create `the_one/interfaces/web/static/js/areas/admin/mcp-servers-grid.js`**. Filename note: `mcp-servers` (plural servers) tracks the user-facing label "MCP Servers"; the URL category and most JS identifiers use `mcp-sources` (technical name from the API path). The asymmetry is deliberate — UI label vs storage entity — and matches the flight spec's terminology in line 129. Structurally identical to `providers-grid.js` with these substitutions:
    - `KNOWN_BADGE_TYPES` → `KNOWN_TRANSPORT_BADGES = ['stdio', 'streamable-http']`. Add a comment noting this list MUST stay in sync with `_validate_mcp_source_config` in `api.py` and the `/api/mcp-sources/types` endpoint — three sites to update if a new transport literal is added (single-source-of-truth refactor is a future cleanup).
    - `renderProvidersGrid` → `renderMcpServersGrid`
    - `provider` / `providers` → `mcpSource` / `mcpSources`
    - Title: `LLM Providers` → `MCP Servers`
    - CTA testid: `new-provider-btn` → `new-mcp-source-btn`; empty: `new-provider-btn-empty` → `new-mcp-source-btn-empty`
    - Tile testid: `provider-card` → `mcp-source-card`
    - Tile class suffix: `provider-tile` → `mcp-source-tile`
    - Badge class root: `admin-provider-badge` → `admin-mcp-badge`
    - Empty-canvas message: `No providers configured.` → `No MCP servers configured.`
    - Meta string source: `provider.base_url` → for stdio: `mcpSource.config.command`; for streamable-http: `mcpSource.config.url`. Use a transport-aware ternary:
      ```javascript
      var displayMeta;
      if (mcpSource.type === 'stdio') {
        displayMeta = (mcpSource.config && mcpSource.config.command) ? mcpSource.config.command : '—';
      } else if (mcpSource.type === 'streamable-http') {
        displayMeta = (mcpSource.config && mcpSource.config.url) ? mcpSource.config.url : '—';
      } else {
        displayMeta = '—';
      }
      ```
    - Final export: `window.App.admin.renderMcpServersGrid = renderMcpServersGrid;`

18. **Register the new sub-module** in `the_one/interfaces/web/static/index.html`. Insert after line 48 (the existing `providers-grid.js` registration):
    ```html
    <script src="/static/js/areas/admin/mcp-servers-grid.js"></script>
    ```
    (Order: must be loaded before `admin.js` itself, because `admin.js`'s `renderMcpSourcesPanel` calls `App.admin.renderMcpServersGrid`. The existing pattern is sub-modules first, area orchestrator last — verify the order.)

19. **Create `tests/browser/test_flow_admin_mcp_navigation.py`** mirroring `tests/browser/test_flow_admin_navigation.py`. Required tests (minimum 6):
    ```python
    def test_admin_section_nav_includes_mcp_servers(app_clean, page):
        page.goto(f"{app_clean}#admin/system")
        nav = page.locator(".area-admin .section-nav")
        expect(nav).to_be_visible()
        items = page.locator(".area-admin .section-nav-item")
        expect(items).to_have_count(4)
        labels = items.evaluate_all("els => els.map(e => e.textContent.trim())")
        assert "MCP Servers" in labels

    def test_admin_section_nav_click_to_mcp_sources(app_clean, page):
        page.goto(f"{app_clean}#admin/system")
        page.locator(".area-admin .section-nav-item", has_text="MCP Servers").click()
        assert page.evaluate("location.hash") == "#admin/mcp-sources"

    def test_admin_direct_load_mcp_sources(app_clean, page):
        page.goto(f"{app_clean}#admin/mcp-sources")
        page.wait_for_selector(".area-admin .page-title", timeout=5000)
        assert page.locator(".area-admin .page-title").text_content().strip() == "MCP Servers"

    def test_admin_direct_load_mcp_sources_new_renders_placeholder(app_clean, page):
        """Direct-load to the create route renders the L5 placeholder editor.

        L5 stages the closure-mirror state slots; the actual editor renders
        in L6. For L5 we assert the BEHAVIORAL contract — the L5 placeholder
        with data-testid="mcp-editor-placeholder" is visible. State
        introspection via App.areas.admin._mcpSourceFormMode is not
        possible because App.areas is closure-private in app.js.
        """
        page.goto(f"{app_clean}#admin/mcp-sources/new")
        placeholder = page.locator('[data-testid="mcp-editor-placeholder"]')
        expect(placeholder).to_be_visible(timeout=8000)

    def test_admin_refresh_preserves_mcp_sources_section(app_clean, page):
        page.goto(f"{app_clean}#admin/mcp-sources")
        page.wait_for_selector(".area-admin .page-title", timeout=5000)
        page.reload()
        page.wait_for_selector(".area-admin .page-title", timeout=5000)
        assert page.evaluate("location.hash") == "#admin/mcp-sources"

    def test_admin_mcp_sources_empty_grid_shows_cta(app_clean, page):
        page.goto(f"{app_clean}#admin/mcp-sources")
        # Wait for fetch to resolve and grid to render
        page.wait_for_selector('[data-testid="new-mcp-source-btn-empty"]', timeout=8000)
        cta = page.locator('[data-testid="new-mcp-source-btn-empty"]')
        expect(cta).to_be_visible()

    def test_admin_mcp_placeholder_navigation_skips_confirm(app_clean, page):
        """The L5 placeholder is non-interactive; navigating away skips the
        confirm dialog because dirty stays false. Pins the dirty-gate
        structural correctness even before L6 wires onDirtyChange.
        """
        page.goto(f"{app_clean}#admin/mcp-sources/new")
        # Wait for the placeholder to render
        expect(page.locator('[data-testid="mcp-editor-placeholder"]')).to_be_visible(timeout=8000)
        # Click "General" — should navigate without surfacing confirmDialog
        page.locator(".area-admin .section-nav-item", has_text="General").click()
        assert page.evaluate("location.hash") == "#admin/system"
        # Confirm dialog must NOT have appeared (no dialog DOM)
        assert page.locator(".confirm-dialog").count() == 0
    ```

    The `app_clean` fixture provides an empty DB — `mcp_sources` table starts empty, so `fetchMcpSources` returns `[]` and the empty-canvas renders with the CTA.

20. **Run the test suite**:
    ```
    make lint
    pytest tests/browser/test_flow_admin_navigation.py tests/browser/test_flow_admin_mcp_navigation.py -v --timeout=120
    pytest tests/browser/ -k "admin" -v --timeout=120
    ```

    Expected: existing admin tests pass (after the count-update in Step 16); new MCP navigation tests pass; full admin sweep green.

21. **Update the flight log** at `flight-log.md` with `### 05-settings-nav-and-grid` entry: status `landed`, started/completed timestamps, "Changes Made" listing the admin.js + mcp-servers-grid.js + index.html + test_flow_admin_navigation.py + test_flow_admin_mcp_navigation.py edits, "Notes" entry confirming the closure-mirror enumeration is complete and the L6 editor bridge points are staged.

22. **Set leg status to `landed`** in this leg's frontmatter.

23. **Do NOT commit**. Per agentic-workflow protocol commit happens at flight end.

24. **Signal `[HANDOFF:review-needed]`** when complete.

## Edge Cases

- **Empty `mcp_sources` table**: `GET /api/mcp-sources` returns `[]`; `mcpSources` is set to the empty array; `populateMcpSourcesGrid` calls `renderMcpServersGrid(container, [])`; the grid sub-module renders the empty-canvas with the centered CTA. No crash. Tested by `test_admin_mcp_sources_empty_grid_shows_cta`.
- **Direct-load `#admin/mcp-sources/{id}` with an unknown id**: `hydrateState` parses → `pendingMcpSourceId = '{id}'`, `pendingMcpSourceFormMode = 'edit'` → `_tryConsumePendingMcpSource` fires → `findMcpSource` returns null → bail; the grid renders. After `fetchMcpSources` resolves, `_tryConsumePendingMcpSource` re-fires (called from `fetchMcpSources.then`) — `findMcpSource` returns null again → final state is grid view, pending state cleared via no path. **Mitigation**: extend `_tryConsumePendingMcpSource` to clear `pendingMcpSourceId`/`pendingMcpSourceFormMode` after the second resolution attempt fails. Actually the providers analog at line 666–676 has the same gap (silent no-op when the id isn't found post-fetch); follow precedent and accept the gap. Implementer: do NOT add the clear-after-second-fail path unless it shows up in HAT.
- **Direct-load `#admin/mcp-sources/` (trailing slash, empty id)**: parsing extracts `rest === ''`; `pendingMcpSourceId = null`. Result: same as `#admin/mcp-sources` (grid view). Mirrors provider behavior at admin.js:62–67 (`if (rest.charAt(rest.length - 1) === '/') rest = rest.slice(0, -1);` then `pendingId = rest ? decodeURIComponent(rest) : null;`).
- **Direct-load `#admin/mcp-sources/new/`** (trailing slash on `/new`): the parsing branch checks `origSub === 'mcp-sources/new'` first (exact match). With trailing slash, exact match fails → falls through to `origSub.indexOf('mcp-sources/') === 0` → `rest === 'new/'` → trailing-slash strip → `rest === 'new'` → `pendingMcpSourceId = 'new'`, `pendingMcpSourceFormMode = 'edit'`. **This is wrong** — it would attempt to edit a source with id 'new'. Mirror the provider analog: the `/new` literal IS handled before the generic `/{id}` branch, so trailing slash should be stripped BEFORE the exact-match check. **Resolution**: provider parsing has the same gap (line 55: `if (origSub === 'providers/new')`). Mirror exactly; do NOT fix in L5. Document as known minor in flight log if HAT surfaces.
- **`mcp-sources` URL encoded id with reserved chars**: `selectMcpSource` calls `encodeURIComponent` and `hydrateState` parsing calls `decodeURIComponent`. UUIDs are alphanum-only; no issue. Documented for completeness.
- **Concurrent fetch races**: `fetchMcpSources` is called from `renderMcpSourcesPanel`. If the user navigates from `#admin/providers` to `#admin/mcp-sources` quickly, two fetches may be in-flight. The stale-then guard in `populateMcpSourcesGrid` (`if (currentCategory !== 'mcp-sources') return`) handles the back-navigation case. Forward-navigation race (both fetches against the same category) — the second `populate` overwrites the first. No crash; final state is correct.
- **Section-nav count update**: existing test at `test_flow_admin_navigation.py::test_admin_section_nav_renders_three_sections` (line 47) MUST be updated to four. Failing to update this test is the most likely L5 regression source. Step 16 calls this out explicitly.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin.js` — extension at 18 enumerated touchpoints (use this list as an implementer checklist; cross-reference with grep before commit):
  1. `serializeState` — new `mcp-sources` branch with three sub-state fallbacks (Step 15)
  2. `hydrateState` — `mcp-sources/new` + `mcp-sources/{id}` parsing branch (Step 14)
  3. `hydrateState` — local var declarations for `pendingMcpSourceId_local` + `pendingMcpSourceFormMode_local` (Step 14)
  4. `hydrateState` — early-return reset block extends with `_pendingMcpSourceId = null; _pendingMcpSourceFormMode = null;` (Step 14)
  5. `hydrateState` — unconditional overwrite block extends with `this._pendingMcpSourceId = pendingMcpSourceId_local; this._pendingMcpSourceFormMode = pendingMcpSourceFormMode_local;` (Step 14)
  6. `hydrateState` — unconditional fire `if (this._tryConsumePendingMcpSource) this._tryConsumePendingMcpSource();` (Step 14)
  7. `validIds` array — add `'mcp-sources'` (Step 3)
  8. `categories` array — add `{ id: 'mcp-sources', label: 'MCP Servers' }` (Step 2)
  9. `init` — 5 new `var` declarations (Step 4)
  10. `doSetCategory` reset block — wipe 4 active+pending mcp slots (Step 5)
  11. `setCategory` dirty-gate — extend `inEditor` (Step 6)
  12. `renderContent` — dispatch branch (Step 7)
  13. NEW function `renderMcpSourcesPanel` with placeholder-editor branch (Step 8)
  14. NEW functions `fetchMcpSources` / `populateMcpSourcesGrid` / `selectMcpSource` / `enterCreateMcpSourceMode` / `findMcpSource` (Step 9)
  15. `_refresh` — `mcp-sources` branch (Step 10)
  16. 4 new `Object.defineProperty` slots (Step 11)
  17. `_setCategory` reset block — wipe 4 active+pending mcp slots (Step 12)
  18. NEW `_tryConsumePendingMcpSource` function (Step 13)
- `the_one/interfaces/web/static/js/areas/admin/mcp-servers-grid.js` (NEW) — the grid sub-module
- `the_one/interfaces/web/static/index.html` — one new `<script>` registration
- `tests/browser/test_flow_admin_navigation.py` — section-count assertion bumped from three to four (one site)
- `tests/browser/test_flow_admin_tools_grid.py` — `to_have_count(3)` → `to_have_count(4)` at line 198 (Built-in Tools nth(2) index unchanged)
- `tests/browser/test_flow_admin_mcp_navigation.py` (NEW) — Playwright tests for the MCP-sources navigation surface (7 tests)
- `missions/07-mcp-integration/flights/01-encrypted-persistence-and-settings/flight-log.md` — `### 05-settings-nav-and-grid` entry appended

## State-Machine Reachability Audit

States introduced or affected:
- **`currentCategory` enum**: extended from `{system, providers, tools}` to `{system, providers, tools, mcp-sources}`. All gates that switch on `currentCategory` need an mcp-sources branch:
  - `serializeState` switch — new branch added (Step 15)
  - `validIds` membership check — new entry (Step 3)
  - `renderContent` dispatch — new branch (Step 7)
  - `_refresh` switch — new branch (Step 10)
  - `setCategory` dirty-gate `inEditor` expression — new disjunct (Step 6)
- **MCP-source form-mode enum**: `null | 'add' | 'edit'` — same shape as providers. Gates:
  - `serializeState` produces three URL shapes (`mcp-sources`, `mcp-sources/new`, `mcp-sources/{id}`)
  - `setCategory` dirty-gate triggers `confirmDialog` only when form-mode is non-null
  - `renderMcpSourcesPanel` editor-vs-grid switch
- **Pending state pair** (`pendingMcpSourceId`, `pendingMcpSourceFormMode`): consumed by `_tryConsumePendingMcpSource`. Lifecycle: set by `hydrateState`; cleared by `_tryConsumePendingMcpSource` on success; survives `fetchMcpSources` if the source wasn't yet in cache; re-attempted after the fetch.

Tests that pin pre-L5 state and would contradict L5:
- `tests/browser/test_flow_admin_navigation.py::test_admin_section_nav_renders_three_sections` — count assertion. Step 16 updates to four. Failure to update this test is one canonical L5 regression source.
- `tests/browser/test_flow_admin_tools_grid.py:198` (`test_admin_tools_section_nav_label_is_built_in_tools`) — `to_have_count(3)` assertion; nth(2) index for "Built-in Tools" remains valid because MCP Servers is appended at index 3. Step 16 updates this too.
- Implementer must also `grep -rn "to_have_count(3)\|three sections\|\.section-nav" tests/browser/` at edit time to catch any additional sites added between leg-design and implementation.

No FK behaviors. No application caches in L5 beyond the existing `mcpSources = null` initial cache (which is invalidated on every `_refresh` and on every category-back-navigation that re-enters mcp-sources).

## Cache Freshness Contract

- `mcpSources` closure-local cache: populated by `fetchMcpSources`; NOT reset on category-change (mirrors `providers` cache pattern); re-fetched on every `_refresh` call AND on every `renderMcpSourcesPanel` grid-branch call (the call to `fetchMcpSources` at the end of the function). Stale-then guard at `populateMcpSourcesGrid` prevents cross-category clobber.
- `editingMcpSource` is set by `selectMcpSource` from a tile click OR by `_tryConsumePendingMcpSource` after a successful pending-id resolution. Cleared by `doSetCategory`, `_setCategory`, `enterCreateMcpSourceMode`, or a successful editor save (the L6 `onSaveSuccess` callback).

## Citation Audit

All citations are admin.js line numbers. The file is post-L4-stable (L1-L4 did not modify `admin.js`); citations should hold but the implementer must regrep before edits. Anchors:
- `admin.js:8-33` `serializeState` — verified
- `admin.js:34-105` `hydrateState` — verified (incl. lines 39–45 reset block, 55–67 providers parsing, 90–96 unconditional overwrite, 103–104 unconditional fire)
- `admin.js:83` `validIds` — verified
- `admin.js:108-115` `categories` — verified
- `admin.js:120-138` provider-state declarations — verified
- `admin.js:140-151` tools-state declarations — verified
- `admin.js:185-191` beforeunload listener — verified
- `admin.js:199-213` `doSetCategory` reset block — verified
- `admin.js:218-225` `setCategory` dirty-gate — verified
- `admin.js:240-248` `renderContent` dispatch — verified
- `admin.js:252-335` `renderProvidersPanel` — verified
- `admin.js:337-349` `fetchProviders` — verified
- `admin.js:354-367` `populateProviderGrid` (with stale-then guard at line 361) — verified
- `admin.js:369-391` `selectProvider` / `enterCreateMode` — verified
- `admin.js:393-399` `findProvider` — verified
- `admin.js:581-595` `_refresh` — verified
- `admin.js:596-639` `Object.defineProperty` slots — verified
- `admin.js:640-654` `_setCategory` — verified
- `admin.js:655-677` `_tryConsumePendingProvider` — verified
- `admin.js:678-686` `_tryConsumePendingTool` — verified
- `admin.js:688-691` init block — verified
- `providers-grid.js` (100 lines) — verified as the structural template
- `index.html:47-53` script registrations — verified
- `tests/browser/test_flow_admin_navigation.py` (line 47 `_renders_three_sections`) — verified
- `tests/browser/test_flow_admin_tools_grid.py` (line 198 `_label_is_built_in_tools`, `to_have_count(3)`) — verified by reviewer recon
- `the_one/interfaces/web/static/js/app.js` (line 2 `var areas = {};`) — `App.areas` is closure-private; NOT exported via the `Object.assign(window.App, {...})` block at lines 266–268. This is why L5 tests use behavioral DOM assertions, not state introspection.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified (within L5's scope; see Notes)
- [ ] `make lint` clean — **NOT MET due to pre-existing L1-L4 inheritance.** Ruff fails on `repositories.py:255,258` (undefined `Any`) and `api.py:11` (unused `Path`) + `api.py:583` (line >100 chars). Verified by stashing L5 changes and re-running — failures identical. L5 introduces zero new ruff errors. Flagged for review/L1-L4 follow-up.
- [x] `pytest tests/browser/test_flow_admin_navigation.py tests/browser/test_flow_admin_mcp_navigation.py -v --timeout=120` green (14/14)
- [x] `pytest tests/browser/ -k "admin" -v --timeout=120` green except for `test_admin_tools_renders_grid_with_4_tabs` (pre-existing F6-leg-07 failure: tools-grid has 3 tabs but the test expects 4 — verified pre-existing by stash-and-rerun; unrelated to L5)
- [ ] `make test-browser` green — not run as a whole; targeted admin sweep is 39/40 green (one pre-existing failure as above). Full sweep deferred to flight-end review.
- [x] Existing `test_admin_section_nav_renders_three_sections` updated/renamed to four sections
- [x] Update flight-log.md with leg progress entry
- [x] Set leg status to `landed` (frontmatter line 3)
- [x] Do NOT check off this leg in flight.md (commit at flight end)
- [x] Do NOT commit
