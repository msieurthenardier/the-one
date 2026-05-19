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
    var defaultLabel = (options && options.defaultLabel) || 'Use default';

    var currentSerialized = (currentValue === '' || currentValue == null) ? '' : String(currentValue);
    var matched = (currentSerialized === '');
    var ladderHtml = '';
    for (var i = 0; i < LIFECYCLE_OPTIONS.length; i++) {
      var opt = LIFECYCLE_OPTIONS[i];
      var optStr = String(opt.value);
      var selected = (currentSerialized === optStr);
      if (selected) matched = true;
      ladderHtml += '<option value="' + escapeAttr(optStr) + '"' +
                    (selected ? ' selected' : '') + '>' +
                    escapeHtml(opt.label) + '</option>';
    }

    // Default sentinel (empty string) — null payload. Selected when no
    // current value is set.
    var defaultSelected = (currentSerialized === '') ? ' selected' : '';
    var defaultOptionHtml = '<option value=""' + defaultSelected + '>' +
                            escapeHtml(defaultLabel) + '</option>';

    // "Never" sentinel for continuation only — emits null payload too,
    // distinguished from "use default" by the data attribute. Both serialize
    // to null but the dropdown shows different labels so the operator's
    // intent is visible.
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
           defaultOptionHtml + neverOptionHtml + customOptionHtml + ladderHtml +
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
            { defaultLabel: 'Use default (30 min)', includeNever: false });
    html += '</div>';
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<small class="form-hint" data-testid="connector-account-idle-hint">' +
            'Warm connector connections are reaped after this many seconds of inactivity. ' +
            'Leave on "Use default" to apply the system default (30 min).' +
            '</small>';
    html += '</div>';

    // Chat-session continuation window (F3 L5)
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="cf-continuation-window">Chat-session continuation window</label>';
    html += renderLifecycleSelect('cf-continuation-window', 'session_continuation_seconds',
            'connector-account-continuation-input', contValue,
            { defaultLabel: 'Use default (24 hours)', includeNever: true });
    html += '</div>';
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<small class="form-hint" data-testid="connector-account-continuation-hint">' +
            'Inbounds on the same conversation continue an existing chat session within this window. ' +
            'After this period of platform silence, the next inbound starts a fresh session. ' +
            'Leave on "Use default" to apply the system default (24 hours). ' +
            'Distinct from the pool idle timeout above, which controls gateway warm-keep — not chat-session lifecycle.' +
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

    // M10 F6 L4: include the allowlist toggle + rows in the snapshot
    // so the dirty-tracker fires on toggle changes and add/remove/edit
    // of allowlist rows. Pairing state is NOT included — the pairing
    // button triggers an out-of-band POST that persists immediately,
    // independent of the editor's Save button (the in-memory
    // ``account.config.pairing`` mirror prevents data loss when the
    // operator then clicks Save with other dirty fields).
    var allowlist = null;
    var allowlistToggle = container.querySelector('.connector-allowlist-toggle');
    if (allowlistToggle) {
      var enabled = !!allowlistToggle.checked;
      var peersList = [];
      var channelsList = [];
      var allowlistInputs = container.querySelectorAll('.connector-allowlist-input');
      for (var a = 0; a < allowlistInputs.length; a++) {
        var ainp = allowlistInputs[a];
        var akind = ainp.getAttribute('data-allowlist-kind');
        var aval = ainp.value || '';
        if (akind === 'peers') peersList.push(aval);
        else if (akind === 'channels') channelsList.push(aval);
      }
      allowlist = { enabled: enabled, peers: peersList, channels: channelsList };
    }

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
      wireAllowlistEvents(container, checkDirty);
      // After wiring the allowlist events, recapture the snapshot so
      // the initial render's allowlist state doesn't count as dirty.
      // (renderConnectorAccountEditor pre-populates from
      // account.config.allowlist; getFormSnapshot now reads those rows.
      // The first call to attachStaticListeners happened before the
      // allowlist nodes existed in earlier code paths — they do exist
      // now since these sections render synchronously above. The
      // initial snapshot from line ~488 already includes the allowlist
      // state, so no recapture is strictly required, but we call
      // checkDirty once to ensure save/cancel button state agrees with
      // the just-rendered allowlist baseline.)
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
    // Allowlist: derive from the toggle + list editors. If the toggle
    // is unchecked, OMIT ``config.allowlist`` entirely (default-permit
    // semantic per leg-1b). If checked, emit ``{peers, channels}``
    // even when both lists are empty — that's the lockdown affordance
    // (leg-1b empty-preservation invariant).
    if (isEdit) {
      var allowlistState = collectAllowlistFromContainer(container);
      if (allowlistState && allowlistState.enabled) {
        config.allowlist = {
          peers: allowlistState.peers,
          channels: allowlistState.channels
        };
      } else {
        // Toggle unchecked — ensure no allowlist key leaks through
        // (defensively delete in case a kv-row added one).
        if (Object.prototype.hasOwnProperty.call(config, 'allowlist')) {
          delete config.allowlist;
        }
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

    // Issued-at summary row — present when a pairing record exists.
    // Empty placeholder otherwise so the section never feels blank.
    html += '<div class="field-row admin-pf-row">';
    html += '<label>Status</label>';
    html += '<div class="connector-pairing-status" data-testid="connector-pairing-status">';
    if (issuedAt) {
      html += 'Code on file (issued ' + escapeHtml(issuedAt) +
              '). The code is only shown immediately after generation — ' +
              'regenerate to reveal a fresh code.';
    } else {
      html += 'No pairing code generated yet.';
    }
    html += '</div>';
    html += '</div>';

    // Action row — button + transient code-reveal slot.
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<div class="connector-pairing-actions">';
    html += '<button type="button" class="btn-outlined-primary connector-pairing-generate-btn" ' +
            'data-testid="connector-pairing-generate-btn">' +
            escapeHtml(buttonLabel) + '</button>';
    html += '</div>';
    html += '</div>';

    // Code-reveal slot — populated after the operator clicks Generate /
    // Regenerate. Hidden on initial render (no auto-reveal on load).
    html += '<div class="field-row admin-pf-row connector-pairing-reveal-row" ' +
            'data-testid="connector-pairing-reveal-row" hidden>';
    html += '<label for="connector-pairing-code-readonly">Code</label>';
    html += '<div class="connector-pairing-reveal">';
    html += '<input type="text" id="connector-pairing-code-readonly" ' +
            'class="field-input admin-pf-input connector-pairing-code-input" ' +
            'data-testid="connector-pairing-code-input" readonly value="" />';
    html += '<button type="button" class="btn-outlined-primary connector-pairing-copy-btn" ' +
            'data-testid="connector-pairing-copy-btn">Copy</button>';
    html += '<small class="form-hint">Copy this code now — it will not be ' +
            'displayed again until you regenerate.</small>';
    html += '</div>';
    html += '</div>';

    html += '</div>';
    // Note: pairing state is mirrored to ``account.config.pairing`` by
    // the POST response and re-read on the next render. No form-snapshot
    // entry is needed (the button is not a dirty source — the endpoint
    // persists immediately, independent of the editor's Save button).
    void escapeAttr;
    return html;
  }

  function renderAllowlistSection(account) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var allowlist = (account && account.config && account.config.allowlist) || null;
    var enabled = allowlist != null;
    var peers = (allowlist && Array.isArray(allowlist.peers)) ? allowlist.peers.slice() : [];
    var channels = (allowlist && Array.isArray(allowlist.channels)) ? allowlist.channels.slice() : [];

    var html = '';
    html += '<div class="editor-section connector-allowlist-section">';
    html += '<div class="section-title">Account-scope allowlist</div>';

    // Toggle row.
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="connector-allowlist-enabled">Enable</label>';
    html += '<div>';
    html += '<input type="checkbox" id="connector-allowlist-enabled" ' +
            'class="connector-allowlist-toggle" ' +
            'data-testid="connector-allowlist-toggle"' +
            (enabled ? ' checked' : '') + ' />';
    html += '<small class="form-hint">' +
            'Check to gate inbounds + outbounds by peer / channel. ' +
            'Uncheck for default-permit (no allowlist on this account). ' +
            'When checked with empty lists below, this account is in ' +
            'lockdown — nothing is admitted until you add an entry or ' +
            'a pairing prefix promotes a peer.' +
            '</small>';
    html += '</div>';
    html += '</div>';

    // List editors — hidden when toggle is off.
    var listsHidden = enabled ? '' : ' hidden';
    html += '<div class="connector-allowlist-lists' + listsHidden +
            '" data-testid="connector-allowlist-lists">';
    html += renderAllowlistList('peers', 'Peers', peers);
    html += renderAllowlistList('channels', 'Channels', channels);
    html += '</div>';

    html += '</div>';
    void escapeHtml;
    void escapeAttr;
    return html;
  }

  function renderAllowlistList(kind, label, entries) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var html = '';
    html += '<div class="connector-allowlist-list" data-allowlist-kind="' +
            escapeAttr(kind) + '" data-testid="connector-allowlist-' +
            escapeAttr(kind) + '-list">';
    html += '<div class="connector-allowlist-list-header">' +
            '<strong>' + escapeHtml(label) + '</strong>' +
            '<button type="button" class="btn-outlined-primary kv-add-row-btn ' +
            'connector-allowlist-add-btn" data-allowlist-kind="' +
            escapeAttr(kind) + '" data-testid="connector-allowlist-' +
            escapeAttr(kind) + '-add-btn">+ Add</button>' +
            '</div>';
    html += '<div class="connector-allowlist-rows">';
    for (var i = 0; i < entries.length; i++) {
      html += renderAllowlistRow(kind, entries[i]);
    }
    html += '</div>';
    html += '</div>';
    return html;
  }

  function renderAllowlistRow(kind, value) {
    var escapeAttr = window.App.escapeAttr;
    var html = '';
    html += '<div class="connector-allowlist-row" data-allowlist-kind="' +
            escapeAttr(kind) + '">';
    html += '<input type="text" class="field-input admin-pf-input ' +
            'connector-allowlist-input" data-allowlist-kind="' +
            escapeAttr(kind) + '" value="' + escapeAttr(value || '') +
            '" placeholder="' + (kind === 'peers' ? 'peer id' : 'channel id') + '" />';
    html += '<button type="button" class="connector-allowlist-remove-btn" ' +
            'data-allowlist-kind="' + escapeAttr(kind) +
            '" aria-label="Remove entry" title="Remove">' +
            window.App.icon('trash') + '</button>';
    html += '</div>';
    return html;
  }

  function renderAttachedAgentsSection() {
    var html = '';
    html += '<div class="editor-section connector-attached-agents-section">';
    html += '<div class="section-title">Attached agents</div>';
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<div class="connector-attached-agents-list" ' +
            'data-testid="connector-attached-agents-list">' +
            '<em class="form-hint">Loading…</em>' +
            '</div>';
    html += '</div>';
    html += '</div>';
    return html;
  }

  function renderAttachedAgentsList(container, rows) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var listEl = container.querySelector('[data-testid="connector-attached-agents-list"]');
    if (!listEl) return;
    if (!rows || rows.length === 0) {
      listEl.innerHTML = '<em class="form-hint">No agents attached to this connector.</em>';
      return;
    }
    var html = '<ul class="connector-attached-agents">';
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {};
      var name = String(row.name || '');
      var peersCount = Number(row.peers_count || 0);
      var channelsCount = Number(row.channels_count || 0);
      // Deep-link to the Agent Editor — leg 5 will route the
      // ``#studio/agents/{name}`` URL with an additional fragment
      // for the Connectors tab. Until leg 5 lands, the existing
      // routing fallback displays the agent editor's default tab.
      html += '<li class="connector-attached-agent" ' +
              'data-testid="connector-attached-agent-' + escapeAttr(name) + '">';
      html += '<a href="#studio/agents/' + escapeAttr(name) + '" ' +
              'class="connector-attached-agent-link" ' +
              'data-testid="connector-attached-agent-link-' + escapeAttr(name) + '">' +
              escapeHtml(name) + '</a>';
      html += ' <span class="connector-attached-agent-counts">' +
              'peers: ' + escapeHtml(String(peersCount)) +
              ' · channels: ' + escapeHtml(String(channelsCount)) +
              '</span>';
      html += '</li>';
    }
    html += '</ul>';
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
      var originalLabel = btn.textContent;
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
            statusEl.textContent = 'Code on file (issued ' + (data.issued_at || '') +
                                   '). The code is only shown immediately after generation — ' +
                                   'regenerate to reveal a fresh code.';
          }
          // Relabel the button to "Regenerate code" once a code exists.
          btn.textContent = 'Regenerate code';

          // Mirror the new pairing into the local ``account.config``
          // so any subsequent Save (collectFormData) preserves it
          // through the merge step.
          if (!account.config) account.config = {};
          account.config.pairing = { code: data.code, issued_at: data.issued_at };

          window.App.showFlash(container, 'Pairing code generated. Click Save to persist other changes.');
        })
        .catch(function (err) {
          btn.textContent = originalLabel;
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

  function wireAllowlistEvents(container, checkDirty) {
    var toggle = container.querySelector('.connector-allowlist-toggle');
    var listsWrap = container.querySelector('[data-testid="connector-allowlist-lists"]');
    if (toggle && listsWrap) {
      toggle.addEventListener('change', function () {
        listsWrap.hidden = !toggle.checked;
        checkDirty();
      });
    }

    // Delegated input + click events on the allowlist section so
    // dynamically-added rows participate without re-binding.
    var section = container.querySelector('.connector-allowlist-section');
    if (!section) return;

    section.addEventListener('input', function (e) {
      var target = e.target;
      if (target && target.classList && target.classList.contains('connector-allowlist-input')) {
        checkDirty();
      }
    });

    section.addEventListener('click', function (e) {
      var target = e.target;
      if (!target) return;
      var addBtn = target.closest && target.closest('.connector-allowlist-add-btn');
      if (addBtn) {
        var kind = addBtn.getAttribute('data-allowlist-kind');
        var listEl = section.querySelector('[data-allowlist-kind="' + kind +
                                           '"].connector-allowlist-list');
        if (!listEl) return;
        var rowsWrap = listEl.querySelector('.connector-allowlist-rows');
        if (!rowsWrap) return;
        var tmp = document.createElement('div');
        tmp.innerHTML = renderAllowlistRow(kind, '');
        var newRow = tmp.querySelector('.connector-allowlist-row');
        if (newRow) {
          rowsWrap.appendChild(newRow);
          // Focus the newly-added input so the operator can start
          // typing immediately (keyboard reachability).
          var input = newRow.querySelector('input');
          if (input) input.focus();
          checkDirty();
        }
        return;
      }
      var removeBtn = target.closest && target.closest('.connector-allowlist-remove-btn');
      if (removeBtn) {
        var row = removeBtn.closest('.connector-allowlist-row');
        if (row && row.parentNode) {
          row.parentNode.removeChild(row);
          checkDirty();
        }
      }
    });
  }

  function collectAllowlistFromContainer(container) {
    // Returns ``{ enabled: bool, peers: list, channels: list }``. The
    // caller decides whether to emit ``config.allowlist`` based on
    // ``enabled``. Empty trimmed entries are dropped; whitespace-only
    // entries are not preserved.
    var toggle = container.querySelector('.connector-allowlist-toggle');
    if (!toggle) return null;
    var enabled = !!toggle.checked;
    var peers = [];
    var channels = [];
    var inputs = container.querySelectorAll('.connector-allowlist-input');
    for (var i = 0; i < inputs.length; i++) {
      var inp = inputs[i];
      var kind = inp.getAttribute('data-allowlist-kind');
      var val = (inp.value || '').trim();
      if (!val) continue;
      if (kind === 'peers') peers.push(val);
      else if (kind === 'channels') channels.push(val);
    }
    return { enabled: enabled, peers: peers, channels: channels };
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
