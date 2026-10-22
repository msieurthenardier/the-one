// App.studio.knowledgeGlue -- the Library "Knowledge bases" group's section glue
// (M31 F2 L02b, DD1): the section dispatch (create form, detail view, section
// root), the create form and detail mounts, and the 5 s status poll. Moved
// verbatim out of studio.js; a factory it calls once in init:
//
//   var knowledge = App.studio.knowledgeGlue.create(ctx);
//
// ctx (studio -> module): self, state, pane (the libraryPane handle),
// providers (the providers-section handle), setActiveSection, discardOpen,
// writeUrl, sectionContent() (the detail host; the element is created once),
// fetchAgents, buildRootHeading, agentData. The poll timer stays on
// `self._knowledgePollTimer` because `deactivate` reads it.
//
// handle (module -> studio): render() (renderKnowledgeSection), reset() (stop
// the poll and drop the detail handle), isOpen() (a detail or the create form),
// clearPoll(), itemsSignature(status).
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
    var setActiveSection = ctx.setActiveSection;
    var reloadLibrary = pane.reload;
    var syncLibrarySelection = pane.sync;
    var libraryRowIndex = pane.rowIndex;
    var focusLibraryRowNear = pane.focusNear;
    var focusLibraryGroupStart = pane.focusGroupStart;
    var renderLibraryEmpty = pane.renderEmpty;

    // Knowledge section (Flight 6 leg 1, DD-2, L1-D1; M25 F3 L4a) — the
    // global knowledge-base inventory. Three-branch dispatch: the create form
    // (kbCreateMode), a detail view (self._selectedKbId set) and, at the
    // section root, the empty detail state beside the Library list,
    // hash-routed by serializeState/hydrateState above as 'knowledge/new' /
    // 'knowledge/{kb_id}' / 'knowledge'.
    // kb-studio-round-trip remediation FIX 1 (2026-09-18): the signature
    // (per-status counts + chunk count) the items list was LAST rendered
    // against. The status poll re-fetches `/items` and rebuilds the list
    // only when a fresh `/status` response's signature differs from this
    // one — never on every tick, which would blow away an open chunks/
    // source panel or scroll position (L1-D2's actual intent). Reset to
    // null on every fresh mount below so the first poll tick after a
    // remount compares against the mount-time snapshot, not a stale
    // knowledge base's signature.
    //
    // Flight 7 Leg 2 (DD-6): widened to fold in `status.content_freshness`
    // (the backend's MAX(indexed_at)-over-file-items aggregate) — WITHOUT
    // it, a content-only edit to an already-indexed file changes neither
    // the per-status counts nor the chunk count, so this signature never
    // moved and the `/items` re-fetch below never fired, even though the
    // freshness field the item row now renders (AC-1) had gone stale. Both
    // halves land in the same commit — DD-6's own reason: shipping the
    // render half alone would have converted an invisible blind spot into
    // a visible staleness bug.
    var lastKnownItemsSignature = null;

    function knowledgeItemsSignature(status) {
      return (
        JSON.stringify((status && status.items) || {}) +
        '|' + (status && status.chunks) +
        '|' + (status && status.content_freshness)
      );
    }

    function renderKnowledgeSection() {
      sectionContentEl.innerHTML = '';
      if (state.kbCreateMode) {
        clearKnowledgePoll();
        state.knowledgeDetailHandle = null;
        renderKnowledgeCreateView();
      } else if (self._selectedKbId) {
        renderKnowledgeDetailView(self._selectedKbId);
      } else {
        // L1-D2 site 3: leaving the detail view for the section root stops the
        // poll -- covered here since every root mount (direct nav, the
        // breadcrumb's group link, browser Back, delete) routes through this
        // branch.
        clearKnowledgePoll();
        state.knowledgeDetailHandle = null;
        renderLibraryEmpty();
      }
      syncLibrarySelection(false);
    }

    // The create form (M25 F3 L4a, DD8; closes squawk 0101): `#library/
    // knowledge/~new` in the detail pane. Creating opens the new knowledge
    // base's detail view (a bypass go() REPLACING the create entry, after the
    // store reload, so the router names the new item); Cancel discards and
    // replaces to the section root.
    function renderKnowledgeCreateView() {
      state.dirty = false;
      var kbGen = state.editorGen;
      function stillOnCreate() {
        var cur = App.router.current();
        return kbGen === state.editorGen && state.kbCreateMode && !!cur &&
          cur.route === 'library/knowledge/' + '~new';
      }
      App.studio.renderKnowledgeCreate(sectionContentEl, {
        onDirtyChange: function (d) { if (kbGen === state.editorGen) state.dirty = d; },
        onCancel: function () {
          discardOpen_();
          App.router.go(App.router.href({ destination: 'library' }),
            { replace: true, bypassGuard: true });
          focusLibraryGroupStart('knowledge');
        },
        // Called after the POST succeeded and the module invalidated
        // 'knowledge-bases'. Order (H1): clear `dirty` at once -- only while
        // the user is still on this form, since the flag is shared by every
        // studio editor -- then await the store reload (the row exists and the
        // router can name the new item), then, still on this form and with no
        // decision pending, replace ~new with the new item.
        onCreateSuccess: function (kb) {
          if (stillOnCreate()) state.dirty = false;
          var open = function () {
            if (!stillOnCreate() || App.router.isDeciding()) return;
            state.kbFocusFolderFor = kb.id;
            App.router.go(App.router.href({ destination: 'library', section: 'knowledge', id: kb.id }),
              { replace: true, bypassGuard: true });
          };
          reloadLibrary('knowledge-bases').then(open, open);
        }
      });
    }

    self._focusKbCreate = function () { pane.focusCreate('knowledge'); };

    function findKnowledgeBase(id) {
      if (!state.knowledgeBases) return null;
      for (var i = 0; i < state.knowledgeBases.length; i++) {
        if (state.knowledgeBases[i].id === id) return state.knowledgeBases[i];
      }
      return null;
    }

    // Navigation away from a KB detail that is gone or finished (delete, a 404
    // poll bounce): a bypass go() REPLACING the detail's entry, so Back does not
    // land on a dead KB. No leave guard -- the user did not ask to leave.
    function leaveKnowledgeDetail_() {
      discardOpen_(); // the detail is for a gone item: tear it down first
      App.router.go(App.router.href({ destination: 'library' }),
        { replace: true, bypassGuard: true });
    }

    function renderKnowledgeDetailView(kbId) {
      // Opening another knowledge base stops the previous one's poll at once.
      clearKnowledgePoll();
      state.knowledgeDetailHandle = null;
      // The create form's folder-focus request applies to its own new item
      // only (it survives the create form's closeOpenItem on the way here).
      if (state.kbFocusFolderFor !== kbId) state.kbFocusFolderFor = null;
      // A fresh hydrate (traversal, typed hash, boot) skips the cached list: the
      // KB may have been deleted since it was cached, so it is fetched.
      var skipCache = self._kbFresh === true;
      self._kbFresh = false;
      var cached = skipCache ? null : findKnowledgeBase(kbId);
      if (cached) {
        mountKnowledgeDetail(cached);
        return;
      }
      // Not in the section cache (e.g. a direct hash-load on
      // #library/knowledge/{kb_id} before the list has loaded) — fetch it
      // directly rather than waiting on the list. The detail pane shows
      // nothing meanwhile (never the section root's empty state).
      fetch('/api/knowledge-bases/' + encodeURIComponent(kbId))
        .then(function (r) {
          if (!r.ok) throw new Error('knowledge base not found: HTTP ' + r.status);
          return r.json();
        })
        .then(function (kb) {
          if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) return;
          mountKnowledgeDetail(kb);
        })
        .catch(function () {
          // Unknown/deleted id — heal the URL to the section root in place (a
          // detail LOAD that finds the item gone) and show the root.
          if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) return;
          self._selectedKbId = null;
          setActiveSection('library');
        });
    }

    function mountKnowledgeDetail(kb) {
      sectionContentEl.innerHTML = '<div class="admin-loading">Loading knowledge base…</div>';
      Promise.all([
        fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/status')
          .then(function (r) {
            if (r.status === 404) { var gone = new Error('knowledge base gone'); gone.gone = true; throw gone; }
            if (!r.ok) throw new Error('status fetch failed: HTTP ' + r.status);
            return r.json();
          }),
        fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items')
          .then(function (r) {
            if (!r.ok) throw new Error('items fetch failed: HTTP ' + r.status);
            return r.json();
          })
      ]).then(function (results) {
        // Stale-then guard: bail if the user navigated away, or to a
        // different knowledge base, mid-fetch.
        if (self._activeSection !== 'knowledge' || self._selectedKbId !== kb.id) return;
        lastKnownItemsSignature = knowledgeItemsSignature(results[0]);
        // F6 L5 (L5-D3): reset the orchestrator's dirty mirror BEFORE the
        // detail view mounts — mirrors the mcp-sources/connectors editor
        // pattern ("Reset orchestrator dirty mirror BEFORE editor mount").
        // The fresh render closure starts clean; onDirtyChange only fires
        // on the operator's first edit-form input.
        state.dirty = false;
        var kbGen = state.editorGen;
        state.knowledgeDetailHandle = App.studio.renderKnowledgeDetail(
          sectionContentEl, kb, { status: results[0], items: results[1] },
          {
            // Back is retired (M25 F3 L4b, DD2): the header breadcrumb's
            // "Knowledge bases" link closes the detail (onBreadcrumbClick).
            // DD8: replace to the section root; the row leaves the list (the
            // module invalidated the collection) and focus goes to the row
            // now at its index (the next, else the previous), else Add. The
            // index is read first, while the row is still listed.
            onDeleteSuccess: function () {
              var rowIndex = libraryRowIndex('knowledge:' + kb.id);
              leaveKnowledgeDetail_();
              reloadLibrary('knowledge-bases').then(function () { focusLibraryRowNear(rowIndex); });
            },
            // F6 L3 (L3-D5), carried by F6 L5's Name+Description edit form
            // (L5-D2): re-mount the detail view from the saved object —
            // refreshes the header title and re-fetches status/items. The
            // module invalidated the collection, so the list's row follows
            // the rename (M25 F3 L4a: reloadLibrary, no manual cache patch).
            onSaveSuccess: function (updatedKb) {
              if (kbGen !== state.editorGen) return; // discarded mid-save: no resurrection
              reloadLibrary('knowledge-bases');
              mountKnowledgeDetail(updatedKb);
            },
            // F6 L5 (L5-D3): bridges the edit form's dirty state into the
            // orchestrator's closure `dirty`, consumed by
            // the App.nav source's `isDirty` (`editorOpen`) — mirrors the
            // mcp-sources/connectors `onDirtyChange: function (d) { dirty = d; }`
            // pattern already established below.
            onDirtyChange: function (d) { state.dirty = d; }
          }
        );
        startKnowledgePoll(kb.id);
        // A just-created knowledge base (squawk 0101): registering a folder is
        // always the next step, and the form the user was typing in is gone.
        if (state.kbFocusFolderFor === kb.id) {
          state.kbFocusFolderFor = null;
          var folderInput = sectionContentEl.querySelector('[data-testid="kb-folder-path-input"]');
          if (folderInput) folderInput.focus();
        }
        App.focusAfter.flush();
      }).catch(function (err) {
        if (self._activeSection !== 'knowledge' || self._selectedKbId !== kb.id) return;
        if (err && err.gone) {
          // Cached KB deleted meanwhile: same heal as a 404 on the detail GET.
          self._selectedKbId = null;
          setActiveSection('library');
          return;
        }
        sectionContentEl.innerHTML = '<div class="admin-loading">Failed to load knowledge base.</div>';
      });
    }

    // ── L1-D2: the 5-second status poll, owned here (not by the render
    // module) so the three clear sites below can all reach one handle.
    function clearKnowledgePoll() {
      if (self._knowledgePollTimer) {
        clearInterval(self._knowledgePollTimer);
        self._knowledgePollTimer = null;
      }
    }

    function startKnowledgePoll(kbId) {
      clearKnowledgePoll(); // single handle — never stack timers across re-renders
      self._knowledgePollTimer = setInterval(function () {
        if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) {
          clearKnowledgePoll();
          return;
        }
        fetch('/api/knowledge-bases/' + encodeURIComponent(kbId) + '/status')
          .then(function (r) {
            if (r.status === 404) {
              // Edge case: the knowledge base was deleted while this view
              // was open (another tab, or the poll racing a delete) —
              // return to the section root rather than leaving a dead view
              // or looping on the error.
              clearKnowledgePoll();
              if (self._activeSection === 'knowledge' && self._selectedKbId === kbId) {
                leaveKnowledgeDetail_();
              }
              return null;
            }
            if (!r.ok) throw new Error('status poll failed: HTTP ' + r.status);
            return r.json();
          })
          .then(function (status) {
            if (!status) return; // 404 branch above already handled it
            if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) return;
            if (state.knowledgeDetailHandle) state.knowledgeDetailHandle.updateStatus(status);
            // kb-studio-round-trip remediation FIX 1: invalidate the items
            // list only when the counts it was last rendered against have
            // changed (registering a folder, an indexing pass completing,
            // a watcher pickup, …) — re-fetching `/items` on every tick
            // would destroy an open chunks/source panel and scroll
            // position, which is exactly what L1-D2 excluded polling items
            // to avoid.
            var signature = knowledgeItemsSignature(status);
            if (signature !== lastKnownItemsSignature) {
              fetch('/api/knowledge-bases/' + encodeURIComponent(kbId) + '/items')
                .then(function (r2) {
                  if (!r2.ok) throw new Error('items poll failed: HTTP ' + r2.status);
                  return r2.json();
                })
                .then(function (freshItems) {
                  if (self._activeSection !== 'knowledge' || self._selectedKbId !== kbId) return;
                  if (state.knowledgeDetailHandle && state.knowledgeDetailHandle.updateItems) {
                    state.knowledgeDetailHandle.updateItems(freshItems);
                  }
                  lastKnownItemsSignature = signature;
                })
                .catch(function () {
                  // Leave the list as last rendered; `lastKnownItemsSignature`
                  // is not advanced, so this is retried on the next tick.
                });
            }
          })
          .catch(function () {
            // L1-D2: a failed poll leaves the last-rendered state — no
            // blanking, no escalation to a flash.
          });
      }, 5000);
    }

    return {
      render: renderKnowledgeSection,
      reset: function () {
        clearKnowledgePoll();
        state.knowledgeDetailHandle = null;
      },
      isOpen: function () { return !!(self._selectedKbId || state.kbCreateMode); },
      clearPoll: clearKnowledgePoll,
      itemsSignature: knowledgeItemsSignature
    };
  }

  window.App.studio.knowledgeGlue = { create: create };
})();
