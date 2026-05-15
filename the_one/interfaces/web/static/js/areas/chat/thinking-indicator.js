(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // L5.3 — Working-row indicator. Replaces the prior .toolcall thinking
  // block with a slim mono row carrying a pulsing accent dot, a WORKING
  // label, and an optional token-counter tail.
  //
  // state = { tokens_so_far, tokens_target } (both optional)
  function createThinking(state) {
    var el = document.createElement('div');
    el.className = 'working-row';
    el.setAttribute('data-testid', 'thinking-indicator');

    var dot = document.createElement('span');
    dot.className = 'stat-dot work';
    el.appendChild(dot);

    var labelEl = document.createElement('span');
    labelEl.className = 'working-label';
    labelEl.textContent = 'WORKING';
    el.appendChild(labelEl);

    var detail = document.createElement('span');
    detail.className = 'working-detail';
    var tokensPart = '';
    if (state && state.tokens_so_far != null && state.tokens_target != null) {
      tokensPart = ' · token ' + state.tokens_so_far + ' / ' + state.tokens_target;
    }
    detail.textContent = '— agent is responding' + tokensPart;
    el.appendChild(detail);

    return el;
  }

  // Update an existing working-row's token counter in place. Used by the
  // chat-area `usage` handler when streaming tokens land. No-op when el
  // is null or doesn't carry the working-detail tail.
  function updateThinking(el, state) {
    if (!el) return;
    var detail = el.querySelector('.working-detail');
    if (!detail) return;
    var tokensPart = '';
    if (state && state.tokens_so_far != null && state.tokens_target != null) {
      tokensPart = ' · token ' + state.tokens_so_far + ' / ' + state.tokens_target;
    }
    detail.textContent = '— agent is responding' + tokensPart;
  }

  // Idempotent: no-op if el is null/undefined; otherwise removes the element.
  // No _dotTimer to clear (CSS-driven animation replaced JS setInterval).
  function removeThinking(el) {
    if (!el) return;
    if (el.parentNode) el.parentNode.removeChild(el);
  }

  window.App.chat.createThinking = createThinking;
  window.App.chat.updateThinking = updateThinking;
  window.App.chat.removeThinking = removeThinking;
})();
