// App.studio.renderConnectorEditor — Connector Account editor (M10 F2 L6).
//
// Structurally mirrors mcp-server-editor.js minus MCP-specific concerns
// (no transport-specific config, no OAuth, no tools list, no sandbox).
//
// Edit-mode tabbed layout (M10 F7 L9 HAT; F5 L3 moved Runtime Config
// across tabs; F5 L6 HAT round-4 renamed sections + reordered the
// Access and Routing tab to Discord → Access → Routing → Session and
// added friendly descriptions under each terse header):
//
//   General tab — WHAT the bot is:
//     Connection — name, type, config kv (with substrate-managed
//                  Test Connection footer-row + registry-mediated
//                  Invite block per F5 L2 MCP-parity refactor
//                  mirroring mcp-server-editor.js mcp-test-row
//                  placement)
//     Credentials — secrets kv with __MASKED__ round-trip
//     Pairing — operator-generated pairing code
//     Attached Agents — read-only summary
//     Danger Zone — delete button
//
//   F5 L6 HAT round-8: the editable "System Prompt Directive" section
//   was REMOVED from the General tab (criterion #14 reverted). The
//   read-only effective-directive surface now lives under the Auto-reply
//   toggle in the Session section (Access and Routing tab) — see
//   ``renderEffectiveDirectiveCodeblock`` below.
//
//   Access and Routing tab — HOW it behaves at runtime (F5 L6 HAT R4
//   ordering: Discord first, then Access → Routing → Session):
//     Discord — registry-mediated runtime-config block (was
//               "Runtime Config"; mounts the typed Intents/Servers/
//               Presence/Advanced block per F5 L3)
//     Access — account-scope peer/channel/server/role allowlist
//              (was "Account-scope allowlist")
//     Routing — operator-authored routing rules + default agent
//               (was "Routing rules")
//     Session — idle_timeout_seconds, session_continuation_seconds,
//               Auto-reply toggle (was "Lifecycle"), and the
//               read-only effective-directive codeblock that reactively
//               mirrors the Auto-reply toggle state (F5 L6 HAT round-8).
//
// Create mode renders flat (only Connection + Credentials + Lifecycle
// render there — not enough sections to justify the tab split). The
// Discord typed runtime-config block renders INSIDE the Connection
// section in create-mode (per F5 L3 — flat layout has no tabs to
// mount it on; the registry's ``renderConnectionFields(account,
// isCreate=true)`` delegates to the same shared body used by
// ``renderRuntimeConfigFields`` in edit-mode for single-source-of-truth
// markup).
//
// Per-key __MASKED__ round-trip mirrors MCP exactly: each secret row
// captures `_originalMasked` via the data-original-masked attribute at
// mount time. At save time, if value === _originalMasked, the payload
// emits '__MASKED__' for that key and the backend preserves the stored
// secret (api.py:2192-2207 honors the sentinel per-key).
//
// "Create & Test" combined-action: the create-mode primary button does
// POST /api/connectors → on 201 POST /test/connect → renders
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
//   Tab "General"            — Connection (with Test Connection
//                              footer-row + Invite block folded in
//                              per F5 L2 MCP-parity), Credentials,
//                              Pairing, Attached agents, Danger zone.
//   Tab "Access and Routing" — Discord, Access, Routing, Session
//                               (F5 L6 HAT R4 reorg + renames).
// Create mode renders flat (only the Connection + Credentials + Lifecycle
// sections render there — not enough sections to justify the tab split).
// All tab panel contents mount SYNCHRONOUSLY at editor-load time so the
// L7 dirty-tracker / snapshot logic + selectors continue to resolve
// against any section regardless of which tab is currently active.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // M11 F2 L4: ``MASKED_SENTINEL`` is hoisted to
  // ``window.App.studio.MASKED_SENTINEL`` (set in
  // ``connector-form-registry.js`` at module-load time — the studio's
  // earliest-loading module). The local declaration was deleted in
  // L4 to remove the duplication between this file and
  // ``connector-form-discord.js``. Use sites read the shared
  // constant directly: ``window.App.studio.MASKED_SENTINEL``.

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

  function renderConnectorEditor(container, account, types, callbacks, forceCreate) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    // M11 F1 L7 HAT: ``forceCreate`` lets the create-mode type-change
    // re-render path pass an account-shaped stub (carrying the freshly
    // picked ``type`` + any operator-entered ``name``) while still
    // rendering as create mode. The five-arg signature is additive —
    // existing callers (studio.js shell, edit-mode Cancel re-render at
    // L1021) pass four args and behave unchanged.
    var isCreate = forceCreate ? true : !account;
    // In create mode, the header title stays "New Connector" regardless
    // of any operator-entered name (the name lives in the form input).
    // The stub passed at type-change time may carry a ``name`` field so
    // the input value can be restored; the title is a separate concern.
    var name = isCreate ? 'New Connector' : (account.name || '');
    var type = isCreate ? ((account && account.type) || '') : (account.type || '');
    // M10 F7 L9 HAT: tabbed-layout default. Mirrors agent-editor.js
    // (initialTab callback param, default to 'general'). The studio
    // shell does not yet route _activeTab into the connector
    // editor, but the hook is in place for future wiring.
    var initialTab = callbacks.initialTab || 'general';

    // ── Header ─────────────────────────────────────────────────────────
    var html = '';
    // M11 F2 L4: ``data-account-id`` is set ONLY in edit mode. Create
    // mode (and the F1 L7 stub re-mount path that picks Discord) keeps
    // the attribute absent because ``account.id`` doesn't exist yet.
    // The attribute is the new authoritative source for
    // ``connector-form-discord.js:_resolveAccountFromContainer`` —
    // replaces the prior ``window.location.hash`` parse.
    var editorRootAttrs = '';
    if (!isCreate && account && account.id) {
      editorRootAttrs = ' data-account-id="' + escapeAttr(String(account.id)) + '"';
    }
    html += '<div class="connector-editor"' + editorRootAttrs + '>';
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
    var saveTestId = isCreate ? 'create-and-test-connector-btn' : 'save-connector-btn';
    var saveLabel = isCreate ? 'Create & Test' : 'Save';
    html += '<div class="form-actions">';
    html += '<button type="button" class="btn-outlined-primary back-btn" data-testid="back-connector-btn" aria-label="Back to connectors list">' + window.App.icon('arrow-left') + ' Back</button>';
    html += '<button type="button" class="btn-outlined-primary cancel-btn" data-testid="cancel-connector-btn" disabled>Cancel</button>';
    html += '<button type="button" class="btn-filled-primary save-btn" data-testid="' + saveTestId + '" disabled>' + escapeHtml(saveLabel) + '</button>';
    html += '<span class="editor-error" data-testid="connector-editor-error"></span>';
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
    // F5 L2: edit-mode hosts the Test Connection footer-row + the
    // registry-mediated Invite block INSIDE this section, mirroring
    // mcp-server-editor.js:472-501's mcp-test-row placement. The
    // wrapping <div> carries data-testid="connector-connection-section"
    // so future tests can assert "Test Connection lives inside
    // Connection" by DOM ancestry.
    var connectionHtml = '';
    connectionHtml += '<div class="editor-section" data-testid="connector-connection-section">';
    connectionHtml += '<h2 class="section-title">Connection</h2>';
    connectionHtml += renderConnectionFields(account, types, isCreate);
    if (!isCreate) {
      // M11 F17 L5: live status indicator row (replaces "Not tested").
      connectionHtml += renderLiveStatusRow();
      connectionHtml += renderTestConnectionRow();
      // Invite block — registry-mediated (Discord today). Returns
      // wrapper-less content per F5 L2's renderInviteSection contract
      // change (see connector-form-discord.js:renderInviteSection).
      var inviteRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
      var inviteEntry = (inviteRegistry && account && account.type) ? inviteRegistry.get(account.type) : undefined;
      if (inviteEntry && typeof inviteEntry.renderInviteSection === 'function') {
        connectionHtml += inviteEntry.renderInviteSection(account);
      }
    }
    connectionHtml += '</div>';

    // Credentials section.
    var credentialsHtml = '';
    credentialsHtml += '<div class="editor-section">';
    credentialsHtml += '<h2 class="section-title">Credentials</h2>';
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
    // F5 L6 HAT R4: renamed "Lifecycle" → "Session"; the per-section
    // friendly description sits flush under the terse title (see
    // ``.section-description`` in studio.css).
    lifecycleHtml += '<h2 class="section-title">Session</h2>';
    lifecycleHtml += '<div class="section-description">How sessions continue and connections idle.</div>';

    // F5 L3: ``<small class="form-hint">`` blocks replaced with
    // ``.field-info-icon`` tooltips per Design Decision. Production
    // pattern matches ``mcp-server-editor.js:790-795``: a ``<button
    // type="button" class="field-info-icon" title="...">`` next to the
    // label provides the browser-native tooltip; an ``aria-describedby``
    // + ``visually-hidden`` sibling carries the screen-reader text. The
    // 'data-testid' on the info-icon button preserves the
    // ``connector-{idle,continuation,auto-relay}-hint`` testid
    // lineage from the dropped ``<small>`` elements so existing tests
    // resolve against the new affordance (`continuation-hint` test is
    // updated to ``to_have_attribute("title", ...)`` since the tooltip
    // text lives in the title attribute now).
    var infoIcon = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';
    var escAttr = window.App.escapeAttr;
    var escHtml = window.App.escapeHtml;

    // Chat-session window (F3 L5) — F5 L6 HAT: rendered FIRST per
    // operator preference (continuation semantics are the dominant
    // operator concern); label shortened from "Chat-session continuation
    // window" to "Chat-session window".
    var contTipText = 'Inbound continues the same chat session within this window.';
    lifecycleHtml += '<div class="field-row admin-pf-row">';
    lifecycleHtml += '<label for="cf-continuation-window">Chat-session window</label>';
    lifecycleHtml += '<button type="button" class="field-info-icon" ' +
            'title="' + escAttr(contTipText) + '" ' +
            'aria-describedby="connector-continuation-help-text" ' +
            'data-testid="connector-continuation-hint">' + infoIcon + '</button>';
    lifecycleHtml += '<span id="connector-continuation-help-text" class="visually-hidden">' +
            escHtml(contTipText) + '</span>';
    lifecycleHtml += renderLifecycleSelect('cf-continuation-window', 'session_continuation_seconds',
            'connector-continuation-input', contValue,
            { defaultSeconds: 86400, includeNever: true });
    lifecycleHtml += '</div>';

    // Idle timeout (F2) — F5 L6 HAT: rendered SECOND; label shortened
    // from "Pool idle timeout" to "Idle timeout".
    var idleTipText = 'Reap warm connection after inactivity.';
    lifecycleHtml += '<div class="field-row admin-pf-row">';
    lifecycleHtml += '<label for="cf-idle-timeout">Idle timeout</label>';
    lifecycleHtml += '<button type="button" class="field-info-icon" ' +
            'title="' + escAttr(idleTipText) + '" ' +
            'aria-describedby="connector-idle-help-text" ' +
            'data-testid="connector-idle-hint">' + infoIcon + '</button>';
    lifecycleHtml += '<span id="connector-idle-help-text" class="visually-hidden">' +
            escHtml(idleTipText) + '</span>';
    lifecycleHtml += renderLifecycleSelect('cf-idle-timeout', 'idle_timeout_seconds',
            'connector-idle-timeout-input', idleValue,
            { defaultSeconds: 1800, includeNever: false });
    lifecycleHtml += '</div>';

    // M11 F7 L11: Always Listen toggle (account-level capability switch).
    // When ON, the F7 policy gate runs inference on non-mentioned channel
    // messages and may engage the bot. When OFF, only mentions / DMs /
    // /talk_to overrides engage. Per-agent toggles in the agent's
    // Connectors tab gate which attached agents participate when this
    // master is ON (greyed-out when this is OFF).
    var alwaysListenConfigValue = (!isCreate && account.config && Object.prototype.hasOwnProperty.call(account.config, 'always_listen'))
        ? !!account.config.always_listen
        : false;
    var alwaysListenTipText = 'When on, the bot listens to all channel messages on ' +
            'this account and uses a lightweight inference call to decide whether ' +
            'to respond. Per-attached-agent toggles control which agents participate. ' +
            'When off, only @mentions, DMs, and /talk_to overrides engage the bot.';
    lifecycleHtml += '<div class="field-row admin-pf-row cf-always-listen-row">';
    lifecycleHtml += '<label for="cf-always-listen">Always Listen</label>';
    lifecycleHtml += '<button type="button" class="field-info-icon" ' +
            'title="' + escAttr(alwaysListenTipText) + '" ' +
            'aria-describedby="connector-always-listen-help-text" ' +
            'data-testid="connector-always-listen-hint">' + infoIcon + '</button>';
    lifecycleHtml += '<span id="connector-always-listen-help-text" class="visually-hidden">' +
            escHtml(alwaysListenTipText) + '</span>';
    lifecycleHtml += '<label class="tool-enable-switch">';
    lifecycleHtml += '<input type="checkbox" class="field-input" id="cf-always-listen" ' +
            'data-field="always_listen" ' +
            'data-testid="connector-always-listen-toggle"' +
            ' aria-label="Always Listen"' +
            (alwaysListenConfigValue ? ' checked' : '') + ' />';
    lifecycleHtml += '<span class="tool-enable-switch-track"></span>';
    lifecycleHtml += '</label>';
    lifecycleHtml += '</div>';

    // M11 F13 L4: Inference provider + model rows (conditional on
    // always_listen=true). The connector's policy-gate inference call
    // uses these to pick the LLM that decides engage-or-silent on
    // non-mentioned channel messages. Empty / unset values fall through
    // to the routed agent's LLM per the L3 dispatcher contract. Use the
    // ``hidden`` attribute on a wrapper div (NOT remove-from-DOM) so
    // typed-but-unsaved values survive an OFF→ON master-toggle flip.
    var inferenceProviderConfigValue = (!isCreate && account.config &&
            Object.prototype.hasOwnProperty.call(account.config, 'inference_provider_config_id'))
        ? account.config.inference_provider_config_id
        : null;
    var inferenceModelConfigValue = (!isCreate && account.config &&
            Object.prototype.hasOwnProperty.call(account.config, 'inference_model'))
        ? account.config.inference_model
        : null;
    var inferenceRowsHidden = !alwaysListenConfigValue;

    var inferenceProviderTipText = 'The LLM provider used by the policy-gate ' +
            'inference call when Always Listen is on. Leave empty to use the ' +
            'routed agent’s own LLM.';
    var inferenceModelTipText = 'The model identifier the inference call uses ' +
            'on the selected provider. Provider-type determines whether the model ' +
            'list is queryable (Ollama yes; OpenAI / Anthropic no).';

    lifecycleHtml += '<div class="cf-inference-rows" data-testid="connector-inference-rows-container"' +
            (inferenceRowsHidden ? ' hidden' : '') + '>';

    // Provider dropdown.
    lifecycleHtml += '<div class="field-row admin-pf-row cf-inference-provider-row">';
    lifecycleHtml += '<label for="cf-inference-provider">Inference provider</label>';
    lifecycleHtml += '<button type="button" class="field-info-icon" ' +
            'title="' + escAttr(inferenceProviderTipText) + '" ' +
            'aria-describedby="connector-inference-provider-help-text" ' +
            'data-testid="connector-config-inference-provider-hint">' + infoIcon + '</button>';
    lifecycleHtml += '<span id="connector-inference-provider-help-text" class="visually-hidden">' +
            escHtml(inferenceProviderTipText) + '</span>';
    lifecycleHtml += '<select class="field-input field-select admin-pf-input admin-pf-select" ' +
            'id="cf-inference-provider" data-field="inference_provider_config_id" ' +
            'data-testid="connector-config-inference-provider-select">';
    // Initial placeholder option only; full population happens async in
    // populateInferenceProviderDropdown after mount (mirrors
    // populateRoutingAgentDropdowns). If the persisted value exists, we
    // pre-emit it as a selected option so the dirty-tracker's mount-time
    // snapshot reflects the persisted state (otherwise the populate-step
    // would flip the value and read as a dirty edit).
    lifecycleHtml += '<option value=""' +
            (inferenceProviderConfigValue == null ? ' selected' : '') +
            '>— Use routed agent’s LLM —</option>';
    if (inferenceProviderConfigValue) {
      lifecycleHtml += '<option value="' + escAttr(inferenceProviderConfigValue) + '" selected>' +
              escHtml(inferenceProviderConfigValue) + '</option>';
    }
    lifecycleHtml += '</select>';
    lifecycleHtml += '</div>';

    // Model dropdown. Populated async by populateInferenceModelDropdown
    // when a provider is selected (mirrors studio.js fetchModelsForProvider:
    // /api/providers/{id}/models → options; values not in the fetched list
    // surface as "{value} (custom)" so the operator's typed model survives
    // a provider that doesn't enumerate it via API — same pattern chat uses).
    // Pre-emit the persisted value as a selected option so the dirty-tracker's
    // mount snapshot reflects the persisted state pre-populate.
    lifecycleHtml += '<div class="field-row admin-pf-row cf-inference-model-row">';
    lifecycleHtml += '<label for="cf-inference-model">Inference model</label>';
    lifecycleHtml += '<button type="button" class="field-info-icon" ' +
            'title="' + escAttr(inferenceModelTipText) + '" ' +
            'aria-describedby="connector-inference-model-help-text" ' +
            'data-testid="connector-config-inference-model-hint">' + infoIcon + '</button>';
    lifecycleHtml += '<span id="connector-inference-model-help-text" class="visually-hidden">' +
            escHtml(inferenceModelTipText) + '</span>';
    lifecycleHtml += '<select class="field-input field-select admin-pf-input admin-pf-select" ' +
            'id="cf-inference-model" data-field="inference_model" ' +
            'data-testid="connector-config-inference-model-select">';
    // Initial placeholder options. If no provider selected → "Select a
    // provider first" (matches studio.js behavior). If provider selected
    // AND a model value is persisted → pre-emit selected option so the
    // dirty-tracker's mount snapshot reflects the persisted state.
    if (!inferenceProviderConfigValue) {
      lifecycleHtml += '<option value="" disabled' +
              (inferenceModelConfigValue ? '' : ' selected') +
              '>Select a provider first</option>';
    } else {
      lifecycleHtml += '<option value=""' +
              (inferenceModelConfigValue ? '' : ' selected') +
              '>— No model —</option>';
    }
    if (inferenceModelConfigValue) {
      lifecycleHtml += '<option value="' + escAttr(inferenceModelConfigValue) + '" selected>' +
              escHtml(inferenceModelConfigValue) + '</option>';
    }
    lifecycleHtml += '</select>';
    lifecycleHtml += '</div>';

    lifecycleHtml += '</div>'; // .cf-inference-rows

    lifecycleHtml += '</div>';

    // Pairing section (edit mode only).
    // M10 F6 L4: operator generates / regenerates the account pairing
    // code. The endpoint is the only writer for ``config["pairing"]``.
    var pairingHtml = isCreate ? '' : renderPairingSection(account);

    // Runtime Config section (edit mode only) — F5 L3.
    // F5 L6 HAT R4: section title is now "Discord" and this section
    // sits FIRST on the Access-and-Routing tab (was between Lifecycle
    // and Allowlist).
    // Registry-mediated section that mounts per-type runtime-config
    // content. The hook returns wrapper-less content; the substrate
    // wraps in an ``editor-section`` with the type-specific title.
    // Discord today; future typed connectors with runtime config blocks
    // plug in via the same hook. Absent → no section renders (Stub
    // type fails the typeof check; runtimeConfigHtml stays ''). The
    // create-mode flat layout has no tabs to mount this on; Discord's
    // ``renderConnectionFields(account, isCreate=true)`` delegates to
    // the same shared body so the runtime-config inputs render inside
    // the Connection section during creation.
    var runtimeConfigHtml = '';
    if (!isCreate) {
      var runtimeRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
      var runtimeEntry = (runtimeRegistry && account && account.type) ? runtimeRegistry.get(account.type) : undefined;
      if (runtimeEntry && typeof runtimeEntry.renderRuntimeConfigFields === 'function') {
        var runtimeInner = runtimeEntry.renderRuntimeConfigFields(account);
        if (runtimeInner) {
          runtimeConfigHtml += '<div class="editor-section" data-testid="connector-runtime-config-section">';
          // F5 L6 HAT R4: renamed "Runtime Config" → "Discord" with a
          // friendly description. The data-testid still says
          // "runtime-config" because the substrate hook is type-agnostic
          // — future non-Discord typed connectors will plug into the
          // same slot and the section header will adapt per-type
          // (deferred; today Discord is the sole connector).
          runtimeConfigHtml += '<h2 class="section-title">Discord</h2>';
          runtimeConfigHtml += '<div class="section-description">What events the bot subscribes to, where it operates, and how it appears.</div>';
          runtimeConfigHtml += runtimeInner;
          runtimeConfigHtml += '</div>';
        }
      }
    }

    // Account-scope allowlist section (edit mode only).
    // M10 F6 L4: account-level peer/channel allowlist editor.
    var allowlistHtml = isCreate ? '' : renderAllowlistSection(account);

    // Routing Rules section (edit mode only).
    // M10 F7 L7: operator-authored, ordered routing rules + per-account
    // default agent. Rides ``config.routing`` (L2 validator).
    var routingHtml = isCreate ? '' : renderRoutingRulesSection(account);

    // Attached agents (read-only, edit mode only).
    // M10 F6 L4: read-only summary of agents whose
    // ``connector_ids`` includes this account.
    var attachedAgentsHtml = isCreate ? '' : renderAttachedAgentsSection();

    // Test Connection content lives INSIDE the Connection section above (F5 L2 MCP-parity refactor).

    // Invite content lives INSIDE the Connection section above (F5 L2 MCP-parity refactor); the registry hook is called from there.

    // M11 F5 L6 HAT round-8: the M11 F2 L4 registry-mediated System
    // Prompt Directive section was REMOVED here (criterion #14
    // reverted; substrate defaults are used universally). The
    // read-only effective-directive preview now lives under the
    // Auto-reply toggle in the Session section (see ``lifecycleHtml``
    // above).

    // Danger Zone (edit only).
    var dangerZoneHtml = '';
    if (!isCreate) {
      dangerZoneHtml += '<div class="editor-section danger-zone">';
      dangerZoneHtml += '<h2 class="section-title danger-zone-title">Danger Zone</h2>';
      dangerZoneHtml += '<button type="button" class="btn-muted-destructive delete-btn connector-delete-btn" data-testid="delete-connector-btn" data-name="' + escapeAttr(account.name || '') + '">' +
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
              'data-testid="tab-access-and-routing" aria-selected="false" tabindex="-1">Advanced</button>';
      html += '</div>';

      // Tab panels — ALL section content is mounted into the DOM
      // synchronously here. App.tabs only toggles the `hidden` attribute
      // for non-active panels, so every selector that L7 wired (form
      // snapshot, dirty-tracker, collectFormData, attached-agents fetch)
      // continues to resolve against any section regardless of which
      // tab is currently active.
      html += '<div class="tabpanels">';
      // General tab — Connection (with Test Connection footer-row +
      // Invite block folded in per F5 L2 MCP-parity refactor),
      // Credentials, Pairing, Attached agents, Danger zone.
      html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.general +
              '" data-tab-id="general" aria-labelledby="connector-tab-general" hidden>';
      html += connectionHtml;
      html += credentialsHtml;
      html += pairingHtml;
      // M11 F5 L6 HAT round-8: directive section removed; nothing
      // mounts between Pairing and Attached Agents anymore.
      html += attachedAgentsHtml;
      // F5 L2: testConnectionHtml + inviteHtml folded into connectionHtml
      // above to mirror MCP editor's mcp-test-row placement.
      html += dangerZoneHtml;
      html += '</div>';
      // Access and Routing tab — F5 L6 HAT R4 reorg: emit in
      // Discord → Access → Routing → Session order. The variable names
      // (runtimeConfigHtml / allowlistHtml / routingHtml / lifecycleHtml)
      // are retained from earlier rounds and intentionally NOT renamed
      // — they're internal identifiers; only the operator-visible
      // section titles (and now this emission order) changed.
      html += '<div role="tabpanel" class="tabpanel" id="' + PANEL_IDS.accessAndRouting +
              '" data-tab-id="access-and-routing" aria-labelledby="connector-tab-access-and-routing" hidden>';
      // M11 F17 L5: discoverable-entities banner at the TOP of the tab,
      // relabeled as "Entries last refreshed" (data freshness, not connection).
      html += renderDiscoverableEntitiesBanner();
      html += runtimeConfigHtml;  // "Discord"
      html += allowlistHtml;       // "Access"
      html += routingHtml;         // "Routing"
      html += lifecycleHtml;       // "Session"
      html += '</div>';
      html += '</div>'; // .tabpanels
    }

    html += '</div>'; // .connector-editor

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
      html += '<div class="connector-empty-types-banner" ' +
              'data-testid="connector-empty-types-banner" role="status">';
      html += '<strong>No connector types are registered yet.</strong> ';
      html += 'Discord support lands in Flight 8 of Mission 10. ';
      html += 'For HAT or local testing you can seed a <code>stub</code>-type account via ';
      html += '<code>POST /api/connectors</code> with <code>{"type":"stub", ...}</code>.';
      html += '</div>';
    }

    // M11 F1 L7 HAT: in create mode, an account-shaped stub may carry
    // ``name`` (operator-typed before picking type) and ``type`` (the
    // freshly picked type) so the type-change re-render restores those
    // values. Pre-stub renders pass ``account === null``; ``createName``
    // / ``createType`` then default to empty and the placeholder selects.
    var createName = (isCreate && account && typeof account.name === 'string') ? account.name : '';
    var createType = (isCreate && account && typeof account.type === 'string') ? account.type : '';

    // Name
    html += '<div class="field-row admin-pf-row" data-field-row="name">';
    html += '<label for="cf-name">Name</label>';
    html += '<input class="field-input admin-pf-input" id="cf-name" data-field="name" data-testid="connector-name-input" value="' +
            escapeAttr(isCreate ? createName : (account.name || '')) +
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
      html += '<select class="field-input field-select admin-pf-input admin-pf-select" id="cf-type" data-field="type" data-testid="connector-type-select"' + typeDisabledAttr + '>';
      if (typesEmpty) {
        html += '<option value="" disabled selected>No connector types registered yet</option>';
      } else {
        // M11 F1 L7 HAT: the placeholder option renders ONLY when no
        // type has been picked yet (``createType === ''``); once the
        // operator picks a real type, the placeholder is suppressed
        // from the rendered list and the matching ladder entry below
        // carries ``selected`` so the re-render restores the pick.
        // F5 L6 HAT: ``hidden`` attribute keeps the placeholder out of
        // the open list while still displaying its text in the closed
        // state — operator wants a label-only placeholder, not a
        // selectable row.
        if (createType === '') {
          html += '<option value="" disabled selected hidden>Select a connector type</option>';
        }
        for (var i = 0; i < typesList.length; i++) {
          var t = typesList[i];
          var optSelected = (t.value === createType) ? ' selected' : '';
          html += '<option value="' + escapeAttr(t.value) + '"' + optSelected + '>' + escapeHtml(t.label) + '</option>';
        }
      }
      html += '</select>';
    } else {
      html += '<input class="field-input admin-pf-input" id="cf-type" data-field="type" data-testid="connector-type-readonly" value="' +
              escapeAttr(account.type || '') + '" readonly />';
    }
    html += '<span class="field-error" data-field-error="type" hidden></span>';
    html += '</div>';

    // Config kv editor — plaintext key-value rows.
    //
    // M11 F1 L3: per-type form registry consult. The substrate emits
    // the outer field-row wrapper unconditionally so the
    // '[data-testid="connector-config"]' selector keeps
    // resolving for tests; only the inner content varies between the
    // typed (entry.renderConnectionFields) and generic
    // (renderConfigKvTable) render paths. Triple-guard against an
    // early-load race where the registry script hasn't attached yet.
    // M11 F1 L7 HAT: in create mode, consult the registry against the
    // type carried on the account stub (set by the type-change
    // re-render in ``wireEditorEvents`` when the operator picks a
    // connector type). Pre-stub renders pass ``account === null``;
    // ``connActiveType`` then evaluates to '' and the generic kv-table
    // fallback path stays in place — preserving the pre-pick baseline.
    var connRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var connActiveType = (account && account.type) || '';
    var connEntry = (connRegistry && connActiveType) ? connRegistry.get(connActiveType) : undefined;

    html += '<div class="field-row admin-pf-row connector-config-wrap">';
    html += '<label>Config</label>';
    html += '<div class="connector-config" data-testid="connector-config">';
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
  // M11 F7 L12 (HAT-time hotfix): ``always_listen`` joins the reserved set —
  // the L11 Session-section toggle is the only writer for
  // ``config.always_listen``. Without this entry the kv-table also renders
  // ``always_listen`` and the operator sees two conflicting controls. Caught
  // at L12 Phase 1 walk.
  // M11 F13 L4: ``inference_provider_config_id`` + ``inference_model``
  // join the reserved set — the new Session-section rows are the only
  // writers for these flat keys. Without these entries the kv-table
  // also renders them post-v26 migration and the operator sees
  // duplicate controls (same hazard as F7 L12's always_listen hotfix).
  var RESERVED_CONFIG_KEYS = {
    pairing: true,
    allowlist: true,
    routing: true,
    always_listen: true,
    inference_provider_config_id: true,
    inference_model: true,
  };

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
    var html = '<table class="connector-config-table" data-testid="connector-config-table">';
    html += '<thead class="connector-config-thead' + headHiddenClass + '">' +
            '<tr><th>Key</th><th>Value</th><th aria-label="Actions"></th></tr></thead>';
    html += '<tbody data-testid="connector-config-tbody">';
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
    html += '<tr class="connector-config-row" data-row-idx="' + idx + '">';
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
    // existing ``.editor-section`` / ``.connector-secrets``
    // wrappers (`renderConnectorEditor:268-273`), so the
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
    var html = '<table class="connector-secrets-table" data-testid="connector-secrets-table">';
    html += '<thead class="connector-secrets-thead' + headHiddenClass + '">' +
            '<tr><th>Key</th><th>Value</th><th aria-label="Actions"></th></tr></thead>';
    html += '<tbody data-testid="connector-secrets-tbody">';
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
    html += '<tr class="connector-secret-row" data-row-idx="' + idx + '">';
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
    var configRowEls = container.querySelectorAll('.connector-config-table tbody tr.connector-config-row');
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
    var secretRowEls = container.querySelectorAll('.connector-secrets-table tbody tr.connector-secret-row');
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

    // M11 F7 L11: ``always_listen`` is a substrate-level capability
    // switch, captured as a SEPARATE top-level key on the snapshot
    // object. The staticFields loop above reads ``.value`` (which is
    // ``"on"`` for checkboxes regardless of checked state), so the new
    // field cannot piggyback on that loop — it must be captured here as
    // a real boolean. Triple-guard: when the input is absent (older
    // create-mode renders, or future code that drops the toggle), the
    // key is OMITTED so the snapshot bytes stay stable for the unchanged
    // surface.
    var alwaysListenSnap = container.querySelector('[data-field="always_listen"]');
    if (alwaysListenSnap) {
      snapshotObj.always_listen = !!alwaysListenSnap.checked;
    }

    // M11 F13 L4: capture the two inference-config fields on the snapshot
    // object so the dirty-tracker fires for edits. Mirrors the always_listen
    // pattern — read the live DOM value; OMIT the key when the input is
    // absent so unrelated render paths keep stable snapshot bytes. Serialize
    // empty string as null so the mount-time snapshot matches the
    // collectFormData null-write semantic (otherwise the populate-step's
    // recapture is the only thing keeping the form from reading as dirty).
    var inferenceProviderSnap = container.querySelector('[data-field="inference_provider_config_id"]');
    if (inferenceProviderSnap) {
      snapshotObj.inference_provider_config_id = inferenceProviderSnap.value || null;
    }
    var inferenceModelSnap = container.querySelector('[data-field="inference_model"]');
    if (inferenceModelSnap) {
      snapshotObj.inference_model = inferenceModelSnap.value || null;
    }

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
    var nextConfigRowIdx = container.querySelectorAll('.connector-config-table tbody tr.connector-config-row').length;
    var nextSecretRowIdx = container.querySelectorAll('.connector-secrets-table tbody tr.connector-secret-row').length;

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

    // M11 F7 L11: dispatch always-listen changes for the agent's Connectors
    // tab to grey-out per-agent toggles. Third inline-CustomEvent string in
    // Studio (n=3 — see TODO below citing F4 R13 lift candidate).
    //
    // TODO(routine-maintenance): with n=3 reached
    // (connector-pool-warmed + connector-discoverable-
    // refresh-requested + this one), F4 R13 calls for lifting the inline
    // CustomEvent strings into a shared studio-event-bus module. Defer
    // per F7 recon discipline (the bus lift expands the leg surface
    // beyond the policy-gate scope).
    var alwaysListenEl = container.querySelector('[data-field="always_listen"]');
    if (alwaysListenEl && account && account.id) {
      alwaysListenEl.addEventListener('change', function () {
        App.studio.eventBus.emit('connector-always-listen-changed', {
          accountId: account.id,
          enabled: !!alwaysListenEl.checked,
        });
        // M11 F13 L4: toggle the inference-rows visibility in lockstep
        // with the always-listen master toggle. Use the ``hidden``
        // attribute on the wrapping container (not remove-from-DOM) so
        // typed-but-unsaved values survive an OFF→ON flip.
        var inferenceWrap = container.querySelector('[data-testid="connector-inference-rows-container"]');
        if (inferenceWrap) {
          if (alwaysListenEl.checked) {
            inferenceWrap.removeAttribute('hidden');
          } else {
            inferenceWrap.setAttribute('hidden', '');
          }
        }
      });
    }

    // ── M11 F1 L7 HAT: create-mode type-change re-render ───────────────
    //
    // In create mode, picking a type from the dropdown must cause the
    // form to re-render so the per-type registry entry's typed fields
    // (intents fieldset, BOT_TOKEN typed input, etc.) replace the
    // generic kv-table fallback. The substrate hardcoded
    // ``isCreate ? '' : account.type`` for the registry consult before
    // this fix, so the typed form never rendered at create time.
    //
    // Approach (Option A — full re-mount): capture the Name input
    // value, build an account-shaped stub carrying the new type +
    // captured name, and call ``renderConnectorEditor`` with
    // ``forceCreate=true``. The re-render path re-attaches all
    // listeners (this attachStaticListeners + the registry's
    // wireEvents). The Name value is restored via the stub so the
    // operator's prior typing isn't lost.
    //
    // The fix is type-agnostic: ``registry.get(newType)`` resolves any
    // registered entry. Unregistered types (e.g. ``'stub'``) re-render
    // into the generic kv-table — the existing baseline for those
    // types — without special-casing.
    //
    // Edit mode: the type field is read-only (``readonly`` attribute,
    // no ``change`` event for the operator to fire), so this listener
    // would be inert; it's gated behind ``isCreate`` anyway.
    if (isCreate) {
      var typeSelectEl = container.querySelector('[data-field="type"]');
      if (typeSelectEl && typeSelectEl.tagName === 'SELECT') {
        typeSelectEl.addEventListener('change', function () {
          var newType = typeSelectEl.value || '';
          if (!newType) return;
          // Capture the Name input value so the re-render restores it.
          var nameEl = container.querySelector('[data-field="name"]');
          var capturedName = nameEl ? (nameEl.value || '') : '';
          var stub = {
            name: capturedName,
            type: newType,
            config: {},
            secrets: {}
          };
          renderConnectorEditor(container, stub, types, callbacks, true);
          // Picking a type IS a dirty edit relative to the pre-pick
          // baseline. The fresh editor's snapshot includes ``type=newType``,
          // so its own ``checkDirty`` would read clean — manually flip
          // the Save / Cancel state so the operator can complete the
          // form and submit. Re-finding the elements (not capturing
          // pre-re-render references) because the previous DOM was
          // replaced.
          var newSaveBtn = container.querySelector('.save-btn');
          var newCancelBtn = container.querySelector('.cancel-btn');
          if (newSaveBtn) newSaveBtn.disabled = false;
          if (newCancelBtn) newCancelBtn.disabled = false;
          if (callbacks.onDirtyChange) callbacks.onDirtyChange(true);
        });
      }
    }

    // ── Config kv table delegated events ──────────────────────────────
    var configTable = container.querySelector('.connector-config-table');
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
          var rrow = removeBtn.closest('tr.connector-config-row');
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
        var tbody = container.querySelector('.connector-config-table tbody');
        if (!tbody) return;
        var idx = nextConfigRowIdx++;
        var tmp = document.createElement('tbody');
        tmp.innerHTML = renderConfigRow({ key: '', value: '' }, idx);
        var newTr = tmp.querySelector('tr.connector-config-row');
        if (newTr) {
          tbody.appendChild(newTr);
          updateConfigHeadVisibility(container);
          checkDirty();
        }
      });
    }

    // ── Secrets kv table delegated events ─────────────────────────────
    var secretsTable = container.querySelector('.connector-secrets-table');
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
          var row = eyeBtn.closest('tr.connector-secret-row');
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
          var rrow = removeBtn.closest('tr.connector-secret-row');
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
        var tbody = container.querySelector('.connector-secrets-table tbody');
        if (!tbody) return;
        var idx = nextSecretRowIdx++;
        var tmp = document.createElement('tbody');
        tmp.innerHTML = renderSecretRow({ key: '', value: '', _originalMasked: '' }, idx);
        var newTr = tmp.querySelector('tr.connector-secret-row');
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
          renderConnectorEditor(container, account, types, callbacks);
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
    var deleteBtn = container.querySelector('[data-testid="delete-connector-btn"]');
    if (deleteBtn && isEdit) {
      function doDelete(btn, revertFn) {
        fetch('/api/connectors/' + encodeURIComponent(account.id), { method: 'DELETE' })
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

      // M11 F13 L4: populate the inference-provider dropdown asynchronously.
      // Fires regardless of always-listen state so the dropdown is ready
      // when the operator flips the master toggle ON.
      populateInferenceProviderDropdown(container, account, checkDirty, recaptureSnapshot);

      // M11 F13 L4 (model-dropdown enhancement): wire the provider-select
      // change handler to repopulate the model dropdown from
      // /api/providers/{id}/models. Also populate immediately for the
      // persisted provider (if any) so the operator sees the model list on
      // initial load.
      wireInferenceModelRepopulate(container, account, checkDirty, recaptureSnapshot);

      // M11 F17 L5: start the live-status poll on editor mount.
      _wireLiveStatus(container, account);
    }
  }

  // ── Save handlers ───────────────────────────────────────────────────

  function handleSaveEdit(account, payload, container, callbacks, saveBtn, recaptureSnapshot) {
    var errorEl = container.querySelector('.editor-error');
    saveBtn.disabled = true;
    var originalLabel = saveBtn.textContent;
    saveBtn.textContent = 'Saving…';

    App.api.fetchJson('/api/connectors/' + encodeURIComponent(account.id), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
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

    App.api.fetchJson('/api/connectors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (newAccount) {
        saveBtn.textContent = 'Testing…';
        return fetch('/api/connectors/' + encodeURIComponent(newAccount.id) + '/test/connect', {
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
      var configRows = container.querySelectorAll('.connector-config-table tbody tr.connector-config-row');
      for (var i = 0; i < configRows.length; i++) {
        var crow = configRows[i];
        var ck = crow.querySelector('.config-key-input');
        var cv = crow.querySelector('.config-value-input');
        if (!ck || !cv) continue;
        var ckey = (ck.value || '').trim();
        if (!ckey) continue;
        config[ckey] = cv.value || '';
      }

      var secretRows = container.querySelectorAll('.connector-secrets-table tbody tr.connector-secret-row');
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
          secrets[skey] = window.App.studio.MASKED_SENTINEL;
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
          roles: allowlistState.roles,
          dm_admission: allowlistState.dm_admission  // M11 F10 L2
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

    // M11 F7 L11: always_listen is a substrate-level capability switch
    // (NOT routed through the per-type registry's ``collect`` hook —
    // registry entries own only type-specific inputs). The toggle lives
    // in the Session section and is rendered in both create + edit modes;
    // when the toggle element is present, write its boolean state to
    // ``config.always_listen`` so the backend's L5 validator persists it.
    var alwaysListenInputCFD = container.querySelector('[data-field="always_listen"]');
    if (alwaysListenInputCFD) {
      config.always_listen = !!alwaysListenInputCFD.checked;
    }

    // M11 F13 L4: write the connector-scope inference fields into
    // ``config``. Empty values serialize as null (NOT empty string) so
    // the Pydantic validator's ``str | None`` shape accepts them and the
    // L3 dispatcher's "None falls through to routed-agent LLM" path
    // fires. Write the keys unconditionally when the inputs exist so
    // toggling non-null → null actually clears the persisted state; the
    // ``if (input)`` guards handle render paths that drop the fields.
    var inferenceProviderInput = container.querySelector('[data-field="inference_provider_config_id"]');
    if (inferenceProviderInput) {
      config.inference_provider_config_id = inferenceProviderInput.value || null;
    }
    var inferenceModelInput = container.querySelector('[data-field="inference_model"]');
    if (inferenceModelInput) {
      config.inference_model = (inferenceModelInput.value || '').trim() || null;
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

    fetch('/api/connectors/' + encodeURIComponent(accountId) + '/test/connect', {
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

    // M11 F4 L4 fold-in (HAT-discovered): when Test Connection's response
    // carries ``pool_warmed=true`` (A1 contract), dispatch a
    // ``connector-pool-warmed`` event so any mounted
    // ``discoverable-dropdown`` for this account re-fetches its entity
    // list. Without this nudge, dropdowns hold their stale pre-probe-404
    // state until the operator clicks each axis's Refresh manually. This
    // is the warmup-signal-propagation extension of the
    // ``pool-warming-entrypoints-are-finite-and-named`` convention
    // (M11 F4 L1): the named entrypoint announces its success, listeners
    // react.
    if (status === 'ok' && details && details.pool_warmed === true && accountId) {
      App.studio.eventBus.emit('connector-pool-warmed', { accountId: accountId });
    }

    if (ledEl) {
      ledEl.className = 'indicator-led ' + statusLedClass(status) + ' connector-test-led';
      ledEl.setAttribute('data-state', status);
      ledEl.setAttribute('aria-label', statusAriaLabel(status));
    }
    if (messageEl) {
      messageEl.textContent = message || statusAriaLabel(status);
    }
    // F5 L6 HAT round-7: statusEl removed; inline messageEl (next to LED)
    // is the single source for the status text. The block-level status
    // div was a duplicate of messageEl — operator-flagged in HAT.
    void statusEl;
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

  // ── Discoverable-entities banner (M11 F17 L5 relocation) ────────────
  //
  // Formerly rendered inside the Users allowlist section. Moved to the
  // TOP of the Access-and-Routing tab so it is clearly a data-freshness
  // indicator rather than a connection-status indicator. Relabeled from
  // "Discoverable entities" → "entries last refreshed" per the leg spec.
  // Testid ``connector-allowlist-banner`` is PRESERVED so ``_wireAllowlistBanner``
  // and existing browser tests resolve without changes.

  function renderDiscoverableEntitiesBanner() {
    var html = '';
    html += '<div class="editor-section connector-discoverable-banner-section">';
    html += '<div class="field-row admin-pf-row connector-allowlist-banner" ' +
            'data-testid="connector-allowlist-banner" data-state="pre-probe">';
    html += '<label>Entries last refreshed</label>';
    html += '<span class="indicator-led indicator-led--idle ' +
            'connector-allowlist-banner-led" ' +
            'data-testid="connector-allowlist-banner-led" ' +
            'aria-label="Discoverable entities status"></span>';
    html += '<span class="connector-allowlist-banner-status" ' +
            'data-testid="connector-allowlist-banner-status" aria-live="polite">' +
            'Connect to populate the discoverable lists.</span>';
    html += '<button type="button" class="btn-outlined-primary ' +
            'connector-allowlist-banner-refresh" ' +
            'data-testid="connector-allowlist-banner-refresh">Refresh</button>';
    html += '</div>';
    html += '</div>';
    return html;
  }

  // ── Live connection-status indicator (M11 F17 L5) ───────────────────
  //
  // Replaces the old hardcoded "Not tested" indicator. Returns a
  // field-row that renders the live status driven by polling
  // ``GET /api/connectors/{id}/status`` every 2–5s. The poll starts on
  // editor mount (``_wireLiveStatus``) and stops when the element is
  // removed from the DOM (``isConnected`` guard, mirroring the
  // allowlist-banner's pool-warm-handler pattern).
  //
  // States: connected | connecting | disconnected | error
  // Non-alarming copy for the intended-cold "no attached agent" case
  // (state=disconnected, no error) — shown as "Disconnected".
  // Error state surfaces ``last_error`` + optional ``last_error_link``.
  //
  // data-testids added (referenced by behavior test connector-editor-ux.md):
  //   connector-live-status       — the status text span (steps 1/2/8)
  //   connector-live-status-error — the error message span (step 8)
  //   connector-live-status-error-link — the error action link (step 8)

  function renderLiveStatusRow() {
    var html = '';
    html += '<div class="field-row admin-pf-row connector-live-status-row">';
    html += '<label>Connection</label>';
    html += '<div class="connector-live-status-wrap">';
    html += '<span class="indicator-led indicator-led--idle connector-live-status-led" ' +
            'aria-label="Status unknown" data-state="unknown"></span>';
    html += '<span class="connector-live-status-text" ' +
            'aria-live="polite" ' +
            'data-testid="connector-live-status">Checking…</span>';
    html += '</div>';
    html += '</div>';
    html += '<div class="connector-live-status-error-wrap" ' +
            'role="alert" ' +
            'data-testid="connector-live-status-error-wrap" hidden>';
    html += '<span class="connector-live-status-error" ' +
            'data-testid="connector-live-status-error"></span>';
    html += '<a class="connector-live-status-error-link" ' +
            'data-testid="connector-live-status-error-link" ' +
            'target="_blank" rel="noopener noreferrer" hidden></a>';
    html += '</div>';
    return html;
  }

  // ── Validate (doctor probe) footer-row (formerly "Test Connection") ──
  //
  // Relabeled to "Validate" per M11 F17 L5 design decision. The button
  // testid ``connector-test-connection-btn`` is PRESERVED byte-for-byte
  // so existing browser tests continue to resolve. Only the visible
  // button label text changes.

  function renderTestConnectionRow() {
    var html = '';
    html += '<div class="field-row admin-pf-row connector-test-row">';
    html += '<label></label>';
    html += '<div class="connector-test-actions">';
    html += '<button type="button" class="btn-outlined-primary connector-test-connection-btn" data-testid="connector-test-connection-btn">' +
            window.App.icon('refresh-cw') + ' Validate</button>';
    html += '<span class="indicator-led indicator-led--idle connector-test-led" data-testid="connector-test-led" data-state="idle" aria-label="Not tested"></span>';
    html += '<span class="connector-test-message" aria-live="polite" data-testid="connector-test-message"></span>';
    html += '</div>';
    html += '</div>';
    html += '<div class="connector-test-details-wrap" data-testid="connector-test-details-wrap" hidden>' +
            '<div data-testid="connector-test-details"></div>' +
            '</div>';
    return html;
  }

  // ── Pairing / Allowlist / Attached agents (M10 F6 L4) ───────────────
  //
  // These three sections render only in edit mode (gated on
  // ``!isCreate`` at the call site, mirroring the Test Connection +
  // Danger Zone gate). They operate on the leg-1b reserved
  // ``config["pairing"]`` and ``config["allowlist"]`` keys and on the
  // new reverse-lookup endpoint
  // ``GET /api/connectors/{id}/attached-agents`` (leg-4 spec).
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
    html += '<h2 class="section-title">Pairing</h2>';

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
    // rendered ``<label>`` text + hint text vary per type.
    // ``hintTone === 'native'`` drops the "Discord-flavored" qualifier
    // on the groups + roles rows (redundant noise when the label
    // already says "Servers / Roles").
    //
    // F5 L6 HAT round-3 — each axis row converted to the canonical
    // ``.field-row.admin-pf-row`` 3-column layout
    // (label | info-icon | chiplist), matching the Lifecycle section's
    // pattern (Chat-session window / Idle timeout). Pre-round-3 the row
    // used ``<label> | <chiplist> | <small.form-hint>`` which read as
    // a different shape than the Lifecycle rows one section up. The
    // verbose ``<small class="form-hint">`` block is dropped; its text
    // moves into the info-icon's ``title=`` (browser-native tooltip on
    // hover) + a visually-hidden sibling span (screen-reader access via
    // ``aria-describedby``). The ``data-testid="connector-allowlist-
    // {axis}-hint"`` migrates from the dropped ``<small>`` to the new
    // info-icon ``<button>`` so any test resolving by this testid
    // continues to find an element. The ``connector-acl-
    // fieldlabel`` class is preserved on the ``<label>`` for any
    // styling/test selectors that key on it.
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var vocab = _vocabForAccount(account);
    var nativeTone = vocab.hintTone === 'native';
    var infoIcon = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';

    var html = '';
    // M11 F12 L5 cycle 5 — split the prior single "Access" section into
    // two sections: USERS (peers + DM admission) and SERVERS (the
    // hierarchical server-as-parent organizer). Both wrappers retain
    // the ``connector-allowlist-section`` class so existing selectors
    // (e.g. the Discord-vocabulary label-list assertion) collect labels
    // across both sections without modification. The DM admission row
    // moves above the Users (peers) row per operator UX request — the
    // gating decision ("admit any DMs at all?") naturally precedes the
    // per-peer chip list.
    html += '<div class="editor-section connector-allowlist-section ' +
            'connector-allowlist-section--users">';
    // F5 L6 HAT R4: renamed "Account-scope allowlist" → "Access" with
    // a friendly description. L5 cycle 5: "Access" → "Users".
    // M11 F17 L8 (Leg D): "Users" → "Direct Messages" (peers axis is
    // DM-only post-F16; relabel matches the actual function).
    html += '<h2 class="section-title">Direct Messages</h2>';
    html += '<div class="section-description">Who can DM the bot.</div>';

    // M11 F17 L5: discoverable-entities banner moved to the TOP of the
    // Access-and-Routing tab (rendered by renderDiscoverableEntitiesBanner
    // and prepended to the tab panel by renderConnectorEditor). Removed
    // from this section to avoid duplication. The ``connector-allowlist-banner``
    // testid and wiring are unchanged; _wireAllowlistBanner resolves by
    // testid so it works from the new location.

    html += '<div class="connector-allowlist-lists" ' +
            'data-testid="connector-allowlist-lists">';

    // M11 F10 L2: DM admission axis (3-value selector). Semantic
    // placement: dm_admission gates WHETHER any DMs are admitted; the
    // Users (peers) chip-list below then defines WHO. Storage at
    // account.config.allowlist.dm_admission; dispatcher consult at
    // _acl.py:admits_inbound (L1).
    //
    // L5 cycle 5: moved ABOVE the Users chip-list per operator UX
    // request. The "Approved peers are those on the Users allowlist
    // below" tooltip phrasing tracks the new ordering. The peers row
    // still owns the ``connector-allowlist-peers-row`` testid + the
    // ``dm-admission-admin-approved`` state class that gates the
    // per-peer DM toggles; that wiring is order-agnostic (queries by
    // testid) so the swap is purely visual.
    // M11 F17 L8 (Leg D): relabeled — section is now "Direct Messages";
    // tooltip updated to match new 3-mode policy copy.
    var dmAdmissionTipText = 'Controls who can send direct messages to ' +
        'the bot. "Only these people" admits peers on the Direct ' +
        'Messages list below.';
    // M11 F12 L4 — Literal value rename ``allowlisted-peers-only`` →
    // ``admin-approved`` (operator-vocabulary alignment per F12 L3).
    var currentDmAdmission = (account && account.config && account.config.allowlist &&
        account.config.allowlist.dm_admission) || 'admin-approved';
    html += '<div class="field-row admin-pf-row connector-acl-fieldrow" ' +
            'data-testid="connector-allowlist-dm-admission-row">';
    html += '<label class="connector-acl-fieldlabel" ' +
            'for="connector-allowlist-dm-admission-select">DM admission</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + escapeAttr(dmAdmissionTipText) + '" ' +
            'aria-describedby="connector-allowlist-dm-admission-help-text" ' +
            'data-testid="connector-allowlist-dm-admission-hint">' + infoIcon + '</button>';
    html += '<span id="connector-allowlist-dm-admission-help-text" class="visually-hidden">' +
            escapeHtml(dmAdmissionTipText) + '</span>';
    html += '<select id="connector-allowlist-dm-admission-select" ' +
            'class="field-input admin-pf-input" ' +
            'data-testid="connector-allowlist-dm-admission-select">';
    // M11 F17 L8 (Leg D): relabeled dm_admission options to plain-
    // language copy. Values unchanged; only display text updated.
    html += '<option value="none"' +
            (currentDmAdmission === 'none' ? ' selected' : '') + '>No one</option>';
    html += '<option value="admin-approved"' +
            (currentDmAdmission === 'admin-approved' ? ' selected' : '') +
            '>Only these people</option>';
    html += '<option value="all"' +
            (currentDmAdmission === 'all' ? ' selected' : '') + '>Anyone</option>';
    html += '</select>';
    html += '</div>';

    // Peers (Users) axis. Sits below the DM admission row (L5 cycle 5
    // reorder) so the gating decision precedes the per-peer chip list.
    var peersTipText = 'Empty list = no ' + vocab.peer + ' restriction.';
    // M11 F12 L4 — peers row carries a state-class for the per-peer
    // DM toggle visibility. The class is initialized from
    // ``currentDmAdmission`` (read above) and toggled live by the
    // dm_admission select's change handler wired in
    // ``wireAllowlistEvents``.
    var peersDmClass = ' connector-allowlist-peers-row';
    html += '<div class="field-row admin-pf-row connector-acl-fieldrow' + peersDmClass +
            '" data-testid="connector-allowlist-peers-row">';
    html += '<label class="connector-acl-fieldlabel">' +
            escapeHtml(_capitalize(vocab.peers)) + '</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + escapeAttr(peersTipText) + '" ' +
            'aria-describedby="connector-allowlist-peers-help-text" ' +
            'data-testid="connector-allowlist-peers-hint">' + infoIcon + '</button>';
    html += '<span id="connector-allowlist-peers-help-text" class="visually-hidden">' +
            escapeHtml(peersTipText) + '</span>';
    html += '<div data-allowlist-chiplist-slot="peers"></div>';
    html += '</div>';

    html += '</div>'; // .connector-allowlist-lists
    html += '</div>'; // .editor-section USERS

    // SERVERS section (L5 cycle 5 split from the prior single ACCESS
    // section). The hierarchical Server-as-parent organizer renders
    // here. The section header is self-evident; no intro line.
    //
    // M11 F12 L5 — hierarchical Server-as-parent layout. The Servers
    // section is the PARENT organizer; channels + roles render as
    // NESTED sub-controls inside each server row at mount time (see
    // ``_mountAllowlistHierarchicalEditor`` below).
    //
    // The L4 flat 3-section layout (Channels / Guilds / Roles as
    // siblings) is gone. Markup carries a single Servers slot; the
    // mount-time render reads ``account.config.allowlist.guilds`` and
    // for each guild_id builds a server row with two sub-chiplists
    // (channels filtered by guild_id; roles filtered by guild_id).
    //
    // Slot-id retention: the slot keys ``channels`` / ``guilds`` /
    // ``roles`` are NOT in this markup any more; the collect path
    // reads the hierarchical state via the slot getter installed on
    // the Servers slot itself.
    html += '<div class="editor-section connector-allowlist-section ' +
            'connector-allowlist-section--servers">';
    html += '<h2 class="section-title">Servers</h2>';
    var guildsTipText = 'Add a ' + vocab.group +
            '. Narrow which channels and roles inside it the bot ' +
            'answers from.' +
            (nativeTone ? '' : ' Discord-flavored.');
    html += '<div class="field-row admin-pf-row connector-acl-fieldrow ' +
            'connector-allowlist-servers-section" ' +
            'data-testid="connector-allowlist-servers-section">';
    html += '<label class="connector-acl-fieldlabel">' +
            escapeHtml(_capitalize(vocab.groups)) + '</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + escapeAttr(guildsTipText) + '" ' +
            'aria-describedby="connector-allowlist-guilds-help-text" ' +
            'data-testid="connector-allowlist-guilds-hint">' + infoIcon + '</button>';
    html += '<span id="connector-allowlist-guilds-help-text" class="visually-hidden">' +
            escapeHtml(guildsTipText) + '</span>';
    html += '<div data-allowlist-chiplist-slot="guilds" ' +
            'data-testid="connector-allowlist-servers-slot"></div>';
    html += '</div>';
    html += '</div>'; // .editor-section SERVERS
    return html;
  }

  // Build a chip-list-editor wrapper for the account-scope allowlist.
  // Mirrors connectors-tab.js::_buildChipList exactly so the two
  // surfaces feel identical at the operator level. Per-account ACL
  // data attributes are NOT used here (this is the account-scope
  // list, not a per-agent ACL); studio.js's collectFormData reads the
  // wrapper via the studio-side ``.connector-acl-chiplist`` selector,
  // but the connector-editor's own collectFormData reads via
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
            'tabindex="0" aria-label="Reorder rule — use Arrow keys to move" title="Drag to reorder" ' +
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
    // F5 L6 HAT R4: renamed "Routing rules" → "Routing" with a
    // friendly description.
    html += '<h2 class="section-title">Routing</h2>';
    html += '<div class="section-description">Which agent handles which message.</div>';

    // M10 F7 L9 HAT2: default-agent row at the top of the section
    // (operator visual-hierarchy feedback during HAT). The rules table +
    // "Add rule" button follow.
    //
    // F5 L6 HAT R5: the dangling ``<small class="form-hint">Fall back to
    // first-eligible-alphabetical agent.</small>`` row read as a
    // disconnected concern beneath the dropdown. Migrated to the
    // canonical 3-column ``label | info-icon | field`` shape — the
    // tooltip text is now Default-agent-specific and answers the
    // "what happens if I leave this empty?" question directly, in line
    // with the info-icon pattern established by Lifecycle / Runtime
    // Config / Access in rounds 3-4. ``data-testid="connector-routing-
    // default-hint"`` migrates from the dropped ``<small>`` to the new
    // info-icon ``<button>`` (any test resolving by this testid keeps
    // finding an element).
    var escapeHtml = window.App.escapeHtml;
    var infoIcon = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';
    var defaultAgentTipText = "Picks up messages that don't match any " +
            "per-rule override below. Leave empty to fall back to the " +
            "first eligible agent alphabetically.";
    html += '<div class="field-row admin-pf-row connector-routing-default-row">';
    html += '<label for="connector-routing-default">Default agent</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + escapeAttr(defaultAgentTipText) + '" ' +
            'aria-describedby="connector-routing-default-help-text" ' +
            'data-testid="connector-routing-default-hint">' + infoIcon + '</button>';
    html += '<span id="connector-routing-default-help-text" class="visually-hidden">' +
            escapeHtml(defaultAgentTipText) + '</span>';
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

    // M12 F4 L1 A2: persistent visually-hidden live region for keyboard
    // reorder announcements. Injected once per section render (not per
    // keypress). The keydown handler in wireRoutingRulesEvents writes
    // position text here after each move, or a boundary message when
    // the rule is already first/last.
    html += '<span class="visually-hidden" aria-live="polite" data-routing-live-region></span>';

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

  // M11 F3 L6b — per-row routing-rules match-cell editor mount dispatch.
  //
  // Mirrors L6a's ``_mountAllowlistAxisEditor`` shape for the
  // routing-rules table's per-row match cell. Routing rows are scoped
  // (channel / thread / dm / peer per F7 vocab); the match values
  // target the corresponding API axis per the mapping below. For
  // Discord accounts the registry-entry ``renderDiscoverableDropdown``
  // hook mounts the live-data dropdown; stub-type accounts fall back
  // to the existing chip-list editor (preserves the regression
  // contract for F6/F7 stub-type tests).
  //
  // Scope → API axis mapping (centralized here):
  //   ``'channel'`` → ``'channels'``
  //   ``'thread'``  → ``'channels'`` (threads narrow channels at
  //                                   routing-engine time per F7 logic)
  //   ``'dm'``      → ``'peers'``
  //   ``'peer'``    → ``'peers'``
  //
  // Dropdown path installs ``slotEl._routingMatchValues = () => ids``
  // on the chip-list slot — the canonical bridge for the collect path
  // in ``collectRoutingFromContainer``. The chip-list fallback does
  // NOT install the getter (collect path falls through to the
  // text-node walk on the seeded ``.chip`` elements).
  function _mountRoutingMatchEditor(slotEl, account, scope, currentValues, vocab, checkDirty) {
    if (!slotEl) return;
    var state = { values: (currentValues || []).slice() };
    var registry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var entry = (registry && account && account.type) ? registry.get(account.type) : null;
    // Scope → API axis. Routes the dropdown to the right entity feed.
    var apiAxis;
    if (scope === 'channel' || scope === 'thread') {
      apiAxis = 'channels';
    } else if (scope === 'dm' || scope === 'peer') {
      apiAxis = 'peers';
    } else {
      // Empty or unknown scope (e.g. a freshly-added row before the
      // operator picks a scope). Default to ``channels`` for the
      // dropdown so the operator has something to scan; the
      // scope-change listener re-mounts as soon as the operator
      // picks a scope.
      apiAxis = 'channels';
    }
    if (entry && typeof entry.renderDiscoverableDropdown === 'function') {
      var dropdownEl = entry.renderDiscoverableDropdown(
        account,
        apiAxis,
        state.values,
        vocab,
        function onChange(newValues) {
          state.values = (newValues || []).slice();
          if (typeof checkDirty === 'function') checkDirty();
        }
      );
      if (dropdownEl) {
        slotEl.innerHTML = '';
        slotEl.appendChild(dropdownEl);
        slotEl._routingMatchValues = function () { return state.values.slice(); };
        return;
      }
    }
    // Fallback: chip-list editor (stub-type / no-entry regression
    // contract). Preserves the same DOM shape as ``_renderRoutingRow``
    // emits, so the collect-path text-node walk reads the values back
    // identically to the pre-L6b shape.
    var helpers = window.App.adminFormHelpers;
    // Clear any previously-installed getter so the collect path falls
    // through to the text-node walk after a re-mount.
    if (slotEl._routingMatchValues) {
      try { delete slotEl._routingMatchValues; }
      catch (_) { slotEl._routingMatchValues = null; }
    }
    slotEl.innerHTML = '';
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    for (var i = 0; i < state.values.length; i++) {
      var v = String(state.values[i]);
      var chip = document.createElement('span');
      chip.className = 'chip';
      chip.appendChild(document.createTextNode(v));
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chip-remove';
      btn.setAttribute('aria-label', 'Remove ' + v);
      btn.textContent = '×';
      chip.appendChild(btn);
      slotEl.appendChild(chip);
    }
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'chip-list-input';
    input.placeholder = 'Add match value…';
    input.setAttribute('aria-label', 'Add match value');
    slotEl.appendChild(input);
    if (helpers && helpers.wireChipListEditor) {
      helpers.wireChipListEditor(slotEl, { onChange: checkDirty });
    }
    void escapeAttr; void escapeHtml;
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

    // M10 F7 L9 HAT2 / M11 F3 L6b: wire the per-row match-cell editor.
    //
    // L6b dispatches through ``_mountRoutingMatchEditor`` which mirrors
    // L6a's ``_mountAllowlistAxisEditor`` shape — Discord-type accounts
    // get the live-data dropdown component (axis selected per the row's
    // current scope: channel/thread → ``channels``; dm/peer →
    // ``peers``); stub-type accounts fall back to the chip-list editor.
    //
    // The pre-rendered chip-list mount-site stays in the row HTML (per
    // ``_renderRoutingRow``); when the dropdown path is taken the slot
    // is wholesale replaced and a per-slot ``_routingMatchValues``
    // getter is installed for the collect-path bridge.
    function _wireRoutingMatchChiplist(rowEl) {
      var slot = rowEl.querySelector('.connector-routing-match-chiplist');
      if (!slot) return;
      var scopeEl = rowEl.querySelector('[data-routing-scope]');
      var scope = scopeEl ? scopeEl.value : '';
      // Read the initial committed match values from the pre-rendered
      // chip-list (``_renderRoutingRow`` emits a ``.chip`` per seeded
      // match value; the input is ignored).
      var initialValues = [];
      var seededChips = slot.querySelectorAll('.chip');
      for (var si = 0; si < seededChips.length; si++) {
        var chip = seededChips[si];
        var label = '';
        for (var sn = 0; sn < chip.childNodes.length; sn++) {
          var node = chip.childNodes[sn];
          if (node.nodeType === 3) label += node.nodeValue;
        }
        label = (label || '').trim();
        if (label) initialValues.push(label);
      }
      var vocab = _vocabForAccount(account);
      _mountRoutingMatchEditor(slot, account, scope, initialValues, vocab, checkDirty);
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

    // M12 F4 L1 A2 — keyboard reorder via ArrowUp / ArrowDown.
    //
    // The keydown handler replicates the drag path's inline DOM mutation
    // (there is no shared reorder function — both paths mutate DOM order
    // directly and collectRoutingFromContainer reads querySelectorAll
    // result). Uses Array.indexOf on the live rows NodeList (NOT the
    // stale data-row attr) to find the current position. After
    // insertBefore the moved handle receives focus (insertBefore drops
    // focus to <body> otherwise). A persistent visually-hidden
    // aria-live="polite" region announces the new position; at
    // boundaries it announces "already first/last" rather than silently
    // no-op'ing.
    function _wireRoutingKeyboardReorder(rowEl) {
      var handle = rowEl.querySelector('[data-routing-drag-handle]');
      if (!handle) return;
      handle.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
        e.preventDefault();
        var parent = rowEl.parentNode;
        if (!parent) return;
        var rows = Array.prototype.slice.call(
          parent.querySelectorAll('tr.connector-routing-row')
        );
        var idx = rows.indexOf(rowEl);
        if (idx === -1) return;
        var liveRegion = section.querySelector('[data-routing-live-region]');
        if (e.key === 'ArrowUp') {
          if (idx === 0) {
            if (liveRegion) liveRegion.textContent = 'Rule is already first';
            return;
          }
          parent.insertBefore(rowEl, rows[idx - 1]);
        } else {
          if (idx === rows.length - 1) {
            if (liveRegion) liveRegion.textContent = 'Rule is already last';
            return;
          }
          parent.insertBefore(rowEl, rows[idx + 1].nextSibling);
        }
        checkDirty();
        handle.focus();
        if (liveRegion) {
          var updatedRows = Array.prototype.slice.call(
            parent.querySelectorAll('tr.connector-routing-row')
          );
          var newPos = updatedRows.indexOf(rowEl) + 1;
          liveRegion.textContent = 'Rule moved to position ' + newPos + ' of ' + updatedRows.length;
        }
      });
    }

    function _wireRoutingRow(rowEl) {
      _wireRoutingMatchChiplist(rowEl);
      _wireRoutingDragHandle(rowEl);
      _wireRoutingDropTarget(rowEl);
      _wireRoutingKeyboardReorder(rowEl);
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
      //
      // M11 F3 L6b: scope change re-mounts the row's match-value editor
      // because the API axis (and therefore the dropdown's data source)
      // depends on the row's scope. Previous match values are CLEARED on
      // scope change — the simpler semantics; ids belonging to the
      // previous axis are no longer valid against the new axis.
      tbody.addEventListener('change', function (e) {
        var t = e.target;
        if (!t) return;
        if (t.hasAttribute && t.hasAttribute('data-routing-scope')) {
          var rowEl = t.closest && t.closest('tr.connector-routing-row');
          if (rowEl) {
            var slot = rowEl.querySelector('.connector-routing-match-chiplist');
            if (slot) {
              var vocab = _vocabForAccount(account);
              _mountRoutingMatchEditor(slot, account, t.value, [], vocab, checkDirty);
            }
          }
          checkDirty();
          return;
        }
        if (t.hasAttribute && t.hasAttribute('data-routing-agent')) {
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
      //
      // M11 F3 L6b: when the row's match cell is mounted as the
      // dropdown component (Discord-type accounts), the per-slot
      // ``_routingMatchValues`` getter is the canonical bridge — the
      // dropdown's chip DOM shape differs structurally from the
      // chip-list editor's, so falling through to the text-node walk
      // would mis-read dropdown chips. The chip-list fallback path
      // does NOT install the getter; collect path falls through.
      var matchValues = [];
      if (matchEl) {
        if (typeof matchEl._routingMatchValues === 'function') {
          var vals = matchEl._routingMatchValues() || [];
          for (var vi = 0; vi < vals.length; vi++) {
            var vStr = (vals[vi] == null) ? '' : String(vals[vi]);
            if (vStr) matchValues.push(vStr);
          }
        } else {
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
    html += '<h2 class="section-title">Attached agents</h2>';
    html += '<div class="connector-attached-agents-list" ' +
            'data-testid="connector-attached-agents-list">' +
            '<em class="form-hint">Loading…</em>' +
            '</div>';
    html += '</div>';
    return html;
  }

  function renderAttachedAgentsList(container, rows, account, checkDirty, recaptureSnapshot) {
    // M11 F1 L6 — table headers consult the per-type vocabulary so a
    // Discord-type account renders "Users" / "Channels" instead of
    // the substrate's neutral "Peers" / "Channels". The per-row
    // ``_renderAxis`` calls do not vary by type — the empty-list
    // copy ("DMs only" / "none") remains shared across types.
    //
    // M11 F9 L5 — signature extended with ``checkDirty`` /
    // ``recaptureSnapshot`` so the per-row detach click handler can
    // chain into ``fetchAttachedAgents`` (which itself consumes those
    // params to re-snapshot the dirty-tracker baseline after re-fetch).
    // Both are forwarded verbatim from ``fetchAttachedAgents``.
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
      // Cycle-2 fix (Bug 5): post-L3 each entry is a structured-tuple
      // dict (peers: ``{id, dm_allowed}``; channels:
      // ``{guild_id, channel_id}``; roles: ``{guild_id, role_id}``).
      // ``String({})`` returns ``"[object Object]"`` — unwrap to the
      // id field per axis, falling back to bare-string for legacy
      // flat-id payloads. Label resolution lives in the hierarchical
      // editor's per-mount cache (``_labelFor``) which is out of scope
      // here; the compact attached-agents table renders raw ids by
      // design (operator can click through to the agent to see full
      // chips with labels).
      var parts = '';
      for (var ci = 0; ci < value.length; ci++) {
        var entry = value[ci];
        var id = '';
        if (entry && typeof entry === 'object') {
          if (axis === 'peers') id = entry.id;
          else if (axis === 'channels') id = entry.channel_id;
          else if (axis === 'roles') id = entry.role_id;
          else id = entry.id || '';
          id = String(id == null ? '' : id);
        } else {
          id = String(entry);
        }
        parts += '<span class="chip">' + escapeHtml(id) + '</span>';
      }
      return parts;
    }

    var html = '<table class="connector-attached-agents-table" ' +
               'data-testid="connector-attached-agents-table">';
    html += '<thead><tr>' +
            '<th>Agent</th>' +
            '<th>' + escapeHtml(_capitalize(vocab.peers)) + '</th>' +
            '<th>' + escapeHtml(_capitalize(vocab.channels)) + '</th>' +
            '<th aria-label="Actions"></th>' +
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
      // M11 F9 L5 — per-row Detach button. The click handler issues
      // DELETE against the agent-side resource, re-fetches on success,
      // and dispatches ``connector-agent-detached`` for the grid badge
      // (handler installed at studio.js init).
      html += '<td class="connector-attached-agent-actions">' +
              '<button type="button" class="btn-link-danger connector-attached-agent-detach-btn" ' +
              'data-testid="connector-attached-agent-detach-' + escapeAttr(name) + '" ' +
              'data-agent-name="' + escapeAttr(name) + '" ' +
              'data-account-id="' + escapeAttr(account.id) + '">Detach</button>' +
              '</td>';
      html += '</tr>';
    }
    html += '</tbody></table>';
    listEl.innerHTML = html;

    // M11 F9 L5 — wire detach buttons. Per-button IIFE captures ``btn``
    // for each closure (avoids the loop-var pitfall under ``var``).
    var detachBtns = listEl.querySelectorAll('.connector-attached-agent-detach-btn');
    for (var b = 0; b < detachBtns.length; b++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          var agentName = btn.dataset.agentName;
          var accountId = btn.dataset.accountId;
          if (!agentName || !accountId) return;
          btn.disabled = true;
          btn.textContent = 'Detaching…';
          var url = '/api/agents/' + encodeURIComponent(agentName) +
                    '/connectors/' + encodeURIComponent(accountId);
          fetch(url, {method: 'DELETE'})
            .then(function (resp) {
              if (!resp.ok) {
                btn.disabled = false;
                btn.textContent = 'Detach';
                // Inline error — append a row-level error message so
                // the operator can re-click. No toast system in scope
                // (matches F8-era convention).
                var errListEl = container.querySelector(
                  '[data-testid="connector-attached-agents-list"]'
                );
                if (errListEl) {
                  var errEl = document.createElement('div');
                  errEl.className = 'form-hint connector-attached-agent-detach-error';
                  errEl.textContent = 'Detach failed (HTTP ' + resp.status +
                                      '). Click Detach again to retry.';
                  errListEl.appendChild(errEl);
                }
                return;
              }
              // Success: re-fetch the section (re-renders with new row
              // set + re-snapshots the dirty-tracker baseline), then
              // dispatch the CustomEvent so the Connectors grid (if
              // mounted) refreshes its agent-count badge.
              fetchAttachedAgents(container, account, checkDirty, recaptureSnapshot);
              // TODO(routine-maintenance): see the matching TODO above
              // — F4 R13 studio-event-bus lift candidate; M11 F9 L6
              // will refactor this inline dispatch + the matching
              // connectors-tab.js listener into the shared bus.
              App.studio.eventBus.emit('connector-agent-detached', {
                agent_name: agentName,
                account_id: accountId,
              });
            })
            .catch(function (e) {
              btn.disabled = false;
              btn.textContent = 'Detach';
              var errListEl = container.querySelector(
                '[data-testid="connector-attached-agents-list"]'
              );
              if (errListEl) {
                var errEl = document.createElement('div');
                errEl.className = 'form-hint connector-attached-agent-detach-error';
                errEl.textContent = 'Detach failed (network error: ' +
                                    escapeHtml(e && e.message ? e.message : String(e)) +
                                    '). Click Detach again to retry.';
                errListEl.appendChild(errEl);
              }
            });
        });
      })(detachBtns[b]);
    }
  }

  function fetchAttachedAgents(container, account, checkDirty, recaptureSnapshot) {
    // M11 F1 L6 — accept the full ``account`` object (not just the
    // id) so ``renderAttachedAgentsList`` can consult the per-type
    // vocabulary for the table-header text. ``account.id`` drives the
    // fetch URL; ``account.type`` drives the vocabulary lookup.
    var accountId = account && account.id;
    fetch('/api/connectors/' + encodeURIComponent(accountId) + '/attached-agents')
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
        renderAttachedAgentsList(container, rows, account, checkDirty, recaptureSnapshot);
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

  // M11 F13 L4: populate the inference-provider dropdown from
  // /api/providers. Mirrors the routing-default-agent dropdown pattern —
  // render-with-placeholder, fetch, populate, preserve-stale-as-disabled.
  // Re-snapshot after population so the populated form is the dirty
  // baseline (otherwise the operator's first edit would compare against
  // a placeholder-only baseline that no longer exists in the DOM).
  function populateInferenceProviderDropdown(container, account, checkDirty, recaptureSnapshot) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var sel = container.querySelector('[data-testid="connector-config-inference-provider-select"]');
    if (!sel) return;  // rows hidden under always_listen=false on render, OR not in this render path
    var currentValue = (account && account.config && account.config.inference_provider_config_id) || '';
    fetch('/api/providers')
      .then(function (resp) { return resp.ok ? resp.json() : []; })
      .then(function (providers) {
        if (!Array.isArray(providers)) providers = [];
        // Stable display order — name asc.
        providers.sort(function (a, b) {
          return String(a.name || '').localeCompare(String(b.name || ''));
        });
        var html = '';
        html += '<option value=""' + (currentValue === '' ? ' selected' : '') +
                '>— Use routed agent’s LLM —</option>';
        var matchedPersisted = false;
        for (var i = 0; i < providers.length; i++) {
          var p = providers[i];
          var pid = String(p.id || '');
          var pname = String(p.name || pid);
          if (pid === currentValue) matchedPersisted = true;
          html += '<option value="' + escapeAttr(pid) + '"' +
                  (pid === currentValue ? ' selected' : '') + '>' +
                  escapeHtml(pname) + '</option>';
        }
        // Stale-id preservation — keep the persisted value visible (and
        // selected) as a disabled option so the operator sees their
        // original choice and that it's no longer valid. Mirrors
        // populateRoutingAgentDropdowns's stale-selection snippet.
        if (currentValue && !matchedPersisted) {
          html += '<option value="' + escapeAttr(currentValue) + '" selected disabled>' +
                  escapeHtml(currentValue) + ' (provider deleted)</option>';
        }
        sel.innerHTML = html;
        if (typeof recaptureSnapshot === 'function') recaptureSnapshot();
        if (typeof checkDirty === 'function') checkDirty();
      })
      .catch(function () {
        // Network / 5xx — leave the placeholder-only options in place.
        // The operator sees the empty-state placeholder; they can save
        // (which writes null + falls through to routed-agent's LLM).
      });
  }

  // M11 F13 L4 (model-dropdown enhancement): wire the inference-provider
  // select's change handler to repopulate the inference-model select from
  // /api/providers/{providerId}/models. Also populates immediately for the
  // persisted provider (if any) so the model list appears on initial load.
  // Mirrors studio.js fetchModelsForProvider — handles the case where the
  // operator's previously-typed model is no longer enumerable by surfacing
  // it as "{value} (custom)" so the value survives.
  var _connectorModelsFetchController = null;
  var _connectorModelsActiveProviderId = null;
  function wireInferenceModelRepopulate(container, account, checkDirty, recaptureSnapshot) {
    var providerSel = container.querySelector('[data-testid="connector-config-inference-provider-select"]');
    if (!providerSel) return;
    providerSel.addEventListener('change', function () {
      populateInferenceModelDropdown(container, providerSel.value, null, checkDirty, recaptureSnapshot);
    });
    // Initial populate for the persisted provider so the model list is
    // visible on mount (otherwise the operator sees "Select a provider
    // first" until they change the provider, which is confusing when one
    // is already set).
    var persistedProviderId = (account && account.config && account.config.inference_provider_config_id) || '';
    var persistedModel = (account && account.config && account.config.inference_model) || '';
    if (persistedProviderId) {
      populateInferenceModelDropdown(container, persistedProviderId, persistedModel, checkDirty, recaptureSnapshot);
    }
  }

  function populateInferenceModelDropdown(container, providerId, persistedModel, checkDirty, recaptureSnapshot) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var sel = container.querySelector('[data-testid="connector-config-inference-model-select"]');
    if (!sel) return;
    // Carry-forward the currently-selected model so we can re-surface it
    // (a) if the persisted value isn't in the fetched list (as "(custom)"),
    // or (b) if the operator typed it before the provider switched.
    var currentVal = persistedModel != null ? persistedModel : sel.value;

    // Cancel any in-flight fetch from a prior provider selection (mirrors
    // studio.js race-guard so a slow earlier response doesn't clobber a
    // fresh later one).
    if (_connectorModelsFetchController) {
      try { _connectorModelsFetchController.abort(); } catch (_) { /* noop */ }
    }
    _connectorModelsFetchController = (typeof AbortController !== 'undefined')
      ? new AbortController()
      : null;
    _connectorModelsActiveProviderId = providerId;
    var fetchProviderId = providerId;
    var fetchSignal = _connectorModelsFetchController ? _connectorModelsFetchController.signal : undefined;

    if (!providerId) {
      // Provider cleared back to "— Use routed agent's LLM —" → model is
      // moot. Replace with "Select a provider first" disabled placeholder.
      // Do NOT recapture the snapshot — the populate here is a side effect
      // of the operator's provider-clear edit, and the dirty-tracker must
      // still see the change vs the persisted baseline so Save stays enabled.
      // Clear the value to null so the snapshot serializes as null (matches
      // the collectFormData null-write rule).
      sel.innerHTML = '<option value="" disabled selected>Select a provider first</option>';
      sel.value = '';
      // Dispatch a synthetic change so the general change listener fires
      // checkDirty against the persisted baseline (we don't call checkDirty
      // ourselves to avoid races with concurrent async populates on mount).
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }

    // Loading state.
    sel.innerHTML = '<option value="" disabled selected>Loading models…</option>';

    fetch('/api/providers/' + encodeURIComponent(providerId) + '/models', {
      signal: fetchSignal,
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Failed');
        return r.json();
      })
      .then(function (models) {
        // Drop the response if the user switched providers mid-flight.
        if (_connectorModelsActiveProviderId !== fetchProviderId) return;
        if (!Array.isArray(models)) models = [];
        var html = '';
        html += '<option value=""' + (currentVal ? '' : ' selected') + '>— No model —</option>';
        var matched = false;
        for (var i = 0; i < models.length; i++) {
          var modelId = models[i].id || models[i].name;
          if (modelId == null) continue;
          var sid = String(modelId);
          if (sid === currentVal) matched = true;
          html += '<option value="' + escapeAttr(sid) + '"' +
                  (sid === currentVal ? ' selected' : '') + '>' +
                  escapeHtml(sid) + '</option>';
        }
        // Preserve a typed-but-not-enumerated value as "(custom)" — same
        // pattern as studio.js for chat. Operator's saved string is never
        // silently wiped just because the provider can't list it (e.g.,
        // OpenAI/Anthropic don't enumerate, or an Ollama model isn't
        // pulled locally yet — operator may pull it later).
        if (currentVal && !matched) {
          html += '<option value="' + escapeAttr(currentVal) + '" selected>' +
                  escapeHtml(currentVal) + ' (custom)</option>';
        }
        sel.innerHTML = html;
        // Do NOT call checkDirty or recapture — the populate is a DOM-only
        // side effect (no user edit). On user-driven provider change, the
        // general change listener (wired in wireEditorEvents) already fires
        // checkDirty against the persisted baseline. On initial mount,
        // there's no edit to track. Calling checkDirty here introduces a
        // race against concurrent async populates (provider + fetchAttachedAgents).
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        if (_connectorModelsActiveProviderId !== fetchProviderId) return;
        // Network / 5xx — surface a clear failure state but preserve the
        // persisted value as a disabled-selected option so the operator's
        // saved choice is still visible. They can still pick "— No model —"
        // to clear it.
        var failHtml = '<option value="" disabled>Failed to load models</option>';
        if (currentVal) {
          failHtml += '<option value="' + escapeAttr(currentVal) + '" selected>' +
                      escapeHtml(currentVal) + ' (saved)</option>';
        } else {
          failHtml = '<option value="" disabled selected>Failed to load models</option>';
        }
        sel.innerHTML = failHtml;
      });
  }

  function wirePairingEvents(container, account, callbacks) {
    var btn = container.querySelector('.connector-pairing-generate-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var originalHtml = btn.innerHTML;
      btn.disabled = true;
      btn.textContent = 'Generating…';
      fetch('/api/connectors/' + encodeURIComponent(account.id) + '/pairing-code', {
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

  // M11 F3 L6a — per-axis allowlist editor mount dispatch.
  //
  // For each allowlist axis, consult the per-type connector form
  // registry: if the account's type entry exposes a
  // ``renderDiscoverableDropdown`` hook, mount the live-data dropdown
  // component for that axis; otherwise fall back to the chip-list
  // editor (the stub-type / no-entry regression contract).
  //
  // Storage axis ``'guilds'`` translates to API axis ``'groups'`` (per
  // the L3 ``DiscoverableEntities`` shape) before invoking the hook.
  // The other three axes (``peers``, ``channels``, ``roles``) pass
  // through unchanged.
  //
  // Dropdown path installs a per-slot ``_allowlistValues`` getter that
  // returns the current id array — the collect-path and snapshot-path
  // bridge for dropdown-driven values (whose ``.chip`` DOM shape is
  // structurally distinct from the chip-list editor and cannot be
  // read via the text-node walk). The chip-list fallback does NOT
  // install the getter; the collect path falls through to the
  // existing text-node walk.
  // M11 F12 L4 — per-storage-axis structured-tuple shape:
  //   peers    → {id, dm_allowed}        (valueShape: 'peer')
  //   channels → {guild_id, channel_id}  (valueShape: 'channel')
  //   roles    → {guild_id, role_id}     (valueShape: 'role')
  //   guilds   → str                     (valueShape: 'flat')
  // The dropdown component understands ``valueShape`` directly; the
  // stub fallback chip-list editor speaks flat-string ids, so the
  // _mountAllowlistAxisEditor wraps/unwraps at the fallback boundary.
  var _AXIS_VALUE_SHAPE = {
    peers: 'peer',
    channels: 'channel',
    roles: 'role',
    guilds: 'flat'
  };

  function _entryIdForAxis(entry, storageAxis) {
    if (entry == null) return '';
    if (storageAxis === 'peers') {
      return (entry && typeof entry === 'object') ? String(entry.id || '') : String(entry);
    }
    if (storageAxis === 'channels') {
      return (entry && typeof entry === 'object') ? String(entry.channel_id || '') : String(entry);
    }
    if (storageAxis === 'roles') {
      return (entry && typeof entry === 'object') ? String(entry.role_id || '') : String(entry);
    }
    return String(entry);
  }

  function _wrapFlatForAxis(id, storageAxis) {
    // Wrap a bare id string from the stub chip-list editor into the
    // structured-tuple shape. The stub path has no entity context so
    // guild_id falls back to null (legacy-permissive — surfaces the
    // legacy indicator on the chip post-mount).
    var s = (id == null) ? '' : String(id);
    if (!s) return null;
    // M11 F17 L8 (Leg D): bare ``{id}`` — dm_allowed retired at v28.
    if (storageAxis === 'peers') return { id: s };
    if (storageAxis === 'channels') return { guild_id: null, channel_id: s };
    if (storageAxis === 'roles') return { guild_id: null, role_id: s };
    return s;
  }

  function _mountAllowlistAxisEditor(slotEl, account, storageAxis, currentValues, vocab, checkDirty) {
    if (!slotEl) return;
    var valueShape = _AXIS_VALUE_SHAPE[storageAxis] || 'flat';
    var state = { values: (currentValues || []).slice() };
    var registry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
    var entry = (registry && account && account.type) ? registry.get(account.type) : null;
    if (entry && typeof entry.renderDiscoverableDropdown === 'function') {
      var apiAxis = (storageAxis === 'guilds') ? 'groups' : storageAxis;
      var dropdownEl = entry.renderDiscoverableDropdown(
        account,
        apiAxis,
        state.values,
        vocab,
        function onChange(newValues) {
          state.values = (newValues || []).slice();
          if (typeof checkDirty === 'function') checkDirty();
        },
        // M11 F12 L4 — opt into structured-tuple shape per axis.
        { valueShape: valueShape }
      );
      if (dropdownEl) {
        slotEl.innerHTML = '';
        slotEl.appendChild(dropdownEl);
        slotEl._allowlistValues = function () { return state.values.slice(); };
        return;
      }
    }
    // Fallback: chip-list (preserves stub-type / no-entry behavior).
    // M11 F12 L4 — the stub chip-list editor speaks flat-string ids;
    // unwrap structured tuples for display, then install a getter that
    // re-wraps on collect. Chip-list edits are observed via the
    // _allowlistValues getter so the collect path reads the wrapped
    // shape without round-tripping through the chip DOM.
    var helpers = window.App.adminFormHelpers;
    slotEl.innerHTML = '';
    var flatIds = [];
    for (var fi = 0; fi < state.values.length; fi++) {
      flatIds.push(_entryIdForAxis(state.values[fi], storageAxis));
    }
    var chiplist = _buildAllowlistChipList(storageAxis, flatIds);
    slotEl.appendChild(chiplist);
    if (helpers && helpers.wireChipListEditor) {
      helpers.wireChipListEditor(chiplist, { onChange: checkDirty });
    }
    // M11 F12 L4 — install the bridge getter for chip-list mode too so
    // the structured-tuple wrapping happens at read time (the chip DOM
    // still stores plain ids; the wrap synthesizes guild_id=null /
    // dm_allowed=false defaults at collect time).
    if (valueShape !== 'flat') {
      slotEl._allowlistValues = function () {
        var out = [];
        var chips = chiplist.querySelectorAll('.chip');
        for (var i = 0; i < chips.length; i++) {
          var label = '';
          for (var j = 0; j < chips[i].childNodes.length; j++) {
            var n = chips[i].childNodes[j];
            if (n.nodeType === 3) label += n.nodeValue;
          }
          label = (label || '').trim();
          if (label) {
            var wrapped = _wrapFlatForAxis(label, storageAxis);
            if (wrapped) out.push(wrapped);
          }
        }
        return out;
      };
    }
    // Guilds (valueShape === 'flat') leaves no getter; collect path
    // falls through to the text-node walk in
    // collectAllowlistFromContainer (returns bare strings — matches the
    // storage shape).
  }

  // M11 F12 L5 — hierarchical Server-as-parent allowlist editor mount.
  //
  // Renders the Servers (guilds) chip-list using the discoverable
  // dropdown as a server-row generator; below each server row,
  // renders 2 nested sub-chiplists (channels filtered to the row's
  // guild_id; roles filtered to the row's guild_id).
  //
  // Wildcard ``"*"`` sentinel rendering: when a server row has no
  // explicit channel narrowing (the channel sub-list is empty for
  // this guild_id), the UI renders a single "(all channels)" sentinel
  // chip. Same for roles. Per the AC: the sentinel is rendered on
  // ANY empty server row regardless of pre-/post-L5 origin (operator
  // sees a consistent UI state).
  //
  // Storage-write-time sentinel insertion: when a server is added via
  // the add-server dropdown, the corresponding ``{guild_id, channel_id:
  // "*"}`` and ``{guild_id, role_id: "*"}`` entries are inserted into
  // the in-memory state immediately, so the save payload carries the
  // sentinel explicitly. When the operator adds an explicit channel
  // under a server, the sentinel is removed (replaced by the explicit
  // chip); when the operator removes the last explicit channel, the
  // sentinel is re-inserted.
  //
  // The Servers slot installs a single ``_allowlistValues`` getter at
  // mount time that returns the FULL hierarchical state as a flat
  // ``{guilds, channels, roles}`` triple; ``collectAllowlistFromContainer``
  // reads it via a hierarchical-getter contract (separate field).
  function _mountAllowlistHierarchicalEditor(
    slotEl, account, guildsInit, channelsInit, rolesInit, vocab, checkDirty
  ) {
    if (!slotEl) return;

    // In-memory state. The state shape mirrors the storage shape so
    // collect-path emit is a direct projection.
    var state = {
      guilds: (guildsInit || []).slice(),
      channels: (channelsInit || []).map(function (c) {
        return (c && typeof c === 'object') ? Object.assign({}, c) : c;
      }),
      roles: (rolesInit || []).map(function (r) {
        return (r && typeof r === 'object') ? Object.assign({}, r) : r;
      })
    };

    function _emitDirty() {
      if (typeof checkDirty === 'function') checkDirty();
    }

    // Per-editor label cache. Mirrors the ``_labelCache`` pattern in
    // ``connectors-tab.js`` (lines ~271-304) so guild_id → friendly
    // server name resolution works on render without depending on the
    // sibling discoverable-dropdown's internal entity cache. The cache
    // is populated lazily on first ``_rerender`` and triggers a
    // single re-render once it resolves so server-row headers swap
    // raw ids for friendly labels without flicker on subsequent
    // re-renders.
    //
    // Cycle-2 fix: cache is axis-nested (``{axis: {id: label}}``)
    // because Discord assigns identical snowflake IDs to a guild and
    // its ``@everyone`` role — a flat ``{id: label}`` dict silently
    // overwrites one with the other (server-row header would show
    // ``"@everyone"`` instead of the guild name). ``_labelFor`` now
    // requires an explicit axis so callers can't trip the collision.
    var _labelCache = null;
    var _labelCachePromise = null;

    // Cycle-3 fix (Bug 7): the lazy ``_labelCache`` populates on first
    // ``_rerender`` — but if Test Connection hasn't been run yet the
    // ``/discoverable-entities`` GET returns 404 and the cache fills
    // with empty buckets. Without invalidation, every subsequent
    // ``_ensureLabelCache`` call short-circuits to that empty-resolved
    // promise and server-row headers stay raw guild IDs forever even
    // after the operator clicks Test Connection.
    //
    // Mirror the discoverable-dropdown self-detach pattern (see
    // ``discoverable-dropdown.js`` lines 814-848): listen for
    // ``connector-pool-warmed`` (fires when Test Connection warms the
    // pool) and ``connector-discoverable-refresh-requested`` (fires
    // when the operator clicks the section-level Refresh banner button).
    // On each event matching this editor's accountId, reset the cache
    // and re-fetch; once the promise resolves, trigger ``_rerender``
    // so server-row headers swap raw IDs for friendly labels. Self-
    // detaches on the next event after the editor's slot has been
    // removed from the DOM (small leak surface, accepted — same
    // posture as the dropdown's handlers).
    function _invalidateAndRefresh() {
      _labelCache = null;
      _labelCachePromise = null;
      _ensureLabelCache().then(function () {
        if (!slotEl || !document.body.contains(slotEl)) return;
        _rerender();
      });
    }
    var _poolWarmedHandler = function (event) {
      if (!slotEl || !document.body.contains(slotEl)) {
        document.removeEventListener('connector-pool-warmed', _poolWarmedHandler);
        document.removeEventListener(
          'connector-discoverable-refresh-requested', _refreshRequestedHandler
        );
        return;
      }
      if (event && event.detail && account
          && event.detail.accountId === account.id) {
        _invalidateAndRefresh();
      }
    };
    var _refreshRequestedHandler = function (event) {
      if (!slotEl || !document.body.contains(slotEl)) {
        document.removeEventListener('connector-pool-warmed', _poolWarmedHandler);
        document.removeEventListener(
          'connector-discoverable-refresh-requested', _refreshRequestedHandler
        );
        return;
      }
      if (event && event.detail && account
          && event.detail.accountId === account.id) {
        _invalidateAndRefresh();
      }
    };
    App.studio.eventBus.on('connector-pool-warmed', _poolWarmedHandler);
    App.studio.eventBus.on(
      'connector-discoverable-refresh-requested', _refreshRequestedHandler
    );

    function _ensureLabelCache() {
      if (_labelCachePromise) return _labelCachePromise;
      if (!account || !account.id) {
        _labelCache = { peers: {}, channels: {}, groups: {}, roles: {} };
        _labelCachePromise = Promise.resolve(_labelCache);
        return _labelCachePromise;
      }
      var url = '/api/connectors/' +
        encodeURIComponent(account.id) +
        '/discoverable-entities';
      _labelCachePromise = fetch(url).then(function (response) {
        if (!response.ok) {
          _labelCache = { peers: {}, channels: {}, groups: {}, roles: {} };
          return _labelCache;
        }
        return response.json().then(function (body) {
          var map = { peers: {}, channels: {}, groups: {}, roles: {} };
          var ents = (body && body.entities) || {};
          var axes = ['peers', 'channels', 'groups', 'roles'];
          for (var a = 0; a < axes.length; a++) {
            var axisKey = axes[a];
            var list = ents[axisKey] || [];
            for (var i = 0; i < list.length; i++) {
              var e = list[i];
              if (e && e.id && e.label) map[axisKey][String(e.id)] = e.label;
            }
          }
          _labelCache = map;
          return _labelCache;
        });
      }).catch(function (err) {
        _labelCache = { peers: {}, channels: {}, groups: {}, roles: {} };
        try { console.error('connector-editor label-cache fetch failed:', err); }
        catch (logErr) { /* console missing */ }
        return _labelCache;
      });
      return _labelCachePromise;
    }

    function _labelFor(id, axis) {
      if (_labelCache && id != null && axis) {
        var bucket = _labelCache[axis];
        if (bucket) {
          var hit = bucket[String(id)];
          if (hit) return hit;
        }
      }
      return String(id);
    }

    function _channelsForGuild(guildId) {
      var out = [];
      for (var i = 0; i < state.channels.length; i++) {
        var c = state.channels[i];
        if (c && c.guild_id === guildId) out.push(c);
      }
      return out;
    }

    function _rolesForGuild(guildId) {
      var out = [];
      for (var i = 0; i < state.roles.length; i++) {
        var r = state.roles[i];
        if (r && r.guild_id === guildId) out.push(r);
      }
      return out;
    }

    function _hasExplicitChannel(guildId) {
      var entries = _channelsForGuild(guildId);
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].channel_id !== '*') return true;
      }
      return false;
    }

    function _hasExplicitRole(guildId) {
      var entries = _rolesForGuild(guildId);
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].role_id !== '*') return true;
      }
      return false;
    }

    function _ensureChannelSentinel(guildId) {
      if (!_hasExplicitChannel(guildId)) {
        var hasSentinel = false;
        for (var i = 0; i < state.channels.length; i++) {
          if (state.channels[i].guild_id === guildId
              && state.channels[i].channel_id === '*') {
            hasSentinel = true; break;
          }
        }
        if (!hasSentinel) {
          state.channels.push({ guild_id: guildId, channel_id: '*' });
        }
      }
    }

    function _ensureRoleSentinel(guildId) {
      if (!_hasExplicitRole(guildId)) {
        var hasSentinel = false;
        for (var i = 0; i < state.roles.length; i++) {
          if (state.roles[i].guild_id === guildId
              && state.roles[i].role_id === '*') {
            hasSentinel = true; break;
          }
        }
        if (!hasSentinel) {
          state.roles.push({ guild_id: guildId, role_id: '*' });
        }
      }
    }

    function _removeChannelSentinel(guildId) {
      state.channels = state.channels.filter(function (c) {
        return !(c.guild_id === guildId && c.channel_id === '*');
      });
    }

    function _removeRoleSentinel(guildId) {
      state.roles = state.roles.filter(function (r) {
        return !(r.guild_id === guildId && r.role_id === '*');
      });
    }

    function _cascadeDeleteServer(guildId) {
      state.guilds = state.guilds.filter(function (g) { return g !== guildId; });
      state.channels = state.channels.filter(function (c) {
        return c.guild_id !== guildId;
      });
      state.roles = state.roles.filter(function (r) {
        return r.guild_id !== guildId;
      });
    }

    function _onServerAdded(guildId) {
      if (state.guilds.indexOf(guildId) === -1) {
        state.guilds.push(guildId);
      }
      _ensureChannelSentinel(guildId);
      _ensureRoleSentinel(guildId);
      _emitDirty();
      _rerender();
    }

    function _onChannelAdded(guildId, channelId) {
      _removeChannelSentinel(guildId);
      var exists = false;
      for (var i = 0; i < state.channels.length; i++) {
        if (state.channels[i].guild_id === guildId
            && state.channels[i].channel_id === channelId) {
          exists = true; break;
        }
      }
      if (!exists) {
        state.channels.push({ guild_id: guildId, channel_id: channelId });
      }
      _emitDirty();
      _rerender();
    }

    function _onChannelRemoved(guildId, channelId) {
      state.channels = state.channels.filter(function (c) {
        return !(c.guild_id === guildId && c.channel_id === channelId);
      });
      _ensureChannelSentinel(guildId);
      _emitDirty();
      _rerender();
    }

    function _onRoleAdded(guildId, roleId) {
      _removeRoleSentinel(guildId);
      var exists = false;
      for (var i = 0; i < state.roles.length; i++) {
        if (state.roles[i].guild_id === guildId
            && state.roles[i].role_id === roleId) {
          exists = true; break;
        }
      }
      if (!exists) {
        state.roles.push({ guild_id: guildId, role_id: roleId });
      }
      _emitDirty();
      _rerender();
    }

    function _onRoleRemoved(guildId, roleId) {
      state.roles = state.roles.filter(function (r) {
        return !(r.guild_id === guildId && r.role_id === roleId);
      });
      _ensureRoleSentinel(guildId);
      _emitDirty();
      _rerender();
    }

    function _renderServerRow(guildId) {
      var row = document.createElement('div');
      row.className = 'connector-allowlist-server-row';
      row.setAttribute('data-guild-id', guildId);
      row.setAttribute(
        'data-testid', 'connector-allowlist-server-row-' + guildId
      );

      // Header: server name + remove button. Resolve guild_id → friendly
      // label via ``_labelCache`` (mirrors connectors-tab.js pattern); the
      // cache may not be populated yet on first render — ``_rerender``
      // kicks ``_ensureLabelCache`` and re-renders once it resolves.
      var header = document.createElement('div');
      header.className = 'connector-allowlist-server-row-header';
      var nameSpan = document.createElement('span');
      nameSpan.className = 'connector-allowlist-server-row-name';
      nameSpan.textContent = _labelFor(guildId, 'groups');
      header.appendChild(nameSpan);
      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'connector-allowlist-server-row-remove';
      removeBtn.setAttribute(
        'data-testid',
        'connector-allowlist-server-row-remove-' + guildId
      );
      removeBtn.setAttribute('aria-label', 'Remove server ' + _labelFor(guildId, 'groups'));
      removeBtn.textContent = '×';
      removeBtn.addEventListener('click', function () {
        _cascadeDeleteServer(guildId);
        _emitDirty();
        _rerender();
      });
      header.appendChild(removeBtn);
      row.appendChild(header);

      // Nested channels sub-chiplist for this guild_id.
      var channelsSubRow = document.createElement('div');
      channelsSubRow.className =
        'connector-allowlist-server-row-children connector-allowlist-channels-sub';
      var channelsLabel = document.createElement('span');
      channelsLabel.className = 'connector-allowlist-sub-label';
      channelsLabel.textContent = _capitalize(vocab.channels) + ':';
      channelsSubRow.appendChild(channelsLabel);

      // Wildcard sentinel chip ("(all channels)") renders when the
      // server row has no explicit channel narrowing. Explicit channel
      // chips are NOT rendered here — the mounted discoverable-dropdown
      // owns explicit chip rendering (with friendly labels + working
      // remove buttons) when it receives the entries as initial values.
      // Rendering them here too caused the L5 double-chip bug (one with
      // raw ID, one from the dropdown with friendly label).
      var channelsEntries = _channelsForGuild(guildId);
      for (var ci = 0; ci < channelsEntries.length; ci++) {
        var ce = channelsEntries[ci];
        if (ce.channel_id === '*') {
          var sentinelChip = document.createElement('span');
          sentinelChip.className =
            'chip connector-allowlist-channel-chip connector-allowlist-wildcard-sentinel';
          sentinelChip.setAttribute(
            'data-testid',
            'connector-allowlist-channels-wildcard-' + guildId
          );
          sentinelChip.textContent = '(all ' + vocab.channels + ')';
          // Sentinel chip is not directly removable — it disappears
          // when the operator adds an explicit channel.
          channelsSubRow.appendChild(sentinelChip);
        }
      }

      // Add-channel dropdown (server-scoped — pass guildId context).
      // The dropdown is also responsible for rendering explicit chips
      // (via its internal _renderChips) and for emitting removals when
      // the operator clicks a chip's × button — so the editor must
      // handle both additions AND removals from the onChange payload.
      var registry = (window.App && window.App.studio
          && window.App.studio.connectorFormRegistry) || null;
      var typeEntry = (registry && account && account.type)
          ? registry.get(account.type) : null;
      if (typeEntry && typeof typeEntry.renderDiscoverableDropdown === 'function') {
        var channelDropdown = typeEntry.renderDiscoverableDropdown(
          account, 'channels',
          channelsEntries.filter(function (c) { return c.channel_id !== '*'; }),
          vocab,
          function (newValues) {
            // Diff new vs old (excluding sentinel). Net-additions
            // become explicit channel adds; net-removals fire
            // ``_onChannelRemoved`` (the dropdown's chip × button is
            // the sole remove affordance post fix-cycle).
            var oldEntries = channelsEntries
              .filter(function (c) { return c.channel_id !== '*'; });
            var existingIds = {};
            for (var oi = 0; oi < oldEntries.length; oi++) {
              existingIds[oldEntries[oi].channel_id] = true;
            }
            var newSet = {};
            for (var ni = 0; ni < newValues.length; ni++) {
              var nv = newValues[ni];
              var nid = (nv && typeof nv === 'object')
                  ? nv.channel_id : String(nv);
              if (!nid) continue;
              newSet[nid] = true;
              if (!existingIds[nid]) _onChannelAdded(guildId, nid);
            }
            for (var ri = oldEntries.length - 1; ri >= 0; ri--) {
              var rid = oldEntries[ri].channel_id;
              if (!newSet[rid]) _onChannelRemoved(guildId, rid);
            }
          },
          { valueShape: 'channel', guildId: guildId }
        );
        if (channelDropdown) {
          channelDropdown.classList.add(
            'connector-allowlist-server-scoped-dropdown'
          );
          channelsSubRow.appendChild(channelDropdown);
        }
      }
      row.appendChild(channelsSubRow);

      // Nested roles sub-chiplist for this guild_id.
      var rolesSubRow = document.createElement('div');
      rolesSubRow.className =
        'connector-allowlist-server-row-children connector-allowlist-roles-sub';
      var rolesLabel = document.createElement('span');
      rolesLabel.className = 'connector-allowlist-sub-label';
      rolesLabel.textContent = _capitalize(vocab.roles) + ':';
      rolesSubRow.appendChild(rolesLabel);

      // Wildcard sentinel chip ("(all roles)") renders when the server
      // row has no explicit role narrowing. Explicit role chips are
      // owned by the dropdown (see channels comment above).
      var rolesEntries = _rolesForGuild(guildId);
      for (var ri = 0; ri < rolesEntries.length; ri++) {
        var re = rolesEntries[ri];
        if (re.role_id === '*') {
          var roleSentinelChip = document.createElement('span');
          roleSentinelChip.className =
            'chip connector-allowlist-role-chip connector-allowlist-wildcard-sentinel';
          roleSentinelChip.setAttribute(
            'data-testid',
            'connector-allowlist-roles-wildcard-' + guildId
          );
          roleSentinelChip.textContent = '(all ' + vocab.roles + ')';
          rolesSubRow.appendChild(roleSentinelChip);
        }
      }

      if (typeEntry && typeof typeEntry.renderDiscoverableDropdown === 'function') {
        var roleDropdown = typeEntry.renderDiscoverableDropdown(
          account, 'roles',
          rolesEntries.filter(function (r) { return r.role_id !== '*'; }),
          vocab,
          function (newValues) {
            // Diff new vs old (excluding sentinel). Net-additions →
            // ``_onRoleAdded``; net-removals → ``_onRoleRemoved`` (the
            // dropdown's chip × is the sole remove affordance post
            // fix-cycle, mirroring the channels handler above).
            var oldEntries = rolesEntries
              .filter(function (r) { return r.role_id !== '*'; });
            var existingIds = {};
            for (var oi = 0; oi < oldEntries.length; oi++) {
              existingIds[oldEntries[oi].role_id] = true;
            }
            var newSet = {};
            for (var ni = 0; ni < newValues.length; ni++) {
              var nv = newValues[ni];
              var nid = (nv && typeof nv === 'object')
                  ? nv.role_id : String(nv);
              if (!nid) continue;
              newSet[nid] = true;
              if (!existingIds[nid]) _onRoleAdded(guildId, nid);
            }
            for (var rri = oldEntries.length - 1; rri >= 0; rri--) {
              var rrid = oldEntries[rri].role_id;
              if (!newSet[rrid]) _onRoleRemoved(guildId, rrid);
            }
          },
          { valueShape: 'role', guildId: guildId }
        );
        if (roleDropdown) {
          roleDropdown.classList.add(
            'connector-allowlist-server-scoped-dropdown'
          );
          rolesSubRow.appendChild(roleDropdown);
        }
      }
      row.appendChild(rolesSubRow);

      return row;
    }

    function _rerender() {
      // Kick the label cache on first render so guild_id → friendly
      // server name resolution swaps in once the
      // ``/discoverable-entities`` fetch resolves. The cache populates
      // once per editor mount; the ``.then`` re-render only fires once
      // (the promise is memoized, so subsequent ``_rerender`` calls
      // reuse the resolved cache directly).
      if (_labelCache === null && _labelCachePromise === null) {
        _ensureLabelCache().then(function () { _rerender(); });
      }
      slotEl.innerHTML = '';

      // Add-server dropdown lives at the top of the slot.
      var addServerWrap = document.createElement('div');
      addServerWrap.className = 'connector-allowlist-add-server';
      var registry = (window.App && window.App.studio
          && window.App.studio.connectorFormRegistry) || null;
      var typeEntry = (registry && account && account.type)
          ? registry.get(account.type) : null;
      if (typeEntry && typeof typeEntry.renderDiscoverableDropdown === 'function') {
        // Cycle-2 fix (Bug 4): pass an empty currentValues array so
        // the dropdown's internal chiplist stays empty. Server-rows
        // below are the canonical representation of selected guilds;
        // letting the dropdown render its own chips on top produced
        // two visual representations per guild ("Constellation" chip
        // floating above the full server card). The onChange handler
        // still fires when the operator picks a server — we only
        // care about net-additions here (removals are handled by the
        // per-row × button on each server card, which calls
        // _cascadeDeleteServer directly).
        var serverDropdown = typeEntry.renderDiscoverableDropdown(
          account, 'groups',
          [],
          vocab,
          function (newValues) {
            var existing = {};
            for (var ei = 0; ei < state.guilds.length; ei++) {
              existing[state.guilds[ei]] = true;
            }
            // Net-additions become _onServerAdded(). Removals via
            // the dropdown's own × are not possible here because its
            // chiplist is empty — per-row × is the sole remove path.
            for (var ni = 0; ni < newValues.length; ni++) {
              var nv = newValues[ni];
              var nid = (typeof nv === 'object' && nv) ? String(nv) : String(nv);
              if (!existing[nid]) _onServerAdded(nid);
            }
          },
          { valueShape: 'flat' }
        );
        if (serverDropdown) {
          addServerWrap.appendChild(serverDropdown);
        }
      } else {
        // Fallback chip-list for stub types (no discoverable
        // dropdown). The chip-list mirrors the L4 behavior for the
        // guilds slot — operator types a guild_id; on commit, we
        // synthesize a server-added event.
        var fallbackChiplist = _buildAllowlistChipList('guilds', state.guilds);
        addServerWrap.appendChild(fallbackChiplist);
        var helpers = window.App.adminFormHelpers;
        if (helpers && helpers.wireChipListEditor) {
          helpers.wireChipListEditor(fallbackChiplist, {
            onChange: function () {
              // Re-read the chiplist, diff guilds, fire add/remove.
              var newGuilds = [];
              var chips = fallbackChiplist.querySelectorAll('.chip');
              for (var i = 0; i < chips.length; i++) {
                var label = '';
                for (var j = 0; j < chips[i].childNodes.length; j++) {
                  var n = chips[i].childNodes[j];
                  if (n.nodeType === 3) label += n.nodeValue;
                }
                label = (label || '').trim();
                if (label) newGuilds.push(label);
              }
              var oldSet = {};
              for (var oi = 0; oi < state.guilds.length; oi++) {
                oldSet[state.guilds[oi]] = true;
              }
              var newSet = {};
              for (var ni = 0; ni < newGuilds.length; ni++) {
                newSet[newGuilds[ni]] = true;
                if (!oldSet[newGuilds[ni]]) _onServerAdded(newGuilds[ni]);
              }
              for (var gi = state.guilds.length - 1; gi >= 0; gi--) {
                var gid = state.guilds[gi];
                if (!newSet[gid]) {
                  _cascadeDeleteServer(gid);
                  _emitDirty();
                }
              }
              _rerender();
            }
          });
        }
      }
      slotEl.appendChild(addServerWrap);

      // Per-server rows.
      var rowsWrap = document.createElement('div');
      rowsWrap.className = 'connector-allowlist-server-rows';
      rowsWrap.setAttribute(
        'data-testid', 'connector-allowlist-server-rows'
      );
      for (var gi = 0; gi < state.guilds.length; gi++) {
        // Pre-L5 empty-server-row rendering rule: render the sentinel
        // chip for ANY server row whose channels/roles list is empty
        // for that guild_id, regardless of pre-/post-L5 origin
        // (architect cycle-1 low-1 lock).
        _ensureChannelSentinel(state.guilds[gi]);
        _ensureRoleSentinel(state.guilds[gi]);
        rowsWrap.appendChild(_renderServerRow(state.guilds[gi]));
      }
      slotEl.appendChild(rowsWrap);
    }

    // Hierarchical getter contract: the Servers slot exposes a
    // ``_hierarchicalAllowlistValues`` getter that returns the full
    // {guilds, channels, roles} triple. ``collectAllowlistFromContainer``
    // reads this directly (separate path from the per-axis getter).
    slotEl._hierarchicalAllowlistValues = function () {
      return {
        guilds: state.guilds.slice(),
        channels: state.channels.slice(),
        roles: state.roles.slice()
      };
    };

    _rerender();
  }

  function wireAllowlistEvents(container, account, checkDirty) {
    // M10 F6 L7 HAT — chip-lists are always mounted. Empty lists are
    // valid and mean "unrestricted on this axis."
    //
    // M11 F12 L5 — the L4 flat 3-section layout (Channels / Guilds /
    // Roles as siblings) is replaced by a hierarchical Server-as-
    // parent layout: the Guilds (Servers) slot is the parent
    // organizer; channels + roles render as nested sub-chiplists
    // inside each server row. The mount-time function
    // ``_mountAllowlistHierarchicalEditor`` reads
    // ``account.config.allowlist.{guilds, channels, roles}`` and
    // builds the nested view; on save, the collect path reads
    // hierarchical state back via the slot getter.
    //
    // The peers slot still mounts as a flat chip-list (peers are not
    // server-scoped); the dm_admission select is unchanged.
    var allowlist = (account && account.config && account.config.allowlist) || null;
    var peersInit = (allowlist && Array.isArray(allowlist.peers)) ? allowlist.peers : [];
    var guildsInit = (allowlist && Array.isArray(allowlist.guilds)) ? allowlist.guilds : [];
    var channelsInit = (allowlist && Array.isArray(allowlist.channels)) ? allowlist.channels : [];
    var rolesInit = (allowlist && Array.isArray(allowlist.roles)) ? allowlist.roles : [];
    var peersSlot = container.querySelector('[data-allowlist-chiplist-slot="peers"]');
    var serversSlot = container.querySelector('[data-allowlist-chiplist-slot="guilds"]');
    var vocab = _vocabForAccount(account);

    _mountAllowlistAxisEditor(peersSlot, account, 'peers', peersInit, vocab, checkDirty);
    _mountAllowlistHierarchicalEditor(
      serversSlot, account, guildsInit, channelsInit, rolesInit, vocab, checkDirty
    );

    // M11 F12 L4 — per-peer DM toggle visibility wiring (recommended
    // path (b): CSS-toggle via parent class change). The dm_admission
    // <select> change handler toggles ``dm-admission-admin-approved``
    // on the peers section. CSS controls visibility — see studio.css.
    // Path (b) preserves checkbox state across mode flips: switching to
    // ``none`` / ``all`` HIDES the toggles without erasing dm_allowed
    // values, so flipping back to ``admin-approved`` restores them.
    var dmAdmissionSelect = container.querySelector(
        '[data-testid="connector-allowlist-dm-admission-select"]');
    var peersRow = container.querySelector(
        '[data-testid="connector-allowlist-peers-row"]');
    function _applyPeersDmClass(value) {
      if (!peersRow) return;
      var on = (value === 'admin-approved');
      peersRow.classList.toggle('dm-admission-admin-approved', on);
    }
    if (dmAdmissionSelect) {
      _applyPeersDmClass(dmAdmissionSelect.value);
      dmAdmissionSelect.addEventListener('change', function () {
        _applyPeersDmClass(dmAdmissionSelect.value);
        if (typeof checkDirty === 'function') checkDirty();
      });
    } else {
      // Defensive: defaults to admin-approved when select is absent
      // (matches collectAllowlistFromContainer's fallback at :3567).
      _applyPeersDmClass('admin-approved');
    }

    // F5 L6 HAT R5: wire the section-level banner (pre-probe vs
    // populated state + manual Refresh dispatch). The 4 axes' per-axis
    // Refresh buttons + pre-probe hints were removed from
    // ``discoverable-dropdown.js`` in the same round; the banner is the
    // single source of pool-warm signal + manual-refresh affordance.
    _wireAllowlistBanner(container, account);
  }

  // F5 L6 HAT R5: section-level banner wiring.
  //
  // The banner has two states:
  //   pre-probe  — no cached entities yet (404 from L4 GET); shows the
  //                "Run Test Connection" hint; Refresh button hidden.
  //   populated  — cached entities present (200 from L4 GET); shows
  //                "Last refreshed: {when}"; Refresh button visible.
  //
  // Initial state is the pessimistic pre-probe pose set by the markup.
  // On mount, we fire one L4 GET to discover the actual state without
  // forcing a refresh; the response (200 / 404 / 503) drives the
  // banner state. We also listen for the
  // ``connector-pool-warmed`` event (dispatched by Test
  // Connection's onResponse when the pool just warmed) so the banner
  // transitions in real time without another GET round-trip.
  //
  // The Refresh button dispatches
  // ``connector-discoverable-refresh-requested`` with
  // ``{ accountId }`` detail — all 4 mounted axis dropdowns listen and
  // re-fetch on a match. We also do a GET ourselves after the dispatch
  // (with a small delay) to refresh the banner's "Last refreshed"
  // timestamp; the dropdowns' own POST to /refresh updates the cache
  // and the subsequent GET reads the new timestamp.

  // M11 F17 L5: live status poll wiring.
  //
  // Polls ``GET /api/connectors/{id}/status`` every 3s (between 2–5s
  // per the design decision). Stops when the status indicator element
  // is removed from the DOM (``isConnected`` guard, mirroring the
  // allowlist banner's poolWarmedHandler pattern).
  //
  // State → LED class / label mapping:
  //   connected    → indicator-led--success / "Connected"
  //   connecting   → indicator-led--idle    / "Connecting…"
  //   disconnected → indicator-led--idle    / "Disconnected"
  //   error        → indicator-led--danger  / "Error"
  //
  // On error, the ``connector-live-status-error`` span receives the
  // ``last_error`` message and ``connector-live-status-error-link``
  // renders a clickable portal link (hidden when ``last_error_link``
  // is null).
  function _wireLiveStatus(container, account) {
    if (!container || !account || !account.id) return;
    var led = container.querySelector('.connector-live-status-led');
    var textEl = container.querySelector('[data-testid="connector-live-status"]');
    var errorWrap = container.querySelector('[data-testid="connector-live-status-error-wrap"]');
    var errorEl = container.querySelector('[data-testid="connector-live-status-error"]');
    var errorLink = container.querySelector('[data-testid="connector-live-status-error-link"]');
    if (!textEl) return;

    var _POLL_INTERVAL_MS = 3000;
    var _pollTimer = null;

    function _updateLed(state) {
      if (!led) return;
      led.classList.remove(
        'indicator-led--success',
        'indicator-led--warning',
        'indicator-led--danger',
        'indicator-led--idle'
      );
      if (state === 'connected') {
        led.classList.add('indicator-led--success');
      } else if (state === 'error') {
        led.classList.add('indicator-led--danger');
      } else {
        led.classList.add('indicator-led--idle');
      }
      led.setAttribute('data-state', state);
      led.setAttribute('aria-label', _stateLabel(state));
    }

    function _stateLabel(state) {
      if (state === 'connected') return 'Connected';
      if (state === 'connecting') return 'Connecting';
      if (state === 'error') return 'Error';
      return 'Disconnected';
    }

    function _stateText(state) {
      if (state === 'connected') return 'Connected';
      if (state === 'connecting') return 'Connecting…';
      if (state === 'error') return 'Error';
      return 'Disconnected';
    }

    function _applyStatus(body) {
      var state = (body && body.state) || 'disconnected';
      _updateLed(state);
      textEl.textContent = _stateText(state);
      if (state === 'error' && body.last_error) {
        if (errorEl) errorEl.textContent = body.last_error;
        if (errorLink) {
          if (body.last_error_link) {
            errorLink.href = body.last_error_link;
            errorLink.textContent = 'Fix in Developer Portal';
            errorLink.removeAttribute('hidden');
          } else {
            errorLink.setAttribute('hidden', '');
          }
        }
        if (errorWrap) errorWrap.removeAttribute('hidden');
      } else {
        if (errorWrap) errorWrap.setAttribute('hidden', '');
      }
      // M11 F17 L5 fix: when the status poll returns an application_id for a
      // connected connector, seed the Discord invite-section cache so the invite
      // URL renders without a manual Validate step. No-op when the Discord
      // namespace is absent (non-Discord connectors, early-load race) or when
      // application_id is null (disconnected / connecting / non-Discord client).
      var appId = body && body.application_id;
      if (appId && account && account.id &&
          window.App && window.App.studio && window.App.studio.connectorFormDiscord &&
          typeof window.App.studio.connectorFormDiscord.setApplicationId === 'function') {
        window.App.studio.connectorFormDiscord.setApplicationId(account.id, appId);
      }
    }

    function _poll() {
      if (!textEl.isConnected) {
        // Element removed — editor unmounted. Stop polling.
        if (_pollTimer) clearTimeout(_pollTimer);
        return;
      }
      var url = '/api/connectors/' + encodeURIComponent(account.id) + '/status';
      fetch(url).then(function (resp) {
        if (!resp.ok) return null;
        return resp.json();
      }).then(function (body) {
        if (!textEl.isConnected) return;
        if (body) _applyStatus(body);
        _pollTimer = setTimeout(_poll, _POLL_INTERVAL_MS);
      }).catch(function () {
        if (!textEl.isConnected) return;
        // On network error keep the last state and retry.
        _pollTimer = setTimeout(_poll, _POLL_INTERVAL_MS);
      });
    }

    // Initial fetch immediately on mount.
    _poll();
  }

  function _wireAllowlistBanner(container, account) {
    if (!container || !account || !account.id) return;
    var banner = container.querySelector('[data-testid="connector-allowlist-banner"]');
    if (!banner) return;
    var refreshBtn = banner.querySelector(
      '[data-testid="connector-allowlist-banner-refresh"]'
    );
    var statusEl = banner.querySelector(
      '[data-testid="connector-allowlist-banner-status"]'
    );
    var ledEl = banner.querySelector(
      '[data-testid="connector-allowlist-banner-led"]'
    );
    if (!refreshBtn || !statusEl || !ledEl) return;

    function _setLed(modifier) {
      ledEl.classList.remove(
        'indicator-led--success',
        'indicator-led--warning',
        'indicator-led--danger',
        'indicator-led--idle'
      );
      ledEl.classList.add('indicator-led--' + modifier);
    }

    function _setState(stateName, message) {
      banner.setAttribute('data-state', stateName);
      if (stateName === 'populated') {
        _setLed('success');
        refreshBtn.removeAttribute('hidden');
        refreshBtn.removeAttribute('disabled');
      } else if (stateName === 'refreshing') {
        // Visual mid-refresh pose — disable the button to avoid
        // double-clicks; the dropdowns are doing the heavy lifting via
        // their own _refreshEntities calls.
        refreshBtn.setAttribute('disabled', '');
      } else if (stateName === 'unsupported') {
        _setLed('idle');
        refreshBtn.setAttribute('hidden', '');
      } else {
        // pre-probe / error fall through to the idle pose.
        // F5 L6 HAT round-6: keep Refresh visible so the operator can
        // re-trigger a probe attempt without leaving the A&R tab.
        // Clicking Refresh in pre-probe state re-fetches; still 404
        // leaves the state in pre-probe (harmless); successful warmup
        // transitions to populated.
        _setLed('idle');
        refreshBtn.removeAttribute('hidden');
        refreshBtn.removeAttribute('disabled');
      }
      if (typeof message === 'string') {
        statusEl.textContent = message;
      }
    }

    function _formatFetchedAt(iso) {
      if (!iso) return '';
      // Defensive: any parse failure → fall back to the raw string so
      // the operator still sees *something*. Mirrors the
      // ``connectors-tab.js`` defensive-ago pattern.
      var date;
      try { date = new Date(iso); }
      catch (e) { return iso; }
      if (!date || isNaN(date.getTime())) return iso;
      var diffMs = Date.now() - date.getTime();
      if (diffMs < 0 || diffMs < 5000) return 'just now';
      var diffS = Math.floor(diffMs / 1000);
      if (diffS < 60) return diffS + 's ago';
      var diffM = Math.floor(diffS / 60);
      if (diffM < 60) return diffM + 'm ago';
      var diffH = Math.floor(diffM / 60);
      if (diffH < 24) return diffH + 'h ago';
      return date.toLocaleString();
    }

    function _probe() {
      var url = '/api/connectors/' + encodeURIComponent(account.id) +
                '/discoverable-entities';
      fetch(url).then(function (response) {
        if (response.status === 404) {
          _setState('pre-probe',
                    'Refresh connection to populate the discoverable lists.');
          return null;
        }
        if (response.status === 503) {
          _setState('unsupported',
                    'This connector type does not expose discoverable entities.');
          return null;
        }
        if (!response.ok) {
          _setState('pre-probe',
                    "Couldn't load discoverable lists; try Refresh.");
          // Show the refresh button on error so operator can retry.
          refreshBtn.removeAttribute('hidden');
          refreshBtn.removeAttribute('disabled');
          return null;
        }
        return response.json();
      }).then(function (body) {
        if (!body) return;
        var fetchedAt = body.fetched_at || '';
        var ago = _formatFetchedAt(fetchedAt);
        _setState('populated',
                  ago ? 'Last refreshed: ' + ago : 'Loaded.');
      }).catch(function (err) {
        _setState('pre-probe',
                  "Couldn't load discoverable lists; try Refresh.");
        refreshBtn.removeAttribute('hidden');
        refreshBtn.removeAttribute('disabled');
        try { console.error('allowlist banner probe failed:', err); }
        catch (logErr) { /* console missing */ }
      });
    }

    refreshBtn.addEventListener('click', function () {
      _setState('refreshing', 'Refreshing…');
      try {
        App.studio.eventBus.emit('connector-discoverable-refresh-requested', {
          accountId: account.id,
        });
      } catch (e) {
        try { console.error('refresh-requested dispatch failed:', e); }
        catch (logErr) { /* console missing */ }
      }
      // Give the dropdowns a moment to POST /refresh + cache the new
      // payload before we GET to read the fresh ``fetched_at``. 600ms
      // is a heuristic — the L4 POST is synchronous-on-success per the
      // F4 L4 contract, but we want the cache write to land first.
      setTimeout(_probe, 600);
    });

    // React in real time to a Test Connection success that warmed the
    // pool. The Test Connection POST handler (see connector-
    // editor.js renderTestConnectionResponse) dispatches this event
    // with ``{ accountId }`` detail when ``details.pool_warmed === true``.
    var poolWarmedHandler = function (event) {
      if (!banner.isConnected) {
        document.removeEventListener('connector-pool-warmed', poolWarmedHandler);
        return;
      }
      if (event && event.detail && event.detail.accountId === account.id) {
        // Small delay to let the dropdowns' own _fetchEntities settle
        // before we GET for the ``fetched_at`` timestamp.
        setTimeout(_probe, 600);
      }
    };
    App.studio.eventBus.on('connector-pool-warmed', poolWarmedHandler);

    // Initial probe — discover the real pool state on editor mount.
    _probe();
  }

  function collectAllowlistFromContainer(container) {
    // M10 F6 L7 HAT — Returns ``{ peers, channels, guilds, roles }``
    // (or null if the slots are missing — defensive). All 4 lists are
    // ALWAYS emitted; empty list = unrestricted on that axis. Chips
    // are read in DOM order; the wireChipListEditor helper guarantees
    // only committed chip elements (not the live input) carry values.
    // Whitespace-only entries cannot reach a chip (the helper trims
    // before committing). M10 F8 L8 added the guilds + roles axes.
    //
    // M11 F3 L6a — per-slot ``_allowlistValues`` getter (installed by
    // ``_mountAllowlistAxisEditor`` when the dropdown path is taken)
    // is the canonical bridge for dropdown-driven values. The dropdown
    // component's ``.chip`` DOM shape is structurally distinct from
    // the chip-list editor's, so falling through to the text-node walk
    // would mis-read the dropdown chips. The getter wraps the
    // dropdown's own state. Chip-list path does NOT install the
    // getter; we fall back to the text-node walk.
    var peersSlot = container.querySelector('[data-allowlist-chiplist-slot="peers"]');
    var serversSlot = container.querySelector('[data-allowlist-chiplist-slot="guilds"]');
    if (!peersSlot && !serversSlot) return null;
    // M11 F12 L5 — channels + roles are read from the Servers slot's
    // hierarchical getter; the L4 flat per-axis slots no longer
    // exist (the markup at ``renderAllowlistSection`` only renders
    // peers + servers slots).
    function _readChiplist(slot) {
      // M11 F12 L4 — the ``_allowlistValues`` getter now returns the
      // structured-tuple shape directly for peers/channels/roles (and
      // bare strings for guilds). Pass non-string entries through
      // unchanged so the structured shape reaches the save payload; for
      // bare-string fallbacks (text-node walk path) preserve the
      // pre-L4 behavior.
      var out = [];
      if (!slot) return out;
      if (typeof slot._allowlistValues === 'function') {
        var vals = slot._allowlistValues() || [];
        for (var k = 0; k < vals.length; k++) {
          var v = vals[k];
          if (v == null) continue;
          if (typeof v === 'object') {
            out.push(v);
          } else {
            var s = String(v);
            if (s) out.push(s);
          }
        }
        return out;
      }
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
    // M11 F10 L2: dm_admission axis (3-value selector). Reads the
    // selector value; defaults to 'admin-approved' when the selector is
    // absent (defensive — shouldn't reach this code path because the
    // early-return above already guards on chiplist absence, and
    // dm_admission renders in the same section).
    // M11 F12 L4: Literal value rename ``allowlisted-peers-only`` →
    // ``admin-approved`` (operator-vocabulary alignment).
    var dmAdmissionSelect = container.querySelector(
        '[data-testid="connector-allowlist-dm-admission-select"]');
    var dmAdmission = dmAdmissionSelect ? dmAdmissionSelect.value : 'admin-approved';

    // M11 F12 L5 — hierarchical channels + roles + guilds read from
    // the Servers slot's hierarchical getter; falls back to empty
    // lists if the slot hasn't installed the getter (e.g. early
    // probe before mount).
    var hierarchical = (serversSlot
        && typeof serversSlot._hierarchicalAllowlistValues === 'function')
        ? serversSlot._hierarchicalAllowlistValues()
        : { guilds: [], channels: [], roles: [] };

    return {
      peers: _readChiplist(peersSlot),
      channels: hierarchical.channels,
      guilds: hierarchical.guilds,
      roles: hierarchical.roles,
      dm_admission: dmAdmission
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
    // M11 F12 L4 — peers / channels now carry structured-tuple shape:
    //   peers:    [{id, dm_allowed}]
    //   channels: [{guild_id, channel_id}]
    // Extract the id field for set-difference + the agent-side lookup
    // (per-agent ACL stores the same structured shape post-L4).
    function _peerIds(arr) {
      var ids = [];
      for (var i = 0; i < (arr || []).length; i++) {
        var p = arr[i];
        if (p && typeof p === 'object') {
          if (p.id) ids.push(String(p.id));
        } else if (p != null) {
          ids.push(String(p));
        }
      }
      return ids;
    }
    function _channelIds(arr) {
      var ids = [];
      for (var i = 0; i < (arr || []).length; i++) {
        var c = arr[i];
        if (c && typeof c === 'object') {
          if (c.channel_id) ids.push(String(c.channel_id));
        } else if (c != null) {
          ids.push(String(c));
        }
      }
      return ids;
    }

    var origAllowlist = (account && account.config && account.config.allowlist) || null;
    var origPeers = _peerIds(origAllowlist && origAllowlist.peers);
    var origChannels = _channelIds(origAllowlist && origAllowlist.channels);
    var newAllowlist = (payload && payload.config && payload.config.allowlist) || null;
    var newPeers = _peerIds(newAllowlist && newAllowlist.peers);
    var newChannels = _channelIds(newAllowlist && newAllowlist.channels);

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

    fetch('/api/connectors/' + encodeURIComponent(account.id) + '/attached-agents')
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
          // M11 F12 L4 — per-agent peers/channels arrive in the same
          // structured-tuple shape as account-scope (storage
          // pass-through). Project to ids for set-membership.
          var rowPeers = _peerIds(row.peers);
          var rowChannels = _channelIds(row.channels);
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
    var thead = container.querySelector('.connector-config-thead');
    if (!thead) return;
    var rowCount = container.querySelectorAll('.connector-config-table tbody tr.connector-config-row').length;
    thead.classList.toggle('is-hidden', rowCount === 0);
  }

  function updateSecretsHeadVisibility(container) {
    var thead = container.querySelector('.connector-secrets-thead');
    if (!thead) return;
    var rowCount = container.querySelectorAll('.connector-secrets-table tbody tr.connector-secret-row').length;
    thead.classList.toggle('is-hidden', rowCount === 0);
  }

  window.App.studio.renderConnectorEditor = renderConnectorEditor;
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
