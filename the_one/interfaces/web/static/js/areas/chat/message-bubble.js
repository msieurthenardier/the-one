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

  // Builds an attribution label: <div class="msg-attribution {side}">{text}</div>.
  // side is 'from-you' (user) or 'from-agent' (everything else).
  function renderAttribution(side, text) {
    var el = document.createElement('div');
    el.className = 'msg-attribution ' + side;
    el.textContent = text;
    return el;
  }

  window.App.chat.renderMessage = renderMessage;
  window.App.chat.renderAttribution = renderAttribution;
})();
