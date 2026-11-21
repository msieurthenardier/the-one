// App.chat.fillReceipts -- the receipts for GleepGlorp form fills (M36 F3 L6, flight DD7).
//
// One receipt per fill, keyed by id, in the chat of the fill (`session_id`). It follows the fill's
// status live (`fill_requested`, `fill_changed`) and after a reload (`fills` in
// `proposals_snapshot`), and sits after the turn that made it, ordered with the proposal cards by
// App.chat.cardOrder. A receipt made during a turn is held and lands when the turn ends.
//
// Every chat instance showing the conversation draws the receipt. Only the drawer has buttons: its
// config's `fillHooks` ({fillNow(view), isApplying(id)}; the defaults do nothing and answer false)
// supply the retry (Fill now is the only button). This module never claims, applies or reports
// a fill.
//
// State lives here, not in the DOM: a log wipe drops every receipt and redraw() draws them again.
//
// Exposes: onRequested(frame), onChanged(frame), onSnapshot(frame), redraw(), clear(), reset(),
//   turnEnded(), refresh().
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var LEASE_MS = 120000;
  var REASONS = {
    in_chats: 'You were in Chats when it arrived.',
    stay: 'You chose to stay on the page you were editing.',
    editor_unavailable: 'The agent editor could not open.',
    target_gone: 'That agent no longer exists.'
  };
  var HEADLINES = {
    sent: 'Filling the form…',
    applying: 'Filling the form…',
    filled: 'Form filled',
    partly_filled: 'Form partly filled',
    not_filled: 'Form not filled',
    replaced: 'Replaced by a newer fill.'
  };

  function fmtTime(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return window.App.time.formatClock(d);
  }

  function listWords(labels) {
    if (labels.length <= 1) return labels.join('');
    return labels.slice(0, -1).join(', ') + ' and ' + labels[labels.length - 1];
  }

  function fieldsText(n) {
    return n === 1 ? '1 field' : n + ' fields';
  }

  function create(ctx) {
    var chatState = ctx.chatState;
    var messagesEl = ctx.messagesEl;
    var isDrawer = ctx.profile === 'drawer';

    // The chat the receipts belong to, and its fills by id: {view, el, drawn, held, fresh}.
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

    // The log was wiped: every receipt is gone from the DOM, the state stays for redraw().
    function clear() {
      entries().forEach(function (e) { e.el = null; e.drawn = false; });
    }

    // ── State and wording ──────────────────────────────────────────────

    function hooks() {
      return ctx.fillHooks || {};
    }

    function applyingHere(id) {
      var h = hooks();
      return !!(h.isApplying && h.isApplying(id));
    }

    function reasonOf(v) {
      var r = v.outcome && v.outcome.reason;
      return r && REASONS[r] ? r : null;
    }

    function labelsOf(v, keys) {
      return (keys || []).map(function (k) { return (v.labels && v.labels[k]) || k; });
    }

    // Fill now: a retry the drawer window may run (never in Chats, never for a gone agent).
    function offersFillNow(v) {
      if (!isDrawer || v.target_gone) return false;
      if (v.status === 'not_filled') return reasonOf(v) !== 'target_gone';
      if (v.status === 'sent') return !applyingHere(v.id);
      if (v.status === 'applying') {
        if (applyingHere(v.id)) return false;
        var at = v.claimed_at ? new Date(v.claimed_at).getTime() : NaN;
        return !isNaN(at) && Date.now() - at > LEASE_MS;
      }
      return false;
    }

    // ── Rendering ──────────────────────────────────────────────────────

    // `attrs` carries the line's literal data-testid.
    function line(attrs, text) {
      return App.ui.util.el('p', Object.assign({ className: 'chat-fill-line', text: text }, attrs));
    }

    function head(v) {
      var kids = [App.ui.util.el('span', { text: 'Form fill' })];
      if (v.untrusted) {
        kids.push(App.ui.noteFlag({ sources: v.untrusted_sources, subject: 'fill', testid: 'fill-receipt-flag' }));
      }
      kids.push(App.ui.util.el('span', {
        className: 'chat-proposal-time', text: fmtTime(v.resolved_at || v.created_at)
      }));
      return App.ui.util.el('div', { className: 'chat-proposal-head' }, kids);
    }

    function body(e) {
      var v = e.view;
      var kids = [head(v)];
      kids.push(App.ui.util.el('p', {
        className: 'chat-fill-headline', 'data-testid': 'fill-receipt-headline', text: HEADLINES[v.status] || ''
      }));
      if (v.status !== 'replaced') {
        kids.push(App.ui.util.el('h3', {
          className: 'chat-proposal-title', 'data-testid': 'fill-receipt-title', text: v.title
        }));
      }
      if (v.status === 'filled') {
        kids.push(line({ 'data-testid': 'fill-receipt-detail' }, fieldsText(v.field_count) + ' · Not saved'));
      } else if (v.status === 'partly_filled') {
        kids.push(line({ 'data-testid': 'fill-receipt-detail' }, fieldsText(v.field_count) + ' · Not saved'));
        kids.push(line({ 'data-testid': 'fill-receipt-kept' }, keptText(v)));
      } else if (v.status === 'not_filled') {
        var reason = reasonOf(v);
        if (reason) kids.push(line({ 'data-testid': 'fill-receipt-reason' }, REASONS[reason]));
      }
      var fillNow = offersFillNow(v);
      if (fillNow && v.stale && v.stale.length) {
        kids.push(line({ 'data-testid': 'fill-receipt-stale' }, 'Changed since GleepGlorp filled it: ' +
          listWords(v.stale.map(function (f) { return f.label; })) + '.'));
      }
      if (e.notice) kids.push(line({ 'data-testid': 'fill-receipt-notice' }, e.notice));
      var buttons = [];
      if (fillNow) {
        var b = App.ui.button({ variant: 'primary', label: 'Fill now', testid: 'fill-receipt-fill-now' });
        b.addEventListener('click', function () { onFillNow(e); });
        buttons.push(b);
      }
      if (buttons.length) {
        kids.push(App.ui.util.el('div', { className: 'chat-proposal-foot' }, buttons));
      }
      return kids;
    }

    function build(e) {
      var v = e.view;
      var kids = body(e);
      e.el.setAttribute('data-status', v.status);
      e.el.className = 'chat-proposal chat-fill' + (v.status === 'replaced' ? ' chat-proposal--withdrawn' : '');
      e.el.setAttribute('aria-label', 'Form fill: ' + v.title);
      // On the body wrapper, never an ancestor of the status node: some screen readers hold back
      // live-region updates inside an aria-busy subtree (WCAG 4.1.3).
      e.el.removeAttribute('aria-busy');
      if (v.status === 'sent' || v.status === 'applying') e.body.setAttribute('aria-busy', 'true');
      else e.body.removeAttribute('aria-busy');
      e.body.replaceChildren.apply(e.body, kids);
      announce(e);
    }

    // The root is not a live region (a rebuild is not read); this one persistent status node says
    // what changed, once per status. A receipt drawn again from a reload or replay is silent.
    function say(e, text, delay) {
      // Clear first, so the same words said twice are still announced.
      if (e.statusEl) e.statusEl.textContent = '';
      setTimeout(function () { if (e.statusEl) e.statusEl.textContent = text; }, delay);
    }

    // What is announced: the receipt's own words (headline, title, field count and, when some
    // fields were kept, the kept sentence).
    function announceText(v) {
      var s = v.status;
      var text = HEADLINES[s] || '';
      if (s === 'sent' || s === 'applying' || s === 'replaced') return text;
      text += ': ' + v.title + '.';
      if (s === 'filled' || s === 'partly_filled') {
        text += ' ' + fieldsText(v.field_count) + ' · Not saved.';
      }
      if (s === 'partly_filled') {
        text += ' ' + keptText(v);
      }
      return text;
    }

    function keptText(v) {
      return 'You had changed ' + listWords(labelsOf(v, v.outcome && v.outcome.kept)) +
        ' and not saved them, so I left them.';
    }

    function announce(e) {
      var s = e.view.status;
      if (e.said === s) return;
      var first = e.said === undefined;
      e.said = s;
      if (first && !e.fresh) return;
      e.fresh = false;
      say(e, announceText(e.view), first ? 100 : 0);
    }

    function info(e) {
      return { kind: 'fill', id: e.view.id, createdAt: e.view.created_at, toolCallId: e.view.tool_call_id };
    }

    function isPinned() {
      return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight <=
        ctx.transcript.SCROLL_PIN_THRESHOLD;
    }

    function draw(e) {
      if (e.drawn && e.el && e.el.isConnected) return;
      var wasPinned = isPinned();
      // A labelled group, not a region landmark: a long transcript must not fill the landmark list.
      e.el = App.ui.util.el('div', {
        role: 'group', 'data-testid': 'fill-receipt', 'data-fill-id': String(e.view.id)
      });
      e.statusEl = App.ui.util.el('div', {
        className: 'visually-hidden', role: 'status', 'aria-live': 'polite', 'data-testid': 'fill-receipt-announce'
      });
      e.body = App.ui.util.el('div', { className: 'chat-proposal-body' });
      e.el.appendChild(e.statusEl);
      e.el.appendChild(e.body);
      e.said = undefined;
      build(e);
      App.chat.cardOrder.mark(e.el, info(e));
      App.chat.cardOrder.place(messagesEl, e.el, info(e));
      e.drawn = true;
      e.held = false;
      if (wasPinned) messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function render(e) {
      if (e.drawn && e.el) build(e);
    }

    // ── Applying a version of a fill ───────────────────────────────────

    function setView(e, view) {
      if (JSON.stringify(e.view) === JSON.stringify(view)) return false;
      if (e.view.status !== view.status) e.notice = null;
      e.view = view;
      render(e);
      return true;
    }

    function upsert(view) {
      var e = byId[view.id];
      if (e) {
        setView(e, view);
        return e;
      }
      e = { view: view, el: null, drawn: false, held: false, fresh: false };
      byId[view.id] = e;
      return e;
    }

    function adopt(data) {
      if (sid !== data.session_id) {
        reset();
        sid = data.session_id;
      }
    }

    function onSnapshot(data) {
      if (!data || !Array.isArray(data.fills) || data.session_id !== chatState.boundId()) return;
      adopt(data);
      var seen = Object.create(null);
      data.fills.forEach(function (v) { seen[v.id] = true; upsert(v); });
      Object.keys(byId).forEach(function (k) {
        if (!seen[k]) {
          var gone = byId[k];
          if (gone.el && gone.el.parentNode) gone.el.parentNode.removeChild(gone.el);
          delete byId[k];
        }
      });
      entries().forEach(function (e) { if (!e.drawn) draw(e); });
    }

    // fill_requested and fill_changed: a view of one fill. The caller (turn-frames) has already
    // checked the frame is for the bound chat.
    function onFrame(data) {
      if (!data || !data.fill) return;
      adopt(data);
      var known = !!byId[data.fill.id];
      var e = upsert(data.fill);
      if (!known) e.fresh = true;
      if (e.drawn) return;
      if (!known && (ctx.send.isCurrentBusy() || ctx.turnWork.isOpen())) {
        // A receipt made during a turn lands after the turn's reply (turnEnded).
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
    }

    // Every path that ends a turn calls this: the held receipts land now.
    function turnEnded() {
      entries().forEach(function (e) { if (e.held) draw(e); });
    }

    // Re-draws every drawn receipt (the hooks' answers changed).
    function refresh() {
      entries().forEach(render);
    }

    // ── Actions ────────────────────────────────────────────────────────

    // The hook may return a promise of {busy: true} (a claim refused because another window is
    // applying the fill): the receipt then says so, until its status next changes.
    function onFillNow(e) {
      var h = hooks();
      if (!h.fillNow) return;
      var r = h.fillNow(e.view);
      if (r && typeof r.then === 'function') {
        r.then(function (res) {
          if (res && res.busy && e.drawn) {
            e.notice = 'Still being applied in another window.';
            render(e);
            say(e, e.notice, 0);
          }
        }, function () { /* the hook reports its own failures */ });
      }
    }

    return {
      onRequested: onFrame,
      onChanged: onFrame,
      onSnapshot: onSnapshot,
      redraw: redraw,
      clear: clear,
      reset: reset,
      turnEnded: turnEnded,
      refresh: refresh
    };
  }

  window.App.chat.fillReceipts = { create: create };
})();
