// App.studio.renderConnectorAccountEditor — Connector Account editor (M10 F2 L6).
//
// Structurally mirrors mcp-server-editor.js minus MCP-specific concerns
// (no transport-specific config, no OAuth, no tools list, no sandbox).
//
//   <div class="editor-header"> … </div>
//   <div class="editor-section">Connection</div>          (name, type, config kv)
//   <div class="editor-section">Credentials</div>         (secrets kv with __MASKED__ round-trip)
//   <div class="editor-section">Lifecycle</div>           (idle_timeout_seconds)
//   <div class="editor-section">Test Connection</div>     (edit-mode only — probe + banner)
//   <div class="editor-section danger-zone"> … </div>     (edit-mode only)
//
// Per-key __MASKED__ round-trip mirrors MCP exactly: each secret row
// captures `_originalMasked` via the data-original-masked attribute at
// mount time. At save time, if value === _originalMasked, the payload
// emits '__MASKED__' for that key and the backend preserves the stored
// secret (api.py:2192-2207 honors the sentinel per-key).
//
// "Create & Test" combined-action: the create-mode primary button does
// POST /api/connector-accounts → on 201 POST /test/connect → renders
// the probe report inline while studio.js transitions to edit-mode.
// The probe report is handed off via a module-level _pendingProbeReport
// because callbacks.onSaveSuccess(updated, true) unmounts this editor
// and mounts a fresh one in edit-mode (see studio.js:670-738); the
// fresh-editor render path picks up _pendingProbeReport and renders
// the banner before clearing the variable.
//
// callbacks: { onBack, onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange }
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var MASKED_SENTINEL = '__MASKED__';

  // ── Hand-off state for create+test → edit-mode banner ───────────────
  // Set by handleCreateAndTest BEFORE invoking callbacks.onSaveSuccess.
  // Read + cleared by the next render-edit-mode pass. Module-level so it
  // survives the unmount/mount cycle studio.js performs on isCreate=true.
  var _pendingProbeReport = null;

  // ── DoctorReport.status → LED class ────────────────────────────────
  // Verified at design review against static/css/components.css:861-895
  // (--success / --warning / --danger / --idle exist; no --error class).
  function statusLedClass(status) {
    switch (status) {
      case 'ok':
        return 'indicator-led--success';
      case 'degraded':
        return 'indicator-led--warning';
      case 'failed':
      case 'error':
        return 'indicator-led--danger';
      default:
        return 'indicator-led--idle';
    }
  }

  function statusAriaLabel(status) {
    switch (status) {
      case 'ok': return 'OK';
      case 'degraded': return 'Degraded';
      case 'failed': return 'Failed';
      case 'error': return 'Error';
      default: return status || 'Unknown';
    }
  }

  // ── Public entry point ──────────────────────────────────────────────

  function renderConnectorAccountEditor(container, account, types, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !account;
    var name = isCreate ? 'New Connector Account' : (account.name || '');
    var type = isCreate ? '' : (account.type || '');

    // ── Header ─────────────────────────────────────────────────────────
    var html = '';
    html += '<div class="connector-account-editor">';
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h1 class="editor-title">' + escapeHtml(name) + '</h1>';
    if (!isCreate) {
      var ttlSummary;
      if (account.idle_timeout_seconds == null) {
        ttlSummary = 'default TTL';
      } else {
        ttlSummary = account.idle_timeout_seconds + 's idle TTL';
      }
      var subtitleParts = [escapeHtml(type), escapeHtml(ttlSummary)];
      html += '<p class="editor-subtitle">' + subtitleParts.join(' · ') + '</p>';
    }
    html += '</div>';

    // Action cluster.
    var saveTestId = isCreate ? 'create-and-test-connector-account-btn' : 'save-connector-account-btn';
    var saveLabel = isCreate ? 'Create & Test' : 'Save';
    html += '<div class="form-actions">';
    html += '<button type="button" class="btn-outlined-primary back-btn" data-testid="back-connector-account-btn" aria-label="Back to connector accounts list">' + window.App.icon('arrow-left') + ' Back</button>';
    html += '<button type="button" class="btn-outlined-primary cancel-btn" data-testid="cancel-connector-account-btn" disabled>Cancel</button>';
    html += '<button type="button" class="btn-filled-primary save-btn" data-testid="' + saveTestId + '" disabled>' + escapeHtml(saveLabel) + '</button>';
    html += '<span class="editor-error" data-testid="connector-account-editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // ── Connection section ────────────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Connection</div>';
    html += renderConnectionFields(account, types, isCreate);
    html += '</div>';

    // ── Credentials section ───────────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Credentials</div>';
    html += renderSecretsKvTable(account);
    html += '</div>';

    // ── Lifecycle section ─────────────────────────────────────────────
    var idleValue = (!isCreate && account.idle_timeout_seconds != null) ? account.idle_timeout_seconds : '';
    var contValue = (!isCreate && account.session_continuation_seconds != null) ? account.session_continuation_seconds : '';
    html += '<div class="editor-section">';
    html += '<div class="section-title">Lifecycle</div>';

    // Pool idle timeout (F2)
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="cf-idle-timeout">Pool idle timeout (s)</label>';
    // No frontend min/max — backend Pydantic validator owns the truth
    // (1 <= value <= 604800). Empty string → null payload.
    html += '<input class="field-input admin-pf-input" id="cf-idle-timeout" type="number" ' +
            'data-field="idle_timeout_seconds" data-testid="connector-account-idle-timeout-input" ' +
            'value="' + escapeAttr(String(idleValue)) + '" placeholder="Use default (30 min)" />';
    html += '</div>';
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<small class="form-hint" data-testid="connector-account-idle-hint">' +
            'Warm connector connections are reaped after this many seconds of inactivity. ' +
            'Leave empty to use the system default (30 min).' +
            '</small>';
    html += '</div>';

    // Chat-session continuation window (F3 L5)
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="cf-continuation-window">Chat-session continuation window (s)</label>';
    // No frontend min/max — backend Pydantic validator owns the truth
    // (1 <= value <= 604800). Empty string → null payload.
    html += '<input class="field-input admin-pf-input" id="cf-continuation-window" type="number" ' +
            'data-field="session_continuation_seconds" data-testid="connector-account-continuation-input" ' +
            'value="' + escapeAttr(String(contValue)) + '" placeholder="Use default (24 hours)" />';
    html += '</div>';
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<small class="form-hint" data-testid="connector-account-continuation-hint">' +
            'Inbounds on the same conversation continue an existing chat session within this window. ' +
            'After this many seconds of platform silence, the next inbound starts a fresh session. ' +
            'Leave empty to use the system default (24 hours). ' +
            'Distinct from the pool idle timeout above, which controls gateway warm-keep — not chat-session lifecycle.' +
            '</small>';
    html += '</div>';

    html += '</div>';

    // ── Test Connection section (edit mode only) ──────────────────────
    if (!isCreate) {
      html += '<div class="editor-section connector-test-section">';
      html += '<div class="section-title">Test Connection</div>';
      html += '<div class="field-row admin-pf-row">';
      html += '<label></label>';
      html += '<div class="connector-test-actions">';
      html += '<button type="button" class="btn-outlined-primary connector-test-connection-btn" data-testid="connector-test-connection-btn">' +
              window.App.icon('refresh-cw') + ' Test connection</button>';
      html += '<span class="indicator-led indicator-led--idle connector-test-led" data-testid="connector-test-led" data-state="idle" aria-label="Not tested"></span>';
      html += '<span class="connector-test-message" data-testid="connector-test-message"></span>';
      html += '</div>';
      html += '</div>';
      html += '<div class="connector-test-status" data-testid="connector-test-status" hidden></div>';
      html += '<div class="connector-test-details-wrap" data-testid="connector-test-details-wrap" hidden>' +
              '<div data-testid="connector-test-details"></div>' +
              '</div>';
      html += '</div>';
    }

    // ── Danger Zone (edit only) ───────────────────────────────────────
    if (!isCreate) {
      html += '<div class="editor-section danger-zone">';
      html += '<div class="section-title danger-zone-title">Danger Zone</div>';
      html += '<button type="button" class="btn-muted-destructive delete-btn connector-delete-btn" data-testid="delete-connector-account-btn" data-name="' + escapeAttr(account.name || '') + '">' +
              window.App.icon('trash') +
              '<span data-confirm-title>Delete Connector Account</span>' +
              '</button>';
      html += '</div>';
    }

    html += '</div>'; // .connector-account-editor

    container.innerHTML = html;

    wireEditorEvents(container, account, types, callbacks, isCreate);

    // After mount, consume any pending probe report (set by the
    // create-and-test handler in the previous editor mount).
    if (!isCreate && _pendingProbeReport) {
      var report = _pendingProbeReport;
      _pendingProbeReport = null;
      renderTestConnectionBanner(container, report);
    }
  }

  // ── Field rendering ─────────────────────────────────────────────────

  function renderConnectionFields(account, types, isCreate) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var html = '';

    // Name
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="cf-name">Name</label>';
    html += '<input class="field-input admin-pf-input" id="cf-name" data-field="name" data-testid="connector-account-name-input" value="' +
            escapeAttr(isCreate ? '' : (account.name || '')) +
            '" placeholder="My Discord bot" />';
    html += '</div>';

    // Type — select on create, read-only display on edit. Mirrors MCP's
    // edit-time type immutability: changing type would invalidate the
    // config + secrets shape, so the type is locked once chosen.
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="cf-type">Type</label>';
    if (isCreate) {
      var typesList = Array.isArray(types) ? types : [];
      html += '<select class="field-input field-select admin-pf-input admin-pf-select" id="cf-type" data-field="type" data-testid="connector-account-type-select">';
      if (typesList.length === 0) {
        // Production-empty: no connector types registered yet.
        html += '<option value="" disabled selected>No connector types registered yet</option>';
      } else {
        html += '<option value="" disabled selected>Select a connector type</option>';
        for (var i = 0; i < typesList.length; i++) {
          var t = typesList[i];
          html += '<option value="' + escapeAttr(t.value) + '">' + escapeHtml(t.label) + '</option>';
        }
      }
      html += '</select>';
    } else {
      html += '<input class="field-input admin-pf-input" id="cf-type" data-field="type" data-testid="connector-account-type-readonly" value="' +
              escapeAttr(account.type || '') + '" readonly />';
    }
    html += '</div>';

    // Config kv editor — plaintext key-value rows.
    html += '<div class="field-row admin-pf-row connector-account-config-wrap">';
    html += '<label>Config</label>';
    html += '<div class="connector-account-config" data-testid="connector-account-config">';
    html += renderConfigKvTable(account);
    html += '</div>';
    html += '</div>';

    return html;
  }

  function collectConfigRows(account) {
    var rows = [];
    if (!account || !account.config) return rows;
    for (var k in account.config) {
      if (Object.prototype.hasOwnProperty.call(account.config, k)) {
        var v = account.config[k];
        var rendered;
        if (typeof v === 'string') {
          rendered = v;
        } else {
          rendered = JSON.stringify(v);
        }
        rows.push({ key: k, value: rendered });
      }
    }
    return rows;
  }

  function collectSecretRows(account) {
    var rows = [];
    if (!account || !account.secrets) return rows;
    for (var k in account.secrets) {
      if (Object.prototype.hasOwnProperty.call(account.secrets, k)) {
        var masked = String(account.secrets[k] == null ? '' : account.secrets[k]);
        rows.push({ key: k, value: masked, _originalMasked: masked });
      }
    }
    return rows;
  }

  function renderConfigKvTable(account) {
    var existingRows = collectConfigRows(account);
    var headHiddenClass = existingRows.length === 0 ? ' is-hidden' : '';
    var html = '<table class="connector-account-config-table" data-testid="connector-account-config-table">';
    html += '<thead class="connector-account-config-thead' + headHiddenClass + '">' +
            '<tr><th>Key</th><th>Value</th><th aria-label="Actions"></th></tr></thead>';
    html += '<tbody data-testid="connector-account-config-tbody">';
    for (var i = 0; i < existingRows.length; i++) {
      html += renderConfigRow(existingRows[i], i);
    }
    html += '</tbody></table>';
    html += '<button type="button" class="btn-outlined-primary connector-config-add-row-btn" data-testid="connector-config-add-row-btn">+ Add config row</button>';
    return html;
  }

  function renderConfigRow(row, idx) {
    var escapeAttr = window.App.escapeAttr;
    var html = '';
    html += '<tr class="connector-account-config-row" data-row-idx="' + idx + '">';
    html += '<td><input class="field-input config-key-input" data-field="config-key" data-row="' + idx + '" value="' + escapeAttr(row.key || '') + '" placeholder="key" /></td>';
    html += '<td><input class="field-input config-value-input" type="text" data-field="config-value" data-row="' + idx + '" value="' + escapeAttr(row.value || '') + '" placeholder="value" /></td>';
    html += '<td><button type="button" class="config-remove-row-btn" data-row="' + idx + '" aria-label="Remove row" title="Remove row">' + window.App.icon('trash') + '</button></td>';
    html += '</tr>';
    return html;
  }

  function renderSecretsKvTable(account) {
    var existingRows = collectSecretRows(account);
    var headHiddenClass = existingRows.length === 0 ? ' is-hidden' : '';
    var html = '<table class="connector-account-secrets-table" data-testid="connector-account-secrets-table">';
    html += '<thead class="connector-account-secrets-thead' + headHiddenClass + '">' +
            '<tr><th>Key</th><th>Value</th><th aria-label="Actions"></th></tr></thead>';
    html += '<tbody data-testid="connector-account-secrets-tbody">';
    for (var i = 0; i < existingRows.length; i++) {
      html += renderSecretRow(existingRows[i], i);
    }
    html += '</tbody></table>';
    html += '<button type="button" class="btn-outlined-primary connector-secrets-add-row-btn" data-testid="connector-secrets-add-row-btn">+ Add credential row</button>';
    return html;
  }

  function renderSecretRow(row, idx) {
    var escapeAttr = window.App.escapeAttr;
    var origMasked = row._originalMasked || '';
    var html = '';
    html += '<tr class="connector-account-secret-row" data-row-idx="' + idx + '">';
    html += '<td><input class="field-input secret-key-input" data-field="secret-key" data-row="' + idx + '" value="' + escapeAttr(row.key || '') + '" placeholder="KEY" /></td>';
    html += '<td><div class="api-key-wrap">';
    html += '<input class="field-input secret-value-input kv-value-secret" type="password" data-field="secret-value" data-row="' + idx + '" value="' + escapeAttr(row.value || '') + '" data-original-masked="' + escapeAttr(origMasked) + '" placeholder="value" />';
    html += '<button class="api-key-eye secret-eye-btn" type="button" data-row="' + idx + '" aria-label="Show value">' + window.App.icon('eye') + '</button>';
    html += '</div></td>';
    html += '<td><button type="button" class="secret-remove-row-btn" data-row="' + idx + '" aria-label="Remove row" title="Remove row">' + window.App.icon('trash') + '</button></td>';
    html += '</tr>';
    return html;
  }

  // ── Form snapshot + dirty tracking ──────────────────────────────────

  function getFormSnapshot(container) {
    var staticData = {};
    var staticFields = ['name', 'type', 'idle_timeout_seconds', 'session_continuation_seconds'];
    for (var i = 0; i < staticFields.length; i++) {
      var el = container.querySelector('[data-field="' + staticFields[i] + '"]');
      staticData[staticFields[i]] = el ? el.value : '';
    }

    var configRows = [];
    var configRowEls = container.querySelectorAll('.connector-account-config-table tbody tr.connector-account-config-row');
    for (var c = 0; c < configRowEls.length; c++) {
      var crow = configRowEls[c];
      var ckey = crow.querySelector('.config-key-input');
      var cval = crow.querySelector('.config-value-input');
      configRows.push({
        key: ckey ? ckey.value : '',
        value: cval ? cval.value : ''
      });
    }

    var secretRows = [];
    var secretRowEls = container.querySelectorAll('.connector-account-secrets-table tbody tr.connector-account-secret-row');
    for (var s = 0; s < secretRowEls.length; s++) {
      var srow = secretRowEls[s];
      var skey = srow.querySelector('.secret-key-input');
      var sval = srow.querySelector('.secret-value-input');
      secretRows.push({
        key: skey ? skey.value : '',
        value: sval ? sval.value : ''
      });
    }

    return JSON.stringify({ static: staticData, config: configRows, secrets: secretRows });
  }

  // ── Event wiring ────────────────────────────────────────────────────

  function wireEditorEvents(container, account, types, callbacks, isCreate) {
    var isEdit = !isCreate;
    var snapshot = getFormSnapshot(container);
    var dirty = false;
    var nextConfigRowIdx = container.querySelectorAll('.connector-account-config-table tbody tr.connector-account-config-row').length;
    var nextSecretRowIdx = container.querySelectorAll('.connector-account-secrets-table tbody tr.connector-account-secret-row').length;

    function checkDirty() {
      var current = getFormSnapshot(container);
      dirty = (current !== snapshot);
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = !dirty;
      if (cancelBtn) cancelBtn.disabled = !dirty;
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);
    }

    function recaptureSnapshot() {
      snapshot = getFormSnapshot(container);
      dirty = false;
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = true;
      if (cancelBtn) cancelBtn.disabled = true;
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
    }

    // ── Static field listeners ────────────────────────────────────────
    function attachStaticListeners() {
      var inputs = container.querySelectorAll(
        '.editor-section .field-input:not(.config-key-input):not(.config-value-input):not(.secret-key-input):not(.secret-value-input), ' +
        '.editor-section .field-select'
      );
      for (var i = 0; i < inputs.length; i++) {
        inputs[i].addEventListener('input', checkDirty);
        inputs[i].addEventListener('change', checkDirty);
      }
    }
    attachStaticListeners();

    // ── Config kv table delegated events ──────────────────────────────
    var configTable = container.querySelector('.connector-account-config-table');
    if (configTable) {
      configTable.addEventListener('input', function (e) {
        var target = e.target;
        if (!target) return;
        if (target.classList && (target.classList.contains('config-key-input') || target.classList.contains('config-value-input'))) {
          checkDirty();
        }
      });
      configTable.addEventListener('click', function (e) {
        var target = e.target;
        if (!target) return;
        var removeBtn = target.closest && target.closest('.config-remove-row-btn');
        if (removeBtn) {
          var rrow = removeBtn.closest('tr.connector-account-config-row');
          if (rrow) {
            rrow.parentNode.removeChild(rrow);
            updateConfigHeadVisibility(container);
            checkDirty();
          }
        }
      });
    }
    var configAddBtn = container.querySelector('.connector-config-add-row-btn');
    if (configAddBtn) {
      configAddBtn.addEventListener('click', function () {
        var tbody = container.querySelector('.connector-account-config-table tbody');
        if (!tbody) return;
        var idx = nextConfigRowIdx++;
        var tmp = document.createElement('tbody');
        tmp.innerHTML = renderConfigRow({ key: '', value: '' }, idx);
        var newTr = tmp.querySelector('tr.connector-account-config-row');
        if (newTr) {
          tbody.appendChild(newTr);
          updateConfigHeadVisibility(container);
          checkDirty();
        }
      });
    }

    // ── Secrets kv table delegated events ─────────────────────────────
    var secretsTable = container.querySelector('.connector-account-secrets-table');
    if (secretsTable) {
      secretsTable.addEventListener('input', function (e) {
        var target = e.target;
        if (!target) return;
        if (target.classList && (target.classList.contains('secret-key-input') || target.classList.contains('secret-value-input'))) {
          checkDirty();
        }
      });
      secretsTable.addEventListener('click', function (e) {
        var target = e.target;
        if (!target) return;
        var eyeBtn = target.closest && target.closest('.secret-eye-btn');
        if (eyeBtn) {
          var row = eyeBtn.closest('tr.connector-account-secret-row');
          if (row) {
            var valueInput = row.querySelector('.secret-value-input');
            if (valueInput) {
              if (valueInput.type === 'password') {
                valueInput.type = 'text';
                eyeBtn.innerHTML = window.App.icon('eye-off');
                eyeBtn.setAttribute('aria-label', 'Hide value');
              } else {
                valueInput.type = 'password';
                eyeBtn.innerHTML = window.App.icon('eye');
                eyeBtn.setAttribute('aria-label', 'Show value');
              }
            }
          }
          return;
        }
        var removeBtn = target.closest && target.closest('.secret-remove-row-btn');
        if (removeBtn) {
          var rrow = removeBtn.closest('tr.connector-account-secret-row');
          if (rrow) {
            rrow.parentNode.removeChild(rrow);
            updateSecretsHeadVisibility(container);
            checkDirty();
          }
        }
      });
    }
    var secretsAddBtn = container.querySelector('.connector-secrets-add-row-btn');
    if (secretsAddBtn) {
      secretsAddBtn.addEventListener('click', function () {
        var tbody = container.querySelector('.connector-account-secrets-table tbody');
        if (!tbody) return;
        var idx = nextSecretRowIdx++;
        var tmp = document.createElement('tbody');
        tmp.innerHTML = renderSecretRow({ key: '', value: '', _originalMasked: '' }, idx);
        var newTr = tmp.querySelector('tr.connector-account-secret-row');
        if (newTr) {
          tbody.appendChild(newTr);
          updateSecretsHeadVisibility(container);
          checkDirty();
        }
      });
    }

    // ── Back ──────────────────────────────────────────────────────────
    var backBtn = container.querySelector('.back-btn');
    if (backBtn && callbacks.onBack) {
      backBtn.addEventListener('click', function () { callbacks.onBack(); });
    }

    // ── Cancel ────────────────────────────────────────────────────────
    var cancelBtn = container.querySelector('.cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        if (isEdit) {
          // Re-render the editor from the source — clobbers all in-flight
          // edits including kv-rows the operator added/removed.
          renderConnectorAccountEditor(container, account, types, callbacks);
        } else if (callbacks.onCancel) {
          callbacks.onCancel();
        }
      });
    }

    // ── Save / Create & Test ──────────────────────────────────────────
    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        var errorEl = container.querySelector('.editor-error');
        if (errorEl) errorEl.textContent = '';

        var payload = collectFormData(container, account, isEdit);
        if (!payload) return;

        if (isEdit) {
          handleSaveEdit(account, payload, container, callbacks, saveBtn, recaptureSnapshot);
        } else {
          handleCreateAndTest(payload, container, types, callbacks, saveBtn);
        }
      });
    }

    // ── Test Connection (edit only) ───────────────────────────────────
    var testBtn = container.querySelector('[data-testid="connector-test-connection-btn"]');
    if (testBtn && isEdit) {
      testBtn.addEventListener('click', function () {
        handleTestConnection(account.id, container, testBtn);
      });
    }

    // ── Delete (edit only) ────────────────────────────────────────────
    var deleteBtn = container.querySelector('[data-testid="delete-connector-account-btn"]');
    if (deleteBtn && isEdit) {
      function doDelete(btn, revertFn) {
        fetch('/api/connector-accounts/' + encodeURIComponent(account.id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error((e && e.detail) || 'Delete failed'); });
            window.App.showFlash(container, 'Connector account deleted');
            if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
          })
          .catch(function (err) {
            revertFn();
            window.App.showFlash(container, 'Error: ' + err.message, true);
          });
      }
      deleteBtn.addEventListener('click', function () {
        window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
      });
    }
  }

  // ── Save handlers ───────────────────────────────────────────────────

  function handleSaveEdit(account, payload, container, callbacks, saveBtn, recaptureSnapshot) {
    var errorEl = container.querySelector('.editor-error');
    saveBtn.disabled = true;
    var originalLabel = saveBtn.textContent;
    saveBtn.textContent = 'Saving…';

    fetch('/api/connector-accounts/' + encodeURIComponent(account.id), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            var detail;
            try {
              var parsed = JSON.parse(body);
              detail = parsed && parsed.detail;
            } catch (_) { /* non-JSON body */ }
            if (Array.isArray(detail)) {
              detail = detail.map(function (d) {
                var loc = (d.loc || []).join('.');
                return loc ? (loc + ': ' + d.msg) : d.msg;
              }).join(' | ');
            }
            if (!detail) {
              var snippet = (body || '').trim().slice(0, 500);
              detail = 'Server error ' + r.status + ' ' + r.statusText +
                       (snippet ? ': ' + snippet : '');
            }
            throw new Error(detail || 'Save failed');
          });
        }
        return r.json();
      })
      .then(function (updated) {
        window.App.showFlash(container, 'Connector account saved');
        saveBtn.textContent = originalLabel;
        if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, false);
        recaptureSnapshot();
      })
      .catch(function (err) {
        saveBtn.textContent = originalLabel;
        saveBtn.disabled = false;
        if (errorEl) errorEl.textContent = err.message || String(err);
      });
  }

  function handleCreateAndTest(payload, container, types, callbacks, saveBtn) {
    var errorEl = container.querySelector('.editor-error');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Creating…';

    fetch('/api/connector-accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            var detail;
            try {
              var parsed = JSON.parse(body);
              detail = parsed && parsed.detail;
            } catch (_) { /* non-JSON */ }
            if (Array.isArray(detail)) {
              detail = detail.map(function (d) {
                var loc = (d.loc || []).join('.');
                return loc ? (loc + ': ' + d.msg) : d.msg;
              }).join(' | ');
            }
            if (!detail) {
              var snippet = (body || '').trim().slice(0, 500);
              detail = 'Server error ' + r.status + ' ' + r.statusText +
                       (snippet ? ': ' + snippet : '');
            }
            throw new Error(detail || 'Create failed');
          });
        }
        return r.json();
      })
      .then(function (newAccount) {
        saveBtn.textContent = 'Testing…';
        return fetch('/api/connector-accounts/' + encodeURIComponent(newAccount.id) + '/test/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        }).then(function (probeResp) {
          // Probe failures during create+test are surfaced as a banner,
          // NOT thrown — the account was successfully persisted.
          return probeResp.json().catch(function () {
            return { status: 'error', message: 'Probe response was not JSON', details: {} };
          }).then(function (probeData) {
            return { account: newAccount, probe: probeData };
          });
        }, function (probeErr) {
          // Network-level failure on the probe — still transition to
          // edit-mode but surface the probe failure as an error banner.
          return {
            account: newAccount,
            probe: {
              status: 'error',
              message: 'Probe network error: ' + (probeErr && probeErr.message ? probeErr.message : String(probeErr)),
              details: {}
            }
          };
        });
      })
      .then(function (result) {
        window.App.showFlash(container, 'Connector account created');
        // Hand off the probe report to the next render-edit-mode pass.
        _pendingProbeReport = result.probe;
        if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(result.account, true);
      })
      .catch(function (err) {
        saveBtn.textContent = 'Create & Test';
        saveBtn.disabled = false;
        if (errorEl) errorEl.textContent = err.message || String(err);
      });
  }

  // ── Form payload assembly ───────────────────────────────────────────

  function collectFormData(container, account, isEdit) {
    var errorEl = container.querySelector('.editor-error');
    var nameEl = container.querySelector('[data-field="name"]');
    var name = nameEl ? nameEl.value.trim() : '';
    if (!name) {
      if (errorEl) errorEl.textContent = 'Name is required.';
      return null;
    }
    var typeEl = container.querySelector('[data-field="type"]');
    var typeValue = typeEl ? typeEl.value : '';
    if (!typeValue) {
      if (errorEl) errorEl.textContent = 'Type is required.';
      return null;
    }

    var config = {};
    var configRows = container.querySelectorAll('.connector-account-config-table tbody tr.connector-account-config-row');
    for (var i = 0; i < configRows.length; i++) {
      var crow = configRows[i];
      var ck = crow.querySelector('.config-key-input');
      var cv = crow.querySelector('.config-value-input');
      if (!ck || !cv) continue;
      var ckey = (ck.value || '').trim();
      if (!ckey) continue;
      config[ckey] = cv.value || '';
    }

    var secrets = {};
    var secretRows = container.querySelectorAll('.connector-account-secrets-table tbody tr.connector-account-secret-row');
    for (var j = 0; j < secretRows.length; j++) {
      var srow = secretRows[j];
      var sk = srow.querySelector('.secret-key-input');
      var sv = srow.querySelector('.secret-value-input');
      if (!sk || !sv) continue;
      var skey = (sk.value || '').trim();
      if (!skey) continue;
      var value = sv.value || '';
      var origMasked = sv.dataset.originalMasked || '';
      if (origMasked && value === origMasked) {
        // Per-row __MASKED__ — backend preserves the stored secret.
        secrets[skey] = MASKED_SENTINEL;
      } else {
        secrets[skey] = value;
      }
    }

    var idleEl = container.querySelector('[data-field="idle_timeout_seconds"]');
    var idleRaw = idleEl ? (idleEl.value || '').trim() : '';
    var idleValue = null;
    if (idleRaw !== '') {
      // Parse as number; let backend reject anything invalid via 422.
      var parsed = Number(idleRaw);
      if (!isNaN(parsed) && isFinite(parsed)) {
        // Always submit as an integer if it looks like one; let backend
        // 422 catch non-integer / out-of-range values.
        idleValue = Math.trunc(parsed);
      } else {
        idleValue = idleRaw; // pass-through string; backend will 422
      }
    }

    var contEl = container.querySelector('[data-field="session_continuation_seconds"]');
    var contRaw = contEl ? (contEl.value || '').trim() : '';
    var contValue = null;
    if (contRaw !== '') {
      // Parse as number; let backend reject anything invalid via 422.
      var contParsed = Number(contRaw);
      if (!isNaN(contParsed) && isFinite(contParsed)) {
        // Always submit as an integer if it looks like one; let backend
        // 422 catch non-integer / out-of-range values.
        contValue = Math.trunc(contParsed);
      } else {
        contValue = contRaw; // pass-through string; backend will 422
      }
    }

    return {
      name: name,
      type: typeValue,
      config: config,
      secrets: secrets,
      idle_timeout_seconds: idleValue,
      session_continuation_seconds: contValue
    };
  }

  // ── Test Connection handler ─────────────────────────────────────────

  function handleTestConnection(accountId, container, testBtn) {
    var statusEl = container.querySelector('[data-testid="connector-test-status"]');
    var detailsWrap = container.querySelector('[data-testid="connector-test-details-wrap"]');
    var detailsEl = container.querySelector('[data-testid="connector-test-details"]');
    var ledEl = container.querySelector('[data-testid="connector-test-led"]');
    var messageEl = container.querySelector('[data-testid="connector-test-message"]');

    testBtn.disabled = true;
    if (ledEl) {
      ledEl.className = 'indicator-led indicator-led--idle connector-test-led';
      ledEl.setAttribute('data-state', 'testing');
      ledEl.setAttribute('aria-label', 'Testing');
    }
    if (messageEl) messageEl.textContent = '';
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = 'Testing connection…';
    }
    if (detailsWrap) detailsWrap.hidden = true;
    if (detailsEl) detailsEl.innerHTML = '';

    fetch('/api/connector-accounts/' + encodeURIComponent(accountId) + '/test/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
      .then(function (resp) {
        if (resp.ok) return resp.json();
        return resp.text().then(function (body) {
          var snippet = (body || '').trim().slice(0, 500);
          var err = new Error('Server error ' + resp.status + ' ' + resp.statusText +
                              (snippet ? ': ' + snippet : ''));
          err.serverStatus = resp.status;
          throw err;
        });
      })
      .then(function (report) {
        renderTestConnectionBanner(container, report);
      })
      .catch(function (err) {
        // Network / 5xx — render as a synthetic error banner so the UI is
        // never blank after a click.
        renderTestConnectionBanner(container, {
          status: 'error',
          message: 'Network error: ' + (err && err.message ? err.message : String(err)),
          details: {}
        });
      })
      .then(function () {
        testBtn.disabled = false;
      });
  }

  function renderTestConnectionBanner(container, report) {
    var escapeHtml = window.App.escapeHtml;
    var statusEl = container.querySelector('[data-testid="connector-test-status"]');
    var detailsWrap = container.querySelector('[data-testid="connector-test-details-wrap"]');
    var detailsEl = container.querySelector('[data-testid="connector-test-details"]');
    var ledEl = container.querySelector('[data-testid="connector-test-led"]');
    var messageEl = container.querySelector('[data-testid="connector-test-message"]');

    var status = (report && report.status) || 'error';
    var message = (report && report.message) || '';
    var details = (report && report.details) || {};

    if (ledEl) {
      ledEl.className = 'indicator-led ' + statusLedClass(status) + ' connector-test-led';
      ledEl.setAttribute('data-state', status);
      ledEl.setAttribute('aria-label', statusAriaLabel(status));
    }
    if (messageEl) {
      messageEl.textContent = message || statusAriaLabel(status);
    }
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.innerHTML = escapeHtml(message || statusAriaLabel(status));
    }
    if (detailsEl && detailsWrap) {
      detailsEl.innerHTML = renderDetailsBlock(details);
      detailsWrap.hidden = false;
    }
  }

  function renderDetailsBlock(details) {
    var escapeHtml = window.App.escapeHtml;
    if (!details || typeof details !== 'object' || Object.keys(details).length === 0) {
      return '<div class="connector-test-details-empty"><em>(no additional details)</em></div>';
    }
    var html = '<dl class="connector-test-details-list kv-display">';
    var keys = Object.keys(details);
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      var value = details[key];
      var renderedValue;
      if (typeof value === 'string') {
        // Secret-shaped values (start with '***') pass through unchanged —
        // do NOT re-mask, do NOT escape transform. Plain HTML escape only.
        renderedValue = '<span class="connector-test-details-value">' + escapeHtml(value) + '</span>';
      } else {
        var json = '';
        try {
          json = JSON.stringify(value);
        } catch (_) {
          json = String(value);
        }
        renderedValue = '<code class="font-mono connector-test-details-value">' + escapeHtml(json) + '</code>';
      }
      html += '<dt class="connector-test-details-key">' + escapeHtml(key) + '</dt><dd>' + renderedValue + '</dd>';
    }
    html += '</dl>';
    return html;
  }

  // ── KV table head visibility helpers ────────────────────────────────

  function updateConfigHeadVisibility(container) {
    var thead = container.querySelector('.connector-account-config-thead');
    if (!thead) return;
    var rowCount = container.querySelectorAll('.connector-account-config-table tbody tr.connector-account-config-row').length;
    thead.classList.toggle('is-hidden', rowCount === 0);
  }

  function updateSecretsHeadVisibility(container) {
    var thead = container.querySelector('.connector-account-secrets-thead');
    if (!thead) return;
    var rowCount = container.querySelectorAll('.connector-account-secrets-table tbody tr.connector-account-secret-row').length;
    thead.classList.toggle('is-hidden', rowCount === 0);
  }

  window.App.studio.renderConnectorAccountEditor = renderConnectorAccountEditor;
})();
