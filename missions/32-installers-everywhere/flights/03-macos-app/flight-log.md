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

- **Leg 3b AC1 (the probe fix) done.**
  - The signatures are taken from the runtime (the inherited prototype; the protocol, then constants for reopen).
  - The selftest fails on route `none`, and the probe still runs after it.
  - Prompt dismissal, a focused Cmd-W, denser P1 marks and a `PLN` row.
  - Four Linux rehearsals pass.

  The fix is test-harness only, and the Reviewer's medium on leg 2 was the same class, so no separate review: the flight-end Reviewer covers it.
  - Committed `c2db6f1` (the probe plus the flight artifacts; leg 4 phase A's and leg 5's code stay out). Pushed. `gh auth` re-verified.
  - **Run `40206047338` dispatched** (`mode=probe`, `c2db6f1`). **Dispatch 2 of 5.**

- **Leg 3b landed (run `40206047338`, dispatch 2 of 5, about 60 billed min; the flight total so far is about 110 billed).**
  - **Leg 4's Phase B gate is met:**
    - route `subclass`;
    - signatures `applicationShouldTerminate:` `I@:@` (inherited), reopen `B@:@B` (protocol), `willTerminate` `v@:@`;
    - **the `callAfter` reply was delivered** during the `NSTerminateLater` wait, for the quit Apple event (terminate → reply 3.0 s → `willTerminate`) and for a real Cmd-Q;
    - Cmd-Q is **path T, observed**;
    - the reopen handler fires on `open -a` with no new process;
    - no local-network prompt for the product.
  - **Corrected reading (P5):** replacing the `.app` while it runs **crashes the old process without a drain** (pywebview's `FileNotFoundError` for its JS dir), and `open -a` then starts the new one. No data loss was observed (SQLite is crash-safe), so divert 4 is not triggered.
    - **Disposition:** the guide says to quit before replacing (DD5 already planned that). The contributor check's step 9 observes Finder's real behaviour. A guard (e.g. the new copy taking over before the old one touches its moved files) is out of this flight's scope; it's a candidate for the debrief.
  - **Probe Cmd-W:** it has no effect on the probe's window, cause unknown. The product's Cmd-W behaves (it exits with a drain on today's build), so Cmd-W is not used as a driver.
  - **Still unproven until leg 7:** the delegate on the real product under load, and the Dock's Quit and logout paths.

- **Leg 4 Phase A accepted** (`make test-unit` 7325 passed, 12 skipped; ruff clean; the split guard passes; the canary has 7 `ast` checks).
  - Accepted deviations:
    - `macos_dock` is imported at module top in `window_control.py`. The DD12 test forbids lazy imports on the close path, and `macos_dock` has no top-level AppKit import (subprocess-tested);
    - `begin_quit()` returns the window on the first call only, so geometry is saved once across paths T and S;
    - `DockView` gains `native_window`.
  - **Phase B started;** its gate is met by leg 3b.
- **Sequencing:** leg 6 Phase A changes the Linux build (`render.py`, the templates, `build-inner.sh`), and leg 4 Phase B builds a `.deb` for its GTK smoke from the working tree. So leg 6 Phase A starts **after** leg 4 Phase B lands, not beside it.

- **Leg 6 (`macos-recipe`) risk tier: HIGH** (the metadata interface consumed by Linux and Flight 4; it builds what leg 7 spends dispatches on).
  - **Design review cycle 1 (Sonnet): approve with changes.** Four highs folded in:
    1. the spec can't render from the staged copy, so `build.sh` writes `product.json` and passes it as `M32_PRODUCT_JSON`;
    2. universal2 wheels would fail an arm64-only rule, so the audit requires arm64 present, reports fat files, uses `otool -arch arm64`, and the first run is `--report-only`;
    3. probe mode would pass the old bundle id, so it comes from `build.env`;
    4. `checks.sh` had two owners, so the workflow owns it, `build.sh` no longer calls it, and `M32_SKIP_DMG`/`M32_REUSE_VENV` are added for N+1.

    The mediums folded in:
    - logs read from a file (below);
    - apps addressed by path, with System Events by pid;
    - the port as a parameter;
    - geometry compared AX against AX;
    - AXPress on the close button;
    - an anchored `^FAIL` and the lifecycle summary in the final check;
    - a fixed N+1 scheme, with the version read from `/api/info`;
    - `hdiutil attach` details;
    - `.ips` crash-report diffs;
    - explicit `doctor` greps;
    - the full pystray removal from the spec;
    - shared shell helpers in `lib.sh`;
    - `info_plist.py` as a helper;
    - two more rehearsal scenarios.
  - **The Flight Director's call (logged for alignment): a log file for Finder launches.** A Finder-launched macOS app's stdout/stderr go nowhere today (`ensure_stdio_streams` only replaces `None` streams). `frozen_entry_mac.py` (packaging code) redirects the `app` command's output to `~/Library/Logs/GleepGlorp AI/app.log` when stderr is not a TTY, truncated past 10 MB. That gives contributors a log to send back, and `lifecycle.sh` one stable place to read; the guide names it.
  - **The reviewer's questions, answered:**
    - `lifecycle.sh` runs even after `checks.sh` failures (dispatches are scarce);
    - Phase B starts from leg 4's AC5 table, quoted;
    - logs come from the new log file.
  - **No second cycle.** Status `ready`. Phase A starts after leg 4 Phase B lands (the Linux build overlap).

- **Leg 4 landed** (Phase B):
  - `make test-unit` 7358 passed, 12 skipped; ruff clean; the split guard passes;
  - the `settings` lane passed 108;
  - Linux `0.11.9.dev32` GTK smoke OVERALL PASS on `ubuntu-26.04`;
  - the AC5 observable table is in its section.
  - **Accepted deviation:** `_destroy_splash` is not suppressed on `boot_stopped` alone, since `_boot` sets that event on a normal boot too and the splash would never close. On darwin it is suppressed on `terminate_pending`, `really_quit`, `loop_stopped` or a boot error. Every quit sets `really_quit` through `begin_quit`, and a test pins that a normal boot still closes the splash.
  - **Not provable off a Mac:** `_install_delegate`'s class body and `_begin_activity` (`# pragma: no cover`); leg 7's hosted run is their proof.
- **Checkpoint review of legs 4 and 5 (Sonnet:** process signalling, the shared seam, the credential-gated routes) runs beside **leg 6 Phase A**, which edits packaging files only. The Reviewer runs targeted tests only, so leg 6's in-progress files can't disturb it.

- **Checkpoint review of legs 4 and 5 (Sonnet): `[HANDOFF:confirmed]`, no blocking issues.** 283 targeted tests pass.
  - Paths T and S, the splash suppression, the darwin `quit_desktop` mapping, the inherited delegate signatures and the AppKit import isolation are verified.
  - Linux and Windows are unchanged (priming is a no-op; the `PATH` walk keeps `PATHEXT`; `killpg` only on the login shell's own group).
  - The security surface is unchanged.
  - Non-blocking notes:
    1. a failed delegate install leaves the stock delegate (Cmd-Q then terminates without a drain), so **`lifecycle.sh` asserts `route=subclass` first** (carried to legs 6-7);
    2. the static `PATH` additions are cross-platform (covered by AC2's exception);
    3. `strip_bundle_dir_from_path`'s docstring says "front" but strips everywhere (pre-existing);
    4. the darwin gate is only really exercised in the hosted run.
  - Legs 4 and 5 `completed`, committed as checkpoint 3 (leg 6 Phase A's in-progress packaging files stay out).

- **Leg 6 Phase A accepted:**
  - `make test-unit` 7399 passed, 12 skipped; ruff and shellcheck clean;
  - the Linux no-change proof's only difference is `METAINFO_ID` → `APP_ID` (same value);
  - the Linux `0.11.9.dev33` build and its audit pass (1027 files, max GLIBC 2.34);
  - the macOS spec's Analysis on Linux exits 0;
  - the `build.sh` rehearsal passes.

  Choices noted: a failed `.dmg` is now fatal in `build.sh`; `build.env` is shell-quoted, so the workflow must `source` it; a dylib's own install name is exempt from the load-path rule.
  - **Phase B started** (the workflow modes, `checks.sh`, `lib.sh`, `lifecycle.sh`, the rehearsal). Until it lands, the committed workflow's `full` mode would build with no checks. Nothing dispatches before Phase B.
  - **Check:** the Phase A agent reported "background work"; no process of its own was found running (only Flight 2's known `dbus-daemon` 2132116).

- **Operator (2026-10-25): "go ahead and kill it".** The Flight Director stopped the two leftover `dbus-daemon` processes from Flight 2 leg 2's doctor smoke by their recorded PIDs (2132116 at-spi, 2132108 session bus); both are gone. That closes the item carried since Flight 2.
- **Leg 6 landed** (Phase B):
  - `lib.sh` factored (probe.sh's rehearsal unchanged);
  - `lifecycle.sh` L1-L10, asserting `route=subclass` first;
  - the workflow's `full`/`lifecycle`/`probe` modes;
  - `checks.sh` updated;
  - 7 lifecycle rehearsal scenarios plus 6 workflow-extraction runs; the rehearsal found and fixed 4 `lifecycle.sh` bugs;
  - `make test-unit` 7399 passed, 12 skipped.
  - **Open:** the per-step `timeout-minutes` sum to 71 against a 50-minute job, so the worst case might cut the evidence upload; sent to the review.
  - A `the-one` process on 8491 reported by the Developer (pid 2322812) had exited by the time the Flight Director checked. It was not this flight's (likely Mission 31's test instance).
  - **Checkpoint review before dispatch 3 (Sonnet:** CI workflow surface, scarce dispatches).

- **Leg 6 checkpoint review (Sonnet): `[HANDOFF:confirmed]` with one required change.** The per-step caps sum to about 79 min (with the evidence steps) against a 50-min job, so a job-timeout cancellation could lose the evidence.
  - **The fix:** a 60-min job; tightened early caps; `M32_T0` recorded; a dynamic lifecycle bound that always leaves 7 min for the evidence steps (`FAIL L0 no time left` if under 300 s); lifecycle `BUDGET` 850 s.
  - **Optional fixes taken:** the final check requires `checks.sh`'s end marker; the `checks.sh` `.dmg`-exists `$?` bug; the audit cap 420 s.
  - **Cost:** the worst case rises from 50 to 60 min; the typical run (about 15 min) is unchanged.
  - **Noted for the debrief (not fixed):** `render.load()` now always derives the bundle versions, so a non-`X.Y.Z[.devN]` version (for example `1.0`) fails every render, Linux and Windows included. Harmless for `0.11.x`; Flight 4's dynamic version should know it.
- **Leg 7 (`macos-hosted-checks`) risk tier: LOW** for its spec: a dispatch, evidence reading, fixes and docs. Any product fix it needs is reviewed at flight end. No design review. Status `ready`.

- **Leg 6 review fixes applied** (a 60-min job; caps summing to 42 min before lifecycle; the dynamic bound; the `L0` no-time path rehearsed; `BUDGET` 850; the `== A done` guard; the `.dmg` `$?` fix; the audit at 420 s). No re-review: the Reviewer's own items. Leg 6 `completed`, committed as checkpoint 4.
- **Dispatch 3 of 5:** `mode=lifecycle` (leg 7, step 1).

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

### macos-dock-mode

**Phase A checkpoint** (leg 4; status `in-flight`; Phase B waits for leg 3b's evidence on the delegate route and the reply mechanism). Uncommitted.

**Built**
- `the_one/interfaces/desktop/macos_dock.py` (new; no top-level AppKit/objc import, verified by a subprocess test): `DockView` (frozen: `really_quit, booting, has_window, terminate_pending, has_server, native_window`), `snapshot(state, *, native_window=False)`, `on_close(view)`, `on_reopen(view)`, `on_terminate(view)`, `terminate_reply_code(decision)` (`reply-now` -> 1 `NSTerminateNow`; the other two -> 2 `NSTerminateLater`), constants `NS_TERMINATE_NOW/LATER/CANCEL`, `BOOT_WAIT_BOUND = 5.0`.
- `TerminateWorker(reply, drain, boot_wait, log_flush, clock=time.monotonic, sleep=time.sleep, boot_bound=5.0)` with `.run()` and `.start()` (one daemon thread). Order: `boot_wait(5.0)` (timeout only warns), `drain()` (exceptions logged, never block the reply), log "terminate: reply sending", `log_flush()`, `reply()` (one retry after `sleep(0.5)`). Never reads geometry, never takes `state.lock`. `flush_log_handlers()` flushes (never closes) root + shell logger handlers: pass it as `log_flush`.
- AppKit seams (lazy imports inside each): `_call_after(fn, *args)`, `_nsapp()`, `_native_window(window)` (= `window.native`, which is the `NSWindow` in pywebview 5.4), `terminate_app()`, `reply_to_terminate(ok=True)`, `activate(window)`, `native_visible(window) -> bool | None`. **`install` is not written** (Phase B). `reply_to_terminate` uses `_call_after` (`AppHelper.callAfter`); Phase B swaps in the `performSelectorOnMainThread...` fallback if 3b says callAfter replies are not delivered.
- `session_state.py`: `begin_quit()` (sets `really_quit` + `quit_requested`; returns the published window ONLY on the first call, else None, so geometry is saved once), `terminate_pending` + `mark_terminate_pending() -> bool`, `loop_stopped`; both cleared by `reset()`.
- `window_control.py`: darwin `quit_desktop` (`loop_stopped` -> "window" with nothing more; "already" -> "window", no second terminate; tags "window"/"booting" -> `macos_dock.terminate_app()`, which raising returns None; "browser"/None unchanged), darwin `focus_window` -> `macos_dock.activate`, darwin `window_visible` -> `macos_dock.native_visible`. `macos_dock` is imported at module top, because `tests/test_desktop_shell.py::test_close_path_functions_have_no_imports` (DD12) forbids lazy imports in `quit_desktop`.

**Tests**: `tests/test_macos_dock.py` (decision truth tables over all 64 views plus named cases; snapshot; worker order, boot bound/takeover bound, boot timeout, drain raising, reply retry, no lock held, daemon thread, flush without close; `begin_quit`, `mark_terminate_pending`, `reset`; darwin `quit_desktop` per tag incl. already/loop_stopped/failure; `focus_window`; `window_visible`; chrome register/deregister unchanged; `activate` main-thread dispatch; `native_visible` direct/fallback/None/timeout; `terminate_app`/`reply_to_terminate`; no AppKit import) and `tests/test_pywebview_cocoa_canary.py` (7 `ast` facts: AppDelegate has `applicationShouldTerminate_` and no reopen method; `windowShouldClose_` -> `should_close` -> `events.closing.set`; `windowWillClose_` calls `app.stop_` + `abortModal`, posts no event; `keyDown_` `'q'` -> `app.stop_`; `_add_app_menu` `terminate:`/`q`; `BrowserView.__init__` calls `AppDelegate.alloc`; `restore` calls `deminiaturize_` directly). The worker's `drain` is not yet wired to `_graceful_shutdown`.

**Results**: `make test-unit` 7325 passed, 12 skipped; `ruff check` and `ruff format --check` clean; split guard passes. (One first-run failure, the DD12 no-lazy-import test, was fixed by the top-level import above.) No existing test needed inverting.

**Phase B must know**
- The delegate callback does, on the main thread: `view = macos_dock.snapshot(state, native_window=...)`; `d = on_terminate(view)`; for `drain-then-reply`: `mark_terminate_pending()`, `win = state.begin_quit()`, save geometry from `win` (direct `frame()` read) if a window was published, build `TerminateWorker(reply=reply_to_terminate, drain=lambda: _graceful_shutdown(state.server, state.thread), boot_wait=state.boot_stopped.wait, log_flush=flush_log_handlers).start()`, return 2. `already-pending` returns 2; `reply-now` returns 1. Return values use the runtime's `I@:@`, not `NSUInteger`.
- `snapshot` reads `state.server`, which `run()` must now set (and clear at exit); `state.tray_mode = "dock"` must be assigned at the top of `run()`.
- `begin_quit()` returns None on a repeat, so path S after path T does not save geometry twice.

**AC5 observable table (for leg 7's `lifecycle.sh`)**: log lines `terminate: drain started`, `terminate: drain done in <s>s`, `terminate: reply sending`, `terminate: boot did not stop within 5.0s` (warning); the install-route line and the terminate-received / path-S-exiting lines are Phase B's. State-route fields: `tray: "dock"` (Phase B), `visible` (real `isVisible`), `mode`, `pid`.

**Phase B gate quote (leg 3b, `### macos-probe-rerun`, run `40206047338`)**, read before any Phase B code:
- Route installed: `subclass` (`selftest ok route=subclass`; `[BLOCKED:delegate-unextendable]` does not apply). So `install` replaces `BrowserView.AppDelegate` with a subclass, not `classAddMethods`.
- Logged signatures: `terminate=b'I@:@' (superclass) reopen=b'B@:@B' (protocol) willTerminate=b'v@:@' (protocol)`. `applicationShouldTerminate_` and `applicationWillTerminate_` are plain methods (no explicit signature, inherited prototype); reopen is wrapped in `objc.selector(..., signature=<protocol encoding, offsets stripped>)`.
- Counts: terminate=1, reply=1, willTerminate=1 event (the SUMMARY's 2 is a double grep match).
- `callAfter` reply delivered during the NSTerminateLater wait: YES, for both the quit Apple event and Cmd-Q (path T observed directly). The `NSRunLoopCommonModes` fallback is not used; `reply_to_terminate` keeps `AppHelper.callAfter`.

**Phase B checkpoint** (leg 4; status `landed`). Uncommitted.

**Wired**
- `shell.py`: darwin sets `state.tray_mode = "dock"` right after `state.reset()`; `macos_dock.install(self)` just before `webview.start`; no tray (step 5 raises `_NoTrayError` on darwin, pystray never imported); `_on_closing` dock branch (`_dock_hide`: `on_close` + `window.hide()`, no notice, failed hide allows); `_destroy_splash` suppression; `_boot` sets `boot_stopped` in a `finally` (every exit, all platforms); on darwin `_abort_if_quit` and the step-6 quit return without publishing/destroying, and an unhandled boot error calls `macos_dock.terminate_app()` once unless `terminate_pending`; path S (`_path_s_begin` after `webview.start`, the existing `finally` drain, then `_path_s_exit`: 5 s wait on `boot_stopped`, flush, `os._exit(0)`); `finally` clears `state.server`/`state.thread`; `platform_env.prime_login_shell_path()` after `state.begin_boot()` (after the `is_ours` return); `DesktopSession._drain` (the worker's drain, wraps `_graceful_shutdown`).
- `macos_dock.py`: `handle_terminate` / `_start_terminate` / `handle_reopen`, `order_out`, `_reopen_signature`/`_protocol_signature`, `_install_delegate` (subclass `GleepGlorpAppDelegate`, plain `applicationShouldTerminate_`/`applicationWillTerminate_`, reopen via `objc.selector` with the protocol encoding; failure leaves the stock delegate, route `none`), `_begin_activity`, `install` (once; token in module-level `_ACTIVITY_TOKEN`). `_install_delegate` and `_begin_activity` are the only unit-untestable bodies (`# pragma: no cover`, need AppKit); they are exercised by leg 7's hosted run.
- Docs: `the_one/agents.md` "macOS dock mode (M32 F3 L04, DD2-DD5)" paragraph (after the L01 module-map paragraph), one `CLAUDE.md` sentence in the Desktop launcher section.

**One deliberate deviation from the leg text**: `_destroy_splash` is NOT suppressed on `boot_stopped` alone. `_boot` sets `boot_stopped` on every exit including a successful one, and the page's `loaded` handler dismisses the splash after that, so literal suppression would leave the splash up forever. Suppression is `terminate_pending or really_quit or loop_stopped or a boot error` (darwin only); every quit path sets one of the first two (`begin_quit`), and the error path sets a local event. Tested (a normal darwin boot still destroys the splash).

**Tests** (`tests/test_macos_dock_shell.py`, 33 with the Phase A file's neighbours unchanged): `test_dock_tray_mode_and_install_precede_webview_start`, `test_no_pystray_on_darwin_boot`, `test_prime_called_once_after_begin_boot`, `test_prime_not_called_on_the_is_ours_branch`, `test_server_and_thread_cleared_after_run`, `test_path_s_ordered_sequence` (install, start returns, order_out, save, drain, flush, exit(0)), `test_path_s_with_only_the_splash_saves_nothing`, `test_path_s_waits_on_boot_stopped_before_exit`, the five `test_dock_*close*` tests, `test_splash_destroy_is_suppressed_by_each_flag[terminate_pending|really_quit|loop_stopped]`, `test_splash_still_destroyed_on_a_normal_darwin_boot`, `test_boot_abort_on_darwin_sets_boot_stopped_and_destroys_nothing`, `test_boot_error_on_darwin_calls_terminate_once`, `test_boot_error_with_terminate_pending_does_not_terminate_again`, `test_install_*` (token stored at module level, runs once and logs the route, survives an activity failure), `test_handle_terminate_*` (drain and LATER, repeat starts one worker, window client NOW, unpublished window skips the save, never raises), `test_handle_reopen_*`, `test_reopen_signature_*`, `test_a_dock_close_state_route_reports_dock`. The canary and the Phase A tests are unchanged. No existing test was inverted or modified.

**Gates**: `make test-unit` 7358 passed, 12 skipped; `ruff check` and `ruff format --check` (the_one tests scripts evals) clean; split guard passes. `settings` lane (`THE_ONE_TEST_NETNS=1`): 108 passed in 236 s. Linux build `0.11.9.dev32` (`M32_BUILD=$HOME/the-one-m32-build/f3`) then `gtk-smoke.sh ubuntu-26.04 --deb ...dev32_amd64.deb`: **`OVERALL PASS`** (evidence `$HOME/the-one-m32-evidence/f3/leg4/`: `build.log`, `smoke.log`). No containers or root-owned files left.

**AC5 observable table** (logger `the_one.interfaces.desktop.shell`, in `~/Library/Logs/...`/the app log; state route = `GET /api/window/state`):

| lifecycle step | log line (exact text) | state-route field |
|---|---|---|
| launch (install) | `macos dock: delegate installed (route=subclass, app nap activity held)` | `tray: "dock"`, `mode`, `pid` |
| window closed (red button / Cmd-W on main) | `dock: window hidden on close` | `visible: false` (real `NSWindow.isVisible`), process alive |
| Dock icon / `open -a` | `reopen: decision=show hasVisibleWindows=<bool>` (`decision=defer` while booting, `ignore` while quitting) | `visible: true` |
| second launch | focus POST handled (existing focus path), `reopen:` as above when AppKit forwards it | `visible: true`, same `pid` |
| any path-T quit (menu/Dock Quit, Apple event, logout, Cmd-Q, `the-one quit`, `POST /api/window/quit`, takeover) | `terminate: applicationShouldTerminate received (decision=drain-then-reply)` | (server then drains) |
| drain | `terminate: drain started` then `terminate: drain done in <s>s` (uvicorn's `Shutting down` / `Finished server process` lines in stderr) | route unreachable afterwards |
| reply | `terminate: reply sending`, then `terminate: applicationWillTerminate (AppKit exiting)` | process gone |
| boot did not stop in time | `terminate: boot did not stop within 5.0s` (warning) | - |
| repeat terminate | `terminate: applicationShouldTerminate received (decision=already-pending)` | - |
| window-only client quit | `... (decision=reply-now)` | - |
| path S (Cmd-W on splash alone) | `path S: webview.start returned — draining`, drain lines from uvicorn, `path S: exiting (os._exit(0))` | gone |
| boot stuck on path S | `path S: boot did not stop within 5.0s` (warning) before the exit line | gone |

**Leg 6/7 must know**
- Nothing here has run on a Mac: `_install_delegate`'s class body and `_begin_activity` are unverified until leg 7. Their failure modes are logged (`macos dock: delegate install failed — stock delegate` -> route `none`; then Cmd-Q takes path S, the red button still hides). Leg 7's `lifecycle.sh` should assert the `route=subclass` line first.
- `quit_desktop` on darwin sends every non-None tag, `"booting"` included, through `terminate_app()`; the quit route's JSON still says `state: "window"` (or `"booting"`).
- The launch can take up to 5 s longer before the splash on a frozen macOS build (`prime_login_shell_path`).
- Dock-mode `Window` state: `tracked_visible` is not used on darwin; `window_visible` reads the native window.

### macos-recipe

**Phase A checkpoint (leg 6, Developer).** Leg status is `in-flight`; Phase B (workflow `full`/`lifecycle`, `lifecycle.sh`, `lib.sh`, `checks.sh`, rehearsal) follows. Uncommitted.

- **Built.**
  - `packaging/product.toml`: top-level `app_id`, `[linux] metainfo_id` removed, `[macos]` (`bundle_name`, `bundle_executable`, `dmg_file_stem`, `min_os = "14.0"`, `bundle_category`).
  - `render.py`: `load()` rejects a key repeated across sections or between a section and the top level, and a derived name in the TOML; derives `bundle_short_version` and `bundle_version` (refuses `a`/`b`/`rc`/`.postN`, two-part versions, dev >= 9999); `next_version()` and `render.py --next-version V` (`0.11.8` -> `0.11.9.dev1`, `.devN` -> `.devN+1`; `--repo` is not needed for it).
  - Linux key rename `METAINFO_ID` -> `APP_ID` in `build.env.in`, `metainfo.xml.in`, `build-inner.sh`.
  - `macos/info_plist.py` (pure; exactly the ten keys of the leg); `the-one.spec` reads `M32_PRODUCT_JSON` (name, id, short version, `info_plist(PRODUCT)`, executable name), pystray fully removed, docstring updated.
  - `macos/build.sh`: `[--version X] [--from-head]` (positional warns), writes `macos-<v>/build.env` (shell-quoted `VERSION APP_ID APP DMG`; **source it**, `APP` has a space) and `product.json`, `SOURCE_DATE_EPOCH` from the last commit, no `checks.sh`, `M32_SKIP_DMG` (alias `M32_SKIP_CHECKS`), `M32_REUSE_VENV`, `.dmg` from `dmg-root/` (`ditto` of the .app + `Applications` symlink, `-fs HFS+ -format UDZO`, one retry, failure is now fatal).
  - `macos/frozen_entry_mac.py`: `redirect_app_log()` (app command + non-TTY stderr -> `~/Library/Logs/GleepGlorp AI/app.log`, append, line-buffered, truncate if > 10 MB, failure -> None) and `_install_log()` (dup2 of fds 1/2 plus `sys.stdout/stderr`); `launch_args()` unchanged.
  - `macos/audit.py` (`APP (--min-os V | --product-json F) [--report-only]`; lipo/otool; fat files listed not failed; dylib own install name excluded from the load-path check; missing minos reported as unknown). `macos/README.md` updated.
- **Linux no-change proof.** Old tree = `git archive e21d219`, rendered with `--set version=0.11.9.dev33 --set release_date=2023-11-14` for `build.env`, `AppRun`, `control`, `deb.desktop`, `metainfo.xml`, the AppImage integration `.desktop.in` and the root `.desktop`. The only diff is `-METAINFO_ID=ai.gleepglorp.GleepGlorpAI` / `+APP_ID=ai.gleepglorp.GleepGlorpAI` in `build.env` (evidence: `~/the-one-m32-evidence/f3/leg6/linux-nochange.diff`).
- **Linux build.** `M32_BUILD=$HOME/the-one-m32-build/f3 packaging/linux/build.sh --version 0.11.9.dev33` (the leg said dev31; dev33 was asked for): `.deb` + AppImage built; in-build bundle audit `1027 files, max GLIBC_2.34 (limit 2.39), 0 problem(s): PASS`; the `.deb` carries `usr/share/metainfo/ai.gleepglorp.GleepGlorpAI.metainfo.xml`.
- **Spec Analysis on Linux.** The real spec ran through PyInstaller 6.22.3 against the staged copy (rc 0, `BUNDLE` a no-op on Linux but its arguments, `info_plist(PRODUCT)` included, are evaluated). A pystray WARNING in that log is the contrib stdhook reaching pystray through the app's own imports, not the spec.
- **build.sh rehearsal.** With a fake venv (`pyinstaller` that makes the .app tree), and shims for `codesign`/`ditto`/`hdiutil`: full run rc 0, `build.env` sources correctly, the spec env gets `M32_PRODUCT_JSON`, the dmg root holds `GleepGlorp AI.app` + `Applications -> /Applications`; `M32_SKIP_CHECKS=1` + positional version skips the dmg; unknown option rc 2.
- **Tests.** `tests/test_packaging_metadata.py` (REQUIRED updated; `app_id`, `[macos]` keys, collisions, derived-key rejection, mapping vs PEP 440 order, refusals, `next_version` + CLI round trip, metainfo id) and new `tests/test_packaging_macos_audit.py` (canned otool/lipo: pass, bad load path, no arm64, minos too high, unknown minos, legacy min, tool failure, exit codes, `--product-json`; `info_plist` keys and values; spec has no pystray; the log redirect: TTY, other command, append, truncation, failure fallback, folder name == `bundle_name`). 59 pass.
- **Gates.** ruff check + format clean on `the_one/ tests/ scripts/ evals/ packaging/`; shellcheck 0.10.0 clean on `build.sh` and `build-inner.sh`; `bash -n` on `packaging/macos/*.sh`; `make test-unit`: 7399 passed, 12 skipped.
- **Phase B must know.**
  - `build.sh` no longer calls `checks.sh`, so the current workflow's `full` mode has no checks until Phase B rewires it (expected). The workflow still passes the positional version and the old probe bundle id `ai.gleepglorp.the-one`; both need updating (`APP_ID` is in `build.env`).
  - `checks.sh` still has the old best-effort `open` block and an `$EXE` argument; the app/exe names should come from `build.env`/`product.json`.
  - `audit.py` is not yet called anywhere; first hosted run uses `--report-only`.
  - The Info.plist/bundle id changed to `ai.gleepglorp.GleepGlorpAI`, so the data-dir/log path expectations in `lifecycle.sh` use `~/Library/Logs/GleepGlorp AI/app.log`.
  - Scratch: `$HOME/the-one-m32-build/f3/b-rehearse` (build.sh rehearsal kit: `venv-pyi/bin/{python,pyinstaller}`, `shims/`).

**Phase B checkpoint (leg 6, Developer).** Leg status `landed`. Uncommitted. Evidence: `~/the-one-m32-evidence/f3/leg6/` (`rehearsal-lifecycle-*`, `rehearsal-workflow-*`, `rehearsal-probe-after-factoring-ok`, `rehearse6-scripts/` = the whole rehearsal kit, `test-unit.out`).

**Leg 4's AC5 observable table, quoted** (the exact text `lifecycle.sh` asserts; logger `the_one.interfaces.desktop.shell` in `~/Library/Logs/GleepGlorp AI/app.log`; state route = `GET /api/window/state`):

| lifecycle step | log line (exact text) | state-route field |
|---|---|---|
| launch (install) | `macos dock: delegate installed (route=subclass, app nap activity held)` | `tray: "dock"`, `mode`, `pid` |
| window closed (red button / Cmd-W on main) | `dock: window hidden on close` | `visible: false` (real `NSWindow.isVisible`), process alive |
| Dock icon / `open -a` | `reopen: decision=show hasVisibleWindows=<bool>` (`decision=defer` while booting, `ignore` while quitting) | `visible: true` |
| second launch | focus POST handled (existing focus path), `reopen:` as above when AppKit forwards it | `visible: true`, same `pid` |
| any path-T quit (menu/Dock Quit, Apple event, logout, Cmd-Q, `the-one quit`, `POST /api/window/quit`, takeover) | `terminate: applicationShouldTerminate received (decision=drain-then-reply)` | (server then drains) |
| drain | `terminate: drain started` then `terminate: drain done in <s>s` (uvicorn's `Shutting down` / `Finished server process` lines in stderr) | route unreachable afterwards |
| reply | `terminate: reply sending`, then `terminate: applicationWillTerminate (AppKit exiting)` | process gone |
| boot did not stop in time | `terminate: boot did not stop within 5.0s` (warning) | - |
| repeat terminate | `terminate: applicationShouldTerminate received (decision=already-pending)` | - |
| window-only client quit | `... (decision=reply-now)` | - |
| path S (Cmd-W on splash alone) | `path S: webview.start returned — draining`, drain lines from uvicorn, `path S: exiting (os._exit(0))` | gone |
| boot stuck on path S | `path S: boot did not stop within 5.0s` (warning) before the exit line | gone |

`lifecycle.sh` asserts the `route=subclass` install line FIRST (L1), then the rows it uses: install, `dock: window hidden on close`, `reopen: decision=show`, and for each quit the four lines received, `drain started`, `drain done in`, `reply sending` in that order (`applicationWillTerminate` is recorded, not required).

**Built (Phase B)**
- `packaging/macos/lib.sh` (new): `tl now fsub sleep_s wait_until track alive pids_for stop_all stop_pid listener runrc rcnote cred cred_prefix http http_post shot front_pid front_note gate_wait window_state new_pid wait_exit`, moved out of `probe/probe.sh` (which now sources it; behaviour unchanged, see the re-run below).
- `packaging/macos/lifecycle.sh` (new, `lifecycle.sh APP_N APP_N1 APP_ID VERSION_N VERSION_N1 OUT_DIR`): installs N by `ditto` into `$M32_INSTALL_DIR` (default `/Applications`), runs L1-L10 as `--run` children each under its own cap, writes one `PASS|FAIL <id> <title>: [ok: ...] [BAD: ...]` row per step (+ `INFO L3i` for Cmd-W) and `== done`. Log read by byte offset; apps by path (`open -a`); System Events by `first process whose unix id is <pid>`; pids from `/api/window/state`; every call through `tl`. A step that finds no app running starts one (evidence says so). Parameters: `M32_PRODUCT_PORT` (non-default makes `open --env THE_ONE_PORT/THE_ONE_DATA_DIR` and the CLI env carry it), `M32_DATA_DIR`, `M32_APP_LOG`, `M32_CRASH_DIR`, `M32_INSTALL_DIR`, `M32_BUDGET` (1000), `M32_CAP_Ln`, `M32_SCALE`, `M32_STOP_WAIT`.
- `packaging/macos/checks.sh`: old `open` block removed; strict doctor greps (`desktop shell: OK — Cocoa backend present`, `tray: dock`, `^ *path: `); bundle audit (`M32_AUDIT_ARGS`, default `--report-only`, note = the `audit:` summary line); `.dmg` layout (`hdiutil attach -readonly -nobrowse -noverify -noautoopen -mountpoint`, `GleepGlorp AI.app` + `Applications` -> `/Applications`, detached in an EXIT trap with a `-force` retry). `M32_DMG` / `M32_PRODUCT_JSON` come from the workflow (the bundle name and executable name from `product.json`).
- `.github/workflows/macos-packages.yml` (`on:` byte-identical to `probe/macos-packages.stub.yml`, checked by `diff`; `actionlint 1.7.7` with shellcheck 0.10.0 clean): `inputs.mode` goes through `env` (not inlined), an unknown mode fails in Paths.
- `packaging/macos/README.md`, `probe/README.md`, `probe.sh` header: the new files, modes, step table, bounds and the estimate.

**Workflow mode map**

| step | full | lifecycle | probe |
|---|---|---|---|
| Build (`build.sh --version $M32_VERSION`, `continue-on-error`, id `build`; exports `M32_DMG` from `build.env`) | yes | yes | - |
| Build the product app (`M32_SKIP_CHECKS=1 M32_SKIP_DMG=1`, id `build_probe`) | - | - | yes |
| Checks (`checks.sh A ...`, `!cancelled()`, `M32_AUDIT_ARGS=--report-only`; writes a `FAIL checks:` line itself when there is no `.app`) | yes | yes | - |
| Build N+1 (`M32_REUSE_VENV=1 M32_SKIP_DMG=1`, version from `render.py --next-version`, logs in `logs/n1/`) | - | yes, only if the N build succeeded | - |
| Lifecycle (`lifecycle.sh` under `perl alarm 1200`, `!cancelled()`, never fails the step; writes `FAIL L0` itself when a bundle is missing) | - | yes, even after a checks failure | - |
| Freeze probe app, selftest, Premise probe (`probe.sh "$APP" ... "$APP_ID"` from `build.env`) | - | - | yes |
| Summary (`A/`, `lifecycle/`, `probe/`), log upload, `.dmg` upload (`macos-dmg`, 7 days, `if env.M32_DMG != ''`), final check (anchored `^FAIL`; fails on a non-success build / N+1 build outcome; fails in lifecycle mode when `lifecycle/SUMMARY.txt` is missing) | yes | yes | yes (no `.dmg`) |

**Bound table and worst case**

| step | cap (s) | | step | cap (s) |
|---|---|---|---|---|
| install (`ditto`) | 120 | | L6 quit Apple event | 130 |
| L1 launch | 80 | | L7 `quit --wait` | 120 |
| L2 close | 50 | | L8 Cmd-Q | 130 |
| L3 reopen | 70 | | L9 upgrade | 190 |
| L4 second launch | 50 | | L10 trash | 70 |
| L5 geometry | 200 | | | |

Sum with the install: 1210 s, but a step is skipped once 1000 s have passed, so with every cap firing the run ends after L9 at about 1140 s plus the final stop (about 19-20 min), under the 1200 s outer bound (the cap trap runs after the current foreground call, at most one inner bound later, so the outer bound is the backstop). Estimated job (no hosted lifecycle run exists yet): **typical about 15 min** (setup and N build with `.dmg` 3, checks 3, N+1 build 1, lifecycle 5-8, uploads 1); **plausible worst case about 40 min** (every non-lifecycle step at 2x typical: 8 + 6 + 3 + 2, plus lifecycle at its 19-minute bound), under the 50 min job. The sum of every step's own `timeout-minutes` is 71 (3+1+2+4+1+6+12+12+8+22), so a run in which several steps hit their own caps would be cut by the job timeout; that run has already failed, and the `always()` steps upload what exists. The probe runs measured 4.5 and 5.25 min for a whole job including the build, so the 2x figure is generous for setup and N build.

**Rehearsal by execution (Linux)** — `rehearse6` kit: a fake product exe (Python server answering `/api/live`, `/api/window/state`, `/api/info`, the quit/focus routes, providers/agents/sessions, writing leg 4's log lines to a fake `~/Library/Logs/GleepGlorp AI/app.log`, honouring `window-state.json`, refusing 8484/8485) and shims for `open`, `osascript`, `lsappinfo`, `screencapture`, `ditto`, `hdiutil` (a tar of the source folder, so attach rebuilds the layout), `codesign`, `otool`, `lipo`, `python3 -m pip|venv`, `uv`, `sysctl`, `df`. Ports 18490-18497 only. SUMMARY tails:
- **all pass** (`rehearsal-lifecycle-ok`, 32 s): `== done in 32 s: 12 PASS, 0 FAIL`; e.g. `PASS L6 quit Apple event drains, then exits: [ok: app running] [ok: only the installed copy runs ...] [ok: quit Apple event (rc=0)] [ok: exited within 70 s (1.1 s)] [ok: log: received, drain started, drain done, reply sending, in order] ...`.
- **one expectation fails** (`fail`: geometry not restored, 31 s): `FAIL L5 ... [BAD: size within 2 px (716x537 -> 1024x743)] [BAD: position within 40 px ...]`, `== done in 31 s: 11 PASS, 1 FAIL`; the script continued through L10. Also `crash` (a `.ips` after the Apple-event quit): `FAIL L6 ... [BAD: no new crash report (...the-one-....ips )]`.
- **`osascript` hang** (`hang`: every System Events call sleeps 100 s, 330 s): `[BAD: close button AXPress (rc=142 (bound fired))]` in L2, `[BAD: set position and size (rc=142 (bound fired))]` and `[BAD: Cmd-Q keystroke (rc=142 (bound fired))]` in L5, L8 likewise; `== done in 330 s: 9 PASS, 3 FAIL`; no process or listener left. A cap firing is shown by `capfire` (`M32_CAP_L5=2`): `FAIL L5 step cap of 2 s reached; partial evidence in ...`, the next step restarts the app, `11 PASS, 1 FAIL`.
- **`open -n` returns a second listening pid** (`second`, SO_REUSEPORT): `FAIL L4 ... [BAD: second process 1396075 exited (still alive)] [BAD: one listener on 18492, the first process (during: 1395479 1396075; after: 1395479 1396075)]` (L6 then fails as collateral: the listener that answers is the second process).
- **drain lines missing** (`nodrain`, no log lines on the Apple-event quit): `FAIL L6 ... [BAD: log: received, drain started, drain done, reply sending, in order (missing: terminate: applicationShouldTerminate received (decision=drain-then-reply))] [applicationWillTerminate not logged]`, `11 PASS, 1 FAIL`.
- Each scenario ended `leftover processes: none`, `listeners: none`.
- **Workflow steps extracted and run** (`wf6.py`: `bash --noprofile --norc -eo pipefail` per `run:` step, `if:`/`continue-on-error`/`steps.*.outcome` evaluated, fake `RUNNER_TEMP`, the real `build.sh`, `checks.sh`, `lifecycle.sh`, `probe.sh`): `full` (checks `0 hard check(s) failed`; audit with `--report-only` prints `audit (--report-only): audit: 4 Mach-O files, 1 fat (universal), ... 1 problem(s)` and `PASS bundle audit` because it is report-only; `.dmg` layout 4 PASS; final check rc 0; both uploads would find their paths), `lifecycle` (N+1 version `0.11.9.dev41` from `--next-version`; 12 PASS; final check rc 0), `lifecycle` with `hdiutil attach` failing (checks `FAIL dmg attaches read-only`, lifecycle **still ran** 12 PASS, final check rc 1), `lifecycle` with the geometry failure (final check rc 1 listing the `FAIL L5` row), `lifecycle` with a failing freeze (checks write `FAIL checks: the .app is missing`, N+1 skipped, lifecycle writes `FAIL L0 an app bundle is missing`, final rc 1), `probe` (selftest, premise probe passes `bundle_id=ai.gleepglorp.GleepGlorpAI` from `build.env`, no `.dmg`, no `quiescence` rows, final rc 0). "Runner evidence" runs on Linux through `sysctl`/`df`/`xcodebuild`/`system_profiler` shims.
- **probe.sh unchanged after the lib.sh factoring:** the "all shims succeed" rehearsal re-run (`rehearsal-probe-after-factoring-ok`, `driver rc=0 in 42 s`, no leftovers) against leg 3b's last `rehearsal-ok` SUMMARY: identical rows after normalising numbers and paths; the single difference is a timing mark (`+cut not-live` in 3b's cold series vs `live` now, the scaled-cap artefact leg 3b already recorded).
- Bugs the rehearsal found in `lifecycle.sh` (fixed): `chk "..." $?` read after a command substitution in the label (four sites, now `rc=$?` first); `ensure_app` did not wait for the window after a launch; the exit time printed without a unit. Found by reading: `cli_env` running the shell function `tl` under `env` (replaced by `cli_run`, which puts `env` inside `tl`).

**Checks.** `shellcheck 0.10.0 -x` clean on `lifecycle.sh lib.sh checks.sh build.sh probe/probe.sh`; `bash -n` under bash 3.2.57 (`bash:3.2` image, read-only mount; removed with `docker rmi`, no `m32-*` container left) for the same five; grep for `mapfile|readarray|${x,,}|declare -A|local -n|[[ =~|&>>|\|&` finds only comments (no arrays, no `[[`); `actionlint 1.7.7 -shellcheck` clean; `on:` block equals the stub; `ruff check` and `ruff format --check` (`packaging/ the_one/ tests/ scripts/ evals/`) clean; `make test-unit`: **7399 passed, 12 skipped** (384 s, `test-unit.out`).

**Leg 7 (the hosted run) must know**
- Nothing here has run on a Mac. Unproven until dispatch: System Events `click button 1 of window 1` as the close driver, `tell application id "ai.gleepglorp.GleepGlorpAI" to quit` reaching the `/Applications` copy (the build-directory copies are only asserted not to run), the JXA screen-size read, `lsappinfo front` after `open -a`, `lsof` listeners, `hdiutil attach -mountpoint` flags, `system_profiler` in "Runner evidence" (wrapped in `|| true`), and the two `_install_delegate`/`_begin_activity` bodies from leg 4. If L1's `route=subclass` row is BAD, read it first.
- The `--report-only` audit passes whatever it finds: read `A/audit.txt` and flip `M32_AUDIT_ARGS` (workflow, Checks step; set it to the empty string to enforce) once the report is clean.
- Dispatch with `-f mode=lifecycle -f version=<dev version>`: N is that version, N+1 is `render.py --next-version` of it. A dispatch with no version input uses `__version__` (a final `0.11.8` gives N+1 `0.11.9.dev1`, which `CFBundleVersion`-sorts above it).
- `lifecycle.sh` needs the credential file to exist before L1: it is created by `checks.sh` gate 4 (`rotate-api-credential` on the default data dir); the lifecycle header and L9 record that. If the checks step is skipped or dies earlier, the state-route reads in L1 return 401 and every step fails honestly.
- Geometry (L5) compares System Events' frame to System Events' frame (size +-2 px, position +-40 px); `window-state.json` is only asserted to exist and to have changed. The screen is read first; the target frame is 70% of it.
- First-paint PNGs at +1, +3 and +5 s are in `lifecycle/L1/`; `lifecycle/app.log` is the whole log; each quit step keeps its segment (`quit-event.log`, `quit-cli.log`, `cmd-q.log`).
- The `.dmg` artifact is `macos-dmg` (7 days). The N+1 build is never uploaded.

**Review fixes (leg 6).** Timeout layering reworked: job 60 min; step caps checkout 2, Paths 1, Runner evidence 2, setup-python 3, versions 1, export 5, build 12, checks 10, N+1 build 6 (42 min before lifecycle), Lifecycle 21 (bound `B = min(1200, 3600 - elapsed - 420)` s from `M32_T0` recorded in the Paths step; `B < 300` writes `FAIL L0 no time left` and skips), Summary 1, log upload 3, .dmg upload 2, final check 1 (7 min after). `lifecycle.sh` gets `M32_BUDGET=B-200` (default lowered 1000 to 850). Worst case: 42 min + B 660 s + 7 min = 60 min, so at least 7 min remain for the evidence steps in every path. Also: the final check requires the `== A done` line in `A/SUMMARY.txt`; `checks.sh` dmg-exists capture no longer reads the `$(basename)` status (and clears SC2319); `audit.py` cap 300 to 420 s. Verified: actionlint 1.7.7 clean, shellcheck 0.10.0 clean at `-S error`, `bash -n`, `on:` block identical to the stub, workflow rehearsals in lifecycle mode (all pass: 12 PASS, final check rc 0), `late` scenario (`M32_T0` 3400 s back: `FAIL L0 no time left`, Summary/upload/final check ran, final check red), and full mode.


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

- **AC3 (evidence reading)** (Developer, no code change, commit or dispatch). Run `40206047338` (dispatch 2 of 5; `macos-packages.yml`, `mode=probe`, commit `c2db6f1`; run 15:15:08Z to 15:20:27Z; every step green including "Probe app selftest", `selftest ok route=subclass`). Evidence: `~/the-one-m32-evidence/f3/leg3b/run-40206047338/` (artifact), `run-40206047338/run.log` (`gh run view --log`), `sha256.txt` beside it (one line per file, 198 lines). Paths below are relative to `run-40206047338/macos-packages-logs/`; `probe/` = the probe evidence. Runner: macOS 15.7.9, arm64 (`runner.txt`). The probe's own logs are `probe/P*/…-probe.log`; the premise step ended `== done in 234 s` (`probe-step.log`).

  **Answers (the leg-4 gate is items 1, 2, 3):**

  1. **Route and signatures: `subclass` installed.** `probe-selftest.txt`: `resolved signatures: terminate=b'I@:@' (superclass) reopen=b'B@:@B' (protocol) willTerminate=b'v@:@' (protocol)`; `signature subclass applicationShouldTerminate_=b'I@:@'`; `signature subclass applicationWillTerminate_=b'v@:@'`; `signature subclass applicationShouldHandleReopen_hasVisibleWindows_=b'B@:@B'`; `signature superclass applicationShouldTerminate_=b'I@:@'`; `route: subclass`; `pywebview=? pyobjc=12.2`; `selftest ok route=subclass`. Sources: terminate = superclass (the plain method with no explicit signature inherits `I@:@`), reopen and willTerminate = the `NSApplicationDelegate` protocol (the reopen selector is not on pywebview's delegate). The delegate in effect: `NSApp.delegate().className() at shown = M32ProbeAppDelegate` (`probe/P2/probe-probe.log`, line 11; identical in P3/P4). `classAddMethods` was not needed and not exercised. **Not blocked: `[BLOCKED:delegate-unextendable]` does not apply.**
  2. **`NSTerminateLater` plus the deferred reply: it terminated, both ways. callAfter reply delivered: YES.** The reply is `AppHelper.callAfter(app.replyToApplicationShouldTerminate_, True)` from a `terminate-worker` thread after a 3 s sleep (`delegate_probe.py` line 80), so the reply crossed from a non-main thread through `callAfter`, and AppKit finished the termination.
     - **Quit Apple event** (`probe/P2/probe-probe.log`): `3.534 [MainThread] terminate: applicationShouldTerminate_ called; returning NSTerminateLater (2)`; `6.549 [terminate-worker] terminate: replying True after 3 s`; `6.556 [MainThread] willTerminate: applicationWillTerminate_ (AppKit reached its exit)` (7 ms after the reply); `6.563 window closed event`. SUMMARY: `P2: probe (route subclass): osascript rc=0; exited 0.0s after the event returned; log: terminate=1 reply=1 willTerminate=2` (the count 2 is a grep that also matches the `resolved signatures … willTerminate=` line; the log has one `willTerminate:` event). `osascript` returned only once the app was gone, i.e. AppKit held the quit event pending the reply (the event reply is itself deferred).
     - **Cmd-Q keystroke** (`probe/P3/probe-q-probe.log`): `5.562 applicationShouldTerminate_ called; returning NSTerminateLater (2)`; `8.576 replying True after 3 s`; `8.581 willTerminate`; `8.584 window closed event`. SUMMARY: `P3: probe Cmd-Q (route subclass): front=23596 (the app); keystroke rc=0; exited=yes after 3.3s; path=T (applicationShouldTerminate_ ran)`: the process exit follows the 3 s deferral, so the process did not exit until the reply was delivered.
     - Caveats: the probe's main loop was idle (no server, no other main-thread work); the run-loop mode AppKit was in while waiting is not logged, so this proves `callAfter` is delivered under `NSTerminateLater` for an idle app, not under a busy main thread. The named fallback (`performSelectorOnMainThread_withObject_waitUntilDone_modes_` with `NSRunLoopCommonModes`) is therefore **not needed**; leg 4 should keep `callAfter` and keep its own bounded worker (a reply that never arrives would hang quit).
  3. **Cmd-Q's path: T, observed directly.** `exited=yes after 3.3s; path=T (applicationShouldTerminate_ ran)`, with the `applicationShouldTerminate_` log line above. (Leg 3's inference of T is confirmed.)
  4. **Reopen handler on `open -a`: fired**, with `hasVisibleWindows=True`: `probe/P4/probe-probe.log` line 12: `3.469 [MainThread] reopen: applicationShouldHandleReopen called hasVisibleWindows=True`; SUMMARY `P4: probe (route subclass): open -a on the running app rc=0; pids before [21610 ] after [21610 ]` (no new process). It also fired in P3 (`probe-q-probe.log` 3.437 and `probe-w-probe.log` 3.402) on the `open -a` that precedes each keystroke. The product, still on pywebview's stock delegate, has no handler (unchanged: pids `[21899]` before and after; `open -n` second pid 22190 exited 0.3 s after appearing, one focus line in the first's log, `lsappinfo front pid=21899`).
  5. **Cmd-W on the focused probe window: no effect.** SUMMARY: `P3: probe Cmd-W after a click in the window (clicked 512,384 rc=0): front=22913 (the app); state before: windows=1 visible=true frontmost=true pos=192,184 size=640x400; keystroke rc=0; state 2 s after: windows=1 visible=true frontmost=true pos=192,184 size=640x400; exited=no`. The window was clicked, frontmost and visible, and still is after the keystroke (`probe/P3/probe-w-before.png` and `probe-w-after.png` are the same white window; the log has no close event). So focus was not the cause in leg 3: the probe window ignores Cmd-W with the click and the raise done. (Cause not established; a missing Close menu binding on the probe's pywebview window is a hypothesis, not observed.) The **product's Cmd-W**: `front=22606 (the app); … keystroke rc=0; state after: curl-rc=7; pid alive=no`, and this time the drain ran (`probe/P3/product.stderr` lines 29-36: `Shutting down` … `Finished server process [22606]`), as in leg 3. Leg 4 must not rely on Cmd-W as a driver for a no-menu pywebview window; the product exits on it only through its close fallback.
  6. **PLN: the product did not trigger a local-network prompt, and the probe's did not appear either.** SUMMARY: `PLN: after the product's first launch: alert windows none seen (rc=0); screenshot 130582B (pln.png)`; `PLN: dismissal attempt: none seen (rc=0)`; every later `*-lnp.txt` is `rc=0` with nothing read. `probe/P1/pln.png` shows the painted Chats page ("Hello.") with no dialog; no screenshot in the run shows an overlay (leg 3's stale "Allow M32 Probe to find devices on local networks?" prompt is gone from `cold-1.png`, `probe-w-*.png`, `pln.png`). Caveats: the read covers the alert windows of the five listed owners and "none seen" means no AX window was found, so a prompt owned by another process would be missed, but the screenshots agree. Why the prompt vanished is not established (a fresh runner image state, or the earlier prompt having been a one-off tied to the probe's first local-network use); the product itself reads clean on this run.
  7. **Changed readings vs leg 3** (quote both):
     - **First paint (DD11):** cold: `+1 bytes=84614` (dark empty window, `P1/cold-1.png`: title bar and a uniform near-black client area), `+2 84796` (still empty), `+3 130637` (painted, stable to +30 s); warm: `+1 84771`, `+2 93492` (mid-paint), `+3 130234`. `/api/live` was 200 at +1 s. The control (data-URL window, no server): `84042B` at +1, +2, +3, +5 (blank white) and `84137B` at +10. So the paint lands between +2 and +3 s (cold) and the empty window is visible at +1 and +2 s: consistent with leg 3 (1-3 s) and now narrowed to 2-3 s; no blank beyond 3 s. Reading unchanged: not reproduced as a persistent blank; environmental per DD11; leg 4 changes nothing for first paint.
     - **P5 replace while running: a different outcome.** Leg 3: the old process stayed alive and answered. Now: `old alive=no; open -a rc=0; pids now [24220 ]` (a new pid; the old 24189 is gone) and `state: 200 {…"pid":24220}`. `probe/P5/old.stderr` line 56: `*** Terminating app due to uncaught exception 'OC_PythonException', reason: '<class 'FileNotFoundError'>: Cannot find JS directory in /Applications/GleepGlorp AI.app/Contents/Frameworks/webview/js'` then `libc++abi: terminating due to uncaught exception of type NSException`. So deleting a running bundle can crash the old process the next time it lazily reads a resource from the bundle (here pywebview's js directory, most likely when the window or a page triggers it), with no server drain; whether it crashes depends on timing. Divert 4 is not triggered (the marker copy is intact and the new process runs; the crash lost no stored data in evidence), but **the guide's replace advice must say "quit before replacing" without promising the old copy keeps running**, and leg 3's "the running copy keeps running" sentence is retracted.
     - **P2 on the product** is unchanged: the quit Apple event gives no drain (`probe/P2/product.stderr` ends at `connection open`, no `Shutting down`), while Cmd-W and the cold quit (`probe/P1/cold.stderr` lines 29-36) do drain: the defect leg 4 fixes.
     - P9 unchanged (`destroy: webview.start returned 0.013 s after window.destroy(); process alive=yes`), P6 unchanged (`spctl rc=3`, `syspolicy_check rc=70`, translocated path, "Not Opened" dialog), OTOOL unchanged (`max minos=14.0`, 13 files at 14.0), P8 unchanged (runner PATH, `SHELL=/bin/bash`, `--env` passes). P1 `quit rc=0, exited in 0.3s` cold and `0.7s` warm. One new harness note: `probe-step.log` line 1 has `probe.sh: line 140: …/the-one/api-credential: No such file or directory` (the product's credential file is read before it exists; harmless, the premise rows are present).
  8. **Divert and acceptable-variation criteria re-evaluated.**
     - Delegate cannot be extended by either route (DD4): **CLEARED, not triggered** (the subclass route installed and ran).
     - `NSTerminateLater` does not drain (DD3): **CLEARED, not triggered** (items 2-3: the deferred reply terminated both the Apple-event quit and Cmd-Q).
     - No GUI session: not triggered. Replace-while-running loses or corrupts data (P5): not triggered (see item 7 for the changed crash reading).
     - 5-dispatch budget spent without a green lifecycle run: not triggered (2 of 5 used, 3 left; this run's selftest and probe are green).
     - Acceptable variations: the `callAfter` reply worked, so the `NSRunLoopCommonModes` fallback is not taken; the `classAddMethods` and `os._exit(0)` variations are not needed; first paint "environmental" stands.
     - **Still unanswered:** the delegate on the real product (the probe has no server, no tray, no busy main thread); the run-loop mode during the wait; how a Dock quit or logout path behaves (the probe tested only the Apple event and Cmd-Q).
  9. **Hosted minutes.** Job `build` 15:15:11Z to 15:20:26Z = 5 min 15 s, billed as 6 whole minutes: 6 x 10 = **60 billed macOS minutes** (about 52.5 if billed by the exact 5.25 min). Of that the premise step was 234 s. Flight total so far: 50 (run 40203877635) + 60 = **110 billed minutes**.

  **Leg-4 preconditions, answered:** (a) route that installed: `subclass`; (b) logged signatures: terminate `I@:@` (superclass), reopen `B@:@B` (protocol), willTerminate `v@:@` (protocol), `NSApp.delegate().className()` = `M32ProbeAppDelegate`; (c) counts: terminate=1 (called), reply=1, willTerminate=1 event (the SUMMARY row prints 2, a double grep match); (d) **callAfter reply delivered: yes** (both quit paths; 3 s deferral, `willTerminate` 7 ms and 5 ms after the reply); (e) neither-route-installed gate: does not apply; (f) the `NSRunLoopCommonModes` fallback: not needed; (g) `classAddMethods`: not chosen, `install` replaces the class attribute as DD4 says.

## Anomalies

---

## Session Notes
