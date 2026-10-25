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
  - **Outward steps done:**
    - committed `503ac2e` (leg 2 plus the flight artifacts) and pushed `flight/03-macos-app`;
    - stub PR #312 opened from a temporary worktree, lint and pip-audit passed, squash-merged as `5e93f6c`; its branch and worktree were removed. `gh`'s local "switch to main" was refused because `main` is checked out in Mission 31's worktree; nothing there was touched;
    - `gh auth` re-verified;
    - **probe run `40203877635` dispatched** (`--ref flight/03-macos-app -f mode=probe`, 14:47Z). **Dispatch 1 of 4.**
- **Leg 1 landed** (phase B):
  - on the merged tree, `make test-unit` 7237 passed, 12 skipped, with no fix needed;
  - the `settings` lane passed 108 (the full gate was skipped: Mission 31's browser processes were live on the host; it runs at flight end);
  - the GTK smoke OVERALL PASS on both baselines;
  - the takeover over `~dev20` PASS;
  - the container gates all PASS.

  The Developer chowned 112 root-owned files that the containers left under `f3/` back to the user.
  - **Not ours:** `$HOME/the-one-m32-evidence/A-recheck` (Flight 1) still holds root-owned files. It is to be cleaned with the operator's knowledge at flight end.
  - **Checkpoint review of leg 1 now** (Sonnet: it moves the credential-gated window routes' backing and the process-signalling code), so legs 4-5 build on reviewed, committed modules.
- **Leg 5 (`macos-runtime-seam`) risk tier: HIGH** (the shared frozen seam, with a Windows-visible change in the `PATH` walk). Its design review is running. It does not depend on the probe. Its interface to leg 4: `env.prime_login_shell_path()`, which leg 4 calls in `DesktopSession.run`.
- **Leg 5 design review cycle 1 (Sonnet): approve with changes.** Folded in:
  - the darwin gate reuses `bundle_has_modules` (pywebview 5.4's `__init__` imports no backend, so this is belt and braces), and a frozen OK detail never says "skipped" (`score_doctor`);
  - a mandatory `score_doctor` regression test;
  - the bundle strip runs over the combined `PATH` (the login entries could otherwise bypass it);
  - a stub-specific runtime detail;
  - a zombie-aware grandchild test with a short timeout, plus a never-exiting shell;
  - a lock, a cached fallback, and `path_source()` returning `(source, reason)` (an addition to the leg-4 interface);
  - `Exception`-wide fallback handling;
  - empty `PATH` entries skipped, and a `normpath` stub match;
  - the static additions accepted as an additive POSIX change.

  **No second cycle:** every change is the reviewer's own recommendation. Status `ready`.
  - **Sequencing:** leg 5 starts after the leg 1 checkpoint review finishes and leg 1 is committed, so the reviewer's unit run never sees half-done leg 5 edits.
- **Leg 1 checkpoint review (Sonnet): `[HANDOFF:confirmed]`, no blocking issues.**
  - AC1 was verified by AST diff: `takeover.py` is byte-identical apart from the logger line, and `window_control.py` differs only by `state.` substitutions and the `quit_desktop` extraction.
  - `SessionState` reproduces every locked section exactly.
  - No cycles; the shim stays GUI-free.
  - The security-relevant paths are unchanged.
  - 398 targeted tests pass.
  - Non-blocking notes:
    - the guard's untested exotic forms (`patch.multiple`, a non-literal attribute name, attribute-held aliases), which no test uses;
    - `state.server`/`state.thread` stay set after `run()` ends, so **leg 4 clears them** when it starts using them;
    - the AC boxes (now ticked).
  - Leg 1 status `completed`, committed as a checkpoint.
- **Probe run `40203877635` finished:** success, 14:47:26Z to 14:51:56Z, about 4.5 job-minutes. That is shorter than leg 2's typical estimate, so leg 3 checks whether premises bailed early.
- **Leg 3 (`macos-probe-run`) risk tier: LOW.** It reads evidence and makes no product change. Its outputs are decisions (the apparatus, the first-paint cause, the `min_os`), each logged for the legs that depend on them. No design review.
- **Mission 31 Flight 4 merged to `main` (#309, `b1e47ae`, 2026-10-25).** Mission 31 is still `active` (Flight 5 remains), so its constraints stand: no release, its checkout untouched, and shared files kept additive. 188 files changed. The overlap with this flight is `CLAUDE.md` and `the_one/agents.md` only; none of leg 1's or leg 2's working files are touched by it.
  - **Call:** merge `origin/main` into `flight/03-macos-app` at the next checkpoint (after leg 1 phase A and leg 2 land, before the review), not under two running Developers.
  - After the merge, leg 1's guard and `make test-unit` are re-run on the merged tree (main adds tests), and leg 1 phase B builds from it.
  - **Commit plan:** after leg 2 is reviewed, the Flight Director commits leg 2's files **plus the flight artifacts** (`flight.md`, `flight-log.md`, `legs/`) without leg 1's uncommitted code, then opens the stub PR and pushes. Leg 3 then dispatches.

---

- **Leg 3 landed** (run `40203877635`). The run was complete, not cut short; the premise step took 187 s, and leg 2's estimate was high.
  - **Answered:**
    - Accessibility and the quit Apple event both work, so the DD9 seam is **not** needed;
    - Cmd-Q most likely takes path T;
    - the first paint is not reproduced on the runner (painted by +3 s), so it looks environmental: no shell change, and squawk 0253 stays open;
    - `open --env` works;
    - replace-while-running keeps the old process (the guide says "quit first");
    - Gatekeeper on macOS 15.7 shows "Not Opened" with no Open button;
    - today's pystray crashes off the main thread (confirming DD2), and an Apple-event quit gives no drain (confirming DD3).
  - **Unanswered:** the delegate route. `delegate_probe.py` declared `applicationShouldTerminate:` as `Q@:@`, but the runtime prototype is `I@:@`, so both routes raised `BadPrototypeError` and every launch used the stock delegate. The selftest passed on that fallback, a harness gap.
  - **`min_os`:** the maximum minos is 14.0 (13 numpy extension files).
  - **Operator decisions (2026-10-25):**
    - "Re-probe, cap to 5": fix the probe, re-run it (dispatch 2), and raise the flight's cap to 5;
    - "macOS 14+": `min_os = 14.0`. DD8 and DD10 are annotated in `flight.md`, with the original text kept.
  - **Leg 3b (`macos-probe-rerun`), risk tier LOW:**
    - fix the probe: take the signatures from the superclass and the protocol, not hard-coded; the selftest **fails** unless a route installs; dismiss the local-network prompt; a focused Cmd-W;
    - re-dispatch (outward steps under the operator's standing go for the probe, now with the raised cap);
    - read the delegate, reopen and Cmd-W evidence.

    No design review: a bounded fix to test harness code; the flight-end Reviewer covers it.

- **Leg 5 landed** (Developer report):
  - `make test-unit` 7283 passed, 12 skipped; ruff clean;
  - `doctor` on the Linux host unchanged;
  - one intended test change: the darwin `tray:` line is now `tray: dock`.

  Uncommitted; it is reviewed with leg 4.
- **Leg 4 (`macos-dock-mode`) risk tier: HIGH** (lifecycle, quit and drain paths, the shared desktop shell).
  - **Design review cycle 1 (Sonnet): approve with changes.** Two highs:
    1. path S had no exit: pywebview's `_boot` thread is non-daemon, so S now waits on `boot_stopped` then `os._exit(0)` after the drain;
    2. `_destroy_splash` while only the splash exists empties `instances` and calls `app.stop_`/`abortModal` mid-drain, so it is suppressed on darwin during any quit state.

    The mediums folded in:
    - a `loop_stopped` flag;
    - named AppKit seams and `TerminateWorker` parameters;
    - full decision tables;
    - `tray_mode = "dock"` set at the top of `run()`;
    - the reply delivered in AppKit's modal wait (a gate on 3b's evidence, with `performSelectorOnMainThread…modes` as the fallback);
    - the timing budget (a 5 s boot wait + 60 s join < 75 s);
    - "reply sending", flush, then reply;
    - geometry read on the main thread in the delegate callback.

    The lows: the App Nap token held at module level; `chrome` unchanged; priming after `begin_boot`.
  - **The Flight Director's answers to the review's questions:**
    - `os._exit(0)` after the drain is accepted for path S;
    - `reply-now` returns `NSTerminateNow`;
    - an unpublished window's geometry save is skipped.
  - **No second cycle:** every change is the reviewer's own recommendation. Two phases (A: core, state, control, canary; B: shell wiring, install, docs, gates). Status `ready`. The 3b gate applies to **Phase B only**: Phase A (the pure core, the worker, state, control, the canary) does not depend on the route, so it starts now, beside 3b's probe fix (disjoint files).

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

**Phase B checkpoint** (AC1-AC7 hold; leg status `landed`; run on the merged tree, `16484eb` plus the leg's uncommitted files).

- **Re-verify on the merged tree.** Guard + `SessionState` tests: 46 passed. `make test-unit`: `== 7237 passed, 12 skipped, 2987 deselected, 56 warnings in 338.83s ==` (12 skips as expected; grew from 7105 with main's tests; the merge broke nothing in the leg's files). `ruff check` clean; `ruff format --check`: 697 files already formatted.
- **AC5.** `THE_ONE_TEST_NETNS=1 ... --lane settings -x`: `108 passed in 239.43s`. The full `--parallel 3` gate was NOT run: Chromium/Playwright processes from the Mission 31 checkout were live on the host at the time, so only `settings` ran.
- **AC6.** `.deb` built with `M32_BUILD=$HOME/the-one-m32-build/f3 packaging/linux/build.sh --version 0.11.9.dev30` (`gleepglorp-ai_0.11.9~dev30_amd64.deb`, plus an AppImage). `gtk-smoke.sh`: `ubuntu-26.04` OVERALL PASS, `debian-13` OVERALL PASS (0 FAIL rows each; window maps, WM_DELETE_WINDOW close per tray mode with `tray: none`, size stable 1440x900 across relaunches, quit route exits within 15 s). Takeover (`--takeover-from` Flight 2's `~dev20` on `ubuntu-26.04`): `OVERALL PASS (takeover)` (old v0.11.9.dev20 replaced, new v0.11.9.dev30 serving, window visible, `the-one quit` ends it). Gates (`gates.sh ... --display xvfb`): `deb/ubuntu-26.04-baseline: G1p=PASS G1u=PASS G2=PASS G3=PASS G4=PASS upgrade=N/A single=PASS`; `deb/debian-13-baseline`: same.
- **AC7.** No 8484/8485 listener; operator data dir newest file mtime unchanged (1791383047.967 before and after). Only `m32-*` containers, none left. The smoke/gate runs left 112 root-owned files under `f3` evidence/build; chowned back with a throwaway `m32-chown` container (0 left under `f3`; the older `A-recheck` evidence dir from an earlier flight still holds root-owned files, untouched). No PID kills outside the scripts' own recorded groups. `git status` shows only this leg's files plus leg 2/3 artifacts.
- **Evidence:** `$HOME/the-one-m32-evidence/f3/leg1/` (`settings-lane.log`, `build.log`, `smoke-<distro>.log`, `takeover.log`, `gates-<distro>.log`); packages in `$HOME/the-one-m32-build/f3/packages/`.

---

### macos-runtime-seam

**Landed** (leg 5; DD2, DD6, DD7). Uncommitted.

**Implemented**
- `platform/interpreter.py`: `walk_python_candidates(names, search_path)` (candidate-outer, per-entry `shutil.which(cand, path=entry)`, empty entries skipped, Store alias and CLT stub skipped, returns `(found, skipped)`); `_is_clt_stub` (darwin only, `normpath` compare, never resolves symlinks); `_command_line_tools_installed` (`xcode-select -p`, 5 s bound, cached, existing-directory check); the DD6 darwin error text. The override is never filtered.
- `platform/env.py`: `prime_login_shell_path(timeout=5.0)`, `path_source()`, `_PRIMED` state (cached including fallback), login-first order in `clean_subprocess_env` with the bundle strip over the combined `PATH`, the two static additions, and a guard for `Path.home()` raising.
- `main.py`: `serve` and `doctor` prime first. `diagnostics.py`: stub-aware `detect_runtimes`, `tray: dock`, the `path:` advisory line, `_probe_desktop_shell_darwin`.
- Docs: `the_one/agents.md` ("macOS runtime seam" section) and one `CLAUDE.md` addition.

**Choices the DDs left open**
- Markers `__M32_PATH_BEGIN__` / `__M32_PATH_END__`; the last complete block wins; a probe failure reason is one of "did not answer within Ns", "exited N", "could not run '<shell>': <ExcType>", "the login shell printed no PATH".
- `path:` shows `path: unprimed` on a frozen darwin process that never primed (e.g. `chat`); absent elsewhere.
- A new test file `tests/test_macos_runtime_seam.py` (rather than appending to the existing env/interpreter files); doctor tests are `TestMacosDoctor` in `tests/test_doctor.py`; the AC5 test is in `tests/test_packaging_score.py`.
- `_XCODE_SELECT` / `_XCODE_SELECT_TIMEOUT` are module constants so tests can point at a fake binary.
- Existing tests: none pinned first-hit-only behaviour. One was updated by intent: `test_doctor.py::test_tray_lines` darwin assertion (`tray: not probed (macOS)` to `tray: dock`).

**Tests** (`tests/test_macos_runtime_seam.py` unless noted)
- Walk and stub: `TestStubAndWalk` (stub then real python, stub with CLT, only the stub, `/Library/...` not a stub, never runs off darwin, Windows alias shadowing, override unfiltered, empty entries, candidate-outer); `TestXcodeSelect` (cached, removed dir, non-zero exit, bounded hang).
- Priming: `TestPrimeLoginShellPath` (not applicable, markers, fish-style via printenv, rc noise, last block, timeout kills the group via `/proc/<pid>/stat`, never-exiting shell, missing/relative `$SHELL`, non-zero exit, empty block, no markers, passwd fallback, idempotent plus cached fallback, concurrent first calls run one probe).
- Order: `TestPathOrder`; static additions and the `HOME` guard; `test_main_primes_before_serve_and_doctor[serve|doctor]`.
- Doctor: `TestMacosDoctor` (Cocoa OK without "skipped", frozen missing FAIL, non-frozen skipped, no Cocoa/pystray import, `path:` line only on frozen darwin, stub reported not found, walk past the stub). AC5: `test_frozen_darwin_doctor_output_passes` in `tests/test_packaging_score.py`; `score.py` unchanged.

**Results**: `make test-unit`: 7283 passed, 12 skipped. `ruff check` and `ruff format --check`: clean.

**AC4** (`THE_ONE_DATA_DIR=<scratch> THE_ONE_PORT=8496 the-one doctor`, non-frozen Linux): the same gate lines as before (child spawn, python interpreter, desktop shell, llm providers, model catalog, usearch, fts5, embedding model, file watcher, window chrome, time zones, mcp sdk) all OK, `RESULT: PASS`; advisory lines `sandbox: bubblewrap` and `tray: none — no tray backend for this session`; no `path:` line. (The pre-existing `desktop shell: OK — skipped — unexpected error: Namespace AyatanaAppIndicator3 not available` is the untouched generic Linux path.) The runtimes list now reads python3 via the per-entry walk (`/bin/python3`); `python` is not found on this host, as before. Scratch dir removed; no 8484/8485 contact.

**For leg 4**: add `from the_one.platform.env import prime_login_shell_path` and a single `prime_login_shell_path()` call in `DesktopSession.run` just after the `is_ours` return; it never raises and is a no-op off frozen darwin. This leg did not touch `the_one/interfaces/desktop/`. Tests that monkeypatch `sys.platform` to darwin and freeze must reset `env_mod._PRIMED` (the new test file does so with an autouse fixture).

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

### macos-probe-run

**Landed.** Run `40203877635` (dispatch 1 of 4; `macos-packages.yml`, `flight/03-macos-app` at `503ac2e`, `mode=probe`). No code change, commit, push or dispatch by this leg. Evidence: `~/the-one-m32-evidence/f3/leg3/` (`run-40203877635/` = the downloaded artifact, `sha256.txt` = its sha256 list, `run.log` = `gh run view --log`). Cited paths below are relative to `run-40203877635/macos-packages-logs/` (`probe/` = `$M32_LOGS/probe/`).

**The run is complete, not bailed out early.** Job `build` succeeded 14:47:26Z to 14:51:56Z (4m30s); the premise step finished `== done in 187 s` (`probe-step.log`), and every premise row is in `probe/SUMMARY.txt`. It is short because leg 2's "typical 455 s" was a worst-case-leaning estimate: most premises needed 5-30 s (P2/P3/P4/P9 exit almost at once), and the only bound that fired was P6's `open` (rc=142, by design). `probe/tracked.pids` lists 16 pids and there is no `quiesce.log` (no forced kill). Runner (`runner.txt`): macOS 15.7.9 (24G830), arm64, Xcode 16.4, 5 CPUs, 15 GB; `/usr/bin/python3` 3.9.6. The product `.app` is built from `main`'s desktop code (DD9), so product rows describe today's build.

**One harness defect limits the run: the delegate premises are unanswered.** `delegate_probe.py` declared `applicationShouldTerminate:` as `Q@:@`; the runtime's superclass signature is `b'I@:@'` (pyobjc 12.2). Both routes raised `objc.BadPrototypeError: ... signature that is not compatible with ObjC runtime: I@:@ != Q@:@` (`probe/P2/probe-probe.log`, identical in every probe log; `probe-selftest.txt` ends `selftest ok route=none (stock delegate)`, so the selftest passed on the fallback). Every probe launch therefore ran on pywebview's **stock** delegate: `route: none (stock delegate)`.

#### Premise table

| premise | observed (SUMMARY row; evidence) | settles |
|---|---|---|
| P7 | `xcode-select -p rc=0 path=/Applications/Xcode_16.4.app/Contents/Developer; /usr/bin/python3 --version rc=0 Python 3.9.6` (`P7/`) | Toolchain present. Not decision-bearing. |
| OTOOL | `152 Mach-O files, 152 read; max minos=14.0; table: minos count;11.0 139;14.0 13;; unreadable/no-version: 0` (`OTOOL/table.txt`, `sorted.tsv`) | The 13 files at 14.0 are all numpy extensions (`numpy/_core/_multiarray_umath`, `_multiarray_tests`, `fft`, `linalg`, 9 under `random/`). Everything else is 11.0. Decision 5. |
| P8 | product via plain `open`: `PATH=/Users/runner/hostedtoolcache/Python/3.11.9/arm64/bin:... SHELL=/bin/bash HOME=/Users/runner TMPDIR=/var/folders/.../T/ M32_PROBE_ENV=(not seen)`; probe via `open --env M32_PROBE_ENV=1`: same PATH/SHELL, `M32_PROBE_ENV=1`; probe log `env M32_PROBE_ENV=1 (does open --env pass variables)` (`P8/*.ps-eww`, `*.lsappinfo`, `probe-env-probe.log`) | `open --env` passes variables. The inherited PATH is the runner's own, so it does not model a Finder launch. Decision 6. |
| P1 | cold: `up (pid 4054); first /api/live=200 at +1s; +1 bytes=118341 live; +3 bytes=173421 live; +5 ... 173458 ... +30 bytes=173453`; warm: `+1 bytes=125116 ... +3 bytes=173111 ... +30 bytes=173004`; control (probe data-URL window): `+1 bytes=117522B; +3 117461B; +5 117461B; +10 117461B`. PNGs read: `P1/cold-1.png` dark empty window, `cold-3.png` painted Chats page ("Hello."), `warm-1.png` window mid-geometry-restore with a white card, `control-5.png` a plain white window | The runner has a GUI session (divert 3 not triggered) and the product painted by +3 s on both launches. Decision 4. |
| P4 | probe: `open -a ... pids before [5972] after [5972]; reopen log: 0 line(s)` (stock delegate, no handler to log). product: `open -a ... pids before [6032] after [6032]; state: 200 {"desktop":true,"mode":"window","visible":true,"mapped":null,"tray":null,"version":"0.11.8","pid":6032}`; `open -n rc=0: second pid=6263 exited 0.3s after appearing; focus lines in the first's log: 1; ... lsappinfo front pid=6032 (first=6032 second=6263); screenshot 173091B` (`P4/after-open-n.png`: first instance's window in front) | Reopen of a running app does not spawn a process (DD5). `lsappinfo front` is usable and `-n` takeover works on today's build. The reopen **handler** is unanswered (no delegate installed). |
| P2 | product: `osascript rc=0; exited 0.0s after the event returned`; probe: `osascript rc=0; exited 0.0s after the event returned; log: terminate=0 reply=0 willTerminate=0`; signatures `[MainThread] signature superclass applicationShouldTerminate_=b'I@:@'` | The quit Apple event reaches the app (Automation works), and the stock delegate lets AppKit exit at once. `NSTerminateLater`: **unanswered**. The product's `P2/product.stderr` ends at the catalog warning with no `Shutting down` / `Finished server process`: today's build is killed by the Apple-event quit with **no server drain** (compare `P3/product.stderr` lines 30-37, which do show the drain). |
| P3 | product Cmd-W: `front=6441 (the app); state before: 200 {...}; keystroke rc=0; state after: curl-rc=7; pid alive=no`; probe Cmd-W: `front=6668 (the app); keystroke rc=0; exited=no; path=none logged`; probe Cmd-Q: `front=6922 (the app); keystroke rc=0; exited=yes after 0.3s; path=none logged` (`P3/probe-q-probe.log`: `window closed event` at 2.496 s, no `exit path S` line) | Accessibility works: `rc=0`, a keystroke changed the app's state. Decision 1 and 3. |
| P9 | `[MainThread] destroy: webview.start returned 0.003 s after window.destroy(); process alive=yes (waited 5s of 28)`; log: `exit path S (start returned, no terminate)` (`P9/destroy-probe.log`) | Destroying the last window from a worker returns `webview.start` at once on this stack; no hang (the hazard DD3 avoids does not show here). The process stays alive after the return, so S needs an explicit exit. |
| P5 | `installed copy pid 7244; replaced (rm -rf + ditto of a marked copy: ditto rc=0, sign rc=0) while running; old alive=yes; open -a rc=0; pids now [7244 ] (same pid ...); old process holds the marker open: 0; marker file present: yes; state: 200 {... "pid":7244}` | Decision 7. |
| P6 | `spctl rc=3 ... rejected`; `syspolicy_check rc=70 ... failed one or more pre-distribution checks`; `open rc=142 (bound fired); dialog dismiss rc=0; process after open: 7840(translocated); path: /private/var/.../AppTranslocation/4F2F678C-.../d/GleepGlorp AI.app/Contents/MacOS/the-one`; `P6/after-open.png`: dialog "GleepGlorp AI" Not Opened | Decision 8. |

#### Decisions

1. **Apparatus (DD9).** Accessibility works (P3: three `System Events` keystrokes `rc=0`, and the probe's Cmd-Q ended the process in 0.3 s), `lsappinfo front` is usable (P3 `front=<pid> (the app)`; P4 `lsappinfo front pid=6032`), and the quit Apple event reaches the app (P2 `rc=0`, both apps gone 0.0 s later). **The DD9 test seam is not needed in leg 4 for keystroke or quit driving.** Caveats: (a) Cmd-W did nothing to the probe window but ended the product (the product has the tray-unavailable "close button will exit" fallback, and its exit logged the drain; the cause of the difference is not established, so leg 4 must not rely on Cmd-W as a close driver without re-running P3 on the fixed delegate); (b) a stale "Allow M32 Probe to find devices on local networks?" privacy prompt overlays every screenshot after the first probe launch (`P1/cold-1.png` onward) and was never dismissed. It did not stop keystrokes, but the lifecycle script should dismiss it or avoid launching the probe in the same run, and screenshots are partly covered.
2. **Delegate (DD4, DD3): UNANSWERED.** Route `none (stock delegate)`: the declared `Q@:@` is rejected by the runtime (`I@:@`). Neither route was exercised for real, and `NSTerminateLater` plus the deferred reply never ran (`terminate=0 reply=0 willTerminate=0`). Fix for the re-run: declare `b"I@:@"` (better, read it from the superclass at run time, `BrowserView.AppDelegate.applicationShouldTerminate_.signature`, which the probe already logs). `NSTerminateLater` is 2, which fits a 32-bit unsigned return. **Leg 4 must not copy DD4's text "declared so PyObjC types the return as `NSUInteger`":** the installed prototype is `I@:@`.
3. **Cmd-Q's path (DD3): T, by inference.** The probe's Cmd-Q ended the process 0.3 s later with a `window closed event` and **no** `exit path S` line, whereas the S path in P9 does write that line (`P9/destroy-probe.log`). So AppKit's `terminate:` ran (T), consistent with pywebview's `q` menu binding. The stock delegate logs nothing at terminate, so this is not a direct observation; the re-run's `terminate=` count will confirm it.
4. **First paint (DD11).** Cold: +1 s dark empty window (118341 B), +3 s painted (173421 B, stable to +30 s); warm: +1 s mid-restore (125116 B), +3 s painted (173111 B). `/api/live` was 200 at +1 s both times, so the server was up before the window painted. The control window is white at +1 s and unchanged after (117522 to 117461 B), so WKWebView itself starts in under a second and the gap is the page load. **A blank first paint is not reproduced on this runner**, and the samples are only +1 and +3, so the paint landed between 1 and 3 s. Class: not our shell and not ATS blocking on this runner (the page loaded over `http://127.0.0.1` as built from `main`); the persistent blank on the operator's own Mac stays unexplained, so DD11's "environmental: document it and keep squawk 0253 open" applies. **Leg 4 changes nothing for first paint.** The warm +1 s frame shows the window being laid out at a restored geometry before content; record it, no action.
5. **`min_os` (DD8).** The maximum `LC_BUILD_VERSION` minos is **14.0** (13 files, all numpy: `_core/_multiarray_umath`, `_core/_multiarray_tests`, `fft/_pocketfft_umath`, `linalg/_umath_linalg`, `random/{_bounded_integers,_common,_generator,_mt19937,_pcg64,_philox,_sfc64,bit_generator,mtrand}`); the other 139 are 11.0 (`OTOOL/table.txt`). That is above 11.0, so DD8's `min_os` becomes 14.0, and **14.0 exceeds macOS 13, which the leg says to raise**: the supported macOS floor would rise from 11 to 14 (operator-visible: the guide's requirements line, the Info.plist `LSMinimumSystemVersion`, and the release notes). The alternative is a numpy pin whose arm64 wheel carries an 11.0 or 12.0 minos, which is an operator and Flight Director choice (it touches the pinned dependency closure). Either way leg 6 must not hard-code 11.0.
6. **Environment (DD7).** An `open`-launched app inherits the launching session's environment: `PATH=/Users/runner/hostedtoolcache/Python/3.11.9/arm64/bin:...`, `SHELL=/bin/bash`, `HOME=/Users/runner`, `TMPDIR=/var/folders/.../T/`; `lsappinfo` shows `LSEnvironment=[ NULL ]`. **`open --env` passes variables** (`M32_PROBE_ENV=1` seen by the probe; the plain-`open` product did not see it). The runner's PATH is its own service PATH, not the stripped `/usr/bin:/bin:/usr/sbin:/sbin` of a real Finder launch, and `SHELL` is `/bin/bash` rather than the user default zsh, so **P8 does not confirm DD7's stripped-PATH premise**; leg 5's login-shell check must set `SHELL` and a minimal `PATH` explicitly (`env -i`-style), as DD7 already says.
7. **Replace while running (P5, DD5).** After the running app's bundle was deleted and replaced by a marked, re-signed copy, the old process stayed alive, `open -a` returned rc=0 with the **same pid 7244**, and the old process answered `/api/window/state` with `version 0.11.8`; it holds no file of the new copy open (`old process holds the marker open: 0`), and no crash or error appears in `P5/old.stderr`. No data loss or corruption: divert criterion 4 not triggered. The guide must say: quit GleepGlorp AI before replacing it in Applications; if you replace it while it runs, the running copy keeps running and `open` just brings it forward, so the new version only takes effect after a quit and relaunch. Limit: the probe emulated Finder with `rm -rf` plus `ditto`, not Finder's own replace dialog.
8. **Gatekeeper (P6).** `spctl`: `rejected` (rc=3). `syspolicy_check` (rc=70): `Notary Ticket Missing` ("A Notarization ticket is not stapled to this application") and `Internal Xprotect Error`, both Fatal (`P6/syspolicy.txt`). `open` of the quarantined copy (`xattr rc=0`) started a process from an **AppTranslocation** path (`/private/var/folders/.../AppTranslocation/4F2F678C-.../d/GleepGlorp AI.app/Contents/MacOS/the-one`, pid 7840) and showed the dialog "GleepGlorp AI" Not Opened: "Apple could not verify "GleepGlorp AI" is free of malware that may harm your Mac or compromise your privacy.", with buttons **Done** and **Move to Trash** only (`P6/after-open.png`; there is no Open button on macOS 15.7). `open` itself blocked until the bound (rc=142); the dialog was dismissed by clicking Done in `CoreServicesUIAgent` (`dismiss rc=0`). Feeds leg 7: the approval path is System Settings, Privacy and Security, "Open Anyway" after the first refused launch (not exercised here: do not state it as observed), and the guide should note the app runs from a translocated path until moved out of Downloads/quarantine.
9. **Today's build (DD2).** `P2/product.stderr` and `P3/product.stderr`: `System tray unavailable — close button will exit the app (F4 fallback)` with `NSInternalInconsistencyException - NSWindow should only be instantiated on the main thread!` raised from `build_tray` / `__init__` (pystray off the main thread). That confirms DD2: the tray cannot be built on darwin as it is, `tray: null` in `/api/window/state`, and a window close exits the app. `/api/window/state` has `visible:true, mapped:null` and **no `focused` key** in the build from `main`. The Apple-event quit gives no server drain (decision 2, P2 row), which is the defect DD3 fixes; the `open -n` takeover works (second process exited in 0.3 s, one focus line in the first's log).

#### Divert and acceptable-variation criteria

- **Delegate cannot be extended by either route (DD4):** NOT triggered, and NOT cleared. Both routes failed only on the probe's own wrong prototype; nothing yet shows a corrected subclass fails.
- **`NSTerminateLater` does not drain (DD3):** NOT triggered, NOT cleared: never exercised (`terminate=0`).
- **No GUI session (P1):** NOT triggered. Windows were created, painted and screenshotted; P3/P4 drove them.
- **Replace-while-running loses or corrupts data (P5):** NOT triggered (decision 7).
- **4-dispatch budget spent without a green lifecycle run:** NOT triggered: 1 of 4 used, so 3 left; a corrected probe re-run would be the second.
- **Acceptable variations:** P3 and P2 did not fail, so the seam fallback is not taken; `os._exit(0)` and `classAddMethods` variations are not yet evaluated (need the re-run); first paint: the "environmental" variation applies provisionally (decision 4).

#### What a re-run needs

Only decision 2 (and, with it, the handler halves of P4 and the T-path confirmation of P3) is unanswered. Fix `delegate_probe.py`: declare (or inherit) `I@:@` for `applicationShouldTerminate:`; keep the selftest as the gate (it must print `route=subclass`); dispatch `mode=probe` again. Also dismiss or deny the "local network" prompt before the screenshots (e.g. have `probe.sh` click Don't Allow through `CoreServicesUIAgent`/`UserNotificationCenter`, or accept the overlay), and re-run P3 Cmd-W to see whether the probe and the product behave alike. Probe-only cost about 4.5 minutes (see below). This is a probe change the Flight Director must schedule; this leg changed none.

#### Notes for legs 4-7 (for the Flight Director to re-design)

- **Leg 4:** build the delegate with the superclass-derived `I@:@` signature, not `NSUInteger`; do not add a test seam for keystroke/quit driving (decision 1); the macOS quit path must be added because today's Apple-event quit skips the drain; first paint needs no shell change.
- **Leg 5:** the login-shell env check must pin `SHELL`/`PATH` itself (decision 6).
- **Leg 6:** `min_os` becomes 14.0 unless numpy is re-pinned (decision 5); needs an operator call.
- **Leg 7:** guide content from decisions 7 and 8 (quit before replacing; Gatekeeper "Not Opened" dialog has no Open button on macOS 15, use Privacy and Security).

#### Hosted minutes used

Job `build`: 14:47:26Z to 14:51:56Z = **4 min 30 s** (billed as 5 whole minutes, so 5 x 10 = **50 billed minutes** for macOS; 45 if billed by the exact 4.5 min). Of that the premise step was 187 s. Running total for this flight: this run only (leg 2's rehearsals were Linux, local).

### macos-probe-rerun

- **AC1 (probe fix)** (Developer, no commit). Edits: `packaging/macos/probe/{delegate_probe.py,probe.sh,README.md}` and `.github/workflows/macos-packages.yml` (the `on:` block is untouched and identical to the stub).
  - **`delegate_probe.py`:** the explicit `Q@:@` is gone. `applicationShouldTerminate_` and `applicationWillTerminate_` are plain methods of the subclass, so PyObjC uses the inherited prototype (`I@:@` in leg 3's log). The reopen selector is not defined by pywebview's delegate, so its encoding is read from the `NSApplicationDelegate` protocol (`protocolNamed(...).descriptionForInstanceMethod_`, then `instanceMethods()`), frame offsets stripped; if the protocol yields nothing it is built from `objc._C_*` constants. A `resolved signatures:` line logs each signature and its source (superclass, protocol or constants), then each defined method's `.signature` and the superclass's. The `classAddMethods` fallback builds its selectors from the same resolved signatures. `--selftest` exits 3 (and logs `selftest FAILED`) when the route is `none`. `NSApp.delegate().className()` is logged on the `shown` and `loaded` events. Unverifiable on Linux: how PyObjC actually resolves the reopen encoding (the dispatch-2 log will say).
  - **Workflow:** the selftest step stays a plain failing step (the job reads red). The `Premise probe` step now has `if: ${{ !cancelled() && inputs.mode == 'probe' }}` (it still `continue-on-error`), so a failed selftest still yields P1/P4/P8 and the upload; its `timeout-minutes` is 23 and the outer alarm 1290 s (caps now sum to 1110 s: P8 120, P1 260, P4 110, P2 110, P3 180, P9 60).
  - **`probe.sh`:** `lnp_check` (one bounded System Events call, 8 s) reads the alert windows of `UserNotificationCenter`, `CoreServicesUIAgent`, `SecurityAgent`, `NotificationCenter` and `universalaccessd` (owner, window name, texts, buttons) and, when asked, presses Allow, else Don't Allow (AXPress, by button name). It runs after every probe launch (P1's launches skip it so the marks are not delayed; P1's control runs it after its series). New row `PLN`: after the cold product launch's series, a screenshot (`P1/pln.png`) and a read without dismissing, then the dismissal attempt (two rows). P3's probe Cmd-W now raises the probe and clicks the window centre first (`focus_click`), and records the window's count/visible/frontmost/position/size before and 2 s after (`window_state`). P1 marks are +1, +2, +3, +5, +10 (+20, +30 for the product).
  - **Checks:** ruff format and check, `py_compile`, `bash -n`, shellcheck 0.10.0 and actionlint 1.7.7 are clean.
  - **Rehearsals (Linux, shims)**, evidence under `$HOME/the-one-m32-evidence/f3/leg3b/`: `rehearsal-ok` (43 s), `rehearsal-tcc` (363 s; every System Events call hits its bound, the PLN and P3 rows say so), `rehearsal-openfail` (178 s), all with no leftover process or listener; and `rehearsal-workflow-none` (the fake selftest reports route `none`, exits 3: the selftest step fails, the premise probe still runs and writes SUMMARY, the logs directory is populated, the final check step passes) beside `rehearsal-workflow-ok`. The shims return empty output for System Events reads, so the new `PLN`/`window_state` text paths are exercised only for "none seen" and "unreadable"; real alert text is untested until dispatch 2. On the rehearsal, the cold series' last mark shows `cut` at a 0.05 scale (shot time against the scaled cap); at scale 1 the 45 s cap leaves wide margin.

## Anomalies

---

## Session Notes
