// App.admin.knowledgeSettingsController -- the handles of the mounted Knowledge indexing page, for
// GleepGlorp's form fill and an approval's follow (M36 F5 L4b, flight DD8, DD9 and DD14).
//
//   var ctl = App.admin.knowledgeSettingsController.create(env)
//
// knowledge-settings-page.js builds it once per mount and returns it on its handle
// (`getController()`, which is null while the first load is in flight). `env` is the page's
// closure:
//   {el, sizeInput, overlapInput, intervalInput, watchToggle, sizeField, overlapField,
//    intervalField, isAlive(), saving(), loadState() -> 'loading' | 'ok' | 'failed',
//    snapshot() -> {size_chars, overlap_chars, watch_enabled, reconcile_interval_seconds}
//    (the raw input strings and the switch), getBaseline() (the saved values, null before the
//    load), setBaseline(data) (a GET/PUT body: moves the baseline and the read-only facts),
//    write(pageName, value) (sets one control and clears its server error; no recompute),
//    revalidate() (the page's own recompute: validity, dirty, the leave guard), isDirty()}
//
// The fields are the flat names of the server's `app_settings` kind for this page:
// chunk_size_chars, chunk_overlap_chars, watch_enabled, reconcile_interval_seconds (the page's
// own names drop the `chunk_` prefix). Every setter is silent (no Save, no request).
//
//   key, id, el              'edit:knowledge-indexing', 'knowledge-indexing', the page root
//   alive(), ready(), saving(), onIdle(fn), idle()
//                            ready() is false only after a failed load, so a fill returns
//                            `editor_unavailable` at once instead of waiting
//   fields()                 the four names
//   values(), baseline()     numbers and a boolean (a blank or non-numeric input reads as its text)
//   setField(key, value), placeNote(key, el), addFollowNotes(detail, fields), clearNotes(),
//   isDirty(), checkDirty(), changed()
//   rebase(data)             an approved change: a clean field takes the stored value, a dirty one
//                            keeps the operator's while its baseline moves; the read-only facts
//                            refresh too
//   fill                     the GleepGlorp fill handle (knowledge-settings-fill.js)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  var FIELDS = ['chunk_size_chars', 'chunk_overlap_chars', 'watch_enabled',
    'reconcile_interval_seconds'];
  // The kind's name -> the page's own.
  var PAGE = {
    chunk_size_chars: 'size_chars',
    chunk_overlap_chars: 'overlap_chars',
    watch_enabled: 'watch_enabled',
    reconcile_interval_seconds: 'reconcile_interval_seconds'
  };

  function num(v) {
    if (typeof v === 'boolean') return v;
    var s = String(v);
    return s.trim() !== '' && !isNaN(Number(s)) ? Number(s) : s;
  }

  function create(env) {
    var dead = false;
    var idleWaiters = [];
    var fillApi = null;

    function mapped(snap) {
      var out = {};
      FIELDS.forEach(function (f) { out[f] = num(snap[PAGE[f]]); });
      return out;
    }

    function placeNote(key, note) {
      if (key === 'chunk_size_chars') { env.sizeField.el.appendChild(note); return [env.sizeInput]; }
      if (key === 'chunk_overlap_chars') {
        env.overlapField.el.appendChild(note);
        return [env.overlapInput];
      }
      if (key === 'reconcile_interval_seconds') {
        env.intervalField.el.appendChild(note);
        return [env.intervalInput];
      }
      if (key === 'watch_enabled') {
        env.watchToggle.el.after(note);
        return [env.watchToggle.control];
      }
      return null;
    }
    var followNotes = App.gleepglorpFollow.fieldNotes(placeNote,
      { testid: 'knowledge-settings-approved-change-note' });

    var ctl = {
      key: 'edit:knowledge-indexing',
      id: 'knowledge-indexing',
      el: env.el,
      alive: function () { return !dead && env.isAlive(); },
      ready: function () { return ctl.alive() && env.loadState() === 'ok'; },
      saving: function () { return env.saving(); },
      onIdle: function (fn) { if (!env.saving()) fn(); else idleWaiters.push(fn); },
      idle: function () {
        if (env.saving() || !idleWaiters.length) return;
        var list = idleWaiters;
        idleWaiters = [];
        list.forEach(function (fn) { fn(); });
      },
      fields: function () { return FIELDS.slice(); },
      checkDirty: function () { if (ctl.alive()) env.revalidate(); },
      // The page's own recompute calls this: the notes follow what the controls hold.
      changed: function () { if (!dead && fillApi) fillApi.redraw(); },
      isDirty: function () { return env.isDirty(); },
      values: function () { return mapped(env.snapshot()); },
      baseline: function () {
        var b = env.getBaseline();
        return b ? mapped(b) : {};
      },
      setField: function (key, value) {
        if (!ctl.alive() || !PAGE[key]) return false;
        env.write(PAGE[key], value);
        env.revalidate();
        return true;
      },
      placeNote: placeNote,
      addFollowNotes: function (detail, names) {
        followNotes.show(detail, (names || []).filter(function (n) { return FIELDS.indexOf(n) !== -1; }));
      },
      clearNotes: function () {
        if (fillApi) fillApi.clear();
        followNotes.clear();
      },
      rebase: function (data) {
        if (!ctl.alive() || !data || !env.getBaseline()) return false;
        var cur = env.snapshot();
        var base = env.getBaseline();
        var chunking = data.chunking || {};
        var monitoring = data.monitoring || {};
        var next = {
          size_chars: chunking.size_chars,
          overlap_chars: chunking.overlap_chars,
          watch_enabled: !!monitoring.watch_enabled,
          reconcile_interval_seconds: monitoring.reconcile_interval_seconds
        };
        Object.keys(next).forEach(function (p) {
          // Clean: the control still holds the saved value (the page compares strings).
          var clean = p === 'watch_enabled'
            ? cur[p] === base[p] : cur[p] === String(base[p]);
          if (clean) env.write(p, next[p]);
        });
        env.setBaseline(data);
        env.revalidate();
        return true;
      },
      destroy: function () {
        dead = true;
        idleWaiters = [];
        followNotes.clear();
        if (fillApi) fillApi.destroy();
      }
    };

    fillApi = App.admin.knowledgeSettingsFill.create(ctl);
    ctl.fill = fillApi;
    return ctl;
  }

  window.App.admin.knowledgeSettingsController = { create: create };
})();
