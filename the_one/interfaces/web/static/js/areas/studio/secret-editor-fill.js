// App.studio.secretEditorFill -- GleepGlorp's form fill in the secret editor (M36 F5 L3b, flight
// DD6 and DD14).
//
// A fill writes a secret's name, description and allowed tools into the open create form or an
// existing secret's edit form as UNSAVED edits the operator reviews and saves: nothing is stored
// here and the dirty baseline is never touched. A fill NEVER writes a value: no value input, no
// masked row and no key table row is changed (the one exception is the create form's row 0 key,
// which follows the filled name's slug as typing does, unless the operator typed a key). The
// value is the operator's; a create fill says so in a note under the values table ("Enter the
// value for {key}, then Create."), which follows row 0 live and goes once a value is typed.
//
// The module level (attach, whenSettled, isOpen, apply: the drawer's applier reads them through
// the kind's spec in secret-kinds.js), the note bookkeeping and the write bookkeeping are shared:
// areas/shared/gleepglorp-fill-core.js (App.gleepglorpFill). This module holds what is the secret
// editor's.
//
// Per controller (secret-editor-controller.js calls create(controller) once):
//   handle: apply(view), redraw() (draws the notes; idempotent), clear(), destroy()
//
// What the OPERATOR changed and has not saved is kept: a field differs from the baseline AND from
// what the last fill wrote there (the ordered list, for the tools). The tools note names the
// tools added against the baseline, compared as sets so a reorder is not an addition.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var core = App.gleepglorpFill;
  var same = core.same;
  var has = core.has;

  var ALLOWED = ['name', 'description', 'allowed_tools'];
  var NOTE_ORDER = ['name', 'description', 'allowed_tools'];

  var mod = core.module({ routeIs: core.libraryRoute('secrets') });

  function create(ctl) {
    // What the fills wrote in this mount: {at, isCreate, values: {name|description|allowed_tools}}.
    var record = null;
    var dead = false;
    // The control the table note is linked to (a rebuilt row leaves it detached).
    var tableControl = null;
    var notes = core.notes(ctl, { testid: 'secret-filled-note', skipIfUnchanged: true });

    function added_(cur, base) {
      return cur.filter(function (t) { return base.indexOf(t) === -1; });
    }

    // Row 0's key and whether its value is still empty: the handoff note's wording.
    function tableText_() {
      var row = ctl.firstRow();
      if (row && row.value !== '') return null; // a value was typed
      return row && row.key
        ? 'Enter the value for ' + row.key + ', then Create.'
        : 'Enter a key and value, then Create.';
    }

    function wanted_() {
      var out = [];
      if (!record) return out;
      var cur = ctl.values();
      var base = ctl.baseline();
      var rv = record.values;
      NOTE_ORDER.forEach(function (k) {
        if (!has(rv, k) || !same(cur[k], rv[k])) return;
        if (k !== 'allowed_tools') {
          out.push({ field: k, text: 'Filled by GleepGlorp' + notes.whenText(record) });
          return;
        }
        var added = added_(cur.allowed_tools, base.allowed_tools);
        if (added.length) {
          out.push({ field: k, text: 'Filled by GleepGlorp: added ' + added.join(', ') + '.' });
        }
      });
      if (record.isCreate) {
        var text = tableText_();
        if (text) out.push({ field: 'values', table: true, text: text });
      }
      return out;
    }

    function redraw() {
      if (dead) return;
      // A rebuilt row (setValues, a removed row) detaches the control the note described.
      if (tableControl && !tableControl.isConnected) notes.removeAll();
      notes.redraw(wanted_());
      tableControl = record && record.isCreate ? ctl.valueInput() : null;
    }

    function clear() {
      record = null;
      tableControl = null;
      notes.removeAll();
    }

    function write_(vals, isCreate) {
      var c = ctl.values();
      var b = ctl.baseline();
      if (!record) record = { at: null, isCreate: isCreate, values: {} };
      record.at = new Date().toISOString();
      record.isCreate = record.isCreate || isCreate;
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
      return Promise.resolve(write_(prep.vals, prep.isCreate));
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

  window.App.studio.secretEditorFill = {
    create: create,
    attach: mod.attach,
    whenSettled: mod.whenSettled,
    isOpen: mod.isOpen,
    apply: mod.apply,
    ALLOWED: ALLOWED
  };
})();
