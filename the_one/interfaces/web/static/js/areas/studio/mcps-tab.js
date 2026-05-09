// App.studio.renderMcpsTab — agent-editor MCPs tab (F8 L3 full implementation).
//
// Replaces the 22-line empty-state stub with a fully-functional per-agent
// MCP attach + override + per-tool toggle UI. Three rendering branches:
//   1. Empty state — when allSources is [].
//   2. Chip-list — default view; shows all sources; click toggles attach/detach.
//   3. Per-attachment editor — shown when a source-id is selected (chip click
//      or deep-link via #studio/agents/{name}/mcps/{source-id}).
//
// Public API:
//   App.studio.renderMcpsTab(panel, agent, allSources, callbacks)
//     panel       — DOM element (the MCPs tabpanel)
//     agent       — AgentConfig object (may be null for create-mode, which is
//                   fine; the tab is read-only without an agent)
//     allSources  — array of MCPSource objects from /api/mcp-sources
//     callbacks   — { fetchMcpSourceTools, onChange, onSelectedSourceChange,
//                     pendingSourceId }
//
// Credential override schemas (hardcoded — avoids a fresh fetch on each open):
//   stdio         → env: dict[str, str] + Substitute
//   streamable-http → bearer_token: str + Substitute, headers: dict + Substitute
//
// Save flow: studio.js::collectFormData walks:
//   [data-mcp-override-source][data-mcp-override-field]  → mcp_overrides
//   [data-mcp-tool-toggle][data-mcp-source]              → enabled_tools/disabled_tools
//   .chip-area[data-type="mcp"] .chip                    → mcp_source_ids
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Hardcoded override prop shapes (mirrors L1 StdioMCPOverride /
  // StreamableHttpMCPOverride — no runtime schema fetch needed for L3).
  var MCP_OVERRIDE_SCHEMAS = {
    stdio: {
      env: {
        type: 'object',
        title: 'Environment variables',
        description: 'Key/value pairs overlaid on the source\'s secrets["env"] at spawn time.',
        x_marker: 'Substitute'
      }
    },
    'streamable-http': {
      bearer_token: {
        type: 'string',
        title: 'Bearer token',
        description: 'Replaces the source-stored bearer token. Use __MASKED__ to preserve the current value.',
        x_marker: 'Substitute'
      },
      headers: {
        type: 'object',
        title: 'HTTP headers',
        description: 'Key/value pairs overlaid on the source\'s HTTP request headers.',
        x_marker: 'Substitute'
      }
    }
  };

  // ── Main entry point ──────────────────────────────────────────────────────

  function renderMcpsTab(panel, agent, allSources, callbacks) {
    panel.innerHTML = '';
    callbacks = callbacks || {};
    var fetchMcpSourceTools = callbacks.fetchMcpSourceTools;
    var onChange = callbacks.onChange || function () {};
    var onSelectedSourceChange = callbacks.onSelectedSourceChange || function () {};
    var pendingSourceId = callbacks.pendingSourceId || null;

    // Remove stale hashchange listener if any (from a prior render cycle on
    // the same panel object — e.g. agent re-select without DOM rebuild).
    if (panel._mcpsTabHashHandler) {
      window.removeEventListener('hashchange', panel._mcpsTabHashHandler);
      panel._mcpsTabHashHandler = null;
    }

    if (!allSources || allSources.length === 0) {
      _renderEmptyState(panel);
      return;
    }

    // Determine which source-id (if any) to open the per-attachment editor for.
    // Priority: pendingSourceId from hydrate > parsed from current hash.
    var selectedSourceId = pendingSourceId || _parseSourceIdFromHash();

    if (selectedSourceId) {
      _renderPerAttachmentEditor(panel, agent, allSources, selectedSourceId,
        fetchMcpSourceTools, onChange, onSelectedSourceChange);
    } else {
      _renderChipList(panel, agent, allSources, fetchMcpSourceTools, onChange, onSelectedSourceChange);
    }

    // Hash-change listener: re-renders when operator navigates via browser
    // back/forward within the area. Removed when panel is garbage-collected
    // or next renderMcpsTab call cleans it up. Panel must still be in DOM
    // for re-render to be meaningful; innerHTML='' on a detached panel is
    // harmless (acceptable lifecycle per existing agent-editor pattern).
    function onHashChange() {
      renderMcpsTab(panel, agent, allSources, {
        fetchMcpSourceTools: fetchMcpSourceTools,
        onChange: onChange,
        onSelectedSourceChange: onSelectedSourceChange
        // pendingSourceId intentionally NOT forwarded: hashchange re-parse
        // reads the live URL fragment instead.
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

  // ── Chip-list view ────────────────────────────────────────────────────────
  //
  // DOM structure:
  //   - .chip-area[data-type="mcp"] (HIDDEN) — the semantics sink for
  //     collectFormData. Only ATTACHED source chips live here. Each chip:
  //     <div class="chip" data-id="{source.id}">. These are invisible to the
  //     operator; the visual chip-list below is the UI surface.
  //   - .mcp-attach-chip-list — visual chip list; shows ALL sources with
  //     attach/detach toggle semantics. Chips here do NOT carry data-id in
  //     the collectFormData-recognized container.
  //
  // When operator clicks an unattached chip → add a hidden chip to chip-area
  // (and add chip-attached class to the visual chip) → onChange fires.
  // When operator clicks an attached chip → open per-attachment editor.

  function _renderChipList(panel, agent, allSources, fetchMcpSourceTools, onChange, onSelectedSourceChange) {
    var attachedIds = _attachedSourceIds(agent);

    var header = document.createElement('p');
    header.className = 'mcp-chip-list-header';
    header.textContent = 'Click a source to attach it. Click an attached source to open its settings.';
    panel.appendChild(header);

    // Hidden chip-area — picked up by studio.js::collectFormData.
    // Contains only attached-source chips.
    var chipArea = document.createElement('div');
    chipArea.className = 'chip-area';
    chipArea.setAttribute('data-type', 'mcp');
    chipArea.setAttribute('data-testid', 'mcp-chip-area');
    chipArea.style.display = 'none';
    panel.appendChild(chipArea);

    // Pre-populate hidden chip-area with already-attached sources.
    var localAttached = {};  // tracks current UI state (may differ from server)
    for (var id in attachedIds) {
      if (attachedIds.hasOwnProperty(id)) {
        localAttached[id] = true;
        var hc = document.createElement('div');
        hc.className = 'chip';
        hc.setAttribute('data-id', id);
        chipArea.appendChild(hc);
      }
    }

    // Visual chip list.
    var visualList = document.createElement('div');
    visualList.className = 'mcp-attach-chip-list';
    visualList.setAttribute('data-testid', 'mcp-visual-chip-list');
    panel.appendChild(visualList);

    for (var i = 0; i < allSources.length; i++) {
      (function (source) {
        var isAttached = localAttached[source.id] === true;

        var chip = document.createElement('div');
        chip.className = 'chip' + (isAttached ? ' chip-attached' : '');
        chip.setAttribute('data-source-id', source.id);
        chip.setAttribute('data-testid', 'mcp-chip-' + source.id);
        chip.setAttribute('role', 'button');
        chip.setAttribute('tabindex', '0');
        chip.setAttribute('aria-pressed', isAttached ? 'true' : 'false');

        var nameSpan = document.createElement('span');
        nameSpan.className = 'chip-name';
        nameSpan.textContent = source.name;
        chip.appendChild(nameSpan);

        var badge = document.createElement('span');
        badge.className = 'chip-transport-badge';
        badge.textContent = source.type === 'stdio' ? 'stdio' : 'http';
        chip.appendChild(badge);

        chip.addEventListener('click', function () {
          var nowAttached = chip.classList.contains('chip-attached');
          if (nowAttached) {
            // Already attached → open per-attachment editor.
            onSelectedSourceChange(source.id);
            _renderPerAttachmentEditor(panel, agent, allSources, source.id,
              fetchMcpSourceTools, onChange, onSelectedSourceChange);
          } else {
            // Not yet attached → attach.
            chip.classList.add('chip-attached');
            chip.setAttribute('aria-pressed', 'true');
            localAttached[source.id] = true;
            // Add to hidden chip-area so collectFormData picks it up.
            var hiddenChip = document.createElement('div');
            hiddenChip.className = 'chip';
            hiddenChip.setAttribute('data-id', source.id);
            hiddenChip.setAttribute('data-hidden-for', source.id);
            chipArea.appendChild(hiddenChip);
            if (onChange) onChange();
          }
        });

        chip.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            chip.click();
          }
        });

        visualList.appendChild(chip);
      })(allSources[i]);
    }
  }

  // ── Per-attachment editor ─────────────────────────────────────────────────

  function _renderPerAttachmentEditor(panel, agent, allSources, sourceId,
      fetchMcpSourceTools, onChange, onSelectedSourceChange) {
    var source = null;
    for (var i = 0; i < allSources.length; i++) {
      if (allSources[i].id === sourceId) { source = allSources[i]; break; }
    }

    panel.innerHTML = '';

    // Back-to-chip-list button.
    var backBtn = document.createElement('button');
    backBtn.type = 'button';
    backBtn.className = 'btn-outlined-cyan mcp-editor-back-btn';
    backBtn.setAttribute('data-testid', 'mcp-editor-back-btn');
    backBtn.textContent = '← Back to MCP sources';
    backBtn.addEventListener('click', function () {
      onSelectedSourceChange(null);
      _renderChipList(panel, agent, allSources, fetchMcpSourceTools, onChange, onSelectedSourceChange);
    });
    panel.appendChild(backBtn);

    // Unknown source guard — edge case from L3 Edge Cases.
    if (!source) {
      var errDiv = document.createElement('div');
      errDiv.className = 'mcp-auth-required-notice';
      errDiv.setAttribute('data-testid', 'mcp-source-not-found');
      errDiv.textContent = 'Source not found. It may have been deleted.';
      panel.appendChild(errDiv);
      return;
    }

    // Header.
    var headerDiv = document.createElement('div');
    headerDiv.className = 'mcp-attachment-editor';
    headerDiv.setAttribute('data-testid', 'mcp-attachment-editor');

    var titleEl = document.createElement('h3');
    titleEl.className = 'mcp-editor-title';
    titleEl.textContent = source.name;
    var transportBadge = document.createElement('span');
    transportBadge.className = 'chip-transport-badge';
    transportBadge.textContent = source.type === 'stdio' ? ' (stdio)' : ' (http)';
    titleEl.appendChild(transportBadge);
    headerDiv.appendChild(titleEl);

    // Ensure the chip exists in the chip-area (even though it's not visible)
    // so collectFormData picks it up as attached. We embed a hidden chip-area
    // that mirrors the attached state when the editor is open.
    var hiddenChipArea = document.createElement('div');
    hiddenChipArea.className = 'chip-area';
    hiddenChipArea.setAttribute('data-type', 'mcp');
    hiddenChipArea.style.display = 'none';
    var attachedIds = _attachedSourceIds(agent);
    // Always include the currently-editing source as attached (operator
    // navigated here via chip click which attaches on click).
    var allAttachedIds = Object.keys(attachedIds);
    if (allAttachedIds.indexOf(sourceId) === -1) allAttachedIds.push(sourceId);
    for (var j = 0; j < allAttachedIds.length; j++) {
      var hiddenChip = document.createElement('div');
      hiddenChip.className = 'chip';
      hiddenChip.setAttribute('data-id', allAttachedIds[j]);
      hiddenChipArea.appendChild(hiddenChip);
    }
    headerDiv.appendChild(hiddenChipArea);

    panel.appendChild(headerDiv);

    // ── Tools section ─────────────────────────────────────────────────────

    var toolsSection = document.createElement('div');
    toolsSection.className = 'mcp-editor-section';
    var toolsLabel = document.createElement('h4');
    toolsLabel.textContent = 'Tools';
    toolsSection.appendChild(toolsLabel);

    var refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'btn-outlined-cyan mcp-refresh-tools-btn';
    refreshBtn.setAttribute('data-testid', 'mcp-refresh-tools-btn');
    refreshBtn.textContent = 'Refresh tools';
    toolsSection.appendChild(refreshBtn);

    var toolsBody = document.createElement('div');
    toolsBody.className = 'mcp-tools-body';
    toolsBody.setAttribute('data-testid', 'mcp-tools-body');
    toolsBody.textContent = 'Loading tools…';
    toolsSection.appendChild(toolsBody);

    panel.appendChild(toolsSection);

    function loadTools(forceRefresh) {
      toolsBody.textContent = 'Loading tools…';
      if (!fetchMcpSourceTools) {
        toolsBody.textContent = 'Tool discovery not available.';
        return;
      }
      fetchMcpSourceTools(sourceId, { forceRefresh: !!forceRefresh }).then(function (data) {
        _renderToolsCheckboxGroup(toolsBody, source, agent, data.tools || [], onChange);
      }).catch(function (err) {
        if (err && err.name === 'AuthRequired') {
          _renderAuthRequiredNotice(toolsBody, sourceId);
        } else {
          toolsBody.innerHTML = '';
          var errEl = document.createElement('div');
          errEl.className = 'mcp-tools-error';
          errEl.setAttribute('data-testid', 'mcp-tools-error');
          errEl.textContent = 'Error loading tools: ' + (err && err.message ? err.message : String(err));
          toolsBody.appendChild(errEl);
        }
      });
    }

    refreshBtn.addEventListener('click', function () { loadTools(true); });

    // ── Credential overrides section ──────────────────────────────────────

    var overridesSection = document.createElement('div');
    overridesSection.className = 'mcp-editor-section';
    overridesSection.setAttribute('data-mcp-override-source', source.name);
    var overridesLabel = document.createElement('h4');
    overridesLabel.textContent = 'Credential overrides';
    overridesSection.appendChild(overridesLabel);

    var helpers = window.App.adminFormHelpers;
    var schema = MCP_OVERRIDE_SCHEMAS[source.type] || {};
    var agentOverride = ((agent && agent.mcp_overrides) || {})[source.name] || {};
    var fieldNames = Object.keys(schema);

    if (fieldNames.length === 0) {
      var noFields = document.createElement('p');
      noFields.className = 'empty-state';
      noFields.textContent = 'No credential overrides available for this source type.';
      overridesSection.appendChild(noFields);
    } else if (!helpers) {
      var noHelpers = document.createElement('p');
      noHelpers.className = 'mcp-tools-error';
      noHelpers.textContent = 'Form helpers not loaded. Cannot render override fields.';
      overridesSection.appendChild(noHelpers);
    } else {
      var overrideHtml = '';
      for (var fi = 0; fi < fieldNames.length; fi++) {
        var fname = fieldNames[fi];
        var prop = schema[fname];
        var agentVal = (fname in agentOverride) ? agentOverride[fname] : null;
        // Substitute fields: start blank if agent has no value; preserve
        // __MASKED__ if the backend returned it.
        if (agentVal === null && prop.x_marker === 'Substitute') {
          agentVal = '';
        }
        // renderField emits data-tool-override-tool too (hardcoded at
        // tools-form-helpers.js:127-129), but collectFormData's tool_overrides
        // walk requires BOTH data-tool-override-tool AND data-tool-override-field;
        // our attrPrefix='data-mcp-override-field' means the latter attribute is
        // absent for tool_overrides, so no collision. See L3 context note.
        overrideHtml += helpers.renderField(fname, prop, agentVal, {
          mode: 'agent',
          operatorValue: null,
          attrPrefix: 'data-mcp-override-field',
          toolName: source.name
        });
      }
      var overrideContainer = document.createElement('div');
      overrideContainer.innerHTML = overrideHtml;
      // Stamp data-mcp-override-source on every element that has
      // data-mcp-override-field. studio.js::collectFormData requires BOTH
      // attributes on the SAME element (parallel to how tool_overrides uses
      // data-tool-override-tool + data-tool-override-field on the same input).
      // helpers.renderField puts data-mcp-override-field on inputs but has no
      // mechanism to add an arbitrary second attribute; we stamp it here.
      var fieldEls = overrideContainer.querySelectorAll('[data-mcp-override-field]');
      for (var fe = 0; fe < fieldEls.length; fe++) {
        fieldEls[fe].setAttribute('data-mcp-override-source', source.name);
      }
      overridesSection.appendChild(overrideContainer);

      // Wire chip-list editors (dict fields use chip-list-editor widget).
      var chipEditors = overrideContainer.querySelectorAll('.chip-list-editor');
      for (var ce = 0; ce < chipEditors.length; ce++) {
        helpers.wireChipListEditor(chipEditors[ce], {
          onChange: function () { if (onChange) onChange(); }
        });
      }

      // Wire input/change events on override fields. These fields are added
      // to the DOM AFTER studio.js::wireEditorEvents has already run, so we
      // must manually attach listeners here. studio.js's wireEditorEvents
      // wires .field-input/.field-select/.field-textarea elements that exist
      // at editor-mount time; override fields appear later on chip click.
      var overrideInputs = overrideContainer.querySelectorAll(
        '.field-input, .field-textarea, .field-select'
      );
      for (var oi = 0; oi < overrideInputs.length; oi++) {
        overrideInputs[oi].addEventListener('input', function () { if (onChange) onChange(); });
        overrideInputs[oi].addEventListener('change', function () { if (onChange) onChange(); });
      }
    }

    panel.appendChild(overridesSection);

    // Kick off tools load.
    loadTools(false);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _renderToolsCheckboxGroup(container, source, agent, tools, onChange) {
    container.innerHTML = '';

    if (!tools || tools.length === 0) {
      var noTools = document.createElement('p');
      noTools.className = 'empty-state';
      noTools.setAttribute('data-testid', 'mcp-no-tools-msg');
      noTools.textContent = 'No tools available for this source.';
      container.appendChild(noTools);
      return;
    }

    // Determine mode: allowlist vs denylist (see L3.7 spec).
    var overrides = ((agent && agent.mcp_overrides) || {})[source.name] || {};
    var existingEnabled = overrides.enabled_tools;
    var existingDisabled = overrides.disabled_tools || [];
    var isAllowlist = Array.isArray(existingEnabled) && existingEnabled !== null;
    var mode = isAllowlist ? 'allowlist' : 'denylist';

    var group = document.createElement('div');
    group.className = 'mcp-tools-checkbox-group';
    group.setAttribute('data-mcp-tool-group', '');
    group.setAttribute('data-mcp-tool-mode', mode);
    group.setAttribute('data-testid', 'mcp-tools-checkbox-group');

    for (var i = 0; i < tools.length; i++) {
      (function (tool) {
        var toolName = tool.name;
        var prefixedName = 'mcp__' + _slugify(source.name) + '__' + toolName;

        var isChecked;
        if (isAllowlist) {
          isChecked = existingEnabled.indexOf(toolName) !== -1;
        } else {
          isChecked = existingDisabled.indexOf(toolName) === -1;
        }

        var label = document.createElement('label');
        label.className = 'mcp-tool-toggle-label';

        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = isChecked;
        checkbox.setAttribute('data-mcp-tool-toggle', toolName);
        checkbox.setAttribute('data-mcp-source', source.name);
        checkbox.setAttribute('data-testid', 'mcp-tool-toggle-' + toolName);
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
    notice.setAttribute('data-testid', 'mcp-auth-required-notice');
    notice.textContent = 'This source needs Test/auth on the source-edit page first. ';
    var link = document.createElement('a');
    link.href = '#studio/mcp-sources/' + encodeURIComponent(sourceId);
    link.textContent = 'Go to source settings';
    link.setAttribute('data-testid', 'mcp-auth-required-link');
    notice.appendChild(link);
    container.appendChild(notice);
  }

  function _attachedSourceIds(agent) {
    var ids = {};
    if (!agent) return ids;
    var sourceIds = agent.mcp_source_ids || [];
    for (var i = 0; i < sourceIds.length; i++) {
      ids[sourceIds[i]] = true;
    }
    return ids;
  }

  function _parseSourceIdFromHash() {
    // Parse source-id from `#studio/agents/{name}/mcps/{source-id}` if present.
    var hash = window.location.hash;
    // Strip leading '#'.
    if (hash.charAt(0) === '#') hash = hash.slice(1);
    // Expected shape: studio/agents/{name}/mcps/{source-id}
    var mcpsIdx = hash.indexOf('/mcps/');
    if (mcpsIdx === -1) return null;
    var afterMcps = hash.slice(mcpsIdx + '/mcps/'.length);
    if (!afterMcps) return null;
    // Defensive: strip trailing slashes.
    if (afterMcps.charAt(afterMcps.length - 1) === '/') {
      afterMcps = afterMcps.slice(0, -1);
    }
    return afterMcps ? decodeURIComponent(afterMcps) : null;
  }

  // Convert a source name to a slug suitable for the MCP tool prefix
  // (mcp__{slug}__{tool}). Mirrors the server-side slugification used by
  // _tool.py. Keep in sync if the server-side logic changes.
  function _slugify(name) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  }

  window.App.studio.renderMcpsTab = renderMcpsTab;
})();
