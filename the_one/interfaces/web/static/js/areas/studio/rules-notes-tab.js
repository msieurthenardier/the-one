// App.studio.renderRulesNotesTab -- the agent editor's "Rules and notes" tab
// (M27 F1 L2, flight DD6). Built with DOM APIs only, on the control library
// (M31 F2 L09: App.ui.section / status / emptyState / confirm).
// Mounted once per agent: it declares no setAgent and is left out of the editor's
// patch (it saves immediately and keys only on the agent's name; a rename is a new
// identity and remounts).
//
// Two sections: Rules (the operator's ordered list of standing instructions for
// the agent, M27 F1) and Notes (M27 F2 L3: a switch, and the agent's own notes
// to review, trace, edit, delete and clear). The panel is built from
// `makeSection(panel, id, title)`; each section is a self-contained builder
// (`buildRulesSection`, `buildNotesSection`) sharing the module helpers below.
//
// Save model (DD6): every control saves IMMEDIATELY through the REST API, then
// re-reads the list and re-renders the LIST only (so the Add textarea keeps its
// focus). Nothing here joins the General form's dirty state or `App.nav`, so the
// leave guard ignores it; unsaved text typed into Add rule or an inline edit is
// lost on navigation without a prompt (accepted, flagged for the HAT).
//
// callbacks: {
//   fetchRules(name)             -> Promise<{rules, limits}>
//   createRule(name, text)       -> Promise<rule>
//   updateRule(name, id, patch)  -> Promise<rule>      patch: {text?, enabled?}
//   deleteRule(name, id)         -> Promise
//   reorderRules(name, ids)      -> Promise<{rules, limits}>
//   fetchNotes(name)             -> Promise<{enabled, notes, limits, usage}>
//   setNotesEnabled(name, bool)  -> Promise
//   deleteNote(name, id)         -> Promise
//   clearNotes(name)             -> Promise<{deleted}>
// }
// Note text can come from an attacker: every note field is written with
// textContent only (never an HTML-string sink).
// `agent` is null in create mode: a "save first" notice and no controls.
//
// Focus: after Add the Add textarea (cleared); after Move the same Move button
// (the other one when it is now at an end); after Delete the neighbouring row's
// Edit button (the Add textarea when the list is empty); after an inline Save or
// Cancel that row's Edit button; after a toggle the row's toggle.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var shared = window.App.studio.rulesNotesShared;
  var APPLIES_NOTE = shared.APPLIES_NOTE;
  var el = shared.el;
  var makeSection = shared.makeSection;
  var buildErrorLine = shared.buildErrorLine;
  var buildLiveLine = shared.buildLiveLine;
  var buildEmpty = shared.buildEmpty;
  var messageOf = shared.messageOf;
  var disableList = shared.disableList;
  var makeMutate = shared.makeMutate;
  var buildInlineEditor = shared.buildInlineEditor;
  var buildDeleteButton = shared.buildDeleteButton;
  var DEFAULT_RULE_CHARS = 500;

  function buildRulesSection(panel, agent, cb) {
    var name = agent.name || '';
    var section = makeSection(panel, 'rules', 'Rules');
    section.setAttribute('data-testid', 'rules-section');
    var rules = [];
    var limits = { rule_chars: DEFAULT_RULE_CHARS };
    var editingId = null;
    var busy = false;
    var gen = 0;

    var appliesNote = el('p', 'rules-applies-note', APPLIES_NOTE);
    appliesNote.setAttribute('data-testid', 'rules-applies-note');
    section.appendChild(appliesNote);

    var errorLine = buildErrorLine();
    errorLine.el.setAttribute('data-testid', 'rules-error');
    section.appendChild(errorLine.el);

    // Polite, visually hidden status line: announces crossing the per-rule limit
    // (the delete arm is announced by App.ui.confirm).
    var liveLine = buildLiveLine();
    liveLine.el.setAttribute('data-testid', 'rules-status');
    section.appendChild(liveLine.el);
    var announce = liveLine.announce;
    var addWasOver = false;

    var listWrap = el('div', 'rules-list-wrap');
    section.appendChild(listWrap);

    // ── Add control ────────────────────────────────────────────────
    var addBox = el('div', 'rules-add');
    var addInput = App.ui.textarea({ rows: 3, testid: 'rules-add-input' });
    var addLabel = el('label', 'rules-add-label', 'Add a rule');
    addLabel.htmlFor = addInput.id;
    var addFoot = el('div', 'rules-add-foot');
    var addCount = el('span', 'rules-add-count');
    addCount.setAttribute('data-testid', 'rules-add-count');
    addCount.id = 'rules-add-count-' + addInput.id;
    addInput.setAttribute('aria-describedby', addCount.id);
    var addBtn = App.ui.button({
      variant: 'primary',
      label: 'Add rule',
      testid: 'rules-add-btn',
      disabled: true,
      onClick: function () { add(); }
    });
    addFoot.appendChild(addCount);
    addFoot.appendChild(addBtn);
    addBox.appendChild(addLabel);
    addBox.appendChild(addInput);
    addBox.appendChild(addFoot);
    section.appendChild(addBox);

    function maxChars() { return limits.rule_chars || DEFAULT_RULE_CHARS; }

    function syncAdd() {
      var n = addInput.value.length;
      var over = n > maxChars();
      addCount.textContent = n + ' / ' + maxChars() + (over ? ' \u2014 over the limit' : '');
      addCount.classList.toggle('rules-add-count--over', over);
      if (over) addInput.setAttribute('aria-invalid', 'true');
      else addInput.removeAttribute('aria-invalid');
      if (over !== addWasOver) {
        addWasOver = over;
        announce(over ? 'Over the ' + maxChars() + ' character limit for a rule.' : '');
      }
      addBtn.disabled = busy || over || !addInput.value.trim();
    }
    addInput.addEventListener('input', syncAdd);

    var showError = errorLine.show;

    function setBusy(on) {
      busy = on;
      listWrap.setAttribute('aria-busy', on ? 'true' : 'false');
      if (on) disableList(listWrap);
      syncAdd();
    }

    // ── Rendering the list ─────────────────────────────────────────
    function ruleLabel(index) { return 'Rule ' + (index + 1); }

    function rowEdit(id) {
      return listWrap.querySelector('[data-testid="rules-row-edit"][data-rule-id="' + id + '"]');
    }

    function buildRow(rule, index) {
      var row = el('li', 'rules-row' + (rule.enabled ? '' : ' rules-row--off'));
      row.setAttribute('data-testid', 'rules-row');
      row.setAttribute('data-id', rule.id);
      row.setAttribute('data-enabled', rule.enabled ? 'true' : 'false');
      var label = ruleLabel(index);

      row.appendChild(el('span', 'rules-row-number', String(index + 1)));

      var body = el('div', 'rules-row-body');
      var actions = el('div', 'rules-row-actions');

      var toggle = App.ui.toggle({
        label: label + ' enabled',
        labelHidden: true,
        checked: rule.enabled,
        testid: 'rules-row-toggle',
        onChange: function (checked) {
          mutate(function () {
            return cb.updateRule(name, rule.id, { enabled: checked });
          }, function () {
            var t = listWrap.querySelector('[data-id="' + rule.id + '"] [data-testid="rules-row-toggle"]');
            if (t) t.focus();
          }, { origin: { kind: 'row', id: rule.id, control: 'rules-row-toggle' } });
        }
      });
      toggle.control.setAttribute('data-rule-id', rule.id);
      row.appendChild(toggle.el);
      toggle.el.classList.add('rules-row-toggle-wrap');

      if (editingId === rule.id) {
        var editor = buildInlineEditor({
          value: rule.text,
          max: maxChars,
          noun: 'rule',
          label: 'Edit ' + label.toLowerCase(),
          idSuffix: 'rules-edit-count-' + rule.id,
          isBusy: function () { return busy; },
          announce: announce,
          onSave: function (text) {
            mutate(function () {
              return cb.updateRule(name, rule.id, { text: text });
            }, function () { focusEdit(rule.id); }, {
              before: function () { editingId = null; },
              keepEditingOnError: true,
              origin: { kind: 'row', id: rule.id, control: 'rules-row-save' }
            });
          },
          onCancel: function () {
            editingId = null;
            showError('');
            renderList();
            focusEdit(rule.id);
          }
        });
        editor.input.setAttribute('data-testid', 'rules-row-edit-input');
        editor.save.setAttribute('data-testid', 'rules-row-save');
        editor.cancel.setAttribute('data-testid', 'rules-row-cancel');
        body.appendChild(editor.label);
        body.appendChild(editor.input);
        body.appendChild(editor.foot);
        row.appendChild(body);
        return row;
      }

      var textEl = el('p', 'rules-row-text', rule.text);
      textEl.setAttribute('data-testid', 'rules-row-text');
      body.appendChild(textEl);
      row.appendChild(body);

      var edit = App.ui.button({
        variant: 'ghost',
        size: 'sm',
        label: 'Edit',
        ariaLabel: 'Edit ' + label.toLowerCase(),
        testid: 'rules-row-edit',
        onClick: function () {
          editingId = rule.id;
          showError('');
          renderList();
          var inp = listWrap.querySelector('[data-id="' + rule.id + '"] [data-testid="rules-row-edit-input"]');
          if (inp) inp.focus();
        }
      });
      edit.setAttribute('data-rule-id', rule.id);
      var up = App.ui.button({
        variant: 'ghost',
        size: 'sm',
        label: 'Move up',
        ariaLabel: 'Move ' + label.toLowerCase() + ' up',
        testid: 'rules-row-up',
        disabled: index === 0,
        onClick: function () { move(index, -1); }
      });
      var down = App.ui.button({
        variant: 'ghost',
        size: 'sm',
        label: 'Move down',
        ariaLabel: 'Move ' + label.toLowerCase() + ' down',
        testid: 'rules-row-down',
        disabled: index === rules.length - 1,
        onClick: function () { move(index, 1); }
      });
      var del = buildDeleteButton({
        ariaLabel: 'Delete ' + label.toLowerCase(),
        onConfirm: function (revert) {
          var neighbour = rules[index + 1] || rules[index - 1] || null;
          mutate(function () {
            return cb.deleteRule(name, rule.id);
          }, function () {
            if (neighbour) focusEdit(neighbour.id);
            else addInput.focus();
          }, { onError: revert, origin: { kind: 'row', id: rule.id, control: 'rules-row-delete' } });
        }
      });
      del.setAttribute('data-testid', 'rules-row-delete');
      actions.appendChild(edit);
      actions.appendChild(up);
      actions.appendChild(down);
      actions.appendChild(del);
      row.appendChild(actions);
      return row;
    }

    function focusEdit(id) {
      var b = rowEdit(id);
      if (b) b.focus();
    }

    function renderList() {
      listWrap.textContent = '';
      if (!rules.length) {
        var empty = buildEmpty('No rules yet.', true);
        empty.setAttribute('data-testid', 'rules-empty');
        listWrap.appendChild(empty);
        return;
      }
      var ol = el('ol', 'rules-list');
      ol.setAttribute('role', 'list');
      ol.setAttribute('data-testid', 'rules-list');
      ol.setAttribute('aria-label', 'Rules');
      for (var i = 0; i < rules.length; i++) ol.appendChild(buildRow(rules[i], i));
      listWrap.appendChild(ol);
    }

    // Read the list; a stale response never overwrites a newer render.
    function load() {
      var mine = ++gen;
      return cb.fetchRules(name).then(function (body) {
        if (mine !== gen) return;
        rules = (body && body.rules) || [];
        if (body && body.limits) limits = body.limits;
        if (editingId && !rules.some(function (r) { return r.id === editingId; })) editingId = null;
        renderList();
        syncAdd();
      });
    }

    var mutate = makeMutate({
      listWrap: listWrap,
      editTestid: 'rules-row-edit',
      isBusy: function () { return busy; },
      setBusy: setBusy,
      showError: showError,
      load: load,
      fallback: function () { return addInput; }
    });

    function add() {
      var text = addInput.value;
      if (!text.trim()) return;
      mutate(function () {
        return cb.createRule(name, text);
      }, function () {
        addInput.value = '';
        syncAdd();
        addInput.focus();
      }, { origin: { kind: 'add' } });
    }

    function move(index, delta) {
      var ids = rules.map(function (r) { return r.id; });
      var target = index + delta;
      if (target < 0 || target >= ids.length) return;
      var moved = ids.splice(index, 1)[0];
      ids.splice(target, 0, moved);
      mutate(function () {
        return cb.reorderRules(name, ids);
      }, function () {
        var rowEl = listWrap.querySelector('[data-id="' + moved + '"]');
        if (!rowEl) return;
        var same = rowEl.querySelector(delta < 0
          ? '[data-testid="rules-row-up"]' : '[data-testid="rules-row-down"]');
        var other = rowEl.querySelector(delta < 0
          ? '[data-testid="rules-row-down"]' : '[data-testid="rules-row-up"]');
        if (same && !same.disabled) same.focus();
        else if (other) other.focus();
      }, { origin: { kind: 'row', id: moved, control: delta < 0 ? 'rules-row-up' : 'rules-row-down' } });
    }

    // An approved change to a rule reloads the list (M36 F2 L8). An open inline edit keeps the
    // operator's typed text; when the stored rule changed under it, the row says so.
    function reload() {
      var input = editingId ?
        listWrap.querySelector('[data-testid="rules-row-edit-input"]') : null;
      var editedId = input ? editingId : null;
      var typed = input ? input.value : null;
      var old = null;
      for (var i = 0; i < rules.length; i++) if (rules[i].id === editedId) old = rules[i].text;
      return load().then(function () {
        if (editedId === null || editingId !== editedId || typed === old) return;
        var fresh = listWrap.querySelector('[data-testid="rules-row-edit-input"]');
        if (!fresh) return;
        fresh.value = typed;
        fresh.dispatchEvent(new Event('input', { bubbles: true }));
        var now = null;
        for (var j = 0; j < rules.length; j++) if (rules[j].id === editedId) now = rules[j].text;
        if (now === old) return;
        var note = el('p', 'rules-row-changed-note',
          'This rule changed. Save will replace it with your text.');
        note.setAttribute('data-testid', 'rules-row-changed-note');
        var host = fresh.parentNode;
        if (host) host.appendChild(note);
      });
    }

    syncAdd();
    listWrap.appendChild(el('p', 'rules-loading', 'Loading…'));
    load().catch(function (err) {
      showError('Couldn’t load rules: ' + messageOf(err));
      listWrap.textContent = '';
    });
    return {
      reload: reload,
      placeNote: function (note) { section.insertBefore(note, listWrap); }
    };
  }

  function renderRulesNotesTab(panel, agent, callbacks) {
    callbacks = callbacks || {};
    panel.textContent = '';
    if (!agent) {
      var notice = buildEmpty('Save the agent first to add rules.');
      notice.setAttribute('data-testid', 'rules-create-mode');
      panel.appendChild(notice);
      var notesNotice = buildEmpty('Save the agent first to let it keep notes.');
      notesNotice.setAttribute('data-testid', 'notes-create-mode');
      panel.appendChild(notesNotice);
      return;
    }
    var rulesHandle = buildRulesSection(panel, agent, callbacks);
    window.App.studio.buildNotesSection(panel, agent, callbacks);
    return rulesHandle;
  }

  window.App.studio.renderRulesNotesTab = renderRulesNotesTab;
})();
