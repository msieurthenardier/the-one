App.registerArea({
  id: 'admin',
  label: 'System',
  icon: App.icons.admin,
  order: 30,

  // The General pages (M25 F3 L5a, DD6): the former single "General" page is
  // three, each with its own route (#settings/appearance|prompts|encryption).
  // Their area subs equal their route sections. The legacy `general` and
  // `system` subs map to the first of them.
  GENERAL_SUBS: ['appearance', 'date-and-time', 'prompts', 'encryption'],


  serializeState: function () {
    if (this.GENERAL_SUBS.indexOf(this._currentCategory) !== -1) return this._currentCategory;
    if (this._currentCategory === 'tools') {
      return this._toolsPage ? this._toolsPage.serialize() : 'tools';
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
    // this, currentCategory retains whatever it was (e.g. 'tools') and the
    // router's post-hydrate sync would rewrite the URL to that retained state
    // instead of the canonical default. F6 HAT regression. (The router itself
    // never hydrates an empty admin sub: a bare #settings resolves to its root.)
    if (!sub) {
      if (this._setCategory) this._setCategory(this.GENERAL_SUBS[0]);
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


    // The tools item route ('tools/{name}'): the tools page parses its own sub.
    var pendingToolName_local = null;
    var pendingToolFormMode_local = null;
    var toolsSub = App.admin.toolsPage.parseSub(origSub);
    if (toolsSub) {
      sub = 'tools';
      pendingToolName_local = toolsSub.pendingName;
      pendingToolFormMode_local = toolsSub.pendingMode;
    }


    var validIds = this.GENERAL_SUBS.concat(['tools', 'knowledge']);
    if (validIds.indexOf(sub) === -1) return;

    // Set category FIRST — _setCategory wipes pending state on category change,
    // so we must set pending AFTER it to survive the wipe.
    //
    // An ITEM sub inside the category that is already showing does not go
    // through _setCategory: it would re-render the grid (and refetch the list)
    // only for the item to replace it. The open item is closed in state and
    // the consume paths below render the item directly.
    var itemSub = !!pendingToolFormMode_local;
    if (itemSub && this._currentCategory === sub) {
      if (this._closeOpenItem) this._closeOpenItem();
    } else if (this._setCategory) {
      this._setCategory(sub);
    }

    // Always overwrite pending state — including with nulls when the new
    // sub does not match tools/... — so navigating from
    // #settings/tools/{name} → #settings/appearance clears pending state.
    this._pendingToolName = pendingToolName_local;
    this._pendingToolFormMode = pendingToolFormMode_local;
    // An item route is a navigation the user made (a tool name link,
    // Back/Forward, a deep link or boot): the item, once mounted,
    // scrolls its header into view and takes focus (M25 F3 L5b, DD7). Store
    // notifications and _refresh re-fetches never set this.
    if (this._setOpenIntent) this._setOpenIntent(itemSub);

    // Sub-state changes within the same category (e.g., #settings/tools →
    // #settings/tools/{name}) do NOT trigger _setCategory's re-render path
    // because currentCategory is unchanged. Fire consume unconditionally so
    // within-admin sub navigation actually opens the editor.
    if (this._tryConsumePendingTool) this._tryConsumePendingTool();
    // The Settings nav marks the page's SECTION on every hydrate, item routes
    // included (#settings/tools/{name} keeps "Built-in tools" selected).
    if (this._syncNavSelection) this._syncNavSelection();
    // The list marks the open (or pending) item: the tool tile.
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
    // Groups in table order.
    var navGroups = [];
    var groupByLabel = {};
    for (var pg = 0; pg < App.settingsPages.length; pg++) {
      var navPage = App.settingsPages[pg];
      if (!Object.prototype.hasOwnProperty.call(groupByLabel, navPage.group)) {
        groupByLabel[navPage.group] = { label: navPage.group, items: [] };
        navGroups.push(groupByLabel[navPage.group]);
      }
      groupByLabel[navPage.group].items.push(navItem(navPage));
    }
    var currentCategory = this.GENERAL_SUBS[0];
    var contentEl;

    // Orchestrator's mirror of the open editor's local `dirty` flag (F6 leg
    // 04). The editor sub-module is the source of truth for the disabled-button
    // flip; the orchestrator mirror is the source of truth for the leave guard
    // (App.nav source, registered below). The bridge is the onDirtyChange
    // callback of the tools editor and the Knowledge indexing page.
    var dirty = false;
    // Discard generation (M25 F2 L5): the App.nav discard() bumps it; an async
    // resolver captured under an older generation (an in-flight save) must not
    // resurrect the editor state it tore down. The tools page shares this one
    // counter through its ctx.
    var editorGen = 0;
    // Set by a discard that tore an editor down in STATE only: the editor DOM is
    // still mounted, so the next _setCategory must re-render even though no item
    // is open any more. Cleared by every panel render. (Since M25 F3 L5b a
    // discard on an item page clears its item section, so it never sets this.)
    var editorDomStale = false;

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
    contentEl = App.ui.util.el('div', { className: 'admin-content' });
    content.textContent = '';
    content.appendChild(contentEl);

    var self = this;

    // The Built-in tools page (areas/admin/tools-page.js). It reaches this
    // area only through the ctx below; the _tool* seams further down forward to
    // its state, so they are defined before anything can reach the handle.
    var tools = App.admin.toolsPage.create({
      getCategory: function () { return currentCategory; },
      setDirty: function (d) { dirty = !!d; },
      getGen: function () { return editorGen; },
      bumpGen: function () { editorGen += 1; },
      setDomStale: function (s) { editorDomStale = !!s; },
      contentEl: function () { return contentEl; },
      content: content,
      serializeState: function () { return self.serializeState(); },
      pageLabel: pageLabel
    });
    self._toolsPage = tools;

    // ── Rendering ─────────────────────────────────────────────────────

    // The General pages (system-page.js): each renders only its own block.
    var GENERAL_RENDERERS = {
      appearance: 'renderAppearancePage',
      'date-and-time': 'renderDateTimePage',
      prompts: 'renderPromptsPage',
      encryption: 'renderEncryptionPage'
    };

    function renderContent() {
      // Every page render replaces the content; Built-in tools mounts a fresh
      // scaffold.
      tools.reset();
      if (GENERAL_RENDERERS[currentCategory]) {
        App.admin[GENERAL_RENDERERS[currentCategory]](contentEl);
      } else if (currentCategory === 'tools') {
        tools.render();
      } else if (currentCategory === 'knowledge') {
        renderKnowledgePanel();
      }
    }

    // ── Knowledge Panel (F6 leg 04, DD-7) ─────────────────────────────
    // No grid/editor split — the whole category is one form, so it delegates
    // straight to the sub-module and bridges its dirty state onto the shared
    // `dirty` mirror exactly as the tools editor does.
    function renderKnowledgePanel() {
      editorDomStale = false;
      dirty = false;
      App.admin.renderKnowledgeSettingsPage(contentEl, {
        onDirtyChange: function (d) { dirty = d; }
      });
    }

    // Store reference for activate() to reuse
    self._refresh = function () {
      if (GENERAL_RENDERERS[currentCategory]) {
        renderContent();
      } else if (currentCategory === 'tools') {
        tools.refresh();
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
      return (currentCategory === 'tools' && tools.isOpen())
        || currentCategory === 'knowledge';
    }
    self._discardEditor = function () {
      editorGen += 1;
      App.focusAfter.cancel();
      try {
        // Knowledge settings is one form: discard is just dirty=false (re-entry
        // re-renders from the saved settings). Otherwise tear the item down:
        // on an item page (Built-in tools) that empties the item
        // section below the list (M25 F3 L5b), so no discarded editor lingers
        // under the tiles; anywhere else the next _setCategory re-renders.
        if (currentCategory !== 'knowledge') {
          self._closeOpenItem();
          if (!tools.scaffoldFor(currentCategory)) editorDomStale = true;
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
    // The tool-state seams forward to the tools page's state.
    ['toolFormMode', 'editingTool', 'pendingToolName', 'pendingToolFormMode'].forEach(function (key) {
      Object.defineProperty(self, '_' + key, {
        get: function () { return tools[key]; },
        set: function (v) { tools[key] = v; },
        configurable: true
      });
    });
    // Section-root semantics: hydrating a category renders exactly that
    // category. A category CHANGE resets everything; the SAME category with an
    // item open (the tool editor) closes it, so clicking
    // the current category -- or going to its root -- closes the item. On the
    // item page (Built-in tools) the close happens IN PLACE (M25
    // F3 L5b, DD7): the item section is emptied and the list stays as it is.
    self._setCategory = function (sub) {
      if (tools.scaffoldFor(sub) && !editorDomStale) {
        if (tools.hasItemOrPending()) {
          self._closeOpenItem();
        }
        settingsNav.setSelected(routeSection(currentCategory));
        return;
      }
      // Knowledge has no grid/editor split (the whole panel is the form), so
      // re-hydrating it re-renders from the saved settings: Continue discards.
      var itemOpen = !!(tools.toolFormMode || currentCategory === 'knowledge');
      if (currentCategory !== sub || itemOpen || editorDomStale) {
        editorGen += 1;
        App.focusAfter.cancel();
        currentCategory = sub;
        tools.onCategoryChange();
        dirty = false;
        settingsNav.setSelected(routeSection(currentCategory));
        renderContent();
      }
    };
    // The nav's selection is the current page's section (never an item id).
    self._syncNavSelection = function () {
      settingsNav.setSelected(routeSection(currentCategory));
    };
    // The list's selection is the open item, else the pending one (a deep
    // link still loading): the tool tile. In place.
    self._syncItemSelection = function () { tools.syncItemSelection(); };
    // hydrateState marks an item route as an intent (see the tools page).
    self._setOpenIntent = function (on) { tools.setOpenIntent(on); };
    // Close the open tool item (state and, on an item page, DOM).
    self._closeOpenItem = function () { tools.closeOpenItem(); };
    self._tryConsumePendingTool = function () { tools.tryConsumePending(); };

    // ── Init ──────────────────────────────────────────────────────────

    renderContent();
  },

  activate: function () {
    if (this._refresh) {
      this._refresh();
    }
  },

  deactivate: function () {}
});
