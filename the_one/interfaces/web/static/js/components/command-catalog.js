// L8 — command palette action catalog.
//
// Static actions: navigation + theme + reload + new-session.
// Dynamic actions: agents, providers, sessions — fetched lazily per
// open, cached for 5s. All endpoints are GETs that already exist.
//
// Sessions endpoint: /api/chat/sessions (NOT /api/sessions; the bare
// /api/sessions path does not exist — same gotcha telemetry-refresh.js
// documents at lines 6 + 22).
(function () {
  'use strict';

  var CACHE_TTL_MS = 5000;
  var SESSION_LIMIT = 10;

  var cache = {
    agents: null,
    providers: null,
    sessions: null,
    fetchedAt: 0,
  };

  function fresh() { return Date.now() - cache.fetchedAt < CACHE_TTL_MS; }

  function staticActions() {
    var nav = [
      { id: 'go-chat',     section: 'NAVIGATION', label: 'Go to Chat',                hash: '#chat' },
      { id: 'go-studio',   section: 'NAVIGATION', label: 'Go to Studio',              hash: '#studio' },
      { id: 'go-system',   section: 'NAVIGATION', label: 'Go to System',              hash: '#admin' },
      { id: 'go-providers',section: 'NAVIGATION', label: 'Open Providers',            hash: '#admin/providers' },
      { id: 'go-agents',   section: 'NAVIGATION', label: 'Open Agents',               hash: '#studio/agents' },
      { id: 'go-tools',    section: 'NAVIGATION', label: 'Open Built-in Tools',       hash: '#admin/tools' },
      { id: 'go-mcps',     section: 'NAVIGATION', label: 'Open MCP Servers',          hash: '#studio/mcps' },
    ];

    var current = (window.App && window.App.theme) ? window.App.theme.get() : null;
    var themes = [
      { id: 'theme-light', section: 'ACTIONS', label: 'Theme: Light', themeMode: 'light' },
      { id: 'theme-dark',  section: 'ACTIONS', label: 'Theme: Dark',  themeMode: 'dark'  },
      { id: 'theme-auto',  section: 'ACTIONS', label: 'Theme: Auto',  themeMode: 'auto'  },
    ].filter(function (t) { return t.themeMode !== current; });

    var actions = [
      { id: 'new-session', section: 'ACTIONS', label: 'New session', event: 'chat:new-session' },
      { id: 'reload',      section: 'ACTIONS', label: 'Reload app',  builtin: 'reload' },
    ];

    return nav.concat(themes).concat(actions);
  }

  function fetchJSON(path) {
    return fetch(path, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error(path + ' ' + r.status)); });
  }

  // Returns a Promise<Array<item>>.  Items have shape:
  //   { id, section, label, keywords?, hash?, themeMode?, event?, builtin?, invoke? }
  function build() {
    var staticItems = staticActions();

    if (fresh() && cache.agents && cache.providers && cache.sessions) {
      return Promise.resolve(staticItems.concat(cache.agents, cache.providers, cache.sessions));
    }

    return Promise.all([
      fetchJSON('/api/agents').catch(function () { return []; }),
      fetchJSON('/api/providers').catch(function () { return []; }),
      fetchJSON('/api/chat/sessions').catch(function () { return []; }),
    ]).then(function (results) {
      var agents = results[0] || [];
      var providers = results[1] || [];
      var sessions = results[2] || [];

      cache.agents = agents.map(function (a) {
        return {
          id: 'agent-' + (a.name || a.id),
          section: 'AGENTS',
          label: 'Switch to agent: ' + (a.name || a.id),
          keywords: (a.persona || '') + ' ' + (a.model || ''),
          event: 'chat:switch-agent',
          eventDetail: { name: a.name || a.id },
        };
      });
      cache.providers = providers.map(function (p) {
        return {
          id: 'provider-' + (p.id || p.name),
          section: 'PROVIDERS',
          label: 'Edit provider: ' + (p.name || p.id),
          keywords: p.provider_type || '',
          hash: '#admin/providers?edit=' + encodeURIComponent(p.id || p.name),
        };
      });
      // Client-side sort + limit — the endpoint does not accept ?limit.
      cache.sessions = sessions
        .slice()
        .sort(function (a, b) { return (b.updated_at || 0) - (a.updated_at || 0); })
        .slice(0, SESSION_LIMIT)
        .map(function (s) {
          return {
            id: 'session-' + s.id,
            section: 'SESSIONS',
            label: 'Open session: ' + (s.title || s.id),
            hash: '#chat?session=' + encodeURIComponent(s.id),
          };
        });
      cache.fetchedAt = Date.now();
      return staticItems.concat(cache.agents, cache.providers, cache.sessions);
    });
  }

  // For tests + the palette's "Some results unavailable" status.
  function lastFetchHadFailures() {
    return !(cache.agents && cache.providers && cache.sessions);
  }

  function invoke(item) {
    if (item.hash) { window.location.hash = item.hash; return; }
    if (item.themeMode && window.App && window.App.theme) {
      window.App.theme.set(item.themeMode); return;
    }
    if (item.event) {
      document.dispatchEvent(new CustomEvent(item.event, { detail: item.eventDetail || {} }));
      return;
    }
    if (item.builtin === 'reload') { window.location.reload(); return; }
  }

  window.App = window.App || {};
  window.App.commandCatalog = {
    build: build,
    invoke: invoke,
    lastFetchHadFailures: lastFetchHadFailures,
    // For tests:
    _resetCache: function () { cache = { agents: null, providers: null, sessions: null, fetchedAt: 0 }; },
  };
})();
