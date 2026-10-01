# Squawk 0111: Chat stalled-join recovery can leave one orphan empty session

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: —

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

*(written at completion)*

## Verification

## Sign-Off

*(written at completion)*
