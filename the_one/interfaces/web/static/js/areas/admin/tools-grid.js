(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // The Built-in tools LIST (M31 F4 L06, flight DD6): category tabs
  // (App.ui.tabs) over one App.ui.toolTile.grid per category, mounted once and
  // reconciled by tool name. A toggle, a list refetch or a selection change
  // patches the tiles it concerns; the list is never rebuilt, so a focused
  // toggle, link or tab keeps focus with no hand-made restore.
  //
  //   App.admin.toolsGrid.create(listEl, {onToggle(name, enabled),
  //     onBeforeCategoryChange(id, commit)}) ->
  //     { render(toolConfigs, {selectedName, inFlight}), setSelection(name),
  //       setLoading(), setError(text, onRetry), destroy() }
  //
  //   render(null) shows "Loading tools…"; an empty array an empty state. A
  //   tile's description is the served `summary` (B1), the model-facing
  //   `description` only when a summary is missing. `inFlight` is a map of
  //   tool name -> true: those tiles' switches are disabled. setError(text,
  //   onRetry) shows the load failure and a Retry button (the list never
  //   loaded); render() clears it.
  //
  // onBeforeCategoryChange(id, commit), when given, wraps a USER tab switch
  // (click, Enter, Space): the tab changes only if the callback calls
  // commit(), now or later (the veto is the tab staying put). The page uses it
  // to close an open tool editor, through the router's leave guard, first
  // (HAT step 3). A programmatic reveal of a tool's category does not use it.
  //
  // The tool's Config class determines its category, but the API surfaces only
  // name/summary/description/enabled/config, so the table is client-side: the
  // one shared table (static/js/tool-categories.js). A tool missing from it
  // would show in no tab; tests/test_tool_categories.py prevents that.
  var TOOL_CATEGORIES = App.toolCategories.categoryOf;
  var CATEGORY_ORDER = App.toolCategories.order;
  var CATEGORY_LABELS = App.toolCategories.labels;

  // Module state, so the active tab survives a re-render and leaving and
  // re-entering Settings › Built-in tools within the page's lifetime. Default
  // 'filesystem' (the largest group).
  var activeCategory = 'filesystem';
  // The open tool whose category was last revealed: opening a tool (or a deep
  // link to one) switches the tabs to its category ONCE; a later render with
  // the same tool open (a toggle PUT) keeps whatever tab the user chose since.
  var revealedName = null;

  function categoryOf(name) {
    return TOOL_CATEGORIES[name] || 'unknown';
  }

  function sortedByName(configs) {
    return configs.slice().sort(function (a, b) {
      return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
    });
  }

  App.admin.toolsGrid = {
    create: function (listEl, opts) {
      opts = opts || {};
      var util = App.ui.util;
      var onToggle = typeof opts.onToggle === 'function' ? opts.onToggle : function () {};

      var onBefore = typeof opts.onBeforeCategoryChange === 'function'
        ? opts.onBeforeCategoryChange : null;

      var stateEl = util.el('div', { className: 'tools-grid-state', hidden: true });
      listEl.appendChild(stateEl);

      var items = [];
      var ti;
      for (ti = 0; ti < CATEGORY_ORDER.length; ti++) {
        items.push({
          id: CATEGORY_ORDER[ti],
          label: CATEGORY_LABELS[CATEGORY_ORDER[ti]],
          testid: 'tab-' + CATEGORY_ORDER[ti]
        });
      }
      var initial = CATEGORY_ORDER.indexOf(activeCategory) === -1 ? 'filesystem' : activeCategory;
      var tabs = App.ui.tabs({
        label: 'Tool categories',
        idPrefix: 'tools',
        items: items,
        initial: initial,
        panelPadding: 'none',
        onBeforeChange: onBefore ? function (id, commit) {
          // Re-pressing the active tab is intentionally a no-op.
          if (id === activeCategory) return;
          onBefore(id, commit);
        } : null,
        onChange: function (id) { activeCategory = id; }
      });
      tabs.el.hidden = true;
      listEl.appendChild(tabs.el);

      // One grid per category, in its panel; one tile per tool, kept for the
      // life of the list.
      var grids = Object.create(null);
      var empties = Object.create(null);
      CATEGORY_ORDER.forEach(function (cid) {
        grids[cid] = App.ui.toolTile.grid({ label: CATEGORY_LABELS[cid] + ' tools' });
        tabs.panel(cid).appendChild(grids[cid].el);
        empties[cid] = App.ui.emptyState({ title: 'No tools.', variant: 'flush' });
        empties[cid].hidden = true;
        tabs.panel(cid).appendChild(empties[cid]);
      });
      var tiles = Object.create(null); // name -> { tile, category }
      var order = Object.create(null); // category -> the names shown, in order
      var selected = null;
      // The tool whose switch held focus when its PUT disabled it. A browser
      // drops focus from a control that becomes disabled, so the grid gives it
      // back when that tile is enabled again and nothing else took focus.
      var heldFocus = null;

      function showState(node) {
        stateEl.textContent = '';
        if (node) stateEl.appendChild(node);
        stateEl.hidden = !node;
        tabs.el.hidden = !!node;
      }

      function makeTile(t) {
        var name = t.name;
        var tile = App.ui.toolTile({
          name: name,
          href: App.router.href({ destination: 'settings', section: 'tools', id: name }),
          description: t.summary || t.description || '',
          testid: 'tool-card',
          dataset: { name: name },
          toggle: {
            label: 'Enable ' + name + ' for all agents',
            checked: !!t.enabled,
            testid: 'tool-toggle',
            dataset: { name: name },
            onChange: function (checked) { onToggle(name, checked); }
          }
        });
        return { tile: tile, category: categoryOf(name) };
      }

      // The element holding focus, as a tile name (a toggle or a link) or a tab.
      function focusedTool() {
        var a = document.activeElement;
        if (!a || !listEl.contains(a)) return null;
        var card = a.closest ? a.closest('[data-testid="tool-card"]') : null;
        return card ? card.getAttribute('data-name') : null;
      }

      // Where focus goes when the focused tool leaves the list: the next
      // tile's toggle in the same panel, else the previous one's, else the
      // panel's tab.
      function successorOf(name, kept) {
        var cat = tiles[name] ? tiles[name].category : null;
        var names = cat && order[cat] ? order[cat] : [];
        var at = names.indexOf(name);
        var i;
        for (i = at + 1; i < names.length; i++) if (kept[names[i]]) return names[i];
        for (i = at - 1; i >= 0; i--) if (kept[names[i]]) return names[i];
        return null;
      }

      function revealSelected() {
        if (!selected) {
          revealedName = null;
          return;
        }
        if (selected === revealedName) return;
        revealedName = selected;
        var cat = TOOL_CATEGORIES[selected];
        if (cat && CATEGORY_ORDER.indexOf(cat) !== -1 && tabs.selected() !== cat) tabs.select(cat);
      }

      function applySelection() {
        Object.keys(tiles).forEach(function (name) {
          tiles[name].tile.setSelected(!!selected && name === selected);
        });
      }

      var controller = {
        setLoading: function () {
          var status = App.ui.status({ testid: 'tools-loading' });
          status.set('pending', 'Loading tools…');
          showState(status.el);
        },

        setError: function (text, onRetry) {
          var status = App.ui.status({ role: 'alert', testid: 'tools-load-error' });
          status.set('danger', "Couldn't load the built-in tools." + (text ? ' ' + text : ''));
          var box = util.el('div', { className: 'tools-grid-error' }, [status.el]);
          if (typeof onRetry === 'function') {
            box.appendChild(App.ui.button({
              label: 'Retry',
              variant: 'secondary',
              testid: 'tools-load-retry',
              onClick: onRetry
            }));
          }
          showState(box);
        },

        render: function (toolConfigs, ropts) {
          ropts = ropts || {};
          var inFlight = ropts.inFlight || Object.create(null);
          if (ropts.selectedName !== undefined) selected = ropts.selectedName || null;
          if (toolConfigs === null || toolConfigs === undefined) {
            controller.setLoading();
            return;
          }
          if (toolConfigs.length === 0) {
            showState(App.ui.emptyState({ title: 'API returned no tools.', variant: 'flush' }));
            return;
          }
          showState(null);
          revealSelected();

          var sorted = sortedByName(toolConfigs);
          var kept = Object.create(null);
          sorted.forEach(function (t) { kept[t.name] = true; });

          // Focus is held across a removal: note where it goes before the tile leaves.
          var focused = focusedTool();
          var heir = focused && !kept[focused] ? successorOf(focused, kept) : null;
          var lostCategory = focused && !kept[focused] && tiles[focused] ? tiles[focused].category : null;

          var byCategory = Object.create(null);
          sorted.forEach(function (t) {
            var entry = tiles[t.name];
            if (!entry) {
              entry = makeTile(t);
              tiles[t.name] = entry;
            } else {
              entry.tile.setChecked(!!t.enabled);
              entry.tile.setDescription(t.summary || t.description || '');
            }
            var nowDisabled = !!inFlight[t.name];
            if (nowDisabled && !entry.disabled && document.activeElement === entry.tile.toggle.control) {
              heldFocus = t.name;
            }
            entry.tile.setDisabled(nowDisabled);
            entry.disabled = nowDisabled;
            entry.category = categoryOf(t.name);
            (byCategory[entry.category] = byCategory[entry.category] || []).push(t.name);
          });
          Object.keys(tiles).forEach(function (name) {
            if (!kept[name]) delete tiles[name];
          });

          CATEGORY_ORDER.forEach(function (cid) {
            var names = byCategory[cid] || [];
            grids[cid].sync(names.map(function (n) { return tiles[n].tile; }));
            grids[cid].el.hidden = names.length === 0;
            empties[cid].hidden = names.length !== 0;
            order[cid] = names;
          });
          applySelection();

          if (heldFocus && tiles[heldFocus] && !tiles[heldFocus].disabled) {
            var back = tiles[heldFocus].tile.toggle.control;
            var idle = !document.activeElement || document.activeElement === document.body;
            heldFocus = null;
            if (idle) back.focus({ preventScroll: true });
          } else if (heldFocus && !tiles[heldFocus]) {
            heldFocus = null;
          }
          if (focused && !kept[focused]) {
            if (heir) {
              tiles[heir].tile.toggle.control.focus({ preventScroll: true });
            } else if (lostCategory) {
              var tab = tabs.tablist.querySelector('[data-tab-id="' + lostCategory + '"]');
              if (tab) tab.focus({ preventScroll: true });
            }
          }
        },

        // Mark the open tool in place: aria-current="page" on its link and the
        // selected wash on its tile; every other tile is cleared. Opening a tool
        // switches the tabs to its category once (an unknown name keeps the tab).
        setSelection: function (name) {
          selected = name || null;
          applySelection();
          revealSelected();
        },

        destroy: function () {
          tabs.destroy();
        }
      };
      return controller;
    }
  };
})();
