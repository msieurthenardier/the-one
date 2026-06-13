# Leg: windows-import-unblock

**Status**: completed
**Flight**: [Windows PTY Parity (ConPTY)](../flight.md)

## Objective

Split `the_one/platform/pty.py` into a platform-neutral dispatcher + a
`pty_unix.py` backend so the module (and the app/CLI import cascade) imports
cleanly on Windows, add a non-required `windows-2022` CI lane that runs the
default suite as a failure-inventory gate, and land the two F1 ride-alongs —
*without* the Windows PTY backend itself (deferred to Leg 2).

## Context

- **DD2 (split-module):** `platform/pty.py` → neutral `PtySession` ABC +
  `create_pty_session` dispatcher with **no module-scope platform stdlib**;
  `UnixPtySession` (+ its `fcntl`/`pty`/`select`/`signal` imports, the
  `_get_libc`/`_libc` fork-safety singleton, and the fork-safety docstring)
  moves byte-identically to `platform/pty_unix.py`. The import-time
  `NotImplementedError` guard (`pty.py:82-83`) is deleted.
- **DD6 (cascade unblock):** the goal is `import the_one.platform.pty` (and
  therefore `web/app.py → agent/factory.py:16 → tools/builtins.py:28 →
  tools/sessions.py:52`) succeeding on Windows. `tools/sessions.py:52` imports
  the `create_pty_session` *function* (does not call it at import), so the
  cascade unblocks even though the Windows backend is deferred.
- **Leg-1/Leg-2 boundary:** the Windows backend (`pty_windows.py`,
  `WindowsPtySession`, pywinpty) is **Leg 2**. In this leg,
  `create_pty_session()` on `os.name == "nt"` raises
  `NotImplementedError("WindowsPtySession lands in M15 F3 Leg 2")` *inside the
  function* — the module still imports. The honest Leg-1 contract is "module
  imports on Windows," not "PTY works on Windows."
- **DD7 (inventory gate):** the `windows-2022` job runs the full default suite
  and produces the *actual Windows failure inventory* (the red list that scopes
  Leg 4 per DD10). It is **non-required** this leg (branch-protection flip is
  Leg 4). It must NOT use `-x` — we want the complete failure list, not
  first-failure.
- **Implementing agent runs on Linux/WSL2** — it can verify the POSIX side
  locally (suite must stay green) but **cannot** verify the Windows import or
  produce the inventory; those are confirmed on the `windows-2022` lane after
  the Flight Director pushes the branch (recorded as the FD CI-gating
  adaptation). Do not block the leg on local Windows verification.
- **F1 lesson carried:** security-invariant/denylist surfaces are untouched
  here (Windows = passthrough); this is a structural refactor + CI + test
  hygiene leg.

## Inputs

What exists before this leg:
- `the_one/platform/pty.py` — single module, `UnixPtySession` + ABC + factory,
  raises `NotImplementedError` at import on `nt` (`pty.py:82-83`).
- `the_one/platform/__init__.py:42-48` — POSIX-guarded re-export of
  `PtySession`, `UnixPtySession`, `create_pty_session` from `the_one.platform.pty`.
- `tests/test_pty_session.py` — module-level `pytestmark =
  skipif(os.name != "posix")` (line 27-30), top-level
  `from the_one.platform.pty import (PtySession, UnixPtySession,
  create_pty_session)` (line 32-36), and `TestWindowsGuard` (lines 243-260)
  asserting import *raises* on Windows.
- `tests/test_mcp_sandbox_integration.py:88` and
  `tests/test_mcp_stdio_sandbox.py:447` — `skipif(shutil.which("bwrap") is None)`
  on bwrap integration tests (should be `@pytest.mark.requires_bwrap`).
- `the_one/mcp/_tool.py:157` and `the_one/mcp/_tool_provider.py:306` — lazy
  `from the_one.platform.sandbox.errors import SandboxError` with no comment
  naming the `mcp/__init__` eager-load-cycle hazard.
- `the_one/tools/_session_registry.py:33-35` — module docstring states
  `PtySession` "raises NotImplementedError at import time on Windows" and the
  registry "is therefore Unix-only" — becomes a stale lie after this leg.
- `tests/test_session_tools.py:456` — per-test `skipif(os.name != "posix")` on
  `test_end_to_end_real_pty_round_trip` (correct as-is post-fix; see guidance).
- `.github/workflows/test.yml` — `test` / `browser` / `bwrap` jobs (Linux only).

## Outputs

What exists after this leg:
- `the_one/platform/pty.py` — neutral: `PtySession` ABC + `create_pty_session`
  dispatcher; no module-scope `fcntl`/`pty`/`select`/`signal`/`ctypes`; imports
  on every OS; POSIX-guarded re-export `if os.name == "posix": from .pty_unix
  import UnixPtySession` for back-compat.
- `the_one/platform/pty_unix.py` — `UnixPtySession` + fork-safety machinery,
  moved byte-identically.
- `tests/test_pty_session.py` — skips via `pytest.skip(...,
  allow_module_level=True)` BEFORE the `UnixPtySession` import (clean skip on
  Windows, no collection error); `TestWindowsGuard` removed (relocated+inverted
  below).
- `tests/test_pty_dispatch.py` (new, platform-neutral) — asserts the module
  imports on the current platform and `create_pty_session` dispatches correctly
  (POSIX → `UnixPtySession`; Windows → currently raises the Leg-2 sentinel).
- `.github/workflows/test.yml` — new non-required `windows` job on
  `windows-2022` running the default suite (no `-x`).
- The two bwrap test files re-marked with `@pytest.mark.requires_bwrap`; the two
  `SandboxError` lazy-import sites carry a cycle-hazard comment.

## Acceptance Criteria

- [ ] `the_one/platform/pty.py` contains no module-scope import of `fcntl`,
      `pty`, `select`, `signal`, or `ctypes`; the import-time `os.name == "nt"`
      `NotImplementedError` guard is gone.
- [ ] `UnixPtySession` and its fork-safety machinery (`_get_libc`/`_libc`, the
      fork-safety docstring) live in `the_one/platform/pty_unix.py`, behaviorally
      byte-identical (no logic change).
- [ ] `the_one.platform.pty` and `the_one.platform` import without error when
      `os.name` is simulated as `"nt"` (see Verification — collection-time test).
- [ ] `from the_one.platform.pty import UnixPtySession` still works on POSIX
      (back-compat re-export); `the_one/platform/__init__.py` re-export and
      `tests/test_pty_session.py:32` import unchanged and passing on POSIX.
- [ ] `create_pty_session()` returns a `UnixPtySession` on POSIX and raises
      `NotImplementedError` naming Leg 2 on `nt` (asserted in
      `test_pty_dispatch.py`).
- [ ] `TestWindowsGuard` (old import-raises assertion) is removed; the inverted
      intent (import *succeeds* on Windows) is covered in `test_pty_dispatch.py`.
- [ ] `tests/test_mcp_sandbox_integration.py:88` and
      `tests/test_mcp_stdio_sandbox.py:447` use `@pytest.mark.requires_bwrap`
      (not raw `skipif(which("bwrap"))`); they still deselect by default and
      still run under the `bwrap` CI job.
- [ ] `the_one/mcp/_tool.py:157` and `the_one/mcp/_tool_provider.py:306` carry a
      comment naming the `mcp/__init__` eager-load-cycle hazard that requires the
      lazy `SandboxError` import.
- [ ] `.github/workflows/test.yml` has a non-required `windows` job on
      `windows-2022` running the default suite without `-x`.
- [ ] `the_one/tools/_session_registry.py:33-35` docstring no longer claims
      `PtySession` raises on Windows / the registry is Unix-only-by-import (it
      now collects on all platforms; backend exercised from Leg 2).
- [ ] `the_one/platform/__init__.py` docstring `pty` line (line 11) no longer
      says "importing on Windows raises NotImplementedError".
- [ ] The Linux default suite, `bwrap` suite, and browser suite remain green
      (no regression) — verified locally by the implementing agent.

## Verification Steps

POSIX-side (implementing agent, locally — host-native, NO Docker):
- `.venv/bin/python -m pytest tests/test_pty_session.py tests/test_pty_dispatch.py -x --timeout=60 -q` — passes (UnixPtySession contract + dispatch).
- `.venv/bin/python -c "from the_one.platform.pty import PtySession, UnixPtySession, create_pty_session; print('posix import ok')"` — no error.
- Simulate Windows import cleanly: `.venv/bin/python -c "import unittest.mock as m, os; \
  _=m.patch.object(os,'name','nt').start(); import importlib, the_one.platform.pty as p; importlib.reload(p); print('nt import ok')"` — prints `nt import ok`, no `NotImplementedError`. *(Note: a full `os.name=='nt'` simulation is imperfect on Linux — the authoritative Windows-import check is the `windows-2022` CI lane post-push; this local check guards the module-scope-import contract.)*
- Cascade smoke: `.venv/bin/python -c "import the_one.tools.sessions; import the_one.agent.factory; print('cascade import ok')"` — no error on POSIX (confirms the function-import path is intact).
- `.venv/bin/python -m pytest -m requires_bwrap tests/ --timeout=300 -q` — 31+ pass (re-marked tests still selected by the bwrap job).
- Full default suite: `.venv/bin/python -m pytest tests/ --timeout=300 -q` — green (no regression from the split).
- `.venv/bin/python -m ruff check the_one/platform tests/test_pty_dispatch.py .github` and `ruff format --check` — clean.

Windows-side (Flight Director, post-push, on the `windows-2022` CI lane):
- The `windows` job's pytest **imports** `the_one.platform.pty` and collects the
  suite without the prior `NotImplementedError` (the module-import goal).
- The job's log is captured as the **failure inventory** for DD10/Leg 4 scoping
  (the red list — expected non-empty; this job is non-required).

## Implementation Guidance

1. **Create `the_one/platform/pty_unix.py`** — move `UnixPtySession`, the
   `_get_libc`/`_libc` singleton, the `_INTERACTIVE_SHELL_BASENAMES` and
   `_DEFAULT_*`/`_READ_CHUNK` constants it uses, the module's POSIX stdlib
   imports (`fcntl`, `pty`, `select`, `signal`, `ctypes`), and the fork-safety
   docstring. **Byte-identical logic** — this is a mechanical move, not a
   rewrite. Keep the function-level `from the_one.platform.sandbox import ...`
   imports inside `start()` function-level (preserves the `platform ↔
   platform.sandbox` cycle avoidance). The belt-and-suspenders
   `if os.name != "posix": raise` inside `start()` (pty.py:255-261) stays.

2. **Reduce `the_one/platform/pty.py`** to: the module docstring (updated — no
   longer "raises on Windows"), the `PtySession` ABC, the shared
   constants if the ABC/dispatcher needs them, and `create_pty_session`. Delete
   the import-time guard (lines 82-83) and the POSIX stdlib imports. The
   dispatcher:
   ```python
   def create_pty_session(cwd=None, shell=None, profile=None, cleanup_dir=None) -> PtySession:
       if os.name == "nt":
           raise NotImplementedError("WindowsPtySession lands in M15 F3 Leg 2")
       from the_one.platform.pty_unix import UnixPtySession
       return UnixPtySession(cwd=cwd, shell=shell, profile=profile, cleanup_dir=cleanup_dir)
   ```
   Add the back-compat re-export at module scope:
   ```python
   if os.name == "posix":
       from the_one.platform.pty_unix import UnixPtySession  # noqa: F401  (back-compat re-export)
   ```
   Decide where `PtySession` ABC lives: keep it in `pty.py` (it's
   platform-neutral, imports cleanly everywhere) and have `pty_unix.py` import
   it via `from the_one.platform.pty import PtySession`. Confirm no import cycle
   results (pty.py must not import pty_unix at module top except under the POSIX
   guard — that guard is fine since pty_unix importing pty.py for the ABC is a
   one-way edge: pty.py(ABC) ← pty_unix; the POSIX re-export pty.py → pty_unix
   closes a cycle ONLY on POSIX and Python handles it because the ABC is defined
   above the re-export line. Order: define `PtySession` and `create_pty_session`
   FIRST, then the `if os.name == "posix": from .pty_unix import UnixPtySession`
   re-export LAST in the module). **Add an explicit ordering comment** at the
   re-export line naming the constraint (the ABC must be defined above this line;
   reordering would deadlock the POSIX import) — the cycle is reviewer-confirmed
   safe but the ordering is load-bearing, so guard it like the module's other
   fork-safety conventions. (A neutral `pty_abc.py` was considered and declined
   for minimal surface; revisit in Leg 2 if the cycle proves fragile.)

3. **`the_one/platform/__init__.py`** — no change needed if the POSIX-guarded
   block keeps importing the three names from `the_one.platform.pty` (the
   re-export makes `UnixPtySession` available there on POSIX). Update the
   module docstring's pty line (no longer "raises NotImplementedError on
   Windows" — now "POSIX backend via pty_unix; Windows backend lands F3 L2").

4. **`the_one/tools/_session_registry.py:33-35`** — update the module docstring:
   `PtySession` now imports cleanly on all platforms (no import-time raise), so
   the registry collects on Windows too; concrete Windows exercise lands with
   the backend in Leg 2. Remove the "raises NotImplementedError at import time
   on Windows / Unix-only" claim.

5. **`tests/test_pty_session.py`** — replace the module-level `pytestmark`
   skip with an early `allow_module_level` skip placed **before** the
   `UnixPtySession` import so the file cleanly skips on Windows without a
   collection-time ImportError:
   ```python
   import os, pytest
   if os.name != "posix":
       pytest.skip("UnixPtySession requires POSIX (pty.fork)", allow_module_level=True)
   from the_one.platform.pty import PtySession, UnixPtySession, create_pty_session
   ```
   **Delete `TestWindowsGuard`** (lines 243-260) — its "import raises on
   Windows" assertion is the contract this leg removes, and it lives in a
   POSIX-skipped file so it can't test Windows behavior anyway.

6. **Create `tests/test_pty_dispatch.py`** (platform-neutral — NOT skipped on
   Windows) covering the relocated+inverted intent:
   - `test_module_imports_on_current_platform`: `import the_one.platform.pty`
     and `the_one.platform` — no raise (runs everywhere; on the Windows CI lane
     this is the real import-success assertion).
   - `test_dispatch_posix` (`skipif(os.name != "posix")`): `create_pty_session()`
     returns a `UnixPtySession`.
   - `test_dispatch_windows_pending_leg2` (`skipif(os.name != "nt")`):
     `create_pty_session()` raises `NotImplementedError` mentioning Leg 2.
     **Add an inline comment in the test body** noting Leg 2 INVERTS this
     (from `raises` to `returns WindowsPtySession`) — so a future reader of the
     CI inventory doesn't mistake it for a broken test.
   - **Do NOT add a module-level guard to `tests/test_session_tools.py`** — its
     per-test `skipif(os.name != "posix")` at line 456 stays correct, and the
     file collects cleanly on Windows after the split (its `_pty_fixtures.py`
     `MockPtySession` imports `PtySession`, which now imports everywhere).

7. **Re-mark bwrap tests** — **concrete decision** (resolved at design review
   against `test_pty_sandbox.py:55`, which uses ONLY `@pytest.mark.requires_bwrap`
   with no `skipif` fallback): the repo convention is that the registered marker
   deselects locally via `addopts` and `-m requires_bwrap` is run only where
   bwrap exists (the `bwrap` CI job installs it). So **drop the `skipif`
   fallback and use the registered marker** at both sites:
   - `tests/test_mcp_sandbox_integration.py`: **delete the module-scope alias
     line `requires_bwrap = pytest.mark.skipif(...)` (line 88)** and change each
     of the **nine** `@requires_bwrap` decorators (tests #1-9) to
     `@pytest.mark.requires_bwrap`. Do not leave any test referencing the
     deleted alias name (half-application would `NameError` at collection).
   - `tests/test_mcp_stdio_sandbox.py:447`: replace
     `@pytest.mark.skipif(shutil.which("bwrap") is None, …)` with
     `@pytest.mark.requires_bwrap`.
   Confirm post-change: deselected by default `addopts`, selected by
   `-m requires_bwrap`, and the `bwrap` CI job still runs them. (The graceful
   skip-when-absent is intentionally dropped — it matches the established
   `test_pty_sandbox.py` convention.)

8. **Cycle-hazard comments** — at `the_one/mcp/_tool.py:157` and
   `the_one/mcp/_tool_provider.py:306`, add a comment above the lazy
   `from the_one.platform.sandbox.errors import SandboxError`, e.g.:
   ```python
   # Lazy import (NOT module-top): `the_one.mcp.__init__` eagerly imports this
   # module (`_tool`/`_tool_provider`), so a top-level SandboxError import
   # re-opens the mcp/__init__ eager-load cycle. Keep it function-local.
   ```

9. **CI job** — in `.github/workflows/test.yml` add (mirroring the `test` job
   but pinned and without `-x`):
   ```yaml
     windows:
       runs-on: windows-2022
       defaults:
         run:
           shell: bash   # Git Bash on the runner — avoids PowerShell stripping
                         # the quotes in `pip install -e ".[all-llms,dev]"` and
                         # obscuring the real test inventory behind an install fail.
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.11"
             cache: pip
         - run: pip install -e ".[all-llms,dev]"
         - name: Run default suite (Windows — failure-inventory gate, non-required)
           run: python -m pytest tests/ --timeout=300 --tb=short
   ```
   Do NOT add it to branch protection (Leg 4 flips it to required). Note: this
   job is expected RED this leg — it produces the inventory.

## Notes for the Flight Director (post-implementation)

- After the Developer lands this leg (POSIX-green locally), the branch must be
  **pushed** so the `windows-2022` lane runs — this is the CI-gating adaptation:
  the Windows import-success confirmation and the failure inventory (DD7/DD10)
  only exist on CI. Capture the inventory into the flight log before scoping
  Leg 4.

## Citation Audit

All code citations verified against current code at leg-design time (2026-06-13):
`pty.py:82-83` (import guard) OK; `pty.py:255-261` (belt-and-suspenders posix
check) OK; `platform/__init__.py:42-48` (POSIX-guarded re-export) OK;
`test_pty_session.py:27-36` (pytestmark + import) and `:243-260`
(`TestWindowsGuard`) OK; `tools/sessions.py:52` (`create_pty_session` import)
OK; `agent/factory.py:16` (`BuiltinToolProvider` import) OK; `tools/builtins.py:28`
(`from the_one.tools.sessions import`) OK; `mcp/_tool.py:157` and
`mcp/_tool_provider.py:306` (lazy `SandboxError` imports) OK; `mcp/__init__.py`
eager `_tool`/`_tool_provider` imports OK; `test_mcp_sandbox_integration.py:88`
(module-scope `requires_bwrap` skipif alias, tests #1-9 per :86-87) OK —
refined guidance to preserve absent-host skip; `test_mcp_stdio_sandbox.py:447`
(per-test `skipif(which("bwrap"))`) OK; `test_pty_sandbox.py:55` (marker
convention reference) OK. No drift; 14 citations clean.
