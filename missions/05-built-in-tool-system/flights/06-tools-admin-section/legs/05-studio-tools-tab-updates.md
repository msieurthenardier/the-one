# Leg: 05-studio-tools-tab-updates

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Surface F6's two new operator-state surfaces in the Studio agent-editor's Tools tab. (1) **Disabled-tool surfacing**: tools the operator has disabled at the admin grid render with a strikethrough name, dim-row styling, "Disabled by operator" tooltip, and a `disabled` attribute on the checkbox — clicks are noop. The agent's existing `enabled_tools` / `disabled_tools` data is preserved unchanged (no auto-stripping). (2) **Per-agent override UI**: each ENABLED tool row gets a collapsible `<details>` panel below it labeled "Narrow constraints", which lazy-loads the tool's schema on first open and renders typed widgets for each field. Marker-dispatch differs from L3's admin form: `Narrow` widgets are constrained to the operator's saved value (the agent narrows further); `NarrowSuperset` shows operator's items as locked chips with an "add more" input; `Substitute` is free-form; unmarked operator-only fields (e.g., `redirect_cap`) are HIDDEN. Save flows through the existing agent-editor save pipeline by widening `studio.js::collectFormData` to walk a new `[data-tool-override-tool][data-tool-override-field]` attribute pattern and assemble `tool_overrides: {tool_name: {field: value, ...}}`. To avoid drift between admin and agent forms, L3's inline form helpers (`renderField`, chip-list editor, `readFieldValue`) are EXTRACTED into a shared `admin/tools-form-helpers.js` module that both `tools-editor.js` and `tools-tab.js` consume.

## Context

- **F6 mission goal — agent-level override surface**: operators set tool-level baselines (L1-L4); agents narrow within those baselines for least-privilege per role. The resolver at `the_one/tools/resolver.py` already enforces the marker semantics on save (server-side validation); L5's UI is the operator's editing surface.
- **F6 Decision 4** (typed widget per field for agent-level overrides): widget enforces `Narrow`-marked fields by reading the operator's saved value (NOT the schema's `le`/`ge`) and constraining the agent's input to be `<=` (int), subset (Narrow list), or superset (NarrowSuperset list). Validation is client+server; client-side is UX, server-side is the security boundary (already in F2 resolver tests).
- **F6 Decision 8** (Studio Tools tab disabled-tool surfacing): disabled tools show in the per-agent grid with `disabled` HTML attribute, "Disabled by operator" tooltip, strikethrough on the name, dim row. Click is no-op. Agent's data preserved (NOT auto-stripped) — when the operator re-enables, the agent's prior on/off state survives unchanged.
- **F6 Decision 9** (Substitute-vs-Narrow agent UI):
  - `Narrow` (int) → `<input type=number max={operator_value}>`
  - `Narrow` (list[str]) → chip-list constrained to subset of operator's
  - `NarrowPrefix` (list[str]) → chip-list with path-prefix-checked entries (admin-side L3 just uses plain chip-list; L5 same — the prefix semantic is purely server-side validation)
  - `NarrowSuperset` (list[str]) → chip-list with operator's items rendered as locked chips (agent must contain operator's; agent may add more)
  - `Substitute` (any) → free-form input typed to field's base type
  - Unmarked field (e.g., `redirect_cap`) → operator-only; HIDDEN from agent override surface (operator can set; agent can't override; the F2 resolver raises `ValueError("... no Narrow/Substitute marker ...")` on agent override of an unmarked field).
- **F6 Decision 12** (two-Reviewer-pass batching): L5 commits no docs. The agent override UX is documented in `agents.md` at L9.
- **F2 `tool_overrides` field shape**: `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None = None` at `the_one/agent/config.py:65`. Empty dict = no overrides; per-tool entries are validated by `resolve()` at AgentFactory.create() time. L5's save shape: `data.tool_overrides = {tool_name: {field: value, ...}}` — only tools with at least one set field appear in the dict.
- **L3 form-helper extraction rationale**: tools-editor.js (admin) renders fields with the schema's `le`/`ge` as the ceiling. tools-tab.js (agent) renders the same fields but with the operator's saved value as the ceiling. Same widget shapes (number, dropdown, chip-list, text), different ceilings + different "locked-chip" rendering for NarrowSuperset. Two implementations would drift; L5 extracts the renderer into a shared `admin/tools-form-helpers.js` module that takes a `context = {mode: 'admin' | 'agent', operatorValue?: any}` parameter. tools-editor.js (post-extraction) and tools-tab.js (new caller) both consume the shared helpers. Cost: tools-editor.js touched outside L5's "Studio only" scope — but the alternative (duplicate logic, 4 marker types × 2 modes = guaranteed drift) is worse.
- **Studio data-attribute conventions**: studio.js:725 reads `[data-tool]` for the tool-toggle checkboxes; studio.js:710 reads `[data-field]` for general-field inputs. L5 introduces `[data-tool-override-tool="{name}"][data-tool-override-field="{fname}"]` so studio.js's `collectFormData` walks them into `tool_overrides`. The two-attribute split avoids ambiguity if a future field uses `field-input` — the `tool-override` prefix is the disambiguator.
- **`<details>`/`<summary>` for the panel**: native HTML disclosure widget — keyboard-operable (Enter/Space toggles), screen-reader announces "Narrow constraints, collapsed/expanded", no JS needed for the toggle. Lazy-fetch fires on `toggle` event when `details.open === true`. CSS opens with chevron rotation matching the existing studio collapse pattern.
- **Lazy schema fetch**: each tool's schema is ~1-3 KB JSON. Fetching all 19 at agent-edit mount = wasteful (operator typically narrows 0-2 tools per agent). L5 fetches lazily on `<details>` first-open; a closure-local `schemaCache: {name → schema}` short-circuits subsequent opens. The disabled-tool set is fetched eagerly (single GET at editor mount; needed for grid rendering, not just override panels).
- **TOOL_CATEGORIES already lives in studio.js** as a callback param to renderToolsTab (passed in from studio.js where the agent-editor is mounted). L2 added the same map in tools-grid.js. Verify both maps match during implementation; if they drift, log a deviation.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/tools-tab.js` (93 lines) — the existing agent-editor Tools tab; currently renders MCP stub + 4-category checkbox grid. L5 widens significantly.
- `the_one/interfaces/web/static/js/areas/studio.js:649-762` — the agent-editor orchestrator's `collectFormData` + the `editorEl.querySelectorAll('.tool-toggle')` walk. L5 widens `collectFormData` to walk override inputs.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js:140-144` — where `renderToolsTab` is invoked. L5 plumbs new callbacks: `disabledTools: Set<string>`, `operatorConfigs: {name → {enabled, config}}`, `onPanelExpand: function(name) → Promise<schema>`.
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` (post-L4, **595 lines**) — source of `renderField`, chip-list helpers, `readFieldValue`. L5 extracts these into a shared module; tools-editor.js post-extraction imports them.
- `the_one/interfaces/web/api.py` (post-L1):
  - `GET /api/tools/configs` returns `[{name, description, enabled, config}, ...]` — L5's eager mount-time fetch.
  - `GET /api/tools/configs/{name}` returns `{name, description, enabled, config, schema}` — L5's lazy per-panel-expand fetch.
- `the_one/agent/config.py:65` — `tool_overrides: dict[str, dict[str, Any]] | None`.
- `the_one/tools/resolver.py` — `_check_narrow`, `_check_narrow_prefix`, `_check_narrow_superset`, `Substitute`. L5's client-side validation must match these (or be lenient — server is the boundary; client is UX).

## Outputs

### New shared module — `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` (~310 LoC, extracted from tools-editor.js)

Per-Reviewer (medium): kept under `admin/` (not `shared/`) since the rendering substrate was authored for the admin form first and Studio is the second consumer. Top-of-file comment notes the cross-area consumption: `// Shared form-helper module — owned by admin/ but consumed by studio/tools-tab.js too. Future: move to shared/ if a third consumer appears.`

- IIFE wrapper; `window.App.adminFormHelpers = { renderField, wireChipListEditor, readFieldValue, chipExists, readChipListValue, renderChipListEditor, cssEscape }`.
- **Helpers extracted** from tools-editor.js (per-Reviewer high precision pin):
  - `renderField` (line 150 in current tools-editor.js)
  - `renderChipListEditor` (line 221)
  - `readChipListValue` (line 242)
  - `readFieldValue` (line 256)
  - `cssEscape` (line 294)
  - `wireChipListEditor` (line 448)
  - `chipExists` (helper utility)
- **Helpers KEPT in tools-editor.js** (admin-orchestrator concerns or Save-flow specific):
  - `renderEnabledRow` (line 143) — admin-only `enabled` checkbox row
  - `getFormSnapshot` (line 278) — admin dirty-tracking specific
  - `clearFieldErrors` / `renderFieldErrors` — admin Save-422 inline error UX
  - `renderTestSuccess` / `renderTestError` — L4 test-button helpers
  - `wireEvents` (line 299) — admin orchestrator
  - `_TESTABLE_TOOLS` constant — L4 admin-only
  - Save handler / Cancel handler / Test handler / Back handler
- **Designer Q1**: `clearFieldErrors` / `renderFieldErrors` ALSO extract — Studio's tool_overrides 422 path needs them. Add to the extraction list. Parameterize the field-row selector: `renderFieldErrors(container, errors, options = {fieldRowSelector: '[data-field-name]'})` so admin uses `data-field-name` and Studio uses `data-tool-override-tool="{name}"][data-tool-override-field="{field}"`. Final extraction list: `renderField, renderChipListEditor, readChipListValue, readFieldValue, cssEscape, wireChipListEditor, chipExists, clearFieldErrors, renderFieldErrors`.
- **Designer Q4**: `getFormSnapshotForTool` was a typo in the leg's earlier draft — drop from exports list. Studio uses its own `onChange` callback for dirty-tracking; admin's `getFormSnapshot` stays admin-local.
- `renderField(name, prop, value, context)` — context object:
  - `context.mode: 'admin' | 'agent'`
  - `context.operatorValue: any` (when `mode === 'agent'`; the saved operator value used as the ceiling for Narrow / locked entries for NarrowSuperset / etc.)
  - `context.attrPrefix: 'data-field' | 'data-tool-override-field'` (the data-attribute name to use; `data-field` for admin, `data-tool-override-field` for agent)
  - `context.toolName: string` (when agent mode; surfaces as `data-tool-override-tool="{name}"` on every input — feeds collectFormData's walk)
- Marker-aware dispatch in agent mode:
  - `bool` → `<input type=checkbox>` (no marker-narrow semantics; agent toggles freely)
  - `integer` + `Narrow` + `ui_hint=dropdown` → `<select>` filtered to ui_choices entries `<= operator_value`
  - `integer` + `Narrow` (no dropdown) → `<input type=number min={prop.minimum} max={operator_value}>` — `max` is operator's value (per Decision 4 narrowing-downward semantics from `_check_narrow` at resolver.py:108-138); `min` stays at the schema's `prop.minimum` (the absolute floor — agent can narrow as low as the schema allows). Per-Reviewer (high): the leg's earlier draft omitted `min`, which would've allowed agent values below the schema floor — server validates but UX should match.
  - `integer` + no marker → HIDDEN (operator-only field; agent override would be rejected by resolver)
  - `array` + `Narrow` (list[str]) → chip-list editor where chips MUST be drawn from operator's saved list (typed input shows autocomplete from operator's items; non-matching entry → red border + tooltip)
  - `array` + `NarrowSuperset` (list[str]) → chip-list with operator's items rendered as locked. Per-Reviewer (low): extend `renderChipListEditor` to accept a `lockedItems: Set<string>` param; chips for those values render WITHOUT the `<button class="chip-remove">` element entirely (NOT just `display: none` — keyboard focus order shouldn't include hidden buttons; screen readers shouldn't announce them). CSS `.chip[data-locked]` still styles them (dimmer + cursor:default) for visual differentiation.
  - `array` + `NarrowPrefix` (list[str]) → chip-list (admin-style; entries must be path-prefixes of an operator entry — server validates; client is lenient)
  - `string` + `Substitute` → `<input type=text>` (free-form; no comparison)
  - Unknown / un-marked → HIDDEN
- `wireChipListEditor(containerEl, callbacks)` — same chip-list event wiring (Enter/comma/backspace/×) but with callback hooks for `onChipAttempt(value)` returning `accept | reject` so the agent-mode caller can validate against operator's set.
- `readFieldValue(inputEl)` — same dispatch on widget shape; returns the parsed value.
- `chipExists(containerEl, value)` — dedupe utility.
- The module is loaded via `<script src="/static/js/areas/admin/tools-form-helpers.js"></script>` BEFORE `tools-editor.js` and `studio/tools-tab.js` so the namespace is populated at consume time.

### `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` (delta)

- **Drop the inline helpers** that move to `tools-form-helpers.js` (~150 LoC removed).
- **Replace inline calls** with `window.App.adminFormHelpers.renderField(name, prop, value, {mode: 'admin', attrPrefix: 'data-field'})`.
- **Replace inline chip-list wiring** with `window.App.adminFormHelpers.wireChipListEditor(...)`.
- **Behavior unchanged** — admin form renders identically; this is a pure extraction. L7 Playwright tests for L3 still pass.
- File shrinks from ~580 → ~430 lines.

### `the_one/interfaces/web/static/js/areas/studio/tools-tab.js` (widened from 93 → ~300 lines)

- **New callback params**: `disabledTools: Set<string>`, `operatorConfigs: {name → {enabled, config}}`, `fetchToolSchema: function(name) → Promise<schema>` (the lazy schema fetcher; closure-cached in studio.js).
- **Disabled-tool styling**: per-tool row, when `disabledTools.has(name)`, the rendered HTML adds:
  - `<label class="tool-row tool-row-disabled" title="Disabled by operator">`
  - `<input type="checkbox" disabled ...>` (the `disabled` attr is the source of truth)
  - `<span class="tool-name tool-name-strike">{name}</span>` (CSS strikethrough)
- **Override panel** (per-tool, only when NOT disabled AND tool's Config has at least one Narrow/Substitute-marked field — the "is the override surface non-empty" check requires the schema, which is lazy-fetched. Render a placeholder `<details>` shell for every enabled tool; on first expand, fetch schema and render fields. If fetched schema has zero overridable fields, replace panel content with `<p>No constraints to narrow.</p>`):
  ```html
  <details class="tool-row-overrides" data-tool="{name}">
    <summary>Narrow constraints</summary>
    <div class="tool-row-overrides-body">
      <p class="loading">Loading…</p>
    </div>
  </details>
  ```
- **Toggle handler**: on `<details>` `toggle` event when `details.open === true`, lazy-fetch schema, render fields:
  ```javascript
  details.addEventListener('toggle', function () {
    if (!details.open) return;
    if (details.dataset.loaded === 'true') return;
    details.dataset.loaded = 'true';
    var name = details.dataset.tool;
    fetchToolSchema(name).then(function (detail) {
      var bodyEl = details.querySelector('.tool-row-overrides-body');
      var schema = detail.schema;
      var operatorConfig = detail.config;  // operator's saved values
      var agentOverride = (agent.tool_overrides || {})[name] || {};
      var fieldNames = Object.keys(schema.properties || {});
      var html = '';
      var rendered = 0;
      for (var i = 0; i < fieldNames.length; i++) {
        var fname = fieldNames[i];
        var prop = schema.properties[fname];
        var marker = prop.x_marker;
        // Skip un-marked operator-only fields entirely.
        if (!marker) continue;
        var operatorVal = (fname in operatorConfig) ? operatorConfig[fname] : prop['default'];
        var agentVal = (fname in agentOverride) ? agentOverride[fname] : null;
        html += window.App.adminFormHelpers.renderField(fname, prop, agentVal, {
          mode: 'agent',
          operatorValue: operatorVal,
          attrPrefix: 'data-tool-override-field',
          toolName: name
        });
        rendered++;
      }
      if (rendered === 0) {
        bodyEl.innerHTML = '<p class="empty-state">No constraints to narrow.</p>';
      } else {
        bodyEl.innerHTML = html;
        // Wire chip-list interactions inside the new panel.
        var chipEditors = bodyEl.querySelectorAll('.chip-list-editor');
        for (var c = 0; c < chipEditors.length; c++) {
          window.App.adminFormHelpers.wireChipListEditor(chipEditors[c], {
            onChange: function () { if (callbacks.onChange) callbacks.onChange(); }
          });
        }
        // Wire the input change events for dirty-tracking.
        var fieldInputs = bodyEl.querySelectorAll('[data-tool-override-field]');
        for (var f = 0; f < fieldInputs.length; f++) {
          fieldInputs[f].addEventListener('change', function () {
            if (callbacks.onChange) callbacks.onChange();
          });
        }
      }
    }).catch(function () {
      var bodyEl = details.querySelector('.tool-row-overrides-body');
      bodyEl.innerHTML = '<p class="error">Failed to load schema.</p>';
      details.dataset.loaded = 'false';  // allow retry on next open
    });
  });
  ```
- Disabled tools have NO `<details>` panel (operator-disabled = no narrowing surface relevant; agent's existing override data is preserved silently in the agent's saved JSON via the orchestrator NOT auto-stripping).

### `the_one/interfaces/web/static/js/areas/studio.js` (delta)

- **Mount-time fetch** of `/api/tools/configs` (eager) — caches `disabledTools: Set<string>` and `operatorConfigs: {name → {enabled, config}}`. Fires once per agent-edit mount; cleared on agent change.
- **Lazy schema fetcher** `fetchToolSchema(name)` — closure-cached; subsequent calls return cached promise. Per-Reviewer (medium): the cache stores the **promise**, not the resolved value, so concurrent callers (e.g., user opens + closes + opens fast) reuse the same in-flight promise. Callable from tools-tab.js. The schema cache survives across agent changes within the same studio area lifetime — schemas are static at runtime. Operator's saved configs cache (`operatorConfigs`) and `disabledTools` are RE-fetched on every agent-edit mount (these can change between agent edits in another tab).
- **Pass new callbacks to `renderToolsTab`** (in agent-editor.js; studio.js triggers the agent-editor mount):
  ```javascript
  window.App.studio.renderToolsTab(toolsPanel, agent, {
    toolCategories: callbacks.toolCategories,
    allTools: callbacks.allTools,
    onChange: callbacks.onChange,
    disabledTools: callbacks.disabledTools,        // NEW
    operatorConfigs: callbacks.operatorConfigs,    // NEW
    fetchToolSchema: callbacks.fetchToolSchema     // NEW
  });
  ```
- **`collectFormData` widening** at studio.js:708-762:
  ```javascript
  // L5 — collect tool_overrides from override panels.
  var overrideInputs = editorEl.querySelectorAll('[data-tool-override-tool][data-tool-override-field]');
  var overrides = {};
  for (var o = 0; o < overrideInputs.length; o++) {
    var oi = overrideInputs[o];
    var toolName = oi.dataset.toolOverrideTool;
    var fieldName = oi.dataset.toolOverrideField;
    var val = window.App.adminFormHelpers.readFieldValue(oi);
    // Skip empty overrides — agent.tool_overrides only contains tools with at least one set field.
    if (val === null || val === undefined || (Array.isArray(val) && val.length === 0) || val === '') continue;
    if (!overrides[toolName]) overrides[toolName] = {};
    overrides[toolName][fieldName] = val;
  }
  // chip-list editors live in <div class="chip-list-editor"> with data-tool-override-field on the div.
  // The querySelector above picks them up (they have data-tool-override-field too) — readFieldValue dispatches.
  data.tool_overrides = Object.keys(overrides).length > 0 ? overrides : null;
  ```
- **Disabled-tool toggle preservation** (Decision 8): the existing `enabledNames`/`disabledNames` walk at studio.js:725-748 reads ALL `.tool-toggle` checkboxes including disabled ones. Disabled checkboxes still report `.checked` = current state (HTML `disabled` attribute does NOT block reading the property; only blocks user toggling). So the agent's saved on/off state survives operator-disable cycles automatically — no special handling needed.

### `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` (delta)

- Plumb the 3 new callbacks (`disabledTools`, `operatorConfigs`, `fetchToolSchema`) from studio.js through to renderToolsTab. ~6 lines added at the call site (line 140-144 area).

### CSS additions — `the_one/interfaces/web/static/css/studio.css` (append)

- `.tool-row-disabled { opacity: 0.5; cursor: not-allowed; }`
- `.tool-row-disabled .tool-toggle { cursor: not-allowed; }`
- `.tool-name-strike { text-decoration: line-through; color: var(--fg-faint); }`
- `.tool-row-overrides { margin: 4px 0 8px 28px; padding: 0; border-left: 2px solid var(--border-strong); }` (left-border indicates nesting under tool row)
- `.tool-row-overrides[open] { padding: 4px 0 8px 12px; }`
- `.tool-row-overrides summary { cursor: pointer; padding: 4px 8px; font-size: var(--font-size-small); color: var(--fg-secondary); user-select: none; }`
- `.tool-row-overrides summary:hover { color: var(--accent); }`
- `.tool-row-overrides-body { padding: 4px 8px 0; }`
- `.tool-row-overrides .field-row { margin-bottom: 8px; }` (smaller gaps for the nested form)
- `.tool-row-overrides .chip[data-locked] { background: var(--surface-elevated); opacity: 0.7; cursor: default; }` (NarrowSuperset locked chips)
- `.tool-row-overrides .chip[data-locked] .chip-remove { display: none; }`
- `.tool-row-overrides .empty-state { font-size: var(--font-size-small); color: var(--fg-secondary); padding: 4px 8px; }`

### `the_one/interfaces/web/static/index.html`

- Insert `<script src="/static/js/areas/admin/tools-form-helpers.js"></script>` at line 48 area, **just before `tools-grid.js`** (placement within the admin/* block; alphabetic + admin-grouping). Per-Reviewer (high) clarification: studio modules load BEFORE admin modules in the HTML (lines 39-45 vs 46-52), so a helpers module under admin/ loads AFTER tools-tab.js in declaration order. **This is runtime-fine** — both consumers' render functions execute at agent-edit mount time, by which point all top-level scripts have parsed and `window.App.adminFormHelpers` is populated. The placement choice is for human readability + the verify-serving alphabetic ordering, NOT for runtime correctness.

### `Makefile:93` — verify-serving loop

- Append `admin/tools-form-helpers.js` to the asset list.

### Tests

- `tests/test_tools_form_helpers_assets.py` (new, 1 test):
  - `test_tools_form_helpers_js_served` — assert `GET /static/js/areas/admin/tools-form-helpers.js` returns 200 and contains `window.App.adminFormHelpers`.

- `tests/test_agent_tool_overrides_round_trip.py` (new, 2 tests — per-Reviewer medium: catches AgentConfig pydantic round-trip independently of the JS layer):
  - `test_agent_put_with_null_tool_overrides_round_trips` — POST/PUT agent with `tool_overrides=null`; GET → `tool_overrides is None` (preserved).
  - `test_agent_put_with_tool_overrides_round_trips` — POST/PUT agent with `tool_overrides={"http_request": {"host_allowlist": ["example.com"]}}`; GET → exact match. Uses the existing `tests/test_db_api.py:16-35` client fixture pattern.

- **Behavior coverage deferred to L7 Playwright** (per F6 user direction "L7 = full Playwright coverage"). L7 tests:
  - Disabled tool shows strikethrough + dim + un-clickable.
  - Re-enabling restores interactivity; agent's prior state preserved.
  - Override panel collapsed by default; expands on click; lazy-fetches schema.
  - Narrow int → max attr matches operator's saved value.
  - NarrowSuperset → operator's items render as locked chips with no × button.
  - Substitute → free-form input.
  - Unmarked field → not rendered in panel.
  - Save assembles `tool_overrides` correctly; PUT to /api/agents/{name} round-trips.

## Acceptance Criteria

- [x] New shared module `tools-form-helpers.js` exists, exports `window.App.adminFormHelpers = {renderField, wireChipListEditor, readFieldValue, chipExists}`.
- [x] `renderField(name, prop, value, context)` accepts a context object with `mode`, `operatorValue`, `attrPrefix`, `toolName`.
- [x] **Admin mode** (`context.mode === 'admin'`) renders fields IDENTICALLY to L3's pre-extraction behavior — all L3 acceptance criteria + the L7 Playwright admin tests pass unchanged.
- [x] **Agent mode** (`context.mode === 'agent'`):
  - `bool` → checkbox.
  - `integer` + `Narrow` + `ui_hint=dropdown` → `<select>` filtered to ui_choices `<= operatorValue`.
  - `integer` + `Narrow` (no dropdown) → `<input type=number max={operatorValue}>` — operator's value as the ceiling, NOT the schema's `le`.
  - `integer` + no marker → element is NOT rendered (skipped in the iteration).
  - `array` + `Narrow` → chip-list constrained to subset of operator's items.
  - `array` + `NarrowSuperset` → chip-list with operator's items as locked chips (`.chip[data-locked]`, no × button); agent additions are removable.
  - `array` + `NarrowPrefix` → chip-list (admin-style; client lenient; server validates).
  - `string` + `Substitute` → `<input type=text>` free-form.
  - All inputs carry `data-tool-override-tool="{toolName}" data-tool-override-field="{fieldName}"`.
- [x] `tools-editor.js` (admin) post-extraction calls `window.App.adminFormHelpers.renderField(...)` with `mode: 'admin'`. File shrinks ~150 lines.
- [x] `tools-tab.js` (Studio) widens to render `.tool-row-disabled` styling for tools where `disabledTools.has(name)`.
- [x] Disabled tool's checkbox carries the `disabled` HTML attribute; click is no-op; agent's prior state preserved across operator-disable/re-enable cycles.
- [x] Each ENABLED tool's row gets a sibling `<details class="tool-row-overrides" data-tool="{name}">` panel labeled "Narrow constraints"; collapsed by default.
- [x] On first `<details>` open: lazy-fetches `GET /api/tools/configs/{name}` (cached after first fetch); renders override fields via `window.App.adminFormHelpers.renderField('agent', ...)`.
- [x] If schema has zero overridable (marker-bearing) fields, panel body shows "No constraints to narrow.".
- [x] If schema fetch fails, panel body shows "Failed to load schema." and `data-loaded="false"` so the next open retries.
- [x] `studio.js::collectFormData` walks `[data-tool-override-tool][data-tool-override-field]` inputs, builds `tool_overrides: {name → {field → value}}`. Empty per-tool entries are dropped. Empty top-level dict becomes `null` (not `{}`).
- [x] **`fetchToolSchema(name)` caches the PROMISE (not the resolved value)** — concurrent callers during an in-flight fetch reuse the same promise; no double-fetch.
- [x] **Schema cache survives across agent changes** within the studio area's lifetime; **`operatorConfigs` and `disabledTools` are re-fetched per agent-edit mount**.
- [x] **For unsaved tools, `operatorConfig === {}`** (NOT `null`); the panel falls back to `prop['default']` for each field's operator value.
- [x] **Narrow integer `min` floor**: `<input type=number min={prop.minimum} max={operator_value}>` — schema floor preserved; operator's value as the ceiling.
- [x] **NarrowSuperset locked chips render WITHOUT the `<button class="chip-remove">` element entirely** (NOT just `display: none` via CSS). Keyboard focus order excludes them; screen readers don't announce them. CSS `.chip[data-locked]` styles for visual differentiation.
- [x] **Disabled-tool checkbox `.checked` walk preserved**: existing studio.js:725-748 `enabledNames`/`disabledNames` walk reads `.checked` on ALL `.tool-toggle` checkboxes including disabled ones. Agent's prior on/off state survives operator-disable cycles.
- [x] `studio.js` mount-time fetch of `/api/tools/configs` populates `disabledTools` set + `operatorConfigs` cache; passed to renderToolsTab.
- [x] `studio.js` `fetchToolSchema(name)` lazy-fetches with closure cache; passed to renderToolsTab.
- [x] `agent-editor.js` plumbs the 3 new callbacks (`disabledTools`, `operatorConfigs`, `fetchToolSchema`) from studio.js to renderToolsTab.
- [x] CSS additions: `.tool-row-disabled`, `.tool-name-strike`, `.tool-row-overrides`, `.tool-row-overrides summary`, `.tool-row-overrides-body`, `.tool-row-overrides .chip[data-locked]`. All token references resolve.
- [x] HTML template loads `tools-form-helpers.js` BEFORE `tools-editor.js` and `tools-tab.js`.
- [x] `Makefile:93` includes `admin/tools-form-helpers.js` in verify-serving loop.
- [x] `tests/test_tools_form_helpers_assets.py` ships with 1 test; passes.
- [x] **L0-L4 regression unchanged** — no existing test touches the new attribute pattern; the existing `[data-tool]` checkbox walk at studio.js:725 is preserved verbatim.
- [x] `make test-unit` is green (modulo CSS-token deselect).
- [x] `make rebuild` succeeds; `make verify-serving` confirms the new file is served (200).
- [x] No L0/L1 backend code is touched.

## Verification Steps

```bash
# 1. Module structure — new shared helpers
docker exec the-one cat the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js | grep -c "App.adminFormHelpers"  # 1+
docker exec the-one cat the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js | grep -c "renderField\|wireChipListEditor\|readFieldValue"  # 3+

# 2. Admin tools-editor.js post-extraction — no longer carries inline renderField/chip-list helpers
docker exec the-one grep -c "function renderField\|function wireChipListEditor" the_one/interfaces/web/static/js/areas/admin/tools-editor.js  # 0 (extracted)
docker exec the-one grep -c "App.adminFormHelpers" the_one/interfaces/web/static/js/areas/admin/tools-editor.js  # 1+ (consumer)

# 3. Studio tools-tab.js widening
docker exec the-one grep -c "tool-row-disabled\|tool-row-overrides" the_one/interfaces/web/static/js/areas/studio/tools-tab.js  # 2+
docker exec the-one grep -c "fetchToolSchema\|App.adminFormHelpers" the_one/interfaces/web/static/js/areas/studio/tools-tab.js  # 2+

# 4. Studio orchestrator widening
docker exec the-one grep -c "data-tool-override-tool\|data-tool-override-field" the_one/interfaces/web/static/js/areas/studio.js  # 2+
docker exec the-one grep -c "tool_overrides" the_one/interfaces/web/static/js/areas/studio.js  # 1+

# 5. CSS
docker exec the-one grep -c "tool-row-disabled\|tool-name-strike\|tool-row-overrides" the_one/interfaces/web/static/css/studio.css  # 3+

# 6. Targeted test
docker exec the-one pytest tests/test_tools_form_helpers_assets.py -x -q

# 7. L0-L4 regression
docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py tests/test_factory.py tests/test_factory_disable_enforcement.py tests/test_api_tool_configs.py tests/test_enrich_schema_with_markers.py tests/test_tools_admin_grid_assets.py tests/test_tools_admin_editor_assets.py tests/test_tools_test_button_assets.py -x -q

# 8. Full unit suite
docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# 9. Static asset wiring
make rebuild
make verify-serving  # 9 admin sub-modules, all 200

# 10. Manual smoke (browser):
#     a. Open Studio → any agent → Tools tab. All 19 tool rows render.
#     b. Disable web_search via #admin/tools toggle → switch back to Studio agent → web_search row shows strikethrough + dim + un-clickable checkbox.
#     c. Re-enable web_search via admin → Studio Tools tab refresh → row interactive again, prior on/off state preserved.
#     d. Click "Narrow constraints" on http_request → panel expands; lazy-fetch fires; widgets render. host_allowlist (Narrow list) → chip-list constrained to operator's items. host_denylist (NarrowSuperset list) → operator's items render as locked chips. default_user_agent (Substitute) → free-form text. redirect_cap (no marker) → not rendered.
#     e. Add an entry to host_allowlist; save agent → API readback shows tool_overrides.http_request.host_allowlist = [...added entry].
#     f. Save with no overrides set → tool_overrides is null in agent JSON (not {}).

# 11. Lint
docker exec the-one ruff check tests/test_tools_form_helpers_assets.py
```

## Implementation Guidance

1. **Extract first** — create `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` by lifting the existing `renderField`, `wireChipListEditor`, `readFieldValue`, `chipExists`, and any related closure helpers from `tools-editor.js`. Wrap in IIFE; expose via `window.App.adminFormHelpers = {...}`. The signatures gain a `context` param; admin-mode callers pass `{mode: 'admin', attrPrefix: 'data-field'}`.
2. **Refactor admin tools-editor.js** — delete the now-extracted helpers; update calls to use `window.App.adminFormHelpers.renderField(name, prop, value, {mode: 'admin', attrPrefix: 'data-field'})`. Run all L0-L4 regression tests + `make rebuild` + manual smoke admin Tools editor — verify behavior is unchanged.
3. **Add the agent-mode branch** to `tools-form-helpers.js::renderField`. The L3 admin-mode dispatch is the baseline; agent mode adds the marker-aware constraints + the operator-only HIDDEN behavior.
4. **Add HTML script tag** at `the_one/interfaces/web/static/index.html` line 47 area: `<script src="/static/js/areas/admin/tools-form-helpers.js"></script>` BEFORE the existing tools-editor.js / tools-grid.js tags.
5. **Add Makefile entry** at line 93.
6. **Widen studio.js** for the mount-time fetch + lazy schema fetcher. Best mount point: alongside the existing `fetchAgents` etc., before the agent-editor mount call. Closure-cache the schema fetcher.
7. **Plumb agent-editor.js** to pass the 3 new callbacks to renderToolsTab.
8. **Widen tools-tab.js**: disabled-tool styling per row, `<details>` panel per enabled tool, lazy-load handler. The chip-list wiring uses the extracted helper.
9. **Widen `collectFormData`** in studio.js to walk override inputs and assemble `tool_overrides`.
10. **CSS additions** to studio.css.
11. **Asset test** + run verification block.

## Edge Cases

- **Agent already has tool_overrides for a tool whose Config has been changed in code** (e.g., a marker removed from a field): the override panel still renders the field (using whatever marker the schema currently declares); if the marker is gone, the field is HIDDEN. The agent's stale override JSON survives in the saved data; the resolver at AgentFactory.create() will raise `ValueError`. **Mitigation**: log a one-line console.warn when the panel skips a marker that's present in the agent's saved overrides — surfaces the drift visibly during dev.
- **Operator changes the saved value AFTER agent narrowed**: e.g., operator's `timeout_seconds_max=60`, agent narrowed to `30`; operator drops to `20`. The agent's saved override is now invalid (30 > 20 = operator's). Resolver raises at AgentFactory.create(). L5's UI: when the panel re-opens, the `<input type=number max={operator_value=20}>` shows `value=30` (from agent override) but the validation flags it red on submit. Acceptable — operator awareness is the point.
- **Empty operator config (no narrowing yet)**: operator value falls back to `prop['default']`. Agent panel renders with the default as the ceiling. If a Narrow field's default is the schema's `le` (often the case), the panel shows the full range — agent can narrow within the absolute hard ceiling.
- **Agent toggle ON for a disabled tool**: when operator disables a tool and agent's `enabled_tools` includes it, `disabledTools.has(name)` is true → checkbox is `disabled` AND visually checked (CSS strikethrough). The agent's data is preserved. When operator re-enables, checkbox un-disables, still checked.
- **Override panel for a disabled tool**: not rendered. Operator-disabled tools have NO `<details>` panel (Decision 8 — operator's intent is "this tool is off"; agent can't narrow what doesn't exist for them). Agent's prior tool_overrides[disabled_tool] entry survives in saved JSON and resurfaces when operator re-enables.
- **Schema fetch fails mid-edit**: panel body shows "Failed to load schema." with `data-loaded="false"`. Operator collapses + re-opens → re-fetches.
- **Agent saves with `tool_overrides = {}`**: collectFormData detects empty dict and sets `data.tool_overrides = null`. The agent's API representation is `null` (not `{}`) — matches AgentConfig's `dict[str, dict] | None` shape.
- **Agent saves with `tool_overrides[tool] = {}` (per-tool entry empty)**: collectFormData skips empty per-tool entries. The tool name doesn't appear in the saved dict at all.
- **Multiple panels expanded**: each panel's lazy-fetch runs independently. The `details.dataset.loaded` flag is per-panel.
- **`<details>` keyboard interaction**: native — Enter/Space on `<summary>` toggles. Tab through tool rows + override panels works without explicit tabindex management.
- **Tools-editor.js extraction breaks L3 acceptance criteria if not done carefully**: the extraction MUST be a pure refactor — admin behavior identical. Run all L3-related tests after the extraction step (step 2) BEFORE proceeding to add agent-mode branches (step 3) — bisects any regression cleanly.
- **Drift between TOOL_CATEGORIES (studio.js + tools-grid.js)**: L2 added the same map in tools-grid.js; the existing studio.js TOOL_CATEGORIES predates F6. If they differ post-L5 implementation, log a deviation. Future L9 docs can address consolidation.
- **`data-tool-override-tool` attribute case sensitivity**: HTML data attributes are lowercased in DOM access (`dataset.toolOverrideTool`). The setter uses kebab-case (`data-tool-override-tool`); the reader uses camelCase (`oi.dataset.toolOverrideTool`). Standard pattern — verify at implementation time.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` — NEW shared module (~250 LoC; extracted + extended).
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` — DELTA: delete extracted helpers; add admin-mode caller stubs (~150 LoC removed).
- `the_one/interfaces/web/static/js/areas/studio/tools-tab.js` — widened from 93 → ~300 LoC (disabled rendering + override panels + lazy-fetch handlers).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — DELTA: plumb 3 new callbacks (~6 lines added).
- `the_one/interfaces/web/static/js/areas/studio.js` — DELTA: mount-time fetch, lazy schema fetcher, callback plumbing, `collectFormData` widening (~50 lines added).
- `the_one/interfaces/web/static/css/studio.css` — append disabled-row + override-panel styling.
- `the_one/interfaces/web/static/index.html` — script tag for tools-form-helpers.js.
- `Makefile` — verify-serving loop appended with `admin/tools-form-helpers.js`.
- `tests/test_tools_form_helpers_assets.py` — NEW (1 test).
- `tests/test_agent_tool_overrides_round_trip.py` — NEW (2 tests, AgentConfig pydantic round-trip independently of the JS layer).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] L3-extraction smoke: admin Tools editor still saves/loads identically (no L3 regression — full L0-L4 regression sweep green: 104 tests passed)
- [x] `make test-unit` green (modulo CSS-token deselect) — 1043 passed, 1 skipped
- [x] `make rebuild` succeeds; `make verify-serving` shows tools-form-helpers.js as 200
- [ ] Live smoke (manual): deferred to L6 HAT (interactive walkthrough — 9 scenarios)
- [x] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` — not yet, batched per F6 two-Reviewer-pass strategy (Decision 12)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
