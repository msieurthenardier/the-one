# Leg: fresh-cache

**Status**: completed
**Flight**: [Live Chats list and connector chats](../flight.md)

## Objective
A web turn on a chat whose stored content changed since the server cached it (a connector turn, a REST rename or purge) re-syncs the cached agent from the database first, so it never writes stale history over the other writer's messages; and the browser test apparatus that drives a real connector turn through the stub seam exists and is proven.

## Context
- Sortie DD4 (fingerprint re-sync under the lock) and DD8 (stub-seam apparatus). Charter criterion 3.
- Root cause: `_locked_message_processing` (`the_one/interfaces/web/app.py`, "The lock + `_process_and_broadcast` body") runs the turn on the `Session` cached at join time; `_save_session_to_db` then writes `session.agent.messages` and `session.title` whole. `dispatch_inbound` (`the_one/connectors/inbound.py`) takes the same `session_locks[id]`, reads the row, runs its own turn and `chat_repo.update`s it. So the lock serializes the two writers, but the web side never sees the connector's write.
- No later leg depends on internals here except the fixture/seeders (legs 2 and 3 reuse them).
- Architect review 2 confirmed `_save_session_to_db`'s `model_copy(update=...)` does not validate and `ChatSessionRepository.update` binds `messages` verbatim, so the bytes the web hashes are the bytes stored; `_row_to_model` normalises on read (`title or "New chat"`, `messages or "[]"`).

## Inputs
- Worktree `.claude/worktrees/sortie-live-chats-list` on branch `sortie/05-live-chats`, with its own `.venv` (re-verify: `.venv/bin/python -c "import the_one; print(the_one.__file__)"` prints a path under the worktree).
- `POST /api/_test/stub/inbound` (`api.py::stub_test_inbound`), dual-gated on `THE_ONE_DEV_MODE=true` + `THE_ONE_STUB_TEST_ENDPOINT=1`; returns 409 while the stub account is not connected (`StubPlugin.push_inbound` raises `ConnectorClientError`). The POST blocks for the whole connector turn.
- `tests/browser/conftest.py::_spawn_app(tmp_path, extra_env=...)`; `seeders.seed_mock_provider`/`seed_mock_agent`; `seeders.seed_connector` (today: a DISABLED discord connector only).
- Lifespan startup registers `StubPlugin` under type `"stub"` when both gates are open.

## Outputs
- `Session` carries `db_fingerprint`; a web turn re-syncs a stale cache before running.
- A stub-connector browser fixture + seeder, and `tests/browser/test_flow_chat_live_updates.py` with the criterion-3 test.
- Unit tests for the re-sync.

## Acceptance Criteria
- [ ] `the_one/interfaces/web/app.py` has `_fingerprint(messages: str | None, title: str | None) -> str`, a hash of `messages or "[]"` and `title or "New chat"` (the same defaults `_row_to_model` applies on read), so a value written and the same value read back are equal by construction.
- [ ] `Session` has `db_fingerprint: str | None = None`. It is set: in `_restore_session` (both the in-place update branch and the new-`Session` branch) from the same `db_session` read the history is built from; in `_create_session` from the `messages`/`title` of the row it creates; in `_save_session_to_db` from the exact `encoded` messages and title it passes to `repo.update`, only after `repo.update` returns (no read-back).
- [ ] `_locked_message_processing`, after acquiring `session_locks[session.id]` and before `_process_and_broadcast`, and before `current_chat_session_id.set(...)` (outside the `try`/`finally` that resets that token), calls a re-sync helper inside its own `try/except Exception` (log a warning, proceed unsynced; `CancelledError` is not caught and propagates). The helper: `session.db_fingerprint is None` → return at once with no read and no change (no baseline: bare test Sessions, and a non-strict create whose row never landed); otherwise it reads the row: `KeyError` → no change; fingerprint equal → no change and no further work; different → `session.agent.messages = session.agent.messages[:1] + <row's non-system messages>` (decoded with `decode_messages`, the same rule `_restore_session` uses), `session.history = messages_to_ui_events(<row messages>)`, `session.title = <row title>`, `session.db_fingerprint = <row fingerprint>`.
- [ ] The re-sync runs even when the agent is paused for auth (no `_deferred_tool_calls` skip): `Agent.step` clears the deferral at its start (`the_one/agent/core.py`, the `self._deferred_tool_calls = None` in `step`).
- [ ] Unit tests (new file `tests/test_web_session_resync.py`, database from `tests/_schema_template.py`, never `ensure_schema`/`init_db`): (0) a `None` fingerprint with a differing row replaces nothing; (a) a stored row changed by another writer after the cache was built is re-synced, and the subsequent save keeps the other writer's messages; (b) an equal fingerprint performs no message replacement; (c) a missing row leaves the session unchanged; (d) a re-sync read that raises (non-`KeyError`) does not stop `_process_and_broadcast` from running; (e) `_fingerprint` of the values `_save_session_to_db` writes equals `_fingerprint` of the row read back through `ChatSessionRepository.get`, including an empty title; (f) at least one test drives the real `_locked_message_processing` path (not only the helper) against a real template DB, with a scripted provider (`FakeLLM`-style), the other writer's change made through `ChatSessionRepository.update` on a `model_copy` of the row with only `messages` changed (as `dispatch_inbound` does), to show it survives the web turn's save; (g) a `CancelledError` raised by the re-sync read propagates.
- [ ] Browser apparatus: a fixture (in `tests/browser/conftest.py`, or the new test file if it is the only user) that spawns the app with `extra_env={"THE_ONE_STUB_TEST_ENDPOINT": "1"}`, seeds a mock provider and a mock agent, and creates an **enabled** `stub` connector whose `default_agent` is that agent and whose `allowlist.peers` holds the test peer; a seeder for that connector (a separate `seed_stub_connector` in `tests/browser/seeders.py`; `seed_connector` stays as it is). The fixture registers and unregisters its credential and tears the process down like the existing app fixtures (`_unregister_credential`, `_teardown_proc`); a helper that posts to `/api/_test/stub/inbound` and waits (bounded, ~15 s) through 409s until the stub account is connected.
- [ ] Browser test in `tests/browser/test_flow_chat_live_updates.py` (`@pytest.mark.browser`; navigation through `_nav`/`_chats`/`_lists`, no raw route hashes, no retired selectors): a first inbound DM creates the connector chat; the browser opens it (navigation or reload is fine in this leg: the live list is leg 2); a second inbound DM runs a connector turn while the chat is open; the browser sends a message and waits for the turn to finish; `GET /api/chat/sessions/{id}` (with `auth_headers_for`) shows, by content, both inbound texts, the connector turn's mock reply and the browser's message in the stored history. The test fails on the base commit (verified by temporarily disabling the re-sync, then restored).
- [ ] The new test file runs in the `chats` lane (`bash scripts/run-tests.sh --lane chats --list` lists it).
- [ ] `the_one/agents.md` documents the re-sync (where the chat web session cache is described) in a short paragraph: the fingerprint, where it is set, the turn-start re-sync, the `None` = no baseline rule, and the recorded known edges (a write landing between `_restore_session`'s read and its cache update leaves an older fingerprint, so the next turn re-syncs: benign; resume-after-auth runs without the lock; REST `/api/chat` has no re-sync; a second tab's re-join drops a pending deferral).
- [ ] `make test-unit` passes (12 skipped expected on this host, 14 under `THE_ONE_TEST_NETNS=1`; read `-rs` before treating another count as drift); the `chats` lane passes with `THE_ONE_TEST_NETNS=1`.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_web_session_resync.py -x --timeout 30`
- `make test-unit PYTHON=.venv/bin/python` (or `PYTHON=.venv/bin/python bash scripts/run-tests.sh -x --timeout 60`), note the skip count.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh -m browser tests/browser/test_flow_chat_live_updates.py -x`
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -x`
- Falsification: comment out the re-sync call, re-run the browser test and test (f), confirm both fail, restore. Record in the flight log.

## Implementation Guidance

1. **Fingerprint and marker** (`app.py`)
   - `_fingerprint` with `hashlib.sha256` over `(title or "New chat")` + a separator + `(messages or "[]")`; return the hexdigest.
   - Add the field to the `Session` dataclass (it is `@dataclass` with defaults; keep the default `None`).
   - `_restore_session`: set it from `db_session.messages`/`db_session.title` in both branches. Do not re-read the row.
   - `_create_session`: set it from the `ChatSessionModel` it builds (`messages="[]"`, `title=session.title`).
   - `_save_session_to_db`: after `await repo.update(updated)` succeeds, `session.db_fingerprint = _fingerprint(encoded, session.title)`. Leave the existing broad `except` as is.

2. **Re-sync helper** (`app.py`)
   - e.g. `async def _resync_session_from_db(session: Session) -> None`, near `_restore_session`. Uses `_chat_repo()`. Keep the agent's system message (`session.agent.messages[:1]`), as `_restore_session` does.
   - Call it from `_locked_message_processing` right after `async with session_locks[session.id]:` and the `last_activity` touch, wrapped in its own `try/except Exception: logger.warning(..., exc_info=True)`. It must be outside the existing `try` that catches `Exception` and sends "An error occurred", or inside its own inner `try`, so a failed read never skips the turn.
   - Many existing unit tests drive `_spawn_message_processing`/`_process_and_broadcast` with a bare `Session` and no row (e.g. `tests/test_cancel.py`). The helper must be a no-op for them (`KeyError` path, or the guarded exception path), never a failure. Run those files.

3. **Unit tests** (`tests/test_web_session_resync.py`)
   - Use the patterns in existing web-session tests (grep `tests/` for `_restore_session(` and `_locked_message_processing(` / `_spawn_message_processing(` callers) and `tests/conftest.py`'s `FakeLLM`. Build the database with `tests/_schema_template.py`.

4. **Browser apparatus**
   - Read `tests/browser/conftest.py`'s `_spawn_app`, `app_clean`, `app_with_provider`, `app_with_agent` and `tests/browser/seeders.py`. Mirror `app_with_agent`, adding `extra_env`.
   - Connector create: `POST /api/connectors` with `type: "stub"`, `config: {enabled: true, default_agent: <agent>, allowlist: {peers: [<peer>], channels: []}}` and a dummy token (see `tests/test_connector_routes.py::_stub_payload` for the accepted shape). Confirm against the route's validation.
   - Inbound helper: `httpx.post(f"{base}/api/_test/stub/inbound", json={"connector_id", "peer_id", "peer_name", "text", "is_dm": True}, headers=auth_headers_for(base), timeout=...)`, retrying on 409 until connected. The chat a DM creates is titled `DM: <peer_name>` (see `inbound.py::_session_title`); find its id via `GET /api/chat/sessions`.
   - The mock agent's reply text is the mock provider's default ("Mock response from the mock provider.") unless the seeder sets a response.

5. **Docs**: one paragraph in `the_one/agents.md` (find the section that describes `_restore_session` / the web `Session` cache). Do not touch CLAUDE.md in this leg.

## Edge Cases
- **Bare `Session` with no row** (unit tests, a chat deleted meanwhile): no change, turn runs.
- **`start_session` first turn**: the session is cached before `repo.create` lands; its fingerprint is set from the row it creates, so the first turn finds it equal (or `KeyError` if the create has not landed yet: no change). Never re-sync to an empty history over the optimistic first turn.
- **`/reset`**: writes through `_save_session_to_db`, so the marker follows it.
- **An empty stored title** (REST PUT): `_fingerprint` normalises it, so no spurious re-sync each turn.
- **`platform` / `session_metadata`**: not refreshed by the re-sync (out of scope; restore already sets them for a joined connector chat).
- **Patched repos in existing tests** returning a `MagicMock` row: the guarded `except` absorbs the `TypeError` with a warning. Run every file that drives the turn path (`test_last_usage_persistence`, `test_last_usage_round_trip`, `test_self_configuration_write`, `test_notes_tools`, `test_auto_load`, `test_streaming`, `test_cancel`, `test_ws_*`, `test_app_websocket_pause_resume`, `test_process_and_broadcast_*`) and check none asserts no warnings; the `None` rule keeps bare Sessions from reaching the read at all.
- **Cancellation**: the re-sync runs before the turn; a `CancelledError` while awaiting the read must propagate (do not swallow `BaseException`; `except Exception` does not catch `CancelledError`).

## Files Affected
- `the_one/interfaces/web/app.py` - `_fingerprint`, `Session.db_fingerprint`, set sites, `_resync_session_from_db`, the call in `_locked_message_processing`
- `tests/test_web_session_resync.py` - new unit tests
- `tests/browser/conftest.py` and/or `tests/browser/seeders.py` - stub-connector fixture, seeder, inbound helper
- `tests/browser/test_flow_chat_live_updates.py` - new browser test (criterion 3)
- `the_one/agents.md` - re-sync paragraph

## Citation Audit
Checked against the worktree at `08562ec`: `_locked_message_processing` takes `session_locks[session.id]` and wraps `_process_and_broadcast` in `try/except Exception` that sends "An error occurred while processing your message."; `_save_session_to_db` `model_copy(update={"title", "messages": encoded})` then `repo.update`; `_restore_session` builds `ui_events` from `decode_messages(db_session.messages)` and updates a cached Session in place under `_sessions_lock`; `_create_session` builds `ChatSessionModel(..., messages="[]")` and `repo.create`s it after caching; `dispatch_inbound` takes `session_locks[session_row.id]` and ends with `chat_repo.update(updated)`; `stub_test_inbound` maps `ConnectorClientError` to 409; `_spawn_app` accepts `extra_env`. All verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
