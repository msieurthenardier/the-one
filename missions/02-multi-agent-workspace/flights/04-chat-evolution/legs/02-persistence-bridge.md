# Leg: persistence-bridge

**Status**: completed
**Flight**: [Chat Evolution](../flight.md)

## Objective
Sessions persist to DB and restore on server restart or session join, with full message history and agent context.

## Context
- Leg 01 established: V2 schema (nullable agent_name), `messages_to_ui_events()` in codec, Session dataclass with `agent_name` field
- Design Decision D1: In-memory Session is cache, DB is source of truth
- Design Decision D5: Save to DB after each complete exchange ("done" event)
- Design Decision D7: Rebuild agent on restore via `factory.create(agent_name)` + inject stored messages
- `ChatSessionRepository` in `repositories.py` has full CRUD: list, get, create, update, delete, purge_messages
- `encode_messages()` / `decode_messages()` handle full round-trip serialization
- `AgentFactory.create(name)` supports named agents and "default"
- `Agent.messages` is a publicly writable list that can be replaced for restore

## Inputs
- `the_one/interfaces/web/app.py` — Session dataclass with agent_name, `_get_session()` creates in-memory-only sessions, `_process_and_broadcast()` doesn't save to DB, WebSocket handlers use in-memory `_sessions` dict for list/delete
- `the_one/db/repositories.py` — ChatSessionRepository ready to use
- `the_one/db/codec.py` — encode_messages, decode_messages, messages_to_ui_events all ready
- `the_one/agent/factory.py` — AgentFactory.create(name) ready

## Outputs
- `_create_session()` function that creates both in-memory Session and DB ChatSession row
- `_restore_session()` function that loads from DB, rebuilds Agent, injects messages, builds UI events
- `_get_or_restore_session()` function that checks memory first, falls back to DB
- `_save_session_to_db()` function that encodes agent.messages and updates DB
- `_process_and_broadcast()` calls save after each exchange
- WebSocket `list_sessions` queries DB instead of in-memory dict
- WebSocket `delete_session` removes from both memory and DB
- WebSocket `new_session` accepts `agent_name` from payload and creates DB row
- `/api/chat` REST endpoint accepts `agent_name` and saves after processing
- `/api/chat/reset` saves after reset

## Acceptance Criteria
- [x] New sessions are persisted to DB immediately on creation
- [x] Messages saved to DB after each complete exchange (after "done" event)
- [x] Server restart preserves all sessions — `list_sessions` shows them from DB
- [x] Joining a restored session shows full conversation history (UI events derived from stored messages)
- [x] Continuing a restored conversation works (agent has correct message context)
- [x] Deleting a session removes from both in-memory cache and DB
- [x] `new_session` WebSocket action accepts `agent_name` from payload
- [x] `/api/chat` REST endpoint accepts `agent_name` parameter
- [x] Agent rebuild on restore uses correct agent config (named or default)
- [x] If agent was deleted, restore falls back to default agent gracefully
- [x] Existing tests still pass
- [x] `/api/chat/reset` persists the reset to DB

## Verification Steps
- Run `python3 -m pytest tests/ -v` — full suite passes
- Inspect `_create_session` — creates both in-memory Session and DB ChatSession row
- Inspect `_restore_session` — loads from DB, creates Agent via factory, replaces agent.messages
- Inspect `_process_and_broadcast` — calls `_save_session_to_db` after agent step completes
- Inspect WebSocket `list_sessions` — queries ChatSessionRepository.list()
- Inspect WebSocket `delete_session` — deletes from both _sessions dict and DB

## Implementation Guidance

1. **Add DB helper** (`the_one/interfaces/web/app.py`)
   - Add `from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events`
   - Add `from the_one.db.models import ChatSession`
   - Add `from the_one.db.repositories import ChatSessionRepository`
   - Add `import logging` and create logger
   - Add async helper `_chat_repo() -> ChatSessionRepository` (get connection, return repo) — this is a local helper in app.py, separate from the one in api.py

2. **`_create_session(agent_name, source, session_id)`** — replaces ad-hoc session creation
   - Generate session ID if not provided
   - Normalize agent_name: if "default" or empty, store as None in DB (because "default" doesn't exist in `agents` table — FK would be violated)
   - `source` parameter is for in-memory Session only, not stored to DB
   - Create Agent via `factory.create(agent_name or "default")`
   - Create in-memory Session with agent_name field set
   - Create ChatSession model and persist via repo.create()
   - Return the in-memory Session

3. **`_restore_session(session_id)`** — loads from DB into memory
   - Get ChatSession from repo (return None if not found)
   - Create Agent via `factory.create(db_session.agent_name or "default")`
   - If agent was deleted (KeyError), fall back to `factory.create("default")`
   - Decode messages from DB, replace `agent.messages` if non-empty
   - Build UI events via `messages_to_ui_events(messages)`
   - Create in-memory Session with history=ui_events, agent_name, title from DB
   - Store in `_sessions` dict and return

4. **`_get_or_restore_session(session_id)`** — cache-then-DB lookup
   - Check `_sessions` dict first
   - Fall back to `_restore_session`

5. **`_save_session_to_db(session)`** — persist current state
   - Encode `session.agent.messages` via `encode_messages()`
   - Fetch existing ChatSession via `repo.get(session.id)`
   - Build updated model: `db_session.model_copy(update={"title": session.title, "messages": encoded})`
   - Call `repo.update(updated)`
   - Wrap in try/except KeyError: log warning if session not found in DB (shouldn't happen)
   - Save errors should be logged but NEVER interrupt the conversation flow

6. **Update `_process_and_broadcast`**
   - After the agent step loop completes (before sending "done" event), call `_save_session_to_db(session)`
   - Save must be in try/except so DB errors do not prevent the "done" event from being sent

7. **Update WebSocket handlers**
   - `join`: use `_get_or_restore_session()`, include `agent_name` in response
   - `list_sessions`: query `ChatSessionRepository.list()` instead of iterating `_sessions`, return id/title/agent_name/created_at/updated_at
   - `new_session`: read `agent_name` from payload, use `_create_session(agent_name=...)`, include `agent_name` in response
   - `delete_session`: delete from both `_sessions` and DB (catch KeyError on DB delete)
   - Auto-join (no session): use `_create_session()`, include `agent_name` in response

8. **Update `/api/chat` REST endpoint**
   - Accept `agent_name` from payload
   - Use `_get_or_restore_session` for existing sessions, `_create_session` for new ones
   - Save is handled by `_process_and_broadcast` already

9. **Update `/api/chat/reset`**
   - After reset, call `_save_session_to_db(s)` to persist the cleared state

10. **Remove old `_get_session`**
    - Replace all call sites with the new functions, then delete it

## Edge Cases
- **Agent deleted between save and restore**: `factory.create(name)` raises KeyError → catch and fall back to default
- **Session in DB but not in memory**: normal case after restart, handled by `_restore_session`
- **Session in memory but not in DB**: shouldn't happen (create writes to both), but `_save_session_to_db` logs warning
- **Empty messages in DB**: `decode_messages("[]")` returns `[]`, agent keeps its initial system message
- **Concurrent WebSocket clients on same session**: subscribers set already handles this — save writes full message list regardless
- **DB save failure mid-conversation**: log error, continue conversation — user experience is not interrupted, but persistence may be stale
- **list_sessions response size**: return only summary fields (id, title, agent_name, created_at, updated_at) — do NOT include message payloads

## Files Affected
- `the_one/interfaces/web/app.py` — Major refactor of session management

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
