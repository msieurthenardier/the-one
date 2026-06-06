# Flight: Daily Automatic Purge

**Status**: completed
**Mission**: [Chat History Retention](../../mission.md)

## Contributing to Criteria
- [x] A daily automated process removes every conversation whose last interaction predates
  the agent's retention window, while leaving conversations within the window intact.
- [x] Purge (both manual and automated) removes entire conversations — including
  connector-originated ones — and never affects another agent's conversations. *(F2 covered the
  **manual** half; this flight completes the **automated** half.)*

---

## Pre-Flight

### Objective

Add the daily automatic purge that enforces each agent's retention policy. A background
sweep — wired into the FastAPI lifespan, mirroring the M12 F05 web-session-reaper shape
(loop + `create_task` start + shutdown-drain) — runs on a **due-based catch-up** trigger:
it persists a single global `last_purge_at` and runs only when ≥24h have elapsed, so it is
not re-run on every restart but a window missed during downtime self-heals on next startup.
Each run enumerates agents, computes a per-agent cutoff from that agent's
`chat_history_retention_days`, and deletes every `chat_sessions` row (interactive **and**
connector-originated) whose last engaged interaction (`updated_at`) predates the cutoff —
leaving newer conversations, the active connector session, and other agents' conversations
intact. Because the sweep runs in-process, it also evicts the purged rows from the in-memory
`_sessions` registry (closing the DD2a gap the F2 debrief flagged for the automated case).
A dev-mode-gated test endpoint fires one sweep on demand so the behavior gate is deterministic.

### Open Questions

- [x] **`last_purge_at` storage — table, file, or settings store?** → Resolved: a **new
  `app_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)` kv table via a v31 migration**,
  with `last_purge_at` as a single row. No app-metadata / kv / settings table exists today
  (`grep` across `the_one/` returns none; `CURRENT_VERSION = 30` at `db/schema.py:15`). A
  DB table keeps the timestamp transactional with the sweep, matches the project's
  dedicated-SQLite-table convention, and is reusable for future global state — preferred over
  a disk file (separate volume-persistence + non-transactional). See DD1. **Requires a
  migration → atomic-leg discipline (Leg 1), mirroring F1's v30 same-leg pattern.**
- [x] **DD2a for the automated case — what about in-memory `_sessions` staleness?** →
  Resolved: **the sweep evicts matching `_sessions` entries**. Unlike F2's HTTP purge endpoint
  (which DD2a kept out of app-layer state to avoid a structural boundary crossing), the sweep
  already lives in the app layer (`app.py`, where the F05 reaper and `_sessions` live), so
  touching `_sessions` under `_sessions_lock` is a clean same-layer operation, not a crossing.
  Aged rows are idle by definition, so this rarely collides with an open tab. See DD4.
- [x] **How to fire the sweep deterministically for the behavior gate?** → Resolved: a
  **dev-mode-gated `POST /api/_test/purge-sweep` test endpoint**, gated on `settings.dev_mode`
  AND an env var (`THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`), mirroring the existing stub-connector
  test seam (`app.py:124`, `THE_ONE_REGISTER_STUB_CONNECTOR` + `dev_mode`). Production never
  sets the gate. See DD5.
- [x] **Timestamp comparison for the by-age cutoff — lexical or `datetime()`-normalized?** →
  Resolved: **lexical string comparison** (`updated_at < ?`) with the cutoff produced in the
  same `now_iso()` ISO-8601-UTC shape. `updated_at` is always written via `now_iso()`
  (`models.py:13` `default_factory=now_iso`; every `chat_sessions` insert passes
  `session.updated_at`, `repositories.py:983`), and the active-session resolver already relies
  on lexical ordering (`ORDER BY updated_at DESC`, `repositories.py:917/963`). Lexical is
  therefore correct and consistent. See DD3 for the legacy-format caveat.

No open questions remain for this flight.

### Design Decisions

> **Errata (post-flight, 2026-06-06 — see [flight-debrief.md](flight-debrief.md)):** two DDs below
> carry reasoning that was superseded during implementation and should be read with these corrections:
> - **DD2** says "SELECT-then-DELETE **in one transaction** … no concurrent writer can slip between
>   them." That atomicity framing is wrong — the bare `SELECT` runs outside any transaction. The
>   actual safety guarantee is **serial connection + monotonic-forward `updated_at`**: an interleaving
>   bump can only move a captured row *out* of the predicate, never an uncaptured row *in*, so the
>   returned ids are always a **superset** of rows deleted (no false deletion; at worst a benign
>   spurious `_sessions` eviction). The shipped docstring (`repositories.py` `delete_older_than`)
>   carries the corrected reasoning.
> - **DD5** says step 7 reads the "**unchanged** `last_purge_at`" observable. Wrong — the always-force
>   endpoint advances `last_purge_at` on every run (`run_purge_sweep` sets it unconditionally). The
>   behavior gate correctly asserts `deleted: 0` for idempotency instead. The due-respecting "skip if
>   <24h" path is covered by unit tests, not the live gate.

**DD1 — `last_purge_at` lives in a new `app_metadata` kv table (v31 migration, atomic leg)**:
Add `CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)` as
schema **v31** (bump `CURRENT_VERSION` 30 → 31, `db/schema.py:15`), plus an
`AppMetadataRepository` with narrow `get(key)` / `set(key, value)` (or the even narrower
`get_last_purge_at()` / `set_last_purge_at(iso)`).
- Rationale: no metadata/kv/settings store exists; a DB table is transactional with the sweep,
  persists across restarts in the same SQLite file the app already manages, and follows the
  project's table-per-concern convention. `last_purge_at` is **global** (one daily sweep covers
  all agents), so a single kv row — not a per-agent column — is the right shape.
- Atomic-leg requirement: the migration, the `CREATE TABLE`, the repository, and its tests land
  in **one leg** (Leg 1), mirroring F1's v30 same-leg pattern, so no half-applied schema state
  can be observed.
- Trade-off: one more migration in the chain. Accepted — the alternative (a disk file) trades the
  migration for non-transactional, volume-fragile state outside the DB.

**DD2 — New by-age repository primitive returning deleted ids**: Add
`ChatSessionRepository.delete_older_than(agent_name: str, cutoff: str) -> list[str]` near the
F2 `delete_all_for_agent` (`repositories.py:1039`). **Primary form: SELECT-id-snapshot then
DELETE in one transaction** — `SELECT id FROM chat_sessions WHERE agent_name = ? AND updated_at < ?`
to capture the ids, then `DELETE FROM chat_sessions WHERE agent_name = ? AND updated_at < ?`, then
`commit()`; return the captured ids.
- Rationale: the existing `delete_all_for_agent` deletes unconditionally and returns only a
  count — the sweep needs an **age predicate** and needs the **ids** (not just a count) to evict
  the matching in-memory `_sessions` entries (DD4). The `agent_name` filter gives cross-agent
  isolation for free, exactly as F2's purge does (criterion 5).
- Why SELECT-then-DELETE over `RETURNING`: `RETURNING` (SQLite ≥ 3.35) is **net-new to this repo**
  — there is zero existing usage, F2's sibling primitive deliberately used plain `DELETE` +
  `rowcount`, and the Docker base image's bundled `sqlite3` version is not pinned in this spec.
  SELECT-then-DELETE is one extra query inside the same transaction (no concurrent writer can slip
  between them — single-writer SQLite + the repo's serial connection), removes the build-sensitivity
  branch entirely, and is negligible at operator scale. (`RETURNING id` is an acceptable variation
  if a leg confirms the deployed build supports it, but is not the default.)
- Connector + active-session behavior: connector sessions are `chat_sessions` rows with
  `agent_name` set (`connectors/_session.py:181`), so they are swept by the same predicate; the
  **active** connector session survives because its `updated_at` is bumped on each engaged turn
  (`update_last_inbound`, `repositories.py:1095`) and is therefore recent / inside the window.
  Superseded channel rows age out independently — the mission's intended consequence.

**DD3 — Per-agent cutoff via lexical ISO-8601 comparison**: The sweep computes, per agent,
`cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()` and passes
it to `delete_older_than`. Comparison is lexical (`updated_at < cutoff`).
- Rationale: `updated_at` is always written in `now_iso()` ISO-8601-UTC form, and the active-
  session resolver already depends on lexical ordering of that column — so a lexical cutoff is
  both correct and consistent with established behavior. No `datetime()` normalization is
  introduced (it would diverge from the resolver's lexical ordering and adds SQLite-build
  sensitivity around `+00:00` offsets).
- Legacy-format caveat (accepted, low risk): a row written via the *column default*
  (`datetime('now')`, space-separated, no offset) would mis-compare lexically. In practice no such
  rows exist — the `ChatSession` model's `default_factory=now_iso` means every insert supplies an
  ISO value; the default only guards against a bare `INSERT` that omits the column, which the
  codebase never issues. Noted so a future reader doesn't re-derive it.
- Orphaned-session boundary (accepted): the sweep enumerates `agents` and purges by-age per
  enumerated agent, so sessions orphaned by a deleted agent (agent gone, rows survive since v5
  dropped the FK) are **not** auto-purged by this sweep. They remain reachable by F2's manual
  unconditional purge. Out of scope for the daily policy sweep (the mission frames retention as
  per-agent); documented, not silently dropped.

**DD4 — The sweep evicts matching `_sessions` (closes DD2a for the automated case)**: After the
per-agent deletes, the sweep pops every deleted id from the in-memory `_sessions` registry (and
from `session_locks`, mirroring the F05 reaper's lock-map hygiene at `app.py:501`) under
`_sessions_lock`.
- Rationale: the F2 debrief flagged that a background reaper deleting DB rows without evicting
  `_sessions` would leave a connected Chat tab showing stale sessions and risk an unpersisted turn
  on a purged row. F2 *accepted* that boundary because its purge ran in the HTTP/repo layer and
  reaching into `_sessions` would have been a structural boundary crossing. **This sweep already
  runs in `app.py`** alongside `_sessions` and the F05 reaper, so the eviction is a clean
  same-layer operation — the right place to close the gap.
- Mechanism: the sweep's DB phase (enumerate agents → `delete_older_than` per agent → collect
  ids → `set_last_purge_at`) is a pure service function returning the deleted ids; the app-layer
  loop wraps it and performs the `_sessions`/`session_locks` eviction. This keeps the DB logic
  unit-testable without `_sessions`, and the eviction testable against a seeded `_sessions`.
- Trade-off: an operator actively chatting in a tab whose session is past retention will have that
  tab's in-memory session evicted mid-view (next interaction starts a fresh session). This is the
  intended consequence of an automatic policy purge and matches the reaper's existing eviction
  semantics; an open tab on a *recently active* session is never affected (recent `updated_at` →
  inside window → not swept).

**DD5 — Dev-mode-gated test trigger endpoint**: Add `POST /api/_test/purge-sweep`, gated on
`settings.dev_mode` AND `os.environ.get("THE_ONE_PURGE_SWEEP_TEST_ENDPOINT") == "1"`. It runs one
sweep and returns `{"deleted": N, "last_purge_at": "<iso>"}`.
- Rationale: the production trigger is the 24h due-check, which a behavior test cannot wait on. A
  dev-mode-gated seam fires the real sweep on demand and lets the gate assert the result directly,
  with zero production exposure (both gates default off). This is the act-axis apparatus the gate
  needs; the observe-axis paths (`GET /api/chat/sessions?agent_name=…`) already exist.
- Precedent (stronger than the stub-connector seam at `app.py:124`): **`api.py` already hosts
  `dev_mode`-gated `/_test/` endpoints** (`api.py:3676`, `:3715`), so a `/_test/purge-sweep` route in
  `api.py` is the established home. The route calls an `app.py` `_run_purge_sweep()` wrapper — and
  `api.py` already function-locally imports app-layer symbols from `app.py` (`api.py:2166`), so the
  import direction is a proven pattern, not a new coupling. Keep the `settings.dev_mode` AND env-var
  dual gate so dev-mode-alone does not expose it.
- Force vs due-respecting: the endpoint runs the sweep unconditionally (forces) so the gate's
  primary path is deterministic; the due-check logic ("skip if `< 24h`") is asserted by Leg 3 unit
  tests, and the gate's step-7 "second sweep deletes nothing" reads the unchanged-`last_purge_at`
  observable. (If a `?force=false` form is trivial to add it may be, but it is not required.)
- Trade-off: a test-only route in the app. Kept honest by the dual gate and a `_test/` path prefix
  that signals its nature; never mounted in production config.

**DD6 — Lifespan wiring mirrors the F05 web-session reaper exactly**: A
`_chat_history_purge_loop()` is started with `asyncio.create_task` in the lifespan startup just
after the web-session reaper start (`app.py:113`), held in a module-level task reference, and
cancelled in a `_chat_history_purge_shutdown_drain()` wired into the shutdown branch alongside the
reaper drain (`app.py:232–238`). On startup the loop runs a due-check immediately (catch-up), then
sleeps a coarse interval (a fraction of 24h, env-overridable like the reaper's
`THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS`) and re-checks, purging only when `now - last_purge_at ≥ 24h`.
- Rationale: the mission mandates this shape and names the F05 reaper as the precedent
  (`app.py:512/113/539/232`). Reusing the proven loop+start+drain structure minimizes lifespan-
  ordering risk (the drain-order spy test at `app.py:248` locks the contract).
- **Startup-catch-up divergence from the reaper (must be deliberate):** the F05 reaper
  `await asyncio.sleep(interval)` *first* (`app.py:520–524`), so it touches no DB state at startup;
  this loop does a DB due-check **on entry**. That immediate due-check MUST sit **inside** the loop
  body's `try/except Exception` guard — not before it — so a startup DB failure is logged-and-
  continued, not propagated into lifespan. Consequence to flag for Leg 3: the lifespan tests that
  mock `get_connection` to a bare `MagicMock` (the drain-order spy `test_lifespan_shutdown_drain_order`,
  `tests/test_mcp_pool.py:528`) will now exercise this startup pass — the guard makes the mocked
  `execute(...)` raise-and-swallow harmless, but it must be guarded by design, not by accident. The
  drain-order whitelist in that test (`{pty, mcp, connector, oauth, db}`) ignores the new drain, so
  no order assertion breaks.
- Trade-off: another lifespan task. Negligible — it sleeps almost always and does one cheap
  due-check per wake.

### Prerequisites
- [x] Project initialized; Mission 13 active; Flight 1 (`chat_history_retention_days`, v30) and
  Flight 2 (manual purge, `delete_all_for_agent`) landed and merged to `main` (F2 = PR #100, merged
  at flight start 2026-06-06; see flight-log Flight Director Notes).
- [x] F05 web-session reaper present as the lifespan precedent (`app.py:512/113/539/232`,
  re-verified this planning pass).
- [x] `chat_sessions.updated_at` is written in `now_iso()` ISO-8601-UTC form on every insert
  (`models.py:13`, `repositories.py:983`); lexical comparison is sound (DD3).
- [x] the-one dev environment available (Docker + Makefile, Python 3.11+, SQLite); M12's `ruff
  check` + `ruff format --check` gate must pass on all new code.
- [x] **Behavior-test execution prerequisites** (this flight names `agent-history-auto-purge` as an
  acceptance gate). Per Pre-Flight Rigor, the apparatus-audited environment must hold at execution
  and is probed at planning:
  - **Apparatus-audited environment (both axes)**: a rebuilt instance on `http://localhost:8484`
    started in **dev mode** with `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`; at least two agents (target
    + bystander, `mock` provider); `curl` for seeding and observation. *Act path* — seed aged/recent
    interactive + connector sessions via `POST /api/chat/sessions` (accepts a caller-supplied
    `updated_at`, verified at `api.py` `create_chat_session` → `ChatSession.model_validate` →
    `repo.create`) and fire `POST /api/_test/purge-sweep`. *Observe path* — `GET
    /api/chat/sessions?agent_name=…` reads remaining rows; the trigger response reports `deleted` +
    `last_purge_at`. Both read paths exist today; no extra test-only read seam is introduced.
  - **Crew-execution mode**: the Executor + Validator run re-spawn-per-checkpoint by default;
    **batched-Witnessed is an accepted mode** for this project (operator decision, F2 debrief) and
    this spec has no mid-test branching. Live continuation (experimental `SendMessage`, requires
    `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) is an optimization, **not** a prerequisite — do not
    defer the gate for lack of it.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (code surfaces re-checked this pass; behavior-test execution
  prerequisites recorded)
- [x] Validation approach defined (unit + behavior test + browser/full suite)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Four legs. One migration (Leg 1). No frontend changes — this flight is backend lifespan + repo +
a test seam (so the F2 `extractApiError` carry-forward, which lives in `studio.js`, does **not**
share this flight's surface and stays for the end-of-mission maintenance flight).

**Leg 1 — `app-metadata-store` (atomic migration leg)**: Bump `CURRENT_VERSION` 30 → 31
(`db/schema.py:15`); add the v31 migration creating `app_metadata (key TEXT PRIMARY KEY, value
TEXT NOT NULL)` (idempotent `CREATE TABLE IF NOT EXISTS`, following the project's migration idiom);
add an `AppMetadataRepository` with `get(key) -> str | None` and `set(key, value)` (upsert via
`INSERT … ON CONFLICT(key) DO UPDATE`). Tests: migration brings a v30 DB to v31 with the table
present; `get` returns `None` for an absent key; `set`-then-`get` roundtrips; `set` twice upserts
(no duplicate-key error). `make rebuild`; touched unit suites; `ruff` clean.

**Leg 2 — `purge-by-age-primitive`**: Add `ChatSessionRepository.delete_older_than(agent_name,
cutoff) -> list[str]` near `delete_all_for_agent` (`repositories.py:1039`), capturing the deleted
ids (DD2). Unit tests (deterministic invariants, DD4-style coverage split): aged interactive row
deleted; recent interactive row kept; aged superseded connector row deleted; active connector row
(recent `updated_at`) kept; another agent's aged row untouched (cross-agent isolation); empty /
no-match returns `[]`; returned ids match exactly the rows removed; a rename-then-sweep composition
(rename an agent with aged + recent rows, sweep by the new name, assert correct rows gone) — the
F2 rename-safety property still holds for the age-filtered delete. `ruff` clean.

**Leg 3 — `daily-purge-lifespan`**: The core flight.
1. **Sweep service (pure, testable):** a function that reads all agents'
   `(name, chat_history_retention_days)` via a **dedicated projection** —
   `SELECT name, chat_history_retention_days FROM agents` (a small `SQLiteAgentStore` helper, or
   inline in the service). Prefer this over `list_agents()` (`repositories.py:77`, names only) +
   per-agent `load()` (`:114`), which would decode a full `AgentConfig` per agent. Then compute a
   per-agent `cutoff` (DD3), call `delete_older_than` per agent, accumulate deleted ids + count,
   then `set_last_purge_at(now_iso())`. Returns `{deleted, last_purge_at, ids}`. N+1 by-agent
   queries are fine at operator scale (the `list_by_connector` linear-scan precedent,
   `repositories.py:96`).
2. **Due-check:** `is_purge_due(last_purge_at, now) -> bool` → `last_purge_at is None or now -
   last_purge_at >= 24h`. Unit-tested in isolation (absent → due; 23h → not due; 25h → due).
3. **App-layer wrapper + lifespan loop (mirror F05 reaper):** `_run_purge_sweep()` calls the sweep
   service, then evicts the returned ids from `_sessions` + `session_locks` under `_sessions_lock`
   (DD4). **Copy the reaper's exact two-phase eviction shape** (`app.py:485–501`): collect/pop the
   matching entries from `_sessions` *under* `_sessions_lock`, then `session_locks.pop(sid, None)`
   *outside* the lock — the subtle discipline is that `session_locks` is popped after releasing
   `_sessions_lock` (`app.py:497–501`). `_chat_history_purge_loop()` runs a due-check immediately on
   entry (catch-up) **inside the loop body's `try/except Exception`** (DD6 — the startup-divergence
   guard), purges if due, then `while True: sleep(coarse interval); if due: purge`. Start via
   `create_task` at lifespan startup just after the reaper (`app.py:113`); hold a module-level task
   ref; add `_chat_history_purge_shutdown_drain()` (cancel + await,
   `contextlib.suppress(CancelledError)`) wired into the shutdown branch beside the reaper drain
   (`app.py:232–238`). Note for the leg: the DB-mocking lifespan tests (`tests/test_mcp_pool.py:528`)
   now run this loop's startup pass — verify they stay green with the guard in place.
4. **Dev-mode test endpoint (DD5):** `POST /api/_test/purge-sweep`, gated on `settings.dev_mode` +
   `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`, calls `_run_purge_sweep()` and returns `{deleted,
   last_purge_at}`. When the gate is off it 404s/disabled (route not registered or returns 404).
   Tests: sweep service deletes per-agent by window; `_sessions` eviction pops exactly the swept
   ids and leaves recent ones; due-check matrix; the endpoint is gated (off by default). `make
   rebuild`; unit suites; `ruff` clean.

**Leg 4 — `verify-integration`**: Author finalized + run the behavior gate
`agent-history-auto-purge` (seed aged + recent interactive and connector sessions across a target
+ bystander agent via `POST /api/chat/sessions` with backdated `updated_at`; fire `POST
/api/_test/purge-sweep`; observe aged rows gone, recent + active-connector rows kept, bystander
untouched, `last_purge_at` advanced; second sweep deletes nothing). Run the full unit suite +
browser suite for regression; `ruff check` + `ruff format --check` clean. Capture the behavior-test
run log and suite metrics for the debrief.

### Checkpoints
- [x] v31 migration creates `app_metadata`; `AppMetadataRepository` get/set/upsert roundtrips;
  a v30 DB migrates clean.
- [x] `delete_older_than` deletes aged interactive + superseded-connector rows, keeps recent +
  active-connector rows, isolates other agents, returns the deleted ids; rename-then-sweep holds.
- [x] Sweep service computes per-agent cutoffs and advances `last_purge_at`; due-check skips
  `< 24h` and runs `≥ 24h`; `_sessions` eviction pops exactly the swept ids.
- [x] Purge loop starts in lifespan (catch-up on startup) and drains cleanly on shutdown (no
  lingering task; drain-order contract intact).
- [x] Dev-mode `POST /api/_test/purge-sweep` fires one sweep and is gated off in production config.
- [x] Behavior test `agent-history-auto-purge` passes; full unit + browser suites green; `ruff` clean.

### Adaptation Criteria

**Divert if**:
- The F05 reaper lifespan structure (`app.py:113/232/512/539`) has been restructured such that the
  start/drain insertion points no longer hold — re-locate before wiring.
- `chat_sessions.updated_at` is found to be written in a non-`now_iso()` shape anywhere (would
  break lexical comparison) — re-verify DD3 before relying on it.
- `RETURNING` is unsupported by the deployed SQLite build — fall back to the SELECT-then-DELETE
  form within one transaction (DD2 already specifies this fallback; not a true divert).

**Acceptable variations**:
- Exact metadata key name (`last_purge_at` vs `chat_history.last_purge_at`) and whether the repo
  exposes generic `get/set` or purpose-named `get_last_purge_at/set_last_purge_at`.
- The coarse loop interval and its env-var name (cosmetic; mirror the reaper's idiom).
- The test endpoint's exact path (`/api/_test/purge-sweep` vs sibling) and whether it accepts a
  `force` flag — keep it dual-gated and dev-only.

### Legs

> **Note:** Tentative; legs are created one at a time as the flight progresses.

- [x] `app-metadata-store` - v31 migration + `app_metadata` kv table + `AppMetadataRepository`
  (atomic-leg: schema + repo + tests together).
- [x] `purge-by-age-primitive` - `ChatSessionRepository.delete_older_than(agent_name, cutoff) ->
  list[str]` + unit tests (age filter, connector sweep, active-session survival, cross-agent
  isolation, returned ids, rename-then-sweep).
- [x] `daily-purge-lifespan` - due-based catch-up sweep service + per-agent cutoff + `_sessions`
  eviction + lifespan loop/start/shutdown-drain (mirror F05) + dev-mode `POST /api/_test/purge-sweep`
  trigger + unit tests.
- [x] `verify-integration` - run the `agent-history-auto-purge` behavior gate + full unit/browser
  suites + `ruff`; capture run log and metrics.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [x] v31 migration verified against the live DB (table present, `last_purge_at` row written after
  a sweep)
- [x] Automated sweep verified against the live DB: aged conversations (interactive + connector)
  gone, recent + active-connector + other-agent conversations intact
- [x] `make test` green (unit + browser); `ruff check` + `ruff format --check` clean
- [x] Behavior test `agent-history-auto-purge` passes
- [x] Mission criteria 4 (daily automated process) and the automated half of criterion 5
  (connector + cross-agent isolation) checked off in `mission.md`
- [x] Mission Known Issue "Post-purge WebSocket `session_list` staleness (DD2a consequence)"
  re-assessed: this flight evicts `_sessions` on the automated sweep (DD4); note in the debrief
  whether the manual-purge half of that known issue remains open (F2's HTTP endpoint still does not
  evict) or is now considered acceptable
- [x] Code + artifacts committed together

### Verification

- **Unit**: `app_metadata` migration + repo roundtrip (Leg 1); `delete_older_than` invariants
  (Leg 2); sweep service per-agent cutoff, due-check matrix, `_sessions` eviction, endpoint gating
  (Leg 3) — `make test-unit`.
- **Behavior test (gate)**: `/behavior-test agent-history-auto-purge` — seed aged + recent
  interactive and connector sessions across two agents, fire the dev-mode sweep trigger, observe
  the aged conversations gone while recent / active-connector / other-agent conversations remain
  and `last_purge_at` advances.
  Spec: [tests/behavior/agent-history-auto-purge.md](../../../../../tests/behavior/agent-history-auto-purge.md).
- **Restart catch-up** (Variant A, optional but recommended): set `last_purge_at` ~25h in the past,
  restart, assert a sweep ran during lifespan startup.
- **Full suite**: unit + browser via `make test` for regression; `ruff` gate clean.
