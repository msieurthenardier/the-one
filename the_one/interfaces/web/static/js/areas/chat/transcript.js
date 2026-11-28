// App.chat.transcript -- the message log: addMsg and the scroll pin, history replay, the
// model-loading line, tool bubbles, delivered tool results and the notice lines (M31 F6 L02,
// split out of areas/chat.js; M31 F6 L05c moved it onto the control library: App.ui.message
// and its attribution, App.ui.thinking and App.ui.notice).
//
// A turn's work (narration, thinking, tool calls) and its replay live in App.chat.turnWork
// (Sortie 16 L02); this module builds the reply bubble, the chart and widget draws and the
// markdown seam (renderMarkdown) it uses.
// clearLog() is the one log wipe: it drops every handle the old log held (the turn groups,
// model loading, widget cards), so no timer survives a conversation change.
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
    function isPinned() {
      return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight <= SCROLL_PIN_THRESHOLD;
    }
    function scrollToBottomIfPinned() {
      if (isPinned()) {
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }
    // M35 F1 L2 (AC10): for later layout (a chart's first draw, a width change) the pinned state
    // cannot be re-measured, because the content already grew. The flag is true after content was
    // inserted while pinned and false once the reader scrolls away from the bottom.
    var pinnedFlag = true;
    // A hidden box (a narrow window showing the list pane) has no height and may report a reset
    // scroll position: that is not the reader leaving the bottom, so it never clears the flag.
    messagesEl.addEventListener('scroll', function () {
      if (!messagesEl.clientHeight) return;
      pinnedFlag = isPinned();
    });
    function onChartLayout() {
      if (pinnedFlag) messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    // Sortie 21 L1: a pinned transcript stays pinned when its box reappears or resizes (the chat
    // pane shown after the list, a composer height change). Disconnected by destroy(), never by
    // clearLog (which runs on every conversation change).
    var resizeObserver = null;
    if (typeof ResizeObserver === 'function') {
      resizeObserver = new ResizeObserver(function () {
        if (messagesEl.clientHeight) onChartLayout();
      });
      resizeObserver.observe(messagesEl);
    }
    function destroy() {
      if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null; }
    }
    // The one shared role=status node the "Copy reply" confirmations announce in (it lives
    // outside the role=log message list, so the confirmation is not read as a new message).
    function liveEl() { return ctx.copyLiveEl; }
    // Code-block copy confirmations announce in the same shared node.
    // Charts draw from ```chart blocks in assistant replies only (M35 F1 L2, DD6).
    function drawChart(source, meta) {
      return App.ui.chart.block(source, { closed: meta.closed, testid: 'chat-chart', onLayout: onChartLayout });
    }

    // Widgets draw from ```widget blocks in assistant replies only (M35 F2 L6, DD1, DD7, DD9).
    // The attribution name of the reply being rendered: a history replay sets it (null for no
    // agent); live replies use the chat's agent.
    var historyAgent;
    function widgetAgentName() {
      if (historyAgent !== undefined) return historyAgent;
      return state.currentAgentName || null;
    }
    // FNV-1a over UTF-16 code units, 8 hex digits: a short, stable, non-cryptographic key part.
    function fnv1a(s) {
      var h = 0x811c9dc5;
      for (var i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i);
        h = Math.imul(h, 0x01000193) >>> 0;
      }
      return ('00000000' + h.toString(16)).slice(-8);
    }
    // Every handle drawWidget returned, so clearLog can destroy a card that was built in a
    // fragment and cleared before it was ever connected (sweep() alone would miss it).
    var widgetHandles = [];
    // hash -> how many CLOSED widgets with that source this log has drawn (resets in clearLog).
    var widgetSeen = Object.create(null);
    // INVARIANT: drawWidget is never called from a render whose fragment is thrown away. Every
    // text is rendered once, by the turn-work module (narration when its group opens, the reply
    // when it lands), so the counter below stays equal between a live reply and its reload.
    function drawWidget(source, meta) {
      var hash = fnv1a(source);
      var n = widgetSeen[hash] || 0;
      var closed = meta.closed !== false;
      var sid = ctx.chatState.boundId() || ctx.chatState.activeId() || '';
      var handle = App.ui.widget({
        source: source,
        closed: closed,
        agentName: widgetAgentName(),
        testid: 'chat-widget',
        key: sid + ':' + hash + ':' + n
      });
      if (closed) widgetSeen[hash] = n + 1;
      if (!handle) return null;
      widgetHandles.push(handle);
      return handle.el;
    }
    function mdOpts() {
      return { copyLiveEl: ctx.copyLiveEl, codeBlockRenderers: { chart: drawChart, widget: drawWidget } };
    }
    // The markdown fragment for a turn's narration (charts and widgets draw through the
    // transcript, so the widget key counter stays here).
    function renderMarkdown(text) {
      return App.markdown.render(text, mdOpts());
    }

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
      // Sampled BEFORE the insert: a chart can add more than the pin threshold at once.
      var wasPinned = isPinned();
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
        marker: opts.marker || null,
        testid: 'message'
      });
      if (opts.routineId) msg.el.setAttribute('data-routine-id', String(opts.routineId));
      // The proposal cards stop their placement walk at a user bubble (M36 F2 L6).
      if (role === 'user') msg.el.setAttribute('data-role', 'user');
      if (role === 'user') dropContinue();
      // M36 F3 L4: the page line is a sibling above the bubble, never inside it.
      if (opts.pageLine) addPageChip(null, opts.pageLine);
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
      if (wasPinned) messagesEl.scrollTop = messagesEl.scrollHeight;
      else scrollToBottomIfPinned();
      App.perf.mark('addMsg:end');
      App.perf.measure('addMsg', 'addMsg:start', 'addMsg:end');
      return msg.el;
    }

    // The quiet page line (App.ui.message.context). With a `bubble` already in the log it goes
    // right before it (the sender's own bubble, whose line the server sends back as
    // `page_line`); with none it is appended (addMsg then appends the bubble after it).
    // M36 F4 L1b: the stored line ends with the page's route for the model, " (#library/mcp/~new)";
    // the operator sees only the label, so the one trailing route suffix is dropped here (every
    // chip, live or replayed, is built by this function). A route holds no whitespace.
    function addPageChip(bubble, line) {
      if (typeof line !== 'string') return;
      line = line.replace(/ \(#\S*\)$/, '');
      if (!line) return;
      var chip = App.ui.message.context({ text: line, testid: 'message-context' });
      if (bubble && bubble.parentNode === messagesEl) messagesEl.insertBefore(chip.el, bubble);
      else if (!bubble) messagesEl.appendChild(chip.el);
      else return;
      scrollToBottomIfPinned();
    }

    // The one place a user event becomes a bubble (live frame and history replay). A routine
    // run's message is the routine's: its name as the attribution, a "Routine" chip, no
    // source prefix. Any other non-web source keeps the "[source] " prefix.
    function addUserEvent(ev, extra) {
      extra = extra || {};
      var opts = { ts: extra.ts, visibility: ev.visibility, peerName: ev.peer_name };
      if (ev.page && typeof ev.page.line === 'string') opts.pageLine = ev.page.line;
      if (!Object.prototype.hasOwnProperty.call(extra, 'ts')) delete opts.ts;
      // M36 F2 L6 (DD8, board option B): an approval is the quiet line, never a bubble (the text
      // the model sees is not shown); a dismissal draws nothing (the card's Dismissed line says
      // it). Checked before the routine marker.
      if (ev.proposal_event) {
        if (ev.proposal_event === 'dismissed') return;
        dropContinue();
        messagesEl.appendChild(App.ui.notice({
          tone: 'muted',
          body: ev.proposal_event === 'approved'
            ? 'You approved this change. GleepGlorp is continuing.'
            : 'You approved this change.',
          testid: 'chat-approval-line'
        }).el);
        scrollToBottomIfPinned();
        return;
      }
      if (ev.routine_name) {
        opts.marker = { label: 'Routine' };
        opts.routineId = ev.routine_id;
        addMsg('user', ev.content, String(ev.routine_name), opts);
        return;
      }
      var cls = ev.source === 'api' ? 'user api' : 'user';
      var prefixed = ev.source && ev.source !== 'web' && !(extra.history && ev.source === 'restored') &&
        ev.proposal_id == null;
      addMsg(cls, (prefixed ? '[' + ev.source + '] ' : '') + ev.content, ev.peer_name || 'You', opts);
    }

    // The one log wipe (DD11 4): every handle the old log held is dropped, then the log is
    // emptied. The three wipe sites (a pending chat, a deleted chat, a history replay) call it.
    function clearLog() {
      state.pendingPageBubble = null;
      dropContinue();
      dropModelLoading();
      if (ctx.turnWork) ctx.turnWork.reset();
      // The proposal cards go with the log; their state stays for redraw() (M36 F2 L6).
      if (ctx.proposalCards) ctx.proposalCards.clear();
      if (ctx.fillReceipts) ctx.fillReceipts.clear();
      pinnedFlag = true;
      // Widgets (M35 F2 L6, DD7): destroy every card this log drew, then wipe, then sweep as a
      // backstop for a card that was connected once and detached by something else.
      var cards = widgetHandles;
      widgetHandles = [];
      widgetSeen = Object.create(null);
      for (var w = 0; w < cards.length; w++) {
        try { cards[w].destroy(); } catch (e) { /* defensive: one card never blocks the wipe */ }
      }
      messagesEl.replaceChildren();
      App.ui.widget.sweep();
    }

    // `opts.trailing` ('closed' default, 'working' or 'sign-in') says how the last turn
    // renders (App.chat.turnWork.replay); the turn grouping lives there.
    function renderHistory(history, agentName, opts) {
      messagesEl.setAttribute('aria-busy', 'true');
      // The turn groups and the model-loading line from the conversation the log showed
      // before are dropped with the wipe.
      clearLog();
      var agentLabel = agentName || 'agent';
      historyAgent = agentName || null;
      try {
        ctx.turnWork.replay(history, agentLabel, {
          trailing: opts && opts.trailing,
          agentName: agentName
        });
      } finally { historyAgent = undefined; }
      // The proposal cards the chat already holds are drawn again, in place (M36 F2 L6).
      if (ctx.proposalCards) ctx.proposalCards.redraw();
      if (ctx.fillReceipts) ctx.fillReceipts.redraw();
      messagesEl.removeAttribute('aria-busy');
    }

    // The "Loading model" line: a system-toned thinking handle kept here, settled in place by
    // "Model loaded." (never found by a class query) and dropped on any log wipe or turn end.
    var loadingHandle = null;
    function showModelLoading() {
      // An empty running work line gives way to this line (a group with items stays).
      ctx.turnWork.hideForLoading();
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
    // collapsing into the turn's work group like before. Excludes
    // error results defensively (an error never actually reached a
    // platform-send success, but the visibility tag alone shouldn't be the
    // only guard against surfacing an error as if it were delivered).
    function isDeliveredToolResult(ev) {
      return !!state.currentSessionPlatform && !ev.is_error && ev.visibility !== 'operator';
    }

    // Renders a delivered (peer-visible) tool-result as a top-level bubble
    // — outside the turn's work group — with the same agent
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

    function addDiscardedNotice(n) {
      messagesEl.appendChild(App.ui.notice({
        tone: 'muted',
        body: n > 1 ? n + ' queued messages discarded.' : 'Queued message discarded.',
        testid: 'chat-discarded'
      }).el);
      scrollToBottomIfPinned();
    }

    // DD8 F2: the agent ran out of steps. A muted line after the reply, never stored (a re-join
    // renders none). "Max iterations" links to the agent's settings only when the agent has a
    // stored record (the default agent and a deleted agent get plain text).
    // L10d: a live Continue button follows the notice (web chats only) unless the composer is
    // blocked or the hold queue is non-empty (it drains at once). One live handle at a time.
    var liveContinue = null;
    function dropContinue() {
      if (liveContinue && liveContinue.wrap.parentNode) liveContinue.wrap.parentNode.removeChild(liveContinue.wrap);
      liveContinue = null;
    }
    function setContinueEnabled(enabled) {
      if (liveContinue && !liveContinue.busy) liveContinue.btn.disabled = !enabled;
    }
    function buildContinue() {
      var wrap = document.createElement('span');
      wrap.className = 'chat-step-limit-actions';
      var btn = App.ui.button({
        variant: 'secondary', size: 'sm', label: 'Continue', testid: 'chat-step-limit-continue',
        onClick: function () {
          if (!liveContinue || liveContinue.busy) return;
          var mine = liveContinue;
          mine.busy = true;
          btn.disabled = true;
          var ok = ctx.send.sendText('continue');
          if (ok) {
            if (liveContinue === mine) dropContinue();
            ctx.composer.focus();
          } else {
            mine.busy = false;
            btn.disabled = !!(state.bannerActive || ctx.composer.input.disabled);
          }
        }
      });
      wrap.appendChild(btn);
      liveContinue = { wrap: wrap, btn: btn, busy: false };
      return wrap;
    }

    function addStepLimitNotice(steps, agentName) {
      dropContinue();
      var n = Number(steps);
      var used = n >= 1 ? 'used its ' + n + ' steps' : 'reached its step limit';
      // M36 F1 L04: through App.chat.agentKind; GleepGlorp's link goes to its settings page.
      var kindInfo = agentName ? App.chat.agentKind(agentName) : { kind: 'unknown' };
      var hasRecord = kindInfo.kind === 'agent' || kindInfo.kind === 'gleepglorp';
      var sid = ctx.chatState.activeId();
      var canContinue = !state.bannerActive && !ctx.composer.input.disabled && !!sid &&
        ctx.holdQueue.count(sid) === 0;
      var body = document.createDocumentFragment();
      body.appendChild(document.createTextNode('Stopped: this agent ' + used + ' for this message. ' +
        (canContinue ? 'Click Continue or raise ' : 'Send another message to continue, or raise ')));
      if (hasRecord) {
        var link = document.createElement('a');
        link.href = kindInfo.settingsHref;
        link.textContent = 'max iterations';
        link.setAttribute('data-testid', 'chat-step-limit-link');
        body.appendChild(link);
      } else {
        body.appendChild(document.createTextNode('max iterations'));
      }
      body.appendChild(document.createTextNode(' in its settings.'));
      if (canContinue) body.appendChild(buildContinue());
      messagesEl.appendChild(App.ui.notice({ tone: 'muted', body: body, testid: 'chat-step-limit' }).el);
      scrollToBottomIfPinned();
    }

    return {
      SCROLL_PIN_THRESHOLD: SCROLL_PIN_THRESHOLD,
      addMsg: addMsg,
      addPageChip: addPageChip,
      addUserEvent: addUserEvent,
      scrollToBottomIfPinned: scrollToBottomIfPinned,
      clearLog: clearLog,
      destroy: destroy,
      renderHistory: renderHistory,
      renderMarkdown: renderMarkdown,
      showModelLoading: showModelLoading,
      settleModelLoading: settleModelLoading,
      dropModelLoading: dropModelLoading,
      buildToolMsg: buildToolMsg,
      isDeliveredToolResult: isDeliveredToolResult,
      appendDeliveredToolMsg: appendDeliveredToolMsg,
      isAgentError: isAgentError,
      addAgentError: addAgentError,
      addStoppedNotice: addStoppedNotice,
      addDiscardedNotice: addDiscardedNotice,
      addStepLimitNotice: addStepLimitNotice,
      setContinueEnabled: setContinueEnabled,
      cssEscape: cssEscape
    };
  }

  window.App.chat.transcript = { create: create };
})();
