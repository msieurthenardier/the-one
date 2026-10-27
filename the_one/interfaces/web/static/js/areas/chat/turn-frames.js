// App.chat.turnFrames -- the frames that render a turn, behind the socket's frame gate: user,
// assistant, thinking, tool_call, tool_result, system, usage, done, cancelled, and the sign-in
// frames delegated to App.chat.signIn (M31 F6 L02, split out of areas/chat.js, moved verbatim
// apart from the ctx./state. prefixes). handle(data) is the old tail of sock.onmessage.
//
// Exposes: handle, handleSystem.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var state = ctx.state;
    var chatState = ctx.chatState;
    var messagesEl = ctx.messagesEl;
    var sendBtn = ctx.sendBtn;
    var content = ctx.content;
    var agentDrawer = ctx.agentDrawer;

    var NOTE_TOOLS = { save_note: true, update_note: true, forget_note: true };

    function handleSystem(data) {
      if (data.content === 'Loading model...') {
        // Server will run `agent.step` only AFTER the load finishes — until
        // then, suppress the "thinking" indicator we optimistically showed
        // on send so the operator sees a single, accurate state.
        ctx.transcript.hideThinking();
        var loadEl = document.createElement('div');
        // `system-model-loading` is a system-only class so the
        // `Model loaded.` handler below can target this row exclusively
        // without accidentally matching the thinking indicator (which
        // also carries `.model-loading` for shared dot-animation styling).
        loadEl.className = 'msg system model-loading system-model-loading';
        // DOM-built (M25 F4 L4b; was a static innerHTML literal).
        var loadTextEl = document.createElement('span');
        loadTextEl.className = 'model-loading-text';
        loadTextEl.textContent = 'Loading model';
        var dotEl = document.createElement('span');
        dotEl.className = 'model-loading-dots';
        loadEl.appendChild(loadTextEl);
        loadEl.appendChild(dotEl);
        messagesEl.appendChild(loadEl);
        ctx.transcript.scrollToBottomIfPinned();
        var frames = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];
        var frameIdx = 0;
        loadEl._dotTimer = setInterval(function () { frameIdx = (frameIdx + 1) % frames.length; dotEl.textContent = ' ' + frames[frameIdx]; }, 120);
      } else if (data.content === 'Model loaded.') {
        var loadingMsg = messagesEl.querySelector('.system-model-loading');
        if (loadingMsg) {
          if (loadingMsg._dotTimer) clearInterval(loadingMsg._dotTimer);
          loadingMsg.classList.remove('model-loading');
          loadingMsg.classList.remove('system-model-loading');
          loadingMsg.textContent = 'Model loaded.';
        } else { ctx.transcript.addMsg('system', data.content); }
        // Restore the "thinking" state — the agent step is about to run
        // and we still owe the user a response indicator until the first
        // chunk arrives.
        var loadedActive = chatState.activeId();
        if (loadedActive && state.inFlightSessions[loadedActive]) {
          ctx.transcript.showThinking();
        }
      } else {
        ctx.transcript.hideThinking();
        ctx.transcript.addMsg('system', data.content);
        var errActive = chatState.activeId();
        if (errActive && state.inFlightSessions[errActive]) {
          delete state.inFlightSessions[errActive];
          ctx.sessionFlow.clearLiveRefresh(errActive);
          // Also clear any pending queued message — the session is no longer
          // processing so the queue slot is moot (the error terminated the turn).
          delete state.pendingQueuedMessages[errActive];
          ctx.holdQueue.clearPendingQueued();
          ctx.send.updateStopControl();
          if (!state.sessionBannerEl) sendBtn.disabled = false;
        }
      }
    }

    function handle(data) {
      if (data.type === 'user') {
        var cls = data.source === 'api' ? 'user api' : 'user';
        // M10 F05 L05: forward visibility from the live user event.
        // ``data.visibility`` is undefined on today's live broadcasts
        // (known limitation: storage-edge shim runs post-step; live
        // broadcast emits inline within step) — the channel is wired
        // for the follow-on live-broadcast tagging leg.
        // M11 F06 L04: forward peer_name from the live broadcast onto the
        // attribution + bubble side. Peer-attributed inbound user events
        // (per F6 L3 dispatcher binding + F6 L2 codec projection) carry
        // data.peer_name. Operator-typed user events have no peer_name.
        var liveAttribution = data.peer_name || 'You';
        ctx.transcript.addMsg(cls, (data.source && data.source !== 'web' ? '[' + data.source + '] ' : '') + data.content, liveAttribution, { visibility: data.visibility, peerName: data.peer_name });
      }
      else if (data.type === 'assistant_chunk') ctx.transcript.onAssistantChunk(data);
      else if (data.type === 'assistant') {
        // Direct-action shortcut path (non-streaming). Server only emits
        // this when no chunks fired. Streaming path skips it server-side.
        // Uniform finalize call — no-op when currentStreamingMsg is null.
        ctx.transcript.hideThinking();
        ctx.transcript.finalizeStreamingBubble();
        ctx.transcript.clearStreamingVisibility();
        // M10 F05 L05: forward visibility from the live assistant event.
        ctx.transcript.addMsg('assistant', data.content, state.currentAgentName || 'agent', { visibility: data.visibility });
      }
      else if (data.type === 'thinking') {
        // M16 F10 L05 (DD2 reveal-after): the settled turn's thinking
        // disclosure. Fires AFTER the answer streamed, so the loading spinner
        // is already hidden by the assistant/chunk path — do NOT call
        // hideThinking()/finalizeStreamingBubble() (that would disturb the
        // spinner state machine or an in-progress bubble). Just append the
        // disclosure in stream order.
        ctx.transcript.renderThinking(data);
      }
      else if (data.type === 'tool_call') {
        if (data.tool_call_id) state.liveToolNames[data.tool_call_id] = data.name;
        ctx.transcript.hideThinking();
        // Iteration boundary — finalize the current streaming bubble so
        // iteration N+1's chunks land in a fresh bubble (markdown
        // rendering + reset of currentStreamingMsg both happen inside).
        ctx.transcript.finalizeStreamingBubble();
        ctx.transcript.clearStreamingVisibility();
        // L03: route into the trace shell for this assistant turn.
        var argsText = '> ' + data.name + '(' + Object.entries(data.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')';
        var liveTrace = ctx.transcript.getOrCreateTrace(data.parent_message_id);
        // M10 F05 L05: forward visibility from the live tool_call event.
        var liveMsg = ctx.transcript.buildToolMsg(argsText, false, data.tool_call_id, { visibility: data.visibility });
        if (liveTrace) {
          App.chat.appendToTrace(liveTrace, liveMsg);
        } else {
          // Legacy / null parent_message_id — render standalone.
          messagesEl.appendChild(liveMsg);
        }
        ctx.transcript.scrollToBottomIfPinned();
      }
      else if (data.type === 'tool_result') {
        // M27 F3 L2: a note tool changed the notes; the panel re-fetches.
        if (NOTE_TOOLS[state.liveToolNames[data.tool_call_id]]) agentDrawer.refreshNotes();
        // Iteration boundary — finalize the current streaming bubble.
        ctx.transcript.finalizeStreamingBubble();
        ctx.transcript.clearStreamingVisibility();
        // M23 F02 L03: a delivered (peer-visible) tool result is
        // promoted to a top-level bubble live too, matching renderHistory
        // — otherwise a live-vs-reload rendering gap would just move from
        // the operator-only marker (fixed above) to this accordion
        // placement instead.
        if (ctx.transcript.isDeliveredToolResult(data)) {
          ctx.transcript.appendDeliveredToolMsg(data, state.currentAgentName || 'agent', new Date().toISOString());
        } else {
          // L03: route into the trace shell for this assistant turn.
          var resTrace = ctx.transcript.getOrCreateTrace(data.parent_message_id);
          // M10 F05 L05: forward visibility from the live tool_result event.
          var resMsg = ctx.transcript.buildToolMsg(data.content, data.is_error, data.tool_call_id, { visibility: data.visibility });
          if (resTrace) {
            App.chat.appendToTrace(resTrace, resMsg);
          } else {
            messagesEl.appendChild(resMsg);
          }
        }
        ctx.transcript.scrollToBottomIfPinned();
      }
      else if (data.type === 'system') handleSystem(data);
      else if (data.type === 'usage') App.chat.updateTelemetry(content, data);
      else if (data.type === 'auth_required') ctx.signIn.onAuthRequired(data);
      else if (data.type === 'auth_resolved') ctx.signIn.onAuthResolved(data);
      else if (data.type === 'auth_failed') ctx.signIn.onAuthFailed(data);
      else if (data.type === 'done') {
        ctx.transcript.hideThinking();
        // End of agent step — finalize so the streaming bubble swaps
        // its accumulated text for the markdown-rendered fragment, and
        // the next user message starts a fresh streaming round.
        ctx.transcript.finalizeStreamingBubble();
        ctx.transcript.clearStreamingVisibility();
        // AC6: the joined session (activeId); a held message goes out on
        // the joined path (performSend), never as a start.
        var sid = chatState.activeId();
        // F09-02 (client-hold): the held queued message was NOT sent during
        // the turn — it waited locally. Now the running turn has finished, so
        // dequeue it and send it via the NORMAL send path. This renders the
        // user bubble in the correct order (after this turn's response, before
        // the queued turn's response) and starts the queued turn — the sender's
        // optimistic render + the backend's sender-exclusion (app.py) align
        // because it flows through the same path as a normal send.
        var held = sid ? state.pendingQueuedMessages[sid] : null;
        if (held) {
          ctx.send.sendHeld(sid);
        } else {
          // No held message — normal idle reset.
          if (sid) {
            delete state.inFlightSessions[sid];
            delete state.ownTurn[sid];
          }
          ctx.holdQueue.clearPendingQueued();
          ctx.send.updateStopControl();
          if (!state.sessionBannerEl) sendBtn.disabled = false;
        }
        ctx.sessionFlow.refreshSessionList();
        // A session_updated waited for this turn: re-join now (a held message
        // started a new own turn above, so the wait continues).
        if (sid && state.refreshAfterTurn[sid] && !state.ownTurn[sid]) {
          delete state.refreshAfterTurn[sid];
          ctx.sessionFlow.rejoinForUpdate(sid);
        }
      }
      else if (data.type === 'cancelled') {
        // F7 L04: cancel — mirror the FULL done reset (binding per design review).
        // The partial assistant bubble was already committed by the backend (leg 3);
        // finalizeStreamingBubble() seals any streaming tail still in the pacing queue.
        ctx.transcript.hideThinking();
        ctx.transcript.finalizeStreamingBubble();
        ctx.transcript.clearStreamingVisibility();
        var cancelledActive = chatState.activeId();
        if (cancelledActive) {
          delete state.inFlightSessions[cancelledActive];
          delete state.ownTurn[cancelledActive];
          // Cancel also discards any pending queued message (DD4 sub-decision:
          // "stop" means stop everything). Both the optimistic click handler and
          // this arrival path clear it so a race between the two is safe.
          delete state.pendingQueuedMessages[cancelledActive];
          ctx.holdQueue.clearPendingQueued();
        }
        ctx.send.updateStopControl();
        if (!state.sessionBannerEl) sendBtn.disabled = false;
        ctx.sessionFlow.refreshSessionList();
        if (cancelledActive && state.refreshAfterTurn[cancelledActive]) {
          delete state.refreshAfterTurn[cancelledActive];
          ctx.sessionFlow.rejoinForUpdate(cancelledActive);
        }
      }
    }

    return {
      handle: handle,
      handleSystem: handleSystem
    };
  }

  window.App.chat.turnFrames = { create: create };
})();
