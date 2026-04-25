App.registerArea({
  id: 'chat',
  label: 'Chat',
  icon: '\uD83D\uDCAC',
  order: 10,

  init: function (sidebar, content) {
    var ws = null;
    var busy = false;
    var currentSessionId = null;
    var currentAgentName = null;
    var messagesEl, inputEl, sendBtn, statusEl, sessionListEl, agentSelect, agentBadgeEl;
    var bannerEl = null;

    // Build sidebar DOM
    sidebar.innerHTML =
      '<div id="sidebar-header">' +
        '<span class="title">the-one</span>' +
        '<div class="sidebar-actions">' +
          '<select class="agent-select"><option value="">default</option></select>' +
          '<button class="new-chat">+ new</button>' +
        '</div>' +
      '</div>' +
      '<div class="session-list"></div>';

    sessionListEl = sidebar.querySelector('.session-list');
    var newChatBtn = sidebar.querySelector('.new-chat');
    agentSelect = sidebar.querySelector('.agent-select');

    // Build content DOM
    content.innerHTML =
      '<div class="header">' +
        '<span class="status">connecting...</span>' +
        '<span class="session-agent-badge"></span>' +
        '<div class="telemetry">' +
          '<span><span class="label">in:</span> <span class="value t-in">0</span></span>' +
          '<span><span class="label">out:</span> <span class="value t-out">0</span></span>' +
          '<span><span class="label">ctx:</span> <span class="value t-ctx">0</span></span>' +
          '<div class="context-bar-wrap"><div class="context-bar"></div></div>' +
          '<span class="value t-ctx-pct">0%</span>' +
        '</div>' +
      '</div>' +
      '<div class="messages"></div>' +
      '<div class="input-area">' +
        '<input placeholder="Type a message..." autocomplete="off" />' +
        '<button>Send</button>' +
      '</div>';

    messagesEl = content.querySelector('.messages');
    inputEl = content.querySelector('.input-area input');
    sendBtn = content.querySelector('.input-area button');
    statusEl = content.querySelector('.status');
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

    function addMsg(cls, text) {
      var el = document.createElement('div');
      el.className = 'msg ' + cls;
      el.textContent = text;
      messagesEl.appendChild(el);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function highlightActiveSession() {
      var items = sessionListEl.querySelectorAll('.session-item');
      for (var i = 0; i < items.length; i++) {
        items[i].classList.toggle('active', items[i].dataset.id === currentSessionId);
      }
    }

    function fetchAgents() {
      return fetch('/api/agents')
        .then(function (r) { return r.json(); })
        .then(function (agents) {
          var prev = agentSelect.value;
          agentSelect.innerHTML = '';
          if (agents.length === 0) {
            agentSelect.innerHTML = '<option value="" disabled>No agents configured</option>';
          }
          for (var i = 0; i < agents.length; i++) {
            var opt = document.createElement('option');
            opt.value = agents[i].name;
            opt.textContent = agents[i].name;
            agentSelect.appendChild(opt);
          }
          // Preserve previous selection if still available
          if (prev) {
            for (var j = 0; j < agentSelect.options.length; j++) {
              if (agentSelect.options[j].value === prev) {
                agentSelect.value = prev;
                break;
              }
            }
          }
        })
        .catch(function () { /* agents list is nice-to-have */ });
    }

    function renderSessionList(sessions) {
      sessionListEl.innerHTML = '';
      for (var i = 0; i < sessions.length; i++) {
        (function (s) {
          var el = document.createElement('div');
          el.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
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

          var delBtn = document.createElement('span');
          delBtn.className = 'delete';
          delBtn.textContent = '\u2715';
          delBtn.onclick = function (e) {
            e.stopPropagation();
            ws.send(JSON.stringify({ action: 'delete_session', session_id: s.id }));
          };
          el.appendChild(delBtn);

          el.onclick = function () { joinSession(s.id); };
          sessionListEl.appendChild(el);
        })(sessions[i]);
      }
    }

    function renderHistory(history) {
      messagesEl.innerHTML = '';
      for (var i = 0; i < history.length; i++) {
        var ev = history[i];
        if (ev.type === 'user') {
          var cls = ev.source === 'api' ? 'user api' : 'user';
          addMsg(cls, (ev.source && ev.source !== 'web' && ev.source !== 'restored' ? '[' + ev.source + '] ' : '') + ev.content);
        }
        else if (ev.type === 'assistant') addMsg('assistant', ev.content);
        else if (ev.type === 'tool_call') addMsg('tool', '> ' + ev.name + '(' + Object.entries(ev.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')');
        else if (ev.type === 'tool_result') addMsg(ev.is_error ? 'tool error' : 'tool', ev.content);
        else if (ev.type === 'system') addMsg('system', ev.content);
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

    function send() {
      var text = inputEl.value.trim();
      if (!text || busy) return;
      addMsg('user', text);
      ws.send(JSON.stringify({ message: text }));
      inputEl.value = '';
      busy = true;
      sendBtn.disabled = true;
    }

    function checkProviders() {
      return Promise.all([
        fetch('/api/providers').then(function (r) { return r.json(); }),
        fetch('/api/agents').then(function (r) { return r.json(); })
      ])
        .then(function (results) {
          var providers = results[0];
          var agents = results[1];
          var msg = null;
          if (providers.length === 0 && agents.length === 0) {
            msg = 'Getting started: add a provider in Admin, then create an agent in Studio to start chatting.';
          } else if (providers.length === 0) {
            msg = 'No providers configured \u2014 add one in Admin to start chatting.';
          } else if (agents.length === 0) {
            msg = 'No agents configured \u2014 create one in Studio to start chatting.';
          }
          if (msg) {
            if (!bannerEl) {
              bannerEl = document.createElement('div');
              bannerEl.className = 'chat-no-providers';
              messagesEl.parentNode.insertBefore(bannerEl, messagesEl);
            }
            bannerEl.textContent = msg;
          } else {
            if (bannerEl) {
              bannerEl.parentNode.removeChild(bannerEl);
              bannerEl = null;
            }
          }
        })
        .catch(function () { /* best-effort */ });
    }

    function connect() {
      var proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(proto + '://' + location.host + '/ws');

      ws.onopen = function () {
        statusEl.textContent = 'connected';
        checkProviders().then(function () {
          return fetchAgents();
        }).then(function () {
          ws.send(JSON.stringify({ action: 'list_sessions' }));
        });
      };

      ws.onclose = function () {
        statusEl.textContent = 'disconnected';
        setTimeout(connect, 2000);
      };

      ws.onmessage = function (e) {
        var data = JSON.parse(e.data);

        if (data.type === 'session_list') {
          renderSessionList(data.sessions);
          if (data.sessions.length > 0 && !currentSessionId) {
            joinSession(data.sessions[0].id);
          } else if (!currentSessionId && !bannerEl) {
            // Only auto-create a session if setup is complete (no banner showing)
            var msg = { action: 'new_session' };
            if (agentSelect.value) msg.agent_name = agentSelect.value;
            ws.send(JSON.stringify(msg));
          }
          return;
        }

        if (data.type === 'session_joined') {
          currentSessionId = data.session_id;
          currentAgentName = data.agent_name;
          updateAgentBadge(data.agent_name);
          renderHistory(data.history);
          refreshSessionList();
          return;
        }

        if (data.type === 'session_deleted') {
          if (currentSessionId === data.session_id) {
            currentSessionId = null;
            messagesEl.innerHTML = '';
            var delMsg = { action: 'new_session' };
            if (agentSelect.value) delMsg.agent_name = agentSelect.value;
            ws.send(JSON.stringify(delMsg));
          }
          refreshSessionList();
          return;
        }

        if (data.type === 'user') {
          var cls = data.source === 'api' ? 'user api' : 'user';
          addMsg(cls, (data.source && data.source !== 'web' ? '[' + data.source + '] ' : '') + data.content);
        }
        else if (data.type === 'assistant') addMsg('assistant', data.content);
        else if (data.type === 'tool_call') addMsg('tool', '> ' + data.name + '(' + Object.entries(data.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')');
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
            addMsg('system', data.content);
            // Reset busy state if an error arrived (e.g. failed session creation)
            if (busy) {
              busy = false;
              sendBtn.disabled = false;
            }
          }
        }
        else if (data.type === 'usage') {
          updateTelemetry(data);
        }
        else if (data.type === 'done') {
          busy = false;
          sendBtn.disabled = false;
          refreshSessionList();
        }
      };
    }

    // Wire events
    inputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    sendBtn.addEventListener('click', send);
    newChatBtn.addEventListener('click', function () {
      if (bannerEl) return; // setup not complete
      var selected = agentSelect.value;
      var msg = { action: 'new_session' };
      if (selected) msg.agent_name = selected;
      ws.send(JSON.stringify(msg));
    });

    // Store references for activate
    this._connect = connect;
    this._ws = function () { return ws; };
    this._fetchAgents = fetchAgents;
    this._checkProviders = checkProviders;
  },

  activate: function () {
    if (!this._ws || !this._ws() || this._ws().readyState > 1) {
      this._connect();
    } else if (this._ws() && this._ws().readyState === WebSocket.OPEN) {
      this._fetchAgents();
      this._checkProviders();
    }
  },

  deactivate: function () {
    // Keep WS alive
  }
});
