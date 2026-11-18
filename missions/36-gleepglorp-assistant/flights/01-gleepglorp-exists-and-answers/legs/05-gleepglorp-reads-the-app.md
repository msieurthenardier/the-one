# Leg: gleepglorp-reads-the-app

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Give GleepGlorp one read-only tool, `read_app_config(kind, name?)`, built on
whitelist views of its own that read only non-secret fields from the
repositories, and prove with an allowlist test, a secret-parity test across
every encrypted store and a no-write test that it can read the app's
configuration and status but never a secret, a tail of one, a chat, a file or
a log.

## Context
- Flight DD5 and the mission's "Secrets never pass through GleepGlorp"
  criterion. Split from the flight's original Leg 5 (flight log); Leg 6 adds the
  guide, prompt, notes and web.
- **Design change from DD5 (decided at this leg's design review, recorded in the
  flight log):** DD5 said GleepGlorp's views reuse the API's response helpers,
  moved into a shared module, with a `strict` mode. The review showed the move
  is not pure (the helpers drag in the masking machinery, repository factories
  bound to `api.py`, `HTTPException`-raising route bodies, about 700 lines, and
  tests import a dozen private names) and that the API's views pass several
  secret-bearing fields through: MCP `config.env` and `config.headers` values
  (`_mcp_source_response`, `api.py` ~:3517, after masking only `secrets`), an
  agent's `tool_overrides` (never masked, `the_one/agents.md` ~:890), a
  provider's free-form `config`/`base_url`, and secret tails
  (`_emit_mask` ~:3373). **So GleepGlorp gets separate whitelist views**: they
  build their output field by field from repositories and models, never read
  or decrypt a secret column, and leave every API view untouched (so API
  output is byte-identical by construction). Masking holds by construction
  (a field is shown only if it is listed), and the parity test enforces it.
- The encrypted corpora (`the_one/db/encryption_corpora.py` ~:39-52; nine
  `(table, column)` pairs, not eight as CLAUDE.md says — fix CLAUDE.md):
  `llm_providers.api_key`, `llm_providers.secrets`, `mcp_sources.secrets`,
  `connectors.secrets`, `agents.tool_overrides`, `agents.mcp_overrides`,
  `tool_configs.secrets`, `agent_external_credentials.secret`,
  `secret_values.value`. Plus secret-bearing plain fields: MCP OAuth keys
  (`access_token`, `refresh_token`, `dcr_credentials`, …), MCP `config.env` and
  `config.headers` values, provider `base_url`/`config` URLs, MCP `url`.
- Taint: `read_app_config` stays untrusted (the fail-closed default in
  `the_one/agent/taint.py`).
- Tool pattern: `conn = await get_connection()` inside `execute`
  (`tools/connector_lookup.py` ~:78-81); `get_connection()` is the process-wide
  aiosqlite connection (`db/connection.py` ~:45).

## Inputs
- Leg 4 landed. **Hard precondition: this leg starts only after Leg 4 has
  landed** (both touch the GleepGlorp build and the flight's tests).
- Leg 3's always-seed hook in the GleepGlorp branch of `_build` iterates the
  registry (`factory.py` ~:733-737) and the allowlist test
  `tests/test_gleepglorp_build.py` (~:72 `test_the_minimal_allowlist`).

## Outputs
- `the_one/gleepglorp/views.py`: whitelist view functions per kind.
- `the_one/gleepglorp/read_tool.py`: `ReadAppConfigTool` (`read_app_config`).
- The GleepGlorp build registers it.
- Tests: views, the tool, allowlist, secret parity, no-write, kind
  classification. Docs: `SECURITY-MODEL.md`, `the_one/agents.md`, CLAUDE.md.
- No change to `api.py`'s response helpers.

## Acceptance Criteria
- [ ] **The tool shape**: `read_app_config(kind, name?)` with `kind` one of
      `overview`, `agents`, `mcp_servers`, `providers`, `knowledge_bases`,
      `connectors`, `routines`, `secrets`, `built_in_tools`, `settings` (ten
      values; no singular/plural pairs). Without `name`, a list kind returns
      every item's name and a one-line summary; with `name`, the item's detail.
      `routines` takes an agent name (required). `overview` and `settings` take
      no name. An unknown or missing required name returns a plain message
      listing the valid names (never an exception into the loop). Output is
      compact JSON. The description is short (Leg 7 measures it).
- [ ] **What each detail holds** (whitelist; nothing else is emitted):
      - `overview`: counts and names per kind; GleepGlorp's state, model and
        switches; the time zone.
      - agent: name, description, system prompt, model and provider name,
        enabled/disabled tools, the names of tools with overrides (never
        override values), rules (text, on/off), attached MCP servers and
        knowledge bases by name, the routines count, the notes count (never
        note text), rich visuals, the self-configuration switch.
      - MCP server: name, type, command and arguments (shown as written: the
        documented residual), working directory (shown; the sandbox's
        writable paths are not), the address as scheme, host, port and path
        (user info and query string removed; a token in the path is a
        documented residual), header and env-var **names only**, connection
        status from the stored `_cache` keys only (`status`,
        `protocol_version`, `last_check` `{status, at}` or `last_updated`,
        `auth_posture`, `protocol_fallback`, and the tool names from
        `tools[]` with each description cut to 200 characters; check the
        entry shape in `mcp/_agent_cache.py` ~:21 / `to_cache_payload`). Never
        `server_info`, `instructions`, `meta` or `capabilities` (server-written
        free text). There is no stored error text, so none is shown.
        Signed-in yes/no is any key of `OAUTH_MANAGED_SECRET_KEYS` (from
        `the_one.mcp.oauth.storage`) present in the decrypted `secrets`
        (the MCP rule, `api.py` ~:3556), computed in memory and never
        emitted beyond the boolean. Which agents use it
        (`SQLiteAgentStore.list_by_mcp_source`).
      - provider: name, type, the base address reduced to scheme, host and
        port (a key in a query or path never shows), `oauth_active` yes/no by
        the plan rule (`access_token` and `refresh_token` both present,
        `api.py` ~:6238), which agents (`list_by_provider`) and whether
        GleepGlorp use it. No model list: none is stored (the models route
        fetches live), and the tool never fetches.
      - knowledge base: name, folder paths (shown), item counts by status,
        the latest indexed time and the indexer state (the name resolved to
        its id through `KnowledgeBaseRepository`; `KBItemRepository`
        `count_by_status`, `list_folders`, `latest_indexed_at`;
        `knowledge/manager.py` `get_indexing_manager().state(kb_id)`), which
        agents (`list_by_kb`).
      - connector: name, type, enabled, default agent, channel bindings, never
        a token or secret.
      - routines (for an agent): name, schedule sentence and next run
        (`routines/describe.py` `schedule_sentence` ~:40 and `describe_next`,
        with `RoutineRepository`), the prompt, on/off. No `last_run`, run
        outcomes or `session_id` (they point at chats).
      - secret: name, description, key names (shown: GleepGlorp needs them to
        explain `{{secret:key}}`), allowed tools, granted agents
        (`list_by_secret`); never a value.
      - built-in tools: name, on/off for the app, summary (`cls.summary` from
        `the_one.tools.builtins`), and the settings from `row.config` only
        (never `row.secrets`) minus the tool's secret field names, computed by
        a small neutral re-implementation of `_secret_field_names` (`api.py`
        ~:3485 walks `Config.model_fields` for `json_schema_extra["secret"]`).
      - settings: time zone and knowledge indexing (the theme is browser-only
        and absent).
      - Never chats, files or logs.
- [ ] **Secret parity** (falsified: with one view emitting a secret field the
      test fails): a test seeds a distinct value of 16+ characters with a
      unique random-looking tail in every slot — a provider API key; plan
      OAuth `access_token` and `refresh_token`; a plan-token provider's token
      and its `token_set_at`; MCP `secrets` headers and env; all six MCP OAuth
      managed keys (`access_token`, `refresh_token`, `token_expires_at`,
      `token_type`, `scope`, `dcr_credentials` as a dict holding a
      `client_secret`; `mcp/oauth/storage.py` ~:51-59); a connector token in
      `secrets` and a decoy field in a connector's `config`; an agent
      `tool_overrides` value; an `mcp_overrides` credential and an
      `agent_mcp_tool_cache` row; a tool-config secret field (such as a search
      engine key) and a non-secret field beside it; an external credential
      (vacuous: no kind reads that table, stated in the test); a Library
      secret value — plus MCP `config.env` and `config.headers` values
      (sensitive and not), a provider base URL carrying a user-info password,
      a `?token=` query and a path segment token, an MCP address carrying a
      user-info password and a `?token=` query, and tokens planted in an MCP
      `_cache`'s `server_info`, `instructions` and `meta`. It calls every kind,
      with and without every valid name, and the unknown-name path, and
      asserts the serialized output contains no seeded value and no last four
      characters of one. Tokens placed in an MCP command argument and in an
      MCP address path segment **are** shown (asserted, so those residuals are
      deliberate).
- [ ] **Structural allowlist and classification**: each kind has a declared
      constant of the keys it may emit; a test fails if a view emits a key not
      in its constant, if a `kind` value has no view function, or if a kind
      has no entry in the parity driver.
- [ ] **Read-only by construction**: a test runs every kind and name and
      asserts that the aiosqlite connection's `total_changes` is unchanged and
      that a `sqlite_master` snapshot and `PRAGMA schema_version` are
      unchanged (`total_changes` counts only row changes, not DDL).
      `gleepglorp.load_settings` is checked not to write on first read.
- [ ] **A row that cannot be decrypted** (a stale key, `InvalidToken` on load)
      degrades to that item reading "unreadable (the encryption key changed)"
      in the list; the tool never raises.
- [ ] **Never an agent's notes text or chat content**: a seeded agent note and a
      seeded chat message with distinctive text never appear in any result.
- [ ] **Allowlist**: GleepGlorp's registered tool names are exactly
      `{"search_tools", "current_time", "read_app_config"}`
      (`test_the_minimal_allowlist` updated), its schema is in the starting set
      with exposure off, and no other agent gains the tool.
- [ ] **API untouched**: relative to the tree at this leg's start, this leg
      changes nothing in `api.py` or `secrets_api.py`; the API route tests pass
      unchanged.
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes under 350 s; ruff clean.
- [ ] Docs: `SECURITY-MODEL.md` "GleepGlorp's read surface" (what it reads, the
      whitelist views, the residual: a token in a command argument or in free
      text such as a system prompt, description, rule or routine prompt is
      shown as written and goes to the model provider; server-written MCP tool
      descriptions are capped and untrusted); `the_one/agents.md` ("GleepGlorp
      (M36)": the views module and the tool); CLAUDE.md (one paragraph). The
      corpus count is corrected to nine wherever it says eight (CLAUDE.md,
      `the_one/agents.md`, the `encryption_corpora.py` docstrings ~:1, ~:94).

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_views.py tests/test_gleepglorp_read_tool.py tests/test_gleepglorp_build.py -x --timeout 60`.
- Falsification reports for parity, classification, no-write and allowlist.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `git diff --stat -- the_one/interfaces/web/api.py the_one/interfaces/web/secrets_api.py` shows nothing from this leg.

## Implementation Guidance
1. **`views.py`.** One async function per kind (`overview_view(conn)`,
   `agents_view(conn, name=None)`, …), each building a plain dict from
   repositories in `the_one.db` (agents store, `LLMProviderRepository`,
   `MCPSourceRepository`, knowledge-base repositories, connector repository,
   routine repositories with the effective zone from `the_one.time_zones`,
   secret repository metadata, `ToolConfigRepository` with each tool's secret
   field names, `AgentRuleRepository`, `AgentNoteRepository` counts — add a
   read-only count method if none exists; usage via the agent store's
   `list_by_provider`/`list_by_kb`/`list_by_secret`/`list_by_mcp_source`).
   The repositories decrypt on load, so plaintext is in memory: the rule is
   **never emit** a secret field, enforced by building each output dict field
   by field against the kind's key constant. Catch a decrypt failure per row
   and degrade that item. A small `scrub_url(url, keep_path)` (drop user info
   and query; for providers drop the path too) and `cut(text, n)` live in the
   module. Reuse neutral helpers in `the_one` (routine `describe`,
   `the_one.tools.builtins` summaries, `the_one.mcp.oauth.storage`
   `OAUTH_MANAGED_SECRET_KEYS`, `time_zones.load_effective_zone`); re-implement
   small what exists only in `interfaces/web` (`_secret_field_names`, the
   provider `oauth_active` rule). The unknown-name message lists only that
   kind's names.
2. **The tool.** `ReadAppConfigTool(Tool)` per the tool-authorship contract
   in `the_one/agents.md`: `conn = await get_connection()` in `execute`
   (as `tools/connector_lookup.py` does; tests patch `get_connection` the way
   that tool's tests do, and the views take `conn` so they test directly);
   dispatch on `kind`; return `json.dumps(view, separators=(",", ":"))`; on a
   bad name return the plain message. Schema: `kind` enum of ten, `name`
   optional string; a one-paragraph description.
3. **Register** it in the GleepGlorp branch of `_build` beside
   `current_time`; the always-seed hook seeds it. Update the allowlist test.
4. **Tests.** A seeded-value table drives the parity test (one line per slot);
   the classification test iterates the `kind` enum; the no-write test reads
   `total_changes` on the underlying sqlite connection before and after.
5. **Docs** as the AC.

## Edge Cases
- **A name with odd characters**: looked up exactly; an unknown name lists the
  valid names.
- **An agent named like a token**: names are not secrets; the unknown-name list
  shows names only.
- **An MCP server with no `_cache`**: status "not checked yet".
- **No network from a read**: the tool never fetches model lists or tests
  connections.
- **Very large configurations**: list kinds stay short; an agent's prompt and a
  routine prompt are returned whole; tool descriptions are capped.
- **The agent detail and MCP credentials**: "attached MCP servers by name" reads
  `mcp_source_ids` only, never `mcp_overrides` values or the per-agent tool
  cache.
- **The self-configuration surface row**: listed as "Self-configuration (built
  in, controlled from the agent's Self-configuration tab)" with no credential
  and no address.

## Files Affected
- New: `the_one/gleepglorp/views.py`, `the_one/gleepglorp/read_tool.py`,
  `tests/test_gleepglorp_views.py`, `tests/test_gleepglorp_read_tool.py`.
- Changed: `the_one/agent/factory.py` (registration), `tests/test_gleepglorp_build.py`,
  `the_one/db/repositories.py` (a read-only count method, only if needed),
  `the_one/db/encryption_corpora.py` (docstrings only), `SECURITY-MODEL.md`,
  `the_one/agents.md`, CLAUDE.md.

## Citation Audit
From this leg's design review against the current tree (Leg 3 in it; Leg 4 in
progress). Re-locate by symbol.
- `the_one/db/encryption_corpora.py` ~:39-52 - nine `(table, column)` pairs - verified (review)
- `api.py` `_mcp_source_response` ~:3517 returns `config` after masking only `secrets`; `config.env` (~:3600) and `config.headers` (~:3568) values pass through - verified (review)
- `the_one/agents.md` ~:890 - agent `tool_overrides` never masked in the API view - verified (review)
- `api.py` `_emit_mask` ~:3373 shows a tail - verified (review)
- `tools/connector_lookup.py` ~:78-81 - `get_connection()` inside `execute` - verified (review)
- `db/connection.py` ~:45 - process-wide connection - verified (review)
- `factory.py` ~:733-737 always-seed hook; `tests/test_gleepglorp_build.py` ~:72 - verified (review)
- `routines/service.py` ~:179 `routine_view` needs a run repo and a zone - verified (review)
