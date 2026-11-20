// App.chat.send -- the send path: the composer's send(), the normal-turn performSend, the held
// message's sendHeld, setInputValue, and the busy and Stop-control helpers (M31 F6 L02, split
// out of areas/chat.js, moved verbatim apart from the ctx./state. prefixes).
//
// Exposes: isCurrentBusy, updateStopControl, performSend, sendHeld, setInputValue, send, sendText.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var state = ctx.state;
    var chatState = ctx.chatState;
    var composer = ctx.composer;

    // Busy while starting (the first turn is on its way, whatever the
    // in-flight map says), else when the active session has a turn in flight.
    function isCurrentBusy() {
      if (chatState.state().name === 'starting') return true;
      var a = chatState.activeId();
      return !!(a && state.inFlightSessions[a]);
    }

    // Show/hide the stop button derived from isCurrentBusy() so that any code
    // path that clears inFlightSessions (onclose, session-switch, done, cancelled)
    // automatically hides it without extra plumbing. Call this after any mutation
    // to inFlightSessions or after the session state changes.
    function updateStopControl() {
      composer.setBusy(isCurrentBusy());
      // M36 F2 L6: the proposal cards' buttons follow the same busy state (a polled read).
      if (ctx.proposalCards) ctx.proposalCards.refreshBusy();
    }

    // Normal turn-send path: optimistic user bubble, transmit, mark in-flight,
    // show the thinking indicator. Shared by send() (direct send) and the WS
    // `done` handler (dequeue of a held message) so the two paths can never
    // diverge. Does NOT touch the input value — callers manage that (the direct
    // path clears it; the dequeue path must not clobber what the user is typing).
    //
    // M16 F12 L08: when image(s) are staged, the outgoing payload gains an
    // `images` field (text-only sends stay byte-identical — no `images` key).
    // The optimistic bubble mirrors the backend's content_to_text projection
    // ("text [image]", or just "[image]" with no text) so the sender sees the
    // same shape the server will broadcast/persist. Staged images are
    // cleared after every send, sent or held (HAT fix round 2: now the
    // whole `stagedImages` array, not a single-shot slot).
    function performSend(text, opts) {
      var payload = { message: text };
      var displayText = text;
      if (!(opts && opts.textOnly) && ctx.attachments.staged().length) {
        payload.images = ctx.attachments.staged();
        displayText = text ? text + ' [image]' : '[image]';
        ctx.attachments.clearStagedImages();
      }
      ctx.turnWork.onUserEvent();
      ctx.transcript.addMsg('user', displayText, 'You');
      ctx.ws().send(JSON.stringify(payload));
      // Keyed on activeId() (AC6): the joined session (the `done` handler's
      // held message also comes through here, on the joined path).
      var active = chatState.activeId();
      if (active) {
        state.inFlightSessions[active] = true;
        state.ownTurn[active] = true;
      }
      updateStopControl();
      ctx.turnWork.begin();
    }

    // Send the held message of a session through the normal send path. Shared
    // by the `done` handler and a session_updated re-join's reply, so the two
    // cannot drift.
    function sendHeld(sid) {
      // A closed or unbound socket keeps every held message (a drain must never reach it).
      if (!ctx.socket.socketOpen() || state.rebinding) return;
      var held = ctx.holdQueue.shift(sid);
      if (held === null) return;
      // The first goes now; the rest stay chipped, in order, for the following turn ends.
      ctx.holdQueue.refresh();
      performSend(held, { textOnly: true });
    }

    // Every scripted write to the composer's text goes through here, so the
    // textarea re-fits (a cleared draft drops back to two rows).
    function setInputValue(text) {
      composer.setValue(text);
    }

    // The composer's onSend (Enter or the Send button) with the raw value: the control calls it
    // for a busy or empty Enter too, so the area's guards (and its clearing on success) are here.
    function send(raw) {
      var text = String(raw === undefined ? composer.getValue() : raw).trim();
      if (!text && !ctx.attachments.staged().length) return;
      // Blocked by health gate (agent deleted, provider missing, etc.) — never queue.
      if (state.bannerActive || composer.input.disabled) return;
      var st = chatState.state().name;
      // Nothing open, or a join still in flight: nothing a message could go
      // to (an unbound socket would auto-create a default-agent session).
      // The text stays in the composer.
      if (st === 'idle' || st === 'joining') return;

      var isReset = (text === '/reset');
      // /reset clears a conversation; a chat that does not exist yet has
      // none. Never sent, never held (AC6).
      if (isReset && (st === 'pending' || st === 'starting')) {
        ctx.sessionFlow.showNotice('Send a message to start the chat first');
        return;
      }
      var active = chatState.activeId();
      // F09-04: /reset is a control command — never hold it, and it wipes the
      // conversation, so discard any held queued message + chip first so a
      // stale hold can't fire after the context is cleared.
      if (isReset && active) {
        ctx.holdQueue.discardAll(active);
        ctx.holdQueue.clearPendingQueued();
      }

      if (!isReset && isCurrentBusy()) {
        // CLIENT-HOLD queue (F09-04; many messages since L10a, capped at 10): hold
        // each message locally, in order, while a turn runs. It is NOT sent to the backend now — the `done`
        // handler sends it via the normal path once the running turn finishes.
        // This keeps cancel trivial (nothing sent) and the chip pinned. Each
        // `done` sends the first. Keyed on
        // activeId(): the client id while starting (the server uses it as the
        // session id), so a second Send while starting is held, never sent
        // as a plain message (AC6).
        if (!active) return;
        // At the cap nothing is held and the text stays in the box (a note says why).
        if (!ctx.holdQueue.push(active, text)) {
          ctx.holdQueue.showFull();
          return;
        }
        // The hold queue carries text only (F09-04 predates image attach) —
        // attach-while-a-turn-is-running is explicitly out of scope for L08
        // (the attach handler below already ignores staging while busy, but
        // this guards the rare race where a turn starts busy between staging
        // and send).
        ctx.attachments.clearStagedImages();
        setInputValue('');
        ctx.holdQueue.refresh();
        return;
      }

      // AC8: a closed socket, or one not re-bound yet after a reconnect,
      // keeps the text: a message must never reach an unbound socket.
      if (!ctx.socket.socketOpen() || state.rebinding) return;

      if (st === 'pending') {
        if (ctx.sessionFlow.startSend(text)) setInputValue('');
        return;
      }
      performSend(text);
      setInputValue('');
    }

    // Send (or hold, while a turn runs) a fixed text on an operator's behalf, as the step-limit
    // notice's Continue does (L10d). It shares send()'s guards, but never reads or clears the
    // composer text or the staged images. True only when the text was sent or held.
    function sendText(text) {
      if (state.bannerActive || composer.input.disabled) return false;
      var st = chatState.state().name;
      if (st !== 'joined' && !isCurrentBusy()) return false;
      var active = chatState.activeId();
      if (!active) return false;
      if (isCurrentBusy()) {
        if (!ctx.holdQueue.push(active, text)) {
          ctx.holdQueue.showFull();
          return false;
        }
        ctx.holdQueue.refresh();
        return true;
      }
      if (!ctx.socket.socketOpen() || state.rebinding) return false;
      performSend(text, { textOnly: true });
      return true;
    }

    return {
      sendText: sendText,
      isCurrentBusy: isCurrentBusy,
      updateStopControl: updateStopControl,
      performSend: performSend,
      sendHeld: sendHeld,
      setInputValue: setInputValue,
      send: send
    };
  }

  window.App.chat.send = { create: create };
})();
