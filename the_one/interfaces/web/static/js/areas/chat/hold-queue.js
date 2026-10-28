// App.chat.holdQueue -- the client hold queue and its pinned chips (M31 F6 L02, split out of
// areas/chat.js; many messages since L10a).
//
// A message sent while a turn runs is held locally (pendingQueuedMessages[sessionId], an ARRAY
// of strings in send order, in the shared state) and shown as one chip each in the region above
// the composer; each `done` frame sends the first through the normal path. An empty queue has
// NO key (an empty array is truthy, so every reader tests `.length` and discards delete the
// key). Exposes: list, count, push, shift, discardAll, showPendingQueued, clearPendingQueued,
// cancelPendingQueued, MAX.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var MAX = 10;

  function create(ctx) {
    var state = ctx.state;
    var chatState = ctx.chatState;

    var chipEls = [];
    var pendingQueuedRegionEl = ctx.composer.slots.queued;
    var statusEl = null;
    var fullEl = null;
    var fullTimer = null;
    var fullTextTimer = null;

    function list(sid) {
      var q = sid ? state.pendingQueuedMessages[sid] : null;
      return q && q.length ? q : [];
    }

    function count(sid) { return list(sid).length; }

    // Append a message; false (nothing stored) at the cap.
    function push(sid, text) {
      var q = list(sid);
      if (q.length >= MAX) return false;
      if (!q.length) state.pendingQueuedMessages[sid] = q = [];
      q.push(text);
      return true;
    }

    // Remove and return the first held message (the key goes with the last one), or null.
    function shift(sid) {
      var q = list(sid);
      if (!q.length) return null;
      var first = q.shift();
      if (!q.length) delete state.pendingQueuedMessages[sid];
      return first;
    }

    // Drop the whole queue of a session; returns how many were held. DOM untouched.
    function discardAll(sid) {
      var n = count(sid);
      if (sid) delete state.pendingQueuedMessages[sid];
      return n;
    }

    // The persistent live region's status line, kept in the region so every change is announced.
    function setStatus(n) {
      if (!pendingQueuedRegionEl) return;
      if (!statusEl) {
        statusEl = document.createElement('span');
        statusEl.className = 'visually-hidden';
        statusEl.setAttribute('data-testid', 'pending-queued-status');
        pendingQueuedRegionEl.appendChild(statusEl);
      }
      statusEl.textContent = n === 0 ? '' : (n === 1 ? '1 message queued' : n + ' messages queued');
    }

    // Remove the chips from the DOM (idempotent). Does NOT touch the held messages.
    function clearPendingQueued() {
      for (var i = 0; i < chipEls.length; i++) {
        if (chipEls[i].parentNode) chipEls[i].parentNode.removeChild(chipEls[i]);
      }
      chipEls = [];
      setStatus(0);
      hideFull();
    }

    // Render one chip per held message of the list, in order (rebuilds all, so the names
    // "Cancel queued message {i} of {n}" are always current).
    function showPendingQueued(texts) {
      clearPendingQueued();
      if (!texts || !texts.length || !pendingQueuedRegionEl) return;
      var n = texts.length;
      for (var i = 0; i < n; i++) {
        chipEls.push(buildChip(texts[i], i, n));
      }
      for (var j = 0; j < chipEls.length; j++) {
        pendingQueuedRegionEl.insertBefore(chipEls[j], statusEl);
      }
      setStatus(n);
    }

    function buildChip(text, index, n) {
      // The persistent region is aria-live; chips are rebuilt on every change, so they are
      // silent and only the hidden status line announces "{n} messages queued".
      var lead = document.createElement('span');
      lead.className = 'pending-queued-lead';
      lead.textContent = 'Queued';
      var chip = App.ui.chip({
        label: text,
        truncate: true,
        lead: lead,
        onRemove: function () { removeAt(index); },
        removeLabel: n > 1 ? 'Cancel queued message ' + (index + 1) + ' of ' + n : 'Cancel queued message',
        removeTestid: 'pending-queued-cancel',
        testid: 'pending-queued',
        dataset: { index: String(index) }
      });
      chip.setAttribute('aria-live', 'off');
      return chip;
    }

    // Re-render the active session's queue from state.
    function refresh() {
      showPendingQueued(list(chatState.activeId()));
    }

    // Cancel (x) on one chip: drop that message only (purely local, nothing was sent). Focus goes
    // to the next chip, else the previous one, else the message box (WCAG 2.4.3).
    function removeAt(index) {
      var a = chatState.activeId();
      var q = list(a);
      if (index < 0 || index >= q.length) return;
      var hadFocus = !!(chipEls[index] && chipEls[index].contains(document.activeElement));
      q.splice(index, 1);
      if (!q.length) delete state.pendingQueuedMessages[a];
      refresh();
      if (!hadFocus) return;
      var target = chipEls[index] || chipEls[index - 1];
      var btn = target && target.querySelector('[data-testid="pending-queued-cancel"]');
      if (btn) btn.focus();
      else if (ctx.composer.input) ctx.composer.input.focus();
    }

    // Cancel the LAST chip's message (kept for callers that cancel "the" queued message).
    function cancelPendingQueued() {
      removeAt(count(chatState.activeId()) - 1);
    }

    function hideFull() {
      if (fullTimer) { clearTimeout(fullTimer); fullTimer = null; }
      if (fullTextTimer) { clearTimeout(fullTextTimer); fullTextTimer = null; }
      if (fullEl && fullEl.parentNode) fullEl.parentNode.removeChild(fullEl);
      fullEl = null;
    }

    // At the cap: a short muted note under the composer (the text stays in the box).
    function showFull() {
      hideFull();
      var host = ctx.composer.el.parentNode;
      if (!host) return;
      fullEl = document.createElement('p');
      fullEl.className = 'pending-queued-full';
      fullEl.setAttribute('role', 'status');
      fullEl.setAttribute('data-testid', 'pending-queued-full');
      host.insertBefore(fullEl, ctx.composer.el.nextSibling);
      // A status node inserted with its text may stay silent: insert empty, write next tick.
      var node = fullEl;
      fullTextTimer = setTimeout(function () {
        fullTextTimer = null;
        if (fullEl === node) node.textContent = 'Queue is full (' + MAX + ')';
      }, 50);
      fullTimer = setTimeout(hideFull, 4000);
    }

    return {
      MAX: MAX,
      list: list,
      count: count,
      push: push,
      shift: shift,
      discardAll: discardAll,
      refresh: refresh,
      showFull: showFull,
      showPendingQueued: showPendingQueued,
      clearPendingQueued: clearPendingQueued,
      cancelPendingQueued: cancelPendingQueued
    };
  }

  window.App.chat.holdQueue = { create: create };
})();
