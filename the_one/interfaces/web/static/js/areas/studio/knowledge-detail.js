// App.studio.renderKnowledgeDetail — the Knowledge detail pane (Mission 24
// Flight 6 Leg 1, DD-2, L1-D1; split into modules in Mission 31 Flight 3 Leg
// 02). The create form is knowledge-create.js; the Folders, Status, Search and
// chunks/source sections are knowledge-folders (its file rows are
// knowledge-rows)/-status/-search/-inspect.js, each created here with a ctx. This module keeps the frame, the Name and
// Description fields with their dirty tracking, the danger zone and the
// composition. Built with DOM APIs only (see knowledge-shared.js).
//
// L1-D2: the 5-second status poll is owned by `knowledge-glue.js`, not this
// module: `renderKnowledgeDetail` returns `{updateStatus(status),
// updateItems(items), destroy()}`. `updateStatus` refreshes the status summary and the
// folders list WITHOUT rebuilding the items list, an open chunks/source panel
// or the search form. `updateItems` is called by the glue only when the poll's
// per-status + chunk counts differ from what the list was last rendered against
// (and it never touches the chunks/source panels, so an open panel survives).
//
// L6-D1: Name + Description are ALWAYS-LIVE fields (no edit-button toggle);
// Save/Cancel sit in the header, disabled until the form is dirty. The 5-second
// poll must never re-render these fields mid-keystroke; structurally it cannot,
// because they live in their own section, a subtree `status.update` and the
// folders' `renderFolders`/`renderAllItems` never touch. Save patches the frame
// in place (M31 F3 L05a): the glue no longer remounts after a Save.
//
// `state` is the glue's initial-fetch snapshot `{status, items}`, read only at
// construction; `initialStatus.folders` is shared by reference into the
// folders module's `currentFolders`.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var _el = K.el;

  // ── Detail ────────────────────────────────────────────────────────────
  //
  // Section order (AC-6, Leg 6): header/fields → Folders → Status → Search →
  // Danger Zone.
  //
  // M31 F3 L05a (DD5): the frame is built once per mount from the library
  // (`editorShell`, `field`) and Save patches it in place: nothing remounts, so
  // an expanded folder panel, an open chunks/source panel, search results and the
  // scroll position survive. The value model (`readValues()`/`snapshot`/`stored`)
  // decides dirty, never the DOM. `destroy()` marks the mount dead; every async
  // write checks `alive` (and the glue's `isCurrent` through the callbacks).

  function renderKnowledgeDetail(container, kb, state, callbacks) {
    callbacks = callbacks || {};
    state = state || {};
    var items = state.items || [];
    var initialStatus = state.status || null;
    var alive = true;
    function isLive() { return alive; }

    var root = _el('div', { className: 'knowledge-inventory knowledge-detail' });
    root.setAttribute('data-testid', 'studio-knowledge-inventory');
    container.appendChild(root);

    // The last saved record: Cancel restores from it, never from the DOM.
    var stored = kb;
    var busy = false;

    // ── Header (AC-1, L6-D1): the breadcrumb, the title/subtitle (last-saved
    // values, patched in place on Save), the unsaved caption, Cancel and Save.
    // No edit button. M25 F3 L4b retired Back (DD2): the breadcrumb's "Library"
    // link closes the item to the Library root, through the router's leave guard.
    var shell = App.ui.editorShell({
      breadcrumb: {
        label: 'Library',
        href: App.router.href({ destination: 'library' }),
        trail: ' / Knowledge bases'
      },
      title: kb.name,
      subtitle: kb.description || '',
      errorRole: 'alert',
      actions: {
        cancel: { testid: 'cancel-knowledge-btn', onClick: cancel },
        save: { testid: 'save-knowledge-btn', onClick: save }
      }
    });
    root.appendChild(shell.el);

    // ── Fields (AC-2, L6-D1) — Name + Description, ALWAYS live, no wrapping
    // edit form. Reuses the create form's 43-code-point advisory hint and
    // empty-name refusal.
    var nameInput = App.ui.textInput({
      id: 'kb-name',
      value: kb.name,
      placeholder: 'Knowledge base name',
      testid: 'kb-name-input',
      dataset: { field: 'name' },
      onInput: function () {
        refreshHint();
        shell.setError('');
        onValuesChanged();
      }
    });
    var nameField = App.ui.field({
      label: 'Name',
      control: nameInput,
      hintTestid: 'kb-name-hint'
    });
    function refreshHint() {
      nameField.setHint(Array.from(nameInput.value).length > 43
        ? 'Names over 43 characters get a shortened, hashed tool name.' : null);
    }
    refreshHint();

    var descInput = App.ui.textarea({
      id: 'kb-description',
      value: kb.description || '',
      rows: 3,
      placeholder: 'Optional description',
      testid: 'kb-description-input',
      dataset: { field: 'description' },
      onInput: function () {
        shell.setError('');
        onValuesChanged();
      }
    });
    var descField = App.ui.field({ label: 'Description', control: descInput });
    root.appendChild(App.ui.section({ children: [nameField.el, descField.el] }).el);

    // AC-3/AC-4 — dirty tracking from a value model: Save/Cancel stay disabled
    // until the values differ from the last saved snapshot; Cancel restores from
    // `stored`. The unsaved caption follows the same value through the shell.
    function readValues() {
      return { name: nameInput.value, description: descInput.value };
    }
    var snapshot = readValues();
    function isDirty() {
      var v = readValues();
      return v.name !== snapshot.name || v.description !== snapshot.description;
    }
    function onValuesChanged() {
      var d = isDirty();
      shell.setDirty(d);
      if (alive && callbacks.onDirtyChange) callbacks.onDirtyChange(d);
    }
    function setInputsDisabled(value) {
      nameInput.disabled = value;
      descInput.disabled = value;
    }

    // Focus after an in-place action (M25 F6 L1b, DD2): Save and Cancel disable
    // themselves, so a keyboard user's focus goes to the title.
    function cancel() {
      if (!alive || busy) return;
      var focusTok = App.focusAfter.begin(shell.cancelButton);
      nameInput.value = stored.name;
      descInput.value = stored.description || '';
      refreshHint();
      shell.setError('');
      onValuesChanged();
      App.focusAfter.restore(focusTok, shell.titleEl);
    }

    function save() {
      if (!alive || busy) return;
      shell.setError('');
      // AC-7 (Leg 6, carried from L5-D2): an empty name is refused
      // client-side — no request sent — exactly as the create form's
      // empty-name refusal.
      var newName = nameInput.value.trim();
      if (!newName) {
        shell.setError('Name is required.');
        return;
      }
      var saveTok = App.focusAfter.begin(shell.saveButton);
      busy = true;
      shell.setBusy(true);
      setInputsDisabled(true);
      App.api.fetchJson('/api/knowledge-bases/' + encodeURIComponent(kb.id), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName, description: descInput.value })
      }).then(function (updated) {
        // A KB rename rewrites agents' kb_ids / KB tool references (DD8), and
        // the Library list shows the name (DD9): the collections are stale
        // whatever became of this mount.
        App.store.invalidate('knowledge-bases');
        App.store.invalidate('agents');
        if (!alive) return;
        // L05a: patch in place (no remount). The fields are written from the
        // saved record (the trimmed name), the snapshot is retaken and dirty
        // recomputed, then the inputs come back.
        busy = false;
        stored = updated;
        shell.setTitle(updated.name);
        shell.setSubtitle(updated.description || '');
        nameInput.value = updated.name;
        descInput.value = updated.description || '';
        refreshHint();
        snapshot = readValues();
        setInputsDisabled(false);
        shell.setBusy(false);
        onValuesChanged();
        if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated);
        App.focusAfter.restore(saveTok, shell.titleEl);
      }, function (err) {
        if (!alive) return;
        busy = false;
        setInputsDisabled(false);
        shell.setBusy(false);
        shell.setError((err && err.message) || String(err));
        App.focusAfter.restore(saveTok, shell.saveButton);
      });
    }


    // ── Composition. DOM order is today's: header, fields, Folders, Status,
    // Search, Danger Zone (each section appends to `root` when created). The
    // inspect panels are created first but appended nothing until after the
    // Folders section. Cross-module calls are lazy wrappers over handles that
    // exist by the time any event or promise can reach them.
    //
    // M31 F3 HAT: a panel opens with its opener (the row's menu trigger); its
    // close hands focus back through the folders module, which knows the rows
    // and panels; and after every items render the folders module reports the
    // live ids, so an open panel whose item is gone closes.
    var folders = null;
    var inspect = window.App.studio.knowledgeInspect.create({
      kb: kb,
      onClose: function (item, opener) {
        if (alive && folders) folders.focusAfterInspect(item, opener);
      }
    });
    folders = window.App.studio.knowledgeFolders.create({
      kb: kb,
      root: root,
      container: container,
      initialStatus: initialStatus,
      openChunks: function (item, opener) { return inspect.openChunks(item, opener); },
      openSource: function (item, opener) { return inspect.openSource(item, opener); },
      refreshStatus: function () { return refreshStatusNow(); },
      refreshItems: function () { return refreshItemsListNow(); },
      onItemsRendered: function (liveIds) { if (alive) inspect.closeUnless(liveIds); },
      isLive: isLive,
      isCurrent: isLive,
      // A folder or file action's failure goes to the editor header (M31 F3
      // L06a, DD6).
      setError: function (text) { if (alive) shell.setError(text || ''); }
    });
    folders.renderAllItems(items);
    folders.foldersSection.appendChild(inspect.chunksPanel);
    folders.foldersSection.appendChild(inspect.sourcePanel);

    var status = window.App.studio.knowledgeStatus.create({
      kb: kb,
      root: root,
      initialStatus: initialStatus,
      refreshStatus: function () { return refreshStatusNow(); },
      isLive: isLive
    });
    var search = window.App.studio.knowledgeSearch.create({ kb: kb, root: root, isLive: isLive });

    function refreshStatusNow() {
      if (!alive) return;
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/status')
        .then(function (r) {
          if (!r.ok) throw new Error('status fetch failed: HTTP ' + r.status);
          return r.json();
        })
        .then(function (fresh) {
          if (!alive) return;
          status.update(fresh);
          folders.renderFolders((fresh && fresh.folders) || []);
        })
        .catch(function () {
          // L1-D2: a failed refresh leaves the last-rendered state.
        });
    }

    function refreshItemsListNow() {
      if (!alive) return;
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items')
        .then(function (r) {
          if (!r.ok) throw new Error('items fetch failed: HTTP ' + r.status);
          return r.json();
        })
        .then(function (freshItems) { if (alive) folders.renderAllItems(freshItems); })
        .catch(function () {
          // Leave last-rendered state; the operator can retry.
        });
    }

    // ── Danger Zone (AC-12), on the library since M31 F3 L05b. One DELETE: the
    // `deleting` flag short-circuits every later confirm and the button is
    // disabled until the request settles. A failure shows its reason in the
    // zone's own notice (next to the button, where the operator is looking) and
    // reverts the arm.
    var deleting = false;
    var danger = App.ui.dangerZone({
      notice: { testid: 'kb-delete-error' },
      actions: [{
        label: 'Delete Knowledge Base',
        testid: 'delete-knowledge-base-btn',
        icon: 'trash',
        onConfirm: function (revert) {
          if (deleting) return;
          deleting = true;
          danger.setDisabled(true);
          danger.setNotice(null);
          App.api.fetchJson(
            '/api/knowledge-bases/' + encodeURIComponent(kb.id), { method: 'DELETE' })
            .then(function () {
              App.store.invalidate('knowledge-bases');
              App.store.invalidate('agents');
              if (alive && callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
            })
            .catch(function (err) {
              deleting = false;
              if (!alive) return;
              revert();
              danger.setDisabled(false);
              danger.setNotice((err && err.message) || 'Delete failed');
            });
        }
      }]
    });
    root.appendChild(danger.el);

    return {
      updateStatus: function (s) {
        if (!alive) return;
        status.update(s);
        folders.renderFolders((s && s.folders) || []);
      },
      updateItems: function (list) {
        if (alive) folders.renderAllItems(list);
      },
      // The mount is dead: late responses (Save, search, panels, the poll's
      // calls) do nothing, and a parked focus restore is dropped.
      destroy: function () {
        alive = false;
        App.focusAfter.cancel();
        search.destroy();
        status.destroy();
        folders.destroy();
        inspect.destroy();
      }
    };
  }


  window.App.studio.renderKnowledgeDetail = renderKnowledgeDetail;
})();
