# Flight: Windows PTY Parity (ConPTY)

**Status**: ready
**Mission**: [Native Desktop Installers](../../mission.md)

> **Executes before Flight 2** (macOS Seatbelt) per the 2026-06-13 order swap —
> the operator has a native Windows host (under WSL2) giving this flight a
> *local* test apparatus, and Windows runners bill at 2× vs macOS 10×. See the
> mission's Flights note.

## Contributing to Criteria

- [ ] Interactive PTY-backed shell/session tools work at feature parity on **all
      three platforms**, including Windows, and remain governed by the shared
      sandbox boundary where a backend exists *(behavior-test-backed — the
      operator runs it on real Windows hardware this flight; DD8)*
- [ ] The app builds, runs, and is tested entirely without Docker; the existing
      test suite passes host-natively in CI *(extended to Windows: full default
      suite becomes a required `windows-2022` job; DD7)*

> **Enabling (not a headline criterion, but the load-bearing consequence):**
> this flight is what makes `the_one` **importable and runnable on Windows at
> all** — today the `platform/pty.py` import guard cascades through
> `agent/factory.py → tools/builtins.py → tools/sessions.py`, so neither the
> web app nor the CLI can even be imported on Windows. Flights 4 (native
> window) and 5 (packaging) for Windows structurally depend on this landing.

---

## Pre-Flight

### Objective

Add a `WindowsPtySession` (ConPTY via `pywinpty`) behind the Mission-14
`PtySession` ABC so interactive shell/session tools reach feature parity on
Windows, and — as the enabling prerequisite — make `the_one.platform.pty`
**import cleanly on Windows** so the app/CLI import cascade unblocks. The
backend spawns through the existing seam (passthrough on Windows — the
documented sandbox gap), uses a `select`/`fcntl`-free idle-window read loop,
and supervises the child via the ConPTY process handle. A required
`windows-2022` CI lane runs the full default suite (PTY functional tests now
included; containment tests stay POSIX-gated — DD9), and the operator runs a
Witnessed behavior test on real Windows hardware. No consumer changes — the
registry, reaper, lifespan, and four `shell_session_*` tools already program
against the clean `PtySession` ABC.

### Open Questions

- [x] ConPTY access mechanism → **resolved, DD1** (pywinpty, Windows-only dep)
- [x] Windows CI scope → **resolved, DD7** (full default suite, required)
- [x] Behavior-test backing → **resolved, DD8** (authored; operator-run)
- [ ] **Does closing the ConPTY reliably kill the child, or is a Win32 Job
      Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) required for guaranteed
      orphan reap?** → empirical, resolved at Leg 3 (verified on `windows-2022`
      CI **and** the operator's box — the F1 "verify the load-bearing premise"
      lesson; the operator's local Windows host is the ideal apparatus). Not
      locked at planning because it rests on ConPTY runtime behavior.

### Design Decisions

**DD1 — ConPTY via `pywinpty` as a Windows-only dependency.**
`pywinpty>=2.0; sys_platform == "win32"` in base `dependencies` (environment
marker — never installs on Linux/macOS dev boxes or their frozen artifacts;
installs into the Flight-5 Windows frozen app as an ordinary wheel).
- Rationale: pywinpty is the maintained, de-facto-standard ConPTY binding (the
  mission's named choice). Raw ConPTY via ctypes means hand-rolling
  `CreatePseudoConsole` + overlapped-IO pipe lifecycle + handle-inheritance — a
  large, error-prone native surface. Unlike the macOS srt-vs-direct call (where
  the dependency dragged Node onto the core path), pywinpty is a thin Python
  wheel with no runtime prerequisite, so the no-frameworks identity argument
  doesn't bite: it's a binding, not a framework.
- Trade-off: a native dependency whose wheel must exist for the target Python
  (3.11+, win_amd64 — verified available). Pinned with a floor, not exact, to
  match the project's dep convention. **Flight-5 note:** pywinpty 2.x vendors a
  native `.pyd` + bundled DLL and is Python-ABI-specific (cp311 ≠ cp312) — the
  freeze tool must collect the native binary and the frozen Python's ABI must
  match the wheel. Recorded so Flight 5 (packaging) isn't surprised; not work
  for this flight.

**DD2 — Split-module structure: a platform-neutral dispatcher imports on
every OS; each backend keeps its platform stdlib disjoint.** Rather than
guard/lazy-load POSIX stdlib inside one shared module (which invites a
half-guarded `NameError`-on-Windows footgun — the module references
`signal.SIGKILL`/`fcntl.fcntl`/`select.select` in *method bodies* at lines
337/355/503/587/618, not just the import lines, and `signal.SIGKILL` does not
exist on Windows), the module is split (architect review, 2026-06-13):
- **`platform/pty.py`** keeps the `PtySession` ABC + the `create_pty_session`
  dispatcher; it imports NO platform-specific stdlib at module scope, so it
  imports cleanly on every OS. The import-time `NotImplementedError` guard
  (`pty.py:82-83`) is deleted. Consumers keep importing
  `create_pty_session`/`PtySession` from `the_one.platform.pty` — **no
  call-site changes**.
- **`platform/pty_unix.py`** holds `UnixPtySession` with its module-level
  `fcntl`/`pty`/`select`/`signal` imports and the fork-safety
  "parent-loads/child-execs" convention **byte-identical** to today (a
  mechanical move, not a rewrite). Imported by the dispatcher only on POSIX.
- **`platform/pty_windows.py`** holds `WindowsPtySession` with its `pywinpty`
  import. Imported by the dispatcher only on `nt`.

`create_pty_session()` dispatches `from .pty_windows import WindowsPtySession`
on `os.name == "nt"`, else `from .pty_unix import UnixPtySession`. Each
backend's platform stdlib loads only when that backend is selected — no lazy
per-method imports, no shared guarded surface. The `PtySession` ABC boundary
is already clean (registry/reaper/lifespan/tools verified to touch only
`start/send/close/is_alive/last_activity` + the ABC type — recon).

**Back-compat for `UnixPtySession`-by-name importers (round-2 review):** two
sites import `UnixPtySession` *by name* from `the_one.platform.pty` —
`the_one/platform/__init__.py:44` (a public POSIX-guarded re-export →
`the_one.platform.UnixPtySession`) and `tests/test_pty_session.py:34`. The
move must preserve that name on POSIX: `pty.py` re-exports it under a
`if os.name == "posix": from .pty_unix import UnixPtySession` guard (keeps
`pty.py` platform-clean on Windows while preserving the POSIX import surface) —
zero churn at those two sites. The libc/fork-safety singleton (`_get_libc`/
`_libc`) and the fork-safety docstring travel *with* `UnixPtySession` into
`pty_unix.py` (the one piece a careless move could strand in `pty.py`, dead on
POSIX); the function-level `platform.sandbox` imports stay function-level, so
the existing `platform ↔ platform.sandbox` cycle-avoidance is preserved.

**`TestWindowsGuard` inverts (Leg 1):** `tests/test_pty_session.py:243-260`
currently asserts `import the_one.platform.pty` *raises* `NotImplementedError`
on Windows — the exact contract DD2 deletes. Leg 1 inverts it: importing
`the_one.platform.pty` on Windows must now *succeed*, and `create_pty_session()`
returns a `WindowsPtySession`. This test is a hard contradiction with the
guard deletion and must be changed, not left.

**DD3 — `select`/`fcntl`-free idle-window read loop, same readiness contract.**
The Unix backend reads via `select.select` on a non-blocking master fd in a
thread executor. The Windows backend uses pywinpty's non-blocking read in the
same `run_in_executor` pattern, preserving the **identical** readiness contract
(`start()` blocks until ~100ms idle OR a 2s cap; `send()` reads until idle OR
timeout — `_DEFAULT_IDLE_WINDOW`/`_DEFAULT_START_TIMEOUT`/`_READ_CHUNK`
constants shared). No prompt-regex matching. The idle-mark is shell-agnostic,
so cmd.exe's banner+prompt needs no special handling.

**DD4 — Process supervision via the ConPTY process handle; the bwrap teardown
branch is never taken on Windows.** `is_alive` polls the child's exit status
through pywinpty (no `os.waitpid`). `close()` terminates via the process handle
(no `os.kill`/signals). `self._wrapped` is structurally `False` on Windows
(passthrough backend → `spec.command` is the shell, never `"bwrap"`), so the
SIGKILL-fast bwrap branch is dead code on this platform by construction — the
Windows `close()` implements its own terminate-then-confirm path. Orphan-reap
guarantee is the open question (DD-OQ) resolved empirically at Leg 3.

**DD5 — Windows subprocess env needs platform-essential keys.** The current
8-key allowlist (`env.py`: PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ)
is POSIX-shaped — on Windows none of HOME/USER/LOGNAME exist (it's
USERPROFILE/USERNAME) and, critically, **cmd.exe misbehaves or fails without
`SystemRoot`** (and `PATHEXT` for command resolution; `TEMP`/`TMP` for tooling).
Leg 2 extends the allowlist with a Windows-only essential set
(`SystemRoot`, `PATHEXT`, `TEMP`, `TMP`, `USERPROFILE`, `USERNAME`,
`COMSPEC` — final set pinned against real cmd.exe behavior on CI), applied only
on `nt` so POSIX env stays byte-identical. This is a backend-functionality
prerequisite, not a nicety — the session won't work without it. **Consumer
audit (Leg 2):** `_build_subprocess_env`/`_ENV_ALLOWLIST` are re-exported via
`tools/execution.py` for back-compat and asserted by tests
(`test_execution_tools.py` exercises the `env`-command output and allowlist
shape) — the Windows branch changes that output on `nt`, so the env-assertion
tests and re-export consumers must be audited, not just `pty.py`'s call site.
POSIX output stays byte-identical (the branch only adds keys under `os.name ==
"nt"`).

**DD6 — Import-cascade unblock is in scope and verified.** Removing the guard
(DD2) makes `import the_one.interfaces.web.app` and the CLI entry succeed on
Windows for the first time. Leg 1's acceptance explicitly verifies the cascade
(`agent/factory → tools/builtins → tools/sessions → platform/pty`) imports on
the `windows-2022` runner, and that the default suite **collects** there (the
prerequisite for DD7).

**DD7 — Windows CI: full default suite on `windows-2022` (pinned), required.**
Operator decision (mirrors the macOS DD9 choice). Recon supports feasibility:
non-PTY Windows portability is largely already done (deps have win_amd64
wheels; every POSIX import is guarded; paths via `platformdirs`), and once
pty.py imports the cascade unblocks. Pinned image (`windows-2022`, not
`-latest`) avoids drift between Leg 1's green and Leg 4's required flip.
- **Concrete tar-pit risk (architect review):** the default suite runs
  un-gated POSIX *command strings* against real cmd.exe —
  `test_execution_tools.py` issues `true`, `env`, `seq`-loop / bash `for`
  syntax, `exit 7`, `cwd="/etc"`, `pwd`, `echo err >&2` (lines 91-193); these
  fail on cmd.exe and collection won't reveal them. **Leg 1 is therefore a
  GATE, not just a "collect" step**: it runs the collected suite on
  `windows-2022` and produces the *actual Windows failure inventory*, so Leg 4
  is scoped against real data. If that inventory's portability tail exceeds a
  leg's worth, the divert fires *before* committing to "required" (see
  Adaptation Criteria).
- Cost note: private repo, Windows runners bill at **2×** (vs macOS 10×) — a
  full suite (~Linux 327s baseline, likely slower on Windows) per push is
  acceptable; flagged for awareness, reversible by demoting to non-required.

**DD8 — Behavior test authored and operator-run on real Windows hardware.**
Unlike the macOS flight (no operator hardware → criterion deferred to Flight 8),
the operator has a native Windows host, so the mission's "PTY parity
(behavior-test-backed)" criterion is **satisfied this flight**. A Witnessed
behavior-test spec (`tests/behavior/windows-pty-parity.md` per ARTIFACTS.md) —
start a `shell_session`, run a command, observe output, send a second command
in the same session (state persists), close — apparatus: the operator's Windows
shell/CLI driving the real `shell_session_*` tools. **Authored this flight;
run by the operator** (the implementing agents run on Linux/CI and cannot
exercise the Windows backend interactively — see Prerequisites).

**DD9 — Containment tests are already `@requires_bwrap`-gated and auto-skip on
Windows; this flight only ensures their module *imports*.** Windows ships
sandbox-passthrough (the mission's documented gap), so `test_pty_sandbox.py`
containment assertions have nothing to enforce there. They are **not**
`skipif(os.name != "posix")` (corrected at architect review, 2026-06-13) —
every containment test carries `@pytest.mark.requires_bwrap`
(`test_pty_sandbox.py:55/147/281`), which is both in the default-suite deselect
set (`pyproject.toml:77`) **and** skips when `bwrap` is absent (always true on
Windows). So they deselect cleanly with no new gating. The ONLY Leg-1
requirement is that the module *imports* on Windows once the `pty.py` guard is
gone — it does `from the_one.platform.pty import create_pty_session` (line 46)
and `import signal` (line 32) at top level; both import fine on Windows under
the split-module structure (DD2). The Windows suite proves the PTY *functional*
contract (spawn, idle-readiness, send/receive, session-state persistence, clean
teardown, no orphans), NOT containment. SECURITY-MODEL.md records Windows
interactive tools run unsandboxed (already the documented stance).

**DD10 — Leg-4 Windows test triage: parametrize wrapper tests, POSIX-gate
shell-semantics tests.** The un-gated POSIX command-string tests
(`test_execution_tools.py` et al.) split two ways, triaged against Leg 1's
failure inventory: (a) tests targeting the *execution wrapper* (exit-code
capture, stderr split, cwd, timeout) get **parametrized** with a
platform-equivalent command (`true`→`cmd /c (exit 0)`, `env`→`set`, `pwd`→`cd`,
`exit 7`→`exit 7`); (b) tests targeting *POSIX shell semantics specifically*
(`$(seq …)`, `for … do … done`, `/etc` paths) get **POSIX-gated**
(`skipif(os.name != "posix")`) — they assert Unix behavior that has no cmd.exe
analogue worth contorting. The split  is data-driven (Leg 1's red list), not
guessed; Leg 4's size is bounded by it (and by the DD7 divert if the tail is
large). **Third residue (round-2 review):** some tests refuse on the host side
*before any subprocess spawns* (`test_execution_tools.py` denylist/cwd-allowlist/
timeout-clip tests, :124/:131/:145/:170) — already platform-neutral, needing
neither bucket; a couple assert against POSIX path literals (`"/etc"`, :136)
that Leg 1's inventory may flag for a Windows-neutral path. Leg 4 won't be
surprised to find "already-portable, no action" tests.

### Prerequisites

- [x] Flight 1 merged to `main` (host-native suite + CI baseline green)
- [x] M14 `PtySession` ABC boundary verified clean (registry/reaper/lifespan/
      tools touch only the ABC — recon 2026-06-13)
- [x] `select_shell()` already returns `("cmd.exe", ["/c"])` on Windows
      (`shell.py:59-60`) — no shell-selection work needed
- [x] Sandbox factory already returns passthrough gracefully on Windows
      (`factory.py:170`); `PassthroughSandbox.prepare_spawn` makes no Unix
      assumptions (recon-confirmed)
- [x] `pywinpty` win_amd64 wheels exist for Python 3.11+ (verified)
- [ ] **Implementing agents run on Linux/CI — they cannot exercise the Windows
      backend interactively.** Unit/functional iteration is `windows-2022`
      CI-bound (tight loops; the F1 "first CI run is part of the flight" lesson
      applies *more* here). The operator's Windows host is the apparatus for the
      DD8 behavior test and the DD-OQ orphan-reap check — coordinate a hands-on
      window before the required-flip (Leg 4) and behavior test (Leg 5).
- [ ] Branch-protection / required-checks updated for the new `windows-2022`
      job when it flips to required (operator action at Leg 4, repo admin)

### Pre-Flight Checklist

- [x] All open questions resolved or assigned to an empirical leg (DD-OQ → Leg 3)
- [x] Design decisions documented
- [x] Prerequisites verified (two operator actions pending, non-blocking to start)
- [x] Validation approach defined (DD7 CI + DD8 behavior test; per-leg acceptance)
- [x] Legs defined

---

## In-Flight

### Technical Approach

`WindowsPtySession` lands in its own `platform/pty_windows.py` (DD2 split-module
design), satisfying the same `PtySession` ABC. `platform/pty.py` is reduced to
the neutral ABC + `create_pty_session` dispatcher (no module-scope platform
stdlib, so it imports on every OS; the import-time guard removed);
`UnixPtySession` moves to `platform/pty_unix.py` byte-identically.
`create_pty_session` dispatches by `os.name`. The Windows backend
spawns the shell through the seam's passthrough `SpawnSpec`, drives a
pywinpty pseudoconsole, and reuses the shared idle-window readiness constants
via a poll-based (not `select`-based) read loop in `run_in_executor`. Env is
assembled with the Windows-essential allowlist (DD5). Teardown uses the process
handle; the orphan-reap mechanism (ConPTY-close vs. Job Object) is settled
empirically. The clean ABC means the L5b registry, reaper, lifespan, and L6
tools are untouched. Most of the backend is only exercisable on the
`windows-2022` lane and the operator's host — so CI is load-bearing and the
implementer leans on it (cannot reproduce locally on WSL2/Linux).

### Checkpoints

- [ ] `platform/pty.py` + the app/CLI import cascade import cleanly on
      `windows-2022`; default suite **collects** there (Leg 1)
- [ ] `WindowsPtySession` start/send/close round-trips a real cmd.exe session on
      `windows-2022` (Leg 2)
- [ ] No orphaned child after `close()` / parent-death on Windows — mechanism
      chosen and verified (Leg 3)
- [ ] Full default suite **green** on `windows-2022`; PTY functional tests run
      on Windows, containment tests POSIX-gated; job flipped to required (Leg 4)
- [ ] No Linux/macOS regression: `test`/`browser`/`bwrap` jobs stay green every
      leg; POSIX env byte-identical (DD5)
- [ ] Operator runs the Windows PTY behavior test → pass (Leg 5)

### Adaptation Criteria

**Divert if**:
- Making the full suite green on Windows surfaces portability work exceeding a
  leg's worth (a long tail beyond PTY) → demote the suite job to non-required,
  re-scope this flight to PTY-functional + the portable subset, split the
  remainder into a Windows-portability flight (reverses DD7 — operator sign-off)
- pywinpty cannot deliver the idle-readiness/teardown contract reliably (e.g.
  non-blocking read semantics fight the idle-mark) → stop, evaluate raw ConPTY
  or contract adjustment with operator input before further legs
- Orphan reap proves to need a Job Object AND that interacts badly with the
  registry's reaper model → re-design supervision with operator input (Leg 3)

**Acceptable variations**:
- Exact Windows env-essential key set (DD5 — iterated against real cmd.exe on CI)
- Orphan-reap mechanism (ConPTY-close vs Job Object — DD-OQ, empirical)
- PTY functional-test layout (parametrize cross-platform vs. parallel
  Windows-gated file) — leg design picks
- Whether the Windows job shares a workflow matrix with existing jobs or stays
  a separate named job
- Default shell stays `cmd.exe` (PowerShell is a documented future option, not
  this flight)

### Legs

> Tentative breakdown — refined per-leg at design time (`/leg`).

1. **windows-import-unblock** — Split-module restructure (DD2): move
   `UnixPtySession` to `platform/pty_unix.py` (byte-identical, mechanical),
   reduce `platform/pty.py` to the ABC + `create_pty_session` dispatcher with
   no module-scope platform stdlib, delete the import-time guard; confirm the
   app/CLI import cascade succeeds on Windows. Add the
   `windows-2022` full-default-suite CI job (**non-required while iterating**;
   pinned image). **Gate, not just collect**: run the collected suite and
   capture the *actual Windows failure inventory* (the red list Leg 4 will be
   scoped against — collection alone hides the cmd.exe command-string failures
   in `test_execution_tools.py`). If the non-PTY portability tail exceeds a
   leg's worth, fire the DD7 divert before proceeding.
   **Migrated F1 ride-alongs on this CI-touching surface**: re-mark the ~12
   `skipif(which("bwrap"))` integration tests as `@pytest.mark.requires_bwrap`
   (`test_mcp_sandbox_integration.py:88`, `test_mcp_stdio_sandbox.py:447`) — so
   they're honest deselects, not invisible false-skips on the new Windows
   runner; and add the `mcp/__init__` eager-load-cycle guard comments at the
   lazy `SandboxError` import sites (`_tool.py:157`, `_tool_provider.py:306`).
2. **windows-pty-backend** — `WindowsPtySession` via pywinpty (DD1 dep with the
   `sys_platform` marker; DD3 idle-window read loop; DD4 handle-based
   supervision); `create_pty_session` Windows dispatch (DD2); the DD5 Windows
   env-essential allowlist (backend won't function without `SystemRoot` et al.).
   Acceptance: a real cmd.exe session round-trips on `windows-2022`.
3. **windows-teardown-and-orphans** — Resolve DD-OQ: verify whether
   ConPTY-close reliably reaps the child or a Job Object
   (`KILL_ON_JOB_CLOSE`) is needed; implement the chosen mechanism; confirm no
   orphan after `close()` and after parent-death. **Empirically verified on
   `windows-2022` CI and the operator's host** (the F1 design-time-verification
   lesson). Confirm `_wrapped` is never True on Windows (dead bwrap branch).
4. **windows-suite-green** — Make the full default suite **green** on
   `windows-2022`: refactor PTY functional tests to run on Windows (containment
   tests already `@requires_bwrap`-deselected — DD9); triage Leg 1's failure
   inventory per DD10 (parametrize wrapper tests, POSIX-gate shell-semantics
   tests); flip the Windows job to **required** (operator updates branch
   protection). No-regression audit on Linux/macOS.
5. **behavior-test-and-docs** — Author the Windows PTY Witnessed behavior-test
   spec (DD8); **operator runs it on real Windows hardware** → evidence logged;
   docs: SECURITY-MODEL.md (Windows interactive tools unsandboxed — DD9),
   `agents.md`/CLAUDE.md Windows PTY notes (pywinpty, ConPTY readiness, the
   never-taken bwrap branch), mission Known Issues review; verify-integration
   (all lanes green, cascade re-verified, no regression).

### Verification

- **Functional PTY parity on Windows** — `windows-2022` CI (Leg 4): the PTY
  functional contract (spawn, idle-readiness, send/receive, session-state
  persistence across sends, clean teardown, no orphans) runs and passes on
  Windows; full default suite green and required.
- **Behavior test** — `tests/behavior/windows-pty-parity.md` (DD8), authored
  this flight, **run by the operator on real Windows hardware**: start a
  `shell_session`, run a command, observe output, send a second command (state
  persists), close cleanly. This is the mission-criterion's behavior-test
  backing — real, this flight, not deferred.
- **No-regression** — existing `test`/`browser`/`bwrap` jobs required and green
  on every leg; POSIX subprocess env byte-identical (DD5 applies only on `nt`).
- **Orphan-reap** — empirically verified on CI and the operator's host (Leg 3).
- **Containment** — explicitly out of scope on Windows (DD9); POSIX containment
  tests unchanged.
