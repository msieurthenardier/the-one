# Leg: backend-rename

**Status**: completed
**Flight**: [Connector Terminology Rename + Small-Housekeeping Fold-Ins](../flight.md)

## Objective

Land the full Python-side rename of `ConnectorAccount` → `Connector` and schema migration v23 that renames the `connector_accounts` table plus all dependent FK columns + indexes, leaving API URL paths and frontend DOM strings unchanged so the running app keeps working between L1 and L2.

## Context

This is the first of three legs in F11. Per the flight's L1/L2 split design decision, **L1 touches Python only** — the 12 FastAPI routes continue to expose `/api/connector-accounts/...` paths (the routes internally operate on `Connector` model instances and `ConnectorRepository`), and the JS / CSS / `data-testid` / `data-*` / HTML template strings all stay at `connector-account-...`. L2 atomically swaps the URL surface + frontend together; L3 closes housekeeping items.

**Schema migration shape**: v23 follows the v6/v12/v19 row-rewrite ceremony precedent for the parent table rename + `pending_approvals` FK-target update, and uses `ALTER TABLE RENAME COLUMN` for `chat_sessions.connector_account_id` + `agents.connector_account_ids` (no FK on those, just a partial index that gets dropped + recreated against the renamed column). Operator chose "full consistency" (FK columns + JSON column rename too) over "table-only with historical column-name residue" at flight planning.

**Atomicity boundary** (per flight spec L1 description, the bolded NOT-touch list): no `data-testid` value, `data-*` attribute name, CSS class, JS variable name, or HTML template string changes in L1. That is L2's job.

## Inputs

- F11 flight artifact at `../flight.md` (status: in-flight)
- F11 flight log at `../flight-log.md` with reconnaissance report
- Branch `flight/11-connector-rename-and-housekeeping` checked out from main
- Current main HEAD: `74826ac` (F10 land)
- Backend test suite baseline: 2733 passed / 4 skipped / 13 pre-existing asyncio teardown errors in `test_provider_repository.py` / ~256s wall (per F10 debrief test-metrics)
- 40 Python source files reference `ConnectorAccount` (per `grep -rln 'ConnectorAccount\b' the_one/ tests/ --include='*.py'`)
- 43 Python source files reference `connector_account_id` or `connector_account_ids`
- `the_one/agents.md` has 13 Python-class citations at lines 100, 216, 243, 399, 411, 604, 607, 608, 609, 610, 652, 660, 666 (per F11 architect cycle-1 grep)
- Uncommitted operator dev state: `docker-compose.yml` has `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL` env vars (M11 F7 L12 HAT). **DO NOT stage this file.** Stage Python files explicitly.

## Outputs

- New migration block at `the_one/db/schema.py` for v23 (transactional `executescript`, idempotent re-run, schema_version inserted LAST)
- `ConnectorAccount` class renamed to `Connector` in `the_one/db/models.py`
- `ConnectorAccountRepository` class renamed to `ConnectorRepository` in `the_one/db/repositories.py`
- All ~40 Python files updated to use `Connector` / `ConnectorRepository`
- All ~43 Python files updated to use `connector_id` / `connector_ids` accessors
- `the_one/db/_connector_types.py` docstring updated for renamed class + JSON column
- `the_one/agents.md` Python class citations updated (13 lines; structural sweep stays L3)
- Repository SQL strings reference `connectors` table + renamed columns
- FK CASCADE comment at `schema.py:793` updated to reference `connectors`
- Flight log updated with L1 progress entry
- Leg status `landed` (NOT committed — Phase 2d commits all three legs together)

## Acceptance Criteria

- [x] Schema migration v23 added to `the_one/db/schema.py` following the v19 `executescript` row-rewrite shape (PRAGMA foreign_keys=OFF, CREATE NEW, INSERT FROM OLD, DROP OLD, ALTER RENAME, PRAGMA foreign_keys=ON, INSERT OR IGNORE schema_version LAST).
- [x] New `TestSchemaV23` test class added to `tests/test_db_migration.py` following the existing `TestSchemaVN` class pattern (cf. `TestSchemaV14`, etc.) — asserts that (a) a v22-seeded DB with rows in `connector_accounts` + `chat_sessions` + `pending_approvals` + `agents.connector_account_ids` migrates cleanly to v23 with all row content preserved; (b) the resulting schema has `connectors` table (not `connector_accounts`), `chat_sessions.connector_id` column (not `connector_account_id`), `pending_approvals.connector_id` column with FK to `connectors(id)`, `agents.connector_ids` column; (c) the two partial indexes exist and reference the renamed columns; (d) re-running `ensure_schema` on an already-v23 DB is a no-op.
- [x] `class ConnectorAccount` in `the_one/db/models.py` is renamed to `class Connector`.
- [x] `class ConnectorAccountRepository` in `the_one/db/repositories.py` is renamed to `class ConnectorRepository`.
- [x] `the_one/db/_connector_types.py` docstring references `Connector.type` and `agents.connector_ids` (not `ConnectorAccount.type` / `agents.connector_account_ids`).
- [x] Repository SQL strings in `the_one/db/repositories.py` reference `connectors` table; SQL referencing the renamed columns uses `connector_id` / `connector_ids`.
- [x] `git grep -E '\bConnectorAccount\b' the_one/ tests/` returns zero hits in source files. Acceptable residue: flight artifacts (this leg, the flight log, the flight spec) retain the historical name as history. The v19 migration body has no `ConnectorAccount` references (SQL only).
- [x] `git grep -E 'connector_account_id|connector_account_ids' the_one/ tests/` returns zero hits in source files. Acceptable residue: `the_one/db/schema.py` v16/v17/v21 migration bodies retain the historical column names as the FROM side of the v23 row-rewrite + as the original ALTER ADD COLUMN statements; flight artifacts retain history.
- [x] `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30` is green (the regression net for v23 — exercises all priors + v23 on a fresh DB).
- [x] `docker exec the-one pytest -x --timeout 60` is green at 2733+ passing / 4 skipped (the 13 pre-existing asyncio teardown errors persist — L3's scope, not L1's).
- [x] FK in `pending_approvals` table references `connectors(id)` not `connector_accounts(id)`, verified by reading the v23 migration body OR via `PRAGMA foreign_key_list(pending_approvals)` on a migrated DB.
- [x] Partial indexes `idx_chat_sessions_external_key` and `idx_pending_approvals_account_peer_status` recreated against the renamed column names.
- [x] 12 FastAPI routes in `the_one/interfaces/web/api.py` still expose `/api/connector-accounts/...` paths (L1 atomicity boundary: URL rename is L2's job; spot-check by grep).
- [x] Zero diff in any JS / CSS / HTML template file (L1 atomicity boundary: `git diff --name-only main` must not include any file under `the_one/interfaces/web/static/` except where Python templates or generated HTML might leak — none should be touched in L1).
- [x] `the_one/agents.md` Python class citations at the 13 identified lines updated to reference `Connector` / `ConnectorRepository` (NOT the structural sweep — that's L3).
- [x] Flight log `Leg Progress` section has an L1 entry summarizing changes + test results.
- [x] Leg status updated to `landed` in this file's header. **DO NOT commit** — Phase 2d batches commits.

## Verification Steps

1. **Migration test suite** (the regression net for v23 specifically):
   - `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30`
   - Must show green; if a test pinning the old `connector_accounts` table name fails, update the test (it's pinning the v19 shape, which is now wrong post-v23).

2. **Full backend suite** (`-x` interaction with L3-deferred errors — important):
   - The 13 pre-existing asyncio teardown errors in `tests/test_provider_repository.py` are TEARDOWN errors. Pytest's `-x` / `--exitfirst` halts on the first error or failure, **including** teardown errors. To avoid halting the broad-suite run on these L3-deferred errors, deselect that file for the L1 leg-end verification:
   - `docker exec the-one pytest --deselect tests/test_provider_repository.py -x --timeout 60`
   - Must show 2733+ passing / 4 skipped (the 13 errors are deselected for this run only). L3's housekeeping-bundle leg will fix the fixture and the deselect can drop.
   - Alternative if deselect feels too narrow: run without `-x` (`pytest --timeout 60`) and inspect that ALL errors come from `tests/test_provider_repository.py` (no new errors introduced by L1). The convention's `-x` shape exists to catch new failures fast; for L1 the L3-deferred errors are noise, not signal.
   - The 2733+ count grows by `+1` from the new `TestSchemaV23` test class added per AC #2; further new tests are not expected.

3. **Grep verification (mechanical L1 boundary check)**:
   - `git grep -E '\bConnectorAccount\b' the_one/ tests/` → zero hits in source files
   - `git grep -E 'connector_account_id|connector_account_ids' the_one/ tests/` → zero hits in source files (allowed residue documented at the gate)
   - `git grep -E 'connector_account' the_one/db/schema.py` → may return hits inside v16/v17/v21/v23 migration bodies (acceptable — those document the historical state OR are the FROM side of the v23 row-rewrite)

4. **L1 atomicity boundary checks**:
   - `git diff --name-only main -- 'the_one/interfaces/web/static/'` → empty (no JS/CSS/HTML touched in L1)
   - `git diff --name-only main -- 'tests/browser/'` → empty (no browser test changes in L1)
   - `grep -nE '/api/connector-accounts' the_one/interfaces/web/api.py` → 12 hits (URL paths unchanged)

5. **FK verification** (one of):
   - Read the v23 migration body in `the_one/db/schema.py` and confirm `pending_approvals_new` declares `connector_id TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE`
   - Or after running the migration test suite, inspect a migrated DB: `sqlite3 <db> 'PRAGMA foreign_key_list(pending_approvals);'` shows `connectors` as the referenced table

## Implementation Guidance

**Order matters within this leg.** Do the migration body FIRST (so the test suite has the new schema available), then the Python class + accessor sweep (so tests can exercise the renamed names), then run tests.

### Step 1 — Add migration v23 to `the_one/db/schema.py`

Locate the end of the v22 block (currently the latest migration). Add a new `if version < 23:` block matching the v19 `executescript` precedent (`the_one/db/schema.py:708-768`). The v23 body must:

1. Toggle `PRAGMA foreign_keys=OFF` at the start, `=ON` at the end.
2. Row-rewrite `connector_accounts` → `connectors`:
   - `DROP TABLE IF EXISTS connectors_new`
   - `CREATE TABLE connectors_new (...)` — copy the v19 shape exactly (9 columns: `id`, `type` with the `CHECK (type IN ({_CONNECTOR_TYPES_SQL}))` constraint, `config`, `secrets`, `created_at`, `updated_at`, `name`, `idle_timeout_seconds`, `session_continuation_seconds`)
   - `INSERT INTO connectors_new (...) SELECT (...) FROM connector_accounts`
   - `DROP TABLE connector_accounts`
   - `ALTER TABLE connectors_new RENAME TO connectors`
3. Row-rewrite `pending_approvals` (FK target update — the FK column references the parent table, which just got renamed). All these statements live in the SAME `executescript` block as Step 1.2 above; the index is auto-dropped when the parent table is dropped, then explicitly recreated against the renamed column:
   - `DROP TABLE IF EXISTS pending_approvals_new`
   - `CREATE TABLE pending_approvals_new (...)` — same 8-column shape as the v21 `pending_approvals` table (`the_one/db/schema.py:802-813`), but with the FK column renamed `connector_account_id` → `connector_id` and the FK reference updated to `REFERENCES connectors(id) ON DELETE CASCADE`
   - `INSERT INTO pending_approvals_new (id, connector_id, peer_id, peer_name, preview, received_at, status, resolved_at) SELECT id, connector_account_id, peer_id, peer_name, preview, received_at, status, resolved_at FROM pending_approvals`
   - `DROP TABLE pending_approvals` — (the index `idx_pending_approvals_account_peer_status` dies with this DROP; the CREATE INDEX two bullets below re-establishes it against the renamed column)
   - `ALTER TABLE pending_approvals_new RENAME TO pending_approvals`
   - `CREATE INDEX IF NOT EXISTS idx_pending_approvals_account_peer_status ON pending_approvals (connector_id, peer_id, status)` — recreated against renamed column. (Index name retained even though it says "account" — renaming the index name is a separate concern; not required for correctness. If you choose to rename it for consistency, do so AND update any test that references the index name; out of L1 default scope unless test breakage forces the issue.)
4. Column-rename `chat_sessions.connector_account_id` → `chat_sessions.connector_id`:
   - `ALTER TABLE chat_sessions RENAME COLUMN connector_account_id TO connector_id`
   - `DROP INDEX IF EXISTS idx_chat_sessions_external_key`
   - `CREATE INDEX idx_chat_sessions_external_key ON chat_sessions(platform, connector_id, channel_id, COALESCE(thread_id, '')) WHERE platform IS NOT NULL` — recreated against renamed column expression
5. Column-rename `agents.connector_account_ids` → `agents.connector_ids`:
   - `ALTER TABLE agents RENAME COLUMN connector_account_ids TO connector_ids`
6. `INSERT OR IGNORE INTO schema_version (version) VALUES (23)` LAST, then `await conn.commit()`, then `version = 23`.

Use the v19 docstring shape as the model — explain the operation, cite the v6/v12/v19 precedent for the row-rewrite shape, note idempotency, and mention this lands M11 F11 L1 (the rename).

### Step 2 — Rename the Pydantic class + repository

- `the_one/db/models.py` — `class ConnectorAccount(BaseModel):` → `class Connector(BaseModel):` (look for the class definition; the architect cycle-1 grep cited line 116 but verify with `grep -n 'class ConnectorAccount' the_one/db/models.py`). Update the class docstring's references to `connector_accounts` table to `connectors`.
- `the_one/db/repositories.py` — `class ConnectorAccountRepository:` → `class ConnectorRepository:` (architect cited line 506; verify with grep). Update SQL strings inside the class methods to reference `connectors` table and the renamed `connector_id` / `connector_ids` columns wherever they currently reference `connector_accounts` / `connector_account_id` / `connector_account_ids`.
- Update the docstring at the top of `_connector_types.py` — 6 occurrences verified at Phase 3b:
  - line 7: `ConnectorAccount.type` → `Connector.type`
  - line 12: `connector_accounts` (table name in prose) → `connectors`
  - line 19: `connector_accounts` (table name in v14 prose) → `connectors`
  - line 21: `connector_accounts` → `connectors`; `agents.connector_account_ids` → `agents.connector_ids`
  - line 23: `connector_accounts.type` → `connectors.type`
  - line 33: `ConnectorAccount(type="stub")` → `Connector(type="stub")`

### Step 3 — Python-wide accessor sweep

- Identify the surface: `grep -rln 'ConnectorAccount\b\|connector_account_id\|connector_account_ids' the_one/ tests/ --include='*.py'` (40+43 = ~70 distinct files, allowing for overlap).
- All `the_one/connectors/*.py` plugin files participate in this sweep (Developer cycle-1 reviewer confirmation): `base.py`, `_inbound.py`, `_inference.py`, `_commands.py`, `_pool.py`, `_acl.py`, `_discord.py`, `_stub.py`, `registry.py`, etc. Most reference `ConnectorAccount` as a type annotation or argument.
- For each file: rename `ConnectorAccount` → `Connector`, `ConnectorAccountRepository` → `ConnectorRepository`, `.connector_account_id` → `.connector_id`, `.connector_account_ids` → `.connector_ids`, and any local variable / parameter / fixture name that carries `connector_account_id` etc.
- Watch for `register_builtin_connectors` calls (in tests) using `ConnectorAccount(type="stub")` — these are 69+ sites per `_connector_types.py:32`; the search-and-replace should catch them but verify the count drops to zero.
- Update the FK comment at `the_one/db/schema.py:793` referencing the renamed parent table (`connector_accounts` → `connectors`).
- DO NOT touch repository method names (`ConnectorAccountRepository.create()` → `ConnectorRepository.create()` is the class rename; the method names themselves don't carry the term).

**Migration-test update strategy (nuanced — per cycle-1 Developer feedback):** `tests/test_db_migration.py` has 117 hits across `TestSchemaV{13,14,15,16,17,18,19,21,22}` classes. Two categories with DIFFERENT update rules:

- **Category A — tests bootstrapping a vN<23 schema and asserting vN-era names**: These tests deliberately pin historical names (e.g. assert `connector_accounts` exists after the v13 migration runs on a hand-built v12 DB). DO NOT rename the historical names in these tests — they document the intermediate schema state. The vN-era table/column names must stay as they were when vN landed.
- **Category B — tests running full `ensure_schema` (no version cap) and asserting final-shape names**: These tests assert the post-all-migrations schema state. DO rename references from `connector_accounts` → `connectors`, `connector_account_id` → `connector_id`, etc. — they assert the latest shape, which v23 changes.

Discriminator: read each test's `arrange` section. If it starts the DB at a specific `schema_version` and asserts a specific vN row-rewrite worked, it's Category A. If it runs `ensure_schema` to completion and asserts shape, it's Category B. When in doubt, the safest default is Category A (preserve historical names) — under-renaming is recoverable in cycle 2 review; over-renaming corrupts the migration regression net's purpose.

### Step 4 — `agents.md` Python class citations

For each of the 13 lines (100, 216, 243, 399, 411, 604, 607, 608, 609, 610, 652, 660, 666), read the line in context and rename `ConnectorAccount` references → `Connector`, `ConnectorAccountRepository` → `ConnectorRepository`, `connector_account_ids` / `connector_account_id` → renamed forms. DO NOT add new sections, promote conventions, or change structural prose — that's L3's job.

The historical-citation lines (e.g. lines mentioning "F1 L7 — connector-account-editor.js create-mode bug") should leave the historical artifact name intact (the file is still named `connector-account-editor.js` in this leg; L2 will rename it). Use judgment: prose that says "the ConnectorAccount class" updates; prose that names a historical artifact (a file, a commit, a flight title) does not.

### Step 4b — `the_one/connectors/README.md` (plugin author documentation)

The connectors plugin-author README references `ConnectorAccount` directly as the canonical class plugin authors interact with. Sweep this file in L1 (it's adjacent to the renamed class; leaving it stale would mislead any future plugin author reading it). Rename `ConnectorAccount` → `Connector` throughout; preserve historical-artifact references (e.g. "F1 L7 commit ..." stays). Update any code-block examples that instantiate the class.

### Step 5 — Run tests

```bash
# Migration test suite first (regression net for v23):
docker exec the-one pytest tests/test_db_migration.py -x --timeout 30

# Then broader suite:
docker exec the-one pytest -x --timeout 60
```

Allowed test outcomes:
- 2733+ passing / 4 skipped / **13 pre-existing asyncio teardown errors** in `test_provider_repository.py` (L3 scope; do NOT fix in L1)
- Wall-clock within ~10% of the 256s F10 baseline (allowing for v23 migration overhead in fixtures)

If a test fails because it pins the old `connector_accounts` table name in a fixture or SQL string: update the test in lockstep with the schema change (this is acceptance criterion territory, not a divert).

If a test fails for a substantive reason (e.g. a repository method returns wrong data): treat as a regression, isolate, and fix before signaling [HANDOFF:review-needed].

### Step 6 — Atomicity boundary verification

```bash
# Must be empty (no JS/CSS/HTML in L1):
git diff --name-only main -- 'the_one/interfaces/web/static/'

# Must be empty (no browser test changes in L1):
git diff --name-only main -- 'tests/browser/'

# Must show 12 hits (URL paths preserved for L2):
grep -nE '/api/connector-accounts' the_one/interfaces/web/api.py | wc -l
```

### Step 7 — Update flight log and leg status

- Append an entry to `../flight-log.md` under `## Leg Progress` summarizing what changed (migration v23, ~370 Python sites, test results).
- Update this leg artifact's header `**Status**: landed` (NOT `completed` — Phase 2d commits + completes).
- Do NOT update the flight-spec leg checkbox to `[x]` (the commit leg does that).
- Do NOT commit. Do NOT `git add`. Signal `[HANDOFF:review-needed]` per the leg-execution crew's Implement prompt.

## Edge Cases

- **SQLite version**: `ALTER TABLE ... RENAME COLUMN ...` requires SQLite ≥3.25 (2018-09). Host sqlite is 3.45.1 (cycle-1 verified); the Docker image's `python:3.11` base ships modern sqlite. The fallback to row-rewrite is theoretically sound but practically unreachable.
- **`_CONNECTOR_TYPES_SQL` interpolation**: The v19 migration uses `{_CONNECTOR_TYPES_SQL}` inside an f-string `executescript`, which means `{{` and `}}` for literal braces. Match this pattern in v23 — copy the v19 block verbatim and edit, don't rewrite from scratch.
- **Idempotency**: Re-running `ensure_schema` on a fresh DB must apply v23 cleanly; re-running on an already-v23 DB must be a no-op (the `if version < 23:` guard handles this).
- **Test fixtures using `ConnectorAccount(type="stub")`**: 69+ sites per `_connector_types.py:32`. The rename to `Connector(type="stub")` is mechanical; verify the consistency tests at `tests/test_connector_types_consistency.py` still pass.
- **Import statements**: `from the_one.db.models import ConnectorAccount` becomes `from the_one.db.models import Connector`. Watch for aliased imports (`as`-renames) — none expected but spot-check.
- **The `connector_acls` column on `agents`**: unchanged. The column name `connector_acls` does NOT contain `connector_account` and is not renamed. Same for `connector_always_listen` (v20). Both stay.
- **Docker compose env vars**: the operator's local `docker-compose.yml` modification adding `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL` must NOT be staged. When this leg eventually commits (Phase 2d), explicit `git add <files>` is the rule — never `git add .` or `git add -A`.
- **Test that explicitly inserts a pre-v23 row into `connector_accounts`**: if any test fixture sets up a DB at schema version <23 and inserts into `connector_accounts`, it must still work because v23 row-rewrites the historical table into the new shape. If a test bypasses `ensure_schema` (rare), it would now reference a nonexistent table — fix the test to use `ensure_schema` properly OR insert into `connectors` directly post-migration.

## Files Affected

**Schema + models + repository** (canonical names cited symbol+file form):
- `the_one/db/schema.py` — add v23 migration block (after v22); update FK CASCADE comment at `:793`
- `the_one/db/models.py:Connector` (was `ConnectorAccount`) — class rename + docstring updates
- `the_one/db/repositories.py:ConnectorRepository` (was `ConnectorAccountRepository`) — class rename + SQL string updates
- `the_one/db/_connector_types.py` — docstring updates (6 occurrences at lines 7, 12, 19, 21, 23, 33 — verified Phase 3b)

**Python sweep** (~70 files identified via `grep -rln '\bConnectorAccount\b\|connector_account_id\|connector_account_ids' the_one/ tests/ --include='*.py'`):
- 40 files reference `ConnectorAccount`
- 43 files reference `connector_account_id` or `connector_account_ids`
- Overlap expected; total unique surface ~50-70 files

**Documentation**:
- `the_one/agents.md` — Python class citations at lines 100, 216, 243, 399, 411, 604, 607, 608, 609, 610, 652, 660, 666 (class-name updates only; structural sweep is L3)
- `the_one/connectors/README.md` — plugin-author documentation references `ConnectorAccount` (per cycle-1 review); update class-name references; preserve historical-artifact citations

**Flight artifacts** (mandatory updates per leg-execution protocol):
- `missions/11-discord-connector-depth/flights/11-connector-rename-and-housekeeping/flight-log.md` — append L1 progress entry
- This file (`legs/01-backend-rename.md`) — status → `landed`

**Explicitly NOT affected in L1**:
- Any file under `the_one/interfaces/web/static/` (CSS, JS, HTML) — L2's job
- Any file under `tests/browser/` (browser test selectors + filenames) — L2's job
- `the_one/interfaces/web/api.py` route path strings (the URL segments `/api/connector-accounts/...` stay) — L2's job
- `docker-compose.yml` (operator's local dev state, unrelated to F11)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (migration applied, classes renamed, sweep complete, grep gates clean, tests green within L3-deferred-allowance)
- [x] L1 atomicity boundary verified (no `static/`, `browser/`, URL-path changes)
- [x] Migration test suite green specifically (`pytest tests/test_db_migration.py -x --timeout 30`)
- [x] Full backend suite green (2733+ passing, 13 carried asyncio errors expected)
- [x] Flight-log L1 progress entry appended
- [x] This leg's status set to `landed` (NOT `completed` — Phase 2d commits)
- [x] Do NOT update flight-spec leg checkbox (commit leg does that)
- [x] Do NOT commit, do NOT `git add` (Phase 2d batches all three legs into one review + one commit)
- [x] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

Phase 3b verification (2026-05-28, leg-design time):

| Citation | Classification | Resolution |
|----------|---------------|------------|
| `the_one/db/models.py:116` — `class ConnectorAccount(BaseModel):` | OK | Line confirmed; class definition at exactly :116 |
| `the_one/db/repositories.py:506` — `class ConnectorAccountRepository:` | OK | Line confirmed |
| `the_one/db/_connector_types.py:7` — `ConnectorAccount.type` | OK | Line confirmed |
| `the_one/db/_connector_types.py:21` — `agents.connector_account_ids` | OK | Line confirmed |
| `the_one/db/_connector_types.py:33` — `ConnectorAccount(type="stub")` | OK | Line confirmed |
| `the_one/db/_connector_types.py:39` — text mentioning class | **gone** (drift) | Repaired inline — actual `_connector_types.py` rename surface has 6 occurrences at lines 7, 12, 19, 21, 23, 33; not line 39. Implementation guidance updated to enumerate all 6. |
| `the_one/db/schema.py:793` — FK CASCADE comment | OK | Line 793 in the v21 docstring header reads "FK CASCADE on connector_account_id mirrors..." — comment needs renaming when v21's referenced column gets renamed by v23 |
| `the_one/db/schema.py:708-768` — v19 row-rewrite block | OK | Block starts at :708 (`if version < 19:`) and ends at :768 (`version = 19`) |
| `the_one/db/schema.py:802-813` — v21 pending_approvals table shape | OK | CREATE TABLE block at :802-813 with FK at :804-805 and index at :815-816 |
| agents.md lines 100, 216, 243, 399, 411, 604, 607, 608, 609, 610, 652, 660, 666 | not re-verified | Architect cycle-1 grep is the source; Phase 3b trusts it. Implementing developer re-greps before touching. |

10 citations verified; 1 drift repaired inline. No `gone` citations require human review.
