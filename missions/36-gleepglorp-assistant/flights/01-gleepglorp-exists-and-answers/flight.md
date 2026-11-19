# Flight: GleepGlorp exists and can answer

**Status**: completed
**Mission**: [GleepGlorp, the In-App Assistant](../../mission.md)

## Contributing to Criteria

- [ ] **GleepGlorp is ready once its model is chosen.** In full: the settings
      page, the setup state, the on/off switch, web access, memory, retention
      and the purge pass.
- [ ] **Nothing changes without the operator's click.** Partly: GleepGlorp's
      Flight 1 tool set is read-only plus its own notes, and the allowlist test
      over its registered tools lands here. Flights 2 and 3 extend the
      allowlist with the proposal and form-fill tools.
- [ ] **Secrets never pass through GleepGlorp.** Partly: every read is masked
      (proved against a seeded secret in every corpus), and GleepGlorp steers a
      secret or sign-in to the right page with a link. Forms and proposals come
      in Flights 2 and 3.
- [ ] **GleepGlorp sticks to the app.** Mostly: it declines off-topic requests,
      has only its own tools, and cannot be bound to a connector or own a
      routine. The "Check this" flag on proposals and form fills comes later.
- [ ] **The Default agent is gone.** In full.
- [ ] **Quality is measured on every default eval model.** Partly: the
      GleepGlorp scenario set and baseline for questions about the app, secret
      handoffs and declines, the Haiku pass bar, small-model readings and the
      tool-count measurement. Later flights extend the set.

---

## Pre-Flight

### Objective

Give the app its built-in assistant and take the old Default agent away.
GleepGlorp gets its settings (model, on/off, web access, memory, chat
retention) on a Settings page of its own, a build path that needs no agents
row, a place first in the agent picker and in Chats, and a setup state until a
model is chosen. It gets a shipped prompt (shown read-only in Settings ›
Prompts) and a small read-only tool set: a masked view of the app's
configuration and status, a shipped app guide looked up by topic, its own
notes, and web search and fetch. Its quality is measured by a new eval scenario
set with a recorded baseline. The legacy `default` agent, its stored row and
every chat with no agent are deleted, and "GleepGlorp" and "default" become
reserved agent names. Squawk 0383 (the unit tier at its time target) is folded
in first, so the flight's new tests have room.

### Open Questions

- [x] A hidden agents row, or no row? → No row (operator, 2026-11-18, no
      objection to the Flight Director's recommendation). See DD1.
- [x] Where do GleepGlorp's notes live, given every agent-keyed table has a
      foreign key to `agents(name)`? → A table of its own. See DD4.
- [x] Where is the Settings page, and how does it save? → Its own "Assistant"
      group at the top of the Settings nav; Cancel and Save (operator,
      2026-11-18). See DD7 and the Mockups.
- [x] How does GleepGlorp appear in the agent picker? → Its own "Built in"
      group on top (operator, 2026-11-18). See DD8.
- [x] What does a GleepGlorp chat show with no model? → Guidance in the
      new-chat card, the message box disabled (operator, 2026-11-18). See DD8.
- [x] What do the CLI and `/api/selftest` do without the Default agent? → Use
      GleepGlorp (operator, 2026-11-18). See DD3.
- [x] Default state of the switches? → All on (operator, 2026-11-18). See DD2.
- [x] A HAT leg? → Yes, closing this flight (operator, 2026-11-18).
- [x] Squawk 0383? → Folded in as the first leg (operator, 2026-11-18).
- [x] High-fidelity screens? → Approved (operator, 2026-11-18), see the
      Mockups section's board.
- [x] Where does a bare `#settings` land? → Appearance, unchanged
      (2026-11-18). See the Mockups section.
- [x] Do chat links to app pages work? → Yes. The chat markdown renderer keeps
      a same-origin `#` href (`markdown.js::safeHref`), opens it in the same
      tab (only `http(s)` links get `target=_blank`), and `App.nav`'s
      bubble-phase `a[href^="#"]` interceptor routes it through the leave
      guard. See DD6.
- [x] What does "no search backend" mean? → A keyed engine whose required
      fields are empty. Keyless DuckDuckGo is the default and always counts as
      configured. See DD5.

### Design Decisions

**DD1. GleepGlorp is not an agents row; its chats use the reserved name "GleepGlorp"**
- Choice: GleepGlorp has no row in `agents`. Its chats are stored with
  `chat_sessions.agent_name = "GleepGlorp"` (the canonical spelling; the column
  has had no foreign key since v5). That name is the chat marker the mission
  asks for: nothing else can produce it once DD10 reserves it. The constant
  lives in one Python module and one JS module.
- Rationale: with no row, every agent route (edit, rename, delete, rules,
  notes, routines, self-configuration, MCP credentials) answers 404 for
  GleepGlorp by construction, so a route someone forgets to guard fails closed.
  A hidden row would make notes and retention free but needs a guard on every
  current and future agent route, and one missed guard lets the operator, or an
  agent through self-configuration, edit GleepGlorp.
- Trade-off: notes (DD4), retention (DD9), provider usage (DD2) and the model
  pre-load each need an explicit GleepGlorp path.

**DD2. Settings live in `app_metadata` under one key, with one route**
- Choice: one JSON value under the key `gleepglorp`, a pydantic model on the
  `time_zones.py` pattern (`SETTING_KEY`, `model_validate_json`, falls back to
  defaults on a bad value): `enabled` (default true), `provider_config_id`
  (default null), `model` (default null), `web_access` (default true),
  `memory` (default true), `retention_days` (default 30, 1-365, the same range
  as `AgentConfig.chat_history_retention_days`). Routes: `GET /api/gleepglorp`
  returns the settings plus a derived `state`: `off`, `needs_model` (no
  provider or no model), `provider_missing` (the stored provider no longer
  exists) or `ready`. `PUT /api/gleepglorp` takes the whole settings object;
  an unknown provider is a 422 on `loc ["provider_config_id"]`, and other
  errors use the project's 422 list shape.
- Provider usage: deleting a provider GleepGlorp uses is refused with the same
  409 as a provider an agent uses (`api.py` provider delete, `list_by_provider`),
  `GET /api/providers/{id}/agents` (`api.py` ~:6378) includes GleepGlorp, and
  `App.usage.providerAgents` (today a pure function of the agents list) takes
  GleepGlorp's settings as a second input, so the provider row reads "used by
  GleepGlorp".
- Rationale: the mission's planning decision. One key keeps the setting atomic.
  Refusing the provider delete matches the existing rule, so GleepGlorp never
  silently loses its model.
- Trade-off: the provider-usage code reads two places.

**DD3. `AgentFactory.create` splits into loading a config and a shared build**
- Choice: `create(name)` keeps its signature for every caller (web, connectors,
  CLI, selftest). Inside, it either loads a stored agent's config, or for the
  reserved name builds GleepGlorp's in memory from its settings, then runs one
  shared `_build` step: provider resolution, the tool registry, tool exposure
  (sortie 11), prompt composition, notes binding and `bind_agent`. GleepGlorp's
  build passes its own tool inputs (DD5) and its own prompt layers (DD6), and
  never the operator's tool whitelist, rules, persona, secrets, MCP servers,
  knowledge bases, routines or connector tools. The branch matches the exact
  spelling `GleepGlorp`, so `gleepglorp` stays an unknown agent. A disabled
  GleepGlorp, or one with no model, raises a GleepGlorp-specific error that the
  session paths turn into GleepGlorp degraded statuses (DD8), never the
  agent-wording "provider missing" text. In Leg 3 (not Leg 2, so no leg leaves
  a broken tree), `_default_config` and the `"default"` entry in `list_agents`
  are removed and `create`'s default argument becomes the GleepGlorp name, so
  the CLI's `the-one chat` and `/api/selftest` use GleepGlorp (operator
  decision); both report a GleepGlorp that is off or has no model in plain
  words, never a traceback or a 500 (the CLI catches only `ValueError`,
  `cli.py:72-79`, so GleepGlorp's error subclasses it or is caught there).
  `/api/selftest`'s tool check asks for `read_file` (`app.py` ~:3392-3404),
  which GleepGlorp does not have, so the check changes to `current_time`. The
  web paths that auto-created a no-agent chat (`/api/chat` with no agent, the
  WebSocket auto-create, `app.py` ~:3443, ~:3563, ~:3804) require a named agent
  and refuse with their existing error shape. All of this lands in Leg 3,
  together with every app.py and CLI NULL→`default` path (DD10's list), so the
  fallback and its callers go in one change.
- In Leg 3 GleepGlorp's synthesized config has `notes_enabled=False` and no web
  tools: the Memory and Web access settings are stored and shown but take
  effect only in Leg 5, when the GleepGlorp notes store and web wiring land
  (otherwise the agent notes repository would raise `KeyError` on the first
  save, `db/repositories.py` ~:2462-2468). Leg 3 ships a minimal allowlist test
  pinning `{search_tools, continue, current_time}`, so the "never the
  operator's whitelist" boundary is pinned from the first leg that builds
  GleepGlorp. The Leg 3-4 placeholder prompt does not go through the platform
  layer of `build_system_prompts`, so `_platform_prompt_pins.py` stays green.
- Rationale: one entry point keeps restore, model pre-load and the session
  paths working without a parallel builder. The shared `_build` means
  GleepGlorp gets tool exposure and the notes binding for free (survey
  recommendation).
- Trade-off: `create` is on every chat's hot path, so the refactor is guarded
  by the existing factory tests, unchanged, plus GleepGlorp's own.

**DD4. GleepGlorp's notes have their own table behind the same notes tools**
- Choice: a new `gleepglorp_notes` table (schema v53, DD10) with the
  `agent_notes` columns and no foreign key, and a next-number counter that only
  goes up (kept beside the settings or in a one-row table), matching
  `notes_next_number`; `MAX(number) + 1` would reuse a forgotten note's number.
  A repository with the same interface as `AgentNoteRepository` (list if
  enabled, save, update, forget, clear), selected through the notes tools'
  `_repo()` seam (`notes/tools.py:113`), which becomes an instance method keyed
  on the tool's bound agent name (today a `staticmethod` with no owner), and
  through the prompt builder. The memory switch is
  GleepGlorp's `memory` setting. Routes for the Settings page: `GET
  /api/gleepglorp/notes`, `DELETE /api/gleepglorp/notes/{id}`, `DELETE
  /api/gleepglorp/notes`. Note text is rendered with `textContent` only, as on
  the agent Notes tab, and a note written after untrusted content carries the
  warning-triangle flag.
- Rationale: rebuilding `agent_notes` without its foreign key would touch every
  agent's notes path to serve one non-row owner. A separate table keeps the
  agent path unchanged.
- Trade-off: two notes tables with the same shape. The repository interface
  keeps them from drifting.

**DD5. GleepGlorp's Flight 1 tools: read the app, read the guide, notes, web**
- Choice: exactly these tools. GleepGlorp's build seeds every one of them into
  the starting set whatever the tool-exposure decision says, because exposure
  depends on the provider reporting a context window (`factory.py` ~:655-685)
  and on `THE_ONE_TOOL_EXPOSURE_FRACTION`, so the mock provider,
  `openai-compatible` servers or exposure turned off would otherwise leave its
  tools reachable only through discovery. The core always sends
  `search_tools` and `continue` (`agent/core.py:126`, `:224`; `core.py` is
  frozen and not changed), so the allowlist names both explicitly, plus
  `current_time` (whitelist-exempt for every agent today, kept: it pairs with
  the date line):
  - `read_app_config(kind, name?)`: one tool with an enum of kinds, so a small
    model chooses from one schema rather than a dozen: `overview` (counts and
    names of everything, GleepGlorp's own state), `agents`, `agent`,
    `mcp_servers`, `mcp_server` (including connection status and tool names
    from `_cache`), `providers`, `provider` (including its model list when
    cached), `knowledge_bases`, `knowledge_base` (including index status),
    `connectors`, `connector`, `routines` (for a named agent), `secrets`
    (names, descriptions and allowed tools only), `built_in_tools`, `settings`
    (time zone and knowledge indexing; the theme lives in the browser and is
    not readable). `agent` includes the system prompt, description, model,
    tools and overrides, rules, attached MCP servers and knowledge bases, and a
    count of its notes, never the notes' text (they can hold personal facts).
    Never chats, files or logs.
  - `get_app_guide(topic)`: DD6. The topic list is in the tool description.
  - The notes tools, when `memory` is on (DD4).
  - `fetch_url` and `web_search`, when `web_access` is on, under the
    operator's existing `WebConfig` / `WebSearchConfig` limits. Each is removed
    when the operator has switched that tool off for the whole app. `web_search`
    is not offered when the configured engine is a keyed one whose required
    fields are empty (`searxng_base_url`; `google_pse_api_key` +
    `google_pse_cse_id`; `brave_api_key`; `tavily_api_key`), and the Settings
    page says so.
- *(Amended in flight, Leg 5 design review, 2026-11-18: GleepGlorp's reads use
  separate whitelist views in `the_one/gleepglorp/views.py`, built field by
  field from repositories, with `kind` reduced to ten values and `name`
  optional; the API helpers are not moved. See the flight log. The original
  text follows.)* The read views come from the same functions the API uses. The response
  helpers in `api.py` (`_agent_response`, `_provider_response`,
  `_mcp_source_response` with `_mask_secrets`, `_connector_response`, the
  secrets `_response`, the settings responses) and the two inline views
  (knowledge bases, the tool-config list and detail) move into one shared
  module that both the routes and the tool import. The move is done first as a
  pure move with re-exports from `api.py` (the project's canonical-import plus
  convenience-re-export pattern), so routes and tests are untouched; the new
  module never imports from `interfaces/web` (`_agent_response` needs
  `_resolve_kb_tool_names` and `_agent_notices`, which move with it).
- GleepGlorp's views mask harder than the API's. The API shows a 4-character
  tail of a secret of 12 or more characters (`_emit_mask`, `api.py`
  ~:3264-3272), returns the values of headers and env vars the operator marked
  not sensitive (`_agent_response` `plain_names`, ~:288-321), and passes MCP
  `config` through (`_mcp_source_response`, ~:3419). Everything GleepGlorp reads
  goes to a third-party model, so its views take a `tail=False` option (no
  tail), show header and env names but never values, and show an MCP address
  without its query string or user info. Command arguments are shown as they
  are (GleepGlorp needs them to help); a token placed in an argument is a
  residual risk recorded in `SECURITY-MODEL.md`.
- An allowlist test pins GleepGlorp's registered tool names per settings
  combination. A secret-parity test stores a known value of 16 or more
  characters in every masked slot (provider key, plan OAuth secrets, MCP
  headers and env, per-agent MCP credentials, connector secrets, tool-config
  secret fields, Library secret values, the self-configuration credential) and
  asserts that no `read_app_config` result for any kind contains the value or
  its last four characters.
- Taint: `get_app_guide` joins `TRUSTED_TOOL_NAMES` (shipped text).
  `read_app_config` stays untrusted, the fail-closed default in
  `the_one/agent/taint.py`, because configuration text can be written by agents
  (self-configuration) or come from MCP servers. Flight 2 revisits the
  granularity when proposals carry the flag.
- Rationale: few tools for small models; masking by construction rather than a
  second set of redaction rules.
- Trade-off: a large enum in one schema. The tool-count and schema-size
  measurement (Leg 6) decides whether it needs splitting.

**DD6. The shipped prompt and the app guide are app files, written for people**
- The prompt: GleepGlorp's system prompt is its own text, not the agent
  platform prompt: who it is, what it may and may not do (app support only,
  every change is the operator's, never a secret, decline and point to the
  operator's agents, never promise abilities it does not have), how to use its
  tools, and how to send the operator to a
  page: a markdown link to an app route that lands on a page (for example
  `[New model provider](#library/providers/~new)` or
  `[GleepGlorp settings](#settings/gleepglorp)`), which opens in place through
  the router and the leave guard. A bare `#library/{group}` is an alias that
  redirects to the Library start page, so it is never used. Pasted keys: if the operator pastes something
  that looks like a key, GleepGlorp does not repeat it and tells them where it
  belongs. The prompt is followed by the notes layer (when memory is on) and
  the date line. No rules, persona, secrets or visuals layers. The text lives
  in one Python module with sections like `platform_prompt.py`'s. `GET
  /api/info` gains a `gleepglorp_prompt` field, and Settings › Prompts shows it
  as its own read-only block. Other agents' prompts do not change, and
  `tests/_platform_prompt_pins.py` proves it.
- The guide: one markdown file per topic in a package directory (for example
  `the_one/gleepglorp/guide/`), in plain help-text English a person can read,
  covering at least: the app's map, agents, tools and overrides, rules and
  notes, MCP servers (local command vs HTTP, headers, sign-in, per-agent
  credentials), model providers (the Claude variants, Ollama), knowledge
  bases, connectors, routines, secrets, settings and GleepGlorp itself. The
  files are package data (`pyproject.toml`), so every installer carries them.
  `get_app_guide` returns one topic, or the topic list for an unknown topic.
  A drift test fails when a guide link names a route the router does not serve,
  or an alias route that redirects (checked against the route grammar,
  `App.settingsPages` and the Library groups), or a topic the guide does not
  have.
- Rationale: the mission's knowledge-sources decision. Written for people, so
  Help pages can reuse it later.
- Trade-off: the guide is prose that can go stale in ways the drift test cannot
  see. The project convention in the mission covers that.

**DD7. The Settings page is "GleepGlorp" in a new "Assistant" group**
- Choice: a new top group "Assistant" in `App.settingsPages` with one page,
  section `gleepglorp`, label "GleepGlorp", route `#settings/gleepglorp`. Built
  on the library as an `editorShell` page with Cancel and Save in its header,
  like Knowledge indexing: a Model section (provider select and model picker,
  reusing the agent editor's model picker if it fits, and a note that small
  local models may struggle), a Behavior section (switches for GleepGlorp, Web
  access and Memory, and "Keep chats for N days"), and a Memory section (the
  notes list with delete and Clear all, which act at once and are not part of
  Save; Clear all asks through the confirm dialog). The page joins `App.nav`'s
  leave guard. The Jump-to palette lists it through `App.settingsPages`.
- Rationale: operator choice from the mockups.
- Trade-off: the tests that pin the Settings table and the nav groups change.

**DD8. GleepGlorp in the picker, Chats, the pane and the drawer**
- One client source: `GET /api/gleepglorp` (DD2) read through `App.store` as a
  new single-object collection or a small `App.gleepglorp` module (leg design
  picks), invalidated on Save and pushed on change (DD11). It lands in Leg 3,
  which needs it for the Settings page and `App.usage.providerAgents`
  (`store.js` ~:147 returns a count, so the provider row's wording in
  `library-pane.js` ~:240 changes to name GleepGlorp).
- One client helper answers "which agent is this?" for the five places that
  test membership in the agents list today (`session-flow.js` `agentListed`,
  `socket.js` `agentMayExist`, `chat.js` → `chatPane.agentInfo`, the
  transcript's step-limit link at ~:384-399, the drawer's `describe`). It
  returns a kind (`agent`, `gleepglorp` or unknown) and a settings href
  (`#agents/{name}` or `#settings/gleepglorp`), so no path ever builds
  `#agents/GleepGlorp`.
- The picker: a "Built in" group above "Recently used" with one row,
  GleepGlorp, and the description "Help setting up the app" (or "Needs a model"
  when its state is `needs_model` or `provider_missing`). It is never in
  Recently used or All agents, and is hidden when `enabled` is off. Search
  matches it by name and description.
- The setup state: picking GleepGlorp with no model opens the usual pending
  new-chat card with a warning line, "GleepGlorp needs a model first.", and a
  button, "Choose a model for GleepGlorp", that goes to `#settings/gleepglorp`.
  If there are no providers at all, the line says to add a model provider first
  and links to `#library/providers/~new`. The message box is blocked through
  the composer's existing blocked state.
- Chats: a GleepGlorp chat's row shows "GleepGlorp" as its agent. The header
  reads "with GleepGlorp". The drawer gets a new kind for GleepGlorp: its facts
  (model, provider, web access, memory with its note count, chat retention),
  "What it can use", the line "GleepGlorp can't change anything by itself.",
  and "Open GleepGlorp settings" instead of "Open agent settings".
- Degraded states: new session statuses for GleepGlorp, `gleepglorp_off`,
  `gleepglorp_needs_model` and `gleepglorp_provider_missing`, each shown as the
  warning banner with its own sentence ("GleepGlorp is turned off. Turn it on
  to continue this chat.", "GleepGlorp needs a model.", "GleepGlorp's model
  provider was removed.") and an "Open GleepGlorp settings" button, and a
  blocked composer. Never the agent "provider missing" banner
  (`session-state.js` ~:57, `chat.js` ~:471) and never the deleted-agent notice.
- Jump-to: GleepGlorp is a candidate of its own kind (not `kind: 'agent'`,
  whose href is `#agents/{id}`, `jump-to.js` ~:129, ~:269) marked "Built in",
  that opens `#chats/~new/GleepGlorp`; the Settings page is a candidate through
  `App.settingsPages`. GleepGlorp is not in the empty query's recent-agents mix,
  matching the picker.
- A direct `#chats/~new/GleepGlorp` while GleepGlorp is off shows the new-chat
  card with "GleepGlorp is turned off." and the settings button, the same
  pattern as the setup state, with the composer blocked.
- Rationale: operator choices from the mockups. One helper so a sixth
  membership check cannot drift.

**DD9. Retention covers GleepGlorp chats**
- Choice: `retention.run_purge_sweep` gets one extra pass after its per-agent
  loop: `delete_older_than("GleepGlorp", cutoff)` with GleepGlorp's
  `retention_days`, its ids joining `all_ids` so live sessions are evicted.
  GleepGlorp's notes are not purged by age, as agent notes are not.
- Rationale: the mission criterion. The existing sweep is name-keyed and works
  for any string.

**DD10. Retiring the Default agent: one schema step, reserved names, and a startup rename**
- Schema v53 (irreversible, operator decision: nothing is kept). Agent names
  are case-sensitive (`agents.name TEXT PRIMARY KEY`, `schema.py:53`), so a user
  agent called `Default` is a different agent and is untouched here (the
  startup rename handles it):
  - delete the `agents` row named exactly `default`, so its rules, notes,
    routines, revisions and tool cache cascade (the migration connection runs
    with `PRAGMA foreign_keys=ON`, and the migration test asserts the cascaded
    rows are gone, not only the agent row);
  - delete that agent's self-configuration MCP row (the surface row whose
    marker names `default`; `agent_external_credentials` cascades);
  - remove exactly `default` from every connector's `default_agent` and
    `channel_map`;
  - delete every chat whose `agent_name` is NULL or exactly `default`;
  - delete chats named exactly `GleepGlorp` only when no agents row has that
    name (left over from a deleted user agent); a live agent's chats are carried
    by the startup rename below;
  - create `gleepglorp_notes` and its counter (DD4).
- Reserved names: an agent-only check beside `naming.py::check_name` refuses
  `GleepGlorp` and `default` in any letter case with the naming rule's 422
  (`loc ["name"]`, a plain sentence). It is called on agent create, agent
  rename and the legacy JSON import. The import check is load-bearing:
  `migrate_json_to_sqlite` runs on every startup (`db/migration.py:15`), so
  without it a leftover `default.json` would bring `default` back after v53.
  Connector create and update refuse either name in `default_agent` or a
  `channel_map` value with a 422, and `connectors/inbound.py` drops a message
  bound to either name before `resolve_session` (~:404), so no connector chat
  row named `GleepGlorp` is ever created. The routines guards
  (`routines/service.py:486`, `routines/tool_provider.py:24`,
  `routines_api.py` `_DEFAULT_AGENT`) become reserved-name checks that also
  refuse GleepGlorp. `tests/test_api_name_rule.py` classifies the changes.
- `start_session` (`app.py:3608`): in Leg 2 its `default` refusal becomes the
  reserved-name rule (refuses both names in any case). In Leg 4 it admits the
  exact spelling `GleepGlorp` and still refuses `default` in any case and every
  other spelling of GleepGlorp (`gleepglorp` stays an unknown agent).
- Startup rename: an agent-only predicate used by `db/name_repair.py`'s
  `_repair_agents` (not the shared `_is_bad`, which serves all four kinds, so a
  provider or MCP server called "Default" is untouched) flags a stored agent
  whose name, `casefold()`ed, is `default` or `gleepglorp`, and renames it once, with
  the reserved names in `taken` so it gets a suffix ("Default 2",
  "GleepGlorp 2") rather than an unchanged name. Rename carries its chats,
  connectors and cascaded tables as today.
- `default` special cases to remove or convert (the full list; leg design
  re-checks lines). The factory fallback and its app.py and CLI callers (the
  `factory.py` entries, `_create_session`'s NULL normalization, restore, the
  pre-load and self-configuration `or "default"` paths, `cli.py`, selftest and
  the auto-create paths) go together in Leg 3; Leg 2 takes the rest. Python: `factory.py` `create` default, `list_agents`,
  `_load_config` / `_default_config` (Leg 3, DD3); `app.py` `_create_session`'s
  NULL normalization (~:1765), restore (~:1869), the self-configuration pending
  registry keyed on `"default"` (~:2953-2959, ~:3043), `start_session`'s refusal
  (~:3608, becomes the reserved-name rule); `api.py` `_session_notes_map`
  (~:2155, ~:2165); `cli.py:72`; the routines guards above. JS:
  `agent-picker.js` `liveAgents`; `agent-drawer.js` (~:275-292, :537, :622-624,
  :716); `chats-list.js:118`; `chat-pane.js` (:24, :55, :99); `jump-to.js`
  (:31, :138, :174); `session-flow.js:249`; `transcript.js:344`;
  `routines-tab.js:67`; `self-config-routines.js:45`. Every "Default agent"
  string goes, with the browser tests that pin it. The connector editor's
  "Default agent" field label (a connector's fallback agent) is a different
  concept and stays.
- Rationale: one hard-to-reverse step, in a leg of its own.
- Trade-off: an operator on an older version loses their no-agent chats at
  upgrade. Accepted (operator, the only user).

**DD11. Open pages follow a settings change**
- Choice: a Save on the GleepGlorp page pushes a `gleepglorp_changed` frame
  (the `sessions_changed` pattern: to every socket, coalesced) carrying the new
  `state`. An open picker, pending chat or drawer re-reads the client source,
  so a chat that was blocked on "needs a model" unblocks without a reload. A
  client with a GleepGlorp chat open re-joins it on the frame (the
  `session_updated` pattern), because a joined socket otherwise keeps the
  agent it was built with (`app.py` ~:1820-1825). The server also refuses a
  GleepGlorp turn while GleepGlorp is off or has no model, with the matching
  degraded status (DD8), so a stale tab cannot use it. The check sits in the
  turn handler and reads the settings per turn, not the agent cached on the
  session. Both land in Leg 4.
- Rationale: the HAT's second-window step; the settings page and the chat are
  often open in different windows.

**DD12. Evals: a GleepGlorp scenario set with its own builder, and a gated leg**
- Choice: a scenario key `agent.builder = "gleepglorp"`. `_seed` writes
  GleepGlorp's settings to `app_metadata` instead of an agents row, `run_once`
  builds through `AgentFactory.create("GleepGlorp")` (still under
  `provider_patch`), and the saved-notes read uses the GleepGlorp notes table.
  The set lives in `evals/gleepglorp/scenarios`, with its baseline at
  `evals/baselines/m36-gleepglorp.json`. Scenarios cover: what a page or
  concept does (guide lookup, correct answer), what is configured now (the read
  tool, no secret in the reply), a request that needs a key or a sign-in (a link
  to the right page, the key not repeated), a pasted key, off-topic requests
  (declined, pointed to the operator's agents) and an injected instruction in a
  fetched page (not followed). New checks: `reply_links_to_route` (accepts only
  routes that land on a page, never an alias) and `no_seeded_secret_in_reply`;
  the existing `tool_called`, `judge` and `reply_not_matches` cover the rest.
  The harness turns `web_search` off app-wide (`evals/harness.py` ~:75, ~:319),
  so GleepGlorp evals run without search; the fetched-page scenario uses
  `fetch_url` against a local fixture. The tool-count and schema-size reading
  is taken both with and without `web_search`.
- External sessions are re-checked, not trusted from planning: the plan token
  and Ollama with `qwen3-4b` and `lfm3` are checked at the start of every
  round, not once per leg.
- The leg is shaped for an operator gate (Mission 35's lesson): the measured
  prompt text is committed before each round, the leg declares a round budget
  (at most 4 rounds of n=20 on the default models), a stop rule (stop when
  Haiku clears the bar, or after the budget, and report), and a must-keep list
  (the limits, the secret rule and the link format are never trimmed for
  size). The operator sets the Haiku pass bar from the first full round. The
  tool-count and schema-size reading (DD5) is taken in the same leg.
- Rationale: the mission's quality criterion and its evals constraint.

**DD13. The HAT's apparatus is checked by the crew first**
- Choice: before the operator's HAT walk, the crew runs every HAT step's setup
  against a scratch instance (port 8490 or higher, scratch data directory) and
  records that each state appears: a fresh install with no providers, a
  provider with no GleepGlorp model, a ready GleepGlorp, a GleepGlorp turned
  off, and a second window open on a GleepGlorp chat. The HAT's real model
  provider is re-checked at this point, not trusted from planning. Mission 35
  lost operator time in every flight to HAT setups that had not been checked.

### Mockups (operator-approved, 2026-11-18)

The Settings page (DD7):

```
SETTINGS             | GleepGlorp                       [Cancel] [Save]
 ASSISTANT           | The built-in assistant that helps you
  GleepGlorp  <      | set up and tune the app.
 GENERAL             |
  Appearance         | MODEL --------------------------------------
  Date and time      |  Provider  [ Claude Plan (OAuth)        v ]
  Prompts            |  Model     [ claude-haiku-4-5           v ]
  Encryption         |  Small local models may struggle.
 DEFAULTS FOR AGENTS |
  Built-in tools     | BEHAVIOR -----------------------------------
  Knowledge indexing |  GleepGlorp      (on)  Help button and Chats
                     |  Web access      (on)  Search, read pages
                     |  Memory          (on)  Keep notes about you
                     |  Keep chats for  [ 30 ] days
                     |
                     | MEMORY ------------------------ [Clear all]
                     |  Prefers local models     Nov 18  [x]
                     |  /!\ Uses GitHub MCP...    Nov 18  [x]
```

The agent picker (DD8):

```
+ New chat ------------------------------+
| [ Search agents...                   ] |
| BUILT IN                               |
|  * GleepGlorp   Help setting up the app |
| RECENTLY USED                          |
|  research       claude-haiku-4-5       |
| ALL AGENTS                             |
|  coder          qwen3-4b               |
|  research       claude-haiku-4-5       |
+----------------------------------------+
```

The setup state (DD8):

```
 New chat
 with GleepGlorp

   [ GleepGlorp ]
   GleepGlorp
   The built-in assistant that helps you
   set up and tune the app.

   /!\ GleepGlorp needs a model first.
       [ Choose a model for GleepGlorp ]

   Pick a different agent

 +-------------------------------------------+
 | Message GleepGlorp...        (disabled)   |
 +-------------------------------------------+
```

They are references for layout and wording, not pixel contracts. The control
library's own classes decide spacing.

**High-fidelity board (operator-approved, 2026-11-18):**
https://claude.ai/artifact/JJaL55X2wc7KBkiyqKGcWV (private to the operator),
built on the GleepGlorp AI design system, dark and light. Six screens at
1280×800:
1. Settings › GleepGlorp in the new Assistant group (DD7), Model, Behavior and
   Memory sections, a flagged note.
2. The New chat picker with the Built in group (DD8).
3. The setup state with no model, and its no-providers variant (DD8).
4. A GleepGlorp chat answering an MCP question with page links, the token left
   to the operator, and the drawer's GleepGlorp kind (DD6, DD8).
5. A GleepGlorp chat while it is off, with the degraded banner and its two
   other wordings (DD8).
6. Settings › Prompts with GleepGlorp's block first (DD6).

Decided with the board (operator, 2026-11-18): the Assistant group sits at the
top of the Settings nav as shown; a bare `#settings` (the rail's Settings)
still lands on Appearance (Flight Director's recommendation; the operator did
not choose otherwise); GleepGlorp's block comes first on the Prompts page;
GleepGlorp does not mention abilities it does not have yet (screen 4's "In the
next update…" line is dropped, and the prompt says so). The board's text is
illustrative; the prompt text on screen 6 is a placeholder tuned in Leg 6.

### Citation Audit

Verified against the working tree at `9fea53cd` (survey plus Flight Director
spot checks). Leg designs re-check line numbers.

| Citation | Status |
|---|---|
| `the_one/db/schema.py:18` — `CURRENT_VERSION = 52`; steps are `if version < N:` blocks ending in `INSERT OR IGNORE INTO schema_version` | verified |
| `the_one/db/schema.py` ~:3049-3052 — `agent_notes.agent_name REFERENCES agents(name) ON DELETE CASCADE ON UPDATE CASCADE` (DD4) | verified |
| `the_one/db/schema.py` ~:533-566 — v5 dropped `chat_sessions.agent_name`'s foreign key (DD1) | verified (survey) |
| `the_one/db/repositories.py` ~:2361 (class), ~:2413-2470 — `AgentNoteRepository.list_if_enabled` and `_switch_state` read `notes_enabled` / `notes_next_number` from the agents row and raise `KeyError` with none (DD4) | verified (survey) |
| `the_one/notes/tools.py:113` — `NotesToolBase._repo()` is a staticmethod seam (DD4) | verified (survey) |
| `the_one/agent/factory.py:365` — `create(self, name="default")`; `:733` `list_agents` adds `"default"`; `:741` `_load_config`; `:749` `_default_config` (DD3) | verified |
| `the_one/agent/factory.py` ~:586-591, :647-650, :725 — notes tools registered outside the disabled filter, seeded, bound (DD3, DD5) | verified (survey) |
| `the_one/agent/factory.py` ~:662-690, `agent/tool_exposure.py::decide_exposure` — exposure decided after registration (DD3) | verified (survey) |
| `the_one/interfaces/web/app.py:1765-1768` — `_create_session` stores `default` as NULL; `:1869` restore uses `or "default"`; `:3608` `start_session` refuses `default`; `:2239-2244` model pre-load skips non-row names; `:3443`, `:3563`, `:3804` no-agent auto-create; `:3373` selftest (DD3) | verified (1765, 3608 by FD; rest survey) |
| `the_one/interfaces/cli.py:72` — `factory.create()` with no agent (DD3) | verified (survey) |
| `the_one/retention.py:48,75-77` — `run_purge_sweep` loops `list_retention_windows()` and calls `delete_older_than(name, cutoff)` (DD9) | verified |
| `the_one/naming.py:38` — `check_name(value)` is shared by every named kind, so agent-only reserved names need their own check (DD10) | verified |
| `the_one/db/name_repair.py` ~:40, :59-85 — `_is_bad` uses `check_name`; `_repair_agents` renames through `repair_name(..., taken=...)` and `agent_store.rename` (DD10) | verified (survey) |
| `the_one/interfaces/web/api.py` ~:3648-3669 — the reserved MCP name `self-configuration` precedent (DD10) | verified (survey) |
| `the_one/interfaces/web/api.py` ~:6402-6409 — provider delete returns 409 when `list_by_provider` finds agents (DD2) | verified |
| `the_one/interfaces/web/api.py` — `_agent_response` (~:235), `_provider_response` (~:6117), `_mcp_source_response` (~:3419) / `_mask_secrets` (~:3408), `_connector_response` (~:4871); KB view inline (~:2429-2443); tool configs (~:954, ~:979); `secrets_api.py:58 _response` (DD5) | verified (survey) |
| `the_one/db/models.py` ~:221-250 — connector config validation is shape-only; nothing refuses a reserved agent name (DD10) | verified (survey) |
| `the_one/connectors/inbound.py` ~:402-419 — inbound calls `factory.create(agent_name)` (DD10) | verified (survey) |
| `the_one/agent/taint.py` — `TRUSTED_TOOL_NAMES`; every other tool is untrusted (fail-closed) (DD5) | verified |
| `the_one/tools/web.py:244` `fetch_url` (`WebConfig`), `:479` `web_search` (`WebSearchConfig`); `tools/_search_backends.py` ~:541-579 builds the backend; keyless DuckDuckGo default `_web_search_config.py:78` (DD5) | verified (survey) |
| `the_one/interfaces/web/static/js/markdown.js:127-139` — `safeHref` keeps same-origin `#` hrefs; `:905` only `http(s)` links get `target=_blank` (DD6) | verified |
| `the_one/interfaces/web/static/js/nav.js:130` — bubble-phase `a[href^="#"]` interceptor (DD6) | verified |
| `the_one/interfaces/web/static/js/settings-pages.js` ~:23-30 — `App.settingsPages`; pinned by `tests/test_settings_pages_static.py` (DD7) | verified (survey) |
| `the_one/interfaces/web/static/js/areas/chat/agent-picker.js` ~:60-66, :91-114, :140-151 — `liveAgents` drops `default`; Recently used; groups (DD8) | verified (survey) |
| `the_one/interfaces/web/static/js/areas/chat/agent-drawer.js` ~:270-292, :600-628 — `describe()` kinds, facts, "Default agent" (DD8) | verified (survey) |
| `evals/harness.py` ~:95, :370-425, :445-530 — `RunSpec.agent_name`, `_seed` writes an AgentConfig row, `run_once` builds under `provider_patch` (DD12) | verified (survey) |
| `the_one/time_zones.py` ~:41, :221-237 — the `app_metadata` setting pattern (DD2) | verified (survey) |

### Prerequisites

- [x] Mission 36 approved and active (operator, 2026-11-18).
- [ ] A clean `main` at or after `9fea53cd`, with no flight branch in progress.
- [ ] The eval apparatus works on this host before Leg 6: the plan token at
      `~/.config/the-one-evals/plan-token`, Ollama running with `qwen3-4b` and
      `lfm3`, and `make eval ARGS="run --help"` succeeding. Checked by the crew
      at Leg 6's start and again before every round (DD12).
- [ ] A real model provider for the HAT (the operator's Claude plan or a local
      Ollama model) on a scratch instance, never 8484 or the default data
      directory.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The flight runs in seven legs. Leg 1 makes room in the unit tier. Leg 2 is the
irreversible schema step and the name and label work, isolated so it can be
reviewed on its own. Leg 3 gives GleepGlorp its settings, its Settings page and
its build path. Leg 4 makes it work end to end in Chats with a placeholder
prompt. Leg 5 gives it its knowledge, tools and real prompt. Leg 6 measures and
tunes the prompt against the new eval set under an operator gate. Leg 7 is the
HAT. Legs 3 and 4 split by capability (settings and build; the chat
experience), each with its own backend, UI and tests, not by layer.

Each leg carries its own tests and documentation (CLAUDE.md, `the_one/agents.md`,
`SECURITY-MODEL.md` for the read surface, the README where user-visible
behaviour changes, `docs/ui-control-inventory.md` if a control gains an
option). Browser lanes are chosen by squawk 0334's rule: the Settings table,
the picker groups and the "Default agent" strings are pinned in several lanes
(`settings`, `chats`, `routing`, `shared`, `agents`), so every lane whose files
match the changed lists runs, not only the owning one.

### Checkpoints

- [ ] Unit tier back under its target with room (Leg 1)
- [ ] Schema v53 applied on a copy of a database that has a stored `default`
      agent, its chats and a connector bound to it; nothing named `default`
      remains (Leg 2)
- [ ] A GleepGlorp chat answers in the browser on the mock provider; the setup
      state and the off state show (Legs 3-4)
- [ ] The allowlist and secret-parity tests pass; the guide drift test passes;
      Settings › Prompts shows the GleepGlorp prompt (Leg 5)
- [ ] The baseline is recorded and the operator has set the Haiku pass bar
      (Leg 6)
- [ ] HAT passed (Leg 7)

### Adaptation Criteria

**Divert if**:
- The factory split (DD3) cannot keep the existing factory tests unchanged,
  apart from those that pin the Default agent (`tests/test_factory.py`
  ~:190-205, ~:893-903), which Leg 3 removes.
- Moving the response helpers out of `api.py` (DD5) changes any API response
  body.
- Haiku cannot reach a usable pass rate within the round budget with the tool
  set in DD5 (re-plan the tool shape before Flight 2 builds on it).

**Acceptable variations**:
- The client source for GleepGlorp's state is an `App.store` collection or its
  own small module (DD8).
- The notes counter sits beside the settings or in a one-row table (DD4).
- The guide's topic list grows or merges as it is written.
- `read_app_config`'s kinds merge or split after the Leg 6 measurement.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> and created one at a time as the flight progresses. This list will evolve
> based on discoveries during implementation.

- [x] `unit-tier-room` - Squawk 0383: trim the real-time MCP stdio tests (keep
      one real slow-start test, slack of 4 s or more per real-fixture test),
      re-measure the unit tier on a quiet host, and only if trimming falls
      short move the target with a recorded reason. Completes the squawk.
- [x] `retire-default-agent` - DD10: schema v53, the reserved-name check on
      agent, connector, import and routines paths (and `start_session`
      refusing both names), the inbound drop, the agent-only startup rename,
      and the agent editor's routines checks for an agent named `default`,
      with the tests that pin them. (The chat-surface "Default agent" labels
      moved to Leg 4; see the flight log.) Every app.py and CLI NULL→`default` path and the factory
      fallback stay working until Leg 3 removes them together, so the tree is
      never broken between legs.
- [x] `gleepglorp-settings-and-build` - DD1, DD2, DD3, DD7 (the Model and
      Behavior sections), DD9: the settings model and routes (classified in
      `tests/test_api_name_rule.py`), the client source, provider usage (the
      409, the agents route, `providerAgents` and its wording), the factory
      split with the GleepGlorp build (`notes_enabled=False`, no web tools, a
      placeholder prompt) and its minimal allowlist test, the removal of the
      factory fallback with every app.py and CLI `default` caller and the
      auto-create paths, the CLI and selftest (tool check on `current_time`),
      the Settings page with its nav group and router `DESTINATIONS` row, and
      the retention pass.
- [x] `gleepglorp-in-chats` - DD8, DD11: GleepGlorp chats end to end.
      `start_session` admits the exact `GleepGlorp`, the session paths and
      model pre-load, the GleepGlorp degraded statuses and the server's
      per-turn refusal, the client "which agent" helper with its settings
      href, the picker's Built in group, the setup and off new-chat states,
      the Chats row and header, the drawer kind, the off banner, Jump-to's
      GleepGlorp kind, the change push with the re-join, and the removal of
      every chat-surface "Default agent" label and `default` check
      (`chats-list.js`, `chat-pane.js`, `agent-drawer.js`, `jump-to.js`,
      `agent-picker.js`, `session-flow.js`, `transcript.js`) with the browser
      tests that pin them.
- [x] `gleepglorp-reads-the-app` - DD5 (split from the original
      `gleepglorp-knows-the-app` during execution; see the flight log): the
      shared view module moved out of `api.py`, strict masking,
      `read_app_config`, the read-only proof, the allowlist and secret-parity
      tests, `SECURITY-MODEL.md`.
- [x] ~~`gleepglorp-guide-memory-web`~~ - aborted before starting; split at its
      design review into the three legs below (flight log).
- [x] `gleepglorp-memory-and-web` - DD4, the web part of DD5, DD7 (the Memory
      section): the GleepGlorp notes repository and tools, its notes heading,
      the Memory section, the notes routes, the web tools under the switch,
      `web_search_available` and its hint.
- [x] `gleepglorp-guide` - DD6 (the guide): the topic files, `get_app_guide`,
      the drift and format test, package data in every installer.
- [x] `gleepglorp-prompt` - DD6 (the prompt): the shipped prompt (version 1),
      its token measurement, `/api/info` `gleepglorp_prompt` and the Prompts
      block.
- [x] `prompt-and-evals` - DD12: the builder switch in the harness, the new
      checks, the scenario set, measured rounds under the budget and stop
      rule, the baseline, the operator's Haiku pass bar, small-model readings
      and the tool-count reading. Operator-gated.
- [x] `hat` - Guided HAT with fixes (DD13 apparatus check first). Steps as
      state transitions: fresh install with no providers → provider added, no
      GleepGlorp model → model chosen → real answers about a page, a
      configured item and a key request → off → on again; a second window on
      a GleepGlorp chat follows a settings change; Default agent gone.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (`make gate` under `THE_ONE_TEST_NETNS=1`, unit tier within
      its target)
- [ ] Documentation updated (CLAUDE.md, `the_one/agents.md`,
      `SECURITY-MODEL.md`, README, `docs/ui-control-inventory.md` if touched)
- [ ] Squawk 0383 completed

### Verification

- Unit and browser tests for every DD, including the allowlist test (DD5), the
  secret-parity test (DD5), the guide drift test (DD6), the schema v53
  migration on a seeded database (DD10), the reserved-name refusals across
  agent, connector and import paths (DD10), and the unchanged platform-prompt
  pins (DD6).
- The eval baseline `evals/baselines/m36-gleepglorp.json` with the operator's
  Haiku pass bar recorded, small-model readings and the tool-count reading
  (DD12).
- The HAT (Leg 7), with its apparatus checked first (DD13).
- No behavior test this flight. The mission's behavior-test-backed criteria
  (overlay, form fill, proposals) belong to Flights 2 and 3. Flight 1's real-model
  behaviour is covered by the evals and the HAT.
