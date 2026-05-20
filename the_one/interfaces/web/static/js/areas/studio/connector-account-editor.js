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

  // ── Lifecycle dropdown ladder (F5 L8 HAT) ──────────────────────────
  // Operator-friendly preset values for idle_timeout_seconds and
  // session_continuation_seconds. Values are seconds; labels are
  // human-readable. Both fields share the same ladder; the continuation
  // field also offers a "Never (always continue)" option representing
  // null (the API field is nullable). The idle-timeout field treats the
  // default sentinel (empty option value) as null.
  //
  // Values mirror the API's Pydantic bound (1 <= value <= 604800), so
  // every option is round-tripped without backend rejection. Custom
  // persisted values that don't match a ladder entry render as a
  // disabled "Custom: Xs" option (collectFormData passes them through).
  // M10 F6 L7 HAT issue #8: single "(default)" entry instead of a
  // separate top-of-list sentinel. The entry whose ``value`` equals
  // the option's ``defaultSeconds`` gets the "(default)" suffix and
  // serializes to null. Other entries serialize to their seconds value.
  var LIFECYCLE_OPTIONS = [
    { value: 300, label: '5 minutes' },
    { value: 900, label: '15 minutes' },
    { value: 1800, label: '30 minutes' },
    { value: 3600, label: '1 hour' },
    { value: 14400, label: '4 hours' },
    { value: 86400, label: '1 day' },
    { value: 604800, label: '1 week' }
  ];

  function renderLifecycleSelect(id, fieldName, testId, currentValue, options) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var includeNever = !!(options && options.includeNever);
    var defaultSeconds = (options && options.defaultSeconds) || 1800;

    var currentSerialized = (currentValue === '' || currentValue == null) ? '' : String(currentValue);
    var matched = (currentSerialized === '');
    var ladderHtml = '';
    for (var i = 0; i < LIFECYCLE_OPTIONS.length; i++) {
      var opt = LIFECYCLE_OPTIONS[i];
      var optStr = String(opt.value);
      var isDefault = (opt.value === defaultSeconds);
      // The "(default)" entry serializes to null (empty value); other
      // entries serialize to their seconds value.
      var optValue = isDefault ? '' : optStr;
      var selected = isDefault
        ? (currentSerialized === '')
        : (currentSerialized === optStr);
      if (selected) matched = true;
      var labelText = isDefault ? opt.label + ' (default)' : opt.label;
      ladderHtml += '<option value="' + escapeAttr(optValue) + '"' +
                    (isDefault ? ' data-default-sentinel="1"' : '') +
                    (selected ? ' selected' : '') + '>' +
                    escapeHtml(labelText) + '</option>';
    }

    // "Never" sentinel for continuation only — emits null payload too,
    // distinguished from "(default)" by the literal value "__NEVER__".
    var neverOptionHtml = '';
    if (includeNever) {
      neverOptionHtml = '<option value="__NEVER__">Never (always continue)</option>';
    }

    // Custom fallback — if the persisted value isn't on the ladder and
    // isn't empty, render a disabled "Custom: Xs" option (selected) so
    // the operator sees the stored value. Submitting unchanged passes
    // the value through verbatim.
    var customOptionHtml = '';
    if (!matched && currentSerialized !== '') {
      customOptionHtml = '<option value="' + escapeAttr(currentSerialized) +
                         '" selected data-custom="1">Custom: ' +
                         escapeHtml(currentSerialized) + 's</option>';
    }

    return '<select class="field-input field-select admin-pf-input admin-pf-select" id="' +
           escapeAttr(id) + '" data-field="' + escapeAttr(fieldName) + '" ' +
           'data-testid="' + escapeAttr(testId) + '">' +
           neverOptionHtml + customOptionHtml + ladderHtml +
           '</select>';
  }

  function parseLifecycleValue(container, fieldName) {
    var el = container.querySelector('[data-field="' + fieldName + '"]');
    if (!el) return null;
    var raw = (el.value || '').trim();
    if (raw === '' || raw === '__NEVER__') return null;
    var parsed = Number(raw);
    if (!isNaN(parsed) && isFinite(parsed)) {
      return Math.trunc(parsed);
    }
    return raw; // pass-through; backend will 422
  }

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

  // ── Inline field-level validation rendering ─────────────────────────
  // M10 F6 L7 HAT: validation errors render adjacent to the offending
  // field row (inline `[data-field-error]` span + `field-error-highlight`
  // class on the row) instead of being dumped in the top action-cluster
  // `.editor-error` span. Mirrors the admin tools-editor's
  // `renderFieldErrors` pattern (admin.css:355-370,448-454).
  function clearFieldErrors(container) {
    var rows = container.querySelectorAll('[data-field-row]');
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.remove('field-error-highlight');
    }
    var spans = container.querySelectorAll('[data-field-error]');
    for (var j = 0; j < spans.length; j++) {
      spans[j].textContent = '';
      spans[j].setAttribute('hidden', '');
    }
  }

  function setFieldError(container, fieldName, message) {
    var row = container.querySelector('[data-field-row="' + fieldName + '"]');
    if (row) row.classList.add('field-error-highlight');
    var span = container.querySelector('[data-field-error="' + fieldName + '"]');
    if (span) {
      span.textContent = message;
      span.removeAttribute('hidden');
    }
  }

  // ── Public entry point ──────────────────────────────────────────────

  function renderConnectorAccountEditor(container, account, types, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !account;
    var name = isCreate ? 'New Connector' : (account.name || '');
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
    html += '<button type="button" class="btn-outlined-primary back-btn" data-testid="back-connector-account-btn" aria-label="Back to connectors list">' + window.App.icon('arrow-left') + ' Back</button>';
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
    // F5 L8 HAT: free-form numeric inputs replaced with dropdowns offering
    // the operator-friendly ladder defined in LIFECYCLE_OPTIONS below. The
    // continuation field also offers a "Never (always continue)" option
    // representing null; the idle-timeout field only offers the default
    // sentinel (empty string → null). Custom persisted values that don't
    // match a ladder entry are rendered as a disabled "Custom: Xs" option
    // so the operator sees what's stored without overwriting it.
    var idleValue = (!isCreate && account.idle_timeout_seconds != null) ? account.idle_timeout_seconds : '';
    var contValue = (!isCreate && account.session_continuation_seconds != null) ? account.session_continuation_seconds : '';
    html += '<div class="editor-section">';
    html += '<div class="section-title">Lifecycle</div>';

    // Pool idle timeout (F2)
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="cf-idle-timeout">Pool idle timeout</label>';
    html += renderLifecycleSelect('cf-idle-timeout', 'idle_timeout_seconds',
            'connector-account-idle-timeout-input', idleValue,
            { defaultSeconds: 1800, includeNever: false });
    html += '</div>';
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<small class="form-hint" data-testid="connector-account-idle-hint">' +
            'Reap warm connection after inactivity.' +
            '</small>';
    html += '</div>';

    // Chat-session continuation window (F3 L5)
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="cf-continuation-window">Chat-session continuation window</label>';
    html += renderLifecycleSelect('cf-continuation-window', 'session_continuation_seconds',
            'connector-account-continuation-input', contValue,
            { defaultSeconds: 86400, includeNever: true });
    html += '</div>';
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<small class="form-hint" data-testid="connector-account-continuation-hint">' +
            'Inbound continues the same chat session within this window.' +
            '</small>';
    html += '</div>';

    html += '</div>';

    // ── Pairing section (edit mode only) ──────────────────────────────
    // M10 F6 L4: operator generates / regenerates the account pairing
    // code. The endpoint is the only writer for ``config["pairing"]``
    // (leg-1b schema); the code is shown ONCE after the operator
    // clicks. Subsequent renders display only the ``issued_at`` summary
    // — the operator must regenerate to reveal a fresh code (leg-1b
    // decision: plaintext storage but no auto-display on load).
    if (!isCreate) {
      html += renderPairingSection(account);
    }

    // ── Account-scope allowlist section (edit mode only) ──────────────
    // M10 F6 L4: account-level peer/channel allowlist editor.
    // Checkbox gates the two list editors; unchecked = default-permit
    // (saving OMITS ``config.allowlist``); checked + empty lists =
    // lockdown (saving sends ``{"peers": [], "channels": []}`` — the
    // leg-1b empty-preservation invariant).
    if (!isCreate) {
      html += renderAllowlistSection(account);
    }

    // ── Attached agents (read-only, edit mode only) ───────────────────
    // M10 F6 L4: read-only summary of agents whose
    // ``connector_account_ids`` includes this account, with per-agent
    // ACL counts and deep-links. Populated asynchronously on mount via
    // GET /api/connector-accounts/{id}/attached-agents (the editor
    // renders an empty placeholder; the fetch fills it in).
    if (!isCreate) {
      html += renderAttachedAgentsSection();
    }

    // ── Test Connection section (edit mode only) ──────────────────────
    if (!isCreate) {
      html += '<div class="editor-section connector-test-section">';
      html += '<div class="section-title">Test Connection</div>';
      html += '<div class="connector-test-actions">';
      html += '<button type="button" class="btn-outlined-primary connector-test-connection-btn" data-testid="connector-test-connection-btn">' +
              window.App.icon('refresh-cw') + ' Test connection</button>';
      html += '<span class="indicator-led indicator-led--idle connector-test-led" data-testid="connector-test-led" data-state="idle" aria-label="Not tested"></span>';
      html += '<span class="connector-test-message" data-testid="connector-test-message">Not tested</span>';
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
              '<span data-confirm-title>Delete Connector</span>' +
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
    var typesList = Array.isArray(types) ? types : [];
    var typesEmpty = isCreate && typesList.length === 0;

    // M10 F6 L7 HAT: when production has zero registered connector types
    // (CONNECTOR_TYPES = () until Flight 8 lands Discord), surface a
    // themed banner inside the Connection section instead of just an
    // unselectable dropdown placeholder. Operator can still test the
    // F6 surfaces against API-seeded `stub` accounts (the schema has
    // no CHECK constraint on `type` until v19).
    if (typesEmpty) {
      html += '<div class="connector-account-empty-types-banner" ' +
              'data-testid="connector-account-empty-types-banner" role="status">';
      html += '<strong>No connector types are registered yet.</strong> ';
      html += 'Discord support lands in Flight 8 of Mission 10. ';
      html += 'For HAT or local testing you can seed a <code>stub</code>-type account via ';
      html += '<code>POST /api/connector-accounts</code> with <code>{"type":"stub", ...}</code>.';
      html += '</div>';
    }

    // Name
    html += '<div class="field-row admin-pf-row" data-field-row="name">';
    html += '<label for="cf-name">Name</label>';
    html += '<input class="field-input admin-pf-input" id="cf-name" data-field="name" data-testid="connector-account-name-input" value="' +
            escapeAttr(isCreate ? '' : (account.name || '')) +
            '" placeholder="My Discord bot" />';
    html += '<span class="field-error" data-field-error="name" hidden></span>';
    html += '</div>';

    // Type — select on create, read-only display on edit. Mirrors MCP's
    // edit-time type immutability: changing type would invalidate the
    // config + secrets shape, so the type is locked once chosen.
    html += '<div class="field-row admin-pf-row" data-field-row="type">';
    html += '<label for="cf-type">Type</label>';
    if (isCreate) {
      var typeDisabledAttr = typesEmpty ? ' disabled aria-disabled="true"' : '';
      html += '<select class="field-input field-select admin-pf-input admin-pf-select" id="cf-type" data-field="type" data-testid="connector-account-type-select"' + typeDisabledAttr + '>';
      if (typesEmpty) {
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
    html += '<span class="field-error" data-field-error="type" hidden></span>';
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

  // M10 F6 L4: reserved top-level ``config`` keys owned by dedicated
  // editor sections (Pairing, Allowlist). These are NOT shown in the
  // arbitrary kv-table — the dedicated sections are the only writers,
  // and ``collectFormData`` merges them back into the save payload so
  // they round-trip without operator intervention.
  var RESERVED_CONFIG_KEYS = { pairing: true, allowlist: true };

  function collectConfigRows(account) {
    var rows = [];
    if (!account || !account.config) return rows;
    for (var k in account.config) {
      if (Object.prototype.hasOwnProperty.call(account.config, k)) {
        if (RESERVED_CONFIG_KEYS[k]) continue;  // owned by a dedicated section
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
    // F5 L8 HAT: label "+ Add row" matches MCP's kv-add-row-btn (the section
    // title — "Config" — already provides the row-type context). The
    // `kv-add-row-btn` class hook brings the same studio CSS posture as
    // MCP's add-row affordance.
    html += '<button type="button" class="btn-outlined-primary kv-add-row-btn connector-config-add-row-btn" data-testid="connector-config-add-row-btn">+ Add row</button>';
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
    // F5 L8 HAT: label "+ Add row" matches MCP's kv-add-row-btn pattern
    // (the section title — "Credentials" — already provides context).
    html += '<button type="button" class="btn-outlined-primary kv-add-row-btn connector-secrets-add-row-btn" data-testid="connector-secrets-add-row-btn">+ Add row</button>';
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

    // M10 F6 L7 HAT — semantic redesign: no Enable toggle. The
    // snapshot captures the always-mounted peers/channels chip-lists.
    // Empty lists are valid and meaningful (unrestricted on that axis).
    // Pairing state is NOT included — the pairing button triggers an
    // out-of-band POST that persists immediately, independent of the
    // editor's Save button (the in-memory ``account.config.pairing``
    // mirror prevents data loss when the operator then clicks Save
    // with other dirty fields).
    var allowlist = collectAllowlistFromContainer(container);

    return JSON.stringify({
      static: staticData,
      config: configRows,
      secrets: secretRows,
      allowlist: allowlist
    });
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
          // M10 F6 L7 HAT — stale-chip warning. If the operator removed
          // a chip that an attached agent's ACL still references, warn
          // before the PUT so the operator can keep the entry (or
          // accept that the agent's ACL chip will be effectively
          // dead-pointing after save).
          _confirmStaleChipsThen(
            account, payload, container,
            function () {
              handleSaveEdit(account, payload, container, callbacks, saveBtn, recaptureSnapshot);
            }
          );
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
            window.App.showFlash(container, 'Connector deleted');
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

    // ── F6 L4: Pairing / Allowlist / Attached agents (edit only) ──────
    if (isEdit) {
      wirePairingEvents(container, account, callbacks);
      wirePairingCopyEvents(container);
      wireAllowlistEvents(container, account, checkDirty);
      // M10 F6 L7 HAT: chip-list editors are mounted lazily by
      // wireAllowlistEvents AFTER the initial snapshot was captured.
      // The chip-list content (peers / channels from
      // account.config.allowlist) was therefore absent from the
      // baseline. Recapture so the just-mounted chips don't count as
      // a dirty edit.
      recaptureSnapshot();
      checkDirty();

      // Kick off the attached-agents fetch on mount. The list renders
      // a "Loading…" placeholder until this resolves.
      fetchAttachedAgents(container, account.id);
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
        window.App.showFlash(container, 'Connector saved');
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
        window.App.showFlash(container, 'Connector created');
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
    // Clear stale state on entry — both the inline field markers and
    // the action-cluster aggregate span (the latter is preserved for
    // backend-422 surfacing; field-level pre-flight checks now render
    // inline at the offending row).
    clearFieldErrors(container);
    if (errorEl) errorEl.textContent = '';

    var nameEl = container.querySelector('[data-field="name"]');
    var name = nameEl ? nameEl.value.trim() : '';
    var typeEl = container.querySelector('[data-field="type"]');
    var typeValue = typeEl ? typeEl.value : '';

    // Collect ALL pre-flight failures before returning so the operator
    // sees every offender at once (vs. fix one, save, see the next).
    var hadError = false;
    if (!name) {
      setFieldError(container, 'name', 'Name is required.');
      hadError = true;
    }
    if (!typeValue) {
      setFieldError(container, 'type', 'Type is required.');
      hadError = true;
    }
    if (hadError) return null;

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

    // F5 L8 HAT: Lifecycle fields are dropdowns. Empty value (the "Use
    // default" sentinel) and "__NEVER__" (continuation-only) both serialize
    // to null. Any other value is parsed as an integer and passed through;
    // backend Pydantic owns out-of-range validation.
    var idleValue = parseLifecycleValue(container, 'idle_timeout_seconds');
    var contValue = parseLifecycleValue(container, 'session_continuation_seconds');

    // M10 F6 L4: merge the reserved ``pairing`` + ``allowlist`` keys
    // with the existing arbitrary ``config`` kv-table rows. Order: kv
    // rows first (so a stale ``pairing`` / ``allowlist`` row in the kv
    // table — should not normally happen, but the operator could type
    // one — is OVERWRITTEN by the canonical reserved-key sources here).
    //
    // ``account.config.pairing`` is the source of truth for the
    // pairing key: it is set by the pairing-code endpoint click
    // handler (wirePairingEvents) and may have changed since the
    // editor mounted. Edit-mode only — create mode has no
    // ``account`` to read from.
    if (isEdit && account && account.config && account.config.pairing) {
      config.pairing = account.config.pairing;
    }
    // Allowlist: M10 F6 L7 HAT — semantic redesign. The chip-lists are
    // ALWAYS mounted and ALWAYS emitted. Empty list = unrestricted on
    // that axis (post-redesign "empty = all permitted" semantic). The
    // shape sent is always ``{peers: [...], channels: [...]}`` — never
    // omitted.
    if (isEdit) {
      var allowlistState = collectAllowlistFromContainer(container);
      if (allowlistState) {
        config.allowlist = {
          peers: allowlistState.peers,
          channels: allowlistState.channels
        };
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

  // ── Pairing / Allowlist / Attached agents (M10 F6 L4) ───────────────
  //
  // These three sections render only in edit mode (gated on
  // ``!isCreate`` at the call site, mirroring the Test Connection +
  // Danger Zone gate). They operate on the leg-1b reserved
  // ``config["pairing"]`` and ``config["allowlist"]`` keys and on the
  // new reverse-lookup endpoint
  // ``GET /api/connector-accounts/{id}/attached-agents`` (leg-4 spec).
  //
  // The save flow (``collectFormData``) merges pairing + allowlist with
  // the existing arbitrary config kv-table — no key is silently
  // dropped. ``getFormSnapshot`` is extended so the dirty-tracker fires
  // on the allowlist editor; the pairing button is NOT a dirty source
  // (it issues an independent POST that persists server-side
  // immediately).

  function renderPairingSection(account) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var pairing = (account && account.config && account.config.pairing) || null;
    var issuedAt = pairing && pairing.issued_at ? String(pairing.issued_at) : '';
    var buttonLabel = pairing ? 'Regenerate code' : 'Generate code';

    var html = '';
    html += '<div class="editor-section connector-pairing-section">';
    html += '<div class="section-title">Pairing</div>';

    // Action row — Generate/Regenerate button with refresh icon,
    // followed by the status line. Order is button-then-status so the
    // primary affordance reads first.
    html += '<div class="field-row admin-pf-row">';
    html += '<label>Status</label>';
    html += '<div class="connector-pairing-row">';
    html += '<button type="button" class="btn-outlined-primary connector-pairing-generate-btn" ' +
            'data-testid="connector-pairing-generate-btn">' +
            window.App.icon('refresh') + ' ' + escapeHtml(buttonLabel) + '</button>';
    html += '<div class="connector-pairing-status" data-testid="connector-pairing-status">';
    if (issuedAt) {
      html += 'Code on file · issued ' + escapeHtml(issuedAt);
    } else {
      html += 'No pairing code generated yet.';
    }
    html += '</div>';
    html += '</div>';
    html += '</div>';

    // Code-reveal slot — only rendered into the DOM after the operator
    // clicks Generate / Regenerate. The empty-on-load state has NO
    // reveal row at all (issue #4: only show when there's a code).
    // The copy button is an in-input icon button (issue #3).
    html += '<div class="field-row admin-pf-row connector-pairing-reveal-row" ' +
            'data-testid="connector-pairing-reveal-row" hidden>';
    html += '<label for="connector-pairing-code-readonly">Code</label>';
    html += '<div class="connector-pairing-reveal">';
    html += '<div class="connector-pairing-code-wrap">';
    html += '<input type="text" id="connector-pairing-code-readonly" ' +
            'class="field-input admin-pf-input connector-pairing-code-input" ' +
            'data-testid="connector-pairing-code-input" readonly value="" />';
    html += '<button type="button" class="connector-pairing-copy-btn" ' +
            'data-testid="connector-pairing-copy-btn" ' +
            'aria-label="Copy pairing code" title="Copy">' +
            window.App.icon('copy') + '</button>';
    html += '</div>';
    html += '<small class="form-hint">Copy now — only shown once.</small>';
    html += '</div>';
    html += '</div>';

    html += '</div>';
    void escapeAttr;
    return html;
  }

  function renderAllowlistSection(account) {
    // M10 F6 L7 HAT — semantic redesign: dropped the Enable toggle.
    // Chip-lists are ALWAYS rendered. Empty list = unrestricted on
    // that axis (no constraint). Both axes empty = fully unrestricted
    // account (the common "I want a public bot" intent that previously
    // required toggling Enable off). See flight-log "Deviations".
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;

    var html = '';
    html += '<div class="editor-section connector-allowlist-section">';
    html += '<div class="section-title">Account-scope allowlist</div>';

    html += '<div class="connector-allowlist-lists" ' +
            'data-testid="connector-allowlist-lists">';
    html += '<div class="connector-account-acl-fieldrow">';
    html += '<label class="connector-account-acl-fieldlabel">Peers</label>';
    html += '<div data-allowlist-chiplist-slot="peers"></div>';
    html += '<small class="form-hint" ' +
            'data-testid="connector-allowlist-peers-hint">' +
            'Empty list = no peer restriction.' +
            '</small>';
    html += '</div>';
    html += '<div class="connector-account-acl-fieldrow">';
    html += '<label class="connector-account-acl-fieldlabel">Channels</label>';
    html += '<div data-allowlist-chiplist-slot="channels"></div>';
    html += '<small class="form-hint" ' +
            'data-testid="connector-allowlist-channels-hint">' +
            'Empty list = no channel restriction.' +
            '</small>';
    html += '</div>';
    html += '</div>';

    html += '</div>';
    void escapeHtml;
    void escapeAttr;
    return html;
  }

  // Build a chip-list-editor wrapper for the account-scope allowlist.
  // Mirrors connectors-tab.js::_buildChipList exactly so the two
  // surfaces feel identical at the operator level. Per-account ACL
  // data attributes are NOT used here (this is the account-scope
  // list, not a per-agent ACL); studio.js's collectFormData reads the
  // wrapper via the studio-side ``.connector-acl-chiplist`` selector,
  // but the connector-account-editor's own collectFormData reads via
  // the slot dataset (data-allowlist-chiplist-slot).
  function _buildAllowlistChipList(kind, items) {
    var wrapper = document.createElement('div');
    wrapper.className = 'chip-list-editor connector-allowlist-chiplist';
    wrapper.setAttribute('data-allowlist-kind', kind);
    wrapper.setAttribute('data-testid', 'connector-allowlist-' + kind + '-chiplist');

    for (var i = 0; i < (items || []).length; i++) {
      var v = String(items[i]);
      var chip = document.createElement('span');
      chip.className = 'chip';
      chip.appendChild(document.createTextNode(v));
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chip-remove';
      btn.setAttribute('aria-label', 'Remove ' + v);
      btn.textContent = '×'; // × multiplication sign
      chip.appendChild(btn);
      wrapper.appendChild(chip);
    }

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'chip-list-input';
    input.placeholder = kind === 'peers' ? 'Add peer…' : 'Add channel…';
    input.setAttribute('aria-label', kind === 'peers' ? 'Add peer' : 'Add channel');
    wrapper.appendChild(input);
    return wrapper;
  }

  function renderAttachedAgentsSection() {
    var html = '';
    html += '<div class="editor-section connector-attached-agents-section">';
    html += '<div class="section-title">Attached agents</div>';
    html += '<div class="connector-attached-agents-list" ' +
            'data-testid="connector-attached-agents-list">' +
            '<em class="form-hint">Loading…</em>' +
            '</div>';
    html += '</div>';
    return html;
  }

  function renderAttachedAgentsList(container, rows) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var listEl = container.querySelector('[data-testid="connector-attached-agents-list"]');
    if (!listEl) return;
    if (!rows || rows.length === 0) {
      listEl.innerHTML = '<em class="form-hint">No agents attached.</em>';
      return;
    }
    // M10 F6 L7 HAT — semantic redesign: render the actual per-agent
    // ACL chips (read-only). Each axis is tri-state:
    //   - null → "inherits" hint
    //   - [] → "none" (peers) / "DMs only" (channels) hint
    //   - [items] → chips
    // The chip primitive is reused without the remove-button affordance
    // (read-only display); each row links to the agent editor.
    function _renderAxis(value, axis) {
      if (value == null) {
        return '<em class="form-hint" data-testid="' +
               'connector-attached-axis-inherits">inherits</em>';
      }
      if (Array.isArray(value) && value.length === 0) {
        if (axis === 'channels') {
          return '<em class="form-hint" data-testid="' +
                 'connector-attached-axis-dms-only">DMs only</em>';
        }
        return '<em class="form-hint" data-testid="' +
               'connector-attached-axis-none">none</em>';
      }
      var parts = '';
      for (var ci = 0; ci < value.length; ci++) {
        parts += '<span class="chip">' + escapeHtml(String(value[ci])) + '</span>';
      }
      return parts;
    }

    var html = '<table class="connector-attached-agents-table" ' +
               'data-testid="connector-attached-agents-table">';
    html += '<thead><tr>' +
            '<th>Agent</th>' +
            '<th>Peers</th>' +
            '<th>Channels</th>' +
            '</tr></thead>';
    html += '<tbody>';
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var name = String(row.name || '');
      var peersVal = (row.peers === undefined) ? null : row.peers;
      var channelsVal = (row.channels === undefined) ? null : row.channels;
      html += '<tr class="connector-attached-agent-row" ' +
              'data-testid="connector-attached-agent-' + escapeAttr(name) + '">';
      html += '<td><a href="#studio/agents/' + escapeAttr(name) + '" ' +
              'class="connector-attached-agent-link" ' +
              'data-testid="connector-attached-agent-link-' + escapeAttr(name) + '">' +
              escapeHtml(name) + '</a></td>';
      html += '<td data-testid="connector-attached-agent-peers-' +
              escapeAttr(name) + '">' + _renderAxis(peersVal, 'peers') + '</td>';
      html += '<td data-testid="connector-attached-agent-channels-' +
              escapeAttr(name) + '">' + _renderAxis(channelsVal, 'channels') + '</td>';
      html += '</tr>';
    }
    html += '</tbody></table>';
    listEl.innerHTML = html;
  }

  function fetchAttachedAgents(container, accountId) {
    fetch('/api/connector-accounts/' + encodeURIComponent(accountId) + '/attached-agents')
      .then(function (resp) {
        if (!resp.ok) {
          // 404 or 5xx — render a clear failure message rather than
          // leaving the "Loading…" placeholder in place forever.
          var listEl = container.querySelector('[data-testid="connector-attached-agents-list"]');
          if (listEl) {
            listEl.innerHTML = '<em class="form-hint">Could not load attached agents (status ' +
                               resp.status + ').</em>';
          }
          return null;
        }
        return resp.json();
      })
      .then(function (rows) {
        if (rows == null) return;
        if (!Array.isArray(rows)) rows = [];
        renderAttachedAgentsList(container, rows);
      })
      .catch(function (err) {
        var listEl = container.querySelector('[data-testid="connector-attached-agents-list"]');
        if (listEl) {
          listEl.innerHTML = '<em class="form-hint">Network error: ' +
                             window.App.escapeHtml(err && err.message ? err.message : String(err)) +
                             '</em>';
        }
      });
  }

  function wirePairingEvents(container, account, callbacks) {
    var btn = container.querySelector('.connector-pairing-generate-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var originalHtml = btn.innerHTML;
      btn.disabled = true;
      btn.textContent = 'Generating…';
      fetch('/api/connector-accounts/' + encodeURIComponent(account.id) + '/pairing-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
        .then(function (resp) {
          if (!resp.ok) {
            return resp.text().then(function (body) {
              throw new Error('Pairing-code request failed (' + resp.status + '): ' +
                              (body || '').slice(0, 200));
            });
          }
          return resp.json();
        })
        .then(function (data) {
          if (!data || typeof data.code !== 'string' || !data.code) {
            throw new Error('Malformed pairing-code response');
          }
          // Reveal the code in the read-only slot.
          var revealRow = container.querySelector('[data-testid="connector-pairing-reveal-row"]');
          var codeInput = container.querySelector('[data-testid="connector-pairing-code-input"]');
          if (codeInput) codeInput.value = data.code;
          if (revealRow) revealRow.hidden = false;

          // Update the status row text so subsequent navigations away +
          // back show the new issued_at without the code (matches the
          // initial-render contract).
          var statusEl = container.querySelector('[data-testid="connector-pairing-status"]');
          if (statusEl) {
            statusEl.textContent = 'Code on file · issued ' + (data.issued_at || '');
          }
          // Relabel the button to "Regenerate code" once a code exists.
          // Use innerHTML to preserve the refresh icon — textContent would
          // strip the SVG.
          btn.innerHTML = window.App.icon('refresh') + ' Regenerate code';

          // Mirror the new pairing into the local ``account.config``
          // so any subsequent Save (collectFormData) preserves it
          // through the merge step.
          if (!account.config) account.config = {};
          account.config.pairing = { code: data.code, issued_at: data.issued_at };

          window.App.showFlash(container, 'Pairing code generated. Click Save to persist other changes.');
        })
        .catch(function (err) {
          btn.innerHTML = originalHtml;
          window.App.showFlash(container, 'Pairing error: ' + (err && err.message ? err.message : String(err)), true);
        })
        .then(function () {
          btn.disabled = false;
        });
    });
    void callbacks;
  }

  function wirePairingCopyEvents(container) {
    var copyBtn = container.querySelector('.connector-pairing-copy-btn');
    if (!copyBtn) return;
    copyBtn.addEventListener('click', function () {
      var codeInput = container.querySelector('[data-testid="connector-pairing-code-input"]');
      if (!codeInput || !codeInput.value) return;
      // Clipboard API path with a defensive select+execCommand fallback
      // for older / non-secure-context environments.
      var copied = false;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(codeInput.value);
          copied = true;
        }
      } catch (_) { /* fall through */ }
      if (!copied) {
        codeInput.removeAttribute('readonly');
        codeInput.select();
        try { document.execCommand('copy'); copied = true; } catch (_) { /* noop */ }
        codeInput.setAttribute('readonly', 'readonly');
      }
      window.App.showFlash(container, copied ? 'Pairing code copied' : 'Copy failed', !copied);
    });
  }

  function wireAllowlistEvents(container, account, checkDirty) {
    // M10 F6 L7 HAT — semantic redesign: no toggle. Chip-lists are
    // always mounted. Empty lists are valid and mean "unrestricted on
    // this axis."
    //
    // Mount the chip-list editors into the slot divs. Pre-existing
    // entries come from account.config.allowlist; if absent, empty
    // chip-lists are mounted so the operator can start typing
    // immediately.
    var allowlist = (account && account.config && account.config.allowlist) || null;
    var peersInit = (allowlist && Array.isArray(allowlist.peers)) ? allowlist.peers : [];
    var channelsInit = (allowlist && Array.isArray(allowlist.channels)) ? allowlist.channels : [];
    var peersSlot = container.querySelector('[data-allowlist-chiplist-slot="peers"]');
    var channelsSlot = container.querySelector('[data-allowlist-chiplist-slot="channels"]');
    var helpers = window.App.adminFormHelpers;

    function _mountChipList(slot, kind, init) {
      if (!slot) return;
      slot.innerHTML = '';
      var chiplist = _buildAllowlistChipList(kind, init);
      slot.appendChild(chiplist);
      if (helpers && helpers.wireChipListEditor) {
        helpers.wireChipListEditor(chiplist, { onChange: checkDirty });
      }
    }
    _mountChipList(peersSlot, 'peers', peersInit);
    _mountChipList(channelsSlot, 'channels', channelsInit);
  }

  function collectAllowlistFromContainer(container) {
    // M10 F6 L7 HAT — semantic redesign: no toggle. Returns
    // ``{ peers: list, channels: list }`` (or null if the slots are
    // missing — defensive). Both lists are ALWAYS emitted; empty list
    // = unrestricted on that axis. Chips are read in DOM order; the
    // wireChipListEditor helper guarantees only committed chip elements
    // (not the live input) carry values. Whitespace-only entries cannot
    // reach a chip (the helper trims before committing).
    var peersSlot = container.querySelector('[data-allowlist-chiplist-slot="peers"]');
    var channelsSlot = container.querySelector('[data-allowlist-chiplist-slot="channels"]');
    if (!peersSlot && !channelsSlot) return null;
    function _readChiplist(slot) {
      var out = [];
      if (!slot) return out;
      var chips = slot.querySelectorAll('.chip');
      for (var i = 0; i < chips.length; i++) {
        var chip = chips[i];
        var label = '';
        for (var j = 0; j < chip.childNodes.length; j++) {
          var n = chip.childNodes[j];
          if (n.nodeType === 3) {
            label += n.nodeValue;
          }
        }
        label = (label || '').trim();
        if (label) out.push(label);
      }
      return out;
    }
    return {
      peers: _readChiplist(peersSlot),
      channels: _readChiplist(channelsSlot)
    };
  }

  // ── Stale-chip warning (M10 F6 L7 HAT) ──────────────────────────────
  //
  // Before save, if the operator removed any chip relative to the
  // originally-loaded account.config.allowlist, fetch the attached
  // agents and warn if any removed chip is still referenced by an
  // agent's per-account ACL. The operator can cancel (abort save) or
  // confirm (proceed; the agent's chip stays in their ACL but no
  // longer matches an account-scope entry — effectively dead).

  function _confirmStaleChipsThen(account, payload, container, proceed) {
    var origAllowlist = (account && account.config && account.config.allowlist) || null;
    var origPeers = (origAllowlist && Array.isArray(origAllowlist.peers)) ? origAllowlist.peers : [];
    var origChannels = (origAllowlist && Array.isArray(origAllowlist.channels)) ? origAllowlist.channels : [];
    var newAllowlist = (payload && payload.config && payload.config.allowlist) || null;
    var newPeers = (newAllowlist && Array.isArray(newAllowlist.peers)) ? newAllowlist.peers : [];
    var newChannels = (newAllowlist && Array.isArray(newAllowlist.channels)) ? newAllowlist.channels : [];

    var removedPeers = [];
    for (var i = 0; i < origPeers.length; i++) {
      if (newPeers.indexOf(origPeers[i]) === -1) removedPeers.push(origPeers[i]);
    }
    var removedChannels = [];
    for (var j = 0; j < origChannels.length; j++) {
      if (newChannels.indexOf(origChannels[j]) === -1) removedChannels.push(origChannels[j]);
    }
    if (removedPeers.length === 0 && removedChannels.length === 0) {
      // No removals — proceed immediately.
      proceed();
      return;
    }

    fetch('/api/connector-accounts/' + encodeURIComponent(account.id) + '/attached-agents')
      .then(function (resp) {
        if (!resp.ok) return null;
        return resp.json();
      })
      .then(function (rows) {
        if (!Array.isArray(rows) || rows.length === 0) {
          proceed();
          return;
        }
        var affected = []; // [{agent, kind, chip}]
        for (var k = 0; k < rows.length; k++) {
          var row = rows[k] || {};
          var aname = String(row.name || '');
          var rowPeers = Array.isArray(row.peers) ? row.peers : [];
          var rowChannels = Array.isArray(row.channels) ? row.channels : [];
          for (var p = 0; p < removedPeers.length; p++) {
            if (rowPeers.indexOf(removedPeers[p]) !== -1) {
              affected.push({ agent: aname, kind: 'peer', chip: removedPeers[p] });
            }
          }
          for (var c = 0; c < removedChannels.length; c++) {
            if (rowChannels.indexOf(removedChannels[c]) !== -1) {
              affected.push({ agent: aname, kind: 'channel', chip: removedChannels[c] });
            }
          }
        }
        if (affected.length === 0) {
          proceed();
          return;
        }
        var lines = ['Removing these account-scope entries will leave dead references in attached agent ACLs:'];
        for (var li = 0; li < affected.length; li++) {
          var aff = affected[li];
          lines.push('  - agent "' + aff.agent + '": ' + aff.kind + ' "' + aff.chip + '"');
        }
        lines.push('');
        lines.push('Continue with save?');
        var ok = window.confirm(lines.join('\n'));
        if (ok) proceed();
      })
      .catch(function () {
        // Network failure — fall back to proceeding (don't block the
        // operator on a transient fetch failure; the save itself will
        // surface any backend rejection).
        proceed();
      });
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
