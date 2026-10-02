# Leg: library-list (4a)

**Status**: completed
**Flight**: [List and Detail](../flight.md)

## Objective

Make Library a grouped list beside a detail pane (DD5, DD8), so that **every row and
every Add item resolves** by the end of this leg.

- **One grouped list** sits in the Library column:
  - groups for Knowledge bases, MCP servers and Connectors;
  - an intro;
  - an **Add** menu;
  - group empty lines;
  - row meta from `App.usage`.
- **Editors beside the list.** All three Library editors open beside the list, no longer
  replacing a grid.
- **Connector URLs.** Connectors get real URLs, `#library/connectors/{id}` and `~new`.
- **Knowledge-base create** becomes a `~new` form in the detail pane, which closes squawk
  0101.
- **Retired:**
  - the Library "sections" nav;
  - the three tile grids.
- **Empty detail state.** It shows when no item is open.
- **Back controls (interim).** They remain until leg 4b, routed to their section root.

## Context

- **Flight decisions:**
  - DD5: the Library list. Its row table defines icons, meta and testids, and the
    connector count includes `channel_map`.
  - DD8: create routes, Cancel and delete, and the focus rule.
  - DD3: the guards. `setActiveSection` owns the list pane's lifetime.
  - DD11: ownership of the shared lane.
  - The cycle-2 resolution: leg 4a hosts all three editors.
- **Legs 1–3 outputs:**
  - **Leg 1:** `listPane` with `groups`, per-group `emptyText`, `intro`,
    `rowStyle: 'library'`, `scrollToSelected` and focus preservation. Also `_lists.py`
    and the guard.
  - **Leg 2:**
    - `App.store` `knowledge-bases`, `mcp-sources` and `connectors`, with the invalidation
      map;
    - `App.usage.kbAgents/mcpAgents/connectorAgents/mcpToolCount`;
    - `describeRoute` names, and the `sync` create→item announcement with a name hint.
  - **Leg 3** (landed; read its flight-log entry):
    - **Host pattern.** The studio sidebar panel holds `.studio-agents-list` next to the
      Library section nav, with `.is-hidden` switching and flex sizing
      (`flex: 1; min-height: 0; display: flex; flex-direction: column`, and
      `> .ui-list-pane { flex: 1 }`).
      - **The DOM class differs from the code.** `renderSectionNav` renames the
        `.studio-section-nav` element to `.section-nav`, so the DOM class is
        `.section-nav`.
      - `setActiveSection` owns which host shows and the pane's lifetime.
    - **`listPane` options:** `item.lead`, a function-valued `emptyText(q)`, and the
      `position: relative` fix on the pane and rows.
    - **The `renderAgentList(scroll)` single-builder pattern.** `scroll` is true only after
      a load or navigation, never on a bare store notification.
    - **Scroll-to-selected.** It re-scrolls once more on `document.fonts.ready`, because
      the cold-load font reflow put the row 18px out of view. Reuse it for Library.
    - **Delete to root.** Read the row index before the request. Focus then goes to the
      next row, else the previous, else the create action.
    - **Isolation test:** `tests/browser/test_agents_library_isolation.py`, with held
      requests and counters and no timing.
  - Read the leg 1–3 entries in the flight log before starting.
- **Studio Library today** (`areas/studio.js`; line numbers from `508fc83`, so re-grep):
  - **Section nav.** `App.layout.renderSectionNav(sectionNavEl, …)` at `:408-420`, with
    the `LIBRARY_ROUTE_SECTION` map at `:403-407`.
  - **Knowledge bases:**
    - `renderKnowledgeSection` `:470` and `renderKnowledgeGridView` `:484-497`. The grid
      is `App.studio.renderKnowledgeGrid`, with its inline create form, in
      `knowledge-section.js:300-390`.
    - `onCreateSuccess` ignores `kb`, which is squawk 0101.
    - `selectKnowledgeBase` `:526` is a `go`.
    - `leaveKnowledgeDetail_` `:533` is a replace with bypass to the section root.
    - `renderKnowledgeDetailView` `:540`.
  - **MCP:** `renderMcpSourcesSection` `:723`.
    - It promotes the pending `add`.
    - The editor's `onBack` is a `go` to the section root.
    - `onCancel` is a replace with bypass.
    - `populateMcpSourcesGrid` `:881` renders the grid (`mcp-servers-grid.js`).
  - **Connectors:** `renderConnectorsSection` `:960`, `selectConnector` `:1051` and
    `enterCreateConnectorMode` `:1059`. All three work **in place**: there is no route,
    and `serializeState` returns `'connectors'` (`:33`).
    - The editor's `onBack` uses an inline `App.nav.confirmLeave`.
    - `onSaveSuccess` stays in place.
    - The grid is `App.studio.renderConnectorsGrid` (`connector-editor.js:214`), and its
      empty-state CTA at `:243` is unstyled.
  - **`hydrateState`** (`:88-200`) parses `knowledge/{id}`, `connectors` and
    `mcp-sources/new|{id}`, and handles the pending MCP state (`_pendingMcpSource*`).
  - **`closeOpenItem`** (`:1073`) and `setActiveSection` (`:1110`) clean up the outgoing
    section.
- **Router.** `SECTIONS` (`router.js:67-76`) marks knowledge and connectors `create: false`.
  The MCP row is `create: true`, and its area sub is `mcp-sources/new`.

## Inputs

- `static/js/router.js` (`SECTIONS` rows)
- `areas/studio.js`, `areas/studio/knowledge-section.js`, `areas/studio/mcp-servers-grid.js`,
  `areas/studio/connector-editor.js`, `areas/studio/mcp-server-editor.js`
- `static/js/ui/menu.js`, `ui/list-pane.js` (consumer, plus `scrollToGroup`),
  `ui/feedback.js` (`emptyState`), `static/js/icons.js` (`database` exists; add `server`
  and `plug`)
- `css/studio.css`, `css/base.css`, `css/components.css`
- Library-lane tests:
  - `test_flow_studio_knowledge_inventory`
  - `test_flow_studio_mcp_editor`
  - `test_flow_studio_mcp_navigation`
  - `test_mcp_test_connection_button`
  - `test_studio_connector_editor`
- Shared-lane allow-list files that touch Library. Enumerate them at leg start by
  grepping for `section-nav-item`, `knowledge-base-card`, `mcp-source-card`,
  `connector-card` and `entity-tile` on Library routes.

## Outputs

**1. The Library column.**
- **Host.** A `.studio-library-list` host replaces the Library section nav: the
  `renderSectionNav` call and `LIBRARY_ROUTE_SECTION` go.
  - It uses the same switching, lifetime and flex rules as leg 3's agents host:
    `setActiveSection` creates and destroys the pane on entering and leaving the Library
    sections, and only one pane exists in the studio sidebar at a time.
  - **Moving between Library sections keeps the pane.** Knowledge, MCP and Connectors are
    all one Library list, so a move between them is not a leave.
  - `test_agents_library_isolation.py` is extended to cover it.
- **CSS.** `#app-sidebar[data-destination="library"] { padding-top: 0 }`.
- **The Library section-nav element** is removed from studio, along with its DOM and
  CSS. It is `.studio-section-nav` in code and `.section-nav` in the DOM. `section-nav.js`
  keeps its Settings caller until leg 5a.
- **`setActiveSection`** now switches between two list hosts (agents and library), with
  no section-nav host. Exactly one pane exists at a time.

**2. The grouped list** (DD5). One `App.ui.listPane` with these options:
- `title: 'Library'`;
- `intro`: "Things agents can use. Attach them from an agent's Knowledge and MCPs tabs."
  (A19);
- `rowStyle: 'library'`;
- testid `library-list`, registered (the isolation test needs it; Agents uses
  `agents-list`);
- no filter and no count.

The **Add** action is an `App.ui.menu`:
- **Trigger.** "Add", `.btn-outlined-primary.btn-sm`, plus icon, testid
  `library-add-btn`.
- **Items:**

  | Item | Destination | Testid |
  |---|---|---|
  | "Knowledge base" | `go(href({ destination: 'library', section: 'knowledge', create: true }))` | `library-add-knowledge` |
  | "MCP server" | `go(href({ … section: 'mcp', create: true }))` | `library-add-mcp` |
  | "Connector" | `go(href({ … section: 'connectors', create: true }))` | `library-add-connector` |

- **Alignment** (design review, M1). The popup is `position: absolute; left: 0;
  min-width: 160px` (`components.css:~788-807`). The trigger sits at the right of a
  300px `overflow: hidden` aside, so the default alignment overruns by about 80px.
  - **Use `align: 'end'`**, which `App.ui.menu` already supports.
  - If `align: 'end'` still clips, **stop and report**. A `position: fixed` fallback
    would be a control-library change, which this leg does not make.
- **Clipping check.** Every item rect lies inside the `#app-sidebar` rect, and
  `elementFromPoint` at each item's four inset corners returns the item. A centre-only
  check passes a half-clipped item.
- **Lifetime.** This is `App.ui.menu`'s first production use. Call `menu.destroy()` when
  the pane is destroyed.

The **groups** are, in order:

| Group | `emptyText` |
|---|---|
| "Knowledge bases" | "No knowledge bases yet." |
| "MCP servers" | "No MCP servers yet." |
| "Connectors" | "No connectors yet." |

Each group is sorted A–Z by name.

**Item ids are namespaced** (`'knowledge:' + id`, `'mcp:' + id`, `'connector:' + id`).
`listPane` rejects duplicate ids across groups.

**Rows:**

| Type | Icon | Meta | `href` | Testid |
|---|---|---|---|---|
| Knowledge base | `database` | `{n} agents` | `#library/knowledge/{id}` | `knowledge-base-card` |
| MCP server | `server` | `{t} tools · {n} agents`, or `Tools not loaded · {n} agents` when `mcpToolCount` is `null` | `#library/mcp/{id}` | `mcp-source-card` |
| Connector | `plug` | `{n} agents` | `#library/connectors/{id}` | `connector-card` |

- Knowledge-base and MCP counts come from `App.usage.kbAgents` and `App.usage.mcpAgents`.
  The connector count comes from `App.usage.connectorAgents(c).length`.
- Use the singular for one: "1 agent" and "1 tool".
- **Accessible name, settled by the design review.** Library row meta is a visible text
  span inside the `<a>`, so it is already in the accessible name, and the icon is
  `aria-hidden`. No `nameSuffix` is needed.
- **Icons.** They live in `static/js/icons.js`, pinned to lucide@v0.265.0. `database`
  exists. Add `server` and `plug` with v0.265.0 geometry.
- **Agent counts appear only once `agents` has loaded.** Until then the meta shows only
  what is known: an MCP row shows "{t} tools", and knowledge-base and connector rows show
  no meta. The agents notification fills them in. It is never "0 agents" while loading
  (an acceptable variation in the flight spec).
- **Fetch policy** (design review, issue H3; it implements DD9's freshness bound):
  - **Pane creation** (entering Library from Agents, or a cold boot onto a Library route)
    calls `App.store.get(name, { force: true })` for `knowledge-bases`, `mcp-sources` and
    `connectors`. `agents` gets a plain `get`, so it reuses the cache when Agents loaded
    it.
  - **Studio `activate` while on a Library section** (the pane survives a trip to Chats or
    Settings) force-gets the same three. This replaces `_refresh`'s MCP-only refetch
    (`studio.js:~3165-3169`). Fold that refetch in; don't keep both.
  - **A move between Library sections** fetches nothing. The pane and its data stay.
  - **After a mutation**, the editor's callback invalidates the collection (leg 2), then
    `reloadLibrary(name)` does a plain `get(name)`. `invalidate` alone notifies no
    subscriber (`store.js:55-57, 84-89`).
    - This applies to every create, save, rename, delete and MCP Refresh callback.
    - **MCP has no Refresh callback today.** `mcp-server-editor.js` invalidates
      `mcp-sources` on a connect success (`~1963`: the manual Refresh, the auto-run after
      create, and Phase 2 after sign-in) and on Reset connection (`~1354`). It calls no
      studio callback at any of these. Add an **`onListStale`** editor callback, fire it
      after each of those invalidations, and wire it to `reloadLibrary('mcp-sources')`.
      Otherwise the tool count stays "Tools not loaded" after a Refresh, and a create's
      Refresh invalidation lands after the save's reload.
    - It replaces the self-refetching grid paths this leg deletes:
      `fetchKnowledgeBases_()` in `onCreateSuccess`, `fetchMcpSources_`,
      `fetchConnectors_`, and the knowledge-base rename's manual cache patch
      (`studio.js:~519-522, ~651-655`).
  - **Rewrite `test_store_library.py::test_library_list_request_counts`.** Its `BEFORE`
    table becomes the new policy:
    - cold boot onto a Library route: (1, 1, 1);
    - first Library entry from Agents: (1, 1, 1);
    - every move between Library sections: (0, 0, 0);
    - re-entry from Agents: (1, 1, 1);
    - the studio `activate` from Chats on a Library route: (1, 1, 1).

    The test has 16 steps. The three trailing `== 1` assertions
    (`test_store_library.py:~327-329`), each section loading on its own move, are replaced
    by assertions that each move between sections is (0, 0, 0).

    The invariant it pins is: at most one request per collection per step, and none on a
    move between Library sections. The kb create and delete invalidation tests (`:359`,
    `:378`) must still pass, now through `reloadLibrary`.
- **Data:**
  - One subscription for each of the four collections.
  - The section caches (`knowledgeBases`, `mcpSources`, `connectors`) are fed from the
    store data. These caches back `find*`, `tryConsumePendingMcpSource` and the new
    connector pending consume, so an intent row click always finds its item.
  - **One `renderLibraryList(scroll)` builder** calls `setItems` and `setSelected` (the
    leg 3 pattern).
    - **First load.** Don't call `setItems` until all three Library collections have each
      settled, so the groups never flash "No … yet." before data arrives.
      - A collection counts as **settled** when `App.store.peek(name).loaded` is true, or
        this pane's `get` has settled. So a re-entry renders from the cache at once, and
        the forced get's notification refreshes it.
      - **While gated, the pane's own empty state** would read listPane's default "Nothing
        to show" (`list-pane.js:~162, ~280`). Give the pane a function `emptyText` that
        returns "Loading library…" until the gate opens, as leg 3 does
        (`studio.js:~1767-1770`).
    - **Load failure:**
      - **Never loaded.** A collection with no value gives its group the empty line
        "Couldn't load {group}." The grids' "Failed to load …" lines are deleted with
        them.
      - **Last-good value.** A failed forced get with a last-good value (`peek` reports
        `ok: false` with a value) keeps showing the stale rows. A background refresh
        failure never blanks a list (Flight Director decision, design review cycle 2).
    - **Re-entry agent counts** render from `peek('agents')`. A plain `get` on a warm cache
      resolves without notifying anyone.
  - **`setSelected`** is driven by studio state, including a pending deep-link id (leg 3's
    pattern). A cold deep link therefore selects its row as soon as the list loads. It
    selects nothing at a section root or on `~new`.
  - **`scrollToSelected()`** runs after loads and navigations, never on a bare store
    notification, with leg 3's `document.fonts.ready` re-scroll.
- **Retired:**
  - `renderKnowledgeGridView`, plus `knowledge-section.js`'s grid and its inline create
    form;
  - `populateMcpSourcesGrid`, plus `mcp-servers-grid.js`;
  - `renderConnectorsGrid`, plus its unstyled CTA.
  
  Delete the dead code and grid-only CSS (`.entity-tile-grid` usages in studio).

**3. Detail pane.**
- **Section root, no item** (`#library/knowledge`, `#library/mcp`, `#library/connectors`).
  A pane-size `App.ui.emptyState` (`headingLevel: 2`, as leg 3), with these copies and
  testids:

  | Route | Copy | Testid |
  |---|---|---|
  | `#library/knowledge` | "Select a knowledge base, or add one." | `library-empty-knowledge` |
  | `#library/mcp` | "Select an MCP server, or add one." | `library-empty-mcp` |
  | `#library/connectors` | "Select a connector, or add one." | `library-empty-connectors` |

  - **The action.** Each empty state has an action that opens the matching `~new`, with
    testid `library-empty-{kind}-add`, registered.
  - **Group scroll.** On the section's activation, the matching group is scrolled into
    view (DD5). `listPane` has no API for this (`scrollToSelected` needs a selected row),
    so **add `scrollToGroup(groupId)`** to the factory.
    - **Group ids.** `normalise` keeps only `{label, emptyText, items}`
      (`list-pane.js:~29`), and `groupNodes` holds `{node, emptyLine}` (`~359`). Add an
      optional `group.id`, validated unique in `normalise`, and update the header
      comment's group schema.
    - **Behaviour.** An unknown or hidden group is a no-op. It scrolls within the body,
      as `scrollToSelected` does.
    - **Library ids:** `knowledge`, `mcp` and `connectors`.
    - **When it runs:** on a root hydrate, **and** after the gated first `setItems`. On a
      cold `#library/mcp` the groups do not exist when the hydrate runs.

    The full factory checklist applies:
    - a header-comment entry;
    - a contract test in both engines;
    - the inventory row updated;
    - the demo calls it.
  - **No flash on deep links.** While a pending deep-link id is still resolving, the detail
    pane shows nothing rather than flashing the empty state.
  - **MCP's open path survives the grid's removal.** Its fetch → consume pending → dead-id
    heal (`studio.js:~869-885`) sits inside the **grid branch** today. It is replaced by
    the pending-item rule below, never copied into the root branch: that copy would fetch
    on every MCP root render and break §2's (0,0,0) moves.
- **The pending-item rule** (design review cycle 2, high). One rule for MCP and connectors:
  - **A root with no pending id** fetches nothing.
  - **A pending id on a fresh hydrate** (cold boot, Back, Forward or reload):
    1. `App.store.get(name, { force: true })`. It joins the forced get from pane creation
       or `activate`, so a cold boot stays (1,1,1).
    2. Consume.
    3. Heal to the section root if the id is absent.

    This keeps
    `test_router_items.py::test_dead_mcp_source_on_forward_heals_to_root` (`~586`)
    passing; Forward relies on `_closeMcpForm` (`studio.js:~229-233`) plus a forced
    fetch.
  - **A pending id on an intent** (a row click, an agent-tab link):
    - consume from the section cache;
    - if it misses (a cold cache), consume on the next store notification, or after a
      plain `get`;
    - never heal on non-fresh data.
  - **Subscriptions re-attempt pending consumes.** Today the grid's `.then(tryConsume…)`
    retried after its fetch (`studio.js:~986-987` "will retry after fetch"). Nothing else
    does, once it is gone.
  - **Connectors get the MCP within-section branch.** Port the `prev === section`
    skip-or-close-form branch (`studio.js:~226-240`). Otherwise a row click within
    Connectors first re-renders the **old** connector, because `renderConnectorsSection`
    runs while `connectorFormMode` is still `'edit'`.
  - **Subscriptions live for the page's lifetime.** Register the four Library
    subscriptions once in `init`, like `agents` and `providers`.
    - They always feed the section caches and re-attempt pending consumes.
    - They render the list only while the Library pane exists.
    - This closes the cold-cache intent gap with no per-pane subscribe and unsubscribe.
- **Item open.** The existing editor mounts in the detail pane:
  - knowledge base: `renderKnowledgeDetailView`;
  - MCP: `App.studio.renderMcpSourceEditor`;
  - connector: `App.studio.renderConnectorEditor`.
  
  The list stays visible. **Interim Back** (removed in 4b):
  - knowledge base: `back-knowledge-btn` → `go` to `#library/knowledge`;
  - MCP: `back-mcp-source-btn` → `go` to `#library/mcp` (unchanged);
  - connector: `back-connector-btn` → `go` to `#library/connectors`. This **replaces**
    the inline `App.nav.confirmLeave` gate; the router guard handles a dirty editor.
- **Closing an item after leg 4b.** Leg 4b removes Back. The breadcrumb's group segment,
  as in "Library / **MCP servers**", becomes a link to the section root (a DD2 refinement
  that leg 4b implements). In this leg, the "current section closes the editor" tests are
  rewritten onto the interim Back, and 4b moves them to the breadcrumb link:
  - `test_router_guard.py`, four tests;
  - `test_router_items.py::test_connector_editor_closed_by_library_connectors_section`.

**4. Knowledge-base create** (DD8; closes squawk 0101).
- **Router.** `SECTIONS` knowledge becomes `create: true`, with area sub `knowledge/new`,
  the MCP pattern (`router.js` `areaSubToRoute`/`resolve` round-trip). `href()` and
  `parse()` already accept `~new` for any section; only `resolve` and `areaSubToRoute`
  read `create`.
- **Accepted risk: an id of exactly `new`.** A knowledge base or connector created
  through the API with that id is unreachable at its item route; knowledge-base ids allow
  `^[A-Za-z0-9_-]{1,64}$` (`db/models.py:104`). This is the same risk MCP already
  carries, so record it in `agents.md`. `~new` itself cannot collide, because `enc()`
  writes a leading `~` as `%7E`.
- **Studio plumbing** (design review, issue M3):
  - `hydrateState` matches `knowledge/new` **before** the `knowledge/` prefix branch
    (`studio.js:~135`). Otherwise `_selectedKbId` becomes `'new'`, the fetch 404s, and the
    route heals to the root.
  - `serializeState` checks the create flag **first**.
  - The create flag is added to `editorOpen()` (`studio.js:~3188-3193`), or the form is
    never guarded.
  - The flag is cleared in `closeOpenItem`, in the knowledge cleanup on leaving
    (`~1189`), and on any `knowledge` or `knowledge/{id}` hydrate. Otherwise a later
    `sync` writes the new item's URL back to `~new`.
  - **Same-route Add.** Choosing an Add item whose `~new` form is already open only
    refocuses that form's first field, whether or not it is dirty, as leg 3's
    `goCreateAgent` does (`studio.js:~1732-1737`). It never runs a guarded `go` to the
    same route. This applies to all three Add items.
  - **The `knowledge/new` hydrate** calls `closeOpenItem` unless the create form is
    already open, mirroring `agents/~new` (`studio.js:~167-170`). Otherwise an open
    knowledge-base detail's poll and `_selectedKbId` survive.
- **Create form.** A new `App.studio.renderKnowledgeCreate(container, opts)`, a DOM-built
  component in `knowledge-section.js`. It is shown in the detail pane at
  `#library/knowledge/~new` and contains:
  - **Header.** Its own header (DD2): breadcrumb "Library / Knowledge bases" and
    `h1.editor-title` "New knowledge base". That `h1` is the only one in the pane.
  - **Fields.** Name and Description, with the testids `kb-create-name-input` and
    `kb-create-description-input` kept from the inline form.
    - The name keeps its **43-code-point hint** (`kb-create-name-hint`, M24 DD-16).
    - The form keeps its **error line** (`kb-create-error`).
  - **Actions.** `.form-actions` holding Cancel (`kb-create-cancel-btn`, new) and Create
    (`kb-create-submit-btn`, kept).
    - **Create stays enabled**, as today. An empty name shows "Name is required." in the
      error line. This keeps M24 F06 AC-2 and
      `test_create_knowledge_base_hint_and_empty_name_refused`.
  - **Dirty source.** It reports dirty through studio's `dirty` / `App.nav` source. The
    unsaved indicator on this form is leg 4b's.
- **Save-create.**
  - The POST is the existing knowledge-base create call (`knowledge-section.js:373`).
  - **At submit,** capture `editorGen`, as the MCP and connector `onSaveSuccess` paths do.
    **Create stays disabled** from submit until the form is gone or the request fails;
    a second click during the await would otherwise POST a duplicate. The old form
    re-enabled it on success (`knowledge-section.js:~386`).
  - **On success, in order** (H1; ordering corrected at design review cycle 2):
    1. `App.store.invalidate('knowledge-bases')` (leg 2).
    2. **Clear `dirty` synchronously,** but only if `editorGen` is unchanged and the route
       is still `library/knowledge/~new`. `dirty` is one flag shared by every studio
       editor (`studio.js:~311`). Clearing it after the user has moved on would strip
       another editor's unsaved state from the guard and `beforeunload`. Clearing it
       before the await also stops a prompt about already-saved work during the reload.
    3. **Await `App.store.get('knowledge-bases')`.** `go()` takes no name hint, and its
       commit names the item from the store (`router.js:~404-410, ~476-483`). A
       knowledge-base id is opaque 12-hex, unlike an agent's, so without this step the
       commit speaks "Library — Knowledge — Knowledge base". After `invalidate`, a plain
       `get` always refetches, and subscribers run before the awaiting caller resumes. So
       the row exists before the hydrate's `setSelected`.
    4. **Re-check** that `editorGen` is unchanged, the route is still `~new`, and
       `!App.router.isDeciding()`. `go()` joins a pending decision before it looks at
       `bypassGuard` (`router.js:~612-618`). If any check fails, skip the `go`.
    5. `go(href({ destination: 'library', section: 'knowledge', id: kb.id }), { replace: true, bypassGuard: true })`.
  - **If the `get` fails**, still `go`. The announcement falls back to the noun; that is
    acceptable, and the detail view still opens.
  - **Focus.** After the detail view mounts, move focus to `kb-folder-path-input`.
    Registering a folder is always the next step (squawk 0101), and the form the user was
    typing in is gone.
  - **The router announces the new knowledge base by name** through the `go` commit.
- **Cancel.** It runs the discard teardown, then `go(href(knowledge root), { replace: true,
  bypassGuard: true })`. Focus follows the DD8 rule.

**5. Connector URLs** (DD8).
- **Router.** `SECTIONS` connectors becomes `create: true`, with area subs
  `connectors/new` and `connectors/{id}`.
- **Studio:**
  - `serializeState` returns `connectors/new` (add mode) or `connectors/{id}` (edit
    mode).
  - `hydrateState` parses both, with a **pending-state** pair, `_pendingConnectorFormMode`
    and `_pendingConnectorId`, consumed after `App.store.get('connectors')` resolves.
    This mirrors MCP's `_pendingMcpSource*`, including the dead-id heal (a `fresh`
    hydrate on an unknown id goes to the root).
    - Match `connectors/new` **before** `connectors/`.
    - **Always overwrite** the pending pair on hydrate (MCP does this at `~223-226`).
    - **The pending id survives the race.** While a pending id is set, `serializeState`
      returns it (MCP does this at `~49-53`). Otherwise a cold deep link is synced to the
      root before the list loads.
    - **Within-section consume.** Add one like `_tryConsumePendingMcpSource(!fresh)` at
      `~263`.
    - **An `add` pending state needs no list.** Consume it at once (as MCP does); don't
      wait on `get('connectors')` for it.
- **Navigation:**
  - `selectConnector` becomes a row `href` (intent `go`).
  - `enterCreateConnectorMode` becomes the Add menu's `go` to `~new`.
  - Neither renders in place any more.
- **Save-create.** `onSaveSuccess` switches to edit mode with **no navigation and no
  hydrate**. Today it re-renders the editor from the saved row, behind an async wait for
  types and agents; that is fine.
  - It then calls
    `App.router.sync('studio', 'connectors/' + encodeURIComponent(id), { name: updated.name })`,
    which announces through the leg 2 create→item rule.
  - Before the `sync`, it invalidates `connectors`, runs `reloadLibrary('connectors')` and
    clears `dirty`.
  - Leg 4b owns the state-preservation checks.
- **Cancel** (design review, M2; DD8). `connector-editor.js:~626` calls `onCancel` in
  both modes, and today that closes the editor (`studio.js:~1030`).
  - **Edit mode:** revert in place. Re-render from `editingConnector` and clear `dirty`.
    The route stays `#library/connectors/{id}`.
  - **Create mode:** discard, then `go` replace with `bypassGuard` to
    `#library/connectors`.
- **Delete.** `onDeleteSuccess` replaces to `#library/connectors` and applies the DD8
  focus rule.

**6. MCP.** It keeps its routes and its save-create path, which leg 2 already announces.
Selection is now a list-row `href`. Its section root shows the empty state, not the grid.

**7. Tests.**
- **Migration scope** (design review, H4; DD11 lists files by name). The guard covers only
  part of this. The grid surfaces it does not cover:
  - the `.page-title` texts "MCP Servers" and "Connectors";
  - `studio-knowledge-inventory` at the section root;
  - `new-*-btn` and `kb-create-*`;
  - `.empty-canvas`;
  - `[data-id]` row selectors (list rows carry no `data-id`);
  - the `.entity-tile-grid` flash observer.

  | Lane | File | Library-specific hits (approximate) |
  |---|---|---|
  | library | `test_flow_studio_knowledge_inventory.py` | ~57: cards, new-btn, kb-create, inventory, section-nav, page-title. Its `_create_knowledge_base` helper assumes create returns to the grid. Back ×10 stays until 4b. |
  | library | `test_studio_connector_editor.py` | new-btn ×11, card ×3, page-title ×2; Back ×3 stays until 4b |
  | library | `test_flow_studio_mcp_navigation.py` | page-title ×5, new-btn ×2, section-nav ×4, empty-canvas ×3 |
  | library | `test_flow_studio_mcp_editor.py` | page-title ×3, card ×1; Back ×2 stays until 4b |
  | library | `test_mcp_test_connection_button.py` | none |
  | agents | `test_flow_studio_navigation.py` | ~35, including nine Library section-nav tests (render, default section, roving tabindex, click ×2, arrows, Enter, persists-on-refresh ×2), the Library-trip test and the aside tests. **Rewrite the keyboard tests** as list and Add-menu keyboard tests; do not delete them (the 5a precedent). |
  | agents | `test_agents_library_isolation.py` | `_sidebar` and `_expect_library_host` use `nav.section-nav`; inventory ×2 |
  | agents | `test_flow_studio_knowledge_attach.py` | Back ×2 (4b only; no change here) |
  | shared | `test_router_items.py` | ~26: cards through `[data-id]`, new-connector ×4, section-nav, inventory ×3, and the `.entity-tile-grid` flash observer (`~114-126`) behind `test_mcp_open_no_refetch_no_flash`; Back ×7 stays until 4b |
  | shared | `test_router_guard.py` | ~17 Library: section-nav clicks ×5, new-connector ×2, inventory ×3, MCP page-title; back-knowledge ×4 stays until 4b |
  | shared | `test_nav_guard.py` | 7, plus the inline-dialog re-home (AC5) and `test_connector_back_goes_through_app_nav` (the inline gate and `new-connector-btn`) |
  | shared | `test_store_library.py` | 7, plus the request-count rewrite (§2) |
  | shared | `test_flow_hash_routing.py` | Library half: inventory ×2 (a `LEGACY_URL_TESTS` member), MCP page-title ×2 |
  | shared | `test_flow_dirty_confirm.py` | inventory `~194` (not allow-listed, so the guard won't flag it) |
  | shared | `test_shell_rail.py` | the fit loop (`~261-277`) includes `library/knowledge`; its `assert rows` fails |
  | shared | `test_lists_helper.py` | the connectors case now asserts the route |
  | shared | `test_router_core.py` | redirect and parity rows for `knowledge/~new` and `connectors/~new`. (Its `.page-title "Knowledge"` hits are Settings knowledge indexing, not Library.) |

  - About 17 files. Only about two can leave the allow-list in this leg
    (`test_flow_studio_mcp_navigation.py`, `test_flow_studio_navigation.py`). Most keep
    Back (4b) or Settings (5a/5b) usages.
  - **Timebox.** This is one leg; a split would leave lanes red, as with leg 3. Run the
    library lane after each step, and the agents and shared files you touch as you go.
- **Library half of the shared lane.** For each allow-listed shared file that touches
  Library, migrate only its Library parts. **A file leaves the allow-list only when
  fully clean.**
- **`test_router_items.py::test_agent_create_route_and_connector_back_each_ask_once`**
  assumes the inline gate and `new-connector-btn`. Rewrite it onto the router guard and
  the Add menu.
- **`_nav.py` parity** (design review, M7). `legacy_hash` and `_from_legacy`
  (`_nav.py:~181-187, ~224-230`) map `new` to `~new` only for mcp and providers. Add
  knowledge and connectors, update the docstring table, and add `REDIRECT_ROWS` and
  parity rows (`test_router_core.py:~159`) for `#studio/knowledge/new` and
  `#studio/connectors/new`.
- **Helpers in `_lists.py`** (design review, M10):
  - **reuse** the existing `expect_selected(page, dest, name)` with `dest` such as
    `"library/knowledge"` (no new 4-argument form);
  - flip `LISTS["library/connectors"].item_route` to `True` (`_lists.py:~53-56`);
  - **new:** `library_add(page, kind)` and `library_empty_state(page, kind)`.
  - Helper modules may never name a guarded selector (`back-*-btn` and the others).
- **Retired testids.** Add `new-knowledge-base-btn`, `new-mcp-source-btn` and
  `new-connector-btn` to `RETIRED_SELECTORS`, and move their registry rows to the
  "Retired testids" table.
- **Interim-Back assertions** (AC3) go in a file already allow-listed through 4b, such as
  `test_router_items.py`. A new file naming `back-*-btn` would fail the guard.
- **MCP seeding with cached tools.** `PUT` strips `_cache` (`api.py:~2683`), and `POST`
  appears to keep it. Verify; otherwise route-stub the list response.
- **New tests**, in **`test_flow_studio_library_list.py`**, added to `library_pat` in
  `scripts/run-tests.sh` (design review, M5).
  - A name outside the `test_flow_studio_*` glob would also match `shared`, which is the
    complement of chats, studio and settings, not of `library_pat`, so it would run in
    two lanes.
  - Update `CLAUDE.md`'s explicit library-lane file list.

  The tests:
  - group order and A–Z sorting;
  - group empty lines;
  - meta counts against seeded attachments: a knowledge base attached to 2 agents, an MCP
    server with cached tools, and a connector with `default_agent` plus a `channel_map`
    duplicate;
  - each Add item opens its `~new`, and the menu is not clipped;
  - knowledge-base create opens the new knowledge base (0101), with the route replaced and
    the name announced;
  - knowledge-base and connector Cancel-on-create;
  - a connector deep link, cold, including an unknown id that heals to the root;
  - the empty detail state per section, and the group scroll (`scrollToGroup`);
  - the list stays visible with each editor open;
  - **delete, for each type:** replace to the root, the row leaves, and focus follows the
    DD8 rule;
  - **list freshness:** create, rename and delete each update the list without a reload
    (`reloadLibrary`);
  - **connector Cancel:** edit mode reverts in place, and create mode returns to the
    root;
  - **loading and failure:** no "No … yet." flash before data arrives (a held request),
    and a failed collection shows "Couldn't load {group}.".

**8. Docs.**
- `agents.md`: the Library list structure, the connector routes, knowledge-base
  `~new`, and the retired grids and section nav.
- `docs/ui-testid-registry.md`:
  - new: `library-add-btn`, `library-add-*`, `library-empty-*`,
    `library-empty-*-add`, `kb-create-cancel-btn`. (`kb-create-description-input` is
    already registered.)
  - retired, in the "Retired testids" table: `new-knowledge-base-btn`,
    `new-mcp-source-btn` and `new-connector-btn`. The card testids
    (`knowledge-base-card`, `mcp-source-card`, `connector-card`) do **not** retire: DD5
    keeps them on the rows.
  - new: `library-list`.
- `docs/ui-control-inventory.md`:
  - `menu`'s first production use;
  - the `listPane` `scrollToGroup` method;
  - remove the section-nav row's Library caller.
- `CLAUDE.md`:
  - the destination router line becomes `#library/{knowledge|mcp|connectors}[/~new|/{id}]`;
  - the library-lane file list.
- `agents.md`:
  - the fetch policy and `reloadLibrary`;
  - the accepted risk of an id of exactly `new`;
  - that `nav.js`'s non-router `confirmLeave` caller path is now test-only.

## Acceptance Criteria

- [ ] **AC1 — List.** With 2 knowledge bases, 2 MCP servers and 1 connector seeded:
  - **Groups.** The column shows the title "Library", the intro, the Add button and the
    three groups, in order and sorted A–Z.
  - **Rows.** Each row has its icon and meta. The knowledge-base agent counts match the
    seeded attachments, MCP shows its tool count (or "Tools not loaded") and agent count,
    and the connector count de-duplicates its `default_agent` and `channel_map`.
  - **Group empty lines.** With zero connectors, the Connectors group shows "No
    connectors yet.".
  - **No section nav.** The "Library sections" nav does not exist.
- [ ] **AC2 — Add menu.**
  - **Keyboard.** The menu opens by keyboard (Enter, Space, ArrowDown) and by click.
  - **Items.** The three items each navigate to their `~new`.
  - **Clipping.** It is not clipped at 1440×900 or 1024×768, with `align: 'end'`. Each
    item rect lies inside the `#app-sidebar` rect, and `elementFromPoint` at each item's
    four inset corners returns the item.
  - **Focus.** Escape closes the menu and returns focus to the trigger.
- [ ] **AC3 — Items beside the list.** For each type:
  - **Opening.** Clicking the row opens its editor in the detail pane. The row has
    `aria-current="page"`, and the list stays visible.
  - **Leave guard.** With a dirty editor, clicking another row asks once (router guard);
    Stay keeps the URL and the edit.
  - **Interim Back.** It returns to the section root's empty state.
  - **Delete.** Deleting the open item replaces to the section root. The row leaves the
    list, and focus follows DD8's single rule: the next row in list order, else the
    previous one, else Add.
  - **Freshness.** A create, rename or delete is reflected in the list without a reload.
- [ ] **AC4 — Knowledge-base create (0101).**
  - **Form.** Add, then "Knowledge base", shows the create form with its own header, the
    name hint, and an enabled Create. An empty name shows "Name is required.".
  - **Create.**
    - Entering a name and pressing Create opens the new knowledge base's detail view.
    - The route is `#library/knowledge/{id}`, with `history.length` unchanged
      (replace).
    - The new row is selected, and the announcer speaks its name (not the noun).
    - Focus is in `kb-folder-path-input`.
  - **Cancel.** It returns to `#library/knowledge`.
  - **Squawk.** Squawk 0101's repro passes, and the squawk is ready to close in the
    flight commit (Corrective Action written).
- [ ] **AC5 — Connector URLs.**
  - **Cold deep links.** `#library/connectors/{id}` cold-loads the editor beside the
    list, with the row selected.
  - **Dead ids.** An unknown id heals to `#library/connectors`.
  - **Create.** `#library/connectors/~new`, then Save. There is no navigation and no
    hydrate; the editor re-renders in edit mode from the saved row. The URL becomes
    `/{id}`, the announcer speaks the connector name, and the new row appears in the list.
  - **Cancel.** In edit mode it reverts in place, and the URL stays. In create mode it
    returns to `#library/connectors`.
  - **Leave guard.** Interim Back from a dirty connector editor asks once, through the
    router guard. The inline gate is gone.
  - **The inline-dialog test is re-homed.** Leg 3 moved
    `test_nav_guard.py::test_go_while_inline_nav_dialog_pending_resolves_stay_and_does_not_join`
    onto the connector editor's inline Back dialog, the one this leg removes.
    - After this leg, the only `confirmLeave` caller is the router adapter
      (`router.js:~545`), so no other app caller remains. Drive the dialog directly, with
      a dirty source present (a dirty connector `~new` form) so it opens:
      1. In `page.evaluate`, call `window.__p = App.nav.confirmLeave({ caller: 'test' })`
         without awaiting it.
      2. `App.router.go('library/mcp')` returns `false`, and `isDeciding()` is `false`.
      3. Continue resolves `__p` to `true` and runs the discard. The URL is unchanged.
    - Record in the flight log that `nav.js`'s non-router caller path is now test-only.
      Never delete the test silently.
- [ ] **AC6 — Empty states.**
  - Each section root shows its empty state (`h2`) with a working action, and scrolls its
    group into view.
  - **No grid markup.** A DOM query for `.entity-tile, .entity-tile-grid, .page-header`
    within the Library detail pane returns nothing. It deliberately excludes
    `.empty-canvas`, which the pane-size `emptyState` renders.
  - **No flash.** A cold deep link to an item never shows the empty state first.
- [ ] **AC7 — Isolation and fetching.**
  - `test_agents_library_isolation.py` is extended with Library list steps, and it passes.
  - Exactly one list pane exists across Agents ↔ Library switches, and moving between
    Library sections keeps the same pane.
  - The rewritten `test_library_list_request_counts` passes against the §2 fetch policy.
- [ ] **AC8 — Tests and guard.**
  - **Lanes.** The library lane and every shared file touched are green.
  - **Allow-list.** Every fully clean file leaves the allow-list; no file is listed
    while clean.
  - **`library_pat`** includes the new files, and no file runs in two lanes.
- [ ] **AC9 — Gates.**
  - `make lint` and `make test-unit`;
  - all five lanes, one at a time, with `THE_ONE_TEST_NETNS=1`;
  - the `test_ui_*` contracts in both engines;
  - the WebKitGTK probe at `#library/knowledge` with `--root-selector '#app-sidebar'`, and
    at an open knowledge base with
    `--root-selector '#main-content [data-testid="studio-knowledge-inventory"]'`.
    - Leg 3 found that a bare `#main-content` scans before the editor mounts.
    - `index.html` changes in this leg, so run `make restart` on the 8485 instance before
      the probe (`lru_cache`).

## Verification Steps

- AC1–AC7: the library-lane files and the new list test, plus the isolation test.
- AC8 and AC9: the gates.

## Implementation Guidance

1. **Router rows.**
   - Set knowledge and connectors to `create: true`, with their area subs.
   - Add round-trip tests, plus the `_nav.py` parity and `REDIRECT_ROWS` rows.
   - Add serialize and hydrate for `knowledge/new`, `connectors/new` and
     `connectors/{id}`, with the connector pending state and the §4 and §5 plumbing.
2. **The list host and pane.**
   - Create them in `setActiveSection`. Moving between Library sections keeps the pane.
   - Add the `renderLibraryList(scroll)` builder, the store subscriptions, the fetch
     policy and `reloadLibrary`. Feed the section caches from the store.
   - Remove the section nav.
   - Add `listPane.scrollToGroup`, with its contract tests.
3. **Detail.**
   - Add the empty states.
   - Mount the editors into the detail pane.
   - Move MCP's fetch → consume → heal path out of the grid branch.
   - Remove the grids and their dead code.
4. **Knowledge-base create component**, then the save (await the store), Cancel and
   announce flow.
5. **Connector navigation**, then save-create through `sync` with a name hint, Cancel by
   mode, then delete to the root.
6. **The Add menu** with `align: 'end'`, then its clipping check.
7. **Tests.** Migrate the files, add the helpers and new tests, extend the isolation
   test, and prune the allow-list.
8. **Docs, then the gates and the probe.**

Run the library lane after each step. It takes about 6 minutes.

## Edge Cases

- **A knowledge base, MCP server and connector that share a display name.** Namespaced
  ids keep their rows distinct.
- **A cold deep link** to `#library/mcp/{id}` before any store load. The pending-state
  paths cover it, and the list fills in once the store loads.
- **The knowledge-base detail poll.** Leaving Library stops it (leg 3 isolation). Opening
  another knowledge base from the list stops the old poll.
- **Deleting the open item.** Replace to the section root. Focus follows DD8's single
  rule: the next row in list order (which may be in the next group), else the previous
  one, else Add.
  - **When to read the row index.** The delete requests live in the editor modules, so
    studio cannot read the index before the request. Read it at the top of
    `onDeleteSuccess`, before teardown and before `reloadLibrary`. The row is still
    listed at that point, because `invalidate` notifies nobody.
  - An earlier per-group variant of this rule is withdrawn, because DD8 is the flight's
    one rule.
- **Focus after a create-mode Cancel** (knowledge base and connector): the first row of
  that section's group, else Add, as leg 3 does (`focusAgentRowNear(0)`).
- **An MCP source in create mode** (`~new`) while the list notifies. `setItems` keeps
  focus, so the create form is not disturbed.
- **The Add menu while a dirty editor is open.** The `go` to `~new` asks once (router
  guard).
- **A connector type list fetch failure.** The create form shows the existing error.
  Unchanged.
- **Self-configuration surface MCP rows** never appear (plain-list store).
- **A move between Library sections while an item's editor is dirty.** It is a `go` to
  another section root, so the router guard asks once, and the pane stays.
- **A mutation in another tab or window.** The list updates on the next studio `activate`
  (forced get), within DD9's freshness bound.

## Files Affected

- `static/js/router.js`
- `areas/studio.js`, `areas/studio/knowledge-section.js`, `areas/studio/connector-editor.js`
- `areas/studio/mcp-server-editor.js`: the Back target, and the new `onListStale` callback
  fired after its `mcp-sources` invalidations (`~1354`, `~1963`)
- `areas/studio/mcp-servers-grid.js`, deleted, together with:
  - its `index.html` tag;
  - the cache-busting count (73 → 72);
  - its `DYNAMIC_SINK_BASELINE` entry (`tests/test_ui_guards.py:~185-189`).
- `static/js/icons.js` (`server`, `plug`)
- `static/js/ui/list-pane.js` (`scrollToGroup`), its contract tests and its demo
- `css/studio.css`, `css/base.css`, `css/components.css`. Take care: `.mcp-source-tile*`
  (`studio.css:~415-519`) is the agent MCPs-tab vocabulary, and `.entity-tile*` and
  `.empty-canvas` are shared with Settings and `emptyState`. Delete only Library-only
  rules, such as `.knowledge-create-form[hidden]` (`studio.css:~1186`).
- **Tests:**
  - `tests/browser/_lists.py` and `_nav.py`;
  - the files in the §7 migration table;
  - `test_flow_studio_library_list.py` (new);
  - `test_ui_library_contract.py` (`scrollToGroup`);
  - `scripts/run-tests.sh` (`library_pat`);
  - `tests/test_nav_helper.py` (the allow-list and `RETIRED_SELECTORS`);
  - `tests/test_index_asset_cache_busting.py` and `tests/test_ui_guards.py`.
- **Optional:** the agent-tab links "Create one in Knowledge." (`knowledge-tab.js:~93`) and
  "Add one in the Library." (`mcps-tab.js:~62`) may target the matching `~new`. Retargeting
  the `mcps-tab.js` link changes its `DYNAMIC_SINK_BASELINE` line in `test_ui_guards.py`.
- `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`, `the_one/agents.md`,
  `CLAUDE.md`
- `squawks/0101-kb-create-lands-on-grid-not-detail.md` (Corrective Action)
- `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`

## Citation Audit

The leg design review re-grepped these against the working tree, with legs 1–3 landed
and uncommitted. Context's `508fc83` line numbers are superseded by this table.

| Citation (working tree) | Status |
|---|---|
| `studio.js` `serializeState` `29-80`: knowledge `34-37`, connectors `43`, MCP `44-55` | verified (design review) |
| `studio.js` `hydrateState` `115-264`: knowledge `132-145`, connectors `146-148`, MCP `149-166`, consume tail `232-263` | verified (design review) |
| `studio.js` sidebar hosts: `401-405`; `LIBRARY_ROUTE_SECTION` `427-431`; `renderSectionNav` `432-449`; `updateActiveSection` `1156`; section-nav toggle `1205` | verified (design review) |
| `studio.js` knowledge bases: `renderKnowledgeSection` `498`; grid view `512-525` (`onCreateSuccess` `519-522`); `fetchKnowledgeBases_` `532`; `selectKnowledgeBase` `558`; `leaveKnowledgeDetail_` `565`; `renderKnowledgeDetailView` `571`; `mountKnowledgeDetail` `604` (`onBack` `638`) | verified (design review) |
| `studio.js` MCP: `renderMcpSourcesSection` `755` (`onBack` `786`, `onCancel` `789`, `onSaveSuccess` `798`, grid branch `863-885`); `fetchMcpSources_` `903`; `populateMcpSourcesGrid` `920`; `selectMcpSource` `934`; `enterCreateMcpSourceMode` `939`; `tryConsumePendingMcpSource` `963` | verified (design review) |
| `studio.js` connectors: `renderConnectorsSection` `999` (inline `confirmLeave` `1024-1029`, `onCancel` `1030`, `onSaveSuccess` `1031-1037`); `fetchConnectors_` `1062`; `selectConnector` `1090`; `enterCreateConnectorMode` `1098` | verified (design review) |
| `studio.js` `closeOpenItem` `1112`; `discardOpen_` `1138`; `setActiveSection` `1149` (hosts `1199-1205`); `editorOpen` `3188`; `_refresh` MCP refetch `~3165-3169` | verified (design review) |
| `router.js` `SECTIONS` `72-81`; `itemName` `404-410`; commit announce `476-483`; `confirmLeave` adapter `~545`; `go` `607-629` | verified (design review) |
| `store.js` subscribers fire on load only `55-57`; `invalidate` `84-89` | verified (design review) |
| `knowledge-section.js` grid `300-436`, POST `373`, Back `465`; `connector-editor.js` `214`, `243`, Cancel `~626`, Back `317`; `mcp-server-editor.js` Back `492` | verified (design review) |
| `components.css` menu popup `~788-807`; `menu.js` keyboard `137-144`, Escape `161-164`; `icons.js` (lucide@v0.265.0) | verified (design review) |

---

## Post-Completion

Status transitions, the flight-log update, checking off in the parent flight, and the
commit are Flight Control protocol, driven by the execution workflow. They are not
repeated here.
