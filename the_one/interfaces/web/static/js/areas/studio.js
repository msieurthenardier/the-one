App.registerArea({
  id: 'studio',
  label: 'Agent Studio',
  icon: App.icons.studio,
  order: 20,
  sidebarLabel: 'Agent list',

  // ── Hash-routing serialize/hydrate ──────────────────────────────────
  //
  // serializeState branch order (explicit):
  //   1. _activeSection === 'knowledge' → 'knowledge' | 'knowledge/{kb_id}'
  //      (Flight 6 leg 1, L1-D1 — mirrors the mcp-sources deep-link shape)
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
    if (this._activeSection === 'knowledge') {
      if (this._selectedKbId) return 'knowledge/' + encodeURIComponent(this._selectedKbId);
      return 'knowledge';
    }
    // Mission 23 Flight 2 Leg 2 (DD-9): the Connectors section is
    // deliberately NOT deep-link-aware like mcp-sources — no
    // 'connectors/new' or 'connectors/{id}' sub-path. A refresh while
    // editing lands back on the grid (minimal-form trade-off, not a
    // hash-routing gap).
    if (this._activeSection === 'connectors') return 'connectors';
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
    if (sub === 'knowledge') {
      section = 'knowledge';
      // F4 L7-style bare-URL defensive clear (mirrors the 'agents'/
      // '!sub' branch below): re-entering the bare section always shows
      // the grid, never a stale detail-view selection from a prior
      // navigation within the same area lifecycle.
      this._selectedKbId = null;
    } else if (sub && sub.indexOf('knowledge/') === 0) {
      // Flight 6 leg 1 (L1-D1): direct-load on knowledge/{kb_id} — parse
      // the id so the detail view opens on refresh, mirroring the
      // mcp-sources/{id} parsing immediately below.
      section = 'knowledge';
      var krest = sub.slice('knowledge/'.length);
      if (krest.charAt(krest.length - 1) === '/') krest = krest.slice(0, -1);
      var kslashIdx = krest.indexOf('/');
      if (kslashIdx !== -1) krest = krest.slice(0, kslashIdx);
      this._selectedKbId = krest ? decodeURIComponent(krest) : null;
    } else if (sub === 'connectors') {
      section = 'connectors';
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
        if (tab === 'general' || tab === 'knowledge' || tab === 'mcps' || tab === 'tools' || tab === 'self-configuration') {
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
    if (this._setActiveSection) {
      this._setActiveSection(section, { writeUrl: false });
    }
    // Within-mcp-sources sub-navigation (e.g. mcp-sources → mcp-sources/new)
    // doesn't change _activeSection, so _setActiveSection's renderContent
    // path won't re-enter the editor branch. Fire consume unconditionally
    // so within-section direct-loads open the editor.
    if (this._tryConsumePendingMcpSource) this._tryConsumePendingMcpSource();
  },

  init: function (sidebar, content) {
    var self = this;

    // ── Per-instance state (promoted from closure locals to this.* so
    //    serializeState reads the right values) ────────────────────────────
    self._agents = [];
    self._allTools = [];
    self._allMcpSources = [];
    self._allKnowledgeBases = [];
    // F6 L3 (L3-D1) — explicit load-success flag for the agent-editor's
    // Knowledge tab. NOT inferred from `_allKnowledgeBases` being
    // null/empty: `refreshKnowledgeBasesCache` keeps a populated STALE
    // array on failure (DD-15), so a non-null array says nothing about
    // whether the most recent refresh succeeded.
    self._knowledgeBasesLoaded = false;
    self._allProviders = [];
    self._selectedAgent = null;
    // Squawk 0090 — explicit load-success flag for `self._selectedAgent`,
    // the SAME discipline DD-4 fixed `_knowledgeBasesLoaded` with (above).
    // `doSelect`'s fresh-agent GET has a `.catch` that resolves with the
    // stale cached agent so the editor still renders SOMETHING (L3-D7);
    // that stale object is also what `_storedUngatedDisabledNames()`
    // unions into `disabled_tools`, so a failed fetch would otherwise
    // re-emit a PRE-rename `kb__{old_slug}__…__search` entry and overwrite
    // the post-rename one `rename_kb_tool_references` wrote — silently
    // re-enabling a tool the operator disabled. So: render from the stale
    // object, but refuse to SAVE from it. `false` blocks Save; create-mode
    // and "no agent selected" leave it `true` (nothing stale to union).
    self._selectedAgentLoaded = true;
    self._pendingSelectName = self._pendingSelectName || null;
    self._pendingTabName = self._pendingTabName || null;
    self._createMode = false;
    self._activeSection = self._activeSection || 'agents';
    self._activeTab = self._activeTab || 'general';
    // F8 L3 Patch C — selected source-id within the agent MCPs tab.
    // Written by renderMcpsTab when a chip is clicked or a deep-link hydrates.
    // Read by serializeState to append /{source-id} to the URL.
    self._selectedMcpAgentSourceId = null;
    // Flight 6 leg 1 (L1-D1/L1-D2): the Knowledge detail-view selection
    // and its poll-timer handle. `self._selectedKbId` may already be set
    // by a pre-init hydrateState call (mirrors `_pendingSelectName`'s
    // `|| null` preserve, though in this codebase's actual boot order
    // init() always runs first — see app.js::switchTo).
    self._selectedKbId = self._selectedKbId || null;
    self._knowledgePollTimer = null;
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

    // ── Connectors state (Mission 23 Flight 2 Leg 2) ────────────────────
    // Deliberately simpler than the MCP-sources state above — no
    // pending-hash-route race handling (DD-9: no deep-link sub-paths).
    var CONNECTOR_TYPES = [];
    var connectorTypesReady = null;
    var connectors = null; // null until first fetch resolves
    var connectorFormMode = null; // null | 'add' | 'edit'
    var editingConnector = null;

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

    var TOOL_CATEGORIES = {
      'Filesystem': ['read_file', 'write_file', 'edit_file', 'delete_file', 'move_file', 'mkdir', 'glob', 'grep', 'list_dir'],
      'Execution': ['shell', 'python_exec', 'shell_session_start', 'shell_session_send', 'shell_session_close', 'shell_session_list'],
      'Web': ['download_file', 'fetch_url', 'http_request', 'web_search'],
      // Squawk 0028: Mission 23 Flight 2's two connector tools
      // (`send_to_platform_channel` / `fetch_channel_history`) were
      // registered as built-ins with no Tools-tab category, making them
      // invisible to the per-agent enable/disable affordance DD-4 assumes
      // exists. Named 'Connectors' to match the tools' domain — distinct
      // from the sidebar's 'Connectors' NAV SECTION (external connector
      // configs, above); this is a tools-tab category tile, same as
      // Filesystem/Execution/Web.
      'Connectors': ['send_to_platform_channel', 'fetch_channel_history']
      // Squawk 0032: the Administration area's Tools grid keeps its own
      // (differently-shaped) TOOL_CATEGORIES mirrors in
      // admin/tools-grid.js and admin/tools-editor.js — brought to
      // parity with this one by that squawk. Not unified with this one.
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
        // Header CTA (M17 F3 leg 03 CTA unification): always visible with
        // icon + text label, in BOTH empty and populated grid states. The
        // empty-canvas renders a second instance of the same component
        // (see renderAgentList) wired to the same handler.
        '<button class="btn-outlined-primary" type="button" data-testid="new-agent-btn">' +
          App.icon('square-pen') + '<span>New Agent</span>' +
        '</button>' +
      '</div>' +
      '<div class="entity-tile-grid" role="listbox" aria-label="Agents"></div>';
    var agentListEl = agentsContentEl.querySelector('.entity-tile-grid');
    var newAgentBtn = agentsContentEl.querySelector('[data-testid="new-agent-btn"]');

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
      // Mission 23 Flight 2 Leg 2: reinstates a "Connectors" nav entry
      // (present M10 through Mission 23 Flight 1, which reset the
      // connector subsystem and removed it along with the routes).
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
          // same-section reclicks, so re-entering Agents after visiting
          // another section restored the previously-edited agent's editor
          // (incl. tab). Routing should land on the listing instead.
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
            } else if (prev === 'knowledge' && self._selectedKbId) {
              self._selectedKbId = null;
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
            } else if (section === 'knowledge' && self._selectedKbId) {
              // setActiveSection's own reset block only fires on a section
              // CHANGE (prevSection !== section), so a same-section reclick
              // needs the poll cleared here too — the grid render below
              // would otherwise leave the detail view's timer running.
              clearKnowledgePoll();
              knowledgeDetailHandle = null;
              self._selectedKbId = null;
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

    // Knowledge section (Flight 6 leg 1, DD-2, L1-D1) — the global
    // knowledge-base inventory. Two-branch dispatch mirroring
    // renderMcpSourcesSection: a grid (no selection) and a detail view
    // (self._selectedKbId set), hash-routed by serializeState/hydrateState
    // above as 'knowledge' / 'knowledge/{kb_id}'.
    var knowledgeBases = null; // section-local grid cache; null until first fetch resolves
    var knowledgeGridHandle = null; // { updateList(kbs) } — never a full rebuild on refresh
    var knowledgeDetailHandle = null; // { updateStatus(status), updateItems(items) } — L1-D2's poll target
    // kb-studio-round-trip remediation FIX 1 (2026-09-18): the signature
    // (per-status counts + chunk count) the items list was LAST rendered
    // against. The status poll re-fetches `/items` and rebuilds the list
    // only when a fresh `/status` response's signature differs from this
    // one — never on every tick, which would blow away an open chunks/
    // source panel or scroll position (L1-D2's actual intent). Reset to
    // null on every fresh mount below so the first poll tick after a
    // remount compares against the mount-time snapshot, not a stale
    // knowledge base's signature.
    var lastKnownItemsSignature = null;

    function knowledgeItemsSignature(status) {
      return JSON.stringify((status && status.items) || {}) + '|' + (status && status.chunks);
    }

    function renderKnowledgeSection() {
      sectionContentEl.innerHTML = '';
      if (self._selectedKbId) {
        renderKnowledgeDetailView(self._selectedKbId);
      } else {
        // L1-D2 site 3: navigating from the detail view back to the grid
        // stops the poll — covered here since every grid mount (direct
        // nav, Back button, delete) routes through this branch.
        clearKnowledgePoll();
        knowledgeDetailHandle = null;
        renderKnowledgeGridView();
      }
    }

    function renderKnowledgeGridView() {
      // Full rebuild ONLY at mount — `knowledgeGridHandle.updateList` (not
      // a second call to renderKnowledgeGrid) carries every subsequent
      // refresh below, so a fetch resolving after the operator has opened
      // the create form never rebuilds the chrome out from under them.
      knowledgeGridHandle = App.studio.renderKnowledgeGrid(sectionContentEl, knowledgeBases, {
        onSelectKnowledgeBase: selectKnowledgeBase,
        onCreateSuccess: function () {
          // AC-2: appears in the list without a page reload.
          fetchKnowledgeBases_();
        }
      });
      fetchKnowledgeBases_();
    }

    function fetchKnowledgeBases_() {
      return fetch('/api/knowledge-bases')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // Stale-then guard: bail if the user navigated away, or into a
          // detail view, mid-fetch.
          if (self._activeSection !== 'knowledge' || self._selectedKbId) return;
          knowledgeBases = data;
          if (knowledgeGridHandle) knowledgeGridHandle.updateList(knowledgeBases);
        })
        .catch(function () {
          if (self._activeSection !== 'knowledge' || self._selectedKbId) return;
          var gridEl = sectionContentEl.querySelector('.entity-tile-grid');
          if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load knowledge bases.</div>';
        });
    }

    function findKnowledgeBase(id) {
      if (!knowledgeBases) return null;
      for (var i = 0; i < knowledgeBases.length; i++) {
        if (knowledgeBases[i].id === id) return knowledgeBases[i];
      }
      return null;
    }

    function selectKnowledgeBase(id) {
      self._selectedKbId = id;
      if (window.App && window.App.router) App.router.replaceSub(self.serializeState());
      renderKnowledgeSection();
    }

    function renderKnowledgeDetailView(kbId) {
      var cached = findKnowledgeBase(kbId);
      if (cached) {
        mountKnowledgeDetail(cached);
        return;
      }
      // Not in the grid's cache (e.g. a direct hash-load on
      // #studio/knowledge/{kb_id} before the grid has ever fetched) —
      // fetch it directly rather than waiting on a list fetch that may
      // never run while a detail view stays selected.
      fetch('/api/knowledge-bases/' + encodeURIComponent(kbId))
        .then(function (r) {
          if (!r.ok) throw new Error('knowledge base not found: HTTP ' + r.status);
          return r.json();
        })
        .then(function (kb) {
          if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) return;
          mountKnowledgeDetail(kb);
        })
        .catch(function () {
          // Unknown/deleted id — fall back to the grid rather than a dead view.
          if (self._activeSection !== 'knowledge') return;
          self._selectedKbId = null;
          if (window.App && window.App.router) App.router.replaceSub('knowledge');
          renderKnowledgeSection();
        });
    }

    function mountKnowledgeDetail(kb) {
      sectionContentEl.innerHTML = '<div class="admin-loading">Loading knowledge base…</div>';
      Promise.all([
        fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/status')
          .then(function (r) {
            if (!r.ok) throw new Error('status fetch failed: HTTP ' + r.status);
            return r.json();
          }),
        fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items')
          .then(function (r) {
            if (!r.ok) throw new Error('items fetch failed: HTTP ' + r.status);
            return r.json();
          })
      ]).then(function (results) {
        // Stale-then guard: bail if the user navigated away, or to a
        // different knowledge base, mid-fetch.
        if (self._activeSection !== 'knowledge' || self._selectedKbId !== kb.id) return;
        lastKnownItemsSignature = knowledgeItemsSignature(results[0]);
        // F6 L5 (L5-D3): reset the orchestrator's dirty mirror BEFORE the
        // detail view mounts — mirrors the mcp-sources/connectors editor
        // pattern ("Reset orchestrator dirty mirror BEFORE editor mount").
        // The fresh render closure starts clean; onDirtyChange only fires
        // on the operator's first edit-form input.
        dirty = false;
        knowledgeDetailHandle = App.studio.renderKnowledgeDetail(
          sectionContentEl, kb, { status: results[0], items: results[1] },
          {
            // AC-8/L5-D3: mirrors mcp-sources' own onBack — the LOCAL
            // Back button doesn't decide to discard on its own; a dirty
            // edit form gates through App.confirmDialog here, same as
            // section-nav/cross-area navigation gates through
            // `_confirmLeaveImpl`.
            onBack: function () {
              function doBack() {
                self._selectedKbId = null;
                dirty = false;
                if (window.App && window.App.router) App.router.replaceSub('knowledge');
                renderKnowledgeSection();
              }
              if (dirty) {
                App.confirmDialog({ onConfirm: doBack });
                return;
              }
              doBack();
            },
            onDeleteSuccess: function () {
              self._selectedKbId = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('knowledge');
              renderKnowledgeSection();
            },
            // F6 L3 (L3-D5), carried by F6 L5's Name+Description edit form
            // (L5-D2): re-mount the detail view from the saved object —
            // refreshes the header title and re-fetches status/items — and
            // update the grid's section-local cache so navigating back
            // shows the new name without a second fetch.
            onSaveSuccess: function (updatedKb) {
              if (knowledgeBases) {
                for (var ki = 0; ki < knowledgeBases.length; ki++) {
                  if (knowledgeBases[ki].id === updatedKb.id) { knowledgeBases[ki] = updatedKb; break; }
                }
              }
              mountKnowledgeDetail(updatedKb);
            },
            // F6 L5 (L5-D3): bridges the edit form's dirty state into the
            // orchestrator's closure `dirty`, consumed by
            // `_confirmLeaveImpl`'s `inEditor` gate — mirrors the
            // mcp-sources/connectors `onDirtyChange: function (d) { dirty = d; }`
            // pattern already established below.
            onDirtyChange: function (d) { dirty = d; }
          }
        );
        startKnowledgePoll(kb.id);
      }).catch(function () {
        if (self._activeSection !== 'knowledge' || self._selectedKbId !== kb.id) return;
        sectionContentEl.innerHTML = '<div class="admin-loading">Failed to load knowledge base.</div>';
      });
    }

    // ── L1-D2: the 5-second status poll, owned here (not by the render
    // module) so the three clear sites below can all reach one handle.
    function clearKnowledgePoll() {
      if (self._knowledgePollTimer) {
        clearInterval(self._knowledgePollTimer);
        self._knowledgePollTimer = null;
      }
    }

    function startKnowledgePoll(kbId) {
      clearKnowledgePoll(); // single handle — never stack timers across re-renders
      self._knowledgePollTimer = setInterval(function () {
        if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) {
          clearKnowledgePoll();
          return;
        }
        fetch('/api/knowledge-bases/' + encodeURIComponent(kbId) + '/status')
          .then(function (r) {
            if (r.status === 404) {
              // Edge case: the knowledge base was deleted while this view
              // was open (another tab, or the poll racing a delete) —
              // return to the grid rather than leaving a dead view or
              // looping on the error.
              clearKnowledgePoll();
              self._selectedKbId = null;
              if (window.App && window.App.router) App.router.replaceSub('knowledge');
              renderKnowledgeSection();
              return null;
            }
            if (!r.ok) throw new Error('status poll failed: HTTP ' + r.status);
            return r.json();
          })
          .then(function (status) {
            if (!status) return; // 404 branch above already handled it
            if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) return;
            if (knowledgeDetailHandle) knowledgeDetailHandle.updateStatus(status);
            // kb-studio-round-trip remediation FIX 1: invalidate the items
            // list only when the counts it was last rendered against have
            // changed (registering a folder, an indexing pass completing,
            // a watcher pickup, …) — re-fetching `/items` on every tick
            // would destroy an open chunks/source panel and scroll
            // position, which is exactly what L1-D2 excluded polling items
            // to avoid.
            var signature = knowledgeItemsSignature(status);
            if (signature !== lastKnownItemsSignature) {
              fetch('/api/knowledge-bases/' + encodeURIComponent(kbId) + '/items')
                .then(function (r2) {
                  if (!r2.ok) throw new Error('items poll failed: HTTP ' + r2.status);
                  return r2.json();
                })
                .then(function (freshItems) {
                  if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) return;
                  if (knowledgeDetailHandle && knowledgeDetailHandle.updateItems) {
                    knowledgeDetailHandle.updateItems(freshItems);
                  }
                  lastKnownItemsSignature = signature;
                })
                .catch(function () {
                  // Leave the list as last rendered; `lastKnownItemsSignature`
                  // is not advanced, so this is retried on the next tick.
                });
            }
          })
          .catch(function () {
            // L1-D2: a failed poll leaves the last-rendered state — no
            // blanking, no escalation to a flash.
          });
      }, 5000);
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

    // ── Connectors section (Mission 23 Flight 2 Leg 2, DD-9) — one file,
    // no deep-link sub-paths (see serializeState). Mirrors the
    // mcp-sources grid/editor dispatch above, minus the pending-hash-
    // route race handling that only mcp-sources needs.
    function renderConnectorsSection() {
      sectionContentEl.innerHTML = '';
      if (connectorFormMode) {
        dirty = false;
        var typesReady = connectorTypesReady || fetchConnectorTypes();
        // Fetch agents directly rather than reading `self._agents` — the
        // shared `loadAll()` populating it runs once at init and is NOT
        // guaranteed to have resolved yet if the operator navigates
        // straight to #studio/connectors and clicks "New Connector"
        // immediately (a real race, not just a theoretical one — caught
        // by tests/browser/test_studio_connector_editor.py). A dedicated
        // fetch here is always fresh and never depends on load order.
        Promise.all([typesReady, fetchAgents()]).then(function (results) {
          var agentsForDropdown = results[1];
          if (connectorFormMode == null || self._activeSection !== 'connectors') return;
          function doHandleBack() {
            connectorFormMode = null;
            editingConnector = null;
            dirty = false;
            if (window.App && window.App.router) App.router.replaceSub('connectors');
            renderConnectorsSection();
          }
          App.studio.renderConnectorEditor(
            sectionContentEl, editingConnector, CONNECTOR_TYPES, agentsForDropdown, {
              onBack: function () {
                if (dirty) {
                  App.confirmDialog({ onConfirm: doHandleBack });
                  return;
                }
                doHandleBack();
              },
              onCancel: doHandleBack,
              onSaveSuccess: function (updated, isCreate) {
                editingConnector = updated;
                connectorFormMode = 'edit';
                dirty = false;
                if (isCreate) renderConnectorsSection();
              },
              onDeleteSuccess: doHandleBack,
              onDirtyChange: function (d) { dirty = d; }
            }
          );
        });
        return;
      }
      App.studio.renderConnectorsGrid(sectionContentEl, connectors, {
        selectedId: editingConnector ? editingConnector.id : null,
        onSelectConnector: selectConnector,
        onCreateConnector: enterCreateConnectorMode
      });
      fetchConnectors_();
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
          if (self._activeSection !== 'connectors') return;
          connectors = data;
          if (!connectorFormMode) {
            App.studio.renderConnectorsGrid(sectionContentEl, connectors, {
              selectedId: editingConnector ? editingConnector.id : null,
              onSelectConnector: selectConnector,
              onCreateConnector: enterCreateConnectorMode
            });
          }
        })
        .catch(function () {
          if (self._activeSection !== 'connectors') return;
          var gridEl = sectionContentEl.querySelector('.entity-tile-grid');
          if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load connectors.</div>';
        });
    }

    function findConnector(id) {
      if (!connectors) return null;
      for (var i = 0; i < connectors.length; i++) {
        if (connectors[i].id === id) return connectors[i];
      }
      return null;
    }

    function selectConnector(id) {
      var found = findConnector(id);
      if (!found) return;
      connectorFormMode = 'edit';
      editingConnector = found;
      if (window.App && window.App.router) App.router.replaceSub(self.serializeState());
      renderConnectorsSection();
    }

    function enterCreateConnectorMode() {
      connectorFormMode = 'add';
      editingConnector = null;
      if (window.App && window.App.router) App.router.replaceSub(self.serializeState());
      renderConnectorsSection();
    }

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
      if (prevSection === 'connectors' && section !== 'connectors') {
        connectorFormMode = null;
        editingConnector = null;
        dirty = false;
      }
      // Flight 6 leg 1 (L1-D2 site 1): leaving Knowledge for another
      // section stops the 5-second status poll AND clears the detail-view
      // selection, so re-entering #studio/knowledge mounts the grid — the
      // same contract the two blocks above already have. F6 L5 (L5-D3)
      // adds the dirty-mirror reset the mcp-sources/connectors blocks
      // above already carry — this site is reached directly by callers
      // that route through setActiveSection without going through
      // commit() first (e.g. hash-route hydration), so it needs its own
      // reset rather than relying on commit()'s.
      if (prevSection === 'knowledge' && section !== 'knowledge') {
        clearKnowledgePoll();
        knowledgeDetailHandle = null;
        self._selectedKbId = null;
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
    // M21 F01 L02 (DD3): the editor's fetch — as opposed to the admin
    // grid's `fetchMcpSources_` below — includes per-agent
    // self-configuration surface rows so the agent editor's MCPs tab and
    // Self-configuration tab can see them; the admin grid excludes them by
    // default (no query param there).
    function fetchMcpSources() {
      return fetch('/api/mcp-sources?include_agent_surfaces=1').then(function (r) { return r.json(); });
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
      // Re-fetch both the MCP sources cache (the surface row was just
      // created/destroyed server-side) AND the agent itself (its
      // mcp_source_ids just changed server-side, outside the Save flow).
      // doSelect() re-renders the editor while preserving the active tab,
      // so the MCPs tab reflects the new/removed row without a reload.
      return Promise.all([
        refreshMcpSourcesCache(),
        fetch('/api/agents/' + encodeURIComponent(name)).then(function (r) { return r.json(); })
      ]).then(function (results) {
        var updated = results[1];
        for (var i = 0; i < self._agents.length; i++) {
          if (self._agents[i].name === name) { self._agents[i] = updated; break; }
        }
        doSelect(updated);
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
          // The flag lives outside the Save flow; re-render so the tab
          // (and its status fetch) reflect the new value.
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

    function fetchSelfConfigurationPendingCount(name) {
      return fetch('/api/agents/' + encodeURIComponent(name) +
        '/self-configuration/revisions/pending-count')
        .then(function (r) {
          if (!r.ok) throw new Error('fetch pending-count: HTTP ' + r.status);
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
      return fetchKnowledgeBases().then(function (kbs) {
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
        fetchKnowledgeBases(), fetchProviders()
      ])
        .then(function (results) {
          self._agents = results[0];
          self._allTools = results[1];
          self._allMcpSources = results[2];
          self._allKnowledgeBases = results[3];
          self._allProviders = results[4];
          // Capability fetch chains off providers — separate Promise.all
          // because it depends on results[4]. Failures are non-fatal:
          // tiles render without chips rather than blocking the list.
          return fetchProviderModelCaps(self._allProviders).then(function (caps) {
            self._modelCapsByProvider = caps;
            if (self._activeSection === 'agents') renderAgentList();
          });
        });
    }

    // Squawk 0014 — loadAll() rejects (network blip, non-JSON error body)
    // with no rejection handler at either call site, so the Studio area
    // silently stays blank / stops refreshing. Shared renderer for both
    // call sites below. `nonDestructive: true` (the _refresh path) must
    // not clear already-rendered content, so it uses the existing
    // App.showFlash overlay (admin.js:534 uses the same pattern for a
    // top-level list-fetch failure) instead of touching sectionContentEl.
    // The init path has nothing worth preserving yet, so it appends a
    // persistent `.admin-loading` line — the same class studio.js already
    // uses for section-level fetch failures (fetchMcpSources_ below),
    // already styled for `.area-studio` in
    // studio.css. Built via createElement/textContent (not innerHTML) per
    // tests/test_ui_guards.py's dynamic-sink freeze.
    function showLoadAllError(err, opts) {
      var reason = (err && err.message) ? err.message : 'unknown error';
      var msg = 'Unable to load Studio data — ' + reason + '.';
      if (opts && opts.nonDestructive) {
        App.showFlash(content, msg, true);
        return;
      }
      var bannerEl = document.createElement('div');
      bannerEl.className = 'admin-loading studio-loadall-error';
      bannerEl.setAttribute('role', 'alert');
      bannerEl.textContent = msg;
      sectionContentEl.appendChild(bannerEl);
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
        // Second instance of the header CTA component (M17 F3 leg 03 CTA
        // unification): same class + handler, NO data-testid — the unified
        // testid (new-agent-btn) lives uniquely on the always-visible
        // header CTA so strict-mode locators never double-match.
        var emptyBtn = document.createElement('button');
        emptyBtn.type = 'button';
        emptyBtn.className = 'btn-outlined-primary empty-canvas-cta';
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
      // Squawk 0090: the object seated here is the LIST-route cache, which
      // may predate a knowledge-base rename. Block Save until the
      // fresh-agent fetch below resolves and says otherwise, so a save
      // racing the in-flight refresh can't union from it either.
      self._selectedAgentLoaded = false;
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
      // a manual page reload. F6 L3 (L3-D1, L3-D3) adds two more: the
      // knowledge-base list refresh (mirrors the MCP one), and a fresh
      // fetch of THIS agent — needed because `loadAll()` does not re-run
      // on a Studio section switch, so after a rename performed in the
      // Knowledge section the cached `agent` object here can still hold a
      // pre-rewrite `disabled_tools` entry (collectFormData's ungated-
      // prefix union below reads from `self._selectedAgent`, so it must be
      // current). L3-D7: the fresh-agent fetch carries its own `.catch`
      // that resolves with the passed-in `agent` — this `Promise.all` has
      // no rejection handler anywhere in its chain, so a rejecting member
      // would strand the editor with nothing rendered, which is a worse
      // failure than re-rendering from a stale agent.
      //
      // Squawk 0090: rendering from the stale agent stays (that is the
      // L3-D7 trade-off, and `renderEditor(freshAgent)` below renders the
      // very object the union would read, so the UI remains
      // self-consistent) — what does NOT stay is saving from it. The
      // `.catch` records the failure in `freshAgentLoaded`, which becomes
      // `self._selectedAgentLoaded`; `renderEditor` then shows the
      // load-failure affordance and `checkDirty`/`save` keep Save
      // disabled. Refusing the save is the fix rather than DD-4's
      // omit-the-field shape because `disabled_tools` has NO server-side
      // preserve-on-omit path (`update_agent` preserves only
      // `mcp_overrides`, `self_revision_requires_approval` and `kb_ids`;
      // `AgentConfig.disabled_tools` defaults to `[]`), so omitting it
      // would WIPE every disabled tool — a strictly worse fail-open.
      var freshAgentLoaded = true;
      Promise.all([
        refreshToolConfigsCache(),
        refreshMcpSourcesCache(),
        refreshKnowledgeBasesCache(),
        fetch('/api/agents/' + encodeURIComponent(agent.name))
          .then(function (r) {
            if (!r.ok) throw new Error('fetch fresh agent: HTTP ' + r.status);
            return r.json();
          })
          .catch(function () {
            freshAgentLoaded = false;
            return agent;
          })
      ]).then(function (results) {
        // L3-D3: the fetch is not enough on its own — reassign
        // self._selectedAgent (and the matching self._agents entry) and
        // render the FETCHED object, not the outer closure's `agent`, or
        // the union below silently keeps reading stale disabled_tools.
        var freshAgent = results[3];
        self._selectedAgent = freshAgent;
        self._selectedAgentLoaded = freshAgentLoaded;
        for (var fi = 0; fi < self._agents.length; fi++) {
          if (self._agents[fi].name === freshAgent.name) { self._agents[fi] = freshAgent; break; }
        }
        renderEditor(freshAgent);
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
      // Squawk 0090: create-mode has no stored agent to union from
      // (`_storedUngatedDisabledNames` returns `[]` — AC-9), so there is
      // nothing stale to guard against; Create must stay enabled.
      self._selectedAgentLoaded = true;
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
      // a manual page reload. F6 L3 (L3-D3): the fresh-agent refetch is
      // select-path only — create mode has no agent to fetch — but the
      // knowledge-base refresh goes into both sites.
      Promise.all([refreshToolConfigsCache(), refreshMcpSourcesCache(), refreshKnowledgeBasesCache()]).then(function () {
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
        onPurge: handlePurgeHistory,
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
        // F6 L3 — knowledge-base list + the L3-D1 load-success flag for
        // the Knowledge tab. Both are refreshed at editor-mount time (see
        // selectAgent / doSelect / doEnterCreateMode above).
        allKnowledgeBases: self._allKnowledgeBases,
        knowledgeBasesLoaded: self._knowledgeBasesLoaded === true,
        // F8 L3 — MCP source list + per-source tools fetcher for MCPs tab.
        allMcpSources: self._allMcpSources,
        fetchMcpSourceTools: fetchMcpSourceTools,
        pendingMcpAgentSourceId: self._pendingMcpAgentSourceId || null,
        // Callback so renderMcpsTab can notify studio.js when the selected
        // source changes (chip click → per-attachment editor). studio.js
        // updates _selectedMcpAgentSourceId and syncs the URL.
        onSelectedMcpSourceChange: function (sourceId) {
          self._selectedMcpAgentSourceId = sourceId;
          writeUrl_();
        },
        // M21 F01 L02 — Self-configuration tab network calls.
        fetchSelfConfigurationStatus: fetchSelfConfigurationStatus,
        onEnableSelfConfiguration: enableSelfConfiguration,
        onDisableSelfConfiguration: disableSelfConfiguration,
        // M21 F02 L02 — approval-mode toggle + revision queue.
        onSetSelfConfigurationApprovalMode: setSelfConfigurationApprovalMode,
        fetchSelfConfigurationRevisions: fetchSelfConfigurationRevisions,
        fetchSelfConfigurationPendingCount: fetchSelfConfigurationPendingCount,
        onApproveSelfConfigurationRevision: approveSelfConfigurationRevision,
        onDismissSelfConfigurationRevision: dismissSelfConfigurationRevision,
        // M21 F02 L03 — revision history restore.
        onRestoreSelfConfigurationRevision: restoreSelfConfigurationRevision,
        // M21 F03 L03 — external-client credential grant/list/revoke/rotate.
        onMintExternalCredential: mintExternalCredential,
        fetchExternalCredentials: fetchExternalCredentials,
        onRevokeExternalCredential: revokeExternalCredential,
        onRotateExternalCredential: rotateExternalCredential
      });

      // Squawk 0090 — the load-failure affordance, mirroring the sibling
      // `agent-knowledge-load-error` (knowledge-tab.js, DD-4/L3-D1): say
      // plainly that this editor is showing a possibly-stale copy and that
      // saving is off until it reloads. Built with createElement +
      // textContent (no innerHTML) so `tests/test_ui_guards.py`'s
      // dynamic-sink baseline is untouched.
      if (!isCreate && self._selectedAgentLoaded === false) {
        var loadErrEl = document.createElement('div');
        loadErrEl.className = 'agent-load-error';
        loadErrEl.setAttribute('data-testid', 'agent-load-error');
        loadErrEl.setAttribute('role', 'status');
        loadErrEl.textContent =
          'Couldn’t load this agent’s current configuration. The fields below may be ' +
          'out of date, so saving is disabled. Go back and reopen the agent to retry.';
        var headerEl = editorEl.querySelector('.editor-header');
        if (headerEl && headerEl.parentNode) {
          headerEl.parentNode.insertBefore(loadErrEl, headerEl.nextSibling);
        } else {
          editorEl.insertBefore(loadErrEl, editorEl.firstChild);
        }
      }

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
      self._selectedAgentLoaded = true;  // squawk 0090: nothing selected, nothing stale
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

    // Purge chat history (M13 F2 leg 02). Mirrors handleDeleteEditor's
    // two-step App.confirmDelete arm-then-fire, but DELETEs the agent's chat
    // SESSIONS (not the agent) and KEEPS the agent selected — no
    // loadAll()/selectAgent/renderEmptyEditor. On success the deleted count is
    // flashed in place; on transport failure the armed button reverts and an
    // error flash shows. Reads self._selectedAgent.name (like
    // handleDeleteEditor), not the button's data-name.
    function handlePurgeHistory(purgeBtn) {
      var name = self._selectedAgent ? self._selectedAgent.name : null;
      if (!name) return;
      App.confirmDelete(purgeBtn, function (btn, revertFn) {
        fetch('/api/agents/' + encodeURIComponent(name) + '/chat/sessions', { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Purge failed'); });
            return r.json();
          })
          .then(function (body) {
            var n = body && typeof body.deleted === 'number' ? body.deleted : 0;
            App.showFlash(editorEl, 'Purged ' + n + ' conversation' + (n === 1 ? '' : 's'), false);
          })
          .catch(function (err) {
            revertFn();
            App.showFlash(editorEl, (err && err.message) || 'Purge failed', true);
          });
      }, { confirmLabel: 'Confirm Purge?' });
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
      // Squawk 0090: Save additionally stays disabled while the editor is
      // rendering a NOT-freshly-loaded agent — `collectFormData`'s
      // ungated-prefix union reads `self._selectedAgent`, and a stale one
      // would re-emit a pre-rename `kb__…__search` entry. Cancel is
      // deliberately NOT gated: discarding edits is always safe.
      var saveBlocked = !self._createMode && self._selectedAgentLoaded === false;
      var saveBtn = editorEl.querySelector('.save-btn');
      if (saveBtn) saveBtn.disabled = !dirty || saveBlocked;
      var cancelBtn = editorEl.querySelector('.cancel-btn');
      if (cancelBtn) cancelBtn.disabled = !dirty;
    }

    // F6 L3 (L3-D3, DD-13) — the ungated-prefix `disabled_tools` union.
    // `collectFormData`'s tool-toggle walk below only ever sees BUILT-IN
    // tool checkboxes (the Tools tab renders built-in categories only), so
    // an ungated-prefix entry set through the API (see the prefix list
    // below) would otherwise be erased by any unrelated Studio save.
    // Reads `self._selectedAgent`
    // — refreshed on every agent-edit mount by doSelect's fresh-agent
    // fetch (L3-D3) — never the stale outer closure or `self._agents`
    // cache, so a rename performed earlier in the session doesn't put a
    // pre-rewrite entry straight back. `self._selectedAgent` is `null` in
    // create-mode (AC-9): a new agent has no stored entries, so this
    // returns `[]` rather than crashing Save.
    var UNGATED_TOOL_PREFIXES = ['mcp__', 'kb__'];
    function _storedUngatedDisabledNames() {
      var stored = (self._selectedAgent && self._selectedAgent.disabled_tools) || [];
      var result = [];
      for (var s = 0; s < stored.length; s++) {
        for (var p = 0; p < UNGATED_TOOL_PREFIXES.length; p++) {
          if (stored[s].indexOf(UNGATED_TOOL_PREFIXES[p]) === 0) {
            result.push(stored[s]);
            break;
          }
        }
      }
      return result;
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
        } else if (key === 'chat_history_retention_days') {
          // DD6: preserve the raw parsed value — only NaN (empty/non-numeric)
          // falls back to the 30-day default. A typed out-of-range value (e.g.
          // 0 or 400) is forwarded verbatim so the server's validation rejects
          // it with a 422 that surfaces at the UI, rather than being silently
          // clamped to the default client-side. (Contract relied on by the
          // agent-retention-setting-roundtrip behavior-test lower-bound variant.)
          var n = parseInt(f.value, 10);
          data[key] = Number.isNaN(n) ? 30 : n;
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

      // F6 L3 (L3-D3, DD-13): every branch appends the stored ungated-
      // prefix entries AFTER the built-in names, in their original stored
      // order — a Set or object-key walk would make the Save button
      // flicker, since this value feeds dirty-tracking via getFormSnapshot.
      if (allOn) {
        data.enabled_tools = null;
        data.disabled_tools = [].concat(_storedUngatedDisabledNames());
      } else if (enabledNames.length <= disabledNames.length) {
        // enabled_tools is a BUILT-IN-only whitelist by backend contract
        // (AgentConfig.is_tool_enabled, F09-08): the backend does not gate
        // `mcp__`-prefixed MCP tools by this list — MCP is governed by
        // mcp_overrides. Do NOT inject `mcp__` names here; that would
        // reintroduce the coupling that silently stripped MCP tools.
        data.enabled_tools = enabledNames;
        data.disabled_tools = [].concat(_storedUngatedDisabledNames());
      } else {
        data.enabled_tools = null;
        data.disabled_tools = disabledNames.concat(_storedUngatedDisabledNames());
      }

      // Connections (chips) — Tools tab does not currently render chips
      // (MCP attach is a tool-row toggle, not a chip; see F8 L4 note
      // below). The override chip-list editors carry
      // data-tool-override-tool (NOT data-type), so they don't match the
      // [data-type] selector here and are picked up below in the override
      // walk.
      // F8 L4 — MCPs tab uses tool-row toggles instead of chip-area.
      // Walk the new [data-mcp-source-toggle]:checked selector to collect
      // attached source IDs.
      var mcpToggles = editorEl.querySelectorAll('[data-mcp-source-toggle][data-mcp-source-id]');
      data.mcp_source_ids = [];
      for (var m = 0; m < mcpToggles.length; m++) {
        if (mcpToggles[m].checked) data.mcp_source_ids.push(mcpToggles[m].dataset.mcpSourceId);
      }

      // F6 L3 (DD-4, L3-D1): `kb_ids` is sent ONLY when the Knowledge
      // tab's root carries `data-kb-list-loaded="true"` — set by
      // knowledge-tab.js exclusively on a successful refresh. When the
      // marker is absent (load failed, or a save races an in-flight
      // refresh — Edge Case), `kb_ids` is omitted from the payload
      // entirely so the server-side preserve (Leg 2 AC-7) keeps the
      // stored value instead of squawk 0050's `kb_ids: []` wipe. A loaded
      // surface with zero checked rows still sends `[]` — a legitimate
      // "detach everything".
      var kbTabRoot = editorEl.querySelector('[data-testid="agent-knowledge-tab"][data-kb-list-loaded="true"]');
      if (kbTabRoot) {
        var kbToggles = editorEl.querySelectorAll('[data-kb-toggle][data-kb-id]:checked');
        data.kb_ids = [];
        for (var k = 0; k < kbToggles.length; k++) {
          data.kb_ids.push(kbToggles[k].dataset.kbId);
        }
      }

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
            if (!r.ok) return r.json().then(function (e) { throw new Error(extractApiError(e, 'Create failed')); });
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
        // Squawk 0090 — belt-and-braces behind the disabled Save button
        // (a keyboard/script-driven click, or a save that races the
        // in-flight fresh-agent fetch, still reaches here). Refuse rather
        // than PUT a body whose `disabled_tools` was unioned from a
        // possibly-pre-rename cached agent.
        if (self._selectedAgentLoaded === false) {
          if (errorEl) {
            errorEl.textContent =
              'Can’t save — this agent’s current configuration failed to load.';
          }
          return;
        }
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
                  throw new Error(extractApiError(e, 'Rename failed'));
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
            if (!r.ok) return r.json().then(function (e) { throw new Error(extractApiError(e, 'Save failed')); });
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
                // kb-studio-round-trip remediation FIX 2 (FINDING 7,
                // 2026-09-18): `loadAll()` repopulates `self._agents` from
                // the LIST route, which deliberately omits `kb_tool_names`
                // (L2-D5, to avoid an N+1 read on every page load) — so
                // `found` structurally cannot carry it. `updated` is the
                // PUT response, which DOES carry it (same single-agent
                // shape `GET /api/agents/{name}` returns). Merge it forward
                // rather than discarding it in favour of the list object,
                // or an attached row would regress to the unattached
                // placeholder immediately after every save.
                found.kb_tool_names = updated.kb_tool_names;
                self._selectedAgent = found;
                renderEditor(found);
                showFlash('Saved');
                // Rewrite the URL so refresh / back-button targets the
                // new agent name (the area's URL keys on
                // _selectedAgent.name; writeUrl_ re-serializes).
                if (typeof writeUrl_ === 'function') writeUrl_();
              } else if (self._agents.length > 0) {
                // Save→delete race (F1 debrief): a concurrent DELETE removed
                // this agent between the PUT resolving and loadAll(). Without
                // this fallback the block silently no-ops, stranding a stale
                // editor for a now-gone agent. Fall to the first agent (parity
                // with handleDeleteEditor / _refresh).
                selectAgent(self._agents[0]);
              } else {
                self._selectedAgent = null;
                renderEmptyEditor();
                updateContentVisibility();
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

    // Extract a human-readable error message from a FastAPI response body.
    // e        - the parsed JSON response body
    // fallback - returned when no usable message can be derived
    //
    // FastAPI 422 bodies have e.detail as a Pydantic validation array:
    //   [{ loc: [..., "field"], msg: "Input should be ..." }, ...]
    // Single-string details (e.g. 404, 409 custom errors) are passed through.
    function extractApiError(e, fallback) {
      if (!e || !e.detail) return fallback;
      if (typeof e.detail === 'string') return e.detail;
      if (Array.isArray(e.detail)) {
        var msgs = [];
        for (var i = 0; i < e.detail.length; i++) {
          var item = e.detail[i];
          var field = (item.loc && item.loc.length) ? item.loc[item.loc.length - 1] : null;
          msgs.push(field ? (field + ': ' + item.msg) : item.msg);
        }
        return msgs.join('; ') || fallback;
      }
      return fallback;
    }

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
      }).catch(function (err) {
        showLoadAllError(err, { nonDestructive: true });
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
    // `inEditor` predicate covers every editor mount context (agents,
    // mcp-sources, connectors, and — as of F6 L5 — knowledge).
    self._confirmLeaveImpl = function (proceed, abort) {
      var inEditor =
        (self._activeSection === 'agents' && self._selectedAgent) ||
        (self._activeSection === 'mcp-sources' && mcpSourceFormMode) ||
        (self._activeSection === 'connectors' && connectorFormMode) ||
        // F6 L5 (L5-D3): a reversal of Leg 3's stated non-goal — the
        // inventory's create/register forms stay OUT of this gate
        // (single-field, submit-immediately), but the detail view's
        // Name+Description edit form (L5-D2) is multi-field with an
        // explicit Save, the exact shape this dialog exists for. `dirty`
        // can only become true while a detail view is mounted (the grid
        // has no edit form), so gating on `self._selectedKbId` alone
        // mirrors the `mcpSourceFormMode`/`connectorFormMode` shape above
        // without needing a parallel "form open" flag.
        (self._activeSection === 'knowledge' && self._selectedKbId);
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
        // Guard: if the user entered create mode or selected an agent while
        // loadAll was still in flight (e.g. slow fetchProviderModelCaps on a
        // live Ollama instance), don't clobber the editor they are already in.
        // The editor is already correctly rendered and visible from the
        // doEnterCreateMode / doSelect Promise.all.then() path.
        if (self._createMode || self._selectedAgent) return;
        // Bare #studio/agents shows the tile grid in the main panel; no
        // agent is auto-selected. The user picks a tile (or +) to enter
        // the editor.
        renderEmptyEditor();
        updateContentVisibility();
      }
    }).catch(function (err) {
      showLoadAllError(err);
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
  // Flight 6 leg 1 (L1-D2 site 2): app.js's performCrossAreaSwitch calls
  // this on EVERY cross-area transition. Without it, opening a Knowledge
  // detail view and clicking e.g. Chat leaves the 5-second poll running
  // for the life of the page — this is the first Studio section to need a
  // real body here; every prior section issues one-shot fetches, not
  // intervals. Note the beforeunload listener registered inside init()
  // is NOT touched here — the in-file warning at its registration site
  // forbids removing that listener in deactivate(), not giving
  // deactivate() a body.
  deactivate: function () {
    if (this._knowledgePollTimer) {
      clearInterval(this._knowledgePollTimer);
      this._knowledgePollTimer = null;
    }
  }
});
