// App.chat.drawerParts -- pure DOM builders for the agent drawer's Routines and Notes groups
// (split out of agent-drawer.js, M33 F1 L7, to keep the module under the 800-line rule). No
// state: the drawer passes its data in. Every text goes through textContent (el's `text`) and
// `title`, never an HTML sink.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  function arr(v) {
    return Array.isArray(v) ? v : [];
  }

  // M33 F1 L7: "Tue 9:00 AM" / "Today 9:00 AM" / "Oct 30 9:00 AM" in the operator zone,
  // through App.time only.
  var WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function whenLabel(iso) {
    var d = new Date(iso);
    if (!iso || isNaN(d.getTime())) return '';
    var diff = App.time.dayNumber(d) - App.time.dayNumber(new Date());
    var p = App.time.parts(d);
    var day = diff === 0 ? 'Today' : Math.abs(diff) <= 6 ? WEEKDAYS[p.weekday] : MONTHS[p.month] + ' ' + p.day;
    return day + ' ' + App.time.formatClock(d);
  }

  function routineMeta(r) {
    if (r.finished_at) return 'Done';
    if (!r.enabled) return 'Off';
    return r.next_run_at ? 'Next ' + whenLabel(r.next_run_at) : '';
  }

  // The Routines group: read-only, A-Z by name; names through textContent only.
  function routinesGroup(routinesState) {
    var box = el('div', { className: 'chat-drawer-group', dataset: { group: 'routines' } }, [
      el('h4', { className: 'chat-drawer-group-label', text: 'Routines' })
    ]);
    if (routinesState.status !== 'ok') {
      box.appendChild(el('p', {
        className: 'chat-drawer-none',
        text: routinesState.status === 'error' ? 'Couldn\'t load' : 'Loading…'
      }));
      return box;
    }
    var rows = arr(routinesState.value).filter(function (r) { return r && r.name !== undefined; });
    if (!rows.length) {
      box.appendChild(el('p', { className: 'chat-drawer-none', text: 'None' }));
      return box;
    }
    rows = rows.slice().sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
    var ul = el('ul', { className: 'chat-drawer-list' });
    ul.setAttribute('data-testid', 'chat-drawer-routines');
    for (var i = 0; i < rows.length; i++) {
      var li = el('li', null, [
        el('span', { className: 'chat-drawer-item-name', text: String(rows[i].name) }),
        el('span', { className: 'chat-drawer-item-meta', text: routineMeta(rows[i]) })
      ]);
      li.setAttribute('title', String(rows[i].name));
      li.setAttribute('data-testid', 'chat-drawer-routine-item');
      ul.appendChild(li);
    }
    box.appendChild(ul);
    return box;
  }

  function noteOriginLine(n) {
    if (n.origin_kind === 'other') return 'Outside a chat';
    if (n.origin_kind === 'connector') {
      var who = n.origin_peer_name || n.origin_peer_id || '';
      return String(n.origin_platform || 'connector') + (who ? ' · ' + who : '');
    }
    return String(n.origin_label || 'Untitled chat') + (n.origin_exists ? '' : ' (chat deleted)');
  }

  function noteItem(n) {
    var headKids = [];
    if (n.untrusted) {
      var flag = App.ui.noteFlag({ sources: arr(n.untrusted_sources) });
      flag.setAttribute('data-testid', 'chat-drawer-notes-flag');
      headKids.push(flag);
    }
    headKids.push(el('span', { className: 'chat-drawer-note-text', text: String(n.text) }));
    var li = el('li', null, [
      el('div', { className: 'chat-drawer-note-head' }, headKids),
      el('div', { className: 'chat-drawer-note-origin', text: noteOriginLine(n) })
    ]);
    li.setAttribute('title', String(n.text));
    li.setAttribute('data-testid', 'chat-drawer-notes-item');
    li.setAttribute('data-id', n.id);
    li.setAttribute('data-number', String(n.number));
    return li;
  }

  function noteList(rows, pending) {
    var ul = el('ul', { className: 'chat-drawer-notes' + (pending ? ' chat-drawer-notes--pending' : '') });
    ul.setAttribute('role', 'list');
    if (pending) ul.setAttribute('data-testid', 'chat-drawer-notes-pending');
    else ul.setAttribute('data-testid', 'chat-drawer-notes');
    for (var i = 0; i < rows.length; i++) ul.appendChild(noteItem(rows[i]));
    return ul;
  }


  window.App.chat.drawerParts = {
    whenLabel: whenLabel,
    routineMeta: routineMeta,
    routinesGroup: routinesGroup,
    noteOriginLine: noteOriginLine,
    noteItem: noteItem,
    noteList: noteList
  };
})();
