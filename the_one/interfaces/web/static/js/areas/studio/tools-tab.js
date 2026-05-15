// App.studio.renderToolsTab — agent-editor Tools tab content (F5 leg 03 + F6 leg 05).
//
// Two visually-grouped subsections:
//   1. "MCP tools" — stub one-liner.
//   2. "Built-in tools" — 4-category checkbox UI; F6 leg 05 widened to:
//      - Surface operator-disabled tools with strikethrough name + dim row +
//        "Disabled by operator" tooltip + `disabled` HTML attr on checkbox.
//        Click is no-op; agent's prior on/off state preserved (NOT auto-stripped).
//      - Each ENABLED tool gets a `<details>` panel labeled "Narrow constraints"
//        that lazy-loads the tool's schema on first expand and renders typed
//        widgets per Narrow / NarrowSuperset / NarrowPrefix / Substitute marker.
//      - Save flows through studio.js::collectFormData walking
//        `[data-tool-override-tool][data-tool-override-field]` inputs into a
//        `tool_overrides: {tool_name: {field: value, ...}}` map.
//
// The checkbox state binds to enabled_tools / disabled_tools via the same
// data-tool selectors collectFormData reads — operator-disabled checkboxes
// still report `.checked` (HTML `disabled` only blocks user toggling, not
// property reads), so agent's prior state survives operator-disable cycles.
//
// callbacks:
//   - toolCategories: {category: [tool_name, ...]}
//   - allTools: [{name, description}, ...]
//   - onChange: () → void (dirty-tracking)
//   - disabledTools: Set<string> (operator-disabled tool names; F6 L5)
//   - operatorConfigs: {name: {enabled, config}} (operator's saved per-tool
//     configs — used as the ceiling for Narrow widgets) (F6 L5)
//   - fetchToolSchema: (name) → Promise<{name, description, enabled, config,
//     schema}> (lazy schema fetcher; closure-cached in studio.js) (F6 L5)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderToolsTab(panel, agent, callbacks) {
    callbacks = callbacks || {};
    var TOOL_CATEGORIES = callbacks.toolCategories || {};
    var allTools = callbacks.allTools || [];
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    // F6 L5 callbacks. Defaults keep the pre-L5 behavior intact when the
    // orchestrator hasn't passed them through (Knowledge tab refreshes,
    // empty-state flows, etc.).
    var disabledTools = callbacks.disabledTools || (new (window.Set || Object)());
    var operatorConfigs = callbacks.operatorConfigs || {};
    var fetchToolSchema = callbacks.fetchToolSchema || null;

    function isDisabled(name) {
      if (disabledTools && typeof disabledTools.has === 'function') {
        return disabledTools.has(name);
      }
      return false;
    }

    // Compute enabled set for the agent (mirrors pre-leg-03 logic).
    var cfg = agent || { enabled_tools: null, disabled_tools: [] };
    var enabledSet = {};
    for (var i = 0; i < allTools.length; i++) {
      var tn = allTools[i].name;
      if (cfg.enabled_tools !== null && cfg.enabled_tools !== undefined) {
        enabledSet[tn] = cfg.enabled_tools.indexOf(tn) >= 0;
      } else {
        enabledSet[tn] = (cfg.disabled_tools || []).indexOf(tn) < 0;
      }
    }

    function findTool(name) {
      for (var i = 0; i < allTools.length; i++) {
        if (allTools[i].name === name) return allTools[i];
      }
      return null;
    }

    // M10 L5.4 — compute enabled/total counts for the mono "TOOLS · N / M
    // enabled" header label. Counts mirror the `enabledSet` built above,
    // which reflects the agent's saved state (operator-disabled tools are
    // still counted in the denominator — they appear in the UI as off).
    var enabledCount = 0;
    var totalCount = allTools.length;
    for (var ti = 0; ti < allTools.length; ti++) {
      if (enabledSet[allTools[ti].name]) enabledCount++;
    }

    var html = '';

    // Mono uppercase header for the tools tab (M10 L5.4 — coord-style).
    html += '<div class="field-label tools-tab-head">' +
      '<span>TOOLS &middot; ' + enabledCount + ' / ' + totalCount + ' enabled</span>' +
      '<span class="field-hint">narrowed from defaults</span>' +
      '</div>';

    // The MCPs subsection moved to a sibling tab; the parent tab label
    // ("Built-in Tools") supplies the page-level header here, so this tab
    // now starts with category sections directly.
    html += '<div class="tool-actions">' +
      '<button type="button" class="btn-outlined-primary tool-select-all">All</button>' +
      '<button type="button" class="btn-outlined-primary tool-select-none">None</button>' +
      '</div>';
    var catKeys = Object.keys(TOOL_CATEGORIES);
    for (var c = 0; c < catKeys.length; c++) {
      var cat = catKeys[c];
      var toolNames = TOOL_CATEGORIES[cat];
      html += '<h2 class="section-title">' + escapeHtml(cat) + '</h2>';
      html += '<div class="tool-chip-grid">';
      for (var t = 0; t < toolNames.length; t++) {
        var tName = toolNames[t];
        var toolInfo = findTool(tName);
        var checked = enabledSet[tName] ? ' checked' : '';
        var disabled = isDisabled(tName);
        var rowClass = 'tool-row tool-chip-row' + (disabled ? ' tool-row-disabled' : '');
        var rowAttrs = '';
        if (disabled) rowAttrs = ' title="Disabled by operator"';
        // Append legacy `.tool-name` (and `.tool-name-strike` when locked)
        // to the chip itself — tests expect to locate by `.tool-name` and
        // assert the strike class on disabled rows.
        var chipClass = 'tool-chip tool-name' + (enabledSet[tName] ? ' on' : ' off') +
          (disabled ? ' tool-chip-locked tool-name-strike' : '');
        var chipTitle = toolInfo && toolInfo.description ? toolInfo.description : tName;
        html += '<label class="' + rowClass + '"' + rowAttrs + '>';
        // Hidden checkbox carries the source-of-truth state for
        // collectFormData. Visually replaced by the .tool-chip button.
        html += '<input type="checkbox" class="tool-toggle" data-tool="' + escapeAttr(tName) + '"' + checked + (disabled ? ' disabled' : '') + ' aria-hidden="true" tabindex="-1" />';
        html += '<button type="button" class="' + chipClass + '" data-tool="' + escapeAttr(tName) +
          '" aria-pressed="' + (enabledSet[tName] ? 'true' : 'false') + '" title="' + escapeAttr(chipTitle) + '"' +
          (disabled ? ' disabled' : '') + '>' + escapeHtml(tName) + '</button>';
        // Keep tool description in the DOM (sr-only) for screen-reader
        // context — chip surface alone is too terse.
        html += '<span class="sr-only tool-desc">' + escapeHtml(toolInfo ? toolInfo.description : '') + '</span>';
        html += '</label>';
        // Override panel — only for ENABLED tools (operator-disabled tools
        // have no narrowing surface relevant). Collapsed by default; lazy-
        // loads schema on first open. Agent's existing tool_overrides[name]
        // entry survives in saved JSON regardless of panel state.
        if (!disabled) {
          html += '<details class="tool-row-overrides" data-tool="' + escapeAttr(tName) + '">';
          html += '<summary>Details</summary>';
          html += '<div class="tool-row-overrides-body">';
          html += '<p class="loading">Loading…</p>';
          html += '</div>';
          html += '</details>';
        }
      }
      html += '</div>';
    }

    panel.innerHTML = html;

    // Wire chip buttons → toggle the hidden checkbox → re-style. The label
    // wrapper would also toggle the checkbox via native label-for semantics
    // even without a 'for' attribute (clicking a label toggles its first
    // descendant checkbox), so the explicit button handler stops the
    // default label propagation and drives toggle state itself.
    function syncChipState(chip, isOn) {
      if (isOn) {
        chip.classList.add('on');
        chip.classList.remove('off');
      } else {
        chip.classList.add('off');
        chip.classList.remove('on');
      }
      chip.setAttribute('aria-pressed', isOn ? 'true' : 'false');
    }
    var chips = panel.querySelectorAll('.tool-chip[data-tool]');
    for (var ch = 0; ch < chips.length; ch++) {
      (function (chip) {
        chip.addEventListener('click', function (evt) {
          // The chip lives inside a <label>; without preventDefault the
          // label's implicit-for would also flip the checkbox, doubling
          // the state change. preventDefault keeps us in sole control.
          evt.preventDefault();
          if (chip.disabled) return;
          var name = chip.dataset.tool;
          var toggle = panel.querySelector('.tool-toggle[data-tool="' + name + '"]');
          if (!toggle || toggle.disabled) return;
          toggle.checked = !toggle.checked;
          syncChipState(chip, toggle.checked);
          if (callbacks.onChange) callbacks.onChange();
        });
      })(chips[ch]);
    }
    // Expose a re-sync entry point so select-all / select-none (which flip
    // the underlying checkboxes) can refresh chip styling.
    panel._toolsChipResync = function () {
      var allChips = panel.querySelectorAll('.tool-chip[data-tool]');
      for (var i = 0; i < allChips.length; i++) {
        var name = allChips[i].dataset.tool;
        var toggle = panel.querySelector('.tool-toggle[data-tool="' + name + '"]');
        if (!toggle) continue;
        syncChipState(allChips[i], toggle.checked);
      }
    };

    // Wire select-all / select-none — operator-disabled checkboxes are
    // skipped (HTML `disabled` blocks programmatic `checked = true` from
    // sticking on user-visible form state, but `.checked = ` does set the
    // property; we explicitly skip them so the operator's intent dominates).
    var allBtn = panel.querySelector('.tool-select-all');
    var noneBtn = panel.querySelector('.tool-select-none');
    if (allBtn) allBtn.onclick = function () {
      var toggles = panel.querySelectorAll('.tool-toggle');
      for (var i = 0; i < toggles.length; i++) {
        if (toggles[i].disabled) continue;
        toggles[i].checked = true;
      }
      if (panel._toolsChipResync) panel._toolsChipResync();
      if (callbacks.onChange) callbacks.onChange();
    };
    if (noneBtn) noneBtn.onclick = function () {
      var toggles = panel.querySelectorAll('.tool-toggle');
      for (var i = 0; i < toggles.length; i++) {
        if (toggles[i].disabled) continue;
        toggles[i].checked = false;
      }
      if (panel._toolsChipResync) panel._toolsChipResync();
      if (callbacks.onChange) callbacks.onChange();
    };

    // Wire override-panel lazy-load handlers (F6 L5). Each `<details>`'s
    // `toggle` event fires when the user opens (or closes) the panel; we
    // gate on `details.open === true && !details.dataset.loaded`. The
    // schema fetch is closure-cached in studio.js, so reopen-after-close
    // is a cache hit.
    if (fetchToolSchema) {
      var panels = panel.querySelectorAll('.tool-row-overrides');
      for (var p = 0; p < panels.length; p++) {
        wireOverridePanel(panels[p], agent, operatorConfigs, fetchToolSchema, callbacks);
      }
    }
  }

  // Lazy-load + render override fields for one <details> panel.
  function wireOverridePanel(detailsEl, agent, operatorConfigs, fetchToolSchema, callbacks) {
    detailsEl.addEventListener('toggle', function () {
      if (!detailsEl.open) return;
      if (detailsEl.dataset.loaded === 'true') return;
      detailsEl.dataset.loaded = 'true';
      var name = detailsEl.dataset.tool;
      var helpers = window.App.adminFormHelpers;
      var bodyEl = detailsEl.querySelector('.tool-row-overrides-body');

      fetchToolSchema(name).then(function (detail) {
        var schema = (detail && detail.schema) || {};
        // Operator config falls back to {} when the tool has no saved row;
        // each field's operator value falls back to prop['default'] then.
        var operatorRow = operatorConfigs[name] || {};
        var operatorConfig = operatorRow.config || {};
        var agentOverride = ((agent && agent.tool_overrides) || {})[name] || {};
        var fieldNames = Object.keys(schema.properties || {});

        var html = '';
        var rendered = 0;
        for (var i = 0; i < fieldNames.length; i++) {
          var fname = fieldNames[i];
          var prop = schema.properties[fname];
          var marker = prop.x_marker;
          // Skip un-marked fields entirely (operator-only — agent override
          // would be rejected by resolver). Boolean fields render
          // unconditionally.
          if (!marker && prop.type !== 'boolean') {
            // Surface drift visibly when the agent has a stale override
            // for a now-unmarked field.
            if (fname in agentOverride) {
              // eslint-disable-next-line no-console
              console.warn('Agent "%s" has an override on tool "%s" field "%s" but the schema no longer marks that field as overridable; the resolver will reject this.', (agent && agent.name) || '?', name, fname);
            }
            continue;
          }
          var operatorVal = (fname in operatorConfig) ? operatorConfig[fname] : prop['default'];
          var agentVal = (fname in agentOverride) ? agentOverride[fname] : null;
          // For booleans/non-Narrow widgets in agent mode, use agent's
          // saved value if set, else operator's value as the seed (so
          // toggles reflect the inherited baseline).
          if (agentVal === null) {
            // For Substitute fields, the agent has no inherited value —
            // start blank.
            if (marker === 'Substitute') {
              agentVal = '';
            } else if (marker === 'NarrowSuperset' && Array.isArray(operatorVal)) {
              // The renderer takes operator's items + agent's additions;
              // pre-fill with operator's items as the union baseline.
              agentVal = operatorVal.slice();
            } else {
              agentVal = operatorVal;
            }
          }
          html += helpers.renderField(fname, prop, agentVal, {
            mode: 'agent',
            operatorValue: operatorVal,
            attrPrefix: 'data-tool-override-field',
            toolName: name
          });
          rendered++;
        }
        if (rendered === 0) {
          bodyEl.innerHTML = '<p class="empty-state">No constraints to narrow.</p>';
          return;
        }
        bodyEl.innerHTML = html;
        // Wire chip-list editors (delegated handlers per editor element).
        var chipEditors = bodyEl.querySelectorAll('.chip-list-editor');
        for (var ce = 0; ce < chipEditors.length; ce++) {
          helpers.wireChipListEditor(chipEditors[ce], {
            onChange: function () { if (callbacks.onChange) callbacks.onChange(); }
          });
        }
        // Dirty-tracking: every override input fires onChange on change/input.
        var inputs = bodyEl.querySelectorAll('input[data-tool-override-field], select[data-tool-override-field]');
        for (var ii = 0; ii < inputs.length; ii++) {
          inputs[ii].addEventListener('change', function () {
            if (callbacks.onChange) callbacks.onChange();
          });
          inputs[ii].addEventListener('input', function () {
            if (callbacks.onChange) callbacks.onChange();
          });
        }
      }).catch(function () {
        bodyEl.innerHTML = '<p class="error">Failed to load schema.</p>';
        // Allow retry on next open by clearing the loaded flag.
        detailsEl.dataset.loaded = 'false';
      });
    });
  }

  window.App.studio.renderToolsTab = renderToolsTab;
})();
