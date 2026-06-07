# Leg: pty-platform-seam

**Status**: completed
**Flight**: [PTY Through the Seam](../flight.md)

## Objective

Route the `UnixPtySession` spawn (`pty.fork()` + child-side `execvp`) through the
shared sandbox seam by computing a `SpawnSpec` in the parent before `fork()` and
exec-ing the wrapped command in the child — single-path, with passthrough
reproducing today's behavior — and implement the resolved bwrap teardown, gated by
an orphan-survival `@requires_bwrap` test that lands in this leg.

## Context

- **Design decisions** (from `flight.md`): DD1 (wrap child-side exec, compute spec
  in parent — fork-safety: the factory touches logging locks), DD2 (single-path
  through the seam), DD4 (env via `SpawnSpec.env`, F4 Decision-10 allowlist
  preserved), DD5 (orphan-survival test co-located here), DD7 (pin existing PTY
  unit tests to passthrough), DD8 (`UnixPtySession` gains `profile` param), DD9
  (`--die-with-parent` load-bearing).
- **Resolved teardown** (architect): keep **single-pid kill** (not killpg) —
  `--die-with-parent` + PID-namespace teardown on SIGKILL reaps `setsid`'d
  grandchildren killpg would miss. **SIGKILL-fast on the wrapped path** (bwrap
  doesn't forward SIGTERM to the inner shell, so the 1 s grace is wasted);
  **SIGTERM-first on the passthrough path** (preserve today's graceful behavior).
  Add a confirm-reaped settle so the orphan assertion is deterministic.
- This is the first and heaviest leg; Legs 2-4 depend on the `profile` param and
  the seam routing landing here. No prior legs in this flight.

## Inputs

What exists before this leg runs:
- `the_one/platform/pty.py` — `UnixPtySession` with the unsandboxed child branch
  (`pty.py:192-222`: `os.chdir` → `os.environ.clear()` →
  `os.environ.update(_build_subprocess_env())` → `os.execvp(shell, argv)`) and the
  teardown `_close_blocking` (`pty.py:415-470`, single-pid SIGTERM→1s→SIGKILL).
- The Flight-1 seam: `get_sandbox_backend()` (`platform/sandbox/factory.py:69`),
  `prepare_spawn → SpawnSpec` (`platform/sandbox/base.py:260`), `BubblewrapSandbox`
  emitting `--die-with-parent`/`--unshare-pid`/`--clearenv`/`--setenv`/`--chdir`
  (`platform/sandbox/bubblewrap.py:75-153`), `PassthroughSandbox.prepare_spawn`
  returning args unchanged (`platform/sandbox/passthrough.py:43-58`).
- `tests/test_pty_session.py` — unit tests constructing `UnixPtySession()` bare.
- `tests/test_builtin_tool_sandbox.py` — the `@requires_bwrap` orphan-test pattern
  to mirror (`_sleep_pids()` snapshot + `time.sleep(0.5)` settle,
  `test_builtin_tool_sandbox.py:285-340`).

## Outputs

What exists after this leg completes:
- `UnixPtySession` / `create_pty_session` accept `profile: SandboxProfile | None`;
  `start()` computes the `SpawnSpec` in the parent and the child execs through it.
- `_close_blocking` implements SIGKILL-fast on the wrapped path / SIGTERM-first on
  passthrough, + confirm-reaped settle.
- `tests/test_pty_session.py` pinned to passthrough and green.
- `tests/test_pty_sandbox.py` exists with the orphan-survival `@requires_bwrap`
  test, green under `-m requires_bwrap` on a bwrap host.

## Acceptance Criteria
- [x] `create_pty_session(cwd=None, shell=None, profile=None)` and
      `UnixPtySession.__init__` accept a `profile: SandboxProfile | None` param
      (default `None`), stored for use in `start()`.
- [x] `start()` selects the backend via `get_sandbox_backend()` and computes
      `spec = backend.prepare_spawn(prof, shell, shell_args, _build_subprocess_env(),
      cwd)` **in the parent, before `pty.fork()`** (where `prof = profile or
      SandboxProfile()` and `shell_args` carries the existing `-i`
      interactive-shell logic).
- [x] The forked-child branch execs through the spec: `if spec.cwd is not None:
      os.chdir(spec.cwd)` → `os.environ.clear()` → `os.environ.update(spec.env)` →
      `os.execvp(spec.command, [spec.command, *spec.args])`. The inline
      `_build_subprocess_env()` / bare-shell `execvp` is removed (env now flows
      through `spec.env`).
- [x] Under passthrough, behavior matches today byte-for-byte (cwd via chdir, env =
      `_build_subprocess_env()`, shell `-i` for bash/zsh) — verified by the existing
      `test_pty_session.py` suite passing once pinned to passthrough.
- [x] `_close_blocking` uses **single-pid** kill (no killpg): SIGKILL-fast (then
      blocking `os.waitpid(pid, 0)` on the local `pid`) when the session is
      bwrap-wrapped, SIGTERM-first→1s→SIGKILL when passthrough. No in-`close()`
      settle (the orphan-assertion settle is test-side). `self._wrapped =
      (spec.command == "bwrap")` set in `start()`. `--die-with-parent` dependency
      noted in a code comment (DD9).
- [x] `tests/test_pty_session.py` is pinned to passthrough (`THE_ONE_SANDBOX_DISABLED=1`
      via an autouse fixture / `monkeypatch.setenv` before `start()`) and green
      host-native + in-container.
- [x] `tests/test_pty_sandbox.py` contains a `@requires_bwrap` orphan-survival test:
      start a real (bwrap-wrapped) session, launch a backgrounded grandchild
      (e.g. `sleep 30 &`) inside it, capture its PID, `close()` the session, settle,
      and assert the grandchild PID is **gone** — proving namespace teardown reaps
      descendants, not just the direct shell. Green under `-m requires_bwrap`.
- [x] `ruff check` + `ruff format --check` pass; the changed test files pass.

## Verification Steps
- `docker exec the-one pytest tests/test_pty_session.py -x --timeout 30` — green
  (now pinned to passthrough).
- `docker exec the-one pytest tests/test_pty_sandbox.py -m requires_bwrap -x --timeout 60`
  — orphan-survival test green (bwrap present in-container).
- `docker exec the-one pytest tests/test_pty_session.py -m requires_bwrap -x` — n/a
  unless any session-level bwrap case is added here (orphan test lives in
  `test_pty_sandbox.py`).
- Negative check: temporarily simulate bwrap-missing (or rely on the passthrough
  pin) and confirm `start()`/`send()`/`close()` still work — no construction error.
- `docker exec the-one ruff check the_one/platform/pty.py tests/test_pty_session.py tests/test_pty_sandbox.py`
  and `ruff format --check` — clean.

## Implementation Guidance

1. **Add the `profile` param (DD8).**
   - `UnixPtySession.__init__(self, cwd=None, shell=None, profile=None)` — store
     `self._profile = profile`.
   - `create_pty_session(cwd=None, shell=None, profile=None)` (`pty.py:473`) —
     forward `profile` to `UnixPtySession`.
   - Import `SandboxProfile` and `get_sandbox_backend` at **function level inside
     `start()`** (not module top) to avoid any `platform ↔ platform.sandbox` import
     cycle — mirror `platform/shell.py:123`'s `from the_one.platform.sandbox import
     get_sandbox_backend`.

2. **Compute the SpawnSpec in the parent, before `pty.fork()` (DD1, fork-safety).**
   - In `start()`, after resolving `shell = self._shell_override or
     select_shell()[0]`, build `shell_args`: `["-i"] if os.path.basename(shell) in
     _INTERACTIVE_SHELL_BASENAMES else []` (carry the existing logic out of the
     child).
   - `prof = self._profile or SandboxProfile()`.
   - `backend = get_sandbox_backend()`; `spec = backend.prepare_spawn(prof, shell,
     shell_args, _build_subprocess_env(), str(cwd) if cwd is not None else None)`.
   - Stash `spec` in a local; **do not** call the factory/`prepare_spawn` after
     `fork()` (the child must not touch the logging lock the factory uses).
   - Record whether the spawn is wrapped (e.g. `wrapped = backend.name !=
     "passthrough"` or `spec.command == "bwrap"`) on `self` for the teardown branch.

3. **Rewrite the child branch (`pty.py:192-222`) to exec through the spec.**
   ```python
   if pid == 0:
       try:
           if spec.cwd is not None:
               os.chdir(spec.cwd)        # passthrough: real effect; bwrap: redundant, harmless (DD1)
           os.environ.clear()
           os.environ.update(spec.env)
           os.execvp(spec.command, [spec.command, *spec.args])
       except Exception:                 # pragma: no cover — exec replaces image
           os._exit(127)
       os._exit(127)                     # pragma: no cover
   ```
   - Keep the existing chdir-failure → `os._exit(127)` semantics (chdir now raises
     inside the same try; the bare `except Exception` already maps to 127).

4. **Teardown (resolved): single-pid, path-dependent SIGTERM grace (DD5/DD9).**
   - Store `self._wrapped: bool = False` in `__init__`; set `self._wrapped =
     (spec.command == "bwrap")` in `start()` after computing the spec (commit to the
     **spec-level** ground truth, not `backend.name`, so a future backend variant
     can't drift the check — reviewer low).
   - In `_close_blocking` (`pty.py:415`), branch on `self._wrapped`, operating on the
     **local `pid` variable** captured at `pty.py:426` (`pid = self._pid`) — never on
     `self._pid` directly, which is nilled at `pty.py:469` (reviewer medium):
     - **wrapped** → `os.kill(pid, signal.SIGKILL)` immediately (skip the SIGTERM
       grace; bwrap doesn't forward SIGTERM), then blocking `os.waitpid(pid, 0)`.
       This reap is sufficient: when bwrap (PID 1 of the namespace) dies, the kernel
       SIGKILLs every remaining process in the namespace. **No in-`close()` settle** —
       keep `close()` prompt; the orphan-survival *assertion* gets its settle
       test-side (step 6), which is where the async-teardown-vs-`/proc` race actually
       needs covering (resolves reviewer Question 1).
     - **passthrough** → keep today's SIGTERM → 1 s poll → SIGKILL ladder verbatim
       (preserves graceful behavior; no extra settle — there's no PID namespace to
       drain).
   - Keep all existing `ProcessLookupError`/`ChildProcessError` idempotency guards.
   - Add a code comment: "single-pid SIGKILL reaps the whole bwrap PID namespace via
     `--die-with-parent` (bubblewrap.py) — do not switch to killpg; do not drop
     `--die-with-parent` from the profile/backend (DD9)."

5. **Pin `test_pty_session.py` to passthrough (DD7).**
   - Add a **function-scoped** autouse fixture that does `monkeypatch.setenv(
     "THE_ONE_SANDBOX_DISABLED", "1")` (companion `THE_ONE_TEST_MODE` is already set
     by `tests/conftest.py:42`) so `get_sandbox_backend()` returns passthrough
     regardless of host bwrap. **Must be function-scoped** — pytest's `monkeypatch`
     fixture is function-scoped and cannot be consumed by a module-scoped fixture
     (reviewer low); a function-scoped autouse fixture fires before every test in the
     file, which is exactly the coverage needed. It applies before `start()` because
     it runs before the test body.
   - Re-run the existing assertions (env-allowlist invariant, cwd round-trip, etc.);
     they should pass unchanged because passthrough forwards the spec verbatim.
   - **Update the now-stale `test_env_allowlist_invariant` docstring**
     (`test_pty_session.py:146-151`): it currently says `_build_subprocess_env` is
     read "in the child after fork" and the leak var must be set "before
     `UnixPtySession()` instantiation." Post-rewrite the env is captured **in the
     parent inside `start()`** — reword to "set before `start()` is called" so a
     future reader doesn't monkeypatch between `__init__` and `start()` and get it
     wrong (reviewer medium). The assertion itself still passes (`THE_ONE_TEST_LEAK`
     is not in `_ENV_ALLOWLIST`, so it never enters `spec.env`).

6. **Orphan-survival `@requires_bwrap` test in `tests/test_pty_sandbox.py` (DD5).**
   - New file; module docstring mirroring `test_builtin_tool_sandbox.py:1-18`
     (workspaces under `$HOME`; `THE_ONE_SANDBOX_DISABLED` must be UNSET).
   - Test body: `monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)`;
     create a workspace under `$HOME`; build a profile (use `_build_tool_profile(
     FilesystemConfig(path_allowlist=[str(workspace)], path_denylist=[]),
     ExecutionConfig())` or construct a `SandboxProfile` directly with the workspace
     writable + real home); `session = create_pty_session(cwd=workspace,
     profile=prof)`; `await session.start()`.
   - Inside the session, `await session.send("sleep 30 &\n")`, then capture the
     grandchild PID via the host (`pgrep -f "sleep 30"` snapshot before/after, the
     `_sleep_pids()` pattern from `test_builtin_tool_sandbox.py:307-318`). Add a
     one-line comment: `--unshare-pid` gives the process a namespace-local PID but
     does **not** hide it from the host `/proc`, so host `pgrep` sees it under its
     real host PID (reviewer low — heads off a future doubt).
   - `await session.close()`; **`time.sleep(0.5)` settle (test-side — this is where
     the async PID-namespace teardown is given time to propagate to `/proc`; `close()`
     itself adds no settle)**; assert the new `sleep 30` PID is gone (`pids_after -
     pids_before == set()`). `try/finally` closes the session + removes the workspace.

## Edge Cases
- **`profile is None` on a bwrap host (bare primitive misuse):** `prof =
  SandboxProfile()` → strict cage (no writable paths). Acceptable — the tool layer
  (Leg 2) always supplies a real profile, and these unit tests pin to passthrough.
  Document in the `start()` docstring that callers needing a working session on
  Linux must pass a profile. **Optional** (reviewer suggestion): emit a
  `logging.warning` when `profile is None` *and* the selected backend is bubblewrap,
  to aid debugging the otherwise-silent strict cage — apply at implementer discretion.
- **`spec.env` HOME under passthrough:** passthrough does NOT inject `profile.home`,
  so the child env is exactly `_build_subprocess_env()` (HOME from the allowlist if
  present) — matches today. Under bwrap, `--setenv HOME` comes from `profile.home`.
- **`shell` override (tests pass an explicit shell):** still honored — it feeds
  `prepare_spawn`'s `command`. The `-i` logic keys off `os.path.basename(shell)`.
- **chdir on the bwrap path:** redundant (bwrap `--chdir`) but harmless and required
  for passthrough — do not remove (DD1).
- **`send()`/`is_alive` post-exec:** `self._pid` is the bwrap-outer pid (direct
  child of the Python process); `os.waitpid(self._pid, WNOHANG)` (`pty.py:290`)
  still reaps when the inner shell exits. No change needed.

## Files Affected
- `the_one/platform/pty.py` — `profile` param; parent-side `SpawnSpec`; child execs
  through spec; teardown branch + settle.
- `tests/test_pty_session.py` — autouse passthrough pin.
- `tests/test_pty_sandbox.py` — **new**; orphan-survival `@requires_bwrap` test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`test_pty_session.py` passthrough; `test_pty_sandbox.py`
      orphan-survival under `-m requires_bwrap`)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — do not land the flight here)
- [ ] **Do NOT commit** — batched workflow: review + commit happen after the last
      autonomous leg (Phase 2d). Signal `[HANDOFF:review-needed]` instead.
