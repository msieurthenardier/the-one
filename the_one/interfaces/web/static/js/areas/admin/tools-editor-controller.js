// App.admin.toolsEditorController -- the handles of one mounted built-in tool editor, for
// GleepGlorp's form fill and an approval's follow (M36 F5 L4b, flight DD7, DD9 and DD14).
//
//   var ctl = App.admin.toolsEditorController.create(env)
//
// tools-editor.js builds it once per mount and returns it on its handle (`controller`);
// tools-page.js keeps the live one and hands it to the fill and follow modules. `env` is the
// editor's own closure:
//   {name, el, properties, fieldNames, handles, enabledToggle, showIfCtl, isAlive(), busy(),
//    recompute(), isDirty(), snapshot() -> {enabled, config}, getBaseline(), setBaseline(next)}
//
// The fields are the flat names of the server's `tool_config` kind: `enabled` (the editor's
// Enabled switch, which is not a field handle) and each served config field. Every setter is
// silent (no Save, no request, no change event) and runs the editor's own recompute, so the
// show_if rows, the dirty state and the leave guard follow.
//
//   key, id, el              'edit:{tool}', the tool's name, the editor root
//   alive(), ready(), saving(), onIdle(fn), idle()
//                            saving() is every state in which the form must not be written: a
//                            Save, an impact preview, a connection test or the open "Saving
//                            narrows N agents" dialog. idle() runs the waiters once none holds.
//   fields()                 the names this editor shows, `enabled` first
//   fillFields()             fields() without secret and list-of-paths handles: what a fill may write
//   values(), baseline()     {enabled, ...config}; the baseline is the saved one
//   setField(key, value)     one field; a show_if-hidden row is still written (and still part of
//                            the unsaved edit), it just gets no note
//   placeNote(key, el)       appends the note under the field; null for a hidden row
//   addFollowNotes(detail, fields), clearNotes(), isDirty(), checkDirty(), changed()
//   rebase(row)              an approved change: a clean field takes the stored value, a dirty
//                            one keeps the operator's while its baseline moves
//   fill                     the GleepGlorp fill handle (tool-config-fill.js)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function create(env) {
    var dead = false;
    var idleWaiters = [];
    var fillApi = null;

    function flat(snap) {
      return Object.assign({ enabled: !!snap.enabled }, snap.config);
    }

    function visible(h) { return !h.el.classList.contains('is-hidden'); }

    function placeNote(key, note) {
      if (key === 'enabled') {
        env.enabledToggle.el.after(note);
        return [env.enabledToggle.control];
      }
      var h = env.handles[key];
      if (!h || !visible(h)) return null;
      h.el.appendChild(note);
      return [h.control];
    }
    var followNotes = App.gleepglorpFollow.fieldNotes(placeNote,
      { testid: 'tool-approved-change-note' });

    function busy() { return !!env.busy(); }

    var ctl = {
      key: 'edit:' + env.name,
      id: env.name,
      el: env.el,
      alive: function () { return !dead && env.isAlive(); },
      ready: function () { return ctl.alive(); },
      saving: busy,
      onIdle: function (fn) { if (!busy()) fn(); else idleWaiters.push(fn); },
      // The editor calls this at every site that ends a busy state.
      idle: function () {
        if (busy() || !idleWaiters.length) return;
        var list = idleWaiters;
        idleWaiters = [];
        list.forEach(function (fn) { fn(); });
      },
      fields: function () {
        return ['enabled'].concat(env.fieldNames.filter(function (f) { return !!env.handles[f]; }));
      },
      // The names a fill may write: `fields()` minus the operator-only handles the server's
      // allowlist never names (a stored secret, a list of paths). Defence in depth.
      fillFields: function () {
        var props = env.properties || {};
        return ctl.fields().filter(function (k) {
          var p = props[k];
          if (!p) return true; // `enabled`
          return p.type !== 'array' && p.ui_hint !== 'password' && !p.secret;
        });
      },
      checkDirty: function () { if (ctl.alive()) env.recompute(); },
      // The editor's own change path calls this: the notes follow what the controls hold.
      changed: function () { if (!dead && fillApi) fillApi.redraw(); },
      isDirty: function () { return env.isDirty(); },
      values: function () { return flat(env.snapshot()); },
      baseline: function () { return flat(env.getBaseline()); },
      setField: function (key, value) {
        if (!ctl.alive()) return false;
        if (key === 'enabled') {
          env.enabledToggle.setChecked(!!value);
        } else if (env.handles[key]) {
          env.handles[key].setValue(value);
          env.handles[key].setError(null);
        } else {
          return false;
        }
        env.showIfCtl.apply();
        env.recompute();
        return true;
      },
      placeNote: placeNote,
      addFollowNotes: function (detail, names) {
        var shown = ctl.fields();
        followNotes.show(detail, (names || []).filter(function (n) { return shown.indexOf(n) !== -1; }));
      },
      clearNotes: function () {
        if (fillApi) fillApi.clear();
        followNotes.clear();
      },
      rebase: function (row) {
        if (!ctl.alive() || !row) return false;
        var cur = env.snapshot();
        var base = env.getBaseline();
        var stored = row.config || {};
        var next = { enabled: !!row.enabled, config: {} };
        env.fieldNames.forEach(function (f) {
          var h = env.handles[f];
          if (!h) return;
          var v = (f in stored) ? stored[f] : env.properties[f]['default'];
          if (same(cur.config[f], base.config[f])) {
            h.setValue(v);
            next.config[f] = h.value();
          } else {
            next.config[f] = v;
          }
        });
        if (cur.enabled === base.enabled) env.enabledToggle.setChecked(next.enabled);
        env.setBaseline(next);
        env.showIfCtl.apply();
        env.recompute();
        return true;
      },
      destroy: function () {
        dead = true;
        idleWaiters = [];
        followNotes.clear();
        if (fillApi) fillApi.destroy();
      }
    };

    fillApi = App.admin.toolConfigFill.create(ctl);
    ctl.fill = fillApi;
    return ctl;
  }

  window.App.admin.toolsEditorController = { create: create };
})();
