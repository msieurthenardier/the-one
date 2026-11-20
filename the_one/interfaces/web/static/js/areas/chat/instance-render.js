// App.chat.instanceRender -- the pane and list renders and the composer state of one chat
// instance (Mission 36 F3 L1, lifted verbatim from areas/chat.js apart from the ctx. prefixes and
// the guards for an absent Chats list). Created from the instance's ctx by instance.js, which
// then puts the returned functions on ctx under the same names the modules already call.
//
// Reads from ctx: state, chatState, pane, composer, chatsList (null with no list), agentDrawer,
// healthBanner, chromeEl, welcomeEl, messagesEl, router; and, at call time, send, proposalCards,
// transcript (created later).
//
// Returns: renderPane, renderChatsList, renderWelcome, showWelcome, showChrome, computeBlocked,
// applyComposerState, setupBlocked, refreshAgentsAndSetup, setSessionHealth, toSessionSummary.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var state = ctx.state;
    var chatState = ctx.chatState;
    var pane = ctx.pane;
    var composer = ctx.composer;
    var chatsList = ctx.chatsList;
    var agentDrawer = ctx.agentDrawer;
    var healthBanner = ctx.healthBanner;
    var chromeEl = ctx.chromeEl;
    var welcomeEl = ctx.welcomeEl;

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
      var composerInfo = composerAgent ? App.chat.chatPane.agentInfo(composerAgent, agents, providers) : null;
      var placeholder = composerAgent ? 'Message ' + String(composerAgent) + '…' : 'Message…';
      if (pending && !state.validating && composerInfo && composerInfo.gleepglorp
          && composerInfo.state && composerInfo.state !== 'ready') {
        // M36 F1 HAT: a blocked pending GleepGlorp chat names its next step.
        placeholder = composerInfo.state === 'off' ? 'GleepGlorp is turned off…'
          : (!composerInfo.hasProviders ? 'Add a model provider first…' : 'Choose a model first…');
      }
      composer.setPlaceholder(placeholder);
      composer.setModel(composerInfo ? composerInfo.model : '');
      composer.slots.telemetry.hidden = name !== 'joined';
    }

    // A server list row -> the REST summary shape the store's `sessions`
    // collection holds (shared by the session_list reply and sessions_changed).
    function toSessionSummary(s) {
      return {
        id: s.id,
        agent_name: s.agent_name,
        title: s.title,
        created_at: s.created_at,
        updated_at: s.updated_at,
        platform: s.platform || null,
        // M31 F6 L10b: the working indicator and the new-reply marker (see chat/chat-activity.js).
        busy: !!s.busy,
        turn_seq: s.turn_seq || null
      };
    }

    var chatActivity = App.chat.activity.create();

    // M25 F4 L4a (AC6): the ONE render of the Chats list. The rows are the
    // store's `sessions` (primed from every WebSocket session_list, DD4); the
    // pending chat's row and the selection come from the session state: the
    // pending row while pending or starting, else the joined or joining
    // session's row. It runs from the `sessions` subscription and from
    // every transition that changes the pending row or the selection (pick,
    // open, joined, the starting-to-joined swap, idle, delete). Safe off
    // Chats: a REST-primed list with no socket renders into the hidden
    // sidebar panel, with the state idle. A no-op with no list (a profile
    // without a sidebar).
    function renderChatsList() {
      if (!chatsList) return;
      var st = chatState.state();
      var pendingActive = st.name === 'pending' || st.name === 'starting';
      var peeked = App.store.peek('sessions');
      var rows = Array.isArray(peeked.value) ? peeked.value : [];
      // While starting, the pending row stands for the new chat: a pushed
      // listing may already hold its real row (same id), so omit it.
      if (st.name === 'starting') {
        rows = rows.filter(function (r) { return r.id !== st.clientId; });
      }
      // M31 F6 L10b: row activity. observe() sees every stored row (before the starting
      // filter) and treats the joined chat as open, so it never owes a new-reply dot.
      var openId = st.name === 'joined' ? chatState.boundId() : null;
      var allRows = Array.isArray(peeked.value) ? peeked.value : [];
      // Only a loaded collection baselines (an unloaded one reads as an empty list).
      if (peeked.loaded && peeked.ok !== false) chatActivity.observe(allRows, openId);
      var activity = {};
      for (var r = 0; r < rows.length; r++) {
        var as = chatActivity.stateFor(rows[r], openId);
        if (as) activity[rows[r].id] = as;
      }
      chatsList.render(rows, {
        activity: activity,
        pending: pendingActive ? { agent: st.agent } : null,
        selectedId: pendingActive ? App.chat.chatsList.PENDING_ID : chatState.boundId()
      });
    }

    // M25 F4 L4b (DD3, AC3-AC5): the welcome is the empty state (setup
    // complete: "Start a conversation with one of your agents." and New
    // chat) or the setup guidance (no New chat; the list's is disabled too).
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

    function gleepglorpReady() {
      var s = App.chat.gleepglorpSettings();
      return !!(s && s.state === 'ready');
    }

    // The ONE blocked computation (M31 F6 L05a): a health banner is up, or a pending chat whose
    // setup is incomplete or whose cold load is still validating its agent.
    function computeBlocked() {
      var st = chatState.state();
      if (state.bannerActive) return true;
      if (st.name !== 'pending') return false;
      // M36 F1 L04: a pending GleepGlorp chat is blocked by its own state (not ready), never by
      // the app's setup (GleepGlorp exists to help with it).
      if (st.agent === App.chat.GLEEPGLORP) return !state.validating && !gleepglorpReady();
      return state.setupIncomplete || state.validating;
    }

    // The setup gate (M36 F1 L04): the Chats list's New chat, the picker and a pick are inert
    // while setup is incomplete, unless GleepGlorp is on (it offers help with the setup).
    function setupBlocked() {
      return state.setupIncomplete && !App.chat.gleepglorpEnabled();
    }

    // The composer's state, from the session state: blocked (the input and Attach off, the box
    // dimmed) and busy (Stop shown, Send off). Send is disabled while blocked OR busy, so
    // clearing the banner mid-turn leaves it disabled. Every former sessionBannerEl guard calls
    // this.
    function applyComposerState() {
      var blocked = computeBlocked();
      composer.setBlocked(blocked);
      // The drawer profile's empty-state suggestion follows the same blocked state.
      if (ctx.config.onBlockedChange) ctx.config.onBlockedChange(blocked);
      composer.setBusy(ctx.send.isCurrentBusy());
      if (ctx.proposalCards) ctx.proposalCards.refreshBusy();
      ctx.transcript.setContinueEnabled(!computeBlocked());
    }

    // One read per activation: agents + providers through App.store, deriving
    // the setup state.  Errors are swallowed; on a failure the prior setup
    // state is kept (never flips to "no setup").
    function refreshAgentsAndSetup() {
      return Promise.all([
        App.store.get('providers', { force: true }),
        App.store.get('agents', { force: true }),
        // GleepGlorp's settings feed the setup gate; a failed read keeps the last value.
        App.gleepglorp.get({ force: true }).catch(function () { return null; })
      ])
        .then(function (results) {
          if (ctx.destroyed()) return;
          state.setupState.hasProviders = results[0].length > 0;
          state.setupState.hasAgents = results[1].length > 0;
          state.setupIncomplete = !state.setupState.hasProviders || !state.setupState.hasAgents;
          // M25 F4 L4a (AC2): New chat is natively disabled while setup is
          // incomplete (no provider or no agent); the pane's guidance says
          // why.
          if (chatsList) chatsList.setNewDisabled(setupBlocked());
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

    // `reason` is the server's plain sentence for a `build_failed` chat (set as text by the banner).
    function setSessionHealth(status, reason) {
      var msg = null;
      if (status === 'build_failed') msg = reason || App.chat.DEGRADED_REASONS.build_failed;
      else
      if (status === 'agent_deleted') msg = 'This agent has been deleted. Chat history is preserved but new messages cannot be sent.';
      else if (status === 'provider_missing') msg = "This agent's provider is missing. Add a model provider in Library to continue this conversation.";
      // M36 F1 L04: a GleepGlorp status gets its own sentence and an "Open GleepGlorp settings"
      // button (never the agent texts above, never the deleted-agent notice).
      var ggState = App.chat.GLEEPGLORP_STATUSES[status];
      if (ggState) msg = App.chat.gleepglorpBanner(ggState);
      state.bannerActive = !!msg;
      healthBanner.set(msg || '');
      healthBanner.setChildren([]);
      if (ggState) {
        var action = App.ui.button({
          variant: 'secondary',
          size: 'sm',
          label: 'Open GleepGlorp settings',
          testid: 'chat-health-banner-action',
          onClick: function () {
            ctx.router.go(App.chat.agentKind(App.chat.GLEEPGLORP).settingsHref);
          }
        });
        ctx.prefixTestids(action);
        healthBanner.setChildren([action]);
      }
      applyComposerState();
    }

    return {
      renderPane: renderPane,
      renderChatsList: renderChatsList,
      renderWelcome: renderWelcome,
      showWelcome: showWelcome,
      showChrome: showChrome,
      computeBlocked: computeBlocked,
      applyComposerState: applyComposerState,
      setupBlocked: setupBlocked,
      refreshAgentsAndSetup: refreshAgentsAndSetup,
      setSessionHealth: setSessionHealth,
      toSessionSummary: toSessionSummary
    };
  }

  window.App.chat.instanceRender = { create: create };
})();
