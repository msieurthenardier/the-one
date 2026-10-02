App.registerArea({
  id: 'studio',
  label: 'Agent Studio',
  icon: App.icons.studio,
  order: 20,

  // ── Hash-routing serialize/hydrate ──────────────────────────────────
  //
  // serializeState branch order (explicit):
  //   1. _activeSection === 'knowledge' → 'knowledge/new' (the create form,
  //      checked FIRST; M25 F3 L4a) | 'knowledge/{kb_id}' | 'knowledge'
  //      (Flight 6 leg 1, L1-D1 — mirrors the mcp-sources deep-link shape)
  //   2. _activeSection === 'connectors' → 'connectors/new' | 'connectors/<id>'
  //      | 'connectors' (M25 F3 L4a, DD8: connector URLs, MCP's pending shape)
  //   3. _activeSection === 'mcp-sources' → 'mcp-sources' | 'mcp-sources/new'
  //      | 'mcp-sources/<id>' (post-F2 retrofit; relocated from admin)
  //   4. _activeSection === 'agents' && createMode → 'agents/~new' (M25 F3
  //      L3, DD8: the create route; checked before the pending/selected agent)
  //   5. _activeSection === 'agents' && agent pending or selected →
  //      'agents/<encoded-name>/<tab>'   (F5 leg 03 — appended /{tab})
  //   6. otherwise (no agent) → 'agents'
  //
  // Agent-name segments go through agentSeg: encodeURIComponent leaves `~`
  // alone, so a leading `~` is written as `%7E` -- an agent named `~new` must
  // never serialise to the create sub.
  //
  // F5 leg 03 extends branch 3 by appending the active tab segment so the
  // URL reflects the editor's tab state. Defaults to 'general'. The F3
  // router's serialize-after-hydrate path performs the
  // #studio/agents/{name} → #studio/agents/{name}/general upgrade for free
  // (no new redirect logic in studio.js).
  serializeState: function () {
    function agentSeg(name) {
      var enc = encodeURIComponent(name);
      return enc.charAt(0) === '~' ? '%7E' + enc.slice(1) : enc;
    }
    if (this._activeSection === 'knowledge') {
      if (this._kbCreateMode) return 'knowledge/new';
      if (this._selectedKbId) return 'knowledge/' + encodeURIComponent(this._selectedKbId);
      return 'knowledge';
    }
    // M25 F3 L4a (DD8): connectors are deep-link-aware, on the mcp-sources
    // pattern below (Mission 23 Flight 2's URL-less DD-9 trade-off is gone).
    if (this._activeSection === 'connectors') {
      if (this._connectorFormMode === 'add') return 'connectors/new';
      if (this._connectorFormMode === 'edit' && this._editingConnector) {
        return 'connectors/' + encodeURIComponent(this._editingConnector.id);
      }
      // Hydrate-vs-fetch race: the pending id survives until it resolves, so
      // a cold deep link is never synced to the section root early.
      if (this._pendingConnectorFormMode === 'add') return 'connectors/new';
      if (this._pendingConnectorId) {
        return 'connectors/' + encodeURIComponent(this._pendingConnectorId);
      }
      return 'connectors';
    }
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
    // The create form (DD8). An agent hydrate closes it (hydrateState), so it
    // never coexists with a pending selection.
    if (this._activeSection === 'agents' && this._createMode) return 'agents/~new';
    // A pending selection wins over the agent currently open: an item hydrate
    // (go(), traversal, typed hash) names the target BEFORE doSelect seats it,
    // and a fresh hydrate resolves it only after the list fetch, so the open
    // agent must not overwrite the URL that was just written.
    if (this._activeSection === 'agents' && this._pendingSelectName) {
      return 'agents/' + agentSeg(this._pendingSelectName) +
        '/' + (this._activeTab || 'general') +
        (this._activeTab === 'mcps' && this._pendingMcpAgentSourceId
          ? '/' + encodeURIComponent(this._pendingMcpAgentSourceId) : '');
    }
    if (this._activeSection === 'agents' && this._selectedAgent) {
      var base = 'agents/' + agentSeg(this._selectedAgent.name) +
        '/' + (this._activeTab || 'general');
      // F8 L3 Patch B — when on the MCPs tab AND a source-id is selected,
      // append it so refresh preserves the per-attachment editor view.
      if (this._activeTab === 'mcps' && this._selectedMcpAgentSourceId) {
        return base + '/' + encodeURIComponent(this._selectedMcpAgentSourceId);
      }
      return base;
    }
    return 'agents';
  },

  // hydrateState parses sub and drives the area to exactly that sub. It is
  // called by the router (App.router, commit-sequence step 7) with the AREA-level
  // sub of the destination being shown: `agents[/...]` (Agents destination) or
  // `knowledge|mcp-sources|connectors[/...]` (Library). After hydrate returns,
  // the router calls serializeState and `sync`s the URL (idempotent), so
  // hydrate MUST NOT write the URL itself -- hence {writeUrl: false}.
  //
  // Section-root subs ('agents', 'knowledge', 'mcp-sources', 'connectors')
  // render EXACTLY the root: any open item or create form is closed
  // (closeOpenItem). Item subs open the item through the pending-* paths.
  // M25 F3 L4a: 'knowledge/new' (the knowledge-base create form) and
  // 'connectors/new' | 'connectors/{id}' (connector URLs, on the MCP pending
  // shape) join 'mcp-sources/new' | 'mcp-sources/{id}'; each `new` sub is
  // matched before its item prefix. Every Library hydrate ends with the list
  // pane's selection sync (DD3 (c)).
  //
  // M25 F2 L3 (a): the previous section is captured BEFORE the section
  // changes and passed to _setActiveSection, which owns the outgoing-section
  // cleanup. hydrateState used to assign `_activeSection` itself, so inside
  // _setActiveSection prevSection always equalled section on this path and the
  // cleanup never ran -- the root of the Agents/Library leak.
  //
  // M25 F3 L3 (DD8): 'agents/~new' is the create route, compared RAW before
  // any decode (a name's leading `~` arrives as %7E). It closes the open item
  // unless the create form is already open, which is re-entered without a
  // re-render (a repeated "New" only refocuses the name field). An agent sub
  // closes an open create form (the router's guard has already asked).
  // Every Agents hydrate ends with the list-pane selection sync (DD3 (c)).
  //
  // F5 leg 03: extended to parse 'agents/<name>/<tab>'. Four cases:
  //   - 'agents/{name}'         → activeTab='general' (router rewrites URL)
  //   - 'agents/{name}/'        → activeTab='general' (defensive trailing-slash)
  //   - 'agents/{name}/general|knowledge|mcps|tools' → use that tab
  //   - 'agents/{name}/<other>' → defensively default to 'general'
  // Encoding note: agent names with literal '/' are encoded as '%2F' by
  // encodeURIComponent, so rest.indexOf('/') unambiguously finds the segment
  // separator.
  hydrateState: function (sub, opts) {
    // `fresh` is the router's hydrate ORIGIN (M25 F2 L4): true for a traversal,
    // a typed hash and boot -- an item named by the URL may have been deleted
    // since, so it is resolved against a FRESH fetch (a dead id heals to the
    // section root); false for an intent go() -- the cached list the user just
    // clicked in is used, nothing is refetched and the section root is not
    // re-rendered.
    var fresh = !!(opts && opts.fresh);
    var section = 'agents';
    var prev = this._activeSection;
    var pendingMcpAgentSourceId = null;
    var pending = null;
    var pendingTab = 'general';
    var pendingMcpSourceId_local = null;
    var pendingMcpSourceFormMode_local = null;
    var pendingConnectorId_local = null;
    var pendingConnectorFormMode_local = null;
    var createRoute = false;
    var kbCreateRoute = false;
    var kbCreateWasOpen = false;
    var closeOpenItem = this._closeOpenItem || function () {};
    // The first id segment of an item sub ('<section>/<id>[/...]'), decoded.
    function firstSeg(rest) {
      if (rest.charAt(rest.length - 1) === '/') rest = rest.slice(0, -1);
      var idx = rest.indexOf('/');
      if (idx !== -1) rest = rest.slice(0, idx);
      return rest ? decodeURIComponent(rest) : null;
    }
    if (sub === 'knowledge') {
      section = 'knowledge';
      closeOpenItem();
    } else if (sub === 'knowledge/new') {
      // The create form (M25 F3 L4a, DD8), matched BEFORE the item prefix so
      // it never reads as a knowledge base whose id is "new". It closes the
      // open item unless the create form is already open (a repeated Add only
      // refocuses it); the flag is set before the section renders, so the
      // form is what renders.
      section = 'knowledge';
      kbCreateRoute = true;
      kbCreateWasOpen = prev === 'knowledge' && !!this._kbCreateMode;
      if (!kbCreateWasOpen) closeOpenItem();
      this._kbCreateMode = true;
    } else if (sub && sub.indexOf('knowledge/') === 0) {
      // Flight 6 leg 1 (L1-D1): direct-load on knowledge/{kb_id} — parse
      // the id so the detail view opens on refresh, mirroring the
      // mcp-sources/{id} parsing immediately below.
      section = 'knowledge';
      // An item closes an open create form (the router's guard has asked).
      if (this._kbCreateMode) closeOpenItem();
      this._kbFresh = fresh;  // read once by renderKnowledgeDetailView
      this._selectedKbId = firstSeg(sub.slice('knowledge/'.length));
    } else if (sub === 'connectors') {
      section = 'connectors';
      closeOpenItem();
    } else if (sub === 'connectors/new') {
      // Matched BEFORE the item prefix (M25 F3 L4a, DD8).
      section = 'connectors';
      pendingConnectorFormMode_local = 'add';
    } else if (sub && sub.indexOf('connectors/') === 0) {
      section = 'connectors';
      pendingConnectorFormMode_local = 'edit';
      pendingConnectorId_local = firstSeg(sub.slice('connectors/'.length));
    } else if (sub === 'mcp-sources') {
      section = 'mcp-sources';
      closeOpenItem();
    } else if (sub === 'mcp-sources/new') {
      section = 'mcp-sources';
      pendingMcpSourceFormMode_local = 'add';
    } else if (sub && sub.indexOf('mcp-sources/') === 0) {
      // Direct-load on mcp-sources/{id}: parse the source id so the editor
      // opens on refresh. Mirrors admin.js's L5 parsing pattern (now
      // relocated to studio post-F2 retrofit).
      section = 'mcp-sources';
      pendingMcpSourceFormMode_local = 'edit';
      // Defensive: if extra path segments, take only the first.
      pendingMcpSourceId_local = firstSeg(sub.slice('mcp-sources/'.length));
    } else if (sub === 'agents/~new') {
      section = 'agents';
      createRoute = true;
      if (!(prev === 'agents' && this._createMode)) closeOpenItem();
      this._pendingSelectName = null;
      this._pendingTabName = null;
    } else if (sub && sub.indexOf('agents/') === 0) {
      section = 'agents';
      if (this._createMode) closeOpenItem();
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
        if (tab.indexOf('mcps/') === 0) {
          pendingMcpAgentSourceId = decodeURIComponent(tab.slice('mcps/'.length));
          tab = 'mcps';
        }
        if (tab === 'general' || tab === 'knowledge' || tab === 'mcps' || tab === 'tools' || tab === 'self-configuration') {
          pendingTab = tab;
        } else {
          pendingTab = 'general';
        }
      }
    } else if (sub === 'agents' || !sub) {
      section = 'agents';
      // Section root: the empty detail state -- close any open editor or create form
      // and drop a stale pending selection (a hydrate-before-loadAll target
      // would otherwise re-open its agent when the list arrives).
      closeOpenItem();
      this._pendingSelectName = null;
      this._pendingTabName = null;
      pendingTab = 'general';
    } else {
      // Defensive: unrecognized sub defaults to 'agents'. Do NOT throw.
      section = 'agents';
    }
    this._activeTab = pendingTab;
    if (pending) {
      this._pendingSelectName = pending;
      this._pendingTabName = pendingTab;
    } else if (section !== 'agents') {
      this._pendingSelectName = null;
      this._pendingTabName = null;
    }
    // Always overwrite pending MCP and connector state (including with nulls
    // when sub is not mcp-sources/... or connectors/...) so navigation away
    // clears stale pending.
    this._pendingMcpSourceId = pendingMcpSourceId_local;
    this._pendingMcpSourceFormMode = pendingMcpSourceFormMode_local;
    this._pendingConnectorId = pendingConnectorId_local;
    this._pendingConnectorFormMode = pendingConnectorFormMode_local;
    // The MCPs tab's source focus: the URL's value (or none) replaces the
    // previous one, so `#agents/x/mcps/s2` while on s1 focuses s2.
    this._pendingMcpAgentSourceId = pendingMcpAgentSourceId;
    this._selectedMcpAgentSourceId = pendingMcpAgentSourceId;

    // Item subs inside the section that is already showing do not re-render the
    // section root (no flash, no list refetch): the consume paths below render
    // the item themselves. MCP and connectors share one rule (M25 F3 L4a): a
    // fresh hydrate closes the open form, then resolves the pending id against
    // a FRESH list; an intent consumes it from the cached list, and on a miss
    // (a cold cache) the open form is closed too, so the section never
    // re-renders the OLD item while the new one resolves.
    var skipSectionRender = false;
    if (prev === section) {
      if (pending || (createRoute && this._createMode) || kbCreateWasOpen) {
        skipSectionRender = true;
      } else if (section === 'mcp-sources' && pendingMcpSourceFormMode_local) {
        if (!fresh && this._tryConsumePendingMcpSource) {
          skipSectionRender = this._tryConsumePendingMcpSource(true);
        }
        if (!skipSectionRender && this._closeMcpForm) this._closeMcpForm();
      } else if (section === 'connectors' && pendingConnectorFormMode_local) {
        if (!fresh && this._tryConsumePendingConnector) {
          skipSectionRender = this._tryConsumePendingConnector(true);
        }
        if (!skipSectionRender && this._closeConnectorForm) this._closeConnectorForm();
      }
    }
    // The section change (and the outgoing section's cleanup) happens HERE,
    // before the pending agent is consumed: doSelect requires the Agents
    // section to be active.
    if (!skipSectionRender && this._setActiveSection) {
      this._setActiveSection(section, { writeUrl: false, prev: prev });
    }
    if (pending && this._tryConsumePendingSelect) this._tryConsumePendingSelect(fresh);
    if (createRoute && this._enterCreate) this._enterCreate();
    if (kbCreateRoute && this._focusKbCreate) this._focusKbCreate();
    if (section === 'agents' && this._syncAgentSelection) this._syncAgentSelection();
    // The pending-item rule (M25 F3 L4a), MCP and connectors alike: a create
    // form needs no list and opens at once; an existing item is taken from the
    // cached list for an intent (else on the next store notification, never
    // healed), and resolved against a FORCED fetch for a fresh hydrate (a dead
    // id heals to the section root).
    if (this._resolvePendingLibraryItems) this._resolvePendingLibraryItems(fresh);
    // DD3 (c): the Library list's selection follows the hydrate; a section
    // root scrolls its group into view, an item its row.
    if (section !== 'agents' && this._syncLibrarySelection) this._syncLibrarySelection(true);
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
    // init() always runs first — app.js mounts the area before the router hydrates it).
    self._selectedKbId = self._selectedKbId || null;
    self._knowledgePollTimer = null;
    var dirty = false;
    var snapshot = '';
    // Tab handle returned by App.studio.renderAgentEditor — used for
    // imperative activate(tabId) calls after hydrate.
    var tabHandle = null;
    // Monotonic token: an in-flight doSelect completes only while it is still
    // the latest select AND the user is still on Agents (closeOpenItem and the
    // outgoing-section cleanup bump it).
    var selectSeq = 0;
    // Discard generation (M25 F2 L5): closeOpenItem bumps it; async editor resolvers
    // (saves, type waits) captured under an older one must not resurrect state.
    var editorGen = 0;

    // ── MCP Sources state (post-F2 retrofit; relocated from admin.js) ───
    // The MCP Servers section was originally an admin.js sub-section
    // (M07 F1 L5/L6); moved here post-F2 retrofit because MCP sources are
    // user-managed entities, not system settings. State shape mirrors the
    // admin pattern: type list cached at init, the source list from the store
    // (the Library list's section cache, M25 F3 L4a), formMode +
    // editingMcpSource drive editor-vs-section-root dispatch, pending* slots
    // handle the hydrate-vs-fetch race.
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

    // ── Connectors state (Mission 23 Flight 2 Leg 2; M25 F3 L4a) ─────────
    // The MCP-sources shape above (M25 F3 L4a, DD8: connector URLs): formMode
    // + editingConnector drive the editor, the pending pair handles the
    // hydrate-vs-fetch race, all exposed for serializeState.
    var CONNECTOR_TYPES = [];
    var connectorTypesReady = null;
    var connectors = null; // the section cache (store-fed); null until first load
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

    // ── Knowledge-base create form (M25 F3 L4a, DD8; squawk 0101) ───────
    // `knowledge/new` (the route's `~new`): a create form in the detail pane.
    var kbCreateMode = !!self._kbCreateMode;
    Object.defineProperty(self, '_kbCreateMode', {
      get: function () { return kbCreateMode; },
      set: function (v) { kbCreateMode = !!v; },
      configurable: true
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

    // ── Layout: the sidebar panel holds two sibling list hosts, exactly one
    // visible (setActiveSection owns the switch, M25 F3 L3/L4a, DD3 (e)): the
    // Agents list column (.studio-agents-list) and the Library list column
    // (.studio-library-list), each an App.ui.listPane created on entering its
    // destination and destroyed on leaving it, so exactly one pane exists.
    // The main panel hosts the section-content (the Agents empty state, the
    // Library detail: an editor or an empty state) and the agent editor,
    // toggled via .is-hidden on whether an agent is being edited.
    sidebar.textContent = '';
    var agentsListHost = document.createElement('div');
    agentsListHost.className = 'studio-agents-list is-hidden';
    sidebar.appendChild(agentsListHost);
    var libraryListHost = document.createElement('div');
    libraryListHost.className = 'studio-library-list is-hidden';
    sidebar.appendChild(libraryListHost);
    var agentsList = null;      // the Agents App.ui.listPane while on Agents
    var newAgentBtn = null;     // its "New" title-row action
    var agentsEmptyEl = null;   // the detail pane's empty state (no agent open)
    var agentsEmptyKind = null; // 'some' | 'none' -- which copy agentsEmptyEl shows

    content.innerHTML =
      '<div class="studio-section-content"></div>' +
      '<div class="studio-editor"></div>';
    var sectionContentEl = content.querySelector('.studio-section-content');
    var editorEl = content.querySelector('.studio-editor');

    // ── The Library list column (M25 F3 L4a, DD5) ───────────────────────
    //
    // One grouped App.ui.listPane (Knowledge bases, MCP servers, Connectors)
    // with an Add menu; it replaces the Library section nav and the three
    // tile grids. Rows are links (`#library/{section}/{id}`), so App.nav
    // routes a row click through the router's leave guard.
    //
    // Data. The four store subscriptions (registered once, below loadAll)
    // live for the page: they always feed the section caches (knowledgeBases,
    // mcpSources, connectors -- which back find*, the pending consumes and
    // the knowledge detail's cache hit) and re-attempt pending consumes, and
    // they render the list only while the pane exists. Fetch policy (DD9's
    // freshness bound): pane creation force-gets the three collections and
    // plain-gets agents; studio activate on a Library section force-gets the
    // three; a move between Library sections fetches nothing; a mutation's
    // callback invalidates (the editor) and then reloadLibrary(name)s.
    var LIBRARY_GROUPS = [
      { id: 'knowledge', section: 'knowledge', route: 'knowledge', collection: 'knowledge-bases',
        label: 'Knowledge bases', emptyText: 'No knowledge bases yet.',
        failText: 'Couldn\u2019t load knowledge bases.', icon: 'database',
        testid: 'knowledge-base-card', prefix: 'knowledge:' },
      { id: 'mcp', section: 'mcp-sources', route: 'mcp', collection: 'mcp-sources',
        label: 'MCP servers', emptyText: 'No MCP servers yet.',
        failText: 'Couldn\u2019t load MCP servers.', icon: 'server',
        testid: 'mcp-source-card', prefix: 'mcp:' },
      { id: 'connectors', section: 'connectors', route: 'connectors', collection: 'connectors',
        label: 'Connectors', emptyText: 'No connectors yet.',
        failText: 'Couldn\u2019t load connectors.', icon: 'plug',
        testid: 'connector-card', prefix: 'connector:' }
    ];
    var LIBRARY_EMPTY = {
      knowledge: { title: 'Select a knowledge base, or add one.', add: 'Add knowledge base' },
      mcp: { title: 'Select an MCP server, or add one.', add: 'Add MCP server' },
      connectors: { title: 'Select a connector, or add one.', add: 'Add connector' }
    };
    var libraryList = null;     // the Library App.ui.listPane while on Library
    var libraryAddMenu = null;  // its title-row Add menu (App.ui.menu)
    var libraryRendered = false; // the gated first setItems has run
    var libraryPaneGen = 0;     // bumped on create/destroy: stale pane gets drop
    var libraryPaneSettled = {}; // collection -> this pane's get settled
    var libraryPaneFailed = {};  // collection -> this pane's get failed

    function isLibrarySection(section) {
      return section === 'knowledge' || section === 'mcp-sources' || section === 'connectors';
    }

    function libraryGroupFor(section) {
      for (var i = 0; i < LIBRARY_GROUPS.length; i++) {
        if (LIBRARY_GROUPS[i].section === section) return LIBRARY_GROUPS[i];
      }
      return null;
    }

    function libraryCache(collection) {
      if (collection === 'knowledge-bases') return knowledgeBases;
      if (collection === 'mcp-sources') return mcpSources;
      if (collection === 'connectors') return connectors;
      return null;
    }

    // Only syncLibraryCache and the lifetime subscriptions write the caches.
    function setLibraryCache(collection, list) {
      if (collection === 'knowledge-bases') knowledgeBases = list;
      else if (collection === 'mcp-sources') mcpSources = list;
      else if (collection === 'connectors') connectors = list;
    }

    // The section cache follows the STORE's value, never a request's own
    // result: the store drops a response whose request was invalidated
    // mid-flight (generation-safe), so a stale request resolving after a newer
    // one can never put a deleted row back.
    function syncLibraryCache(collection) {
      var held = App.store.peek(collection).value;
      if (held) setLibraryCache(collection, held);
    }

    function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

    // A collection is SETTLED once the store has ever loaded it or this pane's
    // own get has settled (either way). Until all three have, the list keeps
    // its "Loading library…" state, so no group flashes "No … yet." early.
    function libraryGateOpen() {
      for (var i = 0; i < LIBRARY_GROUPS.length; i++) {
        var name = LIBRARY_GROUPS[i].collection;
        if (!libraryPaneSettled[name] && !App.store.peek(name).loaded) return false;
      }
      return true;
    }

    // The row id the list marks selected: the open item, else a pending deep
    // link's id (so a cold deep link selects its row as soon as the list
    // loads); none at a section root or on a create form.
    function librarySelection() {
      var section = self._activeSection;
      if (section === 'knowledge') {
        return !kbCreateMode && self._selectedKbId ? 'knowledge:' + self._selectedKbId : null;
      }
      if (section === 'mcp-sources') {
        if (mcpSourceFormMode === 'add') return null;
        if (mcpSourceFormMode === 'edit' && editingMcpSource) return 'mcp:' + editingMcpSource.id;
        if (self._pendingMcpSourceFormMode === 'edit' && self._pendingMcpSourceId) {
          return 'mcp:' + self._pendingMcpSourceId;
        }
        return null;
      }
      if (section === 'connectors') {
        if (connectorFormMode === 'add') return null;
        if (connectorFormMode === 'edit' && editingConnector) return 'connector:' + editingConnector.id;
        if (pendingConnectorFormMode === 'edit' && pendingConnectorId) {
          return 'connector:' + pendingConnectorId;
        }
        return null;
      }
      return null;
    }

    // True at a section root: nothing open, nothing pending, no create form.
    function atLibraryRoot() {
      var section = self._activeSection;
      if (section === 'knowledge') return !kbCreateMode && !self._selectedKbId;
      if (section === 'mcp-sources') {
        return !mcpSourceFormMode && !self._pendingMcpSourceFormMode;
      }
      if (section === 'connectors') return !connectorFormMode && !pendingConnectorFormMode;
      return false;
    }

    // One row. The meta is a visible span inside the <a>, so it is part of the
    // accessible name; the type icon is aria-hidden. Agent counts appear only
    // once `agents` has loaded (never "0 agents" while loading). Until then a
    // row with nothing known keeps an empty meta line (a no-break space, which
    // the accessible name trims), so every Library row stays two lines (the
    // reference spec's 50px) and nothing shifts when the counts arrive -- a
    // shift would push a scrolled-in group back out of view.
    function libraryItem(group, row, agents) {
      var meta = [];
      if (group.id === 'mcp') {
        var tools = App.usage.mcpToolCount(row);
        meta.push(tools === null ? 'Tools not loaded' : plural(tools, 'tool', 'tools'));
      }
      if (agents) {
        var n = group.id === 'knowledge' ? App.usage.kbAgents(agents, row.id)
          : group.id === 'mcp' ? App.usage.mcpAgents(agents, row.id)
            : App.usage.connectorAgents(row).length;
        meta.push(plural(n, 'agent', 'agents'));
      }
      var item = {
        id: group.prefix + row.id,
        label: row.name,
        meta: meta.length ? meta.join(' \u00b7 ') : '\u00a0',
        icon: group.icon,
        href: App.router.href({ destination: 'library', section: group.route, id: row.id })
      };
      // The row testid is the group's literal (LIBRARY_GROUPS, where the
      // registry guard sees it): the grids' card testids are kept on the rows.
      item.testid = group.testid;
      return item;
    }

    function libraryGroup(group, agents) {
      var rows = libraryCache(group.collection);
      if (!rows) {
        return {
          id: group.id, label: group.label, items: [],
          emptyText: libraryPaneFailed[group.collection] ? group.failText : group.emptyText
        };
      }
      var sorted = rows.slice().sort(function (a, b) {
        return String(a.name).localeCompare(String(b.name));
      });
      var items = [];
      for (var i = 0; i < sorted.length; i++) items.push(libraryItem(group, sorted[i], agents));
      return { id: group.id, label: group.label, emptyText: group.emptyText, items: items };
    }

    // The one builder of the Library list (leg 3's pattern): setItems, then
    // the selection. A no-op off Library (no pane) and while the first load is
    // gated. `scroll` (a load or a navigation) brings the selected row -- or,
    // at a section root, the section's group -- into view; the gated first
    // fill does too. Store notifications pass nothing.
    function renderLibraryList(scroll) {
      if (!libraryList || !libraryGateOpen()) return;
      var first = !libraryRendered;
      var agentsPeek = App.store.peek('agents');
      var agents = agentsPeek.value || null;
      var groups = [];
      for (var i = 0; i < LIBRARY_GROUPS.length; i++) groups.push(libraryGroup(LIBRARY_GROUPS[i], agents));
      libraryList.setItems(groups);
      libraryRendered = true;
      libraryList.setSelected(librarySelection());
      if (scroll || first) scrollLibrary();
    }

    // The selected row into view (now, and once more when the web fonts are
    // ready: leg 3's cold-load reflow), else at a section root its group (the
    // same re-scroll).
    function scrollLibrary() {
      var pane = libraryList;
      if (!pane || !libraryRendered) return;
      if (librarySelection()) {
        pane.scrollToSelected();
        if (document.fonts && document.fonts.ready) {
          document.fonts.ready.then(function () {
            if (libraryList === pane && librarySelection()) pane.scrollToSelected();
          });
        }
        return;
      }
      if (atLibraryRoot()) {
        var group = libraryGroupFor(self._activeSection);
        if (!group) return;
        pane.scrollToGroup(group.id);
        if (document.fonts && document.fonts.ready) {
          document.fonts.ready.then(function () {
            if (libraryList === pane && atLibraryRoot() && libraryGroupFor(self._activeSection) === group) {
              pane.scrollToGroup(group.id);
            }
          });
        }
      }
    }

    // DD3 (c): re-sync the selection without rebuilding the rows; `scroll`
    // also scrolls (hydrateState passes it).
    function syncLibrarySelection(scroll) {
      if (!libraryList || !libraryRendered) return;
      libraryList.setSelected(librarySelection());
      if (scroll) scrollLibrary();
    }
    self._syncLibrarySelection = syncLibrarySelection;

    // Load the three Library collections for this pane (`force`: pane
    // creation, studio activate) and the agents list (a plain get: it reuses
    // the cache Agents loaded). A failed get with no last-good value marks its
    // group "Couldn't load"; one with a value keeps the stale rows.
    function loadLibrary(force) {
      var gen = libraryPaneGen;
      LIBRARY_GROUPS.forEach(function (group) {
        var name = group.collection;
        App.store.get(name, { force: !!force }).then(function () {
          syncLibraryCache(name);
          if (gen !== libraryPaneGen) return;
          libraryPaneSettled[name] = true;
          libraryPaneFailed[name] = false;
          renderLibraryList();
        }, function () {
          if (gen !== libraryPaneGen) return;
          libraryPaneSettled[name] = true;
          libraryPaneFailed[name] = true;
          renderLibraryList();
        });
      });
      App.store.get('agents').then(function () {
        if (gen === libraryPaneGen) renderLibraryList();
      }, function () { /* the counts stay off until agents load */ });
    }

    // After a mutation: the editor invalidated `name`, so this plain get
    // refetches (a warm, valid cache would resolve without notifying anyone,
    // which is why the list is rendered here as well). Always resolves.
    function reloadLibrary(name) {
      return App.store.get(name).then(function (list) {
        syncLibraryCache(name);
        renderLibraryList();
        return list;
      }, function () {
        renderLibraryList();
        return null;
      });
    }

    // "Add" -> a type: a go() to its `~new` (the router guard asks once about
    // a dirty editor). Choosing the create form that is already open only
    // refocuses its first field, dirty or not, and never runs a guarded go()
    // to the same route.
    function goLibraryCreate(route, opener) {
      var cur = App.router.current();
      var target = 'library/' + route + '/~new';
      if (cur && cur.route === target && libraryCreateOpen(route)) {
        focusLibraryCreate(route);
        return;
      }
      App.router.go(App.router.href({ destination: 'library', section: route, create: true }),
        { opener: opener || null });
    }

    function libraryCreateOpen(route) {
      if (route === 'knowledge') return self._activeSection === 'knowledge' && kbCreateMode;
      if (route === 'mcp') return self._activeSection === 'mcp-sources' && mcpSourceFormMode === 'add';
      if (route === 'connectors') return self._activeSection === 'connectors' && connectorFormMode === 'add';
      return false;
    }

    function focusLibraryCreate(route) {
      var sel = route === 'knowledge' ? '[data-testid="kb-create-name-input"]' : '[data-field="name"]';
      var field = sectionContentEl.querySelector(sel);
      if (field) field.focus();
    }

    function createLibraryList() {
      libraryPaneGen += 1;
      libraryPaneSettled = {};
      libraryPaneFailed = {};
      libraryRendered = false;
      // The subscriptions feed the caches from studio init on; a collection the
      // store loaded before that (another area's get) is seeded from peek, so an
      // open gate never renders an empty group over data the store holds.
      LIBRARY_GROUPS.forEach(function (group) {
        if (!libraryCache(group.collection)) syncLibraryCache(group.collection);
      });
      libraryAddMenu = App.ui.menu({
        trigger: { variant: 'secondary', size: 'sm', icon: 'plus', label: 'Add', testid: 'library-add-btn' },
        // The trigger sits at the right of the 300px aside, whose overflow is
        // hidden: the popup opens toward the start edge so it stays inside.
        align: 'end',
        items: [
          { label: 'Knowledge base', testid: 'library-add-knowledge',
            onSelect: function () { goLibraryCreate('knowledge', libraryAddMenu && libraryAddMenu.trigger); } },
          { label: 'MCP server', testid: 'library-add-mcp',
            onSelect: function () { goLibraryCreate('mcp', libraryAddMenu && libraryAddMenu.trigger); } },
          { label: 'Connector', testid: 'library-add-connector',
            onSelect: function () { goLibraryCreate('connectors', libraryAddMenu && libraryAddMenu.trigger); } }
        ]
      });
      libraryList = App.ui.listPane({
        title: 'Library',
        intro: 'Things agents can use. Attach them from an agent\u2019s Knowledge and MCPs tabs.',
        actions: [libraryAddMenu.el],
        // Shown only until the gated first fill (the groups' own empty lines
        // take over after it).
        emptyText: function () { return 'Loading library\u2026'; },
        rowStyle: 'library',
        testid: 'library-list'
      });
      libraryListHost.appendChild(libraryList.el);
      // A re-entry renders from the cache at once (the gate is open when every
      // collection has loaded before); the forced gets refresh it.
      renderLibraryList(true);
      loadLibrary(true);
    }

    function destroyLibraryList() {
      if (!libraryList) return;
      libraryPaneGen += 1;
      if (libraryAddMenu) libraryAddMenu.destroy();
      libraryList.destroy();
      libraryListHost.textContent = '';
      libraryList = null;
      libraryAddMenu = null;
      libraryRendered = false;
    }

    // The flat, visible-row index of the row `id` (list order, across groups),
    // read BEFORE a delete removes it.
    function libraryRowIndex(id) {
      if (!libraryList) return 0;
      var rows = libraryList.el.querySelectorAll('li > .ui-list-pane-row');
      var items = libraryList.getItems();
      var n = 0;
      for (var i = 0; i < items.length && i < rows.length; i++) {
        if (items[i].id === id) return n;
        if (!rows[i].parentNode.hidden) n++;
      }
      return n;
    }

    // DD8's focus rule after a delete: the row now at `index` (the next one
    // after the removed row, which may be in the next group), else the
    // previous one, else Add.
    function focusLibraryRowNear(index) {
      if (!libraryList) return;
      var rows = libraryList.el.querySelectorAll('li:not([hidden]) > .ui-list-pane-row');
      var target = rows.length ? rows[Math.max(0, Math.min(index, rows.length - 1))] : null;
      if (!target) {
        if (libraryAddMenu) libraryAddMenu.trigger.focus();
        return;
      }
      for (var i = 0; i < rows.length; i++) rows[i].setAttribute('tabindex', rows[i] === target ? '0' : '-1');
      target.focus();
    }

    // After a create-form Cancel: the first row of that section's group, else
    // Add (leg 3's focusAgentRowNear(0)).
    function focusLibraryGroupStart(section) {
      if (!libraryList) return;
      var group = libraryGroupFor(section);
      var first = null;
      var items = libraryList.getItems();
      var rows = libraryList.el.querySelectorAll('li > .ui-list-pane-row');
      for (var i = 0; i < items.length && i < rows.length; i++) {
        if (group && String(items[i].id).indexOf(group.prefix) === 0 && !rows[i].parentNode.hidden) {
          first = rows[i];
          break;
        }
      }
      if (!first) {
        if (libraryAddMenu) libraryAddMenu.trigger.focus();
        return;
      }
      var all = libraryList.el.querySelectorAll('li:not([hidden]) > .ui-list-pane-row');
      for (var k = 0; k < all.length; k++) all[k].setAttribute('tabindex', all[k] === first ? '0' : '-1');
      first.focus();
    }

    // The detail pane at a section root: a pane-size empty state whose action
    // opens that section's create form. Only built at a root (never while a
    // deep-link id is pending, so a cold item link never flashes it).
    function renderLibraryEmpty(section) {
      var group = libraryGroupFor(section);
      if (!group) return;
      var copy = LIBRARY_EMPTY[group.id];
      var action = App.ui.button({
        variant: 'secondary',
        icon: 'plus',
        label: copy.add,
        testid: 'library-empty-' + group.id + '-add',
        onClick: function (e) { goLibraryCreate(group.route, e && e.currentTarget); }
      });
      sectionContentEl.appendChild(App.ui.emptyState({
        title: copy.title,
        size: 'pane',
        headingLevel: 2,
        action: action,
        testid: 'library-empty-' + group.id
      }));
    }

    // The Agents section: the list column plus, in the detail pane, the empty
    // state shown while no agent is open (the editor host covers it
    // otherwise; updateContentVisibility).
    function renderAgentsSection() {
      sectionContentEl.innerHTML = '';
      agentsEmptyEl = null;
      agentsEmptyKind = null;
      renderAgentList(true);
    }

    // Knowledge section (Flight 6 leg 1, DD-2, L1-D1; M25 F3 L4a) — the
    // global knowledge-base inventory. Three-branch dispatch: the create form
    // (kbCreateMode), a detail view (self._selectedKbId set) and, at the
    // section root, the empty detail state beside the Library list,
    // hash-routed by serializeState/hydrateState above as 'knowledge/new' /
    // 'knowledge/{kb_id}' / 'knowledge'.
    var knowledgeBases = null; // the section cache (store-fed); null until first load
    var kbFocusFolderFor = null; // a just-created KB's id: focus its folder field on mount
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
    //
    // Flight 7 Leg 2 (DD-6): widened to fold in `status.content_freshness`
    // (the backend's MAX(indexed_at)-over-file-items aggregate) — WITHOUT
    // it, a content-only edit to an already-indexed file changes neither
    // the per-status counts nor the chunk count, so this signature never
    // moved and the `/items` re-fetch below never fired, even though the
    // freshness field the item row now renders (AC-1) had gone stale. Both
    // halves land in the same commit — DD-6's own reason: shipping the
    // render half alone would have converted an invisible blind spot into
    // a visible staleness bug.
    var lastKnownItemsSignature = null;

    function knowledgeItemsSignature(status) {
      return (
        JSON.stringify((status && status.items) || {}) +
        '|' + (status && status.chunks) +
        '|' + (status && status.content_freshness)
      );
    }

    function renderKnowledgeSection() {
      sectionContentEl.innerHTML = '';
      if (kbCreateMode) {
        clearKnowledgePoll();
        knowledgeDetailHandle = null;
        renderKnowledgeCreateView();
      } else if (self._selectedKbId) {
        renderKnowledgeDetailView(self._selectedKbId);
      } else {
        // L1-D2 site 3: leaving the detail view for the section root stops the
        // poll -- covered here since every root mount (direct nav, the
        // breadcrumb's group link, browser Back, delete) routes through this
        // branch.
        clearKnowledgePoll();
        knowledgeDetailHandle = null;
        renderLibraryEmpty('knowledge');
      }
      syncLibrarySelection(false);
    }

    // The create form (M25 F3 L4a, DD8; closes squawk 0101): `#library/
    // knowledge/~new` in the detail pane. Creating opens the new knowledge
    // base's detail view (a bypass go() REPLACING the create entry, after the
    // store reload, so the router names the new item); Cancel discards and
    // replaces to the section root.
    function renderKnowledgeCreateView() {
      dirty = false;
      var kbGen = editorGen;
      function stillOnCreate() {
        var cur = App.router.current();
        return kbGen === editorGen && kbCreateMode && !!cur &&
          cur.route === 'library/knowledge/' + '~new';
      }
      App.studio.renderKnowledgeCreate(sectionContentEl, {
        onDirtyChange: function (d) { if (kbGen === editorGen) dirty = d; },
        onCancel: function () {
          discardOpen_();
          App.router.go(App.router.href({ destination: 'library', section: 'knowledge' }),
            { replace: true, bypassGuard: true });
          focusLibraryGroupStart('knowledge');
        },
        // Called after the POST succeeded and the module invalidated
        // 'knowledge-bases'. Order (H1): clear `dirty` at once -- only while
        // the user is still on this form, since the flag is shared by every
        // studio editor -- then await the store reload (the row exists and the
        // router can name the new item), then, still on this form and with no
        // decision pending, replace ~new with the new item.
        onCreateSuccess: function (kb) {
          if (stillOnCreate()) dirty = false;
          var open = function () {
            if (!stillOnCreate() || App.router.isDeciding()) return;
            kbFocusFolderFor = kb.id;
            App.router.go(App.router.href({ destination: 'library', section: 'knowledge', id: kb.id }),
              { replace: true, bypassGuard: true });
          };
          reloadLibrary('knowledge-bases').then(open, open);
        }
      });
    }

    self._focusKbCreate = function () { focusLibraryCreate('knowledge'); };

    function findKnowledgeBase(id) {
      if (!knowledgeBases) return null;
      for (var i = 0; i < knowledgeBases.length; i++) {
        if (knowledgeBases[i].id === id) return knowledgeBases[i];
      }
      return null;
    }

    // Navigation away from a KB detail that is gone or finished (delete, a 404
    // poll bounce): a bypass go() REPLACING the detail's entry, so Back does not
    // land on a dead KB. No leave guard -- the user did not ask to leave.
    function leaveKnowledgeDetail_() {
      discardOpen_(); // the detail is for a gone item: tear it down first
      App.router.go(App.router.href({ destination: 'library', section: 'knowledge' }),
        { replace: true, bypassGuard: true });
    }

    function renderKnowledgeDetailView(kbId) {
      // Opening another knowledge base stops the previous one's poll at once.
      clearKnowledgePoll();
      knowledgeDetailHandle = null;
      // The create form's folder-focus request applies to its own new item
      // only (it survives the create form's closeOpenItem on the way here).
      if (kbFocusFolderFor !== kbId) kbFocusFolderFor = null;
      // A fresh hydrate (traversal, typed hash, boot) skips the cached list: the
      // KB may have been deleted since it was cached, so it is fetched.
      var skipCache = self._kbFresh === true;
      self._kbFresh = false;
      var cached = skipCache ? null : findKnowledgeBase(kbId);
      if (cached) {
        mountKnowledgeDetail(cached);
        return;
      }
      // Not in the section cache (e.g. a direct hash-load on
      // #library/knowledge/{kb_id} before the list has loaded) — fetch it
      // directly rather than waiting on the list. The detail pane shows
      // nothing meanwhile (never the section root's empty state).
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
          // Unknown/deleted id — heal the URL to the section root in place (a
          // detail LOAD that finds the item gone) and show the root.
          if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) return;
          self._selectedKbId = null;
          App.router.sync('studio', 'knowledge');
          renderKnowledgeSection();
          syncLibrarySelection(true);
        });
    }

    function mountKnowledgeDetail(kb) {
      sectionContentEl.innerHTML = '<div class="admin-loading">Loading knowledge base…</div>';
      Promise.all([
        fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/status')
          .then(function (r) {
            if (r.status === 404) { var gone = new Error('knowledge base gone'); gone.gone = true; throw gone; }
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
        var kbGen = editorGen;
        knowledgeDetailHandle = App.studio.renderKnowledgeDetail(
          sectionContentEl, kb, { status: results[0], items: results[1] },
          {
            // Back is retired (M25 F3 L4b, DD2): the header breadcrumb's
            // "Knowledge bases" link closes the detail (onBreadcrumbClick).
            // DD8: replace to the section root; the row leaves the list (the
            // module invalidated the collection) and focus goes to the row
            // now at its index (the next, else the previous), else Add. The
            // index is read first, while the row is still listed.
            onDeleteSuccess: function () {
              var rowIndex = libraryRowIndex('knowledge:' + kb.id);
              leaveKnowledgeDetail_();
              reloadLibrary('knowledge-bases').then(function () { focusLibraryRowNear(rowIndex); });
            },
            // F6 L3 (L3-D5), carried by F6 L5's Name+Description edit form
            // (L5-D2): re-mount the detail view from the saved object —
            // refreshes the header title and re-fetches status/items. The
            // module invalidated the collection, so the list's row follows
            // the rename (M25 F3 L4a: reloadLibrary, no manual cache patch).
            onSaveSuccess: function (updatedKb) {
              if (kbGen !== editorGen) return; // discarded mid-save: no resurrection
              reloadLibrary('knowledge-bases');
              mountKnowledgeDetail(updatedKb);
            },
            // F6 L5 (L5-D3): bridges the edit form's dirty state into the
            // orchestrator's closure `dirty`, consumed by
            // the App.nav source's `isDirty` (`editorOpen`) — mirrors the
            // mcp-sources/connectors `onDirtyChange: function (d) { dirty = d; }`
            // pattern already established below.
            onDirtyChange: function (d) { dirty = d; }
          }
        );
        startKnowledgePoll(kb.id);
        // A just-created knowledge base (squawk 0101): registering a folder is
        // always the next step, and the form the user was typing in is gone.
        if (kbFocusFolderFor === kb.id) {
          kbFocusFolderFor = null;
          var folderInput = sectionContentEl.querySelector('[data-testid="kb-folder-path-input"]');
          if (folderInput) folderInput.focus();
        }
      }).catch(function (err) {
        if (self._activeSection !== 'knowledge' || self._selectedKbId !== kb.id) return;
        if (err && err.gone) {
          // Cached KB deleted meanwhile: same heal as a 404 on the detail GET.
          self._selectedKbId = null;
          App.router.sync('studio', 'knowledge');
          renderKnowledgeSection();
          syncLibrarySelection(true);
          return;
        }
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
              // return to the section root rather than leaving a dead view
              // or looping on the error.
              clearKnowledgePoll();
              if (self._activeSection === 'knowledge' && self._selectedKbId === kbId) {
                leaveKnowledgeDetail_();
              }
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

    // MCP Servers section — relocated from admin (post-F2 retrofit). The
    // editor branch waits for the type list then delegates to
    // App.studio.renderMcpSourceEditor; at the section root the detail pane
    // shows the empty state beside the Library list (M25 F3 L4a: the grid is
    // retired). The orchestrator-side callbacks bridge dirty-state +
    // navigation.
    function renderMcpSourcesSection() {
      sectionContentEl.innerHTML = '';
      // If a hash-route pending-create is queued (e.g. direct-load on
      // #library/mcp/~new), promote it to mcpSourceFormMode='add' BEFORE
      // deciding so the editor mounts on first paint. Pending-edit can't
      // promote here because the source needs to be in the cache; the
      // pending-item rule (resolvePendingLibraryItem) handles that path.
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
        var mcpGen = editorGen;
        ready.then(function () {
          if (mcpGen !== editorGen) return; // discarded while the types loaded
          // Re-check formMode at resolution time — operator may have
          // navigated away mid-fetch.
          if (mcpSourceFormMode == null || self._activeSection !== 'mcp-sources') return;
          App.studio.renderMcpSourceEditor(sectionContentEl, editingMcpSource, MCP_TYPES, {
            // Back is retired (M25 F3 L4b, DD2): the header breadcrumb's
            // "MCP servers" link closes the editor (onBreadcrumbClick).
            onCancel: function () {
              // Create-mode Cancel (DD8): discard, then a bypass go()
              // REPLACING the create entry with the section root (Back must
              // not land on a stale create form); focus goes to the group's
              // first row, else Add. Edit-mode Cancel reverts the form
              // in-place and never reaches this callback.
              discardOpen_();
              App.router.go(App.router.href({ destination: 'library', section: 'mcp' }),
                { replace: true, bypassGuard: true });
              focusLibraryGroupStart('mcp-sources');
            },
            onSaveSuccess: function (updated, isCreate) {
              if (mcpGen !== editorGen) return; // discarded mid-save: no resurrection
              editingMcpSource = updated;
              mcpSourceFormMode = 'edit';
              dirty = false;
              // The editor invalidated 'mcp-sources': the list shows the new
              // or renamed row.
              reloadLibrary('mcp-sources');
              // The name hint (M25 F3 L2, DD8): a just-created source is not in
              // the store yet. On create this sync is the ~new -> item
              // transition, which it announces; the editor save invalidated
              // 'mcp-sources' first.
              if (window.App && window.App.router) {
                App.router.sync('studio', self.serializeState(), { name: updated.name });
              }
              syncLibrarySelection(true);
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
              // DD8: the row index is read first (the row is still listed:
              // invalidate notifies nobody), then the dead item's editor is
              // torn down and a bypass go() replaces its entry with the
              // section root; focus follows the reload.
              var rowIndex = libraryRowIndex('mcp:' + (editingMcpSource ? editingMcpSource.id : ''));
              discardOpen_();
              App.router.go(App.router.href({ destination: 'library', section: 'mcp' }),
                { replace: true, bypassGuard: true });
              reloadLibrary('mcp-sources').then(function () { focusLibraryRowNear(rowIndex); });
            },
            // A connect success (Refresh, the auto-run after create, Phase 2
            // after sign-in) or a Reset connection rewrote config._cache and
            // invalidated 'mcp-sources': the row's tool count follows.
            onListStale: function () { reloadLibrary('mcp-sources'); },
            onDirtyChange: function (d) { dirty = d; }
          });
        });
        syncLibrarySelection(false);
        return;
      }
      // A pending deep-link id still resolving: the detail pane stays empty
      // (never the section root's empty state first).
      if (self._pendingMcpSourceFormMode === 'edit' && self._pendingMcpSourceId) {
        syncLibrarySelection(false);
        return;
      }
      renderLibraryEmpty('mcp-sources');
      syncLibrarySelection(false);
    }

    function fetchMcpSourceTypes() {
      mcpTypesReady = fetch('/api/mcp-sources/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { MCP_TYPES = types; })
        .catch(function () { MCP_TYPES = []; });
      return mcpTypesReady;
    }

    // Hydrate-only: a fresh item hydrate (or an intent whose item is not in
    // the cache yet) closes the open form, so the section never re-renders the
    // old item while the new one resolves.
    self._closeMcpForm = function () {
      mcpSourceFormMode = null;
      editingMcpSource = null;
      dirty = false;
    };

    function findMcpSource(id) {
      if (!mcpSources) return null;
      for (var i = 0; i < mcpSources.length; i++) {
        if (mcpSources[i].id === id) return mcpSources[i];
      }
      return null;
    }

    // Opens the pending MCP form (create, or an existing source from the cached
    // list). `allowCache` false skips an existing source. Returns true when it
    // opened an editor.
    function tryConsumePendingMcpSource(allowCache) {
      // Pull pending state from instance properties — hydrateState may have
      // set them after init() already captured the closure-locals.
      var pid = self._pendingMcpSourceId;
      var pmode = self._pendingMcpSourceFormMode;
      if (!pid && !pmode) return false;
      if (pmode === 'add') {
        mcpSourceFormMode = 'add';
        editingMcpSource = null;
        self._pendingMcpSourceId = null;
        self._pendingMcpSourceFormMode = null;
        renderMcpSourcesSection();
        return true;
      }
      if (pmode === 'edit' && pid && allowCache !== false) {
        var found = findMcpSource(pid);
        if (found) {
          mcpSourceFormMode = 'edit';
          editingMcpSource = found;
          self._pendingMcpSourceId = null;
          self._pendingMcpSourceFormMode = null;
          renderMcpSourcesSection();
          return true;
        }
        // else: not in the cache; the pending-item rule re-attempts.
      }
      return false;
    }
    self._tryConsumePendingMcpSource = tryConsumePendingMcpSource;

    // ── Connectors section (Mission 23 Flight 2 Leg 2, DD-9; M25 F3 L4a) ──
    // The mcp-sources dispatch above: the editor, a pending id resolving
    // (nothing), or the section root's empty state. Connectors are routed
    // (`connectors/new`, `connectors/{id}`) with the same pending pair.
    function renderConnectorsSection() {
      sectionContentEl.innerHTML = '';
      if (!connectorFormMode && pendingConnectorFormMode === 'add') {
        connectorFormMode = 'add';
        editingConnector = null;
        pendingConnectorFormMode = null;
        pendingConnectorId = null;
      }
      if (connectorFormMode) {
        dirty = false;
        var typesReady = connectorTypesReady || fetchConnectorTypes();
        // Fetch agents directly rather than reading `self._agents` — the
        // shared `loadAll()` populating it runs once at init and is NOT
        // guaranteed to have resolved yet if the operator deep-links straight
        // to #library/connectors/~new (a real race, not just a theoretical
        // one — caught by tests/browser/test_studio_connector_editor.py). A
        // dedicated fetch here is always fresh and never depends on load
        // order.
        var connGen = editorGen;
        Promise.all([typesReady, fetchAgents(true)]).then(function (results) {
          if (connGen !== editorGen) return; // discarded while the lists loaded
          var agentsForDropdown = results[1];
          if (connectorFormMode == null || self._activeSection !== 'connectors') return;
          App.studio.renderConnectorEditor(
            sectionContentEl, editingConnector, CONNECTOR_TYPES, agentsForDropdown, {
              // Back is retired (M25 F3 L4b, DD2): the header breadcrumb's
              // "Connectors" link closes the editor (onBreadcrumbClick).
              // DD8: edit mode reverts in place (the route stays the item);
              // create mode discards and replaces to the section root.
              onCancel: function () {
                if (connectorFormMode === 'edit' && editingConnector) {
                  dirty = false;
                  renderConnectorsSection();
                  return;
                }
                discardOpen_();
                App.router.go(App.router.href({ destination: 'library', section: 'connectors' }),
                  { replace: true, bypassGuard: true });
                focusLibraryGroupStart('connectors');
              },
              // Save-create keeps the editor's render path (no navigation, no
              // hydrate): the editor re-renders in edit mode from the saved
              // row and the URL moves from ~new to the item through sync(),
              // whose create->item rule announces the name. The editor
              // invalidated 'connectors'; the list reloads and `dirty` clears
              // before the URL write.
              onSaveSuccess: function (updated, isCreate) {
                if (connGen !== editorGen) return; // discarded mid-save: no resurrection
                editingConnector = updated;
                connectorFormMode = 'edit';
                reloadLibrary('connectors');
                dirty = false;
                if (window.App && window.App.router) {
                  App.router.sync('studio', 'connectors/' + encodeURIComponent(updated.id),
                    { name: updated.name });
                }
                syncLibrarySelection(true);
                if (isCreate) renderConnectorsSection();
              },
              onDeleteSuccess: function () {
                var rowIndex = libraryRowIndex('connector:' + (editingConnector ? editingConnector.id : ''));
                discardOpen_();
                App.router.go(App.router.href({ destination: 'library', section: 'connectors' }),
                  { replace: true, bypassGuard: true });
                reloadLibrary('connectors').then(function () { focusLibraryRowNear(rowIndex); });
              },
              onDirtyChange: function (d) { dirty = d; }
            }
          );
        });
        syncLibrarySelection(false);
        return;
      }
      if (pendingConnectorFormMode === 'edit' && pendingConnectorId) {
        syncLibrarySelection(false);
        return;
      }
      renderLibraryEmpty('connectors');
      syncLibrarySelection(false);
    }

    function fetchConnectorTypes() {
      connectorTypesReady = fetch('/api/connectors/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { CONNECTOR_TYPES = types; })
        .catch(function () { CONNECTOR_TYPES = []; });
      return connectorTypesReady;
    }

    function findConnector(id) {
      if (!connectors) return null;
      for (var i = 0; i < connectors.length; i++) {
        if (connectors[i].id === id) return connectors[i];
      }
      return null;
    }

    self._closeConnectorForm = function () {
      connectorFormMode = null;
      editingConnector = null;
      dirty = false;
    };

    // The connector twin of tryConsumePendingMcpSource.
    function tryConsumePendingConnector(allowCache) {
      var pid = pendingConnectorId;
      var pmode = pendingConnectorFormMode;
      if (!pid && !pmode) return false;
      if (pmode === 'add') {
        connectorFormMode = 'add';
        editingConnector = null;
        pendingConnectorId = null;
        pendingConnectorFormMode = null;
        renderConnectorsSection();
        return true;
      }
      if (pmode === 'edit' && pid && allowCache !== false) {
        var found = findConnector(pid);
        if (found) {
          connectorFormMode = 'edit';
          editingConnector = found;
          pendingConnectorId = null;
          pendingConnectorFormMode = null;
          renderConnectorsSection();
          return true;
        }
      }
      return false;
    }
    self._tryConsumePendingConnector = tryConsumePendingConnector;

    // ── The pending-item rule (M25 F3 L4a), one rule for MCP and connectors.
    //   - A root with no pending id fetches nothing.
    //   - A create form needs no list: it opens at once.
    //   - A pending id on a FRESH hydrate (boot, Back/Forward, a typed hash):
    //     force-get (joining pane creation's or activate's forced get), then
    //     consume, then heal a dead id to the section root.
    //   - A pending id on an INTENT (a row click, an agent-tab link): consume
    //     from the section cache; on a miss (a cold cache) consume after a
    //     plain get, or on the next store notification (the lifetime
    //     subscriptions re-attempt) -- never heal on non-fresh data.
    var PENDING_KINDS = {
      'mcp-sources': {
        collection: 'mcp-sources',
        mode: function () { return self._pendingMcpSourceFormMode; },
        id: function () { return self._pendingMcpSourceId; },
        consume: tryConsumePendingMcpSource,
        heal: function () {
          self._pendingMcpSourceId = null;
          self._pendingMcpSourceFormMode = null;
          App.router.sync('studio', 'mcp-sources');
          renderMcpSourcesSection();
          syncLibrarySelection(true);
        }
      },
      'connectors': {
        collection: 'connectors',
        mode: function () { return pendingConnectorFormMode; },
        id: function () { return pendingConnectorId; },
        consume: tryConsumePendingConnector,
        heal: function () {
          pendingConnectorId = null;
          pendingConnectorFormMode = null;
          App.router.sync('studio', 'connectors');
          renderConnectorsSection();
          syncLibrarySelection(true);
        }
      }
    };

    function resolvePendingLibraryItem(section, fresh) {
      var k = PENDING_KINDS[section];
      if (!k || !k.mode()) return;
      if (k.mode() === 'add') {
        k.consume(true);
        return;
      }
      var pid = k.id();
      if (!pid) return;
      var stillPending = function () {
        return self._activeSection === section && k.mode() === 'edit' && k.id() === pid;
      };
      if (!fresh) {
        if (k.consume(true)) return;
        App.store.get(k.collection).then(function () {
          syncLibraryCache(k.collection);
          if (stillPending()) k.consume(true);
        }, function () { /* the next notification re-attempts */ });
        return;
      }
      App.store.get(k.collection, { force: true }).then(function (list) {
        syncLibraryCache(k.collection);
        if (!stillPending()) return; // consumed by the notification, or superseded
        if (k.consume(true)) return;
        // Heal only when the fetch just made agrees the id is gone (the store
        // may have dropped this response if a mutation invalidated it
        // mid-flight; the next notification then consumes the item).
        for (var i = 0; list && i < list.length; i++) {
          if (list[i] && list[i].id === pid) return;
        }
        k.heal();
      }, function () { /* a failed load is not a dead id: stay pending */ });
    }

    self._resolvePendingLibraryItems = function (fresh) {
      if (PENDING_KINDS[self._activeSection]) resolvePendingLibraryItem(self._activeSection, fresh);
    };

    // closeOpenItem: tear every open item down to "nothing open" -- the agent
    // editor and create form, MCP and connector form modes, the knowledge
    // detail view (with its poll) -- and reset the dirty mirror. Called by
    // hydrateState for a SECTION-ROOT route, so clicking the current section
    // (or going to a destination root) still closes the open editor (F4 L7,
    // M10 F6 L7). It is NOT part of setActiveSection, where it would close an
    // item that is being opened. Bumping selectSeq invalidates an in-flight
    // doSelect.
    function closeOpenItem() {
      selectSeq += 1;
      editorGen += 1; // invalidates in-flight editor resolvers (saves, type waits)
      // Unconditional: a caller may have cleared _selectedAgent already (post-
      // delete, the save->delete race) while the stale editor DOM is mounted.
      renderEmptyEditor();
      self._selectedAgent = null;
      self._selectedAgentLoaded = true;
      self._createMode = false;
      mcpSourceFormMode = null;
      editingMcpSource = null;
      connectorFormMode = null;
      editingConnector = null;
      kbCreateMode = false;
      clearKnowledgePoll();
      knowledgeDetailHandle = null;
      self._selectedKbId = null;
      self._selectedMcpAgentSourceId = null;
      self._pendingMcpAgentSourceId = null;
      dirty = false;
    }
    self._closeOpenItem = closeOpenItem;

    // The App.nav discard (M25 F2 L5, DD5): teardown to "nothing open" -- never
    // a URL write. closeOpenItem empties the agent editor; the section-content
    // editors (MCP, connector, KB detail) also leave their DOM in
    // sectionContentEl, so clear it for non-agent editors.
    function discardOpen_() {
      var section = self._activeSection;
      try {
        closeOpenItem();
        if (section !== 'agents' && sectionContentEl) sectionContentEl.innerHTML = '';
      } finally {
        dirty = false; // even a throwing teardown must not leave a phantom flag
      }
    }
    self._discardOpen = discardOpen_;

    // ── The item header's breadcrumb link (M25 F3 L4b; DD2 refinement) ──────
    // Every Agents and Library item header (the agent editor, the knowledge-
    // base detail and `~new` form, the MCP and connector editors) shows
    // "Agents" or "Library / {Group}" with its last segment a link to the
    // destination or section root (`editor-breadcrumb-link`, built by each
    // editor). With Back retired it is the visible way to close an item. A
    // plain activation (a click, or Enter on the link) is routed here, ahead
    // of App.nav's document-level interceptor: an intent go() to the root, so
    // the router's guard asks once about a dirty editor and the root's hydrate
    // closes the item (closeOpenItem). Once it has navigated, focus goes to
    // the closed item's row (DD8); a create form has no row, so focus goes
    // where Cancel on a create form sends it (the section's first row, else
    // the list's primary action). The focus waits one task: after a Continue,
    // nav.js focuses <main> from a setTimeout, and the row must land last.
    // Modified clicks (new tab, etc.) keep the browser's behaviour.
    function closingItem_() {
      var section = self._activeSection;
      return { section: section, rowId: section === 'agents' ? listSelection() : librarySelection() };
    }

    function focusClosedItem_(closing) {
      if (self._activeSection !== closing.section) return; // the user moved on
      if (closing.section === 'agents') {
        if (!agentsList || self._selectedAgent || self._createMode) return;
        focusAgentRowNear(closing.rowId != null ? visibleIndexOf(closing.rowId) : 0);
        return;
      }
      if (!libraryList || !atLibraryRoot()) return;
      if (closing.rowId != null) focusLibraryRowNear(libraryRowIndex(closing.rowId));
      else focusLibraryGroupStart(closing.section);
    }

    function onBreadcrumbClick(e) {
      if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      var link = e.target && typeof e.target.closest === 'function'
        ? e.target.closest('a.editor-breadcrumb-link') : null;
      if (!link || !content.contains(link)) return;
      e.preventDefault();
      var closing = closingItem_();
      App.router.go(link.getAttribute('href'), { opener: link }).then(function (navigated) {
        if (navigated) setTimeout(function () { focusClosedItem_(closing); }, 0);
      });
    }
    content.addEventListener('click', onBreadcrumbClick);

    function setActiveSection(section, options) {
      options = options || {};
      var writeUrl = options.writeUrl !== false; // default true
      // hydrateState captures the previous section and passes it in; it no
      // longer assigns _activeSection itself.
      var prevSection = options.prev !== undefined ? options.prev : self._activeSection;
      self._activeSection = section;
      // Outgoing-section cleanup (M25 F2 L3 (a)): the one place a section
      // change tears down the section being left, shared by hydrateState
      // and destination switches. Leaving Agents drops the
      // selection and create mode and stops an in-flight select from
      // completing (selectSeq).
      if (prevSection === 'agents' && section !== 'agents') {
        selectSeq += 1;
        if (self._selectedAgent || self._createMode) renderEmptyEditor();
        self._selectedAgent = null;
        self._selectedAgentLoaded = true;
        self._createMode = false;
        dirty = false;
      }
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
      // selection (and the create form, M25 F3 L4a), so re-entering
      // #library/knowledge mounts the section root — the
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
        kbCreateMode = false;
        kbFocusFolderFor = null;
        dirty = false;
      }
      // The sidebar hosts (M25 F3 L3/L4a, DD3 (a)/(e)): mountArea never re-runs
      // init between Agents and Library (one area module), so this is the one
      // owner of both list panes' lifetimes -- each created on entering its
      // destination and destroyed on leaving it, the outgoing one first, so
      // exactly one pane exists -- and of which host is visible. A move
      // between Library sections keeps the Library pane (one list).
      if (section === 'agents') {
        destroyLibraryList();
        if (!agentsList) createAgentsList();
      } else {
        destroyAgentsList();
        if (!libraryList) createLibraryList();
      }
      agentsListHost.classList.toggle('is-hidden', section !== 'agents');
      libraryListHost.classList.toggle('is-hidden', section === 'agents');
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

    // Section-content (the Agents empty state / the Library sections) and the
    // agent editor share the main panel (the detail pane); only one is visible
    // at a time. The agent editor takes over when an agent is selected or
    // being created in the Agents section; otherwise section-content -- on
    // Agents, the empty detail state -- is the visible child.
    // The Library sections render their editors and empty states INSIDE
    // sectionContentEl (their own dispatch lives in render*Section), so
    // editorEl stays hidden whenever _activeSection !== 'agents'.
    function updateContentVisibility() {
      var inAgentEditor = self._activeSection === 'agents' &&
                          (self._selectedAgent || self._createMode);
      sectionContentEl.classList.toggle('is-hidden', !!inAgentEditor);
      editorEl.classList.toggle('is-hidden', !inAgentEditor);
    }

    // ── Single URL-write call site ──────────────────────────────────────
    function writeUrl_() {
      if (window.App && window.App.router) {
        App.router.sync('studio', self.serializeState());
      }
    }
    self._writeUrl = writeUrl_;

    // ── Data fetching ────────────────────────────────────────────────

    function fetchAgents(force) { return App.store.get('agents', { force: !!force }); }
    function fetchTools() { return fetch('/api/tools').then(function (r) { return r.json(); }); }
    // M21 F01 L02 (DD3): the editor's fetch — as opposed to the Library
    // list's store collection ('mcp-sources', the plain list) — includes
    // per-agent self-configuration surface rows so the agent editor's MCPs
    // tab and Self-configuration tab can see them; the Library list excludes
    // them (no query param there).
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
      // Every self-configuration enable/disable/approval/revision write funnels
      // here; the server-side agent changed, so the shared list is stale (DD8).
      App.store.invalidate('agents');
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
        if (data.status === 'ok') {
          // The connect rewrote config._cache server-side: the Library list's
          // tool count is stale (M25 F3 L2, DD9).
          App.store.invalidate('mcp-sources');
          return data;
        }
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

    // Studio keeps its own copies (self._agents / self._allProviders), so a
    // store load that Studio did not initiate (Chats activation, a Library KB
    // rename that invalidated 'agents') would otherwise leave them stale.
    // Studio's own loadAll assigns directly, so notifications are ignored
    // while one is in flight.  Detail-shaped objects are never written back
    // to the store: this only reads the notified (list-shaped) copy.
    // The Agents list re-renders on every notification (M25 F3 L3): it sits
    // beside the editor, so an open agent or create form no longer hides it.
    App.store.subscribe('agents', function (list) {
      if (loadAllDepth > 0 || !self._agentsLoaded) return;
      self._agents = list;
      renderAgentList();
    });
    App.store.subscribe('providers', function (list) {
      if (loadAllDepth > 0 || !self._agentsLoaded) return;
      self._allProviders = list;
      renderAgentList(); // the provider dots and names
    });
    // The Library list's four subscriptions (M25 F3 L4a), registered once for
    // the page's lifetime: they always feed the section caches and re-attempt
    // a pending MCP / connector consume (an intent whose item was not cached),
    // and they render the list only while the Library pane exists. A bare
    // notification never scrolls the list.
    App.store.subscribe('knowledge-bases', function (list) {
      knowledgeBases = list;
      renderLibraryList();
    });
    App.store.subscribe('mcp-sources', function (list) {
      mcpSources = list;
      if (self._activeSection === 'mcp-sources' && self._pendingMcpSourceFormMode === 'edit') {
        tryConsumePendingMcpSource(true);
      }
      renderLibraryList();
    });
    App.store.subscribe('connectors', function (list) {
      connectors = list;
      if (self._activeSection === 'connectors' && pendingConnectorFormMode === 'edit') {
        tryConsumePendingConnector(true);
      }
      renderLibraryList();
    });
    App.store.subscribe('agents', function () {
      renderLibraryList(); // the "{n} agents" counts
    });

    function loadAllImpl(force) {
      return Promise.all([
        fetchAgents(force), fetchTools(), fetchMcpSources(),
        fetchKnowledgeBases(force), fetchProviders(force)
      ])
        .then(function (results) {
          self._agents = results[0];
          self._allTools = results[1];
          self._allMcpSources = results[2];
          self._allKnowledgeBases = results[3];
          self._allProviders = results[4];
          self._agentsLoaded = true;
          // The list's rows need both agents and providers (the dot, the
          // provider name); a no-op off Agents.
          renderAgentList(true);
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
    // uses for section-level fetch failures (the knowledge detail view),
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

    // ── Agents list column + empty detail state (M25 F3 L3, DD4) ──────────

    // The agent the list marks selected: the pending hydrate target, else the
    // open agent; none in create mode or outside Agents.
    function listSelection() {
      if (self._activeSection !== 'agents' || self._createMode) return null;
      if (self._pendingSelectName) return self._pendingSelectName;
      return self._selectedAgent ? self._selectedAgent.name : null;
    }

    function providerFor(agent) {
      if (!agent || !agent.provider_config_id) return null;
      var providers = self._allProviders || [];
      for (var i = 0; i < providers.length; i++) {
        if (providers[i].id === agent.provider_config_id) return providers[i];
      }
      return null;
    }

    // One list row. The provider dot is an aria-hidden .badge--{type} disc;
    // the provider's name joins the row's accessible name (A31), so the dot
    // never carries meaning by colour alone. The filter matches the name, the
    // model id and the provider TYPE slug (A16), not the display name.
    function agentItem(agent) {
      var provider = providerFor(agent);
      var type = provider && provider.type ? String(provider.type) : '';
      var dot = document.createElement('span');
      dot.setAttribute('aria-hidden', 'true');
      if (provider) {
        var kind = App.ui.badge.KINDS.indexOf(type) !== -1 ? type : 'unknown';
        dot.className = 'badge badge--' + kind + ' badge-dot';
      } else {
        dot.className = 'badge badge-dot badge-dot--none';
      }
      var model = agent.llm_model || '';
      return {
        id: agent.name,
        label: agent.name,
        meta: model,
        href: App.router.href({ destination: 'agents', id: agent.name }),
        testid: 'agent-item',
        // A trailing separator when the model follows, so the name reads
        // "name, Provider, model", never "Provider model" (the flight-end review).
        nameSuffix: ', ' + (provider ? provider.name || type : 'no provider') +
          (model ? ',' : ''),
        lead: dot,
        filterText: (agent.name + ' ' + model + ' ' + type).toLowerCase()
      };
    }

    // The predicate runs once per row per keystroke, so the needle is derived
    // once per query.
    var filterQuery = null;
    var filterNeedle = '';
    function agentFilter(item, query) {
      if (query !== filterQuery) {
        filterQuery = query;
        filterNeedle = String(query || '').trim().toLowerCase();
      }
      return !filterNeedle || item.filterText.indexOf(filterNeedle) !== -1;
    }

    // "New" (the title-row action and the empty state's action) is a user
    // INTENT: a go() to the create route, so the router's leave guard asks
    // once about an open dirty agent. With the create form already open on
    // its route there is nothing to navigate to: focus returns to the name
    // field and nothing re-renders.
    function goCreateAgent(e) {
      var cur = App.router.current();
      if (self._createMode && cur && cur.route === 'agents/~new') {
        focusNameField();
        return;
      }
      App.router.go(App.router.href({ destination: 'agents', create: true }),
        { opener: (e && e.currentTarget) || null });
    }

    function focusNameField() {
      var nameInput = editorEl.querySelector('#studio-name');
      if (nameInput) nameInput.focus();
    }

    function createAgentsList() {
      newAgentBtn = App.ui.button({
        variant: 'secondary',
        size: 'sm',
        icon: 'plus',
        label: 'New',
        ariaLabel: 'New agent',
        testid: 'new-agent-btn',
        onClick: goCreateAgent
      });
      agentsList = App.ui.listPane({
        title: 'Agents',
        count: true,
        actions: [newAgentBtn],
        filter: {
          label: 'Filter agents',
          placeholder: 'Filter by name, model or provider',
          predicate: agentFilter,
          testid: 'agents-filter'
        },
        emptyText: function (q) {
          if (q) return 'No agents match "' + q + '".';
          return self._agentsLoaded ? 'No agents yet.' : 'Loading agents\u2026';
        },
        rowStyle: 'agents',
        testid: 'agents-list'
      });
      agentsListHost.appendChild(agentsList.el);
    }

    function destroyAgentsList() {
      if (!agentsList) return;
      agentsList.destroy();
      agentsListHost.textContent = '';
      agentsList = null;
      newAgentBtn = null;
    }

    // The one builder of the Agents list (design review item 6): items from
    // self._agents (list- or detail-shaped; only name, llm_model and
    // provider_config_id are read) and self._allProviders, sorted A-Z, then
    // the selection -- setSelected AFTER setItems, so a refetch that lands
    // mid-select keeps the right row. A no-op off Agents (no pane). `scroll`
    // (a load or a navigation) brings the selected row into view (A26); the
    // first fill does too. Store notifications pass nothing, so a user
    // scrolling the list is never yanked back.
    function renderAgentList(scroll) {
      if (!agentsList) return;
      var wasEmpty = agentsList.getItems().length === 0;
      var agents = (self._agents || []).slice().sort(function (a, b) {
        return String(a.name).localeCompare(String(b.name));
      });
      var items = [];
      for (var i = 0; i < agents.length; i++) items.push(agentItem(agents[i]));
      agentsList.setItems(items);
      agentsList.setSelected(listSelection());
      if (scroll || (wasEmpty && items.length)) scrollAgentsToSelected();
      renderAgentsEmpty();
    }

    // Scroll the selected row into view now, and once more when the web fonts
    // are ready: on a cold load the rows reflow when Geist arrives (a fraction
    // of a pixel per row adds up over 25 rows), which would push a row scrolled
    // in with fallback metrics back out of view. After the first load the
    // fonts are ready, so the second scroll lands on the same position.
    function scrollAgentsToSelected() {
      var pane = agentsList;
      pane.scrollToSelected();
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () {
          if (agentsList === pane) pane.scrollToSelected();
        });
      }
    }

    // DD3 (c): every Agents hydrate re-syncs the list's selection (and scrolls
    // to it) without rebuilding the rows.
    self._syncAgentSelection = function () {
      if (!agentsList) return;
      agentsList.setSelected(listSelection());
      scrollAgentsToSelected();
    };

    // The detail pane with no agent open: a pane-size empty state whose copy
    // depends on whether any agent exists. Nothing before the first load.
    // Only its own node is replaced, never the rest of sectionContentEl (the
    // loadAll failure line lives there too).
    function renderAgentsEmpty() {
      if (self._activeSection !== 'agents') return;
      var kind = !self._agentsLoaded ? null : (self._agents.length ? 'some' : 'none');
      if (kind === agentsEmptyKind && (agentsEmptyEl || !kind)) return;
      if (agentsEmptyEl && agentsEmptyEl.parentNode) agentsEmptyEl.parentNode.removeChild(agentsEmptyEl);
      agentsEmptyEl = null;
      agentsEmptyKind = kind;
      if (!kind) return;
      var opts = kind === 'some'
        ? { title: 'Select an agent to edit it, or create a new one.', testid: 'agent-select-empty' }
        : { title: 'No agents yet. Create one to get started.', testid: 'agent-empty' };
      opts.size = 'pane';
      opts.headingLevel = 2;
      opts.action = App.ui.button({
        variant: 'secondary',
        icon: 'plus',
        label: 'New agent',
        testid: 'agent-empty-new',
        onClick: goCreateAgent
      });
      agentsEmptyEl = App.ui.emptyState(opts);
      sectionContentEl.insertBefore(agentsEmptyEl, sectionContentEl.firstChild);
    }

    // DD8 focus rule after a delete or a create-form Cancel: the row at
    // `index` among the visible rows (the next one after a removed row), else
    // the previous one, else the list's "New" action.
    function focusAgentRowNear(index) {
      if (!agentsList) return;
      var rows = agentsList.el.querySelectorAll('li:not([hidden]) > .ui-list-pane-row');
      var target = rows.length ? rows[Math.max(0, Math.min(index, rows.length - 1))] : null;
      if (!target) {
        if (newAgentBtn) newAgentBtn.focus();
        return;
      }
      for (var i = 0; i < rows.length; i++) rows[i].setAttribute('tabindex', rows[i] === target ? '0' : '-1');
      target.focus();
    }

    // The visible-row index the named agent holds (or would hold), read
    // BEFORE a delete: setItems restores focus only to a row that had it.
    function visibleIndexOf(name) {
      if (!agentsList) return 0;
      // Every row, hidden or not, in item order (one row per item).
      var rows = agentsList.el.querySelectorAll('li > .ui-list-pane-row');
      var items = agentsList.getItems();
      var n = 0;
      for (var i = 0; i < items.length && i < rows.length; i++) {
        if (items[i].id === name) return n;
        if (!rows[i].parentNode.hidden) n++;
      }
      return n;
    }

    // ── Agent selection ──────────────────────────────────────────────

    // F5 leg 04: doSelect / doEnterCreateMode — extracted bodies past the
    // dirty-check so the App.confirmDialog onConfirm callback can invoke
    // the real navigation. The async dialog pattern requires the guard to
    // dispatch the dialog and let onConfirm proceed (the synchronous
    // window.confirm guard-and-return pattern doesn't translate directly).
    function doSelect(agent) {
      // M25 F2 L3 (a): refuse to force-switch sections. Only a user who is
      // still on Agents may open an agent; an async caller (the
      // self-configuration refresh, save-create, the delete fallback) whose
      // user has since moved to another section or destination does nothing.
      var routed = window.App && App.router && App.router.current && App.router.current();
      if (self._activeSection !== 'agents' || (routed && routed.destination !== 'agents')) return;
      var mySelect = ++selectSeq;
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
      renderAgentList(true);
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
        // Stale-then guard (M25 F2 L3 (a)): the user may have left Agents, closed
        // the editor or opened another agent while the fetches were in flight.
        if (mySelect !== selectSeq || self._activeSection !== 'agents' || self._createMode) return;
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

    // Agent navigation (M25 F2 L4). Opening an agent is a user INTENT: a list
    // row is an <a href> that App.nav routes through a pushed go(), whose leave
    // guard is the only prompt for unsaved changes. Navigation that is a
    // COMPLETION of something the user already did (save-create, post-delete,
    // the save->delete race, Cancel on the create form) is a bypass go() that
    // REPLACES the current entry: no guard, no extra history entry.
    function replaceWithAgent_(agent) {
      App.router.go(App.router.href({ destination: 'agents', id: agent.name }),
        { replace: true, bypassGuard: true });
    }

    function replaceWithAgentsRoot_() {
      App.router.go(App.router.href({ destination: 'agents' }),
        { replace: true, bypassGuard: true });
    }

    // The create form (M25 F3 L3, DD8): the hydrate target of `agents/~new`
    // (hydrateState calls it as self._enterCreate). Entering it while it is
    // already open re-renders nothing and only refocuses the name field.
    function doEnterCreateMode() {
      if (self._createMode && self._activeSection === 'agents') {
        focusNameField();
        return;
      }
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
      updateContentVisibility();
      // F6 leg 05 — refresh operator-state caches before rendering so the
      // new-agent Tools tab reflects current operator-disabled state.
      // F9 L3 (A-L3-1) — also refresh the MCP sources list so a freshly
      // created source is visible from the new-agent MCPs tab without
      // a manual page reload. F6 L3 (L3-D3): the fresh-agent refetch is
      // select-path only — create mode has no agent to fetch — but the
      // knowledge-base refresh goes into both sites.
      // M25 F3 L3: `#agents/~new` is a route, so a cold deep link can land here
      // before loadAll has the providers the form's picker needs; the store
      // read returns the cached list or joins the in-flight load.
      var myCreate = ++selectSeq;
      var providersReady = fetchProviders().then(function (list) {
        self._allProviders = list;
      }, function () { /* keep the prior list; the form still renders */ });
      Promise.all([
        refreshToolConfigsCache(), refreshMcpSourcesCache(), refreshKnowledgeBasesCache(), providersReady
      ]).then(function () {
        if (myCreate !== selectSeq || self._activeSection !== 'agents' || !self._createMode) return;
        renderEditor(null);
        updateContentVisibility();
        writeUrl_();
        focusNameField();
      });
    }
    self._enterCreate = doEnterCreateMode;

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
        onDelete: handleDeleteEditor,
        onPurge: handlePurgeHistory,
        onSave: function () { save(isCreate); },
        onCancel: function () { cancelEdit(); },
        onTabChange: function (tabId) { setActiveTab(tabId); },
        // F5 leg 05: tabs in the same agent share the form's dirty state, so
        // switching tabs does NOT lose unsaved data — no confirmation prompt.
        // The router's leave guard still fires on a list row, "New", the rail
        // and hash-route navigation to a different agent.
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
        // The studio owns the source focus (hydrate applies the URL's value to
        // both slots); the tab reads it from here, never from location.hash.
        pendingMcpAgentSourceId: self._selectedMcpAgentSourceId || self._pendingMcpAgentSourceId || null,
        // Callback so renderMcpsTab can notify studio.js when the selected
        // source changes (chip click → per-attachment editor). studio.js
        // updates _selectedMcpAgentSourceId and syncs the URL.
        onSelectedMcpSourceChange: function (sourceId) {
          self._selectedMcpAgentSourceId = sourceId;
          self._pendingMcpAgentSourceId = null;
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

      // Dirty snapshot baseline. The header was just rebuilt, so checkDirty
      // re-derives Save, Cancel and the unsaved caption from it (clean).
      snapshot = getFormSnapshot();
      checkDirty();
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
      if (tab !== 'mcps') {
        self._selectedMcpAgentSourceId = null;
        self._pendingMcpAgentSourceId = null;
      }
      self._activeTab = tab;
      if (tabHandle && tabHandle.getActive() !== tab) {
        tabHandle.activate(tab);
      }
      if (writeUrl) writeUrl_();
    }
    self._setActiveTab = setActiveTab;

    // ── Action-cluster handlers ──────────────────────────────────────

    // Cancel discards in-progress edits and restores the editor to the
    // current agent's saved state. The button only fires when dirty
    // (disabled by checkDirty otherwise), so no extra guard.
    function cancelEdit() {
      if (self._createMode) {
        // Create-form Cancel (M25 F3 L3, DD8): there is no saved state to
        // revert to. The studio discard teardown runs first, then a bypass
        // go() (the user already chose to discard) REPLACES the create entry
        // with the Agents root, so Back never lands on a stale create form.
        // Focus: there is no row of its own, so the list's tab stop (the
        // nearest row), else "New".
        discardOpen_();
        replaceWithAgentsRoot_();
        focusAgentRowNear(0);
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
        // DD8 focus: the deleted row's visible index, read BEFORE the request
        // (the row is about to leave the list).
        var rowIndex = visibleIndexOf(name);
        fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
          })
          .then(function () {
            App.store.invalidate('agents');
            self._selectedAgent = null;
            dirty = false;
            return loadAll();
          })
          .then(function () {
            // Post-delete navigation (M25 F3 L3, DD8): replace the deleted
            // agent's entry with the Agents root -- the empty detail state,
            // announced as "Agents" -- never another agent. The deleted
            // agent's editor is torn down first (vanish path). Focus goes to
            // the nearest surviving row (the next, else the previous), else
            // "New".
            discardOpen_();
            replaceWithAgentsRoot_();
            focusAgentRowNear(rowIndex);
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
          // The dirty baseline (renderEditor) was taken before this list
          // arrived, so the select's value moved under it. While the user has
          // changed nothing, re-take it: otherwise an edit that is reverted
          // still reads dirty (Save enabled, "Unsaved changes" shown).
          if (!dirty) {
            snapshot = getFormSnapshot();
            checkDirty();
          }
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
      // The unsaved caption (M25 F3 DD2, A15) reads this same flag: a stable
      // span in the header whose text is set or cleared, never re-created.
      var unsavedEl = editorEl.querySelector('.editor-unsaved');
      if (unsavedEl) unsavedEl.textContent = dirty ? 'Unsaved changes' : '';
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
        // Save-create staleness (the knowledge-base create form's
        // stillOnCreate() pattern): the user may move on while the POST or
        // the list reload that follows it is in flight. This form is still
        // the open item while no teardown has run since Save (closeOpenItem
        // bumps editorGen) and the router still shows the create route.
        var createGen = editorGen;
        var onThisForm = function () {
          var cur = App.router.current();
          return createGen === editorGen && !!cur && cur.route === 'agents/~new';
        };
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
            App.store.invalidate('agents');
            // Still on the form: it is now a saved agent awaiting its route,
            // so clear its flags -- only then, since `dirty` is one flag
            // shared by every studio editor and a re-entered create form owns
            // `_createMode`.
            var stayed = onThisForm() && self._createMode;
            if (stayed) {
              dirty = false;
              self._createMode = false;
            }
            return loadAll().then(function () {
              // The list has the new row either way (loadAll re-rendered it).
              // Open the agent only for a user still on this form with no
              // leave decision pending: a bypass replace would otherwise pull
              // someone who moved on (another agent, the Agents root, another
              // destination) onto the new agent.
              if (!stayed || !onThisForm() || App.router.isDeciding()) return;
              var found = null;
              for (var i = 0; i < self._agents.length; i++) {
                if (self._agents[i].name === created.name) { found = self._agents[i]; break; }
              }
              // Save-create: replace the create route's history entry with
              // the new agent's route (no new entry).
              if (found) replaceWithAgent_(found);
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
              App.store.invalidate('agents');
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
            App.store.invalidate('agents');
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
              } else {
                // Save→delete race (F1 debrief): a concurrent DELETE removed
                // this agent between the PUT resolving and loadAll(). Without
                // this fallback the block silently no-ops, stranding a stale
                // editor for a now-gone agent. Like a delete (M25 F3 L3, DD8),
                // it lands on the Agents root, never on another agent.
                self._selectedAgent = null;
                discardOpen_();
                replaceWithAgentsRoot_();
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

    // Resolves the pending agent (set by hydrateState) against the LOADED list.
    // doSelect, not an inline-gated select: a hydrate is reached through the
    // router, whose leave guard has already asked about unsaved changes, so it
    // must never prompt a second time. Re-opening the same agent re-renders it
    // fresh from the server (a restore after a discarded edit shows saved
    // state, not the abandoned form).
    //
    // An id that is not in the loaded list is DEAD (deleted meanwhile, or a
    // stale link): it is never kept pending -- the URL heals to the Agents root
    // in place and the root renders (no editor, no endless pending state).
    function resolvePendingAgent() {
      var name = self._pendingSelectName;
      if (!name) return;
      if (self._activeSection !== 'agents') return;
      var target = null;
      for (var i = 0; i < self._agents.length; i++) {
        if (self._agents[i].name === name) { target = self._agents[i]; break; }
      }
      self._pendingSelectName = null;
      if (target) {
        doSelect(target);
        return;
      }
      self._pendingTabName = null;
      self._pendingMcpAgentSourceId = null;
      self._activeTab = 'general';
      closeOpenItem();
      renderAgentList();
      updateContentVisibility();
      App.router.sync('studio', 'agents');
    }

    // `fresh` (a traversal, a typed hash or boot) resolves against a FRESH list
    // fetch -- the cached list may still hold an agent deleted since. A non-fresh
    // (intent) hydrate uses the cached list; before the first load has resolved
    // it waits for it.
    var bootLoad = null;  // the init() load while it is in flight
    function tryConsumePendingSelect(fresh) {
      if (!self._pendingSelectName) return;
      var name = self._pendingSelectName;
      if (!fresh && self._agentsLoaded) {
        resolvePendingAgent();
        return;
      }
      var onLoaded = function () {
        if (self._pendingSelectName !== name) return;  // superseded or already resolved
        resolvePendingAgent();
      };
      if (bootLoad) {
        // init()'s own load: it reports its failure itself.
        bootLoad.then(onLoaded, function () {});
        return;
      }
      loadAll().then(onLoaded).catch(function (err) {
        showLoadAllError(err, { nonDestructive: true });
      });
    }

    self._refresh = function () {
      loadAll(true).then(function () {
        // (b) Re-select ONLY on the Agents section: a refresh landing after
        // the user moved to Library must not re-open the stale agent (and
        // doSelect, not selectAgent -- a refresh never prompts).
        if (self._activeSection === 'agents' && self._selectedAgent) {
          var found = null;
          for (var i = 0; i < self._agents.length; i++) {
            if (self._agents[i].name === self._selectedAgent.name) { found = self._agents[i]; break; }
          }
          if (found) {
            doSelect(found);
          } else {
            // The open agent is gone (deleted elsewhere): heal to the Agents
            // root in place, like a dead hydrate id -- never open another
            // agent (M25 F3 L3, DD8).
            closeOpenItem();
            renderAgentList();
            updateContentVisibility();
            App.router.sync('studio', 'agents');
          }
        }
      }).catch(function (err) {
        showLoadAllError(err, { nonDestructive: true });
      });
      // Studio activate on a Library section (the Library pane survived a trip
      // to Chats or Settings): force-get the three Library collections, so a
      // mutation made elsewhere shows within DD9's freshness bound (M25 F3
      // L4a; this replaces the MCP-only refetch). The hydrate that follows
      // joins these requests.
      if (libraryList && isLibrarySection(self._activeSection)) loadLibrary(true);
    };
    self._tryConsumePendingSelect = function (fresh) { tryConsumePendingSelect(fresh); };
    // View of the shared dirty mirror (browser tests assert that a
    // discard/teardown left it false). The setter is a TEST SEAM only: it lets a
    // test plant a stale flag with no editor open to prove App.nav ignores it.
    Object.defineProperty(self, '_dirty', {
      get: function () { return dirty; },
      set: function (v) { dirty = !!v; },
      configurable: true
    });

    // Leave-guard source (M25 F2 L5, DD5). `isDirty` is the
    // editor-open predicate registered via App.nav.registerSource: the shared `dirty` flag AND an editor open,
    // so a stale flag can never raise a phantom prompt or beforeunload. The
    // predicate covers every editor mount context: agents (incl. the create
    // form), mcp-sources, connectors and the knowledge detail view (its
    // Name+Description edit form is multi-field with an explicit Save; the
    // section root has no edit form, so `_selectedKbId` alone marks "form
    // open") and the knowledge-base create form (M25 F3 L4a).
    function editorOpen() {
      return (self._activeSection === 'agents' && !!(self._selectedAgent || self._createMode)) ||
        (self._activeSection === 'mcp-sources' && !!mcpSourceFormMode) ||
        (self._activeSection === 'connectors' && !!connectorFormMode) ||
        (self._activeSection === 'knowledge' && !!(self._selectedKbId || kbCreateMode));
    }
    App.nav.registerSource('studio', {
      isDirty: function () { return dirty && editorOpen(); },
      discard: discardOpen_
    });

    // Pre-fetch MCP source types so the editor mount path doesn't have to
    // wait on the first network round-trip when the operator clicks "New
    // MCP Server" or deep-links to mcp-sources/{id}.
    fetchMcpSourceTypes();

    setActiveSection(self._activeSection || 'agents', { writeUrl: false });

    bootLoad = loadAll(true);
    var bootSettled = function () { bootLoad = null; };
    bootLoad.then(bootSettled, bootSettled);
    bootLoad.then(function () {
      if (self._activeSection === 'agents') {
        if (self._pendingSelectName) {
          // This load is fresh (it just resolved), so a pending id absent from
          // it is dead and heals to the Agents root.
          resolvePendingAgent();
          if (self._selectedAgent) return;
        }
        // Guard: if the user entered create mode or selected an agent while
        // loadAll was still in flight, don't clobber the editor they are
        // already in. The editor is already correctly rendered and visible
        // from the doEnterCreateMode / doSelect Promise.all.then() path.
        if (self._createMode || self._selectedAgent) return;
        // Bare #agents shows the empty detail state beside the list; no
        // agent is auto-selected. The user picks a row (or "New").
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
  // Flight 6 leg 1 (L1-D2 site 2): app.js's mountArea calls
  // this on EVERY cross-area transition. Without it, opening a Knowledge
  // detail view and clicking e.g. Chat leaves the 5-second poll running
  // for the life of the page — this is the first Studio section to need a
  // real body here; every prior section issues one-shot fetches, not
  // intervals. Note the beforeunload listener registered inside init()
  // is gone (the one beforeunload lives in nav.js); this body only
  // stops the knowledge poll.
  deactivate: function () {
    if (this._knowledgePollTimer) {
      clearInterval(this._knowledgePollTimer);
      this._knowledgePollTimer = null;
    }
  }
});
