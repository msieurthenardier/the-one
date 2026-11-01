(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.tabs(opts) -> {el, tablist, panels, select(id), selected(),
  // panel(id), setIndicator(id, label|null), destroy()}. The W3C manual-activation tablist (M31 F2 L4): the
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

    // The indicator (sortie 07 L05, DD11): a small aria-hidden dot plus a
    // visually hidden run ", <label>", so the tab's name reads "Tools, 1 notice".
    // Both nodes are siblings of the label text and carry data-tab-indicator.
    function clearIndicator(tab) {
      var old = tab.querySelectorAll('[data-tab-indicator]');
      for (var n = 0; n < old.length; n++) tab.removeChild(old[n]);
      tab.removeAttribute('aria-label');
    }
    function paintIndicator(tab, label) {
      clearIndicator(tab);
      if (!label) return;
      // The name is also set explicitly: the absolutely positioned hidden run
      // would otherwise be joined to the label with a stray space.
      tab.setAttribute('aria-label', tab.firstChild.textContent + ', ' + label);
      tab.appendChild(util.el('span', {
        className: 'ui-tab-indicator-dot', 'aria-hidden': 'true', 'data-tab-indicator': 'dot'
      }));
      tab.appendChild(util.el('span', {
        className: 'visually-hidden','data-tab-indicator': 'text',
        text: ', ' + label
      }));
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
      if (item.indicator) paintIndicator(tab, item.indicator);
      tablist.appendChild(tab);
      panelsEl.appendChild(panel);
      tabs.push(tab);
      panelList.push(panel);
    }

    var activeId = null;

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

    if (opts.initial) activate(opts.initial);

    return {
      el: root,
      tablist: tablist,
      panels: panelsEl,
      select: activate,
      setIndicator: function (id, label) {
        for (var k = 0; k < tabs.length; k++) {
          if (tabs[k].getAttribute('data-tab-id') === id) {
            paintIndicator(tabs[k], label ? String(label) : null);
            return true;
          }
        }
        return false;
      },
      selected: function () { return activeId; },
      panel: function (id) {
        for (var k = 0; k < panelList.length; k++) {
          if (panelList[k].getAttribute('data-tab-id') === id) return panelList[k];
        }
        return null;
      },
      destroy: function () {
        tablist.removeEventListener('keydown', onKeydown);
        tablist.removeEventListener('click', onClick);
      }
    };
  };
})();
