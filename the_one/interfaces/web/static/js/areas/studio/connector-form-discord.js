// App.studio.connectorFormRegistry — Discord entry (M11 F1 L4).
//
// First consumer of the L3 registry substrate. Registers the
// ``'discord'`` entry at module load time so the connector
// editor renders typed Discord-shaped fields (intents row, scope-to-
// servers list, bot-status editor, masked BOT_TOKEN, Additional
// Config kv-table) instead of falling back to the generic kv-table.
//
// Contract:
//   - L3's ``connector-form-registry.js`` MUST load before this file
//     (script-tag ordering in ``index.html``). If the registry is
//     missing at module-load time, this script throws — surfaced as a
//     console error so the operator sees the misorder immediately.
//   - L2's API validator (``api.py:_validate_connector_config``)
//     accepts the shapes this entry emits — three-key dict for
//     ``intents``, list-of-digit-strings for ``guilds``, dict with
//     optional ``name`` / ``type`` for ``presence``. Empty-dict
//     ``presence`` is accepted (cleared-when-pre-existing intent).
//   - Backward compat: an existing Discord account whose ``config``
//     lacks ``intents`` / ``guilds`` / ``presence`` renders with the
//     typed inputs at defaults; saving without operator edits MUST NOT
//     introduce keys that weren't present (preserves M10 F8
//     byte-identical round-trip).
//
// Public surface: none — registers via side effect at module load.

(function () {
  'use strict';

  if (!window.App || !window.App.studio || !window.App.studio.connectorFormRegistry) {
    throw new Error(
      'connector-form-discord.js: App.studio.connectorFormRegistry is not loaded. ' +
        'Check script-tag ordering in index.html — connector-form-registry.js ' +
        'must load before this file.'
    );
  }

  // M11 F5 L6 HAT round-8: the three ``_DIRECTIVE_*_DEFAULT`` JS twins
  // and the ``renderDirectiveSection`` helper were REMOVED from this
  // module. The simplified two-default surface now lives in
  // ``connector-editor.js`` (the Session-section codeblock
  // mounts the relevant default below the Auto-reply toggle).

  // ── M11 F1 L5 / M11 F17 L5: Invite-URL section ─────────────────────
  //
  // The doctor probe at ``_discord.py`` populates
  // ``report.details.application_id`` on the ``application`` check
  // success path. ``connector-editor.js:renderTestConnectionBanner``
  // forwards this to ``setApplicationId`` below (via the namespace
  // export at the bottom of this IIFE), which caches it per-account-id
  // and re-renders the Invite section's URL display.
  //
  // M11 F17 L5: ``application_id`` is now ALSO persisted in
  // ``account.config["application_id"]`` by the Validate endpoint so
  // the invite renders without a prior Validate on subsequent page
  // loads. ``renderInviteSection`` seeds the cache from the
  // ``account.config`` value when it hasn't been set by a Validate yet.
  var _lastApplicationIdByAccount = {};

  // Required permissions integer for the bot's OAuth2 invite URL.
  // Per F1 Design Decisions §"Invite URL", these are the four
  // permissions M10 F8 + F1 actually need:
  //   1 << 11 = 2048       (Send Messages)
  //   1 << 16 = 65536      (Read Message History)
  //   1 << 10 = 1024       (View Channels)
  //   1 << 31 = 2147483648 (Use Application Commands)
  // Total: 2147552256. Intent toggles do NOT affect this integer;
  // intents and permissions are orthogonal Discord concepts. Future
  // flights extending bot capabilities update this constant alongside.
  //
  // Note on the JavaScript expression: ``1 << 31`` in JavaScript
  // produces the signed-32-bit value ``-2147483648`` because bitwise
  // operators coerce operands to int32. ``Math.pow(2, 31)`` returns
  // the unsigned value 2147483648 as a Number, which OR'd against the
  // small left-shifts gives the correct positive 2147552256. The
  // unary ``+`` here is a clarity nudge; ``Math.pow(2,31)`` already
  // returns a Number.
  var _DISCORD_INVITE_PERMISSIONS = (1 << 11) + (1 << 16) + (1 << 10) + Math.pow(2, 31);

  function _computeInviteUrl(applicationId) {
    return 'https://discord.com/oauth2/authorize?client_id=' + applicationId +
           '&permissions=' + _DISCORD_INVITE_PERMISSIONS +
           '&scope=bot+applications.commands';
  }

  // L2-pinned Discord ``presence.type`` enum (api.py:_DISCORD_PRESENCE_TYPES).
  // The empty option represents "no presence override" — collect emits no
  // ``type`` key. Keep this list in sync with the validator's frozenset.
  var PRESENCE_TYPES = ['playing', 'streaming', 'listening', 'watching', 'competing'];

  // M11 F17 L6 (Leg B): INTENT_AXES removed — all three gateway intents
  // (message_content, members, guilds) are now always-on in the backend.
  // The operator-facing intent checkboxes are gone; no in-JS axis list needed.

  function _escapeHtml(s) {
    return window.App.escapeHtml(s == null ? '' : String(s));
  }

  function _escapeAttr(s) {
    return window.App.escapeAttr(s == null ? '' : String(s));
  }

  // ── Render: Runtime Config (intents + guilds + presence + advanced) ─
  //
  // F5 L3: extracted from the old ``renderConnectionFields`` body so the
  // SAME markup can be rendered either in the Connection section
  // (create-mode flat layout, no tabs) OR on the Access-and-Routing tab
  // between Lifecycle and Allowlist (edit-mode tabbed layout). Single
  // source-of-truth for the runtime-config markup; ``renderConnectionFields``
  // (create-mode) and ``renderRuntimeConfigFields`` (edit-mode-hook for
  // the substrate) both delegate to this helper.
  //
  // Verbose ``<small class="form-hint">`` blocks replaced with
  // ``.field-info-icon`` tooltips per F5 Design Decision; production
  // pattern matches ``mcp-server-editor.js:790-795`` (browser-native
  // ``title=`` tooltip + ``aria-describedby`` + ``visually-hidden`` sibling
  // for screen readers).
  //
  // F5 L6 HAT round-2: all four rows (Intents, Scope to servers, Bot
  // status, Additional Config) use the canonical 2-column
  // ``field-row admin-pf-row`` layout for typography consistency.
  // Label copy revised for plain-English clarity (was: jargon-y
  // "Intents" / "Servers" / "Presence" / "Advanced (kv-table)"). The
  // GUILDS intent label is "Server info" — disambiguates from the
  // Allowlist "Servers" axis (Discord's GUILDS intent carries guild
  // metadata events, not the guild allowlist).
  //
  // F5 L6 HAT round-3: info-icons refactored OUT of the ``<label>``
  // element into sibling position to match the Lifecycle section's
  // 3-column pattern (label | info-icon | field). Pre-round-3 the icon
  // sat nested inside the label cell, which read as "label and its
  // decoration"; the canonical pattern puts the icon between the
  // label and the field control so the flex row treats label +
  // info-icon + field as three visible cells. The visually-hidden span
  // is a sibling of the info-icon (not nested in it) so it does NOT
  // occupy a visible column. Each info-icon now carries a
  // 'data-testid' ('discord-intents-hint' / 'discord-guilds-hint'
  // / 'discord-presence-hint') for parity with the Lifecycle section's
  // 'connector-continuation-hint' / '-idle-hint' sites.

  function _renderRuntimeConfigBody(account) {
    var cfg = (account && account.config) || {};
    var presenceCfg = (typeof cfg.presence === 'object' && cfg.presence) ? cfg.presence : {};

    var html = '';
    var infoIcon = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';

    // M11 F17 L6 (Leg B): Intent checkboxes removed. The three gateway
    // intents (message_content, members, guilds) are always-on in the
    // backend. PrivilegedIntentsRequired errors surface via Leg A's
    // connect-error status path with an actionable portal link.

    // ── "Scope to servers" field retired (M11 F14 L02) ──────────────
    // The standalone top-level "Scope to servers" guilds text field was
    // unified onto the allowlist "Servers" axis (``config.allowlist.guilds``),
    // which is the single source of truth for both inbound-admission ACL
    // AND slash-command registration. Guilds are now set via the
    // connector allowlist editor's "Servers" section. The ``guilds``
    // gateway-intent checkbox ("Server info") in the Intents row above
    // is a separate concept (a Discord gateway intent, not a scoping
    // list) and is intentionally retained.

    // ── Bot status row (HAT round-2 fix #4) ─────────────────────────
    // Pre-round-2 label "Presence" was Discord-jargon; the order was
    // [name input, type select], which read backwards. Round-2 renames
    // to "Bot status" and swaps to [type select, name input] so the two
    // controls read as a sentence ("Playing chess" / "Listening to
    // music"). Option labels rewritten as natural-language verbs;
    // ``value=`` attributes preserved (API contract pinned by L2's
    // ``_DISCORD_PRESENCE_TYPES`` frozenset).
    var presenceName = (typeof presenceCfg.name === 'string') ? presenceCfg.name : '';
    var presenceType = (typeof presenceCfg.type === 'string') ? presenceCfg.type : '';
    var presenceTipText = "What people see next to the bot's name in the member list (e.g., 'Playing chess').";
    var PRESENCE_TYPE_LABELS = {
      playing: 'Playing',
      streaming: 'Streaming',
      listening: 'Listening to',
      watching: 'Watching',
      competing: 'Competing in'
    };

    // F5 L3: stacked ``.field-group`` vocabulary (label above control),
    // replacing the F5 L6 label-left ``field-row admin-pf-row`` layout.
    // "Bot status" is a GROUP caption over the compound (type select +
    // name input) — each inner control carries its own visually-hidden
    // ``<label for>`` below, so the caption stays a bare label. The
    // label + info-icon sit on one line via the shared ``.field-group-label``
    // primitive (label + icon are SIBLINGS — never nest the button in a label).
    html += '<div class="field-group discord-presence-row">';
    html += '<div class="field-group-label">';
    html += '<label>Bot status</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + _escapeAttr(presenceTipText) + '" ' +
            'aria-describedby="discord-presence-help-text" ' +
            'data-testid="discord-presence-hint">' +
            infoIcon + '</button>';
    html += '</div>';
    html += '<span id="discord-presence-help-text" class="visually-hidden">' +
            _escapeHtml(presenceTipText) + '</span>';
    html += '<div class="discord-presence-fields">';
    html += '<label for="cf-discord-presence-type" class="visually-hidden">Activity type</label>';
    html += '<select id="cf-discord-presence-type" class="field-input field-select" data-field="presence-type" data-testid="discord-presence-type">';
    var emptySelected = presenceType === '' ? ' selected' : '';
    html += '<option value=""' + emptySelected + '>(default)</option>';
    for (var p = 0; p < PRESENCE_TYPES.length; p++) {
      var pt = PRESENCE_TYPES[p];
      var sel = (pt === presenceType) ? ' selected' : '';
      var ptLabel = PRESENCE_TYPE_LABELS[pt] || pt;
      html += '<option value="' + _escapeAttr(pt) + '"' + sel + '>' + _escapeHtml(ptLabel) + '</option>';
    }
    html += '</select>';
    html += '<label for="cf-discord-presence-name" class="visually-hidden">Activity name</label>';
    html += '<input id="cf-discord-presence-name" class="field-input" type="text" data-field="presence-name" data-testid="discord-presence-name" ' +
            'value="' + _escapeAttr(presenceName) + '" placeholder="(e.g., chess, music)" />';
    html += '</div>';
    html += '</div>';

    // M11 F17 L7 (Leg C): Additional Config kv-table relocated to a
    // bottom "Advanced" section and re-wrapped in a
    // ``<details>``-based disclosure. Pre-L7 it sat inline among the
    // everyday typed fields (HAT round-2 promoted it there; F17 design
    // review demotes it back). The ``discord-additional-config-row``
    // testid is preserved so ``connector-editor-ux`` step-5 and the
    // create-mode-absence assertion in
    // ``test_flow_studio_connector_create_and_test.py`` continue to
    // resolve. The ``connector-advanced-section`` testid on the outer
    // wrapper lets the new DOM-order assertion confirm placement.
    html += '<details class="advanced-collapsible connector-advanced-section" ' +
            'data-testid="connector-advanced-section">';
    html += '<summary>Advanced</summary>';
    // F5 L3: stacked ``.field-group`` (label above the kv-table body),
    // replacing the label-left ``field-row admin-pf-row`` gutter layout.
    // The pseudo-label is a ``<div>`` (the kv-table has many key/value
    // inputs — no single control to associate a ``<label for>`` with);
    // it is styled to match ``.field-group > label`` typography.
    html += '<div class="field-group discord-additional-config-row" ' +
            'data-testid="discord-additional-config-row">';
    html += '<div class="discord-additional-config-label">Additional Config</div>';
    html += '<div class="discord-additional-config-body">';
    // L4 contract: ``renderConfigKvTable`` is exposed on
    // ``window.App.studio`` for this exact mount point. Triple-guard
    // for early-load (the substrate exposes it at IIFE end, same script).
    var renderKv = (window.App && window.App.studio && window.App.studio.renderConfigKvTable) || null;
    if (typeof renderKv === 'function') {
      html += renderKv(account);
    }
    html += '</div>';
    html += '</div>';
    html += '</details>';

    return html;
  }

  // ── Render: Connection (always empty — runtime config is edit-mode-only) ─
  //
  // F5 L3: in edit-mode (tabbed), runtime-config lives on the
  // Access-and-Routing tab via ``renderRuntimeConfigFields`` so tab
  // semantics are coherent (General = WHAT the bot is; Access and
  // Routing = HOW it behaves at runtime).
  // F5 L6 HAT: create-mode no longer renders runtime config inline.
  // Operators configure Intents/Servers/Presence/Advanced post-create
  // on the A&R tab. Discord's typed Connection-section contribution is
  // now always empty; the shared ``_renderRuntimeConfigBody`` helper
  // stays as the single source-of-truth that ``renderRuntimeConfigFields``
  // (edit-mode A&R tab mount) consumes.
  //
  // The ``isCreate`` parameter is retained in the signature for
  // registry-contract compatibility but is unused.

  function renderConnectionFields(account, isCreate) {  // eslint-disable-line no-unused-vars
    return '';
  }

  // ── Render: Runtime Config (edit-mode hook) ────────────────────────
  //
  // F5 L3: registry-mediated optional hook called by the substrate from
  // ``connector-editor.js`` when building the Access-and-Routing
  // tab. Substrate wraps the returned content in an ``<div
  // class="editor-section">`` with ``<div class="section-title">Runtime
  // Config</div>``; this helper returns the inner content only.

  function renderRuntimeConfigFields(account) {
    return _renderRuntimeConfigBody(account);
  }

  // ── Render: Credentials (typed BOT_TOKEN with masked-edit) ─────────

  function renderCredentialsFields(account) {
    var secrets = (account && account.secrets) || {};
    var masked = secrets.BOT_TOKEN != null ? String(secrets.BOT_TOKEN) : '';
    var infoIcon = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';
    var hintText = 'Stored encrypted at rest; shown masked on read.';

    // F5 L6 HAT: 2-column ``field-row admin-pf-row`` layout (label +
    // input on one row) to match the other form fields. The verbose
    // ``<small class="form-hint">`` block is replaced with a
    // ``.field-info-icon`` tooltip (production pattern: ``title=`` +
    // ``aria-describedby`` + visually-hidden sibling). The
    // ``kv-value-secret`` class is preserved (it carries the masked-edit
    // semantics); ``.field-input`` is added so the input picks up the
    // dark-theme styling + the substrate's ``attachStaticListeners``
    // dirty-tracking wiring.
    // F5 L3: stacked ``.field-group`` (label above control). The info-icon
    // button is un-nested from inside the ``<label>`` (a <button> nested in
    // a <label> is invalid + a click-target ambiguity) into the shared
    // ``.field-group-label`` primitive, where label + icon are siblings.
    var html = '';
    html += '<div class="field-group discord-credentials-row">';
    html += '<div class="field-group-label">';
    html += '<label for="cf-discord-bot-token">Bot Token</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + _escapeAttr(hintText) + '" ' +
            'aria-describedby="discord-bot-token-help-text" ' +
            'data-testid="connector-bot-token-hint">' +
            infoIcon + '</button>';
    html += '</div>';
    html += '<span id="discord-bot-token-help-text" class="visually-hidden">' +
            _escapeHtml(hintText) + '</span>';
    html += '<div class="api-key-wrap">';
    html += '<input class="field-input kv-value-secret" type="password" id="cf-discord-bot-token" ' +
            'data-field="bot-token" data-testid="discord-bot-token" ' +
            'value="' + _escapeAttr(masked) + '" data-original-masked="' + _escapeAttr(masked) +
            '" placeholder="Bot token" />';
    html += '<button class="api-key-eye discord-bot-token-eye-btn" type="button" ' +
            'data-testid="discord-bot-token-eye-btn" aria-label="Show value">' +
            window.App.icon('eye') + '</button>';
    html += '</div>';
    html += '</div>';

    return html;
  }

  // ── Collect: read typed-input DOM → {config, secrets} payload ──────

  // M11 F17 L6 (Leg B): _readIntentChecked removed — intent checkboxes
  // no longer exist in the DOM. Backend always forces all three intents on.

  function _readInputValue(container, fieldName) {
    var el = container.querySelector('[data-field="' + fieldName + '"]');
    return el ? (el.value || '') : '';
  }

  function collect(container, account, isEdit) {
    var existingCfg = (account && account.config) || {};
    var config = {};
    var secrets = {};

    // M11 F17 L6 (Leg B): Intent collect block removed. The backend always
    // forces all three intents on; config["intents"] is kept for back-compat
    // but is no longer written by this form. Pre-existing intents keys are
    // left in config by the backend (not stripped here — inert on connect).

    // ── Guilds: retired (M11 F14 L02) ────────────────────────────────
    // The standalone "Scope to servers" (top-level guilds) form
    // field was unified onto the allowlist "Servers" axis
    // (``config.allowlist.guilds``). Guilds are set via the connector
    // allowlist editor, not this Runtime Config form. No write-back here.

    // ── Presence ─────────────────────────────────────────────────────
    var presenceName = _readInputValue(container, 'presence-name').replace(/^\s+|\s+$/g, '');
    var presenceType = _readInputValue(container, 'presence-type');
    var hadPresenceBefore = Object.prototype.hasOwnProperty.call(existingCfg, 'presence');
    var nameNonEmpty = presenceName.length > 0;
    var typeNonDefault = presenceType.length > 0;
    if (nameNonEmpty || typeNonDefault || hadPresenceBefore) {
      var presence = {};
      if (nameNonEmpty) presence.name = presenceName;
      if (typeNonDefault) presence.type = presenceType;
      // Cleared-when-pre-existing: both blank but key was set before →
      // emit empty dict so operator's clear-intent round-trips
      // (L2 validator accepts empty-dict ``presence``).
      config.presence = presence;
    }

    // ── BOT_TOKEN (masked-edit) ──────────────────────────────────────
    var tokenEl = container.querySelector('[data-field="bot-token"]');
    if (tokenEl) {
      var tokenValue = tokenEl.value || '';
      var origMasked = tokenEl.getAttribute('data-original-masked') || '';
      if (origMasked && tokenValue === origMasked) {
        secrets.BOT_TOKEN = window.App.studio.MASKED_SENTINEL;
      } else {
        secrets.BOT_TOKEN = tokenValue;
      }
    }

    // M11 F5 L6 HAT round-8: the System Prompt Directive collect block
    // was REMOVED (operator-editable per-account directive surface
    // dropped; substrate defaults are used universally).

    // M11 F17 L7 (Leg C): kv-table round-trip fix. The substrate's
    // ``collectFormData`` takes the typed-registry branch (``cfdCollected``
    // truthy) and skips the generic ``.connector-config-row`` DOM scan,
    // so any ad-hoc keys added via the Advanced kv-table were silently
    // lost on save. Fix: extend Discord's ``collect()`` to also scan
    // the kv-table rows and merge non-reserved keys into ``config``.
    //
    // Effective reserved set mirrors the union that ``collectConfigRows``
    // builds at runtime (substrate baseline + per-type list):
    //   substrate: pairing, allowlist, routing, always_listen,
    //              inference_provider_config_id, inference_model
    //   Discord:   intents, presence
    // Keys that ``collect()`` already writes (presence) are also in the
    // reserved set so they cannot be double-written via the kv-table.
    var _kvReserved = {
      pairing: true,
      allowlist: true,
      routing: true,
      always_listen: true,
      inference_provider_config_id: true,
      inference_model: true,
      intents: true,
      presence: true,
      // M11 F17: application_id is persisted by the Validate endpoint
      // (public OAuth2 client id, not a secret) and drives the invite
      // URL. Exclude it from the Advanced kv-table so an operator
      // cannot accidentally delete it and lose the invite link.
      application_id: true
    };
    var kvRows = container.querySelectorAll(
      '.connector-config-table tbody tr.connector-config-row'
    );
    for (var ki = 0; ki < kvRows.length; ki++) {
      var kvRow = kvRows[ki];
      var kkEl = kvRow.querySelector('.config-key-input');
      var kvEl = kvRow.querySelector('.config-value-input');
      if (!kkEl || !kvEl) continue;
      var kk = (kkEl.value || '').trim();
      if (!kk) continue;
      if (_kvReserved[kk]) continue;
      config[kk] = kvEl.value || '';
    }

    return { config: config, secrets: secrets };
  }

  // ── Snapshot: typed-input state → JSON-serializable view ───────────

  function snapshot(container) {
    // M11 F17 L6 (Leg B): intents removed from snapshot — checkboxes gone.
    return {
      presenceName: _readInputValue(container, 'presence-name'),
      presenceType: _readInputValue(container, 'presence-type'),
      botTokenValue: _readInputValue(container, 'bot-token')
    };
  }

  // ── Invite section render + DOM mutation helpers (M11 F1 L5) ──────

  function renderInviteSection(account) {
    var accountId = (account && account.id) || '';
    // M11 F17 L5: seed the cache from account.config.application_id
    // (persisted by the Validate endpoint) so the invite renders on
    // initial load without a prior Validate this session.
    var persistedAppId = (account && account.config && account.config.application_id) || '';
    if (persistedAppId && !_lastApplicationIdByAccount[accountId]) {
      _lastApplicationIdByAccount[accountId] = persistedAppId;
    }
    var appId = _lastApplicationIdByAccount[accountId];
    var hintHidden = appId ? ' hidden' : '';
    var urlHidden = appId ? '' : ' hidden';
    var url = appId ? _computeInviteUrl(appId) : '';
    var infoIcon = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';
    var copyIcon = (window.App && window.App.icon) ? window.App.icon('copy') : '⧉';
    var refreshIcon = (window.App && window.App.icon) ? window.App.icon('refresh-cw') : '↻';
    // M11 F17 L5: updated tooltip text to explain the invite's purpose.
    var infoText = 'Open this to add the bot to a Discord server — needed once per server at setup.';

    var html = '';
    // M17 F5 L3: stacked ``.field-group`` (label + info-icon on one line
    // above the invite field). Copy + Refresh are icon-only buttons
    // matching the existing connector-pairing-copy-btn precedent.
    // The ``connector-invite-section`` testid stays on the outer div so
    // DOM-by-testid lookups keep resolving.
    html += '<div class="field-group connector-invite-row" ' +
            'data-testid="connector-invite-section">';
    html += '<div class="field-group-label">';
    html += '<label>Invite link</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + _escapeAttr(infoText) + '" ' +
            'aria-describedby="connector-invite-help-text" ' +
            'data-testid="connector-invite-info">' + infoIcon + '</button>';
    html += '</div>';
    html += '<span id="connector-invite-help-text" class="visually-hidden">' +
            _escapeHtml(infoText) + '</span>';
    html += '<div class="connector-invite-field">';
    html += '<span class="connector-invite-hint" ' +
            'data-testid="connector-invite-hint"' + hintHidden + '>' +
            'Run Validate to fetch your application ID.' +
            '</span>';
    html += '<div class="connector-invite-url-wrap" ' +
            'data-testid="connector-invite-url-wrap"' + urlHidden + '>';
    html += '<code class="connector-invite-url" ' +
            'data-testid="connector-invite-url">' + _escapeHtml(url) + '</code>';
    html += '<button type="button" class="connector-invite-icon-btn connector-invite-copy-btn" ' +
            'data-testid="connector-invite-copy-btn" ' +
            'title="Copy invite URL" aria-label="Copy invite URL">' +
            copyIcon + '</button>';
    html += '<button type="button" class="connector-invite-icon-btn connector-invite-recompute-btn" ' +
            'data-testid="connector-invite-recompute-btn" ' +
            'title="Refresh invite URL" aria-label="Refresh invite URL">' +
            refreshIcon + '</button>';
    html += '</div>';
    html += '</div>';
    html += '</div>';
    return html;
  }

  // M11 F5 L6 HAT round-8: ``renderDirectiveSection``,
  // ``_renderDirectiveDisclosure``, and ``_updateDirectiveAnnotation``
  // were REMOVED. The directive surface is now read-only and lives
  // under the Auto-reply toggle in the Session section (rendered by
  // ``connector-editor.js``), not as an editable General-tab
  // section.

  function _updateInviteUrlDisplay(container, account) {
    if (!container) return;
    var accountId = (account && account.id) || '';
    var appId = _lastApplicationIdByAccount[accountId];
    var hintEl = container.querySelector('[data-testid="connector-invite-hint"]');
    var urlWrap = container.querySelector('[data-testid="connector-invite-url-wrap"]');
    var urlCode = container.querySelector('[data-testid="connector-invite-url"]');
    if (appId) {
      var url = _computeInviteUrl(appId);
      if (urlCode) urlCode.textContent = url;
      if (urlWrap) urlWrap.hidden = false;
      if (hintEl) hintEl.hidden = true;
    } else {
      if (urlCode) urlCode.textContent = '';
      if (urlWrap) urlWrap.hidden = true;
      if (hintEl) hintEl.hidden = false;
    }
  }

  // ── Event wiring: attach listeners so typed-input edits flip dirty ─

  function _wireListener(container, selector, eventName, handler) {
    var el = container.querySelector(selector);
    if (el) el.addEventListener(eventName, handler);
  }

  function wireEvents(container, checkDirty, account) {
    // M11 F1 L5: the invite-section's intent-recompute path needs to
    // resolve the account so ``_updateInviteUrlDisplay`` can read the
    // module-scope cache by ``account.id``. The substrate calls
    // ``wireEvents(container, checkDirty)`` historically; the third
    // arg is additive and OPTIONAL — when absent, intent-toggle
    // recompute is a no-op (the URL display is pure-template; no harm).
    var inviteAccount = account || _resolveAccountFromContainer(container);

    // M11 F17 L6 (Leg B): _onIntentChange + intent-checkbox listeners removed.
    // Intent checkboxes are gone from the DOM; the invite URL is stable
    // (recompute still triggered by the Recompute button below).

    // Presence name (text) — same per-keystroke pattern.
    _wireListener(container, '[data-field="presence-name"]', 'input', checkDirty);

    // Presence type (``<select>``) — ``change`` fires on selection.
    _wireListener(container, '[data-field="presence-type"]', 'change', checkDirty);

    // BOT_TOKEN — ``input`` for typing + a ``change`` fallback for
    // browser autofill or programmatic ``value`` changes.
    _wireListener(container, '[data-field="bot-token"]', 'input', checkDirty);
    _wireListener(container, '[data-field="bot-token"]', 'change', checkDirty);

    // BOT_TOKEN show/hide eye toggle — flips type=password/text +
    // calls ``checkDirty`` so the snapshot re-captures (the snapshot
    // serializes the input value, not its type attribute, but wiring
    // ``checkDirty`` to the eye keeps the dirty-tracking shape uniform
    // with the secrets-row eye pattern at lines 870-887 of
    // ``connector-editor.js``).
    var eyeBtn = container.querySelector('.discord-bot-token-eye-btn');
    if (eyeBtn) {
      eyeBtn.addEventListener('click', function () {
        var input = container.querySelector('[data-field="bot-token"]');
        if (!input) return;
        if (input.type === 'password') {
          input.type = 'text';
          eyeBtn.innerHTML = window.App.icon('eye-off');
          eyeBtn.setAttribute('aria-label', 'Hide value');
        } else {
          input.type = 'password';
          eyeBtn.innerHTML = window.App.icon('eye');
          eyeBtn.setAttribute('aria-label', 'Show value');
        }
        checkDirty();
      });
    }

    // M11 F5 L6 HAT round-8: the L4 Directive-section wiring was
    // REMOVED here (no editable textarea; no per-disclosure summary
    // repaint). The Session-section codeblock in
    // ``connector-editor.js`` wires its own auto-relay listener
    // for the reactive codeblock content swap.

    // ── L5: Invite-section Copy + Recompute buttons ────────────────
    var copyBtn = container.querySelector('[data-testid="connector-invite-copy-btn"]');
    if (copyBtn) {
      copyBtn.addEventListener('click', function () {
        var urlEl = container.querySelector('[data-testid="connector-invite-url"]');
        if (!urlEl || !navigator.clipboard) return;
        var urlText = urlEl.textContent || '';
        navigator.clipboard.writeText(urlText).then(function () {
          var originalLabel = copyBtn.textContent;
          copyBtn.textContent = 'Copied';
          setTimeout(function () {
            copyBtn.textContent = originalLabel || 'Copy';
          }, 1500);
        });
      });
    }
    var recomputeBtn = container.querySelector('[data-testid="connector-invite-recompute-btn"]');
    if (recomputeBtn && inviteAccount) {
      recomputeBtn.addEventListener('click', function () {
        _updateInviteUrlDisplay(container, inviteAccount);
      });
    }
  }

  // ── M11 F2 L4: account resolution from container DOM ───────────────
  //
  // When the substrate calls ``wireEvents(container, checkDirty)``
  // without an explicit account arg, the invite helpers need to know
  // which account.id keys the cache. The editor's mount node now
  // carries a ``data-account-id`` attribute in edit mode (set by
  // ``connector-editor.js:renderConnectorEditor``); we
  // read it instead of parsing ``window.location.hash`` so the helper
  // is fully DOM-anchored and survives any future routing changes.
  // Returns ``null`` when no ``data-account-id`` is present (create
  // mode, stub re-mount, or detached test container).

  function _resolveAccountFromContainer(container) {
    if (!container) return null;
    // The editor's root element is ``.connector-editor``;
    // ``container.closest`` walks up from any nested section. Fallback
    // to the container itself if it IS the mount node (no ancestor
    // with the class).
    var mountEl = null;
    if (typeof container.closest === 'function') {
      mountEl = container.closest('.connector-editor');
    }
    if (!mountEl) mountEl = container;
    var accountId = mountEl.getAttribute && mountEl.getAttribute('data-account-id');
    if (accountId && accountId !== 'new') {
      return { id: accountId };
    }
    return null;
  }

  // ── M11 F1 L5: public namespace for the editor to push application_id
  //
  // ``connector-editor.js:renderTestConnectionBanner`` calls
  // ``setApplicationId(accountId, appId)`` after a successful probe whose
  // ``report.details`` carries an ``application_id``. The function
  // caches the id and, if the invite-section is currently mounted in
  // the DOM, re-renders the URL display.

  window.App.studio.connectorFormDiscord = {
    setApplicationId: function (accountId, appId) {
      if (!accountId || !appId) return;
      _lastApplicationIdByAccount[accountId] = appId;
      // If the invite-section is mounted, re-render its URL display.
      var inviteSection = document.querySelector('[data-testid="connector-invite-section"]');
      if (!inviteSection) return;
      var container = inviteSection.closest('.connector-editor') ||
                      inviteSection.parentElement || inviteSection;
      _updateInviteUrlDisplay(container, { id: accountId });
    },
    // Test-only hooks (deliberately undocumented in the public surface).
    _computeInviteUrl: _computeInviteUrl,
    _DISCORD_INVITE_PERMISSIONS: _DISCORD_INVITE_PERMISSIONS
  };

  // ── Register at module load ────────────────────────────────────────

  window.App.studio.connectorFormRegistry.register('discord', {
    type: 'discord',
    // M11 F5 L6 HAT round-8: ``system_prompt_directive`` removed from
    // ``reservedConfigKeys``. Legacy rows that still carry the key
    // surface in the Advanced kv-table now (instead of being hidden);
    // they have no behavioral effect (the factory ignores the key) but
    // the operator can see / delete the stale entry from the UI.
    //
    // M11 F14 L02: ``guilds`` removed — the top-level "Scope to servers"
    // field was unified onto ``config.allowlist.guilds`` and the v27
    // migration folds + drops any legacy top-level ``guilds``. No
    // dedicated form input remains, so it is no longer reserved.
    // M11 F17: application_id added — see _kvReserved comment above.
    reservedConfigKeys: ['intents', 'presence', 'application_id'],
    renderConnectionFields: renderConnectionFields,
    renderRuntimeConfigFields: renderRuntimeConfigFields,
    renderCredentialsFields: renderCredentialsFields,
    collect: collect,
    snapshot: snapshot,
    wireEvents: wireEvents,
    renderInviteSection: renderInviteSection,
    // M11 F3 L5: positional-to-opts bridge to the shared
    // ``App.studio.discoverableDropdown`` component. The registry
    // calls this hook with a 5- or 6-positional signature; the
    // component takes a single opts object. Body is mechanical — no
    // internal logic beyond the parameter remap.
    //
    // M11 F12 L4 — 6th positional ``extraOpts`` carries the structured-
    // tuple shape opt-in (``{valueShape: 'peer' | 'channel' | 'role'}``).
    // Default is ``{}`` (flat-id shape — pre-L4 behavior unchanged).
    renderDiscoverableDropdown: function (account, axis, currentValues, vocab, onChange, extraOpts) {
      var opts = {
        axis: axis,
        accountId: account.id,
        currentValues: currentValues,
        onChange: onChange,
        vocab: vocab
      };
      if (extraOpts && typeof extraOpts === 'object') {
        if (extraOpts.valueShape) opts.valueShape = extraOpts.valueShape;
      }
      return App.studio.discoverableDropdown(opts);
    }
  });
})();
