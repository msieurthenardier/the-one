(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // The Providers table (M25 F3 L5b; reference spec section 8.2, flight DD7):
  // the list section of the Providers page, rendered into the page scaffold's
  // `.settings-list` (admin.js owns the page header, "Add provider", and the
  // `.settings-item` section below, where an open provider's editor mounts).
  // DOM-built (no HTML-string sink):
  //
  //   <p class="settings-intro">A provider is ...</p>
  //   <table class="providers-table" aria-label="Providers">
  //     <thead><tr><th>Name</th><th>Type</th><th>Used by</th></tr></thead>
  //     <tbody>
  //       <tr class="providers-table-row [is-selected]" data-id="{id}">
  //         <th scope="row" class="providers-table-name">
  //           <a class="providers-table-link" href="#settings/providers/{id}"
  //              data-testid="provider-card" data-id="{id}" [aria-current="page"]>{name}</a>
  //         </th>
  //         <td><span class="badge badge--{type}">{type}</span></td>
  //         <td class="providers-table-used">{n} agents | "1 agent" | "—"</td>
  //       </tr>
  //
  // Name, Type and Used by only: the board's Status column and health banner
  // are pre-accepted deviations D1/D2 (reference spec section 13). Rows sort
  // A-Z by name. The name link is a plain `<a href>`: App.nav's link
  // interceptor routes a click through the router (an intent go(), so the
  // leave guard asks once about a dirty editor). "Used by" comes from
  // App.usage.providerAgents over the agents list; while the agents list has
  // never loaded it reads "—", never "0 agents" (counts come from data, A23).
  //
  // Zero providers: a pane-size App.ui.emptyState "No providers yet." with
  // "Add provider" (testid providers-empty, its action providers-empty-add).
  //
  // renderProvidersTable is idempotent and re-renders the LIST section only:
  // a call whose rows are unchanged keeps the DOM (no flash, focus kept), a
  // changed call rebuilds the table body and puts focus back on the same
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
        usedBy: usedByText(agents, p.id)
      });
    }
    return out;
  }

  function buildRow(row) {
    var el = window.App.ui.util.el;
    var kind = KNOWN_BADGE_TYPES.indexOf(row.type) >= 0 ? row.type : 'unknown';
    var link = el('a', {
      className: 'providers-table-link',
      href: window.App.router.href({ destination: 'settings', section: 'providers', id: row.id }),
      text: row.name,
      title: row.name
    });
    link.setAttribute('data-testid', 'provider-card');
    link.setAttribute('data-id', row.id);
    var tr = el('tr', { className: 'providers-table-row' }, [
      // The Name cell is the row header (th scope=row, WCAG 1.3.1): a screen
      // reader announces the provider with each Type and Used by cell.
      el('th', { scope: 'row', className: 'providers-table-name' }, [link]),
      el('td', { className: 'providers-table-type' }, [
        window.App.ui.badge({ text: row.type || 'unknown', kind: kind })
      ]),
      el('td', { className: 'providers-table-used', text: row.usedBy })
    ]);
    tr.setAttribute('data-id', row.id);
    return tr;
  }

  function buildTable() {
    var el = window.App.ui.util.el;
    var table = el('table', { className: 'providers-table', 'aria-label': 'Providers' }, [
      el('thead', null, [
        el('tr', null, [
          el('th', { scope: 'col', className: 'providers-col-name', text: 'Name' }),
          el('th', { scope: 'col', className: 'providers-col-type', text: 'Type' }),
          el('th', { scope: 'col', className: 'providers-col-used', text: 'Used by' })
        ])
      ]),
      el('tbody')
    ]);
    return table;
  }

  // The id of the provider link that has focus inside listEl, or null.
  function focusedProviderId(listEl) {
    var active = document.activeElement;
    if (!active || !listEl.contains(active)) return null;
    var link = active.closest ? active.closest('a.providers-table-link') : null;
    return link ? link.getAttribute('data-id') : null;
  }

  function linkFor(listEl, id) {
    var links = listEl.querySelectorAll('a.providers-table-link');
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute('data-id') === id) return links[i];
    }
    return null;
  }

  function renderProvidersTable(listEl, state) {
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
      kind = 'table';
      var rows = rowModel(providers, state.agents);
      signature = 'table:' + JSON.stringify(rows);
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

    // The table: the intro and the table are built once per page and kept;
    // a changed data set rebuilds the body only.
    var intro = listEl.querySelector('.settings-intro');
    var table = listEl.querySelector('table.providers-table');
    if (!intro || !table) {
      listEl.textContent = '';
      intro = el('p', { className: 'settings-intro', text: INTRO });
      table = buildTable();
      listEl.appendChild(intro);
      listEl.appendChild(table);
    }
    var body = table.querySelector('tbody');
    var built = [];
    var model = rowModel(providers, state.agents);
    for (var i = 0; i < model.length; i++) built.push(buildRow(model[i]));
    body.replaceChildren.apply(body, built);
    setProvidersSelection(listEl, state.selectedId);
    if (focusId) {
      var again = linkFor(listEl, focusId);
      if (again) again.focus({ preventScroll: true });
    }
  }

  // Mark the open provider's row (aria-current on its link plus the selected
  // wash on the row) in place; every other row is cleared.
  function setProvidersSelection(listEl, selectedId) {
    var rows = listEl.querySelectorAll('tr.providers-table-row');
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var on = !!selectedId && row.getAttribute('data-id') === selectedId;
      row.classList.toggle('is-selected', on);
      var link = row.querySelector('a.providers-table-link');
      if (!link) continue;
      if (on) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  }

  // The provider links in table order (focus targets after a close or delete).
  function providerLinks(listEl) {
    return Array.prototype.slice.call(listEl.querySelectorAll('a.providers-table-link'));
  }

  // The table-order index of `id`, or -1.
  function providerRowIndex(listEl, id) {
    var links = providerLinks(listEl);
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute('data-id') === id) return i;
    }
    return -1;
  }

  window.App.admin.renderProvidersTable = renderProvidersTable;
  window.App.admin.setProvidersSelection = setProvidersSelection;
  window.App.admin.providerLinks = providerLinks;
  window.App.admin.providerRowIndex = providerRowIndex;
  window.App.admin.sortedProviders = sortedProviders;
})();
