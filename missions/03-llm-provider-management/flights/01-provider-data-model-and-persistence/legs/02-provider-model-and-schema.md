# Leg: provider-model-and-schema

**Status**: completed
**Flight**: [Provider Data Model & Persistence](../flight.md)

## Objective

Add the `LLMProviderConfig` Pydantic model and schema migration v3 that creates the `llm_providers` table and rebuilds the `agents` table to reference providers by ID instead of free-text fields.

## Context

- Leg 01 completed: `the_one/encryption.py` exists with `Encryptor` class, `cryptography` is in dependencies
- Flight design decisions: provider configs have 12-char hex IDs, type is a Literal of 4 values, agents reference providers via `provider_config_id` FK with ON DELETE SET NULL
- Schema v2 is current. The v2 migration already uses the table-rebuild pattern (create new, copy, drop, rename) — this leg follows the same pattern
- The `llm_providers` table must be created BEFORE rebuilding `agents` since the FK references it
- The `agents` table drops `llm_provider` and `llm_base_url` columns, adds `provider_config_id`, keeps `llm_model`
- Existing agents will have NULL `provider_config_id` after migration

## Inputs

- `the_one/db/models.py` — existing Pydantic models (KnowledgeBase, KBItem, MCPSource, ChatSession)
- `the_one/db/schema.py` — schema at version 2 with V1 DDL and V2 migration
- `the_one/agent/config.py` — `AgentConfig` with `llm_provider`, `llm_model`, `llm_base_url` fields (NOT modified in this leg — that's leg 05)

## Outputs

- `LLMProviderConfig` model added to `the_one/db/models.py`
- Schema migration v3 added to `the_one/db/schema.py` (`CURRENT_VERSION = 3`)
- Tests for the migration in `tests/test_schema.py`

## Acceptance Criteria

- [x] `LLMProviderConfig` Pydantic model exists in `the_one/db/models.py` with fields: `id` (str), `name` (str), `type` (Literal["ollama", "openai-compatible", "openai", "anthropic"]), `base_url` (str), `api_key` (str | None, default None), `config` (dict, default empty), `created_at` (str), `updated_at` (str)
- [x] `CURRENT_VERSION` in `schema.py` is `3`
- [x] Migration v3 creates `llm_providers` table with columns: `id TEXT PRIMARY KEY`, `name TEXT NOT NULL`, `type TEXT NOT NULL` with CHECK constraint for the 4 types, `base_url TEXT NOT NULL`, `api_key TEXT` (stores encrypted value), `config TEXT DEFAULT '{}'`, `created_at`, `updated_at`
- [x] Migration v3 rebuilds `agents` table: drops `llm_provider` and `llm_base_url` columns, adds `provider_config_id TEXT REFERENCES llm_providers(id) ON DELETE SET NULL`
- [x] Existing agent data (name, description, llm_model, system_prompt, tools, etc.) is preserved through the rebuild — `provider_config_id` is NULL for migrated rows
- [x] `chat_sessions` FK to `agents` still works after the rebuild (the agents PK `name` is unchanged)
- [x] Migration v3 wraps the table rebuild in `PRAGMA foreign_keys=OFF` / `PRAGMA foreign_keys=ON` to prevent cascade deletion of `chat_sessions`
- [x] Chat sessions referencing agents survive the migration (verified by test)
- [x] `ruff check the_one/db/models.py the_one/db/schema.py` passes
- [x] `pytest tests/test_schema.py -v` passes

## Verification Steps

- `python -c "from the_one.db.models import LLMProviderConfig; print(LLMProviderConfig.model_fields.keys())"` — shows expected fields
- `ruff check the_one/db/models.py the_one/db/schema.py` — no lint errors
- `pytest tests/test_schema.py -v` — all tests pass
- `python -m pytest tests/ -v --timeout=30` — all existing tests still pass

## Implementation Guidance

1. **Add `LLMProviderConfig` to `the_one/db/models.py`**
   ```python
   class LLMProviderConfig(BaseModel):
       """An LLM provider connection configuration."""

       id: str
       name: str
       type: Literal["ollama", "openai-compatible", "openai", "anthropic"]
       base_url: str
       api_key: str | None = None
       config: dict = Field(default_factory=dict)
       created_at: str = Field(default_factory=_now_iso)
       updated_at: str = Field(default_factory=_now_iso)
   ```

2. **Do NOT update SCHEMA_V1 DDL** in this leg. The V1 DDL still uses `llm_provider`/`llm_base_url` columns because `SQLiteAgentStore.save()` still writes to those columns. Updating V1 DDL is deferred to leg 05 when the repository is also updated. Fresh databases will reach the correct schema via v1→v2→v3 migrations.

3. **Add v3 migration** to `ensure_schema()`. **Critical: wrap in `PRAGMA foreign_keys=OFF/ON`** to prevent `DROP TABLE agents` from cascade-deleting `chat_sessions` rows:
   ```python
   if version < 3:
       await conn.executescript("""\
   PRAGMA foreign_keys=OFF;

   CREATE TABLE IF NOT EXISTS llm_providers (
       id TEXT PRIMARY KEY,
       name TEXT NOT NULL,
       type TEXT NOT NULL CHECK (type IN ('ollama', 'openai-compatible', 'openai', 'anthropic')),
       base_url TEXT NOT NULL,
       api_key TEXT,
       config TEXT DEFAULT '{}',
       created_at TEXT NOT NULL DEFAULT (datetime('now')),
       updated_at TEXT NOT NULL DEFAULT (datetime('now'))
   );

   CREATE TABLE IF NOT EXISTS agents_new (
       name TEXT PRIMARY KEY,
       description TEXT DEFAULT '',
       provider_config_id TEXT REFERENCES llm_providers(id) ON DELETE SET NULL,
       llm_model TEXT DEFAULT 'qwen2.5:7b',
       system_prompt TEXT DEFAULT '',
       enabled_tools TEXT,
       disabled_tools TEXT DEFAULT '[]',
       max_iterations INTEGER DEFAULT 20,
       kb_ids TEXT DEFAULT '[]',
       mcp_source_ids TEXT DEFAULT '[]',
       created_at TEXT NOT NULL DEFAULT (datetime('now')),
       updated_at TEXT NOT NULL DEFAULT (datetime('now'))
   );

   INSERT INTO agents_new (name, description, llm_model, system_prompt,
       enabled_tools, disabled_tools, max_iterations, kb_ids, mcp_source_ids,
       created_at, updated_at)
       SELECT name, description, llm_model, system_prompt,
       enabled_tools, disabled_tools, max_iterations, kb_ids, mcp_source_ids,
       created_at, updated_at FROM agents;

   DROP TABLE agents;

   ALTER TABLE agents_new RENAME TO agents;

   PRAGMA foreign_keys=ON;
   """)
       await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (3,))
       await conn.commit()
   ```

   Note: `provider_config_id` is not in the INSERT SELECT — it defaults to NULL for migrated rows. The `llm_provider` and `llm_base_url` columns are not copied to the new table.

4. **Update `CURRENT_VERSION`** to `3`

5. **Create `tests/test_schema.py`**
   - Test fresh database: `ensure_schema` on empty DB creates all tables including `llm_providers` (via v3 migration). Agents table still has `llm_provider`/`llm_base_url` from V1 DDL, plus `provider_config_id` from v3 migration
   - Test v2→v3 migration: create a v2 database with sample agents and chat sessions, run `ensure_schema`, verify:
     - `llm_providers` table exists
     - `agents` table has `provider_config_id` column
     - `agents` table does NOT have `llm_provider` or `llm_base_url` columns
     - Existing agent data is preserved (name, description, llm_model, etc.)
     - `provider_config_id` is NULL for migrated agents
     - `chat_sessions` with FK to agents still work
   - Use `aiosqlite.connect(":memory:")` for fast in-memory tests

## Edge Cases

- **chat_sessions FK cascade on DROP TABLE**: With `PRAGMA foreign_keys=ON`, `DROP TABLE agents` triggers CASCADE deletion of all `chat_sessions` rows. The migration MUST wrap the rebuild in `PRAGMA foreign_keys=OFF` / `PRAGMA foreign_keys=ON` to prevent this. This was caught in design review — the v2 migration didn't hit this because it rebuilt the child table (chat_sessions), not the parent table (agents).
- **Empty agents table**: Migration should work fine — INSERT INTO SELECT with 0 rows is valid.
- **`direct_actions` column**: The `agents` table in the DB may have a `direct_actions` column from `AgentConfig` if any v1 configs were saved with it. Check if this column exists in v2 schema — it's in `AgentConfig` but NOT in the v1 DDL. If it was added dynamically, the migration needs to handle it. Looking at the V1 DDL, `direct_actions` is NOT in the schema, so it won't be an issue.

## Files Affected

- `the_one/db/models.py` — add `LLMProviderConfig` class
- `the_one/db/schema.py` — add v3 migration (V1 DDL NOT updated), bump CURRENT_VERSION
- `tests/test_schema.py` — new file (migration tests)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
