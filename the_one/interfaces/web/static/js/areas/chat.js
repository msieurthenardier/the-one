App.registerArea({
  id: 'chat',
  label: 'Chat',
  icon: '\uD83D\uDCAC',
  order: 10,

  init: function (sidebar, content) {
    var ws = null;
    var busy = false;
    var currentSessionId = null;
    var messagesEl, inputEl, sendBtn, statusEl, sessionListEl;

    // Build sidebar DOM
    sidebar.innerHTML =
      '<div id="sidebar-header">' +
        '<span class="title">the-one</span>' +
        '<button class="new-chat">+ new</button>' +
      '</div>' +
      '<div class="session-list"></div>';

    sessionListEl = sidebar.querySelector('.session-list');
    var newChatBtn = sidebar.querySelector('.new-chat');

    // Build content DOM
    content.innerHTML =
      '<div class="header">' +
        '<span class="status">connecting...</span>' +
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

    function renderSessionList(sessions) {
      sessionListEl.innerHTML = '';
      var groups = {};
      for (var i = 0; i < sessions.length; i++) {
        var src = sessions[i].source || 'web';
        if (!groups[src]) groups[src] = [];
        groups[src].push(sessions[i]);
      }
      var keys = Object.keys(groups).sort(function (a, b) {
        if (a === 'web') return -1;
        if (b === 'web') return 1;
        return a.localeCompare(b);
      });

      for (var k = 0; k < keys.length; k++) {
        var srcKey = keys[k];
        var label = document.createElement('div');
        label.className = 'session-group';
        label.textContent = srcKey;
        sessionListEl.appendChild(label);

        var list = groups[srcKey];
        for (var j = 0; j < list.length; j++) {
          (function (s) {
            var el = document.createElement('div');
            el.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
            el.dataset.id = s.id;

            var titleSpan = document.createElement('span');
            titleSpan.textContent = s.title;
            titleSpan.style.overflow = 'hidden';
            titleSpan.style.textOverflow = 'ellipsis';
            el.appendChild(titleSpan);

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
          })(list[j]);
        }
      }
    }

    function renderHistory(history) {
      messagesEl.innerHTML = '';
      for (var i = 0; i < history.length; i++) {
        var ev = history[i];
        if (ev.type === 'user') {
          var cls = ev.source === 'api' ? 'user api' : 'user';
          addMsg(cls, (ev.source && ev.source !== 'web' ? '[' + ev.source + '] ' : '') + ev.content);
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

    function connect() {
      var proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(proto + '://' + location.host + '/ws');

      ws.onopen = function () {
        statusEl.textContent = 'connected';
        ws.send(JSON.stringify({ action: 'list_sessions' }));
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
          } else if (!currentSessionId) {
            ws.send(JSON.stringify({ action: 'new_session' }));
          }
          return;
        }

        if (data.type === 'session_joined') {
          currentSessionId = data.session_id;
          renderHistory(data.history);
          refreshSessionList();
          return;
        }

        if (data.type === 'session_deleted') {
          if (currentSessionId === data.session_id) {
            currentSessionId = null;
            messagesEl.innerHTML = '';
            ws.send(JSON.stringify({ action: 'new_session' }));
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
        else if (data.type === 'system') addMsg('system', data.content);
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
      ws.send(JSON.stringify({ action: 'new_session' }));
    });

    // Store connect for activate
    this._connect = connect;
    this._ws = function () { return ws; };
  },

  activate: function () {
    if (!this._ws || !this._ws() || this._ws().readyState > 1) {
      this._connect();
    }
  },

  deactivate: function () {
    // Keep WS alive
  }
});
