(function () {
  'use strict';
  window.App = window.App || {};

  // Chart internals, part 3 of 3 (M35 F2 L2, split out of ui/chart.js): the per-type layouts,
  // the data table, the annotation lines and the accessible summary. NOT a control: no App.ui
  // factory is defined here; the functions are shared through App.ui.util.chartParts. Load order:
  // chart-parse.js, chart-scale.js, chart-layout.js, chart.js.
  //
  // Layout: one function per family. Each fills the svg and returns the interaction view
  // {positions: [{x, y, title, rows: [{cls, name, value}], markers: [{x, y, cls}], slice}],
  //  top, bottom}. Every layout runs on an attached svg (the chart lays out after attach), so
  // axis text is measured, not estimated; see chart-scale.js.

  var P = window.App.ui.util.chartParts;
  var has = P.has;
  var formatTick = P.formatTick;
  var formatFull = P.formatFull;
  var SVG_CLASS = P.SVG_CLASS;
  var HEIGHT = P.HEIGHT;
  var SPARK_W = P.SPARK_W;
  var SPARK_H = P.SPARK_H;
  var seriesClass = P.seriesClass;
  var dashClass = P.dashClass;
  var svgEl = P.svgEl;
  var svgText = P.svgText;
  var measure = P.measure;
  var fitText = P.fitText;
  var xText = P.xText;
  var xTick = P.xTick;
  var seriesName = P.seriesName;
  var buildAxis = P.buildAxis;
  var makeScale = P.makeScale;
  var newExtent = P.newExtent;
  var extend = P.extend;
  var kindOf = P.kindOf;
  var unitOf = P.unitOf;
  var computeStacks = P.computeStacks;
  var addGridAndTicks = P.addGridAndTicks;
  var tickWidth = P.tickWidth;
  var addRefLine = P.addRefLine;
  var axisLabels = P.axisLabels;

  function summarise(spec) {
    var t = spec.type;
    var parts = [t === 'sparkline' ? 'Sparkline' : t.charAt(0).toUpperCase() + t.slice(1) + ' chart'];
    if (spec.title) parts.push(spec.title);
    var s0 = spec.series[0];
    var i;
    if (t === 'sparkline') {
      var first = null;
      var last = null;
      var count = 0;
      for (i = 0; i < s0.values.length; i++) {
        if (s0.values[i] !== null) {
          if (first === null) first = s0.values[i];
          last = s0.values[i];
        }
        count++;
      }
      parts.push('from ' + formatFull(first, spec.y.unit) + ' to ' + formatFull(last, spec.y.unit));
      parts.push(count + ' values');
    } else if (t === 'scatter') {
      var pts = 0;
      for (i = 0; i < spec.series.length; i++) pts += spec.series[i].values.length;
      parts.push(pts + ' points');
      parts.push(spec.series.length + ' series');
    } else if (t === 'pie') {
      parts.push(spec.x.values.length + ' slices');
    } else {
      var xs = spec.x.values;
      parts.push(xs.length > 1 ? xText(xs[0]) + ' to ' + xText(xs[xs.length - 1]) : xText(xs[0]));
      parts.push(spec.series.length + ' series');
    }
    return parts.join(', ');
  }

  function scaleDomainLo(side, axL, axR) { return side === 'right' && axR ? axR.d0 : axL.d0; }
  function scaleDomainHi(side, axL, axR) { return side === 'right' && axR ? axR.d1 : axL.d1; }

  function layoutCartesian(svg, spec, width) {
    var n = spec.x.values.length;
    var kinds = spec.series.map(function (s) { return kindOf(spec, s); });
    var stacks = computeStacks(spec, kinds);
    var ext = { left: newExtent(), right: newExtent() };
    var zero = { left: false, right: false };
    var used = { left: false, right: false };
    var si;
    var i;
    for (si = 0; si < spec.series.length; si++) {
      var s = spec.series[si];
      used[s.axis] = true;
      if (kinds[si] === 'bar' || kinds[si] === 'area') zero[s.axis] = true;
      for (i = 0; i < n; i++) {
        var v = s.values[i];
        if (v === null) continue;
        if (stacks[si] && stacks[si][i]) {
          extend(ext[s.axis], stacks[si][i].y0);
          extend(ext[s.axis], stacks[si][i].y1);
        } else {
          extend(ext[s.axis], v);
        }
      }
    }
    var a;
    for (a = 0; a < spec.annotations.length; a++) {
      var an = spec.annotations[a];
      if (an.axis === 'y') extend(ext.left, an.value);
      else if (an.axis === 'y2') { extend(ext.right, an.value); used.right = true; }
    }
    var axL = buildAxis(spec.y, ext.left, zero.left);
    var axR = used.right && spec.y2 ? buildAxis(spec.y2, ext.right, zero.right) : null;

    var hasLabels = !!(spec.y.label || (axR && spec.y2.label));
    var plot = {
      l: Math.max(34, tickWidth(svg, axL, spec.y.unit)),
      r: width - (axR ? Math.max(34, tickWidth(svg, axR, spec.y2.unit)) : 12),
      t: hasLabels ? 24 : 10,
      b: HEIGHT - (spec.x.label ? 40 : 24)
    };
    if (plot.r - plot.l < 40) plot.r = plot.l + 40;
    var ys = makeScale(axL, plot.b, plot.t);
    var yr = axR ? makeScale(axR, plot.b, plot.t) : null;
    var band = (plot.r - plot.l) / n;
    function cx(idx) { return plot.l + (idx + 0.5) * band; }
    function scaleFor(side) { return side === 'right' && yr ? yr : ys; }
    function baseFor(side) {
      var ax = side === 'right' && axR ? axR : axL;
      if (ax.log) return ax.d0;
      return Math.max(ax.d0, Math.min(ax.d1, 0));
    }

    addGridAndTicks(svg, axL, ys, 'left', plot, spec.y.unit);
    if (axR) addGridAndTicks(svg, axR, yr, 'right', plot, spec.y2.unit);
    svg.appendChild(svgEl('line', SVG_CLASS.axisLine, { x1: plot.l, x2: plot.r, y1: plot.b, y2: plot.b }));

    // x tick labels, thinned to fit and truncated with an ellipsis (measured widths).
    var maxText = 0;
    for (i = 0; i < n; i++) maxText = Math.max(maxText, measure(svg, SVG_CLASS.tick, xTick(spec.x.values[i])));
    var stride = Math.max(1, Math.ceil((Math.min(maxText, 120) + 8) / band));
    var maxWidth = Math.max(19, band * stride - 6);
    for (i = 0; i < n; i += stride) {
      svg.appendChild(svgText(SVG_CLASS.tick, cx(i), plot.b + 16, 'middle',
        fitText(svg, SVG_CLASS.tick, xTick(spec.x.values[i]), maxWidth, 24)));
    }
    axisLabels(svg, spec, plot, width, !!axR);

    // bars
    var slotOf = [];
    var slots = 0;
    var slotByAxis = {};
    for (si = 0; si < spec.series.length; si++) {
      if (kinds[si] !== 'bar') { slotOf.push(-1); continue; }
      if (spec.stacked) {
        var key = spec.series[si].axis;
        if (!has(slotByAxis, key)) { slotByAxis[key] = slots; slots++; }
        slotOf.push(slotByAxis[key]);
      } else {
        slotOf.push(slots);
        slots++;
      }
    }
    var barW = slots ? Math.max(1, (band * 0.72) / slots) : 0;
    for (si = 0; si < spec.series.length; si++) {
      if (kinds[si] !== 'bar') continue;
      var bs = spec.series[si];
      var sc = scaleFor(bs.axis);
      var base = baseFor(bs.axis);
      for (i = 0; i < n; i++) {
        if (bs.values[i] === null) continue;
        var y0 = stacks[si] ? stacks[si][i].y0 : base;
        var y1 = stacks[si] ? stacks[si][i].y1 : bs.values[i];
        var p0 = sc(Math.max(y0, scaleDomainLo(bs.axis, axL, axR)));
        var p1 = sc(Math.min(Math.max(y1, scaleDomainLo(bs.axis, axL, axR)), scaleDomainHi(bs.axis, axL, axR)));
        var bx = cx(i) - (slots * barW) / 2 + slotOf[si] * barW;
        svg.appendChild(svgEl('rect', SVG_CLASS.bar + ' ' + seriesClass(si), {
          x: bx, y: Math.min(p0, p1), width: Math.max(1, barW - 1), height: Math.abs(p1 - p0)
        }));
      }
    }

    // areas and lines
    for (si = 0; si < spec.series.length; si++) {
      var ls = spec.series[si];
      if (kinds[si] === 'bar') continue;
      var lsc = scaleFor(ls.axis);
      var lbase = baseFor(ls.axis);
      var seg = [];
      var segs = [];
      for (i = 0; i < n; i++) {
        if (ls.values[i] === null) {
          if (seg.length) { segs.push(seg); seg = []; }
          continue;
        }
        var top = stacks[si] ? stacks[si][i].y1 : ls.values[i];
        var bottom = stacks[si] ? stacks[si][i].y0 : lbase;
        seg.push({ x: cx(i), y: lsc(top), b: lsc(bottom) });
      }
      if (seg.length) segs.push(seg);
      var sp;
      for (sp = 0; sp < segs.length; sp++) {
        var pts = segs[sp];
        var d = '';
        var k;
        for (k = 0; k < pts.length; k++) d += (k ? 'L' : 'M') + pts[k].x + ' ' + pts[k].y;
        if (kinds[si] === 'area' && pts.length > 1) {
          var ad = d;
          for (k = pts.length - 1; k >= 0; k--) ad += 'L' + pts[k].x + ' ' + pts[k].b;
          svg.appendChild(svgEl('path', SVG_CLASS.area + ' ' + seriesClass(si), { d: ad + 'Z' }));
        }
        if (pts.length > 1) {
          svg.appendChild(svgEl('path', SVG_CLASS.line + ' ' + seriesClass(si) + ' ' + dashClass(si), { d: d }));
        }
        if (pts.length === 1 || n <= 24) {
          for (k = 0; k < pts.length; k++) {
            svg.appendChild(svgEl('circle', SVG_CLASS.dot + ' ' + seriesClass(si), { cx: pts[k].x, cy: pts[k].y, r: 3 }));
          }
        }
      }
    }

    // reference lines
    for (a = 0; a < spec.annotations.length; a++) {
      var ann = spec.annotations[a];
      var pos;
      if (ann.axis === 'x') {
        var at = -1;
        for (i = 0; i < n; i++) if (xText(spec.x.values[i]) === xText(ann.value)) at = i;
        if (at === -1) continue;
        pos = { vertical: true, v: cx(at) };
      } else {
        pos = { vertical: false, v: (ann.axis === 'y2' && yr ? yr : ys)(ann.value) };
      }
      addRefLine(svg, ann, pos, plot, ann.label);
    }

    // interaction view
    var positions = [];
    for (i = 0; i < n; i++) {
      var rows = [];
      var markers = [];
      for (si = 0; si < spec.series.length; si++) {
        var vs = spec.series[si];
        var val = vs.values[i];
        rows.push({
          cls: seriesClass(si),
          name: seriesName(vs),
          value: val === null ? 'No data' : formatFull(val, unitOf(spec, vs))
        });
        if (val !== null) {
          var topv = stacks[si] ? stacks[si][i].y1 : val;
          markers.push({ x: cx(i), y: scaleFor(vs.axis)(topv), cls: seriesClass(si) });
        }
      }
      positions.push({ x: cx(i), y: plot.t, title: xText(spec.x.values[i]), rows: rows, markers: markers });
    }
    return { positions: positions, top: plot.t, bottom: plot.b };
  }

  function layoutScatter(svg, spec, width) {
    var ext = { x: newExtent(), y: newExtent() };
    var si;
    var i;
    for (si = 0; si < spec.series.length; si++) {
      for (i = 0; i < spec.series[si].values.length; i++) {
        extend(ext.x, spec.series[si].values[i][0]);
        extend(ext.y, spec.series[si].values[i][1]);
      }
    }
    for (i = 0; i < spec.annotations.length; i++) {
      if (spec.annotations[i].axis === 'x') extend(ext.x, spec.annotations[i].value);
      else extend(ext.y, spec.annotations[i].value);
    }
    var axY = buildAxis(spec.y, ext.y, false);
    var axX = buildAxis({ scale: spec.x.scale, min: null, max: null }, ext.x, false);
    var plot = {
      l: Math.max(34, tickWidth(svg, axY, spec.y.unit)),
      r: width - 16,
      t: spec.y.label ? 24 : 10,
      b: HEIGHT - (spec.x.label ? 40 : 24)
    };
    if (plot.r - plot.l < 40) plot.r = plot.l + 40;
    var ys = makeScale(axY, plot.b, plot.t);
    var xs = makeScale(axX, plot.l, plot.r);
    addGridAndTicks(svg, axY, ys, 'left', plot, spec.y.unit);
    svg.appendChild(svgEl('line', SVG_CLASS.axisLine, { x1: plot.l, x2: plot.r, y1: plot.b, y2: plot.b }));
    for (i = 0; i < axX.ticks.length; i++) {
      svg.appendChild(svgText(SVG_CLASS.tick, xs(axX.ticks[i]), plot.b + 16, 'middle', formatTick(axX.ticks[i], '')));
    }
    axisLabels(svg, spec, plot, width, false);
    var all = [];
    for (si = 0; si < spec.series.length; si++) {
      for (i = 0; i < spec.series[si].values.length; i++) {
        var pt = spec.series[si].values[i];
        all.push({ si: si, x: pt[0], y: pt[1] });
        svg.appendChild(svgEl('circle', SVG_CLASS.point + ' ' + seriesClass(si), {
          cx: xs(pt[0]), cy: ys(pt[1]), r: 4
        }));
      }
    }
    for (i = 0; i < spec.annotations.length; i++) {
      var an = spec.annotations[i];
      addRefLine(svg, an, an.axis === 'x' ? { vertical: true, v: xs(an.value) } : { vertical: false, v: ys(an.value) },
        plot, an.label);
    }
    all.sort(function (p, q) { return p.x - q.x || p.si - q.si; });
    var positions = all.map(function (p) {
      var s = spec.series[p.si];
      var px = xs(p.x);
      var py = ys(p.y);
      return {
        x: px, y: py,
        title: (spec.x.label ? spec.x.label + ': ' : '') + formatFull(p.x, ''),
        rows: [{ cls: seriesClass(p.si), name: seriesName(s), value: formatFull(p.y, spec.y.unit) }],
        markers: [{ x: px, y: py, cls: seriesClass(p.si) }]
      };
    });
    return { positions: positions, top: plot.t, bottom: plot.b };
  }

  function layoutPie(svg, spec, width) {
    var s = spec.series[0];
    var total = 0;
    var i;
    for (i = 0; i < s.values.length; i++) total += s.values[i];
    var cx = width / 2;
    var cy = HEIGHT / 2;
    var r = Math.max(20, Math.min(width / 2, HEIGHT / 2) - 10);
    var angle = -Math.PI / 2;
    var positions = [];
    var nonZero = 0;
    for (i = 0; i < s.values.length; i++) if (s.values[i] > 0) nonZero++;
    for (i = 0; i < s.values.length; i++) {
      var v = s.values[i];
      var sweep = (v / total) * Math.PI * 2;
      var mid = angle + sweep / 2;
      var node = null;
      if (v > 0 && nonZero === 1) {
        node = svgEl('circle', SVG_CLASS.slice + ' ' + seriesClass(i), { cx: cx, cy: cy, r: r });
      } else if (v > 0) {
        var x0 = cx + r * Math.cos(angle);
        var y0 = cy + r * Math.sin(angle);
        var x1 = cx + r * Math.cos(angle + sweep);
        var y1 = cy + r * Math.sin(angle + sweep);
        node = svgEl('path', SVG_CLASS.slice + ' ' + seriesClass(i), {
          d: 'M' + cx + ' ' + cy + 'L' + x0 + ' ' + y0 + 'A' + r + ' ' + r + ' 0 ' +
            (sweep > Math.PI ? 1 : 0) + ' 1 ' + x1 + ' ' + y1 + 'Z'
        });
      }
      if (node) svg.appendChild(node);
      var pct = Math.round((v / total) * 1000) / 10;
      positions.push({
        x: cx + r * 0.6 * Math.cos(mid),
        y: cy + r * 0.6 * Math.sin(mid),
        title: xText(spec.x.values[i]),
        rows: [{ cls: seriesClass(i), name: seriesName(s), value: formatFull(v, spec.y.unit) + ' (' + pct + '%)' }],
        markers: [],
        slice: node
      });
      angle += sweep;
    }
    return { positions: positions, top: 8, bottom: HEIGHT - 8, pie: true };
  }

  function layoutSpark(svg, spec) {
    var vals = spec.series[0].values;
    var lo = Infinity;
    var hi = -Infinity;
    var i;
    for (i = 0; i < vals.length; i++) {
      if (vals[i] === null) continue;
      lo = Math.min(lo, vals[i]);
      hi = Math.max(hi, vals[i]);
    }
    if (hi === lo) { lo -= 1; hi += 1; }
    var n = vals.length;
    function sx(idx) { return 3 + (n > 1 ? (idx / (n - 1)) * (SPARK_W - 6) : (SPARK_W - 6) / 2); }
    function sy(v) { return SPARK_H - 4 - ((v - lo) / (hi - lo)) * (SPARK_H - 8); }
    var d = '';
    var pen = false;
    var lastX = null;
    var lastY = null;
    for (i = 0; i < n; i++) {
      if (vals[i] === null) { pen = false; continue; }
      d += (pen ? 'L' : 'M') + sx(i) + ' ' + sy(vals[i]);
      pen = true;
      lastX = sx(i);
      lastY = sy(vals[i]);
    }
    svg.appendChild(svgEl('path', SVG_CLASS.spark + ' ' + seriesClass(0), { d: d }));
    if (lastX !== null) {
      svg.appendChild(svgEl('circle', SVG_CLASS.dot + ' ' + seriesClass(0), { cx: lastX, cy: lastY, r: 2.5 }));
    }
  }

  function buildTable(spec, caption) {
    var util = App.ui.util;
    var table = util.el('table', { className: 'ui-chart-table' });
    table.appendChild(util.el('caption', { className: 'visually-hidden', text: caption }));
    var head = util.el('tr');
    var body = util.el('tbody');
    var i;
    var si;
    function th(text, scope) {
      var cell = util.el('th', { text: text });
      cell.setAttribute('scope', scope);
      return cell;
    }
    if (spec.type === 'scatter') {
      head.appendChild(th('Series', 'col'));
      head.appendChild(th(spec.x.label || 'x', 'col'));
      head.appendChild(th(spec.y.label || 'y', 'col'));
      for (si = 0; si < spec.series.length; si++) {
        for (i = 0; i < spec.series[si].values.length; i++) {
          var pt = spec.series[si].values[i];
          body.appendChild(util.el('tr', null, [
            th(seriesName(spec.series[si]), 'row'),
            util.el('td', { text: formatFull(pt[0], '') }),
            util.el('td', { text: formatFull(pt[1], spec.y.unit) })
          ]));
        }
      }
    } else {
      head.appendChild(th(spec.x.label || (spec.type === 'pie' ? 'Slice' : 'Category'), 'col'));
      for (si = 0; si < spec.series.length; si++) head.appendChild(th(seriesName(spec.series[si]), 'col'));
      for (i = 0; i < spec.x.values.length; i++) {
        var row = util.el('tr', null, [th(xText(spec.x.values[i]), 'row')]);
        for (si = 0; si < spec.series.length; si++) {
          var v = spec.series[si].values[i];
          row.appendChild(util.el('td', {
            text: v === null ? '' : formatFull(v, unitOf(spec, spec.series[si]))
          }));
        }
        body.appendChild(row);
      }
    }
    table.appendChild(util.el('thead', null, [head]));
    table.appendChild(body);
    return table;
  }

  function annotationLines(spec) {
    var out = [];
    for (var i = 0; i < spec.annotations.length; i++) {
      var an = spec.annotations[i];
      var shown = an.axis === 'x' ? xText(an.value)
        : formatFull(an.value, an.axis === 'y2' && spec.y2 ? spec.y2.unit : spec.y.unit);
      out.push('Reference line: ' + (an.label ? an.label + ', ' : '') + shown);
    }
    return out;
  }

  P.summarise = summarise;
  P.layoutCartesian = layoutCartesian;
  P.layoutScatter = layoutScatter;
  P.layoutPie = layoutPie;
  P.layoutSpark = layoutSpark;
  P.buildTable = buildTable;
  P.annotationLines = annotationLines;
})();
