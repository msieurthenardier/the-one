// App.studio.renderToolsTab — agent-editor Tools tab content (F5 leg 03).
//
// Two visually-grouped subsections:
//   1. "MCP tools" — stub one-liner.
//   2. "Built-in tools" — the existing 4-category checkbox UI lifted from the
//      pre-leg-03 monolithic editor (TOOL_CATEGORIES) verbatim.
//
// The checkbox state binds to enabled_tools / disabled_tools via the same
// data-tool selectors collectFormData reads — moving the checkboxes into a
// tab does NOT change the read shape (collectFormData queries by attribute
// regardless of DOM nesting).
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

    var html = '';

    // MCP subsection — stub.
    html += '<h3 class="section-title">MCP tools</h3>';
    html += '<div class="empty-state" data-testid="agent-mcp-tools-stub">' +
      'MCP servers will be configured in the Tools section, then attached here. Tools can be attached to multiple agents.' +
      '</div>';

    // Built-in subsection — checkbox UI carried verbatim from pre-leg-03.
    html += '<h3 class="section-title">Built-in tools</h3>';
    html += '<div class="tool-actions">' +
      '<button type="button" class="btn-outlined-cyan tool-select-all">All</button>' +
      '<button type="button" class="btn-outlined-cyan tool-select-none">None</button>' +
      '</div>';
    var catKeys = Object.keys(TOOL_CATEGORIES);
    for (var c = 0; c < catKeys.length; c++) {
      var cat = catKeys[c];
      var toolNames = TOOL_CATEGORIES[cat];
      html += '<div class="tool-group">' + escapeHtml(cat) + '</div>';
      for (var t = 0; t < toolNames.length; t++) {
        var tName = toolNames[t];
        var toolInfo = findTool(tName);
        var checked = enabledSet[tName] ? ' checked' : '';
        html += '<label class="tool-row">';
        html += '<input type="checkbox" class="tool-toggle" data-tool="' + escapeAttr(tName) + '"' + checked + ' />';
        html += '<span class="tool-switch"></span>';
        html += '<span class="tool-name">' + escapeHtml(tName) + '</span>';
        html += '<span class="tool-desc">' + escapeHtml(toolInfo ? toolInfo.description : '') + '</span>';
        html += '</label>';
      }
    }

    panel.innerHTML = html;

    // Wire select-all / select-none.
    var allBtn = panel.querySelector('.tool-select-all');
    var noneBtn = panel.querySelector('.tool-select-none');
    if (allBtn) allBtn.onclick = function () {
      var toggles = panel.querySelectorAll('.tool-toggle');
      for (var i = 0; i < toggles.length; i++) toggles[i].checked = true;
      if (callbacks.onChange) callbacks.onChange();
    };
    if (noneBtn) noneBtn.onclick = function () {
      var toggles = panel.querySelectorAll('.tool-toggle');
      for (var i = 0; i < toggles.length; i++) toggles[i].checked = false;
      if (callbacks.onChange) callbacks.onChange();
    };
  }

  window.App.studio.renderToolsTab = renderToolsTab;
})();
