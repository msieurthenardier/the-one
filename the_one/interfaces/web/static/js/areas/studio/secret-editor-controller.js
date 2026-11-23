// App.studio.secretEditorController -- the handles of one mounted secret editor (the create form
// or an existing secret's edit form), for GleepGlorp's form fill and an approval's follow (M36 F5
// L3b, flight DD6, DD9 and DD14).
//
//   var ctl = App.studio.secretEditorController.create(env)
//
// secret-editor.js builds it once per mount and returns it on its handle (`controller`);
// secret-glue.js keeps the live one and hands it to the fill and follow modules. `env` is the
// editor's own closure:
//   {isCreate, id, el, shell, nameInput, descInput, nameField, descField, chips, toolsField, kv,
//    valuesSection, followNameKey(), recompute(), isDirty(), isAlive(), saving(),
//    snapshot([json]), adopt({name, description, allowed_tools})}
//
// Only the METADATA is reachable from here: name, description and allowed tools. The values table
// (keys, masked values, typed values) is never written, rebased or re-read by a fill or a follow,
// except that a fill on a create form lets row 0's key follow the filled name, as typing does.
// Every setter is silent (no Save, no request); each runs the editor's own dirty recompute.
//
//   key, isCreate, id, el    'create' | 'edit:{id}', the mode, the stored id, the editor root
//   alive(), ready(), saving(), onIdle(fn), idle()
//   values(), baseline()     {name, description, allowed_tools}; the baseline is the saved one
//   setField(key, value)     name | description | allowed_tools
//   placeNote(key, el)       appends the note under the field (the chips note sits under the
//                            chips); returns its controls or null
//   placeTableNote(el)       appends the note under the values table; its controls are row 0's
//                            value input (the Add button while there is no row)
//   firstRow()               {key, value} of row 0 or null (the handoff note's input)
//   addFollowNotes(detail, fields), clearNotes(), isDirty(), checkDirty(), changed()
//   rebase(row)              an approved change: a clean field takes the stored value, a dirty
//                            one keeps the operator's while its baseline moves; the values
//                            table is untouched (edit only)
//   fill                     the GleepGlorp fill handle (secret-editor-fill.js)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var FIELDS = ['name', 'description', 'allowed_tools'];

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function create(env) {
    var dead = false;
    var idleWaiters = [];
    var fillApi = null;

    function live() {
      return {
        name: env.nameInput.value,
        description: env.descInput.value,
        allowed_tools: env.chips.values()
      };
    }

    function valueInput() {
      return env.kv.el.querySelector('[data-testid="secret-value-input"]');
    }

    function placeNote(key, note) {
      if (key === 'name') { env.nameField.el.appendChild(note); return [env.nameInput]; }
      if (key === 'description') { env.descField.el.appendChild(note); return [env.descInput]; }
      if (key === 'allowed_tools') { env.toolsField.el.appendChild(note); return [env.chips.input]; }
      return null;
    }
    var followNotes = App.gleepglorpFollow.fieldNotes(placeNote,
      { testid: 'secret-approved-change-note' });

    var ctl = {
      key: env.isCreate ? 'create' : 'edit:' + env.id,
      isCreate: env.isCreate,
      id: env.id,
      el: env.el,
      alive: function () { return !dead && env.isAlive(); },
      ready: function () { return ctl.alive(); },
      saving: function () { return env.saving(); },
      onIdle: function (fn) { if (!env.saving()) fn(); else idleWaiters.push(fn); },
      idle: function () {
        var list = idleWaiters;
        idleWaiters = [];
        list.forEach(function (fn) { fn(); });
      },
      // checkDirty is the editor's own recompute (which also redraws the notes).
      checkDirty: function () { if (ctl.alive()) env.recompute(); },
      // The editor's own change path calls this: the notes follow what the controls hold.
      changed: function () { if (!dead && fillApi) fillApi.redraw(); },
      isDirty: function () { return env.isDirty(); },
      values: live,
      baseline: function () {
        var snap = JSON.parse(env.snapshot());
        return { name: snap.name, description: snap.description, allowed_tools: snap.tools };
      },
      setField: function (key, value) {
        if (!ctl.alive() || FIELDS.indexOf(key) === -1) return false;
        if (key === 'name') {
          env.nameInput.value = String(value);
          env.nameField.setError(null);
          env.followNameKey();
        } else if (key === 'description') {
          env.descInput.value = String(value);
          env.descField.setError(null);
        } else {
          // chips.setValues and kv.setRow fire no onChange: the recompute below is required.
          env.chips.setValues(value);
          env.toolsField.setError(null);
          env.chips.setError(false);
        }
        env.recompute();
        return true;
      },
      placeNote: placeNote,
      placeTableNote: function (note) {
        env.valuesSection.el.appendChild(note);
        var c = valueInput() || env.kv.el.querySelector('[data-testid="secret-add-pair-btn"]');
        return c ? [c] : [];
      },
      firstRow: function () {
        var rows = env.kv.values();
        return rows.length ? { key: rows[0].key, value: rows[0].value } : null;
      },
      valueInput: valueInput,
      addFollowNotes: function (detail, names) {
        followNotes.show(detail, (names || []).filter(function (n) { return FIELDS.indexOf(n) !== -1; }));
      },
      clearNotes: function () {
        if (fillApi) fillApi.clear();
        followNotes.clear();
      },
      rebase: function (row) {
        if (!ctl.alive() || env.isCreate || !row) return false;
        var snap = JSON.parse(env.snapshot());
        var cur = live();
        var next = {
          name: row.name || '', description: row.description || '',
          allowed_tools: row.allowed_tools || []
        };
        if (cur.name === snap.name) env.nameInput.value = next.name;
        if (cur.description === snap.description) env.descInput.value = next.description;
        if (same(cur.allowed_tools, snap.tools)) env.chips.setValues(next.allowed_tools);
        snap.name = next.name;
        snap.description = next.description;
        snap.tools = next.allowed_tools;
        env.snapshot(JSON.stringify(snap));
        env.adopt(next);
        env.recompute();
        return true;
      },
      destroy: function () {
        dead = true;
        idleWaiters = [];
        if (fillApi) fillApi.destroy();
      }
    };

    fillApi = App.studio.secretEditorFill.create(ctl);
    ctl.fill = fillApi;
    return ctl;
  }

  window.App.studio.secretEditorController = { create: create };
})();
