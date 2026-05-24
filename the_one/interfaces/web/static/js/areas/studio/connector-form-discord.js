// App.studio.connectorFormRegistry — Discord entry (M11 F1 L4).
//
// First consumer of the L3 registry substrate. Registers the
// ``'discord'`` entry at module load time so the connector-account
// editor renders typed Discord-shaped fields (intents fieldset, guilds
// list, presence editor, masked BOT_TOKEN, Advanced kv-table
// disclosure) instead of falling back to the generic kv-table.
//
// Contract:
//   - L3's ``connector-form-registry.js`` MUST load before this file
//     (script-tag ordering in ``index.html``). If the registry is
//     missing at module-load time, this script throws — surfaced as a
//     console error so the operator sees the misorder immediately.
//   - L2's API validator (``api.py:_validate_connector_account_config``)
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

  // ── M11 F2 L4: System Prompt Directive defaults ───────────────────
  //
  // VERBATIM copies of the Python constants in
  // ``the_one/agent/config.py``. The Studio's directive section
  // renders these as read-only ``<pre><code>`` blocks inside the three
  // ``<details>`` disclosures, so the operator authoring their own
  // ``system_prompt_directive`` sees exactly which default fires for
  // each ``(connector_attached, send_tool_enabled, auto_relay)`` state
  // and what their text will be appended to.
  //
  // CONTRACT: each constant must equal its Python twin byte-for-byte.
  // A future flight that edits the Python constants MUST update these
  // JS twins in the same atomic diff (the leg artifact's
  // ``test_three_default_disclosures_render_verbatim_python_text``
  // test pins the byte-equality). The trailing comments name the
  // Python symbols so a grep on the Python symbol surfaces the JS
  // twin instantly.

  // Python twin: ``the_one/agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE``.
  var _DIRECTIVE_AUTO_RELAY_DEFAULT = (
    'This conversation is attached to a connector account on an external ' +
    'platform (Discord, Slack, etc.). Auto-relay is ON: your plaintext ' +
    'replies in this session ARE automatically delivered to platform peers ' +
    '— treat the conversation as the platform conversation itself. Do NOT ' +
    'ask the operator for permission to respond on the platform; do NOT ' +
    'narrate that you\'re \'using send_to_platform_channel\'; just reply ' +
    'naturally as you would in any chat. Messages tagged ' +
    '``visibility="platform"`` in the history came from platform peers; ' +
    'messages tagged ``visibility="operator"`` came from the operator\'s ' +
    'private local Chat console (operator-only — these are NOT relayed). ' +
    'If you need to send a message to a different channel or thread on ' +
    'the platform (not the current channel), use the ' +
    '``send_to_platform_channel`` tool explicitly with a target ' +
    'specifying that destination.'
  );

  // Python twin: ``the_one/agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE``.
  var _DIRECTIVE_TOOL_ENABLED_DEFAULT = (
    'This conversation is attached to a connector account on an external ' +
    'platform (Discord, Slack, etc.). Messages tagged ``visibility="platform"`` ' +
    'in the history came from platform peers; messages tagged ' +
    '``visibility="operator"`` came from the operator\'s private local Chat ' +
    'console. When a platform-peer message in this session needs a response, ' +
    'you MUST call the ``send_to_platform_channel`` tool to deliver your reply ' +
    'to peers — your plain-text replies in this session reach only the ' +
    'operator\'s local console, NOT peers. The operator console is for the ' +
    'operator to direct or observe you; only deliberate ``send_to_platform_channel`` ' +
    'calls reach the platform. The tool takes a target (account_id, channel_id, ' +
    'and optional thread_id) plus content. Use the account_id and channel_id ' +
    'from the platform-inbound message you\'re replying to.'
  );

  // Python twin: ``the_one/agent/config.py:_CONNECTOR_TOOL_DISABLED_DIRECTIVE``.
  var _DIRECTIVE_TOOL_DISABLED_DEFAULT = (
    'This conversation is attached to a connector account on an external ' +
    'platform, but the platform-send capability is currently DISABLED by ' +
    'the operator. Your replies in this session reach the operator only ' +
    '— they do not reach the external platform. The ' +
    '`send_to_platform_channel` tool is not available right now. Do not ' +
    'claim to have sent anything to the platform.'
  );

  // ── M11 F1 L5: Invite-URL section ──────────────────────────────────
  //
  // The doctor probe at ``_discord.py`` populates
  // ``report.details.application_id`` on the ``application`` check
  // success path. ``connector-account-editor.js:renderTestConnectionBanner``
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
  var INTENT_AXES = [
    { key: 'message_content', label: 'Message Content' },
    { key: 'members', label: 'Server Members' },
    { key: 'guilds', label: 'Servers' }
  ];

  function _escapeHtml(s) {
    return window.App.escapeHtml(s == null ? '' : String(s));
  }

  function _escapeAttr(s) {
    return window.App.escapeAttr(s == null ? '' : String(s));
  }

  // ── Render: Connection (intents + guilds + presence + advanced) ────

  function renderConnectionFields(account, isCreate) {
    var cfg = (account && account.config) || {};
    var intentsCfg = (typeof cfg.intents === 'object' && cfg.intents) ? cfg.intents : {};
    var guildsCfg = Array.isArray(cfg.guilds) ? cfg.guilds : [];
    var presenceCfg = (typeof cfg.presence === 'object' && cfg.presence) ? cfg.presence : {};

    var html = '';

    // ── Intents fieldset ─────────────────────────────────────────────
    html += '<fieldset class="discord-intents-fieldset" data-testid="discord-intents-fieldset">';
    html += '<legend>Intents</legend>';
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
      html += '<input type="checkbox" data-field="intent-' + axis.key +
              '" data-testid="discord-intent-' + axis.key + '"' + checkedAttr + ' />';
      html += '<span>' + _escapeHtml(axis.label) + '</span>';
      html += '</label>';
    }
    html += '<small class="form-hint">Discord gateway intents — controls which ' +
            'event types the bot receives. All on is the safe default; disable ' +
            'individual intents only if you understand the consequences.</small>';
    html += '</fieldset>';

    // ── Guilds list ──────────────────────────────────────────────────
    var guildsValue = guildsCfg.join(', ');
    html += '<div class="discord-guilds-row">';
    html += '<label for="cf-discord-guilds">Guilds</label>';
    html += '<input type="text" id="cf-discord-guilds" data-field="guilds-list" ' +
            'data-testid="discord-guilds-list" value="' + _escapeAttr(guildsValue) +
            '" placeholder="" />';
    html += '<small class="form-hint">Comma-separated Discord guild IDs (digit-only).</small>';
    html += '</div>';

    // ── Presence editor ──────────────────────────────────────────────
    var presenceName = (typeof presenceCfg.name === 'string') ? presenceCfg.name : '';
    var presenceType = (typeof presenceCfg.type === 'string') ? presenceCfg.type : '';

    html += '<div class="discord-presence-row">';
    html += '<label>Presence</label>';
    html += '<input type="text" data-field="presence-name" data-testid="discord-presence-name" ' +
            'value="' + _escapeAttr(presenceName) + '" placeholder="Activity name" />';
    html += '<select data-field="presence-type" data-testid="discord-presence-type">';
    var emptySelected = presenceType === '' ? ' selected' : '';
    html += '<option value=""' + emptySelected + '>(default)</option>';
    for (var p = 0; p < PRESENCE_TYPES.length; p++) {
      var pt = PRESENCE_TYPES[p];
      var sel = (pt === presenceType) ? ' selected' : '';
      html += '<option value="' + _escapeAttr(pt) + '"' + sel + '>' + _escapeHtml(pt) + '</option>';
    }
    html += '</select>';
    html += '<small class="form-hint">Activity name + type for the bot\'s status. ' +
            'Leave both blank to use the default presence.</small>';
    html += '</div>';

    // ── Advanced kv-table disclosure ─────────────────────────────────
    html += '<details class="discord-advanced-kv-disclosure" ' +
            'data-testid="discord-advanced-kv-disclosure">';
    html += '<summary>Advanced (kv-table)</summary>';
    // L4 contract: ``renderConfigKvTable`` is exposed on
    // ``window.App.studio`` for this exact mount point. Triple-guard
    // for early-load (the substrate exposes it at IIFE end, same script).
    var renderKv = (window.App && window.App.studio && window.App.studio.renderConfigKvTable) || null;
    if (typeof renderKv === 'function') {
      html += renderKv(account);
    }
    html += '</details>';

    return html;
  }

  // ── Render: Credentials (typed BOT_TOKEN with masked-edit) ─────────

  function renderCredentialsFields(account) {
    var secrets = (account && account.secrets) || {};
    var masked = secrets.BOT_TOKEN != null ? String(secrets.BOT_TOKEN) : '';

    var html = '';
    html += '<div class="discord-credentials-row">';
    html += '<label for="cf-discord-bot-token">Bot Token</label>';
    html += '<div class="api-key-wrap">';
    html += '<input class="kv-value-secret" type="password" id="cf-discord-bot-token" ' +
            'data-field="bot-token" data-testid="discord-bot-token" ' +
            'value="' + _escapeAttr(masked) + '" data-original-masked="' + _escapeAttr(masked) +
            '" placeholder="Bot token" />';
    html += '<button class="api-key-eye discord-bot-token-eye-btn" type="button" ' +
            'data-testid="discord-bot-token-eye-btn" aria-label="Show value">' +
            window.App.icon('eye') + '</button>';
    html += '</div>';
    html += '<small class="form-hint">Discord bot token. Stored encrypted at rest; ' +
            'shown masked on read.</small>';
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

    // ── M11 F2 L4: System Prompt Directive ──────────────────────────
    // Trim leading/trailing whitespace per UI convention. Empty value
    // (after trim) → OMIT the key entirely (L3's API validator rejects
    // empty strings; emit-and-reject would be a UX bug).
    var directiveEl = container.querySelector('[data-field="system-prompt-directive"]');
    if (directiveEl) {
      var directiveValue = (directiveEl.value || '').replace(/^\s+|\s+$/g, '');
      if (directiveValue) {
        config.system_prompt_directive = directiveValue;
      }
    }

    return { config: config, secrets: secrets };
  }

  // ── Snapshot: typed-input state → JSON-serializable view ───────────

  function snapshot(container) {
    // M11 F2 L4: ``systemPromptDirective`` is the raw textarea value
    // (NOT trimmed) so the dirty-tracker fires on any whitespace-only
    // edit; symmetric with the secrets-row snapshot pattern.
    var directiveEl = container.querySelector('[data-field="system-prompt-directive"]');
    var systemPromptDirective = directiveEl ? (directiveEl.value || '') : '';
    return {
      intents: {
        message_content: _readIntentChecked(container, 'message_content'),
        members: _readIntentChecked(container, 'members'),
        guilds: _readIntentChecked(container, 'guilds')
      },
      guildsList: _readInputValue(container, 'guilds-list'),
      presenceName: _readInputValue(container, 'presence-name'),
      presenceType: _readInputValue(container, 'presence-type'),
      botTokenValue: _readInputValue(container, 'bot-token'),
      systemPromptDirective: systemPromptDirective
    };
  }

  // ── Invite section render + DOM mutation helpers (M11 F1 L5) ──────

  function renderInviteSection(account) {
    var accountId = (account && account.id) || '';
    var appId = _lastApplicationIdByAccount[accountId];
    var hintHidden = appId ? ' hidden' : '';
    var urlHidden = appId ? '' : ' hidden';
    var url = appId ? _computeInviteUrl(appId) : '';

    var html = '';
    html += '<section class="editor-section connector-invite-section" ' +
            'data-testid="connector-invite-section">';
    html += '<div class="section-title">Invite</div>';
    html += '<p class="connector-invite-hint" ' +
            'data-testid="connector-invite-hint"' + hintHidden + '>' +
            'Run Test Connection first to fetch your application ID.' +
            '</p>';
    html += '<div class="connector-invite-url-wrap" ' +
            'data-testid="connector-invite-url-wrap"' + urlHidden + '>';
    html += '<code class="connector-invite-url" ' +
            'data-testid="connector-invite-url">' + _escapeHtml(url) + '</code>';
    html += '<button type="button" class="btn-outlined-primary connector-invite-copy-btn" ' +
            'data-testid="connector-invite-copy-btn">Copy</button>';
    html += '<button type="button" class="btn-outlined-primary connector-invite-recompute-btn" ' +
            'data-testid="connector-invite-recompute-btn">Recompute</button>';
    html += '</div>';
    html += '</section>';
    return html;
  }

  // ── M11 F2 L4: System Prompt Directive section ────────────────────
  //
  // Edit-mode-only section mounted on the General tab between Pairing
  // and Attached Agents. Renders a textarea for the operator's
  // per-account directive (APPEND-mode — substrate-enforced by L3) +
  // three read-only ``<details>`` disclosures showing the verbatim
  // Python defaults for each ``(connector_attached, send_tool_enabled,
  // auto_relay)`` state-triple. The disclosure for the account's
  // currently-active state gets a ``(this account's current)``
  // annotation that lives in the ``<summary>`` and repaints live on
  // auto-relay toggles.
  //
  // The summary text is rendered EMPTY at initial mount; the SOLE
  // writer of summary ``textContent`` is ``_updateDirectiveAnnotation``,
  // which is called once at ``wireEvents`` time AND on every auto-relay
  // checkbox change. Same code path = byte-stable summary text
  // (no escapeHtml-vs-textContent asymmetry between initial render and
  // post-toggle re-render).

  function renderDirectiveSection(account) {
    var cfg = (account && account.config) || {};
    var existingDirective = (typeof cfg.system_prompt_directive === 'string')
      ? cfg.system_prompt_directive
      : '';

    var html = '';
    html += '<section class="editor-section connector-directive-section" ' +
            'data-testid="connector-account-directive-section">';
    html += '<div class="section-title">System Prompt Directive</div>';

    html += '<textarea data-field="system-prompt-directive" ' +
            'data-testid="connector-account-system-prompt-directive" ' +
            'rows="6" placeholder="(leave empty for no override)">' +
            _escapeHtml(existingDirective) + '</textarea>';
    html += '<small class="form-hint">Your text is appended to whichever ' +
            'default fires for this account\'s current state. Empty = no override.</small>';

    // Three disclosures. Summaries are rendered with EMPTY content
    // here; ``_updateDirectiveAnnotation`` is called once at
    // ``wireEvents`` time to set the initial textContent, guaranteeing
    // byte-identical text between initial render and post-auto-relay-
    // toggle re-render (single code path — no escapeHtml-vs-textContent
    // asymmetry).
    html += _renderDirectiveDisclosure('auto-relay-on', _DIRECTIVE_AUTO_RELAY_DEFAULT);
    html += _renderDirectiveDisclosure('auto-relay-off', _DIRECTIVE_TOOL_ENABLED_DEFAULT);
    html += _renderDirectiveDisclosure('tool-disabled', _DIRECTIVE_TOOL_DISABLED_DEFAULT);

    html += '</section>';
    return html;
  }

  function _renderDirectiveDisclosure(stateKey, defaultText) {
    var html = '<details class="connector-directive-disclosure" ' +
               'data-state-key="' + _escapeAttr(stateKey) + '">';
    // Summary text intentionally empty here — initialized by
    // ``_updateDirectiveAnnotation`` post-mount via ``textContent``.
    html += '<summary data-testid="directive-default-' +
            _escapeAttr(stateKey) + '-summary"></summary>';
    html += '<pre><code data-testid="directive-default-' +
            _escapeAttr(stateKey) + '-text">' +
            _escapeHtml(defaultText) + '</code></pre>';
    html += '</details>';
    return html;
  }

  function _updateDirectiveAnnotation(container) {
    if (!container) return;
    var autoRelayEl = container.querySelector('[data-field="auto_relay_platform_replies"]');
    // Default to autoRelay=true when checkbox isn't found (matches
    // ``account.config.auto_relay_platform_replies`` absent → True at
    // dispatcher consume time per M10 F8 L11 HAT Fix #4 semantics).
    var autoRelay = autoRelayEl ? !!autoRelayEl.checked : true;

    var onSummary = container.querySelector(
      '[data-testid="directive-default-auto-relay-on-summary"]'
    );
    var offSummary = container.querySelector(
      '[data-testid="directive-default-auto-relay-off-summary"]'
    );
    var disabledSummary = container.querySelector(
      '[data-testid="directive-default-tool-disabled-summary"]'
    );

    // Guards keep this a no-op in create mode (registry-dispatch-create-
    // mode-AC) where the directive section is absent → the summaries
    // don't exist → the auto-relay checkbox change still fires but
    // querySelector returns null for each.
    if (onSummary) {
      onSummary.textContent = autoRelay
        ? "When auto-relay is ON (this account's current)"
        : 'When auto-relay is ON';
    }
    if (offSummary) {
      offSummary.textContent = autoRelay
        ? 'When auto-relay is OFF and platform-send tool is enabled'
        : "When auto-relay is OFF and platform-send tool is enabled (this account's current)";
    }
    // Tool-disabled is an AGENT-level setting; the account editor has
    // no agent context, so the annotation can NEVER land here from
    // this surface.
    if (disabledSummary) {
      disabledSummary.textContent = 'When the platform-send tool is disabled';
    }
  }

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
    // ``connector-account-editor.js``).
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

    // ── L4: Directive section wiring ───────────────────────────────
    // (a) initial population of disclosure summaries — one call at
    //     mount time; same code path as the auto-relay change handler
    //     guarantees byte-stable summary text.
    _updateDirectiveAnnotation(container);

    // (b) directive textarea input → dirty tracker. Per-keystroke so
    //     the dirty-state shape matches the other text-input fields.
    _wireListener(container, '[data-field="system-prompt-directive"]', 'input', checkDirty);

    // (c) auto-relay change → repaint annotation. The substrate's
    //     existing change listener on the same element also fires
    //     ``checkDirty`` (attachStaticListeners); the two listeners
    //     are independent and additive — no conflict, no double
    //     dirty-fire (checkDirty is idempotent).
    var autoRelayEl = container.querySelector('[data-field="auto_relay_platform_replies"]');
    if (autoRelayEl) {
      autoRelayEl.addEventListener('change', function () {
        _updateDirectiveAnnotation(container);
      });
    }

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
  // ``connector-account-editor.js:renderConnectorAccountEditor``); we
  // read it instead of parsing ``window.location.hash`` so the helper
  // is fully DOM-anchored and survives any future routing changes.
  // Returns ``null`` when no ``data-account-id`` is present (create
  // mode, stub re-mount, or detached test container).

  function _resolveAccountFromContainer(container) {
    if (!container) return null;
    // The editor's root element is ``.connector-account-editor``;
    // ``container.closest`` walks up from any nested section. Fallback
    // to the container itself if it IS the mount node (no ancestor
    // with the class).
    var mountEl = null;
    if (typeof container.closest === 'function') {
      mountEl = container.closest('.connector-account-editor');
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
  // ``connector-account-editor.js:renderTestConnectionBanner`` calls
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
      var container = inviteSection.closest('.connector-account-editor') ||
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
    // M11 F2 L4: ``system_prompt_directive`` is rendered through the
    // entry's typed directive surface; reserve it so the Advanced
    // kv-table on Discord accounts does NOT also render it as a row.
    reservedConfigKeys: ['intents', 'guilds', 'presence', 'system_prompt_directive'],
    renderConnectionFields: renderConnectionFields,
    renderCredentialsFields: renderCredentialsFields,
    collect: collect,
    snapshot: snapshot,
    wireEvents: wireEvents,
    renderInviteSection: renderInviteSection,
    renderDirectiveSection: renderDirectiveSection,
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
