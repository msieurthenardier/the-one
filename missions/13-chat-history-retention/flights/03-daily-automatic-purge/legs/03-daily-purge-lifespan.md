# Leg: daily-purge-lifespan

**Status**: completed
**Flight**: [Daily Automatic Purge](../flight.md)

## Objective

Wire the daily automatic purge into the app: a pure, testable sweep service (enumerate agents → per-agent cutoff → `delete_older_than` → advance global `last_purge_at`) plus a due-based catch-up check, an app-layer wrapper that evicts swept ids from the in-memory `_sessions` registry, a FastAPI-lifespan loop/start/shutdown-drain mirroring the F05 web-session reaper, and a dev-mode-gated `POST /api/_test/purge-sweep` trigger so the behavior gate can fire one sweep on demand.

## Context

- This is the core leg. It consumes Leg 1 (`AppMetadataRepository`, the `app_metadata` table) and Leg 2 (`ChatSessionRepository.delete_older_than`).
- **DD3/DD6 (flight)**: due-based catch-up — persist a global `last_purge_at`; on startup and each cadence wake, purge only if `≥24h` elapsed; update the timestamp after. Loop/start/drain mirror the F05 reaper (`app.py:512`/`:113`/`:539`/`:236`).
- **DD4 (flight)**: the sweep runs in the app layer, so after the per-agent deletes it evicts the swept ids from `_sessions` + `session_locks` under `_sessions_lock` — closing the DD2a staleness gap for the automated case. Copy the reaper's exact two-phase shape (`app.py:485–501`): collect/pop under `_sessions_lock`, then `session_locks.pop(sid, None)` **outside** the lock.
- **DD5 (flight)**: a `POST /api/_test/purge-sweep` route, dual-gated (`settings.dev_mode` AND `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT == "1"`), forces one sweep and returns `{deleted, last_purge_at}`. Mirrors the existing `/_test/` endpoints (`api.py:3676`, `:3715`) which gate FIRST with a 403; the route calls an app-layer wrapper imported function-locally from `app.py` (the established api→app import direction, `api.py:2166`).
- **Separation (DD4)**: the **pure DB logic** (enumerate, cutoff, delete, set timestamp — returning the swept ids) lives in a new `the_one/retention.py` module so it is unit-testable without importing `app.py` (which pulls in FastAPI + `_sessions`). The **app-layer wrapper** in `app.py` calls it and does the `_sessions` eviction. This keeps each side independently testable.

## Inputs

What exists before this leg (post-Leg-1/2 working tree, uncommitted):
- `the_one/db/repositories.py`: `AppMetadataRepository` (`:909`, async `get`/`set`); `ChatSessionRepository.delete_older_than(agent_name, cutoff) -> list[str]` (after `delete_all_for_agent` `:1070`); `SQLiteAgentStore` (`:71`, `list_agents` `:77`, `load` `:114`).
- `the_one/interfaces/web/app.py`: lifespan (`:85`), reaper start at `:113` (after the OAuth sweep), shutdown drain wired at `:236`; module globals `_sessions` (`:363`), `_sessions_lock` (`:369`), `_web_session_reaper_task` (`:374`), `session_locks` (imported from `the_one.sessions`, `:72`); the reaper **full three-phase** eviction template (`:485–509` — pop under lock, then `session_locks.pop` AND `await agent.aclose()` outside the lock); the TTL env-reader idiom `_get_web_session_idle_ttl` (`:443`); `_chat_repo()` (`:603`); `get_connection` (`:54`); the `from the_one.db.repositories import (…)` block (`:57–62`) imports **only** `ChatSessionRepository, LLMProviderRepository, PendingApprovalRepository, SQLiteAgentStore` — **NOT** `AppMetadataRepository` (this is why the metadata read is kept in `retention.py`, step 3 below, so `app.py` needs no new repo import); `datetime, timezone` imported (`:12`); `logger` (`:77`); `asyncio`/`contextlib`/`os` imported.
- `the_one/interfaces/web/api.py`: `/_test/` dev-mode-gated endpoints (`:3676`, `:3715`) — gate FIRST, `if not settings.dev_mode: raise HTTPException(403, …)`; `os` (`:9`), `settings`, `Request`, `HTTPException` in scope; api→app function-local import precedent (`:2166`, `from the_one.interfaces.web.app import _send_to_session, _sessions`).
- `the_one/config.py`: `dev_mode: bool = False` (`:19`).
- `tests/test_web_session_reaper.py`: app-layer reaper test harness — `monkeypatch.setattr(app_mod, "_sessions", {})` (`:75`), seed `app_mod._sessions[sid] = session`, call the once-fn, assert eviction (`:94–109`). Mirror for the eviction test.
- `tests/test_mcp_pool.py:528`: the lifespan drain-order spy (`test_lifespan_shutdown_drain_order`) mocks `get_connection` to a bare `MagicMock` — the new startup catch-up DB read MUST be inside a `try/except Exception` so this test stays green (DD6).

## Outputs

- `the_one/retention.py` (new): `LAST_PURGE_KEY`, `PURGE_DUE_AFTER`, `is_purge_due(...)`, `run_purge_sweep(conn) -> dict` (pure; returns `{deleted, ids, last_purge_at}`); a `SQLiteAgentStore` retention-window projection helper (added to `repositories.py`).
- `the_one/interfaces/web/app.py`: `_chat_history_purge_task` global; `_get_purge_check_interval()`; `_purge_due()`; `_run_purge_sweep_and_evict()`; `_chat_history_purge_loop()`; `_chat_history_purge_shutdown_drain()`; lifespan start + shutdown-drain wiring.
- `the_one/interfaces/web/api.py`: `POST /_test/purge-sweep` (dual-gated).
- Tests: `tests/test_retention.py` (new); app-layer eviction + endpoint-gating tests; the lifespan drain-order test confirmed still green.

## Acceptance Criteria

- [ ] `is_purge_due(last_purge_at, now)` returns `True` when `last_purge_at is None` OR `now - last_purge_at >= 24h`, else `False` (unit-tested: None→due; 23h→not due; 25h→due; exactly-24h→due).
- [ ] `run_purge_sweep(conn)` enumerates all agents, computes a **per-agent** cutoff from each agent's `chat_history_retention_days`, deletes that agent's sessions older than its cutoff, advances `last_purge_at` to now (ISO), and returns `{deleted: int, ids: list[str], last_purge_at: str}`. Unit-tested: two agents with **different** retention windows each purge by their own window; aged interactive + aged connector rows swept; recent + active-connector + other-agent rows kept; `last_purge_at` advances; returned ids match removed rows.
- [ ] `_run_purge_sweep_and_evict()` calls the sweep then removes every returned id from `_sessions` and `session_locks` and awaits `agent.aclose()` for each evicted session (three-phase, reaper shape `app.py:485–509`). Unit-tested: a seeded `_sessions` entry whose row is swept is evicted and its `agent.aclose()` awaited; an entry whose row survives is left.
- [ ] `_purge_due()` (which reads the DB) is exercised directly by a test against a real seeded connection (True when absent/aged, False when recent) — so a regression in that path is caught rather than swallowed by the DD6 guard.
- [ ] The purge loop is started via `asyncio.create_task` in the lifespan startup (just after the reaper start) and cancelled+drained on shutdown (a `_chat_history_purge_shutdown_drain` wired beside the reaper drain). The loop does an **immediate** due-check on entry (catch-up), then sleeps a coarse interval and re-checks; the startup due-check is inside a `try/except Exception` (DD6).
- [ ] `POST /api/_test/purge-sweep` returns `{deleted, last_purge_at}` when dual-gated ON (`dev_mode` AND `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`), and returns **403** otherwise. Unit-tested: 403 when the gate is off.
- [ ] `tests/test_mcp_pool.py::...drain_order` (and the broader lifespan tests) stay green — the startup catch-up does not break the DB-mocked lifespan path.
- [ ] `ruff check` + `ruff format --check` clean on all changed/new files.
- [ ] All touched suites pass.

## Verification Steps

- `docker exec the-one pytest tests/test_retention.py tests/test_web_session_reaper.py tests/test_mcp_pool.py -x --timeout 30` → green (plus any app-test file the eviction/endpoint tests land in).
- `docker exec the-one pytest tests/test_db_api.py -x --timeout 30` (or wherever the endpoint-gating test lands) → green.
- `docker exec the-one ruff check the_one/retention.py the_one/interfaces/web/app.py the_one/interfaces/web/api.py the_one/db/repositories.py tests/test_retention.py` + `ruff format --check` → clean.
- Sanity: `docker exec the-one python -c "from the_one.retention import is_purge_due; from datetime import datetime, timezone, timedelta; now=datetime(2026,1,2,tzinfo=timezone.utc); print(is_purge_due(None, now), is_purge_due((now-timedelta(hours=23)).isoformat(), now), is_purge_due((now-timedelta(hours=25)).isoformat(), now))"` → `True False True`.

## Implementation Guidance

1. **Agent retention-window projection** (`the_one/db/repositories.py`, `SQLiteAgentStore`)
   - Add a helper returning `(name, retention_days)` pairs without decoding full configs:
     ```python
     async def list_retention_windows(self) -> list[tuple[str, int]]:
         """(name, chat_history_retention_days) for every agent — the
         projection the daily purge sweep enumerates (M13 F03). Avoids the
         full-config decode of load() per agent."""
         async with self.conn.execute(
             "SELECT name, chat_history_retention_days FROM agents ORDER BY name"
         ) as cur:
             return [(row[0], row[1]) for row in await cur.fetchall()]
     ```

2. **New module `the_one/retention.py`** (pure — imports only `datetime`, the repos, `now`-helpers; NOT `app.py`)
   ```python
   from __future__ import annotations
   from datetime import datetime, timedelta, timezone
   import aiosqlite
   from the_one.db.repositories import (
       AppMetadataRepository, ChatSessionRepository, SQLiteAgentStore,
   )

   LAST_PURGE_KEY = "last_purge_at"
   PURGE_DUE_AFTER = timedelta(hours=24)

   def is_purge_due(last_purge_at: str | None, now: datetime) -> bool:
       """Due if never purged, or ≥24h since the last purge."""
       if last_purge_at is None:
           return True
       return now - datetime.fromisoformat(last_purge_at) >= PURGE_DUE_AFTER

   async def get_last_purge_at(conn: aiosqlite.Connection) -> str | None:
       """Read the global last_purge_at (or None if never set). Kept HERE
       (not in app.py) so app.py needs no AppMetadataRepository import —
       app.py's repo import block does not include it (see Inputs)."""
       return await AppMetadataRepository(conn).get(LAST_PURGE_KEY)

   async def run_purge_sweep(conn: aiosqlite.Connection) -> dict:
       """Per-agent age-based purge over all agents. Pure DB logic — does
       NOT touch app-layer _sessions (the app wrapper does). Returns
       {deleted, ids, last_purge_at}."""
       agent_store = SQLiteAgentStore(conn)
       chat_repo = ChatSessionRepository(conn)
       meta = AppMetadataRepository(conn)
       now = datetime.now(timezone.utc)
       all_ids: list[str] = []
       for name, days in await agent_store.list_retention_windows():
           cutoff = (now - timedelta(days=days)).isoformat()
           all_ids.extend(await chat_repo.delete_older_than(name, cutoff))
       last_purge_at = now.isoformat()
       await meta.set(LAST_PURGE_KEY, last_purge_at)
       return {"deleted": len(all_ids), "ids": all_ids, "last_purge_at": last_purge_at}
   ```
   - Note the cutoff uses `(now - timedelta(days=days)).isoformat()` — same `now_iso()` ISO-8601-UTC shape `delete_older_than` compares against lexically (DD3).

3. **App-layer wiring** (`the_one/interfaces/web/app.py`)
   - Add `import the_one.retention as retention` near the other imports.
   - Global near `_web_session_reaper_task` (`:374`): `_chat_history_purge_task: asyncio.Task[None] | None = None`.
   - Env-reader for the loop wake interval, mirroring `_get_web_session_idle_ttl` (`:443`) — **with a floor** (the reaper floors at 30s; here floor at 60s so a `…=0` env value can't busy-loop the DB):
     ```python
     def _get_purge_check_interval() -> int:
         """THE_ONE_PURGE_CHECK_INTERVAL_SECONDS at call time; default 3600
         (coarse — the due-check gates the actual 24h purge). Floored at 60s
         so a 0/negative value can't tight-loop."""
         raw = os.environ.get("THE_ONE_PURGE_CHECK_INTERVAL_SECONDS")
         if raw is None:
             return 3600
         try:
             return max(60, int(raw))
         except ValueError:
             logger.warning("THE_ONE_PURGE_CHECK_INTERVAL_SECONDS=%r not an int; using 3600", raw)
             return 3600
     ```
   - The due-check + wrapper + eviction. **`_purge_due` calls `retention.get_last_purge_at` — app.py does NOT reference `AppMetadataRepository`** (high-issue fix). Eviction mirrors the reaper's **full three-phase** shape (`app.py:485–509`): capture the popped sessions under the lock, then pop `session_locks` AND `await agent.aclose()` outside the lock, so warm Agent resources (MCP subprocesses, connector sockets) are released, not leaked:
     ```python
     async def _purge_due() -> bool:
         conn = await get_connection()
         last = await retention.get_last_purge_at(conn)
         return retention.is_purge_due(last, datetime.now(timezone.utc))

     async def _run_purge_sweep_and_evict() -> dict:
         """Run the DB sweep, then evict swept ids from the in-memory
         _sessions registry (DD4). Three-phase, reaper shape (app.py:485–509):
         pop under _sessions_lock; close + lock-map-pop outside it."""
         conn = await get_connection()
         result = await retention.run_purge_sweep(conn)
         ids = result["ids"]
         if not ids:
             return result
         evicted: list[tuple[str, Agent]] = []
         async with _sessions_lock:
             for sid in ids:
                 sess = _sessions.pop(sid, None)
                 if sess is not None:
                     evicted.append((sid, sess.agent))
         for sid, agent in evicted:               # outside the lock (reaper hygiene)
             session_locks.pop(sid, None)
             try:
                 await agent.aclose()
             except Exception:
                 logger.exception("agent.aclose() raised during purge eviction: sid=%r", sid)
         logger.info("daily purge swept %d session(s); evicted %d from _sessions",
                     len(ids), len(evicted))
         return result
     ```
     (`Agent` is already imported in app.py — it's used in the reaper's `evicted: list[tuple[str, Agent]]` annotation at `:484`. Reuse it.)
   - The loop (mirror `_web_session_reap_loop` `:512`, but due-check on entry **inside the guard**, DD6):
     ```python
     async def _chat_history_purge_loop() -> None:
         """Due-based daily purge. Catch-up on entry, then sleep+recheck.
         M13 F03 — mirrors the F05 web-session reaper loop/start/drain."""
         async def _maybe_purge() -> None:
             try:
                 if await _purge_due():
                     await _run_purge_sweep_and_evict()
             except Exception:
                 logger.exception("daily purge pass raised; continuing")
         await _maybe_purge()                      # startup catch-up (guarded)
         while True:
             await asyncio.sleep(_get_purge_check_interval())
             await _maybe_purge()
     ```
   - Lifespan **start** just after the reaper start (`:113`):
     ```python
     global _chat_history_purge_task
     _chat_history_purge_task = asyncio.create_task(_chat_history_purge_loop())
     ```
   - Shutdown drain fn + wiring beside the reaper drain (`:236`):
     ```python
     async def _chat_history_purge_shutdown_drain() -> None:
         global _chat_history_purge_task
         task = _chat_history_purge_task
         if task is not None and not task.done():
             task.cancel()
             with contextlib.suppress(asyncio.CancelledError):
                 await task
         _chat_history_purge_task = None
     ```
     and in the shutdown branch:
     ```python
     try:
         await _chat_history_purge_shutdown_drain()
     except Exception:
         logger.exception("daily purge shutdown failed")
     ```

4. **Dev-mode test endpoint** (`the_one/interfaces/web/api.py`, near the other `/_test/` routes ~:3676)
   ```python
   @router.post("/_test/purge-sweep")
   async def trigger_purge_sweep() -> dict[str, Any]:
       """M13 F03 — dev-mode-gated test seam. Fires ONE daily-purge sweep
       on demand (production fires on the 24h due-check, which a behavior
       test can't wait on). Dual-gated: dev_mode AND the env flag.
       Gating mirrors the sibling /_test/ seams (403 when off)."""
       if not settings.dev_mode or os.environ.get("THE_ONE_PURGE_SWEEP_TEST_ENDPOINT") != "1":
           raise HTTPException(
               status_code=403,
               detail="test-seam endpoint requires dev_mode + THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1",
           )
       from the_one.interfaces.web.app import _run_purge_sweep_and_evict
       result = await _run_purge_sweep_and_evict()
       return {"deleted": result["deleted"], "last_purge_at": result["last_purge_at"]}
   ```

5. **Tests**
   - `tests/test_retention.py` (new): build a fresh `ensure_schema`'d connection (replicate the `conn` fixture from `tests/test_db_repositories.py:22–35`, or import a shared one). Tests:
     - `is_purge_due` matrix (None→True; 23h→False; 25h→True; exactly 24h→True).
     - `run_purge_sweep` per-agent windows: agent `a` retention 7, agent `b` retention 90; seed each a 30-day-aged session → `a`'s is swept, `b`'s survives; `last_purge_at` is set; returned ids correct.
     - connector aged swept + active (recent) kept; cross-agent isolation; deleted count == len(ids).
   - App-layer eviction (mirror `tests/test_web_session_reaper.py` harness): `monkeypatch.setattr(app_mod, "_sessions", {})`; seed an aged chat row whose id you also place in `_sessions`; call `await app_mod._run_purge_sweep_and_evict()`; assert that id is gone from `_sessions` and a recent-row id placed in `_sessions` remains. Assert the evicted session's `agent.aclose()` was awaited (mirror the reaper test's `agent.aclose.assert_awaited_once()` at `test_web_session_reaper.py:109`). (Needs a real seeded conn via the app's `get_connection`; follow how the reaper tests obtain state, and seed chat rows through `ChatSessionRepository`.)
   - **Due-path coverage (closes the high-issue gap):** a test that drives `app_mod._purge_due()` against a real seeded connection — assert it returns `True` when `last_purge_at` is absent / aged ≥24h and `False` when recently set — AND a test that drives the loop's `_maybe_purge` (or one full `_chat_history_purge_loop` iteration with a tiny interval, then cancel) and asserts a due DB actually gets swept. Without this, a `NameError`/typo in `_purge_due` would be swallowed by the DD6 guard and never caught (this is exactly the failure mode that the missing-import bug would have caused).
   - Endpoint gating: a test asserting `POST /_test/purge-sweep` → 403 when `dev_mode` off or the env flag unset. Use the app-test client pattern used by existing api tests (find a sibling `/_test/` or api test for the TestClient setup).
   - Run `tests/test_mcp_pool.py` to confirm the lifespan drain-order spy stays green.

## Edge Cases

- **DB-mocked lifespan tests (DD6)**: the immediate startup due-check reads the DB; it MUST be inside `try/except Exception` so `test_lifespan_shutdown_drain_order` (mocks `get_connection`) doesn't raise out of the loop. The `_maybe_purge` helper's guard covers this.
- **CancelledError on shutdown**: the loop must let `CancelledError` (from `asyncio.sleep`) propagate — only `Exception` is caught inside `_maybe_purge`, never `BaseException`. The drain cancels + `contextlib.suppress(CancelledError)` awaits.
- **Empty agents table**: `list_retention_windows()` → `[]`; `run_purge_sweep` deletes nothing but STILL advances `last_purge_at` (a due sweep ran; record it so it isn't re-run every wake). The behavior test's "second sweep deletes nothing" relies on this.
- **No agents but sweep due**: same as above — `deleted: 0`, `last_purge_at` advanced.
- **Orphaned sessions (agent deleted)**: not enumerated → not auto-purged (accepted boundary, flight DD3). Do not special-case.
- **`datetime.fromisoformat` on the stored value**: `last_purge_at` is always written via `.isoformat()` here, so `fromisoformat` round-trips it. Don't store a non-ISO value under that key.
- **Concurrent reaper + purge eviction**: both take `_sessions_lock` for their pop phase, so they serialize; `session_locks.pop` outside the lock is idempotent (`pop(sid, None)`).
- **Purge does NOT skip `subscribers_for`/`is_session_processing` (deliberate divergence from the reaper)**: the reaper skips open-tab and mid-turn sessions; the purge is a **policy** eviction (DD4 accepts mid-view eviction), so it evicts unconditionally. In practice this is near-impossible to hit — a session past its retention window is idle by definition (its `updated_at` is ≥ the window old), so it has almost always already been idle-reaped. The only theoretical cost: popping `session_locks[sid]` while a turn holds the lock means a *new* concurrent turn on that sid would get a fresh lock object (the in-flight turn keeps its own reference), briefly losing mutual exclusion on a row that's being deleted anyway. Acceptable; noted so it isn't mistaken for an oversight.

## Files Affected
- `the_one/retention.py` — NEW: pure sweep service + due-check.
- `the_one/db/repositories.py` — `SQLiteAgentStore.list_retention_windows()`.
- `the_one/interfaces/web/app.py` — purge loop/wrapper/eviction/drain + lifespan start & shutdown wiring + interval reader + task global.
- `the_one/interfaces/web/api.py` — `POST /_test/purge-sweep` (dual-gated).
- `tests/test_retention.py` — NEW: due-check + sweep-service tests.
- app-layer eviction test + endpoint-gating test (new file or appended to an existing app/api test module).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (incl. the lifespan drain-order spy still green)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (Flight Director handles `completed`/commit at flight end)
- [ ] Check off this leg in flight.md — *(deferred: Flight Director at flight end)*
- [ ] Commit — *(deferred: single flight-end commit; do NOT commit here)*
