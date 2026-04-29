# Leg: 02-schema-v8-tool-configs-and-overrides

**Status**: completed
**Flight**: [Cross-Platform Foundations & Policy Resolver](../flight.md)

## Objective

Add the persistence surface for the two-layer tool config model: bump schema 7 → 8, create the `tool_configs` SQLite table, add the `agents.tool_overrides` column, add a `ToolConfigRepository`, and add `tool_overrides: dict[str, dict[str, Any]] | None` to `AgentConfig` — without touching tools or the resolver.

## Context

This leg is independent of L1's platform package and a strict precondition for L3 (the resolver reads `tool_configs` and `AgentConfig.tool_overrides`). Per Decision 1 in `flight.md`, agent-level overrides live as a flat `tool_overrides: dict[str, dict[str, Any]] | None = None` field on `AgentConfig` (mirroring the `enabled_tools`/`disabled_tools` shape, NULL meaning "no overrides set"). Per Decision 8, the freshness contract is session-bound — values are read at `AgentFactory.create()` time only.

**Atomicity note from `flight.md` Technical Approach**: `aiosqlite` (wrapping stdlib `sqlite3`) in default `isolation_level=""` mode silently issues an implicit COMMIT before any non-DML statement (CREATE/ALTER/DROP). True multi-DDL transactions would require switching the connection to `isolation_level=None` (autocommit + manually-managed BEGIN/COMMIT). That connection-setup change is **explicitly deferred** as a maintenance task per the F1 debrief recommendation. F2 follows the **v4/v7 pattern** (individual `await conn.execute(...)` per DDL with `INSERT INTO schema_version` LAST) — NOT the v3/v5/v6 `executescript` pattern, which issues an implicit COMMIT *before* the first DDL and would defeat the LAST-INSERT idempotency. Idempotency is provided by `IF NOT EXISTS` + `PRAGMA table_info` guards; a partial apply leaves version=7 and `ensure_schema` retries cleanly on the next call. The `INSERT INTO schema_version` itself uses `INSERT OR IGNORE` to neutralize the narrow concurrent-`ensure_schema` PK-violation race window (v3/v5/v6/v7 all use bare `INSERT` and accept the same rare race; F2 closes it for the new path).

**Carryover from L1 flight log anomalies**: nothing here interacts with the L1 subprocess kill+reap fix, but L2 must not introduce another `executescript`-based migration that conflates DDL with version-bump (the implicit COMMIT defeats the LAST-INSERT idempotency).

### v7 baseline (verified at L2 design time)

- `the_one/db/schema.py:9` — `CURRENT_VERSION = 7`
- `the_one/db/schema.py:251-290` — v6→v7 migration (row-content strip; no DDL)
- `the_one/db/repositories.py:22-109` — `SQLiteAgentStore` with hard-coded 12-column INSERT/UPDATE
- `the_one/db/repositories.py:231-289` — `MCPSourceRepository` (closest template for `ToolConfigRepository`)
- `the_one/agent/config.py:33-66` — `AgentConfig` with `model_config = {"extra": "ignore"}` (so unknown JSON keys are silently dropped, which preserves forward/backward roundtrip cleanly)
- `the_one/interfaces/web/api.py:89-134` — `/api/agents` GET/POST/PUT use `cfg.model_dump()` and `AgentConfig.model_validate(data)`

## Inputs

What exists before this leg runs:

- L1 landed: `the_one/platform/` package exists; tools unchanged
- Schema is at v7
- `AgentConfig` has 10 fields (verified): `name`, `description`, `provider_config_id`, `llm_model`, `system_prompt`, `enabled_tools`, `disabled_tools`, `kb_ids`, `mcp_source_ids`, `max_iterations`
- `SQLiteAgentStore.save()` writes 12 columns (the 10 above plus `created_at`, `updated_at`) — line 47-83
- `MCPSourceRepository` exists as the closest CRUD template
- Branch: `flight/02-cross-platform-foundations` (continuing from L1)

## Outputs

What exists after this leg completes:

- `the_one/db/schema.py:CURRENT_VERSION = 8` and a v7→v8 migration block
- `tool_configs` SQLite table (PK `name`, `config TEXT DEFAULT '{}'`, `created_at`, `updated_at`)
- `agents.tool_overrides` TEXT column (nullable, default NULL)
- `ToolConfigRepository` in `the_one/db/repositories.py` with CRUD + `list_all() -> dict[str, dict]` (the resolver-facing read)
- `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None = None` field
- `SQLiteAgentStore.save()` extended to write 13 columns
- `SQLiteAgentStore._row_to_config()` deserializes `tool_overrides` JSON
- Tests: schema v8 migration, `ToolConfigRepository` CRUD, `AgentConfig.tool_overrides` Pydantic shape, `/api/agents` payload roundtrip
- Flight log + leg + flight artifact updated

## Acceptance Criteria

- [ ] `the_one/db/schema.py` declares `CURRENT_VERSION = 8` and contains a `if version < 8:` migration block that:
  - Creates `tool_configs` table via `CREATE TABLE IF NOT EXISTS` (re-run safe)
  - Adds `agents.tool_overrides` via `ALTER TABLE ... ADD COLUMN`, guarded by `PRAGMA table_info(agents)` to skip if the column already exists (re-run safe)
  - Issues each DDL via individual `await conn.execute(...)` calls (NOT `executescript`)
  - Inserts `schema_version=8` LAST so a partial apply leaves the version at 7 and the next `ensure_schema` retries cleanly
- [ ] `tool_configs` table shape matches `mcp_sources`: `name TEXT PRIMARY KEY`, `config TEXT DEFAULT '{}'`, `created_at TEXT NOT NULL DEFAULT (datetime('now'))`, `updated_at TEXT NOT NULL DEFAULT (datetime('now'))`
- [ ] `agents.tool_overrides` column exists and is nullable — verified by `PRAGMA table_info(agents)` returning a row with `name='tool_overrides'`, `type='TEXT'`, `notnull == 0` (column allows NULL); the migration omits an explicit `DEFAULT NULL` clause (SQLite columns are nullable by default; `PRAGMA table_info.dflt_value` would otherwise surface the literal string `"NULL"`, not Python `None`). Test asserts `dflt_value is None`.
- [ ] `AgentConfig` (in `the_one/agent/config.py`) gains a `tool_overrides: dict[str, dict[str, Any]] | None = None` field (use `dict[str, Any]` for the inner value type so Pydantic v2 actually validates the inner is a dict — bare `dict` is a parametric type and Pydantic enforces inner-value validation only when fully parameterized). Add `from typing import Any` to the imports if not present.
- [ ] `ToolConfigRepository` exists in `the_one/db/repositories.py` with the following methods (mirroring `MCPSourceRepository` shape but adapted for the `name`-keyed `tool_configs` table):
  - `__init__(conn: aiosqlite.Connection)`
  - `async def list() -> list[ToolConfig]` — returns all rows (operator-UI-facing; `list` shadows the builtin to match `MCPSourceRepository.list` consistency)
  - `async def list_all() -> dict[str, dict]` — returns `{name: config_dict}` (**this is the resolver-facing read; L3 imports `list_all`, NOT `list`**; convenience wrapper over `list()`)
  - `async def get(name: str) -> ToolConfig` — raises `KeyError` if missing
  - `async def upsert(name: str, config: dict) -> None` — INSERT or REPLACE; bumps `updated_at` on update. **L3 reads only**; the upsert path is exercised by tests in L2 and by F6's admin UI when it lands. F2 does not call `upsert` from the resolver or the factory.
  - `async def delete(name: str) -> None` — raises `KeyError` if missing
  - `async def exists(name: str) -> bool`
- [ ] A `ToolConfig` Pydantic model is added to `the_one/db/models.py` with `name: str`, `config: dict`, `created_at: str`, `updated_at: str` (mirrors `MCPSource` shape)
- [ ] `SQLiteAgentStore.save()` is extended to write the `tool_overrides` column (13 total). The `INSERT` column list, the `?` placeholder count, the `ON CONFLICT DO UPDATE SET` clause, and the value tuple are all updated in lockstep. JSON serialization: `json.dumps(config.tool_overrides) if config.tool_overrides is not None else None` (preserve NULL as NULL, mirroring `enabled_tools`).
- [ ] `SQLiteAgentStore._row_to_config()` deserializes `tool_overrides`: `json.loads(row["tool_overrides"]) if row["tool_overrides"] else None`. Use truthiness (matches the `enabled_tools` line at `repositories.py:97`); `aiosqlite.Row[<missing>]` raises `IndexError`, so missing-column safety comes from the v8 migration block having run, not from this expression. Don't change to `is not None` — empty-string and NULL must both deserialize to `None` for consistency with other columns.
- [ ] **Test: schema v8 migration on fresh DB** (`tests/test_db_migration.py::TestSchemaV8::test_v8_fresh_db_includes_tool_configs_and_tool_overrides`) — fresh SQLite DB → `ensure_schema` → `CURRENT_VERSION == 8`; `tool_configs` exists; `agents.tool_overrides` column exists; `SELECT * FROM tool_configs` returns no rows
- [ ] **Test: schema v8 migration on v7-fixture DB** — seed a v7-shaped `agents` row (with `enabled_tools` set), rewind `schema_version` to 7, re-run `ensure_schema`, assert (a) the agents row survives unchanged with `tool_overrides=NULL`, (b) `tool_configs` is now present and empty, (c) `schema_version` is 8. Pattern mirrors the existing `TestSchemaV7` rewind technique.
- [ ] **Test: schema v8 migration is idempotent** — call `ensure_schema` twice on a fresh DB; second call is a no-op (no errors, no duplicate `schema_version` rows for v8)
- [ ] **Test: chained v6→v7→v8 migration** — seed a v6-shaped DB (rewind `schema_version` to 6 after a fresh ensure), run `ensure_schema`, assert (a) the v7 row-content strip ran, (b) the v8 DDL ran, (c) `schema_version` lands at 8 with both 7 and 8 rows present. Catches "v7 + v8 apply in sequence leave agents in a weird state" bugs.
- [ ] **Test: regression — missing v8 block is loudly caught** — the fresh-DB v8 test must specifically assert that `tool_configs` exists AND that `agents.tool_overrides` exists. If a future bump to `CURRENT_VERSION = 9` accidentally drops the v8 block, the v8 fresh-DB assertions must fail with a clear "table tool_configs missing" / "column tool_overrides missing" message — not a silent pass via short-circuited `_get_version()`. Test failure messages must mention both names explicitly.
- [ ] **Test: `ToolConfigRepository` CRUD** (`tests/test_db_repositories.py`) — upsert/list/list_all/get/delete/exists; `upsert` updates an existing row's `config` and `updated_at`; `list_all()` returns the dict shape `{name: config_dict}`
- [ ] **Test: `AgentConfig.tool_overrides` Pydantic shape** (`tests/test_config.py`) — defaults to `None`; explicit `{"shell": {"timeout": 30}}` roundtrips through `model_dump` → `model_validate` cleanly; `model_config["extra"] == "ignore"` survives a stale `direct_actions: true` payload (regression check from F1)
- [ ] **Test: `/api/agents` payload roundtrip** (`tests/test_db_api.py`) — GET `/api/agents/{name}` includes `"tool_overrides"` key with value `null` for an agent that has no overrides; POST `/api/agents` with explicit `tool_overrides` dict roundtrips correctly through GET; POST with `tool_overrides=[1,2,3]` (a list) raises 422 Pydantic validation error; POST with `tool_overrides={"shell": "not-a-dict"}` (inner non-dict) ALSO raises 422 (this only works because the inner type is `dict[str, Any]`, not bare `dict`)
- [ ] **Test: `SQLiteAgentStore` save/load roundtrip with `tool_overrides`** (extend `tests/test_db_repositories.py` or `test_store.py`) — saving an agent with `tool_overrides={"shell": {"timeout": 30}}`, reloading, asserts the dict roundtrips
- [ ] All pre-existing tests pass unchanged (no regressions) — `make test-unit` returns the same pass/fail set as on the L1 branch tip plus the new tests
- [ ] No source code modified outside `the_one/db/`, `the_one/agent/config.py`, `the_one/interfaces/web/api.py` (only if the API needs a change — see Edge Cases), and `tests/`

## Verification Steps

```bash
# DDL inspection (in container after make rebuild) — uses TemporaryDirectory
# pattern matching the rest of the test suite (avoids tempfile open-handle
# semantics that bite SQLite on non-POSIX platforms).
docker exec the-one python -c "
import asyncio, aiosqlite, tempfile, pathlib
from the_one.db.schema import ensure_schema, CURRENT_VERSION
async def main():
    assert CURRENT_VERSION == 8
    with tempfile.TemporaryDirectory() as d:
        db_path = pathlib.Path(d) / 'test.db'
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await ensure_schema(conn)
        async with conn.execute('PRAGMA table_info(agents)') as cur:
            cols = {r[1]: (r[2], r[3], r[4]) for r in await cur.fetchall()}
        assert 'tool_overrides' in cols, cols
        assert cols['tool_overrides'][0] == 'TEXT'
        assert cols['tool_overrides'][1] == 0  # notnull=0 → column is nullable
        assert cols['tool_overrides'][2] is None  # no DEFAULT clause
        async with conn.execute(
            \"SELECT name FROM sqlite_master WHERE type='table' AND name='tool_configs'\"
        ) as cur:
            assert (await cur.fetchone()) is not None
        await conn.close()
asyncio.run(main())
print('OK')
"

# Migration tests
docker exec the-one pytest tests/test_db_migration.py::TestSchemaV8 -v

# Repository tests
docker exec the-one pytest tests/test_db_repositories.py -v -k 'ToolConfig or tool_overrides'

# Config + API tests
docker exec the-one pytest tests/test_config.py tests/test_db_api.py -v

# Full suite
make test-unit
```

## Implementation Guidance

1. **Add `ToolConfig` model to `the_one/db/models.py`**

   Mirror `MCPSource` shape:

   ```python
   class ToolConfig(BaseModel):
       name: str
       config: dict
       created_at: str
       updated_at: str
   ```

2. **Schema v8 migration (`the_one/db/schema.py`)**

   - Bump `CURRENT_VERSION = 8`
   - Append after the v6→v7 block:

     ```python
     if version < 8:
         # Tool-level config table (mirrors mcp_sources shape).
         await conn.execute("""\
     CREATE TABLE IF NOT EXISTS tool_configs (
         name TEXT PRIMARY KEY,
         config TEXT DEFAULT '{}',
         created_at TEXT NOT NULL DEFAULT (datetime('now')),
         updated_at TEXT NOT NULL DEFAULT (datetime('now'))
     )""")

         # Idempotent ADD COLUMN: skip if column already exists.
         # NOTE: omit `DEFAULT NULL` — SQLite columns are nullable by default,
         # and an explicit `DEFAULT NULL` clause surfaces in PRAGMA table_info
         # as the literal string "NULL" rather than Python None.
         async with conn.execute("PRAGMA table_info(agents)") as cur:
             cols = {row[1] for row in await cur.fetchall()}
         if "tool_overrides" not in cols:
             await conn.execute(
                 "ALTER TABLE agents ADD COLUMN tool_overrides TEXT"
             )

         # schema_version INSERT goes LAST — partial apply leaves version=7,
         # next ensure_schema retries cleanly. INSERT OR IGNORE neutralizes
         # the narrow concurrent-ensure_schema PK-violation race; older
         # migrations (v3/v5/v6/v7) have the same exposure with bare INSERT.
         await conn.execute(
             "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (8,)
         )
         await conn.commit()
         version = 8
     ```

   - Use `await conn.execute(...)` per statement, NOT `executescript`. The `executescript` form issues an implicit COMMIT and would defeat the LAST-INSERT idempotency.

3. **Add `ToolConfigRepository` to `the_one/db/repositories.py`**

   - Use `MCPSourceRepository` (lines 231-289) as the structural template; adapt:
     - PK is `name` (string), not `id` (UUID)
     - No `type` column
     - `upsert` uses `INSERT ... ON CONFLICT(name) DO UPDATE SET config=excluded.config, updated_at=excluded.updated_at` (no separate create/update — operators set tool config by name; the row exists or it doesn't)
     - `list_all() -> dict[str, dict]` is the resolver-facing convenience wrapper:

       ```python
       async def list_all(self) -> dict[str, dict]:
           items = await self.list()
           return {item.name: item.config for item in items}
       ```

   - Import `ToolConfig` at the top of the file alongside the other model imports.

4. **Extend `AgentConfig` in `the_one/agent/config.py`**

   Add `from typing import Any` near the top if not already imported. Add the field after `mcp_source_ids`:

   ```python
   # Tool-level constraint overrides (per-agent narrowing or substitution).
   # None means "no overrides set" (uses tool-level defaults).
   tool_overrides: dict[str, dict[str, Any]] | None = None
   ```

   No `Field(default_factory=...)` — the explicit `None` default is the locked-down NULL semantic (Decision 1). Use `dict[str, Any]` for the inner value (NOT bare `dict`) so Pydantic v2 actually validates that each tool's override is a dict, not a list/string.

5. **Update `SQLiteAgentStore` in `the_one/db/repositories.py`**

   - `save()` (lines 47-83):
     - Extend INSERT column list from 12 to 13 columns: add `tool_overrides` after `mcp_source_ids`
     - Add a `?` to the VALUES placeholder list
     - Add `tool_overrides=excluded.tool_overrides` to the `ON CONFLICT DO UPDATE SET` clause
     - Add to the value tuple (after `json.dumps(config.mcp_source_ids)`):
       ```python
       json.dumps(config.tool_overrides) if config.tool_overrides is not None else None,
       ```
   - `_row_to_config()` (lines 95-109):
     - Add to the `AgentConfig(...)` constructor call:
       ```python
       tool_overrides=(
           json.loads(row["tool_overrides"]) if row["tool_overrides"] else None
       ),
       ```
       Use truthiness, not `is not None`, to handle both NULL and empty string identically (mirrors the `enabled_tools` line above).

6. **Verify `/api/agents` handlers (`the_one/interfaces/web/api.py:89-134`)**

   These use `cfg.model_dump()` and `AgentConfig.model_validate(data)` — Pydantic field auto-add means **no API code change required**. The new field will appear in payloads as `"tool_overrides": null` for agents with no overrides. Confirm by reading the handlers; if they hand-pick fields anywhere (they don't, as of this leg's prerequisites), update accordingly.

7. **Tests** (under `tests/`):

   - `tests/test_db_migration.py::TestSchemaV8` — three tests as specified in AC; reuse the `TestSchemaV7` rewind pattern for the v7-fixture test
   - `tests/test_db_repositories.py` — add a `TestToolConfigRepository` class with CRUD coverage; add an `SQLiteAgentStore` roundtrip test for `tool_overrides`
   - `tests/test_config.py` — add tests for the new field's default, roundtrip, and `extra: "ignore"` regression check
   - `tests/test_db_api.py` — add `/api/agents` GET/POST tests covering the new field, including the malformed-payload 422 case

8. **Run `make test-unit`** — all green modulo pre-existing CSS-token red.

## Edge Cases

- **Pre-existing v7 agent rows on upgrade**: `ALTER TABLE ADD COLUMN tool_overrides TEXT` populates existing rows with `NULL` (SQLite's default for nullable columns without an explicit DEFAULT clause). Decision 1's locked-down NULL semantic is preserved (no agent-level overrides until an operator sets them).
- **Concurrent `ensure_schema` calls**: Two simultaneous `ensure_schema` invocations on the same DB could both try the v8 block. SQLite serializes writes; the loser's `CREATE TABLE IF NOT EXISTS` is a no-op, the loser's `PRAGMA table_info` sees the new column (or doesn't, depending on timing), the loser's `ALTER TABLE` is guarded out. The losing `INSERT INTO schema_version` would normally raise `IntegrityError` on the PK (`version` is `PRIMARY KEY`); v8 closes this with `INSERT OR IGNORE` (`MAX(version)` reads still return 8, harmless). v3/v5/v6/v7 use bare `INSERT` and accept the narrow race exposure — F2 doesn't backport the fix to older paths.
- **`tool_overrides` JSON with malformed structure**: Pydantic's `dict[str, dict[str, Any]] | None` validates structure at `model_validate()` time. A list, a string, or `{"shell": "not-a-dict"}` raises `ValidationError` (the inner `dict[str, Any]` parameter is what makes the `"not-a-dict"` case fail; bare `dict` would silently accept it). The `/api/agents` POST handler turns this into a 422; tests assert both the outer-non-dict and inner-non-dict cases.
- **`ToolConfigRepository.upsert` race**: two simultaneous upserts of the same name. SQLite's row-level locking serializes them; the last `updated_at` wins. Acceptable.
- **`tool_configs` row that's empty `'{}'`**: counts as "tool exists in operator's config but no overrides set." Resolver in L3 will treat this identically to a missing row — `list_all()` returns `{name: {}}` for the empty case, and L3's resolver short-circuits when both sides are empty. No special handling needed in L2.
- **Forward-reference: cache freshness contract** (per `/leg` skill section 6): the resolver's session-bound contract (Decision 8) means an operator's mid-session edit to a `tool_configs` row does NOT affect the running agent. F2 does not implement caching — `ToolConfigRepository.list_all()` reads fresh on every call. The "cache" is the resolved `Tool.Config` instance held by each tool, populated once at `AgentFactory.create()` (L3). F6's admin UI must communicate "applies to next session." L2 has no caching surface itself; documenting here so L3/F6 don't accidentally introduce one.
- **State-machine reachability** (per `/leg` skill section 5): the `tool_overrides=NULL` state must be reachable. ALTER TABLE without an explicit DEFAULT (combined with SQLite's nullable-by-default semantics) ensures NULL is the value for pre-existing rows. No FK constraint on `agents.tool_overrides` (it's a JSON blob, not a reference). No CASCADE behavior to inspect. Verified: `tests/browser/seeders.py:75-80` builds POST payloads with explicit field whitelisting (Pydantic forward-fills `tool_overrides=None`); no browser test asserts negative field membership on GET responses. `tests/test_db_api.py` and `tests/test_flow_*.py` likewise don't pin payload field counts. Expected `tool_overrides` match count before this leg: 0.

## Files Affected

- `the_one/db/schema.py` — bump `CURRENT_VERSION`, add v7→v8 migration block
- `the_one/db/models.py` — add `ToolConfig` Pydantic model
- `the_one/db/repositories.py` — add `ToolConfigRepository`; extend `SQLiteAgentStore.save()` and `_row_to_config()` for `tool_overrides`
- `the_one/agent/config.py` — add `tool_overrides` field to `AgentConfig`
- `tests/test_db_migration.py` — new `TestSchemaV8` class (3 tests)
- `tests/test_db_repositories.py` — new `TestToolConfigRepository` class (CRUD); extend agent-store roundtrip test
- `tests/test_config.py` — new `tool_overrides` field tests
- `tests/test_db_api.py` — new `/api/agents` `tool_overrides` payload tests
- `missions/05-built-in-tool-system/flights/02-cross-platform-foundations-and-policy-resolver/flight-log.md` — append L2 progress entry
- `missions/05-built-in-tool-system/flights/02-cross-platform-foundations-and-policy-resolver/flight.md` — check off L2

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (per agentic-workflow batched-review pattern, Developer does NOT commit; review and commit happen once at flight end):

- [ ] All acceptance criteria verified
- [ ] New schema/repo/config/API tests passing
- [ ] Pre-existing unit suite still green (modulo pre-existing CSS-token red)
- [ ] Update flight-log.md with L2 progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off L2 in flight.md
- [ ] Do NOT commit — final commit happens once after L7
