App.registerArea({
  id: 'chat',
  label: 'Chat',
  icon: App.icons.chat,
  order: 10,
  sidebarLabel: 'Chat sessions',

  // M25 F4 L3b (DD1, AC5): the session state machine serialises itself:
  // `new/{agent}` while pending or starting, `sessions/{id}` while joining or
  // joined, nothing while idle.
  serializeState: function () {
    return this._serialize ? this._serialize() : null;
  },
  // Bare `#chats` (no sub) keeps whatever is open, a joined session or a
  // pending chat (AC9b); the router's post-hydrate sync then re-canonicalises
  // the URL from serializeState.
  hydrateState: function (sub) {
    if (!sub) return;
    if (this._hydrate) this._hydrate(sub);
  },

  init: function (sidebar, content) {
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
      refreshAfterTurn: Object.create(null),
      updateRejoin: null,
      refreshAfterJoin: null,
      // Per-session one-slot queue: key is session id, value is the pending message text.
      // Mirrors inFlightSessions shape so session-switch and onclose handle both together.
      pendingQueuedMessages: Object.create(null),
      // B9: a held message the operator's own Stop click discarded, keyed by session id; the
      // `cancelled` frame reports it ("Queued message discarded.") and consumes the flag.
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
      // and must keep collapsing into the "Tool activity" accordion.
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

    var messagesEl;

    // M25 F4 L4a (DD5): the Chats list column, an App.ui.listPane built with
    // DOM APIs (areas/chat/chats-list.js): the New chat button (it opens the
    // agent picker) above the cross-agent history in recency groups, with a
    // delete action per row and the pending chat's row. The agent dropdown,
    // its "Select Agent" label and the old history list are retired.
    var chatsList = App.chat.chatsList.create({
      onNew: function (btn) {
        App.chat.openPicker({ opener: btn }).catch(function () { /* a guard Stay */ });
      },
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

    // M25 F4 L4b (DD3, DD6): the detail pane, built with DOM APIs (the
    // content sink is gone): the welcome (the empty and guidance states under
    // one "Hello." h1) and the chrome (the chat header's h1 and "with
    // {agent}", the new-chat state, the message log, then the composer),
    // areas/chat/chat-pane.js. The composer is App.ui.composer (reference
    // spec 5.5, the telemetry row above it), built below.
    var pane = App.chat.chatPane.create({
      onNewChat: function (btn) {
        App.chat.openPicker({ opener: btn }).catch(function () { /* a guard Stay */ });
      },
      onPickDifferent: function (btn) {
        App.chat.openPicker({ opener: btn }).catch(function () { /* a guard Stay */ });
      }
    });
    // M31 F6 L05a (DD4, DD7): the composer is App.ui.composer; the modules reach it through
    // ctx.composer. Every control's behaviour is a callback into a module (called at event time,
    // so the later-created modules are reachable); the modules never touch its elements.
    var composer = App.ui.composer({
      placeholder: 'Message…',
      testid: 'chat-input',
      attachTestid: 'chat-attach-btn',
      fileInputTestid: 'chat-image-input',
      modelTestid: 'chat-model',
      stopTestid: 'chat-stop-btn',
      sendTestid: 'chat-send-btn',
      attachmentsTestid: 'chat-attachments',
      attachmentsStatusTestid: 'chat-attachments-status',
      queuedTestid: 'pending-queued-region',
      onSend: function (raw) { ctx.send.send(raw); },
      onStop: function () { stopTurn(); },
      onAttach: function () { ctx.attachments.attach(); },
      onFiles: function (files) { ctx.attachments.addFiles(files); }
    });
    // The deleted-agent / missing-provider notice: one persistent warning banner above the
    // composer, driven by set(text) (empty collapses it), so a change is announced.
    var healthBanner = App.ui.banner({ tone: 'warning', live: 'status', className: 'chat-health-banner' });
    // M25 F4 L6 (DD7): the agent drawer fills the static shell slot
    // (#chat-drawer, after <main>; areas/chat/agent-drawer.js). Its toggle
    // goes at the END of the chat header. renderPane feeds it the header's
    // agent; activate/deactivate show and hide it with the area.
    var agentDrawer = App.chat.agentDrawer.create({ slot: document.getElementById('chat-drawer') });
    pane.header.appendChild(agentDrawer.toggle);
    var chromeEl = pane.chrome;
    var welcomeEl = pane.welcome;
    messagesEl = pane.messages;

    // The mascot, decorative, above the greeting.
    var mascotEl = document.createElement('img');
    mascotEl.className = 'chat-welcome-mascot';
    mascotEl.src = '/static/brand/gleepglorp_icon.png';
    mascotEl.alt = '';
    mascotEl.setAttribute('aria-hidden', 'true');
    mascotEl.setAttribute('loading', 'eager');
    mascotEl.setAttribute('data-testid', 'chat-welcome-mascot');
    pane.welcomeInner.insertBefore(mascotEl, pane.welcomeInner.firstChild);

    // The chrome: header, new-chat state, the message log, then the composer
    // (M25 F4 L5): its wrapper holds the telemetry row (the readout, shown
    // only while joined: renderPane), the staged-image row and its status,
    // the queued-message region (F09-04: above the box and OUTSIDE the
    // scrolling .messages list, so a held message cannot scroll away;
    // showPendingQueued/clearPendingQueued toggle its `hidden`), then the box.
    // The telemetry readout (App.ui.telemetry, M31 F6 L05c): the area keeps the thresholds
    // (read from App.config on every update, since the config may load after this runs) and
    // the perf marks; session_joined and the usage frame feed it.
    var telemetry = App.ui.telemetry({
      thresholds: function () {
        var cfg = window.App.config || {};
        return { warn: cfg.context_warn_pct || 70, crit: cfg.context_crit_pct || 90 };
      },
      testid: 'chat-telemetry'
    });
    composer.slots.telemetry.appendChild(telemetry.el);
    // The one shared role=status node the transcript's "Copy reply" confirmations announce in,
    // outside the role=log message list (placed in the area panel, after the chrome).
    var copyLiveEl = document.createElement('div');
    copyLiveEl.className = 'visually-hidden';
    copyLiveEl.setAttribute('role', 'status');
    copyLiveEl.setAttribute('data-testid', 'chat-copy-status');
    chromeEl.appendChild(healthBanner.el);
    chromeEl.appendChild(composer.el);
    content.appendChild(welcomeEl);
    content.appendChild(chromeEl);
    content.appendChild(copyLiveEl);

    // The one object every chat module is created from (M31 F6 L02): the state, the session state
    // machine, the DOM refs, the functions this file keeps, and (assigned below as each module is
    // created) the module handles. A module reaches a later-created one only at call time.
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
      renderPane: renderPane,
      renderChatsList: renderChatsList,
      applyComposerState: applyComposerState,
      setSessionHealth: setSessionHealth,
      refreshAgentsAndSetup: refreshAgentsAndSetup,
      showChrome: showChrome,
      showWelcome: showWelcome,
      toSessionSummary: toSessionSummary,
      ws: function () { return ctx.socket.ws(); }
    };

    function sessionRow(id) {
      var rows = App.store.peek('sessions').value;
      if (!Array.isArray(rows) || !id) return null;
      for (var i = 0; i < rows.length; i++) if (rows[i] && rows[i].id === id) return rows[i];
      return null;
    }

    // M25 F4 L4b (AC1, AC2): the header and the new-chat state follow the
    // session state.
    //   pending / starting  "New chat", "with {agent}" (blank while a cold
    //                       `~new` route validates its agent); the new-chat
    //                       state only while pending (the chrome carries
    //                       .chat-chrome--new, so the log shrinks to its
    //                       notices).
    //   joining / joined    the session's title READ FROM THE `sessions`
    //                       STORE by id (so it follows the auto-title), else
    //                       the session_joined payload's, else "Untitled
    //                       chat"; the agent likewise (store row, then the
    //                       payload).
    //   idle                no header (the welcome, or nothing yet).
    // M25 F4 L5 (DD6): the composer follows the same agent as the header:
    // its placeholder "Message {agent}…" ("Message…" with none, or while the
    // header's agent line is blank) and the agent's model id from the
    // `agents` store ('' when unknown). The telemetry row shows only while
    // joined (reference spec 5.3, 5.4: none in the new-chat state).
    // Runs from every transition and from the `sessions`, `agents` and
    // `providers` subscriptions; it patches nodes, never rebuilds them.
    function renderPane() {
      var st = chatState.state();
      var name = st.name;
      var pending = name === 'pending';
      var composerAgent = null;
      // M25 F4 L6 (DD7): the drawer follows the header: its agent, or a
      // neutral loading state while the header's agent line is blank; no
      // chat view (null) while idle.
      var drawerView = null;
      if (pending || name === 'starting') {
        pane.renderHeader({ title: 'New chat', agent: st.agent, blank: state.validating });
        if (!state.validating) composerAgent = st.agent;
        drawerView = state.validating ? { loading: true } : { agent: st.agent };
      } else if (name === 'joined' || name === 'joining') {
        var row = sessionRow(st.id);
        var title = row ? row.title : (name === 'joined' ? state.joinedTitle : null);
        var agent = row ? row.agent_name : (name === 'joined' ? state.currentAgentName : null);
        if (!row && name === 'joining') {
          pane.renderHeader({ title: '', agent: null, blank: true });
          drawerView = { loading: true };
        } else {
          pane.renderHeader({ title: title || 'Untitled chat', agent: agent });
          composerAgent = agent || null;
          drawerView = { agent: agent || null, sessionId: st.id || null };
        }
      } else {
        pane.renderHeader(null);
      }
      agentDrawer.render(drawerView);
      var agents = App.store.peek('agents').value;
      var providers = App.store.peek('providers').value;
      if (pending) {
        pane.renderNewState(state.validating ? { blank: true } : App.chat.chatPane.agentInfo(
          st.agent, agents, providers
        ));
      } else {
        pane.renderNewState(null);
      }
      chromeEl.classList.toggle('chat-chrome--new', pending);
      composer.setPlaceholder(composerAgent ? 'Message ' + String(composerAgent) + '…' : 'Message…');
      composer.setModel(composerAgent ? App.chat.chatPane.agentInfo(composerAgent, agents, providers).model : '');
      composer.slots.telemetry.hidden = name !== 'joined';
    }

    // M25 F4 L4a (AC6): the ONE render of the Chats list. The rows are the
    // store's `sessions` (primed from every WebSocket session_list, DD4); the
    // pending chat's row and the selection come from the session state: the
    // pending row while pending or starting, else the joined or joining
    // session's row. It runs from the `sessions` subscription below and from
    // every transition that changes the pending row or the selection (pick,
    // open, joined, the starting-to-joined swap, idle, delete). Safe off
    // Chats: a REST-primed list with no socket renders into the hidden
    // sidebar panel, with the state idle.
    // A server list row -> the REST summary shape the store's `sessions`
    // collection holds (shared by the session_list reply and sessions_changed).
    function toSessionSummary(s) {
      return {
        id: s.id,
        agent_name: s.agent_name,
        title: s.title,
        created_at: s.created_at,
        updated_at: s.updated_at,
        platform: s.platform || null
      };
    }

    function renderChatsList() {
      var st = chatState.state();
      var pendingActive = st.name === 'pending' || st.name === 'starting';
      var peeked = App.store.peek('sessions');
      var rows = Array.isArray(peeked.value) ? peeked.value : [];
      // While starting, the pending row stands for the new chat: a pushed
      // listing may already hold its real row (same id), so omit it.
      if (st.name === 'starting') {
        rows = rows.filter(function (r) { return r.id !== st.clientId; });
      }
      chatsList.render(rows, {
        pending: pendingActive ? { agent: st.agent } : null,
        selectedId: pendingActive ? App.chat.chatsList.PENDING_ID : chatState.boundId()
      });
    }

    // The list renders from the store subscription only (never also from
    // session_list). The chat area is never destroyed (deactivate keeps the
    // WebSocket and the DOM), so this subscription lives as long as the page
    // and is never unsubscribed.
    App.store.subscribe('sessions', function () { renderChatsList(); renderPane(); });
    // Clock times and day groups follow the operator's time zone (M28 F2 L1): re-label the
    // list and every message timestamp in place when it changes. Never released.
    App.time.onChange(function () {
      renderChatsList();
      App.ui.message.relabel(messagesEl, function (ts) {
        var d = new Date(ts);
        return isNaN(d.getTime()) ? null : App.time.formatClock(d);
      });
    });
    renderChatsList();
    // The new-chat state reads the agent's model, description and provider
    // type from these two stores: re-render when either loads. Never
    // released, like the `sessions` subscription.
    App.store.subscribe('agents', function () { renderPane(); });
    App.store.subscribe('providers', function () { renderPane(); });
    renderPane();

    // M25 F4 L4b (DD3, AC3-AC5): the welcome is the empty state (setup
    // complete: "Start a conversation with one of your agents." and New
    // chat) or the setup guidance (no New chat; the list's is disabled too).
    // The agent list it used to hold is retired (the picker replaces it).
    function renderWelcome() {
      pane.renderWelcome(state.setupState);
    }

    // Only while idle with no chat to auto-join: the idle rules' `welcome`.
    function showWelcome() {
      chromeEl.hidden = true;
      welcomeEl.hidden = false;
      renderWelcome();
    }

    function showChrome() {
      welcomeEl.hidden = true;
      chromeEl.hidden = false;
    }

    // The ONE blocked computation (M31 F6 L05a): a health banner is up, or a pending chat whose
    // setup is incomplete or whose cold load is still validating its agent.
    function computeBlocked() {
      return state.bannerActive ||
        (chatState.state().name === 'pending' && (state.setupIncomplete || state.validating));
    }

    // The composer's state, from the session state: blocked (the input and Attach off, the box
    // dimmed) and busy (Stop shown, Send off). Send is disabled while blocked OR busy, so
    // clearing the banner mid-turn leaves it disabled. Every former sessionBannerEl guard calls
    // this.
    function applyComposerState() {
      composer.setBlocked(computeBlocked());
      composer.setBusy(ctx.send.isCurrentBusy());
    }

    // One read per activation: agents + providers through App.store, deriving
    // the setup state.  Errors are swallowed; on a failure the prior setup
    // state is kept (never flips to "no setup").
    function refreshAgentsAndSetup() {
      return Promise.all([
        App.store.get('providers', { force: true }),
        App.store.get('agents', { force: true })
      ])
        .then(function (results) {
          state.setupState.hasProviders = results[0].length > 0;
          state.setupState.hasAgents = results[1].length > 0;
          state.setupIncomplete = !state.setupState.hasProviders || !state.setupState.hasAgents;
          // M25 F4 L4a (AC2): New chat is natively disabled while setup is
          // incomplete (no provider or no agent); the pane's guidance says
          // why.
          chatsList.setNewDisabled(state.setupIncomplete);
          var stName = chatState.state().name;
          // A shown welcome follows the setup state (the empty state <->
          // the guidance). M25 F4 L4b (DD3): the welcome is SHOWN only by
          // the idle rules (idle with no chat to auto-join); this no longer
          // shows it while idle, so the guidance never flashes before an
          // auto-join (the onopen list request follows this read). A pending
          // chat is never covered by the welcome (AC4); its composer follows
          // the setup state instead.
          if (stName === 'idle' && !welcomeEl.hidden) renderWelcome();
          if (stName === 'pending') applyComposerState();
        })
        .catch(function () { /* best-effort */ });
    }

    function setSessionHealth(status) {
      var msg = null;
      if (status === 'agent_deleted') msg = 'This agent has been deleted. Chat history is preserved but new messages cannot be sent.';
      else if (status === 'provider_missing') msg = "This agent's provider is missing. Add a model provider in Library to continue this conversation.";
      state.bannerActive = !!msg;
      healthBanner.set(msg || '');
      applyComposerState();
    }

    // The chat modules, leaves first (each is App.chat.<name>.create(ctx); see their headers).
    ctx.holdQueue = App.chat.holdQueue.create(ctx);
    ctx.attachments = App.chat.attachments.create(ctx);
    ctx.transcript = App.chat.transcript.create(ctx);
    ctx.send = App.chat.send.create(ctx);
    ctx.signIn = App.chat.signIn.create(ctx);
    ctx.turnFrames = App.chat.turnFrames.create(ctx);
    ctx.sessionFlow = App.chat.sessionFlow.create(ctx);
    ctx.socket = App.chat.socket.create(ctx);

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
      // Optimistic: clear thinking immediately so the UI feels responsive.
      ctx.transcript.hideThinking();
      // Discard pending queued message — "stop" means stop everything.
      var stopActive = chatState.activeId();
      if (stopActive) {
        // B9: remember that this Stop discarded a held message, for the `cancelled` frame.
        if (state.pendingQueuedMessages[stopActive]) state.discardedOnStop[stopActive] = true;
        delete state.pendingQueuedMessages[stopActive];
        ctx.holdQueue.clearPendingQueued();
      }
      // Do NOT prematurely clear inFlightSessions or re-enable Send here;
      // the authoritative `cancelled` event handles those (avoids a race where
      // a rapid double-click re-enables the button before the event arrives).
    }

    var self = this;
    self._connect = ctx.socket.connect;
    self._ws = function () { return ctx.socket.ws(); };
    self._refreshAgentsAndSetup = refreshAgentsAndSetup;
    self._serialize = function () { return chatState.serialize(); };
    self._hydrate = ctx.sessionFlow.hydrate;
    // Test seams. `_joinSession` opens a conversation (one `join`) on an open
    // socket; `_sessionState` is the state machine's state().
    self._joinSession = function (id) {
      if (ctx.socket.socketOpen()) ctx.sessionFlow.openConversation(id);
    };
    self._sessionState = function () { return chatState.state(); };
    // The telemetry handle (App.ui.telemetry), for the threshold and restore tests.
    self._telemetry = function () { return telemetry; };
    // AC4: "the joined or joining id", derived from the state (null while
    // idle, pending or starting).
    Object.defineProperty(self, '_currentSessionId', {
      get: function () { return chatState.boundId(); },
      configurable: true
    });
    Object.defineProperty(self, '_pendingJoinId', {
      get: function () { return ctx.sessionFlow.pendingJoinId(); },
      set: function (v) { ctx.sessionFlow.setPendingJoinId(v); },
      configurable: true
    });

    // M25 F4 L4a (AC12): the agent picker's host, registered LAST in init so
    // App.chat.openPicker calls queued before the area existed run now. The
    // picker hands a pick to requestPick (the route and pickIntent stay
    // in session-flow.js); with setup incomplete an open is an inert no-op.
    App.chat.registerPickerHost({
      setupIncomplete: function () { return state.setupIncomplete; },
      onPick: function (agent, opts) { ctx.sessionFlow.requestPick(agent, opts); },
      chatWith: function (agent, opts) { return ctx.sessionFlow.goPick(agent, opts); }
    });
    self._agentDrawer = agentDrawer;
  },

  activate: function () {
    // M25 F4 L6 (DD7): the drawer shows only on Chats.
    if (this._agentDrawer) this._agentDrawer.setActive(true);
    if (!this._ws || !this._ws() || this._ws().readyState > 1) {
      this._connect();
    } else if (this._ws() && this._ws().readyState === WebSocket.OPEN) {
      this._refreshAgentsAndSetup();
    }
  },

  deactivate: function () {
    // Keep WS alive. The drawer is hidden off Chats, so <main> keeps its
    // full width on Agents, Library and Settings (M25 F4 L6, DD7).
    if (this._agentDrawer) this._agentDrawer.setActive(false);
  }
});