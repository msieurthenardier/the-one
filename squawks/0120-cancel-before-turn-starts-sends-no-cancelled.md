# Squawk 0120: A `cancel` processed before a spawned turn starts sends no `cancelled`

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: 2026-10-06

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

A spawned turn now records two markers and a per-cancel token (`app.py`: `_started_tasks`, `_running_tasks`, `_cancel_tokens`, `_notify_cancelled_once`). `_spawn_message_processing`'s first statement marks the task started; `_process_and_broadcast` marks it running at the `try` whose `except CancelledError` sends `cancelled` (after persisting partial text, now through `_notify_cancelled_once`). The `cancel` branch creates the token (`sent`, `running`) before any `t.cancel()`, and sends through the helper only when no task in the batch ever started (a task cancelled before its first step runs no body code). A task cancelled while waiting on the session lock, or before `_process_and_broadcast`'s `try`, sends from `_spawn_message_processing`'s wrapper `except CancelledError`, unless it was running itself or the batch has a running task (the sole sender). The token is dropped when `_session_inflight[sid]` empties; with no token (lifespan shutdown) the helper always sends. Result: exactly one `cancelled` per `cancel`. Only the WebSocket spawn path changed; no message shape changed.

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

`tests/test_ws_start_session.py::TestCancelSendsExactlyOneCancelled` (new `NoYield` step in the `FakeWebSocket` harness, since its receive yields before every frame): (a) a cancel before the task starts, (b) a cancel while it waits on `session_locks[sid]` (lock released afterwards, not left held), (c) a cancel of a running turn, (d) one cancel over a running turn plus an unstarted one. Each asserts exactly one `cancelled` frame, a clean `_session_inflight` and `_cancel_tokens`, and `is_session_processing` false. `tests/test_cancel.py` and the other cancel tests pass. The squawk's browser check ("Stop at once, then Send re-enables") is dropped: WebSocket frame ordering cannot be made deterministic from Playwright, and the unit tests pin the server behaviour the client reacts to.

## Sign-Off

**Reviewer**: pending the Flight 6 leg review
