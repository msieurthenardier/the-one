# Flight Log: macOS app

**Flight**: [macOS app](flight.md)

## Summary
Planning.

---

## Planning Notes

### Flight Director Notes
- **Branch:** `flight/03-macos-app`, off `origin/main` at `e21d219` (after #311), in the Mission 32 worktree `/home/cprch/projects/the-one-worktrees/m32-installers`. Mission 31's checkout (`/home/cprch/projects/the-one`) is untouched; its Flight 4 HAT is in progress.
- **Inputs carried in:**
  - **Flight 2 debrief recommendations:**
    - rec 1, the `shell.py` split → DD1, leg 1;
    - rec 2, premise probes first → DD9, legs 2-3;
    - rec 3, the notice-length rule → DD2 (no macOS notice; squawk 0254 stays Linux);
    - rec 5, shared packaging steps → DD8 (the Python layer shared now; shell and workflow consolidation is Flight 4's).
  - **Flight 1 debrief rec 5:** budget macOS jobs, rehearse every macOS-only line, and treat the blank first paint as a defect owed a fix → DD10, DD11.
  - **Squawk 0253** (the Ubuntu AppImage's slow first paint) → DD11.
- **Operator answers (2026-10-24):**
  - Dock only, no menu-bar icon;
  - the `shell.py` split is leg 1 of this flight;
  - up to 4 hosted macOS dispatches;
  - unify the app id on `ai.gleepglorp.GleepGlorpAI`.

  The operator approved the working shape ("looks good, continue").
- **Calls the Flight Director made without asking (standing autonomy mode, logged for alignment):**
  - `NSTerminateLater` plus a drain worker for Quit (DD3);
  - a runtime subclass of pywebview's app delegate, with a source canary test (DD4);
  - a `PATH` walk and the `xcode-select -p` check for the Command Line Tools stub; the walk also applies on Windows (DD6);
  - the login-shell `PATH` for a frozen darwin app (DD7);
  - Apple's two version strings derived from PEP 440 (DD8);
  - no shared shell library this flight (DD8);
  - a dual-gated desktop test seam as the fallback apparatus (DD9);
  - the `.dmg` uploaded as a 7-day artifact (DD10);
  - measure the first paint before fixing it (DD11);
  - the CLI documented by path (DD12);
  - the contributor check as a behavior test with a human Executor (DD14).
- **Design review cycle 1 (Architect, Opus): approve with changes.** It spot-checked 18 Citation Audit rows and found 2 wrong (the lock count is 7, not 8; the `windowWillClose_` row lacked its missing-event fact). The Flight Director re-checked the highs against pywebview 5.4's `cocoa.py`. The three high findings:
  1. The delegate and `NSTerminateLater` premises would first meet the runner at dispatch 2. A minimal probe `.app` now joins leg 3's dispatch (DD4, DD9).
  2. Cmd-Q has a second path: `WebKitHost.keyDown_` → `app.stop_`, which bypasses `terminate:` and today saves no geometry. DD3 now has path T and path S, and both save geometry and drain.
  3. `destroy()` → `windowWillClose_` → `app.stop_` posts no event, so the run loop may not return. On darwin every app-started quit now goes through `NSApp.terminate_` (one drain path), and P9 probes the hazard.

  The medium and low findings were folded in:
  - the exit details (log flush, a crash-report check, an `os._exit` variation, `server`/`thread` on `SessionState`, quit while booting);
  - DD7's order (login shell first) and its subprocess traps (a new session plus `killpg`, output to a file, `printenv`, the `pwd` fallback, synchronous priming at command start, not lazily in an async path);
  - the split guard (aliases, assignments, "defined in", module-qualified calls, the singleton reset in place);
  - `render.load()`'s key collision, and a three-integer `CFBundleVersion`;
  - App Transport Security on disk, and as a first-paint candidate;
  - `focus_window`'s AppKit calls on the main thread;
  - App Nap;
  - P5 emulating Finder;
  - bounded TCC calls, and `open --env` for the seam flags;
  - P8 for the inherited environment;
  - leg 5 owns every `doctor` change;
  - leg-number fixes;
  - the per-leg `gh` re-verify;
  - the darwin `desktop shell` gate via `find_spec`, never importing `cocoa.py`;
  - the canary's extra facts;
  - `install` once, on the main thread, with a unique class name;
  - the `min_os` check against `LC_BUILD_VERSION`.
- **Design review cycle 2 (Architect, Opus): approve with changes.** 9 Citation Audit rows were re-checked, all 7 cycle-1 rows included, and all held.
  - **The high finding:** a darwin boot abort that itself called `terminate_` would have re-entered a pending terminate, and nothing signalled that the boot had stopped. Now:
    - `quit_desktop` calls `terminate_` even while booting;
    - `_boot` never terminates (except once on an unhandled error with no terminate pending), and sets a `boot_stopped` Event on every exit;
    - one worker per pending terminate;
    - path T never closes a pywebview window;
    - the budget is 10 s (boot) plus 60 s (join), within the takeover's 75 s.
  - **The medium findings were folded in:**
    - path S calls `begin_quit` first, hides, then saves geometry, which covers the splash and a still-booting `_boot`;
    - the seam drops `terminate` (the quit route already terminates) and gains `geometry`, and it moves to leg 4;
    - the behavior test uses three builds and adds a Dock Quit step;
    - P4 and `lifecycle.sh` check that the app is really frontmost.
  - **Lows and suggestions taken:**
    - stale text (P1-P9, the DD9 heading, the unit-count wording, "finalized", DD14 referencing the test's table);
    - DD1 placements and the `mock.patch`/`patch.object` guard forms;
    - DD7 primed after the `is_ours` return for `app`, and an unprimed process never computes it lazily;
    - `begin_quit` returns the geometry save outside the lock;
    - `render.load()` also rejects collisions with top-level keys, `metainfo_id` is removed in favour of `app_id`, and `.postN` is refused;
    - Flight 4 builds fresh `.dmg`s;
    - pystray is dropped from the macOS spec;
    - squawk 0253's VM check is owned by leg 4;
    - the canary pins the menu's `q` → `terminate:` binding (path S is defensive) and `abortModal`;
    - P9 is informational.
  - **No third cycle:** the 2-cycle maximum was reached, and the remaining items were concrete fixes, not disagreements.
- **The operator approved the flight (2026-10-25):** "approved, commit it and run agentic workflow". Status `ready`.

### Execution — Flight Director Notes
- **2026-10-25, `agentic-workflow` started.**
  - Phase file `.flightops/agent-crews/leg-execution.md` loaded (Developer: Sonnet; Reviewer: Haiku, or Sonnet for security-sensitive diffs).
  - Flight status `ready` → `in-flight`.
  - The standing autonomy mode applies.
- **Leg 1 (`shell-split`) risk tier: HIGH.** It changes a shared interface with many consumers (the routes, the CLI, the back-compat shim the CI packaged smoke imports, about 10 test files), and it restructures lifecycle state.
  - **Design review cycle 1 (Sonnet): approve with changes.** Folded in:
    - the guard's alias forms (any scope, multi-name `from` imports, `sys.modules[...]`, `importlib`, chained aliases, fixtures, `raising=False`), and "defined", not "bound by import";
    - the module-level imports that tests patch through `shell` (`__version__`, `desktop_host`) are re-pointed to the module that uses them;
    - `importlib.reload` no longer resets state, so there is one autouse `state.reset()` fixture in `conftest.py`;
    - `_clear_booting` and the no-tray notice constants are placed;
    - `request_quit()` returns a tagged result;
    - the logger name is kept;
    - every known re-point site is listed;
    - the inert slots `server`/`thread`/`boot_stopped` are added for leg 4;
    - the takeover build is `dev30` over Flight 2's `~dev20` `.deb` (present);
    - the leg runs as **phases A and B**.
  - **No second cycle:** every change adopts the reviewer's own recommendation. Status `ready`.
- **Leg 2 (`macos-probe-prepare`) risk tier: HIGH.** It spends scarce hosted minutes, its output reaches `main` (the stub), and it is first-run harness code (Flight 1's lesson). Its design review is running. It runs beside leg 1, on disjoint files (`packaging/macos/`, `.github/workflows/` against `the_one/`, `tests/`).
  - **Design review cycle 1 (Sonnet): approve with changes.** Folded in:
    - each quit scenario starts from a fresh launch, behind an "is it up" gate, and the probe logs its own pid;
    - Apple events and `open -a` address apps by path, never by id;
    - P6 runs last, with a dismiss attempt;
    - `M32_SKIP_CHECKS` keeps P1 a true cold first launch, plus an `rm -rf` of the data dir;
    - a quiescence check (pids and port 8484) around every premise;
    - the `on:` inputs are frozen now (`version`, `mode` = `full`/`lifecycle`/`probe`), and a new input needs another stub PR;
    - a `--selftest` run of the frozen probe before the premises, because Linux Analysis cannot see pyobjc;
    - the `NSTerminateLater` method declared as leg 4 will declare it (`typedSelector`), with its signatures logged;
    - a worst-case bound table, an outer bound, a 20 min step, and `TERM`/`INT` traps;
    - three `ps` forms for P8;
    - pid discovery by path is allowed, while stopping is by recorded pid only;
    - `lsappinfo front` before each keystroke;
    - P1's probe-window control (DD11);
    - the premise order;
    - the stub copy kept outside `.github/workflows/`.
  - **Deviation from DD9, recorded:** P6 no longer runs `doctor` from a translocated path (translocation happens only through LaunchServices). It records the launched process's path; leg 7 or the contributor check covers `doctor`.
  - **No second cycle:** every change adopts the reviewer's own recommendation. Status `ready`.
- **Merge done early (`16484eb`).** Leg 2's Developer runs no unit tests and `main` touches none of its files, so the merge came right after leg 1 phase A, before phase B. Leg 1's uncommitted `agents.md` paragraph was stashed around the merge and restored with no conflict. Phase B re-runs the unit tier on the merged tree.
- **Leg 1 phase A accepted.** The Developer's two non-mechanical choices stand:
  - `shell.py` imports `state` directly; that is safe because `state` is never rebound;
  - `self._window` is set just after the lock is released; the quit paths read `state.desktop_window`.
- **Leg 2 landed** (Developer report):
  - rehearsed by execution in all three scenarios;
  - the worst case is about 1100 s, under the 20 min step;
  - `actionlint`, `shellcheck`, `ruff` and bash 3.2.57 `-n` are all clean.

  It has no `classAddMethods` fallback, against the leg's guidance; that was sent to review.
  - **Early review checkpoint (leg 2 only) before the dispatch**, as in Flights 1 and 2: hosted legs build from the pushed branch.
  - **Reviewer tier: Sonnet.** A workflow reaching `main` is a CI-permissions surface, and a single scarce dispatch rides on first-run harness code.
  - **Review: no blocking issue, one medium.** The `classAddMethods` fallback the leg asked for was missing, so a rejected subclass would have lost the whole dispatch. Two minors: destroy mode's lingering worker, and skipping the `.dmg` in probe mode. A fix Developer applied all three. The fallback order is subclass, then `classAddMethods`, then the stock delegate, logged as `route:` and shown in the P2/P3/P4 rows. No re-review: the fixes are the Reviewer's own items, spot-checked by the Flight Director.
  - Leg 2 status `completed`. It is committed alone (with the flight artifacts), and leg 1's uncommitted code stays out of the commit.
  - **Operator go (2026-10-25), "Yes, all three":** push, the `.github/`-only stub PR merged after lint, and the probe dispatch.
- **Mission 31 Flight 4 merged to `main` (#309, `b1e47ae`, 2026-10-25).** Mission 31 is still `active` (Flight 5 remains), so its constraints stand: no release, its checkout untouched, and shared files kept additive. 188 files changed. The overlap with this flight is `CLAUDE.md` and `the_one/agents.md` only; none of leg 1's or leg 2's working files are touched by it.
  - **Call:** merge `origin/main` into `flight/03-macos-app` at the next checkpoint (after leg 1 phase A and leg 2 land, before the review), not under two running Developers.
  - After the merge, leg 1's guard and `make test-unit` are re-run on the merged tree (main adds tests), and leg 1 phase B builds from it.
  - **Commit plan:** after leg 2 is reviewed, the Flight Director commits leg 2's files **plus the flight artifacts** (`flight.md`, `flight-log.md`, `legs/`) without leg 1's uncommitted code, then opens the stub PR and pushes. Leg 3 then dispatches.

---

## Leg Progress

### shell-split

**Phase A checkpoint** (AC1-AC4; Phase B, AC5-AC7, not started).

- **Moved.** `takeover.py` (new): `_TAKEOVER_*`, `_now`, `_sleep`, `_parse_version`, `_is_older`, `_auth_headers`, `_running_version`, `_request_quit`, `_pid_alive`, `_wait_for_exit`, `_activation_token`, `_post_focus`, `_takeover`, `_select_port` (body diff against `e21d219`: identical, bar a trailing blank line). `window_control.py` (new): `_is_gtk_backend`, `_on_wayland`, `_mark_visible`, `_show_window`, `_gtk_read`, `window_visible`, `_window_mapped`, `_mode`, `window_state`, `quit_desktop`, `_gtk_activate`, `focus_window`, `set_window_theme`, `_no_tray_hide`, the no-tray notice constants. `session_state.py` (new): `SessionState` plus the instance `state`. `shell.py` keeps `DesktopSession`, the splash, `_wait_until_serving`, `_graceful_shutdown`, `_webview_available`, `_NoTrayError`, the no-webview bodies, the tray notice constants, `run_desktop`. Both new modules use the logger name `the_one.interfaces.desktop.shell`. Callers: `interfaces/app.py` takes `_select_port` from `takeover`; the four `web/app.py` routes import from `window_control`; `main._quit_command` imports `_wait_for_exit` from `takeover`. `from the_one.interfaces.app import _select_port, _webview_available, _wait_until_serving, _graceful_shutdown, run` works and does not import `webview`. `grep "desktop.shell import" the_one/` lists only names `shell.py` defines.
- **Non-mechanical edits (reasons).** (1) `quit_desktop` now calls `state.request_quit()` and maps the tag; the tagged result replaces the local variable `state` and the in-lock returns, same return values (`"already"` maps to `"window"`). (2) `_clear_booting` became `SessionState.clear_booting` (lives on the state). (3) `run()`: the nine `global`s and the reset block became `state.reset(); state.session = self`; the three `with _window_lock` sites became `begin_boot()`, `claim_browser_server(server)` (returns False when a quit was recorded, replacing the in-lock `return`), `release_browser_server()`; `_abort_if_quit`'s locked read became `quit_was_requested()`; step 6 is `quit_now = state.publish_window(main_win)`. (4) Step 6 sets `self._window = main_win` just after the lock is released instead of inside it (a plain attribute store on the session; `_on_closing` reads it only as a fallback). (5) `state.server, state.thread = server, thread` is set right after `thread.start()` (inert slots for leg 4). (6) `shell.py` reaches `state` through `from ...session_state import state` (an alias of the module-level instance, never rebound) rather than `session_state.state`, to keep the long `run()` body readable; moved functions are reached through their module (`takeover.`, `window_control.`). (7) `_mode`/`window_state` read `state.*`; `focus_window` still reads `state.desktop_window` at each use as before. No log message, return value or route answer changed.
- **Test re-points.** `test_desktop_shell.py` (`_select_port` to `takeover`, flags to `state`, `shell_state` fixture now `state.reset()`, `test_close_path_functions_have_no_imports` now parses both `shell.py` and `window_control.py`), `test_desktop_tray.py` (flags/functions re-pointed, `shell_module` docstring fixed), `test_desktop_takeover.py` (seams on `takeover`; the restart test patches `takeover` for the seams and `shell` for `uvicorn`/`threading`/`run_desktop`), `test_cli_quit.py`, `test_window_routes.py`, `test_window_focus.py` (reloads of `shell` dropped; `focus_window` tests set `state.desktop_window`), `test_window_state.py`, `test_api_window_chrome.py`, `conftest.py` (`stub_desktop_host` now `monkeypatch.setattr(state, "tray_mode", None)` without `raising=False`, plus the autouse `_reset_desktop_session_state` fixture calling `state.reset()` around each test). One stale line removed: `test_desktop_tray.py::test_on_closing_modes` had `monkeypatch.setattr(shell_module, "_close_to_tray_notice", None, raising=False)`; that name has never existed in `shell.py` (git history: no definition), so it patched nothing (a silent no-op of exactly the kind the guard exists to catch); the test itself is unchanged and passes. No test deleted or skipped.
- **The guard** (`tests/test_desktop_split_guard.py`, 32 tests, AST-based, aliases at any scope incl. `import ... as`, `from ... import shell [as]`, multi-name from-import, `sys.modules[...]`, `importlib.import_module`, `A = B`, `importlib.reload`, and fixtures returning an alias in the same file or `conftest.py`; patch forms: `monkeypatch.setattr`/`delattr` with a dotted string or `(alias, "name")` incl. `raising=False`, `patch("...shell.X")`, `mock.patch`, `patch.object`, `alias.X = ...`). Allowed names are read from `shell.py`'s own top-level `def`/`class`/assignment targets, so an imported name (`__version__`, `desktop_host`, `httpx`) fails. Unit tests on synthetic sources cover each alias form (module and function scope), each patch form, an imported-not-defined name, an allowed name, fixtures, and a non-shell `shell` fixture that must not be flagged. On the real tree it first listed 9 files / 122 sites to re-point and passes on the final tree. Demonstrated failure on a scratch copy (not committed): with `tests/test_cli_quit.py` pointed back at `import the_one.interfaces.desktop.shell as takeover`, the guard reported `[(153, '_wait_for_exit'), (164, ...), (174, ...), (210, ...)]`. A second check, `test_shell_defines_none_of_the_moved_names`, pins that `shell.py` defines no moved name. Limits: it guards patches and assignments through `shell`, not reads (a read of a moved name through `shell` fails at run time with `AttributeError`) and not `from ...shell import <moved>` (also fails at run time).
- **`SessionState` tests** (`tests/test_desktop_session_state.py`, 14 tests): defaults, in-place `reset()` (same lock and event objects, same key set), the module instance is never rebound, `begin_boot`/`clear_booting`/`quit_was_requested`, `publish_window` return contract, `claim_browser_server` (quit wins; booting cleared either way), `release_browser_server`, and `request_quit` for each of its five tags (no `_on_quit` under the lock; `should_exit` is set under the lock as before).
- **Counts.** Unit tier collected before (any file changed, `e21d219` tree + leg files only): **7115** (`7115/9627 collected, 2512 deselected`). After: **7161** (`7161/9673`). Delta **+46** = 32 guard + 14 `SessionState` tests; every pre-existing test is still collected (the only removed code is the one stale patch line above).
- **Gates.** `make test-unit`: `== 7105 passed, 12 skipped, 2556 deselected, 56 warnings in 330.09s ==` (the expected 12 skips). `ruff check the_one/ tests/ scripts/ evals/`: All checks passed. `ruff format --check`: 681 files already formatted. `the_one/agents.md` gained one additive "Desktop shell module map" paragraph; `CLAUDE.md` names no moved symbol (its `_select_port`/`_graceful_shutdown` mentions are generic and still true through `interfaces/app.py`), so it is unchanged.

---

## Decisions

---

## Deviations

---

### macos-probe-prepare

**Landed** (AC1-AC6). No push, PR, dispatch or commit. Evidence: `~/the-one-m32-evidence/f3/leg2/` (rehearsal SUMMARYs, shim argv logs, lint output, scripts); scratch: `~/the-one-m32-build/f3/`.

- **Files.** New: `.github/workflows/macos-packages.yml`; `packaging/macos/probe/{delegate_probe.py,probe.spec,probe.sh,README.md,macos-packages.stub.yml}`. Deleted (working tree, not staged): `.github/workflows/packaging-probe-macos.yml`. Edited: `packaging/macos/build.sh` (`M32_SKIP_CHECKS=1` exits after the dmg, before `checks.sh`; comment name fix), `packaging/macos/README.md` ("Probe mode" pointer).
- **Frozen `on:` inputs** (byte-identical in branch copy and stub, checked by script): `workflow_dispatch` and `workflow_call`, each with `version` (string, default empty) and `mode` (`choice` full|lifecycle|probe under dispatch, `string` under call; default `full`). No push/pull_request/schedule; every step has `timeout-minutes` (job 50); no `secrets.`; `actionlint` 1.7.7 clean on both; concurrency `macos-packages`, `contents: read`. `lifecycle` runs the same steps as `full` for now.
- **Probe design.** `probe.sh` runs each premise as a child (`probe.sh --run Pn`) under its own `tl` cap, so the worst case is a sum of caps, not a hand count. Order P7, OTOOL, P8, P1 (+control), P4, P2, P3, P9, P5, P6. Pid registry + EXIT/TERM/INT/ALRM traps; quiescence (tracked pids stopped by pid, port 8484 listener check) before and after each premise.
- **Bound table** (caps, s): P7 20, OTOOL 70, P8 110, P1 220, P4 100, P2 100, P3 140, P9 50, P5 80, P6 100 = **990**. Worst case with every cap firing plus at most 11 stop waits of 10 s: about 1100 s (18.3 min), under the step's 20 min; outer `tl` 1170 s. Typical estimate about 455 s (7.6 min); real runs here took 40 s scaled, 214 s with the osascript bound firing.
- **Rehearsal by execution** (Linux, fake `.app` trees, PATH shims for open/osascript/screencapture/lsappinfo/spctl/syspolicy_check/xattr/ditto/codesign/otool/file/xcode-select/log/sw_vers/plutil/ps; fake product HTTP server on port 18484, never 8484/8485; `M32_SCALE=0.05` shrinks only series offsets and settles, never a bound). Each run leaves no process, no listener, no container. SUMMARY excerpts:
  - all shims succeed (40 s): `P1: cold: up ... first /api/live=200 at +1s ...`; `P2: probe: osascript rc=0; exited 1.0s ...; log: terminate=1 reply=1 willTerminate=1; signatures: ...b'Q@:@' ... b'c@:@'`; `P3: probe Cmd-W ... path=S`, `probe Cmd-Q ... path=T`; `P4: product: open -n ... second's own output: second instance: focus ...`; `P5 ... pids now [same] (same pid = the old process answered)`; `P6 ... process after open: 1127652(translocated); path: /private/var/folders/.../AppTranslocation/...`; `OTOOL: 9 Mach-O files ... max minos=12.3.1`.
  - osascript TCC (`-1743`; quit event errors at once, System Events hangs) (214 s): `P2: product: osascript rc=1 err: ... Not authorized to send Apple events ...; still alive after 30 s (stopped by pid)`; `P3: product Cmd-W: ... keystroke rc=142 (bound fired)`; `P3: probe Cmd-Q: ... keystroke rc=142 (bound fired); exited=no; path=none logged`; `P6 ... dialog dismiss rc=142 (bound fired)`.
  - `open` fails (178 s): `P7` and `OTOOL: 9 Mach-O files ... max minos=12.3.1` still present; `P1: cold: not up (open rc=1 err: ... error=-600, pid=none)`; every launch-dependent premise a "not up" row; P6 still records spctl/syspolicy.
  - Workflow probe-mode step scripts extracted from the YAML and run with a fake `RUNNER_TEMP`, a stub `build.sh` (asserting `M32_SKIP_CHECKS=1`), a stub pyinstaller and the real `probe.sh` (`rehearsal-workflow.txt`): Paths, Build, Freeze, selftest, Premise probe, final check all rc 0. The "Runner evidence" step fails on Linux only (`df /System/Volumes/Data`), by construction.
- **Lint.** `shellcheck` 0.10.0 clean on `probe.sh`; `ruff check packaging/` and `ruff format --check packaging/` clean; `delegate_probe.py` `py_compile` ok. `probe.spec` runs through PyInstaller 6.22.3 Analysis on Linux (rc 0; `PyObjCTools.AppHelper` hidden import "not found" there, as expected without pyobjc: only the runner's `--selftest` step proves the pyobjc imports).
- **Bash 3.2.** `bash -n probe.sh` under a real bash 3.2.57 (`bash:3.2` container, read-only mount, removed afterwards) passes; also a grep for mapfile/readarray/`${x,,}`/`declare -A`/`local -n`/`[[ =~ ]]`/`&>>`/`|&` finds none, and the script uses no arrays. The semantics (not just the syntax) are exercised only by the 5.2 rehearsal.
- **Decisions for the Flight Director before dispatch:**
  1. P8's "same with `--env`" is done on the probe app (its log line is definitive for `open --env`), not a second product launch, to stay inside the cap; the product's `--env THE_ONE_PORT` already worked in Flight 1.
  2. The product listens on its default 8484 on the runner (`M32_PRODUCT_PORT` overrides); that is the disposable runner's port, so the "no listener on 8484" quiescence check is per premise, not global.
  3. The probe app has no ATS key and `delegate_probe.py` was never run on a Mac: the first `--selftest` on the runner is its first real execution (pyobjc `typedSelector(b"Q@:@")` on a subclass of pywebview's Python-defined delegate). A failure there is a clear step failure with `probe.log` printed; the fallback (`objc.classAddMethods`) is not implemented, by the leg's design.
  4. Stub PR: copy `packaging/macos/probe/macos-packages.stub.yml` to `.github/workflows/macos-packages.yml` on a branch from main (the old `packaging-probe-macos.yml` stays on main until this flight merges). Dispatch: `gh workflow run macos-packages.yml --ref flight/03-macos-app -f mode=probe`.
  5. The Flight 1 hdiutil dmg step still runs in probe mode (not skipped); fine, it is bounded, but it is wasted minutes if you want them back.

**Review fixes (leg 2).** (1) `delegate_probe.py` now wraps the `BrowserView.AppDelegate` subclass in `try/except`; on failure it logs the traceback and falls back to `objc.classAddMethods` with explicit selectors (`applicationShouldTerminate:` `Q@:@`, `applicationShouldHandleReopen:hasVisibleWindows:` `c@:@c`, `applicationWillTerminate:` `v@:@`); if both fail it continues on the stock delegate. It logs `route: subclass|classAddMethods|none (stock delegate)`; `--selftest` prints the route and exits 0. `probe.sh` P2/P3/P4 probe rows carry `(route ...)` from `probe.log`. (2) Destroy mode ends with `os._exit(3)` after logging the hang, so the sleeping worker cannot keep the process alive. (3) `build.sh` skips the `.dmg` when `M32_SKIP_CHECKS=1` (probe mode); `full`/`lifecycle` unchanged. (4) Leg 2 AC checkboxes ticked. Re-verified on Linux: `bash -n`, shellcheck 0.10.0, ruff check/format, py_compile, and the "ok" rehearsal (rc 0, no leftovers; rows show `route subclass`; the fake probe now logs a route line). The macOS-only paths (classAddMethods fallback) remain unproven until the dispatch.

## Anomalies

---

## Session Notes
