// App.chat.send -- the send path: the composer's send(), the normal-turn performSend, the held
// message's sendHeld, setInputValue, and the busy and Stop-control helpers (M31 F6 L02, split
// out of areas/chat.js, moved verbatim apart from the ctx./state. prefixes).
//
// Exposes: isCurrentBusy, updateStopControl, performSend, sendHeld, setInputValue, send.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var state = ctx.state;
    var chatState = ctx.chatState;
    var inputEl = ctx.inputEl;
    var sendBtn = ctx.sendBtn;
    var stopBtn = ctx.stopBtn;
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
      if (!stopBtn) return;
      stopBtn.hidden = !isCurrentBusy();
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
    function performSend(text) {
      var payload = { message: text };
      var displayText = text;
      if (ctx.attachments.staged().length) {
        payload.images = ctx.attachments.staged();
        displayText = text ? text + ' [image]' : '[image]';
        ctx.attachments.clearStagedImages();
      }
      ctx.transcript.addMsg('user', displayText, 'You');
      ctx.ws().send(JSON.stringify(payload));
      // Keyed on activeId() (AC6): the joined session (the `done` handler's
      // held message also comes through here, on the joined path).
      var active = chatState.activeId();
      if (active) {
        state.inFlightSessions[active] = true;
        state.ownTurn[active] = true;
      }
      sendBtn.disabled = true;
      updateStopControl();
      ctx.transcript.showThinking();
    }

    // Send the held message of a session through the normal send path. Shared
    // by the `done` handler and a session_updated re-join's reply, so the two
    // cannot drift.
    function sendHeld(sid) {
      var held = state.pendingQueuedMessages[sid];
      delete state.pendingQueuedMessages[sid];
      ctx.holdQueue.clearPendingQueued();
      performSend(held);
    }

    // Every scripted write to the composer's text goes through here, so the
    // textarea re-fits (a cleared draft drops back to two rows).
    function setInputValue(text) {
      inputEl.value = text;
      composer.fit();
    }

    function send() {
      var text = inputEl.value.trim();
      if (!text && !ctx.attachments.staged().length) return;
      // Blocked by health gate (agent deleted, provider missing, etc.) — never queue.
      if (state.sessionBannerEl || inputEl.disabled) return;
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
        delete state.pendingQueuedMessages[active];
        ctx.holdQueue.clearPendingQueued();
      }

      if (!isReset && isCurrentBusy()) {
        // One-slot CLIENT-HOLD queue (F09-04): hold exactly one message locally
        // while a turn runs. It is NOT sent to the backend now — the `done`
        // handler sends it via the normal path once the running turn finishes.
        // This keeps cancel trivial (nothing sent) and the chip pinned. A
        // second hold attempt while one is already held is ignored. Keyed on
        // activeId(): the client id while starting (the server uses it as the
        // session id), so a second Send while starting is held, never sent
        // as a plain message (AC6).
        if (!active) return;
        if (state.pendingQueuedMessages[active]) return;
        state.pendingQueuedMessages[active] = text;
        // The hold queue carries text only (F09-04 predates image attach) —
        // attach-while-a-turn-is-running is explicitly out of scope for L08
        // (the attach handler below already ignores staging while busy, but
        // this guards the rare race where a turn starts busy between staging
        // and send).
        ctx.attachments.clearStagedImages();
        setInputValue('');
        ctx.holdQueue.showPendingQueued(text);
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

    return {
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
