# Leg: client-data-store

**Status**: completed
**Flight**: [Shell and Router](../flight.md)

## Objective

Introduce `App.store`, the shared client data layer, for **`agents` and `providers`
only**, and migrate their duplicate list fetches onto it. The store hands out copies,
rejects on failure while keeping the last good value, follows the invalidation map with
generation-safe invalidation, and de-duplicates in-flight requests.

This collapses the **agents and providers** part of the first-activation double load.
The remaining duplicates (tools, MCP sources, KBs, provider model caps) are **recorded,
not fixed**; Flight 3 adds those collections.

## Context

- **Flight decision:** DD8 is this leg's spec: collections, API (`get`/`force`, `peek`,
  `invalidate`, `subscribe`), copies, `fetchJson`, never caching failures, load state,
  the invalidation map, and the freshness bound. Read it in `flight.md`.
- **Leg 1 anomaly:** Studio and Admin load their data twice on first activation, and
  Studio paints the empty canvas before any fetch resolves. Determine whether the
  duplicate is a router-era leftover (legs 3–4 may have already changed it) or a
  fetch-site duplicate this store removes. Record the before and after request counts.
- **Consumers to migrate.** Re-grep, since lines drift after legs 3–6:
  - `chat.js` ~:405 and ~:1017 (`/api/agents`, twice per activate), ~:1016
    (`/api/providers`);
  - `studio.js` `loadAll` (`/api/agents` ~:1150, `/api/providers` ~:1349);
  - `admin.js` providers (~:378).
- **Mutation sites** (corrected at design review; positions as of the review, re-grep):
  - **Agents:** `studio.js` POST ~L2664, rename POST ~L2717, PUT ~L2745, DELETE ~L2089.
    Self-configuration flows all funnel through `_refreshAgentAfterSelfConfigurationChange`
    (~L1169), so **one** `invalidate('agents')` goes there.
  - **Providers:** `provider-editor.js` create/save ~L775, delete ~L901, OAuth
    sign-in/out ~L375, ~L401, ~L427.
  - **Cross-collection:** KB rename `knowledge-section.js` ~L558, KB delete ~L1444, MCP
    delete `mcp-server-editor.js` ~L1304, plus connection delete ~L1345. These modules
    call `App.store.invalidate('agents')`.
  - **Studio's own copies.** `studio.js` writes to its own `self._agents` copy at ~L1861,
    ~L1181 and ~L2766 (`kb_tool_names`, which is detail-shaped; the list route omits it).
    These **stay on Studio's copy**. The store holds list-shaped agents, and detail-shaped
    objects are never written back into it.
  - **`admin.js` ~L469-480 and ~L582-589** mutate `toolConfigs`, **not** agents or
    providers, so they are out of scope. `toolConfigs` is not added in this leg.
- **Studio's second cache.** `loadAll` assigns `self._agents` and `self._allProviders`.
  Agents and Library share the studio module, and `mountArea` only re-activates on a
  module change, so an invalidation from Library (a KB rename) would never reach the
  Agents grid. Studio therefore **subscribes** (`App.store.subscribe('agents'|'providers')`)
  and re-renders its tile grid or its provider data on notification.
- **Out of scope:** Library collections (KBs, MCP sources, connectors, tools and tool
  configs) arrive in Flight 3 with their first list-pane consumers. `toolConfigs` may be
  added only if migrating the admin tools grid is natural (an acceptable variation).

## Inputs

- `static/js/api.js` (`App.api.fetchJson`, which rejects on non-2xx), `index.html`, the
  cache-busting count.
- `areas/chat.js`, `areas/studio.js`, `areas/admin.js`, and every mutation site for
  agents and providers. Grep for `fetch('/api/agents`, `'/api/providers`, and their
  POST, PUT and DELETE calls. This includes OAuth sign-in and out for providers, KB
  rename and delete (which affect agents), self-configuration enable and disable,
  revision approve and restore, and MCP delete.

## Outputs

- **`static/js/store.js`** (new, loaded right after `api.js`). `App.store`:
  - `get(name, {force})`: a Promise of a **copy** (`JSON.parse(JSON.stringify(…))`).
    - `force` joins an in-flight request, else refetches.
    - It **rejects on failure** with the `fetchJson` error, so `loadAll`'s
      `Promise.all` still rejects and `showLoadAllError` still shows (squawk 0014,
      `test_flow_studio_loadall_error`). `peek().value` keeps the last good value
      with `ok:false`, and the next `get` retries.
  - `invalidate(name)` **bumps a generation counter**. A request started before the
    invalidation is not joined by later `get`s and does not populate the cache, so
    post-mutation reads never see pre-mutation data.
  - `peek(name)`: `{value (copy, or null), loaded, ok, error}`.
  - `invalidate(name)`.
  - `subscribe(name, fn) → unsubscribe`. `fn(copy)` is called after every successful
    load, including the first.
  - Collections: `agents` and `providers`.
  - Fetches go through `App.api.fetchJson`. A failure sets `ok: false` and keeps the
    last good value, and is never cached as the value.
- **Consumers** migrated to `App.store.get(...)`. Activation uses `{force: true}` where
  today's code refetches on activate.
  - **Chats is restructured.** Today `ws.onopen` runs `checkSetupState()` (providers and
    agents) and then `.then(fetchAgents)` (agents again, serially). Both re-activation
    calls are back-to-back (chat.js ~L1105, ~L1634-1635). Fold them into **one** function
    that reads agents and providers through the store once, and derives both the setup
    state and the agent list from it.
  - Chats keeps swallowing errors (`.catch(function(){})`). On `ok:false` it keeps its
    prior setup state, so a transient failure never flips to the "no setup" canvas.
  - Studio's connector form dropdown (`studio.js` ~L939, which needs fresh data) uses
    `get('agents', {force: true})`.
- **Invalidation** calls added after every successful mutation in the DD8 map, with
  their cross-collection effects.
- **Docs:** `agents.md` "Client data store (`App.store`)" covering the API, copies,
  load state, the invalidation map and the freshness bound. CLAUDE.md gets a pointer.
- **Flight log:** the before and after request counts for first activation of each
  destination, and the invalidation-site list.

## Acceptance Criteria

- [x] **AC1 — Store API.** As in Outputs, including reject-on-failure and
  generation-safe invalidation.
  - `store.js` is ES5 and uses shell placement (DD12).
  - A browser test (in-app, Chromium) covers:
    - de-duplication: two concurrent `get`s issue one request, and `force` joins an
      in-flight request;
    - copies: mutating a returned value doesn't change `peek`;
    - failure handling: a 500 makes `get` **reject**, while `peek` keeps the previous
      value with `ok:false`, and the next `get` retries;
    - in-flight then `invalidate` then `get` issues a **second** request, and the stale
      response is not cached;
    - `subscribe` notifications;
    - `invalidate` followed by `get`, which refetches.
- [x] **AC2 — Consumers migrated.**
  - The literal list fetches `fetch('/api/agents')` and `fetch('/api/providers')` in
    chat, studio and admin use the store, and grep proves it.
  - The `/api/agents/{name}…` and `/api/providers/{id}…` detail and action routes stay
    as they are by design, including the single-agent detail fetches at studio ~L1840,
    ~L1177 and ~L1169.
  - **Request-count table** (Playwright request log, recorded before and after in the
    flight log, **excluding** WebSocket-reconnect-triggered reads):
    - Chats on cold boot and on re-activation: at most 1 `/api/agents` and 1
      `/api/providers` each;
    - Agents on cold boot, and Agents↔Library: at most 1 of each per activation;
    - Settings → Providers: at most 1 `/api/providers`.
  - The remaining duplicates (tools, MCP, KBs, model caps) are listed as remaining
    work.
- [x] **AC3 — No cache leakage, with propagation.**
  - **Isolation.** After Studio mutates its own `self._agents` copy (the ~L1861 and
    ~L2766 paths), `App.store.peek('agents').value` is unchanged.
  - **Save round trip.** Edit an agent and save. The store is invalidated, Chats'
    agent list reflects the saved value, and Studio's grid re-renders through its
    subscription.
  - **Cross-destination.** Rename a KB in Library, then open Agents. The tile grid
    reflects the change with no studio re-activation.
- [x] **AC4 — Invalidation map.** Each of these invalidates the collection DD8 names:
  - agent create, save, rename or delete;
  - provider create, save or delete;
  - provider OAuth sign-in or sign-out;
  - KB rename or delete;
  - self-configuration enable/disable;
  - revision approve or restore;
  - MCP delete.

  A test per row, or a parametrized one, performs the mutation through the UI or API
  and asserts the next consumer read reflects it. Rows that need a live provider
  (OAuth) are covered by a unit-level spy on `App.store.invalidate`.
- [x] **AC5 — Load-state gating preserved** (retargeted at design review), with each
  case tested by its own route:
  - **(a)** A 500 on the **list** `/api/agents` (exact route) makes `loadAll` reject.
    The load-error banner shows, and no tile or save is offered. This keeps squawk 0014
    and `test_flow_studio_loadall_error` green.
  - **(b)** A 500 on the **detail** `/api/agents/{name}` leaves today's
    `_selectedAgentLoaded:false` save block (squawk 0090) untouched and still working.
    This leg doesn't touch the detail fetches.
  - **(c)** KBs are not in the store; the `_knowledgeBasesLoaded` gating is unchanged.
- [x] **AC6 — Docs.** The `agents.md` section and the CLAUDE.md pointer.
- [x] **AC7 — Gates pass.**
  - `make lint`;
  - `make test-unit`;
  - all five lanes, one at a time;
  - every `test_ui_*` in both engines.

## Verification Steps

- AC1–AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_store*.py -x -rA`,
  plus the request-count test and a grep.
- AC6–AC7: a doc read and the gates.

## Implementation Guidance

1. **`store.js`** plus its tests.
2. **Migrate chat**, then studio `loadAll`, then admin. Count requests before and after.
3. **Mutation sites**: work on copies, or update through the store.
4. **Invalidation map**: add the calls and their tests.
5. **Docs and gates.**

## Edge Cases

- **`fetchJson` on list GETs.** A 204 or a non-JSON 200 throws, which counts as a
  failure; that is acceptable for list endpoints. Never use it for the mutation sites in
  this leg.
- **Default agent.** Verify in `api.py` whether the synthetic default agent appears in
  `GET /api/agents`. Record the answer, and drop this case if it doesn't.
- **Self-configuration writes happen server-side** with no WebSocket notice. Activation
  with `force` is the freshness bound (DD8); document it.
- **Default agent (`agent_name=None`) sessions**: the store's agents list excludes the
  synthetic default agent, matching today's list behaviour. Verify.
- **Provider masked secrets**: the store holds what the API returns (masked `api_key`).
  Never store or log secrets beyond what the API exposes.

## Files Affected

- `static/js/store.js` (new), `api.js` (only if `fetchJson` needs a small extension),
  `areas/chat.js`, `areas/studio.js`, `areas/admin.js`, and the mutation-site modules
  (e.g. self-configuration-tab, knowledge-section)
- `index.html`, `tests/test_index_asset_cache_busting.py`
- `tests/browser/test_store*.py` (new)
- `the_one/agents.md`, `CLAUDE.md`
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`

## Citation Audit

Line numbers come from the flight review at `fe595cc` and the leg 1 anomaly. Re-grep at
leg start, because legs 3–6 move the code.

Design review (Developer, 2026-10-01) — "approve with changes". Applied:
- `get` rejects on failure, preserving the `loadAll` error banner;
- generation-safe `invalidate`;
- Chats restructured to one read per activation, keeping its prior setup state on
  failure;
- AC5 retargeted to list, detail and KB routes;
- Studio subscribes, so its second cache doesn't go stale;
- the mutation-site lists corrected (`admin.js` `toolConfigs` out of scope; Studio's
  detail-shaped copies stay local);
- the objective scoped to agents and providers;
- the request-count table defined;
- the missing consumers and sites added.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
