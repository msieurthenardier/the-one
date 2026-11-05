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
      var headKids = [];
      if (rows[i].untrusted) {
        var flag = App.ui.noteFlag({ subject: 'routine', sources: arr(rows[i].untrusted_sources) });
        flag.setAttribute('data-testid', 'chat-drawer-routine-flag');
        headKids.push(flag);
      }
      headKids.push(el('span', { className: 'chat-drawer-item-name', text: String(rows[i].name) }));
      var li = el('li', null, [
        el('div', { className: 'chat-drawer-note-head' }, headKids),
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


  // Sortie 07 L05 (DD12): the "Needs attention" group, read-only, between the facts and
  // "What it can use". One sentence per tool-override notice (the notice's own message,
  // set as text) and one link to the agent's Tools tab. Null when there are none.
  function noticesGroup(agentName, notices) {
    var list = arr(notices);
    if (!list.length) return null;
    var ul = el('ul', { className: 'chat-drawer-list chat-drawer-notices-list' });
    ul.setAttribute('role', 'list');
    for (var i = 0; i < list.length; i++) {
      ul.appendChild(el('li', null, [
        el('span', { className: 'chat-drawer-item-name', text: String(list[i].message || '') })
      ]));
    }
    var link = el('a', {
      className: 'chat-drawer-notices-link',
      href: App.router.href({ destination: 'agents', id: agentName, tab: 'tools' }),
      text: 'Open the agent’s Tools tab'
    });
    link.setAttribute('data-testid', 'chat-drawer-notices-link');
    var box = el('div', { className: 'chat-drawer-group chat-drawer-notices' }, [
      el('h3', { className: 'chat-drawer-uses-title', text: 'Needs attention' }),
      ul,
      link
    ]);
    box.setAttribute('data-testid', 'chat-drawer-notices');
    return box;
  }

  // Sortie 10: the secrets an agent is granted, A-Z, as drawer list items (name only; a
  // granted id the store no longer has is skipped). Never reads a key or a value.
  function grantedSecrets(agent) {
    var peek = App.store.peek('secrets');
    var rows = peek.loaded ? peek.value : [];
    var out = [];
    var ids = arr(agent.secret_ids);
    for (var i = 0; i < ids.length; i++) {
      for (var j = 0; j < arr(rows).length; j++) {
        if (rows[j] && rows[j].id === ids[i]) out.push({ name: String(rows[j].name || rows[j].id) });
      }
    }
    out.sort(function (a, b) { return a.name.localeCompare(b.name); });
    return out;
  }

  window.App.chat.drawerParts = {
    grantedSecrets: grantedSecrets,
    noticesGroup: noticesGroup,
    whenLabel: whenLabel,
    routineMeta: routineMeta,
    routinesGroup: routinesGroup,
    noteOriginLine: noteOriginLine,
    noteItem: noteItem,
    noteList: noteList
  };
})();
