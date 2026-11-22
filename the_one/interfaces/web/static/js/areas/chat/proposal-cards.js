// App.chat.proposalCards -- the GleepGlorp proposal cards (M36 F2 L6, flight DD6 and DD7).
//
// One card per proposal, keyed by id, in the chat of the proposal (`session_id`). A card follows
// its status live (`proposal_changed`) and after a reload (`proposals_snapshot`, sent right
// after `session_joined`). It sits after the turn that made it: the turn whose work group holds
// the proposing tool call (`data-tool-call-id`), after the last node of that turn.
//
// State lives here, not in the DOM: the log wipes (`clearLog`, `renderHistory`) drop every card
// and `redraw()` (called by renderHistory after a replay) draws them again from state.
//
// States (the root's data-state): pending, applying, applied, dismissed, failed, stale (a
// pending proposal whose base changed: a 409 `stale`), withdrawn (replaced, target gone).
//
// Exposes: onChanged(frame), onSnapshot(frame), redraw(), clear(), reset(), turnEnded(),
//   refreshBusy().
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var BUSY_TEXT = 'Wait for GleepGlorp to finish.';
  var BUSY_REFUSED = 'GleepGlorp is still working. Try again when it finishes.';
  var UNREACHABLE = "Couldn't reach the app. Try again.";
  var APPROVE_KINDS = { approve: true, retry: true, anyway: true };
  var uid = 0;

  function fmtTime(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return window.App.time.formatClock(d);
  }

  function fmtValue(v) {
    if (v === null || v === undefined || v === '') return 'None';
    if (Array.isArray(v)) return v.length ? v.join(', ') : 'None';
    if (typeof v === 'boolean') return v ? 'On' : 'Off';
    return String(v);
  }

  function scheduleValue(text, runs) {
    if (!text) return 'None';
    return runs && runs.length ? text + '\nNext: ' + runs.join(' · ') : text;
  }

  // The label of each field the proposal sets, in the order the server's labels give them.
  function fieldKeys(view) {
    var out = [];
    var labels = view.labels || {};
    for (var k in labels) {
      if (Object.prototype.hasOwnProperty.call(labels, k) &&
          Object.prototype.hasOwnProperty.call(view.changes || {}, k)) out.push(k);
    }
    return out;
  }

  function valueFor(view, key, side) {
    if (key === 'schedule') {
      return side === 'now'
        ? scheduleValue(view.base_schedule_text, view.base_next_runs)
        : scheduleValue(view.schedule_text, view.next_runs);
    }
    if (side === 'now') return fmtValue(view.base ? view.base[key] : undefined);
    return fmtValue(view.changes[key]);
  }

  // An MCP server's `env` and `headers` arrive as nested {row name: value} objects and show one
  // table row per key ("Header Accept", "Env LOG_LEVEL"). The stored keys stay `headers` and
  // `env` (fieldKeys, appliedByApproval); only the table flattens them.
  var ROWS_LABELS = { headers: 'Header', env: 'Env' };

  function isRows(view, key) {
    var v = (view.changes || {})[key];
    return !!ROWS_LABELS[key] && !!v && typeof v === 'object' && !Array.isArray(v);
  }

  // The value a row has now: header names match case-insensitively, env names exactly; an
  // absent row reads undefined (shown as "None").
  function nowRowValue(view, key, row) {
    var rows = view.base ? view.base[key] : null;
    if (!rows || typeof rows !== 'object') return undefined;
    if (Object.prototype.hasOwnProperty.call(rows, row)) return rows[row];
    if (key !== 'headers') return undefined;
    var folded = row.toLowerCase();
    for (var k in rows) {
      if (Object.prototype.hasOwnProperty.call(rows, k) && k.toLowerCase() === folded) return rows[k];
    }
    return undefined;
  }

  function tableRows(view, two) {
    var out = [];
    fieldKeys(view).forEach(function (k) {
      if (isRows(view, k)) {
        Object.keys(view.changes[k]).forEach(function (r) {
          var rr = { label: ROWS_LABELS[k] + ' ' + r, proposed: fmtValue(view.changes[k][r]) };
          if (two) rr.now = fmtValue(nowRowValue(view, k, r));
          out.push(rr);
        });
        return;
      }
      var row = { label: view.labels[k], proposed: valueFor(view, k, 'proposed'), mono: k === 'llm_model' };
      if (two) row.now = valueFor(view, k, 'now');
      out.push(row);
    });
    return out;
  }

  // How many values the proposal sets: one per field, one per row of a rows field.
  function valueCount(view) {
    return fieldKeys(view).reduce(function (n, k) {
      return n + (isRows(view, k) ? Object.keys(view.changes[k]).length : 1);
    }, 0);
  }

  function symDiff(a, b) {
    var out = [];
    (a || []).forEach(function (x) { if ((b || []).indexOf(x) === -1 && out.indexOf(x) === -1) out.push(x); });
    (b || []).forEach(function (x) { if ((a || []).indexOf(x) === -1 && out.indexOf(x) === -1) out.push(x); });
    return out;
  }

  // The tile items a proposal moves, by the editors' group ids (tool names; MCP server and
  // knowledge base NAMES here, ids after resolveItems): the symmetric difference between the stored list and the proposed one. A null
  // enabled_tools means "all", so no tile can be named from it.
  function changedItemsOf(view) {
    var out = {};
    var base = view.base || {};
    var changes = view.changes || {};
    function add(group, key) {
      if (!Object.prototype.hasOwnProperty.call(changes, key)) return;
      if (!Array.isArray(changes[key]) || !Array.isArray(base[key])) return;
      var d = symDiff(base[key], changes[key]);
      if (d.length) out[group] = (out[group] || []).concat(d);
    }
    add('tools', 'enabled_tools');
    add('tools', 'disabled_tools');
    add('mcp_source_ids', 'mcp_source_ids');
    add('kb_ids', 'kb_ids');
    return out;
  }

  // The card's view shows MCP servers and knowledge bases by NAME (the server's display form),
  // while the tiles key on ids: map the names through the client store's lists.
  var NAME_STORES = { mcp_source_ids: 'mcp-sources', kb_ids: 'knowledge-bases' };

  function resolveItems(items) {
    var groups = Object.keys(NAME_STORES).filter(function (g) { return items[g]; });
    var out = {};
    if (items.tools) out.tools = items.tools.slice();
    return Promise.all(groups.map(function (g) {
      return App.store.get(NAME_STORES[g]).then(function (rows) {
        var byName = {};
        (rows || []).forEach(function (r) { byName[r.name] = r.id; });
        out[g] = items[g].map(function (n) { return byName[n]; })
          .filter(function (id) { return id !== undefined; });
      }, function () { /* the notes for this group are skipped */ });
    })).then(function () { return out; });
  }

  function listWords(labels) {
    if (labels.length <= 1) return labels.join('');
    return labels.slice(0, -1).join(', ') + ' and ' + labels[labels.length - 1];
  }

  function create(ctx) {
    var chatState = ctx.chatState;
    var messagesEl = ctx.messagesEl;

    // The chat the cards belong to, and its proposals by id: {view, ui, el, held, drawn}.
    var sid = null;
    var byId = Object.create(null);

    function entries() {
      return Object.keys(byId).map(function (k) { return byId[k]; })
        .sort(function (a, b) { return a.view.id - b.view.id; });
    }

    function reset() {
      sid = null;
      byId = Object.create(null);
    }

    // The log was wiped: every card is gone from the DOM, the state stays for redraw().
    function clear() {
      App.focusAfter.cancel();
      entries().forEach(function (e) { e.el = null; e.drawn = false; });
    }

    // ── State ──────────────────────────────────────────────────────────

    function stateOf(e) {
      var v = e.view;
      if (v.status === 'applied' || v.status === 'dismissed' || v.status === 'withdrawn') return v.status;
      if (v.target_gone || e.ui.gone) return 'withdrawn';
      if (e.ui.acting) return 'applying';
      if (v.status === 'failed') return 'failed';
      return e.ui.stale ? 'stale' : 'pending';
    }

    function sameVersion(a, b) {
      return a.status === b.status && (a.resolved_at || null) === (b.resolved_at || null);
    }

    function freshUi() { return { acting: null, stale: null, error: null, notice: null, gone: false }; }

    // ── Rendering ──────────────────────────────────────────────────────

    function title(view) {
      return App.ui.util.el('h3', { className: 'chat-proposal-title', 'data-testid': 'proposal-title', text: view.title });
    }

    function table(view, two, extra) {
      var t = App.ui.changeTable(Object.assign({
        columns: two ? 2 : 1,
        headers: two ? ['Now', 'Proposed'] : null,
        caption: two ? 'Current and proposed values' : 'Values this change sets',
        rows: tableRows(view, two),
        testid: 'proposal-table'
      }, extra || {}));
      return t.el;
    }

    function head(view) {
      var kids = [App.ui.util.el('span', { text: 'Proposed change' })];
      if (view.untrusted) {
        kids.push(App.ui.noteFlag({ sources: view.untrusted_sources, subject: 'proposal', testid: 'proposal-flag' }));
      }
      kids.push(App.ui.util.el('span', { className: 'chat-proposal-time', text: fmtTime(view.created_at) }));
      return App.ui.util.el('div', { className: 'chat-proposal-head' }, kids);
    }

    // The kind's link to the item the proposal changed, or null (no link: an unknown kind, or a
    // view with nothing to open). Its spec, text and testid come from App.gleepglorpKinds.
    function linkSpecOf(view) {
      var kind = App.gleepglorpKinds.get(view.kind);
      return (kind && kind.openLink && kind.openLink(view)) || null;
    }

    function openLink(view) {
      var l = linkSpecOf(view);
      if (!l) return null;
      return App.ui.util.el('a', {
        href: App.router.href(l.spec), 'data-testid': l.testid, text: l.text
      });
    }

    function details(view) {
      var d = App.ui.disclosure({
        variant: 'plain', summary: 'Details', testid: 'proposal-details', className: 'chat-proposal-details'
      });
      d.body.appendChild(table(view, view.action === 'change'));
      return d.el;
    }

    // A folded line: applied, dismissed or withdrawn.
    function line(view, parts) {
      return App.ui.util.el('div', { className: 'chat-proposal-line', 'data-testid': 'proposal-status-line' }, parts);
    }

    function renderApplied(e) {
      var v = e.view;
      var state = App.ui.util.el('span', { className: 'chat-proposal-state chat-proposal-state--applied' },
        [App.ui.util.icon('check'), 'Applied']);
      var parts = [state, App.ui.util.el('span', { text: (v.result && v.result.summary) || v.title }),
        App.ui.util.el('span', { className: 'chat-proposal-time', text: fmtTime(v.resolved_at || v.created_at) })];
      var link = openLink(v);
      if (link) parts.push(link);
      return [line(v, parts), details(v)];
    }

    function renderDismissed(e) {
      var v = e.view;
      var when = fmtTime(v.resolved_at || v.created_at);
      return [line(v, [App.ui.util.el('span', { text: 'Dismissed · ' + v.title + (when ? ' · ' + when : '') })]),
        details(v)];
    }

    function renderWithdrawn(e) {
      var v = e.view;
      var reason;
      if (v.status === 'withdrawn' && v.result && v.result.reason === 'replaced') {
        reason = 'replaced by the proposal below.';
      } else {
        var kind = App.gleepglorpKinds.get(v.kind);
        reason = kind && kind.labels && kind.labels.withdrawnGone
          ? kind.labels.withdrawnGone(v) : 'the item no longer exists.';
      }
      return [line(v, [App.ui.util.el('span', { text: 'Withdrawn · ' + v.title + ': ' + reason })])];
    }

    function errorText(v) {
      var errs = (v.result && v.result.errors) || [];
      var bits = errs.map(function (er) {
        var key = er.loc && er.loc.length ? er.loc[0] : null;
        var label = key !== null && v.labels && v.labels[key];
        return (label ? label + ': ' : '') + er.msg;
      });
      return ["Couldn't apply this change."].concat(bits).join(' ');
    }

    // `opts` is the App.ui.button options, written out at each call site with its literal testid.
    function button(e, kind, opts) {
      var b = App.ui.button(opts);
      b.setAttribute('data-proposal-action', kind);
      b.addEventListener('click', function () { act(e, kind, b); });
      return b;
    }

    function foot(e, buttons, note, warnings) {
      var waitId = 'proposal-wait-' + (++uid);
      var wait = App.ui.util.el('p', { className: 'chat-proposal-wait', id: waitId, text: BUSY_TEXT });
      wait.hidden = true;
      e.waitEl = wait;
      buttons.forEach(function (b) { b.setAttribute('aria-describedby', waitId); });
      var kids = buttons.slice();
      if (note) kids.push(App.ui.util.el('span', { className: 'chat-proposal-foot-note', text: note }));
      // What the operator should know before approving (an MCP server's saved sign-in, a first
      // download): each warning is a plain line of the footer.
      (warnings || []).forEach(function (w) {
        kids.push(App.ui.util.el('p', {
          className: 'chat-proposal-warning', 'data-testid': 'proposal-warning', text: w
        }));
      });
      kids.push(wait);
      return App.ui.util.el('div', { className: 'chat-proposal-foot' }, kids);
    }

    function footNote(v) {
      if (v.action === 'create') return 'Other settings keep their defaults.';
      var n = valueCount(v);
      var rows = fieldKeys(v).some(function (k) { return isRows(v, k); });
      var noun = rows ? 'value' : 'field';
      return n === 1 ? 'Only this ' + noun + ' changes.' : 'Only these ' + n + ' ' + noun + 's change.';
    }

    // A spacing wrapper (the status and banner controls carry no margin of their own).
    function block(node) {
      var d = document.createElement('div');
      d.className = 'chat-proposal-block';
      d.appendChild(node);
      return d;
    }

    // The neutral line for a refused click (busy) or an unreachable app, with raw details.
    function noticeNode(e) {
      if (e.ui.notice) {
        var s = App.ui.status({ testid: 'proposal-notice', led: false });
        s.set('idle', e.ui.notice);
        return block(s.el);
      }
      if (e.ui.error) {
        var s2 = App.ui.status({ testid: 'proposal-notice', led: false });
        s2.set('idle', UNREACHABLE);
        var d = App.ui.disclosure({ variant: 'plain', summary: 'Technical details', testid: 'proposal-notice-details' });
        d.body.appendChild(document.createTextNode(e.ui.error));
        var wrap = block(s2.el);
        wrap.appendChild(d.el);
        return wrap;
      }
      return null;
    }

    function renderOpen(e, state) {
      var v = e.view;
      var kids = [head(v)];
      if (v.untrusted) {
        kids.push(App.ui.util.el('p', {
          className: 'chat-proposal-hint', 'data-testid': 'proposal-source-hint',
          text: 'Proposed after GleepGlorp read content not from you: ' + v.untrusted_sources.join(', ') +
            '. Read every field before you approve.'
        }));
      }
      kids.push(title(v));
      var primary;
      if (state === 'stale') {
        var labels = e.ui.stale.map(function (f) { return f.label; });
        kids.push(block(App.ui.banner({
          tone: 'warning', role: 'alert', testid: 'proposal-stale',
          text: listWords(labels) + ' changed after GleepGlorp proposed this. ' +
            'Approving anyway replaces the current value below.'
        }).el));
        var t = App.ui.changeTable({
          columns: 2, headers: ['Current', 'Proposed'], caption: 'Changed since proposed',
          testid: 'proposal-table',
          rows: e.ui.stale.map(function (f) {
            return { label: f.label, now: fmtValue(f.current), proposed: fmtValue(f.proposed) };
          })
        });
        kids.push(t.el);
        primary = button(e, 'anyway', { variant: 'primary', label: 'Approve anyway', testid: 'proposal-approve-anyway' });
      } else {
        if (v.status === 'failed') {
          var st = App.ui.status({ testid: 'proposal-error', role: 'alert', led: false, textTone: true });
          st.set('danger', errorText(v));
          kids.push(block(st.el));
        }
        kids.push(table(v, v.action === 'change'));
        primary = v.status === 'failed'
          ? button(e, 'retry', { variant: 'primary', label: 'Try again', testid: 'proposal-try-again' })
          : button(e, 'approve', { variant: 'primary', label: 'Approve', testid: 'proposal-approve' });
      }
      var note = noticeNode(e);
      if (note) kids.push(note);
      var dismiss = button(e, 'dismiss', { variant: 'secondary', label: 'Dismiss', testid: 'proposal-dismiss' });
      kids.push(foot(e, [primary, dismiss], state === 'stale' ? null : footNote(v), v.warnings));
      return kids;
    }

    function build(e) {
      var state = stateOf(e);
      e.waitEl = null;
      var kids;
      if (state === 'applied') kids = renderApplied(e);
      else if (state === 'dismissed') kids = renderDismissed(e);
      else if (state === 'withdrawn') kids = renderWithdrawn(e);
      else kids = renderOpen(e, state === 'applying' ? (e.ui.stale ? 'stale' : e.view.status === 'failed' ? 'failed' : 'pending') : state);
      e.el.setAttribute('data-state', state);
      e.el.className = 'chat-proposal chat-proposal--' + state;
      e.el.setAttribute('aria-label', 'Proposed change: ' + e.view.title);
      // On the body wrapper, never an ancestor of the status node: some screen readers hold back
      // live-region updates inside an aria-busy subtree (WCAG 4.1.3).
      e.el.removeAttribute('aria-busy');
      if (state === 'applying') e.body.setAttribute('aria-busy', 'true');
      else e.body.removeAttribute('aria-busy');
      e.body.replaceChildren.apply(e.body, kids);
      announce(e, state);
      syncBusy(e);
    }

    // The card sits in the polite log, so its root is aria-live="off" (a rebuild is not read) and
    // this one persistent status node says what changed, once per state. A failed or stale card
    // is told by its own role=alert, so the status stays empty then (no double announcement).
    function announceText(e, state) {
      var v = e.view;
      if (state === 'applied') return 'Applied: ' + ((v.result && v.result.summary) || v.title) + '.';
      if (state === 'dismissed') return 'Dismissed: ' + v.title + '.';
      if (state === 'withdrawn') return 'Withdrawn: ' + v.title + '.';
      return '';
    }

    function announce(e, state) {
      if (e.said === state) return;
      var first = e.said === undefined;
      e.said = state;
      var text = announceText(e, state);
      // A card drawn again from a reload or replay is silent: only a live arrival speaks.
      if (first && !e.fresh) return;
      e.fresh = false;
      if (first && state === 'pending') {
        // A live region only speaks a change, so the first text lands once the node is in the page.
        text = 'GleepGlorp proposed a change: ' + e.view.title + '.';
        setTimeout(function () { if (e.statusEl) e.statusEl.textContent = text; }, 100);
        return;
      }
      e.statusEl.textContent = text;
    }

    // Buttons are disabled while a turn runs (the server's 409 busy is the backstop) or while this
    // card's own request is out.
    function syncBusy(e) {
      if (!e.el) return;
      var busy = !!ctx.send.isCurrentBusy();
      var btns = e.el.querySelectorAll('[data-proposal-action]');
      for (var i = 0; i < btns.length; i++) {
        var b = btns[i];
        var kind = b.getAttribute('data-proposal-action');
        var off = busy || !!e.ui.acting;
        // aria-disabled only (never the native attribute): the button stays focusable, so its
        // aria-describedby hint is read. act() ignores every activation while busy.
        if (off) b.setAttribute('aria-disabled', 'true');
        else b.removeAttribute('aria-disabled');
        if (busy) b.title = BUSY_TEXT;
        else b.removeAttribute('title');
        if (APPROVE_KINDS[kind] && e.ui.acting && e.ui.acting !== 'dismiss' && b.firstChild) {
          b.firstChild.data = 'Approving…';
        }
      }
      if (e.waitEl) e.waitEl.hidden = !(busy && !e.ui.acting);
    }

    function refreshBusy() {
      entries().forEach(function (e) { if (e.drawn) syncBusy(e); });
    }

    // ── Placement ──────────────────────────────────────────────────────

    // The placement (after the turn that made the proposal, ordered with the other cards) is the
    // shared App.chat.cardOrder, which the form-fill receipts use too (M36 F3 L6).
    function cardInfo(e) {
      return {
        kind: 'proposal', id: e.view.id, createdAt: e.view.created_at, toolCallId: e.view.tool_call_id
      };
    }

    function isPinned() {
      return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight <=
        ctx.transcript.SCROLL_PIN_THRESHOLD;
    }

    function draw(e) {
      if (e.drawn && e.el && e.el.isConnected) return;
      var wasPinned = isPinned();
      e.el = App.ui.util.el('section', {
        'data-testid': 'proposal-card', 'data-proposal-id': String(e.view.id), 'aria-live': 'off'
      });
      e.statusEl = App.ui.util.el('div', {
        className: 'visually-hidden', role: 'status', 'aria-live': 'polite', 'data-testid': 'proposal-announce'
      });
      e.body = App.ui.util.el('div', { className: 'chat-proposal-body' });
      e.el.appendChild(e.statusEl);
      e.el.appendChild(e.body);
      e.said = undefined;
      build(e);
      App.chat.cardOrder.mark(e.el, cardInfo(e));
      App.chat.cardOrder.place(messagesEl, e.el, cardInfo(e));
      e.drawn = true;
      e.held = false;
      if (wasPinned) messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function render(e) {
      if (e.drawn && e.el) build(e);
    }

    // ── Applying a version of a proposal ───────────────────────────────

    // Takes a view into an entry; a version already held (same status and resolved_at) changes
    // nothing. A new status clears the local lines (stale, error, notice, gone, acting).
    function setView(e, view) {
      if (sameVersion(e.view, view)) return false;
      e.view = view;
      e.ui = freshUi();
      render(e);
      return true;
    }

    function upsert(view) {
      var e = byId[view.id];
      if (e) {
        setView(e, view);
        return e;
      }
      e = { view: view, ui: freshUi(), el: null, drawn: false, held: false, waitEl: null, fresh: false };
      byId[view.id] = e;
      return e;
    }

    function onSnapshot(data) {
      if (!data || data.session_id !== chatState.boundId()) return;
      if (sid !== data.session_id) {
        reset();
        sid = data.session_id;
      }
      var seen = Object.create(null);
      (data.proposals || []).forEach(function (v) { seen[v.id] = true; upsert(v); });
      Object.keys(byId).forEach(function (k) {
        if (!seen[k]) {
          var gone = byId[k];
          if (gone.el && gone.el.parentNode) gone.el.parentNode.removeChild(gone.el);
          delete byId[k];
        }
      });
      entries().forEach(function (e) { if (!e.drawn) draw(e); });
      refreshBusy();
    }

    function onChanged(data) {
      if (!data || !data.proposal || data.session_id !== chatState.boundId()) return;
      if (sid !== data.session_id) {
        reset();
        sid = data.session_id;
      }
      var known = !!byId[data.proposal.id];
      var e = upsert(data.proposal);
      if (!known) e.fresh = true;
      if (e.drawn) return;
      if (!known && (ctx.send.isCurrentBusy() || ctx.turnWork.isOpen())) {
        // A card made during a turn lands after the turn's reply (turnEnded).
        e.held = true;
        return;
      }
      if (!e.held) draw(e);
    }

    // Called by renderHistory after a replay: draw what the state holds again.
    function redraw() {
      if (sid === null) return;
      if (sid !== chatState.boundId()) {
        reset();
        return;
      }
      entries().forEach(function (e) { if (!e.held) draw(e); });
      refreshBusy();
    }

    // Every path that ends a turn calls this: the held cards land now.
    function turnEnded() {
      entries().forEach(function (e) { if (e.held) draw(e); });
      refreshBusy();
    }

    // ── Actions ────────────────────────────────────────────────────────

    function focusTarget(e, kind) {
      return function () {
        if (!e.el) return null;
        var s = stateOf(e);
        if (s === 'applied' || s === 'withdrawn') {
          var l = linkSpecOf(e.view);
          return l ? e.el.querySelector('[data-testid="' + l.testid + '"]') : null;
        }
        if (s === 'dismissed') return ctx.composer.input;
        if (s === 'failed') return e.el.querySelector('[data-testid="proposal-try-again"]');
        if (s === 'stale') return e.el.querySelector('[data-testid="proposal-approve-anyway"]');
        return kind === 'dismiss' ? ctx.composer.input : e.el.querySelector('[data-proposal-action]');
      };
    }

    // The one place an approve response with status `applied` lands (Leg 7 hooks here: the
    // agent editors follow a change the operator approved).
    function appliedByApproval(e, view) {
      void e;
      // The frame to every socket carries the same proposal id, so the second is ignored (its
      // items are merged either way).
      App.approvals.record({
        kind: view.kind,
        agent: view.agent_name,
        target_id: view.target_id,
        fields: fieldKeys(view),
        items: null,
        session_id: sid,
        proposal_id: view.id,
        at: view.resolved_at
      });
      // The tile items follow once the names are ids; a repeat of the proposal id merges them.
      var items = changedItemsOf(view);
      if (Object.keys(items).length) {
        resolveItems(items).then(function (resolved) {
          App.approvals.record({
            kind: view.kind, agent: view.agent_name, target_id: view.target_id, fields: [], items: resolved,
            session_id: sid, proposal_id: view.id, at: view.resolved_at
          });
        });
      }
    }

    function applyResponse(e, view, kind, token) {
      setView(e, view);
      e.ui.acting = null;
      if (APPROVE_KINDS[kind] && view.status === 'applied') appliedByApproval(e, view);
      render(e);
      App.focusAfter.restore(token, focusTarget(e, kind));
    }

    function refetch(e, token) {
      return App.api.fetchJson('/api/gleepglorp/proposals?session_id=' + encodeURIComponent(sid || ''))
        .then(function (r) {
          (r.proposals || []).forEach(function (v) { upsert(v); });
        })
        .catch(function () { /* the next frame or join brings it */ })
        .then(function () {
          e.ui.acting = null;
          render(e);
          App.focusAfter.restore(token, focusTarget(e, 'approve'));
        });
    }

    function onError(e, err, kind, token) {
      var d = err && err.status === 409 && err.detail && typeof err.detail === 'object' ? err.detail : null;
      var which = d && d.error;
      if (which === 'closed') {
        refetch(e, token);
        return;
      }
      e.ui.acting = null;
      if (which === 'busy') {
        e.ui.notice = BUSY_REFUSED;
      } else if (which === 'stale') {
        e.ui.stale = d.fields || [];
      } else if (which === 'gone') {
        e.ui.gone = true;
      } else {
        e.ui.error = (err && err.message) || 'Request failed';
      }
      render(e);
      App.focusAfter.restore(token, focusTarget(e, which === 'stale' ? 'approve' : kind));
    }

    function act(e, kind, btn) {
      if (e.ui.acting || ctx.send.isCurrentBusy()) return;
      var token = App.focusAfter.begin(btn);
      e.ui.acting = kind;
      e.ui.notice = null;
      e.ui.error = null;
      render(e);
      var url = '/api/gleepglorp/proposals/' + encodeURIComponent(e.view.id) +
        (kind === 'dismiss' ? '/dismiss' : '/approve' + (kind === 'anyway' ? '?override=true' : ''));
      App.api.fetchJson(url, { method: 'POST' })
        .then(function (r) { applyResponse(e, r.proposal, kind, token); })
        .catch(function (err) { onError(e, err, kind, token); });
    }

    return {
      onChanged: onChanged,
      onSnapshot: onSnapshot,
      redraw: redraw,
      clear: clear,
      reset: reset,
      turnEnded: turnEnded,
      refreshBusy: refreshBusy
    };
  }

  window.App.chat.proposalCards = { create: create };
})();
