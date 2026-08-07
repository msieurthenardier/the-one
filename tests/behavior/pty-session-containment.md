# Behavior Test: PTY Session Containment

**Slug**: `pty-session-containment`
**Status**: active
**Created**: 2026-06-06
**Last Run**: 2026-06-07-09-56-42

## Intent

Verify that an interactive PTY session **launched by a tool** is governed by the
shared sandbox boundary on Linux — the fourth spawn path closed by Mission 14
Flight 2. Through the real `shell_session_*` tool surface on a running instance,
the test confirms a session is *capable* within its host-workspace (writes under
the real `$HOME` persist) yet *contained* by OS-level enforcement: writes outside
the filesystem allowlist fail, writes to denylisted secret paths fail, outbound
network is refused, and — crucially for a long-lived `pty.fork()` child wrapped in
bubblewrap — no sandboxed descendant survives after the session closes. This needs
a behavior test rather than a unit test because the property under test is the
real bubblewrap-wrapped PTY running through the actual session-tool path with a
live controlling terminal and kernel-enforced namespaces; `@requires_bwrap`
integration tests (in `tests/test_pty_sandbox.py`) cover the same observables
hermetically, but the mission marks this criterion behavior-test-backed because the
end-to-end tool path is where a regression would actually bite.

## Preconditions

- A `the-one` instance is running and reachable (operator confirms the URL / how
  the Executor drives the agent's tools) — a dedicated dev instance, non-default port
  with a scratch data directory, never the operator's default `:8484` instance.
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" for whichever apparatus reaches the agent's
  tools (e.g. `Authorization: Bearer <credential>` for `POST /api/chat`, or a handoff URL
  if driven through the browser).
- The instance host has `bwrap` on `PATH` (probe: `bwrap --version` succeeds) and
  unprivileged user namespaces available (under Docker: `cap_add: SYS_ADMIN` +
  `security_opt: seccomp:unconfined`). **Probe at run time** — if `bwrap` is
  absent, `get_sandbox_backend()` selects passthrough and this test would
  false-pass against an unsandboxed session; the run skill must confirm bubblewrap
  is the selected backend before judging containment (e.g. the startup log line
  `sandbox backend: bubblewrap` or an equivalent probe).
- An agent is configured whose `ExecutionConfig` enables the `shell_session_*`
  tools (and leaves `sandbox_network_allowed=false`, the default) and whose
  `FilesystemConfig` uses the **default** `path_allowlist` (`["~"]`) and default
  `path_denylist` (includes `~/.ssh`). The Executor drives this agent.
- The host `$HOME` is writable on the host (so the real-HOME-persistence row is a
  true positive, not blocked upstream).
- The denylisted secret path used in Step 5 **exists on the host** before the run.
  The default denylist entry `~/.ssh` is re-mounted read-only by the overlay via
  bwrap `--ro-bind-try`, which **silently skips absent paths** — so if `~/.ssh`
  does not exist, no overlay is emitted, the write lands in the writable `~`, and
  the row would false-PASS the write while false-FAILing the containment assertion.
  **Setup probe**: ensure `~/.ssh` exists (`mkdir -p ~/.ssh`) before the run, or
  point Step 5 at a denylist entry that is known to exist on the host.
- A way to read the host process table (`ps` / `pgrep` via Bash) is available to
  the Executor for the orphan-survival row.

## Observables Required

- shell (interactive session stdout — measured via the `shell_session_send` tool's
  returned output)
- process (host process table for orphan-survival — measured via `ps` / `pgrep`
  via Bash)
- filesystem (persisted file contents read back **inside the session** — measured
  via a follow-up `cat` in the same session)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Start a PTY session via the agent's `shell_session_start` tool with no `cwd` (defaults to `$HOME`). Record the returned `session_id`. | A `session_id` is returned (non-error). The session is alive. |
| 2 | In the session, run `pwd` via `shell_session_send`. | Output shows the real `$HOME` path (e.g. `/root` or `/home/<user>`) — the session landed in the host-workspace home, not an ephemeral `/tmp`. |
| 3 | In the session, write and read back a file under `$HOME`: send `echo pty-canary > ~/.pty_canary_$$  && cat ~/.pty_canary_$$`. | Output contains `pty-canary` — a `~`-relative write **persists** and is readable within the session (real HOME is writable; DD3/DD4). |
| 4 | In the session, attempt a write **outside the allowlist**: send `echo nope > /etc/pty_should_fail`. | Output contains a refusal — `Read-only file system` (or `Permission denied`). The write does **not** succeed: a follow-up `cat /etc/pty_should_fail` reports no such file. Outside-allowlist writes are OS-denied. |
| 5 | In the session, attempt a write to a **denylisted secret path** under HOME: send `echo nope > ~/.ssh/pty_should_fail` (`~/.ssh` is in the default denylist, re-mounted read-only by the overlay). | Output contains `Read-only file system`. The denylist overlay blocks the write. *(Note: the `--ro-bind-try` overlay enforces write-protection, not read-blocking — this row asserts not-writable, not unreadable, per the Flight-1 DD4/DD5 resolution.)* |
| 6 | In the session, inspect the network namespace: send `cat /proc/net/dev` (and optionally `ip addr`). | **Primary (namespace isolation):** only the `lo` loopback interface is present — no `eth0` / external interface — confirming the session is in an isolated network namespace (`--unshare-net`, network deny-by-default). *Rationale (2026-06-07 run): a safety-aligned driving agent will refuse to open a raw outbound socket on command — even to prove the sandbox blocks it — so the live assertion uses the namespace-isolation observable the agent cooperates with. The direct outbound-connect refusal (`ENETUNREACH`) is proven deterministically by `tests/test_pty_sandbox.py` (`@requires_bwrap`); see Out of Scope.* |
| 6b | *(optional, agent-permitting)* In the session, attempt an outbound connection: `python3 -c "import socket; socket.create_connection(('1.1.1.1',53),timeout=3)"`. | *(optional)* If the driving apparatus will run it: output shows `Network is unreachable` / `ENETUNREACH`. If the apparatus (e.g. a safety-aligned agent) refuses, skip — the namespace-isolation check (step 6) plus the `@requires_bwrap` network test already cover this. |
| 7 | Identify **this session's** bwrap before closing: via Bash on the host, find the long-lived bwrap that persists across two `shell_session_send` calls (or match on the session's known shell + cwd) and record both its PID and its child shell PID — do NOT just `pgrep bwrap` (other one-shot tool / MCP spawns also produce transient bwrap processes). Then close the session via `shell_session_close` (or `shell_session_kill`); allow a brief settle (~0.5 s) for async PID-namespace teardown. | `[mixed-frame]` (justified: orphan-survival has no in-session surface — the session is gone after close; the host process table is the only read path). After close returns + settle, the **captured** bwrap PID and its sandboxed shell descendant are **gone** — assert specifically that no process matching the captured PID / child-shell PID survives, not merely "no bwrap at all" (DD5; namespace teardown via `--die-with-parent` + single-pid SIGKILL). |
| 8 | Clean up: via Bash on the host, remove `~/.pty_canary_*` if it persisted on the host (it should, under the real-HOME workspace). | (setup row, no judgment) |

## Out of Scope

- **One-shot shell / Python tool containment** — covered by Flight 1's
  `tests/test_builtin_tool_sandbox.py` (`@requires_bwrap`) and the operator-verified
  live demo in the Flight-1 debrief.
- **MCP stdio server containment** — covered by `tests/test_mcp_sandbox_integration.py`.
- **CLI-vs-web parity** — Mission 14 Flight 3 (`Uniform policy & CLI parity`).
- **Read-scoping** (a session being unable to *read* outside its scope) — deferred
  at the mission level (Flight 1 DD5); this test asserts write/network/teardown
  containment only. A denylisted path being unreadable is **not** asserted.
- **Passthrough behavior** (off-Linux / bwrap-missing) — the unit suite
  (`tests/test_pty_session.py`, pinned to passthrough) covers start/send/close
  under passthrough.
- **macOS / Windows PTY backends** — Mission 15.

## Variants (optional)

- **network-allowed**: re-run with the agent's `ExecutionConfig.sandbox_network_allowed=true`.
  Step 6's expectation flips — the outbound connection **succeeds** (or fails for a
  non-sandbox reason like DNS, not `ENETUNREACH`). All other rows unchanged. Confirms
  the network knob is honored on the PTY path, not hard-wired off.
