(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var NO_TOOLS_TITLE =
    'This model does not support tool calling — agents will run in single-shot chat mode.';

  // The row actions, in DOM and focus-fallback order. `state` is the row state the
  // action is shown for.
  var ACTIONS = [
    { name: 'unload', label: 'Unload', busy: 'Unloading…', state: 'running' },
    { name: 'load', label: 'Load', busy: 'Loading…', state: 'idle' },
    { name: 'delete', label: 'Delete', busy: 'Deleting…', state: 'idle', danger: true }
  ];

  // App.ui.modelList(opts) -> {el, reconcile(sections), setRowBusy(name, action),
  // setRowError(name, message), focusRow(name), destroy()} (M31 F6 L08, flight DD10).
  // A presentational keyed list of models: sections, each row's status dot, mono
  // name, capability chips, size and action buttons, with per-row busy and error
  // states and focus kept across a reconcile. It does no fetching; the area passes
  // data in and handles onAction.
  //   label (the list's accessible name), testid, rowTestid (on every row),
  //   density ('compact' keeps a tight, no-action look for a plain list),
  //   actions (which of 'unload', 'load', 'delete' exist; none by default),
  //   confirmLabel (the armed Delete's label, 'Confirm delete?'),
  //   onAction(name, action): a button click (Delete: its second, confirming click);
  //   the control has already set the row busy, so the area only runs the work and
  //   then calls setRowBusy(name, 'done') (success: the NEXT reconcile ends the busy
  //   state; an in-flight row keeps it through any other reconcile) or
  //   setRowBusy(name, null) (failure: label and button restored, an armed Delete
  //   reverted, focus returned to the button when it held focus and focus is now
  //   nowhere),
  //   onFocusLost(): no row is left to take focus (the area focuses its own control).
  //   sections: [{key, label|null, rows: [{name, state: 'running'|'idle'|null,
  //   caps: [string]|null, size: string|null}]}]. Rows are keyed by name (the first
  //   duplicate wins), moved between sections in place, and carry data-name and
  //   data-section. A row with a state has the status dot (Running / Not running).
  //   Focus: a focused (or held) control stays focused; when its button hides or its
  //   row goes, focus moves to the row's first visible enabled action (Unload, Load,
  //   Delete), then the NEXT row's first action, then the PREVIOUS row's, then
  //   onFocusLost(). A row still mid-action is skipped. An armed Delete survives a
  //   reconcile on the same node; when it hides the arm is reverted.
  //   setRowError(name, message|null) shows (4000 ms auto-clear) or clears the row's
  //   error line.
  //   modelList.capabilityChips(caps) -> span.cap-chip-row or null: a chip per
  //   capability, plus a danger "no tools" chip when `tools` is absent; null for a
  //   missing or empty list (a failed lookup must not imply "no capabilities").
  App.ui.modelList = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var wanted = opts.actions || [];
    var rows = Object.create(null);
    var labels = Object.create(null);
    var order = [];
    var destroyed = false;

    var root = util.el('div', {
      className: 'ui-model-list' + (opts.density === 'compact' ? ' ui-model-list--compact' : ''),
      role: opts.label ? 'group' : null,
      'aria-label': opts.label || null
    });
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    // Every row action is named for its model ("Delete {name}"), the visible label's
    // text first (label in name); `name` is the row's, never read back from the DOM.
    function nameButton(btn, name, text) {
      btn.setAttribute('aria-label', text + ' ' + name);
    }

    function setButtonText(btn, text) {
      if (btn._titleEl) btn._titleEl.textContent = text;
      else btn.textContent = text;
      if (btn._rowName != null) nameButton(btn, btn._rowName, text);
    }

    // Back to the un-armed look without the confirm helper's revert function (the row
    // moved to Running, or the list went away).
    function disarm(btn) {
      if (!btn || !btn.classList.contains('confirm-delete')) return;
      clearTimeout(btn._confirmRevertTimer);
      btn._confirmRevertTimer = null;
      btn.classList.remove('confirm-delete');
      if (btn._titleEl && btn._confirmOriginalTitle != null) {
        btn._titleEl.textContent = btn._confirmOriginalTitle;
      }
      btn._confirmOriginalTitle = null;
      if (btn._rowName != null) nameButton(btn, btn._rowName, btn._actLabel);
    }

    function firstAction(row) {
      for (var i = 0; i < row.btnList.length; i++) {
        var b = row.btnList[i];
        if (!b.hidden && !b.disabled) return b;
      }
      return null;
    }

    function clearRowError(row) {
      clearTimeout(row.errorTimer);
      row.errorTimer = null;
      if (row.errorLine) row.errorLine.el.hidden = true;
    }

    function showRowError(row, message) {
      if (!row.errorLine) {
        row.errorLine = App.ui.status({ state: 'danger', text: message });
        row.errorLine.el.classList.add('ui-model-error');
        row.el.appendChild(row.errorLine.el);
      }
      row.errorLine.set('danger', message);
      row.errorLine.el.hidden = false;
      clearTimeout(row.errorTimer);
      row.errorTimer = setTimeout(function () { clearRowError(row); }, 4000);
    }

    function actionOf(name) {
      for (var i = 0; i < ACTIONS.length; i++) if (ACTIONS[i].name === name) return ACTIONS[i];
      return null;
    }

    // End a row's in-flight action: its button back to its label and enabled.
    function clearBusy(row) {
      var was = row.busy;
      row.busy = null;
      row.busyDone = false;
      var act = was && actionOf(was);
      var btn = act && row.btns[was];
      if (!btn) return;
      btn.disabled = false;
      if (was === 'delete' && row.deleteRevert) {
        row.deleteRevert();
        row.deleteRevert = null;
      }
      setButtonText(btn, act.label);
    }

    function setBusy(row, action) {
      var btn = row.btns[action];
      var act = actionOf(action);
      if (!btn || !act) return;
      row.busy = action;
      row.busyDone = false;
      btn.disabled = true;
      setButtonText(btn, act.busy);
    }

    function startAction(row, action) {
      var btn = row.btns[action];
      clearRowError(row);
      row.heldFocus = document.activeElement === btn;
      row.focusBtn = btn;
      setBusy(row, action);
      if (typeof opts.onAction === 'function') opts.onAction(row.name, action);
    }

    function buildRow(name) {
      var row = {
        name: name,
        section: null,
        busy: null,
        busyDone: false,
        capsKey: null,
        errorLine: null,
        errorTimer: null,
        deleteRevert: null,
        heldFocus: false,
        focusBtn: null,
        led: null,
        btns: {},
        btnList: []
      };
      row.nameEl = util.el('span', { className: 'ui-model-name', text: name, title: name });
      row.capsEl = util.el('span', { className: 'ui-model-caps' });
      row.capsEl.hidden = true;
      row.sizeEl = util.el('span', { className: 'ui-model-size' });
      var actionsEl = util.el('div', { className: 'ui-model-actions' });
      ACTIONS.forEach(function (act) {
        if (wanted.indexOf(act.name) === -1) return;
        var btn = App.ui.button({
          variant: act.danger ? 'danger' : undefined,
          size: 'sm',
          label: act.danger ? undefined : act.label
        });
        btn.setAttribute('data-action', act.name);
        btn._rowName = name;
        btn._actLabel = act.label;
        nameButton(btn, name, act.label);
        if (act.danger) {
          btn._titleEl = util.el('span', { text: act.label });
          btn._titleEl.setAttribute('data-confirm-title', '');
          btn.appendChild(btn._titleEl);
          btn.addEventListener('click', function () {
            App.ui.confirm(btn, function (itemEl, revert) {
              row.deleteRevert = revert;
              startAction(row, 'delete');
            }, {
              confirmLabel: opts.confirmLabel || 'Confirm delete?',
              onArmChange: function (armed) {
                nameButton(btn, name, armed ? (opts.confirmLabel || 'Confirm delete?') : act.label);
              }
            });
          });
        } else {
          btn.addEventListener('click', function () { startAction(row, act.name); });
        }
        row.btns[act.name] = btn;
        row.btnList.push(btn);
        actionsEl.appendChild(btn);
      });
      row.el = util.el('div', { className: 'ui-model-row', 'data-name': name },
        [row.nameEl, row.capsEl, row.sizeEl, actionsEl]);
      if (opts.rowTestid) row.el.setAttribute('data-testid', opts.rowTestid);
      return row;
    }

    // Update a row in place for its section key and data.
    function patchRow(row, key, spec) {
      var state = spec.state || null;
      row.section = key;
      row.el.setAttribute('data-section', key);
      if (state) {
        if (!row.led) {
          row.led = App.ui.status({ state: 'idle', ledLabel: 'Model state', live: 'off' });
          row.led.el.classList.add('ui-model-led');
          row.el.insertBefore(row.led.el, row.el.firstChild);
        }
        row.led.el.hidden = false;
        row.led.set(state === 'running' ? 'success' : 'idle', '',
          { ledLabel: state === 'running' ? 'Running' : 'Not running' });
      } else if (row.led) {
        row.led.el.hidden = true;
      }
      var size = spec.size || '';
      if (row.sizeEl.textContent !== size) row.sizeEl.textContent = size;
      var caps = Array.isArray(spec.caps) ? spec.caps : null;
      var capsKey = caps ? caps.join('\n') : '';
      if (capsKey !== row.capsKey) {
        row.capsKey = capsKey;
        row.capsEl.textContent = '';
        var chips = App.ui.modelList.capabilityChips(caps);
        if (chips) row.capsEl.appendChild(chips);
        row.capsEl.hidden = !chips;
      }
      ACTIONS.forEach(function (act) {
        var btn = row.btns[act.name];
        if (!btn) return;
        var hide = state !== act.state;
        if (hide && !btn.hidden) disarm(btn);
        btn.hidden = hide;
      });
      // The reconcile that follows a finished action ends its busy state. An
      // in-flight action keeps its busy state through any other reconcile.
      if (row.busyDone) clearBusy(row);
    }

    // The row that holds keyboard focus. A button this control just disabled (a row
    // action in flight) drops focus to the body, so such a row remembers it held focus
    // (`heldFocus`); that memory only counts while focus is nowhere.
    function focusedRow() {
      var active = document.activeElement;
      var names = Object.keys(rows);
      var i;
      if (active && active !== document.body) {
        for (i = 0; i < names.length; i++) {
          if (rows[names[i]].el.contains(active)) return { row: rows[names[i]], active: active };
        }
        return null;
      }
      for (i = 0; i < names.length; i++) {
        if (rows[names[i]].heldFocus) return { row: rows[names[i]], active: rows[names[i]].focusBtn };
      }
      return null;
    }

    function lostFocus() {
      if (typeof opts.onFocusLost === 'function') opts.onFocusLost();
    }

    function restoreFocus(row, active, oldOrder, present) {
      if (present[row.name]) {
        // A hidden button may still be the active element (WebKit keeps it), so test
        // usability first.
        if (active && active.isConnected && !active.hidden && !active.disabled) {
          if (document.activeElement !== active) active.focus();
          return;
        }
        var action = firstAction(row);
        if (action) action.focus();
        return;
      }
      // The row is gone: the next row's first action, then the previous row's.
      var at = oldOrder.indexOf(row.name);
      var i;
      for (i = at + 1; i < oldOrder.length; i++) {
        if (present[oldOrder[i]]) {
          var after = firstAction(rows[oldOrder[i]]);
          if (after) { after.focus(); return; }
        }
      }
      for (i = at - 1; i >= 0; i--) {
        if (present[oldOrder[i]]) {
          var before = firstAction(rows[oldOrder[i]]);
          if (before) { before.focus(); return; }
        }
      }
      lostFocus();
    }

    function dropRow(name) {
      var row = rows[name];
      clearRowError(row);
      for (var i = 0; i < row.btnList.length; i++) disarm(row.btnList[i]);
      delete rows[name];
    }

    function reconcile(sections) {
      if (destroyed) return;
      var focused = focusedRow();
      var oldOrder = order;
      var present = Object.create(null);
      var desired = [];
      var names = [];
      var list = sections || [];
      for (var s = 0; s < list.length; s++) {
        var sec = list[s];
        var secRows = [];
        var specs = sec.rows || [];
        for (var r = 0; r < specs.length; r++) {
          var name = specs[r].name;
          if (!name || present[name]) continue;
          var row = rows[name];
          if (!row) {
            row = buildRow(name);
            rows[name] = row;
          }
          present[name] = true;
          patchRow(row, sec.key, specs[r]);
          secRows.push(row);
        }
        if (!secRows.length) continue;
        if (sec.label) {
          var lab = labels[sec.key];
          if (!lab) {
            lab = util.el('div', { className: 'ui-model-section-label' });
            labels[sec.key] = lab;
          }
          if (lab.textContent !== sec.label) lab.textContent = sec.label;
          desired.push(lab);
        }
        for (var k = 0; k < secRows.length; k++) {
          desired.push(secRows[k].el);
          names.push(secRows[k].name);
        }
      }
      Object.keys(rows).forEach(function (n) { if (!present[n]) dropRow(n); });
      util.syncChildren(root, desired);
      order = names;
      // A row still mid-action keeps its focus memory for the reconcile that ends it.
      if (focused && !(present[focused.row.name] && focused.row.busy && !focused.row.busyDone)) {
        restoreFocus(focused.row, focused.active, oldOrder, present);
        focused.row.heldFocus = false;
      }
    }

    function setRowBusy(name, action) {
      var row = rows[name];
      if (!row) return;
      if (action === 'done') {
        if (row.busy) row.busyDone = true;
        return;
      }
      if (action) {
        setBusy(row, action);
        return;
      }
      var btn = row.busy ? row.btns[row.busy] : null;
      clearBusy(row);
      if (btn && row.heldFocus &&
          (!document.activeElement || document.activeElement === document.body)) {
        btn.focus();
      }
      row.heldFocus = false;
    }

    function setRowError(name, message) {
      var row = rows[name];
      if (!row) return;
      if (message) showRowError(row, message);
      else clearRowError(row);
    }

    function focusRow(name) {
      var row = rows[name];
      var btn = row ? firstAction(row) : null;
      if (!btn) return false;
      btn.focus();
      return true;
    }

    function destroy() {
      destroyed = true;
      Object.keys(rows).forEach(dropRow);
      order = [];
    }

    return {
      el: root,
      reconcile: reconcile,
      setRowBusy: setRowBusy,
      setRowError: setRowError,
      focusRow: focusRow,
      destroy: destroy
    };
  };

  App.ui.modelList.capabilityChips = function (caps) {
    if (!Array.isArray(caps) || caps.length === 0) return null;
    var row = App.ui.util.el('span', { className: 'cap-chip-row' });
    for (var i = 0; i < caps.length; i++) {
      row.appendChild(App.ui.chip({ label: caps[i], size: 'sm' }));
    }
    if (caps.indexOf('tools') === -1) {
      row.appendChild(App.ui.chip({
        label: 'no tools',
        tone: 'danger',
        size: 'sm',
        title: NO_TOOLS_TITLE
      }));
    }
    return row;
  };
})();
