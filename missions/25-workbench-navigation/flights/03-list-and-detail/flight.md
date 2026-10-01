# Flight: List and Detail

**Status**: ready
**Mission**: [Workbench Navigation and Control Library](../../mission.md)

## Contributing to Criteria

- [ ] **SC2 — Lists stay put** (the list/detail half; Flight 2 delivered the leave guard).
  - Opening any agent, Library item (knowledge base, MCP server, connector) or Settings
    page shows it beside a list that stays visible.
  - No surface replaces its list with an editor or needs a Back control.
  - Creating an item opens it (closes squawk 0101).
  - Leaving unsaved changes through a list row asks first.
  - *(behavior-test-backed: the new `list-and-detail`)*
- [ ] **SC4 — Agents at scale.**
  - The agent list is alphabetical, with a filter by name, model or provider.
  - It stays responsive and visually intact with at least 30 agents.
- [ ] **SC6 — Control library** (continued). The list pane, the Add menu, the grouped
  Settings nav and the empty states on these surfaces come from `App.ui`. Each has a
  demo, an inventory row and contract tests in both engines.
- [ ] **SC8 — Matches the approved samples.**
  - The Agents, Library and Settings frames follow reference spec §3, §4 and §6–§8.
  - The operator checkpoint after this flight is the first visual review.
  - Flight 6 closes this criterion.
- [ ] **SC10 — Operable and regression-safe.**
  - Lists, the Add menu and the Settings nav are keyboard-operable with visible focus.
  - Landmarks and the skip link are preserved.
  - Suites, guards and behavior specs pass.

## Pre-Flight

### Objective

Turn each destination's surface into a list beside a detail pane, as the approved boards
draw it:

| Destination | Left column | Detail |
|---|---|---|
| Agents | An alphabetical agent list with a filter. | The current tabbed editor, hosted with only its chrome changed. |
| Library | One grouped list (Knowledge bases · MCP servers · Connectors) with an **Add** menu. | The knowledge base, MCP server and connector editors, hosted unchanged inside. |
| Settings | A grouped nav of links. | The pages, each under a page header. Item pages (a provider, a built-in tool) keep their list visible. |

Back controls are retired: the list is always there. Creating any item opens it.
Editor internals are out of scope; the next mission redesigns them (mission decision 7).

### Open Questions

- [x] Where the list column lives, its width and the 1024px behaviour → DD1
- [x] Item header and page header; Back retired; unsaved indicator → DD2
- [x] Split the studio module or extend it → DD3
- [x] Agents list: rows, filter, count, selection, scale → DD4
- [x] Library list: groups, rows, meta, the Add menu, empty detail → DD5
- [x] Settings nav: groups, links, the 240 vs 261 width, splitting General → DD6
- [x] How a provider or built-in tool item opens while its list stays visible → DD7
- [x] Create routes, "create opens the new item" (0101), Cancel and Delete → DD8
- [x] Route announcer consistency on create (a Flight 2 debrief finding) → DD8
- [x] `App.store` collections for the Library and "used by" counts → DD9
- [x] Control-library work: list pane gaps and the Settings nav → DD10
- [x] Tests: migration, helpers, lanes → DD11
- [x] Behavior specs and apparatus → DD12
- [x] Reference spec §15 items owned by Flight 3 → DD13
- [x] Operator checkpoint → DD14

### Design Decisions

**DD1 — The list column lives in the destination sidebar; widths are fixed.**

- **Agents.** `DESTINATIONS.agents.sidebar` becomes `true`.
- **Agents and Library.** `#app-sidebar` hosts the destination's **list column**. The
  width comes from a new token `--list-w: 300px` (border-box, reference spec §1.2 and §3).
- **Settings.** The sidebar hosts the **Settings nav** at `--settings-nav-w: 260px`
  (border-box). This resolves A2 by choosing the approved 261px render within 1px.
- **Chats.** Keeps `--sidebar-w` (240px, 200px under 1280px) until Flight 4 rebuilds it.
- **Widths do not shrink.** Under 1280px the list stays 300px and the Settings nav stays
  260px; only the detail pane gives up width. At the 1024px supported minimum:
  - the Agents and Library detail is 1024 − 72 − 300 = **652px**. The tabbed editor's
    content column is 640px (§4), so it fits.
  - the Settings page is 1024 − 72 − 260 = **692px**.
- **Mechanism (design review, issue 1).**
  - `applyShell` (`router.js:406-411`) also sets `aside.dataset.destination`.
  - `css/base.css` gains `#app-sidebar[data-destination="agents"|"library"]` (width
    `--list-w`) and `[data-destination="settings"]` (width `--settings-nav-w`). These rules
    are placed **after** the `max-width: 1279px` rule so they win, and they zero the
    aside's `padding-top`.
  - The list pane's body is the only scroller inside the `overflow: hidden` aside and
    `.sidebar-panel` (`base.css:31,44`).
- **Detail pane.** `#main-content` becomes the detail pane: a fixed header above a
  scrolling body (A27).
- **Padding and copy.** The sidebar's `padding-top: 10px` and `.sidebar-panel` rules stay
  for Chats. The list column and the Settings nav set their own padding per §3 and §8.1.
- **Verification.** Leg 3 measures geometry at 1440×900 and at 1024×768 in both engines.
  - **The 1024px figure is optimistic.** The tabpanel's 20px side padding and a classic
    scrollbar (about 15px) leave about 600px of content. The 640px is a max-width, so
    nothing clips.
  - **Leg 3 gate.** **No tab-strip wrap at 1024px in both engines.**

**DD2 — Item header, page header; Back retired; an unsaved indicator.**

- **Item header (Agents and Library): the editors keep their own header** (design
  review, question 1, option b).
  - Every editor already renders the §4 anatomy: `.editor-header`, then
    `.editor-header-text` with `h1.editor-title`, then `.form-actions`. Examples are
    `provider-editor.js:55-70` and `mcp-server-editor.js:492`.
  - Flight 3 adds the **breadcrumb** (11px, `--fg-muted`) as the first child of
    `.editor-header-text`: "Agents", "Library / {Group}" or "Settings / Providers". It is
    built with DOM APIs, with no new HTML-string sink.
  - **Where it is inserted** (cycle 2, issue 5):
    - **String-built editors** (`agent-editor.js:66-67`, `mcp-server-editor.js:475-476`,
      the provider editor): insert it **after** `innerHTML` is set.
    - **DOM-built editors** (`knowledge-section.js:457-458`, `connector-editor.js:287-288`):
      insert it during construction.
    - **The knowledge-base detail** re-mounts on Save (`knowledge-section.js:452-456`), so
      the breadcrumb is re-added as part of the re-mount.
    - **The knowledge-base `~new` create form** is its own component with its own header.
      Its title is the single `<h1>` in the pane.
  - Flight 3 removes the Back button from each editor's header.
  - **The host renders no second header.** Exactly one `<h1>` and one set of action
    testids per detail pane; contract-tested.
- **Page header (Settings).** Settings pages render the §4 page header:
  `<h1 class="page-title">` with the page's primary action (for example "Add provider").
- **Back controls retired.** They are deleted together with their testids:
  - `back-agent-btn`
  - `back-knowledge-btn`
  - `back-mcp-source-btn`
  - `back-connector-btn`
  - `back-provider-btn`
  - `back-tool-btn`

  `docs/ui-testid-registry.md` records them as retired. A test guard fails if any of them
  reappears.
- **Header actions** are the editors' existing `.form-actions`, unchanged, with their
  testids kept. No new primary action is added.
- **Unsaved indicator (A15).** When the open item is dirty, the header shows the caption
  "Unsaved changes" (11px, `--status-warning`) before the actions.
  - It reads the area's `App.nav` dirty source, so it is never a second dirty flag.
  - It is inserted at the start of the editor's `.form-actions`.
  - It is guidance from the superseded B1 board. It is flagged at the operator checkpoint
    (DD14) for go or no-go.
- **Delete (A18).** Delete stays where each editor has it today, in the agent editor's
  General-tab danger zone and the editors' delete buttons. Moving it is next-mission
  editor work.

**DD3 — Extend the studio module; do not split it.**

- **Decision.** `studio.js` keeps serving both Agents and Library through the Flight 2
  alias layer. Each section renders its list pane into the shared sidebar panel, and its
  detail into `#main-content`.
- **Why not split.** Splitting into Agents and Library modules is about 4–6 legs of
  refactor (the Flight 2 debrief). It would:
  - move every `.area-studio` CSS scope;
  - move every studio test selector;
  - deliver nothing visible.

  The next mission rewrites these editors' internals and is the natural point to split.
- **Guards against leaks** (the Flight 2 debrief's alias-layer debt):
  - **(a) The sidebar panel is re-rendered on every section switch.** `setActiveSection`
    renders the active section's list pane and destroys the previous one (`destroy()`), so
    no Library list survives into Agents.
  - **(b) One regression test per leak class.** It walks Agents → Library → Agents →
    Library through items and asserts:
    - the list, the selection and the detail for each destination;
    - no stray rows;
    - exactly one list pane mounted.
  - **(c)** `hydrateState`'s branch for each `sub` gains the list-pane selection sync.
  - **(d) Single-closure races** (design review, issue 6). The regression also covers:
    - switching destination during an in-flight `loadAll` or knowledge-base poll, with
      no stale render;
    - leaving Library stops the knowledge-base poll timer;
    - `selectSeq` and `editorGen` stale-then guards hold.
  - **(e) List-pane lifetime.** `mountArea` does not re-run `init`/`deactivate` between
    Agents and Library (same area, `app.js:52-75`). So **`setActiveSection` owns creating
    and destroying the list pane.**
- **Divert trigger.** If (a)–(c) cannot stop a leak, see Adaptation Criteria.

**DD4 — The Agents list (§6.1).**

- **List pane.** `App.ui.listPane`:
  - title "Agents" plus a count "{shown} of {total}";
  - a "New" action (`.btn-outlined-primary.btn-sm`, plus icon, testid `new-agent-btn`
    kept);
  - a filter labelled "Filter agents", placeholder "Filter by name, model or provider";
  - rows sorted flat A–Z by `localeCompare` (no grouping, no pinning).
- **Row.**
  - A provider dot: `.badge--{type}`, 8×8, `aria-hidden`.
  - Name (13px) and model id (11px mono, `--fg-muted`).
  - A31: the row's accessible name appends the provider name, for example
    "Research assistant, Claude Max", so the dot is not colour-only.
  - The row is an `<a href="#agents/{name}">` with testid `agent-item`, kept so the
    router and `App.nav` handle it.
  - The selected row carries `aria-current="page"`.
- **Filter.** Matches `name + " " + model + " " + providerType` after trimming and
  lower-casing (A16: the type slug, as the board does).
  - No match shows `No agents match "{q}".` with the count at "0 of N".
  - The detail pane keeps showing the selected agent even when the filter hides its row
    (§10 item 7).
- **Selection and scroll (A26).** On load and on every navigation to an agent, the
  selected row is scrolled into view with `block: 'nearest'`.
- **Scale.** 30+ agents must stay responsive, so filtering hides rows without rebuilding
  them (`listPane` already does).
  - Leg 3 measures filter keystroke latency at 60 versus 10 agents.
  - The gate is a **ratio** (60-agent time ≤ 3× the 10-agent time) plus a loose
    absolute bound, in Chromium with CDP CPU throttling at 4×. WebKit is reported, not
    gated (design review, issue 11).
  - The 60-agent `GET /api/agents` costs one `store.load` per agent (`api.py:716-723`).
    Leg 3 measures it, and a squawk is logged if a forced refresh at activation takes
    over 300ms.
- **Detail.** The item header (DD2) with breadcrumb "Agents", hosting the existing tabbed
  editor unchanged.
  - The board's "Chat" header action belongs to Flight 4, whose picker and pending
    new-chat flow it needs. It is not added here (recorded deviation).
- **No agent open.** At `#agents` with nothing selected, the detail pane shows a
  pane-size `App.ui.emptyState`:
  - with agents: "Select an agent to edit it, or create a new one." with a "New agent"
    action;
  - with zero agents: the existing "No agents yet" copy and CTA, in the detail pane.

**DD5 — The Library list (§7.1) and the Add menu (A14).**

- **List pane.** `App.ui.listPane` with title "Library" and an **Add** action.
  - The Add action is an `App.ui.menu` button: `.btn-outlined-primary.btn-sm`, plus icon,
    testid `library-add-btn`.
  - Its items:
    - "Knowledge base", which goes to `#library/knowledge/~new`;
    - "MCP server", which goes to `#library/mcp/~new`;
    - "Connector", which goes to `#library/connectors/~new`.
  - Testids are `library-add-knowledge`, `library-add-mcp` and `library-add-connector`.
- **Intro (A19).** "Things agents can use. Attach them from an agent's Knowledge and MCPs
  tabs." The board's "Capabilities" does not exist this mission.
- **Groups**, in order: **Knowledge bases**, **MCP servers**, **Connectors**.
  - Each group sorts A–Z.
  - A group with no items shows its own empty line, for example "No knowledge bases yet."
    (DD10 adds per-group empty text).
- **Rows** are `<a href>` with these icons and meta (§13 deviations noted):

  | Type | Icon | Meta | Testid |
  |---|---|---|---|
  | Knowledge base | database | `{n} agents`, from agents' `kb_ids`. The board's `{n} files` is dropped because it needs one status request per knowledge base (N+1). This is a recorded deviation. | `knowledge-base-card` (kept) |
  | MCP server | server | `{n} tools` (from the source's cached tool list; "Tools not loaded" until the first refresh) · `{n} agents` (from `mcp_source_ids`). The connection state is pre-accepted deviation D3. | `mcp-source-card` (kept) |
  | Connector | plug | `{n} agents`: distinct agents named by `config.default_agent` and by `config.channel_map` values, where the list payload carries them. Inbound routing checks `channel_map` first (`inbound.py:341-348`), so `default_agent` alone undercounts. The channel count is pre-accepted deviation D4. | `connector-card` (kept) |

  The selected row carries `aria-current="page"`.
- **Library sections nav removed.** The Flight 2 "Library sections" nav (Knowledge, MCP
  Servers, Connectors buttons) is removed; the groups replace it.
  - The section routes stay: `#library/knowledge`, `#library/mcp` and
    `#library/connectors`.
  - With no item, those routes show a pane-size empty state ("Select a knowledge base, or
    add one.") and scroll their group into view.
  - The rail's Library root stays `#library/knowledge`.
- **Detail.** The item header with breadcrumb "Library / {Group}", hosting the existing
  editors (§7.2 body out of scope).
- **Add menu clipping.** The Add menu popup must not be clipped by the aside's
  `overflow: hidden`. `App.ui.menu` has no edge flip, so leg 4a verifies it, and positions
  the popup `fixed` if needed.

**DD6 — The Settings nav (§8.1).**

- **Element.** `<nav aria-label="Settings">` holding an `<h2>` "Settings" and grouped
  `<a>` items. It is built by a new library factory (DD10).
- **Groups and pages, in order:**

  | Group | Pages |
  |---|---|
  | General | Appearance, Prompts, Encryption |
  | Models | Providers |
  | Defaults for agents | Built-in tools, Knowledge indexing |
  | Developer | Design language (dev mode only) |

- **Item styling.** Items are 28px tall at 12px type. The selected item has the
  translucent wash, an inset 1px accent ring and **`aria-current="page"`** (A12).
- **Heading indent (A3).** The heading aligns with the item text, 20px from the column
  edge (B2's intent).
- **General is split into three pages.**
  - The routes are `#settings/appearance`, `#settings/prompts` and
    `#settings/encryption`. Each hosts its existing block from `system-page.js` under a
    page header.
  - `#settings/general` becomes a legacy redirect to `#settings/appearance`. That
    includes the cold-load and rail-href cases, via the Flight 2 redirect table.
  - The rail's Settings root becomes `#settings/appearance`.
  - **Owned entirely by leg 5a** (design review, issue 3), which includes the routes,
    the redirect, the rail root and every reference:
    - `router.js:12,61,71,234`. The legacy `admin/system` redirect is retargeted
      directly to `settings/appearance`, with no chained redirect.
    - The admin area's internal sub `general` becomes three sub ids (`appearance`,
      `prompts`, `encryption`), with `areaSubToRoute` and `resolve` mappings.
    - `tests/browser/_nav.py`, `test_nav_helper.py`, `test_shell_rail.py`,
      `test_router_core.py`, `test_flow_hash_routing.py`, `test_nav_guard.py`,
      `test_flow_admin_navigation.py`, `test_flow_admin_rotate_flash.py` and
      `test_theme_cross_tab_sync.py`.
    - The `workbench-navigation` and `shell-navigation-smoke` specs.
  - A **persisted-state check.** A `lastRoutes` entry holding `settings/general` resolves
    through the redirect.
  - Until leg 5a, `settings/general` stays the only General route.
- **Section-nav retired.** `areas/layout/section-nav.js` loses both its callers (Library and
  Settings). It is deleted, together with its inventory row.

**DD7 — Settings item pages keep their list visible: the table stays, and the item opens
under it.**

- **Providers.**
  - **Page.** `#settings/providers` is the §8.2 page:
    - the page header "Providers" with "Add provider" (testid `new-provider-btn` kept);
    - the intro paragraph;
    - a **table**: Name · Type · Used by.
    - The Status column is pre-accepted deviation D1 and is omitted. So is the health
      banner (D2).
  - **Rows.** Each row's Name cell is an `<a href="#settings/providers/{id}">`. The row
    for the open provider carries `aria-current="page"` and the selected-row wash.
  - **Opening an item.** `#settings/providers/{id}` and `~new` keep the table where it is
    and render the provider editor **below it**, in the same scrolling page. The editor
    is a section with:
    - its own item header: breadcrumb "Settings / Providers", the title, and the
      Save/Cancel/Test actions;
    - focus moved to the item header's title on open.
  - **Why below and not beside.** The Settings nav already takes the list column. A third
    column would leave the editor 432px at 1024px.
  - **Checkpoint question.** This is a choice where the board is silent, and the operator
    checkpoint asks about it explicitly.
- **Built-in tools.**
  - **Page.** `#settings/tools` keeps its category tabs and tool list, with the enable
    toggles.
  - **Opening a tool.** `#settings/tools/{name}` renders the tool editor below the list,
    under its item header. The tool's row is marked selected.
  - **Rows.** A tool row holds a toggle, so it stays a list item, not a single link. Its
    name becomes the link.
- **Acceptance (design review, issue 9):**
  - **Providers.** At 1440×900 with ≤6 providers, the selected row and the editor's
    header are visible together after open. The page scrolls the editor's header into
    view (`block: 'nearest'`).
  - **Tools.** The editor header is scrolled into view and the selected row is marked.
  - **The tool row's toggle never navigates.** Its click stops at the toggle.
  - **Focus** follows the single rule in DD8 ("Focus after Cancel, close or delete").
- **Other pages.** Knowledge indexing and Design language are plain pages under the page
  header.

**DD8 — Create routes are uniform; create opens the item; route announcements on create.**

- **Create routes.** Every creatable type has a reserved `~new` route:
  - `#agents/~new` (new; Flight 2 redirected it);
  - `#library/knowledge/~new` (new: a create form in the detail pane replaces the inline
    grid form);
  - `#library/mcp/~new` (exists);
  - `#library/connectors/~new` (new; Flight 2 deferred connector URLs);
  - `#settings/providers/~new` (exists).
- **Connector items.** Connector items gain `#library/connectors/{id}`, with serialize
  and hydrate, and pending-state handling on the MCP pattern.
- **Router table.** `SECTIONS` rows for the knowledge-base and connector sections become
  `create: true`, and the agents destination accepts `~new`.
  - Each change lands **in its destination leg**, together with that route's hydrate and
    create form: agents in L3, knowledge base and connectors in L4a (design review,
    issue 2). This means no interim routes.
  - Connector routes land in **L4a**, with the hosted editors (cycle 2, issue 1).
- **Save-create keeps each editor's render path; the URL moves from `~new` to the id**
  (design review, issue 5, question 4).
  - **Provider, MCP and connector** keep today's in-place `onSaveSuccess`, which switches
    to edit mode and preserves OAuth, test results and the active tab. They `sync()` the
    URL to the id.
  - **Agent** keeps `replaceWithAgent_` (`go` with replace).
  - **Knowledge base** (squawk 0101): the create form in the detail pane navigates with
    `go(href(kb), { replace: true, bypassGuard: true })` after its dirty source is
    cleared. It closes 0101.
- **`sync()` announces only a create→item transition** (cycle 2, issue 2: one rule).
  - It announces only when **the previous key was a `~new` key** and the new key has the
    **same destination and section**.
  - Compare against the previous `lastAnnounceKey` **before** overwriting it.
    `router.js:569-570` overwrites it first today.
  - Every other `sync` stays silent: canonicalisation, Chats session syncs
    (`chat.js:1237`) and the studio section syncs (`studio.js:567,640,3049`).
  - L2 unit-tests that `chat` and `agents` syncs stay silent.
  - This closes the stale "Settings — Providers — New" announcement without touching any
    render path.
- **Dirty state on save-create.** Every save-create clears its `App.nav` dirty source
  **before** any URL write, so neither the guard nor `beforeunload` sees stale dirt.
- **Per-type acceptance.** Each of the five types gets a check:
  - create opens the item;
  - the editor is not torn down: the tab and transient state are preserved;
  - the URL is the item;
  - the announcer speaks the item.
- **Announcer names.** `describeRoute` names every item from the store (DD9) with the
  item's display name, not only agents and tools. On a cold deep link the store may not
  be warm yet, so the type name is the accepted fallback for that first announcement.
  It covers:
  - providers;
  - knowledge bases;
  - MCP servers;
  - connectors.

  Unknown ids fall back to the type name.
- **Cancel.**
  - **On a create route.** Cancel runs the area's `App.nav` discard teardown and the
    dirty-source clear first. It then navigates with replace and `bypassGuard` to the
    destination root (`#agents`, `#library/{section}` or `#settings/providers`). The user
    has already chosen to discard.
  - **On an item.** Cancel reverts the edits in place, as today.
- **After delete.** The route replaces to the section or destination root, which shows
  the empty detail state, and the deleted row leaves the list.
  - **Focus after Cancel, close or delete** (one rule for every list and table; cycle 2,
    issue 4):
    - after Cancel or close: focus goes to the item's own row;
    - after delete, or when there is no row: focus goes to the nearest surviving row (the
      next row, else the previous one);
    - when the list is empty: focus goes to the list's or page's primary action ("New",
      "Add" or "Add provider").
  - **Announcement.** The route announcer speaks the root.

**DD9 — `App.store` gains the Library collections; "used by" counts are derived.**

- **New collections** in `store.js` `URLS`:
  - `knowledge-bases` (`/api/knowledge-bases`);
  - `mcp-sources` (`/api/mcp-sources`, the list shape);
  - `connectors` (`/api/connectors`).
- **Not in the store.** The agent editor's `?include_agent_surfaces=1` MCP variant stays
  a direct fetch (detail-shaped, as agent detail is in Flight 2 DD8).
- **Invalidation map**, added to `agents.md`:
  - knowledge base: create, rename and delete invalidate `knowledge-bases` and `agents`;
  - MCP source: create, save, delete and Refresh-tools invalidate `mcp-sources`, and also
    `agents` on delete;
  - connector: create, save and delete invalidate `connectors`;
  - agent save (attachments): invalidates `agents`, as today. That is enough for every
    "used by" count.
- **Subscriptions.** The Library list subscribes to `knowledge-bases`, `mcp-sources`,
  `connectors` and `agents`. The Providers table subscribes to `providers` and `agents`.
- **Counts.** "Used by N agents" is computed client-side by one helper, `App.usage`, in
  `store.js` or a sibling, from the agents collection's list shape:
  - providers: `provider_config_id`;
  - knowledge bases: `kb_ids`;
  - MCP servers: `mcp_source_ids`;
  - connectors: the distinct agents named by `config.default_agent` and by
    `config.channel_map` values, as in DD5.
  - L2 checks that `GET /api/connectors` carries `config.channel_map`. If it does not,
    the count uses `default_agent` only, and the meta reads "default agent: {name}"
    rather than an undercounted number.
  - Counts come from data, never from the board (A23).
- **Freshness bound** (as Flight 2): a destination activation `get`s with
  `{ force: true }`.
- **Migration.** Existing direct fetches of these lists in `studio.js` move to the store:
  - `/api/knowledge-bases`: the knowledge-base grid and `refreshKnowledgeBasesCache`;
  - `/api/mcp-sources`: the plain list;
  - `/api/connectors`.

  `grep` proves the migration.

**DD10 — Control-library work first.**

- **`App.ui.listPane` gains:**
  - a title count slot;
  - an intro slot;
  - per-group empty text;
  - the §3 title style (16px, 600, `--fg`);
  - `rowStyle: 'agents'|'library'` for the A8 geometry: Agents `7px 10px` with no gap,
    Library `8px 10px` with a 2px gap;
  - `scrollToSelected()`;
  - an accessible-name suffix option per row;
  - **focus preservation across `setItems`** (design review, issue 7). `setItems` rebuilds
    every row (`list-pane.js:221-250`). If a row had focus, focus and the roving tabindex
    are restored to the row with the same id, else to the selected row. Contract-tested,
    because store notifications call `setItems` while a row may be focused.

  Existing demos and tests are extended.
- **New factory `App.ui.navGroups`** for the Settings nav:
  - a `<nav aria-label>`, a heading, group labels and `<a>` items;
  - `aria-current="page"` on the selected item;
  - `setSelected()`;
  - testids supplied by the caller.

  It follows the full factory checklist: an ES5 file in `static/js/ui/`, a
  Design-language demo, an inventory row, and contract tests in Chromium and WebKit.
- **Keyboard models:**
  - list panes use `rovingFocus`: flat across groups, Home/End, clamped at the ends. This
    is already shipped.
  - the Settings nav is plain links in Tab order, matching the board's `<a>` items.
  - the Add menu uses `App.ui.menu`'s menu-button keys.
- **Contrast (A24).** The light theme's `--fg-muted` on the selected wash measures 4.43:1.
  Flight 1 owned the gate. Leg 1 adds the selected-row meta pair to
  `test_design_tokens_a11y.py` and applies the Flight 1 resolution if it was deferred.
- **Leg 1 gates.**
  - The testid registry and `test_ui_guards.py` registry sync, for new and retired
    testids.
  - The index cache-busting test, if `index.html` gains script tags.

**DD11 — Tests: migrate through helpers; lanes unchanged.**

- **Helpers.** A new `tests/browser/_lists.py` sits beside `_nav.py`:
  - `list_row(page, dest, name)`, `open_item(page, dest, name)`;
  - `expect_selected(page, dest, name)`;
  - `filter_agents(page, q)`;
  - `library_add(page, kind)`.

  Tests stop clicking `entity-tile`, `section-nav-item` and `back-*-btn` selectors
  directly.
- **Guard.** Leg 1 ships `_lists.py` and extends the AST guard (`test_nav_helper.py`) with
  these retired selectors in the same commit.
  - A per-file **allow-list** holds today's violators.
  - Each leg removes the files it migrates.
  - Leg 6 asserts that the allow-list is empty.
- **Migration.** About 37 test files pin the grids, Back controls and section nav (the
  Flight 3 research):
  - settings ~10;
  - agents ~11;
  - library 4;
  - shared ~11.

  Each destination leg migrates its own lane's files.
- **Shared-lane files are assigned explicitly** (design review, issue 8).
  - A shared file that touches both Library and Settings migrates its Library half in
    leg 4a/4b and its Settings half in leg 5a/5b.
  - The leg that first breaks a file owns its fix.
  - Leg designs list the files by name.
- **New contract tests:**
  - `listPane` additions and `navGroups`, in both engines;
  - the DD3 leak regression;
  - the 60-agent filter timing check (DD4);
  - create-opens-item for each of the five types;
  - the announcer on save-create.
- **Lanes.** Lane membership is unchanged. Any new library test file is added to
  `library_pat` in `scripts/run-tests.sh`.
- **Standing rule.** Browser verification on this host uses `THE_ONE_TEST_NETNS=1`
  (Flight 2).

**DD12 — Behavior specs and apparatus.**

- **New spec: `list-and-detail`** (SC2 list/detail half and SC4). It runs in both themes
  and covers:
  - the Agents list with 30+ seeded agents (filter, count, selection, scroll-into-view,
    editor beside the list);
  - the Library groups and the Add menu (create each type, which opens the new item);
  - the Settings nav (grouped links, General split and redirect);
  - providers: table and item under it;
  - a dirty editor plus a list-row click, which asks;
  - Cancel on create, which returns to the root;
  - delete, which leaves the root empty state.
- **Specs updated** for the new surfaces:
  - `workbench-navigation`: settings routes, Library rows and Back removed;
  - `shell-navigation-smoke`: Settings › Appearance and the Library groups;
  - `studio-agent-crud`: New goes to `~new`, the list row and no Back;
  - `system-provider-config`: table rows and the item under the table;
  - `kb-studio-round-trip`;
  - `agent-governance-and-search`.
  - The rest are updated where they name the retired surfaces (re-grep at leg start).
- **Run at flight close:**
  - `list-and-detail` (dark and light);
  - `workbench-navigation`;
  - `shell-navigation-smoke`;
  - `studio-agent-crud`;
  - `system-provider-config`;
  - `kb-studio-round-trip`.
- **Apparatus.** Specs state an **apparatus fallback list**: goldfinch, then a
  CDP-driven Chromium with real input, the Flight 2 practice.
  - The **CDP Chromium is the default for leg-level checks from leg 3 on**, and goldfinch
    is re-checked at each leg.
  - Concurrent runs give each Executor its own scratch subdirectory (Flight 2 lesson).

**DD13 — Reference spec §15 items owned by Flight 3.**

| Item | Resolution |
|---|---|
| A2 | Settings nav width 260px (DD1). |
| A3 | Heading indented to align with the item text (DD6). |
| A12 | `aria-current="page"` on the selected Settings item and on list rows (DD4–DD6). |
| A14 | The Add menu (DD5). |
| A15 | The unsaved indicator. It comes from B1 guidance and is a checkpoint question (DD2). |
| A16 | The filter matches the provider type slug (DD4). |
| A18 | Delete stays in the editors (DD2). |
| A19 | Intro copy without "Capabilities" (DD5). |
| A23 | Counts come from data (DD9). |
| A26 | Scroll the selected row into view (DD4). |
| A27 | Scrolling bodies under fixed headers (DD1). |

**DD14 — The operator checkpoint.**

After the flight lands, the Flight Director prepares:
- **A dev instance** on 8485 with a scratch data dir. It is seeded through the API with:
  - 30+ agents across several provider types;
  - 4 providers;
  - 3 knowledge bases;
  - 2 MCP servers;
  - 2 connectors.
- **Screenshots** in both themes at 1440×900 and at 1024×768 of:
  - Agents (list plus open agent, filtered, empty filter);
  - Library (list, the Add menu open, each item type open, create forms);
  - Settings (each page, Providers with an item open).
- **A comparison page** that puts the screenshots beside the reference boards. It is
  published as a private artifact so the operator can review it and share it.
- **Explicit questions** for the operator:
  - Settings items open below the table (DD7).
  - The unsaved indicator (DD2).
  - The Library knowledge-base meta drops "files" (DD5).
  - The "Chat" header action is deferred to Flight 4 (DD4).

The operator says go, or flags problems, before Flight 4.

### Citation Audit

From the Flight 3 research digest (`4828d53`). Leg designs re-verify at leg start.

| Citation | Status |
|---|---|
| `router.js` `DESTINATIONS` (agents `sidebar:false`), `SECTIONS` (KB and connectors `create:false`; providers and MCP `create:true`); `agents/~new` redirects (comment: "Flight 3's") | verified (research, `router.js:58-87`) |
| `router.js` `sync` (556–577) retitles, never announces; `describeRoute` names only agents and tools | verified (research; Flight 2 run) |
| `studio.js` `renderAgentList` 1721; `openAgent` 1954; `enterCreateMode` 1997; `doEnterCreateMode` 1968; `handleBack` 2139; `replaceWithAgent_` 1958; `save` 2739 | verified (research) |
| `knowledge-section.js:renderKnowledgeGrid` 300; inline create form; `onCreateSuccess` 390; `studio.js:491` ignores `kb` (squawk 0101) | verified |
| `mcp-servers-grid.js`; `mcp-server-editor.js:492` Back; `connector-editor.js:214` grid, `:317` Back, `:243` unstyled CTA | verified |
| `admin/providers-grid.js`; `provider-editor.js:62` Back; `tools-grid.js` (`role=list`, toggles); `tools-editor.js:132` Back; `system-page.js` (Appearance, Base Prompt, Encryption blocks) | verified |
| `areas/layout/section-nav.js:26` `renderSectionNav` (buttons, roving tabindex); callers `studio.js:408`, `admin.js:255` | verified |
| `ui/list-pane.js:67` API; `ui/menu.js:20` API; `ui/feedback.js:55` `emptyState` | verified |
| `store.js:20` `URLS = {agents, providers}`; fetch sites `studio.js:500, 1395, 864, 1202, 1023` | verified |
| `css/base.css` `#app-sidebar` width `--sidebar-w`, 200px under 1280px | verified |
| `agent-editor.js:81` Back; `router.js:255` `agents/~new` redirect; `router.js:569-570` `sync` records the announce key; `list-pane.js:221-250` `setItems` rebuilds rows; `api.py:716-723` per-agent `store.load`; `api.py:2519-2533` MCP surfaces hidden without `include_agent_surfaces`; `inbound.py:341-348` `channel_map` first | verified (Architect, cycle 1) |

### Prerequisites

- [x] Flight 2 landed (`4828d53`, plus run logs `c1cf5f5`). Branch `flight/03-list-and-detail`
  stacks on `flight/02-shell-and-router`.
- [ ] PRs #217 and #218 merged to `main`. **Not required to start.** Retarget the
  Flight 3 PR after the merges. The operator merges.
- [x] Dev instance on 8485 with a scratch data dir. **Re-verify per leg**: confirm the
  scratch data dir from `/proc/<pid>/environ`, per CLAUDE.md. Never 8484.
- [ ] **Branch stacking.** At each leg start, check `git merge-base` and the PR state of
  #217 and #218. A squash merge of either breaks the stack and needs a rebase onto `main`.
- [ ] **Behavior apparatus.** goldfinch input delivery stopped working during Flight 2.
  The CDP-driven Chromium fallback is the default from leg 3 on (DD12), and goldfinch is
  re-checked at each leg.
- [x] `THE_ONE_TEST_NETNS=1` available (`unshare -rn`), for browser lanes on this host.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified, or explicitly deferred with a re-check point
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The design review moved create routes into their destination legs, moved the General split
into leg 5a, and split the Library and Settings legs (issues 2, 3 and 8).

1. **`list-controls`.**
   - `listPane` additions, including focus preservation across `setItems`.
   - The new `navGroups` factory.
   - The `--list-w` and `--settings-nav-w` tokens.
   - The `applyShell` `data-destination` mechanism, with the per-destination widths
     applied: Library 300px and Settings 260px, each still holding today's section nav.
   - `_lists.py` and the retired-selector AST guard with its allow-list.
   - Demos, inventory rows, testid registry entries and contract tests in both engines.
   - The A24 contrast pair and the cache-busting gate.
   - A contract test in which a store notification calls `setItems` mid-roving, and focus
     survives.
   - A test that `#app-sidebar[hidden]` still wins over the new `data-destination` width
     rules (`base.css:37`).
   - No surface changes.
2. **`data-and-announcer`.**
   - The `App.store` Library collections, the invalidation map and `App.usage`.
   - The fetch-site migration.
   - `describeRoute` item names, with tests for a warm store and for the cold-load
     type-name fallback.
   - `sync()` announcing when the canonical item key changes, which fixes the provider and
     MCP create announcement.
   - No create routes and no surface changes.
3. **`agents-list-detail`.**
   - The Agents list column: filter, count, rows and scroll-to-selected.
   - The breadcrumb in the agent editor's header; agent Back and the grid retired.
   - The empty detail state and the unsaved indicator.
   - The `#agents/~new` route, replacing the Flight 2 redirect and its pinning test, with
     Cancel-on-create.
   - The DD3 leak regression (a)–(e), the ratio filter check, the 1024px tab-wrap gate and
     the `GET /api/agents` cost measurement.
   - The agents-lane migration and its share of the shared lane.
4. **`library-list`** (4a). Every row and every Add item must resolve at the end of 4a
   (cycle 2, issue 1).
   - The grouped Library list, the Add menu (checked for clipping) and the intro.
   - Group empty lines, row meta via `App.usage` and the empty detail states.
   - The Library sections nav retired.
   - **All three editors hosted beside the list**, including the router changes:
     - the connector `SECTIONS` change (`create: true`);
     - connector `{id}` and `~new` routes, with serialize, hydrate and pending state;
     - the knowledge-base `~new` create form in the detail pane (closes 0101).
   - **Interim Back.** In 4a, the editors' Back buttons route to their section root (the
     empty detail state); 4b deletes them.
   - The Library half of the shared lane.
5. **`library-editors`** (4b).
   - Breadcrumbs in the knowledge-base, MCP and connector editors (DD2 insertion rules).
   - Their Back controls retired.
   - The create-opens-item and preservation checks for the knowledge base, MCP and
     connector.
   - The rest of the library-lane migration.
6. **`settings-nav-and-general`** (5a).
   - The `navGroups` Settings nav; section-nav deleted.
   - The General split into three pages, with every `settings/general` reference moved,
     the `admin/system` redirect retargeted, the rail root and the `lastRoutes` check.
   - Page headers.
   - The Settings half of the shared lane.
7. **`settings-items`** (5b).
   - The Providers table, with the item below it and its scroll and focus rules.
   - Built-in tools, with the item below, a non-navigating toggle and the selected row.
   - Provider and tool Back retired.
   - The provider create-opens-item and announcer checks.
   - The settings-lane migration.
8. **`behavior-specs-and-close`.**
   - Author `list-and-detail`, and update the affected specs.
   - Assert the guard allow-list is empty.
   - The flight-close gates, and runs in both themes for the new spec.
   - The DD14 checkpoint package.

### Checkpoints

- [ ] `listPane` additions, `navGroups`, tokens, `_lists.py` and the guard shipped with
  demos, inventory and contract tests in both engines (L1)
- [ ] Library collections in the store, `App.usage` and item-named announcements;
  provider and MCP create announce the item (L2)
- [ ] Agents: list beside the editor, no Back, `~new` create, 30+ agents responsive, leak
  regression passes, no tab wrap at 1024px (L3)
- [ ] Library: grouped list plus Add; every row and Add item resolves; all three editors
  hosted beside the list; connector deep links; knowledge-base create opens the item
  (0101) (L4a)
- [ ] Library: breadcrumbs; no Back; create-opens-item checks for all three types (L4b)
- [ ] Settings: grouped nav of links, General split with redirects, page headers (L5a)
- [ ] Settings items open under their list, with no Back (L5b)
- [ ] Specs pass in both themes; all lanes green; guard allow-list empty; checkpoint
  package ready (L6)

### Adaptation Criteria

**Divert if**:
- **The alias layer leaks across Agents and Library** even with DD3 (a)–(e). Split the
  studio module in this flight, as a recorded scope increase: add a leg between L2 and L3.
- **The 1024px detail width breaks the hosted tabbed editor**, for example tabs that wrap
  or clipped fields. Fall back to a 260px list under 1280px, recorded as a variation.
- **Adding the breadcrumb or removing Back breaks an editor's save path.** Keep that
  editor's Back for the type, and record it as debt for the next mission.

**Acceptable variations**:
- Helper names in `_lists.py` differ.
- The count reads "{shown} of {total}" only once the list is populated; while loading it
  shows nothing.
- The Built-in tools row keeps its current card shape inside the list, as long as the
  name is a link and the open tool is marked selected.
- The knowledge-base meta drops "agents" if the agents list is not yet loaded at first
  paint; it fills in on the store notification.
- Legs 4a/4b or 5a/5b are merged back into one leg if their design review shows them
  small enough.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created
> one at a time as the flight progresses.

- [ ] `list-controls`: `listPane` additions (focus preservation), `navGroups`, width
  tokens and the `data-destination` hook, `_lists.py` with the guard allow-list, A24, and
  the factory checklist.
- [ ] `data-and-announcer`: store collections, the invalidation map, `App.usage`,
  fetch-site migration, `describeRoute` names, and `sync` announcing on an item-key
  change.
- [ ] `agents-list-detail`: the list column, breadcrumb, empty state, unsaved indicator,
  `~new` and Cancel, Back and grid retired, the DD3 regression, the ratio filter check
  and the tab-wrap gate.
- [ ] `library-list`: the grouped list, Add menu, intro, meta and empty states; the
  sections nav retired; all three editors hosted beside the list; connector routes and
  pending state; the knowledge-base `~new` form (0101); interim Back to the section root.
- [ ] `library-editors`: breadcrumbs, Back retired, and the create-opens-item and
  preservation checks.
- [ ] `settings-nav-and-general`: the `navGroups` Settings nav, section-nav deleted, the
  General split with every reference and redirect, and page headers.
- [ ] `settings-items`: the Providers table with the item below it, Built-in tools with
  the item below it, and provider and tool Back retired.
- [ ] `behavior-specs-and-close`: `list-and-detail`, spec updates, gates and runs, and
  the checkpoint package.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged to `main` (after #217 and #218; the operator merges)
- [ ] Tests passing:
  - `make lint` and `make test-unit`;
  - all five lanes (with `THE_ONE_TEST_NETNS=1`);
  - the library contract tests in both engines.
- [ ] Documentation updated:
  - `CLAUDE.md` (routes, the store collections, `_lists.py`);
  - `the_one/agents.md` (list/detail shell, the invalidation map, create routes, the
    retired section-nav);
  - `docs/ui-testid-registry.md` (retired Back testids, new testids);
  - `docs/ui-control-inventory.md`.
- [ ] Squawk 0101 closed in the flight commit
- [ ] Operator checkpoint held, and its outcome recorded in the flight log

### Verification

- **Unit**: `make lint`, `make test-unit`. These include the guards, registry, inventory
  and contrast tests.
- **Browser**: the five lanes one at a time (`THE_ONE_TEST_NETNS=1`), plus every
  `test_ui_*` contract test in both engines.
- **WebKitGTK**: the probe at `#agents`, `#library/knowledge` and
  `#settings/appearance`.
- **Behaviour**:
  - `list-and-detail` (dark and light);
  - `workbench-navigation`;
  - `shell-navigation-smoke`;
  - `studio-agent-crud`;
  - `system-provider-config`;
  - `kb-studio-round-trip`.
- **Flight review**: a Reviewer and an Accessibility Reviewer.
- **Operator checkpoint** (DD14).
