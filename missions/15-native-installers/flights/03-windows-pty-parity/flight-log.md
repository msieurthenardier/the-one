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

## Windows Failure Inventory (DD7/DD10 gate — Leg 1 CI, PR #110)

**Captured from the `windows-2022` lane, 2026-06-13** (run 27475519721, job
81213961283). **The headline result: the suite COLLECTED AND RAN on Windows —
no ImportError, no collection errors.** The Leg-1 import-cascade unblock works.

- **Linux lanes all green** (test 3m37s, browser 15m, bwrap 1m24s, lint) — zero
  regression from the split.
- **Windows: 20 failed, 3014 passed, 9 skipped, 589 deselected, in 25m40s.**
  (Windows wall-clock ≈ 7× Linux — a DD7 cost data point; still within the
  2×-billing envelope the operator approved.)

**DD7 verdict: HOLDS. Divert does NOT fire** — 20 failures across 8 files, all
mechanical/test-side, comfortably ~1 leg of work (Leg 4). No product-blocking
Windows failure.

**Triage (scopes Leg 4 per DD10):**

| Bucket | Count | Tests | Leg-4 disposition |
|--------|------:|-------|-------------------|
| POSIX home-path (`~` → `/home/...`) | 8 | `test_filesystem_tools.py` ×7 tilde-expansion + `test_filesystem_helpers.py` tilde-canonicalize | Parametrize with platform-neutral home, OR confirm `expanduser` behavior is correct on Windows and fix the assertion |
| cmd.exe command strings | 8 | `test_execution_tools.py` ×6 (env/cwd/timeout/output-cap), `test_platform_shell.py` ×2 (env_override, timeout) | DD10 split: parametrize wrapper tests w/ cmd.exe equivalents; POSIX-gate shell-semantics tests |
| POSIX file perms (0600) | 1 | `test_encryption.py::test_key_file_permissions` | POSIX-gate (Windows has no chmod 0600 semantics) |
| **Real test-robustness bug** | 1 | `test_provider_repository.py::test_update_changes_fields` — `updated_at` collides under fast update (identical microsecond timestamp) | Fix properly (monotonic-distinct or `>=`); F1-`last_activity` flavored cross-platform fragility |
| **Test encoding hygiene** | 1 | `test_token_definitions.py` — `css_path.read_text()` w/o `encoding="utf-8"` → cp1252 `UnicodeDecodeError` on Windows | Add `encoding="utf-8"`. **Leg 4 must also grep PRODUCT code for unencoded `open()`/`read_text()` — same pattern there is a REAL Windows bug** (Flight-5 frozen-app relevant) |
| Env handling (DD5-adjacent) | 1 | `test_mcp_stdio_sandbox.py::test_connect_stdio_sdk_default_env_preserved_through_setenv` | Inspect in Leg 4 alongside the DD5 Windows env-allowlist work |

The encoding `UnicodeDecodeError` is the inventory's standout find — precisely
the class of latent Windows bug that running the full suite on Windows (DD7)
exists to surface. Even though this instance is test-side, it mandates the
product-code audit noted above.

### Leg 2 — windows-pty-backend

- **Status**: landed (2026-06-13)
- **Design review** (1 cycle, Developer/Sonnet — read the pywinpty *source*;
  "approve with changes", 3 highs all incorporated):
  - [high] **My idle-read design was wrong.** pywinpty `PtyProcess.read()` does a
    *blocking* `fileobj.recv()` fed by a daemon thread; `read_blocking=False`
    after spawn is a no-op (closure captures the value at construction).
    Corrected to the **socket-timeout** mechanism (`fileobj.settimeout` +
    `recv` + catch `socket.timeout`). This would have burned multiple 25-min CI
    round-trips to discover empirically — the design review paid for itself.
  - [high] `terminate(force=True)` returns a bool and does NOT guarantee death
    (no SIGKILL) → use `proc.close(force=True)` (atomic terminate + socket
    teardown), catch its `IOError`.
  - [high] `_ENV_ALLOWLIST` is pinned to an exact 8-tuple
    (`test_execution_helpers.py:273`) → DD5 must add a **separate**
    `_WINDOWS_ENV_ALLOWLIST` unioned only on `nt`, leaving the pin green.
  - Mediums folded: `read()` returns `str` not `bytes` → accumulate raw bytes
    from `recv`; wrap `write` for `EOFError`; swallow the cmd.exe banner drain's
    `TimeoutError`; commit the shared constants to `pty.py`; `dimensions` note.
  - **No 2nd cycle:** the reviewer's findings were prescriptive (exact corrected
    design), faithfully transcribed; self-verified the incorporation for
    coherence. Spawning a fresh agent would re-derive the same pywinpty
    internals. If the read mechanism still misbehaves, CI catches it (the leg
    budgets 1-2 CI iterations on it).
- **Implementation outcomes (2026-06-13)**:
  - **Files changed** (7 files):
    - `the_one/platform/pty_windows.py` (new) — `WindowsPtySession(PtySession)`
      implementing `start`/`send`/`close`/`is_alive`/`last_activity`; uses
      socket-timeout idle-read mechanism (`proc.fileobj.settimeout` + `recv` +
      `socket.timeout` catch); `close()` uses `proc.close(force=True)` for
      atomic terminate + socket teardown; `dimensions=(50, 220)` for
      cmd.exe banner width.
    - `the_one/platform/pty.py` — three shared constants
      (`_DEFAULT_IDLE_WINDOW`, `_DEFAULT_START_TIMEOUT`, `_READ_CHUNK`)
      relocated here from `pty_unix.py`; `create_pty_session()` `nt` branch
      replaced: imports `WindowsPtySession` and returns it (import kept inside
      the branch so Linux never loads `pty_windows`); module docstring updated.
    - `the_one/platform/pty_unix.py` — removed the three constant definitions;
      imports them from `the_one.platform.pty` instead. `_INTERACTIVE_SHELL_BASENAMES`
      left in place (Unix-only).
    - `the_one/platform/env.py` — added `_WINDOWS_ENV_ALLOWLIST` constant
      (7 Windows-essential keys: `SystemRoot`, `PATHEXT`, `COMSPEC`, `TEMP`,
      `TMP`, `USERPROFILE`, `USERNAME`); `_build_subprocess_env` unions it in
      only on `os.name == "nt"`; `_ENV_ALLOWLIST` unchanged (8-tuple pin green);
      module docstring updated.
    - `pyproject.toml` — `"pywinpty>=2.0; sys_platform == \"win32\""` added to
      base `dependencies`. Verified not installed on Linux (env marker works).
    - `tests/test_pty_dispatch.py` — `test_dispatch_windows_pending_leg2` inverted
      and renamed to `test_dispatch_windows`; now asserts `isinstance(...,
      WindowsPtySession)` under `skipif(os.name != "nt")`.
    - `tests/test_pty_windows.py` (new, `pytestmark` skipif `os.name != "nt"`) —
      7 tests: `test_start_creates_alive_session`, `test_send_echo_hello_round_trip`,
      `test_send_second_command_state_persists`, `test_close_makes_session_not_alive`,
      `test_close_is_idempotent`, `test_last_activity_updated_after_send`,
      `test_send_after_close_raises_runtime_error`.
  - **Verification steps (POSIX-side) — all passed**:
    - `from the_one.platform.pty import create_pty_session, PtySession; print('import ok')`:
      no error — `pty_windows` not imported on Linux.
    - `importlib.util.find_spec('winpty')`: prints `None` — pywinpty not installed.
    - `.venv/bin/python -m pip install -e ".[all-llms,dev]"` on Linux: clean,
      pywinpty not pulled (env marker `sys_platform == "win32"` honored).
    - `pytest tests/test_pty_dispatch.py tests/test_execution_tools.py tests/test_execution_helpers.py
      -x --timeout=60 -q`: **76 passed, 1 skipped** — dispatch + env tests all pass;
      `test_eight_allowlist_keys_canonical_set` pin stays green.
    - Full default suite `pytest tests/ --timeout=300 -q`: **3057 passed, 8 skipped,
      589 deselected** — no regressions (identical count to Leg 1 baseline).
    - `ruff check` + `ruff format --check` on all changed paths: clean.
  - **Deviations**: None from the leg spec. The `noqa: F821` comment on
    `import winpty` suppresses ruff's unresolved-import flag without adding
    winpty to Linux deps (as the leg directed). The `I001` import-order fix
    was applied via `ruff --fix` (two files: `pty_unix.py`, `pty_windows.py`).
  - **Windows-side verification**: deferred to CI post-push per leg design (the
    implementing agent runs Linux/WSL2; authoritative Windows check is the
    `windows-2022` lane running `tests/test_pty_windows.py`). Budget 1-2 CI
    iterations on the socket-timeout read mechanism if needed.
- **B1 fix (2026-06-13) — `_read_until_idle_blocking` socket.timeout / EOF
  collision (blocking review finding):**
  - **Issue:** the `except socket.timeout` handler set `chunk = b""` and fell
    through to the shared `elif chunk == b"": return bytes(buffer)` branch,
    causing a timeout (the normal idle-window signal) to be treated as EOF.
    Result: every `send()` read and the startup banner drain would return after
    the first 0.1 s window even when more output was still in flight — the
    idle-stability contract was broken.
  - **Fix** (`the_one/platform/pty_windows.py`): made the `except socket.timeout`
    handler fully self-contained — idle-stable check, then timeout-budget check
    (with `TimeoutError` raise), then `continue`. Removed the `chunk = b""`
    fall-through. Renamed the data path's `elif chunk == b"":` to a plain
    `else:` (structurally unreachable via `socket.timeout` now, matches the
    Unix backend's shape). This mirrors `pty_unix.py`'s structurally separate
    `else` (select-timeout) vs `if chunk:` (data) branches exactly.
  - **Verification:** `ruff check` + `ruff format --check` clean; `pytest
    tests/test_pty_dispatch.py tests/test_execution_tools.py
    tests/test_execution_helpers.py -x --timeout=60 -q` → **76 passed,
    1 skipped** — identical to original Leg 2 POSIX baseline, no regressions.

### Leg 2 — CI result (windows-2022, PR #110, run 27477230582)

**2026-06-13 — the pywinpty backend is VERIFIED WORKING ON WINDOWS.**
`test_pty_windows.py` ran **7/7 passed** on the windows-2022 lane — start,
cmd.exe echo round-trip, two-send state persistence, close→not-alive,
idempotent close, last_activity, send-after-close RuntimeError. The
socket-timeout read mechanism (the design-review correction) and the
`proc.close(force=True)` teardown both work on real ConPTY. **First CI try —
no iteration needed** (the budgeted 1-2 iterations were saved by the two
review catches). Linux lanes all green.

- Windows suite: **22 failed / 3019 passed** (was 20/3014 at Leg 1). Delta is
  exactly **+7 passed** (test_pty_windows) and **+2 failed** = two NEW
  env-allowlist failures **introduced by DD5 as anticipated**:
  `test_execution_helpers.py::test_returns_only_allowlisted_keys` and
  `test_execution_tools.py::TestPythonExecTool::test_env_allowlist_invariant`.
  They assert the POSIX-only key set; Windows now legitimately carries
  `_WINDOWS_ENV_ALLOWLIST` keys. **Leg 4 owns them** (DD10 env-test triage) —
  tracked, not a surprise (Leg 2 flagged the DD5/env interaction up front).
- **Leg-4 triage list is now 22** (Leg-1 inventory of 20 + these 2 DD5 env
  tests). Backend functional parity is no longer in question — Leg 4 is
  test-side Windows-awareness + the 2 genuine fixes (timestamp collision,
  encoding) + the product-code unencoded-open audit.

### Leg 3 — windows-teardown-and-orphans

- **Status**: landed (2026-06-13)
- **Prior entry (design)** retained below:

- **Status at design**: ready (design complete 2026-06-13)
- **DD-OQ resolved by requirement:** DD4's "no orphan after parent-death"
  mandates a Win32 Job Object (`KILL_ON_JOB_CLOSE`) — `proc.close()` can't
  reap on a parent *crash* (never called), and the OS auto-closes the job
  handle on process death. So the Job Object isn't speculative; it's the only
  mechanism meeting the requirement.
- **Design review** (1 cycle, Developer/Sonnet — Win32 rigor; "approve with
  changes", 2 highs + mediums all incorporated):
  - [high] **Struct-field-type blind-port trap:** `c_ulong` is 8 bytes on Linux
    / 4 on Windows; `Affinity`/working-set are pointer-width (`SIZE_T`). An
    implementer sizing the struct on Linux would get a wrong-but-plausible
    answer → silent `SetInformationJobObject` corruption. Fixed by spelling out
    the full `_fields_` with `ctypes.wintypes` exact types in the leg.
  - [high] **HANDLE truncation:** must be `c_void_p`/`wintypes.HANDLE`, not
    `c_int` (64-bit truncation → `ERROR_INVALID_HANDLE`). Mandated argtypes/
    restype.
  - [med] `CloseHandle` must run even if `proc.close` raises a non-IOError →
    place after the try/except, null `_job` in `finally`.
  - [med] grandchild PID capture: mandate **temp-file self-write** (tasklist
    diff false-passes in shared CI).
  - [low] `ERROR_ACCESS_DENIED` on Win10+ means a real permission failure
    (raise), NOT "already in a job" (nested jobs work on windows-2022).
  - No 2nd cycle: fixes were prescriptive (canonical Win32 struct + standard
    ctypes); self-verified.
- Next: spawn Developer to implement (Phase 2b). Intricate ctypes written blind
  → budget 1-2 CI iterations (DD-OQ is the flight's explicit empirical question).
- **Implementation outcomes (2026-06-13)**:
  - **Files changed** (2 files):
    - `the_one/platform/pty_windows.py` — Win32 Job Object ctypes plumbing
      added at module scope: `_IO_COUNTERS`, `_JOBOBJECT_BASIC_LIMIT_INFORMATION`,
      `_JOBOBJECT_EXTENDED_LIMIT_INFORMATION` structs (verbatim from leg —
      exact field types: `DWORD=wintypes.DWORD`, `LARGE_INTEGER=c_int64`,
      `SIZE_T/ULONG_PTR=c_size_t`); `_setup_kernel32()` sets `argtypes`/`restype`
      on all six kernel32 calls with `HANDLE=wintypes.HANDLE` (c_void_p,
      pointer-width); `_create_job_and_assign(pid)` creates a `KILL_ON_JOB_CLOSE`
      job, opens the target process, calls `AssignProcessToJobObject`, closes
      `hproc`, returns the job handle; `start()` calls `_create_job_and_assign`
      immediately after `PtyProcess.spawn` (before the banner drain), stores
      result as `self._job`; `_close_blocking()` calls `CloseHandle(self._job)`
      after the existing `proc.close` try/except block, in its own `try/finally`
      that nulls `self._job` unconditionally; `WindowsPtySession.__init__`
      initializes `self._job = None`. Module docstring updated with Job Object
      lifecycle section. `ctypes.windll.kernel32` access is guarded by
      `type: ignore[attr-defined]` (not noqa — it's a type annotation concern,
      not an undefined name; ruff passes clean).
    - `tests/test_pty_windows.py` — Two new nt-gated tests added (Leg 3):
      `test_close_reaps_grandchild` (proves backgrounded grandchild is gone
      after `close()` via temp-file PID self-write + `OpenProcess`/
      `GetExitCodeProcess` polling — robust in shared CI per design);
      `test_parent_death_reaps_grandchild` (best-effort: child subprocess
      creates session + grandchild, test hard-kills the child, asserts grandchild
      gone — marked `@pytest.mark.xfail(strict=False)` with documented rationale:
      job handle propagation into subprocess context depends on CI runner's own
      job object placement; the operator's Windows host is the definitive check).
      Win32 constants (`_PROCESS_SYNCHRONIZE`, `_PROCESS_QUERY_LIMITED_INFORMATION`,
      `_STILL_ACTIVE`) defined at module scope to satisfy ruff N806.
      New stdlib imports: `subprocess`, `sys`, `textwrap`, `time`.
  - **Verification steps (POSIX-side) — all passed**:
    - `python -c "import the_one.platform.pty; print('import ok')"`: no error —
      `pty_windows` not imported on Linux; ctypes Job Object code never loads.
    - `ruff check the_one/platform/pty_windows.py tests/test_pty_windows.py`:
      **all checks passed**.
    - `ruff format --check the_one/platform/pty_windows.py tests/test_pty_windows.py`:
      **2 files already formatted** (reformatted before check, clean thereafter).
    - Full default suite `pytest tests/ --timeout=300 -q`: **3057 passed,
      10 skipped, 589 deselected** — identical pass count to Leg 2 baseline;
      the 2 new Windows-only tests appear in the skipped count (correct).
  - **Deviations**: None from the leg spec. The `ctypes.windll` access is
    annotated `type: ignore[attr-defined]` rather than `# noqa: F821` because
    ruff (on Linux, with `wintypes` importable from `ctypes`) sees the attribute
    access as a type error, not an undefined name — mypy/pyright concern, not a
    ruff F821. The noqa form the original `import winpty` used doesn't apply here.
  - **Windows-side verification**: deferred to CI post-push per leg design
    (implementing agent runs Linux/WSL2). The ctypes Job Object is the flight's
    DD-OQ empirical question — budget 1-2 CI iterations. The nested-job case
    (whether `AssignProcessToJobObject` encounters an existing job from
    pywinpty/ConPTY) will be answered by the CI run and captured in the flight log.

### Leg 3 — code review + FD hardening

- **Code review** (Reviewer/Sonnet, deep Win32 scrutiny): `[HANDOFF:confirmed]`.
  Struct layout exact (field order + types match the prescribed `_fields_`;
  `wintypes.DWORD`/`c_int64`/`c_size_t` correct), all six kernel32 calls have
  `wintypes.HANDLE` argtypes/restype (no truncation), constants right
  (KILL_ON_JOB_CLOSE=0x2000, class=9), close() ordering per spec (CloseHandle in
  its own try/finally after proc.close), start() assigns immediately after spawn,
  Linux import-safe (pty_windows never imported on Linux; verified via
  sys.modules). POSIX 3057 passed / 10 skipped.
- **FD-applied hardening** (reviewer's non-blocking obs, fixed pre-push because it
  affects the reap *assertion's* trustworthiness): the test-side
  `ctypes.windll.kernel32` calls (OpenProcess/GetExitCodeProcess in the
  grandchild-liveness check) lacked argtypes → 64-bit HANDLE truncation could
  make the liveness probe unreliable, i.e. the orphan-reap result untrustworthy.
  Added a `_typed_kernel32()` helper (proper argtypes/restype) and routed all 3
  sites through it. Lint clean; Linux import-safe re-verified.
- Next: commit + push → windows-2022 lane is the DD-OQ empirical answer
  (close-reap; nested-job behavior; parent-death xfail).

**2026-06-13 — Out-of-flight CI maintenance (operator request): Node 20 → Node 24 actions.**
GitHub force-migrates Node-20 actions on 2026-06-16; the deprecation warnings
surfaced on every CI run this flight. Bumped `actions/checkout@v4 → @v5` (first
node24 major; minimal jump) and `actions/setup-python@v5 → @v6` (v5 is node20,
v6 is node24) across `lint.yml` + `test.yml` (9 pins). Verified each target
declares `runs.using: node24` via the actions' `action.yml`. Committed
separately (clearly labeled), not folded into a leg — unrelated to PTY parity,
F1 "orphaned-fixes separate commit" precedent. Pushed onto flight/03 (rides the
existing CI/PR); the push supersedes the in-progress Leg-3 run — the replacement
run covers Leg 3 + the action bump together (one Windows run, not two).

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
