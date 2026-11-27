(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.tabs(opts) -> {el, tablist, panels, select(id), selected(),
  // panel(id), setIndicator(id, label|null), focusTab(id), opener(id), place(), destroy()}.
  // The W3C manual-activation tablist (M31 F2 L4): the
  // library form of the old App.tabs helper (js/tabs.js, deleted in M31 F4 L06
  // when its last caller, the Built-in tools list, moved here).
  //   label (the tablist's aria-label), items [{id, label, testid}], initial,
  //   onBeforeChange(id, commit), onChange(id), idPrefix, panelClass, split.
  //   Tab ids are <idPrefix>-tab-<id>, panel ids <idPrefix>-panel-<id>; both
  //   carry data-tab-id. el is div.ui-tabs holding div.tablist[role=tablist]
  //   and a sibling div.tabpanels (one div.tabpanel[role=tabpanel] per item,
  //   hidden unless active); with split: true there is no wrapper (el is null)
  //   and the host places tablist and panels itself.
  //   Keyboard: arrows move focus only (wrapping), Home and End jump, Enter,
  //   Space and click commit. The roving tabindex and aria-selected change only
  //   on a commit. onBeforeChange(id, commit), when given, wraps every commit:
  //   it proceeds only if the callback calls commit() (now or later); doing
  //   nothing is the veto. Arrow keys never go through it. select(id) commits
  //   directly (no onBeforeChange) and, like a user commit, calls onChange.
  //   panelPadding: 'none' (M31 F4 L04d) adds the marker .ui-tabs--flush to
  //   the tablist and every panel: no padding and a visible overflow, so the
  //   page that hosts the tabs owns the inset and the only scroller.
  //   indicator (sortie 07 L05, DD11): an item's optional `indicator` (a label
  //   string such as "1 notice") and setIndicator(id, label|null) draw a small
  //   aria-hidden dot (.ui-tab-indicator-dot) and a visually hidden ", <label>"
  //   run inside the tab button, so the accessible name is "<label>, <indicator>".
  //   Colour is never the only cue; null removes both. Selection and keys are
  //   untouched. setIndicator returns false for an unknown id.
  //   Narrow mode (sortie 21 HAT feature): below 768px (App.ui.util.narrow) the tablist
  //   is hidden and a menu button (App.ui.menu, div.ui-tabs-menu before the tablist)
  //   takes its place: its label is the current tab's label and its chevron marks it
  //   a menu; its popup (named by `popupLabel`, default `label`) lists every tab as a
  //   menuitemradio, the current one checked. Choosing an item goes through the same
  //   commit as a click (onBeforeChange veto, onChange). activate() relabels the button
  //   and moves the check, so select(), the router and fills keep it in step;
  //   setIndicator repaints the button (current tab only) and the item. Test ids:
  //   <idPrefix>-tabs-menu-btn and <tab testid>-menu-item. The tabpanel keeps
  //   aria-labelledby to its (hidden) tab. A change of width switches modes keeping the
  //   selection; an open menu closes without taking focus, and focus inside the part
  //   being hidden moves to its counterpart. At 768px and wider the DOM is exactly
  //   the plain tablist. focusTab(id) focuses the visible control and opener(id)
  //   returns it (the tab at wide, the menu button at narrow; null for an unknown id).
  //   With split: true the host calls place() after putting tablist in the document so
  //   the narrow menu can sit before it.
  //   destroy() removes the listeners and leaves the nodes to the caller.
  App.ui.tabs = function (opts) {
    opts = opts || {};
    if (!opts.label) throw new Error('App.ui.tabs: label is required');
    var items = opts.items || [];
    if (!items.length) throw new Error('App.ui.tabs: items are required');
    var util = App.ui.util;
    var prefix = opts.idPrefix || util.uid('tabs');
    var panelPrefix = opts.panelIdPrefix || (prefix + '-panel');
    var onBeforeChange = typeof opts.onBeforeChange === 'function' ? opts.onBeforeChange : null;
    var onChange = typeof opts.onChange === 'function' ? opts.onChange : function () {};
    var popupLabel = opts.popupLabel || opts.label;

    // The indicator (sortie 07 L05, DD11): a small aria-hidden dot plus a
    // visually hidden run ", <label>", so the tab's name reads "Tools, 1 notice".
    // Both nodes are siblings of the label text and carry data-tab-indicator.
    function clearIndicator(node) {
      var old = node.querySelectorAll('[data-tab-indicator]');
      for (var n = 0; n < old.length; n++) old[n].parentNode.removeChild(old[n]);
      node.removeAttribute('aria-label');
    }
    // `name` is the control's own label (its explicit aria-label becomes "<name>, <label>");
    // `before`, when given, is the child the two nodes go in front of (the narrow
    // trigger's chevron); otherwise they are appended.
    function paintIndicator(node, label, name, before) {
      clearIndicator(node);
      if (!label) return;
      // The name is also set explicitly: the absolutely positioned hidden run
      // would otherwise be joined to the label with a stray space.
      node.setAttribute('aria-label', name + ', ' + label);
      node.insertBefore(util.el('span', {
        className: 'ui-tab-indicator-dot', 'aria-hidden': 'true', 'data-tab-indicator': 'dot'
      }), before || null);
      node.insertBefore(util.el('span', {
        className: 'visually-hidden','data-tab-indicator': 'text',
        text: ', ' + label
      }), before || null);
    }

    var flush = opts.panelPadding === 'none';
    var tablist = util.el('div', {
      role: 'tablist',
      className: 'tablist' + (flush ? ' ui-tabs--flush' : ''),
      'aria-label': opts.label
    });
    var panelsEl = util.el('div', { className: 'tabpanels' });
    var tabs = [];
    var panelList = [];
    var indicators = {};
    var seen = {};
    var i;
    for (i = 0; i < items.length; i++) {
      var item = items[i];
      if (!item || !item.id || !item.label) {
        throw new Error('App.ui.tabs: each item needs an id and a label');
      }
      if (seen[item.id]) throw new Error('App.ui.tabs: duplicate id');
      seen[item.id] = true;
      var tabId = prefix + '-tab-' + item.id;
      var panelId = panelPrefix + '-' + item.id;
      var tab = util.el('button', {
        type: 'button',
        role: 'tab',
        className: 'tab',
        id: tabId,
        'aria-controls': panelId,
        'aria-selected': 'false',
        tabindex: '-1',
        'data-tab-id': item.id,
        'data-testid': item.testid,
        text: item.label
      });
      var panel = util.el('div', {
        role: 'tabpanel',
        className: 'tabpanel' + (opts.panelClass ? ' ' + opts.panelClass : '') + (flush ? ' ui-tabs--flush' : ''),
        id: panelId,
        'aria-labelledby': tabId,
        'data-tab-id': item.id,
        hidden: true
      });
      indicators[item.id] = item.indicator ? String(item.indicator) : null;
      if (item.indicator) paintIndicator(tab, item.indicator, item.label);
      tablist.appendChild(tab);
      panelsEl.appendChild(panel);
      tabs.push(tab);
      panelList.push(panel);
    }

    var activeId = null;

    // ── Narrow mode: one menu button in place of the tablist ───────────
    var narrowMode = false;
    var menuCtl = null;       // the App.ui.menu while narrow
    var menuWrap = null;      // div.ui-tabs-menu holding it
    var menuItemNodes = [];   // the menuitemradio nodes, one per tab, in order
    var menuChevron = null;

    function indexOfId(id) {
      for (var k = 0; k < tabs.length; k++) {
        if (tabs[k].getAttribute('data-tab-id') === id) return k;
      }
      return -1;
    }

    function currentLabel() {
      var k = indexOfId(activeId);
      return k === -1 ? opts.label : items[k].label;
    }

    function repaintTrigger() {
      if (!menuCtl) return;
      var name = currentLabel();
      paintIndicator(menuCtl.trigger, activeId ? indicators[activeId] : null, name, menuChevron);
    }

    // Insert the narrow wrapper before the tablist once the tablist is in a document
    // tree (a split host appends it after construction).
    function place() {
      if (!menuWrap || menuWrap.parentNode || !tablist.parentNode) return;
      tablist.parentNode.insertBefore(menuWrap, tablist);
    }

    function syncMenu() {
      if (!menuCtl) return;
      menuCtl.setTriggerLabel(currentLabel());
      for (var k = 0; k < tabs.length; k++) {
        menuCtl.setItemChecked(k, tabs[k].getAttribute('data-tab-id') === activeId);
      }
      repaintTrigger();
      place();
    }

    function enterNarrow(fromChange) {
      var focusInTabs = fromChange && tablist.contains(document.activeElement);
      var menuItems = items.map(function (it) {
        var mi = {
          label: it.label,
          checked: it.id === activeId,
          onSelect: function () { commit(it.id); }
        };
        if (it.testid) mi.testid = it.testid + '-menu-item';
        return mi;
      });
      var triggerOpts = { label: currentLabel(), className: 'ui-tabs-menu-btn' };
      triggerOpts.testid = prefix + '-tabs-menu-btn';
      menuCtl = App.ui.menu({
        trigger: triggerOpts,
        popupLabel: popupLabel,
        items: menuItems
      });
      // The label lives in a span so it can truncate with an ellipsis; the chevron
      // follows it.
      var trig = menuCtl.trigger;
      var labelSpan = util.el('span', { className: 'ui-menu-trigger-label', text: currentLabel() });
      for (var c = trig.childNodes.length - 1; c >= 0; c--) {
        if (trig.childNodes[c].nodeType === 3) trig.removeChild(trig.childNodes[c]);
      }
      trig.appendChild(labelSpan);
      menuChevron = util.el('span', { className: 'ui-tabs-menu-chevron' }, [util.icon('chevron-down')]);
      trig.appendChild(menuChevron);
      menuItemNodes = Array.prototype.slice.call(menuCtl.popup.querySelectorAll('[role="menuitemradio"]'));
      for (var m = 0; m < menuItemNodes.length; m++) {
        paintIndicator(menuItemNodes[m], indicators[items[m].id], items[m].label);
      }
      menuWrap = util.el('div', {
        className: 'ui-tabs-menu' + (flush ? ' ui-tabs--flush' : '')
      }, [menuCtl.el]);
      tablist.hidden = true;
      repaintTrigger();
      place();
      if (focusInTabs) trig.focus();
    }

    function leaveNarrow(fromChange) {
      var wasOpen = menuCtl.isOpen();
      var focusInMenu = fromChange && menuWrap.contains(document.activeElement);
      if (wasOpen) menuCtl.close(false);
      menuCtl.destroy();
      if (menuWrap.parentNode) menuWrap.parentNode.removeChild(menuWrap);
      menuCtl = null;
      menuWrap = null;
      menuItemNodes = [];
      menuChevron = null;
      tablist.removeAttribute('hidden');
      if (focusInMenu) {
        var k = indexOfId(activeId);
        tabs[k === -1 ? 0 : k].focus();
      }
    }

    function setMode(isNarrow, fromChange) {
      if (isNarrow === narrowMode) return;
      narrowMode = isNarrow;
      if (isNarrow) enterNarrow(fromChange);
      else leaveNarrow(fromChange);
    }

    function activate(id) {
      activeId = id;
      var k;
      for (k = 0; k < tabs.length; k++) {
        var match = tabs[k].getAttribute('data-tab-id') === id;
        tabs[k].setAttribute('aria-selected', match ? 'true' : 'false');
        tabs[k].setAttribute('tabindex', match ? '0' : '-1');
        if (match) {
          panelList[k].removeAttribute('hidden');
        } else {
          panelList[k].setAttribute('hidden', '');
        }
      }
      syncMenu();
      onChange(id);
    }

    function commit(id) {
      if (onBeforeChange) {
        onBeforeChange(id, function () { activate(id); });
      } else {
        activate(id);
      }
    }

    function onKeydown(e) {
      var idx = tabs.indexOf(document.activeElement);
      if (idx === -1) return;
      var next = idx;
      if (e.key === 'ArrowLeft') {
        next = (idx - 1 + tabs.length) % tabs.length;
      } else if (e.key === 'ArrowRight') {
        next = (idx + 1) % tabs.length;
      } else if (e.key === 'Home') {
        next = 0;
      } else if (e.key === 'End') {
        next = tabs.length - 1;
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        commit(tabs[idx].getAttribute('data-tab-id'));
        return;
      } else {
        return;
      }
      e.preventDefault();
      // Focus only: the roving tabindex moves on a commit, not on an arrow.
      tabs[next].focus();
    }

    function onClick(e) {
      var t = e.target && e.target.closest ? e.target.closest('[role="tab"]') : null;
      if (!t || tabs.indexOf(t) === -1) return;
      commit(t.getAttribute('data-tab-id'));
    }

    tablist.addEventListener('keydown', onKeydown);
    tablist.addEventListener('click', onClick);

    var root = null;
    if (!opts.split) {
      root = util.el('div', { className: 'ui-tabs' }, [tablist, panelsEl]);
    }

    // The narrow state is built before the initial activate so it is labelled in one pass.
    setMode(util.narrow.matches(), false);
    var unsubscribeNarrow = util.narrow.subscribe(function (isNarrow) { setMode(isNarrow, true); });

    if (opts.initial) activate(opts.initial);

    return {
      el: root,
      tablist: tablist,
      panels: panelsEl,
      select: activate,
      place: place,
      setIndicator: function (id, label) {
        var k = indexOfId(id);
        if (k === -1) return false;
        var text = label ? String(label) : null;
        indicators[id] = text;
        paintIndicator(tabs[k], text, items[k].label);
        if (menuCtl) {
          paintIndicator(menuItemNodes[k], text, items[k].label);
          repaintTrigger();
        }
        return true;
      },
      selected: function () { return activeId; },
      opener: function (id) {
        var k = indexOfId(id);
        if (k === -1) return null;
        return menuCtl ? menuCtl.trigger : tabs[k];
      },
      focusTab: function (id, focusOpts) {
        var k = indexOfId(id);
        if (k === -1) return false;
        (menuCtl ? menuCtl.trigger : tabs[k]).focus(focusOpts);
        return true;
      },
      panel: function (id) {
        for (var k = 0; k < panelList.length; k++) {
          if (panelList[k].getAttribute('data-tab-id') === id) return panelList[k];
        }
        return null;
      },
      destroy: function () {
        tablist.removeEventListener('keydown', onKeydown);
        tablist.removeEventListener('click', onClick);
        unsubscribeNarrow();
        if (menuCtl) menuCtl.destroy();
      }
    };
  };
})();
