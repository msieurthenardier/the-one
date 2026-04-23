# Flight Log: Chat Evolution

**Flight**: [Chat Evolution](flight.md)

## Summary
Flight 04 implements DB-backed chat sessions, agent picker UI, and session persistence/restore.

---

## Leg Progress

### Leg 01: Schema Migration & Session Manager — completed (2026-04-23)
- **Started**: 2026-04-23
- Schema V2 migration implemented: recreates `chat_sessions` table with nullable `agent_name`, adds `idx_chat_sessions_agent` index
- `CURRENT_VERSION` updated to 2, V1-to-V2 sequential migration works for both fresh and existing DBs
- `ChatSession.agent_name` changed to `str | None = None`
- `messages_to_ui_events()` added to codec.py — converts stored Messages to UI event dicts for session replay
- Session dataclass updated with `agent_name: str | None = None` field, `summary()` includes it
- Removed 3 in-memory-only `/api/sessions` REST endpoints from app.py (GET list, GET by id, DELETE by id)
- 9 new tests added in `TestMessagesToUIEvents` class covering all message types and edge cases
- All 134 tests passing (0 failures)

### Leg 02: Persistence Bridge — completed (2026-04-23)
- **Started**: 2026-04-23
- Replaced `_get_session()` with three new functions: `_create_session()`, `_restore_session()`, `_get_or_restore_session()`
- Added `_save_session_to_db()` helper that encodes agent messages and updates DB via `model_copy()`
- Added `_chat_repo()` helper for DB access (local to app.py, separate from api.py)
- `_create_session`: normalizes agent_name ("default"/empty -> None for FK safety), persists to DB immediately
- `_restore_session`: loads from DB, rebuilds agent via factory, falls back to default on KeyError, injects decoded messages, builds UI events
- `_process_and_broadcast`: saves to DB after each complete exchange (before "done" event), wrapped in try/except
- `list_sessions` WS handler: queries `ChatSessionRepository.list()` instead of in-memory dict, returns summary fields only
- `delete_session` WS handler: removes from both `_sessions` dict and DB
- `new_session` WS handler: accepts `agent_name` from payload
- `/api/chat`: accepts `agent_name` parameter, uses `_get_or_restore_session` or `_create_session`
- `/api/chat/reset`: saves after reset via `_save_session_to_db()`
- All join/new_session/auto-join responses include `agent_name`
- All 134 tests passing (0 failures)

### Leg 03: Agent Picker UI — completed (2026-04-23)
- **Started**: 2026-04-23
- Sidebar header restructured: title on first line, then row with agent `<select>` dropdown + "+ new" button
- `fetchAgents()` fetches `/api/agents`, populates dropdown with `.name` from each agent, prepends "default" option (value=""), preserves selection across refreshes, called on WS connect and `activate()`
- `new_session` click handler reads `agentSelect.value`, includes `agent_name` in WS message when non-empty
- `renderSessionList` converted to flat list (removed source-based grouping), two-line items with title + agent subtitle (`session-item-text` column layout)
- `session_joined` handler reads `data.agent_name`, stores as `currentAgentName`, calls `updateAgentBadge()`
- Content header: added `session-agent-badge` span after status, `updateAgentBadge(name)` sets text to `name || 'default'`
- `renderHistory`: treats source "restored" like "web" (no [restored] prefix)
- `activate()`: calls `fetchAgents()` when WS is open
- CSS: removed `.session-group` rules, added `.sidebar-actions` flex row, `.agent-select` dark-theme styled, `.session-item-text` column layout, `.session-item-agent` dimmed, `.session-agent-badge` badge in content header
- All 134 tests passing (0 failures)

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
