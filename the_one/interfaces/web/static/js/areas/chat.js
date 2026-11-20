// The Chats area descriptor (Mission 36 F3 L1): the "Chats profile" of the chat instance factory.
// All chat logic lives in App.chat.create (areas/chat/instance.js); this file builds the Chats
// config (the list in the sidebar, the pane in the content panel, the agent drawer slot, the
// picker host, sign-in, the router adapter and today's testids), calls the factory once and
// exposes the handle's test seams on the descriptor.
App.registerArea({
  id: 'chat',
  label: 'Chat',
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
    // The content panel carries both `area-chat` (from app.js) and `chat-instance`, the class
    // chat.css scopes its rules to.
    content.classList.add('chat-instance');

    // The Chats router adapter: exactly the calls the chat modules used to make directly.
    var router = {
      sync: function (sub) { App.router.sync('chat', sub); },
      go: function (href, opts) { return App.router.go(href, opts); },
      // The pick's guarded go: replace (not push) when already on a `~new` route.
      goNew: function (agent, opts) {
        var cur = App.router.current();
        var onNew = !!(cur && cur.destination === 'chats' && cur.route.indexOf('chats/~new/') === 0);
        var goOpts = onNew ? { replace: true } : {};
        if (opts && opts.opener) goOpts.opener = opts.opener;
        return App.router.go(App.router.href({ destination: 'chats', create: true, agent: agent }), goOpts);
      }
    };

    var inst = App.chat.create({
      sidebar: sidebar,
      content: content,
      drawerSlot: document.getElementById('chat-drawer'),
      pickerHost: true,
      signIn: true,
      router: router,
      picker: {
        open: function (opener) {
          return App.chat.openPicker({ opener: opener }).catch(function () { /* a guard Stay */ });
        }
      }
      // testids: the factory's defaults are today's `chat-*` ids.
    });

    var self = this;
    self._inst = inst;
    self._connect = inst.connect;
    self._ws = inst.ws;
    self._refreshAgentsAndSetup = inst.refreshAgentsAndSetup;
    self._serialize = inst.serialize;
    self._hydrate = inst.hydrate;
    // Test seams. `_joinSession` opens a conversation (one `join`) on an open
    // socket; `_sessionState` is the state machine's state().
    self._joinSession = inst.joinSession;
    self._sessionState = inst.sessionState;
    // The telemetry handle (App.ui.telemetry), for the threshold and restore tests.
    self._telemetry = function () { return inst.telemetry; };
    // The transcript, for the widget teardown race test (renderHistory and clearLog in one task).
    self._transcript = function () { return inst.transcript; };
    // The turn work module (the open group, replay), for the flow tests.
    self._turnWork = function () { return inst.turnWork; };
    // The turn-frame handler, for tests that feed one frame (the deleted-agent step-limit notice).
    self._turnFrames = function () { return inst.turnFrames; };
    // AC4: "the joined or joining id", derived from the state (null while
    // idle, pending or starting).
    Object.defineProperty(self, '_currentSessionId', {
      get: function () { return inst.currentSessionId(); },
      configurable: true
    });
    Object.defineProperty(self, '_pendingJoinId', {
      get: function () { return inst.pendingJoinId(); },
      set: function (v) { inst.setPendingJoinId(v); },
      configurable: true
    });
    self._agentDrawer = inst.agentDrawer;
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
