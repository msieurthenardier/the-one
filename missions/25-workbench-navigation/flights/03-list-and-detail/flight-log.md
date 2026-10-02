# Flight Log: List and Detail

**Flight**: [List and Detail](flight.md)

## Summary

**Status**: landed (2026-10-02). PR #219, `7aa490f` + `56f7d75` + `9590984`.

All eight legs landed, and both flight-end reviewers confirmed after a fix pass. Every gate
is green: unit, all five lanes and both engines. All six close-gate behavior specs pass:

| Spec | Result |
|---|---|
| `workbench-navigation` | 28/28 |
| `kb-studio-round-trip` | 18/18 |
| `list-and-detail` | 38/38 |
| `shell-navigation-smoke` | 8/8 |
| `studio-agent-crud` | 18/18 |
| `system-provider-config` | 20/20 |

The `list-and-detail` run caught one real defect: Cancel was disabled on a pristine create
form. It was fixed in-flight (`56f7d75`) and re-verified. Squawk 0101 is closed.

Still open:
- the DD14 operator checkpoint (go or no-go before Flight 4);
- the merge to `main` (the operator merges).

---

## Reconnaissance Report

Source: the Flight 3 research digest (read-only reconnaissance of `4828d53`), plus the Flight 2 debrief and flight-close observations.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Squawk 0101 (knowledge-base create lands on the grid) | confirmed-live | `studio.js:490` ignores `kb` in `onCreateSuccess` | Fix in L4a (DD8). |
| Provider-create route announcer stays on "— New" (Flight 2 observation) | confirmed-live | `router.js` `sync` 556–577 never announces | Fix in L2 (DD8): `sync` announces the create→item transition. |
| Connectors empty-state CTA unstyled | confirmed-live | `connector-editor.js:243` lacks `btn-outlined-primary` | It goes away with the list rebuild (L4); no separate squawk. |
| Tile title runs under the badge | confirmed-live | `components.css:842` `.entity-tile-badge` is absolutely positioned | It goes away with list-pane rows (L3–L5). |
| Section-nav items are `<button>`s | confirmed-live | `section-nav.js:70` | Replaced by the grouped list and `navGroups` links (L4–L5). |
| `listPane` gaps against the reference spec (title count, intro, title style, per-group empty) | confirmed-live | `ui/list-pane.js:67`; `components.css:576` | Fixed in L1. |

---

## Leg Progress

### Leg 1: list-controls (landed, 2026-10-01)

**What landed.** No app surface uses the new list or nav yet. The visible change is the aside
width on Library (300px) and Settings (260px), each still showing today's section nav.

- **`App.ui.listPane` additions** (`static/js/ui/list-pane.js`, `css/components.css`):
  - `count: true` ("{shown} of {total}" across groups, empty at 0 items);
  - `intro`;
  - per-group `emptyText` (a zero-item group keeps its caption plus a `<p>` line that is never
    a row; it hides while a filter query is active);
  - `rowStyle: 'agents'|'library'` (A8 padding and gap, 13px names, and the opt-in 1px border
    selection model; it wins over `compact`; an unknown value throws);
  - per-item `nameSuffix` (a `.visually-hidden` span, never `aria-label`);
  - `scrollToSelected()` (`scrollIntoView({block: 'nearest'})`) and `getItems()`;
  - `setItems` keeps the query, the body's `scrollTop` and focus. It looks up the focused
    entry through `entries[]` before the rebuild, sets the tab stop explicitly after
    `applyView()`, and restores focus synchronously.
  - Every pane now gets the section 3 title row (16px/600/`--fg` h2, actions pushed right), the
    6.1 filter padding, the 3 scroller padding and the 3 group-label style.
- **`App.ui.navGroups`** (`static/js/ui/nav-groups.js`, new): a `<nav aria-label>` with an
  `<h2>`, captions, and `<ul>` lists of `<a href>` items labelled by their captions.
  - `aria-current="page"` and `setSelected`.
  - No click handler, keyboard handling or tabindex.
  - Throws on a missing label, id or href, and on a duplicate id across groups.
  - Section 8.1 geometry: items 28px at 12px, the heading indented 10px (A3).
  - Forced colours: a `Highlight` border, with padding compensated so the item stays 28px.
- **Widths** (DD1): `--list-w: 300px` and `--settings-nav-w: 260px` in `tokens.css` `:root`.
  `applyShell` sets `aside.dataset.destination`. `base.css` adds the agents/library and settings
  width rules after the media rule, never setting `display`. `padding-top` is unchanged.
- **Test helper and guard** (DD11):
  - `tests/browser/_lists.py` provides `list_row` and `open_item` over the kept testids. Name
    matching excludes `[class*=badge]`, because both provider rows carry a "mock" type badge.
    A connector, which has no item route until leg 4a, opens on its editor title.
  - `tests/test_nav_helper.py` gains `RETIRED_SELECTORS`, `RETIRED_SELECTOR_ALLOWLIST`,
    `find_retired_selectors`, `check_retired_selectors`, the self-test and
    `test_no_retired_selectors_in_browser_tests`. The helper walk covers every non-`test_`
    module in `tests/browser/`, with no allow-list.
- **Demos and docs.**
  - The `ui-lists` section gains an Agents-style pane (count, filter, agents row style, name
    suffix, 32 rows in a 300px scrolling column) and a Library-style pane (intro, library row
    style, three groups with one empty).
  - A new `navGroups` demo shows the four Settings groups with Providers selected. The section
    title becomes "Library: lists and navigation", and `admin.css` gains a
    `.design-language-ui-column`.
  - Docs: an inventory row for `navGroups`, plus updated list-pane and section-nav rows.
    `agents.md` covers the control library, the app shell, the nav-helper convention and the
    living reference. `CLAUDE.md` gets the `_lists.py` pointer and a correction to the
    App-shell widths.

**Retired-selector allow-list** (computed from the live AST walk, 29 files, which matches the
design count). Helper modules have no violations.

- `test_flow_admin_knowledge_settings.py`
- `test_flow_admin_navigation.py`
- `test_flow_admin_openrouter.py`
- `test_flow_admin_tools_editor.py`
- `test_flow_admin_tools_grid.py`
- `test_flow_agent_crud.py`
- `test_flow_agent_tabs.py`
- `test_flow_agent_tile.py`
- `test_flow_cross_area_dirty_gate.py`
- `test_flow_dirty_confirm.py`
- `test_flow_hash_routing.py`
- `test_flow_keyboard.py`
- `test_flow_provider_dirty_confirm.py`
- `test_flow_provider_grid.py`
- `test_flow_provider_setup.py`
- `test_flow_studio_knowledge_attach.py`
- `test_flow_studio_knowledge_inventory.py`
- `test_flow_studio_mcp_editor.py`
- `test_flow_studio_mcp_navigation.py`
- `test_flow_studio_navigation.py`
- `test_flow_studio_purge_now_button.py`
- `test_flow_studio_retention_error_message.py`
- `test_nav_guard.py`
- `test_router_announce.py`
- `test_router_guard.py`
- `test_router_items.py`
- `test_shell_rail.py`
- `test_studio_connector_editor.py`
- `test_visual_snapshots.py`

The regex has a left boundary only, so `entity-tile-name` counts as the retired tile while
`feedback-agent-btn` would not. It found the same 29 files as a plain substring match.

**Contrast (AC6).**
- A24 is unchanged: `test_selected_row_meta_passes_body_aa` and the three `_FILL_SITES` rows
  still pass.
- New: `test_list_pane_caption_pairs_pass_body_aa` covers `--fg-muted` on `--sidebar-bg`, and
  asserts that `--sidebar-bg` aliases `--surface` in both blocks. Dark is 4.95:1 and light is
  4.84:1, so no `--fg-secondary` fallback was needed.
- New: `test_nav_groups_pairs_pass_body_aa` covers rest, hover, selected, caption and heading,
  all at 4.84:1 or above.
- New: rule-consumption checks for both.

**Tests added.**
- `test_ui_library_contract.py`: 21 new listPane functions (42 in both engines), including the
  mid-roving store-notification test and a focus-to-filter fallback.
- `test_ui_nav_groups_contract.py` (new): 20 per engine.
- `test_shell_rail.py`: widths split by destination (Chats 240/200, Library 300 and Settings 260
  at every width); a `[hidden]`-wins test; `data-destination` across rail clicks and Back/Forward;
  the clipping-test comment refreshed.
- `test_lists_helper.py` (new, shared lane): one test per destination plus an unknown-list test.
- `test_ui_reference_page.py`: the new demos render in both themes with no console errors.

**Gates.**
- `make lint` clean, and `ruff format --check` clean.
- `make test-unit`: 5012 passed, 10 skipped, 1251 deselected (671.7s).
- Every `test_ui_*` in both engines: 422 passed, 3 skipped (WebKit has no forced-colours
  emulation) (108.1s).
- Lanes, one at a time with `THE_ONE_TEST_NETNS=1`, all green on the first run:

  | Lane | Passed | Skipped | Duration |
  |---|---|---|---|
  | chats | 42 | 0 | 96.1s |
  | agents | 97 | 2 | 214.0s |
  | library | 95 | 1 | 336.8s |
  | settings | 125 | 0 | 229.6s |
  | shared | 810 | 3 | 641.4s |

- No failures to classify.
- Manual check on the 8485 scratch instance (`/tmp/the-one-wbnav-scratch`, restarted for the
  `index.html` change): asides measured 300/260/240 at 1440 and 300/260/200 at 1024, the demos
  render in both themes, and there were no console errors.

**Deviations and decisions.**
- The global listPane restyle goes slightly beyond the title row: the filter padding
  (`0 16px 8px`), the scroller bottom padding (12px) and the group label (`12px 10px 4px`, 500)
  also move to sections 3 and 6.1, as the leg objective asks. The only consumers are the demos.
- Additions beyond the leg spec:
  - `setItems` also keeps the body's `scrollTop`. A rebuild otherwise jumps the 30+ agent list
    to the top on every store notification.
  - When no row is visible after a rebuild, focus goes to the filter instead of dropping to
    `<body>`.
  - Empty-group lines hide while a filter query is active.
  - When every group is empty, the lines show instead of the pane's empty state.
- The `nameSuffix` accessible name comes out as "Research assistant , Claude Max". The hidden
  span is blockified, so accname adds a space before it. The contract pins the order, not the
  separator, and callers pass their own ", " punctuation.
- `navGroups` items pin `line-height: 16px` (Geist's line box), so they render 28px with any
  font. The disk harness has no Geist.
- The registry is unchanged: no app testid was added (the factories forward caller testids,
  and demos pass none). The registry sync passes.
- The navGroups demo lives in `ui-lists-section.js`, which keeps 7 library sections and puts the
  cache-busting count at 73.
- The pixel snapshot baselines (local only, gitignored) for Library and Settings will differ
  because of the wider asides. Regenerate them with `--snapshot-update`.

### Leg 2: data-and-announcer (landed, 2026-10-01)

**What landed.** There is no surface change and no new route. The Library grids now read
through the store, `App.usage` exists, and the route announcer names items.

- **Store collections** (`static/js/store.js`). `URLS` gains `knowledge-bases`,
  `mcp-sources` (the plain list) and `connectors`. The API is unchanged.
- **Fetch-site migration** (`areas/studio.js`):
  - `fetchKnowledgeBases_`, `fetchMcpSources_` and `fetchConnectors_` (the grids) read
    `App.store.get(name, {force: true})`;
  - `fetchKnowledgeBases(force)` (`loadAll`) forwards `loadAll`'s own `force`;
  - `refreshKnowledgeBasesCache` forces, so DD-15's refetch on every agent-edit mount is kept.
    It already had a `.catch`, which keeps the prior cache and sets
    `_knowledgeBasesLoaded = false`;
  - every grid keeps its stale-then guard, render and failure line;
  - the editor's `?include_agent_surfaces=1` fetch and all by-id fetches are unchanged;
  - grep proof: no literal list fetch of the five collections remains outside `store.js`
    (`test_no_literal_list_fetches_outside_store`).
- **Invalidation map.** Every row of Outputs §2, after a successful response only:
  - knowledge base: create (`knowledge-bases`), rename and delete (plus `agents`, already);
  - MCP: create and save (before `onSaveSuccess`); delete and connection delete (plus
    `agents`); the `handleTestConnection` success branch, which covers Refresh, the auto-run
    after create and Phase 2 after sign-in;
  - connector: create, save and delete;
  - the non-invalidating sites are left alone, as specified.
- **`App.usage`** (a section of `store.js`): `providerAgents`, `kbAgents`, `mcpAgents`,
  `connectorAgents` (distinct names, first-seen order, empty and non-string values skipped)
  and `mcpToolCount` (`null` without `_cache.tools`). These are pure functions.
- **`describeRoute(route, nameHint)`** (`router.js`).
  - An explicit `ITEM_COLLECTIONS` map takes `settings/providers`, `library/knowledge`,
    `library/mcp` and `library/connectors` to their collections.
  - It reads `peek` with a guard (`window.App && window.App.store`, `typeof peek`, a
    try/catch), and only for those four known names.
  - Name order: the hint, then the store, then a name an earlier sync hint gave the same key,
    then the type noun ("Provider", "Knowledge base", "MCP server", "Connector"). It never
    speaks the raw id. The 30-character truncation is kept.
  - The title and the announcement share one `describeRoute`, so they always match.
- **`sync(areaId, sub, {name})`.** It reads `prevKey` before recomputing and announces only
  when `isCreateToItem(prevKey, key)` holds: a `~new` key to an item in the same destination
  and section. It records the key in every case.
  - The provider save site (`admin.js` `onSaveSuccess`) and the MCP save site (`studio.js`
    `onSaveSuccess`) pass `{ name: updated.name }`.
  - Both sites invalidate their collection first. The provider editor already did; the MCP
    editor now does.

**Request counts (AC3).** Playwright request log, (knowledge-bases, mcp-sources plain,
connectors) per step. Before = the pre-migration tree with direct fetches, measured with the
same harness. This is now `test_library_list_request_counts`, which asserts after ≤ before
and ≤ 1 per collection per step.

| Step | Before | After |
|---|---|---|
| Chats -> Library (first Studio activation, Knowledge) | 3, 0, 0 | 1, 0, 0 |
| Knowledge -> MCP (first) | 0, 1, 0 | 0, 1, 0 |
| MCP -> Connectors (first) | 0, 0, 1 | 0, 0, 1 |
| Connectors -> Knowledge (re-activation) | 1, 0, 0 | 1, 0, 0 |
| Knowledge -> MCP (re-activation) | 0, 1, 0 | 0, 1, 0 |
| MCP -> Connectors (re-activation) | 0, 0, 1 | 0, 0, 1 |
| Chats -> Library/knowledge (Studio re-activation, same section) | 2, 0, 0 | 1, 0, 0 |
| Chats -> Library/mcp (Studio re-activation, same section) | 1, 2, 0 | 1, 1, 0 |
| Chats -> Library/connectors (Studio re-activation, same section) | 1, 0, 1 | 1, 0, 1 |
| Chats -> Library/knowledge (re-activation, last on connectors) | 2, 0, 0 | 1, 0, 0 |
| Chats -> Library/mcp (re-activation, last on knowledge) | 1, 1, 0 | 1, 1, 0 |
| Chats -> Library/connectors (re-activation, last on mcp) | 1, 1, 1 | 1, 1, 1 |
| Agents -> Library/knowledge (Studio already active) | 1, 0, 0 | 1, 0, 0 |
| Cold boot library/knowledge | 3, 0, 0 | 1, 0, 0 |
| Cold boot library/mcp | 2, 1, 0 | 1, 1, 0 |
| Cold boot library/connectors | 2, 0, 1 | 1, 0, 1 |

The remaining `1, 1, 1` row is `_refresh`'s refetch of the MCP list when Studio was last on
MCP. It is unchanged from before, since `_refresh` runs before the hydrate knows the target
section.

**Agents list shape (AC4).** I checked it before writing `App.usage`: `curl` with the
credential against the 8485 scratch instance (`/tmp/the-one-wbnav-scratch`, environment
verified through `/proc/<pid>/environ`), after seeding a provider, a knowledge base, an MCP
source, an agent and a disabled connector.
- `GET /api/agents` list items carry `provider_config_id`, `kb_ids` and `mcp_source_ids`. The
  keys are `chat_history_retention_days`, `description`, `disabled_tools`, `enabled_tools`,
  `kb_ids`, `llm_model`, `max_iterations`, `mcp_overrides`, `mcp_source_ids`, `name`,
  `provider_config_id`, `self_revision_requires_approval`, `system_prompt` and
  `tool_overrides`.
- `GET /api/connectors` carries `config.default_agent` and `config.channel_map` verbatim.
- No server field was needed. `test_usage_reads_the_live_list_shape` pins this against a
  live app.

**Tests added or changed.**
- `tests/browser/test_store_library.py` (new, shared lane, 24 tests):
  - AC1: five behaviours parametrized over the three collections;
  - AC2: KB create, KB delete, MCP delete and connector create through the UI, each with an
    `invalidate` spy and the next `get`;
  - AC3: request counts;
  - AC4: four `App.usage` tests.
- `tests/browser/test_router_announce.py`:
  - AC5: warm-store naming for the four kinds; cold deep links fall back to the noun (never the
    id, never re-announced); an unknown id.
  - AC6: provider and MCP save-create announce the name; the MCP follow-up syncs (same-key
    item and section root) are silent; chat, agents, section, same-key, `~new`-to-other-section
    and `~new`-to-root syncs leave a sentinel untouched.
- `tests/test_store_static.py`: the grep proof widened to five collections; one window pin per
  invalidation-map row (`INVALIDATION_ROWS`); the name hints; the `sync` ordering
  (`prevKey` read < `isCreateToItem` < key write); the guarded, known-name store reads.
- **Falsified.** Each of these was broken in turn, and the matching tests failed (then the code
  was restored):
  - store naming;
  - the create-to-item announcement;
  - "announce on any key change";
  - the hint.

**Docs.**
- `agents.md` "Client data store": the collections table, the Library read and force policy,
  the request counts, the full invalidation map with the deliberate non-invalidations, and
  `App.usage`.
- `agents.md` "Hash routing": the `sync(areaId, sub, {name})` signature, item naming and the
  noun fallback, and the `sync` announce rule.
- `CLAUDE.md`: the `App.store` paragraph names the five collections and `App.usage`.

**Gates.**
- `make lint` clean, and `ruff format --check` clean.
- `make test-unit`: 5018 passed, 10 skipped, 1286 deselected (647.1s). That is 6 more than
  leg 1: the new static pins.
- `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y` and
  `test_store_static`: 240 passed (0.8s).
- Targeted runs:
  - `test_store_library.py`: 24 passed (67.8s);
  - `test_router_announce.py`: 13 passed (32.1s);
  - `test_store.py`, `test_flow_studio_loadall_error.py` and
    `test_flow_studio_knowledge_attach.py`: 30 passed (69.7s).
- Lanes, one at a time with `THE_ONE_TEST_NETNS=1`, all green:

  | Lane | Passed | Skipped | Duration |
  |---|---|---|---|
  | library | 95 | 1 | 343.3s |
  | settings | 125 | 0 | 234.9s |
  | chats | 42 | 0 | 97.3s |
  | shared | 843 | 3 | 757.9s |
  | agents (extra: `studio.js` changed) | 97 | 2 | 222.1s |

  Shared is 33 more than leg 1: the 24 tests in `test_store_library.py` and 9 new announcer
  tests.
- **One first-run failure, classified as a test precondition.**
  `test_refresh_failure_shows_error_without_blanking_content` failed in the targeted run before
  the lanes; see Deviations.
- **Manual check** on the 8485 scratch instance (`/tmp/the-one-wbnav-scratch`). Static JS is
  served live, so no restart was needed.
  - A cold `#library/knowledge/{id}` is titled "Library — Knowledge — Knowledge base".
  - A warm provider item is titled and announced "Settings — Providers — Shape Mock".
  - `App.usage` against live data gave provider 1, KB 1, MCP 1, connector
    `["shape-agent", "other-agent"]` and tools `null`.
  - There were no console errors.
  - The seed rows were deleted afterwards, which returns the scratch instance to empty.

**Deviations and decisions.**
- **Force policy.** `loadAll` forwards its `force` to the knowledge-base `get` instead of
  always reading non-forced, and the grids get with `force: true` on every mount rather than
  only on re-activation.
  - Why: `force` joins an in-flight request, so the outcome the leg asks for still holds. A
    first activation shares `loadAll`'s request, and nothing is duplicated within an activation
    (the AC3 table).
  - Why: it keeps DD9's freshness bound (an activation forces) and today's freshness when the
    grid mounts with nothing in flight.
  - Why: a literally non-forced `loadAll` read would fail
    `test_refresh_failure_shows_error_without_blanking_content` (re-entry must reload the KB
    list). It would also make a Library visit after Agents show a list possibly minutes old.
- **`test_flow_studio_loadall_error.py::test_refresh_failure_shows_error_without_blanking_content`**
  now waits for its healthy first mount to settle (`goto_settled`) before installing the 500
  stub.
  - It failed on the first run. The first mount's KB request was still in flight when the stub
    went in, and the re-entry's forced `get` joined it. I confirmed this with a probe: at stub
    time `peek('knowledge-bases').loaded` was false and the request was issued but unfinished.
  - This is the store's designed join, so the test's precondition was tightened, not the code.
    The stale docstrings ("none of the five fetch helpers check `r.ok`") were corrected.
- **Extra invalidation.** `studio.js::fetchMcpSourceTools` (the agent editor's MCPs-tab
  `POST …/test/connect`, which also rewrites `config._cache`) invalidates `mcp-sources`. This
  is the same reason as the Refresh row, at a site the leg's table did not list.
- **Name memo.** The router remembers a `sync` hint by route key (`hintNames`) as a fallback
  between the store and the noun. A just-created item then stays named on a later same-key
  retitle, or a Back to it, before its collection reloads. The store still wins when it holds
  the id.
- **Keys.** Announce keys now `enc()` the id, so an id can never read as the `~new` segment
  (an agent named `~new`). The keys are internal only.
- **Hint on every save.** The hint is passed on every provider and MCP save, not only on
  create. An edit-save is a same-key sync, so it stays silent, but its title now shows a
  renamed item's new name immediately.
- **AC1 test location.** The AC1 tests live in the new `test_store_library.py` rather than in
  `test_store.py`, whose scope (agents and providers) is kept. `test_store.py`'s docstring
  points to the new file.
- **Connector naming test.** Connector item routes land in leg 4a. The AC5 connector case goes
  to `#library/connectors/{id}` and checks the commit's title and announcement, which the
  router computes before the area hydrates. Today's studio hydrate falls back to the Agents
  section for that sub; leg 4a fixes this.
- **Anomaly, out of scope.** `POST /api/providers` without `base_url` returns a 500 with a raw
  Pydantic `ValidationError`, not a 422 (seen while seeding the scratch instance). The seeder's
  docstring claims a 422. No squawk has been logged yet; the Flight Director should decide.

### Leg 3: agents-list-detail (landed, 2026-10-01)

**What landed.** Agents is a list column beside a detail pane. The aside shows on Agents, the
tile grid and Back are gone, and `#agents/~new` is a real create route.

- **Shell** (DD1). `DESTINATIONS.agents.sidebar` is `true`, and `base.css` adds
  `#app-sidebar[data-destination="agents"] { padding-top: 0 }`. The studio sidebar panel holds two
  sibling hosts: `.studio-agents-list` and the Library section nav. `setActiveSection` owns which one
  shows (`.is-hidden`) and the list pane's lifetime: it creates the pane on entering Agents and
  destroys it on leaving (DD3 (a)/(e)). Flex sizing is as the design review asked
  (`.studio-agents-list { flex: 1; min-height: 0; display: flex; flex-direction: column }`,
  `> .ui-list-pane { flex: 1 }`); the pane's body is the only scroller.
- **The list** (DD4). One `App.ui.listPane`:
  - title "Agents", `count: true`, `rowStyle: 'agents'`, testid `agents-list`;
  - the title-row "New" (`App.ui.button` secondary, small, plus icon, aria-label "New agent",
    testid `new-agent-btn` kept);
  - the filter "Filter agents" / "Filter by name, model or provider" (testid `agents-filter`);
    the predicate matches `name + ' ' + llm_model + ' ' + providerType` (the type slug, A16),
    trimmed and lower-cased, against a per-row precomputed `filterText`;
  - rows A–Z by `localeCompare`, `{id/label: name, meta: llm_model (mono), href: #agents/{name},
    testid: agent-item, nameSuffix: ", " + provider name (or "no provider"), lead: the dot}`;
  - the provider dot is an `aria-hidden` `.badge.badge--{type}.badge-dot` (8px disc; an unknown
    type uses `badge--unknown`, a missing provider the hollow `.badge-dot--none`).
  - `renderAgentList(scroll)` is the one builder (all six call sites kept, plus the providers
    subscription). It calls `setItems` then `setSelected` (the pending target, else the open
    agent; none in create mode) and scrolls to the selected row after a load or navigation, never
    on a bare store notification. Every Agents hydrate ends with `_syncAgentSelection` (DD3 (c)).
    The agents subscription now always re-renders the list.
- **`listPane` library options.** `item.lead` (as specified: a node before
  `.ui-list-pane-text`, in a `flex: none` `.ui-list-pane-lead` wrapper; a non-node throws) and,
  beyond the leg, `emptyText` as a function of the trimmed query (see Deviations). Header comment,
  two both-engine contract tests and the inventory row are updated, and the Agents-style demo rows
  now carry the dot as `lead`.
- **Detail pane.** No agent open: a pane-size `App.ui.emptyState` (h2) — "Select an agent to edit
  it, or create a new one." (`agent-select-empty`) or "No agents yet. Create one to get started."
  (`agent-empty`, kept), both with "New agent" (`agent-empty-new`); nothing before the first
  load. Agent open: the editor, with `<div class="editor-breadcrumb">Agents</div>` inserted with
  DOM APIs as the first child of `.editor-header-text`, and Back (`back-agent-btn`,
  `handleBack`, its wiring) deleted. `updateContentVisibility` has no grid branch left.
- **Unsaved indicator** (DD2, A15). A stable `<span class="editor-unsaved" role="status"
  data-testid="editor-unsaved">` opens `.form-actions` (inside the baselined markup string; the
  `container.innerHTML = html;` statement is unchanged). `checkDirty` sets or clears its text from
  the same `dirty` flag as Save/Cancel; `renderEditor` calls `checkDirty` after the build. 11px
  `--status-warning`; it stays rendered while empty so the live region is in the tree.
- **Create** (DD8). Router: `href({destination: 'agents', create: true})`, `parse` →
  `{destination: 'agents', create: true}`, `resolve` → `mk('agents/~new', …)` (extra segments
  redirect away), `areaSubToRoute` emits exactly `agents/~new` unescaped. Studio:
  `serializeState` returns `agents/~new` in create mode before the pending/selected checks, and
  writes an agent name's leading `~` as `%7E` (`agentSeg`); `hydrateState` compares the raw sub
  `agents/~new` first, closes the open item (unless the create form is already open), and an agent
  sub closes an open create form. `enterCreateMode` and its inline gate are deleted;
  `doEnterCreateMode` is the hydrate target (`self._enterCreate`), waits for the providers
  through the store (a cold deep link can beat `loadAll`) and focuses `#studio-name`. "New" with
  the clean create form open on its route only refocuses the name (no `go`). Save-create keeps
  `replaceWithAgent_`. Cancel on the create form runs `discardOpen_()`, replaces to `#agents` and
  focuses the list's tab stop, else "New".
- **Delete** (DD8). The row's visible index is read before the request; on success the editor is
  torn down, the route replaces to `#agents` (announced "Agents"), and focus goes to the next row,
  else the previous, else "New". The save-race fallback and `_refresh` (open agent gone) also land
  on the root; no `self._agents[0]` fallback remains.
- **Retired.** The grid body, its page header, the empty canvas, `openAgent`, the tool-count and
  capability-chip helpers (`_countBuiltinTools`, `_countMcpTools`, `_pluralize`,
  `fetchProviderModelCaps`, `_modelCapsByProvider`), and the grid-only CSS
  (`.studio-agents-content`, `.agent-tile-caps`, `.entity-tile-tool-count`). Three
  `DYNAMIC_SINK_BASELINE` entries for `studio.js` are pruned.

**Create sentinel.** `agents/~new`, raw `~`, as the design review chose: a name's leading `~` is
always `%7E` (router `enc()`, studio `agentSeg`), so a raw `~new` in an agents sub only means
create. `routeFor('studio', 'agents/~new/general')` (a longer raw-`~` sub) still escapes to
`agents/%7Enew/general`, so Flight 2's escaping pin holds. Round trips are pinned in
`test_router_core.py` (`parse` of `#agents/~new`, `#agents/%7Enew/general`,
`#agents/new/general`) and end to end in `test_flow_agents_list.py` (agents named `new` and `~new`
open at their escaped routes, survive a reload, and `#agents/~new` opens the create form). The
Flight 2 pin (the `#agents/~new -> agents` row of `REDIRECT_ROWS`) is inverted as
`test_agents_create_route_boots_without_redirect`, and `#agents/~new` joined the JS/`_nav` parity
corpus.

**Migrated test files** (all through `_lists.py` helpers or the new structure):

| File | Lane | Change | Allow-list |
|---|---|---|---|
| `test_flow_agent_crud.py` | agents | `agents_new`, `expect_selected`, `open_item` | removed |
| `test_flow_agent_tabs.py` | agents | `first_row` | removed |
| `test_flow_agent_tile.py` | agents | deleted; rewritten as list-row tests in `test_flow_agents_list.py` | removed |
| `test_flow_studio_purge_now_button.py` | agents | `first_row` | removed |
| `test_flow_studio_retention_error_message.py` | agents | `first_row` | removed |
| `test_flow_studio_agent_save_race.py` | agents | `agents_new`; asserts the root route | not listed |
| `test_flow_studio_knowledge_attach.py` | agents | `first_row`, rail-root re-select, `agents_new` | stays (`back-knowledge-btn`, leg 4b) |
| `test_flow_studio_loadall_error.py` | agents | docstrings | not listed |
| `test_flow_studio_navigation.py` | agents | aside test inverted; `open_item`, `expect_selected`, empty state | stays (`section-nav-item`, leg 4a) |
| `test_flow_studio_openrouter_picker.py` | agents | `agents_new`; list readiness instead of the page title | not listed |
| `test_flow_cross_area_dirty_gate.py` | shared | `first_row` | removed |
| `test_flow_dirty_confirm.py` | shared | Back → "New" as the guarded leave (renamed tests); row click asks | removed |
| `test_flow_keyboard.py` | shared | agent row test rewritten (filter → Tab → row → Enter) | stays (`section-nav-item`, leg 5a) |
| `test_flow_hash_routing.py` | shared | comment | stays (`section-nav-item`, leg 5a) |
| `test_nav_guard.py` | shared | agent paths via rows/rail/"New"; the inline-dialog test moved to the connector Back; the save-then-delete phantom test re-dirties with a different value | stays (`back-connector-btn`, legs 4a/4b) |
| `test_router_items.py` | shared | agent Back → rail root, row click, create route asks once; list-never-empties check | stays (Library/Settings) |
| `test_router_core.py` | shared | pin inverted, create round trips | not listed |
| `test_shell_rail.py` | shared | aside visible at 300px on Agents, `padding-top: 0`; `[hidden]` test hides by hand | stays (`section-nav-item`, leg 4a) |
| `test_store.py` | shared | subscription test renamed; new: repaints beside an open agent | not listed |
| `test_lists_helper.py` | shared | agents smoke covers the new helpers | not listed |
| `test_ui_library_contract.py` | shared | +2 listPane tests (lead, `emptyText(q)`) | not listed |

New: `test_flow_agents_list.py` (16 tests, AC1–AC6), `test_agents_library_isolation.py` (5,
AC7), `test_flow_agents_scale.py` (6, AC8), all in the agents lane through new
`scripts/run-tests.sh` globs `test_flow_agents_*` and `test_agents_*` (`test_flow_agent_*` does not
match the plural). `_lists.py` gained `first_row`, `expect_selected`, `filter_agents`, `agents_new`,
`agents_empty_state`; `seeders.py` gained `seed_mock_agents(base_url, provider_id, n, prefix,
model=None)` over one `httpx.Client`. AC1 runs in **both engines against the running app**
(`engine_browser` plus `credentialed_context`, 35 seeded agents on a mock and an openrouter-type
provider); AC2–AC7 run in Chromium; AC8's tab-strip check runs in both engines.

**Allow-list after pruning** (29 → 22): `test_flow_admin_knowledge_settings.py`,
`test_flow_admin_navigation.py`, `test_flow_admin_openrouter.py`, `test_flow_admin_tools_editor.py`,
`test_flow_admin_tools_grid.py`, `test_flow_hash_routing.py`, `test_flow_keyboard.py`,
`test_flow_provider_dirty_confirm.py`, `test_flow_provider_grid.py`, `test_flow_provider_setup.py`,
`test_flow_studio_knowledge_attach.py`, `test_flow_studio_knowledge_inventory.py`,
`test_flow_studio_mcp_editor.py`, `test_flow_studio_mcp_navigation.py`,
`test_flow_studio_navigation.py`, `test_nav_guard.py`, `test_router_announce.py`,
`test_router_guard.py`, `test_router_items.py`, `test_shell_rail.py`,
`test_studio_connector_editor.py`, `test_visual_snapshots.py`. Every remaining hit is a Library or
Settings selector; no agents selector remains in any of them.

**Scale numbers** (AC8; `test_flow_agents_scale.py`, figures printed and `record_property`'d):

| Check | Result |
|---|---|
| Filter keystroke, Chromium, CPU x4, median per keystroke | 10 agents 0.020ms, 60 agents 0.038ms: ratio **1.93** (gate ≤ 3, ≤ 50ms) |
| Filter keystroke, WebKit (unthrottled, reported) | 10 agents 0.007ms, 60 agents 0.007–0.014ms |
| `GET /api/agents` at 60 agents | direct median 9.6ms; forced store refresh (Resource Timing request→response) 9.5–10.5ms: far under 300ms, **no squawk** |
| 35 agents at 1440×900 | body scrolls, every row 48px ±1, no overlap, header and filter fixed, document height = viewport |
| 1024×768 tab strip | Chromium and WebKit: 5 tabs on one row, tablist `scrollWidth/clientWidth` 652/652, last tab right edge 879 (Chromium) / 870 (WebKit) inside the 1024 pane edge; aside 300px, detail pane 652px |

The keystroke figure is the median over 12 rounds of (time for 10 passes of the "agent 4"
type-then-clear sequence ÷ keystrokes). `performance.now()` is coarsened (Chromium 100µs, WebKit
1ms), so per-dispatch deltas read 0 in WebKit; batching fixes that. The first measurement was a
ratio of 2.18–2.65, close to the gate, so the list pane's filter path was tightened (see
Deviations) before it settled at 1.93.

**Tab overflow** (design review item 3): no overflow in either engine at 1024×768 (above). The
editor always has five tabs; "self-configuration enabled adds a sixth" in the leg's edge cases
does not apply (the tab is unconditional).

**WebKitGTK probe** (WebKitGTK 2.52.6, dev instance 8485 / `/tmp/the-one-wbnav-scratch`, verified
through `/proc/<pid>/environ`, 35 seeded agents, no restart needed: no `index.html` or Python
change):

| URL | Root selector | Result |
|---|---|---|
| `#agents` | `#app-sidebar` (dark, light) | ok, 6 controls, 0 failures |
| `#agents/Agent%2005/general` | `#main-content` (the leg's invocation) | 1 failure: `chat-image-input` (squawk 0110, pre-existing, the hidden chat panel) |
| same | `#main-content .studio-editor:not(.is-hidden)` (the mounted editor) | 55 controls, 4 failures: the Built-in Tools category master toggles have no name — pre-existing, **squawk 0113 logged** |
| `#agents/~new` | the create form (`… #studio-name`) | ok |

The leg's `#main-content` invocation polls only until the selector exists, so it scanned before
the editor mounted (count 6, all chat controls); the editor-scoped selector waits for the mount.

**Gates.**
- `make lint` clean; `ruff format --check` clean.
- `make test-unit`: 5019 passed, 10 skipped, 1315 deselected (648.7s). One more than leg 2:
  `test_editor_header_caption_rules_consume_the_gated_pairs` (the breadcrumb and unsaved caption
  consume `--fg-muted` and `--status-warning`, both gated body AA on `--bg`). An earlier run had
  1 failure, a raw `#agents` hash in the new scale test, fixed through `_nav.current_route`.
- `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_store_static`,
  `test_ui_control_inventory`, `test_nav_helper`: 312 passed (1.4s).
- Every `test_ui_*` in both engines: 426 passed, 3 skipped (WebKit has no forced-colours
  emulation) (112.2s). Leg 1 was 422; the 4 are the two new list-pane tests in two engines.
- `test_nav_guard.py` alone after its fix: 34 passed (90.3s).
- Lanes, one at a time with `THE_ONE_TEST_NETNS=1`:

  | Lane | Passed | Skipped | Duration |
  |---|---|---|---|
  | agents | 121 | 2 | 291.6s |
  | library | 95 | 1 | 343.0s |
  | settings | 125 | 0 | 233.7s |
  | chats | 42 | 0 | 96.6s |
  | shared (rerun, see below) | 848 | 3 | 747.6s |

  Agents is 24 more than leg 2 (27 new tests, 3 retired tile tests); its 2 skips are the
  pre-existing advanced-collapsible and picker-redesign skips. Shared is 5 more than leg 2 (the
  new store test, the 2 list-pane contract tests in two engines); its 3 skips are WebKit
  forced colours. Library, settings and chats are unchanged in count.
- **Shared lane, first run: 1 failed, 847 passed, 3 skipped (773.6s).**
  `test_nav_guard.py::test_no_phantom_after_agent_save_and_delete` saved "dirty edit", then
  typed "dirty edit" again and waited for dirty. That only ever worked because of the dirty
  baseline bug this leg fixed (see Deviations): re-typing the saved value is clean. Classified as a
  test precondition; it now types a different value. The lane was rerun in full (table above).
- **First-run failures in the new tests, all test or apparatus faults except two real
  bugs:** an orphan-provider test whose model contained "mock"; `_Hold.release()` unrouting before
  continuing (Playwright then settled the held routes itself); `wait_settled` without the fetch
  tracker; a same-URL `goto` that did not reload; and the sidebar nav selector
  (`renderSectionNav` renames `.studio-section-nav` to `.section-nav`). The two real bugs, both
  fixed: the rows' `nameSuffix` spans escaping the scroller (below) and the cold-load font reflow
  (below).

**Docs.** `agents.md`: a new "Agents list and detail (M25 F3 L3)" section (hosts, list, detail,
unsaved indicator, create, delete, tests), the create route and sentinel in "Hash routing", the
list-pane leg 3 options, the aside in "App shell — invariants", the store subscription, the push
rules (no agent inline gate, no Back) and the `_lists.py` helpers. `docs/ui-testid-registry.md`:
new `agent-empty-new`, `agent-select-empty`, `agents-filter`, `agents-list`, `editor-unsaved`;
`agent-empty`, `agent-item`, `new-agent-btn` kept with notes; `back-agent-btn` and the two
`agent-tile-*` counts moved to a new "Retired testids" table (outside the guard's parse).
`docs/ui-control-inventory.md`: the list-pane and tile rows. `CLAUDE.md`: the route line
(`#agents[/~new|/{name}[/{tab}]]`), the app shell (the aside on Agents), the agents lane globs, and
an "Agents list and detail" paragraph.

**Deviations and decisions.**
- **`emptyText(q)`, a second library option.** The leg allowed one (`item.lead`), but
  `No agents match "{q}".` needs the query, and the pane built its empty title once from a string.
  A function-valued `emptyText` (called with the trimmed query, `''` without one) re-derives the
  empty title and the filter status; string callers are unchanged. It also gives the zero-agents
  list "No agents yet." instead of a no-match line. Contract-tested in both engines.
- **`.badge.badge-dot` in `components.css`** instead of an agents-scoped dot rule, so the
  design-language demo shows the same dot (as `lead`) without an `.area-studio` rule.
- **List pane filter path tightened** (library internal, no API change): one pass over the rows
  (per-group visibility counted in the same loop), `hidden` / `aria-current` mirrored per entry so
  no DOM read per row, tab stops and counts written only when they change, `announce` reuses the
  pass's count. Studio's predicate derives the needle once per query. Ratio 2.18–2.65 → 1.93.
- **List pane `position: relative`** (pane and rows). The filter status and every row's
  `nameSuffix` are `.visually-hidden` (absolute). With no positioned ancestor they escaped the
  scroller's clipping: 35 rows stretched the document to 1731px in a 900px viewport, and the
  cold-deep-link scroll landed short. A leg 1 latent bug that only a long real list shows.
- **Re-scroll after `document.fonts.ready`.** On a cold load the rows reflow when Geist arrives
  (about 0.7px a row), so the 25th row scrolled in with fallback metrics ended 18px below the
  scroller. `scrollAgentsToSelected` scrolls now and once more when the fonts are ready.
- **Dirty baseline re-taken when the model list arrives** (pre-existing bug, fixed because AC5
  needs it). `renderEditor` took the snapshot before `fetchModelsForProvider` filled the model
  select, so editing a field and reverting it still read dirty (Save enabled; with this leg,
  "Unsaved changes" shown on a clean form). While the form is clean, the snapshot is now re-taken
  when the list arrives. Reproduced on the dev instance before and after.
- **`_refresh`'s first-agent fallback** (a third `self._agents[0]` site the leg did not list) now
  heals to the root too.
- **`fetchProviderModelCaps` deleted** with the tile chips it fed: Studio no longer fetches
  `/api/providers/{id}/models` for every Ollama provider on load.
- **The create form waits for providers through the store** (cold `#agents/~new`).
- **Providers subscription** also re-renders the list (dots and names follow a provider rename).
- **Testids** beyond the leg's list: `agent-select-empty` (the with-agents empty state; `agent-empty`
  stays on the zero-agents copy, which existing tests count), `agents-list`, `agents-filter`. The
  "New" action has `aria-label="New agent"` (it contains the visible "New").
- **Empty state heading** is `h2`; the editor's `h1` stays the only `h1` in the detail pane.
- **`test_flow_agent_tile.py` deleted, not renamed**: its three cases (row testid, click opens,
  several rows) are in `test_flow_agents_list.py`.
- **`test_go_while_inline_nav_dialog_pending_resolves_stay_and_does_not_join`** now opens its
  inline dialog from the connector editor's Back: agent "New" is router-guarded since this leg, so
  it can no longer exercise an inline dialog.
- **Leg text vs code:** the Library host is `.section-nav` after `renderSectionNav` (the leg names
  `.studio-section-nav`); the list `meta` token is `--font-family-mono` (the leg wrote
  `--font-mono`).
- **Not done here:** the behavior specs `studio-agent-crud` and `stub-connector-round-trip` still
  describe the grid and "New Agent" (DD12, leg 6).
- **Squawk 0113** logged (pre-existing Built-in Tools master toggles with no accessible name).
- The local pixel baselines for Agents will differ (the aside now shows). Regenerate with
  `--snapshot-update`.
- The scratch instance is empty again (agents, providers, sessions, knowledge bases, MCP sources,
  connectors all 0).

### Leg 4a: library-list (landed, 2026-10-02)

**What landed.** Library is one grouped list column beside a detail pane. The Library section
nav and the three tile grids are gone; every row and every Add item resolves to a route,
connectors included, and creating a knowledge base opens it (squawk 0101).

- **Host** (DD3 (a)/(e)). The studio sidebar panel holds two list hosts, `.studio-agents-list`
  and `.studio-library-list` (same flex rules), and no section nav (`renderSectionNav`,
  `LIBRARY_ROUTE_SECTION` and `.studio-section-nav` are gone from studio; `section-nav.js` keeps
  its Settings caller). `setActiveSection` destroys the outgoing pane before creating the
  incoming one, so exactly one pane exists; a move between Knowledge, MCP and Connectors keeps
  the Library pane. `base.css`: `#app-sidebar[data-destination="library"] { padding-top: 0 }`.
- **The list** (DD5). One `App.ui.listPane`: title "Library", the A19 intro, `rowStyle:
  'library'`, testid `library-list`, no filter, no count. The Add action is the first production
  `App.ui.menu` (trigger "Add", secondary/small/plus, `library-add-btn`; `align: 'end'`; items
  `library-add-knowledge|mcp|connector` each `go()` to its `~new`; `menu.destroy()` with the pane).
  Groups (ids `knowledge`, `mcp`, `connectors`), each A–Z, with "No … yet." lines. Item ids are
  namespaced. Rows are `<a href>` with the kept card testids, an `aria-hidden` icon (`database`,
  and the new `server` / `plug` in `icons.js` at lucide v0.265.0) and a visible meta from
  `App.usage` (`{n} agents`; `{t} tools · {n} agents` or `Tools not loaded · {n} agents`; the
  connector's de-duplicated `default_agent` + `channel_map` count), singular for one, agent counts
  only once `agents` has loaded.
- **Data and fetch policy** (H3). Four lifetime subscriptions (registered once in `init`) feed the
  section caches (`knowledgeBases`, `mcpSources`, `connectors`), re-attempt pending MCP/connector
  consumes, and render the list only while the pane exists. Pane creation and studio `activate`
  on a Library section force-get the three collections (`loadLibrary(true)`; `_refresh`'s
  MCP-only refetch is folded in); a move between sections fetches nothing; every create, save,
  rename, delete and the MCP `onListStale` callback (new: fired after the connect-success and
  Reset-connection invalidations in `mcp-server-editor.js`) runs `reloadLibrary(name)`. The one
  builder `renderLibraryList(scroll)` is gated until all three collections have settled
  ("Loading library…" meanwhile); a never-loaded collection whose get failed reads "Couldn’t load
  {group}."; a failed refresh keeps the last-good rows. The selection follows studio state
  (including a pending deep-link id); the selected row, or at a section root its group, scrolls
  into view after a load, a navigation or the gated first fill (with leg 3's `fonts.ready`
  re-scroll), never on a bare notification.
- **`listPane.scrollToGroup(id)`** with an optional, unique `group.id` (a duplicate throws).
  Body-only scrolling (`scrollTop`, never `scrollIntoView`); a no-op for an unknown or missing id,
  a hidden group, or a group already wholly visible. Header comment, three contract tests in both
  engines, the inventory row, and the Library-style demo (a "Scroll to Connectors" button).
- **Detail pane.** Section roots show a pane-size `emptyState` (h2) with the leg's copies and
  testids and an action opening the section's `~new` (`library-empty-{group}-add`). A pending
  deep-link id shows nothing until it resolves. Items mount the existing editors beside the list;
  interim Back on all three is a `go()` to the section root, and the connector's inline
  `App.nav.confirmLeave` gate is gone. Opening another knowledge base stops the previous poll at
  once.
- **The pending-item rule** (cycle 2, high), one rule for MCP and connectors
  (`resolvePendingLibraryItem`): a root fetches nothing; a pending id on a fresh hydrate
  force-gets, consumes, then heals a dead id; on an intent it consumes from the cache, else after
  a plain `get` or on the next notification, never healing. The within-section branch is shared:
  a fresh hydrate closes the open form; an intent consumes, and on a cache miss closes the open
  form too.
- **Knowledge-base create** (DD8; squawk 0101). Router `SECTIONS` knowledge and connectors are
  `create: true`. Studio: `knowledge/new` matched before the prefix, the create flag first in
  `serializeState`, in `editorOpen()`, cleared by `closeOpenItem`, leaving Knowledge and an item
  hydrate; the `knowledge/new` hydrate closes an open item unless the form is open.
  `App.studio.renderKnowledgeCreate` (DOM-built) replaces `renderKnowledgeGrid`: breadcrumb
  "Library / Knowledge bases", `h1` "New knowledge base", the kept `kb-create-*` testids plus
  `kb-create-cancel-btn`, Create enabled ("Name is required."), disabled from submit until the
  request fails. Success: invalidate (module) → clear `dirty` only while still on the form →
  await `reloadLibrary` → re-check generation, route and `!isDeciding()` → `go(href(kb),
  {replace, bypassGuard})`; the commit announces the name; focus moves to
  `kb-folder-path-input`. Cancel discards, replaces to the root, and focuses the group's first
  row, else Add.
- **Connector URLs** (DD8). `connectors/new` and `connectors/{id}` with the pending pair (exposed
  through `defineProperty`, always overwritten, returned by `serializeState` while pending).
  Save-create re-renders in edit mode with no navigation and no hydrate, then `reloadLibrary`,
  clear `dirty`, `sync('studio', 'connectors/' + id, {name})` (announced by leg 2's rule). Cancel
  reverts in place in edit mode and discards to the root in create mode.
- **Delete** (all three). The row index is read at the top of `onDeleteSuccess` (the row is still
  listed), then teardown, replace to the root, `reloadLibrary`, and focus the row now at that
  index (next, maybe in the next group), else the previous, else Add.
- **Retired:** `renderKnowledgeGridView`/`renderKnowledgeGrid` and the inline form,
  `fetchKnowledgeBases_`, `selectKnowledgeBase`, `fetchMcpSources_`, `populateMcpSourcesGrid`,
  `selectMcpSource`, `enterCreateMcpSourceMode`, `mcp-servers-grid.js` (its `index.html` tag, the
  cache-busting count 73 → 72, its `DYNAMIC_SINK_BASELINE` entry), `fetchConnectors_`,
  `selectConnector`, `enterCreateConnectorMode`, `renderConnectorsGrid` and its CTA, and
  `.knowledge-create-form[hidden]`. `.entity-tile*`, `.page-header` and `.empty-canvas` stay
  (Settings and `emptyState` still use them).

**Tests.** New: `test_flow_studio_library_list.py` (28 tests, AC1–AC6 plus loading/failure; in
`library_pat`, and `CLAUDE.md`'s library-lane list). Extended: `test_agents_library_isolation.py`
(+1: one pane per destination, the SAME pane node across Library section moves, a new node per
visit), `test_ui_library_contract.py` (+3 `scrollToGroup` / group-id tests, both engines),
`test_ui_reference_page.py` (the demo's "Scroll to Connectors"), `test_store_static.py` (the
fetch-site pin rewritten onto the L4a policy; new `onListStale` pin), `test_nav_helper.py`
(`_nav` rows for `knowledge|connectors/~new`, the three create CTAs in `RETIRED_SELECTORS`).
Helpers: `_lists.library_add(page, kind)`, `_lists.library_empty_state(page, kind)`,
`LISTS["library/connectors"].item_route = True`; `_nav.legacy_hash`/`_from_legacy` map `~new` for
knowledge and connectors (docstring table, `REDIRECT_ROWS` and parity rows in
`test_router_core.py`); `seeders.py` gained `seed_knowledge_base`, `seed_mcp_source(…, tools=)`
(verified: `POST /api/mcp-sources` keeps `config._cache`, so the tool count needs no route stub),
`seed_connector` (disabled) and `seed_agent_with_attachments`.

**Falsified** (each broken in turn, the test failed, the code restored): the KB-create store
await (`test_kb_create_form_opens_the_new_knowledge_base`: no selected row / no name), the
activate force-get (`test_library_list_request_counts`: "Chats -> Library/knowledge … (1, 0, 0) !=
(1, 1, 1)"), the gated first fill's group scroll (`test_section_root_scrolls_its_group_into_view`
timed out), and the reserved meta line (`test_group_scroll_survives_late_agent_counts` failed on
its post-release check, the lane-found failure made deterministic).

**Migrated test files** (Library halves only; Settings and Back usages stay for 4b/5a/5b):

| File | Lane | Change | Allow-list |
|---|---|---|---|
| `test_flow_studio_knowledge_inventory.py` | library | `_create_knowledge_base` creates through Add and waits for the new KB's detail (0101), returning its id; redundant post-create card clicks dropped; root = empty state; section-nav clicks → an MCP row / the rail's Library root; description read back from the detail | stays (`back-knowledge-btn`, 4b) |
| `test_studio_connector_editor.py` | library | create through Add; empty-inventory test → empty state + action; reopen via `open_item` | stays (`back-connector-btn`, 4b) |
| `test_flow_studio_mcp_navigation.py` | library | rewritten: groups, no section nav, row opens editor, empty states | **removed** |
| `test_flow_studio_mcp_editor.py` | library | grid page title → empty state, selected/listed rows | stays (`back-mcp-source-btn`, 4b) |
| `test_mcp_test_connection_button.py` | library | none | not listed |
| `test_flow_studio_navigation.py` | agents | rewritten onto the Library list; the section-nav keyboard tests became list (flat across groups, clamped, Home/End, Enter opens) and Add-menu (Enter/Space/ArrowDown, Escape) keyboard tests | **removed** |
| `test_agents_library_isolation.py` | agents | host checks on `.studio-library-list`, pane counts, Library selection; +1 test | not listed |
| `test_router_items.py` | shared | rows through `_lists`; a list-emptied observer replaces the grid flash observer for MCP/KB; `…_closed_by_library_connectors_section` → `test_connector_editor_closed_by_back_to_the_section_root`; new `test_kb_back_clean_closes_detail` (AC3 interim Back); the connector half of `…connector_back_each_ask_once` rewritten onto the router guard and the Add menu | stays (Back, Settings) |
| `test_router_guard.py` | shared | the four "current section closes the editor" tests go through the interim Back (4b moves them to the breadcrumb link); empty states | stays (`back-knowledge-btn`, Settings) |
| `test_nav_guard.py` | shared | inline-dialog test re-homed (AC5): `App.nav.confirmLeave({caller: 'test'})` over a dirty connector `~new` form; connector Back now asks through the router guard | stays (`back-connector-btn`) |
| `test_store_library.py` | shared | request counts rewritten (`EXPECTED`: PANE (1,1,1) / MOVE (0,0,0), 16 steps, exact); create tests through Add | not listed |
| `test_flow_hash_routing.py` | shared | inventory / MCP page title → empty states | stays (Settings section nav) |
| `test_flow_dirty_confirm.py` | shared | inventory → empty state | not listed |
| `test_shell_rail.py` | shared | fit loop is Settings-only; a separate Library-list fit check (header, intro, captions, a long-named row that ellipsizes) | stays (Settings section nav) |
| `test_lists_helper.py` | shared | connector open asserts the route; the new helpers | not listed |
| `test_router_core.py` | shared | round-trip, `routeFor`/`resolve`, redirect and parity rows for `knowledge/~new`, `connectors/~new`, `connectors/{id}` | not listed |

**Allow-list after pruning** (22 → 20): `test_flow_admin_knowledge_settings.py`,
`test_flow_admin_navigation.py`, `test_flow_admin_openrouter.py`, `test_flow_admin_tools_editor.py`,
`test_flow_admin_tools_grid.py`, `test_flow_hash_routing.py`, `test_flow_keyboard.py`,
`test_flow_provider_dirty_confirm.py`, `test_flow_provider_grid.py`, `test_flow_provider_setup.py`,
`test_flow_studio_knowledge_attach.py`, `test_flow_studio_knowledge_inventory.py`,
`test_flow_studio_mcp_editor.py`, `test_nav_guard.py`, `test_router_announce.py`,
`test_router_guard.py`, `test_router_items.py`, `test_shell_rail.py`,
`test_studio_connector_editor.py`, `test_visual_snapshots.py`. Every remaining Library hit is an
interim Back (leg 4b); the rest are Settings (5a/5b).

**`nav.js`'s non-router `confirmLeave` path is now test-only** (AC5). After this leg the router
adapter is the only app caller; `test_go_while_inline_nav_dialog_pending_resolves_stay_and_does_not_join`
drives the dialog directly, so the path stays pinned rather than deleted silently.

**Gates.**
- `make lint` clean; `ruff format --check` clean (re-checked on the final tree).
- `make test-unit`: 5026 passed, 10 skipped, 1354 deselected (661.3s). Seven more than leg 3: the
  `_nav` mapping rows (3) and scoping assertions, and the new `onListStale` static pin.
- `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_store_static`,
  `test_index_asset_cache_busting`, `test_ui_control_inventory`, `test_nav_helper`,
  `test_ui_library_source`, re-run on the final tree after the late fixes: 354 passed (2.4s).
- Every `test_ui_*` in both engines (`THE_ONE_REQUIRE_WEBKIT=1`): 432 passed, 3 skipped (WebKit has
  no forced-colours emulation) (111.4s). Leg 3 was 426; the 6 are the three new list-pane tests in
  two engines.
- Lanes, one at a time with `THE_ONE_TEST_NETNS=1`:

  | Lane | Passed | Skipped | Duration |
  |---|---|---|---|
  | library (rerun) | 123 | 1 | 409.1s |
  | agents (rerun) | 123 | 2 | 298.1s |
  | settings | 125 | 0 | 229.5s |
  | chats | 42 | 0 | 95.4s |
  | shared (rerun) | 858 | 3 | 738.4s |

  Library is 28 more than leg 3 (the new file). Agents is 2 more (one Library-list test in
  `test_flow_studio_navigation.py`, one isolation test). Shared is 10 more (three router redirect
  rows, `test_kb_back_clean_closes_detail`, and the three `scrollToGroup` tests in two engines).
  Settings and chats are unchanged in count; they ran before the two late fixes below, which touch
  only the Library list's row meta and one announcer test.
- **First runs: two failures, both fixed, then the library, agents and shared lanes were rerun
  in full.** Library: 121 passed, 1 failed (406.98s) -- `test_section_root_scrolls_its_group_into_view`,
  a real layout-shift bug (see "A reserved meta line" below). Shared: 857 passed, 1 failed, 3
  skipped (739.7s) -- `test_router_announce.py::test_cold_item_routes_fall_back_to_the_type_noun`,
  a test precondition this leg's fetch policy invalidates (see below). Agents passed on its first
  run too (123 passed, 2 skipped, 298.7s).

**WebKitGTK probe** (WebKitGTK 2.52.6, dev instance 8485 / `/tmp/the-one-wbnav-scratch`, verified
through `/proc/<pid>/environ`, `make restart`ed after the `index.html` change):

| URL | Root selector | Result |
|---|---|---|
| `#library/knowledge` | `#app-sidebar` (dark, light; the leg's invocation) | ok, 5 controls, 0 failures |
| `#library/knowledge` | `#app-sidebar:has([data-testid="connector-card"])` (dark, light) | ok, 13 controls, 0 failures |
| `#library/knowledge/{id}` | `#main-content [data-testid="studio-knowledge-inventory"]` (dark, light) | ok, 12 controls, 0 failures |
| `#library/knowledge/~new` | `#main-content .knowledge-create` | ok, 4 controls, 0 failures |
| `#library/connectors` | `#main-content [data-testid="library-empty-connectors"]` | ok, 1 control, 0 failures |

The leg's `#app-sidebar` invocation matches before the gated list fills (Add plus its three menu
items), as leg 3 found for `#main-content`; the `:has()` variant waits for the rows.

**Docs.** `agents.md`: a new "Library list and detail (M25 F3 L4a)" section; "Client data store"
(the fetch policy, `reloadLibrary`, the pending-item rule, the Library subscriptions, the request
counts); "Hash routing" (the Library routes and the accepted id-exactly-`new` risk; item opens,
save-create, dead ids; the leave-guard paths, with no inline gate left and the non-router
`confirmLeave` path test-only); "App shell" (Library `padding-top: 0`, no "Library sections"
landmark); the list-pane leg 4a additions; the `_lists.py` / `seeders.py` helpers and the new
`RETIRED_SELECTORS`. `docs/ui-testid-registry.md`: new `library-list`, `library-add-btn`,
`library-add-knowledge|mcp|connector`, the `library-empty-` family, `kb-create-cancel-btn`;
card and `kb-create-*` rows reworded; `new-knowledge-base-btn`, `new-mcp-source-btn`,
`new-connector-btn` moved to "Retired testids". `docs/ui-control-inventory.md`: the menu's first
production use, `scrollToGroup`, section nav down to its Settings caller, the tile row.
`CLAUDE.md`: the `#library/…[/~new|/{id}]` route line, a "Library list and detail" paragraph, the
library-lane file list, the retired create CTAs. Squawk 0101: Corrective Action and Verification
written, status `in-progress` (the flight commit closes it with the Sign-Off).

**Deviations and decisions.**
- **A reserved meta line** (found by the library lane, see Gates). Before `agents` loads, a
  knowledge-base or connector row has no meta; the counts then turned one-line rows into two-line
  rows (+16px each). On a cold `#library/mcp` the group scroll is clamped at the body's maximum,
  so 24 knowledge bases growing pushed the MCP group back out of view
  (`test_section_root_scrolls_its_group_into_view` failed in the lane, passed alone). Rows with
  nothing known now carry a no-break-space meta (the accessible name trims it), so every Library
  row is two lines from the first fill (reference spec section 3's 50px) and nothing shifts; the
  group scroll also re-runs on `document.fonts.ready`, as the selected-row scroll does.
  `test_agent_counts_never_read_zero_while_agents_load` now pins equal row heights before and
  after the counts arrive.
- **Section caches follow the store's value** (`syncLibraryCache`), never a request's own result:
  a stale request resolving after a newer one (pane creation's get versus a delete's reload)
  could otherwise put a deleted row back. The fresh pending-item path also heals only when the
  fetch it just made agrees the id is gone. On pane creation a null cache is seeded from `peek`
  (a collection another area loaded before studio's subscriptions existed).
- **Within-section intent miss closes the open form** (MCP and connectors): when an intent's item
  is not cached yet, the section no longer re-renders the OLD item while the new one resolves;
  it shows nothing until the pending-item rule consumes it.
- **Activate force-get is literal** (`_refresh` calls `loadLibrary(true)` when the Library pane
  exists and Studio is on a Library section). A Chats → Agents trip with Studio last on Library
  therefore also refetches the three lists before the hydrate destroys the pane (not measured;
  the 16 measured steps are exact).
- **Empty-state action labels** ("Add knowledge base", "Add MCP server", "Add connector") and the
  create form's initial focus on its name field were not specified; chosen to match "New agent".
- **`kb-create-error` carries `role="alert"`** (the old inline form's line had no role).
- **Typographic apostrophes** in "Couldn’t load {group}." and the intro ("an agent’s"), as the
  existing "Couldn’t load this agent’s…" copy.
- **`test_router_announce.py::test_cold_item_routes_fall_back_to_the_type_noun`** (leg 2) failed
  in the first shared-lane run: it walked kb → mcp → connector in one document and asserted each
  collection was still cold, but entering Library now loads all three lists (pane creation, by
  this leg's design). Classified as a test precondition: each kind now starts from a fresh
  document (a reload on `settings/general`), which keeps the test's intent (a cold store speaks
  the noun, never the id).
- **Test renames:** `test_connector_editor_closed_by_library_connectors_section` →
  `test_connector_editor_closed_by_back_to_the_section_root` (it no longer involves a section
  click), `test_kb_open_no_list_refetch_no_grid_rebuild` → `…_no_list_flash`.
- **AC6 negative query**: the new test builds the retired tile class from parts
  (`"entity" + "-tile"`) so the retired-selector guard, which fences tests that drive retired
  surfaces, does not flag an assertion that they are absent.
- **Optional agent-tab links** ("Create one in Knowledge.", "Add one in the Library.") were not
  retargeted to `~new` (kept: `test_knowledge_tab_and_mcps_tab_empty_links_use_new_scheme`).
- **Not done here:** behavior specs that name the Library grids or "New Connector" (DD12, leg 6).
- The local pixel baselines for Library will differ (the list replaces the section nav and the
  grids). Regenerate with `--snapshot-update`.
- The scratch instance is empty again (agents, providers, knowledge bases, MCP sources and
  connectors all 0).

### Leg 4b: library-editors (landed, 2026-10-02)

**What landed.** Every Agents and Library item header carries a breadcrumb whose last segment
links to its root, the Library editors' Back controls are gone, all four Library forms carry
the unsaved indicator, and creating each type is checked to open the item with its editor intact.

- **Breadcrumbs** (DD2 and its refinement). The first child of `.editor-header-text`, built with
  DOM APIs (the `href` from `App.router.href`), in edit and create modes, with exactly one `h1`
  in the pane:
  - knowledge base (detail and the `~new` form): "Library / Knowledge bases", built during
    construction by a new `_breadcrumb()` helper in `knowledge-section.js`, so the detail's Save
    re-mount re-adds it;
  - MCP server: "Library / MCP servers", inserted after `innerHTML` (string-built);
  - connector: "Library / Connectors", built during construction;
  - agent: leg 3's "Agents" crumb is now a link to `#agents` (inserted after `innerHTML`).

  The last segment is `<a class="editor-breadcrumb-link" data-testid="editor-breadcrumb-link">`;
  "Library" stays plain text and the breadcrumb stays a `div`. CSS (`components.css`): the link
  inherits the breadcrumb's 11px `--fg-muted` (`color: inherit`, no rest underline), underlines
  on hover, and shows the standard 2px `--accent` `:focus-visible` ring.
- **Closing through the link** (AC2, AC5b). `studio.js` listens for clicks on its `content`
  panel, ahead of `nav.js`'s document-level interceptor. A plain activation (a click or Enter;
  modified clicks keep the browser's behaviour) is `preventDefault`ed and becomes
  `App.router.go(href, {opener: link})`: the router's guard asks once about a dirty editor
  (Stay returns focus to the link through the dialog's opener), and the root's hydrate closes
  the item. When the go resolves `true`, focus moves to the closed item's row (DD8:
  `focusAgentRowNear(visibleIndexOf(name))` / `focusLibraryRowNear(libraryRowIndex(id))`); a
  `~new` form has no row, so focus goes where Cancel on a create form sends it (the section's
  first row, else the list's primary action). The focus runs in a `setTimeout(0)`, because
  after a Continue `nav.js` focuses `<main>` from its own `setTimeout`, and the row must land
  last. It is skipped when the user has moved on.
- **Back retired** (AC2). `back-knowledge-btn`, `back-mcp-source-btn` and `back-connector-btn`
  are deleted, together with their `onBack` callbacks in the three editors and the three
  `onBack` wirings in `studio.js`.
- **Unsaved indicator** (AC3). The stable `<span class="editor-unsaved" role="status"
  data-testid="editor-unsaved">` opens `.form-actions` in the knowledge-base detail and `~new`
  form, the MCP editor (in its baselined markup string, so no new sink) and the connector
  editor. Its text follows the same report that feeds studio's `dirty`:
  - the knowledge-base detail's `checkDirty` / `recapture`;
  - the create form's `reportDirty` (also cleared on a successful Create);
  - a new `reportDirty(d)` in the MCP editor, which all three of its `onDirtyChange` sites now
    call;
  - the connector editor's new `reportDirty`, called by `markDirty`.
- **Connector edit-mode Save leaves the editor clean.** The caption clears and Save and Cancel
  disable, as in the other editors. Before, both buttons stayed enabled after an edit save
  while studio's `dirty` was already false. No `onDirtyChange` call is added there: studio's
  `onSaveSuccess` already clears `dirty` under its generation guard.
- **No router, store or lifecycle change.** Save-create paths, the knowledge-base poll and the
  pending-item rule are untouched.

**Tests.** `test_flow_studio_library_list.py` +15 tests (in `library_pat`):

| AC | Tests |
|---|---|
| AC1 | `test_each_editor_shows_its_breadcrumb_in_edit_and_create_modes` (all three types, edit and `~new`: text, link, `href`, testid, last child, one `h1`, no `.back-btn`); `test_kb_breadcrumb_survives_a_save_remount_and_the_poll_keeps_running` (a new header node, and a `/status` poll request after the re-mount) |
| AC2/AC5b | `test_breadcrumb_link_closes_the_item_and_focuses_its_row` (one per type: root, empty state, row focused, no selection, a pushed entry, no dialog); `test_breadcrumb_link_on_a_dirty_editor_asks_once` (Stay keeps the edit and focuses the link; Continue focuses the row); `test_kb_create_form_breadcrumb_link_returns_to_the_root` (clean and dirty, no POST) |
| AC3 | `test_unsaved_indicator_on_the_knowledge_base_detail`, `…_create_form`, `…_mcp_editor`, `…_connector_editor` (`role=status`, shows on an edit, clears on Cancel / Save / Continue, the same node within a mount) |
| AC4 | `test_kb_save_create_opens_the_item_and_a_row_click_does_not_prompt`; `test_mcp_save_create_keeps_the_editor_and_its_connect_state[tools\|auth_required]`; `test_connector_save_create_keeps_its_fields_and_pairing_state` |

`test_flow_agents_list.py` +1: `test_breadcrumb_link_closes_the_agent_and_focuses_its_row`
("Agents" link and `href`, close, row focus, a pushed entry; dirty: asks once, Stay focuses
the link, Continue focuses the row). The per-type AC4 checks hold the editor's header node
and transient-state node marks across the URL change, the announcement and the list reload,
and count zero hydrates and no new history entry.

**Falsified** (each broken in turn, the test failed, the code restored):
- the focus deferral (focus called synchronously): the three Continue/close pins
  (`…_dirty_editor_asks_once`, `…_kb_create_form_breadcrumb_link…`, the agents link test)
  failed with focus on `<main>`;
- the connector edit-save caption clear: `test_unsaved_indicator_on_the_connector_editor`;
- an editor re-render after the list reload (`onListStale` re-rendering the MCP section):
  `test_mcp_save_create_keeps_the_editor_and_its_connect_state[tools]` lost its Test result.

**Migrated test files** (every `back-*` usage for the three editors removed; closes go through
the new `_lists.close_item(page)`, presence markers became `save-knowledge-btn`):

| File | Lane | Change | Allow-list |
|---|---|---|---|
| `test_router_guard.py` | shared | the four "current section closes the editor" tests (`…_current_section_click_while_dirty…`, `test_clean_reclick_closes_mcp_editor`, `…_connector_editor`, `…_kb_detail`) go through the breadcrumb link; the restore test's markers | stays (Settings: `back-tool-btn`, `section-nav-item`) |
| `test_router_items.py` | shared | renamed `test_connector_editor_closed_by_breadcrumb_to_the_section_root`, `test_kb_breadcrumb_clean_closes_detail` (+ row focus), `test_mcp_breadcrumb_clean_closes_editor`, `test_dirty_mcp_breadcrumb_…`, `test_dirty_kb_breadcrumb_…`, `test_agent_create_route_and_connector_breadcrumb_each_ask_once`; `test_kb_items_push` marker | stays (Settings: `back-provider-btn`, `back-tool-btn`, `entity-tile`) |
| `test_nav_guard.py` | shared | `test_connector_breadcrumb_goes_through_app_nav` (renamed; + Stay focuses the link) | **removed** |
| `test_flow_studio_knowledge_inventory.py` | library | markers; the routing and folder-remove tests close through the link | **removed** |
| `test_flow_studio_mcp_editor.py` | library | create test closes through the link; `test_dirty_breadcrumb_close_confirm_dialog` (renamed) | **removed** |
| `test_studio_connector_editor.py` | library | three reopen-from-the-list closes | **removed** |
| `test_flow_studio_knowledge_attach.py` | agents | two markers | **removed** |

**Allow-list after pruning** (20 → 15): `test_flow_admin_knowledge_settings.py`,
`test_flow_admin_navigation.py`, `test_flow_admin_openrouter.py`, `test_flow_admin_tools_editor.py`,
`test_flow_admin_tools_grid.py`, `test_flow_hash_routing.py`, `test_flow_keyboard.py`,
`test_flow_provider_dirty_confirm.py`, `test_flow_provider_grid.py`, `test_flow_provider_setup.py`,
`test_router_announce.py`, `test_router_guard.py`, `test_router_items.py`, `test_shell_rail.py`,
`test_visual_snapshots.py`. Every remaining hit is a Settings selector (legs 5a/5b).

**AC2 grep.** `grep -r "back-knowledge-btn\|back-mcp-source-btn\|back-connector-btn" the_one/
tests/` returns exactly three lines: the entries of `tests/test_nav_helper.py`'s
`RETIRED_SELECTORS`, the guard DD2 requires to fail if a retired id reappears (leg 3's
`back-agent-btn` has the same standing entry). `the_one/` is clean: `agents.md` names the
three ids only through the registry's retired table.

**Gates.**
- `make lint` clean; `ruff format --check` clean.
- `make test-unit`: 5026 passed, 10 skipped, 1371 deselected (641.9s). The same pass count as leg 4a:
  this leg's unit-side change is extra assertions in an existing test
  (`test_editor_header_caption_rules_consume_the_gated_pairs`: the link's `color: inherit` and
  its `--accent` focus ring) and the allow-list.
- `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_store_static`,
  `test_index_asset_cache_busting`, `test_ui_control_inventory`, `test_nav_helper`,
  `test_ui_library_source`, on the final tree: 354 passed (2.3s).
- Every `test_ui_*` in both engines (`THE_ONE_REQUIRE_WEBKIT=1`): 432 passed, 3 skipped (WebKit has
  no forced-colours emulation) (111.1s). Unchanged from leg 4a: no library change.
- The eight migrated files together, before the lanes: 193 passed (604.9s).
- Lanes, one at a time with `THE_ONE_TEST_NETNS=1`, every one green on its first run:

  | Lane | Passed | Skipped | Duration |
  |---|---|---|---|
  | library | 138 | 1 | 461.7s |
  | agents | 124 | 2 | 302.4s |
  | settings | 125 | 0 | 228.6s |
  | chats | 42 | 0 | 96.0s |
  | shared | 858 | 3 | 738.9s |

  Library is 15 more than leg 4a (the new tests), agents 1 more (the "Agents" link test); the
  shared, settings and chats counts are unchanged (the shared files' changes are renames and
  migrations).

**WebKitGTK probe** (WebKitGTK 2.52.6, dev instance 8485 / `/tmp/the-one-wbnav-scratch`, verified
through `/proc/<pid>/environ`; no restart needed: no `index.html` or Python change in this leg;
an MCP server, a knowledge base, a connector, a mock provider and an agent seeded through the API
for the run):

| URL | Root selector | Result |
|---|---|---|
| `#library/mcp/{id}` | `#main-content` (the leg's invocation; dark) | 6 controls, 1 failure: `chat-image-input` (squawk 0110, pre-existing, the hidden chat panel) |
| `#library/mcp/{id}` | `#main-content .studio-section-content:has([data-testid="save-mcp-source-btn"])` (dark, light) | ok, 16 controls, 0 failures |
| `#library/mcp/~new` | same | ok, 14 controls, 0 failures |
| `#library/knowledge/{id}` | `#main-content [data-testid="studio-knowledge-inventory"]` | ok, 12 controls, 0 failures |
| `#library/knowledge/~new` | `#main-content .knowledge-create` | ok, 5 controls (leg 4a: 4; the link is the fifth), 0 failures |
| `#library/connectors/{id}` | `#main-content .studio-section-content:has([data-testid="save-connector-btn"])` | ok, 15 controls, 0 failures |
| `#agents/{name}/general` | `#main-content .studio-editor:not(.is-hidden) .editor-header` (dark, light) | ok, 3 controls, 0 failures |

As in legs 3 and 4a, the leg's bare `#main-content` invocation matches before the editor mounts
and scans the chat panel; the editor-scoped selectors wait for the mount. The scratch instance was
emptied afterwards (agents, providers, knowledge bases, MCP sources and connectors all 0).

**Docs.** `agents.md`: a new "Item header chrome" bullet in "Library list and detail" (the
breadcrumbs, insertion by build style, the link's routing and focus and why the focus waits a
task, Back retired, the unsaved indicator per editor, the connector edit-save change, the
create-opens-item checks); "Agents list and detail" (the crumb is a link); the leg 4a "Interim
Back" text replaced; "Hash routing" (the section-root close is the breadcrumb link); the
`_lists.py` helpers and the Library tests. `docs/ui-testid-registry.md`: new
`editor-breadcrumb-link`; `editor-unsaved` reworded for its five forms; `back-knowledge-btn`,
`back-mcp-source-btn` and `back-connector-btn` moved to "Retired testids" (two from the
manual-exceptions table, one from the literal table). `CLAUDE.md`: the Agents and Library
paragraphs (the root link, `_lists.close_item`). No behavior spec names the three Back ids
(re-grepped); the specs' Library updates stay with leg 6 (DD12).

**Deviations and decisions.**
- **Focus after a close via the link is studio's, not the router's.** The link has no handler of
  its own in the editors: one delegated `click` listener on studio's `content` routes every
  breadcrumb link (so the editors only build an anchor), and focuses the row after the go
  resolves. The row focus also wins after a Continue, where `nav.js`'s generic DD5 rule focuses
  `<main>`: DD8's "after close: the item's own row" is the more specific rule for this
  control. Recorded for the flight review.
- **Connector edit-mode Save now disables Save/Cancel** (the caption alone could not "clear on
  Save" honestly while Save stayed enabled). A small behaviour change, the same shape as leg 3's
  dirty-baseline fix: no test relied on Save staying enabled after an edit save (re-grepped, all
  connector Save clicks are create flows).
- **The knowledge-base create form clears its caption on a successful Create** (studio then awaits
  the list reload before opening the item, a short window in which the form is still shown).
- **"Preserved" for MCP and connectors, read against the code.** Both save-creates re-render their
  editor once, in edit mode, by design (DD8: "keep each editor's render path"): there is no Test
  result, OAuth state or pairing code in create mode to survive that render, and the MCP editor
  has no tabs. The checks therefore pin what DD8 is about: after the create's own render, nothing
  tears the editor down again (the URL `sync`, the announcement, the list reload, store
  notifications), so the auto-run Refresh result or the OAuth consent prompt (MCP), and the
  entered fields and a pairing code generated after the create (connector), survive; plus zero
  hydrates and no new history entry. Falsified (see above).
- **AC2's grep is not literally empty** (see "AC2 grep" above): the three ids remain in the guard's
  `RETIRED_SELECTORS`, as `back-agent-btn` has since leg 3.
- **Test renames** in `test_router_items.py` (the AC2 bullet's
  `test_connector_editor_closed_by_library_connectors_section` was already
  `…_closed_by_back_to_the_section_root` after leg 4a; it is now
  `…_closed_by_breadcrumb_to_the_section_root`), `test_nav_guard.py` and
  `test_flow_studio_mcp_editor.py`; the `test_clean_reclick_closes_*` names in
  `test_router_guard.py` are kept (their section note now says the Library items close through
  the link).
- **`_lists.breadcrumb_link` / `close_item`** added beyond the leg's file list, so tests never name
  the link's testid directly; `close_item` waits for nothing after the click, since a dirty
  editor asks first.
- **Not changed:** `App.usage` row meta and the pending-item rule (as the leg says); Settings
  (legs 5a/5b), whose `back-provider-btn`, `back-tool-btn` and section-nav usages keep
  `test_router_guard.py` and `test_router_items.py` on the allow-list.
- The local pixel baselines for the Library editors will differ (the breadcrumb line, no Back).
  Regenerate with `--snapshot-update`.
- No squawks logged: the only probe failure is squawk 0110 (pre-existing).

### Leg 5a: settings-nav-and-general (landed, 2026-10-02)

**What landed.** Settings' column is the grouped nav of links from reference spec 8.1, General is
three pages with their own routes, every Settings page sits under the section 4 page header with
the board's label, and `areas/layout/section-nav.js` is gone with its last caller. Leg 5b's
surfaces (the provider and tool grids, editors and Back) are unchanged.

- **The nav** (DD6, DD13 A2/A3/A12). `admin.js` builds one `App.ui.navGroups({label: 'Settings',
  heading: 'Settings', testid: 'settings-nav', groups})`, mounted on `<div class="admin-settings-nav">`,
  a child of the admin sidebar panel (which keeps `.area-admin`; the `<nav class="admin-section-nav">`
  wrapper is gone). Groups in order: General (Appearance, Prompts, Encryption), Models (Providers),
  Defaults for agents (Built-in tools, Knowledge indexing), Developer (Design language, dev mode
  only). Item ids are the ROUTE sections (`knowledge-indexing`, not the area's `knowledge`), so the
  test ids are `settings-nav-{section}`; each `href` is `App.router.href({destination: 'settings',
  section})`. No click handler: `CATEGORY_ROUTE_SECTION`, `setCategory` and the
  `App.layout.renderSectionNav` call are deleted, and a click is a plain link the router guards.
- **Selection.** `_setCategory` calls `settingsNav.setSelected(routeSection(category))` (replacing
  `App.layout.updateActiveSection`; `categoryListEl` is gone), and `hydrateState` ends with
  `_syncNavSelection()` on every hydrate, item routes included (the section id, never the item id).
- **Column CSS.** `base.css`: `#app-sidebar[data-destination="settings"] { padding-top: 0 }` joins the
  agents/library rule. `admin.css`: `.area-admin .admin-settings-nav { flex: 1; min-height: 0;
  overflow-y: auto; padding: 14px 10px }`: the host is the column's scroller (the panel is
  `overflow: hidden`). Heading text and item text both sit 20px from the column edge (10px host +
  10px factory indent), items 28px, column 260px at 1440 and 1024 (measured in both engines).
- **Router** (`router.js`). `SECTIONS` replaces the `general` row with `appearance`, `prompts` and
  `encryption` (`dest: 'settings'`, `area: 'admin'`, `create: false`, subs equal to the route
  sections). `DESTINATIONS.settings.root` is `settings/appearance`, so the rail's first-use href is
  `#settings/appearance` (through `rootOf`). `resolve()` gains the explicit alias: `head ===
  'settings' && segs[1] === 'general'` becomes `settings/appearance`, `redirected = true`, every
  further segment dropped; `go()`, traversal and boot all go through it. The legacy special case
  is `#admin`, `#admin/system[/..]` or `#admin/general[/..]` -> `settings/appearance` directly
  (`GENERAL_ALIAS_TARGET`), never through the alias. `SECTION_LABELS`: `appearance`/`prompts`/
  `encryption` replace `general`, and `tools` is "Built-in tools". The header comment's route table
  is updated. `lastRoutes` is untouched: it is in memory and written from the resolved route, so
  `lastRoute('settings')` cannot be `settings/general` (tested).
- **`admin.js` `'general'` touchpoints.** A `GENERAL_SUBS: ['appearance', 'prompts', 'encryption']`
  property on the area descriptor (admin.js has no IIFE, so a module-level `var` would have been a
  global) drives `serializeState` (a General page serialises as itself), the fallback, the empty-sub
  reset (now Appearance), `validIds`, and the `currentCategory` default; the legacy `general` and
  `system` subs map to `appearance`. `renderContent` and `_refresh` dispatch through a
  `GENERAL_RENDERERS` map.
- **`system-page.js` split.** `renderAppearancePage`, `renderPromptsPage` and `renderEncryptionPage`
  replace `renderSystemPage` (removed). Each owns its page and wires only its own block (the theme
  radiogroup through `App.theme.renderToggle`, the base prompt fetch into its own `<pre>`, the
  rotate flow on its own button), so nothing dereferences another page's nodes. They are DOM-built
  (`App.ui.util.el`; test ids through `setAttribute` so the registry extractor sees them), which
  drops `system-page.js`'s `DYNAMIC_SINK_BASELINE` entry. Each block keeps its classes, copy and
  test ids (`base-prompt-content`, `rotate-key-btn`, `.admin-theme-toggle`, `#admin-theme-toggle-mount`).
  The former in-page "Appearance", "Base Prompt" and "Encryption" titles become each page's `h1`;
  the Appearance `h1` carries `id="admin-appearance-heading"`, so the radiogroup is still named
  "Appearance".
- **Page headers (section 4, AC4).** Labels: Appearance, Prompts, Encryption, **Providers** (was
  "LLM Providers"), **Built-in tools** (was "Built-in Tools"), **Knowledge indexing** (was
  "Knowledge"), **Design language** (was "Design Language"). The Providers primary action is
  "Add provider": the header is now DOM-built with `App.ui.button({label: 'Add provider', icon:
  'plus', testid: 'new-provider-btn'})` (this drops the `providers-grid.js` page-header sink from the
  baseline; the empty-canvas duplicate reads "Add provider" with the plus icon too). Geometry,
  scoped to Settings because `.page-header` is shared: `.area-admin .page-header { padding: 16px
  32px }`, `.area-admin .admin-form { padding: 0 32px 40px; max-width: 880px }`; the Design language
  sections take the 32px inset too.
- **Section-nav retired** (AC5). `areas/layout/section-nav.js` deleted (and with it `App.layout`),
  its `index.html` tag, the cache-busting count (72 -> 71, with a comment naming this leg), its CSS
  (`.section-nav`, `.section-nav-header`, `.section-nav-item`, `components.css`), its inventory row
  (the `navGroups` row now records the replacement), and the Design language surfaces section's
  `.section-nav` sample (its comment points to the `navGroups` demo). Comments describing live
  behaviour were rewritten: `dialog.js` (the confirm dialog's callers are the leave guard),
  `chat.js` (the roving pattern points at `App.ui.util.rovingFocus`), `provider-editor.js` and
  `admin.js`; `studio.css` needed nothing (leg 4a rewrote it). The `Makefile`'s `verify-serving`
  list still named `layout/section-nav.js`; `make restart` failed on its 404, so the entry is
  removed. The AC5 grep returns nothing: `grep -rnE "renderSectionNav|updateActiveSection|section-nav-item|class=\"section-nav|\.section-nav\b" the_one/interfaces/web/static/`
  exits 1.

**Tests.**
- New: `tests/browser/test_flow_admin_settings_nav.py` (settings lane through `test_flow_admin_*`;
  21 tests): AC1 nav groups, links, heading and mount; three groups without dev mode (the
  `/api/config` response patched to `dev_mode: false`); geometry at 1440x900 and 1024x768 in
  Chromium AND WebKit (`engine_browser` + `credentialed_context`): aside 260, `padding-top: 0`,
  host `14px 10px` and `overflow-y: auto`, items 28 ±1, heading text = item text = column + 20 ±1,
  the Developer link unclipped; `aria-current` across intents, item routes and Back/Forward.
  AC2/AC4 every link opens its page with one page header, one `h1`, no breadcrumb and no border;
  each General page renders one block with its own controls only (the radiogroup still named
  "Appearance"); the theme flip; "Add provider". AC3 the alias on a cold load (three suffix forms:
  one `replaceState` of the target, no push), in-app (`go` pushes Appearance itself; a typed hash
  is rewritten in place with `replaceState` only; Back returns), the legacy `#admin`,
  `#admin/system`, `#admin/general` at boot and typed (their history writes are only the target,
  never `settings/general`), the rail's first-use href and `lastRoute('settings')`. AC5 the Design
  language page has no section-nav sample. The leave guard: a dirty provider editor plus a nav link
  asks once (Stay keeps edit, route and selection; Continue lands on Appearance with no second
  dialog and a clean `_dirty`).
- `test_flow_keyboard.py`: the roving-tabindex test is rewritten (not deleted) as
  `test_settings_nav_links_are_in_tab_order` (a `<nav aria-label="Settings">`, seven links with no
  `tabindex`, Tab walks them in group order with a `:focus-visible` solid ring) and
  `test_settings_nav_enter_navigates_and_moves_aria_current`.
- `test_router_core.py`: `REDIRECT_ROWS` (`#admin`, `#admin/general[/x]`, `#admin/system[/x]`,
  `#settings` -> `settings/appearance`; these feed the JS/`_nav` parity corpus) plus a separate
  `GENERAL_ALIAS_ROWS` (`#settings/general`, `/x`, `/x/y`) through the same one-write boot test,
  kept out of the parity corpus; `ROUND_TRIP_SPECS` and the parity corpus gain the three pages;
  every neutral `#settings/general` boot route is `#settings/appearance`.
- Helpers: `_lists.py` gains `SETTINGS_PAGES` / `SETTINGS_PAGE_TITLES`, `settings_nav`,
  `settings_nav_link`, `settings_page_title`, `open_settings_page` and `expect_settings_selected`.
  `_nav.py`: the route table (`settings/appearance|prompts|encryption`), `canonical("settings")` is
  `settings/appearance`, `_from_legacy` folds `#admin`, `#admin/system` and `#admin/general` there;
  `canonical` deliberately does NOT fold `settings/general` (a page left on it fails
  `expect_route(..., "settings/appearance")`, so a missing redirect is caught), and `legacy_hash`
  rejects it. `LEGACY_URL_TESTS`: the two `test_flow_admin_navigation.py` entries renamed, plus
  `test_flow_admin_settings_nav.py::test_legacy_general_hashes_redirect_directly`.
  `test_nav_helper.py`: DD2 rows, canonical tests, a new `test_settings_general_is_not_folded`.

**Falsified** (each broken in turn, the tests failed, the code restored): the `settings/general`
alias in `resolve` (the three cold-load cases, the in-app test and the rail/`lastRoute` test
failed) and the settings `padding-top: 0` rule (the geometry test failed in both engines at both
sizes): 9 failures, restored and re-confirmed.

**Migrated test files** (Settings halves; leg 5b's tiles, Back and grids stay):

| File | Lane | Change | Allow-list |
|---|---|---|---|
| `test_flow_admin_navigation.py` | settings | rewritten on `settings_nav*`; legacy redirect tests renamed `…_to_appearance`; keyboard test is Enter on a focused link | **removed** |
| `test_flow_admin_knowledge_settings.py` | settings | page title "Knowledge indexing"; nav link and selection; "Appearance" replaces "General" as the leave target | **removed** |
| `test_flow_admin_tools_grid.py` | settings | "Built-in tools"; nav-label test renamed `…settings_nav_label…` (text and `href`) | **removed** |
| `test_flow_admin_tools_editor.py` | settings | "Built-in tools"; dirty-gate test renamed `test_editor_settings_nav_dirty_gate` (Appearance link) | stays (`back-tool-btn`, 5b) |
| `test_flow_provider_dirty_confirm.py` | settings | nav-link tests renamed `test_settings_nav_link_*`, target Appearance; "Providers" | stays (`back-provider-btn`, 5b) |
| `test_flow_provider_grid.py` | settings | "Providers", "Add provider" | stays (tiles, Back, 5b) |
| `test_flow_provider_setup.py` | settings | `open_settings_page(page, "providers")` | stays (tile, Back, 5b) |
| `test_flow_provider_editor.py`, `test_flow_admin_openrouter.py`, `test_flow_provider_plan_signin.py` | settings | page title "Providers" | openrouter stays (5b); others not listed |
| `test_flow_hash_routing.py` | shared | nav links, `expect_settings_selected`; history test renamed `test_hash_routing_settings_nav_pushes_history` (Back walks Providers -> Appearance -> Chats) | **removed** |
| `test_flow_keyboard.py` | shared | see above | **removed** |
| `test_router_announce.py` | shared | "Settings — Appearance"; the rail walk also announces "Settings — Built-in tools"; cold-noun test starts from Appearance | **removed** |
| `test_shell_rail.py` | shared | widths at `settings/appearance`; fit test on the nav's links (renamed `test_settings_nav_labels_and_chat_rows_do_not_clip_at_1024`); rail hrefs; landmark test per-role (see Deviations) | **removed** |
| `test_visual_snapshots.py` | pixel | nav link | **removed** |
| `test_router_guard.py` | shared | Providers/tools nav links for the reclick-closes tests; docstrings | stays (`back-tool-btn`, 5b) |
| `test_router_core.py` | shared | see above | not listed |
| `test_nav_guard.py` | shared | knowledge-settings discard case lists from Appearance | not listed |
| `test_flow_admin_rotate_flash.py` | settings | `settings/encryption` | not listed |
| `test_theme_cross_tab_sync.py` | shared | both tabs at `settings/appearance` through `_nav.goto` (was a raw `#admin/general` the route guard missed: the `/#` prefix hides it from `_ROUTE_RE`) | not listed |
| `test_flow_cross_area_dirty_gate.py` | shared | readiness on `settings_nav` | not listed |

**Allow-list after pruning** (15 -> 7): `test_flow_admin_openrouter.py`,
`test_flow_admin_tools_editor.py`, `test_flow_provider_dirty_confirm.py`,
`test_flow_provider_grid.py`, `test_flow_provider_setup.py`, `test_router_guard.py`,
`test_router_items.py`. No `section-nav-item` hit remains in any browser test; every remaining hit
is leg 5b's (`entity-tile`, `back-provider-btn`, `back-tool-btn`).

**Gates.**
- `make lint` clean; `ruff format --check` clean (re-checked on the final tree).
- `make test-unit`: 5031 passed, 10 skipped, 1398 deselected (640.5s). Five more than leg 4b: the
  `_nav` DD2 rows (three General pages replace `settings/general`: +2 rows in two parametrized
  tests) and `test_settings_general_is_not_folded`.
- `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_store_static`,
  `test_index_asset_cache_busting`, `test_ui_control_inventory`, `test_nav_helper`,
  `test_ui_library_source`, on the final tree: 359 passed (2.4s).
- Every `test_ui_*` in both engines (`THE_ONE_REQUIRE_WEBKIT=1`): 432 passed, 3 skipped (WebKit has
  no forced-colours emulation) (111.9s). Unchanged from leg 4b: no library change.
- `test_flow_admin_settings_nav.py` alone (both engines for the geometry test): 20 passed on its
  first run (33.5s); 21 with the AC5 Design language test added later.
- Lanes, one at a time with `THE_ONE_TEST_NETNS=1`:

  | Lane | Passed | Skipped | Duration |
  |---|---|---|---|
  | chats | 42 | 0 | 97.5s |
  | agents | 124 | 2 | 302.3s |
  | library | 138 | 1 | 460.1s |
  | settings (final tree) | 146 | 0 | 270.6s |
  | shared (rerun) | 864 | 3 | 753.5s |

  Settings is 21 more than leg 4b (the new file); shared is 6 more (the keyboard test is two tests
  now, and five new `test_router_core.py` redirect rows: `#admin/general/x`, `#admin/system/x` and
  the three `GENERAL_ALIAS_ROWS`). Chats, agents and library are unchanged in count. An earlier
  settings-lane run on the pre-revert tree (below) was 145 passed (263.2s), before the AC5 test.
- **First runs: two failures, both fixed.**
  - The touched-files batch (13 shared files): 1 failed, 207 passed (456.8s):
    `test_shell_rail.py::test_landmarks_and_aside_labels`, the "Settings" landmark name shared by
    the aside and the new nav (see Deviations; the test is narrowed to per-role uniqueness). The
    file then passed alone (18 passed, 45.1s).
  - Shared lane, first run: 2 failed, 862 passed, 3 skipped (811.3s):
    `test_store.py::test_request_counts_per_activation` and `::test_cold_boot_providers_one_read`
    wait for the provider grid's listbox by its name, "LLM providers", which this leg had renamed
    "Providers". Classified as this leg overreaching onto leg 5b's grid: the label is restored
    (the grid is unchanged until 5b). `test_store.py` alone: 16 passed (37.8s); the shared lane
    and the settings lane were then rerun in full (the table). Chats, agents and library ran before
    the label revert; no test in them names the grid's listbox (grepped).

**WebKitGTK probe** (WebKitGTK 2.52.6, dev instance 8485 / `/tmp/the-one-wbnav-scratch`, verified
through `/proc/<pid>/environ`; `make restart`ed for the `index.html` change; nothing seeded):

| URL | Root selector | Result |
|---|---|---|
| `#settings/appearance` | `#app-sidebar` (dark, light; the leg's invocation) | ok, 8 controls, 0 failures |
| `#settings/appearance` | `#main-content` (dark, light; the leg's invocation) | 9 controls, 1 failure: `chat-image-input` (squawk 0110, pre-existing, the hidden chat panel) |
| `#settings/appearance` | `#main-content .content-panel.area-admin:has(#admin-theme-toggle-mount [role="radio"])` (dark, light) | ok, 3 controls (the theme radios), 0 failures |
| `#settings/prompts` | `… .content-panel.area-admin:has([data-testid="base-prompt-content"])` (dark, light) | ok, 0 controls, 0 failures |
| `#settings/encryption` | `… :has([data-testid="rotate-key-btn"])` (dark, light) | ok, 1 control, 0 failures |
| `#settings/providers` | `… :has([data-testid="new-provider-btn"])` (dark, light) | ok, 2 controls ("Add provider" and the empty-canvas duplicate), 0 failures |

This time the bare `#main-content` scan ran after the page mounted (9 = the 6 chat controls plus the
3 radios), so its only failure is squawk 0110's hidden chat input; the content-scoped roots, as in
legs 3–4b, scan the Settings page alone.

**Docs.** `agents.md`: a new "Settings nav and pages (M25 F3 L5a)" section (the nav, selection, column
CSS, the General split, page headers, section-nav retired, tests); "Hash routing" (scheme, alias
layer subs, the `settings/general` alias and `lastRoutes`, the legacy redirects, paths); "App shell"
(Settings `padding-top: 0`, the landmark names); the `_nav` and `_lists` helper paragraphs; the
nav-groups factory row; the Library host note; the inset-ring list. `CLAUDE.md`: the destination
router line's Settings sections and redirects, and a "Settings nav and pages" paragraph.
`docs/ui-testid-registry.md`: `settings-nav` and the `settings-nav-` family; `base-prompt-content`,
`rotate-key-btn` and `new-provider-btn` notes. `docs/ui-control-inventory.md`: the section-nav row
removed, the `navGroups` row updated. `README.md`: Settings -> Providers / Encryption, Agents.
Behavior specs (text only; leg 6 runs them): `workbench-navigation.md` (step 5's grouped nav and
routes, steps 6, 9, 10, the theme variant, the banner note) and `shell-navigation-smoke.md` (the
objective, step 6's nav and `#settings/appearance`, steps 8 and 9).

**Deviations and decisions.**
- **Landmark names: per-role uniqueness.** AC1/DD6 bind `<nav aria-label="Settings">`, inside the
  aside the router labels "Settings". Flight 2's `test_landmarks_and_aside_labels` asserted no two
  landmarks share a name at all (why the section nav was "Settings sections") and failed. The ARIA
  rule is unique names among landmarks of the same role; complementary "Settings" and navigation
  "Settings" are announced apart. The test now asserts unique (role, name) pairs and pins both
  Settings landmarks. **For the flight's Accessibility Reviewer**: the alternative is relabelling
  the aside on Settings, which would break the aside-label-is-the-destination-name contract.
- **Page header geometry, as section 4 states it.** The leg's sentence applies "`padding: 0 32px`
  and `max-width: 880px`" to both selectors; section 4 gives the header `16px 32px` (full width, the
  action pushed right) and the content `0 32px` with an 880px maximum. Implemented as section 4:
  `.area-admin .page-header { padding: 16px 32px }`, `.area-admin .admin-form { padding: 0 32px
  40px; max-width: 880px }` (the 40px bottom keeps the scroll room `.admin-form` had). The Design
  language sections move from a 20px to a 32px inset to line up with their header. The provider and
  tool grids keep their 20px grid padding (12px off the header) until leg 5b replaces them.
- **"Add provider" uses the plus icon** (section 8.2) instead of `square-pen`, on the header action
  and the empty-canvas duplicate. The grid listbox keeps its `aria-label` "LLM providers": the
  grid is leg 5b's (see the shared-lane first run below).
- **Legacy suffixes.** `#admin/system/x` and `#admin/general/x` also go straight to Appearance (the
  leg named the bare forms); before, `#admin/general/x` reached `settings/general/x` and
  `#admin/system/x` was unknown.
- **The Prompts page has no in-page "Base prompt" label**: the leg drops the titles that repeat the
  page title, so the block is the description and the `<pre>` under the "Prompts" `h1`.
- **`_syncNavSelection` on every hydrate** is belt-and-braces: `_setCategory` already selects on a
  category change; the hydrate call keeps the selection right when a hydrate returns early.
- **Out of scope, left for leg 6 (DD12)**: other behavior specs still name the retired Settings
  surfaces: `system-provider-config.md` ("LLM Providers", 8 hits), `anthropic-plan-signin.md`
  ("LLM Providers" in "Settings sections"), `anthropic-plan-chat-parity.md`,
  `save-preserves-config.md`, `extended-thinking-tool-turn.md`, `studio-agent-crud.md` ("LLM
  Providers"), `chat-roundtrip.md` ("Settings › General") and `agent-governance-and-search.md`
  ("Built-in Tools" in "Settings sections"). `tests/behavior/list-and-detail.md` (untracked, not
  this leg's) already uses the new routes.
- Tests that cite `system-page.js` as history (`test_theme_toggle_cleanup.py`,
  `test_confirm_contract.py`) are unchanged; their claims still hold. One stale line citation in
  `test_flow_admin_rotate_flash.py` was replaced by the page's name.
- The local pixel baselines for Settings will differ (the nav, the headers). Regenerate with
  `--snapshot-update`.
- No squawks logged: the only probe failure is squawk 0110 (pre-existing). The scratch instance
  was not seeded for this leg (the probe needs no data); it holds no agents, providers, knowledge
  bases, MCP sources or connectors.

### Leg 5b: settings-items (landed, 2026-10-02)

**What landed.** Settings item pages keep their list visible (DD7). The Providers grid is the
reference spec 8.2 table, and a provider (or the `~new` form) opens in an item section below
it. A built-in tool opens below the tool list, and its name is the item link. Both editors carry
the "Settings / …" breadcrumb, have no Back, and show the unsaved caption. The retired-selector
allow-list is empty.

- **Page scaffold** (design review issue 1). `admin.js` `mountScaffold(category)` builds, once
  per category render of Providers or Built-in tools, the section 4 page header (plus "Add
  provider"), then `.settings-list`, then `.settings-item`. `scaffoldFor(category)` returns it
  only while that page shows; `renderContent` resets it for every other page.
  - List renders target `.settings-list` only (`renderProvidersTableNow`,
    `renderToolsListNow`); the editors mount in `.settings-item` (`mountProviderItem`,
    `mountToolItem`), so the editors' own `innerHTML` and the tools Cancel re-mount stay inside
    it.
  - The two guards that suppressed list refresh with an editor open are gone
    (`populateProviderGrid`'s `providerFormMode` return, `populateToolGrid`'s `toolFormMode`
    return).
  - `_closeOpenItem` empties the item section (`clearItemSection`). `_setCategory` has a scaffold
    branch: a root hydrate on the same item page (breadcrumb, the nav's current link,
    Back/Forward) closes the item IN PLACE and leaves the list alone. `_discardEditor` empties the
    section through `_closeOpenItem`; `editorDomStale` is set only when no item page shows.
    `editorGen` and the discard path are kept.
  - The failure lines are retargeted to `.settings-list` and shown only for a list that never
    loaded (a failed refresh keeps the last good rows).
  - The editors' flashes are moved from the item section to the page before it is emptied or
    re-mounted (`rescueFlashes`), so "Provider created" and "Provider deleted" now stay on screen.
- **The Providers table** (`areas/admin/providers-table.js`, which replaces `providers-grid.js`;
  DOM-built, no HTML-string sink). The intro, then `<table class="providers-table"
  aria-label="Providers">` with Name · Type · Used by (no Status column, no health banner: D1/D2).
  - Rows sort A–Z. Name is a weight-600 `<a href="#settings/providers/{id}">` with the kept
    `provider-card` testid and `data-id` (ellipsized, with a `title`); Type is `App.ui.badge`
    with the slug; Used by is "{n} agents" / "1 agent" from `App.usage.providerAgents`.
  - The open row: `aria-current="page"` on its link and the selected wash on the row, set in
    place (`setProvidersSelection`).
  - Idempotent rendering: an unchanged row model keeps the DOM; a changed one rebuilds only
    `tbody` and gives focus back to the same provider's link.
  - Zero providers: a pane-size `App.ui.emptyState` "No providers yet." (h2) with "Add provider"
    (`providers-empty`, action `providers-empty-add`).
  - Data (design review issue 5): the table mount calls `App.store.get('agents', {force: true})`
    beside the providers `get`; `init` subscribes to `providers` and `agents`, and both
    re-render the table body only. "Used by" reads "—" while agents never loaded. A list another
    area loaded seeds the table at mount. Mutations re-read with a forced `get` that bypasses the
    one-at-a-time join (`reloadProviders`), and every read prefers the store's current value
    (`storeValue`).
- **A provider below the table.** Breadcrumb "Settings / Providers" (inserted after `innerHTML`,
  "Providers" is `editor-breadcrumb-link` to `#settings/providers`); Back deleted with its
  `onBack` and handler; the stable `editor-unsaved` span opens `.form-actions` and `checkDirty`
  sets it; `h1.editor-title` has `tabindex="-1"`.
  - Cancel on `~new`: `_discardEditor`, `go(root, {replace, bypassGuard})`, focus "Add
    provider". On an item: revert in place (unchanged).
  - Save-create (design review issue 6): mode and editing provider set, and the new provider
    merged into the local list, before the reload, so the new row renders selected; `sync` with
    the name hint announces it; only the item section re-mounts in edit mode.
  - Delete: the row index is read at the top of `onDeleteSuccess`; discard, replace to the root,
    drop the row locally, focus the row now at that index, else the previous, else "Add
    provider".
- **Built-in tools.** The tabs and tile cards stay. In `tileHtml` the tool name is `<a
  class="entity-tile-name tool-tile-link" href>` built with
  `escapeAttr(App.router.href(…))`; the tile keeps `tool-card`, loses `tabindex="0"` and both
  tile handlers (with the `.tool-enable-switch` bail-out), and gets `cursor: default` and no
  hover wash. The toggle's `change` only toggles enablement.
  - `renderToolsGrid(listEl, configs, {onToggle, inFlight, selectedName})` renders the list only
    (no page header). The open tool: the selected wash (`.entity-tile.active`) and
    `aria-current` on its link, in place via `setToolsSelection`.
  - Category on open (design review issue 4): `selectedName` reveals the tool's category once
    (`revealedName`); a deep link opens on its tab, an unknown name keeps the current tab.
  - A list re-render gives focus back to the same toggle, tool link or tab (a toggle disabled by
    its in-flight PUT gets it back on the next render).
  - `selectTool` mounts the item section only (no list rebuild on `_refresh`) and drops a
    response voided by a close or a newer open (`editorGen`); a 404 empties the item section.
  - Breadcrumb "Settings / Built-in tools" (`#settings/tools`); Back deleted with its `onBack` and
    handler; the unsaved caption (`reportDirty`), and Cancel's re-mount keeps the SAME span node.
  - A toggle with a tool open (design review issue 2): `handleToolToggle` re-renders the list
    only. When the toggled tool is the open one, the PUT's success calls the editor's
    `setEnabled` (from the new `onMount(api)` callback), which updates the Enabled control and its
    saved snapshot IN PLACE. No "stale until reopened" variation was needed.
- **Opening, closing and focus.** `hydrateState` marks every item route as an intent
  (`_setOpenIntent`). The mounted item then scrolls its header into view (`block: 'nearest'`)
  and focuses its title, one task later, so it lands after `nav.js`'s Continue focus
  (`revealItem`). Store notifications, `_refresh` and save-create never reveal. One delegated
  click listener on the admin content routes the breadcrumb link (an intent `go`, then focus on
  the closed item's row link, or "Add provider" after a `~new` form) and treats a click on the
  open item's own list link as "reveal", with no navigation.
- **CSS** (`admin.css`): `.settings-list` (`0 32px`, 880px, full height only while the item is
  empty), `.settings-item` (`margin: 24px 32px 0`, 816px, a top hairline; header and sections on
  the list's inset), the table (11px `--fg-muted` 500 heads, `padding: 12px` cells with
  hairlines, `table-layout: fixed`, the selected wash), the tool link and the tile.
- **Retired:** `providers-grid.js` (its `index.html` tag, swapped for `providers-table.js`, so
  the cache-busting count stays 71; its `DYNAMIC_SINK_BASELINE` entry; the `Makefile`
  `verify-serving` entry, swapped too), the two tools-grid page-header sink entries,
  `back-provider-btn`, `back-tool-btn`, `selectProvider`, `openTool`, `populateProviderGrid`.

**Tests.** New: `tests/browser/test_flow_settings_items.py` (21 tests, settings lane through the
new `test_flow_settings_*` glob in `scripts/run-tests.sh`):

| AC | Tests |
|---|---|
| AC1 | `test_providers_table_anatomy_and_used_by_counts` (intro, heads, A–Z rows, 1 / 2 / 0 agents, weight 600, badge, no Status, no banner); `test_used_by_reads_a_dash_until_agents_load`; `test_long_provider_name_ellipsizes` (1024px) |
| AC2 | `test_provider_opens_below_the_table_with_focus_and_visibility` (6 providers, 1440x900, the last row: below the table, both in the viewport, focus on the `h1`, breadcrumb, no Back); `test_dirty_provider_and_another_row_asks_once` (Stay keeps, Continue opens, the title focused last); `test_clicking_the_open_provider_row_does_not_ask_or_remount`; `test_breadcrumb_closes_the_provider_and_focuses_its_row` (pushed; dirty asks once, Stay focuses the link) |
| AC3 | `test_add_provider_opens_the_form_below_and_save_create_keeps_it` (focus, URL `/{id}`, "Settings — Providers — Made provider", selected row, no new history entry, clean, next row opens without a prompt); `test_cancel_on_create_returns_to_the_root_focusing_add_provider` (replaced); `test_delete_focuses_the_nearest_row[middle-focuses-next / last-focuses-previous]` |
| AC4 | `test_tool_opens_below_the_list_scrolled_and_focused`; `test_tool_toggle_never_navigates`; `test_toggling_another_tool_keeps_the_open_editor_and_its_edit` (same header node, edit and caption kept, toggle keeps focus); `test_toggling_the_open_tool_updates_its_enabled_control_in_place`; `test_deep_link_to_a_non_default_category` (Connectors; a later toggle keeps the user's tab); `test_breadcrumb_closes_the_tool_and_focuses_its_name_link` |
| AC5 | `test_unsaved_caption_on_the_provider_editor`, `test_unsaved_caption_on_the_tool_editor_survives_cancel` (shows, clears on Cancel and Save, the same node) |
| Focus | `test_store_notification_and_refresh_never_move_focus` (store loads and `_refresh` with focus in the form; a renamed provider rebuilds the body and the focused row link keeps focus); `test_tab_order_runs_through_the_name_links_then_into_the_editor` |

Unit side: `test_design_tokens_a11y.py` +3 (`test_providers_table_pairs_pass_body_aa` in two
themes, `test_providers_table_rules_consume_the_gated_pairs`); `test_nav_helper.py` (the
allow-list is `frozenset()`); `test_ui_guards.py` (baseline pruned); the cache-busting comment.

**Falsified** (each broken in turn, the tests failed, the code restored): no title focus on
reveal, a tool toggle re-mounting the open editor, no focus after delete, and the tools Cancel
re-creating the caption node: 12 of the 21 new tests failed together.

**Migrated test files** (every `back-provider-btn` / `back-tool-btn`, provider-tile and
tool-tile usage removed; closes go through `_lists.close_item`):

| File | Lane | Change | Allow-list |
|---|---|---|---|
| `test_flow_provider_grid.py` | settings | on the table: the link, `href`, `data-id`, badge and "0 agents"; empty state `providers-empty` and its `providers-empty-add`; name opens; refresh keeps the selection; the breadcrumb closes a clean create form; an unknown id lands on the empty state | **removed** |
| `test_flow_provider_dirty_confirm.py` | settings | Back → the breadcrumb; four tests renamed `test_breadcrumb_*`; closes assert the editor gone and the table kept | **removed** |
| `test_flow_provider_setup.py` | settings | the new row in the table (selected, badge) before a breadcrumb close | **removed** |
| `test_flow_admin_openrouter.py` | settings | breadcrumb close; table row and badge; reopen via `open_item` | **removed** |
| `test_flow_admin_tools_editor.py` | settings | `test_editor_back_button_dirty_gate` → `test_editor_breadcrumb_dirty_gate` | **removed** |
| `test_router_guard.py` | shared | tool reclick markers `save-tool-btn`; selection cleared; new `test_clean_breadcrumb_closes_provider_and_tool_editors` | **removed** |
| `test_router_items.py` | shared | the `.entity-tile-grid` flash observer replaced by a table watch (`__tableEmptied`, row-node identity); tool item via `open_item`; `test_provider_back_clean_closes_editor` → `test_provider_breadcrumb_clean_closes_editor` (+ row focus); the dirty provider/tool Back tests → `…_breadcrumb_…`; the agent no-flash test keeps its list observer only | **removed** |
| `test_flow_admin_tools_grid.py` | settings | name-link clicks (`href`); new `test_admin_tools_tile_body_is_not_a_click_target`; the keyboard test is link Enter plus Tab to the toggle, Space flips without navigating, focus restored; the deep link asserts the tab and the selection | not listed |
| `test_flow_provider_editor.py` | settings | the action cluster has no Back and opens with the caption; create Cancel focuses "Add provider"; `test_back_button_always_enabled` → `test_header_has_breadcrumb_and_no_back`; delete lands on the empty state with focus on "Add provider" | not listed |
| `test_flow_provider_plan_signin.py` | settings | `.back-btn` → the breadcrumb | not listed |
| `test_store.py` | shared | the two "LLM providers" listbox waits → `_lists.providers_table` | not listed |
| `test_lists_helper.py` | shared | the Settings smoke covers the new helpers | not listed |
| `test_visual_snapshots.py` | pixel | `providers-empty` | not listed |

Helpers (`_lists.py`): `_List` gains `link` (a tool tile's name link) and `self_named` (the
provider row IS its name link); `list_row` handles both; new `item_link`, `expect_none_selected`,
`providers_table`, `settings_item`, `tool_toggle`, `open_tool` and `TOOL_TABS`; `open_item`
clicks the item link and `expect_selected` checks `aria-current` on it.

**Allow-list after pruning** (7 → 0): `RETIRED_SELECTOR_ALLOWLIST: frozenset[str] = frozenset()`.
No retired selector remains in any browser test or helper.

**AC6 grep.** `grep -rn "back-provider-btn\|back-tool-btn" the_one/ tests/ scripts/` returns only
the two `RETIRED_SELECTORS` entries in `tests/test_nav_helper.py` (and the guard's self-test
docstring), as for the Library ids in leg 4b. `the_one/` is clean (`agents.md` points to the
registry's retired table instead of naming them).

**Gates.**
- `make lint` clean; `ruff format --check` clean.
- `make test-unit`: 5034 passed, 10 skipped, 1421 deselected (647.0s). Three more than leg 5a: the
  providers-table contrast gates (two themes) and their rule-consumption test.
- `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`,
  `test_index_asset_cache_busting`, `test_store_static`, `test_ui_control_inventory`,
  `test_ui_library_source`, `test_nav_helper`, on the final tree: 359 passed (2.4s) before the
  three new a11y tests; `test_design_tokens_a11y` + `test_ui_guards` + `test_token_definitions`
  after them: 235 passed (0.8s).
- Every `test_ui_*` in both engines (`THE_ONE_REQUIRE_WEBKIT=1`): 432 passed, 3 skipped (WebKit has
  no forced-colours emulation) (111.4s). Unchanged from leg 5a: no library change.
- The migrated settings-lane files together, before the lanes: 103 passed, 1 failed (193.3s); the
  failure was this leg's own test asserting the first tool tile visible while the Web tab was
  revealed (fixed to the `web_search` tile), then the router, store and helper files: 70 passed
  (187.9s). `test_flow_settings_items.py` alone: 21 passed (47.4s).
- Lanes, one at a time with `THE_ONE_TEST_NETNS=1`:

  | Lane | Passed | Skipped | Duration |
  |---|---|---|---|
  | settings | 168 | 0 | 313.1s |
  | shared | 865 | 3 | 758.4s |
  | agents | 124 | 2 | 302.6s |
  | library (rerun) | 138 | 1 | 460.2s |
  | chats | 42 | 0 | 95.7s |

  Settings is 22 more than leg 5a (the 21 new tests and
  `test_admin_tools_tile_body_is_not_a_click_target`); shared is 1 more
  (`test_clean_breadcrumb_closes_provider_and_tool_editors`). Agents, library and chats are
  unchanged in count.
- **Library lane, first run: 1 failed, 137 passed, 1 skipped (466.4s).**
  `test_flow_studio_knowledge_inventory.py::test_detail_view_indexing_poll_reindex_and_search`:
  the "fox" search returned hits without `note.txt`. It passed alone (8.4s) and in the full lane
  rerun (the table). Classified as a pre-existing, load-sensitive test race outside this leg (no
  Library or knowledge-base code changed): the `indexed: 3` wait after "Re-index all" can pass on
  the text left by the previous step, before the requeue lands. **Squawk 0115 logged.**

**WebKitGTK probe** (WebKitGTK 2.52.6, dev instance 8485 / `/tmp/the-one-wbnav-scratch`, verified
through `/proc/<pid>/environ`; `make restart`ed for the `index.html` change; three mock providers
and two agents seeded through the API for the run):

| URL | Root selector | Result |
|---|---|---|
| `#settings/providers/{id}` | `#main-content` (the leg's invocation; dark) | 28 controls, 4 failures: `chat-image-input` (squawk 0110, pre-existing, the hidden chat panel) and 3 provider-editor `field-info-icon` buttons named only by `title` (pre-existing: **squawk 0114 logged**) |
| `#settings/providers/{id}` | `… .content-panel.area-admin:has(.settings-item [data-testid="save-provider-btn"])` (dark, light) | 22 controls, the same 3 info icons (squawk 0114) |
| `#settings/providers/{id}` | the same root `:is(.page-header, .settings-list, .settings-item .editor-header)` (dark, light) | ok, 8 controls (Add provider, three name links, the breadcrumb link, Cancel, Save, Test), 0 failures |
| `#settings/providers/~new` | the same scoped root (dark) | ok, 7 controls, 0 failures |
| `#settings/providers` | `… :has(table.providers-table)` (dark, light) | ok, 4 controls, 0 failures |
| `#settings/tools/web_search` | `… :has(.settings-item [data-testid="save-tool-btn"])` (dark) | 68 controls, 7 tool-editor info icons (squawk 0114) |
| `#settings/tools/web_search` | the same root `:is(.page-header, .settings-list, .settings-item .editor-header)` (dark, light) | ok, 49 controls (4 tabs, 21 name links, 21 toggles, the breadcrumb link, Cancel, Save), 0 failures |

As in legs 3–5a, the bare `#main-content` scan also reaches the hidden chat panel. Scoped to the
page header, the list and the item header (this leg's surfaces), every probe is clean. The
scratch instance was emptied afterwards (agents, providers, knowledge bases, MCP sources and
connectors all 0; the tool a probe toggled off was re-enabled).

**Docs.** `agents.md`: a new "Settings item pages (M25 F3 L5b)" section (the scaffold, the table,
its data, a provider below the table, Built-in tools, a toggle with a tool open, opening/closing
and focus, tests); the 5a section's forward references; the `_lists.py` helpers and the empty
allow-list. `CLAUDE.md`: a "Settings item pages" paragraph, the settings-lane glob and the empty
allow-list. `docs/ui-testid-registry.md`: new `providers-empty`, `providers-empty-add`;
`provider-card`, `tool-card`, `tool-toggle`, `editor-breadcrumb-link`, `editor-unsaved` reworded;
`back-provider-btn` and `back-tool-btn` moved to "Retired testids". `docs/ui-control-inventory.md`:
the badge, empty-state and entity-tile rows, and a new data-table row. No behavior spec was edited
(leg 6).

**Deviations and decisions.**
- **Two `h1`s on a Settings item page.** The leg names the editor's `h1` as the focus target, so
  the page header's `h1` ("Providers") and the editor's `h1` (the item) coexist. DD2's "one `h1`
  per detail pane" was written for the Agents and Library item headers. **For the flight's
  Accessibility Reviewer**: the alternative is demoting the item title to `h2` on Settings.
- **A click on the open item's own list link reveals it, with no navigation** (and "Add provider"
  with the create form already open). With the list now beside the item, a same-route `go()`
  would ask about a dirty editor and re-mount a clean one for nothing.
- **Focus after save-create** moves to the new title when focus was inside the form the re-mount
  replaced (the Create button is destroyed); it is not an intent, so nothing scrolls.
- **Flashes kept on screen** (`rescueFlashes`): "Provider created" and "Provider deleted" used
  to be wiped with their container.
- **Tools editor Cancel after a Save** now re-mounts from the saved values (`originalToolDetail`
  is updated on Save and by `setEnabled`). Before, Cancel after a Save reverted the form to the
  pre-save values while the server held the saved ones (a pre-existing bug, fixed because
  `setEnabled` has to keep the same detail current).
- **"Used by" after a failed agents refresh** keeps the last good counts; "—" is for a list that
  never loaded (the leg 4a rule).
- **Rows sort A–Z** (the leg is silent; the Agents and Library lists sort A–Z).
- **`providers-empty-add`**, a testid for the empty state's action, beyond the leg's
  `providers-empty`.
- **Beyond the leg:** `selectTool` drops responses voided by `editorGen` (the category check
  alone let a slow detail for tool A land after tool B opened); toggle focus survives the in-flight
  re-render; `_refresh` on Providers re-reads providers and agents with an editor open.
- **Item inset.** The item section sits on the list's 32px inset with a hairline above
  (`max-width: 816px`), so the header's actions line up with the table's right edge.
- `test_flow_admin_tools_grid.py::test_admin_tools_tile_body_is_not_a_click_target` builds the
  description class from parts, as leg 4a did, so the guard that fences retired selectors does
  not flag a test that drives the tile body on purpose.
- `README.md`'s screenshot alt text still describes the old grid image; the image was not
  regenerated.
- **Squawks logged:** 0114 (the editors' info-icon buttons are named only by `title`; found by
  this leg's probe at the provider and tool items, pre-existing) and 0115 (the knowledge-base
  detail test can search while "Re-index all" is still running; the library lane's one
  first-run failure, pre-existing).
- The local pixel baselines for Settings will differ (the table, the item below). Regenerate
  with `--snapshot-update`.

### Leg 6: behavior-specs-and-close (landed, 2026-10-02)

**What landed.** The code-side close of Flight 3: the retired-selector guard is unconditional,
the behavior specs that are NOT run at close name the current surfaces, the docs agree with the
tree, squawk 0101 is closed, and every flight-close gate is green on its first run. No product
code changed (no file under `the_one/` other than `agents.md`).

**Guard** (`tests/test_nav_helper.py`, AC1). Nothing outside the file used the allow-list, so the
mechanism is **removed**, not pinned:
- `RETIRED_SELECTOR_ALLOWLIST` is gone. `check_retired_selectors(sources)` takes one
  basename -> source map and reports every hit; test modules and helper modules are walked
  alike (`tests/browser/*.py`), with no per-file exemption. The history comment records the
  29 -> 0 migration.
- `RETIRED_SELECTORS` keeps all 11 Flight 3 ids (`entity-tile`, `section-nav-item`, the six
  `back-*-btn`, the three `new-*-btn`) and gains leg 3's two retired tile counts,
  `agent-tile-tool-count` and `agent-tile-mcp-tool-count` (in the registry's retired table but
  never fenced). 13 ids.
- New pin `test_retired_selectors_cover_the_registry_retired_table`: every id in
  `docs/ui-testid-registry.md`'s "Retired testids" table is in `RETIRED_SELECTORS`, the 11
  Flight 3 ids are a subset, the tuple has no duplicates, and no retired id is registered in a
  live table again (`parse_registry` literal, manual and parametric-prefix rows).
- The self-test drops the allow-list cases and asserts that a hit fails under any file name
  (`test_old.py`, `test_router_core.py`, `_lists.py`, `conftest.py`); the walk asserts it saw the
  four helper modules and more than 50 test files (it sees 89).
- **Falsified** (each broken, failed, restored): a temporary `tests/browser/test_zz_falsify_tmp.py`
  naming `back-tool-btn` failed `test_no_retired_selectors_in_browser_tests`; dropping
  `agent-tile-mcp-tool-count` from the tuple failed the registry pin; a temporary live registry
  row for `back-agent-btn` failed the revival check. `test_nav_helper.py`: 70 passed.
- `tests/browser/_lists.py`'s docstring no longer mentions a shrinking allow-list.

**Behavior specs** (AC2). Re-grepped after leg 5b with a wider pattern than the Flight Director's
(also "Studio", "Admin", "card", "grid", lowercase "back"), then judged hit by hit. The six
run-at-close specs (`list-and-detail`, `workbench-navigation`, `shell-navigation-smoke`,
`studio-agent-crud`, `system-provider-config`, `kb-studio-round-trip`) were **not edited by this
leg**; none carries the `**Updated**` line. No `Last Run` line and no `runs/` log was touched.
- **Updated** (each with `**Updated**: 2026-10-02 (M25 F3 surface rename; not re-run)` as the
  last header line):

  | Spec | Change |
  |---|---|
  | `save-preserves-config` | "Settings › LLM Providers" -> "Settings › Providers" (2); step 4 "Re-select the … card" -> click the row's name link in the Providers table (opens below it); locators "provider grid tile … (providers-grid.js)" -> "Providers table row name link … (providers-table.js)"; cache note "the grid" -> "the table" |
  | `stub-connector-round-trip` | step 1 `new-connector-btn` -> the Library list's Add menu (`library-add-btn` -> "Connector", `library-add-connector`, `#library/connectors/~new`); step 4 "select the `bt-stub` card" -> its row in the Connectors group, "Studio form reload" -> "the connector editor's reload"; observables "editor form and grid" -> "… and the Library list's Connectors group" |
  | `anthropic-plan-signin` | Intent "Settings › LLM Providers" -> "Settings › Providers"; step 1 "LLM Providers" in "Settings sections" -> "Providers" in the Settings nav, then "Add provider" (form below the table) |
  | `agent-governance-and-search` | step 1 "Built-in Tools" in "Settings sections" -> "Built-in tools" in the Settings nav; `web_search` opens from its name link on the Web tab, below the list (`#settings/tools/web_search`) |
  | `extended-thinking-tool-turn` | plan variant "Settings › LLM Providers" -> "Settings › Providers" |
  | `anthropic-plan-chat-parity` | precondition "Settings › LLM Providers" -> "Settings › Providers" |
  | `chat-roundtrip` | dark variant "Settings › General's theme control" -> "Settings › Appearance's" |
  | `vision-round-trip` | precondition "created via the Admin UI" -> "via the Agents destination's "New"" |
  | `discord-live-round-trip` | precondition "connector row created for it (Studio)" -> "(Library › Connectors)" |
  | `agent-retention-setting-roundtrip` | precondition probe "sees Studio render" -> "sees the app render" |

- **Left with a note:** `studio-smoke` (archived since 2026-07-05). Step 2's "connector account
  tile" is not renamed: the Connector Accounts surface and editor it walks were removed in
  Mission 23, so there is no current equivalent; a `> **M25 F3:**` note under the steps table
  says so, plus the `**Updated**` line. **For the Flight Director.**
- **Hits left unchanged (generic words, or descriptive/historical, not a retired surface):**
  "read back" / "falls back" / "feeds back" / "steered back" / "gets back" in
  `kb-agent-query-round-trip`, `pty-session-containment`, `tool-sandbox-containment`,
  `windows-pty-parity`, `tool-sandbox-box-isolation`, `kb-folder-index-round-trip`,
  `gemma-tool-use-recovery`, `directory-lookup-send`, `agent-self-revision-propagation`,
  `discord-live-round-trip`, `agent-governance-and-search`; the M24 Flight 6 Out-of-Scope lines
  ("Studio attach surface", "Studio rendering of …") in `kb-agent-query-round-trip`,
  `kb-folder-index-round-trip` and `kb-folder-watch-round-trip`; descriptive "Studio" in the
  Intent/Observables prose of `agent-retention-setting-roundtrip`,
  `agent-purge-now-clears-history` and `anthropic-plan-chat-parity`; "General tab" and "Delete
  Agent" (the agent editor's tab and danger-zone button, both unchanged, checked in
  `general-tab.js`); `stub-connector-round-trip`'s `new-agent-btn` (kept testid, the "New"
  action); "General provider CRUD" in `anthropic-plan-signin`.

**Docs consistency pass** (AC3). Each mismatch fixed:
- `CLAUDE.md`:
  - the router line listed `#settings/{…}[/{id}]` for every page; it now names the item routes
    that exist (`#settings/providers[/~new|/{id}]`, `#settings/tools/{name}`);
  - the Control library paragraph pointed at `#admin/design-language`; now
    `#settings/design-language`;
  - the `_lists.py` paragraph and the "Settings item pages" paragraph described the allow-list;
    now: no file is exempt, the 13 ids, the registry pin;
  - three stale locations: plan OAuth sign-in "from Administration" -> "from Settings ›
    Providers"; the M24 F6 "Studio's Knowledge section" gains "(since M25 F3, the Library list's
    Knowledge bases group)"; the stub connector "creatable in Studio" -> "from the Library list's
    Add menu";
  - checked and already right: App shell (widths 300/260/240/200 against `tokens.css` and
    `base.css`), `App.store` (the five `URLS`), the lane lists (`library_pat`'s six files, the
    agents and settings globs, `test_flow_settings_*`).
- `the_one/agents.md`:
  - "browser-tests-navigate-through-nav-helper": `destination_locator` was "`#app-topbar …`
    today, the rail later" (it is the rail link); the guard paragraph rewritten for the removed
    allow-list, the two added ids and the registry pin;
  - "Component vocabulary" and "Living reference": `#admin/design-language` ->
    `#settings/design-language`; the `surfaces` section no longer claims a section-nav sample or
    picker miniatures (only entity tiles and list rows remain);
  - "Settings item pages" Tests bullet: the allow-list sentence;
  - "Hash routing": the Paths list's "(5) editor Back" -> the item header's breadcrumb link, and
    "(1) top bar / rail" -> the rail; "the connector editor's Back a router `go()`" -> its inline
    gate gave way to router `go()`s (Back retired in L4b); "Item history" no longer says the
    Back/Cancel buttons are intent `go()`s or that connector open/edit "KEEPS its inline gate":
    the breadcrumb link pushes (browser Back re-opens the item), and no editor has a Back since
    Flight 3 (Agents L3, Library L4b, Settings L5b);
  - checked and already right: the three destination list/detail sections, the invalidation map
    (every row matched to its `App.store.invalidate` call site, and pinned by
    `test_store_static.py`'s `INVALIDATION_ROWS`), the create routes in "Hash routing".
- `docs/ui-testid-registry.md`: checked against `HEAD` with the guard's own parser: the 11 ids
  that left the live tables are all in "Retired testids", the 17 added (`agent-empty-new`,
  `agent-select-empty`, `agents-filter`, `agents-list`, `editor-breadcrumb-link`,
  `editor-unsaved`, `kb-create-cancel-btn`, `library-add-btn`, `library-add-connector|knowledge|mcp`,
  `library-empty-`, `library-list`, `providers-empty`, `providers-empty-add`, `settings-nav`,
  `settings-nav-`) are registered, and no retired id is live. The retired table's preamble
  described only Back controls and create CTAs; it now states the full guard and the pin.
- `docs/ui-control-inventory.md`: the list-pane row now lists every option and every
  controller method (`setItems`, `setSelected`, `focusSelected`, `scrollToSelected`,
  `scrollToGroup`, `getItems`, `destroy`); two new rows for control kinds Flight 3 added with no
  inventory entry: the item header breadcrumb (`.editor-breadcrumb` / `editor-breadcrumb-link`,
  six editors) and the unsaved-changes caption (`.editor-unsaved`), both `not yet defined`
  (hand-built per editor); the chat "List row" row named Flight 3 as its replacement owner (it
  is Flight 4's Chats list); the living-reference route. The `navGroups` and menu rows and the
  section-nav removal were already right. `test_ui_control_inventory.py`: 13 passed.
- `README.md`: the screenshot alt text and captions (text only; the images are unchanged): the
  alt text still describes what each image shows but names the current area and says the
  screenshot is earlier ("the Providers page … when providers showed as a grid of tiles … the
  page is now a table"; the agent editor "from before the agent list column"); captions "Agent
  Studio" -> "Agents", "System — managing LLM providers …" -> "Settings — managing providers …";
  stale area names elsewhere: the intro ("Agent Studio", "Chat", "System" -> Agents, Chats,
  Library, Settings), "System → General → Appearance" -> "Settings → Appearance", "the Studio
  "Connectors" section" -> "the Library's Connectors group", "System → Design Language" ->
  "Settings → Design language".
- The flight's Post-Flight "Documentation updated" item (CLAUDE.md routes, store collections,
  `_lists.py`; agents.md list/detail shell, invalidation map, create routes, retired section
  nav; the registry's retired Back and new testids; the inventory) is satisfied by the tree. The
  checkbox in `flight.md` is left for the Flight Director's flight review.

**Squawk 0101** (AC4). Corrective Action and Verification were already written (leg 4a). Leg 4b's
`test_kb_save_create_opens_the_item_and_a_row_click_does_not_prompt` and this leg's library-lane
run were added to Verification. Status `completed`, Completed 2026-10-02, Sign-Off: "Fixed by M25
F3 leg 4a (`library-list`): creating a knowledge base opens it; closed with the Flight 3 flight
commit", with the Reviewer named as the flight-end Reviewer and the verdict left pending that
review (not claimed in advance).

**Gates** (AC5), on the final tree, one at a time, `THE_ONE_TEST_NETNS=1` for every browser run,
`-x --timeout 120` per test:

| Gate | Passed | Skipped | Duration |
|---|---|---|---|
| `make lint`, `ruff format --check` | clean (496 files formatted) | | |
| `make test-unit` | 5035 (leg 5b's 5034 plus the registry pin; 1421 deselected) | 10 | 647.4s |
| static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_store_static`, `test_ui_control_inventory`, `test_nav_helper`, `test_index_asset_cache_busting`, `test_ui_library_source`) | 363 | 0 | 2.4s |
| every `test_ui_*`, both engines, `THE_ONE_REQUIRE_WEBKIT=1` | 432 | 3 (WebKit forced colours, the three skip sites) | 111.1s |
| chats lane | 42 | 0 | 94.5s |
| agents lane | 124 | 2 | 302.6s |
| library lane | 138 | 1 | 460.3s |
| settings lane | 168 | 0 | 315.7s |
| shared lane (`TEST_TIMEOUT=3600`) | 865 | 3 | 755.9s |

Every gate passed on its **first** run: no reruns, no failures to classify, no hang. Lane counts
equal leg 5b's in every lane. Squawk 0115's knowledge-base search race did not recur. The static
guards are 363 = leg 5b's 362 plus the new registry pin. The browser lanes ran while this leg
edited only Markdown, `tests/test_nav_helper.py` (a unit file no lane collects) and one
`_lists.py` docstring; the unit suite and the static guards ran after the last edit.

**Lane-union check** (`--collect-only -q`, through `scripts/run-tests.sh`):
- per lane: chats 42, agents 126, library 139, settings 168, shared 868 = **1343**;
  `-m browser tests/browser/`: **1343** collected (12 deselected: the pixel snapshots);
- files: 12 + 18 + 6 + 13 + 39 = 88, the union is identical to the whole suite's 88 files, and
  **no file is in two lanes**;
- `test_flow_settings_items.py` is in settings only (the `test_flow_settings_*` glob).

**WebKitGTK probe** (WebKitGTK 2.52.6, dev instance 8485 / `/tmp/the-one-wbnav-scratch`, verified
through `/proc/<pid>/environ`; no restart needed, since this leg changed no Python and no
`index.html`; a mock provider, two agents, a knowledge base, an MCP source and a disabled
connector seeded through the API). Every row ran in dark AND light, with the same result in both:

| URL | Root selector | Result |
|---|---|---|
| `#agents` | `#app-sidebar:has([data-testid="agent-item"])` | ok, 5 controls, 0 failures |
| `#agents` | `#main-content [data-testid="agent-select-empty"]` | ok, 1 control, 0 failures |
| `#agents/{name}/general` | `#main-content .studio-editor:not(.is-hidden) .editor-header` | ok, 3 controls, 0 failures |
| `#library/knowledge` | `#app-sidebar:has([data-testid="connector-card"])` | ok, 8 controls, 0 failures |
| `#library/knowledge` | `#main-content [data-testid="library-empty-knowledge"]` | ok, 1 control, 0 failures |
| `#library/knowledge/{id}` | `#main-content [data-testid="studio-knowledge-inventory"]` | ok, 12 controls, 0 failures |
| `#library/mcp/{id}` | `#main-content .studio-section-content:has([data-testid="save-mcp-source-btn"])` | ok, 16 controls, 0 failures |
| `#library/connectors/{id}` | `#main-content .studio-section-content:has([data-testid="save-connector-btn"])` | ok, 15 controls, 0 failures |
| `#settings/appearance` | `#app-sidebar:has([data-testid="settings-nav"])` | ok, 8 controls, 0 failures |
| `#settings/appearance` | `#main-content .content-panel.area-admin:has(#admin-theme-toggle-mount [role="radio"])` | ok, 3 controls, 0 failures |
| `#settings/providers/{id}` | that root `:has(.settings-item [data-testid="save-provider-btn"]) :is(.page-header, .settings-list, .settings-item .editor-header)` | ok, 6 controls, 0 failures |
| `#settings/tools/web_search` | that root `:has(.settings-item [data-testid="save-tool-btn"]) :is(.page-header, .settings-list, .settings-item .editor-header)` | ok, 49 controls, 0 failures |

24 runs, all `ok`. The root selectors wait for content (rows, the empty states, the mounted
editors), as legs 3-5b learned; the Settings item probes are scoped to the page header, the list
and the item header, because the editor bodies hold squawk 0114's info icons (open, not this
leg's). The seed rows were deleted afterwards (agents, providers, knowledge bases, MCP sources
and connectors all 0), and the instance was stopped with `make down` under the same env.

**Deviations and decisions.**
- **Allow-list mechanism removed rather than pinned** (the leg allowed either): nothing else used
  it, and an unconditional guard cannot be re-opened by a one-line set entry.
- **Two ids added to `RETIRED_SELECTORS`** beyond the leg's list (`agent-tile-tool-count`,
  `agent-tile-mcp-tool-count`): they are in the registry's retired table, so "every retired id"
  includes them; no browser test or helper names them.
- **The registry pin also checks the live tables**, so a retired testid that returns to the source
  (which the registry sync would force back into a live table) fails too.
- **"Studio" / "Admin" in specs**: updated only where a step or precondition tells the reader where
  to go or what to see (three specs); descriptive prose and the M24 history were left (listed
  above).
- **Docs fixes beyond the leg's named items**: the stale `#admin/design-language` route (CLAUDE.md,
  agents.md twice, the inventory), the `destination_locator` description, the Hash routing Back
  text, two inventory rows for Flight 3's new header controls, and README area names outside the
  alt text. All are text; none changes behaviour.
- **Not touched (as instructed):** the Accessibility Reviewer's items (two `h1`s on a Settings item
  page, the "Settings" nav inside the "Settings" aside, the `nameSuffix` comma spacing, leg 4b's
  focus after Continue) and squawks 0110, 0113, 0114, 0115.
- No squawks logged. Pixel snapshots were not run (optional, not a gate).

### Flight-end review fixes (2026-10-02)

**What landed.** The eight non-blocking findings the Flight Director chose to fix after the
flight-end review (the Reviewer and the Accessibility Reviewer both confirmed), plus one defect the
strengthened forced-colours test exposed (item 3b). Nothing is committed.

**1. Agent save-create staleness** (Reviewer #1; `areas/studio.js` `save(true)`). The create path
now follows the knowledge-base create's `stillOnCreate()` pattern:
- `createGen = editorGen` is captured before the POST; `onThisForm()` holds while the generation is
  unchanged (`closeOpenItem` bumps it) and `App.router.current().route` is still `agents/~new`.
- After the POST: `dirty` and `_createMode` are cleared only when `onThisForm()` and `_createMode`
  still hold (`dirty` is one flag shared by every studio editor; a re-entered create form owns
  `_createMode`).
- After the `loadAll()` reload: the bypass replace onto the new agent (and the "Agent created"
  flash) runs only if that held, `onThisForm()` still holds and `!App.router.isDeciding()`;
  otherwise nothing. The list gains the new row either way (`loadAll` re-renders it).
- The stale "so Back never returns to a stale create form" comment is gone (Back is retired); the
  comment now says the replace swaps the create route's history entry.
- **Test:** `test_flow_agents_list.py::test_save_create_does_not_pull_back_a_user_who_moved_on`,
  parametrized `agent` / `destination`. It holds the save-create's list reload (`GET /api/agents`,
  after the POST; the agent exists, checked through the API), opens another agent (a row click) or
  another destination (Settings, through the rail), releases, waits for Studio's list copy to hold
  the new agent, then a 300ms negative window: the route is still where the user went, no dialog;
  the new row is in the list (on Agents directly, or after returning).
- **Falsified:** with the `if (!stayed || !onThisForm() || App.router.isDeciding()) return;` line
  removed, both variants failed (`expected route 'agents/test-agent/general', got
  'agents/Late%20agent/general'` and `expected route 'settings/appearance', got
  'agents/Late%20agent/general'`); restored, both pass.

**2. Settings item editor title is an `h2`** (A11y decision a). `provider-editor.js` and
`tools-editor.js` emit `<h2 class="editor-title" tabindex="-1">` (class, `tabindex` and the focus
target kept; the shared `.editor-header-text .editor-title` rule sets size, weight and margin, so the
look is unchanged). Agents and Library editors keep their `h1`. Header comments updated in both
files.
- **Tests:** new `test_flow_admin_settings_nav.py::test_settings_item_pages_keep_one_h1_with_an_h2_editor_title`
  (an open provider, the provider `~new` form and an open tool: the active panel's only `h1` is the
  page title, the editor title is an `H2` with `tabindex=-1` and holds focus);
  `test_flow_provider_editor.py`'s header check selects `h2.editor-title` and asserts one `h1` in the
  active panel; the `test_flow_settings_items.py` docstring says "title (an h2)". No helper selected
  the editor title as `h1` (`_lists.settings_page_title` is the page header's `h1`, unchanged).

**3. Forced-colours selected cues** (A11y #1, WCAG 1.4.11).
- **Providers row:** `admin.css` gains a forced-colors block: `.providers-table-row.is-selected > td,
  > th { border-block: 2px solid Highlight; }`. It is in `admin.css`, not `components.css`
  (deviation from the brief's fallback): the areas layer outranks the components layer, so a
  components-layer rule would lose its bottom edge to the cells' `border-bottom` in `admin.css`.
- **Selected entity tile** (the open tool): `components.css`'s forced-colors block gains
  `.entity-tile[aria-selected="true"], .entity-tile.active { border-color: Highlight; outline: 1px
  solid Highlight; }`.
- **3b, found and fixed: the `rowStyle` list rows had no forced-colours cue at all.** The
  strengthened contract test (below) showed that in forced colours the selected Agents/Library row's
  border was identical to every other row's (`1px solid rgb(0, 0, 159)`): the transparent rest
  border is forced to the link colour, and the rowStyle selected rule
  (`.ui-list-pane-styled .ui-list-pane-row[aria-current]`, 0,3,0) outranked the forced-colours
  `Highlight` rule (0,2,0), so its `var(--accent)` was forced to the link colour too (confirmed with
  a bare Chromium probe). Fix: in the forced-colors block, `.ui-list-pane-styled .ui-list-pane-row {
  border-color: Canvas; }` and the selected rule at rowStyle specificity `{ border-color: Highlight;
  }`, so only the selected row shows a border.
- **Tests:** static `test_design_tokens_a11y.py::test_forced_colors_keep_a_non_colour_selected_cue`
  (9 cases: each cue is a rule inside its file's `@media (forced-colors: active)` block); Chromium
  emulation `test_flow_settings_items.py::test_forced_colors_keep_the_open_provider_and_tool_distinct`
  (with reduced motion, since the tile's border-color transition otherwise reads mid-way: the open
  provider's cells are `2px solid Highlight`, every other row's top border `0px`; the open tool's
  tile has a `Highlight` border and a `1px solid` `Highlight` outline, no other tile does);
  `test_ui_library_contract.py::test_list_pane_forced_colors_cover_both_selection_models` now covers
  link AND button rows in both selection models and requires that no other row shows the selected
  row's border (WebKit skips, as before: no forced-colours emulation).
- **Falsified:** removing the `> th` providers rule failed the emulation test (`['0px', 'none',
  False] == ['2px', 'solid', True]`); removing the entity-tile rule failed it (`outlineHi: False`);
  removing the two rowStyle rules failed the contract test (`'1px solid rgb(0, 0, 159)' != '1px
  solid rgb(0, 0, 159)'`). Each restored.

**4. Breadcrumb link underlined at rest** (A11y #2, WCAG 1.4.1). `.editor-breadcrumb-link`:
`text-decoration: underline; text-underline-offset: 2px;` at rest, `text-decoration-thickness: 2px`
on hover (a visible hover change now that rest is underlined), the 2px `--accent` focus ring
unchanged. The breadcrumb stays a `div`. **Tests:** `test_design_tokens_a11y.py`'s breadcrumb pin
requires the rest underline; the Agents (`test_open_agent_selects_row_with_breadcrumb_and_no_back`),
Library (`_crumb` / `_expected_crumb`, all three editors in edit and `~new` modes) and Settings
(`test_provider_opens_below_the_table_with_focus_and_visibility`) breadcrumb tests read the computed
`textDecorationLine` = `underline`.

**5. Providers table row header** (A11y #4, WCAG 1.3.1). `providers-table.js` renders the Name cell
as `<th scope="row" class="providers-table-name">` holding the link (testid `provider-card`,
`data-id`, `aria-current` unchanged); the header comment's sketch matches. CSS (`admin.css`): the
column-header rule is now `.providers-table thead th`; `tbody th` shares the body cells' rule (`td,
tbody th`: padding, bottom hairline, `--fg`, middle) with `text-align: start` and regular weight (the
link sets 600); the selected wash covers `> td, > th`. No sink change (DOM-built). **Tests:**
`test_flow_settings_items.py`'s anatomy test asserts the `th[scope=row]` link, a `rowheader` named
"Alpha", the Type badge in the first `td`, and that the row header's computed alignment, padding,
hairline and vertical-align equal a `td`'s with weight 400 (its first run caught `left` vs `start`;
the rule now says `start`); `test_flow_provider_grid.py::test_provider_grid_renders_tiles` indexes the
two data cells; `test_design_tokens_a11y.py` pins `thead th`, `tbody th` and the `> th` wash.

**6. `aria-current` on button rows** (A11y #5). `list-pane.js` `applyView` writes
`aria-current="page"` on a selected link row (`href`) and `"true"` on a selected button row
(`onSelect`); header comment updated. Every selected-row CSS rule lists both values (the wash and
ring, the rowStyle border, the `--fg-secondary` meta/badge/count inks, the forced-colours border).
**Tests:** new both-engine `test_list_pane_aria_current_value_follows_the_row_kind` (link row
`page`, button row `true`, the same computed wash and ring for both kinds);
`test_list_pane_set_selected_unknown_clears_and_first_row_is_stop` selects the button row through
`[aria-current=true]` and asserts no `page`; three new `_FILL_SITES` rows gate the `"true"` inks;
the inventory row documents the values. No app list uses button rows today (Agents and Library rows
are links), so no flow test changed.

**7. `nameSuffix` separator** (A11y c). The Agents row passes `', ' + provider + ','` when the row
has a model (no dangling comma without one); the demo passes `', ' + m.provider + ','`. The name now
reads "Mid router, Router Prime, gpt-like-2". **Tests:** `test_flow_agents_list.py`'s anatomy test
expects the suffix `", Router Prime,"` and the exact name
`^Mid router\s*, Router Prime,\s*gpt-like-2$`; the orphan test expects `", no provider,"`; the
contract test `test_list_pane_name_suffix_extends_the_accessible_name_only` gains a row with meta
pinning "Mixer, OpenAI, gpt-4.1-mini". The list-pane header comment and the inventory describe the
leading and trailing separators.

**8. Stale comments** (Reviewer #4). `history-buckets.js`: the typed-modifier note now cites the
shared badge's `badge--{kind}` convention (`App.ui.badge`, `ui/feedback.js`), and the regex-strip
note says why (server data reaching a class suffix), with no reference to the deleted
`mcp-servers-grid.js`.

**Docs.** `the_one/agents.md`: the list pane (separators, `aria-current` by row kind, the rowStyle
forced-colours fix), the Agents list row and create (the staleness check), the item header chrome
(rest underline), Settings page headers (one `h1`, item pages included), the Providers table (row
header, forced-colours rule and why it lives in `admin.css`), Built-in tools (the tile cue), opening
and focus (`h2.editor-title`), the Settings items Tests bullet. `CLAUDE.md` "Settings item pages"
(row header; the focus target is the `h2` title). `docs/ui-control-inventory.md` (list pane
`aria-current` and `nameSuffix`; breadcrumb rest underline; data table row header and forced
colours). `docs/ui-testid-registry.md` (`provider-card`: the cell is the row header).

**Anomaly (caught and fixed before any gate).** A `perl -0pi` substitution whose `|`-delimited
pattern contained `\|\|` (an empty alternation) matched at offset 0 and prepended the new
`nameSuffix` lines to line 1 of `studio.js`. It still parsed (a JS label), so `node --check` passed,
but it threw `ReferenceError: provider is not defined` at load and the studio area never
registered; `test_ui_reference_page.py`'s console-error check caught it. Removed; the file now
differs from its post-item-1 copy only by the item-7 lines and evaluates and registers under a
stub; the other files this pass edited were checked for a stray prefix (none). The item-1
falsification ran before the slip; the item-1 tests were re-run after the fix (pass), and every
gate below ran after it.

**Accepted as-is (unchanged, per the Flight Director):** the negative-window
`wait_for_timeout(300)` checks; `router.js` `hintNames` not pruned; the id-exactly-`new` risk; the
"Settings" nav inside the "Settings" aside; no `h1` at the Agents/Library roots (Flight 6). Not
edited: `tests/behavior/*.md` (the `list-and-detail` spec's step 20 awaited decision (a), which is
now `h2`: for the Flight Director).

**Gates** (final tree, one at a time, `THE_ONE_TEST_NETNS=1` for every browser run, `-x
--timeout 120` per test):

| Gate | Passed | Skipped | Duration |
|---|---|---|---|
| `make lint`, `ruff format --check` | clean (496 files formatted) | | |
| unit (`make test-unit`'s selection through `scripts/run-tests.sh`, plus `-x --timeout 120`, which the target does not pass) | 5047 (leg 6's 5035 plus 12 new static cases; 1427 deselected) | 10 | 656.7s |
| static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_nav_helper`, `test_store_static`, `test_ui_control_inventory`, `test_index_asset_cache_busting`, `test_ui_library_source`) | 375 (363 plus 3 `_FILL_SITES` rows and 9 forced-colours cases) | 0 | 2.5s |
| every `test_ui_*`, both engines, `THE_ONE_REQUIRE_WEBKIT=1` | 434 (432 plus the new `aria-current` test in each engine) | 3 (WebKit forced colours) | 112.1s |
| chats lane | 42 | 0 | 94.0s |
| agents lane | 126 (124 plus the two save-create variants) | 2 | 308.5s |
| library lane | 138 | 1 | 460.7s |
| settings lane | 170 (168 plus the `h1` and forced-colours tests) | 0 | 317.0s |
| shared lane (`TEST_TIMEOUT=3600`) | 867 (865 plus the `aria-current` test in each engine) | 3 | 754.3s |

Every gate passed on its **first** run on the final tree: no reruns, no hang. Squawk 0115 did not
recur. Lane totals: 1343 passed plus 6 skipped = 1349 = leg 6's 1343 collected plus the 6 new
browser tests. Two development runs before the gates stopped early, each on a defect fixed above:
the first full `test_ui_*` run on the strengthened forced-colours assertion (3b), the second on the
`studio.js` slip (the anomaly). No dev instance was started (no WebKitGTK probe this pass); port 8484
and the default data directory were not touched. Not committed.

### Behavior-gate fix: create-form Cancel (2026-10-02)

**The finding.** The `list-and-detail` behavior spec, checkpoint L6: on a pristine agent create
form (`#agents/~new`, nothing typed) Cancel was **disabled**, so the operator could not use it to
abandon creation. Every editor gated Cancel on `dirty`. That is right in edit mode (Cancel reverts,
and a clean form has nothing to revert) but wrong in create mode, where DD8 makes Cancel "abandon":
discard, replace to the destination root, focus. The knowledge-base `~new` form (`kb-create-cancel-btn`)
never gated it and was the model. Nothing is committed.

**The fix (the Flight Director's decision).** In create mode Cancel is enabled from first render and
stays enabled for as long as the form is in create mode, dirty or not. Edit mode is unchanged
(enabled iff dirty). Per editor:

| Editor | Markup (first render) | Dirty recompute |
|---|---|---|
| Agent | `agent-editor.js`: `cancel-agent-btn` carries `disabled` only when `!isCreate` | `studio.js` `checkDirty`: `cancelBtn.disabled = !dirty && !self._createMode` (it runs at the end of every `renderEditor`, so the markup alone would not hold) |
| MCP server | `mcp-server-editor.js`: `cancel-mcp-source-btn` `disabled` only when `!isCreate` | `checkDirty`: `isEdit && !dirty`; `recaptureSnapshot` (edit-only caller): `disabled = isEdit` |
| Provider | `provider-editor.js`: `cancel-provider-btn` `disabled` only when `!isCreate` | `checkDirty`: `isEdit && !dirty` |
| Connector | `connector-editor.js`: `cancelBtn.disabled = !isCreate` | `markDirty` only ever enables; the edit-save path that disables is `!isCreate` only (unchanged) |

**The Cancel handlers assume nothing about `dirty`** (read against the code): the agent's
`cancelEdit` create branch runs `discardOpen_()` (unconditional `closeOpenItem`, `dirty = false` in a
`finally`), `go(#agents, {replace, bypassGuard})` and `focusAgentRowNear(0)`; the MCP and connector
`onCancel`s run `discardOpen_()`, a bypass replace to `#library/mcp|connectors` and
`focusLibraryGroupStart`; the provider's `onCancel` runs `_discardEditor()`, a bypass replace to
`#settings/providers`, then focus (now `focusProviderRowNear(0)`, see "Provider focus" below). None
has a dirty-only branch or a confirm, so the pristine path is the dirty path minus the typing. No
handler's discard or navigation changed; the comments (the agent's "the button only fires when
dirty", the provider's "Cancel-when-dirty is an intentional discard") now say the create form's
Cancel runs clean or dirty.

**Save-create windows checked.** Between a create POST's success and the edit-mode re-render the
create form's DOM is still mounted. Agent: `_createMode` is cleared once the POST lands (when the user
is still on the form), so `checkDirty` there would gate Cancel on `dirty` again, and `cancelEdit` with
`_createMode` false and no `_selectedAgent` is a no-op, exactly as before (Cancel was already enabled
in that window, since Save needs a dirty form). MCP re-renders on a resolved-promise microtask (no
user click can interleave). Connector: `onCancel` checks `connectorFormMode === 'edit'`, already set by
`onSaveSuccess`, so it re-renders rather than discards. Provider re-mounts in edit mode.

**Provider focus: aligned with DD8 (the Flight Director's follow-up).** The first pass left the
provider create form's Cancel focusing "Add provider" even when the table had rows. That was leg
5b's reading (its spec: "Focus goes to 'Add provider', because no row exists"), pinned by
`test_cancel_on_create_returns_to_the_root_focusing_add_provider`, and the first pass flagged it
rather than change dirty-create behaviour. The Flight Director ruled that the flight DD governs. DD8's
"Focus after Cancel, close or delete" is one rule for every list and table: a create form has no row
of its own, so focus goes to the nearest surviving row (the first row), and the primary action only
when the list is empty, as Agents and Library already did. `admin.js` `onCancel` now calls
`focusProviderRowNear(0)` (the first `provider-card` link, else "Add provider") in place of
`focusAddProvider()`; the discard, the bypass replace and the no-dialog path are unchanged. The leg
5b pin is **renamed and inverted** (not deleted and re-added):
`test_cancel_on_create_returns_to_the_root_focusing_the_first_row` seeds "Alpha" beside the
fixture's "mock" and asserts "Alpha" (the first row, A–Z) is focused and "Add provider" is not. The
empty-table case keeps "Add provider": `test_cancel_on_a_pristine_create_form_abandons_it[app_clean]`
and `test_flow_provider_editor.py::test_create_cancel_navigates_to_grid_when_dirty`.

**Breadcrumb close of `~new`: aligned too (the Flight Director's second follow-up).** The provider
follow-up flagged that closing a provider `~new` form through its breadcrumb's "Providers" link still
focused "Add provider" with rows present. The Flight Director ruled that DD8's single rule covers
close as well as Cancel. In `admin.js` `focusClosedItem`, the `closing.create || !closing.providerId`
branch now calls `focusProviderRowNear(0)` (the first `provider-card` link, else "Add provider"), with
a DD8 comment; the header comment of the delegated click listener says the same. Built-in tools have
no equivalent path: there is no tool create form, and a closed tool always has its own tile (its
branch focuses that tile's name link). New test:
`test_breadcrumb_close_of_the_create_form_focuses_the_first_row[app_with_provider | app_clean]`
(a clean `~new` form; `close_item`; route `settings/providers`, no editor, no `dialog[open]` and no
confirm overlay; with rows, no selection and focus on "Alpha" (seeded before "mock") with "Add
provider" not focused; with none, the zero-providers empty state and "Add provider" focused). No
existing test pinned focus after this close: `test_flow_provider_grid.py::test_cancel_from_create_returns_to_grid`
closes the empty-table form but checks no focus. Its docstring said "(Cancel disabled)", stale since
the fix, and now says Cancel is enabled and points to the focus pins.

**Tests** (no mock libraries; `_lists` / `_nav` helpers):

| File (lane) | New tests |
|---|---|
| `test_flow_agents_list.py` (agents) | `test_cancel_on_a_pristine_create_form_abandons_it[focuses-first-row \| focuses-new]` (enabled with nothing typed, no caption, `App.nav` clean; click: no `dialog[open]` and no confirm overlay, route `agents`, `history.length` unchanged, the empty state, no editor, no row selected, focus on the seeded row, else "New"); `test_create_form_cancel_stays_enabled_when_the_form_is_clean_again` (type, then clear: caption gone, Create disabled, Cancel enabled, and it still abandons); `test_cancel_on_a_clean_open_agent_stays_disabled` (edit pin: disabled clean, enabled by an edit, reverts in place and disables, route unchanged) |
| `test_flow_studio_library_list.py` (library) | `test_cancel_on_a_pristine_create_form_abandons_it[mcp-focuses-first-row \| mcp-focuses-add \| connector-focuses-first-row \| connector-focuses-add]` (the same checks against `#library/mcp` / `#library/connectors`, the section empty state, focus on the group's first row, else Add); `test_mcp_create_form_cancel_stays_enabled_when_the_form_is_clean_again` (the connector form has no clean-again state: its dirty mark is one-way); `test_cancel_on_a_clean_open_item_stays_disabled[mcp \| connector]` (edit pins) |
| `test_flow_settings_items.py` (settings) | `test_cancel_on_a_pristine_create_form_abandons_it[app_with_provider \| app_clean]` (the table with no selection and focus on its first link, "Alpha" seeded before "mock"; else the zero-providers empty state and "Add provider"); `test_provider_create_form_cancel_stays_enabled_when_the_form_is_clean_again`; the leg 5b pin renamed and inverted to `test_cancel_on_create_returns_to_the_root_focusing_the_first_row` (follow-up, above). The provider edit pin already existed: `test_flow_provider_editor.py::test_save_and_cancel_disabled_when_clean` and `test_cancel_reverts_in_edit_mode` |

No existing test asserted a disabled Cancel on a create form (re-grepped every cancel testid,
`.cancel-btn` and `to_be_disabled`; the remaining disabled assertions are all edit mode), so none
changed. The three files' docstrings name the fix. The first run of the 14 new tests: all passed
(35.9s).

**Falsified** (each reverted, run, restored; `git diff --stat` confirmed the restore):
- MCP: the markup's `disabled` and `checkDirty`'s `!dirty` put back. The three MCP tests failed
  (`Locator expected to be enabled - unexpected value "disabled"`, at the pristine and clean-again
  assertions); the connector variants passed. 3 failed, 2 passed.
- Agent (the original finding): only `checkDirty` put back to `!dirty`, with the markup fix kept. Both
  pristine variants and the clean-again test failed at the "enabled" assertion; the edit pin passed.
  3 failed, 1 passed. This shows the markup alone does not hold: `renderEditor` ends with `checkDirty`.
- Provider focus (the follow-up): `focusProviderRowNear(0)` put back to `focusAddProvider()`. The
  inverted pin and the pristine `[app_with_provider]` variant failed (`Locator expected to be focused
  - unexpected value "inactive"`); `[app_clean]` passed (an empty table focuses "Add provider"
  either way). 2 failed, 1 passed.
- Breadcrumb close of `~new` (the second follow-up): `focusProviderRowNear(0)` in `focusClosedItem`
  put back to `focusAddProvider()`. `[app_with_provider]` failed (`Locator expected to be focused -
  unexpected value "inactive"`); `[app_clean]` passed. 1 failed, 1 passed.

**Docs.** `the_one/agents.md`: the agents unsaved-indicator bullet (Save's `disabled`, Cancel's only on
an open agent), the agents Create bullet (create-form Cancel is never gated on `dirty`; the same for
the MCP, connector and provider forms, as the knowledge-base form; the tests), and the provider
bullet's Cancel (enabled from first render; since the follow-up, focus on the first provider link,
else "Add provider", per DD8) and the Settings items "Opening, closing and focus" bullet (the
breadcrumb close of a `~new` form, the same rule; tools have no create form). Code comments in the five files. `CLAUDE.md`, the testid registry and the behavior
specs are unchanged (none described the gating; the specs are under a running gate).

**Gates** (final tree, one at a time, `THE_ONE_TEST_NETNS=1` for every browser run):

| Gate | Passed | Skipped | Duration |
|---|---|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (496 files formatted) | | |
| `make test-unit` | 5047 (unchanged; 1441 deselected = the flight-end 1427 plus the 14 new browser tests) | 10 | 656.8s |
| static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_nav_helper`, `test_store_static`, `test_ui_control_inventory`, `test_index_asset_cache_busting`) | 344 (plus `test_ui_library_source`: 31) | 0 | 2.4s |
| agents lane (`-q -x --timeout 60`) | 130 (126 plus 4 new) | 2 | 317.7s |
| library lane | 145 (138 plus 7 new) | 1 | 480.2s |
| settings lane | 173 (170 plus 3 new) | 0 | 330.4s |
| shared lane (`TEST_TIMEOUT=3600`) | 867 (unchanged) | 3 | 763.1s |

Every gate passed on its **first** run on the final tree: no reruns, no hang, even with three
behavior-gate browsers running on the machine. The chats lane was not in the brief and was not run
(no chats file or code path changed).

**Gates after the provider-focus follow-up** (final tree; `admin.js` and
`test_flow_settings_items.py` changed, so the settings lane was rerun):

| Gate | Passed | Skipped | Duration |
|---|---|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (496 files formatted) | | |
| static guards (the seven files above plus `test_ui_library_source`) | 375 (344 + 31) | 0 | 2.4s |
| settings lane (`-q -x --timeout 60`) | 173 (unchanged: one test renamed, none added) | 0 | 324.1s |

Both passed on the first run. The other lanes and `make test-unit` were not rerun: no file they
own changed (the `admin.js` edit is one focus call in the provider `onCancel`, exercised only by
settings-lane tests).

**Gates after the breadcrumb-close follow-up** (final tree; `admin.js`, `test_flow_settings_items.py`
and the `test_flow_provider_grid.py` docstring changed):

| Gate | Passed | Skipped | Duration |
|---|---|---|---|
| `make lint`, `ruff format --check the_one/ tests/ scripts/` | clean (496 files formatted) | | |
| static guards (the seven files plus `test_ui_library_source`) | 375 | 0 | 2.4s |
| settings lane (`-q -x --timeout 60`) | 175 (173 plus the 2 new breadcrumb-close cases) | 0 | 325.7s |

All passed on the first run. Not rerun, for the same reason: the change is one focus call in the
admin area's `focusClosedItem`, reached only by settings-lane tests.

Port 8484, the default data directory and the three behavior-gate dev instances (8485, 8486, 8487)
and their scratch directories were not touched; no instance was started or restarted. Not committed.

---

## Flight Director Notes

- 2026-10-01: **Flight drafted** by the Flight Director, autonomously, without an operator
  interview.
  - **Inputs:**
    - the Flight 3 research digest;
    - the Flight 2 debrief (Architect input) and its flight-close observations;
    - reference spec §3–§8, §13 and §15.
  - **Draft shape:** 14 DDs and 6 legs.
- 2026-10-01: **Architect cycle 1** returned "approve with changes": 3 high, 6 medium and 4
  low issues, plus 6 questions.
  - **Applied:**
    - DD1 width mechanism: `aside.dataset.destination` plus CSS placed after the media
      query; the list body is the scroller.
    - Create routes move into their destination legs; L2 is narrowed to
      `data-and-announcer`.
    - The General split moves wholly into L5a, with every `settings/general` reference
      enumerated, the `admin/system` redirect retargeted, admin sub ids and a
      `lastRoutes` check.
    - DD2: the editors keep their own header and the breadcrumb is added inside it, so
      there is one `<h1>` and no duplicate testids.
    - DD8: save-create keeps each editor's render path, and `sync()` announces on an
      item-key change. A dirty clear precedes URL writes, and each type gets a
      per-type preservation check.
    - DD3 guards (d) single-closure races and (e) list-pane lifetime owned by
      `setActiveSection`.
    - DD10 focus preservation across `setItems`.
    - DD11 guard allow-list and explicit shared-lane ownership.
    - L4 and L5 each split, making 8 legs.
    - DD7 acceptance for scroll, toggle and focus.
    - The ratio-based filter gate with throttled Chromium.
    - Connector counts include `channel_map`.
    - Add-menu clipping check.
    - Prerequisites: branch-stack check, `/proc` environ, CDP apparatus default from L3.
    - Citation line fixes.
  - **Substantive changes**, so a second cycle follows (the methodology cap is two).
- 2026-10-01: **Architect cycle 2** returned "approve with changes": 2 high and 4 medium
  issues.
  - **Applied:**
    - L4a now carries every route it links to: connector routes and the hosting of all
      three editors, with interim Back to the section root. L4b is breadcrumbs, Back
      removal and checks.
    - One `sync` announce rule: only `~new` to an item in the same destination and
      section, compared before `lastAnnounceKey` is overwritten. Chats and agents syncs
      are unit-tested silent.
    - DD9 connector counts aligned with DD5, plus an L2 payload check.
    - One focus rule after Cancel, close or delete.
    - DD2 breadcrumb insertion per editor build style, re-added on the knowledge-base
      re-mount; the knowledge-base `~new` form has its own `<h1>`.
    - Reconnaissance table fixed.
    - Suggestions added to L1 and L2.
  - **The two-cycle cap is reached.** Per-leg design reviews (most legs are high risk)
    re-verify against the code.
  - **Flight set `ready`.**
- 2026-10-01: **Leg 1 `list-controls` designed.**
  - **Risk tier: high.** It touches the shared control library, the shell aside CSS, and
    the shared test guard infrastructure.
  - **Developer design review:** "approve with changes", with 2 high and 4 medium issues.
  - **Applied:**
    - The violator count corrected to 29 and computed live. `test_router_*.py` is not
      exempt.
    - The guard also walks helper modules, with an empty allow-list.
    - Focus preservation goes through `entries[]`, with an explicit tab stop after
      `applyView()` and a synchronous restore.
    - The border selection model is opt-in under `rowStyle` only; the default row is
      unchanged.
    - `padding-top: 0` is deferred to the list legs.
    - `test_shell_rail` is split by destination, and the specificity notes are added.
    - A24 is verify-only, plus the new 11px text pairs.
    - The cache-busting count goes from 72 to 73.
  - These are corrections, not a redesign, so there is no second review. Leg set `ready`.
- 2026-10-01: **Leg 1 implementation spawned** (Opus). Then **Leg 2 `data-and-announcer`
  designed**, in parallel, as an artifact only.
  - **Risk tier: high.** The leg changes cache freshness and shared router behaviour.
  - **Developer design review:** "approve with changes", with 1 high and 4 medium issues.
  - **Applied:**
    - the `sync` name hint `{ name }`, plus invalidate-before-`sync`, because a
      just-created item is not yet in the store, so a store-only name would announce the
      type noun;
    - AC3 restated as "no more than today, no duplicate per activation", with the force
      policy defined;
    - explicit failure behaviour per site, including the `refreshKnowledgeBasesCache`
      catch;
    - invalidation-map gaps filled (MCP Refresh, connector save and delete), plus
      explicit non-invalidations;
    - `App.usage` moved inside `store.js`, so there is no cache-busting conflict with
      leg 1;
    - a guarded `describeRoute` with an explicit section-to-collection map;
    - the skipped-`sync` rule and the silent MCP follow-up `sync` stated.
  - **Leg 2 set `ready`.** It waits for leg 1 to land, because both touch `router.js`
    and the docs.
- 2026-10-01: **Leg 1 landed** (`[LAND:leg]`), with every gate green on the first run:

  | Gate | Result |
  |---|---|
  | unit | 5,012 |
  | `test_ui_*`, both engines | 422 |
  | chats lane | 42 |
  | agents lane | 97 |
  | library lane | 95 |
  | settings lane | 125 |
  | shared lane | 810 |

  - The guard allow-list holds 29 files, matching the design review.
  - **Accepted deviations:**
    - `setItems` also keeps `scrollTop`.
    - Focus falls back to the filter when no row is visible.
    - Empty-group lines hide while a query is active.
    - Navgroup items pin `line-height`.
  - **Noted for the flight review:** the `nameSuffix` accessible name renders "Name ,
    Provider", with a space before the comma, at the inline boundary.
- **Leg 2 implementation** spawned (Opus).
- **Leg 3 `agents-list-detail`** designed. **Risk tier: high** (shell, router create
  route, guard removal, studio closure). Its design review is running in parallel; it is
  read-only.
- 2026-10-01: **Leg 3 design review:** "approve with changes", with 4 high and 5 medium
  issues.
  - **Applied:**
    - **Create sentinel.** `agents/~new` is special-cased in `areaSubToRoute`, `resolve`,
      `href` and `parse`. `serializeState` escapes a leading `~`, and round-trip tests
      cover `new`, `~new` and create.
    - **`item.lead`.** Added as a general list-pane library option, because no leading
      slot exists.
    - **Tab-overflow gate.** It now asserts `scrollWidth <= clientWidth`, with five tabs.
      The rail is 72px, so the pane is 652px.
    - **Delete fallbacks.** The fallbacks at `:2184` and `:2877` go to the `#agents` root.
      The row index is captured before delete.
    - **Flex sizing** for the list host.
    - **`renderAgentList`.** It is the single item builder across its six call sites.
    - **`enterCreateMode` deleted.** Its two callers use `go`, and a repeated "New" is a
      pinned no-op.
    - **Unsaved indicator.** A stable status span toggled by `checkDirty`.
    - **Migration scope.** About 15 files are listed. `test_flow_agent_tile` is rewritten.
      There is a `seed_mock_agents` bulk helper and a dead-code purge.
    - **Probe.** The exact WebKitGTK probe invocation.
  - **Kept as one leg.** A 3a/3b split would leave lanes red between legs. The file list
    is explicit, with a timebox note.
  - **Leg 3 set `ready`.** It waits for leg 2 to land.
- 2026-10-01: **Leg 2 landed** (`[LAND:leg]`), with all gates green: unit 5,018; library
  95; settings 125; chats 42; shared 843; agents 97.
  - **Request counts:** first Library activation went from 3 knowledge-base requests to 1,
    and no step rose.
  - **Agents list shape:** confirmed to carry `provider_config_id`, `kb_ids` and
    `mcp_source_ids`. Connectors carry `channel_map`.
  - **Accepted deviations:**
    - **Force policy.** A forced request joins one already in flight, so this is still
      one request per activation, and DD9 freshness is preserved.
    - **Extra invalidation** in `fetchMcpSourceTools`.
    - **Remembered name hints.** Route keys now encode the id.
    - **Hint on every save.** Edit saves stay silent but retitle the page.
    - **Test placement.** The store-library tests are in their own file.
    - **Connector naming test** goes through `go`, before leg 4a's routes exist.
  - **Squawk 0112 logged:** `POST /api/providers` without `base_url` returns 500 with a
    raw `ValidationError` instead of a 422.
- **Leg 3 implementation** spawned (Opus).
- **Leg 4a `library-list`** designed. **Risk tier: high** (router create routes,
  connector pending state, studio closure, retired grids). Its design review waits for
  leg 3 to land, because it builds on leg 3's host pattern.
- 2026-10-01: **Environment.**
  - The operator merged PR #217 (a squash, `3121c2d`), which left #218 conflicting.
  - `flight/02-shell-and-router` was rebased onto `main` (identical tree), force-pushed
    with lease, and its PR body fixed through the REST API. `gh pr edit` failed on a
    Projects-classic GraphQL deprecation.
  - #218 is now mergeable.
  - Flight 3 will branch from the rebased `flight/02`.
- **Legs 4b, 5a and 5b** designed.
  - **Risk tiers:**
    - **4b: low.** Breadcrumbs, the indicator and Back removal follow leg 3's patterns, on
      the surfaces leg 4a hosts. No design review; the flight-end Reviewer covers it.
    - **5a: high.** Router rows, redirects, the root change and a deleted module.
    - **5b: high.** The Settings page structure, toggle and refresh paths, and focus.
  - The 5a and 5b design reviews ran in parallel with leg 3's implementation. They are
    read-only, and both legs come after 4a and 4b.
- 2026-10-01: **Leg 5b design review:** "approve with changes", with 2 high and 9 medium
  issues.
  - **Applied:**
    - **Page scaffold** (high). The panels replaced `contentEl` wholesale, so each
      category render now builds `.settings-list` and `.settings-item` once:
      - list renders target the list section;
      - editors mount in the item section;
      - "Close item" clears the item section;
      - save-create re-mounts only the item section;
      - the failure messages are retargeted.
    - **Live list refresh** (high). The `providerFormMode` and `toolFormMode` guards that
      suppressed list refresh are removed:
      - `handleToolToggle` re-renders only the list;
      - the open editor's enabled control is updated in place;
      - `selectTool` no longer rebuilds the list on `_refresh`.
    - **Tool-name links** are built with `escapeAttr(App.router.href(…))`. The tile
      handlers are removed, and the keyboard test targets the name link.
    - **Deep-link category.** `renderToolsGrid` takes a `selectedName`.
    - **Explicit agents load.** The table calls `App.store.get('agents')` and
      subscribes, showing "—" until it loads.
    - **Markup kept.** The provider link keeps `data-id`.
    - **Empty state.** New testid `providers-empty`.
    - **`h1`.** Gets `tabindex="-1"`. Focus and scroll happen on intent only.
    - **Back removed.** Both `onBack` callbacks and their handlers go.
    - **Housekeeping.** The `providers-grid.js` tag, cache-busting entry and HTML-sink
      baseline; the migration counts.
  - **Leg 5b set `ready`.**
- 2026-10-01: **Leg 5a design review:** "approve with changes", with 2 high and 4 medium
  issues.
  - **Applied:**
    - **Redirect mechanism** (high). It is now an explicit `settings/general` alias in
      `resolve`, with the suffix dropped. `admin/system` and `admin/general` are
      special-cased directly.
      - **Correction:** the plan assumed `lastRoutes` is persisted. It is in memory only,
        so the persisted-state AC is replaced: `lastRoute('settings')` never returns
        `settings/general`, and the rail's first-use href is checked.
    - **Section-nav retirement** (high). The design-language `.section-nav` sample is
      removed (the `navGroups` demo replaces it). The AC5 grep is narrowed to code
      identifiers, and the comments on live behaviour are rewritten.
    - **Label churn.** About 15 test files are listed, the bulk of them `.section-nav-item`
      locators the guard already forces.
    - **Labels.** `SECTION_LABELS` drops `general` for the three new pages, and `tools`
      becomes "Built-in tools".
    - **Page headers.** They already exist, so this is mostly a label change. Their CSS
      is scoped to `.area-admin`, because `.page-header` is shared with Agents and
      Library. "New Provider" becomes "Add provider".
    - **Accessible name.** The theme radiogroup's `aria-labelledby` target moves to the
      Appearance `h1`.
    - **`admin.js` `'general'` touchpoints** are enumerated, with a `GENERAL_SUBS`
      helper. `_setCategory` calls `navGroups.setSelected`.
    - **Sidebar scroll.** `.sidebar-panel` is `overflow: hidden`, so the nav host
      scrolls.
    - **Test file name.** It is `test_flow_admin_settings_nav.py`, which matches the
      settings-lane glob.
  - **Open questions, decided:**
    - The `#settings/general/<x>` suffix is dropped.
    - `test_flow_keyboard.py`'s roving-tabindex test is **rewritten** as link
      Tab-order and Enter tests, not deleted. Keyboard coverage stays.
  - **Leg 5a set `ready`.** It still runs after 4a and 4b, because it deletes
    `section-nav.js`.
- 2026-10-01: **Leg 3 landed** (`[LAND:leg]`), with all gates green:

  | Gate | Result |
  |---|---|
  | unit | 5,019 |
  | `test_ui_*`, both engines | 426 |
  | agents lane | 121 |
  | library lane | 95 |
  | settings lane | 125 |
  | chats lane | 42 |
  | shared lane | 848 (rerun after a test-precondition fix) |

  - **Scale.** The filter keystroke ratio is 1.93 (gate ≤3), and `GET /api/agents` at 60
    agents takes about 10ms, so no squawk.
  - **Allow-list:** 29 → 22.
  - **Accepted deviations:**
    - `emptyText(q)` as a function;
    - a shared `.badge-dot` rule;
    - the list pane's filter path tightened;
    - two real bugs fixed: `position: relative` on the list pane, and a re-scroll after
      `document.fonts.ready`;
    - the pre-existing dirty-baseline bug fixed, which AC5 needs;
    - three extra testids.
  - **Squawk 0113 logged.** The Built-in Tools category master toggles have no accessible
    name; this is pre-existing.
  - **Left for leg 6 (DD12):** the specs `studio-agent-crud` and
    `stub-connector-round-trip` still describe the grid.
  - **Flagged for the flight-end review:** the `nameSuffix` comma spacing (from leg 1).
- **Leg 4a updated with leg 3's ground truth before its review:**
  - the host class in the DOM is `.section-nav`;
  - the isolation test file's name;
  - moves between Library sections keep the pane;
  - reuse the `fonts.ready` re-scroll;
  - **re-home `test_nav_guard`'s inline-dialog test.** Leg 3 moved it onto the connector
    editor's inline Back dialog, which leg 4a removes.
- **Leg 4a design review** spawned (Opus, read-only).
- 2026-10-01: **Leg 4a design review (cycle 1):** "approve with changes", with 4 high,
  10 medium and 10 low issues.
  - **High, applied:**
    - **H1, knowledge-base create announces the noun.** `go` has no name hint, and a
      knowledge-base id is opaque. Fix: invalidate, **await the store `get`**, clear
      `dirty`, check the user is still on `~new`, then `go` replace. On a failed `get`,
      go anyway.
    - **H2, the list never refreshes after a mutation.** `invalidate` notifies no
      subscriber. Fix: `reloadLibrary(name)` in every create, save, rename, delete and
      Refresh callback, and the section caches are fed from the store.
    - **H3, request counts.** A fetch policy is defined:
      - pane creation and studio `activate` force-get the three collections;
      - moves between Library sections fetch nothing;
      - `test_library_list_request_counts` is rewritten.
    - **H4, migration scope.** An explicit 17-file table, with lanes and hit counts.
  - **Mediums, applied:**
    - the Add menu uses `align: 'end'`, with a corners clipping check (stop if it still
      clips);
    - connector Cancel works by mode;
    - the create and pending plumbing order;
    - the knowledge-base create form keeps M24's enabled Create, "Name is required.", the
      43-code-point hint and the error line;
    - the new test file is `test_flow_studio_library_list.py`, so it runs in one lane;
    - `listPane.scrollToGroup`, with the full factory checklist;
    - `_nav.py` parity and the accepted risk of an id of exactly `new`;
    - loading and failure states, with no empty-line flash;
    - delete focus uses DD8's flat rule (the leg's per-group variant is withdrawn);
    - helpers: reuse `expect_selected`, and the interim-Back assertions go in allow-listed
      files.
  - **Lows, applied:** the citations table, deleting `mcp-servers-grid.js` (baseline and
    cache count), CSS hazards, the AC6 query, the probe selector, docs, singular forms,
    same-route Add refocusing, and the AC5 wording.
  - **The `test_nav_guard` inline-dialog test** is re-homed by driving
    `App.nav.confirmLeave` directly. After this leg, only the router adapter calls it.
  - **The designer's questions, decided (Flight Director):**
    1. **Closing an item without Back:** the breadcrumb's last segment links to its
       section root (DD2 refinement). Leg 4b implements it for Agents and Library, and
       leg 5b for Settings. It goes on the DD14 checkpoint list.
    2. **Connector Cancel:** edit mode reverts in place (DD8); create mode discards and
       returns to the root.
    3. **Knowledge-base Create:** it stays enabled with "Name is required." (the M24
       contract).
    4. **List fetching:** pane creation and studio activate (forced); moves between
       sections fetch nothing; mutations reload.
    5. **The `~new` form's unsaved indicator** is leg 4b's.
  - **Substantive changes,** so a second review cycle (the last allowed) was spawned.
- 2026-10-01: **Leg 4a design review (cycle 2):** "approve with changes", with 1 high, 4
  medium and 7 low issues. The reviewer verified H1–H3 mechanically against `store.js`
  and `router.js`, and found the request-count table achievable exactly.
  - **Applied:**
    - **One pending-item rule for MCP and connectors** (high).
      - A root fetches nothing.
      - A pending id on a fresh hydrate force-gets, then consumes, then heals.
      - A pending id on an intent consumes from the cache, or on the next notification,
        and never heals.
      - Lifetime subscriptions re-attempt pending consumes.
      - Connectors get MCP's within-section branch.
      - This resolves the conflict between copying the grid fetch and the (0,0,0) moves,
        and keeps the Forward dead-id heal test.
    - **Knowledge-base create order.** Capture `editorGen`; clear `dirty` before the await
      only if the user is still on `~new`; re-check the route, the generation and
      `!isDeciding()` before `go`; Create stays disabled.
    - **`onListStale`** callback for MCP's Refresh and Reset invalidations.
    - **`scrollToGroup`.** Optional `group.id`, validated unique; it runs after the gated
      first `setItems` too.
    - **Loading.** The pane shows "Loading library…" while gated. Data counts as settled
      by `peek(...).loaded`.
    - **Lows:**
      - the 16-step request-count table;
      - same-route Add refocuses whether dirty or not, for all three items;
      - the `knowledge/new` hydrate calls `closeOpenItem`;
      - the delete row index is read in `onDeleteSuccess`;
      - focus after a create-mode Cancel;
      - pane testid `library-list`;
      - stale text fixed (card testids do not retire; `encodeURIComponent` in `sync`).
  - **The reviewer's question, decided:** a failed forced refresh with a last-good list
    keeps the stale rows. "Couldn't load" appears only for a list that never loaded.
  - **No third cycle.** These fixes are local text edits with the fixes prescribed. The
    two-cycle cap is respected, and the implementing Developer re-greps at leg start.
  - **Leg 4a set `ready`.**
- **Leg 4a implementation** spawned (Opus).
- 2026-10-02: **Leg 4a landed** (`[LAND:leg]`), with all gates green:

  | Gate | Result |
  |---|---|
  | unit | 5,026 |
  | `test_ui_*`, both engines | 432 |
  | library lane | 123 |
  | agents lane | 123 |
  | settings lane | 125 |
  | chats lane | 42 |
  | shared lane | 858 |
  | WebKitGTK probe | 0 failures |

  - **First-run failures, both fixed:**
    - **A real bug.** Late agent counts grew rows from one line to two and pushed the
      scrolled group out of view. Rows now stay two lines from the first fill.
    - **A test precondition** in `test_router_announce`.
  - **Allow-list:** 22 → 20. Its remaining Library hits are interim Back only.
  - **Squawk 0101:** `in-progress`, with Corrective Action and Verification written. The
    flight commit closes it.
  - **Accepted deviations:**
    - section caches follow the store's value;
    - a cold-cache intent closes the open form;
    - the activate refetch is literal;
    - empty-state action labels "Add …";
    - `kb-create-error` has `role="alert"`;
    - the AC6 guard workaround (class names built from parts);
    - the agent-tab links are not retargeted (optional).
- **Leg 4b refreshed and tiered.**
  - **Context refreshed** from leg 4a: the `~new` form's breadcrumb, the tests moving from
    interim Back to the breadcrumb link, and the allow-list exits.
  - **Added AC5b:** breadcrumb links, the DD2 refinement.
  - **Risk tier: low,** as at planning. It is additive header chrome and indicators
    following the leg 3 and leg 4a patterns, with no router, store or lifecycle change.
    The breadcrumb link is a plain `href` the router already guards. No per-leg design
    review; the flight-end Reviewer covers it.
  - **Leg 4b set `ready`.** Its implementation is spawned (Opus).
- 2026-10-02: **Leg 4b landed** (`[LAND:leg]`). Every gate passed on its first run:

  | Gate | Result |
  |---|---|
  | unit | 5,026 |
  | `test_ui_*`, both engines | 432 |
  | library lane | 138 |
  | agents lane | 124 |
  | settings lane | 125 |
  | chats lane | 42 |
  | shared lane | 858 |
  | WebKitGTK probe, scoped to the editors | 0 failures |

  - **Allow-list:** 20 → 15, all Settings.
  - **Accepted deviations:**
    - AC2's grep matches only the `RETIRED_SELECTORS` guard entries, which is by design.
    - Connector edit-mode Save now leaves the editor clean (it previously stayed dirty).
    - "Preserved" means no teardown after the editor's own create-to-edit render.
  - **For the flight-end review:** after Continue on a breadcrumb close, focus goes to
    the item's row (DD8) rather than `nav.js`'s generic `<main>` focus, via a
    `setTimeout(0)`. The review should check this against the router's
    focus-after-commit contract.
- **Leg 5a context refreshed** with the ground truth after legs 3–4b: studio no longer
  calls the section nav, and the 15-file allow-list. The plan was otherwise reviewed and
  set `ready` earlier. Its implementation is spawned (Opus).
- 2026-10-02: **Environment.**
  - The operator merged PR #218 (a squash, `560aa9b`). Its tree equals the local
    `flight/02` tip `e6a3a90`; `git diff` is empty.
  - Flight 3's branch still stacks on the pre-squash `flight/02` commits.
  - **Plan:** after the flight commit, `git rebase --onto origin/main e6a3a90`. It replays
    only `508fc83` and the flight commit, with no working-tree change. It is not done now,
    because the working tree holds uncommitted leg work and a Developer is editing.
- **Leg 6 `behavior-specs-and-close`** designed. **Risk tier: low:** gates, a guard
  tightening, mechanical spec text and docs, with no product behaviour change. No per-leg
  design review.
  - **Split for Witnessed independence:**
    - **The Developer:** the guard, the specs **not** run at close, the docs pass,
      squawk 0101 and the gates.
    - **The Flight Director:** authors `list-and-detail` and updates the six run-at-close
      specs, after the flight-end review.
  - The behavior runs follow the flight commit, as in Flight 2.
  - The leg stays `planned` until leg 5b lands.
- **Leg 6 draft spec.** The Flight Director drafted `tests/behavior/list-and-detail.md`
  (status `draft`, 21 steps; Settings steps 18–20 to verify against legs 5a and 5b), with
  the copy read from source.
- 2026-10-02: **Leg 5a landed** (`[LAND:leg]`), with every gate green on the final tree:

  | Gate | Result |
  |---|---|
  | unit | 5,031 |
  | static guards | 359 |
  | `test_ui_*`, both engines | 432 |
  | chats lane | 42 |
  | agents lane | 124 |
  | library lane | 138 |
  | settings lane | 146 |
  | shared lane | 864 (rerun) |
  | WebKitGTK probe | clean, apart from squawk 0110, the pre-existing hidden chat input |

  - **Allow-list:** 15 → 7, all leg 5b's.
  - **Falsification:** removing the alias, or the settings `padding-top` rule, made 4
    tests fail.
  - **First-run failures, both fixed:** a landmark-name uniqueness test, and two
    `test_store` listbox-name tests (the rename was reverted to leg 5b's scope).
  - **Accepted deviations:**
    - geometry follows §4 (header 16px 32px);
    - the "Add provider" icon;
    - legacy suffixes redirect straight to Appearance;
    - `GENERAL_SUBS` lives on the descriptor;
    - Prompts has no in-page label;
    - the theme cross-tab test navigates through `_nav`;
    - a new `LEGACY_URL_TESTS` entry;
    - a `Makefile` `verify-serving` fix, because `make restart` failed after
      `section-nav.js` was deleted.
  - **For the Accessibility Reviewer:** `<nav aria-label="Settings">` sits inside the
    aside also labelled "Settings". `test_landmarks_and_aside_labels` was narrowed to
    unique (role, name) pairs. The reviewer decides whether the aside is relabelled on
    Settings.
  - **Specs left for leg 6:** `system-provider-config`, `anthropic-plan-signin`,
    `anthropic-plan-chat-parity`, `save-preserves-config`, `extended-thinking-tool-turn`,
    `studio-agent-crud`, `chat-roundtrip`, `agent-governance-and-search`.
- **Leg 5b context refreshed** with the ground truth after leg 5a:
  - the 7-file allow-list;
  - the "LLM providers" listbox that `test_store` uses;
  - **the `Makefile` `verify-serving` list must drop any deleted file;**
  - the `_lists` Settings helpers;
  - `admin.js` lines moved.

  Its implementation is spawned (Opus).
- 2026-10-02: **Leg 5b landed** (`[LAND:leg]`), with every gate green:

  | Gate | Result |
  |---|---|
  | unit | 5,034 |
  | `test_ui_*`, both engines | 432 |
  | settings lane | 168 |
  | shared lane | 865 |
  | agents lane | 124 |
  | library lane | 138 (rerun) |
  | chats lane | 42 |

  - **The library lane's first run had one failure,**
    `test_detail_view_indexing_poll_reindex_and_search`, a pre-existing race in that test.
    It passed alone and in the full rerun, and is logged as **squawk 0115**.
  - **Allow-list:** 7 → **empty**.
  - **Falsification:** breaking 4 behaviours made 12 tests fail.
  - **WebKitGTK probe:** clean on the leg's surfaces. Three pre-existing info-icon buttons
    are named only by `title`, logged as **squawk 0114**.
  - **Accepted deviations:**
    - clicking the open item's own link only brings it into view;
    - focus after save-create goes to the new title;
    - flash messages now show;
    - the tools editor's Cancel-after-Save bug is fixed;
    - providers sort A–Z;
    - "Used by" keeps the last good counts after a failed refresh;
    - the `providers-empty-add` testid;
    - `selectTool` drops stale responses.
  - **For the Accessibility Reviewer:** two `h1`s on a Settings item page (the page title
    and the editor title).
- **Leg 6** set `ready` with the ground truth after leg 5b, and its implementation is
  spawned (Opus).
- 2026-10-02: **The Flight Director updated the run-at-close specs** (Witnessed
  independence; the Developers did not touch these):
  - `workbench-navigation`: steps 3, 4, 6, 7, 8 and 10;
  - `shell-navigation-smoke`: steps 4, 5 and 8;
  - `studio-agent-crud`: steps 2, 3, 5, 6, 7, 9 and 10, plus the prose;
  - `system-provider-config`: steps 2, 3, 6, 7, 10 and 11, plus the prose;
  - `kb-studio-round-trip`: a mapping note only, with assertions unchanged.

  `list-and-detail` is drafted; its step 20 awaits the Accessibility Reviewer's call on
  the Settings item page `h1`.
- 2026-10-02: **Leg 6 landed** (`[LAND:leg]`). Every gate passed on its first run:

  | Gate | Result |
  |---|---|
  | unit | 5,035 |
  | static guards | 363 |
  | `test_ui_*`, both engines | 432 |
  | chats lane | 42 |
  | agents lane | 124 |
  | library lane | 138 |
  | settings lane | 168 |
  | shared lane | 865 |
  | lane-union check | 1,343 tests = the whole suite, no file in two lanes |
  | WebKitGTK probe | 24/24 runs ok |

  - **Guard.** The allow-list mechanism is removed, and a registry↔guard pin is added
    (falsified three ways).
  - **Specs.** 10 non-close specs updated; `studio-smoke` (archived) is left with a note.
  - **Docs.** The consistency pass is done.
  - **Squawk 0101** is `completed`.
- **All legs have landed.** The flight-end review is spawned: a Reviewer and an
  Accessibility Reviewer in parallel, both Sonnet (never Opus for review).
- 2026-10-02: **Flight-end review.** Both reviewers signalled `[HANDOFF:confirmed]`, with
  no blocking issues.
  - **Accessibility Reviewer, decisions on the four flagged questions:**
    - (a) Settings item editor titles → `h2`;
    - (b) keep the "Settings" `nav` inside the "Settings" aside (different roles);
    - (c) keep the `nameSuffix`, adding a separator before the model;
    - (d) leg 4b's focus after Continue is correct and robust.
  - **Non-blocking findings:**
    - forced-colours selected cues missing on the Providers table rows and
      `.entity-tile.active`;
    - the breadcrumb link has no cue at rest besides colour;
    - no `h1` at the Agents and Library roots;
    - the Providers table needs a `th scope="row"`;
    - `aria-current="page"` on button rows.
  - **Reviewer, non-blocking findings:**
    - agent save-create has no staleness check (`studio.js:~3445-3460`; the KB path has
      `stillOnCreate()`), plus a stale "Back" comment;
    - the `nameSuffix` is acceptable;
    - the negative-window waits are acceptable;
    - stale `mcp-servers-grid.js` comments in `history-buckets.js`;
    - `hintNames` is never pruned (bounded);
    - the id-exactly-`new` risk is accepted.
  - **Fix pass, applied:**
    - the agent create staleness check;
    - Settings item titles → `h2`;
    - forced-colours cues;
    - the breadcrumb underlined at rest;
    - `th scope="row"`;
    - `aria-current="true"` on button rows;
    - the `nameSuffix` separator;
    - stale comments.
  - **Deferred to Flight 6 (alignment) and the debrief:** an `h1` at the Agents and
    Library roots, and a destination-specific aside label (polish).
  - **Snapshot** of the reviewed tree, taken through a temporary index:
    `3bf9d0b8a6696392781d2c5cd327130c2d2a7297`. A focused re-review checks the fix diff
    against it.
  - **Fixes landed** (see the "Flight-end review fixes" entry). Every gate was green on
    its first run. The pass also found and fixed list-pane selected rows that were
    indistinguishable in forced colours.
  - **Focused re-review** of the fix diff against the snapshot (Sonnet):
    `[HANDOFF:confirmed]`, with no blocking issues and no residue from the `perl`
    anomaly.
- 2026-10-02: **Leg statuses → `completed`.** The flight spec's checkpoints L1–L5b, its
  legs list and the completion items for legs, tests, docs and squawk 0101 are checked
  off. The L6 checkpoint stays open until the behavior runs pass and the checkpoint
  package is ready.
- **Flight commit** on the stacked branch, then `git rebase --onto origin/main e6a3a90`.
- 2026-10-02: **Flight commit `7aa490f`**, rebased onto `main` `560aa9b` after #218 was
  squash-merged.
- 2026-10-02: **Behavior close gate (DD12).** All six specs ran with live Executor and
  Validator pairs (SendMessage), on CDP-driven Chromium (DD12's fallback; goldfinch's input
  is still broken). Each spec had its own instance, port and workspace. Wave 1 started at
  12:08:59Z and wave 2 at 12:46:53Z, both concurrent:

  | Spec | Instance | Result |
  |---|---|---|
  | `workbench-navigation` | 8485 | 28/28 |
  | `kb-studio-round-trip` | 8487 | 18/18 |
  | `list-and-detail` | 8486, with the stub flag | 38/38 after one fix |
  | `shell-navigation-smoke` | 8485 | 8/8 |
  | `studio-agent-crud` | 8485 | 18/18 |
  | `system-provider-config` | 8485 | 20/20 |

  - **`kb-studio-round-trip` step 10.** My instruction (SIGTERM) let the graceful drain
    finish the whole pass, so resume was not exercised. I re-ran the step with SIGKILL, and
    it passed.
  - **`list-and-detail` L6 FAILED, attempt 1.** Cancel was disabled on the pristine
    `#agents/~new` form, against DD8. It is a real product defect, and the MCP, connector
    and provider create forms had it too.
  - **The Flight Director's call (autonomous):** fix the system, continue the run, and rerun
    the checkpoint after the fix (Witnessed protocol: a failed checkpoint does not land).
  - **The rest of `list-and-detail`.** After the fix, L6r passed on a cold reload, and the
    Dark variant (D2–D20) ran on the fixed code.
  - **`system-provider-config` D10.** The Executor's capture script crashed after the delete
    fired, so the focus clause was unmeasured. D10 was rerun as **D10r** after an API
    re-seed and passed; this is recorded in its run log as an apparatus deviation.
  - **Run logs** are under each spec's `runs/`, and every spec's Last Run line is updated.
    `list-and-detail` is now `active`.
- 2026-10-02: **Behavior-gate fix** (Developer; see the "Behavior-gate fix: create-form
  Cancel" entry). Create-mode Cancel is enabled from first render on all four editors.
  - **Provider focus decisions (Flight Director, out loud).** The Developer flagged that the
    provider create-form Cancel, and then its breadcrumb close, focused "Add provider" even
    when the table has rows. Leg 5b's wording ("because no row exists") is a leg-level
    reading that conflicts with **DD8's single rule**: when there is no row of the item's
    own, focus the nearest surviving row, and use the primary action only when the list is
    empty. **The flight DD governs**, and Agents and Library already comply. Both paths were
    aligned to "first row, else Add provider"; the pinned test was inverted by renaming.
  - **Gates, all green:**
    - unit 5,047;
    - agents lane 130;
    - library lane 145;
    - settings lane 175;
    - shared lane 867;
    - static guards 375;
    - lint and format clean.
  - **Focused review** (Sonnet): `[HANDOFF:confirmed]`, with no high or medium issues.
- 2026-10-02: **Spec fixes from the runs** (Flight Director):
  - `kb-studio-round-trip` step 10: stop with SIGKILL after at least one item is indexed,
    and snapshot the indexed ids and hashes first.
  - `list-and-detail` step 19: a new-document load from `about:blank`, because an in-app
    hash change is redirected before any reload.
  - The other spec-quality notes the Validators raised go to the debrief: `history.length`
    capped at 50 in Chromium, focus targets after Stay and Continue, success toasts, a
    second seeded provider/agent, and so on.
- **Observations for the debrief and the DD14 checkpoint** (none spec-asserted, none
  blocking):
  - **Focus after Create and Save** (agent, provider) and **after Test** (provider) drops to
    BODY, because the clicked button re-renders or disables.
  - **Focus after Add → MCP server or Connector** stays on the Add menu trigger, not the
    form's Name field. The knowledge-base form and Agents' New do focus Name.
  - **Cancel on a create form** focuses the first row, not the previously open item.
  - **A deep-linked selected row** scrolls flush to the list bottom, with zero margin.
  - **Agent-row provider dots** are coloured per provider *type*, so two mock providers look
    identical.
  - **Cross-client staleness.** A tab's store does not see another client's new agent until
    a reload (per-client freshness bound).
  - **Single-provider fixtures** auto-select the provider on `#agents/~new`.

- 2026-10-02: **Flight landed** (`3e61968`). PR #219 is marked ready for review; the
  operator merges.
- 2026-10-02: **DD14 checkpoint package prepared.**
  - **Instance.** A fresh dev instance on 8485, scratch data dir
    `/tmp/the-one-f3-checkpoint`, with `THE_ONE_DEV_MODE=true` and
    `THE_ONE_STUB_TEST_ENDPOINT=1`; the environment was verified from `/proc/<pid>/environ`.
    The behavior instances on 8485 and 8486 were stopped first. It is seeded through the API
    with:
    - 32 agents across 4 providers (Anthropic and OpenAI with placeholder keys, Ollama, Mock);
    - 3 knowledge bases;
    - 2 MCP servers (stdio, the repo's `hello_server.py`);
    - 2 disabled Discord connectors.
  - **Screenshots.** 21 views × 2 themes × 2 sizes (1440×900, 1024×768) = 84 captures, with
    no page errors and every route matching. The approved B3 board was rendered from its
    committed source with a scratchpad stand-in for the canvas runtime (agents, library and
    settings screens, both themes). Neither set is committed (reference README: screenshots
    are flight-log evidence only).
  - **Comparison page,** published as a private artifact:
    https://claude.ai/artifact/A6PWRtnpDXtfwbLJnAumLw. It puts the board beside each
    destination's build, shows every view, and lists eight explicit questions:
    - DD7: items open below the list;
    - DD2: the unsaved indicator;
    - DD5: knowledge-base meta drops "files";
    - DD4: "Chat" deferred to Flight 4;
    - the breadcrumb-link refinement;
    - the zero-margin row scroll;
    - focus after create and save;
    - provider dots per type.
  - **Next.** STOP for the operator's go or no-go before Flight 4. The outcome will be
    recorded here.

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
