// App.studio.libraryPane -- the Library list column (M31 F2 L02b, DD1): the
// grouped App.ui.listPane (Model providers, Knowledge bases, MCP servers,
// Connectors, Secrets (sortie 10)) with its Add menu, the section caches' sync, the gated
// first fill, the selection rule, the row-focus helpers and the Library start
// page. Moved verbatim out of studio.js; a factory it calls once in init, on
// the providers-section.js precedent:
//
//   var pane = App.studio.libraryPane.create(ctx);
//
// Created FIRST of the Library modules (the groups and the providers section
// take its handle). The five Library App.store.subscribe calls stay in the
// shell, which calls the handle.
//
// ctx (studio -> module):
//   self                  the area object (_activeSection, _selectedKbId,
//                         _pendingMcpSourceFormMode, _pendingMcpSourceId)
//   state                 the shell's shared state (read at use time): kbCreateMode,
//                         the MCP / connector form and pending slots, the four caches
//   listHost              the sidebar's Library host element
//   sectionContent()      the section-content host (the start page, create focus)
//   buildRootHeading(t)   the shell's page-h1 builder (shared with the Agents root)
//   providers()           the providers-section handle. A function because the
//                         providers section is created AFTER the pane (its ctx
//                         takes this handle): the one back-reference, resolved at
//                         call time.
//
// handle (module -> studio): syncCache(collection), reload(name) (reloadLibrary),
// render(scroll), sync(scroll) (syncLibrarySelection), rowIndex(id),
// focusNear(index), focusGroupStart(section), renderEmpty(), load(force),
// create() / destroy() (the list pane's lifetime), reset(), isOpen(),
// selection(), atRoot(), goCreate(route, opener), focusCreate(route),
// isSection(section).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // The one Library group table (squawk 0191), exposed as App.studio.libraryGroups
  // (a copy per read) so studio-route.js derives its section list from it at call time.
  var LIBRARY_GROUPS = [
    { id: 'providers', section: 'providers', route: 'providers', collection: 'providers',
      label: 'Model providers', emptyText: 'No model providers yet.',
      failText: 'Couldn\u2019t load model providers.', icon: 'sparkles',
      testid: 'provider-card', prefix: 'provider:' },
    { id: 'knowledge', section: 'knowledge', route: 'knowledge', collection: 'knowledge-bases',
      label: 'Knowledge bases', emptyText: 'No knowledge bases yet.',
      failText: 'Couldn\u2019t load knowledge bases.', icon: 'database',
      testid: 'knowledge-base-card', prefix: 'knowledge:' },
    { id: 'mcp', section: 'mcp-sources', route: 'mcp', collection: 'mcp-sources',
      label: 'MCP servers', emptyText: 'No MCP servers yet.',
      failText: 'Couldn\u2019t load MCP servers.', icon: 'server',
      testid: 'mcp-source-card', prefix: 'mcp:' },
    { id: 'connectors', section: 'connectors', route: 'connectors', collection: 'connectors',
      label: 'Connectors', emptyText: 'No connectors yet.',
      failText: 'Couldn\u2019t load connectors.', icon: 'plug',
      testid: 'connector-card', prefix: 'connector:' },
    { id: 'secrets', section: 'secrets', route: 'secrets', collection: 'secrets',
      label: 'Secrets', emptyText: 'No secrets yet.',
      failText: 'Couldn’t load secrets.', icon: 'key',
      testid: 'secret-card', prefix: 'secret:' }
  ];
  window.App.studio.libraryGroups = function () {
    return LIBRARY_GROUPS.map(function (g) {
      var copy = {};
      Object.keys(g).forEach(function (k) { copy[k] = g[k]; });
      return copy;
    });
  };

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var libraryListHost = ctx.listHost;
    var buildRootHeading = ctx.buildRootHeading;

    // ── The Library list column (M25 F3 L4a, DD5) ───────────────────────
    //
    // One grouped App.ui.listPane (Model providers, Knowledge bases, MCP servers, Connectors)
    // with an Add menu; it replaces the Library section nav and the three
    // tile grids. Rows are links (`#library/{section}/{id}`), so App.nav
    // routes a row click through the router's leave guard.
    //
    // Data. The five store subscriptions (registered once, below loadAll)
    // live for the page: they always feed the section caches (knowledgeBases,
    // mcpSources, connectors, providersCache -- which back find*, the pending consumes and
    // the knowledge detail's cache hit) and re-attempt pending consumes, and
    // they render the list only while the pane exists. Fetch policy (DD9's
    // freshness bound): pane creation force-gets the four collections and
    // plain-gets agents; studio activate on a Library section force-gets the
    // four; a move between Library sections fetches nothing; a mutation's
    // callback invalidates (the editor) and then reloadLibrary(name)s.
    // The Library start page (DD15): one block per type, in LIBRARY_GROUPS order.
    var LIBRARY_EMPTY = {
      providers: {
        add: 'Add model provider',
        text: 'The connection an agent uses to reach a model: an account or a server that runs ' +
          'models, such as Anthropic, OpenAI or Ollama. Each agent picks one in its Model section.'
      },
      knowledge: {
        add: 'Add knowledge base',
        text: 'Folders of your documents that agents can search. The app indexes the files and ' +
          'keeps the index current as they change. Attach a knowledge base to an agent on the ' +
          'agent\u2019s Knowledge tab.'
      },
      mcp: {
        add: 'Add MCP server',
        text: 'Tool servers that use the Model Context Protocol, such as a browser, a database ' +
          'or another app\u2019s API. Choose which agents get which tools on each agent\u2019s ' +
          'Tools tab.'
      },
      connectors: {
        add: 'Add connector',
        text: 'Links to chat platforms such as Discord, so people can talk to your agents there. ' +
          'Each connector routes its channels to the agents you choose.'
      },
      secrets: {
        add: 'Add secret',
        text: 'Passwords, keys and other values an agent can use in a tool call without ever ' +
          'seeing them. Choose which agents get which secrets on each agent’s Tools tab.'
      }
    };
    var LIBRARY_INTRO = 'Add something here once, then choose which agents use it in each ' +
      'agent\u2019s settings.';
    var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'anthropic-plan', 'anthropic-plan-token', 'mock', 'openrouter'];
    var libraryList = null;     // the Library App.ui.listPane while on Library
    var libraryAddMenu = null;  // its title-row Add menu (App.ui.menu)
    var libraryRendered = false; // the gated first setItems has run
    var libraryPaneGen = 0;     // bumped on create/destroy: stale pane gets drop
    var libraryPaneSettled = {}; // collection -> this pane's get settled
    var libraryPaneFailed = {};  // collection -> this pane's get failed

    // `library` is the root pseudo-section (DD1): the start page, no group.
    function isLibrarySection(section) {
      return section === 'library' || libraryGroupFor(section) !== null;
    }

    function libraryGroupFor(section) {
      for (var i = 0; i < LIBRARY_GROUPS.length; i++) {
        if (LIBRARY_GROUPS[i].section === section) return LIBRARY_GROUPS[i];
      }
      return null;
    }

    function libraryCache(collection) {
      if (collection === 'providers') return state.providersCache;
      if (collection === 'knowledge-bases') return state.knowledgeBases;
      if (collection === 'mcp-sources') return state.mcpSources;
      if (collection === 'connectors') return state.connectors;
      if (collection === 'secrets') return state.secrets;
      return null;
    }

    // Only syncLibraryCache and the lifetime subscriptions write the caches.
    function setLibraryCache(collection, list) {
      if (collection === 'providers') state.providersCache = list;
      else if (collection === 'knowledge-bases') state.knowledgeBases = list;
      else if (collection === 'mcp-sources') state.mcpSources = list;
      else if (collection === 'connectors') state.connectors = list;
      else if (collection === 'secrets') state.secrets = list;
    }

    // The section cache follows the STORE's value, never a request's own
    // result: the store drops a response whose request was invalidated
    // mid-flight (generation-safe), so a stale request resolving after a newer
    // one can never put a deleted row back.
    function syncLibraryCache(collection) {
      var held = App.store.peek(collection).value;
      if (held) setLibraryCache(collection, held);
    }

    function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

    // A collection is SETTLED once the store has ever loaded it or this pane's
    // own get has settled (either way). Until all three have, the list keeps
    // its "Loading library…" state, so no group flashes "No … yet." early.
    function libraryGateOpen() {
      for (var i = 0; i < LIBRARY_GROUPS.length; i++) {
        var name = LIBRARY_GROUPS[i].collection;
        if (!libraryPaneSettled[name] && !App.store.peek(name).loaded) return false;
      }
      return true;
    }

    // The row id the list marks selected: the open item, else a pending deep
    // link's id (so a cold deep link selects its row as soon as the list
    // loads); none at a section root or on a create form.
    function librarySelection() {
      var section = self._activeSection;
      if (section === 'library') return null; // the root: nothing selected (DD1)
      if (section === 'providers') return ctx.providers().selectionId();
      if (section === 'knowledge') {
        return !state.kbCreateMode && self._selectedKbId ? 'knowledge:' + self._selectedKbId : null;
      }
      if (section === 'mcp-sources') {
        if (state.mcpSourceFormMode === 'add') return null;
        if (state.mcpSourceFormMode === 'edit' && state.editingMcpSource) return 'mcp:' + state.editingMcpSource.id;
        if (self._pendingMcpSourceFormMode === 'edit' && self._pendingMcpSourceId) {
          return 'mcp:' + self._pendingMcpSourceId;
        }
        return null;
      }
      if (section === 'connectors') {
        if (state.connectorFormMode === 'add') return null;
        if (state.connectorFormMode === 'edit' && state.editingConnector) return 'connector:' + state.editingConnector.id;
        if (state.pendingConnectorFormMode === 'edit' && state.pendingConnectorId) {
          return 'connector:' + state.pendingConnectorId;
        }
        return null;
      }
      if (section === 'secrets') {
        if (state.secretFormMode === 'add') return null;
        if (state.secretFormMode === 'edit' && state.editingSecret) return 'secret:' + state.editingSecret.id;
        if (state.pendingSecretFormMode === 'edit' && state.pendingSecretId) {
          return 'secret:' + state.pendingSecretId;
        }
        return null;
      }
      return null;
    }

    // True at the Library root (DD1): the `library` pseudo-section, where
    // nothing is open or pending in any group.
    function atLibraryRoot() {
      return self._activeSection === 'library';
    }

    // One row. The meta is a visible span inside the <a>, so it is part of the
    // accessible name; the type icon is aria-hidden. Agent counts appear only
    // once `agents` has loaded (never "0 agents" while loading). Until then a
    // row with nothing known keeps an empty meta line (a no-break space, which
    // the accessible name trims), so every Library row stays two lines (the
    // reference spec's 50px) and nothing shifts when the counts arrive -- a
    // shift would push a scrolled-in group back out of view.
    function libraryItem(group, row, agents) {
      var meta = [];
      if (group.id === 'providers') {
        // Explicit branch: any group that is not named falls through to the
        // connector count below (sortie 02, DD5).
        if (agents) {
          // GleepGlorp has no agents row: name it first when its settings use this
          // provider ("GleepGlorp", or "GleepGlorp, 2 agents"; M36 F1 L03).
          var gg = window.App.gleepglorp ? App.gleepglorp.peek().value : null;
          var pn = App.usage.providerAgents(agents, row.id);
          var ggUses = App.usage.providerAgents([], row.id, gg) === 1;
          if (ggUses) meta.push(pn ? 'GleepGlorp, ' + plural(pn, 'agent', 'agents') : 'GleepGlorp');
          else meta.push(plural(pn, 'agent', 'agents'));
        }
      }
      if (group.id === 'mcp') {
        // ONE mcpState call: the state and the count cannot disagree, and the words
        // come from App.usage.mcpStateLabel, the editor's status line source (DD6).
        // A connected row shows its tool count; an errored or signed-out row shows
        // only its state, even with a cached count (the editor carries the detail).
        var ms = App.usage.mcpState(row);
        meta.push(ms.state === 'connected' ? plural(ms.tools, 'tool', 'tools') :
          App.usage.mcpStateLabel(ms.state));
      }
      if (group.id === 'secrets') {
        // "N values" first (known from the row itself), then the agent count.
        var vn = (row.values || []).length;
        meta.push(plural(vn, 'value', 'values'));
      }
      if (agents && group.id !== 'providers') {
        var n = group.id === 'knowledge' ? App.usage.kbAgents(agents, row.id)
          : group.id === 'mcp' ? App.usage.mcpAgents(agents, row.id)
            : group.id === 'secrets' ? App.usage.secretAgents(agents, row.id).length
              : App.usage.connectorAgents(row).length;
        meta.push(plural(n, 'agent', 'agents'));
      }
      var item = {
        id: group.prefix + row.id,
        label: row.name,
        meta: meta.length ? meta.join(' \u00b7 ') : '\u00a0',
        icon: group.icon,
        href: App.router.href({ destination: 'library', section: group.route, id: row.id })
      };
      // The row testid is the group's literal (LIBRARY_GROUPS, where the
      // registry guard sees it): the grids' card testids are kept on the rows.
      item.testid = group.testid;
      if (group.id === 'providers') {
        // The type badge; an unknown type uses the `unknown` kind.
        item.badges = [{
          text: row.type || 'unknown',
          kind: KNOWN_BADGE_TYPES.indexOf(row.type) >= 0 ? row.type : 'unknown'
        }];
      }
      if (group.id === 'mcp') {
        // Local (stdio) or Remote (streamable-http), own badge kinds.
        var isLocal = row.type === 'stdio';
        item.badges = [{ text: isLocal ? 'Local' : 'Remote', kind: isLocal ? 'local' : 'remote' }];
      }
      return item;
    }

    function libraryGroup(group, agents) {
      var rows = libraryCache(group.collection);
      if (!rows) {
        return {
          id: group.id, label: group.label, items: [],
          emptyText: libraryPaneFailed[group.collection] ? group.failText : group.emptyText
        };
      }
      var sorted = rows.slice().sort(function (a, b) {
        return String(a.name).localeCompare(String(b.name));
      });
      var items = [];
      for (var i = 0; i < sorted.length; i++) items.push(libraryItem(group, sorted[i], agents));
      return { id: group.id, label: group.label, emptyText: group.emptyText, items: items };
    }

    // The one builder of the Library list (leg 3's pattern): setItems, then
    // the selection. A no-op off Library (no pane) and while the first load is
    // gated. `scroll` (a load or a navigation) brings the selected row into
    // view; the gated first fill does too. Store notifications pass nothing.
    function renderLibraryList(scroll) {
      if (!libraryList || !libraryGateOpen()) return;
      var first = !libraryRendered;
      var agentsPeek = App.store.peek('agents');
      var agents = agentsPeek.value || null;
      var groups = [];
      for (var i = 0; i < LIBRARY_GROUPS.length; i++) groups.push(libraryGroup(LIBRARY_GROUPS[i], agents));
      libraryList.setItems(groups);
      libraryRendered = true;
      libraryList.setSelected(librarySelection());
      if (scroll || first) scrollLibrary();
    }

    // The selected row into view (now, and once more when the web fonts are
    // ready: leg 3's cold-load reflow). At the Library root there is nothing to
    // scroll to: every root is the one start page (DD2).
    function scrollLibrary() {
      var pane = libraryList;
      if (!pane || !libraryRendered) return;
      if (librarySelection()) {
        pane.scrollToSelected();
        if (document.fonts && document.fonts.ready) {
          document.fonts.ready.then(function () {
            if (libraryList === pane && librarySelection()) pane.scrollToSelected();
          });
        }
      }
    }

    // DD3 (c): re-sync the selection without rebuilding the rows; `scroll`
    // also scrolls (hydrateState passes it).
    function syncLibrarySelection(scroll) {
      if (!libraryList || !libraryRendered) return;
      libraryList.setSelected(librarySelection());
      if (scroll) scrollLibrary();
    }
    self._syncLibrarySelection = syncLibrarySelection;

    // Load the four Library collections for this pane (`force`: pane
    // creation, studio activate) and the agents list (a plain get: it reuses
    // the cache Agents loaded). A failed get with no last-good value marks its
    // group "Couldn't load"; one with a value keeps the stale rows.
    function loadLibrary(force) {
      var gen = libraryPaneGen;
      LIBRARY_GROUPS.forEach(function (group) {
        var name = group.collection;
        App.store.get(name, { force: !!force }).then(function () {
          syncLibraryCache(name);
          if (gen !== libraryPaneGen) return;
          libraryPaneSettled[name] = true;
          libraryPaneFailed[name] = false;
          renderLibraryList();
        }, function () {
          if (gen !== libraryPaneGen) return;
          libraryPaneSettled[name] = true;
          libraryPaneFailed[name] = true;
          renderLibraryList();
        });
      });
      App.store.get('agents').then(function () {
        if (gen === libraryPaneGen) renderLibraryList();
      }, function () { /* the counts stay off until agents load */ });
      // GleepGlorp's provider joins the provider rows' meta (M36 F1 L03).
      App.gleepglorp.get({ force: !!force }).then(function () {
        if (gen === libraryPaneGen) renderLibraryList();
      }, function () { /* the meta simply omits GleepGlorp */ });
    }

    // After a mutation: the editor invalidated `name`, so this plain get
    // refetches (a warm, valid cache would resolve without notifying anyone,
    // which is why the list is rendered here as well). Always resolves.
    function reloadLibrary(name) {
      return App.store.get(name).then(function (list) {
        syncLibraryCache(name);
        renderLibraryList();
        return list;
      }, function () {
        renderLibraryList();
        return null;
      });
    }

    // "Add" -> a type: a go() to its `~new` (the router guard asks once about
    // a dirty editor). Choosing the create form that is already open only
    // refocuses its first field, dirty or not, and never runs a guarded go()
    // to the same route.
    function goLibraryCreate(route, opener) {
      var cur = App.router.current();
      var target = 'library/' + route + '/~new';
      if (cur && cur.route === target && libraryCreateOpen(route)) {
        focusLibraryCreate(route);
        return;
      }
      App.router.go(App.router.href({ destination: 'library', section: route, create: true }),
        { opener: opener || null });
    }

    function libraryCreateOpen(route) {
      if (route === 'providers') return ctx.providers().createOpen();
      if (route === 'knowledge') return self._activeSection === 'knowledge' && state.kbCreateMode;
      if (route === 'mcp') return self._activeSection === 'mcp-sources' && state.mcpSourceFormMode === 'add';
      if (route === 'connectors') return self._activeSection === 'connectors' && state.connectorFormMode === 'add';
      if (route === 'secrets') return self._activeSection === 'secrets' && state.secretFormMode === 'add';
      return false;
    }

    function focusLibraryCreate(route) {
      if (route === 'providers') { ctx.providers().focusCreate(); return; }
      var sel = route === 'knowledge' ? '[data-testid="kb-create-name-input"]' : '[data-field="name"]';
      var field = ctx.sectionContent().querySelector(sel);
      if (field) field.focus();
    }

    function createLibraryList() {
      libraryPaneGen += 1;
      libraryPaneSettled = {};
      libraryPaneFailed = {};
      libraryRendered = false;
      // The subscriptions feed the caches from studio init on; a collection the
      // store loaded before that (another area's get) is seeded from peek, so an
      // open gate never renders an empty group over data the store holds.
      LIBRARY_GROUPS.forEach(function (group) {
        if (!libraryCache(group.collection)) syncLibraryCache(group.collection);
      });
      libraryAddMenu = App.ui.menu({
        trigger: { variant: 'secondary', size: 'sm', icon: 'plus', label: 'Add', testid: 'library-add-btn' },
        // The trigger sits at the right of the 300px aside, whose overflow is
        // hidden: the popup opens toward the start edge so it stays inside.
        align: 'end',
        items: [
          { label: 'Model provider', testid: 'library-add-provider',
            onSelect: function () { goLibraryCreate('providers', libraryAddMenu && libraryAddMenu.trigger); } },
          { label: 'Knowledge base', testid: 'library-add-knowledge',
            onSelect: function () { goLibraryCreate('knowledge', libraryAddMenu && libraryAddMenu.trigger); } },
          { label: 'MCP server', testid: 'library-add-mcp',
            onSelect: function () { goLibraryCreate('mcp', libraryAddMenu && libraryAddMenu.trigger); } },
          { label: 'Connector', testid: 'library-add-connector',
            onSelect: function () { goLibraryCreate('connectors', libraryAddMenu && libraryAddMenu.trigger); } },
          { label: 'Secret', testid: 'library-add-secret',
            onSelect: function () { goLibraryCreate('secrets', libraryAddMenu && libraryAddMenu.trigger); } }
        ]
      });
      libraryList = App.ui.listPane({
        title: 'Library',
        intro: 'Things agents can use. Attach them from an agent\u2019s Knowledge and Tools tabs.',
        actions: [libraryAddMenu.el],
        // Shown only until the gated first fill (the groups' own empty lines
        // take over after it).
        emptyText: function () { return 'Loading library\u2026'; },
        rowStyle: 'library',
        testid: 'library-list'
      });
      libraryListHost.appendChild(libraryList.el);
      // A re-entry renders from the cache at once (the gate is open when every
      // collection has loaded before); the forced gets refresh it.
      renderLibraryList(true);
      loadLibrary(true);
    }

    function destroyLibraryList() {
      if (!libraryList) return;
      libraryPaneGen += 1;
      if (libraryAddMenu) libraryAddMenu.destroy();
      libraryList.destroy();
      libraryListHost.textContent = '';
      libraryList = null;
      libraryAddMenu = null;
      libraryRendered = false;
    }

    // The flat, visible-row index of the row `id` (list order, across groups),
    // read BEFORE a delete removes it.
    function libraryRowIndex(id) {
      if (!libraryList) return 0;
      var rows = libraryList.rows();
      var items = libraryList.getItems();
      var n = 0;
      for (var i = 0; i < items.length && i < rows.length; i++) {
        if (items[i].id === id) return n;
        if (!rows[i].parentNode.hidden) n++;
      }
      return n;
    }

    // DD8's focus rule after a delete: the row now at `index` (the next one
    // after the removed row, which may be in the next group), else the
    // previous one, else Add.
    function focusLibraryRowNear(index) {
      if (!libraryList) return;
      var rows = libraryList.rows(true);
      var target = rows.length ? rows[Math.max(0, Math.min(index, rows.length - 1))] : null;
      if (!target) {
        if (libraryAddMenu) libraryAddMenu.trigger.focus();
        return;
      }
      for (var i = 0; i < rows.length; i++) rows[i].setAttribute('tabindex', rows[i] === target ? '0' : '-1');
      target.focus();
    }

    // After a create-form Cancel: the first row of that section's group, else
    // Add (leg 3's focusAgentRowNear(0)).
    function focusLibraryGroupStart(section) {
      if (!libraryList) return;
      var group = libraryGroupFor(section);
      var first = null;
      var items = libraryList.getItems();
      var rows = libraryList.rows();
      for (var i = 0; i < items.length && i < rows.length; i++) {
        if (group && String(items[i].id).indexOf(group.prefix) === 0 && !rows[i].parentNode.hidden) {
          first = rows[i];
          break;
        }
      }
      if (!first) {
        if (libraryAddMenu) libraryAddMenu.trigger.focus();
        return;
      }
      var all = libraryList.rows(true);
      for (var k = 0; k < all.length; k++) all[k].setAttribute('tabindex', all[k] === first ? '0' : '-1');
      first.focus();
    }

    // The Library start page (the `library` root, DD1/DD6): one card per group.
    function renderLibraryEmpty() {
      var el = App.ui.util.el;
      ctx.sectionContent().appendChild(buildRootHeading('Library'));
      var blocks = LIBRARY_GROUPS.map(function (g) {
        var copy = LIBRARY_EMPTY[g.id];
        return el('section', { className: 'start-page-card' }, [
          el('span', { className: 'start-page-card-icon' }, [App.ui.util.icon(g.icon)]),
          el('div', { className: 'start-page-card-body' }, [
            el('h2', { className: 'start-page-card-title', text: g.label }),
            el('p', { className: 'start-page-text', text: copy.text })
          ]),
          App.ui.button({
            variant: 'secondary',
            icon: 'plus',
            label: copy.add,
            testid: 'library-start-' + g.id + '-add',
            onClick: function (e) { goLibraryCreate(g.route, e && e.currentTarget); }
          })
        ]);
      });
      var page = el('div', { className: 'start-page' },
        [el('p', { className: 'start-page-text', text: LIBRARY_INTRO })].concat(blocks));
      page.setAttribute('data-testid', 'library-start');
      ctx.sectionContent().appendChild(page);
    }

    return {
      syncCache: syncLibraryCache,
      reload: reloadLibrary,
      render: renderLibraryList,
      sync: syncLibrarySelection,
      rowIndex: libraryRowIndex,
      focusNear: focusLibraryRowNear,
      focusGroupStart: focusLibraryGroupStart,
      renderEmpty: renderLibraryEmpty,
      load: loadLibrary,
      create: createLibraryList,
      destroy: destroyLibraryList,
      // Tear the pane down to nothing (same as destroy: the pane keeps no state
      // beyond its lifetime).
      reset: destroyLibraryList,
      isOpen: function () { return !!libraryList; },
      selection: librarySelection,
      atRoot: atLibraryRoot,
      goCreate: goLibraryCreate,
      focusCreate: focusLibraryCreate,
      isSection: isLibrarySection
    };
  }

  window.App.studio.libraryPane = { create: create };
})();
