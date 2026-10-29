// App.studio.renderRoutinesTab -- the agent editor's "Routines" tab (M33 F1 L8, flight DD12).
// Lists the agent's routines (schedule, target, next run, last outcome) with a per-row switch,
// Run now, Delete and a History disclosure. Built with DOM APIs on the control library; every
// string from the server (names, titles, reasons) is written with textContent only.
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

  var POLL_MS = 3000;
  var HISTORY_PAGE = 20;
  var DEFAULT_RUN_TIMEOUT_S = 900;

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
    if (agent.name === 'default') {
      var defNote = shared.buildEmpty('Routines need a named agent.');
      defNote.setAttribute('data-testid', 'routines-default-agent');
      panel.appendChild(defNote);
      return INERT;
    }

    var name = agent.name || '';
    var section = App.ui.section({
      title: 'Routines', titleTag: 'h3', className: 'rules-notes-section', testid: 'routines-section'
    });
    panel.appendChild(section.el);

    var intro = el('p', 'routines-intro',
      'A routine sends a prompt to this agent on a schedule, even while you are away.');
    section.el.appendChild(intro);

    var toolbar = el('div', 'routines-toolbar');
    var newBtn = App.ui.button({
      variant: 'primary', label: 'New routine', testid: 'routines-new-btn',
      onClick: function () { openForm('create', null, newBtn); }
    });
    toolbar.appendChild(newBtn);
    section.el.appendChild(toolbar);

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
    var listEl = el('ul', 'routines-list');
    listEl.setAttribute('role', 'list');
    listEl.setAttribute('aria-label', 'Routines');
    var emptyEl = null;
    var loadingEl = el('p', 'routines-loading', 'Loading\u2026');
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

    function openForm(mode, routine, opener) {
      if (typeof cb.openRoutineForm !== 'function') return;
      if (formPromise && formPromise.focus && formHost.firstChild) { formPromise.focus(); return; }
      var result = cb.openRoutineForm({
        mode: mode, routine: routine, opener: opener, agent: name, panelHost: formHost,
        limits: limits, callbacks: { createRoutine: cb.createRoutine, updateRoutine: cb.updateRoutine }
      });
      formPromise = result;
      Promise.resolve(result).then(function (saved) {
        if (formPromise === result) formPromise = null;
        if (destroyed || saved === false || saved === null || saved === undefined) return;
        var savedId = saved && saved.id ? saved.id : (routine ? routine.id : null);
        return load().then(function () {
          var v = savedId && views[savedId];
          if (v) v.edit.focus();
        });
      }).catch(noop);
    }

    // ── Rows ──────────────────────────────────────────────────────────
    function buildView(r) {
      var v = { id: r.id, row: r, busy: false, starting: false, histLoaded: false, histCursor: null };
      var li = el('li', 'routine-row');
      li.setAttribute('data-testid', 'routine-row');
      li.setAttribute('data-routine-id', r.id);
      v.el = li;

      var head = el('div', 'routine-head');
      v.nameEl = el('span', 'routine-name');
      v.nameEl.setAttribute('data-testid', 'routine-name');
      head.appendChild(v.nameEl);
      // The flag slot (M33 F2 L5): holds an App.ui.noteFlag while the routine is flagged.
      v.flagSlot = el('span', 'routine-flag-slot');
      head.appendChild(v.flagSlot);
      v.toggle = App.ui.toggle({
        label: 'Run on schedule', labelHidden: true, checked: !!r.enabled, testid: 'routine-toggle',
        onChange: function (checked) { onToggle(v, checked); }
      });
      v.toggle.control.setAttribute('data-routine-id', r.id);
      head.appendChild(v.toggle.el);
      li.appendChild(head);

      var info = el('div', 'routine-info');
      v.originEl = el('p', 'routine-line routine-origin', 'Made by the agent');
      v.originEl.setAttribute('data-testid', 'routine-origin');
      v.scheduleEl = el('p', 'routine-line routine-schedule');
      v.scheduleEl.setAttribute('data-testid', 'routine-schedule');
      v.targetEl = el('p', 'routine-line routine-target');
      v.targetEl.setAttribute('data-testid', 'routine-target');
      v.nextEl = el('p', 'routine-line routine-next');
      v.nextEl.setAttribute('data-testid', 'routine-next');
      v.last = App.ui.status({ state: 'idle', live: 'off', testid: 'routine-last' });
      v.last.el.classList.add('routine-line', 'routine-last');
      v.hint = el('p', 'routine-line routine-hint', 'Set a new time to run it again.');
      v.hint.setAttribute('data-testid', 'routine-done-hint');
      info.appendChild(v.originEl);
      info.appendChild(v.scheduleEl);
      info.appendChild(v.targetEl);
      info.appendChild(v.nextEl);
      info.appendChild(v.last.el);
      info.appendChild(v.hint);
      li.appendChild(info);

      v.errorLine = shared.buildErrorLine();
      v.errorLine.el.setAttribute('data-testid', 'routine-error');
      li.appendChild(v.errorLine.el);

      var actions = el('div', 'routine-actions');
      v.runBtn = App.ui.button({
        variant: 'secondary', size: 'sm', label: 'Run now', testid: 'routine-run-now',
        onClick: function () { onRunNow(v); }
      });
      v.edit = App.ui.button({
        variant: 'ghost', size: 'sm', label: 'Edit', testid: 'routine-edit',
        onClick: function () { openForm('edit', v.row, v.edit); }
      });
      v.del = shared.buildDeleteButton({
        ariaLabel: 'Delete routine',
        onConfirm: function (revert) { onDelete(v, revert); }
      });
      v.del.setAttribute('data-testid', 'routine-delete');
      actions.appendChild(v.runBtn);
      actions.appendChild(v.edit);
      actions.appendChild(v.del);
      li.appendChild(actions);

      buildHistory(v);
      li.appendChild(v.history.el);
      return v;
    }

    // Patch a row's text and control states from `v.row` (no rebuild, so focus, an armed
    // Delete and an open History survive a refresh).
    function paint(v) {
      var r = v.row;
      v.nameEl.textContent = r.name || '';
      v.toggle.control.setAttribute('aria-label', 'Run ' + (r.name || '') + ' on schedule');
      v.toggle.setChecked(!!r.enabled);
      var done = !!r.finished_at;
      v.toggle.setDisabled(v.busy || done);
      v.hint.hidden = !done;
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
      v.scheduleEl.textContent = describe.describeSchedule(r.schedule);
      v.targetEl.textContent = describe.describeTarget(r.target);
      v.nextEl.textContent = describe.describeNext(r);
      var st = describe.outcomeStatus(r.last_run, r.running);
      v.last.set(st.state, st.label);
      var runWasFocused = document.activeElement === v.runBtn;
      v.runBtn.disabled = v.busy || v.starting || !!r.running;
      // A disabled button drops focus to the body; keep it in the row instead.
      if (runWasFocused && v.runBtn.disabled) v.toggle.control.focus();
      v.edit.disabled = v.busy;
      v.del.disabled = v.busy;
      // The Delete label follows a rename (leg 9); App.ui.confirm owns it while armed.
      if (v.delLabelFor !== r.name) {
        v.delLabelFor = r.name;
        v.del.setAttribute('aria-label', 'Delete routine ' + (r.name || ''));
      }
      v.runBtn.setAttribute('aria-label', 'Run ' + (r.name || '') + ' now');
      v.edit.setAttribute('aria-label', 'Edit ' + (r.name || ''));
      v.history.summary.setAttribute('aria-label', 'History for ' + (r.name || ''));
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
        if (live) { paint(live); live.toggle.control.focus(); }
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

    function onDelete(v, revert) {
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
          if (nv) nv.toggle.control.focus();
          else if (!newBtn.hidden) newBtn.focus();
        });
      }, function (err) {
        revert();
        v.busy = false;
        setRowError(v, messageOf(err));
        return load().then(noop, noop);
      });
    }

    // ── History ───────────────────────────────────────────────────────
    function buildHistory(v) {
      v.history = App.ui.disclosure({
        variant: 'plain', summary: 'History', testid: 'routine-history',
        onFirstOpen: function () { loadHistory(v, false); }
      });
      v.runsList = el('ul', 'routine-runs');
      v.runsList.setAttribute('role', 'list');
      v.runsList.setAttribute('aria-label', 'Run history');
      v.runsList.setAttribute('data-testid', 'routine-history-list');
      v.histEmpty = el('p', 'routine-line', 'No runs yet.');
      v.histEmpty.setAttribute('data-testid', 'routine-history-empty');
      v.histEmpty.hidden = true;
      v.histError = shared.buildErrorLine();
      v.moreBtn = App.ui.button({
        variant: 'ghost', size: 'sm', label: 'Show older', testid: 'routine-history-more',
        onClick: function () { loadHistory(v, true); }
      });
      v.moreBtn.hidden = true;
      v.history.body.appendChild(v.histError.el);
      v.history.body.appendChild(v.histEmpty);
      v.history.body.appendChild(v.runsList);
      v.history.body.appendChild(v.moreBtn);
    }

    function runEntry(run) {
      var li = el('li', 'routine-run');
      li.setAttribute('data-testid', 'routine-run');
      var st = describe.outcomeStatus(run, false);
      var status = App.ui.status({ state: st.state, text: st.label, live: 'off' });
      status.el.classList.add('routine-run-outcome');
      li.appendChild(status.el);
      var bits = [];
      var trig = describe.describeTrigger(run.trigger_kind);
      if (trig) bits.push(trig);
      var at = run.started_at || run.due_at;
      if (at) bits.push(App.time.formatDateTime(at));
      if (run.new_chat) bits.push('New chat');
      var meta = el('p', 'routine-run-meta', bits.join(' · '));
      li.appendChild(meta);
      return li;
    }

    // First page replaces the list; "Show older" appends the next page.
    function loadHistory(v, older) {
      var mine = older ? v.histGen : (v.histGen = (v.histGen || 0) + 1);
      var before = older ? v.histCursor : null;
      v.histError.show('');
      v.moreBtn.disabled = true;
      return Promise.resolve().then(function () {
        return cb.fetchRoutineRuns(name, v.id, { limit: HISTORY_PAGE, before: before });
      }).then(function (body) {
        if (destroyed || mine !== v.histGen || !views[v.id]) return;
        var runs = (body && body.runs) || [];
        if (!older) v.runsList.textContent = '';
        runs.forEach(function (run) { v.runsList.appendChild(runEntry(run)); });
        v.histLoaded = true;
        var last = runs.length ? runs[runs.length - 1] : null;
        v.histCursor = last ? last.started_at : v.histCursor;
        v.moreBtn.hidden = !(runs.length >= HISTORY_PAGE && last && last.started_at);
        v.histEmpty.hidden = v.runsList.children.length > 0;
      }, function (err) {
        if (!destroyed) v.histError.show('Couldn’t load the history: ' + messageOf(err));
      }).then(function () { v.moreBtn.disabled = false; });
    }

    // ── The list ──────────────────────────────────────────────────────
    function renderEmpty() {
      var none = data.length === 0 && loaded;
      if (none && !emptyEl) {
        var add = App.ui.button({
          variant: 'secondary', label: 'New routine', testid: 'routines-empty-new-btn',
          onClick: function () { openForm('create', null, add); }
        });
        emptyEl = App.ui.emptyState({
          title: 'No routines yet.', titleTag: 'p', variant: 'flush',
          testid: 'routines-empty', action: add
        });
        emptyEl._add = add;
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
        var prevSig = v ? runSig(v.row.last_run) : null;
        if (!v) {
          v = views[r.id] = buildView(r);
        }
        v.row = r;
        paint(v);
        var sig = runSig(r.last_run);
        if (v.histLoaded && v.history.isOpen() && prevSig !== null && prevSig !== sig) {
          loadHistory(v, false);
        }
        settlePending(v);
      });
      Object.keys(views).forEach(function (id) {
        if (seen[id]) return;
        if (views[id].el.parentNode) views[id].el.parentNode.removeChild(views[id].el);
        views[id].history.destroy();
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
      Object.keys(views).forEach(function (id) {
        if (views[id].history.isOpen() && views[id].histLoaded) loadHistory(views[id], false);
      });
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
        Object.keys(views).forEach(function (id) { views[id].history.destroy(); });
      }
    };
  }

  window.App.studio.renderRoutinesTab = renderRoutinesTab;
})();
