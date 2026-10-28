// App.studio.renderGeneralTab -- the agent editor's General tab (M31 F2 L06b).
//
// Built once per editor identity from library controls (App.ui.section, field,
// textInput, textarea, select, button, status, dangerZone) into `panel`, and
// returned as a handle:
//
//   { providerSelect, modelSelect, testButton, setAgent(agent, providers),
//     setNameError(msg | null),
//     applyStored(stored, baseline), setStoredChangeNote(fields | null),
//     setTestResult(state, text), clearTestResult() }
//
// applyStored and setStoredChangeNote serve a stored change that lands while the
// form is open (a self-configuration approval or restore, M31 F2 L10a): the stored
// description / system prompt is written into a CLEAN field only (its value equals
// the snapshot baseline), a field the operator has edited keeps their text and is
// reported, and the note (testid agent-stored-value-changed) says Save will replace
// the stored value. setAgent clears the note.
//
// setAgent patches every value in place (name, description, provider options, the
// model select back to its placeholder, the capability line and the VRAM warning
// cleared, the prompt and the two numbers, Test's disabled state and result). The
// controller re-wires the picker after it, which refetches the model list with
// dataset.pendingValue set to the stored model (App.studio.agentModelPicker).
//
// The field ids (studio-name ... studio-max-iterations), data-field attributes and
// field classes are the contract collectFormData and the browser tests read.
// Each control's own onInput/onChange calls callbacks.onChange (the editor's dirty
// check) directly: the picker's listener sweep does not see these controls.
//
// callbacks: { onChange, onTestProvider, onDelete(revert), onPurge(revert) }.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function option(value, label, flags) {
    var o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    if (flags && flags.disabled) o.disabled = true;
    if (flags && flags.selected) o.selected = true;
    return o;
  }

  function defaults(providers) {
    return {
      name: '',
      description: '',
      provider_config_id: providers && providers.length > 0 ? providers[0].id : null,
      llm_model: '',
      system_prompt: '',
      max_iterations: 20,
      chat_history_retention_days: 30
    };
  }

  function renderGeneralTab(panel, agent, providers, callbacks) {
    callbacks = callbacks || {};
    var ui = window.App.ui;
    var isCreate = !agent;
    var cfg = agent || defaults(providers);

    function dirty() { if (callbacks.onChange) callbacks.onChange(); }
    // The picker's sweep skips a control that already carries its own listeners.
    function own(control) {
      control._dirtyWired = true;
      control.addEventListener('change', dirty);
      return control;
    }

    // ── Identity ────────────────────────────────────────────────────
    // Name is rendered for BOTH create and edit (rename: the save path POSTs
    // /api/agents/{name}/rename before the regular PUT).
    var nameInput = own(ui.textInput({
      id: 'studio-name',
      value: cfg.name || '',
      placeholder: 'agent-name',
      dataset: { field: 'name' },
      onInput: function () { nameField.setError(null); dirty(); }
    }));
    var nameField = ui.field({ label: 'Name', control: nameInput });
    var descriptionInput = own(ui.textInput({
      id: 'studio-description',
      value: cfg.description || '',
      placeholder: 'What does this agent do?',
      dataset: { field: 'description' },
      onInput: dirty
    }));
    var identity = ui.section({
      title: 'Identity',
      children: [
        nameField.el,
        ui.field({ label: 'Description', control: descriptionInput }).el
      ]
    });

    // ── LLM configuration ───────────────────────────────────────────
    var providerSelect = own(ui.select({
      id: 'studio-provider',
      options: [{ value: '', label: 'placeholder' }],
      dataset: { field: 'provider_config_id' }
    }));
    // Native <select> for every provider type: free type-ahead, and it scales to
    // OpenRouter's ~370 models (a datalist variant trapped operators with a stale
    // selection).
    var modelSelect = own(ui.select({
      id: 'studio-model',
      options: [{ value: '', label: 'Select a provider first', disabled: true }],
      dataset: { field: 'llm_model' }
    }));
    var loadingEl = document.createElement('span');
    loadingEl.className = 'model-loading';
    loadingEl.setAttribute('aria-live', 'polite');
    var modelWrap = document.createElement('div');
    modelWrap.className = 'field-model-wrap';
    modelWrap.appendChild(modelSelect);
    modelWrap.appendChild(loadingEl);

    // Ollama models surface their /api/show capabilities here.
    var capsEl = document.createElement('div');
    capsEl.className = 'model-capabilities';
    capsEl.setAttribute('data-testid', 'model-capabilities');
    capsEl.setAttribute('role', 'status');
    capsEl.setAttribute('aria-live', 'polite');

    var vramEl = document.createElement('div');
    vramEl.className = 'studio-vram-warning';
    vramEl.setAttribute('role', 'status');
    vramEl.setAttribute('aria-live', 'polite');

    // Test: next to the provider fields. Its disabled state follows the LIVE
    // provider select (the picker's recomputeTestDisabled), so an unsaved provider
    // change can be tested before saving.
    var testButton = ui.button({
      variant: 'secondary',
      icon: 'play',
      label: 'Test',
      testid: 'test-provider-btn',
      onClick: function () { if (callbacks.onTestProvider) callbacks.onTestProvider(); }
    });
    testButton.title = 'Tests provider connectivity. Does not validate the agent’s full config.';
    var testStatus = ui.status({ testid: 'test-provider-result' });
    testStatus.el.hidden = true;
    var testRow = document.createElement('div');
    testRow.className = 'test-provider-row';
    testRow.appendChild(testButton);
    testRow.appendChild(testStatus.el);

    var llm = ui.section({
      title: 'LLM configuration',
      children: [
        ui.field({ label: 'Provider', control: providerSelect }).el,
        ui.field({ label: 'Model', control: modelSelect, host: modelWrap }).el,
        capsEl,
        vramEl,
        testRow
      ]
    });

    // ── System prompt ───────────────────────────────────────────────
    // The section title is the visible heading; the field's label is visually
    // hidden (the programmatic association, WCAG 1.3.1/4.1.2).
    var promptInput = own(ui.textarea({
      id: 'studio-system-prompt',
      rows: 8,
      value: cfg.system_prompt || '',
      placeholder: 'Instructions for the agent...',
      dataset: { field: 'system_prompt' },
      onInput: dirty
    }));
    var promptSection = ui.section({
      title: 'System prompt',
      children: [ui.field({ label: 'System prompt', labelHidden: true, control: promptInput }).el]
    });

    // ── Behavior ────────────────────────────────────────────────────
    function numberInput(id, field, value, min, max) {
      var input = own(ui.textInput({
        id: id,
        type: 'number',
        value: value,
        dataset: { field: field },
        onInput: dirty
      }));
      input.min = String(min);
      input.max = String(max);
      input.classList.add('field-input-short');
      return input;
    }
    var retentionInput = numberInput('studio-retention-days', 'chat_history_retention_days',
      cfg.chat_history_retention_days || 30, 1, 365);
    var iterationsInput = numberInput('studio-max-iterations', 'max_iterations',
      cfg.max_iterations || 20, 1, 100);
    var behavior = ui.section({
      title: 'Behavior',
      children: [
        ui.field({ label: 'Chat history retention (days)', control: retentionInput }).el,
        ui.field({ label: 'Max iterations', control: iterationsInput }).el
      ]
    });

    // The stored-value-changed note: shown only while a field the operator edited
    // had its stored value change underneath it (see applyStored).
    var storedNote = ui.status({ testid: 'agent-stored-value-changed' });
    storedNote.el.hidden = true;

    panel.appendChild(storedNote.el);
    panel.appendChild(identity.el);
    panel.appendChild(llm.el);
    panel.appendChild(promptSection.el);
    panel.appendChild(behavior.el);

    // ── Danger zone (existing agents only) ──────────────────────────
    // Both actions arm through the library (App.ui.confirm) and commit through
    // the controller's callbacks. They read the stored name from the controller,
    // not the button.
    var danger = null;
    if (!isCreate) {
      danger = ui.dangerZone({
        actions: [
          {
            label: 'Delete agent',
            testid: 'delete-agent-btn',
            confirmLabel: 'Confirm delete?',
            dataset: { name: cfg.name || '' },
            onConfirm: function (revert) { if (callbacks.onDelete) callbacks.onDelete(revert); }
          },
          {
            label: 'Purge now',
            testid: 'purge-history-btn',
            confirmLabel: 'Confirm purge?',
            dataset: { name: cfg.name || '' },
            onConfirm: function (revert) { if (callbacks.onPurge) callbacks.onPurge(revert); }
          }
        ]
      });
      panel.appendChild(danger.el);
    }

    // ── Patching ────────────────────────────────────────────────────
    function fillProviders(c, provs) {
      var nodes = [];
      var found = false;
      if (!c.provider_config_id) {
        nodes.push(option('', 'No provider — add one in Library', { disabled: true, selected: true }));
      }
      for (var p = 0; p < provs.length; p++) {
        var prov = provs[p];
        var isSel = c.provider_config_id === prov.id;
        if (isSel) found = true;
        nodes.push(option(prov.id, prov.name + ' (' + prov.type + ')', { selected: isSel }));
      }
      if (c.provider_config_id && !found) {
        nodes.push(option(c.provider_config_id, 'Unknown provider (' + c.provider_config_id + ')',
          { selected: true }));
      }
      providerSelect.replaceChildren.apply(providerSelect, nodes);
    }

    function setTestResult(state, text) {
      testStatus.set(state, text);
      testStatus.el.hidden = false;
    }

    function clearTestResult() {
      testStatus.el.hidden = true;
      testStatus.set('idle', '');
    }

    var STORED_FIELDS = [
      { key: 'description', label: 'description', input: descriptionInput },
      { key: 'system_prompt', label: 'system prompt', input: promptInput }
    ];

    // Write `stored` ({description, system_prompt}) into the clean fields. `baseline`
    // is the parsed snapshot. A field whose stored value did not change is left
    // alone; a changed one is written when the field is clean; a changed one the
    // operator edited is left and its key returned (the conflicts).
    function applyStored(stored, baseline) {
      var conflicts = [];
      STORED_FIELDS.forEach(function (f) {
        if (!stored || typeof stored[f.key] !== 'string') return;
        var next = stored[f.key];
        var base = baseline && typeof baseline[f.key] === 'string' ? baseline[f.key] : null;
        if (base === next || f.input.value === next) return;
        if (f.input.value === base) {
          f.input.value = next;
        } else {
          conflicts.push(f.key);
        }
      });
      return conflicts;
    }

    var noteTimer = null;
    // Show the note for the given field keys, or hide it for null / none.
    function setStoredChangeNote(fields) {
      var parts = [];
      STORED_FIELDS.forEach(function (f) {
        if (fields && fields.indexOf(f.key) !== -1) {
          parts.push('The stored ' + f.label + ' changed. Save will replace it with your text.');
        }
      });
      noteTimer = clearTimeout(noteTimer);
      if (parts.length === 0) {
        storedNote.el.hidden = true;
        storedNote.set('idle', '');
        return;
      }
      // A live region announces a change of its text, not its appearance: show the
      // empty node first and fill it one tick later (SC 4.1.3).
      if (storedNote.el.hidden) {
        storedNote.set('warning', '');
        storedNote.el.hidden = false;
        noteTimer = setTimeout(function () {
          noteTimer = null;
          storedNote.set('warning', parts.join(' '));
        }, 0);
      } else {
        storedNote.set('warning', parts.join(' '));
      }
    }

    function setAgent(a, provs) {
      setStoredChangeNote(null);
      var c = a || defaults(provs);
      nameField.setError(null);
      nameInput.value = c.name || '';
      descriptionInput.value = c.description || '';
      fillProviders(c, provs || []);
      // The model list is refetched by the picker's wire (pendingValue = the stored
      // model); until it lands the select shows its placeholder.
      modelSelect.replaceChildren(option('', 'Select a provider first',
        { disabled: true, selected: true }));
      delete modelSelect.dataset.pendingValue;
      loadingEl.textContent = '';
      capsEl.textContent = '';
      vramEl.textContent = '';
      vramEl.classList.remove('visible');
      promptInput.value = c.system_prompt || '';
      retentionInput.value = String(c.chat_history_retention_days || 30);
      iterationsInput.value = String(c.max_iterations || 20);
      testButton.disabled = !providerSelect.value;
      clearTestResult();
    }

    // Initial values: the same path as a patch, so the two cannot drift.
    setAgent(agent, providers);

    return {
      providerSelect: providerSelect,
      modelSelect: modelSelect,
      testButton: testButton,
      dangerZone: danger,
      setAgent: setAgent,
      setNameError: function (msg) { nameField.setError(msg || null); },
      applyStored: applyStored,
      setStoredChangeNote: setStoredChangeNote,
      setTestResult: setTestResult,
      clearTestResult: clearTestResult
    };
  }

  window.App.studio.renderGeneralTab = renderGeneralTab;
})();
