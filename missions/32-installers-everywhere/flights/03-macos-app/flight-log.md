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

---

## Leg Progress

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
