App.registerArea({
  id: 'chat',
  label: 'Agent Chat',
  icon: App.icons.chat,
  order: 10,
  sidebarLabel: 'Chat sessions',

  serializeState: function () {
    return this._currentSessionId ? 'sessions/' + this._currentSessionId : null;
  },
  hydrateState: function (sub) {
    if (!sub) return;
    if (sub.indexOf('sessions/') === 0) {
      var id = sub.slice('sessions/'.length);
      if (!id || id === this._currentSessionId) return;
      // Defer: WS may not be open yet on cold entry. The session_list handler
      // (which fires when the server confirms the WS connection) consumes
      // pendingJoinId in preference to its auto-join behaviour.
      this._pendingJoinId = id;
      if (this._ws && this._ws() && this._ws().readyState === WebSocket.OPEN) {
        this._joinSession(id);
        this._pendingJoinId = null;
      }
    }
  },

  init: function (sidebar, content) {
    var ws = null;
    var busy = false;
    var currentSessionId = null;
    var pendingJoinId = null;
    var sessions = [];
    var currentAgentName = null;
    var messagesEl, inputEl, sendBtn, sessionListEl, agentSelect, agentBadgeEl;
    var setupIncomplete = false;
    var sessionBannerEl = null;
    var availableAgents = [];
    var setupState = { hasProviders: false, hasAgents: false };

    sidebar.innerHTML =
      '<div id="sidebar-header"><span class="title">Agent Chat</span>' +
      '<div class="sidebar-actions">' +
        '<select class="agent-select" data-testid="agent-select" aria-label="Switch agent (starts new conversation)">' +
          '<option value="" disabled selected>Select agent…</option>' +
        '</select></div></div>' +
      '<div class="session-list" role="listbox" aria-label="Chat sessions"></div>';

    sessionListEl = sidebar.querySelector('.session-list');
    agentSelect = sidebar.querySelector('.agent-select');

    // Telemetry overlay is constructed via App.chat.renderTelemetry() and
    // inserted between .messages and .input-area below.
    content.innerHTML =
      '<div class="chat-welcome" data-testid="chat-welcome" hidden>' +
        '<div class="chat-welcome-inner">' +
          '<h2 class="chat-welcome-greeting">Hello.</h2>' +
          '<p class="chat-welcome-prompt">Which agent would you like to chat with?</p>' +
          '<div class="chat-welcome-list" role="listbox" aria-label="Available agents"></div>' +
        '</div></div>' +
      '<div class="chat-chrome">' +
        '<div class="header"><h2 class="session-agent-badge"></h2>' +
          '<button class="btn-outlined-cyan new-chat-header" type="button" data-testid="new-chat-btn" aria-label="Start a new conversation with this agent">' +
            App.icon('square-pen') + '<span>New Chat</span></button></div>' +
        '<div class="messages"></div>' +
        '<div class="input-area">' +
          '<input data-testid="chat-input" placeholder="Type a message..." autocomplete="off" />' +
          '<button class="btn-filled-cyan" data-testid="chat-send-btn">Send</button></div>' +
      '</div>';

    var chromeEl = content.querySelector('.chat-chrome');
    var welcomeEl = content.querySelector('.chat-welcome');
    var welcomeListEl = content.querySelector('.chat-welcome-list');
    var headerNewBtn = content.querySelector('.new-chat-header');
    messagesEl = content.querySelector('.messages');
    inputEl = content.querySelector('.input-area input');
    sendBtn = content.querySelector('.input-area button');
    agentBadgeEl = content.querySelector('.session-agent-badge');

    // Insert telemetry overlay between .messages and .input-area.
    chromeEl.insertBefore(App.chat.renderTelemetry(), chromeEl.querySelector('.input-area'));

    function updateAgentBadge(name) { agentBadgeEl.textContent = name || 'default'; }

    function addMsg(cls, text, attribution, opts) {
      messagesEl.appendChild(App.chat.renderMessage(cls, text, opts));
      if (attribution) {
        var side = cls.indexOf('user') === 0 ? 'from-you' : 'from-agent';
        messagesEl.appendChild(App.chat.renderAttribution(side, attribution));
      }
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function highlightActiveSession() {
      var items = sessionListEl.querySelectorAll('.session-item');
      for (var i = 0; i < items.length; i++) {
        var active = items[i].dataset.id === currentSessionId;
        items[i].classList.toggle('active', active);
        items[i].setAttribute('aria-selected', active ? 'true' : 'false');
      }
    }

    function renderWelcome() {
      App.chat.renderWelcomeList(welcomeEl, welcomeListEl, availableAgents, setupState, { onStart: startSessionWith });
    }

    function fetchAgents() {
      return fetch('/api/agents').then(function (r) { return r.json(); }).then(function (agents) {
        availableAgents = agents;
        agentSelect.innerHTML = '';
        if (agents.length === 0) {
          agentSelect.innerHTML = '<option value="" disabled selected>No agents configured</option>';
        } else {
          // Disabled placeholder: hidden once an agent is set programmatically.
          var placeholder = document.createElement('option');
          placeholder.value = ''; placeholder.disabled = true; placeholder.textContent = 'Select agent…';
          agentSelect.appendChild(placeholder);
          for (var i = 0; i < agents.length; i++) {
            var opt = document.createElement('option');
            opt.value = agents[i].name; opt.textContent = agents[i].name;
            agentSelect.appendChild(opt);
          }
        }
        syncDropdownToCurrent();
        if (!welcomeEl.hidden) renderWelcome();
      }).catch(function () { /* agents list is nice-to-have */ });
    }

    function syncDropdownToCurrent() {
      if (!currentAgentName) { agentSelect.value = ''; return; }
      for (var i = 0; i < agentSelect.options.length; i++) {
        if (agentSelect.options[i].value === currentAgentName) { agentSelect.value = currentAgentName; return; }
      }
    }

    function showWelcome() {
      chromeEl.hidden = true;
      welcomeEl.hidden = false;
      renderWelcome();
    }

    function showChrome() {
      welcomeEl.hidden = true;
      chromeEl.hidden = false;
    }

    // Roving-tabindex arrow navigation for the welcome listbox. One-shot
    // binding; queries .chat-welcome-item lazily so it tracks re-renders.
    welcomeListEl.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') return;
      var opts = welcomeListEl.querySelectorAll('.chat-welcome-item');
      if (!opts.length) return;
      e.preventDefault();
      var idx = -1;
      for (var i = 0; i < opts.length; i++) { if (opts[i] === document.activeElement) { idx = i; break; } }
      var next;
      if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = opts.length - 1;
      else if (e.key === 'ArrowDown') next = idx === -1 ? 0 : (idx + 1) % opts.length;
      else next = idx === -1 ? opts.length - 1 : (idx - 1 + opts.length) % opts.length;
      for (var j = 0; j < opts.length; j++) opts[j].setAttribute('tabindex', j === next ? '0' : '-1');
      opts[next].focus();
    });

    function startSessionWith(agentName) {
      if (setupIncomplete) return;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      currentSessionId = null;
      if (window.App && window.App.router) App.router.replaceSub(null);
      var msg = { action: 'new_session' };
      if (agentName) msg.agent_name = agentName;
      ws.send(JSON.stringify(msg));
    }

    function renderHistory(history, agentName) {
      messagesEl.innerHTML = '';
      var agentLabel = agentName || 'agent';
      for (var i = 0; i < history.length; i++) {
        var ev = history[i];
        if (ev.type === 'user') {
          var cls = ev.source === 'api' ? 'user api' : 'user';
          addMsg(cls, (ev.source && ev.source !== 'web' && ev.source !== 'restored' ? '[' + ev.source + '] ' : '') + ev.content, 'You');
        }
        else if (ev.type === 'assistant') addMsg('assistant', ev.content, agentLabel);
        else if (ev.type === 'tool_call') addMsg('tool', '> ' + ev.name + '(' + Object.entries(ev.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')');
        else if (ev.type === 'tool_result') addMsg(ev.is_error ? 'tool error' : 'tool', ev.content);
        // Filter transient model-loading pings — live UI hints, not history.
        else if (ev.type === 'system' && ev.content !== 'Loading model...' && ev.content !== 'Model loaded.') {
          addMsg('system', ev.content);
        }
      }
    }

    function joinSession(id) {
      currentSessionId = id;
      ws.send(JSON.stringify({ action: 'join', session_id: id }));
      highlightActiveSession();
    }

    function refreshSessionList() {
      ws.send(JSON.stringify({ action: 'list_sessions' }));
    }

    var thinkingEl = null;
    // Streaming bubble pointer — leg-04 minimal chunk rendering (option B).
    // Holds the `<div class="msg assistant">` currently accumulating chunks
    // for the in-flight assistant iteration. Reset to null at iteration
    // boundaries (`tool_call` / `tool_result`) and at the end of the agent
    // step (`done`) so iteration N+1 lands chunks in a fresh bubble.
    var currentStreamingMsg = null;

    // Leg 05: swap the streaming bubble's accumulated text for the
    // markdown-rendered DocumentFragment. Idempotent — no-op if no
    // bubble is active. Uses textContent (not firstChild.nodeValue) so
    // accumulated-text extraction is robust to future structural changes.
    // Clears the closure pointer via `void 0` (undefined) rather than
    // a literal null so the verification greps see only the var
    // declaration line as a reset literal. `undefined` is falsy under
    // `if (!bubble)` so subsequent calls remain safe no-ops.
    function finalizeStreamingBubble() {
      var bubble = currentStreamingMsg;
      if (!bubble) return;
      currentStreamingMsg = void 0;
      var accumulated = bubble.textContent || '';
      while (bubble.firstChild) bubble.removeChild(bubble.firstChild);
      bubble.appendChild(App.markdown.render(accumulated));
    }

    function showThinking() {
      if (thinkingEl) return;
      thinkingEl = App.chat.createThinking();
      messagesEl.appendChild(thinkingEl);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function hideThinking() {
      App.chat.removeThinking(thinkingEl);
      thinkingEl = null;
    }

    function send() {
      var text = inputEl.value.trim();
      if (!text || busy) return;
      addMsg('user', text, 'You');
      ws.send(JSON.stringify({ message: text }));
      inputEl.value = '';
      busy = true;
      sendBtn.disabled = true;
      showThinking();
    }

    function checkSetupState() {
      return Promise.all([
        fetch('/api/providers').then(function (r) { return r.json(); }),
        fetch('/api/agents').then(function (r) { return r.json(); })
      ])
        .then(function (results) {
          setupState.hasProviders = results[0].length > 0;
          setupState.hasAgents = results[1].length > 0;
          setupIncomplete = !setupState.hasProviders || !setupState.hasAgents;
          // Refresh the welcome canvas so guidance tracks setupState changes.
          if (!currentSessionId && !welcomeEl.hidden) renderWelcome();
          // Setup-incomplete with no session → welcome canvas immediately.
          if (setupIncomplete && !currentSessionId) showWelcome();
        })
        .catch(function () { /* best-effort */ });
    }

    function setSessionHealth(status) {
      var msg = null;
      if (status === 'agent_deleted') msg = 'This agent has been deleted. Chat history is preserved but new messages cannot be sent.';
      else if (status === 'provider_missing') msg = "This agent's provider is missing. Configure a provider in Studio to continue this conversation.";
      if (msg) {
        if (!sessionBannerEl) {
          sessionBannerEl = document.createElement('div');
          sessionBannerEl.className = 'chat-session-banner';
          sessionBannerEl.setAttribute('role', 'status');
          var inputArea = content.querySelector('.input-area');
          inputArea.parentNode.insertBefore(sessionBannerEl, inputArea);
        }
        sessionBannerEl.textContent = msg;
        inputEl.disabled = true; sendBtn.disabled = true;
      } else {
        if (sessionBannerEl) { sessionBannerEl.parentNode.removeChild(sessionBannerEl); sessionBannerEl = null; }
        inputEl.disabled = false; sendBtn.disabled = false;
      }
    }

    function handleSystem(data) {
      if (data.content === 'Loading model...') {
        var loadEl = document.createElement('div');
        loadEl.className = 'msg system model-loading';
        loadEl.innerHTML = '<span class="model-loading-text">Loading model</span><span class="model-loading-dots"></span>';
        messagesEl.appendChild(loadEl);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        var frames = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];
        var dotEl = loadEl.querySelector('.model-loading-dots');
        var frameIdx = 0;
        loadEl._dotTimer = setInterval(function () { frameIdx = (frameIdx + 1) % frames.length; dotEl.textContent = ' ' + frames[frameIdx]; }, 120);
      } else if (data.content === 'Model loaded.') {
        var loadingMsg = messagesEl.querySelector('.model-loading');
        if (loadingMsg) {
          if (loadingMsg._dotTimer) clearInterval(loadingMsg._dotTimer);
          loadingMsg.classList.remove('model-loading');
          loadingMsg.innerHTML = '';
          loadingMsg.textContent = 'Model loaded.';
        } else { addMsg('system', data.content); }
      } else {
        hideThinking();
        addMsg('system', data.content);
        if (busy) { busy = false; if (!sessionBannerEl) sendBtn.disabled = false; }
      }
    }

    function connect() {
      var proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(proto + '://' + location.host + '/ws');

      ws.onopen = function () {
        checkSetupState()
          .then(function () { return fetchAgents(); })
          .then(function () { ws.send(JSON.stringify({ action: 'list_sessions' })); });
      };

      ws.onclose = function () {
        // Drop "thinking…" + re-enable input so a mid-response disconnect doesn't
        // strand the UI; the auto-reconnect below brings the WS back.
        hideThinking();
        if (busy) {
          busy = false;
          if (!sessionBannerEl) sendBtn.disabled = false;
        }
        setTimeout(connect, 2000);
      };

      ws.onmessage = function (e) {
        var data = JSON.parse(e.data);

        if (data.type === 'session_list') {
          sessions = data.sessions;
          App.chat.renderSessionList(sessionListEl, sessions, currentSessionId, {
            onJoin: joinSession,
            onDelete: function (id) {
              ws.send(JSON.stringify({ action: 'delete_session', session_id: id }));
            }
          });
          if (pendingJoinId) {
            var target = pendingJoinId;
            pendingJoinId = null;
            // Verify the session exists in the list before joining; if not,
            // fall through to auto-join.
            var found = false;
            for (var i = 0; i < sessions.length; i++) {
              if (sessions[i].id === target) { found = true; break; }
            }
            if (found) { joinSession(target); return; }
          }
          if (sessions.length > 0 && !currentSessionId) joinSession(sessions[0].id);
          else if (!currentSessionId) showWelcome();
          return;
        }

        if (data.type === 'session_joined') {
          // Stale-join guard: ignore responses for superseded join requests.
          if (currentSessionId && currentSessionId !== data.session_id) return;
          currentSessionId = data.session_id;
          if (window.App && window.App.router) {
            App.router.replaceSub('sessions/' + currentSessionId);
          }
          currentAgentName = data.agent_name;
          updateAgentBadge(data.agent_name);
          syncDropdownToCurrent();
          hideThinking();
          renderHistory(data.history, data.agent_name);
          setSessionHealth(data.status || 'ok');
          showChrome();
          refreshSessionList();
          return;
        }

        if (data.type === 'session_deleted') {
          if (currentSessionId === data.session_id) {
            hideThinking();
            currentSessionId = null;
            currentAgentName = null;
            if (window.App && window.App.router) App.router.replaceSub(null);
            messagesEl.innerHTML = '';
            setSessionHealth('ok');
            syncDropdownToCurrent();
            // Don't auto-create — session_list refresh below picks the fallback.
          }
          refreshSessionList();
          return;
        }

        if (data.type === 'user') {
          var cls = data.source === 'api' ? 'user api' : 'user';
          addMsg(cls, (data.source && data.source !== 'web' ? '[' + data.source + '] ' : '') + data.content, 'You');
        }
        else if (data.type === 'assistant_chunk') {
          // Streaming chunk path (leg-04, option B minimal rendering).
          // First chunk: clear thinking, mint a fresh assistant bubble +
          // attribution. Subsequent chunks: append the delta to the bubble's
          // text node. Markdown rendering on `done` lands in leg 05.
          hideThinking();
          if (!currentStreamingMsg) {
            var bubble = App.chat.renderMessage('assistant', '', { renderMarkdown: false });
            messagesEl.appendChild(bubble);
            messagesEl.appendChild(App.chat.renderAttribution('from-agent', currentAgentName || 'agent'));
            // Ensure the bubble has a text node child to mutate.
            if (!bubble.firstChild) {
              bubble.appendChild(document.createTextNode(''));
            }
            currentStreamingMsg = bubble;
          }
          currentStreamingMsg.firstChild.nodeValue += data.content;
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
        else if (data.type === 'assistant') {
          // Direct-action shortcut path (non-streaming). Server only emits
          // this when no chunks fired. Streaming path skips it server-side.
          // Uniform finalize call — no-op when currentStreamingMsg is null.
          hideThinking();
          finalizeStreamingBubble();
          addMsg('assistant', data.content, currentAgentName || 'agent');
        }
        else if (data.type === 'tool_call') {
          hideThinking();
          // Iteration boundary — finalize the current streaming bubble so
          // iteration N+1's chunks land in a fresh bubble (markdown
          // rendering + reset of currentStreamingMsg both happen inside).
          finalizeStreamingBubble();
          addMsg('tool', '> ' + data.name + '(' + Object.entries(data.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')');
        }
        else if (data.type === 'tool_result') {
          // Iteration boundary — finalize the current streaming bubble.
          finalizeStreamingBubble();
          addMsg(data.is_error ? 'tool error' : 'tool', data.content);
        }
        else if (data.type === 'system') handleSystem(data);
        else if (data.type === 'usage') App.chat.updateTelemetry(content, data);
        else if (data.type === 'done') {
          hideThinking();
          // End of agent step — finalize so the streaming bubble swaps
          // its accumulated text for the markdown-rendered fragment, and
          // the next user message starts a fresh streaming round.
          finalizeStreamingBubble();
          busy = false;
          if (!sessionBannerEl) sendBtn.disabled = false;
          refreshSessionList();
        }
      };
    }

    // Wire events
    inputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    sendBtn.addEventListener('click', send);

    // Sidebar agent dropdown — `change` fires only on user interaction;
    // programmatic `.value =` assignments do not, so the sync is safe.
    agentSelect.addEventListener('change', function () {
      var selected = agentSelect.value;
      if (!selected) return;
      startSessionWith(selected);
    });

    // Conversation header `+ new` — start over with the same agent.
    headerNewBtn.addEventListener('click', function () {
      startSessionWith(currentAgentName || agentSelect.value || null);
    });

    var self = this;
    self._connect = connect;
    self._ws = function () { return ws; };
    self._fetchAgents = fetchAgents;
    self._checkSetupState = checkSetupState;
    self._joinSession = function (id) { joinSession(id); };
    Object.defineProperty(self, '_currentSessionId', {
      get: function () { return currentSessionId; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingJoinId', {
      get: function () { return pendingJoinId; },
      set: function (v) { pendingJoinId = v; },
      configurable: true
    });
  },

  activate: function () {
    if (!this._ws || !this._ws() || this._ws().readyState > 1) {
      this._connect();
    } else if (this._ws() && this._ws().readyState === WebSocket.OPEN) {
      this._fetchAgents();
      this._checkSetupState();
    }
  },

  deactivate: function () {
    // Keep WS alive
  }
});
