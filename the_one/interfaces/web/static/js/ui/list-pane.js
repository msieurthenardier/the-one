(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var ROW_SELECTOR = 'li:not([hidden]) > .ui-list-pane-row';
  var ROW_STYLES = ['agents', 'library', 'chats'];
  var ACTION_CLASS = 'ui-list-pane-action';

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
        if (item.action !== undefined && item.action !== null) {
          var act = item.action;
          if (!act.label || !act.icon || typeof act.onClick !== 'function') {
            throw new Error('listPane item ' + item.id + ': action needs label, icon and onClick');
          }
        }
        if (item.dataset !== undefined && item.dataset !== null &&
            (typeof item.dataset !== 'object' || Array.isArray(item.dataset))) {
          throw new Error('listPane item ' + item.id + ': dataset must be a plain object');
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
  // setQuery(q), getItems(), destroy()}. A navigation list (DD14).
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
  //
  // M25 F4 L1 (DD5, DD14) additions:
  //   block: a caller node inserted directly AFTER the <header> (outside it,
  //     so the header's children are unchanged), in a .ui-list-pane-block
  //     wrapper (the Chats list's New chat button).
  //   rowStyle 'chats': a two-line row. Line 1 is the label (ellipsis) with
  //     the item's `time` string pushed to the end; line 2 is the meta, then
  //     the badges. icon, lead and count are not drawn in this style, and
  //     `time` is drawn only in it.
  //   item.dataset: a plain object set as data-* on the row element.
  //   The label span always carries data-confirm-title, so
  //     App.ui.confirm(li) swaps the label's text.
  //   item.action {label, icon, testid, onClick(item, actionEl, li)}: a
  //     sibling <button type=button class="ui-list-pane-action"> after the
  //     row inside its <li> (never a .ui-list-pane-row), icon only, named by
  //     aria-label = label. Hidden with display:none until li:hover or
  //     li:focus-within (not visibility/opacity, which would break Tab
  //     reach). onClick reads the entry's CURRENT item at click time. An
  //     item without an action has no button.
  //   Tab policy: only the action of the roving tab-stop row has tabindex 0
  //     (every other action -1), so Tab goes stop row -> its action -> out of
  //     the list. setStop() re-derives the actions' tabindex, and so does a
  //     focusin on the body (rovingFocus rewrites only the rows' tabindex).
  //     Shift+Tab from after the list lands on the stop ROW: its action is
  //     display:none until the li has focus, so it is reached forward only
  //     (the legacy chat list behaved the same).
  //     On an action, ArrowUp/ArrowDown move to the previous/next visible
  //     row (clamped), Home/End to the first/last row.
  //   Focus across setItems: a focused ACTION restores to the same item's
  //     action; when that item is gone (the delete case) focus goes to the
  //     neighbouring row -- the next visible row in the old order, else the
  //     previous one -- and becomes the stop. A focused ROW keeps the rule
  //     above unchanged (same id, else selected, else first).
  //
  // M31 F6 L10b: item.activity, 'working' | 'new' (rowStyle 'chats' only; ignored and
  //   unrendered in the other styles). Every chats row reserves a fixed 12px
  //   .ui-list-pane-activity slot beside the time, so nothing shifts when it fills: 'working'
  //   adds --working (a spinning ring, a static gapped ring under reduced motion), 'new' adds
  //   --new (a filled dot). The slot is aria-hidden; the state is a separate visually hidden
  //   run after nameSuffix: ", Working" or ", New reply". setItems patches the slot in place
  //   when it reuses an armed row.
  //
  // M25 F4 L6 (DD14): setQuery(q) sets the filter's value and query and
  //   applies the view (rows shown or hidden, the selection, the tab stop and
  //   the count re-derived; rows never rebuilt, so focus survives). It is
  //   SILENT: no live announcement (the polite status region is cleared, not
  //   written, so a stale "N results" never lingers). A no-op without a
  //   filter. App.studio.clearAgentFilter calls it with ''.
  //   Armed rows: App.ui.confirm arms by adding .confirm-delete to the
  //     <li> and swapping its [data-confirm-title] child's text (ui/confirm.js).
  //     setItems REUSES an armed <li> (row and action nodes, so the armed
  //     title and the revert timer survive) for the same item id, updating
  //     the entry's item to the new one; it still goes through the view pass
  //     (aria-current, tabindex, hidden). Its label may be stale until it
  //     disarms (at most the 3s revert window). If the armed item is absent
  //     from the new list its <li> is dropped; ui/confirm.js's timer then runs
  //     on a detached node, which is harmless. The next setItems after it
  //     disarms rebuilds it normally.
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
    if (opts.block !== undefined && opts.block !== null) {
      if (!opts.block.nodeType) throw new Error('App.ui.listPane: block must be a node');
      root.appendChild(util.el('div', { className: 'ui-list-pane-block' }, [opts.block]));
    }
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
    body.addEventListener('focusin', onBodyFocusin);
    body.addEventListener('keydown', onBodyKeydown);

    function buildBadges(item) {
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
      return badges;
    }

    // M31 F6 L10b: item.activity ('working' | 'new' | none, rowStyle 'chats' only; ignored in
    // the other styles) -> the slot's modifier class and the row name's separate text run.
    var ACTIVITY_TEXT = { working: ', Working', 'new': ', New reply' };
    function patchActivity(entry) {
      if (!entry.activityMark) return;
      var a = entry.item.activity;
      if (a !== 'working' && a !== 'new') a = '';
      var cls = 'ui-list-pane-activity' + (a ? ' ui-list-pane-activity--' + a : '');
      if (entry.activityMark.className !== cls) entry.activityMark.className = cls;
      var text = a ? ACTIVITY_TEXT[a] : '';
      if (entry.activityText.textContent !== text) entry.activityText.textContent = text;
    }

    // The row element for an entry. The click handler reads entry.item at
    // click time (an armed row is reused with the entry's item replaced).
    function buildRow(entry) {
      var item = entry.item;
      var node;
      if (item.href) {
        node = util.el('a', { className: 'ui-list-pane-row', href: item.href });
      } else {
        node = util.el('button', { className: 'ui-list-pane-row', type: 'button' });
      }
      if (typeof item.onSelect === 'function') {
        node.addEventListener('click', function () {
          var current = entry.item;
          if (typeof current.onSelect === 'function') current.onSelect(current);
        });
      }
      var label = util.el('span', { className: 'ui-list-pane-label', 'data-confirm-title': true, text: item.label });
      var suffix = item.nameSuffix ? util.el('span', { className: 'visually-hidden', text: item.nameSuffix }) : null;
      var hasBadges = item.badges && item.badges.length;
      if (opts.rowStyle === 'chats') {
        var hasTime = item.time !== undefined && item.time !== null && item.time !== '';
        // M31 F6 L10b: the activity slot (always present, so the row never shifts) and its
        // hidden name run, patched in place by patchActivity.
        entry.activityMark = util.el('span', { className: 'ui-list-pane-activity', 'aria-hidden': 'true' });
        entry.activityText = util.el('span', { className: 'visually-hidden' });
        patchActivity(entry);
        node.appendChild(util.el('span', { className: 'ui-list-pane-line' }, [
          label,
          suffix,
          entry.activityText,
          entry.activityMark,
          hasTime ? util.el('span', { className: 'ui-list-pane-time', text: String(item.time) }) : null
        ]));
        if (item.meta || hasBadges) {
          node.appendChild(util.el('span', { className: 'ui-list-pane-line' }, [
            item.meta ? util.el('span', { className: 'ui-list-pane-meta', text: item.meta }) : null,
            hasBadges ? buildBadges(item) : null
          ]));
        }
      } else {
        if (item.icon) {
          node.appendChild(util.el('span', { className: 'ui-list-pane-icon' }, [util.icon(item.icon)]));
        }
        if (item.lead) {
          node.appendChild(util.el('span', { className: 'ui-list-pane-lead' }, [item.lead]));
        }
        var text = util.el('span', { className: 'ui-list-pane-text' }, [label, suffix]);
        if (item.meta) {
          text.appendChild(util.el('span', { className: 'ui-list-pane-meta', text: item.meta }));
        }
        node.appendChild(text);
        if (hasBadges) node.appendChild(buildBadges(item));
        if (item.count !== undefined && item.count !== null && item.count !== '') {
          node.appendChild(util.el('span', { className: 'ui-list-pane-count', text: String(item.count) }));
        }
      }
      if (item.dataset) {
        for (var k in item.dataset) {
          if (Object.prototype.hasOwnProperty.call(item.dataset, k)) node.dataset[k] = item.dataset[k];
        }
      }
      if (item.testid) node.setAttribute('data-testid', item.testid);
      return node;
    }

    // The action button for an entry (null when its item has none). onClick
    // reads entry.item at click time, never a stale closure.
    function buildAction(entry) {
      var spec = entry.item.action;
      if (!spec) return null;
      var btn = util.el('button', {
        type: 'button',
        className: ACTION_CLASS,
        'aria-label': spec.label,
        tabindex: '-1'
      }, [util.icon(spec.icon)]);
      if (spec.testid) btn.setAttribute('data-testid', spec.testid);
      btn.addEventListener('click', function () {
        var current = entry.item;
        var act = current.action || spec;
        act.onClick(current, btn, entry.li);
      });
      return btn;
    }

    // A new entry (li, row and action) for an item in group g.
    function buildEntry(item, g) {
      var entry = { item: item, li: null, row: null, action: null, group: g, hidden: false, current: false };
      entry.row = buildRow(entry);
      entry.action = buildAction(entry);
      entry.li = util.el('li', { className: entry.action ? 'ui-list-pane-has-action' : null }, [entry.row, entry.action]);
      return entry;
    }

    // Writes only what changes (M25 F3 L3): a filter keystroke over a long
    // list should cost about one predicate call per row, not a DOM write.
    // The row and (DD5) its action share the stop: only the stop row's
    // action is tabbable.
    function setStop(stop) {
      for (var i = 0; i < entries.length; i++) {
        var want = entries[i].row === stop ? '0' : '-1';
        if (entries[i].row.getAttribute('tabindex') !== want) entries[i].row.setAttribute('tabindex', want);
        var action = entries[i].action;
        if (action && action.getAttribute('tabindex') !== want) action.setAttribute('tabindex', want);
      }
    }

    function entryOf(node) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].li === node || entries[i].li.contains(node)) return entries[i];
      }
      return null;
    }

    // rovingFocus rewrites only the rows' tabindex on arrow keys, and a
    // click can focus a non-stop row's action: re-derive the stop (rows and
    // actions) from wherever focus lands in the body.
    function onBodyFocusin(e) {
      var entry = entryOf(e.target);
      if (entry && !entry.hidden) setStop(entry.row);
    }

    // Arrow keys on an action (rovingFocus ignores a non-row target):
    // Up/Down to the previous/next visible row, clamped; Home/End to the
    // first/last visible row.
    function onBodyKeydown(e) {
      if (e.defaultPrevented || e.ctrlKey || e.altKey || e.metaKey) return;
      var target = e.target;
      if (!target || !target.classList || !target.classList.contains(ACTION_CLASS)) return;
      var key = e.key;
      if (key !== 'ArrowUp' && key !== 'ArrowDown' && key !== 'Home' && key !== 'End') return;
      var rows = Array.prototype.slice.call(body.querySelectorAll(ROW_SELECTOR));
      if (!rows.length) return;
      var entry = entryOf(target);
      var idx = entry ? rows.indexOf(entry.row) : -1;
      if (idx === -1) return;
      var next;
      if (key === 'Home') next = 0;
      else if (key === 'End') next = rows.length - 1;
      else if (key === 'ArrowDown') next = Math.min(idx + 1, rows.length - 1);
      else next = Math.max(idx - 1, 0);
      e.preventDefault();
      setStop(rows[next]);
      rows[next].focus();
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

    // Where focus is in the body: {entry, onAction, index (in the OLD
    // entries), ids (the old entries' item ids, in order)}, or null.
    function focusedEntry() {
      var active = document.activeElement;
      if (!active || !body.contains(active)) return null;
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].li.contains(active)) {
          var ids = [];
          for (var j = 0; j < entries.length; j++) ids.push(entries[j].item.id);
          return { entry: entries[i], onAction: active === entries[i].action, index: i, ids: ids };
        }
      }
      return null;
    }

    function visibleEntry(id) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].item.id === id && !entries[i].li.hidden) return entries[i];
      }
      return null;
    }

    function focusNode(node, stopRow) {
      setStop(stopRow);
      node.focus();
    }

    // An action is display:none until its li has :focus-within, so it cannot
    // take focus on its own: a transient class shows it for the focus() call,
    // after which :focus-within keeps it shown.
    function focusAction(entry) {
      setStop(entry.row);
      entry.li.classList.add('ui-list-pane-reveal');
      entry.action.focus();
      entry.li.classList.remove('ui-list-pane-reveal');
    }

    // After a rebuild. A focused ACTION goes back to the same item's action,
    // else (its item gone: the delete case) to the neighbouring row: the
    // next old item still visible, else the previous one. A focused ROW
    // goes to the row with the same id when it is still visible, else to
    // the stop applyView chose (the selected row, else the first visible
    // row). Either way, with no row visible focus goes to the filter, so it
    // never drops to <body>.
    function restoreFocus(focused) {
      var id = focused.entry.item.id;
      var same = visibleEntry(id);
      var target = null;
      if (focused.onAction) {
        if (same && same.action) {
          focusAction(same);
          return;
        }
        if (same) target = same.row;
        var k;
        for (k = focused.index + 1; !target && k < focused.ids.length; k++) {
          var after = visibleEntry(focused.ids[k]);
          if (after) target = after.row;
        }
        for (k = focused.index - 1; !target && k >= 0; k--) {
          var before = visibleEntry(focused.ids[k]);
          if (before) target = before.row;
        }
      } else if (same) {
        target = same.row;
      }
      if (!target) target = body.querySelector(ROW_SELECTOR + '[tabindex="0"]');
      if (target) {
        focusNode(target, target);
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
      // Armed rows (App.ui.confirm's .confirm-delete on the li) are
      // reused for their item id, never rebuilt (DD5).
      var armed = {};
      for (var a = 0; a < entries.length; a++) {
        if (entries[a].li.classList.contains('confirm-delete')) armed[entries[a].item.id] = entries[a];
      }
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
          var entry;
          if (Object.prototype.hasOwnProperty.call(armed, item.id)) {
            entry = armed[item.id];
            entry.item = item;
            entry.group = g;
            patchActivity(entry);
          } else {
            entry = buildEntry(item, g);
          }
          ul.appendChild(entry.li);
          entries.push(entry);
        }
        body.appendChild(groupNode);
        groupNodes.push({ id: group.id, node: groupNode, emptyLine: emptyLine });
      }
      applyView();
      body.scrollTop = scrollTop;
      if (focused) restoreFocus(focused);
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

    // Programmatic filter (M25 F4 L6): silent, unlike a keystroke.
    function setQuery(q) {
      if (!filterInput) return;
      var next = q === undefined || q === null ? '' : String(q);
      filterInput.value = next;
      query = next;
      applyView();
      status.textContent = '';
    }

    function getItems() {
      var out = [];
      for (var i = 0; i < entries.length; i++) out.push(entries[i].item);
      return out;
    }

    function destroy() {
      unbind();
      body.removeEventListener('focusin', onBodyFocusin);
      body.removeEventListener('keydown', onBodyKeydown);
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
      setQuery: setQuery,
      getItems: getItems,
      // The row elements in item order (hidden rows included unless visibleOnly), so a
      // consumer can move focus without naming the row class.
      rows: function (visibleOnly) {
        return Array.prototype.slice.call(root.querySelectorAll(
          visibleOnly ? ROW_SELECTOR : 'li > .ui-list-pane-row'));
      },
      destroy: destroy
    };
  };
})();
