// App.chat.transcript -- the message log: addMsg and the scroll pin, history replay, the
// streaming bubble (pacing, safe markdown boundary, finalize), the thinking indicator, trace
// shells, tool bubbles and delivered tool results (M31 F6 L02, split out of areas/chat.js,
// moved verbatim apart from the ctx./state. prefixes).
//
// Exposes the functions below; traceShellFor and resetTraceShells give the other modules the
// trace-shell bucket (it is reassigned on a new conversation, so it never leaves this module).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

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

    // Drop a streaming bubble that belongs to the conversation being left.
    function resetStream() {
      stopPacing();
      pendingChars = '';
      currentStreamingMsg = null;
      currentStreamingVisibility = null;
    }

    function renderHistory(history, agentName) {
      messagesEl.setAttribute('aria-busy', 'true');
      // A streaming bubble from the conversation the log showed before is
      // detached by the wipe below; a later chunk must start a fresh one.
      resetStream();
      messagesEl.replaceChildren();
      // L03: reset the trace-shell bucket on replay so the DOM-rebuild
      // starts fresh; getOrCreateTrace will append shells to the freshly
      // emptied .messages container.
      traceShells = Object.create(null);
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
        // M16 F10 L05: replay the thinking disclosure (position-independent).
        else if (ev.type === 'thinking') renderThinking(ev);
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
          // M23 F02 L03: a delivered (peer-visible) tool result is
          // promoted to a top-level bubble — imperceivable buried inside
          // the collapsed accordion otherwise. Everything else keeps the
          // pre-existing L03 bucketing.
          if (isDeliveredToolResult(ev)) {
            appendDeliveredToolMsg(ev, agentLabel, ev.ts || null);
          } else {
            var trace2 = getOrCreateTrace(ev.parent_message_id);
            var msg2 = buildToolMsg(ev.content, ev.is_error, ev.tool_call_id, { visibility: ev.visibility });
            if (trace2) App.chat.appendToTrace(trace2, msg2);
            else messagesEl.appendChild(msg2);
          }
        }
        // Filter transient model-loading pings — live UI hints, not history.
        else if (ev.type === 'system' && ev.content !== 'Loading model...' && ev.content !== 'Model loaded.') {
          addMsg('system', ev.content, null, histOpts);
        }
      }
      messagesEl.removeAttribute('aria-busy');
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

    // M16 F10 L05: append a thinking disclosure in stream order. Used by BOTH
    // the live ``thinking`` ws handler and the ``renderHistory`` replay branch.
    // Position-independent (mirrors getOrCreateTrace's append) — the source
    // turn may have empty content and thus no preceding assistant bubble. Its
    // OWN disclosure (a distinct `.thinking-disclosure` <details>), NOT nested
    // in the tool-trace shell. Does NOT touch the loading spinner
    // (createThinking/removeThinking/showThinking/hideThinking).
    function renderThinking(evt) {
      messagesEl.appendChild(App.chat.renderThinking(evt));
      scrollToBottomIfPinned();
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
    // attribution row an ordinary assistant reply gets, so it reads as "this
    // reached the peer" rather than as leftover tool debug chatter. `ts`
    // mirrors addMsg's own default: history replay passes the stored
    // timestamp (may be undefined — renders unsuffixed); the live handler
    // passes the render-time Date.
    function appendDeliveredToolMsg(ev, agentLabel, ts) {
      var msgEl = buildToolMsg(ev.content, ev.is_error, ev.tool_call_id, { visibility: ev.visibility });
      messagesEl.appendChild(msgEl);
      messagesEl.appendChild(App.chat.renderAttribution('from-agent', agentLabel, ts));
    }

    function traceShellFor(parentMessageId) { return traceShells[parentMessageId]; }
    function resetTraceShells() { traceShells = Object.create(null); }
    function clearStreamingVisibility() { currentStreamingVisibility = null; }

    // The live assistant_chunk frame (moved from the gated frame chain, turn-frames.js).
    function onAssistantChunk(data) {
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
        messagesEl.appendChild(App.chat.renderAttribution('from-agent', state.currentAgentName || 'agent', new Date().toISOString()));
        // Ensure the bubble has a text node child to mutate.
        if (!bubble.firstChild) {
          bubble.appendChild(document.createTextNode(''));
        }
        currentStreamingMsg = bubble;
        startPacing();
      }
      pendingChars += data.content;
    }

    return {
      SCROLL_PIN_THRESHOLD: SCROLL_PIN_THRESHOLD,
      addMsg: addMsg,
      scrollToBottomIfPinned: scrollToBottomIfPinned,
      resetStream: resetStream,
      renderHistory: renderHistory,
      showThinking: showThinking,
      hideThinking: hideThinking,
      finalizeStreamingBubble: finalizeStreamingBubble,
      getOrCreateTrace: getOrCreateTrace,
      renderThinking: renderThinking,
      buildToolMsg: buildToolMsg,
      isDeliveredToolResult: isDeliveredToolResult,
      appendDeliveredToolMsg: appendDeliveredToolMsg,
      cssEscape: cssEscape,
      traceShellFor: traceShellFor,
      resetTraceShells: resetTraceShells,
      clearStreamingVisibility: clearStreamingVisibility,
      onAssistantChunk: onAssistantChunk
    };
  }

  window.App.chat.transcript = { create: create };
})();
