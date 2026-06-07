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

## Flight Director Notes

- **2026-06-06 — Orchestration start (`/agentic-workflow`).** Phase file
  `leg-execution.md` loaded and validated (Crew / Interaction Protocol / Prompts
  present; crew = Developer/Sonnet, Reviewer/Haiku). Flight 1 confirmed merged to
  `main` (PR #103), so branched `flight/02-pty-through-seam` from `main` (carries
  the seam Flight 2 composes with). Planning artifacts committed (`5853cab`); flight
  → `in-flight`. Total autonomous legs: 4 (`pty-platform-seam`, `pty-tool-wiring`,
  `pty-containment-tests`, `verify-integration`) + 1 optional interactive
  (`uat-and-alignment`). Review + commit deferred to after the last autonomous leg
  per the batched workflow.
- **Reviewer model decision (pre-registered):** the Flight-1 debrief standardized
  "scale Reviewer model to diff risk/size (never Opus)" — this flight is equally
  security-critical (PTY sandbox boundary). The Phase-2d flight review Reviewer will
  be **Sonnet**, not the crew-default Haiku, for the same reason Flight 1 did so.
- **2026-06-06 — Phase 2d (review + commit).** Spawned a single Reviewer (Sonnet,
  per the decision above) over the full uncommitted diff. Verdict
  **`[HANDOFF:confirmed]`**, no blocking issues. Security review confirmed: `SpawnSpec`
  computed parent-side before `pty.fork()` (fork-safe); child execs cleanly through the
  spec; passthrough reproduces today's behavior; teardown operates on the local `pid`
  with `--die-with-parent` preserved; **no code path leaves a tool-launched PTY
  unsandboxed on a bwrap host**; the five `@requires_bwrap` containment tests have no
  false-pass paths. One non-blocking nit (orphan test binds `session` inside `try` —
  harmless, the `NameError` is caught). Marked Legs 1-4 `completed`, checked them off in
  `flight.md`, committed code + artifacts.
- **Remaining before flight landing** (both need the operator / live apparatus): (1) the
  live `/behavior-test pty-session-containment` — Flight-Director-run, gated on
  confirming the act-path drive surface (running instance + an agent with the
  `shell_session_*` tools reachable by the Executor); (2) the optional
  `uat-and-alignment` HAT leg (interactive). The `@requires_bwrap` arm already proves
  containment hermetically; the behavior test is the mission's additional gate.

## Leg Progress

### pty-platform-seam (Leg 1)

**Status**: landed
**Date**: 2026-06-06

**Changes Made**:
- `the_one/platform/pty.py`: Added `profile: SandboxProfile | None = None` param to `UnixPtySession.__init__` and `create_pty_session`. Added `self._profile` and `self._wrapped: bool = False` instance vars. Rewrote `start()` to compute `SpawnSpec` in the parent (before `pty.fork()`) via function-level-imported `get_sandbox_backend()` + `SandboxProfile`, then exec through the spec in the child (replacing the inline `_build_subprocess_env()` / bare `execvp`). Rewrote `_close_blocking` to branch on `self._wrapped`: SIGKILL-fast + blocking `waitpid` for bwrap; SIGTERM→1s→SIGKILL for passthrough. Added DD9 code comment about `--die-with-parent` / no-killpg dependency. All changes operate on the local `pid` variable (never `self._pid` after nilling).
- `tests/test_pty_session.py`: Added function-scoped autouse `_pin_to_passthrough` fixture (`monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")`). Updated stale `test_env_allowlist_invariant` docstring to reflect that env is now captured in the parent inside `start()`, not the child post-fork.
- `tests/test_pty_sandbox.py` (new): `@requires_bwrap` orphan-survival test — starts a real bwrap-wrapped session, backgrounds `sleep 30`, captures grandchild PIDs via host `pgrep`, `close()`s the session, settles 0.5s test-side, asserts all new `sleep 30` PIDs are gone. Includes comment on `--unshare-pid` / host-pgrep visibility.
- `tests/test_session_tools.py`: Pinned `test_end_to_end_real_pty_round_trip` to passthrough (`monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")`) — the test uses `tmp_path` (under `/tmp`), which bwrap's `--tmpfs /tmp` shadows, making the workspace invisible without a real profile. Leg 2 will remove this pin when it supplies a profile through `ShellSessionStartTool`.

**Test Results**:
- `tests/test_pty_session.py`: **16 passed, 1 skipped** (Windows guard) in 13.83s
- `tests/test_pty_sandbox.py -m requires_bwrap`: **1 passed** in 0.93s
- `tests/test_session_tools.py tests/test_session_lifecycle.py`: **41 passed** in 7.56s
- `ruff check` + `ruff format --check`: clean across all changed files

**Notes**:
- The orphan-survival test passes cleanly: `pids_before=set()`, `pids_after_spawn={'<pid>'}`, `pids_after_close=set()` — confirming SIGKILL on the bwrap-outer + `--die-with-parent` reaps the whole PID namespace, including the `sleep 30` grandchild.
- Deviation: `test_session_tools.py:test_end_to_end_real_pty_round_trip` required a passthrough pin. This was not in the leg plan but is necessary because Leg 1 now routes PTY through bwrap even with no profile (strict cage = `/tmp` not writable), and `sessions.py` (Leg 2) doesn't supply a profile yet. The pin is marked for removal in Leg 2.
- `profile` param is typed `object | None` at the module-level signatures (avoiding a top-level import of `SandboxProfile`) and uses a function-level import inside `start()` to mirror `platform/shell.py:123` — no import cycle risk.

### pty-tool-wiring (Leg 2)

**Status**: landed
**Date**: 2026-06-06

**Changes Made**:
- `the_one/tools/sessions.py`: Added `_build_tool_profile` to the `from the_one.tools.execution import (…)` block. In `ShellSessionStartTool.execute`, after `canonical_cwd = _cwd_check(target_cwd, fs_cfg)`, added `profile = _build_tool_profile(fs_cfg, exec_cfg)` and updated the call to `create_pty_session(cwd=canonical_cwd, profile=profile)`. The `Path | None` comment above the call was left intact.
- `tests/test_session_tools.py`: Updated all four `create_pty_session` monkeypatch lambdas (lines 67, 93, 113, 134) to `lambda cwd=None, shell=None, profile=None: MockPtySession()` — signature fix only, not passthrough-pinning. Updated the `test_end_to_end_real_pty_round_trip` docstring to reflect the accurate rationale: the pin is permanent because bwrap mounts a fresh tmpfs at `/tmp` that shadows any `tmp_path` workspace, regardless of profile; this is a tool-layer round-trip test, not a containment test (real-bwrap containment covered by `test_pty_sandbox.py` + behavior spec).
- `tests/test_execution_tools.py`: Added `_build_tool_profile` to the `from the_one.tools.execution import (…)` statement. Added `test_build_tool_profile_default_allowlist` — unit test asserting `writable_paths == [str(Path.home())]`, `readonly_overlay_paths == [str(p) for p in FilesystemConfig()._canonical_denylist]`, `network_allowed is False`, `home == str(Path.home())`.

**Test Results**:
- `tests/test_session_tools.py`: **20 passed** in 1.27s
- `tests/test_execution_tools.py`: **30 passed** in 5.15s (incl. new `_build_tool_profile` unit test)
- `tests/test_pty_session.py`: **16 passed, 1 skipped** in 13.80s (Leg 1 regression — no regressions)
- `ruff check` + `ruff format --check`: clean across all three touched files

**Notes**:
- No deviations from the leg plan. All four lambda signatures were updated by a single `replace_all` edit (they shared the same `lambda cwd=None, shell=None: MockPtySession()` form). The round-trip pin rationale comment now correctly describes the permanent `/tmp` tmpfs shadow reason rather than the stale "until Leg 2 wires the profile" framing. The `_build_tool_profile` unit test required no passthrough fixture since the function never calls the sandbox factory.

### pty-containment-tests (Leg 3)

**Status**: landed
**Date**: 2026-06-06

**Changes Made**:
- `tests/test_pty_sandbox.py`: Appended four `@pytest.mark.requires_bwrap` containment tests to the existing file (orphan-survival from Leg 1 retained):
  - `test_pty_write_outside_allowlist_denied` — workspace + sibling both created explicitly on host; profile `writable_paths=[workspace]`; write into sibling via `send`; host-FS assertion `not target.exists()`.
  - `test_pty_denylist_secret_write_denied_sibling_allowed` — `secret/key` created with "original-content"; profile `readonly_overlay_paths=[secret_dir]`; overwrite attempt; host-FS assertion content unchanged; sibling write asserted present.
  - `test_pty_network_denied_by_default_allowed_when_enabled` — host loopback TCP server (thread + `SO_REUSEADDR` + `stop_event`); non-interactive `/bin/sh` session; single-line `python3 -c '...'` probe using string-concat trick (`"con"+"nected"`) to keep the literal sentinel out of the PTY-echoed command text; deny → assert `"connected" not in out`; allow → assert `"connected" in out`.
  - `test_pty_real_home_persistence` — `monkeypatch.setenv("HOME", str(workspace))`; profile `home=str(workspace)`, `writable_paths=[workspace]`; `echo pty-home-canary > ~/canary.txt`; host-FS assertion on `workspace/"canary.txt"`.
- Module docstring updated to cover the four new test groups.
- Added imports: `socket`, `threading`.

**Test Results**:
- `docker exec the-one pytest tests/test_pty_sandbox.py -m requires_bwrap -x --timeout 90`: **5 passed** in 4.13s (orphan + 4 new)
- `--collect-only -m requires_bwrap`: all 5 collected; deselected (5/5) without marker (confirms `requires_bwrap` on all)
- `ruff check` + `ruff format --check`: clean

**Notes**:
- **Network test sentinel deviation:** The initial probe used `print('connected')` literally in the command string. The PTY echoes the input back, so the echoed command itself contained the word "connected" — causing the deny-path assertion (`"connected" not in out`) to false-fail (Connection Refused was returned correctly, but the assertion failed on the echoed command text). Fixed by encoding the sentinel as `"con"+"nected"` in the Python probe source, so the literal word "connected" only appears in the stdout output line (on success), not in the echoed command. The deny and allow assertions are now correctly discriminating.
- No other deviations. All host-FS assertions use `Path.exists()` / `.read_text()` with no `time.sleep` settle (bwrap `--bind` writes are kernel-synchronous per the spec's Implementation Guidance).

### verify-integration (Leg 4)

**Status**: landed
**Date**: 2026-06-06

**Changes Made**:
- `SECURITY-MODEL.md` (§ Tool Execution Boundary): Updated the "Subprocess environment" bullet — removed the stale parenthetical "(PTY sessions are not yet wired through the seam)"; stated that `UnixPtySession` now builds `_build_subprocess_env()` in the parent and passes it through `get_sandbox_backend().prepare_spawn(...)` identically (M14 F2). Updated the "OS-level execution fence" bullet from "(M14 F1)" to "(M14 F1+F2)"; expanded the spawn path list from two to all four (`shell`, `python_exec`, MCP stdio, PTY `shell_session_*`); added one sentence on PTY teardown (`--die-with-parent` + single-pid SIGKILL → kernel PID-namespace teardown reaps `setsid`'d grandchildren); added one sentence on the deliberate `--new-session` omission and its accepted `TIOCSTI` tradeoff.
- `the_one/agents.md`: (a) Added new `### the_one/platform/sandbox/` subsection (four modules: base/factory/bubblewrap/passthrough; the `prepare_spawn → SpawnSpec` contract; backend selection via `get_sandbox_backend()`; all four spawn sites funnel through it). (b) Updated `### Sandbox seam — platform-wide (M14 F1, authoritative …)` heading → `M14 F1+F2`. (c) Updated the **Scope** paragraph: "Three spawn paths" → "Four spawn paths", dropped future-tense "wired in Flight 2 of M14". (d) Updated `Call sites (M14 F1 update):` → `M14 F1+F2 update` and the `pty.py::UnixPtySession` bullet "not yet wired" → now wired through the seam (parent-side `_build_subprocess_env()` via `prepare_spawn`).
- `CLAUDE.md` (line 131): Updated `requires_bwrap` count from "7 tests: 5 built-in containment + 2 MCP pool integration" → "12 tests: 5 built-in containment + 2 MCP pool integration + 5 PTY containment (`test_pty_sandbox.py`)". No other stale PTY/shell_session unsandboxed claim found in CLAUDE.md.
- `pyproject.toml` (line 75): Updated comment-only deselect-math from `requires_bwrap=7 … total=552` → `requires_bwrap=12 … total=557`. The `addopts` line was not touched.

**Test Results**:
- **Full default suite** (`docker exec the-one pytest --timeout 60`): **3008 passed, 4 skipped, 557 deselected**, 3 warnings in 303.91s. Delta vs Flight-1 baseline (3007 passed / 4 skipped / 552 deselected): +1 passed, +5 deselected (as expected: 5 new `@requires_bwrap` PTY tests added to deselected count). No regressions. 1 warning was `PytestUnhandledThreadExceptionWarning` on aiosqlite event-loop-closed — pre-existing unrelated to this flight.
- **`-m requires_bwrap`** (`docker exec the-one pytest -m requires_bwrap --timeout 90`): **12 passed, 3557 deselected** in 9.97s. All 12 green: 5 built-in containment (`test_builtin_tool_sandbox.py`) + 2 MCP pool integration (`test_mcp_pool.py`) + 5 PTY containment (`test_pty_sandbox.py`).
- **ruff gate** (`ruff check .` + `ruff format --check .`): clean. `ruff check`: "All checks passed!"; `ruff format --check`: "440 files already formatted".
- No `test_connectors_e2e.py::test_e2e_full_lifecycle` failure observed; no re-run required.

**Notes**:
- All three verification greps returned clean: `grep "not yet wired|wired in Flight 2|Three spawn paths" agents.md SECURITY-MODEL.md` → empty; `grep "not yet wired|not wired through the seam" SECURITY-MODEL.md` → empty; `grep "requires_bwrap" CLAUDE.md pyproject.toml` → counts read 12 and 557.
- `platform/sandbox/` subsection insertion point: placed immediately before `### MCP error translation`, after the existing sandbox seam numbered-list items — matches the doc's existing convention-entry style for architecture subsections.
- pyproject.toml comment updated only (label changed from "last verified L5" → "last verified L4 F2" to track when the math was last recalculated).

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
