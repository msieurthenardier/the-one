// App.chat.turnWork -- one work group per chat turn (Sortie 16 L02, flight DD2-DD9). The
// frames of a turn (text, thinking, tool calls and results) go into one App.ui.turnWork group;
// the reply is built by the transcript's addMsg when the turn ends. Live and replay share the
// rules below, so a reload shows what the live turn showed.
//
// Rules (see the flight artifact):
//  - Pending text is the current pass's text so far. It shows as the group's quiet preview.
//    A tool call (or the next text) folds it into the group as a narration item.
//  - The most recent narration stays plain text until it can no longer become the reply; every
//    text is rendered as markdown at most once, in turn order, and no rendered node is moved.
//  - At `done` (only from "working") the reply is the last non-empty text: the pending text,
//    else the latest narration (its item is removed and its source goes through addMsg).
//  - cancelled, a turn-ending system frame, step_limit and auth_required fold and set the state;
//    none builds a reply.
//  - Replay groups the stored events by turn. A closed trailing turn keeps its history so a
//    live frame that reaches it re-renders the turn open (ensureOpen, step 2).
//
// Exposes (all but create are called by other chat modules; names in the flight log):
//   begin, onText, onThinking, onToolCall, onToolResult, onDone, onCancelled, onSystemEnd,
//   onStepLimit, onAuthRequired, onAuthResolved, onUserEvent, stopClicked, dropEmpty,
//   hideForLoading, groupEl, replay, reset.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function hasText(s) {
    return /\S/.test(s || '');
  }

  function toolCallText(name, args) {
    var parts = Object.entries(args || {}).map(function (kv) {
      return kv[0] + '=' + JSON.stringify(kv[1]);
    });
    return '> ' + name + '(' + parts.join(', ') + ')';
  }

  // The word a fence line's info string names, lower-cased ('' when none).
  function fenceInfo(afterTicks) {
    return afterTicks.trim().split(/\s+/)[0].toLowerCase();
  }

  function phraseFor(info) {
    return info === 'chart' ? 'Drawing a chart' : info === 'widget' ? 'Building a widget' : '';
  }

  // An info word still being typed ("", "ch", "wid") that may become chart or widget.
  function mayBecomeVisual(info) {
    return info === '' || 'chart'.indexOf(info) === 0 || 'widget'.indexOf(info) === 0;
  }

  // The line with leading whitespace, blockquote markers, list markers and a task marker
  // removed, as the renderer unwraps quote and list-item content before parsing it again.
  function unwrapLine(s) {
    var pos = 0;
    var n = s.length;
    for (;;) {
      while (pos < n && /\s/.test(s.charAt(pos))) pos++;
      if (pos < n && s.charAt(pos) === '>') { pos++; continue; }
      // Markers are matched in place, with no length limit and no backtracking: a bullet or a
      // digit run then a dot (any number of digits), followed by whitespace; the whitespace
      // itself is skipped at the top of the next pass.
      var p = pos;
      var c = s.charAt(p);
      if (c === '-' || c === '*' || c === '+') {
        p++;
      } else {
        while (p < n && s.charAt(p) >= '0' && s.charAt(p) <= '9') p++;
        if (p > pos && s.charAt(p) === '.') p++;
        else p = pos;
      }
      if (p > pos && p < n && /\s/.test(s.charAt(p))) { pos = p; continue; }
      if (pos > 0 && c === '[' && pos + 2 < n && ' xX'.indexOf(s.charAt(pos + 1)) >= 0 &&
          s.charAt(pos + 2) === ']' &&
          (pos + 3 >= n || /\s/.test(s.charAt(pos + 3)))) {
        pos += 3;
        continue;
      }
      break;
    }
    return s.substring(pos);
  }

  // The preview text: the pending text with chart and widget source replaced by a fixed
  // phrase ("Drawing a chart" / "Building a widget"); raw source never shows. Line endings are
  // normalised as the renderer does. A fence at column 0 follows the renderer's rules (it
  // opens on a line starting with three backticks and closes only on a bare fence line). A
  // chart or widget fence found after quote or list markers or indentation hides everything
  // from there on, since its close is not tracked. Hiding too much is accepted; showing
  // source is not. While a chart or widget block is still open at the end, only its phrase is
  // returned. An unfinished opener on the last line is held back.
  function previewFor(text) {
    var lines = String(text == null ? '' : text).replace(/\r\n?/g, '\n').split('\n');
    var out = [];
    var lastPhrase = '';
    var mode = 0; // 0 text, 1 ordinary fence, 2 chart/widget fence, 3 nested chart/widget
    var last = lines.length - 1;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (mode === 3) continue;
      if (mode === 2) {
        if (/^```\s*$/.test(line)) mode = 0;
        continue;
      }
      if (mode === 1) {
        out.push(line);
        if (/^```\s*$/.test(line)) mode = 0;
        continue;
      }
      var top = line.substr(0, 3) === '```';
      var rest = top ? line : unwrapLine(line);
      if (rest.substr(0, 3) !== '```') { out.push(line); continue; }
      var info = fenceInfo(rest.substring(3));
      var phrase = phraseFor(info);
      if (phrase) {
        out.push(phrase);
        lastPhrase = phrase;
        mode = top ? 2 : 3;
        continue;
      }
      if (i === last && mayBecomeVisual(info)) break;
      out.push(line);
      if (top) mode = 1;
    }
    // Still inside a chart or widget block: only its phrase shows.
    if (mode >= 2) return lastPhrase;
    return out.join('\n');
  }

  function splitTurns(history) {
    var turns = [];
    var cur = null;
    for (var i = 0; i < history.length; i++) {
      var ev = history[i];
      if (ev.type === 'user') {
        cur = { events: [ev] };
        turns.push(cur);
      } else {
        if (!cur) {
          cur = { events: [] };
          turns.push(cur);
        }
        cur.events.push(ev);
      }
    }
    // The codec stores a message's text first, then its thinking; live it is the reverse.
    // Put a thinking event above the text of the same stored message.
    for (var t = 0; t < turns.length; t++) {
      var evs = turns[t].events;
      for (var j = 1; j < evs.length; j++) {
        if (evs[j].type === 'thinking' && evs[j - 1].type === 'assistant') {
          var tmp = evs[j - 1];
          evs[j - 1] = evs[j];
          evs[j] = tmp;
        }
      }
    }
    return turns;
  }

  function hasWork(turn) {
    for (var i = 0; i < turn.events.length; i++) {
      var ty = turn.events[i].type;
      if (ty === 'assistant' || ty === 'thinking' || ty === 'tool_call' || ty === 'tool_result') return true;
    }
    return false;
  }

  function create(ctx) {
    var state = ctx.state;
    var messagesEl = ctx.messagesEl;

    // Every group {h, latest, calls, state}; the open group of the running turn; the most
    // recent group (the sign-in block's anchor).
    var groups = [];
    var open = null;
    var lastGroup = null;
    var pending = '';
    var pendingVis = null;
    // The history of a trailing turn replay closed, kept so a live frame can reopen it.
    var keptHistory = null;
    var keptAgent = null;
    var closedMark = false;

    function transcript() { return ctx.transcript; }

    function makeGroup(stateName) {
      var h = App.ui.turnWork({
        testid: 'turn-work',
        previewTestid: 'turn-work-preview',
        state: stateName
      });
      var g = { h: h, latest: null, calls: 0, state: stateName };
      messagesEl.appendChild(h.el);
      groups.push(g);
      lastGroup = g;
      transcript().scrollToBottomIfPinned();
      return g;
    }

    function setGroupState(g, name) {
      g.state = name;
      g.h.setState(name);
    }

    function removeGroup(g) {
      var at = groups.indexOf(g);
      if (at !== -1) groups.splice(at, 1);
      if (lastGroup === g) lastGroup = null;
      if (open === g) open = null;
      g.h.destroy();
      if (g.h.el.parentNode) g.h.el.parentNode.removeChild(g.h.el);
    }

    function flagVis(g, vis) {
      if (vis === 'operator') g.h.setOperatorOnly(true);
    }

    // Render the latest narration in place, once (it can no longer become the reply).
    function renderLatest(g) {
      if (!g.latest) return;
      var item = g.latest.item;
      var src = g.latest.src;
      g.latest = null;
      item.setContent(transcript().renderMarkdown(src));
    }

    function fold(g) {
      if (hasText(pending)) {
        renderLatest(g);
        var item = g.h.add('narration', pending);
        g.latest = { item: item, src: pending, vis: pendingVis };
        flagVis(g, pendingVis);
      }
      pending = '';
      pendingVis = null;
      g.h.setPreview(null);
      transcript().scrollToBottomIfPinned();
    }

    // The one way a group is opened (see the leg's design): reuse the open group; reopen a
    // trailing turn replay closed; else create one at the end of the log.
    function ensureOpen(stateName) {
      if (open) {
        if (open.state === 'sign-in' && stateName === 'working') setGroupState(open, 'working');
        open.h.el.hidden = false;
        return open;
      }
      if (closedMark) {
        var hist = keptHistory;
        var agent = keptAgent;
        closedMark = false;
        keptHistory = null;
        transcript().renderHistory(hist, agent, { trailing: stateName });
        if (open) return open;
      }
      open = makeGroup(stateName);
      return open;
    }

    function begin() {
      var g = ensureOpen('working');
      if (g.h.isEmpty() && pending === '' && messagesEl.lastChild !== g.h.el) {
        messagesEl.appendChild(g.h.el);
      }
      transcript().scrollToBottomIfPinned();
    }

    function onText(data, whole) {
      var g = ensureOpen('working');
      if (whole) {
        fold(g);
        pending = data.content || '';
        pendingVis = data.visibility || null;
      } else {
        if (pending === '') pendingVis = data.visibility || null;
        pending += data.content || '';
      }
      g.h.setPreview(previewFor(pending));
      transcript().scrollToBottomIfPinned();
    }

    function onThinking(data) {
      var g = ensureOpen('working');
      g.h.add('thinking', data.content != null ? data.content : '');
      flagVis(g, data.visibility);
      transcript().scrollToBottomIfPinned();
    }

    function onToolCall(data) {
      var g = ensureOpen('working');
      fold(g);
      var row = transcript().buildToolMsg(toolCallText(data.name, data.arguments), false, data.tool_call_id);
      g.h.add('tool', row);
      g.calls += 1;
      g.h.setToolCalls(g.calls);
      g.h.setActivity(data.name);
      flagVis(g, data.visibility);
      transcript().scrollToBottomIfPinned();
    }

    function onToolResult(data) {
      if (transcript().isDeliveredToolResult(data)) {
        transcript().appendDeliveredToolMsg(data, state.currentAgentName || 'agent', new Date().toISOString());
        transcript().scrollToBottomIfPinned();
        return;
      }
      var g = ensureOpen('working');
      g.h.add('tool', transcript().buildToolMsg(data.content, data.is_error, data.tool_call_id));
      g.h.setActivity(null);
      flagVis(g, data.visibility);
      transcript().scrollToBottomIfPinned();
    }

    function onDone() {
      var g = open;
      if (!g) return;
      if (g.state === 'working') {
        var replyText = null;
        var vis = null;
        if (hasText(pending)) {
          renderLatest(g);
          replyText = pending;
          vis = pendingVis;
        } else if (g.latest) {
          replyText = g.latest.src;
          vis = g.latest.vis;
          g.latest.item.remove();
          g.latest = null;
        }
        pending = '';
        pendingVis = null;
        g.h.setPreview(null);
        g.h.setActivity(null);
        setGroupState(g, 'done');
        if (g.h.isEmpty()) removeGroup(g);
        if (replyText !== null) {
          transcript().addMsg('assistant', replyText, state.currentAgentName || 'agent', { visibility: vis });
        }
      }
      open = null;
    }

    function onCancelled() {
      var g = open;
      if (!g) return;
      fold(g);
      renderLatest(g);
      setGroupState(g, 'stopped');
      open = null;
    }

    function onSystemEnd() {
      var g = open;
      if (!g) return;
      fold(g);
      if (g.h.isEmpty()) {
        removeGroup(g);
      } else {
        renderLatest(g);
        setGroupState(g, 'error');
      }
      open = null;
    }

    function onStepLimit() {
      var g = open;
      if (!g) return;
      fold(g);
      renderLatest(g);
      setGroupState(g, 'step-limit');
    }

    function onAuthRequired() {
      var g = ensureOpen('sign-in');
      fold(g);
      setGroupState(g, 'sign-in');
      return g.h.el;
    }

    function onAuthResolved() {
      if (open && open.state === 'sign-in') setGroupState(open, 'working');
    }

    // A live user event (a frame, a local send, a start) closes any open turn.
    function onUserEvent() {
      var g = open;
      if (g) {
        fold(g);
        renderLatest(g);
        if (g.state === 'working') g.h.stopDots();
        open = null;
      }
      keptHistory = null;
      keptAgent = null;
      closedMark = false;
    }

    function stopClicked() {
      if (open) open.h.stopDots();
    }

    function dropEmpty() {
      if (open && open.h.isEmpty() && pending === '') removeGroup(open);
    }

    function hideForLoading() {
      if (open && open.h.isEmpty()) open.h.el.hidden = true;
    }

    function groupEl() {
      if (open) return open.h.el;
      return lastGroup ? lastGroup.h.el : null;
    }

    function renderTurn(events, trailing, label) {
      var live = trailing !== 'closed';
      var textIdx = -1;
      var i;
      for (i = events.length - 1; i >= 0; i--) {
        if (events[i].type === 'assistant' && hasText(events[i].content)) {
          textIdx = i;
          break;
        }
      }
      var g = null;
      function grp() {
        if (!g) g = makeGroup(live ? trailing : 'done');
        return g;
      }
      var replyOpts = null;
      for (i = 0; i < events.length; i++) {
        var ev = events[i];
        var histOpts = { ts: ev.ts || null, visibility: ev.visibility, peerName: ev.peer_name };
        if (ev.type === 'user') {
          transcript().addUserEvent(ev, { ts: histOpts.ts, history: true });
        } else if (ev.type === 'assistant') {
          if (!hasText(ev.content)) continue;
          if (i === textIdx && !live) {
            replyOpts = histOpts;
            continue;
          }
          var ga = grp();
          if (live && i === textIdx) {
            var plain = ga.h.add('narration', ev.content);
            ga.latest = { item: plain, src: ev.content, vis: ev.visibility || null };
          } else {
            ga.h.add('narration', transcript().renderMarkdown(ev.content));
          }
          flagVis(ga, ev.visibility);
        } else if (ev.type === 'thinking') {
          var gt = grp();
          gt.h.add('thinking', ev.content != null ? ev.content : '');
          flagVis(gt, ev.visibility);
        } else if (ev.type === 'tool_call') {
          var gc = grp();
          gc.h.add('tool', transcript().buildToolMsg(toolCallText(ev.name, ev.arguments), false, ev.tool_call_id));
          gc.calls += 1;
          flagVis(gc, ev.visibility);
        } else if (ev.type === 'tool_result') {
          if (transcript().isDeliveredToolResult(ev)) {
            transcript().appendDeliveredToolMsg(ev, label, ev.ts || null);
          } else {
            var gr = grp();
            gr.h.add('tool', transcript().buildToolMsg(ev.content, ev.is_error, ev.tool_call_id));
            flagVis(gr, ev.visibility);
          }
        } else if (ev.type === 'system' && ev.content !== 'Loading model...' && ev.content !== 'Model loaded.') {
          transcript().addMsg('system', ev.content, null, histOpts);
        }
      }
      if (live && !g) grp();
      if (g) g.h.setToolCalls(g.calls);
      if (live) open = g;
      if (!live && textIdx !== -1) {
        transcript().addMsg('assistant', events[textIdx].content, label, replyOpts);
      }
    }

    function replay(history, agentLabel, opts) {
      opts = opts || {};
      var trailing = opts.trailing || 'closed';
      keptHistory = null;
      keptAgent = null;
      closedMark = false;
      var turns = splitTurns(history || []);
      for (var t = 0; t < turns.length; t++) {
        var last = t === turns.length - 1;
        renderTurn(turns[t].events, last ? trailing : 'closed', agentLabel);
      }
      if (trailing === 'closed' && turns.length && hasWork(turns[turns.length - 1])) {
        keptHistory = history;
        keptAgent = opts.agentName;
        closedMark = true;
      }
    }

    function reset() {
      for (var i = 0; i < groups.length; i++) {
        try { groups[i].h.destroy(); } catch (e) { /* defensive: one group never blocks the wipe */ }
      }
      groups = [];
      open = null;
      lastGroup = null;
      pending = '';
      pendingVis = null;
      keptHistory = null;
      keptAgent = null;
      closedMark = false;
    }

    return {
      begin: begin,
      onText: onText,
      onThinking: onThinking,
      onToolCall: onToolCall,
      onToolResult: onToolResult,
      onDone: onDone,
      onCancelled: onCancelled,
      onSystemEnd: onSystemEnd,
      onStepLimit: onStepLimit,
      onAuthRequired: onAuthRequired,
      onAuthResolved: onAuthResolved,
      onUserEvent: onUserEvent,
      stopClicked: stopClicked,
      dropEmpty: dropEmpty,
      hideForLoading: hideForLoading,
      groupEl: groupEl,
      replay: replay,
      reset: reset,
      previewFor: previewFor
    };
  }

  window.App.chat.turnWork = { create: create };
})();
