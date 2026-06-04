# Flight: Long-Lived Session Hygiene

**Status**: landed
**Mission**: [Maintenance (Post-M11)](../../mission.md)

## Contributing to Criteria
- [ ] web `_sessions` (`app.py:340`) has an idle-TTL reaper (or size cap) modeled on the PTY `_session_registry`; long-lived process no longer grows unboundedly (P4)

---

## Pre-Flight

### Objective
Add eviction to the web `_sessions` cache so a long-running process stops growing unboundedly, by porting the idle-reaper + TTL pattern that the PTY `_session_registry` already uses.

### Open Questions
- [x] Eviction policy — **RESOLVED at flight start: idle-TTL only** (operator), default **1800s / 30 min** via `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` (mirrors `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`, also 1800). No LRU cap (single-user browser chat won't hit a count flood; the divert criteria allow adding one later if needed).
- [x] Scope clarified: this dict (`app.py:346`) holds **UI chat sessions only** (the `/ws` Studio chat). Connector/Discord sessions are resolved DB-direct via `connectors/_session.py` and are NOT in this cache — the reaper does not touch them.
- [x] **Operator hard requirement: a chat must keep working WITHOUT a page refresh after the idle window.** This dictates the in-use guard (see Design Decisions): only sessions with **zero live WS subscribers** are reapable; an open tab is never reaped.

### Design Decisions

**Port the existing in-repo pattern, don't invent one**: `tools/_session_registry.py` already has a working idle-reaper + TTL + shutdown-drain. The web `_sessions` dict (`app.py:340`) should reuse that shape rather than a novel mechanism.
- Rationale: proven pattern, consistent mental model, less risk.
- Trade-off: the two caches hold different objects (PTY sessions vs `Agent` instances) so the reaper is adapted, not copied verbatim.

**Idle-TTL is the primary mechanism**: Evict entries untouched for a configurable idle window. The TTL is read from an env tunable (consistent with `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` etc.) and documented in `.env.example` (coordinate with Flight 06 DOC4).

**The DB is the durable store; the dict is a warm cache**: Eviction must only drop the in-memory `Agent` — the `chat_sessions` DB row remains, so an evicted session restores on next access. Confirm the restore path (`app.py:646`) cleanly rehydrates an evicted-then-reaccessed session.

**Clean teardown of evicted Agents**: Each `_sessions` entry pins a provider client + MCP tool handles; eviction must release those (the reaper calls the Agent's cleanup/close) so eviction actually frees resources rather than orphaning them.

**In-use guard keys on live WS subscribers, not just message recency** (operator hard requirement — "works without refresh"): The `/ws` message path holds a loop-scoped reference to the `Session`/`Agent` and does NOT re-look-up `_sessions` per message (`app.py:1586-1621`). So if the reaper tore down an Agent that an open tab still references, the next message on that tab would hit a dead Agent — the exact "needs a refresh" failure. Therefore the reaper must **never reap a session that has ≥1 live WS subscriber** (`subscribers_for(session.id)` non-empty). Only sessions with **zero subscribers AND idle past the TTL** are reaped — precisely the closed-tab/navigated-away leak (today `WebSocketDisconnect` at `:1623` drops the subscriber but never the `_sessions` entry, so those linger forever). A reaped (zero-subscriber) session has no stale held reference; reopening it re-`join`s and rehydrates from the DB.

### Prerequisites
- [ ] Confirm the restore path rehydrates a reaped session without data loss.

### Pre-Flight Checklist
- [ ] All open questions resolved (eviction policy)
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach
One leg: introduce an idle-TTL reaper for the web `_sessions` dict, adapted from `_session_registry`, with clean Agent teardown on eviction and a configurable TTL env var. Add tests asserting eviction-after-idle and clean rehydration-on-reaccess.

### Checkpoints
- [x] Reaper evicts idle, zero-subscriber sessions; evicted Agents torn down (`Agent.aclose()`)
- [x] Reaccessing an evicted session rehydrates from the DB with no data loss
- [x] TTL configurable (`THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS`, default 1800) + documented

### Adaptation Criteria

**Divert if**:
- The `Agent` teardown on eviction proves unsafe mid-stream (e.g. an in-flight tool call) — add an in-use guard so only genuinely idle sessions are reaped.

**Acceptable variations**:
- Adding an LRU size cap alongside the TTL if idle-only proves insufficient.

### Legs
- [x] `01-web-sessions-idle-reaper` - Port the PTY reaper pattern to the web `_sessions` cache (P4)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (11 new reaper tests; full suite 2946 green)
- [x] Documentation updated (`.env.example` TTL var; agents.md web-cache-reaper note)

### Verification
A test that creates sessions, advances idle time past the TTL, and asserts they are evicted and their Agents torn down; a test that reaccesses an evicted session and asserts full rehydration from `chat_sessions`. Suite green.
