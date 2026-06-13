# Behavior Test: Windows PTY Parity (ConPTY)

**Slug**: `windows-pty-parity`
**Status**: draft
**Created**: 2026-06-14
**Last Run**: never

## Intent

Verify that interactive PTY-backed `shell_session_*` tools work at **feature
parity on real Windows** — through the actual tool surface on a `the-one`
instance running on Windows, driving a real `cmd.exe` via ConPTY (`pywinpty`).
This is the mission's "PTY parity (behavior-test-backed)" criterion (DD8): the
`windows-2022` CI lane covers `WindowsPtySession` at the unit level
(`tests/test_pty_windows.py` — 7 always-passing functional tests + 2
`xfail`/best-effort orphan-reap tests), but the mission marks the criterion
behavior-test-backed because the **end-to-end tool path on real Windows
hardware** — a live controlling pseudoconsole, persistent interactive shell
state across sends, and real process teardown — is where a regression would
actually bite. **This test also resolves the Leg-3 DD-OQ** that CI could not
reliably exercise (the grandchild-launch-through-PTY harness was flaky): the
orphan-reap row below is the **definitive** check that the Win32 Job Object
(`KILL_ON_JOB_CLOSE`) reaps a backgrounded grandchild when the session closes.

Windows ships sandbox-**passthrough** (the mission's documented gap, DD9) — so
this test verifies *functional* parity (spawn, persistent state, output,
teardown), NOT containment. Containment is Linux-only (`pty-session-containment`).

## Preconditions

- A `the-one` instance is running on a **real Windows host** (Windows 10 1809+
  for ConPTY) and reachable; the operator confirms the URL / how the Executor
  drives the agent's tools. (Install path today: `pip install -e ".[all-llms,dev]"`
  on Windows Python 3.11+; `pywinpty` installs from its win_amd64 wheel. The
  packaged installer is Flight 5.)
- The sandbox backend resolves to **passthrough** on Windows (expected — the
  factory returns passthrough on non-Linux). This is NOT a containment test; do
  not assert isolation.
- An agent is configured whose `ExecutionConfig` enables the `shell_session_*`
  tools. The Executor drives this agent.
- A way to read the **Windows process table** is available to the operator/Executor
  for the orphan-reap row — `tasklist` (e.g. `tasklist /FI "PID eq <pid>"`) or
  Task Manager.

## Observables Required

- shell (interactive session stdout — measured via the `shell_session_send`
  tool's returned output)
- process (Windows process table for orphan-reap — measured via `tasklist`)
- filesystem (a file written + read back **inside the session** — measured via a
  follow-up `type` in the same session)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Start a PTY session via the agent's `shell_session_start` tool (no `cwd`). Record the returned `session_id`. | A `session_id` is returned (non-error). The session is alive. cmd.exe started under ConPTY. |
| 2 | In the session, run `echo hello` via `shell_session_send`. | Output contains `hello` — the round-trip works through real ConPTY. |
| 3 | In the session, run `set FOO=bar`, then in a SEPARATE `shell_session_send` run `echo %FOO%`. | The second send's output contains `bar` — **interactive state persists across sends** (the core persistent-PTY property vs a one-shot spawn; proves it's a live session, not per-command processes). |
| 4 | In the session, run `cd`. | Output shows a Windows-format path (e.g. `C:\Users\<user>`) — the session has a real cwd, native path form (not an MSYS `/c/...` path). |
| 5 | In the session, write then read back a file: send `echo win-canary> %TEMP%\winpty_canary.txt`, then `type %TEMP%\winpty_canary.txt`. | The `type` output contains `win-canary` — a write persists and is readable within the session. |
| 6 | **Orphan-reap (the definitive DD-OQ check):** in the session, launch a backgrounded grandchild that outlives the command — send `start /b "" timeout /t 120 /nobreak`. Via `tasklist` on the host, find the `timeout.exe` PID spawned by this session and record it (confirm it is running). | A `timeout.exe` grandchild is running (PID recorded). `[mixed-frame]` (justified: process-table is the only read path for teardown — the session is gone after close). |
| 7 | Close the session via `shell_session_close`; allow a brief settle (~1 s). Then re-check the recorded `timeout.exe` PID via `tasklist /FI "PID eq <pid>"`. | The recorded `timeout.exe` PID is **GONE** (`tasklist` reports "No tasks") — the Win32 Job Object's `KILL_ON_JOB_CLOSE` reaped the whole tree when the session's job handle closed. **This is the definitive orphan-reap verification deferred from Leg 3.** Also: `shell_session` reports the session no longer alive. |
| 8 | *(optional, parent-death variant — operator-permitting)* Repeat 6, then instead of `shell_session_close`, **hard-kill the `the-one` process** (Task Manager → End Task, or `taskkill /F`). Re-check the grandchild PID. | *(optional)* The `timeout.exe` grandchild is **gone** — the OS auto-closed the job handle on process death (`KILL_ON_JOB_CLOSE` fires without `close()` ever running). Confirms the parent-death reap guarantee (the xfailed CI test). |
| 9 | Clean up: remove `%TEMP%\winpty_canary.txt` if it persisted. | (setup row, no judgment) |

## Out of Scope

- **Containment / isolation** — Windows ships passthrough (DD9, documented gap);
  this test asserts functional parity + teardown only, NOT that the session is
  contained. Linux containment is covered by `pty-session-containment`.
- **The unit-level `WindowsPtySession` contract** — covered hermetically by
  `tests/test_pty_windows.py` (`windows-2022` CI, nt-gated): start/send/close,
  idle-readiness, state persistence, send-after-close, last_activity.
- **`run_shell` (non-PTY) timeout tree-kill** — a known Windows gap (mission
  Known Issues): the one-shot shell timeout fires but does not promptly reap its
  child tree. This test covers the **PTY** path (Job Object), not `run_shell`.
- **macOS PTY** — Mission 15 Flight 2 (parked) / future.

## Variants (optional)

- **PowerShell shell**: re-run with the session shell overridden to
  `powershell.exe` (if/when supported) — cmd.exe is the default this flight.
