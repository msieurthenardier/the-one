// App.gleepglorp -- the client's one source for GleepGlorp's settings (M36 F1 L03).
//
// App.store holds list-shaped collections and cannot hold a single object, so GleepGlorp's
// settings ({enabled, provider_config_id, model, web_access, memory, retention_days, state})
// have this small module of their own. Same contract as App.store:
//
//   App.gleepglorp.get({force})  -> Promise of a COPY of the settings. Joins an in-flight
//       request; force refetches even when loaded. REJECTS on failure (the fetchJson error);
//       peek().value keeps the last good value.
//   App.gleepglorp.peek()        -> {value (copy|null), loaded, ok, error}
//   App.gleepglorp.invalidate()  -> a request started earlier is not joined by later gets
//       and never fills the cache.
//   App.gleepglorp.prime(obj)    -> replaces the value (a Save response, a later push), then
//       notifies subscribers with a copy.
//   App.gleepglorp.subscribe(fn) -> unsubscribe. fn(copy) after each load or prime.
(function () {
  'use strict';

  var URL = '/api/gleepglorp';
  var c = { value: null, loaded: false, ok: true, error: null, fresh: false, gen: 0,
            inflight: null, subs: [] };

  function copy(v) { return v === null || v === undefined ? null : JSON.parse(JSON.stringify(v)); }

  function notify() {
    c.subs.slice().forEach(function (fn) {
      try { fn(copy(c.value)); } catch (e) { console.error(e); }
    });
  }

  function startFetch() {
    var gen = c.gen;
    var p = window.App.api.fetchJson(URL).then(function (data) {
      if (gen === c.gen) {
        c.value = data; c.loaded = true; c.ok = true; c.error = null; c.fresh = true;
        if (c.inflight === p) c.inflight = null;
        notify();
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

  function get(opts) {
    var force = !!(opts && opts.force);
    if (c.inflight) return c.inflight.then(copy);
    if (c.loaded && c.ok && c.fresh && !force) return Promise.resolve(copy(c.value));
    return startFetch();
  }

  function peek() {
    return { value: copy(c.value), loaded: c.loaded, ok: c.ok, error: c.error };
  }

  function invalidate() {
    c.gen += 1; c.inflight = null; c.fresh = false;
  }

  function prime(obj) {
    c.gen += 1; c.inflight = null;
    c.value = copy(obj); c.loaded = true; c.ok = true; c.error = null; c.fresh = true;
    notify();
  }

  function subscribe(fn) {
    c.subs.push(fn);
    return function () {
      var i = c.subs.indexOf(fn);
      if (i !== -1) c.subs.splice(i, 1);
    };
  }

  window.App = window.App || {};
  window.App.gleepglorp = { get: get, peek: peek, invalidate: invalidate, prime: prime,
                            subscribe: subscribe };
})();
