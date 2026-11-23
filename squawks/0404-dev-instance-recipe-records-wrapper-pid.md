# Squawk 0404: The dev-instance recipe can record a shell wrapper's PID, not the server's

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-23
**Completed**: —

## Report

When the commands are run as one `cd <dir> && THE_ONE_PORT=… the-one serve … &` list (the way an
agent's single Bash call runs them), the `&` backgrounds the whole `&&` list. `$!` is then a
subshell's PID, not the server's, and "stop by recorded PID" kills the wrapper and can leave the
server running.

It happened twice in the Mission 36 Flight 4 HAT: the dev-instance restart recorded 2003686 (the
server was 2003690), and the key-server fixture recorded 1904882 (the server was 1904884). Both
were caught from `/proc` and the listener before any kill. Found by the Flight 4 debrief.

## Evidence
- `CLAUDE.md` "Behavior-test credential convention": `mkdir -p … && cd …`, then
  `THE_ONE_PORT=8486 … the-one serve >serve.log 2>&1 &` and `echo $! > serve.pid`.
- `missions/36-gleepglorp-assistant/flights/04-mcp-servers-and-providers/flight-log.md`, the Leg 8
  "Dev instance restart" and "Key server" entries.

## Corrective Action
*(written at completion)*

## Verification
The recipe starts the server as its own statement (`cd` on a separate line, or `exec` in a
subshell). It also says to confirm the recorded PID owns the port (`ss -ltnp`) before relying on
it. A dry run in a scratch dir records a PID whose `/proc/<pid>/cmdline` is the server.
