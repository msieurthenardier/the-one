// App.studio.secretGlue -- the Library "Secrets" group's section glue (sortie 10, DD1): the
// connector glue's shape (routing, pending id, store reload) for the secret editor
// (secret-editor.js). A factory it calls once in init, after the connector glue (it registers
// its kind with the one pending-item rule that lives there):
//
//   var secrets = App.studio.secretGlue.create(ctx);
//
// ctx (studio -> module): self, state, pane (the libraryPane handle), connectors (the
// connectorGlue handle), setActiveSection, discardOpen, sectionContent(), agentData.
//
// handle (module -> studio): render(), tryConsumePending(allowCache) -> bool, reset() (close
// the open form; discards the still-mounted editor's edits first), isOpen().
//
// The editor is mounted once and kept by an identity key ('add' or 'edit:' + id), so a same-key
// render (a store notification, a pending consume) keeps its unsaved edits; a different key
// destroys the old handle first. `epoch` is bumped by every teardown.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var pane = ctx.pane;
    var sectionContentEl = ctx.sectionContent();
    var discardOpen_ = ctx.discardOpen;
    var setActiveSection = ctx.setActiveSection;
    var reloadLibrary = pane.reload;
    var syncLibrarySelection = pane.sync;
    var libraryRowIndex = pane.rowIndex;
    var focusLibraryRowNear = pane.focusNear;
    var focusLibraryGroupStart = pane.focusGroupStart;
    var renderLibraryEmpty = pane.renderEmpty;

    var handle = null;
    var handleKey = null;
    var handleGen = null; // state.editorGen when the live editor mounted
    var epoch = 0;
    // The live editor's GleepGlorp controller, or null (none mounted, or torn down).
    var current = null;

    // The area seams studio-route.js reads (serialize) and writes (hydrate), exposed on the
    // area object like the other Library groups' (studio.js keeps the state itself).
    [['_secretFormMode', 'secretFormMode'], ['_editingSecret', 'editingSecret'],
      ['_pendingSecretId', 'pendingSecretId'], ['_pendingSecretFormMode', 'pendingSecretFormMode']
    ].forEach(function (pair) {
      Object.defineProperty(self, pair[0], {
        get: function () { return state[pair[1]]; },
        set: function (v) { state[pair[1]] = v; },
        configurable: true
      });
    });
    // The lifetime subscription (the connectors twin): feeds the cache, re-attempts a pending
    // consume, and renders the list while the pane exists.
    App.store.subscribe('secrets', function (list) {
      state.secrets = list;
      if (self._activeSection === 'secrets' && state.pendingSecretFormMode === 'edit') {
        tryConsumePendingSecret(true);
      }
      pane.render();
    });

    function formKey() {
      if (state.secretFormMode === 'add') return 'add';
      if (state.secretFormMode === 'edit' && state.editingSecret) return 'edit:' + state.editingSecret.id;
      return null;
    }

    function destroyHandle() {
      var old = handle;
      handle = null;
      handleKey = null;
      current = null;
      if (old && old.destroy) old.destroy();
    }

    function teardown() {
      epoch += 1;
      // The leave guard's Continue reaches here through discardOpen_ -> closeOpenItem:
      // reset the still-mounted editor to its baseline, then drop it.
      if (handle && handle.discard) handle.discard();
      destroyHandle();
    }

    function renderSecretsSection() {
      if (!state.secretFormMode && state.pendingSecretFormMode === 'add') {
        state.secretFormMode = 'add';
        state.editingSecret = null;
        state.pendingSecretFormMode = null;
        state.pendingSecretId = null;
      }
      if (state.secretFormMode) {
        var key = formKey();
        if (handle && key !== null && key === handleKey) {
          syncLibrarySelection(false); // same editor: its unsaved edits survive
          return;
        }
        destroyHandle();
        sectionContentEl.replaceChildren();
        state.dirty = false;
        var secGen = state.editorGen;
        handleKey = key;
        handle = App.studio.renderSecretEditor(sectionContentEl, state.editingSecret, {
          // Create closes by discarding and replacing to the Library root; edit mode reverts in
          // place inside the editor.
          onCancel: function () {
            discardOpen_();
            App.router.go(App.router.href({ destination: 'library' }),
              { replace: true, bypassGuard: true });
            focusLibraryGroupStart('secrets');
          },
          // A create re-renders in edit mode from the saved row and the URL moves from ~new to
          // the item through sync(); an edit Save is patched in place by the editor.
          onSaveSuccess: function (updated, isCreate) {
            if (secGen !== state.editorGen) return; // discarded mid-save: no resurrection
            state.editingSecret = updated;
            state.secretFormMode = 'edit';
            reloadLibrary('secrets');
            state.dirty = false;
            if (window.App && window.App.router) {
              App.router.sync('studio', 'secrets/' + encodeURIComponent(updated.id),
                { name: updated.name });
            }
            syncLibrarySelection(true);
            if (isCreate) renderSecretsSection();
          },
          onDeleteSuccess: function () {
            var rowIndex = libraryRowIndex('secret:' + (state.editingSecret ? state.editingSecret.id : ''));
            discardOpen_();
            App.router.go(App.router.href({ destination: 'library' }),
              { replace: true, bypassGuard: true });
            reloadLibrary('secrets').then(function () { focusLibraryRowNear(rowIndex); });
            // The grants were stripped server-side: the row counts follow.
            App.store.get('agents').then(function () {}, function () {});
          },
          onDirtyChange: function (d) { if (secGen === state.editorGen) state.dirty = d; }
        });
        handleGen = secGen;
        current = handle ? handle.controller : null;
        App.focusAfter.flush();
        syncLibrarySelection(false);
        return;
      }
      teardown();
      sectionContentEl.replaceChildren();
      if (state.pendingSecretFormMode === 'edit' && state.pendingSecretId) {
        syncLibrarySelection(false);
        return;
      }
      renderLibraryEmpty();
      syncLibrarySelection(false);
    }

    // GleepGlorp's fill and an approval's follow (secret-editor-fill.js, -follow.js) reach the
    // live editor through this accessor. A follow is NOT a Save: followed(row) leaves the form
    // mode, the dirty mirror and the mount alone (onSaveSuccess clears `dirty` and re-mounts a
    // create), and only moves what an approval changed: the cached row, the list, the router's
    // name and the Library selection.
    App.studio.secretEditorFill.attach(function () { return current; });
    App.studio.secretEditorFollow.attach({
      getController: function () { return current; },
      followed: function (row) {
        if (handleGen !== state.editorGen) return; // discarded meanwhile: no resurrection
        state.editingSecret = row;
        reloadLibrary('secrets');
        if (window.App && window.App.router) {
          App.router.sync('studio', 'secrets/' + encodeURIComponent(row.id), { name: row.name });
        }
        syncLibrarySelection(true);
      }
    });

    function findSecret(id) {
      if (!state.secrets) return null;
      for (var i = 0; i < state.secrets.length; i++) {
        if (state.secrets[i].id === id) return state.secrets[i];
      }
      return null;
    }

    self._closeSecretForm = function () {
      teardown();
      state.secretFormMode = null;
      state.editingSecret = null;
      state.dirty = false;
    };

    function tryConsumePendingSecret(allowCache) {
      var pid = state.pendingSecretId;
      var pmode = state.pendingSecretFormMode;
      if (!pid && !pmode) return false;
      if (pmode === 'add') {
        state.secretFormMode = 'add';
        state.editingSecret = null;
        state.pendingSecretId = null;
        state.pendingSecretFormMode = null;
        renderSecretsSection();
        return true;
      }
      if (pmode === 'edit' && pid && allowCache !== false) {
        var found = findSecret(pid);
        if (found) {
          state.secretFormMode = 'edit';
          state.editingSecret = found;
          state.pendingSecretId = null;
          state.pendingSecretFormMode = null;
          renderSecretsSection();
          return true;
        }
      }
      return false;
    }
    self._tryConsumePendingSecret = tryConsumePendingSecret;

    // Join the one pending-item rule (connector-glue.js).
    ctx.connectors.registerPending('secrets', {
      collection: 'secrets',
      mode: function () { return state.pendingSecretFormMode; },
      id: function () { return state.pendingSecretId; },
      consume: tryConsumePendingSecret,
      heal: function () {
        state.pendingSecretId = null;
        state.pendingSecretFormMode = null;
        setActiveSection('library');
      }
    });

    return {
      render: renderSecretsSection,
      tryConsumePending: tryConsumePendingSecret,
      reset: function () {
        teardown();
        state.secretFormMode = null;
        state.editingSecret = null;
      },
      isOpen: function () { return !!state.secretFormMode; }
    };
  }

  window.App.studio.secretGlue = { create: create };
})();
