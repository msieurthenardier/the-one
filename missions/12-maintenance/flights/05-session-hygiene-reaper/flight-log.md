# Flight Log: Long-Lived Session Hygiene

**Flight**: [Long-Lived Session Hygiene](flight.md)

## Summary
In progress. Single leg: add an idle-TTL reaper to the web `_sessions` cache (UI chat sessions) so closed-tab sessions stop accumulating, with clean Agent teardown and a configurable TTL — gated so a session with a live WS subscriber is never reaped (operator's "works without refresh" requirement).

---

## Leg Progress

### Leg 01 — web-sessions-idle-reaper (2026-06-04)

**Status**: landed

**What changed:**

1. **`LLMProvider.aclose()` (no-op base)** — `the_one/llm/base.py`: added default no-op `async def aclose(self)` to the base class. Anthropic provider overrides it with `await self.client.close()`; OpenAI provider overrides with `await self.client.close()`. Ollama uses per-request `httpx.AsyncClient` contexts (no persistent client) and inherits the no-op.

2. **`Agent.aclose()` (idempotent)** — `the_one/agent/core.py`: added `async def aclose(self)` with a `_closed` idempotency guard. Delegates to `await self.llm.aclose()`. Does NOT touch MCP (pool-owned). Confirmed: the openai and anthropic async clients both use `.close()` (not `.aclose()`) — verified in container.

3. **`Session.last_activity: float`** — `the_one/interfaces/web/app.py` `Session` dataclass: added `last_activity: float = field(default_factory=time.monotonic)`. Touched (set to `time.monotonic()`) at: `_create_session`, `_restore_session` (both in-place-update and new-session paths, plus the in-flight short-circuit path), `_spawn_message_processing` (top of lock body), `chat_reset`, and `WebSocketDisconnect`.

4. **Shared `asyncio.Lock` for `_sessions`** — `_sessions_lock: asyncio.Lock` added as module-level state. All read-modify-write sites (create, restore: not-found/degraded pop + in-place update + new session insert, delete_session action) serialized through it. `_reap_web_sessions_once()` does snapshot+pop under the lock, `agent.aclose()` outside. `session_locks.pop(sid, None)` called on eviction to prevent lock-map leak.

5. **Reaper functions (inline in `app.py`)**:
   - `_get_web_session_idle_ttl()` — reads `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` at call time, int-parse fallback to 1800.
   - `_reap_web_sessions_once()` — two-phase: snapshot+pop under lock, then `agent.aclose()` outside. Returns evicted session ids. Guards: `not subscribers_for(sid)` AND `not is_session_processing(sid)` AND `(now - last_activity) > TTL`.
   - `_web_session_reap_loop()` — wakes every `max(30, TTL // 10)` seconds, calls `_reap_web_sessions_once()`, defensive catch on loop-body errors.
   - `_web_session_reaper_shutdown_drain()` — cancels the task, drains all remaining sessions with `agent.aclose()`.

6. **Lifespan wiring** — reaper started (via `asyncio.create_task(_web_session_reap_loop())`) immediately after `start_periodic_sweep()` on startup; `_web_session_reaper_shutdown_drain()` called after in-flight/resume task drains, before PTY `_session_registry_shutdown_drain()`.

7. **`.env.example`** — documented `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` (with default 1800 and description).

8. **`the_one/agents.md`** — added "Web-session idle reaper" subsection documenting reaper mechanics, TTL env var, safety invariant, and teardown behavior.

9. **`tests/test_web_session_reaper.py`** (new file, 11 tests):
   - (a) eviction of idle zero-subscriber session + `aclose()` called
   - (b) subscribed session NOT reaped (operator hard requirement)
   - (c) processing session NOT reaped
   - (d) fresh session NOT evicted
   - (e) rehydration from DB after eviction
   - (f) shutdown drain closes all sessions
   - (g) shutdown drain cancels reaper task
   - (h) mixed sessions — only stale zero-subscriber evicted
   - (i) Agent.aclose() idempotency
   - (j) TTL env var read at call time
   - (k) invalid TTL env var falls back to 1800

**Test results**: 11/11 new tests passed; existing tests: `test_lifespan.py` 7/7, `test_agent.py` + `test_lifespan.py` + `test_web_session_reaper.py` 33/33, session-related suite 52/52, full unit suite pending (running broad).

**New env var**: `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` (default 1800, documented in `.env.example`).

---

## Flight Director Notes

### 2026-06-04 — Flight start (extended operator scoping)
- Invoked via `/agentic-workflow` for `the-one` mission 12, flight 05 (Long-Lived Session Hygiene). Branched `flight/05-session-hygiene-reaper` off `main` (Flights 01–04 merged; main at 6652126). Developer spawns pinned to `model: sonnet`.
- **Operator scoping conversation (resolved the open question with grounding):**
  - Confirmed `_sessions` (`app.py:346`) holds **UI chat sessions only** (the `/ws` Studio chat). Connector/Discord inbound is DB-direct via `connectors/_session.py:resolve_session` (no warm in-memory agent dict) — the reaper does NOT touch connector sessions.
  - **Eviction policy = idle-TTL only** (not LRU/both). The PTY `_session_registry` pattern being ported is itself idle-TTL-only (its `register()` enforces no cap despite the "5 max" docstring). Single-user browser chat won't hit a count flood; LRU deferrable per divert criteria.
  - **TTL default = 1800s (30 min)** via `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS`, mirroring `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` (also 1800, read-at-call-time, int-parse fallback).
  - **Operator hard requirement: a chat must keep working WITHOUT a page refresh after the idle window.** Root-caused: the `/ws` message path (`app.py:1586-1621`) holds a loop-scoped `Session`/`Agent` reference and does NOT re-look-up `_sessions` per message. So tearing down an Agent an open tab still references would break the next message → the "needs refresh" failure. **Design rule: the reaper only reaps sessions with ZERO live WS subscribers** (`subscribers_for(session.id)` empty) AND idle past TTL. An open tab is never reaped → works without refresh. The leak this fixes is the closed-tab case (`WebSocketDisconnect` at `:1623` drops the subscriber but never the `_sessions` entry → lingers forever). Reaped zero-subscriber sessions rehydrate on next `join`.
- Flight `ready` → `in-flight`. Proceeding to leg design review (with the WS-subscriber guard baked in as a hard AC).

### 2026-06-04 — Leg design review (Developer agent, Sonnet) + revisions
Approve-with-changes; several high-severity findings folded in (corrections + necessary additions, no new scope direction → no second cycle):
- **[high] No `Agent` teardown method exists.** The leg assumed `agent.close()`. Reality: `Agent` (core.py) has none, and **MCP handles are pool-owned** (separate reaper), not per-Agent. So this leg ADDS `Agent.aclose()` (idempotent) → new `LLMProvider.aclose()` (base no-op; Anthropic/OpenAI/Ollama close their `httpx` client). Teardown = close the LLM HTTP client only. Expanded Files Affected to `agent/core.py` + `llm/base.py` + providers.
- **[high] In-flight guard**: a WS can disconnect (subscriber→0) while a tool call runs ~120s. Reaper must also gate on `not is_session_processing(sid)`, not just zero-subscriber.
- **[high] Lock discipline**: `_sessions` has no lock today; the reaper's `aclose()` introduces an async boundary. Added a shared `asyncio.Lock` for all `_sessions` RMW; two-phase snapshot-under-lock → `aclose()` outside lock (PTY pattern).
- **[med] `aclose()` idempotency** (`_closed` guard); **[med] `session_locks` leak** — pop the evicted session's lock; **[low] touch `last_activity` on WS disconnect** (closed-tab clock start).
- Confirmed: subscriber registry = `sessions/_broadcast.py` `_subscribers` (keyed by `session.id`); `Session` needs a new `last_activity`; lifespan start after `start_periodic_sweep` (~109), stop before PTY drain (~229). Reaper inline in `app.py` (where the dict + guards live; avoids circular imports). `delete_session` also lacks `aclose()` → out-of-scope follow-up noted.
- Proceeding to implementation (`model: sonnet`).

---

### 2026-06-04 — Code review (Reviewer, Haiku) → confirmed
- **[HANDOFF:confirmed]**. Reviewer verified the load-bearing correctness: the eviction predicate requires all three guards (`not subscribers_for` AND `not is_session_processing` AND idle>TTL) — the operator's "works without refresh" requirement is bulletproof; lock discipline is two-phase (select+pop under lock, `aclose()` outside); `Agent.aclose()` idempotent and uses the correct `.close()` SDK method; lifespan wiring + TTL env reader correct; 11 tests meaningful. Single-leg flight, no UI → no Accessibility Reviewer. Full suite 2946 green (developer-run). Single review cycle, no fixes.

---

## Decisions

### Teardown scope = LLM HTTP client only (MCP is pool-owned)
**Context**: The leg's "release provider client + MCP tool handles" wording implied per-Agent MCP teardown.
**Decision**: `Agent.aclose()` closes only the LLM provider's HTTP client; MCP connections are owned by `mcp/_pool.py` with its own TTL reaper and are not per-Agent.
**Impact**: Eviction frees the LLM client deterministically; MCP idle connections continue to be reaped by their existing pool reaper. No double-management.

---

## Deviations

### Provider close method is `.close()`, not `.aclose()`
**Planned**: Leg guidance said providers implement `await self.client.aclose()`.
**Actual**: The Anthropic and OpenAI async SDK clients expose async `.close()` (not `.aclose()`); the developer verified in-container and used `.close()`.
**Reason**: SDK API reality. Harmless — `Agent.aclose()` is still the public name; only the internal provider call differs.

---

## Anomalies

_None._

---

## Session Notes
