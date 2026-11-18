// App.studio.buildNotesSection -- the Notes section of the agent editor's Rules and notes
// tab (M27 F2 L3, flight DD10; split out of rules-notes-tab.js in M31 F2 L11 with no
// behaviour change). Called by renderRulesNotesTab with (panel, agent, callbacks); the
// callbacks are documented in rules-notes-tab.js. Note text can come from an attacker:
// every note field is written with textContent only (never an HTML-string sink).
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

  // The row's frame: the list item, the [n] number and the body column.
  function noteRowShell(note) {
    var row = el('li', 'notes-row');
    row.setAttribute('data-testid', 'notes-row');
    row.setAttribute('data-id', note.id);
    row.setAttribute('data-number', String(note.number));
    row.appendChild(el('span', 'notes-row-number', '[' + note.number + ']'));
    row.appendChild(el('div', 'notes-row-body'));
    return row;
  }

  // One note's read-only row: text, the "Check this" flag, time, origin and "Edited by
  // you", then `opts.actions` (an element, or null) at the end. Pure: no state and no
  // callbacks, so the agent Notes tab and GleepGlorp's Memory section share it. The note's
  // text is attacker-influenced and is written with textContent only.
  function noteRow(note, opts) {
    var row = noteRowShell(note);
    var body = row.querySelector('.notes-row-body');

    var textEl = el('p', 'rules-row-text notes-row-text', note.text);
    textEl.setAttribute('data-testid', 'notes-row-text');
    body.appendChild(textEl);

    var meta = el('div', 'notes-row-meta');
    meta.setAttribute('data-testid', 'notes-row-meta');
    if (note.untrusted) {
      var check = App.ui.noteFlag({ sources: note.untrusted_sources || [] });
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

    if (opts && opts.actions) row.appendChild(opts.actions);
    return row;
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

    var errorLine = buildErrorLine();
    errorLine.el.setAttribute('data-testid', 'notes-error');
    section.appendChild(errorLine.el);

    var liveLine = buildLiveLine();
    liveLine.el.setAttribute('data-testid', 'notes-status');
    section.appendChild(liveLine.el);
    var announce = liveLine.announce;

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

    var showError = errorLine.show;

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

      if (editingId === note.id) {
        var row = noteRowShell(note);
        var body = row.querySelector('.notes-row-body');
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
      return noteRow(note, { actions: actions });
    }

    function renderList() {
      listWrap.textContent = '';
      if (!notes.length) {
        var empty = buildEmpty('No notes yet.', true);
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

  window.App.studio.buildNotesSection = buildNotesSection;
  window.App.studio.noteRow = noteRow;
  window.App.studio.formatNotesCount = formatCount;
})();
