// App.studio.renderKnowledgeTab — agent-editor Knowledge tab content (F5 leg 03).
//
// Stub one-liner. Distinct from the sidebar Knowledge section (managed via
// stub-knowledge.js) — this tab is the per-agent attach surface; the sidebar
// is the global KB inventory. Both are stubs in F5; future flights wire them.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderKnowledgeTab(panel) {
    panel.innerHTML = '';
    var div = document.createElement('div');
    div.className = 'empty-state';
    div.setAttribute('data-testid', 'agent-knowledge-tab-stub');
    div.textContent = 'Knowledge bases will be attached to this agent here in a future flight. Knowledge bases can be attached to multiple agents.';
    panel.appendChild(div);
  }

  window.App.studio.renderKnowledgeTab = renderKnowledgeTab;
})();
