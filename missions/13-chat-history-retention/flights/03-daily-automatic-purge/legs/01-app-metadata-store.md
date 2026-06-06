# Leg: app-metadata-store

**Status**: completed
**Flight**: [Daily Automatic Purge](../flight.md)

## Objective

Add a global key/value metadata store — a v31 schema migration creating an `app_metadata` table plus an `AppMetadataRepository` (get/set/upsert) — to hold the daily purge's global `last_purge_at` timestamp, with the migration, table, repository, and tests all landing together (atomic-migration leg).

## Context

- **Design decision DD1** (flight): `last_purge_at` is global (one daily sweep covers all agents), so it belongs in a single kv row, not a per-agent column. No app-metadata/kv/settings table exists today; this leg creates one. A DB table keeps the timestamp transactional with the sweep (Leg 3 writes it inside the sweep) and persists in the same SQLite file the app already manages.
- **Atomic-leg requirement**: F1's v30 column migration taught the lesson that a schema change and its read/write paths must land in one leg to avoid a half-applied state being observable. Here the surface is smaller (a brand-new table, not an `ALTER` to a hot table), but the discipline holds: migration + repository + tests in this single leg.
- **This leg ships no consumer yet** — Leg 3 wires `get`/`set` into the sweep. This leg delivers the store and proves it round-trips. That is intentional and acceptable: the table and repo are inert until Leg 3, and shipping them first keeps Leg 3 focused on the sweep logic.
- **Contract pinned for Leg 3** (resolving the flight's DD1 acceptable-variation): this leg commits to **generic `get(key)` / `set(key, value)`**, and Leg 3 will call `get("last_purge_at")` / `set("last_purge_at", <iso>)` — NOT purpose-named `get_last_purge_at` accessors. Keep the key string `"last_purge_at"` as the agreed contract between the two legs.

## Inputs

What exists before this leg runs:
- `the_one/db/schema.py` with `CURRENT_VERSION = 30` (`:15`) and the v30 migration block ending at `version = 30` (`:1863`).
- The migration idiom: each `if version < N:` block does its DDL then `INSERT OR IGNORE INTO schema_version (version) VALUES (N)` + `commit()` + `version = N` (v30 precedent at `:1842–1863`; for the new-table shape see `CREATE TABLE IF NOT EXISTS connector_accounts` in the **v13** block (`schema.py ~:491–541`) or `pending_approvals` in the **v21** block (`schema.py ~:839–910`)).
- `the_one/db/repositories.py` housing the async repositories (each takes an `aiosqlite.Connection` in `__init__`; e.g. `SQLiteAgentStore` at `:71`, `ToolConfigRepository`'s upsert idiom `INSERT … ON CONFLICT(name) DO UPDATE SET … = excluded.…` at `:872–882`).
- Test fixtures: `tests/test_db_repositories.py` `conn` fixture (`:22–35`) builds a fresh DB via `ensure_schema`; `tests/test_db_migration.py` imports `CURRENT_VERSION, ensure_schema` (`:16`) and asserts `schema_version` reaches `CURRENT_VERSION` (`:192–199`).

## Outputs

What exists after this leg completes:
- `the_one/db/schema.py`: `CURRENT_VERSION = 31`; a new `if version < 31:` block creating `app_metadata`.
- `the_one/db/repositories.py`: a new `AppMetadataRepository` class with `get(key) -> str | None` and `set(key, value) -> None` (upsert).
- `tests/test_db_migration.py`: a test that a v30 DB migrates to v31 with `app_metadata` present and `schema_version` = 31.
- `tests/test_db_repositories.py`: a fixture + tests for `AppMetadataRepository` (absent-key → None; set-then-get roundtrip; set-twice upserts without error).

## Acceptance Criteria

- [ ] `CURRENT_VERSION == 31` in `the_one/db/schema.py`.
- [ ] A v31 migration block creates `app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)` via `CREATE TABLE IF NOT EXISTS`, then records `schema_version` 31 with `INSERT OR IGNORE`, committing — following the v30 idiom (and the v13/v21 new-table shape); idempotent / re-runnable after a partial apply.
- [ ] Running `ensure_schema` on a fresh DB and on a DB stamped at v30 both end at `schema_version == 31` with `app_metadata` present (a table-exists check on `sqlite_master`).
- [ ] `AppMetadataRepository(conn)` exposes `async get(key) -> str | None` (returns `None` for an absent key, the stored string otherwise) and `async set(key, value) -> None` (inserts or updates; calling it twice for the same key does not raise and leaves the latest value).
- [ ] Unit tests cover: migration reaches v31 + table present; `get` of an absent key → `None`; `set`-then-`get` roundtrip; `set` twice upserts (no `UNIQUE`/`PRIMARY KEY` violation, latest value wins).
- [ ] `ruff check` and `ruff format --check` pass on all changed files.
- [ ] The full touched unit suites pass (`test_db_migration.py`, `test_db_repositories.py`).

## Verification Steps

- `docker exec the-one python -c "from the_one.db.schema import CURRENT_VERSION; print(CURRENT_VERSION)"` → prints `31`.
- `docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py -x --timeout 30` → green, including the new tests.
- `docker exec the-one ruff check the_one/db/schema.py the_one/db/repositories.py tests/test_db_migration.py tests/test_db_repositories.py` and `docker exec the-one ruff format --check <same files>` → clean.
- Manual table check: `docker exec the-one python -c "import asyncio, aiosqlite; from the_one.db.schema import ensure_schema; ..."` (or rely on the migration test) confirming `app_metadata` exists after `ensure_schema`.

## Implementation Guidance

1. **Bump the version constant** (`schema.py:15`)
   - `CURRENT_VERSION = 30` → `31`.

2. **Add the v31 migration block** immediately after the v30 block (`schema.py:1863`, after `version = 30`)
   - Mirror the new-table idiom (v13 `connector_accounts` / v21 `pending_approvals`), not the `ALTER` idiom. Use `conn.execute(...)` for the single `CREATE TABLE` (as v30 does); `executescript` is only needed for multi-statement blocks:
     ```python
     if version < 31:
         # M13 F03 L01 — global app-metadata kv store. Holds the daily
         # purge's `last_purge_at` (Leg 3). Brand-new table, so CREATE TABLE
         # IF NOT EXISTS (idempotent / partial-apply safe), then stamp the
         # version with INSERT OR IGNORE last, mirroring v21/v30.
         await conn.execute(
             "CREATE TABLE IF NOT EXISTS app_metadata ("
             "    key TEXT PRIMARY KEY,"
             "    value TEXT NOT NULL"
             ")"
         )
         await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (31,))
         await conn.commit()
         version = 31
     ```
   - Do NOT add `app_metadata` to `SCHEMA_V1` — fresh DBs run every `if version < N` block in sequence, so the migration block creates the table for fresh DBs too (this is how v21's `connector_accounts` and every post-v1 table are handled).

3. **Add `AppMetadataRepository`** to `the_one/db/repositories.py`
   - Place it near the other small repositories (e.g. after `ToolConfigRepository`, whose upsert idiom it mirrors). Constructor takes `conn: aiosqlite.Connection` like its siblings.
   - `get`:
     ```python
     async def get(self, key: str) -> str | None:
         async with self.conn.execute(
             "SELECT value FROM app_metadata WHERE key = ?", (key,)
         ) as cur:
             row = await cur.fetchone()
         return row[0] if row is not None else None
     ```
   - `set` (upsert, mirroring the `ON CONFLICT … DO UPDATE` idiom at `repositories.py:858–879`):
     ```python
     async def set(self, key: str, value: str) -> None:
         await self.conn.execute(
             "INSERT INTO app_metadata (key, value) VALUES (?, ?) "
             "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
             (key, value),
         )
         await self.conn.commit()
     ```
   - Export handling: `the_one/db/__init__.py` re-exports only connection helpers and `repositories.py` has no `__all__` — repos are imported directly from `the_one.db.repositories` (e.g. `api.py:44`). So there is **nothing to add to a package export**. The one concrete edit is the test file's explicit import tuple (`tests/test_db_repositories.py:10–19`): add `AppMetadataRepository` there so the new tests can import it.

4. **Migration test** (`tests/test_db_migration.py`)
   - **Canonical: the fresh-DB path** — a fresh `ensure_schema`'d connection runs blocks 1→31 in sequence and therefore exercises the new `app_metadata` block. Assert: `MAX(schema_version) == CURRENT_VERSION` (31) AND `app_metadata` appears in `sqlite_master`. Follow the existing assertion style (`:197–199`). (A hand-built v30-stamped variant is optional — a faithful v30 DB can't be built without the old code; the fresh path already covers the transition.)

5. **Repository tests** (`tests/test_db_repositories.py`)
   - Add an `app_metadata_repo` fixture mirroring `agent_store` (`:38–40`): `return AppMetadataRepository(conn)`.
   - Tests: `get` absent → `None`; `set` then `get` returns the value; `set` twice (same key, different value) → no raise, second value wins.

## Edge Cases

- **Partial apply / re-run**: `CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE` make the block safe to re-run after a crash mid-migration (consistent with v30's comment). Do not use a bare `CREATE TABLE` (would raise on re-run).
- **Empty-string value**: `value TEXT NOT NULL` permits `''` but not SQL `NULL`. `last_purge_at` is always a real ISO string, so this is fine; document that callers must pass a string (Leg 3 always does).
- **Absent vs present-but-empty**: `get` returns `None` only when the row is absent. Leg 3's due-check treats `None` as "never purged → due" — keep `get`'s absent→`None` contract crisp so that logic is unambiguous.
- **Fresh-DB path**: confirm a brand-new DB (version 0 → SCHEMA_V1 → all migrations) ends with `app_metadata` present — the migration test should cover both the fresh and the v30-stamped path, or at least the fresh path (which exercises the full chain).

## Files Affected
- `the_one/db/schema.py` — `CURRENT_VERSION` 30→31; new v31 migration block creating `app_metadata`.
- `the_one/db/repositories.py` — new `AppMetadataRepository` (get/set upsert); export if siblings are exported.
- `tests/test_db_migration.py` — v31 reach + `app_metadata`-present test.
- `tests/test_db_repositories.py` — `app_metadata_repo` fixture + get/set/upsert tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts) — *(deferred: this flight commits once after the last autonomous leg per agentic-workflow; do NOT commit here)*
