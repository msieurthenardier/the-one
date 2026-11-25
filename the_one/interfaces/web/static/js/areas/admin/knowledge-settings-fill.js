// App.admin.knowledgeSettingsFill -- GleepGlorp's form fill in the Knowledge indexing page (M36 F5
// L4b, flight DD8 and DD14).
//
// A fill writes the chunk size, chunk overlap, watch switch and reconciliation interval into the
// open page (#settings/knowledge-indexing) as UNSAVED edits the operator reviews and saves:
// nothing is stored here and the dirty baseline is never touched. The page revalidates after each
// write, so its own error shows (an overlap above half the size) and Save follows its validity.
//
// The module level (attach, whenSettled, isOpen, apply: the drawer's applier reads them through
// the `app_settings` kind's spec in app-settings-kinds.js), the note bookkeeping and the write
// bookkeeping are shared: areas/shared/gleepglorp-fill-core.js (App.gleepglorpFill). A page whose
// first load failed reports not ready, so a fill gives up at once (`editor_unavailable`).
//
// Per controller (knowledge-settings-controller.js calls create(controller) once):
//   handle: apply(view), redraw() (draws the notes; idempotent), clear(), destroy()
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  var core = App.gleepglorpFill;
  var same = core.same;
  var has = core.has;

  var ALLOWED = ['chunk_size_chars', 'chunk_overlap_chars', 'watch_enabled',
    'reconcile_interval_seconds'];

  var mod = core.module({ routeIs: core.settingsRoute('knowledge-indexing', false) });

  function create(ctl) {
    // What the fills wrote in this mount: {at, values: {field: value}}.
    var record = null;
    var dead = false;
    var notes = core.notes(ctl, { testid: 'knowledge-settings-filled-note', skipIfUnchanged: true });

    function wanted_() {
      var out = [];
      if (!record) return out;
      var cur = ctl.values();
      ALLOWED.forEach(function (k) {
        if (!has(record.values, k) || !same(cur[k], record.values[k])) return;
        out.push({ field: k, text: 'Filled by GleepGlorp' + notes.whenText(record) });
      });
      return out;
    }

    function redraw() {
      if (dead) return;
      notes.redraw(wanted_());
    }

    function clear() {
      record = null;
      notes.removeAll();
    }

    function write_(vals) {
      var c = ctl.values();
      var b = ctl.baseline();
      if (!record) record = { at: null, values: {} };
      record.at = new Date().toISOString();
      var rv = record.values;
      var w = core.writer(c, b, rv);
      ALLOWED.forEach(function (k) {
        if (!has(vals, k)) return;
        if (same(c[k], vals[k])) return;
        if (w.operatorScalar(k)) { w.keep(k); return; }
        ctl.setField(k, vals[k]);
        rv[k] = vals[k];
        w.wrote(k);
      });
      return w.finish(ctl, redraw);
    }

    function apply(view) {
      var prep = core.prepare(ctl, view, { allowed: ALLOWED, dead: dead });
      if (!prep) return Promise.resolve({ unavailable: true });
      return Promise.resolve(write_(prep.vals));
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

  window.App.admin.knowledgeSettingsFill = {
    create: create,
    attach: mod.attach,
    whenSettled: mod.whenSettled,
    isOpen: mod.isOpen,
    apply: mod.apply,
    ALLOWED: ALLOWED
  };
})();
