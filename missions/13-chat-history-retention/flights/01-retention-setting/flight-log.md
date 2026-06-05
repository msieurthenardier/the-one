# Flight Log: Retention Setting

**Flight**: [Retention Setting](flight.md)

## Summary

Flight in execution under `/agentic-workflow` (deferred review/commit model: per-leg design
review, single flight-level code review + commit after the last autonomous leg). Branch
`flight/01-retention-setting`. Two autonomous legs + behavior-test acceptance.

---

## Leg Progress

### Leg 1 — retention-field-and-persistence (`landed`)

**Changes made:**
- `the_one/agent/config.py`: Added `chat_history_retention_days: int = Field(default=30, ge=1, le=365)` to the `# Behavior` group after `max_iterations`.
- `the_one/db/schema.py`: Bumped `CURRENT_VERSION` from 29 to 30. Added `if version < 30:` migration block with `agents` table-presence guard (mirrors v29's `pending_approvals` guard), PRAGMA column guard, `ALTER TABLE agents ADD COLUMN chat_history_retention_days INTEGER NOT NULL DEFAULT 30` (SQL hand-split across two lines per ruff 100-char limit), `INSERT OR IGNORE INTO schema_version` last, `await conn.commit()`, `version = 30`.
- `the_one/db/repositories.py`: Added `chat_history_retention_days` to `save()` INSERT column list, VALUES placeholders (now 18 `?`), ON CONFLICT DO UPDATE SET clause, and parameter tuple. Added direct decode `chat_history_retention_days=row["chat_history_retention_days"]` in `_row_to_config()` (no `or 30` per DD3).
- `tests/test_db_migration.py`: Relaxed two `assert CURRENT_VERSION == 29` pins (at :278 and :5018) to `>= 29` with updated messages. Added `TestSchemaV30` class (3 sub-tests: fresh-DB-has-column, v29-fixture-migration-adds-column-and-backfills-to-30, idempotent-re-run). Module-level `assert CURRENT_VERSION >= 30` guard added per `>= N` idiom.
- `tests/test_config.py`: Added `TestChatHistoryRetentionDaysField` class with default (30), boundary (1 and 365 valid), and reject (0, 366, -5 raise `pydantic.ValidationError`) tests. Added `pydantic` import.
- `tests/test_db_api.py`: Added `test_create_agent_persists_chat_history_retention_days` (POST with 90, GET back 90, PUT to 180, GET back 180) and `test_create_agent_with_out_of_range_retention_days_returns_422` (400 → HTTP 422).

**Test results (in-container, after `make rebuild`):**
- `tests/test_config.py`: 32 passed
- `tests/test_db_migration.py`: 84 passed
- `tests/test_db_api.py`: 117 passed
- Combined: 233 passed, 0 failed
- `ruff check the_one tests`: all checks passed
- `ruff format --check the_one tests`: 324 files already formatted

**Decisions/anomalies:**
- The v30 migration block required an `agents` table-presence guard (via `sqlite_master` check) because some existing test fixtures in `test_db_migration.py` build partial schemas (e.g. only `connector_accounts`) and `PRAGMA table_info(agents)` returns empty when the table is absent, causing `ALTER TABLE agents` to fail with `no such table`. The v29 block uses the same defensive pattern for `pending_approvals`. No spec change required.
- The `test_v30_migration_on_v29_fixture_adds_column_backfills_rows` test builds a fresh minimal v29-shaped DB from scratch rather than rewinding a full-schema DB (SQLite < 3.35 does not support DROP COLUMN, making the "rewind then re-add column" approach unreliable). The fresh-file approach cleanly exercises the migration code path.

### Leg 2 — retention-input-general-tab (`landed`)

**Changes made:**
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js`: Added `chat_history_retention_days: 30` to the create-mode default `cfg` object. Added a `field-row` for the retention days input (`id="studio-retention-days"`, `data-field="chat_history_retention_days"`, `type="number"`, `min="1"`, `max="365"`, seeded from `cfg.chat_history_retention_days || 30`) inside the Behavior `editor-section`, positioned immediately before the Max Iterations `field-row`.
- `the_one/interfaces/web/static/js/areas/studio.js`: Added `else if (key === 'chat_history_retention_days')` branch in `collectFormData` using DD6-compliant raw-value preservation (`var n = parseInt(f.value, 10); data[key] = Number.isNaN(n) ? 30 : n;`), slotted between the `max_iterations` and `provider_config_id` branches.
- `tests/browser/test_flow_agent_tabs.py`: Added `test_retention_days_input_renders_above_max_iterations` — a `@pytest.mark.browser` test using `app_with_agent` + `_wait_editor_ready(page)` that asserts: the `[data-field="chat_history_retention_days"]` input is visible with `id="studio-retention-days"`, `type="number"`, `min="1"`, `max="365"`; and it precedes `[data-field="max_iterations"]` in DOM order via `compareDocumentPosition`.

**Test results (in-container, after `make rebuild`):**
- `docker exec the-one bash /app/scripts/run-tests.sh -m browser tests/browser/test_flow_agent_tabs.py -v --tb=short`
- Collected 13 items; 12 passed, 1 skipped (expected skip: `test_advanced_section_visible_with_disabled_inputs`)
- New test `test_retention_days_input_renders_above_max_iterations` — **PASSED**
- No regression: all 11 previously-passing tests still pass
- `ruff check tests`: all checks passed
- `ruff format --check tests`: 220 files already formatted

**Decisions/anomalies:**
- Playwright Chromium and its system-library dependencies were not present in the running container (they are installed at image-build time by `playwright install-deps` and `playwright install chromium` in the Dockerfile, but the running container had a newer Playwright version that referenced a different chromium-headless-shell revision). Required: `playwright install chromium` then individual `apt-get install` calls for missing `.so` files (`libglib-2.0.so.0`, `libnspr4`, `libnss3`, and related X/CUPS libraries). These installs are ephemeral to the running container — the Makefile `make rebuild` will rebake a clean image with all deps. The tests ran and passed correctly after the deps were present.

---

## Flight Director Notes

### Leg 1 spot-check (Flight Director)
- Verified the landed diff is in scope (exactly the 6 authorized files), `CURRENT_VERSION = 30`,
  the v30 block is well-formed (sqlite_master table guard + PRAGMA column guard + E501-split ALTER
  + INSERT-last + commit + `version = 30`), and the `save()`/decode edits are present. The
  Developer's added `agents` table-presence guard matches the v29 defensive pattern — accepted.

### Leg 2 design (`retention-input-general-tab`)
- Authored from the flight spec; spawned a Developer (Sonnet) for design review. Verdict:
  **approve with changes**.
- Self-verified the two medium findings before incorporating: (1) `pyproject.toml:76` `addopts`
  deselects `browser` by default, so a bare `pytest tests/browser/...` runs ZERO tests (false
  green) — corrected the leg's verification to the canonical `run-tests.sh -m browser` /
  `make test-browser` form; (2) `max_iterations` uses `|| 20`, not `|| 30` — fixed the mislabel in
  both the leg and flight DD6 (guidance unchanged: preserve the raw value, no falsy coercion).
  Also set `compareDocumentPosition` as the primary DOM-order assertion (project idiom) and noted
  `THE_ONE_DEV_MODE` is handled by `conftest.py`. Minor/correctness fixes only → second design
  cycle skipped. Leg 2 → `ready`.

### Orchestration start
- **Phase file**: `.flightops/agent-crews/leg-execution.md` (project crew) — validated, all
  required sections present. Developer = Sonnet, Reviewer = Haiku, Accessibility Reviewer =
  Sonnet (spawn only for the UI leg).
- **Planning gate**: flight was `planning`; the operator's `/agentic-workflow` invocation is
  the approval clearing the gate. Transitioned `planning → in-flight` and created branch
  `flight/01-retention-setting` (carrying the uncommitted planning artifacts — they land with
  the flight).
- **Leg plan**: (1) `retention-field-and-persistence` — backend, no UI; (2)
  `retention-input-general-tab` — frontend, UI (Accessibility Reviewer applies at flight
  review). Behavior test `agent-retention-setting-roundtrip` is flight-level acceptance, run
  after both legs implement + `make rebuild`.
- **Project test convention** (from crew Implement prompt): `docker exec the-one pytest …`
  (NOT `docker compose exec`), always `-x --timeout 30`. Relayed to every Developer spawn.

### Flight 1 review gate (Flight Director)
- **Code review** (Haiku): confirmed — all findings resolved; no blocking issues.
- **Accessibility review** (Sonnet): confirmed — all findings resolved; no blocking issues.
- Both legs marked `completed`; source code and artifacts staged for the single flight-level commit.
- **Non-blocking observation carried forward**: the General-tab `system_prompt` textarea
  (`general-tab.js`, System Prompt section) lacks a `<label for>`/`id` association (WCAG 1.3.1
  / 4.1.2). Pre-existing — not introduced by this flight. Carry forward to a future flight or
  maintenance pass.

### Leg 1 design (`retention-field-and-persistence`)
- Authored the leg artifact directly from the (architect-validated) flight spec — DD-driven,
  no human interview needed. Spawned a Developer (Sonnet) for design review.
- Review verdict: **approve with changes**. Confirmed the two literal `== 29` pins
  (`test_db_migration.py:278`, `:5018`) are the ONLY version pins that break, and that NO test
  asserts an exhaustive `agents` column-set (new column is safe). SQLite `NOT NULL DEFAULT 30`
  and Pydantic `Field(ge/le)`→422 mechanics verified.
- Incorporated (minor spec-clarity only, no design change → second cycle skipped): prefixed the
  `api.py` path to `the_one/interfaces/web/api.py`; dropped the imprecise `:129` citation; made
  the idempotent re-run an explicit third `TestSchemaV30` sub-test; set the new class-guard style
  to `>= 30`. Leg 1 → `ready`.

---

## Decisions

_None yet._

---

## Deviations

_None yet._

---

## Anomalies

_None yet._

---

## Session Notes

_None yet._
