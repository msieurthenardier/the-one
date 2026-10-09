// App.studio.renderRulesNotesTab -- the agent editor's "Rules and notes" tab
// (M27 F1 L2, flight DD6). Built with DOM APIs only.
//
// Flight 1 holds one section, Rules: the operator's ordered list of standing
// instructions for the agent. Flight 2 appends a Notes section below it, so the
// panel is built from `makeSection(id, title)` and the Rules section is a
// self-contained builder (`buildRulesSection`).
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
// }
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

  var APPLIES_NOTE = 'Changes apply to new and reopened chats, and to the next ' +
    'message in connector channels.';
  var DEFAULT_RULE_CHARS = 500;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  // One titled section of the panel. Flight 2 appends Notes with the same call.
  function makeSection(panel, id, title) {
    var root = el('div', 'editor-section rules-notes-section');
    var heading = el('h3', 'section-title', title);
    root.appendChild(heading);
    panel.appendChild(root);
    return root;
  }

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

    var errorEl = el('p', 'rules-error');
    errorEl.setAttribute('data-testid', 'rules-error');
    errorEl.setAttribute('role', 'alert');
    errorEl.hidden = true;
    section.appendChild(errorEl);

    // Polite, visually hidden status line: announces the delete arm (the delete
    // button's persistent aria-label overrides the swapped "Confirm delete?"
    // text, as in self-configuration-tab.js) and crossing the per-rule limit.
    var liveEl = el('p', 'visually-hidden');
    liveEl.setAttribute('data-testid', 'rules-status');
    liveEl.setAttribute('role', 'status');
    liveEl.setAttribute('aria-live', 'polite');
    section.appendChild(liveEl);
    function announce(msg) { liveEl.textContent = msg || ''; }
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

    function showError(msg) {
      errorEl.textContent = msg || '';
      errorEl.hidden = !msg;
    }

    function setBusy(on) {
      busy = on;
      listWrap.setAttribute('aria-busy', on ? 'true' : 'false');
      var controls = listWrap.querySelectorAll('button, input, textarea');
      for (var i = 0; i < controls.length; i++) {
        if (on) {
          controls[i]._wasDisabled = controls[i].disabled;
          controls[i].disabled = true;
        }
      }
      syncAdd();
    }

    function messageOf(err) {
      return (err && err.message) ? err.message : 'Request failed';
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
          });
        }
      });
      toggle.control.setAttribute('data-rule-id', rule.id);
      row.appendChild(toggle.el);
      row.querySelector('.ui-toggle').classList.add('rules-row-toggle-wrap');

      if (editingId === rule.id) {
        var editInput = App.ui.textarea({
          rows: 3,
          value: rule.text,
          testid: 'rules-row-edit-input'
        });
        var editLabel = el('label', 'visually-hidden', 'Edit ' + label.toLowerCase());
        editLabel.htmlFor = editInput.id;
        var editCount = el('span', 'rules-add-count');
        editCount.id = 'rules-edit-count-' + rule.id;
        editInput.setAttribute('aria-describedby', editCount.id);
        var save = App.ui.button({
          variant: 'primary',
          size: 'sm',
          label: 'Save',
          testid: 'rules-row-save',
          onClick: function () {
            var text = editInput.value;
            if (!text.trim()) return;
            mutate(function () {
              return cb.updateRule(name, rule.id, { text: text });
            }, function () { focusEdit(rule.id); }, {
              before: function () { editingId = null; },
              keepEditingOnError: true
            });
          }
        });
        var cancel = App.ui.button({
          variant: 'secondary',
          size: 'sm',
          label: 'Cancel',
          testid: 'rules-row-cancel',
          onClick: function () {
            editingId = null;
            showError('');
            renderList();
            focusEdit(rule.id);
          }
        });
        var editWasOver = false;
        var syncEdit = function () {
          var n = editInput.value.length;
          var over = n > maxChars();
          if (over !== editWasOver) {
            editWasOver = over;
            announce(over ? 'Over the ' + maxChars() + ' character limit for a rule.' : '');
          }
          editCount.textContent = n + ' / ' + maxChars() + (over ? ' \u2014 over the limit' : '');
          editCount.classList.toggle('rules-add-count--over', over);
          if (over) editInput.setAttribute('aria-invalid', 'true');
          else editInput.removeAttribute('aria-invalid');
          save.disabled = busy || over || !editInput.value.trim();
        };
        editInput.addEventListener('input', syncEdit);
        syncEdit();
        var editFoot = el('div', 'rules-add-foot');
        editFoot.appendChild(editCount);
        var editBtns = el('div', 'rules-row-actions');
        editBtns.appendChild(cancel);
        editBtns.appendChild(save);
        editFoot.appendChild(editBtns);
        body.appendChild(editLabel);
        body.appendChild(editInput);
        body.appendChild(editFoot);
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
      var del = App.ui.button({
        variant: 'danger',
        size: 'sm',
        ariaLabel: 'Delete ' + label.toLowerCase(),
        className: 'delete-btn',
        testid: 'rules-row-delete'
      });
      del.appendChild(el('span', null, 'Delete')).setAttribute('data-confirm-title', '');
      del.addEventListener('click', function () {
        announce('');
        window.App.confirmDelete(del, function (btn, revert) {
          var neighbour = rules[index + 1] || rules[index - 1] || null;
          mutate(function () {
            return cb.deleteRule(name, rule.id);
          }, function () {
            if (neighbour) focusEdit(neighbour.id);
            else addInput.focus();
          }, { onError: revert });
        });
        if (del.classList.contains('confirm-delete')) {
          announce('Press Delete again to confirm deleting ' + label.toLowerCase() + '.');
        }
      });
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
        var empty = el('p', 'rules-empty', 'No rules yet.');
        empty.setAttribute('data-testid', 'rules-empty');
        listWrap.appendChild(empty);
        return;
      }
      var ol = el('ol', 'rules-list');
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

    // Run one saving action: disable the controls, call the API, re-read the
    // list, then place focus. On failure show the detail inline and re-read so
    // the list stays as the server has it.
    function mutate(action, afterFocus, opts) {
      opts = opts || {};
      if (busy) return Promise.resolve();
      showError('');
      var prior = listWrap.contains(document.activeElement) ? document.activeElement : null;
      var priorRow = prior && prior.closest ? prior.closest('[data-id]') : null;
      var priorKey = prior ? {
        kind: prior.getAttribute('data-testid'),
        id: priorRow ? priorRow.getAttribute('data-id') : null
      } : null;
      // After a failure: the pre-action control if it is still there, else
      // that row's Edit button, else the Add textarea (SC 2.4.3).
      var fromAdd = !prior && section.contains(document.activeElement) &&
        !listWrap.contains(document.activeElement);
      var restoreFocus = function () {
        if (fromAdd) { addInput.focus(); return; }
        if (!priorKey) return;
        if (prior && document.contains(prior) && !prior.disabled) { prior.focus(); return; }
        if (priorKey.id) {
          var again = listWrap.querySelector('[data-id="' + priorKey.id + '"] [data-testid="' +
            priorKey.kind + '"]');
          if (again && !again.disabled) { again.focus(); return; }
          var edit = rowEdit(priorKey.id);
          if (edit && !edit.disabled) { edit.focus(); return; }
        }
        addInput.focus();
      };
      setBusy(true);
      return Promise.resolve().then(action).then(function () {
        if (opts.before) opts.before();
        setBusy(false);
        return load();
      }).then(function () {
        if (afterFocus) afterFocus();
      }, function (err) {
        showError(messageOf(err));
        if (opts.onError) opts.onError();
        setBusy(false);
        if (opts.keepEditingOnError) {
          // The server rejected the edit; the inline editor (and its text)
          // stay open so the operator can fix it.
          restoreDisabled();
          restoreFocus();
          return;
        }
        return load().then(function () {}, function () {}).then(restoreFocus);
      });
    }

    function restoreDisabled() {
      var controls = listWrap.querySelectorAll('button, input, textarea');
      for (var i = 0; i < controls.length; i++) {
        if (controls[i]._wasDisabled !== undefined) {
          controls[i].disabled = controls[i]._wasDisabled;
          delete controls[i]._wasDisabled;
        }
      }
    }

    function add() {
      var text = addInput.value;
      if (!text.trim()) return;
      mutate(function () {
        return cb.createRule(name, text);
      }, function () {
        addInput.value = '';
        syncAdd();
        addInput.focus();
      });
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
      });
    }

    syncAdd();
    listWrap.appendChild(el('p', 'rules-loading', 'Loading…'));
    load().catch(function (err) {
      showError('Couldn’t load rules: ' + messageOf(err));
      listWrap.textContent = '';
    });
  }

  function renderRulesNotesTab(panel, agent, callbacks) {
    callbacks = callbacks || {};
    panel.textContent = '';
    if (!agent) {
      var notice = el('p', 'empty-state', 'Save the agent first to add rules.');
      notice.setAttribute('data-testid', 'rules-create-mode');
      panel.appendChild(notice);
      return;
    }
    buildRulesSection(panel, agent, callbacks);
  }

  window.App.studio.renderRulesNotesTab = renderRulesNotesTab;
})();
