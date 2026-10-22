// App.studio.renderAgentEditor -- the agent editor's frame (M31 F2 L06a).
//
// Builds the editor surface into `container` on the control library and returns a
// handle:
//
//   <div class="editor-header">            App.ui.editorShell (breadcrumb, title,
//                                          subtitle, Chat as `extra`, Cancel, Save)
//   <div class="agent-load-error">         the squawk-0090 affordance (a frame node,
//                                          shown or hidden, never inserted afterwards)
//   <div role="tablist" class="tablist">   App.ui.tabs (split: true, so the tablist
//   <div class="tabpanels">                and the panels are direct children, as before)
//
// Tab ids are agent-tab-{id} and panel ids agent-tab-panel-{id}. The six tabs keep
// their builders (renderGeneralTab ... renderSelfConfigurationTab), each called into
// its panel.
//
// handle: { shell, tabs, loadErrorEl, key, patch(agent, providers, callbacks, loaded),
//           panelContainer(id), destroy() }.
//   patch(...) is the same-identity update: it sets the shell title, subtitle and
//   Chat visibility, updates the load-error node, patches General through its
//   setAgent (mounted once per identity, 06b), patches Knowledge through its
//   setAgent (07a), patches MCPs through setSources then setAgent (07b) and rebuilds
//   the content of the other three panels (the interim: those switch to patch-only in
//   legs 08-10). It does not re-wire listeners or
//   reset the snapshot: the controller does both after it (it owns checkDirty and the picker).
//
// callbacks: { onDelete, onPurge, onSave, onCancel, onTabChange, onTestProvider,
//              toolCategories, allTools, initialTab, ... } (the controller's bag).
//
// Editor Delete (General's Danger Zone) uses App.confirmDelete via the controller's
// handleDeleteEditor; this module only passes the handler down.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var TAB_ITEMS = [
    { id: 'general', label: 'General' },
    { id: 'rules-and-notes', label: 'Rules and notes' },
    { id: 'knowledge', label: 'Knowledge' },
    { id: 'mcps', label: 'MCPs' },
    // data-tab-id "tools" + testid tab-tools stay (tests and URL routing key off
    // "tools"); only the visible label narrows to "Built-in Tools".
    { id: 'tools', label: 'Built-in Tools' },
    { id: 'self-configuration', label: 'Self-configuration' }
  ];

  var PANEL_IDS = {};
  TAB_ITEMS.forEach(function (item) { PANEL_IDS[item.id] = 'agent-tab-panel-' + item.id; });

  var LOAD_ERROR_TEXT =
    'Couldn’t load this agent’s current configuration. The fields below may be ' +
    'out of date, so saving is disabled. Go back and reopen the agent to retry.';

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
      case 'mcps':
        // Built once per identity; patch calls its setSources and setAgent (07b).
        return studio.renderMcpsTab(panel, agent, cb.allMcpSources, {
          fetchMcpSourceTools: cb.fetchMcpSourceTools,
          onChange: cb.onChange,
          onSelectedSourceChange: cb.onSelectedMcpSourceChange,
          pendingSourceId: cb.pendingMcpAgentSourceId
        });
      case 'tools':
        studio.renderToolsTab(panel, agent, {
          toolCategories: cb.toolCategories,
          allTools: cb.allTools,
          onChange: cb.onChange,
          disabledTools: cb.disabledTools,
          operatorConfigs: cb.operatorConfigs,
          fetchToolSchema: cb.fetchToolSchema
        });
        break;
      case 'self-configuration':
        // `agent` is null in create mode; the tab renders a "save first" notice.
        studio.renderSelfConfigurationTab(panel, agent, {
          fetchStatus: cb.fetchSelfConfigurationStatus,
          onEnable: cb.onEnableSelfConfiguration,
          onDisable: cb.onDisableSelfConfiguration,
          onSetApprovalMode: cb.onSetSelfConfigurationApprovalMode,
          fetchRevisions: cb.fetchSelfConfigurationRevisions,
          fetchPendingCount: cb.fetchSelfConfigurationPendingCount,
          onApproveRevision: cb.onApproveSelfConfigurationRevision,
          onDismissRevision: cb.onDismissSelfConfigurationRevision,
          onRestoreRevision: cb.onRestoreSelfConfigurationRevision,
          onMintExternalCredential: cb.onMintExternalCredential,
          fetchExternalCredentials: cb.fetchExternalCredentials,
          onRevokeExternalCredential: cb.onRevokeExternalCredential,
          onRotateExternalCredential: cb.onRotateExternalCredential
        });
        break;
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
    var h = { key: null, shell: null, tabs: null, loadErrorEl: null, chatBtn: null, general: null, knowledge: null, mcps: null };

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

    // The squawk-0090 load-failure node: a frame node above the tabs, shown by
    // setLoadError(true). Plain textContent.
    h.loadErrorEl = document.createElement('div');
    h.loadErrorEl.className = 'agent-load-error';
    h.loadErrorEl.setAttribute('data-testid', 'agent-load-error');
    h.loadErrorEl.setAttribute('role', 'status');
    h.loadErrorEl.textContent = LOAD_ERROR_TEXT;
    h.loadErrorEl.hidden = true;

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
    container.appendChild(h.loadErrorEl);
    container.appendChild(h.tabs.tablist);
    container.appendChild(h.tabs.panels);

    function setLoadError(on) {
      h.loadErrorEl.hidden = !on;
    }

    // Rebuild the content of all six panels (the interim list), each into its
    // cleared panel, from the given agent and callback bag.
    // `keep` lists the panel ids patched in place instead (General, Knowledge, MCPs).
    function rebuildPanels(a, provs, cb, keep) {
      for (var i = 0; i < TAB_ITEMS.length; i++) {
        if (keep && keep.indexOf(TAB_ITEMS[i].id) !== -1) continue;
        var panel = h.tabs.panel(TAB_ITEMS[i].id);
        clearNode(panel);
        var built = buildPanel(TAB_ITEMS[i].id, panel, a, provs, cb);
        if (TAB_ITEMS[i].id === 'general') h.general = built;
        if (TAB_ITEMS[i].id === 'knowledge') h.knowledge = built;
        if (TAB_ITEMS[i].id === 'mcps') h.mcps = built;
      }
    }

    // Initial mount: the General tab is populated before this function returns
    // so form-field tests find their [data-field] selectors immediately.
    rebuildPanels(agent, providers, callbacks);
    setLoadError(!isCreate && callbacks.loadFailed === true);

    // Same-identity update (see the header). The controller re-wires the picker
    // and resets the snapshot after it.
    h.patch = function (a, provs, cb) {
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
      rebuildPanels(a, provs, cb, ['general', 'knowledge', 'mcps']);
    };
    h.rebuildPanels = rebuildPanels;
    h.setLoadError = setLoadError;
    h.destroy = function () {
      h.tabs.destroy();
      clearNode(container);
    };
    return h;
  }

  window.App.studio.renderAgentEditor = renderAgentEditor;
  window.App.studio.AGENT_PANEL_IDS = PANEL_IDS;
})();
