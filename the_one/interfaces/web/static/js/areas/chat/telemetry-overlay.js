(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function fmtTokens(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
  }

  // Read the context-fullness thresholds plumbed from the backend via
  // /api/config → window.App.config (M16 F08 L05). Falls back to the 70/90
  // defaults when config is absent (old / failed config fetch) so the overlay
  // never crashes and degrades to the historical thresholds.
  function ctxThresholds() {
    var cfg = window.App.config || {};
    return {
      warn: cfg.context_warn_pct || 70,
      crit: cfg.context_crit_pct || 90
    };
  }

  // Map a percentage to its state class ('' / 'warn' / 'crit') using the
  // configured thresholds. Single derivation site for both update paths.
  function ctxStateClass(pct, t) {
    return pct >= t.crit ? 'crit' : pct >= t.warn ? 'warn' : '';
  }

  // Build the non-color a11y label for the overlay container. KEEPS the
  // "Token usage" prefix (structure-based locators depend on it) and appends
  // a state phrase perceivable without color at warn / crit.
  function ctxAriaLabel(pct, stateClass) {
    var label = 'Token usage: ' + pct + '% of context';
    if (stateClass === 'crit') return label + ', context nearly full';
    if (stateClass === 'warn') return label + ', approaching limit';
    return label;
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
      // F2 Leg 2 (A.8): mark per-row contents aria-hidden so the
      // container's aria-label="Token usage" is the only SR exposure.
      // Avoids polite-live re-announcing every token-count update
      // (which fires per server stream chunk). Sighted users see all
      // four values; SR users get the summary label on focus.
      row.setAttribute('aria-hidden', 'true');
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
    var stateClass = ctxStateClass(pct, ctxThresholds());
    var pctEl = chromeContent.querySelector('.t-ctx-pct');
    pctEl.textContent = pct + '%';
    pctEl.className = 'value t-ctx-pct' + (stateClass ? ' ' + stateClass : '');
    var bar = chromeContent.querySelector('.context-bar');
    bar.style.width = pct + '%';
    bar.className = 'context-bar' + (stateClass ? ' ' + stateClass : '');
    // Non-color a11y: make the container aria-label reflect pct + warn/crit
    // state so the threshold signal is perceivable without color (the bar
    // coloring is otherwise color-only). Detail rows stay aria-hidden.
    var overlayEl = chromeContent.querySelector('.telemetry-overlay');
    if (overlayEl) overlayEl.setAttribute('aria-label', ctxAriaLabel(pct, stateClass));
    // Retain raw input values so setTelemetryMax can recompute the bar
    // from retained context_tokens without re-parsing formatted DOM text.
    chromeContent.__telemetry = {
      input_tokens: data.input_tokens,
      output_tokens: data.output_tokens,
      context_tokens: data.context_tokens,
      max_context_tokens: data.max_context_tokens || 0,
    };
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
    // Reset the container aria-label to the baseline so a prior warn/crit
    // label (e.g. "Token usage: 85% of context, approaching limit") does not
    // persist across a session switch into a brand-new session with no usage.
    var overlayEl = chromeContent.querySelector('.telemetry-overlay');
    if (overlayEl) overlayEl.setAttribute('aria-label', ctxAriaLabel(0, ''));
    // Mirror the DOM reset in the retained raw state so setTelemetryMax
    // starts from zeros after a session switch.
    chromeContent.__telemetry = {
      input_tokens: 0,
      output_tokens: 0,
      context_tokens: 0,
      max_context_tokens: 0,
    };
  }

  // Update ONLY the max and recompute the context bar from the retained
  // raw context_tokens. Never touches .t-in / .t-out / .t-ctx so it
  // cannot clobber a synchronous last_usage restore (or a live usage event
  // that arrived before the /context-window seed resolved).
  function setTelemetryMax(chromeContent, maxContextTokens) {
    var t = chromeContent.__telemetry || {};
    var ctx = t.context_tokens || 0;
    chromeContent.querySelector('.t-max').textContent = fmtTokens(maxContextTokens || 0);
    var pct = maxContextTokens > 0
      ? Math.min(100, Math.round(ctx / maxContextTokens * 100))
      : 0;
    var stateClass = ctxStateClass(pct, ctxThresholds());
    var pctEl = chromeContent.querySelector('.t-ctx-pct');
    pctEl.textContent = pct + '%';
    pctEl.className = 'value t-ctx-pct' + (stateClass ? ' ' + stateClass : '');
    var bar = chromeContent.querySelector('.context-bar');
    bar.style.width = pct + '%';
    bar.className = 'context-bar' + (stateClass ? ' ' + stateClass : '');
    // Non-color a11y signal — mirror updateTelemetry so the aria-label stays
    // in sync after the async max-context resolution recomputes pct.
    var overlayEl = chromeContent.querySelector('.telemetry-overlay');
    if (overlayEl) overlayEl.setAttribute('aria-label', ctxAriaLabel(pct, stateClass));
    // Update retained max so subsequent setTelemetryMax calls stay consistent.
    if (chromeContent.__telemetry) {
      chromeContent.__telemetry.max_context_tokens = maxContextTokens || 0;
    }
  }

  window.App.chat.fmtTokens = fmtTokens;
  window.App.chat.renderTelemetry = renderTelemetry;
  window.App.chat.updateTelemetry = updateTelemetry;
  window.App.chat.resetTelemetry = resetTelemetry;
  window.App.chat.setTelemetryMax = setTelemetryMax;
})();
