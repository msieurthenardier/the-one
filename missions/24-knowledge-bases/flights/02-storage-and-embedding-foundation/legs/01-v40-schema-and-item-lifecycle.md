# Leg: v40-schema-and-item-lifecycle

**Status**: completed
**Flight**: [Storage and Embedding Foundation](../flight.md)

## Objective

Land schema v40 — `kb_items` rebuilt with a constrained lifecycle and a
`kb_chunks` table whose ids are never recycled, plus an FTS5 index over chunk
text — together with the item repository methods and routes that let an item
leave `pending`, and the write-transaction guard that every committing write
on the shared connection goes through from now on.

## Context

- Flight DD-5 (the v40 shape, the `AUTOINCREMENT` rule, the no-triggers FTS
  decision and its recorded costs), DD-13 (every committer holds the lock;
  `write_transaction()`; non-reentrant with detection; conditional-`UPDATE`
  transitions; the lint guard), and the R8 route fixes.
- This is the flight's one hard-to-reverse step, so it lands first and alone.
  Leg 2 (chunk repository, FTS sync, `fts5` probe) and Legs 3–4 (seams)
  depend only on this leg's tables and guard. Nothing here touches
  `the_one/embeddings`, `the_one/vectors`, `diagnostics.py` or the CI lanes.
- The Architect's cycle-2 finding is the load-bearing context for the guard:
  a lock scoped to multi-statement writers **does not** protect a partial
  write from a plain single-statement committer on the same connection —
  the reviewer modelled it and the partial rows were destroyed. Hence every
  committer, including the 41 self-committing repository methods that exist
  today and the encryption-rotation endpoint, goes through the guard.
- Migrations under `ensure_schema` are **outside** the rule: they run at
  `init_db()` before any request or background task exists, and their 40
  `commit()` sites are the per-block stamps the append-only history depends
  on. The guard test excludes `the_one/db/schema.py` explicitly and says why.
- Nothing in this leg writes a chunk or a vector; `kb_chunks` and
  `kb_chunks_fts` are created here so the migration is one block, and their
  repository arrives in Leg 2.

## Inputs

- `the_one/db/schema.py` at v39: `CURRENT_VERSION = 39` (`:14`);
  `SCHEMA_V1`'s `kb_items` DDL (`:72-80`, `type … CHECK (type IN ('file',
  'url'))`, `status TEXT DEFAULT 'pending'`, no indexes); the v37 rebuild
  template (`:2141-2212`); the v39 block ending at `:2370`; the stale
  aiosqlite comment (`:319-327`).
- `the_one/db/models.py:88-97` — `KBItem` with `type: Literal["file","url"]`
  and `status: str = "pending"`; the `PROVIDER_TYPES` import-time assert
  pattern at `:70-75`.
- `the_one/db/repositories.py:361-477` — `KnowledgeBaseRepository`,
  `KBItemRepository` (no `update`, no status method); 41 `conn.commit()` call
  sites across the file (`grep -c "\.commit()"`).
- `the_one/interfaces/web/api.py:1367-1462` — the eight KB routes;
  `_kb_repo`/`_kb_item_repo` helpers at `:244-251`; the rotation endpoint's
  write block ending at `:4850-4852` (`commit()` / `rollback()`) — the one
  pre-existing multi-statement writer, and the only `commit()` outside
  `the_one/db/`.
- `tests/test_db_migration.py` — `TestSchemaV39` at `:4338-4519`: the four
  shapes to mirror are `test_v39_upgrade_from_fresh_db` (`:4346`, the AC-1
  analogue), `test_v39_upgrade_from_v38_db_preserves_connector_rows`
  (`:4394`, the AC-2 analogue), `test_v39_idempotent_on_double_ensure`
  (`:4439`) and `test_v39_tolerant_of_rewind_rerun` (`:4455`); `assert
  CURRENT_VERSION == 39` at `:4389`; the `_rewind_to_pre_v38` helper at
  `:4158` (the rewind-helper idiom).
- `tests/test_db_repositories.py:66-71` (`kb_repo`/`kb_item_repo` fixtures),
  `:539-605` (KB tests); `tests/test_db_api.py:539-606` (KB API tests);
  `tests/test_provider_types_consistency.py` (the consistency-test shape).
- Precedents: `the_one/sessions/_locks.py` (module-level lock + `*_for_test`
  reset), `tests/test_ui_guards.py` / `tests/test_token_definitions.py`
  (repo-source guard tests), `api.py:889/1223` (409 shape).

## Outputs

- `the_one/db/_kb_types.py` (new): `KB_ITEM_TYPES = ("file", "url",
  "folder")`, `KB_ITEM_STATUSES = ("pending", "indexing", "indexed",
  "failed")`, `KB_ITEM_TRANSITIONS: dict[str, frozenset[str]]` mapping each
  target status to its allowed predecessors — `indexing: {pending}`,
  `indexed: {indexing}`, `failed: {indexing}`, `pending: {indexing, failed,
  indexed}` — and `class KBItemTransitionError(ValueError)`.
- `the_one/db/_write_lock.py` (new): `write_transaction(conn)` async context
  manager over one module-level `asyncio.Lock`; commits on clean exit, rolls
  back on exception, raises `RuntimeError` on same-task re-entry;
  `reset_for_test()`.
- `the_one/db/schema.py`: `CURRENT_VERSION = 40`; the v40 block; the
  `:319-327` comment rewritten to the true rule.
- `the_one/db/models.py`: `KBItem` with `type: Literal["file","url",
  "folder"]`, `status: Literal["pending","indexing","indexed","failed"] =
  "pending"`, `error: str | None = None`, `content_hash: str | None = None`,
  `size_bytes: int | None = None`, `mtime: float | None = None`, `updated_at:
  str = Field(default_factory=now_iso)`, `indexed_at: str | None = None`;
  two import-time asserts pinning both `Literal`s to the tuples.
- `the_one/db/repositories.py`: every `commit()` replaced by a
  `write_transaction` block (41 sites); `KBItemRepository.create` writes the
  new columns; new `update_status`, `set_content_identity`, `list_by_status`,
  `count_by_status`; `_row_to_model` reads the new columns.
- `the_one/interfaces/web/api.py`: `GET /knowledge-bases/{kb_id}/items/{item_id}`;
  `POST /knowledge-bases/{kb_id}/items/{item_id}/retry`; `create_kb_item`
  returns 404 for an unknown KB; `delete_kb_item` scoped by `kb_id`; the
  rotation endpoint's write block inside `write_transaction`.
- Tests: `tests/test_db_migration.py::TestSchemaV40` (+ `_rewind_to_v39_kb_items`
  helper; the `:4389` assertion updated to 40); `tests/test_kb_types_consistency.py`
  (new); `tests/test_db_write_lock.py` (new — behaviour + source guard);
  `tests/test_db_repositories.py` additions; `tests/test_db_api.py` additions.
- Flight log: leg entry with the unit-gate figure and the migration test
  count. `the_one/agents.md`: the `db-writes-hold-the-write-lock` convention
  entry (Leg 2 adds the FTS-specific rules to it).

## Acceptance Criteria

- [x] AC-1 `CURRENT_VERSION == 40`; a fresh DB after `ensure_schema` has
      `kb_items` with columns `{id, kb_id, parent_id, type, path_or_url,
      status, error, content_hash, size_bytes, mtime, created_at,
      updated_at, indexed_at}`, `kb_chunks` with `{id, item_id, kb_id, seq,
      text, char_start, char_end, created_at}`, `kb_chunks_fts` present, and
      `sqlite_master` **containing** `kb_items`, `kb_chunks`, `kb_chunks_fts`,
      `sqlite_sequence`, `idx_kb_items_kb_id`, `idx_kb_items_kb_status`,
      `idx_kb_chunks_kb_id` (membership, never an exact set — FTS5 shadow
      tables `kb_chunks_fts_data/_idx/_docsize/_config` also exist).
- [x] AC-2 Upgrade from a v39-shaped DB carrying three `kb_items` rows —
      status `'pending'`, status `NULL`, status `'garbage'` — preserves all
      three with ids, `kb_id`, `parent_id`, `type`, `path_or_url`, `created_at`
      intact; the NULL and `'garbage'` rows read back as `'pending'`;
      `updated_at` equals `created_at` for migrated rows; `PRAGMA
      foreign_keys` is 1 afterwards.
- [x] AC-3 Both CHECKs hold on a fresh DB: `type='folder'` and every status in
      `KB_ITEM_STATUSES` insert; `type='blob'` and `status='done'` raise
      `sqlite3.IntegrityError`.
- [x] AC-4 `ensure_schema` twice stamps 40 exactly once; the `>= 7`
      rewind-rerun (the `test_v39_tolerant_of_rewind_rerun` pattern) does not
      raise and leaves the AC-1 shape intact; a stamp-only rewind
      (`DELETE … WHERE version >= 40`) re-runs without rebuilding (the
      column-absence guard short-circuits) and preserves rows.
- [x] AC-5 `kb_chunks` ids are never recycled: insert three rows, delete the
      last, insert again → the new id is greater than every id ever issued.
- [x] AC-6 `KBItemRepository.update_status` performs exactly the transitions
      in `KB_ITEM_TRANSITIONS` (`pending→indexing→indexed`, `indexing→failed`,
      `indexing→pending`, `failed→pending`, `indexed→pending`), as **one**
      conditional `UPDATE`; every other pair raises `KBItemTransitionError`;
      an unknown id raises `KeyError`; `failed` carries `error`, and moving
      out of `failed` clears it; reaching `indexed` stamps `indexed_at`; every
      transition stamps `updated_at`.
- [x] AC-7 `set_content_identity`, `list_by_status(kb_id, status)` and
      `count_by_status(kb_id) -> dict[str, int]` (all four statuses present,
      zeros included) behave as named, with tests.
- [x] AC-8 `write_transaction`: (a) a task that raises after its first
      statement leaves none of its rows; (b) **the interleave case** — task A
      inserts, awaits, then raises, while task B performs a plain
      single-statement repository write in the gap: A's rows are absent, B's
      row is present; (c) same-task re-entry raises `RuntimeError` before
      acquiring; (d) two tasks contending complete in sequence with both
      commits landing.
- [x] AC-9 Source guard: `.commit()` and `.rollback()` occur in exactly two
      files under `the_one/` — `the_one/db/_write_lock.py` and
      `the_one/db/schema.py` — asserted by a test that scans the package
      (the same genre as `tests/test_ui_guards.py`), with a docstring stating
      why `schema.py` is exempt.
- [x] AC-10 Routes: `GET …/items/{item_id}` returns the item (404 for an
      unknown id **or** an id belonging to a different KB); `POST
      …/items/{item_id}/retry` moves `failed` and `indexing` items to
      `pending` (200 with the item) and returns 409 for any other status and
      404 for unknown/other-KB ids; `POST …/{kb_id}/items` for an unknown KB
      returns 404, not 500; `DELETE …/{kb_id}/items/{item_id}` returns 404
      when the item exists but belongs to another KB.
- [x] AC-11 The rotation endpoint's write block runs inside
      `write_transaction` and `encryptor.install_key(new_key)` is still the
      first statement after the block exits with no `await` between the
      commit (context exit) and the install — the existing Q1 invariant.
      The existing rotation tests pass unchanged.
- [x] AC-12 `make test-unit` green; `ruff check` and `ruff format --check`
      clean; the unit-gate wall time stays within the 455–470 s band
      (3,950 tests at Flight 1 close).

## Verification Steps

- AC-1–5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_db_migration.py -x --timeout 60 -k V40` and the fresh-DB
  `PRAGMA table_info` / `sqlite_master` assertions in `TestSchemaV40`.
- AC-3 also via `tests/test_kb_types_consistency.py` (Literal == tuple for
  both fields; fresh-DB CHECK rejects a bogus value for both — the
  `test_provider_types_consistency.py` shape).
- AC-6–7: `tests/test_db_repositories.py::TestKBItemRepository*`.
- AC-8–9: `tests/test_db_write_lock.py`.
- AC-10: `tests/test_db_api.py::TestKnowledgeBaseAPI` additions.
- AC-11: the existing `tests/test_*rotat*` / encryption tests, plus reading
  `api.py`'s block.
- AC-12: `make test-unit`; `ruff check the_one/ tests/`; `ruff format --check
  the_one/ tests/`.

## Implementation Guidance

1. **`_kb_types.py` first**, so the model, the repository and the tests import
   one source. Docstring in the `_provider_types.py` style, but say plainly
   that the **SQL CHECKs are frozen inline literals in the v40 block and are
   not derived from these tuples** (`schema.py:22-28` is the rule); the tuples
   pin the Pydantic `Literal`s and the transition table only. Keep the
   transition map keyed by target so `update_status` can render `status IN
   (…)` from it.

2. **`_write_lock.py`.** One module-level `asyncio.Lock` and one module-level
   `_owner: asyncio.Task | None`. `write_transaction(conn)`:
   ```python
   task = asyncio.current_task()
   if _owner is task:
       raise RuntimeError("write_transaction re-entered by its own task — compose as sequential transactions, never nested")
   async with _lock:
       _owner = task
       try:
           yield
           await conn.commit()
       except BaseException:
           await conn.rollback()
           raise
       finally:
           _owner = None
   ```
   Decorated with `@contextlib.asynccontextmanager`. Check `_owner`
   **before** `async with _lock` — inside it would deadlock, which is the
   thing the check exists to prevent. `reset_for_test()` clears the owner
   and replaces the lock; `tests/test_db_write_lock.py` wires it into a
   module-local `autouse=True` fixture (the `tests/test_sandbox_factory.py`
   `_reset_selection_log_state` pattern — not a global conftest change),
   because the lock and owner are module-level state shared across the
   whole test session.
   Rollback on `BaseException` so a `CancelledError` mid-write does not leave
   an open transaction for the next holder to commit by accident.

3. **v40 block** appended after v39 (`:2370`), comment header citing this
   leg, DD-5 and DD-13. Order: (a) `DROP TABLE IF EXISTS kb_items_new` as the
   v33-style defensive prelude; (b) guard: table present **and**
   `"content_hash" not in PRAGMA table_info(kb_items)`; (c) if guarded-in,
   one `executescript`:
   ```
   PRAGMA foreign_keys=OFF;
   CREATE TABLE kb_items_new (
       id TEXT PRIMARY KEY,
       kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
       parent_id TEXT REFERENCES kb_items_new(id) ON DELETE CASCADE,
       type TEXT NOT NULL CHECK (type IN ('file', 'url', 'folder')),
       path_or_url TEXT NOT NULL,
       status TEXT NOT NULL DEFAULT 'pending'
           CHECK (status IN ('pending', 'indexing', 'indexed', 'failed')),
       error TEXT,
       content_hash TEXT,
       size_bytes INTEGER,
       mtime REAL,
       created_at TEXT NOT NULL DEFAULT (datetime('now')),
       updated_at TEXT NOT NULL DEFAULT (datetime('now')),
       indexed_at TEXT
   );
   INSERT INTO kb_items_new (id, kb_id, parent_id, type, path_or_url, status, created_at, updated_at)
       SELECT id, kb_id, parent_id, type, path_or_url,
              CASE WHEN status IN ('pending','indexing','indexed','failed') THEN status ELSE 'pending' END,
              created_at, created_at
       FROM kb_items;
   DROP TABLE kb_items;
   ALTER TABLE kb_items_new RENAME TO kb_items;
   ```
   then `PRAGMA foreign_keys=ON` as its own `execute`, for consistency with
   v37 (`:2181-2184`) — the reviewer verified it also takes effect as the
   last statement inside the script, as v39 does it; either is correct, and
   forgetting it altogether leaves the singleton with FKs off for the
   process. The self-FK `parent_id` is declared against
   `kb_items_new` exactly as v37 declares `restored_from`; the RENAME
   rewrites it. Columns are named explicitly on both sides of the
   INSERT-SELECT, never positional. (d) `CREATE TABLE IF NOT EXISTS
   kb_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL
   REFERENCES kb_items(id) ON DELETE CASCADE, kb_id TEXT NOT NULL REFERENCES
   knowledge_bases(id) ON DELETE CASCADE, seq INTEGER NOT NULL, text TEXT
   NOT NULL, char_start INTEGER NOT NULL, char_end INTEGER NOT NULL,
   created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE (item_id,
   seq))` as a plain `execute`. (e) `CREATE VIRTUAL TABLE IF NOT EXISTS
   kb_chunks_fts USING fts5(text, content='kb_chunks', content_rowid='id',
   tokenize='porter unicode61')`. (f) the three `CREATE INDEX IF NOT EXISTS`
   as plain `execute`s. (g) `INSERT OR IGNORE INTO schema_version … (40)`
   last, `commit()`, `version = 40`. Add the one-line comment that the
   `executescript` requires no open transaction touching the FTS table
   (true today because every block commits).

4. **Rewrite the `:319-327` comment** to the measured rule: under
   `isolation_level=""` the first DML opens a transaction that ends only at
   `commit()`/`rollback()`; DDL and PRAGMA do **not** auto-commit (removed in
   Python 3.6); what splits a transaction is another coroutine's `commit()`
   on the shared connection — hence `write_transaction` (DD-13). Keep the
   rest of that comment (stamp-last, `OR IGNORE`) intact.

5. **Models.** Add the fields; keep `parent_id` untouched; add the two
   import-time asserts next to the provider one. `extra` stays default
   (`ignore`) — the API routes are `Request`-based hand-validators and the
   existing PUT route relies on merge-then-revalidate.

6. **Repositories — the mechanical sweep.** Replace every
   `await self.conn.execute(...); await self.conn.commit()` pair with
   `async with write_transaction(self.conn): await self.conn.execute(...)`.
   Existence checks that raise `KeyError` stay **outside** the block (reads
   need no lock and must not hold it across a raise). Methods that already
   do several writes before one commit (look for loops in `SQLiteAgentStore`
   and the connector/MCP repos) wrap the whole sequence. Do it file-wide in
   one pass and let AC-9's guard test prove nothing was missed.

7. **`KBItemRepository`.** `create` inserts all thirteen columns. `update_status(
   item_id, status, *, error=None)`: first `if status not in
   KB_ITEM_TRANSITIONS: raise ValueError(...)` — never let the dict lookup's
   `KeyError` masquerade as "item not found"; then `allowed =
   KB_ITEM_TRANSITIONS[status]` and one `UPDATE kb_items SET status=?,
   error=?, updated_at=?, indexed_at=CASE WHEN ?='indexed' THEN ? ELSE
   indexed_at END WHERE id=? AND status IN (…)` inside `write_transaction`,
   binding **one** `now = now_iso()` for both `updated_at` and the
   `indexed_at` THEN-branch so the two stamps are identical on the
   transition into `indexed`. `cur.rowcount` from `async with conn.execute(
   …) as cur` is the precedent at `repositories.py:265-270`
   (`SQLiteAgentStore.compare_and_set_field`); if `rowcount == 0`, one `SELECT status` to
   raise `KeyError` (missing) or `KBItemTransitionError(f"{current}→{status}")`;
   return the re-read item. `error` is stored only when `status == 'failed'`
   and set to NULL otherwise. `set_content_identity(item_id, *, content_hash,
   size_bytes, mtime)` is one UPDATE stamping `updated_at`. `list_by_status`
   uses the `(kb_id, status)` index; `count_by_status` is one `GROUP BY`
   folded onto a dict seeded with every status at 0.

8. **Routes.** Add the two under the `# ── KB Items ──` banner. Scoping rule
   for every item route: fetch by id, then `if item.kb_id != kb_id: 404` —
   same message as unknown, so ids do not leak across KBs. `retry`: catch
   `KBItemTransitionError` → 409 with the current status in `detail`.
   `create_kb_item`: `await _kb_repo().get(kb_id)` → 404 before validating
   the body. `delete_kb_item`: scope check before `repo.delete`.

9. **Rotation endpoint.** Replace the `try: … await conn.commit() except:
   await conn.rollback(); encryptor.discard_pending_key(); raise` shape with
   `try: async with write_transaction(conn): <reads and updates> except
   Exception: encryptor.discard_pending_key(); raise` and keep
   `encryptor.install_key(new_key)` as the very next line after the `try`
   block — the context manager's exit **is** the commit, and the existing
   "no `await` between commit and install" comment stays true because the
   exit returns synchronously after its awaited commit. Reads may sit inside
   the block (the lock serialises; it does not care about reads). Update
   the stale `:4642-4647` comment only insofar as it references the removed
   `commit()` — the full rewrite is squawk 0051 and stays out of this leg.

10. **Tests.** `TestSchemaV40` mirrors `TestSchemaV39`'s four shapes plus
    AC-2 (via a `_rewind_to_v39_kb_items(conn)` helper that drops the v40
    `kb_items`, recreates the exact `SCHEMA_V1` shape from `schema.py:72-80`,
    seeds the three rows, deletes `schema_version >= 40`), AC-3 and AC-5.
    Update the literal at `:4389` to 40 and leave the v39 test otherwise
    intact. `tests/test_db_write_lock.py` needs a real `aiosqlite`
    connection with a throwaway table; for AC-8(b) use `asyncio.gather` with
    an `asyncio.Event` so B's write is provably inside A's gap. AC-9 scans
    `Path("the_one").rglob("*.py")`.

11. **`agents.md`.** Add `### \`db-writes-hold-the-write-lock\`` to Project
    Conventions (Project-wide group): the one-sentence rule, why (the
    Architect's model), the exemption for `ensure_schema`, the no-nesting
    rule ("compose as sequential transactions"), and the guard test's name.

12. **Flight log entry** with: migration test count, `make test-unit`
    figures, the `commit()` sweep count (expect 41 + 1), and anything the
    sweep surfaced.

## Edge Cases

- **Crash between `CREATE kb_items_new` and `RENAME`**: the `DROP TABLE IF
  EXISTS kb_items_new` prelude makes the next `ensure_schema` clean.
- **Rewind-rerun (`>= 7`)**: v40 re-enters with `content_hash` present →
  guard skips the rebuild; every later statement is `IF NOT EXISTS` / `OR
  IGNORE`. The FTS table survives; test asserts it is still queryable.
- **`PRAGMA foreign_keys=OFF` inside `executescript`**: `executescript`
  commits any open transaction first, so the PRAGMA takes effect; the
  matching `ON` must be a separate `execute` after the script.
- **`status = NULL` legacy rows**: mapped by the `CASE` in the INSERT-SELECT;
  `_row_to_model`'s `or "pending"` fallback becomes dead code and is removed
  (the column is `NOT NULL` now).
- **`sqlite_sequence`**: appears once any `AUTOINCREMENT` table exists; the
  `sqlite_master` assertions are membership-style so it cannot break them.
- **`write_transaction` and `CancelledError`**: rollback runs on
  `BaseException`; the lock is released by `async with`.
- **Re-entry detection across tasks**: `_owner` is compared by identity to
  `asyncio.current_task()`; a *different* task simply waits on the lock.
- **Repository methods that raise `KeyError` after an existence check**: the
  check stays outside the guard; the guard wraps only the statement(s) that
  write.
- **No cascade-cleanup code in this leg**: `kb_chunks` carries `ON DELETE
  CASCADE` but nothing writes chunks until Leg 2, so
  `KnowledgeBaseRepository.delete` / `KBItemRepository.delete` change only
  by the guard sweep; the FTS/vector cleanup hooks are Leg 2's.
- **`delete_kb_item` cross-KB**: today deleting item X through any KB's path
  succeeds — that is a behaviour change; `tests/test_db_api.py::test_kb_items`
  uses the correct KB and stays green.
- **Windows path**: nothing platform-specific in this leg.

## Files Affected

- `the_one/db/_kb_types.py` — new
- `the_one/db/_write_lock.py` — new
- `the_one/db/schema.py` — `CURRENT_VERSION`, v40 block, `:319-327` comment
- `the_one/db/models.py` — `KBItem` fields + asserts
- `the_one/db/repositories.py` — `write_transaction` sweep (41 sites), `KBItemRepository` methods
- `the_one/interfaces/web/api.py` — two item routes, two route fixes, rotation block
- `the_one/agents.md` — convention entry
- `tests/test_db_migration.py` — `TestSchemaV40`, helper, `:4389` literal
- `tests/test_kb_types_consistency.py` — new
- `tests/test_db_write_lock.py` — new
- `tests/test_db_repositories.py` — `KBItemRepository` additions
- `tests/test_db_api.py` — item route additions
- `missions/24-knowledge-bases/flights/02-storage-and-embedding-foundation/flight-log.md` — leg entry

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (the Flight Director sets `completed` after the flight-end review)
- [x] Check off this leg in flight.md
- [x] Do NOT commit — review and commit are deferred to the flight-end review

## Citation Audit

Design review (Developer, 2026-09-14) verified every cited location against
the working tree and ran nine empirical probes (v40 rebuild end-to-end with
the three seed rows and a self-referential `parent_id`; `executescript` +
PRAGMA; `AUTOINCREMENT` non-recycling; external-content FTS5 sync, rebuild
and integrity-check; conditional `UPDATE` + `rowcount`; the commit →
`install_key` scheduling invariant under an `asyncio.Lock` with a contending
task; the repository re-entry sweep; the rotation failure test's
`commit`-patch path; the corpora-guard regex). All held. Two citations
corrected: `TestSchemaV39` is `:4338-4519` (was `:4439-4519`, omitting the
two tests AC-1/AC-2 mirror); the provider assert is `models.py:70-75`.
