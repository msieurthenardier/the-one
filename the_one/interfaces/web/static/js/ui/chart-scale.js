(function () {
  'use strict';
  window.App = window.App || {};

  // Chart internals, part 2 of 3 (M35 F2 L2, split out of ui/chart.js): SVG and text helpers
  // (including the measured text width), scales, axes, ticks and stacking. NOT a control: no
  // App.ui factory is defined here; the functions are shared through App.ui.util.chartParts. Load
  // order: chart-parse.js, chart-scale.js, chart-layout.js, chart.js.
  //
  // Text width (M35 F2 L2, flight DD14): axis text is measured in the browser, not estimated.
  // A probe <text> with the measured class is appended to the chart's own live <svg> (so the
  // real inherited font applies), read with getComputedTextLength() and removed at once. The
  // result is cached by (class, string) and the cache is cleared when the web fonts finish
  // loading, so a layout run before then cannot poison later ones. The old 6.4 px per code
  // point estimate remains only as the fallback: a detached svg, a thrown error, or a length of
  // 0 for a non-empty string.

  var P = window.App.ui.util.chartParts;
  var has = P.has;
  var cpLen = P.cpLen;
  var formatTick = P.formatTick;
  var formatFull = P.formatFull;

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var HEIGHT = 240;
  var SPARK_W = 140;
  var SPARK_H = 32;

  var SVG_CLASS = {
    grid: 'ui-chart-grid',
    axisLine: 'ui-chart-axis-line',
    tick: 'ui-chart-tick',
    axisLabel: 'ui-chart-axis-label',
    line: 'ui-chart-line',
    area: 'ui-chart-area',
    bar: 'ui-chart-bar',
    dot: 'ui-chart-dot',
    point: 'ui-chart-point',
    slice: 'ui-chart-slice',
    sliceActive: 'ui-chart-slice--active',
    ref: 'ui-chart-ref',
    refLabel: 'ui-chart-ref-label',
    guide: 'ui-chart-guide',
    marker: 'ui-chart-marker',
    spark: 'ui-chart-spark'
  };

  function seriesClass(i) {
    var cls = 'ui-chart-series-' + ((i % 8) + 1);
    return cls;
  }
  function dashClass(i) {
    var cls = '';
    if (i >= 4) cls = 'ui-chart-dash-' + (((i - 4) % 4) + 1);
    return cls;
  }

  // ---------------------------------------------------------------------------------------
  // Drawing helpers
  // ---------------------------------------------------------------------------------------

  function svgEl(tag, cls, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    if (cls) node.setAttribute('class', cls);
    var k;
    if (attrs) {
      for (k in attrs) {
        if (has(attrs, k)) node.setAttribute(k, String(attrs[k]));
      }
    }
    return node;
  }

  function svgText(cls, x, y, anchor, text) {
    var node = svgEl('text', cls, { x: x, y: y, 'text-anchor': anchor });
    node.textContent = text;
    return node;
  }

  var widthCache = {};
  function clearWidthCache() { widthCache = {}; }
  if (document.fonts && document.fonts.ready && typeof document.fonts.ready.then === 'function') {
    document.fonts.ready.then(clearWidthCache, function () { /* keep the estimate path */ });
  }

  function estimateWidth(text) { return cpLen(text) * 6.4; }

  // measure(svg, cls, text) -> pixels. Never throws.
  function measure(svg, cls, text) {
    text = String(text);
    if (text === '') return 0;
    var key = cls + '\u0000' + text;
    if (has(widthCache, key)) return widthCache[key];
    var w = 0;
    try {
      if (svg && svg.isConnected) {
        var probe = svgEl('text', cls, { x: 0, y: 0 });
        probe.textContent = text;
        svg.appendChild(probe);
        try {
          w = probe.getComputedTextLength();
        } finally {
          svg.removeChild(probe);
        }
      }
    } catch (err) {
      w = 0;
    }
    if (!(w > 0)) return estimateWidth(text);
    widthCache[key] = w;
    return w;
  }

  function codePoints(text) {
    var out = [];
    for (var i = 0; i < text.length; i++) {
      var c = text.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
        var d = text.charCodeAt(i + 1);
        if (d >= 0xdc00 && d <= 0xdfff) {
          out.push(text.slice(i, i + 2));
          i++;
          continue;
        }
      }
      out.push(text.charAt(i));
    }
    return out;
  }

  // fitText(svg, cls, text, maxWidth, maxCp): the text if it fits in maxWidth pixels and in
  // maxCp code points, else the longest code-point-safe prefix that fits with an ellipsis (at
  // least one code point). The prefix length is binary-searched, so the measurement count is
  // bounded by log2(maxCp).
  function fitText(svg, cls, text, maxWidth, maxCp) {
    text = String(text);
    var cps = codePoints(text);
    if (cps.length <= maxCp && measure(svg, cls, text) <= maxWidth) return text;
    var lo = 1;
    var hi = Math.max(1, Math.min(cps.length - 1, maxCp - 1));
    var best = 1;
    var guard = 0;
    while (lo <= hi && guard < 8) {
      var mid = (lo + hi) >> 1;
      if (measure(svg, cls, cps.slice(0, mid).join('') + '…') <= maxWidth) {
        best = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
      guard++;
    }
    return cps.slice(0, best).join('') + '…';
  }

  function xText(v) { return typeof v === 'number' ? formatFull(v, '') : String(v); }
  function xTick(v) { return typeof v === 'number' ? formatTick(v, '') : String(v); }

  function seriesName(s) { return s.name || 'Value'; }

  // ---------------------------------------------------------------------------------------
  // Scales, axes, stacking
  // ---------------------------------------------------------------------------------------

  function pow10(e) { return parseFloat('1e' + e); }
  function roundClean(v) { return parseFloat(v.toPrecision(12)); }

  function niceStep(range, count) {
    var raw = range / count;
    var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var norm = raw / mag;
    var nice = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
    return nice * mag;
  }

  function newExtent() { return { min: Infinity, max: -Infinity }; }
  function extend(ext, v) {
    if (v < ext.min) ext.min = v;
    if (v > ext.max) ext.max = v;
  }

  // buildAxis(axisSpec, extent, includeZero) -> {log, d0, d1, ticks}: the domain and the tick
  // values, before any pixels are known (the margins depend on the tick text).
  function buildAxis(axisSpec, ext, includeZero) {
    var log = axisSpec.scale === 'log';
    var lo = ext.min;
    var hi = ext.max;
    var ticks = [];
    var e;
    if (lo === Infinity) {
      lo = log ? 1 : 0;
      hi = log ? 10 : 1;
    }
    var fixedLo = axisSpec.min !== null && axisSpec.min !== undefined;
    var fixedHi = axisSpec.max !== null && axisSpec.max !== undefined;
    if (log) {
      var d0 = fixedLo ? axisSpec.min : pow10(Math.floor(Math.log(lo) / Math.LN10 + 1e-12));
      var d1 = fixedHi ? axisSpec.max : pow10(Math.ceil(Math.log(hi) / Math.LN10 - 1e-12));
      if (d1 <= d0) d1 = d0 * 10;
      var e0 = Math.ceil(Math.log(d0) / Math.LN10 - 1e-9);
      var e1 = Math.floor(Math.log(d1) / Math.LN10 + 1e-9);
      var stride = Math.max(1, Math.ceil((e1 - e0 + 1) / 7));
      for (e = e0; e <= e1; e += stride) ticks.push(pow10(e));
      if (ticks.length === 0) ticks.push(d0);
      return { log: true, d0: d0, d1: d1, ticks: ticks };
    }
    if (includeZero) {
      lo = Math.min(lo, 0);
      hi = Math.max(hi, 0);
    }
    if (hi === lo) {
      var pad = Math.abs(lo) * 0.1 || 1;
      lo -= pad;
      hi += pad;
    } else if (!includeZero) {
      var span = (hi - lo) * 0.04;
      lo -= span;
      hi += span;
    }
    if (fixedLo) lo = axisSpec.min;
    if (fixedHi) hi = axisSpec.max;
    if (hi <= lo) hi = lo + 1;
    var step = niceStep(hi - lo, 5);
    var a = fixedLo ? lo : Math.floor(lo / step + 1e-9) * step;
    var b = fixedHi ? hi : Math.ceil(hi / step - 1e-9) * step;
    var t;
    for (t = Math.ceil(a / step - 1e-9); t * step <= b + step * 1e-9; t++) ticks.push(roundClean(t * step));
    return { log: false, d0: roundClean(a), d1: roundClean(b), ticks: ticks };
  }

  function makeScale(axis, r0, r1) {
    if (axis.log) {
      var l0 = Math.log(axis.d0) / Math.LN10;
      var k = (r1 - r0) / (Math.log(axis.d1) / Math.LN10 - l0);
      return function (v) { return r0 + (Math.log(v) / Math.LN10 - l0) * k; };
    }
    var kk = (r1 - r0) / (axis.d1 - axis.d0);
    return function (v) { return r0 + (v - axis.d0) * kk; };
  }

  function kindOf(spec, s) {
    if (s.type) return s.type;
    return spec.type === 'bar' ? 'bar' : spec.type === 'line' ? 'line' : 'area';
  }

  function unitOf(spec, s) {
    return s.axis === 'right' && spec.y2 ? spec.y2.unit : spec.y.unit;
  }

  // Per-series, per-category [y0, y1] when the series is stacked; null entries for gaps.
  function computeStacks(spec, kinds) {
    var stacks = [];
    var n = spec.x.values ? spec.x.values.length : 0;
    var posTop = { left: [], right: [] };
    var negTop = { left: [], right: [] };
    var si;
    var i;
    for (si = 0; si < spec.series.length; si++) {
      var s = spec.series[si];
      var stackable = spec.stacked && (kinds[si] === 'bar' || kinds[si] === 'area');
      if (!stackable) { stacks.push(null); continue; }
      var side = s.axis;
      var row = [];
      for (i = 0; i < n; i++) {
        var v = s.values[i];
        if (posTop[side][i] === undefined) { posTop[side][i] = 0; negTop[side][i] = 0; }
        if (v === null) { row.push(null); continue; }
        if (kinds[si] === 'area' || v >= 0) {
          row.push({ y0: posTop[side][i], y1: posTop[side][i] + v });
          posTop[side][i] += v;
        } else {
          row.push({ y0: negTop[side][i], y1: negTop[side][i] + v });
          negTop[side][i] += v;
        }
      }
      stacks.push(row);
    }
    return stacks;
  }

  // ---------------------------------------------------------------------------------------
  // Axis drawing
  // ---------------------------------------------------------------------------------------

  function addGridAndTicks(svg, axis, scale, side, plot, unit) {
    var j;
    for (j = 0; j < axis.ticks.length; j++) {
      var py = scale(axis.ticks[j]);
      if (side === 'left') {
        svg.appendChild(svgEl('line', SVG_CLASS.grid, { x1: plot.l, x2: plot.r, y1: py, y2: py }));
        svg.appendChild(svgText(SVG_CLASS.tick, plot.l - 6, py + 4, 'end', formatTick(axis.ticks[j], unit)));
      } else {
        svg.appendChild(svgText(SVG_CLASS.tick, plot.r + 6, py + 4, 'start', formatTick(axis.ticks[j], unit)));
      }
    }
  }

  // The widest tick label of an axis (measured on the live svg), plus the 12 px margin.
  function tickWidth(svg, axis, unit) {
    var w = 0;
    for (var j = 0; j < axis.ticks.length; j++) {
      w = Math.max(w, measure(svg, SVG_CLASS.tick, formatTick(axis.ticks[j], unit)));
    }
    return Math.ceil(w) + 12;
  }

  function addRefLine(svg, ann, pos, plot, label) {
    if (pos.vertical) {
      svg.appendChild(svgEl('line', SVG_CLASS.ref, { x1: pos.v, x2: pos.v, y1: plot.t, y2: plot.b }));
      if (label) {
        var right = pos.v > plot.l + (plot.r - plot.l) * 0.7;
        svg.appendChild(svgText(SVG_CLASS.refLabel, right ? pos.v - 4 : pos.v + 4, plot.t + 11,
          right ? 'end' : 'start', label));
      }
    } else {
      svg.appendChild(svgEl('line', SVG_CLASS.ref, { x1: plot.l, x2: plot.r, y1: pos.v, y2: pos.v }));
      if (label) svg.appendChild(svgText(SVG_CLASS.refLabel, plot.r - 4, pos.v - 4, 'end', label));
    }
  }

  function axisLabels(svg, spec, plot, width, hasRight) {
    if (spec.y.label) svg.appendChild(svgText(SVG_CLASS.axisLabel, plot.l, 12, 'start', spec.y.label));
    if (hasRight && spec.y2 && spec.y2.label) {
      svg.appendChild(svgText(SVG_CLASS.axisLabel, plot.r, 12, 'end', spec.y2.label));
    }
    if (spec.x.label) {
      svg.appendChild(svgText(SVG_CLASS.axisLabel, (plot.l + plot.r) / 2, HEIGHT - 4, 'middle', spec.x.label));
    }
  }

  P.SVG_CLASS = SVG_CLASS;
  P.HEIGHT = HEIGHT;
  P.SPARK_W = SPARK_W;
  P.SPARK_H = SPARK_H;
  P.seriesClass = seriesClass;
  P.dashClass = dashClass;
  P.svgEl = svgEl;
  P.svgText = svgText;
  P.measure = measure;
  P.fitText = fitText;
  P.xText = xText;
  P.xTick = xTick;
  P.seriesName = seriesName;
  P.buildAxis = buildAxis;
  P.makeScale = makeScale;
  P.newExtent = newExtent;
  P.extend = extend;
  P.kindOf = kindOf;
  P.unitOf = unitOf;
  P.computeStacks = computeStacks;
  P.addGridAndTicks = addGridAndTicks;
  P.tickWidth = tickWidth;
  P.addRefLine = addRefLine;
  P.axisLabels = axisLabels;
})();
