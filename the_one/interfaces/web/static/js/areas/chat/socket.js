// App.chat.socket -- the chat WebSocket: connect and reconnect, onopen, onclose, and the one
// sock.onmessage entry with the session frames (M31 F6 L02, split out of areas/chat.js, moved
// verbatim apart from the ctx./state. prefixes).
//
// The frame order is the contract (leg 02, DD3): (1) boundOn = sock on session_joined, (2) the
// session lifecycle frames, each returning, (3) the popup close for auth_resolved / auth_failed,
// (4) the frame gate chatState.onFrame(data).accept, (5) the gated frames, in
// App.chat.turnFrames. `ws` lives here; ctx.ws() returns the live socket.
//
// Exposes: connect, ws, socketOpen, sendBinding.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var state = ctx.state;
    var chatState = ctx.chatState;
    var messagesEl = ctx.messagesEl;
    var agentDrawer = ctx.agentDrawer;

    var ws = null;
    var reconnectTimer = null;
    var toSessionSummary = ctx.toSessionSummary;

    // AC8: the socket the current binding was made on (a start_session, join
    // or leave sent, or a session_joined received). Reconnect actions run
    // only for a binding made on an EARLIER socket.
    var boundOn = null;

    // 0.3: false only when the agents store is loaded and ok and holds no agent of this name
    // (a deleted agent). An unloaded store (a cold deep link) says "may exist": the eager
    // resolve still runs.
    // M36 F1 L04: through App.chat.agentKind. GleepGlorp (no agents row, no context-window
    // route) never fetches.
    function agentMayExist(name) {
      var kind = App.chat.agentKind(name).kind;
      return kind === 'agent' || kind === 'loading';
    }

    function socketOpen() {
      return !!(ws && ws.readyState === WebSocket.OPEN);
    }

    // start_session, join and leave (un)bind this socket: record which one
    // (AC8's per-socket binding record).
    function sendBinding(frame) {
      ws.send(JSON.stringify(frame));
      boundOn = ws;
    }

    function connect() {
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      var proto = location.protocol === 'https:' ? 'wss' : 'ws';
      var sock = new WebSocket(proto + '://' + location.host + '/ws');
      ws = sock;

      sock.onopen = function () {
        if (sock !== ws) { sock.close(); return; } // superseded before it opened
        state.firstListPending = true;
        var st = chatState.state();
        var boundEarlier = boundOn !== null && boundOn !== sock;
        // AC8: while starting, re-send the SAME start_session at once (never
        // `join`); the server's idempotency joins or creates it exactly once.
        if (st.name === 'starting' && boundEarlier) {
          var act = chatState.reconnectAction(null, true);
          if (act.send === 'start_session' && act.frame) sendBinding(act.frame);
        }
        // Joined or joining: the fresh socket is unbound until the first
        // session_list re-joins (or idles); Send and Stop wait.
        if (st.name === 'joined' || st.name === 'joining') state.rebinding = true;
        ctx.refreshAgentsAndSetup()
          .then(function () {
            if (sock === ws && sock.readyState === WebSocket.OPEN) {
              sock.send(JSON.stringify({ action: 'list_sessions' }));
            }
          });
      };

      sock.onclose = function () {
        if (sock !== ws) return; // a superseded socket
        // AC6: while starting, keep the held slot, busy and the thinking
        // indicator: the re-sent start_session restores is_processing.
        if (chatState.state().name !== 'starting') {
          // Re-enable input so a mid-response disconnect doesn't strand the UI; the
          // auto-reconnect below brings the WS back. The work group stays as it is (the
          // re-join's replay rebuilds the log).
          // Disconnect drops every in-flight broadcast — clear both maps so neither
          // the held-message queue nor the stop control get stuck after reconnect.
          for (var k in state.inFlightSessions) delete state.inFlightSessions[k];
          for (var k2 in state.pendingQueuedMessages) ctx.holdQueue.discardAll(k2);
          ctx.sessionFlow.clearLiveRefresh();
          ctx.holdQueue.clearPendingQueued();
          ctx.send.updateStopControl();
          ctx.applyComposerState();
          // M36 F2 L6: the turn is gone with the socket, so a held proposal card lands.
          ctx.proposalCards.turnEnded();
        }
        reconnectTimer = setTimeout(connect, 2000);
      };

      sock.onmessage = function (e) {
        if (sock !== ws) return;
        var data = JSON.parse(e.data);
        if (data.type === 'session_joined') boundOn = sock;

        if (data.type === 'sessions_changed') {
          // Server push (a connector chat, another tab, a delete, a purge):
          // refresh the local list and the store only. Never the rebind logic,
          // the idle rules, a render call or the open conversation.
          state.sessions = data.sessions || [];
          ctx.sessionFlow.pruneDrafts(state.sessions.map(function (s) { return s.id; }));
          App.store.prime('sessions', state.sessions.map(toSessionSummary));
          return;
        }

        if (data.type === 'config_changed') {
          // An approved GleepGlorp change reached the stored configuration (any window, any
          // state, so before the gate): the editors, list and drawer follow it (M36 F2 L7).
          App.approvals.record(data);
          return;
        }

        if (data.type === 'gleepglorp_changed') {
          // GleepGlorp's settings changed (any tab, any state, so before the gate): update the
          // client's copy, then follow it. A joined GleepGlorp chat re-joins (deferred until
          // its own turn ends) so its banner and composer follow. A pending one, the picker and
          // the drawer re-render from chat.js's App.gleepglorp subscription (prime notifies).
          // A notes-only push (L06: a delete or Clear all in Settings > GleepGlorp) carries
          // no settings: it only tells an open Memory list to reload.
          if (!data.settings) {
            window.dispatchEvent(new Event('gleepglorp-notes-changed'));
            return;
          }
          App.gleepglorp.prime(data.settings);
          if (chatState.state().name === 'joined' && state.currentAgentName === App.chat.GLEEPGLORP) {
            ctx.sessionFlow.requestRefresh(chatState.boundId());
          }
          return;
        }

        if (data.type === 'session_updated') {
          // A connector turn finished in a chat this socket is subscribed to.
          // Joining that very id: re-join once more after its reply (the update
          // can land between the server's join read and its reply). Otherwise
          // only the joined chat reacts (the gate), and only for its own id.
          var updState = chatState.state();
          if (updState.name === 'joining' && updState.id === data.session_id) {
            state.refreshAfterJoin = data.session_id;
            return;
          }
          if (data.session_id !== chatState.boundId() || !chatState.accepts(data)) return;
          ctx.sessionFlow.requestRefresh(data.session_id);
          return;
        }

        if (data.type === 'session_list') {
          state.sessions = data.sessions || [];
          state.listSeen = true;
          ctx.sessionFlow.pruneDrafts(state.sessions.map(function (s) { return s.id; }));
          // M25 F4 L1 (DD4): every session_list reply primes the store's
          // 'sessions' collection, mapped to the REST summary shape
          // (_session_summary), so a WebSocket-primed row and a REST-fetched
          // row never differ. While Chats is active the WebSocket is the
          // source; nothing here fetches. (A start_session join's refresh
          // lands here too: DD4's start_session invalidation row.)
          App.store.prime('sessions', state.sessions.map(toSessionSummary));
          // M25 F4 L4a (AC6): the prime above notifies the `sessions`
          // subscription, which renders the Chats list; nothing here renders
          // it a second time.
          // AC8: the first list on a fresh socket re-binds a joined or joining
          // state made on an earlier socket: re-join when the session is still
          // listed, else idle with a notice (never join an unknown id).
          var firstOnSocket = state.firstListPending;
          state.firstListPending = false;
          var listName = chatState.state().name;
          if (firstOnSocket && (listName === 'joined' || listName === 'joining')) {
            var ids = state.sessions.map(function (s) { return s.id; });
            var re = chatState.reconnectAction(ids, boundOn !== null && boundOn !== sock);
            if (re.send === 'join') {
              // joined/joining(id) -> joining(id): the same row stays
              // selected, so the list (rendered by the prime above) is current.
              sendBinding({ action: 'join', session_id: re.id });
              return;
            }
            if (re.toIdle) {
              // Deleted while the socket was down: idle, a notice, and the
              // idle rules below.
              state.rebinding = false;
              ctx.sessionFlow.clearConversation();
              ctx.sessionFlow.setWelcomeNotice(re.notice);
            }
            // Otherwise the binding was made on this socket already (a join
            // sent since it opened): its own reply clears `rebinding`.
          }
          // AC2b: the idle rules, on every list, only while idle.
          ctx.sessionFlow.runIdleRules();
          return;
        }

        if (data.type === 'session_joined') {
          var joinedEff = chatState.onFrame(data);
          if (!joinedEff.accept) {
            // A late reply to a superseded join or start (a start abandoned
            // by a pick may still have created its session: list it).
            if (joinedEff.refreshList) ctx.sessionFlow.refreshSessionList();
            return;
          }
          state.rebinding = false;
          state.liveToolNames = {};
          // Did this reply answer a session_updated re-join (or a session_updated
          // that landed while joining)? Both marks are consumed by any reply.
          var upd = state.updateRejoin && state.updateRejoin.id === data.session_id ? state.updateRejoin : null;
          var again = state.refreshAfterJoin === data.session_id;
          state.updateRejoin = null;
          state.refreshAfterJoin = null;
          if (joinedEff.startFailed) {
            ctx.sessionFlow.applyStartFailed(joinedEff);
            return;
          }
          var joinedId = data.session_id;
          if (joinedEff.fromStart) ctx.sessionFlow.promoteDraft(joinedId);
          App.perf.mark('session-join:received');
          App.router.sync('chat', joinedEff.sync);
          state.currentAgentName = data.agent_name;
          // M23 F02 L03: capture the joined session's connector platform
          // (undefined on a degraded-session payload's older clients / any
          // server that hasn't rolled this field out — falls back to null,
          // same as a genuine web-native session) BEFORE renderHistory runs,
          // since it reads currentSessionPlatform to gate tool-result
          // promotion.
          state.currentSessionPlatform = data.platform || null;
          state.joinedTitle = data.title || null;
          // The selection follows the join (joining -> joined; a start's
          // starting -> joined swap drops the pending row), and so does the
          // header (AC1: the title from the `sessions` store, falling back
          // to this payload's).
          ctx.renderChatsList();
          ctx.renderPane();
          ctx.telemetry.reset();
          // AC2/AC7: the first turn behaves like any turn. A start's join
          // with an empty history keeps the optimistic bubble; any other
          // join renders the history (an in-flight session's history already
          // holds the user event). A turn in flight renders its trailing turn
          // as running (the work group stays open for the live frames).
          var rendersHistory = joinedEff.render === 'history';
          if (rendersHistory) {
            ctx.transcript.renderHistory(data.history, data.agent_name,
              { trailing: data.is_processing ? 'working' : 'closed' });
          }
          state.startBubbleNodes = [];
          // M16 F06 L02: synchronously restore persisted last_usage into
          // the overlay so the token counts aren't lost on session reopen.
          // Uses a defensive read pattern (session_metadata may be absent).
          // max_context_tokens is 0 here (unknown until the seed resolves);
          // the bar will fill once setTelemetryMax runs async shortly after.
          var lastUsage = (data.session_metadata && data.session_metadata.last_usage) || null;
          if (lastUsage) {
            ctx.telemetry.update({
              input_tokens: lastUsage.input_tokens || 0,
              output_tokens: lastUsage.output_tokens || 0,
              context_tokens: lastUsage.context_tokens || 0,
              max_context_tokens: 0,
            });
          }
          ctx.setSessionHealth(data.status || 'ok', data.reason);
          // Sync per-session busy state to server ground truth
          // (`is_session_processing(session.id)`). Without this,
          // switching away from an in-flight session and back leaves
          // the prior `busy` flag stale — either stuck-disabled (turn
          // finished while away) or stuck-enabled (turn still running).
          // F09-04 (client-hold): clear any stale chip from a previous session,
          // then re-show it if THIS session still holds one. The held message is
          // client-only (no backend task) and keyed per session, so it is
          // decoupled from is_processing — do not delete it based on the busy
          // flag (session switch / cancel / dequeue manage its lifecycle).
          // A start's hold was keyed on its client id, which IS this id.
          ctx.holdQueue.clearPendingQueued();
          if (data.is_processing) {
            state.inFlightSessions[joinedId] = true;
            ctx.turnWork.begin();
          } else {
            delete state.inFlightSessions[joinedId];
            // A start whose turn never ran leaves no empty "Working" line behind.
            if (!rendersHistory) ctx.turnWork.dropEmpty();
          }
          var sentHeld = false;
          if (ctx.holdQueue.count(joinedId)) {
            if (upd && !data.is_processing) {
              // The re-join found the chat idle: the message held meanwhile goes now.
              ctx.send.sendHeld(joinedId);
              sentHeld = true;
            } else {
              ctx.holdQueue.showPendingQueued(ctx.holdQueue.list(joinedId));
            }
          }
          ctx.send.updateStopControl();
          ctx.showChrome();
          agentDrawer.setSessionMetadata(joinedId, data.session_metadata);
          agentDrawer.refreshNotes();
          agentDrawer.refreshRoutines();
          // F7 L04 eager-resolve: fetch the agent's max_context_tokens BEFORE the first user
          // message so the readout's `max:` field shows the real value (not 0). Closes F6.5
          // debrief AI #5. Fire-and-forget; a failure (400, a misconfigured provider) leaves
          // `max:` at its default until the first usage event arrives.
          // M31 F6 L05c (DD11 5, 0.3): the fetch is skipped when the join says the agent is
          // gone or unusable (status not ok: a request could only 404 or 400 in the console),
          // or when the loaded agents store has no such agent. The response is applied only
          // while the bound session and its agent are still the ones the join was for.
          if (state.currentAgentName && (data.status || 'ok') === 'ok' && agentMayExist(state.currentAgentName)) {
            var cwAgent = state.currentAgentName;
            var cwSession = joinedId;
            fetch('/api/agents/' + encodeURIComponent(cwAgent) + '/context-window')
              .then(function (r) { return r.ok ? r.json() : null; })
              .then(function (payload) {
                var unchanged = chatState.boundId() === cwSession && state.currentAgentName === cwAgent;
                if (unchanged && payload && payload.max_context_tokens) {
                  // M16 F06 L02: max-only seed — never re-zeros restored used-counts.
                  ctx.telemetry.setMax(payload.max_context_tokens);
                }
              })
              .catch(function () { /* best-effort; silent on failure */ });
          }
          // M08 F6 L06 HAT fix: scroll-to-bottom on session join/deep-link/
          // refresh. renderHistory() above ran while chrome was hidden
          // (clientHeight=0), so smart-scroll's pin check failed. After
          // showChrome flips visibility, jump unconditionally to the most
          // recent message — that's where the user expects to land when
          // they open a session.
          messagesEl.scrollTop = messagesEl.scrollHeight;
          // A session_updated re-join keeps an unpinned reader where they were.
          if (upd && !upd.pinned && !sentHeld) messagesEl.scrollTop = upd.scrollTop;
          // Still processing (another turn is running): re-join on its end.
          // Otherwise a session_updated that landed during the join re-joins now.
          if (data.is_processing) {
            if (upd || again) state.refreshAfterTurn[joinedId] = true;
          } else if (again) {
            ctx.sessionFlow.requestRefresh(joinedId);
          }
          App.perf.mark('session-join:dom-mutated');
          App.perf.measure('session-join.ws-to-dom', 'session-join:received', 'session-join:dom-mutated');
          requestAnimationFrame(function () {
            App.perf.mark('session-join:painted');
            App.perf.measure('session-join.dom-to-paint', 'session-join:dom-mutated', 'session-join:painted');
          });
          // The list refresh also primes the store's `sessions` (a start's
          // new session appears; DD4's start_session invalidation row).
          ctx.sessionFlow.refreshSessionList();
          return;
        }

        if (data.type === 'start_failed') {
          var failedEff = chatState.onFrame(data);
          if (failedEff.accept && failedEff.startFailed) ctx.sessionFlow.applyStartFailed(failedEff);
          return;
        }

        if (data.type === 'join_failed') {
          var joinFailedEff = chatState.onFrame(data);
          if (!joinFailedEff.accept) return;
          state.rebinding = false;
          var failedOwner = state.draftOwner;
          ctx.sessionFlow.clearConversation();
          ctx.sessionFlow.dropDraft(failedOwner);
          ctx.sessionFlow.setWelcomeNotice(joinFailedEff.notice);
          ctx.sessionFlow.refreshSessionList();
          return;
        }

        if (data.type === 'session_deleted') {
          var deletedEff = chatState.onFrame(data);
          ctx.sessionFlow.dropDraft('s:' + data.session_id);
          if (!deletedEff.toIdle && state.draftOwner === 's:' + data.session_id) {
            // The open chat is gone but the view stays: its composer text must not be re-saved
            // under a dead key.
            state.draftOwner = null;
            state.draftEpoch++;
          }
          if (deletedEff.toIdle) {
            state.rebinding = false;
            ctx.sessionFlow.clearConversation();
            ctx.sessionFlow.dropDraft('s:' + data.session_id);
            if (state.draftOwner === 's:' + data.session_id) {
              state.draftOwner = null;
              state.draftEpoch++;
            }
            // Don't auto-create — the session_list refresh below runs the
            // idle rules.
          }
          ctx.sessionFlow.refreshSessionList();
          return;
        }

        // OAuth: the popup close is global (it may belong to any session);
        // only the inline rendering below is gated (AC3).
        if (data.type === 'auth_resolved' || data.type === 'auth_failed') {
          ctx.signIn.settleClose(data);
        }

        // AC3, the frame gate: every other frame is session-scoped (it
        // carries no session_id), so it renders only while joined. Frames
        // from a session this socket left (a pick's `leave`, a switch) are
        // dropped while pending, starting or joining.
        if (!chatState.onFrame(data).accept) return;

        ctx.turnFrames.handle(data);
      };
    }

    return {
      connect: connect,
      ws: function () { return ws; },
      socketOpen: socketOpen,
      sendBinding: sendBinding
    };
  }

  window.App.chat.socket = { create: create };
})();
