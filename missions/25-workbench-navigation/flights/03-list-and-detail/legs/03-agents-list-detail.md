# Leg: agents-list-detail

**Status**: completed
**Flight**: [List and Detail](../flight.md)

## Objective

Make Agents a list beside a detail pane (DD1–DD4, DD8):

- **List column.** An alphabetical agent list sits in the sidebar column: filter,
  "{shown} of {total}" count, provider dot, name and model line, selection, and
  scroll-to-selected.
- **Detail pane.** The existing tabbed editor is hosted beside the list, with the
  "Agents" breadcrumb and with Back removed.
- **Empty detail state.** It shows when no agent is open.
- **Create route.** `#agents/~new` becomes a real create route, replacing Flight 2's
  redirect, with Cancel-on-create.
- **Unsaved indicator.** It appears in the editor header.
- **Retired.** The agents tile grid and its page header.
- **Regressions.** The DD3 leak and race regressions, the scale checks and the 1024px
  tab-wrap gate land with this leg.

## Context

- **Flight decisions:**
  - DD1: column width and mechanism. Leg 1 shipped `--list-w`, `data-destination` and
    the width rule. **This leg** sets `DESTINATIONS.agents.sidebar = true` and applies
    `padding-top: 0` for agents.
  - DD2: breadcrumb in the editor's own header; Back retired; the unsaved indicator.
  - DD3: extend studio, guards (a)–(e).
  - DD4: the list spec.
  - DD8: create, Cancel and delete; the focus rule.
  - DD11: tests and the guard allow-list.
- **Leg 1 outputs used here:**
  - `App.ui.listPane` with `count`, `rowStyle: 'agents'`, `scrollToSelected`,
    `nameSuffix`, and focus preservation across `setItems`;
  - `tests/browser/_lists.py`;
  - the retired-selector guard and its allow-list.

  Read the leg 1 entry in the flight log for the shipped API before starting.
- **Leg 2 outputs:** `App.store` collections and `App.usage` (only `agents` and
  `providers` matter here); `describeRoute` names.
- **Studio structure** (`areas/studio.js`):
  - `init(sidebar, content)` at `:236`;
  - the sidebar holds `.studio-section-nav` (`:368`), the **Library** section nav;
  - the content holds `.studio-section-content` (`:373`) and `.studio-editor` (`:374`);
  - the agents content is built at about `:376-391`: the `h1.page-title` "Agents", the
    `new-agent-btn`, and `.entity-tile-grid[role=listbox]`;
  - `renderAgentList` at `:1721` builds `button.entity-tile.agent-item`, with
    `aria-label` set to the name;
  - `renderAgentsSection` at `:427`;
  - `setActiveSection` at `:1110-1166` handles outgoing-section cleanup and renders by
    section;
  - `updateContentVisibility` at `:1172-1177` toggles between the grid and the editor.
- **Agent create today:**
  - `enterCreateMode` (`:1997`) runs an inline `App.nav.confirmLeave` gate, then calls
    `doEnterCreateMode` (`:1968`).
  - Create is URL-less: `writeUrl_` writes `agents`.
  - `renderEditor(null)` builds the create form.
  - Save-create goes through `replaceWithAgent_` (`:1958`), a `go` with replace and
    bypass.
- **Router:** `router.js:254-256` redirects `agents/~new` to `agents`, with the comment
  "Flight 3's". `DESTINATIONS.agents` has `sidebar: false` (`:59`).
- **Agent editor header:** `areas/studio/agent-editor.js:66-90` is string-built.
  - The title is `h1.editor-title` ("New Agent" in create mode).
  - `.form-actions` holds Back (`back-agent-btn`, `:79-81`), Cancel (`cancel-agent-btn`)
    and Save (`save-agent-btn`).
  - `handleBack` is at `studio.js:2139`.
- **Studio's agents subscription:** `App.store.subscribe('agents', ...)` at
  `studio.js:1580` re-renders the grid only when no agent is selected and the area is
  not in create mode.

## Inputs

- `static/js/router.js`
- `areas/studio.js`, `areas/studio/agent-editor.js`
- `static/js/ui/list-pane.js` (consumer only, plus the one option this leg may add)
- `css/studio.css`, `css/base.css`
- `tests/browser/` agents-lane files, and shared-lane files on the guard allow-list
  that touch Agents (enumerate them at leg start: `grep agent-item|back-agent-btn|entity-tile`)
- `tests/browser/_lists.py`, `tests/browser/_nav.py`
- `docs/ui-testid-registry.md`

## Outputs

**1. Shell.**
- `DESTINATIONS.agents.sidebar` becomes `true`.
- The CSS sets `#app-sidebar[data-destination="agents"] { padding-top: 0 }`.
- Inside the studio sidebar panel, an **Agents list host** (`.studio-agents-list`) and the
  existing `.studio-section-nav` are siblings. Exactly one is visible: Agents shows the
  list, Library shows the section nav until leg 4a replaces it.
- **Owner.** `setActiveSection` owns the visibility switch and the list pane's lifetime
  (DD3 (e)). It creates the pane on entering Agents and destroys it on leaving.
- **Hiding.** Hide either host with the existing `.is-hidden` class
  (`components.css:1647`). Keep calling `App.layout.updateActiveSection` for the hidden
  section nav, which is harmless.
- **Flex sizing** (design review, item 5). `.sidebar-panel` is a column with
  `overflow: hidden` (`base.css:53-54`). `.ui-list-pane` has no `flex: 1`
  (`components.css:570`), and its body scrolls only when bounded (`:599-604`). Add:
  - `.studio-agents-list { flex: 1; min-height: 0; display: flex; flex-direction: column }`
  - `.studio-agents-list > .ui-list-pane { flex: 1 }`
  
  The 35-agent scroll check proves the result.

**2. The Agents list** (DD4). One `App.ui.listPane`:
- **Pane options:**
  - title "Agents", `count: true`;
  - action "New": `App.ui.button`, outlined primary, small, plus icon, testid
    `new-agent-btn` (kept);
  - filter labelled "Filter agents", placeholder "Filter by name, model or provider";
  - `rowStyle: 'agents'`.
- **Filter predicate.** It matches `name + ' ' + llm_model + ' ' + providerType`, trimmed
  and lower-cased, where `providerType` is the provider's **type slug** (A16), taken from
  the providers store.
- **Items:**
  - sorted A–Z with `localeCompare` on the name;
  - `id: name`, `label: name`;
  - `meta: llm_model`, rendered **mono** by the scoped rule
    `.ui-list-pane-style-agents .ui-list-pane-meta { font-family: var(--font-mono) }` in
    `components.css`, next to the leg 1 row-style rules (`:707-708`). Check the exact
    class and token names leg 1 shipped;
  - `href: App.router.href({ destination: 'agents', id: name })`;
  - `testid: 'agent-item'` (kept);
  - `nameSuffix: ', ' + providerDisplayName` (A31).
- **Provider dot.** An 8×8 `.badge--{type}`, `aria-hidden`, **before** the text.
  - `listPane` has **no leading slot**. `buildRow` (`list-pane.js:152-197`) supports only
    `icon`, trailing `badges` and `count`.
  - This leg adds a **general library option `item.lead`**: a node placed before
    `.ui-list-pane-text`, with a `.ui-list-pane-lead { flex: none }` rule. It also adds:
    - a header-comment update (`:67-75`);
    - a both-engine contract test;
    - the inventory-row update in `docs/ui-control-inventory.md`.
- **Selection.**
  - `setSelected(name)` runs on every hydrate to an agent, including `~new`, which means
    no selection.
  - `scrollToSelected()` runs after a load and after a navigation (A26).
  - When the filter hides the selected agent, the detail pane keeps showing it (§10.7).
- **Data** (design review, item 6).
  - `renderAgentList` becomes **the one function** that computes items from
    `self._agents` and `self._allProviders`, then calls `pane.setItems(...)` and
    `pane.setSelected(...)`.
  - It is a **no-op when the pane does not exist**, for example on Library.
  - The grid body at `:1721-1837` is deleted.
  - Its six call sites stay as they are: `:430`, `:1584` (the subscription, now always
    calling it), `:1609` (after provider caps; this is what adds provider data to rows),
    `:1881`, `:1980` and `:3047`.
  - The list reads `self._agents`. Those objects may be detail-shaped after
    `_refreshAgentAfterSelfConfigurationChange` (`:1227-1230`). The list needs only
    `name`, `llm_model` and `provider_config_id`, which both shapes carry, and nothing is
    written back to the store (Flight 2 DD8).
  - A self-configuration refetch notification can land mid-`doSelect`. `setSelected`
    runs after `setItems`.
- **Retired.** The agents tile grid (`.entity-tile-grid`, `.entity-tile.agent-item`) and
  its page header. Their empty-canvas copy moves into the detail empty state.

**3. Detail pane.**
- **No agent open** (`#agents`). The detail pane shows a pane-size `App.ui.emptyState`:
  - **with agents:** title "Select an agent to edit it, or create a new one.", with
    action "New agent" (`agent-empty-new`, which navigates to `~new`);
  - **with no agents:** "No agents yet. Create one to get started.", with the same
    action. Keep testid `agent-empty` on this state.
- **Agent open.** The existing editor (`renderEditor`), hosted unchanged except for:
  - **Breadcrumb.** A `<div class="editor-breadcrumb">` with "Agents", inserted after the
    editor's `innerHTML` is set, as the first child of `.editor-header-text`. It is built
    with DOM APIs (DD2).
  - **Back removed.** `back-agent-btn` is deleted from `agent-editor.js`, together with
    `handleBack` and its wiring.
  - **Unsaved indicator** (DD2, A15).
    - When the editor is dirty, a caption `<span class="editor-unsaved"
      data-testid="editor-unsaved">Unsaved changes</span>` (11px, `--status-warning`)
      sits at the start of `.form-actions`.
    - It is driven by the same `checkDirty()` that flips the Save and Cancel `disabled`
      state, so there is no second dirty flag.
    - In create mode it shows once any field differs from the defaults. `checkDirty`
      (`studio.js:2484`) already runs in create mode, with no `_createMode` exclusion.
    - **Markup.** A **stable** `<span class="editor-unsaved" role="status"
      data-testid="editor-unsaved">` is part of the `.form-actions` string in
      `agent-editor.js:78-86`. That `innerHTML` statement is baselined
      (`test_ui_guards.py:161-163`), and its text is unchanged.
    - `checkDirty` toggles the span's text ("Unsaved changes" or empty). It never creates
      or destroys the node.
    - `renderEditor` rebuilds the header, so it calls `checkDirty` after the build.
- **Content visibility.** `updateContentVisibility` shows the editor when an agent is
  selected or in create mode, and the empty state otherwise. The grid branch is removed.

**4. Create route** (DD8).
- **Router** (design review, item 1: the sentinel must round-trip).
  - **The sub is `agents/~new`.** Agent names are always written with a leading `~` as
    `%7E` (`enc()`), so `agents/~new` (a raw `~`) can only mean create.
  - **`areaSubToRoute`** (`router.js:186-189`, which runs `escapeEncoded` on every agents
    segment) **special-cases `segs[1] === '~new'`** and emits the route `agents/~new`
    **unescaped**.
  - **`resolve`** (`router.js:254`). The redirect is replaced by
    `mk('agents/~new', dest, 'agents/~new', redirected)`.
  - **`href`** (`:131-150`, whose agents branch ignores `spec.create` today) and
    **`parse`** (`:160-170`) handle `create`.
  - **`studio.js` `serializeState`** (`:24-77`):
    - It uses plain `encodeURIComponent` (`:49, 55, 59`), which leaves `~`, so an agent
      named `~new` would serialize as `agents/~new/general`. Add a local helper that
      writes a leading `~` as `%7E` for agent-name segments.
    - Add a create branch, `if (_activeSection === 'agents' && _createMode) return
      'agents/~new'`, **before** the `_pendingSelectName` check (`:42-48`) and the
      `_selectedAgent` check (`:49`).
  - **The hydrate sub-parser** (`studio.js` ~`:147`) compares the raw segment `~new`
    before it decodes.
  - **Round-trip tests:**
    - `agents/~new` means create;
    - `agents/%7Enew/general` is an agent named `~new`;
    - `agents/new/general` is an agent named `new`.
- **Entering create.**
  - "New" (list action) and the empty-state action call
    `App.router.go(href({ destination: 'agents', create: true }))`. That is an intent
    `go`, so the router's leave guard asks once when an open agent is dirty.
  - **`enterCreateMode` is deleted** (`:1997`), together with its inline
    `App.nav.confirmLeave` gate. Its two callers become `go(href(create))`:
    - the empty-canvas CTA (`:1743`), which is replaced by the empty state's action;
    - `newAgentBtn` (`:3078`).
  - `doEnterCreateMode` stays as the hydrate target.
  - **"New" while the clean create form is already open.** The `go` to the same route is
    a router no-op; confirm with `sameRoute`. It is pinned by a test: nothing re-renders,
    and focus moves to the name field.
  - **Focus on entering create.** Focus goes to the name field (`#studio-name`).
  - `hydrateState` for the create sub calls `doEnterCreateMode`.
  - `serializeState` in create mode returns the create sub, so `writeUrl_` keeps
    `#agents/~new`.
- **Save-create.** It keeps `replaceWithAgent_`, a replace `go` to the new agent that
  announces it. It clears `dirty` before navigating (DD8).
- **Cancel in create mode.** It runs the studio discard teardown (`discardOpen_`), then
  `go(href({ destination: 'agents' }), { replace: true, bypassGuard: true })`. Focus
  follows the DD8 rule: no row to return to, so the nearest row, else the "New" action.
- **Cancel on an open agent.** It reverts in place, unchanged.

**5. Delete** (DD8; design review, item 4).
- **Fallbacks replaced.** Three code paths fall back to `self._agents[0]` today:
  - `handleDeleteEditor` (`studio.js:2184-2188`) does `replaceWithAgent_(self._agents[0])`
    when agents remain;
  - the save-then-concurrent-delete race (`:2877-2878`) does the same.

  Both change to **an unconditional replace to the `#agents` root** (a new
  `replaceWithAgentsRoot_()`), so the empty state shows, and the row leaves the list on
  the store notification. The save-create path at `:2768` is unaffected.
- **Focus.** Capture the deleted row's index **before** the delete request, because
  `setItems` restores focus only when the focused row had focus.
- Focus goes to the nearest surviving row (next, else previous), else to "New".
- The announcer speaks "Agents".

**6. DD3 regressions** (a)–(e), in one new file, `tests/browser/test_agents_library_isolation.py`.
It must be added to a lane: it belongs to `agents`, so add it to that lane's glob or
explicit list. It covers:
- **Destination walk.** Agents → open agent A → Library (an item) → Agents → Library →
  Agents. At every step:
  - the visible list host matches the destination;
  - exactly one list pane is mounted in the studio sidebar;
  - the right selection and detail are showing;
  - there are no stray rows.
- **Destination switch mid-load.** Switch destination while `loadAll` is in flight (delay
  hook) and while a knowledge-base poll is active (Library knowledge detail). Then check:
  - there is no stale render on arrival;
  - the knowledge-base poll timer stops on leaving Library, asserted through a fetch
    counter;
  - the `selectSeq` and `editorGen` stale-then guards hold.

**7. Scale checks.**
- **Ratio filter timing** (DD4).
  - Seed 60 agents and, separately, 10.
  - Measure script time per filter keystroke (a `performance.now()` delta around the
    input handler, or the CDP `Performance` metrics) in Chromium with
    `Emulation.setCPUThrottlingRate(4)`.
  - **Gate:** the 60-agent median is at most 3× the 10-agent median, and at most 50ms
    absolute under throttle.
  - WebKit is reported, not gated.
- **`GET /api/agents` cost at 60 agents** (`api.py:716-723`, a per-agent `store.load`).
  Measure the server time. If a forced refresh at activation exceeds 300ms, log a squawk
  and do not fix it here.
- **30+ agents render intact.** At 1440×900, 35 agents: the list scrolls, rows stay
  48px ±1, there is no overlap, and the title row and filter stay fixed.

**8. Tab-overflow gate** (design review, item 3).
- The editor always has **five tabs**: General, Knowledge, MCPs, Built-in Tools and
  Self-configuration (`agent-editor.js:92-113`).
- `.tablist` is a flex row with no wrap (`components.css:1075-1080`), so tabs can only
  overflow; they never wrap.
- **At 1024×768**, assert `tablist.scrollWidth <= tablist.clientWidth`, and that the
  last tab's right edge is inside the detail pane, in both engines.
- The pane is 1024 − 72 (rail) − 300 (list) = 652px. The estimated tab width is about
  590px.

**9. Tests.**
- **Agents-lane migration.** Every agents-lane file and every shared-lane file this leg
  breaks moves to `_lists.py` helpers and the new structure: no `entity-tile`, no
  `back-agent-btn`.
- **Scope** (design review, item 8): about 15 of the 29 allow-listed files.
  - `agent-item` is in 15 test files.
  - `back-agent-btn` is in 4 (11 hits in `test_flow_dirty_confirm.py`).
  - `entity-tile` is in 16. **Only the agents usages** are in scope. Provider, admin and
    Library `entity-tile` files stay allow-listed until legs 4a, 4b and 5b.
  - `agent-empty` is in 4.
  - `new-agent-btn` is in 14. It still works wherever the button stays visible at
    `#agents`; it breaks where a test clicks it while on Library.
  - `test_flow_agent_tile.py` (12 `entity-tile` hits) is expected to need a **rewrite**
    into a list-row test, not a patch.
- **Listing.** List every migrated file in the flight-log entry, and keep the
  allow-list honest: a file leaves it only when it is fully clean.
- **Timebox.** If migration runs long, report early. Do not land a red lane.
- **New helpers in `_lists.py`:**
  - `expect_selected(page, 'agents', name)` (row `aria-current`);
  - `filter_agents(page, q)`;
  - `agents_new(page)`;
  - `agents_empty_state(page)`.
- **Seeding helper.** `tests/browser/seeders.py` gains
  `seed_mock_agents(base_url, provider_id, n, prefix, model=None)`. It uses a shared
  `httpx.Client`, because today only one-at-a-time `seed_mock_agent` exists
  (`seeders.py:41-110`). It also gets a provider-type or model parameter, so the
  filter-by-provider and filter-by-model tests work.
- **Dead code.** Delete the grid with its dead code: `studio.js:376-391`, `studio.css:9`
  and any grid-only CSS.
- **Allow-list.** Remove every migrated file from `RETIRED_SELECTOR_ALLOWLIST`, with the
  guard staying green.
- **Flight 2's pinning test** for the `agents/~new` redirect is **inverted** to assert the
  create route. Rename the test rather than deleting and re-adding it.

**10. Docs.**
- `agents.md`:
  - the Agents list and detail structure;
  - the create route sentinel;
  - the unsaved indicator;
  - the retired grid and Back.
- `docs/ui-testid-registry.md`:
  - retired: `back-agent-btn`;
  - new: `agent-empty-new`, `editor-unsaved`, and the list-pane testids;
  - `new-agent-btn` and `agent-item` are kept.
- `CLAUDE.md`: if the route table there changes, adjust the routes line.

## Acceptance Criteria

- [ ] **AC1 — List.** At `#agents` with 35 seeded agents:
  - **Order and count.** The list shows A–Z rows, and the count reads "35 of 35".
  - **Filter by name.** Typing a name fragment narrows the rows, and the count updates.
  - **Filter by model.** Typing a model fragment matches.
  - **Filter by provider.** Typing the provider type slug (for example "mock") matches,
    while the provider display name does **not** match unless it is also in the
    name or model (A16).
  - **No match.** It shows `No agents match "{q}".` and "0 of 35".
  - **Row anatomy.** Each row has the dot, the name, and the mono model line. Its
    accessible name includes the provider name.
  - All checks run in Chromium and WebKit through `engine_page` against the running
    app, or in Chromium with a spot check in WebKit; record which.
- [ ] **AC2 — Selection and detail.**
  - **Opening an agent.** Clicking a row navigates to `#agents/{name}/general`. The row
    has `aria-current="page"`, the editor shows beside the list, and the list stays
    visible.
  - **Breadcrumb.** It reads "Agents".
  - **No Back.** `back-agent-btn` does not exist.
  - **Filtered-out selection.** Filtering the open agent out keeps the editor showing.
  - **Cold deep link.** A cold load of `#agents/{25th-name}/general` scrolls the
    selected row into view inside the list scroller.
- [ ] **AC3 — Empty states.**
  - `#agents` with agents shows the select-or-create empty state, and its action opens
    `#agents/~new`.
  - With zero agents it shows "No agents yet…" with `agent-empty`.
  - Neither state shows an editor.
- [ ] **AC4 — Create.**
  - **Entry points.** "New" and the empty-state action go to `#agents/~new` and show the
    create form beside the list, with focus on the name field.
  - **Repeat "New".** Pressing it with the clean create form already open is a no-op,
    and focus stays on or returns to the name field.
  - **Leave guard.** From a dirty open agent, "New" asks once (the router guard); Stay
    keeps both the edit and the URL.
  - **Save-create.** Saving opens the new agent with the route replaced (`history.length`
    unchanged), selects its row and announces it.
  - **Cancel.** Cancel in create mode returns to `#agents` with focus on the nearest row,
    else "New".
  - **Names that look like create.** An agent named `new` stays reachable at
    `#agents/new`.
  - **Pin inverted.** The Flight 2 redirect pin is inverted (renamed).
- [ ] **AC5 — Unsaved indicator.** Editing a field shows "Unsaved changes" in the header
  actions. Save, Cancel, or Continue in the leave dialog removes it. It never appears
  while the editor is clean.
- [ ] **AC6 — Delete.** Deleting an agent:
  - lands on `#agents` (the empty state);
  - removes the row;
  - focuses the nearest surviving row, else "New";
  - announces "Agents".
- [ ] **AC7 — DD3 regressions.** `test_agents_library_isolation.py` passes every step of
  Outputs §6, in Chromium. The knowledge-base poll-stop and stale-render checks are
  asserted through counters, not timing.
- [ ] **AC8 — Scale and width.**
  - The ratio filter gate passes (Chromium, throttled), and the WebKit numbers are
    recorded.
  - The `GET /api/agents` 60-agent server time is recorded (and a squawk logged if over
    300ms).
  - 35 agents render intact.
  - At 1024×768, the tab strip does not overflow (`scrollWidth <= clientWidth`) in both
    engines.
  - At 1024×768, the aside is 300px and the detail pane is at least 650px.
- [ ] **AC9 — Tests and guard.**
  - The agents lane and every shared-lane file touched are green.
  - The migrated files are off the allow-list, and the guard is green.
  - The `_lists.py` helpers are used, and no raw retired selectors remain in the
    migrated files.
- [ ] **AC10 — Gates.**
  - `make lint` and `make test-unit` (guards, registry, inventory, contrast);
  - all five lanes, one at a time, with `THE_ONE_TEST_NETNS=1`;
  - the `test_ui_*` contracts in both engines;
  - the WebKitGTK probe, run with `/usr/bin/python3 scripts/webkitgtk_probe.py --url
    'http://127.0.0.1:8485/#agents' --data-dir /tmp/the-one-wbnav-scratch --root-selector
    '#app-sidebar'`, and again with `--url '…/#agents/{name}/general' --root-selector
    '#main-content'`, on the 8485 dev instance (never 8484). Record any pre-existing
    failure, such as squawk 0110.

## Verification Steps

- AC1–AC6: the agents-lane files, plus the new list and create tests (name them, for
  example `test_flow_agents_list.py`, and add them to the agents lane).
- AC7: `test_agents_library_isolation.py`.
- AC8: the scale and width tests (a `@pytest.mark.browser` file in the agents lane). The
  60-agent seed uses the API seeding helpers in `tests/browser/seeders.py`.
- AC9 and AC10: the gates.

## Implementation Guidance

1. **Router.**
   - Remove the `~new` redirect, choose the create sentinel, and update `href`,
     `resolve` and `areaSubToRoute`.
   - Invert the pinning test.
   - Set `DESTINATIONS.agents.sidebar = true`.
2. **Studio sidebar.**
   - Add the list host.
   - `setActiveSection` creates or destroys the agents list pane and toggles the host and
     the section-nav visibility.
   - Wire `subscribe('agents')` to `setItems`.
3. **Detail.** Add the empty state and remove the grid branch from
   `updateContentVisibility` and `renderAgentsSection`.
4. **Editor.** Add the breadcrumb insertion and remove Back and `handleBack`. Then add
   the unsaved indicator in `checkDirty`.
5. **Create, Cancel and delete flows**, with the focus rule.
6. **Tests.**
   - Migrate the agents lane and the shared files.
   - Add the helpers.
   - Add the regression, scale and width tests.
   - Prune the allow-list.
7. **Docs, then the gates and the WebKitGTK probe.**

Run the agents lane after each step. The lane is about 4 minutes.

## Edge Cases

- **Agent names** with `/`, `~`, spaces or Unicode. `href` goes through `seg()`
  (`encodeURIComponent`, plus `~` written as `%7E`). Test one name with a space and one
  starting with `~`.
- **A provider missing** for an agent (deleted provider). The dot is neutral, the
  `nameSuffix` reads "no provider", and the filter's provider slug is empty.
- **The store not yet loaded at first paint.** The list shows nothing and no count, then
  fills on the notification. That is an accepted variation.
- **Self-configuration enabled** adds a sixth tab. That is the tab-wrap gate's worst
  case.
- **Agents ↔ Library** within one area module. `mountArea` does not re-init, so the list
  host switch must happen in `setActiveSection`. Verified by AC7.
- **The rail restore href** to the last-open agent still works (Flight 2).
- **Keyboard.** Tab enters the list at the selected row (list-pane roving); Enter on a
  row navigates (native link). The filter is in Tab order before the list.

## Files Affected

- `static/js/router.js`
- `areas/studio.js`, `areas/studio/agent-editor.js`
- `static/js/ui/list-pane.js` (`item.lead`), its contract test, and
  `docs/ui-control-inventory.md`
- `tests/browser/seeders.py` (`seed_mock_agents`)
- `css/studio.css`, `css/base.css`
- `tests/browser/_lists.py`
- `tests/browser/test_flow_agents_list.py` (new), `test_agents_library_isolation.py`
  (new), and the scale and width test file (new)
- agents-lane test files (migrated), and shared-lane files touching Agents (migrated)
- `scripts/run-tests.sh` (new files into the agents lane)
- `tests/test_nav_helper.py` (allow-list pruning)
- `docs/ui-testid-registry.md`, `the_one/agents.md`, `CLAUDE.md`
- `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`

## Citation Audit

The Flight Director checked these against `508fc83`:

| Citation | Status |
|---|---|
| `studio.js:236` `init`; `:368` section nav; `:373-374` content and editor; `:376-391` agents content and grid; `:427` `renderAgentsSection`; `:1110-1166` `setActiveSection`; `:1172-1177` `updateContentVisibility`; `:1580` agents subscription; `:1721` `renderAgentList`; `:1958` `replaceWithAgent_`; `:1968` `doEnterCreateMode`; `:1997` `enterCreateMode` (inline gate); `:2007` `renderEmptyEditor`; `:2139` `handleBack` | verified |
| `agent-editor.js:66-90` string-built header; Back `:79-81` | verified |
| `router.js:59` agents `sidebar: false`; `:254-256` `~new` redirect | verified |

The leg design review re-checked these on the leg-1 working tree, where `studio.js` was
unchanged. Leg 2 may shift `studio.js` lines. Additional rows from the review:
- `router.js:131-150` (`href`), `:160-170` (`parse`), `:186-189` (`areaSubToRoute`
  escape), `:254`;
- `studio.js:24-77, 147, 1227-1230, 1743, 2184-2188, 2484, 2768, 2877-2878, 3078`;
- `list-pane.js:152-197, 241`;
- `components.css:570, 599-604, 707-708, 1075-1080, 1647`;
- `agent-editor.js:92-113`;
- `seeders.py:41-110`;
- `test_ui_guards.py:161-163`.

---

## Post-Completion

Completion steps (status transitions, the flight-log update, checking off in the parent
flight, and the commit) are Flight Control protocol, driven by the execution workflow.
They are not repeated here.
