(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // Format an ISO timestamp as "HH:MM:SS UTC". Returns "" for falsy input.
  function fmtTs(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    var hh = String(d.getUTCHours()).padStart(2, '0');
    var mm = String(d.getUTCMinutes()).padStart(2, '0');
    var ss = String(d.getUTCSeconds()).padStart(2, '0');
    return hh + ':' + mm + ':' + ss + ' UTC';
  }

  // Renders a user message row.
  // <div class="msg-row user" data-testid="message">
  //   <div class="msg-body">
  //     <div class="msg-text">{text}</div>
  //     <div class="msg-meta" style="justify-content:flex-end"><span class="msg-time">{ts}</span></div>
  //   </div>
  // </div>
  function renderUserMessage(text, ts) {
    var row = document.createElement('div');
    row.className = 'msg-row user';
    row.setAttribute('data-testid', 'message');

    var body = document.createElement('div');
    body.className = 'msg-body';

    var textEl = document.createElement('div');
    textEl.className = 'msg-text';
    textEl.textContent = text;
    body.appendChild(textEl);

    var formatted = fmtTs(ts);
    if (formatted) {
      var meta = document.createElement('div');
      meta.className = 'msg-meta';
      meta.style.justifyContent = 'flex-end';
      var timeEl = document.createElement('span');
      timeEl.className = 'msg-time';
      timeEl.textContent = formatted;
      meta.appendChild(timeEl);
      body.appendChild(meta);
    }

    row.appendChild(body);
    return row;
  }

  // Renders an agent message row. Returns an object { row, msgText } so the
  // streaming-pacing path can hold a reference to the .msg-text div directly.
  //
  // <div class="msg-row" data-testid="message">
  //   <div class="agent-avatar">{first2}</div>
  //   <div class="msg-body">
  //     <div class="msg-meta"><span class="msg-author">{name}</span><span class="msg-time">{ts}</span></div>
  //     <div class="msg-text">{markdown OR text OR empty}</div>
  //   </div>
  // </div>
  //
  // opts.renderMarkdown (default true) — pass false for streaming accumulation
  // path so chunks append as plain text; finalizeStreamingBubble swaps on done.
  function renderAgentMessage(text, agentName, ts, opts) {
    opts = opts || {};
    var name = agentName || 'agent';

    var row = document.createElement('div');
    row.className = 'msg-row';
    row.setAttribute('data-testid', 'message');

    var avatar = document.createElement('div');
    avatar.className = 'agent-avatar';
    avatar.textContent = name.slice(0, 2).toUpperCase();
    row.appendChild(avatar);

    var body = document.createElement('div');
    body.className = 'msg-body';

    var meta = document.createElement('div');
    meta.className = 'msg-meta';
    var authorEl = document.createElement('span');
    authorEl.className = 'msg-author';
    authorEl.textContent = name;
    meta.appendChild(authorEl);
    var formatted = fmtTs(ts);
    if (formatted) {
      var timeEl = document.createElement('span');
      timeEl.className = 'msg-time';
      timeEl.textContent = formatted;
      meta.appendChild(timeEl);
    }
    body.appendChild(meta);

    var msgText = document.createElement('div');
    msgText.className = 'msg-text';
    if (opts.renderMarkdown !== false && text) {
      msgText.appendChild(App.markdown.render(text));
    } else {
      // Streaming path: seed with an empty text node for the pacing ticker
      // to mutate (commitSafeBoundary / pacingTick read lastChild as text node).
      msgText.appendChild(document.createTextNode(text || ''));
    }
    body.appendChild(msgText);
    row.appendChild(body);

    return { row: row, msgText: msgText };
  }

  // Renders a tool call as a collapsible .toolcall block.
  //
  // status values: 'running' (live), 'done', 'error', or null/undefined.
  // args can be an object (arguments dict) or a string.
  function renderToolCall(name, args, status) {
    var el = document.createElement('div');
    el.className = 'toolcall';
    el.setAttribute('data-testid', 'toolcall');

    var header = document.createElement('div');
    header.className = 'toolcall-header';

    var chevronSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chevronSvg.setAttribute('class', 'icn toolcall-chevron');
    chevronSvg.setAttribute('viewBox', '0 0 16 16');
    chevronSvg.setAttribute('aria-hidden', 'true');
    var chevronPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    chevronPath.setAttribute('d', 'M6 4l4 4-4 4');
    chevronPath.setAttribute('stroke', 'currentColor');
    chevronPath.setAttribute('stroke-width', '1.6');
    chevronPath.setAttribute('fill', 'none');
    chevronPath.setAttribute('stroke-linecap', 'round');
    chevronSvg.appendChild(chevronPath);
    header.appendChild(chevronSvg);

    var nameEl = document.createElement('span');
    nameEl.className = 'toolcall-name';
    nameEl.textContent = name || 'tool';
    header.appendChild(nameEl);

    // Args preview as summary.
    var summary = '';
    if (args && typeof args === 'object') {
      var keys = Object.keys(args);
      if (keys.length > 0) {
        summary = keys.slice(0, 2).map(function (k) { return k + '=' + JSON.stringify(args[k]); }).join(', ');
        if (keys.length > 2) summary += ', …';
      }
    } else if (typeof args === 'string' && args) {
      summary = args.length > 60 ? args.slice(0, 60) + '…' : args;
    }
    if (summary) {
      var summaryEl = document.createElement('span');
      summaryEl.className = 'toolcall-summary';
      summaryEl.textContent = summary;
      header.appendChild(summaryEl);
    }

    if (status) {
      var statusEl = document.createElement('span');
      statusEl.className = 'toolcall-status';
      var dot = document.createElement('span');
      dot.className = 'dot' + (status === 'running' ? ' live' : status === 'error' ? ' warn' : ' idle');
      statusEl.appendChild(dot);
      var statusText = document.createElement('span');
      statusText.textContent = status;
      statusEl.appendChild(statusText);
      header.appendChild(statusEl);
    }

    el.appendChild(header);

    // Args body (collapsed by default; click header to expand).
    if (args !== null && args !== undefined) {
      var bodyEl = document.createElement('div');
      bodyEl.className = 'toolcall-body';
      var section = document.createElement('div');
      section.className = 'toolcall-section';
      var labelEl = document.createElement('div');
      labelEl.className = 'toolcall-section-label';
      labelEl.textContent = 'Args';
      section.appendChild(labelEl);
      var contentEl = document.createElement('div');
      contentEl.className = 'toolcall-content';
      var argsStr = typeof args === 'object' ? JSON.stringify(args, null, 2) : String(args);
      contentEl.textContent = argsStr;
      section.appendChild(contentEl);
      bodyEl.appendChild(section);
      el.appendChild(bodyEl);
    }

    // Toggle .open on header click.
    header.addEventListener('click', function () {
      el.classList.toggle('open');
    });

    return el;
  }

  // Renders a tool result as a .toolcall.open block with "Result" label.
  function renderToolResult(resultContent, isError) {
    var el = document.createElement('div');
    el.className = 'toolcall open';
    el.setAttribute('data-testid', 'toolcall');

    var header = document.createElement('div');
    header.className = 'toolcall-header';

    var chevronSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chevronSvg.setAttribute('class', 'icn toolcall-chevron');
    chevronSvg.setAttribute('viewBox', '0 0 16 16');
    chevronSvg.setAttribute('aria-hidden', 'true');
    var chevronPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    chevronPath.setAttribute('d', 'M6 4l4 4-4 4');
    chevronPath.setAttribute('stroke', 'currentColor');
    chevronPath.setAttribute('stroke-width', '1.6');
    chevronPath.setAttribute('fill', 'none');
    chevronPath.setAttribute('stroke-linecap', 'round');
    chevronSvg.appendChild(chevronPath);
    header.appendChild(chevronSvg);

    var nameEl = document.createElement('span');
    nameEl.className = 'toolcall-name';
    nameEl.textContent = 'Result';
    header.appendChild(nameEl);

    if (isError) {
      var statusEl = document.createElement('span');
      statusEl.className = 'toolcall-status';
      var dot = document.createElement('span');
      dot.className = 'dot warn';
      statusEl.appendChild(dot);
      var statusText = document.createElement('span');
      statusText.textContent = 'error';
      statusEl.appendChild(statusText);
      header.appendChild(statusEl);
    }

    el.appendChild(header);

    var bodyEl = document.createElement('div');
    bodyEl.className = 'toolcall-body';
    var section = document.createElement('div');
    section.className = 'toolcall-section';
    var contentEl = document.createElement('div');
    contentEl.className = 'toolcall-content';
    contentEl.textContent = resultContent || '';
    section.appendChild(contentEl);
    bodyEl.appendChild(section);
    el.appendChild(bodyEl);

    header.addEventListener('click', function () {
      el.classList.toggle('open');
    });

    return el;
  }

  // Renders a system message as a compact .toolcall variant (always closed).
  function renderSystemMessage(text) {
    var el = document.createElement('div');
    el.className = 'toolcall';
    el.setAttribute('data-testid', 'message');
    el.setAttribute('data-system-msg', '');

    var header = document.createElement('div');
    header.className = 'toolcall-header';

    var nameEl = document.createElement('span');
    nameEl.className = 'toolcall-name';
    nameEl.textContent = 'System';
    header.appendChild(nameEl);

    var summaryEl = document.createElement('span');
    summaryEl.className = 'toolcall-summary';
    summaryEl.textContent = text || '';
    header.appendChild(summaryEl);

    el.appendChild(header);
    return el;
  }

  // Legacy compatibility wrappers used by the history-restore path in chat.js.
  // These route to the new render functions based on the CSS class string
  // that the old code passed.  The streaming-accumulation path uses
  // renderAgentMessage() directly.

  // renderMessage(cls, text, opts) — kept as a router for the addMsg() path.
  // cls is the old-style string: 'user', 'user api', 'assistant', 'tool',
  // 'tool error', 'system'.
  // Returns the DOM element (row or toolcall).
  function renderMessage(cls, text, opts) {
    opts = opts || {};
    var firstToken = cls.split(' ')[0];
    if (firstToken === 'user') {
      var ts = opts.ts || null;
      return renderUserMessage(text, ts);
    }
    if (firstToken === 'assistant') {
      var result = renderAgentMessage(text, opts.agentName || null, opts.ts || null, opts);
      return result.row;
    }
    if (firstToken === 'tool') {
      var isError = cls.indexOf('error') !== -1;
      return renderToolResult(text, isError);
    }
    if (firstToken === 'system') {
      return renderSystemMessage(text);
    }
    // Fallback: plain text block.
    var fallback = document.createElement('div');
    fallback.className = 'toolcall';
    fallback.setAttribute('data-testid', 'message');
    var h = document.createElement('div');
    h.className = 'toolcall-header';
    var n = document.createElement('span');
    n.className = 'toolcall-name';
    n.textContent = cls;
    var s = document.createElement('span');
    s.className = 'toolcall-summary';
    s.textContent = text;
    h.appendChild(n);
    h.appendChild(s);
    fallback.appendChild(h);
    return fallback;
  }

  // renderAttribution() is now a no-op shim — Holograph embeds author/time
  // inside the .msg-body .msg-meta div. Returns null so callers that
  // conditionally appendChild can guard with a truthiness check.
  // In the updated chat.js addMsg() the attribution arg is ignored; this
  // shim exists only in case any residual caller still invokes it.
  function renderAttribution(/* side, text, ts */) {
    return null;
  }

  window.App.chat.fmtTs = fmtTs;
  window.App.chat.renderUserMessage = renderUserMessage;
  window.App.chat.renderAgentMessage = renderAgentMessage;
  window.App.chat.renderToolCall = renderToolCall;
  window.App.chat.renderToolResult = renderToolResult;
  window.App.chat.renderSystemMessage = renderSystemMessage;
  window.App.chat.renderMessage = renderMessage;
  window.App.chat.renderAttribution = renderAttribution;
})();
