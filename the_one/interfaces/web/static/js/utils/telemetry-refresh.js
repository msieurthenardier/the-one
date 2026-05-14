// M10 — telemetry refresh. Fetches API counts and pushes them into
// TelemetryStore. Called on area mount and after operator actions
// that change counts (provider create/delete, agent create/delete).
//
// Note on session endpoint: the project's chat-sessions API lives at
// `/api/chat/sessions` (not `/api/sessions`). All four endpoints return
// JSON arrays; non-array shapes are silently skipped so a future
// envelope migration won't 500 the page.
(function () {
  'use strict';

  function fetchJSON(url) {
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  function refresh() {
    Promise.all([
      fetchJSON('/api/providers'),
      fetchJSON('/api/agents'),
      fetchJSON('/api/chat/sessions'),
      fetchJSON('/api/tools/configs')
    ]).then(function (results) {
      var providers = results[0];
      var agents = results[1];
      var sessions = results[2];
      var tools = results[3];

      var patch = {};
      if (Array.isArray(providers)) patch.providers = providers.length;
      if (Array.isArray(agents)) patch.agents = agents.length;
      if (Array.isArray(sessions)) patch.sessions = sessions.length;
      if (Array.isArray(tools)) patch.tools = tools.length;

      if (Object.keys(patch).length > 0) {
        window.TelemetryStore.set(patch);
      }
    });
  }

  window.TelemetryRefresh = { refresh: refresh };
})();
