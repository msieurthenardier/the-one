(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var ROW_SELECTOR = 'li:not([hidden]) > .ui-list-pane-row';
  var ROW_STYLES = ['agents', 'library'];

  function defaultPredicate(item, query) {
    var needle = query.toLowerCase();
    var hay = (item.label || '') + ' ' + (item.meta || '');
    return hay.toLowerCase().indexOf(needle) !== -1;
  }

  // Normalise setItems input (a flat item array, or an array of groups) to
  // [{id, label, emptyText, items}] and validate it BEFORE any DOM is touched.
  function normalise(input) {
    var list = input || [];
    var isGroups = list.length > 0 && Array.isArray(list[0].items);
    var groups = [];
    var seen = {};
    var seenGroups = {};
    var i;
    var j;
    if (isGroups) {
      for (i = 0; i < list.length; i++) {
        if (!Array.isArray(list[i].items)) {
          throw new Error('App.ui.listPane: cannot mix groups and plain items');
        }
        var gid = list[i].id;
        var hasId = gid !== undefined && gid !== null && gid !== '';
        if (hasId && Object.prototype.hasOwnProperty.call(seenGroups, gid)) {
          throw new Error('listPane duplicate group id ' + gid);
        }
        if (hasId) seenGroups[gid] = true;
        groups.push({
          id: hasId ? gid : null,
          label: list[i].label || '',
          emptyText: list[i].emptyText || '',
          items: list[i].items
        });
      }
    } else {
      groups.push({ id: null, label: null, emptyText: '', items: list });
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
        if (item.lead !== undefined && item.lead !== null && !item.lead.nodeType) {
          throw new Error('listPane item ' + item.id + ': lead must be a node');
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
  // setSelected(id), focusSelected(), scrollToSelected(), scrollToGroup(id),
  // getItems(), destroy()}. A navigation list (DD14).
  //   title (required, the h2), count (true: a "{shown} of {total}" span after
  //   the title, empty while there are no items), intro (a muted paragraph
  //   under the title row), actions (array of elements, pushed right), filter
  //   ({label, placeholder, predicate(item, query), plus a nested test id
  //   option placed on the filter input}), emptyText (a string, or a
  //   function(query) -> string called with the trimmed filter query, so the
  //   empty state and the filter status can name the query; '' when no query
  //   is active), items | groups,
  //   selectedId, density (regular | compact), rowStyle ('agents' | 'library':
  //   the reference row geometry with a 1px rest border that the selection
  //   colours; it wins over density, and without it rows keep the inset-ring
  //   selection), and the test id option on the root section.
  //   group: {id, label, emptyText, items}. id is optional and, when given,
  //   unique across the groups (a duplicate throws); scrollToGroup(id) finds
  //   the group by it. A group with no items and an emptyText shows its
  //   caption and that muted line (never a focusable row) while no filter
  //   query is active; a group whose rows are all filtered out hides.
  //   item: {id, label, meta, nameSuffix, href | onSelect, badges[], count,
  //   icon, lead, and a per-item test id option placed on the row}. lead is a
  //   caller-built node (a provider dot) placed directly before the text, in a
  //   .ui-list-pane-lead wrapper that does not shrink; it is not part of the
  //   name, so a decorative lead is aria-hidden by its caller. nameSuffix is
  //   appended to the row's accessible name by a visually-hidden span (never
  //   aria-label, which would replace the visible name); it is a separate
  //   text run, so callers include their own separators: a leading one, and a
  //   trailing one when meta follows (", Claude Max,", so the name reads
  //   "label, Claude Max, meta"). A badges[] entry is a node, a string, or
  //   {text, kind, title}: with a kind it renders through App.ui.badge,
  //   without one as a neutral muted span. count is trailing text (never
  //   colour-only meaning). The empty element is App.ui.emptyState.
  // Rows are links when href is given, else buttons. The selected row carries
  // aria-current: "page" on a link row (it opens a page), "true" on a button
  // row (an onSelect row selects in place; the flight-end review). Keyboard
  // handling lives on the list body only (Tab enters at the selected row,
  // else the first visible row; arrows/Home/End roving). No document-level
  // listener is ever installed (DD1).
  // setItems rebuilds every row but keeps the filter query and the body's
  // scroll position, and when a row had focus it restores focus (and the tab
  // stop) to the row with the same id, else the selected row, else the first
  // visible row (M25 F3 DD10: store notifications call setItems mid-roving).
  // A filter keystroke never rebuilds: one pass over the rows that writes only
  // the attributes that change (M25 F3 L3, the 60-agent filter gate).
  // scrollToGroup(id) brings the group with that id into view within the body
  // scroller only (its top at the body's top, unless it is already wholly
  // visible); an unknown id, or a hidden group, is a no-op (M25 F3 L4a).
  App.ui.listPane = function (opts) {
    opts = opts || {};
    if (!opts.title) throw new Error('App.ui.listPane: title is required');
    if (opts.rowStyle && ROW_STYLES.indexOf(opts.rowStyle) === -1) {
      throw new Error('App.ui.listPane: unknown rowStyle "' + opts.rowStyle + '"');
    }
    var util = App.ui.util;
    var predicate = (opts.filter && opts.filter.predicate) || defaultPredicate;
    var titleId = util.uid('lp-title');
    var selectedId = opts.selectedId === undefined ? null : opts.selectedId;
    var query = '';
    var entries = [];
    var groupNodes = [];
    var density = opts.density === 'compact' ? 'compact' : 'regular';
    var filterInput = null;
    var countEl = null;
    var lastShown = 0; // rows the last applyView left visible (for announce)

    var title = util.el('h2', { className: 'ui-list-pane-title', id: titleId, text: opts.title });
    var header = util.el('header', { className: 'ui-list-pane-header' }, [title]);
    if (opts.count) {
      countEl = util.el('span', { className: 'ui-list-pane-total' });
      header.appendChild(countEl);
    }
    if (opts.actions && opts.actions.length) {
      header.appendChild(util.el('div', { className: 'ui-list-pane-actions' }, opts.actions));
    }
    var rootClass = 'ui-list-pane ui-list-pane-' + density;
    if (opts.rowStyle) rootClass += ' ui-list-pane-styled ui-list-pane-style-' + opts.rowStyle;
    var root = util.el('section', { className: rootClass, 'aria-labelledby': titleId }, [header]);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    if (opts.intro) root.appendChild(util.el('p', { className: 'ui-list-pane-intro', text: opts.intro }));

    if (opts.filter) {
      filterInput = App.ui.textInput({
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
    // emptyText may be a function of the trimmed query (M25 F3 L3): the empty
    // title is then re-derived on every view change.
    function emptyTextFor(q) {
      return typeof opts.emptyText === 'function' ? opts.emptyText(q) : opts.emptyText;
    }
    var empty = App.ui.emptyState({ title: emptyTextFor('') || 'Nothing to show' });
    var emptyTitle = empty.querySelector('.ui-empty-title');
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
      if (item.lead) {
        node.appendChild(util.el('span', { className: 'ui-list-pane-lead' }, [item.lead]));
      }
      var text = util.el('span', { className: 'ui-list-pane-text' }, [
        util.el('span', { className: 'ui-list-pane-label', text: item.label })
      ]);
      if (item.nameSuffix) {
        text.appendChild(util.el('span', { className: 'visually-hidden', text: item.nameSuffix }));
      }
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

    // Writes only what changes (M25 F3 L3): a filter keystroke over a long
    // list should cost about one predicate call per row, not a DOM write.
    function setStop(stop) {
      for (var i = 0; i < entries.length; i++) {
        var want = entries[i].row === stop ? '0' : '-1';
        if (entries[i].row.getAttribute('tabindex') !== want) entries[i].row.setAttribute('tabindex', want);
      }
    }

    // Show/hide rows for the filter, then re-derive selection, the tab stop
    // and the count. Rows are never rebuilt here, so focus survives typing.
    // One pass over the rows (M25 F3 L3): per-group visibility is counted in
    // the same loop, so a keystroke costs one predicate call per row.
    function applyView() {
      var shown = 0;
      var anyGroupLine = false;
      var firstVisible = null;
      var selectedRow = null;
      var groupShown = [];
      var i;
      for (i = 0; i < groupNodes.length; i++) groupShown.push(0);
      for (i = 0; i < entries.length; i++) {
        var entry = entries[i];
        var visible = !query || predicate(entry.item, query);
        // entry.hidden / entry.current mirror the row's hidden and
        // aria-current (only this file writes them), so no DOM read per row.
        if (entry.hidden === visible) {
          entry.hidden = !visible;
          entry.li.hidden = !visible;
        }
        if (visible) {
          shown++;
          groupShown[entry.group]++;
          if (!firstVisible) firstVisible = entry.row;
        }
        var current = entry.item.id === selectedId;
        if (current !== entry.current) {
          entry.current = current;
          if (current) entry.row.setAttribute('aria-current', entry.item.href ? 'page' : 'true');
          else entry.row.removeAttribute('aria-current');
        }
        if (current && visible) selectedRow = entry.row;
      }
      for (i = 0; i < groupNodes.length; i++) {
        var group = groupNodes[i];
        var lineShown = group.emptyLine && !query;
        if (lineShown) anyGroupLine = true;
        var groupVisible = lineShown || groupShown[i] > 0;
        if (group.node.hidden === groupVisible) group.node.hidden = !groupVisible;
      }
      lastShown = shown;
      setStop(selectedRow || firstVisible);
      if (countEl) {
        var countText = entries.length ? shown + ' of ' + entries.length : '';
        if (countEl.textContent !== countText) countEl.textContent = countText;
      }
      if (typeof opts.emptyText === 'function') {
        var emptyTitleText = emptyTextFor(query.trim()) || 'Nothing to show';
        if (emptyTitle.textContent !== emptyTitleText) emptyTitle.textContent = emptyTitleText;
      }
      empty.hidden = shown > 0 || anyGroupLine;
      body.hidden = !empty.hidden;
    }

    function announce() {
      if (!query) {
        status.textContent = '';
        return;
      }
      var n = lastShown;
      status.textContent = n === 0 ? emptyTextFor(query.trim()) || 'No matches' : n === 1 ? '1 result' : n + ' results';
    }

    // The entry whose row holds focus (the row itself or a node inside it).
    function focusedEntry() {
      var active = document.activeElement;
      if (!active || !body.contains(active)) return null;
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].row === active || entries[i].row.contains(active)) return entries[i];
      }
      return null;
    }

    // After a rebuild that removed the focused row: focus (and the tab stop)
    // go to the row with the same id when it is still visible, else to the
    // stop applyView chose (the selected row, else the first visible row),
    // else to the filter when no row is visible, so focus never drops to body.
    function restoreFocus(id) {
      var target = null;
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].item.id === id && !entries[i].li.hidden) target = entries[i].row;
      }
      if (!target) target = body.querySelector(ROW_SELECTOR + '[tabindex="0"]');
      if (target) {
        setStop(target);
        target.focus();
      } else if (filterInput) {
        filterInput.focus();
      }
    }

    function setItems(input) {
      var groups = normalise(input);
      // Read before the rebuild: removing the focused node moves focus to
      // <body> at once, so the restore below must also run synchronously.
      var focused = focusedEntry();
      var scrollTop = body.scrollTop;
      body.textContent = '';
      entries = [];
      groupNodes = [];
      for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        var ul = util.el('ul', { className: 'ui-list-pane-list' });
        var groupNode = ul;
        var emptyLine = false;
        if (group.label !== null) {
          var capId = util.uid('lp-cap');
          var caption = util.el('div', { className: 'ui-list-pane-caption', id: capId, text: group.label });
          if (!group.items.length && group.emptyText) {
            emptyLine = true;
            groupNode = util.el('div', { className: 'ui-list-pane-group' }, [
              caption,
              util.el('p', { className: 'ui-list-pane-group-empty', text: group.emptyText })
            ]);
          } else {
            ul.setAttribute('aria-labelledby', capId);
            groupNode = util.el('div', { className: 'ui-list-pane-group' }, [caption, ul]);
          }
        } else {
          ul.setAttribute('aria-labelledby', titleId);
        }
        for (var n = 0; n < group.items.length; n++) {
          var item = group.items[n];
          var row = buildRow(item);
          var li = util.el('li', null, [row]);
          ul.appendChild(li);
          entries.push({ item: item, li: li, row: row, group: g, hidden: false, current: false });
        }
        body.appendChild(groupNode);
        groupNodes.push({ id: group.id, node: groupNode, emptyLine: emptyLine });
      }
      applyView();
      body.scrollTop = scrollTop;
      if (focused) restoreFocus(focused.item.id);
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

    // Scroll the selected row into view within the body scroller (A26). A
    // no-op when nothing is selected or the filter hides the selected row.
    function scrollToSelected() {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].item.id === selectedId && !entries[i].li.hidden) {
          entries[i].row.scrollIntoView({ block: 'nearest' });
          return;
        }
      }
    }

    // Scroll the group with this id into view within the body scroller only
    // (never an ancestor): its top meets the body's top unless the group is
    // already wholly visible. A no-op for an unknown id or a hidden group.
    function scrollToGroup(id) {
      if (id === undefined || id === null || id === '') return;
      var node = null;
      for (var i = 0; i < groupNodes.length; i++) {
        if (groupNodes[i].id === id) node = groupNodes[i].node;
      }
      if (!node || node.hidden || body.hidden) return;
      var bodyBox = body.getBoundingClientRect();
      var box = node.getBoundingClientRect();
      if (box.top >= bodyBox.top - 0.5 && box.bottom <= bodyBox.bottom + 0.5) return;
      body.scrollTop += box.top - bodyBox.top;
    }

    function getItems() {
      var out = [];
      for (var i = 0; i < entries.length; i++) out.push(entries[i].item);
      return out;
    }

    function destroy() {
      unbind();
      body.textContent = '';
      entries = [];
      groupNodes = [];
    }

    setItems(opts.items || opts.groups || []);
    return {
      el: root,
      setItems: setItems,
      setSelected: setSelected,
      focusSelected: focusSelected,
      scrollToSelected: scrollToSelected,
      scrollToGroup: scrollToGroup,
      getItems: getItems,
      destroy: destroy
    };
  };
})();
