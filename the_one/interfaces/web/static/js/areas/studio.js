// M25 F4 L6 (flight DD7, leg AC12): App.studio.clearAgentFilter() clears the
// Agents list's filter, so a committed go() to an agent (the chat drawer's
// "Open agent settings"; leg 7's palette) always shows its row (reference
// spec 10, item 18). Defined at script load as a safe no-op: before the
// studio area's init there is no Agents pane and nothing to clear. init
// replaces it with the real one (the pane survives a visit to Chats: only
// setActiveSection destroys it, on Agents to Library).
window.App = window.App || {};
window.App.studio = window.App.studio || {};
window.App.studio.clearAgentFilter = function () {};

App.registerArea({
  id: 'studio',
  label: 'Agent Studio',
  icon: App.icons.studio,
  order: 20,

  // ── Hash-routing serialize/hydrate ──────────────────────────────────
  //
  // The bodies live in js/areas/studio/studio-route.js (App.studio.route, M31
  // F2 L02a): stateless, they read the area through its `_` fields and the
  // defineProperty getters init installs over `state`. The branch-order and
  // hydrate commentary moved with them.
  serializeState: function () {
    return App.studio.route.serialize(this);
  },

  hydrateState: function (sub, opts) {
    return App.studio.route.hydrate(this, sub, opts);
  },

  init: function (sidebar, content) {
    var self = this;

    // ── Per-instance state (promoted from closure locals to this.* so
    //    serializeState reads the right values) ────────────────────────────
    self._agents = [];
    self._allTools = [];
    self._allMcpSources = [];
    // Squawk 0080 — explicit load-success flag for `_allMcpSources`: true
    // once ANY fetch of the list has succeeded, never reset by a later
    // failure (a failed refresh keeps the last good cache, which is what the
    // MCPs tab then renders). While false the tab shows zero rows, so
    // `collectFormData` must not read "no checked toggles" as "detach all".
    self._mcpSourcesLoaded = false;
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
    // The shell's shared mutable state (M31 F2 L02a, DD1): every variable that
    // more than one section reads or writes lives here, so the modules split
    // out of this file reach it through ctx.state. Read and write `state.x`
    // at use time; never cache a mutable flag or object across an async
    // boundary. Generation tokens (selectSeq, editorGen) are captured BY VALUE
    // on purpose and compared against the live value when they resolve.
    var state = {
      dirty: false,
      snapshot: '',
      // The App.ui.tabs handle of the mounted agent editor -- used for
      // imperative select(tabId) calls after hydrate.
      tabHandle: null,
      // Monotonic token: an in-flight doSelect completes only while it is still
      // the latest select AND the user is still on Agents (closeOpenItem and the
      // outgoing-section cleanup bump it).
      selectSeq: 0,
      // Discard generation (M25 F2 L5): closeOpenItem bumps it; async editor
      // resolvers (saves, type waits) captured under an older one must not
      // resurrect state.
      editorGen: 0,
      // MCP Sources form state (the getters below expose it for serializeState)
      mcpSourceFormMode: null, // null | 'add' | 'edit'
      editingMcpSource: null,
      pendingMcpSourceId: self._pendingMcpSourceId || null,
      pendingMcpSourceFormMode: self._pendingMcpSourceFormMode || null,
      // Connectors form state
      connectorFormMode: null, // null | 'add' | 'edit'
      editingConnector: null,
      pendingConnectorId: self._pendingConnectorId || null,
      pendingConnectorFormMode: self._pendingConnectorFormMode || null,
      // Knowledge-base create form (M25 F3 L4a, DD8; squawk 0101)
      kbCreateMode: !!self._kbCreateMode,
      kbFocusFolderFor: null, // a just-created KB's id: focus its folder field on mount
      knowledgeDetailHandle: null, // { updateStatus(status), updateItems(items) } -- the poll target
      // The init() agents load while it is in flight (the shell writes it; the agents
      // list's pending-agent rule waits on it).
      bootLoad: null,
      // The Library section caches (store-fed); null until first load
      knowledgeBases: null,
      mcpSources: null,
      connectors: null,
      providersCache: null
    };

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
    // shared `state` object is the single source of truth.
    Object.defineProperty(self, '_mcpSourceFormMode', {
      get: function () { return state.mcpSourceFormMode; },
      set: function (v) { state.mcpSourceFormMode = v; },
      configurable: true
    });
    Object.defineProperty(self, '_editingMcpSource', {
      get: function () { return state.editingMcpSource; },
      set: function (v) { state.editingMcpSource = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingMcpSourceId', {
      get: function () { return state.pendingMcpSourceId; },
      set: function (v) { state.pendingMcpSourceId = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingMcpSourceFormMode', {
      get: function () { return state.pendingMcpSourceFormMode; },
      set: function (v) { state.pendingMcpSourceFormMode = v; },
      configurable: true
    });

    // ── Connectors state (Mission 23 Flight 2 Leg 2; M25 F3 L4a) ─────────
    // The MCP-sources shape above (M25 F3 L4a, DD8: connector URLs): formMode
    // + editingConnector drive the editor, the pending pair handles the
    // hydrate-vs-fetch race, all exposed for serializeState.
    Object.defineProperty(self, '_connectorFormMode', {
      get: function () { return state.connectorFormMode; },
      set: function (v) { state.connectorFormMode = v; },
      configurable: true
    });
    Object.defineProperty(self, '_editingConnector', {
      get: function () { return state.editingConnector; },
      set: function (v) { state.editingConnector = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingConnectorId', {
      get: function () { return state.pendingConnectorId; },
      set: function (v) { state.pendingConnectorId = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingConnectorFormMode', {
      get: function () { return state.pendingConnectorFormMode; },
      set: function (v) { state.pendingConnectorFormMode = v; },
      configurable: true
    });

    // ── Knowledge-base create form (M25 F3 L4a, DD8; squawk 0101) ───────
    // `knowledge/new` (the route's `~new`): a create form in the detail pane.
    Object.defineProperty(self, '_kbCreateMode', {
      get: function () { return state.kbCreateMode; },
      set: function (v) { state.kbCreateMode = !!v; },
      configurable: true
    });

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

    content.innerHTML =
      '<div class="studio-section-content"></div>' +
      '<div class="studio-editor"></div>';
    var sectionContentEl = content.querySelector('.studio-section-content');
    var editorEl = content.querySelector('.studio-editor');

    // The agent form's reading and dirty tracking (M31 F2 L03): collectFormData,
    // getFormSnapshot, checkDirty. Created first -- the model picker and the
    // editor controller take it.
    var formData = App.studio.agentFormData.create({
      self: self,
      state: state,
      editorEl: editorEl,
      // call-time: the current editor mount's shell (the controller is created after)
      shell: function () { return controller ? controller.shell() : null; }
    });

    // The model picker's wiring (M31 F2 L03): the model fetch, capability chips,
    // provider-change side effects and the VRAM check.
    var picker = App.studio.agentModelPicker.create({
      self: self, state: state, editorEl: editorEl, formData: formData
    });

    var controller = null; // the agent editor controller (created below, after agentData)
    var agentsListMod = null; // the agents-list handle (created below, after the controller)
    // The network layer, caches and loadAll (M31 F2 L02a): App.studio.agentData.
    // The Library and agent store subscriptions below stay here and call it.
    var agentData = App.studio.agentData.create({
      self: self,
      content: content,
      sectionContentEl: sectionContentEl,
      renderAgentList: function (scroll) { agentsListMod.render(scroll); }, // call-time getter into the list
      onSelfConfigChanged: function (updated) { agentsListMod.doSelect(updated); }
    });

    // The agent editor's controller (M31 F2 L03): renderEditor, tabs, Cancel,
    // Delete, Purge, Test provider, Save. Created after agentData (it takes the
    // handle). `list` is a CALL-TIME getter into the agents list, which is
    // created after the controller (selection calls renderEditor).
    controller = App.studio.agentEditorController.create({
      self: self,
      state: state,
      editorEl: editorEl,
      agentData: agentData,
      formData: formData,
      picker: picker,
      discardOpen: discardOpen_,
      writeUrl: writeUrl_,
      list: function () { return agentsListMod; } // call-time: the list is created after the controller
    });
    self._setActiveTab = controller.setActiveTab;

    // The Library list column (M25 F3 L4a, DD5; moved to libraryPane in M31 F2
    // L02b): the pane, its caches' sync, the gated fill, the selection rule and
    // the row-focus helpers. Created first -- the providers section and the
    // groups take its handle; it reaches the providers handle (created next,
    // from this handle) through a call-time getter.
    var providersSection = null;
    var libraryPane = App.studio.libraryPane.create({
      self: self,
      state: state,
      listHost: libraryListHost,
      sectionContent: function () { return sectionContentEl; },
      buildRootHeading: buildRootHeading,
      providers: function () { return providersSection; }
    });

    // The Model providers group's detail pane (sortie 02, DD4): a section
    // module that reaches studio only through this ctx. Studio keeps two views
    // of providers, both fed from App.store's `providers` collection: the
    // Agents list's gated `self._allProviders` (loadAll / the gated
    // subscription below, unchanged) and the Library cache `providersCache`
    // (the ungated subscription below).
    providersSection = App.studio.providersSection.create({
      host: function () { return sectionContentEl; },
      setDirty: function (b) { state.dirty = !!b; },
      editorGen: function () { return state.editorGen; },
      isActive: function () { return self._activeSection === 'providers'; },
      discardOpen: function () { discardOpen_(); },
      reloadLibrary: function (name) { return libraryPane.reload(name); },
      syncLibrarySelection: function (force) { libraryPane.sync(force); },
      libraryRowIndex: function (id) { return libraryPane.rowIndex(id); },
      focusLibraryRowNear: function (idx) { libraryPane.focusNear(idx); },
      focusLibraryGroupStart: function (id) { libraryPane.focusGroupStart(id); },
      cache: function () { return state.providersCache; },
      showRoot: function () { setActiveSection('library'); }
    });
    self._providersSection = providersSection;

    // The Library groups' section glue (M31 F2 L02b): knowledge, MCP,
    // connectors (+ the pending-item rule). One ctx, created after the pane and
    // the providers section; each module takes what it needs from it.
    var glueCtx = {
      self: self,
      state: state,
      pane: libraryPane,
      providers: providersSection,
      setActiveSection: setActiveSection,
      discardOpen: discardOpen_,
      writeUrl: writeUrl_,
      sectionContent: function () { return sectionContentEl; },
      fetchAgents: agentData.fetchAgents,
      buildRootHeading: buildRootHeading,
      agentData: agentData
    };
    var knowledgeGlue = App.studio.knowledgeGlue.create(glueCtx);
    var mcpGlue = App.studio.mcpGlue.create(glueCtx);
    glueCtx.mcp = mcpGlue; // the connector module takes it for the pending-item rule
    var connectorGlue = App.studio.connectorGlue.create(glueCtx);

    // The Agents list column and agent selection (M31 F2 L03). Created after the
    // controller (selection calls renderEditor); the controller and agentData reach
    // it through call-time getters (they are created before it).
    agentsListMod = App.studio.agentsList.create({
      self: self,
      state: state,
      listHost: agentsListHost,
      editorEl: editorEl,
      sectionContent: function () { return sectionContentEl; },
      agentData: agentData,
      controller: controller,
      updateContentVisibility: updateContentVisibility,
      setActiveSection: setActiveSection,
      writeUrl: writeUrl_,
      closeOpenItem: closeOpenItem
    });
    self._syncAgentSelection = agentsListMod.syncSelection;
    App.studio.clearAgentFilter = agentsListMod.clearFilter;
    self._enterCreate = agentsListMod.enterCreate;

    // The detail pane at a section root: a pane-size empty state whose action
    // opens that section's create form. Only built at a root (never while a
    // deep-link id is pending, so a cold item link never flashes it).
    // DD11: a section root with no editor open has one visible page
    // `h1` ("Agents" / "Library"). It lives and dies with the root state: the
    // Library root's is built here beside the empty state (every section
    // render starts by clearing sectionContentEl); the Agents root's is
    // synced by updateContentVisibility. With an editor open, `.editor-title`
    // is the page's only `h1`.
    function buildRootHeading(text) {
      var h = document.createElement('h1');
      h.className = 'start-page-title';
      h.setAttribute('data-testid', 'root-heading');
      h.textContent = text;
      return h;
    }

    // The Agents section: the list column plus, in the detail pane, the empty
    // state shown while no agent is open (the editor host covers it
    // otherwise; updateContentVisibility).
    function renderAgentsSection() {
      sectionContentEl.innerHTML = '';
      agentsListMod.resetEmpty();
      agentsListMod.render(true);
    }

    // closeOpenItem: tear every open item down to "nothing open" -- the agent
    // editor and create form, MCP and connector form modes, the knowledge
    // detail view (with its poll) -- and reset the dirty mirror. Called by
    // hydrateState for a SECTION-ROOT route, so clicking the current section
    // (or going to a destination root) still closes the open editor (F4 L7,
    // M10 F6 L7). It is NOT part of setActiveSection, where it would close an
    // item that is being opened. Bumping selectSeq invalidates an in-flight
    // doSelect.
    function closeOpenItem() {
      App.focusAfter.cancel();
      state.selectSeq += 1;
      state.editorGen += 1; // invalidates in-flight editor resolvers (saves, type waits)
      // Unconditional: a caller may have cleared _selectedAgent already (post-
      // delete, the save->delete race) while the stale editor DOM is mounted.
      agentsListMod.renderEmptyEditor();
      self._selectedAgent = null;
      self._selectedAgentLoaded = true;
      self._createMode = false;
      mcpGlue.reset();
      connectorGlue.reset();
      providersSection.reset();
      state.kbCreateMode = false;
      knowledgeGlue.reset();
      self._selectedKbId = null;
      self._selectedMcpAgentSourceId = null;
      self._pendingMcpAgentSourceId = null;
      state.dirty = false;
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
        state.dirty = false; // even a throwing teardown must not leave a phantom flag
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
      return { section: section, rowId: section === 'agents' ? agentsListMod.selection() : libraryPane.selection() };
    }

    function focusClosedItem_(closing) {
      // The user moved on: an Agents close must still be on Agents, a Library
      // close at the Library root (DD1) with nothing open.
      if (self._activeSection !== (closing.section === 'agents' ? 'agents' : 'library')) return;
      if (closing.section === 'agents') {
        if (!agentsListMod.isOpen() || self._selectedAgent || self._createMode) return;
        agentsListMod.focusNear(closing.rowId != null ? agentsListMod.indexOf(closing.rowId) : 0);
        return;
      }
      if (!libraryPane.isOpen() || !libraryPane.atRoot()) return;
      if (closing.rowId != null) libraryPane.focusNear(libraryPane.rowIndex(closing.rowId));
      else libraryPane.focusGroupStart(closing.section);
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
        state.selectSeq += 1;
        if (self._selectedAgent || self._createMode) agentsListMod.renderEmptyEditor();
        self._selectedAgent = null;
        self._selectedAgentLoaded = true;
        self._createMode = false;
        state.dirty = false;
      }
      if (prevSection === 'mcp-sources' && section !== 'mcp-sources') {
        mcpGlue.reset();
        state.dirty = false;
      }
      if (prevSection === 'connectors' && section !== 'connectors') {
        connectorGlue.reset();
        state.dirty = false;
      }
      if (prevSection === 'providers' && section !== 'providers') {
        providersSection.reset();
        state.dirty = false;
      }
      // Flight 6 leg 1 (L1-D2 site 1): leaving Knowledge for another
      // section stops the 5-second status poll AND clears the detail-view
      // selection (and the create form, M25 F3 L4a), so re-entering
      // an item mounts clean -- the
      // same contract the two blocks above already have. F6 L5 (L5-D3)
      // adds the dirty-mirror reset the mcp-sources/connectors blocks
      // above already carry — this site is reached directly by callers
      // that route through setActiveSection without going through
      // commit() first (e.g. hash-route hydration), so it needs its own
      // reset rather than relying on commit()'s.
      if (prevSection === 'knowledge' && section !== 'knowledge') {
        knowledgeGlue.reset();
        self._selectedKbId = null;
        state.kbCreateMode = false;
        state.kbFocusFolderFor = null;
        state.dirty = false;
      }
      // The sidebar hosts (M25 F3 L3/L4a, DD3 (a)/(e)): mountArea never re-runs
      // init between Agents and Library (one area module), so this is the one
      // owner of both list panes' lifetimes -- each created on entering its
      // destination and destroyed on leaving it, the outgoing one first, so
      // exactly one pane exists -- and of which host is visible. A move
      // between Library sections keeps the Library pane (one list).
      if (section === 'agents') {
        libraryPane.destroy();
        if (!agentsListMod.isOpen()) agentsListMod.create();
      } else {
        agentsListMod.destroy();
        if (!libraryPane.isOpen()) libraryPane.create();
      }
      agentsListHost.classList.toggle('is-hidden', section !== 'agents');
      libraryListHost.classList.toggle('is-hidden', section === 'agents');
      if (section === 'library') {
        sectionContentEl.innerHTML = '';
        libraryPane.renderEmpty();
        libraryPane.sync(false);
      } else if (section === 'providers') {
        providersSection.render();
      } else if (section === 'knowledge') {
        knowledgeGlue.render();
      } else if (section === 'mcp-sources') {
        mcpGlue.render();
      } else if (section === 'connectors') {
        connectorGlue.render();
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
      // DD11: the Agents root's `h1` exists only with no agent open.
      var rootH1 = sectionContentEl.querySelector(':scope > h1[data-testid="root-heading"]');
      var wantRootH1 = self._activeSection === 'agents' && !inAgentEditor;
      if (wantRootH1 && !rootH1) {
        sectionContentEl.insertBefore(buildRootHeading('Agents'), sectionContentEl.firstChild);
      } else if (!wantRootH1 && rootH1 && self._activeSection === 'agents') {
        sectionContentEl.removeChild(rootH1);
      }
    }

    // ── Single URL-write call site ──────────────────────────────────────
    function writeUrl_() {
      if (window.App && window.App.router) {
        App.router.sync('studio', self.serializeState());
      }
    }
    self._writeUrl = writeUrl_;

    // Studio keeps its own copies (self._agents / self._allProviders), so a
    // store load that Studio did not initiate (Chats activation, a Library KB
    // rename that invalidated 'agents') would otherwise leave them stale.
    // Studio's own loadAll assigns directly, so notifications are ignored
    // while one is in flight.  Detail-shaped objects are never written back
    // to the store: this only reads the notified (list-shaped) copy.
    // The Agents list re-renders on every notification (M25 F3 L3): it sits
    // beside the editor, so an open agent or create form no longer hides it.
    App.store.subscribe('agents', function (list) {
      if (agentData.loadAllDepth() > 0 || !self._agentsLoaded) return;
      self._agents = list;
      agentsListMod.render();
    });
    App.store.subscribe('providers', function (list) {
      if (agentData.loadAllDepth() > 0 || !self._agentsLoaded) return;
      self._allProviders = list;
      agentsListMod.render(); // the provider dots and names
    });
    // The Library list's five subscriptions (M25 F3 L4a; providers, sortie 02), registered once for
    // the page's lifetime: they always feed the section caches and re-attempt
    // a pending MCP / connector consume (an intent whose item was not cached),
    // and they render the list only while the Library pane exists. A bare
    // notification never scrolls the list.
    App.store.subscribe('providers', function (list) {
      state.providersCache = list;
      if (self._activeSection === 'providers' && providersSection.pendingMode() === 'edit') {
        providersSection.consume(true);
      }
      libraryPane.render();
    });
    App.store.subscribe('knowledge-bases', function (list) {
      state.knowledgeBases = list;
      libraryPane.render();
    });
    App.store.subscribe('mcp-sources', function (list) {
      state.mcpSources = list;
      if (self._activeSection === 'mcp-sources' && self._pendingMcpSourceFormMode === 'edit') {
        mcpGlue.tryConsumePending(true);
      }
      libraryPane.render();
    });
    App.store.subscribe('connectors', function (list) {
      state.connectors = list;
      if (self._activeSection === 'connectors' && state.pendingConnectorFormMode === 'edit') {
        connectorGlue.tryConsumePending(true);
      }
      libraryPane.render();
    });
    App.store.subscribe('agents', function () {
      libraryPane.render(); // the "{n} agents" counts
    });


    self._refresh = function () {
      agentData.loadAll(true).then(function () {
        // (b) Re-select ONLY on the Agents section: a refresh landing after
        // the user moved to Library must not re-open the stale agent (and
        // doSelect, not selectAgent -- a refresh never prompts).
        if (self._activeSection === 'agents' && self._selectedAgent) {
          var found = null;
          for (var i = 0; i < self._agents.length; i++) {
            if (self._agents[i].name === self._selectedAgent.name) { found = self._agents[i]; break; }
          }
          if (found) {
            agentsListMod.doSelect(found);
          } else {
            // The open agent is gone (deleted elsewhere): heal to the Agents
            // root in place, like a dead hydrate id -- never open another
            // agent (M25 F3 L3, DD8).
            closeOpenItem();
            agentsListMod.render();
            updateContentVisibility();
            App.router.sync('studio', 'agents');
          }
        }
      }).catch(function (err) {
        agentData.showLoadAllError(err, { nonDestructive: true });
      });
      // Studio activate on a Library section (the Library pane survived a trip
      // to Chats or Settings): force-get the four Library collections, so a
      // mutation made elsewhere shows within DD9's freshness bound (M25 F3
      // L4a; this replaces the MCP-only refetch). The hydrate that follows
      // joins these requests.
      if (libraryPane.isOpen() && libraryPane.isSection(self._activeSection)) libraryPane.load(true);
    };
    self._tryConsumePendingSelect = function (fresh) { agentsListMod.tryConsumePending(fresh); };
    // View of the shared dirty mirror (browser tests assert that a
    // discard/teardown left it false). The setter is a TEST SEAM only: it lets a
    // test plant a stale flag with no editor open to prove App.nav ignores it.
    Object.defineProperty(self, '_dirty', {
      get: function () { return state.dirty; },
      set: function (v) { state.dirty = !!v; },
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
        (self._activeSection === 'mcp-sources' && mcpGlue.isOpen()) ||
        (self._activeSection === 'connectors' && connectorGlue.isOpen()) ||
        (self._activeSection === 'providers' && providersSection.editorOpen()) ||
        (self._activeSection === 'knowledge' && knowledgeGlue.isOpen());
    }
    App.nav.registerSource('studio', {
      isDirty: function () { return state.dirty && editorOpen(); },
      discard: discardOpen_
    });

    // Pre-fetch MCP source types so the editor mount path doesn't have to
    // wait on the first network round-trip when the operator clicks "New
    // MCP Server" or deep-links to mcp-sources/{id}.
    mcpGlue.prefetchTypes();

    setActiveSection(self._activeSection || 'agents', { writeUrl: false });

    // The init() load, while it is in flight: the list's pending-agent rule reads it.
    var bootLoad = agentData.loadAll(true);
    state.bootLoad = bootLoad;
    var bootSettled = function () { state.bootLoad = null; };
    bootLoad.then(bootSettled, bootSettled);
    bootLoad.then(function () {
      if (self._activeSection === 'agents') {
        if (self._pendingSelectName) {
          // This load is fresh (it just resolved), so a pending id absent from
          // it is dead and heals to the Agents root.
          agentsListMod.resolvePending();
          if (self._selectedAgent) return;
        }
        // Guard: if the user entered create mode or selected an agent while
        // loadAll was still in flight, don't clobber the editor they are
        // already in. The editor is already correctly rendered and visible
        // from the doEnterCreateMode / doSelect Promise.all.then() path.
        if (self._createMode || self._selectedAgent) return;
        // Bare #agents shows the empty detail state beside the list; no
        // agent is auto-selected. The user picks a row (or "New").
        agentsListMod.renderEmptyEditor();
        updateContentVisibility();
      }
    }).catch(function (err) {
      agentData.showLoadAllError(err);
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
