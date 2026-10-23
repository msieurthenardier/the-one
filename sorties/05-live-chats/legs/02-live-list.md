# Leg: live-list

**Status**: completed
**Flight**: [Live Chats list and connector chats](../flight.md)

## Objective
Every write that changes what the Chats list shows raises one in-process signal from the db layer; the web app coalesces those signals and pushes a `sessions_changed` frame with the full list to every connected WebSocket; the browser primes its lists from a push and does nothing else, so an open Chats list follows connector chats, other tabs, deletes and purges without moving the user.

## Context
- Sortie DD1 (signal), DD2 (registry, summary read, coalesced push, shutdown order), DD3 (client priming), DD7 (docs). Charter criteria 1 and 4.
- Leg 1 (`fresh-cache`) built the stub-connector browser fixture, `seed_stub_connector` and the inbound helper in `tests/browser/` and created `tests/browser/test_flow_chat_live_updates.py`; this leg adds tests to that file and reuses the apparatus. Read the flight log's `fresh-cache` entry first for what actually landed (names, fixture shape, timings).
- Today the server sends `session_list` only in reply to `list_sessions` (`app.py::websocket_endpoint`, the `if action == "list_sessions":` branch); the client asks only after its own actions (`chat.js::refreshSessionList` and `sock.onopen`).
- The client's `session_list` handler runs the first-socket rebind and `runIdleRules()`; the idle rules auto-open `sessions[0]` while idle (`session-state.js::idleRules`). A push must never reach them.

## Inputs
- Leg 1 landed (apparatus + `Session.db_fingerprint` re-sync; `app.py` already modified in the working tree; do not revert any of it).
- `the_one/sessions/_broadcast.py` (`add_subscriber`, `broadcast_to_session`, `clear_subscribers_for_test`), `the_one/sessions/__init__.py`.
- `ChatSessionRepository` (`the_one/db/repositories.py`) and the agent rename `UPDATE chat_sessions SET agent_name = ?` in `SQLiteAgentStore`.
- The lifespan in `app.py` (`async def lifespan`: startup, `yield`, then the drains; `close_connection()` last).

## Outputs
- `the_one/db/_session_changes.py` (new), repository notify calls, `ChatSessionRepository.list_summaries()`.
- Socket registry + `broadcast_to_all` in `the_one/sessions/_broadcast.py`; registration in `websocket_endpoint`; the coalescing listener in the lifespan.
- `chat.js` `sessions_changed` branch and shared mapping helper; `session-state.js` gate; `renderChatsList` starting-row filter.
- Unit tests, browser tests, docs.

## Acceptance Criteria
- [ ] `the_one/db/_session_changes.py` (stdlib only): `add_listener(fn)`, `remove_listener(fn)`, `notify_sessions_changed()` (calls every listener, each inside `try/except Exception` with `logger.exception`; never raises; no-op with no listener), `clear_for_test()`. `tests/test_imports.py`'s first-touch module list gains `the_one.db._session_changes`.
- [ ] `ChatSessionRepository.create`, `update`, `delete`, `delete_all_for_agent` (only when it deleted rows), `delete_older_than` (only when it returns a non-empty list), `purge_messages` and `update_last_inbound` call `notify_sessions_changed()` once, after their `async with write_transaction(...)` block has exited; `SQLiteAgentStore`'s rename does the same after its block. `append_to_session_metadata` and `set_session_metadata_key` do not. A call that raises (e.g. `KeyError` on a missing row) does not notify.
- [ ] `ChatSessionRepository.list_summaries()` returns `ChatSession` models in `list()`'s order (`updated_at DESC`) without reading `messages` or `session_metadata` (select the other columns plus `NULL AS messages, NULL AS session_metadata`, reusing `_row_to_model`, which defaults `messages` to `"[]"`), so `_session_to_list_payload` applies unchanged.
- [ ] `the_one/sessions/_broadcast.py`: `add_socket(ws)`, `remove_socket(ws)`, `all_sockets()` (snapshot copy), `async broadcast_to_all(payload)` (skips/discards a socket whose send raises, and removes it from the registry), cleared by `clear_subscribers_for_test()`; exported from `the_one/sessions/__init__.py`.
- [ ] `websocket_endpoint` calls `add_socket(ws)` right after `await ws.accept()` and `remove_socket(ws)` in a `finally` that covers every exit of the receive loop (the existing `except WebSocketDisconnect` body stays as it is).
- [ ] The lifespan, at startup, registers one listener that captures the running loop. A signal arms a trailing push ~250 ms later (one pending push at a time; later signals inside the window fold in; "on the loop's thread" is decided by comparing `asyncio.get_running_loop()` (inside `try/except RuntimeError`) with the captured loop; otherwise `loop.call_soon_threadsafe`, where a `RuntimeError` or `loop.is_closed()` means a closed loop and the signal is ignored; the listener has a `closed` flag set at removal, and a queued `schedule` callback that runs after it is set does nothing). On fire, the task first clears `pending`, then reads, so a signal arriving during the read arms a new push and no write is lost: no sockets → no DB read; else one `list_summaries()` read, then `broadcast_to_all({"type": "sessions_changed", "sessions": [_session_to_list_payload(s) ...]})`; a failed read logs a warning and sends nothing. At shutdown, the listener is removed **first**, immediately after `yield` (before the ollama/PTY/in-flight-task drains), and any pending push task/timer is cancelled and awaited before `close_connection()`.
- [ ] Unit tests (new `tests/test_session_changes.py` and/or additions to an existing WS test file; databases from `tests/_schema_template.py`): every listed repository method notifies exactly once on success and the listener can read the committed row back; metadata methods and failing calls do not notify; `delete_older_than` with nothing to delete does not notify; the rename notifies; `list_summaries()` matches `list()`'s ids, order and projected payload; the coalescer folds N signals inside the window into one `list_summaries` read and one frame per socket; a signal arriving during the read arms a second push; a signal after removal (including a queued callback) pushes nothing; `list_summaries()` on a row whose `messages` holds a sentinel returns models with `messages == "[]"`; zero sockets → no read; a failed read sends nothing; a dead socket is discarded; listener removal stops pushes.
- [ ] `chat.js`: one shared helper maps server rows to the REST summary shape (`id`, `agent_name`, `title`, `created_at`, `updated_at`, `platform: s.platform || null`) and both the `session_list` reply and the new `sessions_changed` branch prime `App.store` (`sessions`) through it. The `sessions_changed` branch sets the local `sessions` array, primes the store, and returns: it does not touch `listSeen`, `firstListPending`, `rebinding`, or call `runIdleRules()`, `renderChatsList()`, `openConversation`, `App.router.go/sync`, or anything on the composer.
- [ ] `session-state.js::accepts` returns true for `sessions_changed` in every state, and `onFrame` returns `{ accept: true }` for it. `tests/browser/test_flow_chat_session_state.py::test_frame_gate` adds `sessions_changed` to its always-accepted side so the rule is pinned in all five states.
- [ ] `renderChatsList` omits a listed row whose id equals the starting `clientId` while the state is `starting` (the pending row stands for it). The filter sits before the `App.chat.chatsList.PENDING_ID` reference and uses only deeper-indented braces, so `test_chats_list_renders_from_the_sessions_subscription_only`'s window (up to the first `"\n    }"`) still holds its pins.
- [ ] `tests/test_store_static.py::test_chat_session_list_primes_sessions_in_the_summary_shape` is updated deliberately: it pins the helper's six keys (`: s.` count 6 in the helper), that the `session_list` handler and the `sessions_changed` branch each prime `sessions` through the helper exactly once, and that neither calls `renderChatsList(`. Other static tests in that file still pass unchanged.
- [ ] Browser tests added to `tests/browser/test_flow_chat_live_updates.py`: (1) with the Chats list open and idle on the empty/welcome state, an inbound stub DM creates a chat and its row appears within 10 s with no reload, the state stays `idle` (no auto-open), and the route is unchanged; (2) with a chat open and text typed (not sent) in `chat-input`, an inbound DM from a second allowlisted peer adds its row; the open chat stays joined, the route and the composer's value are unchanged; (3) a chat started in a second page of the same context appears in the first page's list with no reload; (4) a chat deleted in the second page disappears from the first page's list; (5) an armed delete row on the first page keeps `confirm-delete` across a push caused by the second page. Test (1) also asserts the welcome state stays visible (`_chats.welcome`). Navigation through `_nav`/`_chats`/`_lists` only.
- [ ] Docs: `the_one/agents.md` WebSocket protocol table gains `sessions_changed`; the frame-gate bullet ("everything but the six below": recount after adding `sessions_changed`) and the idle-rules bullet ("run on EVERY `session_list`") in the chat session-state section are corrected; the `the_one/sessions` section gains the socket registry; the db/repository section gains the change signal and `list_summaries()`. CLAUDE.md's "Client data store (`App.store`…)" paragraph notes that `sessions` is also primed by `sessions_changed` pushes from the server.
- [ ] `make test-unit` passes (12 skipped expected; 14 under `THE_ONE_TEST_NETNS=1`); the static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`) pass; the `chats` and `routing` lanes pass with `THE_ONE_TEST_NETNS=1`; `ruff check` / `ruff format --check` clean.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_session_changes.py tests/test_store_static.py tests/test_imports.py -x --timeout 30`
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 30`
- `make test-unit` (via the worktree venv), read `-rs`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh -m browser tests/browser/test_flow_chat_live_updates.py -x`
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -x` and `--lane routing -x`
- Falsification: disable the push (e.g. make the listener a no-op), confirm browser tests (1)-(4) fail, restore. Record in the flight log.

## Implementation Guidance

1. **Signal module** — `the_one/db/_session_changes.py`, a plain module-level `list` of callables. Import it in `repositories.py` with a plain `from the_one.db._session_changes import notify_sessions_changed` (leaf, no cycle; `tests/test_imports.py` first-touch).
2. **Repository calls** — place each `notify_sessions_changed()` after the `async with write_transaction(...)` block, never inside it; keep existing `KeyError` raises before any notify.
3. **`list_summaries()`** — explicit column list: `id, agent_name, title, created_at, updated_at, platform, connector_id, channel_id, thread_id, peer_id, last_inbound_at, NULL AS messages, NULL AS session_metadata`; check `_row_to_model` reads no other column.
4. **Socket registry** — beside the subscriber registry; module-level `set`. In `websocket_endpoint`, wrap the existing `try/except WebSocketDisconnect` in an outer `try/finally` so `add_socket` and `remove_socket` are visibly paired; import the new names in `app.py`'s `the_one.sessions` import block.
5. **Listener** — in `app.py` near the other lifespan helpers: a small class or closure holding `loop`, `pending: asyncio.Task | None`. `notify` → if on loop thread: schedule; else `loop.call_soon_threadsafe(schedule)`; guard `loop.is_closed()`. `schedule` creates the task only if none is pending; the task sleeps the window, clears `pending`, then reads and broadcasts. Use `_chat_repo()` for the read. Register after the DB is initialised at startup. In shutdown, remove the listener as the first statement after `yield`; cancel + `await` (suppress `CancelledError`) the pending task before `close_connection()`.
6. **Client** — in `chat.js` add e.g. `function toSessionSummary(s) { return { id: s.id, … }; }`; the `session_list` handler's prime becomes `App.store.prime('sessions', sessions.map(toSessionSummary))`. Add `if (data.type === 'sessions_changed') { sessions = data.sessions || []; App.store.prime('sessions', sessions.map(toSessionSummary)); return; }` before the `session_list` branch (so the static test's window logic stays simple), and update the static test accordingly. In `renderChatsList`, filter `peeked.value` when `st.name === 'starting'` by `st.clientId`.
7. **Browser tests** — reuse leg 1's fixture and inbound helper; give `seed_stub_connector` (or the fixture) a second allowlisted peer (e.g. a `peers` list parameter, keeping leg 1's default and callers working) for test (2); for the second page use `page.context.new_page()` (same cookie jar) and `_nav.open_destination`/`_chats` helpers; for deletion use `_chats.chat_row_delete`. Wait with Playwright `expect(...)` timeouts, never `time.sleep`.
8. **Docs** as listed.

## Edge Cases
- **A push before the socket's first reply** (fresh socket): ignored by the rebind logic because the branch returns before `firstListPending` is read.
- **A push while `starting`**: the new row is filtered until `session_joined` swaps the pending row for the real one.
- **A push while `joining`/`joined`**: the selected row stays selected (selection comes from the state, not the list).
- **A chat deleted elsewhere while open**: its row disappears; the pane stays (recorded known edge, sortie DD3).
- **Shutdown writes** (in-flight cancel saves, connector drain): no push, the listener is already removed.
- **Unit tests without lifespan**: no listener, no push. `the_one.db._session_changes.clear_for_test()` is called in `tests/conftest.py`'s `reset_lifespan_singletons` fixture teardown, and the new `tests/test_session_changes.py` fixtures clear it before and after.
- **Pushes to a socket that has not asked for a list yet**: sent; the client ignores them for rebind purposes (no server-side filter).
- **`heal()`** runs the idle rules over the local `sessions` array, which a push now updates: the same result a fresh list would give.
- **Out-of-order snapshots** (a push and a reply crossing): accepted, recorded.

## Files Affected
- `the_one/db/_session_changes.py` - new
- `the_one/db/repositories.py` - notify calls, `list_summaries()`
- `the_one/sessions/_broadcast.py`, `the_one/sessions/__init__.py` - socket registry, `broadcast_to_all`
- `the_one/interfaces/web/app.py` - socket registration in `websocket_endpoint`, coalescing listener in the lifespan
- `the_one/interfaces/web/static/js/areas/chat.js` - `toSessionSummary`, `sessions_changed` branch, `renderChatsList` filter
- `the_one/interfaces/web/static/js/areas/chat/session-state.js` - gate
- `tests/test_session_changes.py` (new), `tests/test_store_static.py`, `tests/test_imports.py`, `tests/conftest.py` (listener clear)
- `tests/browser/seeders.py` - second allowlisted peer
- `tests/browser/test_flow_chat_session_state.py` - frame-gate case
- `tests/browser/test_flow_chat_live_updates.py` - tests (1)-(4)
- `the_one/agents.md`, `CLAUDE.md` - docs

## Citation Audit
Checked against the worktree at `08562ec` (before leg 1's edits to `app.py`): `ChatSessionRepository.list` is `SELECT * ... ORDER BY updated_at DESC`; `_row_to_model` (ChatSession) reads `id, agent_name, title, messages, created_at, updated_at, platform, connector_id, channel_id, thread_id, peer_id, session_metadata, last_inbound_at` and defaults `messages` to `"[]"`; `session-state.js::accepts` always accepts `session_list`/`session_deleted` and treats other frames as session-scoped; `chat.js::renderChatsList` reads `App.store.peek('sessions')` and the state; `tests/test_store_static.py:101-116` pins one prime, six `: s.` keys, and no `renderChatsList(` in the `session_list` window; the lifespan's shutdown begins right after `yield` with the ollama drain and ends with `close_connection()`. Re-check `app.py` line positions after leg 1.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
