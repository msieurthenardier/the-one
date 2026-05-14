App.registerArea({
  id: 'chat',
  label: 'Chat',
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

  init: function (content) {
    var ws = null;
    // Per-session in-flight tracker: a session is "busy" when its agent
    // is mid-turn. Was previously a single `busy` flag per WebSocket, but
    // that caused the input to stay disabled in a NEW conversation when
    // the user switched away from a still-running one (post-F4 surfacing).
    var inFlightSessions = Object.create(null);
    function isCurrentBusy() {
      return !!(currentSessionId && inFlightSessions[currentSessionId]);
    }
    var currentSessionId = null;
    var pendingJoinId = null;
    var sessions = [];
    var currentAgentName = null;
    var messagesEl, inputEl, sendBtn, sessionListEl, convoHeaderEl, composerEl, newSessionBtn;
    var setupIncomplete = false;
    var sessionBannerEl = null;
    var availableAgents = [];
    var setupState = { hasProviders: false, hasAgents: false };

    // Holograph layout: .chat-layout with .sessions-pane (left) + .convo-pane (right).
    // No sidebar — the sessions pane is part of content itself.
    content.innerHTML =
      '<div class="chat-layout">' +
        '<aside class="sessions-pane">' +
          '<div class="sessions-header">' +
            '<h3>Sessions</h3>' +
            '<button class="new-session-btn" type="button" aria-label="New session" data-testid="new-chat-btn">' +
              '<svg class="icn icn-sm" viewBox="0 0 12 12" aria-hidden="true">' +
                '<path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
              '</svg>' +
            '</button>' +
          '</div>' +
          '<div class="sessions-list" id="chat-sessions-list" role="listbox" aria-label="Chat sessions"></div>' +
        '</aside>' +
        '<div class="convo-pane">' +
          '<div class="convo-header" id="chat-convo-header"></div>' +
          '<div class="convo-stream" id="chat-convo-stream" role="log" aria-live="polite" aria-relevant="additions" aria-atomic="false"></div>' +
          '<div class="composer" id="chat-composer"></div>' +
        '</div>' +
      '</div>';

    sessionListEl = content.querySelector('.sessions-list');
    convoHeaderEl = content.querySelector('.convo-header');
    messagesEl = content.querySelector('.convo-stream');
    composerEl = content.querySelector('.composer');
    newSessionBtn = content.querySelector('.new-session-btn');

    // renderComposer — writes the composer-box HTML into composerEl and
    // (re-)wires the send button and Enter-key handler. Called on init and
    // whenever the active agent changes so the placeholder stays accurate.
    function renderComposer(agentName) {
      composerEl.innerHTML =
        '<div class="composer-box">' +
          '<textarea class="composer-input" rows="1" placeholder="Ask ' + (agentName || 'agent') + ' anything…" data-testid="chat-input" aria-label="Message"></textarea>' +
          '<div class="composer-controls">' +
            '<button class="btn btn-ghost" type="button" data-action="attach" aria-label="Attach file">' +
              '<svg class="icn icn-sm" viewBox="0 0 16 16" aria-hidden="true">' +
                '<path d="M10 4L5 9a2 2 0 002.8 2.8L13 6.6a3.5 3.5 0 00-4.9-4.9L3 6.6" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>' +
              '</svg>' +
              '<span>Attach</span>' +
            '</button>' +
            '<div class="right">' +
              '<span class="chip mono" id="chat-ctx-chip">0k ctx</span>' +
              '<button class="btn btn-primary" type="button" data-action="send" data-testid="chat-send-btn">' +
                'Send' +
                '<svg class="icn icn-sm" viewBox="0 0 12 12" aria-hidden="true">' +
                  '<path d="M2 6h8M6 2l4 4-4 4" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>' +
                '</svg>' +
              '</button>' +
            '</div>' +
          '</div>' +
        '</div>';
      inputEl = composerEl.querySelector('.composer-input');
      sendBtn = composerEl.querySelector('[data-action="send"]');
      var attachBtn = composerEl.querySelector('[data-action="attach"]');
      if (attachBtn) {
        attachBtn.addEventListener('click', function () { App.toast('Attachments coming soon.'); });
      }
      inputEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
      });
      sendBtn.addEventListener('click', send);
    }

    // renderConvoHeader — writes the convo-header content for an active session.
    // When session is null/undefined, renders an empty placeholder div.
    function renderConvoHeader(session) {
      if (!session) {
        convoHeaderEl.innerHTML = '<div></div>';
        return;
      }
      var title = (session.title || 'Untitled').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      var agentNameSafe = (session.agent_name || 'Agent').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      var modelSafe = (session.model || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      var initials = (session.agent_name || 'A').slice(0, 2).toUpperCase();
      convoHeaderEl.innerHTML =
        '<div><div class="convo-title">' + title + '</div></div>' +
        '<div class="convo-agent">' +
          '<div class="agent-avatar">' + initials + '</div>' +
          '<span>' + agentNameSafe + '</span>' +
          (modelSafe ? '<span class="chip mono">' + modelSafe + '</span>' : '') +
        '</div>' +
        '<div class="convo-actions">' +
          '<button class="btn btn-ghost" aria-label="Session settings" type="button">' +
            '<svg class="icn" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.6" fill="none"/></svg>' +
          '</button>' +
        '</div>';
    }

    // updateCtxChip — inline telemetry chip update (replaces the floating overlay).
    function updateCtxChip(data) {
      var chip = content.querySelector('#chat-ctx-chip');
      if (!chip) return;
      var ctxK = data.context_tokens >= 1000 ? (data.context_tokens / 1000).toFixed(1) + 'k' : String(data.context_tokens);
      chip.textContent = ctxK + ' ctx';
    }

    function resetCtxChip() {
      var chip = content.querySelector('#chat-ctx-chip');
      if (chip) chip.textContent = '0k ctx';
    }

    // Initial render: no active session.
    renderComposer(null);
    renderConvoHeader(null);

    // updateAgentBadge — re-renders the convo-header with the current agent.
    // Called on session_joined with the resolved session object (or synthetic
    // minimal object when only the agent name is known).
    function updateAgentBadge(name) {
      // If a full session object is available use renderConvoHeader; otherwise
      // update just the avatar initials via a minimal synthetic session shape.
      // (The full session_joined event provides the real data via renderConvoHeader.)
    }

    function addMsg(cls, text, attribution, opts) {
      // attribution arg is now ignored (Holograph embeds author/time in msg-body).
      // opts.agentName is used by renderMessage for the avatar initials.
      var msgOpts = opts || {};
      if (cls.indexOf('assistant') === 0 && !msgOpts.agentName) {
        msgOpts = { agentName: currentAgentName, ts: msgOpts.ts, renderMarkdown: msgOpts.renderMarkdown };
      }
      var el = App.chat.renderMessage(cls, text, msgOpts);
      if (el) messagesEl.appendChild(el);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function highlightActiveSession() {
      var items = sessionListEl.querySelectorAll('.session-card');
      for (var i = 0; i < items.length; i++) {
        var active = items[i].dataset.sessionId === currentSessionId;
        items[i].classList.toggle('active', active);
        items[i].setAttribute('aria-selected', active ? 'true' : 'false');
      }
    }

    function renderWelcome() {
      App.chat.renderWelcomeList(messagesEl, availableAgents, setupState, { onStart: startSessionWith });
    }

    function fetchAgents() {
      return fetch('/api/agents').then(function (r) { return r.json(); }).then(function (agents) {
        availableAgents = agents;
        if (welcomeVisible) renderWelcome();
      }).catch(function (err) {
        /* agents list is nice-to-have */
        console.warn('chat: fetchAgents failed', err);
      });
    }

    // welcomeVisible tracks whether the convo-stream is showing the welcome
    // empty-state (vs. a message history). This replaces the old welcomeEl.hidden flag.
    var welcomeVisible = false;

    function showWelcome() {
      welcomeVisible = true;
      renderConvoHeader(null);
      renderWelcome();
    }

    function showChrome() {
      welcomeVisible = false;
      // convo-pane is always visible; showChrome just means the welcome is gone.
      // The actual content was set by the session_joined handler.
    }

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
      messagesEl.setAttribute('aria-busy', 'true');
      messagesEl.innerHTML = '';
      var agentLabel = agentName || 'agent';
      for (var i = 0; i < history.length; i++) {
        var ev = history[i];
        // Pass ts explicitly (server-side broadcast events carry it; DB-restored
        // events do not). When ts is undefined, addMsg's default is omitted so
        // historical messages without a stored timestamp render unsuffixed.
        var histOpts = { ts: ev.ts || null };
        if (ev.type === 'user') {
          var cls = ev.source === 'api' ? 'user api' : 'user';
          addMsg(cls, (ev.source && ev.source !== 'web' && ev.source !== 'restored' ? '[' + ev.source + '] ' : '') + ev.content, 'You', histOpts);
        }
        else if (ev.type === 'assistant') addMsg('assistant', ev.content, agentLabel, histOpts);
        else if (ev.type === 'tool_call') {
          var hTc = App.chat.renderToolCall(ev.name, ev.arguments, 'done');
          messagesEl.appendChild(hTc);
        }
        else if (ev.type === 'tool_result') {
          var hTr = App.chat.renderToolResult(ev.content, ev.is_error);
          messagesEl.appendChild(hTr);
        }
        // Filter transient model-loading pings — live UI hints, not history.
        else if (ev.type === 'system' && ev.content !== 'Loading model...' && ev.content !== 'Model loaded.') {
          addMsg('system', ev.content, null, histOpts);
        }
      }
      messagesEl.removeAttribute('aria-busy');
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

    // Render-pacing queue: API chunks enqueue here; a setInterval loop
    // drains characters into the bubble's pending text node (always the
    // bubble's lastChild) at ~60 chars/sec. Adaptive: long queue drains
    // faster so we don't lag behind a fast API. On finalize, the queue
    // drains synchronously before the markdown swap.
    var pendingChars = '';
    var pacingTimer = null;

    // Find the last "safe" position for incremental markdown rendering:
    // the index AFTER a blank-line block boundary (`\n\n`) that is NOT
    // inside an unclosed code fence. Returns 0 if no safe boundary.
    // A real blank line requires two adjacent newlines, which appears in
    // text.split('\n') as a sequence ["...non-empty", "", "..."] — so we
    // require lines[i+1]==='' AND i+2<lines.length (the trailing "" from
    // a single \n at end-of-input has no element after it, so we skip it).
    function findSafeRenderBoundary(text) {
      var lines = text.split('\n');
      var inFence = false;
      var lastSafe = 0;
      var pos = 0;
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (line.replace(/^\s+/, '').indexOf('```') === 0) inFence = !inFence;
        pos += line.length + 1;
        if (!inFence && lines[i + 1] === '' && i + 2 < lines.length) {
          lastSafe = pos + 1;
        }
      }
      return lastSafe;
    }

    // After paced text is appended to the pending tail, check whether a
    // new block boundary became visible. If yes, render the committed
    // prefix as markdown and shrink the pending tail. Keeps the bubble's
    // lastChild as a (possibly-empty) text node for subsequent appends.
    function commitSafeBoundary() {
      if (!currentStreamingMsg) return;
      var tail = currentStreamingMsg.lastChild;
      if (!tail || tail.nodeType !== 3) return;
      var boundary = findSafeRenderBoundary(tail.nodeValue || '');
      if (boundary <= 0) return;
      var toRender = tail.nodeValue.slice(0, boundary);
      var rest = tail.nodeValue.slice(boundary);
      var fragment = App.markdown.render(toRender);
      if (!fragment.firstChild) return;
      currentStreamingMsg.insertBefore(fragment, tail);
      tail.nodeValue = rest;
    }

    function pacingTick() {
      if (!pendingChars.length || !currentStreamingMsg) return;
      var tail = currentStreamingMsg.lastChild;
      if (!tail || tail.nodeType !== 3) return;
      var n = Math.max(1, Math.ceil(pendingChars.length / 30));
      var slice = pendingChars.slice(0, n);
      pendingChars = pendingChars.slice(n);
      tail.nodeValue += slice;
      commitSafeBoundary();
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function startPacing() {
      if (pacingTimer) return;
      pacingTimer = setInterval(pacingTick, 16);
    }

    function stopPacing() {
      if (pacingTimer) { clearInterval(pacingTimer); pacingTimer = null; }
    }

    function drainPacing() {
      if (pendingChars.length && currentStreamingMsg) {
        var tail = currentStreamingMsg.lastChild;
        if (tail && tail.nodeType === 3) tail.nodeValue += pendingChars;
      }
      pendingChars = '';
      stopPacing();
    }

    // Leg 05: swap the streaming bubble's pending tail for its
    // markdown-rendered fragment. Already-committed blocks (from
    // commitSafeBoundary) stay in place. Idempotent — no-op if no
    // bubble is active. Clears the closure pointer via `void 0`.
    function finalizeStreamingBubble() {
      drainPacing();
      var bubble = currentStreamingMsg;
      if (!bubble) return;
      currentStreamingMsg = void 0;
      var tail = bubble.lastChild;
      var tailText = '';
      if (tail && tail.nodeType === 3) {
        tailText = tail.nodeValue || '';
        bubble.removeChild(tail);
      }
      if (tailText) bubble.appendChild(App.markdown.render(tailText));
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

    // F5 L5: Login-required inline button helpers.
    //
    // Idempotent: clearLoginRequiredButton removes any stale buttons for the
    // same source_id BEFORE renderLoginRequiredButton appends a new one. This
    // keeps the L3 reconnect-snapshot replay from creating duplicate buttons
    // (the cached auth_required event is re-broadcast on every WS reconnect
    // when the agent has a pending pause).
    function clearLoginRequiredButton(data) {
      var sid = data && data.source_id ? data.source_id : null;
      var sel = sid
        ? '.login-required-btn[data-source-id="' + cssEscape(sid) + '"]'
        : '.login-required-btn';
      var existing = messagesEl.querySelectorAll(sel);
      for (var i = 0; i < existing.length; i++) {
        if (existing[i].parentNode) existing[i].parentNode.removeChild(existing[i]);
      }
    }

    function cssEscape(s) {
      // Minimal subset of CSS.escape — escape quotes + backslashes so the
      // attribute selector parses cleanly. source_ids are always slugs (no
      // whitespace) per L0/L1 validation, so this is sufficient.
      return String(s).replace(/(["\\])/g, '\\$1');
    }

    // Track per-source consent popups so the WS-delivered consent_url
    // (which arrives AFTER /api/oauth/start) can navigate the popup that
    // was opened during the user's click gesture. Opening the popup at
    // click time (with about:blank as placeholder) preserves the
    // user-gesture chain — browsers will block window.open() called
    // later from inside a WS event handler.
    var oauthPopups = Object.create(null);
    // Preserve source_name across re-renders. The SECOND auth_required
    // event (broadcast by the SDK's redirect_handler) carries the real
    // consent_url but historically lacked source_name; the backend now
    // includes it, but we keep this map as a defensive cache so a stale
    // event still renders the friendly name.
    var sourceNames = Object.create(null);

    function openConsentPopup(url, sourceId) {
      var popupW = 600;
      var popupH = 700;
      var parentX = window.screenX !== undefined ? window.screenX : window.screenLeft;
      var parentY = window.screenY !== undefined ? window.screenY : window.screenTop;
      var parentW = window.outerWidth || window.innerWidth || screen.width;
      var parentH = window.outerHeight || window.innerHeight || screen.height;
      var popupLeft = parentX + Math.max(0, (parentW - popupW) / 2);
      var popupTop = parentY + Math.max(0, (parentH - popupH) / 2);
      var features = (
        'width=' + popupW + ',height=' + popupH +
        ',left=' + Math.round(popupLeft) +
        ',top=' + Math.round(popupTop)
      );
      var name = 'mcp-oauth-consent-' + (sourceId || 'unknown');
      return window.open(url || 'about:blank', name, features);
    }

    function startLoginFlow(data) {
      var sourceId = data.source_id;
      // Open popup synchronously during the click gesture. If consent_url
      // is already known (idempotent re-emission), navigate the popup
      // immediately; otherwise open with about:blank and POST
      // /api/oauth/start, then navigate when the WS event arrives.
      var popup = openConsentPopup(data.consent_url || 'about:blank', sourceId);
      if (!popup) {
        addMsg('system', 'Popup blocked — please allow popups for this site and retry.');
        return;
      }
      oauthPopups[sourceId] = popup;
      if (data.consent_url) return;
      fetch('/api/oauth/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_id: sourceId,
          chat_session_id: currentSessionId,
          tool_call_id: data.tool_call_id,
          resource_metadata_url: data.resource_metadata_url,
        }),
      }).then(function (r) {
        if (r.ok) return;
        return r.json().then(function (err) {
          var detail = (err && err.detail) || 'OAuth start failed';
          addMsg('system', detail);
          closeOauthPopup(sourceId);
        });
      }).catch(function (e) {
        addMsg('system', 'Network error: ' + (e && e.message ? e.message : e));
        closeOauthPopup(sourceId);
      });
    }

    function closeOauthPopup(sourceId) {
      var popup = oauthPopups[sourceId];
      if (!popup) return;
      try { if (!popup.closed) popup.close(); } catch (e) { /* ignore */ }
      delete oauthPopups[sourceId];
    }

    function renderLoginRequiredButton(data) {
      // Drop any prior button for this source first (reconnect idempotency).
      clearLoginRequiredButton(data);
      if (data.source_id && data.source_name) {
        sourceNames[data.source_id] = data.source_name;
      }
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-primary login-required-btn'; // L6.3: Holograph btn vocabulary
      btn.dataset.sourceId = data.source_id || '';
      btn.dataset.toolCallId = data.tool_call_id || '';
      btn.dataset.resourceMetadataUrl = data.resource_metadata_url || '';
      if (data.consent_url) btn.dataset.consentUrl = data.consent_url;
      var label = data.source_name
        || (data.source_id && sourceNames[data.source_id])
        || data.source_id
        || '<unknown>';
      btn.textContent = 'Login required for ' + label;
      btn.addEventListener('click', function () {
        startLoginFlow(data);
      });
      messagesEl.appendChild(btn);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function renderResumingPlaceholder(data) {
      // Lightweight system message indicating the resumed tool call is
      // re-running. The eventual tool_result event renders normally; this
      // placeholder is purely cosmetic so the chat doesn't go silent
      // between auth_resolved and the resumed tool_result arrival.
      addMsg('system', 'Resuming…');
    }

    function send() {
      var text = inputEl.value.trim();
      if (!text || isCurrentBusy()) return;
      addMsg('user', text, 'You');
      ws.send(JSON.stringify({ message: text }));
      inputEl.value = '';
      if (currentSessionId) inFlightSessions[currentSessionId] = true;
      sendBtn.disabled = true;
      showThinking();
    }

    function checkSetupState() {
      return Promise.all([
        fetch('/api/providers').then(function (r) { return r.ok ? r.json() : []; }),
        fetch('/api/agents').then(function (r) { return r.ok ? r.json() : []; })
      ])
        .then(function (results) {
          setupState.hasProviders = results[0].length > 0;
          setupState.hasAgents = results[1].length > 0;
          setupIncomplete = !setupState.hasProviders || !setupState.hasAgents;
          // Refresh the welcome canvas so guidance tracks setupState changes.
          if (!currentSessionId && welcomeVisible) renderWelcome();
          // Setup-incomplete with no session → welcome canvas immediately.
          if (setupIncomplete && !currentSessionId) showWelcome();
        })
        .catch(function (err) {
          /* best-effort */
          console.warn('chat: checkSetupState failed', err);
        });
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
          composerEl.parentNode.insertBefore(sessionBannerEl, composerEl);
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
        // Server will run `agent.step` only AFTER the load finishes — until
        // then, suppress the "thinking" indicator we optimistically showed
        // on send so the operator sees a single, accurate state.
        hideThinking();
        // Render a toolcall-style "Loading model" indicator with a live dot.
        var loadEl = document.createElement('div');
        loadEl.className = 'toolcall open system-model-loading';
        loadEl.innerHTML =
          '<div class="toolcall-header">' +
            '<span class="toolcall-name">Loading model</span>' +
            '<span class="toolcall-status"><span class="dot live"></span></span>' +
          '</div>';
        messagesEl.appendChild(loadEl);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      } else if (data.content === 'Model loaded.') {
        var loadingMsg = messagesEl.querySelector('.system-model-loading');
        if (loadingMsg) {
          // Swap the live dot for an idle dot + update label.
          var nameEl = loadingMsg.querySelector('.toolcall-name');
          if (nameEl) nameEl.textContent = 'Model loaded.';
          var dotEl = loadingMsg.querySelector('.dot');
          if (dotEl) { dotEl.classList.remove('live'); dotEl.classList.add('idle'); }
          loadingMsg.classList.remove('system-model-loading');
        } else { addMsg('system', data.content); }
        // Restore the "thinking" state — the agent step is about to run
        // and we still owe the user a response indicator until the first
        // chunk arrives.
        if (currentSessionId && inFlightSessions[currentSessionId]) {
          showThinking();
        }
      } else {
        hideThinking();
        addMsg('system', data.content);
        if (currentSessionId && inFlightSessions[currentSessionId]) {
          delete inFlightSessions[currentSessionId];
          if (!sessionBannerEl) sendBtn.disabled = false;
        }
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
        // Disconnect drops every in-flight broadcast — clear the whole map.
        for (var k in inFlightSessions) delete inFlightSessions[k];
        if (!sessionBannerEl) sendBtn.disabled = false;
        setTimeout(connect, 2000);
      };

      ws.onerror = function (e) {
        console.error('chat ws: error', e);
      };

      ws.onmessage = function (e) {
        var data;
        try {
          data = JSON.parse(e.data);
        } catch (err) {
          console.error('chat ws: malformed frame', err, String(e.data).slice(0, 200));
          return;
        }

        if (data.type === 'session_list') {
          sessions = data.sessions;
          App.chat.renderSessionList(sessionListEl, sessions, currentSessionId, {
            onJoin: joinSession,
            onDelete: function (id, btn) {
              // Two-step confirm via the canonical App.confirmDelete helper
              // (F5 leg 02). WS delete is fire-and-forget so revertFn is
              // unused here — server-side broadcast updates the list.
              var item = btn.closest('.session-card');
              if (!item) return;
              App.confirmDelete(item, function (itemEl, revertFn) {
                ws.send(JSON.stringify({ action: 'delete_session', session_id: id }));
              });
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
          // Re-render convo header with session details and refresh composer placeholder.
          renderConvoHeader({ title: data.title || ('Chat with ' + (data.agent_name || 'agent')), agent_name: data.agent_name, model: data.model });
          renderComposer(data.agent_name);
          hideThinking();
          resetCtxChip();
          renderHistory(data.history, data.agent_name);
          setSessionHealth(data.status || 'ok');
          // Sync per-session busy state to server ground truth (the
          // session's `processing_lock.locked()` boolean). Without this,
          // switching away from an in-flight session and back leaves
          // the prior `busy` flag stale — either stuck-disabled (turn
          // finished while away) or stuck-enabled (turn still running).
          if (data.is_processing) {
            inFlightSessions[currentSessionId] = true;
            if (!sessionBannerEl) sendBtn.disabled = true;
            showThinking();
          } else {
            delete inFlightSessions[currentSessionId];
            if (!sessionBannerEl) sendBtn.disabled = false;
          }
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
          // First chunk: clear thinking, mint a fresh agent .msg-row.
          // currentStreamingMsg now points at the .msg-text div inside
          // the row (not the row itself), so the pacing ticker can append
          // text-node children to the correct element.
          hideThinking();
          if (!currentStreamingMsg) {
            var streamResult = App.chat.renderAgentMessage('', currentAgentName || 'agent', new Date().toISOString(), { renderMarkdown: false });
            messagesEl.appendChild(streamResult.row);
            // streamResult.msgText is the .msg-text div; seed with empty text node.
            if (!streamResult.msgText.firstChild) {
              streamResult.msgText.appendChild(document.createTextNode(''));
            }
            currentStreamingMsg = streamResult.msgText;
            startPacing();
          }
          pendingChars += data.content;
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
          var tcEl = App.chat.renderToolCall(data.name, data.arguments, 'running');
          messagesEl.appendChild(tcEl);
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
        else if (data.type === 'tool_result') {
          // Iteration boundary — finalize the current streaming bubble.
          finalizeStreamingBubble();
          var trEl = App.chat.renderToolResult(data.content, data.is_error);
          messagesEl.appendChild(trEl);
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
        else if (data.type === 'system') handleSystem(data);
        else if (data.type === 'usage') updateCtxChip(data);
        else if (data.type === 'auth_required') {
          // F5 L5: lazy-path → render an inline "Login required for <source>"
          // button in the chat history. First emission has consent_url=null;
          // a second emission (post /api/oauth/start) carries the real
          // consent_url. When the second event arrives AND we have a popup
          // opened from the user's click gesture, navigate it to the
          // consent_url directly — preserves the gesture chain so the
          // browser doesn't block the navigation or convert it to a tab.
          hideThinking();
          finalizeStreamingBubble();
          if (data.consent_url && oauthPopups[data.source_id]) {
            var p = oauthPopups[data.source_id];
            try {
              if (!p.closed) {
                p.location.href = data.consent_url;
                p.focus();
              }
            } catch (e) { /* cross-origin or closed; ignore */ }
          }
          renderLoginRequiredButton(data);
        }
        else if (data.type === 'auth_resolved') {
          // F5 L5: auth completed. Clear inline button, close popup,
          // surface a "Resuming…" placeholder until the resumed
          // tool_result arrives. The callback page's own
          // window.close() usually fires first; this is a fallback.
          clearLoginRequiredButton(data);
          closeOauthPopup(data.source_id);
          renderResumingPlaceholder(data);
        }
        else if (data.type === 'auth_failed') {
          // F5 L5: surface the OAuth-flow failure as a system error
          // notice; close any open popup for this source.
          closeOauthPopup(data.source_id);
          var failMsg = 'OAuth failed: ' + (data.description || data.error || 'unknown error');
          addMsg('system', failMsg);
        }
        else if (data.type === 'done') {
          hideThinking();
          // End of agent step — finalize so the streaming bubble swaps
          // its accumulated text for the markdown-rendered fragment, and
          // the next user message starts a fresh streaming round.
          finalizeStreamingBubble();
          if (currentSessionId) delete inFlightSessions[currentSessionId];
          if (!sessionBannerEl) sendBtn.disabled = false;
          refreshSessionList();
        }
      };
    }

    // Wire events — input/sendBtn are wired inside renderComposer() because
    // the composer is re-rendered on agent change. newSessionBtn is static.
    newSessionBtn.addEventListener('click', function () {
      startSessionWith(currentAgentName || null);
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
