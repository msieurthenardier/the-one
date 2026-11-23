// App.studio.providerEditorController -- the handles of one mounted provider editor, for
// GleepGlorp's form fill and an approval's follow (M36 F4 L5b, flight DD10 and DD11).
//
//   var ctl = App.studio.providerEditorController.create(env)
//
// provider-editor.js builds it once per mount and returns it (providers-section.js keeps the
// live one and hands it to the fill and follow modules). `env` is the editor's own closure:
//   {h, el, isCreate, id, types, typeDefaults(type), applyType(type), adopt(row), checkDirty(),
//    isCurrent(), saving(), snapshot([json])}
//
// Every setter is silent (no Save, no Test, no sign-in, no models fetch, no request); the caller
// runs checkDirty() once it has written. Values are keyed by the STORED names (name, type,
// base_url, num_ctx, thinking_enabled, reasoning_effort, api_key); the dirty snapshot is keyed
// by the data-field names (config.num_ctx, ...).
//
//   key, isCreate, id, el    'create' | 'edit:{id}', the mode, the stored id, the editor root
//   alive(), ready(), saving(), onIdle(fn), idle()
//                            alive: this mount is the current one and not destroyed; ready: the
//                            type list loaded (an empty list is a failed fetch)
//   values(), baseline()     the live and the saved values; api_key is whatever the key input
//                            holds (the masked string when untouched), never a real key
//   hasType(t), takesKey(t)  the type list offers t; the type shows a key row
//   shows(key)               the field's row is visible for the current type
//   setType(t, {keepUrl})    the type select and everything the change handler does (rows, the
//                            default address, the key label); keepUrl keeps the typed address
//                            when the new type shows one
//   setField(key, value)     name, base_url, num_ctx, thinking_enabled, reasoning_effort; false
//                            when the row is not shown
//   clearKey()               empties the key input, so Save sends null
//   placeNote(key, el)       appends the note under the field's row; returns its controls
//   placeFollowNote(el), clearNotes(), isDirty(), rebase(row), afterCancel(fn)
//   fill                     the GleepGlorp fill handle (provider-editor-fill.js)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var DEFAULT_NUM_CTX = 32768;
  var FOLLOW_TESTID = 'provider-approved-change-note';
  // stored name -> the data-field name of the dirty snapshot
  var FIELD = {
    name: 'name', type: 'type', base_url: 'base_url', api_key: 'api_key',
    num_ctx: 'config.num_ctx', thinking_enabled: 'config.thinking_enabled',
    reasoning_effort: 'config.reasoning_effort'
  };

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function numberOf(v) {
    var n = Number(v);
    return v !== '' && isFinite(n) ? n : v;
  }

  // The snapshot (data-field keys) of a stored provider row, as the editor builds it at mount.
  function snapshotOf(row) {
    var cfg = row.config || {};
    return {
      name: row.name || '', type: row.type, base_url: row.base_url || '',
      api_key: row.api_key || '',
      'config.num_ctx': String(cfg.num_ctx != null ? cfg.num_ctx : DEFAULT_NUM_CTX),
      'config.thinking_enabled': !!cfg.thinking_enabled,
      'config.reasoning_effort': cfg.reasoning_effort || ''
    };
  }

  // Stored-name values from a data-field snapshot.
  function valuesOf(snap) {
    var out = {};
    Object.keys(FIELD).forEach(function (k) { out[k] = snap[FIELD[k]]; });
    out.num_ctx = numberOf(out.num_ctx);
    return out;
  }

  function create(env) {
    var h = env.h;
    var dead = false;
    var idleWaiters = [];
    var cancelHook = null;
    var fillApi = null;

    var rows = {
      name: h.name, type: h.type, base_url: h.baseUrl, api_key: h.apiKey, num_ctx: h.numCtx,
      thinking_enabled: h.thinking, reasoning_effort: h.effort
    };
    var controls = {
      name: h.name.control, type: h.type.control, base_url: h.baseUrl.control,
      api_key: h.secret.input, num_ctx: h.numCtx.control, thinking_enabled: h.thinking.control,
      reasoning_effort: h.effort.control
    };

    function liveSnapshot() {
      var data = {};
      h.fieldEls.forEach(function (el) {
        data[el.dataset.field] = el.type === 'checkbox' ? el.checked : el.value;
      });
      return data;
    }

    function write(key, value) {
      if (key === 'api_key') h.secret.setValue(value);
      else if (key === 'thinking_enabled') controls[key].checked = !!value;
      else controls[key].value = String(value);
    }

    function removeFollowNote() {
      var old = env.el.querySelectorAll('[data-testid="' + FOLLOW_TESTID + '"]');
      for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    }

    var ctl = {
      key: env.isCreate ? 'create' : 'edit:' + env.id,
      isCreate: env.isCreate,
      id: env.id,
      el: env.el,
      alive: function () { return !dead && env.isCurrent(); },
      ready: function () { return ctl.alive() && (env.types || []).length > 0; },
      saving: function () { return env.saving(); },
      onIdle: function (fn) { if (!env.saving()) fn(); else idleWaiters.push(fn); },
      idle: function () {
        var list = idleWaiters;
        idleWaiters = [];
        list.forEach(function (fn) { fn(); });
      },
      checkDirty: function () { if (ctl.alive()) env.checkDirty(); },
      values: function () { return valuesOf(liveSnapshot()); },
      baseline: function () { return valuesOf(JSON.parse(env.snapshot())); },
      hasType: function (t) {
        return (env.types || []).some(function (x) { return x.value === t; });
      },
      takesKey: function (t) {
        var d = env.typeDefaults(t);
        return !!(d && d.showApiKey);
      },
      shows: function (key) { return !!rows[key] && !rows[key].el.hidden; },
      setType: function (t, opts) {
        if (!ctl.alive() || !ctl.hasType(t)) return false;
        var url = opts && opts.keepUrl ? controls.base_url.value : null;
        controls.type.value = t;
        env.applyType(t);
        var d = env.typeDefaults(t);
        if (url !== null && d && d.showBaseUrl) controls.base_url.value = url;
        return true;
      },
      setField: function (key, value) {
        if (!ctl.alive() || !controls[key] || key === 'api_key' || key === 'type') return false;
        if (key !== 'name' && !ctl.shows(key)) return false;
        write(key, value);
        return true;
      },
      clearKey: function () { if (ctl.alive()) h.secret.setValue(''); },
      placeNote: function (key, note) {
        if (!rows[key]) return [];
        rows[key].el.appendChild(note);
        return [controls[key]];
      },
      // The follow note: one line under the header, replacing the last one.
      placeFollowNote: function (note) {
        removeFollowNote();
        note.setAttribute('data-testid', FOLLOW_TESTID);
        h.shell.el.parentNode.insertBefore(note, h.shell.el.nextSibling);
      },
      clearNotes: function () {
        if (fillApi) fillApi.clear();
        removeFollowNote();
      },
      isDirty: function () { return !same(liveSnapshot(), JSON.parse(env.snapshot())); },
      // A Cancel that has reverted the form (the editor's own click handler ran first) runs this
      // once: the follow uses it to open the provider as an approval changed it.
      afterCancel: function (fn) { cancelHook = fn; },
      // An approved change for this provider that kept its type: a clean field takes the stored
      // value, a dirty one keeps the operator's while its baseline moves. False when the stored
      // type is not the mounted one (the follow re-mounts or notes that instead).
      rebase: function (row) {
        if (!ctl.alive() || env.isCreate || !row) return false;
        var base = JSON.parse(env.snapshot());
        if (row.type !== base.type) return false;
        var live = liveSnapshot();
        var next = snapshotOf(row);
        Object.keys(next).forEach(function (field) {
          if (!(field in base)) return;
          if (same(live[field], base[field])) {
            Object.keys(FIELD).forEach(function (k) { if (FIELD[k] === field) write(k, next[field]); });
          }
          base[field] = next[field];
        });
        env.snapshot(JSON.stringify(base));
        env.adopt(row);
        env.checkDirty();
        return true;
      },
      destroy: function () {
        dead = true;
        if (fillApi) fillApi.destroy();
      }
    };

    // Cancel runs the editor's own handler first (it was registered with the shell).
    if (h.shell.cancelButton) {
      h.shell.cancelButton.addEventListener('click', function () {
        var fn = cancelHook;
        cancelHook = null;
        if (fn && ctl.alive()) fn();
      });
    }

    fillApi = App.studio.providerEditorFill.create(ctl);
    ctl.fill = fillApi;
    // The notes follow the controls the operator edits (a note stays only under a control that
    // still holds the written value).
    ['input', 'change'].forEach(function (ev) {
      h.fieldEls.forEach(function (el) { el.addEventListener(ev, function () { fillApi.redraw(); }); });
    });
    return ctl;
  }

  window.App.studio.providerEditorController = { create: create };
})();
