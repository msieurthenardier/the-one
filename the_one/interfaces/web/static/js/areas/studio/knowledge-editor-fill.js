// App.studio.knowledgeEditorFill -- GleepGlorp's form fill in the knowledge-base editor (M36 F5
// L3b, flight DD4, DD5 and DD14).
//
// A fill writes a name and a description into the open create form or an existing base's edit
// form as UNSAVED edits the operator reviews and saves: nothing is stored here, the dirty
// baseline is never touched. Only the editor's own Create or Save stores anything. Folders,
// files and indexing are the operator's and never part of a fill (the server kind refuses them).
//
// The module level (attach, whenSettled, isOpen, apply: the drawer's applier reads them through
// the kind's spec in knowledge-kinds.js), the note bookkeeping and the write bookkeeping are
// shared: areas/shared/gleepglorp-fill-core.js (App.gleepglorpFill). This module holds what is
// the knowledge-base editor's: the allowlist, the notes it wants and the focus seam.
//
// Per controller (knowledge-editor-controller.js calls create(controller) once):
//   handle: apply(view), redraw() (draws the notes; idempotent), clear(), destroy()
//
// What the OPERATOR changed and has not saved is kept: a field differs from the baseline AND
// from what the last fill wrote there. `written` and `kept` use the stored names.
//
// The create-focus suppression (flight DD14 leg decision 3): opening #library/knowledge/~new
// focuses the name input, which would take focus from the drawer composer on a fill navigation.
// knowledge-kinds.js sets a one-shot flag in beforeNavigate (a create only) and clears it in
// afterNavigate; knowledge-glue.js's create-focus consumes it and skips the focus when it is set.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var core = App.gleepglorpFill;
  var same = core.same;
  var has = core.has;

  var ALLOWED = ['name', 'description'];

  var mod = core.module({ routeIs: core.libraryRoute('knowledge') });

  var suppressCreateFocus = false;
  function suppressNextCreateFocus() { suppressCreateFocus = true; }
  function clearCreateFocusSuppression() { suppressCreateFocus = false; }
  function consumeCreateFocusSuppression() {
    var was = suppressCreateFocus;
    suppressCreateFocus = false;
    return was;
  }

  function create(ctl) {
    // What the fills wrote in this mount: {at, values: {name|description: value}}.
    var record = null;
    var dead = false;
    var notes = core.notes(ctl, { testid: 'kb-filled-note', skipIfUnchanged: true });

    // A note stays only under a control that still holds the value a fill wrote.
    function wanted_() {
      var out = [];
      if (!record) return out;
      var cur = ctl.values();
      ALLOWED.forEach(function (k) {
        if (has(record.values, k) && same(cur[k], record.values[k])) {
          out.push({ field: k, text: 'Filled by GleepGlorp' + notes.whenText(record) });
        }
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

  window.App.studio.knowledgeEditorFill = {
    create: create,
    attach: mod.attach,
    whenSettled: mod.whenSettled,
    isOpen: mod.isOpen,
    apply: mod.apply,
    suppressNextCreateFocus: suppressNextCreateFocus,
    clearCreateFocusSuppression: clearCreateFocusSuppression,
    consumeCreateFocusSuppression: consumeCreateFocusSuppression,
    ALLOWED: ALLOWED
  };
})();
