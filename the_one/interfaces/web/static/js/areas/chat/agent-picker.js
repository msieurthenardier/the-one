// The agent picker (M25 F4 leg 4a, flight DD2, DD4, A16; reference spec 5.6).
//
// App.chat.openPicker({opener}) -> Promise, resolved once the picker is open
// (or, with setup incomplete, at once without opening: an inert no-op).
//   - Chats not the active destination: it first runs
//     App.router.go(App.router.href({destination: 'chats'})) and continues on
//     a commit; it REJECTS on a guard Stay.
//   - The chat area not initialised yet: the call waits in a queue that the
//     chat area flushes at the end of its init (registerPickerHost).
//   - A picker already open: its search input takes focus.
//
// The picker is an App.ui.searchList in an App.ui.modal chooser (layout
// 'chooser', 640 wide at top 72, dismissible, the "Esc" close button, the
// footer "Picking an agent starts a new chat with it" / "Enter to start").
// It is BUILT FRESH on every open, so the query is cleared on the next open,
// never on close (reference spec 10, item 11).
//
// Rows (testid agent-picker-row, dataset {agent}): the provider dot as lead
// (badge badge--{type} badge-dot, aria-hidden; the type comes from the
// `providers` store by the agent's provider_config_id; an unknown type is
// badge--unknown and a missing provider badge-dot--none, as the Agents list
// does), the agent name, its description, and the model (meta, mono).
// Groups:
//   empty query  "Recently used" (up to 5: the agents with the latest
//                updated_at over sessions whose platform is null and whose
//                agent is live, DD4/A32), then "All agents" (every agent A-Z,
//                the recent ones included);
//   a query      one "{n} matching" group, A-Z (A16: a recorded deviation
//                from the board's data order), a case-insensitive substring
//                over the name, the model, the provider type slug and the
//                description;
//   no match     No agents match "{q}".
// The synthetic `default` agent and deleted agents never appear (only the
// live `agents` store rows, minus a `default` name). The picker waits on both
// `agents` and `providers` (App.store.get) and refreshes as each resolves.
//
// Picking closes the picker; from the modal's onClose (after focus is back on
// the opener) the chat area's onPick(agent, {opener}) runs, so a leave-guard
// dialog never stacks under the chooser. Escape, the close button and the
// backdrop close it with focus back at the opener. The picker does not own
// the pick itself (chat.js's requestPick does: the route, pickIntent).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var RECENT_MAX = 5;
  var host = null; // {setupIncomplete(), onPick(agent, {opener}), chatWith(agent, {opener})} from chat.js
  var queue = []; // open requests made before the chat area's init
  var openModal = null; // the open picker: {modal, list}

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  function arr(v) {
    return Array.isArray(v) ? v : [];
  }

  // The live agents, A-Z, without the synthetic default.
  function liveAgents(agents) {
    var out = [];
    var list = arr(agents);
    for (var i = 0; i < list.length; i++) {
      var a = list[i];
      if (!a || !a.name || a.name === 'default') continue;
      out.push(a);
    }
    out.sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
    return out;
  }

  // The agent's provider TYPE slug: '' for a provider with no type, null when
  // the agent has no provider or it is not in the store.
  function providerType(agent, providers) {
    if (!agent.provider_config_id) return null;
    var list = arr(providers);
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].id === agent.provider_config_id) {
        return list[i].type ? String(list[i].type) : '';
      }
    }
    return null;
  }

  function providerDot(type) {
    return App.ui.badge.dot(type);
  }

  // Up to five live agents, most recently used first (DD4): the latest
  // updated_at (else created_at) over the sessions with no platform (a
  // connector session is not the operator's use, A32) and a live agent.
  function recentAgents(agents, sessions) {
    var byName = {};
    for (var i = 0; i < agents.length; i++) byName[agents[i].name] = agents[i];
    var latest = {};
    var list = arr(sessions);
    for (var j = 0; j < list.length; j++) {
      var s = list[j];
      if (!s || s.platform) continue;
      var name = s.agent_name;
      if (!name || !Object.prototype.hasOwnProperty.call(byName, name)) continue;
      var t = Date.parse(s.updated_at || s.created_at || '');
      if (isNaN(t)) t = 0;
      if (!Object.prototype.hasOwnProperty.call(latest, name) || t > latest[name]) latest[name] = t;
    }
    var names = Object.keys(latest);
    names.sort(function (a, b) {
      if (latest[a] !== latest[b]) return latest[b] - latest[a];
      return a.localeCompare(b);
    });
    var out = [];
    for (var k = 0; k < names.length && k < RECENT_MAX; k++) out.push(byName[names[k]]);
    return out;
  }

  function haystack(agent, type) {
    return [agent.name, agent.llm_model || '', type || '', agent.description || '']
      .join(' ').toLowerCase();
  }

  // The searchList source: the groups for this query, from the stores.
  function source(query) {
    var agents = liveAgents(App.store.peek('agents').value);
    var providers = App.store.peek('providers').value;
    var types = {};
    for (var i = 0; i < agents.length; i++) types[agents[i].name] = providerType(agents[i], providers);
    function item(agent) {
      return {
        id: agent.name,
        label: agent.name,
        description: agent.description || '',
        meta: agent.llm_model || '',
        metaMono: true,
        lead: providerDot(types[agent.name]),
        dataset: { agent: agent.name }
      };
    }
    var q = String(query || '').trim().toLowerCase();
    if (!q) {
      var groups = [];
      var recent = recentAgents(agents, App.store.peek('sessions').value);
      if (recent.length) groups.push({ id: 'recent', label: 'Recently used', items: recent.map(item) });
      groups.push({ id: 'all', label: 'All agents', items: agents.map(item) });
      return groups;
    }
    var matched = [];
    for (var m = 0; m < agents.length; m++) {
      if (haystack(agents[m], types[agents[m].name]).indexOf(q) !== -1) matched.push(agents[m]);
    }
    return [{ id: 'matching', label: matched.length + ' matching', items: matched.map(item) }];
  }

  function emptyText(query) {
    if (!App.store.peek('agents').loaded) return 'Loading agents…';
    var q = String(query || '').trim();
    // Zero agents cannot reach the picker (New chat is disabled while setup
    // is incomplete); the text is defensive.
    return q ? 'No agents match "' + q + '".' : 'No agents yet.';
  }

  function build(opener) {
    var modal = null;
    var picked = null;
    var list = App.ui.searchList({
      label: 'Find an agent',
      placeholder: 'Find an agent by name, model or provider',
      variant: 'chooser',
      inputTestid: 'agent-picker-search',
      rowTestid: 'agent-picker-row',
      source: source,
      emptyText: emptyText,
      onPick: function (item) {
        picked = item.id;
        modal.close(item.id);
      }
    });
    // A fragment, so its item is a flex child of the footer row; the end text is
    // the modal's footerEnd.
    var footer = document.createDocumentFragment();
    footer.appendChild(el('span', { text: 'Picking an agent starts a new chat with it' }));
    var entry = { modal: null, list: list };
    modal = App.ui.modal({
      title: 'Start a chat with…',
      layout: 'chooser',
      width: 640,
      top: 72,
      dismissible: true,
      closeButton: { label: 'Esc', ariaLabel: 'Close (Esc)', testid: 'agent-picker-close' },
      body: el('div', { className: 'agent-picker-body' }, [list.el]),
      footer: footer,
      footerEnd: 'Enter to start',
      initialFocus: list.input,
      testid: 'agent-picker',
      onClose: function (value) {
        list.destroy();
        if (openModal === entry) openModal = null;
        // After the modal restored focus to the opener: a guard dialog the
        // pick may raise never stacks under the chooser.
        if (picked && value === picked && host) host.onPick(picked, { opener: opener });
      }
    });
    entry.modal = modal;
    openModal = entry;
    modal.open(opener);

    // Wait on both lists; refresh as each resolves (while still open). A
    // list already loaded rendered from the cache above.
    ['agents', 'providers'].forEach(function (name) {
      if (App.store.peek(name).loaded) return;
      App.store.get(name).then(function () {
        if (openModal === entry) list.refresh();
      }, function () { /* the empty state stays */ });
    });
  }

  function openNow(opener, resolve) {
    if (host.setupIncomplete()) {
      resolve();
      return;
    }
    if (openModal && openModal.modal.isOpen()) {
      openModal.list.input.focus();
      resolve();
      return;
    }
    var fallback = document.activeElement;
    if (fallback === document.body || fallback === document.documentElement) fallback = null;
    build(opener || fallback);
    resolve();
  }

  function proceed(opener, resolve) {
    if (!host) {
      queue.push({ opener: opener, resolve: resolve });
      return;
    }
    openNow(opener, resolve);
  }

  function openPicker(opts) {
    opts = opts || {};
    var opener = opts.opener || null;
    return new Promise(function (resolve, reject) {
      var cur = App.router && App.router.current ? App.router.current() : null;
      if (cur && cur.destination === 'chats') {
        proceed(opener, resolve);
        return;
      }
      App.router.go(App.router.href({ destination: 'chats' })).then(function (ok) {
        if (!ok) {
          reject(new Error('openPicker: the move to Chats did not commit'));
          return;
        }
        proceed(opener, resolve);
      }, reject);
    });
  }

  // Called by the chat area at the END of its init: registers the pick
  // handler and flushes the open requests that waited for it.
  function registerPickerHost(h) {
    host = h;
    var waiting = queue;
    queue = [];
    for (var i = 0; i < waiting.length; i++) openNow(waiting[i].opener, waiting[i].resolve);
  }

  // App.chat.chatWith(agent, {opener}) -> Promise<boolean> (M25 F4 L6, DD8):
  // a start from outside Chats (the agent editor's Chat action). The guarded
  // go() to `#chats/~new/{agent}`, so a dirty editor asks once (Stay returns
  // focus to the opener; Continue lands on the pending chat). Once the chat
  // area exists the go carries its one-shot pick intent (host.chatWith),
  // so the AC9 rail restore cannot keep a joined session started from this
  // agent instead; before its init the state is idle and a plain go() does.
  // Unlike a pick, it is not inert while setup is incomplete (the pending
  // chat then shows its blocked composer).
  function chatWith(agent, opts) {
    if (!agent) return Promise.resolve(false);
    if (host && typeof host.chatWith === 'function') return host.chatWith(agent, opts || {});
    var goOpts = {};
    if (opts && opts.opener) goOpts.opener = opts.opener;
    return App.router.go(App.router.href({ destination: 'chats', create: true, agent: agent }), goOpts);
  }

  window.App.chat.openPicker = openPicker;
  window.App.chat.chatWith = chatWith;
  window.App.chat.registerPickerHost = registerPickerHost;
  window.App.chat.agentPicker = {
    source: source,
    recentAgents: recentAgents,
    // The providers resolution, shared with the chat pane's new-chat state
    // (M25 F4 L4b): the agent's provider TYPE slug, '' for a provider with
    // no type, null for no provider or one not in the store.
    providerType: providerType,
    RECENT_MAX: RECENT_MAX
  };
})();
