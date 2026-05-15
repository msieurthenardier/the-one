// M10 — smooth integer counter animation. Honors prefers-reduced-motion.
// Cap update frequency at 4Hz so rapid telemetry changes don't stutter.
(function () {
  'use strict';

  var MIN_INTERVAL_MS = 250;
  var inflight = new WeakMap();

  function reducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function animate(node, target, durationMs) {
    if (!node) return;
    var startVal = parseInt(node.textContent, 10);
    if (isNaN(startVal)) startVal = 0;
    var endVal = parseInt(target, 10);
    if (isNaN(endVal)) {
      // Non-numeric target (e.g., '—'); jump.
      node.textContent = String(target);
      return;
    }
    if (reducedMotion()) {
      node.textContent = String(endVal);
      return;
    }
    if (startVal === endVal) return;

    var existing = inflight.get(node);
    if (existing) existing.stop = true;

    var startMs = performance.now();
    var d = durationMs || 240;
    var token = { stop: false, lastUpdate: 0 };
    inflight.set(node, token);

    function tick(now) {
      if (token.stop) return;
      var t = Math.min(1, (now - startMs) / d);
      var eased = 1 - Math.pow(1 - t, 3);  // easeOutCubic
      var v = Math.round(startVal + (endVal - startVal) * eased);
      var sinceLast = now - token.lastUpdate;
      if (sinceLast >= MIN_INTERVAL_MS || t === 1) {
        node.textContent = String(v);
        token.lastUpdate = now;
      }
      if (t < 1) {
        requestAnimationFrame(tick);
      } else {
        node.textContent = String(endVal);
        inflight.delete(node);
      }
    }
    requestAnimationFrame(tick);
  }

  window.LerpCounter = { animate: animate };
})();
