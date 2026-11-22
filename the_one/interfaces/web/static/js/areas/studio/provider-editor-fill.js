// App.studio.providerEditorFill -- GleepGlorp's form fill in the model provider editor (M36 F4
// L5b, flight DD10 and DD11).
//
// A fill writes values into the open provider editor (a create form or an existing provider's
// edit form) as UNSAVED edits the operator reviews and saves: nothing is stored here, the dirty
// baseline is never touched, no sign-in starts and no models fetch runs. Only the editor's own
// Save stores anything.
//
// A fill NEVER carries a key, and an old key never follows a provider to a new service:
//   - the view's `clears_key` (computed on the server) says the type moves away from a
//     key-taking type: the key field is emptied, so Save sends null. When in doubt, clear: a
//     type move away from the editor's own saved key-taking type clears it too;
//   - a key the operator typed is never cleared (the note then reads "Check the key for this
//     type."), and a type the operator chose differently is kept, with the key untouched;
//   - a key-taking type a fill writes leaves the key for the operator (a note says so).
//
// Module level (the drawer's applier, js/gleepglorp-drawer/fill.js, reads these through the
// kind's spec in provider-kinds.js):
//   attach(getController)   the section gives the live editor controller accessor
//   whenSettled(key, {timeoutMs}) -> Promise<boolean>  true once the editor for `key` ('create'
//                           or 'edit:{id}') is mounted with its type list, the router is on it and
//                           no Save is in flight; false at the timeout (default 10000 ms;
//                           `window.__ggFillSettleTimeoutMs` is read only in dev mode) or at once
//                           when the type list did not load. It never waits for the models panel.
//   isOpen(key), apply(view) -> Promise<{unavailable, written, kept}>
//
// Per controller (provider-editor-controller.js calls create(controller) once):
//   handle: apply(view), redraw() (draws the notes; idempotent), clear(), destroy()
//
// The write: the allowlist (name, type, base_url, num_ctx, thinking_enabled, reasoning_effort;
// anything else, a key included, is ignored with one console warning); the type; the fields;
// the key; then checkDirty. What the OPERATOR changed and has not saved is kept: a field differs
// from the baseline AND from what the last fill wrote there. An option the chosen type does not
// show is skipped (neither written nor kept). `written` and `kept` use the stored names.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var NOTE_TESTID = 'provider-filled-note';
  var ALLOWED = ['name', 'type', 'base_url', 'num_ctx', 'thinking_enabled', 'reasoning_effort'];
  var FIELDS = ['name', 'base_url', 'num_ctx', 'thinking_enabled', 'reasoning_effort'];
  var NOTE_ORDER = ['name', 'type', 'base_url', 'num_ctx', 'thinking_enabled', 'reasoning_effort'];
  var TOKEN_TYPE = 'anthropic-plan-token';
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
    if (segs[1] !== 'providers') return false;
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
    // What the fills wrote in this mount: {at, values: {name|type|...: value}, key: null |
    // 'enter' | 'check'} (key: the note under the key row).
    var record = null;
    // The notes drawn now: [{id, controls}], each id on its controls' aria-describedby
    // (appended, never replacing) and removed again exactly when the note goes (SC 1.3.1).
    var placed = [];
    var drawnSig = null;
    var noteSeq = 0;
    var dead = false;

    function removeNotes_() {
      placed.forEach(function (entry) {
        entry.controls.forEach(function (c) {
          var ids = (c.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (x) {
            return x && x !== entry.id;
          });
          if (ids.length) c.setAttribute('aria-describedby', ids.join(' '));
          else c.removeAttribute('aria-describedby');
        });
      });
      placed = [];
      drawnSig = null;
      var old = ctl.el.querySelectorAll('[data-testid="' + NOTE_TESTID + '"]');
      for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    }

    function buildNote_(field, text) {
      var p = document.createElement('p');
      p.id = 'provider-filled-note-' + (++noteSeq);
      p.className = 'agent-filled-note';
      p.setAttribute('data-testid', 'provider-filled-note');
      p.setAttribute('data-field', field);
      p.appendChild(App.ui.icon('bot', { size: 'sm' }));
      p.appendChild(document.createTextNode(' ' + text));
      return p;
    }

    function whenText_() {
      var t = record && record.at ? new Date(record.at) : null;
      return t && !isNaN(t.getTime()) ? ' · ' + App.time.formatClock(t) : '';
    }

    function keyText_(cur) {
      if (record.key === 'check') return 'Check the key for this type.';
      return cur.type === TOKEN_TYPE
        ? 'Enter the token from claude setup-token.'
        : 'Enter the key for this type.';
    }

    // The notes that should show now: a note stays only under a control that still holds the
    // value a fill wrote (or, for the key row, in the state the note describes).
    function wanted_() {
      var out = [];
      if (!record) return out;
      var cur = ctl.values();
      var rv = record.values;
      NOTE_ORDER.forEach(function (k) {
        if (has(rv, k) && same(cur[k], rv[k]) && (k === 'name' || k === 'type' || ctl.shows(k))) {
          out.push({ field: k, text: 'Filled by GleepGlorp' + whenText_() });
        }
      });
      if (record.key && ctl.shows('api_key')) {
        var typed = cur.api_key !== '' && cur.api_key !== ctl.baseline().api_key;
        if ((record.key === 'enter' && cur.api_key === '') || (record.key === 'check' && typed)) {
          out.push({ field: 'api_key', text: keyText_(cur) });
        }
      }
      return out;
    }

    // Draw the notes (idempotent, and a no-op while the wanted set is what is drawn).
    function redraw() {
      if (dead) return;
      var list = wanted_();
      var sig = JSON.stringify(list);
      if (sig === drawnSig) return;
      removeNotes_();
      list.forEach(function (n) {
        var el = buildNote_(n.field, n.text);
        var controls = ctl.placeNote(n.field, el);
        var entry = { id: el.id, controls: controls };
        controls.forEach(function (c) {
          var ids = (c.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
          if (ids.indexOf(entry.id) === -1) ids.push(entry.id);
          c.setAttribute('aria-describedby', ids.join(' '));
        });
        placed.push(entry);
      });
      drawnSig = sig;
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
        else vals[k] = view.values[k];
      });
      if (ignored.length) {
        // eslint-disable-next-line no-console
        console.warn('GleepGlorp fill ' + view.id + ': ignored keys outside the allowlist: ' +
          ignored.join(', '));
      }
      return Promise.resolve(write_(vals, !!view.clears_key, isCreate));
    }

    function write_(vals, clearsKey, isCreate) {
      var c = ctl.values();
      var b = ctl.baseline();
      if (!record) record = { at: null, values: {}, key: null };
      record.at = new Date().toISOString();
      var rv = record.values;
      var written = [];
      var kept = [];
      function keep(k) { if (kept.indexOf(k) === -1) kept.push(k); }
      function wrote(k) { if (written.indexOf(k) === -1) written.push(k); }
      // The operator's: differs from the baseline AND from what a fill wrote there.
      function operatorScalar(k) { return !same(c[k], b[k]) && !same(c[k], rv[k]); }

      // 1. The type. One the operator chose differently (or one the list does not offer) is
      // kept: the fill neither changes it nor clears the key.
      var typeKept = false;
      var typeWritten = false;
      if (has(vals, 'type') && c.type !== vals.type) {
        if (!ctl.hasType(vals.type) || operatorScalar('type')) {
          keep('type');
          typeKept = true;
        } else {
          ctl.setType(vals.type, { keepUrl: operatorScalar('base_url') });
          rv.type = vals.type;
          wrote('type');
          typeWritten = true;
        }
      }

      // 2. The fields, against what the editor shows now. The address belongs to the fill's own
      // type, so it is not written under a type the operator chose.
      var cur = ctl.values();
      FIELDS.forEach(function (k) {
        if (!has(vals, k)) return;
        if (k === 'base_url' && typeKept) { keep(k); return; }
        if (k !== 'name' && !ctl.shows(k)) return; // not shown for this type: skipped
        if (same(cur[k], vals[k])) return;
        if (operatorScalar(k)) { keep(k); return; }
        ctl.setField(k, vals[k]);
        rv[k] = vals[k];
        wrote(k);
      });

      // 3. The key. A fill carries none. Leaving a key-taking type clears the field, unless the
      // operator typed one (kept, with a note) or chose another type (kept, key untouched).
      var after = ctl.values();
      var crossType = !isCreate && has(vals, 'type') && !typeKept && vals.type !== b.type &&
        ctl.takesKey(b.type);
      var typed = after.api_key !== '' && after.api_key !== b.api_key;
      var takesKey = ctl.takesKey(after.type);
      if ((clearsKey || crossType) && !typeKept) {
        if (typed) {
          record.key = 'check';
        } else {
          ctl.clearKey();
          if (takesKey) record.key = 'enter';
        }
      } else if (typeWritten && takesKey) {
        record.key = typed ? 'check' : 'enter';
      }
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

  window.App.studio.providerEditorFill = {
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
