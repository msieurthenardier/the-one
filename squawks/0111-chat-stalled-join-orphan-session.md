# Squawk 0111: Chat stalled-join recovery can leave one orphan empty session

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: 2026-10-05 (M25 Flight 4 leg 3b, `start-flow-client`)

## Report

Mission 25 Flight 2's review fixes added a 10-second stalled-join recovery timer to the
chat start path in `chat.js`.

- **The failure.** If the server's `session_joined` takes longer than 10 seconds after
  the client sends `new_session`, the timer re-sends the start. The server can then
  create a second session, which stays empty and orphaned in the history.
- **A second gap.** The drain re-send path, which runs when the socket reconnects with a
  pending start, does not re-arm the timer.
- **Reviewer's view.** The flight-end Reviewer accepted this as a low-severity trade-off.
  The recovery exists because the WebSocket protocol has no error frame for a failed
  start.

## Evidence

- The flight-review fix round in
  `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md` records the
  accepted trade-off. See "Flight review" in the Flight Director Notes.
- `the_one/interfaces/web/static/js/areas/chat.js` holds the `pendingStart` handling: the
  `sent` flag and the stalled-join timer.

## Corrective Action

Closed **by construction** in M25 Flight 4 leg 3b (flight DD1), with the server side in
leg 2 (`ws-start-protocol`):

- **`new_session` is gone.** The client never sends it, and leg 3b deleted its branch from
  `websocket_endpoint` (`the_one/interfaces/web/app.py`). A stray `new_session` frame now
  falls into the message path, whose validator finds an empty payload: no reply, nothing
  created (`tests/test_ws_start_session.py::test_new_session_is_gone_and_creates_nothing`).
- **The stalled-join recovery is gone with it.** `pendingStart` (the queued intent and its
  `sent` flag), `armPendingStartTimer`, `clearPendingStartTimer`,
  `DEFAULT_START_JOIN_TIMEOUT_MS`, the `App.chatStartJoinTimeoutMs` test hook and the
  `session_list` drain re-send are deleted from `static/js/areas/chat.js`.
- **The replacement cannot orphan a session.** Picking an agent creates nothing (a `leave`
  and a client-side *pending* chat, `#chats/~new/{agent}`). The first send is one
  `start_session` carrying a client-generated id (32 hex). The server action is
  idempotent on that id (an existing id is joined, and the first message is processed
  exactly once) and reserves the id across sockets, so a re-send can never create a second
  session.
- **Only a socket close re-sends.** At `onopen` on a fresh socket, a chat still `starting`
  re-sends the SAME `start_session` (never `join`). A lost reply on an **open** socket is
  **deliberately no longer recovered**: there is no timer; the server always answers a
  `start_session` (`session_joined`, or the typed `start_failed`, with its reservation wait
  bounded at 30s), so the case the timer guessed at no longer exists. This is the recorded
  trade-off of retiring the timer.
- **The second gap closes too**: there is no drain path left to re-arm.

## Verification

- **Static pin:** `tests/test_store_static.py::test_retired_new_session_path_is_gone_from_the_client`
  fails if `new_session`, `pendingStart`, `armPendingStartTimer`, `clearPendingStartTimer`,
  `DEFAULT_START_JOIN_TIMEOUT_MS`, `chatStartJoinTimeoutMs` or `startSessionWith` appears in
  any `static/js` file.
- **Server:** `tests/test_ws_start_session.py` (leg 2's idempotency, reservation and
  strict-create tests; leg 3b's `test_new_session_is_gone_and_creates_nothing`).
- **Browser:** `tests/browser/test_flow_chat_start_reconnect.py` (renamed from
  `test_flow_chat_start_recovery.py`, which pinned the timer):
  - a `start_session` that never reached the server (dropped, then the socket closed) is
    re-sent at the reconnect: exactly one session, the first message delivered once, and a
    send held in the reconnect gap lands in the same session (no plain message on an
    unbound socket);
  - a `start_session` that reached the server (its `session_joined` swallowed, then the
    socket closed) is re-sent and joins: still one session, the first message once;
  - reconnect while joined re-joins; the joined session deleted while the socket was down
    goes idle with no default-agent session created.
- **Browser:** `tests/browser/test_router_items.py::test_a_first_send_before_a_pending_session_list_creates_exactly_one_session`
  (inverted from the `new_session` drain test): a list reply landing between a
  `start_session` and its join re-sends nothing.
- **Leg 8 re-check** (the flight's closing gates): every test named above still exists
  and passed: `make test-unit` 5177 passed (the static pin and `test_ws_start_session.py`),
  `chats` 162 passed (the reconnect file's 4 tests), `shared` 461 passed
  (`test_router_items.py`).

## Sign-Off

*(pending: the M25 Flight 4 flight-end review signs it off)*
