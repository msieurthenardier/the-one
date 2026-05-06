App.registerArea({
  id: 'admin',
  label: 'Settings',
  icon: App.icons.admin,
  order: 30,
  sidebarLabel: 'Settings categories',

  serializeState: function () {
    if (this._currentCategory === 'system') return 'system';
    if (this._currentCategory === 'providers') {
      if (this._providerFormMode === 'add') return 'providers/new';
      if (this._providerFormMode === 'edit' && this._editingProvider) {
        return 'providers/' + encodeURIComponent(this._editingProvider.id);
      }
      // Hydrate-vs-fetch race: pending id known but provider not yet loaded.
      if (this._pendingFormMode === 'add') return 'providers/new';
      if (this._pendingProviderId) {
        return 'providers/' + encodeURIComponent(this._pendingProviderId);
      }
      return 'providers';
    }
    if (this._currentCategory === 'tools') {
      if (this._toolFormMode === 'edit' && this._editingTool) {
        return 'tools/' + encodeURIComponent(this._editingTool.name);
      }
      // Hydrate-vs-fetch race: pending name known but tool detail not yet loaded.
      if (this._pendingToolName) {
        return 'tools/' + encodeURIComponent(this._pendingToolName);
      }
      return 'tools';
    }
    if (this._currentCategory === 'mcp-sources') {
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
    return this._currentCategory || 'system';
  },
  hydrateState: function (sub) {
    // Empty sub (user navigated to bare `#admin`) → reset to default 'system'.
    // Without this, currentCategory retains whatever it was (e.g. 'providers')
    // and the router's syncUrlFromState would rewrite the URL to that retained
    // state instead of the canonical default. F6 HAT regression.
    if (!sub) {
      if (this._setCategory) this._setCategory('system');
      this._pendingProviderId = null;
      this._pendingFormMode = null;
      this._pendingToolName = null;
      this._pendingToolFormMode = null;
      this._pendingMcpSourceId = null;
      this._pendingMcpSourceFormMode = null;
      return;
    }
    var origSub = sub;
    // Legacy redirect: #admin/general → #admin/system (F6 leg 01).
    if (sub === 'general') sub = 'system';

    var pendingId = null;
    var pendingFormMode = null;
    var pendingToolName_local = null;
    var pendingToolFormMode_local = null;
    var pendingMcpSourceId_local = null;
    var pendingMcpSourceFormMode_local = null;
    if (origSub === 'providers/new') {
      sub = 'providers';
      pendingFormMode = 'add';
    } else if (origSub && origSub.indexOf('providers/') === 0) {
      sub = 'providers';
      pendingFormMode = 'edit';
      // Strip trailing slash defensively; decodeURIComponent the id.
      var rest = origSub.slice('providers/'.length);
      if (rest.charAt(rest.length - 1) === '/') rest = rest.slice(0, -1);
      // Defensive: if extra path segments, take only the first.
      var slashIdx = rest.indexOf('/');
      if (slashIdx !== -1) rest = rest.slice(0, slashIdx);
      pendingId = rest ? decodeURIComponent(rest) : null;
    } else if (origSub === 'tools') {
      sub = 'tools';
    } else if (origSub && origSub.indexOf('tools/') === 0) {
      // F6 leg 03: parse the tool name out of `tools/{name}` so the
      // editor opens on direct-load / refresh.
      sub = 'tools';
      pendingToolFormMode_local = 'edit';
      var trest = origSub.slice('tools/'.length);
      if (trest.charAt(trest.length - 1) === '/') trest = trest.slice(0, -1);
      // Defensive: if extra path segments, take only the first.
      var tslashIdx = trest.indexOf('/');
      if (tslashIdx !== -1) trest = trest.slice(0, tslashIdx);
      pendingToolName_local = trest ? decodeURIComponent(trest) : null;
    } else if (origSub === 'mcp-sources/new') {
      sub = 'mcp-sources';
      pendingMcpSourceFormMode_local = 'add';
    } else if (origSub && origSub.indexOf('mcp-sources/') === 0) {
      // M07 F1 L5: parse the source id out of `mcp-sources/{id}` so the
      // editor opens on direct-load / refresh. Mirrors providers parsing.
      sub = 'mcp-sources';
      pendingMcpSourceFormMode_local = 'edit';
      var mrest = origSub.slice('mcp-sources/'.length);
      if (mrest.charAt(mrest.length - 1) === '/') mrest = mrest.slice(0, -1);
      // Defensive: if extra path segments, take only the first.
      var mslashIdx = mrest.indexOf('/');
      if (mslashIdx !== -1) mrest = mrest.slice(0, mslashIdx);
      pendingMcpSourceId_local = mrest ? decodeURIComponent(mrest) : null;
    }

    var validIds = ['system', 'providers', 'tools', 'mcp-sources'];
    if (validIds.indexOf(sub) === -1) return;

    // Set category FIRST — _setCategory wipes pending state on category change,
    // so we must set pending AFTER it to survive the wipe.
    if (this._setCategory) this._setCategory(sub);

    // Always overwrite pending state — including with nulls when the new
    // sub does not match providers/... — so navigating from
    // #admin/providers/new → #admin/system clears pending state.
    this._pendingProviderId = pendingId;
    this._pendingFormMode = pendingFormMode;
    this._pendingToolName = pendingToolName_local;
    this._pendingToolFormMode = pendingToolFormMode_local;
    this._pendingMcpSourceId = pendingMcpSourceId_local;
    this._pendingMcpSourceFormMode = pendingMcpSourceFormMode_local;

    // Sub-state changes within the same category (e.g.,
    // #admin/providers → #admin/providers/new) do NOT trigger _setCategory's
    // re-render path because currentCategory is unchanged. Fire consume
    // unconditionally so within-admin sub navigation actually opens the
    // editor.
    if (this._tryConsumePendingProvider) this._tryConsumePendingProvider();
    if (this._tryConsumePendingTool) this._tryConsumePendingTool();
    if (this._tryConsumePendingMcpSource) this._tryConsumePendingMcpSource();
  },

  init: function (sidebar, content) {
    var categories = [
      { id: 'system', label: 'General' },
      { id: 'providers', label: 'LLM Providers' },
      // F6 HAT inline fix #5: "Tools" → "Built-in Tools" — distinguishes
      // from future MCP / external tool surfaces. id stays 'tools' so URL
      // routing (#admin/tools/{name}) is unchanged.
      { id: 'tools', label: 'Built-in Tools' },
      // M07 F1 L5: MCP Servers section. UI label uses "Servers" (plural)
      // tracking the user-facing concept; the URL slug `mcp-sources` and
      // most JS identifiers track the storage entity (matches API path).
      { id: 'mcp-sources', label: 'MCP Servers' }
    ];
    var currentCategory = 'system';
    var categoryListEl;
    var contentEl;

    // Provider state
    var providers = null; // null until first fetch resolves; helper shows loading placeholder.
    var providerFormMode = null; // null | 'add' | 'edit'
    var editingProvider = null;
    var pendingProviderId = null;
    var pendingFormMode = null;

    // Orchestrator's mirror of the provider-editor sub-module's local `dirty`
    // flag (F6 leg 04). The editor sub-module is the source of truth for the
    // disabled-button flip; the orchestrator mirror is the source of truth
    // for the navigation gates (Back / section-nav / beforeunload). The
    // bridge is the onDirtyChange callback in renderProviderEditor's
    // callbacks object.
    var dirty = false;

    // Provider type list — fetched from /api/providers/types so dev-mode gating
    // for the `mock` type is enforced server-side. Populated by fetchProviderTypes().
    var PROVIDER_TYPES = [];
    var providerTypesReady = null;

    // MCP source type list — fetched from /api/mcp-sources/types. Populated by
    // fetchMcpSourceTypes(). Mirrors PROVIDER_TYPES lifecycle: cached once at
    // init, never invalidated mid-session. New transport literals require a
    // page reload to surface (M07 F1 L6).
    var MCP_TYPES = [];
    var mcpTypesReady = null;

    // Tools state (F6 leg 02)
    var toolConfigs = null; // null until first fetch resolves; helper shows loading placeholder.
    // Per-tool in-flight PUT tracker — second click while a PUT is pending is
    // dropped (toggle is also disabled in CSS via the `disabled` attr).
    // Closes the optimistic-update double-click race.
    var toolsInFlight = Object.create(null);

    // Tools editor state (F6 leg 03)
    var toolFormMode = null; // null | 'edit'
    var editingTool = null; // { name, description, enabled, config, schema } | null
    var pendingToolName = null; // hydrate-vs-fetch race
    var pendingToolFormMode = null; // null | 'edit'

    // MCP Sources state (M07 F1 L5)
    var mcpSources = null; // null until first fetch resolves
    var mcpSourceFormMode = null; // null | 'add' | 'edit'
    var editingMcpSource = null;
    var pendingMcpSourceId = null;
    var pendingMcpSourceFormMode = null;

    function fetchProviderTypes() {
      providerTypesReady = fetch('/api/providers/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { PROVIDER_TYPES = types; })
        .catch(function () { PROVIDER_TYPES = []; });
      return providerTypesReady;
    }

    function fetchMcpSourceTypes() {
      mcpTypesReady = fetch('/api/mcp-sources/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { MCP_TYPES = types; })
        .catch(function () { MCP_TYPES = []; });
      return mcpTypesReady;
    }

    // TYPE_DEFAULTS is static metadata kept unconditional — existing mock
    // providers (created when dev_mode was on) must still render correctly
    // when dev_mode is off. The dropdown filter prevents *new* mock
    // providers; it does not hide *existing* ones. The provider-type badge
    // suffix mapping (KNOWN_BADGE_TYPES) lives in providers-grid.js post-leg-02.
    var TYPE_DEFAULTS = {
      'ollama': { base_url: 'http://localhost:11434/v1', showBaseUrl: true, showApiKey: false },
      'openai-compatible': { base_url: '', showBaseUrl: true, showApiKey: true },
      'openai': { base_url: 'https://api.openai.com/v1', showBaseUrl: false, showApiKey: true },
      'anthropic': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: true },
      'mock': { base_url: '', showBaseUrl: false, showApiKey: false }
    };

    // ── beforeunload listener (F6 leg 04) ──────────────────────────────
    //
    // Registered ONCE at init() time (init runs once per area lifetime,
    // gated by app.js's initialized[areaId] check). The closure `dirty`
    // flag is the sole gate — when in another area, dirty is false (the
    // editor isn't mounted); when in admin with an unsaved provider edit,
    // dirty is true and the listener calls e.preventDefault() to surface
    // the browser's native "Leave site?" prompt.
    //
    // Do NOT remove on deactivate() — closure-flag gate handles all cross-
    // area transitions. Mirrors studio.js:127-149.
    window.addEventListener('beforeunload', function (e) {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    });

    // Build sidebar via the shared section-nav primitive (F6 leg 01).
    // Mount on a child div (not the sidebar panel itself) so the panel's
    // .area-admin class is preserved — the helper sets className on its
    // container, which would otherwise clobber the area scoping class.
    sidebar.innerHTML = '<div class="admin-section-nav"></div>';
    var sectionNavEl = sidebar.querySelector('.admin-section-nav');
    function doSetCategory(catId) {
      currentCategory = catId;
      providerFormMode = null;
      editingProvider = null;
      pendingProviderId = null;
      pendingFormMode = null;
      toolFormMode = null;
      editingTool = null;
      pendingToolName = null;
      pendingToolFormMode = null;
      mcpSourceFormMode = null;
      editingMcpSource = null;
      pendingMcpSourceId = null;
      pendingMcpSourceFormMode = null;
      dirty = false;
      if (window.App && window.App.router) App.router.replaceSub(currentCategory);
      App.layout.updateActiveSection(categoryListEl, currentCategory);
      renderContent();
    }
    function setCategory(catId) {
      // Dirty gate fires only when leaving an editor-mounted context.
      // Same-category clicks short-circuit naturally (no state change).
      // Mirrors studio.js:190-201 (F5 leg 04 setActiveSection).
      var inEditor = (currentCategory === 'providers' && providerFormMode)
                  || (currentCategory === 'tools' && toolFormMode)
                  || (currentCategory === 'mcp-sources' && mcpSourceFormMode);
      if (dirty && inEditor) {
        App.confirmDialog({ onConfirm: function () { doSetCategory(catId); } });
        return;
      }
      doSetCategory(catId);
    }
    App.layout.renderSectionNav(sectionNavEl, categories, currentCategory, {
      onSelect: setCategory,
      // Sidebar header omitted — the topbar's app-picker pill already names
      // the active area, so a duplicate <h2> in the sidebar is redundant.
      ariaLabel: 'Settings sections'
    });
    categoryListEl = sectionNavEl; // helper rendered into the container

    // Build content
    content.innerHTML = '<div class="admin-content"></div>';
    contentEl = content.querySelector('.admin-content');

    // ── Rendering ─────────────────────────────────────────────────────

    function renderContent() {
      if (currentCategory === 'system') {
        App.admin.renderSystemPage(contentEl);
      } else if (currentCategory === 'providers') {
        renderProvidersPanel();
      } else if (currentCategory === 'tools') {
        renderToolsPanel();
      } else if (currentCategory === 'mcp-sources') {
        renderMcpSourcesPanel();
      }
    }

    // ── Providers Panel ───────────────────────────────────────────────

    function renderProvidersPanel() {
      // Editor branch: delegate to provider-editor sub-module (F6 leg 03).
      if (providerFormMode) {
        // Reset orchestrator's dirty mirror BEFORE editor mount (F6 leg 04).
        // The fresh editor closure starts at dirty=false; the onDirtyChange
        // bridge only fires on the first user input. This handles the
        // create\u2192edit re-render case cleanly: the previous closure's
        // dirty=true would otherwise dangle in the orchestrator mirror.
        dirty = false;

        // Wait for provider types before rendering the editor (the type
        // dropdown depends on PROVIDER_TYPES). The gate moved here from
        // renderProviderForm() which the leg deleted.
        var ready = providerTypesReady || fetchProviderTypes();
        ready.then(function () {
          // doHandleBack hoisted into ready.then closure (per leg-04 OQ1
          // resolution: simpler placement; body uses orchestrator
          // closure-locals which mutate globally).
          function doHandleBack() {
            providerFormMode = null;
            editingProvider = null;
            dirty = false;
            if (window.App && window.App.router) App.router.replaceSub('providers');
            renderProvidersPanel();
          }
          App.admin.renderProviderEditor(contentEl, editingProvider, PROVIDER_TYPES, {
            onBack: function () {
              if (dirty) {
                App.confirmDialog({ onConfirm: doHandleBack });
                return;
              }
              doHandleBack();
            },
            onCancel: function () {
              // Create-mode Cancel: navigate back to grid (the editor's
              // Cancel handler only invokes onCancel when isCreate).
              // Cancel-when-dirty is intentional discard \u2014 no dialog gate.
              providerFormMode = null;
              editingProvider = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('providers');
              renderProvidersPanel();
            },
            onSaveSuccess: function (updated, isCreate) {
              // Editor sub-module owns the fetch; this callback only mutates
              // orchestrator state on success. For create\u2192edit transition,
              // re-render the editor with the new provider so Models +
              // Danger Zone + Test button now render.
              editingProvider = updated;
              providerFormMode = 'edit';
              dirty = false; // Save cleared dirty (sub-module recaptures snapshot).
              if (window.App && window.App.router) {
                App.router.replaceSub(self.serializeState());
              }
              if (isCreate) {
                renderProvidersPanel();
              }
              // Edit\u2192edit case: editor stays mounted; sub-module's local
              // snapshot recapture handles dirty reset. No re-render needed.
            },
            onDeleteSuccess: function () {
              providerFormMode = null;
              editingProvider = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('providers');
              renderProvidersPanel();
            },
            onDirtyChange: function (d) { dirty = d; },
            getTypeDefaults: function (type) { return TYPE_DEFAULTS[type]; }
          });
        });
        return;
      }
      // Grid branch: delegate to providers-grid sub-module.
      App.admin.renderProvidersGrid(contentEl, providers, {
        selectedId: editingProvider ? editingProvider.id : null,
        onSelectProvider: selectProvider,
        onCreateProvider: enterCreateMode
      });
      // The sub-module renders a "Loading providers\u2026" placeholder if providers
      // is null/undefined; it auto-populates the grid otherwise. Trigger fetch
      // to (re-)populate.
      fetchProviders();
    }

    function fetchProviders() {
      return fetch('/api/providers')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          providers = data;
          populateProviderGrid();
          self._tryConsumePendingProvider();
        })
        .catch(function () {
          var gridEl = contentEl.querySelector('.entity-tile-grid');
          if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load providers.</div>';
        });
    }

    // Re-populate the existing tile grid in-place AFTER fetch resolves \u2014
    // does NOT re-fire fetchProviders (would loop). Skips when the editor
    // branch is active (no grid is mounted).
    function populateProviderGrid() {
      if (providerFormMode) return;
      // Stale-then guard: if a fetchProviders kicked off while currentCategory
      // was 'providers' resolves AFTER the user has navigated to the System
      // page (e.g., area re-activate → hydrate-back-to-system race), the .then
      // would clobber the System content. Bail when no longer on providers.
      // F6 HAT regression.
      if (currentCategory !== 'providers') return;
      App.admin.renderProvidersGrid(contentEl, providers, {
        selectedId: editingProvider ? editingProvider.id : null,
        onSelectProvider: selectProvider,
        onCreateProvider: enterCreateMode
      });
    }

    function selectProvider(id) {
      var provider = findProvider(id);
      if (!provider) return; // pending-id race; will be re-attempted after fetch
      providerFormMode = 'edit';
      editingProvider = provider;
      pendingProviderId = null;
      pendingFormMode = null;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderProvidersPanel();
    }

    function enterCreateMode() {
      providerFormMode = 'add';
      editingProvider = null;
      pendingProviderId = null;
      pendingFormMode = null;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderProvidersPanel();
    }

    function findProvider(id) {
      if (!providers) return null;
      for (var i = 0; i < providers.length; i++) {
        if (providers[i].id === id) return providers[i];
      }
      return null;
    }

    // ── Tools Panel (F6 leg 02 / leg 03 editor) ───────────────────────

    function renderToolsPanel() {
      // Editor branch (F6 leg 03): delegate to tools-editor sub-module.
      if (toolFormMode === 'edit' && editingTool) {
        // Reset orchestrator's dirty mirror BEFORE editor mount (mirrors
        // provider-editor pattern at renderProvidersPanel:222). The fresh
        // editor closure starts at dirty=false; the onDirtyChange bridge
        // only fires on the first user input.
        dirty = false;
        App.admin.renderToolsEditor(contentEl, editingTool, {
          onBack: function () {
            if (dirty) {
              App.confirmDialog({ onConfirm: function () { exitEditor(); } });
              return;
            }
            exitEditor();
          },
          onCancel: function () {
            // Cancel sub-module restores original DOM (re-mounts with the
            // original toolDetail). Orchestrator stays in editor mode —
            // there is no navigate-to-grid on Cancel for tools (Cancel is
            // a snapshot-revert, not a "discard and exit").
            dirty = false;
          },
          onSaveSuccess: function (updated) {
            // Update the grid cache so an immediate Back lands on a current
            // grid (post-leg-02 cache fields: name, description, enabled, config).
            if (toolConfigs) {
              for (var i = 0; i < toolConfigs.length; i++) {
                if (toolConfigs[i].name === updated.name) {
                  toolConfigs[i] = {
                    name: updated.name,
                    description: updated.description,
                    enabled: updated.enabled,
                    config: updated.config
                  };
                  break;
                }
              }
            }
            // Merge the PUT response (4 fields) preserving the prior schema —
            // L1's upsert_tool_config response does NOT include `schema`. The
            // editor sub-module reads `toolDetail.schema` on each render.
            editingTool = {
              name: updated.name,
              description: updated.description,
              enabled: updated.enabled,
              config: updated.config,
              schema: editingTool.schema
            };
            dirty = false;
          },
          onDirtyChange: function (d) { dirty = d; }
        });
        return;
      }
      // Grid branch (L2)
      App.admin.renderToolsGrid(contentEl, toolConfigs, {
        onToggle: handleToolToggle,
        inFlight: toolsInFlight,
        onSelectTool: selectTool
      });
      fetchToolConfigs();
    }

    function exitEditor() {
      toolFormMode = null;
      editingTool = null;
      dirty = false;
      if (window.App && window.App.router) App.router.replaceSub('tools');
      renderToolsPanel();
    }

    function selectTool(name) {
      // ALWAYS fetches — the grid cache lacks `schema`, so a cache-lookup
      // short-circuit would always fall through to fetch anyway.
      return fetch('/api/tools/configs/' + encodeURIComponent(name))
        .then(function (r) {
          if (!r.ok) throw new Error('Fetch failed: ' + r.status);
          return r.json();
        })
        .then(function (detail) {
          editingTool = detail;
          toolFormMode = 'edit';
          pendingToolName = null;
          pendingToolFormMode = null;
          if (window.App && window.App.router) {
            App.router.replaceSub(self.serializeState());
          }
          renderToolsPanel();
        })
        .catch(function () {
          App.showFlash(contentEl, 'Failed to load ' + name + '.', true);
        });
    }

    function fetchToolConfigs() {
      return fetch('/api/tools/configs')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // Stale-then guard at cache-write: if the operator switched away
          // mid-fetch, do not clobber the cache.
          if (currentCategory !== 'tools') return;
          toolConfigs = data;
          populateToolGrid();
        })
        .catch(function () {
          if (currentCategory !== 'tools') return;
          var gridEl = contentEl.querySelector('.entity-tile-grid');
          if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load tools.</div>';
        });
    }

    function populateToolGrid() {
      // Stale-then guard: bail when no longer on tools (mirrors providers),
      // OR when the editor is mounted (no grid in the DOM to populate).
      if (currentCategory !== 'tools') return;
      if (toolFormMode) return;
      App.admin.renderToolsGrid(contentEl, toolConfigs, {
        onToggle: handleToolToggle,
        inFlight: toolsInFlight,
        onSelectTool: selectTool
      });
    }

    function handleToolToggle(name, newEnabled) {
      // Drop second click while a PUT is pending for this tool.
      if (toolsInFlight[name]) return;

      // Optimistic update: flip cache, re-render, PUT. Revert on failure.
      var idx = -1;
      for (var i = 0; i < toolConfigs.length; i++) {
        if (toolConfigs[i].name === name) { idx = i; break; }
      }
      if (idx === -1) return;
      var prev = toolConfigs[idx].enabled;
      toolConfigs[idx].enabled = newEnabled;
      toolsInFlight[name] = true;
      populateToolGrid();

      fetch('/api/tools/configs/' + encodeURIComponent(name), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newEnabled })  // omit config — L1 REPLACE preserves
      }).then(function (r) {
        if (!r.ok) throw new Error('PUT failed: ' + r.status);
      }).catch(function () {
        // Revert and surface the error via the existing admin wrapper.
        toolConfigs[idx].enabled = prev;
        showAdminFlash('Failed to update ' + name + '.', true);
      }).then(function () {
        // Always clear in-flight + re-render (success path also re-renders
        // to clear the `disabled` attr on the toggle).
        delete toolsInFlight[name];
        populateToolGrid();
      });
    }

    // ── MCP Sources Panel (M07 F1 L5) ────────────────────────────────

    function renderMcpSourcesPanel() {
      // Editor branch (M07 F1 L6 — replaces the L5 placeholder). Mirrors
      // renderProvidersPanel's editor branch shape: wait for type list,
      // then delegate to App.admin.renderMcpSourceEditor with the
      // orchestrator-side callbacks bridging dirty-state + navigation.
      if (mcpSourceFormMode) {
        // Reset orchestrator's dirty mirror BEFORE editor mount (mirrors
        // provider-editor pattern). The fresh editor closure starts at
        // dirty=false; the onDirtyChange bridge fires on first user input.
        dirty = false;
        var ready = mcpTypesReady || fetchMcpSourceTypes();
        ready.then(function () {
          function doHandleBack() {
            mcpSourceFormMode = null;
            editingMcpSource = null;
            dirty = false;
            if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
            renderMcpSourcesPanel();
          }
          App.admin.renderMcpSourceEditor(contentEl, editingMcpSource, MCP_TYPES, {
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
              renderMcpSourcesPanel();
            },
            onSaveSuccess: function (updated, isCreate) {
              editingMcpSource = updated;
              mcpSourceFormMode = 'edit';
              dirty = false;
              if (window.App && window.App.router) {
                App.router.replaceSub(self.serializeState());
              }
              if (isCreate) {
                // create→edit transition: re-render the editor so the
                // Danger Zone + edit-mode subtitle render with the
                // newly-assigned id.
                renderMcpSourcesPanel();
              }
            },
            onDeleteSuccess: function () {
              mcpSourceFormMode = null;
              editingMcpSource = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('mcp-sources');
              renderMcpSourcesPanel();
            },
            onDirtyChange: function (d) { dirty = d; }
          });
        });
        return;
      }
      // Grid branch
      App.admin.renderMcpServersGrid(contentEl, mcpSources, {
        selectedId: editingMcpSource ? editingMcpSource.id : null,
        onSelectMcpSource: selectMcpSource,
        onCreateMcpSource: enterCreateMcpSourceMode
      });
      fetchMcpSources();
    }

    function fetchMcpSources() {
      return fetch('/api/mcp-sources')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // Stricter stale-then guard at cache-write (mirrors tools pattern
          // at fetchToolConfigs; deliberately diverges from the older
          // providers pattern which writes the cache unconditionally).
          if (currentCategory !== 'mcp-sources') return;
          mcpSources = data;
          populateMcpSourcesGrid();
          self._tryConsumePendingMcpSource();
        })
        .catch(function () {
          if (currentCategory !== 'mcp-sources') return;
          var gridEl = contentEl.querySelector('.entity-tile-grid');
          if (gridEl) gridEl.innerHTML = '<div class="admin-loading">Failed to load MCP sources.</div>';
        });
    }

    function populateMcpSourcesGrid() {
      // Stale-then guard: bail when no longer on mcp-sources (mirrors
      // providers/tools), OR when the editor placeholder is mounted.
      if (currentCategory !== 'mcp-sources') return;
      if (mcpSourceFormMode) return;
      App.admin.renderMcpServersGrid(contentEl, mcpSources, {
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
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderMcpSourcesPanel();
    }

    function enterCreateMcpSourceMode() {
      mcpSourceFormMode = 'add';
      editingMcpSource = null;
      pendingMcpSourceId = null;
      pendingMcpSourceFormMode = null;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderMcpSourcesPanel();
    }

    function findMcpSource(id) {
      if (!mcpSources) return null;
      for (var i = 0; i < mcpSources.length; i++) {
        if (mcpSources[i].id === id) return mcpSources[i];
      }
      return null;
    }

    // ── Provider Form / Delete / Models / Ollama ─────────────────────
    // Migrated to admin/provider-editor.js + admin/provider-models.js in
    // F6 leg 03. The orchestrator's renderProvidersPanel above delegates
    // editor mounting to App.admin.renderProviderEditor; that sub-module
    // owns the form/test/save/delete fetches and invokes onSaveSuccess /
    // onDeleteSuccess callbacks for state mutation. The Ollama lifecycle
    // panel + basic-model-list both live in App.admin.renderProviderModels.

    // ── Flash Feedback ────────────────────────────────────────────────

    function showAdminFlash(msg, isError) {
      App.showFlash(contentEl, msg, isError);
    }

    // ── Helpers ────────────────────────────────────────────────────────

    var escapeHtml = App.escapeHtml;
    var escapeAttr = App.escapeAttr;

    // Store reference for activate() to reuse
    var self = this;
    self._refresh = function () {
      if (currentCategory === 'system') {
        App.admin.renderSystemPage(contentEl);
      } else if (currentCategory === 'providers' && !providerFormMode) {
        fetchProviders().then(function () {
          self._tryConsumePendingProvider();
        });
      } else if (currentCategory === 'tools' && toolFormMode === 'edit' && editingTool) {
        // Re-fetch the per-tool detail so the editor reflects external changes
        // (e.g., DB tweak) while the editor was mounted.
        selectTool(editingTool.name);
      } else if (currentCategory === 'tools') {
        fetchToolConfigs();
      } else if (currentCategory === 'mcp-sources') {
        fetchMcpSources();
      }
    };
    Object.defineProperty(self, '_currentCategory', {
      get: function () { return currentCategory; },
      configurable: true
    });
    Object.defineProperty(self, '_providerFormMode', {
      get: function () { return providerFormMode; },
      set: function (v) { providerFormMode = v; },
      configurable: true
    });
    Object.defineProperty(self, '_editingProvider', {
      get: function () { return editingProvider; },
      set: function (v) { editingProvider = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingProviderId', {
      get: function () { return pendingProviderId; },
      set: function (v) { pendingProviderId = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingFormMode', {
      get: function () { return pendingFormMode; },
      set: function (v) { pendingFormMode = v; },
      configurable: true
    });
    Object.defineProperty(self, '_toolFormMode', {
      get: function () { return toolFormMode; },
      set: function (v) { toolFormMode = v; },
      configurable: true
    });
    Object.defineProperty(self, '_editingTool', {
      get: function () { return editingTool; },
      set: function (v) { editingTool = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingToolName', {
      get: function () { return pendingToolName; },
      set: function (v) { pendingToolName = v; },
      configurable: true
    });
    Object.defineProperty(self, '_pendingToolFormMode', {
      get: function () { return pendingToolFormMode; },
      set: function (v) { pendingToolFormMode = v; },
      configurable: true
    });
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
    self._setCategory = function (sub) {
      if (currentCategory !== sub) {
        currentCategory = sub;
        providerFormMode = null;
        editingProvider = null;
        pendingProviderId = null;
        pendingFormMode = null;
        toolFormMode = null;
        editingTool = null;
        pendingToolName = null;
        pendingToolFormMode = null;
        mcpSourceFormMode = null;
        editingMcpSource = null;
        pendingMcpSourceId = null;
        pendingMcpSourceFormMode = null;
        App.layout.updateActiveSection(categoryListEl, currentCategory);
        renderContent();
      }
    };
    self._tryConsumePendingProvider = function () {
      if (!pendingProviderId && !pendingFormMode) return;
      if (pendingFormMode === 'add') {
        providerFormMode = 'add';
        editingProvider = null;
        pendingFormMode = null;
        pendingProviderId = null;
        renderProvidersPanel();
        return;
      }
      if (pendingFormMode === 'edit' && pendingProviderId) {
        var found = findProvider(pendingProviderId);
        if (found) {
          providerFormMode = 'edit';
          editingProvider = found;
          pendingProviderId = null;
          pendingFormMode = null;
          renderProvidersPanel();
        }
        // else: provider not in cache (unknown or fetch race not yet resolved);
        // _tryConsumePendingProvider re-fires after fetchProviders.then.
      }
    };
    self._tryConsumePendingTool = function () {
      if (!pendingToolName && !pendingToolFormMode) return;
      if (pendingToolFormMode === 'edit' && pendingToolName) {
        var name = pendingToolName;
        pendingToolName = null;
        pendingToolFormMode = null;
        selectTool(name);
      }
    };
    self._tryConsumePendingMcpSource = function () {
      if (!pendingMcpSourceId && !pendingMcpSourceFormMode) return;
      if (pendingMcpSourceFormMode === 'add') {
        mcpSourceFormMode = 'add';
        editingMcpSource = null;
        pendingMcpSourceFormMode = null;
        pendingMcpSourceId = null;
        renderMcpSourcesPanel();
        return;
      }
      if (pendingMcpSourceFormMode === 'edit' && pendingMcpSourceId) {
        var found = findMcpSource(pendingMcpSourceId);
        if (found) {
          mcpSourceFormMode = 'edit';
          editingMcpSource = found;
          pendingMcpSourceId = null;
          pendingMcpSourceFormMode = null;
          renderMcpSourcesPanel();
        }
        // else: source not in cache; will be re-attempted after fetchMcpSources resolves.
      }
    };

    // ── Init ──────────────────────────────────────────────────────────

    fetchProviderTypes();
    fetchMcpSourceTypes();
    renderContent();
  },

  activate: function () {
    if (this._refresh) {
      this._refresh();
    }
  },

  deactivate: function () {}
});
