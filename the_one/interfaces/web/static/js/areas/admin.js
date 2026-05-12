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
      return;
    }
    var origSub = sub;
    // Legacy redirect: #admin/general → #admin/system (F6 leg 01).
    if (sub === 'general') sub = 'system';

    var pendingId = null;
    var pendingFormMode = null;
    var pendingToolName_local = null;
    var pendingToolFormMode_local = null;
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
    }

    var validIds = ['system', 'providers', 'tools'];
    // Mission 08 F2 L1: dev-mode-only Design Language gallery category.
    if (window.App && window.App.config && window.App.config.dev_mode) {
      validIds.push('design-language');
    }
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

    // Sub-state changes within the same category (e.g.,
    // #admin/providers → #admin/providers/new) do NOT trigger _setCategory's
    // re-render path because currentCategory is unchanged. Fire consume
    // unconditionally so within-admin sub navigation actually opens the
    // editor.
    if (this._tryConsumePendingProvider) this._tryConsumePendingProvider();
    if (this._tryConsumePendingTool) this._tryConsumePendingTool();
  },

  init: function (sidebar, content) {
    var categories = [
      { id: 'system', label: 'General' },
      { id: 'providers', label: 'LLM Providers' },
      // F6 HAT inline fix #5: "Tools" → "Built-in Tools" — distinguishes
      // from MCP / external tool surfaces. id stays 'tools' so URL routing
      // (#admin/tools/{name}) is unchanged. The MCP Servers section that
      // M07 F1 L5 originally placed here was relocated to the Studio nav
      // post-F2 retrofit (admin = system settings, studio = user-managed).
      { id: 'tools', label: 'Built-in Tools' }
    ];
    // Mission 08 F2 L1: dev-mode-only Design Language gallery category.
    // Boot-blocking fetch in app.js populates window.App.config before init.
    if (window.App && window.App.config && window.App.config.dev_mode) {
      categories.push({ id: 'design-language', label: 'Design Language' });
    }
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

    function fetchProviderTypes() {
      providerTypesReady = fetch('/api/providers/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { PROVIDER_TYPES = types; })
        .catch(function () { PROVIDER_TYPES = []; });
      return providerTypesReady;
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
      'mock': { base_url: '', showBaseUrl: false, showApiKey: false },
      'openrouter': { base_url: 'https://openrouter.ai/api/v1', showBaseUrl: true, showApiKey: true }
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
      dirty = false;
      if (window.App && window.App.router) App.router.replaceSub(currentCategory);
      App.layout.updateActiveSection(categoryListEl, currentCategory);
      renderContent();
    }
    function setCategory(catId) {
      // Dirty gate fires only when leaving an editor-mounted context.
      // Same-category clicks short-circuit naturally (no state change).
      // Mirrors studio.js's setActiveSection dirty gate.
      var inEditor = (currentCategory === 'providers' && providerFormMode)
                  || (currentCategory === 'tools' && toolFormMode);
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
      } else if (currentCategory === 'design-language') {
        App.admin.renderDesignLanguagePage(contentEl);
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

    // ── Init ──────────────────────────────────────────────────────────

    fetchProviderTypes();
    renderContent();
  },

  activate: function () {
    if (this._refresh) {
      this._refresh();
    }
  },

  deactivate: function () {}
});
