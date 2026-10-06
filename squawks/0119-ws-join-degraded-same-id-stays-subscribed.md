# Squawk 0119: A degraded `join` of the already-bound session leaves the socket subscribed

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: —

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

*(written at completion)*

## Verification

In the `tests/test_ws_start_session.py` harness: bind a socket to session X. Make X's
restore degrade (delete its agent). Send `join(X)`. Then broadcast to X, and assert the
socket receives nothing and `subscribers_for(X)` excludes it.

## Sign-Off

*(written at completion)*
