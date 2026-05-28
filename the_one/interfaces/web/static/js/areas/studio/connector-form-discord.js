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

  // ── M11 F1 L5: Invite-URL section ──────────────────────────────────
  //
  // The doctor probe at ``_discord.py`` populates
  // ``report.details.application_id`` on the ``application`` check
  // success path. ``connector-editor.js:renderTestConnectionBanner``
  // forwards this to ``setApplicationId`` below (via the namespace
  // export at the bottom of this IIFE), which caches it per-account-id
  // and re-renders the Invite section's URL display.
  //
  // The cache is intentionally ephemeral (module-scope, cleared on
  // reload) — ``application_id`` is not persisted in ``account.config``
  // or any DB column; the operator re-runs Test Connection to refresh.
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

  // Intent axes, in render order. Labels are operator-facing; the keys are
  // the L2 validator's required dict-key set.
  //
  // F5 L6 HAT round-2 #1+#3: copy revised to sentence-case + clarified
  // "Server info" (the GUILDS intent carries guild metadata events; the
  // unrelated Allowlist "Servers" axis is a separate concept gated by
  // ``Scope to servers`` below — see HAT fix #2 for the disambiguation).
  var INTENT_AXES = [
    { key: 'message_content', label: 'Message content' },
    { key: 'members', label: 'Server members' },
    { key: 'guilds', label: 'Server info' }
  ];

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
  // ``data-testid`` (``discord-intents-hint`` / ``discord-guilds-hint``
  // / ``discord-presence-hint``) for parity with the Lifecycle section's
  // ``connector-continuation-hint`` / ``-idle-hint`` sites.

  function _renderRuntimeConfigBody(account) {
    var cfg = (account && account.config) || {};
    var intentsCfg = (typeof cfg.intents === 'object' && cfg.intents) ? cfg.intents : {};
    var guildsCfg = Array.isArray(cfg.guilds) ? cfg.guilds : [];
    var presenceCfg = (typeof cfg.presence === 'object' && cfg.presence) ? cfg.presence : {};

    var html = '';
    var infoIcon = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';

    // ── Intents row (HAT round-2 fix #1) ────────────────────────────
    // Pre-round-2: ``<fieldset><legend>Intents</legend>`` + free-floating
    // info-icon + flat checkbox list. Operator HAT found the fieldset
    // shape, the bare "Intents" label, and the per-axis copy
    // ("Message Content" / "Server Members" / "Servers") all confusing.
    //
    // Round-2: canonical 2-column ``field-row admin-pf-row`` layout —
    // label cell ("Receive messages from:") on the left, checkbox list
    // on the right. Sentence-case copy + "Server info" for the GUILDS
    // intent disambiguates from the Allowlist "Servers" axis. The
    // ``discord-intents-fieldset`` testid migrates to the row container
    // as ``discord-intents-row`` so the "intents block exists" signal
    // survives for tests that asserted presence/absence by testid.
    var intentsTipText = 'Discord event types the bot receives. All on is the safe default.';
    html += '<div class="field-row admin-pf-row discord-intents-row" ' +
            'data-testid="discord-intents-row">';
    html += '<label>Receive messages from:</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + _escapeAttr(intentsTipText) + '" ' +
            'aria-describedby="discord-intents-help-text" ' +
            'data-testid="discord-intents-hint">' +
            infoIcon + '</button>';
    html += '<span id="discord-intents-help-text" class="visually-hidden">' +
            _escapeHtml(intentsTipText) + '</span>';
    html += '<div class="discord-intents-checkbox-list">';
    for (var i = 0; i < INTENT_AXES.length; i++) {
      var axis = INTENT_AXES[i];
      // Default-on when the operator has never set intents (M10 F8 hardcoded
      // default mirror); per-axis ``account.config.intents`` override wins.
      var checked = true;
      if (Object.prototype.hasOwnProperty.call(intentsCfg, axis.key)) {
        checked = !!intentsCfg[axis.key];
      }
      var checkedAttr = checked ? ' checked' : '';
      html += '<label class="discord-intent-row">';
      html += '<input type="checkbox" class="checkbox-primary" data-field="intent-' + axis.key +
              '" data-testid="discord-intent-' + axis.key + '"' + checkedAttr + ' />';
      html += '<span>' + _escapeHtml(axis.label) + '</span>';
      html += '</label>';
    }
    html += '</div>';
    html += '</div>';

    // ── Scope to servers row (HAT round-2 fix #2) ───────────────────
    // Pre-round-2 label "Servers" collided with the Allowlist "Servers"
    // axis. Renamed to "Scope to servers" so the Runtime Config field
    // is unambiguously the Discord guild-scoping setting. Container
    // bumped to the canonical 2-column ``field-row admin-pf-row``
    // layout for typography consistency with the other rows.
    var guildsValue = guildsCfg.join(', ');
    var guildsTipText = 'Comma-separated server IDs. Leave blank to allow all servers the bot is in.';
    html += '<div class="field-row admin-pf-row discord-guilds-row">';
    html += '<label for="cf-discord-guilds">Scope to servers</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + _escapeAttr(guildsTipText) + '" ' +
            'aria-describedby="discord-guilds-help-text" ' +
            'data-testid="discord-guilds-hint">' +
            infoIcon + '</button>';
    html += '<span id="discord-guilds-help-text" class="visually-hidden">' +
            _escapeHtml(guildsTipText) + '</span>';
    html += '<input class="field-input" type="text" id="cf-discord-guilds" data-field="guilds-list" ' +
            'data-testid="discord-guilds-list" value="' + _escapeAttr(guildsValue) +
            '" placeholder="" />';
    html += '</div>';

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

    html += '<div class="field-row admin-pf-row discord-presence-row">';
    html += '<label>Bot status</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + _escapeAttr(presenceTipText) + '" ' +
            'aria-describedby="discord-presence-help-text" ' +
            'data-testid="discord-presence-hint">' +
            infoIcon + '</button>';
    html += '<span id="discord-presence-help-text" class="visually-hidden">' +
            _escapeHtml(presenceTipText) + '</span>';
    html += '<div class="discord-presence-fields">';
    html += '<select class="field-input field-select" data-field="presence-type" data-testid="discord-presence-type">';
    var emptySelected = presenceType === '' ? ' selected' : '';
    html += '<option value=""' + emptySelected + '>(default)</option>';
    for (var p = 0; p < PRESENCE_TYPES.length; p++) {
      var pt = PRESENCE_TYPES[p];
      var sel = (pt === presenceType) ? ' selected' : '';
      var ptLabel = PRESENCE_TYPE_LABELS[pt] || pt;
      html += '<option value="' + _escapeAttr(pt) + '"' + sel + '>' + _escapeHtml(ptLabel) + '</option>';
    }
    html += '</select>';
    html += '<input class="field-input" type="text" data-field="presence-name" data-testid="discord-presence-name" ' +
            'value="' + _escapeAttr(presenceName) + '" placeholder="(e.g., chess, music)" />';
    html += '</div>';
    html += '</div>';

    // ── Additional Config row (HAT round-2 fix #3) ──────────────────
    // Pre-round-2: ``<details><summary>Advanced (kv-table)</summary>``
    // disclosure. Operator HAT found "kv-table" jargon-y and the
    // disclosure-by-default-collapsed shape an unnecessary hop for
    // operators who'd just typed BOT_TOKEN/intents/etc. and might want
    // to add an ad-hoc config key. Round-2 inlines the kv-table under
    // an "Additional Config" subheading in the same 2-column row
    // layout. The ``discord-advanced-kv-disclosure`` testid migrates
    // to the row container as ``discord-additional-config-row`` so the
    // "additional-config block exists" signal survives.
    html += '<div class="field-row admin-pf-row discord-additional-config-row" ' +
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
    var html = '';
    html += '<div class="field-row admin-pf-row discord-credentials-row">';
    html += '<label for="cf-discord-bot-token">';
    html += 'Bot Token';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + _escapeAttr(hintText) + '" ' +
            'aria-describedby="discord-bot-token-help-text" ' +
            'data-testid="connector-bot-token-hint">' +
            infoIcon + '</button>';
    html += '<span id="discord-bot-token-help-text" class="visually-hidden">' +
            _escapeHtml(hintText) + '</span>';
    html += '</label>';
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

  function _readIntentChecked(container, axisKey) {
    var el = container.querySelector('[data-field="intent-' + axisKey + '"]');
    // Default-on when missing (mirrors the render default).
    return el ? !!el.checked : true;
  }

  function _readInputValue(container, fieldName) {
    var el = container.querySelector('[data-field="' + fieldName + '"]');
    return el ? (el.value || '') : '';
  }

  function _splitGuildsList(raw) {
    if (!raw) return [];
    var parts = raw.split(',');
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var trimmed = parts[i].replace(/^\s+|\s+$/g, '');
      if (trimmed) out.push(trimmed);
    }
    return out;
  }

  function collect(container, account, isEdit) {
    var existingCfg = (account && account.config) || {};
    var config = {};
    var secrets = {};

    // ── Intents ──────────────────────────────────────────────────────
    var intents = {
      message_content: _readIntentChecked(container, 'message_content'),
      members: _readIntentChecked(container, 'members'),
      guilds: _readIntentChecked(container, 'guilds')
    };
    var allTrue = intents.message_content && intents.members && intents.guilds;
    var hadIntentsBefore = Object.prototype.hasOwnProperty.call(existingCfg, 'intents');
    // Emit only when at least one checkbox is NOT True OR the operator's
    // prior choice carried an ``intents`` key (round-trip exactly).
    if (!allTrue || hadIntentsBefore) {
      config.intents = intents;
    }

    // ── Guilds ───────────────────────────────────────────────────────
    var guildsRaw = _readInputValue(container, 'guilds-list');
    var guildsList = _splitGuildsList(guildsRaw);
    var hadGuildsBefore = Object.prototype.hasOwnProperty.call(existingCfg, 'guilds');
    // Emit non-empty list OR honor operator clearing a pre-existing list.
    if (guildsList.length > 0 || hadGuildsBefore) {
      config.guilds = guildsList;
    }

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

    return { config: config, secrets: secrets };
  }

  // ── Snapshot: typed-input state → JSON-serializable view ───────────

  function snapshot(container) {
    return {
      intents: {
        message_content: _readIntentChecked(container, 'message_content'),
        members: _readIntentChecked(container, 'members'),
        guilds: _readIntentChecked(container, 'guilds')
      },
      guildsList: _readInputValue(container, 'guilds-list'),
      presenceName: _readInputValue(container, 'presence-name'),
      presenceType: _readInputValue(container, 'presence-type'),
      botTokenValue: _readInputValue(container, 'bot-token')
    };
  }

  // ── Invite section render + DOM mutation helpers (M11 F1 L5) ──────

  function renderInviteSection(account) {
    var accountId = (account && account.id) || '';
    var appId = _lastApplicationIdByAccount[accountId];
    var hintHidden = appId ? ' hidden' : '';
    var urlHidden = appId ? '' : ' hidden';
    var url = appId ? _computeInviteUrl(appId) : '';
    var infoIcon = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';
    var copyIcon = (window.App && window.App.icon) ? window.App.icon('copy') : '⧉';
    var refreshIcon = (window.App && window.App.icon) ? window.App.icon('refresh-cw') : '↻';
    var infoText = 'Open this URL on Discord to add the bot to a server.';

    var html = '';
    // F5 L6 HAT round-7: 3-column field-row pattern
    // (label | info-icon | field-content). Copy + Refresh are icon-only
    // buttons matching the existing connector-pairing-copy-btn precedent.
    // The testid moves from a <section> wrapper (pre-L2) to the
    // outer field-row div so DOM-by-testid lookups keep resolving.
    html += '<div class="field-row admin-pf-row connector-invite-row" ' +
            'data-testid="connector-invite-section">';
    html += '<label>Invite link</label>';
    html += '<button type="button" class="field-info-icon" ' +
            'title="' + _escapeAttr(infoText) + '" ' +
            'aria-describedby="connector-invite-help-text" ' +
            'data-testid="connector-invite-info">' + infoIcon + '</button>';
    html += '<span id="connector-invite-help-text" class="visually-hidden">' +
            _escapeHtml(infoText) + '</span>';
    html += '<div class="connector-invite-field">';
    html += '<span class="connector-invite-hint" ' +
            'data-testid="connector-invite-hint"' + hintHidden + '>' +
            'Refresh connection first to fetch your application ID.' +
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

    function _onIntentChange() {
      if (typeof checkDirty === 'function') checkDirty();
      if (inviteAccount) _updateInviteUrlDisplay(container, inviteAccount);
    }

    // Intent checkboxes — ``change`` (not ``input``) is the canonical
    // event for ``<input type="checkbox">`` state flips across browsers.
    // L5 extends each handler to ALSO recompute the invite-URL display
    // (the display is stable because intents and permissions are
    // orthogonal — but exercising the recompute path proves the
    // permission integer stays pinned at 2147552256).
    _wireListener(container, '[data-field="intent-message_content"]', 'change', _onIntentChange);
    _wireListener(container, '[data-field="intent-members"]', 'change', _onIntentChange);
    _wireListener(container, '[data-field="intent-guilds"]', 'change', _onIntentChange);

    // Guilds list (text) — ``input`` for per-keystroke dirty detection.
    _wireListener(container, '[data-field="guilds-list"]', 'input', checkDirty);

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
    reservedConfigKeys: ['intents', 'guilds', 'presence'],
    renderConnectionFields: renderConnectionFields,
    renderRuntimeConfigFields: renderRuntimeConfigFields,
    renderCredentialsFields: renderCredentialsFields,
    collect: collect,
    snapshot: snapshot,
    wireEvents: wireEvents,
    renderInviteSection: renderInviteSection,
    // M11 F3 L5: positional-to-opts bridge to the shared
    // ``App.studio.discoverableDropdown`` component. The registry
    // calls this hook with a 5-positional signature; the component
    // takes a single opts object. Body is mechanical — no internal
    // logic beyond the parameter remap.
    renderDiscoverableDropdown: function (account, axis, currentValues, vocab, onChange) {
      return App.studio.discoverableDropdown({
        axis: axis,
        accountId: account.id,
        currentValues: currentValues,
        onChange: onChange,
        vocab: vocab
      });
    }
  });
})();
