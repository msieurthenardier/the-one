// App.studio.renderRoutinesTab -- the agent editor's "Routines" tab (M33 F1 L8, flight DD12;
// the list is cards of M33 F4, built as the Tools tab's). Lists the agent's routines as
// App.ui.groupTile cards: the enable switch, name, flag and an actions menu (Run now, Edit,
// Delete) on top, the schedule and the next and last runs under it, and a "Details" expander
// at the bottom (the prompt and the recent runs, routines-row-details.js).
// Built with DOM APIs on the control library; every string from the server (names, titles,
// reasons) is written with textContent only.
//
// Save model (as the Rules tab): every action saves at once through the REST API, then
// refetches. Nothing here joins General's dirty state or App.nav.
//
// Lifecycle: the handle is {setAgent, activate, deactivate, destroy}. The tab makes no request
// until activate() (the editor calls it on a mount that opens on this tab, and on each switch
// to it); both are idempotent. While active, the tab is visible and a run is going (a row
// `running`, or a Run now not yet seen to finish), it refetches every 3 seconds; it also
// refetches when the document becomes visible. deactivate() stops the timer; destroy() drops
// the App.time and visibilitychange listeners as well.
//
// New routine and Edit call callbacks.openRoutineForm({mode, routine, opener, agent,
// panelHost, limits, callbacks}) (the form is routines-form.js, M33 F1 L9), which returns a
// promise that resolves with the saved routine (null on Cancel). The form sits in `formHost`
// above the list and is discarded when the tab is left.
//
// callbacks: {
//   fetchRoutines(name)              -> Promise<{routines, limits}>
//   updateRoutine(name, id, patch)   -> Promise<routine>
//   deleteRoutine(name, id)          -> Promise
//   runRoutine(name, id)             -> Promise   (202; a 409 error has status 409)
//   fetchRoutineRuns(name, id, opts) -> Promise<{runs}>   opts: {limit, before}
//   createRoutine(name, body)        -> Promise<routine>
//   openRoutineForm(req)             -> Promise<routine|null>  (the promise has close()/focus())
// }
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var shared = window.App.studio.rulesNotesShared;
  var el = shared.el;
  var messageOf = shared.messageOf;
  var describe = window.App.studio.routinesDescribe;
  var rowDetails = window.App.studio.routinesRowDetails;

  var POLL_MS = 3000;
  var DEFAULT_RUN_TIMEOUT_S = 900;
  // The actions menu's items, by index (the menu's setItemDisabled addresses them).
  var ITEM_RUN = 0;
  var ITEM_EDIT = 1;
  var ITEM_DELETE = 2;

  function noop() {}
  var INERT = { setAgent: noop, activate: noop, deactivate: noop, destroy: noop };

  function runSig(run) {
    return run ? [run.outcome, run.finished_at, run.session_id].join('|') : '';
  }

  function renderRoutinesTab(panel, agent, callbacks) {
    var cb = callbacks || {};
    panel.textContent = '';
    if (!agent) {
      var saveFirst = shared.buildEmpty('Save the agent first to add routines.');
      saveFirst.setAttribute('data-testid', 'routines-save-first');
      panel.appendChild(saveFirst);
      return INERT;
    }

    var name = agent.name || '';
    var section = App.ui.section({
      title: 'Routines', titleTag: 'h3', className: 'rules-notes-section', testid: 'routines-section'
    });
    panel.appendChild(section.el);

    var head = el('div', 'routines-head');
    head.appendChild(el('p', 'routines-intro',
      'A routine sends a prompt to this agent on a schedule. Each run starts a new chat.'));
    var newBtn = App.ui.button({
      variant: 'primary', label: 'New routine', testid: 'routines-new-btn',
      onClick: function () { openForm('create', null, newBtn); }
    });
    head.appendChild(newBtn);
    section.el.appendChild(head);

    var errorLine = shared.buildErrorLine();
    errorLine.el.setAttribute('data-testid', 'routines-error');
    section.el.appendChild(errorLine.el);
    // Polite status for a Run now: one line at the start, one when that run finishes.
    var liveLine = shared.buildLiveLine();
    liveLine.el.setAttribute('data-testid', 'routines-live');
    section.el.appendChild(liveLine.el);

    var formHost = el('div', 'routines-form-host');
    section.el.appendChild(formHost);
    var formPromise = null;

    var listWrap = el('div', 'routines-list-wrap');
    section.el.appendChild(listWrap);
    // The routine cards, one App.ui.groupTile each. Nothing clips the list (no overflow rule),
    // so a card's open actions menu is never cut off at the last card.
    var listEl = el('div', 'routines-list');
    listEl.setAttribute('role', 'list');
    listEl.setAttribute('aria-label', 'Routines');
    listEl.hidden = true;
    var emptyEl = null;
    var loadingEl = el('p', 'routines-loading', 'Loading…');
    listWrap.appendChild(loadingEl);

    var views = {};          // id -> row view
    var data = [];           // the latest routines, sorted by name
    var limits = {};
    var gen = 0;
    var active = false;
    var destroyed = false;
    var loaded = false;
    var pollTimer = null;
    var pending = {};        // id -> {until, base}: a Run now not yet seen to finish

    function showError(msg) { errorLine.show(msg); }

    // ── New / Edit ────────────────────────────────────────────────────
    function closeForm() {
      var p = formPromise;
      formPromise = null;
      if (p && p.close) p.close();
    }

    // New routine keeps its form at the top of the list. Edit swaps that routine's card for
    // the form in the card's own slot (the card is hidden, so its menu is unreachable); Save
    // and Cancel bring the card back in place. One form at a time: opening another (New or
    // Edit) while one is open focuses the open one and changes nothing.
    function openForm(mode, routine, opener) {
      if (typeof cb.openRoutineForm !== 'function') return;
      if (formPromise && formPromise.focus) { formPromise.focus(); return; }
      var editing = mode === 'edit' && routine && views[routine.id] ? views[routine.id] : null;
      var host = editing ? editing.editHost : formHost;
      if (editing) editing.tile.el.hidden = true;
      var result = cb.openRoutineForm({
        mode: mode, routine: routine, opener: opener, agent: name, panelHost: host,
        limits: limits, callbacks: { createRoutine: cb.createRoutine, updateRoutine: cb.updateRoutine }
      });
      formPromise = result;
      Promise.resolve(result).then(function (saved) {
        if (formPromise === result) formPromise = null;
        if (editing) {
          editing.tile.el.hidden = false;
          // Cancel: the form gave focus back to a control that was hidden at that moment.
          if (active && !destroyed && (!document.activeElement || document.activeElement === document.body)) {
            editing.menu.trigger.focus();
          }
        }
        if (destroyed || saved === false || saved === null || saved === undefined) return;
        var savedId = saved && saved.id ? saved.id : (routine ? routine.id : null);
        return load().then(function () {
          var v = savedId && views[savedId];
          if (v) v.menu.trigger.focus();
        });
      }).catch(noop);
    }

    // ── Rows ──────────────────────────────────────────────────────────
    // A routine is one App.ui.groupTile card, as the Tools tab's categories: the enable switch,
    // the name (and the "Made by the agent" chip), the flag and the "⋯" menu on the title row;
    // the schedule and the next and last runs under it; the "Details" expander at the bottom,
    // whose body is the prompt and the recent runs.
    function buildView(r) {
      var v = { id: r.id, row: r, busy: false, starting: false };

      v.details = rowDetails.create({
        fetchRuns: function (opts) { return cb.fetchRoutineRuns(name, v.id, opts); }
      });

      // The flag slot (M33 F2 L5): holds an App.ui.noteFlag while the routine is flagged.
      v.flagSlot = el('span', 'routine-flag-slot');

      var sub = el('div', 'routine-sub');
      v.scheduleEl = el('p', 'routine-schedule');
      v.scheduleEl.setAttribute('data-testid', 'routine-schedule');
      sub.appendChild(v.scheduleEl);
      var times = el('p', 'routine-times');
      times.appendChild(document.createTextNode('Next run: '));
      v.nextEl = el('span', 'routine-next');
      v.nextEl.setAttribute('data-testid', 'routine-next');
      times.appendChild(v.nextEl);
      var dot = el('span', 'routine-times-dot', '·');
      dot.setAttribute('aria-hidden', 'true');
      times.appendChild(dot);
      times.appendChild(document.createTextNode('Last run: '));
      v.last = App.ui.status({ state: 'idle', live: 'off', testid: 'routine-last' });
      v.last.el.classList.add('routine-last');
      times.appendChild(v.last.el);
      sub.appendChild(times);

      v.menu = App.ui.menu({
        trigger: {
          variant: 'ghost', size: 'sm', iconOnly: true, icon: 'more', ariaLabel: 'Actions',
          testid: 'routine-actions'
        },
        align: 'end', testid: 'routine-menu',
        items: [
          { label: 'Run now', icon: 'play', testid: 'routine-run-now', onSelect: function () { onRunNow(v); } },
          { label: 'Edit', icon: 'edit', testid: 'routine-edit',
            onSelect: function () { openForm('edit', v.row, v.menu.trigger); } },
          { label: 'Delete', icon: 'trash', danger: true, testid: 'routine-delete',
            onSelect: function () { askDelete(v); } }
        ]
      });
      v.tile = App.ui.groupTile({
        name: r.name || '',
        testid: 'routine-row',
        dataset: { routineId: r.id },
        master: {
          label: 'Enable ' + (r.name || ''), tristate: false, state: r.enabled ? 'on' : 'off',
          testid: 'routine-toggle', dataset: { routineId: r.id },
          onChange: function (checked) { onToggle(v, checked); }
        },
        actions: [v.flagSlot, v.menu.el],
        subtitle: sub,
        toolLabel: 'Details',
        expandLabel: function () { return 'Details for ' + (v.row.name || 'routine'); },
        expandTestid: 'routine-details-toggle',
        bodyTestid: 'routine-details',
        onExpand: function (open) { v.details.setOpen(open); }
      });
      // The list item holds the card and, while it is edited, the form in its place.
      v.el = el('div', 'routine-item');
      v.el.setAttribute('role', 'listitem');
      v.editHost = el('div', 'routine-edit-host');
      v.el.appendChild(v.tile.el);
      v.el.appendChild(v.editHost);
      v.nameEl = v.tile.nameEl;
      v.nameEl.setAttribute('data-testid', 'routine-name');
      // The master's switch, for the paint-time state the tile has no setter for.
      v.toggleInput = v.tile.toggle.control;
      v.expandBtn = v.tile.expandBtn;
      v.tile.body.id = App.ui.util.uid('routine-details');
      v.expandBtn.setAttribute('aria-controls', v.tile.body.id);
      v.originEl = App.ui.chip({ label: 'Made by the agent', size: 'sm', testid: 'routine-origin' });
      v.nameEl.parentNode.insertBefore(v.originEl, v.nameEl.nextSibling);
      v.tile.body.appendChild(v.details.el);

      v.errorLine = shared.buildErrorLine();
      v.errorLine.el.setAttribute('data-testid', 'routine-error');
      v.errorLine.el.classList.add('routine-row-error');
      v.tile.el.insertBefore(v.errorLine.el, v.expandBtn);
      return v;
    }

    // Patch a row's text and control states from `v.row` (no rebuild, so focus, an open
    // menu and an open details region survive a refresh).
    function paint(v) {
      var r = v.row;
      var rname = r.name || '';
      v.nameEl.textContent = rname;
      v.toggleInput.setAttribute('aria-label', 'Enable ' + rname);
      var done = !!r.finished_at;
      // A Done routine cannot run: its switch stays, disabled and off, with the reason.
      v.tile.setMaster(r.enabled && !done ? 'on' : 'off');
      v.tile.setToolCount('Details');   // re-applies the expand button's "Details for {name}"
      v.tile.toggle.setDisabled(v.busy || done);
      if (done) {
        if (!v.doneNote) {
          v.doneNote = el('span', 'visually-hidden', 'Done: edit the schedule to run it again.');
          v.doneNote.id = App.ui.util.uid('routine-done');
          v.el.appendChild(v.doneNote);
        }
        v.toggleInput.setAttribute('aria-describedby', v.doneNote.id);
      } else {
        v.toggleInput.removeAttribute('aria-describedby');
      }
      v.originEl.hidden = r.created_by !== 'agent';
      var flagSig = r.untrusted ? JSON.stringify(r.untrusted_sources || []) : '';
      if (v.flagSig !== flagSig) {
        v.flagSig = flagSig;
        v.flagSlot.textContent = '';
        if (r.untrusted) {
          var flag = App.ui.noteFlag({ subject: 'routine', sources: r.untrusted_sources || [] });
          flag.setAttribute('data-testid', 'routine-flag');
          v.flagSlot.appendChild(flag);
        }
      }
      v.scheduleEl.textContent = r.schedule_text || '';
      v.nextEl.textContent = describe.describeNext(r);
      v.nextEl.title = done ? 'Edit the schedule to run it again.' : '';
      var st = describe.outcomeStatus(r.last_run, r.running);
      v.last.set(st.state, st.label);   // the stored reason is in the details' run list
      v.menu.trigger.setAttribute('aria-label', 'Actions for ' + rname);
      v.menu.popup.setAttribute('aria-label', 'Actions for ' + rname);
      v.menu.setItemDisabled(ITEM_RUN, v.busy || v.starting || !!r.running || done);
      v.menu.setItemDisabled(ITEM_EDIT, v.busy);
      v.menu.setItemDisabled(ITEM_DELETE, v.busy);
      v.details.update(r);
    }

    function setRowError(v, msg) { v.errorLine.show(msg); }

    // ── Actions ───────────────────────────────────────────────────────
    function onToggle(v, checked) {
      if (v.busy) return;
      setRowError(v, '');
      v.busy = true;
      paint(v);
      Promise.resolve().then(function () {
        return cb.updateRoutine(name, v.id, { enabled: checked });
      }).then(null, function (err) {
        setRowError(v, messageOf(err));
      }).then(function () {
        v.busy = false;
        return load().then(noop, noop);
      }).then(function () {
        var live = views[v.id];
        if (live) { paint(live); live.toggleInput.focus(); }
      });
    }

    function onRunNow(v) {
      if (v.busy || v.starting) return;
      setRowError(v, '');
      v.starting = true;
      paint(v);
      var timeout = (limits.run_timeout_seconds || DEFAULT_RUN_TIMEOUT_S) + 30;
      pending[v.id] = { until: Date.now() + timeout * 1000, base: runSig(v.row.last_run) };
      Promise.resolve().then(function () {
        return cb.runRoutine(name, v.id);
      }).then(function () {
        liveLine.announce('Started ' + (v.row.name || 'routine'));
        return null;
      }, function (err) {
        if (err && err.status === 409) {
          setRowError(v, 'This routine is already running.');
        } else {
          delete pending[v.id];
          setRowError(v, messageOf(err));
        }
      }).then(function () {
        v.starting = false;
        return load().then(noop, noop);
      });
    }

    // Delete asks first; Cancel or Escape returns focus to the row's actions button.
    function askDelete(v) {
      App.confirmDialog({
        title: 'Delete ' + (v.row.name || 'this routine') + '?',
        message: 'Its run history goes with it. The chats its runs started stay.',
        confirmText: 'Delete', cancelText: 'Cancel', danger: true, opener: v.menu.trigger,
        onConfirm: function () { onDelete(v); }
      });
    }

    function onDelete(v) {
      if (v.busy) return;
      setRowError(v, '');
      var idx = data.findIndex(function (x) { return x.id === v.id; });
      var neighbour = data[idx + 1] || data[idx - 1] || null;
      v.busy = true;
      paint(v);
      Promise.resolve().then(function () {
        return cb.deleteRoutine(name, v.id);
      }).then(function () {
        delete pending[v.id];
        return load().then(noop, noop).then(function () {
          var nv = neighbour && views[neighbour.id];
          if (nv) nv.expandBtn.focus();
          else if (!newBtn.hidden) newBtn.focus();
        });
      }, function (err) {
        v.busy = false;
        setRowError(v, messageOf(err));
        paint(v);
        return load().then(noop, noop);
      });
    }

    // ── The list ──────────────────────────────────────────────────────
    function renderEmpty() {
      var none = data.length === 0 && loaded;
      if (none && !emptyEl) {
        emptyEl = App.ui.emptyState({
          title: 'No routines yet.', titleTag: 'p', variant: 'flush',
          testid: 'routines-empty'
        });
        listWrap.insertBefore(emptyEl, listWrap.firstChild);
      } else if (!none && emptyEl) {
        listWrap.removeChild(emptyEl);
        emptyEl = null;
      }
      listEl.hidden = data.length === 0;
    }

    function apply(body) {
      var rows = ((body && body.routines) || []).slice().sort(function (a, b) {
        return String(a.name).toLowerCase() < String(b.name).toLowerCase() ? -1 :
          String(a.name).toLowerCase() > String(b.name).toLowerCase() ? 1 : 0;
      });
      if (body && body.limits) limits = body.limits;
      data = rows;
      loaded = true;
      if (loadingEl.parentNode) loadingEl.parentNode.removeChild(loadingEl);
      var seen = {};
      rows.forEach(function (r) {
        seen[r.id] = true;
        var v = views[r.id];
        if (!v) {
          v = views[r.id] = buildView(r);
        }
        v.row = r;
        paint(v);
        settlePending(v);
      });
      Object.keys(views).forEach(function (id) {
        if (seen[id]) return;
        var gone = views[id];
        // A routine removed under the operator (the agent cancelled it): focus must not fall
        // to the body.
        if (gone.el.contains(document.activeElement)) newBtn.focus();
        // The agent cancelled the routine under an open edit form: the form goes with it.
        if (formPromise && gone.editHost.firstChild) closeForm();
        if (gone.el.parentNode) gone.el.parentNode.removeChild(gone.el);
        gone.menu.destroy();
        gone.tile.destroy();
        gone.details.destroy();
        delete views[id];
        delete pending[id];
      });
      // Order: only move nodes that are out of place.
      rows.forEach(function (r, i) {
        var node = views[r.id].el;
        if (listEl.children[i] !== node) listEl.insertBefore(node, listEl.children[i] || null);
      });
      if (!listEl.parentNode) listWrap.appendChild(listEl);
      renderEmpty();
      schedulePoll();
    }

    function settlePending(v) {
      var p = pending[v.id];
      if (!p) return;
      var r = v.row;
      if (Date.now() > p.until) { delete pending[v.id]; return; }
      if (!r.running && !v.starting && r.last_run && r.last_run.outcome !== 'running' &&
          runSig(r.last_run) !== p.base) {
        delete pending[v.id];
        liveLine.announce((r.name || 'Routine') + ': ' + describe.outcomeStatus(r.last_run, false).label);
      }
    }

    function load() {
      var mine = ++gen;
      return Promise.resolve().then(function () {
        return cb.fetchRoutines(name);
      }).then(function (body) {
        if (destroyed || mine !== gen) return;
        apply(body);
        if (!loaded) loaded = true;
      }, function (err) {
        if (destroyed || mine !== gen) return;
        // A 404 means the agent is already going away: the editor is closing.
        if (err && err.status === 404) return;
        if (!loaded) showError('Couldn’t load routines: ' + messageOf(err));
        else showError(messageOf(err));
        throw err;
      });
    }

    // ── Polling ───────────────────────────────────────────────────────
    function needsPoll() {
      var now = Date.now();
      for (var i = 0; i < data.length; i++) {
        if (data[i].running) return true;
        var p = pending[data[i].id];
        if (p && now <= p.until) return true;
      }
      return false;
    }

    function stopPoll() {
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    }

    function schedulePoll() {
      stopPoll();
      if (!active || destroyed || document.hidden || !needsPoll()) return;
      pollTimer = setTimeout(function () {
        pollTimer = null;
        if (!active || destroyed || document.hidden) return;
        load().then(noop, function () { schedulePoll(); });
      }, POLL_MS);
    }

    function onVisibility() {
      if (!active || destroyed || document.hidden) return;
      load().then(noop, noop);
    }
    document.addEventListener('visibilitychange', onVisibility);

    var offTime = App.time.onChange(function () {
      if (destroyed) return;
      data.forEach(function (r) { if (views[r.id]) paint(views[r.id]); });
      Object.keys(views).forEach(function (id) { views[id].details.reload(); });
    }, panel);

    // ── The handle ────────────────────────────────────────────────────
    return {
      // A same-identity update only swaps the reference: no refetch, no reset.
      setAgent: function (a) { if (a && a.name === name) agent = a; },
      activate: function () {
        if (destroyed || active) return;
        active = true;
        load().then(noop, noop);
      },
      deactivate: function () {
        active = false;
        stopPoll();
        closeForm();
      },
      destroy: function () {
        destroyed = true;
        active = false;
        stopPoll();
        closeForm();
        gen++;
        document.removeEventListener('visibilitychange', onVisibility);
        if (offTime) offTime();
        Object.keys(views).forEach(function (id) {
          views[id].menu.destroy();
          views[id].tile.destroy();
          views[id].details.destroy();
        });
      }
    };
  }

  window.App.studio.renderRoutinesTab = renderRoutinesTab;
})();
