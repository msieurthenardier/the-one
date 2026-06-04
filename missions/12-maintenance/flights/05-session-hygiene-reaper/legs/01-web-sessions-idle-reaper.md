# Leg: web-sessions-idle-reaper

**Status**: completed
**Flight**: [Long-Lived Session Hygiene](../flight.md)

## Objective
Add an idle-TTL reaper to the web `_sessions` cache (`app.py:346`) — modeled on the PTY `_session_registry` reaper — so idle, **zero-subscriber** sessions are evicted and their `Agent`'s LLM HTTP client released, bounding memory growth in a long-lived process (resolves finding P4). Includes adding the `Agent.aclose()` teardown method this requires (it does not exist yet).

## Context
- Maintenance report 2026-06-04, finding **P4** (Action Required): the web `_sessions: dict[str, Session]` (`app.py:340`) has no TTL, size cap, or reaper. Entries are added on create (`:502`) and restore (`:646`) and removed only on degraded-restore (`pop` at `544/571/580/589`) or explicit user delete (`del` at `1572`). Each entry pins a live `Agent` (provider client, MCP tool handles, full message history). Single-user does NOT bound this — one operator accumulates sessions over a long-running process.
- The PTY `tools/_session_registry.py` already implements a full idle-reaper + TTL + shutdown-drain (`_sessions` at `:73`) — a copyable pattern. The `_session_registry` race finding (P6) is a *separate* dict and is out of scope here.
- **Design-review findings (load-bearing — applied):**
  - **No `Agent` teardown method exists.** `the_one/agent/core.py` `Agent` has no `close`/`aclose`/`cleanup`. The leg must ADD `async def aclose()` to `Agent` (idempotent, `_closed` guard) that calls a new `LLMProvider.aclose()`; the providers with persistent `httpx` clients (`AnthropicProvider`/`OpenAIProvider`/`OllamaProvider`) implement it as `await self.client.aclose()`. **MCP tool handles are NOT per-Agent** — they're owned by `the_one/mcp/_pool.py` (keyed `(agent_name, source_id)`) with its own TTL reaper; `Agent.aclose()` does NOT touch MCP. So "teardown" here = close the LLM provider's HTTP client only.
  - **Subscriber registry** lives in `the_one/sessions/_broadcast.py` (`_subscribers: defaultdict[str, set]`, keyed by `session.id`); the reaper's guard is `not subscribers_for(session_id)`.
  - **`Session` has no `last_activity`** — must be added (a `float` via `time.monotonic()`), touched at create/restore/message/`chat_reset`/WS-disconnect.
  - **`_sessions` has no lock today** — the reaper introduces an async boundary (`aclose()`), so all `_sessions` read-modify-write sites must serialize through a shared `asyncio.Lock` (snapshot-under-lock, `aclose()` outside the lock — the PTY two-phase pattern).
  - **In-flight guard**: gate reaping on `not is_session_processing(session_id)` too — a WS can disconnect (subscriber removed) while a long tool call runs up to 120s; the subscriber guard alone wouldn't protect it.

## Inputs
- `the_one/interfaces/web/app.py:340` (the web `_sessions` dict) and its mutation sites (`:502, 544, 571, 580, 589, 646, 1572`).
- `the_one/tools/_session_registry.py` (the reaper pattern to adapt) — idle reaper, TTL, shutdown drain.
- The `chat_sessions` DB table + restore path (`app.py:646`) as the durable backing store.

## Outputs
- An idle-TTL reaper for web `_sessions` with clean `Agent` teardown on eviction.
- A configurable TTL env var (documented; coordinate with Flight 06 DOC4).

## Acceptance Criteria
- [x] Web `_sessions` entries idle beyond a configurable TTL **AND with zero live WS subscribers** are evicted by a background reaper
- [x] **A session with ≥1 live WS subscriber is NEVER reaped** — operator hard requirement (works without refresh); verified by test (b)
- [x] Eviction tears down the `Agent` via `Agent.aclose()` (closes the LLM provider HTTP client; MCP is pool-owned, untouched)
- [x] No reap mid-stream: `not is_session_processing(sid)` guard; verified by test (c)
- [x] Reaccessing an evicted session rehydrates from `chat_sessions` with full history; verified by test (e)
- [x] TTL via `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS`, read at call time, int-parse fallback, **default 1800s**
- [x] The reaper drains/stops cleanly on app shutdown (lifespan), before the PTY drain
- [x] Tests cover (a) eviction+teardown, (b) subscriber-not-reaped, (c) processing-not-reaped, (e) rehydration, (f) shutdown drain — 11 tests, full suite 2946 green

## Verification Steps
- `docker exec the-one pytest tests/test_lifespan.py -q` and any new session-reaper test green
- New test: create N sessions, advance idle clock past TTL, assert eviction + Agent cleanup called
- New test: evict a session, reaccess it, assert full message history restored from DB
- Manual/log check: reaper starts in the lifespan and stops on shutdown without warnings

## Implementation Guidance

1. **Study the PTY reaper** in `tools/_session_registry.py` — note how it tracks last-activity, the reaper task cadence, the TTL source, the in-use guard, and the shutdown drain.
2. **Add `Agent.aclose()` (new, this leg)** — `the_one/agent/core.py`: `async def aclose(self)` with a `self._closed` idempotency guard, delegating to `self.llm.aclose()`. Add `async def aclose(self)` to the `LLMProvider` base (`the_one/llm/base.py`) — default no-op — and implement in the persistent-client providers (`await self.client.aclose()`; `httpx.AsyncClient.aclose()` is itself idempotent). Do NOT touch MCP (pool-owned, separate reaper).
3. **Add `last_activity: float` to `Session`** (`app.py:308`) and touch it (`time.monotonic()`) at: `_create_session` (~506), `_restore_session` (~617/648), the `/ws` message path / `_spawn_message_processing` (~376/1586), `chat_reset` (~1455), and **on `WebSocketDisconnect`** (~1625, so a closed tab's idle clock starts at disconnect).
4. **Add a shared `asyncio.Lock` for `_sessions`** and acquire it on every read-modify-write (create, restore, delete, reaper pop). Reaper = two-phase: under the lock, snapshot and select sessions where `not subscribers_for(sid)` AND `not is_session_processing(sid)` AND `(now - last_activity) > TTL`, pop them; **then call `await agent.aclose()` OUTSIDE the lock**. Also `session_locks.pop(sid, None)` on eviction (only when the lock isn't held) to avoid the lock-map leak.
5. **Write the reaper inline in `app.py`** (module-level `_WEB_SESSION_REAPER_INTERVAL_SECONDS` ~ TTL/10 but floor ~30s, a testable `_reap_web_sessions_once()` returning evicted ids, a `_reap_loop`, and a `_web_session_reaper_shutdown_drain()`), mirroring the PTY shapes — kept in `app.py` because `_sessions` + subscribers + `session_locks` + `is_session_processing` + the restore path all live there (avoids circular imports).
6. **Wire into the lifespan** — start the reaper task just after `start_periodic_sweep()` (~109, before `yield`); on shutdown, cancel + drain it AFTER the in-flight/resume task drains (~219/227) and BEFORE the PTY `_session_registry_shutdown_drain()` (~229) and `close_connection()` (~279).
7. **Add the TTL env var** — `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS`, read at call time via `os.environ.get` with int-parse fallback to **1800**, exactly like `_pool.py`'s `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`. Document in `.env.example` (Flight 06 DOC4 also touches it — append, don't conflict).
8. **Confirm the restore path** — a reaped (zero-subscriber) session, on next `join`, goes through `_get_or_restore_session`→`_restore_session` (652/526) and rebuilds the Agent from `chat_sessions` with full history. (Reopen latency = same as any rejoin today — acceptable, lossless.)
9. **Tests** — see Acceptance Criteria (a)-(d): use a mock/AsyncMock `Agent.aclose`; set `last_activity` to a stale value directly (simplest) or monkeypatch `time.monotonic`; add an autouse fixture clearing `app._sessions` (+ subscribers/locks) between tests.

## Edge Cases
- **WS disconnect during a long tool call** — the subscriber is removed at disconnect but the message task runs up to ~120s; the `is_session_processing` guard prevents reaping it mid-turn even though subscriber count is 0.
- **Concurrent reap vs `join`** — handled by the shared lock + close-outside-lock: a `join` arriving after the pop creates a fresh `Session`/`Agent` (separate object) while the old one is torn down — safe.
- **`aclose()` idempotency** — `shutdown_drain` may `aclose()` a session the reaper already closed; the `_closed` guard + httpx's own idempotent `aclose()` make this harmless.
- **Reaper interval vs TTL** — interval a fraction of the TTL (timely but not busy); floor at ~30s.
- **`delete_session` (`app.py:1574`) also lacks `aclose()`** — once `aclose()` exists it should call it too; minor, noted as a follow-up (not required for this leg's P4 fix).

## Files Affected
- `the_one/interfaces/web/app.py` - reaper (inline), `_sessions` lock + `last_activity`, lifespan wiring, TTL env read
- `the_one/agent/core.py` - new `Agent.aclose()` (idempotent)
- `the_one/llm/base.py` (+ Anthropic/OpenAI/Ollama provider impls) - new `LLMProvider.aclose()`
- `the_one/tools/_session_registry.py` - reference only (no change)
- `.env.example` - document `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` (coordinate with Flight 06)
- `the_one/agents.md` - brief anchor for the web-cache reaper (coordinate with Flight 06 DOC5)
- `tests/test_lifespan.py` (+ a new session-reaper test) - coverage

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
