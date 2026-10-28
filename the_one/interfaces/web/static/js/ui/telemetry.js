(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var DEFAULT_WARN = 70;
  var DEFAULT_CRIT = 90;
  var STATE_CLASS = {
    '': '',
    warn: ' ui-telemetry-pct--warn',
    crit: ' ui-telemetry-pct--crit'
  };
  var BAR_STATE_CLASS = {
    '': '',
    warn: ' ui-telemetry-bar--warn',
    crit: ' ui-telemetry-bar--crit'
  };

  function fmtTokens(n) {
    n = Number(n) || 0;
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
  }

  function stateOf(pct, t) {
    return pct >= t.crit ? 'crit' : pct >= t.warn ? 'warn' : '';
  }

  // The accessible name keeps the "Token usage" prefix and adds a state phrase that does
  // not depend on colour.
  function nameOf(pct, state) {
    var label = 'Token usage: ' + pct + '% of context';
    if (state === 'crit') return label + ', context nearly full';
    if (state === 'warn') return label + ', approaching limit';
    return label;
  }

  // App.ui.telemetry(opts) -> {el, update(data), setMax(n), reset(), destroy()}
  // (M31 F6 L04, DD4)
  //
  // The context-usage readout: a context bar and percentage, and on hover or focus the
  // in / out / ctx / max token counts. role=status, tabindex=0, resting opacity 0.7
  // (pinned by the contrast audit), lifted to 1 on hover or focus-within.
  //
  // opts:
  //   thresholds  {warn, crit} (percent) or a function returning it, read on every update
  //               (the caller's configuration may load after the control is built);
  //               default 70 / 90. A missing or zero value falls back to the default.
  //   testid      placed on the root (supplied by the caller)
  //
  // update(data) takes the server's usage frame: input_tokens, output_tokens,
  // context_tokens, max_context_tokens. setMax(n) touches only the maximum and the
  // percentage (the raw counts it keeps are what the percentage is recomputed from), so a
  // late-arriving context window never clobbers a restored count. reset() zeroes all of it.
  // The per-row values are aria-hidden: the root's name is the only announcement.
  // After destroy() every method is a no-op.
  App.ui.telemetry = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var gone = false;
    var raw = { input: 0, output: 0, context: 0, max: 0 };

    function thresholds() {
      var t = typeof opts.thresholds === 'function' ? opts.thresholds() : opts.thresholds;
      t = t || {};
      return { warn: t.warn || DEFAULT_WARN, crit: t.crit || DEFAULT_CRIT };
    }

    var bar = util.el('div', { className: 'ui-telemetry-bar' });
    var pctEl = util.el('span', { className: 'ui-telemetry-pct', text: '0%' });
    var summary = util.el('div', { className: 'ui-telemetry-summary' }, [
      util.el('div', { className: 'ui-telemetry-bar-wrap' }, [bar]),
      pctEl
    ]);
    var valueEls = {};
    var rowDefs = [['input', 'in:'], ['output', 'out:'], ['context', 'ctx:'], ['max', 'max:']];
    var rows = [];
    for (var i = 0; i < rowDefs.length; i++) {
      var valueEl = util.el('span', { className: 'ui-telemetry-value', text: '0' });
      valueEls[rowDefs[i][0]] = valueEl;
      rows.push(util.el('span', { className: 'ui-telemetry-row', 'aria-hidden': 'true' }, [
        util.el('span', { className: 'ui-telemetry-label', text: rowDefs[i][1] }),
        ' ',
        valueEl
      ]));
    }
    var root = util.el('div', {
      className: 'ui-telemetry',
      tabindex: '0',
      role: 'status',
      'aria-label': 'Token usage'
    }, [summary, util.el('div', { className: 'ui-telemetry-details' }, rows)]);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    function paint() {
      valueEls.input.textContent = fmtTokens(raw.input);
      valueEls.output.textContent = fmtTokens(raw.output);
      valueEls.context.textContent = fmtTokens(raw.context);
      valueEls.max.textContent = fmtTokens(raw.max);
      var pct = raw.max > 0 ? Math.min(100, Math.round(raw.context / raw.max * 100)) : 0;
      var state = stateOf(pct, thresholds());
      pctEl.textContent = pct + '%';
      pctEl.className = 'ui-telemetry-pct' + STATE_CLASS[state];
      bar.style.width = pct + '%';
      bar.className = 'ui-telemetry-bar' + BAR_STATE_CLASS[state];
      root.setAttribute('aria-label', nameOf(pct, state));
    }

    return {
      el: root,
      update: function (data) {
        if (gone || !data) return;
        raw = {
          input: Number(data.input_tokens) || 0,
          output: Number(data.output_tokens) || 0,
          context: Number(data.context_tokens) || 0,
          max: Number(data.max_context_tokens) || 0
        };
        paint();
      },
      setMax: function (n) {
        if (gone) return;
        raw.max = Number(n) || 0;
        paint();
      },
      reset: function () {
        if (gone) return;
        raw = { input: 0, output: 0, context: 0, max: 0 };
        paint();
      },
      destroy: function () { gone = true; }
    };
  };
  App.ui.telemetry.formatTokens = fmtTokens;
})();
