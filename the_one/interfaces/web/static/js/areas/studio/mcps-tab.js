// App.studio.renderMcpsTab — agent-editor MCPs tab (Holograph two-mode layout).
//
// Replaces the Mission-08 inline-<details> row pattern with the Holograph
// two-mode dispatch:
//
//   Mode 1 — List view (no source selected)
//     A 3-column .mcp-sources-grid of .mcp-source-card tiles. Each card shows
//     the source name, transport chip, attach toggle, and a short summary.
//     Clicking the card body (not the toggle) selects the source and switches
//     to Mode 2.
//
//   Mode 2 — Per-attachment editor (source selected)
//     Full-pane editor rendered inside the same panel: header strip (name +
//     transport + back-arrow), optional auth-required callout, tools-mode
//     segmented control (allowlist / denylist), cached-tools grid with per-tool
//     checkboxes.
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
    while (panel.firstChild) panel.removeChild(panel.firstChild);
    callbacks = callbacks || {};
    var fetchMcpSourceTools = callbacks.fetchMcpSourceTools;
    var onChange = callbacks.onChange || function () {};
    var onSelectedSourceChange = callbacks.onSelectedSourceChange || function () {};
    var pendingSourceId = callbacks.pendingSourceId || _parseSourceIdFromHash();

    // Remove stale hashchange listener if any.
    _removeHashListener(panel);

    if (!allSources || allSources.length === 0) {
      _renderEmptyState(panel);
      return;
    }

    if (pendingSourceId) {
      // Mode 2: find the source and render the attachment editor directly.
      var selectedSource = _findSource(allSources, pendingSourceId);
      if (selectedSource) {
        _renderAttachmentEditor(panel, selectedSource, agent, allSources,
          fetchMcpSourceTools, onChange, onSelectedSourceChange);
      } else {
        // Unknown source id — fall back to list view.
        _renderSourcesGrid(panel, agent, allSources, null,
          fetchMcpSourceTools, onChange, onSelectedSourceChange);
      }
    } else {
      // Mode 1: list view.
      _renderSourcesGrid(panel, agent, allSources, null,
        fetchMcpSourceTools, onChange, onSelectedSourceChange);
    }

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
    var text = document.createTextNode('No MCP sources registered yet. ');
    div.appendChild(text);
    var link = document.createElement('a');
    link.href = '#studio/mcp-sources';
    link.textContent = 'Add one in MCP Sources.';
    div.appendChild(link);
    panel.appendChild(div);
  }

  // ── Mode 1: sources list grid ─────────────────────────────────────────────
  //
  // 3-column .mcp-sources-grid. Each .mcp-source-card contains:
  //   - .mcp-source-head: attach toggle + source name + transport .chip.mono
  //   - .mcp-source-body: short description / command preview / counts
  //
  // Clicking the card body (not the toggle) triggers Mode 2.

  function _renderSourcesGrid(panel, agent, allSources, selectedSourceId,
      fetchMcpSourceTools, onChange, onSelectedSourceChange) {
    var attachedIds = _attachedSourceIds(agent);

    var grid = document.createElement('div');
    grid.className = 'mcp-sources-grid';
    grid.setAttribute('data-testid', 'mcp-sources-list');

    for (var i = 0; i < allSources.length; i++) {
      (function (source) {
        var isAttached = attachedIds[source.id] === true;
        var isSelected = selectedSourceId === source.id;

        var card = document.createElement('div');
        card.className = 'mcp-source-card' + (isSelected ? ' selected' : '');
        card.setAttribute('data-testid', 'mcp-source-card-' + source.id);
        card.dataset.sourceId = source.id;

        // ── Head: toggle + name + transport chip ──
        var head = document.createElement('div');
        head.className = 'mcp-source-head';

        // Attach checkbox — clicking this does NOT navigate to Mode 2.
        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.setAttribute('data-mcp-source-toggle', '');
        checkbox.setAttribute('data-mcp-source-id', source.id);
        checkbox.setAttribute('data-testid', 'mcp-source-toggle-' + source.id);
        checkbox.checked = isAttached;
        checkbox.addEventListener('change', function (e) {
          e.stopPropagation();
          if (onChange) onChange();
        });
        // Prevent checkbox clicks from reaching the card click handler.
        checkbox.addEventListener('click', function (e) { e.stopPropagation(); });
        head.appendChild(checkbox);

        var nameEl = document.createElement('span');
        nameEl.className = 'agent-card-title';
        nameEl.style.flex = '1';
        nameEl.textContent = source.name;
        head.appendChild(nameEl);

        var transportChip = document.createElement('span');
        transportChip.className = 'chip mono';
        transportChip.textContent = source.type === 'stdio' ? 'stdio' : 'streamable-http';
        head.appendChild(transportChip);

        card.appendChild(head);

        // ── Body: description / command / counts ──
        var body = document.createElement('div');
        body.className = 'mcp-source-body';

        var metaLine = '';
        if (source.type === 'stdio') {
          metaLine = (source.config && source.config.command) ? source.config.command : '';
        } else {
          metaLine = (source.config && source.config.url) ? source.config.url : '';
        }
        var cachedCount = (source.config && source.config._cache &&
          Array.isArray(source.config._cache.tools))
          ? source.config._cache.tools.length : 0;

        var summaryParts = [];
        if (metaLine) summaryParts.push(metaLine);
        if (cachedCount > 0) summaryParts.push(cachedCount + ' tool' + (cachedCount !== 1 ? 's' : ''));
        body.textContent = summaryParts.join(' · ') || 'No details available';

        card.appendChild(body);

        // Clicking the card (anywhere except the toggle) opens Mode 2.
        card.addEventListener('click', function () {
          if (onSelectedSourceChange) onSelectedSourceChange(source.id);
          while (panel.firstChild) panel.removeChild(panel.firstChild);
          _removeHashListener(panel);
          _renderAttachmentEditor(panel, source, agent, allSources,
            fetchMcpSourceTools, onChange, onSelectedSourceChange);
        });

        grid.appendChild(card);
      })(allSources[i]);
    }

    panel.appendChild(grid);
  }

  // ── Mode 2: per-attachment editor ────────────────────────────────────────
  //
  // Full-pane editor:
  //   - Header strip: back-arrow + source name + transport chip
  //   - Optional auth-required callout
  //   - "Tools mode" segmented control (allowlist / denylist)
  //   - "Cached tools" grid of .tool-card checkboxes
  //
  // A hidden attach checkbox for the source is also rendered so that
  // [data-mcp-source-toggle][data-mcp-source-id]:checked is still
  // collectible by the save flow while in Mode 2.

  function _renderAttachmentEditor(panel, source, agent, allSources,
      fetchMcpSourceTools, onChange, onSelectedSourceChange) {
    var overrides = ((agent && agent.mcp_overrides) || {})[source.name] || {};
    var isAllowlist = Array.isArray(overrides.enabled_tools);
    var mode = isAllowlist ? 'allowlist' : 'denylist';
    var attachedIds = _attachedSourceIds(agent);
    var isAttached = attachedIds[source.id] === true;

    var editorDiv = document.createElement('div');
    editorDiv.className = 'editor-section';
    editorDiv.setAttribute('data-testid', 'agent-mcp-attachment-editor');
    editorDiv.setAttribute('data-source-id', source.id);

    // ── Hidden attach checkbox (save-flow selector contract) ──
    // While in Mode 2 the form still needs to find the source's attach
    // checkbox. Keep it hidden — it carries the same attach state as the
    // card-view checkbox would.
    var hiddenCheckbox = document.createElement('input');
    hiddenCheckbox.type = 'checkbox';
    hiddenCheckbox.setAttribute('data-mcp-source-toggle', '');
    hiddenCheckbox.setAttribute('data-mcp-source-id', source.id);
    hiddenCheckbox.setAttribute('data-testid', 'mcp-source-toggle-' + source.id);
    hiddenCheckbox.checked = isAttached;
    hiddenCheckbox.style.display = 'none';
    hiddenCheckbox.addEventListener('change', function () { if (onChange) onChange(); });
    editorDiv.appendChild(hiddenCheckbox);

    // ── Header strip ──
    var headerStrip = document.createElement('div');
    headerStrip.style.cssText = 'display:flex; align-items:center; gap:10px; margin-bottom:16px;';

    var backBtn = document.createElement('button');
    backBtn.className = 'btn btn-ghost';
    backBtn.type = 'button';
    backBtn.setAttribute('data-action', 'back');
    backBtn.setAttribute('aria-label', 'Back to attachments');

    // Build back-arrow SVG via DOM to avoid innerHTML.
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'icn');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M10 4l-4 4 4 4');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '1.6');
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke-linecap', 'round');
    svg.appendChild(path);
    backBtn.appendChild(svg);

    backBtn.addEventListener('click', function () {
      if (onSelectedSourceChange) onSelectedSourceChange(null);
      while (panel.firstChild) panel.removeChild(panel.firstChild);
      _removeHashListener(panel);
      _renderSourcesGrid(panel, agent, allSources, null,
        fetchMcpSourceTools, onChange, onSelectedSourceChange);
    });
    headerStrip.appendChild(backBtn);

    var titleEl = document.createElement('span');
    titleEl.className = 'editor-title';
    titleEl.style.fontSize = '15px';
    titleEl.textContent = source.name;
    headerStrip.appendChild(titleEl);

    var transportChip = document.createElement('span');
    transportChip.className = 'chip mono';
    transportChip.textContent = source.type === 'stdio' ? 'stdio' : 'streamable-http';
    headerStrip.appendChild(transportChip);

    editorDiv.appendChild(headerStrip);

    // ── Auth-required callout (only when source.auth_required) ──
    if (source.auth_required) {
      var callout = document.createElement('div');
      callout.className = 'callout warn';
      callout.style.marginBottom = '14px';
      callout.appendChild(document.createTextNode('Connect this source from the '));
      var calloutLink = document.createElement('a');
      calloutLink.href = '#studio/mcp-sources/' + encodeURIComponent(source.id);
      calloutLink.textContent = 'MCP Sources page';
      callout.appendChild(calloutLink);
      callout.appendChild(document.createTextNode(' to enable tool selection.'));
      editorDiv.appendChild(callout);
    }

    // ── Tools mode segmented control ──
    var modeLabel = document.createElement('div');
    modeLabel.className = 'section-label';
    modeLabel.textContent = 'Tools mode';
    editorDiv.appendChild(modeLabel);

    var segControl = document.createElement('div');
    segControl.className = 'seg';
    segControl.style.marginBottom = '18px';
    segControl.setAttribute('data-attachment-mode', '');
    segControl.dataset.mode = mode;

    var allowlistBtn = document.createElement('button');
    allowlistBtn.className = 'seg-btn' + (mode === 'allowlist' ? ' active' : '');
    allowlistBtn.type = 'button';
    allowlistBtn.setAttribute('data-mode', 'allowlist');
    allowlistBtn.textContent = 'Allowlist';

    var denylistBtn = document.createElement('button');
    denylistBtn.className = 'seg-btn' + (mode === 'denylist' ? ' active' : '');
    denylistBtn.type = 'button';
    denylistBtn.setAttribute('data-mode', 'denylist');
    denylistBtn.textContent = 'Denylist';

    segControl.appendChild(allowlistBtn);
    segControl.appendChild(denylistBtn);
    editorDiv.appendChild(segControl);

    // ── Cached tools section ──
    var toolsLabel = document.createElement('div');
    toolsLabel.className = 'section-label';
    toolsLabel.setAttribute('data-testid', 'mcp-tools-count-label-' + source.id);
    editorDiv.appendChild(toolsLabel);

    var toolsGridWrap = document.createElement('div');
    toolsGridWrap.className = 'tools-grid';
    toolsGridWrap.setAttribute('data-testid', 'mcp-tools-grid-' + source.id);
    editorDiv.appendChild(toolsGridWrap);

    panel.appendChild(editorDiv);

    // ── Mode-switch wiring ──
    // Switching mode inverts the current selection by collecting the
    // currently-checked tool names then re-rendering with new mode semantics.
    function switchMode(newMode) {
      if (newMode === segControl.dataset.mode) return;

      var currentChecked = [];
      var checkboxes = toolsGridWrap.querySelectorAll('[data-mcp-tool-toggle]');
      for (var c = 0; c < checkboxes.length; c++) {
        if (checkboxes[c].checked) {
          currentChecked.push(checkboxes[c].getAttribute('data-tool-name'));
        }
      }

      segControl.dataset.mode = newMode;
      allowlistBtn.className = 'seg-btn' + (newMode === 'allowlist' ? ' active' : '');
      denylistBtn.className = 'seg-btn' + (newMode === 'denylist' ? ' active' : '');

      _renderToolCards(toolsGridWrap, source, agent, newMode, currentChecked,
        cachedToolsList, toolsLabel, onChange);

      if (onChange) onChange();
    }

    allowlistBtn.addEventListener('click', function () { switchMode('allowlist'); });
    denylistBtn.addEventListener('click', function () { switchMode('denylist'); });

    // ── Lazy-load tools then render ──
    var cachedToolsList = [];

    // Show a loading indicator while the async fetch is in flight.
    if (!_hasCachedTools(source)) {
      toolsLabel.textContent = 'Cached tools…';
      var loadingEl = document.createElement('p');
      loadingEl.className = 'loading';
      loadingEl.textContent = 'Loading tools…';
      toolsGridWrap.appendChild(loadingEl);
    }

    _ensureToolsLoaded(source, fetchMcpSourceTools).then(function (tools) {
      cachedToolsList = tools;
      _renderToolCards(toolsGridWrap, source, agent, mode, null, tools, toolsLabel, onChange);
    }).catch(function (err) {
      toolsLabel.textContent = 'Cached tools (0)';
      while (toolsGridWrap.firstChild) toolsGridWrap.removeChild(toolsGridWrap.firstChild);
      if (err && err.name === 'AuthRequired') {
        _renderAuthRequiredNotice(toolsGridWrap, source);
      } else {
        var errEl = document.createElement('div');
        errEl.className = 'mcp-tools-error';
        errEl.setAttribute('data-testid', 'mcp-tools-error-' + source.id);
        errEl.textContent = 'Error loading tools: ' + (err && err.message ? err.message : String(err));
        toolsGridWrap.appendChild(errEl);
      }
    });
  }

  // ── Tool cards ────────────────────────────────────────────────────────────
  //
  // Renders the .tools-grid contents. Each .tool-card has:
  //   - .tool-head: tool name + per-tool checkbox
  //   - .tool-desc: tool description
  //
  // overriddenChecked: when non-null, uses this list of tool names as the
  // checked set (used when switching mode). When null, derives checked state
  // from agent.mcp_overrides[source.name].

  function _renderToolCards(container, source, agent, mode, overriddenChecked,
      tools, countLabel, onChange) {
    while (container.firstChild) container.removeChild(container.firstChild);

    if (!tools || tools.length === 0) {
      var noTools = document.createElement('p');
      noTools.className = 'empty-state';
      noTools.setAttribute('data-testid', 'mcp-no-tools-msg-' + source.id);
      noTools.textContent = 'No tools available for this source.';
      container.appendChild(noTools);
      if (countLabel) countLabel.textContent = 'Cached tools (0)';
      return;
    }

    if (countLabel) countLabel.textContent = 'Cached tools (' + tools.length + ')';

    var overrides = ((agent && agent.mcp_overrides) || {})[source.name] || {};
    var existingEnabled = overrides.enabled_tools;
    var existingDisabled = overrides.disabled_tools || [];
    var isAllowlist = mode === 'allowlist';

    for (var i = 0; i < tools.length; i++) {
      (function (tool) {
        var toolName = tool.name;

        var isChecked;
        if (overriddenChecked !== null && overriddenChecked !== undefined) {
          // Mode was just switched — use the caller-supplied checked set.
          isChecked = overriddenChecked.indexOf(toolName) !== -1;
        } else if (isAllowlist) {
          isChecked = Array.isArray(existingEnabled) && existingEnabled.indexOf(toolName) !== -1;
        } else {
          // Denylist: checked means NOT denied.
          isChecked = existingDisabled.indexOf(toolName) === -1;
        }

        var cardEl = document.createElement('div');
        cardEl.className = 'tool-card';

        var headEl = document.createElement('div');
        headEl.className = 'tool-head';

        var nameSpan = document.createElement('span');
        nameSpan.className = 'tool-name';
        nameSpan.textContent = toolName;
        headEl.appendChild(nameSpan);

        var toggleWrap = document.createElement('div');
        toggleWrap.className = 'tool-toggle-wrap';

        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = isChecked;
        checkbox.setAttribute('data-mcp-tool-toggle', toolName);
        checkbox.setAttribute('data-mcp-source', source.name);
        checkbox.setAttribute('data-tool-name', toolName);
        checkbox.setAttribute('data-testid', 'mcp-tool-toggle-' + source.id + '-' + toolName);
        checkbox.addEventListener('change', function () { if (onChange) onChange(); });
        toggleWrap.appendChild(checkbox);

        headEl.appendChild(toggleWrap);
        cardEl.appendChild(headEl);

        if (tool.description) {
          var descEl = document.createElement('div');
          descEl.className = 'tool-desc';
          descEl.textContent = tool.description;
          cardEl.appendChild(descEl);
        }

        container.appendChild(cardEl);
      })(tools[i]);
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  // Cache-first tool loader. Resolves with the tool list from the source's
  // config._cache.tools if present; otherwise calls fetchMcpSourceTools.
  // Mirrors the cache-first semantics of the old _populateDetailsBody.
  function _ensureToolsLoaded(source, fetchMcpSourceTools) {
    if (_hasCachedTools(source)) {
      return Promise.resolve(source.config._cache.tools);
    }
    if (typeof fetchMcpSourceTools === 'function') {
      return fetchMcpSourceTools(source.id).then(function (data) {
        var tools = (data && data.tools) ? data.tools
          : (Array.isArray(data) ? data : []);
        if (!source.config) source.config = {};
        if (!source.config._cache) source.config._cache = {};
        source.config._cache.tools = tools;
        return tools;
      });
    }
    return Promise.resolve([]);
  }

  function _hasCachedTools(source) {
    return !!(source && source.config && source.config._cache &&
              Array.isArray(source.config._cache.tools));
  }

  function _renderAuthRequiredNotice(container, source) {
    var sourceId = source.id;
    var sourceName = source.name || source.id;
    while (container.firstChild) container.removeChild(container.firstChild);
    var notice = document.createElement('div');
    notice.className = 'mcp-auth-required-notice';
    notice.setAttribute('data-testid', 'mcp-auth-required-notice-' + sourceId);
    notice.textContent = '"' + sourceName + '" needs Test/auth on the source-edit page first. ';
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

  function _findSource(allSources, sourceId) {
    for (var i = 0; i < allSources.length; i++) {
      if (allSources[i].id === sourceId) return allSources[i];
    }
    return null;
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

  function _removeHashListener(panel) {
    if (panel._mcpsTabHashHandler) {
      window.removeEventListener('hashchange', panel._mcpsTabHashHandler);
      panel._mcpsTabHashHandler = null;
    }
  }

  window.App.studio.renderMcpsTab = renderMcpsTab;
})();
