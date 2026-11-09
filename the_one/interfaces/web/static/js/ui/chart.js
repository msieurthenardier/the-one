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
  //   App.ui.chart.placeholder({type, testid}) -> {el, setType, setSource, destroy}
  //                                               (js/ui/chart-placeholder.js)
  //
  // The chart builds its structure at once and lays out its SVG at the width it is given:
  // on its first ResizeObserver callback after attach, and again on width changes (coalesced
  // to one animation frame). Text is laid out at its true size and never scaled. All colour is
  // CSS (ui-chart-series-N classes using var(--chart-N)), so a theme change repaints with no
  // JavaScript. No document listeners, no timers.

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var TYPES = ['bar', 'line', 'area', 'scatter', 'pie', 'sparkline'];
  var X_TYPES = ['bar', 'line', 'area', 'pie', 'scatter'];
  var Y2_TYPES = ['bar', 'line', 'area'];
  var ANNOTATION_TYPES = ['bar', 'line', 'area', 'scatter'];
  var MAX_SERIES = 8;
  var MAX_VALUES = 2000;
  var MAX_CATEGORIES = 200;
  var MAX_SLICES = 12;
  var MAX_ANNOTATIONS = 5;
  var MAX_LABEL = 60;
  var MAX_UNIT = 12;
  var MAX_TITLE = 120;
  var PREFIX_UNITS = ['$', '€', '£', '¥'];
  var THIN_SPACE = ' ';
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

  function has(obj, key) { return Object.prototype.hasOwnProperty.call(obj, key); }
  function isObject(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function isNone(v) { return v === undefined || v === null; }

  // Length in Unicode code points (the document counts code points, not UTF-16 units).
  function cpLen(s) {
    var n = 0;
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
        var d = s.charCodeAt(i + 1);
        if (d >= 0xdc00 && d <= 0xdfff) i++;
      }
      n++;
    }
    return n;
  }

  // ---------------------------------------------------------------------------------------
  // Number display (docs/chart-format.md "Number display")
  // ---------------------------------------------------------------------------------------

  function sig3(a) {
    var m = /^(\d)\.(\d\d)e([+-]\d+)$/.exec(a.toExponential(2));
    return { digits: m[1] + m[2], exp: parseInt(m[3], 10) };
  }
  function trimZeros(text) {
    if (text.indexOf('.') !== -1) text = text.replace(/0+$/, '').replace(/\.$/, '');
    return text;
  }
  function expForm(digits, exp) {
    return trimZeros(digits.charAt(0) + '.' + digits.slice(1)) + 'e' + exp;
  }
  function withUnit(sign, body, unit) {
    if (unit && PREFIX_UNITS.indexOf(unit) !== -1) return sign + unit + body;
    if (unit) return sign + body + THIN_SPACE + unit;
    return sign + body;
  }

  function formatTick(value, unit) {
    unit = unit || '';
    if (value === 0) return withUnit('', '0', unit);
    var sign = value < 0 ? '-' : '';
    var s = sig3(Math.abs(value));
    var exp = s.exp;
    if (exp >= 15 || exp < -6) return withUnit(sign, expForm(s.digits, exp), unit);
    var suffix = '';
    var shift = 0;
    if (exp >= 9) { suffix = 'B'; shift = 9; }
    else if (exp >= 6) { suffix = 'M'; shift = 6; }
    else if (exp >= 3) { suffix = 'k'; shift = 3; }
    var point = exp - shift + 1;
    var body;
    if (point <= 0) {
      body = '0.' + new Array(-point + 1).join('0') + s.digits;
    } else if (point >= 3) {
      body = s.digits + new Array(point - 3 + 1).join('0');
    } else {
      body = s.digits.slice(0, point) + '.' + s.digits.slice(point);
    }
    return withUnit(sign, trimZeros(body) + suffix, unit);
  }

  function formatFull(value, unit) {
    unit = unit || '';
    if (value === 0) return withUnit('', '0', unit);
    var sign = value < 0 ? '-' : '';
    var a = Math.abs(value);
    var s = sig3(a);
    if (s.exp >= 15 || s.exp < -6) return withUnit(sign, expForm(s.digits, s.exp), unit);
    var fixed = a.toFixed(6);
    var parts = fixed.split('.');
    var whole = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    var text = trimZeros(whole + '.' + parts[1]);
    if (text === '0') sign = '';
    return withUnit(sign, text, unit);
  }

  // ---------------------------------------------------------------------------------------
  // Validation: a second implementation of docs/chart-format.md (same order, same sentences)
  // ---------------------------------------------------------------------------------------

  function Fail(message) { this.message = message; }

  function scalarKey(v) { return typeof v === 'string' ? 's:' + v : 'n:' + String(v); }

  function labelCheck(text) {
    var n = cpLen(text);
    if (n > MAX_LABEL) throw new Fail('A label is ' + n + ' characters; the limit is ' + MAX_LABEL + '.');
  }

  function seriesRef(list, i) {
    var s = list[i];
    var name = isObject(s) ? s.name : null;
    if (typeof name === 'string' && name) return 'Series "' + name + '"';
    return 'Series ' + (i + 1);
  }

  function emptyAxis() {
    return { label: '', unit: '', scale: 'linear', min: null, max: null, values: null };
  }

  function parseAxis(raw, key, chartType) {
    if (isNone(raw)) {
      if (key === 'x' && chartType !== 'scatter') {
        throw new Fail('Axis "x" needs a list of "values" with at least one entry.');
      }
      return emptyAxis();
    }
    if (!isObject(raw)) throw new Fail('Axis "' + key + '" must be an object.');
    var label = '';
    if (has(raw, 'label')) {
      if (typeof raw.label !== 'string') throw new Fail('Axis "' + key + '" has a "label" that isn\'t text.');
      labelCheck(raw.label);
      label = raw.label;
    }
    var unit = '';
    if (key !== 'x' && has(raw, 'unit')) {
      if (typeof raw.unit !== 'string') throw new Fail('Axis "' + key + '" has a "unit" that isn\'t text.');
      var ul = cpLen(raw.unit);
      if (ul > MAX_UNIT) throw new Fail('A unit is ' + ul + ' characters; the limit is ' + MAX_UNIT + '.');
      unit = raw.unit;
    }
    var scale = 'linear';
    if (has(raw, 'scale')) {
      scale = raw.scale;
      if (scale !== 'linear' && scale !== 'log') {
        throw new Fail('Axis "' + key + '" has a "scale" that isn\'t linear or log.');
      }
      if (key === 'x' && scale === 'log' && chartType !== 'scatter') {
        throw new Fail('A log scale on axis "x" only works on a scatter chart.');
      }
    }
    var lo = null;
    var hi = null;
    if (key !== 'x') {
      var names = ['min', 'max'];
      for (var k = 0; k < names.length; k++) {
        if (has(raw, names[k]) && !isNum(raw[names[k]])) {
          throw new Fail('Axis "' + key + '" has a "' + names[k] + '" that isn\'t a number.');
        }
      }
      if (has(raw, 'min')) lo = raw.min;
      if (has(raw, 'max')) hi = raw.max;
      if (lo !== null && hi !== null && lo >= hi) {
        throw new Fail('Axis "' + key + '" needs "min" to be below "max".');
      }
      if (scale === 'log' && lo !== null && lo <= 0) {
        throw new Fail('Axis "' + key + '" has a log scale, so "min" must be above 0.');
      }
    }
    var values = null;
    if (key === 'x' && chartType !== 'scatter') {
      var vals = raw.values;
      if (!Array.isArray(vals) || vals.length === 0) {
        throw new Fail('Axis "x" needs a list of "values" with at least one entry.');
      }
      var seen = {};
      values = [];
      for (var i = 0; i < vals.length; i++) {
        var v = vals[i];
        if (typeof v === 'string') {
          labelCheck(v);
        } else if (!isNum(v)) {
          throw new Fail('Axis "x" has a value that is neither text nor a number.');
        }
        var sk = scalarKey(v);
        if (has(seen, sk)) throw new Fail('Axis "x" lists the same value twice.');
        seen[sk] = true;
        values.push(v);
      }
    }
    return { label: label, unit: unit, scale: scale, min: lo, max: hi, values: values };
  }

  function parseSeriesOne(s, i, chartType, multiple, hasY2, list) {
    if (!isObject(s)) throw new Fail('Series ' + (i + 1) + ' isn\'t an object.');
    var name = s.name;
    var nameOk = typeof name === 'string' && name !== '';
    if (multiple && !nameOk) throw new Fail('Series ' + (i + 1) + ' needs a "name".');
    if (has(s, 'name') && typeof name !== 'string') {
      throw new Fail('Series ' + (i + 1) + ' needs a "name".');
    }
    if (typeof name === 'string') labelCheck(name);
    var ref = seriesRef(list, i);
    var stype = null;
    if (has(s, 'type')) {
      if (chartType !== 'bar' && chartType !== 'line') {
        throw new Fail(ref + ' has its own "type", which only bar and line charts allow.');
      }
      stype = s.type;
      if (stype !== 'bar' && stype !== 'line') {
        throw new Fail(ref + ' has a "type" that isn\'t bar or line.');
      }
    }
    var axis = 'left';
    if (has(s, 'axis')) {
      axis = s.axis;
      if (axis !== 'left' && axis !== 'right') {
        throw new Fail(ref + ' has an "axis" that isn\'t left or right.');
      }
      if (axis === 'right' && !hasY2) {
        throw new Fail(ref + ' is on the right axis, but the chart has no "y2".');
      }
    }
    var vals = s.values;
    if (!Array.isArray(vals)) throw new Fail(ref + ' needs a list of "values".');
    var out = [];
    for (var j = 0; j < vals.length; j++) {
      var v = vals[j];
      if (chartType === 'scatter') {
        if (!(Array.isArray(v) && v.length === 2 && isNum(v[0]) && isNum(v[1]))) {
          throw new Fail(ref + ' has a point that isn\'t an [x, y] pair of numbers.');
        }
        out.push([v[0], v[1]]);
      } else if (chartType === 'pie') {
        if (!isNum(v)) throw new Fail(ref + ' has a value that isn\'t a number.');
        out.push(v);
      } else {
        if (v !== null && !isNum(v)) throw new Fail(ref + ' has a value that isn\'t a number or null.');
        out.push(v);
      }
    }
    return { name: typeof name === 'string' ? name : '', values: out, axis: axis, type: stype };
  }

  function parseAnnotations(raw, chartType, x, y, y2) {
    if (!Array.isArray(raw)) throw new Fail('The "annotations" must be a list.');
    var out = [];
    var cats = {};
    var xs = x.values || [];
    for (var c = 0; c < xs.length; c++) cats[scalarKey(xs[c])] = true;
    for (var idx = 0; idx < raw.length; idx++) {
      var i = idx + 1;
      var a = raw[idx];
      if (!isObject(a)) throw new Fail('Annotation ' + i + ' isn\'t an object.');
      var axis = a.axis;
      if (axis !== 'y' && axis !== 'y2' && axis !== 'x') {
        throw new Fail('Annotation ' + i + ' needs an "axis" of y, y2 or x.');
      }
      if (axis === 'y2' && y2 === null) {
        throw new Fail('Annotation ' + i + ' is on "y2", but the chart has no "y2".');
      }
      var value = a.value;
      if (axis === 'x' && chartType !== 'scatter') {
        if (!(typeof value === 'string' || isNum(value)) || !has(cats, scalarKey(value))) {
          throw new Fail('Annotation ' + i + ' is at a category that isn\'t in the x values.');
        }
      } else if (!isNum(value)) {
        throw new Fail('Annotation ' + i + ' needs a numeric "value".');
      }
      var label = '';
      if (has(a, 'label')) {
        if (typeof a.label !== 'string') throw new Fail('Annotation ' + i + ' has a "label" that isn\'t text.');
        labelCheck(a.label);
        label = a.label;
      }
      var logAxis = axis === 'y' ? y : axis === 'y2' ? y2 : (chartType === 'scatter' ? x : null);
      if (logAxis && logAxis.scale === 'log' && value <= 0) {
        throw new Fail('Annotation ' + i + ' is on a log axis, so its value must be above 0.');
      }
      out.push({ axis: axis, value: value, label: label });
    }
    return out;
  }

  function validate(source) {
    var data;
    try {
      data = JSON.parse(source);
    } catch (err) {
      throw new Fail('The chart text isn\'t valid JSON.');
    }
    if (!isObject(data)) throw new Fail('The chart must be one JSON object.');
    if (!has(data, 'type')) throw new Fail('The chart needs a "type".');
    var chartType = data.type;
    if (typeof chartType !== 'string' || TYPES.indexOf(chartType) === -1) {
      throw new Fail('The chart "type" must be one of bar, line, area, scatter, pie or sparkline.');
    }
    var title = '';
    if (has(data, 'title')) {
      if (typeof data.title !== 'string') throw new Fail('The "title" must be text.');
      var tl = cpLen(data.title);
      if (tl > MAX_TITLE) throw new Fail('The title is ' + tl + ' characters; the limit is ' + MAX_TITLE + '.');
      title = data.title;
    }
    if (has(data, 'stacked') && typeof data.stacked !== 'boolean') {
      throw new Fail('The "stacked" setting must be true or false.');
    }
    var stacked = data.stacked === true && (chartType === 'bar' || chartType === 'area');

    var x = X_TYPES.indexOf(chartType) !== -1 ? parseAxis(data.x, 'x', chartType) : emptyAxis();
    var y = parseAxis(data.y, 'y', chartType);
    var y2 = null;
    if (Y2_TYPES.indexOf(chartType) !== -1 && !isNone(data.y2)) y2 = parseAxis(data.y2, 'y2', chartType);

    var raw = data.series;
    if (!Array.isArray(raw) || raw.length === 0) {
      throw new Fail('The chart needs a "series" list with at least one entry.');
    }
    var multiple = raw.length > 1;
    var series = [];
    var i;
    for (i = 0; i < raw.length; i++) {
      series.push(parseSeriesOne(raw[i], i, chartType, multiple, y2 !== null, raw));
    }

    if (chartType === 'pie' && series.length !== 1) {
      throw new Fail('A pie chart takes one series; this one has ' + series.length + '.');
    }
    var names = {};
    for (i = 0; i < series.length; i++) {
      if (multiple && has(names, series[i].name)) {
        throw new Fail('Two series are both named "' + series[i].name + '".');
      }
      names[series[i].name] = true;
    }
    if (chartType === 'bar' || chartType === 'line' || chartType === 'area' || chartType === 'pie') {
      var n = (x.values || []).length;
      for (i = 0; i < series.length; i++) {
        if (series[i].values.length !== n) {
          throw new Fail(seriesRef(raw, i) + ' has ' + series[i].values.length +
            ' values, but the x axis has ' + n + '.');
        }
      }
    }
    for (i = 0; i < series.length; i++) {
      var anyValue = false;
      for (var q = 0; q < series[i].values.length; q++) {
        if (series[i].values[q] !== null) { anyValue = true; break; }
      }
      if (!anyValue) throw new Fail(seriesRef(raw, i) + ' has no values to draw.');
    }
    if (chartType === 'pie') {
      var total = 0;
      for (i = 0; i < series[0].values.length; i++) {
        if (series[0].values[i] < 0) {
          throw new Fail(seriesRef(raw, 0) +
            ' has a negative value; a pie needs every slice at 0 or more.');
        }
        total += series[0].values[i];
      }
      if (total <= 0) throw new Fail('A pie chart needs a total above 0.');
    }
    for (i = 0; i < series.length; i++) {
      var vs = series[i].values;
      var k2;
      if (chartType === 'scatter') {
        if (y.scale === 'log') {
          for (k2 = 0; k2 < vs.length; k2++) {
            if (vs[k2][1] <= 0) {
              throw new Fail(seriesRef(raw, i) +
                ' has a value of 0 or less; a log scale needs every value above 0.');
            }
          }
        }
        if (x.scale === 'log') {
          for (k2 = 0; k2 < vs.length; k2++) {
            if (vs[k2][0] <= 0) {
              throw new Fail(seriesRef(raw, i) +
                ' has an x value of 0 or less; a log scale needs every x above 0.');
            }
          }
        }
      } else {
        var sideAxis = series[i].axis === 'right' && y2 !== null ? y2 : y;
        if (sideAxis.scale === 'log') {
          for (k2 = 0; k2 < vs.length; k2++) {
            if (vs[k2] !== null && vs[k2] <= 0) {
              throw new Fail(seriesRef(raw, i) +
                ' has a value of 0 or less; a log scale needs every value above 0.');
            }
          }
        }
      }
    }
    if (stacked && (y.scale === 'log' || (y2 !== null && y2.scale === 'log'))) {
      throw new Fail('A stacked chart can\'t use a log scale.');
    }

    var annotations = [];
    if (ANNOTATION_TYPES.indexOf(chartType) !== -1 && has(data, 'annotations') && data.annotations !== null) {
      annotations = parseAnnotations(data.annotations, chartType, x, y, y2);
    }

    var totalValues = 0;
    for (i = 0; i < series.length; i++) totalValues += series[i].values.length;
    if (totalValues > MAX_VALUES) {
      throw new Fail('This chart has ' + totalValues + ' values; the limit is ' + MAX_VALUES + '.');
    }
    if (X_TYPES.indexOf(chartType) !== -1 && chartType !== 'scatter' && x.values.length > MAX_CATEGORIES) {
      throw new Fail('This chart has ' + x.values.length + ' categories; the limit is ' + MAX_CATEGORIES + '.');
    }
    if (series.length > MAX_SERIES) {
      throw new Fail('This chart has ' + series.length + ' series; the limit is ' + MAX_SERIES + '.');
    }
    if (chartType === 'pie' && series[0].values.length > MAX_SLICES) {
      throw new Fail('This pie chart has ' + series[0].values.length + ' slices; the limit is ' + MAX_SLICES + '.');
    }
    if (annotations.length > MAX_ANNOTATIONS) {
      throw new Fail('This chart has ' + annotations.length + ' annotations; the limit is ' + MAX_ANNOTATIONS + '.');
    }
    return {
      type: chartType, title: title, x: x, y: y, y2: y2, series: series,
      stacked: stacked, annotations: annotations
    };
  }

  function parse(source) {
    try {
      return { ok: true, spec: validate(String(source)) };
    } catch (err) {
      if (err instanceof Fail) return { ok: false, message: err.message };
      return { ok: false, message: 'The chart couldn\'t be read.' };
    }
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

  function textWidth(text) { return cpLen(String(text)) * 6.4; }

  function truncate(text, max) {
    text = String(text);
    if (text.length <= max) return text;
    var cut = Math.max(1, max - 1);
    var c = text.charCodeAt(cut - 1);
    if (c >= 0xd800 && c <= 0xdbff) cut--;
    return text.slice(0, cut) + '…';
  }

  function xText(v) { return typeof v === 'number' ? formatFull(v, '') : String(v); }
  function xTick(v) { return typeof v === 'number' ? formatTick(v, '') : String(v); }

  function seriesName(s) { return s.name || 'Value'; }

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

  // ---------------------------------------------------------------------------------------
  // Layout: one function per family. Each fills the svg and returns the interaction view
  // {positions: [{x, y, title, rows: [{cls, name, value}], markers: [{x, y, cls}], slice}],
  //  top, bottom}.
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

  function tickWidth(axis, unit) {
    var w = 0;
    for (var j = 0; j < axis.ticks.length; j++) {
      w = Math.max(w, textWidth(formatTick(axis.ticks[j], unit)));
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
      l: Math.max(34, tickWidth(axL, spec.y.unit)),
      r: width - (axR ? Math.max(34, tickWidth(axR, spec.y2.unit)) : 12),
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

    // x tick labels, thinned to fit and truncated with an ellipsis.
    var maxText = 0;
    for (i = 0; i < n; i++) maxText = Math.max(maxText, textWidth(xTick(spec.x.values[i])));
    var stride = Math.max(1, Math.ceil((Math.min(maxText, 120) + 8) / band));
    var maxChars = Math.max(3, Math.floor((band * stride - 6) / 6.4));
    for (i = 0; i < n; i += stride) {
      svg.appendChild(svgText(SVG_CLASS.tick, cx(i), plot.b + 16, 'middle',
        truncate(xTick(spec.x.values[i]), Math.min(maxChars, 24))));
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

  function scaleDomainLo(side, axL, axR) { return side === 'right' && axR ? axR.d0 : axL.d0; }
  function scaleDomainHi(side, axL, axR) { return side === 'right' && axR ? axR.d1 : axL.d1; }

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
      l: Math.max(34, tickWidth(axY, spec.y.unit)),
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

  // ---------------------------------------------------------------------------------------
  // The control
  // ---------------------------------------------------------------------------------------

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
  App.ui.chart.formatTick = formatTick;
  App.ui.chart.formatFull = formatFull;

  // App.ui.chart.block(source, {closed, testid}) -> Node (DD9). The drawn chart for a valid
  // spec, otherwise the error notice: a danger "Couldn't draw this chart." with the validator's
  // sentence, or a muted "This chart was cut off before it finished." when the fence never
  // closed (closed === false). The source sits under "Technical details". Never throws.
  function errorBlock(source, reason, cutOff, opts) {
    var util = App.ui.util;
    var details = App.ui.disclosure({
      variant: 'plain',
      summary: 'Technical details',
      testid: opts.testid ? opts.testid + '-error-details' : null
    });
    details.body.appendChild(App.ui.codeBlock({ text: source, maxHeight: 'short', label: 'Chart source' }).el);
    var kids = [util.el('div', {
      className: 'ui-chart-error-head',
      text: cutOff ? 'This chart was cut off before it finished.' : 'Couldn\'t draw this chart.'
    })];
    if (!cutOff && reason) kids.push(util.el('div', { className: 'ui-chart-error-reason', text: reason }));
    kids.push(details.el);
    return App.ui.notice({
      tone: cutOff ? 'muted' : 'danger',
      body: util.el('div', { className: 'ui-chart-error' }, kids),
      testid: opts.testid ? opts.testid + '-error' : null
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
