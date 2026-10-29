// App.studio.renderAgentEditor -- the agent editor's frame (M31 F2 L06a).
//
// Builds the editor surface into `container` on the control library and returns a
// handle:
//
//   <div class="editor-header">            App.ui.editorShell (breadcrumb, title,
//                                          subtitle, Chat as `extra`, Cancel, Save)
//   <div role="tablist" class="tablist">   App.ui.tabs (split: true, so the tablist
//   <div class="tabpanels">                and the panels are direct children, as before)
//
// A failed load of the agent's current configuration (squawk 0090) is a line in the
// header's error slot (setLoadError) carrying the testid agent-load-error, present
// only while the load has failed; Save stays disabled.
//
// Tab ids are agent-tab-{id} and panel ids agent-tab-panel-{id}. The six tabs keep
// their builders (renderGeneralTab ... renderSelfConfigurationTab), each called into
// its panel.
//
// handle: { shell, tabs, key, patch(agent, providers, callbacks, loaded),
//           panelContainer(id), destroy() }.
//   patch(...) is the same-identity update: it sets the shell title, subtitle and
//   Chat visibility, updates the load-error node, patches General through its
//   setAgent (mounted once per identity, 06b), patches Knowledge through its
//   setAgent (07a), patches MCPs through setSources then setAgent (07b), patches
//   Tools through its setAgent (08b; a fourth argument `{revert: true}` is Cancel),
//   leaves Rules and notes alone (09: it saves immediately, keys only on the name
//   and declares no setAgent) and hands Self-configuration its record through
//   setAgent (10a: it refetches its own data after its actions; nothing is rebuilt,
//   so a patch rebuilds no panel). It does not re-wire listeners or
//   reset the snapshot: the controller does both after it (it owns checkDirty and the picker).
//
// callbacks: { onDelete, onPurge, onSave, onCancel, onTabChange, onTestProvider,
//              toolCategories, allTools, initialTab, ... } (the controller's bag).
//
// Editor Delete (General's Danger Zone) uses App.ui.confirm via the controller's
// handleDeleteEditor; this module only passes the handler down.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var TAB_ITEMS = [
    { id: 'general', label: 'General' },
    { id: 'rules-and-notes', label: 'Rules and notes' },
    { id: 'knowledge', label: 'Knowledge' },
    // One Tools tab holds two sections: Built-in tools, then MCP servers (M33 F1 L06).
    { id: 'tools', label: 'Tools' },
    { id: 'routines', label: 'Routines' },
    { id: 'self-configuration', label: 'Self-configuration' }
  ];

  var PANEL_IDS = {};
  TAB_ITEMS.forEach(function (item) { PANEL_IDS[item.id] = 'agent-tab-panel-' + item.id; });

  var LOAD_ERROR_LINE =
    'Save is off because this agent’s settings didn’t load. Reopen the agent to try again.';

  // The per-tab entry functions, each called into its (cleared) panel.
  function buildPanel(id, panel, agent, providers, cb) {
    var studio = window.App.studio;
    switch (id) {
      case 'general':
        // General is built once per identity; patch calls its setAgent (06b).
        return studio.renderGeneralTab(panel, agent, providers, {
          onChange: cb.onChange,
          onTestProvider: cb.onTestProvider,
          onDelete: cb.onDelete,
          onPurge: cb.onPurge
        });
      case 'rules-and-notes':
        // `agent` is null in create mode (the tab shows a "save first" notice).
        studio.renderRulesNotesTab(panel, agent, {
          fetchRules: cb.fetchRules,
          createRule: cb.createRule,
          updateRule: cb.updateRule,
          deleteRule: cb.deleteRule,
          reorderRules: cb.reorderRules,
          fetchNotes: cb.fetchNotes,
          setNotesEnabled: cb.setNotesEnabled,
          updateNote: cb.updateNote,
          deleteNote: cb.deleteNote,
          clearNotes: cb.clearNotes
        });
        break;
      case 'knowledge':
        // Built once per identity; patch calls its setAgent (07a).
        return studio.renderKnowledgeTab(panel, agent, cb.allKnowledgeBases, {
          onChange: cb.onChange,
          knowledgeBasesLoaded: cb.knowledgeBasesLoaded
        });
      case 'tools': {
        // Two sections in one panel. Both child modules wipe the node they are
        // given, so each gets its own host div inside its section (never the
        // panel or the section body). Built once per identity; patch calls the
        // children's setters through the composite (07b, 08b).
        var ui = window.App.ui;
        var builtinHost = document.createElement('div');
        builtinHost.setAttribute('data-testid', 'agent-tools-builtin-host');
        var mcpHost = document.createElement('div');
        mcpHost.setAttribute('data-testid', 'agent-tools-mcp-host');
        var builtinSection = ui.section({
          title: 'Built-in tools', titleTag: 'h2', testid: 'agent-tools-builtin-section',
          children: [builtinHost]
        });
        var mcpSection = ui.section({
          title: 'MCP servers', titleTag: 'h2', testid: 'agent-tools-mcp-section',
          children: [mcpHost]
        });
        panel.appendChild(builtinSection.el);
        panel.appendChild(mcpSection.el);
        var mcpsHandle = studio.renderMcpsTab(mcpHost, agent, cb.allMcpSources, {
          fetchMcpSourceTools: cb.fetchMcpSourceTools,
          onChange: cb.onChange,
          onSelectedSourceChange: cb.onSelectedMcpSourceChange,
          pendingSourceId: cb.pendingMcpAgentSourceId
        });
        var builtinHandle = studio.renderToolsTab(builtinHost, agent, {
          toolCategories: cb.toolCategories,
          allTools: cb.allTools,
          onChange: cb.onChange,
          disabledTools: cb.disabledTools,
          operatorConfigs: cb.operatorConfigs,
          fetchToolSchema: cb.fetchToolSchema
        });
        return {
          builtin: builtinHandle,
          mcps: mcpsHandle,
          setAgent: function (a, opts) { builtinHandle.setAgent(a, opts); },
          destroy: function () {
            if (mcpsHandle && mcpsHandle.destroy) mcpsHandle.destroy();
            if (builtinHandle && builtinHandle.destroy) builtinHandle.destroy();
          }
        };
      }
      case 'routines':
        // `agent` is null in create mode (a "save first" notice); the `default` agent gets
        // a "needs a named agent" notice. Returns {setAgent, activate, deactivate, destroy}.
        return studio.renderRoutinesTab(panel, agent, {
          fetchRoutines: cb.fetchRoutines,
          createRoutine: cb.createRoutine,
          updateRoutine: cb.updateRoutine,
          deleteRoutine: cb.deleteRoutine,
          runRoutine: cb.runRoutine,
          fetchRoutineRuns: cb.fetchRoutineRuns,
          openRoutineForm: cb.openRoutineForm
        });
      case 'self-configuration':
        // `agent` is null in create mode; the tab renders a "save first" notice.
        return studio.renderSelfConfigurationTab(panel, agent, {
          fetchStatus: cb.fetchSelfConfigurationStatus,
          onEnable: cb.onEnableSelfConfiguration,
          onDisable: cb.onDisableSelfConfiguration,
          onSetApprovalMode: cb.onSetSelfConfigurationApprovalMode,
          fetchRevisions: cb.fetchSelfConfigurationRevisions,
          onApproveRevision: cb.onApproveSelfConfigurationRevision,
          onDismissRevision: cb.onDismissSelfConfigurationRevision,
          onRestoreRevision: cb.onRestoreSelfConfigurationRevision,
          fetchRoutinesItem: cb.fetchRoutinesItem,
          putRoutinesItem: cb.putRoutinesItem,
          fetchRoutineProposals: cb.fetchRoutineProposals,
          approveRoutineProposal: cb.approveRoutineProposal,
          dismissRoutineProposal: cb.dismissRoutineProposal,
          onMintExternalCredential: cb.onMintExternalCredential,
          fetchExternalCredentials: cb.fetchExternalCredentials,
          onRevokeExternalCredential: cb.onRevokeExternalCredential,
          onRotateExternalCredential: cb.onRotateExternalCredential
        });
      default:
        break;
    }
    return null;
  }

  function clearNode(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function renderAgentEditor(container, agent, providers, callbacks) {
    callbacks = callbacks || {};
    var ui = window.App.ui;
    var isCreate = !agent;
    var h = { key: null, shell: null, tabs: null, loadFailed: false, chatBtn: null, general: null, knowledge: null, mcps: null, tools: null, routines: null, selfConfig: null };

    function chatTarget(a) { return a ? (a.name || '') : ''; }

    // M25 F4 L6 (DD8): Chat, a header action on a SAVED agent only (never in
    // create mode: there is no agent to chat with yet). It starts a new chat with
    // the stored name through App.chat.chatWith (the guarded go to
    // `#chats/~new/{name}`, so a dirty editor asks once). The click reads the
    // CURRENT name from h.agentName, which patch updates.
    h.agentName = chatTarget(agent);
    var extra = [];
    if (!isCreate) {
      h.chatBtn = ui.button({
        variant: 'secondary',
        icon: 'chat',
        label: 'Chat',
        className: 'agent-chat-btn',
        testid: 'agent-chat-btn',
        onClick: function () {
          window.App.chat.chatWith(h.agentName, { opener: h.chatBtn });
        }
      });
      extra.push(h.chatBtn);
    }

    // Cancel follows `dirty` on an open agent only (it reverts; nothing to revert
    // while clean). On the create form it abandons creation (DD8), so it is
    // enabled from first render (enabledWhenClean); Save still waits for a change.
    h.shell = ui.editorShell({
      // Save errors in the header are announced (squawk 0273); the load-failure line
      // drops the role while it shows (setLoadError), since its toast announces it.
      errorRole: 'alert',
      breadcrumb: {
        label: 'Agents',
        href: window.App.router.href({ destination: 'agents' })
      },
      title: isCreate ? 'New Agent' : (agent.name || ''),
      subtitle: isCreate ? null : (agent.description || ''),
      actions: {
        extra: extra,
        cancel: {
          testid: 'cancel-agent-btn',
          enabledWhenClean: isCreate,
          onClick: function () { if (callbacks.onCancel) callbacks.onCancel(); }
        },
        save: {
          label: isCreate ? 'Create' : 'Save',
          testid: 'save-agent-btn',
          onClick: function () { if (callbacks.onSave) callbacks.onSave(); }
        }
      }
    });

    var items = TAB_ITEMS.map(function (item) {
      return { id: item.id, label: item.label, testid: 'tab-' + item.id };
    });
    h.tabs = ui.tabs({
      label: 'Agent settings',
      items: items,
      idPrefix: 'agent',
      panelIdPrefix: 'agent-tab-panel',
      split: true,
      onChange: callbacks.onTabChange,
      initial: callbacks.initialTab || 'general'
    });

    clearNode(container);
    container.appendChild(h.shell.el);
    container.appendChild(h.tabs.tablist);
    container.appendChild(h.tabs.panels);

    // The load-failure line lives in the header's error slot. It acts only on a
    // change of state, so a patch neither re-announces the line nor erases a save
    // error the operator is reading.
    function setLoadError(on) {
      on = !!on;
      if (on === h.loadFailed) return;
      h.loadFailed = on;
      if (on) {
        // Drop the alert role first so the load line can never be announced.
        h.shell.errorEl.removeAttribute('role');
        h.shell.errorEl.setAttribute('data-testid', 'agent-load-error');
        h.shell.setError(LOAD_ERROR_LINE);
      } else {
        h.shell.setError(null);
        h.shell.errorEl.removeAttribute('data-testid');
        h.shell.errorEl.setAttribute('role', 'alert');
      }
      // Tie the disabled Save to its only explanation (WCAG 1.3.1/3.3.1); add or
      // remove just this token so any other description survives.
      var errId = h.shell.errorEl.id;
      if (!errId) {
        errId = 'agent-editor-header-error';
        h.shell.errorEl.id = errId;
      }
      var btn = h.shell.saveButton;
      var toks = (btn.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (t) {
        return t && t !== errId;
      });
      if (on) toks.push(errId);
      if (toks.length) btn.setAttribute('aria-describedby', toks.join(' '));
      else btn.removeAttribute('aria-describedby');
    }

    // Build the content of the panels, each into its cleared panel, from the given
    // agent and callback bag. Since leg 10a every tab is patched in place, so this
    // runs once at mount (the interim rebuild list is empty); `keep` lists panel ids
    // to skip (none now; kept for a future rebuild).
    function rebuildPanels(a, provs, cb, keep) {
      for (var i = 0; i < TAB_ITEMS.length; i++) {
        if (keep && keep.indexOf(TAB_ITEMS[i].id) !== -1) continue;
        var panel = h.tabs.panel(TAB_ITEMS[i].id);
        clearNode(panel);
        var built = buildPanel(TAB_ITEMS[i].id, panel, a, provs, cb);
        if (TAB_ITEMS[i].id === 'general') h.general = built;
        if (TAB_ITEMS[i].id === 'knowledge') h.knowledge = built;
        if (TAB_ITEMS[i].id === 'tools') {
          h.toolsTab = built;
          h.mcps = built.mcps;
          h.tools = built.builtin;
        }
        if (TAB_ITEMS[i].id === 'routines') h.routines = built;
        if (TAB_ITEMS[i].id === 'self-configuration') h.selfConfig = built;
      }
    }

    // Initial mount: the General tab is populated before this function returns
    // so form-field tests find their [data-field] selectors immediately.
    rebuildPanels(agent, providers, callbacks);
    setLoadError(!isCreate && callbacks.loadFailed === true);
    // App.ui.tabs fires onChange(initial) while it is built, before any panel exists, so a
    // mount that opens on Routines (a direct route, an agent switch, a rename remount)
    // never reaches the tab through the controller's setActiveTab: activate it here.
    // activate() is idempotent.
    if (h.routines && h.tabs.selected() === 'routines') h.routines.activate();

    // Same-identity update (see the header). The controller re-wires the picker
    // and resets the snapshot after it.
    // `opts.revert` is Cancel (the Tools tab drops its loaded override bodies).
    h.patch = function (a, provs, cb, opts) {
      h.agentName = chatTarget(a);
      h.shell.setTitle(a.name || '');
      h.shell.setSubtitle(a.description || '');
      if (h.chatBtn) h.chatBtn.hidden = false;
      setLoadError(cb.loadFailed === true);
      h.general.setAgent(a, provs);
      h.knowledge.setAgent(a, {
        allKnowledgeBases: cb.allKnowledgeBases,
        knowledgeBasesLoaded: cb.knowledgeBasesLoaded
      });
      // The source list first (the agent's own self-configuration surface may have
      // appeared or gone), then the agent's choices.
      h.mcps.setSources(cb.allMcpSources, a.name);
      h.mcps.setAgent(a, { pendingSourceId: cb.pendingMcpAgentSourceId });
      h.tools.setAgent(a, {
        revert: !!(opts && opts.revert),
        disabledTools: cb.disabledTools,
        operatorConfigs: cb.operatorConfigs,
        fetchToolSchema: cb.fetchToolSchema
      });
      // Self-configuration refetches its own data after its actions (10a): the
      // patch only hands it the record (the approval flag lives on it).
      h.selfConfig.setAgent(a);
      // Routines only swaps its agent reference (no refetch, no reset).
      h.routines.setAgent(a);
    };
    h.rebuildPanels = rebuildPanels;
    h.setLoadError = setLoadError;
    h.destroy = function () {
      if (h.selfConfig) h.selfConfig.destroy();
      if (h.routines) h.routines.destroy();
      if (h.toolsTab) h.toolsTab.destroy();
      h.tabs.destroy();
      clearNode(container);
    };
    return h;
  }

  window.App.studio.renderAgentEditor = renderAgentEditor;
  window.App.studio.AGENT_PANEL_IDS = PANEL_IDS;
})();
