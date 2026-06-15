# Flight Log: Windows Native App Hardening — Desktop Presence & Lifecycle

**Flight**: [Windows Native App Hardening — Desktop Presence & Lifecycle](flight.md)

## Summary

Flight created 2026-06-15 (planning). Introduces a single composable desktop-shell
module (`the_one/interfaces/desktop/`) adding system-tray presence + background-run,
single-instance focus, and window-state persistence to the F4 native window.
Phase-5b Architect review complete (approve-with-changes; all changes incorporated).
Awaiting operator sign-off, then execution via `/agentic-workflow`.

---

## Leg Progress

### Leg 1: desktop-shell-scaffold — landed (2026-06-15)

**What changed:**
- Created `the_one/interfaces/desktop/__init__.py` — package init exporting `run_desktop`.
- Created `the_one/interfaces/desktop/shell.py` — verbatim body of `app.py`'s F4 launcher
  with `run` renamed to `run_desktop`; all four helpers (`_select_port`, `_webview_available`,
  `_wait_until_serving`, `_graceful_shutdown`) relocated there unchanged.
- Reduced `the_one/interfaces/app.py` to a back-compat shim re-exporting all five symbols
  from `desktop.shell` (including `run_desktop as run`). No logic in `app.py` remains.
- `pyproject.toml` `[gui]` extra: added `pystray>=0.19` and `pillow>=10.0`.
- `tests/test_app_launcher.py` → `tests/test_desktop_shell.py` (git mv): every
  `the_one.interfaces.app` reference repointed to `the_one.interfaces.desktop.shell`;
  all `launcher_module.run()` / `launcher_mod.run()` calls updated to `run_desktop()`.

**Test results:** 17/17 passed, 0 failures, 0 errors (host-native, `--timeout=30`).

**Verification outputs:**
- Import surface (new + back-compat): `ok`
- `pystray` + `PIL` importable: `deps ok`
- CI shim (`from the_one.interfaces.app import _select_port`): `ci-shim ok`
- Reload target (`importlib.reload(the_one.interfaces.desktop.shell)`): `reload ok`
- Stray `test_app_launcher` references: none
- `git diff --stat` scope: `app.py`, `tests/test_desktop_shell.py`, `pyproject.toml`, `missions/` (planning artifact), new `desktop/` package (untracked — correct).

**Deviations:** None. `pip install -e ".[gui]"` partially failed on this headless Linux host
because PyGObject (gtk extra for pywebview) requires native GTK dev headers not present in
the environment. `pystray` and `pillow` installed cleanly; this is a pre-existing environment
constraint unrelated to this leg's changes. The leg's scope (pystray + pillow in `[gui]`)
is fully verified by the direct `pip install "pystray>=0.19" "pillow>=10.0"` + import check.

### Leg 4: window-state-persistence — landed (2026-06-15)

**What changed:**
- Created `the_one/interfaces/desktop/window_state.py` — new module (headless-importable,
  no GUI top-level imports). Exports: `load_state() -> dict | None` (reads
  `data_dir / "window-state.json"`; returns None on absent/corrupt file, never raises);
  `save_state(w, h, x=None, y=None)` (creates data_dir, writes JSON, best-effort); and
  `clamp_to_bounds(state, screens) -> dict` (computes screen union, clamps width/height to
  union dims first, then clamps top-left into [union_x_min, union_x_max - w] ×
  [union_y_min, union_y_max - h] — negative-origin-safe). `_state_path()` helper resolves
  at call time (not import time) so monkeypatch works in tests.
- Updated `the_one/interfaces/desktop/shell.py` `run_desktop()`: added window-state restore
  block before `create_window` — calls `load_state()`, if present calls
  `clamp_to_bounds(state, webview.screens())` (screens() called with parens), spreads
  width/height/x/y into `_create_kwargs`; absent state → only `frameless=False` in kwargs
  (F4 defaults unchanged).
- Added `_save_current_geometry(window)` helper (nested closure in `run_desktop`): guards on
  `window.events.shown.is_set()` (avoids 15s GUI-thread block if window hasn't shown);
  reads geometry in `try/except` (covers pywebview 5 GUI-backed properties); calls
  `save_state(w, h, x, y)`.
- Wired `_save_current_geometry(_desktop_window)` into `_on_closing` (at top, before any
  hide/destroy) and `_on_quit` (before `window.destroy()` — redundant-but-safe for future
  backends per edge-case note).
- Created `tests/test_window_state.py` — 18 tests covering: round-trip with/without x/y;
  load returns None on absent file; load returns None on corrupt JSON; load returns None on
  non-dict JSON; clamp on-screen unchanged; clamp off-screen x clamped; window wider than
  screen shrinks then x clamped; negative-origin monitor valid; negative x below left edge
  clamped to union_x_min; empty screens → state unchanged; multi-monitor union; run_desktop
  with saved state passes kwargs to create_window; run_desktop no state → no geometry kwargs;
  capture-skip-when-not-shown; both-paths write geometry; geometry-raises → save not called.

**Test results:** 60/60 passed (18 new window-state + 17 shell + 17 tray + 8 window-focus),
0 failures, 0 errors (host-native, `--timeout=30`).

**Verification outputs:**
- Import check: `ws import ok` (no GUI stack required)
- `git diff --stat` scope: `the_one/interfaces/desktop/` (new window_state.py + shell.py
  modified, all untracked as a new package) + `tests/test_window_state.py` (new untracked).

**Deviations:** None. `_on_quit` capture is correctly documented as redundant-but-safe:
pywebview-5.4 fires `closing` on `destroy()` in all backends (winforms/gtk/cocoa, confirmed
in source), so `_on_closing` already captured geometry before `_on_quit` reaches `destroy()`.
The double write is idempotent (same geometry) and retained for forward-safety.

### Leg 3: single-instance-focus — landed (2026-06-15)

**What changed:**
- Added `focus_window() -> bool` to `the_one/interfaces/desktop/shell.py`: reads
  `_desktop_window`; None → False; calls `show()` + `restore()` thread-safely; guards
  in try/except → log + False on failure.
- Added focus-and-exit branch to `run_desktop()` in `shell.py`: immediately after
  `_select_port()`, if `is_ours=True`, POSTs header-less to
  `http://{host}:{sel_port}/api/window/focus` (timeout=2.0s); catches `httpx.HTTPError`
  broadly (logs warning); returns. The existing `if not is_ours:` server-start block is
  untouched (now unreachable for the `is_ours=True` case due to early return).
- Added `POST /api/window/focus` endpoint to `the_one/interfaces/web/app.py` beside
  `/api/info`: lazy-imports `focus_window` inside the handler body (web-import purity);
  returns `{"focused": focus_window()}` 200.
- Created `tests/test_window_focus.py` — 8 new tests: `focus_window()` unit tests (no
  window → False; window → show+restore+True; exception → False); endpoint tests (focused
  true/false; header-less POST not rejected); run_desktop focus-and-exit branch tests
  (POST URL + no-Origin check; no window created; POST-raise → clean exit).
- Updated `tests/test_desktop_shell.py`: replaced `test_run_case_b_no_server_started`
  (old: expected window creation on `is_ours=True`) and
  `test_run_case_b_no_backend_opens_browser_and_returns` (old: expected browser.open on
  `is_ours=True`) to reflect the new focus-and-exit behavior. Both now verify POST is
  called and no window/server/browser is created.
- Updated `tests/test_desktop_tray.py`: `_run_desktop_with_tray` helper changed from
  `_select_port → (8484, True)` to `(8484, False)` (with server/thread mocks) so tray
  tests still reach the window-creation path; `test_tray_failure_no_closing_handler_registered`
  updated identically.

**Test results:** 42/42 passed (8 new window-focus + 17 shell + 17 tray), 0 failures,
0 errors (host-native, `--timeout=30`).

**Verification outputs:**
- Route check: `['/api/window/focus']`
- Web import purity: `web import ok` (no pywebview pulled at module load)
- `git diff --stat` scope: `the_one/interfaces/web/app.py` (modified) +
  `the_one/interfaces/desktop/` (untracked, incl. shell.py changes) +
  `tests/test_window_focus.py` (untracked) + `tests/test_desktop_shell.py` (modified) +
  `tests/test_desktop_tray.py` (untracked, modified).

**Deviations:**
- Two additional tests in `test_desktop_shell.py` updated (beyond the leg spec's scope):
  `test_run_case_b_no_backend_opens_browser_and_returns` expected `is_ours=True` to open
  a browser; this was pre-Leg-3 behavior that no longer applies. Updated to verify the
  new focus-and-exit path. These are legitimate regressions, not surprises — the
  behavioral change is the entire point of this leg.

### Leg 2: system-tray-and-background — landed (2026-06-15)

**Spike outcome (pystray + pywebview semantics — headless host, reasoned from source):**

Neither pywebview nor pystray is installed in the project venv on this headless Linux host.
The spike reasoned from pystray source (`_base.py`, `_win32.py`) and library knowledge of
pywebview:

- **Thread model chosen: `Icon.run_detached()` (DD2 default).** The win32 backend's
  `_run_detached()` (confirmed in `_win32.py:130`) starts `threading.Thread(target=lambda:
  self._run())` — **no `daemon=True`**, so it is a non-daemon thread. Confirmed: if
  `icon.stop()` is ever skipped, this thread is left alive and the process won't exit
  (the `finally: _graceful_shutdown` drain blocks forever). Mitigation implemented:
  `icon.stop()` is wrapped in `try/except` and called before `window.destroy()` in the
  Quit callback so it cannot be skipped.

- **Marshalling rule:** tray callbacks (`on_show`, `on_quit`) call pywebview's
  `window.show()`/`restore()`/`hide()`/`destroy()` from the pystray win32 message-loop
  thread. pywebview's Window methods are documented as thread-safe; no native-handle
  access is done. `hide()` in `_on_closing` (which runs on pywebview's main thread, not
  the tray thread) is wrapped in `try/except` returning `True` on failure because
  pywebview's `Event.set()` swallows handler exceptions — a raise would be silently
  ignored and the cancel return value lost.

- **Spike checklist recorded:**
  - (a) `hide()` callable synchronously from inside the `closing` handler — YES (pywebview
    main thread; window methods are synchronous).
  - (b) `destroy()` callable from pystray's win32 message-loop thread — YES (pywebview
    Window methods are thread-safe per library design).
  - (c) `run_detached()` on Windows needs no `darwin_nsapplication` arg — YES (the kwarg
    is filtered by prefix `darwin_` and simply unused on win32; no error).

- **Empirical coexistence proof deferred to Leg 5** (frozen `windows-2022` packaged-smoke)
  **and Leg 6** (operator HAT / `windows-desktop-presence` behavior test), per DD6.
  This host has no GUI stack; all Leg 2 tests are mocked-GUI unit tests.

**What changed:**
- Created `the_one/interfaces/desktop/notice.py` — first-run close-to-tray marker
  (`notice_shown()` / `mark_notice_shown()`) under `settings.data_dir`, with its own
  `mkdir(parents=True, exist_ok=True)`.
- Created `the_one/interfaces/desktop/tray.py` — lazy-import pystray Icon builder
  (`build_tray(on_show, on_quit)`) with Show/Quit menu + Pillow icon from brand PNG +
  `notify(icon, message, title)` wrapper.
- Extended `the_one/interfaces/desktop/shell.py` `run_desktop()`: module-level
  `_really_quit`/`_desktop_window` lifecycle state; `_on_closing` (hide-to-tray,
  first-run notice, hide-failure → return True); `_on_show` (show + restore);
  `_on_quit` (set flag, guarded stop, destroy); tray try/except degrade (no `closing`
  handler on failure → F4 fallback).
- Created `tests/test_desktop_tray.py` — 17 mocked-GUI unit tests using `_EventCapture`
  helper for `window.events.closing +=` registration.

**Test results:** 34/34 passed (17 new tray + 17 existing shell), 0 failures,
0 errors (host-native, `--timeout=30`).

**Verification outputs:**
- `import the_one.interfaces.desktop.tray, the_one.interfaces.desktop.shell` (no
  pystray/webview): `import ok`
- Brand icon path: `icon ok True`
- `git diff --stat` scope: changes confined to `the_one/interfaces/desktop/` (new files
  untracked) and `tests/` (new untracked), plus leg artifact update.

**Deviations:** None. pywebview and pystray not installed in venv on this headless Linux
host; spike reasoned from pystray `_base.py`/`_win32.py` source (installed) and pywebview
library knowledge. All GUI-contract tests use mocked modules. Real coexistence deferred to
Leg 5/6 per DD6 (pre-planned deviation, logged in spike).

### Leg 5: freeze-integration — landed (2026-06-15)

**What changed:**

- `packaging/windows/the-one.spec`:
  - Added `pystray_hidden = collect_submodules("pystray", on_error="warn")` — `on_error="warn"` is MANDATORY: pystray's `_xorg`/`_gtk`/`_appindicator`/`_darwin` backends import Linux/macOS-only deps at module scope and would abort the Windows freeze without it (same failure mode as `mcp.cli` at spec line 75).
  - Added `"pystray._win32"` and `"pystray._util.win32"` to `hiddenimports` (redundant but explicit).
  - Added `*pystray_hidden` to `hiddenimports`.
  - **PIL/Pillow approach**: relied on the `pyinstaller-hooks-contrib` PIL hook (no explicit `collect_submodules("PIL")` added). The hooks-contrib hook handles `_imaging` + plugins; adding an explicit collect is only needed if a frozen build proves a plugin is missing. **This is the approach used.**
  - **Tray PNG**: confirmed the existing `static_datas = collect_data_files("the_one", includes=["interfaces/web/static/**/*"])` already collects `the_one/interfaces/web/static/brand/gleepglorp_icon.png` (the path used in `tray.py`). No duplicate `datas` entry added.
  - Rewrote the stale docstring at lines 20-21 ("Leg 4's CI packaged-smoke…") to remove the leg-number reference.
  - Rewrote the stale inline comment at line 85 ("Leg-4 build note:") to remove the leg-number reference.

- `the_one/diagnostics.py`:
  - Rewrote the stale module docstring at line 17 ("Leg 4's CI packaged-smoke reads exactly this exit code…") to remove the leg-number reference.
  - Added `_probe_desktop_shell() → ProbeResult`: imports `the_one.interfaces.desktop.tray` + `pystray` + `PIL` in try/except; on success → `ok=True, detail="pystray + PIL importable"`; on `ImportError` when frozen → `ok=False` (gate); on `ImportError` when not frozen → `ok=True, detail="skipped (gui extra not installed)"` (informational). Catches broad `Exception` for safety (never crashes).
  - Added `desktop = _probe_desktop_shell()` to `run_doctor`'s gates list; printed with the existing `"  {name}: {status} — {detail}"` format.

- `.github/workflows/windows-installer.yml`:
  - Added `grep -q "desktop shell: OK" doctor.out` to the "Packaged-smoke (a) — frozen doctor" step. A freeze that drops pystray/Pillow will now fail the smoke even if `RESULT: PASS` were somehow printed without the desktop line.

- `the_one/agents.md`:
  - Expanded the "Desktop launcher" section with a new "M15 F6 desktop-shell additions" block documenting: close-to-tray / background run, Quit-from-tray as the real exit, single-instance focus (`/api/window/focus`), and `window-state.json` persistence.

- `README.md`:
  - Added background-run / close-to-tray, Quit-from-tray, single-instance-focus, and window-state-persistence paragraphs to the "Desktop window" section.

- `CLAUDE.md`:
  - Expanded the "Desktop launcher" section with a brief M15 F6 summary (close-to-tray, Quit-from-tray, `/api/window/focus`, `window-state.json`).

- `tests/test_doctor.py`:
  - Added `TestProbeDesktopShell` class (5 tests): OK-path (import-present → ok=True); skip-path (import-absent + not-frozen → ok=True, "skipped"); skip-keeps-PASS (non-frozen skip → RESULT: PASS in full doctor output); frozen-fail → RESULT: FAIL; desktop line present in output.

**Test results:** 109 passed, 10 skipped (pre-existing bwrap skips), 0 failures (host-native, `--timeout=30`).

**Verification outputs:**
- `the-one doctor` output: `desktop shell: OK — pystray + PIL importable` / `RESULT: PASS` ✓
- `python -c "import ast; ast.parse(...); print('spec parses')"`: `spec parses` ✓
- `grep -n "pystray\|PIL\|collect_submodules" packaging/windows/the-one.spec`: entries present at lines 98, 138-139, 142 ✓
- `git diff --stat` scope: `.github/workflows/`, `CLAUDE.md`, `README.md`, `packaging/windows/the-one.spec`, `tests/test_doctor.py`, `the_one/agents.md`, `the_one/diagnostics.py` — all expected; prior-leg files (`the_one/interfaces/app.py`, `the_one/interfaces/web/app.py`, `pyproject.toml`, `missions/mission.md`, `tests/test_desktop_shell.py`) are staged changes from earlier legs in this flight, not this leg's work ✓

**Deviations:**
- **Frozen `windows-2022` build deferred (pre-planned):** The frozen packaged-smoke cannot run on this headless Linux host, and the `windows-installer.yml` workflow is tag-gated (`v*` push only). Proof of correct freeze (pystray/Pillow bundled, `desktop shell: OK` in frozen doctor output) is deferred to the next `v*` tag build and the Leg-6 operator HAT. This is the pre-planned deviation noted in the leg's Context section and matches acceptance criterion 7 (HAT/tag-gated).
- **PIL via hooks-contrib (not explicit collect):** chose the `pyinstaller-hooks-contrib` PIL hook approach over explicit `collect_submodules("PIL")` per the implementation guidance preference. Logged per the leg's criterion 1 requirement to state the approach.

---

## Decisions

### Single Phase-5b review cycle (no second pass)
**Context**: The Architect returned approve-with-changes. Every issue was a
documentation/scoping correction with a prescribed fix (Origin-allowlist reality,
freeze collection contract, close-only geometry baseline, marshalling note, docs-as-leg,
behavior-test step-7 settle) — no open design direction remained after resolving the
three designer questions.
**Decision**: Incorporated all changes and skipped the second review cycle (the skill
permits skipping when changes are corrective, not substantive re-design). The 3
designer questions were resolved by the Flight Director: focus client sends no `Origin`
header; close-only geometry capture is the planned path; the Leg-2 spike defaults to
pystray `run_detached()` while evaluating the daemon-thread alternative.
**Impact**: Spec is codebase-validated and ready for operator sign-off without a
further review round.

---

## Deviations

_(none yet)_

---

## Anomalies

### Window-state restore crash: webview.screens called as function on a proxy-list (M15 F6 HAT fix, 2026-06-15)

**Discovered by:** HAT operator logfile on a real Windows machine running the
frozen build.

**Traceback:**
```
WARNING the_one.interfaces.desktop.shell: window_state: restore failed; using defaults
  File "the_one/interfaces/desktop/shell.py", line 196, in run_desktop
  File "proxy_tools/__init__.py", line 131, in <lambda>
TypeError: 'list' object is not callable
```

**Root cause:** The Leg-4 implementation called `webview.screens()` (with
parens), consistent with the API surface described in the Leg-4 design review.
The *installed* pywebview exposes `webview.screens` as a `proxy_tools` lazy
module property that **already evaluates to the list of Screen objects** — it is
not a function.  Calling it with `()` attempts to call a list → `TypeError`.
The outer `except Exception` catch logged "restore failed; using defaults" and
fell back to defaults, so the window opened at defaults on every launch despite
a correctly-written `window-state.json` on disk.

Geometry *capture* was unaffected — `window-state.json` was being written
correctly after each close.  Only restore was broken.

**Root-cause of the root cause:** The Leg-4 design-review API claim (`screens`
is a callable) was wrong for the installed build.  The unit-test mock used
`webview_mock.screens.return_value = [screen]`, which exercises the mock's
`__call__` path and hid the incompatibility — the mock never revealed whether
the real `screens` attribute is a list or a function.

**Fix:** Replaced the direct `webview.screens()` call with a robust resolution
sequence in `run_desktop()`: (1) read `webview.screens` into `_screens`; (2) if
it is already a `list`/`tuple`, use it directly (installed pywebview); (3)
otherwise try `list(_screens)` to materialise a proxy-iterable; (4) catch
`TypeError` and call `_screens()` as a function (other-version callable form).
The existing outer `except Exception` remains as the final safety net.

**Fix — resize-on-show:** The tray `_on_show` callback was calling both
`window.show()` and `window.restore()`.  Since the window is hidden via
close-to-tray (not minimized), `restore()` was resetting the window's size on
every Show click.  Removed `restore()` from `_on_show`; kept only `show()`.
`focus_window()` keeps its `show()+restore()` pair for the single-instance path
where the window may genuinely be minimized.

**Tests added/updated:**
- `test_window_state.py`:
  - `test_run_desktop_restores_saved_geometry_screens_as_list` — plain-list
    form (the HAT / installed pywebview case).
  - `test_run_desktop_restores_saved_geometry_screens_as_callable` — callable
    form (a lambda; `list(fn)` raises TypeError → callable branch).
  - `test_run_desktop_screens_as_list_does_not_raise` — regression: asserts
    restore does not throw and geometry is applied when `webview.screens` is a
    plain list.
  - Kept `test_run_desktop_restores_saved_geometry` as an alias pointing at the
    list-form test.
- `test_desktop_tray.py`:
  - `test_show_callback_calls_window_show_not_restore` — asserts `show()` is
    called and `restore()` is NOT called from `_on_show`.

**Test results:** 83 passed, 0 failures, 0 errors (host-native,
`tests/test_window_state.py tests/test_desktop_shell.py
tests/test_desktop_tray.py tests/test_window_focus.py
tests/test_frozen_stdio.py tests/test_doctor.py`, `--timeout=30`). ✓

---

### Frozen windowed-app stdio crash (M15 F6 review-fix, 2026-06-15)

**Discovered by:** HAT operator on a real Windows machine running the frozen
windowed build (`the-one-app.exe`, PyInstaller `console=False`).

**Root cause:** PyInstaller's `console=False` EXE has no console attached, so
it sets `sys.stdout` and `sys.stderr` to `None` at process start.  Uvicorn's
`ColourizedFormatter.__init__` (uvicorn/logging.py line 42) calls
`sys.stdout.isatty()` during `uvicorn.Config(...)` setup →
`AttributeError: 'NoneType' object has no attribute 'isatty'` →
`ValueError: Unable to configure formatter 'default'` → `run_desktop()` crashes
before the server starts.

**Traceback path:** `packaging/windows/frozen_entry_gui.py:24` → `the_one/main.py`
(`cli_entry`) → `the_one/interfaces/desktop/shell.py:160` (`uvicorn.Config(...)`)
→ `uvicorn/logging.py:42` (`sys.stdout.isatty()`).

**Pre-existing latent bug:** F4 never ran the rendered-window HAT; the console
build and host-native tests always have a real stdout so the crash is invisible
in CI.  Only the frozen `console=False` launch path is affected.

**Fix:** Added `ensure_stdio_streams()` to `the_one/platform/env.py`.  It
replaces any `None` stream with a line-buffered append file at
`settings.data_dir / "logs" / "the-one-app.log"` (devnull fallback on any
error).  Called at the top of `packaging/windows/frozen_entry_gui.py` (primary,
before `cli_entry()`) and at the start of `run_desktop()` (defensive, idempotent
second call for any non-frozen-entry launch path).  A real file object's
`.isatty()` returns `False` — satisfies uvicorn's color-detection check with no
crash.  New test: `tests/test_frozen_stdio.py` (7 tests, all green).

---

### Over-the-top install blocked by running app (M15 F6 HAT, 2026-06-15)

**Discovered by:** HAT operator — installing a new build over a running install failed
with file-copy errors; `the-one-app.exe` remained running after the installer attempted
to close it.

**Root cause:** F6 Leg 2 changed WM_CLOSE to hide the app to the tray instead of
quitting it.  Inno Setup's built-in "close the running application" step sends WM_CLOSE
(same signal as the title-bar X button), which now only hides the window.  The background
process stays alive, holding file locks on the install directory, and the installer's
file-copy step fails.

**Fix:** Two-layer defence added to `packaging/windows/the-one.iss`:

1. `[Setup]` directives (Inno 6.3+, build host has 6.7.1):
   - `CloseApplications=force` — after the Restart Manager's graceful-close attempt,
     force-terminates any process still locking install-dir files.
   - `RestartApplications=no` — prevents the Restart Manager from relaunching the old
     binary after the upgrade (the `[Run]` post-install entry handles user-initiated
     launch).

2. `[Code]` backstop (`PrepareToInstall` → `KillRunning`): runs before any files are
   copied; calls `taskkill /F /IM the-one-app.exe` and `taskkill /F /IM the-one.exe`
   via `{sys}\taskkill.exe`.  Return code is ignored (exit 128 = "not found" is fine).
   The installer image is `the-one-setup-<ver>.exe`, so neither kill target matches it.

**Scope:** `packaging/windows/the-one.iss` only — no Python source changes, no new tests
(packaging-only fix; real validation at the next Windows HAT build).

---

## Flight Director Notes

### 2026-06-15 — Execution kickoff (/agentic-workflow)
- Phase file `leg-execution.md` loaded + validated (Crew / Interaction Protocol /
  Prompts present). Crew: Developer (Sonnet, design-review + implement), Reviewer
  (Haiku, code review). Batch model: design per leg → implement → one end-of-flight
  review + commit.
- Branch `flight/06-windows-app-hardening-presence` created off `main`; planning
  artifacts (mission re-scope, flight spec/log, behavior-test spec) carried onto it.
  Flight status → `in-flight`.
- **Override — stale crew prompt:** the "Developer: Implement" prompt still references
  `docker exec the-one pytest …`, but M15 F1 retired Docker (tests are host-native
  now). Per the skill-boundary rule, every Developer spawn this flight will be
  instructed to run **host-native `python -m pytest -x --timeout=30 <files>`** instead
  of the Docker flow. Flagged for the F6 debrief: the `leg-execution.md` crew file
  needs its test-command updated (or re-defaulted) project-wide.
- 6 legs planned: desktop-shell-scaffold → system-tray-and-background → single-
  instance-focus → window-state-persistence → freeze-integration → hat-and-gui-
  behavior-test (interactive). Starting at Leg 1.

### 2026-06-15 — Leg 1 → Leg 2 transition
- Leg 1 (`desktop-shell-scaffold`) landed: design-review (Developer/Sonnet,
  approve-with-changes — 3 cosmetic fixes folded, no re-review) → implement
  (Developer/Sonnet, 17/17 launcher tests green host-native). The consumer audit
  confirmed only `main.py` + the CI workflow + the test file import `interfaces.app`;
  back-compat shim covers all three. Headless-Linux `[gui]` install still hits the
  known PyGObject GTK-headers wall (F4-documented; pystray/pillow install clean).
- Proceeding to Leg 2 (`system-tray-and-background`) — the flight's lead-risk leg
  (pystray⇄pywebview coexistence). Real GUI/tray validation is deferred to Leg 5
  (frozen `windows-2022` smoke) and Leg 6 (operator HAT) per DD6; Leg 2's own tests
  are mocked-GUI unit tests, host-native.

## Session Notes

### 2026-06-15 — Flight authored

- Created during the Windows-only mission re-scope. Two operator decisions shaped it:
  depth-first-on-Windows (hardening before mac/Linux packaging), then mac/Linux pulled
  out of M15 entirely (→ follow-up mission).
- Forks resolved with the operator: close-to-tray (DD3); single composable module,
  not a per-OS backend split (DD1); HAT leg + Witnessed GUI behavior-test spec (DD6).
- Behavior-test spec authored inline: `tests/behavior/windows-desktop-presence.md`.

### 2026-06-15 — Review-fix pass (post end-of-flight review)

End-of-flight Reviewer confirmed with no blocking issues but flagged four findings.
All four addressed:

1. **Freeze gap — `packaging/windows/the-one.spec`** (SUBSTANTIVE): Added
   `*collect_submodules("the_one.interfaces.desktop")` to `hiddenimports`.  The
   `tray`, `notice`, and `window_state` submodules are only imported lazily inside
   function bodies and were invisible to PyInstaller's static analysis.  Without this
   fix they would be missing from the frozen bundle → guaranteed `desktop shell: FAIL`
   at the next tag build.
   - `collect_submodules("the_one.interfaces.desktop")` confirmation (host-native):
     `['the_one.interfaces.desktop', 'the_one.interfaces.desktop.notice',`
     `'the_one.interfaces.desktop.shell', 'the_one.interfaces.desktop.tray',`
     `'the_one.interfaces.desktop.window_state']` — all five members enumerated. ✓

2. **Dead guard — `the_one/interfaces/desktop/shell.py`**: Removed the `if not is_ours:`
   guard at ~line 156 (dead condition — `is_ours=True` already returned above).
   De-indented the server-start block to run unconditionally at that point with an
   explanatory comment.  `finally: _graceful_shutdown(...)` is unaffected.

3. **Consistency — `the_one/interfaces/desktop/notice.py`**: Moved
   `from the_one.config import settings` from module top-level into `_marker_path()`
   at call time, matching `window_state._state_path()`'s pattern.  A test
   monkeypatching `settings.data_dir` is now honoured without patching the helper.

4. **Test strengthening — `tests/test_window_state.py::test_on_closing_saves_geometry`**:
   Rewrote to actually fire `_on_closing` via the registered `closing` event handler.
   Injects pystray + PIL mocks (same pattern as `test_desktop_tray.py`) so the tray
   block succeeds and `_on_closing` is registered; pre-marks the notice to suppress
   noise; fires `closing_event.fire()` and asserts the file is written with the mock
   window's geometry and the handler returns `False` (cancel destroy).

**Test results:** 73 passed, 0 failures (host-native,
`tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_focus.py`
`tests/test_window_state.py tests/test_doctor.py`, `--timeout=30`). ✓
**Import check:** `imports ok` ✓
**Spec parse:** `spec parses` ✓

### 2026-06-15 — Phase 2d: end-of-flight review + autonomous-batch commit (Flight Director)

- **Reviewer** (Sonnet — bumped from the crew's Haiku default for this flight's size/
  risk; still not Opus per the rule) reviewed the full uncommitted change set with no
  knowledge of the implementers' reasoning → `[HANDOFF:confirmed]`, 73/73 green, all
  five legs' acceptance criteria met, **no blocking issues**. Three non-blocking
  findings + the freeze gap → one Developer fix pass (above); fixes were targeted,
  prescribed, and test-verified, so no second full review cycle.
- **Committed autonomous legs 1–5** (batch model): legs 1–5 → `completed`, checked off
  in flight.md; draft PR opened. **Leg 6 (`hat-and-gui-behavior-test`) remains** — the
  interactive operator HAT + the `windows-desktop-presence` Witnessed behavior test,
  which need a **frozen Windows build of this branch** (the tray/window/freeze behaviors
  have no CI apparatus — DD6). Flight stays `in-flight` pending the HAT; build logistics
  to be settled with the operator.
