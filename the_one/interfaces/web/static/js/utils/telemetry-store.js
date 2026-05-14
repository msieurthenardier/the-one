// M10 — telemetry store. Single source of live counts for the topnav
// chip strip, area headers, and empty-state stat rows. Plain
// observable — no framework. Initial values are em-dash placeholders
// (NOT zero — see spec §16 risk).
(function () {
  'use strict';

  var state = {
    sessions: '—',
    agents: '—',
    providers: '—',
    tools: '—',
    ctx: '—',
    ws_rtt_ms: '—',
    ws_state: 'down'  // 'down' | 'stale' | 'ok'
  };
  var subs = [];

  function get() {
    // Defensive copy to prevent mutation by consumers.
    return Object.assign({}, state);
  }

  function set(patch) {
    Object.assign(state, patch);
    for (var i = 0; i < subs.length; i++) {
      try {
        subs[i](get());
      } catch (e) {
        console.error('[TelemetryStore] subscriber threw:', e);
      }
    }
  }

  function subscribe(fn) {
    subs.push(fn);
    return function unsubscribe() {
      var idx = subs.indexOf(fn);
      if (idx >= 0) subs.splice(idx, 1);
    };
  }

  window.TelemetryStore = { get: get, set: set, subscribe: subscribe };
})();
