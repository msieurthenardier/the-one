(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.chart (M35 F1 L1, flight DD2-DD5, DD7, DD9): the chart control. The format is
  // specified once in docs/chart-format.md, with the shared corpus in tests/fixtures/charts/;
  // the Python validator the_one/visuals/chart_spec.py is the second implementation of the
  // same document, and both are tested against the corpus with identical sentences.
  //
  //   App.ui.chart.parse(source) -> {ok: true, spec} | {ok: false, message}
  //   App.ui.chart.formatTick(value, unit) / formatFull(value, unit)   locale-neutral numbers
  //   App.ui.chart({spec, testid}) -> {el, destroy()}
  //   App.ui.chart.block(source, {closed, testid}) -> Node  (the chart, or the error notice)
  //
  // Since M35 F2 L2 the control is four files, loaded in this order: chart-parse.js (numbers
  // and validation), chart-scale.js (SVG and text helpers with measured text width, scales,
  // axes), chart-layout.js (the per-type layouts, the table, the summary) and this file (the
  // factory, tooltip, keyboard, live node, Show data, block). The first three are not controls:
  // they define no App.ui factory and share through the private App.ui.util.chartParts namespace.
  //
  // The chart builds its structure at once and lays out its SVG at the width it is given:
  // on its first ResizeObserver callback after attach, and again on width changes (coalesced
  // to one animation frame). Text is laid out at its true size and never scaled; axis text is
  // measured in the live SVG. All colour is CSS (ui-chart-series-N classes using
  // var(--chart-N)), so a theme change repaints with no JavaScript. No document listeners, no
  // timers.

  var P = App.ui.util.chartParts;
  var SVG_CLASS = P.SVG_CLASS;
  var HEIGHT = P.HEIGHT;
  var SPARK_W = P.SPARK_W;
  var SPARK_H = P.SPARK_H;
  var seriesClass = P.seriesClass;
  var svgEl = P.svgEl;
  var xText = P.xText;
  var seriesName = P.seriesName;
  var kindOf = P.kindOf;
  var summarise = P.summarise;
  var layoutCartesian = P.layoutCartesian;
  var layoutScatter = P.layoutScatter;
  var layoutPie = P.layoutPie;
  var layoutSpark = P.layoutSpark;
  var buildTable = P.buildTable;
  var annotationLines = P.annotationLines;
  var parse = P.parse;

  App.ui.chart = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var spec = opts.spec;
    if (!spec || !spec.series || !spec.series.length) throw new Error('App.ui.chart: a parsed spec is required');
    var testid = opts.testid || null;
    var isSpark = spec.type === 'sparkline';
    var isPie = spec.type === 'pie';
    var summary = summarise(spec);

    var figure = util.el('figure', {
      className: 'ui-chart' + (isSpark ? ' ui-chart--spark' : ''),
      'data-chart-type': spec.type
    });
    if (testid) figure.setAttribute('data-testid', testid);

    // caption: title and legend
    var caption = util.el('figcaption', { className: 'ui-chart-caption' });
    if (spec.title) caption.appendChild(util.el('div', { className: 'ui-chart-title', text: spec.title }));
    var legendItems = [];
    var si;
    if (!isSpark) {
      if (isPie) {
        for (si = 0; si < spec.x.values.length; si++) {
          legendItems.push({ name: xText(spec.x.values[si]), cls: seriesClass(si), line: false });
        }
      } else if (spec.series.length > 1 || spec.series[0].name) {
        for (si = 0; si < spec.series.length; si++) {
          legendItems.push({
            name: seriesName(spec.series[si]),
            cls: seriesClass(si),
            line: spec.type !== 'scatter' && kindOf(spec, spec.series[si]) === 'line'
          });
        }
      }
    }
    if (legendItems.length) {
      var legend = util.el('ul', { className: 'ui-chart-legend' });
      for (si = 0; si < legendItems.length; si++) {
        var it = legendItems[si];
        legend.appendChild(util.el('li', { className: 'ui-chart-legend-item' }, [
          util.el('span', {
            className: 'ui-chart-swatch ' + it.cls + (it.line ? ' ui-chart-swatch--line' : ''),
            'aria-hidden': 'true'
          }),
          util.el('span', { className: 'ui-chart-legend-name', text: it.name })
        ]));
      }
      caption.appendChild(legend);
    }
    if (!isSpark || spec.title) figure.appendChild(caption);

    // the svg
    var svg = svgEl('svg', 'ui-chart-svg', { role: 'img', 'aria-label': summary, focusable: 'false' });
    svg.setAttribute('height', isSpark ? SPARK_H : HEIGHT);
    var tooltip = null;
    var live = null;
    var plot = null;
    var describeId = null;
    if (isSpark) {
      svg.setAttribute('width', SPARK_W);
      svg.setAttribute('viewBox', '0 0 ' + SPARK_W + ' ' + SPARK_H);
      layoutSpark(svg, spec);
      figure.appendChild(svg);
    } else {
      plot = util.el('div', {
        className: 'ui-chart-plot',
        role: 'group',
        tabindex: '0',
        'aria-label': (spec.title ? spec.title + ', chart values' : 'Chart values')
      });
      if (testid) plot.setAttribute('data-testid', testid + '-plot');
      describeId = util.uid('chart-keys');
      var hint = util.el('span', {
        className: 'visually-hidden',
        id: describeId,
        text: 'Use the arrow keys to read values.'
      });
      plot.setAttribute('aria-describedby', describeId);
      tooltip = util.el('div', { className: 'ui-chart-tooltip', 'aria-hidden': 'true', hidden: true });
      if (testid) tooltip.setAttribute('data-testid', testid + '-tooltip');
      live = util.el('span', {
        className: 'visually-hidden ui-chart-live',
        'aria-live': 'polite',
        'aria-atomic': 'true'
      });
      if (testid) live.setAttribute('data-testid', testid + '-live');
      plot.appendChild(hint);
      plot.appendChild(live);
      plot.appendChild(svg);
      plot.appendChild(tooltip);
      figure.appendChild(plot);

      // Show data
      var dis = App.ui.disclosure({
        variant: 'plain',
        summary: 'Show data',
        testid: opts.testid ? opts.testid + '-data' : null,
        className: 'ui-chart-data'
      });
      var wrap = util.el('div', {
        className: 'ui-chart-table-wrap',
        tabindex: '0',
        role: 'region',
        'aria-label': spec.title ? spec.title + ', data table' : 'Chart data table'
      });
      wrap.appendChild(buildTable(spec, spec.title ? spec.title + ', data' : 'Chart data'));
      dis.body.appendChild(wrap);
      var notes = annotationLines(spec);
      if (notes.length) {
        var list = util.el('ul', { className: 'ui-chart-notes' });
        for (si = 0; si < notes.length; si++) list.appendChild(util.el('li', { text: notes[si] }));
        dis.body.appendChild(list);
      }
      figure.appendChild(dis.el);
    }

    // layout and interaction state
    var destroyed = false;
    var observer = null;
    var raf = 0;
    var laidWidth = 0;
    var pendingWidth = 0;
    var view = { positions: [], top: 0, bottom: 0 };
    var active = -1;
    var guide = null;
    var markerNodes = [];

    function hide() {
      active = -1;
      if (tooltip) tooltip.hidden = true;
      if (live) live.textContent = '';
      if (guide) guide.setAttribute('hidden', '');
      var m;
      for (m = 0; m < markerNodes.length; m++) markerNodes[m].setAttribute('hidden', '');
      for (m = 0; m < view.positions.length; m++) {
        if (view.positions[m].slice) view.positions[m].slice.setAttribute('class',
          SVG_CLASS.slice + ' ' + seriesClass(m));
      }
    }

    function show(idx, announce) {
      if (destroyed || !view.positions.length) return;
      if (idx < 0) idx = 0;
      if (idx > view.positions.length - 1) idx = view.positions.length - 1;
      hide();
      active = idx;
      var pos = view.positions[idx];
      tooltip.textContent = '';
      tooltip.appendChild(util.el('div', { className: 'ui-chart-tooltip-title', text: pos.title }));
      var r;
      for (r = 0; r < pos.rows.length; r++) {
        tooltip.appendChild(util.el('div', { className: 'ui-chart-tooltip-row' }, [
          util.el('span', { className: 'ui-chart-swatch ' + pos.rows[r].cls, 'aria-hidden': 'true' }),
          util.el('span', { className: 'ui-chart-tooltip-name', text: pos.rows[r].name }),
          util.el('span', { className: 'ui-chart-tooltip-value', text: pos.rows[r].value })
        ]));
      }
      if (announce && live) {
        var parts = [];
        for (r = 0; r < pos.rows.length; r++) parts.push(pos.rows[r].name + ' ' + pos.rows[r].value);
        live.textContent = pos.title + ': ' + parts.join(', ');
      }
      tooltip.hidden = false;
      var boxW = plot.clientWidth;
      var tw = tooltip.offsetWidth;
      var left = pos.x + 14;
      if (left + tw > boxW) left = Math.max(0, pos.x - 14 - tw);
      tooltip.style.left = left + 'px';
      tooltip.style.top = Math.max(0, Math.min(pos.y, HEIGHT - tooltip.offsetHeight)) + 'px';
      if (guide) {
        guide.setAttribute('x1', pos.x);
        guide.setAttribute('x2', pos.x);
        guide.removeAttribute('hidden');
      }
      for (r = 0; r < markerNodes.length; r++) {
        if (pos.markers[r]) {
          markerNodes[r].setAttribute('cx', pos.markers[r].x);
          markerNodes[r].setAttribute('cy', pos.markers[r].y);
          markerNodes[r].setAttribute('class', SVG_CLASS.marker + ' ' + pos.markers[r].cls);
          markerNodes[r].removeAttribute('hidden');
        }
      }
      if (pos.slice) pos.slice.setAttribute('class', SVG_CLASS.slice + ' ' + seriesClass(idx) + ' ' + SVG_CLASS.sliceActive);
    }

    function layout(width) {
      if (destroyed || width <= 0) return;
      laidWidth = width;
      svg.textContent = '';
      svg.setAttribute('width', width);
      svg.setAttribute('viewBox', '0 0 ' + width + ' ' + HEIGHT);
      svg.setAttribute('data-width', String(width));
      if (spec.type === 'scatter') view = layoutScatter(svg, spec, width);
      else if (isPie) view = layoutPie(svg, spec, width);
      else view = layoutCartesian(svg, spec, width);
      guide = null;
      markerNodes = [];
      if (!view.pie) {
        guide = svgEl('line', SVG_CLASS.guide, { x1: 0, x2: 0, y1: view.top, y2: view.bottom, hidden: '' });
        svg.appendChild(guide);
        var maxMarkers = 0;
        for (var p = 0; p < view.positions.length; p++) {
          maxMarkers = Math.max(maxMarkers, view.positions[p].markers.length);
        }
        for (var m = 0; m < maxMarkers; m++) {
          var node = svgEl('circle', SVG_CLASS.marker, { r: 5, hidden: '' });
          markerNodes.push(node);
          svg.appendChild(node);
        }
      }
      var prev = active;
      active = -1;
      if (tooltip) tooltip.hidden = true;
      if (prev >= 0) show(prev);
      fireLayout();
    }

    // opts.onLayout: after the first layout and on each width change; a no-op once the figure is
    // detached or the chart destroyed. A throw in the callback never breaks the chart.
    function fireLayout() {
      if (destroyed || typeof opts.onLayout !== 'function' || !figure.isConnected) return;
      try { opts.onLayout(); } catch (e) { /* the caller's callback must not break drawing */ }
    }

    function schedule() {
      if (destroyed || raf) return;
      raf = window.requestAnimationFrame(function () {
        raf = 0;
        if (destroyed) return;
        var w = pendingWidth || Math.floor(figure.clientWidth);
        if (w > 0 && w !== laidWidth) layout(w);
      });
    }

    function onResize(entries) {
      if (destroyed) return;
      if (!figure.isConnected) {
        // Detached after having been drawn: stop observing. A chart that was never attached
        // keeps waiting for its first width.
        if (laidWidth > 0 && observer) {
          observer.disconnect();
          observer = null;
        }
        return;
      }
      var w = Math.floor(entries && entries.length && entries[0].contentRect
        ? entries[0].contentRect.width : figure.clientWidth);
      if (w <= 0) return;
      pendingWidth = w;
      if (laidWidth === 0) layout(w);
      else schedule();
    }

    if (isSpark) {
      // A sparkline has no observer: fire once, on the first frame it is attached (bounded wait).
      var sparkTries = 0;
      var sparkWait = function () {
        if (destroyed) return;
        if (figure.isConnected) { fireLayout(); return; }
        if (++sparkTries < 30) window.requestAnimationFrame(sparkWait);
      };
      if (typeof opts.onLayout === 'function') window.requestAnimationFrame(sparkWait);
    } else {
      if (typeof window.ResizeObserver === 'function') {
        observer = new window.ResizeObserver(onResize);
        observer.observe(figure);
      } else {
        schedule();
      }

      var nearest = function (clientX) {
        var box = svg.getBoundingClientRect();
        var px = clientX - box.left;
        var best = -1;
        var bestD = Infinity;
        for (var i = 0; i < view.positions.length; i++) {
          var d = Math.abs(view.positions[i].x - px);
          if (d < bestD) { bestD = d; best = i; }
        }
        return best;
      };
      plot.addEventListener('pointermove', function (ev) {
        if (destroyed || !view.positions.length) return;
        var idx = nearest(ev.clientX);
        if (idx >= 0 && idx !== active) show(idx);
      });
      plot.addEventListener('pointerleave', function () {
        if (plot.ownerDocument.activeElement !== plot) hide();
      });
      plot.addEventListener('focus', function () {
        if (!destroyed) show(0);
      });
      plot.addEventListener('blur', function () { hide(); });
      plot.addEventListener('keydown', function (ev) {
        var n = view.positions.length;
        if (!n) return;
        var key = ev.key;
        if (key === 'ArrowRight' || key === 'ArrowDown') show(active < 0 ? 0 : Math.min(n - 1, active + 1), true);
        else if (key === 'ArrowLeft' || key === 'ArrowUp') show(active < 0 ? 0 : Math.max(0, active - 1), true);
        else if (key === 'Home') show(0, true);
        else if (key === 'End') show(n - 1, true);
        else if (key === 'Escape') { hide(); return; }
        else return;
        ev.preventDefault();
      });
    }

    return {
      el: figure,
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        if (observer) { observer.disconnect(); observer = null; }
        if (raf) { window.cancelAnimationFrame(raf); raf = 0; }
      }
    };
  };

  App.ui.chart.parse = parse;
  App.ui.chart.formatTick = P.formatTick;
  App.ui.chart.formatFull = P.formatFull;

  // App.ui.chart.block(source, {closed, testid}) -> Node (DD9). The drawn chart for a valid
  // spec, otherwise the error notice: a danger "Couldn't draw this chart." with the validator's
  // sentence, or a muted "This chart was cut off before it finished." when the fence never
  // closed (closed === false). The source sits under "Technical details". Never throws. The
  // notice is App.ui.visualNotice (js/ui/visual-notice.js), shared with the widget block.
  function errorBlock(source, reason, cutOff, opts) {
    return App.ui.visualNotice({
      tone: cutOff ? 'muted' : 'danger',
      headline: cutOff ? 'This chart was cut off before it finished.' : 'Couldn\'t draw this chart.',
      reason: cutOff ? '' : reason,
      source: source,
      sourceLabel: 'Chart source',
      testid: opts.testid ? opts.testid + '-error' : null,
      detailsTestid: opts.testid ? opts.testid + '-error-details' : null
    }).el;
  }

  App.ui.chart.block = function (source, opts) {
    opts = opts || {};
    var text = source === undefined || source === null ? '' : String(source);
    try {
      var result = parse(text);
      if (result.ok) {
        return App.ui.chart({ spec: result.spec, testid: opts.testid, onLayout: opts.onLayout }).el;
      }
      return errorBlock(text, result.message, opts.closed === false, opts);
    } catch (err) {
      try {
        return errorBlock(text, '', false, opts);
      } catch (err2) {
        var fallback = document.createElement('div');
        fallback.textContent = 'Couldn\'t draw this chart.';
        return fallback;
      }
    }
  };
})();
