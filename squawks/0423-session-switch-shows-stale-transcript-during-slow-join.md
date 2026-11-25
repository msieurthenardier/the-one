# Squawk 0423: A session switch keeps the previous transcript on screen while a slow join is pending

**Status**: escalated
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

In the installed app, switching chat sessions left the pane showing the previous conversation, a GleepGlorp chat, for about a minute before the selected chat appeared. Two causes compound:

- **Server:** the `join` handler rebuilds the agent before it replies with `session_joined`. The WebSocket loop handles one action at a time per socket, so one slow build delays every later action on that socket. Two stacked 30 s builds come to about a minute (the slow build is squawk 0422).
- **Client:** opening a conversation enters `joining(id)` and re-renders the chrome. It neither clears nor masks the old log, and nothing shows that a join is pending.

Squawk 0422 removes today's 30 s trigger. Any other slow build would still freeze the pane the same way, for example an MCP connect or a slow database read.

## Evidence
- `the_one/interfaces/web/app.py:_websocket_loop`: the `action == "join"` branch awaits `_get_or_restore_session` before `ws.send_json(_build_session_joined_ok(...))`. That function reaches `_restore_session`, which awaits `factory.create`.
- `static/js/areas/chat/session-flow.js:openConversation`: calls `chatState.openConversation`, `sendBinding({action: 'join'})` and `renderPane()`. It has no `clearLog` and no joining indicator (compare `renderPending`, which calls `ctx.transcript.clearLog()`).
- `static/js/areas/chat/session-state.js:accepts`: while `joining`, every session-scoped frame is dropped. The old log is static content that no frame replaces until `session_joined`.

## Corrective Action
*(not a squawk: see Disposition)*

## Verification
*(set by the sortie)*

## Sign-Off
*(not applicable)*

## Disposition
**Escalated**: this fails squawk criteria 2 and 3.
- **Criterion 2 (no design decisions):** what the pane shows while joining is a UI design call. A cleared log flashes empty on every fast switch, while a loading state or mask needs a design.
- **Criterion 3 (bounded blast radius):** taking the build out of the per-socket loop changes the chat WebSocket protocol's ordering and the session state machine's `joining` handling.

Recommended vehicle: `/mission-control:sortie`. Make the pane show a pending join, and keep a slow agent build from blocking the socket. The sortie is not planned yet; link it here when it exists.
