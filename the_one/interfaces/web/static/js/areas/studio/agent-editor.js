// App.studio.renderAgentEditor — agent-editor scaffold (F5 leg 03).
//
// Builds the editor surface:
//   <div class="editor-header">
//     <div class="editor-header-text">
//       <h1>Agent name</h1>
//       <p>Description</p>
//     </div>
//     <div class="form-actions">
//       <button>← Back</button>
//       <button>Delete</button>
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
// callbacks: { onBack, onDelete, onSave, onTabChange, onTestProvider,
//              toolCategories, allTools, initialTab }
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
    tools: 'agent-tab-panel-tools'
  };

  function renderAgentEditor(container, agent, providers, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !agent;
    var initialTab = callbacks.initialTab || 'general';

    var name = isCreate ? 'New Agent' : (agent.name || '');
    var description = isCreate ? '' : (agent.description || '');

    // M10 L5.4 — coord-header readout: "● EDITING · AGENT NN". For create
    // mode show "NEW" instead of a numeric index; otherwise zero-pad the
    // 1-based index from callbacks.agentIndex (computed in studio.js from
    // the agents list).
    var agentIndex = (typeof callbacks.agentIndex === 'number') ? callbacks.agentIndex : null;
    var coordLabel;
    if (isCreate) {
      coordLabel = 'EDITING · NEW AGENT';
    } else if (agentIndex !== null && agentIndex >= 0) {
      var idxStr = String(agentIndex + 1);
      if (idxStr.length < 2) idxStr = '0' + idxStr;
      coordLabel = 'EDITING · AGENT ' + idxStr;
    } else {
      coordLabel = 'EDITING · AGENT';
    }

    var html = '';

    // === Editor header (M10 L5.4 — coord-header + mono actions) =========
    // The outer wrapper keeps the `.editor-header` class for any styling
    // hooks that still target it; the inner `.editor-head` carries the new
    // flex layout (coord + name on the left, action cluster on the right).
    //
    // Backward-compat selectors preserved:
    //   - `.editor-title` (text == agent name) — used by 9+ browser tests
    //   - `data-testid="back-agent-btn"` / `cancel-agent-btn` / `save-agent-btn`
    //   - `.back-btn` / `.cancel-btn` / `.save-btn` (studio.js wires by class)
    //   - `.editor-error` span (validation error sink)
    //
    // The Cancel button is visually rebranded as "↻ REVERT" and the Save
    // button as "✓ SAVE" — `cancelEdit()` already restores the saved
    // snapshot, which is exactly what an operator means by "revert".
    html += '<div class="editor-header">';
    html += '<div class="editor-head">';
    html += '<div class="editor-head-text">';
    html += '<div class="editor-coord"><span class="dot">●</span> ' + coordLabel + '</div>';
    html += '<h1 class="editor-title editor-name">' + escapeHtml(name) + '</h1>';
    if (!isCreate) {
      html += '<p class="editor-subtitle">' + escapeHtml(description) + '</p>';
    }
    html += '</div>';

    // === Action cluster ===========================================
    // F5 leg 05: Delete moved into the General tab's Danger Zone (only
    // for existing agents). The header carries Back / Revert / Save.
    // Save and Revert share `disabled` as the SINGLE source of truth —
    // checkDirty() flips both to mirror the dirty flag.
    html += '<div class="editor-actions form-actions">';
    html += '<button type="button" class="btn-action back-btn" ' +
      'data-testid="back-agent-btn" data-action="back" aria-label="Back to agents list">' +
      '← BACK</button>';
    html += '<button type="button" class="btn-action cancel-btn" ' +
      'data-testid="cancel-agent-btn" data-action="revert" disabled>↻ REVERT</button>';
    html += '<button type="button" class="btn-action accent save-btn" ' +
      'data-testid="save-agent-btn" data-action="save" disabled>✓ ' +
      (isCreate ? 'CREATE' : 'SAVE') + '</button>';
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-head
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
    // `data-tab-id="tools"` + `data-testid="tab-tools"` preserved (browser
    // tests + URL routing still key off "tools"); only the visible label
    // and panel content semantics narrow to "Built-in Tools".
    html += '<button type="button" role="tab" class="tab" id="agent-tab-tools" ' +
      'aria-controls="' + PANEL_IDS.tools + '" data-tab-id="tools" ' +
      'data-testid="tab-tools" aria-selected="false" tabindex="-1">Built-in Tools</button>';
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
    html += '</div>';

    container.innerHTML = html;

    // Wire action-cluster buttons — handlers from callbacks.
    var backBtn = container.querySelector('.back-btn');
    if (backBtn && callbacks.onBack) {
      backBtn.addEventListener('click', function () { callbacks.onBack(); });
    }
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

    window.App.studio.renderGeneralTab(generalPanel, agent, providers, {
      onTestProvider: callbacks.onTestProvider,
      onDelete: callbacks.onDelete
    });
    window.App.studio.renderKnowledgeTab(knowledgePanel);
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
