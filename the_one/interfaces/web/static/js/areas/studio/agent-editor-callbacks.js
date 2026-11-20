// App.studio.agentEditorCallbacks -- the callback bag the agent editor is built with (split
// out of agent-editor-controller.js in M36 F2 L7, no behaviour change). A factory the
// controller calls once:
//
//   var cb = App.studio.agentEditorCallbacks.create(ctx);
//   var bag = cb.build(isCreate);
//
// ctx (controller -> module): self, agentData (the agent-data handle), writeUrl() and the
// controller's handlers: onDelete(revertFn), onPurge(revertFn), save(isCreate), cancel(),
// setActiveTab(tab), testProvider(), onChange().
// handle: build(isCreate).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var agentData = ctx.agentData;
    // The per-agent Tools tab's categories: label -> tool names, from the one
    // shared table (static/js/tool-categories.js, M25 F4 L6, AC9; it replaced
    // this file's copy and the two admin/tools-*.js maps).
    var TOOL_CATEGORIES = App.toolCategories.byCategory;

    function build(isCreate) {
      return {
        loadFailed: !isCreate && self._selectedAgentLoaded === false,
        initialTab: self._activeTab || 'general',
        onDelete: ctx.onDelete,
        onPurge: ctx.onPurge,
        onSave: function () { ctx.save(isCreate); },
        onCancel: function () { ctx.cancel(); },
        onTabChange: function (tabId) { ctx.setActiveTab(tabId); },
        // F5 leg 05: tabs in the same agent share the form's dirty state, so
        // switching tabs does NOT lose unsaved data — no confirmation prompt.
        // The router's leave guard still fires on a list row, "New", the rail
        // and hash-route navigation to a different agent.
        onTestProvider: ctx.testProvider,
        toolCategories: TOOL_CATEGORIES,
        allTools: self._allTools,
        onChange: ctx.onChange,
        // F6 leg 05 — operator-state surfaces in Tools tab. Caches were
        // refreshed at editor-mount time (see selectAgent / doSelect). The
        // schema fetcher is closure-cached and survives agent changes.
        disabledTools: self._disabledTools,
        operatorConfigs: self._operatorConfigs,
        fetchToolSchema: agentData.fetchToolSchema,
        // F6 L3 — knowledge-base list + the L3-D1 load-success flag for
        // the Knowledge tab. Both are refreshed at editor-mount time (see
        // selectAgent / doSelect / doEnterCreateMode above).
        allKnowledgeBases: self._allKnowledgeBases,
        knowledgeBasesLoaded: self._knowledgeBasesLoaded === true,
        // Sortie 10: the Secrets section's list + load flag (agent-data.js owns them).
        allSecrets: self._allSecrets || [],
        secretsLoaded: self._secretsLoaded === true,
        // F8 L3 — MCP source list + per-source tools fetcher for Tools tab.
        allMcpSources: self._allMcpSources,
        testMcpAsAgent: agentData.testMcpAsAgent,
        saveMcpCredentials: agentData.saveMcpCredentials,
        // The studio owns the source focus (hydrate applies the URL's value to
        // both slots); the tab reads it from here, never from location.hash.
        pendingMcpAgentSourceId: self._selectedMcpAgentSourceId || self._pendingMcpAgentSourceId || null,
        // Callback so renderMcpsTab can notify studio.js when the selected
        // source changes (chip click → per-attachment editor). studio.js
        // updates _selectedMcpAgentSourceId and syncs the URL.
        onSelectedMcpSourceChange: function (sourceId) {
          self._selectedMcpAgentSourceId = sourceId;
          self._pendingMcpAgentSourceId = null;
          ctx.writeUrl();
        },
        // M27 F1 L2 -- Rules and notes tab network calls.
        fetchRules: agentData.fetchRules,
        createRule: agentData.createRule,
        updateRule: agentData.updateRule,
        deleteRule: agentData.deleteRule,
        reorderRules: agentData.reorderRules,
        fetchNotes: agentData.fetchNotes,
        setNotesEnabled: agentData.setNotesEnabled,
        deleteNote: agentData.deleteNote,
        clearNotes: agentData.clearNotes,
        // M33 F1 L8 -- Routines tab network calls.
        fetchRoutines: agentData.fetchRoutines,
        createRoutine: agentData.createRoutine,
        updateRoutine: agentData.updateRoutine,
        deleteRoutine: agentData.deleteRoutine,
        runRoutine: agentData.runRoutine,
        fetchRoutineRuns: agentData.fetchRoutineRuns,
        fetchRoutinesItem: agentData.fetchRoutinesItem,
        putRoutinesItem: agentData.putRoutinesItem,
        fetchRoutineProposals: agentData.fetchRoutineProposals,
        approveRoutineProposal: agentData.approveRoutineProposal,
        dismissRoutineProposal: agentData.dismissRoutineProposal,
        openRoutineForm: function (req) {
          var f = App.studio.routinesForm;
          return f && f.open ? f.open(req) : Promise.resolve(null);
        },
        // M21 F01 L02 — Self-configuration tab network calls.
        fetchSelfConfigurationStatus: agentData.fetchSelfConfigurationStatus,
        onEnableSelfConfiguration: agentData.enableSelfConfiguration,
        onDisableSelfConfiguration: agentData.disableSelfConfiguration,
        // M21 F02 L02 — approval-mode toggle + revision queue.
        onSetSelfConfigurationApprovalMode: agentData.setSelfConfigurationApprovalMode,
        fetchSelfConfigurationRevisions: agentData.fetchSelfConfigurationRevisions,
        onApproveSelfConfigurationRevision: agentData.approveSelfConfigurationRevision,
        onDismissSelfConfigurationRevision: agentData.dismissSelfConfigurationRevision,
        // M21 F02 L03 — revision history restore.
        onRestoreSelfConfigurationRevision: agentData.restoreSelfConfigurationRevision,
        // M21 F03 L03 — external-client credential grant/list/revoke/rotate.
        onMintExternalCredential: agentData.mintExternalCredential,
        fetchExternalCredentials: agentData.fetchExternalCredentials,
        onRevokeExternalCredential: agentData.revokeExternalCredential,
        onRotateExternalCredential: agentData.rotateExternalCredential
      };
    }

    return { build: build };
  }

  window.App.studio.agentEditorCallbacks = { create: create };
})();
