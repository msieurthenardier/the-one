// App.studio.connectorGlue -- the Library "Connectors" group's section glue
// (M31 F2 L02b, DD1) plus the one pending-item rule shared by MCP, connectors
// and providers. Moved verbatim out of studio.js; a factory it calls once in
// init, LAST of the Library modules (it takes the MCP handle for the rule):
//
//   var connectors = App.studio.connectorGlue.create(ctx);
//
// ctx (studio -> module): self, state, pane (the libraryPane handle),
// providers (the providers-section handle), mcp (the mcpGlue handle),
// setActiveSection, discardOpen, writeUrl, sectionContent() (the detail host;
// the element is created once), fetchAgents, buildRootHeading, agentData.
//
// handle (module -> studio): render() (renderConnectorsSection),
// tryConsumePending(allowCache) -> bool, reset() (close the open form),
// isOpen() (a form is open), resolvePendingLibraryItem(section, fresh) (the
// pending-item rule; `self._resolvePendingLibraryItems` calls it).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var pane = ctx.pane;
    var sectionContentEl = ctx.sectionContent(); // created once by the shell, never replaced
    var discardOpen_ = ctx.discardOpen;
    var setActiveSection = ctx.setActiveSection;
    var reloadLibrary = pane.reload;
    var syncLibrarySelection = pane.sync;
    var libraryRowIndex = pane.rowIndex;
    var focusLibraryRowNear = pane.focusNear;
    var focusLibraryGroupStart = pane.focusGroupStart;
    var renderLibraryEmpty = pane.renderEmpty;
    var providers = ctx.providers;
    var mcp = ctx.mcp;
    var agentData = ctx.agentData;

    var CONNECTOR_TYPES = [];
    var connectorTypesReady = null;

    // ── Connectors section (Mission 23 Flight 2 Leg 2, DD-9; M25 F3 L4a) ──
    // The mcp-sources dispatch (mcp-glue.js): the editor, a pending id resolving
    // (nothing), or the section root's empty state. Connectors are routed
    // (`connectors/new`, `connectors/{id}`) with the same pending pair.
    function renderConnectorsSection() {
      sectionContentEl.innerHTML = '';
      if (!state.connectorFormMode && state.pendingConnectorFormMode === 'add') {
        state.connectorFormMode = 'add';
        state.editingConnector = null;
        state.pendingConnectorFormMode = null;
        state.pendingConnectorId = null;
      }
      if (state.connectorFormMode) {
        state.dirty = false;
        var typesReady = connectorTypesReady || fetchConnectorTypes();
        // Fetch agents directly rather than reading `self._agents` — the
        // shared `loadAll()` populating it runs once at init and is NOT
        // guaranteed to have resolved yet if the operator deep-links straight
        // to #library/connectors/~new (a real race, not just a theoretical
        // one — caught by tests/browser/test_studio_connector_editor.py). A
        // dedicated fetch here is always fresh and never depends on load
        // order.
        var connGen = state.editorGen;
        Promise.all([typesReady, agentData.fetchAgents(true)]).then(function (results) {
          if (connGen !== state.editorGen) return; // discarded while the lists loaded
          var agentsForDropdown = results[1];
          if (state.connectorFormMode == null || self._activeSection !== 'connectors') return;
          App.studio.renderConnectorEditor(
            sectionContentEl, state.editingConnector, CONNECTOR_TYPES, agentsForDropdown, {
              // Back is retired (M25 F3 L4b, DD2): the header breadcrumb's
              // "Connectors" link closes the editor (onBreadcrumbClick).
              // DD8: edit mode reverts in place (the route stays the item);
              // create mode discards and replaces to the section root.
              onCancel: function () {
                if (state.connectorFormMode === 'edit' && state.editingConnector) {
                  state.dirty = false;
                  renderConnectorsSection();
                  return;
                }
                discardOpen_();
                App.router.go(App.router.href({ destination: 'library' }),
                  { replace: true, bypassGuard: true });
                focusLibraryGroupStart('connectors');
              },
              // Save-create keeps the editor's render path (no navigation, no
              // hydrate): the editor re-renders in edit mode from the saved
              // row and the URL moves from ~new to the item through sync(),
              // whose create->item rule announces the name. The editor
              // invalidated 'connectors'; the list reloads and `dirty` clears
              // before the URL write.
              onSaveSuccess: function (updated, isCreate) {
                if (connGen !== state.editorGen) return; // discarded mid-save: no resurrection
                state.editingConnector = updated;
                state.connectorFormMode = 'edit';
                reloadLibrary('connectors');
                state.dirty = false;
                if (window.App && window.App.router) {
                  App.router.sync('studio', 'connectors/' + encodeURIComponent(updated.id),
                    { name: updated.name });
                }
                syncLibrarySelection(true);
                if (isCreate) renderConnectorsSection();
              },
              onDeleteSuccess: function () {
                var rowIndex = libraryRowIndex('connector:' + (state.editingConnector ? state.editingConnector.id : ''));
                discardOpen_();
                App.router.go(App.router.href({ destination: 'library' }),
                  { replace: true, bypassGuard: true });
                reloadLibrary('connectors').then(function () { focusLibraryRowNear(rowIndex); });
              },
              onDirtyChange: function (d) { state.dirty = d; }
            }
          );
          // A create's or an edit-mode Cancel's parked focus restore (M25 F6 L1b).
          App.focusAfter.flush();
        });
        syncLibrarySelection(false);
        return;
      }
      if (state.pendingConnectorFormMode === 'edit' && state.pendingConnectorId) {
        syncLibrarySelection(false);
        return;
      }
      renderLibraryEmpty();
      syncLibrarySelection(false);
    }

    function fetchConnectorTypes() {
      connectorTypesReady = fetch('/api/connectors/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { CONNECTOR_TYPES = types; })
        .catch(function () { CONNECTOR_TYPES = []; });
      return connectorTypesReady;
    }

    function findConnector(id) {
      if (!state.connectors) return null;
      for (var i = 0; i < state.connectors.length; i++) {
        if (state.connectors[i].id === id) return state.connectors[i];
      }
      return null;
    }

    self._closeConnectorForm = function () {
      state.connectorFormMode = null;
      state.editingConnector = null;
      state.dirty = false;
    };

    // The connector twin of tryConsumePendingMcpSource.
    function tryConsumePendingConnector(allowCache) {
      var pid = state.pendingConnectorId;
      var pmode = state.pendingConnectorFormMode;
      if (!pid && !pmode) return false;
      if (pmode === 'add') {
        state.connectorFormMode = 'add';
        state.editingConnector = null;
        state.pendingConnectorId = null;
        state.pendingConnectorFormMode = null;
        renderConnectorsSection();
        return true;
      }
      if (pmode === 'edit' && pid && allowCache !== false) {
        var found = findConnector(pid);
        if (found) {
          state.connectorFormMode = 'edit';
          state.editingConnector = found;
          state.pendingConnectorId = null;
          state.pendingConnectorFormMode = null;
          renderConnectorsSection();
          return true;
        }
      }
      return false;
    }
    self._tryConsumePendingConnector = tryConsumePendingConnector;

    // ── The pending-item rule (M25 F3 L4a), one rule for MCP and connectors.
    //   - A root with no pending id fetches nothing.
    //   - A create form needs no list: it opens at once.
    //   - A pending id on a FRESH hydrate (boot, Back/Forward, a typed hash):
    //     force-get (joining pane creation's or activate's forced get), then
    //     consume, then heal a dead id to the section root.
    //   - A pending id on an INTENT (a row click, an agent-tab link): consume
    //     from the section cache; on a miss (a cold cache) consume after a
    //     plain get, or on the next store notification (the lifetime
    //     subscriptions re-attempt) -- never heal on non-fresh data.
    var PENDING_KINDS = {
      'mcp-sources': {
        collection: 'mcp-sources',
        mode: function () { return self._pendingMcpSourceFormMode; },
        id: function () { return self._pendingMcpSourceId; },
        consume: mcp.tryConsumePending,
        heal: function () {
          self._pendingMcpSourceId = null;
          self._pendingMcpSourceFormMode = null;
          setActiveSection('library');
        }
      },
      'providers': {
        collection: 'providers',
        mode: function () { return providers.pendingMode(); },
        id: function () { return providers.pendingId(); },
        consume: providers.consume,
        heal: providers.heal
      },
      'connectors': {
        collection: 'connectors',
        mode: function () { return state.pendingConnectorFormMode; },
        id: function () { return state.pendingConnectorId; },
        consume: tryConsumePendingConnector,
        heal: function () {
          state.pendingConnectorId = null;
          state.pendingConnectorFormMode = null;
          setActiveSection('library');
        }
      }
    };

    function resolvePendingLibraryItem(section, fresh) {
      var k = PENDING_KINDS[section];
      if (!k || !k.mode()) return;
      if (k.mode() === 'add') {
        k.consume(true);
        return;
      }
      var pid = k.id();
      if (!pid) return;
      var stillPending = function () {
        return self._activeSection === section && k.mode() === 'edit' && k.id() === pid;
      };
      if (!fresh) {
        if (k.consume(true)) return;
        App.store.get(k.collection).then(function () {
          pane.syncCache(k.collection);
          if (stillPending()) k.consume(true);
        }, function () { /* the next notification re-attempts */ });
        return;
      }
      App.store.get(k.collection, { force: true }).then(function (list) {
        pane.syncCache(k.collection);
        if (!stillPending()) return; // consumed by the notification, or superseded
        if (k.consume(true)) return;
        // Heal only when the fetch just made agrees the id is gone (the store
        // may have dropped this response if a mutation invalidated it
        // mid-flight; the next notification then consumes the item).
        for (var i = 0; list && i < list.length; i++) {
          if (list[i] && list[i].id === pid) return;
        }
        k.heal();
      }, function () { /* a failed load is not a dead id: stay pending */ });
    }

    self._resolvePendingLibraryItems = function (fresh) {
      if (PENDING_KINDS[self._activeSection]) resolvePendingLibraryItem(self._activeSection, fresh);
    };

    return {
      render: renderConnectorsSection,
      tryConsumePending: tryConsumePendingConnector,
      reset: function () {
        state.connectorFormMode = null;
        state.editingConnector = null;
      },
      isOpen: function () { return !!state.connectorFormMode; },
      resolvePendingLibraryItem: resolvePendingLibraryItem
    };
  }

  window.App.studio.connectorGlue = { create: create };
})();
