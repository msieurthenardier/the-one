// App.chat.sessionFlow -- the session state machine's wiring: pick, open, reset, clear, the
// idle rules, hydrate, validate, heal, the first send (startSend), start_failed, the live-refresh
// flags and the list refresh (M31 F6 L02, split out of areas/chat.js, moved verbatim apart from
// the ctx./state. prefixes).
//
// pendingJoinId lives here (a cold #chats/{id} waits for the first session_list); the handle
// gives the _pendingJoinId test seam its accessor. Exposes the functions below.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var state = ctx.state;
    var chatState = ctx.chatState;
    var messagesEl = ctx.messagesEl;
    var composer = ctx.composer;
    var pane = ctx.pane;

    var pendingJoinId = null;

    // L10c: per-chat drafts. The composer holds the draft of state.draftOwner; switching the
    // active conversation saves it and restores the new one's (silent: no announcement, no focus).
    function switchDraft(newKey) {
      if (newKey === state.draftOwner) return;
      if (state.draftOwner !== null) {
        var text = composer.getValue();
        var images = ctx.attachments.staged().slice();
        if (text || images.length) state.drafts[state.draftOwner] = { text: text, images: images };
        else delete state.drafts[state.draftOwner];
      }
      var d = newKey !== null ? state.drafts[newKey] : null;
      ctx.send.setInputValue(d ? d.text : '');
      ctx.attachments.setStaged(d ? d.images : []);
      state.draftOwner = newKey;
      state.draftEpoch++;
    }
    function dropDraft(key) { if (key) delete state.drafts[key]; }
    // The first reply of a start: the pending chat's draft key becomes the session's, the
    // composer untouched (anything typed while starting carries over).
    function promoteDraft(id) {
      var old = state.draftOwner;
      if (old && old.indexOf('n:') === 0) {
        // The pending chat's draft now lives in the session; the old key must not resurface
        // in the next pending chat for that agent. Late image reads follow the promotion
        // through the instance token (draftEpoch), never the reusable n: key.
        dropDraft(old);
        state.promotedKeys[state.draftEpoch] = 's:' + id;
        var epochs = Object.keys(state.promotedKeys);
        if (epochs.length > 8) delete state.promotedKeys[epochs[0]];
        state.draftEpoch++;
      }
      state.draftOwner = 's:' + id;
    }
    function pruneDrafts(ids) {
      var live = Object.create(null);
      for (var i = 0; i < ids.length; i++) live['s:' + ids[i]] = true;
      for (var k in state.drafts) {
        if (k !== state.draftOwner && k.indexOf('n:') !== 0 && !live[k]) delete state.drafts[k];
      }
    }

    function clearLiveRefresh(id) {
      var k;
      if (id == null) {
        for (k in state.ownTurn) delete state.ownTurn[k];
        for (k in state.refreshAfterTurn) delete state.refreshAfterTurn[k];
        state.updateRejoin = null;
        state.refreshAfterJoin = null;
        return;
      }
      delete state.ownTurn[id];
      delete state.refreshAfterTurn[id];
      if (state.updateRejoin && state.updateRejoin.id === id) state.updateRejoin = null;
      if (state.refreshAfterJoin === id) state.refreshAfterJoin = null;
    }

    // An idle notice ("That conversation no longer exists") on the welcome
    // canvas; pending and joined notices go into the message log.
    function setWelcomeNotice(text) {
      pane.setNotice(text);
    }

    function showNotice(text) {
      if (chatState.state().name === 'idle') setWelcomeNotice(text);
      else ctx.transcript.addMsg('system', text);
    }

    // Every start intent (the agent picker: the Chats list's New chat, the
    // empty state's New chat, "Pick a different agent") is a route,
    // `#chats/~new/{agent}` (DD2): the router's hydrate performs the pick. A re-pick while already on a `~new` route replaces
    // it (AC12). Inert while setup is incomplete. opts.opener (the picker's
    // opener) is where a guard Stay returns focus.
    function requestPick(agent, opts) {
      if (ctx.setupBlocked() || !agent) return;
      // M31 F6 L05a (0.1, DD11 1): a completed PICKER pick lands in the message box (a guard Stay
      // resolves false, so focus stays at the opener). Only this path: chatWith, direct hash
      // entry and re-renders never move focus.
      goPick(agent, opts).then(function (ok) { if (ok) composer.focus(); });
    }

    // The pick's guarded go() with its one-shot pickIntent, so the AC9 rail
    // restore never swallows a deliberate start. Also the agent editor's
    // Chat action (M25 F4 L6, DD8), through App.chat.chatWith: from a dirty
    // editor the router's guard asks once. Resolves with the go()'s result.
    function goPick(agent, opts) {
      // M36 F3 L1: the router adapter (ctx.router.goNew) owns the route, including the
      // replace-when-already-on-a-`~new`-route check.
      state.pickIntent = agent;
      var done = function (ok) { state.pickIntent = null; return ok; };
      return ctx.router.goNew(agent, opts)
        .then(done, function () { state.pickIntent = null; return false; });
    }

    // pick(agent): pending(agent) (no session yet), a `leave` for whatever
    // this socket had bound, and the pending pane. A pick of the agent
    // already pending or starting changes nothing.
    function pickAgent(agent) {
      var eff = chatState.pick(agent);
      if (eff.noop) return false;
      if (eff.leave && ctx.socket.socketOpen()) ctx.socket.sendBinding({ action: 'leave' });
      if (eff.discardHeld) ctx.holdQueue.discardAll(eff.discardHeld);
      switchDraft('n:' + agent);
      clearLiveRefresh();
      if (eff.clearPendingJoin) pendingJoinId = null;
      state.rebinding = false;
      state.startBubbleNodes = [];
      renderPending();
      return true;
    }

    // The pending pane (M25 F4 L4b, DD6): the header reads "New chat" with
    // "with {agent}" (blank while a cold load validates the agent), the
    // new-chat state shows the agent (renderPane), the welcome is hidden, the
    // log is empty, the composer is ready, and the Chats list carries the
    // selected "New chat" row (4a).
    function renderPending() {
      var st = chatState.state();
      state.currentAgentName = st.agent;
      state.currentSessionPlatform = null;
      ctx.transcript.clearLog();
      ctx.telemetry.reset();
      ctx.holdQueue.clearPendingQueued();
      setWelcomeNotice(null);
      ctx.setSessionHealth('ok');
      ctx.applyComposerState();
      ctx.send.updateStopControl();
      ctx.showChrome();
      ctx.renderChatsList();
      ctx.renderPane();
    }

    // openConversation(id): joining(id) and one `join`. Discards a pending
    // chat or a held message of the conversation being left. The chrome
    // shows at once (AC B: the welcome never shows while joining, so no
    // empty state flashes before the session_joined), with the header read
    // from the `sessions` store.
    function openConversation(id) {
      // A move to another session drops the live-refresh flags; a same-id
      // re-join (rejoinForUpdate) keeps them.
      if (chatState.boundId() !== id) clearLiveRefresh();
      var eff = chatState.openConversation(id);
      if (eff.discardHeld) {
        ctx.holdQueue.discardAll(eff.discardHeld);
        ctx.holdQueue.clearPendingQueued();
      }
      switchDraft('s:' + id);
      state.validating = false;
      state.startBubbleNodes = [];
      setWelcomeNotice(null);
      ctx.socket.sendBinding({ action: 'join', session_id: id });
      ctx.showChrome();
      ctx.renderChatsList();
      ctx.renderPane();
    }

    function resetToIdle() {
      var eff = chatState.reset();
      clearLiveRefresh();
      if (eff.discardHeld) ctx.holdQueue.discardAll(eff.discardHeld);
      ctx.holdQueue.clearPendingQueued();
      switchDraft(null);
      state.rebinding = false;
      state.validating = false;
      state.startBubbleNodes = [];
      ctx.renderChatsList();
      ctx.renderPane();
    }

    // The pane after the state went idle: today's session_deleted reset.
    // The next session_list's idle rules pick what shows next.
    function clearConversation() {
      clearLiveRefresh();
      switchDraft(null);
      state.currentAgentName = null;
      state.currentSessionPlatform = null;
      state.joinedTitle = null;
      ctx.router.sync(null);
      ctx.transcript.clearLog();
      ctx.setSessionHealth('ok');
      ctx.send.updateStopControl();
      ctx.renderChatsList();
      ctx.renderPane();
    }

    // AC2b: one set of idle rules on every session_list, only while idle.
    function runIdleRules() {
      // The drawer profile is never idle: no auto-join, no welcome.
      if (ctx.profile === 'drawer') return;
      if (!ctx.socket.socketOpen()) return;
      var r = chatState.idleRules(state.sessions, pendingJoinId);
      if (r.clearPendingJoin) pendingJoinId = null;
      if (r.open) { openConversation(r.open); return; }
      if (r.welcome) ctx.showWelcome();
    }

    function hydrate(sub) {
      if (sub.indexOf('sessions/') === 0) { hydrateSession(sub.slice('sessions/'.length)); return; }
      if (sub === 'new' || sub.indexOf('new/') === 0) hydrateNew(sub.slice('new/'.length));
    }

    function hydrateSession(id) {
      if (!id || chatState.boundId() === id) return;
      if (ctx.socket.socketOpen()) {
        pendingJoinId = null;
        openConversation(id);
        return;
      }
      // Not open yet (a cold entry, a reconnect gap): the first session_list
      // opens it through the idle rules. Opening a conversation discards
      // whatever was open, so the state goes idle now.
      if (chatState.state().name !== 'idle') resetToIdle();
      pendingJoinId = id;
    }

    // `#chats/~new/{agent}` (AC12). The router passes the still-encoded
    // segment. Sets the state SYNCHRONOUSLY: the router serialises it right
    // after this returns.
    function hydrateNew(seg) {
      var agent = null;
      try { agent = decodeURIComponent(seg || ''); } catch (e) { agent = null; }
      var intent = state.pickIntent !== null && state.pickIntent === agent;
      if (!agent) { heal(); return; }
      var st = chatState.state();
      // AC9, the rail restore: back on the `~new` route of the pending chat
      // that became this joined session, with no pick or open since. Keep the
      // session; the router's post-hydrate sync re-canonicalises the URL.
      if (!intent && st.name === 'joined' && st.startedFrom &&
          st.startedFrom.agent === agent && st.startedFrom.cid === st.id) return;
      var kind = App.chat.agentKind(agent).kind;
      if (kind === 'gleepglorp' && !App.gleepglorp.peek().loaded) {
        // M36 F1 L04: GleepGlorp's state is not known yet (a cold deep link): pending at once
        // with the neutral pane until its settings load. Never healed away.
        if (!((st.name === 'pending' || st.name === 'starting') && st.agent === agent)) {
          state.validating = true;
          pickAgent(agent);
        }
        var settle = function () {
          var cur = chatState.state();
          if (cur.name === 'pending' && cur.agent === agent && state.validating) finishValidation();
        };
        App.gleepglorp.get().then(settle, settle);
        return;
      }
      if (kind === 'gleepglorp' || (App.store.peek('agents').loaded && kind === 'agent')) {
        var wasValidating = state.validating;
        state.validating = false;
        // The same agent's cold pending chat, still validating: validated now.
        if (!pickAgent(agent) && wasValidating && st.name === 'pending' && st.agent === agent) {
          finishValidation();
        }
        // M25 F6 L2: the cached list can lag an API-side delete (nothing
        // invalidates the store), so a pending chat renders at once from it
        // and a background forced read re-validates: a deleted agent heals.
        if (chatState.state().name === 'pending' && kind === 'agent') {
          App.store.get('agents', { force: true }).then(function (list) {
            validatePending(agent, list);
          }, function () { /* unverifiable: the server's start_session validates */ });
        }
        return;
      }
      // A cold load (or an agent the cached list lacks): pending at once
      // with a neutral pane, validated when the agents store resolves
      // (a stale cache refetches).
      if (!((st.name === 'pending' || st.name === 'starting') && st.agent === agent)) {
        state.validating = true;
        pickAgent(agent);
      }
      App.store.get('agents').then(function (list) {
        validatePending(agent, list);
      }, function () {
        validatePending(agent, null);
      });
    }

    function validatePending(agent, list) {
      var st = chatState.state();
      if (st.name !== 'pending' || st.agent !== agent) return; // moved on
      if (list && App.chat.agentKind(agent).kind === 'unknown') { heal(); return; }
      if (!state.validating) return;
      // Known (or unverifiable: the server's start_session validates too).
      finishValidation();
    }

    function finishValidation() {
      state.validating = false;
      ctx.applyComposerState();
      ctx.renderPane();
    }

    // AC12 heal: an unusable `~new` route (no agent, `default`, an unknown or
    // deleted agent, a malformed `%` escape) goes back to `#chats` (replace)
    // and the idle rules. A pending chat it made is reset; a joined or
    // starting conversation is left alone (the router's post-hydrate sync
    // re-canonicalises the URL to it).
    function heal() {
      if (chatState.state().name === 'pending') {
        var failedKey = state.draftOwner;
        resetToIdle();
        clearConversation();
        dropDraft(failedKey);
      } else {
        ctx.router.sync(null);
      }
      if (chatState.state().name === 'idle' && state.listSeen && ctx.profile !== 'drawer') runIdleRules();
    }

    // The first send of a pending chat: `start_session` with a client id
    // (AC2, DD1). The optimistic bubble, thinking and busy behave like any
    // turn; the reply's session_joined keeps the bubble when the history is
    // empty.
    function startSend(text) {
      var payload = { message: text };
      var displayText = text;
      if (ctx.attachments.staged().length) {
        payload.images = ctx.attachments.staged();
        displayText = text ? text + ' [image]' : '[image]';
      }
      var eff = chatState.startSend(App.chat.newClientId(), payload);
      if (eff.noop) return false;
      if (payload.images) ctx.attachments.clearStagedImages();
      var before = messagesEl.lastChild;
      ctx.turnWork.onUserEvent();
      ctx.transcript.addMsg('user', displayText, 'You');
      state.startBubbleNodes = [];
      for (var n = before ? before.nextSibling : messagesEl.firstChild; n; n = n.nextSibling) {
        state.startBubbleNodes.push(n);
      }
      ctx.socket.sendBinding(eff.send);
      state.ownTurn[eff.send.session_id] = true;
      ctx.send.updateStopControl();
      // pending -> starting: the new-chat state gives way to the log.
      ctx.renderPane();
      ctx.turnWork.begin();
      return true;
    }

    // start_failed (or a degraded, empty session_joined) while starting: back
    // to the pending chat with the message restored (AC2).
    function applyStartFailed(eff) {
      for (var i = 0; i < state.startBubbleNodes.length; i++) {
        var node = state.startBubbleNodes[i];
        if (node.parentNode) node.parentNode.removeChild(node);
      }
      state.startBubbleNodes = [];
      ctx.turnWork.dropEmpty();
      var held = [];
      if (eff.clientId) {
        delete state.inFlightSessions[eff.clientId];
        clearLiveRefresh(eff.clientId);
        held = ctx.holdQueue.list(eff.clientId).slice();
        ctx.holdQueue.discardAll(eff.clientId);
      }
      ctx.holdQueue.clearPendingQueued();
      var p = eff.payload || {};
      if (!composer.getValue() && p.message) ctx.send.setInputValue(p.message);
      if (p.images && p.images.length) {
        ctx.attachments.prependStaged(p.images);
      }
      if (held.length) {
        // The first held message returns to an empty box; whatever cannot is discarded, said
        // once with the count.
        var rest = held;
        if (!composer.getValue()) {
          ctx.send.setInputValue(held[0]);
          rest = held.slice(1);
        }
        if (rest.length === 1) ctx.transcript.addMsg('system', 'The queued message was discarded.');
        else if (rest.length > 1) ctx.transcript.addMsg('system', rest.length + ' queued messages were discarded.');
      }
      ctx.applyComposerState();
      ctx.send.updateStopControl();
      // starting -> pending: the new-chat state is back; the error shows in
      // the log under it (the pending chrome shrinks the log to its notices).
      ctx.renderPane();
      ctx.transcript.addMsg('system', eff.error);
    }

    function refreshSessionList() {
      // The drawer profile never lists: the sessions_changed push replaces it (M36 F3 L3).
      if (ctx.profile === 'drawer') return;
      if (ctx.socket.socketOpen()) ctx.ws().send(JSON.stringify({ action: 'list_sessions' }));
    }

    // ── The drawer profile (M36 F3 L3) ──────────────────────────────────────
    // The bound session changed: tell the profile (the drawer stores the id).
    function sessionChanged(id) {
      if (ctx.config.onSessionChange) ctx.config.onSessionChange(id);
    }

    // Back to a fresh pending chat with the fixed agent after the conversation went away
    // (join_failed, session_deleted, a pruned bound session): never idle, never the router.
    function drawerToPending() {
      pickAgent(ctx.config.agent);
      sessionChanged(null);
    }

    // New chat: a fresh pending chat (a pick leaves whatever is bound) and the stored id cleared.
    function drawerStartNew() {
      state.pendingRejoinId = null;
      var moved = pickAgent(ctx.config.agent);
      sessionChanged(null);
      return moved;
    }

    // A fixed text (the empty state's suggestion): the first send of a pending chat, else a plain
    // send. False when it was not sent (blocked, socket closed, still re-binding).
    function drawerSendText(text) {
      if (chatState.state().name === 'pending') {
        if (ctx.computeBlocked() || !ctx.socket.socketOpen() || state.rebinding) return false;
        return startSend(text);
      }
      return ctx.send.sendText(text);
    }

    // A sessions_changed list without the bound session (deleted from Chats, purged): the
    // drawer moves to a fresh pending chat and clears the stored id.
    function dropGoneBound(rows) {
      if (ctx.profile !== 'drawer') return;
      var st = chatState.state();
      if (st.name !== 'joined') return;
      for (var i = 0; i < rows.length; i++) if (rows[i] && rows[i].id === st.id) return;
      var key = state.draftOwner;
      resetToIdle();
      clearConversation();
      dropDraft(key);
      drawerToPending();
    }

    // Re-join the open chat after a session_updated (a connector turn changed
    // its stored history). Records whether the reader was at the bottom, and
    // the offset, so the reply can keep an unpinned reader where they were.
    function rejoinForUpdate(id) {
      var dist = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
      state.updateRejoin = { id: id, pinned: dist <= ctx.transcript.SCROLL_PIN_THRESHOLD, scrollTop: messagesEl.scrollTop };
      openConversation(id);
    }

    // Refresh now, or after this client's own outstanding turn ends.
    function requestRefresh(id) {
      if (state.ownTurn[id]) state.refreshAfterTurn[id] = true;
      else rejoinForUpdate(id);
    }

    return {
      switchDraft: switchDraft,
      dropDraft: dropDraft,
      promoteDraft: promoteDraft,
      pruneDrafts: pruneDrafts,
      pendingJoinId: function () { return pendingJoinId; },
      setPendingJoinId: function (v) { pendingJoinId = v; },
      clearLiveRefresh: clearLiveRefresh,
      rejoinForUpdate: rejoinForUpdate,
      requestRefresh: requestRefresh,
      refreshSessionList: refreshSessionList,
      sessionChanged: sessionChanged,
      drawerToPending: drawerToPending,
      drawerStartNew: drawerStartNew,
      drawerSendText: drawerSendText,
      dropGoneBound: dropGoneBound,
      showNotice: showNotice,
      setWelcomeNotice: setWelcomeNotice,
      requestPick: requestPick,
      goPick: goPick,
      pickAgent: pickAgent,
      renderPending: renderPending,
      openConversation: openConversation,
      resetToIdle: resetToIdle,
      clearConversation: clearConversation,
      runIdleRules: runIdleRules,
      hydrate: hydrate,
      startSend: startSend,
      applyStartFailed: applyStartFailed
    };
  }

  window.App.chat.sessionFlow = { create: create };
})();
