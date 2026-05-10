// App.studio.renderMcpsTab — agent-editor MCPs tab.
//
// Mirrors the built-in Tools tab pattern (`tool-row` + sibling
// `tool-row-overrides <details>`): each MCP source is rendered as a
// single row with an attach toggle on the summary line, and a
// collapsible details panel below containing the per-tool checkbox
// group + credential override fields.
//
// Public API:
//   App.studio.renderMcpsTab(panel, agent, allSources, callbacks)
//     panel       — DOM element (the MCPs tabpanel)
//     agent       — AgentConfig object (may be null for create-mode)
//     allSources  — array of MCPSource objects from /api/mcp-sources
//     callbacks   — { fetchMcpSourceTools, onChange, onSelectedSourceChange,
//                     pendingSourceId }
//
// Save-flow selectors (collected by studio.js::collectFormData):
//   [data-mcp-source-toggle][data-mcp-source-id]:checked  → mcp_source_ids
//   [data-mcp-tool-toggle][data-mcp-source]               → enabled_tools/disabled_tools
//
// Per-agent credential overrides (bearer_token, headers, env) are NOT
// rendered in this UI — see flight log Anomaly A5 for the rationale.
// The backend's `mcp_overrides[source_name]` schema still accepts
// credential fields via API for non-OAuth use cases; a future flight
// will land a per-agent OAuth re-auth toggle for SSO sources, replacing
// the manual-paste UX that didn't fit operators.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // ── Main entry point ──────────────────────────────────────────────────────

  function renderMcpsTab(panel, agent, allSources, callbacks) {
    panel.innerHTML = '';
    callbacks = callbacks || {};
    var fetchMcpSourceTools = callbacks.fetchMcpSourceTools;
    var onChange = callbacks.onChange || function () {};
    var onSelectedSourceChange = callbacks.onSelectedSourceChange || function () {};
    var pendingSourceId = callbacks.pendingSourceId || _parseSourceIdFromHash();

    // Remove stale hashchange listener if any.
    if (panel._mcpsTabHashHandler) {
      window.removeEventListener('hashchange', panel._mcpsTabHashHandler);
      panel._mcpsTabHashHandler = null;
    }

    if (!allSources || allSources.length === 0) {
      _renderEmptyState(panel);
      return;
    }

    _renderSourcesList(panel, agent, allSources, fetchMcpSourceTools,
      onChange, onSelectedSourceChange, pendingSourceId);

    // Hash-change listener: re-renders when operator deep-links/back-navigates.
    function onHashChange() {
      renderMcpsTab(panel, agent, allSources, {
        fetchMcpSourceTools: fetchMcpSourceTools,
        onChange: onChange,
        onSelectedSourceChange: onSelectedSourceChange
        // pendingSourceId omitted — re-parsed from hash on next render.
      });
    }
    window.addEventListener('hashchange', onHashChange);
    panel._mcpsTabHashHandler = onHashChange;
  }

  // ── Empty state ───────────────────────────────────────────────────────────

  function _renderEmptyState(panel) {
    var div = document.createElement('div');
    div.className = 'mcp-empty-state';
    div.setAttribute('data-testid', 'mcp-empty-state');
    div.innerHTML = 'No MCP sources registered yet. ' +
      '<a href="#studio/mcp-sources">Add one in MCP Sources.</a>';
    panel.appendChild(div);
  }

  // ── Sources list (single render branch) ───────────────────────────────────
  //
  // Each source = `<div class="tool-row mcp-source-row">` containing:
  //   - <label> with attach toggle + name + transport badge
  //   - sibling <details class="tool-row-overrides"> with the per-source
  //     details panel (per-tool checkboxes + credential overrides)
  //
  // Mirrors built-in tools tab look-and-feel exactly.

  function _renderSourcesList(panel, agent, allSources, fetchMcpSourceTools,
      onChange, onSelectedSourceChange, pendingSourceId) {
    var attachedIds = _attachedSourceIds(agent);
    var listContainer = document.createElement('div');
    listContainer.className = 'mcp-sources-list';
    listContainer.setAttribute('data-testid', 'mcp-sources-list');

    for (var i = 0; i < allSources.length; i++) {
      (function (source) {
        var isAttached = attachedIds[source.id] === true;
        var rowWrapper = document.createElement('div');
        rowWrapper.className = 'mcp-source-row-wrapper';
        rowWrapper.setAttribute('data-testid', 'mcp-source-row-' + source.id);

        // Row summary with attach toggle.
        var rowLabel = document.createElement('label');
        rowLabel.className = 'tool-row mcp-source-row';

        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'tool-toggle mcp-source-toggle';
        checkbox.setAttribute('data-mcp-source-toggle', '');
        checkbox.setAttribute('data-mcp-source-id', source.id);
        checkbox.setAttribute('data-testid', 'mcp-source-toggle-' + source.id);
        checkbox.checked = isAttached;
        rowLabel.appendChild(checkbox);

        var visualSwitch = document.createElement('span');
        visualSwitch.className = 'tool-switch';
        rowLabel.appendChild(visualSwitch);

        var nameSpan = document.createElement('span');
        nameSpan.className = 'tool-name';
        nameSpan.textContent = source.name;
        rowLabel.appendChild(nameSpan);

        var descSpan = document.createElement('span');
        descSpan.className = 'tool-desc';
        descSpan.textContent = source.type === 'stdio' ? 'stdio' : 'streamable-http';
        rowLabel.appendChild(descSpan);

        rowWrapper.appendChild(rowLabel);

        // Details panel — collapsible. Lazy-loads per-tool list + override
        // fields on first open. Auto-opens when pendingSourceId matches.
        var details = document.createElement('details');
        details.className = 'tool-row-overrides mcp-source-details';
        details.setAttribute('data-source-id', source.id);
        details.setAttribute('data-testid', 'mcp-source-details-' + source.id);
        if (pendingSourceId === source.id) {
          details.setAttribute('open', '');
        }

        var summary = document.createElement('summary');
        summary.textContent = 'Details';
        details.appendChild(summary);

        var body = document.createElement('div');
        body.className = 'tool-row-overrides-body';
        body.setAttribute('data-testid', 'mcp-source-details-body-' + source.id);
        var loadingP = document.createElement('p');
        loadingP.className = 'loading';
        loadingP.textContent = 'Open to load details…';
        body.appendChild(loadingP);
        details.appendChild(body);

        rowWrapper.appendChild(details);

        // Wire toggle change → onChange (dirty tracking + URL routing).
        checkbox.addEventListener('change', function () {
          if (onChange) onChange();
        });

        // Wire details-open → lazy-load body + URL deep-link sync.
        details.addEventListener('toggle', function () {
          if (details.open) {
            // URL sync — open panel reflects in the deep-link.
            if (onSelectedSourceChange) onSelectedSourceChange(source.id);
            if (details.dataset.loaded !== 'true') {
              details.dataset.loaded = 'true';
              _populateDetailsBody(body, source, agent, fetchMcpSourceTools, onChange);
            }
          } else {
            // Closed — clear deep-link if we own it.
            if (onSelectedSourceChange) {
              var currentSourceId = _parseSourceIdFromHash();
              if (currentSourceId === source.id) onSelectedSourceChange(null);
            }
          }
        });

        // Auto-load if pendingSourceId opens us by default.
        if (pendingSourceId === source.id) {
          details.dataset.loaded = 'true';
          _populateDetailsBody(body, source, agent, fetchMcpSourceTools, onChange);
          if (onSelectedSourceChange) onSelectedSourceChange(source.id);
        }

        listContainer.appendChild(rowWrapper);
      })(allSources[i]);
    }

    panel.appendChild(listContainer);
  }

  // ── Details body ──────────────────────────────────────────────────────────

  function _populateDetailsBody(body, source, agent, fetchMcpSourceTools, onChange) {
    body.innerHTML = '';

    // Tools section.
    var toolsSection = document.createElement('div');
    toolsSection.className = 'mcp-editor-section';
    var toolsLabel = document.createElement('h4');
    toolsLabel.textContent = 'Tools';
    toolsSection.appendChild(toolsLabel);

    var refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'btn-outlined-cyan mcp-refresh-tools-btn';
    refreshBtn.setAttribute('data-testid', 'mcp-refresh-tools-btn-' + source.id);
    refreshBtn.textContent = 'Refresh tools';
    toolsSection.appendChild(refreshBtn);

    var toolsBody = document.createElement('div');
    toolsBody.className = 'mcp-tools-body';
    toolsBody.setAttribute('data-testid', 'mcp-tools-body-' + source.id);
    toolsSection.appendChild(toolsBody);

    body.appendChild(toolsSection);

    // F9 L3 (A-L3-2) — cache-first read. L1 persists the tools list to
    // `source.config._cache.tools` on every successful /test/connect from the
    // source-edit page (and the /test/connect endpoint writes it server-side
    // too). When the operator opens the details panel for a source that has
    // a populated cache, render synchronously from the cache — no probe, no
    // loading placeholder, no flicker.
    //
    // The auth-required notice path is reachable only via the probe (in
    // loadTools). That's correct: a source with cached tools has been
    // authenticated successfully at some point, so the cache itself is
    // auth-affirmative. If tokens are later revoked, the operator's explicit
    // Refresh-tools click triggers a fresh probe, which surfaces the
    // auth-required notice via the existing path.
    function _hasCachedTools(src) {
      return !!(src && src.config && src.config._cache &&
                Array.isArray(src.config._cache.tools));
    }

    function loadTools(forceRefresh) {
      // Cache-first on the initial load; the explicit Refresh-tools button
      // bypasses by passing forceRefresh=true.
      if (!forceRefresh && _hasCachedTools(source)) {
        _renderToolsCheckboxGroup(toolsBody, source, agent,
          source.config._cache.tools, onChange);
        return;
      }
      toolsBody.textContent = 'Loading tools…';
      if (!fetchMcpSourceTools) {
        toolsBody.textContent = 'Tool discovery not available.';
        return;
      }
      fetchMcpSourceTools(source.id, { forceRefresh: !!forceRefresh }).then(function (data) {
        _renderToolsCheckboxGroup(toolsBody, source, agent, data.tools || [], onChange);
      }).catch(function (err) {
        if (err && err.name === 'AuthRequired') {
          _renderAuthRequiredNotice(toolsBody, source.id);
        } else {
          toolsBody.innerHTML = '';
          var errEl = document.createElement('div');
          errEl.className = 'mcp-tools-error';
          errEl.setAttribute('data-testid', 'mcp-tools-error-' + source.id);
          errEl.textContent = 'Error loading tools: ' + (err && err.message ? err.message : String(err));
          toolsBody.appendChild(errEl);
        }
      });
    }

    refreshBtn.addEventListener('click', function () { loadTools(true); });

    // Credential overrides section intentionally omitted — see flight log
    // Anomaly A5. The bearer_token / headers / env fields don't fit the
    // OAuth sources operators care about; a future flight lands a per-agent
    // re-auth toggle. For now, agent-side override = which servers + which
    // tools.

    loadTools(false);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _renderToolsCheckboxGroup(container, source, agent, tools, onChange) {
    container.innerHTML = '';

    if (!tools || tools.length === 0) {
      var noTools = document.createElement('p');
      noTools.className = 'empty-state';
      noTools.setAttribute('data-testid', 'mcp-no-tools-msg-' + source.id);
      noTools.textContent = 'No tools available for this source.';
      container.appendChild(noTools);
      return;
    }

    var overrides = ((agent && agent.mcp_overrides) || {})[source.name] || {};
    var existingEnabled = overrides.enabled_tools;
    var existingDisabled = overrides.disabled_tools || [];
    var isAllowlist = Array.isArray(existingEnabled) && existingEnabled !== null;
    var mode = isAllowlist ? 'allowlist' : 'denylist';

    var group = document.createElement('div');
    group.className = 'mcp-tools-checkbox-group';
    group.setAttribute('data-mcp-tool-group', '');
    group.setAttribute('data-mcp-tool-mode', mode);
    group.setAttribute('data-testid', 'mcp-tools-checkbox-group-' + source.id);

    for (var i = 0; i < tools.length; i++) {
      (function (tool) {
        var toolName = tool.name;
        var prefixedName = 'mcp__' + _slugify(source.name) + '__' + toolName;
        var isChecked = isAllowlist
          ? existingEnabled.indexOf(toolName) !== -1
          : existingDisabled.indexOf(toolName) === -1;

        var label = document.createElement('label');
        label.className = 'mcp-tool-toggle-label';

        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = isChecked;
        checkbox.setAttribute('data-mcp-tool-toggle', toolName);
        checkbox.setAttribute('data-mcp-source', source.name);
        checkbox.setAttribute('data-testid', 'mcp-tool-toggle-' + source.id + '-' + toolName);
        checkbox.addEventListener('change', function () { if (onChange) onChange(); });

        var nameSpan = document.createElement('span');
        nameSpan.className = 'mcp-tool-toggle-name';
        nameSpan.textContent = toolName;

        var hintSpan = document.createElement('span');
        hintSpan.className = 'mcp-tool-toggle-hint';
        hintSpan.textContent = ' (' + prefixedName + ')';

        label.appendChild(checkbox);
        label.appendChild(nameSpan);
        label.appendChild(hintSpan);
        group.appendChild(label);
      })(tools[i]);
    }

    container.appendChild(group);
  }

  function _renderAuthRequiredNotice(container, sourceId) {
    container.innerHTML = '';
    var notice = document.createElement('div');
    notice.className = 'mcp-auth-required-notice';
    notice.setAttribute('data-testid', 'mcp-auth-required-notice-' + sourceId);
    notice.textContent = 'This source needs Test/auth on the source-edit page first. ';
    var link = document.createElement('a');
    link.href = '#studio/mcp-sources/' + encodeURIComponent(sourceId);
    link.textContent = 'Go to source settings';
    link.setAttribute('data-testid', 'mcp-auth-required-link-' + sourceId);
    notice.appendChild(link);
    container.appendChild(notice);
  }

  function _attachedSourceIds(agent) {
    var ids = {};
    if (!agent) return ids;
    var sourceIds = agent.mcp_source_ids || [];
    for (var i = 0; i < sourceIds.length; i++) ids[sourceIds[i]] = true;
    return ids;
  }

  function _parseSourceIdFromHash() {
    var hash = window.location.hash;
    if (hash.charAt(0) === '#') hash = hash.slice(1);
    var mcpsIdx = hash.indexOf('/mcps/');
    if (mcpsIdx === -1) return null;
    var afterMcps = hash.slice(mcpsIdx + '/mcps/'.length);
    if (!afterMcps) return null;
    if (afterMcps.charAt(afterMcps.length - 1) === '/') afterMcps = afterMcps.slice(0, -1);
    return afterMcps ? decodeURIComponent(afterMcps) : null;
  }

  function _slugify(name) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  }

  window.App.studio.renderMcpsTab = renderMcpsTab;
})();
