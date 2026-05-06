(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Renders the MCP Servers page-header + tile grid.
  //
  // Filename note: this file is `mcp-servers-grid.js` (plural servers,
  // matching the user-facing label "MCP Servers"); the URL category and
  // most JS identifiers use `mcp-sources` / `mcpSource` (the technical
  // entity name from the API path /api/mcp-sources). The asymmetry is
  // deliberate — UI label vs storage entity.
  //
  // Tile DOM (mirrors providers-grid.js):
  //   <button class="entity-tile mcp-source-tile"
  //           data-testid="mcp-source-card"
  //           data-id="{mcpSource.id}"
  //           aria-selected="{true|false}">
  //     <span class="entity-tile-badge admin-mcp-badge admin-mcp-badge--{type}">{type}</span>
  //     <span class="entity-tile-name">{name}</span>
  //     <span class="entity-tile-meta">{command-or-url || '—'}</span>
  //   </button>

  // KEEP IN SYNC with the transport literals in `_validate_mcp_source_config`
  // in api.py and the `/api/mcp-sources/types` endpoint — three sites to
  // update if a new transport literal is added (single-source-of-truth
  // refactor is a future cleanup).
  var KNOWN_TRANSPORT_BADGES = ['stdio', 'streamable-http'];

  function renderMcpServersGrid(container, mcpSources, callbacks) {
    callbacks = callbacks || {};
    var onSelectMcpSource = callbacks.onSelectMcpSource || function () {};
    var onCreateMcpSource = callbacks.onCreateMcpSource || function () {};
    var selectedId = callbacks.selectedId || null;

    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;

    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">MCP Servers</h1>' +
        // Header CTA renders icon-only at rest; expands on hover. CSS hides
        // it entirely when the grid below is empty, deferring the affordance
        // to the empty-canvas's centered CTA.
        '<button class="new-entity-btn" type="button" data-testid="new-mcp-source-btn" aria-label="New MCP server">' +
          window.App.icon('square-pen') + '<span>New MCP Server</span>' +
        '</button>' +
      '</div>' +
      '<div class="entity-tile-grid" role="listbox" aria-label="MCP servers">' +
        '<div class="admin-loading">Loading MCP servers…</div>' +
      '</div>';

    var newMcpBtn = container.querySelector('.new-entity-btn');
    newMcpBtn.addEventListener('click', function () { onCreateMcpSource(); });

    var gridEl = container.querySelector('.entity-tile-grid');
    if (mcpSources === null || mcpSources === undefined) {
      // Loading state — caller will re-invoke with populated array
      return;
    }

    if (mcpSources.length === 0) {
      gridEl.innerHTML =
        '<div class="empty-canvas">' +
          '<div class="empty-canvas-inner admin-provider-empty">' +
            '<div>No MCP servers configured. Add one to get started.</div>' +
            '<button class="new-entity-btn is-expanded" type="button" data-testid="new-mcp-source-btn-empty">' +
              window.App.icon('square-pen') + '<span>New MCP Server</span>' +
            '</button>' +
          '</div>' +
        '</div>';
      var emptyBtn = gridEl.querySelector('[data-testid="new-mcp-source-btn-empty"]');
      emptyBtn.addEventListener('click', function () { onCreateMcpSource(); });
      return;
    }

    var html = '';
    for (var i = 0; i < mcpSources.length; i++) {
      var s = mcpSources[i];
      var typeSuffix = KNOWN_TRANSPORT_BADGES.indexOf(s.type) >= 0 ? s.type : 'unknown';
      var displayMeta;
      if (s.type === 'stdio') {
        displayMeta = (s.config && s.config.command) ? s.config.command : '—';
      } else if (s.type === 'streamable-http') {
        displayMeta = (s.config && s.config.url) ? s.config.url : '—';
      } else {
        displayMeta = '—';
      }
      var isActive = selectedId === s.id;
      html +=
        '<button class="entity-tile mcp-source-tile" type="button" role="option" ' +
            'data-testid="mcp-source-card" data-id="' + escapeAttr(s.id) + '" ' +
            'aria-selected="' + (isActive ? 'true' : 'false') + '">' +
          '<span class="entity-tile-badge admin-mcp-badge admin-mcp-badge--' +
            escapeAttr(typeSuffix) + '">' + escapeHtml(s.type) + '</span>' +
          '<span class="entity-tile-name">' + escapeHtml(s.name) + '</span>' +
          '<span class="entity-tile-meta">' + escapeHtml(displayMeta) + '</span>' +
        '</button>';
    }
    gridEl.innerHTML = html;

    var tiles = gridEl.querySelectorAll('.mcp-source-tile');
    for (var t = 0; t < tiles.length; t++) {
      (function (tileEl) {
        tileEl.addEventListener('click', function () {
          var id = tileEl.dataset.id;
          if (id) onSelectMcpSource(id);
        });
      })(tiles[t]);
    }
  }

  window.App.admin.renderMcpServersGrid = renderMcpServersGrid;
})();
