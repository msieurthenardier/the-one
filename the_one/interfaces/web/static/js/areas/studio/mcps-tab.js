// App.studio.renderMcpsTab — agent-editor MCPs tab (rebuilt on the control library in
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
//     panel       — DOM element (the MCPs tabpanel)
//     agent       — AgentConfig object (null for create mode)
//     allSources  — array of MCPSource objects from /api/mcp-sources
//     callbacks   — { fetchMcpSourceTools, onChange, onSelectedSourceChange,
//                     pendingSourceId }
//                   `onChange` is the editor's dirty callback, called from the
//                   masters' own onChange and one delegated change handler on each
//                   group (the editor's field-level listener sweep does not see
//                   library inputs).
//   h = { setAgent(agent, opts), setSources(sources, agentName), destroy() }.
//   Mounted once per agent identity. setAgent patches in place: each master from
//   `mcp_source_ids` (a self-configuration source stays locked on), each group's
//   `data-mcp-tool-mode` from `mcp_overrides`, every loaded tool's checked state, and
//   the count chips; `opts.pendingSourceId` (a later deep link) expands that tile.
//   setSources reconciles tiles by source id (adds the agent's own new
//   self-configuration surface, removes a deleted one, swaps the empty state and the
//   list); every other tile is left alone (same node, expanded state, unsaved choices).
//
// Save-flow selectors (collected by agent-form-data.js, unchanged):
//   [data-mcp-source-toggle][data-mcp-source-id]   on the master's input → mcp_source_ids
//   [data-mcp-tool-toggle][data-mcp-source]        on each row's input → enabled/disabled tools
//   closest('[data-mcp-tool-group]')[data-mcp-tool-mode]
//
// Per-agent credential overrides (bearer_token, headers, env) are NOT rendered here
// (flight log Anomaly A5); the backend still accepts them via API.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderMcpsTab(panel, agent, allSources, callbacks) {
    callbacks = callbacks || {};
    var ui = window.App.ui;
    var fetchMcpSourceTools = callbacks.fetchMcpSourceTools;
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

    function isSelfConfiguration(source) {
      var marker = source.config && source.config.self_configuration;
      return !!(marker && typeof marker === 'object');
    }

    // M21 F01 L02 (DD3): the editor's fetch includes every agent's
    // self-configuration surface row, but this tab shows an agent ONLY its own,
    // never another agent's. Create mode (no name) shows none.
    function visibleSources() {
      var out = [];
      for (var i = 0; i < sources.length; i++) {
        var marker = sources[i].config && sources[i].config.self_configuration;
        if (marker && typeof marker === 'object') {
          if (!agentName || marker.agent !== agentName) continue;
        }
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

    function cachedTools(source) {
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
      var locked = isSelfConfiguration(source);
      var entry = {
        source: source,
        locked: locked,
        tile: null,
        group: null,
        noteHost: null,
        rows: {},
        order: [],
        loadStarted: false,
        gen: 0
      };

      // Refresh keeps its visible label at the small size; its name says which source.
      var refreshBtn = ui.button({
        size: 'sm',
        icon: 'refresh-cw',
        label: 'Refresh',
        ariaLabel: 'Refresh tools for ' + source.name,
        testid: 'mcp-refresh-tools-btn-' + source.id,
        onClick: function () {
          // Opens the panel if closed, then force-reloads the tools. The explicit
          // selected-source callback replaces onExpand, which setExpanded never fires.
          if (!entry.tile.isExpanded()) {
            entry.loadStarted = true;
            entry.tile.setExpanded(true);
            setSelected(source.id);
          }
          loadTools(entry, true);
        }
      });

      var actions = [];
      if (locked) {
        // The surface's OWN attach switch is locked checked and disabled: it is
        // managed from the Self-configuration tab. A disabled checked input still
        // matches `:checked`, so collectFormData keeps the id in `mcp_source_ids`.
        var hint = document.createElement('span');
        hint.className = 'mcp-source-tile-self-configuration-hint';
        hint.setAttribute('data-testid', 'mcp-source-self-configuration-hint-' + source.id);
        hint.textContent = 'managed on the Self-configuration tab';
        actions.push(hint);
      }
      actions.push(refreshBtn);

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
        actions: actions,
        subtitle: subtitle,
        master: {
          label: 'Attach ' + source.name,
          tristate: false,
          state: 'off',
          disabled: locked,
          testid: 'mcp-source-toggle-' + source.id,
          dataset: { mcpSourceToggle: '', mcpSourceId: source.id },
          onChange: function () { onChange(); }
        },
        toolLabel: 'Tools',
        testid: 'mcp-source-row-' + source.id,
        dataset: { sourceId: source.id },
        expandTestid: 'mcp-source-expand-' + source.id,
        bodyTestid: 'mcp-source-details-body-' + source.id,
        onFirstExpand: function () {
          if (entry.loadStarted) return;
          entry.loadStarted = true;
          loadTools(entry, false);
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
      tile.body.appendChild(entry.noteHost);
      tile.body.appendChild(entry.group);

      patchEntry(entry);
      return entry;
    }

    function destroyEntry(entry) {
      entry.gen += 1;
      entry.group.removeEventListener('change', entry.onGroupChange);
      Object.keys(entry.rows).forEach(function (name) { entry.rows[name].destroy(); });
      entry.tile.destroy();
    }

    // Masters, tool mode, checked states and the count, from currentAgent.
    function patchEntry(entry) {
      var attached = attachedIds();
      entry.tile.setMaster(entry.locked || attached[entry.source.id] === true ? 'on' : 'off');
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
        var cached = cachedTools(entry.source);
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

    function loadTools(entry, forceRefresh) {
      var source = entry.source;
      var cached = cachedTools(source);
      if (!forceRefresh && cached) {
        applyTools(entry, cached);
        return;
      }
      if (!fetchMcpSourceTools) {
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
      var gen = ++entry.gen;
      fetchMcpSourceTools(source.id, { forceRefresh: !!forceRefresh }).then(function (data) {
        if (destroyed || gen !== entry.gen) return;
        applyTools(entry, (data && data.tools) || []);
      }).catch(function (err) {
        if (destroyed || gen !== entry.gen) return;
        if (err && err.name === 'AuthRequired') {
          setNote(entry, authNotice(source));
        } else {
          // The existing rows stay; the error shows above them, replacing any previous one.
          var errEl = window.App.buildMcpError(err && err.message ? err.message : String(err));
          errEl.setAttribute('data-testid', 'mcp-tools-error-' + source.id);
          setNote(entry, errEl);
        }
      });
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
        Object.keys(entries).forEach(function (id) { patchEntry(entries[id]); });
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
