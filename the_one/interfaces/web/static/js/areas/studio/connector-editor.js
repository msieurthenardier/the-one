// App.studio.renderConnectorEditor — Studio connector-editor section
// (Mission 23 Flight 2 Leg 2, DD-9). Since M25 F3 L4a connectors are rows of
// the Library list (studio.js) and routed (`#library/connectors/~new|{id}`);
// the tile grid is retired.
//
// One file, mirroring mcp-server-editor.js but SMALLER — a minimal CRUD
// form, not a live-status/discoverable-tool surface. Fields: name, type, token (masked, per-key __MASKED__ round-
// trip via the SAME `_looks_masked` contract the backend uses), default
// agent (dropdown sourced from the live agents list), allowlist (peers +
// channels, newline-separated), always-listen channels, channel→agent map
// (simple key/value rows), doctor button + result, pairing-code button +
// result. No live-status polling, no discoverable dropdowns — deliberate
// (DD-9 trade-off).
//
// Built entirely via document.createElement + textContent assignment (the
// _el helper below), NOT string-concatenated HTML sinks — Mission 17
// Flight 1's dynamic-sink baseline freeze (see tests/test_ui_guards.py)
// forbids new dynamic HTML-sink call sites. This mirrors the current-
// generation Studio pattern (see self-configuration-tab.js), NOT the
// pre-freeze string-template style still visible in mcp-server-editor.js
// and agent-editor.js (grandfathered baseline entries). The container
// clears below assign a bare empty string literal to the sink property,
// which the guard's own rule classifies as static (exempt), not dynamic.
//
// M25 F3 L4b (DD2): Back (`onBack`) is retired. The header carries the
// breadcrumb "Library / Connectors" (its group a link to
// `#library/connectors`) and the unsaved caption at the start of
// `.form-actions`, whose text follows the editor's dirty reports.
//
// Mission 23 Flight 3 Leg 2 (DD-6): `config.enabled` is now a persisted
// key (default true, absent key = enabled, no migration). Every connector
// still starts listening on create (unless created with `enabled: false`)
// and stops on delete; PUT branches on the NEW row's effective `enabled`
// value only — true restarts (today's stop+start), false stops and does
// NOT restart, regardless of the prior value (api.py `update_connector`).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // ── DOM-builder micro-helpers (no innerHTML anywhere below) ──────────

  function _el(tag, opts) {
    var e = document.createElement(tag);
    opts = opts || {};
    if (opts.className) e.className = opts.className;
    if (opts.text !== undefined) e.textContent = opts.text;
    return e;
  }

  function _btn(className, testid, text) {
    var b = _el('button', { className: className, text: text });
    b.type = 'button';
    if (testid) b.setAttribute('data-testid', testid);
    return b;
  }

  function _input(type, field, value, placeholder) {
    var i = _el('input', { className: 'field-input' });
    i.type = type;
    i.setAttribute('data-field', field);
    i.value = value || '';
    if (placeholder) i.placeholder = placeholder;
    return i;
  }

  function _textarea(field, value, rows, placeholder) {
    var t = _el('textarea', { className: 'field-textarea' });
    t.setAttribute('data-field', field);
    t.rows = rows;
    t.value = value || '';
    if (placeholder) t.placeholder = placeholder;
    return t;
  }

  function _select(field, options, selectedValue) {
    var s = _el('select', { className: 'field-input field-select' });
    s.setAttribute('data-field', field);
    for (var i = 0; i < options.length; i++) {
      var opt = _el('option', { text: options[i].label });
      opt.value = options[i].value;
      if (options[i].value === selectedValue) opt.selected = true;
      s.appendChild(opt);
    }
    return s;
  }

  // HAT inline fix (Mission 23 Flight 3 Leg 4): the bare browser checkbox
  // rendered orphaned/centered under its label. Reuses the established
  // `.tool-enable-switch` iOS-style toggle (admin.css, scoped to both
  // `.area-admin` and `.area-studio` — see components.css's note that it is
  // the documented single-binary-flip primitive) instead of inventing a new
  // control. Label-left `.field-row` layout (not the stacked `.field-group`
  // the other connector fields use) mirrors the same single-toggle
  // exception documented in tools-editor.js's renderEnabledRow. The real
  // `<input type="checkbox">` stays in the DOM (visually hidden via
  // opacity:0, not display:none) — focusable, space-togglable, and
  // `<label for>`-associated, so it keeps the same a11y contract as a bare
  // checkbox. `data-field` is preserved for save-time `.checked` reads.
  function _toggleRow(section, labelText, id, field, checked) {
    var row = _el('div', { className: 'field-row connector-enabled-row' });
    row.setAttribute('data-field-name', field);
    var rowLabel = _el('label', { text: labelText });
    rowLabel.setAttribute('for', id);
    var swLabel = _el('label', { className: 'tool-enable-switch' });
    swLabel.title = labelText + (checked ? ' (on)' : ' (off)');
    var input = _el('input', {});
    input.type = 'checkbox';
    input.id = id;
    input.setAttribute('data-field', field);
    input.checked = checked;
    input.setAttribute('aria-label', labelText);
    var track = _el('span', { className: 'tool-enable-switch-track' });
    track.setAttribute('aria-hidden', 'true');
    swLabel.appendChild(input);
    swLabel.appendChild(track);
    row.appendChild(rowLabel);
    row.appendChild(swLabel);
    section.appendChild(row);
    return input;
  }

  function _fieldGroup(section, labelText, id, inputEl) {
    var wrap = _el('div', { className: 'field-group' });
    var label = _el('label', { text: labelText });
    label.setAttribute('for', id);
    inputEl.id = id;
    wrap.appendChild(label);
    wrap.appendChild(inputEl);
    section.appendChild(wrap);
    return inputEl;
  }

  function _section(container, titleText) {
    var sec = _el('div', { className: 'editor-section' });
    sec.appendChild(_el('div', { className: 'section-title', text: titleText }));
    container.appendChild(sec);
    return sec;
  }

  // ── Status LED (Squawk 0045: MCP-panel parity) ────────────────────────
  // Reuses the shared `indicator-led` primitive (components.css) — no new
  // CSS component. Maps a doctor probe's `status` ("ok"/"degraded"/
  // "failed", DoctorReport in the_one/connectors/base.py) plus the /test
  // response's `disabled` flag onto the LED's four available modifier
  // states (success/warning/danger/idle). Per the squawk's pinned
  // decision #2, a disabled connector always shows idle regardless of the
  // underlying probe status — disabled reads as "not currently trying to
  // connect", not as a health verdict.
  function _connectorLedState(status, disabled) {
    if (disabled) return 'idle';
    if (status === 'ok') return 'success';
    if (status === 'degraded') return 'warning';
    if (status === 'failed') return 'danger';
    return 'idle';
  }

  function _connectorLedLabel(status, disabled) {
    if (disabled) return 'Disabled';
    if (status === 'ok') return 'Connected';
    if (status === 'degraded') return 'Degraded';
    if (status === 'failed') return 'Not connected';
    return 'Checking connection…';
  }

  // ── Inline setup steps (Squawk 0046) ──────────────────────────────────
  // Pinned FD decision: a small STATIC per-type step list, NOT a rendering
  // of docs/connector-setup.md and NOT any fetch/sync machinery — the doc
  // stays the source of truth (it carries its own "verified against" date)
  // and this list is a signpost, condensed by hand to agree with it.
  // Bullets are kept short and each platform's list names the ONE thing
  // that silently breaks setup for that platform (Discord: the Message
  // Content intent; Telegram: /setprivacy Disable) plus where the token
  // comes from. Pairing is referenced by name only (its own section below
  // carries the actual help line) so the two don't drift out of sync on
  // their own. `stub` (and any other/unknown type) intentionally gets no
  // entry — the section hides itself in that case.
  var SETUP_STEPS_BY_TYPE = {
    discord: [
      'Create an application at the Discord developer portal ' +
        '(discord.com/developers/applications) → Bot tab → Add Bot. Copy the ' +
        'token immediately — Discord shows it once — and paste it into Token above.',
      'Bot tab → Privileged Gateway Intents → enable Message Content Intent. ' +
        'Skip this and every inbound message arrives with empty content — the ' +
        'connector looks "connected but silent".',
      'OAuth2 → URL Generator → scopes `bot`, permissions Send Messages + Read ' +
        'Message History. Open the generated URL and pick the target server.',
      'Set a default agent below, then save and use the Pairing section to ' +
        'admit the first peer.',
      'Add the channel id(s) to Admission below (and to Always-listen for ' +
        'reply-with-no-mention).'
    ],
    telegram: [
      'DM @BotFather → /newbot → follow the prompts. BotFather returns the ' +
        'token — paste it into Token above.',
      'Message @BotFather → /setprivacy → Disable, BEFORE adding the bot to ' +
        'any group it should always-listen in. Skip this and the bot only sees ' +
        'commands, @mentions, and replies to its own messages in a group — not ' +
        'retroactive once a message is missed.',
      'Set a default agent below, then save and use the Pairing section to ' +
        'admit the first peer.',
      "Add the bot to a group like any member, then add the group's chat id " +
        'to Admission below.'
    ]
  };

  function _linesToArray(text) {
    return String(text || '')
      .split('\n')
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
  }

  function _arrayToLines(arr) {
    return (arr || []).join('\n');
  }

  // ── Editor ────────────────────────────────────────────────────────────

  function renderConnectorEditor(container, connector, connectorTypes, agents, callbacks) {
    callbacks = callbacks || {};
    var isCreate = !connector;
    var types = connectorTypes || [];
    var cfg = connector || {
      name: '',
      type: (types[0] && types[0].value) || 'discord',
      config: {},
      secrets: {}
    };
    var config = cfg.config || {};
    var allowlist = config.allowlist || {};

    container.innerHTML = ''; // static clear — exempt from the sink freeze

    // ── Header ────────────────────────────────────────────────────────
    // M25 F3 L4b (DD2): the breadcrumb "Library / Connectors" is the first
    // child of .editor-header-text (built here, during construction), in edit
    // and create modes. Its group segment links to the section root: with Back
    // retired it is the visible way to close the item. studio.js routes the
    // click (the router's guard asks once about a dirty editor) and focuses
    // the item's row after the close (DD8).
    var header = _el('div', { className: 'editor-header' });
    var headerText = _el('div', { className: 'editor-header-text' });
    var crumb = _el('div', { className: 'editor-breadcrumb', text: 'Library / ' });
    var crumbLink = _el('a', { className: 'editor-breadcrumb-link', text: 'Connectors' });
    crumbLink.setAttribute('href', window.App.router.href({ destination: 'library', section: 'connectors' }));
    crumbLink.setAttribute('data-testid', 'editor-breadcrumb-link');
    crumb.appendChild(crumbLink);
    headerText.appendChild(crumb);
    var connTitle = _el('h1', {
      className: 'editor-title',
      text: isCreate ? 'New Connector' : (cfg.name || '')
    });
    connTitle.setAttribute('tabindex', '-1');
    headerText.appendChild(connTitle);

    // Squawk 0045: connection-status LED, edit mode only (no LED on the
    // create form — nothing to probe until the connector exists). Sits in
    // the header next to the connector name, not inside Diagnostics — the
    // operator's "auto green dot" is at-a-glance, not a diagnosis tool.
    var statusLedEl = null;
    var statusLabelEl = null;
    if (!isCreate) {
      var statusRow = _el('div', { className: 'connector-status-row' });
      statusLedEl = _el('span', { className: 'indicator-led indicator-led--idle' });
      statusLedEl.setAttribute('data-testid', 'connector-status-led');
      statusLedEl.setAttribute('aria-label', 'Checking connection…');
      statusRow.appendChild(statusLedEl);
      statusLabelEl = _el('span', {
        className: 'connector-status-label',
        text: 'Checking connection…'
      });
      statusLabelEl.setAttribute('data-testid', 'connector-status-label');
      statusRow.appendChild(statusLabelEl);
      headerText.appendChild(statusRow);
    }
    header.appendChild(headerText);

    // The cluster opens with the stable unsaved caption (DD2, A15): its text
    // follows the editor's dirty reports (reportDirty below). Back is retired.
    // Cancel on the create form abandons creation (DD8), so it is enabled
    // from first render, clean or dirty (the M25 F3 behavior-gate fix); in
    // edit mode it reverts, and stays disabled until a field changes.
    var actions = _el('div', { className: 'form-actions' });
    var unsavedEl = _el('span', { className: 'editor-unsaved' });
    unsavedEl.setAttribute('role', 'status');
    unsavedEl.setAttribute('data-testid', 'editor-unsaved');
    var cancelBtn = _btn('btn-outlined-primary cancel-btn', 'cancel-connector-btn', 'Cancel');
    cancelBtn.disabled = !isCreate;
    var saveBtn = _btn('btn-filled-primary save-btn', 'save-connector-btn', isCreate ? 'Create' : 'Save');
    saveBtn.disabled = true;
    var errorEl = _el('span', { className: 'editor-error' });
    actions.appendChild(unsavedEl);
    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);
    actions.appendChild(errorEl);
    header.appendChild(actions);
    container.appendChild(header);

    // ── Identity ─────────────────────────────────────────────────────
    var identity = _section(container, 'Identity');
    _fieldGroup(identity, 'Name', 'conn-name', _input('text', 'name', cfg.name, 'connector-name'));
    var typeOptions = types.map(function (t) { return { value: t.value, label: t.label }; });
    var typeSelectEl = _select('type', typeOptions, cfg.type);
    _fieldGroup(identity, 'Type', 'conn-type', typeSelectEl);
    _fieldGroup(
      identity, 'Token', 'conn-token',
      _input('password', 'token', (cfg.secrets && cfg.secrets.token) || '', 'Platform credential')
    );
    // Checked-state trap (DD-6): render from `!== false`, never a truthy
    // check — `!!config.enabled` is falsy for the absent-key legacy case
    // and would invert the documented default (absent key = enabled).
    _toggleRow(identity, 'Enabled', 'conn-enabled', 'enabled', config.enabled !== false);

    // ── Setup steps (Squawk 0046) ───────────────────────────────────────
    // Rendered on BOTH create and edit — a first-timer needs this most on
    // the create form, before anything else on the page helps them. Kept
    // live against the Type select so switching types before saving
    // updates the bullets immediately.
    var setupSteps = _section(container, 'Setup steps');
    setupSteps.setAttribute('data-testid', 'connector-setup-steps');
    var setupStepsList = _el('ul', { className: 'connector-setup-steps-list' });
    setupSteps.appendChild(setupStepsList);
    // Squawk 0046 review fix (dead link): only `/static` is mounted
    // (the_one/interfaces/web/app.py), so `docs/` is not served over HTTP —
    // an `<a href="docs/connector-setup.md">` 404s. No route/static mount
    // for `docs/` (new HTTP surface + security-posture question, out of
    // scope for a squawk) and no external GitHub link (this is a
    // local-first app that may run offline; an outbound link is an
    // operator choice, not an implementer's). Grepped the rest of the app
    // for an existing "point at repo docs" pattern first — none exists —
    // so this renders as plain text via the shared `.field-hint` muted-text
    // primitive (components.css), naming the file path for the operator to
    // open from the repo checkout themselves.
    var setupStepsDocRef = _el('span', {
      className: 'field-hint connector-setup-steps-doc-ref',
      text: 'Full walkthrough: docs/connector-setup.md (in the repo)'
    });
    setupStepsDocRef.setAttribute('data-testid', 'connector-setup-steps-doc-ref');
    setupSteps.appendChild(setupStepsDocRef);

    function updateSetupSteps() {
      var type = typeSelectEl.value;
      var steps = SETUP_STEPS_BY_TYPE[type];
      setupStepsList.innerHTML = ''; // static clear — exempt from the sink freeze
      if (!steps) {
        setupSteps.hidden = true;
        return;
      }
      setupSteps.hidden = false;
      setupStepsList.setAttribute('data-testid', 'connector-setup-steps-list-' + type);
      steps.forEach(function (stepText) {
        setupStepsList.appendChild(_el('li', { text: stepText }));
      });
    }
    updateSetupSteps();
    typeSelectEl.addEventListener('change', updateSetupSteps);

    // ── Binding ──────────────────────────────────────────────────────
    var binding = _section(container, 'Binding');
    var agentOptions = [{ value: '', label: '— none —' }].concat(
      agents.map(function (a) { return { value: a.name, label: a.name }; })
    );
    _fieldGroup(
      binding, 'Default agent', 'conn-default-agent',
      _select('default_agent', agentOptions, config.default_agent || '')
    );

    // ── Admission ────────────────────────────────────────────────────
    var admission = _section(container, 'Admission');
    _fieldGroup(
      admission, 'Allowlisted peers (one per line)', 'conn-allowlist-peers',
      _textarea('allowlist_peers', _arrayToLines(allowlist.peers), 3)
    );
    _fieldGroup(
      admission, 'Allowlisted channels (one per line)', 'conn-allowlist-channels',
      _textarea('allowlist_channels', _arrayToLines(allowlist.channels), 3)
    );
    _fieldGroup(
      admission, 'Always-listen channels (one per line)', 'conn-always-listen',
      _textarea('always_listen', _arrayToLines(config.always_listen), 2)
    );

    // ── Pairing (edit mode only) ──────────────────────────────────────
    // Squawk 0044: pairing is the required enrollment action that admits the
    // first peer, not diagnosis — it was previously filed under Diagnostics
    // next to "Run doctor", which misled operators into treating it as
    // optional. Relocated here, next to the admission fields it feeds.
    var pairingResultEl = null;
    if (!isCreate) {
      var pairing = _section(container, 'Pairing');
      pairing.appendChild(_el('p', {
        className: 'section-description',
        text: 'The peer DMs the bot, you generate a code, and the peer replies with it within 10 minutes.'
      }));
      var pairingBtn = _btn(
        'btn-outlined-primary pairing-btn', 'connector-pairing-btn', 'Generate pairing code'
      );
      pairing.appendChild(pairingBtn);
      pairingResultEl = _el('div', { className: 'connector-pairing-result' });
      pairingResultEl.setAttribute('data-testid', 'connector-pairing-result');
      pairingResultEl.setAttribute('role', 'status');
      pairingResultEl.setAttribute('aria-live', 'polite');
      pairing.appendChild(pairingResultEl);

      // Renders the generated code as its own selectable <code> element (not
      // fused into the status prose) plus a Copy button, mirroring the
      // <code> + copy-button + clipboard pattern already used for markdown
      // code blocks (markdown.js renderCodeBlock). Expiry stays plain prose.
      pairingBtn.addEventListener('click', function () {
        pairingResultEl.textContent = 'Generating…';
        fetch('/api/connectors/' + encodeURIComponent(cfg.id) + '/pairing-code', { method: 'POST' })
          .then(function (r) {
            if (!r.ok) throw new Error('pairing-code request failed: HTTP ' + r.status);
            return r.json();
          })
          .then(function (result) {
            pairingResultEl.textContent = '';
            var codeRow = _el('div', { className: 'connector-pairing-code-row' });
            var codeEl = _el('code', { className: 'connector-pairing-code', text: result.code });
            codeEl.setAttribute('data-testid', 'connector-pairing-code');
            codeRow.appendChild(codeEl);
            var copyBtn = _btn(
              'btn-outlined-primary connector-pairing-copy-btn', 'connector-pairing-copy-btn', 'Copy'
            );
            copyBtn.setAttribute('aria-label', 'Copy pairing code');
            copyBtn.addEventListener('click', function () {
              var clip = (typeof navigator !== 'undefined') && navigator.clipboard;
              if (!clip || typeof clip.writeText !== 'function') {
                if (window.App && window.App.showFlash) window.App.showFlash(pairingResultEl, 'Copy failed', true);
                return;
              }
              clip.writeText(codeEl.textContent).then(function () {
                if (window.App && window.App.showFlash) window.App.showFlash(pairingResultEl, 'Copied!');
              }).catch(function () {
                if (window.App && window.App.showFlash) window.App.showFlash(pairingResultEl, 'Copy failed', true);
              });
            });
            codeRow.appendChild(copyBtn);
            pairingResultEl.appendChild(codeRow);
            pairingResultEl.appendChild(_el(
              'span', { className: 'connector-pairing-expiry', text: 'Expires ' + result.expires_at }
            ));
          })
          .catch(function (err) {
            pairingResultEl.textContent = err.message || String(err);
          });
      });
    }

    // ── Channel → agent map ──────────────────────────────────────────
    var mapSection = _section(container, 'Channel → agent map');
    var rowsEl = _el('div', { className: 'connector-channel-map-rows' });
    mapSection.appendChild(rowsEl);
    var addRowBtn = _btn(
      'btn-outlined-primary channel-map-add-btn', 'connector-channel-map-add-btn', '+ Add row'
    );
    mapSection.appendChild(addRowBtn);

    var channelMap = config.channel_map || {};
    var rowEntries = Object.keys(channelMap).map(function (k) { return [k, channelMap[k]]; });

    function renderRows() {
      rowsEl.innerHTML = ''; // static clear — exempt
      rowEntries.forEach(function (entry, idx) {
        var row = _el('div', { className: 'connector-channel-map-row' });
        row.setAttribute('data-testid', 'connector-channel-map-row');
        row.setAttribute('data-row-idx', String(idx));
        var chInput = _el('input', { className: 'field-input channel-map-channel' });
        chInput.value = entry[0];
        chInput.placeholder = 'channel id';
        var agInput = _el('input', { className: 'field-input channel-map-agent' });
        agInput.value = entry[1];
        agInput.placeholder = 'agent name';
        var removeBtn = _btn(
          'channel-map-remove-btn', 'connector-channel-map-remove-btn', '✕'
        );
        removeBtn.setAttribute('aria-label', 'Remove row');
        chInput.addEventListener('input', markDirty);
        agInput.addEventListener('input', markDirty);
        removeBtn.addEventListener('click', function () {
          rowEntries.splice(idx, 1);
          renderRows();
          markDirty();
        });
        row.appendChild(chInput);
        row.appendChild(agInput);
        row.appendChild(removeBtn);
        rowsEl.appendChild(row);
      });
    }
    renderRows();
    addRowBtn.addEventListener('click', function () {
      rowEntries.push(['', '']);
      renderRows();
      markDirty();
    });

    // Applies a doctor probe outcome to the header LED. Shared by the
    // one-shot auto-probe below and the manual "Run doctor" button so the
    // two stay in sync — whichever probed last wins.
    function applyDoctorStatusToLed(status, disabled) {
      if (!statusLedEl) return;
      var state = _connectorLedState(status, disabled);
      var label = _connectorLedLabel(status, disabled);
      statusLedEl.className = 'indicator-led indicator-led--' + state;
      statusLedEl.setAttribute('aria-label', label);
      if (statusLabelEl) statusLabelEl.textContent = label;
    }

    // ── Diagnostics + Danger Zone (edit mode only) ────────────────────
    var doctorResultEl = null;
    if (!isCreate) {
      var diagnostics = _section(container, 'Diagnostics');
      var doctorBtn = _btn('btn-outlined-primary doctor-btn', 'connector-doctor-btn', 'Run doctor');
      diagnostics.appendChild(doctorBtn);
      doctorResultEl = _el('div', { className: 'connector-doctor-result' });
      doctorResultEl.setAttribute('data-testid', 'connector-doctor-result');
      doctorResultEl.setAttribute('role', 'status');
      doctorResultEl.setAttribute('aria-live', 'polite');
      diagnostics.appendChild(doctorResultEl);

      var danger = _el('div', { className: 'editor-section danger-zone' });
      danger.appendChild(_el('div', { className: 'section-title danger-zone-title', text: 'Danger Zone' }));
      var deleteBtn = _el('button', { className: 'btn-muted-destructive delete-btn' });
      deleteBtn.type = 'button';
      deleteBtn.setAttribute('data-testid', 'delete-connector-btn');
      var deleteTitle = _el('span', { text: 'Delete Connector' });
      deleteTitle.setAttribute('data-confirm-title', '');
      deleteBtn.appendChild(deleteTitle);
      danger.appendChild(deleteBtn);
      container.appendChild(danger);

      doctorBtn.addEventListener('click', function () {
        doctorResultEl.textContent = 'Running…';
        fetch('/api/connectors/' + encodeURIComponent(cfg.id) + '/test', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (result) {
            var lines = [result.status + ': ' + result.message];
            (result.warnings || []).forEach(function (w) { lines.push('warning: ' + w); });
            doctorResultEl.textContent = lines.join(' | ');
            applyDoctorStatusToLed(result.status, result.disabled);
          })
          .catch(function (err) {
            doctorResultEl.textContent = 'Doctor request failed: ' + (err.message || err);
          });
      });

      // Squawk 0045, pinned decision #1: probe doctor exactly ONCE,
      // automatically, when an EXISTING connector is opened — the
      // operator's "auto green dot". No polling loop, and this branch
      // never runs for the create form (guarded by the enclosing
      // `!isCreate`). Drives the header LED only — the Diagnostics
      // section's result prose stays a manual-click affordance so the
      // "Run doctor" button's existing behavior/tests are untouched.
      fetch('/api/connectors/' + encodeURIComponent(cfg.id) + '/test', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function (result) {
          applyDoctorStatusToLed(result.status, result.disabled);
        })
        .catch(function () {
          // Best-effort convenience indicator — leave it at "Checking…"
          // on failure rather than surfacing a second error path; the
          // operator still has the manual "Run doctor" button below.
        });

      deleteBtn.addEventListener('click', function () {
        window.App.confirmDelete(deleteBtn, function (el, revertFn) {
          fetch('/api/connectors/' + encodeURIComponent(cfg.id), { method: 'DELETE' })
            .then(function (r) {
              if (!r.ok) throw new Error('Delete failed');
              App.store.invalidate('connectors'); // the Library list loses a row (DD9)
              if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
            })
            .catch(function (err) {
              revertFn();
              errorEl.textContent = err.message || String(err);
            });
        });
      });
    }

    // ── Dirty tracking — any top-level field change enables Save/Cancel.
    // The unsaved caption follows the same reports that feed studio's
    // `dirty` through onDirtyChange (M25 F3 L4b).
    function reportDirty(d) {
      unsavedEl.textContent = d ? 'Unsaved changes' : '';
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(d);
    }
    function markDirty() {
      saveBtn.disabled = false;
      cancelBtn.disabled = false;
      reportDirty(true);
    }
    container.querySelectorAll('[data-field]').forEach(function (el) {
      el.addEventListener('input', markDirty);
      el.addEventListener('change', markDirty);
    });

    // Focus after an in-place action (M25 F6 L1b, DD2). The title is re-resolved
    // when the focus timer fires (a create or an edit-mode Cancel re-mounts).
    function titleEl() { return container.querySelector('.editor-title'); }
    if (callbacks.onCancel) {
      cancelBtn.addEventListener('click', function () {
        // Edit-mode Cancel reverts in place through a re-mount (async: the
        // agents fetch): park the restore, the orchestrator's mount flushes it.
        // Create-mode Cancel closes the editor (DD8) and takes none.
        if (!isCreate) App.focusAfter.defer(App.focusAfter.begin(cancelBtn), titleEl);
        callbacks.onCancel();
      });
    }

    // ── Save ─────────────────────────────────────────────────────────
    function collectPayload() {
      var field = function (name) {
        var el = container.querySelector('[data-field="' + name + '"]');
        return el ? el.value : '';
      };
      var peers = _linesToArray(field('allowlist_peers'));
      var channels = _linesToArray(field('allowlist_channels'));
      var alwaysListen = _linesToArray(field('always_listen'));
      var defaultAgent = field('default_agent');

      var channelMapOut = {};
      rowsEl.querySelectorAll('.connector-channel-map-row').forEach(function (row) {
        var ch = row.querySelector('.channel-map-channel').value.trim();
        var ag = row.querySelector('.channel-map-agent').value.trim();
        if (ch) channelMapOut[ch] = ag;
      });

      var newConfig = {};
      if (defaultAgent) newConfig.default_agent = defaultAgent;
      if (Object.keys(channelMapOut).length > 0) newConfig.channel_map = channelMapOut;
      if (peers.length > 0 || channels.length > 0) {
        newConfig.allowlist = {};
        if (peers.length > 0) newConfig.allowlist.peers = peers;
        if (channels.length > 0) newConfig.allowlist.channels = channels;
      }
      if (alwaysListen.length > 0) newConfig.always_listen = alwaysListen;
      // Save-path trap: the generic `field(name)` reader returns `.value`
      // (useless for a checkbox) — read `.checked` directly. Sparse-config
      // pattern: checked (default) omits the key; unchecked persists
      // `enabled: false`.
      var enabledEl = container.querySelector('[data-field="enabled"]');
      if (enabledEl && !enabledEl.checked) newConfig.enabled = false;

      return {
        name: field('name').trim(),
        type: field('type'),
        config: newConfig,
        secrets: { token: field('token') }
      };
    }

    function _errorMessageFromResponse(body) {
      var detail;
      try {
        var parsed = JSON.parse(body);
        detail = parsed && parsed.detail;
      } catch (_e) {
        // Non-JSON body — fall through.
      }
      if (Array.isArray(detail)) {
        detail = detail.map(function (d) {
          var loc = (d.loc || []).join('.');
          return loc ? (loc + ': ' + d.msg) : d.msg;
        }).join(' | ');
      }
      return detail;
    }

    saveBtn.addEventListener('click', function () {
      errorEl.textContent = '';
      var payload = collectPayload();
      if (!payload.name) {
        errorEl.textContent = 'Name is required.';
        return;
      }
      var saveTok = App.focusAfter.begin(saveBtn);
      var url = isCreate ? '/api/connectors' : '/api/connectors/' + encodeURIComponent(cfg.id);
      var method = isCreate ? 'POST' : 'PUT';
      fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            var detail = _errorMessageFromResponse(body);
            throw new Error(detail || (isCreate ? 'Create failed' : 'Save failed'));
          });
        }
        return r.json();
      }).then(function (updated) {
        App.store.invalidate('connectors'); // the Library list shows it (DD9)
        window.App.showFlash(container, isCreate ? 'Connector created' : 'Connector saved');
        // A create re-mounts in edit mode asynchronously: park the restore for
        // the orchestrator's mount to flush.
        if (isCreate) App.focusAfter.defer(saveTok, titleEl);
        if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, isCreate);
        // An edit save keeps this editor (a create re-renders it in edit
        // mode): the form now matches the saved row, so it reads clean again
        // -- the caption clears and Save/Cancel disable, as in the other
        // editors (M25 F3 L4b). studio's onSaveSuccess has cleared its own
        // `dirty` under its generation guard, so no onDirtyChange here.
        if (!isCreate) {
          unsavedEl.textContent = '';
          saveBtn.disabled = true;
          cancelBtn.disabled = true;
          // Squawk 0126: the title follows the saved row (a rename).
          if (updated && updated.name) connTitle.textContent = updated.name;
          App.focusAfter.restore(saveTok, titleEl);
        }
      }).catch(function (err) {
        errorEl.textContent = err.message || String(err);
        App.focusAfter.defer(null);
        App.focusAfter.restore(saveTok, saveBtn);
      });
    });
  }

  window.App.studio.renderConnectorEditor = renderConnectorEditor;
})();
