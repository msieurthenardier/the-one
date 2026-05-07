// App.admin.renderProviderEditor — provider-editor scaffold (F6 leg 03).
//
// Builds the editor surface mirroring studio's agent-editor (F5 leg 03):
//   <div class="editor-header">
//     <div class="editor-header-text">
//       <h1 class="editor-title">{name | "New Provider"}</h1>
//       <p class="editor-subtitle">{type · base_url}</p>  (edit only)
//     </div>
//     <div class="form-actions">
//       <button class="back-btn">← Back</button>
//       <button class="cancel-btn" disabled>Cancel</button>
//       <button class="save-btn" disabled>{Save | Create}</button>
//       <button class="test-provider-btn">Test</button>  (edit only)
//       <span class="editor-error"></span>
//     </div>
//   </div>
//   <div class="editor-section">
//     <div class="section-title">Connection</div>
//     {name + type + base_url + api_key fields}
//     <div class="test-result"></div>
//   </div>
//   <div class="editor-section">                    (edit only)
//     <div class="section-title">Models</div>
//     <div class="provider-models"></div>
//   </div>
//   <div class="editor-section danger-zone">        (edit only)
//     <div class="section-title danger-zone-title">Danger Zone</div>
//     <button class="delete-btn">Delete Provider</button>
//   </div>
//
// callbacks: { onBack, onCancel, onSaveSuccess, onDeleteSuccess, getTypeDefaults }
//
// Editor Delete uses App.confirmDelete (canonical destructive-confirm helper)
// since F6 leg 04. The agent-usage hard-block remains as a pre-confirmDelete
// gate (no confirm flow when agents reference the provider).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  function renderProviderEditor(container, provider, providerTypes, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !provider;
    var name = isCreate ? 'New Provider' : (provider.name || '');

    // ── Header HTML ─────────────────────────────────────────────────
    var html = '';
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h1 class="editor-title">' + escapeHtml(name) + '</h1>';
    if (!isCreate) {
      var subtitleParts = [escapeHtml(provider.type)];
      if (provider.base_url) subtitleParts.push(escapeHtml(provider.base_url));
      html += '<p class="editor-subtitle">' + subtitleParts.join(' · ') + '</p>';
    }
    html += '</div>';

    // ── Action cluster ──────────────────────────────────────────────
    html += '<div class="form-actions">';
    html += '<button type="button" class="btn-outlined-cyan back-btn" data-testid="back-provider-btn" aria-label="Back to provider list">' + window.App.icon('arrow-left') + ' Back</button>';
    html += '<button type="button" class="btn-outlined-cyan cancel-btn" data-testid="cancel-provider-btn" disabled>Cancel</button>';
    html += '<button type="button" class="btn-filled-cyan save-btn" data-testid="save-provider-btn" disabled>' + (isCreate ? 'Create' : 'Save') + '</button>';
    if (!isCreate) {
      html += '<button type="button" class="btn-outlined-cyan test-provider-btn" data-testid="test-connection-btn">Test</button>';
    }
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // ── Connection section ──────────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Connection</div>';
    html += renderConnectionFields(provider, providerTypes, callbacks);
    html += '<div class="test-result" aria-live="polite"></div>';
    html += '</div>';

    // ── Models section (edit only) ──────────────────────────────────
    if (!isCreate) {
      html += '<div class="editor-section">';
      html += '<div class="section-title">Models</div>';
      html += '<div class="provider-models"></div>';
      html += '</div>';
    }

    // ── Danger Zone section (edit only) ─────────────────────────────
    if (!isCreate) {
      html += '<div class="editor-section danger-zone">';
      html += '<div class="section-title danger-zone-title">Danger Zone</div>';
      html += '<button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-provider-btn" data-name="' + escapeAttr(provider.name || '') + '"><span data-confirm-title>Delete Provider</span></button>';
      // Hard-block message banner — shown when the provider is in use by
      // ≥1 agents. Sibling of the button (NOT inside it) so long agent-name
      // lists don't deform the button. aria-live="assertive" announces
      // when revealed. F6 HAT refinement.
      html += '<div class="action-blocked-message" data-testid="delete-blocked-message" role="status" aria-live="assertive" hidden></div>';
      html += '</div>';
    }

    container.innerHTML = html;

    wireEditorEvents(container, provider, providerTypes, callbacks);

    // Mount the Models panel synchronously in edit mode (mirrors agent-editor's
    // synchronous General-tab mount so tests find selectors immediately).
    if (!isCreate && window.App.admin.renderProviderModels) {
      var modelsHost = container.querySelector('.provider-models');
      if (modelsHost) {
        window.App.admin.renderProviderModels(modelsHost, provider);
      }
    }
  }

  function renderConnectionFields(provider, providerTypes, callbacks) {
    /* Render the four field rows: name, type, base_url, api_key.
       Reuses pre-leg-03 admin.js:314-351 markup verbatim (DOM/selectors
       preserved for backward compat with tests that locate by #pf-name etc.). */
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !provider;
    var type = isCreate ? '' : provider.type;
    var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(type)) || { base_url: '', showBaseUrl: false, showApiKey: false };

    var html = '';
    // Name
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="pf-name">Name</label>';
    html += '<input class="field-input admin-pf-input" id="pf-name" data-field="name" value="' + escapeAttr(isCreate ? '' : provider.name) + '" placeholder="My Provider" />';
    html += '</div>';

    // Type
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="pf-type">Type</label>';
    html += '<select class="field-input field-select admin-pf-input admin-pf-select" id="pf-type" data-field="type">';
    if (isCreate) html += '<option value="" disabled selected>Select a provider…</option>';
    for (var t = 0; t < providerTypes.length; t++) {
      var pt = providerTypes[t];
      html += '<option value="' + escapeAttr(pt.value) + '"' + (!isCreate && type === pt.value ? ' selected' : '') + '>' + escapeHtml(pt.label) + '</option>';
    }
    html += '</select>';
    html += '</div>';

    // Base URL
    var baseUrlValue = isCreate ? defaults.base_url : provider.base_url;
    html += '<div class="field-row admin-pf-row admin-pf-base-url' + (defaults.showBaseUrl ? '' : ' is-hidden') + '">';
    html += '<label for="pf-base-url">Base URL</label>';
    html += '<input class="field-input admin-pf-input" id="pf-base-url" data-field="base_url" value="' + escapeAttr(baseUrlValue || '') + '" placeholder="https://..." />';
    html += '</div>';

    // API Key (canonical .api-key-wrap + .api-key-eye)
    var apiKeyValue = isCreate ? '' : (provider.api_key || '');
    html += '<div class="field-row admin-pf-row admin-pf-api-key' + (defaults.showApiKey ? '' : ' is-hidden') + '">';
    html += '<label for="pf-api-key">API Key</label>';
    html += '<div class="api-key-wrap">';
    html += '<input class="field-input admin-pf-input admin-pf-password" id="pf-api-key" type="password" data-field="api_key" value="' + escapeAttr(apiKeyValue) + '" placeholder="sk-..." />';
    html += '<button class="api-key-eye" type="button" title="Show/Hide" aria-label="Show password">' + window.App.icon('eye') + '</button>';
    html += '</div>';
    html += '</div>';

    // OpenRouter ranking headers (Decision 3) — operator-configurable
    // optional inputs. Always rendered (so the type-change handler can
    // show/hide them via .is-hidden); hidden initially for non-openrouter
    // types. Empty values are dropped at save time so the server sees the
    // headers as absent.
    var orHidden = defaults.showOpenRouterConfig ? '' : ' is-hidden';
    var refererVal = (provider && provider.config && provider.config.referer) || '';
    var titleVal = (provider && provider.config && provider.config.title) || '';
    html += '<div class="field-row admin-pf-row admin-pf-openrouter-config' + orHidden + '">';
    html += '<label for="pf-referer">App URL (optional)</label>';
    html += '<input type="text" id="pf-referer" class="field-input admin-pf-input"';
    html += ' data-field="config.referer"';
    html += ' placeholder="https://your-app.example.com"';
    html += ' value="' + escapeAttr(refererVal) + '" />';
    html += '<small class="field-hint">Sent as HTTP-Referer for OpenRouter app rankings.</small>';
    html += '</div>';
    html += '<div class="field-row admin-pf-row admin-pf-openrouter-config' + orHidden + '">';
    html += '<label for="pf-title">App Name (optional, max 64)</label>';
    html += '<input type="text" id="pf-title" class="field-input admin-pf-input"';
    html += ' data-field="config.title"';
    html += ' maxlength="64"';
    html += ' value="' + escapeAttr(titleVal) + '" />';
    html += '<small class="field-hint">Sent as X-Title for OpenRouter app rankings.</small>';
    html += '</div>';

    return html;
  }

  function getFormSnapshot(container) {
    var data = {};
    var fields = container.querySelectorAll('[data-field]');
    for (var i = 0; i < fields.length; i++) {
      data[fields[i].dataset.field] = fields[i].value;
    }
    return JSON.stringify(data);
  }

  function wireEditorEvents(container, provider, providerTypes, callbacks) {
    /* Wire: type-change show/hide, eye-toggle, dirty tracking, Back, Cancel,
       Save, Test, Delete. Replaces pre-leg-03 admin.js:385-558 with these
       substitutions:
         - .admin-pf-cancel        → .cancel-btn
         - .admin-pf-save          → .save-btn
         - .admin-pf-test          → .test-provider-btn
         - .admin-pf-eye           → .api-key-eye
         - .admin-pf-error         → .editor-error
         - .admin-pf-test-result   → .test-result
         - .admin-pf-testing       → .test-result-pending (span class)
         - .admin-pf-test-ok       → .test-result-ok      (span class)
         - .admin-pf-test-fail     → .test-result-fail    (span class)
       Adds: MASKED_SENTINEL capture (originalMaskedApiKey); dirty-tracking
       shim (snapshot + checkDirty); .back-btn handler; .delete-btn handler
       with agent-usage hard-block + inline two-step. Sub-module owns the
       fetch (POST/PUT/DELETE/test); onSaveSuccess + onDeleteSuccess
       callbacks notify orchestrator AFTER successful response. */
    var isEdit = !!provider;
    var snapshot = getFormSnapshot(container);
    var dirty = false;
    /* MASKED_SENTINEL preservation (preserves admin.js:466-470 behavior).
       Capture the originally pre-filled (masked) api-key value so we can
       detect "user did not modify the field" on submit. In create mode this
       is empty. */
    var MASKED_SENTINEL = '__MASKED__';
    var originalMaskedApiKey = isEdit ? (provider.api_key || '') : '';

    function checkDirty() {
      var current = getFormSnapshot(container);
      dirty = current !== snapshot;
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = !dirty;
      if (cancelBtn) cancelBtn.disabled = !dirty;
      // F6 leg 04 bridge: notify orchestrator's mirror so navigation gates
      // (Back / section-nav / beforeunload) can read the same logical state.
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);
    }

    /* Wire input/change listeners on all .field-input + .field-select */
    var inputs = container.querySelectorAll('.field-input, .field-select');
    for (var i = 0; i < inputs.length; i++) {
      inputs[i].addEventListener('input', checkDirty);
      inputs[i].addEventListener('change', checkDirty);
    }

    /* Type-change: show/hide base_url + api_key + openrouter config rows +
       reset base_url default. Does NOT clobber api_key or config fields so
       values are preserved across provider-type switches. */
    var typeSelect = container.querySelector('[data-field="type"]');
    var baseUrlRow = container.querySelector('.admin-pf-base-url');
    var baseUrlInput = container.querySelector('[data-field="base_url"]');
    var apiKeyRow = container.querySelector('.admin-pf-api-key');
    var openrouterConfigRows = container.querySelectorAll('.admin-pf-openrouter-config');
    if (typeSelect) {
      typeSelect.addEventListener('change', function () {
        var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(typeSelect.value)) || {};
        baseUrlRow.classList.toggle('is-hidden', !defaults.showBaseUrl);
        apiKeyRow.classList.toggle('is-hidden', !defaults.showApiKey);
        baseUrlInput.value = defaults.base_url || '';
        for (var k = 0; k < openrouterConfigRows.length; k++) {
          openrouterConfigRows[k].classList.toggle('is-hidden', !defaults.showOpenRouterConfig);
        }
        checkDirty();
      });
    }

    /* Eye toggle. */
    var eyeBtn = container.querySelector('.api-key-eye');
    var passwordInput = container.querySelector('.admin-pf-password');
    if (eyeBtn && passwordInput) {
      eyeBtn.addEventListener('click', function () {
        if (passwordInput.type === 'password') {
          passwordInput.type = 'text';
          eyeBtn.innerHTML = window.App.icon('eye-off');
          eyeBtn.setAttribute('aria-label', 'Hide password');
        } else {
          passwordInput.type = 'password';
          eyeBtn.innerHTML = window.App.icon('eye');
          eyeBtn.setAttribute('aria-label', 'Show password');
        }
      });
    }

    /* Back. */
    var backBtn = container.querySelector('.back-btn');
    if (backBtn && callbacks.onBack) {
      backBtn.addEventListener('click', function () { callbacks.onBack(); });
    }

    /* Cancel: edit mode reverts; create mode delegates to onCancel (orchestrator
       handles the navigate-to-grid). */
    var cancelBtn = container.querySelector('.cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        if (isEdit) {
          // Revert to snapshot.
          var snap = JSON.parse(snapshot);
          var fields2 = container.querySelectorAll('[data-field]');
          for (var j = 0; j < fields2.length; j++) {
            fields2[j].value = snap[fields2[j].dataset.field] || '';
          }
          dirty = false;
          checkDirty();
        } else if (callbacks.onCancel) {
          callbacks.onCancel();
        }
      });
    }

    /* Save: editor sub-module owns the fetch. Orchestrator's
       onSaveSuccess callback handles state mutation + URL update. */
    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        var errorEl = container.querySelector('.editor-error');
        errorEl.textContent = '';
        var payload = collectFormData(container, callbacks, originalMaskedApiKey, MASKED_SENTINEL, isEdit);
        if (!payload) return; // validation failed; collectFormData wrote error
        var url = isEdit ? '/api/providers/' + encodeURIComponent(provider.id) : '/api/providers';
        var method = isEdit ? 'PUT' : 'POST';
        fetch(url, {
          method: method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || (isEdit ? 'Save failed' : 'Create failed')); });
            return r.json();
          })
          .then(function (updated) {
            window.App.showFlash(container, isEdit ? 'Provider saved' : 'Provider created');
            if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, !isEdit);
            // For create→edit transition the orchestrator re-renders the
            // editor with the new provider — closure is replaced. The
            // snapshot reset below only matters for the edit→edit case
            // where the editor stays mounted.
            if (isEdit) {
              snapshot = getFormSnapshot(container);
              dirty = false;
              checkDirty();
            }
          })
          .catch(function (err) {
            errorEl.textContent = err.message || String(err);
          });
      });
    }

    /* Test: only in edit mode. */
    var testBtn = container.querySelector('.test-provider-btn');
    if (testBtn && isEdit) {
      testBtn.addEventListener('click', function () {
        var resultEl = container.querySelector('.test-result');
        resultEl.innerHTML = '<span class="test-result-pending">Testing…</span>';
        testBtn.disabled = true;
        fetch('/api/providers/' + encodeURIComponent(provider.id) + '/test', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (result) {
            testBtn.disabled = false;
            if (result.status === 'ok') {
              resultEl.innerHTML = '<span class="test-result-ok">✓ ' + window.App.escapeHtml(result.detail || 'Connected') + '</span>';
              window.App.showFlash(container, 'Connection successful');
              // OQ4 resolution: editor sub-module owns its own DOM children.
              // Refresh the Models panel directly (no orchestrator round-trip).
              var modelsHost = container.querySelector('.provider-models');
              if (modelsHost && window.App.admin.renderProviderModels) {
                window.App.admin.renderProviderModels(modelsHost, provider);
              }
            } else {
              resultEl.innerHTML = '<span class="test-result-fail">✗ ' + window.App.escapeHtml(result.detail || 'Failed') + '</span>';
              window.App.showFlash(container, 'Connection failed', true);
            }
          })
          .catch(function (err) {
            testBtn.disabled = false;
            resultEl.innerHTML = '<span class="test-result-fail">✗ ' + window.App.escapeHtml(err.message || 'Request failed') + '</span>';
            window.App.showFlash(container, 'Connection test error', true);
          });
      });
    }

    /* Delete: only in edit mode. Agent-usage hard-block pre-gate +
       App.confirmDelete for the confirm flow (F6 leg 04). */
    var deleteBtn = container.querySelector('.delete-btn');
    if (deleteBtn && isEdit) {
      var deleteHardBlockTimer = null;
      var blockedMsgEl = container.querySelector('.action-blocked-message');

      function doDelete(btn, revertFn) {
        fetch('/api/providers/' + encodeURIComponent(provider.id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
            window.App.showFlash(container, 'Provider deleted');
            if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
          })
          .catch(function (err) {
            revertFn();
            window.App.showFlash(container, 'Error: ' + err.message, true);
          });
      }

      deleteBtn.addEventListener('click', function () {
        // OQ2 RESOLUTION: explicit "already armed → commit" branch removed.
        // App.confirmDelete (confirm.js:58-67) handles the second-click
        // commit internally when the button already has the .confirm-delete
        // class. The agent-usage pre-gate fetch on the second click is
        // wasted work but functionally harmless (result is ignored on the
        // commit path because the helper's class check beats us to
        // onConfirm).
        //
        // Pre-gate: agent-usage hard-block.
        fetch('/api/providers/' + encodeURIComponent(provider.id) + '/agents')
          .then(function (r) { return r.json(); })
          .then(function (data) {
            var agents = data.agents || [];
            if (agents.length > 0) {
              // Hard-block: surface the message in a sibling banner (NOT
              // inside the button, which would deform with long agent-name
              // lists). Button text stays "Delete Provider".
              if (blockedMsgEl) {
                blockedMsgEl.textContent = 'Used by: ' + agents.join(', ');
                blockedMsgEl.removeAttribute('hidden');
              }
              deleteBtn.disabled = true;
              if (deleteHardBlockTimer) clearTimeout(deleteHardBlockTimer);
              deleteHardBlockTimer = setTimeout(function () {
                deleteBtn.disabled = false;
                if (blockedMsgEl) {
                  blockedMsgEl.setAttribute('hidden', '');
                  blockedMsgEl.textContent = '';
                }
              }, 3000);
            } else {
              // No agent usage: arm via App.confirmDelete.
              window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
            }
          })
          .catch(function () {
            // Network failure on agent-usage check: fail open — arm anyway.
            window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
          });
      });
    }
  }

  function collectFormData(container, callbacks, originalMaskedApiKey, MASKED_SENTINEL, isEdit) {
    /* Validate + collect payload. Mirrors pre-leg-03 admin.js:440-477 (Save
       handler's prologue) but returns null + writes error when invalid.
       Preserves the MASKED_SENTINEL substitution from admin.js:466-470. */
    var errorEl = container.querySelector('.editor-error');
    var nameInput = container.querySelector('[data-field="name"]');
    var name = nameInput.value.trim();
    if (!name) {
      errorEl.textContent = 'Name is required.';
      return null;
    }
    var typeSelect = container.querySelector('[data-field="type"]');
    var selectedType = typeSelect.value;
    if (!selectedType) {
      errorEl.textContent = 'Type is required.';
      return null;
    }
    var defaults = (callbacks.getTypeDefaults && callbacks.getTypeDefaults(selectedType)) || {};
    var baseUrlInput = container.querySelector('[data-field="base_url"]');
    var baseUrl = baseUrlInput.value.trim();
    if (!defaults.showBaseUrl) baseUrl = defaults.base_url || '';
    if (!baseUrl && defaults.showBaseUrl) {
      errorEl.textContent = 'Base URL is required.';
      return null;
    }
    var apiKeyInput = container.querySelector('[data-field="api_key"]');
    var apiKey = apiKeyInput ? apiKeyInput.value : null;
    if (!apiKey) apiKey = null;
    /* MASKED_SENTINEL: if editing and the user did not modify the pre-filled
       (masked) value, send the sentinel so the backend preserves the existing
       stored key. Mirrors admin.js:466-470. */
    if (isEdit && originalMaskedApiKey && apiKey === originalMaskedApiKey) {
      apiKey = MASKED_SENTINEL;
    }
    var payload = { name: name, type: selectedType, base_url: baseUrl, api_key: apiKey };

    // OpenRouter optional ranking-header inputs (Task 9) — read values,
    // validate client-side (server re-validates), drop empty values so
    // the saved config doesn't carry empty-string keys.
    if (selectedType === 'openrouter') {
      var refererInput = container.querySelector('[data-field="config.referer"]');
      var titleInput = container.querySelector('[data-field="config.title"]');
      var orReferer = refererInput ? refererInput.value.trim() : '';
      var orTitle = titleInput ? titleInput.value.trim() : '';

      if (orReferer && /[\r\n\x00]/.test(orReferer)) {
        errorEl.textContent = 'App URL contains an invalid control character.';
        return null;
      }
      if (orReferer && !/^https?:\/\//i.test(orReferer)) {
        errorEl.textContent = 'App URL must start with http:// or https://.';
        return null;
      }
      if (orTitle && /[\r\n\x00]/.test(orTitle)) {
        errorEl.textContent = 'App Name contains an invalid control character.';
        return null;
      }

      var cfg = {};
      if (orReferer) cfg.referer = orReferer;
      if (orTitle) cfg.title = orTitle;
      payload.config = cfg;
    }

    return payload;
  }

  window.App.admin.renderProviderEditor = renderProviderEditor;
})();
