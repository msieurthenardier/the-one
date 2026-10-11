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
  //
  // M10 F05 L05: visibility distinction. When ``opts.visibility === 'operator'``,
  // the bubble gains the ``msg-operator-only`` class and a leading
  // ``<span class="msg-operator-only-label">[operator-only]</span>`` child.
  // The non-markdown text body switches from ``el.textContent = text`` (which
  // would wipe the prepended label) to ``el.appendChild(createTextNode(text))``
  // — DOM-API, XSS-equivalent. Bubbles without ``opts.visibility === 'operator'``
  // render byte-identically to today (no class, no label, no dataset, no DOM
  // shape change).
  function renderMessage(cls, text, opts) {
    opts = opts || {};
    var el = document.createElement('div');
    var fullCls = 'msg ' + cls;
    // M10 F05 L08 HAT: suppress the operator-only marker on the
    // operator's own user bubbles — the operator knows what they
    // typed and the marker is visual noise on their own messages.
    // The marker still applies to assistant / tool bubbles where it
    // signals "this reply / tool result is NOT visible to peers."
    // Class & label are skipped together; dataset still records the
    // visibility tag for DOM-shape assertions and future logic.
    var firstToken = cls.split(' ')[0];
    var isUserBubble = firstToken === 'user';
    var isOperatorOnly = opts.visibility === 'operator' && !isUserBubble;
    if (isOperatorOnly) {
      fullCls += ' msg-operator-only';
    }
    // M11 F06 L04: peer-attributed user bubble gets msg-from-peer for the
    // CSS left-align override (.area-chat .msg.user.msg-from-peer in chat.css,
    // declared after .area-chat .msg.user — same specificity, last-rule-wins).
    // Composes cleanly with visibility: peer-inbound users have visibility=None
    // by construction (the visibility tagger in llm/base.py skips Role.USER),
    // so isOperatorOnly above is false for peer bubbles.
    if (opts.peerName) {
      fullCls += ' msg-from-peer';
    }
    el.className = fullCls;
    el.setAttribute('data-testid', 'message');
    // Stash for DOM-shape assertions and future maintenance. Only set when
    // visibility is a truthy string, so non-tagged bubbles preserve the
    // pre-leg dataset-absent shape.
    if (opts.visibility) {
      el.dataset.visibility = opts.visibility;
    }
    if (isOperatorOnly) {
      var label = document.createElement('span');
      label.className = 'msg-operator-only-label';
      label.textContent = '[operator-only]';
      el.appendChild(label);
    }
    // M11 F06 L04 a11y follow-up: when the bubble represents a peer-attributed
    // user message, prepend a visually-hidden span that screen readers will
    // announce as "From {peerName}: " before the message text. Sighted users
    // already get the attribution via the left-aligned bubble + the
    // .msg-attribution.from-peer label below; assistive tech otherwise sees
    // only `<div class="msg user">{text}</div>`, which is semantically
    // indistinguishable from the operator's own user bubble (WCAG 1.3.3 /
    // 1.4.1 — color & position alone cannot convey meaning). Mirrors the
    // msg-operator-only-label idiom directly above. The .visually-hidden
    // utility class is defined in chat.css (sr-only pattern) so the span
    // takes no visual space.
    if (opts.peerName) {
      var peerLabel = document.createElement('span');
      peerLabel.className = 'msg-from-peer-label visually-hidden';
      peerLabel.textContent = 'From ' + opts.peerName + ': ';
      el.appendChild(peerLabel);
    }
    if (shouldRenderAsMarkdown(cls, opts)) {
      el.appendChild(App.markdown.render(text));
    } else if (isOperatorOnly || opts.peerName) {
      // Label was prepended — textContent assignment would wipe it.
      // Use appendChild(createTextNode(...)) which is XSS-equivalent
      // (DOM API, not innerHTML) but preserves the label. The peer-attributed
      // branch joins this path for the same reason: the visually-hidden
      // msg-from-peer-label was just prepended and must survive the body
      // append. Peer bubbles take the non-markdown branch (renderMessage's
      // markdown gating fires only for the 'assistant' first-token), so this
      // branch is the only one that handles peer-attributed text.
      el.appendChild(document.createTextNode(text));
    } else {
      el.textContent = text;
    }
    return el;
  }

  // Format an ISO timestamp as a 12-hour operator-zone clock time ("3:45 PM", DD14).
  // Returns "" for falsy or invalid input.
  function fmtTs(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    return window.App.time.formatClock(d);
  }

  // Builds an attribution label: <div class="msg-attribution {side}">{text}<span class="msg-attribution-ts">{ts}</span></div>.
  // side is 'from-you' (user) or 'from-agent' (everything else). ts is an
  // optional ISO 8601 timestamp string; if present, it renders as a local
  // 12-hour time suffix (no seconds).
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
      tsEl.setAttribute('data-ts', String(ts));
      el.appendChild(tsEl);
    }
    return el;
  }

  window.App.chat.renderMessage = renderMessage;
  window.App.chat.renderAttribution = renderAttribution;
})();
