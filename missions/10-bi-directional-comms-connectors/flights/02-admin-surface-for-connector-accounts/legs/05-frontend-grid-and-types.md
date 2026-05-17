# Leg: frontend-grid-and-types

**Status**: completed
**Flight**: [Admin Surface for Connector Accounts](../flight.md)

## Objective

Land the Studio "Connector Accounts" section: the entity-tile grid (parallel to `admin/providers-grid.js`), the routing wiring in `studio.js` (sub-paths `new` and `{id}`, selection state, form-mode state mirroring the MCP block), and the `/api/connector-accounts/types` consumer. Ship a minimal placeholder editor file (`connector-account-editor.js`) sufficient to make form-mode routing testable; leg 6 replaces it with the full editor. Empty-canvas copy explicitly explains the production empty state ("no connector types registered yet — Flight 8 will add Discord").

## Context

### Why this leg

Per the flight Design Decision "Studio placement, not Admin" and the leg listing:

- Connector accounts are many-to-many identities (the operator may have 3 Discord bots, 2 Slack workspace apps) — structural match to MCP sources, not LLM providers.
- The Studio area already gained an `mcp-sources` section post-F2 retrofit; this leg adds a fourth section (`connector-accounts`) using the same shape.
- The REST surface (legs 3 + 4) provides every endpoint this leg needs.
- The full editor (Connection, Credentials, Lifecycle, Test Connection, Danger Zone) lands in leg 6 — this leg ships the routing + grid + a minimal placeholder editor so the browser-flow navigation test ("New button opens form → Cancel returns to empty state") is testable without requiring leg 6 to land first. **Trade-off (explicit)**: we ship ~50 LoC of throwaway code (the placeholder editor file) in exchange for catching routing bugs one leg earlier; leg 6 replaces the file wholesale. The alternative — deferring the routing test to leg 6 — would save the throwaway but couple routing verification to editor-shape verification, masking which surface a future regression came from. Going with the placeholder.

### Relevant design decisions

- **"Studio placement, not Admin"** — drives the file location: `static/js/areas/studio/connector-accounts-grid.js` (NOT `admin/`), and the section integration in `studio.js`.
- **"Stub plugin is NOT exposed via `/api/connector-accounts/types` in production"** — the grid's empty-canvas state is the production reality until Flight 8. Copy mentions this explicitly: "no connector types registered yet — Flight 8 will add Discord."
- **No type-specific config validation** (deferred to per-connector flights) — drives the grid's `displayMeta`: render the account's `type` as the badge and the account's `name` as the primary label; no transport-specific meta line (MCP shows `command`/`url`; connectors have nothing equivalent until per-connector config shapes ship in Flights 8/9). The tile-meta line in the grid stays empty (`—`) for now.

### Key learnings from prior flights

- **MCP grid + section integration at `static/js/areas/studio.js:280-602`** is the precedent. The "Studio sections array" at L294-303 currently lists `agents / knowledge / mcp-sources`; this leg appends `connector-accounts` as a fourth entry. Every `mcp-sources` switch / state-machine branch in `studio.js` gets a parallel `connector-accounts` branch.
- **`renderMcpServersGrid` shape at `studio/mcp-servers-grid.js`** — 117-line file with `KNOWN_TRANSPORT_BADGES` allowlist, empty-canvas branch, `entity-tile` markup. The connector grid mirrors verbatim minus the transport-specific meta line.
- **`script src` registration in `static/index.html`** — adding a new JS file requires a `<script src="/static/js/areas/studio/connector-accounts-grid.js"></script>` tag (and a parallel one for `connector-account-editor.js`). The MCP entries are at L53-54.
- **Browser-test precedent at `tests/browser/test_flow_studio_mcp_navigation.py`** — 6 tests using `app_clean` + `page` fixtures, behavioural DOM assertions (`App.areas` is closure-private). This leg's browser tests follow the same shape.

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/static/js/areas/studio.js` — current Studio area module. `_activeSection` accepts `agents / knowledge / mcp-sources`. The section nav at L294-303 lists 3 entries.
- `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js` (117 lines) — the structural template for `connector-accounts-grid.js`.
- `the_one/interfaces/web/static/js/areas/admin/providers-grid.js` (100 lines) — alternative template; the `KNOWN_BADGE_TYPES` allowlist pattern is more directly applicable (no transport-config meta to render).
- `the_one/interfaces/web/static/index.html:46-58` — script-src section where the new JS files register.
- `tests/browser/test_flow_studio_mcp_navigation.py` (6 tests) — browser-flow test precedent.
- `tests/browser/conftest.py` + `tests/browser/seeders.py` + `tests/browser/design_tokens.py` — the browser-test framework.
- `/api/connector-accounts` + `/api/connector-accounts/types` (legs 3 + 4) — backend endpoints.

## Outputs

What exists after this leg completes:

- **New file**: `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js` (~120 LoC). Module pattern: `(function () { 'use strict'; window.App.studio = window.App.studio || {}; ... window.App.studio.renderConnectorAccountsGrid = renderConnectorAccountsGrid; })();`
  - `KNOWN_CONNECTOR_BADGES = []` — empty allowlist in production (no real types registered). Future flights extend with `'discord'`, etc. Mirror of `KNOWN_TRANSPORT_BADGES` in `mcp-servers-grid.js`.
  - `renderConnectorAccountsGrid(container, accounts, callbacks)` — three branches: header + new-btn + grid skeleton; null/undefined → loading state; empty array → centered empty-canvas CTA with the "no connector types registered yet" copy; populated array → tile markup.
  - Tile markup: `<button class="entity-tile connector-account-tile" ...><span class="entity-tile-badge admin-connector-badge admin-connector-badge--{type}">{type}</span><span class="entity-tile-name">{name}</span><span class="entity-tile-meta">—</span></button>`. The `—` placeholder is deliberate: connectors have no transport-config-equivalent meta until per-platform configs ship in Flights 8/9.
  - `data-testid` values: `"new-connector-account-btn"`, `"new-connector-account-btn-empty"`, `"connector-account-card"`. Mirrors the MCP precedent's naming convention.
- **New file**: `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (~50 LoC placeholder). Exposes `window.App.studio.renderConnectorAccountEditor(container, account, types, callbacks)` with a minimal shape:
  - Renders a back button, a title ("New Connector Account" / "Edit Connector Account"), and a `Cancel` button.
  - The Cancel button calls `callbacks.onCancel()`.
  - **Explicit placeholder comment** at the top of the file: `// PLACEHOLDER — leg 6 (frontend-editor-and-browser-tests) replaces this file wholesale with the full editor (Connection, Credentials, Lifecycle, Test Connection, Danger Zone). This leg ships only the minimal navigation surface so the routing test ("New button opens form → Cancel returns to empty state") is testable.`
  - `data-testid="connector-account-editor-placeholder"` on the container so the navigation test can verify the editor mounted.
- **Updated**: `the_one/interfaces/web/static/index.html` — two new `<script>` tags registering the grid + placeholder editor files. Placed alongside the existing MCP script tags at L53-54.
- **Updated**: `the_one/interfaces/web/static/js/areas/studio.js` — adds the `connector-accounts` section parallel to `mcp-sources`. The diff surface:
  - `serializeState()` (~L24-35) — new `connector-accounts` branch with the same form-mode/id serialization shape.
  - `hydrateState()` (~L78-100) — new `connector-accounts` URL parsing branch with the same `pendingConnectorAccountId / pendingConnectorAccountFormMode` shape.
  - Closure-locals near L206-227: `connectorAccounts`, `connectorAccountFormMode`, `editingConnectorAccount`, `pendingConnectorAccountId`, `pendingConnectorAccountFormMode`, `connectorTypesReady`, `CONNECTOR_TYPES`. Mirror of the existing MCP locals.
  - `Object.defineProperty` properties at L216-228 — `_editingConnectorAccount`, `_pendingConnectorAccountId`, `_pendingConnectorAccountFormMode`.
  - Section-nav array at L294-303 — append `{ id: 'connector-accounts', label: 'Connector Accounts' }` as the fourth entry.
  - `setActiveSection`'s section dispatch at L598-602 — new `else if (section === 'connector-accounts') renderConnectorAccountsSection();` branch.
  - `onSelect` confirm-leave block at L317-326 — add a `connector-accounts` branch for "click same nav while editor is mounted → back to grid."
  - `renderConnectorAccountsSection()` — mirror of `renderMcpSourcesSection()` (~120 LoC), branching on form mode.
  - `fetchConnectorAccountTypes()` / `fetchConnectorAccounts_()` / `populateConnectorAccountsGrid()` — mirrors of the MCP fetchers (~50 LoC).
  - `selectConnectorAccount(id)` / `enterCreateConnectorAccountMode()` / `findConnectorAccount(id)` / `tryConsumePendingConnectorAccount()` — mirrors of the MCP helpers (~40 LoC).
  - `setActiveSection` state-reset branch at L591-595 — leaving `connector-accounts` clears `connectorAccountFormMode` + `editingConnectorAccount`.
- **New file**: `tests/browser/test_flow_studio_connector_account_navigation.py` (~120 LoC) — 7 tests mirroring `test_flow_studio_mcp_navigation.py`:
  1. `test_studio_section_nav_includes_connector_accounts` — section nav now has 4 entries; assert order: `["Agents", "Knowledge", "MCP Servers", "Connector Accounts"]`.
  2. `test_studio_section_nav_click_to_connector_accounts` — click "Connector Accounts" → URL becomes `#studio/connector-accounts`; page title is "Connector Accounts".
  3. `test_studio_direct_load_connector_accounts` — direct-load `#studio/connector-accounts` renders the page.
  4. `test_studio_direct_load_connector_accounts_new_renders_placeholder_editor` — direct-load `#studio/connector-accounts/new` mounts the placeholder editor (assert `[data-testid="connector-account-editor-placeholder"]` is visible).
  5. `test_studio_refresh_preserves_connector_accounts_section` — refresh on `#studio/connector-accounts` preserves the URL.
  6. `test_studio_connector_accounts_empty_grid_shows_cta` — empty `connector_accounts` table → empty-canvas with centered CTA renders + the "no connector types registered yet — Flight 8 will add Discord" copy is present.
  7. `test_studio_connector_accounts_new_button_opens_form_then_cancel_returns_to_grid` — click "New Connector Account" → URL becomes `#studio/connector-accounts/new` and placeholder editor mounts; click Cancel → URL back to `#studio/connector-accounts` and empty-canvas re-renders.
- **Updated**: existing browser tests that hardcode the 3-section nav (caught at design review — the leg's initial citation pass missed `test_flow_studio_navigation.py`):
  - `tests/browser/test_flow_studio_mcp_navigation.py:28-36` — `test_studio_section_nav_includes_mcp_servers`: `to_have_count(3)` → `to_have_count(4)`; labels list extended.
  - `tests/browser/test_flow_studio_navigation.py:38-46` — `test_studio_section_nav_renders_three_buttons`: rename to `_renders_four_buttons` (or generalise to `_renders_all_sections`); `to_have_count(3)` → `to_have_count(4)`; the `buttons.nth(2)` "MCP Servers" assertion stays; add `buttons.nth(3)` for "Connector Accounts".
  - `tests/browser/test_flow_studio_navigation.py:140-170` (keyboard-nav assertions) — every wrap-around target that currently lands on `mcp-sources` (ArrowDown from `mcp-sources` wraps to `agents`; End → `mcp-sources`; ArrowUp from `agents` wraps to `mcp-sources`) must shift one position: the new last entry is `connector-accounts`. Wrap-around targets become `connector-accounts`; End lands on `connector-accounts`; ArrowDown from `mcp-sources` → `connector-accounts` (no wrap); ArrowDown from `connector-accounts` → `agents` (wrap). Audit every key/wrap assertion in the block and update each.
  - **Generalisation note**: pre-implementation, `grep -rn "to_have_count(3)\|\"MCP Servers\"]" tests/browser/` to catch any other site that overlaps. The design-review pass found these two files; if a third surfaces during implementation, treat it the same way.
- Flight log "Leg Progress" entry + Design Adjustments entry (the placeholder editor file).
- Flight artifact's leg-5 checkbox ticked.

## Acceptance Criteria

- [ ] `connector-accounts-grid.js` exists and exposes `window.App.studio.renderConnectorAccountsGrid` with the documented signature.
- [ ] `connector-account-editor.js` exists as a minimal placeholder with `window.App.studio.renderConnectorAccountEditor`; the placeholder comment explicitly names leg 6 as the replacement.
- [ ] Both new files are registered in `static/index.html` via `<script src>` tags.
- [ ] `studio.js` section nav lists 4 entries: Agents / Knowledge / MCP Servers / Connector Accounts.
- [ ] Routing accepts `#studio/connector-accounts`, `#studio/connector-accounts/new`, and `#studio/connector-accounts/{id}`.
- [ ] Direct-load on `#studio/connector-accounts/new` renders the placeholder editor.
- [ ] Direct-load on `#studio/connector-accounts/{id}` resolves the account from the cache (or after the fetch completes) and renders the placeholder editor with the editing-account context.
- [ ] Empty-canvas state renders the "no connector types registered yet — Flight 8 will add Discord" copy.
- [ ] Clicking "New Connector Account" from the empty-canvas CTA or the page-header button drives form-mode transition.
- [ ] Cancel from the placeholder editor returns to the grid view (empty-canvas if no accounts).
- [ ] Both existing browser tests with 3-section hardcoded assertions are updated:
  - `test_flow_studio_mcp_navigation.py::test_studio_section_nav_includes_mcp_servers` → 4 entries.
  - `test_flow_studio_navigation.py::test_studio_section_nav_renders_three_buttons` → renamed + 4 entries.
- [ ] All keyboard-nav wrap-around assertions in `test_flow_studio_navigation.py:140-170` updated so wrap targets, End, and adjacent-arrow positions all reflect `connector-accounts` as the new last section.
- [ ] Seven new browser tests in `test_flow_studio_connector_account_navigation.py` all pass.
- [ ] `make test` clean (browser-test recipe green; +at least 7 tests on the 1805 baseline — though the browser tests may be counted via the `make test-browser` recipe rather than the unit suite; report both).
- [ ] `make lint` clean.
- [ ] No regression on the existing 6 `test_flow_studio_mcp_navigation.py` tests (one is updated, five stay green).

## Verification Steps

How to confirm each criterion:

- `ls the_one/interfaces/web/static/js/areas/studio/ | grep connector-account` — two new files.
- `grep -n "connector-account" the_one/interfaces/web/static/index.html` — two new script tags.
- `grep -n "connector-accounts\|connectorAccount\|ConnectorAccount" the_one/interfaces/web/static/js/areas/studio.js` — every expected site lights up.
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_navigation.py tests/browser/test_flow_studio_mcp_navigation.py tests/browser/test_flow_studio_navigation.py` — all tests green (7 new + 6 mcp-nav with 1 updated + N studio-nav with the count + keyboard-wrap updates). Direct `docker exec` is the fast scoped iteration tool; the canonical recipe is `make test-browser` (which sets `THE_ONE_DEV_MODE=true` and chains the playwright-install precondition).
- `make test-browser` — full browser-test recipe green. **MUST be the final invocation before signaling complete** — direct `docker exec` skips the `_ensure-playwright` precondition and the `THE_ONE_DEV_MODE=true` env-var setup that the canonical recipe provides.
- `make test` — full unit suite green (no regressions; browser tests may not be in the default `make test` target, but they MUST be run separately).
- `make lint` — clean.

## Implementation Guidance

1. **Create `connector-accounts-grid.js`**
   - Path: `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js`.
   - Structurally analogous to `studio/mcp-servers-grid.js`. Key differences:
     - `KNOWN_CONNECTOR_BADGES = []` — start empty; future flights extend.
     - Title: `"Connector Accounts"` (page-title).
     - New-button label: `"New Connector Account"`. Aria-label: `"New connector account"`.
     - Empty-canvas copy: two-line block:
       - Line 1: `"No connector accounts configured."`
       - Line 2: `"No connector types registered yet — Flight 8 will add Discord."` (small text, e.g. `<div class="empty-canvas-secondary">...</div>` or just a second `<div>` matching MCP precedent's structure).
       - Centered CTA: same `new-entity-btn is-expanded` markup as MCP.
     - `data-testid` values: `"new-connector-account-btn"`, `"new-connector-account-btn-empty"`, `"connector-account-card"`.
     - Tile DOM:
       ```html
       <button class="entity-tile connector-account-tile" type="button" role="option"
               data-testid="connector-account-card" data-id="..."
               aria-selected="false">
         <span class="entity-tile-badge admin-connector-badge admin-connector-badge--{typeSuffix}">{type}</span>
         <span class="entity-tile-name">{name}</span>
         <span class="entity-tile-meta">—</span>
       </button>
       ```
       The `—` meta line is intentional (no transport-config equivalent for connectors in Flight 2; Flights 8/9 will revisit per-platform).
   - Export: `window.App.studio.renderConnectorAccountsGrid = renderConnectorAccountsGrid;`

2. **Create `connector-account-editor.js`** (minimal placeholder)
   - Path: `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`.
   - Top-of-file comment naming leg 6 as the replacement.
   - Minimal body:
     ```javascript
     (function () {
       'use strict';
       window.App = window.App || {};
       window.App.studio = window.App.studio || {};

       // PLACEHOLDER — leg 6 (frontend-editor-and-browser-tests) replaces
       // this file wholesale with the full editor (Connection, Credentials,
       // Lifecycle, Test Connection, Danger Zone). This leg ships only the
       // minimal navigation surface so the routing test ("New button opens
       // form → Cancel returns to empty state") is testable.

       function renderConnectorAccountEditor(container, account, types, callbacks) {
         callbacks = callbacks || {};
         var onCancel = callbacks.onCancel || function () {};
         var escapeHtml = window.App.escapeHtml;
         var title = account ? 'Edit Connector Account' : 'New Connector Account';

         container.innerHTML =
           '<div class="connector-account-editor" data-testid="connector-account-editor-placeholder">' +
             '<div class="page-header">' +
               '<h1 class="page-title">' + escapeHtml(title) + '</h1>' +
             '</div>' +
             '<div class="editor-section">' +
               '<p>Placeholder editor — full form lands in leg 6.</p>' +
               '<button class="btn" type="button" data-testid="cancel-connector-account-btn">Cancel</button>' +
             '</div>' +
           '</div>';

         var cancelBtn = container.querySelector('[data-testid="cancel-connector-account-btn"]');
         cancelBtn.addEventListener('click', function () { onCancel(); });
       }

       window.App.studio.renderConnectorAccountEditor = renderConnectorAccountEditor;
     })();
     ```

3. **Register both files in `static/index.html`**
   - Add two `<script src>` tags AFTER the existing MCP entries at L53-54:
     ```html
     <script src="/static/js/areas/studio/connector-accounts-grid.js"></script>
     <script src="/static/js/areas/studio/connector-account-editor.js"></script>
     ```
   - Verify they appear BEFORE `<script src="/static/js/areas/studio.js"></script>` at L55 (so `App.studio.renderConnectorAccountsGrid` exists when `studio.js` runs).

4. **Extend `studio.js`**
   - **Locate each MCP block in `studio.js` and add a parallel CONNECTOR-ACCOUNTS block.** Don't try to factor out a generic abstraction — the diff is mechanical and parallel, and prematurely abstracting it would obscure intent. Inline the parallel branches.
   - Specific edits (line numbers approximate; rely on the surrounding context):
     1. **`serializeState()` (L23-43)**: add a `connector-accounts` branch after the `mcp-sources` block:
        ```javascript
        if (this._activeSection === 'connector-accounts') {
          if (this._connectorAccountFormMode === 'add') return 'connector-accounts/new';
          if (this._connectorAccountFormMode === 'edit' && this._editingConnectorAccount) {
            return 'connector-accounts/' + encodeURIComponent(this._editingConnectorAccount.id);
          }
          if (this._pendingConnectorAccountFormMode === 'add') return 'connector-accounts/new';
          if (this._pendingConnectorAccountId) {
            return 'connector-accounts/' + encodeURIComponent(this._pendingConnectorAccountId);
          }
          return 'connector-accounts';
        }
        ```
     2. **`hydrateState()` (L60-160)**: add parsing for the three `connector-accounts*` URL forms, parallel to the MCP block. Local variables: `pendingConnectorAccountId_local`, `pendingConnectorAccountFormMode_local`. Final assignment: `this._activeSection = section` reaches `'connector-accounts'`; `this._pendingConnectorAccountId = ...`; `this._pendingConnectorAccountFormMode = ...`. Mirrors `mcp-sources` exactly.
     3. **Closure-locals near init()** (L206-228): add `connectorAccounts = null`, `connectorAccountFormMode = null`, `editingConnectorAccount = null`, `pendingConnectorAccountId = self._pendingConnectorAccountId || null`, `pendingConnectorAccountFormMode = self._pendingConnectorAccountFormMode || null`, `connectorTypesReady = null`, `CONNECTOR_TYPES = []`.
     4. **`Object.defineProperty` chain** (L216-228): add three properties mirroring the MCP ones: `_editingConnectorAccount`, `_pendingConnectorAccountId`, `_pendingConnectorAccountFormMode`.
     5. **Section-nav array** (L294-303): append `{ id: 'connector-accounts', label: 'Connector Accounts' }` as the fourth entry.
     6. **`onSelect` confirm-leave block** (L317-326): add a `connector-accounts` branch:
        ```javascript
        } else if (section === 'connector-accounts' && connectorAccountFormMode) {
          connectorAccountFormMode = null;
          editingConnectorAccount = null;
          dirty = false;
        }
        ```
     7. **Add new functions** (after the MCP block at ~L580):
        - `renderConnectorAccountsSection()` — mirror of `renderMcpSourcesSection()`. Branches: `if (!connectorAccountFormMode && self._pendingConnectorAccountFormMode === 'add')` → promote; `if (connectorAccountFormMode)` → mount placeholder editor with onBack / onCancel callbacks that clear state + replaceSub('connector-accounts') + re-render the section; else → mount grid + `fetchConnectorAccounts_()`.
        - `fetchConnectorAccountTypes()` — `fetch('/api/connector-accounts/types').then(...).then(types => { CONNECTOR_TYPES = types; }).catch(() => { CONNECTOR_TYPES = []; })`. Sets `connectorTypesReady`.
        - `fetchConnectorAccounts_()` — `fetch('/api/connector-accounts').then(...).then(data => { ... connectorAccounts = data; populateConnectorAccountsGrid(); })`. Stale-then guards.
        - `populateConnectorAccountsGrid()` — re-renders grid with current cache.
        - `selectConnectorAccount(id)` — sets form-mode='edit', editingAccount, clears pending, writes URL, re-renders.
        - `enterCreateConnectorAccountMode()` — sets form-mode='add', clears editing + pending, writes URL, re-renders.
        - `findConnectorAccount(id)` — array search through cache.
        - `tryConsumePendingConnectorAccount()` — mirror of `tryConsumePendingMcpSource`, exposed as `self._tryConsumePendingConnectorAccount`.
     8. **`setActiveSection`'s leave-section reset** (L591-595): add a `connector-accounts` exit branch:
        ```javascript
        if (prevSection === 'connector-accounts' && section !== 'connector-accounts') {
          connectorAccountFormMode = null;
          editingConnectorAccount = null;
          dirty = false;
        }
        ```
     9. **`setActiveSection`'s section dispatch** (L596-602): add an `else if (section === 'connector-accounts') renderConnectorAccountsSection();` branch.

5. **Update existing browser tests that hardcode the 3-section nav** — pre-implementation grep: `grep -rn "to_have_count(3)\|\"MCP Servers\"\\]" tests/browser/` and inspect each hit.
   - `tests/browser/test_flow_studio_mcp_navigation.py:28-36` (`test_studio_section_nav_includes_mcp_servers`):
     - `expect(items).to_have_count(3)` → `to_have_count(4)`.
     - `assert labels == ["Agents", "Knowledge", "MCP Servers"]` → `["Agents", "Knowledge", "MCP Servers", "Connector Accounts"]`.
     - Update the test's docstring/comment if it pins "3 entries" verbatim.
   - `tests/browser/test_flow_studio_navigation.py:38-46` (`test_studio_section_nav_renders_three_buttons`):
     - Rename function to `test_studio_section_nav_renders_four_buttons` (or `_renders_all_sections`).
     - `to_have_count(3)` → `to_have_count(4)`.
     - Add `buttons.nth(3)` assertion for "Connector Accounts".
   - `tests/browser/test_flow_studio_navigation.py:140-170` — keyboard-nav assertions. Audit EVERY wrap, End, ArrowDown/ArrowUp target. Concretely:
     - Any assertion that currently expects an arrow-key key press to wrap "from `mcp-sources` to `agents`" — update to "from `connector-accounts` to `agents`" (the new last → first wrap).
     - Any assertion that End lands on `mcp-sources` — update to `connector-accounts`.
     - Any assertion that ArrowUp from `agents` wraps to `mcp-sources` — update to `connector-accounts`.
     - Any assertion that ArrowDown from `mcp-sources` wraps — now it should go to `connector-accounts` (the new mid-list position; no wrap), and a NEW assertion that ArrowDown from `connector-accounts` wraps to `agents` should be added.
     - Read the block in full before editing; some of these may be combined into a single test that exercises the cycle end-to-end.

6. **Create `test_flow_studio_connector_account_navigation.py`**
   - Path: `tests/browser/test_flow_studio_connector_account_navigation.py`.
   - Mirror the 6 existing tests from `test_flow_studio_mcp_navigation.py` adapted for connector accounts. Plus the 7th: `test_studio_connector_accounts_new_button_opens_form_then_cancel_returns_to_grid`.
   - For test 6 (empty-canvas copy assertion), use a selector for the Flight-8-mention text or assert `expect(page.locator(".empty-canvas")).to_contain_text("Flight 8 will add Discord")`.
   - For test 7 (new-button → cancel round-trip):
     ```python
     page.goto(f"{app_clean}#studio/connector-accounts")
     page.wait_for_selector('[data-testid="new-connector-account-btn-empty"]', timeout=8000)
     page.locator('[data-testid="new-connector-account-btn-empty"]').click()
     # Verify form mounted
     expect(page.locator('[data-testid="connector-account-editor-placeholder"]')).to_be_visible(timeout=5000)
     assert page.evaluate("location.hash") == "#studio/connector-accounts/new"
     # Cancel
     page.locator('[data-testid="cancel-connector-account-btn"]').click()
     # Empty-canvas back
     expect(page.locator(".empty-canvas")).to_be_visible(timeout=5000)
     assert page.evaluate("location.hash") == "#studio/connector-accounts"
     ```

7. **Run scoped tests then full recipe**
   - `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_navigation.py tests/browser/test_flow_studio_mcp_navigation.py` — 13 tests green (7 new + 6 existing including the updated nav-count test).
   - `make test-browser` — full browser recipe green.
   - `make test` — full unit suite green (no regressions).
   - `make lint` — clean.

8. **Update artifacts and flight log**
   - Set this leg's status to `landed`.
   - Append a "Leg Progress" entry summarizing: grid file, placeholder editor file, studio.js routing wiring, types-route consumer, browser-test additions + updates, test deltas.
   - Append a "Design Adjustments" entry: minimal placeholder editor in this leg (leg 6 replaces it wholesale) — needed for the "New button opens form → Cancel returns to empty state" test to work without requiring leg 6 to land first.
   - Check off leg 5 in `flight.md`.
   - Do NOT commit.

## Edge Cases

- **`tests/browser/` snapshot baselines** — gitignored per `.gitignore:14-15` (user-global rule). Any visual snapshot assertions added by this leg's tests run against locally-regenerated baselines. The 7 new tests use DOM-shape assertions (no snapshots) so this isn't an issue, but the design-token sanity check (if added) MUST NOT commit baseline files.
- **`app_clean` fixture state** — `tests/browser/conftest.py` provides a clean DB per test. The connector_accounts table is empty by default; the empty-canvas test exercises this. If the test framework's `seeders.py` is consulted (e.g. for the future "list shows tile" test in leg 6), the seeder helper for connector accounts lands in leg 6, NOT this leg.
- **Section-nav 4th entry shifts layout** — confirm the sidebar accommodates 4 items visually without overflow. The CSS at `static/css/...` (TBD by recon) likely uses flex/grid that auto-fits; if there's a hardcoded width that breaks at 4 items, surface as a defect and resolve at the leg-6 design-language pass.
- **`KNOWN_CONNECTOR_BADGES` empty + CSS** — verified at design review: `admin-mcp-badge` has ZERO CSS rules anywhere; ALL badge styling rides on the base `.entity-tile-badge` class (`components.css:560`). The `admin-mcp-badge` class is purely a future hook for per-type color overrides (analogous to `--badge-discord` in the LLM-provider checklist). **No CSS work is needed in this leg.** The connector grid's `admin-connector-badge` / `admin-connector-badge--{type}` classes are present-as-future-hooks; no rule needs to land in `admin.css` or `tokens.css` until Flight 8 introduces a real type that wants a distinct color.
- **`window.App.escapeHtml` / `window.App.escapeAttr` availability** — both helpers are used by the MCP grid; they're defined elsewhere in the static JS (likely `app.js` or a shared utility). Confirm they're loaded BEFORE this leg's grid file. The script-src ordering at `index.html` already puts utility scripts first; the new tags slot in alongside the existing MCP grid (which uses the same helpers).
- **`renderConnectorAccountEditor`'s `types` parameter unused** — the placeholder editor doesn't render a type selector. The full editor in leg 6 will. Pass `types` through for forward-compatibility; leg 6 consumes it.
- **`fetchConnectorAccountTypes()` called when?** — mirror of MCP: the editor's render path awaits `connectorTypesReady` so type-selector dropdowns can populate. For this leg's placeholder editor, the call is technically unused but harmless; following the MCP pattern keeps the leg-6 transition clean.
- **`make test-browser` recipe** — verify it exists. If it doesn't, the browser tests run via `pytest -m browser` directly. Look at `Makefile` for the canonical invocation pattern.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js` — new file (~120 LoC).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — new minimal placeholder file (~50 LoC; replaced by leg 6).
- `the_one/interfaces/web/static/index.html` — 2 new `<script>` tags.
- `the_one/interfaces/web/static/js/areas/studio.js` — section nav extension + routing branches + new render/fetch functions (~250 LoC added, structurally parallel to the MCP block).
- `tests/browser/test_flow_studio_mcp_navigation.py` — 1 test updated (count + labels).
- `tests/browser/test_flow_studio_connector_account_navigation.py` — new file with 7 tests (~120 LoC).
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight-log.md` — Leg Progress + Design Adjustments entry.
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight.md` — leg-5 checkbox.

## State-Machine Reachability Audit

Routing state machine extended:
- `_activeSection` accepts a new value `'connector-accounts'`.
- New form-mode field `_connectorAccountFormMode` ∈ `{null, 'add', 'edit'}`.
- New pending-state fields `_pendingConnectorAccountId`, `_pendingConnectorAccountFormMode`.

These are operator-driven; no DB or backend state change. The existing MCP routing's form-mode machinery is the model — its lifecycle is well-understood and the connector branch mirrors it.

- **Existing tests pinning section count** — `test_studio_section_nav_includes_mcp_servers` (the leg updates it).
- **Hash-routing fixture (`conftest.py`)** — does NOT pin specific section names. Adding a new section doesn't break the fixture.

## Cache Freshness Contract

For the `connectorAccounts` closure-local cache in `studio.js`:

- **Source of truth**: `/api/connector-accounts` REST endpoint.
- **Rebuild trigger**: per-mount of the `connector-accounts` section. Re-fetches on every section entry (`fetchConnectorAccounts_()` runs in the grid render branch).
- **Maximum staleness**: until the operator navigates back into the section. An operator editing an account in another tab won't see the change reflected in this tab's grid until they navigate away and back. **Acceptable** — mirrors MCP precedent; the operator-facing contract is "your tab is your truth."
- **User-action invalidation map**:
  - Section entry → re-fetch.
  - Create / Update / Delete via the editor → return to grid + re-fetch (leg 6 handles this; this leg's placeholder Cancel just navigates back to the existing cache, which is unmodified).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test` clean (no unit-test regressions)
- [ ] `make test-browser` (or `pytest -m browser`) clean — all 7 new + 6 existing (with 1 updated) connector/MCP navigation tests green
- [ ] `make lint` clean
- [ ] Flight log updated with a "Leg Progress" entry AND a "Design Adjustments" entry naming the placeholder editor file
- [ ] This leg's status updated to `landed` (in this file's header)
- [ ] This leg checked off in `flight.md` Legs list
- [ ] Do NOT commit — review and commit happen once at the end of the flight per `/agentic-workflow`

---

## Citation Audit

8 code-location citations verified against current code at leg design time:

- `the_one/interfaces/web/static/js/areas/studio.js:23-43 — serializeState` — **OK** (verified; current MCP branch handles 4 URL forms).
- `the_one/interfaces/web/static/js/areas/studio.js:78-100 — hydrateState MCP parsing` — **OK** (verified).
- `the_one/interfaces/web/static/js/areas/studio.js:206-228 — closure-locals + Object.defineProperty for MCP state` — **OK** (verified).
- `the_one/interfaces/web/static/js/areas/studio.js:294-303 — section-nav array` — **OK** (verified; current 3 entries: Agents / Knowledge / MCP Servers).
- `the_one/interfaces/web/static/js/areas/studio.js:317-326 — onSelect confirm-leave block` — **OK** (verified; MCP branch at L322-326).
- `the_one/interfaces/web/static/js/areas/studio.js:354-602 — renderMcpSourcesSection + helpers` — **OK** (verified; the structural template).
- `the_one/interfaces/web/static/index.html:53-55 — script src ordering` — **OK** (verified; MCP grid + editor at L53-54, studio.js at L55).
- `tests/browser/test_flow_studio_mcp_navigation.py:28-80 — existing MCP nav tests` — **OK** (verified; 6 tests + the `to_have_count(3)` assertion at L34).

0 citations drifted, 0 unverifiable.
