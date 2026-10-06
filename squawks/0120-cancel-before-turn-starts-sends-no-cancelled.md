# Squawk 0120: A `cancel` processed before a spawned turn starts sends no `cancelled`

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: —

## Report

The WebSocket loop spawns a turn as a background task (`_spawn_web_message`, used by the
`message` path and by `start_session`) and goes straight back to `ws.receive_text()`. When
the client's `cancel` frame is already queued on the socket, that receive returns without
yielding to the event loop, so the `cancel` branch runs `task.cancel()` **before the task's
first step**.

A task cancelled before it starts never runs its coroutine: `_spawn_message_processing`'s
`async with session_locks[...]` and `_process_and_broadcast`'s `except asyncio.CancelledError`
(which persists any partial text and sends `{"type": "cancelled"}`) are never entered. So
the client never receives `cancelled` (or `done`), and a client that marked the turn busy
stays busy: Stop stays visible, Send stays disabled, the thinking indicator stays.

`start_session`'s `session_joined` carries `is_processing: true` (the turn is spawned right
after it), so the client is busy from that frame on; a plain `message` marks itself busy
optimistically. Both paths are exposed. A human click is normally too slow to land inside
the window (the turn has begun by then); a scripted Stop right after the send lands in it.

M25 Flight 4 leg 3b found it while testing "Stop while starting"
(`tests/browser/test_flow_chat_start_flow.py::test_stop_while_starting_cancels_the_first_turn`
clicks Stop only once the server has created the session, so it does not depend on this).
It predates the flight: the `message` path behaves the same way.

## Evidence

- `app.py`, `_spawn_web_message` (`asyncio.create_task(_spawn_message_processing(...))`) and
  the `cancel` branch of `websocket_endpoint` (`for t in tuple(_session_inflight.get(...)):
  if not t.done(): t.cancel()`).
- `app.py`, `_process_and_broadcast`'s `except asyncio.CancelledError:` block: the only
  sender of `{"type": "cancelled"}`.
- Reproduced in a scratch browser test on `flight/04-chats-and-jump-to` (leg 3b): pick an
  agent, send, click Stop at once; the frames received were `session_joined`
  (`is_processing: true`) and `session_list`, with no `cancelled` and no `done`.

## Corrective Action

*(written at completion)*

A likely shape: a done-callback on the spawned task (or the `cancel` branch) that sends
`cancelled` when the task was cancelled without its coroutine ever starting, for example
tracked by a "started" flag the coroutine sets on entry.

## Verification

In the `tests/test_ws_start_session.py` harness: script `start_session` (or `message`)
followed immediately by `cancel` on one socket, and assert a `cancelled` frame arrives and
`is_session_processing(sid)` ends false. Then a browser test: send and click Stop at once,
and assert Stop hides and Send re-enables.

## Sign-Off

*(written at completion)*
