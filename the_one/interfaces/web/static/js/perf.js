// App.perf — F7 performance measurement substrate.
//
// Gated by ?perf=1 in URL query string OR localStorage.getItem('the-one-perf') === '1'.
// Production paths pay zero cost (no-op when disabled).
//
// Public surface:
//   App.perf.enabled    -> boolean
//   App.perf.mark(name) -> void
//   App.perf.measure(name, startMark, endMark) -> void
//   App.perf.captureHeap() -> { usedJSHeapSize, totalJSHeapSize, jsHeapSizeLimit, timestamp } | null
//   App.perf.dump() -> { enabled, marks: PerformanceEntry[], measures: PerformanceEntry[], heap: object|null }
//   App.perf.summary() -> { enabled, measures: {[name]: {count, p50, p95, max}}, heap: object|null }
//   App.perf.reset() -> void
//
// The dump() output is the canonical operator-readable export; capture via
// Chrome DevTools MCP's evaluate_script + list_console_messages.
(function () {
  'use strict';
  window.App = window.App || {};

  function isEnabled() {
    try {
      var u = new URL(window.location.href);
      if (u.searchParams.get('perf') === '1') return true;
    } catch (e) { /* IE / legacy — fall through */ }
    try {
      return window.localStorage.getItem('the-one-perf') === '1';
    } catch (e) {
      return false;
    }
  }

  var enabled = isEnabled();

  function mark(name) {
    if (!enabled || typeof performance === 'undefined' || !performance.mark) return;
    try { performance.mark(name); } catch (e) { /* swallow — same mark twice is fine */ }
  }

  function measure(name, startMark, endMark) {
    if (!enabled || typeof performance === 'undefined' || !performance.measure) return;
    try { performance.measure(name, startMark, endMark); } catch (e) { /* swallow */ }
  }

  function captureHeap() {
    if (!enabled) return null;
    var m = (typeof performance !== 'undefined') && performance.memory;
    if (!m) return null;
    return {
      usedJSHeapSize: m.usedJSHeapSize,
      totalJSHeapSize: m.totalJSHeapSize,
      jsHeapSizeLimit: m.jsHeapSizeLimit,
      timestamp: Date.now()
    };
  }

  function entriesAsArray(type) {
    if (typeof performance === 'undefined' || !performance.getEntriesByType) return [];
    return performance.getEntriesByType(type).map(function (e) {
      return { name: e.name, startTime: e.startTime, duration: e.duration };
    });
  }

  function dump() {
    return {
      enabled: enabled,
      marks: enabled ? entriesAsArray('mark') : [],
      measures: enabled ? entriesAsArray('measure') : [],
      heap: captureHeap()
    };
  }

  function reset() {
    if (!enabled || typeof performance === 'undefined') return;
    try {
      performance.clearMarks();
      performance.clearMeasures();
    } catch (e) { /* swallow */ }
  }

  // Cycle-1 reviewer addition: aggregator avoids dump-payload bloat when
  // many entries share a name (e.g. 100 addMsg measures from session-join
  // replay). Returns count + percentile durations per measure name.
  function percentile(sorted, p) {
    if (sorted.length === 0) return 0;
    var idx = Math.min(sorted.length - 1, Math.floor(sorted.length * p));
    return sorted[idx];
  }

  function summary() {
    if (!enabled) return { enabled: false, measures: {}, heap: null };
    var byName = {};
    var measures = entriesAsArray('measure');
    for (var i = 0; i < measures.length; i++) {
      var m = measures[i];
      (byName[m.name] = byName[m.name] || []).push(m.duration);
    }
    var out = {};
    for (var name in byName) {
      if (!Object.prototype.hasOwnProperty.call(byName, name)) continue;
      var arr = byName[name].slice().sort(function (a, b) { return a - b; });
      out[name] = {
        count: arr.length,
        p50: percentile(arr, 0.5),
        p95: percentile(arr, 0.95),
        max: arr[arr.length - 1]
      };
    }
    return { enabled: true, measures: out, heap: captureHeap() };
  }

  window.App.perf = {
    enabled: enabled,
    mark: mark,
    measure: measure,
    captureHeap: captureHeap,
    dump: dump,
    summary: summary,
    reset: reset
  };
})();
