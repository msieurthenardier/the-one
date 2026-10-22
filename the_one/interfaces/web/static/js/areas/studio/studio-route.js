// App.studio.route -- the studio area's hash-routing serialize / hydrate
// (M31 F2 L02a, DD1). Moved verbatim out of studio.js; the area's
// serializeState / hydrateState are one-line delegations:
//
//   serializeState: function () { return App.studio.route.serialize(this); },
//   hydrateState: function (sub, opts) { return App.studio.route.hydrate(this, sub, opts); },
//
// STATELESS: both functions take the area object (`self`) and read and write
// only its `_`-prefixed fields and hooks (`_activeSection`, `_pendingSelectName`,
// `_closeOpenItem`, the defineProperty getters over studio's `state`, ...). It is
// deliberately not a create(ctx) module: the router may call hydrateState
// before the area's init has run, and every hook is guarded
// (`self._closeOpenItem || function () {}`), which must survive.
window.App = window.App || {};
window.App.studio = window.App.studio || {};

App.studio.route = {
  // ── serialize ──
  // serializeState branch order (explicit):
  //   0. _activeSection === 'library' → 'library' (the Library root, the start
  //      page: nothing open in any group; DD1 of the library-root sortie). A
  //      group section with nothing open also returns 'library' (the bare
  //      section subs are never produced; DD2).
  //   0b. _activeSection === 'providers' → 'providers/new' | 'providers/<id>'
  //      (the providers section module's serialize(), sortie 02) | 'library'
  //   1. _activeSection === 'knowledge' → 'knowledge/new' (the create form,
  //      checked FIRST; M25 F3 L4a) | 'knowledge/{kb_id}' | 'knowledge'
  //      (Flight 6 leg 1, L1-D1 — mirrors the mcp-sources deep-link shape)
  //   2. _activeSection === 'connectors' → 'connectors/new' | 'connectors/<id>'
  //      | 'connectors' (M25 F3 L4a, DD8: connector URLs, MCP's pending shape)
  //   3. _activeSection === 'mcp-sources' → 'mcp-sources' | 'mcp-sources/new'
  //      | 'mcp-sources/<id>' (post-F2 retrofit; relocated from admin)
  //   4. _activeSection === 'agents' && createMode → 'agents/~new' (M25 F3
  //      L3, DD8: the create route; checked before the pending/selected agent)
  //   5. _activeSection === 'agents' && agent pending or selected →
  //      'agents/<encoded-name>/<tab>'   (F5 leg 03 — appended /{tab})
  //   6. otherwise (no agent) → 'agents'
  //
  // Agent-name segments go through agentSeg: encodeURIComponent leaves `~`
  // alone, so a leading `~` is written as `%7E` -- an agent named `~new` must
  // never serialise to the create sub.
  //
  // F5 leg 03 extends branch 3 by appending the active tab segment so the
  // URL reflects the editor's tab state. Defaults to 'general'. The F3
  // router's serialize-after-hydrate path performs the
  // #studio/agents/{name} → #studio/agents/{name}/general upgrade for free
  // (no new redirect logic in studio.js).
  serialize: function (self) {
    function agentSeg(name) {
      var enc = encodeURIComponent(name);
      return enc.charAt(0) === '~' ? '%7E' + enc.slice(1) : enc;
    }
    // The Library root (DD1): the start page, nothing open in any group.
    if (self._activeSection === 'library') return 'library';
    // Providers (sortie 02): the section module owns the item state, so the sub
    // is its serialize() (null at no item -> the root).
    if (self._activeSection === 'providers') {
      return (self._providersSection && self._providersSection.serialize()) || 'library';
    }
    if (self._activeSection === 'knowledge') {
      if (self._kbCreateMode) return 'knowledge/new';
      if (self._selectedKbId) return 'knowledge/' + encodeURIComponent(self._selectedKbId);
      return 'library';
    }
    // M25 F3 L4a (DD8): connectors are deep-link-aware, on the mcp-sources
    // pattern below (Mission 23 Flight 2's URL-less DD-9 trade-off is gone).
    if (self._activeSection === 'connectors') {
      if (self._connectorFormMode === 'add') return 'connectors/new';
      if (self._connectorFormMode === 'edit' && self._editingConnector) {
        return 'connectors/' + encodeURIComponent(self._editingConnector.id);
      }
      // Hydrate-vs-fetch race: the pending id survives until it resolves, so
      // a cold deep link is never synced to the section root early.
      if (self._pendingConnectorFormMode === 'add') return 'connectors/new';
      if (self._pendingConnectorId) {
        return 'connectors/' + encodeURIComponent(self._pendingConnectorId);
      }
      return 'library';
    }
    if (self._activeSection === 'mcp-sources') {
      if (self._mcpSourceFormMode === 'add') return 'mcp-sources/new';
      if (self._mcpSourceFormMode === 'edit' && self._editingMcpSource) {
        return 'mcp-sources/' + encodeURIComponent(self._editingMcpSource.id);
      }
      // Hydrate-vs-fetch race: pending id known but source not yet loaded.
      if (self._pendingMcpSourceFormMode === 'add') return 'mcp-sources/new';
      if (self._pendingMcpSourceId) {
        return 'mcp-sources/' + encodeURIComponent(self._pendingMcpSourceId);
      }
      return 'library';
    }
    // The create form (DD8). An agent hydrate closes it (hydrateState), so it
    // never coexists with a pending selection.
    if (self._activeSection === 'agents' && self._createMode) return 'agents/~new';
    // A pending selection wins over the agent currently open: an item hydrate
    // (go(), traversal, typed hash) names the target BEFORE doSelect seats it,
    // and a fresh hydrate resolves it only after the list fetch, so the open
    // agent must not overwrite the URL that was just written.
    if (self._activeSection === 'agents' && self._pendingSelectName) {
      return 'agents/' + agentSeg(self._pendingSelectName) +
        '/' + (self._activeTab || 'general') +
        (self._activeTab === 'mcps' && self._pendingMcpAgentSourceId
          ? '/' + encodeURIComponent(self._pendingMcpAgentSourceId) : '');
    }
    if (self._activeSection === 'agents' && self._selectedAgent) {
      var base = 'agents/' + agentSeg(self._selectedAgent.name) +
        '/' + (self._activeTab || 'general');
      // F8 L3 Patch B — when on the MCPs tab AND a source-id is selected,
      // append it so refresh preserves the per-attachment editor view.
      if (self._activeTab === 'mcps' && self._selectedMcpAgentSourceId) {
        return base + '/' + encodeURIComponent(self._selectedMcpAgentSourceId);
      }
      return base;
    }
    return 'agents';
  },

  // hydrateState parses sub and drives the area to exactly that sub. It is
  // called by the router (App.router, commit-sequence step 7) with the AREA-level
  // sub of the destination being shown: `agents[/...]` (Agents destination) or
  // `library` | `providers|knowledge|mcp-sources|connectors/{new|id}` (Library: `library`
  // is the root; a bare group sub is the router's alias for it). After hydrate returns,
  // the router calls serializeState and `sync`s the URL (idempotent), so
  // hydrate MUST NOT write the URL itself -- hence {writeUrl: false}.
  //
  // Section-root subs ('agents', 'library')
  // render EXACTLY the root: any open item or create form is closed
  // (closeOpenItem). Item subs open the item through the pending-* paths.
  // M25 F3 L4a: 'knowledge/new' (the knowledge-base create form) and
  // 'connectors/new' | 'connectors/{id}' (connector URLs, on the MCP pending
  // shape) join 'mcp-sources/new' | 'mcp-sources/{id}'; each `new` sub is
  // matched before its item prefix. Every Library hydrate ends with the list
  // pane's selection sync (DD3 (c)).
  //
  // M25 F2 L3 (a): the previous section is captured BEFORE the section
  // changes and passed to _setActiveSection, which owns the outgoing-section
  // cleanup. hydrateState used to assign `_activeSection` itself, so inside
  // _setActiveSection prevSection always equalled section on this path and the
  // cleanup never ran -- the root of the Agents/Library leak.
  //
  // M25 F3 L3 (DD8): 'agents/~new' is the create route, compared RAW before
  // any decode (a name's leading `~` arrives as %7E). It closes the open item
  // unless the create form is already open, which is re-entered without a
  // re-render (a repeated "New" only refocuses the name field). An agent sub
  // closes an open create form (the router's guard has already asked).
  // Every Agents hydrate ends with the list-pane selection sync (DD3 (c)).
  //
  // F5 leg 03: extended to parse 'agents/<name>/<tab>'. Four cases:
  //   - 'agents/{name}'         → activeTab='general' (router rewrites URL)
  //   - 'agents/{name}/'        → activeTab='general' (defensive trailing-slash)
  //   - 'agents/{name}/general|knowledge|mcps|tools' → use that tab
  //   - 'agents/{name}/<other>' → defensively default to 'general'
  // Encoding note: agent names with literal '/' are encoded as '%2F' by
  // encodeURIComponent, so rest.indexOf('/') unambiguously finds the segment
  // separator.
  hydrate: function (self, sub, opts) {
    // `fresh` is the router's hydrate ORIGIN (M25 F2 L4): true for a traversal,
    // a typed hash and boot -- an item named by the URL may have been deleted
    // since, so it is resolved against a FRESH fetch (a dead id heals to the
    // section root); false for an intent go() -- the cached list the user just
    // clicked in is used, nothing is refetched and the section root is not
    // re-rendered.
    var fresh = !!(opts && opts.fresh);
    var section = 'agents';
    var prev = self._activeSection;
    var pendingMcpAgentSourceId = null;
    var pending = null;
    var pendingTab = 'general';
    var pendingMcpSourceId_local = null;
    var pendingMcpSourceFormMode_local = null;
    var pendingConnectorId_local = null;
    var pendingConnectorFormMode_local = null;
    var pendingProviderId_local = null;
    var pendingProviderMode_local = null;
    var createRoute = false;
    var kbCreateRoute = false;
    var kbCreateWasOpen = false;
    var closeOpenItem = self._closeOpenItem || function () {};
    // The first id segment of an item sub ('<section>/<id>[/...]'), decoded.
    function firstSeg(rest) {
      if (rest.charAt(rest.length - 1) === '/') rest = rest.slice(0, -1);
      var idx = rest.indexOf('/');
      if (idx !== -1) rest = rest.slice(0, idx);
      return rest ? decodeURIComponent(rest) : null;
    }
    if (sub === 'library' || sub === 'providers' || sub === 'knowledge' || sub === 'connectors' || sub === 'mcp-sources') {
      // The Library root (DD1): the start page. Closing the open item bumps
      // editorGen, so a save resolving after a breadcrumb go cannot move the
      // URL back to the item. (A bare section sub is the router's alias for
      // it and never arrives; treated as the root defensively.)
      section = 'library';
      closeOpenItem();
    } else if (sub === 'providers/new') {
      // Matched BEFORE the item prefix (sortie 02): never a provider whose id is "new".
      section = 'providers';
      pendingProviderMode_local = 'add';
    } else if (sub && sub.indexOf('providers/') === 0) {
      section = 'providers';
      pendingProviderMode_local = 'edit';
      pendingProviderId_local = firstSeg(sub.slice('providers/'.length));
    } else if (sub === 'knowledge/new') {
      // The create form (M25 F3 L4a, DD8), matched BEFORE the item prefix so
      // it never reads as a knowledge base whose id is "new". It closes the
      // open item unless the create form is already open (a repeated Add only
      // refocuses it); the flag is set before the section renders, so the
      // form is what renders.
      section = 'knowledge';
      kbCreateRoute = true;
      kbCreateWasOpen = prev === 'knowledge' && !!self._kbCreateMode;
      if (!kbCreateWasOpen) closeOpenItem();
      self._kbCreateMode = true;
    } else if (sub && sub.indexOf('knowledge/') === 0) {
      // Flight 6 leg 1 (L1-D1): direct-load on knowledge/{kb_id} — parse
      // the id so the detail view opens on refresh, mirroring the
      // mcp-sources/{id} parsing immediately below.
      section = 'knowledge';
      // An item closes an open create form (the router's guard has asked).
      if (self._kbCreateMode) closeOpenItem();
      self._kbFresh = fresh;  // read once by renderKnowledgeDetailView
      self._selectedKbId = firstSeg(sub.slice('knowledge/'.length));
    } else if (sub === 'connectors/new') {
      // Matched BEFORE the item prefix (M25 F3 L4a, DD8).
      section = 'connectors';
      pendingConnectorFormMode_local = 'add';
    } else if (sub && sub.indexOf('connectors/') === 0) {
      section = 'connectors';
      pendingConnectorFormMode_local = 'edit';
      pendingConnectorId_local = firstSeg(sub.slice('connectors/'.length));
    } else if (sub === 'mcp-sources/new') {
      section = 'mcp-sources';
      pendingMcpSourceFormMode_local = 'add';
    } else if (sub && sub.indexOf('mcp-sources/') === 0) {
      // Direct-load on mcp-sources/{id}: parse the source id so the editor
      // opens on refresh. Mirrors admin.js's L5 parsing pattern (now
      // relocated to studio post-F2 retrofit).
      section = 'mcp-sources';
      pendingMcpSourceFormMode_local = 'edit';
      // Defensive: if extra path segments, take only the first.
      pendingMcpSourceId_local = firstSeg(sub.slice('mcp-sources/'.length));
    } else if (sub === 'agents/~new') {
      section = 'agents';
      createRoute = true;
      if (!(prev === 'agents' && self._createMode)) closeOpenItem();
      self._pendingSelectName = null;
      self._pendingTabName = null;
    } else if (sub && sub.indexOf('agents/') === 0) {
      section = 'agents';
      if (self._createMode) closeOpenItem();
      var rest = sub.slice('agents/'.length);
      var slashIdx = rest.indexOf('/');
      if (slashIdx === -1) {
        pending = decodeURIComponent(rest);
        pendingTab = 'general';
      } else if (slashIdx === rest.length - 1) {
        // Trailing-slash defensive — treat as no-tab.
        pending = decodeURIComponent(rest.slice(0, slashIdx));
        pendingTab = 'general';
      } else {
        pending = decodeURIComponent(rest.slice(0, slashIdx));
        var tab = rest.slice(slashIdx + 1);
        // F8 L3 Patch A — split deeper "mcps/{source-id}" BEFORE the
        // four-tab whitelist check. Without this, the whitelist would
        // reject "mcps/some-uuid" and default to "general", breaking
        // deep-link navigation (AC L3.6 + Browser Test 6).
        if (tab.indexOf('mcps/') === 0) {
          pendingMcpAgentSourceId = decodeURIComponent(tab.slice('mcps/'.length));
          tab = 'mcps';
        }
        if (tab === 'general' || tab === 'rules-and-notes' || tab === 'knowledge' || tab === 'mcps' || tab === 'tools' || tab === 'self-configuration') {
          pendingTab = tab;
        } else {
          pendingTab = 'general';
        }
      }
    } else if (sub === 'agents' || !sub) {
      section = 'agents';
      // Section root: the empty detail state -- close any open editor or create form
      // and drop a stale pending selection (a hydrate-before-loadAll target
      // would otherwise re-open its agent when the list arrives).
      closeOpenItem();
      self._pendingSelectName = null;
      self._pendingTabName = null;
      pendingTab = 'general';
    } else {
      // Defensive: unrecognized sub defaults to 'agents'. Do NOT throw.
      section = 'agents';
    }
    self._activeTab = pendingTab;
    if (pending) {
      self._pendingSelectName = pending;
      self._pendingTabName = pendingTab;
    } else if (section !== 'agents') {
      self._pendingSelectName = null;
      self._pendingTabName = null;
    }
    // Always overwrite pending MCP and connector state (including with nulls
    // when sub is not mcp-sources/... or connectors/...) so navigation away
    // clears stale pending.
    self._pendingMcpSourceId = pendingMcpSourceId_local;
    self._pendingMcpSourceFormMode = pendingMcpSourceFormMode_local;
    self._pendingConnectorId = pendingConnectorId_local;
    self._pendingConnectorFormMode = pendingConnectorFormMode_local;
    if (self._providersSection) self._providersSection.setPending(pendingProviderMode_local, pendingProviderId_local);
    // The MCPs tab's source focus: the URL's value (or none) replaces the
    // previous one, so `#agents/x/mcps/s2` while on s1 focuses s2.
    self._pendingMcpAgentSourceId = pendingMcpAgentSourceId;
    self._selectedMcpAgentSourceId = pendingMcpAgentSourceId;

    // Item subs inside the section that is already showing do not re-render the
    // section root (no flash, no list refetch): the consume paths below render
    // the item themselves. MCP and connectors share one rule (M25 F3 L4a): a
    // fresh hydrate closes the open form, then resolves the pending id against
    // a FRESH list; an intent consumes it from the cached list, and on a miss
    // (a cold cache) the open form is closed too, so the section never
    // re-renders the OLD item while the new one resolves.
    var skipSectionRender = false;
    if (prev === section) {
      if (pending || (createRoute && self._createMode) || kbCreateWasOpen) {
        skipSectionRender = true;
      } else if (section === 'mcp-sources' && pendingMcpSourceFormMode_local) {
        if (!fresh && self._tryConsumePendingMcpSource) {
          skipSectionRender = self._tryConsumePendingMcpSource(true);
        }
        if (!skipSectionRender && self._closeMcpForm) self._closeMcpForm();
      } else if (section === 'connectors' && pendingConnectorFormMode_local) {
        if (!fresh && self._tryConsumePendingConnector) {
          skipSectionRender = self._tryConsumePendingConnector(true);
        }
        if (!skipSectionRender && self._closeConnectorForm) self._closeConnectorForm();
      } else if (section === 'providers' && pendingProviderMode_local && self._providersSection) {
        if (!fresh) skipSectionRender = self._providersSection.consume(true);
        if (!skipSectionRender) self._providersSection.reset();
      }
    }
    // The section change (and the outgoing section's cleanup) happens HERE,
    // before the pending agent is consumed: doSelect requires the Agents
    // section to be active.
    if (!skipSectionRender && self._setActiveSection) {
      self._setActiveSection(section, { writeUrl: false, prev: prev });
    }
    if (pending && self._tryConsumePendingSelect) self._tryConsumePendingSelect(fresh);
    if (createRoute && self._enterCreate) self._enterCreate();
    if (kbCreateRoute && self._focusKbCreate) self._focusKbCreate();
    if (section === 'agents' && self._syncAgentSelection) self._syncAgentSelection();
    // The pending-item rule (M25 F3 L4a), MCP and connectors alike: a create
    // form needs no list and opens at once; an existing item is taken from the
    // cached list for an intent (else on the next store notification, never
    // healed), and resolved against a FORCED fetch for a fresh hydrate (a dead
    // id heals to the section root).
    if (self._resolvePendingLibraryItems) self._resolvePendingLibraryItems(fresh);
    // DD3 (c): the Library list's selection follows the hydrate; a section
    // root scrolls its group into view, an item its row.
    if (section !== 'agents' && self._syncLibrarySelection) self._syncLibrarySelection(true);
  },
};
