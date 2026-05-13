(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Renders the MCP Servers page-header + tile grid (Studio nav).
  // Originally placed in admin nav (M07 F1 L5); relocated to studio post-F2
  // retrofit because MCP sources are user-managed entities, not system
  // settings. App.studio.* namespace; consumed by studio.js.
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

  // Holograph shape: container is already the .mcp-sources-grid div (CSS grid
  // 3-column card layout). The page-header with New button is in .area-header
  // (rendered by studio.js). This function populates the grid with
  // .mcp-source-card elements, or the loading / empty states.
  function renderMcpServersGrid(container, mcpSources, callbacks) {
    callbacks = callbacks || {};
    var onSelectMcpSource = callbacks.onSelectMcpSource || function () {};
    var onCreateMcpSource = callbacks.onCreateMcpSource || function () {};
    var selectedId = callbacks.selectedId || null;

    if (mcpSources === null || mcpSources === undefined) {
      // Loading state — caller will re-invoke with populated array
      container.innerHTML = '<div class="admin-loading">Loading MCP servers…</div>';
      return;
    }

    if (mcpSources.length === 0) {
      var emptyWrap = document.createElement('div');
      emptyWrap.className = 'empty-canvas';
      var emptyInner = document.createElement('div');
      emptyInner.className = 'empty-canvas-inner admin-provider-empty';
      emptyInner.setAttribute('data-testid', 'studio-mcp-empty');
      var emptyMsg = document.createElement('div');
      emptyMsg.textContent = 'No MCP servers configured. Add one to get started.';
      emptyInner.appendChild(emptyMsg);
      var emptyBtn = document.createElement('button');
      emptyBtn.className = 'btn btn-primary';
      emptyBtn.type = 'button';
      emptyBtn.setAttribute('data-testid', 'new-mcp-source-btn-empty');
      emptyBtn.textContent = 'New MCP Server';
      emptyBtn.addEventListener('click', function () { onCreateMcpSource(); });
      emptyInner.appendChild(emptyBtn);
      emptyWrap.appendChild(emptyInner);
      container.innerHTML = '';
      container.appendChild(emptyWrap);
      return;
    }

    container.innerHTML = '';
    for (var i = 0; i < mcpSources.length; i++) {
      (function (s) {
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

        var cardEl = document.createElement('div');
        cardEl.className = 'mcp-source-card' + (isActive ? ' selected' : '');
        cardEl.setAttribute('role', 'option');
        cardEl.setAttribute('tabindex', '0');
        cardEl.setAttribute('data-testid', 'mcp-source-card');
        cardEl.dataset.id = s.id;
        cardEl.setAttribute('aria-selected', isActive ? 'true' : 'false');

        var headEl = document.createElement('div');
        headEl.className = 'mcp-source-head';

        var badgeEl = document.createElement('span');
        badgeEl.className = 'admin-mcp-badge admin-mcp-badge--' + typeSuffix;
        badgeEl.textContent = s.type;
        headEl.appendChild(badgeEl);

        var nameEl = document.createElement('span');
        nameEl.className = 'agent-card-title';
        nameEl.textContent = s.name;
        headEl.appendChild(nameEl);

        cardEl.appendChild(headEl);

        var bodyEl = document.createElement('div');
        bodyEl.className = 'mcp-source-body';
        bodyEl.textContent = displayMeta;
        cardEl.appendChild(bodyEl);

        cardEl.addEventListener('click', function () {
          var id = cardEl.dataset.id;
          if (id) onSelectMcpSource(id);
        });
        cardEl.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            var id = cardEl.dataset.id;
            if (id) onSelectMcpSource(id);
          }
        });

        container.appendChild(cardEl);
      })(mcpSources[i]);
    }
  }

  window.App.studio.renderMcpServersGrid = renderMcpServersGrid;
})();
