// App.chat.create(config) -- one complete chat instance (Mission 36 F3 L1, DD2): the body that
// areas/chat.js's init used to be, lifted into a factory so the app can call it twice. The Chats
// area is its first caller (the "Chats profile"); the GleepGlorp drawer is the second (Leg 3).
//
// config:
//   content       (required) the element the pane is built into.
//   sidebar       the element for the Chats list; the list is created only when given.
//   drawerSlot    the element for the agent drawer; created only when given (else a no-op stub).
//   pickerHost    true: register the agent picker host (the Chats profile only: it is a singleton).
//   signIn        true: create the sign-in module; false: ctx.signIn is null and callers guard it.
//   router        the adapter {sync(sub), goNew(agent, opts), go(href, opts)}; no chat module calls
//                 App.router.sync / go directly.
//   picker        optional {open(opener)}: drives the pane's New chat and Pick a different agent
//                 buttons and the list's New chat; with none those buttons do nothing.
//   testids       the composer's nine ids (testid for the input, attachTestid, fileInputTestid,
//                 modelTestid, stopTestid, sendTestid, attachmentsTestid, attachmentsStatusTestid,
//                 queuedTestid), telemetryTestid and copyStatusTestid; each defaults to its Chats
//                 `chat-*` value.
//
// The drawer profile (M36 F3 L3), `profile: 'drawer'`, adds:
//   agent         the fixed agent ('GleepGlorp'): the instance is never idle, it is a pending
//                 chat with that agent when it has no conversation.
//   testidPrefix  ('gg-') prepended to every testid built at construct time and by the lazily
//                 built queue and attachment nodes; per-message testids stay fixed.
//   onSessionChange(id)  the bound session changed: an accepted session_joined (id), or New
//                 chat / a failed or deleted conversation (null).
//   emptyState    a Node shown while the chat is pending, in place of the new-chat state.
//   onBlockedChange(blocked)  the composer's blocked state, for the empty state's suggestion.
//   pageContext() (M36 F3 L4) returns the page descriptor to send with a message, or null; the
//                 Chats profile has none, so its payloads have no `page` key.
//   fillHooks {fillNow(view), isApplying(id)} (M36 F3 L6) the receipts' Fill now (drawer only).
//   onFillRequested(view, sessionId) (M36 F3 L6, drawer only) a fill_requested for the bound chat
//                 while this instance owns the turn (ctx.send.ownsTurn): the drawer applies it.
// and the socket's onopen only re-joins its own conversation, never lists sessions or idles.
//
// The handle: root, connect, ws, refreshAgentsAndSetup, serialize, hydrate, joinSession,
// sessionState, telemetry, transcript, turnWork, turnFrames, agentDrawer, currentSessionId(),
// pendingJoinId(), setPendingJoinId(v), startNew(), sendText(text), focusComposer(),
// isBlocked(), destroy().
//
// destroy(): sets the destroyed flag, releases the store / time / GleepGlorp subscriptions, closes
// the socket with its reconnect timer, clears the hold queue's timers and the transcript (widget
// cards), and removes the DOM this instance built. The Chats instance never calls it.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // The keys are App.ui.composer's own option names (the testid guard reads literal values for a
  // `testid` / `<name>Testid` key), so the composer takes them as they are.
  var DEFAULT_TESTIDS = {
    testid: 'chat-input',
    attachTestid: 'chat-attach-btn',
    fileInputTestid: 'chat-image-input',
    modelTestid: 'chat-model',
    stopTestid: 'chat-stop-btn',
    sendTestid: 'chat-send-btn',
    attachmentsTestid: 'chat-attachments',
    attachmentsStatusTestid: 'chat-attachments-status',
    queuedTestid: 'pending-queued-region',
    telemetryTestid: 'chat-telemetry',
    copyStatusTestid: 'chat-copy-status'
  };
  var NON_COMPOSER_TESTIDS = ['telemetryTestid', 'copyStatusTestid'];

  // The stub drawer of a profile with no drawer slot: every method the modules call, a no-op.
  function stubDrawer() {
    var noop = function () {};
    return {
      toggle: document.createElement('button'),
      render: noop,
      setActive: noop,
      setSessionMetadata: noop,
      refreshNotes: noop,
      refreshRoutines: noop,
      destroy: noop
    };
  }

  function create(config) {
    var content = config.content;
    var sidebar = config.sidebar || null;
    var router = config.router;
    var picker = config.picker || null;
    var testids = {};
    var k;
    for (k in DEFAULT_TESTIDS) testids[k] = (config.testids && config.testids[k]) || DEFAULT_TESTIDS[k];

    // M36 F3 L3: the drawer profile. Every behaviour below that differs is keyed on isDrawer
    // (read once into ctx.profile); the Chats profile passes none of these options.
    var isDrawer = config.profile === 'drawer';
    var testidPrefix = config.testidPrefix || '';

    // Prefix the testids a module builds at construct time (or lazily) with the profile's
    // prefix: the root's own and every descendant's. A no-op for the Chats profile.
    function prefixTestids(root) {
      if (!testidPrefix || !root) return;
      var nodes = [root].concat(Array.prototype.slice.call(root.querySelectorAll('[data-testid]')));
      for (var i = 0; i < nodes.length; i++) {
        var v = nodes[i].getAttribute('data-testid');
        if (v) nodes[i].setAttribute('data-testid', testidPrefix + v);
      }
    }

    var destroyed = false;
    var unsubs = [];

    // Shared mutable state (M31 F6 L02): every variable that more than one chat module reads or
    // writes lives here and is read and written as state.x by all of them (a variable only one
    // module uses stays in that module's closure; the socket stays in socket.js, behind ctx.ws()).
    var state = {
      // Per-session in-flight tracker: a session is "busy" when its agent
      // is mid-turn. Was previously a single `busy` flag per WebSocket, but
      // that caused the input to stay disabled in a NEW conversation when
      // the user switched away from a still-running one (post-F4 surfacing).
      inFlightSessions: Object.create(null),
      // Sortie 05 leg 3 (DD6): live refresh of an open chat. ownTurn marks a turn
      // THIS client sent (distinct from inFlightSessions, which an is_processing
      // join also sets); refreshAfterTurn defers a session_updated re-join until
      // that turn ends; updateRejoin records a re-join sent for session_updated
      // (its pin state and scroll offset); refreshAfterJoin notes a session_updated
      // that landed while the same id was being joined. All keyed by session id.
      ownTurn: Object.create(null),
      // L10c: unsent drafts, keyed 's:{id}' (a session) or 'n:{agent}' (a pending new chat);
      // draftOwner is the key whose draft the composer currently holds (null: none).
      drafts: Object.create(null),
      draftOwner: null,
      // draftEpoch is the pending-instance token (bumped on every draft switch, promotion and
      // draft-owner clear); promotedKeys maps a pending instance's epoch token to the 's:{id}'
      // it became (late image reads follow it; pruned to the most recent few).
      draftEpoch: 0,
      promotedKeys: Object.create(null),
      refreshAfterTurn: Object.create(null),
      updateRejoin: null,
      refreshAfterJoin: null,
      // The drawer profile: a conversation the drawer asked to re-join before its socket was
      // open; onopen consumes it (null otherwise).
      pendingRejoinId: null,
      // Per-session held-message queue (up to 10): key is session id, value is the list of held texts.
      // Mirrors inFlightSessions shape so session-switch and onclose handle both together.
      pendingQueuedMessages: Object.create(null),
      // B9: how many held messages the operator's own Stop click discarded, keyed by session
      // id; the `cancelled` frame reports it ("Queued message discarded.") and consumes it.
      discardedOnStop: Object.create(null),
      sessions: [],
      // A session_list has arrived on some socket (the idle rules can run).
      listSeen: false,
      // Set in onopen; cleared after that socket's first session_list, so the
      // later lists (the refresh after `done`) never re-run the reconnect rules.
      firstListPending: false,
      // Set in onopen while joined or joining (the fresh socket is unbound until
      // the re-join lands); cleared when that state resolves. While set, Send
      // keeps its text and Stop does nothing: a message on an unbound socket
      // would auto-create a default-agent session.
      rebinding: false,
      // The agent an entry point asked to pick (requestPick): its hydrate is a
      // real pick even where the AC9 rail-restore rule would keep a session.
      pickIntent: null,
      // A cold `#chats/~new/{agent}` waits for the agents store to validate the
      // agent; the composer stays disabled meanwhile (AC12).
      validating: false,
      // The optimistic first-message bubble's nodes, removed on start_failed.
      startBubbleNodes: [],
      // M36 F3 L4: the sender's bubble that is waiting for its `page_line` frame (one slot: the
      // client sends one turn at a time). Cleared on done, cancelled, a turn-ending system
      // frame, start_failed, a log wipe and a page_line for another session.
      pendingPageBubble: null,
      currentAgentName: null,
      // M27 F3 L2: live tool_call_id -> tool name (tool_result events carry no
      // name), so a note tool's result can refresh the agent panel's notes.
      liveToolNames: {},
      // M23 F02 L03 (behavior-test fix): the joined session's connector
      // platform, if any (mirrors ChatSession.platform / session_joined's new
      // `platform` field). null for a web-native session. Used to gate the
      // peer-visible-tool-result promotion: the operator-only /
      // peer-visible distinction only exists for connector-attached sessions;
      // a plain chat session's tool results have no visibility concept at all
      // and must keep collapsing into the turn's work group.
      currentSessionPlatform: null,
      // The joined session's title from its session_joined (the header's
      // fallback until the `sessions` store has its row).
      joinedTitle: null,
      setupIncomplete: false,
      // The deleted-agent / missing-provider health banner is active (the persistent library
      // banner below carries its text); computeBlocked reads it.
      bannerActive: false,
      setupState: { hasProviders: false, hasAgents: false }
    };

    // M25 F4 L3b (DD1): the session state machine (areas/chat/session-state.js).
    // Every inbound frame passes its gate; busy, the hold queue and Stop key
    // on its activeId() (the client id while starting, the session id while
    // joined). There is no "null means idle": the state's name says it.
    var chatState = App.chat.createSessionState();

    // The picker hook: with none given, the buttons do nothing.
    function openPicker(btn) {
      if (picker && picker.open) picker.open(btn);
    }

    // M25 F4 L4a (DD5): the Chats list column, an App.ui.listPane built with
    // DOM APIs (areas/chat/chats-list.js): the New chat button (it opens the
    // agent picker) above the cross-agent history in recency groups, with a
    // delete action per row and the pending chat's row. Created only with a sidebar.
    var chatsList = null;
    if (sidebar) {
      chatsList = App.chat.chatsList.create({
        onNew: function (btn) { openPicker(btn); },
        onDelete: function (id, li, btn, title) {
          // Two-step confirm (arm, then confirm) via App.ui.confirm on the row's <li>; the
          // WebSocket delete is fire-and-forget and the server's session_deleted + list refresh
          // update the list (the listPane keeps an armed <li> across rebuilds, DD5).
          // A1 (WCAG 4.1.2/4.1.3): the action's accessible name follows the armed state,
          // derived from the row's title (never read back from the DOM, since a second click
          // runs this again): onArmChange fires on arm, lapse, commit and revert, idempotently.
          App.ui.confirm(li, function (itemEl, revert) {
            if (!ctx.socket.socketOpen()) {
              // DD11 6: nothing was sent, so say so and disarm the row.
              revert();
              App.ui.flash("Not connected, so the chat wasn't deleted. Try again in a moment.", { error: true });
              return;
            }
            ctx.ws().send(JSON.stringify({ action: 'delete_session', session_id: id }));
          }, {
            onArmChange: function (armed) {
              if (btn) btn.setAttribute('aria-label', (armed ? 'Confirm delete: ' : 'Delete chat: ') + title);
            }
          });
        }
      });
      sidebar.appendChild(chatsList.el);
    }

    // M25 F4 L4b (DD3, DD6): the detail pane, built with DOM APIs: the welcome (the empty and
    // guidance states under one "Hello." h1) and the chrome (the chat header's h1 and "with
    // {agent}", the new-chat state, the message log, then the composer),
    // areas/chat/chat-pane.js. The composer is App.ui.composer (reference spec 5.5, the
    // telemetry row above it), built below.
    var pane = App.chat.chatPane.create({
      drawer: isDrawer,
      testidPrefix: testidPrefix,
      emptyState: config.emptyState || null,
      onNewChat: function (btn) { openPicker(btn); },
      onPickDifferent: function (btn) { openPicker(btn); },
      go: function (href, opts) { return router.go(href, opts); }
    });
    // M31 F6 L05a (DD4, DD7): the composer is App.ui.composer; the modules reach it through
    // ctx.composer. Every control's behaviour is a callback into a module (called at event time,
    // so the later-created modules are reachable); the modules never touch its elements.
    var composerOpts = {
      placeholder: 'Message…',
      onSend: function (raw) { ctx.send.send(raw); },
      onStop: function () { stopTurn(); },
      onAttach: function () { ctx.attachments.attach(); },
      onFiles: function (files) { ctx.attachments.addFiles(files); }
    };
    for (k in testids) if (NON_COMPOSER_TESTIDS.indexOf(k) < 0) composerOpts[k] = testids[k];
    var composer = App.ui.composer(composerOpts);
    // The deleted-agent / missing-provider notice: one persistent warning banner above the
    // composer, driven by set(text) (empty collapses it), so a change is announced.
    var healthBanner = App.ui.banner({ tone: 'warning', live: 'status', className: 'chat-health-banner' });
    // M25 F4 L6 (DD7): the agent drawer fills the static shell slot (#chat-drawer, after <main>;
    // areas/chat/agent-drawer.js) when a slot is given; otherwise a no-op stub. Its toggle goes at
    // the END of the chat header. renderPane feeds it the header's agent.
    var agentDrawer = config.drawerSlot
      ? App.chat.agentDrawer.create({ slot: config.drawerSlot })
      : stubDrawer();
    pane.header.appendChild(agentDrawer.toggle);
    var chromeEl = pane.chrome;
    var welcomeEl = pane.welcome;
    var messagesEl = pane.messages;

    // The mascot, decorative, above the greeting. The drawer profile has no welcome, so none.
    if (!isDrawer) {
      var mascotEl = document.createElement('img');
      mascotEl.className = 'chat-welcome-mascot';
      mascotEl.src = '/static/brand/gleepglorp_icon.png';
      mascotEl.alt = '';
      mascotEl.setAttribute('aria-hidden', 'true');
      mascotEl.setAttribute('loading', 'eager');
      mascotEl.setAttribute('data-testid', 'chat-welcome-mascot');
      pane.welcomeInner.insertBefore(mascotEl, pane.welcomeInner.firstChild);
    }

    // The chrome: header, new-chat state, the message log, then the composer
    // (M25 F4 L5): its wrapper holds the telemetry row (the readout, shown
    // only while joined: renderPane), the staged-image row and its status,
    // the queued-message region (F09-04: above the box and OUTSIDE the
    // scrolling .messages list, so a held message cannot scroll away;
    // showPendingQueued/clearPendingQueued toggle its `hidden`), then the box.
    // The telemetry readout (App.ui.telemetry, M31 F6 L05c): the instance keeps the thresholds
    // (read from App.config on every update, since the config may load after this runs) and
    // the perf marks; session_joined and the usage frame feed it.
    var telemetryOpts = {
      thresholds: function () {
        var cfg = window.App.config || {};
        return { warn: cfg.context_warn_pct || 70, crit: cfg.context_crit_pct || 90 };
      }
    };
    telemetryOpts.testid = testids.telemetryTestid;
    var telemetry = App.ui.telemetry(telemetryOpts);
    composer.slots.telemetry.appendChild(telemetry.el);
    // The one shared role=status node the transcript's "Copy reply" confirmations announce in,
    // outside the role=log message list (placed in the content panel, after the chrome).
    var copyLiveEl = document.createElement('div');
    copyLiveEl.className = 'visually-hidden';
    copyLiveEl.setAttribute('role', 'status');
    copyLiveEl.setAttribute('data-testid', testids.copyStatusTestid);
    chromeEl.appendChild(healthBanner.el);
    chromeEl.appendChild(composer.el);
    // The drawer profile builds its DOM detached and attaches it on the drawer's first open
    // (handle.attach()): the closed, hidden drawer then adds no second `.messages`, `.chat-chrome`
    // or live node to the page, and the socket and the renders work on the detached nodes.
    function attach() {
      if (chromeEl.parentNode === content) return;
      content.appendChild(chromeEl);
      content.appendChild(copyLiveEl);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    if (!isDrawer) {
      content.appendChild(welcomeEl);
      content.appendChild(chromeEl);
      content.appendChild(copyLiveEl);
    }

    // The one object every chat module is created from (M31 F6 L02): the state, the session state
    // machine, the DOM refs, the render functions (assigned below from instance-render.js), and
    // (assigned below as each module is created) the module handles. A module reaches a
    // later-created one only at call time. ctx.router is the profile's router adapter.
    var ctx = {
      state: state,
      chatState: chatState,
      messagesEl: messagesEl,
      composer: composer,
      telemetry: telemetry,
      copyLiveEl: copyLiveEl,
      pane: pane,
      chromeEl: chromeEl,
      welcomeEl: welcomeEl,
      content: content,
      agentDrawer: agentDrawer,
      chatsList: chatsList,
      healthBanner: healthBanner,
      router: router,
      config: config,
      profile: isDrawer ? 'drawer' : 'chats',
      // M36 F3 L6: the form-fill receipts' hooks (the drawer supplies them); a no-op and "not
      // applying" by default, so a receipt's Fill now does nothing in an instance that has none.
      fillHooks: {
        fillNow: (config.fillHooks && config.fillHooks.fillNow) || function () {},
        isApplying: (config.fillHooks && config.fillHooks.isApplying) || function () { return false; }
      },
      testidPrefix: testidPrefix,
      prefixTestids: prefixTestids,
      signIn: null,
      destroyed: function () { return destroyed; },
      ws: function () { return ctx.socket.ws(); }
    };
    var render = App.chat.instanceRender.create(ctx);
    for (k in render) ctx[k] = render[k];

    // The chat modules, leaves first (each is App.chat.<name>.create(ctx); see their headers).
    ctx.holdQueue = App.chat.holdQueue.create(ctx);
    ctx.attachments = App.chat.attachments.create(ctx);
    ctx.transcript = App.chat.transcript.create(ctx);
    ctx.turnWork = App.chat.turnWork.create(ctx);
    ctx.send = App.chat.send.create(ctx);
    ctx.proposalCards = App.chat.proposalCards.create(ctx);
    ctx.fillReceipts = App.chat.fillReceipts.create(ctx);
    if (config.signIn) ctx.signIn = App.chat.signIn.create(ctx);
    ctx.turnFrames = App.chat.turnFrames.create(ctx);
    ctx.sessionFlow = App.chat.sessionFlow.create(ctx);
    ctx.socket = App.chat.socket.create(ctx);

    // The list renders from the store subscription only (never also from session_list). The
    // Chats instance is never destroyed (deactivate keeps the WebSocket and the DOM), so its
    // subscriptions live as long as the page; destroy() releases them through these handles.
    unsubs.push(App.store.subscribe('sessions', function () {
      ctx.renderChatsList();
      ctx.renderPane();
    }));
    // Clock times and day groups follow the operator's time zone (M28 F2 L1): re-label the
    // list and every message timestamp in place when it changes. No owner element: the
    // listener must outlive a detached root and is released by destroy().
    unsubs.push(App.time.onChange(function () {
      if (destroyed) return;
      ctx.renderChatsList();
      App.ui.message.relabel(messagesEl, function (ts) {
        var d = new Date(ts);
        return isNaN(d.getTime()) ? null : App.time.formatClock(d);
      });
    }));
    ctx.renderChatsList();
    // The new-chat state reads the agent's model, description and provider
    // type from these two stores: re-render when either loads.
    unsubs.push(App.store.subscribe('agents', function () { if (!destroyed) ctx.renderPane(); }));
    unsubs.push(App.store.subscribe('providers', function () { if (!destroyed) ctx.renderPane(); }));
    ctx.renderPane();
    // The drawer profile is never idle: with no conversation it is a pending chat with its fixed
    // agent (no router involvement, nothing sent until the operator sends).
    if (isDrawer) ctx.sessionFlow.pickAgent(config.agent);

    // F7 L04: stop/cancel button — send the cancel action, then optimistically
    // reset the thinking indicator and discard any pending queued message. The
    // `cancelled` event from the backend will perform the authoritative full reset.
    function stopTurn() {
      if (!ctx.send.isCurrentBusy()) return; // no-op: already done, or raced to completion
      // AC8: a closed or not-yet-re-bound socket has nothing to cancel (and a
      // send on a closed socket throws). While starting, the cancel is
      // ordered after start_session on the socket, so it binds to the new
      // session.
      if (!ctx.socket.socketOpen() || state.rebinding) return;
      ctx.ws().send(JSON.stringify({ action: 'cancel' }));
      // Optimistic: stop the work line's dots at once so the UI feels responsive (the state
      // changes only on the server's frames).
      ctx.turnWork.stopClicked();
      // Discard pending queued message — "stop" means stop everything.
      var stopActive = chatState.activeId();
      if (stopActive) {
        // B9: remember that this Stop discarded a held message, for the `cancelled` frame.
        // L10a: the count, since the queue is gone by the time `cancelled` arrives.
        var stopHeld = ctx.holdQueue.discardAll(stopActive);
        if (stopHeld) state.discardedOnStop[stopActive] = stopHeld;
        ctx.holdQueue.clearPendingQueued();
      }
      // Do NOT prematurely clear inFlightSessions or re-enable Send here;
      // the authoritative `cancelled` event handles those (avoids a race where
      // a rapid double-click re-enables the button before the event arrives).
    }

    // M25 F4 L4a (AC12): the agent picker's host, registered LAST so App.chat.openPicker calls
    // queued before the instance existed run now. Only the Chats profile registers it (the host
    // is a module singleton). The picker hands a pick to requestPick (the route and pickIntent
    // stay in session-flow.js); with setup incomplete an open is an inert no-op.
    if (config.pickerHost) {
      App.chat.registerPickerHost({
        setupIncomplete: ctx.setupBlocked,
        onPick: function (agent, opts) { ctx.sessionFlow.requestPick(agent, opts); },
        chatWith: function (agent, opts) { return ctx.sessionFlow.goPick(agent, opts); }
      });
    }
    // M36 F1 L04: GleepGlorp's settings (loaded now, current through every Save and push):
    // the setup gate, the pending chat's state and composer follow them.
    App.gleepglorp.get().catch(function () { /* the next refresh retries */ });
    unsubs.push(App.gleepglorp.subscribe(function () {
      if (destroyed) return;
      if (chatsList) chatsList.setNewDisabled(ctx.setupBlocked());
      ctx.applyComposerState();
      ctx.renderPane();
    }));

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      for (var i = 0; i < unsubs.length; i++) {
        try { unsubs[i](); } catch (e) { /* already released */ }
      }
      unsubs = [];
      ctx.socket.close();
      ctx.holdQueue.destroy();
      ctx.transcript.clearLog();
      var nodes = [welcomeEl, chromeEl, copyLiveEl, chatsList && chatsList.el];
      for (var n = 0; n < nodes.length; n++) {
        if (nodes[n] && nodes[n].parentNode) nodes[n].parentNode.removeChild(nodes[n]);
      }
    }

    return {
      root: content,
      connect: ctx.socket.connect,
      ws: function () { return ctx.socket.ws(); },
      refreshAgentsAndSetup: ctx.refreshAgentsAndSetup,
      serialize: function () { return chatState.serialize(); },
      hydrate: ctx.sessionFlow.hydrate,
      // Opens a conversation (one `join`) on an open socket. The drawer profile remembers an id
      // asked for before its socket opened, and its onopen joins it.
      joinSession: function (id) {
        if (ctx.socket.socketOpen()) ctx.sessionFlow.openConversation(id);
        else if (isDrawer) state.pendingRejoinId = id;
      },
      // The drawer profile: a fresh pending chat with the fixed agent (New chat).
      attach: attach,
      messagesEl: messagesEl,
      startNew: function () { return ctx.sessionFlow.drawerStartNew(); },
      // Send a fixed text (the empty state's suggestion): starts the chat when it is pending.
      sendText: function (text) { return ctx.sessionFlow.drawerSendText(text); },
      focusComposer: function () { composer.focus(); },
      isBlocked: function () { return ctx.computeBlocked(); },
      sessionState: function () { return chatState.state(); },
      telemetry: telemetry,
      transcript: ctx.transcript,
      turnWork: ctx.turnWork,
      turnFrames: ctx.turnFrames,
      fillReceipts: ctx.fillReceipts,
      // The hooks object itself (a test or Part B may replace a member).
      fillHooks: ctx.fillHooks,
      agentDrawer: agentDrawer,
      currentSessionId: function () { return chatState.boundId(); },
      pendingJoinId: function () { return ctx.sessionFlow.pendingJoinId(); },
      setPendingJoinId: function (v) { ctx.sessionFlow.setPendingJoinId(v); },
      destroy: destroy
    };
  }

  window.App.chat.create = create;
})();
