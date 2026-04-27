(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var THINKING_FRAMES = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];

  // Builds the thinking element (with data-testid="thinking-indicator"),
  // starts the dot-animation interval, and stores the interval id on the
  // element as `el._dotTimer` so removeThinking can clear it.
  function createThinking() {
    var el = document.createElement('div');
    el.className = 'msg assistant model-loading thinking';
    el.setAttribute('data-testid', 'thinking-indicator');
    el.innerHTML = '<span class="model-loading-text">thinking</span><span class="model-loading-dots"></span>';
    var dotEl = el.querySelector('.model-loading-dots');
    var frameIdx = 0;
    el._dotTimer = setInterval(function () {
      frameIdx = (frameIdx + 1) % THINKING_FRAMES.length;
      dotEl.textContent = ' ' + THINKING_FRAMES[frameIdx];
    }, 120);
    return el;
  }

  // Idempotent: no-op if el is null/undefined; otherwise clears the interval
  // and removes the element from its parent.
  function removeThinking(el) {
    if (!el) return;
    if (el._dotTimer) clearInterval(el._dotTimer);
    if (el.parentNode) el.parentNode.removeChild(el);
  }

  window.App.chat.createThinking = createThinking;
  window.App.chat.removeThinking = removeThinking;
})();
