App.registerArea({
  id: 'admin',
  label: 'System',
  icon: App.icons.admin,
  order: 30,

  serializeState: function () {
    if (this._currentCategory === 'general') return 'general';
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
    return this._currentCategory || 'general';
  },
  // hydrateState(sub, {fresh}) renders exactly `sub`. `fresh` is the router's
  // hydrate ORIGIN (M25 F2 L4): true for a traversal, a typed hash and boot --
  // an item named by the URL may have been deleted since, so it is resolved
  // against a FRESH fetch and a dead id heals to the section root; false for an
  // intent go() (a click on a row), which opens the item from the cached list
  // without re-rendering the grid or refetching.
  hydrateState: function (sub, opts) {
    var fresh = !!(opts && opts.fresh);
    // Empty sub (user navigated to bare `#admin`) → reset to default 'general'.
    // Without this, currentCategory retains whatever it was (e.g. 'providers')
    // and the router's syncUrlFromState would rewrite the URL to that retained
    // state instead of the canonical default. F6 HAT regression.
    if (!sub) {
      if (this._setCategory) this._setCategory('general');
      this._pendingProviderId = null;
      this._pendingFormMode = null;
      this._pendingToolName = null;
      this._pendingToolFormMode = null;
      return;
    }
    var origSub = sub;
    // Legacy redirect: #admin/system → #admin/general (Flight 3 Leg 06 rename).
    // The 'system' sub-id was an interim slug; the canonical sub for the
    // General page is now 'general' (matches the visible label + avoids the
    // post-Leg-02 area-label-vs-sub-id confusion where the area is also
    // labeled "System"). Predecessor redirect: 'general' → 'system'
    // (F6 leg 01) — flipped back here.
    if (sub === 'system') sub = 'general';

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

    var validIds = ['general', 'providers', 'tools', 'knowledge'];
    // Mission 08 F2 L1: dev-mode-only Design Language gallery category.
    if (window.App && window.App.config && window.App.config.dev_mode) {
      validIds.push('design-language');
    }
    if (validIds.indexOf(sub) === -1) return;

    // Set category FIRST — _setCategory wipes pending state on category change,
    // so we must set pending AFTER it to survive the wipe.
    //
    // An ITEM sub inside the category that is already showing does not go
    // through _setCategory: it would re-render the grid (and refetch the list)
    // only for the item to replace it. The open item is closed in state and
    // the consume paths below render the item directly.
    var itemSub = !!(pendingFormMode || pendingToolFormMode_local);
    if (itemSub && this._currentCategory === sub) {
      if (this._closeOpenItem) this._closeOpenItem();
    } else if (this._setCategory) {
      this._setCategory(sub);
    }

    // Always overwrite pending state — including with nulls when the new
    // sub does not match providers/... — so navigating from
    // #admin/providers/new → #admin/general clears pending state.
    this._pendingProviderId = pendingId;
    this._pendingFormMode = pendingFormMode;
    this._pendingToolName = pendingToolName_local;
    this._pendingToolFormMode = pendingToolFormMode_local;

    // Sub-state changes within the same category (e.g.,
    // #admin/providers → #admin/providers/new) do NOT trigger _setCategory's
    // re-render path because currentCategory is unchanged. Fire consume
    // unconditionally so within-admin sub navigation actually opens the
    // editor -- an existing provider from the cache only for a non-fresh
    // (intent) hydrate.
    if (this._tryConsumePendingProvider) this._tryConsumePendingProvider(!fresh);
    // A provider still pending needs the list: a fresh hydrate always refetches
    // (the fetch also heals a dead id); an intent hydrate only when the cache
    // could not resolve it.
    if (this._pendingFormMode === 'edit' && this._pendingProviderId && this._fetchProviders) {
      this._fetchProviders();
    }
    if (this._tryConsumePendingTool) this._tryConsumePendingTool();
  },

  init: function (sidebar, content) {
    var categories = [
      { id: 'general', label: 'General' },
      { id: 'providers', label: 'LLM Providers' },
      // F6 HAT inline fix #5: "Tools" → "Built-in Tools" — distinguishes
      // from MCP / external tool surfaces. id stays 'tools' so URL routing
      // (#admin/tools/{name}) is unchanged. The MCP Servers section that
      // M07 F1 L5 originally placed here was relocated to the Studio nav
      // post-F2 retrofit (admin = system settings, studio = user-managed).
      { id: 'tools', label: 'Built-in Tools' },
      // M24 F06 L04, DD-7: app-wide chunking + monitoring settings. The
      // Knowledge *inventory* (create/rename/delete a knowledge base) lives
      // in Studio, not here — this panel is app-wide settings only.
      { id: 'knowledge', label: 'Knowledge' }
    ];
    // Mission 08 F2 L1: dev-mode-only Design Language gallery category.
    // Boot-blocking fetch in app.js populates window.App.config before init.
    if (window.App && window.App.config && window.App.config.dev_mode) {
      categories.push({ id: 'design-language', label: 'Design Language' });
    }
    var currentCategory = 'general';
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
    // for the leave guard (App.nav source, registered below). The
    // bridge is the onDirtyChange callback in renderProviderEditor's
    // callbacks object.
    var dirty = false;
    // Discard generation (M25 F2 L5): the App.nav discard() bumps it; an async
    // resolver captured under an older generation (an in-flight save, the
    // provider-types wait) must not resurrect the editor state it tore down.
    var editorGen = 0;
    // Set by a discard that tore an editor down in STATE only: the editor DOM is
    // still mounted, so the next _setCategory must re-render even though no item
    // is open any more. Cleared by every panel render.
    var editorDomStale = false;

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
      'ollama': { base_url: 'http://localhost:11434/v1', showBaseUrl: true, showApiKey: false, showNumCtx: true, showReasoningEffort: true },
      'openai-compatible': { base_url: '', showBaseUrl: true, showApiKey: true, showReasoningEffort: true },
      'openai': { base_url: 'https://api.openai.com/v1', showBaseUrl: false, showApiKey: true, showReasoningEffort: true },
      'anthropic': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: true, showThinkingEnabled: true, showReasoningEffort: true },
      // anthropic-plan (M19 F01 L03): OAuth sign-in instead of an API key —
      // no api-key input EVER (mission criterion), base_url hidden but
      // force-submitted from this default (the model requires it and the
      // type is NOT URL-validation-skipped). Thinking/reasoning surface
      // mirrors 'anthropic' so extended-thinking parity is reachable.
      // showPlanSignIn drives the sign-in section's type-driven show/hide.
      'anthropic-plan': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: false, showThinkingEnabled: true, showReasoningEffort: true, showPlanSignIn: true },
      'mock': { base_url: '', showBaseUrl: false, showApiKey: false },
      'openrouter': { base_url: 'https://openrouter.ai/api/v1', showBaseUrl: true, showApiKey: true, showReasoningEffort: true }
    };

    // Build sidebar via the shared section-nav primitive (F6 leg 01).
    // Mount on a child div (not the sidebar panel itself) so the panel's
    // .area-admin class is preserved — the helper sets className on its
    // container, which would otherwise clobber the area scoping class.
    // F2 Leg 2 (A.10): use <nav> instead of <div> so the section-nav
    // composes as a landmark. The shared renderSectionNav helper drops
    // role="group" (which was the prior compromise when the container
    // was a plain <div>) — nav role is now load-bearing.
    sidebar.innerHTML = '<nav class="admin-section-nav"></nav>';
    var sectionNavEl = sidebar.querySelector('.admin-section-nav');
    // Section nav is a user INTENT: it routes through the router (M25 F2 L3),
    // whose leave guard asks about unsaved changes exactly once. The former
    // in-area dirty gate here is gone, so a dirty editor never prompts twice.
    // A click on the current category goes to that category's root, which
    // closes an open editor (_setCategory's same-category close).
    var CATEGORY_ROUTE_SECTION = { knowledge: 'knowledge-indexing' };
    function setCategory(catId) {
      App.router.go(App.router.href({
        destination: 'settings',
        section: CATEGORY_ROUTE_SECTION[catId] || catId
      }));
    }
    App.layout.renderSectionNav(sectionNavEl, categories, currentCategory, {
      onSelect: setCategory,
      // Sidebar header omitted — the top bar's destination buttons already
      // name the active destination (aria-current="page"), so a duplicate
      // <h2> in the sidebar is redundant.
      ariaLabel: 'Settings sections'
    });
    categoryListEl = sectionNavEl; // helper rendered into the container

    // Build content
    content.innerHTML = '<div class="admin-content"></div>';
    contentEl = content.querySelector('.admin-content');

    // ── Rendering ─────────────────────────────────────────────────────

    function renderContent() {
      if (currentCategory === 'general') {
        App.admin.renderSystemPage(contentEl);
      } else if (currentCategory === 'providers') {
        renderProvidersPanel();
      } else if (currentCategory === 'tools') {
        renderToolsPanel();
      } else if (currentCategory === 'knowledge') {
        renderKnowledgePanel();
      } else if (currentCategory === 'design-language') {
        App.admin.renderDesignLanguagePage(contentEl);
      }
    }

    // ── Providers Panel ───────────────────────────────────────────────

    function renderProvidersPanel() {
      editorDomStale = false;
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
        var mountGen = editorGen;
        ready.then(function () {
          if (mountGen !== editorGen) return; // discarded while the types loaded
          App.admin.renderProviderEditor(contentEl, editingProvider, PROVIDER_TYPES, {
            // Back is a user INTENT (M25 F2 L4): a pushed go() to the section
            // root. The router's leave guard is the only prompt (the former
            // inline App.confirmDialog is gone, so Continue never asks
            // twice); the root hydrate closes the editor and resets `dirty`.
            onBack: function () {
              App.router.go(App.router.href({ destination: 'settings', section: 'providers' }));
            },
            onCancel: function () {
              // Create-mode Cancel: back to the grid (the editor's Cancel
              // handler only invokes onCancel when isCreate). Cancel-when-dirty
              // is intentional discard -- no gate -- so this is a bypass go()
              // REPLACING the create entry (Back must not land on a stale
              // create form).
              App.router.go(App.router.href({ destination: 'settings', section: 'providers' }),
                { replace: true, bypassGuard: true });
            },
            onSaveSuccess: function (updated, isCreate) {
              if (mountGen !== editorGen) return; // discarded mid-save: no resurrection
              // Editor sub-module owns the fetch; this callback only mutates
              // orchestrator state on success. For create\u2192edit transition,
              // re-render the editor with the new provider so Models +
              // Danger Zone + Test button now render.
              editingProvider = updated;
              providerFormMode = 'edit';
              dirty = false; // Save cleared dirty (sub-module recaptures snapshot).
              if (window.App && window.App.router) {
                App.router.sync('admin', self.serializeState());
              }
              if (isCreate) {
                renderProvidersPanel();
              }
              // Edit\u2192edit case: editor stays mounted; sub-module's local
              // snapshot recapture handles dirty reset. No re-render needed.
            },
            onDeleteSuccess: function () {
              if (mountGen !== editorGen) return;
              // Post-delete navigation: a bypass go() replacing the deleted
              // provider's entry. Discard first so a stray dirty flag cannot
              // outlive the deleted item.
              self._discardEditor();
              App.router.go(App.router.href({ destination: 'settings', section: 'providers' }),
                { replace: true, bypassGuard: true });
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

    // One list request at a time: a render's grid fetch and a fresh hydrate's
    // fetch (hydrateState) are the same request.
    var providersInFlight = null;
    function fetchProviders() {
      if (providersInFlight) return providersInFlight;
      var p = fetchProvidersNow();
      providersInFlight = p;
      var clear = function () { if (providersInFlight === p) providersInFlight = null; };
      p.then(clear, clear);
      return p;
    }

    function fetchProvidersNow() {
      return App.store.get('providers', { force: true })
        .then(function (data) {
          providers = data;
          populateProviderGrid();
          self._tryConsumePendingProvider();
          // A pending id absent from a FRESH fetch is dead (deleted meanwhile,
          // or a stale link): never keep it in the URL. Heal to the section
          // root in place.
          if (pendingFormMode === 'edit' && pendingProviderId && !findProvider(pendingProviderId)) {
            pendingProviderId = null;
            pendingFormMode = null;
            if (window.App && window.App.router) App.router.sync('admin', self.serializeState());
          }
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

    // Opening a provider / the create form from the grid are user INTENTS:
    // pushed go()s (Back returns to the grid), hydrated with the cached list.
    function selectProvider(id) {
      if (!findProvider(id)) return; // pending-id race; will be re-attempted after fetch
      App.router.go(App.router.href({ destination: 'settings', section: 'providers', id: id }));
    }

    function enterCreateMode() {
      App.router.go(App.router.href({ destination: 'settings', section: 'providers', create: true }));
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
      editorDomStale = false;
      // Editor branch (F6 leg 03): delegate to tools-editor sub-module.
      if (toolFormMode === 'edit' && editingTool) {
        // Reset orchestrator's dirty mirror BEFORE editor mount (mirrors
        // provider-editor pattern at renderProvidersPanel:222). The fresh
        // editor closure starts at dirty=false; the onDirtyChange bridge
        // only fires on the first user input.
        dirty = false;
        var toolGen = editorGen;
        App.admin.renderToolsEditor(contentEl, editingTool, {
          // Back is a user INTENT (M25 F2 L4): a pushed go() to the section
          // root. The router's leave guard is the only prompt (no inline
          // App.confirmDialog); the root hydrate closes the editor.
          onBack: function () {
            App.router.go(App.router.href({ destination: 'settings', section: 'tools' }));
          },
          onCancel: function () {
            // Cancel sub-module restores original DOM (re-mounts with the
            // original toolDetail). Orchestrator stays in editor mode —
            // there is no navigate-to-grid on Cancel for tools (Cancel is
            // a snapshot-revert, not a "discard and exit").
            dirty = false;
          },
          onSaveSuccess: function (updated) {
            if (toolGen !== editorGen || !editingTool) return; // discarded mid-save
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
        onSelectTool: openTool
      });
      fetchToolConfigs();
    }

    // A tool row click is a user INTENT: a pushed go() (Back returns to the
    // grid). selectTool (below) is the hydrate/consume path that loads the
    // tool's detail.
    function openTool(name) {
      App.router.go(App.router.href({ destination: 'settings', section: 'tools', id: name }));
    }

    function selectTool(name) {
      // ALWAYS fetches — the grid cache lacks `schema`, so a cache-lookup
      // short-circuit would always fall through to fetch anyway.
      return fetch('/api/tools/configs/' + encodeURIComponent(name))
        .then(function (r) {
          if (r.status === 404) { var gone = new Error('tool not found'); gone.gone = true; throw gone; }
          if (!r.ok) throw new Error('Fetch failed: ' + r.status);
          return r.json();
        })
        .then(function (detail) {
          // Stale-then guard: this fetch may have kicked off in a tools
          // editor context (e.g., admin.activate()→_refresh re-fetches the
          // current tool on area re-entry). If the synchronous hydrateState
          // path that ran AFTER the fetch started has since cleared
          // currentCategory to something other than 'tools' (cross-area
          // back-and-forth race), abandon the mutation — otherwise the
          // then-block would clobber the now-correct page render.
          if (currentCategory !== 'tools') return;
          editingTool = detail;
          toolFormMode = 'edit';
          pendingToolName = null;
          pendingToolFormMode = null;
          if (window.App && window.App.router) {
            App.router.sync('admin', self.serializeState());
          }
          renderToolsPanel();
        })
        .catch(function (err) {
          if (currentCategory !== 'tools') return;
          if (err && err.gone) {
            // Dead id (an unknown name in the URL, or a tool removed while its
            // editor was open): close any editor and heal the URL to the
            // section root in place -- nothing is left pending.
            pendingToolName = null;
            pendingToolFormMode = null;
            toolFormMode = null;
            editingTool = null;
            dirty = false;
            App.router.sync('admin', 'tools');
            renderToolsPanel();
            return;
          }
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
        onSelectTool: openTool
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

    // ── Knowledge Panel (F6 leg 04, DD-7) ─────────────────────────────
    // No grid/editor split — the whole category is one form, so it delegates
    // straight to the sub-module and bridges its dirty state onto the shared
    // `dirty` mirror exactly as the provider/tools editors do.
    function renderKnowledgePanel() {
      editorDomStale = false;
      dirty = false;
      App.admin.renderKnowledgeSettingsPage(contentEl, {
        onDirtyChange: function (d) { dirty = d; }
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
      if (currentCategory === 'general') {
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
      } else if (currentCategory === 'knowledge' && !dirty) {
        // Mirrors the providers branch above: skip the refetch while dirty
        // so a cross-area-and-back trip never silently clobbers an unsaved
        // edit. A dirty knowledge panel simply keeps showing its own state.
        renderKnowledgePanel();
      }
    };
    // Leave-guard source (M25 F2 L5, DD5). `isDirty` is the
    // editor-open predicate registered via App.nav.registerSource: the shared `dirty` flag AND an editor actually
    // open, so a stale flag can never raise a phantom prompt or beforeunload.
    // `discard` is teardown only (never a URL write) and bumps editorGen.
    function editorOpen() {
      return (currentCategory === 'providers' && !!providerFormMode)
        || (currentCategory === 'tools' && !!toolFormMode)
        || currentCategory === 'knowledge';
    }
    self._discardEditor = function () {
      editorGen += 1;
      try {
        // Knowledge settings is one form: discard is just dirty=false (re-entry
        // re-renders from the saved settings). Otherwise tear the item down.
        if (currentCategory !== 'knowledge') {
          self._closeOpenItem();
          editorDomStale = true;
        }
      } finally {
        dirty = false;
      }
    };
    if (window.App && window.App.nav) {
      window.App.nav.registerSource('admin', {
        isDirty: function () { return dirty && editorOpen(); },
        discard: function () { self._discardEditor(); }
      });
    }
    // View of the shared dirty mirror (browser tests). The setter is a TEST SEAM
    // only: it plants a stale flag with no editor open (App.nav must ignore it).
    Object.defineProperty(self, '_dirty', {
      get: function () { return dirty; },
      set: function (v) { dirty = !!v; },
      configurable: true
    });
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
    // Section-root semantics: hydrating a category renders exactly that
    // category. A category CHANGE resets everything; the SAME category with an
    // item open (provider editor/create, tool editor) closes it, so clicking
    // the current category -- or going to its root -- returns to the grid.
    self._setCategory = function (sub) {
      // Knowledge has no grid/editor split (the whole panel is the form), so
      // re-hydrating it re-renders from the saved settings: Continue discards.
      var itemOpen = !!(providerFormMode || toolFormMode || currentCategory === 'knowledge');
      if (currentCategory !== sub || itemOpen || editorDomStale) {
        editorGen += 1;
        currentCategory = sub;
        providerFormMode = null;
        editingProvider = null;
        pendingProviderId = null;
        pendingFormMode = null;
        toolFormMode = null;
        editingTool = null;
        pendingToolName = null;
        pendingToolFormMode = null;
        dirty = false;
        App.layout.updateActiveSection(categoryListEl, currentCategory);
        renderContent();
      }
    };
    // Close the open provider/tool item in STATE only (no render): an item
    // hydrate inside the category that is already showing replaces it.
    self._closeOpenItem = function () {
      editorGen += 1; // a teardown invalidates any in-flight editor resolver
      providerFormMode = null;
      editingProvider = null;
      pendingProviderId = null;
      pendingFormMode = null;
      toolFormMode = null;
      editingTool = null;
      pendingToolName = null;
      pendingToolFormMode = null;
      dirty = false;
    };
    self._fetchProviders = function () { return fetchProviders(); };
    // `allowCache` false (a fresh hydrate) leaves an existing provider pending:
    // the cached list may hold one deleted since, so fetchProviders resolves it.
    // A create form needs no list and always opens.
    self._tryConsumePendingProvider = function (allowCache) {
      if (!pendingProviderId && !pendingFormMode) return;
      if (pendingFormMode === 'add') {
        providerFormMode = 'add';
        editingProvider = null;
        pendingFormMode = null;
        pendingProviderId = null;
        renderProvidersPanel();
        return;
      }
      if (pendingFormMode === 'edit' && pendingProviderId && allowCache !== false) {
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
        // The pending slot stays set until the detail loads (selectTool clears
        // it on success, or heals on a 404), so serializeState keeps the URL
        // on `tools/{name}` meanwhile instead of flickering to the root.
        selectTool(pendingToolName);
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
