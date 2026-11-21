// App.chat.chatPane -- the Chats detail pane (M25 F4 leg 4b; flight DD3, DD6;
// reference spec 5.2, 5.4). Built with DOM APIs only (the chat area's former
// content sink is gone). It folds in the former areas/chat/welcome.js.
//
// The pane is two siblings in the chat content panel:
//
//   the welcome (div.chat-welcome, testid chat-welcome)
//     The empty and setup-guidance states, shown only while the session state
//     is idle with no chat to auto-join (the chat area decides when). One h1,
//     the "Hello." greeting (h1.chat-welcome-greeting), then an idle notice
//     (p.chat-welcome-notice, role=status, hidden when empty), the prompt
//     (p.chat-welcome-prompt), the guidance (p.chat-welcome-guidance) and the
//     actions row. The mascot (chat-welcome-mascot) is prepended by the caller.
//       setup complete    the prompt "Start a conversation with one of your
//                         agents." and New chat (btn-filled-primary, testid
//                         chat-empty-new-btn), which calls onNewChat(btn);
//       setup incomplete  no prompt and no New chat: the guidance links
//                         (.chat-welcome-link, router hrefs) to Library ›
//                         Model providers (the create form) and/or Agents.
//
//   the chrome (div.chat-chrome)
//     The header (header.chat-header, testid chat-header): an h1 (the chat's
//     title, or "New chat") and "with {agent}" (span.chat-agent-line, testid
//     chat-agent-line; "Unknown agent" for a null agent); hidden while idle.
//     chat.js appends the agent drawer's toggle at its end (M25 F4 L6,
//     areas/chat/agent-drawer.js).
//     Then the new-chat state (div.chat-new-state, testid chat-new-state),
//     shown only while a chat is pending: a badge badge--{type} whose TEXT is
//     the model (A20), the agent name as an h2, the description and "Pick a
//     different agent" (btn-ghost btn-sm, testid chat-pick-different-btn),
//     which calls onPickDifferent(btn). Then the message log (div.messages).
//     The caller appends the composer pieces, the telemetry overlay and the
//     queued-message region after the log.
//
// Every render PATCHES nodes built once (text, classes, `hidden`), so a store
// notification never rebuilds a focused control.
//
// API:
//   App.chat.chatPane.create({onNewChat(btn), onPickDifferent(btn), go(href)}) -> {
//     welcome, welcomeInner, welcomeNotice, chrome, header, newState, messages,
//     newChatButton, pickDifferentButton,
//     renderWelcome(setup)      setup {hasProviders, hasAgents}
//     setNotice(text)           the idle notice on the welcome ('' hides it)
//     renderHeader(view)        null hides it; {title, agent, blank}: blank
//                               leaves the agent line empty (a cold `~new`
//                               route still validating its agent)
//     renderNewState(view)      null hides it; {blank} shows it empty; else
//                               agentInfo()'s {name, model, description, kind}
//   }
//   App.chat.chatPane.agentInfo(name, agents, providers) -> {name, model,
//     description, kind, known}: the agent's row from the `agents` list, the
//     badge kind from the providers resolution (App.chat.agentPicker.
//     providerType); a type outside App.ui.badge.KINDS, no provider or an
//     unknown agent is 'unknown'.
//   App.chat.chatPane.agentLine(agent) -> 'with {agent}' ('Unknown agent' for
//     a null or empty agent)
//   agentInfo(GleepGlorp) -> {kind: 'builtin', gleepglorp: true, state, hasProviders, ...}
//     (M36 L04): the new-chat state shows "Built in", the model and, when its state is not
//     ready, the setup block (chat-new-gleepglorp-setup / -action).
//   App.chat.chatPane.guidance(setup) -> the guidance <p> (setup incomplete)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var EMPTY_PROMPT = 'Start a conversation with one of your agents.';

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  // `href` is a router href (App.router.href), e.g. '#library/providers/~new'.
  function welcomeLink(text, href) {
    return el('a', { className: 'chat-welcome-link', href: href, text: text });
  }

  // The setup-incomplete guidance line: no provider (and maybe no agent), or
  // no agent only. Same copy and hrefs as the former welcome.js.
  function guidance(setup) {
    var p = el('p', { className: 'chat-welcome-guidance' });
    var library = App.router.href({ destination: 'library', section: 'providers', create: true });
    var agents = App.router.href({ destination: 'agents' });
    if (!setup.hasProviders && !setup.hasAgents) {
      p.appendChild(document.createTextNode('Add a model provider in '));
      p.appendChild(welcomeLink('Library', library));
      p.appendChild(document.createTextNode(', then create an agent in '));
      p.appendChild(welcomeLink('Agents', agents));
      p.appendChild(document.createTextNode(' to start chatting.'));
    } else if (!setup.hasProviders) {
      p.appendChild(document.createTextNode('Add a model provider in '));
      p.appendChild(welcomeLink('Library', library));
      p.appendChild(document.createTextNode(' to start chatting.'));
    } else {
      p.appendChild(document.createTextNode('Create an agent in '));
      p.appendChild(welcomeLink('Agents', agents));
      p.appendChild(document.createTextNode(' to start chatting.'));
    }
    return p;
  }

  // A row with no agent (impossible after schema v53) reads "Unknown agent".
  function agentLine(agent) {
    return 'with ' + (agent ? String(agent) : 'Unknown agent');
  }

  var GLEEPGLORP_DESCRIPTION = 'Help setting up the app';

  // GleepGlorp's info: the "Built in" badge, its model, and the state its setup block shows
  // (null while its settings have not loaded yet).
  function gleepglorpInfo(providers) {
    var s = App.chat.gleepglorpSettings();
    return {
      name: App.chat.GLEEPGLORP,
      model: s && s.model ? String(s.model) : '',
      description: GLEEPGLORP_DESCRIPTION,
      kind: 'builtin',
      known: true,
      gleepglorp: true,
      state: s ? s.state : null,
      hasProviders: Array.isArray(providers) ? providers.length > 0 : true
    };
  }

  function agentInfo(name, agents, providers) {
    if (App.chat.agentKind(name).kind === 'gleepglorp') return gleepglorpInfo(providers);
    var row = null;
    var list = Array.isArray(agents) ? agents : [];
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].name === name) { row = list[i]; break; }
    }
    var type = row ? App.chat.agentPicker.providerType(row, providers) : null;
    var kind = type && App.ui.badge.KINDS.indexOf(type) !== -1 ? type : 'unknown';
    return {
      name: name,
      model: row && row.llm_model ? String(row.llm_model) : '',
      description: row && row.description ? String(row.description) : '',
      kind: kind,
      known: !!row
    };
  }

  // The drawer profile's pane (M36 F3 L3): no header, welcome or mascot (the drawer has its own
  // header and never idles), so none of their testids exist in the page. What is built is the
  // message log and a new-chat state that holds the drawer's own empty state (opts.emptyState, a
  // Node). The welcome and header members are detached, hidden stand-ins, so the instance's
  // renders can call the same methods; they build no testid.
  function createDrawerPane(opts) {
    var welcome = el('div', { className: 'chat-welcome', hidden: true });
    var welcomeInner = el('div', { className: 'chat-welcome-inner' });
    var header = el('header', { className: 'chat-header', hidden: true });
    var newState = el('div', { className: 'chat-new-state', hidden: true });
    newState.setAttribute('data-testid', 'gg-new-state');
    if (opts.emptyState) newState.appendChild(opts.emptyState);
    // The log's live-region attributes are set by the drawer while it is open (chat.js
    // setLive), not here: a closed drawer is hidden, and a second always-present role=log would
    // sit beside the Chats log in the page.
    var messages = el('div', { className: 'messages' });
    var chrome = el('div', { className: 'chat-chrome' }, [newState, messages]);
    function noop() {}
    return {
      welcome: welcome,
      welcomeInner: welcomeInner,
      welcomeNotice: null,
      chrome: chrome,
      header: header,
      newState: newState,
      messages: messages,
      newChatButton: null,
      pickDifferentButton: null,
      renderWelcome: noop,
      setNotice: noop,
      renderHeader: noop,
      renderNewState: function (view) { newState.hidden = !view || !!view.blank; }
    };
  }

  function create(opts) {
    opts = opts || {};
    if (opts.drawer) return createDrawerPane(opts);

    // ── The welcome: the empty and guidance states ────────────────────
    var greeting = el('h1', { className: 'chat-welcome-greeting', text: 'Hello.' });
    // An idle notice ("That conversation no longer exists"); the only
    // role=status inside the welcome.
    var notice = el('p', { className: 'chat-welcome-notice', role: 'status', hidden: true });
    var prompt = el('p', { className: 'chat-welcome-prompt', text: EMPTY_PROMPT });
    var guidanceSlot = el('div', { className: 'chat-welcome-guidance-slot' });
    var newChatButton = App.ui.button({
      variant: 'primary',
      label: 'New chat',
      icon: 'square-pen',
      testid: 'chat-empty-new-btn',
      onClick: function () { if (opts.onNewChat) opts.onNewChat(newChatButton); }
    });
    var actions = el('div', { className: 'chat-welcome-actions' });
    var inner = el('div', { className: 'chat-welcome-inner' }, [greeting, notice, prompt, guidanceSlot, actions]);
    var welcome = el('div', { className: 'chat-welcome', hidden: true }, [inner]);
    welcome.setAttribute('data-testid', 'chat-welcome');

    function renderWelcome(setup) {
      setup = setup || {};
      var complete = !!(setup.hasProviders && setup.hasAgents);
      while (guidanceSlot.firstChild) guidanceSlot.removeChild(guidanceSlot.firstChild);
      if (complete) {
        prompt.hidden = false;
        guidanceSlot.hidden = true;
        if (newChatButton.parentNode !== actions) actions.appendChild(newChatButton);
        actions.hidden = false;
      } else {
        prompt.hidden = true;
        guidanceSlot.appendChild(guidance(setup));
        guidanceSlot.hidden = false;
        if (newChatButton.parentNode) newChatButton.parentNode.removeChild(newChatButton);
        actions.hidden = true;
      }
    }

    function setNotice(text) {
      notice.textContent = text || '';
      notice.hidden = !text;
    }

    // ── The chrome: header, new-chat state, message log ───────────────
    var title = el('h1', { className: 'chat-header-title' });
    var line = el('span', { className: 'chat-agent-line' });
    line.setAttribute('data-testid', 'chat-agent-line');
    var header = el('header', { className: 'chat-header', hidden: true }, [title, line]);
    header.setAttribute('data-testid', 'chat-header');

    function renderHeader(view) {
      if (!view) {
        header.hidden = true;
        return;
      }
      title.textContent = view.title || '';
      line.textContent = view.blank ? '' : agentLine(view.agent);
      header.hidden = false;
    }

    var badge = App.ui.badge.live({ kind: 'unknown' });
    var agentName = el('h2', { className: 'chat-new-state-agent' });
    var description = el('p', { className: 'chat-new-state-description', hidden: true });
    var pickDifferentButton = App.ui.button({
      variant: 'ghost',
      size: 'sm',
      label: 'Pick a different agent',
      className: 'chat-new-state-pick',
      testid: 'chat-pick-different-btn',
      onClick: function () { if (opts.onPickDifferent) opts.onPickDifferent(pickDifferentButton); }
    });
    // M36 F1 L04: GleepGlorp's setup block (board screen 3): a warning with one primary action
    // while GleepGlorp is off, needs a model or has lost its provider.
    var setupAction = App.ui.button({
      variant: 'primary',
      label: 'Open GleepGlorp settings',
      className: 'chat-new-gleepglorp-setup-action',
      testid: 'chat-new-gleepglorp-setup-action',
      onClick: function () { if (setupAction.dataset.href && opts.go) opts.go(setupAction.dataset.href); }
    });
    // Built on first need and taken out of the DOM when not shown, so no other chat has a
    // (hidden) second banner beside the health banner.
    var setupBlock = null;
    var setupText = el('span', { className: 'chat-new-gleepglorp-setup-text' });
    var setupLine = el('p', { className: 'chat-new-gleepglorp-setup-line' },
      [App.ui.util.icon('alert-circle'), setupText]);
    // The visible sentence is hidden from assistive tech: the live region below announces it
    // (kept in sync by renderSetupBlock), so browse mode reads it once.
    setupLine.setAttribute('aria-hidden', 'true');
    var modelLine = el('p', { className: 'chat-new-state-model', hidden: true });
    modelLine.setAttribute('data-testid', 'chat-new-state-model');
    // A persistent live region (WCAG 4.1.3; not a second `.ui-banner`): built once, its text
    // set when the setup block shows and cleared when it does not, so a screen reader
    // announces the setup sentence even though the visible block is inserted on demand.
    var setupLive = el('span', { className: 'visually-hidden' });
    setupLive.setAttribute('role', 'status');
    setupLive.setAttribute('data-testid', 'chat-new-gleepglorp-setup-live');
    var newInner = el('div', { className: 'chat-new-state-inner' }, [badge.el, modelLine, agentName, description, pickDifferentButton, setupLive]);

    // The setup block's sentence, action label and target for a GleepGlorp info.
    function renderSetupBlock(view) {
      var show = !!(view.gleepglorp && view.state && view.state !== 'ready');
      if (!show) {
        setupLive.textContent = '';
        if (setupBlock && setupBlock.el.parentNode) setupBlock.el.parentNode.removeChild(setupBlock.el);
        return;
      }
      if (!setupBlock) {
        // Option A, "quiet next step": no box, no warning tone, one muted line and the button.
        setupBlock = { el: el('div', { className: 'chat-new-gleepglorp-setup' }, [setupLine, setupAction]) };
        setupBlock.el.setAttribute('data-testid', 'chat-new-gleepglorp-setup');
      }
      if (setupBlock.el.parentNode !== newInner) newInner.insertBefore(setupBlock.el, pickDifferentButton);
      var text, label, href;
      if (view.state === 'off') {
        text = 'GleepGlorp is turned off. Turn it on to chat with it.';
        label = 'Open GleepGlorp settings';
        href = App.chat.agentKind(App.chat.GLEEPGLORP).settingsHref;
      } else if (!view.hasProviders) {
        text = 'Add a model provider to start chatting with GleepGlorp.';
        label = 'Add a model provider';
        href = App.router.href({ destination: 'library', section: 'providers', create: true });
      } else {
        text = 'Choose a model to start chatting with GleepGlorp.';
        label = 'Choose a model';
        href = App.chat.agentKind(App.chat.GLEEPGLORP).settingsHref;
      }
      setupText.textContent = text;
      if (setupLive.textContent !== text) setupLive.textContent = text;
      setupAction.setAttribute('data-href', href);
      setupAction.textContent = label;
    }
    var newState = el('div', { className: 'chat-new-state', hidden: true }, [newInner]);
    newState.setAttribute('data-testid', 'chat-new-state');

    function renderNewState(view) {
      if (!view) {
        newState.hidden = true;
        return;
      }
      newState.hidden = false;
      // A cold `~new` route still validating its agent: a neutral, empty
      // state (the agent may be unknown and heal to #chats).
      newInner.hidden = !!view.blank;
      if (view.blank) return;
      if (view.gleepglorp) {
        // "Built in", with the model in its own line (the badge reads the kind, not the type).
        badge.set({ kind: 'builtin', text: 'Built in' });
        modelLine.textContent = view.model || '';
        modelLine.hidden = !view.model;
      } else {
        badge.set({ kind: view.kind || 'unknown', text: view.model });
        modelLine.hidden = true;
      }
      renderSetupBlock(view);
      agentName.textContent = view.name || '';
      description.textContent = view.description || '';
      description.hidden = !view.description;
    }

    var messages = el('div', {
      className: 'messages',
      role: 'log',
      'aria-live': 'polite',
      'aria-relevant': 'additions',
      'aria-atomic': 'false'
    });

    var chrome = el('div', { className: 'chat-chrome' }, [header, newState, messages]);

    return {
      welcome: welcome,
      welcomeInner: inner,
      welcomeNotice: notice,
      chrome: chrome,
      header: header,
      newState: newState,
      messages: messages,
      newChatButton: newChatButton,
      pickDifferentButton: pickDifferentButton,
      renderWelcome: renderWelcome,
      setNotice: setNotice,
      renderHeader: renderHeader,
      renderNewState: renderNewState
    };
  }

  window.App.chat.chatPane = {
    create: create,
    agentInfo: agentInfo,
    agentLine: agentLine,
    guidance: guidance
  };
})();
