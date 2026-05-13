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
        if (tab === 'general' || tab === 'knowledge' || tab === 'mcps' || tab === 'tools') {
          pendingTab = tab;
        } else {
          pendingTab = 'general';
        }
        this._pendingMcpAgentSourceId = pendingMcpAgentSourceId;  // consumed by renderMcpsTab
      }
    } else if (sub === 'agents' || !sub) {
      section = 'agents';
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

  init: function (content) {
    var self = this;

    // ── Per-instance state (promoted from closure locals to this.* so
    //    serializeState reads the right values) ────────────────────────────
    self._agents = [];
    self._allTools = [];
    self._allMcpSources = [];
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
      'Web': ['download_file', 'fetch_url', 'http_request', 'web_search']
    };

    // ── Holograph layout: no sidebar. content hosts a top sub-nav + 3 sub
    // blocks (Agents / Knowledge / MCP Sources). Only one sub block is
    // .active at a time (CSS: `.studio-sub.active { display: block }`).
    content.innerHTML =
      '<div class="area-header">' +
        '<div>' +
          '<span class="area-title">Studio</span>' +
          '<span class="area-sub">Configure and edit your agents</span>' +
        '</div>' +
        '<button class="btn btn-primary" id="studio-new-agent-btn" data-testid="new-agent-btn">' +
          '<svg class="icn icn-sm" viewBox="0 0 12 12" aria-hidden="true">' +
            '<path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
          '</svg>' +
          'New agent' +
        '</button>' +
      '</div>' +
      '<div class="studio-subnav" id="studio-subnav"></div>' +
      '<div class="studio-sub" id="sub-agents"></div>' +
      '<div class="studio-sub" id="sub-knowledge"></div>' +
      '<div class="studio-sub" id="sub-mcp-sources"></div>';

    var sectionNavEl = content.querySelector('#studio-subnav');
    var subAgentsEl = content.querySelector('#sub-agents');
    var subKnowledgeEl = content.querySelector('#sub-knowledge');
    var subMcpSourcesEl = content.querySelector('#sub-mcp-sources');
    var newAgentHeaderBtn = content.querySelector('#studio-new-agent-btn');

    // editorEl and agentListEl are populated lazily when renderAgentsSection
    // mounts the .studio-layout grid for the first time. Declared here so
    // all downstream closures (renderEditor, renderEmptyEditor, wireEditorEvents,
    // etc.) share the same binding and can be re-pointed on first render.
    var editorEl = null;
    var agentListEl = null;

    // ── Section navigation ─────────────────────────────────────────────

    App.layout.renderSectionNav(sectionNavEl, [
      { id: 'agents', label: 'Agents' },
      { id: 'knowledge', label: 'Knowledge' },
      // Post-F2 retrofit: replaced 'Tools' stub (id: 'tools') with the
      // real MCP Servers section (id: 'mcp-sources'). The URL slug uses
      // 'mcp-sources' (matches the /api/mcp-sources REST path) while the
      // user-facing label uses "MCP Servers" (mirrors the storage entity
      // vs. UI label asymmetry from M07 F1).
      { id: 'mcp-sources', label: 'MCP Servers' }
    ], self._activeSection, {
      onSelect: function (section) {
        // F5 leg 04: dirty gate — fires when leaving an editor-mounted
        // context. Two surfaces now host editors: the agent editor in
        // Agents and the MCP source editor in MCP Servers. Knowledge has
        // no editor.
        var commit = function () { setActiveSection(section); };
        var inEditingContext =
          (self._activeSection === 'agents' && self._selectedAgent) ||
          (self._activeSection === 'mcp-sources' && mcpSourceFormMode);
        if (dirty && inEditingContext) {
          App.confirmDialog({ onConfirm: commit });
        } else {
          commit();
        }
      },
      // Sidebar header omitted — the topbar's area buttons already name the
      // active area (highlighted via aria-current="page"), so a duplicate
      // <h2> in the sidebar is redundant.
      ariaLabel: 'Agent Studio sections'
    });

    function renderAgentsSection() {
      // Mount the .studio-layout grid on first activation; subsequent calls
      // just refresh the agent list. editorEl and agentListEl are re-bound
      // each time in case subAgentsEl was cleared.
      if (!subAgentsEl.querySelector('.studio-layout')) {
        subAgentsEl.innerHTML =
          '<div class="studio-layout">' +
            '<aside class="agents-pane">' +
              '<div class="agents-list" id="studio-agents-list" role="listbox" aria-label="Agents"></div>' +
            '</aside>' +
            '<div class="editor-pane" id="studio-editor-pane"></div>' +
          '</div>';
      }
      agentListEl = subAgentsEl.querySelector('#studio-agents-list');
      editorEl = subAgentsEl.querySelector('#studio-editor-pane');
      renderAgentList();
    }

    function renderKnowledgeSection() {
      if (!subKnowledgeEl.querySelector('.knowledge-stub-pane')) {
        App.studio.renderKnowledgeStub(subKnowledgeEl);
      }
    }

    // MCP Servers section — relocated from admin (post-F2 retrofit). Mirrors
    // admin.js's renderMcpSourcesPanel: editor branch waits for type list
    // then delegates to App.studio.renderMcpSourceEditor; grid branch
    // delegates to App.studio.renderMcpServersGrid. The orchestrator-side
    // callbacks bridge dirty-state + navigation.
    function renderMcpSourcesSection() {
      // Clear the sub-block so editor/grid mount fresh each call.
      subMcpSourcesEl.innerHTML = '';
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
          subMcpSourcesEl.innerHTML = '<div class="mcp-source-editor-pane" id="studio-mcp-editor-pane"></div>';
          var mcpEditorPaneEl = subMcpSourcesEl.querySelector('#studio-mcp-editor-pane');
          function doHandleBack() {
            mcpSourceFormMode = null;
            editingMcpSource = null;
            dirty = false;
            if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
            renderMcpSourcesSection();
          }
          App.studio.renderMcpSourceEditor(mcpEditorPaneEl, editingMcpSource, MCP_TYPES, {
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
                  var refreshBtn = subMcpSourcesEl.querySelector(
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
      // Grid branch — mount the .mcp-sources-grid wrapper, then render tiles.
      subMcpSourcesEl.innerHTML = '<div class="mcp-sources-grid" id="studio-mcp-grid"></div>';
      var mcpGridEl = subMcpSourcesEl.querySelector('#studio-mcp-grid');
      App.studio.renderMcpServersGrid(mcpGridEl, mcpSources, {
        selectedId: editingMcpSource ? editingMcpSource.id : null,
        onSelectMcpSource: selectMcpSource,
        onCreateMcpSource: enterCreateMcpSourceMode
      });
      fetchMcpSources_().then(function () {
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
          var gridEl = subMcpSourcesEl.querySelector('#studio-mcp-grid');
          if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load MCP sources.</div>';
        });
    }

    function populateMcpSourcesGrid() {
      // Stale-then guard: bail when no longer on mcp-sources OR when the
      // editor is mounted (no grid in the DOM to populate).
      if (self._activeSection !== 'mcp-sources') return;
      if (mcpSourceFormMode) return;
      var mcpGridEl = subMcpSourcesEl.querySelector('#studio-mcp-grid');
      if (!mcpGridEl) return; // guard: grid not yet mounted
      App.studio.renderMcpServersGrid(mcpGridEl, mcpSources, {
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

    function setActiveSection(section, options) {
      options = options || {};
      var writeUrl = options.writeUrl !== false; // default true
      var prevSection = self._activeSection;
      self._activeSection = section;
      // Toggle .active on the three sub-blocks — CSS: `.studio-sub.active { display: block }`.
      subAgentsEl.classList.toggle('active', section === 'agents');
      subKnowledgeEl.classList.toggle('active', section === 'knowledge');
      subMcpSourcesEl.classList.toggle('active', section === 'mcp-sources');
      // Update section-nav active state.
      App.layout.updateActiveSection(sectionNavEl, section);
      // Show/hide the header's New agent button — only relevant on Agents section.
      newAgentHeaderBtn.style.display = (section === 'agents') ? '' : 'none';
      // Reset MCP-section local state when leaving mcp-sources for another
      // section — closes the editor + clears formMode so a re-entry
      // re-mounts the grid.
      if (prevSection === 'mcp-sources' && section !== 'mcp-sources') {
        mcpSourceFormMode = null;
        editingMcpSource = null;
        dirty = false;
      }
      // Lazy-render each section the first time (or every time for MCP —
      // its grid/editor dispatch lives in renderMcpSourcesSection).
      if (section === 'knowledge') {
        renderKnowledgeSection();
      } else if (section === 'mcp-sources') {
        renderMcpSourcesSection();
      } else {
        renderAgentsSection();
      }
      if (writeUrl) writeUrl_();
    }
    self._setActiveSection = setActiveSection;

    // updateContentVisibility is no longer needed in the Holograph shape —
    // the agents sub-block's .studio-layout grid always shows both the agents
    // pane and the editor pane side-by-side. The editor-pane is simply empty
    // when no agent is selected (renderEmptyEditor clears it). The is-hidden
    // toggle on sectionContentEl/editorEl was Mission-08's single-panel
    // show/hide mechanism; the new shape uses CSS grid so both are always
    // visible within the active sub-block.
    function updateContentVisibility() {
      // No-op in Holograph shape. Kept as a function so all existing callers
      // (doSelect, doEnterCreateMode, doHandleBack, loadAll callback) compile
      // without modification. Safe to remove after L4.5 selector migration.
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
      return Promise.all([fetchAgents(), fetchTools(), fetchMcpSources(), fetchKnowledgeBases(), fetchProviders()])
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
      // agentListEl may be null before renderAgentsSection has run once.
      if (!agentListEl) return;
      agentListEl.innerHTML = '';
      var agents = self._agents;
      if (agents.length === 0 && !self._createMode) {
        var emptyDiv = document.createElement('div');
        emptyDiv.className = 'empty-canvas';
        emptyDiv.setAttribute('data-testid', 'agent-empty');
        // Message + CTA centered in the agents pane.
        var msg = document.createElement('p');
        msg.textContent = 'No agents yet. Create one to get started.';
        emptyDiv.appendChild(msg);
        var emptyBtn = document.createElement('button');
        emptyBtn.type = 'button';
        emptyBtn.className = 'btn btn-primary';
        emptyBtn.setAttribute('data-testid', 'new-agent-btn-empty');
        emptyBtn.textContent = 'Create your first agent';
        emptyBtn.addEventListener('click', enterCreateMode);
        emptyDiv.appendChild(emptyBtn);
        agentListEl.appendChild(emptyDiv);
        return;
      }
      for (var i = 0; i < agents.length; i++) {
        (function (agent) {
          var isActive = self._selectedAgent && self._selectedAgent.name === agent.name && !self._createMode;

          // ── Holograph agent card (`.agent-card` / `.agent-card-*`) ────
          var cardEl = document.createElement('div');
          cardEl.className = 'agent-card' + (isActive ? ' selected' : '');
          cardEl.setAttribute('data-testid', 'agent-item');
          cardEl.setAttribute('role', 'option');
          cardEl.dataset.name = agent.name;
          cardEl.setAttribute('aria-selected', isActive ? 'true' : 'false');
          cardEl.setAttribute('tabindex', '0');

          // Avatar — first two letters of the agent name, uppercased.
          var avatarEl = document.createElement('div');
          avatarEl.className = 'agent-card-avatar';
          avatarEl.textContent = (agent.name || 'A').slice(0, 2).toUpperCase();
          cardEl.appendChild(avatarEl);

          var bodyEl = document.createElement('div');
          bodyEl.className = 'agent-card-body';

          var titleEl = document.createElement('div');
          titleEl.className = 'agent-card-title';
          titleEl.textContent = agent.name;
          bodyEl.appendChild(titleEl);

          // Model label in monospace beneath the name.
          var modelLabel = agent.llm_model || '';
          var providerLabel = '';
          if (agent.provider_config_id) {
            for (var pi = 0; pi < self._allProviders.length; pi++) {
              if (self._allProviders[pi].id === agent.provider_config_id) {
                providerLabel = self._allProviders[pi].name || '';
                break;
              }
            }
          }
          var modelEl = document.createElement('div');
          modelEl.className = 'agent-card-model';
          if (providerLabel && modelLabel) {
            modelEl.textContent = providerLabel + ' · ' + modelLabel;
          } else if (providerLabel) {
            modelEl.textContent = providerLabel;
          } else if (modelLabel) {
            modelEl.textContent = modelLabel;
          } else {
            modelEl.textContent = 'no provider';
          }
          bodyEl.appendChild(modelEl);

          // Meta line — tool counts. Preserved as data-testid attrs for
          // L4.5 browser-test selector migration.
          var metaEl = document.createElement('div');
          metaEl.className = 'agent-card-meta';
          // F9 L3 (A-L3-3) — Two metric spans: built-in + MCP tool counts.
          var builtinCount = _countBuiltinTools(agent, self._allTools);
          var mcpCount = _countMcpTools(agent, self._allMcpSources);
          var toolCountSpan = document.createElement('span');
          toolCountSpan.setAttribute('data-testid', 'agent-tile-tool-count');
          toolCountSpan.textContent = _pluralize(builtinCount, 'tool', 'tools');
          metaEl.appendChild(toolCountSpan);
          var sep = document.createTextNode(' · ');
          metaEl.appendChild(sep);
          var mcpCountSpan = document.createElement('span');
          mcpCountSpan.setAttribute('data-testid', 'agent-tile-mcp-tool-count');
          mcpCountSpan.textContent = _pluralize(mcpCount, 'MCP tool', 'MCP tools');
          metaEl.appendChild(mcpCountSpan);

          // Capability chips — only render when caps are available.
          var renderer = window.App.admin && window.App.admin.renderCapabilityChips;
          var caps = null;
          if (agent.provider_config_id && agent.llm_model) {
            var byModel = self._modelCapsByProvider[agent.provider_config_id];
            if (byModel) caps = byModel[agent.llm_model];
          }
          if (renderer && Array.isArray(caps)) {
            var capsSep = document.createTextNode(' ');
            metaEl.appendChild(capsSep);
            var capsWrap = document.createElement('span');
            capsWrap.className = 'agent-tile-caps';
            capsWrap.innerHTML = renderer(caps);
            metaEl.appendChild(capsWrap);
          }

          bodyEl.appendChild(metaEl);
          cardEl.appendChild(bodyEl);

          cardEl.addEventListener('click', function () { selectAgent(agent); });
          cardEl.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              selectAgent(agent);
            }
          });

          agentListEl.appendChild(cardEl);
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
      Promise.all([refreshToolConfigsCache(), refreshMcpSourcesCache()]).then(function () {
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
      Promise.all([refreshToolConfigsCache(), refreshMcpSourcesCache()]).then(function () {
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
      if (editorEl) editorEl.innerHTML = '';
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

    function renderModelCapabilities() {
      var capsEl = editorEl.querySelector('.model-capabilities');
      var selectEl = editorEl.querySelector('#studio-model');
      if (!capsEl || !selectEl) return;
      var modelId = selectEl.value;
      var caps = modelCapsBy[modelId];
      var renderer = window.App.admin && window.App.admin.renderCapabilityChips;
      if (!modelId || !renderer || caps === undefined || caps === null) {
        capsEl.innerHTML = '';
        return;
      }
      capsEl.innerHTML = '<span class="model-capabilities-label">Capabilities:</span> ' + renderer(caps);
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
          failOpt.selected = !currentVal;
          failOpt.textContent = 'Failed to load models';
          selectEl.replaceChildren(failOpt);
          // Even on fetch failure, preserve the prior model value as a
          // "(custom)" option so the operator's selection survives the
          // switch regardless of whether the new provider is reachable.
          if (currentVal) {
            var customOpt = document.createElement('option');
            customOpt.value = currentVal;
            customOpt.selected = true;
            customOpt.textContent = currentVal + ' (custom)';
            selectEl.appendChild(customOpt);
          }
          delete selectEl.dataset.pendingValue;
          if (loadingEl) loadingEl.textContent = '';
          modelCapsBy = {};
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
          // Capture the current model value BEFORE clearing the picker so that
          // fetchModelsForProvider can preserve it as a "(custom)" option when
          // the new provider's model list doesn't contain it. Setting
          // selectedIndex = 0 wipes selectEl.value, and the fetch reads
          // currentVal from selectEl.value (falling back to pendingValue), so
          // we must stash the live value into pendingValue first.
          if (modelEl && modelEl.value) modelEl.dataset.pendingValue = modelEl.value;
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

      // F8 L4: scope to built-in-tool toggles only — F8's MCP source toggles
      // also use class="tool-toggle" for visual parity but carry data-mcp-source-id
      // (NOT data-tool); without the [data-tool] filter, they'd contaminate
      // enabled_tools/disabled_tools with `undefined` (from `dataset.tool`).
      var toggles = editorEl.querySelectorAll('.tool-toggle[data-tool]');
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
        var name = self._selectedAgent.name;
        data.name = name;
        fetch('/api/agents/' + encodeURIComponent(name), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
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

    // Wire the header "New agent" button (visible on Agents section only).
    // Dirty-gate: if already in an editing context, confirm before switching.
    newAgentHeaderBtn.addEventListener('click', function () {
      var inEditingContext =
        (self._activeSection === 'agents' && self._selectedAgent) ||
        (self._activeSection === 'mcp-sources' && mcpSourceFormMode);
      var commit = function () {
        setActiveSection('agents');
        enterCreateMode();
      };
      if (dirty && inEditingContext) {
        App.confirmDialog({ onConfirm: commit });
      } else {
        commit();
      }
    });

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
  deactivate: function () {}
});
