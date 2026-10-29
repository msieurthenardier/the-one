// App.studio.selfConfigRoutines -- the Self-configuration tab's "Routines" item (M33 F2 L5):
// the two switches (let this agent manage its routines; require approval for its changes), the
// "Waiting for approval" queue (self-config-routines-queue.js) and the read-only "Changes by the
// agent" history. `build(ctx)` appends one section to `ctx.panel` and publishes
// `ctx.refetchRoutines()` (the item, the pending list and the first history page, patched in
// place) and `ctx.routinesAnnounce(text)`. Per-mount state lives on `ctx` (`routinesSeq`), never
// at module level; a response is applied only while the mount is alive and no newer refetch
// has started. Every text goes through textContent.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var PAGE = 20;
  var HISTORY_STATUSES = ['applied', 'dismissed', 'superseded'];

  function el(tag, attrs, children) { return App.ui.util.el(tag, attrs, children); }
  function msg(err) { return err && err.message ? err.message : String(err); }

  // A page of resolved proposals, newest first: one request per resolved status, merged (the
  // route filters one status at a time). Returns {rows, more}.
  function fetchHistoryPage(ctx, before) {
    var cb = ctx.callbacks;
    return Promise.all(HISTORY_STATUSES.map(function (status) {
      return cb.fetchRoutineProposals(ctx.agent.name, { status: status, limit: PAGE + 1, before: before });
    })).then(function (results) {
      var rows = [];
      results.forEach(function (r) { rows = rows.concat((r && r.proposals) || []); });
      rows.sort(function (a, b) {
        if (a.created_at !== b.created_at) return a.created_at < b.created_at ? 1 : -1;
        return a.id < b.id ? 1 : -1;
      });
      return { rows: rows.slice(0, PAGE), more: rows.length > PAGE };
    });
  }

  function build(ctx) {
    var cb = ctx.callbacks;
    var queueMod = window.App.studio.selfConfigRoutinesQueue;
    ctx.routinesSeq = 0;
    ctx.routinesSection = App.ui.section({
      title: 'Routines', titleTag: 'h3', className: 'self-config-routines-section'
    });
    ctx.panel.appendChild(ctx.routinesSection.el);
    var body = ctx.routinesSection.body;

    // The reserved `default` agent has no routines: a note, no switches.
    if (ctx.agent.name === 'default') {
      body.appendChild(App.ui.emptyState({
        title: 'Routines need a named agent.', titleTag: 'p', variant: 'plain',
        testid: 'self-config-routines-default-agent'
      }));
      ctx.refetchRoutines = function () { return Promise.resolve(); };
      ctx.routinesAnnounce = function () {};
      return;
    }

    body.appendChild(el('p', { className: 'self-configuration-description',
      text: 'Let this agent list, schedule, change and cancel its own routines, including ones ' +
        'you made. With approval on, each change waits for you here.' }));

    var errorLine = App.ui.status({ state: 'danger', led: false, role: 'alert', testid: 'self-config-routines-error' });
    errorLine.el.classList.add('self-configuration-error');
    errorLine.el.hidden = true;

    var enableStatus = App.ui.status({ state: 'idle', text: 'Loading…', led: false, testid: 'self-config-routines-status' });
    enableStatus.el.classList.add('self-configuration-status');
    var enableCtl = App.ui.toggle({
      label: 'Let this agent manage its routines', testid: 'self-config-routines-toggle', disabled: true
    });
    enableCtl.el.classList.add('self-configuration-toggle-switch');
    var approvalStatus = App.ui.status({ state: 'idle', text: 'Loading…', led: false, testid: 'self-config-routines-approval-status' });
    approvalStatus.el.classList.add('self-configuration-status');
    var approvalCtl = App.ui.toggle({
      label: 'Require approval for routine changes', testid: 'self-config-routines-approval-toggle', disabled: true
    });
    approvalCtl.el.classList.add('self-configuration-toggle-switch');
    var live = App.ui.status({ state: 'idle', text: '', led: false, testid: 'self-config-routines-live' });
    live.el.classList.add('self-config-routines-live');

    body.appendChild(enableCtl.el);
    body.appendChild(enableStatus.el);
    body.appendChild(approvalCtl.el);
    body.appendChild(approvalStatus.el);
    body.appendChild(errorLine.el);
    body.appendChild(live.el);

    queueMod.build(ctx);

    // ── history ("Changes by the agent") ────────────────────────────────
    body.appendChild(el('h4', { className: 'self-config-routines-subheading', text: 'Changes by the agent' }));
    var historyList = el('ul', { className: 'self-config-routine-history' });
    historyList.setAttribute('role', 'list');
    historyList.setAttribute('data-testid', 'self-config-routine-history');
    body.appendChild(historyList);
    var historyEmpty = el('p', { className: 'self-configuration-description', text: 'No changes yet.' });
    historyEmpty.setAttribute('data-testid', 'self-config-routine-history-empty');
    body.appendChild(historyEmpty);
    var olderBtn = App.ui.button({
      variant: 'secondary', size: 'sm', label: 'Show older', testid: 'self-config-routine-history-older'
    });
    olderBtn.hidden = true;
    body.appendChild(olderBtn);

    var historyViews = {};
    var older = [];          // rows loaded by "Show older", below the first page
    var cursor = null;       // created_at of the last row shown, for the next page
    var hasMore = false;
    var tailMore = false;    // whether more lies beyond the "Show older" rows
    var firstPage = [];      // the latest first page

    function buildHistoryRow(p) {
      var li = el('li', { className: 'self-config-routine-history-row' });
      li.setAttribute('data-testid', 'self-config-routine-history-row');
      li.setAttribute('data-id', p.id);
      li.setAttribute('data-status', p.status);
      li.appendChild(queueMod.buildHead(p));
      var st = el('span', { className: 'self-config-routine-status', text: queueMod.statusWord(p.status) });
      st.setAttribute('data-testid', 'self-config-routine-history-status');
      li.appendChild(st);
      return { id: p.id, el: li };
    }

    function renderHistory(first, more) {
      firstPage = first;
      var seen = {};
      var rows = first.concat(older.filter(function (r) { return !first.some(function (f) { return f.id === r.id; }); }));
      rows = rows.filter(function (r) { if (seen[r.id]) return false; seen[r.id] = true; return true; });
      queueMod.reconcile(historyList, rows, historyViews, buildHistoryRow);
      historyEmpty.hidden = rows.length > 0;
      historyList.hidden = rows.length === 0;
      cursor = rows.length ? rows[rows.length - 1].created_at : null;
      hasMore = more;
      olderBtn.hidden = !hasMore;
    }

    // Focus must never be left on body after the Show older button disabled itself: fall back to
    // the button (visible, enabled), else the history list. Never steals focus the user moved.
    function settleFocus() {
      var a = document.activeElement;
      if (a && a !== document.body) return;
      if (!olderBtn.hidden && !olderBtn.disabled) { olderBtn.focus(); return; }
      historyList.tabIndex = -1;
      historyList.focus();
    }

    olderBtn.onclick = function () {
      if (!cursor) return;
      var seq = ctx.routinesSeq;
      olderBtn.disabled = true;
      fetchHistoryPage(ctx, cursor).then(function (page) {
        if (ctx.destroyed) return;
        if (seq !== ctx.routinesSeq) {
          // A refetch landed mid-load and re-rendered; the button must not stay stuck disabled.
          olderBtn.disabled = false;
          settleFocus();
          return;
        }
        older = older.concat(page.rows);
        tailMore = page.more;
        renderHistory(firstPage, page.more);
        olderBtn.disabled = false;
        var firstNew = page.rows.length && historyViews[page.rows[0].id];
        if (firstNew) { firstNew.el.tabIndex = -1; firstNew.el.focus(); }
        settleFocus();
        ctx.routinesAnnounce(page.rows.length + (page.rows.length === 1 ? ' older change shown.' : ' older changes shown.'));
      }, function (e) {
        if (ctx.destroyed) return;
        olderBtn.disabled = false;
        showError('Could not load older changes: ' + msg(e));
        settleFocus();
      });
    };

    // ── switches ────────────────────────────────────────────────────────
    var state = { enabled: false, requires_approval: true, pending_count: 0 };
    var withdrawn = false;

    function showError(text) {
      errorLine.el.hidden = !text;
      errorLine.set('danger', text || '');
    }

    function paintSwitches() {
      enableStatus.set('idle', (state.enabled
        ? 'On: this agent can manage its routines.'
        : 'Off: this agent has no routine tools.') + (withdrawn && !state.enabled ? ' Pending changes were withdrawn.' : ''));
      approvalStatus.set('idle', state.requires_approval
        ? 'Approval is on: changes wait for you.'
        : 'Approval is off: changes apply at once.');
      enableCtl.setChecked(state.enabled);
      approvalCtl.setChecked(state.requires_approval);
      enableCtl.setDisabled(false);
      approvalCtl.setDisabled(false);
    }

    function put(patch, ctl, previous) {
      if (!cb.putRoutinesItem) { ctl.setChecked(previous); return; }
      showError('');
      enableCtl.setDisabled(true);
      approvalCtl.setDisabled(true);
      cb.putRoutinesItem(ctx.agent.name, patch).then(function (view) {
        if (ctx.destroyed) return;
        var wasPending = state.pending_count;
        state = { enabled: !!view.enabled, requires_approval: !!view.requires_approval, pending_count: view.pending_count || 0 };
        withdrawn = patch.enabled === false && wasPending > 0;
        if (withdrawn) ctx.routinesAnnounce('Pending changes were withdrawn.');
        paintSwitches();
        refetchRoutines();
      }, function (e) {
        if (ctx.destroyed) return;
        ctl.setChecked(previous);
        showError('Could not change this: ' + msg(e));
        enableCtl.setDisabled(false);
        approvalCtl.setDisabled(false);
      });
    }
    enableCtl.control.onchange = function () {
      put({ enabled: enableCtl.control.checked }, enableCtl, state.enabled);
    };
    approvalCtl.control.onchange = function () {
      put({ requires_approval: approvalCtl.control.checked }, approvalCtl, state.requires_approval);
    };

    ctx.routinesAnnounce = function (text) {
      if (ctx.destroyed) return;
      live.set('idle', text);
    };

    // ── refetch ─────────────────────────────────────────────────────────
    function refetchRoutines() {
      var seq = ++ctx.routinesSeq;
      function alive() { return !ctx.destroyed && seq === ctx.routinesSeq; }
      if (!cb.fetchRoutinesItem || !cb.fetchRoutineProposals) return Promise.resolve();
      return Promise.all([
        cb.fetchRoutinesItem(ctx.agent.name),
        cb.fetchRoutineProposals(ctx.agent.name, { status: 'pending', limit: 200 }),
        fetchHistoryPage(ctx, null)
      ]).then(function (res) {
        if (!alive()) return;
        var view = res[0];
        state = { enabled: !!view.enabled, requires_approval: !!view.requires_approval, pending_count: view.pending_count || 0 };
        if (state.enabled) withdrawn = false;
        paintSwitches();
        ctx.renderRoutineQueue((res[1] && res[1].proposals) || []);
        renderHistory(res[2].rows, older.length ? tailMore : res[2].more);
      }, function () {
        if (!alive()) return;
        enableStatus.set('idle', 'Unable to load routine settings.');
        approvalStatus.set('idle', '');
        // Never leave an actionable item for a queue that cannot be confirmed.
        ctx.renderRoutineQueue([]);
        ctx.routineQueueEmpty.hidden = true;
        ctx.routineQueueCount.el.hidden = false;
        ctx.routineQueueCount.set('idle', 'Unable to load waiting changes.');
      });
    }
    ctx.refetchRoutines = refetchRoutines;
  }

  window.App.studio.selfConfigRoutines = { build: build };
})();
