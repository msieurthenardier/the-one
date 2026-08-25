# Leg: self-configuration-surface-read

**Status**: completed
**Flight**: [Self-Configuration Surface](../flight.md)

## Objective

Stand up the loopback self-configuration MCP surface end to end in read-only
form: a per-agent credential the gate resolves to that one agent, a
streamable-http endpoint the platform serves itself, the two read tools with
their secret-free projection, an enable/disable API with a Studio tab, and the
per-agent `streamable-http` source row that makes the operator's existing
per-source and per-tool controls govern it — off by default for every agent.

## Context

- **DD1** — the surface is a real `streamable-http` source row per enabled
  agent pointing at a loopback endpoint on the existing app and port. The
  re-entrancy probe (flight log, Session Notes) confirmed the platform's own
  client path connects to a sub-app mounted on the real app from inside HTTP
  and WebSocket handlers in ~45 ms with no deadlock, and established six
  constraints this leg inherits (lifespan wrap, shutdown-drain warning,
  `auth_posture=no_auth`, operator-level gate identity, URL shape, cache-first
  build). Each is addressed below.
- **DD2 / DD4** — identity comes from the credential, not the URL; Leg 2 mints
  one credential per agent for that agent's own client only. The credential
  lives in the source row's `secrets`, which is encrypted at rest and masked by
  `_mcp_source_response`. The gate's lookup seam is `api_credential.register_source`
  + `resolve_caller` (synchronous, walked per request); `IdentifiedCaller`
  carries `identifier` and `source` and nothing else.
- **DD3** — surface rows are hidden from the admin MCP Sources listing but must
  reach the agent editor's MCPs tab. Both screens call `GET /api/mcp-sources`
  today (`studio.js:fetchMcpSources_` for the grid, `studio.js:fetchMcpSources`
  for the editor), so the filter must be a request-level switch, not a
  repository change.
- **DD6** — the four-tool catalog; this leg ships the two read tools.
  `get_my_configuration` and `describe_my_capabilities` return purpose-built
  projections, never a serialized row.
- **DD9** — a credential whose agent no longer has the surface enabled is
  refused, and the refusal is asserted.
- **Flight open question resolved here**: `describe_my_capabilities` **does**
  list the self-configuration source among the agent's sources. Visibility is
  not writability — the allowlist is the catalog's shape — and an agent that
  cannot see the surface it is speaking through reasons badly about its own
  limits. It is listed under its ordinary source name with its tool names.
- **Leg-level decisions (LD1–LD6)** below refine the flight's DDs. LD2's
  route-scoping is the one that touches Mission 20's middleware; it is recorded
  in the flight log as Decision D5 with the reasoning.
- **Prior-leg learnings (Leg 1, landed 2026-08-24, uncommitted on the flight
  branch)**: `SQLiteAgentStore(conn, encryptor: Encryptor | None = None)` —
  pass `get_encryptor(settings.data_dir)` explicitly from `api.py` so the test
  fixture's patch governs it (`api.py:_agent_store`, :78). Every agent-config
  HTTP return goes through `api.py:_agent_response` (:87) — new endpoints in
  this leg that return an agent config must too. `_overrides.py:MCP_OVERRIDE_CREDENTIAL_KEYS`
  (:112) is the marker-derived credential-key set; reuse it for the
  surface-row override guard (Edge Cases). `update_agent` now resolves
  `mcp_overrides` against the stored row via `_merge_preserved_mcp_credentials`
  (:128) **before** validation — the ownership guard this leg adds to
  `create_agent`/`update_agent` must run on the validated config, after that
  merge. Full unit lane: 4288 passed / 10 skipped in ~6 min; run it once at
  leg end, not per iteration.

### Leg decisions

**LD1 — Ownership lives on the row.** A surface row carries
`config["self_configuration"] = {"agent": "<agent name>"}` and is named
`self-configuration (<agent name>)`. Enabled-ness **is** the row's existence
plus its id being in the owner's `mcp_source_ids` — no new `AgentConfig` field,
so nothing the agent can write governs the surface (mission constraint).
`rename_agent` cascades the marker and name; `delete_agent` deletes the row.
Ownership is enforced server-side: `create_agent` / `update_agent` reject
(422) any `mcp_source_ids` entry that is another agent's surface row, so agent
B can never attach agent A's surface even via the raw API.

**LD2 — Per-agent credentials are gate-scoped to the surface path.** A new
`SelfConfigurationCredentialSource` registers behind the seam. The credential
reuses `LocalApiCredential`'s shape with a distinct prefix (`agt`), so the
file source's `parse` rejects it on prefix and falls through. Resolution goes
through an in-memory registry `{identifier → (source_id, secret)}` (the seam is
synchronous; a per-request DB read is not an option), loaded from every marked
row at lifespan start and mutated by enable/disable in-process. **The gate
confines this source to the surface's mount path, HTTP only.** Mechanism: a
leaf constants module exports `CONFINED_SOURCE_PATHS: dict[str, str]` mapping
a credential-source *name* to the path prefix it may reach
(`{"self-configuration": MOUNT_PATH}`); the gate, after resolving a caller,
looks the caller's `source` up in that map and — only when present — refuses
any HTTP path outside the prefix and every WebSocket upgrade with 403. Sources
absent from the map (`file`, and the cookie channel's `session`) are admitted
exactly as today; the `CredentialSource` protocol itself is not widened (DD8's
"do not widen" holds). Flight 3 adds its own entry.
Without this, an `agt` credential is an operator credential with a different
prefix — the Mission 20 debrief's carry-forward ("harmless today; live the
moment a second `CredentialSource` exists") is exactly this. This is the
per-route scope enforcement Mission 20 deferred for want of a consumer; the
consumer has arrived.

**LD3 — The surface URL is reconciled at startup, never trusted from the
row.** Enable stores `http://127.0.0.1:{settings.port}{MOUNT_PATH}/` (always
`127.0.0.1`, never `settings.host`, which may be `0.0.0.0`). Lifespan start
rewrites `config.url` on every marked row from the current `settings.port`
while it loads the credential registry, so a port change between runs cannot
strand a row.

**LD4 — One FastMCP instance, stateless, mounted on the app, lifespan-wrapped.**
`mcp.server.fastmcp.FastMCP(stateless_http=True, streamable_http_path="/")`
mounted at `MOUNT_PATH = "/mcp/self-configuration"`, its
`session_manager.run()` wrapped around the existing lifespan body (probe
constraint 1; `run()` is once-per-instance). Stateless avoids cross-request
session state that a credential could otherwise ride. The calling agent is
resolved inside each tool from the ASGI scope the gate stamped
(`ctx.request_context.request.scope[CALLER_SCOPE_KEY]`) — the SDK sets
`RequestContext.request` to the Starlette request for HTTP transports. If
stateless mode turns out not to interoperate with the platform's client, fall
back to stateful (the probe's configuration) — both require `run()`.

**LD5 — Projections are explicit field lists, and the leg names them.**
`get_my_configuration` returns exactly: `name`, `description`, `system_prompt`,
`llm_model`, `provider` (`{name, type}` of the provider row — never its id,
`api_key`, `base_url`, or `secrets`), `max_iterations`,
`chat_history_retention_days`, `enabled_tools`, `disabled_tools`, and
`knowledge_bases` (names). It never touches `tool_overrides`, `mcp_overrides`,
`connector_acls`, `connector_always_listen`, `provider_config_id`, `kb_ids`,
`mcp_source_ids`, or `connector_ids`. `describe_my_capabilities` returns
`builtin_tools` (name + description, filtered by the same two predicates
`AgentFactory.create` uses — operator `ToolConfig.enabled` and
`AgentConfig.is_tool_enabled`), `mcp_sources` (name, type, and tool names from
`config._cache.tools` filtered through `filter_mcp_tools_by_override` — the
flight's Verification demands the filter be exercised, not bypassed), and
`connectors` (name, type). Neither tool builds an `Agent` — building one from
inside that agent's own tool call would recurse into the surface.

**LD6 — Enable populates the tool cache in-process.** The enable path lists
the FastMCP instance's tools directly (no loopback hop) and writes
`config._cache = {"tools": [...], "auth_posture": "no_auth", ...}` in the shape
`test/connect` writes, so agent builds take the cache-first path (probe
constraint 6) and the pool never attempts DCR on a 401 (constraint 3).

## Inputs

- Leg 1 landed: encrypted/masked agent overrides; `_agent_response` in
  `api.py`; `SQLiteAgentStore` takes an encryptor.
- `the_one/api_credential.py` — `LocalApiCredential` (`generate`, `parse`,
  `encode`; prefix constant `CREDENTIAL_PREFIX = "loc"`), `IdentifiedCaller`,
  `CredentialSource` protocol, `FileCredentialSource`, `register_source`,
  `resolve_caller`, and the `_sources` list. The seam test to mirror:
  `tests/test_api_credential.py::test_second_source_resolves_through_same_entry_point`.
- `the_one/interfaces/web/middleware.py` — `CredentialGateMiddleware._handle_http`
  (resolves cookie then header, stamps `scope[CALLER_SCOPE_KEY]`, else 401),
  `_handle_websocket`, `EXEMPT_PATHS`, `CALLER_SCOPE_KEY = "the_one.caller"`.
- `the_one/interfaces/web/app.py` — `lifespan` (DB init, factory construction,
  `_mcp_pool_shutdown_drain` on shutdown), `app = FastAPI(..., lifespan=lifespan)`,
  `add_middleware(CredentialGateMiddleware)`, `app.mount("/static", ...)`.
- `the_one/db/models.py:MCPSource` — `type: Literal["stdio", "streamable-http"]`,
  `config`, `secrets`.
- `the_one/mcp/transports/streamable_http.py:build_request_headers` — flat
  merge of `config.headers` and `secrets` (OAuth keys filtered), so
  `secrets["Authorization"] = "Bearer agt_…"` is presented on every request.
- `the_one/mcp/_pool.py:_entry_worker` — reads `config._cache.auth_posture`;
  `_evict_all_for_source(source_id)`.
- `the_one/mcp/_tool_provider.py` — `get_tools_for_agent` cache-first path,
  `filter_mcp_tools_by_override`, `_apply_override`.
- `the_one/interfaces/web/api.py` — `list_mcp_sources`, `get_mcp_source`,
  `update_mcp_source`, `delete_mcp_source` (evicts pool, cleans runtime cache,
  deletes row), `_validate_mcp_source_config` (streamable-http requires
  `config.url`), the `test/connect` `_cache` write shape
  (`tools`, `capabilities`, `server_info`, `instructions`, `meta`,
  `protocol_version`, `last_updated`), `create_agent`, `update_agent`,
  `rename_agent`, `delete_agent`, `_agent_response`.
- `the_one/agent/factory.py:AgentFactory.create` — the two built-in tool
  predicates (`ToolConfig.enabled` via `ToolConfigRepository.list()`;
  `config.is_tool_enabled`).
- Studio: `studio/agent-editor.js` (tablist with five tabs, `PANEL_IDS`, the
  per-tab `render*Tab` calls), `studio.js` hash-route tab whitelist
  (`tab === 'general' || … || 'tools'`), `studio.js:fetchMcpSources` (editor)
  vs `fetchMcpSources_` (grid), `studio/mcps-tab.js:renderMcpsTab`,
  `studio/general-tab.js` as the template for a new tab module.
- Browser tests: `tests/browser/test_flow_agent_tabs.py::test_tablist_renders_with_five_tabs`
  (must become six), `tests/browser/test_studio_mcps_tab.py` (attach /
  per-tool toggle patterns), `tests/browser/seeders.py` (`seed_mock_provider`,
  `seed_mock_agent`).
- MCP SDK in the venv: `mcp` 1.28.1 — `FastMCP`, `session_manager`,
  `streamable_http_app()`, `RequestContext.request`.

## Outputs

- `the_one/self_configuration/` (new package): `credentials.py`
  (`SelfConfigurationCredentialSource`, registry load/add/remove, `agt`
  prefix), `surface.py` (FastMCP instance, `MOUNT_PATH`, the two read tools,
  caller → agent resolution with the DD9 refusal), `projection.py` (the two
  projections as pure functions over repositories), `manage.py`
  (enable / disable / reconcile-at-startup / cascade helpers).
- `api_credential.py`: `LocalApiCredential.parse` / `encode` accept a prefix.
- `middleware.py`: source-scoped admission (LD2).
- `app.py`: mount, lifespan wrap, startup reconcile + registry load.
- `api.py`: `GET/POST/DELETE /api/agents/{name}/self-configuration`;
  `list_mcp_sources` filter with `?include_agent_surfaces=1`; `update_mcp_source`
  409 on a marked row; `delete_mcp_source` routes a marked row through disable;
  ownership guard in `create_agent` / `update_agent`; cascades in
  `rename_agent` / `delete_agent`.
- Studio: `studio/self-configuration-tab.js` (sixth tab), `agent-editor.js`
  and `studio.js` wiring, `mcps-tab.js` shows an agent only its own surface
  row.
- Tests: unit (seam, scoping, projections' regression net, refusal,
  enable/disable lifecycle, ownership guard, listing filter, reconcile),
  integration (agent build with the surface attached yields exactly the
  operator-enabled tools, through `filter_mcp_tools_by_override`), browser
  (tab renders; enable → MCPs tab shows the surface with per-tool checkboxes
  that persist).
- Docs: `SECURITY-MODEL.md` (Authentication: second credential source and its
  path scoping; Secrets: per-agent surface credentials), `the_one/agents.md`
  (self-configuration surface contract), `CLAUDE.md` (operator-facing: the tab,
  the two tools, off by default).

## Acceptance Criteria

- [x] **AC1 — off by default.** A freshly created agent and every pre-existing
      agent have no surface row; `GET /api/agents/{name}/self-configuration`
      returns `{"enabled": false}`; the agent's MCPs tab lists no surface.
- [x] **AC2 — enable mints and attaches.** `POST /api/agents/{name}/self-configuration`
      creates exactly one `streamable-http` row named
      `self-configuration (<name>)` with the ownership marker, a loopback URL
      built from `settings.port`, `secrets["Authorization"]` holding a freshly
      minted `agt`-prefixed credential (encrypted at rest, masked in every
      response, **never returned by the enable endpoint**), `_cache.tools`
      populated in-process with the read tools and `_cache.auth_posture =
      "no_auth"`; appends the row id to the agent's `mcp_source_ids`; registers
      the credential. A second POST is idempotent (200, same row, no second
      credential).
- [x] **AC3 — the agent's client actually presents the credential** (DD4's
      "not merely that a mint function exists"): building the agent via
      `AgentFactory.create` with the cache cleared and calling `list_tools`
      through the pool reaches the surface and returns the read tools; the
      request arrived with the `agt` bearer and the gate stamped a caller from
      source `self-configuration`.
- [x] **AC4 — identity and refusal (DD2, DD9).** `resolve_caller("agt_…")`
      yields `IdentifiedCaller(source="self-configuration")` whose identifier
      maps to exactly one agent; after `DELETE .../self-configuration`, the
      same credential no longer resolves (401 at the gate) — and, separately,
      a registry entry whose row has been deleted underneath it, or whose
      owner's `mcp_source_ids` no longer contains it, is refused *inside the
      tool* with an error result naming the surface as disabled. Both refusals
      are asserted, not assumed.
- [x] **AC5 — gate scoping (LD2).** A request bearing an `agt` credential to
      any path other than `MOUNT_PATH/*` — including `/api/agents`,
      `/api/info`, `/`, and `/static/*` — is refused with 403; a WebSocket
      upgrade bearing it is refused; the file credential and session cookie are
      unaffected everywhere (existing gate tests stay green).
- [x] **AC6 — `get_my_configuration` is secret-free by construction.** With
      the agent's provider carrying an API key, its `mcp_overrides` carrying
      `bearer_token`/`headers`/`env`, an attached MCP source carrying secrets,
      and an attached connector carrying a token, the tool's result text
      contains none of those values and only the LD5 fields. The regression net
      is an assertion on the serialized result text, mirroring
      `test_list_returns_masked_secrets`.
- [x] **AC7 — `describe_my_capabilities` reflects the operator's controls.**
      Built-ins excluded by either predicate are absent; MCP tools the operator
      disabled per-agent (`mcp_overrides[<source>].disabled_tools`) are absent
      — verified *through* `filter_mcp_tools_by_override`; the
      self-configuration source itself is listed with its tool names; no
      source config, URL, header, or secret appears in the result text.
- [x] **AC8 — per-tool control through existing machinery** (mission
      criterion 8). With the surface enabled and `describe_my_capabilities`
      disabled via the MCPs tab's checkbox (persisted to
      `mcp_overrides["self-configuration (<name>)"].disabled_tools`), an agent
      build yields only `get_my_configuration` from the surface — asserted via
      `MCPToolProvider.get_tools_for_agent`, not around it.
- [x] **AC9 — read scope is the agent itself.** Two enabled agents: each
      credential's `get_my_configuration` returns its own row and never the
      other's; attaching agent A's surface row to agent B via `PUT /api/agents/B`
      is rejected 422; agent B's MCPs tab does not list A's row.
- [x] **AC10 — admin isolation (DD3).** `GET /api/mcp-sources` omits marked
      rows; `GET /api/mcp-sources?include_agent_surfaces=1` includes them (the
      editor's fetch uses it); `PUT /api/mcp-sources/{id}` on a marked row →
      409; `DELETE /api/mcp-sources/{id}` on a marked row performs the full
      disable (row gone, id removed from the owner's `mcp_source_ids`,
      credential unregistered, pool evicted).
- [x] **AC11 — lifecycle cascades.** `rename_agent` updates the marker and the
      row name and the surface keeps working under the new name;
      `delete_agent` removes the row and unregisters the credential; startup
      reconcile rewrites a stale `config.url` port and loads every marked row's
      credential into the registry.
- [x] **AC12 — Studio.** The agent editor shows a sixth tab, "Self-configuration",
      with an enable/disable control and a status line; enabling from the tab
      makes the surface appear on the MCPs tab with per-tool checkboxes that
      persist; `test_tablist_renders_with_five_tabs` is updated to six;
      hash-route `#studio/agents/<name>/self-configuration` selects the tab.
- [x] **AC13 — clean startup and shutdown.** `make test-unit` green; ruff
      clean; the app starts and stops without the `session_manager` runtime
      error; the loopback-session shutdown WARNING is either eliminated (evict
      marked rows' pool entries before the listener closes) or documented in
      the flight log as accepted.
- [x] **AC14 — docs** per Outputs, including `SECURITY-MODEL.md`'s statement
      that a per-agent credential is confined to the surface path.

## Verification Steps

- AC1, AC2, AC4, AC9, AC10, AC11: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_api.py tests/test_api_credential.py -x --timeout 30`
  (new file uses the `tests/test_db_api.py::client` fixture shape).
- AC3, AC8: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_surface.py -x --timeout 60`
  — spins the real app in-process (the pattern the re-entrancy probe used:
  uvicorn on a free port, `THE_ONE_DATA_DIR` in `tmp_path`) and drives
  `MCPToolProvider.get_tools_for_agent` / `_pool.acquire`.
- AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_credential_gate.py -x --timeout 30`
  (extend with the `agt` scoping matrix).
- AC6, AC7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_projection.py -x --timeout 30`
  — assertions on `json.dumps(result)` text.
- AC12: `make test-browser` (or `scripts/run-tests.sh --lane browser`) on
  `tests/browser/test_flow_agent_tabs.py tests/browser/test_studio_self_configuration_tab.py`.
- AC13: `make test-unit`; `make lint`; `.venv/bin/ruff format --check the_one/ tests/`;
  `THE_ONE_DATA_DIR=<scratch> THE_ONE_PORT=<free> .venv/bin/the-one serve`
  started and stopped, log checked.

## Implementation Guidance

Work in this order; each step leaves the suite green. **Treat AC5's scoping
matrix as an internal go/no-go before step 3**: do not mount the surface until
the gate confines `agt` credentials and cookie/file callers still pass
everywhere.

1. **Credential shape and source** — `api_credential.py`, new
   `the_one/self_configuration/credentials.py`
   - Give `LocalApiCredential.parse` and `encode` a `prefix` keyword defaulting
     to `CREDENTIAL_PREFIX`; add `AGENT_CREDENTIAL_PREFIX = "agt"` in the new
     module. `FileCredentialSource` is unchanged (it parses with the default
     prefix and rejects `agt_` tokens).
   - `SelfConfigurationCredentialSource(name="self-configuration")` with a
     module-level registry `dict[str, tuple[str, str]]` (identifier →
     (source_id, secret)); `resolve` parses with the `agt` prefix, looks up
     the identifier, `hmac.compare_digest`s the secret, returns
     `IdentifiedCaller(identifier=<credential identifier>, source=self.name)`.
     Expose `register(source_id, credential)`, `unregister(source_id)`,
     `source_id_for(identifier)`, `load_from_rows(sources)`, and
     `clear_for_test()`.
   - Register the source once at import of the package's `__init__` **or**
     explicitly in lifespan — pick lifespan (explicit, testable), and guard
     against double registration.

2. **Gate scoping** — `middleware.py`
   - In `_handle_http`, at the existing `if caller is not None:` block
     (~:360-363): `confined = CONFINED_SOURCE_PATHS.get(caller.source)`; if
     `confined is not None and not path.startswith(confined)` → `_send_403`
     (add it to `CredentialGateMiddleware`; today only
     `OriginAllowlistMiddleware` has one, ~:134-147). In `_handle_websocket`,
     after caller resolution and before the scope stamp (~:386-396): a caller
     whose source is in the map is refused outright. **`session` (cookie) and
     `file` callers must be untouched** — `_resolve_cookie` yields
     `IdentifiedCaller(source="session")`, so any check phrased as
     "source is not `file`" breaks the whole web UI; the AC5 matrix includes
     cookie → 200 on every path precisely to catch that. Import the map from
     `the_one/self_configuration/constants.py` (leaf module: constants only)
     so `middleware.py` gains no heavy import. Note `CALLER_SCOPE_KEY` has no
     production reader today; the surface's `_calling_agent(ctx)` becomes the
     first — test it directly.

3. **Surface server** — `the_one/self_configuration/surface.py`
   - `FastMCP("the-one self-configuration", stateless_http=True,
     streamable_http_path="/")`; two tools with the LD5 projections; a
     `_calling_agent(ctx)` helper that reads
     `ctx.request_context.request.scope[CALLER_SCOPE_KEY]`, maps identifier →
     source_id via the registry, loads the row, reads the owner marker, and
     verifies the owner's `mcp_source_ids` contains the row (DD9). Any failure
     → return an error result (`isError`) with a one-line message; never raise
     a stack into the transport.
   - `list_surface_tools()` returning the `_cache.tools` payload shape for LD6
     (name, description, input_schema).

4. **Projections** — `projection.py`: pure async functions taking repositories
   and the agent name; LD5's field lists verbatim; unit-tested in isolation
   with seeded secrets everywhere they can live.

5. **Management** — `manage.py`: `enable(name)`, `disable(name)`,
   `status(name)`, `reconcile_on_startup()`, `cascade_rename(old, new)`,
   `cascade_delete(name)`, `owner_of(source)`, `is_surface_row(source)`,
   `surface_url()`. Enable = mint → create row (marker, URL, secrets,
   `_cache`) → append to `mcp_source_ids` via the store → register. Disable =
   `_evict_all_for_source` → remove from `mcp_source_ids` → delete row →
   unregister. Reuse `MCPSourceRepository` and `SQLiteAgentStore`
   (with the api-module encryptor, per Leg 1).

6. **App wiring** — `app.py`: `app.mount(MOUNT_PATH, surface.streamable_http_app())`
   after the API router; wrap the lifespan body in
   `async with surface.session_manager.run():`; call `reconcile_on_startup()`
   after `init_db`; register the credential source; on shutdown, evict marked
   rows' pool entries **before** `_mcp_pool_shutdown_drain` if that removes
   the probe's DELETE warning (verify; otherwise document).

7. **API** — `api.py`: the three agent endpoints; `list_mcp_sources` query
   param; `update_mcp_source` 409 and `delete_mcp_source` re-route for marked
   rows; ownership guard shared by `create_agent`/`update_agent`; cascades in
   `rename_agent`/`delete_agent`. Every response through `_agent_response` /
   `_mcp_source_response` as today.

8. **Studio** — `studio/self-configuration-tab.js` modelled on
   `general-tab.js`; sixth tab button/panel in `agent-editor.js` (id
   `agent-tab-self-configuration`, `data-tab-id="self-configuration"`,
   `data-testid="tab-self-configuration"`); whitelist entry in `studio.js`;
   editor fetch → `/api/mcp-sources?include_agent_surfaces=1`; `mcps-tab.js`
   filters marked rows to `config.self_configuration.agent === agent.name`
   (create-mode agent: none). The surface row's attach toggle on the MCPs
   tab renders **checked and disabled** with a hint ("managed on the
   Self-configuration tab") — a disabled checked checkbox still matches
   `:checked`, so `collectFormData`'s toggle scan keeps the id in
   `mcp_source_ids`; the per-tool checkboxes beneath it stay fully editable
   (that is the operator's per-capability control). Enabling from the tab
   re-fetches sources and re-renders the MCPs tab so the row appears without
   a reload.

9. **Tests, then docs**, per Verification Steps and Outputs.

## Edge Cases

- **Enable on an agent with no provider** → allowed (the surface reads config;
  a provider is a chat concern), but `describe_my_capabilities` reports
  `provider: null`.
- **Operator renames the row via the API** → blocked by the 409; the row name
  is derived from the agent name and only `rename_agent` changes it.
- **Registry and DB disagree** (row deleted by hand, process restarted) →
  reconcile rebuilds the registry from rows; a credential for a vanished row
  simply no longer resolves.
- **Two processes sharing a data dir** → unsupported already (CLAUDE.md
  single-process assumption); the in-memory registry inherits that posture and
  the leg documents it.
- **`settings.port` differs from the running port** — the desktop launcher's
  `_select_port` (`the_one/interfaces/desktop/shell.py:run_desktop`, ~:512-550)
  may bind a fallback port and uses `sel_port` only locally; `settings.port` is
  never updated. The port *is* known before uvicorn is constructed and
  `Settings` is mutable, so **close it in this leg**: assign
  `settings.port = sel_port` in `run_desktop` immediately after `_select_port`
  resolves (only when this process will serve — the attach-a-window-only path
  runs no lifespan). Add a unit test in `tests/test_desktop_shell.py` that the
  fallback branch updates `settings.port`.
- **Agent's `mcp_overrides` for the surface carry `bearer_token`** → the
  overlay would replace the minted credential on the wire and the gate would
  401 → graceful skip. Reject credential keys on a surface row's override in
  `update_agent` (422) so an agent cannot be handed a foreign credential
  through the override path.
- **Credential rotation via `the-one rotate`** (Mission 20 file credential) →
  unaffected; `agt` credentials are independent. Per-agent revoke/rotate is
  Flight 3.
- **An `agt` credential presented with a session cookie** → the cookie wins
  (resolved first) and is the operator; the credential is ignored. Acceptable —
  a browser never carries an `agt` token.
- **Stateless HTTP and the client's standalone GET SSE** → in stateless mode
  the server never issues a session id and the SDK client's
  `handle_get_stream` returns early when it has none, so no GET is ever sent
  (verified in mcp 1.28.1 by the design review). Stateful fallback remains
  available but is not expected to be needed.
- **`describe_my_capabilities` with an empty `_cache.tools` on some other
  source** → report the source with `tools: []` and `tools_known: false`; do
  not connect.

## Files Affected

- `the_one/api_credential.py` — prefix parameter.
- `the_one/self_configuration/{__init__,constants,credentials,surface,projection,manage}.py` — new.
- `the_one/interfaces/web/middleware.py` — confined-source admission.
- `the_one/interfaces/desktop/shell.py` — `settings.port = sel_port` after
  `_select_port`.
- `the_one/interfaces/web/app.py` — mount, lifespan wrap, reconcile, register.
- `the_one/interfaces/web/api.py` — new endpoints, listing filter, guards,
  cascades.
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js` — new.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`,
  `.../studio.js`, `.../studio/mcps-tab.js` — wiring and filtering.
- `tests/test_self_configuration_{api,surface,projection}.py` — new;
  `tests/test_api_credential.py`, `tests/test_credential_gate.py`,
  `tests/test_desktop_shell.py`, `tests/browser/test_flow_agent_tabs.py` —
  extended;
  `tests/browser/test_studio_self_configuration_tab.py` — new.
- `SECURITY-MODEL.md`, `the_one/agents.md`, `CLAUDE.md` — docs.

## Risk Checks

- **Schema**: none. The surface is a row in an existing table with an existing
  `type`; the marker lives in `config` JSON. No migration.
- **State-machine reachability**: enabled ⇔ row exists ∧ id ∈ owner's
  `mcp_source_ids`. Lower layers that could foreclose it: `delete_mcp_source`
  (re-routed), `update_agent` dropping the id from `mcp_source_ids` (that is
  a legitimate operator detach — treat as *disabled but row present*; the DD9
  check refuses, and `status` reports `enabled: false, orphaned_row: true`;
  the next enable reuses the row). Tests pin all three states.
- **Cache freshness**: two caches. (1) Credential registry — source of truth
  is the marked rows; rebuild triggers are startup reconcile, enable, disable,
  delete-source, delete-agent; acceptable staleness zero, met because every
  mutation path is in-process. (2) `_cache.tools` on the row — source of truth
  is the FastMCP instance's tool list; rebuild trigger is enable (and Leg 3
  must re-run it when the write tools are added — recorded for Leg 3);
  staleness beyond that is impossible because the tool set is code.
- **Interface changes**: `LocalApiCredential.parse/encode` gain a keyword with
  a default (callers: `api_credential.py`, `interfaces/cli.py` rotate path,
  tests — grep `.parse(` / `.encode(`); `CredentialGateMiddleware` behaviour
  changes only for non-file sources (none exist before this leg);
  `list_mcp_sources` response narrows for marked rows only.
- **Security-sensitive**: the whole leg. Highest-risk item is LD2 — a missed
  path check turns an agent credential into a platform credential. The
  scoping test matrix in AC5 is the net.

## Citation Audit

Checked against the working tree on `flight/01-self-configuration-surface`
with Leg 1 landed (uncommitted), 2026-08-24:

- `api_credential.py` — `LocalApiCredential.parse` :91 / `encode` :106
  (prefix hardcoded via `CREDENTIAL_PREFIX` :42), `IdentifiedCaller` :123,
  `CredentialSource` :379, `FileCredentialSource` :396, `_sources` :426,
  `register_source` :429, `resolve_caller` :437 — live.
- `middleware.py` — `EXEMPT_PATHS` :185, `SESSION_COOKIE_NAME` :188,
  `CALLER_SCOPE_KEY` :193, `_handle_http` :307 (stamps scope then
  `await self.app`), `_handle_websocket` follows — live.
- `app.py` — `lifespan` :125, `_mcp_pool_shutdown_drain()` :316,
  `app = FastAPI(...)` :359, `add_middleware(CredentialGateMiddleware)` :377,
  `app.mount("/static", ...)` :378, `include_router` :379 — live.
- `api.py` (post-Leg 1) — `_agent_store` :78, `_agent_response` :87,
  `_merge_preserved_mcp_credentials` :128, `# ── Agents` :596, `delete_agent`
  :764, `rename_agent` :833, `# ── Knowledge Bases` :883,
  `list_mcp_sources` :1423, `update_mcp_source` :1474, `delete_mcp_source`
  :1552, `rotate_encryption_key` :4914 — live.
- `db/models.py:MCPSource` `type: Literal["stdio", "streamable-http"]` — live.
- `db/repositories.py` — `SQLiteAgentStore.__init__` :122 — live.
- `mcp/_overrides.py:MCP_OVERRIDE_CREDENTIAL_KEYS` :112 — live.
- `mcp/_pool.py` — `_entry_worker` :148 (`auth_posture` read :203),
  `_evict_all_for_source` :303, `acquire` :458 — live.
- `mcp/_tool_provider.py` — `filter_mcp_tools_by_override` (~:80-105),
  `_apply_override` (~:107-190), `get_tools_for_agent` :219 with the
  cache-first branch (~:260-330) — live.
- `mcp/transports/streamable_http.py:build_request_headers` — live.
- `agent/factory.py:AgentFactory.create` :222 (predicates at the
  `ToolConfigRepository.list()` / `config.is_tool_enabled` lines) — live.
- Studio: `agent-editor.js` tablist :92-113, panels :116-127, `render*Tab`
  calls :154-177; `studio.js` whitelist :162, `fetchMcpSources_` :642,
  `fetchMcpSources` :1011; `mcps-tab.js:renderMcpsTab` — live.
- Tests: `tests/test_flow_agent_tabs.py::test_tablist_renders_with_five_tabs`
  :68 (`to_have_count(5)`), `tests/test_api_credential.py::test_second_source_resolves_through_same_entry_point`
  :141, `tests/browser/seeders.py::seed_mock_agent` :83 — live.
- MCP SDK 1.28.1 — `FastMCP(stateless_http=..., streamable_http_path=...)`,
  `session_manager` property, `streamable_http_app()`,
  `RequestContext.request` (populated in stateless mode), client
  `handle_get_stream` early-return without a session id — verified in the
  venv by the design review.
- `middleware.py:_resolve_cookie` ~:400-423 yields `source="session"`;
  `OriginAllowlistMiddleware._send_403` ~:134-147; `desktop/shell.py:run_desktop`
  `_select_port` at ~:513, `uvicorn.Config` at ~:550 — verified by the design
  review.

Design review (2026-08-24, Developer/Sonnet): approve with changes — LD2's
wording corrected from "source is not `file`" to the confined-source map
(the literal wording would have refused the session cookie everywhere);
desktop-launcher port write-back pulled into scope; stateless-GET edge case
and MCPs-tab toggle semantics tightened.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
