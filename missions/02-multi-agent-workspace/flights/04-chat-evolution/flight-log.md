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

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
