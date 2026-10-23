// App.studio.knowledgeFolders — the Knowledge detail's Folders section: Add
// folder, the folder panels, the "Other items" panel, the file rows and their
// overflow menu, and the keyed reconcile (Mission 24 Flight 6 Leg 6; split out
// of knowledge-section.js in Mission 31 Flight 3 Leg 02; on the library in
// Leg 06a).
//
// Design notes carried over from the former module header:
//   L6-D2: folders are `App.ui.disclosure` panels (`buildFolderPanel`)
//     containing their own files. Items are grouped by `parent_id` against the
//     CURRENT folder set (`renderAllItems`); anything whose `parent_id` is
//     unset OR points at a folder that no longer exists lands in a trailing
//     "Other items" panel (`renderOtherItems`), never nested under a folder
//     its path merely happens to contain (DD-9's standalone badge is exactly
//     for that case, and only applies inside "Other items"). A file row INSIDE
//     a panel renders its path relative to that folder's root
//     (`_relativeItemPath`); "Other items" rows keep ABSOLUTE paths.
//   L6-D3: removing a folder is an immediate, irreversible, server-side
//     cascading DELETE, so the trash icon button in the folder's summary keeps
//     the two-step `App.ui.confirm` (the summary is the state element, the
//     disclosure's text its `[data-confirm-title]`). Squawk 0088: the armed
//     state is only safe because nothing RECREATES an armed summary and
//     nothing else writes its text (`updateFolderMeta` never calls
//     `setSummary`; the library's `setSummary` is also a no-op while armed).
//     MOVING an attached node is a separate hazard (M31 F3 L06a): `appendChild`
//     /`insertBefore` of an attached node blurs a focused descendant, so every
//     reconcile below (`syncChildren`) leaves a node alone when it is already
//     in place and moves it only when its position really changed. The
//     consequence sentence survives as the Folders section's description
//     (`kb-folders-cascade-hint`).
//   L6-D4: the per-row overflow menu is an `App.ui.menu` (M31 F3 L06b) in an
//     area-owned `span.kb-item-menu-slot` on file rows. A panel's toggle to
//     closed closes its rows' menus; a removed row destroys its menu.
//
// Poll-vs-mutation split: `renderFolders(folders)` reconciles panel IDENTITY
// plus each panel's chips and meta lines and is safe on every 5-second tick
// (it never recreates an existing panel and never touches file rows).
// `renderAllItems(items)` is the items counterpart: file rows are keyed by item
// id and patched in place (DD8-4: a refresh no longer closes an open menu or
// steals focus); it runs at mount, on an items-signature change, and after a
// folder mutation. The two never call each other.
//
// `create(ctx)`: ctx = {kb, root, container, initialStatus, openChunks,
// openSource, refreshStatus, refreshItems, isLive, isCurrent, setError}. The
// openers and refreshers are the detail's lazy wrappers, called only from
// events and promises; `setError(text)` writes the editor header's error
// surface. It appends the Folders section to `root` at call time and returns
// `{foldersSection, renderFolders, renderAllItems, destroy}`; the initial
// `renderFolders` runs inside `create`, the initial `renderAllItems` is the
// detail's call. All per-mount state lives in the `create` closure.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var _el = K.el;
  var _errorMessageFromResponse = K.errorMessageFromResponse;
  var _containingFolder = K.containingFolder;
  var _relativeItemPath = K.relativeItemPath;

  // Makes `parent.children` (from `offset`) exactly `nodes`, in order, touching
  // only what is wrong: a child not in `nodes` is removed first, then a node is
  // inserted only when it is not already at its position. A node already in
  // place is never re-appended (re-appending an attached node blurs a focused
  // descendant).
  function syncChildren(parent, nodes, offset) {
    var i;
    for (i = parent.children.length - 1; i >= offset; i--) {
      if (nodes.indexOf(parent.children[i]) === -1) parent.removeChild(parent.children[i]);
    }
    for (i = 0; i < nodes.length; i++) {
      var at = parent.children[offset + i];
      if (at !== nodes[i]) parent.insertBefore(nodes[i], at || null);
    }
  }

  function setTextIfChanged(node, text) {
    if (node.textContent !== text) node.textContent = text;
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
    function openChunksPanel(item) { return ctx.openChunks(item); }
    function openSourcePanel(item) { return ctx.openSource(item); }
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
      children: [folderField.el, addFolderBtn, foldersListEl]
    });
    var foldersSection = section.el;
    root.appendChild(foldersSection);

    // Reconciliation state — keyed by folder id so an operator-expanded panel
    // is never torn down by a routine poll tick (see the header's
    // "Poll-vs-mutation split").
    var folderPanels = {}; // folder id -> panel (see buildFolderPanel)
    var currentFolders = (initialStatus && initialStatus.folders) || [];
    var otherItemsPanel = null; // built lazily, only while standalone items exist
    var otherAttached = false;
    var destroyed = false;

    // ── Row groups. A group is the files container of one panel: a stable
    // empty-state node first, then one keyed row per item. `renderRows`
    // adds rows for new ids, removes rows for gone ids (closing their menu
    // first) and patches kept rows only where text changed.
    function newGroup(filesEl, emptyTitle) {
      var emptyEl = emptyTitle
        ? App.ui.emptyState({ title: emptyTitle, titleTag: 'p' })
        : null;
      if (emptyEl) filesEl.appendChild(emptyEl);
      return { filesEl: filesEl, emptyEl: emptyEl, rows: {} };
    }

    // A removed row's menu is destroyed (no document listener survives it); a
    // collapsing panel only closes its rows' menus, without returning focus to
    // a trigger that is about to be hidden.
    function releaseRow(entry) {
      entry.menu.destroy();
    }

    function closeGroupMenus(group) {
      if (!group) return;
      Object.keys(group.rows).forEach(function (id) { group.rows[id].menu.close(false); });
    }

    function releaseGroup(group) {
      Object.keys(group.rows).forEach(function (id) { releaseRow(group.rows[id]); });
      group.rows = {};
    }

    // Shared row builder for a file item, used both inside a folder
    // panel's body and inside the trailing "Other items" panel.
    // `opts.standalone` gates the DD-9 badge lookup — only meaningful for
    // items with no real parent, which is exactly the "Other items" set.
    // `opts.folderPath` is the OWNING folder's path and is set only for
    // the first case: inside a panel the path renders relative to that
    // root (see `_relativeItemPath`). The "Other items" panel passes none
    // — those items are parentless by definition, so there is no root to
    // relativize against and the absolute path is the only honest display.
    // Either way the full absolute path stays one hover away in `title`.
    function buildFileItemRow(item) {
      var entry = { item: item };
      var row = _el('div', { className: 'kb-item-row' });
      row.setAttribute('data-testid', 'kb-item-row');
      row.setAttribute('data-item-id', item.id);
      entry.row = row;
      entry.pathEl = _el('span', { className: 'kb-item-path' });
      entry.statusEl = _el('span', { className: 'kb-item-status' });
      entry.statusEl.setAttribute('data-testid', 'kb-item-status');
      entry.errorLine = null; // App.ui.status, only while failed with an error
      entry.freshEl = null;
      entry.badge = null;
      // The menu sits in an area-owned slot span that places it at the row's
      // end; the library menu inside it owns its own look and behaviour.
      entry.menu = App.ui.menu({
        trigger: {
          iconOnly: true, icon: 'more', ariaLabel: 'Item actions',
          variant: 'ghost', size: 'sm', testid: 'kb-item-menu-btn'
        },
        items: [
          { label: 'View chunks', testid: 'kb-item-chunks-btn',
            onSelect: function () { openChunksPanel(entry.item); } },
          { label: 'View source', testid: 'kb-item-source-btn',
            onSelect: function () { openSourcePanel(entry.item); } }
        ],
        align: 'end',
        testid: 'kb-item-menu'
      });
      entry.menuSlot = _el('span', { className: 'kb-item-menu-slot' });
      entry.menuSlot.appendChild(entry.menu.el);
      return entry;
    }

    function patchFileItemRow(entry, item, opts) {
      entry.item = item;
      var shown = (opts.folderPath && _relativeItemPath(item.path_or_url, opts.folderPath)) ||
        item.path_or_url;
      setTextIfChanged(entry.pathEl, shown);
      if (entry.pathEl.title !== item.path_or_url) entry.pathEl.title = item.path_or_url;
      setTextIfChanged(entry.statusEl, item.status);

      if (item.status === 'failed' && item.error) {
        if (!entry.errorLine) {
          entry.errorLine = App.ui.status({
            led: false, live: 'off', textTone: true, testid: 'kb-item-error'
          });
          entry.errorText = null;
        }
        if (entry.errorText !== item.error) {
          entry.errorText = item.error;
          entry.errorLine.set('danger', item.error);
        }
      } else {
        entry.errorLine = null;
      }

      // Flight 7 Leg 2 (DD-6, AC-1): the freshness signal — derived from
      // `indexed_at`, which only advances when THIS item actually re-indexes.
      // `content_hash` rides along as the hover title. Rendered only when the
      // item has ever indexed (a never-indexed item gets no fabricated stamp).
      if (item.indexed_at) {
        if (!entry.freshEl) {
          entry.freshEl = _el('span', { className: 'kb-item-indexed-at' });
          entry.freshEl.setAttribute('data-testid', 'kb-item-indexed-at');
        }
        setTextIfChanged(entry.freshEl, 'Indexed: ' + item.indexed_at);
        var hashTitle = item.content_hash ? 'content hash: ' + item.content_hash : '';
        if (entry.freshEl.title !== hashTitle) entry.freshEl.title = hashTitle;
      } else {
        entry.freshEl = null;
      }

      var standaloneFolder = opts.standalone ? _containingFolder(item, currentFolders) : null;
      if (standaloneFolder) {
        // DD-9: a standalone file whose path lies inside a registered folder is
        // badged rather than silently shown as a look-alike duplicate.
        var label = 'standalone (in ' + standaloneFolder.path + ')';
        if (!entry.badge) {
          entry.badge = App.ui.chip({
            tone: 'warning', label: label, testid: 'kb-item-standalone-badge'
          });
        } else {
          setTextIfChanged(entry.badge, label);
        }
      } else {
        entry.badge = null;
      }

      syncChildren(entry.row, [entry.pathEl, entry.statusEl,
        entry.errorLine && entry.errorLine.el, entry.freshEl, entry.badge,
        entry.menuSlot].filter(Boolean), 0);
    }

    function renderRows(group, items, opts) {
      var wanted = {};
      items.forEach(function (it) { wanted[it.id] = true; });
      Object.keys(group.rows).forEach(function (id) {
        if (!wanted[id]) {
          var gone = group.rows[id];
          releaseRow(gone);
          if (gone.row.parentNode) gone.row.parentNode.removeChild(gone.row);
          delete group.rows[id];
        }
      });
      var nodes = [];
      items.forEach(function (it) {
        var entry = group.rows[it.id];
        if (!entry) {
          entry = buildFileItemRow(it);
          group.rows[it.id] = entry;
        }
        patchFileItemRow(entry, it, opts);
        nodes.push(entry.row);
      });
      if (group.emptyEl) {
        group.emptyEl.hidden = nodes.length > 0;
        syncChildren(group.filesEl, [group.emptyEl].concat(nodes), 0);
      } else {
        syncChildren(group.filesEl, nodes, 0);
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
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items/' + encodeURIComponent(f.id),
        { method: 'DELETE' }
      ).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            throw new Error(_errorMessageFromResponse(body) || 'Remove failed');
          });
        }
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
        onToggle: function (open) { if (!open) closeGroupMenus(group); }
      });

      var metaEl = _el('div', { className: 'kb-folder-meta' });
      ctl.body.appendChild(metaEl);
      var filesEl = _el('div', { className: 'kb-folder-files' });
      ctl.body.appendChild(filesEl);
      group = newGroup(filesEl, 'No files indexed from this folder yet.');

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

    // One keyed meta line: built the first time its text is non-empty, patched
    // only when the text changes, dropped (and rebuilt later) when it empties.
    function plainLine(className, testid) {
      var el = _el('div', { className: className });
      if (testid) el.setAttribute('data-testid', testid);
      return { el: el, write: function (t) { el.textContent = t; } };
    }
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
    function updateFolderMeta(panel, f) {
      setTextIfChanged(panel.statusChip, 'status: ' + f.status);
      setTextIfChanged(panel.watchChip, 'watch: ' + f.watch);
      setLine(panel, 'indexed', f.indexed_at ? 'Indexed: ' + f.indexed_at : null,
        function () { return plainLine('kb-folder-indexed-at'); });
      // Flight 7 Leg 2 (DD-7, AC-10): the last completed walk's skip counters.
      // `null` means "not yet walked", which renders nothing (not a fabricated
      // "0").
      setLine(panel, 'skip',
        f.skipped_dirs != null && f.skipped_entries != null
          ? 'Skipped: ' + f.skipped_dirs + ' dirs, ' + f.skipped_entries + ' entries' : null,
        function () { return plainLine('kb-folder-skip-counts', 'kb-folder-skip-counts'); });
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
      var nodes = [];
      ['indexed', 'skip', 'error', 'werror'].forEach(function (k) {
        if (panel.lines[k]) nodes.push(panel.lines[k].el);
      });
      syncChildren(panel.metaEl, nodes, 0);
    }

    // The folders list: the stable empty-state node, every folder panel in the
    // folders' order, then the trailing "Other items" panel while it has rows.
    function syncPanelList(orderedFolderIds) {
      var nodes = orderedFolderIds.map(function (id) { return folderPanels[id].detailsEl; });
      if (otherAttached && otherItemsPanel) nodes.push(otherItemsPanel.detailsEl);
      syncChildren(foldersListEl, [foldersEmptyEl].concat(nodes), 0);
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
      folders.forEach(function (f) {
        seenIds[f.id] = true;
        order.push(f.id);
        var panel = folderPanels[f.id];
        if (!panel) {
          panel = buildFolderPanel(f);
          folderPanels[f.id] = panel;
        }
        updateFolderMeta(panel, f);
      });

      Object.keys(folderPanels).forEach(function (id) {
        if (!seenIds[id]) {
          var stale = folderPanels[id];
          // A removed armed summary's revert timer is harmless: App.ui.confirm
          // reverts a detached node (it only announces "not confirmed").
          releaseGroup(stale.group);
          stale.ctl.destroy();
          if (stale.detailsEl.parentNode) {
            stale.detailsEl.parentNode.removeChild(stale.detailsEl);
          }
          delete folderPanels[id];
        }
      });
      lastFolderOrder = order;
      syncPanelList(order);
    }
    renderFolders(currentFolders);

    // ── "Other items" trailing panel (L6-D2, chosen option (a)) ─────────
    // Items with `parent_id` unset, OR pointing at a folder that no
    // longer exists, render here — never nested under a folder whose path
    // merely contains them (that would render a FALSE parentage, exactly
    // what DD-9's standalone badge exists to prevent).

    function buildOtherItemsPanel() {
      var group = null;
      var ctl = App.ui.disclosure({
        variant: 'bordered',
        summary: 'Other items',
        testid: 'kb-other-items-panel',
        onToggle: function (open) { if (!open) closeGroupMenus(group); }
      });
      var filesEl = _el('div', { className: 'kb-other-items-files' });
      ctl.body.appendChild(filesEl);
      group = newGroup(filesEl, null);
      return { ctl: ctl, detailsEl: ctl.el, group: group };
    }

    function renderOtherItems(otherItems) {
      if (otherItems.length === 0) {
        if (otherItemsPanel) {
          // Kept for reuse, but detached with its rows and menus released.
          releaseGroup(otherItemsPanel.group);
          otherItemsPanel.group.filesEl.textContent = '';
        }
        if (otherAttached) {
          otherAttached = false;
          syncPanelList(lastFolderOrder);
        }
        return;
      }
      if (!otherItemsPanel) otherItemsPanel = buildOtherItemsPanel();
      if (!otherAttached) {
        otherAttached = true;
        syncPanelList(lastFolderOrder);
      }
      // Never armed, so the armed no-op of `setSummary` does not apply.
      otherItemsPanel.ctl.setSummary('Other items (' + otherItems.length + ')');
      renderRows(otherItemsPanel.group, otherItems, { standalone: true });
    }

    // ── Items reconciliation (L1-D2/FIX1 carried) — only ever called at
    // mount, on an actual items-signature change, or right after a folder
    // mutation. Never called from `renderFolders`.
    function renderAllItems(nextItems) {
      if (destroyed) return;
      // id -> folder: the folder OBJECT is what the rows need, to render each
      // file's path relative to its own root.
      var foldersById = {};
      currentFolders.forEach(function (f) { foldersById[f.id] = f; });

      var byFolder = {};
      var other = [];
      nextItems
        .filter(function (it) { return it.type === 'file'; })
        .forEach(function (item) {
          if (item.parent_id && foldersById[item.parent_id]) {
            (byFolder[item.parent_id] = byFolder[item.parent_id] || []).push(item);
          } else {
            other.push(item);
          }
        });

      Object.keys(folderPanels).forEach(function (id) {
        renderRows(folderPanels[id].group, byFolder[id] || [], {
          standalone: false,
          folderPath: foldersById[id] && foldersById[id].path
        });
      });
      renderOtherItems(other);
    }

    function addFolder() {
      folderField.setError(null);
      setHeaderError('');
      var path = folderInput.value.trim();
      if (!path) {
        folderField.setError('Folder path is required.');
        return;
      }
      addFolderBtn.disabled = true;
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'folder', path_or_url: path })
      }).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            // DD-10: render the route's own `detail` message verbatim —
            // 422 non-existent/not-a-directory, 422 filesystem root, 422
            // data-directory overlap, 409 overlapping folder, 422 body
            // validation all carry a prose `detail`.
            throw new Error(_errorMessageFromResponse(body) || 'Folder registration failed');
          });
        }
        return r.json();
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
      // The mount is dead: release every panel control and every row's menu.
      destroy: function () {
        destroyed = true;
        Object.keys(folderPanels).forEach(function (id) {
          releaseGroup(folderPanels[id].group);
          folderPanels[id].ctl.destroy();
        });
        if (otherItemsPanel) {
          releaseGroup(otherItemsPanel.group);
          otherItemsPanel.ctl.destroy();
        }
      }
    };
  }

  window.App.studio.knowledgeFolders = { create: create };
})();
