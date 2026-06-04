# Flight: Long-Lived Session Hygiene

**Status**: ready
**Mission**: [Maintenance (Post-M11)](../../mission.md)

## Contributing to Criteria
- [ ] web `_sessions` (`app.py:340`) has an idle-TTL reaper (or size cap) modeled on the PTY `_session_registry`; long-lived process no longer grows unboundedly (P4)

---

## Pre-Flight

### Objective
Add eviction to the web `_sessions` cache so a long-running process stops growing unboundedly, by porting the idle-reaper + TTL pattern that the PTY `_session_registry` already uses.

### Open Questions
- [ ] Eviction policy — idle-TTL reaper vs LRU size cap vs both? See Design Decisions.

### Design Decisions

**Port the existing in-repo pattern, don't invent one**: `tools/_session_registry.py` already has a working idle-reaper + TTL + shutdown-drain. The web `_sessions` dict (`app.py:340`) should reuse that shape rather than a novel mechanism.
- Rationale: proven pattern, consistent mental model, less risk.
- Trade-off: the two caches hold different objects (PTY sessions vs `Agent` instances) so the reaper is adapted, not copied verbatim.

**Idle-TTL is the primary mechanism**: Evict entries untouched for a configurable idle window. The TTL is read from an env tunable (consistent with `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` etc.) and documented in `.env.example` (coordinate with Flight 06 DOC4).

**The DB is the durable store; the dict is a warm cache**: Eviction must only drop the in-memory `Agent` — the `chat_sessions` DB row remains, so an evicted session restores on next access. Confirm the restore path (`app.py:646`) cleanly rehydrates an evicted-then-reaccessed session.

**Clean teardown of evicted Agents**: Each `_sessions` entry pins a provider client + MCP tool handles; eviction must release those (the reaper calls the Agent's cleanup/close) so eviction actually frees resources rather than orphaning them.

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
- [ ] Reaper evicts idle sessions; evicted Agents are torn down
- [ ] Reaccessing an evicted session rehydrates from the DB with no data loss
- [ ] TTL configurable + documented

### Adaptation Criteria

**Divert if**:
- The `Agent` teardown on eviction proves unsafe mid-stream (e.g. an in-flight tool call) — add an in-use guard so only genuinely idle sessions are reaped.

**Acceptable variations**:
- Adding an LRU size cap alongside the TTL if idle-only proves insufficient.

### Legs
- [ ] `01-web-sessions-idle-reaper` - Port the PTY reaper pattern to the web `_sessions` cache (P4)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated (`.env.example` TTL var; agents.md note on the web-cache reaper)

### Verification
A test that creates sessions, advances idle time past the TTL, and asserts they are evicted and their Agents torn down; a test that reaccesses an evicted session and asserts full rehydration from `chat_sessions`. Suite green.
