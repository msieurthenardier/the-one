(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Renders the Knowledge section stub: a centered .empty-state with one-liner.
  // Future mission will replace this with the KB CRUD surface.
  function renderKnowledgeStub(container) {
    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">Knowledge</h1>' +
      '</div>' +
      '<div class="empty-state" data-testid="studio-knowledge-stub">' +
        'Knowledge bases will be created and managed here in a future mission.' +
      '</div>';
  }

  window.App.studio.renderKnowledgeStub = renderKnowledgeStub;
})();
