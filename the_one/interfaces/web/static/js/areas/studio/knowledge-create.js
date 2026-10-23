// App.studio.renderKnowledgeCreate — the Knowledge create form
// (Mission 24 Flight 6 Leg 1; split out of knowledge-section.js in
// Mission 31 Flight 3 Leg 02). Built entirely with DOM APIs through the
// helpers in knowledge-shared.js.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var _el = K.el;

  // ── Create form (M25 F3 L4a, DD8; closes squawk 0101; library frame M31 F3 L05a)
  //
  // `#library/knowledge/~new`: the create form in the detail pane, beside the
  // Library list. Its header is `App.ui.editorShell` (the breadcrumb "Library /
  // Knowledge bases", the pane's only `h1` "New knowledge base", the unsaved
  // caption, Cancel and Create, both enabled on a clean form); the fields are
  // `App.ui.field`s. The M24 contract is kept: an empty name shows "Name is
  // required." with no request, and the 43-code-point hint (DD-16).
  // The empty-name error is a field error on Name (`kb-create-name-error`,
  // aria-invalid on the input, focus moved to it; cleared when the name is
  // edited and on the next submit). `kb-create-error` under Description shows
  // only server and network failures (an operator-approved exception to
  // flight DD6, "kb-create-error stays the one error surface", made at the
  // M31 F3 HAT).
  //
  // callbacks: {onDirtyChange(bool), onCancel(), onCreateSuccess(kb)}.
  // Returns {focus(), destroy()}. Create keeps the shell busy from submit until
  // the request fails (a second click during the await would POST a duplicate);
  // on success the form is about to go, so it stays busy. The module
  // invalidates 'knowledge-bases' (DD9) before onCreateSuccess, which owns the
  // navigation (studio.js). After destroy() nothing is reported or written.
  function renderKnowledgeCreate(container, callbacks) {
    callbacks = callbacks || {};
    var alive = true;

    var root = _el('div', { className: 'knowledge-inventory knowledge-create' });
    container.appendChild(root);

    var shell = App.ui.editorShell({
      breadcrumb: {
        label: 'Library',
        href: App.router.href({ destination: 'library' }),
        trail: ' / Knowledge bases'
      },
      title: 'New knowledge base',
      actions: {
        cancel: {
          testid: 'kb-create-cancel-btn',
          enabledWhenClean: true,
          onClick: function () {
            if (alive && callbacks.onCancel) callbacks.onCancel();
          }
        },
        save: {
          label: 'Create',
          testid: 'kb-create-submit-btn',
          enabledWhenClean: true,
          onClick: submit
        }
      }
    });
    root.appendChild(shell.el);

    var nameInput = App.ui.textInput({
      id: 'kb-create-name',
      placeholder: 'Knowledge base name',
      testid: 'kb-create-name-input',
      dataset: { field: 'name' },
      onInput: function () {
        nameField.setError(null);
        refreshHint();
        reportDirty();
      }
    });
    // DD-16: advisory only — 43 CODE POINTS ([...name].length), never
    // name.length (UTF-16 units), or an astral character would count
    // double in the browser and single on the server.
    var nameField = App.ui.field({
      label: 'Name',
      control: nameInput,
      hintTestid: 'kb-create-name-hint',
      errorTestid: 'kb-create-name-error'
    });
    function refreshHint() {
      nameField.setHint(Array.from(nameInput.value).length > 43
        ? 'Names over 43 characters get a shortened, hashed tool name.' : null);
    }

    // AC-4 (M24 F06 L05): the create form also accepts a description —
    // no length rule, nothing derives from it (L5-D2).
    var descInput = App.ui.textarea({
      id: 'kb-create-description',
      rows: 3,
      placeholder: 'Optional description',
      testid: 'kb-create-description-input',
      dataset: { field: 'description' },
      onInput: function () { reportDirty(); }
    });
    var descField = App.ui.field({ label: 'Description', control: descInput });

    // kb-studio-round-trip remediation FIX 3: a block-level line carries a
    // server or network create error (a library status line, text tone, no
    // LED; empty until such an error). The empty-name error is Name's own.
    var errorLine = App.ui.status({
      state: 'danger', led: false, role: 'alert', textTone: true, testid: 'kb-create-error'
    });
    errorLine.set('danger', '');

    var fields = App.ui.section({ children: [nameField.el, descField.el, errorLine.el] });
    root.appendChild(fields.el);

    // Dirty while either field holds anything (the form starts empty); the
    // unsaved caption follows the same value through the shell.
    var wasDirty = false;
    function reportDirty() {
      var d = nameInput.value !== '' || descInput.value !== '';
      if (d === wasDirty) return;
      wasDirty = d;
      shell.setDirty(d);
      if (alive && callbacks.onDirtyChange) callbacks.onDirtyChange(d);
    }

    function submit() {
      if (!alive) return;
      errorLine.set('danger', '');
      nameField.setError(null);
      // AC-2: an empty name is refused client-side — no request sent.
      var name = nameInput.value.trim();
      if (!name) {
        nameField.setError('Name is required.');
        nameInput.focus();
        return;
      }
      shell.setBusy(true);
      App.api.fetchJson('/api/knowledge-bases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, description: descInput.value })
      }).then(function (kb) {
        // The row exists whatever became of the form: the list always learns of it.
        App.store.invalidate('knowledge-bases'); // the Library list gains a row (DD9)
        if (!alive) return;
        // Saved: the caption clears while studio awaits the list reload before
        // opening the new item (studio clears its own `dirty`). The shell stays
        // busy: the form is about to be replaced.
        wasDirty = false;
        shell.setDirty(false);
        shell.setBusy(true);
        if (callbacks.onCreateSuccess) callbacks.onCreateSuccess(kb);
      }).catch(function (err) {
        if (!alive) return;
        shell.setBusy(false);
        errorLine.set('danger', (err && err.message) || String(err));
      });
    }

    return {
      focus: function () { nameInput.focus(); },
      destroy: function () { alive = false; }
    };
  }


  window.App.studio.renderKnowledgeCreate = renderKnowledgeCreate;
})();
