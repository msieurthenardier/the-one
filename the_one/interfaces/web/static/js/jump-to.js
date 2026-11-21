// App.jumpTo -- the jump-to palette (M25 F4 L7, flight DD9, DD10, DD14; reference spec 9).
//
// A composition, not a factory: an App.ui.searchList inside an App.ui.modal
// chooser named by `ariaLabel` "Jump to" (no visible title, no header row),
// 600 wide at top 96, dismissible, testid `jump-to`. It is BUILT FRESH on
// every open, so the query starts empty each time.
//
//   App.jumpTo.open(opener)   open the palette (focus on its input); when it
//                             is already open, focus its input instead. The
//                             opener (the element focused at Ctrl K, or the
//                             rail's Jump to control) is CAPTURED here: Escape
//                             returns focus to it, and so does a guard's Stay.
//                             <body> / <html> count as no opener (#main-content).
//   App.jumpTo.isOpen()
//   App.jumpTo.focusInput()   focus the open palette's input, only while the
//                             palette is the topmost modal.
//   App.jumpTo.candidates()   the full ordered candidate list (pure over the
//                             store caches), and match(query) the first 8
//                             matches: both exported for tests. An empty
//                             query shows emptyMix(candidates()) instead.
//
// The body: the input bar (the searchList's field wrapper, restyled: the
// search icon, the visually hidden label "Jump to", the input `jump-to-input`
// with the placeholder, then the palette's own "Esc" close button
// `jump-to-close`, accessible name "Close (Esc)", which calls the modal's
// close()) over the results. The footer: "{Ctrl K|⌘ K} from anywhere" and
// "Enter to open", both on the left.
//
// Candidates, in this order (DD10, A17): agents A-Z; chats newest first
// (`sessions` by updated_at, stable; an empty title reads "Untitled chat"; the
// agent is the stored agent_name, "Unknown agent" for none; GleepGlorp, "Built in", comes
// first among the agents while it is enabled, M36 L04); the New chat…
// action; model providers, knowledge bases, MCP servers, connectors and secrets (each A-Z); the Settings
// pages in nav order (App.settingsPages).
// Rows (testid `jump-to-result`, data-kind / data-id) show the label and the
// "where" text (`meta`, not mono). Matching is a case-insensitive substring
// over `label + " " + where`, trimmed; the first 8 matching candidates show.
// The EMPTY query is a mix instead (operator decision, DD13 preview option C,
// flight 4 leg 9): up to 3 recent chats, New chat…, up to 4 recently used
// agents (the picker's recentAgents), then the board-order fill, 8 in total.
// No match reads
// `No matches for "{q}".`
//
// Cold data (AC11): open() calls App.store.get for each collection (`sessions`
// with force: the WebSocket primes it only while Chats is active) and refreshes
// the list as each resolves, ONLY while this palette is still the open one. A
// failed collection is left out silently.
//
// Opening a result (AC10): the palette CLOSES FIRST (so a dirty editor's
// confirm is the only modal: the Flight 1 DD8 chaining rule), then, from the
// modal's onClose (focus is back on the opener), navigates with the captured
// opener: App.router.go(href, {opener}). An agent clears the Agents filter
// once its go commits (App.studio.clearAgentFilter); New chat… calls
// App.chat.openPicker({opener}) alone (it goes to Chats itself and rejects on
// a guard Stay).
(function () {
  'use strict';
  window.App = window.App || {};

  var CAP = 8;
  var RECENT_CHATS = 3;
  var RECENT_AGENTS = 4;
  var COLLECTIONS = ['agents', 'sessions', 'providers', 'knowledge-bases', 'mcp-sources', 'connectors', 'secrets'];
  var LIBRARY = [
    { kind: 'provider', collection: 'providers', section: 'providers', where: 'Library · Model provider' },
    { kind: 'knowledge-base', collection: 'knowledge-bases', section: 'knowledge', where: 'Library · Knowledge base' },
    { kind: 'mcp-server', collection: 'mcp-sources', section: 'mcp', where: 'Library · MCP server' },
    { kind: 'connector', collection: 'connectors', section: 'connectors', where: 'Library · Connector' },
    { kind: 'secret', collection: 'secrets', section: 'secrets', where: 'Library · Secret' }
  ];
  var current = null; // the open palette: {modal, list, opener, picked}

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  function arr(v) {
    return Array.isArray(v) ? v : [];
  }

  // A collection's cached rows; an unknown or failed one is empty.
  function rows(name) {
    try {
      return arr(App.store.peek(name).value);
    } catch (e) {
      return [];
    }
  }

  function isNamed(row) {
    return !!row && row.name !== undefined && row.name !== null && row.name !== '';
  }

  function sortedByName(list) {
    var out = [];
    for (var i = 0; i < list.length; i++) if (isNamed(list[i])) out.push(list[i]);
    out.sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
    return out;
  }

  function stamp(session) {
    var t = Date.parse((session && (session.updated_at || session.created_at)) || '');
    return isNaN(t) ? 0 : t;
  }

  // Newest first; equal timestamps keep their store order (decorated sort).
  function sortedChats(list) {
    var decorated = [];
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].id !== undefined && list[i].id !== null) {
        decorated.push({ s: list[i], t: stamp(list[i]), i: i });
      }
    }
    decorated.sort(function (a, b) { return b.t - a.t || a.i - b.i; });
    var out = [];
    for (var k = 0; k < decorated.length; k++) out.push(decorated[k].s);
    return out;
  }

  function settingsWhere(page) {
    return 'Settings · ' + page.group;
  }

  // Every candidate, in board order: {kind, key, label, where, section?}.
  function candidates() {
    var out = [];
    var i;
    // M36 F1 L04: GleepGlorp, first among the agents, while it is enabled.
    var gg = App.gleepglorp && App.gleepglorp.peek().value;
    if (gg && gg.enabled) {
      out.push({ kind: 'gleepglorp', key: 'GleepGlorp', label: 'GleepGlorp', where: 'Built in' });
    }
    var agents = sortedByName(rows('agents'));
    for (i = 0; i < agents.length; i++) {
      out.push({ kind: 'agent', key: String(agents[i].name), label: String(agents[i].name), where: 'Agent' });
    }
    var chats = sortedChats(rows('sessions'));
    for (i = 0; i < chats.length; i++) {
      var s = chats[i];
      out.push({
        kind: 'chat',
        key: String(s.id),
        label: s.title ? String(s.title) : 'Untitled chat',
        where: 'Chat · ' + (s.agent_name ? String(s.agent_name) : 'Unknown agent')
      });
    }
    out.push({ kind: 'action', key: 'new-chat', label: 'New chat…', where: 'Action' });
    for (var g = 0; g < LIBRARY.length; g++) {
      var group = LIBRARY[g];
      var items = sortedByName(rows(group.collection));
      for (i = 0; i < items.length; i++) {
        if (items[i].id === undefined || items[i].id === null) continue;
        out.push({
          kind: group.kind,
          key: String(items[i].id),
          label: String(items[i].name),
          where: group.where,
          section: group.section
        });
      }
    }
    var pages = arr(App.settingsPages);
    for (i = 0; i < pages.length; i++) {
      out.push({ kind: 'settings', key: pages[i].section, label: pages[i].label, where: settingsWhere(pages[i]) });
    }
    // M36 F3 L2: open the GleepGlorp drawer, off Chats while GleepGlorp is enabled (on Chats the
    // GleepGlorp candidate above already starts a chat). Last, so the empty query never shows it
    // ahead of the board-order fill.
    var here = App.router && App.router.current && App.router.current();
    if (gg && gg.enabled && here && here.destination !== 'chats') {
      out.push({ kind: 'gleepglorp-ask', key: 'ask', label: 'Ask GleepGlorp', where: 'Assistant' });
    }
    return out;
  }

  // The recently used agents as candidates (the picker's rule, A32): live
  // agents only (no nameless row, no synthetic `default`), at most
  // RECENT_AGENTS. Empty when the picker is absent or throws.
  function recentAgentCandidates() {
    var out = [];
    try {
      var picker = App.chat && App.chat.agentPicker;
      if (!picker || typeof picker.recentAgents !== 'function') return out;
      var live = [];
      var list = rows('agents');
      for (var i = 0; i < list.length; i++) {
        if (isNamed(list[i])) live.push(list[i]);
      }
      var recent = arr(picker.recentAgents(live, rows('sessions')));
      for (var k = 0; k < recent.length && out.length < RECENT_AGENTS; k++) {
        if (!isNamed(recent[k])) continue;
        out.push({ kind: 'agent', key: String(recent[k].name), label: String(recent[k].name), where: 'Agent' });
      }
    } catch (e) {
      return [];
    }
    return out;
  }

  // The empty query's list, given the board-order candidates: up to
  // RECENT_CHATS chats, New chat…, up to RECENT_AGENTS recent agents, then
  // the board order skipping what is shown, CAP in total.
  function emptyMix(all) {
    var out = [];
    var seen = {};
    function add(c) {
      var id = c.kind + ':' + c.key;
      if (out.length >= CAP || seen[id]) return;
      seen[id] = true;
      out.push(c);
    }
    var i;
    var chats = 0;
    for (i = 0; i < all.length && chats < RECENT_CHATS; i++) {
      if (all[i].kind === 'chat') {
        add(all[i]);
        chats++;
      }
    }
    for (i = 0; i < all.length; i++) {
      if (all[i].kind === 'action') {
        add(all[i]);
        break;
      }
    }
    var agents = recentAgentCandidates();
    for (i = 0; i < agents.length; i++) add(agents[i]);
    for (i = 0; i < all.length; i++) add(all[i]);
    return out;
  }

  // The first CAP candidates whose `label + " " + where` holds the trimmed
  // query (case-insensitive); with an empty query, the emptyMix.
  function match(query) {
    var q = String(query === undefined || query === null ? '' : query).trim().toLowerCase();
    var all = candidates();
    if (!q) return emptyMix(all);
    var out = [];
    for (var i = 0; i < all.length && out.length < CAP; i++) {
      var c = all[i];
      if ((c.label + ' ' + c.where).toLowerCase().indexOf(q) !== -1) out.push(c);
    }
    return out;
  }

  function toItem(c) {
    return {
      id: c.kind + ':' + c.key,
      label: c.label,
      meta: c.where,
      dataset: { kind: c.kind, id: c.key },
      candidate: c
    };
  }

  function source(query) {
    var found = match(query);
    var items = [];
    for (var i = 0; i < found.length; i++) items.push(toItem(found[i]));
    // One unlabelled group: the board draws no group headings.
    return [{ id: 'results', items: items }];
  }

  function emptyText(query) {
    return 'No matches for "' + String(query || '').trim() + '".';
  }

  function keyHint() {
    var s = App.shortcuts;
    var mac = !!(s && typeof s.isMacPlatform === 'function' && s.isMacPlatform());
    return s && typeof s.jumpToKeys === 'function' ? s.jumpToKeys(mac).hint : 'Ctrl K';
  }

  // Navigate to a picked candidate. Runs from the modal's onClose, after the
  // palette is gone and focus is back on the opener.
  function act(c, opener) {
    var R = App.router;
    if (!R) return;
    var who = opener && opener.isConnected ? opener : document.getElementById('main-content');
    var goOpts = { opener: who };
    if (c.kind === 'agent') {
      R.go(R.href({ destination: 'agents', id: c.key }), goOpts).then(function (ok) {
        if (ok && App.studio && typeof App.studio.clearAgentFilter === 'function') {
          App.studio.clearAgentFilter();
        }
      });
    } else if (c.kind === 'gleepglorp') {
      // The pending GleepGlorp chat, through the router (a dirty editor asks once).
      R.go(R.href({ destination: 'chats', create: true, agent: c.key }), goOpts);
    } else if (c.kind === 'gleepglorp-ask') {
      // Runs from the modal's onClose, after focus went back to the opener, so the drawer's own
      // focus move (to its title) is the last one.
      if (App.gleepglorpDrawer) App.gleepglorpDrawer.open();
    } else if (c.kind === 'chat') {
      R.go(R.href({ destination: 'chats', id: c.key }), goOpts);
    } else if (c.kind === 'action') {
      if (App.chat && typeof App.chat.openPicker === 'function') {
        App.chat.openPicker({ opener: who }).then(null, function () { /* a guard Stay */ });
      }
    } else if (c.kind === 'settings') {
      R.go(R.href({ destination: 'settings', section: c.key }), goOpts);
    } else if (c.section) {
      R.go(R.href({ destination: 'library', section: c.section, id: c.key }), goOpts);
    }
  }

  function isOpen() {
    return !!current && current.modal.isOpen();
  }

  // Focus the open palette's input, only when the palette is the topmost
  // modal (dialogs are appended to <body> in open order).
  function focusInput() {
    if (!isOpen()) return;
    var open = document.querySelectorAll('dialog[open]');
    if (open.length && open[open.length - 1] !== current.modal.el) return;
    current.list.input.focus();
  }

  // Re-render with fresh store data. The searchList keeps the highlighted row by
  // identity (M31 F6 L03b, D4, squawk 0185, superseding M25 DD10's "the first row
  // follows the data"): the row Enter would pick never changes under the user when
  // data lands. A no-op once this palette closed (its list is destroyed).
  function refresh(entry) {
    if (current !== entry || !entry.modal.isOpen()) return;
    entry.list.refresh();
  }

  function load(entry) {
    COLLECTIONS.forEach(function (name) {
      var p;
      try {
        p = App.store.get(name, name === 'sessions' ? { force: true } : undefined);
      } catch (e) {
        return;
      }
      p.then(function () { refresh(entry); }, function () { /* left out silently */ });
    });
    // GleepGlorp's settings (its candidate shows while it is enabled).
    if (App.gleepglorp) {
      App.gleepglorp.get().then(function () { refresh(entry); }, function () { /* left out */ });
    }
  }

  function open(opener) {
    if (isOpen()) {
      focusInput();
      return;
    }
    if (opener === document.body || opener === document.documentElement) opener = null;
    var entry = { modal: null, list: null, opener: opener || null, picked: null };

    var list = App.ui.searchList({
      label: 'Jump to',
      placeholder: 'Jump to an agent, chat, library item or setting',
      inputTestid: 'jump-to-input',
      rowTestid: 'jump-to-result',
      source: source,
      emptyText: emptyText,
      onPick: function (item) {
        entry.picked = item.candidate || null;
        entry.modal.close('pick');
      }
    });
    // The input bar is the searchList's field wrapper ([hidden label, input]):
    // the search icon goes first, the palette's own close button last (A11:
    // "Esc", named "Close (Esc)"; ariaLabel modals have no header for one).
    var bar = list.input.parentNode;
    bar.classList.add('jump-to-bar');
    bar.insertBefore(el('span', { className: 'jump-to-bar-icon', 'aria-hidden': 'true' }, [
      App.ui.util.icon('search')
    ]), bar.firstChild);
    bar.appendChild(App.ui.button({
      label: 'Esc',
      ariaLabel: 'Close (Esc)',
      variant: 'ghost',
      size: 'sm',
      testid: 'jump-to-close',
      onClick: function () { entry.modal.close(); }
    }));

    // A fragment, so the two items are the footer row's own flex children
    // (both on the left: no footerEnd).
    var footer = document.createDocumentFragment();
    footer.appendChild(el('span', { text: keyHint() + ' from anywhere' }));
    footer.appendChild(el('span', { text: 'Enter to open' }));

    entry.list = list;
    entry.modal = App.ui.modal({
      ariaLabel: 'Jump to',
      layout: 'chooser',
      width: 600,
      top: 96,
      dismissible: true,
      id: 'jump-to-dialog',
      testid: 'jump-to',
      body: el('div', { className: 'jump-to-body' }, [list.el]),
      footer: footer,
      initialFocus: list.input,
      onClose: function (value) {
        list.destroy();
        if (current === entry) current = null;
        if (value === 'pick' && entry.picked) act(entry.picked, entry.opener);
      }
    });
    current = entry;
    entry.modal.open(entry.opener);
    load(entry);
  }

  window.App.jumpTo = {
    open: open,
    isOpen: isOpen,
    focusInput: focusInput,
    candidates: candidates,
    match: match,
    emptyMix: emptyMix,
    CAP: CAP,
    RECENT_CHATS: RECENT_CHATS,
    RECENT_AGENTS: RECENT_AGENTS
  };
})();
