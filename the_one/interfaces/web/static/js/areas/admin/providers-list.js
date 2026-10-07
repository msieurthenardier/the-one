(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // The Providers list (M25 F3 L5b, tiles since L7; flight DD7 as amended):
  // the list section of the Providers page, rendered into the page scaffold's
  // `.settings-list` (admin.js owns the page header, "Add provider", and the
  // `.settings-item` section below, where an open provider's editor mounts).
  // A tile grid matching Built-in tools, by operator decision at the Flight 3
  // checkpoint (reference spec 8.2 drew a table). DOM-built (no HTML-string sink):
  //
  //   <p class="settings-intro">A provider is ...</p>
  //   <div class="entity-tile-grid provider-tile-grid" role="list" aria-label="Providers">
  //     <div class="entity-tile provider-tile [active]" role="listitem" data-id="{id}">
  //       <a class="entity-tile-name provider-tile-link" href="#settings/providers/{id}"
  //          data-testid="provider-card" data-id="{id}" title="{name}"
  //          [aria-current="page"]>{name}</a>
  //       <span class="badge badge--{type} provider-tile-badge">{type}</span>
  //       <span class="provider-tile-url">{base_url}</span>   (omitted when empty)
  //       <span class="provider-tile-used"><span class="visually-hidden">Used by </span>
  //         <span class="provider-tile-used-value">{n} agents | "1 agent" | "—"</span></span>
  //     </div>
  //
  // Tiles sort A-Z by name. The name link is the item link, a plain
  // `<a href>`: App.nav's link interceptor routes a click through the router
  // (an intent go(), so the leave guard asks once about a dirty editor); the
  // tile itself is not a click target. "Used by" comes from
  // App.usage.providerAgents over the agents list; while the agents list has
  // never loaded it reads "—", never "0 agents" (counts come from data, A23).
  //
  // Zero providers: a pane-size App.ui.emptyState "No providers yet." with
  // "Add provider" (testid providers-empty, its action providers-empty-add).
  //
  // renderProvidersList is idempotent and re-renders the LIST section only:
  // a call whose tiles are unchanged keeps the DOM (no flash, focus kept), a
  // changed call rebuilds the grid's children and puts focus back on the same
  // provider's link when a link had it. Selection is applied in place by
  // setProvidersSelection, never by a rebuild.
  //
  // state: { providers: array|null, agents: array|null (null = not loaded),
  //          failed: bool (the list never loaded), selectedId, onCreate: fn }

  var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'anthropic-plan', 'mock', 'openrouter'];
  var INTRO = 'A provider is an account or server that runs models. Agents pick one in their Model section.';

  function usedByText(agents, providerId) {
    if (!Array.isArray(agents)) return '—';
    var n = window.App.usage.providerAgents(agents, providerId);
    return n === 1 ? '1 agent' : n + ' agents';
  }

  function sortedProviders(providers) {
    return providers.slice().sort(function (a, b) {
      return String(a.name || '').localeCompare(String(b.name || ''));
    });
  }

  function rowModel(providers, agents) {
    var out = [];
    var list = sortedProviders(providers);
    for (var i = 0; i < list.length; i++) {
      var p = list[i];
      out.push({
        id: p.id,
        name: p.name || '',
        type: p.type || '',
        baseUrl: p.base_url || '',
        usedBy: usedByText(agents, p.id)
      });
    }
    return out;
  }

  function buildTile(row) {
    var el = window.App.ui.util.el;
    var kind = KNOWN_BADGE_TYPES.indexOf(row.type) >= 0 ? row.type : 'unknown';
    // App.ui.badge takes no extra class; the corner position is a class added
    // here (the control library is not extended for one consumer).
    var badge = window.App.ui.badge({ text: row.type || 'unknown', kind: kind });
    badge.classList.add('provider-tile-badge');
    var link = el('a', {
      className: 'entity-tile-name provider-tile-link',
      href: window.App.router.href({ destination: 'settings', section: 'providers', id: row.id }),
      text: row.name,
      title: row.name
    });
    link.setAttribute('data-testid', 'provider-card');
    link.setAttribute('data-id', row.id);
    // Source order is the reading order: name, then type, URL, "Used by".
    // The name and the badge share a flex title row (DD3), so the badge never
    // overlaps the name.
    var kids = [el('div', { className: 'tile-title-row' }, [link, badge])];
    if (row.baseUrl) {
      kids.push(el('span', { className: 'provider-tile-url', text: row.baseUrl, title: row.baseUrl }));
    }
    // A visually-hidden "Used by " prefix keeps the value's meaning for a
    // screen reader (the table's column header is gone); the visible text is
    // the value alone.
    kids.push(el('span', { className: 'provider-tile-used' }, [
      el('span', { className: 'visually-hidden', text: 'Used by ' }),
      el('span', { className: 'provider-tile-used-value', text: row.usedBy })
    ]));
    var tile = el('div', { className: 'entity-tile provider-tile' }, kids);
    tile.setAttribute('role', 'listitem');
    tile.setAttribute('data-id', row.id);
    return tile;
  }

  function buildGrid() {
    var el = window.App.ui.util.el;
    var grid = el('div', { className: 'entity-tile-grid provider-tile-grid' });
    grid.setAttribute('role', 'list');
    grid.setAttribute('aria-label', 'Providers');
    return grid;
  }

  // The id of the provider link that has focus inside listEl, or null.
  function focusedProviderId(listEl) {
    var active = document.activeElement;
    if (!active || !listEl.contains(active)) return null;
    var link = active.closest ? active.closest('a.provider-tile-link') : null;
    return link ? link.getAttribute('data-id') : null;
  }

  function linkFor(listEl, id) {
    var links = listEl.querySelectorAll('a.provider-tile-link');
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute('data-id') === id) return links[i];
    }
    return null;
  }

  function renderProvidersList(listEl, state) {
    state = state || {};
    var el = window.App.ui.util.el;
    var providers = state.providers;
    var kind;
    var signature;
    if (providers === null || providers === undefined) {
      kind = state.failed ? 'failed' : 'loading';
      signature = kind;
    } else if (providers.length === 0) {
      kind = 'empty';
      signature = kind;
    } else {
      kind = 'grid';
      var rows = rowModel(providers, state.agents);
      signature = 'grid:' + JSON.stringify(rows);
    }
    if (listEl._providersSignature === signature) {
      setProvidersSelection(listEl, state.selectedId);
      return;
    }
    listEl._providersSignature = signature;
    var focusId = focusedProviderId(listEl);

    if (kind === 'loading' || kind === 'failed') {
      listEl.textContent = '';
      listEl.appendChild(el('div', {
        className: 'admin-loading',
        text: kind === 'failed' ? 'Failed to load providers.' : 'Loading providers…'
      }));
      return;
    }

    if (kind === 'empty') {
      listEl.textContent = '';
      var addBtn = window.App.ui.button({
        label: 'Add provider',
        icon: 'plus',
        testid: 'providers-empty-add',
        onClick: function () { if (state.onCreate) state.onCreate(); }
      });
      listEl.appendChild(window.App.ui.emptyState({
        title: 'No providers yet.',
        headingLevel: 2,
        size: 'pane',
        action: addBtn,
        testid: 'providers-empty'
      }));
      return;
    }

    // The grid: the intro and the grid are built once per page and kept;
    // a changed data set rebuilds the grid's children only.
    var intro = listEl.querySelector('.settings-intro');
    var grid = listEl.querySelector('.provider-tile-grid');
    if (!intro || !grid) {
      listEl.textContent = '';
      intro = el('p', { className: 'settings-intro', text: INTRO });
      grid = buildGrid();
      listEl.appendChild(intro);
      listEl.appendChild(grid);
    }
    var built = [];
    var model = rowModel(providers, state.agents);
    for (var i = 0; i < model.length; i++) built.push(buildTile(model[i]));
    grid.replaceChildren.apply(grid, built);
    setProvidersSelection(listEl, state.selectedId);
    if (focusId) {
      var again = linkFor(listEl, focusId);
      if (again) again.focus({ preventScroll: true });
    }
  }

  // Mark the open provider's tile (aria-current on its link plus .active, the
  // selected wash, on the tile) in place; every other tile is cleared.
  function setProvidersSelection(listEl, selectedId) {
    var tiles = listEl.querySelectorAll('.provider-tile');
    for (var i = 0; i < tiles.length; i++) {
      var tile = tiles[i];
      var on = !!selectedId && tile.getAttribute('data-id') === selectedId;
      tile.classList.toggle('active', on);
      var link = tile.querySelector('a.provider-tile-link');
      if (!link) continue;
      if (on) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  }

  // The provider links in grid order (focus targets after a close or delete).
  function providerLinks(listEl) {
    return Array.prototype.slice.call(listEl.querySelectorAll('a.provider-tile-link'));
  }

  // The grid-order index of `id`, or -1.
  function providerRowIndex(listEl, id) {
    var links = providerLinks(listEl);
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute('data-id') === id) return i;
    }
    return -1;
  }

  window.App.admin.renderProvidersList = renderProvidersList;
  window.App.admin.setProvidersSelection = setProvidersSelection;
  window.App.admin.providerLinks = providerLinks;
  window.App.admin.providerRowIndex = providerRowIndex;
  window.App.admin.sortedProviders = sortedProviders;
})();
