// App.studio.agentsList -- the Agents list column and agent selection (M31 F2
// L03, DD1): the App.ui.listPane (rows, filter, "New"), the detail pane's empty
// state, row-focus helpers, selection (doSelect, replaceWith*, create mode),
// renderEmptyEditor and the pending-agent rule (resolvePendingAgent,
// tryConsumePendingSelect). Moved verbatim out of studio.js; a factory studio
// calls once in init, AFTER the controller (selection calls renderEditor):
//
//   var list = App.studio.agentsList.create(ctx);
//
// ctx (studio -> module): self, state, listHost (the sidebar host the pane is
// mounted in), editorEl, sectionContent() (the detail host), agentData and
// controller (handles), updateContentVisibility, setActiveSection, writeUrl,
// closeOpenItem. The pending-agent rule reads `state.bootLoad` (the init() load
// while it is in flight; the shell writes it).
//
// handle (module -> studio): isOpen(), create(), destroy() (the pane's lifetime,
// owned by setActiveSection), resetEmpty() (drop the empty-state node before a
// fresh section render), render(scroll) (renderAgentList), selection()
// (listSelection), focusNear(index), indexOf(name) (visibleIndexOf),
// renderEmptyEditor(), doSelect(agent), enterCreate() (doEnterCreateMode),
// syncSelection(), clearFilter(), replaceWithAgent(agent),
// replaceWithAgentsRoot(), resolvePending(), tryConsumePending(fresh).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var agentsListHost = ctx.listHost;
    var editorEl = ctx.editorEl;
    var sectionContentEl = ctx.sectionContent(); // created once by the shell, never replaced
    var agentData = ctx.agentData;
    var renderEditor = ctx.controller.renderEditor;
    var updateContentVisibility = ctx.updateContentVisibility;
    var setActiveSection = ctx.setActiveSection;
    var writeUrl_ = ctx.writeUrl;
    var closeOpenItem = ctx.closeOpenItem;

    var agentsList = null;      // the Agents App.ui.listPane while on Agents
    var newAgentBtn = null;     // its "New" title-row action
    var agentsEmptyEl = null;   // the detail pane's empty state (no agent open)
    var agentsEmptyKind = null; // 'some' | 'none' -- which copy agentsEmptyEl shows


    // The Agents start page's intro.
    var AGENTS_INTRO = 'An agent is an assistant you set up for a kind of work. Each one has a ' +
      'model from one of your providers, instructions that shape how it behaves, and the tools ' +
      'and knowledge it can use. Chat with an agent from Chats, or connect it to a chat ' +
      'platform with a connector.';

    // ── Agents list column + empty detail state (M25 F3 L3, DD4) ──────────

    // The agent the list marks selected: the pending hydrate target, else the
    // open agent; none in create mode or outside Agents.
    function listSelection() {
      if (self._activeSection !== 'agents' || self._createMode) return null;
      if (self._pendingSelectName) return self._pendingSelectName;
      return self._selectedAgent ? self._selectedAgent.name : null;
    }

    function providerFor(agent) {
      if (!agent || !agent.provider_config_id) return null;
      var providers = self._allProviders || [];
      for (var i = 0; i < providers.length; i++) {
        if (providers[i].id === agent.provider_config_id) return providers[i];
      }
      return null;
    }

    // One list row. The provider dot is an aria-hidden .badge--{type} disc;
    // the provider's name joins the row's accessible name (A31), so the dot
    // never carries meaning by colour alone. The filter matches the name, the
    // model id and the provider TYPE slug (A16), not the display name.
    function attentionChip() {
      var chip = App.ui.chip({ label: 'Needs attention', tone: 'warning', size: 'sm' });
      chip.setAttribute('aria-hidden', 'true');
      return chip;
    }

    function agentItem(agent) {
      var needs = !!(agent.notices && agent.notices.length);
      var provider = providerFor(agent);
      var type = provider && provider.type ? String(provider.type) : '';
      var dot = App.ui.badge.dot(provider ? type : null);
      var model = agent.llm_model || '';
      return {
        id: agent.name,
        label: agent.name,
        meta: model,
        href: App.router.href({ destination: 'agents', id: agent.name }),
        testid: 'agent-item',
        // A trailing separator when the model follows, so the name reads
        // "name, Provider, model", never "Provider model" (the flight-end review).
        // A row with tool-override notices (sortie 07 L05, DD11) also carries ", needs
        // attention" in its name, once: the visible chip is aria-hidden so it is not read twice.
        nameSuffix: ', ' + (provider ? provider.name || type : 'no provider') +
          (needs ? ', needs attention' : '') + (model ? ',' : ''),
        badges: needs ? [attentionChip()] : undefined,
        notices: needs ? agent.notices.length : 0,
        lead: dot,
        filterText: (agent.name + ' ' + model + ' ' + type).toLowerCase()
      };
    }

    // The predicate runs once per row per keystroke, so the needle is derived
    // once per query.
    var filterQuery = null;
    var filterNeedle = '';
    function agentFilter(item, query) {
      if (query !== filterQuery) {
        filterQuery = query;
        filterNeedle = String(query || '').trim().toLowerCase();
      }
      return !filterNeedle || item.filterText.indexOf(filterNeedle) !== -1;
    }

    // "New" (the title-row action and the empty state's action) is a user
    // INTENT: a go() to the create route, so the router's leave guard asks
    // once about an open dirty agent. With the create form already open on
    // its route there is nothing to navigate to: focus returns to the name
    // field and nothing re-renders.
    function goCreateAgent(e) {
      var cur = App.router.current();
      if (self._createMode && cur && cur.route === 'agents/~new') {
        focusNameField();
        return;
      }
      App.router.go(App.router.href({ destination: 'agents', create: true }),
        { opener: (e && e.currentTarget) || null });
    }

    function focusNameField() {
      var nameInput = editorEl.querySelector('#studio-name');
      if (nameInput) nameInput.focus();
    }

    function createAgentsList() {
      newAgentBtn = App.ui.button({
        variant: 'secondary',
        size: 'sm',
        icon: 'plus',
        label: 'New',
        ariaLabel: 'New agent',
        testid: 'new-agent-btn',
        onClick: goCreateAgent
      });
      agentsList = App.ui.listPane({
        title: 'Agents',
        count: true,
        actions: [newAgentBtn],
        filter: {
          label: 'Filter agents',
          placeholder: 'Filter by name, model or provider',
          predicate: agentFilter,
          testid: 'agents-filter'
        },
        emptyText: function (q) {
          if (q) return 'No agents match "' + q + '".';
          return self._agentsLoaded ? 'No agents yet.' : 'Loading agents\u2026';
        },
        rowStyle: 'agents',
        testid: 'agents-list'
      });
      agentsListHost.appendChild(agentsList.el);
    }

    // Everything a row shows, as one string (the dot is compared by its class).
    var lastItemsSig = null;
    function itemsSignature(items) {
      return JSON.stringify(items.map(function (it) {
        return [it.id, it.label, it.meta, it.href, it.nameSuffix, it.filterText,
          it.lead ? it.lead.className : '', it.notices];
      }));
    }

    function destroyAgentsList() {
      lastItemsSig = null;
      if (!agentsList) return;
      agentsList.destroy();
      agentsListHost.textContent = '';
      agentsList = null;
      newAgentBtn = null;
    }

    // The one builder of the Agents list (design review item 6): items from
    // self._agents (list- or detail-shaped; only name, llm_model,
    // provider_config_id and notices are read) and self._allProviders, sorted A-Z, then
    // the selection -- setSelected AFTER setItems, so a refetch that lands
    // mid-select keeps the right row. A no-op off Agents (no pane). `scroll`
    // (a load or a navigation) brings the selected row into view (A26); the
    // first fill does too. Store notifications pass nothing, so a user
    // scrolling the list is never yanked back.
    function renderAgentList(scroll) {
      if (!agentsList) return;
      var wasEmpty = agentsList.getItems().length === 0;
      var agents = (self._agents || []).slice().sort(function (a, b) {
        return String(a.name).localeCompare(String(b.name));
      });
      var items = [];
      for (var i = 0; i < agents.length; i++) items.push(agentItem(agents[i]));
      // A reload that changes nothing a row shows must not rebuild the rows
      // (a late list fetch used to detach the row a user was about to use).
      var sig = itemsSignature(items);
      if (sig !== lastItemsSig || agentsList.getItems().length !== items.length) {
        agentsList.setItems(items);
        lastItemsSig = sig;
      }
      agentsList.setSelected(listSelection());
      if (scroll || (wasEmpty && items.length)) scrollAgentsToSelected();
      renderAgentsEmpty();
    }

    // Scroll the selected row into view now, and once more when the web fonts
    // are ready: on a cold load the rows reflow when Geist arrives (a fraction
    // of a pixel per row adds up over 25 rows), which would push a row scrolled
    // in with fallback metrics back out of view. After the first load the
    // fonts are ready, so the second scroll lands on the same position.
    function scrollAgentsToSelected() {
      var pane = agentsList;
      pane.scrollToSelected();
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () {
          if (agentsList === pane) pane.scrollToSelected();
        });
      }
    }

    // DD3 (c): every Agents hydrate re-syncs the list's selection (and scrolls
    // to it) without rebuilding the rows.
    function syncAgentSelection() {
      if (!agentsList) return;
      agentsList.setSelected(listSelection());
      scrollAgentsToSelected();
    }

    // The real App.studio.clearAgentFilter (M25 F4 L6, AC12; the stub above
    // the area is a no-op until here). Silent (listPane.setQuery announces
    // nothing), then the selected row is scrolled into view: the caller runs
    // it AFTER its go() commits, when the hydrate has already selected the
    // agent but its row may have been filtered out.
    function clearAgentFilter() {
      if (!agentsList) return;
      agentsList.setQuery('');
      scrollAgentsToSelected();
    }

    // The detail pane with no agent open: a pane-size empty state whose copy
    // depends on whether any agent exists. Nothing before the first load.
    // Only its own node is replaced, never the rest of sectionContentEl (the
    // loadAll failure line lives there too).
    function renderAgentsEmpty() {
      if (self._activeSection !== 'agents') return;
      var kind = !self._agentsLoaded ? null : (self._agents.length ? 'some' : 'none');
      if (kind === agentsEmptyKind && (agentsEmptyEl || !kind)) return;
      if (agentsEmptyEl && agentsEmptyEl.parentNode) agentsEmptyEl.parentNode.removeChild(agentsEmptyEl);
      agentsEmptyEl = null;
      agentsEmptyKind = kind;
      if (!kind) return;
      var el = App.ui.util.el;
      agentsEmptyEl = el('div', {
        className: 'start-page'
      }, [
        el('p', { className: 'start-page-text', text: AGENTS_INTRO }),
        el('p', {
          className: 'start-page-text',
          text: kind === 'some' ? 'Pick an agent from the list to edit it.' : 'No agents yet.'
        }),
        App.ui.button({
          variant: 'primary',
          icon: 'plus',
          label: 'New agent',
          testid: 'agent-empty-new',
          onClick: goCreateAgent
        })
      ]);
      if (kind === 'some') agentsEmptyEl.setAttribute('data-testid', 'agent-select-empty');
      else agentsEmptyEl.setAttribute('data-testid', 'agent-empty');
      // After the visible root heading (a sibling) when it is there.
      var rootH1 = sectionContentEl.querySelector(':scope > h1[data-testid="root-heading"]');
      sectionContentEl.insertBefore(agentsEmptyEl, rootH1 ? rootH1.nextSibling : sectionContentEl.firstChild);
    }

    // DD8 focus rule after a delete or a create-form Cancel: the row at
    // `index` among the visible rows (the next one after a removed row), else
    // the previous one, else the list's "New" action.
    function focusAgentRowNear(index) {
      if (!agentsList) return;
      var rows = agentsList.rows(true);
      var target = rows.length ? rows[Math.max(0, Math.min(index, rows.length - 1))] : null;
      if (!target) {
        if (newAgentBtn) newAgentBtn.focus();
        return;
      }
      for (var i = 0; i < rows.length; i++) rows[i].setAttribute('tabindex', rows[i] === target ? '0' : '-1');
      target.focus();
    }

    // The visible-row index the named agent holds (or would hold), read
    // BEFORE a delete: setItems restores focus only to a row that had it.
    function visibleIndexOf(name) {
      if (!agentsList) return 0;
      // Every row, hidden or not, in item order (one row per item).
      var rows = agentsList.rows();
      var items = agentsList.getItems();
      var n = 0;
      for (var i = 0; i < items.length && i < rows.length; i++) {
        if (items[i].id === name) return n;
        if (!rows[i].parentNode.hidden) n++;
      }
      return n;
    }

    // ── Agent selection ──────────────────────────────────────────────

    // F5 leg 04: doSelect / doEnterCreateMode — extracted bodies past the
    // dirty-check so the App.confirmDialog onConfirm callback can invoke
    // the real navigation. The async dialog pattern requires the guard to
    // dispatch the dialog and let onConfirm proceed (the synchronous
    // window.confirm guard-and-return pattern doesn't translate directly).
    function doSelect(agent) {
      // M25 F2 L3 (a): refuse to force-switch sections. Only a user who is
      // still on Agents may open an agent; an async caller (the
      // self-configuration refresh, save-create, the delete fallback) whose
      // user has since moved to another section or destination does nothing.
      var routed = window.App && App.router && App.router.current && App.router.current();
      if (self._activeSection !== 'agents' || (routed && routed.destination !== 'agents')) return;
      var mySelect = ++state.selectSeq;
      // Preserve the current tab when re-selecting the same agent (e.g.,
      // when activate() triggers a refresh after the user is already
      // viewing this agent on a non-default tab). Honor any pending tab
      // from hydrate, otherwise keep the existing _activeTab; only reset
      // to 'general' on a genuine agent change.
      var sameAgent = self._selectedAgent && self._selectedAgent.name === agent.name && !self._createMode;
      var tabToActivate;
      if (self._pendingTabName) {
        tabToActivate = self._pendingTabName;
      } else if (sameAgent) {
        tabToActivate = self._activeTab || 'general';
      } else {
        tabToActivate = 'general';
      }
      self._createMode = false;
      self._selectedAgent = agent;
      // Squawk 0090: the object seated here is the LIST-route cache, which
      // may predate a knowledge-base rename. Block Save until the
      // fresh-agent fetch below resolves and says otherwise, so a save
      // racing the in-flight refresh can't union from it either.
      self._selectedAgentLoaded = false;
      state.dirty = false;
      self._pendingTabName = null;
      self._activeTab = tabToActivate;
      renderAgentList(true);
      // F6 leg 05 — refresh operator-state caches on every agent-edit
      // mount (operator may have flipped a toggle in another tab between
      // agent edits). Render-on-resolve so the Tools tab reflects current
      // disabled state from first paint.
      // F9 L3 (A-L3-1) — also refresh the MCP sources list so a source
      // created on the source-edit page appears in the Tools tab without
      // a manual page reload. F6 L3 (L3-D1, L3-D3) adds two more: the
      // knowledge-base list refresh (mirrors the MCP one), and a fresh
      // fetch of THIS agent — needed because `loadAll()` does not re-run
      // on a Studio section switch, so after a rename performed in the
      // Knowledge section the cached `agent` object here can still hold a
      // pre-rewrite `disabled_tools` entry (collectFormData's ungated-
      // prefix union below reads from `self._selectedAgent`, so it must be
      // current). L3-D7: the fresh-agent fetch carries its own `.catch`
      // that resolves with the passed-in `agent` — this `Promise.all` has
      // no rejection handler anywhere in its chain, so a rejecting member
      // would strand the editor with nothing rendered, which is a worse
      // failure than re-rendering from a stale agent.
      //
      // Squawk 0090: rendering from the stale agent stays (that is the
      // L3-D7 trade-off, and `renderEditor(freshAgent)` below renders the
      // very object the union would read, so the UI remains
      // self-consistent) — what does NOT stay is saving from it. The
      // `.catch` records the failure in `freshAgentLoaded`, which becomes
      // `self._selectedAgentLoaded`; `renderEditor` then shows the
      // load-failure line in the editor header and `checkDirty`/`save` keep Save
      // disabled. Refusing the save is the fix rather than DD-4's
      // omit-the-field shape because `disabled_tools` has NO server-side
      // preserve-on-omit path (`update_agent` preserves only
      // `mcp_overrides`, `self_revision_requires_approval` and `kb_ids`;
      // `AgentConfig.disabled_tools` defaults to `[]`), so omitting it
      // would WIPE every disabled tool — a strictly worse fail-open.
      var freshAgentLoaded = true;
      Promise.all([
        agentData.refreshToolConfigsCache(),
        agentData.refreshMcpSourcesCache(),
        agentData.refreshKnowledgeBasesCache(),
        fetch('/api/agents/' + encodeURIComponent(agent.name))
          .then(function (r) {
            if (!r.ok) throw new Error('fetch fresh agent: HTTP ' + r.status);
            return r.json();
          })
          .catch(function () {
            freshAgentLoaded = false;
            return agent;
          }),
        // Sortie 10: after the fresh agent, so `results[3]` stays the agent.
        agentData.refreshSecretsCache()
      ]).then(function (results) {
        // Stale-then guard (M25 F2 L3 (a)): the user may have left Agents, closed
        // the editor or opened another agent while the fetches were in flight.
        if (mySelect !== state.selectSeq || self._activeSection !== 'agents' || self._createMode) return;
        // L3-D3: the fetch is not enough on its own — reassign
        // self._selectedAgent (and the matching self._agents entry) and
        // render the FETCHED object, not the outer closure's `agent`, or
        // the union below silently keeps reading stale disabled_tools.
        if (!freshAgentLoaded) {
          App.ui.flash('Couldn’t load this agent’s settings.', { error: true });
        }
        var freshAgent = results[3];
        self._selectedAgent = freshAgent;
        self._selectedAgentLoaded = freshAgentLoaded;
        for (var fi = 0; fi < self._agents.length; fi++) {
          if (self._agents[fi].name === freshAgent.name) { self._agents[fi] = freshAgent; break; }
        }
        renderEditor(freshAgent);
        updateContentVisibility();
        writeUrl_();
        App.focusAfter.flush();
      });
    }

    // Agent navigation (M25 F2 L4). Opening an agent is a user INTENT: a list
    // row is an <a href> that App.nav routes through a pushed go(), whose leave
    // guard is the only prompt for unsaved changes. Navigation that is a
    // COMPLETION of something the user already did (save-create, post-delete,
    // the save->delete race, Cancel on the create form) is a bypass go() that
    // REPLACES the current entry: no guard, no extra history entry.
    function replaceWithAgent_(agent) {
      App.router.go(App.router.href({ destination: 'agents', id: agent.name }),
        { replace: true, bypassGuard: true });
    }

    function replaceWithAgentsRoot_() {
      App.router.go(App.router.href({ destination: 'agents' }),
        { replace: true, bypassGuard: true });
    }

    // The create form (M25 F3 L3, DD8): the hydrate target of `agents/~new`
    // (hydrateState calls it as self._enterCreate). Entering it while it is
    // already open re-renders nothing and only refocuses the name field.
    function doEnterCreateMode() {
      if (self._createMode && self._activeSection === 'agents') {
        focusNameField();
        return;
      }
      self._createMode = true;
      self._selectedAgent = null;
      // Squawk 0090: create-mode has no stored agent to union from
      // (`_storedUngatedDisabledNames` returns `[]` — AC-9), so there is
      // nothing stale to guard against; Create must stay enabled.
      self._selectedAgentLoaded = true;
      self._activeTab = 'general';
      state.dirty = false;
      if (self._activeSection !== 'agents') {
        setActiveSection('agents', { writeUrl: false });
      }
      renderAgentList();
      updateContentVisibility();
      // F6 leg 05 — refresh operator-state caches before rendering so the
      // new-agent Tools tab reflects current operator-disabled state.
      // F9 L3 (A-L3-1) — also refresh the MCP sources list so a freshly
      // created source is visible from the new-agent Tools tab without
      // a manual page reload. F6 L3 (L3-D3): the fresh-agent refetch is
      // select-path only — create mode has no agent to fetch — but the
      // knowledge-base refresh goes into both sites.
      // M25 F3 L3: `#agents/~new` is a route, so a cold deep link can land here
      // before loadAll has the providers the form's picker needs; the store
      // read returns the cached list or joins the in-flight load.
      var myCreate = ++state.selectSeq;
      var providersReady = agentData.fetchProviders().then(function (list) {
        self._allProviders = list;
      }, function () { /* keep the prior list; the form still renders */ });
      Promise.all([
        agentData.refreshToolConfigsCache(), agentData.refreshMcpSourcesCache(), agentData.refreshKnowledgeBasesCache(),
        agentData.refreshSecretsCache(), providersReady
      ]).then(function () {
        if (myCreate !== state.selectSeq || self._activeSection !== 'agents' || !self._createMode) return;
        renderEditor(null);
        updateContentVisibility();
        writeUrl_();
        focusNameField();
      });
    }

    // ── Editor rendering ─────────────────────────────────────────────

    function renderEmptyEditor() {
      // Destroys the editor mount (the controller's slot clears the host).
      ctx.controller.destroyEditor();
      state.tabHandle = null;
    }


    // ── Init ─────────────────────────────────────────────────────────

    // Resolves the pending agent (set by hydrateState) against the LOADED list.
    // doSelect, not an inline-gated select: a hydrate is reached through the
    // router, whose leave guard has already asked about unsaved changes, so it
    // must never prompt a second time. Re-opening the same agent re-renders it
    // fresh from the server (a restore after a discarded edit shows saved
    // state, not the abandoned form).
    //
    // An id that is not in the loaded list is DEAD (deleted meanwhile, or a
    // stale link): it is never kept pending -- the URL heals to the Agents root
    // in place and the root renders (no editor, no endless pending state).
    function resolvePendingAgent() {
      var name = self._pendingSelectName;
      if (!name) return;
      if (self._activeSection !== 'agents') return;
      var target = null;
      for (var i = 0; i < self._agents.length; i++) {
        if (self._agents[i].name === name) { target = self._agents[i]; break; }
      }
      self._pendingSelectName = null;
      if (target) {
        doSelect(target);
        return;
      }
      self._pendingTabName = null;
      self._pendingMcpAgentSourceId = null;
      self._activeTab = 'general';
      closeOpenItem();
      renderAgentList();
      updateContentVisibility();
      App.router.sync('studio', 'agents');
    }

    // `fresh` (a traversal, a typed hash or boot) resolves against a FRESH list
    // fetch -- the cached list may still hold an agent deleted since. A non-fresh
    // (intent) hydrate uses the cached list; before the first load has resolved
    // it waits for it.
    function tryConsumePendingSelect(fresh) {
      if (!self._pendingSelectName) return;
      var name = self._pendingSelectName;
      if (!fresh && self._agentsLoaded) {
        resolvePendingAgent();
        return;
      }
      var onLoaded = function () {
        if (self._pendingSelectName !== name) return;  // superseded or already resolved
        resolvePendingAgent();
      };
      if (state.bootLoad) {
        // init()'s own load: it reports its failure itself.
        state.bootLoad.then(onLoaded, function () {});
        return;
      }
      agentData.loadAll().then(onLoaded).catch(function (err) {
        agentData.showLoadAllError(err, { nonDestructive: true });
      });
    }

    return {
      isOpen: function () { return !!agentsList; },
      create: createAgentsList,
      destroy: destroyAgentsList,
      resetEmpty: function () {
        agentsEmptyEl = null;
        agentsEmptyKind = null;
      },
      render: renderAgentList,
      selection: listSelection,
      focusNear: focusAgentRowNear,
      indexOf: visibleIndexOf,
      renderEmptyEditor: renderEmptyEditor,
      doSelect: doSelect,
      enterCreate: doEnterCreateMode,
      syncSelection: syncAgentSelection,
      clearFilter: clearAgentFilter,
      replaceWithAgent: replaceWithAgent_,
      replaceWithAgentsRoot: replaceWithAgentsRoot_,
      resolvePending: resolvePendingAgent,
      tryConsumePending: tryConsumePendingSelect
    };
  }

  window.App.studio.agentsList = { create: create };
})();
