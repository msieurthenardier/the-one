// App.studio.mcpEditorFill -- GleepGlorp's form fill in the MCP server editor (M36 F4 L4b, flight
// DD8 and DD9).
//
// A fill writes values into the open MCP server editor as UNSAVED edits the operator reviews and
// saves: nothing is stored here, the dirty baseline is never touched, no Test runs and no popup
// opens. Only the editor's own Save stores anything.
//
// The module level (attach, whenSettled, isOpen, apply: the drawer's applier,
// js/gleepglorp-drawer/fill.js, reads them through the kind's spec in mcp-kinds.js), the note
// bookkeeping and the write bookkeeping are shared with the provider fill:
// areas/shared/gleepglorp-fill-core.js (App.gleepglorpFill). This module holds what is the MCP
// editor's.
//
// Per controller (mcp-server-editor.js calls create(controller) once):
//   handle: apply(view), redraw() (draws the notes; idempotent), clear() (drops the record and
//           the notes), destroy()
//
// The write, all or nothing on availability, then in this order: the allowlist (seven keys,
// anything else ignored with one console warning; `type` only on a create); `type` (create
// only), then the fields, then the rows; then checkDirty. What the OPERATOR changed and has not
// saved is kept: a field differs from the baseline AND from what the last fill wrote there. The
// command and its arguments are one group (reported under its stored key), and each row is kept
// or written on its own. An empty value for a secret-looking key is the handoff: it adds an empty
// Sensitive row for the operator to fill in, and never replaces a row that is already there.
//
// The notes: a record {at, values} of what was written per key; redraw() draws "Filled by
// GleepGlorp" under each control that still holds the recorded value, and one note under the
// table ("Filled by GleepGlorp: A, B. Enter the value for X."). The rows re-render on a rebase,
// a type switch and a row write, which discards the notes inside them, so this module always
// redraws (it does not skip an unchanged list).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var core = App.gleepglorpFill;
  var same = core.same;
  var has = core.has;

  var ALLOWED = ['name', 'type', 'command', 'args', 'url', 'env', 'headers'];
  var ROW_KEYS = ['env', 'headers'];
  var TYPED_KEYS = ['command', 'args', 'url', 'env', 'headers'];

  var mod = core.module({ routeIs: core.libraryRoute('mcp') });

  // ── The per-controller handle ─────────────────────────────────────

  function create(ctl) {
    // What the fills wrote in this mount: {at, values: {name|type|url: string,
    // command: {command, args}, 'rows:env' | 'rows:headers': {foldedKey: {key, value}}}}.
    var record = null;
    var dead = false;
    var notes = core.notes(ctl, { testid: 'mcp-filled-note' });

    // The notes that should show now. A control the operator has since changed no longer holds
    // the recorded value, so it gets no note.
    function wanted_() {
      var out = [];
      if (!record) return out;
      var rv = record.values;
      var c = ctl.values().connection;
      var filledText = 'Filled by GleepGlorp' + notes.whenText(record);
      ['name', 'type', 'url'].forEach(function (k) {
        if (has(rv, k) && same(c[k], rv[k])) out.push({ field: k, text: filledText });
      });
      if (has(rv, 'command') && c.type === 'stdio' && same(ctl.storedCommand(), rv.command)) {
        out.push({ field: 'command', text: filledText });
      }
      var kind = ctl.rowKind();
      var rows = rv['rows:' + kind];
      if (!rows) return out;
      var filled = [];
      var handoff = [];
      Object.keys(rows).forEach(function (f) {
        var st = ctl.rowState(rows[f].key);
        if (!st.exists || st.value !== rows[f].value) return;
        filled.push(rows[f].key);
        if (rows[f].value === '' && st.sensitive) handoff.push(rows[f].key);
      });
      if (!filled.length) return out;
      out.push({
        field: kind,
        table: true,
        text: 'Filled by GleepGlorp: ' + filled.join(', ') + '.' +
          handoff.map(function (k) { return ' Enter the value for ' + k + '.'; }).join('')
      });
      return out;
    }

    // Draw the notes (idempotent: it removes its own first).
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
      var prep = core.prepare(ctl, view, {
        allowed: ALLOWED,
        dead: dead,
        skip: function (k, isCreate) { return k === 'type' && !isCreate; } // a change never sets the type
      });
      if (!prep) return Promise.resolve({ unavailable: true });
      return Promise.resolve(write_(prep.vals));
    }

    function write_(vals) {
      var start = ctl.values();
      var c = start.connection;
      var b = ctl.baseline().connection;
      if (!record) record = { at: null, values: {} };
      record.at = new Date().toISOString();
      var rv = record.values;
      var w = core.writer(c, b, rv, { onlyIn: vals });
      var keep = w.keep;
      var wrote = w.wrote;
      var operatorScalar = w.operatorScalar;

      // 1. The type, create only. One the operator chose differently is kept, and then none of
      // the fields that belong to the fill's own type are written either.
      var typeKept = false;
      if (has(vals, 'type') && c.type !== vals.type) {
        if (operatorScalar('type')) {
          keep('type');
          typeKept = true;
        } else {
          ctl.setType(vals.type);
          rv.type = vals.type;
          wrote('type');
        }
      }
      if (typeKept) {
        TYPED_KEYS.forEach(keep);
        return w.finish(ctl, redraw);
      }

      // 2. The plain fields.
      ['name', 'url'].forEach(function (k) {
        if (!has(vals, k) || same(c[k], vals[k])) return;
        if (operatorScalar(k)) { keep(k); return; }
        ctl.setField(k, vals[k]);
        rv[k] = vals[k];
        wrote(k);
      });

      // 3. The command and its arguments: one group, through the runtime collapse.
      if (has(vals, 'command') || has(vals, 'args')) {
        var now = ctl.storedCommand();
        var target = {
          command: has(vals, 'command') ? vals.command : now.command,
          args: has(vals, 'args') ? vals.args : now.args
        };
        if (!same(now, target)) {
          var groupDirty = ['runtime', 'command', 'args'].some(function (k) {
            return !same(c[k], b[k]);
          });
          if (groupDirty && !same(now, rv.command)) {
            keep(has(vals, 'command') ? 'command' : 'args');
          } else {
            ctl.setField('command', target);
            rv.command = target;
            wrote('command');
          }
        }
      }

      // 4. The rows, per key.
      ROW_KEYS.forEach(function (rk) {
        if (!has(vals, rk)) return;
        if (ctl.rowKind() !== rk) { keep(rk); return; }
        var recorded = (rv['rows:' + rk] = rv['rows:' + rk] || {});
        var entries = [];
        var anyKept = false;
        Object.keys(vals[rk]).forEach(function (name) {
          var value = vals[rk][name];
          var folded = rk === 'headers' ? name.toLowerCase() : name;
          var st = ctl.rowState(name);
          var rec = recorded[folded];
          if (!st.exists) {
            entries.push({ key: name, value: value });
            recorded[folded] = { key: name, value: value };
            return;
          }
          // Already there with this value (an earlier fill's handoff row, or a row that
          // happens to match): nothing to write.
          if (st.value === value && (value !== '' || st.sensitive)) return;
          // A handoff never replaces a row that is there.
          if (value === '') { anyKept = true; return; }
          var operator = st.masked || (st.dirty && !(rec && rec.value === st.value));
          if (operator) { anyKept = true; return; }
          entries.push({ key: name, value: value });
          recorded[folded] = { key: name, value: value };
        });
        if (entries.length) {
          ctl.setRows(entries);
          wrote(rk);
        }
        if (anyKept) keep(rk);
      });
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

  window.App.studio.mcpEditorFill = {
    create: create,
    attach: mod.attach,
    whenSettled: mod.whenSettled,
    isOpen: mod.isOpen,
    apply: mod.apply,
    ALLOWED: ALLOWED
  };
})();
