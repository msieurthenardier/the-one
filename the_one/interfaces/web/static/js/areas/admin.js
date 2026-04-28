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
    return this._currentCategory || 'system';
  },
  hydrateState: function (sub) {
    if (!sub) return;
    var origSub = sub;
    // Legacy redirect: #admin/general → #admin/system (F6 leg 01).
    if (sub === 'general') sub = 'system';

    var pendingId = null;
    var pendingFormMode = null;
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
    }

    var validIds = ['system', 'providers'];
    if (validIds.indexOf(sub) === -1) return;

    // Set category FIRST — _setCategory wipes pending state on category change,
    // so we must set pending AFTER it to survive the wipe.
    if (this._setCategory) this._setCategory(sub);

    // Always overwrite pending state — including with nulls when the new
    // sub does not match providers/... — so navigating from
    // #admin/providers/new → #admin/system clears pending state.
    this._pendingProviderId = pendingId;
    this._pendingFormMode = pendingFormMode;

    // Sub-state changes within the same category (e.g.,
    // #admin/providers → #admin/providers/new) do NOT trigger _setCategory's
    // re-render path because currentCategory is unchanged. Fire consume
    // unconditionally so within-admin sub navigation actually opens the
    // editor.
    if (this._tryConsumePendingProvider) this._tryConsumePendingProvider();
  },

  init: function (sidebar, content) {
    var categories = [
      { id: 'system', label: 'System' },
      { id: 'providers', label: 'LLM Providers' }
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
      dirty = false;
      if (window.App && window.App.router) App.router.replaceSub(currentCategory);
      App.layout.updateActiveSection(categoryListEl, currentCategory);
      renderContent();
    }
    function setCategory(catId) {
      // Dirty gate fires only when leaving providers + editor-mounted
      // context. Same-category clicks short-circuit naturally (no state
      // change). Mirrors studio.js:190-201 (F5 leg 04 setActiveSection).
      var inEditor = currentCategory === 'providers' && providerFormMode;
      if (dirty && inEditor) {
        App.confirmDialog({ onConfirm: function () { doSetCategory(catId); } });
        return;
      }
      doSetCategory(catId);
    }
    App.layout.renderSectionNav(sectionNavEl, categories, currentCategory, {
      onSelect: setCategory,
      header: 'Settings',
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
    self._setCategory = function (sub) {
      if (currentCategory !== sub) {
        currentCategory = sub;
        providerFormMode = null;
        editingProvider = null;
        pendingProviderId = null;
        pendingFormMode = null;
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
