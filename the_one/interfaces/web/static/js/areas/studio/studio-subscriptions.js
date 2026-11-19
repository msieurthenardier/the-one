// App.studio.subscriptions -- the studio shell's App.store / App.gleepglorp subscriptions
// (split out of studio.js, squawk 0386). Registered once for the page's lifetime (nothing
// unsubscribes). Reaches the shell only through ctx:
//   self, state, agentData, libraryPane, providersSection, mcpGlue, connectorGlue,
//   agentsList()   call-time getter (the agents list handle)
//   controller()   call-time getter (the agent editor controller)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var agentData = ctx.agentData;
    var libraryPane = ctx.libraryPane;
    var providersSection = ctx.providersSection;
    var mcpGlue = ctx.mcpGlue;
    var connectorGlue = ctx.connectorGlue;

    // Studio keeps its own copies (self._agents / self._allProviders), so a
    // store load that Studio did not initiate (Chats activation, a Library KB
    // rename that invalidated 'agents') would otherwise leave them stale.
    // Studio's own loadAll assigns directly, so notifications are ignored
    // while one is in flight.  Detail-shaped objects are never written back
    // to the store: this only reads the notified (list-shaped) copy.
    // The Agents list re-renders on every notification (M25 F3 L3): it sits
    // beside the editor, so an open agent or create form no longer hides it.
    App.store.subscribe('agents', function (list) {
      if (agentData.loadAllDepth() > 0 || !self._agentsLoaded) return;
      self._agents = list;
      ctx.agentsList().render();
      // The open editor follows the refreshed NOTICES only (sortie 07 L05); the selected
      // agent's row in the fresh list, never its other fields, so an unsaved edit is kept.
      var sel = self._selectedAgent && self._selectedAgent.name;
      var controller = ctx.controller();
      if (sel && controller) {
        for (var ai = 0; ai < list.length; ai++) {
          if (list[ai].name === sel) {
            controller.setNotices(sel, list[ai].notices || []);
            break;
          }
        }
      }
    });
    App.store.subscribe('providers', function (list) {
      if (agentData.loadAllDepth() > 0 || !self._agentsLoaded) return;
      self._allProviders = list;
      ctx.agentsList().render(); // the provider dots and names
    });
    // The Library list's five subscriptions (M25 F3 L4a; providers, sortie 02): they always
    // feed the section caches and re-attempt a pending MCP / connector consume (an intent
    // whose item was not cached), and they render the list only while the Library pane
    // exists. A bare notification never scrolls the list.
    App.store.subscribe('providers', function (list) {
      state.providersCache = list;
      if (self._activeSection === 'providers' && providersSection.pendingMode() === 'edit') {
        providersSection.consume(true);
      }
      libraryPane.render();
    });
    App.store.subscribe('knowledge-bases', function (list) {
      state.knowledgeBases = list;
      libraryPane.render();
    });
    App.store.subscribe('mcp-sources', function (list) {
      state.mcpSources = list;
      if (self._activeSection === 'mcp-sources' && self._pendingMcpSourceFormMode === 'edit') {
        mcpGlue.tryConsumePending(true);
      }
      libraryPane.render();
    });
    App.store.subscribe('connectors', function (list) {
      state.connectors = list;
      if (self._activeSection === 'connectors' && state.pendingConnectorFormMode === 'edit') {
        connectorGlue.tryConsumePending(true);
      }
      libraryPane.render();
    });
    App.store.subscribe('agents', function () { libraryPane.render(); }); // "{n} agents"
    App.gleepglorp.subscribe(function () { libraryPane.render(); }); // GleepGlorp in a provider meta
  }

  window.App.studio.subscriptions = { create: create };
})();
