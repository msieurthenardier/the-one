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

  var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'mock'];

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
        '<button class="btn-outlined-cyan new-entity-btn" type="button" data-testid="new-provider-btn">' +
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
      gridEl.innerHTML =
        '<div class="empty-canvas">' +
          '<div class="empty-canvas-inner admin-provider-empty">' +
            'No providers configured. Add one to get started.' +
          '</div>' +
        '</div>';
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
