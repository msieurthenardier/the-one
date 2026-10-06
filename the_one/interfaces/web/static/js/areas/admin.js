App.registerArea({
  id: 'admin',
  label: 'System',
  icon: App.icons.admin,
  order: 30,

  // The General pages (M25 F3 L5a, DD6): the former single "General" page is
  // three, each with its own route (#settings/appearance|prompts|encryption).
  // Their area subs equal their route sections. The legacy `general` and
  // `system` subs map to the first of them.
  GENERAL_SUBS: ['appearance', 'prompts', 'encryption'],

  serializeState: function () {
    if (this.GENERAL_SUBS.indexOf(this._currentCategory) !== -1) return this._currentCategory;
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
    return this._currentCategory || this.GENERAL_SUBS[0];
  },
  // hydrateState(sub, {fresh}) renders exactly `sub`. `fresh` is the router's
  // hydrate ORIGIN (M25 F2 L4): true for a traversal, a typed hash and boot --
  // an item named by the URL may have been deleted since, so it is resolved
  // against a FRESH fetch and a dead id heals to the section root; false for an
  // intent go() (a click on a row), which opens the item from the cached list
  // without re-rendering the grid or refetching.
  hydrateState: function (sub, opts) {
    var fresh = !!(opts && opts.fresh);
    // Empty sub → reset to the first General page (Appearance). Without
    // this, currentCategory retains whatever it was (e.g. 'providers') and the
    // router's post-hydrate sync would rewrite the URL to that retained state
    // instead of the canonical default. F6 HAT regression. (The router itself
    // never hydrates an empty admin sub: a bare #settings resolves to its root.)
    if (!sub) {
      if (this._setCategory) this._setCategory(this.GENERAL_SUBS[0]);
      this._pendingProviderId = null;
      this._pendingFormMode = null;
      this._pendingToolName = null;
      this._pendingToolFormMode = null;
      if (this._syncNavSelection) this._syncNavSelection();
      return;
    }
    var origSub = sub;
    // The legacy subs of the former single General page ('general', and its
    // interim slug 'system') map to its first page (M25 F3 L5a). The router
    // already redirects their routes (#settings/general, #admin/system,
    // #admin/general); this keeps a stray legacy sub from rendering nothing.
    if (sub === 'system' || sub === 'general') sub = this.GENERAL_SUBS[0];

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

    var validIds = this.GENERAL_SUBS.concat(['providers', 'tools', 'knowledge']);
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
    // #settings/providers/~new → #settings/appearance clears pending state.
    this._pendingProviderId = pendingId;
    this._pendingFormMode = pendingFormMode;
    this._pendingToolName = pendingToolName_local;
    this._pendingToolFormMode = pendingToolFormMode_local;
    // An item route is a navigation the user made (a row or name link, "Add
    // provider", Back/Forward, a deep link or boot): the item, once mounted,
    // scrolls its header into view and takes focus (M25 F3 L5b, DD7). Store
    // notifications and _refresh re-fetches never set this.
    if (this._setOpenIntent) this._setOpenIntent(itemSub);

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
    // The Settings nav marks the page's SECTION on every hydrate, item routes
    // included (#settings/providers/{id} keeps "Providers" selected).
    if (this._syncNavSelection) this._syncNavSelection();
    // The list marks the open (or pending) item: the provider row, the tool tile.
    if (this._syncItemSelection) this._syncItemSelection();
  },

  init: function (sidebar, content) {
    // The Settings nav (M25 F3 L5a, DD6; reference spec section 8.1): one
    // App.ui.navGroups of plain links, built from the shared page table
    // App.settingsPages (settings-pages.js, M25 F4 L7: the same table the
    // router's labels and the jump-to palette read). Each item is keyed by
    // its ROUTE section, which is also its test id suffix. The area's own
    // category ids differ for one page only: its 'knowledge' category is the
    // 'knowledge-indexing' page (ROUTE_SECTION, internal to this file).
    // Built-in tools are named so to tell them from MCP / external tools. The
    // Knowledge indexing page is app-wide chunking + monitoring settings (M24
    // F06 L04, DD-7); the knowledge-base inventory lives in the Library.
    var ROUTE_SECTION = { knowledge: 'knowledge-indexing' };
    function routeSection(category) { return ROUTE_SECTION[category] || category; }
    function settingsPage(section) {
      var pages = App.settingsPages;
      for (var p = 0; p < pages.length; p++) if (pages[p].section === section) return pages[p];
      return null;
    }
    // The page's name from the table, by area category.
    function pageLabel(category) {
      var page = settingsPage(routeSection(category));
      return page ? page.label : category;
    }
    function navItem(page) {
      return {
        id: page.section,
        label: page.label,
        href: App.router.href({ destination: 'settings', section: page.section }),
        testid: 'settings-nav-' + page.section
      };
    }
    // Groups in table order. A devOnly page (the Design language gallery,
    // Mission 08 F2 L1) shows only in dev mode, filtered here at init: the
    // boot-blocking fetch in app.js populates window.App.config before it.
    var devMode = !!(window.App && window.App.config && window.App.config.dev_mode);
    var navGroups = [];
    var groupByLabel = {};
    for (var pg = 0; pg < App.settingsPages.length; pg++) {
      var navPage = App.settingsPages[pg];
      if (navPage.devOnly && !devMode) continue;
      if (!Object.prototype.hasOwnProperty.call(groupByLabel, navPage.group)) {
        groupByLabel[navPage.group] = { label: navPage.group, items: [] };
        navGroups.push(groupByLabel[navPage.group]);
      }
      groupByLabel[navPage.group].items.push(navItem(navPage));
    }
    var currentCategory = this.GENERAL_SUBS[0];
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
    // is open any more. Cleared by every panel render. (Since M25 F3 L5b a
    // discard on an item page clears its item section, so it never sets this.)
    var editorDomStale = false;

    // The item-page scaffold (M25 F3 L5b, flight DD7): Providers and Built-in
    // tools render, once per category render, the page header, then
    // `.settings-list` (the provider tiles / the tool list), then `.settings-item`
    // (the open item's editor). List renders target the list section only and
    // editors mount in the item section, so neither replaces the other.
    // { category, listEl, itemEl } | null (another page is showing).
    var scaffold = null;
    // Set by hydrateState for an item route; consumed when that item mounts
    // (scroll its header into view, focus its title). See _setOpenIntent.
    var openIntent = false;
    // The mounted tool editor's { setEnabled } (tools-editor.js onMount).
    var toolEditorApi = null;
    // True once a providers list request failed while no list was ever loaded.
    var providersFailed = false;

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
    // mapping (KNOWN_BADGE_TYPES) lives in providers-list.js (M25 F3 L5b).
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

    // The nav mounts on a child of the sidebar panel, never on the panel
    // itself, so the panel keeps its .area-admin class. The host is the
    // column's scroller (the panel is overflow: hidden) and carries the
    // section 8.1 column padding. The items are plain links with no handler:
    // a click is a user INTENT that App.nav's link interceptor routes through
    // the router, whose leave guard asks about unsaved changes exactly once.
    // A click on the current page goes to that page's root, which closes an
    // open editor (_setCategory's same-category close).
    var settingsNav = App.ui.navGroups({
      label: 'Settings',
      heading: 'Settings',
      testid: 'settings-nav',
      groups: navGroups,
      selectedId: routeSection(currentCategory)
    });
    sidebar.textContent = '';
    sidebar.appendChild(App.ui.util.el('div', { className: 'admin-settings-nav' }, [settingsNav.el]));

    // Build content
    content.innerHTML = '<div class="admin-content"></div>';
    contentEl = content.querySelector('.admin-content');

    // The Providers list's data (M25 F3 L5b, DD9): lifetime subscriptions,
    // registered once. A load of either collection -- by this page or any
    // other area -- re-renders the tile grid only (renderProvidersListNow is
    // a no-op unless the Providers page is showing); never the editor below.
    App.store.subscribe('providers', function (list) {
      providers = list;
      providersFailed = false;
      renderProvidersListNow();
    });
    App.store.subscribe('agents', function () { renderProvidersListNow(); });

    // ── Rendering ─────────────────────────────────────────────────────

    // The General pages (system-page.js): each renders only its own block.
    var GENERAL_RENDERERS = {
      appearance: 'renderAppearancePage',
      prompts: 'renderPromptsPage',
      encryption: 'renderEncryptionPage'
    };

    function renderContent() {
      // Every page render replaces the content; Providers and Built-in tools
      // mount a fresh scaffold below.
      scaffold = null;
      toolEditorApi = null;
      if (GENERAL_RENDERERS[currentCategory]) {
        App.admin[GENERAL_RENDERERS[currentCategory]](contentEl);
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

    // ── Item-page scaffold (M25 F3 L5b, flight DD7) ──────────────────
    // Providers and Built-in tools keep their list visible: the open item's
    // editor renders BELOW the list, in the same scrolling page. One scaffold
    // per category render: the section 4 page header, `.settings-list` (the
    // Providers tiles or the tool list) and `.settings-item` (the editor).
    // List renders target the list section only; editors mount in the item
    // section; closing an item empties the item section. The list therefore
    // refreshes while an editor is open (store notifications, toggles,
    // _refresh) without ever touching the editor.

    function mountScaffold(category) {
      var el = App.ui.util.el;
      contentEl.textContent = '';
      var header = el('div', { className: 'page-header' }, [
        el('h1', { className: 'page-title', text: pageLabel(category) })
      ]);
      if (category === 'providers') {
        // The page's primary action (reference spec section 8.2).
        header.appendChild(App.ui.button({
          label: 'Add provider',
          icon: 'plus',
          testid: 'new-provider-btn',
          onClick: function () { enterCreateMode(); }
        }));
      }
      var listEl = el('div', { className: 'settings-list settings-list--' + category });
      var itemEl = el('div', { className: 'settings-item' });
      contentEl.appendChild(header);
      contentEl.appendChild(listEl);
      contentEl.appendChild(itemEl);
      scaffold = { category: category, listEl: listEl, itemEl: itemEl };
      return scaffold;
    }

    // The mounted scaffold when `category` is the page showing, else null.
    function scaffoldFor(category) {
      return scaffold && scaffold.category === category && currentCategory === category ? scaffold : null;
    }

    // An editor's flashes (App.showFlash) are appended to its own container,
    // the item section, which a close or a create->edit re-mount empties:
    // move them to the page first so they stay on screen (position: fixed;
    // their own timers remove them).
    function rescueFlashes(itemEl) {
      var flashes = itemEl.querySelectorAll('.app-flash');
      for (var i = 0; i < flashes.length; i++) {
        if (flashes[i].parentNode === itemEl) contentEl.appendChild(flashes[i]);
      }
    }

    // Close the open item's DOM: the item section is emptied (DD7).
    function clearItemSection() {
      toolEditorApi = null;
      if (!scaffold) return;
      rescueFlashes(scaffold.itemEl);
      scaffold.itemEl.textContent = '';
    }

    function focusNoScroll(node) {
      try { node.focus({ preventScroll: true }); } catch (e) { node.focus(); }
    }

    // An item opened by an intent (a row or name link, "Add provider", a deep
    // link or boot) scrolls its header into view (block: nearest) and moves
    // focus to its title (tabindex=-1). It waits one task: after a Continue
    // on the leave dialog, nav.js focuses <main> from a setTimeout, and the
    // title must land last. A close or a newer open in between cancels it.
    function revealItem(itemEl) {
      var gen = editorGen;
      setTimeout(function () {
        if (gen !== editorGen || !itemEl.isConnected) return;
        var header = itemEl.querySelector('.editor-header');
        var title = itemEl.querySelector('.editor-title');
        if (header && typeof header.scrollIntoView === 'function') header.scrollIntoView({ block: 'nearest' });
        if (title) focusNoScroll(title);
      }, 0);
    }

    function rootHref(section) {
      return App.router.href({ destination: 'settings', section: section });
    }

    // ── Providers Panel ───────────────────────────────────────────────

    function renderProvidersPanel() {
      editorDomStale = false;
      mountScaffold('providers');
      // A list another area already loaded paints at once (no "Loading" flash).
      if (providers === null) {
        var known = App.store.peek('providers');
        if (known.loaded) providers = known.value;
      }
      renderProvidersListNow();
      // DD9 freshness bound: the page's mount re-reads both collections.
      fetchProviders();
      loadAgentsForTable();
      if (providerFormMode) mountProviderItem();
    }

    // The agents list the "Used by" column counts, or null while it has never
    // loaded (the tiles then read "—", never "0 agents"). The admin area has
    // no other use for agents; the tiles subscribe to the store.
    function agentsForTable() {
      var known = App.store.peek('agents');
      return known.loaded ? known.value : null;
    }

    function loadAgentsForTable() {
      App.store.get('agents', { force: true }).catch(function () { renderProvidersListNow(); });
    }

    function selectedProviderId() {
      if (providerFormMode === 'edit' && editingProvider) return editingProvider.id;
      if (pendingFormMode === 'edit' && pendingProviderId) return pendingProviderId;
      return null;
    }

    // Re-render the Providers LIST section only (never the item section).
    function renderProvidersListNow() {
      var sc = scaffoldFor('providers');
      if (!sc) return;
      App.admin.renderProvidersList(sc.listEl, {
        providers: providers,
        agents: agentsForTable(),
        failed: providersFailed,
        selectedId: selectedProviderId(),
        onCreate: enterCreateMode
      });
    }

    // Mount the provider editor (create or edit) in the item section.
    // opts.keepFocus: a re-mount (save-create) puts focus on the new title
    // when focus was inside the editor it replaces.
    function mountProviderItem(opts) {
      opts = opts || {};
      if (!scaffoldFor('providers') || !providerFormMode) return;
      // Reset orchestrator's dirty mirror BEFORE editor mount (F6 leg 04).
      // The fresh editor closure starts at dirty=false; the onDirtyChange
      // bridge only fires on the first user input. This handles the
      // create->edit re-mount cleanly: the previous closure's dirty=true
      // would otherwise dangle in the orchestrator mirror.
      dirty = false;
      var reveal = openIntent;
      openIntent = false;
      // Wait for provider types before rendering the editor (the type
      // dropdown depends on PROVIDER_TYPES).
      var ready = providerTypesReady || fetchProviderTypes();
      var mountGen = editorGen;
      ready.then(function () {
        var sc = scaffoldFor('providers');
        if (mountGen !== editorGen || !sc || !providerFormMode) return; // closed while the types loaded
        var hadFocus = !!opts.keepFocus && sc.itemEl.contains(document.activeElement);
        rescueFlashes(sc.itemEl);
        App.admin.renderProviderEditor(sc.itemEl, editingProvider, PROVIDER_TYPES, providerCallbacks(mountGen));
        App.admin.setProvidersSelection(sc.listEl, selectedProviderId());
        if (reveal) {
          revealItem(sc.itemEl);
        } else if (hadFocus) {
          var title = sc.itemEl.querySelector('.editor-title');
          if (title) focusNoScroll(title);
        }
      });
    }

    function providerCallbacks(mountGen) {
      return {
        onCancel: function () {
          // Create-mode Cancel (the editor's Cancel only calls onCancel when
          // isCreate; edit mode reverts in place). It is enabled from first
          // render, so this runs on a pristine form as well as a dirty one;
          // either way it is an intentional discard -- no gate -- so:
          // discard, then a bypass go() REPLACING the create entry (Back must
          // not land on a stale create form). Focus (DD8's one rule for Cancel,
          // close and delete): a create form has no row of its own, so the
          // nearest surviving row -- the first provider tile link -- else
          // "Add provider" when the grid is empty. (Leg 5b sent it to "Add
          // provider" always; the behavior-gate fix aligned it with DD8, as
          // Agents and Library already were.)
          if (mountGen !== editorGen) return;
          self._discardEditor();
          App.router.go(rootHref('providers'), { replace: true, bypassGuard: true }).then(function () {
            focusProviderRowNear(0);
          });
        },
        onSaveSuccess: function (updated, isCreate) {
          if (mountGen !== editorGen) return; // discarded mid-save: no resurrection
          // Editor sub-module owns the fetch; this callback only mutates
          // orchestrator state on success. The editing provider and the
          // mode are set BEFORE the list reload lands, so the new or renamed
          // row renders selected.
          editingProvider = updated;
          providerFormMode = 'edit';
          dirty = false; // Save cleared dirty (sub-module recaptures snapshot).
          if (providers) {
            var merged = [];
            var seen = false;
            for (var i = 0; i < providers.length; i++) {
              if (providers[i].id === updated.id) { merged.push(updated); seen = true; } else merged.push(providers[i]);
            }
            if (!seen) merged.push(updated);
            providers = merged;
          }
          // The name hint (M25 F3 L2, DD8): a just-created provider is not in
          // the store yet, so the router could not name it. On create this
          // sync is the ~new -> item transition, which it announces.
          if (window.App && window.App.router) {
            App.router.sync('admin', self.serializeState(), { name: updated.name });
          }
          renderProvidersListNow();
          if (isCreate) {
            // Create -> edit: re-mount ONLY the item section in edit mode
            // (Models, Danger Zone and Test now render); the tile list stays.
            mountProviderItem({ keepFocus: true });
          }
          // Edit -> edit: the editor stays mounted; its own snapshot
          // recapture handles the dirty reset.
          reloadProviders();
        },
        onDeleteSuccess: function () {
          if (mountGen !== editorGen) return;
          // Focus after delete (DD8): the nearest surviving row -- the next,
          // else the previous -- else "Add provider". The row's index is read
          // now, while it is still listed.
          var sc = scaffoldFor('providers');
          var goneId = editingProvider ? editingProvider.id : null;
          var idx = sc && goneId ? App.admin.providerRowIndex(sc.listEl, goneId) : -1;
          // Discard first so a stray dirty flag cannot outlive the deleted
          // item, then a bypass go() replacing the deleted provider's entry.
          self._discardEditor();
          if (providers && goneId) {
            providers = providers.filter(function (p) { return p.id !== goneId; });
          }
          App.router.go(rootHref('providers'), { replace: true, bypassGuard: true }).then(function () {
            renderProvidersListNow();
            focusProviderRowNear(idx);
          });
          reloadProviders();
        },
        onDirtyChange: function (d) { dirty = d; },
        getTypeDefaults: function (type) { return TYPE_DEFAULTS[type]; }
      };
    }

    function focusAddProvider() {
      var btn = contentEl.querySelector('[data-testid="new-provider-btn"]');
      if (btn) btn.focus();
    }

    // Focus the provider tile link at `idx` (clamped to the last row), else
    // "Add provider" when the grid has no tiles.
    function focusProviderRowNear(idx) {
      var sc = scaffoldFor('providers');
      if (!sc) return;
      var links = App.admin.providerLinks(sc.listEl);
      if (!links.length) { focusAddProvider(); return; }
      links[Math.max(0, Math.min(idx < 0 ? 0 : idx, links.length - 1))].focus();
    }

    // One list request at a time: a render's list fetch and a fresh hydrate's
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

    // The store's current value wins over a request's own result: a request
    // that started before an invalidate resolves with a stale list.
    function storeValue(name, data) {
      var known = App.store.peek(name);
      return known.loaded ? known.value : data;
    }

    function fetchProvidersNow() {
      return App.store.get('providers', { force: true })
        .then(function (data) {
          providers = storeValue('providers', data);
          providersFailed = false;
          renderProvidersListNow();
          self._tryConsumePendingProvider();
          // A pending id absent from a FRESH fetch is dead (deleted meanwhile,
          // or a stale link): never keep it in the URL. Heal to the section
          // root in place.
          if (pendingFormMode === 'edit' && pendingProviderId && !findProvider(pendingProviderId)) {
            pendingProviderId = null;
            pendingFormMode = null;
            openIntent = false;
            renderProvidersListNow();
            if (window.App && window.App.router) App.router.sync('admin', self.serializeState());
          }
        })
        .catch(function () {
          // Only a list that never loaded reads as failed; a failed refresh
          // keeps the last good rows.
          if (providers === null) providersFailed = true;
          renderProvidersListNow();
        });
    }

    // After a mutation (save, create, delete): re-read the list (the editor
    // already invalidated it), bypassing fetchProviders' one-at-a-time join
    // so a request from before the mutation is never reused. The store's
    // subscription re-renders the tile grid; the editor is untouched.
    function reloadProviders() {
      App.store.get('providers', { force: true }).then(function (data) {
        providers = storeValue('providers', data);
        renderProvidersListNow();
      }, function () { /* keep the last good rows */ });
    }

    // Opening a provider / the create form is a user INTENT: a pushed go()
    // (Back returns to the root), hydrated with the cached list. The tiles'
    // name links are plain links App.nav routes the same way.
    function enterCreateMode() {
      // The create form already open: just bring it into view (no go(), so a
      // dirty form is never asked about, nor re-mounted).
      if (currentCategory === 'providers' && providerFormMode === 'add' && scaffold) {
        revealItem(scaffold.itemEl);
        return;
      }
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
      mountScaffold('tools');
      renderToolsListNow();
      fetchToolConfigs();
      if (toolFormMode === 'edit' && editingTool) mountToolItem();
    }

    function selectedToolName() {
      if (toolFormMode === 'edit' && editingTool) return editingTool.name;
      if (pendingToolFormMode === 'edit' && pendingToolName) return pendingToolName;
      return null;
    }

    // Re-render the tool LIST section only (never the item section).
    function renderToolsListNow() {
      var sc = scaffoldFor('tools');
      if (!sc) return;
      App.admin.renderToolsGrid(sc.listEl, toolConfigs, {
        onToggle: handleToolToggle,
        inFlight: toolsInFlight,
        selectedName: selectedToolName()
      });
    }

    // Mount the tool editor in the item section.
    function mountToolItem() {
      var sc = scaffoldFor('tools');
      if (!sc || toolFormMode !== 'edit' || !editingTool) return;
      // Reset orchestrator's dirty mirror BEFORE editor mount (mirrors the
      // provider editor). The fresh editor closure starts at dirty=false;
      // the onDirtyChange bridge only fires on the first user input.
      dirty = false;
      var reveal = openIntent;
      openIntent = false;
      var toolGen = editorGen;
      toolEditorApi = null;
      rescueFlashes(sc.itemEl);
      App.admin.renderToolsEditor(sc.itemEl, editingTool, {
        onCancel: function () {
          // Cancel sub-module restores original DOM (re-mounts with the
          // original toolDetail). Orchestrator stays in editor mode —
          // Cancel is a snapshot-revert, not a "discard and exit".
          dirty = false;
        },
        onSaveSuccess: function (updated) {
          if (toolGen !== editorGen || !editingTool) return; // discarded mid-save
          // Update the list cache (post-leg-02 cache fields: name,
          // description, enabled, config); the list above re-renders so the
          // tile's toggle shows the saved enablement.
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
          renderToolsListNow();
        },
        onDirtyChange: function (d) { dirty = d; },
        onMount: function (api) { if (toolGen === editorGen) toolEditorApi = api; }
      });
      App.admin.setToolsSelection(sc.listEl, editingTool.name);
      if (reveal) revealItem(sc.itemEl);
    }

    // Loads the tool's detail and mounts its editor (the hydrate / consume
    // path, and _refresh's re-read of the open tool). It renders the ITEM
    // section only: the list is never rebuilt here. A close or a newer open
    // while the detail loads (editorGen) drops the response.
    function selectTool(name) {
      var gen = editorGen;
      // ALWAYS fetches — the list cache lacks `schema`, so a cache-lookup
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
          // path that ran AFTER the fetch started has since moved to another
          // page, or closed / replaced the item, abandon the mutation —
          // otherwise the then-block would clobber the now-correct render.
          if (currentCategory !== 'tools' || gen !== editorGen) return;
          editingTool = detail;
          toolFormMode = 'edit';
          pendingToolName = null;
          pendingToolFormMode = null;
          if (window.App && window.App.router) {
            App.router.sync('admin', self.serializeState());
          }
          mountToolItem();
        })
        .catch(function (err) {
          if (currentCategory !== 'tools' || gen !== editorGen) return;
          if (err && err.gone) {
            // Dead id (an unknown name in the URL, or a tool removed while its
            // editor was open): close any editor and heal the URL to the
            // section root in place -- nothing is left pending.
            pendingToolName = null;
            pendingToolFormMode = null;
            toolFormMode = null;
            editingTool = null;
            dirty = false;
            openIntent = false;
            clearItemSection();
            App.router.sync('admin', 'tools');
            var sc = scaffoldFor('tools');
            if (sc) App.admin.setToolsSelection(sc.listEl, null);
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
          renderToolsListNow();
        })
        .catch(function () {
          if (currentCategory !== 'tools') return;
          // Only a list that never loaded reads as failed.
          var sc = scaffoldFor('tools');
          if (sc && toolConfigs === null) {
            sc.listEl.textContent = '';
            sc.listEl.appendChild(App.ui.util.el('div', { className: 'admin-loading', text: 'Failed to load tools.' }));
          }
        });
    }

    // A list re-render (M25 F3 L5b): with the tool editor open below, only the
    // list section is rebuilt; the editor is never touched.
    function populateToolGrid() {
      renderToolsListNow();
    }

    function handleToolToggle(name, newEnabled) {
      // Drop second click while a PUT is pending for this tool.
      if (toolsInFlight[name] || !toolConfigs) return;

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
        // The toggled tool is the one open below: its editor's Enabled
        // control and saved snapshot follow, in place (no re-mount, so an
        // unsaved edit elsewhere in the form is kept).
        if (editingTool && editingTool.name === name) {
          editingTool.enabled = newEnabled;
          if (toolEditorApi) toolEditorApi.setEnabled(newEnabled);
        }
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

    // ── Opening and closing items from the page (M25 F3 L5b) ────────
    // One delegated click listener on the area's content, ahead of App.nav's
    // document-level link interceptor:
    // * the item header's breadcrumb link ("Settings / Providers" or
    //   "Settings / Built-in tools"; with Back retired it closes the item):
    //   an intent go() to the page root, so the router's guard asks once
    //   about a dirty editor and the root hydrate closes the item in place.
    //   Once it has navigated, focus goes to the closed item's row (DD8); a
    //   create form has no row, so the nearest surviving row (the grid's
    //   first provider link), else "Add provider". The focus waits one task:
    //   after a Continue, nav.js focuses <main> from a setTimeout. Built-in
    //   tools have no create form, and a closed tool always has its own tile.
    // * a list link to the item ALREADY open (its row, its tool name): no
    //   navigation (nothing to ask about, nothing to re-mount); the item is
    //   just brought into view and focused.
    // Modified clicks (new tab, etc.) keep the browser's behaviour.
    function closingItem() {
      return {
        category: currentCategory,
        providerId: providerFormMode === 'edit' && editingProvider ? editingProvider.id : null,
        create: providerFormMode === 'add',
        toolName: toolFormMode === 'edit' && editingTool ? editingTool.name : null
      };
    }

    function focusClosedItem(closing) {
      var sc = scaffoldFor(closing.category);
      if (!sc || providerFormMode || toolFormMode) return; // the user moved on
      if (closing.category === 'providers') {
        // DD8's one rule for Cancel, close and delete: a `~new` form has no row
        // of its own, so the first tile, else "Add provider" when the grid is
        // empty (as the create-form Cancel; leg 5b focused "Add provider"
        // always, and the behavior-gate fix aligned it with Agents/Library).
        if (closing.create || !closing.providerId) { focusProviderRowNear(0); return; }
        var idx = App.admin.providerRowIndex(sc.listEl, closing.providerId);
        focusProviderRowNear(idx);
        return;
      }
      if (closing.category === 'tools' && closing.toolName) {
        var tiles = sc.listEl.querySelectorAll('[data-testid="tool-card"]');
        for (var i = 0; i < tiles.length; i++) {
          if (tiles[i].getAttribute('data-name') !== closing.toolName) continue;
          var link = tiles[i].querySelector('a');
          if (link && link.offsetParent !== null) link.focus();
          return;
        }
      }
    }

    function openItemLink(target) {
      if (!scaffold) return null;
      var row = target.closest('a.provider-tile-link');
      if (row && scaffold.listEl.contains(row)) {
        return providerFormMode === 'edit' && editingProvider && row.getAttribute('data-id') === editingProvider.id
          ? row : null;
      }
      var toolLink = target.closest('a.tool-tile-link');
      if (toolLink && scaffold.listEl.contains(toolLink)) {
        var tile = toolLink.closest('[data-testid="tool-card"]');
        return toolFormMode === 'edit' && editingTool && tile && tile.getAttribute('data-name') === editingTool.name
          ? toolLink : null;
      }
      return null;
    }

    content.addEventListener('click', function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      var target = e.target;
      if (!target || typeof target.closest !== 'function') return;
      if (openItemLink(target)) {
        e.preventDefault();
        revealItem(scaffold.itemEl);
        return;
      }
      var link = target.closest('a.editor-breadcrumb-link');
      if (!link || !content.contains(link)) return;
      e.preventDefault();
      var closing = closingItem();
      App.router.go(link.getAttribute('href'), { opener: link }).then(function (navigated) {
        if (navigated) setTimeout(function () { focusClosedItem(closing); }, 0);
      });
    });

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
    // F6 leg 03. The orchestrator's mountProviderItem above delegates
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
      if (GENERAL_RENDERERS[currentCategory]) {
        renderContent();
      } else if (currentCategory === 'providers') {
        // The list refreshes with an editor open too (M25 F3 L5b): only the
        // tile grid re-renders, never the editor below it.
        fetchProviders().then(function () {
          self._tryConsumePendingProvider();
        });
        loadAgentsForTable();
      } else if (currentCategory === 'tools') {
        fetchToolConfigs();
        // Re-fetch the per-tool detail so the editor reflects external changes
        // (e.g., DB tweak) while the editor was mounted. It re-mounts the
        // item section only (no focus move: not an intent).
        if (toolFormMode === 'edit' && editingTool) selectTool(editingTool.name);
      } else if (currentCategory === 'knowledge' && !dirty) {
        // Skip the refetch while dirty so a cross-area-and-back trip never
        // silently clobbers an unsaved edit. A dirty knowledge panel simply
        // keeps showing its own state.
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
        // re-renders from the saved settings). Otherwise tear the item down:
        // on an item page (Providers, Built-in tools) that empties the item
        // section below the list (M25 F3 L5b), so no discarded editor lingers
        // under the tiles; anywhere else the next _setCategory re-renders.
        if (currentCategory !== 'knowledge') {
          self._closeOpenItem();
          if (!scaffoldFor(currentCategory)) editorDomStale = true;
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
    // the current category -- or going to its root -- closes the item. On the
    // item pages (Providers, Built-in tools) the close happens IN PLACE (M25
    // F3 L5b, DD7): the item section is emptied and the list stays as it is.
    self._setCategory = function (sub) {
      if (scaffoldFor(sub) && !editorDomStale) {
        if (providerFormMode || toolFormMode || pendingFormMode || pendingProviderId ||
            pendingToolFormMode || pendingToolName) {
          self._closeOpenItem();
        }
        settingsNav.setSelected(routeSection(currentCategory));
        return;
      }
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
        openIntent = false;
        settingsNav.setSelected(routeSection(currentCategory));
        renderContent();
      }
    };
    // The nav's selection is the current page's section (never an item id).
    self._syncNavSelection = function () {
      settingsNav.setSelected(routeSection(currentCategory));
    };
    // The list's selection is the open item, else the pending one (a deep
    // link still loading): the provider row, the tool tile. In place.
    self._syncItemSelection = function () {
      var sp = scaffoldFor('providers');
      if (sp) App.admin.setProvidersSelection(sp.listEl, selectedProviderId());
      var st = scaffoldFor('tools');
      if (st) App.admin.setToolsSelection(st.listEl, selectedToolName());
    };
    // hydrateState marks an item route as an intent (see openIntent).
    self._setOpenIntent = function (on) { openIntent = !!on; };
    // Close the open provider/tool item: its state and, on an item page, its
    // DOM (the item section is emptied; M25 F3 L5b). An item hydrate inside
    // the category that is already showing then mounts the new item there.
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
      openIntent = false;
      clearItemSection();
      self._syncItemSelection();
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
        mountProviderItem();
        self._syncItemSelection();
        return;
      }
      if (pendingFormMode === 'edit' && pendingProviderId && allowCache !== false) {
        var found = findProvider(pendingProviderId);
        if (found) {
          providerFormMode = 'edit';
          editingProvider = found;
          pendingProviderId = null;
          pendingFormMode = null;
          mountProviderItem();
          self._syncItemSelection();
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
