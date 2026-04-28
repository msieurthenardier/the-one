(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Renders the Tools section stub: a centered .empty-state with one-liner.
  // Future mission will replace this with MCP server + built-in tool config.
  function renderToolsStub(container) {
    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">Tools</h1>' +
      '</div>' +
      '<div class="empty-state" data-testid="studio-tools-stub">' +
        'MCP servers and built-in tools will be configured here in a future mission.' +
      '</div>';
  }

  window.App.studio.renderToolsStub = renderToolsStub;
})();
