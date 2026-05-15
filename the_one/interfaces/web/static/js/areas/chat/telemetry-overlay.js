(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function fmtTokens(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
  }

  // Builds the chrome-free telemetry overlay (ghosted by default; hover/focus
  // expands details and lifts opacity to 1). Returns the .telemetry-overlay
  // container with all inner spans/divs. Mirrors the original innerHTML shape
  // verbatim so the F2/F3 CSS rules and a11y attributes stay valid.
  function renderTelemetry() {
    var overlay = document.createElement('div');
    overlay.className = 'telemetry-overlay';
    overlay.setAttribute('tabindex', '0');
    overlay.setAttribute('role', 'status');
    overlay.setAttribute('aria-label', 'Token usage');

    var summary = document.createElement('div');
    summary.className = 'telemetry-summary';

    var barWrap = document.createElement('div');
    barWrap.className = 'context-bar-wrap';
    var bar = document.createElement('div');
    bar.className = 'context-bar';
    barWrap.appendChild(bar);
    summary.appendChild(barWrap);

    var pctSpan = document.createElement('span');
    pctSpan.className = 'value t-ctx-pct';
    pctSpan.textContent = '0%';
    summary.appendChild(pctSpan);

    overlay.appendChild(summary);

    var details = document.createElement('div');
    details.className = 'telemetry-details';

    var rows = [
      { label: 'in:', cls: 't-in' },
      { label: 'out:', cls: 't-out' },
      { label: 'ctx:', cls: 't-ctx' },
      { label: 'max:', cls: 't-max' }
    ];
    for (var i = 0; i < rows.length; i++) {
      var row = document.createElement('span');
      row.className = 'telemetry';
      var labelEl = document.createElement('span');
      labelEl.className = 'label';
      labelEl.textContent = rows[i].label;
      row.appendChild(labelEl);
      row.appendChild(document.createTextNode(' '));
      var valueEl = document.createElement('span');
      valueEl.className = 'value ' + rows[i].cls;
      valueEl.textContent = '0';
      row.appendChild(valueEl);
      details.appendChild(row);
    }

    overlay.appendChild(details);
    return overlay;
  }

  function updateTelemetry(chromeContent, data) {
    App.perf.mark('telemetry-update:start');
    chromeContent.querySelector('.t-in').textContent = fmtTokens(data.input_tokens);
    chromeContent.querySelector('.t-out').textContent = fmtTokens(data.output_tokens);
    chromeContent.querySelector('.t-ctx').textContent = fmtTokens(data.context_tokens);
    chromeContent.querySelector('.t-max').textContent = fmtTokens(data.max_context_tokens || 0);
    var pct = data.max_context_tokens > 0
      ? Math.min(100, Math.round(data.context_tokens / data.max_context_tokens * 100))
      : 0;
    var stateClass = pct >= 90 ? 'crit' : pct >= 70 ? 'warn' : '';
    var pctEl = chromeContent.querySelector('.t-ctx-pct');
    pctEl.textContent = pct + '%';
    pctEl.className = 'value t-ctx-pct' + (stateClass ? ' ' + stateClass : '');
    var bar = chromeContent.querySelector('.context-bar');
    bar.style.width = pct + '%';
    bar.className = 'context-bar' + (stateClass ? ' ' + stateClass : '');
    App.perf.mark('telemetry-update:end');
    App.perf.measure('telemetry-update', 'telemetry-update:start', 'telemetry-update:end');
  }

  // Clear all displayed values back to zero / default. Called on session
  // switch so token counts from the previous session don't bleed across.
  function resetTelemetry(chromeContent) {
    chromeContent.querySelector('.t-in').textContent = '0';
    chromeContent.querySelector('.t-out').textContent = '0';
    chromeContent.querySelector('.t-ctx').textContent = '0';
    chromeContent.querySelector('.t-max').textContent = '0';
    var pctEl = chromeContent.querySelector('.t-ctx-pct');
    pctEl.textContent = '0%';
    pctEl.className = 'value t-ctx-pct';
    var bar = chromeContent.querySelector('.context-bar');
    bar.style.width = '0%';
    bar.className = 'context-bar';
  }

  window.App.chat.fmtTokens = fmtTokens;
  window.App.chat.renderTelemetry = renderTelemetry;
  window.App.chat.updateTelemetry = updateTelemetry;
  window.App.chat.resetTelemetry = resetTelemetry;
})();
