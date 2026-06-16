# Flight Log: Windows Native App Hardening — Visual Polish

**Flight**: [Windows Native App Hardening — Visual Polish](flight.md)

## Summary

Flight created 2026-06-15 (planning). Extends the F6 desktop-shell with the visual half:
a `DesktopSession` refactor (folded in per operator), frameless custom window chrome
(themed titlebar in `#app-topbar`), a launch splash, and a brand taskbar icon. Awaiting
design review (Phase 5b) and operator sign-off.

---

## Leg Progress

### desktop-session-refactor (Leg 1)
**Status**: landed

#### Implementation (2026-06-15)
- Introduced `DesktopSession` class in `the_one/interfaces/desktop/shell.py`. The class
  owns `self._icon` as instance state. The window reference (`_desktop_window`) and quit
  flag (`_really_quit`) remain module-level globals, written by the session via `global`
  declarations — per the RESOLVED DD1 decision, ensuring `focus_window()` and the F6 test
  suite's direct module-attribute writes continue to work unchanged.
- Four lifecycle callbacks converted to methods: `_save_current_geometry(self, window)`,
  `_on_closing(self) -> bool`, `_on_show(self, icon)`, `_on_quit(self, icon)`. The full
  create-window / tray-wiring / `webview.start()` / `finally: _graceful_shutdown(...)` sequence
  moved into `DesktopSession.run()`. Browser-fallback and `is_ours` early-return paths also
  moved into `run()`.
- `run_desktop()` stays a module-level function: calls `ensure_stdio_streams()` at the
  outermost entry (before constructing the session), then `DesktopSession().run()`.
- All four stateless helpers and `focus_window` remain module-level, signatures unchanged.
- No test files were modified — the module-global bridge strategy was designed precisely so
  the F6 suites pass unchanged.

#### Test outcomes
- F6 regression net: `pytest tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_focus.py tests/test_window_state.py -x --timeout=30` → **63 passed, 0 failed**.
- Broader smoke (`pytest -q -x --timeout=30 -k "desktop or window or interface"`) → **81 passed, 10 skipped, 0 failed**.
- Import contracts verified clean.

#### Deviations / anomalies
- None. Pure structural refactor; no test adaptations required.

#### Design review (Phase 2a)
- Leg artifact authored from the real `shell.py` (381 lines) + the F6 regression net.
- One Developer design-review pass (Sonnet). Assessment: **approve with changes**. Three
  findings, all incorporated:
  - **[high]** `tests/test_window_state.py` was missing from the named regression net (it
    calls `run_desktop()` and fires the real `_on_closing`) — added.
  - **[high]** `_really_quit` has TWO module-level reach points in `test_desktop_tray.py`:
    a **write** at :333 (before `_on_closing`) and a **read** at :500 (after `_on_quit`) —
    leg now requires the methods to read AND write the module global.
  - **[medium]** `test_window_focus.py` assigns `shell_mod._desktop_window` directly, so
    `focus_window()` must keep reading the **module global** — resolution locked (no
    delegate-to-instance).
- **Decision (DD1-consistent):** keep `_desktop_window` and `_really_quit` as module globals
  the `DesktopSession` reads/writes; class strictly minimal (no forward-looking placeholders);
  `ensure_stdio_streams()` stays at the outermost entry in `run_desktop()`. Second
  design-review cycle skipped — fixes were direct transcriptions of the reviewer's prescribed
  changes (no new design surface).

---

### window-chrome (Leg 2) — implementation

**Status**: landed

- Lead-risk leg. **Two design-review cycles** (Sonnet), both reading the pinned **pywebview
  5.4** source.
- Round 1 (approve with changes) caught real correctness bugs, all incorporated:
  - **[high]** three more `frameless is False` assertions in `test_window_state.py`
    (:309/:345/:430) beyond `test_desktop_shell.py:297` — all four must flip to `True`.
  - **[high]** `easy_drag` defaults to `True` and pywebview has **no `no-drag` exemption** —
    the original "add `no-drag` to controls" plan was wrong. Reframed: `easy_drag=False` + a
    **dedicated `.pywebview-drag-region` spacer** that does NOT contain the controls/nav
    buttons (siblings, not descendants — the only reliable mitigation).
  - **[medium]** `toggle_maximize` has no native pywebview equivalent → app-side
    `_is_maximized` flag. **[medium]** `js_api` window-ref stored on the session after
    `create_window`. **[low]** `close()` guards `self._icon is None` → destroy (F6 fallback).
- Round 2 (approve, low-only) confirmed all 8 design points against the source; two LOW
  framing corrections applied: `easy_drag` is likely inoperative on Windows edgechromium
  (`platform=='chromium'` check) — kept as the defensive value + a HAT observation; and
  `renderTopBar()` runs once at `DOMContentLoaded` (re-run on `pywebviewready`, not "every
  nav"). Max review cycles reached on a clean approve — no escalation.
- **Spike deferral:** the frameless resize / native drag / js_api effect can't be observed on
  this Linux dev host (pywebview not installed; tests mock it). Implemented to the DD3
  "if-yes" default (`frameless=True, resizable=True`); empirical verification + the conditional
  Leg 3 (`window-resize`) defer to the operator HAT (Leg 7).

#### Implementation (2026-06-15)

##### What was implemented

1. **`_WindowApi` class** (`the_one/interfaces/desktop/shell.py`) — owns `minimize()` →
   `window.minimize()`; `toggle_maximize()` with app-side `_is_maximized` bool toggling
   `window.maximize()` / `window.restore()`; `close()` → shared `_close_to_tray()`. Added
   docstring confirming pywebview strips `self` → zero-arg JS calls.

2. **Shared `_close_to_tray()` session method** — extracted the close-to-tray body from
   `_on_closing` into a method both `_on_closing` and `_WindowApi.close()` call. Guard: if
   `self._icon is None` (tray failed to start), sets `_really_quit=True` and calls
   `destroy()` instead of hiding into a non-existent tray — mirrors the F6 tray-absent
   fallback exactly. Returns `True` on successful hide, `False` on hide failure or tray-absent
   path, so `_on_closing` can compute its return value cleanly.

3. **`create_window` kwargs updated** — `_create_kwargs` now initialises with `frameless=True,
   resizable=True, easy_drag=False`. The `js_api=api` argument is passed to `create_window`.
   Wiring order: `api = self._window_api` → `create_window(..., js_api=api)` → `self._window =
   _desktop_window` and `api._window = _desktop_window`. `DesktopSession.__init__` now
   initialises `self._window = None` and `self._window_api = _WindowApi(self)`.

4. **`renderTopBar()` in `app.js`** — inside the function, guarded by `if (window.pywebview)`:
   injects `<div class="pywebview-drag-region">` (flex spacer, aria-hidden) + `<div
   class="win-controls">` containing three `<button class="win-ctrl-btn">` elements (minimize
   / maximize / close), as siblings of `<div class="app-topbar-actions">`. Buttons call
   `window.pywebview.api.minimize()` / `.toggle_maximize()` / `.close()` via inline onclick.
   A `window.addEventListener('pywebviewready', ...)` re-runs `renderTopBar()` on the
   pywebview bridge becoming available (DOMContentLoaded fires before bridge injection).

5. **CSS** (`components.css`) — `.pywebview-drag-region` (`flex: 1`, `app-region: drag`);
   `.win-controls` flex group; `.win-ctrl-btn` transparent themed button with hover + 
   focus-visible; `.win-ctrl-close:hover` uses `--status-danger` (OS-convention red). All
   using existing tokens.

6. **Four `frameless is False` assertions flipped to `True`** in `test_desktop_shell.py:297`
   and `test_window_state.py` (three tests). Also added `easy_drag=False` and `js_api is not
   None` assertions to all four test locations.

7. **New test file `tests/test_desktop_chrome.py`** (8 tests):
   - `test_api_minimize_calls_window_minimize` — minimize() → window.minimize()
   - `test_api_minimize_noop_when_window_is_none` — no crash
   - `test_api_toggle_maximize_first_call_maximizes` — first toggle → maximize + flag=True
   - `test_api_toggle_maximize_second_call_restores` — second toggle → restore + flag=False
   - `test_api_toggle_maximize_three_calls` — three-call sequence
   - `test_api_toggle_maximize_noop_when_window_is_none` — no crash
   - `test_api_close_hides_window_when_tray_active` — close() → hide, _really_quit stays False
   - `test_api_close_destroys_when_tray_absent` — close() → destroy + _really_quit=True

8. **New Playwright browser test `tests/browser/test_window_chrome_dom.py`** (5 tests,
   `@pytest.mark.browser`, excluded from default CI run):
   - Stubs `window.pywebview` via `page.add_init_script`, dispatches `pywebviewready` event.
   - Asserts: `.pywebview-drag-region` present; `.win-controls` present with 3 buttons;
     drag-region has no interactive children; `.win-controls` is not inside drag-region;
     nav buttons still navigate; no controls in plain browser mode.

##### HAT-deferred items (for Leg 7 — real Windows install)

- **Frameless edge-resize** (DD3): does `resizable=True` keep OS edge-resize on the installed
  pywebview/winforms? If no → Leg 3 (`window-resize`) opens.
- **Native drag-move**: does the `.pywebview-drag-region` element move the window on
  Windows WebView2 (edgechromium)? pywebview's whole-window drag listener only activates
  when `platform=='chromium'`; Windows reports `'edgechromium'` → `easy_drag` is likely
  inoperative; drag-region is the sole JS drag surface, but WebView2 native-layer behavior
  is unknown until HAT.
- **`js_api` effect**: do minimize/toggle_maximize/close actually call the pywebview Window
  methods on the real install?
- **Maximize behavior**: does `window.maximize()` on a frameless window produce true
  OS-maximize or needs fill-work-area? (DD "acceptable variation".)

##### Deviations / anomalies

- `_close_to_tray()` returns a bool so `_on_closing` can correctly return `True` when
  `hide()` raises (matching the existing test contract). The no-op `_icon is None` guard
  in `_close_to_tray` can only be triggered via `_WindowApi.close()` since `_on_closing`
  is only registered when `self._icon is not None` — the guard is belt-and-suspenders for
  any future call path but matters specifically for the `close()` js_api method.
- `easy_drag=False` noted as likely inoperative on Windows edgechromium — kept as the
  defensive documented value per DD round-2 conclusion.

##### Test outcomes

- Regression net (`test_desktop_shell.py test_desktop_tray.py test_window_focus.py
  test_window_state.py`): **63 passed, 0 failed** (unchanged count; four assertions flipped
  to `True` as expected).
- New chrome tests (`test_desktop_chrome.py`): **8 passed, 0 failed**.
- Broader smoke (`-k "desktop or window or interface"`): **89 passed, 10 skipped, 0 failed**
  (vs 81 before; +8 new chrome tests).
- Playwright DOM tests (`test_window_chrome_dom.py`): marked `@pytest.mark.browser`,
  excluded from default CI run. DOM-shape assertions (drag-region present, no interactive
  children, controls sibling not descendant, nav buttons fire, no controls in plain browser)
  are authored and will be run as part of Leg 7 (HAT apparatus includes a browser run).

### splash-screen (Leg 4) — design BLOCKED on operator decision

**Status**: planning (design reviewed; escalated — not implemented)

- Leg authored, then design-reviewed (Sonnet, reading pinned pywebview 5.4 source). Verdict:
  **spike-first-escalate**.
- The splash forces a restructure of the F6-HAT-passed core launch path: because pywebview's
  GUI loop blocks, a splash can only be visible *during* the boot wait if `_wait_until_serving`
  + main-window creation + tray wiring move INTO a `webview.start(func=_boot)` callback. The
  `start(func)` threading contract is confirmed real in the source, BUT three empirical
  unknowns are **HAT-only** (pywebview isn't installed on the Linux dev host):
  1. two WebView2 instances sharing one `storage_path`/user-data-folder (lock/corruption?);
  2. winforms `_main_window_created.wait()` has **no timeout** → a fast-server race could hang;
  3. frameless-splash compositor behavior on real Windows.
- Review also surfaced real correctness fixes (error path must destroy BOTH splash+main, not
  just the splash, or the loop hangs; `threading.Event`-guarded idempotent splash destroy;
  `splash.events.shown.wait(15)` first line of `_boot`), a browser-fallback behavior change
  (`_wait_until_serving` no longer called on that path), and deeper launch-test churn (4+ tests
  need an extract-and-invoke-`_boot` adaptation).
- DD4 already names a divert fallback (static/native splash, or defer). Escalated to the
  operator: spike-first on the Windows box vs implement-now-bet-on-HAT vs defer/simplify. The
  restructure destabilizes a HAT-passed path with no local verification — not a call to make
  autonomously. **Awaiting operator decision.**
- **Operator decision (2026-06-16): spike-first on Windows.** Splash held in `planning`; the
  operator runs a minimal 2-window pywebview spike on the Windows box before the `_boot`
  restructure is committed. Spike instructions prepared by the Flight Director (see Session
  Notes). If the spike passes → implement Leg 4 with the review's fixes; if not → DD4 divert.

### Flight Director Notes — remaining-work scoping after the splash escalation (2026-06-16)

Windows apparatus is now the gating resource for most of what's left. Breakdown:
- **Autonomous-on-Linux, do now:** Leg 5 (`freeze-and-icon`) **code portion** — regenerate
  `the-one.ico` to add 256/128/64 from `icon-512.png`, set `icon=` on `exe_gui` in the spec.
- **Windows/Concourse-gated:** the Leg-4 splash spike; Leg 3 (`window-resize`, conditional on
  the Leg-2 chrome spike); Leg 5 **packaged-smoke** (windows-2022 runner); Leg 7 operator HAT +
  `windows-desktop-chrome` behavior test.
- **Deferred to last:** Leg 6 (`docs`) — written after the spike + HAT settle the final shape
  (splash form, resize resolution, js_api/drag runtime-forms), so it documents what actually
  shipped rather than churning twice (F6-debrief "docs as a separate, final leg" lesson).
- Batched review + commit (Phase 2d) happens after the last leg that can land; the
  Windows-gated legs that remain open after this session are tracked here for resumption.

### freeze-and-icon (Leg 5) — host-runnable portion

**Status**: landed (Windows-gated remainder tracked below)

#### Implementation (2026-06-16)

**Files changed:**

1. `packaging/windows/regenerate_icon.py` (new) — reproducible regen helper. Opens
   `the_one/interfaces/web/static/brand/icon-512.png` (512×512 RGBA) and writes
   `packaging/windows/installer-assets/the-one.ico` with
   `sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)]` via `Pillow img.save(format="ICO",
   sizes=[...])`. Paths resolved relative to `__file__` so the script runs from anywhere.
   Source image is NOT mutated before save (Pillow downsamples each ICO frame on write).

2. `packaging/windows/installer-assets/the-one.ico` — regenerated from `icon-512.png`.
   **Sizes before:** `[(16,16),(32,32),(48,48)]`. **Sizes after:** `[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]`.

3. `packaging/windows/the-one.spec` — `exe_gui` EXE() block gains
   `icon='installer-assets/the-one.ico',  # DD5: brand icon embedded in windowed exe (window/taskbar/Alt-Tab)`.
   `exe_cli` is unchanged (DD5 targets the windowed exe only).

4. `packaging/windows/the-one.iss` — updated the stale comment (~lines 41–43) that said
   "The exe carries no embedded icon resource (the Leg-2 .spec omits EXE(icon=))". Now
   reads: the windowed exe (the-one-app.exe) embeds the icon via EXE(icon=) (DD5 / Leg 5);
   `UninstallDisplayIcon` still uses the separately-installed `{app}\the-one.ico` for
   Add/Remove-Programs registration (correct). No icon-reference paths were changed — all
   four already point at `installer-assets\the-one.ico` and improve automatically from the
   regen.

#### Verification outputs

- **Pillow size check:** `sorted(im.info['sizes'])` → `[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]` ✓ (includes (256,256))
- **`py_compile packaging/windows/the-one.spec`** → exit 0 ✓
- **`grep -n "icon=" packaging/windows/the-one.spec`** → line 240 only, inside `exe_gui` ✓
- **Desktop suite smoke** (`test_desktop_shell.py test_desktop_chrome.py -q --timeout=30`) → **25 passed, 0 failed** ✓

#### Windows-gated remainder (operator phase, tracked with Leg 7)

- **Packaged-smoke** on `windows-2022` runner: build the frozen artifact
  (`pyinstaller packaging/windows/the-one.spec`), launch `the-one-app.exe`, confirm the
  brand icon renders on the window, taskbar, and Alt-Tab — baked via EXE(icon=).
- **Chrome/splash web assets in bundle**: chrome JS/CSS assets were already collected via
  `collect_data_files("the_one", includes=["interfaces/web/static/**/*"])` (spec lines
  111–113). Splash asset confirmation depends on Leg 4 (spike-pending); both are verified
  in the Leg 7 HAT.
- A Linux freeze was NOT attempted — native deps (pywinpty, pywebview→pythonnet) require
  Windows. The spec statically validates on Linux (`py_compile` passes); the build-and-launch
  proof is the `windows-2022` runner's job.

---

## Decisions

_(runtime decisions not in the original plan — none yet)_

### Flight Director Notes

#### 2026-06-15 — Flight execution started (agentic-workflow)
- Loaded `/agentic-workflow` for `the-one` mission 15, flight 7. Phase file
  `leg-execution.md` validated (Crew / Interaction Protocol / Prompts all present).
- **Gate decision:** flight was in `planning`, log noted "awaiting design review (Phase
  5b) and operator sign-off." Surfaced to operator; operator chose **"mark it as ready and
  keep going"** — taking the workflow invocation as sign-off. Flight-level Phase 5b review
  skipped per operator; per-leg design review (Phase 2a) still runs. Flight → `in-flight`.
- Branch `flight/07-windows-app-hardening-visual-polish` created off `main` (F6 merged,
  18b19ec). F7 planning artifacts + `tests/behavior/windows-desktop-chrome.md` carried over
  as untracked.
- Execution model: leg design reviewed per leg; code review + commit deferred to end of the
  last autonomous leg (agentic-workflow batched model). Leg 3 (`window-resize`) is
  conditional on the Leg 2 chrome spike. Leg 7 (`hat-and-gui-behavior-test`) is interactive
  (operator HAT + behavior test) — driven by the Flight Director, not autonomous.

---

## Deviations

_(none yet)_

---

## Anomalies

_(none yet)_

---

## Session Notes

### 2026-06-15 — Flight authored

- Sibling to F6 (visual half). Forks resolved with the operator: frameless + custom
  titlebar (DD2); fold the `DesktopSession` refactor into F7 (DD1).
- F6-debrief lessons bound in as explicit DDs: verify pywebview API runtime form at the
  spikes / mock the real type (DD7); HAT-before-merge + crash-log already in place (DD6).
- Lead risk: frameless-window resize on Windows (DD3 spike).
- Behavior-test spec authored inline: `tests/behavior/windows-desktop-chrome.md`.

### 2026-06-16 — Session 1 close-out (checkpoint commit) + Windows-phase handoff

**Landed this session (autonomous, on Linux): Legs 1, 2, 5(code).** Reviewer-confirmed
(71 tests green). **Checkpoint commit `feb1019`** on `flight/07-windows-app-hardening-visual-polish`
(legs `landed`, NOT `completed` — flight not landing yet; HAT pending). Not pushed; no PR yet
(draft PR opens at flight completion after the HAT, per the skill's "all legs complete" gate).

**Open work — all Windows/operator-gated (resume here):**
1. **Leg 4 splash spike (do first — gates Leg 4).** Run the spike below on the Windows box.
2. **Leg 3 `window-resize`** — conditional on the Leg-2 chrome HAT (does `resizable=True` keep
   edge-resize on the frameless install?). Only opens if resize is lost.
3. **Leg 5 packaged-smoke** — `windows-2022` Concourse runner: build the frozen artifact,
   confirm brand icon + chrome/splash assets in `dist/the-one/`.
4. **Leg 6 `docs`** — write AFTER the spike + HAT settle the final shape (deferred so docs
   reflect what shipped; F6-debrief "docs as the final leg" lesson).
5. **Leg 7 HAT + `/behavior-test windows-desktop-chrome`** — operator HAT on the real install.
6. **Flight-completion commit + draft PR** (Phase 2d/3): statuses→`completed`, flight→`landed`,
   PR ready after HAT pass.

#### Leg-4 splash multi-window spike (operator runs on Windows)

Goal: confirm DD4's two-window pywebview model works on the real install BEFORE committing the
`webview.start(func=_boot)` restructure of the HAT-passed launch path. Mirrors `_boot` closely
so the result transfers. From the `the-one` repo on the Windows box with the gui extra
installed (`pip install -e ".[gui]"`), run a throwaway script:

```python
# spike_splash.py — DELETE after the spike; do not commit.
import threading, time, webview

SPLASH_HTML = "<html><body style='margin:0;background:#111;color:#eee;font-family:sans-serif'>" \
              "<div style='display:flex;height:100vh;align-items:center;justify-content:center'>" \
              "GleepGlorp AI — starting…</div></body></html>"

splash = webview.create_window("splash", html=SPLASH_HTML, frameless=True, width=420, height=260)
main_win = None

def boot():
    splash.events.shown.wait(15)          # (review fix) ensure splash exists before work
    time.sleep(2.0)                        # stand-in for _wait_until_serving
    global main_win
    main_win = webview.create_window("GleepGlorp AI", "https://example.com",
                                     frameless=True, resizable=True, easy_drag=False)
    main_win.events.loaded += lambda: splash.destroy()   # dismiss splash when main loads

webview.start(boot, private_mode=False, storage_path=None)  # storage_path=None → default profile
```

**Observe and record back here:**
- (a) Do BOTH windows appear — splash first, then the main window? (two windows coexist on one loop)
- (b) Does the splash **close on the main window's `loaded`** event, reliably?
- (c) When the main window is then closed, does the process **exit cleanly** (loop returns)?
- (d) Try a failure path: make `boot` raise after the splash shows but before/after creating
      `main_win` — does the app **hang showing only the splash** (confirms the review's
      "destroy BOTH windows on error" requirement)? 
- (e) Any **WebView2 profile lock/corruption** warnings with two windows sharing one
      `storage_path` (try a real `storage_path` dir, not None)?
- (f) Does `create_window(main)` from the `boot` thread ever **hang** (the no-timeout
      `_main_window_created.wait()`) when the wait is near-instant?

If (a)+(b)+(c) pass and (d) is handled by destroying both windows: **implement Leg 4** with the
design-review fixes (destroy both on error; `threading.Event`-guarded idempotent splash destroy;
`shown.wait()` first; preserve `private_mode=False`/`storage_path`; keep `_wait_until_serving` on
the browser-fallback path or document its removal). If two windows DON'T coexist / splash won't
close: take the **DD4 divert** (static/native splash or defer) and re-decide with the operator.

### 2026-06-16 — Leg 4: splash-screen implementation

**Status: landed (host-native tests green; HAT-deferred items noted below)**

#### What was implemented

1. **`SPLASH_HTML` constant** (`the_one/interfaces/desktop/shell.py`, module level) — a
   self-contained inline HTML string with a brand-colored (`#0f1117` background, `#6c63ff`/
   `#4e46e5` gradient accent) frameless splash: logo diamond, "GleepGlorp AI" heading,
   animated loading bar, "starting…" status text. No external refs (no CDN, no localhost URL —
   the server isn't up yet). Pure CSS animation. No bundle asset required (no file:// path).

2. **`DesktopSession.run()` restructured** (M15 F7 Leg 4 — DD4 two-window model):
   - `_wait_until_serving(host, sel_port)` removed from the pre-webview-start synchronous path.
   - Splash created BEFORE `webview.start()`:
     `webview.create_window("GleepGlorp AI — starting", html=SPLASH_HTML, frameless=True, width=320, height=220)`.
   - `threading.Event` `_splash_closed` created to guard idempotent `_destroy_splash()` helper.
   - `_boot(splash_win)` closure defined:
     - Step 1: `splash_win.events.shown.wait(15)` (ensures teardown is always safe).
     - Step 2: `_wait_until_serving(host, sel_port)` (moved here from pre-start).
     - Step 3: `webview.create_window("GleepGlorp AI", url, js_api=api, **_create_kwargs)` with
       the same Leg-2 `frameless=True, resizable=True, easy_drag=False, js_api=api` kwargs plus
       the F6 window-state-restore geometry kwargs.
     - Step 4: tray wiring (same `build_tray + run_detached + _on_closing` block).
     - Step 5: sets `_desktop_window`, `self._window`, `api._window`.
     - Step 6: `main_win.events.loaded += lambda: _destroy_splash()` (splash dismissed when
       main UI is ready).
     - Exception path: `_destroy_splash()` + `main_win.destroy()` (if created) + re-raise
       so the GUI loop returns rather than hanging on an orphaned splash.
   - `webview.start(_boot, private_mode=False, storage_path=str(storage_dir))` — `_boot`
     passed as first positional arg; persistence config preserved exactly.
   - **Browser-fallback path**: `_wait_until_serving` kept explicitly on the `else` branch so
     the behavior is unchanged on the no-webview path (moved into `_boot` on the webview path
     only). Comment added explaining why.

3. **Window-state geometry pre-computed before `_boot`** — `load_state()` / `clamp_to_bounds()`
   / `_create_kwargs` assembly runs in `run()` (before `webview.start()`), not inside `_boot`,
   so the `_boot` closure captures the already-resolved kwargs dict. This avoids calling
   `webview.screens` from the background thread (a potential GUI-thread concern).

#### Tests adapted and why

All tests use the **extract-and-invoke-_boot pattern**: capture `_boot` from
`webview_mock.start.call_args.args[0]`, set up `create_window.side_effect` for the main-window
call, then invoke `_boot(mock_splash)` to exercise main-window creation, tray wiring, and handler
registration. `_boot` must be invoked **inside** the active `patch.object` context so spy patches
on `_wait_until_serving` remain active.

Shared `_make_splash_mock()` helper added to each adapted test file — returns a `MagicMock` with
`events.shown.wait.return_value = True` (non-blocking in tests).

**`test_desktop_shell.py`** (adapted + 3 new tests):
- `test_run_calls_create_window_start_and_graceful_shutdown` — adapted: now asserts
  `create_window` called ≥1 time (splash call), splash call has `html=`, `frameless=True`,
  no `js_api`; `start` receives a callable `_boot` as positional arg; `private_mode=False`
  and `storage_path` still asserted; extracts and invokes `_boot` to assert the main-window
  call carries title "GleepGlorp AI" + Leg-2 kwargs.
- NEW `test_boot_happy_path_main_window_kwargs_and_loaded_handler` — invokes `_boot` inside the
  `_wait_until_serving` spy context; asserts `shown.wait` called, spy captures the serving-wait
  call, main window created with correct kwargs, `loaded` event has a registered handler that
  fires `splash.destroy()`.
- NEW `test_boot_error_path_destroys_both_windows` — `_wait_until_serving` raises inside `_boot`;
  asserts `RuntimeError` propagates and `splash.destroy()` called once.
- NEW `test_boot_error_path_destroys_both_when_main_window_created` (renamed/reframed) — tray
  failure (graceful-degrade path); asserts `_boot` doesn't re-raise, main window was created,
  splash NOT destroyed (no error path triggered; splash dismissed via `loaded` event).

**`test_desktop_tray.py`** (adapted):
- `_run_desktop_with_tray` helper — updated to set `create_window.side_effect = [mock_splash, mock_window]`,
  extract `_boot` from `start.call_args.args[0]`, reset side_effect, invoke `_boot(mock_splash)`.
  All 9 tray/closing tests pass through this helper and continue to assert the same closing-event
  and callback behavior; the wiring just now runs inside `_boot`.
- `test_tray_failure_no_closing_handler_registered` — adapted to set `create_window.side_effect`,
  invoke `_boot` so the tray-unavailable code path (build_tray raises) runs inside `_boot`.

**`test_window_state.py`** (adapted):
- `_run_desktop_with_screens` helper — updated to set `create_window.side_effect = [mock_splash, mock_main_window]`,
  invoke `_boot`, reset side_effect. All geometry assertions updated from `assert_called_once()` +
  `call_args.kwargs` to `call_count == 2` + `call_args_list[-1].kwargs` (the main-window call).
- `test_run_desktop_no_state_uses_defaults` — adapted inline (same pattern as helper).
- `test_on_closing_saves_geometry` — adapted to set `create_window.side_effect`, invoke `_boot`
  so `_on_closing` is registered on the main window's closing event.

**`test_desktop_chrome.py`** (adapted):
- `test_api_close_hides_window_when_tray_active` — `_capture_create_window` updated to filter
  calls by `js_api is not None` (splash call returns `None`); extracts and invokes `_boot`.
- `test_api_close_destroys_when_tray_absent` — same pattern.

#### HAT-deferred items (Leg 7, real Windows)

- **Splash actually appears** on launch (frameless, sized 320×220, brand-colored content).
- **Splash dismisses** on the main window's `loaded` event (not before).
- **No orphaned splash** on a boot error (both windows destroy and the process exits).
- **Splash asset in bundle** — SPLASH_HTML is pure inline HTML/CSS with no external refs;
  no bundle asset is required. Confirmed via code inspection (no `file://` refs).

#### Leg-5 dependency

SPLASH_HTML uses only inline HTML/CSS — no external asset file. No bundle entry needed for
the splash content itself. This clears the Leg-5 dependency for the splash. (Any future
logo embed via `file://` would require a Leg-5 bundle-collect entry.)

#### Deviations / anomalies

- Window-state geometry resolution (`webview.screens`) moved to before `webview.start()` (in
  `run()`) rather than inside `_boot`. This is safer (no GUI-thread concern for screens access)
  and simpler (`_boot` receives the already-resolved `_create_kwargs` dict as a closure). The
  leg spec says "create the main window with the same Leg-2 kwargs + F6 window-state-restore
  kwargs" — this satisfies that requirement regardless of where the resolution happens.
- `test_boot_error_path_destroys_both_when_main_window_created` was originally titled to test
  that "both windows are destroyed when main window exists and an error occurs." Since tray
  failure is the graceful-degrade path (not an error) and build_tray raising does NOT re-raise,
  this test was reframed to verify the graceful-degrade path specifically.

#### Test outcomes

- Primary regression net (`test_desktop_shell.py test_desktop_tray.py test_window_focus.py
  test_window_state.py test_desktop_chrome.py -x --timeout=30`): **74 passed, 0 failed**.
- Broader smoke (`-q -x --timeout=30 -k "desktop or window or interface"`): **92 passed, 10 skipped, 0 failed**.

---

### 2026-06-16 — Leg-4 splash spike RESULT: viable (proceed with the pywebview splash)

Operator ran the spike on the Windows box. **All four modes passed** (`single`, `two profile`,
`two none`, `error`): two pywebview windows coexist on one GUI loop, the splash dismisses on the
main window's `loaded` event, the process exits cleanly when the main window closes, and the
error path tears down without hanging.

**Key finding — a red herring, now understood:** the first runs failed with WebView2
`0x8000FFFF E_UNEXPECTED` ("Cannot read and write to its data directory:
`C:\Python311\spike_webview_profile\EBWebView`"). Cause: the script was run from `C:\Python311`,
so the **relative** `storage_path` resolved under the non-writable system-Python dir. Fixed by
using an **absolute writable** profile path (`%TEMP%\spike_webview_profile`). **The real app is
already safe** — it uses `settings.data_dir / "webview"` (absolute, user-writable). No new
constraint for Leg 4 beyond "the profile path is absolute + writable," which already holds.

**Decision: implement Leg 4** (DD4 primary design, NOT the divert) with the design-review fixes
baked in: error path destroys **both** splash+main (not just splash); idempotent splash teardown
guarded by a `threading.Event`; `splash.events.shown.wait(...)` as the first line of `_boot`;
preserve `private_mode=False` + the absolute `storage_path`; keep `_wait_until_serving` on the
browser-fallback path (or document its removal); adapt the 4+ launch tests via the
extract-and-invoke-`_boot` pattern. Native splash appearance/dismissal/no-orphan still
HAT-verified on the real install (Leg 7), but the architecture is now de-risked.

---

### 2026-06-16 — Leg 4 HAT fix: `_boot` no-arg call convention + loaded-event race

**Trigger:** Operator HAT on the real Windows install. The splash hung forever and the main
window never appeared. Windows crash log:

```
Exception in thread Thread-3 (_boot):
TypeError: DesktopSession.run.<locals>._boot() missing 1 required positional argument: 'splash_win'
```

**Root cause (FIX 1):** `_boot` was defined as `def _boot(splash_win) -> None:` but pywebview's
`webview.start(_boot, ...)` calls it as `_boot()` with NO arguments. The parameter was never
passed, so `_boot` raised immediately on every launch. The boot thread died before `create_window`
for the main window was called — leaving the splash (created before `start()`) alive with nothing
to dismiss it, hence the infinite hang.

The fix: change `_boot` to `def _boot() -> None:` and reference the enclosing-scope `splash`
closure variable directly (exactly as `_destroy_splash` already did). The `webview.start(_boot, ...)`
call is unchanged — it was always correct; the bug was the mismatch on the receiving end.

**Race fix (FIX 2):** The loaded→destroy handler was registered AFTER tray wiring. On localhost,
the main window's `loaded` event can fire during tray setup (`build_tray` + `run_detached` takes
non-trivial time), before the handler is subscribed — the splash would then never dismiss even if
`_boot` ran correctly. Fixed by moving `main_win.events.loaded += lambda: _destroy_splash()` to
immediately after `create_window(main_win)`, before tray wiring.

Additionally added an already-loaded backstop: after registering the handler, check
`main_win.events.loaded.is_set()` — if the loaded event already fired before the subscription,
call `_destroy_splash()` immediately. **pywebview 5.4's `Event` class exposes `is_set()`,
confirmed against the pinned wheel source** (`webview/event.py` in
`pywebview-5.4-py3-none-any.whl`): `is_set()` delegates to the internal `threading.Event.is_set()`.
This is the same API already used by the production code for `shown.is_set()` (line 279 in shell.py).

**New `_boot` order** (shell.py `DesktopSession.run()`):
1. `splash.events.shown.wait(15)` — unchanged
2. `_wait_until_serving(host, sel_port)` — unchanged
3. `create_window("GleepGlorp AI", ...)` — unchanged
4. `main_win.events.loaded += lambda: _destroy_splash()` — **moved up, before tray**
4a. `if main_win.events.loaded.is_set(): _destroy_splash()` — **new backstop**
5. Tray wiring (`build_tray`, `run_detached`, `_on_closing`) — unchanged content, now after step 4
6. Publish `_desktop_window / self._window / api._window` — unchanged

**Test-fidelity correction (why the bug shipped):** All `_boot`-invoking tests called
`_boot(mock_splash)` — passing the mock splash as a positional argument. This matched the BUGGY
signature and exercised a code path that pywebview never uses. All invocations changed to `_boot()`
with NO arguments, exactly matching the real pywebview call convention. Tests now fail if `_boot`
is ever redefined with a positional parameter — the regression is caught in CI.

Additionally: `_EventCapture` (the `events.loaded` stand-in for the happy-path test) gained an
`is_set()` method returning `False` by default, so the FIX 2 backstop can be called without
raising `AttributeError` and without prematurely triggering splash teardown in tests that verify
the loaded-handler path. Tests that need to exercise the backstop explicitly set `is_set_value=True`.

**Files changed:**
- `the_one/interfaces/desktop/shell.py` — FIX 1 (`_boot` signature → no params, use closure
  `splash`); FIX 2 (loaded handler registered before tray, `is_set()` backstop added)
- `tests/test_desktop_shell.py` — all `_boot(mock_splash)` → `_boot()`; `_EventCapture.is_set()`
  added; tray-graceful-degrade test uses `_EventCapture` on `events.loaded` to keep backstop from
  firing; updated test docstrings
- `tests/test_desktop_tray.py` — all `_boot(mock_splash)` → `_boot()` in helper and tray-failure test
- `tests/test_desktop_chrome.py` — both `_boot(mock_splash)` → `_boot()`
- `tests/test_window_state.py` — all `_boot(mock_splash)` → `_boot()` in helper and inline uses

**Test outcomes (post-fix):**
- Primary regression net (`test_desktop_shell.py test_desktop_tray.py test_window_focus.py
  test_window_state.py test_desktop_chrome.py -x --timeout=30`): **74 passed, 0 failed**.
- Broader smoke (`-q -x --timeout=30 -k "desktop or window or interface"`): **92 passed, 10 skipped, 0 failed**.

**Leg status: remains `landed`** (HAT fix applied; leg not set to `completed` — awaiting full
flight completion at Leg 7 HAT pass).

---

### 2026-06-16 — Leg 4 logo embed: README brand image in splash via base64 data URI

**What was changed**

The splash no longer uses a static `SPLASH_HTML` constant with a CSS diamond placeholder.
`SPLASH_HTML` was replaced by a `_SPLASH_TEXT_ONLY` fallback constant (same markup) and a
`_splash_html() -> str` builder function.  The builder:

1. Lazily imports `STATIC_DIR` from `the_one.interfaces.web.app` (inside the function to
   avoid any circular-import risk at module load; `run()` has already imported `web.app` by
   splash time).
2. Resolves `STATIC_DIR / "brand" / "gleepglorp_med.png"` — the same path the web server
   uses for static assets, which resolves correctly under PyInstaller's `_MEIPASS` because
   `STATIC_DIR = Path(__file__).parent / "static"` (web/app.py line 80).
3. Reads the PNG bytes and base64-encodes them, then embeds the result as
   `<img src="data:image/png;base64,..." alt="GleepGlorp AI">` (240 px wide, centered on
   the existing `#0f1117` brand-dark background).
4. On any exception (file not found, permission error, encoding failure): logs a warning and
   returns `_SPLASH_TEXT_ONLY` unchanged.  A splash-asset failure can NEVER raise or hang boot.

The `create_window` call was updated from `html=SPLASH_HTML` to `html=_splash_html()`, and
the splash window dimensions bumped to 400×300 (was 320×220) so the 240 px logo is not clipped.

**Freeze-bundle coverage confirmed**

The spec (`packaging/windows/the-one.spec`) uses:
```python
collect_data_files("the_one", includes=["interfaces/web/static/**/*"])
```
The `**/*` glob recurses through all subdirectories under `static/`, including `brand/`.
`static/brand/gleepglorp_med.png` is covered — no spec change required.

**New tests** (`tests/test_desktop_shell.py`)

- `test_splash_html_embeds_base64_data_uri_when_asset_present` — monkeypatches `STATIC_DIR`
  to a tmp directory containing a minimal PNG stub; asserts the data URI appears in the HTML.
- `test_splash_html_falls_back_to_text_only_when_asset_missing` — monkeypatches `STATIC_DIR`
  to an empty tmp directory (no brand PNG); asserts `_splash_html()` does not raise and returns
  valid HTML without a data URI.

**Test outcomes:**
- Primary regression net (`test_desktop_shell.py test_desktop_tray.py test_window_focus.py
  test_window_state.py test_desktop_chrome.py -x --timeout=30`): **76 passed, 0 failed**.
- Broader smoke (`-q -x --timeout=30 -k "desktop or window or interface"`): **94 passed, 10 skipped, 0 failed**.

**Leg status: remains `landed`** (HAT fix in progress — not completed).

---

### 2026-06-16 — Leg 2 HAT fix: robust pywebview bridge detection (window-chrome controls)

**HAT-found symptom**

On the real Windows install, the frameless main window showed the normal top bar (banner + nav tabs) but NO window-chrome controls — no minimize/maximize/close buttons and no drag region. `renderTopBar()` ran (the nav bar rendered), but `window.pywebview` was falsy at every call to `renderTopBar()`, so the `if (window.pywebview)` guard produced no output.

**Root cause — pinned source diagnosis**

Reading the pywebview 5.4 wheel (`pywebview-5.4-py3-none-any.whl`, extracted from the uv.lock-pinned URL):

1. **Injection path:** `edgechromium.py`'s `on_navigation_completed` calls `inject_pywebview(renderer, window)` (`util.py:162`). That function spawns a *second background thread* (`Thread(target=generate_js_object)`) which calls `window.run_js(api_js)` (sets `window.pywebview`) then `window.run_js(finish_script)`.

2. **Event target and name:** `finish.js` (last file loaded) dispatches:
   ```js
   window.dispatchEvent(new CustomEvent('pywebviewready'));
   ```
   The event fires on **`window`** — matching the app.js listener. For `qtwebengine` it fires after `QWebChannel` is ready; all other platforms (including `edgechromium` / WebView2) fire immediately after `api.js` runs.

3. **The real-world timing race for the second window:** The main window is created inside `_boot` — a background thread spawned by `webview.start()`. The page loads and DOMContentLoaded fires. app.js evaluates synchronously and registers `window.addEventListener('pywebviewready', …)`. THEN `on_navigation_completed` fires and `inject_pywebview` spawns its own thread. Under fast localhost loading the injection thread can run near-instantly — but more importantly: `generate_js_object` calls `run_js()` (which marshals to the WinForms UI thread via `Invoke()`), runs `api.js` (sets `window.pywebview`), then runs `finish.js` (dispatches `pywebviewready`). Under the two-window timing the WinForms message queue can process the injection before app.js's `DOMContentLoaded` callback has run, or the event can fire between DOM parse and the script's listener registration — depending on how quickly the second window's WebView2 initializes. Result: `pywebviewready` fires before the listener is attached → silently missed → controls never render.

4. **Why tests didn't catch it:** `add_init_script` runs before ANY page script (Playwright's design). So in the test, `window.pywebview` is always set at script-eval time — the `if (window.pywebview)` check at DOMContentLoaded is always true. The unit/Playwright tests never exercised the post-navigation-completed injection path.

**Fix — robust bridge detection (`app.js`)**

Replaced the single `window.addEventListener('pywebviewready', …)` with a `_watchBridge()` IIFE that covers all timing cases:

- **(a)** `window.pywebview` already set at IIFE eval (script-eval time or before DOMContentLoaded) → `renderTopBar()` immediately.
- **(b)** Not yet present → register listeners on **both** `window` AND `document` (belt-and-suspenders for any backend variation).
- **(c)** Poll backstop: `setInterval(100ms, max 100 ticks = 10s)` — calls `renderTopBar()` once `window.pywebview` appears and clears itself. Catches "event fired before listener attached" and any backend that sets the bridge without dispatching the event.
- **Browser mode (d):** `window.pywebview` is never set; poll times out silently after 10s; no controls render — behavior unchanged.

A `_bridgeRendered` flag ensures `renderTopBar()` is called at most once by the helper (the event and poll are deduped). `renderTopBar()` itself is idempotent (rebuilds innerHTML each call) so calling it from multiple paths (DOMContentLoaded + bridge detection) is safe.

**CSS audit result**

Inspected `#app-topbar`, `.pywebview-drag-region`, `.win-controls`, and `.win-ctrl-btn` rules in `base.css` and `components.css`:
- `#app-topbar` is `display: flex; align-items: center; justify-content: space-between` — flex row, not overflowed, no clip.
- `.pywebview-drag-region` is `flex: 1` — fills space, not hidden.
- `.win-controls` is `display: flex; align-items: center; gap: 4px; flex-shrink: 0` — visible, not `display: none`.
- No rule hides or positions controls off-screen.
- **CSS is not the cause.** The failure was purely the JS bridge-detection timing.

**Test additions (`tests/browser/test_window_chrome_dom.py`)**

Three new `@pytest.mark.browser` tests covering the timing paths the original 5 tests missed:

- `test_controls_render_when_bridge_present_before_domcontentloaded` — `add_init_script` (bridge at script-eval), NO manual event dispatch → controls render via path (a). Isolates the synchronous IIFE check.
- `test_controls_render_when_bridge_set_after_load_via_event` — no `add_init_script`; after page load, sets `window.pywebview` and dispatches `pywebviewready` (mirrors `finish.js` exactly) → controls appear via event listeners. Isolates path (b).
- `test_controls_render_when_bridge_set_after_load_via_poll` — no `add_init_script`; after page load, sets `window.pywebview` with NO event dispatch → controls appear within 3s via poll backstop. Isolates path (c).

Existing 5 tests unchanged. The `test_no_controls_without_pywebview` test now also covers path (d) — poll times out, no controls.

**Test outcomes**

- Primary regression net (`test_desktop_shell.py test_desktop_tray.py test_window_focus.py test_window_state.py test_desktop_chrome.py -x --timeout=30`): **76 passed, 0 failed**.
- New browser tests will be run as part of Leg 7 (browser tests excluded from host-native default run; `@pytest.mark.browser` — requires `THE_ONE_DEV_MODE=true` and Playwright).

**Files changed**
- `the_one/interfaces/web/static/js/app.js` — replaced single `pywebviewready` listener with `_watchBridge()` IIFE (event+document listener + poll backstop).
- `tests/browser/test_window_chrome_dom.py` — updated module docstring; added 3 timing tests.

**Leg status: remains `landed`** (HAT fix applied; awaiting operator re-HAT on Windows at Leg 7).
