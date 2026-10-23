# Sortie: Live Chats list and connector chats

**Status**: landed

## Charter

### Outcome
With the app left open, the Chats list and the open chat stay current as chats change elsewhere: new connector chats appear, and connector replies show up, without a reload.

### Why Now
The operator reported (2026-10-22) that a UI left open for a long time looks stale while Discord/Telegram traffic arrives. Planning found a worse neighbour: typing into an open connector chat after a connector turn silently overwrites that turn.

### Success Criteria
- [ ] A chat a connector creates appears in an already-open Chats list within a few seconds, with no user action.
- [ ] When a connector turn finishes in a chat the browser has open, the pane shows the new messages without a reload.
- [ ] A browser message sent into a connector chat after a connector turn keeps the connector turn in history.
- [ ] A pushed list update never moves the user: it does not auto-open a chat, change the route, or reset the composer.

### Constraints
- No polling. Reuse the existing WebSocket and the neutral `the_one/sessions/` registries.
- No connector protocol change.
- Work only in the sortie worktree (`.claude/worktrees/sortie-live-chats-list`); a separate workstream is active in the main checkout.

---

## Pre-Flight

### Objective
Make the server tell open browsers when chats change, and make the server's cached copy of a chat stop going stale. Every write that changes what the Chats list shows raises one in-process "sessions changed" signal from the db layer; the web app coalesces those signals and pushes a `sessions_changed` frame carrying the full list to every connected WebSocket. The client primes the `sessions` store (and its local list) from a push and does nothing else with it: no idle rules, no rebind, no route change. A web turn that starts on a chat whose stored content changed since the server cached it re-syncs the cached agent from the database first, so it never writes stale history over a connector turn. A connector turn that finishes tells the subscribers of that chat that it changed (`session_updated`); a browser with that chat open re-joins it, which re-renders the history from the database.

### Open Questions
- [x] How should an open connector chat show a connector turn? → re-join when the turn ends; no live streaming of connector turns (operator, 2026-10-22; DD5)
- [x] Which changes push a list? → every chat change, not only connector ones (operator; DD1)
- [x] HAT leg? → no; automated browser tests through the stub connector seam (operator; DD8)
- [x] Fix the stale-cache overwrite here or as a squawk? → here, criterion 3 (operator agreed the charter)
- [x] A message held while joined during a connector turn: sent or discarded? → sent on the `session_updated` re-join, as `done` would (Flight Director, Architect review 1; DD6)
- [x] REST `/api/chat` in scope for criterion 3? → no; it restores at request time and runs without the lock. Recorded as a known edge (DD4)
- [x] Should a push update the local `sessions` array? → yes (DD3)
- [x] Re-sync while a turn is paused for auth? → no skip: `Agent.step` clears `_deferred_tool_calls` at its start (`core.py:244`), so a new turn abandons the deferral anyway, and re-syncing first keeps a connector turn that landed during the pause (Architect review 2; DD4)
- [x] Shared mapping helper or a second inline copy (DD3)? → the shared helper; `tests/test_store_static.py`'s pin is updated deliberately (DD3)
- [x] Leg count → three legs, one sortie (operator, 2026-10-22, over the two-leg soft limit; still one decision cluster)

### Design Decisions

**DD1 — One "sessions changed" signal, raised from the db layer after commit.**
- A new leaf module `the_one/db/_session_changes.py` (stdlib only) holds a listener list, `add_listener`/`remove_listener`, `notify_sessions_changed()` (synchronous; calls each listener inside `try/except Exception` with a log; never raises; a no-op with no listener) and `clear_for_test()` (called from the unit-test fixtures that run the lifespan, e.g. `tests/test_lifespan.py`'s teardown; `the_one.sessions.clear_for_test()` does not clear it).
- `ChatSessionRepository` calls it **after** the `async with write_transaction(...)` block exits (committed) in every method that changes a field the Chats list shows (`id`, `title`, `agent_name`, `created_at`, `updated_at`, `platform`) or removes a row: `create`, `update`, `delete`, `delete_all_for_agent`, `delete_older_than` (only when it deleted rows), `purge_messages`, `update_last_inbound` (bumps `updated_at`, so the list re-orders as an inbound message arrives). `SQLiteAgentStore`'s rename (`UPDATE chat_sessions SET agent_name = ?`, `repositories.py:396`, its own `write_transaction`) calls it after that block. `append_to_session_metadata` and `set_session_metadata_key` do not. A call that raises (`KeyError` on a missing row) does not notify.
- Notify-after-commit is sound: `write_transaction` refuses re-entry from its own task (`_write_lock.py:63`), so no chat-repo write runs inside an outer transaction (Architect review 1 verified the full `chat_sessions` write list: only `ChatSessionRepository` plus the rename).
- Rationale: the repository is the one chokepoint every writer passes (web turns, REST routes, the connector dispatcher, the purge sweep, `retention.py`); a call-site approach would miss the next writer. Living in `the_one/db/` (the db layer announcing its own changes) adds no new dependency to `repositories.py`, which is cycle-sensitive (squawk 0003): the import is a trivial leaf, and `tests/test_imports.py`'s first-touch list gains `the_one.db._session_changes`.
- Trade-off: the db layer gains a side-effect call, bounded to a listener-less no-op outside the web app (CLI, evals, unit tests).
- A unit test pins the method list: each listed method notifies once per successful call (after the row is committed: the listener can read it back), each metadata method does not, and a failed call does not.

**DD2 — The web app coalesces and pushes to every socket.**
- `the_one/sessions/_broadcast.py` gains a registry of every connected WebSocket: `add_socket`/`remove_socket`/`all_sockets()` (snapshot) and `broadcast_to_all(payload)` (same dead-socket discard as `broadcast_to_session`), folded into `clear_subscribers_for_test`. `websocket_endpoint` (the only WebSocket route) registers right after `ws.accept()` and unregisters in a `finally` around the receive loop (today it catches only `WebSocketDisconnect`, `app.py:3222`; any other exit must not leak an entry).
- `ChatSessionRepository` gains `list_summaries()`: selects the list-visible columns only (the eleven `_session_to_list_payload` fields) in `list()`'s order and returns `ChatSession` models with `messages` left at its default, so `_session_to_list_payload` is reused as is and a push never loads every session's `messages` blob. The push uses it; the `list_sessions` reply stays as it is.
- The lifespan registers one listener (capturing the running loop) that arms a trailing coalesce: the first signal schedules a ~250 ms timer on that loop (`call_soon_threadsafe` when called off it; a closed loop is ignored); later signals in the window fold into it; on fire it reads `list_summaries()` once and sends `{"type": "sessions_changed", "sessions": [...]}` to every socket. Zero sockets: no read. A failed read logs a warning and sends nothing (never an empty list).
- Shutdown: the lifespan's shutdown branch removes the listener **first** (before the in-flight-task drain and the connector manager drain, which both write), then cancels and awaits any pending push task, before `close_connection()`. Apps and tests that never run the lifespan have no listener, so they see no push.
- Rationale: one summary read per burst, not per write or per socket; a distinct frame type is inert to an older cached `chat.js` (squawk 0085's same-version cache), where a `session_list` flagged `pushed` would be treated as a reply and run the idle rules.
- Trade-off: up to ~250 ms latency. A push and a `list_sessions` reply can arrive out of order on one socket; both are whole snapshots and the window is negligible; no sequence number (recorded).

**DD3 — A push only primes the lists.**
- `chat.js` handles `sessions_changed` in its own branch: it sets the local `sessions` array (read by `idleRules` via `runIdleRules` and `heal`) and primes `App.store` (`sessions`) with the same REST-summary mapping. Both the reply and the push prime through one shared mapping helper (the six summary keys inline in it); `tests/test_store_static.py::test_chat_session_list_primes_sessions_in_the_summary_shape` is updated deliberately to pin the helper's keys and that both handlers call it (and that neither handler calls `renderChatsList(`). It does not touch `listSeen` or `firstListPending` and does not run `runIdleRules()`. The store subscription re-renders the Chats list and pane header.
- `session-state.js`'s frame gate accepts `sessions_changed` in every state (like `session_list`).
- While `starting`, `renderChatsList` drops a listed row whose id equals the starting `clientId` (the server commits and notifies before `session_joined` arrives; the pending row stands for it).
- Rationale: criterion 4. The idle rules auto-open the most recent chat; on a push they would open a connector chat under a user on the empty welcome state; the first-list rebind must only ever see the socket's own reply.
- Known edge, out of scope: a chat deleted elsewhere while open here loses its row but the pane stays until the user acts (today's behaviour for a REST delete).

**DD4 — A web turn re-syncs a stale cache under the lock.**
- A content fingerprint, not a timestamp: `updated_at` comes from `now_iso()`, which has ~15.6 ms resolution on the shipped Windows build (Python 3.11), and a read-back after a save races writers that do not take the lock. `_fingerprint(messages: str, title: str) -> str` (a hash of the stored `messages` text and the title) lives in `app.py` and applies the same defaults `_row_to_model` applies on read (`title or "New chat"`, `messages or "[]"`) on both sides, so a write and its read-back are equal by construction. (`_save_session_to_db`'s `model_copy(update=...)` does not validate, and `repo.update` binds `messages` verbatim, so the bytes hashed are the bytes stored: Architect review 2.)
- `Session` gains `db_fingerprint: str | None`. It is set from the **same** `db_session` read `_restore_session` builds the history from (both branches; never a later re-read, so a restore racing a connector turn heals at the next turn), in `_create_session` from the row it creates, and in `_save_session_to_db` from the exact bytes it wrote (the encoded messages + title), with no read-back.
- `_locked_message_processing`, after acquiring `session_locks[session.id]` and before `_process_and_broadcast`, runs the re-sync in its **own** `try/except Exception` (log and proceed unsynced; it must never fail the turn: many unit tests drive this path with a bare `Session` and no row): read the row; `KeyError` (no row) → leave the session as it is; fingerprint equal → nothing; different → replace `session.agent.messages[1:]` with the row's non-system messages (the agent's fresh system message stays, as in `_restore_session`), rebuild `session.history` with `messages_to_ui_events`, take the row's `title`, store the new fingerprint.
- Not skipped while the agent is paused for auth: `Agent.step` clears `_deferred_tool_calls` at its start (`core.py:244`), so the new turn abandons the deferral whatever the re-sync does, and the database holds the paused turn's saved messages.
- Rationale: covers every external writer (a connector turn, a REST purge or rename) with one cheap read per web turn; under the lock, so it cannot interleave with the connector's own read-modify-write (`inbound.py:441`).
- Known edges, recorded not fixed: `_resume_paused_session` runs without `session_locks`, so a connector turn landing during an auth pause can still be overwritten by the resume's save; a re-join from a second tab rebuilds `existing.agent` and drops a pending deferral (pre-existing for manual joins); REST `/api/chat` has no lock and no re-sync.

**DD5 — A finished connector turn tells that chat's subscribers.**
- `dispatch_inbound` wraps the whole `async with session_locks[session_row.id]:` block in `try/finally`; the `finally` (outside the lock, so it runs after release) sends `{"type": "session_updated", "session_id": id}` through `broadcast_to_session`, wrapped in `contextlib.suppress(Exception)` so it never masks the turn's own exception or a cancellation (the `finally` can run during connector manager shutdown). It runs on success, on a failed step, and on the early `return` after a failed `factory.create` (`inbound.py:443-447`), so a browser that joined mid-turn always gets it. Sent after the lock so a re-join reads `is_processing` false and its rebuild is not skipped.

**DD6 — The browser re-joins on `session_updated`.**
- `session-state.js`'s frame gate treats `session_updated` as session-scoped (accepted only in `joined` for the bound id). On an accepted one, `chat.js`: if this client has its own turn outstanding (a send or a started chat with no `done`/`cancelled`/error yet, a flag set at send and cleared on those frames, distinct from `inFlightSessions`, which an `is_processing` join also sets), it marks a refresh and re-joins when that turn ends; otherwise it re-joins now through `openConversation(id)` (same id: no held message is discarded).
- Both flags (own-turn-outstanding and refresh-pending) are cleared on `done`, `cancelled`, a turn error, `onclose`, `applyStartFailed`, and every move to another session or state (`openConversation` with a different id, `pick`, `resetToIdle`, `clearConversation`), so a dropped socket never leaves later re-joins deferred forever.
- The behaviours below apply only to a same-id re-join triggered by `session_updated`; a normal open still scrolls to the bottom.
- On a re-join's `session_joined` with `is_processing: false` and a held message for this session (`pendingQueuedMessages[id]`), the held message is sent as the `done` handler does (`chat.js:2038-2066`); a held message otherwise waits forever, since no `done` comes for a connector turn.
- A re-join answered with `is_processing: true` (a queued web turn from another tab took the lock) re-joins once more on that turn's `done`.
- The re-join keeps the scroll position when the user is not pinned to the bottom (the existing `SCROLL_PIN_THRESHOLD` check), keeps the route, the composer text, focus and staged images. Accepted side effects: expanded tool/thinking disclosures collapse, telemetry is reset and restored, `context-window` is re-fetched, and Enter does nothing during the brief `joining`.
- The `session_joined` handler keeps exactly one `return;` after `if (joinedEff.startFailed)` (`test_start_session_join_refreshes_the_list_that_primes_sessions`), or that test is updated deliberately.

**DD7 — Protocol documentation.**
- `the_one/agents.md`: the WebSocket protocol table gains `sessions_changed` and `session_updated`; the frame-gate and idle-rules bullets (`agents.md:1497-1498`: "everything but the six below", idle rules "on EVERY `session_list`") are corrected; the `the_one/sessions` section gains the socket registry, and the db section the changes signal and `list_summaries`. CLAUDE.md's "Client data store" paragraph notes that `sessions` is also primed by `sessions_changed` pushes.

**DD8 — Verification apparatus: browser tests through the stub connector seam.**
- Act: `POST /api/_test/stub/inbound` (dual-gated: `THE_ONE_DEV_MODE=true` + `THE_ONE_STUB_TEST_ENDPOINT=1`, `api.py:4331`) drives the real `dispatch_inbound` through `StubPlugin.push_inbound` with a mock-provider agent (deterministic reply). No browser test drives this seam today; leg 1 builds the apparatus: an app fixture spawned with `extra_env={"THE_ONE_STUB_TEST_ENDPOINT": "1"}` (`tests/browser/conftest.py:207`), a stub connector seeded with `default_agent` and an allowlisted peer (`seeders.seed_connector`), and a wait until the manager reports it connected (`push_inbound` gives 409 until then).
- The inbound POST blocks for the whole connector turn (`manager._on_inbound` awaits `dispatch_inbound`); a mid-turn state (joined during a connector turn) uses the mock provider's `delay_ms` with the POST issued from a background thread.
- Observe: Chats list rows (`_chats.chat_row`/`chat_rows`), the pane's messages, `_chats.session_state`, `_nav.current_route`, the composer's value, and `GET /api/chat/sessions/{id}` for the stored history (criterion 3).
- No behavior test and no pixel tests. New file `tests/browser/test_flow_chat_live_updates.py` (the `chats` lane by its `test_flow_chat*` glob).

### Citation Audit

Verified against the worktree at `08562ec` (Architect review 1 re-checked about twelve rows):

| Citation | Status |
|---|---|
| `the_one/interfaces/web/app.py::websocket_endpoint` — `session_list` is sent only in reply to `list_sessions` (`:3118-3131`); the handler catches only `WebSocketDisconnect` (`:3222`) | verified |
| `the_one/interfaces/web/static/js/areas/chat.js` — `refreshSessionList` (`:933`) is the only `list_sessions` sender besides `onopen` (`:1618`); `session_list` handler primes `App.store` then runs rebind and `runIdleRules` (`:1647-1697`) | verified |
| `the_one/interfaces/web/static/js/areas/chat/session-state.js::idleRules` — while idle, opens `list[0]` unless `suppressAutoJoin` | verified |
| `the_one/connectors/inbound.py::dispatch_inbound` — runs the turn under `session_locks[id]` (`:441`) with an early `return` on a failed `factory.create` (`:443-447`), persists via `chat_repo.update` (`:477`), broadcasts nothing | verified |
| `the_one/sessions/_broadcast.py::broadcast_to_session` — snapshot iterate, discard dead sockets | verified |
| `the_one/db/_write_lock.py` — `write_transaction` refuses re-entry from its own task (`:63`) | verified (Architect) |
| `the_one/interfaces/web/app.py::_save_session_to_db` — writes `session.agent.messages` and `session.title` whole (`:1625-1643`) | verified |
| `the_one/interfaces/web/app.py::_locked_message_processing` — takes `session_locks[session.id]` then calls `_process_and_broadcast` with the cached Session inside `try/except Exception` (`:993-1022`) | verified |
| `the_one/interfaces/web/app.py::_restore_session` — with a cached Session, skips the rebuild while processing/in-flight; otherwise rebuilds agent and history from the DB and updates a cached Session in place (`:1519-1611`) | verified |
| `the_one/db/repositories.py::ChatSessionRepository` — `update`, `update_last_inbound`, `purge_messages` bump `updated_at`; metadata methods do not; `list()` is `SELECT *` | verified |
| `the_one/db/repositories.py:396` — agent rename rewrites `chat_sessions.agent_name` in its own `write_transaction` | verified (Architect) |
| `the_one/agent/core.py` — `_deferred_tool_calls` is `None` unless paused (`:185`, `:244`) | verified |
| `the_one/interfaces/web/api.py::stub_test_inbound` — calls `StubPlugin.push_inbound(connector_id, envelope)` (`:4361`) | verified |
| `tests/browser/conftest.py` — app launcher accepts `extra_env` (`:207`, `:251`) | verified |
| `chat.js` join handler — `is_processing` sets `inFlightSessions[id]` and shows thinking (`:1766-1772`); held messages are sent only from `done` (`:2038-2066`) | verified |
| `tests/test_store_static.py` — pins one `App.store.prime('sessions'` and no `renderChatsList(` in the `session_list` handler, and one `return;` after `startFailed` in `session_joined` | verified (Architect) |

### Prerequisites
- [x] The worktree has its own venv (`.venv`, editable install of the worktree) so tests import the worktree's source, not the main checkout's.
- [x] Re-verify per leg: `.venv/bin/python -c "import the_one; print(the_one.__file__)"` prints a path under the worktree.
- [x] Stub connector seam and mock provider exist and are dual-gated (no new seam).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified (worktree venv imports the worktree, 2026-10-22)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
Leg 1 lands the data-loss fix and proves the test apparatus first: the stub-seam browser apparatus (DD8) and the turn-start re-sync (DD4), with unit tests (a web send after a connector-style write keeps it; a failing re-sync read does not fail the turn; an equal fingerprint does no work; a paused agent re-syncs) and a browser test (a web send into a connector chat after a connector turn keeps it, read back over REST). Leg 2 lands the list push: the signal (DD1), the socket registry, summary read and coalesced push (DD2), the client's push handling (DD3), with unit tests and browser tests (a connector-created chat appears in an open list; a second tab's new chat appears; the empty welcome state does not auto-open on a push; the route and composer are untouched). Leg 3 lands the open-chat refresh: `session_updated` (DD5) and the client re-join (DD6), with unit tests (sent after the lock, on every exit path) and browser tests (a connector reply appears in the open pane, the composer text kept; a join during a connector turn clears the thinking indicator; a held message is sent on the re-join). Docs (DD7) land with the leg that adds each frame.

### Checkpoints
- [x] A web send after a connector turn keeps the connector turn (unit + browser)
- [x] A connector-created chat appears in an open Chats list (browser test)
- [x] An open connector chat shows a connector reply without reload (browser test)
- [x] `make gate` green (with `THE_ONE_TEST_NETNS=1`)

### Adaptation Criteria

**Divert if**:
- The repository chokepoint (DD1) cannot be made safe for some caller without a call-site approach.
- Re-join on `session_updated` disrupts a state the tests cannot hold steady (e.g. a starting chat), needing a different client mechanism.

**Acceptable variations**:
- The coalesce window between 100 and 500 ms.
- Where exactly the "own turn outstanding" flag lives in `chat.js`.
- The fingerprint's hash function.
- Folding a test or doc edit from one leg into the other.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `fresh-cache` - The stub-seam browser apparatus and the turn-start stale-cache re-sync, with unit and browser tests (DD4, DD8)
- [x] `live-list` - The sessions-changed signal, the socket registry and coalesced `sessions_changed` push, the client's push-only priming, tests and docs (DD1-DD3, DD7)
- [x] `live-open-connector-chat` - `session_updated` after a connector turn, the client re-join with turn deferral and held-message dispatch, tests and docs (DD5-DD7)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- Browser tests in the chats lane (`tests/browser/test_flow_chat_live_updates.py`, all three legs) drive the stub connector seam and assert criteria 1, 2 and 4; a unit test plus a browser read-back of the stored history assert criterion 3.
- `make gate` with `THE_ONE_TEST_NETNS=1` green.
