// App.gleepglorpDrawer -- the GleepGlorp assistant's corner button and right drawer, the shell
// only (M36 F3 L2, flight DD1). Leg 3 mounts the drawer's chat into bodySlot().
//
//   App.gleepglorpDrawer.mount()          build and wire the shell (app.js, once, after the rail)
//   .open(opener?) / .close() / .isOpen() the user's open state (held in memory per window)
//   .bodySlot()                           the empty body node Leg 3 fills
//   .headerActions()                      the empty header node Leg 3 puts New chat / Open in
//                                         Chats in (before the labelled Close)
//   .onOpenChange(fn)                     fn(open) after the drawer opens or closes; returns the
//                                         unsubscribe (M36 F3 L3)
//   .setInitialFocus(fn)                  fn() -> true when it focused the chat's composer; the
//                                         open focus rule is setup link, else this, else the title
//   .setContext(parts)                    the "Looking at" line, from route parts (an array of
//                                         strings, or a string)
//   .state()                              the last known GleepGlorp state, or null
//
// The button and the drawer exist on Agents, Library and Settings only: never on Chats (there
// the chat is the page) and never while GleepGlorp is off. The open state is remembered across
// Chats. The button stays hidden until a state is known. All the visible state comes from one
// apply() over four inputs: the GleepGlorp state, the destination, the user's open state and
// the width.
(function () {
  'use strict';

  window.App = window.App || {};

  var PUSH_QUERY = '(min-width: 1280px)';
  var LIBRARY_COLLECTIONS = ['providers', 'knowledge-bases', 'mcp-sources', 'connectors', 'secrets'];
  var TAB_LABELS = {
    general: 'General',
    'rules-and-notes': 'Rules and notes',
    knowledge: 'Knowledge',
    tools: 'Tools',
    routines: 'Routines',
    'self-configuration': 'Self-configuration'
  };

  var mounted = null;

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  function humanize(id) {
    var s = String(id).replace(/-/g, ' ');
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  // The create editors' names, one copy of the server's `page.py::CREATE_NAMES` (pinned equal by
  // `tests/test_gleepglorp_drawer_create_names.py`): the line reads what the model's page line
  // does, where the router's announcer says only "New". Keyed by the Library section, or
  // `agents`.
  var CREATE_NAMES = {
    agents: 'New Agent',
    providers: 'New model provider',
    knowledge: 'New knowledge base',
    mcp: 'New MCP server',
    connectors: 'New Connector',
    secrets: 'New secret'
  };

  // The "Looking at" parts of a route-change info: the announcer's parts, plus an agent's tab.
  function contextParts(info) {
    if (!info) return [];
    var parts = [];
    for (var i = 0; i < info.parts.length; i++) {
      if (info.parts[i]) parts.push(String(info.parts[i]));
    }
    var cp = App.router.parse(info.route);
    if (cp && cp.create && parts.length) {
      var createName = CREATE_NAMES[cp.destination === 'agents' ? 'agents' : cp.section];
      if (createName) parts[parts.length - 1] = createName;
    }
    if (info.destination === 'agents') {
      var p = App.router.parse(info.route);
      if (p && p.id && p.tab) parts.push(TAB_LABELS[p.tab] || humanize(p.tab));
    }
    return parts;
  }

  function mount() {
    if (mounted) return mounted;
    var slot = document.getElementById('gleepglorp-drawer');
    var row = document.querySelector('.app-shell-row');
    if (!slot || !row) return null;

    var state = null; // off | needs_model | provider_missing | ready; null until known
    var onChats = false;
    var userOpen = false;
    var contextText = '';

    // ── The header: robot tile, title, (Leg 3: actions), labelled Close ─────
    var tile = el('span', { className: 'gg-drawer-tile' }, [App.ui.util.icon('bot')]);
    tile.setAttribute('aria-hidden', 'true');
    var title = el('h2', { className: 'gg-drawer-title', text: 'GleepGlorp', tabindex: '-1' });
    title.setAttribute('data-testid', 'gg-drawer-title');
    var actions = el('div', { className: 'gg-drawer-actions' });
    actions.setAttribute('data-testid', 'gg-drawer-actions');
    var closeBtn = App.ui.button({
      variant: 'ghost',
      size: 'sm',
      label: 'Close',
      icon: 'x',
      testid: 'gg-drawer-close',
      onClick: function () { api.close(); }
    });
    closeBtn.setAttribute('aria-keyshortcuts', 'Escape');
    var head = el('div', { className: 'gg-drawer-head' }, [tile, title, actions, closeBtn]);

    // ── The body: the "Looking at" line, the setup block, the chat slot ─────
    var ctxLabel = el('span', { className: 'gg-drawer-context-label', text: 'Looking at' });
    var ctxValue = el('span', { className: 'gg-drawer-context-value' });
    var context = el('p', { className: 'gg-drawer-context' }, [ctxLabel, ' ', ctxValue]);
    context.setAttribute('data-testid', 'gg-drawer-context');

    var setupText = el('p', { className: 'gg-drawer-setup-text' });
    var setupLink = el('a', { className: 'gg-drawer-setup-link', text: 'Choose a model' });
    setupLink.setAttribute('data-testid', 'gg-drawer-setup-action');
    var setup = el('div', { className: 'gg-drawer-setup', hidden: true }, [setupText, setupLink]);
    setup.setAttribute('data-testid', 'gg-drawer-setup');

    var slotBody = el('div', { className: 'gg-drawer-slot' });
    slotBody.setAttribute('data-testid', 'gg-drawer-body');
    var body = el('div', { className: 'gg-drawer-content' }, [context, setup, slotBody]);

    var button = App.ui.cornerButton({
      ariaLabel: 'Ask GleepGlorp',
      icon: 'bot',
      controls: 'gleepglorp-drawer',
      id: 'gleepglorp-corner-button',
      testid: 'gg-corner-button',
      hidden: true,
      onClick: function () { api.open(); }
    });

    var drawer = App.ui.drawer({
      el: slot,
      label: 'GleepGlorp',
      heading: head,
      body: body,
      testid: 'gg-drawer',
      // Show the button first, so the drawer's own focus return finds it visible.
      beforeClose: function () { if (canShow()) button.setHidden(false); },
      onOpenChange: function (open) {
        userOpen = open;
        apply();
        notifyOpen(open);
        if (open) focusInitial();
      }
    });

    // M36 F3 L3: open listeners (the chat's lazy re-join) and the initial-focus rule: the setup
    // link while the setup block shows, else the chat's composer (the registered target), else
    // the title.
    var openListeners = [];
    var focusTarget = null;
    // The last effective open state the listeners were told (the drawer is shown). One call per
    // change, whether the drawer's own open/close or apply() (Chats, GleepGlorp off) caused it.
    var notifiedOpen = false;
    function notifyOpen(open) {
      if (open === notifiedOpen) return;
      notifiedOpen = open;
      openListeners.slice().forEach(function (fn) {
        try { fn(open); } catch (e) { console.error(e); }
      });
    }
    function focusInitial() {
      if (!setup.hidden) { setupLink.focus(); return; }
      if (focusTarget && focusTarget() === true) return;
      title.focus();
    }

    function canShow() {
      return !onChats && state !== null && state !== 'off';
    }

    // Move focus out of the drawer before it is hidden by a state change, so it is never lost
    // to <body>.
    function rescueFocus() {
      var active = document.activeElement;
      if (active && slot.contains(active)) {
        var main = document.getElementById('main-content');
        if (main) main.focus();
      }
    }

    function renderSetup() {
      var needs = state === 'needs_model' || state === 'provider_missing';
      setup.hidden = !needs;
      if (!needs) return;
      setupText.textContent = App.chat.gleepglorpBanner(state);
      setupLink.setAttribute('href', App.chat.agentKind(App.chat.GLEEPGLORP).settingsHref);
    }

    function apply() {
      var show = canShow();
      var drawerShown = show && userOpen;
      var buttonShown = show && !userOpen;
      if (!drawerShown && !slot.hidden) rescueFocus();
      slot.hidden = !drawerShown;
      button.setHidden(!buttonShown);
      button.setExpanded(drawerShown);
      row.classList.toggle('gg-corner-on', buttonShown);
      renderSetup();
      notifyOpen(drawerShown);
    }

    function setState(next) {
      state = next && next.state ? next.state : state;
      // Turned off while open: the drawer closes and stays closed.
      if (state === 'off') userOpen = false;
      apply();
    }

    function setContext(parts) {
      contextText = Array.isArray(parts) ? parts.join(' › ') : String(parts || '');
      ctxValue.textContent = contextText;
      context.hidden = !contextText;
    }

    function renderContext() {
      var info = App.router.describeCurrent();
      if (info && info.destination !== 'chats') setContext(contextParts(info));
    }

    var api = {
      open: function (opener) {
        if (!canShow()) return;
        if (drawer.isOpen()) { focusInitial(); return; }
        drawer.open(opener && opener.nodeType ? opener : button.el);
        // Already shown (restored after Chats): the drawer reports no change.
        userOpen = true;
        apply();
      },
      onOpenChange: function (fn) {
        openListeners.push(fn);
        return function () {
          var i = openListeners.indexOf(fn);
          if (i !== -1) openListeners.splice(i, 1);
        };
      },
      setInitialFocus: function (fn) { focusTarget = fn; },
      close: function () {
        if (drawer.isOpen()) drawer.close();
        else { userOpen = false; apply(); }
      },
      isOpen: function () { return userOpen && canShow(); },
      bodySlot: function () { return slotBody; },
      headerActions: function () { return actions; },
      setContext: setContext,
      state: function () { return state; },
      button: function () { return button; }
    };

    // ── Width: push at 1280px and wider, overlay below ──────────────────────
    var mq = typeof window.matchMedia === 'function' ? window.matchMedia(PUSH_QUERY) : null;
    function applyMode() { drawer.setMode(mq && !mq.matches ? 'overlay' : 'push'); }
    applyMode();
    if (mq) mq.addEventListener('change', applyMode);

    row.appendChild(button.el);

    // ── Inputs ──────────────────────────────────────────────────────────────
    function loadState() {
      if (state !== null || !App.gleepglorp) return;
      App.gleepglorp.get().then(setState, function () { /* retried on the next commit */ });
    }
    if (App.gleepglorp) {
      App.gleepglorp.subscribe(setState);
      var known = App.gleepglorp.peek().value;
      if (known) setState(known);
      else loadState();
    }
    App.router.onCommit(function (destId) {
      onChats = destId === 'chats';
      apply();
      loadState();
    });
    App.router.onRouteChange(function (info) {
      if (info && info.destination !== 'chats') setContext(contextParts(info));
    });
    // An item's name comes from a synchronous store peek, so a cold deep link reads the type
    // noun until its collection loads: redraw the line from the router when one does.
    LIBRARY_COLLECTIONS.forEach(function (name) {
      try { App.store.subscribe(name, renderContext); } catch (e) { /* unknown collection */ }
    });
    renderContext();

    mounted = api;
    window.App.gleepglorpDrawer.open = api.open;
    window.App.gleepglorpDrawer.close = api.close;
    window.App.gleepglorpDrawer.isOpen = api.isOpen;
    window.App.gleepglorpDrawer.onOpenChange = api.onOpenChange;
    window.App.gleepglorpDrawer.setInitialFocus = api.setInitialFocus;
    window.App.gleepglorpDrawer.bodySlot = api.bodySlot;
    window.App.gleepglorpDrawer.headerActions = api.headerActions;
    window.App.gleepglorpDrawer.setContext = api.setContext;
    window.App.gleepglorpDrawer.state = api.state;
    window.App.gleepglorpDrawer.button = api.button;
    return api;
  }

  var stub = function () { return null; };
  window.App.gleepglorpDrawer = {
    mount: mount,
    open: stub,
    close: stub,
    isOpen: function () { return false; },
    onOpenChange: function () { return function () {}; },
    setInitialFocus: stub,
    bodySlot: stub,
    headerActions: stub,
    setContext: stub,
    state: stub,
    button: stub
  };
})();
