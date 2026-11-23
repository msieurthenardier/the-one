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
// The module level (attach, whenSettled, isOpen, apply: the drawer's applier,
// js/gleepglorp-drawer/fill.js, reads them through the kind's spec in provider-kinds.js), the
// note bookkeeping and the write bookkeeping are shared with the MCP fill:
// areas/shared/gleepglorp-fill-core.js (App.gleepglorpFill). whenSettled never waits for the
// models panel. This module holds what is the provider editor's.
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

  var core = App.gleepglorpFill;
  var same = core.same;
  var has = core.has;

  var ALLOWED = ['name', 'type', 'base_url', 'num_ctx', 'thinking_enabled', 'reasoning_effort'];
  var FIELDS = ['name', 'base_url', 'num_ctx', 'thinking_enabled', 'reasoning_effort'];
  var NOTE_ORDER = ['name', 'type', 'base_url', 'num_ctx', 'thinking_enabled', 'reasoning_effort'];
  var TOKEN_TYPE = 'anthropic-plan-token';

  var mod = core.module({ routeIs: core.libraryRoute('providers') });

  // ── The per-controller handle ─────────────────────────────────────

  function create(ctl) {
    // What the fills wrote in this mount: {at, values: {name|type|...: value}, key: null |
    // 'enter' | 'check'} (key: the note under the key row).
    var record = null;
    var dead = false;
    var notes = core.notes(ctl, { testid: 'provider-filled-note', skipIfUnchanged: true });

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
          out.push({ field: k, text: 'Filled by GleepGlorp' + notes.whenText(record) });
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
      notes.redraw(wanted_());
    }

    function clear() {
      record = null;
      notes.removeAll();
    }

    // ── The write ────────────────────────────────────────────────────

    function apply(view) {
      var prep = core.prepare(ctl, view, { allowed: ALLOWED, dead: dead });
      if (!prep) return Promise.resolve({ unavailable: true });
      return Promise.resolve(write_(prep.vals, !!view.clears_key, prep.isCreate));
    }

    function write_(vals, clearsKey, isCreate) {
      var c = ctl.values();
      var b = ctl.baseline();
      if (!record) record = { at: null, values: {}, key: null };
      record.at = new Date().toISOString();
      var rv = record.values;
      var w = core.writer(c, b, rv);
      var keep = w.keep;
      var wrote = w.wrote;
      var operatorScalar = w.operatorScalar;

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
      return w.finish(ctl, redraw);
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
    attach: mod.attach,
    whenSettled: mod.whenSettled,
    isOpen: mod.isOpen,
    apply: mod.apply,
    ALLOWED: ALLOWED
  };
})();
