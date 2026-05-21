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
// callbacks: { onBack, onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange,
//              onTabChange, initialTab }
//
// M10 F7 L9 HAT: edit-mode renders a tabbed layout matching the Agent
// Editor's pattern. Operator-specified split:
//   Tab "General"            — Connection, Credentials, Pairing,
//                              Attached agents, Test connection,
//                              Danger zone.
//   Tab "Access and Routing" — Lifecycle, Allowlist, Routing rules.
// Create mode renders flat (only the Connection + Credentials + Lifecycle
// sections render there — not enough sections to justify the tab split).
// All tab panel contents mount SYNCHRONOUSLY at editor-load time so the
// L7 dirty-tracker / snapshot logic + selectors continue to resolve
// against any section regardless of which tab is currently active.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var MASKED_SENTINEL = '__MASKED__';

  // M11 F1 L6 — Display-text vocabulary substitution. The substrate's
  // persisted vocabulary stays at "peer / channel / guild / role"
  // (Pydantic models, ACL field names, _VALID_ROUTING_SCOPES literals,
  // audit-log keys); only the rendered display labels vary per
  // connector type. Call sites consult ``App.studio.connectorVocabulary``
  // via the triple-guard below; if the script failed to load, the
  // inline ``_DEFAULT_VOCAB_INLINE`` reproduces the pre-L6 baseline
  // ("Peers / Channels / Guilds / Roles") byte-for-byte so no rendering
  // path throws or drifts.
  var _DEFAULT_VOCAB_INLINE = {
    peer: 'peer', peers: 'peers',
    group: 'guild', groups: 'guilds',
    channel: 'channel', channels: 'channels',
    role: 'role', roles: 'roles',
    hintTone: 'generic'
  };

  function _capitalize(s) {
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
  }

  function _vocabForAccount(account) {
    var type = (account && account.type) || '';
    var v = (window.App && window.App.studio && window.App.studio.connectorVocabulary)
      ? window.App.studio.connectorVocabulary.get(type)
      : null;
    return v || _DEFAULT_VOCAB_INLINE;
  }

  // M10 F7 L9 HAT: tab panel ids. Mirror agent-editor.js's PANEL_IDS
  // pattern so test selectors that hop between the two editors share a
  // naming convention.
  var PANEL_IDS = {
    general: 'connector-tab-panel-general',
    accessAndRouting: 'connector-tab-panel-access-and-routing'
  };

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
    // M10 F7 L9 HAT: tabbed-layout default. Mirrors agent-editor.js
    // (initialTab callback param, default to 'general'). The studio
    // shell does not yet route _activeTab into the connector-account
    // editor, but the hook is in place for future wiring.
    var initialTab = callbacks.initialTab || 'general';

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

    // ── Build per-section HTML fragments ──────────────────────────────
    // M10 F7 L9 HAT: section emission decoupled from layout so the same
    // fragments can be slotted either flat (create mode) or partitioned
    // across two tab panels (edit mode). All sections mount
    // SYNCHRONOUSLY at editor-load time — never lazy — so the L7
    // dirty-tracker / collectFormData selectors continue to resolve
    // against every section regardless of which tab is currently
    // active.

    // Connection section.
    var connectionHtml = '';
    connectionHtml += '<div class="editor-section">';
    connectionHtml += '<div class="section-title">Connection</div>';
    connectionHtml += renderConnectionFields(account, types, isCreate);
    connectionHtml += '</div>';

    // Credentials section.
    var credentialsHtml = '';
    credentialsHtml += '<div class="editor-section">';
    credentialsHtml += '<div class="section-title">Credentials</div>';
    credentialsHtml += renderSecretsKvTable(account);
    credentialsHtml += '</div>';

    // Lifecycle section.
    // F5 L8 HAT: free-form numeric inputs replaced with dropdowns offering
    // the operator-friendly ladder defined in LIFECYCLE_OPTIONS below. The
    // continuation field also offers a "Never (always continue)" option
    // representing null; the idle-timeout field only offers the default
    // sentinel (empty string → null). Custom persisted values that don't
    // match a ladder entry are rendered as a disabled "Custom: Xs" option
    // so the operator sees what's stored without overwriting it.
    var idleValue = (!isCreate && account.idle_timeout_seconds != null) ? account.idle_timeout_seconds : '';
    var contValue = (!isCreate && account.session_continuation_seconds != null) ? account.session_continuation_seconds : '';
    var lifecycleHtml = '';
    lifecycleHtml += '<div class="editor-section">';
    lifecycleHtml += '<div class="section-title">Lifecycle</div>';

    // Pool idle timeout (F2)
    lifecycleHtml += '<div class="field-row admin-pf-row">';
    lifecycleHtml += '<label for="cf-idle-timeout">Pool idle timeout</label>';
    lifecycleHtml += renderLifecycleSelect('cf-idle-timeout', 'idle_timeout_seconds',
            'connector-account-idle-timeout-input', idleValue,
            { defaultSeconds: 1800, includeNever: false });
    lifecycleHtml += '</div>';
    lifecycleHtml += '<div class="field-row admin-pf-row">';
    lifecycleHtml += '<label></label>';
    lifecycleHtml += '<small class="form-hint" data-testid="connector-account-idle-hint">' +
            'Reap warm connection after inactivity.' +
            '</small>';
    lifecycleHtml += '</div>';

    // Chat-session continuation window (F3 L5)
    lifecycleHtml += '<div class="field-row admin-pf-row">';
    lifecycleHtml += '<label for="cf-continuation-window">Chat-session continuation window</label>';
    lifecycleHtml += renderLifecycleSelect('cf-continuation-window', 'session_continuation_seconds',
            'connector-account-continuation-input', contValue,
            { defaultSeconds: 86400, includeNever: true });
    lifecycleHtml += '</div>';
    lifecycleHtml += '<div class="field-row admin-pf-row">';
    lifecycleHtml += '<label></label>';
    lifecycleHtml += '<small class="form-hint" data-testid="connector-account-continuation-hint">' +
            'Inbound continues the same chat session within this window.' +
            '</small>';
    lifecycleHtml += '</div>';

    // Auto-relay peer replies to platform (M10 F8 L11 HAT Fix #4).
    // Default-on opt-in setting; stored in ``config.auto_relay_platform_replies``.
    // Absent → treated as True at consume time (dispatcher reads
    // ``account.config.get("auto_relay_platform_replies", True)``).
    // The checkbox renders checked (= auto-relay ON) by default for new
    // accounts AND for existing accounts that lack the key explicitly.
    var autoRelayConfigValue = (!isCreate && account.config && Object.prototype.hasOwnProperty.call(account.config, 'auto_relay_platform_replies'))
        ? !!account.config.auto_relay_platform_replies
        : true;
    lifecycleHtml += '<div class="field-row admin-pf-row">';
    lifecycleHtml += '<label for="cf-auto-relay">Auto-relay peer replies to platform</label>';
    lifecycleHtml += '<input type="checkbox" id="cf-auto-relay" ' +
            'data-field="auto_relay_platform_replies" ' +
            'data-testid="connector-account-auto-relay-toggle"' +
            (autoRelayConfigValue ? ' checked' : '') + ' />';
    lifecycleHtml += '</div>';
    lifecycleHtml += '<div class="field-row admin-pf-row">';
    lifecycleHtml += '<label></label>';
    lifecycleHtml += '<small class="form-hint" data-testid="connector-account-auto-relay-hint">' +
            "When enabled, the agent's plaintext replies to platform peers are automatically posted back to the platform. " +
            'Disable to require the agent to explicitly invoke send_to_platform_channel — useful if you want the agent to deliberate before responding to peers.' +
            '</small>';
    lifecycleHtml += '</div>';

    lifecycleHtml += '</div>';

    // Pairing section (edit mode only).
    // M10 F6 L4: operator generates / regenerates the account pairing
    // code. The endpoint is the only writer for ``config["pairing"]``.
    var pairingHtml = isCreate ? '' : renderPairingSection(account);

    // Account-scope allowlist section (edit mode only).
    // M10 F6 L4: account-level peer/channel allowlist editor.
    var allowlistHtml = isCreate ? '' : renderAllowlistSection(account);

    // Routing Rules section (edit mode only).
    // M10 F7 L7: operator-authored, ordered routing rules + per-account
    // default agent. Rides ``config.routing`` (L2 validator).
    var routingHtml = isCreate ? '' : renderRoutingRulesSection(account);

    // Attached agents (read-only, edit mode only).
    // M10 F6 L4: read-only summary of agents whose
    // ``connector_account_ids`` includes this account.
    var attachedAgentsHtml = isCreate ? '' : renderAttachedAgentsSection();

    // Test Connection section (edit mode only).
    var testConnectionHtml = '';
    if (!isCreate) {
      testConnectionHtml += '<div class="editor-section connector-test-section">';
      testConnectionHtml += '<div class="section-title">Test Connection</div>';
      testConnectionHtml += '<div class="connector-test-actions">';
      testConnectionHtml += '<button type="button" class="btn-outlined-primary connector-test-connection-btn" data-testid="connector-test-connection-btn">' +
              window.App.icon('refresh-cw') + ' Test connection</button>';
      testConnectionHtml += '<span class="indicator-led indicator-led--idle connector-test-led" data-testid="connector-test-led" data-state="idle" aria-label="Not tested"></span>';
      testConnectionHtml += '<span class="connector-test-message" data-testid="connector-test-message">Not tested</span>';
      testConnectionHtml += '</div>';
      testConnectionHtml += '<div class="connector-test-status" data-testid="connector-test-status" hidden></div>';
      testConnectionHtml += '<div class="connector-test-details-wrap" data-testid="connector-test-details-wrap" hidden>' +
              '<div data-testid="connector-test-details"></div>' +
              '</div>';
      testConnectionHtml += '</div>';
    }

    // Invite section (edit mode only) — M11 F1 L5.
    // The Invite section is registry-mediated: the active connector
    // type's entry provides an OPTIONAL ``renderInviteSection(account)``
    // hook. Unregistered types (e.g. ``'stub'``) or types without the
    // hook produce no section — preserves byte-identical DOM for
    // ``'stub'`` tests.
    var inviteHtml = '';
    if (!isCreate) {
      var inviteRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
      var inviteEntry = (inviteRegistry && account && account.type) ? inviteRegistry.get(account.type) : undefined;
      if (inviteEntry && typeof inviteEntry.renderInviteSection === 'function') {
        inviteHtml = inviteEntry.renderInviteSection(account);
      }
    }

    // Danger Zone (edit only).
    var dangerZoneHtml = '';
    if (!isCreate) {
      dangerZoneHtml += '<div class="editor-section danger-zone">';
      dangerZoneHtml += '<div class="section-title danger-zone-title">Danger Zone</div>';
      dangerZoneHtml += '<button type="button" class="btn-muted-destructive delete-btn connector-delete-btn" data-testid="delete-connector-account-btn" data-name="' + escapeAttr(account.name || '') + '">' +
              window.App.icon('trash') +
              '<span data-confirm-title>Delete Connector</span>' +
              '</button>';
      dangerZoneHtml += '</div>';
    }

    // ── Layout assembly ───────────────────────────────────────────────
    // Create mode: flat layout (only Connection / Credentials / Lifecycle
    // render anyway — not enough sections to justify the tab split).
    // Edit mode: two-tab layout per operator partition:
    //   "General"            — Connection, Credentials, Pairing,
    //                          Attached agents, Test connection,
    //                          Danger zone.
    //   "Access and Routing" — Lifecycle, Allowlist, Routing rules.
    if (isCreate) {
      html += connectionHtml;
      html += credentialsHtml;
      html += lifecycleHtml;
    } else {
      // Tablist.
      html += '<div role="tablist" class="tablist" aria-label="Connector account settings">';
      html += '<button type="button" role="tab" class="tab" id="connector-tab-general" ' +
              'aria-controls="' + PANEL_IDS.general + '" data-tab-id="general" ' +
              'data-testid="tab-general" aria-selected="false" tabindex="-1">General</button>';
      html += '<button type="button" role="tab" class="tab" id="connector-tab-access-and-routing" ' +
              'aria-controls="' + PANEL_IDS.accessAndRouting + '" data-tab-id="access-and-routing" ' +
              'data-testid="tab-access-and-routing" aria-selected="false" tabindex="-1">Access and Routing</button>';
      html += '</div>';

      // Tab panels — ALL section content is mounted into the DOM
      // synchronously here. App.tabs only toggles the `hidden` attribute
      // for non-active panels, so every selector that L7 wired (form
      // snapshot, dirty-tracker, collectFormData, attached-agents fetch)
      // continues to resolve against any section regardless of which
      // tab is currently active.
      html += '<div class="tabpanels">';
      // General tab — Connection, Credentials, Pairing, Attached agents,
      // Test connection, Danger zone.
      html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.general +
              '" data-tab-id="general" aria-labelledby="connector-tab-general" hidden>';
      html += connectionHtml;
      html += credentialsHtml;
      html += pairingHtml;
      html += attachedAgentsHtml;
      html += testConnectionHtml;
      html += inviteHtml;
      html += dangerZoneHtml;
      html += '</div>';
      // Access and Routing tab — Lifecycle, Allowlist, Routing rules.
      // Lifecycle (session-continuation window) is policy-shaped enough
      // to belong with the access controls per operator intent.
      html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.accessAndRouting +
              '" data-tab-id="access-and-routing" aria-labelledby="connector-tab-access-and-routing" hidden>';
      html += lifecycleHtml;
      html += allowlistHtml;
      html += routingHtml;
      html += '</div>';
      html += '</div>'; // .tabpanels
    }

    html += '</div>'; // .connector-account-editor

    container.innerHTML = html;

    // Initialize App.tabs in edit mode. The tablist + tabpanels are
    // already in the DOM; this just wires keyboard navigation +
    // aria-selected + hidden-attr toggling, and activates the initial
    // tab so its panel becomes visible synchronously.
    if (!isCreate) {
      var tablistEl = container.querySelector('.tablist');
      var panelsEl = container.querySelector('.tabpanels');
      if (tablistEl && panelsEl && window.App.tabs) {
        window.App.tabs(tablistEl, panelsEl, {
          onChange: callbacks.onTabChange,
          initial: initialTab
        });
      }
    }

    wireEditorEvents(container, account, types, callbacks, isCreate);

    // After mount, consume any pending probe report (set by the
    // create-and-test handler in the previous editor mount).
    if (!isCreate && _pendingProbeReport) {
      var report = _pendingProbeReport;
      _pendingProbeReport = null;
      renderTestConnectionBanner(container, report, account.id);
    }
  }

  // ── Field rendering ─────────────────────────────────────────────────

  function renderConnectionFields(account, types, isCreate) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var html = '';
    var typesList = Array.isArray(types) ? types : [];
    var typesEmpty = isCreate && typesList.length === 0;

    // M10 F6 L7 HAT: when production has zero registered connector types,
    // surface a themed banner inside the Connection section instead of
    // just an unselectable dropdown placeholder. F8 L2 registered
    // `'discord'`, so production normally renders a populated dropdown;
    // the banner remains a fallback when the registry is empty (e.g.
    // tests, or operator override of `register_builtin_connectors`).
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
    //
    // M11 F1 L3: per-type form registry consult. The substrate emits
    // the outer field-row wrapper unconditionally so the
    // ``[data-testid="connector-account-config"]`` selector keeps
    // resolving for tests; only the inner content varies between the
    // typed (entry.renderConnectionFields) and generic
    // (renderConfigKvTable) render paths. Triple-guard against an
    // early-load race where the registry script hasn't attached yet.
    var connRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var connActiveType = isCreate ? '' : ((account && account.type) || '');
    var connEntry = (connRegistry && connActiveType) ? connRegistry.get(connActiveType) : undefined;

    html += '<div class="field-row admin-pf-row connector-account-config-wrap">';
    html += '<label>Config</label>';
    html += '<div class="connector-account-config" data-testid="connector-account-config">';
    if (connEntry && typeof connEntry.renderConnectionFields === 'function') {
      html += connEntry.renderConnectionFields(account, isCreate);
    } else {
      html += renderConfigKvTable(account);
    }
    html += '</div>';
    html += '</div>';

    return html;
  }

  // M10 F6 L4: reserved top-level ``config`` keys owned by dedicated
  // editor sections (Pairing, Allowlist). These are NOT shown in the
  // arbitrary kv-table — the dedicated sections are the only writers,
  // and ``collectFormData`` merges them back into the save payload so
  // they round-trip without operator intervention.
  // M10 F7 L7: ``routing`` joins the reserved set — the Routing Rules
  // editor section is the only writer for ``config.routing`` and merges
  // its state back into the PUT payload via ``collectRoutingFromContainer``.
  var RESERVED_CONFIG_KEYS = { pairing: true, allowlist: true, routing: true };

  function collectConfigRows(account) {
    var rows = [];
    if (!account || !account.config) return rows;

    // M11 F1 L3: compose the effective reserved set as the union of
    // the substrate baseline ``RESERVED_CONFIG_KEYS`` and any per-type
    // ``reservedConfigKeys`` declared by a registered registry entry.
    // The baseline constant stays untouched; composition happens at
    // call time so the registry's lifecycle (entries may register
    // late, after module load) is transparently respected.
    var ccrRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var ccrEntry = (ccrRegistry && account.type) ? ccrRegistry.get(account.type) : undefined;
    var ccrPerType = (ccrEntry && Array.isArray(ccrEntry.reservedConfigKeys)) ? ccrEntry.reservedConfigKeys : [];
    var effectiveReserved = {};
    for (var rk in RESERVED_CONFIG_KEYS) {
      if (Object.prototype.hasOwnProperty.call(RESERVED_CONFIG_KEYS, rk)) {
        effectiveReserved[rk] = true;
      }
    }
    for (var pi = 0; pi < ccrPerType.length; pi++) {
      effectiveReserved[ccrPerType[pi]] = true;
    }

    for (var k in account.config) {
      if (Object.prototype.hasOwnProperty.call(account.config, k)) {
        if (effectiveReserved[k]) continue;  // owned by a dedicated section or per-type form
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
    // M11 F1 L3: per-type form registry consult. When a registered
    // entry exposes ``renderCredentialsFields``, the substitute its
    // return for the inner secrets table HTML; otherwise fall through
    // to the generic kv-table render. The function's outer return
    // value remains the "inner content" the caller mounts inside the
    // existing ``.editor-section`` / ``.connector-account-secrets``
    // wrappers (`renderConnectorAccountEditor:268-273`), so the
    // wrapper-contract for byte-identical fallback DOM is preserved at
    // the caller layer. Triple-guard against an early-load race.
    var secRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var secActiveType = (account && account.type) || '';
    var secEntry = (secRegistry && secActiveType) ? secRegistry.get(secActiveType) : undefined;
    if (secEntry && typeof secEntry.renderCredentialsFields === 'function') {
      return secEntry.renderCredentialsFields(account);
    }

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
    // M10 F8 L11 HAT Fix #4: auto_relay_platform_replies is a
    // checkbox — captured separately by ``.checked`` so a re-render of
    // the editor (with the same toggle state) produces a byte-identical
    // snapshot.
    var autoRelayEl = container.querySelector('[data-field="auto_relay_platform_replies"]');
    staticData['auto_relay_platform_replies'] = autoRelayEl ? !!autoRelayEl.checked : true;

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

    // M10 F6 L7 HAT — semantic redesign: chip-lists are always
    // mounted. Empty lists are valid and meaningful (unrestricted on
    // that axis). M10 F8 L8 extends the snapshot to the 4 axes
    // (peers, channels, guilds, roles). Pairing state is NOT included
    // — the pairing button triggers an out-of-band POST that persists
    // immediately, independent of the editor's Save button (the
    // in-memory ``account.config.pairing`` mirror prevents data loss
    // when the operator then clicks Save with other dirty fields).
    var allowlist = collectAllowlistFromContainer(container);

    // M10 F7 L7: routing-rules state participates in the dirty-tracking
    // snapshot. The routing-section agent dropdowns are async-populated
    // by ``fetchAttachedAgents``; the initial snapshot must be
    // recaptured after that promise resolves (see wireRoutingRulesEvents)
    // so the populated options don't read as a dirty edit.
    var routing = collectRoutingFromContainer(container);

    var snapshotObj = {
      static: staticData,
      config: configRows,
      secrets: secretRows,
      allowlist: allowlist,
      routing: routing
    };

    // M11 F1 L4: per-type registry consult for typed-field snapshot.
    // The entry's optional ``snapshot(container)`` returns a
    // JSON-serializable view of the typed inputs (intent checkboxes,
    // presence dropdown, BOT_TOKEN value, etc.) so the dirty-tracker's
    // serialize-and-compare loop catches operator edits to inputs that
    // live OUTSIDE ``.editor-section .field-input`` / ``.field-select``.
    // Byte-stability contract: when no entry is registered (e.g.
    // ``'stub'``) OR the entry omits ``snapshot``, the snapshot object
    // MUST NOT carry a ``typedFields`` key at all — no
    // ``typedFields: undefined`` placeholder, no key-reordering. Triple
    // guard on the registry access for early-load safety.
    var snapRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var snapActiveType = container.querySelector('[data-field="type"]');
    var snapTypeValue = snapActiveType ? (snapActiveType.value || '') : '';
    var snapEntry = (snapRegistry && snapTypeValue) ? snapRegistry.get(snapTypeValue) : undefined;
    if (snapEntry && typeof snapEntry.snapshot === 'function') {
      var typed = snapEntry.snapshot(container);
      if (typed !== undefined) {
        snapshotObj.typedFields = typed;
      }
    }

    return JSON.stringify(snapshotObj);
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
      // M10 F8 L11 HAT Fix #4: the auto-relay toggle is a bare
      // ``<input type="checkbox">`` without the ``.field-input`` class
      // (it's neither a text input nor a select). Wire its change
      // event explicitly so dirty-tracking observes operator edits.
      var autoRelayToggle = container.querySelector('[data-field="auto_relay_platform_replies"]');
      if (autoRelayToggle) {
        autoRelayToggle.addEventListener('change', checkDirty);
      }
    }
    attachStaticListeners();

    // M11 F1 L4: per-type registry consult for typed-field event
    // wiring. The entry's optional ``wireEvents(container, checkDirty)``
    // attaches the per-input listeners for typed inputs that live
    // OUTSIDE the ``.editor-section .field-input`` / ``.field-select``
    // delegation pattern (raw checkboxes, ``<select>`` without
    // ``.field-select``, secret-style inputs not in the kv-table). The
    // substrate does no per-input-type dispatch — the entry owns its
    // own DOM coupling. Triple-guard for early-load safety; absent
    // hook → no-op (existing behavior preserved for unregistered
    // types and entries without typed inputs).
    var wireRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var wireActiveType = container.querySelector('[data-field="type"]');
    var wireTypeValue = wireActiveType ? (wireActiveType.value || '') : '';
    var wireEntry = (wireRegistry && wireTypeValue) ? wireRegistry.get(wireTypeValue) : undefined;
    if (wireEntry && typeof wireEntry.wireEvents === 'function') {
      // M11 F1 L5: pass ``account`` as a third arg so the entry's
      // invite-section helpers can key the application_id cache by
      // ``account.id``. L4's two-arg signature stays backward-compatible
      // (extra args are ignored).
      wireEntry.wireEvents(container, checkDirty, account);
    }

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
    // ── F7 L7: Routing rules wiring slots in alongside allowlist;
    // its agent-dropdown options are populated AFTER fetchAttachedAgents
    // resolves, so the routing section's own logic re-snapshots then.
    if (isEdit) {
      wirePairingEvents(container, account, callbacks);
      wirePairingCopyEvents(container);
      wireAllowlistEvents(container, account, checkDirty);
      wireRoutingRulesEvents(container, account, checkDirty);
      // M10 F6 L7 HAT: chip-list editors are mounted lazily by
      // wireAllowlistEvents AFTER the initial snapshot was captured.
      // The chip-list content (peers / channels from
      // account.config.allowlist) was therefore absent from the
      // baseline. Recapture so the just-mounted chips don't count as
      // a dirty edit.
      recaptureSnapshot();
      checkDirty();

      // Kick off the attached-agents fetch on mount. The list renders
      // a "Loading…" placeholder until this resolves. The same fetch's
      // ``.then`` populates the routing-section agent dropdowns and
      // re-snapshots (see fetchAttachedAgents).
      fetchAttachedAgents(container, account, checkDirty, recaptureSnapshot);
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
    var secrets = {};

    // M11 F1 L3: per-type registry's ``collect`` hook runs FIRST when
    // an entry exists for the current type; its returned
    // ``{config, secrets}`` seeds the substrate's payload. The
    // substrate's pairing / allowlist / routing / auto_relay merge
    // code below then OVERLAYS the substrate-known reserved keys onto
    // the registry's config, so the entry cannot accidentally write
    // them. When no entry exists, the generic DOM-scan path runs
    // unchanged — this is the regression contract for unregistered
    // types (``'stub'`` today; any future-type-without-UI tomorrow).
    var cfdRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var cfdEntry = (cfdRegistry && typeValue) ? cfdRegistry.get(typeValue) : undefined;
    var cfdCollected = (cfdEntry && typeof cfdEntry.collect === 'function')
      ? cfdEntry.collect(container, account, isEdit)
      : null;

    if (cfdCollected) {
      if (cfdCollected.config) {
        for (var rck in cfdCollected.config) {
          if (Object.prototype.hasOwnProperty.call(cfdCollected.config, rck)) {
            config[rck] = cfdCollected.config[rck];
          }
        }
      }
      if (cfdCollected.secrets) {
        for (var rsk in cfdCollected.secrets) {
          if (Object.prototype.hasOwnProperty.call(cfdCollected.secrets, rsk)) {
            secrets[rsk] = cfdCollected.secrets[rsk];
          }
        }
      }
    } else {
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
    // omitted. M10 F8 L8 adds the ``guilds`` and ``roles`` axes; both
    // are OPTIONAL on the backend validator but the editor always
    // emits them (empty list = unrestricted; uniform shape across all
    // 4 axes on the wire).
    if (isEdit) {
      var allowlistState = collectAllowlistFromContainer(container);
      if (allowlistState) {
        config.allowlist = {
          peers: allowlistState.peers,
          channels: allowlistState.channels,
          guilds: allowlistState.guilds,
          roles: allowlistState.roles
        };
      }
    }
    // M10 F7 L7: Routing rules merge. Only emit ``config.routing`` when
    // the operator has authored at least one complete rule OR set a
    // default agent — empty-rules + null-default means "no routing
    // configured" and the key is OMITTED so the L2 validator doesn't
    // reject an empty-but-present shape and L4's engine falls through
    // to first-eligible-alphabetical. Mirrors the allowlist precedent:
    // "absent = no constraint."
    if (isEdit) {
      var routingState = collectRoutingFromContainer(container);
      if (routingState && (routingState.rules.length > 0 || routingState.default !== null)) {
        config.routing = {
          rules: routingState.rules,
          default: routingState.default
        };
      }
    }

    // M10 F8 L11 HAT Fix #4: auto_relay_platform_replies merge.
    // The toggle is always present (create + edit modes both render
    // it). We always EMIT the bool so the validator sees an explicit
    // shape — there's no "absent" UI path: the operator either ticks
    // (True) or unticks (False) the checkbox. Default rendering is
    // checked / True for new accounts; existing accounts respect the
    // persisted value (absent → True at render time per
    // ``autoRelayConfigValue`` above).
    var autoRelayEl = container.querySelector('[data-field="auto_relay_platform_replies"]');
    if (autoRelayEl) {
      config.auto_relay_platform_replies = !!autoRelayEl.checked;
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
        renderTestConnectionBanner(container, report, accountId);
      })
      .catch(function (err) {
        // Network / 5xx — render as a synthetic error banner so the UI is
        // never blank after a click.
        renderTestConnectionBanner(container, {
          status: 'error',
          message: 'Network error: ' + (err && err.message ? err.message : String(err)),
          details: {}
        }, accountId);
      })
      .then(function () {
        testBtn.disabled = false;
      });
  }

  function renderTestConnectionBanner(container, report, accountId) {
    var escapeHtml = window.App.escapeHtml;
    var statusEl = container.querySelector('[data-testid="connector-test-status"]');
    var detailsWrap = container.querySelector('[data-testid="connector-test-details-wrap"]');
    var detailsEl = container.querySelector('[data-testid="connector-test-details"]');
    var ledEl = container.querySelector('[data-testid="connector-test-led"]');
    var messageEl = container.querySelector('[data-testid="connector-test-message"]');

    var status = (report && report.status) || 'error';
    var message = (report && report.message) || '';
    var details = (report && report.details) || {};

    // M11 F1 L5: if the probe surfaced a Discord ``application_id`` and
    // the Discord namespace is mounted, push the id into its cache so
    // the Invite section's URL renders. No-op when the namespace is
    // absent (e.g. ``'stub'`` tests / future types without an invite
    // helper).
    var applicationId = details && details.application_id;
    if (applicationId && accountId &&
        window.App && window.App.studio && window.App.studio.connectorFormDiscord &&
        typeof window.App.studio.connectorFormDiscord.setApplicationId === 'function') {
      window.App.studio.connectorFormDiscord.setApplicationId(accountId, applicationId);
    }

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
      // Hide the details panel on a clean "ok" status — green LED + message
      // is enough. Surface the details only when the operator needs to
      // debug (degraded / failed / error). Mirrors the M07 inspector
      // convention: status + one-sentence message at-a-glance; full
      // structured detail behind a panel that opens only when there's
      // something to debug.
      if (status === 'ok') {
        detailsEl.innerHTML = '';
        detailsWrap.hidden = true;
      } else {
        detailsEl.innerHTML = renderDetailsBlock(details);
        detailsWrap.hidden = false;
      }
    }
  }

  function renderDetailsBlock(details) {
    if (!details || typeof details !== 'object' || Object.keys(details).length === 0) {
      return '<div class="connector-test-details-empty"><em>(no additional details)</em></div>';
    }
    return _renderDetailsValue(details, 0);
  }

  // Render a single value (scalar / array / object) in the doctor-report
  // details panel. Recursive on nested objects so the M10 F8 L7 doctor's
  // ``details["checks"] = {token: {...}, application: {...}, ...}`` shape
  // renders per-check rows instead of one JSON-stringify dump.
  function _renderDetailsValue(value, depth) {
    var escapeHtml = window.App.escapeHtml;
    if (value === null || value === undefined) {
      return '<span class="connector-test-details-value"><em>(none)</em></span>';
    }
    if (typeof value === 'string') {
      // Secret-shaped values (start with '***') pass through unchanged —
      // do NOT re-mask, do NOT escape transform. Plain HTML escape only.
      return '<span class="connector-test-details-value">' + escapeHtml(value) + '</span>';
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return '<span class="connector-test-details-value">' + escapeHtml(String(value)) + '</span>';
    }
    if (Array.isArray(value)) {
      if (value.length === 0) {
        return '<span class="connector-test-details-value"><em>(none)</em></span>';
      }
      // Render arrays as comma-joined values for short scalar lists; fall
      // back to JSON for nested-array / array-of-object shapes.
      var allScalar = value.every(function (v) {
        return v === null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean';
      });
      if (allScalar) {
        return '<span class="connector-test-details-value">' +
               value.map(function (v) { return escapeHtml(String(v)); }).join(', ') +
               '</span>';
      }
      var json = '';
      try { json = JSON.stringify(value); } catch (_) { json = String(value); }
      return '<code class="font-mono connector-test-details-value">' + escapeHtml(json) + '</code>';
    }
    // Object (nested dict). Render as a nested <dl>. Cap depth defensively
    // (4 levels) so a circular or pathological payload never blows the
    // stack.
    if (depth >= 4) {
      var json2 = '';
      try { json2 = JSON.stringify(value); } catch (_) { json2 = String(value); }
      return '<code class="font-mono connector-test-details-value">' + escapeHtml(json2) + '</code>';
    }
    var keys = Object.keys(value);
    if (keys.length === 0) {
      return '<span class="connector-test-details-value"><em>(none)</em></span>';
    }
    var nestedClass = depth === 0
      ? 'connector-test-details-list kv-display'
      : 'connector-test-details-list connector-test-details-nested kv-display';
    var html = '<dl class="' + nestedClass + '">';
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      html += '<dt class="connector-test-details-key">' + escapeHtml(k) + '</dt>' +
              '<dd>' + _renderDetailsValue(value[k], depth + 1) + '</dd>';
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
    // M10 F6 L7 HAT — chip-lists are ALWAYS rendered. Empty list =
    // unrestricted on that axis. M10 F8 L8 — the editor surfaces 4
    // axes: peers, channels (cross-platform) + guilds, roles (Discord-
    // flavored; other platforms ignore absent/empty values). All 4
    // rows render on every account regardless of platform — the
    // pragmatic generic-UI choice; F10 can revisit per-platform
    // visibility if HAT surfaces operator confusion.
    //
    // M11 F1 L6 — Display labels + hint texts route through the
    // per-type vocabulary map. The persisted chip-list slot keys
    // (``data-allowlist-chiplist-slot="peers"``/``channels``/``guilds``/
    // ``roles``) stay at the substrate's literal field names; only the
    // rendered ``<label>`` text + ``<small>`` hint text vary per type.
    // ``hintTone === 'native'`` drops the "Discord-flavored" qualifier
    // on the groups + roles rows (redundant noise when the label
    // already says "Servers / Roles").
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var vocab = _vocabForAccount(account);
    var nativeTone = vocab.hintTone === 'native';

    var html = '';
    html += '<div class="editor-section connector-allowlist-section">';
    html += '<div class="section-title">Account-scope allowlist</div>';

    html += '<div class="connector-allowlist-lists" ' +
            'data-testid="connector-allowlist-lists">';
    html += '<div class="connector-account-acl-fieldrow">';
    html += '<label class="connector-account-acl-fieldlabel">' +
            escapeHtml(_capitalize(vocab.peers)) + '</label>';
    html += '<div data-allowlist-chiplist-slot="peers"></div>';
    html += '<small class="form-hint" ' +
            'data-testid="connector-allowlist-peers-hint">' +
            'Empty list = no ' + escapeHtml(vocab.peer) + ' restriction.' +
            '</small>';
    html += '</div>';
    html += '<div class="connector-account-acl-fieldrow">';
    html += '<label class="connector-account-acl-fieldlabel">' +
            escapeHtml(_capitalize(vocab.channels)) + '</label>';
    html += '<div data-allowlist-chiplist-slot="channels"></div>';
    html += '<small class="form-hint" ' +
            'data-testid="connector-allowlist-channels-hint">' +
            'Empty list = no ' + escapeHtml(vocab.channel) + ' restriction.' +
            '</small>';
    html += '</div>';
    html += '<div class="connector-account-acl-fieldrow">';
    html += '<label class="connector-account-acl-fieldlabel">' +
            escapeHtml(_capitalize(vocab.groups)) + '</label>';
    html += '<div data-allowlist-chiplist-slot="guilds"></div>';
    html += '<small class="form-hint" ' +
            'data-testid="connector-allowlist-guilds-hint">' +
            'Empty list = no ' + escapeHtml(vocab.group) + ' restriction.' +
            (nativeTone ? '' : ' Discord-flavored; ignored by other platforms.') +
            '</small>';
    html += '</div>';
    html += '<div class="connector-account-acl-fieldrow">';
    html += '<label class="connector-account-acl-fieldlabel">' +
            escapeHtml(_capitalize(vocab.roles)) + '</label>';
    html += '<div data-allowlist-chiplist-slot="roles"></div>';
    html += '<small class="form-hint" ' +
            'data-testid="connector-allowlist-roles-hint">' +
            'Empty list = no ' + escapeHtml(vocab.role) + ' restriction. ' +
            'Any-of overlap.' +
            (nativeTone ? '' : ' Discord-flavored.') +
            '</small>';
    html += '</div>';
    html += '</div>';

    html += '</div>';
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
    // M10 F8 L8 — per-axis placeholder + aria-label. Keep the
    // singular noun matching the kind ("peer", "channel", "guild",
    // "role") so screen-readers announce the right field.
    var _AXIS_NOUN = {
      peers: 'peer',
      channels: 'channel',
      guilds: 'guild',
      roles: 'role'
    };
    var noun = _AXIS_NOUN[kind] || kind;
    input.placeholder = 'Add ' + noun + '…';
    input.setAttribute('aria-label', 'Add ' + noun);
    wrapper.appendChild(input);
    return wrapper;
  }

  // ── Routing Rules section (M10 F7 L7) ──────────────────────────────
  //
  // Operator-authored, ordered list of routing rules and a per-account
  // default agent. The L2 Pydantic validator enforces the shape; this
  // editor emits the validated shape on save. Section structure mirrors
  // ``renderAllowlistSection`` (sibling); table structure mirrors
  // ``renderConfigKvTable`` (kv-row precedent at :463-491).
  //
  // Cycle-1 design-language audit verdict (F6 debrief rec #1, recorded
  // in the leg artifact §9): ZERO new bespoke selectors beyond the F6
  // naming convention. Scope/agent/default dropdowns use the canonical
  // 4-class set (field-input + field-select + admin-pf-input +
  // admin-pf-select); match input uses field-input only; move/remove
  // buttons are bare buttons mirroring config-remove-row-btn at :488.

  var _VALID_ROUTING_SCOPES = ['channel', 'thread', 'dm', 'peer'];

  function _collectRoutingRows(account) {
    var routing = (account && account.config && account.config.routing) || null;
    if (!routing || !Array.isArray(routing.rules)) return [];
    var out = [];
    for (var i = 0; i < routing.rules.length; i++) {
      var r = routing.rules[i] || {};
      // M10 F7 L9 HAT2: ``match`` is now a list of strings (operator-
      // entered chips). Tolerate the old single-string shape during
      // in-memory upgrades — at write time the L2 validator enforces
      // list-form.
      var matchList = [];
      if (Array.isArray(r.match)) {
        for (var m = 0; m < r.match.length; m++) {
          var mv = String(r.match[m] || '').trim();
          if (mv) matchList.push(mv);
        }
      } else if (typeof r.match === 'string' && r.match) {
        matchList.push(r.match);
      }
      out.push({
        scope: String(r.scope || ''),
        match: matchList,
        agent: String(r.agent || '')
      });
    }
    return out;
  }

  function _renderRoutingScopeOptions(currentScope, vocab) {
    // M11 F1 L6 — ``<option value>`` STAYS at the substrate's literal
    // scope value (the persistence vocabulary is unchanged). Only the
    // option's textContent is substituted per the per-type vocabulary
    // map. Today only ``peer`` and ``channel`` have vocabulary
    // entries; ``thread`` and ``dm`` render their literal values
    // unchanged (no Discord-specific labels). ``vocab`` defaults to
    // the inline generic baseline so existing callers/legacy paths
    // see byte-identical pre-L6 output.
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var v = vocab || _DEFAULT_VOCAB_INLINE;
    var html = '<option value="" disabled' +
               (currentScope ? '' : ' selected') + '>Select scope</option>';
    for (var i = 0; i < _VALID_ROUTING_SCOPES.length; i++) {
      var s = _VALID_ROUTING_SCOPES[i];
      var sel = (s === currentScope) ? ' selected' : '';
      var label = s;
      if (s === 'peer') {
        label = v.peer;
      } else if (s === 'channel') {
        label = v.channel;
      }
      html += '<option value="' + escapeAttr(s) + '"' + sel + '>' +
              escapeHtml(label) + '</option>';
    }
    return html;
  }

  function _renderRoutingAgentOptions(currentAgent) {
    // Agent options are async-populated via populateRoutingAgentDropdowns
    // once fetchAttachedAgents resolves. The initial render emits the
    // placeholder option plus — if a value was persisted — a single
    // ``<option selected>`` that holds the value so a save-without-fetch
    // round-trip still preserves the operator's prior choice. The
    // post-fetch populator replaces the entire option list, restoring
    // the selection by value if it's still in the attached set.
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var html = '<option value="">Select agent</option>';
    if (currentAgent) {
      html += '<option value="' + escapeAttr(currentAgent) + '" selected>' +
              escapeHtml(currentAgent) + '</option>';
    }
    return html;
  }

  function _renderRoutingRow(row, idx, vocab) {
    // M11 F1 L6 — ``vocab`` threaded through to ``_renderRoutingScopeOptions``
    // so the scope dropdown's option textContent reflects the per-type
    // vocabulary (e.g. Discord shows "user" / "channel" instead of
    // "peer" / "channel"). The ``<option value>`` stays at the literal
    // scope value; only the visible label varies.
    var escapeAttr = window.App.escapeAttr;
    var html = '';
    // M10 F7 L9 HAT2: rule rows gain a leading drag-handle cell; chevron
    // move buttons removed in favour of native HTML5 drag-and-drop
    // (wired in ``wireRoutingRulesEvents``). The row itself becomes the
    // drop target; the handle is the drag source.
    html += '<tr class="connector-routing-row" data-routing-rule data-routing-rule-idx="' + idx + '">';
    html += '<td class="connector-routing-drag-cell">' +
            '<span class="connector-routing-drag-handle" draggable="true" ' +
            'role="button" aria-label="Drag to reorder rule" title="Drag to reorder" ' +
            'data-routing-drag-handle data-row="' + idx + '">' +
            window.App.icon('grip-vertical') +
            '</span></td>';
    html += '<td><select class="field-input field-select admin-pf-input admin-pf-select" ' +
            'data-routing-scope data-row="' + idx + '">' +
            _renderRoutingScopeOptions(row.scope, vocab) +
            '</select></td>';
    // M10 F7 L9 HAT2: ``match`` is a chip-list (one or more values; the
    // rule fires if ANY value matches the envelope's corresponding
    // field). Cell mounts a chip-list-editor wrapper; the wireRouting
    // pass wires it via ``adminFormHelpers.wireChipListEditor`` for the
    // same operator UX the F6 allowlist editor uses.
    var matchValues = Array.isArray(row.match) ? row.match : [];
    html += '<td class="connector-routing-match-cell">';
    html += '<div class="chip-list-editor connector-routing-match-chiplist" ' +
            'data-routing-match data-row="' + idx + '">';
    for (var ci = 0; ci < matchValues.length; ci++) {
      var v = String(matchValues[ci]);
      html += '<span class="chip">' + window.App.escapeHtml(v) +
              '<button type="button" class="chip-remove" aria-label="Remove ' +
              escapeAttr(v) + '">×</button></span>';
    }
    html += '<input type="text" class="chip-list-input" ' +
            'placeholder="Add match value…" aria-label="Add match value" />';
    html += '</div></td>';
    html += '<td><select class="field-input field-select admin-pf-input admin-pf-select" ' +
            'data-routing-agent data-row="' + idx + '">' +
            _renderRoutingAgentOptions(row.agent) +
            '</select></td>';
    html += '<td>';
    html += '<button type="button" class="connector-routing-remove-row-btn" ' +
            'data-row="' + idx + '" aria-label="Remove rule" title="Remove rule">' +
            window.App.icon('trash') + '</button>';
    html += '</td>';
    html += '</tr>';
    return html;
  }

  function renderRoutingRulesSection(account) {
    var escapeAttr = window.App.escapeAttr;
    var rows = _collectRoutingRows(account);
    var routing = (account && account.config && account.config.routing) || null;
    var defaultAgent = (routing && typeof routing.default === 'string') ? routing.default : '';
    var headHiddenClass = rows.length === 0 ? ' is-hidden' : '';
    // M11 F1 L6 — vocabulary threaded into ``_renderRoutingRow`` for
    // the scope-dropdown textContent substitution.
    var vocab = _vocabForAccount(account);

    var html = '';
    html += '<div class="editor-section connector-routing-section">';
    html += '<div class="section-title">Routing rules</div>';

    // M10 F7 L9 HAT2: default-agent row moves to the TOP of the section
    // (operator visual-hierarchy feedback during HAT). The rules table +
    // "Add rule" button follow. The form-hint stays directly under the
    // default-agent dropdown so the "fall back to first-eligible"
    // micro-copy explains both empty-default AND empty-rules states.
    html += '<div class="field-row admin-pf-row connector-routing-default-row">';
    html += '<label for="connector-routing-default">Default agent</label>';
    html += '<select class="field-input field-select admin-pf-input admin-pf-select" ' +
            'id="connector-routing-default" data-routing-default ' +
            'data-testid="connector-routing-default">';
    html += '<option value="">None</option>';
    if (defaultAgent) {
      html += '<option value="' + escapeAttr(defaultAgent) + '" selected>' +
              window.App.escapeHtml(defaultAgent) + '</option>';
    }
    html += '</select>';
    html += '</div>';
    html += '<div class="field-row admin-pf-row">';
    html += '<label></label>';
    html += '<small class="form-hint" data-testid="connector-routing-default-hint">' +
            'Fall back to first-eligible-alphabetical agent.' +
            '</small>';
    html += '</div>';

    html += '<table class="connector-routing-table" data-testid="connector-routing-table">';
    // M10 F7 L9 HAT2: leading drag-handle column (no header label).
    // Trailing actions column now holds only the remove button.
    html += '<thead class="connector-routing-thead' + headHiddenClass + '">' +
            '<tr><th aria-label="Reorder"></th>' +
            '<th>Scope</th><th>Match</th><th>Agent</th>' +
            '<th aria-label="Actions"></th></tr></thead>';
    html += '<tbody data-testid="connector-routing-tbody">';
    for (var i = 0; i < rows.length; i++) {
      html += _renderRoutingRow(rows[i], i, vocab);
    }
    html += '</tbody></table>';

    html += '<button type="button" class="btn-outlined-primary kv-add-row-btn ' +
            'connector-routing-add-row-btn" ' +
            'data-testid="connector-routing-add-row-btn">+ Add rule</button>';

    html += '</div>'; // .editor-section
    return html;
  }

  // Populate every routing-section agent dropdown (rule rows + default
  // agent) with the live attached-agent set. Called by
  // ``fetchAttachedAgents``'s ``.then`` after ``renderAttachedAgentsList``
  // so both surfaces reflect the same response. Preserves the prior
  // selection by value if the agent is still attached; otherwise the
  // dropdown drops to the placeholder (and the operator must re-select).
  function populateRoutingAgentDropdowns(container, rows) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var names = [];
    for (var i = 0; i < (rows || []).length; i++) {
      var n = String((rows[i] || {}).name || '');
      if (n) names.push(n);
    }
    // Stable display order. Sorting here is for the dropdown — the
    // routing engine (L4) does its own first-eligible-alphabetical
    // sort downstream; this is purely a UI nicety.
    names.sort();

    function _buildOptions(currentValue, includeNone) {
      var html = '';
      if (includeNone) {
        html += '<option value=""' + (currentValue === '' ? ' selected' : '') + '>None</option>';
      } else {
        html += '<option value=""' + (currentValue === '' ? ' selected' : '') + '>Select agent</option>';
      }
      var seen = false;
      for (var j = 0; j < names.length; j++) {
        if (names[j] === currentValue) seen = true;
        html += '<option value="' + escapeAttr(names[j]) + '"' +
                (names[j] === currentValue ? ' selected' : '') + '>' +
                escapeHtml(names[j]) + '</option>';
      }
      // Stale-selection preservation: if the persisted value isn't in
      // the attached set, keep it as a disabled option so the operator
      // sees their original choice (and that it's no longer valid).
      if (currentValue && !seen) {
        html += '<option value="' + escapeAttr(currentValue) + '" selected disabled>' +
                escapeHtml(currentValue) + ' (not attached)</option>';
      }
      return html;
    }

    var ruleAgentSelects = container.querySelectorAll('[data-routing-agent]');
    for (var k = 0; k < ruleAgentSelects.length; k++) {
      var sel = ruleAgentSelects[k];
      sel.innerHTML = _buildOptions(sel.value || '', false);
    }
    var defaultSelect = container.querySelector('[data-routing-default]');
    if (defaultSelect) {
      defaultSelect.innerHTML = _buildOptions(defaultSelect.value || '', true);
    }
  }

  function wireRoutingRulesEvents(container, account, checkDirty) {
    var section = container.querySelector('.connector-routing-section');
    if (!section) return;
    var tbody = section.querySelector('tbody[data-testid="connector-routing-tbody"]');
    var addBtn = section.querySelector('.connector-routing-add-row-btn');
    var helpers = window.App.adminFormHelpers;

    // Track the next-row index for newly-added rows. data-row attributes
    // are presentation-only (the collector reads DOM order), but keeping
    // them stable helps when debugging via the inspector.
    var nextRoutingRowIdx = tbody ? tbody.querySelectorAll('tr.connector-routing-row').length : 0;

    function _updateRoutingHeadVisibility() {
      var thead = section.querySelector('.connector-routing-thead');
      if (!thead) return;
      var n = section.querySelectorAll('tbody tr.connector-routing-row').length;
      thead.classList.toggle('is-hidden', n === 0);
    }

    // M10 F7 L9 HAT2: wire the chip-list editor for a row's match cell.
    // ``adminFormHelpers.wireChipListEditor`` provides the same operator
    // UX as the F6 allowlist editor (Enter/Tab/comma commit, click-×
    // remove, Backspace-on-empty delete-last). The onChange callback
    // re-triggers dirty-tracking on every chip add/remove.
    function _wireRoutingMatchChiplist(rowEl) {
      if (!helpers || !helpers.wireChipListEditor) return;
      var chiplist = rowEl.querySelector('.connector-routing-match-chiplist');
      if (!chiplist) return;
      helpers.wireChipListEditor(chiplist, { onChange: checkDirty });
    }

    // ── HTML5 native drag-and-drop reordering (M10 F7 L9 HAT2) ──────
    //
    // The handle is the drag source (draggable=true); the row is the
    // drop target. Drop semantics: dropping ON a target row inserts the
    // dragged row BEFORE the target. Dropping past the last row (i.e.
    // on the tbody itself, not a row) appends to the end. We track the
    // dragged row via a closure variable; dataTransfer's `text/plain`
    // is set defensively (some browsers require a non-empty payload to
    // initiate a drag).
    //
    // Accessibility / keyboard fallback: NOT shipped in this HAT cycle.
    // The leg spec gave a "pick pragmatically" out for keyboard
    // reordering. Native drag-and-drop covers mouse; keyboard reorder
    // can be re-added in a future HAT iteration if the operator flags
    // it. The Add-rule flow + per-row Remove still work via keyboard.
    var draggedRow = null;

    function _wireRoutingDragHandle(rowEl) {
      var handle = rowEl.querySelector('[data-routing-drag-handle]');
      if (!handle) return;
      handle.addEventListener('dragstart', function (e) {
        draggedRow = rowEl;
        rowEl.classList.add('is-dragging');
        if (e.dataTransfer) {
          // Setting text/plain to a non-empty string is required by
          // some browsers (Firefox) to actually start the drag.
          e.dataTransfer.setData('text/plain', rowEl.dataset.routingRuleIdx || '');
          e.dataTransfer.effectAllowed = 'move';
        }
      });
      handle.addEventListener('dragend', function () {
        if (draggedRow) draggedRow.classList.remove('is-dragging');
        draggedRow = null;
      });
    }

    function _wireRoutingDropTarget(rowEl) {
      rowEl.addEventListener('dragover', function (e) {
        if (!draggedRow || draggedRow === rowEl) return;
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      });
      rowEl.addEventListener('drop', function (e) {
        if (!draggedRow || draggedRow === rowEl) return;
        e.preventDefault();
        // Insert dragged BEFORE the target if dragged came from below,
        // AFTER the target if dragged came from above. Compare DOM
        // positions to pick the side.
        var parent = rowEl.parentNode;
        if (!parent) return;
        var rows = Array.prototype.slice.call(
          parent.querySelectorAll('tr.connector-routing-row')
        );
        var draggedIdx = rows.indexOf(draggedRow);
        var targetIdx = rows.indexOf(rowEl);
        if (draggedIdx === -1 || targetIdx === -1) return;
        if (draggedIdx < targetIdx) {
          // Dragged came from above target → insert after.
          parent.insertBefore(draggedRow, rowEl.nextSibling);
        } else {
          // Dragged came from below target → insert before.
          parent.insertBefore(draggedRow, rowEl);
        }
        checkDirty();
      });
    }

    function _wireRoutingRow(rowEl) {
      _wireRoutingMatchChiplist(rowEl);
      _wireRoutingDragHandle(rowEl);
      _wireRoutingDropTarget(rowEl);
    }

    // Initial wiring for pre-rendered rows.
    if (tbody) {
      var initialRows = tbody.querySelectorAll('tr.connector-routing-row');
      for (var ir = 0; ir < initialRows.length; ir++) {
        _wireRoutingRow(initialRows[ir]);
      }
    }

    // Add rule.
    if (addBtn) {
      addBtn.addEventListener('click', function () {
        if (!tbody) return;
        var idx = nextRoutingRowIdx++;
        var tmp = document.createElement('tbody');
        // M11 F1 L6 — pass the per-type vocabulary so the new row's
        // scope dropdown renders the same substituted labels as the
        // pre-rendered rows above.
        var addVocab = _vocabForAccount(account);
        tmp.innerHTML = _renderRoutingRow({ scope: '', match: [], agent: '' }, idx, addVocab);
        var newTr = tmp.querySelector('tr.connector-routing-row');
        if (!newTr) return;
        // Repopulate the new row's agent dropdown from the live
        // attached-agents response (if it has resolved). The populator
        // tolerates an empty rows list (places only the placeholder
        // option), so it's safe to call even if the fetch is in-flight.
        tbody.appendChild(newTr);
        // Wire chip-list editor + drag-handle on the new row.
        _wireRoutingRow(newTr);
        // Re-run the populator with whatever agents are currently in
        // the existing dropdowns. We synthesise the names list by
        // reading options off ANY pre-existing dropdown so the
        // newly-added row inherits the same set without re-fetching.
        var anyExisting = section.querySelector('[data-routing-agent]:not([data-row="' + idx + '"])') ||
                          section.querySelector('[data-routing-default]');
        if (anyExisting) {
          var seenNames = [];
          for (var oi = 0; oi < anyExisting.options.length; oi++) {
            var optV = anyExisting.options[oi].value;
            if (optV) seenNames.push({ name: optV });
          }
          populateRoutingAgentDropdowns(section, seenNames);
        }
        _updateRoutingHeadVisibility();
        checkDirty();
        var newScope = newTr.querySelector('[data-routing-scope]');
        if (newScope) newScope.focus();
      });
    }

    // Delegated click handler: only delete (move-up / move-down replaced
    // by drag-handle reordering).
    if (tbody) {
      tbody.addEventListener('click', function (e) {
        var target = e.target;
        if (!target) return;
        var rowEl = target.closest && target.closest('tr.connector-routing-row');
        if (!rowEl) return;
        if (target.closest('.connector-routing-remove-row-btn')) {
          rowEl.parentNode.removeChild(rowEl);
          _updateRoutingHeadVisibility();
          checkDirty();
          return;
        }
      });
      // Delegated change for scope/agent. (match dirty-tracking is wired
      // per-row via the chip-list editor's onChange.)
      tbody.addEventListener('change', function (e) {
        var t = e.target;
        if (!t) return;
        if (t.hasAttribute && (t.hasAttribute('data-routing-scope') ||
                               t.hasAttribute('data-routing-agent'))) {
          checkDirty();
        }
      });
    }

    // Default-agent change.
    var defaultSel = section.querySelector('[data-routing-default]');
    if (defaultSel) {
      defaultSel.addEventListener('change', checkDirty);
    }

    void account;
  }

  function collectRoutingFromContainer(container) {
    var section = container.querySelector('.connector-routing-section');
    if (!section) return null;

    var rules = [];
    var ruleRows = section.querySelectorAll('tr.connector-routing-row');
    for (var i = 0; i < ruleRows.length; i++) {
      var row = ruleRows[i];
      var scopeEl = row.querySelector('[data-routing-scope]');
      var matchEl = row.querySelector('[data-routing-match]');
      var agentEl = row.querySelector('[data-routing-agent]');
      var scope = scopeEl ? scopeEl.value : '';
      var agent = agentEl ? agentEl.value : '';
      // M10 F7 L9 HAT2: match is a chip-list. Read the committed chips
      // (live input value is ignored — operator must commit via
      // Enter/Tab/comma for a value to count). Reads chips in DOM
      // order; the wireChipListEditor helper guarantees only committed
      // chip elements carry values.
      var matchValues = [];
      if (matchEl) {
        var chips = matchEl.querySelectorAll('.chip');
        for (var c = 0; c < chips.length; c++) {
          var chip = chips[c];
          var label = '';
          for (var n = 0; n < chip.childNodes.length; n++) {
            var node = chip.childNodes[n];
            if (node.nodeType === 3) {
              label += node.nodeValue;
            }
          }
          label = (label || '').trim();
          if (label) matchValues.push(label);
        }
      }
      // Skip incomplete rule rows (operator added a row but didn't fill
      // every required cell). Per the L2 validator, every field is
      // required; partial rows (no scope / no chips / no agent) are
      // stubs and treated as "not saved".
      if (!scope || matchValues.length === 0 || !agent) continue;
      rules.push({ scope: scope, match: matchValues, agent: agent });
    }

    var defaultSel = section.querySelector('[data-routing-default]');
    var defaultAgent = defaultSel ? defaultSel.value : '';
    if (defaultAgent === '') defaultAgent = null;

    return { rules: rules, default: defaultAgent };
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

  function renderAttachedAgentsList(container, rows, account) {
    // M11 F1 L6 — table headers consult the per-type vocabulary so a
    // Discord-type account renders "Users" / "Channels" instead of
    // the substrate's neutral "Peers" / "Channels". The per-row
    // ``_renderAxis`` calls do not vary by type — the empty-list
    // copy ("DMs only" / "none") remains shared across types.
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var vocab = _vocabForAccount(account);
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
            '<th>' + escapeHtml(_capitalize(vocab.peers)) + '</th>' +
            '<th>' + escapeHtml(_capitalize(vocab.channels)) + '</th>' +
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

  function fetchAttachedAgents(container, account, checkDirty, recaptureSnapshot) {
    // M11 F1 L6 — accept the full ``account`` object (not just the
    // id) so ``renderAttachedAgentsList`` can consult the per-type
    // vocabulary for the table-header text. ``account.id`` drives the
    // fetch URL; ``account.type`` drives the vocabulary lookup.
    var accountId = account && account.id;
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
        renderAttachedAgentsList(container, rows, account);
        // M10 F7 L7: populate routing-section agent dropdowns (rule
        // rows + default-agent) once the attached-agents list is
        // known. Re-snapshot AFTER population so the populated form
        // is the dirty-tracking baseline (otherwise the operator's
        // first edit would compare against an empty-options
        // baseline that no longer exists in the DOM).
        populateRoutingAgentDropdowns(container, rows);
        if (typeof recaptureSnapshot === 'function') {
          recaptureSnapshot();
        }
        if (typeof checkDirty === 'function') {
          checkDirty();
        }
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
    // M10 F6 L7 HAT — chip-lists are always mounted. Empty lists are
    // valid and mean "unrestricted on this axis." M10 F8 L8 extends
    // the mount to the 4 axes (peers, channels, guilds, roles).
    //
    // Mount the chip-list editors into the slot divs. Pre-existing
    // entries come from account.config.allowlist; if absent, empty
    // chip-lists are mounted so the operator can start typing
    // immediately.
    var allowlist = (account && account.config && account.config.allowlist) || null;
    var peersInit = (allowlist && Array.isArray(allowlist.peers)) ? allowlist.peers : [];
    var channelsInit = (allowlist && Array.isArray(allowlist.channels)) ? allowlist.channels : [];
    var guildsInit = (allowlist && Array.isArray(allowlist.guilds)) ? allowlist.guilds : [];
    var rolesInit = (allowlist && Array.isArray(allowlist.roles)) ? allowlist.roles : [];
    var peersSlot = container.querySelector('[data-allowlist-chiplist-slot="peers"]');
    var channelsSlot = container.querySelector('[data-allowlist-chiplist-slot="channels"]');
    var guildsSlot = container.querySelector('[data-allowlist-chiplist-slot="guilds"]');
    var rolesSlot = container.querySelector('[data-allowlist-chiplist-slot="roles"]');
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
    _mountChipList(guildsSlot, 'guilds', guildsInit);
    _mountChipList(rolesSlot, 'roles', rolesInit);
  }

  function collectAllowlistFromContainer(container) {
    // M10 F6 L7 HAT — Returns ``{ peers, channels, guilds, roles }``
    // (or null if the slots are missing — defensive). All 4 lists are
    // ALWAYS emitted; empty list = unrestricted on that axis. Chips
    // are read in DOM order; the wireChipListEditor helper guarantees
    // only committed chip elements (not the live input) carry values.
    // Whitespace-only entries cannot reach a chip (the helper trims
    // before committing). M10 F8 L8 added the guilds + roles axes.
    var peersSlot = container.querySelector('[data-allowlist-chiplist-slot="peers"]');
    var channelsSlot = container.querySelector('[data-allowlist-chiplist-slot="channels"]');
    var guildsSlot = container.querySelector('[data-allowlist-chiplist-slot="guilds"]');
    var rolesSlot = container.querySelector('[data-allowlist-chiplist-slot="roles"]');
    if (!peersSlot && !channelsSlot && !guildsSlot && !rolesSlot) return null;
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
      channels: _readChiplist(channelsSlot),
      guilds: _readChiplist(guildsSlot),
      roles: _readChiplist(rolesSlot)
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
  // M11 F1 L4: expose the generic config kv-table renderer on the
  // studio namespace so per-type registry entries (e.g. the Discord
  // entry's "Advanced (kv-table)" disclosure) can mount it inside
  // their own typed-field markup. The function body is UNCHANGED —
  // only its accessibility extends. Removing this exposure would
  // break L4's Advanced disclosure render.
  window.App.studio.renderConfigKvTable = renderConfigKvTable;
  // M10 F7 L9 HAT: expose PANEL_IDS mirroring agent-editor's
  // AGENT_PANEL_IDS for parity (no current consumer, but anchors the
  // contract for future studio.js URL routing).
  window.App.studio.CONNECTOR_ACCOUNT_PANEL_IDS = PANEL_IDS;
})();
