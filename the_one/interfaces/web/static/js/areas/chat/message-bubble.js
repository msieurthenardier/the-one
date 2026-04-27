(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // First-token whitespace split — matches 'assistant' exactly without
  // accidentally matching dash-prefixed variants like 'assistant-error'.
  // Composite cls strings ('assistant model-loading thinking') match too;
  // the thinking indicator is built via App.chat.createThinking() rather
  // than this path so it never reaches us.
  function shouldRenderAsMarkdown(cls, opts) {
    var firstToken = cls.split(' ')[0];
    return firstToken === 'assistant' && (!opts || opts.renderMarkdown !== false);
  }

  // Builds a chat message bubble: <div class="msg {cls}" data-testid="message">{rendered}</div>.
  // Assistant messages render via the markdown library by default; user,
  // tool, and system messages render via textContent. Pass
  // { renderMarkdown: false } to force textContent for assistant — used
  // by the streaming-accumulation path so chunks append as plain text;
  // finalizeStreamingBubble swaps the buffer for markdown on `done`.
  function renderMessage(cls, text, opts) {
    opts = opts || {};
    var el = document.createElement('div');
    el.className = 'msg ' + cls;
    el.setAttribute('data-testid', 'message');
    if (shouldRenderAsMarkdown(cls, opts)) {
      el.appendChild(App.markdown.render(text));
    } else {
      el.textContent = text;
    }
    return el;
  }

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

  // Builds an attribution label: <div class="msg-attribution {side}">{text}<span class="msg-attribution-ts">{ts}</span></div>.
  // side is 'from-you' (user) or 'from-agent' (everything else). ts is an
  // optional ISO 8601 timestamp string; if present, it renders as a UTC time
  // suffix. Per-session timezone preference belongs in a future settings flight.
  function renderAttribution(side, text, ts) {
    var el = document.createElement('div');
    el.className = 'msg-attribution ' + side;
    el.textContent = text;
    var formatted = fmtTs(ts);
    if (formatted) {
      el.appendChild(document.createTextNode(' · '));
      var tsEl = document.createElement('span');
      tsEl.className = 'msg-attribution-ts';
      tsEl.textContent = formatted;
      el.appendChild(tsEl);
    }
    return el;
  }

  window.App.chat.renderMessage = renderMessage;
  window.App.chat.renderAttribution = renderAttribution;
})();
