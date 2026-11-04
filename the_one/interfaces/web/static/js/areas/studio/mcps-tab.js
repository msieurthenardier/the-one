// App.studio.renderMcpsTab — agent-editor Tools tab, MCP servers section (rebuilt on the control library in
// M31 F2 L07b; flight DD3, DD4, DD6, DD7, DD9-1).
//
// One App.ui.groupTile per MCP source. The tile's master is the ATTACH switch (a
// non-tristate role=switch, never mixed: tool selection does not change it). The
// body is loaded lazily on the first expand and holds a note host (loading, the
// auth-required notice, a connection error, or the empty state) above a group of
// App.ui.toolRow rows (`div[data-mcp-tool-group][data-mcp-tool-mode]`).
//
// Public API:
//   var h = App.studio.renderMcpsTab(panel, agent, allSources, callbacks)
//     panel       — DOM element (the Tools tabpanel)
//     agent       — AgentConfig object (null for create mode)
//     allSources  — array of MCPSource objects from /api/mcp-sources
//     callbacks   — { testMcpAsAgent, onChange, onSelectedSourceChange,
//                     pendingSourceId }
//                   `onChange` is the editor's dirty callback, called from the
//                   masters' own onChange and one delegated change handler on each
//                   group (the editor's field-level listener sweep does not see
//                   library inputs).
//   h = { setAgent(agent, opts), setSources(sources, agentName), destroy() }.
//   Mounted once per agent identity. setAgent patches in place: each master from
//   `mcp_source_ids`, each group's `data-mcp-tool-mode` from `mcp_overrides`, every
//   loaded tool's checked state, and the count chips; `opts.pendingSourceId` (a later
//   deep link) expands that tile. setSources reconciles tiles by source id (adds a new
//   source, removes a deleted one, swaps the empty state and the list); every other
//   tile is left alone (same node, expanded state, unsaved choices).
//   A self-configuration surface row (any agent's, the agent's own included) is never
//   shown here: the Self-configuration tab is its only control, and the server keeps
//   it attached across a Save (sortie 08).
//
// Save-flow selectors (collected by agent-form-data.js, unchanged):
//   [data-mcp-source-toggle][data-mcp-source-id]   on the master's input → mcp_source_ids
//   [data-mcp-tool-toggle][data-mcp-source]        on each row's input → enabled/disabled tools
//   closest('[data-mcp-tool-group]')[data-mcp-tool-mode]
//
// Per-agent credentials (sortie 09 leg 6, DD12): every tile body opens with the section
// built by App.studio.mcpAgentCredentials (the Library's headers table, locked until
// "Override headers", then the status line with Test), then the tool rows. The tile's own
// Save writes through callbacks.saveMcpCredentials (the targeted route) at once and rebases
// only that tile; the editor's main Save no longer carries credentials. The tab tests through
// callbacks.testMcpAsAgent (POST /test/agent): on a user switch-on, on the first expand
// when no applicable list exists, on Test (unsaved values while unlocked) and after a tile
// Save (saved values). Each test carries a per-tile generation; a stale result is dropped.
// A credentialed agent's tile lists only its own per-agent cache (agent.mcp_tool_cache) or a
// test result from this mount, never the shared source cache.
//   h also exposes anyDirty() (a tile is unlocked with unsaved edits: the leave guard).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderMcpsTab(panel, agent, allSources, callbacks) {
    callbacks = callbacks || {};
    var ui = window.App.ui;
    var testMcpAsAgent = callbacks.testMcpAsAgent;
    var credMod = window.App.studio.mcpAgentCredentials;
    var onChange = callbacks.onChange || function () {};
    var onSelectedSourceChange = callbacks.onSelectedSourceChange || function () {};
    var currentAgent = agent || null;
    var agentName = agent ? agent.name : null;
    var sources = allSources || [];
    var entries = {};        // source id -> entry
    var listEl = null;
    var emptyEl = null;
    var selectedId = null;   // the source this tab last reported as the focused one
    var destroyed = false;

    panel.textContent = '';

    // ── Helpers ─────────────────────────────────────────────────────────────

    function slugify(name) {
      // LD7 (M21 F01 L03): keep hyphens/underscores so the tooltip-only prefixed
      // name agrees with `mcp/_tool.py:_normalize_source_name`.
      return name.toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_|_$/g, '');
    }

    // The editor's fetch includes every agent's self-configuration surface row
    // (`?include_agent_surfaces=1`), but this tab shows none of them, the agent's
    // own included (sortie 08 DD1).
    function visibleSources() {
      var out = [];
      for (var i = 0; i < sources.length; i++) {
        var marker = sources[i].config && sources[i].config.self_configuration;
        if (marker && typeof marker === 'object') continue;
        out.push(sources[i]);
      }
      return out;
    }

    function attachedIds() {
      var ids = {};
      var list = (currentAgent && currentAgent.mcp_source_ids) || [];
      for (var i = 0; i < list.length; i++) ids[list[i]] = true;
      return ids;
    }

    function overridesFor(source) {
      return ((currentAgent && currentAgent.mcp_overrides) || {})[source.name] || {};
    }

    function modeFor(source) {
      return Array.isArray(overridesFor(source).enabled_tools) ? 'allowlist' : 'denylist';
    }

    // Is a tool checked by the stored overrides, in the given mode?
    function storedChecked(source, mode, toolName) {
      var o = overridesFor(source);
      if (mode === 'allowlist') {
        return Array.isArray(o.enabled_tools) && o.enabled_tools.indexOf(toolName) !== -1;
      }
      return (o.disabled_tools || []).indexOf(toolName) === -1;
    }

    // Which list a tile shows (sortie 09 DD4, AC6): a credentialed agent sees its own
    // list only (a test result from this mount, else its stored per-agent cache), never
    // the shared one; any other agent sees the shared source cache.
    function credentialed(source) {
      return credMod.hasStoredCredential(source, currentAgent);
    }

    function listedTools(entry) {
      var source = entry.source;
      if (credentialed(source)) {
        var own = (currentAgent && currentAgent.mcp_tool_cache) || {};
        var cache = own[source.id];
        return entry.testedTools || (cache && Array.isArray(cache.tools) ? cache.tools : null);
      }
      return source.config && source.config._cache && Array.isArray(source.config._cache.tools)
        ? source.config._cache.tools : null;
    }

    function setSelected(id) {
      selectedId = id;
      onSelectedSourceChange(id);
    }

    // ── Empty state ─────────────────────────────────────────────────────────

    function buildEmptyState() {
      var addLink = document.createElement('a');
      addLink.href = App.router.href({ destination: 'library' });
      addLink.textContent = 'Add one in the Library.';
      return ui.emptyState({
        title: 'No MCP sources registered yet.',
        titleTag: 'p',
        action: addLink,
        testid: 'mcp-empty-state'
      });
    }

    // ── One source tile ─────────────────────────────────────────────────────

    function buildEntry(source) {
      var entry = {
        source: source,
        tile: null,
        group: null,
        noteHost: null,
        rows: {},
        order: [],
        loadStarted: false,
        gen: 0,
        cred: null,
        testedTools: null,   // the tools of the last ok test in this mount
        settled: null,       // the last settled status line {kind, data}
        testing: false
      };

      // The credential section and the status line with its buttons. Its edits never reach
      // the editor's main dirty state: the tile saves itself.
      entry.cred = credMod.create({
        source: source,
        agent: currentAgent,
        onChange: function () { onCredChange(entry); },
        onTest: function () {
          entry.loadStarted = true;
          runTest(entry, {});
        },
        saveCredentials: callbacks.saveMcpCredentials,
        onSaved: function (updated) { onCredSaved(entry, updated); }
      });

      // Server-declared identity (F4 L2, M08), shown once /test/connect has cached it.
      var subtitle = null;
      var info = source.config && source.config._cache && source.config._cache.server_info;
      if (info) {
        var text = (info.title || info.name || '') + (info.version ? ' · v' + info.version : '');
        if (text.trim()) {
          subtitle = document.createElement('span');
          subtitle.setAttribute('data-testid', 'mcp-source-subtitle-' + source.id);
          subtitle.textContent = text;
          var instructions = source.config._cache.instructions;
          if (instructions) {
            subtitle.className = 'has-instructions';
            subtitle.title = instructions;
          }
        }
      }

      var tile = ui.groupTile({
        name: source.name,
        chips: [source.type === 'stdio' ? 'stdio' : 'http'],
        subtitle: subtitle,
        master: {
          label: 'Attach ' + source.name,
          tristate: false,
          state: 'off',
          testid: 'mcp-source-toggle-' + source.id,
          dataset: { mcpSourceToggle: '', mcpSourceId: source.id },
          onChange: function (nextChecked) {
            onChange();
            // A user toggle only (setMaster is silent): switch-on expands and tests at
            // once with the tile's current values; focus stays on the switch. Switch-off
            // drops a result still in flight.
            if (nextChecked) switchOn(entry);
            else switchOff(entry);
          }
        },
        toolLabel: 'Tools',
        // A20: "Tools for Docs search", "3 tools for Docs search" (label in name).
        expandLabel: function (text) { return text + ' for ' + source.name; },
        testid: 'mcp-source-row-' + source.id,
        dataset: { sourceId: source.id },
        expandTestid: 'mcp-source-expand-' + source.id,
        bodyTestid: 'mcp-source-details-body-' + source.id,
        onFirstExpand: function () {
          if (entry.loadStarted) return;
          entry.loadStarted = true;
          // With an applicable list, show it; otherwise test once (never on a later expand).
          var listed = listedTools(entry);
          if (listed) applyTools(entry, listed);
          else runTest(entry, {});
        },
        onExpand: function (expanded) {
          if (expanded) {
            setSelected(source.id);
          } else if (selectedId === source.id) {
            // DD9-1: collapsing the focused source drops it from the route.
            setSelected(null);
          }
        }
      });
      entry.tile = tile;

      entry.noteHost = document.createElement('div');
      entry.noteHost.hidden = true;
      entry.group = document.createElement('div');
      entry.group.className = 'mcp-tool-group';
      entry.group.setAttribute('data-mcp-tool-group', '');
      entry.group.setAttribute('data-mcp-tool-mode', modeFor(source));
      entry.group.setAttribute('data-testid', 'mcp-tools-checkbox-group-' + source.id);
      // ONE delegated handler (replaces the per-load listeners): the count and the
      // editor's dirty state follow every row change.
      entry.onGroupChange = function () {
        recount(entry);
        onChange();
      };
      entry.group.addEventListener('change', entry.onGroupChange);
      tile.body.appendChild(entry.cred.el);
      tile.body.appendChild(entry.noteHost);
      tile.body.appendChild(entry.group);

      patchEntry(entry);
      showBaseline(entry);
      return entry;
    }

    function destroyEntry(entry) {
      entry.gen += 1;
      entry.cred.destroy();
      entry.group.removeEventListener('change', entry.onGroupChange);
      Object.keys(entry.rows).forEach(function (name) { entry.rows[name].destroy(); });
      entry.tile.destroy();
    }

    // Masters, tool mode, checked states and the count, from currentAgent.
    function patchEntry(entry) {
      var attached = attachedIds();
      entry.tile.setMaster(attached[entry.source.id] === true ? 'on' : 'off');
      var mode = modeFor(entry.source);
      entry.group.setAttribute('data-mcp-tool-mode', mode);
      Object.keys(entry.rows).forEach(function (name) {
        entry.rows[name].setChecked(storedChecked(entry.source, mode, name));
      });
      recount(entry);
    }

    // ── Count ───────────────────────────────────────────────────────────────

    function setCount(entry, enabled, total) {
      entry.tile.setToolCount(total === null ? 'Tools' : total);
      if (total === null || enabled === null) {
        entry.tile.setCount('');
      } else {
        entry.tile.setCount(enabled + ' / ' + total + ' enabled');
      }
    }

    function recount(entry) {
      var names = Object.keys(entry.rows);
      if (names.length === 0) {
        // Rows not built yet: compute from the cache and the stored overrides.
        var cached = listedTools(entry);
        if (!cached) {
          setCount(entry, null, null);
          return;
        }
        var mode = modeFor(entry.source);
        var n = 0;
        for (var i = 0; i < cached.length; i++) {
          if (storedChecked(entry.source, mode, cached[i].name)) n++;
        }
        setCount(entry, n, cached.length);
        return;
      }
      var enabled = 0;
      for (var j = 0; j < names.length; j++) {
        if (entry.rows[names[j]].input.checked) enabled++;
      }
      setCount(entry, enabled, names.length);
    }

    // ── Notes (loading, auth, error, empty) ─────────────────────────────────

    function setNote(entry, node) {
      entry.noteHost.textContent = '';
      if (node) entry.noteHost.appendChild(node);
      entry.noteHost.hidden = !node;
    }

    function authNotice(source) {
      var name = source.name || source.id;
      var status = ui.status({ testid: 'mcp-auth-required-notice-' + source.id });
      status.set('warning', '“' + name + '” needs Test/auth on the source-edit page first.');
      var link = document.createElement('a');
      link.href = App.router.href({ destination: 'library', section: 'mcp', id: source.id });
      link.textContent = 'Go to source settings';
      link.setAttribute('data-testid', 'mcp-auth-required-link-' + source.id);
      status.el.appendChild(document.createTextNode(' '));
      status.el.appendChild(link);
      return status.el;
    }

    // ── Tools: rows keyed by tool name ──────────────────────────────────────

    function buildRow(entry, tool) {
      var source = entry.source;
      var mode = entry.group.getAttribute('data-mcp-tool-mode');
      return ui.toolRow({
        name: tool.name,
        description: tool.description,
        checked: storedChecked(source, mode, tool.name),
        title: 'mcp__' + slugify(source.name) + '__' + tool.name,
        testid: 'mcp-tool-toggle-' + source.id + '-' + tool.name,
        inputDataset: { mcpToolToggle: tool.name, mcpSource: source.name }
      });
    }

    // Success: a tool still present keeps the operator's unsaved state, a new one
    // takes the stored default for the group's CURRENT mode (a Refresh never
    // recomputes the mode; only setAgent does), a removed one's row goes.
    function applyTools(entry, tools) {
      var keep = {};
      var order = [];
      var i;
      for (i = 0; i < tools.length; i++) {
        var tool = tools[i];
        if (!entry.rows[tool.name]) entry.rows[tool.name] = buildRow(entry, tool);
        keep[tool.name] = true;
        order.push(tool.name);
      }
      Object.keys(entry.rows).forEach(function (name) {
        if (keep[name]) return;
        var row = entry.rows[name];
        if (row.el.parentNode) row.el.parentNode.removeChild(row.el);
        row.destroy();
        delete entry.rows[name];
      });
      for (i = 0; i < order.length; i++) {
        var el = entry.rows[order[i]].el;
        if (entry.group.children[i] !== el) entry.group.insertBefore(el, entry.group.children[i] || null);
      }
      if (tools.length === 0) {
        var none = ui.emptyState({
          title: 'No tools available for this source.',
          titleTag: 'p',
          testid: 'mcp-no-tools-msg-' + entry.source.id
        });
        setNote(entry, none);
      } else {
        setNote(entry, null);
      }
      recount(entry);
    }

    // ── Status line and tests (DD6, DD10) ───────────────────────────────────

    function setSettled(entry, kind, data) {
      entry.settled = { kind: kind, data: data || {} };
      entry.cred.setStatus(kind, data);
    }

    // The status line of a tile no test is running on: a missing value, the listed
    // tools (own or shared), "Not listed with this agent's values yet", or blank.
    function showBaseline(entry) {
      var missing = entry.cred.missing();
      var listed = listedTools(entry);
      if (missing.length) setSettled(entry, 'needs', { names: missing });
      else if (listed) setSettled(entry, 'listed', { count: listed.length, perAgent: credentialed(entry.source) });
      else if (credentialed(entry.source)) setSettled(entry, 'none');
      else setSettled(entry, 'idle');
    }

    // A credential edit: a "Needs a value" line follows the names still missing (the
    // editor's dirty state is not involved: the tile saves itself).
    function onCredChange(entry) {
      if (!entry.settled || entry.settled.kind !== 'needs' || entry.testing) return;
      var missing = entry.cred.missing();
      if (missing.join('\n') === (entry.settled.data.names || []).join('\n')) return;
      if (missing.length) setSettled(entry, 'needs', { names: missing });
      else setSettled(entry, 'idle');
    }

    // A tile Save landed: the tab follows the saved agent (never a tab-level setAgent: that
    // would reset the attach switch and the tool rows) and tests once with the saved values.
    function onCredSaved(entry, updated) {
      currentAgent = updated || currentAgent;
      if (updated && updated.name) agentName = updated.name;
      entry.testedTools = null;
      entry.loadStarted = true;
      runTest(entry, { saved: true });
    }

    function switchOn(entry) {
      entry.loadStarted = true;
      if (!entry.tile.isExpanded()) {
        entry.tile.setExpanded(true);
        setSelected(entry.source.id);
      }
      runTest(entry, {});
    }

    function switchOff(entry) {
      entry.gen += 1;
      entry.testing = false;
      if (entry.settled) entry.cred.setStatus(entry.settled.kind, entry.settled.data);
      else showBaseline(entry);
    }

    // Runs the per-agent test (POST /test/agent). `opts.saved` tests the stored values
    // (overrides: null), after a Save; otherwise the tile's unsaved values go along. A
    // missing value is reported before any request.
    function runTest(entry, opts) {
      var source = entry.source;
      var cred = entry.cred;
      var gen = ++entry.gen;
      var missing = cred.missing();
      if (missing.length) {
        entry.testing = false;
        setNote(entry, null);
        setSettled(entry, 'needs', { names: missing });
        return;
      }
      if (!testMcpAsAgent) {
        var unavailable = document.createElement('p');
        unavailable.className = 'loading';
        unavailable.textContent = 'Tool discovery not available.';
        setNote(entry, unavailable);
        return;
      }
      if (Object.keys(entry.rows).length === 0) {
        var loading = document.createElement('p');
        loading.className = 'loading';
        loading.textContent = 'Loading tools…';
        setNote(entry, loading);
      }
      var overrides = opts && opts.saved ? null : cred.payload();
      var withValues = credentialed(source) || overrides !== null;
      entry.testing = true;
      cred.setStatus('testing');
      testMcpAsAgent(source.id, agentName, overrides, { credentialed: withValues }).then(function (data) {
        if (destroyed || gen !== entry.gen) return;
        entry.testing = false;
        var status = data && data.status;
        if (status === 'ok') {
          var tools = data.tools || [];
          entry.testedTools = tools;
          applyTools(entry, tools);
          setSettled(entry, 'ok', { count: tools.length, withValues: withValues });
        } else if (status === 'needs_values') {
          setNote(entry, null);
          setSettled(entry, 'needs', { names: data.missing || [] });
        } else if (status === 'auth_required') {
          setNote(entry, authNotice(source));
          setSettled(entry, 'auth');
        } else {
          showTestError(entry, data && data.error ? data.error : 'unknown error', withValues);
        }
      }).catch(function (err) {
        if (destroyed || gen !== entry.gen) return;
        entry.testing = false;
        if (err && err.status === 422 && Array.isArray(err.detail)) {
          if (cred.showErrors(err.detail)) {
            setNote(entry, null);
            setSettled(entry, 'error', { withValues: true });
            return;
          }
        }
        showTestError(entry, err && err.message ? err.message : String(err), withValues);
      });
    }

    // The existing rows stay; the error shows above them, replacing any previous one.
    function showTestError(entry, raw, withValues) {
      var errEl = window.App.buildMcpError(raw, {
        transport: entry.source.type === 'stdio' ? 'stdio' : 'http'
      });
      errEl.setAttribute('data-testid', 'mcp-tools-error-' + entry.source.id);
      setNote(entry, errEl);
      setSettled(entry, 'error', { withValues: withValues });
    }

    // ── Reconcile the tiles with the visible sources ────────────────────────

    function focusSource(id) {
      var entry = entries[id];
      if (!entry) return;
      // The focus follows the URL: the previously focused tile collapses (silently,
      // setExpanded fires no onExpand) as the new one opens.
      var prev = selectedId && selectedId !== id ? entries[selectedId] : null;
      if (prev && prev.tile.isExpanded()) prev.tile.setExpanded(false);
      if (!entry.tile.isExpanded()) entry.tile.setExpanded(true);
      if (selectedId !== id) setSelected(id);
      // The MCP section sits below the built-in categories, so bring the tile
      // into view (a no-op while the Tools panel is hidden).
      try {
        if (entry.tile.el.scrollIntoView) entry.tile.el.scrollIntoView({ block: 'nearest' });
      } catch (e) { /* best effort */ }
    }

    // The parts of a source the credential section reads; a tile follows a change in
    // them (pending edits kept), every other tile state is left alone.
    function credSignature(s) {
      var kind = s.type === 'stdio' ? 'env' : 'headers';
      return JSON.stringify([s.type, (s.config || {})[kind] || null, s.secrets || null, s.oauth_active === true]);
    }

    function refreshSource(entry, next) {
      var changed = credSignature(entry.source) !== credSignature(next);
      entry.source = next;
      if (!changed) return;
      entry.cred.setSource(next);
      if (!entry.testing) showBaseline(entry);
    }

    function reconcile() {
      var visible = visibleSources();
      var want = {};
      var i;
      for (i = 0; i < visible.length; i++) want[visible[i].id] = true;
      Object.keys(entries).forEach(function (id) {
        if (want[id]) return;
        var gone = entries[id];
        destroyEntry(gone);
        if (gone.tile.el.parentNode) gone.tile.el.parentNode.removeChild(gone.tile.el);
        delete entries[id];
        if (selectedId === id) selectedId = null;
      });

      if (visible.length === 0) {
        if (listEl && listEl.parentNode) listEl.parentNode.removeChild(listEl);
        listEl = null;
        if (!emptyEl) {
          emptyEl = buildEmptyState();
          panel.appendChild(emptyEl);
        }
        return;
      }
      if (emptyEl) {
        if (emptyEl.parentNode) emptyEl.parentNode.removeChild(emptyEl);
        emptyEl = null;
      }
      if (!listEl) {
        listEl = document.createElement('div');
        listEl.className = 'mcp-sources-list';
        listEl.setAttribute('data-testid', 'mcp-sources-list');
        panel.appendChild(listEl);
      }
      for (i = 0; i < visible.length; i++) {
        var id = visible[i].id;
        if (!entries[id]) entries[id] = buildEntry(visible[i]);
        else refreshSource(entries[id], visible[i]);
        var el = entries[id].tile.el;
        if (listEl.children[i] !== el) listEl.insertBefore(el, listEl.children[i] || null);
      }
    }

    reconcile();
    if (callbacks.pendingSourceId) focusSource(callbacks.pendingSourceId);

    return {
      setAgent: function (a, opts) {
        currentAgent = a || null;
        if (a && a.name) agentName = a.name;
        // A rebase of the switches and tool rows (select, Save, Cancel). A tile with unsaved
        // credential edits is left alone (credentials are not part of that Save or Cancel);
        // a clean tile locks and follows the agent.
        Object.keys(entries).forEach(function (id) {
          var e = entries[id];
          if (e.cred.isDirty()) {
            e.cred.adoptAgent(currentAgent);
            patchEntry(e);
            return;
          }
          e.cred.setAgent(currentAgent);
          e.testedTools = null;
          patchEntry(e);
          if (!e.testing) showBaseline(e);
        });
        // A later deep-link change expands that tile (setExpanded fires no onExpand,
        // so the selected-source callback is explicit). An already-loaded body is
        // not refetched. A null value never collapses anything.
        if (opts && opts.pendingSourceId && opts.pendingSourceId !== selectedId) {
          focusSource(opts.pendingSourceId);
        }
      },
      setSources: function (nextSources, name) {
        sources = nextSources || [];
        if (name !== undefined && name !== null) agentName = name;
        reconcile();
      },
      // True while any tile is unlocked with unsaved credential edits (the leave guard).
      anyDirty: function () {
        return Object.keys(entries).some(function (id) { return entries[id].cred.isDirty(); });
      },
      destroy: function () {
        destroyed = true;
        Object.keys(entries).forEach(function (id) { destroyEntry(entries[id]); });
        entries = {};
        listEl = null;
        emptyEl = null;
        panel.textContent = '';
      }
    };
  }

  window.App.studio.renderMcpsTab = renderMcpsTab;
})();
