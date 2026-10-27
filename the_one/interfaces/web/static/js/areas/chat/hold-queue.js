// App.chat.holdQueue -- the one-slot client hold and its pinned chip (M31 F6 L02,
// split out of areas/chat.js, moved verbatim apart from the ctx./state. prefixes).
//
// A message sent while a turn runs is held locally (pendingQueuedMessages[sessionId], in the
// shared state) and shown as a chip in the region above the composer; the `done` frame sends
// it through the normal path. Exposes: showPendingQueued, clearPendingQueued,
// cancelPendingQueued.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var state = ctx.state;
    var chatState = ctx.chatState;

    // DOM element showing the pending queued message hint (one shared element; swapped
    // on session-switch if the joined session has a pending queued message).
    var pendingQueuedEl = null;
    // F09-04: pinned container above the composer that hosts the queued chip,
    // outside the scrolling .messages list.
    var pendingQueuedRegionEl = ctx.composer.slots.queued;

    // F09-04 (client-hold): render a PINNED chip for the held queued message.
    // The chip lives in pendingQueuedRegionEl — a region above the composer,
    // OUTSIDE the scrolling .messages list — so it never scrolls away. The
    // held text is stored per-session in pendingQueuedMessages; only one slot
    // (queue depth = 1). The message is NOT sent to the backend while held —
    // the WS `done` handler sends it via the normal send path once the running
    // turn finishes. The chip carries a keyboard-accessible cancel (×) button.
    function showPendingQueued(text) {
      clearPendingQueued();
      if (!text || !pendingQueuedRegionEl) return;

      // A7: the queued chip is App.ui.chip: a "Queued" lead, the text on one line with an
      // ellipsis, and a library remove button that cancels it (keyboard-activatable).
      var lead = document.createElement('span');
      lead.className = 'pending-queued-lead';
      lead.textContent = 'Queued';
      pendingQueuedEl = App.ui.chip({
        label: text,
        truncate: true,
        lead: lead,
        onRemove: cancelPendingQueued,
        removeLabel: 'Cancel queued message',
        removeTestid: 'pending-queued-cancel',
        testid: 'pending-queued'
      });

      pendingQueuedRegionEl.appendChild(pendingQueuedEl);
    }

    // Remove the pinned chip from the DOM (idempotent). Does NOT touch the
    // held text in pendingQueuedMessages — callers manage that explicitly.
    function clearPendingQueued() {
      if (pendingQueuedEl && pendingQueuedEl.parentNode) {
        pendingQueuedEl.parentNode.removeChild(pendingQueuedEl);
      }
      pendingQueuedEl = null;
    }

    // F09-04: cancel (×) — discard the held message for the current session
    // and remove the chip. Purely local: nothing was sent to the backend, so
    // no turn runs for the discarded message.
    function cancelPendingQueued() {
      var a = chatState.activeId();
      if (a) delete state.pendingQueuedMessages[a];
      // WCAG 2.4.3: the cancel button held focus when it was used; the composer input takes it.
      var hadFocus = !!(pendingQueuedEl && pendingQueuedEl.contains(document.activeElement));
      clearPendingQueued();
      if (hadFocus && ctx.composer.input) ctx.composer.input.focus();
    }

    return {
      showPendingQueued: showPendingQueued,
      clearPendingQueued: clearPendingQueued,
      cancelPendingQueued: cancelPendingQueued
    };
  }

  window.App.chat.holdQueue = { create: create };
})();
