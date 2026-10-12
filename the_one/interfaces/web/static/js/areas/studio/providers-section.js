// App.studio.providersSection -- the Library "Model providers" group's detail
// pane (sortie 02, DD4). A factory studio.js calls once in init:
//
//   var handle = App.studio.providersSection.create(ctx);
//
// The module owns the providers item state (form mode, the provider being
// edited, the pending deep link), the provider-type list and the per-type form
// defaults (the only copy since the Settings Providers page retired). It reaches NO
// studio state except through `ctx`; the shared `dirty` flag, the discard
// generation and the Library list helpers are all ctx calls. If it ever needs
// more, the flight's Divert criterion applies: stop and re-plan this interface.
//
// ctx (studio -> module):
//   host()                      the detail pane element (sectionContentEl)
//   getDirty() / setDirty(b)    the shared dirty mirror
//   editorGen() / bumpEditorGen()  the discard generation (closeOpenItem bumps)
//   isActive()                  studio's section is `providers`
//   discardOpen()               the App.nav discard teardown (never a URL write)
//   reloadLibrary(name)         invalidate-then-refetch + list render; Promise
//   syncLibrarySelection(force) re-sync the list's selected row
//   libraryRowIndex(id)         the flat visible-row index of a row id
//   focusLibraryRowNear(idx)    DD8 focus after a delete
//   focusLibraryGroupStart(id)  DD8 focus after a create-form Cancel
//   cache()                     the providers array (the Library cache) | null
//   showRoot()                  setActiveSection('library'): start page + URL heal
//
// handle (module -> studio): formMode(), editingId(), pendingMode(),
// pendingId(), setPending(mode, id), consume(allowCache) -> bool, heal(),
// render(), reset(), selectionId(), createOpen(), editorOpen(), focusCreate(),
// serialize().
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Provider type list -- fetched from /api/providers/types so dev-mode gating
  // for the `mock` type is enforced server-side.
  var PROVIDER_TYPES = [];
  var providerTypesReady = null;

  function fetchProviderTypes() {
    providerTypesReady = fetch('/api/providers/types')
      .then(function (r) { return r.json(); })
      .then(function (types) { PROVIDER_TYPES = types; })
      .catch(function () { PROVIDER_TYPES = []; });
    return providerTypesReady;
  }

  // Static metadata kept unconditional: existing mock providers (created when
  // dev_mode was on) must still render correctly when dev_mode is off. The
  // dropdown filter prevents *new* mock providers; it does not hide existing
  // ones.
  var TYPE_DEFAULTS = {
    'ollama': { base_url: 'http://localhost:11434/v1', showBaseUrl: true, showApiKey: false, showNumCtx: true, showReasoningEffort: true },
    'openai-compatible': { base_url: '', showBaseUrl: true, showApiKey: true, showReasoningEffort: true },
    'openai': { base_url: 'https://api.openai.com/v1', showBaseUrl: false, showApiKey: true, showReasoningEffort: true },
    'anthropic': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: true, showThinkingEnabled: true, showReasoningEffort: true },
    // anthropic-plan (M19 F01 L03): OAuth sign-in instead of an API key; no
    // api-key input EVER, base_url hidden but force-submitted from this
    // default. showPlanSignIn drives the sign-in section's show/hide.
    'anthropic-plan': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: false, showThinkingEnabled: true, showReasoningEffort: true, showPlanSignIn: true },
    // anthropic-plan-token (sortie 03 DD6): a token pasted from `claude setup-token`
    // instead of an OAuth sign-in. The token lives in the api_key column, so the
    // field is the API-key row relabelled; no showPlanSignIn. apiKeyHelp must
    // contain no closing brace (tests/test_admin_reasoning_effort_field.py reads a
    // TYPE_DEFAULTS entry up to the next one).
    'anthropic-plan-token': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: true, showThinkingEnabled: true, showReasoningEffort: true, apiKeyLabel: 'Token', apiKeyPlaceholder: 'sk-ant-oat01-…', apiKeyHelp: 'Run claude setup-token in a terminal and paste the token it prints. It lasts about a year.' },
    'mock': { base_url: '', showBaseUrl: false, showApiKey: false },
    'openrouter': { base_url: 'https://openrouter.ai/api/v1', showBaseUrl: true, showApiKey: true, showReasoningEffort: true }
  };

  function create(ctx) {
    var formMode = null; // null | 'add' | 'edit'
    var editing = null;  // the provider being edited | null (add)
    var pMode = null;    // a pending deep link: null | 'add' | 'edit'
    var pId = null;
    // The mount token: bumped on every render() and reset(), i.e. on ANY change
    // of the mounted editor (not only closeOpenItem's editorGen bump). Each
    // callbacks() closure captures the token it was mounted under and goes inert
    // once it is stale, so an in-flight save/delete cannot act on whatever the
    // user has since moved to.
    var mountToken = 0;

    function find(id) {
      var list = ctx.cache();
      if (!list) return null;
      for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
      return null;
    }

    function rootHref() {
      return App.router.href({ destination: 'library' });
    }

    // The detail pane: the editor, a pending id resolving (nothing yet), or --
    // with nothing open or pending, which only a stray render reaches -- the
    // Library start page through ctx.showRoot().
    function render() {
      var token = ++mountToken;
      var host = ctx.host();
      host.innerHTML = '';
      if (!formMode && pMode === 'add') {
        formMode = 'add';
        editing = null;
        pMode = null;
        pId = null;
      }
      if (formMode) {
        ctx.setDirty(false);
        var ready = providerTypesReady || fetchProviderTypes();
        var gen = ctx.editorGen();
        ready.then(function () {
          // Discarded or re-mounted while the types loaded.
          if (gen !== ctx.editorGen() || token !== mountToken) return;
          if (formMode == null || !ctx.isActive()) return;
          App.studio.renderProviderEditor(host, editing, PROVIDER_TYPES, callbacks(gen, token));
          // A create's or an edit-mode Cancel's parked focus restore (M25 F6 L1b).
          App.focusAfter.flush();
        });
        ctx.syncLibrarySelection(false);
        return;
      }
      if (pMode === 'edit' && pId) {
        ctx.syncLibrarySelection(false);
        return;
      }
      ctx.showRoot();
    }

    function stillOnCreate() {
      var cur = App.router.current();
      return !!cur && cur.route === 'library/providers/' + '~new';
    }

    function callbacks(gen, token) {
      // Stale: the editor was discarded (gen), re-mounted or reset (token), or
      // the section is no longer providers.
      function stale() {
        return gen !== ctx.editorGen() || token !== mountToken || !ctx.isActive();
      }
      return {
        // Back is retired: the header breadcrumb's "Library" link closes the
        // editor (studio's onBreadcrumbClick). Edit mode reverts in place (the
        // editor does it); create mode discards and replaces to #library.
        onCancel: function () {
          if (stale()) return;
          ctx.discardOpen();
          App.router.go(rootHref(), { replace: true, bypassGuard: true });
          ctx.focusLibraryGroupStart('providers');
        },
        // Save-create keeps the editor's render path (no navigation, no
        // hydrate): the editor re-mounts in edit mode from the saved row, and
        // the URL moves from ~new to the item through sync(). The generation
        // and (for a create) the route are checked first, so a save resolving
        // after the user moved on can neither clear `dirty` nor move the URL
        // back (the save-create staleness guard).
        onSaveSuccess: function (updated, isCreate) {
          // Discarded mid-save, or (for a create) the user moved off the create
          // route: no resurrection, no URL move, no `dirty` change. The provider
          // exists though, so the Library list still refreshes.
          if (stale() || (isCreate && !stillOnCreate())) {
            ctx.reloadLibrary('providers');
            return;
          }
          editing = updated;
          formMode = 'edit';
          ctx.reloadLibrary('providers');
          ctx.setDirty(false);
          App.router.sync('studio', 'providers/' + encodeURIComponent(updated.id),
            { name: updated.name });
          ctx.syncLibrarySelection(true);
          if (isCreate) render();
        },
        onDeleteSuccess: function () {
          if (stale()) {
            ctx.reloadLibrary('providers');
            return;
          }
          var rowIndex = ctx.libraryRowIndex('provider:' + (editing ? editing.id : ''));
          ctx.discardOpen();
          App.router.go(rootHref(), { replace: true, bypassGuard: true });
          ctx.reloadLibrary('providers').then(function () { ctx.focusLibraryRowNear(rowIndex); });
        },
        onDirtyChange: function (d) { if (!stale()) ctx.setDirty(d); },
        getTypeDefaults: function (type) { return TYPE_DEFAULTS[type]; }
      };
    }

    // The pending-item consumer (studio's PENDING_KINDS shape): a create form
    // needs no list; an edit id is taken from the Library cache.
    function consume(allowCache) {
      if (!pId && !pMode) return false;
      if (pMode === 'add') {
        formMode = 'add';
        editing = null;
        pId = null;
        pMode = null;
        render();
        return true;
      }
      if (pMode === 'edit' && pId && allowCache !== false) {
        var found = find(pId);
        if (found) {
          formMode = 'edit';
          editing = found;
          pId = null;
          pMode = null;
          render();
          return true;
        }
      }
      return false;
    }

    return {
      formMode: function () { return formMode; },
      editingId: function () { return editing ? editing.id : null; },
      pendingMode: function () { return pMode; },
      pendingId: function () { return pId; },
      setPending: function (mode, id) { pMode = mode || null; pId = id || null; },
      consume: consume,
      // A dead deep-link id (the fresh list does not hold it) heals to #library.
      heal: function () {
        pId = null;
        pMode = null;
        ctx.showRoot();
      },
      render: render,
      // Close the open item (closeOpenItem, discardOpen, the outgoing-section
      // cleanup, hydrate's same-section close). An abandoned create-to-edit
      // hand-off must not fire a sign-in on a later mount.
      reset: function () {
        mountToken++;
        formMode = null;
        editing = null;
        window.App.studio.clearProviderSignInHandoff();
      },
      selectionId: function () {
        if (formMode === 'add') return null;
        if (formMode === 'edit' && editing) return 'provider:' + editing.id;
        if (pMode === 'edit' && pId) return 'provider:' + pId;
        return null;
      },
      createOpen: function () { return ctx.isActive() && formMode === 'add'; },
      editorOpen: function () { return !!formMode; },
      focusCreate: function () {
        var field = ctx.host().querySelector('[data-field="name"]');
        if (field) field.focus();
      },
      // The area sub: providers/new | providers/{id}; null with no item.
      serialize: function () {
        if (formMode === 'add') return 'providers/new';
        if (formMode === 'edit' && editing) return 'providers/' + encodeURIComponent(editing.id);
        if (pMode === 'add') return 'providers/new';
        if (pId) return 'providers/' + encodeURIComponent(pId);
        return null;
      }
    };
  }

  window.App.studio.providersSection = { create: create };
})();
