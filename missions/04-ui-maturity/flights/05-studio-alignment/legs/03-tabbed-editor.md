# Leg: 03-tabbed-editor

**Status**: completed
**Flight**: [Studio Alignment](../flight.md)

## Objective

Establish the codebase's first tab idiom (W3C ARIA `role="tablist"` with **manual activation** + roving `tabindex`) AND migrate the existing agent form content into three tabs (General / Knowledge / Tools) in a single leg. Refactor the agent editor: fixed header (agent name + description) + action cluster `[← Back]  [Delete]  [Save]` + tablist below. Extend hash routing so the active tab is reflected in the URL (`#studio/agents/{name}/{tab}`) and survives refresh. Land `.tablist`, `.tab`, `.tabpanel`, `.editor-header` (canonical), and `.form-actions` placeholders in `components.css`. The Test button (provider connectivity check) is wired in this leg using the existing `/api/providers/{provider_config_id}/test` endpoint.

The leg is intentionally large per the flight spec's resolved Open Question: splitting tab scaffold from content migration would temporarily break form-field tests until both halves landed — unacceptable mid-flight regression-net gap.

## Context

- Legs 01 (sidebar restructure) and 02 (tile grid + `App.confirmDelete`) have landed. `studio.js` is now 1100 LOC. The editor's monolithic form lives in `renderEditor(agent)` at `studio.js:423` and is populated when `selectAgent(agent)` fires.
- The flight spec's resolved Open Question "Tablist activation mode" specifies **manual activation** with roving `tabindex` (Arrow keys move focus only; Enter/Space commits via `replaceState`). Auto-activation would mutate the URL on every arrow keypress, polluting browser history and aligning poorly with the W3C ARIA Authoring Practices for tabs whose activation has side effects.
- The flight spec's resolved Open Question "Hash-encoded tab state" specifies the URL hierarchy:
  - `#studio/agents/{name}` → upgrades to `#studio/agents/{name}/general` via the F3 router's `replaceState` path (zero new redirect logic in studio.js — `serializeState()` returns the longer form).
  - `#studio/agents/{name}/{tab}` → editor with the specific tab active.
  - `#studio/knowledge` and `#studio/tools` (sidebar sections, leg 01) are SEPARATE from the per-agent editor's Knowledge/Tools tabs — they exist in different URL spaces and serve different purposes (sidebar = manage KBs/tools at studio scope; editor tab = attach to this agent).
- The `App.tabs(tablistEl, panelsEl, {onChange, initial})` helper API is callback-style. Returns `{activate(tabId), getActive()}` for imperative control.
- The `<button class="agent-tile" data-testid="agent-item">` tile (leg 02) uses `aria-selected` on the tile itself for the tile-grid case — the tab idiom uses `aria-selected` on `<button role="tab">` elements (different DOM, no conflict).
- `.editor-header` already exists in `studio.css:22` as the editor's top header. Leg 03 lifts it to `components.css` as canonical vocabulary (entity-name + description block above tablist; admin's provider editor will likely need an analogous header in F6).
- The Test button reuses the existing `POST /api/providers/{provider_config_id}/test` endpoint at `the_one/interfaces/web/api.py:538-590`. Empty request body; response shape `{status: "ok"|"error", detail: str}`. The admin reference at `admin.js:710-739` shows the success/failure pattern with `.admin-pf-test-ok` / `.admin-pf-test-fail` spans + flash messages.
- Per the flight spec, this leg consumes F4 + leg 01 + leg 02 vocabulary verbatim where applicable: `.field-row`, `.field-input`, `.field-textarea`, `.field-select`, `.section-title`, `.empty-state`, `.btn-outlined-cyan`, `.btn-filled-cyan`, `.btn-muted-destructive`. Save/Back/Delete behavior in this leg:
  - **Save** is wired (POST/PUT to existing endpoints) but has no dirty-state gating yet — Save is always enabled when an agent is selected. Leg 04 adds the disabled-when-clean behavior.
  - **Back** is new — returns to `#studio/agents` (no dirty-state confirm in this leg; leg 04 adds it).
  - **Delete** keeps its existing inline two-step flow at `studio.js:660-683` (`.delete-btn.confirm` class state, capital "Confirm Delete?" label, 3s revert timer). Per leg 02's flight log: "Editor's 'Delete Agent' button untouched: keeps its inline two-step delete." Leg 03 does NOT migrate it to `App.confirmDelete`. The button moves into the new `.form-actions` cluster but its handler + class state + label travel with it. The casing divergence between the editor (capital-D) and the tile X / chat session (lowercase-d via `App.confirmDelete`) is a Known Issue queued for a future flight.

## Inputs

What exists before this leg runs (post-leg-02 state):

- `the_one/interfaces/web/static/js/areas/studio.js` (1100 LOC):
  - `serializeState()` at `studio.js:28` — returns `'knowledge'` | `'tools'` | `'agents/<name>'` | `'agents'` (per leg 01).
  - `hydrateState(sub)` at `studio.js:42` — parses the four shapes; defensively defaults to `'agents'`.
  - `_writeUrl()` at `studio.js:191-197` — single URL-mutation site; calls `App.router.replaceSub(self.serializeState())`.
  - `selectAgent(agent)` at `studio.js:385` — sets `_selectedAgent`, calls `renderEditor(agent)`, calls `_writeUrl()`.
  - `renderEditor(agent)` at `studio.js:423` — builds the monolithic form into `.studio-editor`. Sections: `.editor-header` (name + Delete button) at line 445; `.editor-form` at line 454 with identity, LLM config, system prompt, tools (4 hardcoded `TOOL_CATEGORIES`), connections, behavior (`max_iterations`), action cluster (Save) — all under one DOM tree.
  - VRAM warning logic at `studio.js:936-1034` — `clearVramWarning()`, `checkVramForModel()`, debounced on model change at `studio.js:643-645`. Renders into `.studio-vram-warning` placeholder at `studio.js:495`.
  - `collectFormData()` at `studio.js:811` — builds the agent payload from form fields (name, description, provider_config_id, llm_model, system_prompt, enabled_tools/disabled_tools, kb_ids, mcp_source_ids, max_iterations).
  - `Save` (`save-agent-btn`) handler at `studio.js:875-930` — `POST /api/agents` (create) or `PUT /api/agents/{name}` (update); reloads list; re-renders editor.
  - `Delete` editor button (`delete-agent-btn`) at `studio.js:380` (testid) and two-step `App.confirmDelete` flow migrated by leg 02. **Out of scope for leg 03 to re-touch** — the editor's delete flow already uses `App.confirmDelete`.
- `the_one/interfaces/web/static/js/areas/admin.js:710-739` — the provider-test endpoint call pattern (success span `.admin-pf-test-ok`, failure span `.admin-pf-test-fail`, flash messages, auto-fetch models for Ollama on success). Reference for the General-tab Test button.
- `the_one/interfaces/web/api.py:538-590` — `POST /api/providers/{provider_id}/test` endpoint. Empty body; response `{status: "ok"|"error", detail: str}`.
- `the_one/agent/config.py:66-104` — `AgentConfig` schema. Fields: `name`, `description`, `provider_config_id`, `llm_model`, `system_prompt`, `enabled_tools` | `disabled_tools`, `kb_ids`, `mcp_source_ids`, `max_iterations`, `direct_actions` (the last is stored but NOT in UI). NO `temperature` / `top_p` / `max_tokens` fields — the Advanced section is purely a stub.
- `the_one/interfaces/web/static/css/components.css` (472 LOC, post-leg-02): canonical F4 + leg-01 + leg-02 vocabulary. NO `.tablist`, `.tab`, `.tabpanel`, `.editor-header`, `.form-actions` yet.
- `the_one/interfaces/web/static/css/studio.css` (post-leg-02): currently houses `.editor-header` at line 22 (will lift to components.css).
- `the_one/interfaces/web/static/js/icons.js`: `chevron-down`, `chevron-right`, `plus`, `square-pen`, `x` available. **Missing**: `arrow-left` (Back button), `play` (Test button) — must be added in this leg.
- `the_one/interfaces/web/static/js/areas/studio/`:
  - `section-nav.js` (102 LOC, leg 01)
  - `stub-knowledge.js` (18 LOC, leg 01) — sidebar Knowledge section
  - `stub-tools.js` (18 LOC, leg 01) — sidebar Tools section
- `the_one/interfaces/web/static/index.html` post-leg-02 script load order at lines 26-40 (per the grounding report). `tabs.js` inserts after `confirm.js` (line 29), before chat sub-modules.
- `tests/browser/test_flow_agent_crud.py` — interacts with `data-field="name"`, `data-field="description"`, `data-field="system_prompt"`; uses `save-agent-btn` and `delete-agent-btn` testids. After leg 03, these fields live inside the General tab. The General tab is the DEFAULT tab on agent select (via the `#studio/agents/{name}` → `#studio/agents/{name}/general` redirect), so its contents render immediately. The tests should pass without modification PROVIDED the General tab content is mounted and visible by default.
- `tests/browser/test_flow_hash_routing.py` lines 94-129 (`test_hash_routing_studio_agent_persists_on_refresh`) — line 114 expects URL to become `#studio/agents/{name}` after agent select. Per the flight spec leg-03 enumeration, this assertion must update to `#studio/agents/{name}/general` (the replaceState upgrade). Update is explicit and one-line.

## Outputs

- `the_one/interfaces/web/static/js/tabs.js` — NEW. Defines `App.tabs(tablistEl, panelsEl, {onChange, initial})` (~70-100 LOC).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — NEW. Defines `App.studio.renderAgentEditor(container, agent, providers, callbacks)` (~150-200 LOC). Builds: `.editor-header` (name + description; for create-mode renders blank/placeholder), `.form-actions` cluster `[← Back]  [Delete]  [Save]`, `.tablist` with three tab buttons, three `.tabpanel` divs. Wires `App.tabs(...)` for keyboard + activation, calls per-tab render helpers to populate panels.
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` — NEW. Defines `App.studio.renderGeneralTab(panel, agent, providers, callbacks)` (~120-180 LOC). Carries the existing form fields (name [create-only], description, system_prompt, provider_config_id, llm_model, max_iterations) using F4 `.field-row`/`.field-input`/`.field-textarea`/`.field-select` vocabulary. Includes the Ollama VRAM warning placeholder + the model-change debounce hook (delegates to existing `checkVramForModel`). Adds: an Advanced collapsible section with disabled inputs (temperature/top_p/max_tokens) + "Coming soon — provider-bound config in a future flight" caption; a Test button that calls `POST /api/providers/{provider_config_id}/test` and renders the result in an `aria-live="polite"` span.
- `the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js` — NEW. Defines `App.studio.renderKnowledgeTab(panel)` (~15-25 LOC). Renders centered `.empty-state` with the exact two-sentence text: "Knowledge bases will be attached to this agent here in a future flight. Knowledge bases can be attached to multiple agents."
- `the_one/interfaces/web/static/js/areas/studio/tools-tab.js` — NEW. Defines `App.studio.renderToolsTab(panel, agent, callbacks)` (~80-120 LOC). Two visually-grouped subsections: (a) "MCP tools" — `.section-title` + `.empty-state` with one-liner ("MCP servers will be configured in the Tools section, then attached here. Tools can be attached to multiple agents."); (b) "Built-in tools" — `.section-title` + the existing `enabled_tools`/`disabled_tools` checkbox UI verbatim (4 hardcoded `TOOL_CATEGORIES` carry forward unchanged from current studio.js:505-524). Select-all/select-none affordances stay if present today.
- `the_one/interfaces/web/static/js/areas/studio.js` MAJOR REWRITE:
  - `renderEditor(agent)` rewritten to delegate to `App.studio.renderAgentEditor(...)`. Removes the inline form rendering (~200 LOC removed).
  - `serializeState()` extended: when `_activeSection === 'agents'` and `_selectedAgent` is set, return `'agents/' + encodeURIComponent(this._selectedAgent.name) + '/' + this._activeTab` (where `_activeTab` is one of `'general' | 'knowledge' | 'tools'`, defaulting to `'general'`).
  - `hydrateState(sub)` extended: parse `agents/{name}/{tab}` (the third segment is the tab); default tab `'general'` if absent; set `_activeTab` accordingly.
  - New `this._activeTab` field initialized to `'general'`. `_activeTab` is per-agent (resets when `_selectedAgent` changes) but persists for the duration of an agent edit session.
  - `setActiveTab(tab, {writeUrl=true})` — analogous to leg 01's `setActiveSection`. Updates `_activeTab`, calls `App.tabs.activate(tab)` for the editor's tablist, writes URL via `_writeUrl()` (default `writeUrl: true`; hydrate-driven calls use `writeUrl: false`).
  - `selectAgent(agent)` updated to reset `_activeTab = 'general'` (or honor `_pendingTabName` when set during hydrate).
  - VRAM warning logic stays in studio.js (still called from the General tab via callback). The model-change debounce continues to invoke `checkVramForModel`. The placeholder `.studio-vram-warning` element moves into the General tab's DOM.
  - `collectFormData()` continues to read from form fields. The fields now live across the three panels but all retain their `data-field="..."` attributes — `collectFormData()` queries by attribute selector, so it works regardless of DOM nesting.
  - Save handler unchanged in this leg (still wired to `save-agent-btn` click; still calls the existing `POST /api/agents` or `PUT /api/agents/{name}`). Save is **enabled** in this leg (no dirty-state gating yet — that's leg 04).
  - Net delta: -50 to -120 LOC in studio.js (the per-tab modules absorb form rendering, but new orchestration plumbing — tab-handle wiring, `setActiveTab`, hydrate extension, callbacks plumbing, Test button handler — adds back ~80-120 LOC); new total ~970-1000 LOC.
- `the_one/interfaces/web/static/css/components.css` GROWS (~80-120 LOC):
  - `.tablist` — flex container, gap, optional bottom border separator.
  - `.tab` — `<button>` reset, padding, `:focus-visible` ring, `[aria-selected="true"]` accent + bottom border.
  - `.tabpanel` — `[hidden]` reset (`display: none` when hidden), padding for active panel.
  - `.editor-header` — entity-name + description block (lifted from studio.css; LOC moves out of studio.css). Uses F4 typography tokens; flex layout for left-side name/description + right-side action cluster.
  - `.form-actions` — right-aligned button cluster (used by editor's `[← Back] [Delete] [Save]` and reusable for future modal `.modal-actions` composition).
  - `.advanced-collapsible` (or similar) — disclosure widget for the General tab's Advanced stub (consider using native `<details>`/`<summary>` for accessibility — see Edge Cases).
  - `.test-result` — generic span for test-button results, with `.test-result-ok` and `.test-result-fail` modifiers (styled like admin's `.admin-pf-test-ok` / `.admin-pf-test-fail` but generic so admin can adopt in F6).
- `the_one/interfaces/web/static/css/studio.css`:
  - REMOVE `.editor-header` rule at line 22 (lifted to components.css).
  - REMOVE rules for `.editor-form`, `.editor-section`, `.editor-actions`, `.save-btn`, `.delete-btn` if they become structurally obsolete OR keep area-scoped overrides if needed (developer judgment during impl). The action cluster uses canonical `.form-actions` from components.css.
  - Add `.studio-tablist-host` (or similar) for any studio-specific tablist layout (e.g., gap or alignment that differs from canonical). If no studio-specific layout is needed, no rules added.
  - Net delta: ~-15 to -25 LOC; target studio.css ≤ 60 LOC at leg 03 close (per the flight spec's design-system contribution discipline).
- `the_one/interfaces/web/static/css/admin.css` — UNCHANGED in this leg (admin's `.admin-pf-test-*` styles stay; admin migrates to canonical `.test-result` in F6).
- `the_one/interfaces/web/static/js/icons.js` — adds `arrow-left` and `play` icons.
- `the_one/interfaces/web/static/index.html` — adds 4 new `<script>` lines: `tabs.js` (after `confirm.js`), `agent-editor.js`, `general-tab.js`, `knowledge-tab.js`, `tools-tab.js` (the last 4 inserted in the studio sub-module block, before `studio.js`). Reorder studio sub-modules so tabs.js loads before agent-editor.js.
- `the_one/agents.md` — adds three entries to §Design system → "Affordance vocabulary":
  - "Tab idiom" — `.tablist` + `.tab` + `.tabpanel` + the manual-activation keyboard contract + `App.tabs(...)` API.
  - "Editor header" — `.editor-header` canonical primitive (entity-name + description block above tablist).
  - "Form actions" — `.form-actions` right-aligned button cluster.
  - And updates to "Section navigation" entry to clarify the section-nav-vs-tablist distinction (sections are persistent destinations, tabs are within-entity views).
- `tests/browser/test_flow_agent_tabs.py` — NEW. Covers tab idiom: manual-activation keyboard (Arrow Left/Right move focus only — assert URL unchanged after arrow press), Enter/Space commits (URL updates + `aria-selected` toggles + roving `tabindex`), Home/End jumps, click navigation, hash-encoded tab survives refresh, ARIA attributes correct (`role="tablist"`, `role="tab"`, `aria-controls`, `aria-selected`).
- `tests/browser/test_flow_agent_crud.py` — minor adaptations: tests that interact with form fields run as-is if the General tab is the default tab on agent select (see Edge Cases). Add new tests for: Tools tab built-in checkboxes (the existing test exercises the form section but not via tab navigation — verify the tab contains the expected checkboxes), Test button success/failure paths, Advanced section visible-but-disabled.
- `tests/browser/test_flow_hash_routing.py` line 114 (or wherever the assertion is) — UPDATED: assertion changes from `#studio/agents/{name}` to `#studio/agents/{name}/general` (the default-tab replaceState upgrade). Single-line change.
- All F1-F4 + leg-01 + leg-02 tests still pass. Browser baseline: 143 → ≥ 155 after this leg (target: +12 new tests for tab idiom + tab content + Test button + Advanced stub).

## Acceptance Criteria

- [x] **Tab idiom shipped as canonical**: `.tablist`, `.tab`, `.tabpanel` rules in `components.css`. The agent editor uses `<div role="tablist">` containing three `<button role="tab">` elements + three `<div role="tabpanel">` panels. ARIA attributes correct: `aria-selected="true|false"` on tabs, `aria-controls="<panel-id>"` on tabs, `id` on panels, `tabindex="0"` only on the active tab (others have `tabindex="-1"` — roving `tabindex`).
- [x] **`App.tabs(tablistEl, panelsEl, {onChange, initial})` helper** in `static/js/tabs.js`. Returns `{activate(tabId), getActive()}`. **Manual activation**: Arrow Left/Right move focus + visual highlight only (NO URL mutation, NO panel content swap); Home/End jump first/last; Enter or Space commits the focused tab (calls `onChange(tabId)`, swaps panel visibility via `[hidden]` attribute, updates `aria-selected` and roving `tabindex`); Tab moves out of the tablist into the active panel's contents.
- [x] **Hash-encoded active tab**: `serializeState()` returns `'agents/' + encodeURIComponent(name) + '/' + tab` when an agent is selected (where `tab` defaults to `'general'`). `hydrateState(sub)` parses `agents/{name}/{tab}`; defaults `tab` to `'general'` if absent. Refreshing on `#studio/agents/{name}/general` (or `/knowledge` or `/tools`) returns the user to the exact same view.
- [x] **`#studio/agents/{name}` redirects to `#studio/agents/{name}/general`** via the F3 router's existing replaceState path (no new redirect logic in studio.js — `serializeState()` returns the longer form). Verified in browser test.
- [x] **Editor structure**: `<div class="studio-editor">` contains:
  - `<div class="editor-header">` with: entity name (`<h1>`), description (`<p>` or `<span>`); plus `<div class="form-actions">` aligned right containing `[← Back]`, `[Delete]`, `[Save]` buttons.
  - `<div role="tablist" class="tablist" aria-label="Agent settings">` with three `<button role="tab">` elements: General, Knowledge, Tools.
  - Three `<div role="tabpanel" class="tabpanel">` panels (one visible at a time per `[hidden]` attribute control).
- [x] **Action cluster wiring** (this leg's scope):
  - `[← Back]` button (NEW; canonical `.btn-outlined-cyan`, with `arrow-left` icon): on click, sets `_selectedAgent = null` + clears editor + writes URL → `#studio/agents`. No dirty-state confirm in this leg (leg 04 adds it).
  - `[Delete]` button (`data-testid="delete-agent-btn"`, retains `.delete-btn` class composed with whatever canonical button class fits — likely `.btn-muted-destructive`): **keeps its existing inline two-step flow at `studio.js:660-683` exactly as-is**. The class-state machinery (`.delete-btn.confirm`), the capital-D label "Confirm Delete?", the 3s revert timer, and the second-click `DELETE /api/agents/{name}` handler all travel with the button when it moves into the new `.form-actions` cluster. Leg 03 does NOT migrate this button to `App.confirmDelete`. `test_flow_agent_crud.py:73` (which asserts the button's text becomes "Confirm Delete?") continues passing because the inline flow is preserved verbatim.
  - `[Save]` button (`data-testid="save-agent-btn"`, `.btn-filled-cyan`): wired to existing save handler (POST/PUT). **No dirty-state gating in this leg** — Save is always enabled when an agent is selected. Leg 04 adds the disabled-when-clean behavior.
- [x] **General tab content**:
  - Identity fields: name (create-mode only — disabled or read-only after creation), description (always editable). Both use F4 `.field-row` + `.field-input`/`.field-textarea`. `data-field="name"`, `data-field="description"` preserved.
  - System prompt: `.field-textarea` with `data-field="system_prompt"` preserved.
  - LLM config: provider select (`.field-select` with `data-field="provider_config_id"`, id `studio-provider`), model select (`.field-select` with `data-field="llm_model"`, id `studio-model`), VRAM warning placeholder (`.studio-vram-warning`) — all preserved with their existing IDs and selectors so VRAM warning logic at studio.js:936-1034 continues to work.
  - `max_iterations` numeric input (`.field-input` with `data-field="max_iterations"`, type=number) — STAYS in the main General tab body, NOT in the Advanced stub (per the flight spec's resolved Open Question — `max_iterations` is real `AgentConfig` storage; rendering it disabled inside an "Advanced — coming soon" stub would lie about the persistence model).
  - **Advanced section**: a `<details class="advanced-collapsible">` (or equivalent disclosure widget) below the form with `<summary>Advanced</summary>` and three disabled inputs labeled "Temperature", "Top P", "Max tokens" + a caption "Coming soon — provider-bound config in a future flight." All three inputs have `disabled` attribute and `aria-disabled="true"`. Optional: native `<details>`/`<summary>` for accessibility (collapses without JS).
  - **Test button**: `<button class="btn-outlined-cyan" data-testid="test-provider-btn" type="button">[play icon] Test</button>`. Disabled state reads the LIVE provider-select form value (NOT the persisted `agent.provider_config_id`) — the button is enabled iff `#studio-provider` has a non-empty value. Recompute disabled state on the provider-select `change` event (so the user can pick a provider for an unsaved/new agent and immediately test it). Mirrors admin's edit-mode test behavior. Click → `POST /api/providers/{provider_config_id}/test` (empty body); response renders into adjacent `<span class="test-result" aria-live="polite">` as `<span class="test-result test-result-ok">✓ {detail}</span>` on success or `<span class="test-result test-result-fail">✗ {detail}</span>` on failure. On network error, render the error message similarly with the fail modifier. Surface a flash via the existing `App.showFlash(editorEl, msg)` helper (defined at `studio.js:934`, used at `:893, :922`) — success message + non-error variant for ok, error variant for fail. Mirrors admin's `.admin-pf-test-ok`/`.admin-pf-test-fail` pattern but uses canonical `.test-result*` classes (not area-specific). Hover/title tooltip: "Tests provider connectivity. Does not validate the agent's full config."
- [x] **Knowledge tab content**: centered `.empty-state` containing the exact two-sentence text: "Knowledge bases will be attached to this agent here in a future flight. Knowledge bases can be attached to multiple agents." Rendered via `App.studio.renderKnowledgeTab(panel)`.
- [x] **Tools tab content**:
  - Subsection 1: `<h3 class="section-title">MCP tools</h3>` + `.empty-state` "MCP servers will be configured in the Tools section, then attached here. Tools can be attached to multiple agents."
  - Subsection 2: `<h3 class="section-title">Built-in tools</h3>` + the existing 4-category tool checkbox UI (TOOL_CATEGORIES → tool-group + tool-row + tool-toggle). The checkbox state is bound to `enabled_tools`/`disabled_tools` via `data-field` selectors — `collectFormData()` continues to read from these selectors regardless of DOM nesting. Select-all/select-none affordances preserved if present today.
- [x] **Manual-activation keyboard verified**: pressing Arrow Left or Arrow Right on a focused tab moves focus + visual highlight ONLY (URL stays the same; panel content unchanged). Pressing Enter or Space on the focused tab commits — URL updates to include the tab segment, the panel becomes visible (other panels hidden), `aria-selected` and roving `tabindex` update. Browser test asserts this explicitly (focus + URL check after arrow press, then again after Enter).
- [x] **Roving `tabindex` correctness verified**: after Arrow Right from the active tab, `document.activeElement === tabs[next]` even though `tabs[next].getAttribute('tabindex') === '-1'` (browsers honor programmatic `.focus()` on `tabindex="-1"` elements; only the natural Tab order excludes them). After Enter activation, `tabs[next].getAttribute('tabindex') === '0'` and the previously-active tab has `tabindex="-1"`. New browser test asserts this pair of conditions.
- [x] **`tests/browser/test_flow_hash_routing.py:114`** assertion updated from `#studio/agents/{name}` to `#studio/agents/{name}/general` (the default-tab replaceState upgrade). Single-line change.
- [x] **Existing `test_flow_agent_crud.py` tests pass** with at most minor additions: form-field interactions still work because the General tab is the default on agent select (its content is mounted and visible immediately). If any test fails because of timing or ARIA interaction, root-cause; the tab activation should NOT introduce new races.
- [x] **Existing F1-F4 + leg-01 + leg-02 tests pass**: `pytest --timeout=60 tests/` returns exactly 407, `pytest --timeout=120 -m browser tests/browser/` returns ≥ 155 (143 baseline + 12 new for this leg, target).
- [x] **New browser tests** in `tests/browser/test_flow_agent_tabs.py`:
  - Tablist renders with three tabs; ARIA attributes correct.
  - Default tab on agent select is General (URL upgrades to `#studio/agents/{name}/general`).
  - Arrow Left/Right moves focus + highlight only; URL unchanged after arrow press.
  - Enter (or Space) on a focused tab commits: URL updates, `aria-selected` toggles, roving `tabindex` updates, panel visibility swaps.
  - Home/End jump to first/last tab (focus only).
  - Click on a tab commits (same as Enter).
  - Refresh on `#studio/agents/{name}/knowledge` returns the user to the Knowledge tab.
  - Refresh on `#studio/agents/{name}/tools` returns the user to the Tools tab.
  - Tools tab renders the built-in tool checkboxes; checkboxes are interactive.
  - Knowledge tab renders the empty-state text.
  - Advanced section: visible, disabled inputs, "Coming soon" caption present.
  - Test button: disabled when `provider_config_id` unset; click triggers fetch; success path renders `.test-result-ok`; failure path renders `.test-result-fail` (mock the endpoint or use a known-failure provider).
- [x] **VRAM warning continues to work** in the General tab — selecting an Ollama model with insufficient VRAM still shows the warning. Manual check or extend an existing browser test.
- [x] **`agents.md` documentation updated** — 4 NEW entries plus 1 UPDATED entry under §Design system → "Affordance vocabulary":
  - NEW: "Tab idiom" — `.tablist`, `.tab`, `.tabpanel`, manual-activation keyboard contract, `App.tabs(...)` API surface.
  - NEW: "Editor header" — `.editor-header` (entity-name + description block above tablist).
  - NEW: "Form actions" — `.form-actions` (right-aligned button cluster; reusable for modal `.modal-actions` composition in leg 04).
  - NEW: "Test result" — `.test-result` + `.test-result-ok` + `.test-result-fail` (canonical for connectivity-test success/failure indicators; admin's area-specific `.admin-pf-test-*` migrates in F6).
  - UPDATED: "Section navigation" entry from leg 01 — clarify the section-nav-vs-tablist distinction (sections are persistent destinations with their own URL space; tabs are within-entity views under the agent editor).
- [x] **Class composition discipline preserved**: tile button (leg 02) stays as-is; tab buttons are NEW canonical `.tab`. Two distinct primitives — tile = grid cell affordance, tab = within-entity view selector. Documented in agents.md.
- [x] **Single `App.router.replaceSub` call site preserved** in studio.js — `grep -n 'App.router.replaceSub' studio.js` still returns 1 match (in `writeUrl_`).
- [x] Flight log updated with `### 03-tabbed-editor` progress entry.
- [x] This leg's status set to `landed`.

## Verification Steps

- `pytest --timeout=60 tests/` — passes baseline (exactly 407).
- `pytest --timeout=120 -m browser tests/browser/` — passes ≥ 155.
- `pytest --timeout=120 -m browser tests/browser/test_flow_agent_tabs.py` — new file, passes.
- `pytest --timeout=120 -m browser tests/browser/test_flow_agent_crud.py` — passes (form fields accessible via the default General tab).
- `pytest --timeout=120 -m browser tests/browser/test_flow_hash_routing.py` — passes including the updated `:114` assertion.
- `pytest --timeout=120 -m browser tests/browser/test_flow_studio_navigation.py` — passes unchanged (leg 01's section-nav tests).
- Manual browser check: open `#studio/agents/{some-agent}` → URL upgrades to `.../general`; click General/Knowledge/Tools tabs (mouse) → URL updates; Tab into tablist → arrow keys move focus only; Enter commits; refresh on each tab URL returns to that tab; Test button calls endpoint and renders result.
- `wc -l the_one/interfaces/web/static/js/areas/studio.js` — ≤ 1000 (~970-1000 expected; the form rendering moves to per-tab modules but new orchestration plumbing offsets some of the savings).
- `wc -l the_one/interfaces/web/static/css/components.css` — grows by ~80-120 LOC.
- `wc -l the_one/interfaces/web/static/css/studio.css` — ≤ 60 LOC (per design-system contribution discipline).
- `grep -n 'App.router.replaceSub' the_one/interfaces/web/static/js/areas/studio.js` — exactly 1 match.

## Implementation Guidance

1. **Add icons** — open `the_one/interfaces/web/static/js/icons.js` and register `arrow-left` (Lucide ArrowLeft path data) and `play` (Lucide Play path data). Both are required for the Back button and Test button respectively. Verify by grepping for the new keys in the registry.

2. **Create `the_one/interfaces/web/static/js/tabs.js`** with the `App.tabs` helper.
   - Module pattern: `(function (window) { ... window.App = window.App || {}; window.App.tabs = function (tablistEl, panelsEl, opts) { ... }; })(window);`
   - Implementation outline:
     ```
     opts = opts || {};
     var onChange = opts.onChange || function () {};
     var initial = opts.initial;
     var tabs = Array.prototype.slice.call(tablistEl.querySelectorAll('[role="tab"]'));
     var panels = Array.prototype.slice.call(panelsEl.querySelectorAll('[role="tabpanel"]'));
     var activeId = null;

     function activate(tabId) {
       activeId = tabId;
       tabs.forEach(function (t) {
         var match = t.getAttribute('aria-controls') === tabId || t.dataset.tabId === tabId;
         t.setAttribute('aria-selected', match ? 'true' : 'false');
         t.setAttribute('tabindex', match ? '0' : '-1');
       });
       panels.forEach(function (p) {
         var match = p.id === tabId || p.dataset.tabId === tabId;
         if (match) p.removeAttribute('hidden'); else p.setAttribute('hidden', '');
       });
       onChange(tabId);
     }

     function getActive() { return activeId; }

     function focusedIndex() {
       for (var i = 0; i < tabs.length; i++) if (tabs[i] === document.activeElement) return i;
       return -1;
     }

     tablistEl.addEventListener('keydown', function (e) {
       var idx = focusedIndex();
       if (idx === -1) return;
       var next = idx;
       if (e.key === 'ArrowLeft') next = (idx - 1 + tabs.length) % tabs.length;
       else if (e.key === 'ArrowRight') next = (idx + 1) % tabs.length;
       else if (e.key === 'Home') next = 0;
       else if (e.key === 'End') next = tabs.length - 1;
       else if (e.key === 'Enter' || e.key === ' ') {
         e.preventDefault();
         var tabId = tabs[idx].getAttribute('aria-controls') || tabs[idx].dataset.tabId;
         activate(tabId);
         return;
       }
       else return;
       e.preventDefault();
       tabs[next].focus();
       // No tabindex update on arrow nav — roving tabindex updates only on activation.
     });

     tabs.forEach(function (t) {
       t.addEventListener('click', function () {
         var tabId = t.getAttribute('aria-controls') || t.dataset.tabId;
         activate(tabId);
       });
     });

     if (initial) activate(initial);

     return { activate: activate, getActive: getActive };
     ```
   - **Key correctness**: arrow-key navigation moves DOM focus (`tabs[next].focus()`) but does NOT update `tabindex` until activation — that's the roving-tabindex contract. The non-active tabs still have `tabindex="-1"` after focus moves to them via arrow keys; this is correct (the user has explicit focus, so they can interact regardless of tabindex value).
   - **Accessibility note**: when arrow keys move focus to a tab with `tabindex="-1"`, the browser respects programmatic `.focus()` calls — `tabindex="-1"` only excludes from the natural Tab order. After Enter activation, `tabindex` updates to `"0"` for the now-active tab.

3. **Add `tabs.js` to index.html** between `confirm.js` (line 29) and the chat sub-modules block. Single line.

4. **Create `agent-editor.js`** in `the_one/interfaces/web/static/js/areas/studio/`:
   - Exports `App.studio.renderAgentEditor(container, agent, providers, callbacks)`.
   - `callbacks` shape: `{onBack, onDelete, onSave, onTabChange, onTestProvider, onModelChange, ...}` — pass these from studio.js.
   - Builds the DOM: `.editor-header` (h1 name, p description, `.form-actions` action cluster) → `.tablist` (3 tabs) → 3 `.tabpanel` divs (initially `hidden`).
   - For each tab, calls the per-tab render helper to populate the panel.
   - Wires `App.tabs(tablistEl, panelsContainerEl, {onChange: callbacks.onTabChange, initial: callbacks.initialTab || 'general'})`.
   - Returns the tab handle `{activate, getActive}` so studio.js can imperatively call `tabHandle.activate('general')` after a hydrate.
   - Focus management: when an agent is selected for the first time, focus moves to the first tab (or the agent name if create mode).

5. **Create `general-tab.js`**:
   - Exports `App.studio.renderGeneralTab(panel, agent, providers, callbacks)`.
   - Builds the form fields preserving every existing `data-field`, `id`, and selector used by `collectFormData()` and the VRAM warning (e.g., `#studio-provider`, `#studio-model`, `.studio-vram-warning`).
   - Adds the Advanced collapsible (`<details>`/`<summary>` is the recommended a11y default — see Edge Cases) and Test button + result span.
   - Test button click handler: `callbacks.onTestProvider()` — actual fetch logic stays in studio.js (centralizes side-effects + flash messaging).

6. **Create `knowledge-tab.js`** — minimal:
   ```
   App.studio.renderKnowledgeTab = function (panel) {
     panel.innerHTML = '';
     var div = document.createElement('div');
     div.className = 'empty-state';
     div.textContent = 'Knowledge bases will be attached to this agent here in a future flight. Knowledge bases can be attached to multiple agents.';
     panel.appendChild(div);
   };
   ```
   - Note: avoid `innerHTML` for the body text if any user-controlled content could ever leak in; here it's a static literal so safe. Use `textContent` for the literal.

7. **Create `tools-tab.js`**:
   - Exports `App.studio.renderToolsTab(panel, agent, callbacks)`.
   - Two `.section-title` headers + content blocks. The Built-in tools subsection lifts the existing `TOOL_CATEGORIES` rendering from studio.js:505-524 verbatim (move the constant or pass it in as a callback dependency).

8. **Refactor studio.js**:
   - Move `TOOL_CATEGORIES` to a shared location (top of studio.js or a new `static/js/areas/studio/tool-categories.js` constants file). The simpler choice: keep it in studio.js and pass to `renderToolsTab` via callbacks.
   - Rewrite `renderEditor(agent)` to delegate to `App.studio.renderAgentEditor(...)`. Pass callbacks for back/delete/save/tabChange/testProvider. Wire VRAM warning logic via a model-change callback (callbacks.onModelChange dispatches to existing `checkVramForModel`).
   - Add `this._activeTab` field (initialize to `'general'`).
   - Extend `serializeState()` — this is a **one-line edit** to the existing `'agents/<name>'` branch at `studio.js:31` (NOT a rewrite). The existing line returns `'agents/' + encodeURIComponent(this._selectedAgent.name)`; append `+ '/' + (this._activeTab || 'general')`:
     ```
     if (this._activeSection === 'agents' && this._selectedAgent && !this._createMode) {
       var name = encodeURIComponent(this._selectedAgent.name);
       var tab = this._activeTab || 'general';
       return 'agents/' + name + '/' + tab;
     }
     // ... existing branches for create-mode, knowledge, tools, etc. — unchanged
     ```
   - Extend `hydrateState(sub)`:
     ```
     if (sub && sub.indexOf('agents/') === 0) {
       this._activeSection = 'agents';
       var rest = sub.slice('agents/'.length);
       var slashIdx = rest.indexOf('/');
       if (slashIdx === -1) {
         // 'agents/{name}' (no tab segment) — F3 router will rewrite URL after hydrate.
         this._pendingSelectName = decodeURIComponent(rest);
         this._activeTab = 'general';
       } else if (slashIdx === rest.length - 1) {
         // 'agents/{name}/' (trailing slash, empty tab) — defensive: treat as no-tab case.
         this._pendingSelectName = decodeURIComponent(rest.slice(0, slashIdx));
         this._activeTab = 'general';
       } else {
         this._pendingSelectName = decodeURIComponent(rest.slice(0, slashIdx));
         var tab = rest.slice(slashIdx + 1);
         if (tab === 'general' || tab === 'knowledge' || tab === 'tools') {
           this._activeTab = tab;
         } else {
           // Unknown tab string ('agents/{name}/foobar') — default to 'general'.
           this._activeTab = 'general';
         }
       }
       this._tryConsumePendingSelect();
     }
     ```
   - **Encoding note**: agent names with literal `/` are encoded as `%2F` by `encodeURIComponent`, so `rest.indexOf('/')` correctly finds the segment separator (the only naked `/` in `rest`). No URL-decoding ambiguity.
   - Add `setActiveTab(tab, {writeUrl=true})` — analogous to `setActiveSection`. Calls the tab handle's `activate(tab)`, sets `this._activeTab`, optionally writes URL via `_writeUrl()`.
   - In `selectAgent(agent)`, after rendering the editor, ensure the tab handle activates the current `this._activeTab` (which may have been set during hydrate).
   - In `onTabChange(tabId)` callback (passed to `renderAgentEditor`), call `setActiveTab(tabId)` (default `writeUrl: true`).

9. **Test button wiring** — in studio.js, define `onTestProvider()` that:
   - Reads the current provider id directly from the live `#studio-provider` select value (NOT from the persisted agent — supports unsaved changes during create or edit).
   - If unset, no-op (button is disabled at render time + on provider-select `change` event).
   - POST to `/api/providers/{id}/test` with empty body.
   - On 200, parse JSON, render result into the test-result span as `.test-result-ok` or `.test-result-fail` based on `result.status`. Call `App.showFlash(editorEl, result.detail)` for ok or `App.showFlash(editorEl, result.detail, true)` for fail (the second argument is the error flag, mirroring `studio.js:893, :922`).
   - On network error (rejected promise), render the error message in `.test-result-fail` and call `App.showFlash(editorEl, err.message, true)`.
   - **Recompute disabled state on provider-select `change`**: an existing `change` listener on `#studio-provider` already lives at `studio.js:629-634` (clears VRAM warning + fetches models). Prefer chaining the Test-disabled-recompute into that existing handler (locality) rather than adding a second listener; both are correct, but a single handler keeps provider-change side-effects in one place.
   - **Note on flash for the error path**: `App.showFlash` (`app.js:220`) takes `(container, msg, isError)`. The local wrapper at `studio.js:934` is one-arg (`showFlash(msg)`) and drops the error flag, so for the failure case bypass the wrapper and call `App.showFlash(editorEl, err.detail || err.message, true)` directly to preserve the error styling.

10. **CSS additions in `components.css`**:
    - `.tablist` — `display: flex; gap: <token>; border-bottom: 1px solid <token>;`.
    - `.tab` — button reset, `padding: <token>`, `:focus-visible` ring, `[aria-selected="true"]` accent + bottom-border highlight.
    - `.tabpanel` — `[hidden] { display: none; }`; padding for active panel.
    - `.editor-header` — flex layout with name/description on left, `.form-actions` on right; padding; bottom-border separator. Lift the existing `.area-studio .editor-header` rule from studio.css and generalize.
    - `.form-actions` — `display: flex; gap: <token>; justify-content: flex-end;`.
    - `.advanced-collapsible` — minimal disclosure styles for `<details>`/`<summary>`. Or skip if `<details>` defaults are acceptable.
    - `.test-result` — `display: inline-block; margin-left: <token>;` with modifiers `.test-result-ok` (green/check) and `.test-result-fail` (red/cross) using F4 status tokens.

11. **CSS removals in `studio.css`**:
    - Remove `.area-studio .editor-header` (lifted).
    - Decide on `.editor-form`, `.editor-section`, `.editor-actions`, `.save-btn`, `.delete-btn` rules: keep area-scoped overrides only if they're genuinely studio-specific; otherwise remove. The new `.form-actions` replaces `.editor-actions`. Save/Delete buttons use canonical button classes from F4 (`.btn-filled-cyan` etc.), so `.save-btn`/`.delete-btn` likely become obsolete.
    - Result target: studio.css ≤ 60 LOC.

12. **Update `tests/browser/test_flow_hash_routing.py:114`** — change the expected hash from `#studio/agents/{name}` to `#studio/agents/{name}/general`. Single-line.

13. **Write `tests/browser/test_flow_agent_tabs.py`** — 12 tests covering the AC list. Follow the existing test pattern from `test_flow_studio_navigation.py`.

14. **Update `agents.md`** — add the four new entries to §Design system → "Affordance vocabulary".

15. **Run tests**: `pytest --timeout=60 tests/` (407 expected) and `pytest --timeout=120 -m browser tests/browser/` (≥ 155 expected). If any existing test fails, root-cause — the design intent is that form-field tests pass without modification because the General tab is the default tab and its content is mounted on agent select.

16. **Update flight log** — `### 03-tabbed-editor` progress entry with timestamps + Changes Made + Notes.

17. **Set leg status to `landed`**. Do NOT commit. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`<details>`/`<summary>` for the Advanced section**: native HTML disclosure is the simplest a11y-correct disclosure widget. It's keyboard-operable (Tab + Enter to toggle), screen-reader-announced ("collapsed"/"expanded"), and zero-JS. Recommended over a custom button + ARIA. If the design tokens conflict with native styles, override with CSS minimally (e.g., remove the default arrow, replace with `chevron-down` icon + transform). Document the choice in `agents.md`.
- **General tab is the default → existing form-field tests pass without modification**: ensure that `App.studio.renderAgentEditor` activates the General tab synchronously during render (before the test's first form-field interaction). The `App.tabs(...).activate(initial)` call must complete before the function returns.
- **`hydrateState` race with editor render**: if hydrate runs before agents fetch completes, `_pendingSelectName` is set; when agents arrive, `_tryConsumePendingSelect` calls `selectAgent`, which calls `renderEditor`, which activates `_activeTab`. The tab is correctly set before the user interacts. Verify no stale-tab race.
- **Tab URL write loop**: `setActiveTab` writes URL via `_writeUrl()`; the F3 router calls `serializeState` after `hydrateState` and writes URL only if different. The single-call-path discipline from leg 01 avoids loops. Verify with leg-01's same idempotency check.
- **Create mode**: `_createMode === true` keeps `serializeState()` returning `'agents'` (no agent selected, no tab segment). The editor renders with empty fields; the General tab is active by default; no URL upgrade to `.../general` (because there's no agent name to put before it). When the user saves a new agent, `selectAgent(newAgent)` fires → URL upgrades to `.../general` via the standard path.
- **Delete from editor**: when the editor's Delete button confirms, the agent is gone. `selectAgent` is set to null; URL writes to `'agents'` (no tab segment); the editor empties. Verify no broken state.
- **Tab switch during loading**: if the user switches to Tools tab while VRAM polling is in flight, the VRAM warning placeholder (in the General tab) is hidden via `[hidden]` on the panel. The polling completes and writes to the placeholder, but the panel is hidden — no visible artifact. When the user switches back to General, the latest VRAM state is visible. Verify no stale state when switching back-and-forth.
- **`enabled_tools`/`disabled_tools` semantics**: the existing logic in `collectFormData()` reads checkbox state and computes the enabled-or-disabled-list-only payload. Moving the checkboxes into the Tools tab does NOT change this — `collectFormData()` queries by selector regardless of nesting.
- **Test button when no agent selected**: not applicable — Test button is in the General tab, only rendered when an agent is selected (or in create mode with a chosen provider).
- **Test button without `provider_config_id`**: button is `disabled` (not `aria-disabled` only — actually disabled). Click should not fire. Verify in browser test.
- **Deep-link to invalid tab**: `#studio/agents/{name}/foobar` → `hydrateState` defensively defaults to `'general'`. URL gets rewritten to `.../general` via the F3 serialize-after-hydrate path. No broken state.
- **`.editor-header` lift**: the existing `.area-studio .editor-header` rule is being generalized. Verify no other area uses `.editor-header` today (admin doesn't — it uses different selectors). The lift is safe.
- **Roving `tabindex` after activation**: when activation moves to a different tab, the previously-active tab's `tabindex` becomes `"-1"`. If the user had focused that tab (rare; activation usually goes through it), focus might be lost. Browsers handle this gracefully (focus stays on the element until something else takes it), but verify in a test that arrow-key navigation after activation still works.
- **`aria-controls` matching**: the `<button role="tab" aria-controls="<panel-id>">` must reference an existing panel `id`. Use deterministic IDs like `agent-tab-panel-general`, `agent-tab-panel-knowledge`, `agent-tab-panel-tools`. Avoid name-derived IDs (multiple agents would collide).

## Files Affected

- `the_one/interfaces/web/static/js/tabs.js` — NEW (~70-100 LOC).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — NEW (~150-200 LOC).
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` — NEW (~120-180 LOC).
- `the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js` — NEW (~15-25 LOC).
- `the_one/interfaces/web/static/js/areas/studio/tools-tab.js` — NEW (~80-120 LOC).
- `the_one/interfaces/web/static/js/areas/studio.js` — MAJOR refactor: `renderEditor` delegates to `renderAgentEditor`; `serializeState`/`hydrateState` extended; new `_activeTab` field; new `setActiveTab` helper; `onTestProvider` handler. Net: ~-100 to -150 LOC; new total ~950-1000.
- `the_one/interfaces/web/static/js/icons.js` — `+arrow-left`, `+play` icons.
- `the_one/interfaces/web/static/css/components.css` — `+~80-120 LOC` (`.tablist`, `.tab`, `.tabpanel`, `.editor-header`, `.form-actions`, `.test-result*`, optional `.advanced-collapsible`).
- `the_one/interfaces/web/static/css/studio.css` — `-~15-25 LOC` (lift `.editor-header`; remove obsolete `.editor-form`/`.editor-section`/`.editor-actions`/`.save-btn`/`.delete-btn` rules where they're no longer needed). Target: ≤ 60 LOC.
- `the_one/interfaces/web/static/index.html` — `+5 lines` (`tabs.js`, `agent-editor.js`, `general-tab.js`, `knowledge-tab.js`, `tools-tab.js`).
- `tests/browser/test_flow_agent_tabs.py` — NEW (~250-350 LOC, 12 tests).
- `tests/browser/test_flow_hash_routing.py` — line 114 single-line update.
- `tests/browser/test_flow_agent_crud.py` — possibly add 2-3 new tests for Tools tab + Advanced + Test button (or fold into the new agent-tabs test file).
- `the_one/agents.md` — `+~30 LOC` (4 new entries: Tab idiom, Editor header, Form actions, Test result).
- `missions/04-ui-maturity/flights/05-studio-alignment/flight-log.md` — leg progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Flight Director defers commit to flight-end review.**

- [x] All acceptance criteria verified
- [x] All existing tests passing (`pytest --timeout=60 tests/` = 407, `pytest --timeout=120 -m browser tests/browser/` ≥ 155)
- [x] New tests passing (`test_flow_agent_tabs.py` + extensions)
- [x] `test_flow_hash_routing.py:114` updated
- [x] `test_flow_agent_crud.py` passes (form-field tests work because General tab is default)
- [x] VRAM warning still works in General tab (Ollama models w/ insufficient VRAM trigger warning)
- [x] `agents.md` updated with 4 new entries (Tab idiom, Editor header, Form actions, Test result)
- [x] Flight log updated with `### 03-tabbed-editor` progress entry
- [x] This leg's status set to `landed`
- [x] Do NOT check off this leg in flight.md yet (Flight Director handles at flight commit)
- [x] Do NOT commit (Flight Director commits all autonomous legs at flight-end review)
- [x] Signal `[HANDOFF:review-needed]`
