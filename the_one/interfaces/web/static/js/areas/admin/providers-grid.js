(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Renders the LLM Providers page-header + tile grid.
  //
  // Tile DOM (post-leg-02 canonical):
  //   <button class="entity-tile provider-tile"
  //           data-testid="provider-card"
  //           data-id="{provider.id}"
  //           aria-selected="{true|false}">
  //     <span class="entity-tile-badge admin-provider-badge admin-provider-badge--{type}">{type}</span>
  //     <span class="entity-tile-name">{name}</span>
  //     <span class="entity-tile-meta">{base_url || '—'}</span>
  //   </button>
  //
  // The active tile (when an editor is open for that id) carries
  // aria-selected="true"; others carry aria-selected="false".

  var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'mock', 'openrouter'];

  // L4.4 — provider-type card definitions for the empty-state 4-card grid.
  // Anthropic is RECOMMENDED (accent border + accent eyebrow); the other
  // three carry their category label (CLOUD / CLOUD / LOCAL) in muted mono.
  // Clicking a card opens the existing provider-editor pre-targeted to that
  // type via onCreateProvider(type).
  var PROVIDER_TYPE_CARDS = [
    { id: 'anthropic',         name: 'Anthropic',         cat: 'RECOMMENDED', desc: 'Claude family · API key', recommended: true },
    { id: 'openai',            name: 'OpenAI',            cat: 'CLOUD',       desc: 'GPT family · API key',    recommended: false },
    { id: 'openai-compatible', name: 'OpenAI-compatible', cat: 'CLOUD',       desc: 'Together, Groq, etc.',    recommended: false },
    { id: 'ollama',            name: 'Ollama',            cat: 'LOCAL',       desc: 'Self-hosted · no key',    recommended: false }
  ];

  // Builds the 4-card provider-type grid into `gridEl` (replaces any existing
  // children). Each card invokes `onPickType(type)` on click. Built via
  // createElement / textContent (security hook bans innerHTML for dynamic
  // strings; labels here are literal but we keep the pattern uniform).
  function renderProvidersEmpty(gridEl, onPickType) {
    while (gridEl.firstChild) gridEl.removeChild(gridEl.firstChild);
    var typeGrid = document.createElement('div');
    typeGrid.className = 'provider-type-grid';
    typeGrid.setAttribute('data-testid', 'provider-type-grid');

    for (var i = 0; i < PROVIDER_TYPE_CARDS.length; i++) {
      var c = PROVIDER_TYPE_CARDS[i];
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'provider-type-card' + (c.recommended ? ' recommended' : '');
      btn.dataset.testid = 'provider-type-card';
      btn.dataset.providerType = c.id;
      btn.setAttribute('aria-label', 'Create ' + c.name + ' provider');

      var cat = document.createElement('div');
      cat.className = 'provider-type-cat';
      cat.textContent = c.cat;
      btn.appendChild(cat);

      var nm = document.createElement('div');
      nm.className = 'provider-type-name';
      nm.textContent = c.name;
      btn.appendChild(nm);

      var ds = document.createElement('div');
      ds.className = 'provider-type-desc';
      ds.textContent = c.desc;
      btn.appendChild(ds);

      (function (cardEl) {
        cardEl.addEventListener('click', function () {
          onPickType(cardEl.dataset.providerType);
        });
      })(btn);

      typeGrid.appendChild(btn);
    }
    gridEl.appendChild(typeGrid);
  }

  function renderProvidersGrid(container, providers, callbacks) {
    callbacks = callbacks || {};
    var onSelectProvider = callbacks.onSelectProvider || function () {};
    var onCreateProvider = callbacks.onCreateProvider || function () {};
    var selectedId = callbacks.selectedId || null;

    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;

    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">LLM Providers</h1>' +
        // Header CTA renders icon-only at rest; expands on hover. CSS hides
        // it entirely when the grid below is empty, deferring the affordance
        // to the empty-canvas's centered CTA.
        '<button class="new-entity-btn" type="button" data-testid="new-provider-btn" aria-label="New provider">' +
          window.App.icon('square-pen') + '<span>New Provider</span>' +
        '</button>' +
      '</div>' +
      '<div class="entity-tile-grid" role="listbox" aria-label="LLM providers">' +
        '<div class="admin-loading">Loading providers…</div>' +
      '</div>';

    var newProviderBtn = container.querySelector('.new-entity-btn');
    newProviderBtn.addEventListener('click', function () { onCreateProvider(); });

    var gridEl = container.querySelector('.entity-tile-grid');
    if (providers === null || providers === undefined) {
      // Loading state — caller will re-invoke with populated array
      return;
    }

    if (providers.length === 0) {
      // L4.4 — 4-card provider-type grid replaces the old "No providers
      // configured…" canvas. Each card preselects its type in the editor.
      renderProvidersEmpty(gridEl, function (type) { onCreateProvider(type); });
      return;
    }

    var html = '';
    for (var i = 0; i < providers.length; i++) {
      var p = providers[i];
      var typeSuffix = KNOWN_BADGE_TYPES.indexOf(p.type) >= 0 ? p.type : 'unknown';
      var displayUrl = p.base_url ? p.base_url : '—';
      var isActive = selectedId === p.id;
      html +=
        '<button class="entity-tile provider-tile" type="button" role="option" ' +
            'data-testid="provider-card" data-id="' + escapeAttr(p.id) + '" ' +
            'aria-selected="' + (isActive ? 'true' : 'false') + '">' +
          '<span class="entity-tile-badge admin-provider-badge admin-provider-badge--' +
            escapeAttr(typeSuffix) + '">' + escapeHtml(p.type) + '</span>' +
          '<span class="entity-tile-name">' + escapeHtml(p.name) + '</span>' +
          '<span class="entity-tile-meta">' + escapeHtml(displayUrl) + '</span>' +
        '</button>';
    }
    gridEl.innerHTML = html;

    var tiles = gridEl.querySelectorAll('.provider-tile');
    for (var t = 0; t < tiles.length; t++) {
      (function (tileEl) {
        tileEl.addEventListener('click', function () {
          var id = tileEl.dataset.id;
          if (id) onSelectProvider(id);
        });
      })(tiles[t]);
    }
  }

  window.App.admin.renderProvidersGrid = renderProvidersGrid;
})();
