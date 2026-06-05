# Leg: retention-field-and-persistence

**Status**: completed
**Flight**: [Retention Setting](../flight.md)

## Objective

Add the `chat_history_retention_days` field to `AgentConfig` with a 1–365 bound (default 30),
its v30 schema migration, the `save()` column, and the `_row_to_config()` decode — all in one
atomic leg so no agent load ever hits a missing column.

## Context

- **Flight DD1 (atomic leg)**: the Pydantic field, the v30 migration, the `save()` column, and
  the `_row_to_config()` decode must land together. `_row_to_config()` reads columns by name and
  `aiosqlite.Row[<missing>]` raises `IndexError` (in-code note at `db/repositories.py:239–242`);
  shipping the decode before the migration would crash every agent load on an un-migrated DB.
- **Flight DD2 (validation)**: bound the field with Pydantic `Field(ge=1, le=365, default=30)`.
  The POST (`the_one/interfaces/web/api.py:482`) and PUT (`:502`) endpoints already call
  `AgentConfig.model_validate(data)` and map `ValidationError → 422`
  (`the_one/interfaces/web/api.py:483–484`, `:503–504`), so the bound surfaces as a 422 with no
  endpoint changes.
- **Flight DD3 (DDL)**: `chat_history_retention_days INTEGER NOT NULL DEFAULT 30`. The constant
  default backfills existing agents to 30; the validator rejects `< 1`, so a stored value is
  always ≥ 1 and the decode reads the column directly (no `or 30` truthiness guard).
- **Flight DD4 (migration)**: additive ADD COLUMN, migration-only (no `SCHEMA_V1` edit), mirroring
  the v29 block (`schema.py:1794–1840`): PRAGMA `table_info(agents)` guard, ALTER, then
  `INSERT OR IGNORE INTO schema_version` last. Bump `CURRENT_VERSION = 30`. Hand-split the ALTER
  SQL across two lines (it is ~119 chars → exceeds `ruff` `line-length = 100`). Relax the two
  literal `assert CURRENT_VERSION == 29` pins to `>= 29`.
- This is the first of two legs; the General-tab UI is Leg 2 and depends on this field existing.

## Inputs

What exists before this leg runs:
- `the_one/agent/config.py` — `AgentConfig` with `max_iterations: int = 20` at `:265` (the
  "# Behavior" group at `:264`); `field_validator`/`Field` already imported at `:7`.
- `the_one/db/schema.py` — `CURRENT_VERSION = 29` (`:15`); `agents` table DDL in `SCHEMA_V1`
  (`:47–60`, does NOT carry the new column); v29 migration tail at `:1794–1840`.
- `the_one/db/repositories.py` — `save()` (`:121–173`), `_row_to_config()` (`:226+`),
  `max_iterations` decode `row["max_iterations"] or 20` (`:236`).
- `tests/test_db_migration.py` — two literal `assert CURRENT_VERSION == 29` pins (`:278`, `:5018`);
  `TestSchemaV29` class (`:5000+`) is the precedent for a `TestSchemaV30` class.
- `tests/test_config.py` — `AgentConfig` construction/default tests (`TestAgentConfigConstruction`).
- `tests/test_db_api.py` — round-trip precedent `test_create_agent_persists_connector_always_listen`
  (`:141`); 422 precedent `test_create_agent_with_outer_non_dict_tool_overrides_returns_422`
  (`:118`).

## Outputs

What exists after this leg completes:
- `AgentConfig.chat_history_retention_days: int = Field(default=30, ge=1, le=365)`.
- `CURRENT_VERSION == 30`; a v30 migration that adds
  `chat_history_retention_days INTEGER NOT NULL DEFAULT 30` to `agents` and backfills existing
  rows to 30, idempotent on re-run, partial-apply safe.
- `save()` persists the column; `_row_to_config()` decodes it directly.
- The two literal `== 29` version pins relaxed to `>= 29`.
- New tests: model boundary/reject (`test_config.py`), v30 migration (`test_db_migration.py`),
  API persistence round-trip + out-of-range 422 (`test_db_api.py`). All green.

## Acceptance Criteria

- [x] `AgentConfig(name="x").chat_history_retention_days == 30` (default).
- [x] `AgentConfig(name="x", chat_history_retention_days=1)` and `=365` construct successfully;
  `=0`, `=366`, and `=-5` each raise `pydantic.ValidationError`.
- [x] `CURRENT_VERSION == 30` and `the_one/db/schema.py` contains an `if version < 30:` block
  that adds `chat_history_retention_days INTEGER NOT NULL DEFAULT 30` to `agents`.
- [x] On a fresh DB, `ensure_schema` produces an `agents` table with the column present, typed
  `INTEGER`, NOT NULL, default 30; `MAX(schema_version.version) == 30`.
- [x] On a v29-shaped DB with an existing agent row, running `ensure_schema` adds the column and
  backfills the existing agent to `30`; re-running `ensure_schema` is a no-op (idempotent).
- [x] An agent saved with `chat_history_retention_days=90` reads back as `90` through
  `_row_to_config()` (full save→load round-trip).
- [x] `POST`/`PUT /api/agents` with `chat_history_retention_days` out of range returns HTTP 422.
- [x] The two literal `assert CURRENT_VERSION == 29` pins are relaxed to `>= 29`; the full unit
  suite for the touched files is green.
- [x] `ruff check` and `ruff format --check` pass on all changed files.

## Verification Steps

Run inside the container (project convention — NOT `docker compose exec`):

- Model: `docker exec the-one pytest tests/test_config.py -x --timeout 30`
- Migration: `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30`
- Round-trip + 422: `docker exec the-one pytest tests/test_db_api.py -x --timeout 30`
- Lint/format: `docker exec the-one ruff check the_one tests` and
  `docker exec the-one ruff format --check the_one tests`
- Schema version (quick check): `docker exec the-one python -c "from the_one.db.schema import CURRENT_VERSION; print(CURRENT_VERSION)"` → `30`

> A code edit requires `make rebuild` before the container reflects it (image-baked path).
> Rebuild once before running the in-container suite at leg-end.

## Implementation Guidance

1. **Add the Pydantic field** (`the_one/agent/config.py`, in the "# Behavior" group near `:264`)
   - Add beside `max_iterations`:
     `chat_history_retention_days: int = Field(default=30, ge=1, le=365)`
   - `Field` is already imported (`:7`). No custom `@field_validator` needed — the `ge`/`le`
     bound raises `ValidationError`, which the API maps to 422.

2. **Bump the schema version + add the v30 migration** (`the_one/db/schema.py`)
   - Change `CURRENT_VERSION = 29` → `30` (`:15`).
   - Append an `if version < 30:` block after the v29 block (`:1838`), mirroring the v29 ADD
     COLUMN shape. Include a comment naming the mission/flight/leg. Hand-split the ALTER SQL so
     no line exceeds 100 chars, e.g.:
     ```python
     if version < 30:
         # M13 F01 L01 — per-agent chat-history retention. Additive NOT NULL
         # column with a constant DEFAULT 30, which backfills existing agents
         # to the default 30-day policy (mission Open Q resolved). PRAGMA guard
         # + INSERT OR IGNORE last (partial-apply safe), mirroring v29.
         async with conn.execute("PRAGMA table_info(agents)") as cursor:
             agent_cols = {row[1] for row in await cursor.fetchall()}
         if "chat_history_retention_days" not in agent_cols:
             await conn.execute(
                 "ALTER TABLE agents ADD COLUMN "
                 "chat_history_retention_days INTEGER NOT NULL DEFAULT 30"
             )
         await conn.execute(
             "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (30,)
         )
         await conn.commit()
         version = 30
     ```
   - Do NOT edit `SCHEMA_V1` — a fresh DB runs every migration up to `CURRENT_VERSION`, so the
     v30 ALTER fires on fresh DBs too (the `connector_acls`/v18 precedent).

3. **Persist the column in `save()`** (`the_one/db/repositories.py:121–173`)
   - Add `chat_history_retention_days` to the INSERT column list, add one `?` to the `VALUES`
     tuple, add `chat_history_retention_days=excluded.chat_history_retention_days` to the
     `ON CONFLICT ... DO UPDATE SET` clause, and add `config.chat_history_retention_days` to the
     parameter tuple in the matching position.

4. **Decode in `_row_to_config()`** (`the_one/db/repositories.py:226+`)
   - Add `chat_history_retention_days=row["chat_history_retention_days"],` — read directly (no
     `or 30`): the column is NOT NULL DEFAULT 30 and the validator forbids `< 1`, so it is never
     NULL/0. The migration is the gate guaranteeing the column exists (same reasoning as the
     `tool_overrides` note at `:239–242`).

5. **Relax the version pins** (`tests/test_db_migration.py`)
   - Change the two literal `assert CURRENT_VERSION == 29` (`:278`, `:5018`) to `>= 29`, matching
     the v27/v28 `>= N` idiom at `:265`/`:272`. Update the adjacent assertion messages.

6. **Add tests**
   - `tests/test_config.py`: a default test (`== 30`), boundary tests (1 and 365 construct), and
     reject tests (`0`, `366`, `-5` → `pytest.raises(ValidationError)`).
   - `tests/test_db_migration.py`: a `TestSchemaV30` class mirroring `TestSchemaV29`'s three
     sub-tests — (a) fresh-DB-has-column (present, INTEGER, NOT NULL, default 30, head pointer
     30); (b) migration-on-v29-fixture (column added, existing agent backfilled to 30); and
     (c) an explicit idempotent-re-run test (second `ensure_schema` is a no-op). Write the new
     class-guard as `assert CURRENT_VERSION >= 30` (the `>= N` idiom this leg establishes), not
     a fresh literal.
   - `tests/test_db_api.py`: a persistence round-trip mirroring
     `test_create_agent_persists_connector_always_listen` (`:141`) — create/update an agent with
     `chat_history_retention_days=90`, GET it back, assert `90`; plus an out-of-range case
     (e.g. `400`) asserting HTTP 422 (mirror `:118`/`:129`).

7. **Rebuild + run** — `make rebuild`, then the in-container suite + ruff (see Verification).

## Edge Cases

- **Fresh DB vs migrated DB**: both must end with the column present — covered by the
  fresh-DB and v29-fixture migration tests. Do not special-case fresh DBs in `SCHEMA_V1`.
- **Idempotent re-run**: `ensure_schema` may run twice (test rewind harness); the PRAGMA guard +
  `INSERT OR IGNORE` make the second run a no-op. Assert this explicitly.
- **Existing agents backfill**: the `DEFAULT 30` on the ALTER backfills NULLs that would otherwise
  appear; verify an existing row reads `30`, not NULL.
- **Boundary exactness**: 1 and 365 are VALID (inclusive); 0 and 366 are INVALID. Test all four.
- **Position in the model**: field order in the Pydantic model is irrelevant to behavior; the
  "above Max Iterations" requirement is a UI-placement concern handled in Leg 2.

## Files Affected

- `the_one/agent/config.py` — add the `chat_history_retention_days` field.
- `the_one/db/schema.py` — bump `CURRENT_VERSION` to 30; add the v30 migration block.
- `the_one/db/repositories.py` — add the column to `save()` and `_row_to_config()`.
- `tests/test_db_migration.py` — relax two literal `== 29` pins; add `TestSchemaV30`.
- `tests/test_config.py` — add default/boundary/reject tests.
- `tests/test_db_api.py` — add persistence round-trip + out-of-range 422 tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (in-container; ruff clean)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight: (N/A — Leg 2 follows)
- [ ] Commit deferred to flight-level review (per `/agentic-workflow` deferred-commit model) — flight-level commit created at end of Flight 1
