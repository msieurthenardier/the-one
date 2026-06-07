# Flight Log: PTY Through the Seam

**Flight**: [PTY Through the Seam](flight.md)

## Summary

Flight is `ready` (design-reviewed, operator-approved). This log is ready for
execution notes. The planning-time seam reconnaissance and the behavior-test
apparatus audit are recorded below so the crew inherits them.

---

## Planning Reconnaissance (seam still composes)

This flight's "source" is Flight 1's debrief (carry-forward recommendations), not a
maintenance report enumerating file:line work items — so no formal Reconnaissance
Report. The cited locations the flight depends on were verified live against current
code during planning:

| Cited item | Classification | Evidence | Note |
|---|---|---|---|
| PTY child execs unsandboxed | confirmed-live | `the_one/platform/pty.py:192-222` (`os.chdir` → `os.environ.clear/update(_build_subprocess_env())` → `os.execvp(shell, [shell, "-i"])`) | The fourth, still-unsandboxed spawn path. |
| Seam ready to compose | confirmed-live | `prepare_spawn → SpawnSpec` (`platform/sandbox/base.py:260`), `BubblewrapSandbox.prepare_spawn` emits `bwrap … -- cmd *args` (`bubblewrap.py:75-153`) | The argv the PTY child must exec is exactly what `prepare_spawn` returns. |
| Profile reuse hook | confirmed-live | `_build_tool_profile(fs_cfg, exec_cfg)` (`tools/execution.py:424`) | Gives PTY the real `$HOME` + one policy source. |
| Tool-layer wiring point | confirmed-live | `ShellSessionStartTool.execute` → `_cwd_check` → `create_pty_session(cwd=…)` (`tools/sessions.py:104-148`) | Where the profile gets threaded in. |
| bwrap-as-PID-1 teardown semantics | needs-human-recheck | `--unshare-pid` / `--die-with-parent` in `bubblewrap.py:110-118` | Whether SIGTERM reaches the shell through bwrap-PID-1 is a runtime fact → drives the deferred teardown open question; gated by the orphan-survival test. |

---

## Behavior-Test Apparatus Audit (both axes — act AND observe)

Per the flight skill's Phase-4 requirement to premise-audit the verification
apparatus on **both** the act and observe axes, with code citations, before locking
the apparatus design decision (DD6). The behavior test is `pty-session-containment`.

**Act axis (can the apparatus drive the system as a real actor would?)**
- **Yes.** The Executor drives a tool-launched PTY session through the agent's
  `shell_session_start` / `shell_session_send` tools on a running instance
  (`tools/sessions.py:104-148`, `:155-…`). This is the exact surface the mission
  criterion names ("a PTY session **launched by a tool**"). bwrap is present on the
  host (bubblewrap 0.9.0) and the Docker grant (`SYS_ADMIN` + `seccomp:unconfined`)
  satisfies unprivileged-userns, so `get_sandbox_backend()` selects bubblewrap and
  the driven session is really sandboxed — not a passthrough no-op.

**Observe axis (can the apparatus read, through an existing surface, everything the
acceptance criteria must assert?)**
- **In-band (shell frame) — yes.** `shell_session_send` returns the session's raw
  output bytes to the caller (`tools/sessions.py` send path; `UnixPtySession.send`
  returns `bytes`, `platform/pty.py:249-270`). So the containment observables are
  read straight from the tool result:
  - write-outside-allowlist → shell prints `Read-only file system` / `Permission denied`
  - outbound connection → shell/python prints `Network is unreachable` (`ENETUNREACH`)
  - `~`-relative write persists → a follow-up `cat` in the session returns the bytes
- **Out-of-band (process frame) — yes, via host `ps` [mixed-frame, justified].**
  Orphan-survival after `close()` has **no in-band surface** (the session is gone),
  so it is read out-of-band with the host `ps`/`pgrep` apparatus (Bash). This is a
  legitimate cross-frame read (verifying an internal teardown contract the user
  can't see); the `pty-session-containment` spec marks that row `[mixed-frame]`.
- **Read path is pre-existing** — no test-only seam needs to be added to *observe*
  the state under test (the failure mode the skill warns about): the session output
  is already returned by the tool, and the process table is a standard host surface.

Both axes pass at planning with citations → DD6 (live behavior test +
`@requires_bwrap`) is locked.

---

## Design Review (Phase 5b)

**Architect verdict**: *approve with changes* (1 cycle). The Architect read the real
codebase and **confirmed the core composition is correct**: DD1 child-side exec
(slave-PTY fds + controlling tty survive `execvp("bwrap", …)` because bwrap keeps
fds 0/1/2 and emits no `--new-session`; `waitpid(self._pid)` reaps the bwrap-outer
pid); passthrough reproduces today's child behavior byte-for-byte (so no
`test_pty_session.py` assertion breaks under the pin, incl. `test_env_allowlist_invariant`);
the env allowlist is preserved through `prepare_spawn`; and `_build_tool_profile`
needs no PTY-specific field changes.

**Deferred teardown question — Architect resolution** (operator had deferred it to
the architect): keep **single-pid kill** (not killpg) — `--die-with-parent` +
PID-namespace teardown on SIGKILL is strictly stronger than Flight 1's killpg and
reaps `setsid`'d grandchildren killpg would miss; use **SIGKILL-fast on the wrapped
path** (SIGTERM doesn't reach the inner shell through bwrap) with a confirm-reaped
settle; keep SIGTERM-first on passthrough. Baked into the resolved Open Question +
DD5/DD9.

**Changes incorporated** (all from the review):
- **[high]** Leg `pty-tool-wiring` corrected: `test_session_tools.py` mocks
  `create_pty_session` via lambdas (`:67,93,113,133`) — the fix is updating the
  lambda signature to accept `profile=None`, **not** passthrough-pinning (verified
  the file; the mock never reaches the factory). A literal reading of the old leg
  text would have shipped red tests (`TypeError`).
- **[medium]** Orphan-survival `@requires_bwrap` test **moved into `pty-platform-seam`**
  (the leg that implements the kill code) so the leg self-validates — was split into
  the later containment-tests leg.
- **[medium]** Denylist containment row/test must **materialize the denylisted dir
  explicitly** rather than rely on the default `~/.ssh` existing (`--ro-bind-try`
  silently skips absent paths → false-pass). Fixed in Leg `pty-containment-tests`
  and the behavior spec's Preconditions.
- **[low]** Orphan-survival assertion now targets **this session's specific bwrap**
  (by child shell PID), not "no bwrap at all" — avoids flakiness under concurrent
  one-shot/MCP bwrap spawns. Fixed in DD5 + behavior spec Step 7.
- **Suggestions** folded: keep the unified `if spec.cwd: os.chdir(...)` (required for
  passthrough) — noted in DD1; document the deliberate absence of `--new-session`
  + the `TIOCSTI` tradeoff in `SECURITY-MODEL.md` — added to `verify-integration`.
- **Open question** raised by the Architect: confirm the behavior-test **drive
  surface** (how the Executor invokes `shell_session_*` against the running
  instance) before `verify-integration` — added to the apparatus prerequisite. The
  host-crash orphan window (bwrap-outer not tied to the Python app) is a pre-existing
  cross-path gap, recorded as a mission-level open item (DD9 known limitation).

Second review cycle **skipped**: the changes are faithful applications of the
Architect's own file:line-cited prescriptions (leg-text corrections, test placement,
behavior-spec setup rows) — they do not alter the architecture the Architect already
validated. (Within the skill's "skip second pass for minor/prescribed fixes" allowance.)

---

## Mission-Level Open Items (surfaced this flight)

- **Host-crash PTY orphan window**: `--die-with-parent` ties the *inner* shell to
  the bwrap-outer process, but bwrap-outer is not tied to the Python app, so an app
  crash without `close()` relies on the registry reaper/lifespan shutdown to reap a
  long-lived PTY bwrap tree. Pre-existing across all four spawn paths; larger window
  for PTY. Candidate for the mission's end-of-mission maintenance pass / a hardening
  flight.

---

## Leg Progress

_None yet._

---

## Decisions

_Runtime decisions not in the original plan will be recorded here._

---

## Deviations

_Departures from the planned approach will be recorded here._

---

## Anomalies

_Unexpected issues will be recorded here._

---

## Session Notes

- **Planning (2026-06-06)**: Flight created from Mission 14 + Flight 1 debrief
  carry-forwards. Operator decisions: verification = live behavior test +
  `@requires_bwrap`; PTY path = single-path through the seam (retire dual-path
  debt); PTY teardown/kill strategy under bwrap-as-PID-1 = deferred to the
  Phase-5b Architect + `pty-platform-seam` leg design (orphan-survival test gates
  either choice); include the optional HAT/alignment leg.
