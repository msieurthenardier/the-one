(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var ROW_SELECTOR = 'li:not([hidden]) > .ui-list-pane-row';

  function defaultPredicate(item, query) {
    var needle = query.toLowerCase();
    var hay = (item.label || '') + ' ' + (item.meta || '');
    return hay.toLowerCase().indexOf(needle) !== -1;
  }

  // Normalise setItems input (a flat item array, or an array of groups) to
  // [{label, items}] and validate it BEFORE any DOM is touched.
  function normalise(input) {
    var list = input || [];
    var isGroups = list.length > 0 && Array.isArray(list[0].items);
    var groups = [];
    var seen = {};
    var i;
    var j;
    if (isGroups) {
      for (i = 0; i < list.length; i++) {
        if (!Array.isArray(list[i].items)) {
          throw new Error('App.ui.listPane: cannot mix groups and plain items');
        }
        groups.push({ label: list[i].label || '', items: list[i].items });
      }
    } else {
      groups.push({ label: null, items: list });
    }
    for (i = 0; i < groups.length; i++) {
      for (j = 0; j < groups[i].items.length; j++) {
        var item = groups[i].items[j];
        if (item.id === undefined || item.id === null || item.id === '') {
          throw new Error('listPane item: id required');
        }
        if (!item.href && typeof item.onSelect !== 'function') {
          throw new Error('listPane item ' + item.id + ': href or onSelect required');
        }
        if (Object.prototype.hasOwnProperty.call(seen, item.id)) {
          throw new Error('listPane duplicate item id ' + item.id);
        }
        seen[item.id] = true;
      }
    }
    return groups;
  }

  // App.ui.listPane(opts) -> controller {el, setItems(items|groups),
  // setSelected(id), focusSelected(), destroy()}. A navigation list (DD14).
  //   title (required, the h2), actions (array of elements), filter
  //   ({label, placeholder, predicate(item, query), plus a nested test id
  //   option placed on the filter input}), emptyText, items | groups,
  //   selectedId, density (regular | compact), and the test id option on the
  //   root section.
  //   item: {id, label, meta, href | onSelect, badges[], count, icon, and a
  //   per-item test id option placed on the row}. A badges[] entry is a node,
  //   a string, or {text, kind, title}: with a kind it renders through
  //   App.ui.badge, without one as a neutral muted span. count is trailing
  //   text (never colour-only meaning). The empty element is App.ui.emptyState.
  // Rows are links when href is given, else buttons. The selected row carries
  // aria-current="page". Keyboard handling lives on the list body only (Tab
  // enters at the selected row, else the first visible row; arrows/Home/End
  // roving). No document-level listener is ever installed (DD1).
  App.ui.listPane = function (opts) {
    opts = opts || {};
    if (!opts.title) throw new Error('App.ui.listPane: title is required');
    var util = App.ui.util;
    var predicate = (opts.filter && opts.filter.predicate) || defaultPredicate;
    var titleId = util.uid('lp-title');
    var selectedId = opts.selectedId === undefined ? null : opts.selectedId;
    var query = '';
    var entries = [];
    var groupNodes = [];
    var density = opts.density === 'compact' ? 'compact' : 'regular';

    var title = util.el('h2', { className: 'ui-list-pane-title', id: titleId, text: opts.title });
    var header = util.el('header', { className: 'ui-list-pane-header' }, [title]);
    if (opts.actions && opts.actions.length) {
      header.appendChild(util.el('div', { className: 'ui-list-pane-actions' }, opts.actions));
    }
    var root = util.el(
      'section',
      { className: 'ui-list-pane ui-list-pane-' + density, 'aria-labelledby': titleId },
      [header]
    );
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    if (opts.filter) {
      var filterInput = App.ui.textInput({
        type: 'search',
        placeholder: opts.filter.placeholder,
        autocomplete: 'off',
        testid: opts.filter.testid,
        onInput: function () {
          query = filterInput.value;
          applyView();
          announce();
        }
      });
      var filterField = App.ui.field({
        label: opts.filter.label || 'Filter ' + opts.title,
        labelHidden: true,
        control: filterInput
      });
      filterField.el.classList.add('ui-list-pane-filter');
      root.appendChild(filterField.el);
    }

    var body = util.el('div', { className: 'ui-list-pane-body' });
    // The empty state is toggled with hidden, so it is not a reliable live
    // region. A persistent visually-hidden polite region reports filter results
    // instead (WCAG 4.1.3); it is written only when the filter query changes.
    var status = util.el('div', { className: 'ui-list-pane-status' });
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    root.appendChild(status);
    var empty = App.ui.emptyState({ title: opts.emptyText || 'Nothing to show' });
    empty.classList.add('ui-list-pane-empty');
    empty.hidden = true;
    root.appendChild(body);
    root.appendChild(empty);
    var unbind = util.rovingFocus(body, ROW_SELECTOR);

    function buildRow(item) {
      var node;
      if (item.href) {
        node = util.el('a', { className: 'ui-list-pane-row', href: item.href });
      } else {
        node = util.el('button', { className: 'ui-list-pane-row', type: 'button' });
      }
      if (typeof item.onSelect === 'function') {
        node.addEventListener('click', function () {
          item.onSelect(item);
        });
      }
      if (item.icon) {
        node.appendChild(util.el('span', { className: 'ui-list-pane-icon' }, [util.icon(item.icon)]));
      }
      var text = util.el('span', { className: 'ui-list-pane-text' }, [
        util.el('span', { className: 'ui-list-pane-label', text: item.label })
      ]);
      if (item.meta) {
        text.appendChild(util.el('span', { className: 'ui-list-pane-meta', text: item.meta }));
      }
      node.appendChild(text);
      if (item.badges && item.badges.length) {
        var badges = util.el('span', { className: 'ui-list-pane-badges' });
        for (var b = 0; b < item.badges.length; b++) {
          var badge = item.badges[b];
          if (badge && badge.nodeType) {
            badges.appendChild(badge);
          } else if (badge && typeof badge === 'object' && badge.kind) {
            badges.appendChild(App.ui.badge({ text: badge.text, kind: badge.kind, title: badge.title }));
          } else {
            var plain = badge && typeof badge === 'object' ? badge.text : badge;
            badges.appendChild(util.el('span', { className: 'ui-list-pane-badge', text: String(plain) }));
          }
        }
        node.appendChild(badges);
      }
      if (item.count !== undefined && item.count !== null && item.count !== '') {
        node.appendChild(util.el('span', { className: 'ui-list-pane-count', text: String(item.count) }));
      }
      if (item.testid) node.setAttribute('data-testid', item.testid);
      return node;
    }

    // Show/hide rows for the filter, then re-derive selection and the tab
    // stop. Rows are never rebuilt here, so focus survives typing.
    function applyView() {
      var anyVisible = false;
      var firstVisible = null;
      var selectedRow = null;
      var i;
      for (i = 0; i < entries.length; i++) {
        var entry = entries[i];
        var visible = !query || predicate(entry.item, query);
        entry.li.hidden = !visible;
        if (visible) {
          anyVisible = true;
          if (!firstVisible) firstVisible = entry.row;
        }
        if (entry.item.id === selectedId) {
          entry.row.setAttribute('aria-current', 'page');
          if (visible) selectedRow = entry.row;
        } else {
          entry.row.removeAttribute('aria-current');
        }
      }
      for (i = 0; i < groupNodes.length; i++) {
        var group = groupNodes[i];
        var groupVisible = false;
        for (var k = 0; k < group.lis.length; k++) {
          if (!group.lis[k].hidden) groupVisible = true;
        }
        group.node.hidden = !groupVisible;
      }
      var stop = selectedRow || firstVisible;
      for (i = 0; i < entries.length; i++) {
        entries[i].row.setAttribute('tabindex', entries[i].row === stop ? '0' : '-1');
      }
      empty.hidden = anyVisible;
      body.hidden = !anyVisible;
    }

    function announce() {
      if (!query) {
        status.textContent = '';
        return;
      }
      var n = 0;
      for (var i = 0; i < entries.length; i++) {
        if (!entries[i].li.hidden) n++;
      }
      status.textContent = n === 0 ? opts.emptyText || 'No matches' : n === 1 ? '1 result' : n + ' results';
    }

    function setItems(input) {
      var groups = normalise(input);
      body.textContent = '';
      entries = [];
      groupNodes = [];
      for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        var ul = util.el('ul', { className: 'ui-list-pane-list' });
        var groupNode = ul;
        if (group.label !== null) {
          var capId = util.uid('lp-cap');
          ul.setAttribute('aria-labelledby', capId);
          groupNode = util.el('div', { className: 'ui-list-pane-group' }, [
            util.el('div', { className: 'ui-list-pane-caption', id: capId, text: group.label }),
            ul
          ]);
        } else {
          ul.setAttribute('aria-labelledby', titleId);
        }
        var lis = [];
        for (var n = 0; n < group.items.length; n++) {
          var item = group.items[n];
          var row = buildRow(item);
          var li = util.el('li', null, [row]);
          ul.appendChild(li);
          lis.push(li);
          entries.push({ item: item, li: li, row: row });
        }
        body.appendChild(groupNode);
        groupNodes.push({ node: groupNode, lis: lis });
      }
      applyView();
    }

    function setSelected(id) {
      var known = false;
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].item.id === id) known = true;
      }
      selectedId = known ? id : null;
      applyView();
    }

    function focusSelected() {
      var row = body.querySelector(ROW_SELECTOR + '[tabindex="0"]') || body.querySelector(ROW_SELECTOR);
      if (row) row.focus();
    }

    function destroy() {
      unbind();
      body.textContent = '';
      entries = [];
      groupNodes = [];
    }

    setItems(opts.items || opts.groups || []);
    return { el: root, setItems: setItems, setSelected: setSelected, focusSelected: focusSelected, destroy: destroy };
  };
})();
