# Leg: 03-agent-editor-mcps-tab

**Status**: completed
**Flight**: [Studio MCPs tab + inspector polish](../flight.md)

## Objective

Replace `mcps-tab.js`'s 22-line stub with a fully-functional per-agent MCP attach + override + per-tool toggle UI. Multi-attach chip-list sourced from `/api/mcp-sources`; per-attachment editor with per-tool checkbox group (reads tools via L1's `/test/connect`) and credential-override fields (uses `App.adminFormHelpers` for the form substrate). Hash routing for `#studio/agents/{name}/mcps/{source-id}`. Browser tests folded in. App.areas array-shape lock-test added.

## Context

- **L1 + L2 are already landed.** L1 added `/api/mcp-sources/{id}/test/connect`'s `capabilities` field plus `enabled_tools`/`disabled_tools` reserved keys in `StdioMCPOverride` / `StreamableHttpMCPOverride`. L2 polished the source-edit Tools section. L3's per-attachment editor reuses L1's override schemas and L2's `page.route()` mocking pattern.
- **Stub site**: `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` is currently a 22-line empty-state stub. Its single export `App.studio.renderMcpsTab(panel)` is called from `agent-editor.js:150` with just the panel argument. L3 extends both: the stub becomes a full UI module; the `agent-editor.js` call site adds the agent + mcp-source data + callbacks needed.
- **Tool-discovery via `fetchMcpSourceTools` factory (Design Decision §2)**: mirror the existing `studio.js::fetchToolSchema` closure-promise cache pattern at lines 595-609. POST `/api/mcp-sources/{id}/test/connect`; on `{status: "ok"}` resolve with `tools[]` and (post-L1) `capabilities`; on `{status: "auth_required"}` reject with a typed error rendered as inline notice "This source needs Test/auth on the source-edit page first" with a link to `#studio/mcp-sources/{source-id}` — **NEVER auto-trigger the OAuth popup** (that's the source-edit page's affordance); on `{status: "error"}` reject and drop the cache entry so retry works.
- **Per-tool storage shape (locked at Design Decision §1)**: `AgentConfig.mcp_overrides[source_name]` extends with reserved sub-keys `enabled_tools` / `disabled_tools` (un-prefixed server-side tool names). The UI shows the prefixed display name (`mcp__src__foo`) for operator clarity, but stores the un-prefixed value (`foo`) in the override. L1 already extended `StdioMCPOverride` and `StreamableHttpMCPOverride` with these fields; L3 just needs to send them in the save payload.
- **URL → key translation (Design Decision §3)**: hash routing carries `source-id` (uuid, stable across renames). The editor resolves `source-id → source.name` via the chip-list's already-fetched source list at editor-mount time (NOT on every save). `mcp_overrides` is keyed by `source.name`.
- **Override resolver dispatch via `App.adminFormHelpers`**: the L1 override schemas (`StdioMCPOverride.env: dict`, `StreamableHttpMCPOverride.bearer_token: str`, `headers: dict`) use `Annotated[..., Substitute]`. The form substrate already in `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` knows how to render Substitute fields with `__MASKED__` sentinel preservation. L3's per-attachment override panel reuses `helpers.renderField(name, prop, value, {mode: 'agent', operatorValue: ..., attrPrefix: 'data-mcp-override-field', toolName: source.name})`.
- **Save flow (Design Decision §1 + collectFormData extension)**: `studio.js::collectFormData` already collects `mcp_source_ids` from `.chip-area[data-type="mcp"] .chip` elements (lines 1216-1220). L3 adds the `mcp_overrides` walk: querySelectorAll `[data-mcp-override-source][data-mcp-override-field]`, group by source-name, build `{source_name: {field: value}}` dict. Mirror the existing `tool_overrides` walk pattern at lines 1224-1248.
- **Hash routing (Design Decision §3)**: existing `App.router.replaceSub(sub)` at `app.js:287-292` updates the URL fragment without firing `hashchange`. The MCPs tab uses sub-state shape `agents/{name}/mcps/{source-id}` — extends the existing `agents/{name}/{tab}` pattern. The router exposes `parseHash`, `replaceSub`, and emits `hashchange` events on browser-driven navigation; L3's tab listens for `hashchange` to handle deep links.
- **App.areas array-shape lock-test (Design Decision §4)**: F6.6 L0 made `App.areas` a public array surface (`areas: order` at `app.js:277`). The chat browser test calls `window.App.areas.find(a => a.id === 'chat')` (verified at `tests/browser/test_oauth_modal_flow.py:42`). L3 adds a test asserting: (a) `Array.isArray(window.App.areas)`; (b) `window.App.areas.length > 0`; (c) every entry has `id`, `label`, and `order` keys; (d) `window.App.areas.find(a => a.id === 'studio')` returns the studio descriptor.
- **Auth-required handling**: when `fetchMcpSourceTools` rejects with `auth_required`, the L3 UI renders an inline notice (NOT a popup). Notice contains a link to `#studio/mcp-sources/{source-id}` — the operator clicks, navigates to the source-edit page, clicks Test connection there, completes OAuth, returns to the agent-editor MCPs tab. Critically: the agent-editor MUST NOT auto-trigger OAuth from this surface.
- **Empty-state**: when `/api/mcp-sources` returns `[]`, the multi-attach chip-list renders a call-to-action linking to `#studio/mcp-sources` with text "No MCP sources registered yet. Add one in MCP Sources." (Design Decision §3 verbatim text.)

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` — 22-line stub (current state).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js:150` — `renderMcpsTab(mcpsPanel)` call site. The signature extension needs to pass agent + sources + callbacks (mirror `renderToolsTab`'s call site at `agent-editor.js:151-158`).
- `the_one/interfaces/web/static/js/areas/studio.js:595-609` — `fetchToolSchema` closure-promise cache pattern to mirror.
- `the_one/interfaces/web/static/js/areas/studio.js:1216-1220` — `mcp_source_ids` collection.
- `the_one/interfaces/web/static/js/areas/studio.js:1224-1248` — existing `tool_overrides` walk to mirror for `mcp_overrides`.
- `the_one/interfaces/web/static/js/app.js:277` (`areas: order`) and `:287-292` (`router.replaceSub`) — area registry + router.
- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` (527 lines) — `renderField`, `readFieldValue`, `renderChipListEditor`, `wireChipListEditor` — full form substrate.
- `the_one/interfaces/web/static/js/areas/studio/tools-tab.js:155-216` — existing per-tool override panel using `helpers.renderField` with `mode: 'agent'`. Mirror pattern for L3's credential overrides.
- L1's `the_one/mcp/_overrides.py` — `StdioMCPOverride` / `StreamableHttpMCPOverride` schemas. The frontend doesn't re-validate; the backend's resolver does. L3's UI just sends the payload.
- `tests/browser/test_mcp_test_connection_button.py` (post-L2) — `page.route()` mocking pattern in use.

## Outputs

- `mcps-tab.js` is no longer a stub. Exports `App.studio.renderMcpsTab(panel, agent, allSources, callbacks)` — signature extended.
- `agent-editor.js:150` — call updated to pass agent + sources + callbacks.
- `studio.js` adds `fetchMcpSourceTools(sourceId, {forceRefresh})` factory next to `fetchToolSchema`.
- `studio.js::collectFormData` adds the `mcp_overrides` walk (parallel to the existing `tool_overrides` walk).
- New CSS for the chip-list, per-attachment editor panel, empty-state, and inline auth-required notice.
- New browser test file `tests/browser/test_studio_mcps_tab.py` (or appended tests) covering 7+ scenarios.
- `flight-log.md` updated with L3 entry; leg status flipped to `landed`.

## Acceptance Criteria

- [ ] **L3.1 — Stub replaced; multi-attach chip-list renders.** `mcps-tab.js`'s `renderMcpsTab` accepts `(panel, agent, allSources, callbacks)`. The default view (no fragment / no source-id) renders a chip-list of all `allSources` (fetched from `/api/mcp-sources`); each chip shows the source name + transport-type badge (`stdio` / `streamable-http`); attached chips are visually distinct (e.g. `.chip-attached` class); click toggles attach/detach state by mutating the chip's `data-id` membership in the `.chip-area[data-type="mcp"]`. The existing `data-id` semantics from `studio.js::collectFormData:1220` are preserved — no save-payload schema change for `mcp_source_ids`.
- [ ] **L3.2 — Empty state.** When `allSources` is `[]`, render the empty-state CTA: `"No MCP sources registered yet. Add one in MCP Sources."` with a link to `#studio/mcp-sources` (NOT a hash-router redirect — operator clicks).
- [ ] **L3.3 — Per-attachment editor (rendered when URL fragment selects a source-id).** When the URL is `#studio/agents/{name}/mcps/{source-id}` OR the operator clicks a chip in the attached state, render the per-attachment editor for that source. The editor has two sub-sections:
  - **Tools** — checkbox group rendered from `fetchMcpSourceTools(sourceId)`. Each checkbox represents one un-prefixed tool name from the `list_tools()` response; checked state is computed from `agent.mcp_overrides[source.name].enabled_tools` / `disabled_tools` (per L1's reserved-key contract). The display label shows the un-prefixed name and the prefixed name as a hint (e.g. `read_file (mcp__src__read_file)`). A "Refresh tools" button calls `fetchMcpSourceTools(sourceId, {forceRefresh: true})`.
  - **Override credentials** — renders fields per the source's transport-type override schema (`StdioMCPOverride` for stdio, `StreamableHttpMCPOverride` for streamable-http) using `App.adminFormHelpers.renderField` with `attrPrefix: 'data-mcp-override-field'` (NEW prefix, distinct from the existing `data-tool-override-field`). For Substitute fields with operator values, the `__MASKED__` sentinel preserves existing values on save (per the F1 sentinel contract). The per-attachment editor uses `data-mcp-override-source="{source.name}"` on the wrapping element so `collectFormData` can group fields by source.
- [ ] **L3.4 — `fetchMcpSourceTools(sourceId, {forceRefresh: false})` factory** added in `studio.js` next to `fetchToolSchema`. Closure-cached promises keyed by `sourceId`. Cache lifetime: **area-session-scoped**, mirroring `fetchToolSchema` (the cache is declared `var` inside `studio.init()`'s closure; `init()` runs once per area registration, so the cache persists across agent-editor open/close within the same studio area session — tools are static so cross-agent cache reuse is safe). On `forceRefresh: true`: delete the cache entry before invoking the fetch. On API `{status: "ok"}`: resolve with the full response (`{tools, capabilities, ...}`). On API `{status: "auth_required"}`: reject with a typed error (e.g. `Error` with `name === "AuthRequired"` + `consent_url` attached). On API `{status: "error"}`: reject with the error message; drop the cache entry so retry works.
- [ ] **L3.5 — Auth-required inline notice.** When `fetchMcpSourceTools` rejects with `AuthRequired`, the per-attachment editor's Tools section renders an inline notice "This source needs Test/auth on the source-edit page first." with a link to `#studio/mcp-sources/{source-id}`. **No popup auto-opens.** The chat-UI consent popup flow is the source-edit page's responsibility.
- [ ] **L3.6 — Hash routing for `#studio/agents/{name}/mcps/{source-id}`.** Direct navigation to that URL renders the per-attachment editor for the cited source. Listening to `hashchange` updates the editor when the operator navigates within the area. The router's `replaceSub` is used when the operator clicks a chip → editor opens (URL updates without firing `hashchange`). When the operator clicks a chip on a not-yet-attached source, the URL also updates so refreshing the page lands on the same view.
- [ ] **L3.7 — Save flow extends `mcp_overrides`.** `studio.js::collectFormData` walks `[data-mcp-override-source][data-mcp-override-field]` selectors, groups values by `source-name`, and assembles a dict `{source_name: {field: value, ...}}`. The dict is set on `data.mcp_overrides`; if empty, set `null` (mirroring the existing `tool_overrides` walk semantics at `studio.js:1248`). Per-tool checkboxes contribute `enabled_tools` (allowlist mode) OR `disabled_tools` (denylist mode) lists per source — mode is determined at render time from the agent's existing `mcp_overrides[source.name]?.enabled_tools` (non-null → allowlist; else → denylist). New attachments default to denylist mode. The mode is encoded on the wrapping group as `data-mcp-tool-mode="allowlist"|"denylist"` so `collectFormData` can dispatch on it.
- [ ] **L3.8 — `__MASKED__` round-trip for credential overrides.** Set a per-agent `bearer_token` override (e.g. `"my-real-token"`); save; reload the agent editor; verify the field shows `__MASKED__`; save again WITHOUT retyping; verify the underlying value is preserved (the backend's API and resolver handle the sentinel — frontend just doesn't replace `__MASKED__` with empty string on save). Browser-tested.
- [ ] **L3.9 — App.areas array-shape lock-test.** New test asserts: `Array.isArray(window.App.areas)`; `window.App.areas.length > 0`; every entry has `{id, label, order}` keys; `window.App.areas.find(a => a.id === 'studio')` returns the studio descriptor (i.e. is a non-null object). Lives in `tests/browser/test_studio_mcps_tab.py` (or `tests/browser/test_app_areas_shape.py` — implementer chooses based on file cohesion).
- [ ] **L3.10 — Browser tests** covering at minimum:
  1. Attach a source → save → reload → still attached.
  2. Detach → save → reload → no longer attached.
  3. Toggle two tools off → save → reload → toggles preserved.
  4. Credential override save with `__MASKED__` round-trip (per L3.8).
  5. Empty-state when no MCP sources are registered.
  6. Hash routing: visit `#studio/agents/X/mcps/Y` directly → editor renders for source Y.
  7. Auth-required notice: a source with no tokens triggers the inline redirect-to-source-edit notice (no popup auto-opens).
  8. App.areas array-shape lock per L3.9.
  All tests use `page.route()` to mock `/api/mcp-sources/{id}/test/connect` (per L2's introduced pattern) for the per-tool list. The base `/api/mcp-sources` and `/api/agents/{name}` calls hit the real test app server (existing pattern).
- [ ] **L3.11 — `docker exec the-one pytest -m browser tests/browser/test_studio_mcps_tab.py -q --timeout 120 -x` passes.**
- [ ] **L3.12 — Default-suite gate**: `docker exec the-one pytest tests/ -q --timeout 30 -x --ignore=tests/browser` passes; no new failures vs L2 baseline (L0 baseline known issue still allowed).
- [ ] **L3.13 — `flight-log.md`** gets a new "Leg Progress" entry naming each AC. Leg artifact's status is `landed`.

## Verification Steps

1. **L3.1-L3.3, L3.5** — Browser tests assert DOM presence + structure.
2. **L3.4** — `fetchMcpSourceTools` factory testable via the browser tests' mock-driven flows; no separate JS unit test framework in this codebase.
3. **L3.6** — Browser test 6 verifies direct deep-link navigation. Manual smoke also recommended.
4. **L3.7-L3.8** — Browser tests 1-4 + 8 cover save flow.
5. **L3.9** — Browser test 8 (App.areas lock-test).
6. **L3.10-L3.11** — Run `docker exec the-one pytest -m browser tests/browser/test_studio_mcps_tab.py -q --timeout 120 -x`.
7. **L3.12** — Run `docker exec the-one pytest tests/ -q --timeout 30 -x --ignore=tests/browser`.
8. **Manual smoke** (recommended): start dev container, register an MCP source, open the Studio agent editor for a test agent, navigate to MCPs tab, click a chip, eyeball the editor; toggle tools; save; reload; verify state preserved.

## Implementation Guidance

### Order of operations

1. **L3.4** — add `fetchMcpSourceTools` factory in `studio.js` (small, ~30 LOC).
2. **L3.7** — extend `studio.js::collectFormData` with the `mcp_overrides` walk (~20 LOC, mirrors the existing `tool_overrides` walk).
3. **L3.1-L3.3, L3.5** — rewrite `mcps-tab.js`. This is the bulk: chip-list, per-attachment editor, empty-state, auth-required notice, hash-routing wiring. Estimated ~300-450 LOC.
4. **CSS additions** for the new UI elements (~30-50 LOC).
5. **L3.6** — wire `hashchange` listener inside `mcps-tab.js`.
6. **L3.10** — write browser tests with `page.route()` mocking.
7. **L3.9** — App.areas array-shape lock-test.
8. **L3.11-L3.12** — full-suite gate.

### L3.4 — `fetchMcpSourceTools` factory

In `studio.js`, alongside `fetchToolSchema` (around lines 595-609), add:

```js
// L3 — Lazy MCP-source tools fetcher. Closure-cached promise per
// sourceId (mirrors fetchToolSchema's pattern at lines 595-609). The
// cache stores the in-flight promise so concurrent callers reuse it.
// The cache survives across agent changes within the studio area
// lifetime; tools are static within a session.
//
// On API `{status: "ok"}`: resolves with the full response object
// `{tools, capabilities, ...}`.
// On API `{status: "auth_required"}`: rejects with an Error whose
// .name === "AuthRequired" and .consent_url is the redirect URL (UI
// surfaces an inline notice; NEVER auto-trigger the popup from this
// surface — the source-edit page is the OAuth affordance).
// On API `{status: "error"}` or HTTP error: rejects with a generic
// Error; drops the cache entry so retries land on a fresh promise.
var _mcpSourceToolsCache = {};

function fetchMcpSourceTools(sourceId, options) {
  options = options || {};
  if (options.forceRefresh) {
    delete _mcpSourceToolsCache[sourceId];
  }
  if (_mcpSourceToolsCache[sourceId]) return _mcpSourceToolsCache[sourceId];

  var p = fetch('/api/mcp-sources/' + encodeURIComponent(sourceId) + '/test/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }).then(function (r) {
    if (!r.ok) {
      throw new Error('fetchMcpSourceTools: HTTP ' + r.status);
    }
    return r.json();
  }).then(function (data) {
    if (data.status === 'ok') return data;
    if (data.status === 'auth_required') {
      var err = new Error('auth_required');
      err.name = 'AuthRequired';
      err.consent_url = data.consent_url;
      throw err;
    }
    throw new Error(data.error || 'unknown error');
  }).catch(function (err) {
    delete _mcpSourceToolsCache[sourceId];
    throw err;
  });
  _mcpSourceToolsCache[sourceId] = p;
  return p;
}
```

Pass `fetchMcpSourceTools` as a callback to `renderAgentEditor`'s callbacks dict at the call site (around `studio.js:851-871`), so `agent-editor.js` can hand it down to `renderMcpsTab`.

### L3.7 — `collectFormData` extension

In `the_one/interfaces/web/static/js/areas/studio.js::collectFormData`, after the `tool_overrides` walk (around line 1248), add:

```js
// L3 — Walk mcp_overrides selectors. Mirrors the tool_overrides walk
// above, but groups by source-name (data-mcp-override-source) instead
// of tool-name. Per-tool checkboxes contribute enabled_tools /
// disabled_tools lists per source (NOT collected here — they live
// under [data-mcp-tool-toggle][data-mcp-source]).
var mcpOverrideEls = editorEl.querySelectorAll(
  '[data-mcp-override-source][data-mcp-override-field]'
);
var mcpOverrides = {};
for (var mi = 0; mi < mcpOverrideEls.length; mi++) {
  var me = mcpOverrideEls[mi];
  if (me.classList && me.classList.contains('field-row')) continue;
  var sourceName = me.dataset.mcpOverrideSource;
  var fieldName = me.dataset.mcpOverrideField;
  if (!sourceName || !fieldName) continue;
  var v = helpers ? helpers.readFieldValue(me) : null;
  if (v === null || v === undefined) continue;
  if (Array.isArray(v) && v.length === 0) continue;
  if (typeof v === 'string' && v === '') continue;
  if (!mcpOverrides[sourceName]) mcpOverrides[sourceName] = {};
  mcpOverrides[sourceName][fieldName] = v;
}

// Per-tool checkbox toggles within each attached source. Each
// checkbox carries `data-mcp-tool-toggle` (the un-prefixed tool name)
// and `data-mcp-source` (the source name). The wrapping group element
// also carries `data-mcp-tool-mode={"allowlist"|"denylist"}` declared
// at render time based on the agent's existing override shape.
//
// Mode semantics:
//   - denylist (default for new attachments): collect un-checked
//     tools into disabled_tools; enabled_tools is preserved as-is
//     from the existing agent payload (omitted from this leg's UI).
//   - allowlist (when agent already has enabled_tools set via API):
//     collect checked tools into enabled_tools; disabled_tools is
//     preserved as-is.
// L3's UI defaults to denylist mode for new operator-driven toggling
// because it's the simpler mental model. The allowlist branch
// preserves API-provided enabled_tools without dropping them.
var toggleEls = editorEl.querySelectorAll('[data-mcp-tool-toggle][data-mcp-source]');
var enabledBySource = {};
var disabledBySource = {};
var modeBySource = {};
for (var ti = 0; ti < toggleEls.length; ti++) {
  var te = toggleEls[ti];
  var srcName = te.dataset.mcpSource;
  var tlName = te.dataset.mcpToolToggle;
  if (!srcName || !tlName) continue;
  // Mode comes from the wrapping group; fall back to denylist.
  var groupEl = te.closest('[data-mcp-tool-group]');
  var mode = (groupEl && groupEl.dataset.mcpToolMode) || 'denylist';
  modeBySource[srcName] = mode;
  if (mode === 'allowlist') {
    if (te.checked) {
      if (!enabledBySource[srcName]) enabledBySource[srcName] = [];
      enabledBySource[srcName].push(tlName);
    }
  } else {
    if (!te.checked) {
      if (!disabledBySource[srcName]) disabledBySource[srcName] = [];
      disabledBySource[srcName].push(tlName);
    }
  }
}
for (var sname in modeBySource) {
  if (!mcpOverrides[sname]) mcpOverrides[sname] = {};
  if (modeBySource[sname] === 'allowlist') {
    mcpOverrides[sname].enabled_tools = enabledBySource[sname] || [];
  } else {
    if (disabledBySource[sname] && disabledBySource[sname].length > 0) {
      mcpOverrides[sname].disabled_tools = disabledBySource[sname];
    }
  }
}

data.mcp_overrides = Object.keys(mcpOverrides).length > 0 ? mcpOverrides : null;
```

**Mode determination at render time**: when L3's per-attachment editor builds the checkbox group, it inspects `agent.mcp_overrides[source.name]?.enabled_tools`:
- If `enabled_tools` is a non-null array → render in `allowlist` mode (`data-mcp-tool-mode="allowlist"` on the group); checkboxes are checked when name is IN the allowlist.
- Else → render in `denylist` mode (`data-mcp-tool-mode="denylist"`); checkboxes are checked unless name is in `disabled_tools`.

This preserves API-provided `enabled_tools` (whatever shape it had) and lets the UI continue to operate on whichever mode the agent was already configured with. New attachments always default to denylist (most operators want "all tools, except some").

Position: insert AFTER the existing `data.tool_overrides = ...` line (around `studio.js:1248`), BEFORE `return data;`. Indentation matches `collectFormData`'s body.

### L3.1-L3.3 — `mcps-tab.js` rewrite

Rewrite the file. New top-level structure (illustrative — implementer adapts):

```js
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderMcpsTab(panel, agent, allSources, callbacks) {
    panel.innerHTML = '';
    callbacks = callbacks || {};
    var fetchMcpSourceTools = callbacks.fetchMcpSourceTools;
    var onChange = callbacks.onChange || function () {};

    if (!allSources || allSources.length === 0) {
      _renderEmptyState(panel);
      return;
    }

    var sub = _parseSourceFromHash();
    if (sub.sourceId) {
      _renderPerAttachmentEditor(panel, agent, allSources, sub.sourceId, fetchMcpSourceTools, onChange);
    } else {
      _renderChipList(panel, agent, allSources, onChange);
    }

    // Hash-change listener — re-renders when operator deep-links or
    // navigates within the area. Removed on tab unmount.
    function onHashChange() { renderMcpsTab(panel, agent, allSources, callbacks); }
    window.addEventListener('hashchange', onHashChange);
    panel._mcpsTabHashHandler = onHashChange;  // exposed for cleanup
  }

  function _renderEmptyState(panel) { /* ... CTA linking to #studio/mcp-sources ... */ }
  function _renderChipList(panel, agent, allSources, onChange) { /* ... chip-area[data-type="mcp"] with click-to-toggle ... */ }
  function _renderPerAttachmentEditor(panel, agent, allSources, sourceId, fetchMcpSourceTools, onChange) {
    // Look up source by id; render Tools section + Override credentials section.
    // Use App.adminFormHelpers.renderField for credential fields (mode='agent',
    // attrPrefix='data-mcp-override-field', plus data-mcp-override-source on
    // wrapping element).
    // Tools section: fetchMcpSourceTools(sourceId).then(render checkboxes)
    //                .catch(if AuthRequired, render inline notice).
  }
  function _parseSourceFromHash() {
    // Extract source-id from `#studio/agents/{name}/mcps/{source-id}` if present.
  }

  window.App.studio.renderMcpsTab = renderMcpsTab;
})();
```

**Key implementation details**:

- The chip-list uses `<div class="chip-area" data-type="mcp">` so `studio.js::collectFormData` at line 1216 picks up attached chips via `.chip-area[data-type="mcp"] .chip` and reads `chip.dataset.id`. The chip element shape: `<div class="chip" data-id="{source.id}">{source.name}</div>` plus a `chip-attached` class when attached. Click toggles the class AND adds/removes the chip from the area.
- The per-attachment editor's Override credentials section uses `App.adminFormHelpers.renderField(fieldName, prop, value, {mode: 'agent', operatorValue: ..., attrPrefix: 'data-mcp-override-field', toolName: source.name})`. The `toolName` argument is the source's name (the form helpers' arg name says "tool" but it's just the override-key passed through to data attributes — irrelevant whether it's a tool or source). The wrapping `<div>` carries `data-mcp-override-source="{source.name}"` so `collectFormData` can group fields. **Note about cross-namespace attribute emission**: `helpers.renderField` ALSO emits `data-tool-override-tool="{toolName}"` on its inputs (hardcoded at `tools-form-helpers.js:127-129`, NOT derived from `attrPrefix`). This is benign — the existing `tool_overrides` walk at `studio.js:1228` queries `[data-tool-override-tool][data-tool-override-field]` (BOTH attributes required); since L3 sets `attrPrefix='data-mcp-override-field'`, the `data-tool-override-field` companion is absent, so the existing walk doesn't pick up MCP fields. No collision; documenting for clarity.
- The per-tool checkbox group: wrapping element carries `<div data-mcp-tool-group data-mcp-tool-mode="allowlist"|"denylist">`. Each box: `<label><input type="checkbox" data-mcp-tool-toggle="{tool.name}" data-mcp-source="{source.name}" checked>{tool.name}</label>`. Mode-determination at render time (per L3.7): if `agent.mcp_overrides[source.name]?.enabled_tools` is a non-null array → allowlist mode (`data-mcp-tool-mode="allowlist"`; checkboxes checked when name is in allowlist). Else → denylist mode (`data-mcp-tool-mode="denylist"`; checkboxes checked unless name is in `disabled_tools`). The `collectFormData` walk dispatches on the same data attribute. New attachments default to denylist (no `enabled_tools` set yet → denylist by default).
- The L1 schemas (`StdioMCPOverride.env`, `StreamableHttpMCPOverride.bearer_token`/`headers`) are already typed for `App.adminFormHelpers`. The `prop` for each field comes from the schema's JSON Schema dump. The frontend doesn't need a fresh JSON-schema fetch — hardcode the prop shapes for stdio (`env`: object) and streamable-http (`bearer_token`: string + Substitute marker, `headers`: object + Substitute marker). Implementer's discretion: fetch the schema dynamically vs hardcode. **Recommended**: hardcode for L3 to keep scope tight; if/when L1's schemas evolve, add a fetch.

### CSS additions

Append to the appropriate CSS file (`studio.css` for area-scoped rules):

```css
  .area-studio .mcp-attach-chip-list { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 0; }
  .area-studio .mcp-attach-chip-list .chip { padding: 6px 12px; border: 1px solid var(--border); border-radius: 16px; cursor: pointer; user-select: none; background: var(--surface); color: var(--fg-secondary); }
  .area-studio .mcp-attach-chip-list .chip-attached { background: var(--accent); color: var(--fg-on-accent, white); border-color: var(--accent); }
  .area-studio .mcp-attach-chip-list .chip-transport-badge { font-size: 10px; opacity: 0.7; margin-left: 4px; }
  .area-studio .mcp-empty-state { padding: 24px; text-align: center; color: var(--fg-secondary); }
  .area-studio .mcp-empty-state a { color: var(--accent); text-decoration: underline; }
  .area-studio .mcp-attachment-editor { display: flex; flex-direction: column; gap: 16px; padding: 12px 0; }
  .area-studio .mcp-tools-checkbox-group { display: flex; flex-direction: column; gap: 4px; }
  .area-studio .mcp-tools-checkbox-group label { display: flex; align-items: center; gap: 8px; cursor: pointer; }
  .area-studio .mcp-auth-required-notice { padding: 12px; background: var(--surface-elevated); border-left: 3px solid var(--accent); border-radius: 4px; }
```

### L3.6 — Hash routing (CRITICAL: parser + serializer must BOTH be patched)

`studio.js`'s existing `hydrateState` (lines 95-112) parses `agents/{name}/{tab}` but **rejects any tab string that isn't one of `general | knowledge | mcps | tools` — defaulting to `general`**. So a deep link to `#studio/agents/X/mcps/some-uuid` would split as `tab = "mcps/some-uuid"`, fail the four-tab whitelist, and land on the General tab. The deep-link AC L3.6 + Browser Test 6 BOTH fail without explicit parser + serializer patches.

**Patch A — `hydrateState` parse extension** (in `studio.js`, around line 105 inside the `else { ... pending = ...; var tab = rest.slice(slashIdx + 1); if (...) pendingTab = tab; ... }` block):

```js
// L3 patch: accept "mcps/{source-id}" as a deeper sub-path. Stash the
// source-id on a new instance property so renderMcpsTab can pick it up.
} else {
  pending = decodeURIComponent(rest.slice(0, slashIdx));
  var tab = rest.slice(slashIdx + 1);
  // L3 — split deeper "mcps/{source-id}" before the tab whitelist check.
  var pendingMcpAgentSourceId = null;
  if (tab.indexOf('mcps/') === 0) {
    pendingMcpAgentSourceId = decodeURIComponent(tab.slice('mcps/'.length));
    tab = 'mcps';
  }
  if (tab === 'general' || tab === 'knowledge' || tab === 'mcps' || tab === 'tools') {
    pendingTab = tab;
  } else {
    pendingTab = 'general';
  }
  this._pendingMcpAgentSourceId = pendingMcpAgentSourceId;  // NEW property
}
```

**Patch B — `serializeState` extension** (in `studio.js`, around line 37-39):

```js
if (this._activeSection === 'agents' && this._selectedAgent && !this._createMode) {
  var base = 'agents/' + encodeURIComponent(this._selectedAgent.name) +
    '/' + (this._activeTab || 'general');
  // L3 — when on the MCPs tab AND a source-id is selected, append it so
  // refresh preserves the per-attachment editor view.
  if (this._activeTab === 'mcps' && this._selectedMcpAgentSourceId) {
    return base + '/' + encodeURIComponent(this._selectedMcpAgentSourceId);
  }
  return base;
}
```

**Patch C — store the selected source-id when the operator clicks a chip in the per-attachment editor flow.** Add to the studio area's instance state initializer (around `studio.js:153-158` where `self._selectedAgent = null` etc. live):

```js
self._selectedMcpAgentSourceId = null;
```

Then when `renderMcpsTab` opens the per-attachment editor (either from a chip click OR from `_pendingMcpAgentSourceId` consumption on hydrate), call `self._selectedMcpAgentSourceId = sourceId` AND `App.router.replaceSub(self.serializeState())` to sync the URL.

When the operator navigates back to the chip-list view (e.g. via browser back, or by deselecting), set `self._selectedMcpAgentSourceId = null` and re-call `replaceSub`.

**Naming note**: `_pendingMcpAgentSourceId` (used by hydrate) is intentionally distinct from `_pendingMcpSourceId` (used by the mcp-sources section, around lines 132+ in the existing hydrate code) so the two flows don't collide.

When the operator clicks a chip OR the page hydrates from a deep-link, the URL update happens via `App.router.replaceSub(...)` (silent — no hashchange). Browser back/forward fires `hashchange`, the area's existing dispatcher re-runs hydrate, and the MCPs tab re-renders. The MCPs tab itself need NOT add a `hashchange` listener if hydrate-driven re-render covers all cases — verify during implementation; if hydrate-driven re-render doesn't cover the in-tab navigation case, add a `hashchange` listener inside `renderMcpsTab` as the leg's original spec described.

### L3.10 — Browser tests with `page.route()` mocking

Create `tests/browser/test_studio_mcps_tab.py`. Mirror `tests/browser/test_mcp_test_connection_button.py`'s patterns (post-L2). Each test mocks `/api/mcp-sources/{id}/test/connect` via `page.route()` to return a controlled `tools[]`. Assertions probe DOM via `data-testid`-style selectors.

```python
import json
import httpx
import pytest
from playwright.sync_api import Page, expect


def _seed_mcp_source(base_url: str, payload: dict) -> str:
    r = httpx.post(f"{base_url}/api/mcp-sources", json=payload, timeout=5.0)
    assert r.status_code in (200, 201)
    return r.json()["id"]


def _seed_agent(base_url: str, name: str, payload: dict) -> dict:
    payload["name"] = name
    r = httpx.post(f"{base_url}/api/agents", json=payload, timeout=5.0)
    assert r.status_code in (200, 201)
    return r.json()


# Test 1: attach a source → save → reload → still attached
@pytest.mark.browser
def test_attach_source_persists(app_clean: str, page: Page) -> None: ...

# Test 2: detach
@pytest.mark.browser
def test_detach_source_persists(app_clean: str, page: Page) -> None: ...

# Test 3: per-tool toggle
@pytest.mark.browser
def test_per_tool_toggle_persists(app_clean: str, page: Page) -> None: ...

# Test 4: __MASKED__ round-trip
@pytest.mark.browser
def test_credential_override_masked_round_trip(app_clean: str, page: Page) -> None: ...

# Test 5: empty state
@pytest.mark.browser
def test_empty_state_when_no_sources(app_clean: str, page: Page) -> None: ...

# Test 6: hash routing
@pytest.mark.browser
def test_hash_routing_deep_link(app_clean: str, page: Page) -> None: ...

# Test 7: auth-required inline notice
@pytest.mark.browser
def test_auth_required_inline_notice_no_popup(app_clean: str, page: Page) -> None: ...

# Test 8: App.areas array-shape lock
@pytest.mark.browser
def test_app_areas_array_shape_lock(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.wait_for_load_state("domcontentloaded")
    result = page.evaluate("""
        () => ({
            isArray: Array.isArray(window.App.areas),
            length: window.App.areas.length,
            allHaveKeys: window.App.areas.every(a => 'id' in a && 'label' in a && 'order' in a),
            studioFound: !!window.App.areas.find(a => a.id === 'studio'),
        })
    """)
    assert result["isArray"] is True
    assert result["length"] > 0
    assert result["allHaveKeys"] is True
    assert result["studioFound"] is True
```

For Tests 3, 4, 6, 7: use `page.route()` to mock `/api/mcp-sources/{id}/test/connect` with a synthetic `{status: "ok", tools: [...], capabilities: {...}}` payload. For Test 7: return `{status: "auth_required", consent_url: "https://idp.example.com/oauth/authorize"}` and assert no popup opens (use `page.on("popup", ...)` to detect).

## Edge Cases

- **Operator navigates to `#studio/agents/X/mcps/Y` where source Y doesn't exist** — render an error notice with a link back to the chip list. Don't crash.
- **Operator attaches a source, navigates to its per-attachment editor, and the source is later deleted by another tab** — the next save attempt fails with a 404 from the agent PUT; the save flow's existing error handler surfaces the message. Out of scope to handle proactively in L3.
- **A source's `list_tools()` returns 0 tools** — the Tools section renders an "No tools available" message (and the per-tool toggle group is empty). The operator can still set credential overrides.
- **The override schema's `__MASKED__` sentinel for `bearer_token`** — when the agent already has a bearer_token override set, the form helpers render the field showing `__MASKED__`; on save, `collectFormData` reads the masked value and sends it as-is; the backend's API layer detects `__MASKED__` and preserves the prior value. **L3 does NOT reimplement this** — the backend already has the F1 sentinel logic. L3 just sends what the form holds.
- **Two attached sources both have credentials with the same field name (e.g. both have `bearer_token`)** — `collectFormData` groups by source name, so the data attributes `data-mcp-override-source="{source.name}"` keep them separate. No collision.
- **Empty-state navigation race**: if the operator clicks the empty-state CTA link to `#studio/mcp-sources`, the studio area's existing router handles the dispatch. No L3 change.
- **Hash router infinite loop**: a chip click calls `App.router.replaceSub(...)` which uses `history.replaceState` (silent — no `hashchange` fires). The MCPs tab's own `hashchange` listener fires only on browser-driven navigation. So clicking a chip shouldn't trigger the listener; deep-link / back-button does. Verified at the router contract level.
- **Hashchange fires while panel is detached** (operator clicked another tab): the listener still fires; if `panel` is no longer in the DOM, `panel.innerHTML = ''` is harmless. Cleanup is best-effort; no leak. (Acceptable per the existing `agent-editor.js` lifecycle pattern — tabs aren't strict-cleanup.)

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` — full rewrite from 22-line stub to ~300-450 LOC.
- `the_one/interfaces/web/static/js/areas/studio.js` — add `fetchMcpSourceTools` factory (~30 LOC); extend `collectFormData` with `mcp_overrides` walk (~30 LOC); pass `fetchMcpSourceTools` callback through `renderAgentEditor` call site (~3 LOC).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js:150` — extend `renderMcpsTab` call to pass agent + allSources + callbacks (~5 LOC).
- `the_one/interfaces/web/static/css/studio.css` — append CSS rules (~30-50 LOC).
- `tests/browser/test_studio_mcps_tab.py` (new) — 8 browser tests (~400-500 LOC).
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight-log.md` — append L3 progress entry.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight.md` — check off L3 (final commit step).
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/legs/03-agent-editor-mcps-tab.md` — update status to `landed`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `docker exec the-one pytest -m browser tests/browser/test_studio_mcps_tab.py -q --timeout 120 -x` passes
- [ ] Default-suite scoped run passes (no new failures vs L2 baseline)
- [ ] Manual smoke (recommended): hit the agent-editor MCPs tab in dev container, click chip, eyeball editor, save, reload, verify
- [ ] Update `flight-log.md` with the L3 progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit yet — orchestrator batches code review + commit at flight end
- [ ] Signal `[HANDOFF:review-needed]`

## Citation Audit

11 citations verified against current code at leg design time:

- `mcps-tab.js` (currently 22-line stub) — **OK**.
- `agent-editor.js:150` (`renderMcpsTab(mcpsPanel)` call) — **OK**.
- `studio.js:595-609` (`fetchToolSchema` factory pattern) — **OK**.
- `studio.js:1216-1220` (`mcp_source_ids` collection from `.chip-area[data-type="mcp"]`) — **OK**.
- `studio.js:1224-1248` (`tool_overrides` walk) — **OK**.
- `studio.js:851-871` (renderAgentEditor callback dict) — **OK**.
- `app.js:277` (`areas: order` array export) — **OK**.
- `app.js:287-292` (`router.replaceSub`) — **OK**.
- `tests/browser/test_oauth_modal_flow.py:42` (existing `App.areas.find(...)` consumer) — **OK**.
- `admin/tools-form-helpers.js:516` (`window.App.adminFormHelpers` export) — **OK**.
- `studio/tools-tab.js:155-216` (existing per-tool override panel using `helpers.renderField`) — **OK**.
- `studio.js:23-50` (`serializeState`) and `studio.js:95-112` (`hydrateState` agents-tab parsing) — **OK**, verified at design-review time. The deeper-sub-path patches in L3.6 are required because `hydrateState`'s tab whitelist defaults `mcps/{source-id}` to `general`.
- `tools-form-helpers.js:127-129` (`data-tool-override-tool` hardcoded emission) — **OK**, verified during design review; benign because the companion attribute differs.

No drift detected; the L3.6 hash-routing patches were sharpened during design review with concrete code shapes for `hydrateState` + `serializeState` rather than the original "verify and add a branch" hand-wave.
