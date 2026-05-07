// App.studio.renderMcpSourceEditor — MCP source editor (M07 F1 L6;
// relocated from admin → studio post-F2 retrofit).
//
// Mirrors provider-editor.js structural shape:
//   <div class="editor-header"> … </div>
//   <div class="editor-section">Connection</div>          (name, type, transport-fields)
//   <div class="editor-section">Environment Variables /
//                               Custom Headers</div>      (unified kv table)
//   <div class="editor-section mcp-oauth-section"> … </div>  (streamable-http only)
//   <div class="editor-section danger-zone"> … </div>     (edit only)
//
// Per-row UI shape (option c): unified kv table with key / value / sensitive
// checkbox / eye / remove columns. The label swaps "Environment Variables"
// (stdio) ↔ "Custom Headers" (streamable-http) on type change. Sensitive=true
// rows route to `secrets[key]`; sensitive=false rows route to `config.env[key]`
// (stdio) or `config.headers[key]` (streamable-http).
//
// Per-key __MASKED__ round-trip: each kv row captures `_originalMasked` at
// mount via data-original-masked attribute. At save time, if value ===
// _originalMasked AND sensitive=true, payload sends '__MASKED__' for that key
// and the L3 endpoint preserves the stored secret.
//
// OAuth client_secret is locked sensitive=true and routes to
// secrets["oauth_client_secret"] (top-level, NOT nested under config.oauth).
// F5 looks up the secret by this exact key.
//
// callbacks: { onBack, onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange }
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var MASKED_SENTINEL = '__MASKED__';

  // ── Public entry point ──────────────────────────────────────────────

  function renderMcpSourceEditor(container, source, mcpTypes, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !source;
    var name = isCreate ? 'New MCP Server' : (source.name || '');
    var type = isCreate ? '' : (source.type || '');

    // ── Header ─────────────────────────────────────────────────────────
    var html = '';
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h1 class="editor-title">' + escapeHtml(name) + '</h1>';
    if (!isCreate) {
      var summary = '';
      if (source.config) {
        if (type === 'stdio' && source.config.command) summary = source.config.command;
        else if (type === 'streamable-http' && source.config.url) summary = source.config.url;
      }
      var subtitleParts = [escapeHtml(type)];
      if (summary) subtitleParts.push(escapeHtml(summary));
      html += '<p class="editor-subtitle">' + subtitleParts.join(' · ') + '</p>';
    }
    html += '</div>';

    // Action cluster
    html += '<div class="form-actions">';
    html += '<button type="button" class="btn-outlined-cyan back-btn" data-testid="back-mcp-source-btn" aria-label="Back to MCP server list">' + window.App.icon('arrow-left') + ' Back</button>';
    html += '<button type="button" class="btn-outlined-cyan cancel-btn" data-testid="cancel-mcp-source-btn" disabled>Cancel</button>';
    html += '<button type="button" class="btn-filled-cyan save-btn" data-testid="save-mcp-source-btn" disabled>' + (isCreate ? 'Create' : 'Save') + '</button>';
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // ── Connection section ────────────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Connection</div>';
    html += renderConnectionFields(source, mcpTypes);
    html += '</div>';

    // ── Sandbox section (stdio only) ──────────────────────────────────
    // F3 L5b: surfaces SandboxProfile fields for stdio sources. Auto-hides
    // for streamable-http via the existing mcp-stdio-only CSS class. The
    // chip-list mounts post-innerHTML in mountChipListEditors.
    var sandboxHidden = (type !== 'stdio');
    var sandbox = (!isCreate && source.config && source.config.sandbox) || {};
    var networkAllowed = sandbox.network_allowed === true;
    html += '<div class="editor-section mcp-stdio-only' + (sandboxHidden ? ' is-hidden' : '') + '" data-testid="mcp-sandbox-section">';
    html += '<div class="section-title">Sandbox</div>';
    // Network allowed: 2-column field-row (label left, iOS-style toggle right).
    // Mirrors admin tools-editor's renderEnabledRow pattern. The
    // class="field-input" on the checkbox keeps attachStaticListeners wiring
    // dirty-tracking via change events.
    var netTitleText = networkAllowed
      ? 'Network access enabled'
      : 'Network access disabled';
    html += '<div class="field-row admin-pf-row mf-sandbox-network-row">';
    html += '<label for="mf-sandbox-network-allowed">Allow network access</label>';
    html += '<label class="tool-enable-switch" title="' + escapeAttr(netTitleText) + '">';
    html += '<input type="checkbox" class="field-input" id="mf-sandbox-network-allowed" data-field="sandbox-network-allowed"' + (networkAllowed ? ' checked' : '') + ' aria-label="Allow network access" />';
    html += '<span class="tool-enable-switch-track" aria-hidden="true"></span>';
    html += '</label>';
    html += '</div>';
    // Writable paths chip-list (mounted via App.adminFormHelpers post-innerHTML).
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="mf-sandbox-writable-paths">Writable paths</label>';
    html += '<div class="chip-list-editor" id="mf-sandbox-writable-paths" data-field="sandbox-writable-paths" data-field-type="array"></div>';
    html += '</div>';
    html += '</div>';

    // ── Environment / Headers section ─────────────────────────────────
    var kvLabel = (type === 'streamable-http') ? 'Custom Headers' : 'Environment Variables';
    html += '<div class="editor-section">';
    html += '<div class="section-title kv-section-title" ' +
            'data-stdio-label="Environment Variables" ' +
            'data-streamable-http-label="Custom Headers">' +
            escapeHtml(kvLabel) + '</div>';
    html += renderKvTable(source, type);
    html += '<p class="kv-hint" data-testid="kv-hint">Sensitive values are encrypted at rest. ' +
            'Unchecking <strong>Sensitive</strong> on a stored secret clears the value &mdash; ' +
            're-type to keep it.</p>';
    html += '</div>';

    // ── OAuth section (streamable-http only) ──────────────────────────
    var oauthHidden = (type !== 'streamable-http');
    html += '<div class="editor-section mcp-oauth-section' + (oauthHidden ? ' is-hidden' : '') + '" data-testid="mcp-oauth-section">';
    html += '<div class="section-title">OAuth Client Configuration</div>';
    html += renderOAuthFields(source);
    html += '</div>';

    // ── Danger Zone (edit only) ───────────────────────────────────────
    if (!isCreate) {
      html += '<div class="editor-section danger-zone">';
      html += '<div class="section-title danger-zone-title">Danger Zone</div>';
      html += '<button type="button" class="btn-muted-destructive delete-btn" data-testid="delete-mcp-source-btn" data-name="' + escapeAttr(source.name || '') + '"><span data-confirm-title>Delete MCP Server</span></button>';
      html += '</div>';
    }

    container.innerHTML = html;

    mountChipListEditors(container, source);
    wireEditorEvents(container, source, mcpTypes, callbacks);
  }

  // ── Field rendering ─────────────────────────────────────────────────

  function renderConnectionFields(source, mcpTypes) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !source;
    var type = isCreate ? '' : (source.type || '');
    var stdioHidden = (type !== 'stdio');
    var streamableHidden = (type !== 'streamable-http');

    var html = '';

    // Name
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="mf-name">Name</label>';
    html += '<input class="field-input admin-pf-input" id="mf-name" data-field="name" value="' + escapeAttr(isCreate ? '' : (source.name || '')) + '" placeholder="My MCP Server" />';
    html += '</div>';

    // Type
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="mf-type">Type</label>';
    html += '<select class="field-input field-select admin-pf-input admin-pf-select" id="mf-type" data-field="type">';
    if (isCreate) html += '<option value="" disabled selected>Select a transport…</option>';
    var types = mcpTypes || [];
    for (var t = 0; t < types.length; t++) {
      var mt = types[t];
      html += '<option value="' + escapeAttr(mt.value) + '"' + (!isCreate && type === mt.value ? ' selected' : '') + '>' + escapeHtml(mt.label) + '</option>';
    }
    html += '</select>';
    html += '</div>';

    // stdio: command
    var commandValue = (!isCreate && source.config && source.config.command) ? source.config.command : '';
    html += '<div class="field-row admin-pf-row mcp-stdio-only' + (stdioHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-command">Command</label>';
    html += '<input class="field-input admin-pf-input" id="mf-command" data-field="command" value="' + escapeAttr(commandValue) + '" placeholder="github-mcp" />';
    html += '</div>';

    // stdio: cwd
    var cwdValue = (!isCreate && source.config && source.config.cwd) ? source.config.cwd : '';
    html += '<div class="field-row admin-pf-row mcp-stdio-only' + (stdioHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-cwd">Working Directory</label>';
    html += '<input class="field-input admin-pf-input" id="mf-cwd" data-field="cwd" value="' + escapeAttr(cwdValue) + '" placeholder="(optional)" />';
    html += '</div>';

    // stdio: args (chip-list, mounted via App.adminFormHelpers post-innerHTML)
    html += '<div class="field-row admin-pf-row mcp-stdio-only' + (stdioHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-args">Arguments</label>';
    html += '<div class="chip-list-editor" id="mf-args" data-field="args" data-field-type="array"></div>';
    html += '</div>';

    // streamable-http: url
    var urlValue = (!isCreate && source.config && source.config.url) ? source.config.url : '';
    html += '<div class="field-row admin-pf-row mcp-streamable-http-only' + (streamableHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-url">URL</label>';
    html += '<input class="field-input admin-pf-input" id="mf-url" data-field="url" value="' + escapeAttr(urlValue) + '" placeholder="https://example.com/mcp" />';
    html += '</div>';

    return html;
  }

  function collectExistingKvRows(source, type) {
    /* Walk source.config.env (stdio) or source.config.headers
       (streamable-http) AND source.secrets to build the kv-row union list.
       Per-row data shape: { key, value, sensitive, _originalMasked }.
       For sensitive rows the value field is the masked tail, captured into
       _originalMasked for round-trip preservation. */
    var rows = [];
    if (!source) return rows;
    var cfg = source.config || {};
    var plaintextDict = (type === 'streamable-http') ? (cfg.headers || {}) : (cfg.env || {});
    var secrets = source.secrets || {};
    var seen = Object.create(null);

    // Plaintext rows first (in dict-iteration order).
    for (var k in plaintextDict) {
      if (Object.prototype.hasOwnProperty.call(plaintextDict, k)) {
        rows.push({ key: k, value: String(plaintextDict[k]), sensitive: false, _originalMasked: '' });
        seen[k] = true;
      }
    }
    // Sensitive rows next, skipping the OAuth client_secret which lives in
    // its own dedicated field.
    for (var sk in secrets) {
      if (!Object.prototype.hasOwnProperty.call(secrets, sk)) continue;
      if (sk === 'oauth_client_secret') continue;
      if (seen[sk]) continue; // operator may have a duplicate key; plaintext wins.
      var maskedVal = String(secrets[sk] == null ? '' : secrets[sk]);
      rows.push({ key: sk, value: maskedVal, sensitive: true, _originalMasked: maskedVal });
    }
    return rows;
  }

  function renderKvTable(source, type) {
    var existingRows = collectExistingKvRows(source, type);
    var html = '<table class="mcp-kv-table" data-testid="mcp-kv-table">';
    html += '<thead><tr><th>Key</th><th>Value</th><th>Sensitive</th><th aria-label="Actions"></th></tr></thead>';
    html += '<tbody data-testid="mcp-kv-tbody">';
    for (var i = 0; i < existingRows.length; i++) {
      html += renderKvRow(existingRows[i], i);
    }
    html += '</tbody></table>';
    html += '<button type="button" class="btn-outlined-cyan kv-add-row-btn" data-testid="kv-add-row-btn">+ Add row</button>';
    return html;
  }

  function renderKvRow(row, idx) {
    var escapeAttr = window.App.escapeAttr;
    var sensitive = !!row.sensitive;
    var inputType = sensitive ? 'password' : 'text';
    var origMasked = row._originalMasked || '';
    var html = '';
    html += '<tr class="mcp-kv-row" data-row-idx="' + idx + '">';
    html += '<td><input class="field-input kv-key-input" data-field="kv-key" data-row="' + idx + '" value="' + escapeAttr(row.key || '') + '" placeholder="KEY" /></td>';
    html += '<td><div class="api-key-wrap">';
    html += '<input class="field-input kv-value-input' + (sensitive ? ' kv-value-secret' : '') + '" type="' + inputType + '" data-field="kv-value" data-row="' + idx + '" value="' + escapeAttr(row.value || '') + '" data-original-masked="' + escapeAttr(origMasked) + '" placeholder="value" />';
    if (sensitive) {
      html += '<button class="api-key-eye kv-eye-btn" type="button" data-row="' + idx + '" aria-label="Show value">' + window.App.icon('eye') + '</button>';
    }
    html += '</div></td>';
    html += '<td class="mcp-kv-sensitive-cell"><input type="checkbox" class="kv-sensitive-checkbox" data-field="kv-sensitive" data-row="' + idx + '"' + (sensitive ? ' checked' : '') + ' aria-label="Mark sensitive" /></td>';
    html += '<td><button type="button" class="kv-remove-row-btn" data-row="' + idx + '" aria-label="Remove row">' + window.App.icon('x') + '</button></td>';
    html += '</tr>';
    return html;
  }

  function renderOAuthFields(source) {
    var escapeAttr = window.App.escapeAttr;
    var oauth = (source && source.config && source.config.oauth) || {};
    var clientSecret = (source && source.secrets && source.secrets.oauth_client_secret) || '';

    var html = '';

    // issuer_url
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="mf-oauth-issuer-url">Issuer URL</label>';
    html += '<input class="field-input admin-pf-input" id="mf-oauth-issuer-url" data-field="oauth-issuer-url" value="' + escapeAttr(oauth.issuer_url || '') + '" placeholder="https://auth.example.com" />';
    html += '</div>';

    // client_id
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="mf-oauth-client-id">Client ID</label>';
    html += '<input class="field-input admin-pf-input" id="mf-oauth-client-id" data-field="oauth-client-id" value="' + escapeAttr(oauth.client_id || '') + '" placeholder="(optional — DCR auto-registers)" />';
    html += '</div>';

    // scopes (chip-list — mounted post-innerHTML)
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="mf-oauth-scopes">Scopes</label>';
    html += '<div class="chip-list-editor" id="mf-oauth-scopes" data-field="oauth-scopes" data-field-type="array"></div>';
    html += '</div>';

    // redirect_uri
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="mf-oauth-redirect-uri">Redirect URI</label>';
    html += '<input class="field-input admin-pf-input" id="mf-oauth-redirect-uri" data-field="oauth-redirect-uri" value="' + escapeAttr(oauth.redirect_uri || '') + '" placeholder="http://127.0.0.1:53682/callback" />';
    html += '</div>';

    // client_secret (always sensitive, locked checkbox)
    html += '<div class="field-row admin-pf-row">';
    html += '<label for="mf-oauth-client-secret">Client Secret</label>';
    html += '<div class="api-key-wrap">';
    html += '<input class="field-input admin-pf-input admin-pf-password" id="mf-oauth-client-secret" type="password" data-field="oauth-client-secret" value="' + escapeAttr(clientSecret) + '" data-original-masked="' + escapeAttr(clientSecret) + '" placeholder="(optional)" />';
    html += '<button class="api-key-eye oauth-client-secret-eye" type="button" aria-label="Show client secret">' + window.App.icon('eye') + '</button>';
    html += '</div>';
    html += '<input type="checkbox" class="kv-sensitive-checkbox" checked disabled aria-label="OAuth client secret is always sensitive" data-testid="oauth-client-secret-locked-sensitive" />';
    html += '</div>';

    return html;
  }

  // ── Chip-list mount helpers ─────────────────────────────────────────

  function mountChipListEditors(container, source) {
    var helpers = window.App.adminFormHelpers;
    if (!helpers || !helpers.renderChipListEditor) return;

    var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
    if (argsHost) {
      var argsItems = (source && source.config && source.config.args) || [];
      argsHost.outerHTML = helpers.renderChipListEditor('args', argsItems, null, {});
    }
    var scopesHost = container.querySelector('[data-field="oauth-scopes"].chip-list-editor');
    if (scopesHost) {
      var scopesItems = (source && source.config && source.config.oauth && source.config.oauth.scopes) || [];
      scopesHost.outerHTML = helpers.renderChipListEditor('oauth-scopes', scopesItems, null, {});
    }
    // F3 L5b: sandbox writable_paths chip-list (stdio only, but mount for
    // any type — visibility is controlled by the section's mcp-stdio-only
    // class).
    var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
    if (sandboxPathsHost) {
      var sandboxPathsItems = (source && source.config && source.config.sandbox && source.config.sandbox.writable_paths) || [];
      sandboxPathsHost.outerHTML = helpers.renderChipListEditor('sandbox-writable-paths', sandboxPathsItems, null, {});
    }
  }

  function wireChipLists(container, onChange) {
    var helpers = window.App.adminFormHelpers;
    if (!helpers || !helpers.wireChipListEditor) return;
    var hosts = container.querySelectorAll('.chip-list-editor');
    for (var i = 0; i < hosts.length; i++) {
      helpers.wireChipListEditor(hosts[i], { onChange: onChange });
    }
  }

  // ── Form snapshot + dirty tracking ──────────────────────────────────

  function getFormSnapshot(container) {
    /* Three explicit walks (avoid the flat data[dataset.field] = value
       collision since multiple kv rows share data-field="kv-key" etc.). */
    var helpers = window.App.adminFormHelpers;
    var staticData = {};
    // F3 L5b: sandbox-network-allowed is a checkbox; the loop below reads
    // el.checked for type === 'checkbox' and el.value otherwise.
    var staticFields = ['name', 'type', 'command', 'cwd', 'url',
                        'oauth-issuer-url', 'oauth-client-id',
                        'oauth-redirect-uri', 'oauth-client-secret',
                        'sandbox-network-allowed'];
    for (var i = 0; i < staticFields.length; i++) {
      var el = container.querySelector('[data-field="' + staticFields[i] + '"]:not(.chip-list-editor)');
      if (el && el.type === 'checkbox') {
        staticData[staticFields[i]] = !!el.checked;
      } else {
        staticData[staticFields[i]] = el ? el.value : '';
      }
    }

    var chips = { args: [], 'oauth-scopes': [], 'sandbox-writable-paths': [] };
    if (helpers && helpers.readChipListValue) {
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      if (argsHost) chips.args = helpers.readChipListValue(argsHost);
      var scopesHost = container.querySelector('[data-field="oauth-scopes"].chip-list-editor');
      if (scopesHost) chips['oauth-scopes'] = helpers.readChipListValue(scopesHost);
      var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      if (sandboxPathsHost) chips['sandbox-writable-paths'] = helpers.readChipListValue(sandboxPathsHost);
    }

    var kvRows = [];
    var rowEls = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row');
    for (var j = 0; j < rowEls.length; j++) {
      var row = rowEls[j];
      var keyEl = row.querySelector('.kv-key-input');
      var valueEl = row.querySelector('.kv-value-input');
      var sensEl = row.querySelector('.kv-sensitive-checkbox');
      kvRows.push({
        key: keyEl ? keyEl.value : '',
        value: valueEl ? valueEl.value : '',
        sensitive: sensEl ? !!sensEl.checked : false
      });
    }

    return JSON.stringify({ static: staticData, chips: chips, kvRows: kvRows });
  }

  // ── Event wiring ────────────────────────────────────────────────────

  function wireEditorEvents(container, source, mcpTypes, callbacks) {
    var isEdit = !!source;
    var snapshot = getFormSnapshot(container);
    var dirty = false;
    var nextRowIdx = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row').length;

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
      var inputs = container.querySelectorAll('.editor-section .field-input:not(.kv-key-input):not(.kv-value-input), .editor-section .field-select');
      for (var i = 0; i < inputs.length; i++) {
        // Skip chip-list elements (handled via wireChipLists).
        if (inputs[i].classList.contains('chip-list-editor')) continue;
        if (inputs[i].classList.contains('chip-list-input')) continue;
        inputs[i].addEventListener('input', checkDirty);
        inputs[i].addEventListener('change', checkDirty);
      }
    }
    attachStaticListeners();

    // Chip-list onChange bridges
    wireChipLists(container, checkDirty);

    // ── Type-change handler ───────────────────────────────────────────
    var typeSelect = container.querySelector('[data-field="type"]');
    if (typeSelect) {
      typeSelect.addEventListener('change', function () {
        applyTransportVisibility(container, typeSelect.value);
        // checkDirty already wired via static listener above.
      });
    }

    // ── kv table delegated events ─────────────────────────────────────
    var kvTable = container.querySelector('.mcp-kv-table');
    if (kvTable) {
      // Input/keyup on key/value inputs.
      kvTable.addEventListener('input', function (e) {
        var target = e.target;
        if (!target) return;
        if (target.classList && (target.classList.contains('kv-key-input') || target.classList.contains('kv-value-input'))) {
          checkDirty();
        }
      });

      // Change on sensitive checkbox + click on remove / eye buttons.
      kvTable.addEventListener('change', function (e) {
        var target = e.target;
        if (!target) return;
        if (target.classList && target.classList.contains('kv-sensitive-checkbox')) {
          handleSensitiveToggle(target);
          checkDirty();
        }
      });

      kvTable.addEventListener('click', function (e) {
        var target = e.target;
        if (!target) return;
        // Eye toggle (button OR svg inside)
        var eyeBtn = target.closest && target.closest('.kv-eye-btn');
        if (eyeBtn) {
          var row = eyeBtn.closest('tr.mcp-kv-row');
          if (row) {
            var valueInput = row.querySelector('.kv-value-input');
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
        // Remove row
        var removeBtn = target.closest && target.closest('.kv-remove-row-btn');
        if (removeBtn) {
          var rrow = removeBtn.closest('tr.mcp-kv-row');
          if (rrow) {
            rrow.parentNode.removeChild(rrow);
            checkDirty();
          }
          return;
        }
      });
    }

    // ── Add-row button ────────────────────────────────────────────────
    var addRowBtn = container.querySelector('.kv-add-row-btn');
    if (addRowBtn) {
      addRowBtn.addEventListener('click', function () {
        var tbody = container.querySelector('.mcp-kv-table tbody');
        if (!tbody) return;
        var idx = nextRowIdx++;
        var emptyRow = { key: '', value: '', sensitive: false, _originalMasked: '' };
        var tmp = document.createElement('tbody');
        tmp.innerHTML = renderKvRow(emptyRow, idx);
        var newTr = tmp.querySelector('tr.mcp-kv-row');
        if (newTr) {
          tbody.appendChild(newTr);
          checkDirty();
        }
      });
    }

    // ── OAuth client_secret eye-toggle ────────────────────────────────
    var oauthEye = container.querySelector('.oauth-client-secret-eye');
    var oauthSecretInput = container.querySelector('[data-field="oauth-client-secret"]');
    if (oauthEye && oauthSecretInput) {
      oauthEye.addEventListener('click', function () {
        if (oauthSecretInput.type === 'password') {
          oauthSecretInput.type = 'text';
          oauthEye.innerHTML = window.App.icon('eye-off');
          oauthEye.setAttribute('aria-label', 'Hide client secret');
        } else {
          oauthSecretInput.type = 'password';
          oauthEye.innerHTML = window.App.icon('eye');
          oauthEye.setAttribute('aria-label', 'Show client secret');
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
          revertEditorToSource(container, source, callbacks);
          // Re-bind delegated/static listeners that depend on snapshot/dirty
          // tracking — note: kv table itself was rebuilt; the table's
          // delegated listeners are still attached to the same .mcp-kv-table
          // element (we did innerHTML on the section, NOT replaceChild on
          // the table) — but to be safe, re-acquire references.
          // Actually we replace the tbody contents in-place.
          recaptureSnapshot();
        } else if (callbacks.onCancel) {
          callbacks.onCancel();
        }
      });
    }

    // ── Save ──────────────────────────────────────────────────────────
    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        var errorEl = container.querySelector('.editor-error');
        if (errorEl) errorEl.textContent = '';
        var payload = collectFormData(container, source, isEdit);
        if (!payload) return;
        var url = isEdit ? '/api/mcp-sources/' + encodeURIComponent(source.id) : '/api/mcp-sources';
        var method = isEdit ? 'PUT' : 'POST';
        fetch(url, {
          method: method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
          .then(function (r) {
            if (!r.ok) {
              return r.json().then(function (e) {
                var detail = e && e.detail;
                if (Array.isArray(detail)) {
                  // Pydantic ValidationError shape
                  detail = detail.map(function (d) {
                    var loc = (d.loc || []).join('.');
                    return loc ? (loc + ': ' + d.msg) : d.msg;
                  }).join(' | ');
                }
                throw new Error(detail || (isEdit ? 'Save failed' : 'Create failed'));
              });
            }
            return r.json();
          })
          .then(function (updated) {
            window.App.showFlash(container, isEdit ? 'MCP Server saved' : 'MCP Server created');
            if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, !isEdit);
            if (isEdit) {
              // Edit→edit: refresh snapshot from the masked response so
              // subsequent typing dirties from the post-save baseline.
              snapshot = getFormSnapshot(container);
              dirty = false;
              if (saveBtn) saveBtn.disabled = true;
              var c2 = container.querySelector('.cancel-btn');
              if (c2) c2.disabled = true;
              if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
            }
          })
          .catch(function (err) {
            if (errorEl) errorEl.textContent = err.message || String(err);
          });
      });
    }

    // ── Delete (edit only) ────────────────────────────────────────────
    var deleteBtn = container.querySelector('.delete-btn');
    if (deleteBtn && isEdit) {
      function doDelete(btn, revertFn) {
        fetch('/api/mcp-sources/' + encodeURIComponent(source.id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error((e && e.detail) || 'Delete failed'); });
            window.App.showFlash(container, 'MCP Server deleted');
            if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
          })
          .catch(function (err) {
            revertFn();
            window.App.showFlash(container, 'Error: ' + err.message, true);
          });
      }
      deleteBtn.addEventListener('click', function () {
        // L6: NO agent-usage pre-gate (F4 lands per-agent attachments).
        // Bare confirmDelete two-step.
        window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
      });
    }
  }

  // ── Sensitive toggle helpers ────────────────────────────────────────

  function handleSensitiveToggle(checkbox) {
    /* Toggle the value input's type between password/text + render or
       remove the eye-toggle. Critical: when unchecking sensitive on a
       row whose value still equals _originalMasked, clear the value
       field — otherwise the masked tail leaks into plaintext on save. */
    var row = checkbox.closest('tr.mcp-kv-row');
    if (!row) return;
    var valueInput = row.querySelector('.kv-value-input');
    var wrap = row.querySelector('.api-key-wrap');
    if (!valueInput || !wrap) return;

    if (checkbox.checked) {
      // → sensitive
      valueInput.type = 'password';
      valueInput.classList.add('kv-value-secret');
      // Add eye button if missing.
      if (!wrap.querySelector('.kv-eye-btn')) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'api-key-eye kv-eye-btn';
        btn.setAttribute('data-row', valueInput.dataset.row || '');
        btn.setAttribute('aria-label', 'Show value');
        btn.innerHTML = window.App.icon('eye');
        wrap.appendChild(btn);
      }
    } else {
      // → plaintext
      var origMasked = valueInput.dataset.originalMasked || '';
      if (origMasked && valueInput.value === origMasked) {
        // Clear the masked tail so it doesn't leak into config.env / config.headers.
        valueInput.value = '';
      }
      valueInput.type = 'text';
      valueInput.classList.remove('kv-value-secret');
      var eye = wrap.querySelector('.kv-eye-btn');
      if (eye) eye.parentNode.removeChild(eye);
    }
  }

  // ── Type-change visibility helpers ──────────────────────────────────

  function applyTransportVisibility(container, type) {
    var stdioRows = container.querySelectorAll('.mcp-stdio-only');
    var streamableRows = container.querySelectorAll('.mcp-streamable-http-only');
    for (var i = 0; i < stdioRows.length; i++) {
      stdioRows[i].classList.toggle('is-hidden', type !== 'stdio');
    }
    for (var j = 0; j < streamableRows.length; j++) {
      streamableRows[j].classList.toggle('is-hidden', type !== 'streamable-http');
    }
    var oauthSection = container.querySelector('.mcp-oauth-section');
    if (oauthSection) oauthSection.classList.toggle('is-hidden', type !== 'streamable-http');

    var kvLabel = container.querySelector('.kv-section-title');
    if (kvLabel) {
      var stdioLabel = kvLabel.getAttribute('data-stdio-label') || 'Environment Variables';
      var streamLabel = kvLabel.getAttribute('data-streamable-http-label') || 'Custom Headers';
      kvLabel.textContent = (type === 'streamable-http') ? streamLabel : stdioLabel;
    }
  }

  // ── Cancel-revert: rebuild kv-table + chip-lists from source ────────

  function revertEditorToSource(container, source, callbacks) {
    /* In edit mode, revert the form to the source object. Static fields
       restore via a value-loop; the kv-table rebuilds from source (its
       row count can change during edit); chip-list editors re-mount
       fresh. */
    if (!source) return;

    // 1. Static fields
    var staticMap = {
      'name': source.name || '',
      'type': source.type || '',
      'command': (source.config && source.config.command) || '',
      'cwd': (source.config && source.config.cwd) || '',
      'url': (source.config && source.config.url) || '',
      'oauth-issuer-url': (source.config && source.config.oauth && source.config.oauth.issuer_url) || '',
      'oauth-client-id': (source.config && source.config.oauth && source.config.oauth.client_id) || '',
      'oauth-redirect-uri': (source.config && source.config.oauth && source.config.oauth.redirect_uri) || '',
      'oauth-client-secret': (source.secrets && source.secrets.oauth_client_secret) || ''
    };
    Object.keys(staticMap).forEach(function (key) {
      var el = container.querySelector('[data-field="' + key + '"]:not(.chip-list-editor)');
      if (el) el.value = staticMap[key];
    });
    // F3 L5b: sandbox-network-allowed is a checkbox — its display state
    // is controlled by .checked, not .value. Pulled out of the loop above
    // so el.value = ... doesn't no-op the visible checked state.
    var sandboxNetEl = container.querySelector('[data-field="sandbox-network-allowed"]:not(.chip-list-editor)');
    if (sandboxNetEl) {
      sandboxNetEl.checked = !!(source.config && source.config.sandbox && source.config.sandbox.network_allowed === true);
    }

    // 2. Visibility
    applyTransportVisibility(container, source.type || '');

    // 3. KV table — rebuild tbody contents
    var tbody = container.querySelector('.mcp-kv-table tbody');
    if (tbody) {
      var rows = collectExistingKvRows(source, source.type || '');
      var html = '';
      for (var i = 0; i < rows.length; i++) {
        html += renderKvRow(rows[i], i);
      }
      tbody.innerHTML = html;
    }

    // 4. Chip-list editors — re-mount fresh
    var helpers = window.App.adminFormHelpers;
    if (helpers && helpers.renderChipListEditor) {
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      if (argsHost && argsHost.parentNode) {
        var wrapper = document.createElement('div');
        wrapper.innerHTML = helpers.renderChipListEditor('args', (source.config && source.config.args) || [], null, {});
        var newArgs = wrapper.firstChild;
        argsHost.parentNode.replaceChild(newArgs, argsHost);
        if (helpers.wireChipListEditor) {
          helpers.wireChipListEditor(newArgs, function () {
            // Note: this onChange fires before we have a recaptured snapshot;
            // the orchestrator's wireEditorEvents runs once per render and
            // captures dirty-tracking via its own checkDirty closure. After
            // a Cancel revert, we recaptureSnapshot externally.
          });
        }
      }
      var scopesHost = container.querySelector('[data-field="oauth-scopes"].chip-list-editor');
      if (scopesHost && scopesHost.parentNode) {
        var wrapper2 = document.createElement('div');
        wrapper2.innerHTML = helpers.renderChipListEditor('oauth-scopes',
          (source.config && source.config.oauth && source.config.oauth.scopes) || [],
          null, {});
        var newScopes = wrapper2.firstChild;
        scopesHost.parentNode.replaceChild(newScopes, scopesHost);
        if (helpers.wireChipListEditor) {
          helpers.wireChipListEditor(newScopes, function () { /* dirty-tracking handled externally */ });
        }
      }
      // F3 L5b: sandbox writable_paths chip-list re-mount.
      var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      if (sandboxPathsHost && sandboxPathsHost.parentNode) {
        var wrapper3 = document.createElement('div');
        wrapper3.innerHTML = helpers.renderChipListEditor('sandbox-writable-paths',
          (source.config && source.config.sandbox && source.config.sandbox.writable_paths) || [],
          null, {});
        var newSandboxPaths = wrapper3.firstChild;
        sandboxPathsHost.parentNode.replaceChild(newSandboxPaths, sandboxPathsHost);
        if (helpers.wireChipListEditor) {
          helpers.wireChipListEditor(newSandboxPaths, function () { /* dirty-tracking handled externally */ });
        }
      }
    }
  }

  // ── Payload assembly ────────────────────────────────────────────────

  function collectFormData(container, source, isEdit) {
    /* Routes by `type` (NOT by visible-field set). A type-change
       immediately followed by Save emits the type-correct payload. */
    var errorEl = container.querySelector('.editor-error');
    var nameEl = container.querySelector('[data-field="name"]');
    var name = nameEl ? nameEl.value.trim() : '';
    if (!name) {
      if (errorEl) errorEl.textContent = 'Name is required.';
      return null;
    }
    var typeEl = container.querySelector('[data-field="type"]');
    var type = typeEl ? typeEl.value : '';
    if (!type) {
      if (errorEl) errorEl.textContent = 'Type is required.';
      return null;
    }

    var config = {};
    var secrets = {};

    if (type === 'stdio') {
      var commandEl = container.querySelector('[data-field="command"]');
      var command = commandEl ? commandEl.value.trim() : '';
      if (!command) {
        if (errorEl) errorEl.textContent = 'Command is required for stdio servers.';
        return null;
      }
      config.command = command;
      var cwdEl = container.querySelector('[data-field="cwd"]');
      var cwd = cwdEl ? cwdEl.value.trim() : '';
      if (cwd) config.cwd = cwd;
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      var helpers = window.App.adminFormHelpers;
      var argsList = (argsHost && helpers && helpers.readChipListValue) ? helpers.readChipListValue(argsHost) : [];
      if (argsList.length > 0) config.args = argsList;
      config.env = {};
      partitionKvRows(container, config.env, secrets);
      // F3 L5b: sandbox profile (stdio only). Always-emit precedent
      // matches config.env above: empty defaults are written explicitly,
      // not omitted. The L1b API validator accepts the default shape.
      var sandboxNetEl = container.querySelector('[data-field="sandbox-network-allowed"]');
      var networkAllowed = !!(sandboxNetEl && sandboxNetEl.checked);
      var sandboxPathsList = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      var writablePaths = (sandboxPathsList && helpers && helpers.readChipListValue) ? helpers.readChipListValue(sandboxPathsList) : [];
      config.sandbox = { network_allowed: networkAllowed, writable_paths: writablePaths };
    } else if (type === 'streamable-http') {
      var urlEl = container.querySelector('[data-field="url"]');
      var urlValue = urlEl ? urlEl.value.trim() : '';
      if (!urlValue) {
        if (errorEl) errorEl.textContent = 'URL is required for streamable-http servers.';
        return null;
      }
      config.url = urlValue;
      config.headers = {};
      partitionKvRows(container, config.headers, secrets);
      // OAuth section
      collectOAuthSection(container, source, config, secrets, isEdit);
    } else {
      if (errorEl) errorEl.textContent = 'Unsupported transport type: ' + type;
      return null;
    }

    return { name: name, type: type, config: config, secrets: secrets };
  }

  function partitionKvRows(container, plaintextDict, secretsDict) {
    var rows = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row');
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var keyEl = row.querySelector('.kv-key-input');
      var valueEl = row.querySelector('.kv-value-input');
      var sensEl = row.querySelector('.kv-sensitive-checkbox');
      if (!keyEl || !valueEl) continue;
      var key = (keyEl.value || '').trim();
      if (!key) continue; // empty key → silently skip
      var value = valueEl.value || '';
      var sensitive = !!(sensEl && sensEl.checked);
      var origMasked = valueEl.dataset.originalMasked || '';
      if (sensitive) {
        if (origMasked && value === origMasked) {
          // Per-row MASKED_SENTINEL — preserves stored secret backend-side.
          secretsDict[key] = MASKED_SENTINEL;
        } else {
          secretsDict[key] = value;
        }
      } else {
        plaintextDict[key] = value;
      }
    }
  }

  function collectOAuthSection(container, source, config, secrets, isEdit) {
    /* Reads OAuth plaintext fields + client_secret. Behavior:
       - If all plaintext fields and client_secret are empty, omit
         config.oauth entirely (create-mode).
       - Otherwise build config.oauth with only non-empty plaintext fields,
         and route client_secret into secrets["oauth_client_secret"] using
         per-row MASKED_SENTINEL semantic.
       - Stranded-secret edge case (edit mode): if the operator cleared the
         OAuth config but the source previously had oauth_client_secret,
         emit secrets["oauth_client_secret"] = "" so backend's per-key
         MASKED handler treats it as overwrite-with-empty. */
    var helpers = window.App.adminFormHelpers;
    var issuerEl = container.querySelector('[data-field="oauth-issuer-url"]');
    var clientIdEl = container.querySelector('[data-field="oauth-client-id"]');
    var redirectEl = container.querySelector('[data-field="oauth-redirect-uri"]');
    var secretEl = container.querySelector('[data-field="oauth-client-secret"]');
    var scopesHost = container.querySelector('[data-field="oauth-scopes"].chip-list-editor');

    var issuer = issuerEl ? issuerEl.value.trim() : '';
    var clientId = clientIdEl ? clientIdEl.value.trim() : '';
    var redirect = redirectEl ? redirectEl.value.trim() : '';
    var secretValue = secretEl ? (secretEl.value || '') : '';
    var origSecretMasked = secretEl ? (secretEl.dataset.originalMasked || '') : '';
    var scopes = (scopesHost && helpers && helpers.readChipListValue) ? helpers.readChipListValue(scopesHost) : [];

    var hasAnyOAuth = !!(issuer || clientId || redirect || (scopes && scopes.length > 0) || secretValue);
    var hadStoredSecret = !!(source && source.secrets && source.secrets.oauth_client_secret);

    if (hasAnyOAuth) {
      var oauth = {};
      if (issuer) oauth.issuer_url = issuer;
      if (clientId) oauth.client_id = clientId;
      if (redirect) oauth.redirect_uri = redirect;
      if (scopes && scopes.length > 0) oauth.scopes = scopes;
      config.oauth = oauth;

      if (secretValue) {
        if (origSecretMasked && secretValue === origSecretMasked) {
          // Unchanged masked tail — preserve stored secret.
          secrets.oauth_client_secret = MASKED_SENTINEL;
        } else {
          secrets.oauth_client_secret = secretValue;
        }
      }
      // If secretValue is empty but operator has populated other OAuth fields,
      // we omit oauth_client_secret from secrets (no stored secret to preserve).
    } else if (isEdit && hadStoredSecret) {
      // Stranded-secret: operator cleared the entire OAuth section; drop the
      // ciphertext blob explicitly.
      secrets.oauth_client_secret = '';
    }
  }

  window.App.studio.renderMcpSourceEditor = renderMcpSourceEditor;
})();
