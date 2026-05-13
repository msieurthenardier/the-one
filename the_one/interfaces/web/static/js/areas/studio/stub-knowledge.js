(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Renders the Knowledge section stub: a centered card with one-liner.
  // Emits .knowledge-stub-pane so the caller can test for its presence before
  // re-rendering (renderKnowledgeSection is idempotent). Future mission will
  // replace this with the KB CRUD surface.
  function renderKnowledgeStub(container) {
    container.innerHTML =
      '<div class="knowledge-stub-pane" data-testid="studio-knowledge-stub">' +
        '<h2>Knowledge</h2>' +
        '<p>Knowledge bases will be created and managed here in a future mission.</p>' +
        '<button class="btn btn-ghost" type="button" disabled>Add Knowledge Base</button>' +
      '</div>';
  }

  window.App.studio.renderKnowledgeStub = renderKnowledgeStub;
})();
