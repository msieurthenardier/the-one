// App.studio.agentData -- the studio area's network layer and shared caches
// (M31 F2 L02a, DD1): the agent / tool / MCP / rules / notes / self-configuration /
// credential wrappers, the operator-state and knowledge-base caches, the lazy
// schema and MCP-tools fetchers and loadAll. Moved verbatim out of studio.js;
// a factory it calls once in init, on the providers-section.js precedent:
//
//   var agentData = App.studio.agentData.create(ctx);
//
// The module reaches studio only through `ctx`; the five Library
// App.store.subscribe calls and the agent subscriptions stay in the shell,
// which calls the handle.
//
// ctx (studio -> module):
//   self                       the area object (_agents, _allTools, _allMcpSources,
//                              _allKnowledgeBases, _allProviders, _disabledTools,
//                              _operatorConfigs and the loaded flags live on it)
//   content                    the area's content element (the non-destructive
//                              load-error flash)
//   sectionContentEl           the section-content host (the load-error banner)
//   renderAgentList(scroll)    the Agents list render, called by loadAll
//   onSelfConfigChanged(updated)  after a self-configuration write refetched the
//                              agent: studio re-seats it (doSelect today; leg 10
//                              changes it, DD9-3)
//
// handle (module -> studio): EVERY wrapper under its existing name (the agent
// editor takes about 30 of them by reference), plus loadAllDepth() -- the
// number of loadAll calls in flight, read by the agent / provider
// subscriptions that ignore a notification while studio's own load runs.
window.App = window.App || {};
window.App.studio = window.App.studio || {};

App.studio.agentData = {
  create: function (ctx) {
    var self = ctx.self;

    // Operator-state caches (see refreshToolConfigsCache below).
    self._disabledTools = new Set();
    self._operatorConfigs = {};

    // ── Data fetching ────────────────────────────────────────────────

    function fetchAgents(force) { return App.store.get('agents', { force: !!force }); }
    function fetchTools() { return App.api.fetchJson('/api/tools'); }
    // M21 F01 L02 (DD3): the editor's fetch — as opposed to the Library
    // list's store collection ('mcp-sources', the plain list) — includes
    // per-agent self-configuration surface rows so the agent editor's MCPs
    // tab and Self-configuration tab can see them; the Library list excludes
    // them (no query param there).
    function fetchMcpSources() {
      return App.api.fetchJson('/api/mcp-sources?include_agent_surfaces=1');
    }

    // M27 F1 L2 -- rules network calls (DD8). fetchJson surfaces a 422's
    // `detail` as the Error message, which the tab shows inline.
    function rulesUrl(name, suffix) {
      return '/api/agents/' + encodeURIComponent(name) + '/rules' + (suffix || '');
    }
    function rulesJson(method, url, body) {
      var opts = { method: method };
      if (body !== undefined) {
        opts.headers = { 'Content-Type': 'application/json' };
        opts.body = JSON.stringify(body);
      }
      return App.api.fetchJson(url, opts);
    }
    function fetchRules(name) { return App.api.fetchJson(rulesUrl(name)); }
    function createRule(name, text) { return rulesJson('POST', rulesUrl(name), { text: text }); }
    function updateRule(name, id, patch) {
      return rulesJson('PUT', rulesUrl(name, '/' + encodeURIComponent(id)), patch);
    }
    function deleteRule(name, id) {
      return rulesJson('DELETE', rulesUrl(name, '/' + encodeURIComponent(id)));
    }
    function reorderRules(name, ids) { return rulesJson('PUT', rulesUrl(name, '/order'), { ids: ids }); }

    // M27 F2 L3 -- notes network calls (DD11). The same fetchJson contract.
    function notesUrl(name, suffix) {
      return '/api/agents/' + encodeURIComponent(name) + '/notes' + (suffix || '');
    }
    function fetchNotes(name) { return App.api.fetchJson(notesUrl(name)); }
    function setNotesEnabled(name, enabled) {
      return rulesJson('PUT', notesUrl(name, '/settings'), { enabled: !!enabled });
    }
    function updateNote(name, id, text) {
      return rulesJson('PUT', notesUrl(name, '/' + encodeURIComponent(id)), { text: text });
    }
    function deleteNote(name, id) {
      return rulesJson('DELETE', notesUrl(name, '/' + encodeURIComponent(id)));
    }
    function clearNotes(name) { return rulesJson('DELETE', notesUrl(name)); }

    // M33 F1 L8 -- routines network calls (same fetchJson contract: a failure carries
    // `status` and `detail`).
    function routinesUrl(name, suffix) {
      return '/api/agents/' + encodeURIComponent(name) + '/routines' + (suffix || '');
    }
    function fetchRoutines(name) { return App.api.fetchJson(routinesUrl(name)); }
    function createRoutine(name, body) { return rulesJson('POST', routinesUrl(name), body); }
    function updateRoutine(name, id, patch) {
      return rulesJson('PUT', routinesUrl(name, '/' + encodeURIComponent(id)), patch);
    }
    function deleteRoutine(name, id) {
      return rulesJson('DELETE', routinesUrl(name, '/' + encodeURIComponent(id)));
    }
    function runRoutine(name, id) {
      return rulesJson('POST', routinesUrl(name, '/' + encodeURIComponent(id) + '/run'));
    }
    function fetchRoutineRuns(name, id, opts) {
      var q = 'limit=' + encodeURIComponent((opts && opts.limit) || 20);
      if (opts && opts.before) q += '&before=' + encodeURIComponent(opts.before);
      return App.api.fetchJson(routinesUrl(name, '/' + encodeURIComponent(id) + '/runs') + '?' + q);
    }

    // M33 F2 L5 -- the Self-configuration tab's Routines item: the two switches and the
    // agent's routine-change proposals. Same fetchJson contract: a failure carries `status`
    // and `detail` (the approve 409s keep their `{error, ...}` object on `detail`).
    function routinesItemUrl(name, suffix) {
      return '/api/agents/' + encodeURIComponent(name) + '/self-configuration/routines' +
        (suffix || '');
    }
    function fetchRoutinesItem(name) { return App.api.fetchJson(routinesItemUrl(name)); }
    function putRoutinesItem(name, patch) {
      return rulesJson('PUT', routinesItemUrl(name), patch);
    }
    function fetchRoutineProposals(name, opts) {
      opts = opts || {};
      var q = 'limit=' + encodeURIComponent(opts.limit || 20);
      if (opts.status) q += '&status=' + encodeURIComponent(opts.status);
      if (opts.before) q += '&before=' + encodeURIComponent(opts.before);
      return App.api.fetchJson(routinesItemUrl(name, '/proposals') + '?' + q);
    }
    function approveRoutineProposal(name, id, override) {
      return rulesJson('POST', routinesItemUrl(name, '/proposals/' + encodeURIComponent(id) +
        '/approve') + (override ? '?override=true' : ''));
    }
    function dismissRoutineProposal(name, id) {
      return rulesJson('POST', routinesItemUrl(name, '/proposals/' + encodeURIComponent(id) +
        '/dismiss'));
    }

    // M21 F01 L02 — self-configuration status/enable/disable network calls.
    function fetchSelfConfigurationStatus(name) {
      return fetch('/api/agents/' + encodeURIComponent(name) + '/self-configuration')
        .then(function (r) {
          if (!r.ok) throw new Error('fetchSelfConfigurationStatus: HTTP ' + r.status);
          return r.json();
        });
    }

    function _refreshAgentAfterSelfConfigurationChange(name) {
      // Every self-configuration enable/disable/approval/revision write funnels
      // here; the server-side agent changed, so the shared list is stale (DD8).
      App.store.invalidate('agents');
      // Re-fetch both the MCP sources cache (the surface row was just
      // created/destroyed server-side) AND the agent itself (its
      // mcp_source_ids just changed server-side, outside the Save flow).
      // The editor controller's onSelfConfigChanged patches the open editor in
      // place (M31 F2 L10a), so unsaved edits survive and the Tools tab reflects
      // the new/removed row without a reload.
      return Promise.all([
        refreshMcpSourcesCache(),
        App.api.fetchJson('/api/agents/' + encodeURIComponent(name))
      ]).then(function (results) {
        var updated = results[1];
        for (var i = 0; i < self._agents.length; i++) {
          if (self._agents[i].name === name) { self._agents[i] = updated; break; }
        }
        ctx.onSelfConfigChanged(updated);
        return updated;
      });
    }

    function enableSelfConfiguration(name) {
      return fetch('/api/agents/' + encodeURIComponent(name) + '/self-configuration', { method: 'POST' })
        .then(function (r) {
          if (!r.ok) throw new Error('enable self-configuration: HTTP ' + r.status);
          return r.json();
        })
        .then(function (result) {
          return _refreshAgentAfterSelfConfigurationChange(name).then(function () { return result; });
        });
    }

    function disableSelfConfiguration(name) {
      return fetch('/api/agents/' + encodeURIComponent(name) + '/self-configuration', { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) throw new Error('disable self-configuration: HTTP ' + r.status);
          return r.json();
        })
        .then(function () {
          return _refreshAgentAfterSelfConfigurationChange(name).then(function () {
            return { enabled: false };
          });
        });
    }

    // M21 F02 L02 — approval-mode toggle + revision-queue network calls.
    function setSelfConfigurationApprovalMode(name, requiresApproval) {
      return fetch('/api/agents/' + encodeURIComponent(name) + '/self-configuration/approval-mode', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ requires_approval: !!requiresApproval })
      })
        .then(function (r) {
          if (!r.ok) throw new Error('set approval mode: HTTP ' + r.status);
          return r.json();
        })
        .then(function (result) {
          // The flag lives outside the Save flow; the editor is patched and the
          // tab refetches its status.
          return _refreshAgentAfterSelfConfigurationChange(name).then(function () { return result; });
        });
    }

    function fetchSelfConfigurationRevisions(name) {
      return fetch('/api/agents/' + encodeURIComponent(name) + '/self-configuration/revisions')
        .then(function (r) {
          if (!r.ok) throw new Error('fetch revisions: HTTP ' + r.status);
          return r.json();
        });
    }

    function approveSelfConfigurationRevision(name, id, override) {
      var url = '/api/agents/' + encodeURIComponent(name) +
        '/self-configuration/revisions/' + encodeURIComponent(id) + '/approve' +
        (override ? '?override=true' : '');
      return fetch(url, { method: 'POST' }).then(function (r) {
        if (r.status === 409) {
          return r.json().then(function (body) {
            var detail = body && body.detail;
            if (detail && detail.error === 'stale') {
              // DD4 staleness — surface both values so the tab can render
              // the current-vs-proposed override affordance (not a throw).
              return { stale: true, detail: detail };
            }
            throw new Error('approve revision: HTTP 409');
          });
        }
        if (!r.ok) throw new Error('approve revision: HTTP ' + r.status);
        return r.json().then(function (rev) {
          return _refreshAgentAfterSelfConfigurationChange(name).then(function () {
            return { applied: true, revision: rev };
          });
        });
      });
    }

    function dismissSelfConfigurationRevision(name, id) {
      var url = '/api/agents/' + encodeURIComponent(name) +
        '/self-configuration/revisions/' + encodeURIComponent(id) + '/dismiss';
      return fetch(url, { method: 'POST' }).then(function (r) {
        if (!r.ok) throw new Error('dismiss revision: HTTP ' + r.status);
        return r.json().then(function (rev) {
          return _refreshAgentAfterSelfConfigurationChange(name).then(function () { return rev; });
        });
      });
    }

    // M21 F02 L03 — operator-direct restore. `side` selects the value node
    // (proposed = the target row's after-image; base = its before-image, the
    // only way to reach the original pre-first-revision value). Applies
    // immediately regardless of approval mode; on success re-render the tab
    // so the fresh revision list shows the new restore row.
    function restoreSelfConfigurationRevision(name, id, side) {
      var url = '/api/agents/' + encodeURIComponent(name) +
        '/self-configuration/revisions/' + encodeURIComponent(id) + '/restore' +
        '?side=' + encodeURIComponent(side || 'proposed');
      return fetch(url, { method: 'POST' }).then(function (r) {
        if (!r.ok) throw new Error('restore revision: HTTP ' + r.status);
        return r.json().then(function (rev) {
          return _refreshAgentAfterSelfConfigurationChange(name).then(function () { return rev; });
        });
      });
    }

    // M21 F03 L03 — external-client credential grant/list/revoke/rotate
    // network calls (over Leg 1's endpoints). Deliberately NOT routed
    // through `_refreshAgentAfterSelfConfigurationChange`: mint/rotate
    // return the full `ext_<id>.<secret>` token exactly once, and a whole-
    // editor re-render would tear down the copy-once reveal before the
    // operator can copy it. The Self-configuration tab re-fetches the list
    // locally instead; the reveal persists until dismiss or the next full
    // tab render.
    function mintExternalCredential(name, label) {
      return fetch('/api/agents/' + encodeURIComponent(name) +
        '/self-configuration/external-credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: label })
      }).then(function (r) {
        if (!r.ok) throw new Error('mint external credential: HTTP ' + r.status);
        return r.json();
      });
    }

    function fetchExternalCredentials(name) {
      return fetch('/api/agents/' + encodeURIComponent(name) +
        '/self-configuration/external-credentials').then(function (r) {
        if (!r.ok) throw new Error('fetch external credentials: HTTP ' + r.status);
        return r.json();
      });
    }

    function revokeExternalCredential(name, identifier) {
      return fetch('/api/agents/' + encodeURIComponent(name) +
        '/self-configuration/external-credentials/' + encodeURIComponent(identifier), {
        method: 'DELETE'
      }).then(function (r) {
        if (!r.ok) throw new Error('revoke external credential: HTTP ' + r.status);
        return r.json();
      });
    }

    function rotateExternalCredential(name, identifier) {
      return fetch('/api/agents/' + encodeURIComponent(name) +
        '/self-configuration/external-credentials/' + encodeURIComponent(identifier) +
        '/rotate', { method: 'POST' }).then(function (r) {
        if (!r.ok) throw new Error('rotate external credential: HTTP ' + r.status);
        return r.json();
      });
    }

    // M25 F3 L2 (DD9): through App.store. `force` as the other loadAll reads:
    // activation (init / _refresh) and the agent-edit mount refresh force (and
    // join an in-flight request); a post-mutation loadAll() reads the cache
    // unless a knowledge-base mutation invalidated it.
    function fetchKnowledgeBases(force) { return App.store.get('knowledge-bases', { force: !!force }); }
    function fetchProviders(force) { return App.store.get('providers', { force: !!force }); }

    // ── F6 leg 05 — tool configs (operator state) + schema cache ──────
    //
    // Operator-state caches. `_disabledTools` (Set<string>) and
    // `_operatorConfigs` ({name → {enabled, config}}) are RE-fetched on
    // every agent-edit mount — the operator may have flipped a toggle in
    // another tab between agent edits. The schema cache below survives
    // across agent changes (schemas are static at runtime).
    function fetchToolConfigs() {
      return App.api.fetchJson('/api/tools/configs');
    }

    function refreshToolConfigsCache() {
      return fetchToolConfigs().then(function (configs) {
        var disabled = new Set();
        var byName = {};
        for (var i = 0; i < configs.length; i++) {
          var c = configs[i];
          byName[c.name] = { enabled: !!c.enabled, config: c.config || {} };
          if (!c.enabled) disabled.add(c.name);
        }
        self._disabledTools = disabled;
        self._operatorConfigs = byName;
      }).catch(function () {
        // On error, keep prior caches; the tools tab still renders with
        // pre-L5 baseline (no disabled-tool styling, no override panels).
        self._disabledTools = self._disabledTools || new Set();
        self._operatorConfigs = self._operatorConfigs || {};
      });
    }

    // F9 L3 (A-L3-1) — re-fetch the MCP sources list on every agent-edit
    // mount. `_allMcpSources` is otherwise loaded once at studio area mount
    // (loadAll), so a source created on the source-edit page is invisible
    // to the agent editor until the operator hard-reloads. Mirrors
    // refreshToolConfigsCache above. On error, keep the prior cache.
    function refreshMcpSourcesCache() {
      return fetchMcpSources().then(function (sources) {
        self._allMcpSources = sources;
        self._mcpSourcesLoaded = true;
      }).catch(function () {
        self._allMcpSources = self._allMcpSources || [];
      });
    }

    // F6 L3 (L3-D1) — re-fetch the knowledge-base list on every agent-edit
    // mount, mirroring refreshMcpSourcesCache exactly: `_allKnowledgeBases`
    // was otherwise populated once in `loadAll()` and read nowhere else
    // (DD-15 — a knowledge base created in the Knowledge section was
    // invisible to the attach tab until a hard reload). On failure the
    // PRIOR cache is kept (never blanked) for other consumers, but
    // `_knowledgeBasesLoaded` is set false so the tab itself renders the
    // load-failure state rather than presenting that stale cache as
    // current (DD-15's second half, reconciled with DD-4 by this flag).
    function refreshKnowledgeBasesCache() {
      return fetchKnowledgeBases(true).then(function (kbs) {
        self._allKnowledgeBases = kbs;
        self._knowledgeBasesLoaded = true;
      }).catch(function () {
        self._allKnowledgeBases = self._allKnowledgeBases || [];
        self._knowledgeBasesLoaded = false;
      });
    }

    // Lazy schema fetcher — closure-cached. Stores the PROMISE (not the
    // resolved value) so concurrent callers during an in-flight fetch
    // reuse the same in-flight promise (no double-fetch). The cache
    // survives across agent changes; schemas are static.
    var _schemaPromiseCache = {};

    // The agent editor's MCP test (sortie 09, DD6, AC7): POST /test/agent with the agent's
    // name (null in create mode) and the unsaved credential entry (null = the stored
    // ones). Nothing is cached here: every call is a new request, and the caller keeps its
    // own per-tile generation number. Resolves with the route's body
    // ({status: ok | needs_values | auth_required | error, ...}); rejects with the
    // fetchJson error (a 422 carries `status` and `detail`).
    // `opts.credentialed` says the agent has stored credentials for this source: the
    // route then writes the agent's own list, not the shared one, so the Library list is
    // not stale.
    function testMcpAsAgent(sourceId, agentName, overrides, opts) {
      return App.api.fetchJson('/api/mcp-sources/' + encodeURIComponent(sourceId) + '/test/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent: agentName || null, overrides: overrides || null })
      }).then(function (data) {
        // An ok test for an agent with no credential override wrote the shared tool
        // list (config._cache): the Library list is stale (M25 F3 L2, DD9).
        if (data && data.status === 'ok' && !(opts && opts.credentialed)) {
          App.store.invalidate('mcp-sources');
        }
        return data;
      });
    }

    function fetchToolSchema(name) {
      if (_schemaPromiseCache[name]) return _schemaPromiseCache[name];
      var p = fetch('/api/tools/configs/' + encodeURIComponent(name)).then(function (r) {
        if (!r.ok) throw new Error('fetchToolSchema: HTTP ' + r.status);
        return r.json();
      }).catch(function (err) {
        // Drop the cached promise on error so next attempt retries.
        delete _schemaPromiseCache[name];
        throw err;
      });
      _schemaPromiseCache[name] = p;
      return p;
    }

    // `force` (activation / refresh) joins an in-flight store request else
    // refetches; post-mutation callers omit it -- the mutation already
    // invalidated the store, so a plain get refetches anyway.
    var loadAllDepth = 0;
    function loadAll(force) {
      loadAllDepth += 1;
      var done = function () { loadAllDepth -= 1; };
      var p = loadAllImpl(force);
      p.then(done, done);
      return p;
    }

    function loadAllImpl(force) {
      return Promise.all([
        fetchAgents(force), fetchTools(), fetchMcpSources(),
        fetchKnowledgeBases(force), fetchProviders(force)
      ])
        .then(function (results) {
          self._agents = results[0];
          self._allTools = results[1];
          self._allMcpSources = results[2];
          self._mcpSourcesLoaded = true;
          self._allKnowledgeBases = results[3];
          self._allProviders = results[4];
          self._agentsLoaded = true;
          // The list's rows need both agents and providers (the dot, the
          // provider name); a no-op off Agents.
          ctx.renderAgentList(true);
        });
    }

    // Squawk 0014 — loadAll() rejects (network blip, non-JSON error body)
    // with no rejection handler at either call site, so the Studio area
    // silently stays blank / stops refreshing. Shared renderer for both
    // call sites below. `nonDestructive: true` (the _refresh path) must
    // not clear already-rendered content, so it uses the existing
    // App.ui.flash overlay (admin.js:534 uses the same pattern for a
    // top-level list-fetch failure) instead of touching sectionContentEl.
    // The init path has nothing worth preserving yet, so it appends a
    // persistent `.admin-loading` line — the same class studio.js already
    // uses for section-level fetch failures (the knowledge detail view),
    // already styled for `.area-studio` in
    // studio.css. Built via createElement/textContent (not innerHTML) per
    // tests/test_ui_guards.py's dynamic-sink freeze.
    function showLoadAllError(err, opts) {
      var reason = (err && err.message) ? err.message : 'unknown error';
      var msg = 'Unable to load Studio data — ' + reason + '.';
      if (opts && opts.nonDestructive) {
        App.ui.flash(msg, { error: true });
        return;
      }
      var bannerEl = document.createElement('div');
      bannerEl.className = 'admin-loading studio-loadall-error';
      bannerEl.setAttribute('role', 'alert');
      bannerEl.textContent = msg;
      ctx.sectionContentEl.appendChild(bannerEl);
    }

    return {
      fetchAgents: fetchAgents,
      fetchTools: fetchTools,
      fetchMcpSources: fetchMcpSources,
      fetchRoutines: fetchRoutines,
      createRoutine: createRoutine,
      updateRoutine: updateRoutine,
      deleteRoutine: deleteRoutine,
      runRoutine: runRoutine,
      fetchRoutinesItem: fetchRoutinesItem,
      putRoutinesItem: putRoutinesItem,
      fetchRoutineProposals: fetchRoutineProposals,
      approveRoutineProposal: approveRoutineProposal,
      dismissRoutineProposal: dismissRoutineProposal,
      fetchRoutineRuns: fetchRoutineRuns,
      fetchRules: fetchRules,
      createRule: createRule,
      updateRule: updateRule,
      deleteRule: deleteRule,
      reorderRules: reorderRules,
      fetchNotes: fetchNotes,
      setNotesEnabled: setNotesEnabled,
      updateNote: updateNote,
      deleteNote: deleteNote,
      clearNotes: clearNotes,
      fetchSelfConfigurationStatus: fetchSelfConfigurationStatus,
      _refreshAgentAfterSelfConfigurationChange: _refreshAgentAfterSelfConfigurationChange,
      enableSelfConfiguration: enableSelfConfiguration,
      disableSelfConfiguration: disableSelfConfiguration,
      setSelfConfigurationApprovalMode: setSelfConfigurationApprovalMode,
      fetchSelfConfigurationRevisions: fetchSelfConfigurationRevisions,
      approveSelfConfigurationRevision: approveSelfConfigurationRevision,
      dismissSelfConfigurationRevision: dismissSelfConfigurationRevision,
      restoreSelfConfigurationRevision: restoreSelfConfigurationRevision,
      mintExternalCredential: mintExternalCredential,
      fetchExternalCredentials: fetchExternalCredentials,
      revokeExternalCredential: revokeExternalCredential,
      rotateExternalCredential: rotateExternalCredential,
      fetchKnowledgeBases: fetchKnowledgeBases,
      fetchProviders: fetchProviders,
      fetchToolConfigs: fetchToolConfigs,
      refreshToolConfigsCache: refreshToolConfigsCache,
      refreshMcpSourcesCache: refreshMcpSourcesCache,
      refreshKnowledgeBasesCache: refreshKnowledgeBasesCache,
      testMcpAsAgent: testMcpAsAgent,
      fetchToolSchema: fetchToolSchema,
      loadAll: loadAll,
      showLoadAllError: showLoadAllError,
      loadAllDepth: function () { return loadAllDepth; }
    };
  }
};
