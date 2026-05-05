# Leg: 06-editor-sub-module

**Status**: completed
**Flight**: [Encrypted MCP Source Persistence + Settings Page](../flight.md)

## Objective

Land the MCP source editor sub-module that replaces L5's placeholder. After L6, an operator can create, edit, and delete MCP sources for both transports through a Settings editor surface that mirrors the LLM Providers editor's structural shape, with per-key `__MASKED__` round-trip preservation, the deferred per-sensitive-field UI shape decided and implemented (unified key/value table with per-row sensitive checkbox), and an OAuth client config section visible for `streamable-http`.

## Context

L5 staged the closure-mirror, the URL routing, the grid sub-module, and a placeholder editor branch (`data-testid="mcp-editor-placeholder"`) when `mcpSourceFormMode` is non-null. L6 swaps the placeholder for `App.admin.renderMcpSourceEditor` and wires the orchestrator-side callbacks (`onSaveSuccess`, `onDeleteSuccess`, `onBack`, `onCancel`, `onDirtyChange`).

The flight spec line 29 leaves the per-sensitive-field UI shape OPEN, with three candidate shapes. **L6 design picks option (c): unified key/value table with per-row sensitive toggle** for the dynamic-key fields (env vars for stdio, custom headers for streamable-http). Rationale:

- The operator's mental model for env vars is "I have a dict of strings; some are secrets". A unified table mirrors that mental model directly. Splitting into two sections (option b) forces the operator to mentally distinguish which section a future field belongs to before they know whether it's sensitive — premature decision-forcing.
- A chip-list (option a) is too compact for a key-value pair with a per-item state (sensitive checkbox). A table row gives each field room for the key input, value input, sensitive checkbox, and eye-toggle without horizontal cramming.
- The user's hint during mission interview ("Probs a check box to mark as sensitive") points to a per-row checkbox, which both option (a) and option (c) provide. Option (c) gives more visual structure for a typically small but sometimes-many-row dataset.

**Static-shape fields are NOT in the dynamic table** — name, type, transport-specific structural fields (command/cwd/url), and the OAuth client config sub-section have their own fixed positions:

- **Common**: `name` (text input, required), `type` (select: stdio | streamable-http)
- **stdio-specific**: `command` (text input, required), `args` (chip-list of strings, optional), `cwd` (text input, optional)
- **streamable-http-specific**: `url` (text input, required)
- **streamable-http OAuth sub-section** (collapsible — collapsed by default): `issuer_url`, `client_id`, `scopes` (chip-list), `redirect_uri` (all text/list, plaintext); `client_secret` (always-sensitive, eye-toggle, masked-sentinel preserved). The "always sensitive" `client_secret` is the only field whose `sensitive` flag is forced; all other OAuth fields are plaintext-only by design (DCR scopes/clientId/issuerURL are inherently public per OAuth 2.1).
- **Dynamic kv table** (one per transport):
  - stdio: labeled "Environment Variables" — non-sensitive rows route into `config.env` plaintext dict; sensitive rows route into `secrets[key]`
  - streamable-http: labeled "Custom Headers" — non-sensitive rows route into `config.headers` plaintext dict; sensitive rows route into `secrets[key]`

**Save-time payload assembly**: the editor walks the form, partitions plaintext from sensitive, builds `{name, type, config: {...transport-fields..., env|headers|oauth}, secrets: {...sensitive-kv..., oauth_client_secret?}}`, and POSTs/PUTs. **Per-key `__MASKED__` round-trip**: for each sensitive kv row whose value field still equals the originally rendered masked tail (`***...{tail4}` or `***`), the editor substitutes the literal `__MASKED__` sentinel in the payload. The L3 endpoint's per-key sentinel handler (api.py — `update_mcp_source`) then preserves the stored secret for that key. Same semantic as the provider editor's single-key MASKED_SENTINEL; generalized per-row.

**Locked contract: OAuth `client_secret` payload key.** The OAuth client secret is routed into `secrets["oauth_client_secret"]` (top-level key in the secrets dict, NOT nested under `config.oauth`). Rationale: the encryption boundary is the `secrets` column (per the field-segregated decision in flight-spec line 34); a nested `config.oauth.client_secret` would leak through any code path that reads `config` plaintext. F5 (OAuth flow) MUST look up the client secret by the literal string key `"oauth_client_secret"` and NOT under `config.oauth.client_secret`. F2 consumers calling `MCPSource.merged_config()` see a flat dict where the secret appears at top-level (since `merged_config` overlays secrets onto config; the secret "wins" any collision); this means `merged_config()["oauth_client_secret"]` works. **This contract is locked in L6** and referenced from F5's leg specs.

Open question during L6 design that the user's earlier mission-interview answer already resolved: **client_secret is sensitive by default** with no operator override (the checkbox is locked-on-and-disabled in the UI). All other OAuth client fields (issuer_url, client_id, scopes, redirect_uri) are plaintext-only with no sensitive checkbox at all (DCR conventions per the MCP 2025-11-25 spec).

L6 does NOT touch:
- Backend API (L1-L4 supplied the surface; L6 calls existing `/api/mcp-sources` POST/PUT/DELETE plus `/api/mcp-sources/types`)
- The L5 grid sub-module, sidebar nav, or hash routing
- The L7 (optional) HAT walkthrough — that's a separate leg
- Live connection logic — that's F2
- OAuth token-acquisition flow — that's F5

## Inputs

- L1 + L2 + L3 + L4 + L5 have landed
- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` (451 lines) — the canonical structural template. Anchor by symbol:
  - `renderProviderEditor(container, provider, providerTypes, callbacks)` signature (line 41)
  - `renderConnectionFields` (line 114)
  - `getFormSnapshot` + `checkDirty` dirty-tracking pattern (lines 163, 200)
  - MASKED_SENTINEL preservation at lines 191–198, 444–446 (the canonical "if user didn't modify the pre-filled masked value, send `__MASKED__`" pattern)
  - `wireEditorEvents` (line 172)
  - `collectFormData` payload-assembly (line 413)
  - Type-change show/hide pattern (lines 220–232)
  - Eye-toggle pattern (lines 234–249)
  - Back / Cancel / Save handlers (lines 251–314)
  - Delete + `App.confirmDelete` wiring (lines 351–410) — note: provider-editor has an `agents` agent-usage pre-gate; L6 does NOT mirror the agent-usage pre-gate (MCP sources are not yet attached to agents — that's F4. F4 will add the agent-usage pre-gate when per-agent MCP attachment lands.)
- `the_one/interfaces/web/static/js/areas/admin.js` post-L5 (886 lines) — the orchestrator with the `renderMcpSourcesPanel` placeholder branch at lines 620–623 (verified post-L5; previous leg drafts cited line 613 which is the function header). L6 replaces the placeholder branch with a `App.admin.renderMcpSourceEditor` invocation following the providers `renderProvidersPanel` pattern at lines 252–335. The closure mirror (`mcpSourceFormMode`, `editingMcpSource`, `pendingMcpSourceId`, `pendingMcpSourceFormMode`, `dirty`) is already in place from L5 — L6 does not extend it.
- `the_one/interfaces/web/static/js/areas/admin.js:174` — `var PROVIDER_TYPES = [];` (L6 mirrors with `var MCP_TYPES = [];`).
- `the_one/interfaces/web/static/js/areas/admin.js:197` — `function fetchProviderTypes()` (L6 mirrors with `function fetchMcpSourceTypes()`).
- `the_one/interfaces/web/static/js/areas/admin.js:875` — bottom-of-init `fetchProviderTypes();` call, just before `renderContent();` (L6 appends `fetchMcpSourceTypes();` here).
- `the_one/interfaces/web/static/js/areas/admin/providers-grid.js` — UNCHANGED reference (no L6 edits).
- `the_one/interfaces/web/static/js/areas/admin/mcp-servers-grid.js` (post-L5) — UNCHANGED reference (no L6 edits).
- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` — reusable chip-list helpers: `App.adminFormHelpers.renderChipListEditor`, `readChipListValue`, `wireChipListEditor` (exports at line 518–521). L6 reuses these for `args` (stdio) and `scopes` (streamable-http OAuth). Implementer: re-read this file before implementing the chip-list parts of the editor.
- `the_one/interfaces/web/static/index.html` — script registration list. L6 inserts `<script src="/static/js/areas/admin/mcp-server-editor.js"></script>` AFTER the existing `provider-editor.js` registration (line 53). This placement (a) mirrors the providers-grid → provider-editor pairing structurally, and (b) ensures `tools-form-helpers.js` (registered at line 50) is loaded BEFORE the editor consumes its chip-list helpers.
- `the_one/interfaces/web/api.py` — L6 consumers of:
  - `GET /api/mcp-sources/types` (returns `[{value, label}, ...]`) — for the type select
  - `POST /api/mcp-sources` (create)
  - `PUT /api/mcp-sources/{id}` (update; per-key `__MASKED__` honored)
  - `DELETE /api/mcp-sources/{id}` (delete)
- `tests/browser/test_flow_provider_editor.py` — pattern reference for create + edit + delete browser tests, including `MASKED_SENTINEL` round-trip assertions
- `tests/browser/test_flow_admin_mcp_navigation.py` (post-L5) — `test_admin_mcp_placeholder_navigation_skips_confirm` MUST be updated/removed in L6 because the placeholder is replaced by a real (potentially-dirty) editor; the dirty-gate-with-no-edits path still works because a fresh editor's `dirty` is false until first input.

## Outputs

- `the_one/interfaces/web/static/js/areas/admin/mcp-server-editor.js` (NEW, ~600–750 lines) — exports `App.admin.renderMcpSourceEditor(container, source, mcpTypes, callbacks)`. Mirrors `provider-editor.js` structural shape with the L6-specific extensions enumerated below.
- `the_one/interfaces/web/static/js/areas/admin.js` updates:
  - In `renderMcpSourcesPanel` (around line 613, post-L5): replace the placeholder branch with a `mcpTypes`-fetched delegation to `App.admin.renderMcpSourceEditor`. Add `fetchMcpSourceTypes` (mirrors `fetchProviderTypes` at lines 153–159 — fetches `/api/mcp-sources/types` once, caches into `MCP_TYPES`).
  - In `init()`: declare `var MCP_TYPES = [];` and `var mcpTypesReady = null;` near the existing `PROVIDER_TYPES` block (line 137).
  - Init block at line 690: call `fetchMcpSourceTypes()` alongside `fetchProviderTypes()`.
- `the_one/interfaces/web/static/index.html` — new `<script>` registration for the editor sub-module.
- `tests/browser/test_flow_admin_mcp_editor.py` (NEW) — Playwright tests covering create/edit/delete cycles for both transports plus per-key MASKED_SENTINEL round-trip.
- `tests/browser/test_flow_admin_mcp_navigation.py` updates — TWO L5 tests need refactor or delete (the L5 placeholder is gone post-L6):
  - `test_admin_direct_load_mcp_sources_new_renders_placeholder` (L5) — refactor to `test_admin_direct_load_mcp_sources_new_renders_editor` and assert the editor's `[data-testid="save-mcp-source-btn"]` (or `[data-field="name"]`) is visible. Update the docstring.
  - `test_admin_mcp_placeholder_navigation_skips_confirm` (L5) — DELETE (covered by editor's own dirty/clean tests in `test_flow_admin_mcp_editor.py`). The editor's `test_dirty_back_confirm_dialog` plus an inverse "clean editor + back skips confirm" assertion captures the same contract more directly.
- `missions/07-mcp-integration/flights/01-encrypted-persistence-and-settings/flight-log.md` — `### 06-editor-sub-module` entry appended.

## Acceptance Criteria

- [x] NEW file `the_one/interfaces/web/static/js/areas/admin/mcp-server-editor.js` exports `App.admin.renderMcpSourceEditor(container, source, mcpTypes, callbacks)` matching the signature shape of `renderProviderEditor`. The `source` parameter is `null` for create, an `MCPSource` object for edit. The `callbacks` accepts `onBack`, `onCancel`, `onSaveSuccess`, `onDeleteSuccess`, `onDirtyChange` (same names as the provider editor).
- [x] Editor header renders: title (source.name | "New MCP Server"), subtitle in edit mode (`{type} · {url-or-command-summary}`), back button, cancel button (disabled-while-clean), save button (Create | Save), error span. NO test button (live connection logic is F2).
- [x] Connection section renders the static structural fields:
  - `name` (required, plaintext text input)
  - `type` (select populated from `mcpTypes`; `mcpTypes[].value` ∈ {stdio, streamable-http})
  - On `type` change: show/hide transport-specific structural fields AND swap the kv-table label between "Environment Variables" (stdio) and "Custom Headers" (streamable-http). Show/hide the OAuth sub-section to match (visible for streamable-http only).
- [x] stdio-only fields: `command` (text, required when type=stdio), `cwd` (text, optional), `args` (chip-list of strings).
- [x] streamable-http-only fields: `url` (text, required when type=streamable-http).
- [x] Dynamic kv table renders one row per existing entry, plus an empty trailing "+ Add row" button. Each row has: key input, value input, sensitive checkbox, eye-toggle (only visible when sensitive=true), remove-row button. The kv table is a SINGLE table per editor — its label and routing-target switch with `type` (env vars + secrets for stdio, headers + secrets for streamable-http).
- [x] OAuth client config sub-section (rendered ONLY when type=streamable-http) shows: `issuer_url` (text), `client_id` (text), `scopes` (chip-list), `redirect_uri` (text), `client_secret` (sensitive, eye-toggle, MASKED_SENTINEL-preserved on edit). The `client_secret` checkbox is locked-on (visually disabled but checked) — the operator cannot mark it non-sensitive.
- [x] Danger Zone section renders ONLY in edit mode with a `delete-btn` wired through `App.confirmDelete`. NO agent-usage pre-gate (F4 will add this). Bare `App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' })`.
- [x] Dirty tracking via `getFormSnapshot` + `checkDirty` (mirrors provider editor lines 163–210). The form snapshot includes ALL static fields, ALL kv-table rows (key + value + sensitive flag), ALL chip-list items (args, scopes), and ALL OAuth fields. Snapshot is captured at editor mount AND recaptured after a successful save (so subsequent typing dirties from the post-save baseline).
- [x] `onDirtyChange` callback fires on every dirty-state change, mirroring provider editor line 209.
- [x] Save click POSTs (create) or PUTs (edit) to `/api/mcp-sources` or `/api/mcp-sources/{id}`. Payload assembly walks the form, partitions sensitive vs plaintext, builds `{name, type, config, secrets}`. For sensitive kv rows whose value field equals the originally rendered masked value (captured at mount as `originalMaskedSecrets[key]`), the payload's `secrets[key]` is the literal string `'__MASKED__'`. The OAuth `client_secret`'s MASKED_SENTINEL handling mirrors the same per-key shape via `secrets['oauth_client_secret']`.
- [x] On save success: `onSaveSuccess(updated, isCreate)` fires. The orchestrator handles state mutation (mcpSourceFormMode = 'edit', editingMcpSource = updated). Re-render the editor (so create→edit transition shows Danger Zone + edit-mode subtitle).
- [x] On delete success: `onDeleteSuccess()` fires. The orchestrator navigates back to the grid.
- [x] On Back: if dirty, the orchestrator's `App.confirmDialog` gate fires (mirrors the provider pattern at admin.js:278–284); if clean, navigates back to the grid directly.
- [x] Cancel button in edit mode reverts the form to the snapshot (no fetch); in create mode invokes `onCancel` (orchestrator navigates to grid).
- [x] Eye-toggle on each sensitive kv row + on `client_secret` toggles input type between `password` and `text`, mirrors the provider editor's API-key eye-toggle.
- [x] Per-key MASKED_SENTINEL round-trip preserves stored secrets across edit: an operator editing only the name field sees the existing sensitive values pre-filled with the masked-tail string; on save, those values still equal the masked-tail and the payload sends `'__MASKED__'` for each, preserving the stored ciphertext.
- [x] L5's `data-testid="mcp-editor-placeholder"` is no longer rendered post-L6; the L5 placeholder tests (`test_admin_direct_load_mcp_sources_new_renders_placeholder` and `test_admin_mcp_placeholder_navigation_skips_confirm`) are updated/removed accordingly.
- [x] `collectFormData` routes by `type`, NOT by visible-field set. Switching `type` then immediately saving (before dirty handler fires) emits the type-correct payload; never includes the wrong-transport's fields. (Locked invariant: `command` is read only when `type === 'stdio'`; `url` is read only when `type === 'streamable-http'`.)
- [x] NEW file `tests/browser/test_flow_admin_mcp_editor.py` covers AT LEAST 9 tests:
  - `test_create_stdio_source` — fill the form, submit, see the source in the grid post-save
  - `test_create_streamable_http_source_with_oauth` — fill the form including OAuth client config, submit, edit the source and verify all OAuth fields round-trip
  - `test_edit_stdio_source_preserves_unchanged_secrets` — pre-existing source with sensitive env vars; edit only the name; save; reload the editor; verify the sensitive env vars still decrypt to the original values (verified via the masked-tail equality check)
  - `test_edit_streamable_http_source_changes_one_secret` — pre-existing source with two sensitive headers; change one, leave the other; save; verify the changed one is overwritten and the unchanged one is preserved (per-key MASKED_SENTINEL)
  - `test_delete_stdio_source` — confirmDelete two-click flow; source disappears from the grid
  - `test_delete_streamable_http_source` — same as above for streamable-http
  - `test_dirty_back_confirm_dialog` — make the form dirty, click Back, confirm dialog appears, cancel keeps the editor mounted
  - `test_type_change_swaps_field_visibility` — switch type from stdio to streamable-http; assert command field hidden, url field shown, kv-table label changes, OAuth sub-section becomes visible
  - `test_save_with_empty_kv_key_row_silently_skips` — add an empty kv row (no key, no value) plus a populated row; save; the populated row persists and the empty row is dropped (not stored as a `""` key). Pins the "kv row with empty key: skipped at partition time" edge case.
- [x] `the_one/interfaces/web/static/js/areas/admin.js` `renderMcpSourcesPanel` no longer renders the L5 placeholder; instead delegates to `App.admin.renderMcpSourceEditor` with the same callback shape as `renderProvidersPanel`'s editor branch
- [x] `admin.js` declares `MCP_TYPES = []` + `mcpTypesReady = null` and `fetchMcpSourceTypes()` (mirroring `fetchProviderTypes`)
- [x] `admin.js` Init block fires `fetchMcpSourceTypes()` alongside `fetchProviderTypes()`
- [x] `the_one/interfaces/web/static/index.html` registers `mcp-server-editor.js` (new `<script>` tag after the existing `mcp-servers-grid.js` registration)
- [x] `tests/browser/test_flow_admin_mcp_navigation.py::test_admin_mcp_placeholder_navigation_skips_confirm` is either deleted (placeholder no longer exists) or refactored to assert clean-editor navigation skips the confirm dialog
- [x] `make lint` clean
- [x] `make test-browser` green (admin sweep + new MCP editor tests)

## Verification Steps

- `pytest tests/browser/test_flow_admin_mcp_editor.py tests/browser/test_flow_admin_mcp_navigation.py -v --timeout=120` — green
- `pytest tests/browser/ -k "admin or mcp" -v --timeout=120` — full admin + MCP browser sweep green
- `make test-browser` — full browser suite green
- `make lint` — clean
- Manual: open `#admin/mcp-sources/new` → editor renders with Connection section + empty kv table + (when type=streamable-http selected) OAuth section. Fill stdio source, save, see grid update. Click tile, edit only name, save, reload — sensitive env vars unchanged. Click delete, confirm twice, source removed from grid.

## Implementation Guidance

This leg is the largest in the flight (~600–750 LOC of new JS + ~300 LOC of new browser tests). The implementation MUST follow the provider-editor structural shape — the wireEditorEvents pattern, dirty-tracking shim, masked-sentinel capture, fetch-and-callback shape are all canonical. Departures are flagged inline.

1. **Re-locate L5 integration points**. Before any edits run:
   ```
   grep -n "renderMcpSourcesPanel\|mcp-editor-placeholder\|fetchMcpSources\|MCP_TYPES" the_one/interfaces/web/static/js/areas/admin.js
   wc -l the_one/interfaces/web/static/js/areas/admin/provider-editor.js the_one/interfaces/web/static/js/areas/admin/mcp-servers-grid.js
   ```

2. **Create `the_one/interfaces/web/static/js/areas/admin/mcp-server-editor.js`** mirroring `provider-editor.js` shape. The high-level structure:

   ```javascript
   (function () {
     'use strict';
     window.App = window.App || {};
     window.App.admin = window.App.admin || {};

     // Per-row data shape: { key, value, sensitive }. The value is either
     // plaintext (sensitive=false) OR a masked tail (sensitive=true, edit
     // mode, unchanged) OR a fresh plaintext (sensitive=true, user-typed).

     function renderMcpSourceEditor(container, source, mcpTypes, callbacks) {
       callbacks = callbacks || {};
       var escapeHtml = window.App.escapeHtml;
       var escapeAttr = window.App.escapeAttr;
       var isCreate = !source;
       var name = isCreate ? 'New MCP Server' : (source.name || '');
       var type = isCreate ? '' : source.type;

       // ── Header HTML ─────────────────────────────────────────────────
       // Mirrors provider-editor.js:48-70 with substitutions:
       //   data-testid="back-mcp-source-btn", "cancel-mcp-source-btn",
       //   "save-mcp-source-btn"
       // No test-mcp-source-btn (live connection is F2).
       var html = '';
       html += '<div class="editor-header">' + ... + '</div>';

       // ── Connection section ──────────────────────────────────────────
       html += '<div class="editor-section">';
       html += '<div class="section-title">Connection</div>';
       html += renderConnectionFields(source, mcpTypes);
       html += '</div>';

       // ── Environment / Headers section ───────────────────────────────
       html += '<div class="editor-section">';
       html += '<div class="section-title kv-section-title" data-stdio-label="Environment Variables" data-streamable-http-label="Custom Headers">' +
         (type === 'streamable-http' ? 'Custom Headers' : 'Environment Variables') + '</div>';
       html += renderKvTable(source, type);
       html += '</div>';

       // ── OAuth section (streamable-http only, hidden by default) ─────
       html += '<div class="editor-section mcp-oauth-section' + (type === 'streamable-http' ? '' : ' is-hidden') + '">';
       html += '<div class="section-title">OAuth Client Configuration</div>';
       html += renderOAuthFields(source);
       html += '</div>';

       // ── Danger Zone (edit only) ─────────────────────────────────────
       if (!isCreate) {
         html += '<div class="editor-section danger-zone">';
         html += '<div class="section-title danger-zone-title">Danger Zone</div>';
         html += '<button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-mcp-source-btn"><span data-confirm-title>Delete MCP Server</span></button>';
         html += '</div>';
       }

       container.innerHTML = html;
       wireEditorEvents(container, source, mcpTypes, callbacks);
     }

     // ... renderConnectionFields, renderKvTable, renderOAuthFields,
     //     wireEditorEvents, getFormSnapshot, collectFormData, ...

     window.App.admin.renderMcpSourceEditor = renderMcpSourceEditor;
   })();
   ```

3. **`renderConnectionFields(source, mcpTypes)`** renders the static structural fields with transport-aware visibility. Mirrors provider-editor's `renderConnectionFields` (line 114) but:
   - `name` field unchanged in shape
   - `type` select rendered from `mcpTypes`
   - `command` field with `data-field="command"` and a wrapper class `mcp-stdio-only` (visible when type=stdio)
   - `cwd` field with `data-field="cwd"`, wrapper class `mcp-stdio-only`
   - `args` chip-list — reuse `App.adminFormHelpers.renderChipListEditor` (see Step 3a). Wrapper class `mcp-stdio-only`.
   - `url` field with `data-field="url"`, wrapper class `mcp-streamable-http-only` (visible when type=streamable-http)
   - Initial visibility set per `type`; `wireEditorEvents` toggles on type-change.

3a. **Reuse `App.adminFormHelpers.renderChipListEditor` for chip-list fields**. The existing helper at `tools-form-helpers.js:267-305` produces the chip-list DOM; `wireChipListEditor` (line 359+) wires the input/event handlers; `readChipListValue` (line 307-316) reads the array of items. L6 reuses these for `args` (stdio command-line arguments) and OAuth `scopes` (streamable-http). The helper renders into a container with `class="chip-list-editor"`; the container carries `[data-field]` so it appears in the form-snapshot walk. Implementation:
   ```javascript
   // After container.innerHTML = html; in renderMcpSourceEditor, mount the chip-list editors
   var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
   if (argsHost) {
     App.adminFormHelpers.renderChipListEditor(argsHost, (source && source.config && source.config.args) || []);
     App.adminFormHelpers.wireChipListEditor(argsHost, function () { checkDirty(); });
   }
   var scopesHost = container.querySelector('[data-field="oauth-scopes"].chip-list-editor');
   if (scopesHost) {
     App.adminFormHelpers.renderChipListEditor(scopesHost, (source && source.config && source.config.oauth && source.config.oauth.scopes) || []);
     App.adminFormHelpers.wireChipListEditor(scopesHost, function () { checkDirty(); });
   }
   ```
   This eliminates ~100 LOC of duplicated chip-list rendering. **Script-load ordering invariant**: `mcp-server-editor.js` MUST load AFTER `tools-form-helpers.js` (see Step 12).

4. **`renderKvTable(source, type)`** renders the dynamic kv table:
   ```javascript
   function renderKvTable(source, type) {
     var existingRows = collectExistingKvRows(source, type);
     var html = '<table class="mcp-kv-table" data-testid="mcp-kv-table">';
     html += '<thead><tr><th>Key</th><th>Value</th><th>Sensitive</th><th></th></tr></thead>';
     html += '<tbody>';
     for (var i = 0; i < existingRows.length; i++) {
       html += renderKvRow(existingRows[i], i);
     }
     html += '</tbody></table>';
     html += '<button type="button" class="btn-outlined-cyan kv-add-row-btn" data-testid="kv-add-row-btn">+ Add row</button>';
     return html;
   }
   ```

   Where `collectExistingKvRows` walks `source.config.env` (stdio) or `source.config.headers` (streamable-http) AND `source.secrets` to build the union list. Per-row mount-time data:
   ```javascript
   { key: 'GITHUB_TOKEN', value: '***...alue', sensitive: true, _originalMasked: '***...alue' }
   ```
   The `_originalMasked` field is captured per-row at mount; if the value field still equals `_originalMasked` at save time, the payload sends `'__MASKED__'` for that key. NEW rows (added via the add-button) have `_originalMasked: null` and never trigger the sentinel.

5. **`renderKvRow(row, idx)`** renders a single tr:
   ```javascript
   function renderKvRow(row, idx) {
     return '<tr data-row-idx="' + idx + '">' +
       '<td><input class="field-input kv-key-input" data-field="kv-key" data-row="' + idx + '" value="' + escapeAttr(row.key) + '" placeholder="KEY" /></td>' +
       '<td><div class="api-key-wrap"><input class="field-input kv-value-input ' + (row.sensitive ? 'kv-value-secret' : '') +
       '" type="' + (row.sensitive ? 'password' : 'text') + '" data-field="kv-value" data-row="' + idx +
       '" value="' + escapeAttr(row.value) + '" data-original-masked="' + escapeAttr(row._originalMasked || '') + '" />' +
       (row.sensitive ? '<button class="api-key-eye kv-eye-btn" type="button" data-row="' + idx + '" aria-label="Show value">' + window.App.icon('eye') + '</button>' : '') +
       '</div></td>' +
       '<td><input type="checkbox" class="kv-sensitive-checkbox" data-field="kv-sensitive" data-row="' + idx + '"' + (row.sensitive ? ' checked' : '') + ' /></td>' +
       '<td><button type="button" class="kv-remove-row-btn" data-row="' + idx + '" aria-label="Remove row">' + window.App.icon('x') + '</button></td>' +
       '</tr>';
   }
   ```

6. **`renderOAuthFields(source)`** renders the OAuth client config section:
   - `issuer_url` (text, plaintext, `data-field="oauth-issuer-url"`)
   - `client_id` (text, plaintext, `data-field="oauth-client-id"`)
   - `scopes` chip-list (`data-field="oauth-scopes"`)
   - `redirect_uri` (text, plaintext, `data-field="oauth-redirect-uri"`)
   - `client_secret` (password input, `data-field="oauth-client-secret"`, eye-toggle, `data-original-masked="..."`); the sensitive checkbox is rendered alongside but disabled+checked: `<input type="checkbox" checked disabled aria-label="OAuth client secret is always sensitive" />`.

7. **`wireEditorEvents(container, source, mcpTypes, callbacks)`** wires:
   - Type-change handler: hides/shows `.mcp-stdio-only` and `.mcp-streamable-http-only` field rows; hides/shows `.mcp-oauth-section`; updates the kv-section title via `data-stdio-label` / `data-streamable-http-label` lookup; calls `checkDirty`.
   - **Recommended pattern: event delegation on the kv `<table>`** rather than per-row listener attach. Single delegated listeners on `<table>` handle (a) input on key/value text inputs, (b) change on sensitive checkbox, (c) click on eye-toggle, (d) click on remove-row button — dispatch by checking the event target's class. Eliminates the leak risk of per-row attach + simplifies the add-row code (no per-row event-listener attach — the delegated handler picks up new rows automatically).
   - Static fields (`.field-input`, `.field-select` outside the kv-table): `input` + `change` listeners on each.
   - kv add-row button: appends a new empty row to the tbody, calls `checkDirty`. (No per-row listener attach — delegation handles it.)
   - kv remove-row dispatch (delegated): remove the tr, call `checkDirty`.
   - kv sensitive-checkbox change dispatch (delegated): toggle the value input's `type` between `password`/`text`, render/remove the eye-toggle button on that row, call `checkDirty`. **Critical**: toggling from sensitive=true to sensitive=false on a row whose value still equals `_originalMasked` MUST clear the value field (`input.value = ''`); otherwise the masked tail (`***...alue`) leaks into the plaintext `config.env` / `config.headers` dict on save. Add an inline hint under the kv table: "Sensitive values are encrypted at rest. Unchecking 'Sensitive' on a stored secret clears the value — re-type to keep it."
   - Eye-toggle per kv row + OAuth client_secret: same pattern as provider editor.
   - Back / Save / Delete handlers: structurally identical to provider editor, with the `collectFormData`-equivalent producing `{name, type, config, secrets}` instead of `{name, type, base_url, api_key}`.
   - **Cancel handler in edit mode requires DOM rebuild for the kv table**, NOT just a value-restore loop. Provider-editor's Cancel reverts via `JSON.parse(snapshot); fields[j].value = snap[...]` — that pattern only handles value restoration. The kv table's row count can change during edit (operator added/removed rows), so a full rebuild from `source` is needed:
     ```javascript
     // Cancel-in-edit-mode revert:
     // 1. Restore static fields by snapshot value-loop (mirrors provider-editor)
     // 2. Rebuild kv-table by re-rendering from source (NOT from snapshot — the
     //    snapshot has the masked tails for sensitive rows, but rebuilding from
     //    source preserves the masked-tail AND _originalMasked correctly via
     //    collectExistingKvRows/renderKvRow)
     // 3. Rebuild chip-list editors by re-mounting via App.adminFormHelpers.renderChipListEditor
     ```
     Cancel-in-create-mode delegates to `onCancel` (orchestrator navigates to grid).

8. **`getFormSnapshot(container)`** extends the provider-editor pattern but the kv-table rows force a non-flat shape. The provider-editor snapshot uses `data[fields[i].dataset.field] = fields[i].value;` — a flat dict keyed by `data-field`. With the kv table, multiple rows share `data-field="kv-key"` / `kv-value"` / `kv-sensitive"` — flat-dict assignment would collide and only retain the last row.

   Walk in three explicit passes:
   - **Static pass**: select `[data-field]` inputs/selects EXCLUDING the kv-table cells (filter by `:not(.mcp-kv-table [data-field])` OR walk `.editor-section [data-field]:not(.kv-key-input):not(.kv-value-input):not(.kv-sensitive-checkbox)`). Build `static = {name, type, command, cwd, url, oauth-issuer-url, oauth-client-id, oauth-redirect-uri, oauth-client-secret}`.
   - **Chip-list pass**: walk `[data-field].chip-list-editor` containers and call `App.adminFormHelpers.readChipListValue(el)` on each. Build `chips = {args: [...], 'oauth-scopes': [...]}`.
   - **kv-rows pass**: walk `tr[data-row-idx]` in the kv-table tbody, in DOM order. Per row, extract `key`, `value`, `sensitive` from the row's three inputs/checkbox. Build `kvRows = [{key, value, sensitive}, ...]` preserving order.

   Final snapshot: `JSON.stringify({ static: static, chips: chips, kvRows: kvRows })`. Cheap equality via `current !== snapshot` string compare.

9. **`collectFormData(container, isEdit)`** assembles the payload:
   ```javascript
   function collectFormData(container, isEdit) {
     var name = container.querySelector('[data-field="name"]').value.trim();
     if (!name) { ...error...; return null; }
     var type = container.querySelector('[data-field="type"]').value;
     if (!type) { ...error...; return null; }

     var config = {};
     var secrets = {};

     if (type === 'stdio') {
       config.command = container.querySelector('[data-field="command"]').value.trim();
       if (!config.command) { ...error...; return null; }
       config.cwd = container.querySelector('[data-field="cwd"]').value.trim() || undefined;
       config.args = collectChipList(container, 'args');
       config.env = {};
       partitionKvRows(container, config.env, secrets);
     } else if (type === 'streamable-http') {
       config.url = container.querySelector('[data-field="url"]').value.trim();
       if (!config.url) { ...error...; return null; }
       config.headers = {};
       partitionKvRows(container, config.headers, secrets);
       // OAuth section
       var oauth = collectOAuthSection(container, secrets);
       if (oauth) config.oauth = oauth;
     }

     return { name: name, type: type, config: config, secrets: secrets };
   }
   ```

   Where `partitionKvRows(container, plaintextDict, secretsDict)` iterates the tbody rows and routes each row's `value` into the right dict, applying the per-row MASKED_SENTINEL substitution when sensitive and value === `_originalMasked`. Rows with empty key are skipped.

   `collectOAuthSection(container, secretsDict)` reads the four plaintext OAuth fields into a dict (returns null if all four are empty in create mode) and routes `client_secret` into `secretsDict['oauth_client_secret']` with the same MASKED_SENTINEL semantic.

10. **In `the_one/interfaces/web/static/js/areas/admin.js`**: add `MCP_TYPES`/`mcpTypesReady` near `var PROVIDER_TYPES = [];` (line 174). Add `fetchMcpSourceTypes` near `function fetchProviderTypes()` (line 197). Mirror exactly:
    ```javascript
    var MCP_TYPES = [];
    var mcpTypesReady = null;
    function fetchMcpSourceTypes() {
      mcpTypesReady = fetch('/api/mcp-sources/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { MCP_TYPES = types; })
        .catch(function () { MCP_TYPES = []; });
      return mcpTypesReady;
    }
    ```
    Init block at line 875 (the bottom-of-init `fetchProviderTypes();` call, just before `renderContent();`): append `fetchMcpSourceTypes();` immediately after.

11. **Replace L5 placeholder branch** in `renderMcpSourcesPanel` (around admin.js:613, post-L5). Mirror `renderProvidersPanel`'s editor branch at lines 252–322:
    ```javascript
    function renderMcpSourcesPanel() {
      // Editor branch (L6 — replaces the L5 placeholder)
      if (mcpSourceFormMode) {
        dirty = false;
        var ready = mcpTypesReady || fetchMcpSourceTypes();
        ready.then(function () {
          function doHandleBack() {
            mcpSourceFormMode = null;
            editingMcpSource = null;
            dirty = false;
            if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
            renderMcpSourcesPanel();
          }
          App.admin.renderMcpSourceEditor(contentEl, editingMcpSource, MCP_TYPES, {
            onBack: function () {
              if (dirty) {
                App.confirmDialog({ onConfirm: doHandleBack });
                return;
              }
              doHandleBack();
            },
            onCancel: function () {
              mcpSourceFormMode = null;
              editingMcpSource = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
              renderMcpSourcesPanel();
            },
            onSaveSuccess: function (updated, isCreate) {
              editingMcpSource = updated;
              mcpSourceFormMode = 'edit';
              dirty = false;
              if (window.App && window.App.router) {
                App.router.replaceSub(self.serializeState());
              }
              if (isCreate) {
                renderMcpSourcesPanel();
              }
            },
            onDeleteSuccess: function () {
              mcpSourceFormMode = null;
              editingMcpSource = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
              renderMcpSourcesPanel();
            },
            onDirtyChange: function (d) { dirty = d; }
          });
        });
        return;
      }
      // Grid branch (UNCHANGED from L5)
      App.admin.renderMcpServersGrid(contentEl, mcpSources, {
        selectedId: editingMcpSource ? editingMcpSource.id : null,
        onSelectMcpSource: selectMcpSource,
        onCreateMcpSource: enterCreateMcpSourceMode
      });
      fetchMcpSources();
    }
    ```

12. **Register the editor sub-module** in `the_one/interfaces/web/static/index.html`. Insert AFTER the existing `provider-editor.js` registration (line 53), NOT after `mcp-servers-grid.js`. Two reasons:
    - Mirrors the providers-grid → provider-editor pairing structurally (grid file first, editor file last in the admin sub-module block)
    - The editor reuses chip-list helpers from `tools-form-helpers.js` (line 50), so `mcp-server-editor.js` MUST load AFTER that file
    ```html
    <script src="/static/js/areas/admin/mcp-server-editor.js"></script>
    ```
    The expected post-L6 ordering inside `index.html` lines 47–54 is:
    ```
    system-page.js
    providers-grid.js
    tools-form-helpers.js
    tools-grid.js
    tools-editor.js
    provider-editor.js
    provider-models.js
    mcp-servers-grid.js
    mcp-server-editor.js  ← NEW (L6)
    ```
    (Verify the post-L5 ordering at edit time; L5 inserted `mcp-servers-grid.js` somewhere in this block.)

13. **Refactor or delete `test_admin_mcp_placeholder_navigation_skips_confirm`** in `tests/browser/test_flow_admin_mcp_navigation.py`. The placeholder no longer renders post-L6. Two options:
    - DELETE the test entirely. Reasonable because the new editor's clean-state-skips-confirm is covered by `test_dirty_back_confirm_dialog` in the new editor file.
    - REFACTOR to assert the editor (not the placeholder) renders, and clean-state navigation skips confirm. Requires fetching `/api/mcp-sources/types` first.
    Recommended: DELETE. The editor file has its own equivalent coverage.

14. **Create `tests/browser/test_flow_admin_mcp_editor.py`** with the 8 enumerated tests. Critical test — `test_edit_stdio_source_preserves_unchanged_secrets`:
    ```python
    def test_edit_stdio_source_preserves_unchanged_secrets(app_clean, page):
        # Seed a source with a sensitive env var via the API
        import requests
        base_url = app_clean.split("#")[0].rstrip("/")
        resp = requests.post(f"{base_url}/api/mcp-sources", json={
            "name": "GH",
            "type": "stdio",
            "config": {"command": "github-mcp", "env": {}},
            "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
        })
        assert resp.status_code in (200, 201)
        sid = resp.json()["id"]

        # Open the editor
        page.goto(f"{app_clean}#admin/mcp-sources/{sid}")
        page.wait_for_selector('[data-testid="save-mcp-source-btn"]', timeout=8000)

        # Verify the sensitive env var pre-fills with the masked tail
        kv_value = page.locator('.kv-value-input[data-field="kv-value"]').first
        assert kv_value.input_value() == "***...alue"

        # Change ONLY the name field
        page.locator('[data-field="name"]').fill("GH-renamed")

        # Save
        page.locator('[data-testid="save-mcp-source-btn"]').click()
        # Wait for save flash
        page.wait_for_selector('.app-flash:has-text("MCP Server saved")', timeout=8000)

        # Re-fetch via API to verify the masked tail still matches the original
        check = requests.get(f"{base_url}/api/mcp-sources/{sid}")
        assert check.json()["secrets"]["GITHUB_TOKEN"] == "***...alue"
        assert check.json()["name"] == "GH-renamed"
    ```

15. **Test fixture note**: the `app_clean` fixture provides an empty DB. Tests that need pre-seeded sources POST through the API at the test's start (mirrors `test_flow_provider_editor.py` patterns). Implementer: cross-check the conftest's seeders for any helpers.

16. **Run the test suite**:
    ```
    make lint
    pytest tests/browser/test_flow_admin_mcp_editor.py tests/browser/test_flow_admin_mcp_navigation.py -v --timeout=120
    pytest tests/browser/ -k "admin or mcp" -v --timeout=120
    make test-browser
    ```

17. **Update the flight log** at `flight-log.md` with `### 06-editor-sub-module` entry: status `landed`, started/completed timestamps, "Changes Made" listing the new editor file + admin.js extensions + index.html registration + test file edits, "Notes" entry confirming the per-sensitive-field UI shape decision (option c, unified kv table) is locked.

18. **Set leg status to `landed`** in this leg's frontmatter.

19. **Do NOT commit**. Per agentic-workflow protocol commit happens at flight end.

20. **Signal `[HANDOFF:review-needed]`** when complete.

## Edge Cases

- **Empty kv table on create** — tbody renders zero rows; the "+ Add row" button is the only kv-section content. Save works; `config.env` (or `config.headers`) is `{}` and `secrets` is `{}`.
- **kv row with empty key**: skipped at `partitionKvRows` time. The operator cannot save a row with no key. No error message — silently skipped per the "tolerant input" design (operator may have started typing and abandoned a row).
- **kv row with empty value**: stored as the empty string. Plaintext rows store `""`; sensitive rows store ciphertext for `""`. Acceptable — the operator may want an empty env var (POSIX allows this).
- **kv row marked sensitive then unchecked**: if `_originalMasked` is set (this row had a stored secret pre-edit), and the operator unchecks sensitive without changing the value, the value field still shows the masked tail. On save, the row routes into plaintext (`config.env[key] = "***...alue"`) — leaking the masked tail into plaintext! **Mitigation**: when the sensitive checkbox is unchecked AND `_originalMasked` is set AND the value still equals `_originalMasked`, clear the value field on uncheck. The operator must explicitly type the new plaintext value. Document inline. (Alternative: forbid the un-mark — the operator can delete and re-add the row instead. More defensive but more surgical.) **Decision**: clear-on-uncheck-when-masked. Implementer adds this in the sensitive-checkbox change handler.
- **Same key in multiple rows**: the kv table allows duplicate keys; `partitionKvRows` will overwrite earlier values with later values (last-row-wins). Acceptable — operators get a JSON dict, not a multimap. No UI gate against duplicates; the dict semantic is the truth.
- **OAuth client_secret unchecked attempt**: the checkbox is disabled — the operator cannot uncheck. `client_secret` is always sensitive by design.
- **OAuth section with all-empty fields in create mode**: `collectOAuthSection` returns null; `config.oauth` is omitted from the payload entirely. The L3 endpoint's validator allows missing `oauth` for streamable-http (only `url` is required). On edit, if all four were previously populated and the operator clears them all, the payload sends `config.oauth = {}` — the L3 validator sees `oauth.{}` and the per-key string-type checks are vacuously true. Edge-case-but-documented.
- **OAuth clear-with-stranded-client-secret**: in edit mode, if the operator clears all OAuth plaintext fields (issuer_url, client_id, scopes, redirect_uri) AND the source previously had `secrets["oauth_client_secret"]` populated, the operator's intent is "clear OAuth entirely". `collectFormData` MUST also drop the stranded secret: explicitly include `secrets["oauth_client_secret"] = null` in the payload (or set the value to empty string `""` — L3's `update_mcp_source` PUT semantics with `secrets={...}` REPLACES the secrets dict, so any key absent from the incoming `secrets` is dropped). Implementation: when `collectOAuthSection` returns null AND `source.secrets?.oauth_client_secret` was populated AND the operator did NOT type a new client_secret value, set the row's submission value to empty string (NOT the masked sentinel) — this signals "drop this stored secret". Document inline. Without this, clearing OAuth from the UI leaves a stranded ciphertext blob.
- **Save during in-flight type-change**: the operator changes type (which hides/shows fields), then immediately clicks Save before the dirty handler fires. The form snapshot includes the type value, but the visible-field set may differ from the type's expected fields. `collectFormData` reads ALL fields by `data-field` regardless of visibility — `command` is read even when type=streamable-http. **Mitigation**: skip hidden fields. `partitionKvRows` does not need this; `collectFormData` already routes by `type` so `command` is only included when `type==='stdio'`.
- **Network failure mid-save**: error rendered in `.editor-error`; form state preserved; no orchestrator state mutation. Operator can retry. Mirrors provider editor.
- **Per-row eye-toggle loses state on type-change re-render**: the kv table is NOT re-rendered on type change (only the section title swaps); rows persist. But if a future change makes the table re-render, the eye-toggle state would be lost. Acceptable for L6.
- **Existing v9 row that got migrated to streamable-http**: L1's CASE-WHEN renamed `'sse'` → `'streamable-http'`. Such a row's `config` may have stale fields (e.g., `config.command` from when it was stdio, or no `config.url` because old SSE config schema differed). Editor's render path tolerates missing fields (renders empty inputs). Save-time validation will reject if `url` is missing — operator gets a 422; must enter the URL. Acceptable migration UX.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin/mcp-server-editor.js` (NEW, ~600–750 lines)
- `the_one/interfaces/web/static/js/areas/admin.js`:
  1. `MCP_TYPES` + `mcpTypesReady` declarations near line 137
  2. `fetchMcpSourceTypes` function definition near line 153
  3. Init block extension at line 690 (`fetchMcpSourceTypes();`)
  4. `renderMcpSourcesPanel` editor branch — replace L5 placeholder with `App.admin.renderMcpSourceEditor` delegation
- `the_one/interfaces/web/static/index.html` — one new `<script>` tag for `mcp-server-editor.js`
- `tests/browser/test_flow_admin_mcp_editor.py` (NEW, ~300 lines, 8+ tests)
- `tests/browser/test_flow_admin_mcp_navigation.py` — delete or refactor `test_admin_mcp_placeholder_navigation_skips_confirm`
- `missions/07-mcp-integration/flights/01-encrypted-persistence-and-settings/flight-log.md` — `### 06-editor-sub-module` entry appended

## State-Machine Reachability Audit

States introduced or affected:
- **Editor mounted vs unmounted**: L5 staged the `mcpSourceFormMode` closure-local; L6 wires the actual editor mount. The state-machine transition `mcpSourceFormMode: null → 'add'/'edit'` now triggers the real editor render (not a placeholder).
- **Per-row sensitive flag**: each kv table row has `{ key, value, sensitive }`. Toggling `sensitive` on a row with `_originalMasked` triggers the value-clear semantic (Edge Cases). Round-trip preservation requires the `_originalMasked` field to survive across UI events; `wireEditorEvents` reads it from `data-original-masked` attributes.
- **Dirty flag** is shared with the orchestrator's `dirty` mirror via `onDirtyChange`. The L5-staged dirty-gate `inEditor` expression at admin.js:218–225 covers the `(currentCategory === 'mcp-sources' && mcpSourceFormMode)` case; L6 wires the actual onDirtyChange bridge so the gate fires when the operator has uncommitted edits.
- **Per-key MASKED_SENTINEL**: L3's endpoint accepts `secrets[key] === '__MASKED__'` and preserves the stored value. L6 produces this payload shape on edit-save when the operator hasn't modified a sensitive row's value.

Tests that pin pre-L6 state and would contradict L6:
- `tests/browser/test_flow_admin_mcp_navigation.py::test_admin_direct_load_mcp_sources_new_renders_placeholder` — the placeholder no longer renders. Update or delete. Probably refactor to `test_admin_direct_load_mcp_sources_new_renders_editor` and assert the editor's name input is visible.
- `tests/browser/test_flow_admin_mcp_navigation.py::test_admin_mcp_placeholder_navigation_skips_confirm` — the placeholder no longer renders. Delete (covered by editor's own dirty/clean tests) OR refactor.

L5's `_mcpSourceFormMode` setter and `_editingMcpSource` setter are still used by the orchestrator's editor-branch state mutation. No L5 removals.

No FK behaviors. No application caches in L6 beyond `MCP_TYPES` (fetched once, mirrors `PROVIDER_TYPES`).

## Cache Freshness Contract

- `MCP_TYPES` cache: populated once at init via `fetchMcpSourceTypes()`. NOT invalidated mid-session — same lifecycle as `PROVIDER_TYPES`. If new transport literals ship in a future flight, the operator must reload to pick them up.
- `editingMcpSource` is set by L5's `selectMcpSource` from a tile click OR by `_tryConsumePendingMcpSource` after a hash-routing pending-id resolution. L6 receives the source object via the editor function signature; modifications are local to the form until save.

## Citation Audit

Citations re-verified post-design-review against the post-L5 `admin.js` (886 lines). The L5 implementation added ~150 lines, shifting line positions of late-file content. Citations below reflect post-L5 state; implementer must regrep before edits.

- `provider-editor.js` (451 lines) — verified as the structural template
- `provider-editor.js:91` `<span data-confirm-title>Delete Provider</span>` — `App.confirmDelete` consumes `[data-confirm-title]` for label-swap; L6 mirrors with "Delete MCP Server"
- `provider-editor.js:163` `getFormSnapshot` — verified
- `provider-editor.js:172` `wireEditorEvents` — verified
- `provider-editor.js:191-198, 444-446` MASKED_SENTINEL pattern — verified
- `provider-editor.js:413` `collectFormData` — verified
- `provider-editor.js:351-410` Delete + `App.confirmDelete` — verified
- `admin.js:174` `var PROVIDER_TYPES = [];` — **CORRECTED post-design-review** (earlier draft cited line 137, which is inside the closure-mirror init block in post-L5 admin.js)
- `admin.js:197` `function fetchProviderTypes()` — **CORRECTED post-design-review** (earlier draft cited 153-159; that range is pre-L5)
- `admin.js:252-322` `renderProvidersPanel` editor branch — verified post-L5 (UNCHANGED by L5)
- `admin.js:620-623` `renderMcpSourcesPanel` placeholder branch — **CORRECTED post-design-review** (earlier draft cited line 613, which is the function header; the placeholder body is at 620-623)
- `admin.js:875` bottom-of-init `fetchProviderTypes();` call — **CORRECTED post-design-review** (earlier draft cited 690 which was a pre-L5 estimate)
- `tools-form-helpers.js:267-305` `renderChipListEditor` — verified; reuse target for L6 args + scopes chip-lists
- `tools-form-helpers.js:307-316` `readChipListValue` — verified
- `tools-form-helpers.js:359+` `wireChipListEditor` — verified
- `tools-form-helpers.js:518-521` exports — verified
- `the_one/interfaces/web/api.py:485-508` `_mask_secret_value` — verified (per-decoded-VALUE masking with `value[-4:]` tail)
- `the_one/interfaces/web/api.py:540-615` `_validate_mcp_source_config` — verified (transport-aware shape; L6 produces conformant payloads)
- `the_one/interfaces/web/api.py:681-724` `update_mcp_source` per-key MASKED handler — verified
- `the_one/interfaces/web/api.py` `/api/mcp-sources/types` — verified post-L3
- `tests/browser/test_flow_provider_editor.py` — pattern reference for create + edit + delete browser tests with MASKED_SENTINEL coverage — verified
- `tests/browser/test_flow_admin_mcp_navigation.py:54-69` `test_admin_direct_load_mcp_sources_new_renders_placeholder` — verified post-L5; L6 refactors
- `tests/browser/test_flow_admin_mcp_navigation.py:91-110` `test_admin_mcp_placeholder_navigation_skips_confirm` — verified post-L5; L6 deletes

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] `make lint` clean
- [x] `pytest tests/browser/test_flow_admin_mcp_editor.py tests/browser/test_flow_admin_mcp_navigation.py -v --timeout=120` green
- [x] `pytest tests/browser/ -k "admin or mcp" -v --timeout=120` green
- [x] `make test-browser` green
- [x] L5's `test_admin_mcp_placeholder_navigation_skips_confirm` deleted or refactored
- [x] L5's `test_admin_direct_load_mcp_sources_new_renders_placeholder` deleted or refactored
- [x] Update flight-log.md with leg progress entry
- [x] Set leg status to `landed` (frontmatter line 3)
- [x] Do NOT check off this leg in flight.md (commit at flight end)
- [x] Do NOT commit
