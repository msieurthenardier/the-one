// App.chat.transcript -- the message log: addMsg and the scroll pin, history replay, the
// streaming bubble (pacing, safe markdown boundary, finalize), the thinking indicator, trace
// shells, tool bubbles, delivered tool results and the notice lines (M31 F6 L02, split out of
// areas/chat.js; M31 F6 L05c moved it onto the control library: App.ui.message and its
// attribution, App.ui.thinking, App.ui.trace and App.ui.notice).
//
// The streaming source stays here (DD4): pacing, the safe markdown boundary and the finalize
// swap are the area's logic; the bubble's text node is driven through the message handle.
// clearLog() is the one log wipe: it drops every handle the old log held (thinking, model
// loading, the streaming bubble, the trace map), so no timer survives a conversation change.
//
// Exposes the functions below; traceShellFor and resetTraceShells give the other modules the
// trace-shell bucket (it is reassigned on a new conversation, so it never leaves this module).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // The prefix the server puts on a failed turn's `system` frame (app.py).
  var AGENT_ERROR_PREFIX = 'Agent error: ';

  // An ISO timestamp as the operator-zone clock time ("3:45 PM", DD14); '' for a falsy or
  // invalid value (the attribution then renders no time).
  function fmtTs(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    return window.App.time.formatClock(d);
  }

  function create(ctx) {
    var state = ctx.state;
    var messagesEl = ctx.messagesEl;

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

    // The one shared role=status node the "Copy reply" confirmations announce in (it lives
    // outside the role=log message list, so the confirmation is not read as a new message).
    function liveEl() { return ctx.copyLiveEl; }
    // Code-block copy confirmations announce in the same shared node.
    function mdOpts() { return { copyLiveEl: ctx.copyLiveEl }; }

    // The side of a bubble's attribution: a peer-attributed user bubble aligns left (M11 F06
    // L04), an operator-typed one right, every other bubble left.
    function sideFor(role, opts) {
      if (opts.peerName) return 'peer';
      return role === 'user' ? 'you' : 'agent';
    }

    // addMsg(cls, text, attribution, opts): `cls` is the role, optionally followed by 'api'
    // (an API-injected user message) or 'error' (a failed tool result), as the callers have
    // always spelled it. opts: ts, visibility, peerName.
    function addMsg(cls, text, attribution, opts) {
      App.perf.mark('addMsg:start');
      opts = opts || {};
      var tokens = cls.split(' ');
      var role = tokens[0];
      var msg = App.ui.message({
        role: role,
        source: tokens.indexOf('api') !== -1 ? 'api' : null,
        tone: tokens.indexOf('error') !== -1 ? 'error' : null,
        body: role === 'assistant' ? App.markdown.render(text, mdOpts()) : null,
        text: role === 'assistant' ? null : text,
        visibility: opts.visibility,
        visibilityStyle: App.ui.message.visibilityStyles.chip,
        peerName: opts.peerName,
        testid: 'message'
      });
      // A user message ends the previous turn's iteration; an assistant bubble is the anchor
      // the next `thinking` disclosure is placed above (B2).
      if (role === 'user') iterationAnchor = null;
      if (role === 'assistant') iterationAnchor = msg.el;
      messagesEl.appendChild(msg.el);
      if (attribution) {
        var ts = Object.prototype.hasOwnProperty.call(opts, 'ts') ? opts.ts : new Date().toISOString();
        var attr = App.ui.message.attribution({
          side: sideFor(role, opts),
          name: attribution,
          ts: ts,
          timeLabel: fmtTs(ts),
          // F1: a finished agent reply copies its stored content (an empty reply has none).
          copyText: role === 'assistant' && text ? text : null,
          liveEl: liveEl(),
          copyTestid: 'message-copy'
        });
        messagesEl.appendChild(attr.el);
      }
      scrollToBottomIfPinned();
      App.perf.mark('addMsg:end');
      App.perf.measure('addMsg', 'addMsg:start', 'addMsg:end');
    }

    // The one log wipe (DD11 4): every handle the old log held is dropped, then the log is
    // emptied. The three wipe sites (a pending chat, a deleted chat, a history replay) call it.
    function clearLog() {
      hideThinking();
      dropModelLoading();
      resetStream();
      traceShells = Object.create(null);
      iterationAnchor = null;
      messagesEl.replaceChildren();
    }

    // Drop a streaming bubble that belongs to the conversation being left.
    function resetStream() {
      stopPacing();
      pendingChars = '';
      streamMsg = null;
      streamAttr = null;
      streamSource = '';
      currentStreamingVisibility = null;
    }

    // B2: the node a `thinking` disclosure is placed above. The live frame carries no message
    // id and arrives after its reply, so the anchor is the current iteration's reply bubble: the
    // streaming bubble, or the last assistant bubble added since the iteration began. It is
    // cleared at every iteration boundary (tool_call, tool_result, user, done, cancelled), so a
    // thinking-plus-tool-call iteration (no reply) appends in stream order. On replay the
    // anchor is only the bubble built from the immediately preceding `assistant` event.
    var iterationAnchor = null;
    function clearIterationAnchor() { iterationAnchor = null; }

    function renderHistory(history, agentName) {
      messagesEl.setAttribute('aria-busy', 'true');
      // A streaming bubble, a thinking or model-loading line from the conversation the log
      // showed before are dropped with the wipe.
      clearLog();
      var agentLabel = agentName || 'agent';
      for (var i = 0; i < history.length; i++) {
        var ev = history[i];
        // Pass ts explicitly (server-side broadcast events carry it; DB-restored
        // events do not). When ts is undefined, addMsg's default is omitted so
        // historical messages without a stored timestamp render unsuffixed.
        // M10 F05 L05: forward ev.visibility so operator-only bubbles
        // gain the visual marker on replay. Codec emits the key only when
        // non-None (the_one/db/codec.py:154).
        // M11 F06 L04: forward ev.peer_name onto histOpts.peerName so peer-
        // attributed user bubbles render left-aligned with a peer-name
        // attribution label.
        var histOpts = { ts: ev.ts || null, visibility: ev.visibility, peerName: ev.peer_name };
        if (ev.type === 'user') {
          var cls = ev.source === 'api' ? 'user api' : 'user';
          var attribution = ev.peer_name || 'You';
          addMsg(cls, (ev.source && ev.source !== 'web' && ev.source !== 'restored' ? '[' + ev.source + '] ' : '') + ev.content, attribution, histOpts);
        }
        else if (ev.type === 'assistant') addMsg('assistant', ev.content, agentLabel, histOpts);
        // M16 F10 L05: replay the thinking disclosure, above the reply it belongs to (B2).
        else if (ev.type === 'thinking') renderThinking(ev);
        else if (ev.type === 'tool_call') {
          iterationAnchor = null;
          // L03: bucket tool_call events under their parent_message_id's
          // trace shell; fall back to a standalone bubble for legacy/null.
          var argsText = '> ' + ev.name + '(' + Object.entries(ev.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')';
          var trace = getOrCreateTrace(ev.parent_message_id);
          var msg = buildToolMsg(argsText, false, ev.tool_call_id, { visibility: ev.visibility });
          if (trace) trace.append(msg);
          else messagesEl.appendChild(msg);
        }
        else if (ev.type === 'tool_result') {
          iterationAnchor = null;
          // M23 F02 L03: a delivered (peer-visible) tool result is
          // promoted to a top-level bubble — imperceivable buried inside
          // the collapsed accordion otherwise. Everything else keeps the
          // pre-existing L03 bucketing.
          if (isDeliveredToolResult(ev)) {
            appendDeliveredToolMsg(ev, agentLabel, ev.ts || null);
          } else {
            var trace2 = getOrCreateTrace(ev.parent_message_id);
            var msg2 = buildToolMsg(ev.content, ev.is_error, ev.tool_call_id, { visibility: ev.visibility });
            if (trace2) trace2.append(msg2);
            else messagesEl.appendChild(msg2);
          }
        }
        // Filter transient model-loading pings — live UI hints, not history.
        else if (ev.type === 'system' && ev.content !== 'Loading model...' && ev.content !== 'Model loaded.') {
          addMsg('system', ev.content, null, histOpts);
        }
      }
      iterationAnchor = null;
      messagesEl.removeAttribute('aria-busy');
    }

    // The streaming bubble: the App.ui.message handle (streaming: true) accumulating chunks for
    // the in-flight assistant iteration, its attribution handle, and the FULL received text of
    // this bubble (commitSafeBoundary throws committed text away, so Copy needs its own copy).
    // Reset to null at iteration boundaries (`tool_call` / `tool_result`) and at the end of the
    // agent step (`done`), so iteration N+1 lands chunks in a fresh bubble.
    var streamMsg = null;
    var streamAttr = null;
    var streamSource = '';
    // M10 F05 L05: visibility for the streaming bubble. Captured from the FIRST
    // ``assistant_chunk`` of a turn (``data.visibility`` if present) and applied at
    // placeholder construction so the marker lands before chunk accumulation. Today's live
    // broadcast doesn't carry ``visibility`` on ``assistant_chunk`` (known limitation: the
    // storage-edge shim runs AFTER the agent step; broadcasts fire WITHIN it), so the bubble is
    // unmarked until a re-join replays the codec's tag.
    var currentStreamingVisibility = null;

    // Render-pacing queue: API chunks enqueue here; a setInterval loop
    // drains characters into the bubble's pending tail at ~60 chars/sec.
    // Adaptive: long queue drains faster so we don't lag behind a fast API.
    // On finalize, the queue drains synchronously before the markdown swap.
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
    // prefix as markdown and shrink the pending tail.
    function commitSafeBoundary() {
      if (!streamMsg) return;
      var tail = streamMsg.tail();
      var boundary = findSafeRenderBoundary(tail);
      if (boundary <= 0) return;
      var prefix = tail.slice(0, boundary);
      streamMsg.commit(App.markdown.render(prefix, mdOpts()), prefix.length);
    }

    function pacingTick() {
      if (!pendingChars.length || !streamMsg) return;
      var n = Math.max(1, Math.ceil(pendingChars.length / 30));
      var slice = pendingChars.slice(0, n);
      pendingChars = pendingChars.slice(n);
      streamMsg.appendText(slice);
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
      if (pendingChars.length && streamMsg) streamMsg.appendText(pendingChars);
      pendingChars = '';
      stopPacing();
    }

    // Leg 05: swap the streaming bubble's pending tail for its markdown-rendered fragment.
    // Already-committed blocks (from commitSafeBoundary) stay in place. Idempotent: a no-op
    // when no bubble is active. F1: the reply's Copy button is added here, with the full
    // received text (also for a Stopped reply, which copies what was received).
    function finalizeStreamingBubble() {
      drainPacing();
      var bubble = streamMsg;
      if (!bubble) return;
      var attr = streamAttr;
      var source = streamSource;
      streamMsg = null;
      streamAttr = null;
      streamSource = '';
      var tail = bubble.tail();
      bubble.finalize(tail ? App.markdown.render(tail, mdOpts()) : null);
      if (attr && source) attr.setCopy(source);
    }

    // The thinking line (A8): "Thinking" and the control's dots, which read as "Thinking…"
    // (a static ellipsis under reduced motion). hideThinking stops its timer AND removes it.
    var thinkingHandle = null;
    function showThinking() {
      if (thinkingHandle) return;
      thinkingHandle = App.ui.thinking({ label: 'Thinking', tone: 'assistant', testid: 'thinking-indicator' });
      messagesEl.appendChild(thinkingHandle.el);
      scrollToBottomIfPinned();
    }

    function hideThinking() {
      if (!thinkingHandle) return;
      thinkingHandle.destroy();
      if (thinkingHandle.el.parentNode) thinkingHandle.el.parentNode.removeChild(thinkingHandle.el);
      thinkingHandle = null;
    }

    // The "Loading model" line: a system-toned thinking handle kept here, settled in place by
    // "Model loaded." (never found by a class query) and dropped on any log wipe or turn end.
    var loadingHandle = null;
    function showModelLoading() {
      hideThinking();
      dropModelLoading();
      loadingHandle = App.ui.thinking({ label: 'Loading model', tone: 'system', testid: 'model-loading' });
      messagesEl.appendChild(loadingHandle.el);
      scrollToBottomIfPinned();
    }

    // Settles the loading line to `text`; false when there is none (the caller adds a line).
    function settleModelLoading(text) {
      if (!loadingHandle) return false;
      loadingHandle.settle(text);
      loadingHandle = null;
      return true;
    }

    // Stops the loading line's timer and removes it (a wipe, an error, a turn's end).
    function dropModelLoading() {
      if (!loadingHandle) return;
      loadingHandle.destroy();
      if (loadingHandle.el.parentNode) loadingHandle.el.parentNode.removeChild(loadingHandle.el);
      loadingHandle = null;
    }

    function cssEscape(s) {
      // Minimal subset of CSS.escape — escape quotes + backslashes so the
      // attribute selector parses cleanly. source_ids are always slugs (no
      // whitespace) per L0/L1 validation, so this is sufficient.
      return String(s).replace(/(["\\])/g, '\\$1');
    }

    // L03: bucket of trace handles keyed by parent_message_id.
    // On first tool event for a parent, create the trace and append to
    // .messages after the assistant bubble. Subsequent events route to the
    // same trace. Reset by clearLog (replay) and re-seeded from the DOM on a
    // WS reconnect mid-turn through App.ui.trace.find.
    var traceShells = Object.create(null);

    function getOrCreateTrace(parentMessageId) {
      if (!parentMessageId) return null;
      if (traceShells[parentMessageId]) return traceShells[parentMessageId];
      // Self-heal across WS reconnect: if a trace for this parent already exists in the DOM
      // from a prior connection's closure, re-wrap it rather than minting a duplicate.
      var existing = App.ui.trace.find(messagesEl, parentMessageId);
      if (existing) {
        traceShells[parentMessageId] = existing;
        return existing;
      }
      // B3: an icon chevron and "Tool activity · {n}".
      var trace = App.ui.trace({
        id: parentMessageId,
        label: 'Tool activity',
        chevron: 'icon',
        countStyle: 'dot',
        testid: 'trace-shell'
      });
      messagesEl.appendChild(trace.el);
      traceShells[parentMessageId] = trace;
      return trace;
    }

    // M16 F10 L05: place a thinking disclosure. Used by BOTH the live ``thinking`` ws handler
    // and the ``renderHistory`` replay branch. B2: above the reply bubble of its own
    // iteration (the anchor above); with no reply (a thinking-plus-tool-call iteration) it is
    // appended in stream order, as before. It is its OWN disclosure, never nested in the
    // tool trace, and it does not touch the thinking line.
    function renderThinking(evt) {
      evt = evt || {};
      var disclosure = App.ui.trace.thinking({
        label: 'Thinking',
        body: evt.content != null ? evt.content : '',
        parentId: evt.parent_message_id,
        testid: 'thinking-disclosure'
      });
      if (iterationAnchor && iterationAnchor.parentNode === messagesEl) {
        messagesEl.insertBefore(disclosure.el, iterationAnchor);
      } else {
        messagesEl.appendChild(disclosure.el);
      }
      scrollToBottomIfPinned();
    }

    // M10 F05 L05: ``opts`` forwards visibility from the source event dict
    // (history-replay ``ev.visibility`` or live ``data.visibility``). Tool bubbles inherit the
    // persisted visibility tag so operator-only tool events render with the marker on replay.
    // Returns the bubble's element.
    function buildToolMsg(text, isError, toolCallId, opts) {
      opts = opts || {};
      var msg = App.ui.message({
        role: 'tool',
        tone: isError ? 'error' : null,
        text: text,
        visibility: opts.visibility,
        visibilityStyle: App.ui.message.visibilityStyles.chip,
        testid: 'message'
      });
      if (toolCallId) msg.el.dataset.toolCallId = toolCallId;
      return msg.el;
    }

    // M23 F02 L03 (behavior-test fix): a tool_result event is "delivered"
    // (peer-visible, e.g. a successful send_to_platform_channel result) when
    // the session is connector-attached AND the event carries no
    // operator-only tag. Gated on `currentSessionPlatform` — a plain
    // (non-connector) chat session's tool results carry no `visibility` key
    // either, but there's no peer to have seen them, so they must keep
    // collapsing into the "Tool activity" accordion like before. Excludes
    // error results defensively (an error never actually reached a
    // platform-send success, but the visibility tag alone shouldn't be the
    // only guard against surfacing an error as if it were delivered).
    function isDeliveredToolResult(ev) {
      return !!state.currentSessionPlatform && !ev.is_error && ev.visibility !== 'operator';
    }

    // Renders a delivered (peer-visible) tool-result as a top-level bubble
    // — outside the "Tool activity" accordion — with the same agent
    // attribution row an ordinary assistant reply gets (without a Copy: F1 is agent replies
    // only), so it reads as "this reached the peer" rather than as leftover tool debug chatter.
    // `ts` mirrors addMsg's own default: history replay passes the stored timestamp (may be
    // undefined — renders unsuffixed); the live handler passes the render-time Date.
    function appendDeliveredToolMsg(ev, agentLabel, ts) {
      messagesEl.appendChild(buildToolMsg(ev.content, ev.is_error, ev.tool_call_id, { visibility: ev.visibility }));
      messagesEl.appendChild(App.ui.message.attribution({
        side: 'agent',
        name: agentLabel,
        ts: ts,
        timeLabel: fmtTs(ts)
      }).el);
    }

    // A4: an agent error (a `system` frame whose content starts "Agent error: ") is a danger
    // notice with a fixed headline and the raw text under a collapsed "Technical details".
    function isAgentError(content) {
      return typeof content === 'string' && content.indexOf(AGENT_ERROR_PREFIX) === 0;
    }

    function addAgentError(content) {
      var details = App.ui.disclosure({
        variant: 'plain',
        summary: 'Technical details',
        testid: 'chat-agent-error-details'
      });
      details.body.appendChild(document.createTextNode(content.slice(AGENT_ERROR_PREFIX.length)));
      var body = document.createDocumentFragment();
      body.appendChild(document.createTextNode("The agent couldn't finish this reply."));
      body.appendChild(details.el);
      var notice = App.ui.notice({ tone: 'danger', body: body, testid: 'chat-agent-error' });
      messagesEl.appendChild(notice.el);
      scrollToBottomIfPinned();
    }

    // B9: a muted line in the log ("Stopped.", "Queued message discarded."). Never stored, so
    // a re-join shows neither.
    function addStoppedNotice() {
      messagesEl.appendChild(App.ui.notice({ tone: 'muted', body: 'Stopped.', testid: 'chat-stopped' }).el);
      scrollToBottomIfPinned();
    }

    function addDiscardedNotice() {
      messagesEl.appendChild(App.ui.notice({
        tone: 'muted',
        body: 'Queued message discarded.',
        testid: 'chat-discarded'
      }).el);
      scrollToBottomIfPinned();
    }

    // DD8 F2: the agent ran out of steps. A muted line after the reply, never stored (a re-join
    // renders none). "Max iterations" links to the agent's settings only when the agent has a
    // stored record (the default agent and a deleted agent get plain text).
    function addStepLimitNotice(steps, agentName) {
      var n = Number(steps);
      var used = n >= 1 ? 'used its ' + n + ' steps' : 'reached its step limit';
      var rows = App.store.peek('agents').value;
      var hasRecord = false;
      if (agentName && Array.isArray(rows)) {
        for (var i = 0; i < rows.length; i++) {
          if (rows[i] && rows[i].name === agentName) { hasRecord = true; break; }
        }
      }
      var body = document.createDocumentFragment();
      body.appendChild(document.createTextNode('Stopped: this agent ' + used + ' for this message. Send another message to continue, or raise '));
      if (hasRecord) {
        var link = document.createElement('a');
        link.href = App.router.href({ destination: 'agents', id: agentName });
        link.textContent = 'Max iterations';
        link.setAttribute('data-testid', 'chat-step-limit-link');
        body.appendChild(link);
      } else {
        body.appendChild(document.createTextNode('Max iterations'));
      }
      body.appendChild(document.createTextNode(' in its settings.'));
      messagesEl.appendChild(App.ui.notice({ tone: 'muted', body: body, testid: 'chat-step-limit' }).el);
      scrollToBottomIfPinned();
    }

    function traceShellFor(parentMessageId) {
      var trace = traceShells[parentMessageId];
      return trace ? trace.el : null;
    }
    function resetTraceShells() { traceShells = Object.create(null); }
    function clearStreamingVisibility() { currentStreamingVisibility = null; }

    // The live assistant_chunk frame (moved from the gated frame chain, turn-frames.js).
    function onAssistantChunk(data) {
      hideThinking();
      if (!streamMsg) {
        // M10 F05 L05: capture visibility from the FIRST chunk so the marker lands at
        // construction (not at finalize — that would cause a visual flip).
        currentStreamingVisibility = data.visibility || null;
        streamMsg = App.ui.message({
          role: 'assistant',
          streaming: true,
          visibility: currentStreamingVisibility,
          visibilityStyle: App.ui.message.visibilityStyles.chip,
          testid: 'message'
        });
        messagesEl.appendChild(streamMsg.el);
        var now = new Date().toISOString();
        streamAttr = App.ui.message.attribution({
          side: 'agent',
          name: state.currentAgentName || 'agent',
          ts: now,
          timeLabel: fmtTs(now),
          liveEl: liveEl(),
          copyTestid: 'message-copy'
        });
        messagesEl.appendChild(streamAttr.el);
        streamSource = '';
        iterationAnchor = streamMsg.el;
        startPacing();
      }
      streamSource += data.content;
      pendingChars += data.content;
    }

    return {
      SCROLL_PIN_THRESHOLD: SCROLL_PIN_THRESHOLD,
      addMsg: addMsg,
      scrollToBottomIfPinned: scrollToBottomIfPinned,
      clearLog: clearLog,
      resetStream: resetStream,
      renderHistory: renderHistory,
      showThinking: showThinking,
      hideThinking: hideThinking,
      showModelLoading: showModelLoading,
      settleModelLoading: settleModelLoading,
      dropModelLoading: dropModelLoading,
      finalizeStreamingBubble: finalizeStreamingBubble,
      clearIterationAnchor: clearIterationAnchor,
      getOrCreateTrace: getOrCreateTrace,
      renderThinking: renderThinking,
      buildToolMsg: buildToolMsg,
      isDeliveredToolResult: isDeliveredToolResult,
      appendDeliveredToolMsg: appendDeliveredToolMsg,
      isAgentError: isAgentError,
      addAgentError: addAgentError,
      addStoppedNotice: addStoppedNotice,
      addDiscardedNotice: addDiscardedNotice,
      addStepLimitNotice: addStepLimitNotice,
      cssEscape: cssEscape,
      traceShellFor: traceShellFor,
      resetTraceShells: resetTraceShells,
      clearStreamingVisibility: clearStreamingVisibility,
      onAssistantChunk: onAssistantChunk
    };
  }

  window.App.chat.transcript = { create: create };
})();
