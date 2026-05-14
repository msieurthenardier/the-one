(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // L4.3 — Studio · Knowledge empty state (bracket-framed headline + CTA).
  // Replaces the M08 inline stub card with the M10 Holograph empty body.
  //
  // Mounts directly into #sub-knowledge (the Studio top-level Knowledge
  // sub-block). The .studio-empty wrapper + .studio-empty-simple modifier
  // give the body a narrower, centered focal — distinct from the Agents
  // empty state's left-rail + focal grid.
  //
  // Test contract:
  //   data-testid="studio-knowledge-stub" — preserved from the M08 stub so
  //     existing nav-routing tests (test_flow_studio_navigation,
  //     test_flow_hash_routing, test_flow_dirty_confirm) keep passing.
  //   .brack:has-text('No knowledge bases yet') — used by L4.3 empty-state
  //     test in test_studio_empty_states.py.
  function renderKnowledgeStub(container) {
    while (container.firstChild) container.removeChild(container.firstChild);

    var wrap = document.createElement('div');
    wrap.className = 'studio-empty studio-empty-simple knowledge-stub-pane';
    wrap.setAttribute('data-testid', 'studio-knowledge-stub');

    var brack = document.createElement('div');
    brack.className = 'brack';
    var brackTitle = document.createElement('h2');
    brackTitle.className = 'brack-title';
    brackTitle.textContent = 'No knowledge bases yet.';
    brack.appendChild(brackTitle);
    var brackSub = document.createElement('p');
    brackSub.className = 'brack-sub';
    brackSub.textContent =
      'Knowledge is searchable content an agent can cite. ' +
      'Add markdown, web pages, or PDF excerpts; the agent calls a search tool to retrieve relevant chunks.';
    brack.appendChild(brackSub);
    wrap.appendChild(brack);

    var ctas = document.createElement('div');
    ctas.className = 'studio-empty-ctas';
    var ctaNew = document.createElement('button');
    ctaNew.type = 'button';
    ctaNew.className = 'btn-mono';
    ctaNew.setAttribute('data-action', 'new-knowledge');
    ctaNew.setAttribute('data-testid', 'studio-empty-new-knowledge');
    ctaNew.textContent = '+ NEW KNOWLEDGE BASE';
    // No create-knowledge flow exists yet (the Knowledge surface is a stub
    // until a future mission lands KB CRUD). Wire a console.log placeholder
    // so the click is a no-op rather than a dead handler.
    ctaNew.addEventListener('click', function () {
      if (window.console && console.log) {
        console.log('TODO: implement new-knowledge flow');
      }
    });
    ctas.appendChild(ctaNew);
    wrap.appendChild(ctas);

    container.appendChild(wrap);
  }

  window.App.studio.renderKnowledgeStub = renderKnowledgeStub;
})();
