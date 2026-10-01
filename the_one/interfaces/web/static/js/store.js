// App.store — shared client data layer (Mission 25 Flight 2 Leg 7, DD8).
//
// Collections: 'agents' (GET /api/agents) and 'providers' (GET /api/providers).
//
//   App.store.get(name, {force})  -> Promise of a COPY of the list.
//       Joins an in-flight request.  force=true joins an in-flight request
//       too, else refetches even when loaded.  REJECTS on failure with the
//       fetchJson error; peek().value keeps the last good value (ok:false)
//       and the next get retries.
//   App.store.peek(name)          -> {value (copy|null), loaded, ok, error}
//   App.store.invalidate(name)    -> bumps a generation: a request started
//       earlier is not joined by later gets and never populates the cache.
//   App.store.subscribe(name, fn) -> unsubscribe.  fn(copy) after each
//       successful load, including the first.
//
// Freshness: REST is the source of truth; invalidate() is the rebuild
// trigger; destination activation uses get(..., {force:true}) as the bound.
(function () {
  'use strict';

  var URLS = { agents: '/api/agents', providers: '/api/providers' };
  var cols = {};

  function copy(v) { return v === null || v === undefined ? null : JSON.parse(JSON.stringify(v)); }

  function col(name) {
    if (!URLS[name]) throw new Error('App.store: unknown collection ' + name);
    if (!cols[name]) {
      cols[name] = { value: null, loaded: false, ok: true, error: null,
                     fresh: false, gen: 0, inflight: null, subs: [] };
    }
    return cols[name];
  }

  function startFetch(name, c) {
    var gen = c.gen;
    var p = App.api.fetchJson(URLS[name]).then(function (data) {
      if (gen === c.gen) {
        c.value = data; c.loaded = true; c.ok = true; c.error = null; c.fresh = true;
        if (c.inflight === p) c.inflight = null;
        c.subs.slice().forEach(function (fn) {
          try { fn(copy(c.value)); } catch (e) { console.error(e); }
        });
      }
      return copy(data);
    }, function (err) {
      if (gen === c.gen) {
        c.ok = false; c.error = err;
        if (c.inflight === p) c.inflight = null;
      }
      throw err;
    });
    c.inflight = p;
    return p;
  }

  function get(name, opts) {
    var c = col(name);
    var force = !!(opts && opts.force);
    if (c.inflight) return c.inflight.then(copy);
    if (!force && c.loaded && c.fresh && c.ok) return Promise.resolve(copy(c.value));
    return startFetch(name, c).then(copy);
  }

  function peek(name) {
    var c = col(name);
    return { value: copy(c.value), loaded: c.loaded, ok: c.ok, error: c.error };
  }

  function invalidate(name) {
    var c = col(name);
    c.gen += 1;
    c.fresh = false;
    c.inflight = null;
  }

  function subscribe(name, fn) {
    var c = col(name);
    c.subs.push(fn);
    return function () {
      var i = c.subs.indexOf(fn);
      if (i >= 0) c.subs.splice(i, 1);
    };
  }

  window.App = window.App || {};
  window.App.store = { get: get, peek: peek, invalidate: invalidate, subscribe: subscribe };
})();
