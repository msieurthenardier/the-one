// App.studio.knowledgeRows — the Knowledge detail's file rows: the keyed row
// groups, building and patching one file row (status, error, freshness stamp,
// DD-9 chip, overflow menu, remove button), the remove-an-individual-file flow
// and the trailing "Individual files" panel (Mission 31 Flight 4 Leg 02b, split
// out of knowledge-folders.js; the code moved as it was, no behaviour change).
//
// The seam with knowledge-folders.js is two-way:
//   Shared through knowledge-shared.js (used by both): `setTextIfChanged`,
//     `setAttrIfChanged` (and the path/stamp helpers); `syncChildren` is
//     `App.ui.util.syncChildren`.
//   Owned HERE: the row groups and their `order` arrays (folders never reads
//     them), every row's menu, the "Individual files" panel and its attached
//     flag. Folders hears of the panel only through `ctx.attachIndividual`.
//   Owned by folders (rows never reads them): `removedIds` (the tombstones) and
//     `lastItems`; rows reaches them only through `ctx.markRemoved(id)` and
//     `ctx.renderAll()`, a thin wrapper that calls folders' CURRENT
//     `renderAllItems` (it is re-entered from a remove, so never a captured
//     function). Both must tolerate being called before the first
//     `renderAllItems`.
//
// A remove is one DELETE per row; a 2xx or a 404 tombstones the id and
// re-renders from the last items, so a stale /items response can't bring the
// row back; focus then moves to the neighbouring remove button or, with the
// panel emptied, to the Add-folder input.
//
// `create(ctx)`: ctx = {kb, isCurrent, folders, markRemoved, renderAll,
// attachIndividual, focusAddFolder, setError, refreshStatus, refreshItems,
// openChunks, openSource}. `isCurrent` is the same closure folders uses, so a
// late response after an unmount is dropped by both. `folders()` is a getter
// for the current folder array (reassigned on every `renderFolders`; never
// pass the array). Returns `{newGroup, releaseGroup, closeGroupMenus,
// renderRows, removeFile, focusAfterRemove, buildIndividualFilesPanel,
// renderIndividualFiles, individualSummary, destroy}`. All per-mount state
// lives in the `create` closure; folders must create this before its first
// `renderFolders`.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var _el = K.el;
  var _containingFolder = K.containingFolder;
  var _relativeItemPath = K.relativeItemPath;
  var _formatStamp = K.formatStamp;
  var _baseName = K.baseName;
  var syncChildren = App.ui.util.syncChildren;
  var setTextIfChanged = K.setTextIfChanged;
  var setAttrIfChanged = K.setAttrIfChanged;

  var INDIVIDUAL_HINT = 'Added one at a time through the API. These files aren’t watched ' +
    'for changes; use Re-index all files to pick up edits.';

  function create(ctx) {
    var kb = ctx.kb;
    var individualPanel = null; // built lazily, only while individual files exist
    var individualAttached = false;

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
            onSelect: function () { ctx.openChunks(entry.item, entry.menu.trigger); } },
          { label: 'View source', testid: 'kb-item-source-btn',
            onSelect: function () { ctx.openSource(entry.item, entry.menu.trigger); } }
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

      var standaloneFolder = entry.individual ? _containingFolder(item, ctx.folders()) : null;
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
        entry.menuSlot, entry.errorLine && entry.errorLine.el].filter(Boolean));
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
        syncChildren(group.filesEl, [group.emptyEl].concat(nodes));
      } else {
        syncChildren(group.filesEl, nodes);
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
      ctx.setError('');
      function removed() {
        if (!ctx.isCurrent()) return;
        var active = document.activeElement;
        var hadFocus = !active || active === document.body || active === btn ||
          entry.row.contains(active);
        ctx.markRemoved(id);
        ctx.renderAll();
        if (hadFocus) focusAfterRemove(idx);
        ctx.refreshStatus();
        ctx.refreshItems();
      }
      App.api.fetchJson(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items/' + encodeURIComponent(id),
        { method: 'DELETE' }
      ).then(removed, function (err) {
        // A 404 means the file is already gone: the same success path.
        if (err && err.status === 404) return removed();
        throw err;
      }).catch(function (err) {
        if (!ctx.isCurrent()) return;
        entry.removing = false;
        btn.disabled = false;
        if (typeof revertFn === 'function') revertFn();
        ctx.setError('Couldn’t remove the file: ' + ((err && err.message) || err));
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
        ctx.focusAddFolder();
      }
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
          ctx.attachIndividual(null);
        }
        return;
      }
      if (!individualPanel) individualPanel = buildIndividualFilesPanel();
      if (!individualAttached) {
        individualAttached = true;
        ctx.attachIndividual(individualPanel.detailsEl);
      }
      // Never armed, so the armed no-op of `setSummary` does not apply.
      individualPanel.ctl.setSummary('Individual files (' + files.length + ')');
      renderRows(individualPanel.group, files, { individual: true });
    }
    return {
      newGroup: newGroup,
      releaseGroup: releaseGroup,
      closeGroupMenus: closeGroupMenus,
      renderRows: renderRows,
      removeFile: removeFile,
      focusAfterRemove: focusAfterRemove,
      buildIndividualFilesPanel: buildIndividualFilesPanel,
      renderIndividualFiles: renderIndividualFiles,
      // The panel's summary while it is attached, for the focus after an
      // inspect panel closes; null otherwise.
      individualSummary: function () {
        return individualAttached && individualPanel ? individualPanel.ctl.summary : null;
      },
      destroy: function () {
        if (individualPanel) {
          releaseGroup(individualPanel.group);
          individualPanel.ctl.destroy();
        }
      }
    };
  }

  window.App.studio.knowledgeRows = { create: create };
})();
