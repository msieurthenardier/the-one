// App.admin.toolConfigFill -- GleepGlorp's form fill in the built-in tool editor (M36 F5 L4b,
// flight DD7 and DD14).
//
// A fill writes a tool's `enabled` switch and its allowlisted config fields into the open editor
// (#settings/tools/{name}) as UNSAVED edits the operator reviews and saves: nothing is stored here
// and the dirty baseline is never touched. Save runs the impact dialog as today. The grid's
// toggle is never a fill target.
//
// A field the editor hides by show_if (the SearXNG URL while the backend is something else) is
// still written into its handle: it is part of the unsaved edit and of Save, and shows when the
// backend is later switched. It gets no note while its row is hidden. `search_backend` is written
// first, so a fill that sets the backend and its URL in one go writes a visible row.
//
// The module level (attach, whenSettled, isOpen, apply: the drawer's applier reads them through
// the kind's spec in tool-config-kinds.js), the note bookkeeping and the write bookkeeping are
// shared: areas/shared/gleepglorp-fill-core.js (App.gleepglorpFill). This module holds what is the
// tool editor's.
//
// Per controller (tools-editor-controller.js calls create(controller) once):
//   handle: apply(view), redraw() (draws the notes; idempotent), clear(), destroy()
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  var core = App.gleepglorpFill;
  var same = core.same;
  var has = core.has;

  var mod = core.module({ routeIs: core.settingsRoute('tools', true) });

  function create(ctl) {
    // What the fills wrote in this mount: {at, values: {field: value}}.
    var record = null;
    var dead = false;
    var notes = core.notes(ctl, { testid: 'tool-filled-note', skipIfUnchanged: true });

    function wanted_() {
      var out = [];
      if (!record) return out;
      var cur = ctl.values();
      ctl.fields().forEach(function (k) {
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
      // The backend first: its dependent rows (URL, CSE id) are then shown when they are written.
      Object.keys(vals).sort(function (x, y) {
        return (y === 'search_backend') - (x === 'search_backend');
      }).forEach(function (k) {
        if (same(c[k], vals[k])) return;
        if (w.operatorScalar(k)) { w.keep(k); return; }
        ctl.setField(k, vals[k]);
        rv[k] = vals[k];
        w.wrote(k);
      });
      return w.finish(ctl, redraw);
    }

    function apply(view) {
      var prep = core.prepare(ctl, view, { allowed: ctl.fillFields(), dead: dead });
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

  window.App.admin.toolConfigFill = {
    create: create,
    attach: mod.attach,
    whenSettled: mod.whenSettled,
    isOpen: mod.isOpen,
    apply: mod.apply
  };
})();
