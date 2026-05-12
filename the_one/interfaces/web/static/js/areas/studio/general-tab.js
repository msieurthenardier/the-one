// App.studio.renderGeneralTab — agent-editor General tab content (F5 leg 03).
//
// Carries the existing form fields (name [create-only], description,
// system_prompt, provider_config_id, llm_model, max_iterations) using F4
// .field-row / .field-input / .field-textarea / .field-select vocabulary.
// Includes the Ollama VRAM warning placeholder + a Test button that POSTs
// to /api/providers/{id}/test (handler in studio.js — this module just
// wires the click) + an Advanced collapsible section with disabled
// temperature/top_p/max_tokens stubs.
//
// All existing data-field, id, and selector hooks preserved so
// collectFormData() and the VRAM warning logic continue to work without
// modification regardless of which tab is mounted.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderGeneralTab(panel, agent, providers, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !agent;
    var cfg = agent || {
      name: '',
      description: '',
      provider_config_id: providers && providers.length > 0 ? providers[0].id : null,
      llm_model: '',
      system_prompt: '',
      max_iterations: 20
    };

    var html = '';

    // Identity — Name is rendered for BOTH create and edit modes (F4 L02
    // functional batch added rename support). The save path (studio.js)
    // detects a name change for existing agents and POSTs to the
    // /api/agents/{name}/rename endpoint before the regular PUT save.
    html += '<div class="editor-section"><div class="section-title">Identity</div>';
    html += '<div class="field-row"><label for="studio-name">Name</label>' +
      '<input id="studio-name" class="field-input" data-field="name" value="' +
      escapeAttr(cfg.name || '') + '" placeholder="agent-name" />' +
      '</div>';
    html += '<div class="field-row"><label for="studio-description">Description</label>' +
      '<input id="studio-description" class="field-input" data-field="description" value="' + escapeAttr(cfg.description || '') + '" placeholder="What does this agent do?" />' +
      '</div>';
    html += '</div>';

    // LLM Configuration
    html += '<div class="editor-section"><div class="section-title">LLM Configuration</div>';

    // Provider dropdown
    html += '<div class="field-row"><label for="studio-provider">Provider</label>';
    html += '<select id="studio-provider" class="field-input field-select" data-field="provider_config_id">';
    if (!cfg.provider_config_id) {
      html += '<option value="" disabled selected>No provider — configure in Admin</option>';
    }
    var providerFound = false;
    for (var p = 0; p < providers.length; p++) {
      var prov = providers[p];
      var provSelected = cfg.provider_config_id === prov.id ? ' selected' : '';
      if (cfg.provider_config_id === prov.id) providerFound = true;
      html += '<option value="' + escapeAttr(prov.id) + '"' + provSelected + '>' +
        escapeHtml(prov.name) + ' (' + escapeHtml(prov.type) + ')</option>';
    }
    if (cfg.provider_config_id && !providerFound) {
      html += '<option value="' + escapeAttr(cfg.provider_config_id) + '" selected>Unknown provider (' + escapeAttr(cfg.provider_config_id) + ')</option>';
    }
    html += '</select></div>';

    // Model picker — native <select> for all provider types. Browsers
    // provide free type-ahead jump (start typing letters to jump to a
    // matching option), which scales acceptably even for OpenRouter's
    // ~370 models. A prior datalist+input variant was tried but its
    // value-driven filter trapped operators with a stale selection (the
    // dropdown showed only the previously-picked match).
    html += '<div class="field-row"><label for="studio-model">Model</label>';
    html += '<div class="field-model-wrap">';
    html += '<select id="studio-model" class="field-input field-select" data-field="llm_model">';
    html += '<option value="" disabled selected>Select a provider first</option>';
    html += '</select>';
    html += '<span class="model-loading" aria-live="polite"></span>';
    html += '</div></div>';

    // Capability panel — Ollama models surface their /api/show capabilities
    // here so operators see at a glance whether the selected model supports
    // tools (and get a load-bearing warning when it doesn't).
    html += '<div class="model-capabilities" data-testid="model-capabilities" role="status" aria-live="polite"></div>';

    // VRAM warning placeholder (ollama only) — preserved verbatim so
    // checkVramForModel logic in studio.js continues to find this element.
    html += '<div class="studio-vram-warning" role="status" aria-live="polite"></div>';

    // Test button — disabled state computed from the LIVE provider-select
    // value (NOT cfg.provider_config_id), so an unsaved provider change
    // can be tested before save. Click handler delegates to studio.js
    // (callbacks.onTestProvider) to keep network logic + flash messaging
    // co-located with the rest of studio's transport code.
    var testDisabled = !cfg.provider_config_id ? ' disabled' : '';
    html += '<div class="test-provider-row">';
    html += '<button type="button" class="btn-outlined-primary test-provider-btn" ' +
      'data-testid="test-provider-btn"' + testDisabled +
      ' title="Tests provider connectivity. Does not validate the agent’s full config.">' +
      window.App.icon('play') + ' Test</button>';
    html += '<span class="test-result" aria-live="polite" data-testid="test-provider-result"></span>';
    html += '</div>';

    html += '</div>'; // .editor-section LLM

    // System Prompt
    html += '<div class="editor-section"><div class="section-title">System Prompt</div>';
    html += '<textarea class="field-textarea" data-field="system_prompt" rows="8" placeholder="Instructions for the agent...">' +
      escapeHtml(cfg.system_prompt || '') + '</textarea>';
    html += '</div>';

    // Behavior — max_iterations stays here (real AgentConfig storage).
    html += '<div class="editor-section"><div class="section-title">Behavior</div>';
    html += '<div class="field-row"><label for="studio-max-iterations">Max Iterations</label>' +
      '<input id="studio-max-iterations" class="field-input field-input-short" data-field="max_iterations" type="number" value="' +
      (cfg.max_iterations || 20) + '" min="1" max="100" /></div>';
    html += '</div>';

// Danger Zone (existing agents only). The Delete button uses
    // App.confirmDelete (F6 leg 04 migration): first click arms
    // `.delete-btn.confirm-delete` with capital-D "Confirm Delete?" via the
    // helper's confirmLabel option; second click within 3s fires DELETE.
    if (!isCreate) {
      html += '<div class="editor-section danger-zone">';
      html += '<div class="section-title danger-zone-title">Danger Zone</div>';
      html += '<button type="button" class="btn-muted-destructive delete-btn" ' +
        'data-testid="delete-agent-btn" data-name="' + escapeAttr(cfg.name || '') + '">' +
        '<span data-confirm-title>Delete Agent</span></button>';
      html += '</div>';
    }

    panel.innerHTML = html;

    var testBtn = panel.querySelector('.test-provider-btn');
    if (testBtn && callbacks.onTestProvider) {
      testBtn.addEventListener('click', function () { callbacks.onTestProvider(); });
    }
    var deleteBtn = panel.querySelector('.delete-btn');
    if (deleteBtn && callbacks.onDelete) {
      deleteBtn.addEventListener('click', function () { callbacks.onDelete(deleteBtn); });
    }
  }

  window.App.studio.renderGeneralTab = renderGeneralTab;
})();
