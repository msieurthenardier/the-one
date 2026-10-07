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

    // Mission 08 F4 L2 — restructure to match the agent-editor MCPs tab
    // pattern: each TOOL_CATEGORIES key becomes a category tile (echoing
    // .mcp-source-tile), and each individual tool inside renders as a
    // tool tile (echoing .mcp-tool-toggle-label). The legacy per-tool
    // schema-override `<details>` panel is dropped from this view — the
    // saved per-agent override values still persist in JSON, but new
    // overrides cannot be set via UI here. Re-add path is captured in
    // Leg 02's functional-batch section.
    panel.innerHTML = '';

    // M07 F10 lazy-discovery copy (M17 F5 L1): convey the CAN-load semantics.
    // Enabling a built-in tool adds it to the set the agent is ALLOWED to
    // load; the agent loads a tool on demand during a run, not upfront — so an
    // enabled tool is one the agent *can* load, distinct from one it *has*
    // loaded this session. Tone mirrors the MCPs tab's "Expand to load tools…".
    // Rendered via createElement/textContent (no innerHTML — the F1 sink freeze).
    var intro = document.createElement('p');
    intro.className = 'section-description tools-tab-intro';
    intro.textContent =
      'Built-in tools the agent can load. Enabling a tool adds it to the set ' +
      'the agent is allowed to use — the agent loads each tool on demand during ' +
      'a run, not all at once. The count shows how many in a category are enabled.';
    panel.appendChild(intro);

    // Page-level All/None controls dropped in F4 L2 vibe — per-category
    // count badges and per-tool checkboxes are sufficient affordances.
    var listContainer = document.createElement('div');
    listContainer.className = 'tools-categories-list';
    panel.appendChild(listContainer);

    var catKeys = Object.keys(TOOL_CATEGORIES);
    for (var c = 0; c < catKeys.length; c++) {
      (function (cat) {
        var toolNames = TOOL_CATEGORIES[cat];
        var enabledCount = 0;
        for (var ec = 0; ec < toolNames.length; ec++) {
          if (enabledSet[toolNames[ec]]) enabledCount++;
        }

        var tile = document.createElement('div');
        tile.className = 'tools-category-tile';
        tile.setAttribute('data-category', cat);
        tile.setAttribute('aria-expanded', 'false');

        // Row 1: master toggle + category name + count badge.
        var row1 = document.createElement('div');
        row1.className = 'tools-category-tile-row1';

        // Master toggle — iOS-pill matching the MCP source-tile toggle.
        // Tristate visual via .indeterminate when 0 < enabled < total.
        // Click toggles every tool in the category to match the new state.
        var masterWrap = document.createElement('label');
        masterWrap.className = 'tools-category-tile-toggle mcp-source-tile-toggle';

        var masterCb = document.createElement('input');
        masterCb.type = 'checkbox';
        masterCb.className = 'tool-toggle';
        masterCb.setAttribute('data-category-master', cat);
        masterCb.setAttribute('aria-label', 'Enable all ' + cat + ' tools');
        masterWrap.appendChild(masterCb);

        var masterSwitch = document.createElement('span');
        masterSwitch.className = 'tool-switch';
        masterWrap.appendChild(masterSwitch);
        row1.appendChild(masterWrap);

        var nameSpan = document.createElement('span');
        nameSpan.className = 'tools-category-tile-name';
        nameSpan.textContent = cat;
        row1.appendChild(nameSpan);

        var countBadge = document.createElement('span');
        countBadge.className = 'tools-category-tile-count';
        countBadge.textContent = enabledCount + ' / ' + toolNames.length + ' enabled';
        row1.appendChild(countBadge);

        tile.appendChild(row1);

        // Set master-toggle initial state. Update happens via
        // _refreshCategoryCounts when individual tools change.
        if (enabledCount === toolNames.length) {
          masterCb.checked = true;
        } else if (enabledCount === 0) {
          masterCb.checked = false;
        } else {
          masterCb.indeterminate = true;
        }
        masterCb.addEventListener('change', function () {
          var newState = masterCb.checked;
          // After click, browser clears indeterminate. Set every non-disabled
          // tool checkbox to the new state.
          var checkboxes = tile.querySelectorAll('input[data-tool]');
          for (var ci = 0; ci < checkboxes.length; ci++) {
            if (checkboxes[ci].disabled) continue;
            checkboxes[ci].checked = newState;
          }
          if (callbacks.onChange) callbacks.onChange();
          _refreshCategoryCounts();
        });

        // Expand button.
        var expandBtn = document.createElement('button');
        expandBtn.type = 'button';
        expandBtn.className = 'tools-category-tile-expand-btn';
        expandBtn.setAttribute('aria-expanded', 'false');
        var expandLabel = document.createElement('span');
        expandLabel.innerHTML = '<strong>' + toolNames.length + '</strong> tool' +
          (toolNames.length === 1 ? '' : 's');
        expandBtn.appendChild(expandLabel);
        var chevron = document.createElement('span');
        chevron.className = 'tools-category-tile-chevron';
        chevron.textContent = '▸';
        expandBtn.appendChild(chevron);
        tile.appendChild(expandBtn);

        // Tools body — built up-front; hidden until expand.
        var toolsBody = document.createElement('div');
        toolsBody.className = 'tools-category-tile-tools';
        toolsBody.hidden = true;

        for (var ti = 0; ti < toolNames.length; ti++) {
          (function (tName) {
            var toolInfo = findTool(tName);
            var disabled = isDisabled(tName);

            // Each tool = a single `<details>` element. The summary IS the
            // row1 face (checkbox-label on the left + Overrides affordance
            // on the right); the body holds the override fields, lazy-loaded
            // on first open by wireOverridePanel. Per HTML spec, clicks on
            // a form-control descendant of `<summary>` do NOT toggle the
            // `<details>` — so the checkbox-label click toggles only the
            // checkbox; the Overrides affordance area (or any non-label
            // summary area) toggles the details.
            var tile = document.createElement('details');
            tile.className = 'tool-tile tool-row-overrides';
            tile.setAttribute('data-tool', tName);
            if (disabled) {
              tile.classList.add('tool-row-disabled');
              tile.title = 'Disabled by operator';
            }

            var summary = document.createElement('summary');
            summary.className = 'tool-tile-summary';

            // Left side: checkbox-label wrapping the checkbox + tool name +
            // description, all toggle-targeting the checkbox.
            var face = document.createElement('label');
            face.className = 'tool-tile-toggle-face';

            var cb = document.createElement('input');
            cb.type = 'checkbox';
            // No `.tool-toggle` class — that primitive is `display: none`
            // (designed for the iOS-pill pattern paired with `.tool-switch`).
            // We want a visible checkbox here; `.checkbox-primary` supplies
            // the styled box. studio.js's collectFormData query was widened
            // to `input[type="checkbox"][data-tool]` so this still
            // round-trips on save.
            cb.className = 'checkbox-primary';
            cb.checked = !!enabledSet[tName];
            cb.setAttribute('data-tool', tName);
            if (disabled) cb.disabled = true;
            cb.addEventListener('change', function () {
              if (callbacks.onChange) callbacks.onChange();
              _refreshCategoryCounts();
            });
            face.appendChild(cb);

            var textWrap = document.createElement('span');
            textWrap.className = 'mcp-tool-text';

            var nameInner = document.createElement('span');
            nameInner.className = 'mcp-tool-toggle-name';
            if (disabled) nameInner.classList.add('tool-name-strike');
            nameInner.textContent = tName;
            textWrap.appendChild(nameInner);

            var descText = toolInfo && toolInfo.description ? toolInfo.description : '';
            if (descText) {
              var descSpan = document.createElement('span');
              descSpan.className = 'mcp-tool-description';
              var truncated = descText.length > 100
                ? descText.slice(0, 100) + '…'
                : descText;
              descSpan.textContent = ' — ' + truncated;
              descSpan.title = descText;
              textWrap.appendChild(descSpan);
            }

            face.appendChild(textWrap);
            summary.appendChild(face);

            // Right side: Overrides affordance. Visual-only (the parent
            // <details> handles the actual open/close on summary click);
            // the click target IS the summary, the affordance is just the
            // visible chevron + label cue.
            if (!disabled) {
              var affordance = document.createElement('span');
              affordance.className = 'tool-tile-overrides-affordance';
              var aLabel = document.createElement('span');
              aLabel.textContent = 'Overrides';
              affordance.appendChild(aLabel);
              var aChevron = document.createElement('span');
              aChevron.className = 'chevron';
              aChevron.textContent = '▸';
              affordance.appendChild(aChevron);
              summary.appendChild(affordance);
            }

            tile.appendChild(summary);

            // Body — only for ENABLED (operator-allowed) tools.
            // CRITICAL: studio.js::collectFormData REBUILDS `tool_overrides`
            // from DOM on save; without this body rendering the override
            // fields on open, ANY existing override values get wiped to
            // `null` on next save. wireOverridePanel populates the body
            // with existing values on first toggle, and saved-but-untouched
            // overrides re-serialize on subsequent saves.
            if (!disabled) {
              var detailsBody = document.createElement('div');
              detailsBody.className = 'tool-row-overrides-body';
              var loadingP = document.createElement('p');
              loadingP.className = 'loading';
              loadingP.textContent = 'Loading…';
              detailsBody.appendChild(loadingP);
              tile.appendChild(detailsBody);
            }

            toolsBody.appendChild(tile);
          })(toolNames[ti]);
        }

        tile.appendChild(toolsBody);

        expandBtn.addEventListener('click', function () {
          var nextExpanded = expandBtn.getAttribute('aria-expanded') !== 'true';
          tile.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
          expandBtn.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
          toolsBody.hidden = !nextExpanded;
        });

        listContainer.appendChild(tile);
      })(catKeys[c]);
    }

    function _refreshCategoryCounts() {
      var tiles = panel.querySelectorAll('.tools-category-tile');
      for (var ti = 0; ti < tiles.length; ti++) {
        (function (t) {
          var cat = t.getAttribute('data-category');
          var toolNames = TOOL_CATEGORIES[cat] || [];
          var enabled = 0;
          for (var j = 0; j < toolNames.length; j++) {
            var cb = t.querySelector('input[data-tool="' + toolNames[j] + '"]');
            if (cb && cb.checked) enabled++;
          }
          var badge = t.querySelector('.tools-category-tile-count');
          if (badge) badge.textContent = enabled + ' / ' + toolNames.length + ' enabled';

          var master = t.querySelector('input[data-category-master]');
          if (master) {
            if (enabled === toolNames.length) {
              master.checked = true;
              master.indeterminate = false;
            } else if (enabled === 0) {
              master.checked = false;
              master.indeterminate = false;
            } else {
              master.checked = false;
              master.indeterminate = true;
            }
          }
        })(tiles[ti]);
      }
    }

    // Wire override-panel lazy-load handlers (F6 L5; preserved through F4 L2
    // restructure). Each `<details>`'s `toggle` event fires when the user
    // opens (or closes) the panel; the schema fetch is closure-cached in
    // studio.js so reopen-after-close is a cache hit.
    if (fetchToolSchema) {
      var overridePanels = panel.querySelectorAll('.tool-row-overrides');
      for (var p = 0; p < overridePanels.length; p++) {
        wireOverridePanel(overridePanels[p], agent, operatorConfigs, fetchToolSchema, callbacks);
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
