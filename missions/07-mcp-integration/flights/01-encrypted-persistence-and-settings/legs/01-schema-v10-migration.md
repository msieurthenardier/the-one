# Leg: 01-schema-v10-migration

**Status**: completed
**Flight**: [Encrypted MCP Source Persistence + Settings Page](../flight.md)

## Objective

Add schema migration v10 that rebuilds the `mcp_sources` table with a new CHECK constraint (`type IN ('stdio', 'streamable-http')`) and a new `secrets TEXT DEFAULT '{}'` column, renaming any existing `'sse'` rows to `'streamable-http'` via CASE-WHEN in the INSERT-SELECT step.

## Context

The `mcp_sources.type` literal `'sse'` is misaligned with the current MCP specification, which deprecated HTTP+SSE in revision 2025-03-26 and replaced it with Streamable HTTP. F1 reshapes the table to align with the spec AND adds a `secrets` column for field-segregated encryption (plaintext `config` + Fernet-encrypted `secrets` blob, decided at flight design — see flight.md "Field-segregated encryption with two-column storage").

**Why CASE-in-SELECT, not pre-rebuild UPDATE:** the still-active CHECK constraint on `mcp_sources` is `type IN ('stdio', 'sse')`. An UPDATE that writes `'streamable-http'` against this old table would fail constraint validation. The CASE-in-SELECT lands the renamed value directly into the new table whose CHECK already permits it.

**Why TABLE REBUILD, not ALTER:** SQLite has no `ALTER TABLE DROP CONSTRAINT`. The CHECK constraint change requires the v3/v5/v6-style table-rename ceremony (CREATE new + INSERT-SELECT + DROP old + RENAME new).

**Why individual-execute + INSERT OR IGNORE LAST (not `executescript`):** the v8 docstring at `the_one/db/schema.py:298-311` explains that aiosqlite's default mode silently COMMITs before any non-DML statement; `executescript` defeats the LAST-INSERT idempotency contract. v8/v9 set the higher idempotency bar, and v10 follows it.

This leg lands the migration only — the `MCPSource` Pydantic model literal change and the repository encryption envelope land in L2.

## Inputs

- `the_one/db/schema.py` at `CURRENT_VERSION = 9` (line 9)
- `mcp_sources` table at v1 shape: `id, name, type CHECK IN ('stdio','sse'), config, created_at, updated_at` (schema.py:61-68)
- v8 + v9 docstrings + idempotency pattern at `schema.py:292-353` as the precedent
- v3 + v5 + v6 table-rebuild ceremony at `schema.py:124-249` as the structural precedent (note: v3/v5/v6 used `executescript` and identity-SELECTs; v10 uses individual-execute + CASE-WHEN — same ceremony, different API + transformation)

## Outputs

- `the_one/db/schema.py` updated:
  - `CURRENT_VERSION = 10`
  - New `if version < 10:` block at the bottom of `ensure_schema` implementing the table rebuild
- `tests/test_db_migration.py` updated:
  - New `class TestSchemaV10` with four test methods (fresh DB, v9-fixture preservation, idempotent re-run, v9→v10 chained)

No model changes (deferred to L2). No API changes. No UI changes.

## Acceptance Criteria

- [ ] `CURRENT_VERSION` is `10` in `the_one/db/schema.py`
- [ ] On a fresh DB, `ensure_schema` produces an `mcp_sources` table whose CHECK constraint accepts `'streamable-http'` and rejects `'sse'`
- [ ] On a fresh DB, the `mcp_sources` table has a `secrets` column of type `TEXT` with default `'{}'`
- [ ] On a v9 fixture DB containing both an `'sse'` row and a `'stdio'` row (each with non-empty `config`), running `ensure_schema` migrates the `'sse'` row to `type='streamable-http'`, leaves the `'stdio'` row's type unchanged, populates `secrets='{}'` on both rows, preserves `id`, `name`, `config`, `created_at`, `updated_at` on both rows, and inserts a `schema_version` row at version 10
- [ ] Running `ensure_schema` twice in succession is a no-op — exactly one `schema_version` row exists at version 10, and the table shape is unchanged
- [ ] All four `TestSchemaV10` methods pass: fresh DB, v9-fixture preservation, idempotency, chained v9→v10

## Verification Steps

- `pytest tests/test_db_migration.py::TestSchemaV10 -v` — all four methods green
- `pytest tests/test_db_migration.py -v` — full migration suite still green (no regression in v3-v9 chained tests)
- `pytest tests/test_db_repositories.py::TestMCPSourceRepository -v` — existing MCP repo tests will FAIL at `tests/test_db_repositories.py:230,244` because they construct `MCPSource(type="sse")` and the new CHECK rejects `'sse'`. **L1 leaves them failing on purpose** — fixing them is L2's responsibility (the `'sse'` literal removal is part of L2's "Update sites" enumeration in the flight spec). `test_db_api.py::TestMCPSourceAPI` is NOT affected because `test_crud` at `tests/test_db_api.py:193` uses `type="stdio"`. Document the expected partial-flight test breakage in the flight log scoped to `test_db_repositories.py` only.
- `tests/test_schema.py` — exercised by the new migration as part of its v1-to-current walk tests. The `_LEGACY_SCHEMA_V1` constant at `tests/test_schema.py:9-67` is a frozen historical snapshot of the v1 DDL (including the legacy `type IN ('stdio','sse')` CHECK on `mcp_sources`); it MUST NOT be modified — keeping it frozen is the contract for testing migrations against the original v1 starting state. The walk tests apply the legacy DDL, then run `ensure_schema` which walks v1 → v10. No `mcp_sources` rows are seeded in those tests, so v10's INSERT-SELECT produces zero rows and the rebuild proceeds normally. No test assertion changes needed.

## Implementation Guidance

1. **Bump `CURRENT_VERSION` to 10** at `the_one/db/schema.py:9`.

2. **Append a `if version < 10:` block** at the bottom of `ensure_schema` (after the v9 block at `schema.py:334-353`). Use individual `await conn.execute(...)` calls (NOT `executescript`); end with `INSERT OR IGNORE INTO schema_version` for idempotency under partial-apply.

   ```python
   if version < 10:
       # Rebuild mcp_sources to (a) replace the deprecated 'sse' transport
       # literal with the spec-aligned 'streamable-http' in the CHECK
       # constraint, and (b) add the `secrets TEXT DEFAULT '{}'` column
       # for field-segregated encryption (mission 07 flight 01 design).
       # SQLite has no ALTER TABLE DROP CONSTRAINT, so this is a v3/v5/v6-
       # style table-rename ceremony — but built from individual
       # `await conn.execute(...)` calls (NOT executescript) and with
       # `INSERT OR IGNORE INTO schema_version` LAST, mirroring v8/v9's
       # idempotency contract.
       #
       # The 'sse' → 'streamable-http' rename happens via CASE-WHEN in
       # the INSERT-SELECT step, NOT a pre-rebuild UPDATE — the still-
       # active CHECK on the old table is `type IN ('stdio', 'sse')`,
       # which would reject the literal 'streamable-http'.
       #
       # Defensive DROP IF EXISTS on mcp_sources_new clears any stale
       # state from a prior partial-apply (the v8/v9 pattern's stronger
       # idempotency standard).
       await conn.execute("DROP TABLE IF EXISTS mcp_sources_new")

       await conn.execute("""\
   CREATE TABLE mcp_sources_new (
       id TEXT PRIMARY KEY,
       name TEXT NOT NULL,
       type TEXT NOT NULL CHECK (type IN ('stdio', 'streamable-http')),
       config TEXT DEFAULT '{}',
       secrets TEXT DEFAULT '{}',
       created_at TEXT NOT NULL DEFAULT (datetime('now')),
       updated_at TEXT NOT NULL DEFAULT (datetime('now'))
   )""")

       await conn.execute("""\
   INSERT INTO mcp_sources_new (id, name, type, config, secrets, created_at, updated_at)
       SELECT id, name,
              CASE WHEN type = 'sse' THEN 'streamable-http' ELSE type END,
              config,
              '{}',
              created_at,
              updated_at
       FROM mcp_sources""")

       await conn.execute("DROP TABLE mcp_sources")
       await conn.execute("ALTER TABLE mcp_sources_new RENAME TO mcp_sources")

       await conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (10,))
       await conn.commit()
       version = 10
   ```

3. **No `PRAGMA foreign_keys=OFF/ON` brackets needed** — `mcp_sources` has no FK references either inbound or outbound (verified: no other table FKs to `mcp_sources`, and the table itself has no FK columns). v3/v5/v6 used the brackets because their tables had FK relationships; v10 does not. This is a deliberate departure from the v3 ceremony, justified by the actual table shape.

4. **Add `class TestSchemaV10` to `tests/test_db_migration.py`** at the bottom of the file (after the v9 chained test at line 540ish). Mirror the v9 test structure exactly, adapted for the table-rebuild semantic. Four methods:

   **(a) `test_v10_fresh_db_has_secrets_column_and_streamable_http_check`**
   - Open a fresh DB, run `ensure_schema`
   - Assert `CURRENT_VERSION == 10`
   - PRAGMA `table_info(mcp_sources)` includes a `secrets` column of type `TEXT` (per v9 precedent at line 432-438)
   - Behavioural cross-check: an INSERT of a row with `type='streamable-http'` and no `secrets` value succeeds and lands `secrets='{}'` via the column DEFAULT
   - Behavioural cross-check: an INSERT of a row with `type='sse'` raises `aiosqlite.IntegrityError` (CHECK violation)
   - Assert `MAX(version) == 10` in `schema_version`

   **(b) `test_v10_migration_on_v9_fixture_db_preserves_existing_rows`**
   - Mirror the v9 test pattern at `test_db_migration.py:460-494` adapted for the table-rebuild semantic
   - Open a fresh DB, run `ensure_schema` (lands at v10)
   - **Programmatic rewind to v9 state** (the v9 PRAGMA-check pattern doesn't apply because v10 is a TABLE REBUILD, not an ADD COLUMN): `DROP TABLE mcp_sources` — recreate it with the v1 CHECK shape via `CREATE TABLE mcp_sources (id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL CHECK (type IN ('stdio', 'sse')), config TEXT DEFAULT '{}', created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')))` — `DELETE FROM schema_version WHERE version = 10`
   - Seed two rows directly via INSERT against the rewound v9 shape: one with `type='sse'` + non-empty `config`, one with `type='stdio'` + non-empty `config`
   - Re-run `ensure_schema`
   - Assert: `'sse'` row → `type='streamable-http'`, `'stdio'` row → unchanged, both rows have `secrets='{}'`, both rows preserve `id`/`name`/`config`/`created_at`/`updated_at`
   - Assert `MAX(version) == 10`

   **(c) `test_v10_migration_is_idempotent`**
   - Mirror v9 test at `test_db_migration.py:496-513`
   - Open a fresh DB, run `ensure_schema` twice in succession
   - Assert exactly one `schema_version` row at version 10 (count == 1)
   - Assert `mcp_sources` PRAGMA table_info still shows `secrets` column

   **(d) `test_v9_to_v10_chained_migration`**
   - Mirror v9 test at `test_db_migration.py:515-540`
   - Open a fresh DB, run `ensure_schema` (lands at v10)
   - Programmatically rewind to v9: `DROP TABLE mcp_sources; CREATE TABLE mcp_sources (...) with v1 CHECK shape; DELETE FROM schema_version WHERE version = 10`
   - Seed an `'sse'` row directly: `INSERT INTO mcp_sources (id, name, type, config) VALUES ('seed', 'Test', 'sse', '{"command": "python"}')`
   - Re-run `ensure_schema`
   - Assert the seeded row now has `type='streamable-http'`, `secrets='{}'`, original `config` preserved
   - Assert `MAX(version) == 10`

5. **Run the test suite locally before signaling [HANDOFF:review-needed]:**
   ```
   pytest tests/test_db_migration.py::TestSchemaV10 -v
   pytest tests/test_db_migration.py -v   # full migration suite (catches v3-v9 regression)
   pytest tests/test_schema.py -v         # walk tests against legacy DDL — should still pass
   pytest tests/ --tb=short -q            # full unit suite
   ```
   Expected partial breakage: `tests/test_db_repositories.py:230,244` will fail because they construct `MCPSource(type='sse')` — that's L2's update-sites work, not L1's. `tests/test_db_api.py::TestMCPSourceAPI::test_crud` is unaffected (uses `type='stdio'`). Document this expected breakage in the flight log under "Anomalies" with severity "blocking-for-flight-but-expected" and the resolution pointer to L2.

6. **Update the flight log** at `missions/07-mcp-integration/flights/01-encrypted-persistence-and-settings/flight-log.md`:
   - Append an entry under `## Leg Progress` with `### 01-schema-v10-migration`, status `landed`, started/completed timestamps, "Changes Made" summary listing the schema.py + test_db_migration.py edits, and a "Notes" entry for the expected partial test breakage.

7. **Set leg status to `landed`** in this leg's frontmatter (line 3 of this file) when implementation is complete and tests pass.

8. **Do NOT commit.** Per agentic-workflow protocol: implementation only, signal `[HANDOFF:review-needed]`, the orchestrator handles commit at flight end.

## Edge Cases

- **`mcp_sources` table is empty**: the INSERT-SELECT in step 2 produces zero rows, the rest of the rebuild proceeds normally. Verified by the fresh-DB test (no seed = empty source).
- **`mcp_sources_new` already exists from a partial apply**: `DROP TABLE IF EXISTS mcp_sources_new` at the start clears it. The migration block then proceeds as if from a fresh state.
- **Already at v10 (idempotent re-run)**: the `if version < 10:` gate short-circuits. No DDL fires. Verified by `test_v10_migration_is_idempotent`.
- **Existing row has `type='sse'` AND a `secrets` field somehow already populated**: cannot happen pre-v10 because there's no `secrets` column. Post-v10 the column default `'{}'` lands on every migrated row. The CASE-in-SELECT does not affect `secrets` semantics.
- **Existing row has `type='streamable-http'`**: cannot happen pre-v10 because the v1 CHECK rejects it. After v10 the CHECK accepts it. The CASE-in-SELECT's `ELSE type` branch passes it through unchanged on subsequent partial-apply scenarios — but the `if version < 10:` gate already short-circuits in that case, so this branch is dead code in practice. Documented for completeness.
- **Crash between `DROP TABLE mcp_sources` and `RENAME mcp_sources_new`**: this leaves `mcp_sources` gone and `mcp_sources_new` holding the data. The next `ensure_schema` run will see `version < 10` (since `INSERT OR IGNORE INTO schema_version` hasn't yet executed), then execute `DROP TABLE IF EXISTS mcp_sources_new` — destroying the data — then fail at the `INSERT INTO mcp_sources_new ... SELECT ... FROM mcp_sources` step because `mcp_sources` no longer exists. **This is a real data-loss window** that cannot be defended within aiosqlite's per-DDL autocommit constraint (the same constraint v8's docstring at `schema.py:298-311` documents). It is pre-existing in v3/v5/v6 (which use `executescript` with the same exposure). Mitigation in practice: the migration runs once at process startup before any user-visible activity, so the window is on the order of microseconds; an mcp_sources table at startup is also typically very small (operator-set, not user-generated); a backup of `data_dir/the-one.db` taken before the v10 upgrade recovers from any catastrophic crash. Documented per v8's "honesty over silence" precedent — no code change available within the autocommit constraint.

## Files Affected

- `the_one/db/schema.py` — bump `CURRENT_VERSION`, add `if version < 10:` block
- `tests/test_db_migration.py` — add `class TestSchemaV10` with four methods
- `tests/test_schema.py` — exercised by the new migration via the v1-to-current walk tests; `_LEGACY_SCHEMA_V1` constant at lines 9-67 is intentionally NOT modified (frozen historical snapshot of the v1 DDL is the contract that lets these tests simulate pre-migration databases)

## State-Machine Reachability Audit

States introduced or affected:
- `mcp_sources.type` value space: was `{'stdio', 'sse'}`; becomes `{'stdio', 'streamable-http'}`. Existing `'sse'` rows transition to `'streamable-http'` via the migration. No row can remain at `'sse'` post-v10 — the CHECK rejects it.
- `mcp_sources.secrets` column: introduced. Default `'{}'`. No existing row has any other value at migration time (column did not exist).
- `schema_version.version` value space: gains `10`. Idempotent under `INSERT OR IGNORE`.

Tests that pin pre-v10 state and would contradict v10:
- `tests/test_db_repositories.py:230` — `MCPSource(id="b", name="Bravo", type="sse")` — pinned the old literal. **Will fail post-L1**, fix is part of L2's update-sites.
- `tests/test_db_repositories.py:244` — same pattern with `type="sse"` — same disposition.
- `tests/test_db_api.py:188-209` `TestMCPSourceAPI::test_crud` — uses `type="stdio"`, not `'sse'` (verified at line 193); will continue to pass post-L1. The L2 update is to extend coverage, not fix breakage.

No FK behaviors to audit (no FK references to/from `mcp_sources`). No application caches to audit (the migration runs at startup, before any cache populates). No fallback handlers silently masking the `'sse'` value.

## Cache Freshness Contract

This leg does not introduce or read from any cache. The migration runs once at process startup via `ensure_schema(conn)` in `the_one/db/connection.py:get_connection()`. All downstream consumers (`MCPSourceRepository`, `/api/mcp-sources` endpoints) read directly from the DB on each call.

## Citation Audit

12 citations verified against current code at leg design time:
- `the_one/db/schema.py:9` `CURRENT_VERSION = 9` — OK
- `the_one/db/schema.py:61-68` `mcp_sources` table at v1 shape — OK
- `the_one/db/schema.py:124-249` v3/v5/v6 rebuild precedent — OK
- `the_one/db/schema.py:292-353` v8/v9 idempotency precedent — OK
- `the_one/db/schema.py:298-311` v8 docstring on executescript COMMIT behavior — OK
- `the_one/db/schema.py:334-353` v9 block — OK
- `tests/test_db_migration.py:416-540` v9 test class precedent — OK
- `tests/test_db_migration.py:432-438` v9 PRAGMA table_info pattern — OK
- `tests/test_db_migration.py:460-494` v9 v8-fixture preservation pattern — OK
- `tests/test_db_migration.py:496-513` v9 idempotency pattern — OK
- `tests/test_db_migration.py:515-540` v9 chained migration pattern — OK
- `tests/test_db_repositories.py:230,244` `type="sse"` literals (will break post-L1, fix is L2) — OK

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `pytest tests/test_db_migration.py::TestSchemaV10 -v` green
- [ ] `pytest tests/test_db_migration.py -v` green (no v3-v9 regression)
- [ ] Update flight-log.md with leg progress entry (status `landed`, expected partial-breakage note)
- [ ] Set this leg's status to `landed` (in this file's frontmatter, line 3)
- [ ] Do NOT check off this leg in flight.md yet — that happens at flight commit
- [ ] Do NOT commit — per agentic-workflow protocol, commit happens once at flight end
