# Flight Log: Windows PTY Parity (ConPTY)

**Flight**: [flight.md](flight.md)
**Started**: — (planning)

## Summary

_Pending execution._

## Reconnaissance Report

Planning-time recon (2026-06-13), two parallel passes verified against `main`:

### PTY consumer map (is the seam clean?)
- **The `PtySession` ABC boundary is clean.** The L5b registry
  (`tools/_session_registry.py`), idle reaper, FastAPI lifespan
  (`interfaces/web/app.py:76,258`), and the four L6 `shell_session_*` tools
  (`tools/sessions.py:179`) touch only `start/send/close/is_alive/last_activity`
  + the ABC type — zero Unix assumptions leak through. A `WindowsPtySession`
  slots in via `create_pty_session` with no consumer changes. ✅ confirms DD2.
- **Unix-bound primitives are all inside `UnixPtySession`**: `pty.fork`,
  `os.execvp`, `fcntl` O_NONBLOCK, `select.select`, `os.kill`/`signal`/
  `os.waitpid`, `prctl(PR_SET_PDEATHSIG)` (Linux-only). These are what the
  Windows backend replaces (DD3/DD4).
- **`select_shell()` already has a Windows branch** (`shell.py:59-60` →
  `("cmd.exe", ["/c"])`). Env allowlist (`env.py:29`) is POSIX-shaped — Windows
  needs essential keys added (DD5).

### Import-cascade (load-bearing scope fact)
- **The app does not import on Windows today.** `platform/pty.py:82-83` raises
  `NotImplementedError` at import on `nt`; the cascade
  `web/app.py:34 → agent/factory.py:16 → tools/builtins.py:28 →
  tools/sessions.py:52 → platform/pty.py` (and `cli.py:12` via the same
  factory) means neither the web app nor the CLI can be imported on Windows.
  This flight's guard removal (DD2/DD6) unblocks it — and Flights 4/5 for
  Windows structurally depend on it. ✅ elevates this flight beyond "PTY parity."

### Non-PTY Windows portability (is DD7 "full suite required" a tar pit?)
- **Largely already done.** Deps have win_amd64 wheels (no POSIX-only native
  deps; uvicorn[standard] degrades off uvloop gracefully); every POSIX stdlib
  import is behind an `os.name`/`sys.platform` guard; `os.killpg` paths in
  `shell.py:169`/`interpreter.py:166` fall through to `proc.kill()` on Windows;
  paths use `platformdirs` (`config.py:15` → `%APPDATA%\the-one`) and
  `Path.expanduser().resolve()` (`paths.py`). The CLI entry (`main.py:cli_entry`)
  is cross-platform. ➡️ supports DD7 feasibility; the main Windows work is the
  PTY backend itself + the ~15 PTY-dependent test files needing platform gates.

### Sandbox seam Windows-readiness
- `SpawnSpec.creation_flags`/`attribute_list` (`base.py:255-256`) are
  forward-declared for a future AppContainer backend — **no consumer today**;
  this flight does NOT use them (Windows = passthrough). Factory returns
  `PassthroughSandbox` on non-Linux (`factory.py:170`); `PassthroughSandbox`
  makes no Unix assumptions. ✅ confirms DD9 (Windows unsandboxed, graceful).

### Carried-forward / migrated items
| Item | Classification | Evidence | Disposition |
|------|----------------|----------|-------------|
| Re-mark ~12 `skipif(which("bwrap"))` as `@requires_bwrap` | confirmed-live | `test_mcp_sandbox_integration.py:88`, `test_mcp_stdio_sandbox.py:447` | **Migrated from F2 Leg 1 → this flight Leg 1** (Windows CI matrix expands first) |
| `mcp/__init__` eager-load-cycle guard comments | confirmed-live | `_tool.py:157`, `_tool_provider.py:306` (lazy imports, no hazard comment) | **Migrated from F2 Leg 1 → this flight Leg 1** |

Operator confirmations (2026-06-13): DD1 pywinpty, DD7 full-suite-required,
DD8 author-and-operator-run behavior test — all selected. DD-OQ (orphan reap)
deliberately left to empirical Leg 3 resolution on the operator's host + CI.

## Design Review (Phase 5b)

Two Architect review cycles (2026-06-13), both "approve with changes"; all
findings incorporated:

- **Round 1** (1 high, 2 med, 1 low + verifications): confirmed the load-bearing
  import-cascade claim (app + CLI un-importable on Windows today) and the
  `_wrapped`-always-False claim against code. Corrected DD9 (containment tests
  are `@requires_bwrap`-gated, NOT posix-skipif — the stated mechanism was
  wrong and would have misled the implementer). Made DD7's tar-pit concrete
  (cited `test_execution_tools.py`'s un-gated POSIX command strings run against
  cmd.exe) and turned Leg 1 into a failure-inventory *gate*, not a "collect"
  step. **Adopted the architect's split-module alternative** (DD2:
  `pty.py` neutral dispatcher / `pty_unix.py` / `pty_windows.py`) over
  lazy-per-method imports — disjoint platform surfaces, sidesteps the
  `signal.SIGKILL`-absent-on-Windows footgun. Added DD10 (Leg-4 test triage:
  parametrize wrapper tests / POSIX-gate shell-semantics tests), DD5 consumer
  audit, pywinpty Flight-5 freeze note + pytest-asyncio teardown watch-out.
- **Round 2** (1 high, well-bounded): the split-module move would have broken
  two `UnixPtySession`-by-name importers (`platform/__init__.py:44` public
  re-export, `test_pty_session.py:34`) on POSIX — fixed via a POSIX-guarded
  re-export keeping the name importable from `the_one.platform.pty`; flagged
  that `TestWindowsGuard` (`test_pty_session.py:243-260`) asserts the
  now-deleted import-raises contract and Leg 1 must invert it; confirmed the
  libc fork-safety singleton travels with `UnixPtySession` and the
  `platform↔sandbox` cycle-avoidance is preserved; reconciled the Technical
  Approach doc-drift; noted DD10's third "already-portable" residue. Max 2
  cycles reached; spec locked.

## Decisions

_Pending execution — planning-time decisions live in flight.md Design Decisions._

## Deviations

_None yet._

## Anomalies

_None yet._

## Leg Progress

_Pending leg design._
