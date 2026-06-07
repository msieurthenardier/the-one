# Flight: PTY Through the Seam

**Status**: completed
**Mission**: [Unified Tool-Execution Sandbox](../../mission.md)

## Contributing to Criteria
- [ ] All four subprocess spawn paths route through one shared sandboxing
      boundary *(this flight adds the **fourth** — PTY sessions; shell, Python,
      MCP stdio landed in Flight 1)*
- [ ] An interactive **PTY session** launched by a tool is governed by the same
      boundary on Linux *(behavior-test-backed — `pty-session-containment`)*
- [ ] On a platform with no sandbox backend, the PTY path runs through the shared
      seam via a passthrough and does not error *(single-path: passthrough
      reproduces today's behavior)*
- [ ] The sandbox policy is applied uniformly to PTY sessions and the other tool
      spawns from one policy source *(reuses `_build_tool_profile`)*
- [ ] Existing behavior preserved: PTY sessions still start / send / close, tests
      pass, ruff gate passes

---

## Pre-Flight

### Objective

Route the fourth and last unsandboxed spawn path — the interactive PTY session
(`pty.fork()` + child-side `execvp`) — through the shared sandbox seam built in
Flight 1, so a tool-launched shell session is governed by the same bubblewrap
boundary on Linux as the one-shot shell/Python tools. The composition wraps the
**child-side exec**: the parent computes a `SpawnSpec` via
`get_sandbox_backend().prepare_spawn(...)` *before* `pty.fork()` (the factory
touches logging/locks that are not fork-safe), and the forked child execs the
wrapped command (`bwrap … -- <shell> -i` on Linux; the bare shell under
passthrough). The PTY session reuses Flight 1's `_build_tool_profile()` so it
lands on the same host-workspace profile (writable allowlist, read-only denylist
overlay, real `$HOME`, network deny-by-default). Unlike Flight 1's shell/Python
retrofit, the PTY path is **single-path through the seam** — passthrough
reproduces today's behavior off-Linux / bwrap-missing — retiring the dual-path
debt Flight 1's debrief flagged. PTY containment is verified two ways: a live
`/behavior-test pty-session-containment` (the mission's behavior-test gate) **and**
`@requires_bwrap` integration tests, including an orphan-survival-after-close test.

### Open Questions
- [x] Composition shape — **wrap the child-side exec**, not restructure the
      session → DD1 (resolves the mission's heaviest open question, "PTY
      composition")
- [x] `profile`-opt-in dual-path vs single-path → **single-path through the seam**
      (DD2); pins existing PTY unit tests to passthrough (DD7)
- [x] Verification apparatus → **live behavior test + `@requires_bwrap`** (DD6);
      the live test honors the mission's "behavior-test-backed" wording, the
      integration tests give a deterministic inner loop
- [x] Profile derivation → **reuse `_build_tool_profile(fs_cfg, exec_cfg)`** (DD3),
      so PTY gets the real `$HOME` and the same policy source as shell/Python
- [x] Env handling → child env comes from `SpawnSpec.env` (= `_build_subprocess_env()`
      passed into `prepare_spawn`, re-applied by bwrap `--clearenv`/`--setenv`);
      preserves F4 Decision-10 env allowlist (DD4)
- [x] **PTY teardown / kill strategy under bwrap-as-PID-1** → **resolved by the
      Phase-5b Architect** (operator deferred this to the architect): keep the
      **single-pid kill** (NOT killpg) — `--die-with-parent` ties the inner PID-1
      shell to the bwrap-outer pid (`self._pid`) via `PR_SET_PDEATHSIG=SIGKILL`, so
      SIGKILL-of-bwrap triggers kernel PID-namespace teardown that reaps **every**
      process in the namespace, including grandchildren that `setsid`'d away (which
      killpg would miss) — strictly stronger than Flight 1's killpg. On the wrapped
      path, **SIGKILL-fast** (skip the SIGTERM grace, since bwrap does not forward
      SIGTERM to the inner shell so the 1 s grace would always elapse); keep
      SIGTERM-first on the passthrough path to preserve today's graceful behavior.
      Add a brief **confirm-reaped settle** after the bwrap reap (the namespace
      teardown is async relative to `waitpid(bwrap_pid)`), mirroring Flight 1's
      `time.sleep(0.5)` in the orphan test, so the orphan-survival assertion is
      deterministic. `--die-with-parent` is load-bearing — DD9 records it so a
      future profile change can't silently drop it. Gated by the orphan-survival
      `@requires_bwrap` test (DD5), which lands in the **same leg** as the kill code
      (`pty-platform-seam`) so the leg self-validates.

### Design Decisions

**DD1 — Wrap the child-side exec; compute the `SpawnSpec` in the parent.**
- The parent calls `get_sandbox_backend().prepare_spawn(profile, shell, args,
  env, cwd)` **before** `pty.fork()` and stashes the resulting `SpawnSpec`. The
  forked child branch is rewritten to `os.chdir(spec.cwd)` → `os.environ.clear()`
  → `os.environ.update(spec.env)` → `os.execvp(spec.command, [spec.command,
  *spec.args])`. On Linux `spec.command == "bwrap"`; under passthrough
  `spec.command == <shell>` (today's behavior, unchanged).
- Rationale: `prepare_spawn → SpawnSpec` already emits exactly the argv the child
  must exec; the only new work is exec-ing it inside the PTY child instead of via
  `create_subprocess_exec`. No session restructure. Resolves the mission's
  heaviest open question ("wrap the child-side exec in the backend, or restructure
  the session").
- **Fork-safety**: `prepare_spawn` and `get_sandbox_backend()` run in the parent
  only. The factory emits a one-time log and reads module-level state; calling it
  post-`fork()` in the child risks a logging-lock deadlock. Computing the spec
  pre-fork is a correctness requirement, not a style choice.
- Trade-off: the child branch changes shape (no longer chdir-then-clear-then-exec
  the bare shell); the existing `cwd` / env-allowlist behaviors are preserved
  *through* the spec rather than inline.
- **Keep the unified `if spec.cwd is not None: os.chdir(spec.cwd)` in the child.**
  It is redundant on the bwrap path (bwrap re-applies `--chdir`,
  `bubblewrap.py:143`) but **required** for passthrough (no bwrap to chdir) — do not
  "optimize" it away or passthrough cwd silently breaks. (Architect note.)
- **Slave-PTY fds + controlling tty survive the `execvp("bwrap", …)`.** Verified
  (architect): `pty.fork()` sets fds 0/1/2 to the slave + `setsid`/`TIOCSCTTY`;
  fds 0/1/2 are not CLOEXEC and bwrap passes them through; the bubblewrap backend
  emits **no `--new-session`** (`bubblewrap.py`), so the controlling tty is kept and
  interactive send/read works. After exec, `self._pid` is the bwrap-outer pid (a
  direct child of the Python process), so `is_alive`'s `os.waitpid(self._pid,
  WNOHANG)` (`pty.py:290`) still reaps correctly when the inner shell exits.

**DD2 — Single-path through the seam (retire the dual-path debt).**
- `UnixPtySession.start()` **always** routes through
  `get_sandbox_backend().prepare_spawn(...)`. There is no `profile is None` legacy
  branch that bypasses the seam (the divergence Flight 1 kept in `platform/shell.py`
  / `platform/interpreter.py`). When the selected backend is `PassthroughSandbox`,
  the returned `SpawnSpec` is the unwrapped shell — byte-for-byte today's behavior.
- Rationale: the debrief explicitly flagged the dual codepath as "permanent
  dual-path debt — decide it in the Flight 2 spec, not during a leg." A single
  execvp codepath is simpler to reason about than `run_shell`'s branch and removes
  the debt rather than propagating it.
- Trade-off: more unit-test churn now — `test_pty_session.py` constructs
  `UnixPtySession()` bare and asserts the env-allowlist / cwd round-trip; routed
  through the factory it would hit **real bwrap** on a bwrap host. Those tests are
  pinned to passthrough (DD7).

**DD3 — Reuse `_build_tool_profile(fs_cfg, exec_cfg)` for the PTY profile.**
- `ShellSessionStartTool.execute` builds the profile from its `FilesystemConfig`
  + `ExecutionConfig` via the same `_build_tool_profile()` the one-shot tools use
  (`tools/execution.py:424`) and threads it into `create_pty_session(cwd=…,
  profile=…)`.
- Rationale: one policy source for all four spawn types (mission criterion); the
  PTY session inherits the host-workspace profile — writable = allowlist,
  read-only denylist overlay, **real `$HOME`** (so `~`-relative writes in the
  interactive session persist), network deny-by-default. The debrief's
  Recommendation 1 named this reuse explicitly.

**DD4 — Env via `SpawnSpec.env`; F4 Decision-10 allowlist preserved.**
- The parent passes `_build_subprocess_env()` (the eight-key allowlist) as the
  `env` argument to `prepare_spawn`. The bubblewrap backend `--clearenv`s and
  re-emits each key via `--setenv` (overriding `HOME` from `profile.home`); the
  child sets `os.environ = spec.env` before exec. Under passthrough the child env
  is exactly `_build_subprocess_env()` (with the profile `home` ignored) — matching
  today.
- Rationale: keeps the env-allowlist invariant the existing
  `test_env_allowlist_invariant` test pins, now sourced through the spec.

**DD5 — Orphan-survival is the load-bearing teardown assertion; it lands in the
same leg as the kill code.**
- A `@requires_bwrap` test asserts that after `close()` returns (plus the
  confirm-reaped settle), **no sandboxed descendant of the captured bwrap process
  survives** — no leaked shell, no leaked grandchild. This is the property that
  actually matters; the SIGKILL-fast-vs-ladder choice (resolved in Open Questions)
  is an optimization underneath it. The test asserts against the **specific**
  session's bwrap (captured by its child shell PID), not "no bwrap at all" — other
  concurrent bwrap spawns (one-shot tools, MCP) would otherwise make the assertion
  flaky (architect low issue).
- **Co-located with the kill code in `pty-platform-seam`** (not deferred to the
  containment-tests leg) so the leg that implements teardown self-validates —
  mirroring how Flight 1 kept its timeout-kill test in the same leg as the kill
  code (the Leg-4 discipline).
- Rationale: Flight 1 settled its analogous kill question empirically and the
  debrief asked Flight 2 for "a dedicated `@requires_bwrap` PTY
  orphan-survival-after-close test." Mirrors that discipline.

**DD9 — `--die-with-parent` is load-bearing for PTY teardown; record it.**
- The single-pid SIGKILL reaper (Open Questions resolution) works *because* the
  bubblewrap backend emits `--die-with-parent` (`bubblewrap.py:110`), tying the
  inner PID-1 shell's death to the bwrap-outer pid. A future `SandboxProfile` /
  backend change that dropped `--die-with-parent` would silently regress PTY
  orphan-reaping. The `pty-platform-seam` leg notes this dependency in code
  comments and the orphan-survival test stands as its regression guard.
- **Known limitation (carried, not fixed here):** `--die-with-parent` ties the
  *inner* shell to the bwrap-outer process, but bwrap-outer itself is not tied to
  the Python app. If the app crashes without `close()`, the registry reaper /
  lifespan shutdown (`_session_registry`) is the sole guarantee against an orphaned
  PTY bwrap tree — a pre-existing gap across all four spawn paths, with a larger
  window for long-lived PTY. Logged as a mission-level open item (see flight log);
  out of scope for this flight.

**DD6 — Verify both ways: live behavior test + `@requires_bwrap` integration.**
- The mission marks PTY containment "behavior-test-backed," so this flight authors
  and runs `/behavior-test pty-session-containment` (two live agents, Witnessed
  pattern) as the acceptance gate. In parallel, `@requires_bwrap` integration tests
  (write-denied, denylist-secret-not-writable, network deny/allow, real-HOME
  persistence, orphan-survival) give a deterministic inner loop — the surface
  Flight 1 actually used to prove its criterion.
- Rationale: the live test satisfies the mission wording and exercises the real
  session-tool path end to end; the integration tests are fast, hermetic, and
  re-runnable without spinning up the live-agent crew. See the Verification section
  and the **Apparatus audit (both axes)** in the flight log.
- Trade-off: highest verification cost of the three options — accepted because PTY
  is the heaviest/riskiest path and the mission singled it out for behavior-test
  backing.

**DD7 — Pin the existing PTY unit tests to passthrough (DD9 pattern).**
- `tests/test_pty_session.py` (and any `test_session_tools.py` cases that spawn a
  real PTY) set `THE_ONE_SANDBOX_DISABLED=1` (with `THE_ONE_TEST_MODE` from
  conftest) so they deterministically select `PassthroughSandbox` regardless of
  whether the host has bwrap. New `@requires_bwrap` tests cover the real bwrap path.
- Rationale: identical to Flight 1's DD9 for `test_execution_tools.py` — without
  pinning, these unit tests would silently run under bwrap in-container but
  passthrough on a bwrap-less host (different env surface, cwd handling, teardown).

**DD8 — `UnixPtySession` gains an optional `profile: SandboxProfile | None`.**
- `create_pty_session(cwd, shell, profile=None)` and the constructor accept the
  profile. `start()` resolves `prof = profile or SandboxProfile()` and always calls
  `prepare_spawn`. When `profile is None` the effective enforcement is whatever the
  selected backend does with an empty strict-floor profile — which only occurs for
  the bare platform primitive (the tool layer always supplies a real profile, and
  the platform tests pin to passthrough where the profile is ignored). Document
  that the bare primitive on a bwrap host without a profile yields a strict cage,
  not today's open session — callers in the tool layer must pass a profile.

### Prerequisites
- [x] Flight 1's seam exists and is reusable: `get_sandbox_backend()` /
      `prepare_spawn → SpawnSpec` (`platform/sandbox/`), `_build_tool_profile`
      (`tools/execution.py:424`), `SandboxProfile` with `readonly_overlay_paths`
      + profile-driven `home`. Verified live during planning.
- [x] PTY spawn site is as cited and still unsandboxed: `platform/pty.py:192-222`
      (child `os.chdir` → `os.environ.clear/update(_build_subprocess_env())` →
      `os.execvp(shell, [shell, "-i"])`). Verified live.
- [x] Tool-layer hook exists: `ShellSessionStartTool.execute` validates cwd via
      `_cwd_check` then calls `create_pty_session(cwd=…)` (`tools/sessions.py:104-148`).
- [x] `bwrap` present in the dev/test environment — host has bubblewrap 0.9.0;
      Dockerfile installs `bubblewrap`; `docker-compose.yml` grants
      `cap_add: SYS_ADMIN` + `security_opt: seccomp:unconfined`. So both the
      `@requires_bwrap` run **and** the live behavior test can run here.
- [ ] **Behavior-test apparatus (DD6) — verified at planning, probed before run**:
      a running `the-one` instance with an agent whose `ExecutionConfig` enables the
      `shell_session_*` tools and whose `FilesystemConfig` has a known
      allowlist/denylist, on a host where `get_sandbox_backend()` selects
      bubblewrap. **The act-path drive surface must be confirmed before the
      `verify-integration` leg** (architect question): *how* the Executor invokes
      the agent's `shell_session_*` tools against the running instance (HTTP chat
      endpoint vs CLI) and that the surface is reachable by `/behavior-test` — the
      whole act path hinges on it, plus on the driven agent reliably *choosing* to
      call `shell_session_start` when prompted. The `pty-session-containment` spec's
      Preconditions probe this live (see spec). The Executor + Validator run
      re-spawn-per-checkpoint by default; live continuation (experimental
      `SendMessage`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) is an optional
      optimization.

### Pre-Flight Checklist
- [x] All open questions resolved except the teardown/kill strategy, which the
      operator deferred to the Phase-5b Architect + `pty-platform-seam` leg design
      (gated by the orphan-survival test either way — DD5)
- [x] Design decisions documented
- [x] Prerequisites verified (behavior-test apparatus probed live; re-probed at run)
- [x] Validation approach defined (live behavior test + `@requires_bwrap`)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Add an optional `profile: SandboxProfile | None` to `UnixPtySession` /
`create_pty_session`. In `start()`, **in the parent before `pty.fork()`**, select
the backend (`get_sandbox_backend()`) and compute `spec =
backend.prepare_spawn(prof, shell, shell_args, _build_subprocess_env(), cwd)`
where `shell_args` carries the existing `-i` interactive-shell logic. Rewrite the
forked-child branch to `os.chdir(spec.cwd)` (if set) → `os.environ.clear()` →
`os.environ.update(spec.env)` → `os.execvp(spec.command, [spec.command,
*spec.args])`, replacing the inline chdir/clear/execvp-of-the-bare-shell. On Linux
the child execs `bwrap`; under passthrough it execs the bare shell exactly as
today. Wire the tool layer so `ShellSessionStartTool.execute` builds the profile
via `_build_tool_profile(fs_cfg, exec_cfg)` and passes it to
`create_pty_session`. Resolve the teardown/kill strategy under bwrap-as-PID-1
(architect + leg), keeping the orphan-survival property as the gate. Pin the
existing PTY unit tests to passthrough; add `@requires_bwrap` PTY-containment
tests; author and run the `pty-session-containment` behavior test. Update the
sandbox docs (PTY now sandboxed; the single-path seam; add the
`platform/sandbox/` subsection the debrief asked for).

### Checkpoints
- [x] `UnixPtySession` accepts a profile; `SpawnSpec` computed pre-fork; child
      execs through the spec; passthrough reproduces today's start/send/close.
      `test_pty_session.py` pinned to passthrough and green host-native + in-container.
- [x] Resolved teardown implemented (single-pid SIGKILL-fast on the wrapped path +
      confirm-reaped settle); `close()` returns promptly under bwrap; the
      orphan-survival `@requires_bwrap` test (in `pty-platform-seam`) is green.
- [x] `ShellSessionStartTool` builds the profile via `_build_tool_profile` and
      threads it into `create_pty_session`; session-tool tests green (mock lambdas
      updated to accept `profile=None`).
- [x] `@requires_bwrap` PTY tests prove: write outside allowlist denied; denylisted
      secret path not writable; network denied by default and enabled when
      `sandbox_network_allowed=true`; `~`-relative write persists (real HOME);
      no orphan survives `close()`.
- [x] `/behavior-test pty-session-containment` run against the live instance
      (Sonnet agent → `shell_session_*` tools → bwrap PTY; run log
      `tests/behavior/pty-session-containment/runs/2026-06-07-09-56-42.md`).
      **6/7 checkpoints PASS** (real-`$HOME` writable, `/etc` denied, `~/.ssh`
      denylist-protected, orphan-survival reaped); checkpoint 6 (network) INCONCLUSIVE
      — the safety-aligned agent refused the raw-socket probe, so the live observable
      wasn't measured; network-deny is proven deterministically by the
      `@requires_bwrap` suite, and the spec's network step was re-authored to a
      namespace-isolation observable the agent cooperates with.
- [x] Full suite + ruff green; docs updated.

### Adaptation Criteria

**Divert if**:
- bwrap-wrapping the PTY child breaks interactive-session semantics in a way the
  host-workspace profile can't express (e.g. the controlling-tty / slave-fd
  inheritance is lost through the `bwrap` exec, or `--unshare-pid` breaks job
  control the session needs) — re-plan the composition (possibly `--die-with-parent`
  tuning or a different namespace set for the PTY profile).
- The teardown strategy cannot guarantee orphan reaping within an acceptable
  `close()` latency under bwrap-as-PID-1 — escalate to the operator with the
  measured trade-off.

**Acceptable variations**:
- Splitting or merging `pty-platform-seam` / `pty-tool-wiring` if the profile
  threading proves trivial (merge) or the child-branch rewrite proves heavy (keep
  split — the Flight-1 Leg-4 lesson: platform-subprocess changes earn their own leg).
- Folding the `_build_tool_profile` default-allowlist unit test (a Flight-1
  debrief action item) into `pty-tool-wiring` since PTY now exercises that path.

### Legs

> **Note:** Tentative; legs are planned and created one at a time as the flight
> progresses.

- [x] `pty-platform-seam` - `platform/pty.py`: add `profile` param to
      `UnixPtySession` / `create_pty_session`; compute `SpawnSpec` in the parent
      via `get_sandbox_backend().prepare_spawn` (carry the `-i` logic into
      `shell_args`); rewrite the forked-child branch to exec through the spec
      (`if spec.cwd: chdir spec.cwd` → `environ = spec.env` → `execvp spec.command,
      [spec.command, *spec.args]`); single-path (passthrough reproduces today).
      Implement the resolved teardown: single-pid kill, **SIGKILL-fast on the
      wrapped path** / SIGTERM-first on passthrough, + confirm-reaped settle; note
      `--die-with-parent` as load-bearing (DD9). Pin `tests/test_pty_session.py` to
      passthrough. **Add the orphan-survival `@requires_bwrap` test here (DD5)** so
      the kill code self-validates — capture the session's specific bwrap (by child
      shell PID) and assert it + its descendants are gone after `close()`. Files:
      `the_one/platform/pty.py`, `tests/test_pty_session.py`,
      `tests/test_pty_sandbox.py` (orphan-survival case).
- [x] `pty-tool-wiring` - `tools/sessions.py`: `ShellSessionStartTool.execute`
      builds `_build_tool_profile(fs_cfg, exec_cfg)` and threads it into
      `create_pty_session(cwd=…, profile=…)`. **Update the `create_pty_session`
      monkeypatch lambdas in `tests/test_session_tools.py` to accept the new
      `profile=None` kwarg** (`lambda cwd=None, shell=None, profile=None:
      MockPtySession()`) — these tests mock the factory, so the fix is the lambda
      signature, **not** passthrough-pinning (architect high issue; lambdas at
      `test_session_tools.py:67,93,113,133`). Add the `_build_tool_profile`
      default-allowlist production-path unit test (debrief action item; PTY now
      exercises that path). Files: `the_one/tools/sessions.py`,
      `tests/test_session_tools.py`.
- [x] `pty-containment-tests` - Extend `tests/test_pty_sandbox.py` with the
      remaining `@requires_bwrap` tests mirroring `test_builtin_tool_sandbox.py`:
      write-outside-allowlist-denied, denylist-secret-not-writable (sibling-allowed
      control), network deny-by-default + opt-in, real-HOME persistence. **Create
      the denylisted secret dir explicitly** in the test (do NOT rely on the default
      `~/.ssh` existing — `--ro-bind-try` silently skips absent paths, so a missing
      dir would false-pass; mirror `test_builtin_tool_sandbox.py:118`). Workspaces
      under `$HOME` (bwrap lays a fresh tmpfs at `/tmp`). (Orphan-survival already
      landed in `pty-platform-seam`.)
- [x] `verify-integration` - Full suite host-native + in-container; ruff gate;
      `-m requires_bwrap` PTY run on a bwrap host; **probe the behavior-test
      apparatus then run `/behavior-test pty-session-containment`** and capture the
      run log; confirm passthrough (simulated bwrap-missing) does not error and
      start/send/close still work. Update `CLAUDE.md` / `agents.md` /
      `SECURITY-MODEL.md`: PTY is now sandboxed, the single-path seam, the
      load-bearing `--die-with-parent`, the **deliberate absence of `--new-session`**
      (required to keep the controlling tty for interactive use — record the
      `TIOCSTI` input-injection surface it leaves open as a known tradeoff, not an
      oversight), and add the `### the_one/platform/sandbox/` subsection the Flight-1
      debrief requested.
- [x] `uat-and-alignment` *(optional)* - Guided HAT session. **Accepted via operator
      review of the live `/behavior-test` run** (the operator reviewed the Executor↔Sonnet
      conversations directly and signed off); the separate guided step-by-step was
      waived as redundant — the HAT's purpose (human acceptance of real behavior) was
      met by the live run.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed (4 autonomous + optional HAT accepted via behavior-test review)
- [ ] Code merged *(draft PR #104 marked ready for review; awaiting merge)*
- [x] Tests passing (`-m requires_bwrap` 12 passed; full suite 3008 passed; live
      `pty-session-containment` behavior test 6/7 PASS, 1 inconclusive covered
      deterministically by the bwrap suite)
- [x] Documentation updated (PTY sandboxed; single-path seam; `platform/sandbox/`
      doc subsection; `--die-with-parent` / no-`--new-session` notes)

### Verification

- **Live behavior test** `pty-session-containment` (`tests/behavior/`): two live
  agents (Executor drives `shell_session_start` / `shell_session_send` against a
  running instance; an independent Validator judges) prove a tool-launched PTY
  session is contained — a write outside the allowlist fails in-session, an
  outbound connection is refused, `~`-relative writes persist, and after the
  session closes no sandboxed descendant survives on the host. (Mission's
  behavior-test gate for the PTY criterion.)
- **`@requires_bwrap` integration tests** (`tests/test_pty_sandbox.py`) prove the
  same containment deterministically and hermetically: write-denied-outside-allowlist,
  denylist-secret-not-writable, network deny/allow, real-HOME persistence,
  orphan-survival-after-close.
- **Passthrough** (simulated bwrap-missing / non-Linux): the PTY session still
  starts / sends / closes with today's behavior; no construction-time error.
- `ruff check` + `ruff format --check` pass; full default suite green.
- **Honest caveat** (carried from Flight 1): the default `pytest` run does not
  exercise containment (`requires_bwrap` is deselected) and there is no pytest CI
  yet — containment is proven by the deliberate `-m requires_bwrap` run plus the
  live behavior-test run; automated CI is a Mission 15 concern.
