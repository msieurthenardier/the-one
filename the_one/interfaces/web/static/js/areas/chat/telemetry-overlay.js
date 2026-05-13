(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function fmtTokens(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
  }

  // Holograph replaces the floating telemetry overlay with a single inline
  // chip (#chat-ctx-chip) inside the composer. chat.js owns that chip update
  // directly via its updateCtxChip() helper. These three exports are kept as
  // no-ops so any stale caller sites don't throw; fmtTokens is still used
  // by chat.js for the chip text.
  function renderTelemetry() {
    return null;
  }

  function updateTelemetry(/* container, data */) {
    // No-op — Holograph chip update is inline in chat.js.
  }

  function resetTelemetry(/* container */) {
    // No-op — Holograph chip reset is inline in chat.js.
  }

  window.App.chat.fmtTokens = fmtTokens;
  window.App.chat.renderTelemetry = renderTelemetry;
  window.App.chat.updateTelemetry = updateTelemetry;
  window.App.chat.resetTelemetry = resetTelemetry;
})();
