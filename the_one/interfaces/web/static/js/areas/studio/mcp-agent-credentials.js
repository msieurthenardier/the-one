// App.studio.mcpAgentCredentials -- the per-agent credential section of an MCP server tile in the
// agent editor's Tools tab (sortie 09 leg 6, DD12; it replaces the leg 3 per-row layout).
//
//   var cred = App.studio.mcpAgentCredentials.create({
//     source,             // the MCPSource (GET /api/mcp-sources shape: config, secrets, oauth_active)
//     agent,              // the agent record (null in create mode)
//     onChange,           // called after every state change the tile's status line should see
//     onTest,             // called by the Test button
//     saveCredentials,    // (agentName, sourceId, body) -> Promise<updated agent> (the targeted route)
//     onSaved             // (updatedAgent) after a Save landed; the tile re-tests
//   });
//
// handle: { el, setAgent(agent), adoptAgent(agent), setSource(source), payload(), isDirty(),
//           isUnlocked(), missing(), setStatus(kind, data), destroy() }
//
// `el` holds the section (titled like the Library's: "Headers" / "Environment variables", no
// button in its header) and the action row: the status line on the left, then Override
// headers + Test (locked) or Cancel + Save + Test (unlocked).
//
// LOCKED: a read-only App.ui.keyValueTable (Key and Value) of this agent's EFFECTIVE names: the
// server's own in its order, then this agent's own A-Z. A row this agent overrides carries the
// "overridden" pill. A stored sensitive value shows the mask string the API returned; a stored
// non-sensitive value shows in clear (DD12); nothing else is ever shown.
// UNLOCKED: the Library's editable table (shared.buildTable), model rows
//   {_rid, key, value, sensitive, _originalMasked, _server, _serverSet, _serverValue,
//    _serverSensitive, _stored, _bearer, overridden, lock, removable}.
// A server row's key is read-only and its value starts empty (the server's value applies);
// trash on an overridden server row returns it to the server's value. Authorization (a stored
// bearer token, a server-defined name, or any typed key matching it) keeps an editable value
// with the Sensitive toggle locked on; a server with sign-in shows no Authorization row, only a
// note. Save writes through the targeted route immediately; Cancel restores the baseline.
//
// Write shape (DD12): {headers|env: {name: "__MASKED__" (kept sensitive, under its stored
// spelling) | "text"} | null, bearer_token?: null, plain_names: [..] | null}. An empty value
// and a removed row are left out. A typed value lives only in the table's inputs until it goes
// into the targeted route's body or the /test/agent body.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var MASK = '__MASKED__';
  var DUP_MSG = 'This name is already in the table.';

  function nonBlank(v) {
    return typeof v === 'string' && v.trim() !== '';
  }

  // The stored override entry of `agent` for `source` (keyed by source name).
  function storedEntry(agent, source) {
    var all = (agent && agent.mcp_overrides) || {};
    var entry = all[source.name];
    return entry && typeof entry === 'object' ? entry : {};
  }

  // The client mirror of the server's has_credential_override (sortie 09 DD4): a non-blank
  // stored headers/env value or bearer_token, ignoring Authorization/bearer_token on a
  // source with sign-in state.
  function hasStoredCredential(source, agent) {
    var entry = storedEntry(agent, source);
    function has(map, skipAuth) {
      if (!map || typeof map !== 'object') return false;
      return Object.keys(map).some(function (k) {
        if (!nonBlank(map[k])) return false;
        return !(skipAuth && k.trim().toLowerCase() === 'authorization');
      });
    }
    if (source.type === 'stdio') return has(entry.env, false);
    var oauth = source.oauth_active === true;
    if (has(entry.headers, oauth)) return true;
    return !oauth && nonBlank(entry.bearer_token);
  }

  function joinNames(names) {
    if (names.length <= 1) return names.join('');
    return names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
  }

  function plural(n) {
    return n + ' tool' + (n === 1 ? '' : 's');
  }

  function create(opts) {
    var ui = window.App.ui;
    var shared = window.App.studio.mcpEditor.shared;   // read lazily: it loads after this file
    var source = opts.source;
    var onChange = opts.onChange || function () {};
    var onTest = opts.onTest || function () {};
    var st = {
      agent: opts.agent || null, unlocked: false, busy: false, ridSeq: 0, pendingRid: null,
      model: [], baseSnap: '', hiddenAuth: null, sectionError: null, dupErrors: {}, dup: false
    };
    var cur = null;          // {table, destroy}: the table now mounted
    var destroyed = false;
    var id = source.id;

    function isHttp() { return source.type !== 'stdio'; }
    function type() { return isHttp() ? 'streamable-http' : 'stdio'; }
    function kindName() { return isHttp() ? 'headers' : 'env'; }
    function keyOf(name) {
      var s = String(name == null ? '' : name).trim();
      return isHttp() ? s.toLowerCase() : s;
    }
    function isAuthName(name) { return isHttp() && keyOf(name) === 'authorization'; }
    function oauthActive() { return isHttp() && source.oauth_active === true; }
    function nextRid() { st.ridSeq += 1; return 'c' + st.ridSeq; }
    function createMode() { return !st.agent || !st.agent.name; }

    // ── Model ────────────────────────────────────────────────────────────────

    function decorate(r) {
      r.overridden = r._server ? nonBlank(r.value) : true;
      r.removable = r._server ? r.overridden : true;
      var tok = [];
      if (r._server) tok.push('key');
      if (isAuthName(r.key)) {
        tok.push('toggle');
        r.sensitive = true;
      }
      r.lock = tok.join(' ');
      return r;
    }

    // The effective rows of (source, agent): the server's names in its order, then this
    // agent's own A-Z. Only masks and clear non-sensitive values are ever read.
    function buildModel() {
      var entry = storedEntry(st.agent, source);
      var stored = entry[kindName()];
      stored = stored && typeof stored === 'object' ? stored : {};
      var plainSet = {};
      (Array.isArray(entry.plain_names) ? entry.plain_names : []).forEach(function (n) {
        plainSet[keyOf(n)] = true;
      });
      var storedByKey = {};
      Object.keys(stored).forEach(function (n) {
        if (nonBlank(stored[n])) storedByKey[keyOf(n)] = n;
      });
      var oauth = oauthActive();
      st.hiddenAuth = oauth && storedByKey.authorization ? storedByKey.authorization : null;
      var bearer = isHttp() && !oauth && nonBlank(entry.bearer_token) && !storedByKey.authorization;
      var rows = [];
      var seen = {};

      function row(key, server, s) {
        return {
          _rid: nextRid(), key: key, value: '', sensitive: server ? s.sensitive : true,
          _originalMasked: '', _server: server, _serverSet: server && nonBlank(s.value),
          _serverValue: server ? s.value : '', _serverSensitive: server ? s.sensitive : true,
          _stored: null, _bearer: false
        };
      }
      function useStored(r, name) {
        var k = keyOf(name);
        r._stored = name;
        r.sensitive = !plainSet[k];
        r.value = String(stored[name]);
        r._originalMasked = r.sensitive ? r.value : '';
      }
      function useBearer(r) {
        r._bearer = true;
        r.sensitive = true;
        r.value = String(entry.bearer_token);
        r._originalMasked = r.value;
      }

      shared.rowsFromSource(source, type()).forEach(function (s) {
        var k = keyOf(s.key);
        if (oauth && k === 'authorization') return;
        seen[k] = true;
        var r = row(s.key, true, s);
        if (storedByKey[k] !== undefined) useStored(r, storedByKey[k]);
        else if (bearer && k === 'authorization') useBearer(r);
        rows.push(decorate(r));
      });
      var own = [];
      Object.keys(storedByKey).forEach(function (k) {
        if (seen[k] || (oauth && k === 'authorization')) return;
        var r = row(storedByKey[k], false);
        useStored(r, storedByKey[k]);
        own.push(r);
      });
      if (bearer && !seen.authorization) {
        var b = row('Authorization', false);
        useBearer(b);
        own.push(b);
      }
      own.sort(function (x, y) {
        var a = x.key.toLowerCase();
        var c = y.key.toLowerCase();
        return a < c ? -1 : (a > c ? 1 : 0);
      });
      return rows.concat(own.map(decorate));
    }

    // The read-only view: a row this agent overrides shows its own value, any other server row
    // the server's (a plain value in clear, a secret's mask, or empty).
    function lockedRows() {
      return st.model.map(function (r) {
        return {
          _rid: r._rid, key: r.key, overridden: r.overridden, _server: r._server,
          value: r._server && !r.overridden ? r._serverValue : r.value
        };
      });
    }

    function snapOf(list) {
      return JSON.stringify(list.map(function (r) {
        return [r._rid, String(r.key), String(r.value), !!r.sensitive];
      }).sort());
    }

    function liveValues() {
      return cur && st.unlocked ? cur.table.values() : [];
    }

    function isDirty() {
      return st.unlocked && snapOf(liveValues()) !== st.baseSnap;
    }

    // The rows the missing-value check reads: the live table while unlocked, else the model.
    function effective() {
      return st.unlocked ? liveValues() : st.model;
    }

    function missingNames() {
      var out = [];
      effective().forEach(function (r) {
        if (!r._server || r._serverSet || nonBlank(r.value)) return;
        out.push(r.key);
      });
      return out;
    }

    // ── Payload ──────────────────────────────────────────────────────────────

    function buildPayload(values) {
      var out = {};
      var plain = [];
      var bearerRow = null;
      var hadBearer = st.model.some(function (r) { return r._bearer; });
      if (st.hiddenAuth) out[st.hiddenAuth] = MASK;
      values.forEach(function (r) {
        var key = String(r.key == null ? '' : r.key).trim();
        var val = String(r.value == null ? '' : r.value);
        if (r._bearer) bearerRow = r;
        if (!key || val === '') return;
        if (r._bearer && val === r._originalMasked) return;     // an unchanged bearer is kept
        var name = r._stored && keyOf(r._stored) === keyOf(key) ? r._stored : key;
        if (r.sensitive) {
          out[name] = r._stored && r._originalMasked && val === r._originalMasked ? MASK : val;
        } else {
          out[name] = val;
          if (!isAuthName(key)) plain.push(name);
        }
      });
      var res = {};
      res[kindName()] = Object.keys(out).length ? out : null;
      if (hadBearer) {
        var unchanged = bearerRow && String(bearerRow.value) === bearerRow._originalMasked &&
          String(bearerRow.value) !== '';
        if (!unchanged) res.bearer_token = null;
      }
      res.plain_names = plain.length ? plain : null;
      return res;
    }

    // ── DOM ──────────────────────────────────────────────────────────────────

    var tableHost = document.createElement('div');
    var noteHost = document.createElement('div');
    var sectionErrEl = null;
    var liveEl = document.createElement('div');
    liveEl.className = 'visually-hidden';
    liveEl.setAttribute('role', 'status');
    liveEl.setAttribute('data-testid', 'mcp-agent-cred-live-' + id);

    var section = ui.section({
      title: shared.titleFor(type()), titleTag: 'h3', layout: 'stack',
      testid: 'mcp-agent-cred-section-' + id,
      children: [tableHost, noteHost, liveEl]
    });

    var overrideLabel = isHttp() ? 'Override headers' : 'Override environment variables';
    var statusLine = ui.status({
      testid: 'mcp-agent-cred-status-' + id, state: 'idle', textTone: true
    });
    var overrideBtn = ui.button({
      variant: 'secondary', label: overrideLabel,
      ariaLabel: overrideLabel + ' for ' + source.name,
      testid: 'mcp-agent-cred-override-' + id, onClick: function () { unlock(); }
    });
    var cancelBtn = ui.button({
      variant: 'secondary', label: 'Cancel',
      ariaLabel: 'Cancel editing ' + (isHttp() ? 'headers' : 'environment variables') + ' for ' + source.name,
      testid: 'mcp-agent-cred-cancel-' + id, onClick: function () { cancel(); }
    });
    var saveBtn = ui.button({
      variant: 'primary', label: 'Save',
      ariaLabel: 'Save ' + (isHttp() ? 'headers' : 'environment variables') + ' for ' + source.name,
      testid: 'mcp-agent-cred-save-' + id, onClick: function () { save(); }
    });
    var testBtn = ui.button({
      variant: 'secondary', icon: 'play', label: 'Test',
      ariaLabel: 'Test connection for ' + source.name,
      testid: 'mcp-agent-cred-test-' + id, onClick: function () { onTest(); }
    });
    var actionsEl = document.createElement('div');
    actionsEl.className = 'mcp-agent-cred-status-actions';
    [overrideBtn, cancelBtn, saveBtn, testBtn].forEach(function (b) { actionsEl.appendChild(b); });
    var barEl = document.createElement('div');
    barEl.className = 'mcp-agent-cred-status';
    barEl.appendChild(statusLine.el);
    barEl.appendChild(actionsEl);

    var el = document.createElement('div');
    el.className = 'mcp-agent-cred';
    el.appendChild(section.el);
    el.appendChild(barEl);

    function announce(text) {
      liveEl.textContent = '';
      liveEl.textContent = text;
    }

    function makeNote(text) {
      var p = document.createElement('p');
      p.className = 'mcp-agent-cred-note';
      p.textContent = text;
      return p;
    }

    // Notes under the table: the sign-in note, and the create-mode note while unlocked.
    function renderNotes() {
      noteHost.textContent = '';
      if (oauthActive()) {
        var oauthNote = makeNote("Authorization is supplied by this server's sign-in.");
        oauthNote.setAttribute('data-testid', 'mcp-agent-cred-oauth-note-' + id);
        noteHost.appendChild(oauthNote);
      }
      if (st.unlocked && createMode()) {
        var createNote = makeNote('Save the agent first to set its own headers.');
        createNote.setAttribute('data-testid', 'mcp-agent-cred-create-note-' + id);
        noteHost.appendChild(createNote);
      }
      if (st.sectionError) {
        sectionErrEl = document.createElement('p');
        sectionErrEl.className = 'mcp-agent-cred-error';
        sectionErrEl.setAttribute('role', 'alert');
        sectionErrEl.setAttribute('data-testid', 'mcp-agent-cred-error-' + id);
        sectionErrEl.textContent = st.sectionError;
        noteHost.appendChild(sectionErrEl);
      } else {
        sectionErrEl = null;
      }
    }

    function updateButtons() {
      overrideBtn.hidden = st.unlocked;
      cancelBtn.hidden = !st.unlocked;
      saveBtn.hidden = !st.unlocked;
      overrideBtn.disabled = st.busy;
      cancelBtn.disabled = st.busy;
      saveBtn.disabled = st.busy || !isDirty() || createMode() || st.dup;
    }

    function removeLabel(n, row) {
      var k = String(row.key || '').trim();
      return k ? 'Remove ' + k : 'Remove row ' + n;
    }

    function mountTable(focusFirst) {
      if (cur) {
        cur.destroy();
        if (cur.table.el.parentNode) cur.table.el.parentNode.removeChild(cur.table.el);
      }
      st.dupErrors = {};
      st.dup = false;
      var cols = shared.tableColumns(!st.unlocked);
      var table = ui.keyValueTable({
        label: shared.titleFor(type()),
        keyColumn: 'key',
        columns: cols.columns,
        readOnly: !st.unlocked,
        rows: st.unlocked ? st.model.map(function (r) {
          var c = {};
          Object.keys(r).forEach(function (k) { c[k] = r[k]; });
          return c;
        }) : lockedRows(),
        testid: 'mcp-agent-cred-table-' + id,
        addTestid: 'mcp-agent-cred-add-' + id,
        removeLabel: removeLabel,
        rowDataset: function (row) {
          var out = { rid: row._rid || (st.pendingRid = nextRid()) };
          if (row._server) out.name = row.key;
          return out;
        },
        lockBy: 'lock',
        markerBy: 'overridden',
        markerLabel: 'overridden',
        removableBy: 'removable',
        onBeforeRemove: onBeforeRemove,
        onChange: onTableChange
      });
      cols.finish(table);
      cur = {
        table: table,
        destroy: function () {
          table.destroy();
          cols.destroy();
        }
      };
      tableHost.appendChild(table.el);
      if (st.unlocked) st.baseSnap = snapOf(st.model);
      renderNotes();
      updateButtons();
      if (focusFirst && st.unlocked) {
        if (cur.table.values().length) cur.table.focusRow(0, 'value');
        else {
          var add = cur.table.el.querySelector('[data-testid="mcp-agent-cred-add-' + id + '"]');
          if (add) add.focus();
        }
      }
    }

    // Re-derives each live row's pill, remove state and lock (Authorization) and the
    // duplicate-name errors after an edit. Only a changed value reaches the table.
    function refreshDecor() {
      var vals = cur.table.values();
      var count = {};
      vals.forEach(function (r) {
        var k = keyOf(r.key);
        if (k) count[k] = (count[k] || 0) + 1;
      });
      st.dup = false;
      vals.forEach(function (r, i) {
        var want = decorate({
          key: r.key, value: r.value, sensitive: r.sensitive, _server: !!r._server
        });
        var patch = {};
        if (!!r.overridden !== want.overridden) patch.overridden = want.overridden;
        if (!!r.removable !== want.removable) patch.removable = want.removable;
        if ((r.lock || '') !== want.lock) patch.lock = want.lock;
        if (Object.keys(patch).length) cur.table.setRow(i, patch);
        var k = keyOf(r.key);
        var msg = k && count[k] > 1 && !r._server ? DUP_MSG : null;
        if (msg) st.dup = true;
        if ((st.dupErrors[r._rid] || null) !== msg) {
          st.dupErrors[r._rid] = msg;
          cur.table.setError(i, 'key', msg);
        }
      });
    }

    function afterEdit() {
      if (destroyed) return;
      refreshDecor();
      updateButtons();
      onChange();
    }

    function onTableChange(values, ev) {
      if (destroyed || !st.unlocked) return;
      if (ev && ev.type === 'add') {
        // A new row is this agent's own and sensitive by default (DD12).
        cur.table.setRow(values.length - 1, {
          _rid: st.pendingRid || nextRid(), sensitive: true, overridden: true, removable: true
        });
        st.pendingRid = null;
      }
      if (st.sectionError) {
        st.sectionError = null;
        renderNotes();
      }
      afterEdit();
    }

    // Trash on an overridden server row returns it to the server's value; an agent-only row
    // is removed by the table. Focus leaves the button before it is disabled.
    function onBeforeRemove(row, index) {
      if (!row._server) return true;
      cur.table.focusRow(index, 'value');
      cur.table.setRow(index, {
        value: '', _originalMasked: '', sensitive: !!row._serverSensitive,
        overridden: false, removable: false
      });
      afterEdit();
      return false;
    }

    // ── Transitions ──────────────────────────────────────────────────────────

    function unlock() {
      if (st.unlocked || st.busy) return;
      st.unlocked = true;
      st.sectionError = null;
      mountTable(true);
      announce('Editing ' + (isHttp() ? 'headers' : 'environment variables') + ' for this agent');
      onChange();
    }

    function lock(focus) {
      st.unlocked = false;
      st.sectionError = null;
      mountTable(false);
      if (focus) overrideBtn.focus();
    }

    function cancel() {
      if (!st.unlocked || st.busy) return;
      lock(true);
      announce('Changes discarded');
      onChange();
    }

    function placeErrors(items) {
      var vals = cur.table.values();
      var unplaced = [];
      var first = null;
      items.forEach(function (d) {
        if (!d || !Array.isArray(d.loc) || d.loc[1] !== source.name) {
          unplaced.push(String(d && d.msg != null ? d.msg : d));
          return;
        }
        var name = d.loc[2] === 'bearer_token' ? 'Authorization' : d.loc[3];
        var idx = -1;
        if (name !== undefined) {
          vals.forEach(function (r, i) {
            if (idx < 0 && keyOf(r.key) === keyOf(name)) idx = i;
          });
        }
        if (idx < 0) {
          unplaced.push(String(d.msg == null ? '' : d.msg));
          return;
        }
        cur.table.setError(idx, 'value', String(d.msg == null ? '' : d.msg));
        if (first === null) first = idx;
      });
      var text = unplaced.map(function (t) {
        t = t.trim();
        return /[.!?]$/.test(t) ? t : t + '.';
      }).join(' ');
      st.sectionError = text || null;
      renderNotes();
      if (first !== null) cur.table.focusRow(first, 'value');
      else if (sectionErrEl) sectionErrEl.scrollIntoView({ block: 'nearest' });
    }

    function save() {
      if (!st.unlocked || st.busy || !isDirty() || createMode() || st.dup) return;
      var body = buildPayload(liveValues());
      st.busy = true;
      st.sectionError = null;
      renderNotes();
      updateButtons();
      var request;
      try {
        request = Promise.resolve(opts.saveCredentials(st.agent.name, source.id, body));
      } catch (e) {
        request = Promise.reject(e);
      }
      request.then(function (updated) {
        if (destroyed) return;
        st.busy = false;
        st.agent = updated;
        st.model = buildModel();
        lock(true);
        announce('Saved');
        if (opts.onSaved) opts.onSaved(updated);
        onChange();
      }, function (err) {
        if (destroyed) return;
        st.busy = false;
        if (err && err.status === 422 && Array.isArray(err.detail)) {
          placeErrors(err.detail);
        } else {
          st.sectionError = (err && err.message ? String(err.message) : 'Could not save.');
          renderNotes();
        }
        updateButtons();
      });
    }

    // ── Status line ──────────────────────────────────────────────────────────

    var statusSeq = 0;
    function setStatusImpl(kind_, data) {
      // An error is announced once, by the tile's role=alert block; the status words stay
      // readable but are not a second live announcement. The region keeps role=status;
      // aria-live is "off" while it shows an error and is set back to "polite" a task
      // BEFORE the next text is written, so that text is announced.
      statusSeq += 1;
      var mine = statusSeq;
      if (kind_ === 'error') {
        statusLine.el.setAttribute('aria-live', 'off');
        writeStatus(kind_, data);
      } else if (statusLine.el.getAttribute('aria-live') === 'off') {
        statusLine.el.setAttribute('aria-live', 'polite');
        setTimeout(function () { if (mine === statusSeq && !destroyed) writeStatus(kind_, data); }, 0);
      } else {
        statusLine.el.setAttribute('aria-live', 'polite');
        writeStatus(kind_, data);
      }
    }

    function writeStatus(kind_, data) {
      data = data || {};
      var withValues = data.withValues === true;
      switch (kind_) {
        case 'testing':
          statusLine.set('pending', 'Testing…');
          break;
        case 'ok':
          statusLine.set('success', (withValues ? "Connected with this agent's values · " : 'Connected · ') +
            plural(data.count || 0));
          break;
        case 'listed':
          statusLine.set('idle', (data.perAgent ? "Last checked with this agent's values · "
            : 'Last checked · ') + plural(data.count || 0));
          break;
        case 'needs':
          statusLine.set('warning', 'Needs a value for ' + joinNames(data.names || []));
          break;
        case 'none':
          statusLine.set('idle', "Not listed with this agent's values yet");
          break;
        case 'auth':
          statusLine.set('warning', 'Sign-in required');
          break;
        case 'error':
          statusLine.set('danger', withValues ? "Couldn't connect with this agent's values" : "Couldn't connect");
          break;
        default:
          statusLine.set('idle', '');
      }
    }

    // ── Handle ───────────────────────────────────────────────────────────────

    // A rebase from `source` and `st.agent`, locked (every pending edit is discarded).
    function rebase() {
      st.unlocked = false;
      st.sectionError = null;
      st.model = buildModel();
      mountTable(false);
    }

    st.model = buildModel();
    mountTable(false);

    return {
      el: el,
      // A new stored agent: the tile locks and every unsaved edit is discarded.
      setAgent: function (agent) {
        st.agent = agent || null;
        rebase();
      },
      // The agent reference only (a tile with unsaved edits is left alone by a main Save).
      adoptAgent: function (agent) {
        st.agent = agent || null;
        if (st.unlocked) { renderNotes(); updateButtons(); }
      },
      // A changed source: the rows follow it. Unsaved edits are kept.
      setSource: function (next) {
        source = next;
        if (st.unlocked && isDirty()) return;
        var wasUnlocked = st.unlocked;
        st.model = buildModel();
        st.unlocked = wasUnlocked;
        mountTable(false);
      },
      // The unsaved credential entry for /test/agent, or null (locked or unchanged).
      payload: function () { return isDirty() ? buildPayload(liveValues()) : null; },
      isDirty: isDirty,
      isUnlocked: function () { return st.unlocked; },
      // A /test/agent 422 while unlocked: the messages land on their rows (true), else the
      // caller shows the error itself (false).
      showErrors: function (items) {
        if (!st.unlocked) return false;
        placeErrors(items || []);
        return true;
      },
      missing: missingNames,
      setStatus: setStatusImpl,
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        if (cur) cur.destroy();
        if (el.parentNode) el.parentNode.removeChild(el);
      }
    };
  }

  window.App.studio.mcpAgentCredentials = {
    create: create,
    hasStoredCredential: hasStoredCredential
  };
})();
