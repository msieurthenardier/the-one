// App.studio.knowledgeEditorController -- the handles of one mounted knowledge-base editor (the
// create form or an existing base's edit form), for GleepGlorp's form fill and an approval's
// follow (M36 F5 L3b, flight DD4, DD5, DD9 and DD14).
//
//   var ctl = App.studio.knowledgeEditorController.create(env)
//
// knowledge-create.js and knowledge-detail.js each build one per mount and return it on their
// handle (`controller`); knowledge-glue.js keeps the live one and hands it to the fill and
// follow modules. `env` is the editor's own closure:
//   {isCreate, id, el, shell, nameInput, descInput, nameField, descField, refreshHint(),
//    checkDirty(), isAlive(), saving(), snapshot([next]) (edit only), adopt(row) (edit only)}
//
// The contract is the shared one (areas/shared/gleepglorp-fill-core.js, provider-editor-
// controller.js is the model). Values are keyed by the STORED names (name, description). Every
// setter is silent (no Save, no request); the caller runs checkDirty() once it has written.
//
//   key, isCreate, id, el    'create' | 'edit:{id}', the mode, the stored id, the editor root
//   alive(), ready(), saving(), onIdle(fn), idle()
//   values(), baseline()     the live and the saved values (a create's baseline is empty)
//   setField(key, value)     name | description; what the input handler does (errors, hint)
//   placeNote(key, el)       appends the note under the field; returns its controls or null
//   addFollowNotes(detail, fields), clearNotes(), isDirty(), checkDirty()
//   rebase(row)              an approved change: a clean field takes the stored value, a dirty
//                            one keeps the operator's while its baseline moves (edit only)
//   fill                     the GleepGlorp fill handle (knowledge-editor-fill.js)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var FIELDS = ['name', 'description'];

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function create(env) {
    var dead = false;
    var idleWaiters = [];
    var fillApi = null;
    var controls = { name: env.nameInput, description: env.descInput };
    var fields = { name: env.nameField, description: env.descField };

    function live() { return { name: env.nameInput.value, description: env.descInput.value }; }

    function placeNote(key, note) {
      if (!fields[key]) return null;
      fields[key].el.appendChild(note);
      return [controls[key]];
    }
    var followNotes = App.gleepglorpFollow.fieldNotes(placeNote,
      { testid: 'kb-approved-change-note' });

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
      checkDirty: function () { if (ctl.alive()) env.checkDirty(); },
      isDirty: function () { return !same(live(), ctl.baseline()); },
      values: live,
      baseline: function () {
        return env.isCreate ? { name: '', description: '' } : Object.assign({}, env.snapshot());
      },
      setField: function (key, value) {
        if (!ctl.alive() || !controls[key]) return false;
        controls[key].value = String(value);
        env.afterSet(key);
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
      rebase: function (row) {
        if (!ctl.alive() || env.isCreate || !row) return false;
        var cur = live();
        var base = Object.assign({}, env.snapshot());
        var next = { name: row.name || '', description: row.description || '' };
        FIELDS.forEach(function (k) {
          if (cur[k] === base[k]) controls[k].value = next[k];
          base[k] = next[k];
        });
        env.snapshot(base);
        env.adopt(row);
        env.checkDirty();
        return true;
      },
      destroy: function () {
        dead = true;
        idleWaiters = [];
        if (fillApi) fillApi.destroy();
      }
    };

    fillApi = App.studio.knowledgeEditorFill.create(ctl);
    ctl.fill = fillApi;
    // A note stays only under a control that still holds the value a fill wrote.
    ['input', 'change'].forEach(function (ev) {
      FIELDS.forEach(function (k) {
        controls[k].addEventListener(ev, function () { fillApi.redraw(); });
      });
    });
    return ctl;
  }

  window.App.studio.knowledgeEditorController = { create: create };
})();
