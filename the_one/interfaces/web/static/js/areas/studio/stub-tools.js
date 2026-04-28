(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Renders the Tools section stub: a centered .empty-state with one-liner.
  // Future mission will replace this with MCP server + built-in tool config.
  function renderToolsStub(container) {
    container.innerHTML = '';
    var empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.setAttribute('data-testid', 'studio-tools-stub');
    empty.textContent = 'MCP servers and built-in tools will be configured here in a future mission.';
    container.appendChild(empty);
  }

  window.App.studio.renderToolsStub = renderToolsStub;
})();
