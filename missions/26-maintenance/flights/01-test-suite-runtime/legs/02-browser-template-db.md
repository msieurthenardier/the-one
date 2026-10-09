# Leg: browser-template-db

**Status**: completed
**Flight**: [Test-suite runtime](../flight.md)

## Objective
Every browser-test app server starts from a copy of the session's migrated template database, so the server's `init_db` finds the schema current and replays no migrations at boot.

## Context
- **Flight decision "Template database, not a reset seam".** This leg reuses leg 1's template helper, `tests/_schema_template.py`. Leg 1 proves the template equivalent to a fresh `ensure_schema` (AC3 guard), so a server that boots on a copy is in the same state as one that migrated an empty file.
- **Measured cost** (report 2026-10-08, R1/T2):
  - About 936 server starts across the five non-contract lanes, each about 1.15 s of setup.
  - Of that, about 0.37–0.59 s is the server's own `init_db` → `ensure_schema` replay from v0. With fsync on, that is the same cost leg 1 removed from the unit tier.
  - Expected saving: about 0.4 s × 936, roughly 5–6 minutes sequential.
- **The server process imports the same source tree** as the pytest process that built the template, so the template's version always equals the server's `CURRENT_VERSION`. The source of truth is `ensure_schema`, built once per pytest process. It can be stale only if the source changes mid-session, and then the server's `ensure_schema` simply runs the remaining steps.
- **Leg 1 outcome.** See the flight log, "Leg 1: unit-template-db", for the helper's final API and any deviations.

## Inputs
- `tests/_schema_template.py::copy_template(dest)` from leg 1. It copies the template to a path that must not exist yet and sets mode `0o600`.
- `tests/browser/conftest.py::_spawn_app(tmp_path, extra_env=None)`. This is the only spawn path; the other callers are listed under Files Affected. It:
  - creates `tmp_path / "the-one-data"`;
  - writes the credential;
  - runs `Popen` of uvicorn with `THE_ONE_DATA_DIR`;
  - calls `_wait_for_ready`.
- `the_one/config.py::Settings.db_path` is `data_dir / "the-one.db"`.
- `the_one/db/connection.py::get_connection`. It tightens an existing file to `0o600` and switches it to WAL on first open, so a copied DELETE-mode file becomes an ordinary production database.

## Outputs
- `_spawn_app` seeds `data_dir / "the-one.db"` from the template before `Popen`. It gains a keyword `seed_db: bool = True`, so a test that needs the first-boot path can opt out.
- Callers that need an empty data directory pass `seed_db=False`. Only tests that assert first-boot or migration behaviour do so.
- A flight-log entry with the measured per-start setup time before and after.

## Acceptance Criteria
- [ ] **AC1.** `_spawn_app` calls `copy_template(data_dir / "the-one.db")` after `data_dir.mkdir()` and before `subprocess.Popen`, unless `seed_db=False`.
- [ ] **AC2.** A browser-tier check proves a seeded server does not replay migrations.
  - The cheapest observable: after the server is ready, the `schema_version` rows' `applied_at` values in the data directory's database equal the template's. A replay would add new rows; a no-op adds none.
  - A one-file test or an assertion added to an existing fixture test (`tests/browser/test_app_fixture.py`) is enough.
- [ ] **AC3.** Every test that relies on an empty or legacy data directory passes `seed_db=False`, with a one-line comment naming why. If none exists, the flight log says so, along with the grep used to establish that.
  - Look for tests that seed legacy JSON for `migrate_json_to_sqlite`, write the database before boot, or assert first-run state.
- [ ] **AC4.** Browser lanes stay green.
  - Run `chats` and `settings` in full. Those are the two lanes with the heaviest `app_with_data_dir` and direct-sqlite use.
  - Also run every file that calls `_spawn_app` directly.
  - Use `THE_ONE_TEST_NETNS=1`. Passed and skipped counts match the 2026-10-08 baseline: chats 168/0, settings 214/0.
- [ ] **AC5.** The per-start saving is measured against the 2026-10-08 `chats` baseline.
  - Baseline: lane wall time 272 s, 168 passed, and summed setup phases ≥0.05 s of 132 s.
  - The baseline was produced with `--junitxml` plus the inspector's aggregation script, both kept in the Flight Director's scratch area (`<scratchpad>/testperf/chats.xml`, `agg.py`; the Flight Director passes the absolute path in the spawn prompt).
  - After the change, run `chats` the same way with `--junitxml`, aggregate the setup phases the same way, and record before/after setup seconds and wall time in the flight log.
  - The full sequential browser re-measure happens at the end of leg 3, not here.

## Verification Steps
- **AC1:** read `_spawn_app`.
- **AC2:** `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=900 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_app_fixture.py -x --timeout 60`
- **AC3:** grep and reasoning, recorded in the flight log.
- **AC4:** `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -q`, the same for `settings`, plus the `_spawn_app` caller files with `-m browser`.
- **AC5:** `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -v --tb=short -rs --junitxml=<scratch>/leg2-chats.xml --durations=0 --durations-min=0.05 > <scratch>/leg2-chats.log 2>&1`. These are the baseline's exact flags. Then run the baseline's `agg.py`, which parses the `--durations` lines of the log, on the new log, and compare `phases(>=0.05s): setup=` with 132.

## Implementation Guidance
1. **Import the helper** in `tests/browser/conftest.py`: `from tests._schema_template import copy_template`, matching the existing `tests.` import style.
2. **Change `_spawn_app`.** Add `seed_db: bool = True` (keyword) and seed after `data_dir.mkdir()`. Keep the credential write as it is; it is a separate file.
3. **Audit the five other `_spawn_app` callers and `app_with_data_dir` users** for empty-directory assumptions (AC3). Files: `test_app_spawn_credential_wiring.py`, `test_markdown.py`, `test_flow_oauth_callback_cross_site.py`, `test_flow_context_overlay_thresholds.py`, `test_flow_provider_ollama_pull.py`.
4. **Add the AC2 assertion.**
5. **Measure** (AC5) and run the lanes (AC4). Record both in the flight log.

## Edge Cases
- **Tests that write to `the-one.db` while the server runs**, through `sqlite3` direct writes. Examples: `test_flow_chat_visibility_distinction`, `test_flow_chat_peer_attribution`, `test_studio_self_configuration_*`, `test_flow_provider_plan_signin`. These are unaffected: the server has already converted the copy to WAL by the time they write.
- **Template build inside the browser session.** `template_path()` builds lazily, on first use, in the same pytest process. The first browser test pays about 0.5 s once.
- **`data_dir` mode.** `copy_template` sets the file to `0o600`, and production tightens it on open anyway.
- **A module-scoped spawn** (`test_markdown.py`'s module server, if it calls `_spawn_app`) gets the same seeding, which is fine.

## Files Affected
- `tests/browser/conftest.py`: `_spawn_app` and its docstring.
- `tests/browser/test_app_fixture.py`: the AC2 assertion, or a new small test file.
- Any AC3 opt-out callers.
- `missions/26-maintenance/flights/01-test-suite-runtime/flight-log.md`

## Citation Audit
Checked against the working tree at `16e91d7` plus leg 1's uncommitted changes:

| Citation | Status |
|---|---|
| `tests/browser/conftest.py:205` `_spawn_app`: `data_dir.mkdir()` at about 229, credential, `Popen` at about 247, `_wait_for_ready` | verified |
| `tests/browser/conftest.py:129` `_wait_for_ready`: polls `/api/live` with `time.sleep(0.1)` | verified (leg 3 tightens it) |
| `the_one/config.py:106` `db_path` → `data_dir / "the-one.db"` | verified |
| `_spawn_app(` callers: conftest plus 5 test files (11 call sites) | verified |
| `tests/_schema_template.py::copy_template(dest)`: refuses an existing dest, sets mode 0o600 (leg 1 landed) | verified |
