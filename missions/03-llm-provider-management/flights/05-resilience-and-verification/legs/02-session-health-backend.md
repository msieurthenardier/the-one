# Leg: session-health-backend

**Status**: completed
**Flight**: [Resilience & Verification](../flight.md)

## Objective

Replace the silent "fall back to default agent" behavior in `_restore_session` with explicit session-health classification, and surface that classification through the `session_joined` WebSocket message so the frontend (next leg) can render appropriate banners and disable input for degraded sessions.

## Context

Flight 05 design decision **"Session health validation: three states on join"** specifies this. Today, when a user rejoins a session whose agent has been deleted, `the_one/interfaces/web/app.py:154-161` silently swaps in the default agent:

```python
try:
    agent = await factory.create(agent_name_for_factory)
except KeyError:
    logger.warning(
        "Agent %r not found, falling back to default for session %s",
        db_session.agent_name, session_id,
    )
    agent = await factory.create("default")
```

That fallback is the bug the user explicitly wants removed: it makes the UI silently lie about which agent the user is talking to. The design decision requires three explicit states surfaced to the frontend:

- `"ok"` — agent and provider valid, chat is functional
- `"agent_deleted"` — `db_session.agent_name` is set but no agent config of that name exists. History shown read-only; new messages cannot be sent.
- `"provider_missing"` — agent exists but has no `provider_config_id`, OR the referenced provider was deleted. Banner directs user to Studio; once fixed, the next join attempt will return `"ok"`.

A fourth implicit state, `"not_found"`, exists for the case where the session id doesn't exist in the DB at all — current behavior returns `None`, and we preserve that so the websocket auto-create path (lines 514-519) is unchanged.

The decision also says: "Health checks apply to `join` only. `new_session` continues to raise exceptions on invalid agents." That's the scope boundary for this leg — `_create_session` is unchanged.

Flight 04 introduced provider-deletion protection (the schema enforces FK), but agents that referenced a provider deleted before that protection still have orphaned `provider_config_id` values, and agents created without a provider have `provider_config_id IS NULL`. Both produce `provider_missing`.

### Accepted external breakage: Concourse autopilot

`ci/pipeline.yml:66` POSTs to `/api/chat` with `session_id: "autopilot"` every 30 minutes. Today, if the autopilot session's agent gets deleted, the silent default-agent fallback keeps the pipeline running — masking the breakage. After this leg, that POST returns `{"error": "session_agent_deleted"}` (or `session_provider_missing`) on degraded sessions; the pipeline's `urllib.urlopen` still gets a 200 OK but `result.get("messages", [])` is empty, so the autopilot will silently no-op forever in that state.

This is intentional. The silent fallback was hiding the operational issue the design decision is trying to surface. The autopilot operator will need to either (a) recreate the autopilot session via `new_session` with a valid agent, or (b) update `ci/pipeline.yml` to surface `result.get("error")`. Neither is in scope for this leg — flagging this as accepted external breakage; record it in the flight log Decisions section so a future operator finds it.

## Inputs

What exists before this leg:

- Flight 04 has fully landed. The branch is `flight/05-resilience-and-verification`, with leg 01 (key-rotation-atomicity) already implemented but not yet committed (changes are in the working tree).
- `the_one/interfaces/web/app.py` — `_restore_session` (lines 144-180), `_get_or_restore_session` (lines 183-187), WS `join` handler (lines 510-529), HTTP `/api/chat` handler (lines 440-476)
- `the_one/agent/factory.py` — `AgentFactory.create()` raises `KeyError("Unknown agent: ...")` (factory.py:102) when the named agent doesn't exist, and `ValueError("Agent ... has no provider configured")` (factory.py:39-43) when `provider_config_id is None`. `provider_repo.get(provider_config_id)` raises `KeyError("Provider not found: ...")` (db/repositories.py:401) when the provider was deleted.
- `the_one/agent/store.py` — `AgentConfigStore` exposes `await store.exists(name)` (used by `factory._load_config` at factory.py:98)
- `the_one/db/repositories.py` — `LLMProviderRepository.get(id)` and `ChatSessionRepository.get(session_id)` both raise `KeyError` on miss
- `tests/test_session_lifecycle.py` — 13 tests across `TestCreateSession`, `TestSaveSession`, `TestRestoreSession`, `TestGetOrRestoreSession` (8 of which call `_restore_session` or `_get_or_restore_session` directly and will need updates for the new return type)

## Outputs

What exists after this leg completes:

- `the_one/interfaces/web/app.py`:
  - New module-level constants `SESSION_STATUS_OK = "ok"`, `SESSION_STATUS_NOT_FOUND = "not_found"`, `SESSION_STATUS_AGENT_DELETED = "agent_deleted"`, `SESSION_STATUS_PROVIDER_MISSING = "provider_missing"` (or a small `Literal` type alias). Pick whichever fits the file's existing style.
  - New dataclass `RestoredSession` with fields `session: Session | None`, `status: str`, `db_session: ChatSessionModel | None` (the model is needed so the WS handler can render history for degraded states without re-querying the DB).
  - `_restore_session(session_id) -> RestoredSession` — the silent fallback at lines 154-161 is **removed**; replaced with explicit status detection. Degraded states do **not** build an `Agent` and do **not** insert into `_sessions`.
  - `_get_or_restore_session(session_id) -> RestoredSession` — for cached entries returns `RestoredSession(cached, "ok", None)`; otherwise delegates to `_restore_session`. Health checks are NOT re-run for cached sessions; the design decision scopes health checks to the join boundary.
  - WS `join` action (lines 510-529) — reads the new `RestoredSession`, includes `status` in the `session_joined` payload, and handles the four states:
    - `ok` → unchanged behavior, send full session_joined with history from the in-memory `Session`
    - `not_found` → unchanged behavior (fall through to `_create_session`)
    - `agent_deleted` / `provider_missing` → send `session_joined` with `status`, `session_id`, `title` (from `db_session`), `agent_name` (from `db_session`), and `history` decoded from `db_session.messages`. Set the local `session = None` so subsequent message actions in the same WS connection don't operate on the degraded session.
  - HTTP `/api/chat` (lines 440-476) — `_get_or_restore_session` now returns `RestoredSession`; for degraded statuses, return `{"error": "session_<status>"}` (e.g. `"session_agent_deleted"`) without attempting to create a new session. For `not_found`, preserve current fall-through to `_create_session`.
- `tests/test_session_lifecycle.py` — existing tests updated for the new return shape; new tests added for `agent_deleted`, `provider_missing`, and `ok` paths (5+ new tests).
- All previously-passing tests still pass.

## Acceptance Criteria

- [x] `RestoredSession` dataclass exists in `the_one/interfaces/web/app.py` (placement near `Session`, with `from dataclasses import dataclass` if not already imported), with fields `session: Session | None`, `status: str`, `db_session: ChatSessionModel | None`.
- [x] Module-level status constants (`SESSION_STATUS_OK`, `SESSION_STATUS_NOT_FOUND`, `SESSION_STATUS_AGENT_DELETED`, `SESSION_STATUS_PROVIDER_MISSING`) are defined exactly once and used everywhere instead of literal strings — except in tests (tests may use the literals for readability).
- [x] `_restore_session(session_id)` returns `RestoredSession`:
  - `RestoredSession(None, SESSION_STATUS_NOT_FOUND, None)` when `repo.get(session_id)` raises `KeyError`
  - `RestoredSession(None, SESSION_STATUS_AGENT_DELETED, db_session)` when `factory.create(agent_name_for_factory)` raises `KeyError("Unknown agent: ...")` (the `_load_config` branch — agent config not found). Note that if `db_session.agent_name` is empty/None we fall back to `"default"`; if even the default config goes missing this triggers `agent_deleted` — that's a corrupt-installation edge case but the classification is correct.
  - `RestoredSession(None, SESSION_STATUS_PROVIDER_MISSING, db_session)` when `factory.create(...)` raises `ValueError("...has no provider configured...")` OR raises `KeyError("Provider not found: ...")` from the provider repo lookup. Distinguish the two `KeyError` sources by message-substring match (`"Provider not found"` → provider_missing, `"Unknown agent"` → agent_deleted) — there is no exception type hierarchy that makes this cleaner without a refactor of `factory.py` that's out of scope. The implementation MUST include a code comment listing the three exact source sites being matched (`factory.py:102`, `factory.py:39-43`, `repositories.py:401`) so future refactors of those messages are caught at code-review time.
  - `RestoredSession(session, SESSION_STATUS_OK, db_session)` on success — the session is also stored in `_sessions` (existing cache behavior preserved)
  - Any unrecognized `ValueError` from `factory.create` (one whose message does NOT contain "has no provider configured") MUST propagate, not be misclassified.
- [x] **The fallback at app.py:154-161 (the `agent = await factory.create("default")` block) is removed.** A `logger.warning` call for each degraded state is acceptable and encouraged — log the session id, agent name, and status so operators can correlate.
- [x] When `_restore_session` returns a degraded status, no entry is added to `_sessions` (the degraded session has no functional Agent, and caching it would mask future health changes).
- [x] `_get_or_restore_session(session_id) -> RestoredSession`:
  - For `session_id in _sessions`: returns `RestoredSession(_sessions[session_id], SESSION_STATUS_OK, None)`
  - Otherwise delegates to `_restore_session`
- [x] WS `join` action sends a `session_joined` payload that includes a `status` field for ALL four cases. Schema:
  ```json
  {
    "type": "session_joined",
    "session_id": "<sid>",
    "status": "ok" | "agent_deleted" | "provider_missing",
    "title": "<from session or db_session>",
    "agent_name": "<from session or db_session>",
    "history": [<ui events>]
  }
  ```
  (Note: `not_found` is never sent — it's resolved server-side into either `ok` for a freshly-created session or by reusing the already-bound `session`, see next AC.)
  For `agent_deleted` and `provider_missing`: `history` is built by decoding `db_session.messages` and calling `messages_to_ui_events(...)` (same helpers `_restore_session` uses on the OK path).
- [x] WS `join` action handles three sub-cases for the `session_id` field, preserving today's semantics for the no-session_id paths:
  1. **`session_id` is provided** → call `_get_or_restore_session(session_id)`. If `restored.status == "ok"`: re-emit session_joined for the restored session. If degraded: emit session_joined with degraded status and set local `session = None`. If `not_found`: fall through to step 3 (auto-create).
  2. **`session_id` is missing AND outer `session` is already bound** (the user is rebinding to the existing connection's session) → re-emit session_joined for the existing `session` with `status: "ok"`. Do NOT auto-create. **This preserves today's behavior** where bare `{"action": "join"}` on an already-joined connection is idempotent.
  3. **`session_id` is missing AND outer `session` is None** → auto-create via `_create_session()` and emit session_joined with `status: "ok"`.
- [x] After a degraded join, the WS handler MUST set the outer `session` variable to `None` (not the `RestoredSession` dataclass) so subsequent message actions in the same WS connection don't accidentally operate on a degraded session.
- [x] HTTP `/api/chat`:
  - `not_found` (i.e. session_id provided but missing): preserves current fall-through to `_create_session`
  - `agent_deleted` / `provider_missing`: returns `{"error": "session_<status>"}` and does NOT auto-create a new session. **This is an intentional behavior change for the Concourse autopilot** (see "Accepted external breakage" in Context).
  - `ok`: unchanged
- [x] `new_session` and `_create_session` are NOT modified — they continue to raise `ValueError` / `KeyError` on invalid agent specs.
- [x] The bare-message auto-join path (around line 599-613) is NOT modified — fresh sessions skip health checks (they can't be degraded by definition).
- [x] No new top-level imports needed. `dataclass` is already imported on `app.py:7`. `ChatSessionModel` is already imported as an alias on `app.py:23` (`from the_one.db.models import ChatSession as ChatSessionModel`) — use the existing alias, do NOT add a new import. `decode_messages` and `messages_to_ui_events` are already used inside `_restore_session`. If implementing with `Literal` instead of bare string constants, that DOES require adding `Literal` to the existing `typing` import.
- [x] All existing tests in `tests/test_session_lifecycle.py` pass after being updated for the new return shape.
- [x] New tests in `tests/test_session_lifecycle.py` cover:
  - `_restore_session` returns `agent_deleted` when the agent_name in the DB session refers to a non-existent agent config (mock the factory to raise `KeyError("Unknown agent: ...")`)
  - `_restore_session` returns `provider_missing` when the factory raises `ValueError("...has no provider configured...")`
  - `_restore_session` returns `provider_missing` when the factory raises `KeyError("Provider not found: ...")`
  - `_restore_session` returns `not_found` when the session_id is unknown
  - `_restore_session` does NOT cache degraded sessions in `_sessions`
  - `_restore_session` does NOT call `factory.create("default")` after a `KeyError("Unknown agent: ...")` — regression guard against re-introducing the silent fallback. Use `mock.create.assert_called_once_with("missing-agent")` or equivalent.
  - `_restore_session` propagates an unrecognized `ValueError` (e.g. `ValueError("something unexpected")`) instead of misclassifying as `provider_missing`.
  - `_get_or_restore_session` returns `ok` for cached sessions without re-running health checks (e.g. patch the factory to raise after caching — cached call must still return ok).
  - Note: the "default agent config goes missing" corruption case (described in Edge Cases) does NOT require its own test — it's an unreachable corner of the state space. The `agent_deleted` test using `KeyError("Unknown agent: missing-agent")` already exercises the classification path.
- [~] `ruff check` and `ruff format --check` clean for `the_one/interfaces/web/app.py` and `tests/test_session_lifecycle.py`. — `ruff check` clean for both; `ruff format --check` clean for `tests/test_session_lifecycle.py`. For `app.py`, `ruff format --check` reports preexisting drift in regions not touched by this leg; per implementation-guidance step 8 ("only check, don't aggressively reformat unrelated regions") this was left for leg 04. See flight-log Deviations.

## Verification Steps

- `pytest tests/test_session_lifecycle.py -v` — all existing + new tests pass
- `pytest -q` — full suite passes (excluding the 2 known pre-existing collection errors)
- `ruff check the_one/interfaces/web/app.py tests/test_session_lifecycle.py`
- Manual smoke (deferred to HAT leg, not required here): no manual verification needed in this leg — the frontend can't render the new statuses yet.

## Implementation Guidance

1. **Add the dataclass and status constants** at the top of `app.py` (near the existing `Session` dataclass declaration around line 80):
   ```python
   SESSION_STATUS_OK = "ok"
   SESSION_STATUS_NOT_FOUND = "not_found"
   SESSION_STATUS_AGENT_DELETED = "agent_deleted"
   SESSION_STATUS_PROVIDER_MISSING = "provider_missing"

   @dataclass
   class RestoredSession:
       """Result of attempting to restore a session, with health classification.

       For ok-cache hits, db_session is None (we don't re-query the DB).
       For degraded states (agent_deleted, provider_missing), session is None
       and db_session carries the row so the caller can render history.
       """
       session: Session | None
       status: str
       db_session: ChatSessionModel | None = None

       @property
       def is_degraded(self) -> bool:
           return self.status in (SESSION_STATUS_AGENT_DELETED, SESSION_STATUS_PROVIDER_MISSING)
   ```
   `dataclass` is already imported on `app.py:7` — no import change needed. `ChatSessionModel` is already imported on `app.py:23` as an alias (`from the_one.db.models import ChatSession as ChatSessionModel`); use that alias as-is.

2. **Rewrite `_restore_session`** in `the_one/interfaces/web/app.py`:
   ```python
   async def _restore_session(session_id: str) -> RestoredSession:
       """Load a session from DB into memory, classifying its health on the way."""
       try:
           repo = await _chat_repo()
           db_session = await repo.get(session_id)
       except KeyError:
           return RestoredSession(None, SESSION_STATUS_NOT_FOUND, None)

       factory = _get_factory()
       agent_name_for_factory = db_session.agent_name or "default"
       try:
           agent = await factory.create(agent_name_for_factory)
       except KeyError as exc:
           # Two possible KeyError sources from factory.create:
           #   - "Unknown agent: ..."         from factory.py:102 (_load_config)
           #   - "Provider not found: ..."    from db/repositories.py:401 (LLMProviderRepository.get)
           # If any of those messages change, this branch will silently misclassify;
           # update both sites together.
           msg = str(exc)
           if "Provider not found" in msg:
               status = SESSION_STATUS_PROVIDER_MISSING
           else:
               status = SESSION_STATUS_AGENT_DELETED
           logger.warning(
               "Session %s degraded: status=%s agent=%r exc=%s",
               session_id, status, db_session.agent_name, exc,
           )
           return RestoredSession(None, status, db_session)
       except ValueError as exc:
           # AgentFactory raises ValueError("Agent '...' has no provider configured...")
           # at factory.py:39-43 when the agent has no provider_config_id.
           if "has no provider configured" in str(exc):
               logger.warning(
                   "Session %s degraded: status=provider_missing agent=%r",
                   session_id, db_session.agent_name,
               )
               return RestoredSession(None, SESSION_STATUS_PROVIDER_MISSING, db_session)
           raise  # Unrecognized ValueError — surface it; do NOT classify as degraded.

       # Build the ok-path session as before
       messages = decode_messages(db_session.messages)
       if messages:
           agent.messages = messages
       ui_events = messages_to_ui_events(messages)
       session = Session(
           id=session_id,
           agent=agent,
           created=db_session.created_at,
           title=db_session.title,
           agent_name=db_session.agent_name,
           history=ui_events,
       )
       _sessions[session_id] = session
       return RestoredSession(session, SESSION_STATUS_OK, db_session)
   ```
   Notice the silent fallback (`agent = await factory.create("default")`) is gone — that's the load-bearing change. Do not preserve any version of it.

3. **Rewrite `_get_or_restore_session`**:
   ```python
   async def _get_or_restore_session(session_id: str) -> RestoredSession:
       """Check memory first, fall back to DB restore."""
       if session_id in _sessions:
           return RestoredSession(_sessions[session_id], SESSION_STATUS_OK, None)
       return await _restore_session(session_id)
   ```

4. **Update the WS join handler** (lines 510-529 today). The existing code has subtle behavior for the "no session_id" case that MUST be preserved: if the user sends `{"action": "join"}` with no session_id while already attached to a session, the handler re-emits session_joined for the existing session (idempotent re-bind). The proposed implementation must handle this case explicitly. A small helper makes the structure clearer:
   ```python
   def _build_session_joined_ok(session: Session) -> dict[str, Any]:
       return {
           "type": "session_joined",
           "session_id": session.id,
           "status": SESSION_STATUS_OK,
           "title": session.title,
           "agent_name": session.agent_name,
           "history": session.history,
       }

   def _build_session_joined_degraded(restored: RestoredSession) -> dict[str, Any]:
       db = restored.db_session
       assert db is not None
       return {
           "type": "session_joined",
           "session_id": db.id,
           "status": restored.status,
           "title": db.title,
           "agent_name": db.agent_name,
           "history": messages_to_ui_events(decode_messages(db.messages)),
       }
   ```
   Then the handler:
   ```python
   if action == "join":
       session_id = payload.get("session_id")

       if session_id:
           restored = await _get_or_restore_session(session_id)
           if restored.status == SESSION_STATUS_OK:
               # 'session' here is the WS-loop-scoped variable;
               # restored.session is the dataclass field.
               session = restored.session
               if ws not in session.subscribers:
                   session.subscribers.add(ws)
               await ws.send_json(_build_session_joined_ok(session))
               continue
           if restored.is_degraded:
               session = None  # don't operate on a degraded session
               await ws.send_json(_build_session_joined_degraded(restored))
               continue
           # status == not_found → fall through to auto-create below
       elif session is not None:
           # No session_id supplied AND outer session is already bound —
           # preserve today's idempotent re-bind behavior.
           if ws not in session.subscribers:
               session.subscribers.add(ws)
           await ws.send_json(_build_session_joined_ok(session))
           continue
       # else: no session_id AND no outer session → auto-create below.

       # Auto-create: either no session_id was supplied AND no outer session,
       # or the supplied session_id was not_found.
       try:
           session = await _create_session()
       except (ValueError, KeyError) as exc:
           await ws.send_json({"type": "system", "content": f"Cannot start chat: {exc}"})
           continue
       if ws not in session.subscribers:
           session.subscribers.add(ws)
       await ws.send_json(_build_session_joined_ok(session))
       continue
   ```
   Place the two helpers as **module-level functions** near `_send_to_session` (around line 209). They are pure data shapers with no closure dependencies — module-level keeps the WS handler concise and makes the payload shape unit-testable. The `Any` type already exists in app.py imports.

5. **Update HTTP `/api/chat`** (lines 440-476). Today:
   ```python
   if session_id:
       session = await _get_or_restore_session(session_id)
   if session is None:
       try:
           session = await _create_session(...)
       except (ValueError, KeyError) as exc:
           return {"error": f"Cannot start chat: {exc}"}
   ```
   New:
   ```python
   session: Session | None = None
   if session_id:
       restored = await _get_or_restore_session(session_id)
       if restored.status in (SESSION_STATUS_AGENT_DELETED, SESSION_STATUS_PROVIDER_MISSING):
           return {"error": f"session_{restored.status}"}
       session = restored.session  # None for not_found, real Session for ok
   if session is None:
       try:
           session = await _create_session(agent_name=agent_name, source=source, session_id=session_id)
       except (ValueError, KeyError) as exc:
           return {"error": f"Cannot start chat: {exc}"}
   ```

6. **Update `tests/test_session_lifecycle.py`**:
   - In every existing test that calls `_restore_session` or `_get_or_restore_session`, change `restored = await ...` to `result = await ...; restored = result.session; assert result.status == "ok"` (or equivalent — update assertions accordingly).
   - The `patched_app` fixture's `mock_factory_create` always returns a fake agent — the existing tests don't trigger degraded states. For the new tests, build dedicated sub-fixtures or use `unittest.mock.patch.object` on `mock_factory.create` within the test body to inject the right exception:
     ```python
     async def test_restore_returns_agent_deleted(self, patched_app, chat_repo):
         await patched_app._create_session(session_id="orphan", agent_name="missing-agent")
         # Reach into the patched factory and override .create to raise
         patched_app._get_factory.return_value.create = AsyncMock(
             side_effect=KeyError("Unknown agent: missing-agent")
         )
         del patched_app._sessions["orphan"]

         result = await patched_app._restore_session("orphan")
         assert result.session is None
         assert result.status == "agent_deleted"
         assert result.db_session is not None
         assert "orphan" not in patched_app._sessions
     ```
     Adjust the patching to match the actual fixture structure. Read the fixture carefully — it patches `_get_factory` to return an `AsyncMock`, and calls `mock_factory.create = mock_factory_create` (a plain async function, not a Mock). To override per-test, you need to assign `.create` on the same mock object the fixture patched.
   - For `provider_missing`-via-`ValueError`: `side_effect=ValueError("Agent 'foo' has no provider configured. ...")`
   - For `provider_missing`-via-`KeyError`: `side_effect=KeyError("Provider not found: abc123")`
   - For "cached session bypasses health check": create a session normally, then patch `_get_factory().create` to raise, then call `_get_or_restore_session(session_id)` — assert `status == "ok"` because the cache returns the in-memory session without consulting the factory.

7. **Run tests**: `pytest tests/test_session_lifecycle.py -v --timeout=30` first (fast feedback). Then `pytest -q` for the full suite.

8. **Run ruff** on the two touched files. The `app.py` file is large — only check, don't aggressively reformat unrelated regions.

9. **Update flight log** with a Leg Progress entry plus these explicit Decisions:
   - **Concourse autopilot (`ci/pipeline.yml`) accepts the new degraded-error response as breaking.** The pipeline's `urllib.urlopen` will get 200 OK with `{"error": "session_<status>"}` and `messages: []` — surface this in pipeline error handling in a follow-up, or recreate the autopilot session via `new_session` with a valid agent. Out of scope for this leg.
   - **Cached sessions are not re-health-checked.** Per the design decision, health is a join-time concept. If a provider is deleted mid-conversation, the next LLM call will fail with whatever raw error the provider raises; the user will not see a banner. Acceptable trade-off — re-classification on send-time errors is out of scope for this leg.

## Edge Cases

- **`db_session.agent_name is None`**: This is the "default agent" path. `agent_name_for_factory = "default"`. If `factory.create("default")` somehow raises `KeyError("Unknown agent: default")`, that's a corrupt installation — surface as `agent_deleted` (default agent shouldn't go missing, but the state machine handles it correctly).
- **`db_session.agent_name` set but agent config exists, just provider was deleted**: `factory.create(name)` enters the agent-loading path, gets a config, then fails at `provider_repo.get(provider_config_id)` with `KeyError("Provider not found")`. Classified as `provider_missing`. Verified above.
- **Agent config has `provider_config_id is None`**: `factory.create` raises `ValueError("Agent ... has no provider configured")` early (factory.py:39-43), before the provider_repo lookup. Classified as `provider_missing`.
- **Race: provider deleted between health check and message send**: Out of scope. The user joins, sees status=ok, and starts typing. If the provider is deleted at that instant, the next LLM call fails. Existing error handling catches it. Not addressed by this leg.
- **Cached session whose underlying agent has since been deleted**: `_get_or_restore_session` returns the cached `Session` with `status: "ok"`. The agent object itself is still functional in-memory. If the user sends a message, the LLM call may fail (provider no longer reachable). This is intentional — design decision says health is checked at join time, not on every cached read.
- **Auto-join path on bare message** (lines 599-613): unchanged. If a user sends a message without joining first, we auto-create a fresh session — current semantics preserved. Don't add health logic here.
- **`_create_session` with explicit `session_id` matching a deleted-agent session**: Out of scope. The HTTP endpoint and WS `new_session` handler call `_create_session` directly; if the user supplies an `agent_name` of a deleted agent, factory raises and the existing `except (ValueError, KeyError)` branches catch it. This leg does not unify those paths.

## Files Affected

- `the_one/interfaces/web/app.py` — add `RestoredSession` dataclass + status constants; rewrite `_restore_session` and `_get_or_restore_session`; update WS `join` handler; update HTTP `/api/chat` handler. **Net diff: ~80 lines changed/added.**
- `tests/test_session_lifecycle.py` — update ~6 existing tests to unwrap the new dataclass; add 5+ new tests covering degraded states and cache-bypass-of-health-check. **Net diff: ~120 lines changed/added.**

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`pytest tests/test_session_lifecycle.py -v` green; `pytest -q` green except the 2 known pre-existing collection errors)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off the leg in flight.md yet — that happens at flight commit
- [x] Do NOT commit — Mission Control batches review and commit at end of flight
