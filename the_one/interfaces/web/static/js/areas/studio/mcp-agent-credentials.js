// App.studio.mcpAgentCredentials -- the per-agent credential section of an MCP server tile in the
// agent editor's Tools tab (sortie 09 leg 3, DD1, DD4, DD10).
//
//   var cred = App.studio.mcpAgentCredentials.create({
//     source,            // the MCPSource (GET /api/mcp-sources shape: config, secrets, oauth_active)
//     agent,             // the agent record (null in create mode)
//     onChange,          // called after every state change an editor's dirty check should see
//     onTest             // called by the Test and Refresh buttons
//   });
//
// handle: { el, setAgent(agent), setSource(source), payload(), isDirty(), missing(),
//           showErrors(items) -> placed[], setStatus(kind, data), destroy() }
//
// `el` holds the section ("Headers for this agent" / "Environment for this agent"), then the
// connection status line with Test and Refresh. The section keeps per-name state (`pend`: a
// typed value or a removal; `news`: rows added in this edit) and derives its rows, `payload()`
// and `isDirty()` from that state, never from DOM text. No stored value is ever shown or
// held: the section sees names only (the API masks values), and a typed value lives in the
// secret input's value and the `pend` entry until it goes into the save payload or the
// /test/agent body.
//
// Write shape (DD1): payload() is null for an untouched source; otherwise
//   { headers|env: { name: "__MASKED__" (kept) | "new value" } | null, bearer_token?: null }
// where a removed name is left out, "headers: null" means none remain, and bearer_token is
// null whenever Authorization was set, replaced or removed while a bearer_token was stored.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var MASK = '__MASKED__';

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

  // Splits save-error details of one type from the rest (the controller's delegate uses it).
  function splitItems(items, type) {
    var mine = [];
    var rest = [];
    (items || []).forEach(function (d) {
      if (d && d.type === type && Array.isArray(d.loc)) mine.push(d);
      else rest.push(d);
    });
    return { mine: mine, rest: rest };
  }

  // A Save 422's mcp_override details -> the rows of the MCP servers section. Returns
  // { focus: fn | null, text } where text is the sentences of details with no tile or row.
  function placeSaveErrors(tab, items) {
    var r = tab ? tab.showCredentialErrors(items) : { placed: [], unplaced: items };
    var text = r.unplaced.map(function (d) {
      var t = String(d.msg == null ? '' : d.msg).trim();
      return /[.!?]$/.test(t) ? t : t + '.';
    }).join(' ');
    return { focus: r.placed.length ? r.placed[0].focus : null, text: text };
  }

  function create(opts) {
    var ui = window.App.ui;
    var source = opts.source;
    var onChange = opts.onChange || function () {};
    var onTest = opts.onTest || function () {};
    var st = { agent: opts.agent || null, pend: {}, news: [], newSeq: 0, sectionError: null };
    var nodes = {};          // row key -> element
    var errSeq = 0;          // unique row-error ids (a name can hold characters an id cannot)
    var destroyed = false;

    function isHttp() { return source.type !== 'stdio'; }
    function kind() { return isHttp() ? 'headers' : 'env'; }
    function keyOf(name) { return isHttp() ? String(name).toLowerCase() : String(name); }
    function oauthActive() { return isHttp() && source.oauth_active === true; }
    function noun() { return isHttp() ? 'header' : 'variable'; }

    // ── Derived rows ─────────────────────────────────────────────────────────

    function pendOf(key) {
      if (!st.pend[key]) st.pend[key] = { editing: false, value: '', removed: false, opener: null, error: null };
      return st.pend[key];
    }

    function computeRows() {
      var cfg = (source.config && source.config[kind()]) || {};
      var sec = source.secrets || {};
      var entry = storedEntry(st.agent, source);
      var byKey = {};
      var serverRows = [];
      var agentRows = [];

      function add(name, server) {
        var k = keyOf(name);
        if (byKey[k]) return byKey[k];
        var r = {
          key: k, name: name, serverDefined: server, serverSet: false, stored: false,
          storedName: null, bearer: false, oauth: false, isNew: false
        };
        byKey[k] = r;
        (server ? serverRows : agentRows).push(r);
        return r;
      }
      Object.keys(cfg).forEach(function (n) {
        var r = add(n, true);
        if (nonBlank(cfg[n])) r.serverSet = true;
      });
      Object.keys(sec).forEach(function (n) {
        var r = add(n, true);
        if (nonBlank(sec[n])) r.serverSet = true;
      });
      if (oauthActive()) add('Authorization', true).oauth = true;
      var storedMap = entry[kind()];
      if (storedMap && typeof storedMap === 'object') {
        Object.keys(storedMap).forEach(function (n) {
          var r = add(n, false);
          r.stored = true;
          r.storedName = n;
        });
      }
      if (isHttp() && nonBlank(entry.bearer_token)) {
        var a = add('Authorization', false);
        a.bearer = true;
        a.stored = true;
      }
      agentRows.sort(function (x, y) {
        var a = x.name.toLowerCase();
        var b = y.name.toLowerCase();
        return a < b ? -1 : (a > b ? 1 : 0);
      });
      var rows = serverRows.concat(agentRows);
      rows.forEach(function (r) {
        var p = st.pend[r.key] || {};
        r.editing = !!p.editing;
        r.value = p.value || '';
        r.removed = !!p.removed;
        r.opener = p.opener || null;
        r.error = p.error || null;
        r.agentOnly = !r.serverDefined;
        r.tid = r.name;
      });
      st.news.forEach(function (n) {
        rows.push({
          key: 'new-' + n.uid, isNew: true, uid: n.uid, name: n.name, value: n.value,
          editing: true, removed: false, stored: false, error: n.error, tid: 'new-' + n.uid
        });
      });
      rows.byKey = byKey;
      return rows;
    }

    function agentSet(r) {
      return !r.removed && (r.stored || (r.editing && r.value !== ''));
    }

    function missingNames(rows) {
      var out = [];
      rows.forEach(function (r) {
        if (r.isNew || r.oauth || !r.serverDefined || r.serverSet) return;
        if (!agentSet(r)) out.push(r.name);
      });
      return out;
    }

    function touched(rows) {
      return rows.some(function (r) {
        if (r.isNew) return String(r.name || '').trim() !== '' && r.value !== '';
        if (r.oauth) return false;
        return r.removed || (r.editing && r.value !== '');
      });
    }

    function payloadOf(rows) {
      var out = {};
      var bearerNull = false;
      var any = false;
      rows.forEach(function (r) {
        if (r.isNew) {
          var nm = String(r.name || '').trim();
          if (!nm || r.value === '') return;
          any = true;
          var ex = rows.byKey[keyOf(nm)];
          if (ex && ex.bearer) bearerNull = true;
          out[ex ? (ex.storedName || ex.name) : nm] = r.value;
          return;
        }
        if (r.oauth) {
          if (r.storedName) out[r.storedName] = MASK;
          return;
        }
        if (r.removed) {
          any = true;
          if (r.bearer) bearerNull = true;
          return;
        }
        if (r.editing && r.value !== '') {
          any = true;
          out[r.storedName || r.name] = r.value;
          if (r.bearer) bearerNull = true;
          return;
        }
        if (r.storedName) out[r.storedName] = MASK;
      });
      if (!any) return null;
      var res = {};
      res[kind()] = Object.keys(out).length ? out : null;
      if (bearerNull) res.bearer_token = null;
      return res;
    }

    // ── DOM ──────────────────────────────────────────────────────────────────

    var sectionTitle = isHttp() ? 'Headers for this agent' : 'Environment for this agent';
    var listEl = document.createElement('div');
    listEl.className = 'mcp-agent-cred-rows';
    var emptyEl = null;
    var sectionErrEl = null;
    var liveEl = document.createElement('div');
    liveEl.className = 'visually-hidden';
    liveEl.setAttribute('role', 'status');
    liveEl.setAttribute('data-testid', 'mcp-agent-cred-live-' + source.id);

    var addBtn = ui.button({
      variant: 'ghost', size: 'sm', icon: 'plus',
      label: isHttp() ? 'Add header' : 'Add variable',
      ariaLabel: isHttp() ? 'Add header' : 'Add variable',
      testid: 'mcp-agent-cred-add-' + source.id,
      onClick: function () { addNew(); }
    });

    var section = ui.section({
      title: sectionTitle, titleTag: 'h3', layout: 'stack',
      testid: 'mcp-agent-cred-section-' + source.id,
      children: [listEl, addBtn, liveEl]
    });

    var statusLine = ui.status({
      testid: 'mcp-agent-cred-status-' + source.id, state: 'idle', textTone: true
    });
    var testBtn = ui.button({
      size: 'sm', label: 'Test', ariaLabel: 'Test connection for ' + source.name,
      testid: 'mcp-agent-cred-test-' + source.id,
      onClick: function () { onTest(); }
    });
    var refreshBtn = ui.button({
      size: 'sm', compactIcon: true, icon: 'refresh-cw', label: 'Refresh',
      ariaLabel: 'Refresh tools for ' + source.name,
      testid: 'mcp-refresh-tools-btn-' + source.id,
      onClick: function () { onTest(); }
    });
    var actionsEl = document.createElement('div');
    actionsEl.className = 'mcp-agent-cred-status-actions';
    actionsEl.appendChild(testBtn);
    actionsEl.appendChild(refreshBtn);
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

    function stateText(r) {
      if (r.oauth) return "Supplied by the server's sign-in";
      if (r.removed) {
        if (r.serverDefined) return r.serverSet ? 'Server value · on save' : 'Set per agent · missing · on save';
        return 'Removed · on save';
      }
      if (r.isNew) return r.value !== '' ? 'Set for this agent' : 'New ' + noun();
      if (r.stored) return 'Set for this agent';
      if (r.serverDefined && !r.serverSet) return 'Set per agent · missing';
      return 'Server value';
    }

    function btn(r, role, label, aria, onClick, variant) {
      var b = ui.button({
        variant: variant || 'secondary', size: 'sm', label: label, ariaLabel: aria,
        testid: 'mcp-agent-cred-' + role + '-' + source.id + '-' + r.tid,
        onClick: onClick
      });
      b.setAttribute('data-cred-role', role);
      return b;
    }

    function labelFor(r) {
      var nm = String(r.name || '').trim();
      return nm || ('new ' + noun());
    }

    function buildRow(r) {
      var row = document.createElement('div');
      row.className = 'mcp-agent-cred-row';
      row.setAttribute('role', 'group');
      row.setAttribute('aria-label', r.isNew ? 'New ' + noun() : r.name);
      row.setAttribute('data-testid', 'mcp-agent-cred-row-' + source.id + '-' + r.tid);
      row.setAttribute('data-cred-state', r.oauth ? 'oauth' : (r.removed ? 'removed'
        : (r.stored || (r.isNew && r.value !== '') ? 'agent' : (r.serverDefined && !r.serverSet ? 'missing' : 'server'))));

      var head = document.createElement('div');
      head.className = 'mcp-agent-cred-head';
      var nameInput = null;
      if (r.isNew) {
        nameInput = ui.textInput({
          autocomplete: 'off', value: r.name,
          testid: 'mcp-agent-cred-name-' + source.id + '-' + r.tid,
          onInput: function () {
            var n = findNew(r.uid);
            if (!n) return;
            n.name = nameInput.value;
            n.error = null;
            row.setAttribute('aria-label', 'New ' + noun() + (n.name.trim() ? ' ' + n.name.trim() : ''));
            if (secret) {
              var lbl = labelFor(n);
              secret.input.setAttribute('aria-label', 'Value for ' + lbl);
              secret.setLabels('Show value for ' + lbl, 'Hide value for ' + lbl);
            }
            onChange();
          }
        });
        nameInput.setAttribute('aria-label', (isHttp() ? 'Header name' : 'Variable name'));
        head.appendChild(nameInput);
      } else {
        var nameEl = document.createElement('span');
        nameEl.className = 'mcp-agent-cred-name';
        nameEl.textContent = r.name;
        head.appendChild(nameEl);
      }
      var stateEl = document.createElement('span');
      stateEl.className = 'mcp-agent-cred-state';
      stateEl.setAttribute('data-testid', 'mcp-agent-cred-state-' + source.id + '-' + r.tid);
      stateEl.textContent = stateText(r);
      head.appendChild(stateEl);
      row.appendChild(head);

      var controls = document.createElement('div');
      controls.className = 'mcp-agent-cred-controls';
      var secret = null;
      var lbl0 = labelFor(r);

      if (r.oauth) {
        // No action: the server's sign-in supplies Authorization.
      } else if (r.editing) {
        secret = ui.secretInput({
          label: 'Value for ' + lbl0, showLabel: 'Show value for ' + lbl0, hideLabel: 'Hide value for ' + lbl0,
          autocomplete: 'off', value: r.value,
          testid: 'mcp-agent-cred-input-' + source.id + '-' + r.tid,
          revealTestid: 'mcp-agent-cred-reveal-' + source.id + '-' + r.tid
        });
        secret.input.addEventListener('input', function () {
          if (r.isNew) {
            var n = findNew(r.uid);
            if (n) { n.value = secret.input.value; n.error = null; }
          } else {
            var p = pendOf(r.key);
            p.value = secret.input.value;
            p.error = null;
          }
          onChange();
        });
        controls.appendChild(secret.el);
        controls.appendChild(btn(r, 'cancel', 'Cancel', 'Cancel editing ' + lbl0, function () { cancelEdit(r); }, 'ghost'));
      } else if (r.removed) {
        controls.appendChild(btn(r, 'undo', 'Undo', 'Undo change to ' + r.name, function () { undo(r); }, 'ghost'));
      } else if (r.stored) {
        controls.appendChild(btn(r, 'replace', 'Replace', 'Replace ' + r.name, function () { startEdit(r, 'replace'); }));
        if (r.serverDefined) {
          controls.appendChild(btn(r, 'reset', 'Use server value', 'Use server value for ' + r.name,
            function () { remove(r); }, 'ghost'));
        } else {
          controls.appendChild(btn(r, 'reset', 'Remove', 'Remove ' + r.name, function () { remove(r); }, 'ghost'));
        }
      } else {
        controls.appendChild(btn(r, 'set', 'Set for this agent', 'Set for this agent: ' + r.name,
          function () { startEdit(r, 'set'); }));
      }
      var inputEl = secret ? secret.input : nameInput;
      row.appendChild(controls);
      if (r.error) {
        var err = document.createElement('p');
        err.className = 'mcp-agent-cred-error';
        errSeq += 1;
        err.id = 'mcp-agent-cred-err-' + source.id + '-' + errSeq;
        err.setAttribute('role', 'alert');
        err.setAttribute('data-testid', 'mcp-agent-cred-row-error-' + source.id + '-' + r.tid);
        err.textContent = r.error;
        row.appendChild(err);
        var first = secret ? secret.input : (controls.querySelector('button') || inputEl);
        if (first) first.setAttribute('aria-describedby', err.id);
        // The error's input is the secret value input, or the name input of an added row.
        var invalidEl = secret ? secret.input : nameInput;
        if (invalidEl) {
          invalidEl.setAttribute('aria-invalid', 'true');
          invalidEl.addEventListener('input', function () {
            invalidEl.removeAttribute('aria-invalid');
          });
        }
      }
      return row;
    }

    function findNew(uid) {
      for (var i = 0; i < st.news.length; i++) if (st.news[i].uid === uid) return st.news[i];
      return null;
    }

    function renderList() {
      var rows = computeRows();
      listEl.textContent = '';
      nodes = {};
      rows.forEach(function (r) {
        nodes[r.key] = buildRow(r);
        listEl.appendChild(nodes[r.key]);
      });
      if (rows.length === 0) {
        if (!emptyEl) {
          emptyEl = document.createElement('p');
          emptyEl.className = 'mcp-agent-cred-empty';
          emptyEl.setAttribute('data-testid', 'mcp-agent-cred-empty-' + source.id);
          emptyEl.textContent = isHttp() ? 'This server sets no headers.' : 'This server sets no environment variables.';
        }
        listEl.appendChild(emptyEl);
      }
      setSectionError(st.sectionError);
    }

    // The section-level refusal node exists only while there is one.
    function setSectionError(msg) {
      if (!msg) {
        if (sectionErrEl && sectionErrEl.parentNode) sectionErrEl.parentNode.removeChild(sectionErrEl);
        sectionErrEl = null;
        return;
      }
      if (!sectionErrEl) {
        sectionErrEl = document.createElement('p');
        sectionErrEl.className = 'mcp-agent-cred-error';
        sectionErrEl.setAttribute('role', 'alert');
        sectionErrEl.setAttribute('data-testid', 'mcp-agent-cred-error-' + source.id);
      }
      sectionErrEl.textContent = msg;
      if (!sectionErrEl.parentNode) addBtn.parentNode.insertBefore(sectionErrEl, addBtn);
    }

    // Re-renders one row in place; returns its new element (or null once it is gone).
    function refreshRow(key) {
      var rows = computeRows();
      var r = null;
      for (var i = 0; i < rows.length; i++) if (rows[i].key === key) { r = rows[i]; break; }
      var old = nodes[key];
      if (!r) {
        if (old && old.parentNode) old.parentNode.removeChild(old);
        delete nodes[key];
        if (!rows.length) renderList();
        return null;
      }
      var fresh = buildRow(r);
      if (old && old.parentNode) old.parentNode.replaceChild(fresh, old);
      else { listEl.appendChild(fresh); }
      nodes[key] = fresh;
      return fresh;
    }

    function focusIn(node, role) {
      if (!node) return;
      var target = role ? node.querySelector('[data-cred-role="' + role + '"]') : null;
      if (!target) target = node.querySelector('button, input');
      if (target) target.focus();
    }

    // ── Transitions (event, announcement, focus) ─────────────────────────────

    function startEdit(r, opener) {
      var p = pendOf(r.key);
      p.editing = true;
      p.value = '';
      p.opener = opener;
      p.error = null;
      var node = refreshRow(r.key);
      var input = node && node.querySelector('input[type="password"], input[type="text"]');
      if (input) input.focus();
      announce('Enter a value for ' + r.name + ' for this agent');
      onChange();
    }

    function cancelEdit(r) {
      if (r.isNew) {
        st.news = st.news.filter(function (n) { return n.uid !== r.uid; });
        var old = nodes[r.key];
        if (old && old.parentNode) old.parentNode.removeChild(old);
        delete nodes[r.key];
        if (!computeRows().length) renderList();
        announce('Row removed');
        onChange();
        addBtn.focus();
        return;
      }
      var p = pendOf(r.key);
      p.editing = false;
      p.value = '';
      var node = refreshRow(r.key);
      announce(r.name + ' unchanged');
      focusIn(node, p.opener);
      onChange();
    }

    function remove(r) {
      var p = pendOf(r.key);
      p.removed = true;
      p.editing = false;
      p.value = '';
      p.error = null;
      var node = refreshRow(r.key);
      announce(r.name + (r.serverDefined && r.serverSet
        ? ' will use the server value when you save' : ' will be removed when you save'));
      focusIn(node, 'undo');
      onChange();
    }

    function undo(r) {
      var p = pendOf(r.key);
      p.removed = false;
      var node = refreshRow(r.key);
      announce(r.name + ' restored');
      focusIn(node, 'reset');
      onChange();
    }

    function addNew() {
      st.newSeq += 1;
      st.news.push({ uid: st.newSeq, name: '', value: '', error: null });
      var rows = computeRows();
      if (emptyEl && emptyEl.parentNode) emptyEl.parentNode.removeChild(emptyEl);
      var key = 'new-' + st.newSeq;
      var r = rows[rows.length - 1];
      nodes[key] = buildRow(r);
      listEl.appendChild(nodes[key]);
      var nameInput = nodes[key].querySelector('input');
      if (nameInput) nameInput.focus();
      announce('New ' + noun() + ' row added');
      onChange();
    }

    // ── Handle ───────────────────────────────────────────────────────────────

    var statusSeq = 0;
    function setStatusImpl(kind_, data) {
      // An error is announced once, by the tile's role=alert block (or the refused row's
      // message); the status words stay readable but are not a second live announcement.
      // The region keeps role=status; aria-live is "off" while it shows an error, and
      // is set back to "polite" a task BEFORE the next text is written, so that text is announced.
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

    function showErrors(items) {
      var placed = [];
      var rows = computeRows();
      (items || []).forEach(function (d) {
        if (!d || !Array.isArray(d.loc) || d.loc[1] !== source.name) return;
        var field = d.loc[2];
        var name = d.loc[3];
        var msg = String(d.msg == null ? '' : d.msg);
        var key = null;
        if (field === 'bearer_token') key = 'authorization';
        else if (name !== undefined) key = keyOf(name);
        var r = key !== null ? rows.byKey[key] : null;
        var fresh = null;    // an added row the server refused: it is keyed by what was typed
        if (!r && key !== null) {
          rows.forEach(function (x) {
            if (!fresh && x.isNew && keyOf(String(x.name || '').trim()) === key) fresh = x;
          });
        }
        if (fresh) {
          st.news.forEach(function (n) { if (n.uid === fresh.uid) n.error = msg; });
          placed.push({ key: fresh.key, focus: function () { focusIn(nodes[fresh.key]); } });
        } else if (r && !r.oauth) {
          pendOf(r.key).error = msg;
          placed.push({ key: r.key, focus: function () { focusIn(nodes[r.key]); } });
        } else {
          st.sectionError = msg;
          placed.push({ key: null, focus: function () { sectionErrEl && sectionErrEl.scrollIntoView({ block: 'nearest' }); addBtn.focus(); } });
        }
      });
      renderList();
      return placed.map(function (p) {
        return { focus: function () { if (p.key) focusIn(nodes[p.key]); else p.focus(); } };
      });
    }

    renderList();

    return {
      el: el,
      setAgent: function (agent) {
        // Always a rebase: every pending edit is discarded.
        st.agent = agent || null;
        st.pend = {};
        st.news = [];
        st.sectionError = null;
        renderList();
      },
      setSource: function (next) {
        source = next;
        st.sectionError = null;
        renderList();
      },
      payload: function () { return payloadOf(computeRows()); },
      isDirty: function () { return touched(computeRows()); },
      missing: function () { return missingNames(computeRows()); },
      showErrors: showErrors,
      setStatus: setStatusImpl,
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        listEl.textContent = '';
        if (el.parentNode) el.parentNode.removeChild(el);
      }
    };
  }

  window.App.studio.mcpAgentCredentials = {
    create: create,
    hasStoredCredential: hasStoredCredential,
    splitItems: splitItems,
    placeSaveErrors: placeSaveErrors
  };
})();
