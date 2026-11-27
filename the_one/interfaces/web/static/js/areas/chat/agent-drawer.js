// App.chat.agentDrawer -- the agent drawer (M25 F4 L6; flight DD7, DD15 A13,
// A20, A21; reference spec 5.7). Built with DOM APIs only.
//
// The drawer is an App.ui.drawer that FILLS the static shell slot
// `<aside id="chat-drawer" aria-label="This chat's agent">` (index.html, a
// sibling after <main> in .app-shell-row): the chat area never creates or
// removes it, so the header toggle's aria-controls always resolves. It is
// shown only while (a) the chat area is active (setActive, from the area's
// activate/deactivate), (b) there is a chat view (render(view) with a
// non-null view: the header's agent while pending, starting, joining or
// joined), and (c) the current mode's open state is true.
//
// Modes (one state object {mode, open: {push, overlay}}, applied by apply()):
//   push     at 1280px and wider: a 320px flex sibling of <main>; OPEN by
//            default
//   overlay  below 1280px: over the right of the chat pane, with the modal
//            shadow, no scrim and no outside-click close; CLOSED by default
//   A matchMedia('(min-width: 1280px)') `change` listener (on the
//   MediaQueryList, not the document or window; removed by destroy)
//   switches the mode, then that mode's persisted state applies. The open
//   state persists in localStorage `chat-drawer-open` as {push, overlay}
//   (try/catch: blocked storage keeps the defaults).
//
// The toggle (returned for the chat header, at its end): App.ui.button
// ghost icon-only, the panel-right icon, aria-label "Show this chat's agent",
// aria-pressed = the open state, aria-controls="chat-drawer", testid
// chat-drawer-toggle; hidden with no chat view. Escape inside the drawer
// closes it (the factory) and focus returns to the toggle.
//
// Content (re-rendered when renderKey() changes, on opening, on an `agents`/
// `providers`/`knowledge-bases`/`mcp-sources` notification while open and on
// fetch/metadata completions; subscriptions are released by destroy):
//   header   the agent's name (h2, 13px/600) and a badge badge--{type} whose
//            TEXT is the provider type (A20), hidden with no provider
//   body     the description (12px, --fg-secondary); the facts <dl>: Model
//            (mono), Provider (the provider's display name from the store),
//            Chats (the `sessions` rows with that agent_name, connector
//            sessions included, DD4); "What it can use" (A13), read-only:
//            Knowledge bases (kb_ids against the store), MCP servers
//            (mcp_source_ids found in the PLAIN `mcp-sources` list, so the
//            self-configuration loopback source is skipped, with "{n} tools"
//            where App.usage.mcpToolCount knows it), Secrets (names), Built-in tools (the
//            categories with their effective enabled count: globally enabled
//            AND the agent's AgentConfig.is_tool_enabled), Self-configuration
//            (On or Off). An empty group says "None"; a failed load says
//            "Couldn't load" for that group only.
//   Needs attention (sortie 07 L05, DD12): between the facts <dl> and "What it can use",
//            built by App.chat.drawerParts.noticesGroup (agent-drawer-parts.js): one
//            sentence per tool-override notice on the agent row (text only) and a link
//            to the agent's Tools tab (testid chat-drawer-notices-link); absent when
//            there are none.
//   Rules (M27 F1 L2, DD7): first in "What it can use": the agent's enabled
//            rules in order (two-line clamp, full text in `title`), "{n} off"
//            for disabled ones, "No rules" (also on a 404). Read-only: no edit
//            link (Open agent settings is the way to the editor). Fetched once
//            per open and agent: GET /api/agents/{name}/rules.
//   Notes (M27 F2 L3, DD10; F3 L2): after Rules, READ-ONLY: "Off" and "{n} kept"
//            when the switch is off; when on, each note's [n], a warning-triangle
//            flag (testid chat-drawer-notes-flag) for untrusted ones, its text
//            (two-line clamp, full text in `title`) and a short origin line;
//            "No notes yet" (also on a 404). Notes the open chat's prompt does
//            not carry yet sit muted under "Pending · used from the next chat".
//            Fetched per open, agent and session (GET /api/agents/{name}/notes
//            ?session_id=, the server marks `pending`); refreshNotes() re-fetches
//            on a live save/update/forget and after a rejoin.
//   Routine (M33 F1 L7): a "Routine" fact (chat-drawer-routine, "{name} · last ran {day}
//            {time}") from the join's session_metadata.routine, kept per session id by
//            setSessionMetadata(sessionId, meta) and shown only while the view's sessionId
//            matches; and a read-only Routines group after Notes (A-Z, "Next {day} {time}",
//            "Off" or "Done", "None"), fetched per open like Rules (404 = none), refetched
//            without flicker by refreshRoutines() on each session_joined. The default and
//            deleted agents get no group.
//   footer   Open agent settings (App.ui.button secondary, the settings gear,
//            testid chat-drawer-settings-link): a guarded go() to the agent,
//            then App.studio.clearAgentFilter() on a commit (reference spec
//            10, item 18).
// Fetches, only while open with a known agent: GET /api/tools/configs once
// per open, GET /api/agents/{name}/self-configuration once per open and
// agent, and App.store.get for `knowledge-bases` and `mcp-sources` once per
// open (cached, so usually no request). Responses from an earlier open are
// dropped.
// Non-agent states (App.chat.agentKind): gleepglorp (M36 L04: "Built in" badge, its settings
// facts, no per-agent fetches, footer to #settings/gleepglorp); deleted (a null agent, "Unknown
// agent", or a name not in the LOADED `agents` store: "This agent no longer exists", no link)
//   loading   the `agents` store not loaded yet, or the header's agent line
//             still blank: a neutral "Loading…", never "deleted"
//
// API: App.chat.agentDrawer.create({slot}) -> {drawer, toggle,
//   render(view), setActive(bool), destroy()}; view is null or
//   {agent: name|null, loading: bool}.
//   App.chat.agentDrawer.isToolEnabled(agent, name): AgentConfig.
//   is_tool_enabled mirrored (the_one/agent/config.py; parity pinned by
//   tests/browser/test_flow_chat_drawer.py).
//   App.chat.agentDrawer.builtinGroups(agent, configs) -> [{label, enabled,
//   total}] for the categories with at least one effective tool.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var STORAGE_KEY = 'chat-drawer-open';
  var PUSH_QUERY = '(min-width: 1280px)';
  var NARROW_QUERY = '(max-width: 767.98px)'; // below 768px the panel fills the pane (sortie 21 L2)
  var STORES = ['agents', 'providers', 'knowledge-bases', 'mcp-sources', 'secrets', 'sessions'];

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  function arr(v) {
    return Array.isArray(v) ? v : [];
  }

  function readOpen() {
    var out = { push: true, overlay: false };
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      var parsed = raw ? JSON.parse(raw) : null;
      if (parsed && typeof parsed === 'object') {
        if (typeof parsed.push === 'boolean') out.push = parsed.push;
        if (typeof parsed.overlay === 'boolean') out.overlay = parsed.overlay;
      }
    } catch (e) {
      /* blocked storage or bad JSON: the defaults */
    }
    return out;
  }

  function writeOpen(open) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ push: !!open.push, overlay: !!open.overlay }));
    } catch (e) {
      /* blocked storage: the state lives for this page only */
    }
  }

  // isToolEnabled and builtinGroups live in agent-drawer-groups.js (squawk 0386); re-exported below.
  var isToolEnabled = App.chat.drawerGroups.isToolEnabled;
  var builtinGroups = App.chat.drawerGroups.builtinGroups;

  function findBy(list, key, value) {
    var rows = arr(list);
    for (var i = 0; i < rows.length; i++) if (rows[i] && rows[i][key] === value) return rows[i];
    return null;
  }

  function create(opts) {
    opts = opts || {};
    var slot = opts.slot;
    // `open.fill` (below 768px) is session-only: never read from or written to storage, false on
    // every load and on every entry into fill.
    var state = { mode: 'push', open: readOpen() };
    state.open.fill = false;
    var focusOnOpen = false; // one-shot: the toggle opened the panel in fill; apply() consumes it
    var active = false;
    var view = null;
    var applying = false;
    var openGen = 0;
    var current = null; // the agent name the settings link opens
    var ggView = false; // the view is GleepGlorp: the link opens its settings
    var configs = { gen: -1, status: 'idle', value: null };
    var selfConf = { gen: -1, agent: null, status: 'idle', value: null };
    var rulesState = { gen: -1, agent: null, status: 'idle', value: null };
    // M27 F2 L3 (DD10): the Notes group's per-open fetch, shaped like rulesState
    // (value = {enabled, notes}), keyed on agent AND session (F3 L2).
    var notesState = { gen: -1, agent: null, session: null, status: 'idle', value: null };
    var notesToken = 0;
    // M33 F1 L7 (DD10): the Routines group's fetch (value = the agent's routines), and the
    // open chat's join metadata, kept per session id so chat A's routine never shows in B.
    var routinesState = { gen: -1, agent: null, status: 'idle', value: null };
    var routinesToken = 0;
    var sessionMeta = { session: null, meta: null };
    var storeTried = {};
    var storeFailed = {};

    // ── Header, body, footer (built once; render patches or refills) ───
    var nameEl = el('h2', { className: 'chat-drawer-name' });
    var badge = App.ui.badge.live({ kind: 'unknown' });
    var head = el('div', { className: 'chat-drawer-head' }, [nameEl, badge.el]);
    var content = el('div', { className: 'chat-drawer-content' });
    var settingsBtn = App.ui.button({
      variant: 'secondary',
      icon: 'settings',
      label: 'Open agent settings',
      className: 'chat-drawer-settings',
      testid: 'chat-drawer-settings-link',
      onClick: openSettings
    });

    var drawer = App.ui.drawer({
      el: slot,
      label: 'This chat\'s agent',
      heading: head,
      body: content,
      footer: settingsBtn,
      reserveHeaderEnd: true, // room for the header's drawer toggle over the overlay
      testid: 'chat-drawer',
      beforeClose: function () {
        // Before the factory returns focus to the toggle: clear `inert` and show the toggle.
        syncCover(false);
      },
      onOpenChange: function (open) {
        // apply() opens and closes for visibility; only a change from inside
        // the drawer (Escape) is the user's, and persists (never in fill: session-only).
        if (applying) return;
        state.open[state.mode] = open;
        if (state.mode !== 'fill') writeOpen(state.open);
        syncCover(open);
      }
    });
    var footerEl = settingsBtn.parentNode; // the factory's .ui-drawer-footer

    // The Close button (below 768px only; CSS shows it on data-mode="fill").
    var closeBtn = App.ui.button({
      variant: 'ghost',
      icon: 'x',
      iconOnly: true,
      ariaLabel: 'Close agent panel',
      className: 'chat-drawer-close',
      testid: 'chat-drawer-close',
      onClick: function () { drawer.close(); }
    });
    closeBtn.setAttribute('aria-keyshortcuts', 'Escape');
    // The factory's header wrapper, reached through the heading node it placed there (never by
    // position in the <aside>).
    var headerEl = head.parentNode;
    if (headerEl) headerEl.appendChild(closeBtn);

    // One sync point for the shell cover (inert), the toggle's visibility and aria-pressed.
    function syncCover(shown) {
      var cover = !!shown && state.mode === 'fill';
      if (App.shellPane) App.shellPane.setCovered('chat-drawer', cover, { el: drawer.el, close: closeFromShell });
      toggle.hidden = !view || cover;
      toggle.setAttribute('aria-pressed', shown ? 'true' : 'false');
    }
    function closeFromShell() {
      state.open.fill = false;
      apply();
    }

    var toggle = App.ui.button({
      variant: 'ghost',
      icon: 'panel-right',
      iconOnly: true,
      ariaLabel: 'Show this chat\'s agent',
      className: 'chat-drawer-toggle',
      testid: 'chat-drawer-toggle',
      onClick: function () {
        state.open[state.mode] = !state.open[state.mode];
        if (state.mode === 'fill') focusOnOpen = state.open.fill;
        else writeOpen(state.open);
        apply();
      }
    });
    toggle.setAttribute('aria-controls', drawer.el.id || 'chat-drawer');
    toggle.setAttribute('aria-pressed', 'false');
    toggle.hidden = true;

    function openSettings() {
      if (!current && !ggView) return;
      var href = App.chat.agentKind(ggView ? App.chat.GLEEPGLORP : current).settingsHref;
      App.router.go(href, { opener: settingsBtn })
        .then(function (navigated) {
          if (navigated && !ggView && App.studio && typeof App.studio.clearAgentFilter === 'function') {
            App.studio.clearAgentFilter();
          }
        });
    }

    // ── What the view shows ─────────────────────────────────────────────
    function describe() {
      if (!view) return { kind: 'none' };
      if (view.loading) return { kind: 'loading' };
      var name = view.agent;
      if (!name) return { kind: 'deleted', name: 'Unknown agent' };
      var kind = App.chat.agentKind(name).kind;
      if (kind === 'gleepglorp') return { kind: 'gleepglorp' };
      if (kind === 'agent') return { kind: 'agent', name: name, row: findBy(App.store.peek('agents').value, 'name', name) };
      return kind === 'loading' ? { kind: 'loading' } : { kind: 'deleted', name: name };
    }

    // The `sessions` rows of this agent, connector sessions included (DD4).
    function chatsCount(name) {
      var rows = arr(App.store.peek('sessions').value);
      var n = 0;
      for (var i = 0; i < rows.length; i++) {
        if (rows[i] && rows[i].agent_name === name) n += 1;
      }
      return n;
    }

    function facts(pairs) {
      var dl = el('dl', { className: 'chat-drawer-facts' });
      dl.setAttribute('data-testid', 'chat-drawer-facts');
      for (var i = 0; i < pairs.length; i++) {
        dl.appendChild(el('dt', { text: pairs[i][0] }));
        dl.appendChild(el('dd', { className: pairs[i][2] || null, text: pairs[i][1] }));
      }
      return dl;
    }

    function note(text) {
      var p = el('p', { className: 'chat-drawer-note', text: text });
      p.setAttribute('data-testid', 'chat-drawer-note');
      return p;
    }

    // The group builders (group, rulesGroup, notesGroup) live in agent-drawer-groups.js.
    var group = App.chat.drawerGroups.group;

    // The Routine fact's value, only for the metadata of the session the view shows.
    function routineFact() {
      var sid = viewSession();
      var r = sid && sessionMeta.session === sid && sessionMeta.meta ? sessionMeta.meta.routine : null;
      if (!r || !r.name) return null;
      var when = r.last_run_at ? App.chat.drawerParts.whenLabel(r.last_run_at) : '';
      return String(r.name) + (when ? ' · last ran ' + when : '');
    }

    // Fetch the agent's routines (404 = none). `refresh` keeps the shown list until the
    // response arrives; a failed refresh keeps it too. Guarded by token, gen and agent.
    function loadRoutines(agentName, gen, refresh) {
      var token = ++routinesToken;
      if (!refresh) routinesState = { gen: gen, agent: agentName, status: 'pending', value: null };
      fetch('/api/agents/' + encodeURIComponent(agentName) + '/routines').then(function (r) {
        if (r.status === 404) return { routines: [] };
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }).then(function (body) {
        if (token !== routinesToken || routinesState.gen !== gen || routinesState.agent !== agentName) return;
        routinesState = { gen: gen, agent: agentName, status: 'ok', value: (body && body.routines) || [] };
        render();
      }, function () {
        if (token !== routinesToken || routinesState.gen !== gen || routinesState.agent !== agentName) return;
        if (refresh) return;
        routinesState = { gen: gen, agent: agentName, status: 'error', value: null };
        render();
      });
    }

    // No-op while the drawer is closed or the view is not a named agent.
    function refreshRoutines() {
      var info = describe();
      if (info.kind !== 'agent' || !drawer.isOpen()) return;
      loadRoutines(info.name, openGen, routinesState.status === 'ok' && routinesState.agent === info.name);
    }

    // The join's session_metadata, keyed by session id; re-renders when it changed.
    function setSessionMetadata(sessionId, meta) {
      var next = { session: sessionId || null, meta: meta && typeof meta === 'object' ? meta : null };
      var changed = JSON.stringify(next) !== JSON.stringify(sessionMeta);
      sessionMeta = next;
      if (changed) render();
    }

    // Read the notes once per open, agent and session (a raw fetch: a 404, no
    // stored row, reads as "No notes yet"). `refresh` keeps the old list on
    // screen until the new one arrives, and a failed refresh keeps it too. The
    // session id lets the server mark the notes the chat's prompt lacks.
    function loadNotes(agentName, sessionId, gen, refresh) {
      var token = ++notesToken;
      if (!refresh) {
        notesState = { gen: gen, agent: agentName, session: sessionId, status: 'pending', value: null };
      }
      var url = '/api/agents/' + encodeURIComponent(agentName) + '/notes' +
        (sessionId ? '?session_id=' + encodeURIComponent(sessionId) : '');
      fetch(url).then(function (r) {
        if (r.status === 404) return { enabled: true, notes: [] };
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }).then(function (body) {
        if (token !== notesToken) return;
        notesState = {
          gen: gen, agent: agentName, session: sessionId, status: 'ok',
          value: { enabled: !!(body && body.enabled), notes: (body && body.notes) || [] }
        };
        render();
      }, function () {
        if (token !== notesToken) return;
        if (refresh) return;
        notesState = { gen: gen, agent: agentName, session: sessionId, status: 'error', value: null };
        render();
      });
    }

    // Re-fetch the current view's notes now (a live save/update/forget, a
    // rejoin's rebuild), bypassing the per-open cache. Only while open.
    function refreshNotes() {
      var info = describe();
      if (info.kind !== 'agent' || !drawer.isOpen()) return;
      loadNotes(info.name, viewSession(), openGen, notesState.status === 'ok');
    }

    // Re-fetch the current agent's rules (an approved rule change, M36 F2 L7). No-op while the
    // drawer is closed or the view is not a named agent; a failure keeps what is shown.
    var rulesToken = 0;
    function refreshRules() {
      var info = describe();
      if (info.kind !== 'agent' || !drawer.isOpen()) return;
      var name = info.name;
      var gen = openGen;
      var token = ++rulesToken;
      fetch('/api/agents/' + encodeURIComponent(name) + '/rules').then(function (r) {
        if (r.status === 404) return { rules: [] };
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }).then(function (body) {
        if (token !== rulesToken || rulesState.gen !== gen || rulesState.agent !== name) return;
        rulesState = { gen: gen, agent: name, status: 'ok', value: (body && body.rules) || [] };
        render();
      }, function () { /* keep the list shown */ });
    }

    // An approved change (M36 F2 L7): the drawer's group for it reloads, or, for the agent's own
    // settings, the agents store is force-read (the drawer re-renders from its subscription).
    function onConfigChanged(e) {
      var d = e.detail;
      var info = describe();
      if (!d || info.kind !== 'agent' || info.name !== d.agent) return;
      if (d.kind === 'rule') refreshRules();
      else if (d.kind === 'routine') refreshRoutines();
      else App.store.get('agents', { force: true }).catch(function () { /* the next load retries */ });
    }
    document.addEventListener(App.approvals.CONFIG_CHANGED, onConfigChanged);

    function viewSession() {
      return (view && view.sessionId) || null;
    }

    function storeStatus(name) {
      var peek = App.store.peek(name);
      if (peek.loaded) return 'ok';
      return storeFailed[name] ? 'error' : 'loading';
    }

    function uses(agent) {
      // A <div> under an h3, not a named <section>: a named section would
      // add a region landmark beside the drawer's own complementary one.
      var box = el('div', { className: 'chat-drawer-uses' }, [
        el('h3', { className: 'chat-drawer-uses-title', text: 'What it can use' })
      ]);
      box.setAttribute('data-testid', 'chat-drawer-uses');

      box.appendChild(App.chat.drawerGroups.rulesGroup(rulesState));
      box.appendChild(App.chat.drawerGroups.notesGroup(notesState));
      box.appendChild(App.chat.drawerParts.routinesGroup(routinesState));

      var kbStatus = storeStatus('knowledge-bases');
      var kbs = [];
      if (kbStatus === 'ok') {
        var kbRows = App.store.peek('knowledge-bases').value;
        var kbIds = arr(agent.kb_ids);
        for (var k = 0; k < kbIds.length; k++) {
          var kb = findBy(kbRows, 'id', kbIds[k]);
          if (kb) kbs.push({ name: String(kb.name || kb.id) });
        }
        kbs.sort(function (a, b) { return a.name.localeCompare(b.name); });
      }
      box.appendChild(group('knowledge', 'Knowledge bases', kbs, kbStatus));

      var mcpStatus = storeStatus('mcp-sources');
      var mcps = [];
      if (mcpStatus === 'ok') {
        var sources = App.store.peek('mcp-sources').value;
        var ids = arr(agent.mcp_source_ids);
        for (var m = 0; m < ids.length; m++) {
          var source = findBy(sources, 'id', ids[m]);
          if (!source) continue; // unknown ids (the self-configuration loopback) are skipped
          var n = App.usage.mcpToolCount(source);
          mcps.push({
            name: String(source.name || source.id),
            meta: n === null ? '' : n + (n === 1 ? ' tool' : ' tools')
          });
        }
        mcps.sort(function (a, b) { return a.name.localeCompare(b.name); });
      }
      box.appendChild(group('mcp', 'MCP servers', mcps, mcpStatus));

      box.appendChild(group('secrets', 'Secrets', App.chat.drawerParts.grantedSecrets(agent), storeStatus('secrets')));
      var toolItems = [];
      var toolStatus = configs.status === 'ok' ? 'ok' : configs.status === 'error' ? 'error' : 'loading';
      if (toolStatus === 'ok') {
        var groups = builtinGroups(agent, configs.value);
        for (var g = 0; g < groups.length; g++) {
          toolItems.push({ name: groups[g].label, meta: groups[g].enabled + ' of ' + groups[g].total });
        }
      }
      box.appendChild(group('tools', 'Built-in tools', toolItems, toolStatus));
      box.appendChild(App.chat.drawerParts.richVisualsGroup(agent));
      var selfBox = el('div', { className: 'chat-drawer-group', dataset: { group: 'self-configuration' } }, [
        el('h4', { className: 'chat-drawer-group-label', text: 'Self-configuration' })
      ]);
      var selfText = 'Loading…';
      if (selfConf.status === 'ok') selfText = selfConf.value && selfConf.value.enabled ? 'On' : 'Off';
      else if (selfConf.status === 'error') selfText = 'Couldn\'t load';
      selfBox.appendChild(el('p', {
        className: selfConf.status === 'ok' ? 'chat-drawer-value' : 'chat-drawer-none',
        text: selfText
      }));
      box.appendChild(selfBox);
      return box;
    }

    function renderContent(info) {
      var providers = App.store.peek('providers').value;
      content.textContent = '';
      current = null;
      ggView = info.kind === 'gleepglorp';
      var name = '';
      var type = null;
      if (info.kind === 'agent') {
        name = info.name;
        current = info.name;
        type = App.chat.agentPicker.providerType(info.row, providers);
        if (info.row.description) {
          content.appendChild(el('p', { className: 'chat-drawer-description', text: String(info.row.description) }));
        }
        var provider = info.row.provider_config_id ? findBy(providers, 'id', info.row.provider_config_id) : null;
        var factPairs = [
          ['Model', info.row.llm_model ? String(info.row.llm_model) : '—', 'chat-drawer-mono'],
          ['Provider', provider ? String(provider.name || provider.id) : '—'],
          ['Chats', String(chatsCount(info.name))]
        ];
        var routineText = routineFact();
        if (routineText) factPairs.push(['Routine', routineText]);
        var factsEl = facts(factPairs);
        if (routineText) factsEl.lastElementChild.setAttribute('data-testid', 'chat-drawer-routine');
        content.appendChild(factsEl);
        var needsEl = App.chat.drawerParts.noticesGroup(info.name, info.row.notices);
        if (needsEl) content.appendChild(needsEl);
        content.appendChild(uses(info.row));
      } else if (info.kind === 'gleepglorp') {
        name = App.chat.GLEEPGLORP;
        type = 'builtin';
        App.chat.drawerParts.gleepglorpBody(App.chat.gleepglorpSettings(), providers).forEach(function (n) { content.appendChild(n); });
      } else if (info.kind === 'deleted') {
        name = info.name;
        content.appendChild(note('This agent no longer exists'));
        content.appendChild(facts([['Chats', String(chatsCount(info.name))]]));
      } else if (info.kind === 'loading') {
        content.appendChild(note('Loading…'));
      }
      nameEl.textContent = name;
      nameEl.hidden = !name;
      var kind = type && App.ui.badge.KINDS.indexOf(type) !== -1 ? type : 'unknown';
      badge.set({ kind: kind, text: ggView ? 'Built in' : (type || '') });
      footerEl.hidden = info.kind !== 'agent' && !ggView;
      settingsBtn.lastChild.nodeValue = ggView ? 'Open GleepGlorp settings' : 'Open agent settings';
    }

    // The per-open fetches (only while open, for a known agent).
    function ensureFetches(info) {
      if (!drawer.isOpen() || info.kind !== 'agent') return;
      var gen = openGen;
      if (configs.gen !== gen) {
        configs = { gen: gen, status: 'pending', value: null };
        App.api.fetchJson('/api/tools/configs').then(function (rows) {
          if (configs.gen !== gen) return;
          configs = { gen: gen, status: 'ok', value: rows };
          render();
        }, function () {
          if (configs.gen !== gen) return;
          configs = { gen: gen, status: 'error', value: null };
          render();
        });
      }
      if (selfConf.gen !== gen || selfConf.agent !== info.name) {
        var agent = info.name;
        selfConf = { gen: gen, agent: agent, status: 'pending', value: null };
        App.api.fetchJson('/api/agents/' + encodeURIComponent(agent) + '/self-configuration').then(function (body) {
          if (selfConf.gen !== gen || selfConf.agent !== agent) return;
          selfConf = { gen: gen, agent: agent, status: 'ok', value: body };
          render();
        }, function () {
          if (selfConf.gen !== gen || selfConf.agent !== agent) return;
          selfConf = { gen: gen, agent: agent, status: 'error', value: null };
          render();
        });
      }
      if (rulesState.gen !== gen || rulesState.agent !== info.name) {
        var ruleAgent = info.name;
        rulesState = { gen: gen, agent: ruleAgent, status: 'pending', value: null };
        // A raw fetch, not fetchJson: a 404 (no stored row) means an empty
        // list, while any other failure is the error state.
        fetch('/api/agents/' + encodeURIComponent(ruleAgent) + '/rules').then(function (r) {
          if (r.status === 404) return { rules: [] };
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        }).then(function (body) {
          if (rulesState.gen !== gen || rulesState.agent !== ruleAgent) return;
          rulesState = { gen: gen, agent: ruleAgent, status: 'ok', value: (body && body.rules) || [] };
          render();
        }, function () {
          if (rulesState.gen !== gen || rulesState.agent !== ruleAgent) return;
          rulesState = { gen: gen, agent: ruleAgent, status: 'error', value: null };
          render();
        });
      }
      var sid = viewSession();
      if (notesState.gen !== gen || notesState.agent !== info.name || notesState.session !== sid) {
        var same = notesState.gen === gen && notesState.agent === info.name && notesState.status === 'ok';
        loadNotes(info.name, sid, gen, same);
      }
      if (routinesState.gen !== gen || routinesState.agent !== info.name) {
        var rSame = routinesState.gen === gen && routinesState.agent === info.name && routinesState.status === 'ok';
        loadRoutines(info.name, gen, rSame);
      }
      ['knowledge-bases', 'mcp-sources', 'secrets'].forEach(function (name) {
        if (storeTried[name] === gen) return;
        storeTried[name] = gen;
        App.store.get(name).then(function () {
          storeFailed[name] = false;
          render(); // a cached get notifies nobody
        }, function () {
          if (storeTried[name] !== gen) return;
          storeFailed[name] = true;
          render();
        });
      });
    }

    // Render key (M34 F2 L03): view, mode, wants-open, and while open the Chats count.
    var lastKey = null;
    function renderKey() {
      var want = active && !!view && !!state.open[state.mode];
      var info = want ? describe() : { kind: 'none' };
      var n = info.kind === 'agent' || info.kind === 'deleted' ? chatsCount(info.name) : null;
      // A GleepGlorp view re-renders on a settings push.
      return JSON.stringify([view, state.mode, want, n, info.kind === 'gleepglorp' ? App.chat.gleepglorpSettings() : null]);
    }

    function render() {
      var info = describe();
      renderContent(info); lastKey = renderKey(); ensureFetches(info);
    }

    // Visibility: the one place the drawer opens, closes and changes mode.
    function apply() {
      var focusIn = focusOnOpen;
      focusOnOpen = false;
      drawer.setMode(state.mode);
      // Without a chat or while inactive the fill state does not survive (session-only).
      if (state.mode === 'fill' && (!active || !view)) state.open.fill = false;
      var want = active && !!view && !!state.open[state.mode];
      var was = drawer.isOpen();
      // The cover is set (and the toggle hidden) before the drawer opens and cleared before it
      // closes, so focus never moves while the panes are inert.
      syncCover(want);
      applying = true;
      if (want) drawer.open(toggle, { focus: focusIn });
      else drawer.close();
      applying = false;
      // Idempotent; once the drawer is shown it moves focus off <body> or an inert pane.
      if (want) syncCover(true);
      else if (was && App.shellPane.visiblePane() && (!document.activeElement || document.activeElement === document.body)) {
        App.shellPane.focusVisible(); // the toggle is hidden (no chat): focus the visible pane
      }
      if (want && !was) openGen += 1;
      if ((want && !was) || renderKey() !== lastKey) render();
    }

    var mql = typeof window.matchMedia === 'function' ? window.matchMedia(PUSH_QUERY) : null;
    var mqlNarrow = typeof window.matchMedia === 'function' ? window.matchMedia(NARROW_QUERY) : null;
    function modeFor() {
      if (mqlNarrow && mqlNarrow.matches) return 'fill';
      return mql && !mql.matches ? 'overlay' : 'push';
    }
    function onMedia() {
      var prev = state.mode;
      state.mode = modeFor();
      // Entering fill always starts closed (a resize from wide never opens the panel).
      if (state.mode === 'fill' && prev !== 'fill') state.open.fill = false;
      apply();
    }
    state.mode = modeFor();
    [mql, mqlNarrow].forEach(function (q) {
      if (!q) return;
      if (typeof q.addEventListener === 'function') q.addEventListener('change', onMedia);
      else if (typeof q.addListener === 'function') q.addListener(onMedia);
    });

    var unsubs = [];
    function subscribeStore(name) {
      unsubs.push(App.store.subscribe(name, function () {
        if (name === 'sessions' ? renderKey() !== lastKey : drawer.isOpen()) render();
      }));
    }
    for (var s = 0; s < STORES.length; s++) subscribeStore(STORES[s]);
    // GleepGlorp's settings are a module of their own, not an App.store collection (M36 L04).
    unsubs.push(App.gleepglorp.subscribe(function () { if (renderKey() !== lastKey) render(); }));

    function destroy() {
      document.removeEventListener(App.approvals.CONFIG_CHANGED, onConfigChanged);
      for (var i = 0; i < unsubs.length; i++) unsubs[i]();
      unsubs = [];
      [mql, mqlNarrow].forEach(function (q) {
        if (!q) return;
        if (typeof q.removeEventListener === 'function') q.removeEventListener('change', onMedia);
        else if (typeof q.removeListener === 'function') q.removeListener(onMedia);
      });
      App.shellPane.setCovered('chat-drawer', false);
      drawer.destroy();
      if (toggle.parentNode) toggle.parentNode.removeChild(toggle);
    }

    apply();
    return {
      drawer: drawer,
      toggle: toggle,
      render: function (next) {
        view = next || null;
        // Leaving a chat, a pending chat or another chat drops the join metadata.
        if (!view || !view.sessionId || view.sessionId !== sessionMeta.session) {
          sessionMeta = { session: null, meta: null };
        }
        apply();
      },
      setActive: function (on) {
        active = !!on;
        apply();
      },
      refreshNotes: refreshNotes,
      refreshRoutines: refreshRoutines,
      refreshRules: refreshRules,
      setSessionMetadata: setSessionMetadata,
      destroy: destroy
    };
  }

  window.App.chat.agentDrawer = {
    create: create,
    isToolEnabled: isToolEnabled,
    builtinGroups: builtinGroups,
    STORAGE_KEY: STORAGE_KEY
  };
})();
