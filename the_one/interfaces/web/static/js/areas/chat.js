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

  init: function (sidebar, content) {
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
    // Queued new-session intent: set by startSessionWith when the WS is not
    // yet OPEN (e.g. during a brief reconnect cycle). Drained by the
    // session_list handler once the WS comes back up — takes priority over
    // the normal auto-join of the most-recent session.
    var pendingStart = null; // { agentName: string|null }
    var sessions = [];
    var pendingApprovals = []; // M11 F17 L9 (Leg E) — left-panel pending section
    var currentAgentName = null;
    var messagesEl, inputEl, sendBtn, sessionListEl, agentSelect, agentBadgeEl;
    var setupIncomplete = false;
    var sessionBannerEl = null;
    var availableAgents = [];
    var setupState = { hasProviders: false, hasAgents: false };

    // Sidebar headers use the app's `// SECTION` idiom (.section-title) so the
    // chat sidebar reads consistently with admin/studio. The label still owns
    // a `for=` association with the agent select for screen-reader form
    // semantics; .section-title controls the visual treatment.
    sidebar.innerHTML =
      '<div id="sidebar-header">' +
        '<label class="section-title" for="chat-agent-select">Select Agent</label>' +
        '<div class="sidebar-actions">' +
          '<select id="chat-agent-select" class="agent-select" data-testid="agent-select">' +
            '<option value="" disabled selected>Select agent…</option>' +
          '</select>' +
        '</div>' +
      '</div>' +
      '<nav class="session-list" aria-label="Chat sessions"></nav>';

    sessionListEl = sidebar.querySelector('.session-list');
    agentSelect = sidebar.querySelector('.agent-select');

    // Telemetry overlay is constructed via App.chat.renderTelemetry() and
    // inserted between .messages and .input-area below.
    content.innerHTML =
      '<div class="chat-welcome" data-testid="chat-welcome" hidden>' +
        '<div class="chat-welcome-inner">' +
          '<img class="chat-welcome-mascot" src="/static/brand/gleepglorp_icon.png" alt="" aria-hidden="true" loading="eager" data-testid="chat-welcome-mascot">' +
          '<h2 class="chat-welcome-greeting">Hello.</h2>' +
          '<p class="chat-welcome-prompt">Which agent would you like to chat with?</p>' +
          '<div class="chat-welcome-list" role="listbox" aria-label="Available agents"></div>' +
        '</div></div>' +
      '<div class="chat-chrome">' +
        // New-chat button sits inline next to the agent badge — icon-only at
        // rest, expands into the full pill on hover/focus. Pure-CSS
        // hover-expand via max-width transition; no JS state needed.
        '<div class="header"><h2 class="session-agent-badge"></h2>' +
          '<button class="new-chat-header" type="button" data-testid="new-chat-btn" aria-label="Start a new conversation with this agent">' +
            App.icon('square-pen') + '<span>New Chat</span></button></div>' +
        '<div class="messages" role="log" aria-live="polite" aria-relevant="additions" aria-atomic="false"></div>' +
        '<div class="input-area">' +
          '<input data-testid="chat-input" placeholder="Type a message..." autocomplete="off" enterkeyhint="send" aria-label="Message" />' +
          '<button class="btn-filled-primary" data-testid="chat-send-btn" aria-keyshortcuts="Enter">Send</button></div>' +
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

    // M11 F13 L5: routing-audit panel — collapsible inspector for
    // session_metadata["routing"] entries. Mounts between .messages and
    // .input-area so it shares the chat-chrome flexbox column without
    // overlapping the message list scroll region. Populated in the
    // session_joined handler below from data.session_metadata.
    var routingAuditPanelEl = App.chat.routingAuditPanel.create();
    chromeEl.insertBefore(routingAuditPanelEl, chromeEl.querySelector('.input-area'));

    function updateAgentBadge(name) { agentBadgeEl.textContent = name || 'default'; }

    // M08 F6 L06 HAT fix: smart-scroll. Only auto-scroll to the bottom when
    // the user is already near it; if they've scrolled up to read history,
    // leave them where they are so an incoming chunk/message doesn't yank
    // them back down. Threshold is generous enough to absorb a single new
    // message bubble's height (typical ~40-80px) so a user who WAS at the
    // bottom stays pinned after an event.
    var SCROLL_PIN_THRESHOLD = 80;
    function scrollToBottomIfPinned() {
      var dist = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
      if (dist <= SCROLL_PIN_THRESHOLD) {
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }

    function addMsg(cls, text, attribution, opts) {
      App.perf.mark('addMsg:start');
      opts = opts || {};
      messagesEl.appendChild(App.chat.renderMessage(cls, text, opts));
      if (attribution) {
        // M11 F06 L04: side inferred from opts.peerName truthiness.
        // peer-attributed user bubbles align left ('from-peer'); operator-typed
        // user bubbles stay right ('from-you'); non-user bubbles ('assistant',
        // 'tool', 'system') align left ('from-agent') as before.
        var side = opts.peerName
          ? 'from-peer'
          : (cls.indexOf('user') === 0 ? 'from-you' : 'from-agent');
        var ts = Object.prototype.hasOwnProperty.call(opts, 'ts') ? opts.ts : new Date().toISOString();
        messagesEl.appendChild(App.chat.renderAttribution(side, attribution, ts));
      }
      scrollToBottomIfPinned();
      App.perf.mark('addMsg:end');
      App.perf.measure('addMsg', 'addMsg:start', 'addMsg:end');
    }

    function highlightActiveSession() {
      var items = sessionListEl.querySelectorAll('.session-item');
      for (var i = 0; i < items.length; i++) {
        var active = items[i].dataset.id === currentSessionId;
        items[i].classList.toggle('active', active);
        if (active) {
          items[i].setAttribute('aria-current', 'page');
        } else {
          items[i].removeAttribute('aria-current');
        }
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
    // Pattern: roving-tabindex with arrow keys. See section-nav.js:71-91
    // for the canonical implementation. Toggles aria-selected alongside
    // tabindex so the listbox semantic stays accurate (WCAG 4.1.2).
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
      for (var j = 0; j < opts.length; j++) {
        opts[j].setAttribute('tabindex', j === next ? '0' : '-1');
        opts[j].setAttribute('aria-selected', j === next ? 'true' : 'false');
      }
      opts[next].focus();
    });

    function startSessionWith(agentName) {
      if (setupIncomplete) return;
      // Record intent before sending so the WS reconnect path (session_list
      // handler) can honour it if the WS drops between the send and the
      // server's session_joined response. Cleared in session_joined handler.
      pendingStart = { agentName: agentName || null };
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        // WS is in a reconnect cycle — intent is queued; session_list handler
        // will drain it once the connection is restored (preempting auto-join).
        return;
      }
      currentSessionId = null;
      // M11 F9 L4: reset pending-approval dedup on new-chat creation.
      // renderHistory does NOT run for the new-session path, so the
      // renderHistory-side reset alone would not cover it.
      seenApprovalIds = Object.create(null);
      if (window.App && window.App.router) App.router.replaceSub(null);
      var msg = { action: 'new_session' };
      if (agentName) msg.agent_name = agentName;
      ws.send(JSON.stringify(msg));
    }

    function renderHistory(history, agentName) {
      messagesEl.setAttribute('aria-busy', 'true');
      messagesEl.innerHTML = '';
      // L03: reset the trace-shell bucket on replay so the DOM-rebuild
      // starts fresh; getOrCreateTrace will append shells to the freshly
      // emptied .messages container.
      traceShells = Object.create(null);
      // M11 F9 L4: reset pending-approval dedup on replay. Each
      // session_joined event re-emits the historical pending-approval
      // events; the dedup is scoped to the active session, not lifetime.
      seenApprovalIds = Object.create(null);
      var agentLabel = agentName || 'agent';
      for (var i = 0; i < history.length; i++) {
        var ev = history[i];
        // Pass ts explicitly (server-side broadcast events carry it; DB-restored
        // events do not). When ts is undefined, addMsg's default is omitted so
        // historical messages without a stored timestamp render unsuffixed.
        // M10 F05 L05: forward ev.visibility so operator-only bubbles
        // gain the visual marker on replay. Codec emits the key only when
        // non-None (the_one/db/codec.py:154); undefined falls through to
        // the byte-identical path inside renderMessage.
        // M11 F06 L04: forward ev.peer_name onto histOpts.peerName so peer-
        // attributed user bubbles render with msg-from-peer (left-aligned)
        // and a peer-name attribution label. Codec emits peer_name only when
        // non-None (L1+L2 contract); undefined here is falsy → defaults to
        // operator-typed 'You'/'from-you' rendering.
        var histOpts = { ts: ev.ts || null, visibility: ev.visibility, peerName: ev.peer_name };
        if (ev.type === 'user') {
          var cls = ev.source === 'api' ? 'user api' : 'user';
          var attribution = ev.peer_name || 'You';
          addMsg(cls, (ev.source && ev.source !== 'web' && ev.source !== 'restored' ? '[' + ev.source + '] ' : '') + ev.content, attribution, histOpts);
        }
        else if (ev.type === 'assistant') addMsg('assistant', ev.content, agentLabel, histOpts);
        else if (ev.type === 'tool_call') {
          // L03: bucket tool_call events under their parent_message_id's
          // trace shell; fall back to a standalone bubble for legacy/null.
          var argsText = '> ' + ev.name + '(' + Object.entries(ev.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')';
          var trace = getOrCreateTrace(ev.parent_message_id);
          var msg = buildToolMsg(argsText, false, ev.tool_call_id, { visibility: ev.visibility });
          if (trace) App.chat.appendToTrace(trace, msg);
          else messagesEl.appendChild(msg);
        }
        else if (ev.type === 'tool_result') {
          // L03: same bucketing for tool_result events.
          var trace2 = getOrCreateTrace(ev.parent_message_id);
          var msg2 = buildToolMsg(ev.content, ev.is_error, ev.tool_call_id, { visibility: ev.visibility });
          if (trace2) App.chat.appendToTrace(trace2, msg2);
          else messagesEl.appendChild(msg2);
        }
        // Filter transient model-loading pings — live UI hints, not history.
        else if (ev.type === 'system' && ev.content !== 'Loading model...' && ev.content !== 'Model loaded.') {
          addMsg('system', ev.content, null, histOpts);
        }
        // M11 F9 L4: pending-approval banner on replay path.
        else if (ev.type === 'pending-approval') {
          if (!seenApprovalIds[ev.approval_id]) {
            seenApprovalIds[ev.approval_id] = true;
            var pendingBanner = App.chat.renderPendingApproval(ev, {
              onApprove: onApproveClick,
              onDismiss: onDismissClick,
            });
            messagesEl.appendChild(pendingBanner);
          }
        }
      }
      messagesEl.removeAttribute('aria-busy');
    }

    // M11 F9 L4: pending-approval click handlers. Closures over addMsg so
    // the banner module itself stays scope-clean (per Sub-step D: the
    // banner IIFE must not reach for chat.js-local symbols). Optimistic
    // update (apply 'acting' class, hide buttons via CSS) then POST; on
    // 200 swap to the new status badge; on non-200 revert and surface a
    // system error.
    function onApproveClick(approvalId, connectorId, bannerEl) {
      onApprovalAction('approve', approvalId, connectorId, bannerEl);
    }

    function onDismissClick(approvalId, connectorId, bannerEl) {
      onApprovalAction('dismiss', approvalId, connectorId, bannerEl);
    }

    function onApprovalAction(action, approvalId, connectorId, bannerEl) {
      // Optimistic: dim the banner and disable click-through while the
      // request is in flight. CSS rule `.msg-pending-approval-acting`
      // applies `pointer-events: none` and `opacity: 0.6`.
      bannerEl.classList.add('msg-pending-approval-acting');
      var url = '/api/connectors/' + encodeURIComponent(connectorId) +
        '/peer-approvals/' + encodeURIComponent(approvalId) + '/' + action;
      var verb = action === 'approve' ? 'Approve' : 'Dismiss';
      fetch(url, { method: 'POST' })
        .then(function (resp) {
          if (resp.ok) {
            return resp.json().then(function (updated) {
              App.chat.applyApprovalStatus(bannerEl, updated.status);
            });
          }
          bannerEl.classList.remove('msg-pending-approval-acting');
          return resp.text().then(function (body) {
            var msg = verb + ' failed: HTTP ' + resp.status;
            if (body) msg += ' — ' + body.slice(0, 200);
            addMsg('system', msg);
          });
        })
        .catch(function (e) {
          bannerEl.classList.remove('msg-pending-approval-acting');
          addMsg('system', verb + ' failed: ' + (e && e.message ? e.message : e));
        });
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
    // M10 F05 L05: visibility for the streaming bubble. Captured from the
    // FIRST ``assistant_chunk`` of a turn (``data.visibility`` if present)
    // and applied at placeholder construction so the class+label land
    // before chunk accumulation. Today's live broadcast doesn't carry
    // ``visibility`` on ``assistant_chunk`` (known limitation: storage-edge
    // shim runs AFTER the agent step; broadcasts fire WITHIN it) — value
    // stays null and the bubble is unmarked until page refresh, at which
    // point the codec replay carries the tag. Reset alongside
    // ``currentStreamingMsg`` at the call sites of ``finalizeStreamingBubble``
    // to preserve that function's no-signature-change contract.
    var currentStreamingVisibility = null;

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
      scrollToBottomIfPinned();
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
      scrollToBottomIfPinned();
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
        var btn = existing[i];
        // L05: prefer removing the wrapper when present (post-L05 DOM);
        // fall back to the bare button (legacy / pre-L05 / test-synthesized).
        var group = btn.closest('.login-required-group');
        var toRemove = group || btn;
        var parent = toRemove.parentNode;
        if (parent) parent.removeChild(toRemove);
        // L03: if the removal left an empty trace-body, also drop the
        // enclosing trace shell so an empty chrome doesn't linger.
        // (Unchanged from pre-L05 — the wrapper sits inside .trace-body
        // exactly like the bare button did, so `parent` is still the
        // .trace-body in the trace-mount path.)
        if (parent && parent.classList && parent.classList.contains('trace-body') && parent.children.length === 0) {
          var shell = parent.closest('.trace-shell');
          if (shell && shell.parentNode) {
            var key = shell.dataset.parentMsgId;
            shell.parentNode.removeChild(shell);
            if (key) delete traceShells[key];
          }
        }
      }
    }

    function cssEscape(s) {
      // Minimal subset of CSS.escape — escape quotes + backslashes so the
      // attribute selector parses cleanly. source_ids are always slugs (no
      // whitespace) per L0/L1 validation, so this is sufficient.
      return String(s).replace(/(["\\])/g, '\\$1');
    }

    // L03: bucket of trace shells keyed by parent_message_id.
    // On first tool event for a parent, create the shell and append to
    // .messages after the assistant bubble. Subsequent events route to the
    // same shell. Reset on `renderHistory` (replay) and re-seeded from the
    // DOM on WS-reconnect mid-turn via getOrCreateTrace's fallback below.
    var traceShells = Object.create(null);

    // M11 F9 L4: dedup set of pending-approval ids seen this session.
    // Skips re-render when both the replay path (renderHistory) and the
    // WS broadcast path (onmessage 'pending-approval' branch) deliver the
    // same approval_id — handles the restore-then-broadcast race AND the
    // broadcast-then-restore race symmetrically. Reset at two boundaries:
    // inside renderHistory (covers session_joined replay) and inside
    // startSessionWith (covers new-chat creation, which sets currentSessionId
    // = null without calling renderHistory).
    var seenApprovalIds = Object.create(null);

    function getOrCreateTrace(parentMessageId) {
      if (!parentMessageId) return null;
      if (traceShells[parentMessageId]) return traceShells[parentMessageId];
      // Self-heal across WS reconnect: if a shell for this parent already
      // exists in the DOM from a prior connection's closure, re-seed the
      // bucket from DOM rather than minting a duplicate.
      var existing = messagesEl.querySelector(
        '.trace-shell[data-parent-msg-id="' + cssEscape(parentMessageId) + '"]'
      );
      if (existing) {
        traceShells[parentMessageId] = existing;
        return existing;
      }
      var shell = App.chat.renderTrace(parentMessageId);
      messagesEl.appendChild(shell);
      traceShells[parentMessageId] = shell;
      return shell;
    }

    // M10 F05 L05: ``opts`` forwards visibility from the source event dict
    // (history-replay ``ev.visibility`` or live ``data.visibility``) into
    // renderMessage. Tool bubbles inherit the persisted visibility tag so
    // operator-only tool events render with the marker on replay.
    function buildToolMsg(text, isError, toolCallId, opts) {
      var el = App.chat.renderMessage(isError ? 'tool error' : 'tool', text, opts);
      if (toolCallId) el.dataset.toolCallId = toolCallId;
      return el;
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
      // L05: wrapper groups the attribution + button so appendToTrace
      // increments the trace-count by 1 per auth_required event (NOT 2).
      var group = document.createElement('div');
      group.className = 'login-required-group';
      group.dataset.sourceId = data.source_id || '';

      var attr = document.createElement('div');
      attr.className = 'login-required-attribution';
      attr.textContent = 'Authorization required to continue.';
      group.appendChild(attr);

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-filled-primary login-required-btn';
      btn.dataset.sourceId = data.source_id || '';
      btn.dataset.toolCallId = data.tool_call_id || '';
      btn.dataset.resourceMetadataUrl = data.resource_metadata_url || '';
      if (data.consent_url) btn.dataset.consentUrl = data.consent_url;
      var label = data.source_name
        || (data.source_id && sourceNames[data.source_id])
        || data.source_id
        || '<unknown>';
      btn.textContent = 'Log in to ' + label;
      btn.addEventListener('click', function () {
        startLoginFlow(data);
      });
      group.appendChild(btn);
      // L03: mount in the trace shell for this turn, if its parent_message_id
      // is present (the M07 OAuth event carries it). Fall back to a direct
      // .messages append for legacy/null cases (e.g. synthetic auth_required
      // events injected by tests).
      var authTrace = getOrCreateTrace(data.parent_message_id);
      if (authTrace) {
        App.chat.appendToTrace(authTrace, group);
      } else {
        messagesEl.appendChild(group);
      }
      scrollToBottomIfPinned();
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
        // Server will run `agent.step` only AFTER the load finishes — until
        // then, suppress the "thinking" indicator we optimistically showed
        // on send so the operator sees a single, accurate state.
        hideThinking();
        var loadEl = document.createElement('div');
        // `system-model-loading` is a system-only class so the
        // `Model loaded.` handler below can target this row exclusively
        // without accidentally matching the thinking indicator (which
        // also carries `.model-loading` for shared dot-animation styling).
        loadEl.className = 'msg system model-loading system-model-loading';
        loadEl.innerHTML = '<span class="model-loading-text">Loading model</span><span class="model-loading-dots"></span>';
        messagesEl.appendChild(loadEl);
        scrollToBottomIfPinned();
        var frames = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];
        var dotEl = loadEl.querySelector('.model-loading-dots');
        var frameIdx = 0;
        loadEl._dotTimer = setInterval(function () { frameIdx = (frameIdx + 1) % frames.length; dotEl.textContent = ' ' + frames[frameIdx]; }, 120);
      } else if (data.content === 'Model loaded.') {
        var loadingMsg = messagesEl.querySelector('.system-model-loading');
        if (loadingMsg) {
          if (loadingMsg._dotTimer) clearInterval(loadingMsg._dotTimer);
          loadingMsg.classList.remove('model-loading');
          loadingMsg.classList.remove('system-model-loading');
          loadingMsg.innerHTML = '';
          loadingMsg.textContent = 'Model loaded.';
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

      ws.onmessage = function (e) {
        var data = JSON.parse(e.data);

        if (data.type === 'session_list') {
          sessions = data.sessions;
          // M11 F17 L9 (Leg E) — fetch pending approvals for the left-panel
          // pinned section, then render the session list. Errors are swallowed
          // so a failing endpoint never blocks session navigation.
          var _sessionCallbacks = {
            onJoin: joinSession,
            onDelete: function (id, btn) {
              // Two-step confirm via the canonical App.confirmDelete helper
              // (F5 leg 02). WS delete is fire-and-forget so revertFn is
              // unused here — server-side broadcast updates the list.
              // Post-F2 leg 01: .session-item is now the inner <button>; the
              // row wrapper carrying the .confirm-delete class + the
              // [data-confirm-title] span is the <li class="list-item">.
              var item = btn.closest('.list-item');
              if (!item) return;
              App.confirmDelete(item, function (itemEl, revertFn) {
                ws.send(JSON.stringify({ action: 'delete_session', session_id: id }));
              });
            }
          };
          fetch('/api/connectors/peer-approvals/pending')
            .then(function (r) { return r.ok ? r.json() : []; })
            .catch(function () { return []; })
            .then(function (approvals) {
              pendingApprovals = Array.isArray(approvals) ? approvals : [];
              App.chat.renderSessionList(
                sessionListEl, sessions, currentSessionId, _sessionCallbacks, pendingApprovals
              );
              // Drain queued new-session intent (from startSessionWith while WS
              // was reconnecting). Takes priority over pendingJoinId and
              // auto-join so the user's explicit "new chat / switch agent"
              // action is honoured after a brief reconnect.
              if (pendingStart) {
                var startIntent = pendingStart;
                pendingStart = null;
                currentSessionId = null;
                seenApprovalIds = Object.create(null);
                if (window.App && window.App.router) App.router.replaceSub(null);
                var startMsg = { action: 'new_session' };
                if (startIntent.agentName) startMsg.agent_name = startIntent.agentName;
                ws.send(JSON.stringify(startMsg));
                return;
              }
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
            });
          return;
        }

        if (data.type === 'session_joined') {
          // Stale-join guard: ignore responses for superseded join requests.
          if (currentSessionId && currentSessionId !== data.session_id) return;
          // Clear the pending new-session intent: the intended session has
          // now joined successfully (either directly or after a WS reconnect).
          pendingStart = null;
          App.perf.mark('session-join:received');
          currentSessionId = data.session_id;
          if (window.App && window.App.router) {
            App.router.replaceSub('sessions/' + currentSessionId);
          }
          currentAgentName = data.agent_name;
          updateAgentBadge(data.agent_name);
          syncDropdownToCurrent();
          hideThinking();
          App.chat.resetTelemetry(content);
          renderHistory(data.history, data.agent_name);
          // M16 F06 L02: synchronously restore persisted last_usage into
          // the overlay so the token counts aren't lost on session reopen.
          // Uses the same defensive read pattern as the routing panel below.
          // max_context_tokens is 0 here (unknown until the seed resolves);
          // the bar will fill once setTelemetryMax runs async shortly after.
          var lastUsage = (data.session_metadata && data.session_metadata.last_usage) || null;
          if (lastUsage) {
            App.chat.updateTelemetry(content, {
              input_tokens: lastUsage.input_tokens || 0,
              output_tokens: lastUsage.output_tokens || 0,
              context_tokens: lastUsage.context_tokens || 0,
              max_context_tokens: 0,
            });
          }
          // M11 F13 L5: render the routing audit panel from the join
          // payload's session_metadata and wire the Refresh button to
          // re-fetch via REST.
          var routing = (data.session_metadata && data.session_metadata.routing) || [];
          App.chat.routingAuditPanel.render(routingAuditPanelEl, routing);
          App.chat.routingAuditPanel.wireRefresh(routingAuditPanelEl, data.session_id);
          setSessionHealth(data.status || 'ok');
          // Sync per-session busy state to server ground truth
          // (`is_session_processing(session.id)`). Without this,
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
          // F7 L04 eager-resolve: fetch the agent's max_context_tokens
          // BEFORE the first user message so the telemetry overlay's
          // `max:` field shows the real value (not 0). Closes F6.5
          // debrief AI #5. Fire-and-forget; failures (404 — agent was
          // deleted between session create and join — or 400 — provider
          // misconfigured) leave `max:` at its default until the first
          // usage event arrives. Placed AFTER showChrome() so the
          // overlay element exists before updateTelemetry mutates it.
          if (currentAgentName) {
            fetch('/api/agents/' + encodeURIComponent(currentAgentName) + '/context-window')
              .then(function (r) { return r.ok ? r.json() : null; })
              .then(function (payload) {
                if (payload && payload.max_context_tokens) {
                  // M16 F06 L02: max-only seed — never re-zeros restored
                  // used-counts; recomputes the bar from retained context_tokens.
                  App.chat.setTelemetryMax(content, payload.max_context_tokens);
                }
              })
              .catch(function () { /* best-effort; silent on failure */ });
          }
          // M08 F6 L06 HAT fix: scroll-to-bottom on session join/deep-link/
          // refresh. renderHistory() above ran while chrome was hidden
          // (clientHeight=0), so smart-scroll's pin check failed. After
          // showChrome flips visibility, jump unconditionally to the most
          // recent message — that's where the user expects to land when
          // they open a session.
          messagesEl.scrollTop = messagesEl.scrollHeight;
          App.perf.mark('session-join:dom-mutated');
          App.perf.measure('session-join.ws-to-dom', 'session-join:received', 'session-join:dom-mutated');
          requestAnimationFrame(function () {
            App.perf.mark('session-join:painted');
            App.perf.measure('session-join.dom-to-paint', 'session-join:dom-mutated', 'session-join:painted');
          });
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
            // M11 F13 L5: clear the routing audit panel back to empty
            // state when the current session is deleted.
            App.chat.routingAuditPanel.render(routingAuditPanelEl, []);
            // Don't auto-create — session_list refresh below picks the fallback.
          }
          refreshSessionList();
          return;
        }

        if (data.type === 'user') {
          var cls = data.source === 'api' ? 'user api' : 'user';
          // M10 F05 L05: forward visibility from the live user event.
          // ``data.visibility`` is undefined on today's live broadcasts
          // (known limitation: storage-edge shim runs post-step; live
          // broadcast emits inline within step) — the channel is wired
          // for the follow-on live-broadcast tagging leg.
          // M11 F06 L04: forward peer_name from the live broadcast onto the
          // attribution + bubble side. Connector-inbound user events carry
          // data.peer_name (per F6 L3 dispatcher binding + F6 L2 codec
          // projection). Operator-typed user events have no peer_name.
          var liveAttribution = data.peer_name || 'You';
          addMsg(cls, (data.source && data.source !== 'web' ? '[' + data.source + '] ' : '') + data.content, liveAttribution, { visibility: data.visibility, peerName: data.peer_name });
        }
        else if (data.type === 'assistant_chunk') {
          // Streaming chunk path (leg-04, option B minimal rendering).
          // First chunk: clear thinking, mint a fresh assistant bubble +
          // attribution. Subsequent chunks: enqueue the delta into the
          // pacing queue; a setInterval loop drains characters at a
          // smooth rate. Markdown rendering on `done` lands in leg 05.
          hideThinking();
          if (!currentStreamingMsg) {
            // M10 F05 L05: capture visibility from the FIRST chunk so the
            // class+label land at placeholder construction (not at
            // finalize — that would cause a visual flip). Today's live
            // broadcast doesn't carry the tag; the placeholder renders
            // unmarked and the persisted view (post-refresh) shows the
            // marker via the codec replay path.
            currentStreamingVisibility = data.visibility || null;
            var bubble = App.chat.renderMessage('assistant', '', { renderMarkdown: false, visibility: currentStreamingVisibility });
            messagesEl.appendChild(bubble);
            messagesEl.appendChild(App.chat.renderAttribution('from-agent', currentAgentName || 'agent', new Date().toISOString()));
            // Ensure the bubble has a text node child to mutate.
            if (!bubble.firstChild) {
              bubble.appendChild(document.createTextNode(''));
            }
            currentStreamingMsg = bubble;
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
          currentStreamingVisibility = null;
          // M10 F05 L05: forward visibility from the live assistant event.
          addMsg('assistant', data.content, currentAgentName || 'agent', { visibility: data.visibility });
        }
        else if (data.type === 'tool_call') {
          hideThinking();
          // Iteration boundary — finalize the current streaming bubble so
          // iteration N+1's chunks land in a fresh bubble (markdown
          // rendering + reset of currentStreamingMsg both happen inside).
          finalizeStreamingBubble();
          currentStreamingVisibility = null;
          // L03: route into the trace shell for this assistant turn.
          var argsText = '> ' + data.name + '(' + Object.entries(data.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')';
          var liveTrace = getOrCreateTrace(data.parent_message_id);
          // M10 F05 L05: forward visibility from the live tool_call event.
          var liveMsg = buildToolMsg(argsText, false, data.tool_call_id, { visibility: data.visibility });
          if (liveTrace) {
            App.chat.appendToTrace(liveTrace, liveMsg);
          } else {
            // Legacy / null parent_message_id — render standalone.
            messagesEl.appendChild(liveMsg);
          }
          scrollToBottomIfPinned();
        }
        else if (data.type === 'tool_result') {
          // Iteration boundary — finalize the current streaming bubble.
          finalizeStreamingBubble();
          currentStreamingVisibility = null;
          // L03: route into the trace shell for this assistant turn.
          var resTrace = getOrCreateTrace(data.parent_message_id);
          // M10 F05 L05: forward visibility from the live tool_result event.
          var resMsg = buildToolMsg(data.content, data.is_error, data.tool_call_id, { visibility: data.visibility });
          if (resTrace) {
            App.chat.appendToTrace(resTrace, resMsg);
          } else {
            messagesEl.appendChild(resMsg);
          }
          scrollToBottomIfPinned();
        }
        else if (data.type === 'system') handleSystem(data);
        else if (data.type === 'usage') App.chat.updateTelemetry(content, data);
        else if (data.type === 'pending-approval') {
          // M11 F9 L4: live pending-approval banner from the dispatcher
          // (the_one/connectors/_inbound.py emit site). Dedup against the
          // replay path's seenApprovalIds Set so an in-flight broadcast
          // that races a session restore doesn't double-render. The
          // event shape is byte-identical to the codec's projection at
          // pending_approvals_to_ui_events.
          if (!seenApprovalIds[data.approval_id]) {
            seenApprovalIds[data.approval_id] = true;
            var liveBanner = App.chat.renderPendingApproval(data, {
              onApprove: onApproveClick,
              onDismiss: onDismissClick,
            });
            messagesEl.appendChild(liveBanner);
            scrollToBottomIfPinned();
          }
        }
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
          currentStreamingVisibility = null;
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
          currentStreamingVisibility = null;
          if (currentSessionId) delete inFlightSessions[currentSessionId];
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
