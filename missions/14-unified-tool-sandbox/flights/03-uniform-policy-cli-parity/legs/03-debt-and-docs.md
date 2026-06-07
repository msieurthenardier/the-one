# Leg: debt-and-docs

**Status**: completed
**Flight**: [Uniform Policy, CLI Parity & Seam Hardening](../flight.md)

## Objective

Clear the carried light debt and fold in the minimal seam hardening: a
`@requires_bwrap` regression test locking the host-crash PTY-teardown invariant
(with a bwrap-not-setuid probe), an optional cheap pre-`execvp` `PR_SET_PDEATHSIG`
defense-in-depth, the `profile: object` → `TYPE_CHECKING` typing fix, the doc/message
corrections, and the mission known-issue record that the orphan window is mitigated.

## Context

This leg consolidates the former standalone `seam-hardening` leg (operator folded it
in after **DD4** showed the host-crash orphan window is already covered by bwrap's own
`--die-with-parent` → `prctl(PR_SET_PDEATHSIG, SIGKILL)` tied to the Python parent;
empirically verified, ~300ms reap on bwrap 0.9.0). So the hardening shrank to a
regression guard + optional belt-and-suspenders + typing fix, not worth its own slot.

Five sub-items (all in this one leg):

1. **Invariant regression test** (`@requires_bwrap`).
2. **Optional** pre-`execvp` `PR_SET_PDEATHSIG` defense-in-depth (implementer discretion).
3. **Typing fix**: `profile: object | None` → real `SandboxProfile | None` via `TYPE_CHECKING`.
4. **Doc/message debts**: sandbox-factory docstring, bubblewrap message, SECURITY-MODEL
   caveat, footgun docs.
5. **Mission known-issue**: record the orphan window as mitigated.

## Inputs

- `bwrap` 0.9.0 present; `/bin/bwrap` is `-rwxr-xr-x` (NOT setuid, no file caps) on this
  host — confirmed in recon. `PR_SET_PDEATHSIG` therefore survives `execvp("bwrap")`
  (it is cleared on execve only for setuid/setcap binaries).
- `tests/_sandbox_fixtures.py` now exists (leg 02) with `sleep_pids()` + `home_workspace()`
  — the regression test should reuse them.
- PTY fork/exec path verified at the citations below.

## Outputs

- `tests/test_pty_sandbox.py` — new `@requires_bwrap` app-crash regression test.
- `the_one/platform/pty.py` — typing fix (both annotations); optional pre-`execvp`
  pdeathsig in the fork child.
- `the_one/platform/sandbox/factory.py` — docstring correction.
- `the_one/platform/sandbox/bubblewrap.py` — error-message correction.
- `SECURITY-MODEL.md` — `--ro-bind-try` silent-skip caveat.
- `the_one/agents.md` + `CLAUDE.md` — sandbox-testing footgun patterns.
- `missions/14-unified-tool-sandbox/mission.md` — Known Issues entry (orphan window mitigated).

## Acceptance Criteria

### 1. Invariant regression test
- [x] A `@requires_bwrap` test in `tests/test_pty_sandbox.py` **first probes** that
      `/bin/bwrap` is not setuid and has no file capabilities, and **skips** (not
      false-passes) if it is. Use stdlib only — **NOT `getcap`** (not installed in the
      container): `os.stat("/bin/bwrap").st_mode & stat.S_ISUID` for setuid, and
      `os.getxattr("/bin/bwrap", "security.capability")` for file caps (catch `OSError`;
      `errno.ENODATA`/`ENOTSUP` ⇒ no caps ⇒ proceed; presence ⇒ `pytest.skip`). This
      ensures a passing reap is not silently attributable to pdeathsig being cleared on
      `execve` of a setuid/setcap bwrap.
- [x] The test starts a sandboxed PTY session **in a child process** (a driver
      subprocess), launches a `sleep 30` grandchild inside the session, captures its
      host PID via `sleep_pids()`, then **SIGKILLs the driver process without calling
      `session.close()`** (simulating an app crash), waits briefly, and asserts the
      grandchild PID is gone from the host process table.
- [x] The test reuses `tests/_sandbox_fixtures.py` helpers (`sleep_pids`,
      `home_workspace`) and `monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED", raising=False)`.
- [x] Docstring states honestly: this proves the **invariant** (tree reaped when the
      parent dies without `close()`); it does **not** attribute the reap to our code vs
      bwrap's own `--die-with-parent` — it is a regression guard.

### 2. Optional pre-execvp pdeathsig (defense-in-depth)
- [x] **Either** add a `prctl(PR_SET_PDEATHSIG, SIGKILL)` call in the fork child of
      `UnixPtySession.start()` **immediately before** `os.execvp(...)` (`pty.py:255`) —
      **or** explicitly skip it and note the decision. **Fork-safety (high — from design
      review)**: do NOT `import ctypes` or call `ctypes.CDLL(...)` inside the post-fork
      child (a new import/`dlopen` can deadlock on a lock inherited from a parent thread
      mid-import — the module's own DD1 fork-safety rule). Instead `import ctypes` at
      module level and load `libc = ctypes.CDLL("libc.so.6", use_errno=True)` in the
      **parent before `pty.fork()`**; the child only calls the already-loaded
      `libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL)` (`signal` is already imported at
      `pty.py:57`). Honest comment: bwrap's `--die-with-parent` is primary coverage; this
      only closes the microsecond startup race; relies on bwrap not being setuid/setcap.
      Must NOT break the single-pid SIGKILL teardown or cause a double-kill (same signal,
      idempotent). If it causes any conflict, **drop it** (flight Divert criterion).

### 3. Typing fix
- [x] In `the_one/platform/pty.py`, add a `TYPE_CHECKING` block importing
      `SandboxProfile` from `the_one.platform.sandbox.base`, and change **both**
      `profile: object | None  # SandboxProfile | None (avoid import…)` annotations
      (`UnixPtySession.__init__` at `pty.py:170` and `create_pty_session` at `pty.py:558`)
      to `profile: SandboxProfile | None` (the file already has
      `from __future__ import annotations`, so the annotation is a lazy string at
      runtime — no import cycle). Remove the now-stale `# avoid import…` comments.

### 4. Doc/message debts
- [x] `the_one/platform/sandbox/factory.py` — the `_sandbox_disabled_for_tests`
      docstring currently says the MCP site *"keeps its own copy until leg 3 reconciles
      both to this factory"* (`factory.py:~61`). Reword to state the MCP-site copy is
      **intentionally preserved** for the import-cycle workaround (relocation deferred to
      end-of-mission maintenance, DD1) — not "pending reconciliation."
- [x] `the_one/platform/sandbox/bubblewrap.py` — the `__init__` `SandboxError` message
      *"MCP sandbox setup failed: bubblewrap binary not found…"* (`bubblewrap.py:~69`)
      → platform-neutral *"sandbox setup failed: …"* (the seam is platform-wide incl.
      built-in tools + PTY now, not just MCP). **The three "MCP sandbox setup failed"
      messages in `the_one/mcp/transports/stdio.py` (~:180/:190/:197) stay as-is** —
      they are MCP-transport-specific and the prefix is still accurate there (design
      review). Only `bubblewrap.py` changes.
- [x] `tests/test_sandbox_bubblewrap.py` — the verbatim-lock constant `_BWRAP_NOT_FOUND_MSG`
      (`:~22-27`) and the associated test docstring (the "§6 verbatim message" note)
      assert the exact old text; **update them to the new platform-neutral message** or
      the default suite breaks. (Design-review finding — without this, the Global "full
      default suite green" AC fails.)
- [x] `SECURITY-MODEL.md` — near the `--ro-bind-try` mechanism (`:~81`), add the
      **silent-skip-of-absent-paths caveat**: `--ro-bind-try` (vs `--ro-bind`) silently
      skips a denylist path that does not exist on the host, so a denylist entry only
      protects an existing path — a missing path is a no-op (the test-fixture footgun).
- [x] `the_one/agents.md` (Testing-patterns area) **and** `CLAUDE.md` (Conventions or
      Security-posture area) — document the three sandbox-testing footguns:
      (i) **spec-level teardown-dispatch** (`self._wrapped = spec.command == "bwrap"` is
      the ground truth, not a backend flag); (ii) **PTY-echo sentinel** (the PTY echoes
      the command back, so assert on OUTPUT only — use the `"con"+"nected"` string-concat
      trick to keep the literal out of the echoed source); (iii) **`@requires_bwrap`
      workspace-under-`$HOME`** (bwrap mounts a fresh tmpfs at `/tmp`, so test workspaces
      MUST live under `$HOME`, not `/tmp`, or they're invisible inside the sandbox).
      (Choose the section semantically; suggest a heading, don't hard-code a contract.)

### 5. Mission known-issue
- [x] `missions/14-unified-tool-sandbox/mission.md` Known Issues (currently *"None yet"*)
      — add an entry recording that the **host-crash PTY-orphan window was investigated
      and found already mitigated** by bwrap's `--die-with-parent`
      (`prctl(PR_SET_PDEATHSIG, SIGKILL)` tied to the Python parent; empirically
      verified, bwrap 0.9.0, ~300ms reap), locked by this leg's regression test. Frame
      it as resolved/mitigated, not open.

### Global
- [x] Full default suite (`-m "not requires_bwrap"`) green; the bwrap suite
      (`-m requires_bwrap`) green; `ruff check` + `ruff format --check` clean.
- [x] No behavior regression in existing PTY tests.

## Verification Steps

- `docker exec the-one python -m pytest tests/test_pty_sandbox.py -m requires_bwrap --timeout 120` — all green incl. the new regression test.
- `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q` — full default suite green (no import/typing breakage from the pty.py change).
- `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/platform/pty.py`.
- `grep -n "object | None" the_one/platform/pty.py` — returns nothing (both annotations replaced).
- `grep -n "MCP sandbox setup failed" the_one/platform/` — returns nothing (the
  `the_one/mcp/transports/stdio.py` occurrences are intentionally retained — do not grep `the_one/` broadly).
- `grep -rn "until leg 3 reconciles" the_one/` — returns nothing.
- Read `missions/14-unified-tool-sandbox/mission.md` Known Issues — confirms the mitigated entry.

## Implementation Guidance

1. **Typing fix first** (lowest risk, unblocks clean diffs). Add after the stdlib
   imports in `pty.py`:
   ```python
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from the_one.platform.sandbox.base import SandboxProfile
   ```
   Then change `pty.py:170` and `pty.py:558` to `profile: SandboxProfile | None = None,`
   and drop the trailing `# SandboxProfile | None (avoid import…)` comments. The runtime
   function-level import at `pty.py:213` stays (it is used at call time, not just typing).

2. **Regression test.** Model it on `test_pty_close_reaps_namespace_grandchild`
   (`test_pty_sandbox.py:60`) but instead of `session.close()`, the **session lives in a
   separate process that gets SIGKILL'd**. Use a driver run via
   `subprocess.Popen([sys.executable, "-c", <driver>])`. The driver CANNOT use top-level
   `await` — it must wrap the async calls and then block:
   ```python
   driver = r'''
   import asyncio, time
   from pathlib import Path
   from the_one.platform.pty import create_pty_session
   from the_one.platform.sandbox.base import SandboxProfile
   async def main():
       prof = SandboxProfile(writable_paths=[<ws>], network_allowed=False, home=<ws-or-home>)
       s = create_pty_session(cwd=Path(<ws>), profile=prof)
       await s.start()
       await s.send("sleep 30 &\n")
       print("READY", flush=True)   # readiness signal
   asyncio.run(main())
   time.sleep(9999)                 # stay alive until the test SIGKILLs us
   '''
   ```
   The test: launch the driver (it inherits the test's `os.environ`, so
   `monkeypatch.delenv("THE_ONE_SANDBOX_DISABLED")` propagates), wait for the `READY`
   line, snapshot the grandchild PID via `sleep_pids()` (assert it was actually captured —
   else the test races/false-passes), then `os.kill(driver.pid, signal.SIGKILL)`, wait
   ~1s, and assert the grandchild PID is gone. **Why this exercises the invariant**: the
   driver is bwrap's direct parent (driver's `pty.fork()` child execvp's bwrap), so
   killing the driver fires bwrap's `--die-with-parent`, collapsing the PID namespace.
   **Probe bwrap first** (stdlib, see AC 1): `os.stat` S_ISUID + `os.getxattr(...,
   "security.capability")`; `pytest.skip` if setuid/setcap. Honest docstring per AC.

3. **Optional pdeathsig** (do this OR skip-with-note). **Load libc in the PARENT before
   `pty.fork()`** (fork-safety — no new import/dlopen in the child):
   ```python
   # module level (near other imports):
   import ctypes
   # in start(), in the PARENT before pty.fork():
   _libc = ctypes.CDLL("libc.so.6", use_errno=True)
   _PR_SET_PDEATHSIG = 1
   # then in the child try block, immediately before os.execvp (pty.py:255):
   _libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)   # signal already imported at pty.py:57
   ```
   Comment honestly: primary coverage is bwrap's `--die-with-parent`; this closes only the
   microsecond before bwrap registers its own handler; relies on bwrap not being
   setuid/setcap (probed by the test). **The child runs after `pty.fork()`, so the parent
   is the Python process** — exactly what we want PDEATHSIG tied to. If anything about it
   complicates the single-pid teardown, drop it; the regression test stands alone.

4. **Doc/message edits** are mechanical — use the snippet citations above; verify each
   with the grep checks. For the footgun docs, pick the semantically-right section in
   `agents.md`/`CLAUDE.md` (these are the target project's own docs); suggest a heading
   like "Sandbox testing footguns", don't impose a rigid structure.

5. **Mission known-issue** — append under the Known Issues section (preserve the existing
   format; the section currently holds only the "None yet" placeholder — replace/augment
   it with the mitigated entry).

## Edge Cases

- **pdeathsig cleared on execve**: only happens for setuid/setcap binaries. The host's
  bwrap is neither (confirmed). The regression test's probe is what guards this — if a
  future host ships setuid bwrap, the test skips rather than false-passes.
- **Double-kill**: bwrap's own pdeathsig + our pre-exec pdeathsig set the SAME signal
  (SIGKILL) — idempotent, no double-kill hazard.
- **Driver-subprocess flakiness**: ensure the driver has actually forked the grandchild
  before the test captures the PID (readiness signal), else the test races. Give a short
  settle and assert the PID was captured before killing.
- **Typing import cycle**: importing `SandboxProfile` under `TYPE_CHECKING` cannot cause
  a runtime cycle (the block doesn't execute at runtime); the existing runtime import
  stays function-level.
- **Don't touch deferred debt**: the `SandboxError` relocation / `mcp/errors.py`
  import-cycle inversion is **out of scope** (DD1, → maintenance). Only reword the
  factory docstring to say it's intentionally preserved; do not move `SandboxError`.

## Files Affected

- `tests/test_pty_sandbox.py` — new `@requires_bwrap` app-crash regression test.
- `the_one/platform/pty.py` — typing fix (both annotations) + optional pre-`execvp` pdeathsig.
- `the_one/platform/sandbox/factory.py` — docstring reword.
- `the_one/platform/sandbox/bubblewrap.py` — platform-neutral error message.
- `tests/test_sandbox_bubblewrap.py` — update `_BWRAP_NOT_FOUND_MSG` + docstring to the new message.
- `SECURITY-MODEL.md` — `--ro-bind-try` silent-skip caveat.
- `the_one/agents.md` — sandbox-testing footgun patterns.
- `CLAUDE.md` — sandbox-testing footgun patterns (pointer/summary).
- `missions/14-unified-tool-sandbox/mission.md` — Known Issues: orphan window mitigated.

---

## Post-Completion Checklist

> **Batched-commit flight**: implement, update the flight log, set leg status to
> `landed`, signal `[HANDOFF:review-needed]`. No commit here.

- [x] All acceptance criteria verified (all 5 sub-items + global)
- [x] bwrap suite + full default suite green; ruff clean
- [x] Update flight-log.md with this leg's progress entry (note whether the optional
      pdeathsig was included or skipped, with rationale)
- [x] Set this leg's status to `landed` (NOT `completed`)
- [x] Do NOT commit; do NOT check off the leg in flight.md
