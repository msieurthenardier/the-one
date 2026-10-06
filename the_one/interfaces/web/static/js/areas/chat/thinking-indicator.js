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
    // DOM-built (M25 F4 L4b; was a static innerHTML literal).
    var textEl = document.createElement('span');
    textEl.className = 'model-loading-text';
    textEl.textContent = 'thinking';
    var dotEl = document.createElement('span');
    dotEl.className = 'model-loading-dots';
    el.appendChild(textEl);
    el.appendChild(dotEl);
    var frameIdx = 0;
    // F2 Leg 2 (A.7): honor prefers-reduced-motion. The Braille spinner
    // is a continuous animation that users with motion sensitivities
    // should be able to disable. When reduce-motion is set, render a
    // single static "…" and skip the setInterval entirely. WCAG 2.3.3
    // (AAA) is judgment-call territory; we ship the gate because the
    // animation conveys no semantic content beyond "still working".
    var reduceMotion = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion) {
      dotEl.textContent = ' …';
    } else {
      el._dotTimer = setInterval(function () {
        frameIdx = (frameIdx + 1) % THINKING_FRAMES.length;
        dotEl.textContent = ' ' + THINKING_FRAMES[frameIdx];
      }, 120);
    }
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
