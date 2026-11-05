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
//   'secrets'         GET /api/secrets                (sortie 10, DD1) rows
//                     {id, name, description, allowed_tools, values: [{id, key,
//                     value: "__MASKED__"}], ...}; every secret write
//                     invalidates it, a secret DELETE also invalidates 'agents'
//                     (the server strips the id from their secret_ids).
//   'sessions'       GET /api/chat/sessions            (M25 F4 L1, DD4)
//                     rows {id, agent_name, title, created_at, updated_at,
//                     platform}; the chat area also PRIMES it from every
//                     WebSocket session_list reply (mapped to that shape).
//
//   App.store.get(name, {force})  -> Promise of a COPY of the list.
//       Joins an in-flight request.  force=true joins an in-flight request
//       too, else refetches even when loaded.  REJECTS on failure with the
//       fetchJson error; peek().value keeps the last good value (ok:false)
//       and the next get retries.
//   App.store.peek(name)          -> {value (copy|null), loaded, ok, error}
//   App.store.invalidate(name)    -> bumps a generation: a request started
//       earlier is not joined by later gets and never populates the cache.
//   App.store.prime(name, rows)   -> replaces the value with a copy of rows
//       pushed from elsewhere (a WebSocket reply): loaded, ok and fresh all
//       true.  Bumps the generation and clears the in-flight request like
//       invalidate(), so an older racing get neither overwrites the primed
//       value nor notifies (its own caller still gets its own data), and a
//       later get resolves from the primed cache without a fetch.  Then
//       notifies subscribers with a copy.  An unknown name throws.
//   App.store.subscribe(name, fn) -> unsubscribe.  fn(copy) after each
//       successful load or prime, including the first.
//
// Freshness: REST is the source of truth; invalidate() is the rebuild
// trigger; destination activation uses get(..., {force:true}) as the bound.
// 'sessions' is the exception while Chats is active: the WebSocket is its
// source (session_list primes it), with no extra REST fetches.
(function () {
  'use strict';

  var URLS = {
    agents: '/api/agents',
    providers: '/api/providers',
    'knowledge-bases': '/api/knowledge-bases',
    'mcp-sources': '/api/mcp-sources',
    connectors: '/api/connectors',
    secrets: '/api/secrets',
    sessions: '/api/chat/sessions'
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

  function prime(name, rows) {
    var c = col(name);
    c.gen += 1;
    c.inflight = null;
    c.value = copy(rows);
    c.loaded = true; c.ok = true; c.error = null; c.fresh = true;
    c.subs.slice().forEach(function (fn) {
      try { fn(copy(c.value)); } catch (e) { console.error(e); }
    });
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

  // The DISTINCT agent names (first-seen order) whose secret_ids hold `secretId`
  // (sortie 10); its length is the count.
  function secretAgents(agents, secretId) {
    var out = [];
    var list = arr(agents);
    for (var i = 0; i < list.length; i++) {
      var a = list[i];
      if (a && arr(a.secret_ids).indexOf(secretId) !== -1 && out.indexOf(a.name) === -1) out.push(a.name);
    }
    return out;
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
  // been loaded (no config._cache.tools): not zero (the Library list now reads mcpState instead).
  function mcpToolCount(source) {
    var cache = source && source.config && source.config._cache;
    return cache && Array.isArray(cache.tools) ? cache.tools.length : null;
  }

  // The MCP source's connection state, derived from what the server stored
  // (leg 08a, DD6): {state: 'signin'|'error'|'connected'|'none', tools, checkedAt}.
  // `lc` is config._cache.last_check (the last Studio connection check) or null.
  // Precedence: (1) signin when there is no access token and either an OAuth
  // session exists or the last check said auth_required; (2) error when the last
  // check errored; (3) connected when tools are cached (so, with a token, a stale
  // auth_required reads connected); (4) none.  `checkedAt` is lc.at, else
  // _cache.last_updated, in SECONDS (callers multiply by 1000), or null.
  function mcpState(source) {
    var cache = (source && source.config && source.config._cache) || null;
    var lc = cache && cache.last_check && typeof cache.last_check === 'object' ?
      cache.last_check : null;
    var tools = cache && Array.isArray(cache.tools) ? cache.tools.length : null;
    var checkedAt = null;
    if (lc && typeof lc.at === 'number') checkedAt = lc.at;
    else if (cache && typeof cache.last_updated === 'number') checkedAt = cache.last_updated;
    var state = 'none';
    if (!(source && source.has_access_token) &&
        ((source && source.oauth_active) || (lc && lc.status === 'auth_required'))) {
      state = 'signin';
    } else if (lc && lc.status === 'error') {
      state = 'error';
    } else if (tools !== null) {
      state = 'connected';
    }
    return { state: state, tools: tools, checkedAt: checkedAt };
  }

  // The words for a state: the one source for the editor and the Library list.
  function mcpStateLabel(state) {
    if (state === 'signin') return 'Sign-in needed';
    if (state === 'error') return "Couldn't connect";
    if (state === 'connected') return 'Connected';
    return 'Not connected';
  }

  window.App = window.App || {};
  window.App.store = { get: get, peek: peek, invalidate: invalidate, prime: prime, subscribe: subscribe };
  window.App.usage = {
    providerAgents: providerAgents,
    kbAgents: kbAgents,
    mcpAgents: mcpAgents,
    connectorAgents: connectorAgents,
    secretAgents: secretAgents,
    mcpToolCount: mcpToolCount,
    mcpState: mcpState,
    mcpStateLabel: mcpStateLabel
  };
})();
