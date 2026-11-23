// App.studio.renderSecretEditor -- the Library "Secrets" editor (sortie 10, DD1/DD3).
// Secrets are rows of the Library list (library-pane.js) and routed
// (`#library/secrets/~new|{id}`); this editor is mounted by secret-glue.js.
//
//   renderSecretEditor(container, secret, callbacks) -> {destroy, discard, setBusy, setError}
//
// callbacks: { onCancel, onSaveSuccess(updated, isCreate), onDeleteSuccess, onDirtyChange(dirty) }
//
// Built from App.ui library controls on the connector editor's shape (editorShell with the
// breadcrumb "Library / Secrets", section, field with textInput / chipList, keyValueTable,
// dangerZone) and matching the approved mockup (sorties/10-secrets/mockup/). The value model
// is readValues(): dirty is JSON.stringify(readValues()) !== snapshot, so typing a change and
// reverting it is clean.
//
// Secret handling: a stored value is never in the page. The server sends the constant sentinel
// `__MASKED__` for every value; each row is {id, key, value: '__MASKED__', _stored:
// '__MASKED__'} (the table's `storedKey` mode: masked, the eye disabled until the operator
// types). An untouched stored row is sent back as the sentinel with its id (the server keeps
// the ciphertext); a renamed key clears the value (the table's own rule), so the operator must
// type it again. A typed value lives only in the input's .value: no attribute, title, aria-*
// or text node ever holds it.
//
// Errors: a 422 detail list is mapped by `loc` (["name"], ["description"], ["values", i,
// "key"|"value"], ["values"], ["allowed_tools"], ["allowed_tools", i]); a 409 lands on Name;
// anything else goes through editorShell.setError. The empty-allowed-tools sentence is the
// server's own message (no client pre-check).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var MASK = '__MASKED__';
  var slot = window.App.ui.util.mountSlot();

  // The first key follows the name: lowercase, runs of other characters to `_`, trimmed.
  function slug(name) {
    return String(name || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  }

  function rowsFrom(secret) {
    if (!secret) return [{ key: '', value: '', _stored: '' }];
    return (secret.values || []).map(function (v) {
      return { id: v.id, key: v.key, value: MASK, _stored: MASK };
    });
  }

  function renderSecretEditor(container, secret, callbacks) {
    callbacks = callbacks || {};
    var util = window.App.ui.util;
    var isCreate = !secret;
    var stored = secret || { name: '', description: '', allowed_tools: [], values: [] };
    var h = { shell: null };
    var destroyed = false;
    var tok = slot.mount(function () { destroyed = true; }, h);
    var snapshot = '';
    var saving = false;
    var ctl = null; // the GleepGlorp handles (secret-editor-controller.js), built after the mount

    function current() { return !destroyed && slot.isCurrent(tok); }

    function recomputeDirty() {
      if (!h.shell) return;
      var d = JSON.stringify(readValues()) !== snapshot;
      h.shell.setDirty(d);
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(d);
      if (ctl) ctl.changed(); // the fill's notes follow what the controls now hold
    }

    // A new secret's first key follows the name (until the key is typed by hand). Typing and
    // GleepGlorp's fill (controller.setField('name')) share this one rule.
    function followNameKey() {
      if (isCreate && !keyTouched && kv) {
        var rows = kv.values();
        if (rows.length) kv.setRow(0, { key: slug(nameInput.value) });
      }
    }

    // ── Secret section ────────────────────────────────────────────────
    var nameInput = App.ui.textInput({
      id: 'secret-name', value: stored.name || '', placeholder: 'Home address',
      testid: 'secret-name', dataset: { field: 'name' }, onInput: function () {
        nameField.setError(null);
        followNameKey();
        recomputeDirty();
      }
    });
    var nameField = App.ui.field({ label: 'Name', control: nameInput, errorTestid: 'secret-name-error' });
    var descInput = App.ui.textInput({
      id: 'secret-description', value: stored.description || '',
      placeholder: 'What it is and when to use it', testid: 'secret-description',
      onInput: function () { descField.setError(null); recomputeDirty(); }
    });
    var descField = App.ui.field({
      label: 'Description', control: descInput, errorTestid: 'secret-description-error',
      hint: 'Agents see the name, description and keys, never the values.'
    });
    var main = App.ui.section({ title: 'Secret', children: [nameField.el, descField.el] });

    // ── Values ────────────────────────────────────────────────────────
    var keyTouched = !isCreate;
    var kv = App.ui.keyValueTable({
      label: 'Values', testid: 'secret-kv-table', addTestid: 'secret-add-pair-btn',
      addLabel: '+ Add pair', keyColumn: 'key',
      columns: [
        { key: 'key', label: 'Key', placeholder: 'key_name', mono: true, inputTestid: 'secret-key-input' },
        { key: 'value', label: 'Value', placeholder: 'value', type: 'secret', storedKey: '_stored',
          inputTestid: 'secret-value-input' }
      ],
      rows: rowsFrom(secret),
      rowTestid: 'secret-kv-row',
      removeTestid: 'secret-kv-remove-btn',
      removeLabel: function (n, row) { return row.key ? 'Remove ' + row.key : 'Remove pair ' + n; },
      onChange: function () {
        valuesError.set('');
        recomputeDirty();
      }
    });
    // Editing the key by hand ends the follow-the-name rule (programmatic setRow fires no input).
    kv.el.addEventListener('input', function (e) {
      if (e.target && e.target.getAttribute && e.target.getAttribute('data-testid') === 'secret-key-input') {
        keyTouched = true;
      }
    });
    var valuesError = App.ui.banner({ tone: 'error', live: 'alert', testid: 'secret-values-error' });
    var values = App.ui.section({
      title: 'Values', layout: 'stack', children: [kv.el, valuesError.el],
      description: 'Agents use each key as {{secret:key}} in a tool call; the value is filled in ' +
        'when the tool runs. Values are stored encrypted and never shown again, and are hidden ' +
        'wherever they appear in a tool’s output.'
    });

    // ── Allowed tools: chips with search-ahead over GET /api/tool-names ─
    var toolCatalogue = [];
    var TOOLS_HINT = 'Only these tools can receive this secret’s values. ' +
      'Type to search built-in and MCP tools.';
    var chips = App.ui.chipList({
      label: 'Allowed tools', values: stored.allowed_tools || [], placeholder: 'Search tools…',
      inputId: 'secret-allowed-tools', testid: 'secret-allowed-tools', suggestLabel: 'Tool suggestions',
      suggest: function (term) {
        var t = String(term).toLowerCase();
        return toolCatalogue.filter(function (c) { return c.value.toLowerCase().indexOf(t) >= 0; });
      },
      onChange: function () {
        toolsField.setError(null);
        chips.setError(false);
        recomputeDirty();
      }
    });
    var toolsField = App.ui.field({
      label: 'Allowed tools', control: chips.input, host: chips.el, hint: TOOLS_HINT,
      hintTestid: 'secret-tools-hint', errorTestid: 'secret-tools-error'
    });
    var toolsSec = App.ui.section({
      title: 'Allowed tools', layout: 'stack', children: [toolsField.el],
      description: 'If an agent puts this secret in any other tool, the call is refused with an ' +
        'error that names the key, never its value.'
    });
    // Fetched once per mount. A failure leaves free text working and says so.
    App.api.fetchJson('/api/tool-names').then(function (list) {
      if (!current()) return;
      toolCatalogue = (Array.isArray(list) ? list : []).map(function (t) {
        return { value: t.name, label: t.name, detail: t.source === 'mcp' ? (t.source_name || 'MCP') : 'Built-in' };
      });
      // Typed before the catalogue arrived: refresh the open suggestions.
      if (document.activeElement === chips.input && chips.input.value.trim()) chips.input.dispatchEvent(new Event('input', { bubbles: true }));
    }).catch(function () {
      if (!current()) return;
      toolsField.setHint(TOOLS_HINT + ' Suggestions are unavailable right now; you can still type tool names.');
    });

    // ── The value model ───────────────────────────────────────────────
    function readValues() {
      return {
        name: nameInput.value,
        description: descInput.value,
        rows: kv.values().map(function (r) {
          return { id: r.id || null, key: r.key, value: r.value };
        }),
        tools: chips.values()
      };
    }

    // The request body. A stored row's untouched value is the sentinel; a typed or new value
    // goes as typed. The payload is local to the click, so no variable outlives the request.
    function buildPayload(v) {
      return {
        name: v.name.trim(),
        description: v.description.trim(),
        values: v.rows.map(function (r) {
          var out = { key: r.key.trim(), value: r.value };
          if (r.id) out.id = r.id;
          return out;
        }),
        allowed_tools: v.tools
      };
    }

    function clearErrors() {
      nameField.setError(null);
      descField.setError(null);
      toolsField.setError(null);
      chips.setError(false);
      valuesError.set('');
      var n = kv.values().length;
      for (var i = 0; i < n; i++) { kv.setError(i, 'key', null); kv.setError(i, 'value', null); }
      h.shell.setError('');
    }

    // Used by: the agents that hold a grant, from the shared agents collection.
    var usedBody = util.el('p', { className: 'admin-pf-models-help', 'data-testid': 'secret-used-by' });
    var usedNames = [];
    function paintUsedBy(names) {
      usedNames = names;
      usedBody.replaceChildren();
      if (!names.length) {
        usedBody.appendChild(document.createTextNode(
          'No agent uses this secret yet. Grant it in an agent’s Tools tab.'));
        return;
      }
      usedBody.appendChild(document.createTextNode('Granted to '));
      names.forEach(function (name, i) {
        if (i) usedBody.appendChild(document.createTextNode(', '));
        usedBody.appendChild(util.el('a', {
          href: App.router.href({ destination: 'agents', id: name, tab: 'tools' }),
          text: name, 'data-testid': 'secret-used-by-link'
        }));
      });
      usedBody.appendChild(document.createTextNode('. Grant or remove it in each agent’s Tools tab.'));
    }

    // ── Sections ──────────────────────────────────────────────────────
    var frag = document.createDocumentFragment();
    h.shell = App.ui.editorShell({
      breadcrumb: {
        label: 'Library',
        href: window.App.router.href({ destination: 'library' }),
        trail: ' / Secrets'
      },
      title: isCreate ? 'New secret' : (stored.name || ''),
      errorRole: 'alert',
      actions: {
        cancel: { testid: 'cancel-secret-btn', enabledWhenClean: isCreate, onClick: onCancelClick },
        save: { label: isCreate ? 'Create' : 'Save', testid: 'save-secret-btn', onClick: performSave }
      }
    });
    var shell = h.shell;
    frag.appendChild(shell.el);
    frag.appendChild(main.el);
    frag.appendChild(values.el);
    frag.appendChild(toolsSec.el);

    var danger = null;
    var deleting = false;
    if (!isCreate) {
      paintUsedBy([]);
      frag.appendChild(App.ui.section({ title: 'Used by', children: [usedBody] }).el);
      var dangerAction = {
        label: 'Delete secret', testid: 'delete-secret-btn',
        onConfirm: function (revert) {
          if (deleting) return;
          deleting = true;
          danger.setDisabled(true);
          danger.setNotice(null);
          // DELETE answers 204 with no body, which fetchJson would fail to parse.
          fetch('/api/secrets/' + encodeURIComponent(stored.id), { method: 'DELETE' })
            .then(function (r) {
              if (!r.ok) throw new Error('Delete failed: HTTP ' + r.status);
            }).then(function () {
              // The server strips the id from every agent's secret_ids.
              App.store.invalidate('secrets');
              App.store.invalidate('agents');
              if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
            }).catch(function (err) {
              deleting = false;
              if (!current()) return;
              revert();
              danger.setDisabled(false);
              danger.setNotice(err.message || String(err));
            });
        }
      };
      // Read when the button arms: the count follows the agents collection as it loads.
      Object.defineProperty(dangerAction, 'confirmLabel', {
        enumerable: true,
        get: function () {
          var n = usedNames.length;
          return n ? 'Delete and remove from ' + n + (n === 1 ? ' agent?' : ' agents?')
            : 'Confirm delete?';
        }
      });
      danger = App.ui.dangerZone({ action: dangerAction, notice: { testid: 'secret-delete-error' } });
      frag.appendChild(danger.el);
      App.store.get('agents').then(function (agents) {
        if (!current()) return;
        paintUsedBy(App.usage.secretAgents(agents, stored.id));
      }, function () { /* the sentence stays at its empty wording */ });
    }

    container.replaceChildren(frag);
    snapshot = JSON.stringify(readValues());
    shell.setDirty(false);

    function applyRecord(rec) {
      nameInput.value = rec.name || '';
      descInput.value = rec.description || '';
      kv.setValues(rowsFrom(rec));
      chips.setValues(rec.allowed_tools || []);
    }

    function newMountTitle() {
      var cur = slot.current();
      return cur && cur.data.shell && cur.data.shell.titleEl;
    }

    // Cancel: create closes the editor; edit reverts every control in place.
    function onCancelClick() {
      if (isCreate) {
        if (callbacks.onCancel) callbacks.onCancel();
        return;
      }
      var cancelTok = App.focusAfter.begin(shell.cancelButton);
      revertToBaseline();
      App.focusAfter.restore(cancelTok, shell.titleEl);
    }

    function revertToBaseline() {
      ctl.clearNotes();
      applyRecord(stored);
      snapshot = JSON.stringify(readValues());
      clearErrors();
      shell.setDirty(false);
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
    }

    // The 422 list (or a 409) onto its targets. Returns the sentences that found no target.
    function showServerError(err) {
      var rest = [];
      var detail = err && err.detail;
      if (err && err.status === 409) {
        nameField.setError((typeof detail === 'string' && detail) || err.message || 'That name is already used.');
        return rest;
      }
      if (!Array.isArray(detail)) {
        rest.push((err && err.message) || String(err));
        return rest;
      }
      var tools = chips.values();
      detail.forEach(function (d) {
        var loc = Array.isArray(d && d.loc) ? d.loc.slice() : [];
        if (loc[0] === 'body') loc.shift();
        var msg = App.api.humanizeMessage(d && d.msg);
        if (loc[0] === 'name') nameField.setError(msg);
        else if (loc[0] === 'description') descField.setError(msg);
        else if (loc[0] === 'values' && typeof loc[1] === 'number') {
          kv.setError(loc[1], loc[2] === 'value' ? 'value' : 'key', msg);
        } else if (loc[0] === 'values') {
          valuesError.set(msg);
        } else if (loc[0] === 'allowed_tools' && typeof loc[1] === 'number') {
          toolsField.setError('“' + (tools[loc[1]] || '') + '”: ' + msg);
          chips.setError(true);
        } else if (loc[0] === 'allowed_tools') {
          toolsField.setError(msg);
          chips.setError(true);
        } else rest.push(msg);
      });
      return rest;
    }

    function performSave() {
      clearErrors();
      var payload = buildPayload(readValues());
      var body = JSON.stringify(payload);
      payload = null;
      var saveTok = App.focusAfter.begin(shell.saveButton);
      saving = true;
      shell.setBusy(true);
      var url = isCreate ? '/api/secrets' : '/api/secrets/' + encodeURIComponent(stored.id);
      App.api.fetchJson(url, {
        method: isCreate ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: body
      }).then(function (updated) {
        App.store.invalidate('secrets');
        if (!current()) return;
        App.ui.flash(isCreate ? 'Secret created' : 'Secret saved');
        if (isCreate) {
          // The glue re-mounts in edit mode; the editor stays busy until then.
          App.focusAfter.defer(saveTok, newMountTitle);
          if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, true);
          return;
        }
        // Re-baseline from the response: stored masks again, clean.
        stored = updated;
        applyRecord(stored);
        snapshot = JSON.stringify(readValues());
        shell.setTitle(updated.name || '');
        saving = false;
        shell.setBusy(false);
        shell.setDirty(false);
        ctl.clearNotes();
        if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
        App.focusAfter.restore(saveTok, shell.titleEl);
        if (callbacks.onSaveSuccess) {
          try { callbacks.onSaveSuccess(updated, false); } catch (e) {
            if (window.console && console.error) console.error('onSaveSuccess failed', e);
          }
        }
        ctl.idle();
      }).catch(function (err) {
        if (!current()) return;
        var rest = showServerError(err);
        if (rest.length) shell.setError(rest.join(' '));
        saving = false;
        shell.setBusy(false);
        App.focusAfter.defer(null);
        App.focusAfter.restore(saveTok, shell.saveButton);
        ctl.idle();
      });
    }

    // The GleepGlorp handles (secret-editor-controller.js). Only the metadata (name,
    // description, allowed tools) is ever written or rebased by it: never a value, never a row.
    ctl = App.studio.secretEditorController.create({
      isCreate: isCreate, id: isCreate ? null : stored.id, el: container, shell: shell,
      nameInput: nameInput, descInput: descInput, nameField: nameField, descField: descField,
      chips: chips, toolsField: toolsField, kv: kv, valuesSection: values,
      followNameKey: followNameKey, recompute: recomputeDirty, isDirty: function () {
        return JSON.stringify(readValues()) !== snapshot;
      },
      isAlive: current, saving: function () { return saving; },
      snapshot: function (next) { if (next !== undefined) snapshot = next; return snapshot; },
      adopt: function (meta) {
        stored = Object.assign({}, stored, meta);
        shell.setTitle(meta.name || '');
      }
    });

    return {
      controller: ctl,
      destroy: function () {
        if (slot.isCurrent(tok)) slot.destroy();
        else destroyed = true;
        ctl.destroy();
      },
      // The leave guard's discard (App.nav): reset the STILL-MOUNTED editor to its baseline.
      discard: function () { if (current()) revertToBaseline(); },
      setBusy: function (value) { if (current()) shell.setBusy(value); },
      setError: function (text) { if (current()) shell.setError(text); }
    };
  }

  window.App.studio.renderSecretEditor = renderSecretEditor;
})();
