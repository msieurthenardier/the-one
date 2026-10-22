// Shared builders for the agent editor's Rules and notes tab (M31 F2 L11: split from
// rules-notes-tab.js, no behaviour change). Exposed as App.studio.rulesNotesShared and read
// by rules-notes-tab.js (Rules, the entry) and notes-section.js (Notes). Everything is
// built with DOM APIs; note text is written with textContent only.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var APPLIES_NOTE = 'Changes apply to new and reopened chats, and to the next ' +
    'message in connector channels.';

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  // One titled section of the panel. Flight 2 appends Notes with the same call.
  function makeSection(panel, id, title) {
    var section = App.ui.section({ title: title, titleTag: 'h3', className: 'rules-notes-section' });
    panel.appendChild(section.el);
    return section.el;
  }

  // The error line (role=alert, hidden until there is a message) and the polite,
  // visually hidden status line, both App.ui.status. Returns {el, show(msg)} and
  // {el, announce(msg)}.
  function buildErrorLine() {
    var line = App.ui.status({ state: 'danger', role: 'alert' });
    line.el.hidden = true;
    return {
      el: line.el,
      show: function (msg) {
        line.set('danger', msg || '');
        line.el.hidden = !msg;
      }
    };
  }
  function buildLiveLine() {
    var line = App.ui.status({ state: 'idle' });
    line.el.classList.add('visually-hidden');
    return {
      el: line.el,
      announce: function (msg) { line.set('idle', msg || ''); }
    };
  }

  // An empty-state notice (App.ui.emptyState, a paragraph title) in the library's
  // 'plain' variant (the title reads as running text); `flush` also makes the
  // root a flush, left-aligned line, for the list's own "none yet" notice.
  function buildEmpty(title, flush) {
    return App.ui.emptyState({ title: title, titleTag: 'p', variant: flush ? 'flush' : 'plain' });
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

  // A delete button that arms, then confirms, through App.ui.confirm (the
  // library announces the arm from the button's aria-label).
  function buildDeleteButton(cfg) {
    var del = App.ui.button({
      variant: 'danger',
      size: 'sm',
      ariaLabel: cfg.ariaLabel
    });
    del.appendChild(el('span', null, 'Delete')).setAttribute('data-confirm-title', '');
    del.addEventListener('click', function () {
      App.ui.confirm(del, function (btn, revert) { cfg.onConfirm(revert); });
    });
    return del;
  }

  window.App.studio.rulesNotesShared = {
    APPLIES_NOTE: APPLIES_NOTE,
    el: el,
    makeSection: makeSection,
    buildErrorLine: buildErrorLine,
    buildLiveLine: buildLiveLine,
    buildEmpty: buildEmpty,
    messageOf: messageOf,
    disableList: disableList,
    restoreDisabled: restoreDisabled,
    restoreOrigin: restoreOrigin,
    makeMutate: makeMutate,
    buildInlineEditor: buildInlineEditor,
    buildDeleteButton: buildDeleteButton
  };
})();
