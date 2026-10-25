// App.studio.renderConnectorEditor — Studio connector-editor section
// (Mission 23 Flight 2 Leg 2, DD-9). Since M25 F3 L4a connectors are rows of
// the Library list (studio.js) and routed (`#library/connectors/~new|{id}`);
// the tile grid is retired.
//
//   renderConnectorEditor(container, connector, connectorTypes, agents, callbacks)
//     -> {destroy, setBusy, setError}
//
// callbacks: { onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange }
//
// M31 F3 L07a: the frame and fields are built once per mount from App.ui
// library controls (the provider editor's shape): editorShell (breadcrumb
// "Library / Connectors", title, the header status line through afterTitle,
// Cancel/Save, the unsaved caption and the error slot), section, field with
// textInput / select / textarea / secretInput / toggle, status (the header line
// and the doctor result) and button. After the mount, Save and Cancel patch the
// controls through their handles; only a create re-mounts (the glue, in edit
// mode).
//
// The value model: readValues() reads every control (the token as typed or as
// shown, the channel map from the table's model) and dirty is
// JSON.stringify(readValues()) !== snapshot, recomputed from each control's own
// input/change callback. Typing a change and reverting it is clean.
//
// Secret handling (the token): the token's input is written only through
// .value (App.ui.secretInput.setValue, never an attribute, title or aria-label).
// A saved or cancelled form shows the server's MASKED value (`***...abcd`) with
// the reveal off, and the snapshot is read BACK from the controls after that
// write, so no variable holds a typed token once its request has settled. An
// untouched Save sends the masked string and the server (`_looks_masked`) keeps
// the stored token. See `the_one/agents.md` "Connector frame on the library".
//
// M31 F3 L07b: Pairing (section, button, status, copyField), the Channel -> agent
// map (App.ui.keyValueTable) and the Danger zone (App.ui.dangerZone) are library
// controls too; this file builds no hand-made section, button, clipboard or
// confirm markup. The map's rows live in the table's own model (kv.values()).
//
// Mission 23 Flight 3 Leg 2 (DD-6): `config.enabled` is a persisted key
// (default true, absent key = enabled, no migration). Every connector starts
// listening on create (unless created with `enabled: false`) and stops on
// delete; PUT branches on the NEW row's effective `enabled` value only — true
// restarts (today's stop+start), false stops and does NOT restart, regardless
// of the prior value (api.py `update_connector`).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // The handle of the current mount, held in a mount slot. A create re-mounts
  // the editor in edit mode, and the deferred focus after that Save targets the
  // NEW mount's title through the slot (the closure that saved is gone by then).
  var slot = window.App.ui.util.mountSlot();

  // ── Status LED (Squawk 0045: MCP-panel parity) ────────────────────────
  // Maps a doctor probe's `status` ("ok"/"degraded"/"failed", DoctorReport in
  // the_one/connectors/base.py) plus the /test response's `disabled` flag onto
  // the status line's states (success/warning/danger/idle). Per the squawk's
  // pinned decision #2, a disabled connector always shows idle regardless of the
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

  // The stored channel_map object -> the table's rows, in key order.
  function _mapRows(map) {
    map = map || {};
    return Object.keys(map).map(function (k) { return { channel: k, agent: map[k] }; });
  }

  // A select shows the option for `value`, else its first option (a stale agent
  // or type that is no longer offered falls back; nothing throws).
  function _setSelect(sel, value) {
    sel.value = value;
    if (sel.selectedIndex < 0) sel.selectedIndex = 0;
  }

  // A fetchJson failure that is the network (or a body that was not JSON), not an
  // HTTP error status: fetchJson throws a plain Error for a non-OK response.
  function _isTransportError(err) {
    return !!err && (err.name === 'TypeError' || err.name === 'SyntaxError');
  }

  // ── Editor ────────────────────────────────────────────────────────────

  function renderConnectorEditor(container, connector, connectorTypes, agents, callbacks) {
    callbacks = callbacks || {};
    var util = window.App.ui.util;
    var isCreate = !connector;
    var types = connectorTypes || [];
    var cfg = connector || {
      name: '',
      type: (types[0] && types[0].value) || 'discord',
      config: {},
      secrets: {}
    };
    var config = cfg.config || {};
    // The last SAVED record (the server's masked response): Cancel restores from it.
    var stored = cfg;
    var h = { shell: null };
    var destroyed = false;
    var tok = slot.mount(function () { destroyed = true; }, h);
    var snapshot = '';

    function current() { return !destroyed && slot.isCurrent(tok); }

    // ── Controls ─────────────────────────────────────────────────────
    function recomputeDirty() {
      if (!h.shell) return;
      var d = JSON.stringify(readValues()) !== snapshot;
      h.shell.setDirty(d);
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(d);
    }

    var nameInput = App.ui.textInput({
      id: 'conn-name', value: cfg.name || '', placeholder: 'connector-name',
      dataset: { field: 'name' }, onInput: recomputeDirty
    });
    var nameField = App.ui.field({ label: 'Name', control: nameInput });

    var typeOptions = types.map(function (t) { return { value: t.value, label: t.label }; });
    var knownType = false;
    typeOptions.forEach(function (o) { if (o.value === cfg.type) knownType = true; });
    // A saved type the server no longer offers (or an empty type list) still shows.
    if (!knownType) typeOptions.push({ value: cfg.type, label: cfg.type });
    var typeSelect = App.ui.select({
      id: 'conn-type', options: typeOptions, value: cfg.type, dataset: { field: 'type' },
      onChange: function () { updateSetupSteps(); recomputeDirty(); }
    });
    var typeField = App.ui.field({ label: 'Type', control: typeSelect });

    var secret = App.ui.secretInput({
      id: 'conn-token', value: (cfg.secrets && cfg.secrets.token) || '',
      placeholder: 'Platform credential', dataset: { field: 'token' }
    });
    secret.input.addEventListener('input', recomputeDirty);
    secret.input.addEventListener('change', recomputeDirty);
    var tokenField = App.ui.field({ label: 'Token', control: secret.input, host: secret.el });

    // Checked-state trap (DD-6): render from `!== false`, never a truthy
    // check — `!!config.enabled` is falsy for the absent-key legacy case
    // and would invert the documented default (absent key = enabled).
    var enabledToggle = App.ui.toggle({
      id: 'conn-enabled', label: 'Enabled', checked: config.enabled !== false,
      dataset: { field: 'enabled' }, onChange: recomputeDirty
    });

    var identity = App.ui.section({
      title: 'Identity',
      children: [nameField.el, typeField.el, tokenField.el, enabledToggle.el]
    });

    // ── Setup steps (Squawk 0046) ───────────────────────────────────────
    // Rendered on BOTH create and edit — a first-timer needs this most on
    // the create form, before anything else on the page helps them. Kept
    // live against the Type select so switching types before saving
    // updates the bullets immediately.
    var setupStepsList = util.el('ul', { className: 'connector-setup-steps-list' });
    // Squawk 0046 review fix (dead link): only `/static` is mounted
    // (the_one/interfaces/web/app.py), so `docs/` is not served over HTTP —
    // an `<a href="docs/connector-setup.md">` 404s. No route/static mount
    // for `docs/` (new HTTP surface + security-posture question, out of
    // scope for a squawk) and no external GitHub link (this is a
    // local-first app that may run offline; an outbound link is an
    // operator choice, not an implementer's). So this renders as plain text via
    // the area's muted-text class (studio.css), naming the
    // file path for the operator to open from the repo checkout themselves.
    var setupStepsDocRef = util.el('span', {
      className: 'connector-setup-steps-doc-ref',
      'data-testid': 'connector-setup-steps-doc-ref',
      text: 'Full walkthrough: docs/connector-setup.md (in the repo)'
    });
    var setupSteps = App.ui.section({
      title: 'Setup steps', testid: 'connector-setup-steps',
      children: [setupStepsList, setupStepsDocRef]
    });

    function updateSetupSteps() {
      var type = typeSelect.value;
      var steps = SETUP_STEPS_BY_TYPE[type];
      setupStepsList.replaceChildren();
      if (!steps) {
        setupSteps.el.hidden = true;
        return;
      }
      setupSteps.el.hidden = false;
      setupStepsList.setAttribute('data-testid', 'connector-setup-steps-list-' + type);
      steps.forEach(function (stepText) {
        setupStepsList.appendChild(util.el('li', { text: stepText }));
      });
    }
    updateSetupSteps();

    // ── Binding ──────────────────────────────────────────────────────
    var agentOptions = [{ value: '', label: '— none —' }].concat(
      agents.map(function (a) { return { value: a.name, label: a.name }; })
    );
    var agentSelect = App.ui.select({
      id: 'conn-default-agent', options: agentOptions, dataset: { field: 'default_agent' },
      onChange: recomputeDirty
    });
    // A stale default_agent (an agent since deleted) falls back to "— none —".
    _setSelect(agentSelect, config.default_agent || '');
    var binding = App.ui.section({
      title: 'Binding',
      children: [App.ui.field({ label: 'Default agent', control: agentSelect }).el]
    });

    // ── Admission ────────────────────────────────────────────────────
    var allowlist = config.allowlist || {};
    function admissionArea(id, field, value, rows) {
      return App.ui.textarea({
        id: id, value: value, rows: rows, dataset: { field: field }, onInput: recomputeDirty
      });
    }
    var peersArea = admissionArea('conn-allowlist-peers', 'allowlist_peers',
      _arrayToLines(allowlist.peers), 3);
    var channelsArea = admissionArea('conn-allowlist-channels', 'allowlist_channels',
      _arrayToLines(allowlist.channels), 3);
    var listenArea = admissionArea('conn-always-listen', 'always_listen',
      _arrayToLines(config.always_listen), 2);
    var admission = App.ui.section({
      title: 'Admission',
      children: [
        App.ui.field({ label: 'Allowlisted peers (one per line)', control: peersArea }).el,
        App.ui.field({ label: 'Allowlisted channels (one per line)', control: channelsArea }).el,
        App.ui.field({ label: 'Always-listen channels (one per line)', control: listenArea }).el
      ]
    });

    // ── Header ────────────────────────────────────────────────────────
    // M25 F3 L4b (DD2): the breadcrumb "Library / Connectors" ("Library" a link
    // to `#library`, no handler: studio's router interception closes the item,
    // and the guard asks once about a dirty editor). Cancel on the create form
    // abandons creation (DD8), so it is enabled from first render; in edit mode
    // it reverts in place and stays disabled until a field changes.
    //
    // Squawk 0045: the connection status line, edit mode only (no line on the
    // create form — nothing to probe until the connector exists). It sits in the
    // header next to the connector name, not inside Diagnostics.
    var headerStatus = null;
    if (!isCreate) {
      headerStatus = App.ui.status({
        led: true, ledTestid: 'connector-status-led', testid: 'connector-status-label',
        state: 'pending', text: 'Checking connection…'
      });
    }
    h.shell = App.ui.editorShell({
      breadcrumb: {
        label: 'Library',
        href: window.App.router.href({ destination: 'library' }),
        trail: ' / Connectors'
      },
      title: isCreate ? 'New Connector' : (cfg.name || ''),
      afterTitle: headerStatus ? headerStatus.el : null,
      errorRole: 'alert',
      actions: {
        cancel: { testid: 'cancel-connector-btn', enabledWhenClean: isCreate, onClick: onCancelClick },
        save: { label: isCreate ? 'Create' : 'Save', testid: 'save-connector-btn', onClick: performSave }
      }
    });
    var shell = h.shell;

    // The pending header line follows the last doctor outcome (the auto-probe or
    // a manual run, whichever came last).
    function applyDoctorStatusToHeader(status, disabled) {
      if (!headerStatus) return;
      headerStatus.set(_connectorLedState(status, disabled), _connectorLedLabel(status, disabled));
    }

    // ── The value model ───────────────────────────────────────────────
    var kv = null;

    function readValues() {
      return {
        name: nameInput.value,
        type: typeSelect.value,
        token: secret.input.value,
        enabled: enabledToggle.control.checked,
        default_agent: agentSelect.value,
        allowlist_peers: peersArea.value,
        allowlist_channels: channelsArea.value,
        always_listen: listenArea.value,
        channel_map_rows: kv ? kv.values() : []
      };
    }

    // The request payload from a value-model object, with today's normalisation:
    // lines become trimmed arrays with empties dropped, the sparse `config`
    // (`enabled: false` only when it is off), a channel row kept only when its
    // channel is non-empty, and `secrets: {token}`.
    function buildPayload(v) {
      var peers = _linesToArray(v.allowlist_peers);
      var channels = _linesToArray(v.allowlist_channels);
      var alwaysListen = _linesToArray(v.always_listen);
      var channelMapOut = {};
      // A row with an empty channel is dirty (the raw rows) but dropped here; a
      // duplicate channel id: the last row wins. After a Save the table is re-seeded
      // from the response, so the empty row goes and a duplicate shows once.
      v.channel_map_rows.forEach(function (r) {
        var ch = r.channel.trim();
        if (ch) channelMapOut[ch] = r.agent.trim();
      });
      var newConfig = {};
      if (v.default_agent) newConfig.default_agent = v.default_agent;
      if (Object.keys(channelMapOut).length > 0) newConfig.channel_map = channelMapOut;
      if (peers.length > 0 || channels.length > 0) {
        newConfig.allowlist = {};
        if (peers.length > 0) newConfig.allowlist.peers = peers;
        if (channels.length > 0) newConfig.allowlist.channels = channels;
      }
      if (alwaysListen.length > 0) newConfig.always_listen = alwaysListen;
      if (!v.enabled) newConfig.enabled = false;
      return {
        name: v.name.trim(),
        type: v.type,
        config: newConfig,
        secrets: { token: v.token }
      };
    }

    // Patch every control from a saved record, then re-seed the channel-map table. Used by
    // Cancel and by an edit-mode Save (the form then matches the saved row). The
    // token is written back as the record's MASKED value with the reveal off.
    function applyRecord(rec) {
      var c = rec.config || {};
      var al = c.allowlist || {};
      nameInput.value = rec.name || '';
      _setSelect(typeSelect, rec.type);
      updateSetupSteps();
      secret.setValue((rec.secrets && rec.secrets.token) || '');
      enabledToggle.setChecked(c.enabled !== false);
      _setSelect(agentSelect, c.default_agent || '');
      peersArea.value = _arrayToLines(al.peers);
      channelsArea.value = _arrayToLines(al.channels);
      listenArea.value = _arrayToLines(c.always_listen);
      kv.setValues(_mapRows(c.channel_map));
    }

    // ── Sections, in order, built sequentially ───────────────────────
    var frag = document.createDocumentFragment();
    frag.appendChild(shell.el);
    frag.appendChild(identity.el);
    frag.appendChild(setupSteps.el);
    frag.appendChild(binding.el);
    frag.appendChild(admission.el);

    // ── Pairing (edit mode only) ───────────────────────────────────────
    // Squawk 0044: pairing is the required enrollment action that admits the
    // first peer, not diagnosis. It sits next to the admission fields it feeds.
    // The result region is a plain container: a status line for "Generating…" and
    // a failure, then (on success) a read-only copy field and the expiry line.
    if (!isCreate) {
      var pairingBtn = App.ui.button({
        label: 'Generate pairing code', testid: 'connector-pairing-btn', className: 'pairing-btn'
      });
      var pairingResultEl = util.el('div', {
        className: 'connector-pairing-result', 'data-testid': 'connector-pairing-result'
      });
      var pairingStatus = App.ui.status({ led: false });
      pairingStatus.el.hidden = true;
      pairingResultEl.appendChild(pairingStatus.el);
      var pairingSeq = 0;
      frag.appendChild(App.ui.section({
        title: 'Pairing',
        description: 'The peer DMs the bot, you generate a code, and the peer replies with it within 10 minutes.',
        layout: 'stack',
        children: [pairingBtn, pairingResultEl]
      }).el);

      // The stack gap needs the result wrapper hidden while every child is hidden, or
      // an empty wrapper would still take a gap under the button.
      function syncPairingVisibility() {
        pairingResultEl.hidden = Array.prototype.every.call(
          pairingResultEl.children, function (c) { return c.hidden; }
        );
      }
      syncPairingVisibility();

      // "Expires Oct 23, 2026, 8:57 AM" in the operator zone, the ISO value in the
      // title (squawk 0245, DD14). One-shot: the code is short-lived.
      function pairingExpiryEl(iso) {
        var span = util.el('span', {
          className: 'connector-pairing-expiry', text: 'Expires ' + App.time.formatDateTime(iso)
        });
        span.title = String(iso);
        return span;
      }

      function clearPairingResult() {
        pairingResultEl.replaceChildren(pairingStatus.el);
        syncPairingVisibility();
      }
      pairingBtn.addEventListener('click', function () {
        var mine = ++pairingSeq;
        clearPairingResult();
        pairingStatus.el.hidden = false;
        pairingStatus.set('pending', 'Generating…');
        syncPairingVisibility();
        fetch('/api/connectors/' + encodeURIComponent(cfg.id) + '/pairing-code', { method: 'POST' })
          .then(function (r) {
            if (!r.ok) throw new Error('pairing-code request failed: HTTP ' + r.status);
            return r.json();
          })
          .then(function (result) {
            if (!current() || mine !== pairingSeq) return;
            pairingStatus.el.hidden = true;
            pairingResultEl.replaceChildren(
              pairingStatus.el,
              App.ui.copyField({
                value: result.code, label: 'Pairing code', testid: 'connector-pairing-code',
                copyTestid: 'connector-pairing-copy-btn', buttonLabel: 'Copy pairing code'
              }).el,
              pairingExpiryEl(result.expires_at)
            );
            syncPairingVisibility();
          })
          .catch(function (err) {
            if (!current() || mine !== pairingSeq) return;
            clearPairingResult();
            pairingStatus.el.hidden = false;
            pairingStatus.set('danger', err.message || String(err));
            syncPairingVisibility();
          });
      });
    }

    // ── Channel → agent map ─────────────────────────────────────────────
    kv = App.ui.keyValueTable({
      columns: [
        { key: 'channel', label: 'Channel id', placeholder: 'channel id',
          inputTestid: 'connector-channel-map-channel' },
        { key: 'agent', label: 'Agent', placeholder: 'agent name',
          inputTestid: 'connector-channel-map-agent' }
      ],
      rows: _mapRows(config.channel_map),
      rowTestid: 'connector-channel-map-row',
      removeTestid: 'connector-channel-map-remove-btn',
      addTestid: 'connector-channel-map-add-btn',
      label: 'Channel to agent map',
      onChange: recomputeDirty
    });
    frag.appendChild(App.ui.section({ title: 'Channel → agent map', children: [kv.el] }).el);

    // ── Diagnostics (edit mode only) ──────────────────────────────────
    // Both are set in edit mode only (below) and called by an edit Save.
    var runHeaderProbe = null;
    var resetDoctorResult = null;
    if (!isCreate) {
      var doctorStatus = App.ui.status({ testid: 'connector-doctor-result' });
      doctorStatus.el.hidden = true;
      var doctorBtn = App.ui.button({
        label: 'Run doctor', testid: 'connector-doctor-btn', className: 'doctor-btn'
      });
      frag.appendChild(App.ui.section({
        title: 'Diagnostics', layout: 'stack', children: [doctorBtn, doctorStatus.el]
      }).el);

      // Only the latest response is applied: doctorSeq guards the result line (the
      // button is also disabled while a run is in flight) and headerSeq guards the
      // header line, which the auto-probe and a manual run share (newest request wins).
      var doctorSeq = 0;
      var headerSeq = 0;
      doctorBtn.addEventListener('click', function () {
        if (doctorBtn.disabled) return;
        var mine = ++doctorSeq;
        var mineHeader = ++headerSeq;
        doctorBtn.disabled = true;
        doctorStatus.el.hidden = false;
        doctorStatus.set('pending', 'Running…');
        function settle() { if (current() && mine === doctorSeq) doctorBtn.disabled = false; }
        App.api.fetchJson('/api/connectors/' + encodeURIComponent(cfg.id) + '/test', { method: 'POST' })
          .then(function (result) {
            if (!current()) return;
            settle();
            if (mine !== doctorSeq) return;
            var lines = [result.status + ': ' + result.message];
            (result.warnings || []).forEach(function (w) { lines.push('warning: ' + w); });
            doctorStatus.set(_connectorLedState(result.status, result.disabled), lines.join(' | '));
            if (mineHeader === headerSeq) applyDoctorStatusToHeader(result.status, result.disabled);
          })
          .catch(function (err) {
            if (!current()) return;
            settle();
            if (mine !== doctorSeq) return;
            var msg = err.message || String(err);
            doctorStatus.set('danger', _isTransportError(err) ? 'Doctor request failed: ' + msg : msg);
          });
      });

      // Squawk 0045, pinned decision #1: probe doctor exactly ONCE,
      // automatically, when an EXISTING connector is opened — the operator's
      // "auto green dot". No polling loop, and this branch never runs for the
      // create form (guarded by the enclosing `!isCreate`). Drives the header
      // line only — the Diagnostics result stays a manual-click affordance. A
      // non-OK response is "Connection check failed"; a network failure leaves
      // "Checking…" (best-effort convenience indicator).
      //
      // An edit Save patches in place (no remount, DD5), so it re-runs this probe
      // itself: the header must follow the SAVED config (enabled or not), not the
      // verdict from before the Save. Assigned to a function-scoped var so the
      // Save handler can reach it; it stays null on the create form.
      runHeaderProbe = function () {
        var probeHeader = ++headerSeq;
        if (headerStatus) headerStatus.set('pending', 'Checking connection…');
        App.api.fetchJson('/api/connectors/' + encodeURIComponent(cfg.id) + '/test', { method: 'POST' })
          .then(function (result) {
            if (!current() || probeHeader !== headerSeq) return;
            applyDoctorStatusToHeader(result.status, result.disabled);
          })
          .catch(function (err) {
            if (!current() || probeHeader !== headerSeq || _isTransportError(err)) return;
            if (headerStatus) headerStatus.set('danger', 'Connection check failed');
          });
      };

      // After a successful edit Save the Diagnostics result describes the previous
      // config, so it is cleared rather than left to contradict the header. A run
      // still in flight is orphaned (doctorSeq moves on, so it never repaints the
      // line) and the button is released here, since its own settle() no longer will.
      resetDoctorResult = function () {
        ++doctorSeq;
        doctorStatus.el.hidden = true;
        doctorStatus.set('idle', '');
        doctorBtn.disabled = false;
      };

      runHeaderProbe();

      // ── Danger Zone ─────────────────────────────────────────────────
      var deleting = false;
      var danger = App.ui.dangerZone({
        action: {
          label: 'Delete Connector', testid: 'delete-connector-btn',
          onConfirm: function (revert) {
            if (deleting) return; // one DELETE per commit, until it settles
            deleting = true;
            danger.setDisabled(true);
            danger.setNotice(null);
            App.api.fetchJson(
              '/api/connectors/' + encodeURIComponent(cfg.id), { method: 'DELETE' }
            ).then(function () {
              App.store.invalidate('connectors'); // the Library list loses a row (DD9)
              if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
            }).catch(function (err) {
              deleting = false;
              if (!current()) return;
              revert();
              danger.setDisabled(false);
              danger.setNotice(err.message || String(err));
            });
          }
        },
        notice: { testid: 'connector-delete-error' }
      });
      frag.appendChild(danger.el);
    }

    container.replaceChildren(frag);
    snapshot = JSON.stringify(readValues());
    shell.setDirty(false);

    // Focus after an in-place action (M25 F6 L1b, DD2). A create re-mounts, so its
    // restore resolves the NEW mount's title through the slot when the glue flushes.
    function newMountTitle() {
      var cur = slot.current();
      return cur && cur.data.shell && cur.data.shell.titleEl;
    }

    // ── Cancel ─────────────────────────────────────────────────────────
    // Edit mode reverts in place, synchronously (no remount to wait for): every
    // control, the token to its stored mask with the reveal off, and the old
    // channel-map rows, restored from the last SAVED record. Create mode closes
    // the editor (the glue's discard).
    function onCancelClick() {
      if (isCreate) {
        if (callbacks.onCancel) callbacks.onCancel();
        return;
      }
      var cancelTok = App.focusAfter.begin(shell.cancelButton);
      applyRecord(stored);
      snapshot = JSON.stringify(readValues());
      shell.setError('');
      shell.setDirty(false);
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
      App.focusAfter.restore(cancelTok, shell.titleEl);
    }

    // ── Save ───────────────────────────────────────────────────────────
    function performSave() {
      shell.setError('');
      // The payload is local to this click: it is serialised here and no variable
      // outlives the request holding the typed token.
      var payload = buildPayload(readValues());
      if (!payload.name) {
        shell.setError('Name is required.');
        return;
      }
      var body = JSON.stringify(payload);
      payload = null;
      var saveTok = App.focusAfter.begin(shell.saveButton);
      shell.setBusy(true); // a second click cannot send a second request (DD8-2)
      var url = isCreate ? '/api/connectors' : '/api/connectors/' + encodeURIComponent(cfg.id);
      var method = isCreate ? 'POST' : 'PUT';
      // fetchJson flattens a 422 detail list to "field: message" (squawk 0112).
      App.api.fetchJson(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: body
      }).then(function (updated) {
        App.store.invalidate('connectors'); // the Library list shows it (DD9)
        // Destroyed mid-request (a breadcrumb go, a section change): the server state
        // changed, so the invalidation stays, but nothing is written to the page.
        if (!current()) return;
        App.ui.flash(isCreate ? 'Connector created' : 'Connector saved', { container: container });
        // A create re-mounts in edit mode asynchronously and the editor STAYS BUSY
        // until then (no setBusy(false) here): park the restore for that mount.
        if (isCreate) App.focusAfter.defer(saveTok, newMountTitle);
        // Create hands off to the remount first; an edit applies the record (and
        // re-masks the token) BEFORE the callback, whose failure is not a save failure.
        if (isCreate) {
          if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, isCreate);
          return;
        }
        // Edit Save keeps this editor. Order matters for the token: the stored record
        // is the server's masked response, the controls are written FROM it (the token
        // control shows the mask with the reveal off), and the snapshot is read back
        // from the controls, so the typed plaintext is never held or compared again.
        cfg = config = stored = updated;
        applyRecord(stored);
        snapshot = JSON.stringify(readValues());
        // Squawk 0126: the title follows the saved row (a rename).
        shell.setTitle(updated.name || '');
        // No remount, so the open-time probe does not re-run on its own: re-probe for
        // the saved config, and drop the Diagnostics line that describes the old one.
        if (resetDoctorResult) resetDoctorResult();
        if (runHeaderProbe) runHeaderProbe();
        shell.setBusy(false);
        shell.setDirty(false);
        if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
        App.focusAfter.restore(saveTok, shell.titleEl);
        if (callbacks.onSaveSuccess) {
          try { callbacks.onSaveSuccess(updated, isCreate); } catch (e) {
            if (window.console && console.error) console.error('onSaveSuccess failed', e);
          }
        }
      }).catch(function (err) {
        if (!current()) return;
        shell.setError(err.message || String(err));
        shell.setBusy(false);
        App.focusAfter.defer(null);
        App.focusAfter.restore(saveTok, shell.saveButton);
      });
    }

    // The mount's handle: the glue destroys it on an identity change, and un-busies
    // it (setBusy/setError) when a create's remount cannot open the new record.
    return {
      destroy: function () {
        if (slot.isCurrent(tok)) slot.destroy();
        else destroyed = true;
      },
      setBusy: function (value) { if (current()) shell.setBusy(value); },
      setError: function (text) { if (current()) shell.setError(text); }
    };
  }

  window.App.studio.renderConnectorEditor = renderConnectorEditor;
})();
