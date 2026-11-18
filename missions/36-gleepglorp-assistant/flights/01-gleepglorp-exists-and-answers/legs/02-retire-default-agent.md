# Leg: retire-default-agent

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Remove the stored Default agent and its data at upgrade (schema v53), reserve the
agent names "default" and "GleepGlorp" on every path that sets or binds an agent
name, and rename any stored agent that already uses one, leaving the factory's
`default` fallback and its app.py and CLI callers working until Leg 3.

## Context
- Flight DD10 (as amended by both Architect passes), DD4 (the GleepGlorp notes
  table is created by this step), DD1 (the reserved spelling `GleepGlorp`).
- Agent names are case-sensitive (`agents.name TEXT PRIMARY KEY`,
  `db/schema.py:53`). v53 touches exactly `default`; a user agent called
  `Default` is renamed at startup instead (it is a real agent with its own chats).
- Leg boundary (Architect pass 2): this leg does NOT remove `factory.py`'s
  `create(name="default")` / `_default_config` / `list_agents` entry, nor the
  app.py and CLI NULL→`default` paths (`_create_session` ~:1765, restore ~:1869,
  pre-load ~:2239, self-configuration pending ~:2953-2959 and ~:3043, auto-create
  ~:3443/~:3563/~:3804, selftest ~:3373, `cli.py:72`). Leg 3 removes them
  together with GleepGlorp's build.
- **Deviation from the flight's Legs list, recorded here and in the flight log:**
  the chat-surface "Default agent" labels (`chats-list.js`, `chat-pane.js`,
  `agent-drawer.js`, `jump-to.js`, `agent-picker.js` `liveAgents`,
  `session-flow.js:249`, `transcript.js`) move to Leg 4. Until Leg 3 the server
  can still create a NULL-agent chat, so those labels still have something to
  label; Leg 4 rewrites the same surfaces for GleepGlorp anyway, and the five
  browser tests that pin "Default agent" change once, there. This leg takes only
  the JS checks that concern an agent *named* `default` in the agent editor
  (`routines-tab.js:67`, `self-config-routines.js:45`), which v53 and the
  reserved name make dead.

- **`chat_sessions` has no foreign key to `agents`** (dropped in v5,
  `schema.py` ~:534-561; `agent_name TEXT` bare). `DELETE FROM agents` does not
  touch chats, so v53's explicit chat deletes are mandatory. Renames carry
  chats by hand in `agent_store.rename` (`db/repositories.py` ~:451-498), not
  by SQL cascade; the "a live `GleepGlorp` agent's chats survive" criterion
  relies on that code.
- **No other hand-deletes are needed** (design review, verified): the only
  `session_id` columns are `agent_notes.origin_session_id` (~:3058),
  `agent_routines.target_session_id` (~:3133), `agent_routine_runs.session_id`
  (~:3164) and `agent_routine_proposals.session_id` (~:3215), all plain TEXT in
  tables that cascade from `agents` or `agent_routines`; no other agent's rows
  reference `default`'s chats, and no `app_metadata` key is keyed by agent name.
- Decisions on the review's questions: `start_session` keeps its existing
  "Invalid agent name." sentence for a reserved name; the routines guards
  refuse GleepGlorp on purpose (it can never own routines, mission constraint).

## Inputs
- Leg 1 landed (unit tier has room).
- `CURRENT_VERSION = 52` (`db/schema.py:18`); the v52 step is the last
  (`db/schema.py` ~:3320-3330).

## Outputs
- Schema v53 in `the_one/db/schema.py`, `CURRENT_VERSION = 53`, with the hard
  `== 52` pins in `tests/test_db_migration.py` (~:5019, :5375, :5521, :5662,
  :5668, :5801, :5953, :6000, :6359; re-grep) updated. Pins that use
  `CURRENT_VERSION` symbolically need no change.
- An agent-only reserved-name check, used on agent create, agent rename, the
  legacy JSON import, connector create/update, `start_session` and the routines
  guards.
- An agent-only startup-rename predicate in `db/name_repair.py`.
- The inbound drop before `resolve_session`.
- Tests for all of the above; docs updated.

## Acceptance Criteria
- [ ] **v53 on a seeded database** (a real migration from v52, built by a test
      that seeds a v52 database, not the template): given an agent row exactly
      `default` with rules, notes, a routine, a revision and an MCP tool-cache
      row; its self-configuration MCP row (marker
      `{"self_configuration": {"agent": "default"}}`) with an external
      credential; a connector whose `default_agent` is `default` and whose
      `channel_map` has one entry `default` and one entry `research`; chats with
      `agent_name` NULL, `default`, `Default` and `research`; and a chat named
      `GleepGlorp` with no such agent row — after migration: the `default` row,
      its rules, notes, routines, revisions, tool cache, its surface MCP row and
      that row's external credentials are gone; the connector has no
      `default_agent` key and its `channel_map` keeps only the `research`
      entry; the NULL and `default` chats and the orphan `GleepGlorp` chat are
      gone; the `Default` and `research` chats remain; `gleepglorp_notes` and
      its counter exist; `schema_version` holds 53.
- [ ] **v53 keeps a live agent's chats**: with an agent row `GleepGlorp`
      present, its chats survive v53 (the startup rename carries them).
- [ ] **v53 is idempotent** (running `ensure_schema` again changes nothing) and
      runs on a fresh database (the template) without error.
- [ ] **Reserved names, agents**: `POST /api/agents` and
      `POST /api/agents/{name}/rename` refuse `default`, `Default`, `GleepGlorp`
      and `gleepglorp` with a 422 list on `loc ["name"]` (both routes) and a
      plain sentence; `gleep-glorp` and `GleepGlorpX` are allowed. The other
      name-setting routes (MCP, knowledge base, provider, secret) still accept
      `default`. `tests/test_api_name_rule.py` gains the four reserved spellings
      in its create-refuses cases and still passes its route classification.
- [ ] **The counter and notes table**: `gleepglorp_notes` has exactly the
      columns listed in step 7 and a unique index on `number`; the counter row
      is `(1, 1)` after v53 and unchanged by a re-run.
- [ ] **Reserved names, import**: `migrate_json_to_sqlite` skips a JSON config
      named `default` (any case) or `GleepGlorp` (any case), with the same
      warning path as a rule-breaking name, so a leftover `default.json` never
      brings `default` back.
- [ ] **Reserved names, connectors**: connector create and update refuse a
      `default_agent` or any `channel_map` value whose casefold is `default` or
      `gleepglorp`, with a 422 on `["config", "default_agent"]` or
      `["config", "channel_map", <key>]`; a PUT revalidates every binding of the
      merged config (tested); `dispatch_inbound` drops a message whose resolved
      agent is reserved, logging one warning, before `resolve_session`, so no
      chat row is created.
- [ ] **Existing tests that seed `default`**: `tests/test_name_repair.py` (its
      `_seed` saves an agent `default` and expects it to survive, ~:108,
      ~:140-147) is updated to assert the rename instead; the routines tests
      that use `default` as the "no routines" agent
      (`test_routines_api.py` ~:174, ~:788; `test_routines_service.py`
      ~:522-524; `test_routine_tools.py` ~:76) still mean what they did and
      pass; `tests/browser/test_flow_agent_routines*.py` (~:802-826, the
      `routines-default-agent` testid) and any `test_ui_*` contract seeding
      `name: "default"` for those checks are updated or removed with the JS
      check, and the testid joins the retired-testid table if it is gone.
- [ ] **Reserved names, chats and routines**: `start_session` refuses both names
      in any case (Leg 4 later admits exact `GleepGlorp`); the routines REST
      guard (`routines_api.py` `_DEFAULT_AGENT`), `routines/service.py:486` and
      `routines/tool_provider.py:24` refuse both names in any case.
- [ ] **Startup rename**: with stored agents `Default`, `DEFAULT` and
      `GleepGlorp`, startup renames each once to a free name (for example
      `Default 2`, `DEFAULT 3`, `GleepGlorp 2`), carrying its chats and connector
      bindings; a provider, knowledge base or MCP server called `Default` is not
      renamed; a second startup renames nothing.
- [ ] The agent editor's routines checks for an agent named `default`
      (`routines-tab.js:67`, `self-config-routines.js:45`) are removed, and the
      static JS guards pass.
- [ ] The factory fallback and the app.py/CLI NULL→`default` paths are
      unchanged (`git diff` shows no change to them), and the existing tests for
      them still pass.
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes; the owning browser lanes of
      any touched JS file pass (`agent-routines` at least).

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_migration.py tests/test_db_connection.py tests/test_schema.py tests/test_name_repair.py tests/test_api_name_rule.py tests/test_naming.py -x --timeout 60` plus the new test files.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agent-routines -x`.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x`.
- `git diff -- the_one/agent/factory.py the_one/interfaces/cli.py` shows nothing.

## Implementation Guidance

1. **Reserved names, one module.** Add to `the_one/naming.py` (beside
   `check_name`, not inside it: `check_name` serves every kind) a constant
   `GLEEPGLORP_AGENT_NAME = "GleepGlorp"`, `RESERVED_AGENT_NAMES` (casefolded
   `{"default", "gleepglorp"}`), `is_reserved_agent_name(name) -> bool`
   (casefold match) and `check_agent_name(value) -> str` that runs `check_name`
   then raises `NameRuleError` with a plain sentence for a reserved name (for
   example "“GleepGlorp” is the name of the built-in assistant. Choose another
   name." / "“default” is a reserved name. Choose another name."). Use the
   naming rule's existing error type so `_checked_name`'s 422 shape applies.
   Leg 3 imports `GLEEPGLORP_AGENT_NAME` from here.
2. **Agent routes.** Add `_checked_agent_name` beside `_checked_name`
   (`api.py` ~:193-198): `check_agent_name` → on `NameRuleError`, the same
   `name_rule_detail(e.message)` 422 (loc defaults to `"name"`,
   `naming.py` ~:56). Use it only in `create_agent` (~:1447) and `rename_agent`
   (~:1695); the five other `_checked_name` sites (MCP ~:2449/:2490, knowledge
   base ~:3629/:3768, provider and secret ~:6251/:6335) stay as they are.
   `test_api_name_rule.py` classifies by route tuple, so no classification
   change; add the reserved spellings to its create-refuses cases.
3. **Import.** In `db/migration.py`, skip a config when either the file stem or
   `config.name` is reserved (the existing `store.exists(stem)` check runs on
   the stem, ~:25-28, and the two can differ), on the rule-breaking warning
   path; then `check_name` as today.
4. **Connectors.** One shared `_reject_reserved_binding(config)` in `api.py`
   that returns a 422 detail list (a small helper builds the
   `{"type": "name_rule", "loc": [...], "msg": ...}` entries, since
   `name_rule_detail` takes a single-string loc) for a reserved `default_agent`
   (`loc ["config", "default_agent"]`) or `channel_map` value
   (`loc ["config", "channel_map", <key>]`). Call it in `create_connector`
   (`api.py` ~:4952) before `repo.create` (~:4975) and in `update_connector`
   (~:5027) after the merge and before `repo.update` (~:5071). In
   `connectors/inbound.py`, after `_resolve_agent_name` (~:400; the DM path at
   ~:319-327 uses `default_agent` alone, so one check covers both) and before
   `resolve_session` (~:411), drop a reserved name with one warning.
5. **Chats and routines.** `start_session` (`app.py:3608`): replace the
   `== "default"` test with `is_reserved_agent_name(...)`. Routines:
   `routines_api.py` `_DEFAULT_AGENT` guards (~:61, :72, :157, :247),
   `routines/service.py:486`, `routines/tool_provider.py:24` use
   `is_reserved_agent_name`. Keep each guard's existing response.
6. **Startup rename.** In `db/name_repair.py`, `_repair_agents` (~:59) flags a
   name when `_is_bad(old) or is_reserved_agent_name(old)` (an agent-only
   predicate; `_is_bad` stays shared). Seed `taken` with every existing name
   plus the two reserved names (`repair_name` compares casefolded,
   `naming.py` ~:91; `taken` already holds the agent being renamed, and the
   reserved names cover a `Default` with no exact-case twin). `taken.add(new)`
   after each rename keeps `Default` and `DEFAULT` distinct. Rename goes through
   `agent_store.rename` + `cascade_rename` as today; add a test that a
   connector bound to `Default` follows to its new name.
7. **Schema v53.** After the v52 block, `if version < 53:` with idempotent
   steps (the migration connection has `PRAGMA foreign_keys=ON`,
   `db/connection.py:55`; assert it in the test):
   - read `mcp_sources` rows, `json.loads(config)`, delete the ones whose
     `config["self_configuration"]["agent"] == "default"` (exact), so
     `agent_external_credentials` cascades;
   - `DELETE FROM agents WHERE name = 'default'` (cascades rules, notes,
     routines, proposals, revisions, tool cache);
   - read `connectors` rows, `json.loads(config)`, drop a `default_agent` equal
     to `default` and every `channel_map` entry whose value is `default`, write
     back only changed rows; a row whose config is not valid JSON is skipped
     with a warning, not a crash (tested);
   - `DELETE FROM chat_sessions WHERE agent_name IS NULL OR agent_name = 'default'`
     (mandatory: no FK from chats to agents);
   - `DELETE FROM chat_sessions WHERE agent_name = 'GleepGlorp' AND NOT EXISTS
     (SELECT 1 FROM agents WHERE name = 'GleepGlorp')`;
   - no other hand-deletes (see Context);
   - `CREATE TABLE IF NOT EXISTS gleepglorp_notes (` the `agent_notes` columns
     (`schema.py` ~:3049-3066) minus `agent_name`, inlined exactly:
     `id TEXT PRIMARY KEY, number INTEGER NOT NULL, text TEXT NOT NULL,
     untrusted INTEGER NOT NULL DEFAULT 0, untrusted_sources TEXT NOT NULL
     DEFAULT '[]', origin_kind TEXT NOT NULL CHECK (origin_kind IN
     ('web','connector','other')), origin_session_id TEXT, origin_label TEXT,
     origin_platform TEXT, origin_peer_id TEXT, origin_peer_name TEXT,
     created_at TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT
     NULL CHECK (updated_by IN ('agent','operator'))` (re-read the live
     definition and match it, CHECKs included), a unique index on `number`,
     plus a one-row counter table `gleepglorp_notes_counter (id INTEGER PRIMARY
     KEY CHECK (id = 1), next_number INTEGER NOT NULL)` seeded with `(1, 1)` by
     `INSERT OR IGNORE`;
   - `INSERT OR IGNORE INTO schema_version (version) VALUES (53)`, commit,
     `version = 53`. Bump `CURRENT_VERSION`.
8. **JS.** Remove the `default` checks in `routines-tab.js:67` and
   `self-config-routines.js:45` (an agent named `default` can no longer exist).
   Their browser tests pin them (`test_flow_agent_routines*.py` ~:802-826, the
   `routines-default-agent` testid; check `test_ui_*` contracts that seed
   `name: "default"`): remove or rewrite those cases, and add a retired testid
   to the registry's "Retired testids" table and `RETIRED_SELECTORS` if one
   disappears. Fix `tests/test_name_repair.py`'s `default` seed (assert its
   rename).
9. **Docs.** CLAUDE.md "Watch-out — the naming rule" (reserved agent names;
   `default` is no longer a legal agent name — replace the sentence that says it
   is), `the_one/agents.md` "Naming rule" and the schema history, the README if
   it mentions the Default agent.

## Edge Cases
- **A connector whose only binding was `default`** ends with no `default_agent`;
  the existing doctor warning covers it. Do not invent a new binding.
- **A database already past v53** (re-run): every step is a no-op.
- **An `agents` row named `default` that owns an MCP override or KB attachment**:
  cascades or orphaned JSON in other agents is irrelevant; only its own rows go.
- **Rename collisions**: `Default` and `DEFAULT` both exist → two distinct
  suffixed names.

## Files Affected
- `the_one/naming.py` - reserved agent names and `check_agent_name`
- `the_one/db/schema.py` - v53, `CURRENT_VERSION`
- `the_one/db/name_repair.py` - agent-only predicate, reserved names in `taken`
- `the_one/db/migration.py` - `check_agent_name` on import
- `the_one/interfaces/web/api.py` - agent create/rename, connector create/update
- `the_one/interfaces/web/app.py` - `start_session` refusal only
- `the_one/interfaces/web/routines_api.py`, `the_one/routines/service.py`,
  `the_one/routines/tool_provider.py` - reserved-name guards
- `the_one/connectors/inbound.py` - drop before `resolve_session`
- `the_one/interfaces/web/static/js/areas/studio/routines-tab.js`,
  `.../self-config-routines.js` - dead `default` checks removed
- tests: migration, naming, name repair, name rule, connectors, inbound,
  routines, start_session; version pins
- `CLAUDE.md`, `the_one/agents.md`, README if needed

## Citation Audit
Checked against `9fea53cd` by the Flight Director:
- `the_one/db/schema.py:18` `CURRENT_VERSION = 52`; v52 block ~:3320-3330 ends with `INSERT OR IGNORE INTO schema_version`, `commit`, `version = 52` - verified
- `the_one/db/name_repair.py:40` `_is_bad` shared; `:59` `_repair_agents` with `taken = set(names)` and `repair_name(old, kind="agent", taken=taken)` - verified
- `the_one/self_configuration/constants.py:95` `OWNER_MARKER_KEY = "self_configuration"`, marker `{"self_configuration": {"agent": "<name>"}}` - verified
- `the_one/db/models.py` ~:225-245 connector config keys `default_agent` (str), `channel_map` (dict str→str) - verified
- `the_one/connectors/inbound.py` ~:400-412 `_resolve_agent_name` then `resolve_session` - verified
- `the_one/interfaces/web/routines_api.py:61` `_DEFAULT_AGENT = "default"` (:72, :157, :247); `routines/service.py:486`; `routines/tool_provider.py:24` - verified
- `the_one/interfaces/web/api.py:1447` (create), `:1695` (rename) use `_checked_name`; `db/migration.py:32` uses `check_name` - verified
- `the_one/interfaces/web/app.py:3608` `start_session` refuses `"default"` - verified
- connector route lines (~:4952, ~:5027) - unverified; the Developer re-locates them.
