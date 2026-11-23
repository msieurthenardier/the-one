// App.gleepglorpFill -- what the editors' GleepGlorp form-fill modules share (M36 F5 L2, flight
// DD4). A fill writes values into an open editor as UNSAVED edits the operator reviews; the MCP
// and provider fills (areas/studio/{mcp,provider}-editor-fill.js) are built on this. The agent
// fill keeps its own record and group logic. A kind module supplies its constants, its `write_`
// and the list of notes it wants; this core is the scaffolding, the note bookkeeping and the
// bookkeeping of what a write did.
//
//   module({routeIs}) -> {attach, activeFill, isOpen, whenSettled, apply}
//       The module-level object the drawer's applier reads through the kind's spec.
//       routeIs(key) says whether the router is on the editor for `key` ('create' or
//       'edit:{id}'); the kind passes it, so the core never assumes the Library
//       (libraryRoute(section) is the Library's). attach(getController) takes the live editor
//       controller accessor; whenSettled(key, {timeoutMs}) resolves true once the editor for
//       `key` is mounted with its type list, the router is on it and no Save is in flight, and
//       false at the timeout (default 10000 ms; `window.__ggFillSettleTimeoutMs` is read only in
//       dev mode) or at once when the editor mounted without its type list.
//   libraryRoute(section) -> routeIs   #library/{section}/~new (create) or /{id} (edit:{id})
//   prepare(ctl, view, {allowed, dead, skip?}) -> null | {isCreate, vals}
//       null when the fill is unavailable (the handle is dead, or the editor is not this
//       view's, alive, ready and idle). Else the values inside the allowlist; anything else is
//       ignored with one console warning. skip(key, isCreate) drops an allowed key silently.
//   notes(ctl, {testid, idPrefix?, skipIfUnchanged?}) -> {redraw(list), removeAll(), whenText(record)}
//       The per-controller note bookkeeping. redraw(list) removes what it drew and draws each
//       {field, text, table?} through ctl.placeNote(field, el) (ctl.placeTableNote(el) for a
//       `table` entry), linking each note id on its controls' aria-describedby (appended, never
//       replacing) and unlinking it exactly when the note goes (SC 1.3.1). skipIfUnchanged makes
//       it a no-op while the wanted list is what is drawn.
//   writer(c, b, rv, {onlyIn?}) -> {written, kept, keep, wrote, operatorScalar, finish}
//       What one write did. operatorScalar(k): the control differs from the baseline AND from
//       what a fill wrote there. keep(k) records a kept key (only keys present in `onlyIn`
//       when given). finish(ctl, redraw) runs checkDirty, then redraw, then returns
//       {unavailable: false, written, kept}.
//   same(a, b), has(o, k)
(function () {
  'use strict';
  window.App = window.App || {};

  var DEFAULT_TIMEOUT_MS = 10000;
  var POLL_MS = 25;

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  function libraryRoute(section) {
    return function (key) {
      var cur = App.router && App.router.current && App.router.current();
      if (!cur || cur.destination !== 'library') return false;
      var segs = String(cur.route).split('/');
      if (segs[1] !== section) return false;
      if (key === 'create') return segs[2] === '~new';
      try { return decodeURIComponent(segs[2] || '') === key.slice(5); } catch (e) { return false; }
    };
  }

  function timeoutMs_(opts) {
    var seam = window.__ggFillSettleTimeoutMs;
    if (App.config && App.config.dev_mode && typeof seam === 'number') return seam;
    return (opts && opts.timeoutMs) || DEFAULT_TIMEOUT_MS;
  }

  function module(opts) {
    var routeIs = opts.routeIs;
    var getController = function () { return null; };

    function attach(fn) { getController = fn; }

    function activeFill() {
      var ctl = getController();
      return ctl && ctl.fill ? ctl.fill : null;
    }

    function isOpen(key) {
      var f = activeFill();
      return !!f && f.key === key && routeIs(key);
    }

    function whenSettled(key, o) {
      var limit = timeoutMs_(o);
      var t0 = Date.now();
      return new Promise(function (resolve) {
        function later() { setTimeout(check, POLL_MS); }
        function state() {
          var f = activeFill();
          if (!f || f.key !== key || !routeIs(key)) return 'wait';
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

    return {
      attach: attach,
      activeFill: activeFill,
      isOpen: isOpen,
      whenSettled: whenSettled,
      apply: function (view) {
        var f = activeFill();
        return f ? f.apply(view) : Promise.resolve({ unavailable: true });
      }
    };
  }

  function prepare(ctl, view, o) {
    var isCreate = view.action === 'create';
    var key = isCreate ? 'create' : 'edit:' + view.target_id;
    if (o.dead || ctl.key !== key || !ctl.alive() || !ctl.ready() || ctl.saving()) return null;
    var vals = {};
    var ignored = [];
    Object.keys(view.values || {}).forEach(function (k) {
      if (o.allowed.indexOf(k) === -1) ignored.push(k);
      else if (o.skip && o.skip(k, isCreate)) return;
      else vals[k] = view.values[k];
    });
    if (ignored.length) {
      // eslint-disable-next-line no-console
      console.warn('GleepGlorp fill ' + view.id + ': ignored keys outside the allowlist: ' +
        ignored.join(', '));
    }
    return { isCreate: isCreate, vals: vals };
  }

  function notes(ctl, o) {
    var testid = o.testid;
    var idPrefix = o.idPrefix || testid;
    // The notes drawn now: [{id, controls}].
    var placed = [];
    var drawnSig = null;
    var seq = 0;

    function unlink_(entry) {
      entry.controls.forEach(function (c) {
        var ids = (c.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (x) {
          return x && x !== entry.id;
        });
        if (ids.length) c.setAttribute('aria-describedby', ids.join(' '));
        else c.removeAttribute('aria-describedby');
      });
    }

    function link_(entry) {
      entry.controls.forEach(function (c) {
        var ids = (c.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
        if (ids.indexOf(entry.id) === -1) ids.push(entry.id);
        c.setAttribute('aria-describedby', ids.join(' '));
      });
      placed.push(entry);
    }

    function removeAll() {
      placed.forEach(unlink_);
      placed = [];
      drawnSig = null;
      var old = ctl.el.querySelectorAll('[data-testid="' + testid + '"]');
      for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    }

    function build_(field, text) {
      var p = document.createElement('p');
      p.id = idPrefix + '-' + (++seq);
      p.className = 'agent-filled-note';
      p.setAttribute('data-testid', testid);
      p.setAttribute('data-field', field);
      p.appendChild(App.ui.icon('bot', { size: 'sm' }));
      p.appendChild(document.createTextNode(' ' + text));
      return p;
    }

    function redraw(list) {
      var sig = null;
      if (o.skipIfUnchanged) {
        sig = JSON.stringify(list);
        if (sig === drawnSig) return;
      }
      removeAll();
      list.forEach(function (n) {
        var el = build_(n.field, n.text);
        var controls = n.table ? ctl.placeTableNote(el) : ctl.placeNote(n.field, el);
        link_({ id: el.id, controls: controls || [] });
      });
      drawnSig = sig;
    }

    function whenText(record) {
      var t = record && record.at ? new Date(record.at) : null;
      return t && !isNaN(t.getTime()) ? ' · ' + App.time.formatClock(t) : '';
    }

    return { redraw: redraw, removeAll: removeAll, whenText: whenText };
  }

  function writer(c, b, rv, o) {
    var onlyIn = o && o.onlyIn;
    var written = [];
    var kept = [];
    return {
      written: written,
      kept: kept,
      keep: function (k) {
        if (onlyIn && !has(onlyIn, k)) return;
        if (kept.indexOf(k) === -1) kept.push(k);
      },
      wrote: function (k) { if (written.indexOf(k) === -1) written.push(k); },
      // The operator's: differs from the baseline AND from what a fill wrote there.
      operatorScalar: function (k) { return !same(c[k], b[k]) && !same(c[k], rv[k]); },
      finish: function (ctl, redraw) {
        ctl.checkDirty();
        redraw();
        return { unavailable: false, written: written, kept: kept };
      }
    };
  }

  window.App.gleepglorpFill = {
    module: module, libraryRoute: libraryRoute, prepare: prepare, notes: notes, writer: writer,
    same: same, has: has
  };
})();
