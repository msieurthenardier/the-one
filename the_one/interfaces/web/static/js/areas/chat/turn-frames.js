// App.chat.turnFrames -- the frames that render a turn, behind the socket's frame gate: user,
// assistant, thinking, tool_call, tool_result, system, usage, step_limit, done, cancelled, and the sign-in
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
    var agentDrawer = ctx.agentDrawer;

    var NOTE_TOOLS = { save_note: true, update_note: true, forget_note: true };
    var ROUTINE_TOOLS = { schedule_routine: true, change_routine: true, cancel_routine: true };

    function handleSystem(data) {
      if (data.content === 'Loading model...') {
        // Server will run `agent.step` only AFTER the load finishes — until
        // then, suppress the "thinking" indicator we optimistically showed
        // on send so the operator sees a single, accurate state. The line is an
        // App.ui.thinking handle the transcript keeps (DD11 4: its timer stops on
        // settle, on any log wipe and when the turn ends).
        ctx.transcript.showModelLoading();
      } else if (data.content === 'Model loaded.') {
        if (!ctx.transcript.settleModelLoading('Model loaded.')) {
          ctx.transcript.addMsg('system', data.content);
        }
        // Restore the "thinking" state — the agent step is about to run
        // and we still owe the user a response indicator until the first
        // chunk arrives.
        var loadedActive = chatState.activeId();
        if (loadedActive && state.inFlightSessions[loadedActive]) {
          ctx.turnWork.begin();
        }
      } else {
        ctx.transcript.dropModelLoading();
        // Every other system frame ends the turn (the work group folds, or goes if empty).
        ctx.turnWork.onSystemEnd();
        if (ctx.transcript.isAgentError(data.content)) {
          ctx.transcript.addAgentError(data.content);
        } else {
          ctx.transcript.addMsg('system', data.content);
        }
        var errActive = chatState.activeId();
        if (errActive && state.inFlightSessions[errActive]) {
          delete state.inFlightSessions[errActive];
          // M36 F1 L04: clearLiveRefresh wipes the own-turn flag AND a re-join that waited for
          // this turn (a settings push that landed meanwhile); that one must still run, so it
          // is read first and performed after the turn's reset below.
          var waitedForTurn = !!state.refreshAfterTurn[errActive];
          ctx.sessionFlow.clearLiveRefresh(errActive);
          // Also clear any pending queued message — the session is no longer
          // processing so the queue slot is moot (the error terminated the turn).
          // L10a: the whole queue drops with a muted notice; nothing is sent after a failed turn.
          var errHeld = ctx.holdQueue.discardAll(errActive);
          ctx.holdQueue.clearPendingQueued();
          if (errHeld) ctx.transcript.addDiscardedNotice(errHeld);
          ctx.send.updateStopControl();
          ctx.applyComposerState();
          // A re-join that waited for this turn (a push that landed meanwhile) runs now.
          if (waitedForTurn) ctx.sessionFlow.rejoinForUpdate(errActive);
        }
      }
    }

    function handle(data) {
      if (data.type === 'user') {
        // M10 F05 L05 / M11 F06 L04: visibility and peer_name ride the live event; the
        // transcript's addUserEvent owns the bubble (routine marker, source prefix).
        // A new user message ends the previous turn (its work group closes in place).
        ctx.turnWork.onUserEvent();
        ctx.transcript.addUserEvent(data);
        // M33 F1 L7: a routine run in the bound chat is a turn in flight that this window did
        // not start: Stop works and sends are held (never ownTurn), the work group starts
        // after the bubble. Gated on the frame's own session id, like the chat's other frames.
        // M36 F2 L5: so is the turn after an approved proposal (`approved` only; the
        // `approved_no_turn` and `dismissed` marks start no turn).
        if ((data.source === 'routine' || data.proposal_event === 'approved') && data.session_id &&
            data.session_id === chatState.boundId()) {
          state.inFlightSessions[data.session_id] = true;
          ctx.send.updateStopControl();
          ctx.applyComposerState();
          ctx.turnWork.begin();
        }
      }
      else if (data.type === 'assistant_chunk') ctx.turnWork.onText(data, false);
      else if (data.type === 'assistant') {
        // Direct-action shortcut path (non-streaming). Server only emits
        // this when no chunks fired. The text is the pending text of the pass; the reply
        // bubble is built at `done` (M10 F05 L05: its visibility is carried through).
        ctx.turnWork.onText(data, true);
      }
      else if (data.type === 'thinking') ctx.turnWork.onThinking(data);
      else if (data.type === 'tool_call') {
        if (data.tool_call_id) state.liveToolNames[data.tool_call_id] = data.name;
        ctx.turnWork.onToolCall(data);
      }
      else if (data.type === 'tool_result') {
        // M27 F3 L2: a note tool changed the notes; the panel re-fetches.
        if (NOTE_TOOLS[state.liveToolNames[data.tool_call_id]]) agentDrawer.refreshNotes();
        // M33 F4 L5: a routine tool changed the routines; the group re-fetches.
        // An error result changed nothing.
        if (ROUTINE_TOOLS[state.liveToolNames[data.tool_call_id]] && !data.is_error) agentDrawer.refreshRoutines();
        // A delivered (peer-visible) result stays a top-level bubble (M23 F02 L03); any other
        // result goes into the work group under its call.
        ctx.turnWork.onToolResult(data);
      }
      else if (data.type === 'system') handleSystem(data);
      else if (data.type === 'usage') {
        App.perf.mark('telemetry-update:start');
        ctx.telemetry.update(data);
        App.perf.mark('telemetry-update:end');
        App.perf.measure('telemetry-update', 'telemetry-update:start', 'telemetry-update:end');
      }
      else if (data.type === 'auth_required') ctx.signIn.onAuthRequired(data);
      else if (data.type === 'auth_resolved') ctx.signIn.onAuthResolved(data);
      else if (data.type === 'auth_failed') ctx.signIn.onAuthFailed(data);
      else if (data.type === 'step_limit') {
        // DD8 F2: arrives immediately before `done`. The work group folds and reads "Paused at
        // the step limit"; the `done` that follows promotes nothing. A muted line follows.
        // Broadcast-only server side, so a re-join renders none; a held queued message at
        // `done` leaves it in place.
        ctx.turnWork.onStepLimit();
        ctx.transcript.addStepLimitNotice(data.steps, state.currentAgentName);
      }
      else if (data.type === 'done') {
        ctx.transcript.dropModelLoading();
        // End of agent step: the reply lands now (only from "working"), before a held
        // message is sent, so it sits above the queued message's bubble.
        ctx.turnWork.onDone();
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
        var held = sid && ctx.holdQueue.count(sid) > 0;
        var canDrain = held && ctx.socket.socketOpen() && !state.rebinding;
        if (canDrain) {
          ctx.send.sendHeld(sid);
        } else {
          // No held message — normal idle reset.
          if (sid) {
            delete state.inFlightSessions[sid];
            delete state.ownTurn[sid];
          }
          ctx.holdQueue.refresh();
          ctx.send.updateStopControl();
          ctx.applyComposerState();
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
        // The work group folds its pending text and reads "Stopped" (no reply bubble; with no
        // open group nothing changes and only the notices are added).
        ctx.transcript.dropModelLoading();
        ctx.turnWork.onCancelled();
        var cancelledActive = chatState.activeId();
        // B9: "Stopped." after the sealed reply, then "Queued message discarded." when a held
        // message went with it: the Stop click recorded one, or one is still held here (a Stop
        // from another tab never ran this tab's click handler). Neither line is stored.
        ctx.transcript.addStoppedNotice();
        var cancelledHeld = cancelledActive
          ? Math.max(state.discardedOnStop[cancelledActive] || 0, ctx.holdQueue.count(cancelledActive))
          : 0;
        if (cancelledHeld) ctx.transcript.addDiscardedNotice(cancelledHeld);
        if (cancelledActive) delete state.discardedOnStop[cancelledActive];
        if (cancelledActive) {
          delete state.inFlightSessions[cancelledActive];
          delete state.ownTurn[cancelledActive];
          // Cancel also discards any pending queued message (DD4 sub-decision:
          // "stop" means stop everything). Both the optimistic click handler and
          // this arrival path clear it so a race between the two is safe.
          ctx.holdQueue.discardAll(cancelledActive);
          ctx.holdQueue.clearPendingQueued();
        }
        ctx.send.updateStopControl();
        ctx.applyComposerState();
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
