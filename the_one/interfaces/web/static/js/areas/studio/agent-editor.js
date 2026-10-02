// App.studio.renderAgentEditor — agent-editor scaffold (F5 leg 03).
//
// Builds the editor surface:
//   <div class="editor-header">
//     <div class="editor-header-text">
//       <div class="editor-breadcrumb"><a href="#agents">Agents</a></div>
//         (DOM-inserted, M25 F3 L3; a link to the root since L4b)
//       <h1>Agent name</h1>
//       <p>Description</p>
//     </div>
//     <div class="form-actions">
//       <span class="editor-unsaved" role="status"></span>
//       <button>Cancel</button>
//       <button>Save</button>
//     </div>
//   </div>
//   <div role="tablist" class="tablist">
//     <button role="tab">General</button>
//     <button role="tab">Knowledge</button>
//     <button role="tab">Tools</button>
//   </div>
//   <div class="tabpanels">
//     <div role="tabpanel" id="agent-tab-panel-general"></div>
//     <div role="tabpanel" id="agent-tab-panel-knowledge"></div>
//     <div role="tabpanel" id="agent-tab-panel-tools"></div>
//   </div>
//
// Returns the App.tabs handle so studio.js can imperatively activate a tab
// (e.g., after hydrate sets _activeTab). The General tab is mounted
// synchronously before this function returns so test_flow_agent_crud.py's
// form-field tests find [data-field="..."] selectors immediately.
//
// callbacks: { onDelete, onPurge, onSave, onCancel, onTabChange, onTestProvider,
//              toolCategories, allTools, initialTab }
//
// M25 F3 L3 (DD2): the editor is hosted beside the Agents list, so Back is
// retired; the "Agents" breadcrumb is the header's first line, and since L4b
// it is a link to `#agents` (testid `editor-breadcrumb-link`). The
// `editor-unsaved` span is part of the header markup and is never created or
// removed afterwards: studio.js's checkDirty sets its text ("Unsaved
// changes") or clears it, from the same dirty flag as Save and (on an open
// agent) Cancel; the create form's Cancel is always enabled.
//
// Editor Delete button: uses App.confirmDelete via studio.js's
// handleDeleteEditor (F6 leg 04 migration). Capital-D "Confirm Delete?"
// label preserved through the helper's confirmLabel option; armed-state
// class is .delete-btn.confirm-delete. The handler itself lives in
// studio.js (passed in via callbacks.onDelete) — this module just renders
// the button into the General tab's Danger Zone.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var PANEL_IDS = {
    general: 'agent-tab-panel-general',
    knowledge: 'agent-tab-panel-knowledge',
    mcps: 'agent-tab-panel-mcps',
    tools: 'agent-tab-panel-tools',
    'self-configuration': 'agent-tab-panel-self-configuration'
  };

  function renderAgentEditor(container, agent, providers, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !agent;
    var initialTab = callbacks.initialTab || 'general';

    var name = isCreate ? 'New Agent' : (agent.name || '');
    var description = isCreate ? '' : (agent.description || '');

    var html = '';

    // === Editor header ============================================
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h1 class="editor-title">' + escapeHtml(name) + '</h1>';
    if (!isCreate) {
      html += '<p class="editor-subtitle">' + escapeHtml(description) + '</p>';
    }
    html += '</div>';

    // === Action cluster ===========================================
    // F5 leg 05: Delete moved into the General tab's Danger Zone (only
    // for existing agents). The header carries the unsaved caption, Cancel
    // and Save. `disabled` is the SINGLE source of truth for both buttons --
    // checkDirty() sets them (and the caption) from the dirty flag. Cancel
    // follows `dirty` on an open agent only (it reverts; nothing to revert
    // while clean). On the create form it abandons creation (DD8), so it is
    // enabled from first render, typed into or not (the M25 F3 behavior-gate
    // fix); Save still waits for a change.
    html += '<div class="form-actions">';
    html += '<span class="editor-unsaved" role="status" data-testid="editor-unsaved"></span>';
    html += '<button type="button" class="btn-outlined-primary cancel-btn" ' +
      'data-testid="cancel-agent-btn"' + (isCreate ? '' : ' disabled') + '>Cancel</button>';
    html += '<button type="button" class="btn-filled-primary save-btn" ' +
      'data-testid="save-agent-btn" disabled>' + (isCreate ? 'Create' : 'Save') + '</button>';
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // === Tablist ==================================================
    html += '<div role="tablist" class="tablist" aria-label="Agent settings">';
    html += '<button type="button" role="tab" class="tab" id="agent-tab-general" ' +
      'aria-controls="' + PANEL_IDS.general + '" data-tab-id="general" ' +
      'data-testid="tab-general" aria-selected="false" tabindex="-1">General</button>';
    html += '<button type="button" role="tab" class="tab" id="agent-tab-knowledge" ' +
      'aria-controls="' + PANEL_IDS.knowledge + '" data-tab-id="knowledge" ' +
      'data-testid="tab-knowledge" aria-selected="false" tabindex="-1">Knowledge</button>';
    html += '<button type="button" role="tab" class="tab" id="agent-tab-mcps" ' +
      'aria-controls="' + PANEL_IDS.mcps + '" data-tab-id="mcps" ' +
      'data-testid="tab-mcps" aria-selected="false" tabindex="-1">MCPs</button>';
    // data-tab-id="tools" + data-testid="tab-tools" preserved (browser
    // tests + URL routing still key off "tools"); only the visible label
    // and panel content semantics narrow to "Built-in Tools".
    html += '<button type="button" role="tab" class="tab" id="agent-tab-tools" ' +
      'aria-controls="' + PANEL_IDS.tools + '" data-tab-id="tools" ' +
      'data-testid="tab-tools" aria-selected="false" tabindex="-1">Built-in Tools</button>';
    // M21 F01 L02 — fifth tab: enable/disable the loopback self-
    // configuration MCP surface for this agent. Off by default; see
    // studio/self-configuration-tab.js.
    html += '<button type="button" role="tab" class="tab" id="agent-tab-self-configuration" ' +
      'aria-controls="' + PANEL_IDS['self-configuration'] + '" data-tab-id="self-configuration" ' +
      'data-testid="tab-self-configuration" aria-selected="false" tabindex="-1">Self-configuration</button>';
    html += '</div>';

    // === Tab panels ================================================
    html += '<div class="tabpanels">';
    html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.general +
      '" data-tab-id="general" aria-labelledby="agent-tab-general" hidden></div>';
    html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.knowledge +
      '" data-tab-id="knowledge" aria-labelledby="agent-tab-knowledge" hidden></div>';
    html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.mcps +
      '" data-tab-id="mcps" aria-labelledby="agent-tab-mcps" hidden></div>';
    html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.tools +
      '" data-tab-id="tools" aria-labelledby="agent-tab-tools" hidden></div>';
    html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS['self-configuration'] +
      '" data-tab-id="self-configuration" aria-labelledby="agent-tab-self-configuration" hidden></div>';
    html += '</div>';

    container.innerHTML = html;

    // The breadcrumb (M25 F3 DD2), built with DOM APIs after the markup is in
    // place: the first child of .editor-header-text. Its one segment links to
    // the destination root (the DD2 refinement, leg 4b): with Back retired it
    // is the visible way to close the item. studio.js routes the click and
    // focuses the agent's row after the close (DD8).
    var headerText = container.querySelector('.editor-header-text');
    var crumb = document.createElement('div');
    crumb.className = 'editor-breadcrumb';
    var crumbLink = document.createElement('a');
    crumbLink.className = 'editor-breadcrumb-link';
    crumbLink.setAttribute('href', window.App.router.href({ destination: 'agents' }));
    crumbLink.setAttribute('data-testid', 'editor-breadcrumb-link');
    crumbLink.textContent = 'Agents';
    crumb.appendChild(crumbLink);
    headerText.insertBefore(crumb, headerText.firstChild);

    // Wire action-cluster buttons — handlers from callbacks.
    var cancelBtn = container.querySelector('.cancel-btn');
    if (cancelBtn && callbacks.onCancel) {
      cancelBtn.addEventListener('click', function () { callbacks.onCancel(); });
    }
    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn && callbacks.onSave) {
      saveBtn.addEventListener('click', function () { callbacks.onSave(); });
    }

    // Mount per-tab content. The General tab MUST be populated before
    // this function returns so existing form-field tests find their
    // [data-field="..."] selectors immediately on agent select.
    var generalPanel = container.querySelector('#' + PANEL_IDS.general);
    var knowledgePanel = container.querySelector('#' + PANEL_IDS.knowledge);
    var mcpsPanel = container.querySelector('#' + PANEL_IDS.mcps);
    var toolsPanel = container.querySelector('#' + PANEL_IDS.tools);
    var selfConfigurationPanel = container.querySelector('#' + PANEL_IDS['self-configuration']);

    window.App.studio.renderGeneralTab(generalPanel, agent, providers, {
      onTestProvider: callbacks.onTestProvider,
      onDelete: callbacks.onDelete,
      onPurge: callbacks.onPurge
    });
    // F6 L3 — extended signature: pass agent + allKnowledgeBases +
    // callbacks so the Knowledge tab can render the real attach surface
    // (mirrors renderMcpsTab's call site above).
    window.App.studio.renderKnowledgeTab(knowledgePanel, agent, callbacks.allKnowledgeBases, {
      onChange: callbacks.onChange,
      knowledgeBasesLoaded: callbacks.knowledgeBasesLoaded
    });
    // F8 L3 — extended signature: pass agent + allMcpSources + callbacks so
    // the MCPs tab can render the chip-list, per-attachment editor, and
    // credential override fields. Mirrors renderToolsTab's call site below.
    window.App.studio.renderMcpsTab(mcpsPanel, agent, callbacks.allMcpSources, {
      fetchMcpSourceTools: callbacks.fetchMcpSourceTools,
      onChange: callbacks.onChange,
      onSelectedSourceChange: callbacks.onSelectedMcpSourceChange,
      pendingSourceId: callbacks.pendingMcpAgentSourceId
    });
    window.App.studio.renderToolsTab(toolsPanel, agent, {
      toolCategories: callbacks.toolCategories,
      allTools: callbacks.allTools,
      onChange: callbacks.onChange,
      // F6 leg 05 — operator-disabled tools + per-agent override panels.
      disabledTools: callbacks.disabledTools,
      operatorConfigs: callbacks.operatorConfigs,
      fetchToolSchema: callbacks.fetchToolSchema
    });
    // M21 F01 L02 — Self-configuration tab: enable/disable control + status
    // line. `agent` is null in create-mode; the tab renders a "save first"
    // notice in that case (mirrors the Danger Zone's isCreate guard).
    window.App.studio.renderSelfConfigurationTab(selfConfigurationPanel, agent, {
      fetchStatus: callbacks.fetchSelfConfigurationStatus,
      onEnable: callbacks.onEnableSelfConfiguration,
      onDisable: callbacks.onDisableSelfConfiguration,
      // M21 F02 L02 — approval-mode toggle + pending revision queue.
      onSetApprovalMode: callbacks.onSetSelfConfigurationApprovalMode,
      fetchRevisions: callbacks.fetchSelfConfigurationRevisions,
      fetchPendingCount: callbacks.fetchSelfConfigurationPendingCount,
      onApproveRevision: callbacks.onApproveSelfConfigurationRevision,
      onDismissRevision: callbacks.onDismissSelfConfigurationRevision,
      // M21 F02 L03 — revision-history restore control.
      onRestoreRevision: callbacks.onRestoreSelfConfigurationRevision,
      // M21 F03 L03 — external-client credential grant/list/revoke/rotate.
      onMintExternalCredential: callbacks.onMintExternalCredential,
      fetchExternalCredentials: callbacks.fetchExternalCredentials,
      onRevokeExternalCredential: callbacks.onRevokeExternalCredential,
      onRotateExternalCredential: callbacks.onRotateExternalCredential
    });

    // Initialize the App.tabs helper. The initial activation happens here
    // (not deferred) so the General tab's content is visible synchronously.
    var tablistEl = container.querySelector('.tablist');
    var panelsEl = container.querySelector('.tabpanels');
    var tabHandle = window.App.tabs(tablistEl, panelsEl, {
      onChange: callbacks.onTabChange,
      initial: initialTab
    });

    return tabHandle;
  }

  window.App.studio.renderAgentEditor = renderAgentEditor;
  window.App.studio.AGENT_PANEL_IDS = PANEL_IDS;
})();
