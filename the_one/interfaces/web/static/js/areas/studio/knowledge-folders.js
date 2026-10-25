// App.studio.knowledgeFolders — the Knowledge detail's Folders section: Add
// folder, the folder panels (chips, meta lines, delete), the grouping of items
// into panels and the keyed reconcile of the panel list (Mission 24 Flight 6
// Leg 6; split out of knowledge-section.js in Mission 31 Flight 3 Leg 02; on
// the library in Leg 06a). The file rows and the "Individual files" panel are
// knowledge-rows.js (Mission 31 Flight 4 Leg 02b), created here with a ctx.
//
// Design notes carried over from the former module header:
//   L6-D2 (amended at the M31 F3 HAT): folders are `App.ui.disclosure` panels
//     (`buildFolderPanel`) containing their own files. Items are grouped by
//     `parent_id` against the CURRENT folder set (`renderAllItems`): an item
//     with no `parent_id` lands in the trailing "Individual files" panel
//     (rows' `renderIndividualFiles`), never nested under a folder its path
//     merely happens to contain (DD-9's standalone chip is exactly for that
//     case, and only applies there). An item whose `parent_id` names a folder
//     the client does not know is HELD OUT of every panel until its folder
//     appears or the item vanishes: `kb_items.parent_id` is ON DELETE CASCADE,
//     so such an item is client lag (the items and status responses crossing),
//     never real state, and showing it among the individual files would be
//     false. A file row INSIDE a folder panel renders its path relative to that
//     folder's root; an "Individual files" row shows the basename.
//   Tombstones: a removed individual file's id goes into `removedIds` (owned
//     HERE, set through rows' `ctx.markRemoved`), a set for the mount's
//     lifetime that `renderAllItems` filters, so a stale /items response can
//     never bring the row back. Walked files (with a `parent_id`) get no
//     remove: the next walk would recreate them.
//   L6-D3: removing a folder is an immediate, irreversible, server-side
//     cascading DELETE, so the trash icon button in the folder's summary keeps
//     the two-step `App.ui.confirm` (the summary is the state element, the
//     disclosure's text its `[data-confirm-title]`). Squawk 0088: the armed
//     state is only safe because nothing RECREATES an armed summary and
//     nothing else writes its text (`updateFolderMeta` never calls
//     `setSummary`; the library's `setSummary` is also a no-op while armed).
//     MOVING an attached node is a separate hazard (M31 F3 L06a):
//     `appendChild`/`insertBefore` of an attached node blurs a focused
//     descendant, so every reconcile (`App.ui.util.syncChildren`)
//     leaves a node alone when it is already in place and moves it only when
//     its position really changed. The consequence sentence survives as the
//     Folders section's description (`kb-folders-cascade-hint`).
//   L6-D4: a panel's toggle to closed closes its rows' menus (through rows'
//     `closeGroupMenus`); a removed panel releases its rows' groups.
//
// Poll-vs-mutation split: `renderFolders(folders)` reconciles panel IDENTITY
// plus each panel's chips and meta lines; on a tick that adds or removes no
// panel it never touches file rows, and it is safe on every 5-second tick (it
// never recreates an existing panel). `renderAllItems(items)` is the items
// counterpart: it groups the items and hands each group to rows' `renderRows`
// (keyed rows patched in place, DD8-4: a refresh no longer closes an open menu
// or steals focus); it runs at mount, on an items-signature change, after a
// folder mutation, after a remove and after a time-zone change. Beyond those,
// `renderFolders` re-runs it on the last items when it adds or removes a panel,
// so an item held out for an unknown folder lands in its panel as soon as the
// folder appears (keyed rows, so it is a patch, not a rebuild).
//
// `create(ctx)`: ctx = {kb, root, container, initialStatus, openChunks,
// openSource, refreshStatus, refreshItems, isLive, isCurrent, setError,
// onItemsRendered}. The openers (called with `(item, opener)`, the opener
// being the row's menu trigger) and refreshers are the detail's lazy wrappers,
// called only from events and promises; `setError(text)` writes the editor
// header's error surface; `onItemsRendered(liveIds)` runs after every
// `renderAllItems` with the ids of every rendered row. It appends the Folders
// section to `root` at call time and returns `{foldersSection, renderFolders,
// renderAllItems, focusAfterInspect, destroy}`; the initial `renderFolders`
// runs inside `create`, the initial `renderAllItems` is the detail's call.
// All per-mount state lives in the `create` closure; the rows' state lives in
// the rows module, reached only through the handle `create` builds.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var _el = K.el;
  var _formatStamp = K.formatStamp;

  var syncChildren = App.ui.util.syncChildren;
  var setTextIfChanged = K.setTextIfChanged;
  var setAttrIfChanged = K.setAttrIfChanged;

  // "Skipped 2 folders, 1 file" from a walk's skip counters, naming only the
  // non-zero counts; '' when both are zero or the folder has not been walked.
  function skipText(dirs, entries) {
    var parts = [];
    if (dirs) parts.push(dirs + (dirs === 1 ? ' folder' : ' folders'));
    if (entries) parts.push(entries + (entries === 1 ? ' file' : ' files'));
    return parts.length ? 'Skipped ' + parts.join(', ') : '';
  }

  function create(ctx) {
    var kb = ctx.kb;
    var root = ctx.root;
    var initialStatus = ctx.initialStatus;
    function isCurrent() {
      if (ctx.isCurrent) return ctx.isCurrent();
      return ctx.isLive ? ctx.isLive() : true;
    }
    function setHeaderError(text) { if (ctx.setError) ctx.setError(text || ''); }
    function openChunksPanel(item, opener) { return ctx.openChunks(item, opener); }
    function openSourcePanel(item, opener) { return ctx.openSource(item, opener); }
    function refreshStatusNow() { return ctx.refreshStatus(); }
    function refreshItemsListNow() { return ctx.refreshItems(); }

    // ── Folders (AC-6/AC-7/AC-8/AC-9/AC-10, L6-D2/L6-D3) ────────────────
    //
    // HAT polish pass (2026-09-19): Folders is created BEFORE Status, so it
    // renders ABOVE it (the re-index pair is whole-knowledge-base, so it
    // lives beside the whole-knowledge-base status counts).
    //
    // L06a: Add folder is a library field (error through `field.setError`,
    // testid kept by `errorTestid`) and button; the cascade sentence is the
    // section's description.
    var folderInput = App.ui.textInput({
      id: 'kb-folder-path',
      placeholder: '/path/to/folder',
      testid: 'kb-folder-path-input',
      dataset: { field: 'path' }
    });
    var folderField = App.ui.field({
      label: 'Folder path',
      control: folderInput,
      errorTestid: 'kb-folder-add-error'
    });
    // AC-7: "Add folder" (was "Register folder").
    var addFolderBtn = App.ui.button({
      variant: 'secondary',
      label: 'Add folder',
      testid: 'kb-add-folder-btn',
      onClick: addFolder
    });

    var foldersListEl = _el('div', { className: 'kb-folders-list' });
    foldersListEl.setAttribute('data-testid', 'kb-folders-list');
    var foldersEmptyEl = App.ui.emptyState({ title: 'No folders registered.', titleTag: 'p' });
    foldersListEl.appendChild(foldersEmptyEl);

    var section = App.ui.section({
      title: 'Folders',
      description:
        'Removing a folder removes every file indexed from it, along with their chunks and search entries.',
      descriptionTestid: 'kb-folders-cascade-hint',
      layout: 'stack',
      children: [folderField.el, addFolderBtn, foldersListEl]
    });
    var foldersSection = section.el;
    root.appendChild(foldersSection);

    // Reconciliation state — keyed by folder id so an operator-expanded panel
    // is never torn down by a routine poll tick (see the header's
    // "Poll-vs-mutation split").
    var folderPanels = {}; // folder id -> panel (see buildFolderPanel)
    var currentFolders = (initialStatus && initialStatus.folders) || [];
    var individualEl = null; // the Individual files panel's <details> while attached
    var removedIds = {}; // item id -> true: removed here, never shown again
    var lastItems = null;
    var destroyed = false;

    // The file rows (knowledge-rows.js). Created BEFORE the first
    // `renderFolders` (panels build their groups through it); its callbacks
    // tolerate being called before `lastItems` and `folderPanels` are filled.
    var rows = window.App.studio.knowledgeRows.create({
      kb: kb,
      isCurrent: isCurrent,
      folders: function () { return currentFolders; },
      markRemoved: function (id) { removedIds[id] = true; },
      renderAll: function () { if (lastItems) renderAllItems(lastItems); },
      attachIndividual: function (detailsEl) {
        individualEl = detailsEl;
        syncPanelList(lastFolderOrder);
      },
      focusAddFolder: function () { folderInput.focus(); },
      setError: setHeaderError,
      refreshStatus: refreshStatusNow,
      refreshItems: refreshItemsListNow,
      openChunks: openChunksPanel,
      openSource: openSourcePanel
    });

    // After an inspect panel closes (ctx.onClose): back to the opener when it
    // is still on screen, else to the summary of the panel that holds the
    // item, else to the Add-folder input. "On screen" is checked by the focus
    // itself landing: inside a collapsed <details> an element can still report
    // client rects (its content is only skipped), but it cannot take focus.
    function focusAfterInspect(item, opener) {
      if (destroyed) return;
      if (opener && opener.isConnected && opener.getClientRects().length) {
        opener.focus();
        if (document.activeElement === opener) return;
      }
      var summary = null;
      if (item && item.parent_id) {
        var panel = folderPanels[item.parent_id];
        summary = panel ? panel.ctl.summary : null;
      } else {
        summary = rows.individualSummary();
      }
      if (summary && summary.isConnected) {
        summary.focus();
      } else {
        folderInput.focus();
      }
    }

    // ── Folder panel construction/reconciliation (L6-D2/L6-D3/L6-D4) ────

    // `revertFn` comes from App.ui.confirm's commit callback: on the
    // transport-failure path the armed row must roll back (title text
    // restored, `.confirm-delete` cleared) rather than being left stranded
    // reading "Confirm delete?" over a folder that still exists. A failure goes
    // to the editor header (DD6); the header error is cleared when a delete
    // starts.
    function deleteFolder(f, deleteBtn, revertFn) {
      setHeaderError('');
      deleteBtn.disabled = true;
      App.api.fetchJson(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items/' + encodeURIComponent(f.id),
        { method: 'DELETE' }
      ).then(function () {
        if (!isCurrent()) return;
        // The folder's panel is about to go with its trash button: focus goes
        // to the Add-folder input, the next natural place to act.
        folderInput.focus();
        // AC-11: an IMMEDIATE refresh on the success path — both the
        // status/folders AND the item list (a folder's children are file
        // items that just vanished with it) — never waiting on the
        // 5-second poll.
        refreshStatusNow();
        refreshItemsListNow();
      }).catch(function (err) {
        if (!isCurrent()) return;
        deleteBtn.disabled = false;
        if (typeof revertFn === 'function') revertFn();
        setHeaderError('Couldn’t remove the folder: ' + ((err && err.message) || err));
      });
    }

    function buildFolderPanel(f) {
      var statusChip = App.ui.chip({ label: 'status: ' + f.status, testid: 'kb-folder-status' });
      var watchChip = App.ui.chip({ label: 'watch: ' + f.watch, testid: 'kb-folder-watch' });

      // L6-D3 (amended): the delete is an action node of the disclosure, so it
      // is outside the summary's accessible name (the name is the path plus the
      // two chips) and a click on it never toggles the panel. The armed state's
      // visible signal is the swapped summary text; the two-step is stated once,
      // statically, in this button's own name.
      var deleteBtn = App.ui.button({
        variant: 'ghost',
        iconOnly: true,
        icon: 'trash',
        ariaLabel: 'Delete folder ' + f.path + ' (press twice to confirm)',
        testid: 'kb-folder-delete-btn',
        onClick: function () {
          App.ui.confirm(ctl.summary, function (el, revertFn) {
            deleteFolder(f, deleteBtn, revertFn);
          });
        }
      });
      deleteBtn.title = 'Delete folder';

      var group = null; // assigned below; the toggle handler closes over it
      var ctl = App.ui.disclosure({
        variant: 'bordered',
        summary: f.path,
        summaryTestid: 'kb-folder-summary',
        summaryTextTestid: 'kb-folder-path',
        testid: 'kb-folder-panel',
        dataset: { folderId: f.id },
        meta: [statusChip, watchChip],
        actions: [deleteBtn],
        // L6-D4: an open item menu inside this panel's body must not leak when
        // the panel itself collapses.
        onToggle: function (open) { if (!open) rows.closeGroupMenus(group); }
      });

      var metaEl = _el('div', { className: 'kb-folder-meta' });
      ctl.body.appendChild(metaEl);
      var filesEl = _el('div', { className: 'kb-folder-files' });
      ctl.body.appendChild(filesEl);
      group = rows.newGroup(filesEl, 'No files indexed from this folder yet.');

      return {
        ctl: ctl,
        detailsEl: ctl.el,
        statusChip: statusChip,
        watchChip: watchChip,
        metaEl: metaEl,
        lines: {},
        group: group
      };
    }

    // One keyed error line: built the first time its text is non-empty, patched
    // only when the text changes, dropped (and rebuilt later) when it empties.
    function dangerLine(st) {
      return { el: st.el, write: function (t) { st.set('danger', t); } };
    }
    function setLine(panel, key, text, make) {
      var ln = panel.lines[key];
      if (text === null || text === undefined || text === '') {
        delete panel.lines[key];
        return;
      }
      if (!ln) {
        ln = make();
        ln.text = null;
        panel.lines[key] = ln;
      }
      if (ln.text !== text) {
        ln.text = text;
        ln.write(text);
      }
    }

    // Runs on EVERY poll tick. It must never write the folder-path text: while
    // a delete confirm is armed, that node holds App.ui.confirm's "Confirm
    // delete?" placeholder, and the helper's revert restores from a value
    // captured at arm time — so this never calls `setSummary` (squawk 0088;
    // the library's `setSummary` is also a no-op while armed). Chips and the
    // meta lines are separate nodes, patched only when their text changed.
    // The folder's one small meta line (M31 F3 HAT): "Last checked {date},
    // {time}" from the folder's own `indexed_at` (it advances on every
    // completed walk), then " · Skipped 2 folders, 1 file" only when a skip
    // counter is non-zero (Flight 7 Leg 2, DD-7, AC-10: `null` means "not yet
    // walked" and renders nothing, never a fabricated "0"). The precise value
    // is the `title` and `data-indexed-at` of the date span. Built once per
    // panel; each part is patched only when it changed.
    function updateCheckedLine(panel, f) {
      var ln = panel.checked;
      if (!ln) {
        ln = panel.checked = {
          el: _el('div', { className: 'kb-folder-meta-line' }),
          whenEl: _el('span', { className: 'kb-folder-indexed-at' }),
          skipEl: _el('span', { className: 'kb-folder-skip-counts' })
        };
        ln.whenEl.setAttribute('data-testid', 'kb-folder-indexed-at');
        ln.skipEl.setAttribute('data-testid', 'kb-folder-skip-counts');
      }
      var when = f.indexed_at ? 'Last checked ' + _formatStamp(f.indexed_at) : '';
      var skip = (f.skipped_dirs != null && f.skipped_entries != null)
        ? skipText(f.skipped_dirs, f.skipped_entries) : '';
      if (when) {
        setTextIfChanged(ln.whenEl, when);
        if (ln.whenEl.title !== f.indexed_at) ln.whenEl.title = f.indexed_at;
        setAttrIfChanged(ln.whenEl, 'data-indexed-at', f.indexed_at);
      }
      if (skip) setTextIfChanged(ln.skipEl, (when ? ' · ' : '') + skip);
      syncChildren(ln.el, [when && ln.whenEl, skip && ln.skipEl].filter(Boolean));
      return when || skip ? ln.el : null;
    }

    function updateFolderMeta(panel, f) {
      setTextIfChanged(panel.statusChip, 'status: ' + f.status);
      setTextIfChanged(panel.watchChip, 'watch: ' + f.watch);
      var checkedEl = updateCheckedLine(panel, f);
      // AC-5 (carried, M24 F06 L01): the folder's own walk `error`.
      setLine(panel, 'error', f.error,
        function () {
          return dangerLine(App.ui.status({
            led: false, live: 'off', textTone: true, testid: 'kb-folder-status-error'
          }));
        });
      setLine(panel, 'werror', f.watch_error,
        function () {
          return dangerLine(App.ui.status({
            led: false, live: 'off', textTone: true, testid: 'kb-folder-watch-error'
          }));
        });
      var nodes = checkedEl ? [checkedEl] : [];
      ['error', 'werror'].forEach(function (k) {
        if (panel.lines[k]) nodes.push(panel.lines[k].el);
      });
      syncChildren(panel.metaEl, nodes);
    }

    // The folders list: the stable empty-state node, every folder panel in the
    // folders' order, then the trailing "Individual files" panel while it has
    // rows.
    function syncPanelList(orderedFolderIds) {
      var nodes = orderedFolderIds.map(function (id) { return folderPanels[id].detailsEl; });
      if (individualEl) nodes.push(individualEl);
      syncChildren(foldersListEl, [foldersEmptyEl].concat(nodes));
    }

    var lastFolderOrder = [];

    // Reconciles panel identity ONLY — never touches a panel's file-row
    // content (that's `renderAllItems`'s job). Safe to call on every poll tick:
    // an existing panel is never recreated or re-appended, so its `open` state,
    // focus and nested DOM survive.
    function renderFolders(folders) {
      currentFolders = folders;
      foldersEmptyEl.hidden = folders.length > 0;

      var seenIds = {};
      var order = [];
      var identityChanged = false;
      folders.forEach(function (f) {
        seenIds[f.id] = true;
        order.push(f.id);
        var panel = folderPanels[f.id];
        if (!panel) {
          panel = buildFolderPanel(f);
          folderPanels[f.id] = panel;
          identityChanged = true;
        }
        updateFolderMeta(panel, f);
      });

      Object.keys(folderPanels).forEach(function (id) {
        if (!seenIds[id]) {
          var stale = folderPanels[id];
          // A removed armed summary's revert timer is harmless: App.ui.confirm
          // reverts a detached node (it only announces "not confirmed").
          rows.releaseGroup(stale.group);
          stale.ctl.destroy();
          if (stale.detailsEl.parentNode) {
            stale.detailsEl.parentNode.removeChild(stale.detailsEl);
          }
          delete folderPanels[id];
          identityChanged = true;
        }
      });
      lastFolderOrder = order;
      syncPanelList(order);
      // A new or removed panel changes where held-out items belong (see the
      // header); a tick that changes no identity never touches file rows.
      if (identityChanged && lastItems) renderAllItems(lastItems);
    }

    // ── Items reconciliation (L1-D2/FIX1 carried) — only ever called at
    // mount, on an actual items-signature change, or right after a folder
    // mutation, and by `renderFolders` when a panel is added or removed (header).
    // A tombstoned id (removed here) is filtered everywhere; an item whose
    // folder is unknown is held out (see the header). `onItemsRendered` gets
    // the ids of every rendered row, so an open inspect panel whose item is
    // gone can close.
    function renderAllItems(nextItems) {
      if (destroyed) return;
      lastItems = nextItems;
      // id -> folder: the folder OBJECT is what the rows need, to render each
      // file's path relative to its own root.
      var foldersById = {};
      currentFolders.forEach(function (f) { foldersById[f.id] = f; });

      var byFolder = {};
      var individual = [];
      var liveIds = {};
      nextItems
        .filter(function (it) { return it.type === 'file' && !removedIds[it.id]; })
        .forEach(function (item) {
          if (!item.parent_id) {
            individual.push(item);
            liveIds[item.id] = true;
          } else if (foldersById[item.parent_id]) {
            (byFolder[item.parent_id] = byFolder[item.parent_id] || []).push(item);
            liveIds[item.id] = true;
          }
          // else: held out until its folder appears or the item vanishes.
        });

      Object.keys(folderPanels).forEach(function (id) {
        rows.renderRows(folderPanels[id].group, byFolder[id] || [], {
          individual: false,
          folderPath: foldersById[id] && foldersById[id].path
        });
      });
      rows.renderIndividualFiles(individual);
      if (ctx.onItemsRendered) ctx.onItemsRendered(liveIds);
    }
    renderFolders(currentFolders);

    // The shown dates and times follow the operator zone: a zone change
    // re-patches the meta lines and rows in place (only changed text is
    // written). The owner element drops the listener if the section leaves
    // the page without a destroy.
    var offTimeChange = App.time.onChange(function () {
      if (destroyed) return;
      renderFolders(currentFolders);
      if (lastItems) renderAllItems(lastItems);
    }, foldersSection);

    function addFolder() {
      folderField.setError(null);
      setHeaderError('');
      var path = folderInput.value.trim();
      if (!path) {
        folderField.setError('Folder path is required.');
        return;
      }
      addFolderBtn.disabled = true;
      // DD-10: the route's own `detail` message is shown verbatim (422
      // non-existent/not-a-directory, filesystem root, data-directory overlap,
      // 409 overlapping folder, 422 body validation all carry prose).
      App.api.fetchJson('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'folder', path_or_url: path })
      }).then(function () {
        if (!isCurrent()) return;
        folderInput.value = '';
        addFolderBtn.disabled = false;
        refreshStatusNow();
        // kb-studio-round-trip remediation FIX 1: registration changes the
        // status counts, so the poll-invalidation path in `studio.js`
        // (comparing `/status`'s counts against what the items list was
        // last rendered against) refreshes the list on its own within one
        // poll interval — no separate callback needed.
      }).catch(function (err) {
        if (!isCurrent()) return;
        addFolderBtn.disabled = false;
        folderField.setError((err && err.message) || String(err));
      });
    }

    return {
      foldersSection: foldersSection,
      renderFolders: renderFolders,
      renderAllItems: renderAllItems,
      focusAfterInspect: focusAfterInspect,
      // The mount is dead: release every panel control and every row's menu.
      destroy: function () {
        destroyed = true;
        offTimeChange();
        Object.keys(folderPanels).forEach(function (id) {
          rows.releaseGroup(folderPanels[id].group);
          folderPanels[id].ctl.destroy();
        });
        rows.destroy();
      }
    };
  }

  window.App.studio.knowledgeFolders = { create: create };
})();
