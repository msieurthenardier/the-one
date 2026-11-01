// App.studio.agentFormData -- the agent editor's form reading and dirty tracking
// (M31 F2 L03, DD1): collectFormData (the [data-field] / toggle / override walk),
// getFormSnapshot, checkDirty and the ungated-prefix `disabled_tools` union.
// Moved verbatim out of studio.js; a factory studio calls once in init:
//
//   var formData = App.studio.agentFormData.create(ctx);
//
// ctx (studio -> module): self, state, editorEl. The model picker and the editor
// controller both take checkDirty/getFormSnapshot from this handle, which is why
// they live here and not in the controller (no picker <-> controller cycle).
//
// handle (module -> studio): collectFormData(), getFormSnapshot(), checkDirty(),
// blockingError() (M31 F4 L05c).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var editorEl = ctx.editorEl;

    // ── Dirty tracking ───────────────────────────────────────────────

    function getFormSnapshot() {
      var data = collectFormData();
      return JSON.stringify(data);
    }

    function checkDirty() {
      var current = getFormSnapshot();
      state.dirty = current !== state.snapshot;
      // The shell (M31 F2 L06a) derives the unsaved caption, Save and Cancel from
      // the dirty flag: Save follows it, Cancel follows it on an open agent and
      // stays enabled on the create form (enabledWhenClean), which abandons
      // creation (DD8). `shell` is a call-time getter into the current mount; none
      // exists while the editor is still being built.
      var shell = ctx.shell ? ctx.shell() : null;
      if (!shell) return;
      shell.setDirty(state.dirty);
      // Squawk 0090: Save additionally stays disabled while the editor is
      // rendering a NOT-freshly-loaded agent -- `collectFormData`'s
      // ungated-prefix union reads `self._selectedAgent`, and a stale one
      // would re-emit a pre-rename `kb__…__search` entry. The block is re-applied
      // after EVERY setDirty through a dedicated Save disable (never setBusy,
      // which would also disable Cancel): discarding edits is always safe.
      var saveBlocked = !self._createMode && self._selectedAgentLoaded === false;
      if (saveBlocked) shell.saveButton.disabled = true;
    }

    // F6 L3 (L3-D3, DD-13) — the ungated-prefix `disabled_tools` union.
    // `collectFormData`'s tool-toggle walk below only ever sees BUILT-IN
    // tool checkboxes (the Tools tab renders built-in categories only), so
    // an ungated-prefix entry set through the API (see the prefix list
    // below) would otherwise be erased by any unrelated Studio save.
    // Reads `self._selectedAgent`
    // — refreshed on every agent-edit mount by doSelect's fresh-agent
    // fetch (L3-D3) — never the stale outer closure or `self._agents`
    // cache, so a rename performed earlier in the session doesn't put a
    // pre-rewrite entry straight back. `self._selectedAgent` is `null` in
    // create-mode (AC-9): a new agent has no stored entries, so this
    // returns `[]` rather than crashing Save.
    var UNGATED_TOOL_PREFIXES =
      (window.App.toolCategories && window.App.toolCategories.ungatedPrefixes) || [];
    function _storedUngatedDisabledNames() {
      var stored = (self._selectedAgent && self._selectedAgent.disabled_tools) || [];
      var result = [];
      for (var s = 0; s < stored.length; s++) {
        for (var p = 0; p < UNGATED_TOOL_PREFIXES.length; p++) {
          if (stored[s].indexOf(UNGATED_TOOL_PREFIXES[p]) === 0) {
            result.push(stored[s]);
            break;
          }
        }
      }
      return result;
    }

    // ── Form data collection ─────────────────────────────────────────
    //
    // collectFormData queries by [data-field="..."] selectors which work
    // regardless of which tab/panel the field lives in. Fields that span
    // tabs (provider, model, system_prompt, max_iterations on General;
    // tool toggles on Tools) are all reachable from editorEl.
    function collectFormData() {
      var data = {};
      var fields = editorEl.querySelectorAll('input[data-field], textarea[data-field], select[data-field]');
      for (var i = 0; i < fields.length; i++) {
        var f = fields[i];
        if (f.disabled) continue; // skip Advanced-stub disabled inputs
        var key = f.dataset.field;
        if (!key) continue;
        if (key === 'max_iterations') {
          data[key] = parseInt(f.value, 10) || 20;
        } else if (key === 'chat_history_retention_days') {
          // DD6: preserve the raw parsed value — only NaN (empty/non-numeric)
          // falls back to the 30-day default. A typed out-of-range value (e.g.
          // 0 or 400) is forwarded verbatim so the server's validation rejects
          // it with a 422 that surfaces at the UI, rather than being silently
          // clamped to the default client-side. (Contract relied on by the
          // agent-retention-setting-roundtrip behavior-test lower-bound variant.)
          var n = parseInt(f.value, 10);
          data[key] = Number.isNaN(n) ? 30 : n;
        } else if (key === 'provider_config_id') {
          data[key] = f.value || null;
        } else {
          data[key] = f.value;
        }
      }

      // Scope to built-in-tool checkbox toggles only. MCP source toggles
      // carry `data-mcp-source-id` (NOT `data-tool`); MCP per-tool toggles
      // carry `data-mcp-tool-toggle` (handled in a separate collector
      // below). The `input[type="checkbox"]` filter plus `[data-tool]`
      // attribute is sufficient to disambiguate. (Previously this query
      // required `.tool-toggle` for the iOS-pill pattern; Mission 08 F4 L2
      // widened the per-tool tile to use a visible `.checkbox-primary`
      // input — no class disambiguation possible — so the selector
      // shifted to `input[type="checkbox"][data-tool]`.)
      var toggles = editorEl.querySelectorAll('input[type="checkbox"][data-tool]');
      var enabledNames = [];
      var disabledNames = [];
      var exemptOffNames = [];
      var allOn = true;
      var exemptNames = (window.App.toolCategories && window.App.toolCategories.whitelistExempt) || [];
      for (var t = 0; t < toggles.length; t++) {
        var toggleName = toggles[t].dataset.tool;
        if (exemptNames.indexOf(toggleName) >= 0) {
          // M28 DD6: a whitelist-exempt tool (current_time) never enters the
          // branch choice or enabled_tools; unchecked, it goes to
          // disabled_tools in every branch.
          if (!toggles[t].checked) exemptOffNames.push(toggleName);
          continue;
        }
        if (toggles[t].checked) {
          enabledNames.push(toggleName);
        } else {
          disabledNames.push(toggleName);
          allOn = false;
        }
      }

      // F6 L3 (L3-D3, DD-13): every branch appends the stored ungated-
      // prefix entries AFTER the built-in names, in their original stored
      // order — a Set or object-key walk would make the Save button
      // flicker, since this value feeds dirty-tracking via getFormSnapshot.
      if (allOn) {
        data.enabled_tools = null;
        data.disabled_tools = exemptOffNames.concat(_storedUngatedDisabledNames());
      } else if (enabledNames.length <= disabledNames.length) {
        // enabled_tools is a BUILT-IN-only whitelist by backend contract
        // (AgentConfig.is_tool_enabled, F09-08): the backend does not gate
        // `mcp__`-prefixed MCP tools by this list — MCP is governed by
        // mcp_overrides. Do NOT inject `mcp__` names here; that would
        // reintroduce the coupling that silently stripped MCP tools.
        data.enabled_tools = enabledNames;
        data.disabled_tools = exemptOffNames.concat(_storedUngatedDisabledNames());
      } else {
        data.enabled_tools = null;
        data.disabled_tools = disabledNames.concat(exemptOffNames, _storedUngatedDisabledNames());
      }

      // Connections (chips) — Tools tab does not currently render chips
      // (MCP attach is a tool-row toggle, not a chip; see F8 L4 note
      // below). The override chip-list editors carry
      // data-tool-override-tool (NOT data-type), so they don't match the
      // [data-type] selector here and are picked up below in the override
      // walk.
      // F8 L4 — Tools tab uses tool-row toggles instead of chip-area.
      // Walk the new [data-mcp-source-toggle]:checked selector to collect
      // attached source IDs.
      var mcpToggles = editorEl.querySelectorAll('[data-mcp-source-toggle][data-mcp-source-id]');
      data.mcp_source_ids = [];
      if (self._mcpSourcesLoaded || !self._selectedAgent) {
        for (var m = 0; m < mcpToggles.length; m++) {
          if (mcpToggles[m].checked) data.mcp_source_ids.push(mcpToggles[m].dataset.mcpSourceId);
        }
      } else {
        // Squawk 0080: the MCP source list never loaded, so the Tools tab has
        // no rows and every toggle is trivially absent. `update_agent` does
        // not preserve an omitted `mcp_source_ids` (it defaults to []), so
        // send the agent's stored value back unchanged instead of wiping it.
        data.mcp_source_ids = (self._selectedAgent.mcp_source_ids || []).slice();
      }

      // F6 L3 (DD-4, L3-D1): `kb_ids` is sent ONLY when the Knowledge
      // tab's root carries `data-kb-list-loaded="true"` — set by
      // knowledge-tab.js exclusively on a successful refresh. When the
      // marker is absent (load failed, or a save races an in-flight
      // refresh — Edge Case), `kb_ids` is omitted from the payload
      // entirely so the server-side preserve (Leg 2 AC-7) keeps the
      // stored value instead of squawk 0050's `kb_ids: []` wipe. A loaded
      // surface with zero checked rows still sends `[]` — a legitimate
      // "detach everything".
      var kbTabRoot = editorEl.querySelector('[data-testid="agent-knowledge-tab"][data-kb-list-loaded="true"]');
      if (kbTabRoot) {
        var kbToggles = editorEl.querySelectorAll('[data-kb-toggle][data-kb-id]:checked');
        data.kb_ids = [];
        for (var k = 0; k < kbToggles.length; k++) {
          data.kb_ids.push(kbToggles[k].dataset.kbId);
        }
      }

      // F6 leg 05 — collect tool_overrides from per-tool override panels.
      // Each override control carries `data-tool-override-tool="{name}"` and
      // `data-tool-override-field="{field}"` (App.toolConfigFields, M31 F4 L05b,
      // agent mode; the row around it carries neither). The chip-list root carries
      // both too, so the same selector picks it up; readValue dispatches on
      // data-field-type.
      var overrideEls = editorEl.querySelectorAll('[data-tool-override-tool][data-tool-override-field]');
      var overrides = {};
      var renderedFields = {};
      // Sortie 07, DD9: only fields the operator made the agent's OWN are stored (an
      // inherited field follows the app-wide value and stores nothing). The state and
      // the value to store come from the field handles the Tools tab exposes
      // (fieldHandles()); a denied list stores its added chips only.
      var tabHandle = ctx.toolsTab ? ctx.toolsTab() : null;
      var handles = (tabHandle && tabHandle.fieldHandles) ? tabHandle.fieldHandles() : {};
      for (var oi = 0; oi < overrideEls.length; oi++) {
        var oe = overrideEls[oi];
        var toolName = oe.dataset.toolOverrideTool;
        var fieldName = oe.dataset.toolOverrideField;
        if (!toolName || !fieldName) continue;
        var fieldHandle = handles[toolName] && handles[toolName][fieldName];
        if (!fieldHandle) {
          // A rendered control with no handle should not happen: leave the field to
          // the stored-value carry below instead of guessing from the DOM.
          // eslint-disable-next-line no-console
          console.warn('Tool override control %s.%s has no field handle; keeping its stored value.', toolName, fieldName);
          continue;
        }
        if (!renderedFields[toolName]) renderedFields[toolName] = {};
        renderedFields[toolName][fieldName] = true;
        if (!fieldHandle.isOwn()) continue;
        var v = fieldHandle.ownValue();
        // An own field left empty returns to inherited (nothing stored).
        if (v === null || v === undefined) continue;
        if (!overrides[toolName]) overrides[toolName] = {};
        overrides[toolName][fieldName] = v;
      }
      // Squawk 0223: the override inputs exist only for tools whose panel
      // was opened this mount. If none was, OMIT the key (the server keeps
      // the stored map). If some were, the edited tools replace their stored
      // entry and tools never opened keep theirs; `{}` = everything cleared.
      var loadedTools = renderedFields;
      if (Object.keys(loadedTools).length > 0) {
        var stored = (self._selectedAgent && self._selectedAgent.tool_overrides) || {};
        Object.keys(stored).forEach(function (tn) {
          if (!loadedTools[tn]) {
            overrides[tn] = stored[tn];
            return;
          }
          // M31 F4 L05c: a loaded tool's walk rebuilds its entry from the fields it
          // RENDERED. A stored key with no rendered field (the tool's config_fields
          // hides the setting, so it is never in the schema) is carried over
          // unchanged: it stays stored and still applies at resolve time. A key whose
          // field the schema shows but no longer marks overridable is the exception
          // (the panel flags it in data-tool-override-dead): the resolver rejects such
          // an override, so a Save drops it, as it always did.
          var dead = deadFields(tn);
          Object.keys(stored[tn] || {}).forEach(function (fn) {
            if (renderedFields[tn][fn] || dead[fn]) return;
            if (!overrides[tn]) overrides[tn] = {};
            overrides[tn][fn] = stored[tn][fn];
          });
        });
        // Open-and-close stays clean: a result equal to the stored map is not sent
        // (the server keeps it), so opening a panel changes neither the payload nor
        // the dirty snapshot.
        if (canonical(overrides) !== canonical(stored)) data.tool_overrides = overrides;
      }

      // The dead-MCP-override walk that stood here (data-mcp-override-source /
      // -field) had no producer left in js/ and is gone (M31 F4 L05c). The per-tool
      // toggles below still fill mcpOverrides.
      var mcpOverrides = {};

      // Per-tool checkbox toggles within each attached source. Each
      // checkbox carries `data-mcp-tool-toggle` (un-prefixed tool name)
      // and `data-mcp-source` (source name). The wrapping group element
      // carries `data-mcp-tool-mode={"allowlist"|"denylist"}` declared at
      // render time based on the agent's existing override shape.
      //
      // Mode semantics:
      //   - denylist (default for new attachments): collect un-checked
      //     tools into disabled_tools.
      //   - allowlist (when agent already has enabled_tools set): collect
      //     checked tools into enabled_tools.
      var toggleEls = editorEl.querySelectorAll('[data-mcp-tool-toggle][data-mcp-source]');
      var enabledBySource = {};
      var disabledBySource = {};
      var modeBySource = {};
      for (var ti = 0; ti < toggleEls.length; ti++) {
        var te = toggleEls[ti];
        var srcName = te.dataset.mcpSource;
        var tlName = te.dataset.mcpToolToggle;
        if (!srcName || !tlName) continue;
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


      return data;
    }

    // JSON with object keys sorted, so two override maps compare by content.
    function canonical(v) {
      if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
      if (v && typeof v === 'object') {
        return '{' + Object.keys(v).sort().map(function (k) {
          return JSON.stringify(k) + ':' + canonical(v[k]);
        }).join(',') + '}';
      }
      return JSON.stringify(v);
    }

    // The stored override keys the tool's panel flagged as no longer overridable.
    function deadFields(toolName) {
      var out = {};
      var panels = editorEl.querySelectorAll('[data-tool-override-panel]');
      for (var i = 0; i < panels.length; i++) {
        if (panels[i].getAttribute('data-tool-override-panel') !== toolName) continue;
        (panels[i].getAttribute('data-tool-override-dead') || '').split(' ').forEach(function (n) {
          if (n) out[n] = true;
        });
      }
      return out;
    }

    // M31 F4 L05c: the first override field whose value cannot be saved (a number
    // override that is not a whole number), read from the live controls, or null.
    // Kept apart from collectFormData, which stays pure (it also feeds checkDirty
    // and the snapshot). The Save paths call it right after collectFormData.
    // -> { tool, field, label, message, control } | null
    function blockingError() {
      var els = editorEl.querySelectorAll('[data-tool-override-tool][data-tool-override-field]');
      for (var i = 0; i < els.length; i++) {
        // An inherited field stores nothing, so it cannot block a Save.
        if (els[i].getAttribute('data-tool-override-state') === 'inherited') continue;
        var message = window.App.toolConfigFields.invalidMessage(els[i]);
        if (!message) continue;
        var label = els[i].labels && els[i].labels[0] ? els[i].labels[0].textContent : '';
        return {
          tool: els[i].dataset.toolOverrideTool,
          field: els[i].dataset.toolOverrideField,
          label: label || els[i].dataset.toolOverrideField,
          message: message,
          control: els[i]
        };
      }
      return null;
    }

    return {
      blockingError: blockingError,
      collectFormData: collectFormData,
      getFormSnapshot: getFormSnapshot,
      checkDirty: checkDirty
    };
  }

  window.App.studio.agentFormData = { create: create };
})();
