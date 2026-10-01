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
    // The focused source is owned by studio (its hydrateState applies the
    // URL's value); the tab never parses the URL itself.
    var pendingSourceId = callbacks.pendingSourceId || null;

    if (!allSources || allSources.length === 0) {
      _renderEmptyState(panel);
      return;
    }

    _renderSourcesList(panel, agent, allSources, fetchMcpSourceTools,
      onChange, onSelectedSourceChange, pendingSourceId);

  }

  // ── Empty state ───────────────────────────────────────────────────────────

  function _renderEmptyState(panel) {
    var div = document.createElement('div');
    div.className = 'mcp-empty-state';
    div.setAttribute('data-testid', 'mcp-empty-state');
    div.appendChild(document.createTextNode('No MCP sources registered yet. '));
    var addLink = document.createElement('a');
    addLink.href = App.router.href({ destination: 'library', section: 'mcp' });
    addLink.textContent = 'Add one in the Library.';
    div.appendChild(addLink);
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

    // M21 F01 L02 (DD3): the editor's fetch includes every agent's
    // self-configuration surface row (`?include_agent_surfaces=1`), but
    // this tab must show an agent ONLY its own — never another agent's.
    // Create-mode (agent === null) shows none.
    var visibleSources = [];
    for (var vi = 0; vi < allSources.length; vi++) {
      var candidate = allSources[vi];
      var marker = candidate.config && candidate.config.self_configuration;
      if (marker && typeof marker === 'object') {
        if (!agent || marker.agent !== agent.name) continue;
      }
      visibleSources.push(candidate);
    }

    if (visibleSources.length === 0) {
      _renderEmptyState(panel);
      return;
    }

    for (var i = 0; i < visibleSources.length; i++) {
      (function (source) {
        var isAttached = attachedIds[source.id] === true;
        var isSelfConfigurationRow = !!(source.config && source.config.self_configuration &&
          typeof source.config.self_configuration === 'object');

        // Each MCP source = a tile echoing .entity-tile (quiet surface +
        // hairline border). The tile composes: row1 (toggle + name + protocol badge +
        // Refresh) + expand button (tool count + chevron) + collapsible
        // tools body (the per-tool tiles). Mission 08 F4 L2 vibe.
        var tile = document.createElement('div');
        tile.className = 'mcp-source-tile';
        tile.setAttribute('data-source-id', source.id);
        tile.setAttribute('data-testid', 'mcp-source-row-' + source.id);
        var startsExpanded = pendingSourceId === source.id;
        tile.setAttribute('aria-expanded', startsExpanded ? 'true' : 'false');

        // ── Row 1: toggle + name + protocol + Refresh ──────────────────
        var row1 = document.createElement('div');
        row1.className = 'mcp-source-tile-row1';

        var toggleLabel = document.createElement('label');
        toggleLabel.className = 'mcp-source-tile-toggle';

        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'tool-toggle mcp-source-toggle';
        checkbox.setAttribute('data-mcp-source-toggle', '');
        checkbox.setAttribute('data-mcp-source-id', source.id);
        checkbox.setAttribute('data-testid', 'mcp-source-toggle-' + source.id);
        checkbox.checked = isAttached;
        if (isSelfConfigurationRow) {
          // M21 F01 L02: the surface's OWN attach toggle is locked
          // checked+disabled — it is managed exclusively from the
          // Self-configuration tab, never from here. A disabled checked
          // checkbox still matches `:checked` in the DOM, so
          // collectFormData's `[data-mcp-source-toggle]:checked` scan
          // keeps the id in `mcp_source_ids` on save; the per-tool
          // checkboxes below stay fully editable (the operator's
          // per-capability control).
          checkbox.checked = true;
          checkbox.disabled = true;
        }
        toggleLabel.appendChild(checkbox);

        var visualSwitch = document.createElement('span');
        visualSwitch.className = 'tool-switch';
        toggleLabel.appendChild(visualSwitch);

        row1.appendChild(toggleLabel);

        var nameSpan = document.createElement('span');
        nameSpan.className = 'mcp-source-tile-name';
        nameSpan.textContent = source.name;
        row1.appendChild(nameSpan);

        if (isSelfConfigurationRow) {
          var hint = document.createElement('span');
          hint.className = 'mcp-source-tile-self-configuration-hint';
          hint.setAttribute('data-testid', 'mcp-source-self-configuration-hint-' + source.id);
          hint.textContent = 'managed on the Self-configuration tab';
          row1.appendChild(hint);
        }

        // Enabled-count chicklet (matches the built-in Tools tab category
        // chicklet shape) — shows live `X / Y enabled`. Hidden until the
        // source has been connected (cache populated). F4 L2.
        var enabledChicklet = document.createElement('span');
        enabledChicklet.className = 'mcp-source-tile-enabled-count tools-category-tile-count';
        enabledChicklet.hidden = true;
        row1.appendChild(enabledChicklet);

        var protocolBadge = document.createElement('span');
        protocolBadge.className = 'mcp-source-tile-protocol';
        protocolBadge.textContent = source.type === 'stdio' ? 'stdio' : 'http';
        row1.appendChild(protocolBadge);

        var refreshBtn = document.createElement('button');
        refreshBtn.type = 'button';
        refreshBtn.className = 'btn-outlined-primary mcp-refresh-tools-btn';
        refreshBtn.setAttribute('data-testid', 'mcp-refresh-tools-btn-' + source.id);
        refreshBtn.innerHTML = window.App.icon('refresh') + ' Refresh';
        row1.appendChild(refreshBtn);

        tile.appendChild(row1);

        // ── Subtitle: server-declared identity (F4 L2, M08) ─────────────
        // /test/connect writes serverInfo + instructions into
        // source.config._cache when the operator probes. Only render the
        // subtitle when the cache is populated (i.e. the source has been
        // connected at least once) so create-mode tiles stay clean. The
        // instructions field, when present, hangs off the subtitle as a
        // `title=` tooltip so hover reveals the full server-supplied prose.
        var serverInfo = (source && source.config && source.config._cache &&
                          source.config._cache.server_info) || null;
        var instructionsText = (source && source.config && source.config._cache &&
                                source.config._cache.instructions) || null;
        if (serverInfo) {
          var subtitle = document.createElement('div');
          subtitle.className = 'mcp-source-tile-subtitle';
          subtitle.setAttribute('data-testid', 'mcp-source-subtitle-' + source.id);
          var labelText = serverInfo.title || serverInfo.name || '';
          var versionText = serverInfo.version ? ' · v' + serverInfo.version : '';
          subtitle.textContent = labelText + versionText;
          if (instructionsText) {
            // Hover reveals the full instructions prose. The class
            // .has-instructions lets the CSS hint at the affordance with a
            // help-cursor without changing the textual content.
            subtitle.classList.add('has-instructions');
            subtitle.title = instructionsText;
          }
          // Only append if we actually produced visible text — guards
          // against servers that announce serverInfo with only the icons
          // field populated (spec-legal but useless to surface).
          if (subtitle.textContent.trim()) {
            tile.appendChild(subtitle);
          }
        }

        // ── Expand button: tool count + chevron ───────────────────────
        var expandBtn = document.createElement('button');
        expandBtn.type = 'button';
        expandBtn.className = 'mcp-source-tile-expand-btn';
        expandBtn.setAttribute('aria-expanded', startsExpanded ? 'true' : 'false');
        expandBtn.setAttribute('data-testid', 'mcp-source-expand-' + source.id);

        var countSpan = document.createElement('span');
        countSpan.className = 'mcp-source-tile-tool-count';
        var chevron = document.createElement('span');
        chevron.className = 'mcp-source-tile-chevron';
        chevron.textContent = '▸';

        function _cachedTotal(src) {
          return (src && src.config && src.config._cache &&
                  Array.isArray(src.config._cache.tools))
            ? src.config._cache.tools.length : null;
        }
        // Compute "enabled" count from agent.mcp_overrides + cache, applying
        // the same allowlist/denylist logic as _renderToolsCheckboxGroup.
        function _enabledFromCache(src, ag) {
          if (!_hasCachedTools(src)) return null;
          var tools = src.config._cache.tools;
          var overrides = ((ag && ag.mcp_overrides) || {})[src.name] || {};
          var enabledList = overrides.enabled_tools;
          var disabledList = overrides.disabled_tools || [];
          var isAllowlist = Array.isArray(enabledList) && enabledList !== null;
          var count = 0;
          for (var i = 0; i < tools.length; i++) {
            var n = tools[i].name;
            var checked = isAllowlist
              ? enabledList.indexOf(n) !== -1
              : disabledList.indexOf(n) === -1;
            if (checked) count++;
          }
          return count;
        }
        function _setCount(enabled, total) {
          // Expand-button text: total tool count (no enabled).
          if (total === null) {
            countSpan.textContent = 'Tools';
          } else {
            countSpan.innerHTML = '<strong>' + total + '</strong> tool' + (total === 1 ? '' : 's');
          }
          // Chicklet on row 1: `X / Y enabled`, mirroring the built-in
          // Tools category-tile chicklet. Hidden when no cache (no count).
          if (total === null || enabled === null) {
            enabledChicklet.hidden = true;
            enabledChicklet.textContent = '';
          } else {
            enabledChicklet.hidden = false;
            enabledChicklet.textContent = enabled + ' / ' + total + ' enabled';
          }
        }
        // Re-read counts from the rendered DOM (post-_renderToolsCheckboxGroup).
        // Used when individual tool toggles change AND after first tool-load.
        function _recountFromDom() {
          var checkboxes = toolsBody.querySelectorAll('[data-mcp-tool-toggle]');
          if (checkboxes.length === 0) {
            // DOM not yet populated; fall back to cache compute.
            _setCount(_enabledFromCache(source, agent), _cachedTotal(source));
            return;
          }
          var enabled = 0;
          for (var i = 0; i < checkboxes.length; i++) {
            if (checkboxes[i].checked) enabled++;
          }
          _setCount(enabled, checkboxes.length);
        }
        function _hasCachedTools(src) {
          return !!(src && src.config && src.config._cache &&
                    Array.isArray(src.config._cache.tools));
        }
        _setCount(_enabledFromCache(source, agent), _cachedTotal(source));
        expandBtn.appendChild(countSpan);
        expandBtn.appendChild(chevron);

        tile.appendChild(expandBtn);

        // ── Tools body (collapsed by default; tile-style tools inside) ──
        var toolsBody = document.createElement('div');
        toolsBody.className = 'mcp-source-tile-tools tool-row-overrides-body';
        toolsBody.setAttribute('data-testid', 'mcp-source-details-body-' + source.id);
        toolsBody.hidden = !startsExpanded;
        var loadingP = document.createElement('p');
        loadingP.className = 'loading';
        loadingP.textContent = 'Expand to load tools…';
        toolsBody.appendChild(loadingP);
        tile.appendChild(toolsBody);

        // Wire each rendered tool checkbox to re-trigger the source-tile
        // count after every toggle. The _renderToolsCheckboxGroup helper
        // already wires `onChange` for dirty tracking; this adds a second
        // listener for the local count display.
        function _wireToolCheckboxesAndRecount() {
          var checkboxes = toolsBody.querySelectorAll('[data-mcp-tool-toggle]');
          for (var i = 0; i < checkboxes.length; i++) {
            checkboxes[i].addEventListener('change', _recountFromDom);
          }
          _recountFromDom();
        }
        function loadTools(forceRefresh) {
          if (!forceRefresh && _hasCachedTools(source)) {
            _renderToolsCheckboxGroup(toolsBody, source, agent,
              source.config._cache.tools, onChange);
            _wireToolCheckboxesAndRecount();
            return;
          }
          toolsBody.textContent = 'Loading tools…';
          if (!fetchMcpSourceTools) {
            toolsBody.textContent = 'Tool discovery not available.';
            return;
          }
          fetchMcpSourceTools(source.id, { forceRefresh: !!forceRefresh }).then(function (data) {
            var tools = data.tools || [];
            _renderToolsCheckboxGroup(toolsBody, source, agent, tools, onChange);
            _wireToolCheckboxesAndRecount();
          }).catch(function (err) {
            if (err && err.name === 'AuthRequired') {
              _renderAuthRequiredNotice(toolsBody, source);
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

        var loadedOnce = false;
        function _setExpanded(expanded) {
          tile.setAttribute('aria-expanded', expanded ? 'true' : 'false');
          expandBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
          toolsBody.hidden = !expanded;
          if (expanded) {
            if (!loadedOnce) {
              loadedOnce = true;
              loadTools(false);
            }
            if (onSelectedSourceChange) onSelectedSourceChange(source.id);
          } else {
            if (onSelectedSourceChange) {
              var currentSourceId = _parseSourceIdFromHash();
              if (currentSourceId === source.id) onSelectedSourceChange(null);
            }
          }
        }

        // Wire toggle change → onChange (dirty tracking + URL routing).
        checkbox.addEventListener('change', function () {
          if (onChange) onChange();
        });

        // Expand button toggles the tools panel.
        expandBtn.addEventListener('click', function () {
          var nextExpanded = expandBtn.getAttribute('aria-expanded') !== 'true';
          _setExpanded(nextExpanded);
        });

        // Refresh button — opens the panel if closed, force-reloads tools.
        refreshBtn.addEventListener('click', function () {
          if (toolsBody.hidden) {
            loadedOnce = true;
            _setExpanded(true);
          }
          loadTools(true);
        });

        // Auto-load if pendingSourceId opens us by default.
        if (startsExpanded) {
          loadedOnce = true;
          loadTools(false);
          if (onSelectedSourceChange) onSelectedSourceChange(source.id);
        }

        listContainer.appendChild(tile);
      })(visibleSources[i]);
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
    refreshBtn.className = 'btn-outlined-primary mcp-refresh-tools-btn';
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
          _renderAuthRequiredNotice(toolsBody, source);
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
        // Full prefixed name lives as a tooltip on hover; primary text is
        // name + description (Mission 08 F4 L2 vibe).
        label.title = prefixedName;

        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'checkbox-primary';
        checkbox.checked = isChecked;
        checkbox.setAttribute('data-mcp-tool-toggle', toolName);
        checkbox.setAttribute('data-mcp-source', source.name);
        checkbox.setAttribute('data-testid', 'mcp-tool-toggle-' + source.id + '-' + toolName);
        checkbox.addEventListener('change', function () { if (onChange) onChange(); });

        var textWrap = document.createElement('div');
        textWrap.className = 'mcp-tool-text';

        var nameSpan = document.createElement('span');
        nameSpan.className = 'mcp-tool-toggle-name';
        nameSpan.textContent = toolName;
        textWrap.appendChild(nameSpan);

        if (tool.description) {
          var descSpan = document.createElement('span');
          descSpan.className = 'mcp-tool-description';
          var fullDesc = tool.description;
          var truncated = fullDesc.length > 100
            ? fullDesc.slice(0, 100) + '…'
            : fullDesc;
          descSpan.textContent = ' — ' + truncated;
          // Full text on hover for discoverability.
          descSpan.title = fullDesc;
          textWrap.appendChild(descSpan);
        }

        label.appendChild(checkbox);
        label.appendChild(textWrap);
        group.appendChild(label);
      })(tools[i]);
    }

    container.appendChild(group);
  }

  function _renderAuthRequiredNotice(container, source) {
    var sourceId = source.id;
    var sourceName = source.name || source.id;
    container.innerHTML = '';
    var notice = document.createElement('div');
    notice.className = 'mcp-auth-required-notice';
    notice.setAttribute('data-testid', 'mcp-auth-required-notice-' + sourceId);
    notice.textContent = '“' + sourceName + '” needs Test/auth on the source-edit page first. ';
    var link = document.createElement('a');
    link.href = App.router.href({ destination: 'library', section: 'mcp', id: sourceId });
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

  function _slugify(name) {
    // LD7 (M21 F01 L03): keep hyphens/underscores through the substitution
    // (they are also allowed by the backend's `mcp/_tool.py:
    // _normalize_source_name`) so the tooltip-only prefixed name this
    // builds agrees with the ACTUAL tool name the agent sees for a name
    // like the self-configuration surface's constant row name
    // ("self-configuration") — previously this collapsed the hyphen to an
    // underscore while the backend preserved it, showing a tooltip that
    // did not match reality.
    return name.toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_|_$/g, '');
  }

  window.App.studio.renderMcpsTab = renderMcpsTab;
})();
