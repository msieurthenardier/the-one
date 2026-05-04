# Leg: 00-schema-v9-tool-config-enabled

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Land schema v9 — an idempotent `ALTER TABLE tool_configs ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1` — and widen the `ToolConfig` Pydantic model + `ToolConfigRepository` so the storage layer can persist and round-trip a per-tool `enabled: bool` flag. F1-F5 surfaces continue working unchanged (existing rows decode `enabled=True` via the column default; downstream call sites do not yet read or enforce the flag — that's L1). Folded in: shift `_ensure-playwright` out of the `rebuild` chain and into `test-browser` / `test-pixel`, so the L7 Playwright env gap is closed before L7 runs without making routine `make rebuild` slow.

## Context

- **F6 mission goal**: a per-tool admin section in Studio. The first thing the UI must be able to express is "this tool is operator-disabled" — independent of the per-agent `enabled_tools` / `disabled_tools` whitelist semantics. That state lives on the `tool_configs` row (operator-set, tool-keyed), not on the agent row.
- **Why a schema bump rather than smuggling `enabled` into `tool_configs.config` JSON**: the resolver's `list_all()` returns `{name: config_dict}` and the resolver semantics treat an empty `config` dict identically to a missing row. Smuggling `enabled` into that dict would require teaching the resolver about the magic key, which leaks UI concerns into the resolver. Promoting `enabled` to a row-level column keeps `config` purely about resolver-bound settings.
- **F6 Decision 1** (schema-test-pattern): per F5 debrief recommendation 3, the new TestV9Migration class follows the parallel structure already established by TestSchemaV8 — fresh-v9 + v8→v9-with-rows + idempotent + chained-from-v6. Architect was asked to confirm the parallel structure choice; no deviation.
- **F6 Decision 12** (two-Reviewer-pass batching): L0 commits no docs. Documentation (CLAUDE.md "Tool Authorship Contract" updates; CURRENT_VERSION bump notes; admin section overview) is deferred to L9 post-Reviewer.
- **Bonus folded in (per F5 debrief / mission Known Issue F1-2)**: `make rebuild` currently re-runs `_ensure-playwright` even though browser tests are not part of the rebuild verification. This makes routine dev cycles slow without benefit, and (per F1-2 Known Issue) the `test-browser` and `test-pixel` targets that actually need playwright do NOT prereq it, so a fresh `make rebuild` can leave the Playwright install cache wiped exactly when L7 needs it. Fix: remove the `_ensure-playwright` invocation from `rebuild` and `rebuild-clean`; add it as a `@$(MAKE) --no-print-directory _ensure-playwright` prereq inside `test-browser` and `test-pixel`.

## Inputs

- `the_one/db/schema.py:9` — `CURRENT_VERSION = 8`.
- `the_one/db/schema.py:292-336` — v8 migration block (idempotent ADD COLUMN pattern, OR IGNORE on schema_version, individual `await conn.execute(...)` calls instead of `executescript`). v9 follows the same shape.
- `the_one/db/models.py:61-73` — `ToolConfig(BaseModel)` (4 fields: name, config, created_at, updated_at).
- `the_one/db/repositories.py:308-388` — `ToolConfigRepository` (`list`, `list_all`, `get`, `upsert`, `delete`, `exists`, `_row_to_model`).
- `tests/test_db_migration.py:210-419` — `TestSchemaV8` class (4 tests: fresh-v8, v7→v8, idempotent, v6→v7→v8 chained); the `assert CURRENT_VERSION == 8` pin lives at line 233 in `test_v8_fresh_db_includes_tool_configs_and_tool_overrides`.
- `Makefile:21-26` — `rebuild` target (currently invokes `_ensure-playwright` after the build).
- `Makefile:28-35` — `rebuild-clean` target (same).
- `Makefile:37-48` — `_ensure-playwright` internal target (preserved unchanged).
- `Makefile:111-117` — `test-browser` and `test-pixel` (currently do NOT prereq `_ensure-playwright`).

## Outputs

- `the_one/db/schema.py`:
  - `CURRENT_VERSION = 9`.
  - New `if version < 9:` block — idempotent guard via `PRAGMA table_info(tool_configs)`; `await conn.execute("ALTER TABLE tool_configs ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")` only if absent; `INSERT OR IGNORE INTO schema_version (version) VALUES (9)` LAST.
- `the_one/db/models.py`:
  - `ToolConfig` gains `enabled: bool = True` (default keeps F1-F5 round-trips green: nothing in the call graph yet sets it, so omitted-field construction lands on `True`).
- `the_one/db/repositories.py`:
  - `_row_to_model` decodes `bool(row["enabled"])` from the INTEGER column.
  - `upsert(name, config, enabled=True)` — gains the new keyword with default `True` so all existing call sites work unchanged. INSERT writes `int(enabled)`; ON CONFLICT clause adds `enabled=excluded.enabled`. Upsert SQL changes from a 4-column INSERT to a 5-column INSERT.
  - `list` and `get` are inherently covered because they delegate to `_row_to_model`.
- `tests/test_db_migration.py`:
  - The pin at line ~233 — `assert CURRENT_VERSION == 8` — flips to `assert CURRENT_VERSION == 9`. The accompanying message string ("must be 8 after L2") becomes "must be 9 after F6 L0" so the diagnostic on a future bump points to the right place.
  - New `TestSchemaV9` class with parallel structure to `TestSchemaV8`:
    - `test_v9_fresh_db_has_enabled_column_with_default_1` — fresh DB; assert `CURRENT_VERSION == 9`; assert `enabled` column on `tool_configs` (TEXT-or-INTEGER `type == "INTEGER"`, `notnull == 1`, `dflt_value == "1"`); `tool_configs` empty.
    - `test_v9_migration_on_v8_fixture_db_preserves_existing_rows` — fresh ensure_schema, seed a `tool_configs` row, rewind `schema_version` to 8 (DELETE WHERE version = 9), re-run ensure_schema, assert the row survives with `enabled == 1`.
    - `test_v9_migration_is_idempotent` — call `ensure_schema` twice on a fresh DB; assert exactly one row in schema_version for v9; column still present.
    - `test_v8_to_v9_chained_migration` — fresh migrate, seed a v8-shaped `tool_configs` row (4-column INSERT with no `enabled`), rewind to 8, re-run, assert row's `enabled` is 1 (the column default).
- `tests/test_db_repositories.py` — extend the existing `TestToolConfigRepository` class (line 342) using the existing `tool_config_repo` fixture (line 61). Do NOT create a new test file. The new tests are additive — existing tests at lines 342-426 must pass UNCHANGED:
  - `test_upsert_default_enabled_true` — upsert without `enabled` arg, list, expect `enabled is True`.
  - `test_upsert_persists_enabled_false` — `upsert("foo", {}, enabled=False)`, get → `enabled is False`.
  - `test_upsert_round_trips_enabled_true_after_false` — `upsert("foo", {}, enabled=False)` → `upsert("foo", {}, enabled=True)` → get → `enabled is True`.
  - `test_list_all_omits_enabled` — assert `list_all()` still returns `{name: config_dict}` shape AND explicitly `"enabled" not in result["foo"]` (the resolver-facing API is intentionally unchanged in L0; L1 adds the admin read path via `list()`).
  - `test_pydantic_coerces_int_to_bool_for_enabled` — `ToolConfig(name="x", enabled=1)` → `m.enabled is True`. Cheap insurance against a future code path constructing from a raw row tuple instead of `aiosqlite.Row`.
- `Makefile`:
  - `rebuild`: drop the `@$(MAKE) --no-print-directory _ensure-playwright` line.
  - `rebuild-clean`: drop the `@$(MAKE) --no-print-directory _ensure-playwright` line.
  - `test-browser`: prepend `@$(MAKE) --no-print-directory _ensure-playwright` before the `docker exec ... pytest -m browser ...` line (same `@$(MAKE)` form to suppress the "Entering directory" noise).
  - `test-pixel`: prepend `@$(MAKE) --no-print-directory _ensure-playwright` before the pytest line.
  - `_ensure-playwright` body unchanged.

## Acceptance Criteria

- [x] `the_one/db/schema.py` defines `CURRENT_VERSION = 9` and a `if version < 9:` migration block that idempotently adds the `enabled INTEGER NOT NULL DEFAULT 1` column to `tool_configs`.
- [x] The v9 migration uses individual `await conn.execute(...)` calls (NOT `executescript`), guards the ADD COLUMN with `PRAGMA table_info(tool_configs)`, and the `INSERT OR IGNORE INTO schema_version` runs LAST.
- [x] `ToolConfig` Pydantic model has `enabled: bool = True`. Constructing `ToolConfig(name="x")` (no `enabled` arg) produces `enabled is True`.
- [x] `ToolConfigRepository._row_to_model` decodes `enabled` from INTEGER → bool.
- [x] `ToolConfigRepository.upsert` accepts an optional `enabled: bool = True` keyword, encodes `int(enabled)`, and updates `enabled=excluded.enabled` in the ON CONFLICT clause. All existing call sites continue to work without passing the keyword.
- [x] `ToolConfigRepository.list_all()` shape is unchanged — still `{name: config_dict}`. The admin-facing read path that surfaces `enabled` is L1's responsibility.
- [x] `tests/test_db_migration.py` line ~233 pin updates from `assert CURRENT_VERSION == 8` to `assert CURRENT_VERSION == 9` (and the message string updates accordingly).
- [x] New `TestSchemaV9` class exercises four scenarios (fresh v9 / v8 → v9 with seeded row / idempotent / v8 → v9 chained), parallel to `TestSchemaV8`.
- [x] New tests added to `TestToolConfigRepository` (`tests/test_db_repositories.py:342`) cover default-true round-trip, persisting `enabled=False`, flipping `False → True` via upsert, `list_all()` shape preservation (with explicit `"enabled" not in` assertion), and Pydantic int→bool coercion.
- [x] **Existing `TestToolConfigRepository` tests (lines 342-426 of `tests/test_db_repositories.py`) pass unchanged after model widening — no edits to the existing methods.**
- [x] `make test-unit` is green (modulo the pre-existing `tests/test_token_definitions.py::test_every_var_reference_is_defined` red, deselected as in F5 verification).
- [x] `Makefile` no longer invokes `_ensure-playwright` from `rebuild` or `rebuild-clean`. `test-browser` and `test-pixel` invoke it as a prereq.
- [x] `make rebuild` succeeds and does NOT run `playwright install` (verified by absence of "Installing playwright chromium" output during a normal rebuild). *(Verified via `make -n rebuild` static inspection per leg's verification step 7; destructive run not exercised.)*
- [x] `make test-browser` (or even an explicit `make _ensure-playwright`) installs the chromium cache when missing. *(Verified via `make -n test-browser` static inspection — `_ensure-playwright` prereq fires before the pytest line.)*
- [x] `ruff check` clean on touched files. *(Pre-existing `N806 REMOVED` warning in v7 block of `the_one/db/schema.py:261` is unrelated and not introduced by this leg.)*
- [x] No call site outside `the_one/db/{schema,models,repositories}.py` changes in this leg. (L1 owns the resolver / factory / API surface changes.)

## Verification Steps

```bash
# 1. Schema constant + migration block shape
docker exec the-one python -c "
from the_one.db.schema import CURRENT_VERSION
assert CURRENT_VERSION == 9, CURRENT_VERSION
print('OK CURRENT_VERSION == 9')
"

# 2. Model widening + default
docker exec the-one python -c "
from the_one.db.models import ToolConfig
m = ToolConfig(name='x')
assert m.enabled is True, m.enabled
m2 = ToolConfig(name='y', enabled=False)
assert m2.enabled is False, m2.enabled
print('OK ToolConfig.enabled default True / explicit False')
"

# 3. End-to-end migration + repo round-trip on a temp DB
docker exec the-one python -c "
import asyncio, tempfile, aiosqlite
from pathlib import Path
from the_one.db.schema import ensure_schema
from the_one.db.repositories import ToolConfigRepository

async def main():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / 'v9-roundtrip.db'
        conn = await aiosqlite.connect(str(db))
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA foreign_keys=ON')
        await ensure_schema(conn)
        repo = ToolConfigRepository(conn)
        await repo.upsert('shell', {'timeout_sec_default': 30.0})
        items = await repo.list()
        assert len(items) == 1 and items[0].enabled is True, items
        await repo.upsert('shell', {'timeout_sec_default': 30.0}, enabled=False)
        got = await repo.get('shell')
        assert got.enabled is False, got
        await conn.close()
asyncio.run(main())
print('OK upsert/list/get round-trip on enabled')
"

# 4. Idempotent re-run on already-v9 DB
docker exec the-one python -c "
import asyncio, tempfile, aiosqlite
from pathlib import Path
from the_one.db.schema import ensure_schema

async def main():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / 'v9-idem.db'
        conn = await aiosqlite.connect(str(db))
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA foreign_keys=ON')
        await ensure_schema(conn)
        await ensure_schema(conn)  # second call must be a no-op
        async with conn.execute('SELECT COUNT(*) FROM schema_version WHERE version = 9') as cur:
            row = await cur.fetchone()
        assert row[0] == 1, row[0]
        await conn.close()
asyncio.run(main())
print('OK v9 idempotent')
"

# 5. Targeted test runs
docker exec the-one pytest tests/test_db_migration.py -x -q
docker exec the-one pytest tests/test_db_migration.py::TestSchemaV9 -x -q
# (Run repo tests if they exist — verify file path during implementation.)

# 6. Full unit suite (modulo pre-existing CSS-token red)
docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# 7. Makefile bonus — STATIC inspection (avoids destructive rebuild during dev)
#    Verify rebuild no longer references _ensure-playwright; test-browser/test-pixel do.
grep -E '^\s*@?\$\(MAKE\).*_ensure-playwright' Makefile  # should NOT match inside rebuild/rebuild-clean blocks
make -n rebuild 2>&1 | grep -i 'playwright' && echo 'FAIL: rebuild dry-run mentions playwright' || echo 'OK rebuild dry-run silent on playwright'
make -n test-browser 2>&1 | grep -q '_ensure-playwright' && echo 'OK test-browser prereqs ensure-playwright' || echo 'FAIL: test-browser missing prereq'
make -n test-pixel 2>&1 | grep -q '_ensure-playwright' && echo 'OK test-pixel prereqs ensure-playwright' || echo 'FAIL: test-pixel missing prereq'
# (Optional, post-implementation: actually run `make rebuild` once to confirm side-effect — destructive, container restart.)

# 8. Lint
docker exec the-one ruff check the_one/db/schema.py the_one/db/models.py the_one/db/repositories.py tests/test_db_migration.py
```

## Implementation Guidance

1. **Bump the schema constant** at `the_one/db/schema.py:9`:

   ```python
   CURRENT_VERSION = 9
   ```

2. **Append the v9 migration block** at the end of `ensure_schema` (after the v8 block, mirroring v8's structure):

   ```python
       if version < 9:
           # Add `enabled` column to tool_configs so the F6 admin UI can
           # operator-disable a tool without touching per-agent allow/deny
           # lists. Default 1 (true) keeps every pre-v9 row enabled.
           #
           # Idempotency follows the v8 pattern: PRAGMA-check the column
           # presence so a re-run after partial-apply is a no-op, and
           # leave the schema_version INSERT for LAST. Use individual
           # `await conn.execute(...)` calls (NOT `executescript`) so the
           # implicit COMMIT stays out of the way.
           async with conn.execute("PRAGMA table_info(tool_configs)") as cursor:
               existing_cols = {row[1] for row in await cursor.fetchall()}
           if "enabled" not in existing_cols:
               await conn.execute(
                   "ALTER TABLE tool_configs ADD COLUMN "
                   "enabled INTEGER NOT NULL DEFAULT 1"
               )

           await conn.execute(
               "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (9,)
           )
           await conn.commit()
           version = 9
   ```

3. **Widen the model** at `the_one/db/models.py`:

   ```python
   class ToolConfig(BaseModel):
       """A tool-level config row — operator-set defaults for a built-in tool.

       Mirrors `MCPSource` shape but keyed by `name` (the tool's stable
       identifier). The resolver composes this with a per-agent override
       dict from `AgentConfig.tool_overrides` at `AgentFactory.create()`
       time (session-bound; mid-session edits do not affect running agents).

       `enabled` (added in schema v9) is operator-set tool-level on/off.
       Disabled tools are filtered out of the registry at L1's enforcement
       point — independent of per-agent enabled_tools / disabled_tools.
       """

       name: str
       config: dict = Field(default_factory=dict)
       enabled: bool = True
       created_at: str = Field(default_factory=_now_iso)
       updated_at: str = Field(default_factory=_now_iso)
   ```

4. **Update the repository** at `the_one/db/repositories.py`:

   - `upsert` signature gains `enabled: bool = True`:

     ```python
     async def upsert(self, name: str, config: dict, enabled: bool = True) -> None:
         """INSERT or REPLACE the config row, bumping `updated_at` on update.

         `enabled` defaults to True so existing call sites (resolver,
         factory) continue to work without modification. The F6 admin
         UI is the first caller to pass `enabled=False`.

         Caveat: ON CONFLICT writes `enabled=excluded.enabled`, which
         means a config-only update that omits the kwarg will silently
         re-enable a previously-disabled row. Callers that want to
         update only `config` (keeping the existing `enabled` state)
         must read first via `get(name)` and pass the existing flag.
         The L1 admin PUT endpoint sends the full row state, so the
         "last write wins" semantics are intentional for that surface.
         """
         await self.conn.execute(
             """\
             INSERT INTO tool_configs (name, config, enabled, created_at, updated_at)
             VALUES (?, ?, ?, ?, ?)
             ON CONFLICT(name) DO UPDATE SET
                 config=excluded.config,
                 enabled=excluded.enabled,
                 updated_at=excluded.updated_at
             """,
             (name, json.dumps(config), int(enabled), _now_iso(), _now_iso()),
         )
         await self.conn.commit()
     ```

   - `_row_to_model` gains the `enabled` field (decode INTEGER → bool):

     ```python
     @staticmethod
     def _row_to_model(row: aiosqlite.Row) -> ToolConfig:
         return ToolConfig(
             name=row["name"],
             config=json.loads(row["config"] or "{}"),
             enabled=bool(row["enabled"]),
             created_at=row["created_at"],
             updated_at=row["updated_at"],
         )
     ```

   - `list_all()` is unchanged (still returns `{name: config_dict}`). The admin-grid read path that needs `enabled` will call `list()` (which returns full models) in L1.

5. **Update the v8 pin in `tests/test_db_migration.py`** at line ~233:

   ```python
   assert CURRENT_VERSION == 9, (
       f"CURRENT_VERSION must be 9 after F6 L0 (got {CURRENT_VERSION})"
   )
   ```

6. **Add `TestSchemaV9`** to `tests/test_db_migration.py`, mirroring `TestSchemaV8`:

   ```python
   class TestSchemaV9:
       """Tests for the v9 migration that adds tool_configs.enabled."""

       async def test_v9_fresh_db_has_enabled_column_with_default_1(
           self, tmp_path
       ) -> None:
           from the_one.db.schema import CURRENT_VERSION

           db_path = tmp_path / "v9-fresh.db"
           conn = await aiosqlite.connect(str(db_path))
           conn.row_factory = aiosqlite.Row
           await conn.execute("PRAGMA foreign_keys=ON")
           await ensure_schema(conn)

           assert CURRENT_VERSION == 9, CURRENT_VERSION

           async with conn.execute("PRAGMA table_info(tool_configs)") as cur:
               cols = {r["name"]: r for r in await cur.fetchall()}
           assert "enabled" in cols
           col = cols["enabled"]
           assert col["type"] == "INTEGER", col["type"]
           assert col["notnull"] == 1, col["notnull"]
           # SQLite stores the literal text of the DEFAULT clause.
           # Stringify to avoid aiosqlite-version-dependent type quirks.
           assert str(col["dflt_value"]) == "1", col["dflt_value"]

           # Behavioural cross-check: an INSERT that omits `enabled`
           # lands on 1 via the column DEFAULT. The PRAGMA assertion
           # is the schema; this is the contract.
           await conn.execute(
               "INSERT INTO tool_configs (name, config) VALUES (?, ?)",
               ("default-check", json.dumps({})),
           )
           await conn.commit()
           async with conn.execute(
               "SELECT enabled FROM tool_configs WHERE name = 'default-check'"
           ) as cur:
               r = await cur.fetchone()
           assert r["enabled"] == 1, r["enabled"]

           async with conn.execute(
               "SELECT MAX(version) FROM schema_version"
           ) as cur:
               row = await cur.fetchone()
           assert row[0] == 9

           await conn.close()

       async def test_v9_migration_on_v8_fixture_db_preserves_existing_rows(
           self, tmp_path
       ) -> None:
           db_path = tmp_path / "v9-from-v8.db"
           conn = await aiosqlite.connect(str(db_path))
           conn.row_factory = aiosqlite.Row
           await conn.execute("PRAGMA foreign_keys=ON")
           await ensure_schema(conn)

           # Seed a tool_configs row directly (4-column-shaped INSERT
           # would have been the v8 form; on v9 the column default
           # supplies enabled=1 for an INSERT that omits it).
           await conn.execute(
               "INSERT INTO tool_configs (name, config) VALUES (?, ?)",
               ("preexisting", json.dumps({"timeout_sec_default": 30.0})),
           )

           # Rewind to v8.
           await conn.execute("DELETE FROM schema_version WHERE version = 9")
           await conn.commit()

           # Re-run — idempotent guard skips ALTER, INSERT OR IGNORE skips dup.
           await ensure_schema(conn)

           async with conn.execute(
               "SELECT name, config, enabled FROM tool_configs WHERE name = 'preexisting'"
           ) as cur:
               row = await cur.fetchone()
           assert row is not None
           assert json.loads(row["config"]) == {"timeout_sec_default": 30.0}
           assert row["enabled"] == 1

           async with conn.execute(
               "SELECT MAX(version) FROM schema_version"
           ) as cur:
               row = await cur.fetchone()
           assert row[0] == 9

           await conn.close()

       async def test_v9_migration_is_idempotent(self, tmp_path) -> None:
           db_path = tmp_path / "v9-idempotent.db"
           conn = await aiosqlite.connect(str(db_path))
           conn.row_factory = aiosqlite.Row
           await conn.execute("PRAGMA foreign_keys=ON")

           await ensure_schema(conn)
           await ensure_schema(conn)

           async with conn.execute(
               "SELECT COUNT(*) FROM schema_version WHERE version = 9"
           ) as cur:
               row = await cur.fetchone()
           assert row[0] == 1

           async with conn.execute("PRAGMA table_info(tool_configs)") as cur:
               cols = {r["name"] for r in await cur.fetchall()}
           assert "enabled" in cols

           await conn.close()

       async def test_v8_to_v9_chained_migration(self, tmp_path) -> None:
           """Rewind to v8, seed a v8-shaped row (no enabled column at
           insert time logically — the column default supplies 1), then
           run the v9 ADD COLUMN. The seeded row must have enabled=1."""
           db_path = tmp_path / "v9-chain.db"
           conn = await aiosqlite.connect(str(db_path))
           conn.row_factory = aiosqlite.Row
           await conn.execute("PRAGMA foreign_keys=ON")
           await ensure_schema(conn)

           await conn.execute(
               "INSERT INTO tool_configs (name, config) VALUES (?, ?)",
               ("chained", json.dumps({})),
           )
           await conn.execute("DELETE FROM schema_version WHERE version = 9")
           await conn.commit()

           await ensure_schema(conn)

           async with conn.execute(
               "SELECT enabled FROM tool_configs WHERE name = 'chained'"
           ) as cur:
               row = await cur.fetchone()
           assert row["enabled"] == 1

           await conn.close()
   ```

7. **Extend `TestToolConfigRepository`** in `tests/test_db_repositories.py` (existing class at line 342, existing `tool_config_repo` fixture at line 61). Append the new test methods to the class — do NOT touch the existing methods. Use `from the_one.db.models import ToolConfig` for the coercion test:

   ```python
       # ── L0: enabled flag round-trips ───────────────────────────────

       async def test_upsert_default_enabled_true(
           self, tool_config_repo: ToolConfigRepository
       ) -> None:
           await tool_config_repo.upsert("shell", {})
           items = await tool_config_repo.list()
           assert len(items) == 1
           assert items[0].enabled is True

       async def test_upsert_persists_enabled_false(
           self, tool_config_repo: ToolConfigRepository
       ) -> None:
           await tool_config_repo.upsert("shell", {}, enabled=False)
           got = await tool_config_repo.get("shell")
           assert got.enabled is False

       async def test_upsert_round_trips_enabled_true_after_false(
           self, tool_config_repo: ToolConfigRepository
       ) -> None:
           await tool_config_repo.upsert("shell", {}, enabled=False)
           await tool_config_repo.upsert("shell", {}, enabled=True)
           got = await tool_config_repo.get("shell")
           assert got.enabled is True

       async def test_list_all_omits_enabled(
           self, tool_config_repo: ToolConfigRepository
       ) -> None:
           # The resolver-facing list_all() must stay {name: config_dict}.
           # Admin read path in L1 uses list() (which returns full models).
           await tool_config_repo.upsert("shell", {"timeout": 1}, enabled=False)
           result = await tool_config_repo.list_all()
           assert result == {"shell": {"timeout": 1}}
           # Explicit guard: enabled must not leak into the resolver dict.
           assert "enabled" not in result["shell"]

       async def test_pydantic_coerces_int_to_bool_for_enabled(self) -> None:
           # Insurance for any future code path that builds ToolConfig
           # from a raw row tuple instead of an aiosqlite.Row.
           from the_one.db.models import ToolConfig
           m = ToolConfig(name="x", enabled=1)
           assert m.enabled is True
   ```

8. **Makefile bonus** — touch four targets:

   - `rebuild`: drop `@$(MAKE) --no-print-directory _ensure-playwright`, keep `verify-serving`.
   - `rebuild-clean`: same.
   - `test-browser`: prepend `@$(MAKE) --no-print-directory _ensure-playwright` before the pytest line.
   - `test-pixel`: same.

   The `_ensure-playwright` target body is unchanged. Help-comment text on `test-browser` / `test-pixel` may add `(installs playwright if missing)` for clarity.

9. **Run the verification block** above and paste the relevant `pytest -q` summary into the flight log entry for L0.

## Edge Cases

- **`PRAGMA table_info` returns existing columns**: the v9 guard mirrors v8's pattern exactly. A re-run on an already-v9 DB sees `enabled` in `existing_cols`, skips the `ALTER`, hits `INSERT OR IGNORE` on the version row (which is a no-op because v9 already exists), and exits cleanly.
- **`bool(row["enabled"])` decoding**: SQLite stores 0/1. `bool(0)` is `False`, `bool(1)` is `True`. Pre-v9 rows that survive the migration land with `enabled=1` via the column DEFAULT — never `NULL`, because the column is `NOT NULL`.
- **Pydantic `bool` field accepts `0`/`1`**: defensive in case any future code path constructs a model from a raw integer. Default coercion is fine; no `field_validator` needed.
- **`upsert` with `enabled=True` on an already-disabled row**: ON CONFLICT DO UPDATE writes `enabled=excluded.enabled` (which is `1`), re-enabling. This is intentional — the operator's last write wins for both `config` and `enabled`. The admin UI in L3/L4 will write the full row state on save.
- **`list_all()` API stability**: this leg deliberately does NOT enrich `list_all()`'s shape with `enabled`. The resolver / factory / `get_tools()` chain stays unchanged in L0. L1 introduces the admin-facing read (which uses `list()` returning models) and the enforcement point (which decides whether to filter `disabled` tools out of the registry build).
- **F1-F5 callers of `upsert`**: the architect noted no current call site outside the repo's own tests passes `enabled`. Default-True keyword argument keeps every existing call ABI-compatible.
- **`rebuild` Makefile change observability**: the help text on `rebuild` says "REQUIRED after editing JS/CSS/Python". Removing the `_ensure-playwright` line does not change that contract — the rebuild still rebuilds and verifies; only the surprise playwright install is shifted to where it's actually needed.
- **`test-browser` / `test-pixel` newline-with-prefix Make pattern**: ensure the new `@$(MAKE) ...` line is part of the same target body (tab-indented, before the existing `docker exec ...` line). A Makefile editor can collapse whitespace if not careful — verify with `make -n test-browser` to confirm both lines fire in order.

## Files Affected

- `the_one/db/schema.py` — bump `CURRENT_VERSION` to 9; append v9 migration block.
- `the_one/db/models.py` — add `enabled: bool = True` to `ToolConfig`.
- `the_one/db/repositories.py` — widen `upsert` signature; update `_row_to_model`; SQL adds `enabled` column.
- `tests/test_db_migration.py` — flip line ~233 pin; add `TestSchemaV9` class.
- `tests/test_db_repositories.py` — extend `TestToolConfigRepository` (line 342) with 5 new test methods using the existing `tool_config_repo` fixture. No edits to existing methods.
- `Makefile` — drop `_ensure-playwright` from `rebuild` / `rebuild-clean`; add as prereq to `test-browser` / `test-pixel`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `tests/test_db_migration.py` and any new repo tests passing
- [ ] `make test-unit` green (modulo CSS-token deselect)
- [ ] `make rebuild` no longer mentions playwright; `make test-browser` does install if cache absent
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
