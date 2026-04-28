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
// Editor Delete button: KEEPS its inline two-step flow (.delete-btn.confirm
// class state, capital-D "Confirm Delete?" label, 3s revert). The handler
// itself lives in studio.js (passed in via callbacks.onDelete) — this module
// just renders the button into .form-actions. Distinct from App.confirmDelete
// (lowercase-d) used by the tile X-button.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var PANEL_IDS = {
    general: 'agent-tab-panel-general',
    knowledge: 'agent-tab-panel-knowledge',
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
    html += '<div class="form-actions">';
    html += '<button type="button" class="btn-outlined-cyan back-btn" ' +
      'data-testid="back-agent-btn" aria-label="Back to agents list">' +
      window.App.icon('arrow-left') + ' Back</button>';
    if (!isCreate) {
      html += '<button type="button" class="btn-muted-destructive delete-btn" ' +
        'data-testid="delete-agent-btn" data-name="' + escapeAttr(name) + '">Delete Agent</button>';
    }
    // F5 leg 04: Save button uses `disabled` as the SINGLE source of truth.
    // Initial render: disabled (clean snapshot); checkDirty() flips
    // .disabled to mirror the dirty flag. The legacy .clean / .dirty class
    // toggling is removed in leg 04 in favor of the [disabled] attribute.
    html += '<button type="button" class="btn-filled-cyan save-btn" ' +
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
    html += '<button type="button" role="tab" class="tab" id="agent-tab-tools" ' +
      'aria-controls="' + PANEL_IDS.tools + '" data-tab-id="tools" ' +
      'data-testid="tab-tools" aria-selected="false" tabindex="-1">Tools</button>';
    html += '</div>';

    // === Tab panels ================================================
    html += '<div class="tabpanels">';
    html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.general +
      '" data-tab-id="general" aria-labelledby="agent-tab-general" hidden></div>';
    html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.knowledge +
      '" data-tab-id="knowledge" aria-labelledby="agent-tab-knowledge" hidden></div>';
    html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.tools +
      '" data-tab-id="tools" aria-labelledby="agent-tab-tools" hidden></div>';
    html += '</div>';

    container.innerHTML = html;

    // Wire action-cluster buttons — handlers from callbacks. The Delete
    // button's two-step inline flow (capital-D confirm) is wired by
    // studio.js (callbacks.onDelete), not by App.confirmDelete.
    var backBtn = container.querySelector('.back-btn');
    if (backBtn && callbacks.onBack) {
      backBtn.addEventListener('click', function () { callbacks.onBack(); });
    }
    var deleteBtn = container.querySelector('.delete-btn');
    if (deleteBtn && callbacks.onDelete) {
      deleteBtn.addEventListener('click', function () { callbacks.onDelete(deleteBtn); });
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
    var toolsPanel = container.querySelector('#' + PANEL_IDS.tools);

    window.App.studio.renderGeneralTab(generalPanel, agent, providers, {
      onTestProvider: callbacks.onTestProvider
    });
    window.App.studio.renderKnowledgeTab(knowledgePanel);
    window.App.studio.renderToolsTab(toolsPanel, agent, {
      toolCategories: callbacks.toolCategories,
      allTools: callbacks.allTools,
      onChange: callbacks.onChange
    });

    // Initialize the App.tabs helper. The initial activation happens here
    // (not deferred) so the General tab's content is visible synchronously.
    var tablistEl = container.querySelector('.tablist');
    var panelsEl = container.querySelector('.tabpanels');
    var tabHandle = window.App.tabs(tablistEl, panelsEl, {
      onChange: callbacks.onTabChange,
      // F5 leg 04: optional onBeforeChange hook used by studio.js to
      // dispatch the dirty-state confirm dialog before committing the tab.
      onBeforeChange: callbacks.onBeforeTabChange,
      initial: initialTab
    });

    return tabHandle;
  }

  window.App.studio.renderAgentEditor = renderAgentEditor;
  window.App.studio.AGENT_PANEL_IDS = PANEL_IDS;
})();
