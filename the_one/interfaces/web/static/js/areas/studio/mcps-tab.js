// App.studio.renderMcpsTab — agent-editor MCPs tab (stub).
//
// Per-agent MCP-server attach surface. Currently a one-line stub mirroring
// renderKnowledgeTab; a future flight will replace this with the real
// attach UI. Distinct from any future sidebar MCP inventory section (which
// would be the global MCP source list, not per-agent attachment).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderMcpsTab(panel) {
    panel.innerHTML = '';
    var div = document.createElement('div');
    div.className = 'empty-state';
    div.setAttribute('data-testid', 'agent-mcps-tab-stub');
    div.textContent = 'MCP servers will be attached to this agent here in a future flight.';
    panel.appendChild(div);
  }

  window.App.studio.renderMcpsTab = renderMcpsTab;
})();
