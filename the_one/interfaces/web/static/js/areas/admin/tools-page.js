// The Built-in tools page controller (M31 F4 L02a): moved out of areas/admin.js
// with no behaviour change. App.admin.toolsPage.create(ctx) owns the tools
// state (list cache, in-flight toggles, the open item, the pending hydrate
// name), the item-page scaffold and the open/close click delegation. It
// reaches the area (admin.js) only through `ctx`:
//   getCategory()   the page showing (an area category id)
//   setDirty(bool)  the area's dirty mirror (the leave guard reads it)
//   getGen()        the discard generation (one counter, owned by the area)
//   bumpGen()       increments that counter
//   setDomStale(b)  the area's stale-editor-DOM flag
//   contentEl()     the page container the scaffold is mounted in
//   content         the click-delegation target (the area's content panel)
//   serializeState() the area's route-state serializer
//   pageLabel(cat)  the page's name from App.settingsPages
App.admin = App.admin || {};

App.admin.toolsPage = {
  // Parse an area sub ('tools' or 'tools/{name}') into the pending item.
  // Returns null for any other sub.
  parseSub: function (sub) {
    if (sub === 'tools') return { pendingName: null, pendingMode: null };
    if (!sub || sub.indexOf('tools/') !== 0) return null;
    var rest = sub.slice('tools/'.length);
    if (rest.charAt(rest.length - 1) === '/') rest = rest.slice(0, -1);
    // Defensive: if extra path segments, take only the first.
    var slashIdx = rest.indexOf('/');
    if (slashIdx !== -1) rest = rest.slice(0, slashIdx);
    return { pendingName: rest ? decodeURIComponent(rest) : null, pendingMode: 'edit' };
  },

  create: function (ctx) {
    // { category, listEl, itemEl } | null (another page is showing).
    var scaffold = null;
    // Set by a hydrate for an item route; consumed when that item mounts
    // (scroll its header into view, focus its title).
    var openIntent = false;
    // The mounted tool editor's { setEnabled, destroy } (tools-editor.js). Every tool's
    // editor mounts into the same item section, so each mount is a mountSlot token: a
    // stale editor (a Save for tool A resolving after tool B opened) writes no shared
    // state, because it asks isCurrent(token) first.
    var toolEditorApi = null;
    var editorSlot = App.ui.util.mountSlot();
    // null until the first fetch resolves; the grid shows a loading placeholder.
    var toolConfigs = null;
    // Per-tool in-flight PUT tracker: a second click while a PUT is pending is
    // dropped (closes the optimistic-update double-click race).
    var toolsInFlight = Object.create(null);
    // The mounted list (App.admin.toolsGrid, tools-grid.js), built once per
    // scaffold; the list-fetch "latest wins" helper (DD3).
    var grid = null;
    var listFetch = App.ui.util.latest();

    var toolFormMode = null; // null | 'edit'
    var editingTool = null; // { name, description, enabled, config, schema } | null
    var pendingToolName = null; // hydrate-vs-fetch race
    var pendingToolFormMode = null; // null | 'edit'

    // ── Item-page scaffold (M25 F3 L5b, flight DD7) ──────────────────
    // The section 4 page header, `.settings-list` (the tool list) and
    // `.settings-item` (the editor), once per category render. List renders
    // target the list section only; editors mount in the item section;
    // closing an item empties the item section.

    function mountScaffold(category) {
      var el = App.ui.util.el;
      var root = ctx.contentEl();
      root.textContent = '';
      var header = App.ui.pageHeader({ title: ctx.pageLabel(category) }).el;
      var listEl = el('div', { className: 'settings-list settings-list--' + category });
      var itemEl = el('div', { className: 'settings-item' });
      root.appendChild(header);
      root.appendChild(listEl);
      root.appendChild(itemEl);
      scaffold = { category: category, listEl: listEl, itemEl: itemEl };
      grid = category === 'tools' ? App.admin.toolsGrid.create(listEl, { onToggle: handleToolToggle }) : null;
      return scaffold;
    }

    // The mounted scaffold when `category` is the page showing, else null.
    function scaffoldFor(category) {
      return scaffold && scaffold.category === category && ctx.getCategory() === category ? scaffold : null;
    }

    // Close the open item's DOM: the item section is emptied (DD7).
    function clearItemSection() {
      editorSlot.destroy();
      toolEditorApi = null;
      if (!scaffold) return;
      scaffold.itemEl.textContent = '';
    }

    function focusNoScroll(node) {
      try { node.focus({ preventScroll: true }); } catch (e) { node.focus(); }
    }

    // An item opened by an intent (a tool name link, a deep link or boot)
    // scrolls its header into view (block: nearest) and moves focus to its
    // title (tabindex=-1). It waits one task: after a Continue on the leave
    // dialog, nav.js focuses <main> from a setTimeout, and the title must land
    // last. A close or a newer open in between cancels it.
    function revealItem(itemEl) {
      var gen = ctx.getGen();
      setTimeout(function () {
        if (gen !== ctx.getGen() || !itemEl.isConnected) return;
        var header = itemEl.querySelector('[data-testid="tool-editor-header"]');
        var title = header ? header.querySelector('h2[tabindex="-1"]') : null;
        if (header && typeof header.scrollIntoView === 'function') header.scrollIntoView({ block: 'nearest' });
        if (title) focusNoScroll(title);
      }, 0);
    }

    // ── Tools panel ───────────────────────────────────────────────────

    function render() {
      ctx.setDomStale(false);
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
      if (!sc || !grid) return;
      grid.render(toolConfigs, { inFlight: toolsInFlight, selectedName: selectedToolName() });
    }

    // Mount the tool editor in the item section.
    function mountToolItem() {
      var sc = scaffoldFor('tools');
      if (!sc || toolFormMode !== 'edit' || !editingTool) return;
      // Reset the dirty mirror BEFORE editor mount: the fresh editor starts clean;
      // onDirtyChange only fires on the first user input.
      ctx.setDirty(false);
      var reveal = openIntent;
      openIntent = false;
      toolEditorApi = null;
      var api = null;
      var token = editorSlot.mount(function () { if (api) api.destroy(); });
      function isCurrent() { return editorSlot.isCurrent(token); }
      api = App.admin.renderToolsEditor(sc.itemEl, editingTool, {
        isCurrent: isCurrent,
        // A Save response arrived (even for an editor that is no longer current): the
        // list cache and the tiles follow the server.
        onSaved: function (updated) {
          if (ctx.getCategory() !== 'tools' || !toolConfigs) return;
          for (var i = 0; i < toolConfigs.length; i++) {
            if (toolConfigs[i].name === updated.name) {
              // A list toggle for this tool still in flight decides `enabled` when its
              // own response lands (the later write wins on the server).
              toolConfigs[i] = Object.assign({}, toolConfigs[i], {
                name: updated.name,
                description: updated.description,
                enabled: toolsInFlight[updated.name] ? toolConfigs[i].enabled : updated.enabled,
                config: updated.config
              });
              break;
            }
          }
          renderToolsListNow();
        },
        // Current editor only: Cancel and Save success keep the page's state in step.
        onSaveSuccess: function (updated) {
          if (!isCurrent() || !editingTool || editingTool.name !== updated.name) return;
          // Merge the PUT response (4 fields) preserving the prior schema:
          // upsert_tool_config's response does NOT include `schema`, and the
          // editor reads `toolDetail.schema` on each render.
          editingTool = {
            name: updated.name,
            description: updated.description,
            enabled: updated.enabled,
            config: updated.config,
            schema: editingTool.schema
          };
        },
        onCancel: function () {
          // Cancel patches the form back to the saved values; the page stays in editor
          // mode (a snapshot-revert, not a "discard and exit").
          if (isCurrent()) ctx.setDirty(false);
        },
        onDirtyChange: function (d) { if (isCurrent()) ctx.setDirty(d); }
      });
      toolEditorApi = api;
      grid.setSelection(editingTool.name);
      if (reveal) revealItem(sc.itemEl);
    }

    // Loads the tool's detail and mounts its editor (the hydrate / consume
    // path, and refresh's re-read of the open tool). It renders the ITEM
    // section only: the list is never rebuilt here. A close or a newer open
    // while the detail loads (the discard generation) drops the response.
    function selectTool(name) {
      var gen = ctx.getGen();
      // ALWAYS fetches: the list cache lacks `schema`.
      return App.api.fetchJson('/api/tools/configs/' + encodeURIComponent(name))
        .then(function (detail) {
          // Stale-then guard: if a hydrate that ran after the fetch started
          // has moved to another page, or closed / replaced the item, abandon
          // the mutation rather than clobber the now-correct render.
          if (ctx.getCategory() !== 'tools' || gen !== ctx.getGen()) return;
          editingTool = detail;
          toolFormMode = 'edit';
          pendingToolName = null;
          pendingToolFormMode = null;
          if (window.App && window.App.router) {
            App.router.sync('admin', ctx.serializeState());
          }
          mountToolItem();
        })
        .catch(function (err) {
          if (ctx.getCategory() !== 'tools' || gen !== ctx.getGen()) return;
          var gone = !!err && err.status === 404;
          // An editor already open keeps standing when only its re-read fails.
          var stranded = !(toolFormMode === 'edit' && editingTool);
          if (gone || stranded) {
            // Dead id (an unknown name in the URL, or a tool removed while its
            // editor was open) or a detail that would not load: close any
            // editor and heal the URL to the section root in place -- nothing is
            // left pending, and the list stays usable.
            pendingToolName = null;
            pendingToolFormMode = null;
            toolFormMode = null;
            editingTool = null;
            ctx.setDirty(false);
            openIntent = false;
            clearItemSection();
            App.router.sync('admin', 'tools');
            if (grid) grid.setSelection(null);
          }
          if (!gone) {
            App.ui.flash((err && err.message) || ('Failed to load ' + name + '.'), {
              error: true,
              container: ctx.contentEl()
            });
          }
        });
    }

    function fetchToolConfigs() {
      var token = listFetch.next();
      return App.api.fetchJson('/api/tools/configs')
        .then(function (data) {
          // Stale-then guard at cache-write: if the operator switched away
          // mid-fetch, or a newer fetch started, do not clobber the cache.
          if (ctx.getCategory() !== 'tools' || !listFetch.isCurrent(token)) return;
          toolConfigs = data;
          renderToolsListNow();
        })
        .catch(function (err) {
          if (ctx.getCategory() !== 'tools' || !listFetch.isCurrent(token)) return;
          // Only a list that never loaded reads as failed.
          if (grid && toolConfigs === null) {
            grid.setError(err && err.message, fetchToolConfigs);
          }
        });
    }

    function handleToolToggle(name, newEnabled) {
      // Drop second click while a PUT is pending for this tool.
      if (toolsInFlight[name] || !toolConfigs) return;

      // Optimistic update: flip cache, patch the tile, PUT. Revert on failure.
      var idx = -1;
      for (var i = 0; i < toolConfigs.length; i++) {
        if (toolConfigs[i].name === name) { idx = i; break; }
      }
      if (idx === -1) return;
      var prev = toolConfigs[idx].enabled;
      toolConfigs[idx].enabled = newEnabled;
      toolsInFlight[name] = true;
      renderToolsListNow();

      App.api.fetchJson('/api/tools/configs/' + encodeURIComponent(name), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newEnabled })  // omit config: REPLACE preserves
      }).then(function () {
        // The server now holds newEnabled (a Save response that landed meanwhile
        // left the optimistic value alone).
        for (var j = 0; j < toolConfigs.length; j++) {
          if (toolConfigs[j].name === name) toolConfigs[j].enabled = newEnabled;
        }
        // The toggled tool is the one open below: its editor's Enabled
        // control and saved snapshot follow, in place (no re-mount, so an
        // unsaved edit elsewhere in the form is kept).
        if (editingTool && editingTool.name === name) {
          editingTool.enabled = newEnabled;
          if (toolEditorApi) toolEditorApi.setEnabled(newEnabled);
        }
      }).catch(function (err) {
        for (var k = 0; k < toolConfigs.length; k++) {
          if (toolConfigs[k].name === name) toolConfigs[k].enabled = prev;
        }
        showAdminFlash((err && err.message) || ('Failed to update ' + name + '.'), true);
      }).then(function () {
        // Always clear in-flight and patch the tile back (a failed toggle
        // reverts; a settled one is enabled again).
        delete toolsInFlight[name];
        renderToolsListNow();
      });
    }

    function showAdminFlash(msg, isError) {
      App.ui.flash(msg, { error: !!isError, container: ctx.contentEl() });
    }

    // ── Opening and closing items from the page (M25 F3 L5b) ────────
    // One delegated click listener on the area's content, ahead of App.nav's
    // document-level link interceptor:
    // * the item header's breadcrumb link ("Settings / Built-in tools"; with
    //   Back retired it closes the item): an intent go() to the page root, so
    //   the router's guard asks once about a dirty editor and the root hydrate
    //   closes the item in place. Once it has navigated, focus goes to the
    //   closed item's row (DD8). The focus waits one task: after a Continue,
    //   nav.js focuses <main> from a setTimeout.
    // * a list link to the item ALREADY open (its row, its tool name): no
    //   navigation; the item is just brought into view and focused.
    // Modified clicks (new tab, etc.) keep the browser's behaviour.
    function closingItem() {
      return {
        category: ctx.getCategory(),
        toolName: toolFormMode === 'edit' && editingTool ? editingTool.name : null
      };
    }

    function focusClosedItem(closing) {
      var sc = scaffoldFor(closing.category);
      if (!sc || toolFormMode) return; // the user moved on
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
      var toolLink = target.closest('[data-testid="tool-card"] a');
      if (toolLink && scaffold.listEl.contains(toolLink)) {
        var tile = toolLink.closest('[data-testid="tool-card"]');
        return toolFormMode === 'edit' && editingTool && tile && tile.getAttribute('data-name') === editingTool.name
          ? toolLink : null;
      }
      return null;
    }

    ctx.content.addEventListener('click', function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      var target = e.target;
      if (!target || typeof target.closest !== 'function') return;
      if (openItemLink(target)) {
        e.preventDefault();
        revealItem(scaffold.itemEl);
        return;
      }
      var link = target.closest('a[data-testid="editor-breadcrumb-link"]');
      if (!link || !ctx.content.contains(link)) return;
      e.preventDefault();
      var closing = closingItem();
      App.router.go(link.getAttribute('href'), { opener: link }).then(function (navigated) {
        if (navigated) setTimeout(function () { focusClosedItem(closing); }, 0);
      });
    });

    // ── The handle ────────────────────────────────────────────────────

    var handle = {
      render: render,
      scaffoldFor: scaffoldFor,
      parseSub: App.admin.toolsPage.parseSub,
      // A page render replaces the content: drop the scaffold and editor.
      reset: function () {
        if (grid) grid.destroy();
        grid = null;
        listFetch.invalidate();
        editorSlot.destroy();
        scaffold = null;
        toolEditorApi = null;
      },
      // A category change resets the item state (the area bumps its counter).
      onCategoryChange: function () {
        toolFormMode = null;
        editingTool = null;
        pendingToolName = null;
        pendingToolFormMode = null;
        openIntent = false;
      },
      // Something is open or pending (the same-category close test).
      hasItemOrPending: function () {
        return !!(toolFormMode || pendingToolFormMode || pendingToolName);
      },
      isOpen: function () { return !!toolFormMode; },
      refresh: function () {
        fetchToolConfigs();
        // Re-fetch the per-tool detail so the editor reflects external changes
        // while it was mounted. It re-mounts the item section only (no focus
        // move: not an intent).
        if (toolFormMode === 'edit' && editingTool) selectTool(editingTool.name);
      },
      // The area-state string for the open tool: 'tools' or 'tools/{name}'.
      serialize: function () {
        if (toolFormMode === 'edit' && editingTool) {
          return 'tools/' + encodeURIComponent(editingTool.name);
        }
        // Hydrate-vs-fetch race: pending name known but tool detail not yet loaded.
        if (pendingToolName) return 'tools/' + encodeURIComponent(pendingToolName);
        return 'tools';
      },
      // Close the open tool item: its state and its DOM (the item section is
      // emptied; M25 F3 L5b). An item hydrate inside the category that is
      // already showing then mounts the new item there.
      closeOpenItem: function () {
        ctx.bumpGen(); // a teardown invalidates any in-flight editor resolver
        App.focusAfter.cancel();
        toolFormMode = null;
        editingTool = null;
        pendingToolName = null;
        pendingToolFormMode = null;
        ctx.setDirty(false);
        openIntent = false;
        clearItemSection();
        handle.syncItemSelection();
      },
      tryConsumePending: function () {
        if (!pendingToolName && !pendingToolFormMode) return;
        if (pendingToolFormMode === 'edit' && pendingToolName) {
          // The pending slot stays set until the detail loads (selectTool
          // clears it on success, or heals on a 404), so the route state keeps
          // the URL on `tools/{name}` meanwhile instead of flickering to the root.
          selectTool(pendingToolName);
        }
      },
      // The list's selection is the open item, else the pending one (a deep
      // link still loading): the tool tile. In place.
      syncItemSelection: function () {
        if (scaffoldFor('tools') && grid) grid.setSelection(selectedToolName());
      },
      setOpenIntent: function (on) { openIntent = !!on; }
    };

    // State accessors behind the area's test seams.
    function accessor(name, get, set) {
      Object.defineProperty(handle, name, { get: get, set: set, enumerable: true, configurable: true });
    }
    accessor('toolFormMode', function () { return toolFormMode; }, function (v) { toolFormMode = v; });
    accessor('editingTool', function () { return editingTool; }, function (v) { editingTool = v; });
    accessor('pendingToolName', function () { return pendingToolName; }, function (v) { pendingToolName = v; });
    accessor('pendingToolFormMode', function () { return pendingToolFormMode; }, function (v) { pendingToolFormMode = v; });

    return handle;
  }
};
