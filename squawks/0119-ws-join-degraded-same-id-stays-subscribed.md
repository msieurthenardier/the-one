# Squawk 0119: A degraded `join` of the already-bound session leaves the socket subscribed

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: 2026-10-06

## Report

In the WebSocket `join` branch (`the_one/interfaces/web/app.py`, `websocket_endpoint`),
the previous session's subscription is removed only when the requested id **differs** from
the bound one:

```python
if session and session.id != session_id:
    remove_subscriber(session.id, ws)
```

Suppose the socket re-joins the session it is already bound to, and the restore comes back
**degraded** (its agent was deleted, or its provider is missing). The degraded branch then
sets `session = None` and sends the degraded joined frame, but the socket stays subscribed
to that session. So:
- the socket still receives that session's broadcasts, for example a connector turn still
  running on it;
- the loop believes nothing is bound.

The client renders degraded state, so stray frames can land in the pane.

M25 Flight 4 leg 2 found it. Its new `start_session` degraded path unbinds whatever was
bound and does not copy this behaviour. `join` itself was out of that leg's scope.

## Evidence

- `app.py`, the `join` branch: the `if session and session.id != session_id:
  remove_subscriber(...)` guard, then `if restored.is_degraded: session = None; await
  ws.send_json(await _build_session_joined_degraded(restored)); continue`. That is around
  line 2750–2769 at the leg 2 landing, uncommitted on `flight/04-chats-and-jump-to`.
- The leg 2 entry in
  `missions/25-workbench-navigation/flights/04-chats-and-jump-to/flight-log.md`.

## Corrective Action

In `websocket_endpoint`'s `join` branch, the degraded path now calls `remove_subscriber(session.id, ws)` when a session is bound, before `session = None` and the degraded `session_joined` frame (the `not_found` branch's pattern). A join of a different id is unchanged (the earlier `session.id != session_id` unsubscribe still covers it). No message shape changed.

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

`tests/test_ws_start_session.py::TestExistingIdJoins::test_degraded_same_id_rejoin_unsubscribes_the_socket`: bind a socket to a session, make its agent missing, re-`join` the same id; asserts the degraded frame (`agent_deleted`), that `subscribers_for(sid)` excludes the socket, and that a probe broadcast never reaches it.

## Sign-Off

**Reviewer**: pending the Flight 6 leg review
