App.registerArea({
  id: 'studio',
  label: 'Agent Studio',
  icon: App.icons.studio,
  order: 20,
  sidebarLabel: 'Agent list',

  // ── Hash-routing serialize/hydrate ──────────────────────────────────
  //
  // serializeState branch order (explicit):
  //   1. _activeSection === 'knowledge' → 'knowledge'
  //   2. _activeSection === 'mcp-sources' → 'mcp-sources' | 'mcp-sources/new'
  //      | 'mcp-sources/<id>' (post-F2 retrofit; relocated from admin)
  //   3. _activeSection === 'agents' && agent selected && !createMode →
  //      'agents/<encoded-name>/<tab>'   (F5 leg 03 — appended /{tab})
  //   4. otherwise (no agent OR createMode) → 'agents'
  //
  // F5 leg 03 extends branch 3 by appending the active tab segment so the
  // URL reflects the editor's tab state. Defaults to 'general'. The F3
  // router's serialize-after-hydrate path performs the
  // #studio/agents/{name} → #studio/agents/{name}/general upgrade for free
  // (no new redirect logic in studio.js).
  serializeState: function () {
    if (this._activeSection === 'knowledge') return 'knowledge';
    if (this._activeSection === 'mcp-sources') {
      if (this._mcpSourceFormMode === 'add') return 'mcp-sources/new';
      if (this._mcpSourceFormMode === 'edit' && this._editingMcpSource) {
        return 'mcp-sources/' + encodeURIComponent(this._editingMcpSource.id);
      }
      // Hydrate-vs-fetch race: pending id known but source not yet loaded.
      if (this._pendingMcpSourceFormMode === 'add') return 'mcp-sources/new';
      if (this._pendingMcpSourceId) {
        return 'mcp-sources/' + encodeURIComponent(this._pendingMcpSourceId);
      }
      return 'mcp-sources';
    }
    if (this._activeSection === 'connectors') {
      // M11 F11 L2: vocabulary unified — both hash route slug and internal
      // _activeSection key are 'connectors' (the F5 L8 HAT operator-facing
      // slug + legacy substrate-name fallback retired alongside the v23
      // table rename). Symmetry with mcp-sources preserved.
      if (this._connectorFormMode === 'add') return 'connectors/new';
      if (this._connectorFormMode === 'edit' && this._editingConnector) {
        return 'connectors/' + encodeURIComponent(this._editingConnector.id);
      }
      // Hydrate-vs-fetch race: pending id known but account not yet loaded.
      if (this._pendingConnectorFormMode === 'add') return 'connectors/new';
      if (this._pendingConnectorId) {
        return 'connectors/' + encodeURIComponent(this._pendingConnectorId);
      }
      return 'connectors';
    }
    if (this._activeSection === 'agents' && this._selectedAgent && !this._createMode) {
      var base = 'agents/' + encodeURIComponent(this._selectedAgent.name) +
        '/' + (this._activeTab || 'general');
      // F8 L3 Patch B — when on the MCPs tab AND a source-id is selected,
      // append it so refresh preserves the per-attachment editor view.
      if (this._activeTab === 'mcps' && this._selectedMcpAgentSourceId) {
        return base + '/' + encodeURIComponent(this._selectedMcpAgentSourceId);
      }
      return base;
    }
    // Hydrate-before-loadAll race: when the user lands on
    // #studio/agents/{name}/{tab} but agents fetch hasn't completed,
    // _selectedAgent is null even though we already know the target.
    // Without this branch, the F3 router's serialize-after-hydrate would
    // clobber the URL to #studio/agents before tryConsumePendingSelect
    // resolves. Returning the deep form keeps the URL stable.
    if (this._activeSection === 'agents' && this._pendingSelectName) {
      return 'agents/' + encodeURIComponent(this._pendingSelectName) +
        '/' + (this._activeTab || 'general');
    }
    return 'agents';
  },

  // hydrateState parses sub and updates the area's _activeSection + pending
  // agent selection state. After hydrate returns, the F3 router at
  // app.js:179-185 calls serializeState and writes URL via replaceState if
  // serialized !== sub (idempotent). Therefore hydrate MUST NOT call
  // _writeUrl itself — pass {writeUrl: false} when calling setActiveSection.
  //
  // F5 leg 03: extended to parse 'agents/<name>/<tab>'. Four cases:
  //   - 'agents/{name}'         → activeTab='general' (router rewrites URL)
  //   - 'agents/{name}/'        → activeTab='general' (defensive trailing-slash)
  //   - 'agents/{name}/general|knowledge|mcps|tools' → use that tab
  //   - 'agents/{name}/<other>' → defensively default to 'general'
  // Encoding note: agent names with literal '/' are encoded as '%2F' by
  // encodeURIComponent, so rest.indexOf('/') unambiguously finds the segment
  // separator.
  hydrateState: function (sub) {
    var section = 'agents';
    var pending = null;
    var pendingTab = 'general';
    var pendingMcpSourceId_local = null;
    var pendingMcpSourceFormMode_local = null;
    var pendingConnectorId_local = null;
    var pendingConnectorFormMode_local = null;
    if (sub === 'knowledge') {
      section = 'knowledge';
    } else if (sub === 'mcp-sources') {
      section = 'mcp-sources';
    } else if (sub === 'mcp-sources/new') {
      section = 'mcp-sources';
      pendingMcpSourceFormMode_local = 'add';
    } else if (sub && sub.indexOf('mcp-sources/') === 0) {
      // Direct-load on mcp-sources/{id}: parse the source id so the editor
      // opens on refresh. Mirrors admin.js's L5 parsing pattern (now
      // relocated to studio post-F2 retrofit).
      section = 'mcp-sources';
      pendingMcpSourceFormMode_local = 'edit';
      var mrest = sub.slice('mcp-sources/'.length);
      if (mrest.charAt(mrest.length - 1) === '/') mrest = mrest.slice(0, -1);
      // Defensive: if extra path segments, take only the first.
      var mslashIdx = mrest.indexOf('/');
      if (mslashIdx !== -1) mrest = mrest.slice(0, mslashIdx);
      pendingMcpSourceId_local = mrest ? decodeURIComponent(mrest) : null;
    } else if (sub === 'connectors') {
      // M11 F11 L2: vocabulary unified — only the 'connectors' slug is
      // accepted (the F5 L8 HAT legacy substrate-name slug retired
      // alongside the URL rename). The router's serialize-after-hydrate
      // pass will rewrite the URL to 'connectors'.
      section = 'connectors';
    } else if (sub === 'connectors/new') {
      section = 'connectors';
      pendingConnectorFormMode_local = 'add';
    } else if (sub && sub.indexOf('connectors/') === 0) {
      // Direct-load on connectors/{id}: parse the connector id so the
      // editor opens on refresh. Mirrors the mcp-sources parsing pattern
      // above.
      section = 'connectors';
      pendingConnectorFormMode_local = 'edit';
      var crestPrefix = 'connectors/';
      var crest = sub.slice(crestPrefix.length);
      if (crest.charAt(crest.length - 1) === '/') crest = crest.slice(0, -1);
      // Defensive: if extra path segments, take only the first.
      var cslashIdx = crest.indexOf('/');
      if (cslashIdx !== -1) crest = crest.slice(0, cslashIdx);
      pendingConnectorId_local = crest ? decodeURIComponent(crest) : null;
    } else if (sub && sub.indexOf('agents/') === 0) {
      section = 'agents';
      var rest = sub.slice('agents/'.length);
      var slashIdx = rest.indexOf('/');
      if (slashIdx === -1) {
        pending = decodeURIComponent(rest);
        pendingTab = 'general';
      } else if (slashIdx === rest.length - 1) {
        // Trailing-slash defensive — treat as no-tab.
        pending = decodeURIComponent(rest.slice(0, slashIdx));
        pendingTab = 'general';
      } else {
        pending = decodeURIComponent(rest.slice(0, slashIdx));
        var tab = rest.slice(slashIdx + 1);
        // F8 L3 Patch A — split deeper "mcps/{source-id}" BEFORE the
        // four-tab whitelist check. Without this, the whitelist would
        // reject "mcps/some-uuid" and default to "general", breaking
        // deep-link navigation (AC L3.6 + Browser Test 6).
        var pendingMcpAgentSourceId = null;
        if (tab.indexOf('mcps/') === 0) {
          pendingMcpAgentSourceId = decodeURIComponent(tab.slice('mcps/'.length));
          tab = 'mcps';
        }
        if (tab === 'general' || tab === 'knowledge' || tab === 'mcps' || tab === 'connectors' || tab === 'tools') {
          pendingTab = tab;
        } else {
          pendingTab = 'general';
        }
        this._pendingMcpAgentSourceId = pendingMcpAgentSourceId;  // consumed by renderMcpsTab
      }
    } else if (sub === 'agents' || !sub) {
      section = 'agents';
      // F4 L7 (M08): bare URL (#studio or #studio/agents) means "show the
      // grid" — clear any stale editor state from a prior navigation
      // within the same area lifecycle. Without this, returning from
      // another area (e.g. #chat) while Studio's last sub was an agent
      // detail leaves the editor mounted even when the URL is bare.
      this._selectedAgent = null;
      this._createMode = false;
    } else {
      // Defensive: unrecognized sub defaults to 'agents'. Do NOT throw.
      section = 'agents';
    }
    this._activeSection = section;
    this._activeTab = pendingTab;
    if (pending) {
      this._pendingSelectName = pending;
      this._pendingTabName = pendingTab;
      if (this._tryConsumePendingSelect) this._tryConsumePendingSelect();
    } else if (section !== 'agents') {
      this._pendingSelectName = null;
      this._pendingTabName = null;
    }
    // Always overwrite pending MCP state (including with nulls when sub is
    // not mcp-sources/...) so navigation away clears stale pending.
    this._pendingMcpSourceId = pendingMcpSourceId_local;
    this._pendingMcpSourceFormMode = pendingMcpSourceFormMode_local;
    // Same for connectors.
    this._pendingConnectorId = pendingConnectorId_local;
    this._pendingConnectorFormMode = pendingConnectorFormMode_local;
    if (this._setActiveSection) {
      this._setActiveSection(section, { writeUrl: false });
    }
    // Within-mcp-sources sub-navigation (e.g. mcp-sources → mcp-sources/new)
    // doesn't change _activeSection, so _setActiveSection's renderContent
    // path won't re-enter the editor branch. Fire consume unconditionally
    // so within-section direct-loads open the editor.
    if (this._tryConsumePendingMcpSource) this._tryConsumePendingMcpSource();
    if (this._tryConsumePendingConnector) this._tryConsumePendingConnector();
  },

  init: function (sidebar, content) {
    var self = this;

    // ── Per-instance state (promoted from closure locals to this.* so
    //    serializeState reads the right values) ────────────────────────────
    self._agents = [];
    self._allTools = [];
    self._allMcpSources = [];
    // M10 F6 L5 — all connector accounts cache for the agent-editor
    // Connectors tab. Mirrors _allMcpSources: lazy initial list from
    // loadAll, refreshed on every agent-edit mount via
    // refreshConnectorsCache (mirror of refreshMcpSourcesCache).
    self._allConnectors = [];
    self._allKnowledgeBases = [];
    self._allProviders = [];
    self._selectedAgent = null;
    self._pendingSelectName = self._pendingSelectName || null;
    self._pendingTabName = self._pendingTabName || null;
    self._createMode = false;
    self._activeSection = self._activeSection || 'agents';
    self._activeTab = self._activeTab || 'general';
    // F8 L3 Patch C — selected source-id within the agent MCPs tab.
    // Written by renderMcpsTab when a chip is clicked or a deep-link hydrates.
    // Read by serializeState to append /{source-id} to the URL.
    self._selectedMcpAgentSourceId = null;
    var dirty = false;
    var snapshot = '';
    // Tab handle returned by App.studio.renderAgentEditor — used for
    // imperative activate(tabId) calls after hydrate.
    var tabHandle = null;

    // ── MCP Sources state (post-F2 retrofit; relocated from admin.js) ───
    // The MCP Servers section was originally an admin.js sub-section
    // (M07 F1 L5/L6); moved here post-F2 retrofit because MCP sources are
    // user-managed entities, not system settings. State shape mirrors the
    // admin pattern: type list cached at init, source list lazily fetched
    // on section render, formMode + editingMcpSource drive grid-vs-editor
    // dispatch, pending* slots handle the hydrate-vs-fetch race.
    //
    // formMode + editingMcpSource + pending* are exposed via Object
    // .defineProperty getter/setters so serializeState (called from outside
    // init) can read them. Mirrors admin.js's exposure pattern. The
    // closure-local `var`s remain the single source of truth.
    var MCP_TYPES = [];
    var mcpTypesReady = null;
    var mcpSources = null; // null until first fetch resolves
    var mcpSourceFormMode = null; // null | 'add' | 'edit'
    var editingMcpSource = null;
    var pendingMcpSourceId = self._pendingMcpSourceId || null;
    var pendingMcpSourceFormMode = self._pendingMcpSourceFormMode || null;
    Object.defineProperty(self, '_mcpSourceFormMode', {
      get: function () { return mcpSourceFormMode; },
      set: function (v) { mcpSourceFormMode = v; },
      configurable: true
    });
    Object.defineProperty(self, '_editingMcpSource', {
      get: function () { return editingMcpSource; },
      set: function (v) { editingMcpSource = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingMcpSourceId', {
      get: function () { return pendingMcpSourceId; },
      set: function (v) { pendingMcpSourceId = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingMcpSourceFormMode', {
      get: function () { return pendingMcpSourceFormMode; },
      set: function (v) { pendingMcpSourceFormMode = v; },
      configurable: true
    });

    // ── Connector Accounts state (M10 F2 leg 05) ─────────────────────────
    // Parallel to the MCP Sources block above. The Connector Accounts
    // section is structurally identical to MCP Sources (operator-managed
    // entities, many-to-many identities, per-type config — see flight's
    // "Studio placement, not Admin" design decision). State shape mirrors
    // the MCP pattern: type list cached at init, account list lazily
    // fetched on section render, formMode + editingConnector drive
    // grid-vs-editor dispatch, pending* slots handle the hydrate-vs-fetch
    // race.
    var CONNECTOR_TYPES = [];
    var connectorTypesReady = null;
    var connectors = null; // null until first fetch resolves
    var connectorFormMode = null; // null | 'add' | 'edit'
    var editingConnector = null;
    var pendingConnectorId = self._pendingConnectorId || null;
    var pendingConnectorFormMode = self._pendingConnectorFormMode || null;
    Object.defineProperty(self, '_connectorFormMode', {
      get: function () { return connectorFormMode; },
      set: function (v) { connectorFormMode = v; },
      configurable: true
    });
    Object.defineProperty(self, '_editingConnector', {
      get: function () { return editingConnector; },
      set: function (v) { editingConnector = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingConnectorId', {
      get: function () { return pendingConnectorId; },
      set: function (v) { pendingConnectorId = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingConnectorFormMode', {
      get: function () { return pendingConnectorFormMode; },
      set: function (v) { pendingConnectorFormMode = v; },
      configurable: true
    });

    // ── beforeunload listener (F5 leg 04) ────────────────────────────────
    //
    // Registered ONCE at init() time (init runs once per area lifetime,
    // gated by app.js's initialized[areaId] check). The closure `dirty` flag
    // is the sole gate — when in another area, dirty is false because the
    // editor isn't mounted; when in studio with unsaved changes, dirty is
    // true and the listener calls e.preventDefault(); e.returnValue = ''.
    //
    // **Do NOT remove on deactivate()** — deactivate runs on every cross-area
    // transition, so removing there would silently break tab-close
    // protection after a chat → studio → chat round-trip. The closure-flag
    // gate handles all cases.
    //
    // Modern browsers ignore the custom returnValue string and show a
    // generic "Leave site?" dialog; setting returnValue = '' is the modern
    // incantation that triggers the prompt.
    window.addEventListener('beforeunload', function (e) {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    });

    // ── connector-agent-detached listener (M11 F9 L5) ────────────────────
    //
    // Listens for the CustomEvent dispatched by the connector account
    // editor's per-row detach handler. When the Connectors grid is the
    // active studio section, re-fetch the list so the agent-count badge
    // refreshes immediately (the badge value comes from the
    // ``attached_agents_count`` field on the GET /api/connectors
    // response).
    //
    // Registered ONCE at init() time (init runs once per area lifetime,
    // gated by app.js's initialized[areaId] check) — mirrors the
    // ``connectors-tab.js:73`` precedent for ``connector-
    // always-listen-changed``. No teardown: handler is a guarded no-op
    // when the operator is on any section other than the Connectors
    // grid.
    //
    // TODO(routine-maintenance): F4 R13 studio-event-bus lift candidate;
    // M11 F9 L6 will refactor this inline listener (and the matching
    // dispatch in ``connector-editor.js``) into the shared bus.
    App.studio.eventBus.on('connector-agent-detached', function () {
      // Bail when the operator is not on the Connectors grid section —
      // ``fetchConnectors_`` itself stale-guards on
      // ``self._activeSection`` so a late-arriving fetch is safe, but
      // shortcutting here avoids the network round-trip entirely.
      if (self._activeSection !== 'connectors') return;
      // ``fetchConnectors_`` is a function declaration in this
      // same closure (hoisted) so this reference is well-defined even
      // though the function appears later in the file.
      fetchConnectors_();
    });

    var TOOL_CATEGORIES = {
      'Filesystem': ['read_file', 'write_file', 'edit_file', 'delete_file', 'move_file', 'mkdir', 'glob', 'grep', 'list_dir'],
      'Execution': ['shell', 'python_exec', 'shell_session_start', 'shell_session_send', 'shell_session_close', 'shell_session_list'],
      'Web': ['download_file', 'fetch_url', 'http_request', 'web_search']
    };

    // ── Layout: sidebar = section-nav only; main panel hosts both the
    // section-content (tile grid / Knowledge / Tools) and the editor,
    // toggled via .is-hidden based on whether an agent is being edited.
    // F2 Leg 2 (A.10): use <nav> instead of <div> so the section-nav
    // composes as a landmark. See section-nav.js helper change.
    sidebar.innerHTML = '<nav class="studio-section-nav"></nav>';
    var sectionNavEl = sidebar.querySelector('.studio-section-nav');

    content.innerHTML =
      '<div class="studio-section-content"></div>' +
      '<div class="studio-editor"></div>';
    var sectionContentEl = content.querySelector('.studio-section-content');
    var editorEl = content.querySelector('.studio-editor');

    var agentsContentEl = document.createElement('div');
    agentsContentEl.className = 'studio-agents-content';
    agentsContentEl.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">Agents</h1>' +
        // Header CTA renders icon-only at rest; expands on hover. CSS hides
        // it entirely when the grid below is empty, deferring the affordance
        // to the empty-canvas's centered CTA (rendered by renderAgentList).
        '<button class="new-entity-btn" type="button" data-testid="new-agent-btn" aria-label="New agent">' +
          App.icon('square-pen') + '<span>New Agent</span>' +
        '</button>' +
      '</div>' +
      '<div class="entity-tile-grid" role="listbox" aria-label="Agents"></div>';
    var agentListEl = agentsContentEl.querySelector('.entity-tile-grid');
    var newAgentBtn = agentsContentEl.querySelector('.new-entity-btn');

    // ── Section navigation ─────────────────────────────────────────────

    App.layout.renderSectionNav(sectionNavEl, [
      { id: 'agents', label: 'Agents' },
      { id: 'knowledge', label: 'Knowledge' },
      // Post-F2 retrofit: replaced 'Tools' stub (id: 'tools') with the
      // real MCP Servers section (id: 'mcp-sources'). The URL slug uses
      // 'mcp-sources' (matches the /api/mcp-sources REST path) while the
      // user-facing label uses "MCP Servers" (mirrors the storage entity
      // vs. UI label asymmetry from M07 F1).
      { id: 'mcp-sources', label: 'MCP Servers' },
      // M10 F2 leg 05: Connector Accounts section. Operator-managed
      // identities (Discord bots, Slack workspace apps, etc.); structural
      // match to MCP sources. Internal section id is 'connectors'
      // (matches the F2 entity contract — /api/connectors REST
      // path, Connector entity name). F5 L8 HAT: the operator-facing
      // hash slug and label are "Connectors" (shorter, friendlier); the
      // entity-vs-label asymmetry mirrors MCP Servers vs. mcp-sources.
      { id: 'connectors', label: 'Connectors' }
    ], self._activeSection, {
      onSelect: function (section) {
        // F4 L5: delegate to _confirmLeaveImpl (single source of truth).
        // Mirrors admin.js's setCategory which also routes through
        // _confirmLeaveImpl. The empty-function abort is intentional:
        // same-area sidebar nav doesn't need to roll back state on cancel
        // (the dialog just closes; setActiveSection never fires).
        //
        // F4 L7 (M08): clicking the same section's nav item while an
        // editor is mounted should treat the click as "back to grid" —
        // clear editor state so updateContentVisibility shows the grid.
        // Without this, setActiveSection re-renders the grid behind a
        // still-mounted editor and the operator sees no change.
        var commit = function () {
          // Clear editor state of the OUTGOING section when leaving
          // (so re-entering lands on the grid, not the prior editor).
          // M10 F6 L7 HAT: prior logic only cleared state on
          // same-section reclicks, so Agents → Connectors → Agents
          // restored the previously-edited agent's editor (incl. tab).
          // Routing should land on the listing instead.
          var prev = self._activeSection;
          if (prev !== section) {
            if (prev === 'agents' && (self._selectedAgent || self._createMode)) {
              self._selectedAgent = null;
              self._createMode = false;
              dirty = false;
            } else if (prev === 'mcp-sources' && mcpSourceFormMode) {
              mcpSourceFormMode = null;
              editingMcpSource = null;
              dirty = false;
            } else if (prev === 'connectors' && connectorFormMode) {
              connectorFormMode = null;
              editingConnector = null;
              dirty = false;
            }
          } else {
            // Same-section reclick: treat as "back to grid".
            if (section === 'agents' && (self._selectedAgent || self._createMode)) {
              self._selectedAgent = null;
              self._createMode = false;
              dirty = false;
            } else if (section === 'mcp-sources' && mcpSourceFormMode) {
              mcpSourceFormMode = null;
              editingMcpSource = null;
              dirty = false;
            } else if (section === 'connectors' && connectorFormMode) {
              connectorFormMode = null;
              editingConnector = null;
              dirty = false;
            }
          }
          setActiveSection(section);
        };
        self._confirmLeaveImpl(commit, function () {});
      },
      // Sidebar header omitted — the topbar's area buttons already name the
      // active area (highlighted via aria-current="page"), so a duplicate
      // <h2> in the sidebar is redundant.
      ariaLabel: 'Agent Studio sections'
    });

    function renderAgentsSection() {
      sectionContentEl.innerHTML = '';
      sectionContentEl.appendChild(agentsContentEl);
      renderAgentList();
    }

    function renderKnowledgeSection() {
      sectionContentEl.innerHTML = '';
      App.studio.renderKnowledgeStub(sectionContentEl);
    }

    // MCP Servers section — relocated from admin (post-F2 retrofit). Mirrors
    // admin.js's renderMcpSourcesPanel: editor branch waits for type list
    // then delegates to App.studio.renderMcpSourceEditor; grid branch
    // delegates to App.studio.renderMcpServersGrid. The orchestrator-side
    // callbacks bridge dirty-state + navigation.
    function renderMcpSourcesSection() {
      sectionContentEl.innerHTML = '';
      // If a hash-route pending-create is queued (e.g. direct-load on
      // #studio/mcp-sources/new), promote it to mcpSourceFormMode='add'
      // BEFORE deciding grid vs editor so the editor mounts on first paint
      // (no transient grid flash). Pending-edit can't promote here because
      // the source needs to be in the cache; tryConsumePendingMcpSource
      // handles that path after fetchMcpSources_ resolves.
      if (!mcpSourceFormMode && self._pendingMcpSourceFormMode === 'add') {
        mcpSourceFormMode = 'add';
        editingMcpSource = null;
        self._pendingMcpSourceFormMode = null;
        self._pendingMcpSourceId = null;
      }
      if (mcpSourceFormMode) {
        // Reset orchestrator dirty mirror BEFORE editor mount (mirrors the
        // provider-editor pattern). Editor's onDirtyChange fires on first
        // user input.
        dirty = false;
        var ready = mcpTypesReady || fetchMcpSourceTypes();
        ready.then(function () {
          // Re-check formMode at resolution time — operator may have
          // navigated away mid-fetch.
          if (mcpSourceFormMode == null || self._activeSection !== 'mcp-sources') return;
          function doHandleBack() {
            mcpSourceFormMode = null;
            editingMcpSource = null;
            dirty = false;
            if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
            renderMcpSourcesSection();
          }
          App.studio.renderMcpSourceEditor(sectionContentEl, editingMcpSource, MCP_TYPES, {
            onBack: function () {
              if (dirty) {
                App.confirmDialog({ onConfirm: doHandleBack });
                return;
              }
              doHandleBack();
            },
            onCancel: function () {
              // Create-mode Cancel: navigate back to grid. Cancel-when-dirty
              // is intentional discard — no dialog gate. Edit-mode Cancel
              // reverts the form in-place and never reaches this callback.
              mcpSourceFormMode = null;
              editingMcpSource = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
              renderMcpSourcesSection();
            },
            onSaveSuccess: function (updated, isCreate) {
              editingMcpSource = updated;
              mcpSourceFormMode = 'edit';
              dirty = false;
              if (window.App && window.App.router) {
                App.router.replaceSub(self.serializeState());
              }
              if (isCreate) {
                // create→edit transition: re-render so Danger Zone +
                // edit-mode subtitle render with the newly-assigned id.
                renderMcpSourcesSection();
                // F9 L1 (vibing follow-up): auto-run Refresh on create.
                // For streamable-http sources the Refresh button mounts
                // post-render; clicking it programmatically kicks the
                // same code path as a manual click — Phase A connect
                // either succeeds (tools render) or surfaces
                // auth_required (consent-affordance UX, NO popup —
                // popup-blockers reject popups not triggered by direct
                // user gesture, and the gesture context from Save is
                // already lost).
                //
                // F9 L2 D1: stdio sources now also expose the Refresh
                // button (D1 ungated `mcp-test-connection` for stdio),
                // but auto-run remains streamable-http-only to preserve
                // L1's "manual click" flow as the canonical stdio entry
                // point per L2 Scenario 4. Operators who prefer auto-run
                // for stdio can drive it via the normal manual click.
                //
                // setTimeout(0) yields one frame so the editor's
                // wireEditorEvents finishes attaching the click handler
                // before we dispatch the synthetic click.
                setTimeout(function () {
                  if (updated && updated.type !== 'streamable-http') return;
                  var refreshBtn = sectionContentEl.querySelector(
                    '[data-testid="mcp-test-connection"]'
                  );
                  if (refreshBtn) {
                    // Signal to the editor's click handler that this is
                    // the auto-run-after-create path: on auth_required
                    // it must surface the consent button rather than
                    // open the popup directly (the Save click's
                    // user-gesture context is already lost).
                    refreshBtn.dataset.autoRun = '1';
                    refreshBtn.click();
                  }
                }, 0);
              }
            },
            onDeleteSuccess: function () {
              mcpSourceFormMode = null;
              editingMcpSource = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
              renderMcpSourcesSection();
            },
            onDirtyChange: function (d) { dirty = d; }
          });
        });
        return;
      }
      // Grid branch
      App.studio.renderMcpServersGrid(sectionContentEl, mcpSources, {
        selectedId: editingMcpSource ? editingMcpSource.id : null,
        onSelectMcpSource: selectMcpSource,
        onCreateMcpSource: enterCreateMcpSourceMode
      });
      fetchMcpSources_().then(function () {
        // F4 L5: stale-then guard — bail if user navigated away from
        // mcp-sources mid-fetch (mirrors fetchMcpSources_() internal guard).
        if (self._activeSection !== 'mcp-sources') return;
        // After fetch resolves, attempt to consume any pending hash-route
        // selection (e.g. direct-load on #studio/mcp-sources/{id}).
        tryConsumePendingMcpSource();
      });
    }

    function fetchMcpSourceTypes() {
      mcpTypesReady = fetch('/api/mcp-sources/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { MCP_TYPES = types; })
        .catch(function () { MCP_TYPES = []; });
      return mcpTypesReady;
    }

    // Distinct from the existing Promise-only `fetchMcpSources()` (which is
    // consumed by loadAll for agent-editor MCP attach lookups). This wrapper
    // populates the section-local cache + triggers grid re-render.
    function fetchMcpSources_() {
      return fetch('/api/mcp-sources')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // Stale-then guard: bail if user navigated away mid-fetch.
          if (self._activeSection !== 'mcp-sources') return;
          mcpSources = data;
          populateMcpSourcesGrid();
        })
        .catch(function () {
          if (self._activeSection !== 'mcp-sources') return;
          var gridEl = sectionContentEl.querySelector('.entity-tile-grid');
          if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load MCP sources.</div>';
        });
    }

    function populateMcpSourcesGrid() {
      // Stale-then guard: bail when no longer on mcp-sources OR when the
      // editor is mounted (no grid in the DOM to populate).
      if (self._activeSection !== 'mcp-sources') return;
      if (mcpSourceFormMode) return;
      App.studio.renderMcpServersGrid(sectionContentEl, mcpSources, {
        selectedId: editingMcpSource ? editingMcpSource.id : null,
        onSelectMcpSource: selectMcpSource,
        onCreateMcpSource: enterCreateMcpSourceMode
      });
    }

    function selectMcpSource(id) {
      var source = findMcpSource(id);
      if (!source) return; // pending-id race; will be re-attempted after fetch
      mcpSourceFormMode = 'edit';
      editingMcpSource = source;
      pendingMcpSourceId = null;
      pendingMcpSourceFormMode = null;
      self._pendingMcpSourceId = null;
      self._pendingMcpSourceFormMode = null;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderMcpSourcesSection();
    }

    function enterCreateMcpSourceMode() {
      mcpSourceFormMode = 'add';
      editingMcpSource = null;
      pendingMcpSourceId = null;
      pendingMcpSourceFormMode = null;
      self._pendingMcpSourceId = null;
      self._pendingMcpSourceFormMode = null;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderMcpSourcesSection();
    }

    function findMcpSource(id) {
      if (!mcpSources) return null;
      for (var i = 0; i < mcpSources.length; i++) {
        if (mcpSources[i].id === id) return mcpSources[i];
      }
      return null;
    }

    function tryConsumePendingMcpSource() {
      // Pull pending state from instance properties — hydrateState may have
      // set them after init() already captured the closure-locals.
      var pid = self._pendingMcpSourceId;
      var pmode = self._pendingMcpSourceFormMode;
      if (!pid && !pmode) return;
      if (pmode === 'add') {
        mcpSourceFormMode = 'add';
        editingMcpSource = null;
        self._pendingMcpSourceId = null;
        self._pendingMcpSourceFormMode = null;
        renderMcpSourcesSection();
        return;
      }
      if (pmode === 'edit' && pid) {
        var found = findMcpSource(pid);
        if (found) {
          mcpSourceFormMode = 'edit';
          editingMcpSource = found;
          self._pendingMcpSourceId = null;
          self._pendingMcpSourceFormMode = null;
          renderMcpSourcesSection();
        }
        // else: not in cache; will retry after fetchMcpSources_ resolves.
      }
    }
    self._tryConsumePendingMcpSource = tryConsumePendingMcpSource;

    // ── Connector Accounts section (M10 F2 leg 05) ───────────────────────
    // Mirror of the MCP Sources block above. Connector accounts share the
    // same operator-managed-entity shape, so the routing/render machinery
    // is structurally parallel. The placeholder editor lands in this leg;
    // leg 6 replaces it wholesale with the full editor (Connection,
    // Credentials, Lifecycle, Test Connection, Danger Zone).
    function renderConnectorsSection() {
      sectionContentEl.innerHTML = '';
      // Promote pending-create to formMode='add' BEFORE deciding grid vs
      // editor so the editor mounts on first paint (no transient grid
      // flash). Pending-edit can't promote here because the account needs
      // to be in the cache; tryConsumePendingConnector handles
      // that path after fetchConnectors_ resolves.
      if (!connectorFormMode && self._pendingConnectorFormMode === 'add') {
        connectorFormMode = 'add';
        editingConnector = null;
        self._pendingConnectorFormMode = null;
        self._pendingConnectorId = null;
      }
      if (connectorFormMode) {
        // Reset orchestrator dirty mirror BEFORE editor mount (mirrors the
        // mcp-source-editor pattern). Editor's onDirtyChange fires on
        // first user input.
        dirty = false;
        var ready = connectorTypesReady || fetchConnectorTypes();
        // F4 follow-up: re-fetch the connector on editor entry so the editor
        // always reflects current backend state (peers, dm_admission, etc.)
        // rather than the cached list entry. Covers the case where a peer was
        // approved while the editor was open or the user navigates back to the
        // same connector after an out-of-band change. Falls back to the cached
        // editingConnector on any fetch error so the UX degrades gracefully.
        var freshConnectorReady = (connectorFormMode === 'edit' && editingConnector && editingConnector.id)
          ? fetch('/api/connectors/' + encodeURIComponent(editingConnector.id))
              .then(function (r) { return r.ok ? r.json() : null; })
              .then(function (fresh) {
                if (fresh && fresh.id) {
                  editingConnector = fresh;
                  // Patch the list cache so the grid tile reflects the
                  // refreshed state if the operator clicks Back.
                  if (connectors) {
                    for (var _ci = 0; _ci < connectors.length; _ci++) {
                      if (connectors[_ci].id === fresh.id) {
                        connectors[_ci] = fresh;
                        break;
                      }
                    }
                  }
                }
              })
              .catch(function () { /* network error — use cached editingConnector */ })
          : Promise.resolve();
        Promise.all([ready, freshConnectorReady]).then(function () {
          // Re-check formMode at resolution time — operator may have
          // navigated away mid-fetch.
          if (connectorFormMode == null || self._activeSection !== 'connectors') return;
          function doHandleBack() {
            connectorFormMode = null;
            editingConnector = null;
            dirty = false;
            if (window.App && window.App.router) App.router.replaceSub('connectors');
            renderConnectorsSection();
          }
          App.studio.renderConnectorEditor(sectionContentEl, editingConnector, CONNECTOR_TYPES, {
            onBack: function () {
              if (dirty) {
                App.confirmDialog({ onConfirm: doHandleBack });
                return;
              }
              doHandleBack();
            },
            onCancel: function () {
              // Create-mode Cancel: navigate back to grid. Cancel-when-
              // dirty is intentional discard — no dialog gate.
              connectorFormMode = null;
              editingConnector = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('connectors');
              renderConnectorsSection();
            },
            onSaveSuccess: function (updated, isCreate) {
              editingConnector = updated;
              connectorFormMode = 'edit';
              dirty = false;
              if (window.App && window.App.router) {
                App.router.replaceSub(self.serializeState());
              }
              if (isCreate) {
                renderConnectorsSection();
              }
            },
            onDeleteSuccess: function () {
              connectorFormMode = null;
              editingConnector = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('connectors');
              renderConnectorsSection();
            },
            onDirtyChange: function (d) { dirty = d; }
          });
        });
        return;
      }
      // Grid branch
      App.studio.renderConnectorsGrid(sectionContentEl, connectors, {
        selectedId: editingConnector ? editingConnector.id : null,
        onSelectConnector: selectConnector,
        onCreateConnector: enterCreateConnectorMode
      });
      fetchConnectors_().then(function () {
        // Stale-then guard — bail if user navigated away mid-fetch.
        if (self._activeSection !== 'connectors') return;
        // After fetch resolves, attempt to consume any pending hash-route
        // selection (e.g. direct-load on #studio/connectors/{id}).
        tryConsumePendingConnector();
      });
    }

    function fetchConnectorTypes() {
      connectorTypesReady = fetch('/api/connectors/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { CONNECTOR_TYPES = types; })
        .catch(function () { CONNECTOR_TYPES = []; });
      return connectorTypesReady;
    }

    function fetchConnectors_() {
      return fetch('/api/connectors')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // Stale-then guard: bail if user navigated away mid-fetch.
          if (self._activeSection !== 'connectors') return;
          connectors = data;
          populateConnectorsGrid();
        })
        .catch(function () {
          if (self._activeSection !== 'connectors') return;
          var gridEl = sectionContentEl.querySelector('.entity-tile-grid');
          if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load connector accounts.</div>';
        });
    }

    function populateConnectorsGrid() {
      // Stale-then guard: bail when no longer on connectors OR
      // when the editor is mounted (no grid in the DOM to populate).
      if (self._activeSection !== 'connectors') return;
      if (connectorFormMode) return;
      App.studio.renderConnectorsGrid(sectionContentEl, connectors, {
        selectedId: editingConnector ? editingConnector.id : null,
        onSelectConnector: selectConnector,
        onCreateConnector: enterCreateConnectorMode
      });
    }

    function selectConnector(id) {
      var account = findConnector(id);
      if (!account) return; // pending-id race; will be re-attempted after fetch
      connectorFormMode = 'edit';
      editingConnector = account;
      pendingConnectorId = null;
      pendingConnectorFormMode = null;
      self._pendingConnectorId = null;
      self._pendingConnectorFormMode = null;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderConnectorsSection();
    }

    function enterCreateConnectorMode() {
      connectorFormMode = 'add';
      editingConnector = null;
      pendingConnectorId = null;
      pendingConnectorFormMode = null;
      self._pendingConnectorId = null;
      self._pendingConnectorFormMode = null;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderConnectorsSection();
    }

    function findConnector(id) {
      if (!connectors) return null;
      for (var i = 0; i < connectors.length; i++) {
        if (connectors[i].id === id) return connectors[i];
      }
      return null;
    }

    function tryConsumePendingConnector() {
      // Pull pending state from instance properties — hydrateState may
      // have set them after init() already captured the closure-locals.
      var pid = self._pendingConnectorId;
      var pmode = self._pendingConnectorFormMode;
      if (!pid && !pmode) return;
      if (pmode === 'add') {
        connectorFormMode = 'add';
        editingConnector = null;
        self._pendingConnectorId = null;
        self._pendingConnectorFormMode = null;
        renderConnectorsSection();
        return;
      }
      if (pmode === 'edit' && pid) {
        var found = findConnector(pid);
        if (found) {
          connectorFormMode = 'edit';
          editingConnector = found;
          self._pendingConnectorId = null;
          self._pendingConnectorFormMode = null;
          renderConnectorsSection();
        }
        // else: not in cache; will retry after fetchConnectors_ resolves.
      }
    }
    self._tryConsumePendingConnector = tryConsumePendingConnector;

    function setActiveSection(section, options) {
      options = options || {};
      var writeUrl = options.writeUrl !== false; // default true
      var prevSection = self._activeSection;
      self._activeSection = section;
      App.layout.updateActiveSection(sectionNavEl, section);
      // Reset MCP-section local state when leaving mcp-sources for another
      // section — closes the editor + clears formMode so a re-entry
      // re-mounts the grid.
      if (prevSection === 'mcp-sources' && section !== 'mcp-sources') {
        mcpSourceFormMode = null;
        editingMcpSource = null;
        dirty = false;
      }
      // M10 F2 leg 05: parallel reset for connectors on leave.
      if (prevSection === 'connectors' && section !== 'connectors') {
        connectorFormMode = null;
        editingConnector = null;
        dirty = false;
      }
      if (section === 'knowledge') {
        renderKnowledgeSection();
      } else if (section === 'mcp-sources') {
        renderMcpSourcesSection();
      } else if (section === 'connectors') {
        renderConnectorsSection();
      } else {
        renderAgentsSection();
      }
      updateContentVisibility();
      if (writeUrl) writeUrl_();
    }
    self._setActiveSection = setActiveSection;

    // Section-content (tile grid / Knowledge stub / MCP Servers) and the
    // agent editor share the main panel; only one is visible at a time. The
    // agent editor takes over when an agent is selected or being created in
    // the Agents section; otherwise section-content is the visible child.
    // The MCP Servers section renders both grid and editor INSIDE
    // sectionContentEl (its own dispatch lives in renderMcpSourcesSection),
    // so editorEl stays hidden whenever _activeSection !== 'agents'.
    function updateContentVisibility() {
      var inAgentEditor = self._activeSection === 'agents' &&
                          (self._selectedAgent || self._createMode);
      sectionContentEl.classList.toggle('is-hidden', !!inAgentEditor);
      editorEl.classList.toggle('is-hidden', !inAgentEditor);
    }

    // ── Single URL-write call site ──────────────────────────────────────
    function writeUrl_() {
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
    }
    self._writeUrl = writeUrl_;

    // ── Data fetching ────────────────────────────────────────────────

    function fetchAgents() { return fetch('/api/agents').then(function (r) { return r.json(); }); }
    function fetchTools() { return fetch('/api/tools').then(function (r) { return r.json(); }); }
    function fetchMcpSources() { return fetch('/api/mcp-sources').then(function (r) { return r.json(); }); }
    function fetchConnectorsList() {
      // M10 F6 L5 — list of all connector accounts for the agent-editor
      // Connectors tab. Parallel to fetchMcpSources above; the REST path
      // is the same one rendered by the connectors grid (leg 4
      // surface) so a fresh fetch picks up deletions / additions made on
      // the connectors page since the studio area mounted.
      return fetch('/api/connectors').then(function (r) { return r.json(); });
    }
    function fetchKnowledgeBases() { return fetch('/api/knowledge-bases').then(function (r) { return r.json(); }); }
    function fetchProviders() { return fetch('/api/providers').then(function (r) { return r.json(); }); }

    // ── F6 leg 05 — tool configs (operator state) + schema cache ──────
    //
    // Operator-state caches. `_disabledTools` (Set<string>) and
    // `_operatorConfigs` ({name → {enabled, config}}) are RE-fetched on
    // every agent-edit mount — the operator may have flipped a toggle in
    // another tab between agent edits. The schema cache below survives
    // across agent changes (schemas are static at runtime).
    self._disabledTools = new Set();
    self._operatorConfigs = {};

    function fetchToolConfigs() {
      return fetch('/api/tools/configs').then(function (r) { return r.json(); });
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
      }).catch(function () {
        self._allMcpSources = self._allMcpSources || [];
      });
    }

    // M10 F6 L5 — parallel to refreshMcpSourcesCache: re-fetch the
    // connector accounts list on every agent-edit mount so an account
    // created (or deleted) on the connectors page becomes
    // visible (or stops being visible — with a defensive "missing"
    // placeholder if pinned) in the Connectors tab without a manual
    // page reload. On error, keep the prior cache.
    function refreshConnectorsCache() {
      return fetchConnectorsList().then(function (accounts) {
        self._allConnectors = accounts;
      }).catch(function () {
        self._allConnectors = self._allConnectors || [];
      });
    }

    // Lazy schema fetcher — closure-cached. Stores the PROMISE (not the
    // resolved value) so concurrent callers during an in-flight fetch
    // reuse the same in-flight promise (no double-fetch). The cache
    // survives across agent changes; schemas are static.
    var _schemaPromiseCache = {};

    // F8 L3 — Lazy MCP-source tools fetcher. Closure-cached promise per
    // sourceId (mirrors fetchToolSchema's pattern above). The cache stores
    // the in-flight promise so concurrent callers reuse it. The cache
    // survives across agent changes within the studio area lifetime; tools
    // are static within a session (no rename within a session).
    //
    // On API `{status: "ok"}`: resolves with the full response object
    // `{tools, capabilities, ...}`.
    // On API `{status: "auth_required"}`: rejects with an Error whose
    // .name === "AuthRequired" and .consent_url is the OAuth redirect URL.
    // UI surfaces an inline notice; NEVER auto-trigger the popup from this
    // surface — the source-edit page is the OAuth affordance.
    // On API `{status: "error"}` or HTTP error: rejects with a generic
    // Error; drops the cache entry so retries land on a fresh promise.
    var _mcpSourceToolsCache = {};

    function fetchMcpSourceTools(sourceId, options) {
      options = options || {};
      if (options.forceRefresh) {
        delete _mcpSourceToolsCache[sourceId];
      }
      if (_mcpSourceToolsCache[sourceId]) return _mcpSourceToolsCache[sourceId];

      var p = fetch('/api/mcp-sources/' + encodeURIComponent(sourceId) + '/test/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }).then(function (r) {
        if (!r.ok) {
          throw new Error('fetchMcpSourceTools: HTTP ' + r.status);
        }
        return r.json();
      }).then(function (data) {
        if (data.status === 'ok') return data;
        if (data.status === 'auth_required') {
          var err = new Error('auth_required');
          err.name = 'AuthRequired';
          err.consent_url = data.consent_url;
          throw err;
        }
        throw new Error(data.error || 'unknown error from fetchMcpSourceTools');
      }).catch(function (err) {
        // Drop the cached promise on any error so next call retries.
        delete _mcpSourceToolsCache[sourceId];
        throw err;
      });
      _mcpSourceToolsCache[sourceId] = p;
      return p;
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

    // Capability lookup keyed `providerId → modelName → ['completion', ...]`.
    // Populated by `loadAll`; the agent-tile renderer reads from it to show
    // capability chips per agent. Only Ollama providers populate entries
    // — other provider types don't expose per-model capabilities.
    self._modelCapsByProvider = {};

    function fetchProviderModelCaps(providers) {
      var ollamaProviders = (providers || []).filter(function (p) { return p.type === 'ollama'; });
      var fetches = ollamaProviders.map(function (p) {
        return fetch('/api/providers/' + encodeURIComponent(p.id) + '/models')
          .then(function (r) { return r.ok ? r.json() : []; })
          .then(function (models) {
            var byModel = {};
            for (var i = 0; i < models.length; i++) {
              var name = models[i].id || models[i].name;
              if (name) byModel[name] = models[i].capabilities || null;
            }
            return { providerId: p.id, byModel: byModel };
          })
          .catch(function () { return { providerId: p.id, byModel: {} }; });
      });
      return Promise.all(fetches).then(function (results) {
        var map = {};
        for (var i = 0; i < results.length; i++) {
          map[results[i].providerId] = results[i].byModel;
        }
        return map;
      });
    }

    function loadAll() {
      return Promise.all([
        fetchAgents(), fetchTools(), fetchMcpSources(),
        fetchKnowledgeBases(), fetchProviders(),
        // M10 F6 L5 — connector accounts populate the agent-editor
        // Connectors tab. Fetched once at area mount alongside the
        // other entity lists; refreshed per-edit via
        // refreshConnectorsCache.
        fetchConnectorsList()
      ])
        .then(function (results) {
          self._agents = results[0];
          self._allTools = results[1];
          self._allMcpSources = results[2];
          self._allKnowledgeBases = results[3];
          self._allProviders = results[4];
          self._allConnectors = results[5];
          // Capability fetch chains off providers — separate Promise.all
          // because it depends on results[4]. Failures are non-fatal:
          // tiles render without chips rather than blocking the list.
          return fetchProviderModelCaps(self._allProviders).then(function (caps) {
            self._modelCapsByProvider = caps;
            if (self._activeSection === 'agents') renderAgentList();
          });
        });
    }

    // ── Agents tile grid rendering (F5 leg 02) ──────────────────────────

    // F9 L3 (A-L3-3) — Aggregate built-in + MCP tool counts for the tile
    // metric lines. Both counts are derivable from data already loaded by
    // loadAll (self._agents, self._allTools, self._allMcpSources), so no
    // backend round-trip is needed. The MCP override math mirrors the
    // mode-detection logic in mcps-tab.js (isAllowlist when
    // overrides.enabled_tools is an array) so the surfaced count matches
    // what the runtime resolver will actually expose at chat-time.
    function _countBuiltinTools(agent, allTools) {
      var enabled = agent && agent.enabled_tools;
      var disabled = (agent && agent.disabled_tools) || [];
      // null/undefined enabled_tools means "all - disabled" (the agent is
      // in denylist mode); array means "exactly these" (allowlist mode).
      // Counts are bounded by the global tool list — toggles for tools no
      // longer present in the codebase shouldn't inflate the count.
      var globalNames = {};
      for (var i = 0; i < (allTools || []).length; i++) {
        globalNames[allTools[i].name] = true;
      }
      if (Array.isArray(enabled)) {
        var n = 0;
        for (var j = 0; j < enabled.length; j++) {
          if (globalNames[enabled[j]]) n++;
        }
        return n;
      }
      var disabledMatching = 0;
      for (var k = 0; k < disabled.length; k++) {
        if (globalNames[disabled[k]]) disabledMatching++;
      }
      return (allTools || []).length - disabledMatching;
    }

    function _countMcpTools(agent, allMcpSources) {
      var sourceIds = (agent && agent.mcp_source_ids) || [];
      if (sourceIds.length === 0) return 0;
      var byId = {};
      for (var i = 0; i < (allMcpSources || []).length; i++) {
        byId[allMcpSources[i].id] = allMcpSources[i];
      }
      var overrides = (agent && agent.mcp_overrides) || {};
      var total = 0;
      for (var s = 0; s < sourceIds.length; s++) {
        var src = byId[sourceIds[s]];
        if (!src) continue; // orphaned attach — defensive; shouldn't happen post A-L3-1
        var cache = src.config && src.config._cache;
        var cachedTools = (cache && Array.isArray(cache.tools)) ? cache.tools : [];
        if (cachedTools.length === 0) continue; // never tested → 0
        var ov = overrides[src.name] || {};
        var enabledList = ov.enabled_tools;
        var disabledList = ov.disabled_tools || [];
        var nameSet = {};
        for (var ti = 0; ti < cachedTools.length; ti++) {
          // Cached tools are objects with `.name`; defensively allow
          // bare strings if a future shape change shows up.
          var tn = (typeof cachedTools[ti] === 'string') ? cachedTools[ti] : (cachedTools[ti] && cachedTools[ti].name);
          if (tn) nameSet[tn] = true;
        }
        if (Array.isArray(enabledList)) {
          // Allowlist: count entries that resolve to a real cached tool.
          for (var ei = 0; ei < enabledList.length; ei++) {
            if (nameSet[enabledList[ei]]) total++;
          }
        } else {
          // Denylist (default): full cache minus matching disabled entries.
          var disMatch = 0;
          for (var di = 0; di < disabledList.length; di++) {
            if (nameSet[disabledList[di]]) disMatch++;
          }
          total += Math.max(0, cachedTools.length - disMatch);
        }
      }
      return total;
    }

    function _pluralize(n, singular, plural) {
      return n + ' ' + (n === 1 ? singular : plural);
    }

    function renderAgentList() {
      agentListEl.innerHTML = '';
      var agents = self._agents;
      if (agents.length === 0 && !self._createMode) {
        var canvas = document.createElement('div');
        canvas.className = 'empty-canvas';
        var inner = document.createElement('div');
        inner.className = 'empty-canvas-inner agent-empty';
        inner.setAttribute('data-testid', 'agent-empty');
        // Message wrapped in a div so the inline-flex CTA below sits on a
        // new line; .empty-canvas-inner's text-align: center centers both.
        var msg = document.createElement('div');
        msg.textContent = 'No agents yet. Create one to get started.';
        inner.appendChild(msg);
        var emptyBtn = document.createElement('button');
        emptyBtn.type = 'button';
        emptyBtn.className = 'new-entity-btn is-expanded';
        emptyBtn.setAttribute('data-testid', 'new-agent-btn-empty');
        emptyBtn.innerHTML = App.icon('square-pen') + '<span>New Agent</span>';
        emptyBtn.addEventListener('click', enterCreateMode);
        inner.appendChild(emptyBtn);
        canvas.appendChild(inner);
        agentListEl.appendChild(canvas);
        return;
      }
      for (var i = 0; i < agents.length; i++) {
        (function (agent) {
          var isActive = self._selectedAgent && self._selectedAgent.name === agent.name && !self._createMode;

          var tileEl = document.createElement('button');
          tileEl.type = 'button';
          tileEl.className = 'entity-tile agent-item' + (isActive ? ' active' : '');
          tileEl.setAttribute('data-testid', 'agent-item');
          tileEl.setAttribute('role', 'option');
          tileEl.dataset.name = agent.name;
          tileEl.setAttribute('aria-selected', isActive ? 'true' : 'false');
          tileEl.setAttribute('aria-label', agent.name);

          var nameSpan = document.createElement('span');
          nameSpan.className = 'entity-tile-name';
          nameSpan.textContent = agent.name;
          tileEl.appendChild(nameSpan);

          var descSpan = document.createElement('span');
          descSpan.className = 'entity-tile-description';
          descSpan.textContent = agent.description || '';
          tileEl.appendChild(descSpan);

          var metaSpan = document.createElement('span');
          metaSpan.className = 'entity-tile-meta';
          var providerLabel = '';
          if (agent.provider_config_id) {
            for (var pi = 0; pi < self._allProviders.length; pi++) {
              if (self._allProviders[pi].id === agent.provider_config_id) {
                providerLabel = self._allProviders[pi].name || '';
                break;
              }
            }
          }
          var modelLabel = agent.llm_model || '';
          if (providerLabel && modelLabel) {
            metaSpan.textContent = providerLabel + ' · ' + modelLabel;
          } else if (providerLabel) {
            metaSpan.textContent = providerLabel;
          } else if (modelLabel) {
            metaSpan.textContent = modelLabel;
          } else {
            metaSpan.textContent = 'no provider';
          }
          tileEl.appendChild(metaSpan);

          // F9 L3 (A-L3-3) — Two metric lines: built-in tool count + MCP
          // tool count. Both rendered unconditionally (even at 0) so tile
          // height stays uniform across the grid. Disambiguated by label
          // ("tools" vs "MCP tools") and by data-testid for browser tests.
          var builtinCount = _countBuiltinTools(agent, self._allTools);
          var mcpCount = _countMcpTools(agent, self._allMcpSources);
          var toolCountSpan = document.createElement('span');
          toolCountSpan.className = 'entity-tile-tool-count';
          toolCountSpan.setAttribute('data-testid', 'agent-tile-tool-count');
          toolCountSpan.textContent = _pluralize(builtinCount, 'tool', 'tools');
          tileEl.appendChild(toolCountSpan);
          var mcpCountSpan = document.createElement('span');
          mcpCountSpan.className = 'entity-tile-tool-count';
          mcpCountSpan.setAttribute('data-testid', 'agent-tile-mcp-tool-count');
          mcpCountSpan.textContent = _pluralize(mcpCount, 'MCP tool', 'MCP tools');
          tileEl.appendChild(mcpCountSpan);

          // Capability chips — only render when we have caps for this
          // (provider, model) pair. Non-Ollama providers won't populate
          // the lookup; tiles render without chips in that case.
          var renderer = window.App.admin && window.App.admin.renderCapabilityChips;
          var caps = null;
          if (agent.provider_config_id && agent.llm_model) {
            var byModel = self._modelCapsByProvider[agent.provider_config_id];
            if (byModel) caps = byModel[agent.llm_model];
          }
          if (renderer && Array.isArray(caps)) {
            var capsWrap = document.createElement('span');
            capsWrap.className = 'agent-tile-caps';
            capsWrap.innerHTML = renderer(caps);
            tileEl.appendChild(capsWrap);
          }

          tileEl.onclick = function () { selectAgent(agent); };
          tileEl.addEventListener('keydown', function (e) {
            if (e.target !== tileEl) return;
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              selectAgent(agent);
            }
          });

          agentListEl.appendChild(tileEl);
        })(agents[i]);
      }
    }

    // ── Agent selection ──────────────────────────────────────────────

    // F5 leg 04: doSelect / doEnterCreateMode — extracted bodies past the
    // dirty-check so the App.confirmDialog onConfirm callback can invoke
    // the real navigation. The async dialog pattern requires the guard to
    // dispatch the dialog and let onConfirm proceed (the synchronous
    // window.confirm guard-and-return pattern doesn't translate directly).
    function doSelect(agent) {
      // Preserve the current tab when re-selecting the same agent (e.g.,
      // when activate() triggers a refresh after the user is already
      // viewing this agent on a non-default tab). Honor any pending tab
      // from hydrate, otherwise keep the existing _activeTab; only reset
      // to 'general' on a genuine agent change.
      var sameAgent = self._selectedAgent && self._selectedAgent.name === agent.name && !self._createMode;
      var tabToActivate;
      if (self._pendingTabName) {
        tabToActivate = self._pendingTabName;
      } else if (sameAgent) {
        tabToActivate = self._activeTab || 'general';
      } else {
        tabToActivate = 'general';
      }
      self._createMode = false;
      self._selectedAgent = agent;
      dirty = false;
      self._pendingTabName = null;
      self._activeTab = tabToActivate;
      if (self._activeSection !== 'agents') {
        setActiveSection('agents', { writeUrl: false });
      }
      renderAgentList();
      // F6 leg 05 — refresh operator-state caches on every agent-edit
      // mount (operator may have flipped a toggle in another tab between
      // agent edits). Render-on-resolve so the Tools tab reflects current
      // disabled state from first paint.
      // F9 L3 (A-L3-1) — also refresh the MCP sources list so a source
      // created on the source-edit page appears in the MCPs tab without
      // a manual page reload. Both refreshes run in parallel.
      Promise.all([refreshToolConfigsCache(), refreshMcpSourcesCache(), refreshConnectorsCache()]).then(function () {
        renderEditor(agent);
        updateContentVisibility();
        writeUrl_();
      });
    }

    function selectAgent(agent) {
      if (dirty) {
        App.confirmDialog({ onConfirm: function () { doSelect(agent); } });
        return;
      }
      doSelect(agent);
    }

    function doEnterCreateMode() {
      self._createMode = true;
      self._selectedAgent = null;
      self._activeTab = 'general';
      dirty = false;
      if (self._activeSection !== 'agents') {
        setActiveSection('agents', { writeUrl: false });
      }
      renderAgentList();
      // F6 leg 05 — refresh operator-state caches before rendering so the
      // new-agent Tools tab reflects current operator-disabled state.
      // F9 L3 (A-L3-1) — also refresh the MCP sources list so a freshly
      // created source is visible from the new-agent MCPs tab without
      // a manual page reload.
      Promise.all([refreshToolConfigsCache(), refreshMcpSourcesCache(), refreshConnectorsCache()]).then(function () {
        renderEditor(null);
        updateContentVisibility();
        writeUrl_();
      });
    }

    function enterCreateMode() {
      if (dirty) {
        App.confirmDialog({ onConfirm: doEnterCreateMode });
        return;
      }
      doEnterCreateMode();
    }

    // ── Editor rendering ─────────────────────────────────────────────

    function renderEmptyEditor() {
      editorEl.innerHTML = '';
      tabHandle = null;
    }

    // F5 leg 03: renderEditor delegates to the agent-editor module which
    // builds the header + action cluster + tablist + three tab panels.
    // Per-tab render helpers populate the panels; the General tab is mounted
    // synchronously so existing form-field tests find their selectors
    // immediately.
    function renderEditor(agent) {
      var isCreate = !agent;
      tabHandle = App.studio.renderAgentEditor(editorEl, agent, self._allProviders, {
        initialTab: self._activeTab || 'general',
        onBack: handleBack,
        onDelete: handleDeleteEditor,
        onSave: function () { save(isCreate); },
        onCancel: function () { cancelEdit(); },
        onTabChange: function (tabId) { setActiveTab(tabId); },
        // F5 leg 05: tabs in the same agent share the form's dirty state, so
        // switching tabs does NOT lose unsaved data — no confirmation prompt.
        // The dirty gate still fires on Back, section nav, and hash-route
        // navigation to a different agent.
        onTestProvider: testProvider,
        toolCategories: TOOL_CATEGORIES,
        allTools: self._allTools,
        onChange: checkDirty,
        // F6 leg 05 — operator-state surfaces in Tools tab. Caches were
        // refreshed at editor-mount time (see selectAgent / doSelect). The
        // schema fetcher is closure-cached and survives agent changes.
        disabledTools: self._disabledTools,
        operatorConfigs: self._operatorConfigs,
        fetchToolSchema: fetchToolSchema,
        // F8 L3 — MCP source list + per-source tools fetcher for MCPs tab.
        allMcpSources: self._allMcpSources,
        fetchMcpSourceTools: fetchMcpSourceTools,
        pendingMcpAgentSourceId: self._pendingMcpAgentSourceId || null,
        // M10 F6 L5 — connector accounts list for the Connectors tab.
        // Same mount-time cache pattern as allMcpSources.
        allConnectors: self._allConnectors,
        // Callback so renderMcpsTab can notify studio.js when the selected
        // source changes (chip click → per-attachment editor). studio.js
        // updates _selectedMcpAgentSourceId and syncs the URL.
        onSelectedMcpSourceChange: function (sourceId) {
          self._selectedMcpAgentSourceId = sourceId;
          writeUrl_();
        }
      });

      // Wire field-level dirty tracking + provider-change side-effects.
      // These run AFTER the editor DOM is in place.
      wireEditorEvents(isCreate, agent || {
        provider_config_id: self._allProviders.length > 0 ? self._allProviders[0].id : null,
        llm_model: ''
      });

      // Dirty snapshot baseline.
      snapshot = getFormSnapshot();
    }

    // setActiveTab — analogous to setActiveSection. Updates _activeTab,
    // calls the tab handle's activate (which swaps panel visibility +
    // aria-selected + roving tabindex), writes URL via _writeUrl unless
    // the caller opts out (hydrate path).
    function setActiveTab(tab, options) {
      options = options || {};
      var writeUrl = options.writeUrl !== false;
      // F8 L3: clear per-source selection when leaving the MCPs tab so the
      // URL doesn't carry a stale /{source-id} when switching to another tab.
      if (tab !== 'mcps') self._selectedMcpAgentSourceId = null;
      self._activeTab = tab;
      if (tabHandle && tabHandle.getActive() !== tab) {
        tabHandle.activate(tab);
      }
      if (writeUrl) writeUrl_();
    }
    self._setActiveTab = setActiveTab;

    // ── Action-cluster handlers ──────────────────────────────────────

    // Back: clear selection, exit create mode, return to #studio/agents.
    // F5 leg 04: dirty gate via App.confirmDialog. The async restructure
    // mirrors selectAgent / enterCreateMode — extract the body past the
    // dirty-check into doHandleBack so the dialog's onConfirm callback can
    // invoke it.
    function doHandleBack() {
      self._selectedAgent = null;
      self._createMode = false;
      dirty = false;
      self._activeTab = 'general';
      self._selectedMcpAgentSourceId = null;  // F8 L3: clear per-source selection
      renderEmptyEditor();
      renderAgentList();
      updateContentVisibility();
      writeUrl_();
    }

    function handleBack() {
      if (dirty) {
        App.confirmDialog({ onConfirm: doHandleBack });
        return;
      }
      doHandleBack();
    }

    // Cancel discards in-progress edits and restores the editor to the
    // current agent's saved state. In create-mode, it returns to the tile
    // grid (there is no saved state to revert to). The button only fires
    // when dirty (disabled by checkDirty otherwise), so no extra guard.
    function cancelEdit() {
      if (self._createMode) {
        doHandleBack();
        return;
      }
      if (self._selectedAgent) {
        renderEditor(self._selectedAgent);
        dirty = false;
        checkDirty();
      }
    }

    // Editor's Delete button — migrated to App.confirmDelete in F6 leg 04
    // (helper now has 3 permanent consumers: chat session items, studio
    // agent editor, provider editor). Capital-D label "Confirm Delete?"
    // preserved via the confirmLabel option for test_flow_agent_crud.py:73
    // stability and parity with the provider editor.
    function handleDeleteEditor(deleteBtn) {
      var name = self._selectedAgent ? self._selectedAgent.name : null;
      if (!name) return;
      App.confirmDelete(deleteBtn, function (btn, revertFn) {
        fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
          })
          .then(function () {
            self._selectedAgent = null;
            dirty = false;
            return loadAll();
          })
          .then(function () {
            if (self._agents.length > 0) {
              selectAgent(self._agents[0]);
            } else {
              renderEmptyEditor();
              updateContentVisibility();
              writeUrl_();
            }
          })
          .catch(function (err) {
            revertFn();
            App.showFlash(editorEl, (err && err.message) || 'Delete failed', true);
          });
      }, { confirmLabel: 'Confirm Delete?' });
    }

    // Test provider — POST /api/providers/{id}/test with empty body.
    // Reads the LIVE #studio-provider value (NOT cfg.provider_config_id)
    // so unsaved provider changes are testable.
    function testProvider() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      var resultSpan = editorEl.querySelector('.test-result');
      if (!providerSelect || !providerSelect.value) {
        if (resultSpan) {
          resultSpan.className = 'test-result test-result-fail';
          resultSpan.textContent = '✗ No provider selected';
        }
        return;
      }
      var providerId = providerSelect.value;
      if (resultSpan) {
        resultSpan.className = 'test-result';
        resultSpan.textContent = 'Testing…';
      }
      fetch('/api/providers/' + encodeURIComponent(providerId) + '/test', { method: 'POST' })
        .then(function (r) {
          return r.json().then(function (body) { return { ok: r.ok, body: body }; });
        })
        .then(function (res) {
          var detail = (res.body && res.body.detail) || '';
          var isOk = res.ok && res.body && res.body.status === 'ok';
          if (resultSpan) {
            resultSpan.className = 'test-result ' + (isOk ? 'test-result-ok' : 'test-result-fail');
            resultSpan.textContent = (isOk ? '✓ ' : '✗ ') + detail;
          }
          if (isOk) {
            App.showFlash(editorEl, detail || 'Provider test ok');
          } else {
            // Bypass the local one-arg showFlash wrapper which drops the
            // error flag — call App.showFlash directly with isError=true
            // to preserve the error styling.
            App.showFlash(editorEl, detail || 'Provider test failed', true);
          }
        })
        .catch(function (err) {
          var msg = (err && err.message) || 'Network error';
          if (resultSpan) {
            resultSpan.className = 'test-result test-result-fail';
            resultSpan.textContent = '✗ ' + msg;
          }
          App.showFlash(editorEl, msg, true);
        });
    }

    // Capability lookup keyed by model id. Populated by fetchModelsForProvider
    // and consumed by renderModelCapabilities on change. Reset per fetch so
    // a provider switch doesn't bleed stale caps into the new dropdown.
    var modelCapsBy = {};
    // F6.5 L04: parallel cache for the per-model context-window value
    // returned by /api/providers/{id}/models. Same lifecycle as modelCapsBy.
    var modelCtxBy = {};

    function fmtCtxTokens(n) {
      if (typeof n !== 'number' || !(n > 0)) return null;
      if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
      if (n >= 1000) return (n / 1000).toFixed(0) + 'k';
      return String(n);
    }

    function renderModelCapabilities() {
      var capsEl = editorEl.querySelector('.model-capabilities');
      var selectEl = editorEl.querySelector('#studio-model');
      if (!capsEl || !selectEl) return;
      var modelId = selectEl.value;
      var caps = modelCapsBy[modelId];
      var ctx = modelCtxBy[modelId];
      var renderer = window.App.admin && window.App.admin.renderCapabilityChips;
      var capsHtml = (modelId && renderer && caps !== undefined && caps !== null)
        ? renderer(caps)
        : '';
      var ctxLabel = fmtCtxTokens(ctx);
      var ctxHtml = ctxLabel
        ? '<span class="model-capabilities-label">Max context:</span> ' +
          '<span class="model-ctx-chip" data-testid="model-ctx-chip">' + ctxLabel + '</span>'
        : '';
      if (!capsHtml && !ctxHtml) {
        capsEl.innerHTML = '';
        return;
      }
      var parts = [];
      if (capsHtml) {
        parts.push('<span class="model-capabilities-label">Capabilities:</span> ' + capsHtml);
      }
      if (ctxHtml) parts.push(ctxHtml);
      capsEl.innerHTML = parts.join(' &middot; ');
    }

    // Race-condition guard for fetchModelsForProvider (review I6). Rapid
    // provider switching fires concurrent fetches; without a guard a slow
    // earlier response silently clobbers a fresh later one. Two layers:
    //   1. AbortController cancels the in-flight request on the next call.
    //   2. providerId equality check on resolution drops any response that
    //      no longer matches the live selection (covers AbortController
    //      gaps and any future fetch path that doesn't honor signals).
    var _modelsFetchController = null;
    var _activeProviderId = null;

    function fetchModelsForProvider(providerId) {
      var selectEl = editorEl.querySelector('#studio-model');
      var loadingEl = editorEl.querySelector('.model-loading');
      if (!selectEl) return;

      // Cancel any in-flight fetch from a prior provider selection.
      if (_modelsFetchController) {
        try { _modelsFetchController.abort(); } catch (_) { /* noop */ }
      }
      _modelsFetchController = (typeof AbortController !== 'undefined')
        ? new AbortController()
        : null;
      _activeProviderId = providerId;
      var fetchProviderId = providerId;
      var fetchSignal = _modelsFetchController ? _modelsFetchController.signal : undefined;

      var currentVal = selectEl.dataset.pendingValue || selectEl.value;

      if (!providerId) {
        selectEl.innerHTML = '<option value="" disabled selected>Select a provider first</option>';
        if (loadingEl) loadingEl.textContent = '';
        modelCapsBy = {};
        modelCtxBy = {};
        renderModelCapabilities();
        return;
      }

      if (loadingEl) loadingEl.textContent = 'Loading models…';

      fetch('/api/providers/' + encodeURIComponent(providerId) + '/models', {
        signal: fetchSignal,
      })
        .then(function (r) {
          if (!r.ok) throw new Error('Failed');
          return r.json();
        })
        .then(function (models) {
          // Drop the response if the user has since switched providers.
          // Without this guard a slow A-fetch arriving after B-fetch
          // would clobber the picker with A's models while B is selected.
          if (_activeProviderId !== fetchProviderId) return;
          modelCapsBy = {};
          modelCtxBy = {};
          var optsHtml = '<option value="" disabled>Choose a model</option>';
          for (var i = 0; i < models.length; i++) {
            var modelId = models[i].id || models[i].name;
            var sel = modelId === currentVal ? ' selected' : '';
            optsHtml += '<option value="' + escapeAttr(modelId) + '"' + sel + '>' + escapeHtml(modelId) + '</option>';
            // Capability cache shape: dict<model_id, list|null>.
            // Both ollama (`capabilities`) and openrouter (`supported_parameters`,
            // server-side aliased to `capabilities`) flow through this single
            // path. Empty list \u2192 null (fail-open: "fetched but no caps known"
            // \u2192 no chip, mirrors openrouter_api.get_model_capabilities).
            // Absent field \u2192 cache entry stays unset \u2192 no chip.
            var capsRaw = models[i].capabilities;
            if (Array.isArray(capsRaw) && capsRaw.length > 0) {
              modelCapsBy[modelId] = capsRaw;
            } else if (Array.isArray(capsRaw) && capsRaw.length === 0) {
              modelCapsBy[modelId] = null;
            }
            // F6.5 L04: context_length is the per-model max-context-tokens
            // surfaced via /api/providers/{id}/models. Number > 0 \u2192 chip;
            // null/missing \u2192 no chip (operator sees nothing rather than a
            // potentially-wrong value).
            var ctxRaw = models[i].context_length;
            if (typeof ctxRaw === 'number' && ctxRaw > 0) {
              modelCtxBy[modelId] = ctxRaw;
            }
          }
          selectEl.innerHTML = optsHtml;
          // Surface a previously-saved or carried-over value that isn't
          // in the freshly fetched list as a visible "(custom)" option —
          // a clear cue that the selection won't match a known model
          // under this provider, without silently wiping it.
          if (currentVal && !selectEl.querySelector('option[value="' + CSS.escape(currentVal) + '"]')) {
            var customOpt = '<option value="' + escapeAttr(currentVal) + '" selected>' + escapeHtml(currentVal) + ' (custom)</option>';
            selectEl.insertAdjacentHTML('beforeend', customOpt);
          }
          if (loadingEl) {
            loadingEl.textContent = models.length === 0 ? 'No models discovered' : '';
          }
          delete selectEl.dataset.pendingValue;
          renderModelCapabilities();
        })
        .catch(function (err) {
          // Aborted fetches (provider changed mid-flight) are not errors —
          // skip the failure UI so the next fetch's success can paint
          // cleanly without a flash of "Failed to load models".
          if (err && err.name === 'AbortError') return;
          if (_activeProviderId !== fetchProviderId) return;
          var failOpt = document.createElement('option');
          failOpt.value = '';
          failOpt.disabled = true;
          failOpt.selected = true;
          failOpt.textContent = 'Failed to load models';
          selectEl.replaceChildren(failOpt);
          if (loadingEl) loadingEl.textContent = '';
          modelCapsBy = {};
          modelCtxBy = {};
          renderModelCapabilities();
        });
    }

    function recomputeTestDisabled() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      var testBtn = editorEl.querySelector('.test-provider-btn');
      if (!testBtn) return;
      testBtn.disabled = !providerSelect || !providerSelect.value;
    }

    function wireEditorEvents(isCreate, cfg) {
      // Dirty tracking on all inputs (skips disabled Advanced stubs).
      var inputs = editorEl.querySelectorAll('.field-input, .field-textarea, .field-select, .tool-toggle');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].disabled) continue;
        inputs[i].addEventListener('input', checkDirty);
        inputs[i].addEventListener('change', checkDirty);
      }

      // Provider change → repopulate model select, clear VRAM warning,
      // recompute Test btn. Model picker is always a <select> (browsers
      // give us free type-ahead via the native dropdown), so no element
      // swap is needed across provider types.
      var providerSelect = editorEl.querySelector('#studio-provider');
      if (providerSelect) {
        providerSelect.addEventListener('change', function () {
          var selectedProviderId = providerSelect.value;
          var modelEl = editorEl.querySelector('#studio-model');
          if (modelEl) modelEl.selectedIndex = 0;
          clearVramWarning();
          fetchModelsForProvider(selectedProviderId);
          recomputeTestDisabled();
        });
        if (cfg.provider_config_id) {
          var modelSelect = editorEl.querySelector('#studio-model');
          if (modelSelect && cfg.llm_model) modelSelect.dataset.pendingValue = cfg.llm_model;
          fetchModelsForProvider(cfg.provider_config_id);
        }
      }

      // Model change → debounced VRAM check + capability panel refresh.
      var modelInput = editorEl.querySelector('#studio-model');
      if (modelInput) {
        modelInput.addEventListener('change', debouncedVramCheck);
        modelInput.addEventListener('change', renderModelCapabilities);
        if (cfg.llm_model && cfg.provider_config_id) {
          debouncedVramCheck();
        }
      }
    }

    // ── Dirty tracking ───────────────────────────────────────────────

    function getFormSnapshot() {
      var data = collectFormData();
      return JSON.stringify(data);
    }

    function checkDirty() {
      var current = getFormSnapshot();
      dirty = current !== snapshot;
      // `disabled` is the single source of truth for both Save and Cancel.
      var saveBtn = editorEl.querySelector('.save-btn');
      if (saveBtn) saveBtn.disabled = !dirty;
      var cancelBtn = editorEl.querySelector('.cancel-btn');
      if (cancelBtn) cancelBtn.disabled = !dirty;
    }

    // ── Form data collection ─────────────────────────────────────────
    //
    // collectFormData queries by [data-field="..."] selectors which work
    // regardless of which tab/panel the field lives in. Fields that span
    // tabs (provider, model, system_prompt, max_iterations on General;
    // tool toggles on Tools) are all reachable from editorEl.
    function collectFormData() {
      var data = {};
      var fields = editorEl.querySelectorAll('.field-input, .field-textarea, .field-select');
      for (var i = 0; i < fields.length; i++) {
        var f = fields[i];
        if (f.disabled) continue; // skip Advanced-stub disabled inputs
        var key = f.dataset.field;
        if (!key) continue;
        if (key === 'max_iterations') {
          data[key] = parseInt(f.value, 10) || 20;
        } else if (key === 'provider_config_id') {
          data[key] = f.value || null;
        } else {
          data[key] = f.value;
        }
      }

      // Scope to built-in-tool checkbox toggles only. MCP source toggles
      // carry `data-mcp-source-id` (NOT `data-tool`); MCP per-tool toggles
      // carry `data-mcp-tool-toggle` (handled in a separate collector
      // below). The `input[type="checkbox"]` filter plus `[data-tool]`
      // attribute is sufficient to disambiguate. (Previously this query
      // required `.tool-toggle` for the iOS-pill pattern; Mission 08 F4 L2
      // widened the per-tool tile to use a visible `.checkbox-primary`
      // input — no class disambiguation possible — so the selector
      // shifted to `input[type="checkbox"][data-tool]`.)
      var toggles = editorEl.querySelectorAll('input[type="checkbox"][data-tool]');
      var enabledNames = [];
      var disabledNames = [];
      var allOn = true;
      var allOff = true;
      for (var t = 0; t < toggles.length; t++) {
        if (toggles[t].checked) {
          enabledNames.push(toggles[t].dataset.tool);
          allOff = false;
        } else {
          disabledNames.push(toggles[t].dataset.tool);
          allOn = false;
        }
      }

      if (allOn) {
        data.enabled_tools = null;
        data.disabled_tools = [];
      } else if (enabledNames.length <= disabledNames.length) {
        data.enabled_tools = enabledNames;
        data.disabled_tools = [];
      } else {
        data.enabled_tools = null;
        data.disabled_tools = disabledNames;
      }

      // Connections (chips) — Tools tab does not currently render chips
      // (MCP/KB attach is a future-flight stub), so this collects whatever
      // chip-areas exist (none in F5 leg 03; future legs may add them).
      // The new override chip-list editors carry data-tool-override-tool
      // (NOT data-type), so they don't match the [data-type] selector
      // here and are picked up below in the override walk.
      // F8 L4 — MCPs tab uses tool-row toggles instead of chip-area.
      // Walk the new [data-mcp-source-toggle]:checked selector to collect
      // attached source IDs. KB chips still use the chip-area pattern (KB
      // tab is a stub; whenever it lands, it can pick its own selector).
      var mcpToggles = editorEl.querySelectorAll('[data-mcp-source-toggle][data-mcp-source-id]');
      var kbChips = editorEl.querySelectorAll('.chip-area[data-type="kb"] .chip');
      data.mcp_source_ids = [];
      data.kb_ids = [];
      for (var m = 0; m < mcpToggles.length; m++) {
        if (mcpToggles[m].checked) data.mcp_source_ids.push(mcpToggles[m].dataset.mcpSourceId);
      }
      for (var k = 0; k < kbChips.length; k++) data.kb_ids.push(kbChips[k].dataset.id);

      // F6 leg 05 — collect tool_overrides from per-tool override panels.
      // Each override input carries `data-tool-override-tool="{name}"` and
      // `data-tool-override-field="{field}"`. The chip-list-editor wrapper
      // <div> ALSO carries both attrs so the same selector picks it up;
      // readFieldValue dispatches on shape.
      var overrideEls = editorEl.querySelectorAll('[data-tool-override-tool][data-tool-override-field]');
      var overrides = {};
      var helpers = window.App.adminFormHelpers;
      for (var oi = 0; oi < overrideEls.length; oi++) {
        var oe = overrideEls[oi];
        // Skip the .field-row wrapper (which carries the attrs for error
        // rendering) — it's a div with no value to read.
        if (oe.classList && oe.classList.contains('field-row')) continue;
        var toolName = oe.dataset.toolOverrideTool;
        var fieldName = oe.dataset.toolOverrideField;
        if (!toolName || !fieldName) continue;
        var v = helpers ? helpers.readFieldValue(oe) : null;
        // Skip empty overrides — agent.tool_overrides only contains tools
        // with at least one set field.
        if (v === null || v === undefined) continue;
        if (Array.isArray(v) && v.length === 0) continue;
        if (typeof v === 'string' && v === '') continue;
        if (!overrides[toolName]) overrides[toolName] = {};
        overrides[toolName][fieldName] = v;
      }
      data.tool_overrides = Object.keys(overrides).length > 0 ? overrides : null;

      // F8 L3 — Walk mcp_overrides selectors. Mirrors the tool_overrides
      // walk above, but groups by source-name (data-mcp-override-source)
      // instead of tool-name. Per-tool checkboxes are handled separately
      // below via [data-mcp-tool-toggle][data-mcp-source].
      var mcpOverrideEls = editorEl.querySelectorAll(
        '[data-mcp-override-source][data-mcp-override-field]'
      );
      var mcpOverrides = {};
      for (var mi = 0; mi < mcpOverrideEls.length; mi++) {
        var me = mcpOverrideEls[mi];
        if (me.classList && me.classList.contains('field-row')) continue;
        var mSourceName = me.dataset.mcpOverrideSource;
        var mFieldName = me.dataset.mcpOverrideField;
        if (!mSourceName || !mFieldName) continue;
        var mv = helpers ? helpers.readFieldValue(me) : null;
        if (mv === null || mv === undefined) continue;
        if (Array.isArray(mv) && mv.length === 0) continue;
        if (typeof mv === 'string' && mv === '') continue;
        if (!mcpOverrides[mSourceName]) mcpOverrides[mSourceName] = {};
        mcpOverrides[mSourceName][mFieldName] = mv;
      }

      // Per-tool checkbox toggles within each attached source. Each
      // checkbox carries `data-mcp-tool-toggle` (un-prefixed tool name)
      // and `data-mcp-source` (source name). The wrapping group element
      // carries `data-mcp-tool-mode={"allowlist"|"denylist"}` declared at
      // render time based on the agent's existing override shape.
      //
      // Mode semantics:
      //   - denylist (default for new attachments): collect un-checked
      //     tools into disabled_tools.
      //   - allowlist (when agent already has enabled_tools set): collect
      //     checked tools into enabled_tools.
      var toggleEls = editorEl.querySelectorAll('[data-mcp-tool-toggle][data-mcp-source]');
      var enabledBySource = {};
      var disabledBySource = {};
      var modeBySource = {};
      for (var ti = 0; ti < toggleEls.length; ti++) {
        var te = toggleEls[ti];
        var srcName = te.dataset.mcpSource;
        var tlName = te.dataset.mcpToolToggle;
        if (!srcName || !tlName) continue;
        var groupEl = te.closest('[data-mcp-tool-group]');
        var mode = (groupEl && groupEl.dataset.mcpToolMode) || 'denylist';
        modeBySource[srcName] = mode;
        if (mode === 'allowlist') {
          if (te.checked) {
            if (!enabledBySource[srcName]) enabledBySource[srcName] = [];
            enabledBySource[srcName].push(tlName);
          }
        } else {
          if (!te.checked) {
            if (!disabledBySource[srcName]) disabledBySource[srcName] = [];
            disabledBySource[srcName].push(tlName);
          }
        }
      }
      for (var sname in modeBySource) {
        if (!mcpOverrides[sname]) mcpOverrides[sname] = {};
        if (modeBySource[sname] === 'allowlist') {
          mcpOverrides[sname].enabled_tools = enabledBySource[sname] || [];
        } else {
          if (disabledBySource[sname] && disabledBySource[sname].length > 0) {
            mcpOverrides[sname].disabled_tools = disabledBySource[sname];
          }
        }
      }

      data.mcp_overrides = Object.keys(mcpOverrides).length > 0 ? mcpOverrides : null;

      // ── M10 F6 L5 — connector_ids + connector_acls ─────────
      //
      // `connector_ids` from the Connectors-tab attach toggles
      // (`[data-connector-toggle][data-connector-id]`).
      // Order preserved by DOM walk (mirrors the mcp_source_ids walk
      // above). Stale ids (pinned-but-deleted accounts) are also
      // collected via their "(missing — account deleted)" placeholder
      // row, which renders an enabled toggle — operator must explicitly
      // un-check to prune. Mirrors the MCP-source-deletion behavior.
      var connectorToggles = editorEl.querySelectorAll(
        '[data-connector-toggle][data-connector-id]'
      );
      data.connector_ids = [];
      for (var ci = 0; ci < connectorToggles.length; ci++) {
        if (connectorToggles[ci].checked) {
          data.connector_ids.push(
            connectorToggles[ci].dataset.connectorId
          );
        }
      }

      // `connector_acls` from the per-account ACL editors. L7 HAT
      // semantic redesign: each axis is independently captured as one
      // of three values (tri-state):
      //   - null → inherit account-scope
      //   - []   → explicit empty (peers: no peer; channels: DMs only)
      //   - [items] → subset (intersected with account-scope)
      //
      // Markup is one of two modes per axis (set by connectors-tab.js):
      //   - .connector-acl-chiplist with data-connector-acl-mode="chips"
      //     → free chip-list editor (axis: empty chips ⇒ null,
      //       non-empty chips ⇒ [items])
      //   - .connector-acl-checkboxlist with
      //     data-connector-acl-mode="checkboxes"
      //     → checkbox list (all checked ⇒ null,
      //       none checked ⇒ [],
      //       some checked ⇒ [checked items])
      //
      // If BOTH axes of an account resolve to null (inherit-both), we
      // OMIT the account entry from the serialized payload (matches the
      // pre-redesign omit-when-both-empty behavior; the validator
      // accepts both shapes either way). data.connector_acls = null
      // when the outer dict ends up empty.
      var aclAxisEls = editorEl.querySelectorAll(
        '[data-connector-acl-account][data-connector-acl-list][data-connector-acl-mode]'
      );
      var aclAccounts = {};
      for (var li = 0; li < aclAxisEls.length; li++) {
        var wrapper = aclAxisEls[li];
        var aid = wrapper.dataset.connectorAclAccount;
        var listKind = wrapper.dataset.connectorAclList;
        var mode = wrapper.dataset.connectorAclMode;
        if (!aid || (listKind !== 'peers' && listKind !== 'channels')) continue;

        // M11 F12 L4 — per-agent peers/channels persist in the
        // structured-tuple shape mirroring account-scope storage:
        //   peers    → ``[{id}]`` bare dicts (post-v28 M11 F17 L8
        //               Leg D; dm_allowed retired — per-agent peers
        //               never carried it post-v26 either; the latent
        //               bug here emitted it with value true which the
        //               post-v26 Pydantic validator rejects).
        //   channels → ``[{guild_id, channel_id}]`` (guild_id sourced
        //               from the per-channel-id lookup map on the
        //               checkbox wrapper, ``data-channel-guild-id-map``
        //               attribute; the dropdown emits structured tuples
        //               directly so the chips-mode path passes them
        //               through).
        function _wrapPerAgentEntry(id, axisListKind, channelGuildIdMap) {
          var s = (id == null) ? '' : String(id);
          if (!s) return null;
          if (axisListKind === 'peers') {
            return { id: s };
          }
          if (axisListKind === 'channels') {
            var g = null;
            if (channelGuildIdMap && Object.prototype.hasOwnProperty.call(channelGuildIdMap, s)) {
              var mapped = channelGuildIdMap[s];
              g = mapped ? String(mapped) : null;
            }
            return { guild_id: g, channel_id: s };
          }
          return s;
        }

        var axisValue; // null | [] | [items]
        if (mode === 'checkboxes') {
          var boxes = wrapper.querySelectorAll('input[type="checkbox"]');
          var total = boxes.length;
          var checkedVals = [];
          for (var bi = 0; bi < total; bi++) {
            if (boxes[bi].checked) checkedVals.push(boxes[bi].value);
          }
          // M11 F12 L4 — channels checkbox wrapper carries a per-id
          // guild_id lookup as a JSON-encoded data attribute (populated
          // by connectors-tab.js from the account-scope structured
          // shape). Decode once per wrapper; pass into the wrapper.
          var channelGuildIdMap = null;
          if (listKind === 'channels') {
            var rawMap = wrapper.getAttribute('data-channel-guild-id-map');
            if (rawMap) {
              try { channelGuildIdMap = JSON.parse(rawMap); }
              catch (e) { channelGuildIdMap = null; }
            }
          }
          if (total === 0) {
            // No account-scope chips to choose from — treat as inherit.
            axisValue = null;
          } else if (checkedVals.length === total) {
            axisValue = null; // all checked = inherit
          } else if (checkedVals.length === 0) {
            axisValue = []; // none checked = explicit empty
          } else {
            var wrappedSubset = [];
            for (var wi = 0; wi < checkedVals.length; wi++) {
              var wrapped = _wrapPerAgentEntry(checkedVals[wi], listKind, channelGuildIdMap);
              if (wrapped) wrappedSubset.push(wrapped);
            }
            axisValue = wrappedSubset;
          }
        } else {
          // chips mode
          //
          // M11 F3 L6b — per-agent overlay dispatch: when the wrapper
          // carries an ``_overlayChipValues`` getter (installed by
          // connectors-tab.js when the per-agent overlay swaps in the
          // dropdown for Discord-type accounts), consult it first. The
          // dropdown's chip DOM shape differs from the chip-list
          // editor's; falling through to the text-node walk would
          // mis-read dropdown chips. Stub-type / no-entry accounts
          // continue rendering the chip-list and the text-node walk
          // reads them identically to the pre-L6b shape.
          //
          // M11 F12 L4 — dropdown path returns the structured-tuple
          // shape directly (its valueShape was 'peer' / 'channel'); pass
          // those entries through unchanged. The text-node-walk fallback
          // produces bare id strings, which get wrapped via
          // ``_wrapPerAgentEntry`` (guild_id defaults to null for
          // chip-list-mode channels — these flows have no account-scope
          // chips to source guild context from).
          var chipVals = [];
          if (typeof wrapper._overlayChipValues === 'function') {
            var overlayVals = wrapper._overlayChipValues() || [];
            for (var ov = 0; ov < overlayVals.length; ov++) {
              var ovEntry = overlayVals[ov];
              if (ovEntry == null) continue;
              if (typeof ovEntry === 'object') {
                chipVals.push(ovEntry);  // already structured per L4
              } else {
                var ovStr = String(ovEntry);
                if (ovStr) {
                  var ovWrapped = _wrapPerAgentEntry(ovStr, listKind, null);
                  if (ovWrapped) chipVals.push(ovWrapped);
                }
              }
            }
          } else {
            var chips = wrapper.querySelectorAll('.chip');
            for (var cj = 0; cj < chips.length; cj++) {
              var text = chips[cj].textContent || '';
              if (text.charAt(text.length - 1) === '×') {
                text = text.slice(0, -1);
              }
              text = text.trim();
              if (!text) continue;
              var chipWrapped = _wrapPerAgentEntry(text, listKind, null);
              if (chipWrapped) chipVals.push(chipWrapped);
            }
          }
          if (chipVals.length === 0) {
            axisValue = null; // empty chip-list = inherit / unrestricted
          } else {
            axisValue = chipVals;
          }
        }

        if (!aclAccounts[aid]) aclAccounts[aid] = { peers: null, channels: null };
        aclAccounts[aid][listKind] = axisValue;
      }

      // M11 F10 L3: collect per-agent admit_dms opt-out toggles. Walks
      // every input with ``data-field="admit_dms"`` carrying a
      // ``data-account-id``; emits ``admit_dms: false`` into
      // ``aclAccounts[aid]`` ONLY when the checkbox is UNCHECKED.
      //
      // Semantic contract (mirrors the connector_acls "absent = inherit"
      // convention for peers/channels):
      //   - checked → DO NOT emit the key (inherit account-scope)
      //   - unchecked → emit ``admit_dms: false`` (explicit opt-out)
      //
      // ``true`` is structurally equivalent to inherit and never
      // produced by the UI; it would just clutter the persisted shape.
      //
      // Disabled-and-checked inputs are skipped — when account-scope
      // ``dm_admission === "none"`` the per-agent override is inert,
      // and dropping it from emission keeps storage clean. This is the
      // intentional cleanup posture documented in the L3 leg artifact:
      // flipping account-scope to "none" and saving the agent removes
      // the per-agent opt-out from storage.
      //
      // Walks AFTER the peers/channels collection (which initializes
      // ``aclAccounts[aid] = { peers: null, channels: null }`` entries
      // for any account with rendered axis editors) so a merge is
      // safe — but we still init on miss to handle the
      // admit-dms-without-peers-or-channels-rendered edge case (e.g.
      // empty account-scope lists where no axis editor mounts).
      var admitDmsToggles = editorEl.querySelectorAll(
        '[data-field="admit_dms"][data-account-id]'
      );
      for (var adi = 0; adi < admitDmsToggles.length; adi++) {
        var adInput = admitDmsToggles[adi];
        var adAid = adInput.getAttribute('data-account-id');
        if (!adAid) continue;
        if (adInput.checked) continue;  // checked = inherit (no key emitted)
        if (adInput.disabled) continue;  // disabled = structurally inert
        if (!aclAccounts[adAid]) {
          aclAccounts[adAid] = { peers: null, channels: null };
        }
        aclAccounts[adAid].admit_dms = false;
      }

      var finalAcls = {};
      for (var aid2 in aclAccounts) {
        var entry = aclAccounts[aid2];
        // M11 F10 L3: omit accounts where ALL of peers/channels/admit_dms
        // are inherit-state. Equivalently: emit the entry only if any
        // axis has an explicit narrowing. ``admit_dms`` is explicit
        // when the key is present (collect path only sets it to
        // ``false``; ``true`` and absent both inherit).
        if (entry.peers === null
            && entry.channels === null
            && !("admit_dms" in entry)) continue;
        finalAcls[aid2] = entry;
      }
      data.connector_acls = Object.keys(finalAcls).length > 0 ? finalAcls : null;

      // M11 F7 L11: collect per-account always_listen toggles into a
      // ``{account_id: bool, ...}`` dict for the AgentConfig
      // ``connector_always_listen`` field (L6 storage). Mirrors the
      // ``connector_acls`` collection precedent immediately above —
      // walk every per-agent toggle that carries
      // ``data-field="connector_always_listen"`` with
      // ``data-account-id``, group by account id, and emit ``null`` when
      // no toggles are rendered (no attached accounts, or the agent
      // editor's Connectors tab never mounted). The L6 validator accepts
      // null + the dict shape; null is the "field not in use" baseline.
      var alwaysListenToggles = editorEl.querySelectorAll(
        '[data-field="connector_always_listen"][data-account-id]'
      );
      var alwaysListenDict = {};
      for (var ali = 0; ali < alwaysListenToggles.length; ali++) {
        var alInput = alwaysListenToggles[ali];
        var alAid = alInput.getAttribute('data-account-id');
        if (alAid) alwaysListenDict[alAid] = !!alInput.checked;
      }
      data.connector_always_listen = Object.keys(alwaysListenDict).length > 0
        ? alwaysListenDict
        : null;

      return data;
    }

    // ── Save ─────────────────────────────────────────────────────────

    function save(isCreate) {
      var data = collectFormData();
      var errorEl = editorEl.querySelector('.editor-error');

      if (isCreate) {
        if (!data.name || !data.name.trim()) {
          if (errorEl) errorEl.textContent = 'Name is required.';
          return;
        }
        fetch('/api/agents', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Create failed'); });
            return r.json();
          })
          .then(function (created) {
            dirty = false;
            self._createMode = false;
            return loadAll().then(function () {
              var found = null;
              for (var i = 0; i < self._agents.length; i++) {
                if (self._agents[i].name === created.name) { found = self._agents[i]; break; }
              }
              if (found) selectAgent(found);
              showFlash('Agent created');
            });
          })
          .catch(function (err) {
            if (errorEl) errorEl.textContent = err.message;
          });
      } else {
        var oldName = self._selectedAgent.name;
        var requestedName = (data.name || '').trim();
        if (!requestedName) {
          if (errorEl) errorEl.textContent = 'Name is required.';
          return;
        }
        // F4 L02 functional batch — rename support. If the user changed
        // the Name field on an existing agent, POST to the rename
        // endpoint FIRST so the PUT save can target the new PK. On
        // rename failure, abort and surface the error; do NOT proceed
        // with the PUT (the operator can re-try or revert the name
        // input).
        var renamePromise;
        var effectiveName;
        if (requestedName !== oldName) {
          effectiveName = requestedName;
          renamePromise = fetch('/api/agents/' + encodeURIComponent(oldName) + '/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_name: requestedName })
          })
            .then(function (r) {
              if (!r.ok) {
                return r.json().then(function (e) {
                  throw new Error(typeof e.detail === 'string' ? e.detail : 'Rename failed');
                });
              }
              return r.json();
            })
            .then(function (renamed) {
              // Re-bind the in-closure "currently-editing" name so the
              // subsequent PUT targets the new PK and so the area's
              // URL state serialization reflects the rename.
              self._selectedAgent = renamed;
              return renamed;
            });
        } else {
          effectiveName = oldName;
          renamePromise = Promise.resolve(null);
        }

        renamePromise
          .then(function () {
            data.name = effectiveName;
            return fetch('/api/agents/' + encodeURIComponent(effectiveName), {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data)
            });
          })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Save failed'); });
            return r.json();
          })
          .then(function (updated) {
            dirty = false;
            self._selectedAgent = updated;
            return loadAll().then(function () {
              var found = null;
              for (var i = 0; i < self._agents.length; i++) {
                if (self._agents[i].name === updated.name) { found = self._agents[i]; break; }
              }
              if (found) {
                self._selectedAgent = found;
                renderEditor(found);
                showFlash('Saved');
                // Rewrite the URL so refresh / back-button targets the
                // new agent name (the area's URL keys on
                // _selectedAgent.name; writeUrl_ re-serializes).
                if (typeof writeUrl_ === 'function') writeUrl_();
              }
            });
          })
          .catch(function (err) {
            if (errorEl) errorEl.textContent = err.message;
          });
      }
    }

    // ── Helpers ──────────────────────────────────────────────────────

    var showFlash = function (msg) { App.showFlash(editorEl, msg); };

    var formatBytes = App.formatBytes;
    var vramCheckTimer = null;

    function getSelectedProviderType() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      if (!providerSelect || !providerSelect.value) return null;
      for (var i = 0; i < self._allProviders.length; i++) {
        if (String(self._allProviders[i].id) === String(providerSelect.value)) {
          return self._allProviders[i];
        }
      }
      return null;
    }

    function clearVramWarning() {
      var el = editorEl.querySelector('.studio-vram-warning');
      if (el) {
        el.innerHTML = '';
        el.classList.remove('visible');
      }
    }

    function checkVramForModel() {
      var provider = getSelectedProviderType();
      if (!provider || provider.type !== 'ollama') {
        clearVramWarning();
        return;
      }

      var modelInput = editorEl.querySelector('#studio-model');
      if (!modelInput || !modelInput.value.trim()) {
        clearVramWarning();
        return;
      }

      var modelName = modelInput.value.trim();
      var providerId = provider.id;

      Promise.all([
        fetch('/api/providers/' + encodeURIComponent(providerId) + '/models/status')
          .then(function (r) { return r.ok ? r.json() : []; }),
        fetch('/api/providers/' + encodeURIComponent(providerId) + '/models')
          .then(function (r) { return r.ok ? r.json() : []; })
      ])
        .then(function (results) {
          var running = results[0] || [];
          var models = results[1] || [];

          for (var i = 0; i < running.length; i++) {
            var runName = running[i].name || running[i].model || '';
            if (runName === modelName || runName.split(':')[0] === modelName.split(':')[0]) {
              clearVramWarning();
              return;
            }
          }

          var modelSize = 0;
          for (var j = 0; j < models.length; j++) {
            var mId = models[j].id || models[j].name || '';
            if (mId === modelName || mId.split(':')[0] === modelName.split(':')[0]) {
              modelSize = models[j].size || 0;
              break;
            }
          }

          if (!modelSize) {
            clearVramWarning();
            return;
          }

          var totalLoaded = 0;
          var loadedCount = running.length;
          for (var k = 0; k < running.length; k++) {
            totalLoaded += running[k].size_vram || 0;
          }

          var warningEl = editorEl.querySelector('.studio-vram-warning');
          if (warningEl) {
            var msg = 'This model requires ~' + escapeHtml(formatBytes(modelSize)) + '.';
            if (loadedCount > 0) {
              msg += ' Currently ' + escapeHtml(formatBytes(totalLoaded)) +
                ' loaded across ' + loadedCount + ' model' + (loadedCount !== 1 ? 's' : '') + '.';
            }
            warningEl.innerHTML = msg;
            warningEl.classList.add('visible');
          }
        })
        .catch(function () {
          clearVramWarning();
        });
    }

    function debouncedVramCheck() {
      if (vramCheckTimer) clearTimeout(vramCheckTimer);
      vramCheckTimer = setTimeout(checkVramForModel, 500);
    }

    var escapeHtml = App.escapeHtml;
    var escapeAttr = App.escapeAttr;

    // ── Init ─────────────────────────────────────────────────────────

    function tryConsumePendingSelect() {
      if (!self._pendingSelectName) return;
      if (!self._agents || self._agents.length === 0) return;
      var target = null;
      for (var i = 0; i < self._agents.length; i++) {
        if (self._agents[i].name === self._pendingSelectName) { target = self._agents[i]; break; }
      }
      self._pendingSelectName = null;
      if (target && (!self._selectedAgent || self._selectedAgent.name !== target.name)) {
        selectAgent(target);
      }
    }

    newAgentBtn.addEventListener('click', enterCreateMode);

    self._refresh = function () {
      loadAll().then(function () {
        if (self._selectedAgent) {
          var found = null;
          for (var i = 0; i < self._agents.length; i++) {
            if (self._agents[i].name === self._selectedAgent.name) { found = self._agents[i]; break; }
          }
          if (found) selectAgent(found);
          else if (self._agents.length > 0) selectAgent(self._agents[0]);
          else renderEmptyEditor();
        }
      });
      // Also refresh the MCP-sources section if active (e.g. another tab
      // mutated the inventory while studio was deactivated).
      if (self._activeSection === 'mcp-sources' && !mcpSourceFormMode) {
        fetchMcpSources_();
      }
    };
    self._tryConsumePendingSelect = function () { tryConsumePendingSelect(); };

    // F4 L5: confirmLeave wired here so it can close over the local `dirty` flag.
    // Gate semantics mirror admin.js's _confirmLeaveImpl (admin.js:625-636): dirty
    // AND in-editor → confirm dialog; otherwise → proceed immediately. The
    // `inEditor` predicate covers BOTH editor mount contexts.
    self._confirmLeaveImpl = function (proceed, abort) {
      var inEditor =
        (self._activeSection === 'agents' && self._selectedAgent) ||
        (self._activeSection === 'mcp-sources' && mcpSourceFormMode);
      if (dirty && inEditor) {
        App.confirmDialog({ onConfirm: proceed, onCancel: abort });
      } else {
        proceed();
      }
    };

    // Pre-fetch MCP source types so the editor mount path doesn't have to
    // wait on the first network round-trip when the operator clicks "New
    // MCP Server" or deep-links to mcp-sources/{id}.
    fetchMcpSourceTypes();

    setActiveSection(self._activeSection || 'agents', { writeUrl: false });

    loadAll().then(function () {
      if (self._activeSection === 'agents') {
        if (self._pendingSelectName) {
          tryConsumePendingSelect();
          if (self._selectedAgent) return;
        }
        // Bare #studio/agents shows the tile grid in the main panel; no
        // agent is auto-selected. The user picks a tile (or +) to enter
        // the editor.
        renderEmptyEditor();
        updateContentVisibility();
      }
    });
  },

  activate: function () {
    if (this._refresh) this._refresh();
  },
  // F4 L5: confirmLeave — cross-area dirty-gate hook consumed by
  // app.js:switchTo before deactivating the outgoing area on cross-area
  // navigation. Mirrors admin.js:748-754. The `_confirmLeaveImpl` handle
  // is attached inside `init()` so it can close over the local `dirty`
  // flag; this descriptor method just routes through it.
  confirmLeave: function (proceed, abort) {
    if (this._confirmLeaveImpl) {
      this._confirmLeaveImpl(proceed, abort);
    } else {
      proceed();
    }
  },
  deactivate: function () {}
});
