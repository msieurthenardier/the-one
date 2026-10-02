// App.store — shared client data layer (Mission 25 Flight 2 Leg 7, DD8).
//
// Collections (all list-shaped):
//   'agents'          GET /api/agents
//   'providers'       GET /api/providers
//   'knowledge-bases' GET /api/knowledge-bases       (M25 F3 L2, DD9)
//   'mcp-sources'     GET /api/mcp-sources           the PLAIN list: no
//                     self-configuration surface rows.  The agent editor's
//                     ?include_agent_surfaces=1 variant is detail-shaped and
//                     stays a direct fetch.
//   'connectors'      GET /api/connectors
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

  var URLS = {
    agents: '/api/agents',
    providers: '/api/providers',
    'knowledge-bases': '/api/knowledge-bases',
    'mcp-sources': '/api/mcp-sources',
    connectors: '/api/connectors'
  };
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

  // ── App.usage — "used by" counts derived from data (M25 F3 L2, DD9) ──
  //
  // Pure functions: no fetching, no DOM.  `agents` is the LIST-shaped agents
  // array (App.store.peek('agents').value, or what a get resolved with); a
  // missing or non-array argument counts as no agents.  Counts come from data,
  // never from what a page happens to render (A23).
  function arr(v) { return Array.isArray(v) ? v : []; }

  function countAgents(agents, test) {
    var n = 0;
    var list = arr(agents);
    for (var i = 0; i < list.length; i++) if (list[i] && test(list[i])) n += 1;
    return n;
  }

  // Agents whose provider is `providerId`.
  function providerAgents(agents, providerId) {
    return countAgents(agents, function (a) { return a.provider_config_id === providerId; });
  }

  // Agents with the knowledge base `kbId` attached.
  function kbAgents(agents, kbId) {
    return countAgents(agents, function (a) { return arr(a.kb_ids).indexOf(kbId) !== -1; });
  }

  // Agents with the MCP source `sourceId` attached.
  function mcpAgents(agents, sourceId) {
    return countAgents(agents, function (a) { return arr(a.mcp_source_ids).indexOf(sourceId) !== -1; });
  }

  // The DISTINCT agent names a connector routes to: config.default_agent plus
  // every config.channel_map value (inbound routing reads channel_map first,
  // then the default).  Empty and non-string values are skipped.  Returns the
  // names, in first-seen order; its length is the count.
  function connectorAgents(connector) {
    var cfg = (connector && connector.config) || {};
    var out = [];
    function add(name) {
      if (typeof name !== 'string' || name === '' || out.indexOf(name) !== -1) return;
      out.push(name);
    }
    add(cfg.default_agent);
    var map = cfg.channel_map;
    if (map && typeof map === 'object') {
      for (var k in map) if (Object.prototype.hasOwnProperty.call(map, k)) add(map[k]);
    }
    return out;
  }

  // The MCP source's cached tool count, or null when its tools have never
  // been loaded (no config._cache.tools): "Tools not loaded", not zero.
  function mcpToolCount(source) {
    var cache = source && source.config && source.config._cache;
    return cache && Array.isArray(cache.tools) ? cache.tools.length : null;
  }

  window.App = window.App || {};
  window.App.store = { get: get, peek: peek, invalidate: invalidate, subscribe: subscribe };
  window.App.usage = {
    providerAgents: providerAgents,
    kbAgents: kbAgents,
    mcpAgents: mcpAgents,
    connectorAgents: connectorAgents,
    mcpToolCount: mcpToolCount
  };
})();
