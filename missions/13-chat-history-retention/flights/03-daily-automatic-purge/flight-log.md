# Flight Log: Daily Automatic Purge

**Flight**: [Daily Automatic Purge](flight.md)

## Summary

Flight in `planning`. No legs executed yet. This log captures the planning-time
reconnaissance of the carry-forward items the F2 debrief routed toward Flight 3, plus the
code-surface verification behind the design decisions. Execution notes append below once the
flight goes in-flight.

---

## Reconnaissance Report (planning pass, 2026-06-06)

The F2 debrief enumerated follow-ups; the items it tagged for Flight 3 were walked against
current `main` and classified.

| Item (F2 debrief) | Classification | Evidence | Recommendation |
|---|---|---|---|
| Decide DD2a for the automated case (WS `session_list` staleness) | `confirmed-live` | `session_list` is pull-based — sent only in reply to a client `list_sessions` action (`app.py:1711–1725`); there is no all-clients broadcast registry, only `subscribers_for(sid)`. So a background sweep that deletes DB rows leaves an open tab's in-memory view stale until it re-requests. | **Addressed in DD4**: the sweep evicts matching `_sessions` (clean same-layer touch, since the sweep runs in `app.py` unlike F2's repo-layer endpoint). |
| Decide `last_purge_at` storage (table vs settings vs file) | `confirmed-live` | No app-metadata / kv / settings table exists (`grep` across `the_one/` returns none); `CURRENT_VERSION = 30` (`db/schema.py:15`). | **Addressed in DD1**: new `app_metadata` kv table via v31 migration (atomic leg). |
| Resolve the scheduler behavior-test apparatus (backdated `updated_at` seeding + trigger) | `confirmed-live` | `POST /api/chat/sessions` → `ChatSession.model_validate(data)` → `repo.create(session)` passes `session.updated_at` straight through (`api.py` `create_chat_session`), so aged sessions are seedable by curl with a backdated `updated_at`. No on-demand sweep trigger exists. | **Addressed in DD5**: dev-mode-gated `POST /api/_test/purge-sweep` trigger (mirrors the `THE_ONE_REGISTER_STUB_CONNECTOR` seam at `app.py:124`). Seeding needs no new seam; only the trigger is added. |
| Promote `extractApiError` → `App.extractApiError`; audit `e.detail \|\| fallback` idiom | `out-of-scope-for-F3` | The fix lives in `studio.js` / frontend editors; **this flight touches no frontend** (backend lifespan + repo + test seam only). | **Not pulled in** — does not share F3's surface. Remains for the end-of-mission maintenance flight, per the F2 debrief's own routing. |
| `aiosqlite` teardown warning; `agents.md` `Field(ge/le)`+same-leg-migration convention doc | `out-of-scope-for-F3` | Neither shares F3's surface. | **Not pulled in** — end-of-mission maintenance flight. |

### Design-decision surface verification (planning pass)

- **F05 reaper precedent intact**: loop `_web_session_reap_loop` (`app.py:512`), `create_task`
  start (`app.py:113`, after the OAuth sweep), `_web_session_reaper_shutdown_drain` (`app.py:539`)
  wired into shutdown (`app.py:232–238`); lock-map hygiene pops `session_locks` (`app.py:501`).
  F3's loop/start/drain mirror this.
- **`updated_at` is consistently `now_iso()` ISO-8601-UTC**: `ChatSession.updated_at =
  Field(default_factory=now_iso)` (`models.py:13`); every insert passes `session.updated_at`
  (`repositories.py:983`); the active-session resolver orders lexically on it (`ORDER BY updated_at
  DESC`, `repositories.py:917/963`). Lexical cutoff comparison is sound (DD3).
- **F2 purge primitive present**: `delete_all_for_agent` (unconditional, count-returning) at
  `repositories.py:1039` — F3 adds the age-filtered, id-returning sibling beside it (DD2).
- **Connector sessions carry `agent_name` + `updated_at`**: `connectors/_session.py:181–195`
  (`ChatSession(agent_name=…, updated_at=current_iso, platform/connector_id/channel_id=…)`), so the
  age-filtered delete sweeps them and the active one survives via `update_last_inbound`'s bump
  (`repositories.py:1095`).

**Open for the user before execution**: none — the four planning decisions are resolved (DD1–DD5).
The Architect design review (Phase 5b) and crew walkthrough follow.

---

## Flight Director Notes

### 2026-06-06 — Flight start (agentic-workflow)
- **Phase file**: loaded `the_one/.flightops/agent-crews/leg-execution.md` — valid (Crew /
  Interaction Protocol / Prompts present). Developer = Sonnet, Reviewer = Haiku. Tests run via
  `docker exec the-one pytest …` (container `the-one` up + healthy). Git strategy: `branch`.
- **Total legs**: 4 — `app-metadata-store`, `purge-by-age-primitive`, `daily-purge-lifespan`,
  `verify-integration`. Starting at Leg 1.
- **State discrepancy remediated (F2 not merged)**: at flight start, PR #100 (F2 "Purge Now") was
  still **open** — `main` did not yet contain F2's `delete_all_for_agent`, which F3 builds on. The
  flight spec's prerequisite "Flight 2 … landed and merged to main" was optimistic (landed, not
  merged). Surfaced to the operator; operator chose **merge F2 first, then branch off main**. PR
  #100 was `CLEAN`/`MERGEABLE` with lint green → merged (fast-forward `de3a212..2ee44fb`, F2 branch
  deleted). Created `flight/03-daily-automatic-purge` off the updated `main`; confirmed
  `delete_all_for_agent` present. Prerequisite checkbox now accurate.
- **Flight status**: `ready` → `in-flight`.

### 2026-06-06 — Legs 1–3 implemented; single flight review (Phase 2d)
- **Legs 1–3 landed** (batched, no per-leg commit per agentic-workflow): L1 app-metadata-store (v31 + `app_metadata` + `AppMetadataRepository`, 6 tests); L2 purge-by-age-primitive (`delete_older_than`, 6 tests); L3 daily-purge-lifespan (new `retention.py` + lifespan loop/eviction + dual-gated `/_test/purge-sweep`, 14 tests). Each design-reviewed by a Developer agent — L1/L2 one cycle (low-severity citation/wording fixes), **L3 two cycles** (a Developer caught a HIGH issue: `AppMetadataRepository` was not imported in `app.py`, so `_purge_due` would `NameError` and be swallowed by the DD6 guard → daily purge silently dead in production while all tests passed green; fixed by moving the metadata read into `retention.py` `get_last_purge_at` + adding a `_purge_due` due-path test; second cycle approved).
- **Leg 3 deviation (import cycle)**: the implementer found a pre-existing `repositories → agent.config → … → repositories` import cycle that would crash startup if `retention.py` imported repos at module level; deferred the repo imports to function scope (kept `is_purge_due` pure). Verified cold `import the_one.interfaces.web.app` succeeds. Recorded in `retention.py` inline + Leg 3 flight-log entry.
- **Phase 2d review**: spawned a single Reviewer over ALL uncommitted changes (435 LOC across 6 modified + 3 new code files). **Model deviation (logged)**: ran the Reviewer at **Sonnet** rather than the crew-default Haiku — the diff touches the FastAPI lifespan + asyncio concurrency, the highest-risk surface, and the methodology only forbids Opus for the Reviewer. Reviewer signalled **[HANDOFF:confirmed]** — all acceptance criteria met, 335 tests pass, ruff clean, CancelledError/lock discipline/dual-gate verified. No blocking issues.
- **Leg 4 (verify-integration) setup**: pre-checked startup-sweep safety — all 47 dev sessions ≤12d old, all 5 agents at the default 30-day window → the restart catch-up sweep purges zero real data. Added `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1` to `docker-compose.yml` so the dual-gated test seam is reachable; restarting to load the new lifespan wiring + route before running the behavior gate.

## Leg Progress

### 2026-06-06 — Leg 1 `app-metadata-store` — `landed`

Atomic-migration leg: v31 schema migration + `app_metadata` kv table + `AppMetadataRepository` + tests, all together.

**Changes made:**
- `the_one/db/schema.py` — `CURRENT_VERSION` 30 → 31; new `if version < 31:` block creating `app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)` via `CREATE TABLE IF NOT EXISTS`, then `INSERT OR IGNORE` schema_version 31 + commit (mirrors v21/v30 new-table idiom; partial-apply safe). Not added to `SCHEMA_V1` — fresh DBs run every migration block in sequence.
- `the_one/db/repositories.py` — new `AppMetadataRepository(conn)` with async `get(key) -> str | None` (absent → `None`) and async `set(key, value)` upsert via `ON CONFLICT(key) DO UPDATE SET value = excluded.value` (mirrors `ToolConfigRepository`). Contract pinned for Leg 3: generic `get`/`set`, key string `"last_purge_at"`.
- `tests/test_db_migration.py` — `TestSchemaV31`: fresh-DB path reaches v31 with `app_metadata` present (table + column shape: key PK, value TEXT NOT NULL) and head pointer at `CURRENT_VERSION`; idempotent-on-rerun (v31 row appears exactly once).
- `tests/test_db_repositories.py` — added `AppMetadataRepository` to import tuple + `app_metadata_repo` fixture; `TestAppMetadataRepository`: absent-key → `None`, set-then-get roundtrip, set-twice upsert (latest wins, no PK violation), empty-string value distinct from absent.

**Test result:** `docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py -x --timeout 30` → **281 passed** (6 new). `CURRENT_VERSION` verified == 31.

**Lint/format:** `ruff check` clean on all 4 files; `ruff format` applied to `repositories.py` + `test_db_repositories.py` (line-reflow only) — `ruff format --check` now clean.

**Notes / anomalies:** None. Two pre-existing teardown warnings (`Event loop is closed` ResourceWarning from pytest-asyncio loop teardown) appear in the full run; unrelated to this leg's code. No consumer wired yet — table/repo are inert until Leg 3, as intended.

### 2026-06-06 — Leg 2 `purge-by-age-primitive` — `landed`

Age-filtered, id-returning sibling of F2's `delete_all_for_agent`, plus deterministic unit tests.

**Changes made:**
- `the_one/db/repositories.py` — new `ChatSessionRepository.delete_older_than(agent_name, cutoff) -> list[str]` immediately after `delete_all_for_agent` (before `purge_messages`). SELECT-id-snapshot-then-DELETE form on the serial connection (DD2 — no `RETURNING`); deletes rows where `agent_name = ? AND updated_at < ?` (lexical, DD3) and returns the captured ids; returns `[]` and issues no DELETE/commit when nothing matches. Docstring documents the lexical-comparison soundness, rename-safety, and the monotonic-`updated_at` superset guarantee (no false deletion).
- `tests/test_db_repositories.py` — 6 new tests in `TestChatSessionRepository` (M13 F03 L02 block): age filter + returned ids; connector sweep + recent/active survives (with the unit-proxy caveat comment); cross-agent isolation; empty/all-recent no-op; `updated_at == cutoff` boundary kept (strict `<`); rename-then-sweep composition. Explicit ISO-8601-UTC string seeds (`aged`/`recent`/`cutoff`) pin the lexical comparison. Constants are lowercase locals (ruff N806).

**Test result:** `docker exec the-one pytest tests/test_db_repositories.py -x --timeout 30` → **201 passed** (6 new).

**Lint/format:** `ruff check` clean on both changed files; `ruff format` applied to `test_db_repositories.py` (line-reflow only) — `ruff format --check` now clean on both.

**Notes / anomalies:** None. The leg artifact suggested uppercase `AGED`/`RECENT`/`CUTOFF` constants; switched to lowercase to satisfy the M12 ruff N806 CI gate. Primitive is inert until Leg 3 wires the sweep.

### 2026-06-06 — Leg 3 `daily-purge-lifespan` — `landed`

Core leg: pure sweep service + due-check, app-layer eviction wrapper, FastAPI-lifespan loop/start/shutdown-drain mirroring the F05 reaper, and a dual-gated test-trigger endpoint.

**Changes made:**
- `the_one/db/repositories.py` — `SQLiteAgentStore.list_retention_windows() -> list[tuple[str, int]]` (added after `list_agents`): `(name, chat_history_retention_days)` projection avoiding the full-config decode of `load()` per agent.
- `the_one/retention.py` — NEW pure module (imports the repos + `datetime`/`aiosqlite`, NOT `app.py`): `LAST_PURGE_KEY`, `PURGE_DUE_AFTER` (24h), `is_purge_due(last, now)`, `get_last_purge_at(conn)` (keeps the `AppMetadataRepository` read here so `app.py` needs no new repo import), `run_purge_sweep(conn) -> {deleted, ids, last_purge_at}` (per-agent cutoff → `delete_older_than` → advance global `last_purge_at`).
- `the_one/interfaces/web/app.py` — `import the_one.retention as retention`; `_chat_history_purge_task` global beside `_web_session_reaper_task`; `_get_purge_check_interval()` (default 3600, floored at 60); `_purge_due()` (via `retention.get_last_purge_at` — no `AppMetadataRepository` reference in app.py); `_run_purge_sweep_and_evict()` (three-phase eviction: pop under `_sessions_lock`, then `session_locks.pop` + `await agent.aclose()` outside it, reusing the existing `Agent` import); `_chat_history_purge_loop()` (guarded `_maybe_purge` catch-up on entry, then sleep+recheck); `_chat_history_purge_shutdown_drain()`; lifespan start just after the reaper start; shutdown drain beside the reaper drain.
- `the_one/interfaces/web/api.py` — `POST /_test/purge-sweep` dual-gated (`settings.dev_mode` AND `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`), gate-first 403, function-local import of `_run_purge_sweep_and_evict` from app; returns `{deleted, last_purge_at}`.
- `tests/test_retention.py` — NEW (9 tests): `is_purge_due` matrix (None/23h/25h/exactly-24h); `run_purge_sweep` per-agent windows (7 vs 90, each seeded a 30-day-aged session → 7's swept, 90's survives); connector aged swept + active kept; cross-agent isolation; `last_purge_at` advances + round-trips; empty-agents-table still advances timestamp.
- `tests/test_chat_history_purge.py` — NEW (5 tests): app-layer eviction (aged `_sessions` id evicted + `agent.aclose()` awaited, recent id kept); `_purge_due()` against a real seeded connection (True absent/aged, False recent — closes the prior-review coverage gap); one `_chat_history_purge_loop` catch-up iteration sweeps a due DB; endpoint gating 403 when dev_mode off and when env flag unset.

**Test result:** `docker exec the-one pytest tests/test_retention.py tests/test_chat_history_purge.py -x --timeout 30` → **14 passed**. `tests/test_web_session_reaper.py tests/test_mcp_pool.py tests/test_db_repositories.py -x` → **235 passed, 2 deselected** (lifespan drain-order spy stays green).

**Lint/format:** `ruff check` clean on all changed files; `ruff format` applied to `tests/test_chat_history_purge.py` (line-reflow only) — `ruff format --check` now clean on all six files.

**Deviation (import cycle):** the leg snippet for `retention.py` imports the repos at module level. That makes `retention.py` cold-import trigger a **pre-existing** latent cycle (`repositories → agent.config → agent → mcp → _pool → repositories`, which only resolves when `the_one.agent` is imported first — verified: `python -c "from the_one.db.repositories import ChatSessionRepository"` fails on `main` too). Since app.py's `import the_one.retention` is placed before its `from the_one.agent import Agent`, a module-level repo import in retention would have crashed production startup. **Fix:** deferred the repo imports into `get_last_purge_at` / `run_purge_sweep` (function-local); `is_purge_due` needs no repos and stays pure. `retention.py` is now cold-importable (sanity one-liner prints `True False True`) and `import the_one.interfaces.web.app` succeeds cold. Documented inline in `retention.py`.

**Notes / anomalies:** The two pre-existing `Event loop is closed` teardown warnings from the broader suite are unrelated to this leg. The startup catch-up's DB read is inside `_maybe_purge`'s `try/except Exception` (DD6), keeping the DB-mocked lifespan tests green.

### 2026-06-06 — Leg 4 `verify-integration` — `completed`

The flight's live acceptance gate + full-suite regression, run directly by the Flight Director.

**Behavior gate — `agent-history-auto-purge`: PASS 6/6** (run `2026-06-06-14-10-46`, batched-Witnessed; run log committed). Against the restarted container on `localhost:8484` with the dual-gated test endpoint: a forced sweep deleted TARGET (`Ollama testing`)'s two aged conversations — interactive **and** superseded-connector — while the recent interactive, the active-connector, and BYSTANDER (`Sonos Agent`)'s in-window conversation survived; `last_purge_at` advanced; a second sweep deleted nothing (idempotent). An **independent Validator confirmed every load-bearing assertion via its own fresh curls**, not just the Executor's report. Seeded sessions cleaned up post-run (both agents back to baseline).

**Full-suite regression:**
- **Unit** (`pytest -m "not browser and not live and not pixel"`): **2990 passed, 9 skipped, 540 deselected** in 298.85s (+26 vs F2's 2964 — the new L1–L3 tests). The 3 warnings are the pre-existing `aiosqlite` "Event loop is closed" teardown pattern (flagged for the end-of-mission maintenance flight), not failures.
- **Browser** (`pytest tests/browser -m browser`): **478 passed, 35 skipped, 12 deselected** in 563.18s — **identical to the F2 baseline (478 passed), zero regression** (expected: this flight makes no browser-facing changes).
- `ruff check` + `ruff format --check` clean across all changed files.

**Environment note (browser suite):** recreating the container to load the new lifespan wiring + route (`docker compose up -d --force-recreate`) wiped the runtime-installed Playwright chromium (the `/root/.cache/ms-playwright` cache does not persist across recreate — documented in the Makefile `_ensure-playwright` target). First browser run mass-errored (474 errors, chromium-not-installed → then chromium-crash-on-launch). Restored via `playwright install chromium` **and** `playwright install-deps chromium` (the deps were the second half — `make rebuild-browsers` does both); re-run then matched the F2 baseline exactly. Not a code issue.

**Scope addition (documentation):** added `THE_ONE_PURGE_CHECK_INTERVAL_SECONDS` (operational tunable) and `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT` (dev/test seam) to `.env.example`, mirroring the existing reaper-TTL and stub-connector entries (Phase 3 docs check). Added `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1` to `docker-compose.yml` so the dual-gated seam is reachable for the behavior gate.

---

## Decisions

_(runtime decisions not in the original plan — none yet)_

---

## Deviations

_(none yet)_

---

## Anomalies

_(none yet)_

---

## Session Notes

_(append chronological notes during execution)_
