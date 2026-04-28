(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Renders the Knowledge section stub: a centered .empty-state with one-liner.
  // Future mission will replace this with the KB CRUD surface.
  function renderKnowledgeStub(container) {
    container.innerHTML = '';
    var empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.setAttribute('data-testid', 'studio-knowledge-stub');
    empty.textContent = 'Knowledge bases will be created and managed here in a future mission.';
    container.appendChild(empty);
  }

  window.App.studio.renderKnowledgeStub = renderKnowledgeStub;
})();
