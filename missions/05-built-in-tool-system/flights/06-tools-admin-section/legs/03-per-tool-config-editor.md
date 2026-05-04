# Leg: 03-per-tool-config-editor

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Land the per-tool config editor — the second admin sub-route, mounted at `#admin/tools/{name}`. Fetches `GET /api/tools/configs/{name}` (which L1 returns with `enabled`, `config`, `description`, and the marker-enriched `schema`), parses the JSON Schema, and renders one widget per top-level field via a small dispatch on `type` × `x_marker` × `ui_hint`. Save invokes `PUT /api/tools/configs/{name}` with the full body `{enabled, config}` — REPLACE-not-merge contract from L1. Adds the dirty-flag + beforeunload + back-click + section-nav-click gates that the orchestrator's L2 `// TODO L3:` comment flagged. Wires tile-click in tools-grid.js to navigate to the editor (deferred from L2 by design). Test buttons for `web_search` and `fetch_url` are NOT in this leg — that's L4.

## Context

- **F6 mission goal — operator-editable constraints**: L0 stored, L1 enforced + exposed, L2 surfaced enable/disable. L3 closes the per-tool-knob loop: an operator narrows `host_allowlist`, ratchets `timeout_seconds_max` down, picks a different `default_user_agent`, etc. Studio's agent-level overrides (L5) consume the same widget renderer.
- **F6 Decision 3** (server-side marker enrichment): L1 ships `_enrich_schema_with_markers` which injects `x_marker: "Narrow" | "NarrowPrefix" | "NarrowSuperset" | "Substitute" | (absent)` per top-level property. L3 reads `x_marker` to choose widget shape:
  - `x_marker = "Narrow"` (int with `ui_hint=dropdown`) → `<select>` of `ui_choices`; max constrained to `le` (the operator's max).
  - `x_marker = "Narrow"` (int with `ge`/`le` only) → `<input type=number min={ge} max={le}>`.
  - `x_marker = "Narrow"` (list[str]) → chip-list editor (subset semantic — operator's items are always present in the saved value when narrowed; agent's L5 view will show them locked).
  - `x_marker = "NarrowSuperset"` (list[str]) → chip-list editor (operator can ADD entries; agent must contain operator's; admin sees plain editable chip-list).
  - `x_marker = "NarrowPrefix"` (list[str]) → chip-list editor with path-prefix syntax (admin-side: same UX as plain chip-list; the prefix semantic only matters at agent override validation).
  - `x_marker = "Substitute"` (str) → `<input type=text>` (free-form; no comparison).
  - `x_marker` absent (operator-only field, e.g., `WebConfig.redirect_cap`) → still rendered as a regular widget at admin (operator sets it); L5 will hide it from the agent override surface.
  - `bool` (no marker yet declared in F2-F5) → `<input type=checkbox>`.
- **F6 Decision 7** (hash routing): `#admin/tools/{name}` deep-links the editor; refresh lands on the same editor; section-nav clicks back to `system`/`providers` gated by dirty.
- **F6 Decision 12** (two-Reviewer-pass batching): L3 commits no docs. The renderer's widget dispatch table goes to CLAUDE.md "Tool Authorship Contract" addendum at L9.
- **L1 PUT contract review**: L1's `upsert_tool_config` accepts `{enabled?, config?}`. When `config` is present in the body, REPLACES the saved config wholesale; when omitted, preserves it. L2 sends only `{enabled}` to keep the saved config. L3 sends `{enabled, config}` — the full state — for the SAVE button. The Cancel button restores the snapshot client-side and never PUTs.
- **L2 routing handoff**: L2 deliberately strips `tools/{name}` to `tools` in `hydrateState`. L3 swaps that strip for proper handling: `tools/{name}` parses out `pendingToolName`, fires `_tryConsumePendingTool` after the next fetch resolves. The orchestrator pattern mirrors the providers' `_tryConsumePendingProvider` at admin.js:411-433.
- **L2 grid handoff**: L2 left tile-click un-wired (only the toggle was interactive). L3 adds `onSelectTool` callback to `renderToolsGrid`'s callbacks; per-tile click (excluding toggle clicks via the existing `closest('.tool-enable-switch')` guard) calls `onSelectTool(name)` which the orchestrator routes to `selectTool(name)` → editor mode + `replaceSub` to `tools/{name}`.
- **L2 dirty-gate TODO**: admin.js:166-173's `inEditor` check currently reads `currentCategory === 'providers' && providerFormMode`. L3 widens it to `(... || (currentCategory === 'tools' && toolFormMode))` so section-nav clicks while editing a tool surface the unsaved-changes confirm dialog.
- **No chip-list primitive exists yet**: F4/F5 didn't ship one (the `extra_allowed_hosts` field on `WebConfig` was wired but never had a UI — agents passed it via JSON, not a form). L3 ships the FIRST chip-list editor as inline JS in `tools-editor.js`. If L5's Studio override panel needs the same widget, it imports the renderer or calls a small extracted helper (deferred until L5 design).

## Inputs

- `the_one/interfaces/web/static/js/areas/admin.js` (post-L2): `categories` has 3 entries; `validIds` has `'tools'`; `hydrateState` strips `tools/{name}` to `tools`; `renderToolsPanel()` mounts only the grid; `// TODO L3:` comment at line ~169 area on the `inEditor` gate; `toolConfigs` cache + `toolsInFlight` set already exist.
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` (post-L2): exports `App.admin.renderToolsGrid(container, toolConfigs, callbacks)`; callbacks has `onToggle` and `inFlight`; per-tile click handler exists but only forwards to the inner checkbox.
- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` (F4/F6 leg-03/04 of the providers flow): the canonical reference for editor scaffolding — header / form-actions / editor-section / dirty tracking via `getFormSnapshot` + `checkDirty` / save fetch / `MASKED_SENTINEL` pattern (irrelevant to L3 — no API keys). Lines 1-200 cover the main scaffold. L3 mirrors the structure but the form is schema-driven, not hand-written.
- `the_one/interfaces/web/api.py` (post-L1):
  - `GET /api/tools/configs/{name}` returns `{name, description, enabled, config, schema}`.
  - `PUT /api/tools/configs/{name}` accepts `{enabled?, config?}`; REPLACE on `config`.
- `the_one/interfaces/web/static/index.html:48` (post-L2): `tools-grid.js` script tag. L3 adds `tools-editor.js` immediately after.
- `Makefile:93` (post-L2): the `verify-serving` loop. L3 appends `admin/tools-editor.js` to the iteration list.
- `the_one/tools/_web_config.py:151-260` — reference for what kind of fields the editor must handle (int + dropdown, int + ge/le, list[str] Narrow / NarrowSuperset, str Substitute, int operator-only).
- `the_one/tools/execution.py`, `the_one/tools/filesystem.py`, `the_one/tools/python_exec.py` — three more Configs the renderer must handle. Architect verified all 4 Configs are flat (no nested BaseModel fields).
- `tests/test_db_api.py:16-35` — canonical client fixture pattern; L3's asset test reuses it.

## Outputs

- `the_one/interfaces/web/static/js/areas/admin.js`:
  - **State additions**: `var toolFormMode = null;` (`'edit' | null`), `var editingTool = null;` (full detail object — `{name, description, enabled, config, schema}`), `var pendingToolName = null;`, `var pendingToolFormMode = null;`. Place after the existing tool state (`toolConfigs`, `toolsInFlight`).
  - **Dirty-flag widening**: the existing `dirty` closure-local at line 99 is shared by the editor flow (closure-mirroring of the editor sub-module's local). Reuse it — the `// TODO L3:` gate at line ~169 widens to `var inEditor = (currentCategory === 'providers' && providerFormMode) || (currentCategory === 'tools' && toolFormMode);`.
  - **`_setCategory` widening — TWO functions, both must be widened**: `doSetCategory` at admin.js:166-176 (the internal click handler used for in-app section-nav clicks) AND `self._setCategory` at admin.js:488-498 (the property-bag accessor used by `hydrateState` for URL-driven category switches). Per-Reviewer (high-severity): widening only one would let URL-nav from `#admin/tools/web_search` directly to `#admin/system` skip the tool-state wipe. Both functions must clear `toolFormMode`, `editingTool`, `pendingToolName`, `pendingToolFormMode`.
  - **`serializeState`**: the existing `tools` branch returns `'tools'`. Widen: when `toolFormMode === 'edit' && editingTool`, return `'tools/' + encodeURIComponent(editingTool.name)`. When `pendingToolName` (hydrate-vs-fetch race), return `'tools/' + encodeURIComponent(pendingToolName)`.
  - **`hydrateState`**: replace the L2 strip-to-`tools` branch with parse-out-name pattern parallel to the providers' parse at lines 41-54. Specifically:
    - `origSub === 'tools'` → bare grid (clear pending state).
    - `origSub.indexOf('tools/') === 0` → strip prefix, `decodeURIComponent` the rest, set `pendingToolFormMode = 'edit'`, `pendingToolName = name`. Defensive: if extra path segments, take only the first.
    - `validIds` array unchanged from L2 (already includes `tools`).
    - After `_setCategory('tools')`, set the pending pair, fire `_tryConsumePendingTool`.
  - **`_setCategory`**: widen the wipe block (lines 152-162) to also clear `toolFormMode`, `editingTool`, `pendingToolName`, `pendingToolFormMode`.
  - **New `selectTool(name)` function** — **always fetches** `GET /api/tools/configs/{name}` (the cache lacks `schema`; cache-lookup-first would always fall through to fetch anyway). Per-Reviewer (high-severity): drop the cache-lookup-first language entirely. On fetch success: set `editingTool = detail`, `toolFormMode = 'edit'`, clear pending, `App.router.replaceSub(self.serializeState())`, re-render. On 404: `App.showFlash` surfaces the error; orchestrator stays on grid (no state mutation). On other errors: same flash path.
  - **New `_tryConsumePendingTool` function** (mirrors `_tryConsumePendingProvider` at lines 411-433): if `pendingToolFormMode === 'edit' && pendingToolName`, call `selectTool(pendingToolName)`. Bonus: tile-click navigation also calls `selectTool` directly (no pending-state dance).
  - **`renderToolsPanel`** widens with editor branch (mirrors `renderProvidersPanel` at lines 197-280):
    - If `toolFormMode === 'edit' && editingTool`: reset `dirty = false`, mount editor via `App.admin.renderToolsEditor(contentEl, editingTool, {onBack, onCancel, onSaveSuccess, onDirtyChange})`. Mirrors the provider-editor mount at lines 222-267.
    - Else: existing grid branch (unchanged).
  - **Callbacks for editor** (passed to `renderToolsEditor`):
    - `onBack`: dirty-gate via `App.confirmDialog`; on confirm, set `toolFormMode = null`, `editingTool = null`, `dirty = false`, `replaceSub('tools')`, `renderToolsPanel()`.
    - `onCancel`: same as onBack but bypasses the dirty gate (cancel-when-dirty is intentional discard). The editor sub-module's Cancel button restores the snapshot internally.
    - `onSaveSuccess(updated)`: editor's PUT response. Update `toolConfigs` cache (`toolConfigs[i] = {name, description, enabled, config}`), `editingTool = updated`, `dirty = false`. **Do NOT navigate away** — operator stays on the editor (matches provider-editor edit→edit pattern at lines 240-256).
    - `onDirtyChange(d)`: bridge from sub-module's local dirty flag to the orchestrator mirror.
  - **`fetchToolConfigs`** does NOT need to refetch on editor mount — the grid cache and the editor detail are independent fetches (the editor needs `schema` which the list endpoint deliberately omits per L1's design).
  - **`self._refresh`** widens: when `currentCategory === 'tools' && toolFormMode === 'edit' && editingTool`, refetch via `selectTool(editingTool.name)`. When `currentCategory === 'tools' && !toolFormMode`, the existing `fetchToolConfigs()` branch already covers it.
  - **Property accessors** for browser tests + serializeState dispatch: `_toolFormMode`, `_editingTool`, `_pendingToolName`, `_pendingToolFormMode`. **Lifecycle pin** (per-Reviewer high-severity): all four `Object.defineProperty` blocks land in the existing accessor cluster at admin.js:464-487 area (where `_currentCategory`, `_providerFormMode`, etc. live), BEFORE `serializeState` is first called from the router. `_setCategory` already exists (preserve).

- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js`:
  - **Add `onSelectTool` callback** to the destructure block: `var onSelectTool = callbacks.onSelectTool || function () {};`.
  - **Widen the existing tile-click handler**: the L2 handler currently forwards to the inner checkbox unless the click was on the toggle. L3 changes the bail behaviour: when clicking outside the toggle, call `onSelectTool(name)` (navigate to editor) — NOT `input.click()`. The toggle keeps its own native `change` event; the rest of the tile is now a click-to-edit surface.
  - Tile is still `<div role="listitem">` — semantic role preserved (clickable via the JS handler; the editor opens on Enter? — keyboard: Enter on the toggle still flips the toggle, NOT navigates. To make the tile keyboard-navigable: add `tabindex="0"` to the tile and a `keydown` listener for Enter/Space that calls `onSelectTool` UNLESS the active element is the input. **Operator UX gap**: this matches the providers' tile keyboard story — providers' tile is a `<button>` (free keyboard support); tools' tile is a `<div>` because the inner checkbox handles its own focus. Add `tabindex="0"` + keydown to the tile so keyboard users can also select-to-edit. Acceptance criterion below pins this.)
  - **Cursor + hover**: with click-to-edit live, the inherited `cursor: pointer` from `.entity-tile` is fully accurate. No CSS changes required — the L2 `.tool-tile` selector already inherits the hover-accent border flip.
  - File ends ~125 lines after L3 changes (was 122 lines after L2; +3 for the keyboard handler and the callback).

- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` (new file, ~400-450 LoC). Per-Reviewer suggestion: provider-editor is 451 lines for hand-written fields; tools-editor adds chip-list (~50 LoC) + per-field-type readback (~20) + 422 inline error rendering (~30) + chip event delegation (~20). 350 was under-estimated.
  - IIFE wrapping; `window.App.admin.renderToolsEditor(container, toolDetail, callbacks)` global.
  - Editor scaffold mirrors `provider-editor.js`:
    ```html
    <div class="editor-header">
      <div class="editor-header-text">
        <h1 class="editor-title">{name}</h1>
        <p class="editor-subtitle">{description} · {category}</p>
      </div>
      <div class="form-actions">
        <button class="back-btn">{App.icon('arrow-left')} Back</button>
        <button class="cancel-btn" disabled>Cancel</button>
        <button class="save-btn" disabled>Save</button>
        <span class="editor-error"></span>
      </div>
    </div>
    <div class="editor-section">
      <div class="section-title">Configuration</div>
      <div class="field-row tools-editor-enabled-row">
        <label for="tef-enabled">Enabled for all agents</label>
        <input id="tef-enabled" type="checkbox" data-field="enabled" />
      </div>
      {one .field-row per schema property in deterministic order}
      {if no fields beyond `enabled`: <p class="empty-state">No additional configuration.</p>}
    </div>
    <!-- L4 will append a sibling .editor-section below this one for test
         buttons (web_search / fetch_url only). The current scaffold leaves
         the gap implicit — L4 adds the section unconditionally and tools-
         editor.js gates rendering on the tool name. -->
    ```
    Section title is "Configuration" (per-Reviewer Q4) — concise and descriptive without the "Operator settings" framing oddity.
  - **Field rendering dispatch** (in a `renderField(name, prop)` helper). **Iteration order is `Object.keys(schema.properties)`** — Pydantic's declaration order from the Config class (per-Reviewer medium pin), NOT alphabetic; matches the operator's mental-model order in the Config docstrings.
    1. **`bool`** → `<input type=checkbox data-field={name} {checked}>`.
    2. **`integer` + `ui_hint=dropdown` + non-empty `ui_choices`** → `<select data-field={name}>` with one `<option value={c.value} {selected}>{c.label}</option>` per `ui_choices` entry. If the saved value is not in `ui_choices`, append it as a synthetic `<option>` so the form round-trips a custom value. Guard with `Array.isArray(ui_choices) && ui_choices.length > 0` (per-Reviewer medium); empty `ui_choices` falls through to the next branch.
    3. **`integer`** (no `ui_hint=dropdown` OR empty `ui_choices`) → `<input type=number data-field={name} value={v}>`. Add `min={ge}` and `max={le}` IFF the schema declares them (per-Reviewer medium: a future field without `ge`/`le` renders without min/max attrs; client-side validation deferred to server).
    4. **`array` (list[str])** → chip-list editor (see below). Dispatch ignores `ui_hint=dropdown` for `type=array` (per-Reviewer medium): `command_denylist` carries both `NarrowSuperset` and `ui_hint=dropdown` but the operator UX wants chip-list (NarrowSuperset = operator can ADD denylist entries; dropdown was a stale F4 metadata leak meant for a future "reset to baseline" affordance, not the canonical widget).
    5. **`string`** → `<input type=text data-field={name} value={v}>`.
    6. Fallback (unknown type) → `<input type=text data-field={name} value={JSON.stringify(v)}>` with a `field-unknown-type` warning class AND `console.warn('renderField: unknown type "%s" for field "%s"; rendering as text input', type, name);` so a future Config carrying a new type surfaces visibly during dev.
  - **Chip-list editor** (inline component, ~50 LoC). DOM (chips are direct children of `.chip-list-editor` — per-Reviewer low: dropped the `.chip-list-chips` wrapper that was a `display: contents` workaround):
    ```html
    <div class="chip-list-editor" data-field="{name}" data-marker="{x_marker}">
      {for each item: <span class="chip">{value}<button class="chip-remove" aria-label="Remove {value}">×</button></span>}
      <input type="text" class="chip-list-input" placeholder="Add entry…" />
    </div>
    ```
    - Enter (or comma) on the input adds the trimmed non-empty value as a new chip; multiple comma-separated entries pasted at once split + add each.
    - Backspace on empty input removes the last chip; noop when no chips exist.
    - Click on `.chip-remove` removes that chip.
    - Duplicates silently deduped on add.
    - `getFieldValue('chip-list', name)` returns the array of chip text contents in DOM order.
    - Items.type defensive: if `prop.items?.type !== 'string'`, still render as chip-list AND emit `console.warn('chip-list editor: items.type is "%s" (expected "string")...')` — the L1 422 catches the type mismatch on save.
    - **`x_marker = "NarrowSuperset"` admin UX note**: the admin sees a plain editable chip list (no locked entries — operators can add/remove freely; the NarrowSuperset semantic only constrains AGENT overrides, where operator's items become locked). L5 implements the locked-chip view for the agent-side renderer; L3's admin-side stays simple.
  - **Snapshot + dirty tracking** (mirrors provider-editor.js:163-200):
    ```javascript
    function getFormSnapshot(container) {
      var snap = { enabled: container.querySelector('[data-field="enabled"]').checked, config: {} };
      var inputs = container.querySelectorAll('[data-field]:not([data-field="enabled"])');
      for (var i = 0; i < inputs.length; i++) {
        snap.config[inputs[i].dataset.field] = readFieldValue(inputs[i]);
      }
      return JSON.stringify(snap);
    }
    function checkDirty() {
      var newDirty = getFormSnapshot(container) !== snapshot;
      if (newDirty !== dirty) {
        dirty = newDirty;
        container.querySelector('.cancel-btn').disabled = !dirty;
        container.querySelector('.save-btn').disabled = !dirty;
        if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);
      }
    }
    ```
  - **`readFieldValue(inputEl)`**: dispatches on the field's widget shape — checkbox → `.checked`; number → `parseInt(.value, 10)` or `parseFloat`; text/select → `.value`; chip-list-editor → array of chip texts. Defensive: returns the existing prop default when input is empty AND the type is `integer`.
  - **Wire events**: `change` on every form control fires `checkDirty()`. `click` on chip-list components (via event delegation on the chip-list-editor) fires `checkDirty()`. `input` on chip-list-input also fires (after add/remove side-effects) — handled inside the chip-list event handlers.
  - **Save handler**: on `.save-btn` click, build body from `getFormSnapshot` (parse JSON back to object), `PUT` to `/api/tools/configs/{name}`. On 200: refresh local snapshot, `dirty = false`, disable both buttons, call `callbacks.onSaveSuccess(updated)`. On 4xx with `detail` array (Pydantic ValidationError): inline-render errors next to the field labels (`<span class="field-error">{loc.join('.')}: {msg}</span>`). On 5xx or network error: `App.showFlash(container, msg, true)` and keep the form dirty.
  - **Cancel handler**: per-Reviewer (high-severity), pinned to **option A — re-mount with the original `toolDetail`**. The closure captures `var originalToolDetail = toolDetail;` at mount time; Cancel calls `renderToolsEditor(container, originalToolDetail, callbacks)`. Cleaner than rebuilding chip-list DOM from a snapshot string. The new closure starts at `dirty = false`; `onDirtyChange(false)` fires AFTER the prior closure already fired its final `onDirtyChange` — orchestrator mirror is correct.
  - **Back handler**: invoke `callbacks.onBack()` — orchestrator decides whether to gate.
  - **Module exports**: `window.App.admin.renderToolsEditor = renderToolsEditor;`. The chip-list editor stays inline (no public export from L3; L5 may extract).

- `the_one/interfaces/web/static/css/admin.css` (append). All token names verified against tokens.css:
  - `.area-admin .tools-editor-enabled-row { /* spacing for the enabled toggle row */ }`
  - `.area-admin .chip-list-editor { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; padding: 6px; border: 1px solid var(--border-strong); border-radius: 4px; min-height: 40px; }` (chips are direct children — no wrapper needed).
  - `.area-admin .chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; background: var(--surface-elevated); border-radius: 12px; font-size: var(--font-size-small); }`
  - `.area-admin .chip-remove { background: none; border: 0; color: var(--fg-faint); cursor: pointer; padding: 0 2px; font-size: 1em; line-height: 1; }`
  - `.area-admin .chip-remove:hover { color: var(--accent); }`
  - `.area-admin .chip-list-input { flex: 1; min-width: 100px; border: 0; outline: none; padding: 2px; background: transparent; color: var(--fg); }`
  - `.area-admin .field-error { display: block; color: var(--status-danger); font-size: var(--font-size-tiny); margin-top: 4px; }` (per-Reviewer medium: `--status-danger` is canonical; `--text-error` does not exist).
  - `.area-admin .field-description { font-size: var(--font-size-tiny); color: var(--fg-secondary); margin: 4px 0 0 100px; }` (per-Reviewer low: matches the `.field-row label { width: 100px }` gutter so descriptions visually associate with the field).
  - `.area-admin .field-unknown-type { border-color: var(--status-danger); }` (developer-visible cue for an un-dispatched type).

- `the_one/interfaces/web/static/index.html`:
  - Insert `<script src="/static/js/areas/admin/tools-editor.js"></script>` immediately after the `tools-grid.js` line (line 49 area).

- `Makefile:93`:
  - Append `admin/tools-editor.js` to the verify-serving asset loop (after `admin/tools-grid.js`).

- `tests/test_tools_admin_editor_assets.py` (new, 2 tests, mirrors L2's asset-test fixture):
  - `test_tools_editor_js_served` — assert `GET /static/js/areas/admin/tools-editor.js` returns 200 and body contains `App.admin.renderToolsEditor`.
  - `test_index_html_includes_tools_editor_script` — assert the SPA shell contains the new script tag.

- `tests/test_tools_editor_form_dispatch.py` (new, lightweight unit test of the widget dispatch logic — Python implementation of the same algorithm to lock the contract; the JS implementation is verified in L7 Playwright):
  - **Skip this file**. The form-dispatch table is JS-only; an L7 Playwright test asserts the rendered widget shape per field type. Adding a Python mirror is duplication. (Architect note: L7 owns full JS coverage; per-leg unit tests for JS dispatch invite drift.)

## Acceptance Criteria

- [x] `the_one/interfaces/web/static/js/areas/admin.js` — state additions: `toolFormMode`, `editingTool`, `pendingToolName`, `pendingToolFormMode`. Existing `dirty` closure-local is reused.
- [x] **BOTH** `doSetCategory` (admin.js:166-176, internal click handler) AND `self._setCategory` (admin.js:488-498, public hydrate-driven accessor) clear all four new tool-state vars in addition to the existing provider clears. Per-Reviewer (high): widening only `doSetCategory` would leak stale tool state on URL-nav from `#admin/tools/X` directly to `#admin/system`.
- [x] The four new property accessors (`_toolFormMode`, `_editingTool`, `_pendingToolName`, `_pendingToolFormMode`) land in the existing accessor cluster at admin.js:464-487 area, BEFORE `serializeState` is first called from the router.
- [x] `serializeState` returns `'tools'` for grid, `'tools/' + encodeURIComponent(editingTool.name)` for editor, `'tools/' + encodeURIComponent(pendingToolName)` for hydrate-vs-fetch race.
- [x] `hydrateState` parses `tools/{name}` into `pendingToolName + pendingToolFormMode`; bare `tools` clears them. `tools/{name}` with extra path segments takes only the first.
- [x] `// TODO L3:` comment at admin.js:166-173 area replaced with the widened `inEditor` gate `(currentCategory === 'providers' && providerFormMode) || (currentCategory === 'tools' && toolFormMode)`.
- [x] `selectTool(name)` ALWAYS fetches `GET /api/tools/configs/{name}` (no cache-lookup short-circuit — the cache lacks `schema`); sets `editingTool` + `toolFormMode='edit'`, clears pending, calls `replaceSub`, re-renders. NOT shared with `handleToolToggle` (the toggle uses the cached config without fetching the schema). On 404 / network error, surfaces `App.showFlash` and stays on grid.
- [x] `_tryConsumePendingTool` parallels `_tryConsumePendingProvider`; fires after fetch resolves OR on direct tile click.
- [x] `renderToolsPanel` editor branch invokes `App.admin.renderToolsEditor(contentEl, editingTool, callbacks)` with `onBack`, `onCancel`, `onSaveSuccess`, `onDirtyChange`.
- [x] `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` — adds `onSelectTool` to destructure; tile-click handler navigates via `onSelectTool(name)` (not `input.click()`); tile gets `tabindex="0"`; keydown listener on Enter/Space calls `onSelectTool(name)` UNLESS the active element is the toggle input.
- [x] `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` is a new IIFE-wrapped module exporting `App.admin.renderToolsEditor(container, toolDetail, callbacks)`.
- [x] Editor scaffold matches the spec'd shape: `.editor-header` with `.editor-title`/`.editor-subtitle`/`.form-actions` (Back, Cancel, Save, error span); `.editor-section` with `.section-title` "Configuration" (per design Reviewer Q4 — supersedes the earlier "Operator settings" wording in this criterion); the enabled toggle row + one row per schema property.
- [x] **Field iteration order** is `Object.keys(schema.properties)` — Pydantic declaration order — NOT alphabetic.
- [x] **Field-widget dispatch** correctly handles all 5 cases: bool checkbox; int with `ui_hint=dropdown` AND non-empty `ui_choices` → `<select>` (else fall through); int → `<input type=number>` with `min`/`max` IFF `ge`/`le` declared; **`array` (list[str])** → chip-list editor (ignoring any `ui_hint` for `type=array` — `command_denylist` correctly renders as chip-list, not its stale F4 dropdown metadata); string → text input. Unknown type → text input with `field-unknown-type` class + console.warn.
- [x] **Chip-list editor**: Enter or comma adds (multiple comma-separated entries split + add each); backspace on empty removes last (noop if no chips); per-chip × button removes; duplicates silently deduped; `getFieldValue` returns array in DOM order. Dirty fires on chip add/remove.
- [x] **Dirty tracking**: snapshot taken at mount; `change` events on form controls AND chip-list mutations fire `checkDirty()`; Cancel/Save buttons enable when dirty, disable when clean. `onDirtyChange(d)` bridge to orchestrator mirror fires only on transitions.
- [x] **Save handler**: PUTs `{enabled, config}` to `/api/tools/configs/{name}`. On 200: re-snapshot, disable Cancel/Save, fire `onSaveSuccess(updated)`. On 422 with array `detail`: inline `field-error` rendering adjacent to the matching `[data-field-name]` row; if `loc` doesn't match a row, surface in `.editor-error`. On other errors: `App.showFlash` and keep dirty.
- [x] **Cancel handler**: re-mounts the editor via `renderToolsEditor(container, originalToolDetail, callbacks)` (option A pinned per-Reviewer high); `originalToolDetail` is captured at mount time. No PUT. New closure starts at `dirty=false`; `onDirtyChange(false)` bridges to orchestrator.
- [x] **Back handler**: delegates to `callbacks.onBack()`; orchestrator gates on dirty via `App.confirmDialog`.
- [x] **beforeunload**: works through the existing orchestrator listener at admin.js:138-144 (which gates on the closure `dirty` flag) — no new listener needed in tools-editor.js. Verify by mounting the editor with unsaved changes and attempting page reload. (Closure `dirty` mirror is bridged via `onDirtyChange`; pre-existing listener now sees tool-editor mutations through the same `dirty` flag.)
- [x] CSS additions: `.chip-list-editor`, `.chip`, `.chip-remove`, `.chip-list-input`, `.field-error` (uses `--status-danger`), `.field-description`, `.field-unknown-type`, `.tools-editor-enabled-row`. All token references resolve to existing tokens.css entries. (Note: `.chip` / `.chip-remove` selectors are scoped under `.area-admin .chip-list-editor` to avoid clobbering the global `.chip` rule in components.css:286-291.)
- [x] **`populateToolGrid` callbacks widened** (per-Reviewer low) — passes `onSelectTool: selectTool` in addition to `onToggle` + `inFlight` so the L2 stale-then re-render preserves the click-to-edit handler.
- [x] **Tile keyboard model** (per-Reviewer medium): Enter on tile = open editor; Space on tile = open editor; Enter on toggle = noop (matches native checkbox); Space on toggle = flip toggle (native). The `keydown` bail on `document.activeElement.tagName === 'INPUT'` ensures Space-on-toggle does NOT also navigate.
- [x] Back button uses `App.icon('arrow-left') + ' Back'` for visual parity with provider-editor.
- [x] `Makefile:93` includes `admin/tools-editor.js` in the verify-serving loop.
- [x] `the_one/interfaces/web/static/index.html` includes `<script src="/static/js/areas/admin/tools-editor.js">` immediately after `tools-grid.js`.
- [x] `tests/test_tools_admin_editor_assets.py` ships with 2 tests; both pass.
- [x] `make test-unit` is green (modulo CSS-token deselect). (`pytest -m 'not browser and not live and not pixel' --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined`: 1039 passed, 1 skipped, 239 deselected.)
- [x] `make rebuild` succeeds; `make verify-serving` shows tools-editor.js as 200.
- [x] No L0/L1/L2 file is touched besides the documented widening points.
- [x] No L4/L5 surface is created (no test buttons; no Studio Tools tab edits).

## Verification Steps

```bash
# 1. Module structure
docker exec the-one cat the_one/interfaces/web/static/js/areas/admin/tools-editor.js | grep -c 'App.admin.renderToolsEditor'  # should be 1+

# 2. Schema-driven dispatch — load the WebConfig schema in-process and confirm
#    the rendered JS handles all the marker cases (verified visually + by L7 Playwright)
docker exec the-one python -c "
from the_one.tools._web_config import WebConfig
from the_one.interfaces.web.api import _enrich_schema_with_markers
import json
schema = _enrich_schema_with_markers(WebConfig.model_json_schema(), WebConfig)
props = schema['properties']
markers = {n: p.get('x_marker', '(none)') for n, p in props.items()}
types = {n: p.get('type', '?') for n, p in props.items()}
print('WebConfig field markers:', json.dumps(markers, indent=2))
print('WebConfig field types:', json.dumps(types, indent=2))
"

# 3. Targeted asset test
docker exec the-one pytest tests/test_tools_admin_editor_assets.py -x -q

# 4. Regression — L0/L1/L2 unchanged
docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py tests/test_factory.py tests/test_factory_disable_enforcement.py tests/test_api_tool_configs.py tests/test_enrich_schema_with_markers.py tests/test_tools_admin_grid_assets.py -x -q

# 5. Full unit suite
docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# 6. Static asset wiring
make rebuild
make verify-serving  # should print "✓ admin/tools-editor.js served (200)"

# 7. Manual smoke (browser):
#    a. http://localhost:8484/#admin/tools — grid renders; click a tile → editor opens at #admin/tools/{name}.
#    b. Modify a field → Save/Cancel enable; Cancel restores snapshot; Save fires PUT.
#    c. Reload while dirty → browser confirms leave.
#    d. Section-nav click while dirty → confirm dialog.
#    e. Direct-load #admin/tools/web_search → editor opens to web_search.

# 8. Lint
docker exec the-one ruff check tests/test_tools_admin_editor_assets.py
```

## Implementation Guidance

1. **Orchestrator state widening** — `the_one/interfaces/web/static/js/areas/admin.js`:

   ```javascript
   // After the existing tool state (line ~95 area)
   var toolFormMode = null;       // 'edit' | null
   var editingTool = null;        // { name, description, enabled, config, schema } | null
   var pendingToolName = null;    // hydrate-vs-fetch race
   var pendingToolFormMode = null; // 'edit' | null
   ```

2. **Dirty-gate widening** — replace the `inEditor` line at admin.js:167:

   ```javascript
   var inEditor = (currentCategory === 'providers' && providerFormMode)
                || (currentCategory === 'tools' && toolFormMode);
   ```

   Remove the `// TODO L3:` comment (job done).

3. **`serializeState` widening** — extend the `tools` branch:

   ```javascript
   if (this._currentCategory === 'tools') {
     if (this._toolFormMode === 'edit' && this._editingTool) {
       return 'tools/' + encodeURIComponent(this._editingTool.name);
     }
     if (this._pendingToolName) {
       return 'tools/' + encodeURIComponent(this._pendingToolName);
     }
     return 'tools';
   }
   ```

4. **`hydrateState` widening** — replace the L2 strip-to-`tools` shortcut with parse-out-name:

   ```javascript
   var pendingToolName_local = null;
   var pendingToolFormMode_local = null;
   if (origSub === 'tools') {
     sub = 'tools';
   } else if (origSub && origSub.indexOf('tools/') === 0) {
     sub = 'tools';
     pendingToolFormMode_local = 'edit';
     var rest = origSub.slice('tools/'.length);
     if (rest.charAt(rest.length - 1) === '/') rest = rest.slice(0, -1);
     var slashIdx = rest.indexOf('/');
     if (slashIdx !== -1) rest = rest.slice(0, slashIdx);
     pendingToolName_local = rest ? decodeURIComponent(rest) : null;
   }
   // ... existing _setCategory / pending-state assignment for providers ...
   this._pendingToolName = pendingToolName_local;
   this._pendingToolFormMode = pendingToolFormMode_local;
   if (this._tryConsumePendingTool) this._tryConsumePendingTool();
   ```

5. **`_setCategory` widening — TWO functions, both must be widened**:

   First, `doSetCategory` at admin.js:166-176 (internal click-handler):

   ```javascript
   function doSetCategory(catId) {
     currentCategory = catId;
     providerFormMode = null;
     editingProvider = null;
     pendingProviderId = null;
     pendingFormMode = null;
     toolFormMode = null;
     editingTool = null;
     pendingToolName = null;
     pendingToolFormMode = null;
     dirty = false;
     // ... rest unchanged
   }
   ```

   Second, `self._setCategory` at admin.js:488-498 (the public hydrate-driven accessor — used by `hydrateState` for URL-driven category switches):

   ```javascript
   self._setCategory = function (sub) {
     if (currentCategory !== sub) {
       currentCategory = sub;
       providerFormMode = null;
       editingProvider = null;
       pendingProviderId = null;
       pendingFormMode = null;
       toolFormMode = null;
       editingTool = null;
       pendingToolName = null;
       pendingToolFormMode = null;
       App.layout.updateActiveSection(categoryListEl, currentCategory);
       renderContent();
     }
   };
   ```

   Without widening the second one, URL nav from `#admin/tools/web_search` directly to `#admin/system` would skip the tool-state wipe and leave stale `editingTool` dangling.

6. **`renderToolsPanel` editor branch** — widen the L2 grid-only function:

   ```javascript
   function renderToolsPanel() {
     if (toolFormMode === 'edit' && editingTool) {
       dirty = false;  // reset before sub-module mount (mirrors provider pattern)
       App.admin.renderToolsEditor(contentEl, editingTool, {
         onBack: function () {
           if (dirty) { App.confirmDialog({ onConfirm: function () { exitEditor('back'); } }); return; }
           exitEditor('back');
         },
         onCancel: function () {
           // Cancel-when-dirty discards intentionally — no dialog gate.
           // The editor sub-module restores its own snapshot.
           exitEditor('cancel');
         },
         onSaveSuccess: function (updated) {
           // Update grid cache so an immediate Back lands on a current grid.
           for (var i = 0; i < toolConfigs.length; i++) {
             if (toolConfigs[i].name === updated.name) {
               toolConfigs[i] = {
                 name: updated.name,
                 description: updated.description,
                 enabled: updated.enabled,
                 config: updated.config
               };
               break;
             }
           }
           editingTool = updated;  // includes schema (from prior fetch)
           // ^^ careful: server's PUT response does NOT include schema; merge.
           dirty = false;
         },
         onDirtyChange: function (d) { dirty = d; }
       });
       return;
     }
     // Grid branch (L2)
     App.admin.renderToolsGrid(contentEl, toolConfigs, {
       onToggle: handleToolToggle,
       inFlight: toolsInFlight,
       onSelectTool: selectTool
     });
     fetchToolConfigs();
   }

   // L3 also widens `populateToolGrid` (admin.js:390 area) — the L2 stale-then
   // re-render and the failed-fetch fallback both call renderToolsGrid; per-Reviewer
   // (low), they MUST also pass `onSelectTool: selectTool`. Otherwise after a
   // tool toggle PUT, the re-render strips the click-to-edit handler.
   function populateToolGrid() {
     if (currentCategory !== 'tools') return;
     App.admin.renderToolsGrid(contentEl, toolConfigs, {
       onToggle: handleToolToggle,
       inFlight: toolsInFlight,
       onSelectTool: selectTool
     });
   }

   function exitEditor(reason) {
     toolFormMode = null;
     editingTool = null;
     dirty = false;
     if (window.App && window.App.router) App.router.replaceSub('tools');
     renderToolsPanel();
   }
   ```

   **Important**: the PUT response does NOT include `schema` (L1's `upsert_tool_config` returns `{name, description, enabled, config}`). The orchestrator must MERGE the response into `editingTool` preserving the prior `schema`:

   ```javascript
   onSaveSuccess: function (updated) {
     // Merge — preserve schema from the original GET fetch
     editingTool = {
       name: updated.name,
       description: updated.description,
       enabled: updated.enabled,
       config: updated.config,
       schema: editingTool.schema  // schema unchanged across saves
     };
     // ... cache update as above
     dirty = false;
   }
   ```

7. **`selectTool`** — fetches the per-tool detail (with schema):

   ```javascript
   function selectTool(name) {
     return fetch('/api/tools/configs/' + encodeURIComponent(name))
       .then(function (r) {
         if (!r.ok) throw new Error('Fetch failed: ' + r.status);
         return r.json();
       })
       .then(function (detail) {
         editingTool = detail;
         toolFormMode = 'edit';
         pendingToolName = null;
         pendingToolFormMode = null;
         if (window.App && window.App.router) {
           App.router.replaceSub(self.serializeState());
         }
         renderToolsPanel();
       })
       .catch(function () {
         App.showFlash(contentEl, 'Failed to load ' + name + '.', true);
       });
   }
   ```

8. **`_tryConsumePendingTool`**:

   ```javascript
   self._tryConsumePendingTool = function () {
     if (!pendingToolName && !pendingToolFormMode) return;
     if (pendingToolFormMode === 'edit' && pendingToolName) {
       var name = pendingToolName;
       pendingToolName = null;
       pendingToolFormMode = null;
       selectTool(name);
     }
   };
   ```

9. **Property accessors** (minimum needed):

   ```javascript
   Object.defineProperty(self, '_toolFormMode', {
     get: function () { return toolFormMode; },
     set: function (v) { toolFormMode = v; },
     configurable: true
   });
   Object.defineProperty(self, '_editingTool', {
     get: function () { return editingTool; },
     set: function (v) { editingTool = v; },
     configurable: true
   });
   Object.defineProperty(self, '_pendingToolName', {
     get: function () { return pendingToolName; },
     set: function (v) { pendingToolName = v; },
     configurable: true
   });
   Object.defineProperty(self, '_pendingToolFormMode', {
     get: function () { return pendingToolFormMode; },
     set: function (v) { pendingToolFormMode = v; },
     configurable: true
   });
   ```

10. **`tools-grid.js` widening** — add `onSelectTool` callback + tile keyboard handler:

    ```javascript
    callbacks = callbacks || {};
    var onToggle = callbacks.onToggle || function () {};
    var inFlight = callbacks.inFlight || Object.create(null);
    var onSelectTool = callbacks.onSelectTool || function () {};

    // ... existing tile rendering, but each tile gets tabindex="0"
    html += '<div class="entity-tile tool-tile" data-testid="tool-card" ' +
            'data-name="' + escapeAttr(t.name) + '" role="listitem" tabindex="0">' +
            // ... rest unchanged

    // Replace the L2 tile-click handler:
    var tiles = gridEl.querySelectorAll('.tool-tile');
    for (var k = 0; k < tiles.length; k++) {
      (function (tileEl) {
        tileEl.addEventListener('click', function (e) {
          // Bail if click was on the toggle's interactive surface — toggle owns its own change event.
          if (e.target.closest('.tool-enable-switch')) return;
          var name = tileEl.dataset.name;
          if (name) onSelectTool(name);
        });
        tileEl.addEventListener('keydown', function (e) {
          // Enter or Space activates tile UNLESS focus is on the inner input
          if (e.key !== 'Enter' && e.key !== ' ') return;
          if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
          e.preventDefault();
          var name = tileEl.dataset.name;
          if (name) onSelectTool(name);
        });
      })(tiles[k]);
    }
    ```

11. **`tools-editor.js` skeleton** — write the full module following provider-editor.js patterns. The form-rendering dispatch is the new piece:

    ```javascript
    function renderField(name, prop, value) {
      var type = prop.type;
      var marker = prop.x_marker;
      var hint = prop.ui_hint;
      var label = '<label for="tef-' + escapeAttr(name) + '">' + escapeHtml(prop.title || name) + '</label>';
      var description = prop.description ? '<p class="field-description">' + escapeHtml(prop.description) + '</p>' : '';
      var input = '';
      if (type === 'boolean') {
        input = '<input id="tef-' + escapeAttr(name) + '" type="checkbox" data-field="' + escapeAttr(name) + '"' + (value ? ' checked' : '') + ' />';
      } else if (type === 'integer' && hint === 'dropdown' && Array.isArray(prop.ui_choices)) {
        input = '<select id="tef-' + escapeAttr(name) + '" data-field="' + escapeAttr(name) + '">';
        var sawValue = false;
        for (var i = 0; i < prop.ui_choices.length; i++) {
          var c = prop.ui_choices[i];
          var sel = c.value === value ? ' selected' : '';
          if (c.value === value) sawValue = true;
          input += '<option value="' + escapeAttr(String(c.value)) + '"' + sel + '>' + escapeHtml(c.label) + '</option>';
        }
        if (!sawValue) {
          input += '<option value="' + escapeAttr(String(value)) + '" selected>' + escapeHtml(String(value)) + ' (custom)</option>';
        }
        input += '</select>';
      } else if (type === 'integer') {
        var min = prop.minimum != null ? ' min="' + prop.minimum + '"' : '';
        var max = prop.maximum != null ? ' max="' + prop.maximum + '"' : '';
        input = '<input id="tef-' + escapeAttr(name) + '" type="number" data-field="' + escapeAttr(name) + '" value="' + escapeAttr(String(value)) + '"' + min + max + ' />';
      } else if (type === 'array') {
        input = renderChipListEditor(name, value || [], marker);
      } else if (type === 'string') {
        input = '<input id="tef-' + escapeAttr(name) + '" type="text" data-field="' + escapeAttr(name) + '" value="' + escapeAttr(String(value || '')) + '" />';
      } else {
        input = '<input id="tef-' + escapeAttr(name) + '" type="text" class="field-unknown-type" data-field="' + escapeAttr(name) + '" value="' + escapeAttr(JSON.stringify(value)) + '" />';
      }
      return '<div class="field-row tools-editor-field" data-field-name="' + escapeAttr(name) + '">' +
             label + input + description + '</div>';
    }
    ```

    Chip-list editor + readers + the rest of the wiring follow the same shape — keep the file under ~400 LoC by extracting tiny helpers.

12. **Asset test** — `tests/test_tools_admin_editor_assets.py` (mirror L2's fixture):

    ```python
    """Asset wiring for the F6 L3 per-tool editor."""
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
    import the_one.interfaces.web.app as web_app
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


    class TestToolsEditorAssets:
        async def test_tools_editor_js_served(self, client: AsyncClient) -> None:
            resp = await client.get("/static/js/areas/admin/tools-editor.js")
            assert resp.status_code == 200
            assert "App.admin.renderToolsEditor" in resp.text

        async def test_index_html_includes_tools_editor_script(self, client: AsyncClient) -> None:
            resp = await client.get("/static/index.html")
            assert resp.status_code == 200
            assert "tools-editor.js" in resp.text
    ```

13. **Run the verification block** above; paste relevant pytest summaries into the L3 flight-log entry.

## Edge Cases

- **Save returns updated row WITHOUT `schema`**: L1's `upsert_tool_config` returns 4 fields (`name, description, enabled, config`). The orchestrator's `onSaveSuccess` must MERGE preserving the prior `schema` so the next render doesn't break (the editor sub-module reads `toolDetail.schema` to know which fields to render). Codified in the implementation snippet.
- **Schema field of type `array` with no `items`**: defensive — render as chip-list anyway. The L1 `_enrich_schema_with_markers` doesn't touch nested array `items`; Pydantic emits `{"type": "array", "items": {"type": "string"}}` for `list[str]`. If `items.type !== 'string'`, the chip-list reader still returns string chips (the operator types strings into the input); on save, the API's Pydantic validator catches the type mismatch and returns 422 — surfaced inline.
- **`ui_choices` integer values vs string saved value**: `<option value="">` is always a string in DOM. On read-back, parse `parseInt(.value, 10)` for `type=integer` fields. Otherwise the form would round-trip integers as strings and the L1 422 validator would catch them.
- **PUT returns 422 with array `detail`**: render each `loc.join('.') + ': ' + msg` as a `field-error` adjacent to the matching `[data-field-name="{loc[-1]}"]` row. If `loc` doesn't match any field row, surface the full message in `.editor-error`.
- **PUT returns 4xx with non-array `detail` (e.g., HTTPException with `detail="Tool not found: ..."`)**: surface `detail` string in `.editor-error`; keep dirty.
- **Editor mount with `editingTool.config` missing keys** (operator added a new field in code; old saved rows lack it): the form renders defaults from `prop.default`. On save, the full validated dict goes back. No silent loss of operator overrides on adjacent fields.
- **Chip-list backspace-on-empty when no chips exist**: noop — bail when `chips.length === 0`.
- **Chip duplicate**: silently dedupe on add (`if (chips.includes(value)) return;`). Keeps the saved list clean.
- **Chip with whitespace**: trim on add (`.trim()`); empty-after-trim → don't add.
- **Multiple comma-separated entries pasted into chip input**: split on `,`, trim each, add each as a chip. Standard UX for chip inputs.
- **Direct-load `#admin/tools/nonexistent`**: `selectTool` fetch returns 404; `App.showFlash` surfaces error; orchestrator stays on the grid (since `toolFormMode` was never set on failure).
- **Tile keyboard activation while focus is on the inner input**: the keydown handler bails when `document.activeElement.tagName === 'INPUT'` so Space on the toggle still flips the toggle (native behavior). Enter/Space outside the toggle navigates.
- **Section-nav Tools click while editor is mounted on the SAME tool-name path**: `setCategory('tools')` fires; the dirty-gate at admin.js:167 catches; on confirm, exits editor and shows the grid.
- **Section-nav Tools click while editor is mounted on a DIFFERENT category**: `setCategory('tools')` triggers `doSetCategory('tools')` which clears `toolFormMode`; renders the grid.
- **uvicorn `--reload` doesn't watch static files**: `make rebuild` is required for the new tools-editor.js to be served. Documented in verification step 6.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin.js` — orchestrator widening: 4 new state vars; widened `_setCategory`, `serializeState`, `hydrateState`; new `selectTool`, `_tryConsumePendingTool`, `exitEditor` (helper); editor branch in `renderToolsPanel`; widened `inEditor` gate; 4 new property accessors.
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` — adds `onSelectTool` callback; tile-click navigates instead of forwarding; tile gets `tabindex="0"`; keydown handler.
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` — new sub-module (~350 LoC).
- `the_one/interfaces/web/static/css/admin.css` — chip-list + field-error + editor-row styling.
- `the_one/interfaces/web/static/index.html` — script tag for tools-editor.js.
- `Makefile` — verify-serving loop appended with `admin/tools-editor.js`.
- `tests/test_tools_admin_editor_assets.py` — new (2 tests).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test-unit` green (modulo CSS-token deselect)
- [ ] `make rebuild` succeeds; `make verify-serving` shows tools-editor.js as 200
- [ ] Live smoke (manual): tile click → editor; field edits → dirty; Save → PUT → server reflects; Cancel → restore; Back-when-dirty → confirm dialog; reload-when-dirty → browser confirms
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
