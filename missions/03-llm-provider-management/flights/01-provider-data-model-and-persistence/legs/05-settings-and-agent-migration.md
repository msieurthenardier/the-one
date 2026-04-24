# Leg: settings-and-agent-migration

**Status**: completed
**Flight**: [Provider Data Model & Persistence](../flight.md)

## Objective

Remove static LLM env vars from Settings, update AgentConfig to reference providers by ID, update SQLiteAgentStore and AgentFactory for the v3 schema, and fix all 24 failing tests.

## Context

- Legs 01-04 completed: encryption module, schema v3 with `llm_providers` table, `LLMProviderRepository`, REST API endpoints
- Schema v3 removed `llm_provider` and `llm_base_url` columns from `agents` table, added `provider_config_id` FK
- `SQLiteAgentStore.save()` still references removed columns → 24 test failures in `test_db_api.py`, `test_db_migration.py`, `test_db_repositories.py`
- `AgentConfig` still has `llm_provider`, `llm_model`, `llm_base_url` fields — needs `provider_config_id` instead of `llm_provider`/`llm_base_url`
- `AgentFactory.create()` calls `get_provider(config.llm_provider, ...)` — needs to resolve provider config from DB
- `AgentFactory._default_config()` references `settings.llm_provider`, `settings.llm_model`, `settings.llm_base_url` — these will be removed
- `Settings` has `llm_provider`, `llm_model`, `llm_base_url` — to be removed
- `/api/info` in `app.py` references `settings.llm_provider` and `settings.llm_model`
- V1 DDL in `schema.py` still has `llm_provider`/`llm_base_url` columns — needs update for fresh DBs
- Provider type → LLMProvider class mapping: `ollama` and `openai-compatible` → `OllamaProvider`, `openai` → `OpenAIProvider`, `anthropic` → `AnthropicProvider`
- The `get_provider()` registry uses provider names: `ollama`, `openai`, `anthropic` — the config `type` field values must be mapped (e.g., `openai-compatible` → `ollama`)

## Inputs

- `the_one/config.py` — `Settings` with LLM env vars
- `the_one/agent/config.py` — `AgentConfig` with `llm_provider`, `llm_model`, `llm_base_url`
- `the_one/agent/factory.py` — `AgentFactory` with `get_provider()` call and `_default_config()`
- `the_one/db/repositories.py` — `SQLiteAgentStore` with old column references
- `the_one/db/schema.py` — V1 DDL with old columns
- `the_one/interfaces/web/app.py` — `/api/info` endpoint
- `the_one/interfaces/web/api.py` — agent CRUD endpoints (work with `AgentConfig.model_dump()`)
- `the_one/llm/registry.py` — `get_provider(name, **kwargs)` function

## Outputs

- Updated `Settings` (LLM vars removed)
- Updated `AgentConfig` (provider_config_id replaces llm_provider/llm_base_url)
- Updated `SQLiteAgentStore` (matches v3 schema)
- Updated `AgentFactory` (resolves provider from DB)
- Updated V1 DDL in `schema.py`
- Updated `/api/info` endpoint
- All 24 previously-failing tests fixed
- All existing tests pass

## Acceptance Criteria

- [x] `Settings` in `config.py` no longer has `llm_provider`, `llm_model`, or `llm_base_url` fields
- [x] `AgentConfig` replaces `llm_provider` and `llm_base_url` with `provider_config_id: str | None = None`; keeps `llm_model`
- [x] `SQLiteAgentStore.save()` writes to `provider_config_id` instead of `llm_provider`/`llm_base_url`
- [x] `SQLiteAgentStore._row_to_config()` reads `provider_config_id` instead of `llm_provider`/`llm_base_url`
- [x] `AgentFactory.create()` resolves provider config from DB via `LLMProviderRepository` when `provider_config_id` is set
- [x] `AgentFactory.create()` raises a clear error when `provider_config_id` is None (no default fallback)
- [x] `AgentFactory._default_config()` no longer references Settings LLM fields; returns config with `provider_config_id=None`
- [x] V1 DDL in `schema.py` updated: agents table uses `provider_config_id` instead of `llm_provider`/`llm_base_url`
- [x] `/api/info` endpoint no longer returns `provider` or `model` fields
- [x] `/api/settings` response no longer includes LLM fields
- [x] Provider type-to-registry mapping works: `ollama`→`ollama`, `openai-compatible`→`ollama`, `openai`→`openai`, `anthropic`→`anthropic`
- [x] `ruff check` passes on all modified files
- [x] `AgentConfig` has `model_config = {"extra": "ignore"}` so old JSON configs with `llm_provider`/`llm_base_url` fields don't break `FilesystemConfigStore.load()`
- [x] `ruff check` passes on all modified files
- [x] `pytest tests/ -v` — all tests pass (0 failures)

## Verification Steps

- `ruff check the_one/config.py the_one/agent/config.py the_one/agent/factory.py the_one/db/repositories.py the_one/db/schema.py the_one/interfaces/web/app.py` — no lint errors
- `pytest tests/ -v` — all tests pass

## Implementation Guidance

1. **Remove LLM fields from `Settings`** in `config.py`:
   - Delete `llm_provider`, `llm_model`, `llm_base_url` fields
   - Keep all other fields unchanged

2. **Update `AgentConfig`** in `agent/config.py`:
   - Remove `llm_provider` and `llm_base_url` fields
   - Add `provider_config_id: str | None = None`
   - Keep `llm_model` (model selection is per-agent)
   - Add `model_config = {"extra": "ignore"}` — this ensures `FilesystemConfigStore.load()` and `db/migration.py` can still deserialize old JSON configs that contain `llm_provider`/`llm_base_url` without raising `ValidationError`

3. **Update `SQLiteAgentStore`** in `db/repositories.py`:
   - **`save()`**: Replace `llm_provider`, `llm_base_url` column references with `provider_config_id`
   ```python
   async def save(self, config: AgentConfig) -> None:
       now = _now_iso()
       await self.conn.execute(
           """\
           INSERT INTO agents (
               name, description, provider_config_id, llm_model,
               system_prompt, enabled_tools, disabled_tools, max_iterations,
               kb_ids, mcp_source_ids, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
               description=excluded.description,
               provider_config_id=excluded.provider_config_id,
               llm_model=excluded.llm_model,
               system_prompt=excluded.system_prompt,
               enabled_tools=excluded.enabled_tools,
               disabled_tools=excluded.disabled_tools,
               max_iterations=excluded.max_iterations,
               kb_ids=excluded.kb_ids,
               mcp_source_ids=excluded.mcp_source_ids,
               updated_at=excluded.updated_at
           """,
           (
               config.name,
               config.description,
               config.provider_config_id,
               config.llm_model,
               config.system_prompt,
               json.dumps(config.enabled_tools) if config.enabled_tools is not None else None,
               json.dumps(config.disabled_tools),
               config.max_iterations,
               json.dumps(config.kb_ids),
               json.dumps(config.mcp_source_ids),
               now,
               now,
           ),
       )
       await self.conn.commit()
   ```
   - **`_row_to_config()`**: Replace `llm_provider`/`llm_base_url` with `provider_config_id`
   ```python
   @staticmethod
   def _row_to_config(row: aiosqlite.Row) -> AgentConfig:
       enabled = json.loads(row["enabled_tools"]) if row["enabled_tools"] else None
       return AgentConfig(
           name=row["name"],
           description=row["description"] or "",
           provider_config_id=row["provider_config_id"],
           llm_model=row["llm_model"] or "qwen2.5:7b",
           system_prompt=row["system_prompt"] or "",
           enabled_tools=enabled,
           disabled_tools=json.loads(row["disabled_tools"] or "[]"),
           max_iterations=row["max_iterations"] or 20,
           kb_ids=json.loads(row["kb_ids"] or "[]"),
           mcp_source_ids=json.loads(row["mcp_source_ids"] or "[]"),
       )
   ```

4. **Update `AgentFactory`** in `agent/factory.py`:
   - Add provider type-to-registry name mapping
   - Update `create()` to resolve provider config from DB
   - Update `_default_config()` to not reference Settings LLM fields
   ```python
   from the_one.db.connection import get_connection
   from the_one.db.repositories import LLMProviderRepository
   from the_one.encryption import get_encryptor

   # Map provider config type to LLM registry name
   _PROVIDER_TYPE_MAP = {
       "ollama": "ollama",
       "openai-compatible": "ollama",
       "openai": "openai",
       "anthropic": "anthropic",
   }

   class AgentFactory:
       ...
       async def create(self, name: str = "default") -> Agent:
           settings.ensure_dirs()
           config = await self._load_config(name)

           if config.provider_config_id is None:
               raise ValueError(
                   f"Agent '{name}' has no provider configured. "
                   "Please assign a provider in the agent settings."
               )

           # Resolve provider config from DB
           conn = await get_connection()
           encryptor = get_encryptor(settings.data_dir)
           provider_repo = LLMProviderRepository(conn, encryptor)
           provider_config = await provider_repo.get(config.provider_config_id)

           # Map config type to registry name
           registry_name = _PROVIDER_TYPE_MAP[provider_config.type]
           llm = get_provider(
               registry_name,
               model=config.llm_model,
               base_url=provider_config.base_url,
               api_key=provider_config.api_key,
           )
           ...

       def _default_config(self) -> AgentConfig:
           return AgentConfig(
               name="default",
               description="General-purpose agent with full tool access",
           )
   ```
   - Note: All three provider constructors (`OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`) accept `**kwargs`, so passing `api_key` universally is safe — unused kwargs are silently ignored.

5. **Update V1 DDL** in `schema.py`:
   - Replace `llm_provider`, `llm_base_url` columns with `provider_config_id` in the agents table definition
   - This ensures fresh databases get the correct schema from the start
   ```sql
   CREATE TABLE IF NOT EXISTS agents (
       name TEXT PRIMARY KEY,
       description TEXT DEFAULT '',
       provider_config_id TEXT REFERENCES llm_providers(id) ON DELETE SET NULL,
       llm_model TEXT DEFAULT 'qwen2.5:7b',
       system_prompt TEXT DEFAULT '',
       ...
   );
   ```
   - **Important**: V1 DDL must also include `llm_providers` table creation BEFORE the `agents` table (since agents references it). Move the `llm_providers` CREATE TABLE from v3 migration into V1 DDL.

6. **Update `/api/info`** in `app.py`:
   - Remove `provider` and `model` from the response dict
   ```python
   result: dict[str, Any] = {
       "version": "0.1.0",
   }
   ```

7. **Fix failing tests**:
   - **`tests/test_db_api.py`** (7 failures): Agent CRUD tests create `AgentConfig` with `llm_provider`/`llm_base_url` — update to use `provider_config_id`; update assertions accordingly
   - **`tests/test_db_repositories.py`** (14 failures): `SQLiteAgentStore` tests reference old fields — same pattern
   - **`tests/test_db_migration.py`** (3 failures): Migration tests check for old columns and use `AgentConfig(llm_provider=...)` — update to `provider_config_id`; the `test_preserves_all_fields` test should verify `provider_config_id` instead of `llm_provider`
   - **`tests/test_config.py`** (newly broken): Tests construct `AgentConfig` with `llm_provider="openai"` and assert on it — update to use `provider_config_id`; remove assertions on deleted fields
   - **`tests/test_factory.py`** (newly broken): Tests construct `AgentConfig(llm_provider="fake")` and mock `get_provider()` — update to mock the new provider resolution path (DB lookup via `LLMProviderRepository`); test both the "no provider" error case and the "valid provider" case
   - Key pattern: Replace `llm_provider="ollama", llm_base_url="http://..."` with `provider_config_id=None` (or a test provider ID if the test needs one)
   - For tests that need a working provider reference, create a test provider in `llm_providers` table first

## Edge Cases

- **`get_provider()` kwargs**: All three provider constructors accept `**kwargs`, so passing `api_key` universally is safe.
- **Existing agents with NULL provider_config_id**: After migration, all agents have NULL provider. `AgentFactory.create()` should raise a clear error — not silently fail.
- **Default agent**: `_default_config()` returns an agent with `provider_config_id=None`. This means the default agent won't work until a provider is configured. This is the intended behavior per flight design decisions.
- **`/api/settings` endpoint**: It serializes all `Settings.model_fields` — removing LLM fields from Settings automatically removes them from the response.
- **V1 DDL ordering**: `llm_providers` table must be defined BEFORE `agents` table in V1 DDL since agents has a FK reference to it.
- **Tests that create agents via API**: These may send `llm_provider` in request body — update to `provider_config_id`.
- **`/api/selftest` endpoint**: Calls `factory.create()` which will now raise `ValueError` for agents without a provider configured. This is expected — selftest is only meaningful after initial setup.
- **Old JSON config files**: `FilesystemConfigStore.load()` and `db/migration.py` deserialize old configs containing `llm_provider`/`llm_base_url`. Adding `model_config = {"extra": "ignore"}` to `AgentConfig` prevents `ValidationError`.
- **`direct_actions` field**: Exists in `AgentConfig` but is not persisted to the DB. This is a pre-existing gap — do not attempt to fix it in this leg.
- **`_PROVIDER_TYPE_MAP` KeyError**: Guard with a clear error if `provider_config.type` is not in the map, rather than relying on bare `KeyError`.

## Files Affected

- `the_one/config.py` — remove LLM fields from Settings
- `the_one/agent/config.py` — replace llm_provider/llm_base_url with provider_config_id
- `the_one/agent/factory.py` — resolve provider from DB, update _default_config
- `the_one/db/repositories.py` — update SQLiteAgentStore for v3 schema
- `the_one/db/schema.py` — update V1 DDL
- `the_one/interfaces/web/app.py` — fix /api/info
- `tests/test_db_api.py` — fix agent tests
- `tests/test_db_repositories.py` — fix agent store tests
- `tests/test_db_migration.py` — fix migration tests
- `tests/test_config.py` — update AgentConfig construction and assertions
- `tests/test_factory.py` — update to mock new provider resolution path

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
