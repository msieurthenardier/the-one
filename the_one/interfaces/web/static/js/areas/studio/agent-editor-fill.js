// App.studio.agentEditorFill -- GleepGlorp's form fill in the agent editor (M36 F3 L6, flight DD7).
//
// A fill writes values into the open agent editor as UNSAVED edits the operator reviews and
// saves: nothing is stored here, the snapshot (the dirty baseline) is never touched, and only the
// editor's own Save stores anything.
//
// Module level (the drawer's applier, js/gleepglorp-drawer/fill.js, uses these):
//   pendingBegin() -> end()   a Studio load is pending until end() (called by doSelect,
//                             doEnterCreateMode, _refresh and the init load; end is idempotent)
//   whenSettled(key, {timeoutMs}) -> Promise<boolean>  resolves true once the editor for `key`
//                             ('create' or 'edit:{name}') is mounted, the router is on it, no
//                             Studio load is pending and no model list is in flight; false at the
//                             timeout (default 10000 ms; `window.__ggFillSettleTimeoutMs` is read
//                             only in dev mode)
//   isOpen(key)               the slot holds `key` and the router is on that editor
//   selectGeneral()           the editor's own tab control, General
//   apply(view) -> Promise<{unavailable, written, kept}>
//
// Per controller (the controller calls create(ctx) once and registers it, as follow does):
//   var fill = App.studio.agentEditorFill.create(ctx);
//   handle: afterMount() (draws the notes; idempotent), clear() (drops the record and the notes),
//           apply(view), ready(key), isOpen(key), selectGeneral()
//
// ctx (controller -> module): self, state, editorEl, getFormSnapshot, checkDirty,
// currentData() (the current mount's data or null), picker (the model picker handle),
// refreshMcpSources() (the MCP sources cache refresh), setActiveTab(tab).
//
// The write (apply), all or nothing on availability, then in this order: the allowlist (twelve
// keys, anything else is ignored with one console warning); the groups the OPERATOR changed and
// has not saved are kept (a group is the operator's when it differs from the snapshot AND from
// what the last fill wrote there); the plain General fields; the tools whitelist (never widened
// by a disabled_tools-only fill); MCP and Knowledge items; and the model group LAST: setModel,
// then a synchronous checkDirty, then the wait for the model list (so the picker's re-take of the
// baseline sees the editor dirty and skips it).
//
// The notes: a record {key, at, values} of what was written per key and tab item; afterMount
// draws "Filled by GleepGlorp" under each control that still holds the recorded value.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var NOTE_TESTID = 'agent-filled-note';

  // The twelve stored keys a fill may carry (name: create only).
  var ALLOWED = [
    'name', 'description', 'system_prompt', 'provider_config_id', 'llm_model',
    'enabled_tools', 'disabled_tools', 'mcp_source_ids', 'kb_ids', 'rich_visuals',
    'max_iterations', 'chat_history_retention_days'
  ];
  var GENERAL_KEYS = [
    'name', 'description', 'system_prompt', 'max_iterations', 'chat_history_retention_days',
    'rich_visuals'
  ];
  var MODEL_KEYS = ['provider_config_id', 'llm_model'];
  // The tab groups: the stored keys, the tab handle on the editor handle and the prefix of the
  // record's item keys.
  var TABS = [
    { id: 'tools', keys: ['enabled_tools', 'disabled_tools'], handle: 'tools' },
    { id: 'mcp_source_ids', keys: ['mcp_source_ids'], handle: 'mcps' },
    { id: 'kb_ids', keys: ['kb_ids'], handle: 'knowledge' }
  ];
  var DEFAULT_TIMEOUT_MS = 10000;
  var POLL_MS = 25;

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function parse_(s) { try { return JSON.parse(s); } catch (e) { return null; } }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  // ── The pending count and the registry ────────────────────────────

  var pending = 0;
  var active = null;

  function pendingBegin() {
    pending += 1;
    var done = false;
    return function end() {
      if (done) return;
      done = true;
      pending -= 1;
    };
  }

  function routeIsEditor_(key) {
    var cur = App.router && App.router.current && App.router.current();
    if (!cur || cur.destination !== 'agents') return false;
    var segs = String(cur.route).split('/');
    if (key === 'create') return segs[1] === '~new';
    try { return decodeURIComponent(segs[1] || '') === key.slice(5); } catch (e) { return false; }
  }

  function timeoutMs_(opts) {
    var seam = window.__ggFillSettleTimeoutMs;
    if (App.config && App.config.dev_mode && typeof seam === 'number') return seam;
    return (opts && opts.timeoutMs) || DEFAULT_TIMEOUT_MS;
  }

  function whenSettled(key, opts) {
    var limit = timeoutMs_(opts);
    var t0 = Date.now();
    return new Promise(function (resolve) {
      function later() { setTimeout(check, POLL_MS); }
      function check() {
        if (Date.now() - t0 >= limit) { resolve(false); return; }
        if (!active || !active.ready(key)) { later(); return; }
        // Re-checked after a microtask: a load that starts in the same turn counts.
        Promise.resolve().then(function () {
          if (active && active.ready(key)) resolve(true);
          else later();
        });
      }
      check();
    });
  }

  // ── The per-controller handle ─────────────────────────────────────

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var editorEl = ctx.editorEl;
    var getFormSnapshot = ctx.getFormSnapshot;
    var checkDirty = ctx.checkDirty;
    var currentData_ = ctx.currentData;
    var follow = function () { return App.studio.agentEditorFollow; };

    // What the fills wrote in this mount: {key, at, values: {storedKey | 'tab:item': value}}.
    var record = null;

    function mount_() {
      var d = currentData_();
      return d && d.handle ? d : null;
    }

    function slotKey_() {
      var d = mount_();
      return d ? d.key : null;
    }

    function isOpen(key) {
      return slotKey_() === key && routeIsEditor_(key);
    }

    function ready(key) {
      return isOpen(key) && pending === 0 && ctx.picker.modelsSettled();
    }

    // ── The notes ────────────────────────────────────────────────────

    // The notes drawn now: {id, controls}. Each note's id is on its controls' aria-describedby
    // (appended, never replacing), and removed again exactly when the note goes (SC 1.3.1).
    var placed = [];
    var noteSeq = 0;
    var CONTROL_SEL = 'input, textarea, select, [role="switch"]';

    function dropDescribed_(entry) {
      entry.controls.forEach(function (c) {
        var ids = (c.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (x) {
          return x && x !== entry.id;
        });
        if (ids.length) c.setAttribute('aria-describedby', ids.join(' '));
        else c.removeAttribute('aria-describedby');
      });
    }

    function removeNotes_() {
      placed.forEach(dropDescribed_);
      placed = [];
      var old = editorEl.querySelectorAll('[data-testid="' + NOTE_TESTID + '"]');
      for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    }

    // After a note is placed: tie it to its control(s). A tab item's note follows the item's
    // row (its own toggle); a General field's note sits inside the field's host; Rich visuals'
    // follows its switch.
    function describe_(note) {
      var controls = [];
      var item = note.hasAttribute('data-item');
      var scope = null;
      if (item || note.getAttribute('data-field') === 'rich_visuals') {
        scope = note.previousElementSibling;
      } else {
        scope = note.parentNode;
      }
      if (scope) {
        if (item) {
          var first = scope.querySelector(CONTROL_SEL);
          if (first) controls.push(first);
        } else {
          if (scope.matches && scope.matches(CONTROL_SEL)) controls.push(scope);
          var all = scope.querySelectorAll(CONTROL_SEL);
          for (var i = 0; i < all.length; i++) controls.push(all[i]);
        }
      }
      var entry = { id: note.id, controls: controls };
      controls.forEach(function (c) {
        var ids = (c.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
        if (ids.indexOf(entry.id) === -1) ids.push(entry.id);
        c.setAttribute('aria-describedby', ids.join(' '));
      });
      placed.push(entry);
    }

    function buildNote_(field, item) {
      var p = document.createElement('p');
      p.id = 'agent-filled-note-' + (++noteSeq);
      p.className = 'agent-filled-note';
      p.setAttribute('data-testid', 'agent-filled-note');
      p.setAttribute('data-field', field);
      if (item !== undefined) {
        p.setAttribute('data-item', item);
        p.className += ' agent-filled-note--item';
      }
      p.appendChild(App.ui.icon('bot', { size: 'sm' }));
      var t = record && record.at ? new Date(record.at) : null;
      var when = t && !isNaN(t.getTime()) ? ' · ' + App.time.formatClock(t) : '';
      p.appendChild(document.createTextNode(' Filled by GleepGlorp' + when));
      return p;
    }

    // Draw the notes (idempotent: it removes its own first). A control the operator has since
    // changed no longer holds the recorded value, so it gets no note.
    function afterMount() {
      removeNotes_();
      var d = mount_();
      if (!record || !d || d.key !== record.key) return;
      var cur = parse_(getFormSnapshot());
      if (!cur) return;
      var rv = record.values;
      var general = d.handle.general;
      GENERAL_KEYS.forEach(function (k) {
        if (has(rv, k) && same(cur[k], rv[k])) {
          var gn = buildNote_(k);
          general.placeNote(k, gn);
          describe_(gn);
        }
      });
      var modelWritten = MODEL_KEYS.some(function (k) { return has(rv, k); });
      if (modelWritten && same(cur.provider_config_id, rv.provider_config_id) &&
          same(cur.llm_model, rv.llm_model)) {
        var mn = buildNote_('llm_model');
        general.placeNote('llm_model', mn);
        describe_(mn);
      }
      TABS.forEach(function (g) {
        var th = d.handle[g.handle];
        var map = th && th.followMap();
        if (!map) return;
        Object.keys(rv).forEach(function (k) {
          if (k.indexOf(g.id + ':') !== 0) return;
          var item = k.slice(g.id.length + 1);
          if (has(map, item) && map[item] === rv[k]) {
            var tn = buildNote_(g.id, item);
            th.followPlace(item, tn);
            describe_(tn);
          }
        });
      });
    }

    function clear() {
      record = null;
      removeNotes_();
    }

    // ── The write ────────────────────────────────────────────────────

    function selectGeneral() { ctx.setActiveTab('general'); }

    // Resolves {unavailable: true} when nothing was written, else {written, kept} (stored keys).
    function apply(view) {
      var isCreate = view.action === 'create';
      var key = isCreate ? 'create' : 'edit:' + view.agent_name;
      var d = mount_();
      if (!d || d.key !== key) return Promise.resolve({ unavailable: true });

      // 1. The allowlist.
      var vals = {};
      var ignored = [];
      Object.keys(view.values || {}).forEach(function (k) {
        if (ALLOWED.indexOf(k) === -1) ignored.push(k);
        else if (k === 'name' && !isCreate) return; // a change never renames
        else vals[k] = view.values[k];
      });
      if (ignored.length) {
        // eslint-disable-next-line no-console
        console.warn('GleepGlorp fill ' + view.id + ': ignored keys outside the allowlist: ' +
          ignored.join(', '));
      }

      // Availability: everything the fill needs must be there before any write.
      return availability_(d, vals, isCreate).then(function (ok) {
        if (!ok || currentData_() !== d) return { unavailable: true };
        return write_(d, vals, isCreate, key);
      });
    }

    function availability_(d, vals, isCreate) {
      var h = d.handle;
      var name = isCreate ? undefined : d.key.slice(5);
      var wantsMcp = has(vals, 'mcp_source_ids');
      var refresh = wantsMcp && ctx.refreshMcpSources ? ctx.refreshMcpSources() : Promise.resolve();
      return Promise.resolve(refresh).then(function () {
        if (currentData_() !== d) return false;
        if (has(vals, 'enabled_tools') || has(vals, 'disabled_tools')) {
          if (!h.tools || !h.tools.followMap()) return false;
        }
        if (wantsMcp) {
          if (!h.mcps) return false;
          h.mcps.setSources(self._allMcpSources, name);
          var mcpMap = h.mcps.followMap();
          var okMcp = (vals.mcp_source_ids || []).every(function (id) { return has(mcpMap, id); });
          if (!okMcp) return false;
        }
        if (has(vals, 'kb_ids')) {
          var kbMap = h.knowledge && h.knowledge.followMap();
          if (!kbMap) return false;
          if (!(vals.kb_ids || []).every(function (id) { return has(kbMap, id); })) return false;
        }
        return true;
      }, function () { return false; });
    }

    function write_(d, vals, isCreate, key) {
      var h = d.handle;
      var cur = parse_(getFormSnapshot());
      var base = parse_(state.snapshot);
      if (!cur || !base) return { unavailable: true };
      if (!record || record.key !== key) record = { key: key, at: null, values: {} };
      record.at = new Date().toISOString();
      var rv = record.values;
      var written = [];
      var kept = [];
      function noteKept(keys) {
        keys.forEach(function (k) { if (has(vals, k) && kept.indexOf(k) === -1) kept.push(k); });
      }
      function noteWritten(keys) {
        keys.forEach(function (k) { if (has(vals, k) && written.indexOf(k) === -1) written.push(k); });
      }
      // The operator's: differs from the snapshot (follow's test) AND from what a fill wrote.
      function operatorKey(k) {
        return follow().dirtyGroup({ keys: [k] }, cur, base) && !same(cur[k], rv[k]);
      }

      // 4. The plain General fields.
      GENERAL_KEYS.forEach(function (k) {
        if (!has(vals, k) || same(cur[k], vals[k])) return;
        if (operatorKey(k)) { noteKept([k]); return; }
        h.general.setField(k, vals[k]);
        rv[k] = vals[k];
        noteWritten([k]);
      });

      // 5-6. The tab groups.
      TABS.forEach(function (g) {
        if (!g.keys.some(function (k) { return has(vals, k); })) return;
        var th = h[g.handle];
        var target = th.followMapFor(targetConfig_(g, vals, isCreate));
        var curMap = th.followMap();
        // A snapshot taken before a tab's list loaded has no such key: nothing there is the
        // operator's (the baseline is the current state).
        var baseMap = g.keys.some(function (k) { return has(base, k); }) ? th.followMapFor(base) : curMap;
        var final = {};
        var changed = [];
        var anyKept = false;
        Object.keys(curMap).forEach(function (item) {
          var want = target[item];
          if (want === undefined || want === curMap[item]) { final[item] = curMap[item]; return; }
          var recKey = g.id + ':' + item;
          var operator = follow().tabItemDirty(curMap, baseMap, item) && curMap[item] !== rv[recKey];
          if (operator) { final[item] = curMap[item]; anyKept = true; return; }
          final[item] = want;
          changed.push(item);
          rv[recKey] = want;
        });
        th.followSet(final, null);
        if (anyKept) noteKept(g.keys);
        if (changed.length) noteWritten(g.keys);
      });

      // 7. The model group, last.
      var pickerWait = null;
      if (MODEL_KEYS.some(function (k) { return has(vals, k); })) {
        var providerId = has(vals, 'provider_config_id') ? vals.provider_config_id : cur.provider_config_id;
        var model = has(vals, 'llm_model') ? vals.llm_model : cur.llm_model;
        if (!(same(cur.provider_config_id, providerId) && same(cur.llm_model, model))) {
          if (MODEL_KEYS.some(operatorKey)) {
            noteKept(MODEL_KEYS);
          } else {
            h.general.setModel(providerId, model);
            // The editor is dirty NOW, before the list lands: the picker re-takes the baseline
            // only for a clean editor, so it must not see this write as clean.
            checkDirty();
            rv.provider_config_id = providerId;
            rv.llm_model = model;
            noteWritten(MODEL_KEYS);
            if (providerId) pickerWait = ctx.picker.fetchModelsForProvider(providerId);
          }
        }
      }

      function finish() {
        checkDirty();
        afterMount();
        return { unavailable: false, written: written, kept: kept };
      }
      checkDirty();
      return pickerWait ? pickerWait.then(finish, finish) : finish();
    }

    // The config whose enabled-set (or id list) a fill's tab values stand for.
    function targetConfig_(g, vals, isCreate) {
      if (g.id === 'mcp_source_ids') return { mcp_source_ids: vals.mcp_source_ids || [] };
      if (g.id === 'kb_ids') return { kb_ids: vals.kb_ids || [] };
      var stored = (!isCreate && self._selectedAgent) || {};
      if (has(vals, 'enabled_tools')) {
        return {
          enabled_tools: vals.enabled_tools,
          disabled_tools: has(vals, 'disabled_tools') ? vals.disabled_tools : (stored.disabled_tools || [])
        };
      }
      // disabled_tools only: a fill never widens the stored whitelist.
      var off = vals.disabled_tools || [];
      if (stored.enabled_tools !== null && stored.enabled_tools !== undefined) {
        return {
          enabled_tools: stored.enabled_tools.filter(function (n) { return off.indexOf(n) === -1; }),
          disabled_tools: off
        };
      }
      return { enabled_tools: null, disabled_tools: off };
    }

    var handle = {
      afterMount: afterMount,
      clear: clear,
      apply: apply,
      ready: ready,
      isOpen: isOpen,
      selectGeneral: selectGeneral
    };
    active = handle;
    return handle;
  }

  window.App.studio.agentEditorFill = {
    create: create,
    pendingBegin: pendingBegin,
    whenSettled: whenSettled,
    isOpen: function (key) { return !!active && active.isOpen(key); },
    selectGeneral: function () { if (active) active.selectGeneral(); },
    hasController: function () { return !!active; },
    apply: function (view) {
      return active ? active.apply(view) : Promise.resolve({ unavailable: true });
    },
    ALLOWED: ALLOWED
  };
})();
