// App.studio.knowledgeFolders — the Knowledge detail's Folders section: Add
// folder, the folder panels, the "Individual files" panel, the file rows with
// their remove button and overflow menu, and the keyed reconcile (Mission 24
// Flight 6 Leg 6; split out of knowledge-section.js in Mission 31 Flight 3 Leg
// 02; on the library in Leg 06a; "Other items" renamed and given a remove at
// the M31 F3 HAT).
//
// Design notes carried over from the former module header:
//   L6-D2 (amended at the M31 F3 HAT): folders are `App.ui.disclosure` panels
//     (`buildFolderPanel`) containing their own files. Items are grouped by
//     `parent_id` against the CURRENT folder set (`renderAllItems`): an item
//     with no `parent_id` lands in the trailing "Individual files" panel
//     (`renderIndividualFiles`), never nested under a folder its path merely
//     happens to contain (DD-9's standalone chip is exactly for that case, and
//     only applies there). An item whose `parent_id` names a folder the client
//     does not know is HELD OUT of every panel until its folder appears or the
//     item vanishes: `kb_items.parent_id` is ON DELETE CASCADE, so such an item
//     is client lag (the items and status responses crossing), never real
//     state, and showing it among the individual files would be false (it was
//     the former "folder that no longer exists" clause). A file row INSIDE a
//     folder panel renders its path relative to that folder's root
//     (`_relativeItemPath`); an "Individual files" row shows the basename,
//     with the full path on a small ellipsised line under it.
//   Individual files (M31 F3 HAT): files added one at a time through the API.
//     The panel's description says so and that they are not watched (only
//     "Re-index all files" re-reads them). No summary chips: watch would always
//     be off, and a walk status does not apply. Each row has a trash button,
//     armed on itself by `App.ui.confirm`, that DELETEs the item. A removed id
//     goes into `removedIds`, a tombstone set for the mount's lifetime that
//     `renderAllItems` filters, so a stale /items response can never bring the
//     row back. Walked files (with a `parent_id`) get no remove: the next walk
//     would recreate them.
//   Status and stamp (M31 F3 HAT, every panel): an indexed item with an
//     `indexed_at` shows only "Indexed {date}, {time}"; an indexed item with
//     none shows "indexed"; a pending, indexing or failed item shows its status
//     word, plus "Last indexed {date}, {time}" when it has indexed before.
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
//     area-owned `span.kb-item-menu-slot` on file rows (after the remove
//     button, on individual rows). A panel's toggle to closed closes its rows'
//     menus; a removed row destroys its menu. Nothing ever writes the remove
//     button, so a poll can't disturb its armed state.
//
// Poll-vs-mutation split: `renderFolders(folders)` reconciles panel IDENTITY
// plus each panel's chips and meta lines and is safe on every 5-second tick
// (it never recreates an existing panel and never touches file rows).
// `renderAllItems(items)` is the items counterpart: file rows are keyed by item
// id and patched in place (DD8-4: a refresh no longer closes an open menu or
// steals focus); it runs at mount, on an items-signature change, and after a
// folder mutation. The two never call each other.
//
// One exception: when `renderFolders` adds or removes a panel, it re-runs
// `renderAllItems` on the last items, so an item held out for an unknown
// folder lands in its panel as soon as the folder appears (keyed rows, so it
// is a patch, not a rebuild).
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
// runs inside `create`, the initial `renderAllItems` is the detail's call. All
// per-mount state lives in the `create` closure.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var _el = K.el;
  var _errorMessageFromResponse = K.errorMessageFromResponse;
  var _containingFolder = K.containingFolder;
  var _relativeItemPath = K.relativeItemPath;
  var _formatStamp = K.formatStamp;
  var _baseName = K.baseName;

  var INDIVIDUAL_HINT = 'Added one at a time through the API. These files aren’t watched ' +
    'for changes; use Re-index all files to pick up edits.';

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

  function setAttrIfChanged(node, name, value) {
    if (node.getAttribute(name) !== value) node.setAttribute(name, value);
  }

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
      children: [folderField.el, addFolderBtn, foldersListEl]
    });
    var foldersSection = section.el;
    root.appendChild(foldersSection);

    // Reconciliation state — keyed by folder id so an operator-expanded panel
    // is never torn down by a routine poll tick (see the header's
    // "Poll-vs-mutation split").
    var folderPanels = {}; // folder id -> panel (see buildFolderPanel)
    var currentFolders = (initialStatus && initialStatus.folders) || [];
    var individualPanel = null; // built lazily, only while individual files exist
    var individualAttached = false;
    var removedIds = {}; // item id -> true: removed here, never shown again
    var destroyed = false;

    // ── Row groups. A group is the files container of one panel: a stable
    // empty-state node first, then one keyed row per item. `renderRows`
    // adds rows for new ids, removes rows for gone ids (closing their menu
    // first), patches kept rows only where text changed, and keeps `order`
    // (the rendered ids, in order) for the focus after a remove.
    function newGroup(filesEl, emptyTitle, individual) {
      var emptyEl = emptyTitle
        ? App.ui.emptyState({ title: emptyTitle, titleTag: 'p' })
        : null;
      if (emptyEl) filesEl.appendChild(emptyEl);
      return { filesEl: filesEl, emptyEl: emptyEl, rows: {}, order: [], individual: !!individual };
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
      group.order = [];
    }

    // Shared row builder for a file item, used both inside a folder panel's
    // body and inside the trailing "Individual files" panel. `opts.individual`
    // picks the individual shape: the basename and a full-path line in
    // `span.kb-item-file`, the DD-9 chip lookup (only meaningful for items with
    // no real parent), and the remove button. `opts.folderPath` is the OWNING
    // folder's path and is set only for the folder case: inside a folder panel
    // the path renders relative to that root (see `_relativeItemPath`).
    // Either way the full absolute path stays one hover away in `title`.
    // Eligibility for remove is decided here, once: individual and parentless.
    function buildFileItemRow(item, opts) {
      var entry = { item: item, individual: !!opts.individual };
      var row = _el('div', { className: 'kb-item-row' });
      row.setAttribute('data-testid', 'kb-item-row');
      row.setAttribute('data-item-id', item.id);
      entry.row = row;
      entry.pathEl = _el('span', { className: 'kb-item-path' });
      if (entry.individual) {
        entry.fileEl = _el('span', { className: 'kb-item-file' });
        entry.fullPathEl = _el('span', { className: 'kb-item-full-path' });
        entry.fullPathEl.setAttribute('data-testid', 'kb-item-full-path');
        entry.fileEl.appendChild(entry.pathEl);
        entry.fileEl.appendChild(entry.fullPathEl);
      }
      entry.statusEl = _el('span', { className: 'kb-item-status' });
      entry.statusEl.setAttribute('data-testid', 'kb-item-status');
      entry.errorLine = null; // App.ui.status, only while failed with an error
      entry.freshEl = null;
      entry.badge = null;
      // The menu sits in an area-owned slot span that places it at the row's
      // end; the library menu inside it owns its own look and behaviour. The
      // opener handed to the panels is the menu's trigger, where focus goes
      // back when a panel closes.
      entry.menu = App.ui.menu({
        trigger: {
          iconOnly: true, icon: 'more', ariaLabel: 'Item actions',
          variant: 'ghost', size: 'sm', testid: 'kb-item-menu-btn'
        },
        items: [
          { label: 'View chunks', testid: 'kb-item-chunks-btn',
            onSelect: function () { openChunksPanel(entry.item, entry.menu.trigger); } },
          { label: 'View source', testid: 'kb-item-source-btn',
            onSelect: function () { openSourcePanel(entry.item, entry.menu.trigger); } }
        ],
        align: 'end',
        testid: 'kb-item-menu'
      });
      entry.menuSlot = _el('span', { className: 'kb-item-menu-slot' });
      entry.removeBtn = null;
      if (entry.individual && !item.parent_id) {
        // Armed on the button itself (it has no `[data-confirm-title]`, so
        // only the library's armed look changes); the two-step is stated in
        // its name. Nothing writes this button after it is built.
        entry.removeBtn = App.ui.button({
          variant: 'ghost',
          size: 'sm',
          iconOnly: true,
          icon: 'trash',
          ariaLabel: 'Remove file ' + item.path_or_url + ' (press twice to confirm)',
          testid: 'kb-item-remove-btn',
          onClick: function () {
            App.ui.confirm(entry.removeBtn, function (el, revertFn) {
              removeFile(entry, revertFn);
            }, {
              confirmLabel: 'Confirm remove?',
              announceName: 'Remove file ' + _baseName(entry.item.path_or_url)
            });
          }
        });
        entry.removeBtn.title = 'Remove file';
        entry.menuSlot.appendChild(entry.removeBtn);
      }
      entry.menuSlot.appendChild(entry.menu.el);
      return entry;
    }

    function patchFileItemRow(entry, item, opts) {
      entry.item = item;
      var shown;
      if (entry.individual) {
        shown = _baseName(item.path_or_url) || item.path_or_url;
        setTextIfChanged(entry.fullPathEl, item.path_or_url);
        if (entry.fullPathEl.title !== item.path_or_url) entry.fullPathEl.title = item.path_or_url;
      } else {
        shown = (opts.folderPath && _relativeItemPath(item.path_or_url, opts.folderPath)) ||
          item.path_or_url;
      }
      setTextIfChanged(entry.pathEl, shown);
      if (entry.pathEl.title !== item.path_or_url) entry.pathEl.title = item.path_or_url;

      // The status word is left out only when the stamp already says
      // "Indexed …"; every other state shows it (M31 F3 HAT).
      var indexedWithStamp = item.status === 'indexed' && !!item.indexed_at;
      if (!indexedWithStamp) setTextIfChanged(entry.statusEl, item.status);

      if (item.status === 'failed' && item.error) {
        if (!entry.errorLine) {
          entry.errorLine = App.ui.status({
            led: false, live: 'off', textTone: true, testid: 'kb-item-error'
          });
          // Its own line under the row (an area-owned placement class).
          entry.errorLine.el.classList.add('kb-item-error-line');
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
      // Rendered only when the item has ever indexed (a never-indexed item
      // gets no fabricated stamp). The visible text is minute-grained
      // ("Indexed Oct 23, 2026, 8:57 AM", M31 F3 HAT), "Last indexed …" while
      // the item is not (or no longer) indexed; the precise value is
      // `data-indexed-at` and leads the hover title, with `content_hash`
      // after it. Each is written only when it changed (no row rebuild).
      if (item.indexed_at) {
        if (!entry.freshEl) {
          entry.freshEl = _el('span', { className: 'kb-item-indexed-at' });
          entry.freshEl.setAttribute('data-testid', 'kb-item-indexed-at');
        }
        setTextIfChanged(entry.freshEl, (indexedWithStamp ? 'Indexed ' : 'Last indexed ') +
          _formatStamp(item.indexed_at));
        setAttrIfChanged(entry.freshEl, 'data-indexed-at', item.indexed_at);
        var freshTitle = item.indexed_at +
          (item.content_hash ? '\ncontent hash: ' + item.content_hash : '');
        if (entry.freshEl.title !== freshTitle) entry.freshEl.title = freshTitle;
      } else {
        entry.freshEl = null;
      }

      var standaloneFolder = entry.individual ? _containingFolder(item, currentFolders) : null;
      if (standaloneFolder) {
        // DD-9: an individual file whose path lies inside a registered folder is
        // flagged rather than silently shown as a look-alike duplicate.
        var label = 'Also in folder ' + (_baseName(standaloneFolder.path) || standaloneFolder.path);
        if (!entry.badge) {
          entry.badge = App.ui.chip({
            tone: 'warning', label: label, title: standaloneFolder.path,
            testid: 'kb-item-standalone-badge'
          });
          // Area placement: the chip may wrap inside the row, never overflow it.
          entry.badge.classList.add('kb-item-badge');
        } else {
          setTextIfChanged(entry.badge, label);
          setAttrIfChanged(entry.badge, 'title', standaloneFolder.path);
        }
      } else {
        entry.badge = null;
      }

      // One compact line: the name (or, on an individual row, the name over
      // its full path), the status word when shown, the indexed time, the
      // chip, then the slot (remove, menu) at the row's end; a failed item's
      // error wraps to its own line below.
      syncChildren(entry.row, [entry.fileEl || entry.pathEl,
        !indexedWithStamp && entry.statusEl, entry.freshEl, entry.badge,
        entry.menuSlot, entry.errorLine && entry.errorLine.el].filter(Boolean), 0);
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
      group.order = [];
      items.forEach(function (it) {
        var entry = group.rows[it.id];
        if (!entry) {
          entry = buildFileItemRow(it, opts);
          group.rows[it.id] = entry;
        }
        patchFileItemRow(entry, it, opts);
        nodes.push(entry.row);
        group.order.push(it.id);
      });
      if (group.emptyEl) {
        group.emptyEl.hidden = nodes.length > 0;
        syncChildren(group.filesEl, [group.emptyEl].concat(nodes), 0);
      } else {
        syncChildren(group.filesEl, nodes, 0);
      }
    }

    // ── Remove an individual file (M31 F3 HAT). One DELETE per row: the
    // `removing` flag and the disabled button stop a third click. A 2xx or a
    // 404 (already gone) tombstones the id and re-renders from the last items,
    // so the row goes at once and a stale /items response can't bring it back;
    // then status and items refresh. Focus moves only if it was on the row (or
    // had fallen to `body`): to the remove button of the row now at the same
    // position, else the one before it, else (the panel emptied) the
    // Add-folder input. A failure goes to the editor header, reverts the arm,
    // re-enables the button and focuses it again.
    function removeFile(entry, revertFn) {
      if (entry.removing || !individualPanel) return;
      entry.removing = true;
      var btn = entry.removeBtn;
      btn.disabled = true;
      var group = individualPanel.group;
      var id = entry.item.id;
      var idx = group.order.indexOf(id);
      setHeaderError('');
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items/' + encodeURIComponent(id),
        { method: 'DELETE' }
      ).then(function (r) {
        if (!r.ok && r.status !== 404) {
          return r.text().then(function (body) {
            throw new Error(_errorMessageFromResponse(body) || ('HTTP ' + r.status));
          });
        }
        if (!isCurrent()) return;
        var active = document.activeElement;
        var hadFocus = !active || active === document.body || active === btn ||
          entry.row.contains(active);
        removedIds[id] = true;
        if (lastItems) renderAllItems(lastItems);
        if (hadFocus) focusAfterRemove(idx);
        refreshStatusNow();
        refreshItemsListNow();
      }).catch(function (err) {
        if (!isCurrent()) return;
        entry.removing = false;
        btn.disabled = false;
        if (typeof revertFn === 'function') revertFn();
        setHeaderError('Couldn’t remove the file: ' + ((err && err.message) || err));
        btn.focus();
      });
    }

    function focusAfterRemove(idx) {
      var group = individualAttached && individualPanel ? individualPanel.group : null;
      var order = group ? group.order : [];
      var targetId = idx >= 0 ? (order[idx] || order[idx - 1]) : null;
      var target = targetId && group.rows[targetId];
      if (target && target.removeBtn) {
        target.removeBtn.focus();
      } else {
        folderInput.focus();
      }
    }

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
      } else if (individualAttached && individualPanel) {
        summary = individualPanel.ctl.summary;
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
      syncChildren(ln.el, [when && ln.whenEl, skip && ln.skipEl].filter(Boolean), 0);
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
      syncChildren(panel.metaEl, nodes, 0);
    }

    // The folders list: the stable empty-state node, every folder panel in the
    // folders' order, then the trailing "Individual files" panel while it has
    // rows.
    function syncPanelList(orderedFolderIds) {
      var nodes = orderedFolderIds.map(function (id) { return folderPanels[id].detailsEl; });
      if (individualAttached && individualPanel) nodes.push(individualPanel.detailsEl);
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
          releaseGroup(stale.group);
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

    // ── "Individual files" trailing panel (L6-D2, chosen option (a); renamed
    // from "Other items" at the M31 F3 HAT). Items with no `parent_id` render
    // here — never nested under a folder whose path merely contains them
    // (that would render a FALSE parentage, exactly what DD-9's chip exists
    // to prevent). The description is the body's first child.

    function buildIndividualFilesPanel() {
      var group = null;
      var ctl = App.ui.disclosure({
        variant: 'bordered',
        summary: 'Individual files',
        testid: 'kb-individual-files-panel',
        onToggle: function (open) { if (!open) closeGroupMenus(group); }
      });
      var hint = _el('p', { className: 'kb-individual-files-hint', text: INDIVIDUAL_HINT });
      hint.setAttribute('data-testid', 'kb-individual-files-hint');
      ctl.body.appendChild(hint);
      var filesEl = _el('div', { className: 'kb-individual-files-list' });
      ctl.body.appendChild(filesEl);
      group = newGroup(filesEl, null, true);
      return { ctl: ctl, detailsEl: ctl.el, group: group };
    }

    function renderIndividualFiles(files) {
      if (files.length === 0) {
        if (individualPanel) {
          // Kept for reuse, but detached with its rows and menus released.
          releaseGroup(individualPanel.group);
          individualPanel.group.filesEl.textContent = '';
        }
        if (individualAttached) {
          individualAttached = false;
          syncPanelList(lastFolderOrder);
        }
        return;
      }
      if (!individualPanel) individualPanel = buildIndividualFilesPanel();
      if (!individualAttached) {
        individualAttached = true;
        syncPanelList(lastFolderOrder);
      }
      // Never armed, so the armed no-op of `setSummary` does not apply.
      individualPanel.ctl.setSummary('Individual files (' + files.length + ')');
      renderRows(individualPanel.group, files, { individual: true });
    }

    // ── Items reconciliation (L1-D2/FIX1 carried) — only ever called at
    // mount, on an actual items-signature change, or right after a folder
    // mutation. Never called from `renderFolders`.
    // A tombstoned id (removed here) is filtered everywhere; an item whose
    // folder is unknown is held out (see the header). `onItemsRendered` gets
    // the ids of every rendered row, so an open inspect panel whose item is
    // gone can close.
    var lastItems = null;
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
        renderRows(folderPanels[id].group, byFolder[id] || [], {
          individual: false,
          folderPath: foldersById[id] && foldersById[id].path
        });
      });
      renderIndividualFiles(individual);
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
      focusAfterInspect: focusAfterInspect,
      // The mount is dead: release every panel control and every row's menu.
      destroy: function () {
        destroyed = true;
        offTimeChange();
        Object.keys(folderPanels).forEach(function (id) {
          releaseGroup(folderPanels[id].group);
          folderPanels[id].ctl.destroy();
        });
        if (individualPanel) {
          releaseGroup(individualPanel.group);
          individualPanel.ctl.destroy();
        }
      }
    };
  }

  window.App.studio.knowledgeFolders = { create: create };
})();
