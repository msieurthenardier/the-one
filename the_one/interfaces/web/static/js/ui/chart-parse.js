(function () {
  'use strict';
  window.App = window.App || {};

  // Chart internals, part 1 of 3 (M35 F2 L2, split out of ui/chart.js): number display and
  // validation. The format is specified once in docs/chart-format.md, with the shared corpus in
  // tests/fixtures/charts/; the Python validator the_one/visuals/chart_spec.py is the second
  // implementation of the same document, and both are tested against the corpus with identical
  // sentences. This file is NOT a control: it defines no App.ui factory and shares its
  // functions through the private App.ui.util.chartParts namespace, which ui/chart.js reads.
  // Load order: chart-parse.js, chart-scale.js, chart-layout.js, chart.js.

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

  var parts = window.App.ui.util.chartParts = window.App.ui.util.chartParts || {};
  parts.has = has;
  parts.cpLen = cpLen;
  parts.formatTick = formatTick;
  parts.formatFull = formatFull;
  parts.parse = parse;
})();
