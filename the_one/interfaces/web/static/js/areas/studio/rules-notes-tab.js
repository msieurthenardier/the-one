// App.studio.renderRulesNotesTab -- the agent editor's "Rules and notes" tab
// (M27 F1 L2, flight DD6). Built with DOM APIs only.
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
//   updateNote(name, id, text)   -> Promise<note>
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

  function messageOf(err) {
    return (err && err.message) ? err.message : 'Request failed';
  }

  // Disable every control in a list while a request is in flight, remembering
  // each one's prior state.
  function disableList(listWrap) {
    var controls = listWrap.querySelectorAll('button, input, textarea');
    for (var i = 0; i < controls.length; i++) {
      controls[i]._wasDisabled = controls[i].disabled;
      controls[i].disabled = true;
    }
  }

  function restoreDisabled(listWrap) {
    var controls = listWrap.querySelectorAll('button, input, textarea');
    for (var i = 0; i < controls.length; i++) {
      if (controls[i]._wasDisabled !== undefined) {
        controls[i].disabled = controls[i]._wasDisabled;
        delete controls[i]._wasDisabled;
      }
    }
  }

  // Failure focus (SC 2.4.3), from an EXPLICIT origin the caller names rather
  // than document.activeElement (which a mouse click can leave on <body> in
  // WebKit). An origin is one of:
  //   {kind: 'row', id, control}  a control (data-testid) inside a list row
  //   {kind: 'add'}               the section's Add / default target
  //   {kind: 'el', el}            a stable element outside the list
  // A row control that is gone falls back to the row's Edit button (the
  // `editTestid`), then to the section's default target.
  function restoreOrigin(listWrap, origin, editTestid, fallback) {
    var target = null;
    if (origin && origin.kind === 'el' && origin.el && origin.el.isConnected && !origin.el.disabled) {
      target = origin.el;
    } else if (origin && origin.kind === 'row' && origin.id) {
      var row = listWrap.querySelector('[data-id="' + origin.id + '"]');
      if (row) {
        var again = row.querySelector('[data-testid="' + origin.control + '"]');
        if (again && !again.disabled) target = again;
        else {
          var edit = row.querySelector('[data-testid="' + editTestid + '"]');
          if (edit && !edit.disabled) target = edit;
        }
      }
    }
    if (!target) target = fallback;
    if (target) target.focus();
  }

  // One saving action runner shared by both sections. cfg: {isBusy, setBusy(on),
  // showError(msg), load(), listWrap, editTestid, fallback()}. Runs: disable the
  // controls, call the API, re-read the list, then place focus (afterFocus). On
  // failure show the detail inline and re-read so the list stays as the server
  // has it, then restore focus to opts.origin. opts: {origin, before, onError,
  // keepEditingOnError}.
  function makeMutate(cfg) {
    return function mutate(action, afterFocus, opts) {
      opts = opts || {};
      if (cfg.isBusy()) return Promise.resolve();
      cfg.showError('');
      var restore = function () {
        restoreOrigin(cfg.listWrap, opts.origin, cfg.editTestid, cfg.fallback());
      };
      cfg.setBusy(true);
      return Promise.resolve().then(action).then(function () {
        if (opts.before) opts.before();
        cfg.setBusy(false);
        return cfg.load();
      }).then(function () {
        if (afterFocus) afterFocus();
      }, function (err) {
        cfg.showError(messageOf(err));
        if (opts.onError) opts.onError();
        cfg.setBusy(false);
        if (opts.keepEditingOnError) {
          // The server rejected the edit; the inline editor (and its text)
          // stay open so the operator can fix it.
          restoreDisabled(cfg.listWrap);
          restore();
          return;
        }
        return cfg.load().then(function () {}, function () {}).then(restore);
      });
    };
  }

  // The inline editor shared by a rule and a note: a hidden-label textarea, a
  // live "{n} / {max}" count (aria-invalid and Save disabled while over) and
  // Save / Cancel (the caller sets the data-testid literals on the returned
  // nodes: the registry guard only sees literal ids). cfg: {value, max(), noun, label, idSuffix, isBusy, announce(msg), onSave(text), onCancel()}.
  function buildInlineEditor(cfg) {
    var input = App.ui.textarea({ rows: 3, value: cfg.value });
    var label = el('label', 'visually-hidden', cfg.label);
    label.htmlFor = input.id;
    var count = el('span', 'rules-add-count');
    count.id = cfg.idSuffix;
    input.setAttribute('aria-describedby', count.id);
    var save = App.ui.button({
      variant: 'primary',
      size: 'sm',
      label: 'Save',
      onClick: function () {
        if (!input.value.trim()) return;
        cfg.onSave(input.value);
      }
    });
    var cancel = App.ui.button({
      variant: 'secondary',
      size: 'sm',
      label: 'Cancel',
      onClick: function () { cfg.onCancel(); }
    });
    var wasOver = false;
    function sync() {
      var n = input.value.length;
      var max = cfg.max();
      var over = n > max;
      if (over !== wasOver) {
        wasOver = over;
        cfg.announce(over ? 'Over the ' + max + ' character limit for a ' + cfg.noun + '.' : '');
      }
      count.textContent = n + ' / ' + max + (over ? ' — over the limit' : '');
      count.classList.toggle('rules-add-count--over', over);
      if (over) input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
      save.disabled = cfg.isBusy() || over || !input.value.trim();
    }
    input.addEventListener('input', sync);
    sync();
    var foot = el('div', 'rules-add-foot');
    foot.appendChild(count);
    var btns = el('div', 'rules-row-actions');
    btns.appendChild(cancel);
    btns.appendChild(save);
    foot.appendChild(btns);
    return { label: label, input: input, foot: foot, save: save, cancel: cancel, count: count };
  }

  // A delete button that arms, then confirms, through App.confirmDelete (the
  // library announces the arm from the button's aria-label).
  function buildDeleteButton(cfg) {
    var del = App.ui.button({
      variant: 'danger',
      size: 'sm',
      ariaLabel: cfg.ariaLabel,
      className: 'delete-btn',
    });
    del.appendChild(el('span', null, 'Delete')).setAttribute('data-confirm-title', '');
    del.addEventListener('click', function () {
      window.App.confirmDelete(del, function (btn, revert) { cfg.onConfirm(revert); });
    });
    return del;
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

    // Polite, visually hidden status line: announces crossing the per-rule limit
    // (the delete arm is announced by App.ui.confirm).
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
      row.querySelector('.ui-toggle').classList.add('rules-row-toggle-wrap');

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
        var empty = el('p', 'rules-empty', 'No rules yet.');
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

    syncAdd();
    listWrap.appendChild(el('p', 'rules-loading', 'Loading…'));
    load().catch(function (err) {
      showError('Couldn’t load rules: ' + messageOf(err));
      listWrap.textContent = '';
    });
  }

  // ── Notes (M27 F2 L3, flight DD10) ────────────────────────────────────
  var DEFAULT_NOTE_CHARS = 400;
  var DEFAULT_NOTES_TOTAL = 4000;
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function parseWhen(iso) {
    if (!iso) return null;
    var text = String(iso);
    // A stored timestamp without an offset is UTC.
    if (!/(Z|[+-]\d\d:?\d\d)$/.test(text)) text += 'Z';
    var d = new Date(text);
    return isNaN(d.getTime()) ? null : d;
  }

  // The local 12-hour clock for today, otherwise a short date.
  function formatWhen(iso) {
    var d = parseWhen(iso);
    if (!d) return '';
    var now = new Date();
    if (App.time.dayNumber(d) === App.time.dayNumber(now)) {
      return App.time.formatClock(d);
    }
    var p = App.time.parts(d);
    var out = MONTHS[p.month] + ' ' + p.day;
    if (p.year !== App.time.parts(now).year) out += ', ' + p.year;
    return out;
  }

  function formatCount(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  // Where a note was written: built with textContent only.
  function buildOrigin(note) {
    var wrap = el('span', 'notes-row-origin');
    wrap.setAttribute('data-testid', 'notes-row-origin');
    var label = note.origin_label || 'Untitled chat';
    if (note.origin_kind === 'other') {
      wrap.textContent = 'Outside a chat';
      return wrap;
    }
    if (note.origin_kind === 'connector') {
      if (note.origin_platform) {
        wrap.appendChild(App.ui.badge({ text: String(note.origin_platform), testid: 'notes-row-platform' }));
      }
      var peer = note.origin_peer_name || note.origin_peer_id;
      if (peer) wrap.appendChild(el('span', 'notes-row-peer', String(peer)));
    }
    if (note.origin_exists && note.origin_session_id) {
      var link = el('a', 'notes-row-origin-link', label);
      link.setAttribute('href', App.router.href({ destination: 'chats', id: note.origin_session_id }));
      link.setAttribute('data-testid', 'notes-row-origin-link');
      wrap.appendChild(link);
    } else if (note.origin_kind !== 'connector') {
      wrap.appendChild(el('span', null, label + ' (chat deleted)'));
    }
    return wrap;
  }

  function buildNotesSection(panel, agent, cb) {
    var name = agent.name || '';
    var section = makeSection(panel, 'notes', 'Notes');
    section.setAttribute('data-testid', 'notes-section');
    var notes = [];
    var enabled = false;
    var limits = { note_chars: DEFAULT_NOTE_CHARS, total_chars: DEFAULT_NOTES_TOTAL };
    var usedChars = 0;
    var editingId = null;
    var busy = false;
    var gen = 0;

    var toggle = App.ui.toggle({
      label: 'Let this agent keep notes',
      checked: false,
      testid: 'notes-enabled-toggle',
      onChange: function (checked) {
        mutate(function () {
          return cb.setNotesEnabled(name, checked);
        }, function () { toggle.control.focus(); }, { origin: { kind: 'el', el: toggle.control } });
      }
    });
    toggle.el.classList.add('notes-enabled-toggle');
    section.appendChild(toggle.el);

    var appliesNote = el('p', 'rules-applies-note', APPLIES_NOTE);
    appliesNote.setAttribute('data-testid', 'notes-applies-note');
    section.appendChild(appliesNote);

    var offMessage = el('p', 'notes-off-message',
      'Notes are off. This agent can’t see or write notes. Saved notes are kept.');
    offMessage.setAttribute('data-testid', 'notes-off-message');
    offMessage.hidden = true;
    offMessage.id = 'notes-off-message';
    section.appendChild(offMessage);

    var errorEl = el('p', 'rules-error');
    errorEl.setAttribute('data-testid', 'notes-error');
    errorEl.setAttribute('role', 'alert');
    errorEl.hidden = true;
    section.appendChild(errorEl);

    var liveEl = el('p', 'visually-hidden');
    liveEl.setAttribute('data-testid', 'notes-status');
    liveEl.setAttribute('role', 'status');
    liveEl.setAttribute('aria-live', 'polite');
    section.appendChild(liveEl);
    function announce(msg) { liveEl.textContent = msg || ''; }

    var bar = el('div', 'notes-bar');
    var usageEl = el('p', 'notes-usage');
    usageEl.setAttribute('data-testid', 'notes-usage');
    var clearBtn = App.ui.button({
      variant: 'secondary',
      size: 'sm',
      label: 'Clear all',
      testid: 'notes-clear-all',
      onClick: function () { clearAll(); }
    });
    clearBtn.hidden = true;
    bar.appendChild(usageEl);
    bar.appendChild(clearBtn);
    section.appendChild(bar);

    var listWrap = el('div', 'rules-list-wrap');
    section.appendChild(listWrap);

    function maxChars() { return limits.note_chars || DEFAULT_NOTE_CHARS; }

    function showError(msg) {
      errorEl.textContent = msg || '';
      errorEl.hidden = !msg;
    }

    function setBusy(on) {
      busy = on;
      listWrap.setAttribute('aria-busy', on ? 'true' : 'false');
      if (on) disableList(listWrap);
      toggle.control.disabled = on;
      clearBtn.disabled = on;
    }

    function syncHeader() {
      toggle.setChecked(enabled);
      offMessage.hidden = enabled;
      // Described by the off message only while it is showing.
      if (enabled) toggle.control.removeAttribute('aria-describedby');
      else toggle.control.setAttribute('aria-describedby', offMessage.id);
      usageEl.textContent = formatCount(usedChars) + ' of ' +
        formatCount(limits.total_chars || DEFAULT_NOTES_TOTAL) + ' characters';
      clearBtn.hidden = !notes.length;
    }

    function rowEdit(id) {
      return listWrap.querySelector('[data-testid="notes-row-edit"][data-note-id="' + id + '"]');
    }
    function focusEdit(id) {
      var b = rowEdit(id);
      if (b) b.focus();
    }

    function buildRow(note) {
      var label = 'note ' + note.number;
      var row = el('li', 'notes-row');
      row.setAttribute('data-testid', 'notes-row');
      row.setAttribute('data-id', note.id);
      row.setAttribute('data-number', String(note.number));
      row.appendChild(el('span', 'notes-row-number', '[' + note.number + ']'));

      var body = el('div', 'notes-row-body');
      row.appendChild(body);

      if (editingId === note.id) {
        var editor = buildInlineEditor({
          value: note.text,
          max: maxChars,
          noun: 'note',
          label: 'Edit ' + label,
          idSuffix: 'notes-edit-count-' + note.id,
          isBusy: function () { return busy; },
          announce: announce,
          onSave: function (text) {
            mutate(function () {
              return cb.updateNote(name, note.id, text);
            }, function () { focusEdit(note.id); }, {
              before: function () { editingId = null; },
              keepEditingOnError: true,
              origin: { kind: 'row', id: note.id, control: 'notes-row-save' }
            });
          },
          onCancel: function () {
            editingId = null;
            showError('');
            renderList();
            focusEdit(note.id);
          }
        });
        editor.input.setAttribute('data-testid', 'notes-row-edit-input');
        editor.save.setAttribute('data-testid', 'notes-row-save');
        editor.cancel.setAttribute('data-testid', 'notes-row-cancel');
        editor.count.setAttribute('data-testid', 'notes-row-edit-count');
        body.appendChild(editor.label);
        body.appendChild(editor.input);
        body.appendChild(editor.foot);
        return row;
      }

      var textEl = el('p', 'rules-row-text notes-row-text', note.text);
      textEl.setAttribute('data-testid', 'notes-row-text');
      body.appendChild(textEl);

      var meta = el('div', 'notes-row-meta');
      meta.setAttribute('data-testid', 'notes-row-meta');
      if (note.untrusted) {
        var check = App.noteFlag(note.untrusted_sources || []);
        check.setAttribute('data-testid', 'notes-row-flag');
        meta.appendChild(check);
      }
      var changed = note.updated_at && note.updated_at !== note.created_at;
      var when = formatWhen(changed ? note.updated_at : note.created_at);
      if (when) {
        var time = el('span', 'notes-row-time', (changed ? 'Updated ' : '') + when);
        time.setAttribute('data-testid', 'notes-row-time');
        meta.appendChild(time);
      }
      meta.appendChild(buildOrigin(note));
      if (note.updated_by === 'operator') {
        var edited = el('span', 'notes-row-edited', 'Edited by you');
        edited.setAttribute('data-testid', 'notes-row-edited');
        meta.appendChild(edited);
      }
      body.appendChild(meta);

      var actions = el('div', 'rules-row-actions');
      var edit = App.ui.button({
        variant: 'ghost',
        size: 'sm',
        label: 'Edit',
        ariaLabel: 'Edit ' + label,
        testid: 'notes-row-edit',
        onClick: function () {
          editingId = note.id;
          showError('');
          renderList();
          var inp = listWrap.querySelector('[data-id="' + note.id + '"] [data-testid="notes-row-edit-input"]');
          if (inp) inp.focus();
        }
      });
      edit.setAttribute('data-note-id', note.id);
      var del = buildDeleteButton({
        ariaLabel: 'Delete ' + label,
        onConfirm: function (revert) {
          var idx = notes.indexOf(note);
          var neighbour = notes[idx + 1] || notes[idx - 1] || null;
          mutate(function () {
            return cb.deleteNote(name, note.id);
          }, function () {
            if (neighbour) focusEdit(neighbour.id);
            else toggle.control.focus();
          }, { onError: revert, origin: { kind: 'row', id: note.id, control: 'notes-row-delete' } });
        }
      });
      del.setAttribute('data-testid', 'notes-row-delete');
      actions.appendChild(edit);
      actions.appendChild(del);
      row.appendChild(actions);
      return row;
    }

    function renderList() {
      listWrap.textContent = '';
      if (!notes.length) {
        var empty = el('p', 'rules-empty', 'No notes yet.');
        empty.setAttribute('data-testid', 'notes-empty');
        listWrap.appendChild(empty);
        return;
      }
      var ul = el('ul', 'rules-list notes-list');
      ul.setAttribute('data-testid', 'notes-list');
      ul.setAttribute('aria-label', 'Notes');
      ul.setAttribute('role', 'list');
      for (var i = 0; i < notes.length; i++) ul.appendChild(buildRow(notes[i]));
      listWrap.appendChild(ul);
    }

    // "When" labels follow the operator zone (M28 F2 L1). This tab has no teardown
    // hook, so the listener is owner-scoped: App.time drops it once listWrap leaves the page.
    App.time.onChange(function () {
      if (!editingId) renderList();
    }, listWrap);

    function load() {
      var mine = ++gen;
      return cb.fetchNotes(name).then(function (body) {
        if (mine !== gen) return;
        body = body || {};
        enabled = !!body.enabled;
        notes = body.notes || [];
        if (body.limits) limits = body.limits;
        usedChars = body.usage && typeof body.usage.total_chars === 'number'
          ? body.usage.total_chars : notes.reduce(function (n, x) { return n + x.text.length; }, 0);
        if (editingId && !notes.some(function (n) { return n.id === editingId; })) editingId = null;
        syncHeader();
        renderList();
      });
    }

    var mutate = makeMutate({
      listWrap: listWrap,
      editTestid: 'notes-row-edit',
      isBusy: function () { return busy; },
      setBusy: setBusy,
      showError: showError,
      load: load,
      fallback: function () { return toggle.control; }
    });

    function clearAll() {
      var n = notes.length;
      if (!n) return;
      App.confirmDialog({
        title: 'Clear all notes',
        message: 'Clear all ' + n + ' ' + (n === 1 ? 'note' : 'notes') + '? This can’t be undone.',
        confirmText: 'Clear all',
        cancelText: 'Cancel',
        opener: clearBtn,
        onConfirm: function () {
          mutate(function () {
            return cb.clearNotes(name);
          }, function () { toggle.control.focus(); }, { origin: { kind: 'el', el: toggle.control } });
        }
      });
    }

    syncHeader();
    listWrap.appendChild(el('p', 'rules-loading', 'Loading…'));
    load().catch(function (err) {
      showError('Couldn’t load notes: ' + messageOf(err));
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
      var notesNotice = el('p', 'empty-state', 'Save the agent first to let it keep notes.');
      notesNotice.setAttribute('data-testid', 'notes-create-mode');
      panel.appendChild(notesNotice);
      return;
    }
    buildRulesSection(panel, agent, callbacks);
    buildNotesSection(panel, agent, callbacks);
  }

  window.App.studio.renderRulesNotesTab = renderRulesNotesTab;
})();
