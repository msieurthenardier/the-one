# Leg: web-sessions-idle-reaper

**Status**: ready
**Flight**: [Long-Lived Session Hygiene](../flight.md)

## Objective
Add an idle-TTL reaper to the web `_sessions` cache (`app.py:340`) — modeled on the PTY `_session_registry` reaper — so idle sessions are evicted and their `Agent` resources released, bounding memory growth in a long-lived process (resolves finding P4).

## Context
- Maintenance report 2026-06-04, finding **P4** (Action Required): the web `_sessions: dict[str, Session]` (`app.py:340`) has no TTL, size cap, or reaper. Entries are added on create (`:502`) and restore (`:646`) and removed only on degraded-restore (`pop` at `544/571/580/589`) or explicit user delete (`del` at `1572`). Each entry pins a live `Agent` (provider client, MCP tool handles, full message history). Single-user does NOT bound this — one operator accumulates sessions over a long-running process.
- The PTY `tools/_session_registry.py` already implements a full idle-reaper + TTL + shutdown-drain (`_sessions` at `:73`) — a copyable pattern. The `_session_registry` race finding (P6) is a *separate* dict and is out of scope here.

## Inputs
- `the_one/interfaces/web/app.py:340` (the web `_sessions` dict) and its mutation sites (`:502, 544, 571, 580, 589, 646, 1572`).
- `the_one/tools/_session_registry.py` (the reaper pattern to adapt) — idle reaper, TTL, shutdown drain.
- The `chat_sessions` DB table + restore path (`app.py:646`) as the durable backing store.

## Outputs
- An idle-TTL reaper for web `_sessions` with clean `Agent` teardown on eviction.
- A configurable TTL env var (documented; coordinate with Flight 06 DOC4).

## Acceptance Criteria
- [ ] Web `_sessions` entries idle beyond a configurable TTL are evicted by a background reaper
- [ ] Eviction tears down the `Agent` (releases provider client + MCP tool handles) — eviction frees resources, not orphans them
- [ ] An in-use / in-flight session is NOT reaped mid-operation (idle is measured from last activity; in-use guard if needed)
- [ ] Reaccessing an evicted session rehydrates it from `chat_sessions` with no data loss (the dict is a warm cache, the DB is durable)
- [ ] The TTL is configurable via an env var (e.g. `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS`) read the same way as the other pool TTLs; default chosen to be generous for an interactive operator
- [ ] The reaper drains/stops cleanly on app shutdown (lifespan)
- [ ] Tests cover: eviction-after-idle + Agent teardown; rehydration-on-reaccess; no-reap-while-in-use

## Verification Steps
- `docker exec the-one pytest tests/test_lifespan.py -q` and any new session-reaper test green
- New test: create N sessions, advance idle clock past TTL, assert eviction + Agent cleanup called
- New test: evict a session, reaccess it, assert full message history restored from DB
- Manual/log check: reaper starts in the lifespan and stops on shutdown without warnings

## Implementation Guidance

1. **Study the PTY reaper** in `tools/_session_registry.py` — note how it tracks last-activity, the reaper task cadence, the TTL source, the in-use guard, and the shutdown drain.
2. **Adapt for the web cache** — the objects are `Agent`/`Session`, not PTY sessions, so the eviction callback calls the Agent's cleanup/close (release provider client + MCP handles) rather than killing a PTY. Track last-activity by touching a timestamp on each session access (the request paths that read `_sessions`).
3. **Wire the reaper into the lifespan** — start it where the app starts other background tasks (`app.py` lifespan), stop/drain it on shutdown alongside the existing connection close (`:273`).
4. **Add the TTL env var** — read via `os.environ` like the connector-pool TTLs; document in `.env.example` (Flight 06 DOC4 will also touch that file — coordinate to avoid conflict).
5. **Confirm the restore path** — `app.py:646` already restores sessions; verify a reaped-then-reaccessed session goes through it cleanly.
6. **Tests** — cover eviction, teardown, rehydration, and the in-use guard.

## Edge Cases
- **In-flight tool call or streaming response** — must not reap a session mid-operation; gate on activity recency and/or an explicit in-use flag.
- **WebSocket-attached session** — a session with a live WS connection is by definition in-use; ensure the activity touch covers WS traffic, not just HTTP.
- **Reaper interval vs TTL** — interval should be a fraction of the TTL so eviction is timely but not busy.

## Files Affected
- `the_one/interfaces/web/app.py` - reaper task, activity tracking, lifespan wiring, TTL env read
- `the_one/tools/_session_registry.py` - reference only (no change)
- `.env.example` - document the new TTL var (coordinate with Flight 06)
- `the_one/agents.md` - brief anchor for the web-cache reaper (coordinate with Flight 06 DOC5)
- `tests/test_lifespan.py` (+ a new session-reaper test) - coverage

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
