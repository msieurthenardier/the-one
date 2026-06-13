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

## Flight Director Notes

**2026-06-13 — Flight execution started (`/agentic-workflow`).**
- Phase file `.flightops/agent-crews/leg-execution.md` loaded; structure valid
  (Crew / Interaction Protocol / Prompts all present).
- **Crew-file staleness override (skill–project boundary):** the Implement
  prompt instructs `docker exec the-one pytest …` — stale, predating Flight 1's
  full de-Dockerization (the project now tests host-native via
  `.venv/bin/python -m pytest`, browser/long-subprocess suites via
  `scripts/run-tests.sh`). Per CLAUDE.md ("Do not rely on crew prompt files to
  carry skill-required instructions"), the FD issues the correct host-native
  test invocation directly in every Developer spawn, overriding the crew file's
  Docker line. (Crew file itself not edited — it's project-owned; the override
  is per-spawn.)
- **Reviewer model scaling:** crew default is Haiku. Per F1's standardized
  "scale reviewer to diff risk" lesson, the FD will use **Sonnet** for legs
  touching PTY process-supervision / teardown / fork-safety (Legs 2, 3) and the
  Haiku default for lighter legs (1, 4-docs). No leg here touches the
  sandbox/denylist security surface (Windows = passthrough).
- **Structural reality — CI- and operator-gated flight (not fully autonomous):**
  implementing agents run on Linux/WSL2 and cannot exercise the Windows backend.
  Windows verification comes only from the `windows-2022` CI lane (push-gated)
  and, for orphan-reap (Leg 3) and the behavior test (Leg 5), the operator's
  physical Windows host. The skill's "batch all autonomous legs → one commit"
  model will be adapted: the branch is pushed after Windows-relevant legs so CI
  can produce the Leg-1 failure inventory (DD7) and verify the backend before
  later legs are scoped against it. The adaptation will be logged at the point
  it's applied, with rationale.
- Flight status `ready` → `in-flight`. Starting Leg 1 design.

## Flight Director Notes (continued)

**2026-06-13 — Leg 1 complete; CI-gating adaptation applied.**
- **Code review** (Reviewer/Sonnet — scaled up from the Haiku default because the
  leg *moves the fork-safety machinery* under a byte-identical invariant, where
  Haiku could rubber-stamp): `[HANDOFF:confirmed]`. All 12 acceptance criteria
  met; byte-identical move verified (constants, `_get_libc`/prctl, both teardown
  paths); cycle safe + ordering comment present; no POSIX regression (3057
  passed); the new `pty_unix.py` even corrected a stale `_load_libc()` docstring
  typo. No fix cycle needed.
- **Deviation (Developer):** the leg cited "nine decorators" in
  `test_mcp_sandbox_integration.py`; the file actually had **12**
  `@requires_bwrap` usages — all converted. A now-unused `import shutil` in
  `test_mcp_stdio_sandbox.py` was removed to satisfy lint. Both benign.
- **CI-gating adaptation (pre-registered in FD Notes, now applied):** reverting
  from the skill's batch "all legs → one commit" model to a **per-leg
  review→commit→push cadence** for this flight. Rationale: the `windows-2022`
  lane is the only authoritative check that the module imports on Windows and is
  the source of the DD7/DD10 failure inventory that scopes Leg 4 — and Leg 2's
  backend can only be CI-verified, not run locally (implementing agents are on
  Linux/WSL2). Batching would design Legs 2-5 blind to Windows reality. Leg 1 is
  committed and pushed now to produce the inventory before Leg 2 is designed.
  Cost: one `windows-2022` run (2× billing) — within the DD7-approved envelope.

## Decisions

_Pending execution — planning-time decisions live in flight.md Design Decisions._

## Deviations

_None yet._

## Anomalies

_None yet._

## Leg Progress

### Leg 1 — windows-import-unblock

- **Status**: landed (2026-06-13)
- **Design review** (1 cycle, Developer/Sonnet, "approve with changes" — all
  incorporated; no second cycle needed, fixes were precision not architecture):
  - [high] `tools/_session_registry.py:33-35` docstring would become a stale
    lie (claims `PtySession` raises on Windows / registry Unix-only) → added as
    a docstring-update target + acceptance criterion.
  - [med] `windows-2022` CI job risks PowerShell stripping the quotes in
    `pip install -e ".[all-llms,dev]"` → added `defaults.run.shell: bash`.
  - [med] bwrap re-mark left implementer guessing → resolved concretely against
    `test_pty_sandbox.py:55` convention: drop the `skipif` fallback, use
    `@pytest.mark.requires_bwrap`; delete the module-scope alias and update all
    nine decorators in the integration file.
  - Suggestions folded: `platform/__init__.py` docstring acceptance criterion;
    explicit nine-decorator callout; `test_session_tools.py:456` per-test skipif
    stays (no spurious module guard); `test_dispatch_windows_pending_leg2` gets
    an inline "Leg 2 inverts this" comment.
  - Designer call on the ABC-location question: keep `PtySession` in `pty.py`
    with the reviewer-confirmed-safe POSIX re-export cycle + an explicit
    ordering comment (minimal surface); `pty_abc.py` neutral module declined,
    revisitable in Leg 2.
- **Implementation outcomes (2026-06-13)**:
  - **Files changed** (9 files):
    - `the_one/platform/pty_unix.py` (new) — `UnixPtySession` + fork-safety
      machinery moved byte-identically from `pty.py`; imports `PtySession` from
      `the_one.platform.pty`.
    - `the_one/platform/pty.py` — reduced to platform-neutral dispatcher:
      `PtySession` ABC + `create_pty_session`; no module-scope POSIX stdlib;
      import-time guard deleted; POSIX back-compat re-export added with ordering
      comment; `create_pty_session()` raises `NotImplementedError("WindowsPtySession
      lands in M15 F3 Leg 2")` on `os.name == "nt"`.
    - `the_one/platform/__init__.py` — module docstring `pty` line updated (no
      longer "raises on Windows"); POSIX-guard comment clarified.
    - `the_one/tools/_session_registry.py` — docstring updated: `PtySession` now
      imports cleanly on all platforms; Windows exercise lands in Leg 2.
    - `tests/test_pty_session.py` — `pytestmark` replaced with
      `allow_module_level` skip before the `UnixPtySession` import; `TestWindowsGuard`
      class removed (inverted intent covered in `test_pty_dispatch.py`).
    - `tests/test_pty_dispatch.py` (new) — platform-neutral: `test_module_imports_
      on_current_platform`, `test_dispatch_posix`, `test_dispatch_windows_pending_leg2`
      (with inline "Leg 2 inverts this" comment).
    - `tests/test_mcp_sandbox_integration.py` — module-scope `requires_bwrap`
      alias line deleted; all 12 `@requires_bwrap` decorators replaced with
      `@pytest.mark.requires_bwrap`.
    - `tests/test_mcp_stdio_sandbox.py` — `@pytest.mark.skipif(shutil.which("bwrap")
      is None, …)` at line 447 replaced with `@pytest.mark.requires_bwrap`; unused
      bare `import shutil` removed (lint clean).
    - `the_one/mcp/_tool.py` + `_tool_provider.py` — cycle-hazard comments added
      above the lazy `SandboxError` imports naming the `mcp/__init__` eager-load
      cycle.
    - `.github/workflows/test.yml` — `windows` job added on `windows-2022` with
      `shell: bash` default, no `-x`, non-required.
  - **Verification steps — all passed**:
    - `pytest tests/test_pty_session.py tests/test_pty_dispatch.py -x --timeout=60 -q`:
      18 passed, 1 skipped.
    - POSIX import smoke: `from the_one.platform.pty import PtySession, UnixPtySession,
      create_pty_session` → `posix import ok`.
    - Windows import simulation (os.name='nt' patch + reload): `nt import ok`.
    - Cascade smoke: `import the_one.tools.sessions; import the_one.agent.factory`
      → `cascade import ok`.
    - `pytest -m requires_bwrap tests/ --timeout=300 -q`: **41 passed, 3 skipped,
      3603 deselected** (re-marked tests correctly selected; 31+ threshold exceeded).
    - Full default suite `pytest tests/ --timeout=300 -q`: **3057 passed, 1 skipped,
      589 deselected** — no regressions.
    - `ruff check` + `ruff format --check` on all modified paths: clean.
  - **Deviations**: One minor deviation from leg guidance — the leg spec cited
    "nine decorators" in `test_mcp_sandbox_integration.py` but the actual file
    had **12** `@requires_bwrap` decorators (the leg design review counted only
    the un-skipped tests #1-9, not counting #6b/6c/6d which also carried the
    alias decorator). All 12 were converted. Also, removing the `@requires_bwrap`
    alias from `test_mcp_sandbox_integration.py` left no `shutil` usage in
    `test_mcp_stdio_sandbox.py`'s module scope (the existing `shutil` uses there
    are via `bwrap_module.shutil`/`factory_module.shutil`), so the bare `import
    shutil` was removed to keep lint clean — this was the right call per the leg's
    "ruff check clean" acceptance criterion.
  - **Windows-side verification**: deferred to CI post-push per leg design (the
    implementing agent runs Linux/WSL2; authoritative Windows check is the
    `windows-2022` lane). FD captures inventory before scoping Leg 4.
