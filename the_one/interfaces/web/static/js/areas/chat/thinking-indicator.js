(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // Builds the thinking placeholder as a .toolcall.open block.
  // The .dot.live span pulses via CSS (components.css) — no JS animation
  // timer needed. removeThinking is still idempotent (no _dotTimer to clear).
  function createThinking() {
    var el = document.createElement('div');
    el.className = 'toolcall open';
    el.setAttribute('data-testid', 'thinking-indicator');

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
    nameEl.textContent = 'Thinking…';
    header.appendChild(nameEl);

    var statusEl = document.createElement('span');
    statusEl.className = 'toolcall-status';
    var dotEl = document.createElement('span');
    dotEl.className = 'dot live';
    statusEl.appendChild(dotEl);
    header.appendChild(statusEl);

    el.appendChild(header);
    return el;
  }

  // Idempotent: no-op if el is null/undefined; otherwise removes the element.
  // No _dotTimer to clear (CSS-driven animation replaced JS setInterval).
  function removeThinking(el) {
    if (!el) return;
    if (el.parentNode) el.parentNode.removeChild(el);
  }

  window.App.chat.createThinking = createThinking;
  window.App.chat.removeThinking = removeThinking;
})();
