(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Renders the Connector Accounts page-header + tile grid (Studio nav).
  // Mirrors mcp-servers-grid.js's structure; the section was placed in
  // Studio (not Admin) because connector accounts are user-managed
  // identities (operator may have 3 Discord bots, 2 Slack workspace apps)
  // — a structural match to MCP sources, not LLM providers. See the
  // flight's "Studio placement, not Admin" design decision.
  //
  // Tile DOM:
  //   <button class="entity-tile connector-account-tile"
  //           data-testid="connector-account-card"
  //           data-id="{account.id}"
  //           aria-selected="{true|false}">
  //     <span class="entity-tile-badge admin-connector-badge admin-connector-badge--{type}">{type}</span>
  //     <span class="entity-tile-name">{name}</span>
  //     <span class="entity-tile-meta">—</span>
  //   </button>
  //
  // The `—` meta line is deliberate: connectors have no transport-config
  // equivalent until per-platform configs ship in Flights 8/9. The badge
  // CSS classes (`admin-connector-badge`, `admin-connector-badge--{type}`)
  // are present-as-future-hooks; no CSS rule needs to land until a real
  // type wants a distinct color.

  // KEEP IN SYNC with the type literals exposed by
  // `/api/connector-accounts/types`. The list starts empty in production
  // (no plugins register a real type yet — Flight 8 will add Discord).
  // Mirrors KNOWN_TRANSPORT_BADGES in mcp-servers-grid.js.
  var KNOWN_CONNECTOR_BADGES = [];

  function renderConnectorAccountsGrid(container, accounts, callbacks) {
    callbacks = callbacks || {};
    var onSelectConnectorAccount = callbacks.onSelectConnectorAccount || function () {};
    var onCreateConnectorAccount = callbacks.onCreateConnectorAccount || function () {};
    var selectedId = callbacks.selectedId || null;

    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;

    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">Connectors</h1>' +
        // Header CTA renders icon-only at rest; expands on hover. CSS hides
        // it entirely when the grid below is empty, deferring the affordance
        // to the empty-canvas's centered CTA.
        '<button class="new-entity-btn" type="button" data-testid="new-connector-account-btn" aria-label="New connector">' +
          window.App.icon('square-pen') + '<span>New Connector</span>' +
        '</button>' +
      '</div>' +
      '<div class="entity-tile-grid" role="listbox" aria-label="Connectors">' +
        '<div class="admin-loading">Loading connectors…</div>' +
      '</div>';

    var newBtn = container.querySelector('.new-entity-btn');
    newBtn.addEventListener('click', function () { onCreateConnectorAccount(); });

    var gridEl = container.querySelector('.entity-tile-grid');
    if (accounts === null || accounts === undefined) {
      // Loading state — caller will re-invoke with populated array
      return;
    }

    if (accounts.length === 0) {
      gridEl.innerHTML =
        '<div class="empty-canvas">' +
          '<div class="empty-canvas-inner admin-provider-empty">' +
            '<div>No connectors configured.</div>' +
            '<div class="empty-canvas-secondary">No connector types registered yet — Flight 8 will add Discord.</div>' +
            '<button class="new-entity-btn is-expanded" type="button" data-testid="new-connector-account-btn-empty">' +
              window.App.icon('square-pen') + '<span>New Connector</span>' +
            '</button>' +
          '</div>' +
        '</div>';
      var emptyBtn = gridEl.querySelector('[data-testid="new-connector-account-btn-empty"]');
      emptyBtn.addEventListener('click', function () { onCreateConnectorAccount(); });
      return;
    }

    var html = '';
    for (var i = 0; i < accounts.length; i++) {
      var a = accounts[i];
      var typeSuffix = KNOWN_CONNECTOR_BADGES.indexOf(a.type) >= 0 ? a.type : 'unknown';
      var isActive = selectedId === a.id;
      // M11 F9 L5 — agent-count badge replaces the `—` placeholder.
      // Field comes from the GET /api/connector-accounts response
      // (server-side computed). Defaults to 0 when absent so older
      // bundled servers continue to render cleanly.
      var attachedCount = (typeof a.attached_agents_count === 'number')
        ? a.attached_agents_count : 0;
      var metaText = attachedCount === 0
        ? 'No agents'
        : (attachedCount + ' agent' + (attachedCount === 1 ? '' : 's'));
      html +=
        '<button class="entity-tile connector-account-tile" type="button" role="option" ' +
            'data-testid="connector-account-card" data-id="' + escapeAttr(a.id) + '" ' +
            'aria-selected="' + (isActive ? 'true' : 'false') + '">' +
          '<span class="entity-tile-badge admin-connector-badge admin-connector-badge--' +
            escapeAttr(typeSuffix) + '">' + escapeHtml(a.type) + '</span>' +
          '<span class="entity-tile-name">' + escapeHtml(a.name) + '</span>' +
          '<span class="entity-tile-meta">' + escapeHtml(metaText) + '</span>' +
        '</button>';
    }
    gridEl.innerHTML = html;

    var tiles = gridEl.querySelectorAll('.connector-account-tile');
    for (var t = 0; t < tiles.length; t++) {
      (function (tileEl) {
        tileEl.addEventListener('click', function () {
          var id = tileEl.dataset.id;
          if (id) onSelectConnectorAccount(id);
        });
      })(tiles[t]);
    }
  }

  window.App.studio.renderConnectorAccountsGrid = renderConnectorAccountsGrid;
})();
