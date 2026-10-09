# Leg: unit-template-db

**Status**: completed
**Flight**: [Test-suite runtime](../flight.md)

## Objective
Unit-tier tests stop replaying every migration for each test database. They copy one migrated template built once per pytest session, so the unit lane takes 300 s or less with an unchanged pass set and skip count.

## Context
- **Flight decision "Template database, not a reset seam"**:
  - `ensure_schema` creates tables and inserts constant rows only. It generates no ids, keys or credentials, so a copy of a migrated database is equivalent to a fresh replay.
  - The one value that differs is `schema_version.applied_at` (`datetime('now')`), which records when the template was built.
- **Measured cost** (maintenance report 2026-10-08, T1/R2):
  - About 524 s of the 697 s unit lane is fixture setup.
  - A fresh `ensure_schema` takes 0.37–0.59 s: 41 version steps (`CURRENT_VERSION = 41`), each an `executescript` plus an fsync'd commit.
  - The heaviest files are `test_db_api.py` (184 tests, 79 s), `test_db_repositories.py` (212 tests, 80 s), `test_provider_api.py` (187 tests, 73 s), `test_self_configuration_api.py`, `test_ws_start_session.py` (through `isolated_db`) and `test_vector_store.py`.
- **Baseline.** Unit runs 5598 passed, 12 skipped, 697 s, sequential, under `THE_ONE_TEST_NETNS=1`.
  - The 12 skips are the 10 Windows skips plus 2 root-only permission tests. They are not the timing skips.
  - Without netns, expect 10 skips, or 12 when the timing-conditional watcher tests skip. See CLAUDE.md "Expected unit skip count".
- **First leg of the flight.** No prior leg outcomes. Leg 2 (`browser-template-db`) reuses this leg's template helper from `tests/browser/conftest.py`, so the helper must be importable and usable from a plain synchronous call.

## Inputs
- `the_one/db/schema.py::ensure_schema`, `CURRENT_VERSION = 41`.
- `the_one/db/connection.py`:
  - `_connection` is the process singleton.
  - `get_connection()` creates the file with `_create_or_tighten_db_file` (mode 0o600), then sets `journal_mode=WAL` and `foreign_keys=ON`.
  - `init_db()` calls `ensure_schema` on the singleton.
- The four ways the unit tests build a database:
  1. **Direct side connection.** `aiosqlite.connect(path)`, `row_factory`, `PRAGMA foreign_keys=ON`, then `ensure_schema(conn)`. This is the form in `tests/conftest.py::isolated_db` and `tests/test_db_api.py::client`, and in most of the 55 files that call `ensure_schema(`.
  2. **`:memory:` connections.** `test_key_reconcile.py`, `test_provider_repository.py`, `test_kb_retrieval.py:562`, `test_schema.py`.
  3. **`init_db()` or the real lifespan** against `settings.data_dir = tmp_path`. Files: `test_lifespan.py`, `test_web_session_reaper.py`, `test_db_write_lock.py`, `test_chat_history_purge.py`, `test_self_configuration_surface.py`, `test_mcp_pool.py`, plus `TestClient(app)` users such as `test_credential_gate.py`, `test_origin_allowlist.py`, `test_window_focus.py`, `test_api_window_chrome.py`, `test_index_asset_cache_busting.py` and `test_connector_stub_registration_hook.py`.
  4. **The real migration path, on purpose.** `test_db_migration.py` (153 calls), `test_schema.py` (19), and `test_db_connection.py::TestSchemaCreation`.

## Outputs
- **New `tests/_schema_template.py`:**
  - builds the template once per process, lazily;
  - copies it into a test's path;
  - opens a connection on the copy.
- **Converted call sites:**
  - `isolated_db`, `test_db_api.py::client` and every other per-test database built by forms 1 and 3;
  - form 2 where it is a plain fresh database.
- **`PRAGMA synchronous=OFF`** on the connections of tests that still replay migrations: `test_db_migration.py`, `test_schema.py`, and any other site kept on the real path for speed-neutral reasons.
- **New `tests/test_schema_template.py`:** the equivalence guard and the call-site guard.
- **Flight log:** a timing entry for this leg.

## Acceptance Criteria
- [ ] **AC1. The template helper exists.**
  - `tests/_schema_template.py` exposes `template_path()`, which returns the path of a migrated SQLite file. The file is:
    - built with the real `ensure_schema` at most once per pytest process;
    - in `journal_mode=DELETE`;
    - a single file, with no `-wal` or `-shm` sidecar.
  - `template_path()` works when called from a synchronous fixture and from inside a running event loop (an async fixture or test body).
  - The template lives in a temporary directory that is removed at session end.
- [ ] **AC2. Copy and connect helpers exist.**
  - `copy_template(dest)` copies the template to `dest`, which must not exist yet, and leaves it at mode `0o600`.
  - `await connect_template_db(dest)` copies, then returns an `aiosqlite` connection with `row_factory = aiosqlite.Row` and `PRAGMA foreign_keys=ON`. This is the same connection a form-1 site builds today.
- [ ] **AC3. The template matches a fresh replay.** A guard test in `tests/test_schema_template.py` proves that, compared with a database built by the real `ensure_schema` in the same test:
  1. `MAX(version)` in the template's `schema_version` equals `CURRENT_VERSION`, and the set of `version` rows is identical.
  2. `sqlite_master` rows `(type, name, tbl_name, sql)` are identical. Order by type and name, and exclude nothing.
  3. Every non-`schema_version` table holds identical rows.
     - This includes the FTS5 shadow tables (`kb_chunks_fts_data`, `_idx`, `_docsize`, `_config`) and `sqlite_sequence` if present. Compare them as ordinary tables, and skip nothing.
     - Compare a virtual table through its shadow tables, not with `SELECT *`.
  4. `PRAGMA foreign_key_list`, `index_list` and `table_info` match for every table.
     - Skip an `sqlite_%` internal table only if the pragma errors on it.
- [ ] **AC4. Unit-tier call sites use the template.**
  - **Form 1 and form 2:** every per-test fresh database in the unit tier is built through `connect_template_db` or `copy_template`, except the sites AC5 exempts.
  - **Form 3:** sites pre-seed `settings.db_path` with `copy_template` before `init_db` or the lifespan runs. `ensure_schema` still runs in production code and finds the database at `CURRENT_VERSION`.
- [ ] **AC5. The real path stays real.** These sites keep calling the real `ensure_schema` on a fresh or partial database:
  - `test_db_migration.py`
  - `test_schema.py`
  - `test_db_connection.py::TestSchemaCreation`
  - any test that seeds a partial, old-version or hand-built schema before calling `ensure_schema`
  - any test that asserts file-creation behaviour of `get_connection`, such as mode `0o600` with no chmod window or WAL sidecar modes

  Each exempt file is listed in the guard's allow-list with a one-line reason.
- [ ] **AC6. New slow sites are caught.**
  - A guard test fails when a test file outside the allow-list calls `ensure_schema(` or `init_db(` directly.
  - It walks every `tests/**/*.py` with `ast` (`ast.parse`, as `tests/test_nav_helper.py` already does), and does not use a regex.
  - It flags only an `ast.Call` whose callee is a `Name` or `Attribute` named exactly `ensure_schema` or `init_db`. It does not flag:
    - function definitions such as `_fake_init_db` in `test_mcp_pool.py`;
    - docstrings or comments, such as `test_db_write_lock.py:158`;
    - imports used only for patching.
  - The failure message points at `tests/_schema_template.py`.
  - The allow-list is per file, with a one-line reason each. Expect only genuine real-path files:
    - `test_db_migration.py`, `test_schema.py`, `test_db_connection.py` (the whole file);
    - any lifespan, purge or write-lock file whose test asserts the empty-directory `init_db` behaviour;
    - `:memory:` sites kept on purpose;
    - `tests/_schema_template.py` and `tests/test_schema_template.py`, which are self-exempt.

    Roughly 10 entries. A much longer list means the guard is matching the wrong thing.
  - Form-3 sites whose production code calls `init_db` internally, such as lifespan users, are not flagged; only direct test-file calls are.
- [ ] **AC7. Migration replays skip fsync.** `test_db_migration.py` and `test_schema.py` set `PRAGMA synchronous=OFF` on the connections they replay migrations on. Their assertions are unchanged.
- [ ] **AC8. The pass set and skip count are unchanged.**
  - `make test-unit` passes with the baseline count, plus the new guard tests, and the same skip count as the same invocation on `main`.
  - No existing test is deleted, skipped or `xfail`ed.
- [ ] **AC9. The time target is met and recorded.**
  - The unit lane, run under the same conditions as the baseline (`THE_ONE_TEST_NETNS=1`, sequential, quiet host), takes **300 s or less**.
  - The flight log records the wall time, passed and skipped counts, and the 10 slowest setup phases (`--durations=10`) next to the 697 s baseline.
  - **Fallback if the target is missed:** apply `PRAGMA synchronous=OFF` to every test connection for the session (see step 3a). Measured cost of one replay: 0.446 s with the default setting, 0.052 s with `synchronous=OFF`, about 1 ms for a template copy.
  - **If the measured lane is still over 300 s after the fallback:** do not stretch the leg. Record the measured number and the dominant remaining setup costs in the flight log, land the leg, and report it in the `[LAND:leg]` summary. The Flight Director takes the miss to leg 7's conditional trigger.

## Verification Steps
- **AC1–AC3, AC6:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_schema_template.py -x --timeout 60`
- **AC4/AC5:**
  - Run `grep -rn "ensure_schema(\|init_db(" tests/ --include=*.py`. Every hit is in an allow-listed file or in `tests/_schema_template.py`.
  - The AC6 guard passes.
- **AC7:** `grep -n "synchronous" tests/test_db_migration.py tests/test_schema.py`, then run both files green.
- **AC8:** `make test-unit` (or `PYTHON=.venv/bin/python bash scripts/run-tests.sh` with the unit marker set), then compare the summary line with a `main` run under the same flags. Read `-rs` for skips.
- **AC9:** `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=1800 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m 'not browser and not live and not pixel and not requires_bwrap' --durations=10 -q`
  - Record the wall time.
  - If the host is busy, record that, and rerun before judging the target.

## Implementation Guidance

1. **Write `tests/_schema_template.py`.**
   - **Build function.** Use the stdlib to open a connection on a file in a module-level temporary directory (`tempfile.mkdtemp(prefix="the-one-schema-template-")`, removed through `atexit`). Then:
     - run `await ensure_schema(conn)` through `aiosqlite` (`asyncio.run` of a small coroutine);
     - set `PRAGMA synchronous=OFF` for the build;
     - run `PRAGMA journal_mode=DELETE`;
     - close the build connection **inside the thread's own loop**, before the thread exits, so no aiosqlite worker outlives its loop.
   - **First call blocks.** The first `template_path()` call from async code blocks the event loop for about 0.5 s. That is acceptable.
   - **Build from inside a running loop.** `template_path()` may be called from inside a running loop, where `asyncio.run` raises. Run the build in a short-lived `threading.Thread` that calls `asyncio.run`, and join it. Guard the build with a `threading.Lock` and cache the path in a module global.
   - **`copy_template(dest)`**
     - `shutil.copyfile(template_path(), dest)`, then `os.chmod(dest, 0o600)`.
     - Refuse an existing `dest`: raise, so a test never silently overwrites a database it already wrote.
   - **`async def connect_template_db(dest)`**
     - `copy_template(dest)`, `aiosqlite.connect(str(dest))`, `row_factory = aiosqlite.Row`, `PRAGMA foreign_keys=ON`, then return the connection.
   - **Optional `async def connect_template_memory()`** for `:memory:` sites. Open the template read-only with `aiosqlite` and `await tmpl.backup(mem_conn)` into a fresh `:memory:` connection, which keeps in-memory semantics.
     - A site that opens several `:memory:` connections and relies on them being separate databases keeps that separation: one backup per connection. Check `test_key_reconcile.py:42` and `test_kb_retrieval.py:562`.
   - **Production pragmas.** Do not add `synchronous=OFF` to template-derived connections. They no longer replay migrations, and production semantics should stay. `get_connection()` still switches the copy to WAL on first open, as production does.

2. **Add the guards in `tests/test_schema_template.py`.**
   - AC3: the equivalence test, against a real `ensure_schema` build in `tmp_path`.
   - AC6: the call-site guard, with an explicit allow-list `{path: reason}`.
   - A small test that two `copy_template` destinations are independent: writing to one leaves the other unchanged.

3. **Convert the high-cost fixtures first, measuring as you go:**
   - `tests/conftest.py::isolated_db`
   - `tests/test_db_api.py::client`
   - the fixtures in `test_db_repositories.py`, `test_provider_api.py`, `test_self_configuration_api.py` and `test_vector_store.py`

   - `test_provider_api.py` has two such fixtures, `client` (about line 60) and `plan_env` (about line 3292). Convert both.
   - Most form-1 fixtures share the same four lines (connect, `row_factory`, `foreign_keys` pragma, `ensure_schema`). One mechanical replacement with `connect_template_db(db_path)` covers most of them.

   Run each converted file green before moving on.

3a. **Checkpoint: project the total before converting the rest.**
   - Run the heavy files with `--durations=15` and project the lane total.
   - If the projection is over 300 s, decide now whether to add session-wide `PRAGMA synchronous=OFF` for every remaining real-path test connection. Do it through a helper; do not touch production code.
   - Note whether the lifespan-heavy `TestClient(app)` fixtures dominate what remains. Record the projection in the flight log.

4. **Convert the remaining form-1 and form-2 sites** file by file.
   - A `:memory:` site that only needs a fresh schema becomes a `tmp_path` file built through `connect_template_db`.
   - A `:memory:` site that tests something about in-memory behaviour stays, and is added to the allow-list.

5. **Convert the form-3 sites.** Where a fixture sets `settings.data_dir = tmp_path` before `init_db` or the lifespan runs, call `copy_template(settings.db_path)` after the monkeypatch and before the app starts. Examples: `tests/test_lifespan.py::_isolated_data_dir` and the `TestClient(app)` fixtures.
   - Make sure `settings.db_path`'s parent exists.
   - Exception: a test that asserts what `init_db` does to an empty directory stays on the real path, and is allow-listed.

6. **AC7.** Add `PRAGMA synchronous=OFF` right after connecting in `test_db_migration.py`'s and `test_schema.py`'s connection helpers or fixtures. Do not restructure their per-version tests. The optional class-scoped v(N-1) bases are **out of scope** for this leg.

7. **Run the unit lane under the AC9 conditions** and record it in the flight log (see Post-Completion in the spawn prompt).

## Edge Cases
- **Partial-schema tests.** A test that writes tables or an old `schema_version` before calling `ensure_schema` must keep the real path. Copying the template into it would make `ensure_schema` a no-op and silently stop testing the upgrade. Look for `CREATE TABLE` or `INSERT INTO schema_version` in a test body before an `ensure_schema` call.
- **Tests asserting `applied_at` or the build time.** None are known. If one appears, keep it on the real path and allow-list it.
- **Tests that monkeypatch `CURRENT_VERSION` or migration constants.** These stay real, because the template is built at the unpatched version.
- **Fernet or the encryption key.** These are not in the database file (`key_path` and `.env` are separate files), so the template carries no key material. AC3's row comparison proves that no seeded table holds ciphertext.
- **`-wal` and `-shm` on the template.** These must never exist. AC1 asserts it. A template opened by production code would convert to WAL, so only ever copy it; never open the template itself through `get_connection`.
- **A module that imports `ensure_schema` only for the real-path assertions inside a converted file.** Allow-list it at file level with a reason. Do not contort the guard.
- **Timing skips.** `test_kb_watcher` real-watch skips can vary under load (squawk 0132). Compare skip reasons, not only counts.

- **`tests/test_lifespan.py` and other form-3 files with a direct `ensure_schema` call in a test body** (for example `test_lifespan.py:183,271,310`):
  - Convert the call when the test only needs a migrated database.
  - When it asserts what `init_db` or `ensure_schema` does to an empty or partial database, allow-list the file with that reason.
  - Do not split files only to satisfy the guard.
- **Importing the helper from leg 2.** Leg 2 imports it as `from tests._schema_template import ...`, the same way `tests._credential_helpers` is imported. Do not place anything in it that imports `tests/conftest.py`.

## Files Affected
- `tests/_schema_template.py`: new.
- `tests/test_schema_template.py`: new guard tests.
- `tests/conftest.py`: `isolated_db`.
- `tests/test_db_api.py` and about 50 other `tests/test_*.py` files that build a per-test database (see Inputs).
- `tests/test_db_migration.py`, `tests/test_schema.py`: `synchronous=OFF` only.
- `CLAUDE.md` Testing section: one short paragraph on building a test database through `tests/_schema_template.py`, and never by calling `ensure_schema` on a fresh database outside the allow-listed migration tests.
- `missions/26-maintenance/flights/01-test-suite-runtime/flight-log.md`

## Citation Audit
Checked against the working tree at `16e91d7` (2026-10-08):

| Citation | Status |
|---|---|
| `tests/conftest.py:305` `isolated_db`: side connection, `ensure_schema`, `_connection` reset | verified |
| `tests/test_db_api.py:23` `client`: per-test `ensure_schema` | verified |
| `the_one/db/connection.py:12` `_connection`; `:46` `get_connection` WAL plus `foreign_keys`; `init_db` at the end of the file | verified |
| `the_one/db/schema.py:14` `CURRENT_VERSION = 41`; `:112` `ensure_schema` | verified |
| `the_one/db/schema.py:32` `schema_version.applied_at DEFAULT (datetime('now'))` | verified |
| `:memory:` sites: `test_key_reconcile.py:18,42`, `test_provider_repository.py:24`, `test_kb_retrieval.py:562`, `test_schema.py:75,83` | verified |
| `tests/test_lifespan.py::_isolated_data_dir`: monkeypatches `settings.data_dir` and `_connection` | verified |
| `tests/test_db_connection.py::TestSchemaCreation`: real `get_connection()` plus `ensure_schema` | verified |

The flight spec's "46 migrations" is the count of `version < N` steps as of the report. The code has `CURRENT_VERSION = 41`. Either way, the per-test cost is what was measured.
