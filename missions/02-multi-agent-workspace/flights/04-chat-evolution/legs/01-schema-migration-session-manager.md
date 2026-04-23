# Leg: schema-migration-session-manager

**Status**: completed
**Flight**: [Chat Evolution](../flight.md)

## Objective
DB schema V2 migration (nullable agent_name), codec extension for UI event conversion, and Session dataclass updates to support agent selection and DB linkage.

## Context
- Flight 01 established the DB persistence layer with `chat_sessions` table requiring `agent_name NOT NULL`
- The "default" agent is synthesized from settings and never stored in the `agents` table, so a NOT NULL FK constraint prevents creating sessions for it
- Design Decision D3: make `agent_name` nullable
- Design Decision D2: add `messages_to_ui_events()` to convert stored Messages to UI event format for replay
- Design Decision D6: remove in-memory-only `/api/sessions` REST endpoints from app.py (different URL path from DB-backed `/api/chat/sessions` in api.py — no frontend code references `/api/sessions`, sessions are managed via WebSocket)

## Inputs
- `the_one/db/schema.py` — V1 schema with `agent_name TEXT NOT NULL`
- `the_one/db/models.py` — `ChatSession` with `agent_name: str`
- `the_one/db/codec.py` — has `encode_messages()` and `decode_messages()` but no UI event conversion
- `the_one/interfaces/web/app.py` — Session dataclass without `agent_name` field, duplicate `/api/sessions` endpoints at lines 271-288
- `the_one/llm/base.py` — Message, Role, ToolCall, ToolResult dataclasses

## Outputs
- V2 schema migration that makes `agent_name` nullable and adds index
- Updated `ChatSession` model with `agent_name: str | None = None`
- New `messages_to_ui_events()` function in codec.py
- Updated Session dataclass with `agent_name` field
- Duplicate `/api/sessions` REST endpoints removed from app.py
- Tests for `messages_to_ui_events`

## Acceptance Criteria
- [x] Schema V2 migrates cleanly from V1 (table recreated with nullable agent_name, index added)
- [x] `CURRENT_VERSION` updated to 2
- [x] `ChatSession.agent_name` is `str | None = None`
- [x] `messages_to_ui_events` converts user messages to `{type: "user", content, source: "restored"}`
- [x] `messages_to_ui_events` converts assistant text to `{type: "assistant", content}`
- [x] `messages_to_ui_events` converts assistant tool_calls to `{type: "tool_call", name, arguments}` per call
- [x] `messages_to_ui_events` converts tool results to `{type: "tool_result", content, is_error}`
- [x] `messages_to_ui_events` skips system messages
- [x] Session dataclass has `agent_name: str | None = None` field
- [x] Session.summary() includes `"agent_name": self.agent_name` (None renders as JSON null)
- [x] In-memory-only `/api/sessions` GET, GET/{id}, DELETE/{id} endpoints removed from app.py (safe — no frontend consumers, DB-backed equivalents exist at `/api/chat/sessions` in api.py)
- [x] Existing tests still pass
- [x] New tests for `messages_to_ui_events` covering all message types

## Verification Steps
- Run `python3 -m pytest tests/test_db_codec.py -v` — all tests pass including new ones
- Run `python3 -m pytest tests/ -v` — full suite passes
- Inspect schema.py — V2 migration recreates table (SQLite can't ALTER COLUMN)
- Inspect app.py — no `/api/sessions` endpoints remain (only the DB-backed ones in api.py)

## Implementation Guidance

1. **Schema V2 migration** (`the_one/db/schema.py`)
   - Update `CURRENT_VERSION = 2`
   - Add V2 migration in `ensure_schema()` after V1 block
   - SQLite can't ALTER COLUMN — must recreate table: CREATE new table, INSERT...SELECT, DROP old, RENAME
   - New table: `agent_name TEXT REFERENCES agents(name) ON DELETE CASCADE` (no NOT NULL)
   - Add `CREATE INDEX idx_chat_sessions_agent ON chat_sessions(agent_name)`
   - Set `version = 1` after V1 migration so V2 runs in sequence on fresh DB
   - Use `executescript` for V2 DDL (consistent with V1 pattern)
   - After V2 DDL, insert version 2 into `schema_version` and commit (matching V1 pattern at lines 87-88)

2. **Update model** (`the_one/db/models.py`)
   - Change `agent_name: str` to `agent_name: str | None = None`

3. **Add `messages_to_ui_events`** (`the_one/db/codec.py`)
   - Import `Role` from `the_one.llm.base`
   - Function signature: `messages_to_ui_events(messages: list[Message]) -> list[dict[str, Any]]`
   - Skip `Role.SYSTEM`
   - `Role.USER` → `{"type": "user", "content": msg.content, "source": "restored"}`
   - `Role.ASSISTANT` with content → `{"type": "assistant", "content": msg.content}`
   - `Role.ASSISTANT` with tool_calls → one `{"type": "tool_call", "name": tc.name, "arguments": tc.arguments}` per call
   - `Role.TOOL` with tool_result → `{"type": "tool_result", "content": msg.tool_result.content, "is_error": msg.tool_result.is_error}` (full-length content — truncation is a broadcast concern, not a storage/restore concern)
   - Note: assistant messages can have BOTH content and tool_calls — emit both

4. **Update Session dataclass** (`the_one/interfaces/web/app.py`)
   - Add `agent_name: str | None = None` field to Session
   - Update `summary()` to include `agent_name`
   - Remove the three `/api/sessions` endpoints (GET list, GET by id, DELETE by id) — safe, no frontend consumers
   - **Scope boundary**: Do NOT modify `_get_session()`, `_process_and_broadcast()`, or WebSocket handlers — those are leg 02's scope. Only add the `agent_name` field and update `summary()`.

5. **Tests** (`tests/test_db_codec.py`)
   - Add `TestMessagesToUIEvents` class with tests for: skips system, user message, assistant text, assistant tool calls, assistant with both text and tool calls, tool result, tool result error, full conversation

## Edge Cases
- **Assistant message with both content and tool_calls**: emit both an assistant event and tool_call events
- **Tool message without tool_result**: skip (shouldn't happen but be safe)
- **Empty messages list**: return `[]`
- **Fresh DB install**: V1 then V2 migration must run in sequence
- **Existing V1 DB with data**: migration must preserve existing chat_sessions rows

## Files Affected
- `the_one/db/schema.py` — V2 migration
- `the_one/db/models.py` — nullable agent_name
- `the_one/db/codec.py` — add messages_to_ui_events
- `the_one/interfaces/web/app.py` — Session dataclass update, remove duplicate endpoints
- `tests/test_db_codec.py` — new tests

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
