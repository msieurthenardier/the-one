# Leg: gleepglorp-settings-and-build

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Give GleepGlorp its stored settings, its route, its Settings page and its build
path through a split `AgentFactory.create`, and remove the legacy `default`
fallback together with every app.py and CLI caller of it, so that a chat named
`GleepGlorp` builds from the settings and nothing in the app falls back to a
Default agent any more.

## Context
- Flight DD1, DD2, DD3, DD7 (Model and Behavior sections only), DD9; the
  approved board's screen 1 (the Memory section comes in Leg 5).
- Leg 2 (committed `ea55a076`) added `naming.GLEEPGLORP_AGENT_NAME`
  (`"GleepGlorp"`), `is_reserved_agent_name`, schema v53 (no NULL or `default`
  chats remain; `gleepglorp_notes` exists, unused until Leg 5) and the reserved
  `start_session` refusal (Leg 4 admits exact `GleepGlorp`).
- In this leg GleepGlorp's build has `notes_enabled=False` and no web tools; the
  Memory and Web access switches are stored and shown but inert until Leg 5.
  Its prompt is a short placeholder (Leg 5 writes the real one). It does not go
  through `build_system_prompts`' platform layer, so
  `tests/_platform_prompt_pins.py` stays green.
- Chats with GleepGlorp are not started from the UI until Leg 4 (`start_session`
  still refuses the name). This leg proves the build through the factory, the
  session restore path, the CLI and selftest.

- Facts from the design review (verified): `chat_sessions.agent_name` has no FK
  (`schema.py` ~:534), so storing `GleepGlorp` with no agents row is fine; fix
  the stale comment at `app.py` ~:1766 that says otherwise. `AgentConfig` has
  `extra="ignore"` and no required field but `name`; `system_prompt=""` and
  `name="GleepGlorp"` pass. `enabled_tools=[]` yields only whitelist-exempt
  tools (`agent/config.py` ~:200-208), so `current_time` alone; `SearchTools`
  is always registered; connector tools stay out. `current_time` is already
  seeded for every agent regardless of exposure (`factory.py` ~:588-605).
  `SecretResolver("GleepGlorp")` finds no row and fails closed (no grants).
  `App.store` maps names to list endpoints and cannot hold a single object
  (`store.js` ~:48-54): use the separate `App.gleepglorp` module.
  `App.ui.select` throws on an empty `options` array or a `value` not among the
  options (`ui/field.js` ~:93-117).
- Decisions on the review's questions: agent routes that call
  `factory.create(name)` (for example the context-window route, `api.py`
  ~:1424) answer 404 for the reserved name, since GleepGlorp has no agent row
  (DD1); a connector cannot bind to GleepGlorp (Leg 2 refuses it at save and
  drops it inbound); with `current_time` off app-wide GleepGlorp has only
  `search_tools` and its prompt uses the tool-free date wording; retention
  applies to GleepGlorp chats even while GleepGlorp is off.

## Inputs
- `ea55a076` on `flight/01-gleepglorp-exists-and-answers`.
- Code map (verified by a read-only survey of the current tree):
  - `the_one/time_zones.py:41` `SETTING_KEY`, `:171` model (`extra="forbid"`),
    `:221-231` `load_setting` (never raises, default on a bad value),
    `:234-237` `save_setting`; routes `api.py` ~:3110-3191.
  - `the_one/agent/factory.py:365-731` `create`; `:733-754`
    `list_agents`/`_load_config`/`_default_config`; errors `:296`
    `AgentNotFoundError(KeyError)`, `:305` `ProviderNotFoundError(KeyError)`,
    `:313` `ProviderNotConfiguredError(ValueError)`.
  - `the_one/agent/prompt_layers.py:103-174` `build_system_prompts`;
    `time_zones.load_effective_zone` + `date_line` (`:319`).
  - `the_one/interfaces/web/app.py`: statuses `:1697-1701`; `_create_session`
    `:1743-1769`; `_restore_session` `:1870-1903`; `_ensure_ollama_model_loaded`
    `:2240-2243`; self-config pending `:2953-2961`, `:3043-3045`; `/api/selftest`
    `:3367-3415`; `/api/chat` `:3433-3448`; WS auto-create `:3564`, `:3809`.
  - `the_one/interfaces/cli.py:70-78`.
  - `the_one/interfaces/web/api.py`: notes-from-session helper `:2194`, `:2204`;
    provider agents `:6420-6430`; provider delete `:6433-6457`;
    `db/repositories.py:189-195` `list_by_provider`.
  - `the_one/retention.py:48-90`.
  - Settings UI: `static/js/settings-pages.js:23-30`; `router.js` `:78`
    (`root: 'settings/appearance'`), `:96-101` (`SECTIONS`), `:266`;
    `static/js/areas/admin.js` `:10`, `:34`, `:59`, `:110`, `:131-140`, `:169`,
    `:205`, `:221`, `:260`, `:276`, `:280`, `:301`, `:332-342`;
    `areas/admin/knowledge-settings-page.js` (the Save/Cancel page template);
    `static/js/store.js:147-149`, `:238` (`App.usage.providerAgents`);
    `areas/studio/library-pane.js:239-241`; `areas/studio/provider-editor.js:450-473`.

## Outputs
- `the_one/gleepglorp/` package: `settings.py` (model, load, save, state),
  `build.py` (the in-memory `AgentConfig`), `prompt.py` (placeholder prompt
  builder), `__init__.py` re-exports.
- `GET`/`PUT /api/gleepglorp`.
- `AgentFactory.create` split into config loading plus `_build`; the GleepGlorp
  branch; `_default_config` and `list_agents`' `"default"` gone.
- Every app.py, api.py and CLI NULL/`default` path converted.
- The Settings › GleepGlorp page (Model and Behavior), the Assistant nav group,
  the router row; provider usage counting GleepGlorp.
- The retention pass.
- Tests and docs.

## Acceptance Criteria

**Settings and route**
- [ ] `GET /api/gleepglorp` returns `{enabled, provider_config_id, model,
      web_access, memory, retention_days, state}` with defaults `true, null,
      null, true, true, 30` and `state` one of `off`, `needs_model`,
      `provider_missing`, `ready` (derived: off when `enabled` is false; else
      `needs_model` when provider or model is null; else `provider_missing` when
      the provider row does not exist; else `ready`).
- [ ] `PUT /api/gleepglorp` takes the whole settings object and returns the GET
      shape. It refuses with a 422 list (`[{"type", "loc", "msg"}]`, the shape
      `App.api.fieldErrors` reads): a body that is not an object (`loc []`);
      an unknown key (`loc [<key>]`); a wrong type; `retention_days` outside
      1-365 (`loc ["retention_days"]`); a `provider_config_id` naming no
      provider (`loc ["provider_config_id"]`); a non-empty `model` with no
      provider. A stored value that fails to parse loads as the defaults with a
      warning (never a 500).
- [ ] Both routes sit behind the credential gate (a test without the
      credential gets 401) and are classified in `tests/test_api_name_rule.py`
      as routes that set no name.

**The build**
- [ ] `AgentFactory.create("GleepGlorp")` with a ready setting returns an agent
      whose registered tool names are exactly `{"search_tools",
      "current_time"}` (the core adds `continue` itself), whatever the
      operator's tool settings, any agent's whitelist, MCP servers, knowledge
      bases or connectors; whose model is the setting's model; whose system
      prompt is the placeholder plus the date line, with no platform text,
      rules, persona, notes or secrets; and whose `current_time` schema is in
      its starting set even when tool exposure is off
      (`THE_ONE_TOOL_EXPOSURE_FRACTION=0`) or the provider reports no context
      window. (The minimal allowlist test.)
- [ ] `create("GleepGlorp")` raises `GleepGlorpUnavailableError` (a subclass of
      `ProviderNotConfiguredError`, so of `ValueError`) carrying the `state`
      when the setting is `off`, `needs_model` or `provider_missing`.
      `create("gleepglorp")` raises `AgentNotFoundError` (exact spelling only).
- [ ] The existing factory tests pass unchanged except those that pin the
      Default agent (`tests/test_factory.py` `TestDefaultAgent` ~:189-203,
      `TestListAgents` ~:892-903, and `TestSecretResolverInjection` ~:209-210's
      `"default"` parameter, which is renamed to a legal agent name), which are
      removed or rewritten to assert the new behaviour. `create()` with no
      argument builds GleepGlorp; `TestDefaultAgent` becomes a test that
      `create()` with no GleepGlorp model raises `GleepGlorpUnavailableError`
      with state `needs_model`. `create("GleepGlorp")` works with the factory's
      `store` set and with `store=None`.
- [ ] Agent routes that build through the factory by path name (the
      context-window route, `api.py` ~:1424, and any other a grep finds) answer
      404 for `GleepGlorp`, as for any name with no agents row.
- [ ] The session and WebSocket tests that pin the old no-agent behaviour are
      rewritten, not deleted: `tests/test_session_lifecycle.py` (~:49, :67, :77,
      :95, :138, :240, :371: pass a real agent name, or assert the refusal and
      that no session is stored) and `tests/test_ws_start_session.py` (~:407,
      :522, and `test_join_without_an_id_still_auto_creates` ~:1107-1114, which
      becomes a test that a join with no id sends "Cannot start chat: …" and
      creates nothing). `"default"` used only as a string in other tests
      (`test_connector_send_tool.py`, `test_web_list_sessions_projection.py`,
      `test_self_configuration_write.py`, …) is left alone unless a test now
      fails.

**No more Default agent fallback**
- [ ] `_default_config` and the `"default"` entry in `list_agents` are gone;
      `grep -rn '"default"' the_one/agent/factory.py` finds no agent-name use.
- [ ] `_create_session` stores the agent name it is given and refuses a
      missing or empty name with a `ValueError` ("Choose an agent to start a
      chat."); `/api/chat` with no agent catches that `ValueError` and answers
      as it does today for a build failure (HTTP 200 with
      `{"error": "Cannot start chat: …"}`, `app.py` ~:3446-3448); the WS
      `join` with no id and the WS message with no session send their existing
      "Cannot start chat: …" error and create no session.
- [ ] `_restore_session` builds from `db_session.agent_name`; a NULL agent name
      (impossible after v53, defensively) is `AGENT_DELETED`; a GleepGlorp chat
      whose setting is not ready is `PROVIDER_MISSING` for now (Leg 4 adds the
      GleepGlorp statuses).
- [ ] `_ensure_ollama_model_loaded` pre-loads GleepGlorp's model from its
      settings when the chat is GleepGlorp's and its provider is Ollama.
- [ ] The self-configuration pending calls and the api.py notes-from-session
      helper no longer use `or "default"` (a missing name skips the call or
      compares as no match).
- [ ] `the-one chat` with no agent chats with GleepGlorp; with GleepGlorp off
      or without a model it prints one plain line saying so and how to fix it
      (Settings › GleepGlorp) and exits non-zero, never a traceback.
- [ ] `/api/selftest` builds GleepGlorp; its tool check asks for the current
      time and passes on a `current_time` result; with GleepGlorp not ready it
      returns its existing failure JSON with a plain reason, never a 500.

**Settings page**
- [ ] `App.settingsPages` starts with `{section: 'gleepglorp', label:
      'GleepGlorp', group: 'Assistant'}`; the router's settings `SECTIONS` gain
      the matching first row; a bare `#settings` and the rail still land on
      `settings/appearance`.
- [ ] `#settings/gleepglorp` shows the page from the approved board's screen 1
      without the Memory section: header "GleepGlorp" with the subtitle and
      Cancel/Save; Model (provider select listing the model providers, model
      select filled from the chosen provider's model list, the "small local
      models" hint); Behavior (switches GleepGlorp, Web access, Memory with
      their hints; "Keep chats for [n] days"). All controls are `App.ui`
      factories; no HTML-string sinks.
- [ ] Changing any control marks the page dirty (the `editor-unsaved`
      caption); Cancel restores the saved values; Save PUTs, re-baselines from
      the response and focuses per `App.focusAfter`; a 422 lands on its field
      through `App.api.fieldErrors`; leaving with unsaved changes asks once
      through `App.nav`.
- [ ] Testids: `settings-nav-gleepglorp`, `gleepglorp-settings`,
      `gleepglorp-provider`, `gleepglorp-model`, `gleepglorp-enabled`,
      `gleepglorp-web`, `gleepglorp-memory`, `gleepglorp-retention`, plus the
      shell's cancel/save ids, recorded in `docs/ui-testid-registry.md`.
- [ ] Tests that pin the Settings table, groups, keyboard order and Jump-to
      Settings entries are updated (`tests/test_settings_pages_static.py`,
      `tests/browser/test_flow_admin_settings_nav.py`, `test_flow_keyboard.py`,
      `test_flow_jump_to.py`, `test_router_core.py`), and a new browser test file
      `tests/browser/test_flow_settings_gleepglorp.py` covers load, dirty,
      cancel, save, a 422 on retention, and the leave guard.

**Provider usage**
- [ ] `GET /api/providers/{id}/agents` includes `"GleepGlorp"` when GleepGlorp's
      setting names that provider; `DELETE /api/providers/{id}` is refused with
      the existing 409 naming GleepGlorp; the provider editor's existing
      "Used by:" notice therefore names it.
- [ ] `App.usage.providerAgents` takes GleepGlorp's settings as an optional
      third argument and counts it; the Library provider row's meta names
      GleepGlorp ("GleepGlorp", or "GleepGlorp, 2 agents") when it uses that
      provider.

**Retention**
- [ ] `run_purge_sweep` deletes GleepGlorp chats older than its
      `retention_days`, adds their ids to the evicted ids and to `deleted`, and
      leaves younger GleepGlorp chats and other agents' chats alone.

**Gate**
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes under 350 s; the lanes whose
      files match the changed lists pass (`settings`, `routing`, `shared`,
      `providers`, `library`, and the lane holding `test_flow_jump_to.py` and
      `test_flow_keyboard.py`), each with `THE_ONE_TEST_NETNS=1`; the static
      guards pass.

## Verification Steps
- Targeted: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_factory.py tests/test_session_lifecycle.py tests/test_ws_start_session.py tests/test_retention.py tests/test_chat_history_purge.py tests/test_settings_pages_static.py tests/test_api_name_rule.py <new test files> -x --timeout 60`.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings -x` and each other lane named in the Gate criterion (find the owning lanes with `bash scripts/run-tests.sh --lane <lane> --list`).
- Static guards: `tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_nav_helper.py`.
- Manual on a scratch instance (port 8490+, scratch data dir under `$HOME`,
  `THE_ONE_DEV_MODE=true`, a mock provider): open `#settings/gleepglorp`, choose
  the mock provider and model, Save, then `the-one chat` with that data dir and
  get a reply. Record in the flight log.

## Implementation Guidance

1. **`the_one/gleepglorp/settings.py`.** Copy the time-zone pattern:
   `SETTING_KEY = "gleepglorp"`; `GleepGlorpSettings(BaseModel)`
   (`extra="forbid"`, the six fields, `retention_days: int = Field(30, ge=1,
   le=365)`); `load_settings(conn)` (never raises; defaults on a missing or bad
   value, warning logged); `save_settings(conn, s)`; `async def state(conn, s)`
   returning the four states (checks the provider row through
   `LLMProviderRepository`). No cache: read per call, as time zones do.
2. **Routes.** In `api.py`, `GET`/`PUT /api/gleepglorp` beside the time-settings
   routes. The PUT validates by hand into the 422 list shape (see AC), then
   checks the provider exists, saves, and returns the GET shape. Add the
   classification to `tests/test_api_name_rule.py`.
3. **Errors.** In `factory.py`, `class GleepGlorpUnavailableError(
   ProviderNotConfiguredError)` with a `state` attribute and a plain message
   per state ("GleepGlorp is turned off.", "GleepGlorp needs a model.",
   "GleepGlorp's model provider was removed.").
4. **Factory split.** `create(name=GLEEPGLORP_AGENT_NAME)`: `ensure_dirs`; if
   `name == GLEEPGLORP_AGENT_NAME` (exact), load settings, compute state, raise
   `GleepGlorpUnavailableError` unless `ready`, and build the config with
   `the_one.gleepglorp.build.gleepglorp_config(settings)`; else
   `_load_config(name)`. Then `return await self._build(config, gleepglorp=...)`.
   `_build` is today's `:370-731` with `name` → `config.name` (`:372`, `:489`,
   `:494`, `:508`, `:521`, `:566`, `:580`, `:590`). When `gleepglorp` is true:
   - builtins come out as `current_time` alone because `enabled_tools=[]` and
     `current_time` is whitelist-exempt (verified), still under the operator's
     `disabled_names`;
   - skip MCP, knowledge-base, notes, routines and connector-tool stages (the
     config carries none; assert rather than rely on emptiness);
   - `current_time` is already seeded for every agent regardless of exposure;
     keep a GleepGlorp hook that seeds every registered GleepGlorp tool after
     the exposure stage anyway, because Leg 5 adds tools that must always be
     seeded (the hook is a no-op today; its test is the allowlist test);
   - build the prompt with `the_one.gleepglorp.prompt.build_prompts(conn,
     tool_available=...)`, which returns the same `SystemPrompts(tool_capable,
     tool_free)` shape from the placeholder text plus `time_zones.date_line`
     (exceptions swallowed like `build_system_prompts`), instead of
     `build_system_prompts`.
   `gleepglorp_config(settings)` returns an `AgentConfig(name="GleepGlorp",
   provider_config_id=..., llm_model=..., system_prompt="", enabled_tools=[],
   disabled_tools=[], notes_enabled=False, rich_visuals=False,
   routines_self_config_enabled=False, chat_history_retention_days=...)`;
   check `AgentConfig`'s required fields and defaults.
   Remove `_default_config`, the `"default"` in `list_agents`, and `_load_config`'s
   `"default"` branch.
5. **app.py / api.py / cli.py.** Convert each site in the Inputs list per the
   AC, plus `api.py` ~:1415-1424 (the context-window route: refuse the reserved
   name with 404 before building; fix its comment that describes the
   `"default"` fallback) and any other `factory.create(` caller a grep finds
   (`connectors/inbound.py` ~:428 is covered by Leg 2's drop; `evals/harness.py`
   ~:477 builds `ev-*` names and is unaffected until Leg 6):
   `_create_session` (store the name as given; refuse missing; correct the
   stale FK comment at ~:1766);
   `_restore_session` (`db_session.agent_name`, NULL → `AGENT_DELETED`;
   `GleepGlorpUnavailableError` falls under the existing
   `ProviderNotConfiguredError` → `PROVIDER_MISSING` catch); pre-load branch
   (drop its `or "default"`; for `GleepGlorp`, read provider and model from the
   settings instead of `store.load`); self-config pending (pass
   `session.agent_name`; read `_calling_agent` and the pending registry first —
   the comment there calls `"default"` load-bearing — and skip the call when the
   name is None; for GleepGlorp it is a no-op); `/api/chat`; WS auto-create;
   `/api/selftest` (wrap the
   build, change the tool check to `current_time`); `cli.py` (catch
   `GleepGlorpUnavailableError` first and print its message plus "Choose a model
   in Settings › GleepGlorp."); `api.py` `:2194`/`:2204`.
6. **Provider usage.** `list_by_provider` stays agents-only; the two routes add
   `"GleepGlorp"` when the setting names the provider (the GET list sorted with
   GleepGlorp first). `App.usage.providerAgents(agents, providerId, gleepglorp)`
   adds 1 when `gleepglorp && gleepglorp.provider_config_id === providerId`;
   `library-pane.js` builds the meta from the agent count and a GleepGlorp
   flag.
7. **Client source.** A small `App.gleepglorp` module (in
   `static/js/gleepglorp.js`, loaded before the areas; `App.store` cannot hold
   a single object): `get({force})` (GET `/api/gleepglorp`, a copy), `peek()`,
   `invalidate()`, `subscribe(fn)`, `prime(obj)`. Invalidate on Save. Library
   and the Settings page read it; Leg 4 adds the push.
8. **Settings page.** `areas/admin/gleepglorp-page.js`
   (`App.admin.renderGleepGlorpPage(container, {onDirtyChange})`) on the
   `knowledge-settings-page.js` pattern: `App.ui.editorShell({variant:'page',
   ...})`, sections via the library, `App.ui.toggle` ×3, a number
   `App.ui.textInput` for retention, and two `App.ui.select`s built so they
   never throw (`select` refuses empty options and an unknown value):
   - provider: always a first placeholder option (value `""`, "Choose a model
     provider…"), then the providers from `App.store.get('providers')`; when
     the saved id is not among them (`provider_missing`), add one option for it
     labelled "Removed provider" and show a warning hint;
   - model: rebuilt on every provider change from
     `GET /api/providers/{id}/models` (`api.py` ~:6750; a list of
     `{id, name, ...}`; 404 for a missing provider), always with a placeholder
     first ("Choose a model…"); the saved model is added as an option when the
     list lacks it or fails to load; a loading state while it fetches and an
     error hint when it fails. Choosing the placeholder sets null.
   Do not reuse `agent-model-picker.js` (it is bound to the agent editor's
   DOM). Hosting in `admin.js` (more than "like knowledge"): the page is
   neither in `GENERAL_SUBS` nor `tools`/`knowledge`, so give it its own
   category id `gleepglorp`, add it to `validIds` (~:59) and `ROUTE_SECTION`
   (~:110) if the route segment differs, a `renderContent` branch (~:221), a
   refresh-skip-while-dirty branch (~:265), `editorOpen` (~:278) and
   `_discardEditor` (~:280) branches, and the item-open check (~:342); leave
   the `GENERAL_SUBS`-driven getters (~:14-18) and the fallback (~:34, ~:45)
   on Appearance. The table row goes first in `settings-pages.js` (nav groups
   follow table order) and the router `SECTIONS` change with it
   (`tests/test_settings_pages_static.py` pins them equal). If a control needs
   an option it lacks, add it with its catalogue row and contract test.
9. **Retention.** After the per-agent loop in `run_purge_sweep`, load the
   settings and run `chat_repo.delete_older_than("GleepGlorp", cutoff)`;
   append the ids and add the count. GleepGlorp has no routines, so no routine
   passes.
10. **Docs.** CLAUDE.md: a short "GleepGlorp (M36 F1)" paragraph (settings,
    route, build, no Default agent, CLI/selftest); `the_one/agents.md` a
    "GleepGlorp (M36)" section (the split, the branch, the allowlist, the
    settings key, retention); `docs/ui-testid-registry.md`; the README's
    Settings description if it lists pages.

## Edge Cases
- **Provider deleted outside the route** (database edit): state is
  `provider_missing`; the page shows the provider select empty with a warning
  hint, never a crash.
- **Model list fails to load** on the page: the model select shows its error
  state and keeps the saved model as its value.
- **Two windows**: a Save in one does not update the other's open page until
  Leg 4's push; a stale Save simply overwrites (whole-object PUT). Acceptable
  for this leg; note it.
- **`retention_days` sent as a string** ("30"): refused (wrong type), matching
  the strict model.
- **The operator turned `current_time` off app-wide**: GleepGlorp then has only
  `search_tools`; the allowlist test covers both cases.

## Files Affected
- New: `the_one/gleepglorp/{__init__,settings,build,prompt}.py`,
  `static/js/gleepglorp.js`, `static/js/areas/admin/gleepglorp-page.js`,
  `tests/test_gleepglorp_settings.py`, `tests/test_gleepglorp_build.py`,
  `tests/browser/test_flow_settings_gleepglorp.py`.
- Changed: `the_one/agent/factory.py`, `the_one/interfaces/web/app.py`,
  `the_one/interfaces/web/api.py`, `the_one/interfaces/cli.py`,
  `the_one/retention.py`, `static/index.html` (script tag),
  `static/js/settings-pages.js`, `static/js/router.js`,
  `static/js/areas/admin.js`, `static/js/store.js`,
  `static/js/areas/studio/library-pane.js`, tests listed in the AC, docs.

## Citation Audit
From the read-only survey of the current tree (after `ea55a076`); the Flight
Director spot-checked `factory.py:365/733/741/749`, `app.py:1765/3608`,
`retention.py:48/75` earlier at `9fea53cd`. Leg 2 changed `app.py` only at the
`start_session` check and an import, so the cited app.py lines moved by at most
a few lines: the Developer re-locates each by its quoted symbol before editing.
- `time_zones.py:41,171,221-237` - setting pattern - verified (survey)
- `factory.py:296,305,313` error classes; `:365-731` create stages; `:733-754` default fallback - verified (survey)
- `prompt_layers.py:103-174`; `time_zones.py:319` `date_line` - verified (survey)
- `app.py:1697-1701,1743-1769,1870-1903,2240,2953-2961,3043-3045,3367-3415,3433-3448,3564,3809` - verified (survey)
- `cli.py:70-78` - verified (survey)
- `api.py:2194,2204,6420-6457`; `db/repositories.py:189-195` - verified (survey)
- `settings-pages.js:23-30`; `router.js:78,96-101,266`; `admin.js` lines listed - verified (survey)
- `store.js:147-149,238`; `library-pane.js:239-241`; `provider-editor.js:450-473` - verified (survey)
- `agent-model-picker.js` is bound to the agent editor's DOM (`#studio-provider`, `#studio-model`, …) - verified (survey); hence not reused.
