# Squawk 0404: The dev-instance recipe can record a shell wrapper's PID, not the server's

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-23
**Completed**: 2026-11-24

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
`CLAUDE.md` "Behavior-test credential convention": the recipe now sets `S=$HOME/the-one-behavior-test-scratch`
and starts the server as `( cd $S/cwd && THE_ONE_PORT=8486 … exec <repo>/.venv/bin/the-one serve >serve.log 2>&1 ) &`,
then `echo $! > $S/cwd/serve.pid`. `exec` makes the backgrounded subshell become the server, so `$!` is the
server's PID even when the lines are run as one Bash call. One added line explains why and says to confirm
the PID owns the port (`ss -ltnp | grep :8486`, or `/proc/<pid>/cmdline`) before relying on it.
The `tests/behavior/*.md` specs were checked and left alone: their Preconditions already put `cd` on its own
line, so they do not contain the faulty one-liner. Run logs are untouched. No test pins the CLAUDE.md text.

## Verification
Dry run (port 8496, scratch `$HOME/the-one-squawk-0404-scratch`, recipe as written, one Bash call):
- recorded `pid=1768395`; `/proc/1768395/cmdline` = `.../.venv/bin/python3 .../.venv/bin/the-one serve`
- `ss -ltnp | grep :8496` = `LISTEN ... 127.0.0.1:8496 ... users:(("the-one",pid=1768395,fd=18))` (same pid)
- `GET /api/live` = `{"status":"ok"} http=200`
- `kill $(cat serve.pid)`, then port 8496 free; scratch dir removed.
- `tests/test_shell_write_hook.py`: 118 passed.

Acceptance criteria:
The recipe starts the server as its own statement (`cd` on a separate line, or `exec` in a
subshell). It also says to confirm the recorded PID owns the port (`ss -ltnp`) before relying on
it. A dry run in a scratch dir records a PID whose `/proc/<pid>/cmdline` is the server.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; the change is the dev-instance start line, not a credential or gate rule), batch review of squawks 0403, 0404, 0405, 0407, 0408, 0409 and 0410
**Verdict**: confirmed (the recipe is correct as one Bash call; `serve.pid` references are consistent)
**Commit**: `squawk: turnaround 2026-11-24` on squawk/turnaround-2026-11-24
