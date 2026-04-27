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
      // Warm path: WS is open and currentSessionId differs — join immediately
      // and clear the pending stash.
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
    var messagesEl, inputEl, sendBtn, statusEl, sessionListEl, agentSelect, agentBadgeEl;
    var setupIncomplete = false;
    var sessionBannerEl = null;

    var availableAgents = [];
    var setupState = { hasProviders: false, hasAgents: false };

    // Build sidebar DOM
    sidebar.innerHTML =
      '<div id="sidebar-header">' +
        '<span class="title">Agent Chat</span>' +
        '<div class="sidebar-actions">' +
          '<select class="agent-select" data-testid="agent-select" aria-label="Switch agent (starts new conversation)">' +
            '<option value="" disabled selected>Select agent…</option>' +
          '</select>' +
        '</div>' +
      '</div>' +
      '<div class="session-list" role="listbox" aria-label="Chat sessions"></div>';

    sessionListEl = sidebar.querySelector('.session-list');
    agentSelect = sidebar.querySelector('.agent-select');

    // Build content DOM
    content.innerHTML =
      '<div class="chat-welcome" data-testid="chat-welcome" hidden>' +
        '<div class="chat-welcome-inner">' +
          '<h2 class="chat-welcome-greeting">Hello.</h2>' +
          '<p class="chat-welcome-prompt">Which agent would you like to chat with?</p>' +
          '<div class="chat-welcome-list" role="listbox" aria-label="Available agents"></div>' +
        '</div>' +
      '</div>' +
      '<div class="chat-chrome">' +
        '<div class="header">' +
          '<h2 class="session-agent-badge"></h2>' +
          '<button class="new-chat-header" type="button" data-testid="new-chat-btn" aria-label="Start a new conversation with this agent">' +
            App.icon('square-pen') +
            '<span>New Chat</span>' +
          '</button>' +
        '</div>' +
        '<div class="messages"></div>' +
        // Telemetry overlay: chrome-free, ghosted by default; hover/focus
        // expands details (max-width transition) and lifts opacity to 1.
        '<div class="telemetry-overlay" tabindex="0" role="status" aria-label="Token usage">' +
          '<div class="telemetry-summary">' +
            '<div class="context-bar-wrap"><div class="context-bar"></div></div>' +
            '<span class="value t-ctx-pct">0%</span>' +
          '</div>' +
          '<div class="telemetry-details">' +
            '<span class="telemetry"><span class="label">in:</span> <span class="value t-in">0</span></span>' +
            '<span class="telemetry"><span class="label">out:</span> <span class="value t-out">0</span></span>' +
            '<span class="telemetry"><span class="label">ctx:</span> <span class="value t-ctx">0</span></span>' +
          '</div>' +
        '</div>' +
        '<div class="input-area">' +
          '<input data-testid="chat-input" placeholder="Type a message..." autocomplete="off" />' +
          '<button data-testid="chat-send-btn">Send</button>' +
        '</div>' +
      '</div>';

    var chromeEl = content.querySelector('.chat-chrome');
    var welcomeEl = content.querySelector('.chat-welcome');
    var welcomeListEl = content.querySelector('.chat-welcome-list');
    var headerNewBtn = content.querySelector('.new-chat-header');
    messagesEl = content.querySelector('.messages');
    inputEl = content.querySelector('.input-area input');
    sendBtn = content.querySelector('.input-area button');
    agentBadgeEl = content.querySelector('.session-agent-badge');

    function fmtTokens(n) {
      if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
      if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
      return String(n);
    }

    function updateTelemetry(data) {
      content.querySelector('.t-in').textContent = fmtTokens(data.input_tokens);
      content.querySelector('.t-out').textContent = fmtTokens(data.output_tokens);
      content.querySelector('.t-ctx').textContent = fmtTokens(data.context_tokens);
      var pct = data.max_context_tokens > 0
        ? Math.min(100, Math.round(data.context_tokens / data.max_context_tokens * 100))
        : 0;
      content.querySelector('.t-ctx-pct').textContent = pct + '%';
      var bar = content.querySelector('.context-bar');
      bar.style.width = pct + '%';
      bar.className = 'context-bar' + (pct >= 90 ? ' crit' : pct >= 70 ? ' warn' : '');
    }

    function updateAgentBadge(name) {
      agentBadgeEl.textContent = name || 'default';
    }

    function addMsg(cls, text, attribution) {
      var el = document.createElement('div');
      el.className = 'msg ' + cls;
      el.setAttribute('data-testid', 'message');
      el.textContent = text;
      messagesEl.appendChild(el);
      if (attribution) {
        var labelEl = document.createElement('div');
        // 'from-you' for user messages (right-aligned), 'from-agent' for everything else.
        var side = cls.indexOf('user') === 0 ? 'from-you' : 'from-agent';
        labelEl.className = 'msg-attribution ' + side;
        labelEl.textContent = attribution;
        messagesEl.appendChild(labelEl);
      }
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function highlightActiveSession() {
      var items = sessionListEl.querySelectorAll('.session-item');
      for (var i = 0; i < items.length; i++) {
        var isActive = items[i].dataset.id === currentSessionId;
        items[i].classList.toggle('active', isActive);
        items[i].setAttribute('aria-selected', isActive ? 'true' : 'false');
      }
    }

    function fetchAgents() {
      return fetch('/api/agents')
        .then(function (r) { return r.json(); })
        .then(function (agents) {
          availableAgents = agents;
          agentSelect.innerHTML = '';
          if (agents.length === 0) {
            agentSelect.innerHTML = '<option value="" disabled selected>No agents configured</option>';
          } else {
            // Placeholder option — selected only when no current session.
            // Disabled so it can't be chosen by user; not visible in the picker
            // once an agent is set programmatically (selectedIndex moves).
            var placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.disabled = true;
            placeholder.textContent = 'Select agent…';
            agentSelect.appendChild(placeholder);
            for (var i = 0; i < agents.length; i++) {
              var opt = document.createElement('option');
              opt.value = agents[i].name;
              opt.textContent = agents[i].name;
              agentSelect.appendChild(opt);
            }
          }
          // Sync to current session's agent if any.
          syncDropdownToCurrent();
          // If welcome is visible, refresh its listbox now that we have agents.
          if (!welcomeEl.hidden) renderWelcomeList();
        })
        .catch(function () { /* agents list is nice-to-have */ });
    }

    function syncDropdownToCurrent() {
      if (!currentAgentName) {
        agentSelect.value = '';
        return;
      }
      for (var i = 0; i < agentSelect.options.length; i++) {
        if (agentSelect.options[i].value === currentAgentName) {
          agentSelect.value = currentAgentName;
          return;
        }
      }
    }

    function showWelcome() {
      chromeEl.hidden = true;
      welcomeEl.hidden = false;
      renderWelcomeList();
    }

    function showChrome() {
      welcomeEl.hidden = true;
      chromeEl.hidden = false;
    }

    // Renders the welcome canvas based on current setup + agents state.
    // Four states: no providers (& maybe no agents), no agents only,
    // ready-with-agents (full picker), and "no agents in fetch but live"
    // (rare race: setupState says agents exist but availableAgents is empty).
    function renderWelcomeList() {
      var promptEl = welcomeEl.querySelector('.chat-welcome-prompt');
      welcomeListEl.innerHTML = '';

      // Setup-incomplete states — show a guidance line, no agent picker.
      if (!setupState.hasProviders || !setupState.hasAgents) {
        promptEl.hidden = true;
        // Drop the listbox role when there are no options to pick.
        welcomeListEl.removeAttribute('role');
        welcomeListEl.removeAttribute('aria-label');
        var guidance = document.createElement('p');
        guidance.className = 'chat-welcome-guidance';
        if (!setupState.hasProviders && !setupState.hasAgents) {
          guidance.appendChild(document.createTextNode('Add a provider in '));
          guidance.appendChild(welcomeLink('Settings', 'admin'));
          guidance.appendChild(document.createTextNode(', then create an agent in '));
          guidance.appendChild(welcomeLink('Agent Studio', 'studio'));
          guidance.appendChild(document.createTextNode(' to start chatting.'));
        } else if (!setupState.hasProviders) {
          guidance.appendChild(document.createTextNode('Add a provider in '));
          guidance.appendChild(welcomeLink('Settings', 'admin'));
          guidance.appendChild(document.createTextNode(' to start chatting.'));
        } else {
          guidance.appendChild(document.createTextNode('Create an agent in '));
          guidance.appendChild(welcomeLink('Agent Studio', 'studio'));
          guidance.appendChild(document.createTextNode(' to start chatting.'));
        }
        welcomeListEl.appendChild(guidance);
        return;
      }

      // Ready state — show the agent picker.
      promptEl.hidden = false;
      welcomeListEl.setAttribute('role', 'listbox');
      welcomeListEl.setAttribute('aria-label', 'Available agents');
      for (var i = 0; i < availableAgents.length; i++) {
        (function (agent, idx) {
          var opt = document.createElement('div');
          opt.className = 'chat-welcome-item';
          opt.setAttribute('role', 'option');
          opt.setAttribute('tabindex', idx === 0 ? '0' : '-1');
          opt.setAttribute('aria-selected', 'false');
          opt.dataset.agentName = agent.name;

          var nameEl = document.createElement('span');
          nameEl.className = 'chat-welcome-item-name';
          nameEl.textContent = agent.name;
          opt.appendChild(nameEl);

          var metaBits = [];
          if (agent.model) metaBits.push(agent.model);
          if (agent.provider) metaBits.push(agent.provider);
          if (metaBits.length) {
            var metaEl = document.createElement('span');
            metaEl.className = 'chat-welcome-item-meta';
            metaEl.textContent = metaBits.join(' · ');
            opt.appendChild(metaEl);
          }

          opt.addEventListener('click', function () { startSessionWith(agent.name); });
          opt.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              startSessionWith(agent.name);
            }
          });
          welcomeListEl.appendChild(opt);
        })(availableAgents[i], i);
      }
    }

    function welcomeLink(text, areaId) {
      var a = document.createElement('a');
      a.className = 'chat-welcome-link';
      a.href = '#' + areaId;
      a.textContent = text;
      return a;
    }

    // Roving-tabindex arrow navigation for the welcome listbox.
    welcomeListEl.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' &&
          e.key !== 'Home' && e.key !== 'End') return;
      var opts = welcomeListEl.querySelectorAll('.chat-welcome-item');
      if (!opts.length) return;
      e.preventDefault();
      var idx = -1;
      for (var i = 0; i < opts.length; i++) {
        if (opts[i] === document.activeElement) { idx = i; break; }
      }
      var next;
      if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = opts.length - 1;
      else if (e.key === 'ArrowDown') next = idx === -1 ? 0 : (idx + 1) % opts.length;
      else next = idx === -1 ? opts.length - 1 : (idx - 1 + opts.length) % opts.length;
      for (var j = 0; j < opts.length; j++) {
        opts[j].setAttribute('tabindex', j === next ? '0' : '-1');
      }
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

    function startOfDay(d) {
      return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    }

    function bucketForSession(s, nowDay) {
      // Sessions carry created_at/updated_at as ISO strings. Sort buckets by
      // most recent activity (updated_at falls back to created_at).
      var ts = s.updated_at || s.created_at;
      if (!ts) return 'older';
      var parsed = new Date(ts);
      if (isNaN(parsed.getTime())) return 'older';
      var sessionDay = startOfDay(parsed);
      var dayDiff = Math.round((nowDay - sessionDay) / 86400000);
      if (dayDiff <= 0) return 'today';
      if (dayDiff === 1) return 'yesterday';
      if (dayDiff <= 7) return 'last7';
      if (dayDiff <= 30) return 'last30';
      return 'older';
    }

    var BUCKET_ORDER = ['today', 'yesterday', 'last7', 'last30', 'older'];
    var BUCKET_LABELS = {
      today: 'Today',
      yesterday: 'Yesterday',
      last7: 'Last 7 Days',
      last30: 'Last 30 Days',
      older: 'Older'
    };

    function buildSessionItem(s) {
      var el = document.createElement('div');
      el.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
      el.setAttribute('role', 'option');
      el.setAttribute('tabindex', '0');
      el.setAttribute('aria-selected', s.id === currentSessionId ? 'true' : 'false');
      el.dataset.id = s.id;

      var textWrap = document.createElement('div');
      textWrap.className = 'session-item-text';

      var titleSpan = document.createElement('span');
      titleSpan.className = 'session-item-title';
      titleSpan.textContent = s.title;
      textWrap.appendChild(titleSpan);

      var agentSpan = document.createElement('span');
      agentSpan.className = 'session-item-agent';
      agentSpan.textContent = s.agent_name || 'default';
      textWrap.appendChild(agentSpan);

      el.appendChild(textWrap);

      var delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'delete';
      delBtn.setAttribute('aria-label', 'Delete session');
      delBtn.innerHTML = App.icon('x');
      delBtn.onclick = function (e) {
        e.stopPropagation();
        ws.send(JSON.stringify({ action: 'delete_session', session_id: s.id }));
      };
      el.appendChild(delBtn);

      el.onclick = function () { joinSession(s.id); };
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          joinSession(s.id);
        }
      });
      return el;
    }

    function renderSessionList(sessions) {
      sessionListEl.innerHTML = '';
      if (!sessions.length) return;

      // Order sessions by updated_at desc within each bucket; assign to buckets.
      var nowDay = startOfDay(new Date());
      var grouped = {};
      for (var i = 0; i < sessions.length; i++) {
        var s = sessions[i];
        var bucket = bucketForSession(s, nowDay);
        (grouped[bucket] = grouped[bucket] || []).push(s);
      }

      // Sessions list arrives unordered; sort each bucket by recency.
      function recency(s) { return new Date(s.updated_at || s.created_at || 0).getTime(); }
      for (var b in grouped) {
        if (Object.prototype.hasOwnProperty.call(grouped, b)) {
          grouped[b].sort(function (a, c) { return recency(c) - recency(a); });
        }
      }

      // Render heading first, then each non-empty bucket as a role=group.
      var headingEl = document.createElement('div');
      headingEl.className = 'session-list-heading';
      headingEl.textContent = 'Chat History';
      sessionListEl.appendChild(headingEl);

      for (var k = 0; k < BUCKET_ORDER.length; k++) {
        var key = BUCKET_ORDER[k];
        if (!grouped[key] || !grouped[key].length) continue;

        var groupEl = document.createElement('div');
        groupEl.className = 'session-group';
        groupEl.setAttribute('role', 'group');

        var labelId = 'session-group-' + key;
        var labelEl = document.createElement('div');
        labelEl.className = 'session-group-label';
        labelEl.id = labelId;
        labelEl.textContent = BUCKET_LABELS[key];
        groupEl.setAttribute('aria-labelledby', labelId);
        groupEl.appendChild(labelEl);

        for (var m = 0; m < grouped[key].length; m++) {
          groupEl.appendChild(buildSessionItem(grouped[key][m]));
        }
        sessionListEl.appendChild(groupEl);
      }
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
        // Filter out transient model-loading status pings — they are live UI
        // hints, not part of the persistent conversation.
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
    var THINKING_FRAMES = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];

    function showThinking() {
      if (thinkingEl) return;
      thinkingEl = document.createElement('div');
      thinkingEl.className = 'msg assistant model-loading thinking';
      thinkingEl.setAttribute('data-testid', 'thinking-indicator');
      thinkingEl.innerHTML = '<span class="model-loading-text">thinking</span><span class="model-loading-dots"></span>';
      messagesEl.appendChild(thinkingEl);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      var dotEl = thinkingEl.querySelector('.model-loading-dots');
      var frameIdx = 0;
      thinkingEl._dotTimer = setInterval(function () {
        frameIdx = (frameIdx + 1) % THINKING_FRAMES.length;
        dotEl.textContent = ' ' + THINKING_FRAMES[frameIdx];
      }, 120);
    }

    function hideThinking() {
      if (!thinkingEl) return;
      if (thinkingEl._dotTimer) clearInterval(thinkingEl._dotTimer);
      thinkingEl.remove();
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
          // If no current session and welcome is the active view, refresh
          // its content so the guidance reflects the latest state (e.g. user
          // just added a provider in Settings and came back).
          if (!currentSessionId && !welcomeEl.hidden) renderWelcomeList();
          // Setup-incomplete with no session means we should be on the welcome
          // canvas, even if list_sessions hasn't fired yet on this activation.
          if (setupIncomplete && !currentSessionId) showWelcome();
        })
        .catch(function () { /* best-effort */ });
    }

    function setSessionHealth(status) {
      // Default unknown status to 'ok' — defensive against future protocol additions
      var msg = null;
      if (status === 'agent_deleted') {
        msg = 'This agent has been deleted. Chat history is preserved but new messages cannot be sent.';
      } else if (status === 'provider_missing') {
        msg = "This agent's provider is missing. Configure a provider in Studio to continue this conversation.";
      }

      if (msg) {
        if (!sessionBannerEl) {
          sessionBannerEl = document.createElement('div');
          sessionBannerEl.className = 'chat-session-banner';
          sessionBannerEl.setAttribute('role', 'status');
          // Position directly above the input area so the banner explains
          // exactly why the input below it is disabled.
          var inputArea = content.querySelector('.input-area');
          inputArea.parentNode.insertBefore(sessionBannerEl, inputArea);
        }
        sessionBannerEl.textContent = msg;
        inputEl.disabled = true;
        sendBtn.disabled = true;
      } else {
        if (sessionBannerEl) {
          sessionBannerEl.parentNode.removeChild(sessionBannerEl);
          sessionBannerEl = null;
        }
        inputEl.disabled = false;
        sendBtn.disabled = false;
      }
    }

    function connect() {
      var proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(proto + '://' + location.host + '/ws');

      ws.onopen = function () {
        checkSetupState().then(function () {
          return fetchAgents();
        }).then(function () {
          ws.send(JSON.stringify({ action: 'list_sessions' }));
        });
      };

      ws.onclose = function () {
        // Drop the "thinking…" indicator and re-enable the input so a
        // mid-response disconnect doesn't strand the UI; the auto-reconnect
        // below brings the WS back.
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
          renderSessionList(sessions);
          if (pendingJoinId) {
            var target = pendingJoinId;
            pendingJoinId = null;
            // Verify the session exists in the list before joining; if not, fall
            // back to the auto-join (or stay empty if nothing is available).
            var found = false;
            for (var i = 0; i < sessions.length; i++) {
              if (sessions[i].id === target) { found = true; break; }
            }
            if (found) {
              joinSession(target);
              return;
            }
            // pendingJoinId did not match — fall through to auto-join.
          }
          if (sessions.length > 0 && !currentSessionId) {
            joinSession(sessions[0].id);
          } else if (!currentSessionId) {
            // No active session — show the welcome canvas. It self-adapts
            // to the current setup state (providers / agents / both
            // missing → guidance with deep-links; ready → agent picker).
            showWelcome();
          }
          return;
        }

        if (data.type === 'session_joined') {
          // Stale-join guard: ignore responses for superseded join requests.
          // joinSession sets currentSessionId optimistically before sending; if a newer
          // join has been issued since, the response for the older one is irrelevant.
          // Auto-create paths (new_session / fallback) leave currentSessionId null until
          // the response arrives, so guard only when an explicit id was set and mismatches.
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
            // Don't auto-create. The session_list refresh below will either
            // join the most recent remaining session or, if the list is empty,
            // show the welcome canvas via the session_list handler.
          }
          refreshSessionList();
          return;
        }

        if (data.type === 'user') {
          var cls = data.source === 'api' ? 'user api' : 'user';
          addMsg(cls, (data.source && data.source !== 'web' ? '[' + data.source + '] ' : '') + data.content, 'You');
        }
        else if (data.type === 'assistant') {
          hideThinking();
          addMsg('assistant', data.content, currentAgentName || 'agent');
        }
        else if (data.type === 'tool_call') {
          hideThinking();
          addMsg('tool', '> ' + data.name + '(' + Object.entries(data.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')');
        }
        else if (data.type === 'tool_result') addMsg(data.is_error ? 'tool error' : 'tool', data.content);
        else if (data.type === 'system') {
          if (data.content === 'Loading model...') {
            // Show inline ASCII loading animation
            var loadEl = document.createElement('div');
            loadEl.className = 'msg system model-loading';
            loadEl.innerHTML = '<span class="model-loading-text">Loading model</span><span class="model-loading-dots"></span>';
            messagesEl.appendChild(loadEl);
            messagesEl.scrollTop = messagesEl.scrollHeight;
            // Animate dots: ⣾ ⣽ ⣻ ⢿ ⡿ ⣟ ⣯ ⣷
            var frames = ['\u28fe', '\u28fd', '\u28fb', '\u28bf', '\u287f', '\u28df', '\u28ef', '\u28f7'];
            var dotEl = loadEl.querySelector('.model-loading-dots');
            var frameIdx = 0;
            loadEl._dotTimer = setInterval(function () {
              frameIdx = (frameIdx + 1) % frames.length;
              dotEl.textContent = ' ' + frames[frameIdx];
            }, 120);
          } else if (data.content === 'Model loaded.') {
            // Replace loading animation with done message
            var loadingMsg = messagesEl.querySelector('.model-loading');
            if (loadingMsg) {
              if (loadingMsg._dotTimer) clearInterval(loadingMsg._dotTimer);
              loadingMsg.classList.remove('model-loading');
              loadingMsg.innerHTML = '';
              loadingMsg.textContent = 'Model loaded.';
            } else {
              addMsg('system', data.content);
            }
          } else {
            hideThinking();
            addMsg('system', data.content);
            // Reset busy state if an error arrived (e.g. failed session creation)
            if (busy) {
              busy = false;
              // Only re-enable if no degraded session banner is active
              if (!sessionBannerEl) {
                sendBtn.disabled = false;
              }
            }
          }
        }
        else if (data.type === 'usage') {
          updateTelemetry(data);
        }
        else if (data.type === 'done') {
          hideThinking();
          busy = false;
          // Only re-enable if no degraded session banner is active
          if (!sessionBannerEl) {
            sendBtn.disabled = false;
          }
          refreshSessionList();
        }
      };
    }

    // Wire events
    inputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    sendBtn.addEventListener('click', send);

    // Sidebar agent dropdown — changing it starts a new conversation with
    // the chosen agent. The `change` event fires only on user interaction;
    // programmatic `.value =` assignments (used to mirror the current
    // session's agent) do not fire it, so the sync is safe.
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

    // Store references for activate and hydrateState
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
