# Leg: live-open-connector-chat

**Status**: completed
**Flight**: [Live Chats list and connector chats](../flight.md)

## Objective
When a connector turn finishes, the server tells the subscribers of that chat (`session_updated`), and a browser with the chat open re-joins it, so the connector's messages appear without a reload; a join made during a connector turn no longer keeps a thinking indicator forever, and a message the user sent meanwhile is delivered.

## Context
- Sortie DD5 (dispatcher `session_updated`), DD6 (client re-join), DD7 (docs). Charter criteria 2 and 4.
- Leg 1 added the turn-start re-sync (a web turn after a connector turn no longer overwrites it) and the stub-connector browser apparatus; leg 2 added the `sessions_changed` push and the shared summary helper in `chat.js`. Read the flight log's entries for both legs first: names, fixture shapes, and anything that deviated.
- Today `dispatch_inbound` (`the_one/connectors/inbound.py`) runs the turn under `async with session_locks[session_row.id]:`, returns early inside it when `factory.create` fails, persists with `chat_repo.update`, and broadcasts nothing. A browser that joins mid-turn gets `is_processing: true` (`is_session_processing` reflects the lock), so the `session_joined` handler sets `inFlightSessions[id]`, disables Send and shows thinking; no `done` ever comes for a connector turn. A Send in that state is held in `pendingQueuedMessages[id]`, and only the `done` handler (`chat.js`, `else if (data.type === 'done')`) sends a held message.
- A same-id `openConversation(id)` re-joins without discarding the held message (`discardHeld` only for a different id); the `session_joined` handler re-renders the history and forces `messagesEl.scrollTop = messagesEl.scrollHeight`.

## Inputs
- Legs 1 and 2 landed in the working tree (uncommitted; do not revert any of it).
- `the_one/sessions` exports `broadcast_to_session`; `inbound.py` already imports `session_locks` from `the_one.sessions`.
- The stub-connector fixture, `seed_stub_connector` and the inbound helper from leg 1; the mock provider's `delay_ms` config (CLAUDE.md "Mock provider `config` options").

## Outputs
- `dispatch_inbound` sends `session_updated` after the lock on every exit path.
- `chat.js` re-joins on `session_updated` with turn deferral, held-message dispatch, a second re-join when answered `is_processing: true`, and scroll keeping; `session-state.js` gates the frame.
- Unit tests, browser tests, docs.

## Acceptance Criteria
- [x] `dispatch_inbound` wraps the whole `async with session_locks[session_row.id]:` block in `try/finally`; the `finally` (after the lock is released) sends `{"type": "session_updated", "session_id": session_row.id}` via `broadcast_to_session`, inside `contextlib.suppress(Exception)` (add `import contextlib` and import `broadcast_to_session` beside `session_locks`). It runs on a successful turn, on a failed `agent.step` (already caught inside), and on the early `return` after a failed `factory.create`. Early returns before a session is resolved (not admitted, a pairing code, `_handle_new`, no reply) send nothing.
- [x] Unit tests (in `tests/test_connectors_inbound.py` or a new `tests/test_inbound_session_updated.py`, following that file's FakeLLM/fixture patterns): a registered subscriber receives exactly one `session_updated` for the session after a turn, and `session_locks[id].locked()` is False when it is sent; the same on the `factory.create` failure path and on a step that raises; a subscriber whose `send_json` raises does not make `dispatch_inbound` raise; a not-admitted envelope sends nothing; a `CancelledError` raised inside the turn still propagates out of `dispatch_inbound`.
- [x] `session-state.js::accepts` treats `session_updated` as session-scoped (accepted only in `joined`), and `chat.js` ignores one whose `session_id` is not `chatState.boundId()`. `tests/browser/test_flow_chat_session_state.py::test_frame_gate` covers it as a scoped frame (add `"session_updated"` to its `SCOPED` list). Exception, checked in `chat.js` before the gate: a `session_updated` for the id being joined (`joining`, same id) sets a refresh-after-join mark, and the `session_joined` reply for that id is followed by one more update re-join (the update can land between the server's join read and its reply).
- [x] `chat.js` keeps an "own turn outstanding" flag per session: set where this client sends (`performSend`, and a start's send), cleared on `done`, `cancelled`, the turn-error path (the `inFlightSessions` delete in the error handler), `sock.onclose` (inside its existing non-`starting` branch: while `starting` the start is re-sent, so the flag is kept, matching AC6), `applyStartFailed`, and every move to another session or state (`openConversation` with a different id, a pick, `resetToIdle`, `clearConversation`). It is distinct from `inFlightSessions`, which an `is_processing` join also sets. Flags are keyed by session id. In `done`, the held-message branch (`performSend(held)`) starts a new own turn, so the flag stays set there (the re-join waits for that turn's `done`).
- [x] While the agent is paused for auth (a login group is shown in the pane): confirm that the server's pause-snapshot replay on join (`_send_pause_snapshot_if_needed`) restores the login group after a re-join; if it does, re-join normally; if it does not, defer the update re-join until the pause resolves (`auth_resolved`/`auth_failed`). Record which in the flight log.
- [x] On an accepted `session_updated`: own turn outstanding → mark refresh-pending and, on that turn's `done`/`cancelled`, re-join (`openConversation(id)`) after the existing handling; otherwise re-join now. The refresh-pending flag has the same clear sites as the own-turn flag.
- [x] On a `session_joined` that answers a `session_updated` re-join (a flag set when the re-join is sent, cleared on any join reply or move): `is_processing: false` with `pendingQueuedMessages[id]` → the held message is removed and sent through one helper shared with the `done` handler (`delete pendingQueuedMessages[id]; clearPendingQueued(); performSend(held)`), so the two sites cannot drift; `is_processing: true` → re-join once more on the next `done`; the scroll position is kept when the user was not within `SCROLL_PIN_THRESHOLD` of the bottom when the re-join was sent (recorded then, not in the reply handler), restored after `renderHistory`, the forced `scrollTop = scrollHeight` and `showChrome` (otherwise scroll to the bottom as today). A normal open is unchanged. The held dispatch and the scroll restore sit before the handler's `refreshSessionList()` and add no `return;`.
- [x] A re-join keeps the route, the composer's text, focus, and staged images. The `session_joined` handler still has exactly one `return;` after `if (joinedEff.startFailed)` (`tests/test_store_static.py::test_start_session_join_refreshes_the_list_that_primes_sessions`), or that test is updated deliberately with the reason in the flight log.
- [x] Browser tests in `tests/browser/test_flow_chat_live_updates.py`: (1) a connector chat open in the browser, with text typed in `chat-input`: an inbound DM's text and the mock reply appear in the pane without a reload; the state stays `joined`, the route and the composer's value are unchanged; (2) the browser joins the chat while a connector turn is running (mock `delay_ms` of about 4 s or more, the inbound POST issued from a background thread; join mid-turn by navigating to or reloading the chat once the turn has started, synchronising on the pane or `_chats.session_state`, never on sleeps): the thinking indicator shows, then clears after the turn, and the turn's messages are shown; (3) after such a mid-turn join, the user fills `chat-input` and presses Enter (Send is disabled while busy, so never click `chat-send-btn`): the message is held (queued chip), then sent after the `session_updated` re-join, its reply arrives, and `GET /api/chat/sessions/{id}` holds the connector turn and the web message in order; (4) with the chat scrolled up away from the bottom (deterministic history: earlier turns or `seed_session(messages=...)` with fixed plain-text lines, no markdown or images; scroll with `messagesEl.scrollTop = N` via `evaluate`), a connector turn's re-join keeps `scrollTop` within a small tolerance and the last message is not pinned into view, asserted after the new connector reply is in the DOM; (1) also asserts that `chat-input` keeps focus when it had it. Navigation through `_nav`/`_chats`/`_lists` only.
- [x] Docs: `the_one/agents.md` WebSocket protocol table gains `session_updated` (server → subscribers of one session, after a connector turn; the client re-joins), the frame-gate bullet counts it as session-scoped, and the connector inbound section notes the `finally` broadcast. CLAUDE.md is updated only if a paragraph there describes connector chats in the Chats pane (one sentence at most).
- [x] `make test-unit` passes (12 skipped expected; 14 under `THE_ONE_TEST_NETNS=1`); the static guards pass; the `chats`, `routing` and `library` lanes pass with `THE_ONE_TEST_NETNS=1`; `ruff check` / `ruff format --check` clean.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_connectors_inbound.py <new unit file> tests/test_store_static.py -x --timeout 30`
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 30`
- `make test-unit` (via the worktree venv), read `-rs`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=1200 bash scripts/run-tests.sh -m browser tests/browser/test_flow_chat_live_updates.py tests/browser/test_flow_chat_session_state.py -x`
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -x` (and `routing`, `library`)
- Falsification: drop the `session_updated` broadcast, confirm browser tests (1)-(3) fail, restore. Record in the flight log.

## Implementation Guidance

1. **Dispatcher** — in `dispatch_inbound`, `try:` before `async with session_locks[session_row.id]:`, `finally:` with `with contextlib.suppress(Exception): await broadcast_to_session(session_row.id, {...})`. Import `broadcast_to_session` from `the_one.sessions`. Keep the inner `try/except/finally` (ContextVar resets) as is.
2. **Gate** — `session-state.js::accepts` already treats unknown types as session-scoped (`return cur.name === 'joined'`); `onFrame` then returns `{ accept: true }`. Confirm and add a comment line; the id check is in `chat.js`.
3. **Flags in `chat.js`** — e.g. `var ownTurn = {}; var refreshAfterTurn = {}; var updateRejoin = null;` near `inFlightSessions`. A small `clearLiveRefresh(id?)` helper called from every clear site keeps the list honest.
4. **Re-join** — a `rejoinForUpdate(id)` that records the pin state (`messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight <= SCROLL_PIN_THRESHOLD`) and `scrollTop`, sets `updateRejoin = {id, pinned, scrollTop}`, then calls `openConversation(id)`. In `session_joined`, after the history render, when `updateRejoin && updateRejoin.id === joinedId`: restore `scrollTop` if not pinned, then handle held/`is_processing` per the criteria, then clear `updateRejoin`. Keep the single `return;` after `startFailed`.
5. **`done`/`cancelled`** — after their existing handling, if `refreshAfterTurn[sid]` (or the second-re-join mark) → clear it and `rejoinForUpdate(sid)`. Note `done` with a held message calls `performSend(held)`, which starts a new own turn: defer the re-join to that turn's `done` (the flag carries over).
6. **Browser tests** — the mock `delay_ms` on the connector agent's provider makes the turn observable. Leg 1's fixture seeds the provider with no config and does not expose its id: add a fixture variant that takes a provider config (or exposes `provider_id`, then `PUT /api/providers/{id}` to set the delay after the chat exists; confirm `factory.create` re-reads the provider per turn). `delay_ms` slows every turn on that provider, the first DM's included; issue the blocking inbound POST from a `threading.Thread` and join it at the end. Wait with `expect(...)`, never `time.sleep`.
7. **Docs** as listed.

## Edge Cases
- **`session_updated` while `joining`/`pending`/`starting`/`idle`**: dropped by the gate.
- **`session_updated` for another session** (stale subscription): ignored.
- **Socket drop mid-turn**: `onclose` clears both flags; the reconnect's re-join reads fresh history anyway.
- **An already-open chat when a connector turn starts**: the client has no `is_processing` (nothing told it), so Send is enabled; a send goes out (own turn), the server queues the web turn behind the connector's lock, `session_updated` arrives while the own turn is outstanding, and the re-join waits for that turn's `done`. The connector's messages then appear after the web reply. Tests must not assert an earlier re-join in this case.
- **Two tabs**: each re-joins independently; a queued web turn from the other tab answers `is_processing: true` → one more re-join on its `done`.
- **A failed `factory.create`**: the inbound row was bumped but no messages changed; the re-join is harmless and clears a stuck thinking indicator.
- **Cancellation of the dispatcher task** (connector manager shutdown): the `finally` broadcast is suppressed on error; `CancelledError` is not swallowed by `suppress(Exception)` and still propagates.

## Files Affected
- `the_one/connectors/inbound.py` - `try/finally` + `session_updated`
- `the_one/interfaces/web/static/js/areas/chat.js` - flags, `rejoinForUpdate`, `session_updated` branch, `done`/`cancelled`/`session_joined` hooks, clear sites
- `the_one/interfaces/web/static/js/areas/chat/session-state.js` - gate comment (and code only if needed)
- `tests/test_connectors_inbound.py` and/or a new unit file
- `tests/browser/test_flow_chat_live_updates.py`, `tests/browser/test_flow_chat_session_state.py`
- `tests/test_store_static.py` (only if the `return;` pin must change)
- `the_one/agents.md` (and at most one CLAUDE.md sentence)

## Citation Audit
Checked against the worktree at `08562ec` plus the planned leg 1-2 changes: `dispatch_inbound`'s locked block with the `factory.create` early `return` and the final `chat_repo.update`; `inbound.py` imports `session_locks` from `the_one.sessions`; `chat.js` `done` handler sends a held message via `performSend(held)` else clears `inFlightSessions`; `cancelled` clears `inFlightSessions` and the held message; `session_joined` sets `inFlightSessions[joinedId]` on `is_processing` and forces `scrollTop = scrollHeight`; `SCROLL_PIN_THRESHOLD = 80`; `sock.onclose` clears every `inFlightSessions` key; `applyStartFailed` deletes `inFlightSessions[eff.clientId]`; `openConversation` discards a held message only for a different id; `session-state.js::accepts` returns `cur.name === 'joined'` for unlisted types. Re-check line positions after legs 1-2.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
