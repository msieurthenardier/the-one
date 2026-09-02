// App.studio.renderConnectorsGrid / renderConnectorEditor — Studio
// connector-editor section (Mission 23 Flight 2 Leg 2, DD-9).
//
// One file, mirroring the mcp-servers-grid.js + mcp-server-editor.js split
// but SMALLER — a minimal CRUD form, not a live-status/discoverable-tool
// surface. Fields: name, type, token (masked, per-key __MASKED__ round-
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

  function _checkbox(field, checked) {
    var i = _el('input', { className: 'field-checkbox' });
    i.type = 'checkbox';
    i.setAttribute('data-field', field);
    i.checked = checked;
    return i;
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

  function _linesToArray(text) {
    return String(text || '')
      .split('\n')
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
  }

  function _arrayToLines(arr) {
    return (arr || []).join('\n');
  }

  // ── Grid ──────────────────────────────────────────────────────────────

  function renderConnectorsGrid(container, connectors, callbacks) {
    callbacks = callbacks || {};
    var onSelect = callbacks.onSelectConnector || function () {};
    var onCreate = callbacks.onCreateConnector || function () {};
    var selectedId = callbacks.selectedId || null;

    container.innerHTML = ''; // static clear — exempt from the sink freeze

    var header = _el('div', { className: 'page-header' });
    header.appendChild(_el('h1', { className: 'page-title', text: 'Connectors' }));
    var newBtn = _btn('btn-outlined-primary', 'new-connector-btn', 'New Connector');
    newBtn.addEventListener('click', function () { onCreate(); });
    header.appendChild(newBtn);
    container.appendChild(header);

    var gridEl = _el('div', { className: 'entity-tile-grid' });
    gridEl.setAttribute('role', 'listbox');
    gridEl.setAttribute('aria-label', 'Connectors');
    container.appendChild(gridEl);

    if (connectors === null || connectors === undefined) {
      gridEl.appendChild(_el('div', { className: 'admin-loading', text: 'Loading connectors…' }));
      return;
    }

    if (connectors.length === 0) {
      var empty = _el('div', { className: 'empty-canvas' });
      var inner = _el('div', { className: 'empty-canvas-inner admin-provider-empty' });
      inner.appendChild(_el('div', { text: 'No connectors configured. Add one to get started.' }));
      var emptyBtn = _btn('empty-canvas-cta', null, 'New Connector');
      emptyBtn.addEventListener('click', function () { onCreate(); });
      inner.appendChild(emptyBtn);
      empty.appendChild(inner);
      gridEl.appendChild(empty);
      return;
    }

    connectors.forEach(function (c) {
      var tile = _el('button', { className: 'entity-tile connector-tile' });
      tile.type = 'button';
      tile.setAttribute('role', 'option');
      tile.setAttribute('data-testid', 'connector-card');
      tile.setAttribute('data-id', c.id);
      tile.setAttribute('aria-selected', selectedId === c.id ? 'true' : 'false');
      tile.appendChild(_el('span', { className: 'entity-tile-badge admin-mcp-badge', text: c.type }));
      tile.appendChild(_el('span', { className: 'entity-tile-name', text: c.name }));
      tile.appendChild(_el('span', {
        className: 'entity-tile-meta',
        text: (c.config && c.config.default_agent) || '—'
      }));
      tile.addEventListener('click', function () { onSelect(c.id); });
      gridEl.appendChild(tile);
    });
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
    var header = _el('div', { className: 'editor-header' });
    var headerText = _el('div', { className: 'editor-header-text' });
    headerText.appendChild(_el('h1', {
      className: 'editor-title',
      text: isCreate ? 'New Connector' : (cfg.name || '')
    }));
    header.appendChild(headerText);

    var actions = _el('div', { className: 'form-actions' });
    var backBtn = _btn('btn-outlined-primary back-btn', 'back-connector-btn', '← Back');
    backBtn.setAttribute('aria-label', 'Back to connectors list');
    var cancelBtn = _btn('btn-outlined-primary cancel-btn', 'cancel-connector-btn', 'Cancel');
    cancelBtn.disabled = true;
    var saveBtn = _btn('btn-filled-primary save-btn', 'save-connector-btn', isCreate ? 'Create' : 'Save');
    saveBtn.disabled = true;
    var errorEl = _el('span', { className: 'editor-error' });
    actions.appendChild(backBtn);
    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);
    actions.appendChild(errorEl);
    header.appendChild(actions);
    container.appendChild(header);

    // ── Identity ─────────────────────────────────────────────────────
    var identity = _section(container, 'Identity');
    _fieldGroup(identity, 'Name', 'conn-name', _input('text', 'name', cfg.name, 'connector-name'));
    var typeOptions = types.map(function (t) { return { value: t.value, label: t.label }; });
    _fieldGroup(identity, 'Type', 'conn-type', _select('type', typeOptions, cfg.type));
    _fieldGroup(
      identity, 'Token', 'conn-token',
      _input('password', 'token', (cfg.secrets && cfg.secrets.token) || '', 'Platform credential')
    );
    // Checked-state trap (DD-6): render from `!== false`, never a truthy
    // check — `!!config.enabled` is falsy for the absent-key legacy case
    // and would invert the documented default (absent key = enabled).
    _fieldGroup(
      identity, 'Enabled', 'conn-enabled',
      _checkbox('enabled', config.enabled !== false)
    );

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

    // ── Diagnostics + Danger Zone (edit mode only) ────────────────────
    var doctorResultEl = null;
    var pairingResultEl = null;
    if (!isCreate) {
      var diagnostics = _section(container, 'Diagnostics');
      var doctorBtn = _btn('btn-outlined-primary doctor-btn', 'connector-doctor-btn', 'Run doctor');
      diagnostics.appendChild(doctorBtn);
      doctorResultEl = _el('div', { className: 'connector-doctor-result' });
      doctorResultEl.setAttribute('data-testid', 'connector-doctor-result');
      doctorResultEl.setAttribute('role', 'status');
      doctorResultEl.setAttribute('aria-live', 'polite');
      diagnostics.appendChild(doctorResultEl);

      var pairingBtn = _btn(
        'btn-outlined-primary pairing-btn', 'connector-pairing-btn', 'Generate pairing code'
      );
      diagnostics.appendChild(pairingBtn);
      pairingResultEl = _el('div', { className: 'connector-pairing-result' });
      pairingResultEl.setAttribute('data-testid', 'connector-pairing-result');
      pairingResultEl.setAttribute('role', 'status');
      pairingResultEl.setAttribute('aria-live', 'polite');
      diagnostics.appendChild(pairingResultEl);

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
          })
          .catch(function (err) {
            doctorResultEl.textContent = 'Doctor request failed: ' + (err.message || err);
          });
      });

      pairingBtn.addEventListener('click', function () {
        pairingResultEl.textContent = 'Generating…';
        fetch('/api/connectors/' + encodeURIComponent(cfg.id) + '/pairing-code', { method: 'POST' })
          .then(function (r) {
            if (!r.ok) throw new Error('pairing-code request failed: HTTP ' + r.status);
            return r.json();
          })
          .then(function (result) {
            pairingResultEl.textContent = 'Code: ' + result.code + ' (expires ' + result.expires_at + ')';
          })
          .catch(function (err) {
            pairingResultEl.textContent = err.message || String(err);
          });
      });

      deleteBtn.addEventListener('click', function () {
        window.App.confirmDelete(deleteBtn, function (el, revertFn) {
          fetch('/api/connectors/' + encodeURIComponent(cfg.id), { method: 'DELETE' })
            .then(function (r) {
              if (!r.ok) throw new Error('Delete failed');
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
    function markDirty() {
      saveBtn.disabled = false;
      cancelBtn.disabled = false;
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(true);
    }
    container.querySelectorAll('[data-field]').forEach(function (el) {
      el.addEventListener('input', markDirty);
      el.addEventListener('change', markDirty);
    });

    if (callbacks.onBack) backBtn.addEventListener('click', function () { callbacks.onBack(); });
    if (callbacks.onCancel) cancelBtn.addEventListener('click', function () { callbacks.onCancel(); });

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
        window.App.showFlash(container, isCreate ? 'Connector created' : 'Connector saved');
        if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, isCreate);
      }).catch(function (err) {
        errorEl.textContent = err.message || String(err);
      });
    });
  }

  window.App.studio.renderConnectorsGrid = renderConnectorsGrid;
  window.App.studio.renderConnectorEditor = renderConnectorEditor;
})();
