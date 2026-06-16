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
