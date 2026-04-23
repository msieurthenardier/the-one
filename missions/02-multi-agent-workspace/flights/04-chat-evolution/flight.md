# Flight: Chat Evolution

**Status**: in-flight
**Mission**: [Multi-Agent Workspace](../../mission.md)

## Contributing to Criteria
- [ ] Users can select which agent to converse with, and the selected agent's config is reflected in the conversation
- [ ] Chat conversations persist across application restarts, with full message history recoverable

---

## Pre-Flight

### Objective
Bridge the gap between the in-memory session system and the DB persistence layer: add agent picker, persistent chat history, and session restore.

### Open Questions
- [x] How to handle two session systems (in-memory + DB)? → D1: In-memory stays as cache, backed by DB
- [x] What to store in DB vs derive on restore? → D2: Store LLM Messages, derive UI events
- [x] How to handle "default" agent in DB? → D3: Nullable agent_name
- [x] When to save to DB? → D5: After each complete exchange ("done" event)

### Design Decisions

**D1. In-memory Session stays as cache, backed by DB.** The Session holds the live Agent object and WebSocket subscribers (not serializable). Each in-memory Session links to a `chat_sessions` row via its ID. DB is source of truth; memory is runtime cache.

**D2. Store LLM Messages in DB, derive UI events on restore.** Agent needs Message objects (with ToolCall IDs, etc). UI needs event dicts (type: user/assistant/tool_call/tool_result). Add `messages_to_ui_events()` to codec.py to convert Messages to UI events for replay. Save `Agent.messages` to DB after each complete exchange.

**D3. Make `chat_sessions.agent_name` nullable for the "default" agent.** The "default" agent is synthesized from settings and never stored in the agents table. A nullable FK avoids creating a ghost DB row. Schema V2 migration: drop NOT NULL, add index.

**D4. Agent picker is a dropdown in sidebar header, bound per-session.** Agent is chosen at session creation, not switchable mid-conversation (that would invalidate LLM context). Dropdown next to "+ new" with "default" always first. Sessions show agent badge in sidebar.

**D5. Save to DB after each complete exchange ("done" event).** Encode full `Agent.messages` list, overwrite the `messages` column. Batches writes naturally. Last exchange lost on mid-step crash — acceptable.

**D6. Remove duplicate `/api/sessions` endpoints from app.py.** The in-memory-only endpoints at app.py lines 271-288 conflict with DB-backed `/api/chat/sessions` in api.py. WebSocket protocol uses DB-backed sessions going forward.

**D7. Agent rebuild on restore: create fresh Agent, inject stored messages.** `factory.create(agent_name)` + replace `agent.messages` with decoded messages from DB. Agent resumes with full conversation context.

**D8. UX feedback on all state-changing actions.** Learned from Flight 03 — include flash/status feedback in design, not as a UAT discovery.

### Prerequisites
- [x] Flight 01 complete (DB persistence layer)
- [x] Flight 02 complete (app shell)
- [x] Flight 03 complete (Studio agent builder)

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
Connect the existing in-memory Session system with the DB ChatSession table. Sessions are created in both memory and DB simultaneously. Messages are saved to DB after each exchange. On restore (server restart or joining a session not in memory), rebuild the Agent from factory and inject decoded messages.

### Checkpoints
- [x] Schema V2 migration works, codec converts messages to UI events
- [x] Sessions persist to DB and restore on server restart
- [x] Agent picker in UI, bound per-session
- [ ] End-to-end UAT passes

### Adaptation Criteria

**Divert if**:
- Schema migration breaks existing data
- WebSocket protocol changes break existing clients

**Acceptable variations**:
- Minor CSS adjustments for agent picker layout
- Simplifying session list grouping

### Legs

- [x] `schema-migration-session-manager` - Schema V2 migration, codec extension, Session dataclass updates
- [x] `persistence-bridge` - Save/restore sessions to DB, lazy loading
- [x] `agent-picker-ui` - Agent dropdown in sidebar, session badges, content header badge
- [ ] `uat-and-alignment` - End-to-end verification of all chat evolution features

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
1. Start server fresh (empty DB) — Chat loads, can create sessions
2. Send messages, restart server — sessions persist, rejoin shows history, continue works
3. Create agent in Studio → switch to Chat → agent in dropdown → create session with it
4. Multiple agents with separate sessions — correct history per session
5. `curl -X POST /api/chat -d '{"message":"hello","agent_name":"test"}'` — works
6. Delete agent in Studio — its sessions gone from Chat sidebar
