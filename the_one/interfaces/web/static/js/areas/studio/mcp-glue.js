// App.studio.mcpGlue -- the Library "MCP servers" group's section glue (M31 F2
// L02b, DD1): the section dispatch (editor, a pending id resolving, section
// root), the editor mount with its orchestrator callbacks, the type list and the
// pending-consume. Moved verbatim out of studio.js; a factory it calls once in
// init:
//
//   var mcp = App.studio.mcpGlue.create(ctx);
//
// ctx (studio -> module): self, state, pane (the libraryPane handle),
// providers (the providers-section handle), setActiveSection, discardOpen,
// writeUrl, sectionContent() (the detail host; the element is created once),
// fetchAgents, buildRootHeading, agentData.
//
// handle (module -> studio): render() (renderMcpSourcesSection),
// prefetchTypes() (the boot pre-fetch of the type list), tryConsumePending(
// allowCache) -> bool, reset() (close the open form), isOpen() (a form is open).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var pane = ctx.pane;
    var sectionContentEl = ctx.sectionContent(); // created once by the shell, never replaced
    var discardOpen_ = ctx.discardOpen;
    var reloadLibrary = pane.reload;
    var syncLibrarySelection = pane.sync;
    var libraryRowIndex = pane.rowIndex;
    var focusLibraryRowNear = pane.focusNear;
    var focusLibraryGroupStart = pane.focusGroupStart;
    var renderLibraryEmpty = pane.renderEmpty;

    var MCP_TYPES = [];
    var mcpTypesReady = null;
    // The live editor controller (M31 F5 L03), set only from onMounted and only in
    // the mount's own generation; destroyed before every replacement and close.
    var current = null;
    function destroyCurrent() {
      var ctl = current;
      current = null;
      if (ctl) ctl.destroy();
    }

    // MCP Servers section — relocated from admin (post-F2 retrofit). The
    // editor branch waits for the type list then delegates to
    // App.studio.renderMcpSourceEditor; at the section root the detail pane
    // shows the empty state beside the Library list (M25 F3 L4a: the grid is
    // retired). The orchestrator-side callbacks bridge dirty-state +
    // navigation.
    function renderMcpSourcesSection() {
      destroyCurrent();
      sectionContentEl.replaceChildren();
      // If a hash-route pending-create is queued (e.g. direct-load on
      // #library/mcp/~new), promote it to mcpSourceFormMode='add' BEFORE
      // deciding so the editor mounts on first paint. Pending-edit can't
      // promote here because the source needs to be in the cache; the
      // pending-item rule (resolvePendingLibraryItem) handles that path.
      if (!state.mcpSourceFormMode && self._pendingMcpSourceFormMode === 'add') {
        state.mcpSourceFormMode = 'add';
        state.editingMcpSource = null;
        self._pendingMcpSourceFormMode = null;
        self._pendingMcpSourceId = null;
      }
      if (state.mcpSourceFormMode) {
        // Reset orchestrator dirty mirror BEFORE editor mount (mirrors the
        // provider-editor pattern). Editor's onDirtyChange fires on first
        // user input.
        state.dirty = false;
        var ready = mcpTypesReady || fetchMcpSourceTypes();
        var mcpGen = state.editorGen;
        ready.then(function () {
          if (mcpGen !== state.editorGen) return; // discarded while the types loaded
          // Re-check formMode at resolution time — operator may have
          // navigated away mid-fetch.
          if (state.mcpSourceFormMode == null || self._activeSection !== 'mcp-sources') return;
          // Two queued renders must not leave an orphan (the connector precedent).
          destroyCurrent();
          App.studio.renderMcpSourceEditor(sectionContentEl, state.editingMcpSource, MCP_TYPES, {
            // Every mount reports its controller, Reset's re-mount included. One
            // reported in a stale generation is destroyed at once.
            onMounted: function (ctl) {
              if (mcpGen !== state.editorGen) { ctl.destroy(); return; }
              current = ctl;
            },
            // Back is retired (M25 F3 L4b, DD2): the header breadcrumb's
            // "MCP servers" link closes the editor (onBreadcrumbClick).
            onCancel: function () {
              // Create-mode Cancel (DD8): discard, then a bypass go()
              // REPLACING the create entry with the section root (Back must
              // not land on a stale create form); focus goes to the group's
              // first row, else Add. Edit-mode Cancel reverts the form
              // in-place and never reaches this callback.
              discardOpen_();
              App.router.go(App.router.href({ destination: 'library' }),
                { replace: true, bypassGuard: true });
              focusLibraryGroupStart('mcp-sources');
            },
            onSaveSuccess: function (updated, isCreate) {
              if (mcpGen !== state.editorGen) return; // discarded mid-save: no resurrection
              state.editingMcpSource = updated;
              state.mcpSourceFormMode = 'edit';
              state.dirty = false;
              // The editor invalidated 'mcp-sources': the list shows the new
              // or renamed row.
              reloadLibrary('mcp-sources');
              // The name hint (M25 F3 L2, DD8): a just-created source is not in
              // the store yet. On create this sync is the ~new -> item
              // transition, which it announces; the editor save invalidated
              // 'mcp-sources' first.
              if (window.App && window.App.router) {
                App.router.sync('studio', self.serializeState(), { name: updated.name });
              }
              syncLibrarySelection(true);
              if (isCreate) {
                // create→edit transition: re-render so Danger Zone +
                // edit-mode subtitle render with the newly-assigned id.
                var replaced = current; // the create editor, destroyed by this render
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
                // The deferred runTest({autoRun: true}) runs only on the edit
                // mount of THIS created source (a newer render, another item or
                // a close has replaced `current` or `editingMcpSource`).
                setTimeout(function () {
                  if (updated && updated.type !== 'streamable-http') return;
                  var ctl = current;
                  if (!ctl || ctl === replaced || mcpGen !== state.editorGen ||
                      state.editingMcpSource !== updated) return;
                  ctl.runTest({ autoRun: true });
                }, 0);
              }
            },
            onDeleteSuccess: function () {
              // DD8: the row index is read first (the row is still listed:
              // invalidate notifies nobody), then the dead item's editor is
              // torn down and a bypass go() replaces its entry with the
              // section root; focus follows the reload.
              var rowIndex = libraryRowIndex('mcp:' + (state.editingMcpSource ? state.editingMcpSource.id : ''));
              discardOpen_();
              App.router.go(App.router.href({ destination: 'library' }),
                { replace: true, bypassGuard: true });
              reloadLibrary('mcp-sources').then(function () { focusLibraryRowNear(rowIndex); });
            },
            // A connect success (Refresh, the auto-run after create, Phase 2
            // after sign-in) or a Reset connection rewrote config._cache and
            // invalidated 'mcp-sources': the row's tool count follows.
            onListStale: function () { reloadLibrary('mcp-sources'); },
            onDirtyChange: function (d) { state.dirty = d; }
          });
          // A create's parked focus restore (M25 F6 L1b, DD2) lands on the new title.
          App.focusAfter.flush();
        });
        syncLibrarySelection(false);
        return;
      }
      // A pending deep-link id still resolving: the detail pane stays empty
      // (never the section root's empty state first).
      if (self._pendingMcpSourceFormMode === 'edit' && self._pendingMcpSourceId) {
        syncLibrarySelection(false);
        return;
      }
      renderLibraryEmpty();
      syncLibrarySelection(false);
    }

    function fetchMcpSourceTypes() {
      mcpTypesReady = fetch('/api/mcp-sources/types')
        .then(function (r) { return r.json(); })
        .then(function (types) { MCP_TYPES = types; })
        .catch(function () { MCP_TYPES = []; });
      return mcpTypesReady;
    }

    // Hydrate-only: a fresh item hydrate (or an intent whose item is not in
    // the cache yet) closes the open form, so the section never re-renders the
    // old item while the new one resolves.
    self._closeMcpForm = function () {
      destroyCurrent();
      state.mcpSourceFormMode = null;
      state.editingMcpSource = null;
      state.dirty = false;
    };

    function findMcpSource(id) {
      if (!state.mcpSources) return null;
      for (var i = 0; i < state.mcpSources.length; i++) {
        if (state.mcpSources[i].id === id) return state.mcpSources[i];
      }
      return null;
    }

    // Opens the pending MCP form (create, or an existing source from the cached
    // list). `allowCache` false skips an existing source. Returns true when it
    // opened an editor.
    function tryConsumePendingMcpSource(allowCache) {
      // Pull pending state from instance properties — hydrateState may have
      // set them after init() already captured the closure-locals.
      var pid = self._pendingMcpSourceId;
      var pmode = self._pendingMcpSourceFormMode;
      if (!pid && !pmode) return false;
      if (pmode === 'add') {
        state.mcpSourceFormMode = 'add';
        state.editingMcpSource = null;
        self._pendingMcpSourceId = null;
        self._pendingMcpSourceFormMode = null;
        renderMcpSourcesSection();
        return true;
      }
      if (pmode === 'edit' && pid && allowCache !== false) {
        var found = findMcpSource(pid);
        if (found) {
          state.mcpSourceFormMode = 'edit';
          state.editingMcpSource = found;
          self._pendingMcpSourceId = null;
          self._pendingMcpSourceFormMode = null;
          renderMcpSourcesSection();
          return true;
        }
        // else: not in the cache; the pending-item rule re-attempts.
      }
      return false;
    }
    self._tryConsumePendingMcpSource = tryConsumePendingMcpSource;
    // Leaving the Library area destroys the editor (studio.js deactivate) and
    // leaves mcpSourceFormMode alone, so a return is a fresh mount as today.
    self._resetMcp = destroyCurrent;
    // Test seam: the live controller (like the area's other `_` seams).
    self._currentMcpEditor = function () { return current; };
    // GleepGlorp's fill and an approval's follow reach the live editor through the same seam.
    App.studio.mcpEditorFill.attach(function () { return current; });
    App.studio.mcpEditorFollow.attach({
      getController: function () { return current; },
      state: state,
      self: self,
      reload: reloadLibrary,
      syncSelection: syncLibrarySelection
    });

    return {
      render: renderMcpSourcesSection,
      prefetchTypes: fetchMcpSourceTypes,
      tryConsumePending: tryConsumePendingMcpSource,
      reset: function () {
        destroyCurrent();
        state.mcpSourceFormMode = null;
        state.editingMcpSource = null;
      },
      isOpen: function () { return !!state.mcpSourceFormMode; }
    };
  }

  window.App.studio.mcpGlue = { create: create };
})();
