# Leg: data-and-announcer

**Status**: completed
**Flight**: [List and Detail](../flight.md)

## Objective

Give the destination legs the data and announcements they need, with **no surface
change and no new route**:

- **Store collections.** `App.store` gains the Library collections `knowledge-bases`,
  `mcp-sources` and `connectors`. The invalidation map grows, and the existing Library
  list fetches move onto the store (DD9).
- **`App.usage`.** A new helper derives "used by N agents" counts from the agents list
  (DD9).
- **Item names in the title and announcer.** `describeRoute` names every item kind from
  the store: providers, knowledge bases, MCP servers and connectors (DD8).
- **Create→item announcements.** `sync()` announces exactly one transition: from a
  `~new` route to an item in the same destination and section (DD8). This fixes the
  stale "Settings — Providers — New" announcement after provider and MCP save-create.

## Context

- **Flight decisions:**
  - DD8: the announcer rule and its cycle-2 pin.
  - DD9: the collections, the invalidation map, the subscriptions, the counts and the
    freshness bound.
- **`static/js/store.js`** (Flight 2 leg 7):
  - `URLS = { agents, providers }` at `:21`;
  - `get` / `peek` / `invalidate` / `subscribe`;
  - copies, generation-safe invalidation, reject on failure;
  - `agents.md` "Client data store (`App.store`)" holds the map.
- **Current Library fetch sites** (`areas/studio.js`):
  - `fetchKnowledgeBases_` `:499-515`, which feeds the KB grid with a stale-then guard;
  - `fetchKnowledgeBases` `:1395`, which feeds `loadAll` and `refreshKnowledgeBasesCache`;
  - `fetchMcpSources_` `:863-875`, the grid, plain list;
  - `fetchMcpSources` `:1202`, the editor variant `?include_agent_surfaces=1`. It
    **stays a direct fetch**, because it is detail-shaped (DD9);
  - `fetchConnectors_` `:1022-1030`.
- **Mutation sites:**
  - knowledge-base create `knowledge-section.js:373`, rename near `:558`, delete near
    `:1444`. The rename and delete paths already call `App.store.invalidate('agents')`
    at `:571` and `:1449`;
  - MCP save `mcp-server-editor.js:1192`, delete `:1304` (already invalidates agents at
    `:1307`), connection delete `:1346`, and the Refresh-tools path (grep `refresh` in
    the editor);
  - connector save `connector-editor.js:693`, and the delete path (grep `DELETE`).
- **Connector payload.** `GET /api/connectors` returns `_connector_response` →
  `account.model_dump()` (`api.py:3432-3444, 3488-3491`). Its `config` carries
  `default_agent` and the optional `channel_map`. Inbound routing reads `channel_map`
  first (`inbound.py:341-348`). The DD9 connector count can therefore use both.
- **MCP list shape.** `GET /api/mcp-sources` hides self-configuration surface rows unless
  `include_agent_surfaces=1` (`api.py:2519-2533`). The store's `mcp-sources` collection
  is the plain shape. The Library list never shows surface rows, by design.
- **Router announcer** (`router.js`):
  - `describeRoute` `:357-371` names only agents (by id) and tools;
  - `announce` `:396-404`;
  - `sync` `:556-577` overwrites `lastAnnounceKey` at `:569-570` before any comparison,
    and never announces.
  - `commit` announces on `go()` (`:435`).
- **Callers of `sync`** that must stay silent:
  - `chat.js:1237` (`sessions/{id}`);
  - `studio.js:567`, `:640` and `:3049` (studio sections);
  - provider and MCP `onSaveSuccess` paths. These announce **only** on the create→item
    transition.

## Inputs

- `static/js/store.js`, `static/js/router.js`
- `areas/studio.js`, `areas/studio/knowledge-section.js`,
  `areas/studio/mcp-server-editor.js`, `areas/studio/connector-editor.js`,
  `areas/admin/provider-editor.js`
- `the_one/interfaces/web/api.py` (read only: payload shapes)
- `tests/browser/test_store.py`, `tests/test_store_static.py`,
  `tests/browser/test_router_announce.py`
- `the_one/agents.md` "Client data store (`App.store`)", "Hash routing — the router"

## Outputs

**1. Store collections.** `URLS` adds:
- `'knowledge-bases': '/api/knowledge-bases'`
- `'mcp-sources': '/api/mcp-sources'` (the plain list shape)
- `'connectors': '/api/connectors'`

There are no API changes: same copies, generations, rejection and subscriptions.

**2. Invalidation map.** Each mutation invalidates the following, after a successful
response only:

| Mutation | Collections invalidated |
|---|---|
| knowledge base: create | `knowledge-bases` |
| knowledge base: rename, delete | `knowledge-bases`, `agents` (rename and delete already invalidate `agents`) |
| MCP source: create, save | `mcp-sources` |
| MCP source: delete | `mcp-sources`, `agents` (already) |
| MCP source: connection delete | `mcp-sources`, `agents` (already) |
| MCP source: Refresh tools and test-connect success (`mcp-server-editor.js` ~`:1960-1983` writes `config._cache`, also auto-run after create; the squawk 0102 refresh path `:1264-1275`) | `mcp-sources` (the tool count changes) |
| connector: create and save (`connector-editor.js:693`), delete (`:600`) | `connectors` (no invalidation exists today) |
| agent save | `agents` (unchanged; it drives every "used by" count) |

**Not invalidating**, because the list does not show what they change (design review,
item 4):
- knowledge-base folder add (`knowledge-section.js:1228`), item delete (`:906`) and
  retry (`:1333`). The Library list shows the name and the agent count only;
- connector pairing-code POST (`connector-editor.js:443`) and test (`:567`, `:587`).

**The knowledge-base rename path** still writes the section-local array in place
(`studio.js:621`). That is harmless with store copies. It keeps the in-place write and
adds the invalidation.

`agents.md` documents the full map, and `test_store_static.py` pins one grep per row,
in the style of Flight 2.

**3. Fetch-site migration.**
- `fetchKnowledgeBases_`, `fetchKnowledgeBases`, `fetchMcpSources_` and `fetchConnectors_`
  read through `App.store.get('<name>', { force: <as today> })`.
  - Section activation refreshes with `force: true`.
  - Each keeps its stale-then guard and its grid render exactly as today.
  - Where a caller relied on `fetch().then(r.json())` swallowing a non-2xx, it now gets
    a rejection, because `fetchJson` rejects. Keep each caller's current failure UI.
- The editor-variant `fetchMcpSources` (`?include_agent_surfaces=1`) and every by-id
  fetch stay as they are.
- **Failure behaviour** (design review, item 3). `fetchJson` rejects on non-2xx and on
  JSON error bodies, which `fetch().then(r.json())` used to resolve as data. Every
  caller keeps its current failure UI:
  - the grid sites' `.catch` at `:508-513`, `:871-875` and `fetchConnectors_`;
  - `refreshMcpSourcesCache`'s catch at `:1436-1441`;
  - **`refreshKnowledgeBasesCache` (`:1453`, used by the agent-edit mount at `:1918`
    and `:1989`): confirm it has a catch, and add one if not**, so a KB list failure
    never breaks the editor mount.
  
  Re-run `test_flow_studio_loadall_error.py` and `test_flow_studio_knowledge_attach.py`
  (which unroutes `**/api/knowledge-bases` at `:302`) after the migration.
- **Force policy** (design review, item 2):
  - `loadAll`'s knowledge-base `get` is **non-forced**;
  - the grid's first-activation `get` is non-forced, so it joins or reuses `loadAll`'s;
  - `force: true` applies only on a **re-activation** of the section.
- **Grep proof.** No literal `fetch('/api/knowledge-bases')`, `fetch('/api/mcp-sources')`
  or `fetch('/api/connectors')` list call remains in `static/js` outside `store.js`. The
  `?include_agent_surfaces=1` variant, by-id URLs and mutation URLs are exempt.

**4. `App.usage`.** A section **inside `store.js`**. There is no new file, so no new
`index.html` tag and no cache-busting change, which avoids colliding with leg 1's count
change (design review, item 5). It takes the **list-shaped agents** array
(`App.store.peek('agents').value` or a caller-supplied array) and exposes:

- `App.usage.providerAgents(agents, providerId)` → number of agents with
  `provider_config_id === providerId`;
- `App.usage.kbAgents(agents, kbId)` → agents whose `kb_ids` contain `kbId`;
- `App.usage.mcpAgents(agents, sourceId)` → agents whose `mcp_source_ids` contain it;
- `App.usage.connectorAgents(connector)` → the **distinct agent names** in
  `config.default_agent` ∪ `values(config.channel_map)`, skipping empty or non-string
  values;
- `App.usage.mcpToolCount(source)` → `source.config._cache.tools.length` when present,
  else `null`. A `null` means "tools not loaded"; the leg 4a meta shows "Tools not
  loaded".

These are pure functions with no fetching and no DOM.
- **Verify the agents list shape first.** Confirm the fields are present in
  `GET /api/agents`, the list shape: `provider_config_id`, `kb_ids`, `mcp_source_ids`.
  The design review confirmed `list_agents` → `_agent_response` → `AgentConfig.model_dump`
  (`api.py:716-724`, `:126-128`; `config.py:109,120,121`); confirm nothing strips them.
  If a field is missing from the list shape, **stop and report**. Adding a server field
  is a scope decision for the Flight Director.

**5. `describeRoute` item names (DD8).** For an item route, use the item's display name
from the store when the collection is loaded.
- **Route section to collection** (an explicit map in `router.js`; design review, item
  6):

  | Route | Collection |
  |---|---|
  | `settings/providers` | `providers` |
  | `library/knowledge` | `knowledge-bases` |
  | `library/mcp` | `mcp-sources` |
  | `library/connectors` | `connectors` |

- **Guard every read** with `window.App && App.store && App.store.peek`. `router.js`
  loads at `index.html:33`, before `store.js` at `:50`, and `describeRoute` first runs
  from `start()`.
- **Never pass `peek` an unknown name.** `col()` throws for one (`store.js:25-27`).

Names come from these fields:
- providers (`name`) and knowledge bases (`name`);
- MCP sources (`name`) and connectors (`name`);
- agents (the id is already the name; unchanged);
- tools (unchanged).

When the collection is not loaded, or the id is unknown, fall back to a **type noun**:
"Provider", "Knowledge base", "MCP server" or "Connector". Never the raw id. The
30-character truncation stays. `applyTitle` and `announce` both use it, so the title
matches.

**6. `sync()` announces only create→item (DD8, cycle-2 issue 2), with a name hint.**

- **Signature.** `App.router.sync(areaId, sub, opts)`, where `opts` is an optional
  `{ name }`.
- **Why the hint** (design review, item 1, high). A just-created item is not in the store
  cache when its `onSaveSuccess` calls `sync`, so a store-only name would announce the
  type noun.
- **Hint callers.** The provider (`admin.js:331`) and MCP (`studio.js:772`) save-create
  sites pass `{ name: updated.name }`.
- **Invalidate before `sync`.** The provider save-create path invalidates `providers`, and
  the MCP save invalidates `mcp-sources`, so later reads are fresh.
- `describeRoute(route, nameHint)` uses the hint, when given, for the item part.

Inside `sync`:

1. Read `prevKey = lastAnnounceKey` **before** recomputing.
2. Compute `dd = describeRoute(parsed.route, opts && opts.name)`.
3. If `prevKey` ends in `/~new`, `dd.key` has the **same destination and section**, and
   `dd.key` is not a `~new` key, announce `dd.parts`.
4. Set `lastAnnounceKey = dd.key` in every case, as today.

**A skipped save-create `sync`** (`deciding` or `hashMatchesCurrent` early return,
`router.js:556-563`) leaves `prevKey` at `~new`. The next successful `sync` to an item
in that section then announces once. That is the same transition, delayed, and it is
accepted.

**MCP create re-render.** The MCP create path follows its `sync` with
`renderMcpSourcesSection()` and `studio.js:847` (`sync('studio', 'mcp-sources')`). That
second call must stay silent, because `prevKey` is already the item. Pin it in AC6.

Every other `sync` stays silent: canonicalisation, Chats sessions, studio sections, and
the delete-to-root replaces done through `sync`.

## Acceptance Criteria

- [ ] **AC1 — Store collections.** Browser tests (in-app, Chromium) extend
  `test_store.py`. For each of `knowledge-bases`, `mcp-sources` and `connectors`, they
  check:
  - a `get` returns a copy;
  - `force` joins an in-flight request;
  - a 500 rejects, while `peek` keeps the last value;
  - `invalidate` mid-flight then `get` issues a second request;
  - subscribers are notified.
  
  Keep them light: one parametrized test per behaviour.
- [ ] **AC2 — Invalidation map.** Each row of Outputs §2 invalidates its collections after
  a successful mutation. Coverage:
  - **Browser tests** for knowledge-base create, knowledge-base delete, MCP delete and
    connector create. Each performs the mutation through the UI and asserts that the next
    `App.store.get` (or the grid) reflects it.
  - **Static grep pins** for every row in `test_store_static.py`.
- [ ] **AC3 — Fetch-site migration.**
  - The grep proof holds.
  - **Request counts** (Playwright request log, Library first activation and
    re-activation):
    - there are **no more list requests than today**;
    - there is **no duplicate request for the same collection within one activation**.
    
    Record the before and after table in the flight log.
  - **Behaviour unchanged.** The existing library lane passes unchanged (grids, deep
    links, the KB inventory).
- [ ] **AC4 — `App.usage`.** Unit-level browser tests, an `evaluate` over fixed arrays,
  cover:
  - each count, including zero and missing fields;
  - `connectorAgents` de-duplicating an agent that appears as both the default agent and
    a `channel_map` value;
  - `mcpToolCount` returning `null` without `_cache`.
  
  The agents list-shape field check is recorded in the flight log.
- [ ] **AC5 — `describeRoute` names.** With the store warm, the title and the
  announcement read the item's display name for a provider, a knowledge base, an MCP
  server and a connector. Cold deep links fall back to the type noun, never the raw id.
  Tests extend `test_router_announce.py`.
- [ ] **AC6 — `sync` announce rule.**
  - **Announces:** a provider `~new` → save-create (`sync` to the id, with the name hint)
    announces "Settings — Providers — {name}", and an MCP `~new` → save-create announces
    the server name.
  - **The MCP follow-up `sync('studio', 'mcp-sources')`** after create stays silent.
  - **Silent:** a Chats session `sync`, a studio section `sync` and a same-key
    canonicalisation `sync` do **not** change the announcer text. The test seeds a
    sentinel announcer text and asserts it is unchanged.
  - **Unit:** a static or unit test asserts the ordering, comparing `prevKey` before
    reassignment.
- [ ] **AC7 — Docs.**
  - `agents.md`: the new collections, the full invalidation map, `App.usage`, the
    `describeRoute` naming and fallback, and the `sync` announce rule.
  - `CLAUDE.md`: its `App.store` paragraph names the five collections and `App.usage`.
- [ ] **AC8 — Gates.**
  - `make lint` and `make test-unit` (which includes the static guards);
  - the library, settings and shared lanes with `THE_ONE_TEST_NETNS=1`, plus the chats
    lane, which verifies the announcer stays silent on chat syncs;
  - `test_ui_guards`, `test_token_definitions` and `test_design_tokens_a11y`.

## Verification Steps

- AC1, AC2, AC4, AC5 and AC6:
  `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_store.py tests/browser/test_router_announce.py -x -rA`
  plus the new test file(s).
- AC3: the grep, the request-count test and the library lane.
- AC7 and AC8: read the docs; run the gates.

## Implementation Guidance

1. **Store collections.** Adding the `URLS` entries is a one-line change. Then migrate
   the four fetch sites one at a time, re-running the library lane's relevant file after
   each.
2. **Invalidation calls.** Add them at each mutation site after the success response, as
   Flight 2 did for providers.
3. **`App.usage`.** Check the agents list shape first (`curl` with the credential against
   the dev instance on 8485, never 8484).
4. **`describeRoute` names.** Read `App.store.peek(collection)` synchronously; there is
   no fetch inside `describeRoute`.
5. **The `sync` rule and the name hint**, then the announcer tests.
6. **Docs last.** Leg 1 also edits `agents.md`, `CLAUDE.md` and `router.js` (`applyShell`,
   a different function). Re-read those files before editing them; do not overwrite.
   Then run the gates.

## Edge Cases

- **A cold deep link** to `#settings/providers/{id}`. The first announcement and the title
  use "Provider" until the store loads. The title may update when the editor's own
  `sync` runs, but it never re-announces (same key). This is accepted per DD8.
- **A provider renamed while open.** The title updates only on the next commit or sync.
  Acceptable.
- **A `connectors` payload** without `channel_map`, or without `default_agent`. Count
  only what is present, and return 0 when neither is present.
- **`fetchJson` on a 204 or a non-JSON 200** counts as a failure (Flight 2 L7 note). It
  does not apply to these GETs.
- **Self-configuration surface MCP rows** are absent from the plain list. Counts and the
  Library use the plain list only.
- **The agents store does not exist yet in a Library-only session**, for example a cold
  load at `#library/knowledge`. `App.usage` takes an array, so leg 4a calls
  `App.store.get('agents')` and re-renders on its notification. This leg only provides
  the helper.

## Files Affected

- `static/js/store.js` (with `App.usage` inside it), `static/js/router.js`
  (`describeRoute`, `sync`)
- `areas/admin.js` (`onSaveSuccess` name hint at `:331`)
- `areas/studio.js`, `areas/studio/knowledge-section.js`, `areas/studio/mcp-server-editor.js`,
  `areas/studio/connector-editor.js`
- `tests/browser/test_store.py`, `tests/test_store_static.py`,
  `tests/browser/test_router_announce.py`, and a new `tests/browser/test_store_library.py`
  if useful
- `the_one/agents.md`, `CLAUDE.md`
- `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`

## Citation Audit

The Flight Director checked these against `4828d53` / `508fc83`:

| Citation | Status |
|---|---|
| `store.js:21` `URLS` | verified |
| `studio.js:499-515` `fetchKnowledgeBases_`; `:863-875` `fetchMcpSources_`; `:1022-1030` `fetchConnectors_`; `:1202` `include_agent_surfaces`; `:1395` `fetchKnowledgeBases` | verified |
| Existing invalidations: `mcp-server-editor.js:1307, 1349`; `knowledge-section.js:571, 1449`; `provider-editor.js:411, 434, 789, 907` | verified |
| `router.js:357-371` `describeRoute`; `:556-577` `sync` (`:569-570` key write) | verified |
| `api.py:3432-3444` `_connector_response` `model_dump` (config included); `:3488-3491` list | verified |
| `inbound.py:341-348` `channel_map` first | verified (Architect) |
| `admin.js:331`, `studio.js:772` save-create `sync`; `mcp-server-editor.js:1193-1197` (no invalidation), `~1960-1983` Refresh; `connector-editor.js:600, 693`; `knowledge-section.js:559, 906, 1228, 1333`; `studio.js:621, 1436-1441, 1453`; `index.html:33, 50`; `store.js:25-27`; `router.js:396-404, 435, 642` | verified (leg design review) |

---

## Post-Completion

Completion steps (status transitions, the flight-log update, checking off in the parent
flight, and the commit) are Flight Control protocol, driven by the execution workflow.
They are not repeated here.
