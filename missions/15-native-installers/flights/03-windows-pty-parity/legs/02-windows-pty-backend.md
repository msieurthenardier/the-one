# Leg: windows-pty-backend

**Status**: completed
**Flight**: [Windows PTY Parity (ConPTY)](../flight.md)

## Objective

Implement `WindowsPtySession` (ConPTY via `pywinpty`) in `the_one/platform/pty_windows.py`
satisfying the `PtySession` ABC, wire `create_pty_session` to dispatch to it on
Windows, add the `pywinpty` Windows-only dependency, and extend the subprocess
env allowlist with the Windows-essential keys cmd.exe needs — so a real cmd.exe
session round-trips on the `windows-2022` CI lane.

## Context

- **DD1:** `pywinpty>=2.0; sys_platform == "win32"` in base `dependencies`
  (env marker — never installs on Linux/macOS). The implementing agent runs on
  **Linux and cannot install or import pywinpty** — the backend is written
  against the documented API and verified ONLY on the `windows-2022` CI lane.
  Each CI round-trip is ~25 min; get the API right the first time.
- **DD3:** preserve the **identical** readiness contract from `UnixPtySession`
  (`pty_unix.py`): `start()` blocks until ~100ms idle OR a 2s cap; `send()`
  reads until idle OR timeout. Reuse the shared constants
  (`_DEFAULT_IDLE_WINDOW=0.1`, `_DEFAULT_START_TIMEOUT=2.0`, `_READ_CHUNK`) —
  import them from `pty_unix` is wrong (POSIX module); **move the three numeric
  constants to the neutral `pty.py`** (committed location — not a new file) so
  both backends import them platform-neutrally. (`_INTERACTIVE_SHELL_BASENAMES` is
  Unix-only — leave it in `pty_unix`.)
- **DD4:** supervision via the pywinpty process handle (no signals/waitpid).
  `self._wrapped` is structurally `False` on Windows (passthrough → command is
  the shell, never `"bwrap"`) — the bwrap teardown branch does not exist here.
  The orphan-reap *guarantee* (ConPTY-close vs. Job Object) is **Leg 3** — this
  leg does a straightforward `terminate()`-based `close()`; Leg 3 hardens it.
- **DD5:** cmd.exe needs `SystemRoot` (and `PATHEXT`/`COMSPEC`/`TEMP`/`TMP`/
  `USERPROFILE`/`USERNAME`) or it fails/misbehaves — the env work is a
  **backend-functionality prerequisite**, in this leg. **Do NOT edit
  `_ENV_ALLOWLIST`** — `test_execution_helpers.py:273
  (test_eight_allowlist_keys_canonical_set)` pins it to the exact 8-key POSIX
  tuple and would break on Linux. Add a **separate** `_WINDOWS_ENV_ALLOWLIST`
  constant and have `_build_subprocess_env` union it in only under `os.name ==
  "nt"` — POSIX allowlist + the pin stay byte-identical (design review).
- **Leg 1 left** `create_pty_session()` raising a Leg-2 sentinel on `nt` and
  `test_pty_dispatch.py::test_dispatch_windows_pending_leg2` asserting that
  raise. This leg **inverts** both: dispatch returns a `WindowsPtySession`; the
  test asserts that.
- **Seam:** on Windows `get_sandbox_backend()` returns `PassthroughSandbox`
  (recon-confirmed); `prepare_spawn` forwards command/args/env unchanged.
  WindowsPtySession still calls the seam (mirrors Unix; `warn_if_isolation_
  unenforced` correctly fires if a boxed session is requested on unsandboxed
  Windows). No `pty.fork`, so the "parent-loads/child-execs" fork-safety
  convention does NOT apply — the SpawnSpec is computed and handed straight to
  `PtyProcess.spawn`.

## pywinpty API reference (verified 2026-06-13 against pywinpty 3.x `ptyprocess.py`; the `>=2.0` pin resolves to 3.0.x on fresh installs — same `PtyProcess` surface)

```
PtyProcess.spawn(argv, cwd=None, env=None, dimensions=(24, 80))  # classmethod
  - argv: list/tuple of str. cwd defaults to os.getcwd(); env defaults to os.environ.
proc.read(size=1024) -> str   # BLOCKS on proc.fileobj.recv(size); UTF-8 str;
                              # raises EOFError('Pty is closed') at EOF.
proc.write(s) -> int          # routes via proc.pty.write; raises EOFError if PTY closed.
proc.isalive() -> bool        # NON-blocking liveness check.
proc.terminate(force=False) -> bool   # SIGINT; force→SIGTERM; NO SIGKILL; returns bool.
proc.close(force=False)       # terminate(force) + closes fileobj/_server atomically;
                              # may raise IOError if terminate fails.
proc.fileobj                  # a socket.socket — the read transport (ptyprocess.py:56).
proc.pid ; proc.exitstatus
```

**CRITICAL — the idle read mechanism (corrected at design review; the obvious
approach is WRONG).** pywinpty's `PtyProcess.read()` is NOT per-call
non-blocking: it does a **blocking `proc.fileobj.recv(size)`** on a loopback
socket fed by an internal daemon thread, and `read_blocking`/`PYWINPTY_BLOCK`
is captured into that thread's closure at construction — **setting
`read_blocking=False` after spawn does nothing.** Do NOT use it.

The correct idle-detection (closest analog to Unix's `select`+`EAGAIN`):
**`proc.fileobj.settimeout(idle_window)` before each `recv`, then
`proc.fileobj.recv(_READ_CHUNK)` directly** (bypassing `proc.read()` so you get
raw `bytes` — see the str-vs-bytes note below). Catch `socket.timeout` as the
"no data this window" signal (accumulate buffer, reset idle timer on data,
return when the window elapses with bytes buffered or the timeout cap is hit).
Catch the EOF condition (empty recv / `EOFError`) → child exited → return the
buffer (mirrors Unix's `OSError(EIO)` branch). Wrap the whole loop in
`run_in_executor` exactly as `pty_unix` does. **`close()` must
`proc.fileobj.close()` (or `proc.close()`) to unblock any pending `recv` so the
executor thread cannot outlive the event loop** (the pytest-asyncio teardown
wrinkle). pywinpty's own internal thread is `daemon=True`, so it won't block
shutdown — only our recv thread needs the explicit unblock.

**str-vs-bytes:** `UnixPtySession.send()` returns `bytes`. `proc.read()` returns
`str`. Reading `proc.fileobj.recv()` directly gives raw `bytes` — accumulate
bytes from the start so `send()` returns `bytes` with no re-encode (keeps parity
with the Unix backend's return type).

## Inputs

- `the_one/platform/pty.py` — neutral ABC + dispatcher; `create_pty_session`
  raises the Leg-2 sentinel on `nt`; POSIX-guarded `UnixPtySession` re-export.
- `the_one/platform/pty_unix.py` — `UnixPtySession` + the three shared numeric
  constants (currently defined there).
- `the_one/platform/env.py` — `_ENV_ALLOWLIST` (8 POSIX keys) +
  `_build_subprocess_env()`; re-exported via `tools/execution.py`.
- `the_one/platform/shell.py:select_shell` — returns `("cmd.exe", ["/c"])` on nt.
- `tests/test_pty_dispatch.py::test_dispatch_windows_pending_leg2` — asserts the
  Leg-2 sentinel raise (to be inverted).
- `pyproject.toml` — base `dependencies` (no pywinpty yet).

## Outputs

- `the_one/platform/pty_windows.py` (new) — `WindowsPtySession(PtySession)`.
- `the_one/platform/pty.py` — dispatcher `nt` branch returns `WindowsPtySession`;
  the three shared numeric constants relocated here (neutral).
- `the_one/platform/pty_unix.py` — imports the three constants from the neutral
  home instead of defining them.
- `the_one/platform/env.py` — Windows-essential keys added under an `os.name ==
  "nt"` branch; POSIX output byte-identical.
- `pyproject.toml` — `pywinpty>=2.0; sys_platform == "win32"` in dependencies.
- `tests/test_pty_dispatch.py` — `test_dispatch_windows_pending_leg2` inverted →
  asserts a `WindowsPtySession` instance on nt.
- `tests/test_pty_windows.py` (new, `skipif(os.name != "nt")`) — WindowsPtySession
  start/send/close round-trip + is_alive + last_activity (runs only on CI).
- `tests/test_execution_tools.py` / `tests/test_execution_helpers.py` —
  Windows-branch env assertions; POSIX assertions unchanged. *(Note:
  `test_execution_tools.py::TestShellTool::test_env_allowlist_invariant:336` is
  one of the 20 Windows-inventory failures — DD5's env branch interacts with it;
  whatever this leg doesn't resolve, Leg 4 triages.)*

## Acceptance Criteria

- [ ] `the_one/platform/pty_windows.py` defines `WindowsPtySession(PtySession)`
      implementing `start`/`send`/`close`/`is_alive`/`last_activity` per the ABC,
      spawning via `pywinpty` `PtyProcess.spawn`, routed through the seam
      (`get_sandbox_backend().prepare_spawn`).
- [ ] `start()` and `send()` honor the shared readiness contract (idle-window +
      caps) using the shared constants imported from the neutral module — no
      `select`/`fcntl`.
- [ ] `create_pty_session()` returns a `WindowsPtySession` on `os.name == "nt"`
      (no longer raises the sentinel); returns `UnixPtySession` on POSIX
      (unchanged).
- [ ] `tests/test_pty_dispatch.py::test_dispatch_windows_pending_leg2` is
      inverted to assert a `WindowsPtySession` is returned on nt (rename it,
      e.g. `test_dispatch_windows`).
- [ ] `pyproject.toml` declares `pywinpty>=2.0; sys_platform == "win32"`; it does
      NOT install on Linux/macOS (verify: `pip install -e ".[all-llms,dev]"` on
      Linux succeeds without pulling pywinpty).
- [ ] `the_one/platform/env.py` adds a **separate** `_WINDOWS_ENV_ALLOWLIST`
      (at minimum `SystemRoot`, `PATHEXT`, `COMSPEC`, `TEMP`, `TMP`,
      `USERPROFILE`, `USERNAME`), unioned into `_build_subprocess_env` only under
      `os.name == "nt"`. `_ENV_ALLOWLIST` is **unchanged** (the
      `test_execution_helpers.py:273` exact-tuple pin stays green on Linux); the
      `tools/execution.py` re-export still works.
- [ ] `tests/test_pty_windows.py` (Windows-gated) covers a real cmd.exe
      round-trip: start → `send("echo hello")` returns output containing
      `hello` → second `send` in the same session (state persists) → `close()` →
      `is_alive` False.
- [ ] The shared numeric constants live in a neutral module; both backends
      import them; no duplication.
- [ ] Linux default suite / bwrap / browser remain green; lint clean.

## Verification Steps

POSIX-side (implementing agent, locally — pywinpty NOT installable here):
- `pip install -e ".[all-llms,dev]"` (or `.venv/bin/python -m pip ...`) on Linux
  succeeds and does NOT install pywinpty (env marker) — `\.venv/bin/python -c
  "import importlib.util as u; print(u.find_spec('winpty'))"` prints `None`.
- `.venv/bin/python -c "from the_one.platform.pty import create_pty_session, PtySession; print('import ok')"` — no error (pty_windows is only imported inside the nt branch, so its top-level `import winpty` does not execute on Linux).
- `.venv/bin/python -m pytest tests/test_pty_dispatch.py tests/test_execution_tools.py tests/test_execution_helpers.py -x --timeout=60 -q` — POSIX dispatch + env tests pass.
- Full default suite: `.venv/bin/python -m pytest tests/ --timeout=300 -q` — green, no regression.
- `.venv/bin/python -m ruff check the_one/platform tests/test_pty_windows.py` + `ruff format --check` — clean. (Note: ruff must not choke on `import winpty` — it's a runtime import; if ruff/flake flags the unresolved import, add the appropriate ignore, but DO NOT add winpty to Linux deps.)

Windows-side (Flight Director, post-push, `windows-2022` lane):
- pywinpty installs on the runner; `tests/test_pty_windows.py` round-trip passes
  (the authoritative backend verification).
- The Windows failure inventory shrinks (the Leg-1 PTY-related skips now run/pass
  where applicable).

## Implementation Guidance

1. **Relocate shared constants** — move `_DEFAULT_IDLE_WINDOW`,
   `_DEFAULT_START_TIMEOUT`, `_READ_CHUNK` from `pty_unix.py` to the neutral
   `pty.py` (top-level, platform-agnostic). Update `pty_unix.py` to import them
   from `the_one.platform.pty`. Leave `_INTERACTIVE_SHELL_BASENAMES` in
   `pty_unix` (Unix-only).

2. **`the_one/platform/env.py`** — add a **separate** module-level
   `_WINDOWS_ENV_ALLOWLIST` tuple; in `_build_subprocess_env`, on
   `os.name == "nt"`, materialize the union of `_ENV_ALLOWLIST` +
   `_WINDOWS_ENV_ALLOWLIST` (POSIX path returns exactly today's result —
   `_ENV_ALLOWLIST` is NOT modified, preserving the
   `test_execution_helpers.py:273` exact-tuple pin). Keep the trust-surface
   discipline (hardcoded, documented; the Windows keys are non-secret OS
   essentials). Update the module docstring to note the Windows additions and
   why cmd.exe needs them (esp. `SystemRoot`).

3. **`the_one/platform/pty_windows.py`** — `WindowsPtySession(PtySession)`:
   - `__init__(cwd, shell, profile, cleanup_dir)` mirroring `UnixPtySession`'s
     signature; init `_proc=None`, `_closed=False`, `_last_activity=monotonic()`.
   - `start()`: pick shell = `self._shell_override or select_shell()[0]` (=
     `cmd.exe`; use the executable only, NOT the `/c` args — this is a persistent
     interactive session, like Unix uses the shell without `-c`). Compute the
     SpawnSpec via `get_sandbox_backend().prepare_spawn(prof, shell, [], env,
     cwd)` (no interactive-flag args for cmd.exe), calling
     `warn_if_isolation_unenforced(prof, backend)` first. `import winpty` at the
     TOP of this module (only imported on nt via the dispatcher, so safe).
     `PtyProcess.spawn([spec.command, *spec.args], cwd=spec.cwd, env=spec.env)`.
     (`import socket` at module top for the `socket.timeout` catch in the read
     loop.) Drain to idle (the socket-timeout idle helper).
   - `send(input, timeout)`: raise `RuntimeError("session not active")` if
     `self._closed or not self.is_alive` (the `is_alive` check already covers the
     never-started `_proc is None` case — no extra guard needed); append newline
     if missing; `proc.write(...)` wrapped to also catch `EOFError` (PTY closed)
     → `RuntimeError`; read-until-idle; update `_last_activity`; return `bytes`.
   - `_read_until_idle_blocking`: use the **socket-timeout** mechanism (see API
     section) — `proc.fileobj.settimeout(idle_window)`, `recv(_READ_CHUNK)` for
     raw bytes, catch `socket.timeout` as the idle-window signal, catch
     EOF/`EOFError`/empty-recv → return buffer. Accumulate `bytes`. Honor the 2s
     start cap / per-send timeout exactly as `pty_unix._read_until_idle_blocking`.
   - `start()`: after spawn, **drain the cmd.exe startup banner to idle**
     (cmd.exe is more verbose than Unix shells — multiple banner lines);
     swallow `asyncio.TimeoutError` from the drain (`except asyncio.TimeoutError:
     pass`), exactly as `pty_unix.start()` does. Consider `dimensions=(50, 220)`
     to reduce line-wrap surprises in idle-detection (default is 24×80).
   - `close()`: idempotent (guard on `self._closed`). Prefer
     **`proc.close(force=True)`** over `terminate(force=True)` — it terminates
     AND closes `fileobj`/`_server` atomically (which also unblocks any pending
     `recv` in the executor). `terminate()` alone returns a bool and does NOT
     guarantee death (SIGINT→SIGTERM, no SIGKILL). Catch the `IOError`
     `proc.close()` may raise if terminate fails. Then confirm `not proc.isalive()`
     (best-effort; Leg 3 hardens the orphan-reap guarantee). Remove `cleanup_dir`
     AFTER the close (mirror Unix's order: process dead → transport closed →
     rmtree).
   - `is_alive`: `False` if `self._closed or self._proc is None`; else
     `proc.isalive()`.
   - `last_activity`: return `_last_activity`.
   - Use `loop.run_in_executor` for the blocking write/recv/close, exactly as
     `pty_unix` wraps its blocking helpers.

4. **`the_one/platform/pty.py` dispatcher** — replace the `nt` sentinel raise:
   ```python
   if os.name == "nt":
       from the_one.platform.pty_windows import WindowsPtySession
       return WindowsPtySession(cwd=cwd, shell=shell, profile=profile, cleanup_dir=cleanup_dir)
   from the_one.platform.pty_unix import UnixPtySession
   return UnixPtySession(...)
   ```
   Do NOT add a module-scope `import` of either backend (keep them inside the
   branch, so Linux never imports pty_windows / Windows never imports pty_unix).

5. **`pyproject.toml`** — add `"pywinpty>=2.0; sys_platform == \"win32\""` to base
   `dependencies`.

6. **Tests** — invert `test_dispatch_windows_pending_leg2` →
   `test_dispatch_windows` asserting `isinstance(create_pty_session(),
   WindowsPtySession)` under `skipif(os.name != "nt")`. Add
   `tests/test_pty_windows.py` (`skipif(os.name != "nt")`) for the cmd.exe
   round-trip (these run only on the windows-2022 lane). Add Windows-branch env
   assertions. Pin sandbox to passthrough where needed via
   `THE_ONE_SANDBOX_DISABLED=1` + `THE_ONE_TEST_MODE=1` (matches the Unix PTY
   tests' convention).

7. **Do NOT attempt orphan-reap hardening** — that is Leg 3. A clean
   `terminate`-based close is sufficient here.

## Notes for the Flight Director (post-implementation)

- The backend is unverifiable locally (no pywinpty on Linux) — push to run the
  `windows-2022` lane; `test_pty_windows.py` is the real verification. Budget
  for 1-2 CI iterations on the non-blocking-read mechanism. Capture the updated
  Windows pass/fail counts into the flight log.


## Citation Audit

Citations verified against current code at leg-design time (2026-06-13):
`pty.py` dispatcher `nt` sentinel + POSIX re-export OK; `pty_unix.py:71-73`
(the three shared numeric constants — relocate target) OK; `env.py`
`_ENV_ALLOWLIST`/`_build_subprocess_env` OK; `shell.py:select_shell` (`cmd.exe`
on nt) OK; `tests/test_pty_dispatch.py:59` `test_dispatch_windows_pending_leg2`
(invert target) OK; pywinpty `PtyProcess` API verified against pywinpty 3.x
`ptyprocess.py` source (spawn; `read`/`recv` blocking-socket architecture;
`fileobj` socket; `isalive`/`terminate`/`close`/`pid`/`exitstatus`;
EOFError-on-close). Design review corrected the read mechanism (socket-timeout,
NOT `read_blocking`) and flagged `test_execution_helpers.py:273` exact-tuple
pin (→ separate `_WINDOWS_ENV_ALLOWLIST`). Repaired: env-allowlist test location
(`test_execution_tools.py:188/:336` + `test_execution_helpers.py`, NOT a
`test_env_allowlist.py`) — and noted `test_env_allowlist_invariant:336` is a
live Windows-inventory failure DD5 interacts with. 6 citations verified, 1
repaired.
