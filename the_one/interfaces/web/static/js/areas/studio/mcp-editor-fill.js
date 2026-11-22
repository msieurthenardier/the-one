// App.studio.mcpEditorFill -- GleepGlorp's form fill in the MCP server editor (M36 F4 L4b, flight
// DD8 and DD9).
//
// A fill writes values into the open MCP server editor as UNSAVED edits the operator reviews and
// saves: nothing is stored here, the dirty baseline is never touched, no Test runs and no popup
// opens. Only the editor's own Save stores anything.
//
// Module level (the drawer's applier, js/gleepglorp-drawer/fill.js, reads these through the
// kind's spec in mcp-kinds.js):
//   attach(getController)   the glue gives the live editor controller accessor (mcp-glue.js)
//   whenSettled(key, {timeoutMs}) -> Promise<boolean>  true once the editor for `key` ('create' or
//                           'edit:{id}') is mounted with its type list, the router is on it and no
//                           Save is in flight; false at the timeout (default 10000 ms;
//                           `window.__ggFillSettleTimeoutMs` is read only in dev mode) or at once
//                           when the editor mounted without its type list (a failed fetch)
//   isOpen(key)             the live editor holds `key` and the router is on it
//   apply(view) -> Promise<{unavailable, written, kept}>
//
// Per controller (mcp-server-editor.js calls create(controller) once):
//   handle: apply(view), redraw() (draws the notes; idempotent), clear() (drops the record and
//           the notes), destroy()
//
// The write, all or nothing on availability, then in this order: the allowlist (seven keys,
// anything else ignored with one console warning; `type` only on a create); `type` (create
// only), then the fields, then the rows; then checkDirty. What the OPERATOR changed and has not
// saved is kept: a field differs from the baseline AND from what the last fill wrote there. The
// command and its arguments are one group (reported under its stored key), and each row is kept
// or written on its own. An empty value for a secret-looking key is the handoff: it adds an empty
// Sensitive row for the operator to fill in, and never replaces a row that is already there.
//
// The notes: a record {at, values} of what was written per key; redraw() draws "Filled by
// GleepGlorp" under each control that still holds the recorded value, and one note under the
// table ("Filled by GleepGlorp: A, B. Enter the value for X.").
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var NOTE_TESTID = 'mcp-filled-note';
  var ALLOWED = ['name', 'type', 'command', 'args', 'url', 'env', 'headers'];
  var ROW_KEYS = ['env', 'headers'];
  var TYPED_KEYS = ['command', 'args', 'url', 'env', 'headers'];
  var DEFAULT_TIMEOUT_MS = 10000;
  var POLL_MS = 25;

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  var getController = function () { return null; };

  function attach(fn) { getController = fn; }

  function activeFill() {
    var ctl = getController();
    return ctl && ctl.fill ? ctl.fill : null;
  }

  function routeIsEditor_(key) {
    var cur = App.router && App.router.current && App.router.current();
    if (!cur || cur.destination !== 'library') return false;
    var segs = String(cur.route).split('/');
    if (segs[1] !== 'mcp') return false;
    if (key === 'create') return segs[2] === '~new';
    try { return decodeURIComponent(segs[2] || '') === key.slice(5); } catch (e) { return false; }
  }

  function timeoutMs_(opts) {
    var seam = window.__ggFillSettleTimeoutMs;
    if (App.config && App.config.dev_mode && typeof seam === 'number') return seam;
    return (opts && opts.timeoutMs) || DEFAULT_TIMEOUT_MS;
  }

  function isOpen(key) {
    var f = activeFill();
    return !!f && f.key === key && routeIsEditor_(key);
  }

  function whenSettled(key, opts) {
    var limit = timeoutMs_(opts);
    var t0 = Date.now();
    return new Promise(function (resolve) {
      function later() { setTimeout(check, POLL_MS); }
      function state() {
        var f = activeFill();
        if (!f || f.key !== key || !routeIsEditor_(key)) return 'wait';
        if (!f.ctl.ready()) return 'failed'; // mounted without its type list
        return f.ctl.saving() ? 'wait' : 'ok';
      }
      function check() {
        if (Date.now() - t0 >= limit) { resolve(false); return; }
        var s = state();
        if (s === 'failed') { resolve(false); return; }
        if (s !== 'ok') { later(); return; }
        // Re-checked after a microtask: a mount that starts in the same turn counts.
        Promise.resolve().then(function () {
          if (state() === 'ok') resolve(true);
          else later();
        });
      }
      check();
    });
  }

  // ── The per-controller handle ─────────────────────────────────────

  function create(ctl) {
    // What the fills wrote in this mount: {at, values: {name|type|url: string,
    // command: {command, args}, 'rows:env' | 'rows:headers': {foldedKey: {key, value}}}}.
    var record = null;
    // The notes drawn now: {id, controls}. Each note's id is on its controls' aria-describedby
    // (appended, never replacing) and removed again exactly when the note goes (SC 1.3.1).
    var placed = [];
    var noteSeq = 0;
    var dead = false;

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
      var old = ctl.el.querySelectorAll('[data-testid="' + NOTE_TESTID + '"]');
      for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    }

    function buildNote_(field, text) {
      var p = document.createElement('p');
      p.id = 'mcp-filled-note-' + (++noteSeq);
      p.className = 'agent-filled-note';
      p.setAttribute('data-testid', 'mcp-filled-note');
      p.setAttribute('data-field', field);
      p.appendChild(App.ui.icon('bot', { size: 'sm' }));
      p.appendChild(document.createTextNode(' ' + text));
      return p;
    }

    function whenText_() {
      var t = record && record.at ? new Date(record.at) : null;
      return t && !isNaN(t.getTime()) ? ' · ' + App.time.formatClock(t) : '';
    }

    function link_(note, controls) {
      var entry = { id: note.id, controls: controls || [] };
      entry.controls.forEach(function (c) {
        var ids = (c.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
        if (ids.indexOf(entry.id) === -1) ids.push(entry.id);
        c.setAttribute('aria-describedby', ids.join(' '));
      });
      placed.push(entry);
    }

    // Draw the notes (idempotent: it removes its own first). A control the operator has since
    // changed no longer holds the recorded value, so it gets no note.
    function redraw() {
      if (dead) return;
      removeNotes_();
      if (!record) return;
      var rv = record.values;
      var cur = ctl.values();
      var c = cur.connection;
      ['name', 'type', 'url'].forEach(function (k) {
        if (has(rv, k) && same(c[k], rv[k])) {
          var n = buildNote_(k, 'Filled by GleepGlorp' + whenText_());
          link_(n, ctl.placeNote(k, n));
        }
      });
      if (has(rv, 'command') && c.type === 'stdio' && same(ctl.storedCommand(), rv.command)) {
        var cn = buildNote_('command', 'Filled by GleepGlorp' + whenText_());
        link_(cn, ctl.placeNote('command', cn));
      }
      var kind = ctl.rowKind();
      var rows = rv['rows:' + kind];
      if (!rows) return;
      var filled = [];
      var handoff = [];
      Object.keys(rows).forEach(function (f) {
        var st = ctl.rowState(rows[f].key);
        if (!st.exists || st.value !== rows[f].value) return;
        filled.push(rows[f].key);
        if (rows[f].value === '' && st.sensitive) handoff.push(rows[f].key);
      });
      if (!filled.length) return;
      var text = 'Filled by GleepGlorp: ' + filled.join(', ') + '.' +
        handoff.map(function (k) { return ' Enter the value for ' + k + '.'; }).join('');
      var tn = buildNote_(kind, text);
      link_(tn, ctl.placeTableNote(tn));
    }

    function clear() {
      record = null;
      removeNotes_();
    }

    // ── The write ────────────────────────────────────────────────────

    function apply(view) {
      var isCreate = view.action === 'create';
      var key = isCreate ? 'create' : 'edit:' + view.target_id;
      if (dead || ctl.key !== key || !ctl.alive() || !ctl.ready() || ctl.saving()) {
        return Promise.resolve({ unavailable: true });
      }
      var vals = {};
      var ignored = [];
      Object.keys(view.values || {}).forEach(function (k) {
        if (ALLOWED.indexOf(k) === -1) ignored.push(k);
        else if (k === 'type' && !isCreate) return; // a change never sets the type
        else vals[k] = view.values[k];
      });
      if (ignored.length) {
        // eslint-disable-next-line no-console
        console.warn('GleepGlorp fill ' + view.id + ': ignored keys outside the allowlist: ' +
          ignored.join(', '));
      }
      return Promise.resolve(write_(vals));
    }

    function write_(vals) {
      var start = ctl.values();
      var c = start.connection;
      var b = ctl.baseline().connection;
      if (!record) record = { at: null, values: {} };
      record.at = new Date().toISOString();
      var rv = record.values;
      var written = [];
      var kept = [];
      function keep(k) { if (has(vals, k) && kept.indexOf(k) === -1) kept.push(k); }
      function wrote(k) { if (written.indexOf(k) === -1) written.push(k); }
      // The operator's: differs from the baseline AND from what a fill wrote there.
      function operatorScalar(k) { return !same(c[k], b[k]) && !same(c[k], rv[k]); }

      // 1. The type, create only. One the operator chose differently is kept, and then none of
      // the fields that belong to the fill's own type are written either.
      var typeKept = false;
      if (has(vals, 'type') && c.type !== vals.type) {
        if (operatorScalar('type')) {
          keep('type');
          typeKept = true;
        } else {
          ctl.setType(vals.type);
          rv.type = vals.type;
          wrote('type');
        }
      }
      if (typeKept) {
        TYPED_KEYS.forEach(keep);
        return finish_(written, kept);
      }

      // 2. The plain fields.
      ['name', 'url'].forEach(function (k) {
        if (!has(vals, k) || same(c[k], vals[k])) return;
        if (operatorScalar(k)) { keep(k); return; }
        ctl.setField(k, vals[k]);
        rv[k] = vals[k];
        wrote(k);
      });

      // 3. The command and its arguments: one group, through the runtime collapse.
      if (has(vals, 'command') || has(vals, 'args')) {
        var now = ctl.storedCommand();
        var target = {
          command: has(vals, 'command') ? vals.command : now.command,
          args: has(vals, 'args') ? vals.args : now.args
        };
        if (!same(now, target)) {
          var groupDirty = ['runtime', 'command', 'args'].some(function (k) {
            return !same(c[k], b[k]);
          });
          if (groupDirty && !same(now, rv.command)) {
            keep(has(vals, 'command') ? 'command' : 'args');
          } else {
            ctl.setField('command', target);
            rv.command = target;
            wrote('command');
          }
        }
      }

      // 4. The rows, per key.
      ROW_KEYS.forEach(function (rk) {
        if (!has(vals, rk)) return;
        if (ctl.rowKind() !== rk) { keep(rk); return; }
        var recorded = (rv['rows:' + rk] = rv['rows:' + rk] || {});
        var entries = [];
        var anyKept = false;
        Object.keys(vals[rk]).forEach(function (name) {
          var value = vals[rk][name];
          var folded = rk === 'headers' ? name.toLowerCase() : name;
          var st = ctl.rowState(name);
          var rec = recorded[folded];
          if (!st.exists) {
            entries.push({ key: name, value: value });
            recorded[folded] = { key: name, value: value };
            return;
          }
          // Already there with this value (an earlier fill's handoff row, or a row that
          // happens to match): nothing to write.
          if (st.value === value && (value !== '' || st.sensitive)) return;
          // A handoff never replaces a row that is there.
          if (value === '') { anyKept = true; return; }
          var operator = st.masked || (st.dirty && !(rec && rec.value === st.value));
          if (operator) { anyKept = true; return; }
          entries.push({ key: name, value: value });
          recorded[folded] = { key: name, value: value };
        });
        if (entries.length) {
          ctl.setRows(entries);
          wrote(rk);
        }
        if (anyKept) keep(rk);
      });
      return finish_(written, kept);
    }

    function finish_(written, kept) {
      ctl.checkDirty();
      redraw();
      return { unavailable: false, written: written, kept: kept };
    }

    return {
      ctl: ctl,
      key: ctl.key,
      apply: apply,
      redraw: redraw,
      clear: clear,
      destroy: function () { dead = true; record = null; }
    };
  }

  window.App.studio.mcpEditorFill = {
    create: create,
    attach: attach,
    whenSettled: whenSettled,
    isOpen: isOpen,
    apply: function (view) {
      var f = activeFill();
      return f ? f.apply(view) : Promise.resolve({ unavailable: true });
    },
    ALLOWED: ALLOWED
  };
})();
