// App.chat.chatsList -- the Chats list column (M25 F4 leg 4a, flight DD5,
// reference spec 5.1).
//
// An App.ui.listPane titled "Chats" (testid chats-list, rowStyle 'chats', no
// filter) whose header block is the full-width New chat button
// (chats-new-btn). Its rows are the cross-agent history, grouped by recency:
// Today, Yesterday, Last 7 days, Last 30 days and Older (sentence case, A28;
// empty groups are not shown), each newest first. Built with DOM APIs only.
//
// Recency, in LOCAL time, by `updated_at || created_at` (whole calendar days
// between that day and today):
//   day 0 (or a future date)  Today         time h:mm AM/PM (12-hour)
//   day 1                     Yesterday     time Mon (short weekday)
//   days 2-6                  Last 7 days   time Mon
//   days 7-29                 Last 30 days  time Sep 12 (short month, day)
//   day 30 and older          Older         time Sep 12
//   missing or invalid        Older         time ''
// Day 7 goes to Last 30 days, so a weekday label is never ambiguous with
// today's weekday. Times are formatted by hand (never the locale formatters; the clock
// is App.time.formatClock), so
// every engine and locale draws the same English labels.
//
// A row: label = the title, time as above, meta = the agent name ("Default
// agent" for a null agent_name), a connector row's platform as the neutral
// library badge pill (App.ui.badge kind 'unknown'; no class is built from the value), href =
// #chats/{id}, dataset {id}, testid chat-row, and a delete row action (the
// trash icon, "Delete chat: {title}", testid chat-row-delete) that the chat
// area drives through App.ui.confirm(li, ...).
//
// The pending row (a chat picked but not sent yet, DD1): id '__pending__',
// "New chat", time "now", the agent as meta, href #chats/~new/{agent} (so it
// is a LINK and its selection is aria-current="page"), dataset {pending:
// 'true'} with no data-id, and no action. It sits at the top of Today.
//
// API:
//   App.chat.chatsList.create({onNew(btn), onDelete(id, li, btn, title)})
//     -> {el, newButton, render(rows, view), setNewDisabled(bool), destroy()}
//     view: {pending: {agent} | null, selectedId: id | null}
//   App.chat.chatsList.groups(rows, view, onDelete, now) -> the listPane groups
//   App.chat.chatsList.bucketFor(row, now) -> 'today' | 'yesterday' | 'last7'
//     | 'last30' | 'older'
//   App.chat.chatsList.timeFor(row, now) -> the row's time string
//   App.chat.chatsList.platformName(slug) -> 'Discord' (the display name; title-cased if unknown)
//   App.chat.chatsList.PENDING_ID, GROUPS
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var PENDING_ID = '__pending__';
  var GROUPS = [
    { id: 'today', label: 'Today' },
    { id: 'yesterday', label: 'Yesterday' },
    { id: 'last7', label: 'Last 7 days' },
    { id: 'last30', label: 'Last 30 days' },
    { id: 'older', label: 'Older' }
  ];
  var WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  // The row's activity date (updated_at, else created_at), or null.
  function dateOf(row) {
    var ts = row && (row.updated_at || row.created_at);
    if (!ts) return null;
    var d = new Date(ts);
    return isNaN(d.getTime()) ? null : d;
  }

  // Whole calendar days, in the operator's zone, from d's day to now's day.
  function daysAgo(d, now) {
    return window.App.time.dayNumber(now) - window.App.time.dayNumber(d);
  }

  function bucketOf(d, now) {
    if (!d) return 'older';
    var n = daysAgo(d, now);
    if (n <= 0) return 'today';
    if (n === 1) return 'yesterday';
    if (n <= 6) return 'last7';
    if (n <= 29) return 'last30';
    return 'older';
  }

  function timeOf(d, bucket) {
    if (!d) return '';
    if (bucket === 'today') return window.App.time.formatClock(d);
    if (bucket === 'yesterday' || bucket === 'last7') return WEEKDAYS[window.App.time.parts(d).weekday];
    var p = window.App.time.parts(d);
    return MONTHS[p.month] + ' ' + p.day;
  }

  function bucketFor(row, now) {
    return bucketOf(dateOf(row), now || new Date());
  }

  function timeFor(row, now) {
    var d = dateOf(row);
    return timeOf(d, bucketOf(d, now || new Date()));
  }

  // The one platform display-name table of the chat area (A16); an unknown slug is title-cased.
  var PLATFORM_NAMES = { discord: 'Discord', telegram: 'Telegram', slack: 'Slack', stub: 'Stub' };

  function platformName(slug) {
    var s = String(slug);
    var key = s.toLowerCase();
    if (Object.prototype.hasOwnProperty.call(PLATFORM_NAMES, key)) return PLATFORM_NAMES[key];
    return s.replace(/(^|[\s_-])([a-z])/g, function (m, sep, ch) { return sep + ch.toUpperCase(); });
  }

  function sessionItem(row, d, bucket, onDelete) {
    var title = row.title || 'Untitled chat';
    var item = {
      id: row.id,
      label: title,
      time: timeOf(d, bucket),
      meta: row.agent_name || 'Default agent',
      href: App.router.href({ destination: 'chats', id: row.id }),
      dataset: { id: row.id },
      testid: 'chat-row',
      action: {
        label: 'Delete chat: ' + title,
        icon: 'trash',
        testid: 'chat-row-delete',
        onClick: function (current, btn, li) {
          if (typeof onDelete === 'function') onDelete(current.id, li, btn, title);
        }
      }
    };
    // A connector session: its platform as the neutral library badge pill.
    if (row.platform) item.badges = [{ text: platformName(row.platform), kind: 'unknown' }];
    return item;
  }

  function pendingItem(pending) {
    return {
      id: PENDING_ID,
      label: 'New chat',
      time: 'now',
      meta: pending.agent || '',
      href: App.router.href({ destination: 'chats', create: true, agent: pending.agent }),
      dataset: { pending: 'true' },
      testid: 'chat-row'
    };
  }

  // rows (the store's `sessions`) + view -> listPane groups, newest first in
  // each group, empty groups dropped, the pending row first in Today.
  function groups(rows, view, onDelete, now) {
    now = now || new Date();
    view = view || {};
    var byBucket = {};
    var i;
    for (i = 0; i < GROUPS.length; i++) byBucket[GROUPS[i].id] = [];
    var list = Array.isArray(rows) ? rows : [];
    for (i = 0; i < list.length; i++) {
      var row = list[i];
      if (!row || row.id === undefined || row.id === null || row.id === '') continue;
      var d = dateOf(row);
      var bucket = bucketOf(d, now);
      byBucket[bucket].push({ row: row, d: d, bucket: bucket, t: d ? d.getTime() : -Infinity });
    }
    var out = [];
    for (i = 0; i < GROUPS.length; i++) {
      var g = GROUPS[i];
      var entries = byBucket[g.id];
      // Array.prototype.sort is stable: equal times keep the list's order.
      entries.sort(function (a, b) {
        if (a.t === b.t) return 0;
        return a.t > b.t ? -1 : 1;
      });
      var items = [];
      if (g.id === 'today' && view.pending) items.push(pendingItem(view.pending));
      for (var k = 0; k < entries.length; k++) {
        items.push(sessionItem(entries[k].row, entries[k].d, entries[k].bucket, onDelete));
      }
      if (items.length) out.push({ id: g.id, label: g.label, items: items });
    }
    return out;
  }

  function create(opts) {
    opts = opts || {};
    var newButton = App.ui.button({
      label: 'New chat',
      variant: 'primary',
      size: 'lg',
      icon: 'square-pen',
      testid: 'chats-new-btn',
      onClick: function () {
        if (typeof opts.onNew === 'function') opts.onNew(newButton);
      }
    });
    var pane = App.ui.listPane({
      title: 'Chats',
      rowStyle: 'chats',
      block: newButton,
      emptyText: 'No conversations yet.',
      testid: 'chats-list',
      items: []
    });

    function render(rows, view) {
      view = view || {};
      pane.setItems(groups(rows, view, opts.onDelete));
      pane.setSelected(view.selectedId === undefined ? null : view.selectedId);
    }

    function setNewDisabled(disabled) {
      newButton.disabled = !!disabled;
    }

    return {
      el: pane.el,
      newButton: newButton,
      render: render,
      setNewDisabled: setNewDisabled,
      destroy: pane.destroy
    };
  }

  window.App.chat.chatsList = {
    PENDING_ID: PENDING_ID,
    GROUPS: GROUPS,
    bucketFor: bucketFor,
    timeFor: timeFor,
    platformName: platformName,
    groups: groups,
    create: create
  };
})();
