App.registerArea({
  id: 'admin',
  label: 'System',
  icon: App.icons.admin,
  order: 30,
  sidebarLabel: 'System categories',

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
  hydrateState: function (sub) {
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

    var validIds = ['general', 'providers', 'tools'];
    if (validIds.indexOf(sub) === -1) return;

    // Set category FIRST — _setCategory wipes pending state on category change,
    // so we must set pending AFTER it to survive the wipe.
    if (this._setCategory) this._setCategory(sub);

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
    // editor.
    if (this._tryConsumePendingProvider) this._tryConsumePendingProvider();
    if (this._tryConsumePendingTool) this._tryConsumePendingTool();
  },

  init: function (content) {
    var categories = [
      { id: 'general', label: 'General' },
      { id: 'providers', label: 'LLM Providers' },
      // F6 HAT inline fix #5: "Tools" → "Built-in Tools" — distinguishes
      // from MCP / external tool surfaces. id stays 'tools' so URL routing
      // (#admin/tools/{name}) is unchanged. The MCP Servers section that
      // M07 F1 L5 originally placed here was relocated to the Studio nav
      // post-F2 retrofit (admin = system settings, studio = user-managed).
      { id: 'tools', label: 'Built-in Tools' }
    ];
    var currentCategory = 'general';

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
        .catch(function (err) {
          console.warn('admin: fetchProviderTypes failed', err);
          PROVIDER_TYPES = [];
        });
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

    // Build Holograph layout: area-header + subnav + 3 sub-blocks.
    //
    // M10 L3.3 — area header is rendered dynamically by `refreshAdminHeader`
    // (per-subtab eyebrow + title + subtitle). The header element is a shell
    // that gets repopulated on every sub-tab switch. No header CTA — General
    // has Rotate-Key inside a card, Providers has new-provider inside a card,
    // Tools has nothing. Shell DOM built via `insertAdjacentHTML` (matches
    // studio.js's L3.2 pattern; all template content is literal markup,
    // dynamic values come from a curated state object + are escape-safe by
    // construction).
    while (content.firstChild) content.removeChild(content.firstChild);
    content.insertAdjacentHTML('beforeend',
      '<div class="area-header" id="admin-area-header"></div>' +
      '<div class="admin-subnav" id="admin-subnav"></div>' +
      '<div class="admin-sub" id="sub-general"></div>' +
      '<div class="admin-sub" id="sub-providers"></div>' +
      '<div class="admin-sub" id="sub-tools"></div>'
    );

    var headerEl = content.querySelector('#admin-area-header');
    var _adminSubnav = content.querySelector('#admin-subnav');
    var subGeneralEl = content.querySelector('#sub-general');
    var subProvidersEl = content.querySelector('#sub-providers');
    var subToolsEl = content.querySelector('#sub-tools');

    var sectionNavEl = _adminSubnav;

    // M10 L3.3 — Admin area header builder. Each sub-tab gets its own
    // eyebrow + title + subtitle:
    //   - General   → "SYSTEM · GENERAL"       / "General"
    //   - Providers → "SYSTEM · LLM PROVIDERS" / "LLM Providers" (count varies)
    //   - Tools     → "SYSTEM · BUILT-IN TOOLS" / "Built-in Tools" (N / 19)
    // Provider subtitle has the zero-state copy when providerCount === 0
    // (mirrors the topnav stat's zero-state); otherwise it's "N provider[s]
    // configured · API keys encrypted at rest." Tools subtitle is always
    // "N / 19 tools enabled at operator level."
    function buildAdminHeaderHtml(state) {
      var titles = {
        general:   { title: 'General',        sub: 'Appearance, encryption, base prompt — single-user local settings.' },
        providers: { title: 'LLM Providers',  sub: state.providerCount === 0
          ? 'Wire up a provider to unlock the rest of the app. API keys are encrypted at rest.'
          : state.providerCount + ' provider' + (state.providerCount === 1 ? '' : 's') + ' configured · API keys encrypted at rest.' },
        tools:     { title: 'Built-in Tools', sub: state.toolsEnabled + ' / 19 tools enabled at operator level.' }
      };
      var eyebrows = {
        general:   'SYSTEM · GENERAL',
        providers: 'SYSTEM · LLM PROVIDERS',
        tools:     'SYSTEM · BUILT-IN TOOLS'
      };
      var t = titles[state.subtab] || titles.general;
      var e = eyebrows[state.subtab] || eyebrows.general;
      return '<div class="area-header-titleblock">' +
          '<div class="eyebrow">' + e + '</div>' +
          '<h1 class="area-title">' + t.title + '</h1>' +
          '<p class="area-sub">' + t.sub + '</p>' +
        '</div>';
    }

    // Snapshot the per-sub-tab state and re-render the header. providerCount
    // comes from TelemetryStore when numeric (already hydrated by app.js's
    // initial refresh + per-area-switch refresh); when the store value is
    // still the em-dash placeholder, we fall back to the in-memory provider
    // cache, else 0. toolsEnabled is computed from the toolConfigs array
    // (the telemetry store tracks total tool count, NOT enabled count, so
    // we count locally; mirrors the cache the grid already builds against).
    function refreshAdminHeader() {
      if (!headerEl) return;
      var telemetry = (window.TelemetryStore && window.TelemetryStore.get)
        ? window.TelemetryStore.get() : {};
      var providerCount = (typeof telemetry.providers === 'number')
        ? telemetry.providers
        : (Array.isArray(providers) ? providers.length : 0);
      var toolsEnabled = 0;
      if (Array.isArray(toolConfigs)) {
        for (var i = 0; i < toolConfigs.length; i++) {
          if (toolConfigs[i] && toolConfigs[i].enabled) toolsEnabled++;
        }
      }
      var state = {
        subtab: currentCategory || 'general',
        providerCount: providerCount,
        toolsEnabled: toolsEnabled
      };
      while (headerEl.firstChild) headerEl.removeChild(headerEl.firstChild);
      headerEl.insertAdjacentHTML('beforeend', buildAdminHeaderHtml(state));
    }

    // ── Section activation ─────────────────────────────────────────────

    function setActiveSection(catId, opts) {
      opts = opts || {};
      currentCategory = catId;
      subGeneralEl.classList.toggle('active', catId === 'general');
      subProvidersEl.classList.toggle('active', catId === 'providers');
      subToolsEl.classList.toggle('active', catId === 'tools');
      App.layout.updateActiveSection(sectionNavEl, catId);

      // M10 L3.3 — refresh the area-header for the new sub-tab. Fires on
      // every sub-tab switch (sidebar click, hydrateState from URL hash,
      // initial mount). Header content depends on `currentCategory`,
      // `providers`, and `toolConfigs` — all closure locals already
      // up-to-date at this point. Counts may be stale (0/--) until the
      // matching fetch resolves; the .then handlers re-call this fn.
      refreshAdminHeader();

      // Lazy-render — re-render the just-activated section's content.
      if (catId === 'general') {
        App.admin.renderSystemPage(subGeneralEl);
      } else if (catId === 'providers') {
        renderProvidersPanel(subProvidersEl);
      } else if (catId === 'tools') {
        renderToolsPanel(subToolsEl);
      }

      if (opts.writeUrl !== false) {
        if (window.App && window.App.router) App.router.replaceSub(self.serializeState());
      }
    }

    function doSetCategory(catId) {
      providerFormMode = null;
      editingProvider = null;
      pendingProviderId = null;
      pendingFormMode = null;
      toolFormMode = null;
      editingTool = null;
      pendingToolName = null;
      pendingToolFormMode = null;
      dirty = false;
      setActiveSection(catId);
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
      ariaLabel: 'Administration sections'
    });

    // ── Providers Panel ───────────────────────────────────────────────

    function renderProvidersPanel(mountEl) {
      mountEl = mountEl || subProvidersEl;
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
            renderProvidersPanel(mountEl);
          }
          App.admin.renderProviderEditor(mountEl, editingProvider, PROVIDER_TYPES, {
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
              renderProvidersPanel(mountEl);
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
                // M10 L3.3 \u2014 provider was just created; reload the list so
                // the count in the area-header is fresh on next subtab visit.
                // (Header is hidden in editor mode but the count is read by
                // refreshAdminHeader from the in-memory cache, so a stale
                // cache would show wrong copy when the operator goes back.)
                fetchProviders();
                renderProvidersPanel(mountEl);
              }
              // Edit\u2192edit case: editor stays mounted; sub-module's local
              // snapshot recapture handles dirty reset. No re-render needed.
            },
            onDeleteSuccess: function () {
              providerFormMode = null;
              editingProvider = null;
              dirty = false;
              if (window.App && window.App.router) App.router.replaceSub('providers');
              renderProvidersPanel(mountEl);
              // M10 L3.3 \u2014 renderProvidersPanel will refire fetchProviders \u2192
              // which refreshes the header after the cache is updated. No
              // extra call needed here.
            },
            onDirtyChange: function (d) { dirty = d; },
            getTypeDefaults: function (type) { return TYPE_DEFAULTS[type]; }
          });
        });
        return;
      }
      // Grid branch: delegate to providers-grid sub-module.
      App.admin.renderProvidersGrid(mountEl, providers, {
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
          // M10 L3.3 — refresh header after provider fetch so the count in
          // the Providers subtitle reflects real data (initial mount fires
          // refreshAdminHeader before fetchProviders resolves, so the first
          // paint shows the zero-state copy when the cache is empty).
          refreshAdminHeader();
          self._tryConsumePendingProvider();
        })
        .catch(function () {
          var gridEl = subProvidersEl.querySelector('.entity-tile-grid');
          if (gridEl) {
            var errMsg = document.createElement('div');
            errMsg.className = 'admin-loading';
            errMsg.textContent = 'Failed to load providers.';
            gridEl.textContent = '';
            gridEl.appendChild(errMsg);
          }
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
      App.admin.renderProvidersGrid(subProvidersEl, providers, {
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
      renderProvidersPanel(subProvidersEl);
    }

    function enterCreateMode() {
      providerFormMode = 'add';
      editingProvider = null;
      pendingProviderId = null;
      pendingFormMode = null;
      if (window.App && window.App.router) {
        App.router.replaceSub(self.serializeState());
      }
      renderProvidersPanel(subProvidersEl);
    }

    function findProvider(id) {
      if (!providers) return null;
      for (var i = 0; i < providers.length; i++) {
        if (providers[i].id === id) return providers[i];
      }
      return null;
    }

    // ── Tools Panel (F6 leg 02 / leg 03 editor) ───────────────────────

    function renderToolsPanel(mountEl) {
      mountEl = mountEl || subToolsEl;
      // Editor branch (F6 leg 03): delegate to tools-editor sub-module.
      if (toolFormMode === 'edit' && editingTool) {
        // Reset orchestrator's dirty mirror BEFORE editor mount (mirrors
        // provider-editor pattern at renderProvidersPanel:222). The fresh
        // editor closure starts at dirty=false; the onDirtyChange bridge
        // only fires on the first user input.
        dirty = false;
        App.admin.renderToolsEditor(mountEl, editingTool, {
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
            // M10 L3.3 — the editor can flip the `enabled` field; refresh
            // the header so the "N / 19" count is correct when the operator
            // navigates back to the grid (refreshAdminHeader reads from the
            // toolConfigs cache that we just mutated above).
            refreshAdminHeader();
          },
          onDirtyChange: function (d) { dirty = d; }
        });
        return;
      }
      // Grid branch (L2)
      App.admin.renderToolsGrid(mountEl, toolConfigs, {
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
      renderToolsPanel(subToolsEl);
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
            App.router.replaceSub(self.serializeState());
          }
          renderToolsPanel(subToolsEl);
        })
        .catch(function () {
          if (currentCategory !== 'tools') return;
          App.showFlash(subToolsEl, 'Failed to load ' + name + '.', true);
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
          // M10 L3.3 — refresh header after tools fetch so the "N / 19
          // tools enabled" subtitle reflects real data.
          refreshAdminHeader();
        })
        .catch(function () {
          if (currentCategory !== 'tools') return;
          var gridEl = subToolsEl.querySelector('.entity-tile-grid');
          if (gridEl) {
            var errTool = document.createElement('div');
            errTool.className = 'admin-loading';
            errTool.textContent = 'Failed to load tools.';
            gridEl.textContent = '';
            gridEl.appendChild(errTool);
          }
        });
    }

    function populateToolGrid() {
      // Stale-then guard: bail when no longer on tools (mirrors providers),
      // OR when the editor is mounted (no grid in the DOM to populate).
      if (currentCategory !== 'tools') return;
      if (toolFormMode) return;
      App.admin.renderToolsGrid(subToolsEl, toolConfigs, {
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
      // M10 L3.3 — refresh header optimistically so the "N / 19" count
      // tracks the toggle without waiting for the PUT round-trip. Reverted
      // by the .catch when the PUT fails.
      refreshAdminHeader();

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
        refreshAdminHeader();
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
      // Flash relative to the active sub-block.
      var activeEl = subGeneralEl.classList.contains('active') ? subGeneralEl
                   : subProvidersEl.classList.contains('active') ? subProvidersEl
                   : subToolsEl;
      App.showFlash(activeEl, msg, isError);
    }

    // ── Helpers ────────────────────────────────────────────────────────

    var escapeHtml = App.escapeHtml;
    var escapeAttr = App.escapeAttr;

    // Store reference for activate() to reuse
    var self = this;
    self._refresh = function () {
      if (currentCategory === 'general') {
        App.admin.renderSystemPage(subGeneralEl);
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
    // confirmLeave wired here so it can close over the local `dirty` flag.
    // Gate semantics mirror the sidebar setCategory dirty-gate: dirty AND
    // in-editor → confirm dialog; otherwise → proceed immediately.
    self._confirmLeaveImpl = function (proceed, abort) {
      var inEditor = (currentCategory === 'providers' && providerFormMode)
                  || (currentCategory === 'tools' && toolFormMode);
      if (dirty && inEditor) {
        App.confirmDialog({ onConfirm: proceed, onCancel: abort });
      } else {
        proceed();
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
        setActiveSection(sub, { writeUrl: false });
      }
    };
    self._tryConsumePendingProvider = function () {
      if (!pendingProviderId && !pendingFormMode) return;
      if (pendingFormMode === 'add') {
        providerFormMode = 'add';
        editingProvider = null;
        pendingFormMode = null;
        pendingProviderId = null;
        renderProvidersPanel(subProvidersEl);
        return;
      }
      if (pendingFormMode === 'edit' && pendingProviderId) {
        var found = findProvider(pendingProviderId);
        if (found) {
          providerFormMode = 'edit';
          editingProvider = found;
          pendingProviderId = null;
          pendingFormMode = null;
          renderProvidersPanel(subProvidersEl);
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
    setActiveSection(currentCategory, { writeUrl: false });
  },

  activate: function () {
    if (this._refresh) {
      this._refresh();
    }
  },

  // confirmLeave: cross-area dirty-gate hook (F3 L06). Called by app.js
  // switchTo() BEFORE deactivation on cross-area navigation. Clean →
  // immediate proceed; dirty → confirm dialog gates the transition.
  // Mirrors the existing sidebar setCategory dirty-gate so internal
  // (sidebar) + external (topbar/back/hash) nav paths share the contract.
  // The handle is attached inside init() so it can close over the local
  // `dirty` flag.
  confirmLeave: function (proceed, abort) {
    if (this._confirmLeaveImpl) {
      this._confirmLeaveImpl(proceed, abort);
    } else {
      proceed();
    }
  },

  deactivate: function () {}
});
