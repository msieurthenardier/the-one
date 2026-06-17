# Leg: themed-native-frame

**Status**: completed
**Flight**: [Windows Native App Hardening — Visual Polish](../flight.md)

## Objective

Take the DD3 divert: revert the main window to a **native OS frame** (`frameless=False`) — which
provides drag, minimize/maximize/close, resize, and snap natively — keep the launch splash and
the brand taskbar/title-bar icon, and remove the frameless custom chrome that WebView2 wouldn't
cooperate with.

## Context — the pivot (see flight log "PIVOT 2026-06-16")

Operator chose **DD2-alt (themed native frame)** after the HAT (builds #18–#20) showed the
frameless custom chrome fighting WebView2 (edgechromium): js_api buttons didn't fire, titlebar
drag was inert (`easy_drag`/`.pywebview-drag-region` only work on `platform=='chromium'`; CSS
`app-region` is Electron-only), and frameless loses native resize. pywebview frameless targets
CEF/GTK/Qt, not WebView2. **F4/F6 shipped `frameless=False` and HAT-passed** — this returns to
that known-good window and layers on only the F7 branding (splash + icon). Supersedes DD2/DD3.

## Inputs (current committed state on the branch)

- `the_one/interfaces/desktop/shell.py` — Leg-2 chrome: `_create_kwargs = {"frameless": True,
  "resizable": True, "easy_drag": False}`, `js_api=api` on `create_window`, the `_WindowApi`
  class + `self._window_api`, and `api._window` wiring. Leg-4 splash (`_splash_html`, `_boot`,
  `_destroy_splash`) — **KEEP**. The shared `_close_to_tray()` + `_on_closing` — **KEEP**.
- `the_one/interfaces/web/static/js/app.js` — Leg-2 `renderTopBar()` window-control injection
  (`.win-controls` + `.pywebview-drag-region`, `window.pywebview`-gated) and the `_watchBridge`
  IIFE (bridge poll). **REMOVE** — revert `renderTopBar()` to the F6 banner+nav form.
- `the_one/interfaces/web/static/css/components.css` — `.win-controls`, `.win-ctrl-btn`,
  `.win-ctrl-close`, `.pywebview-drag-region` rules. **REMOVE** (now unused).
- Tests: `tests/test_desktop_chrome.py` (js_api unit tests), `tests/browser/test_window_chrome_dom.py`
  (win-controls DOM + bridge-timing), and the `frameless`/`easy_drag`/`js_api` assertions in
  `tests/test_desktop_shell.py` + `tests/test_window_state.py`.
- `tests/behavior/windows-desktop-chrome.md` — steps 3–6 assume custom controls/drag/resize.

## Outputs

- Main window created with the native frame (revert `_create_kwargs` to `{"frameless": False}`;
  drop `easy_drag` and `js_api=`). The native title bar shows "GleepGlorp AI" + the brand icon.
- Frameless custom chrome fully removed: `_WindowApi`/`self._window_api`/`api` wiring out of
  shell.py; the window-control + drag-region injection and `_watchBridge` out of app.js; the
  win-controls/drag-region CSS out of components.css.
- Splash (Leg 4) and brand icon (Leg 5) unchanged and still working.
- Native window-close still routes to F6 close-to-tray (native X → `events.closing` →
  `_on_closing` → `_close_to_tray`). Tray Quit, focus, window-state restore all intact.
- Tests updated to the native-frame reality; behavior-test spec revised (steps 3–6).

## Acceptance Criteria

- [ ] `create_window` is called with **`frameless=False`, `resizable=True`** and NO `js_api=`
      and NO `easy_drag` (native frame). (Keep `resizable=True` explicit so the existing
      `resizable is True` assertion at `test_desktop_shell.py:461` stays valid.)
- [ ] `_WindowApi` class, `self._window_api`, the `api = ...; js_api=api; api._window = ...`
      wiring are removed from shell.py. `self._window = main_win` / `_desktop_window = main_win`
      (used by `focus_window` + window-state) are **kept**.
- [ ] `_on_closing` is still registered on the native window's `events.closing` and routes to
      `_close_to_tray()` — the **native X hides to tray** (F6 behavior preserved), tray Quit
      exits cleanly. `_close_to_tray()` and the tray-absent fallback are unchanged.
- [ ] `renderTopBar()` no longer injects window controls or a drag region — reverted to the F6
      banner + nav form. No `window.pywebview` gating, no `_watchBridge` IIFE in app.js.
- [ ] The win-controls / `.pywebview-drag-region` CSS rules are removed from components.css.
- [ ] The splash (Leg 4) still appears with the logo and dismisses on load; the brand icon
      (Leg 5) is unchanged.
- [ ] Tests updated, no dead references: delete `tests/test_desktop_chrome.py` and
      `tests/browser/test_window_chrome_dom.py` (100% Leg-2-chrome specific). Flip the **five
      MAIN-window** `frameless` assertions to `False`: `test_desktop_shell.py:358` and `:460`,
      and `test_window_state.py:342`, `:381`, `:487`. **The SPLASH assertion at
      `test_desktop_shell.py:322` STAYS `True`** (the splash window remains frameless — do NOT
      flip it). Drop the `easy_drag is False` and `js_api is not None` assertions at
      `test_desktop_shell.py:359/360,462/463` and `test_window_state.py:343/344,382/383,488/489`.
      KEEP the `resizable is True` assertion at `:461`. The `js_api is None` splash check at
      `:324` becomes moot — remove it. F6 regression suites green: `test_desktop_shell.py`,
      `test_desktop_tray.py`, `test_window_focus.py`, `test_window_state.py`.
- [ ] The behavior-test spec is **fully** revised (not just steps 3–6) and **renamed** to
      `windows-native-frame-splash` (the "chrome" name now misleads): Intent, Observables,
      Out of Scope, and Steps 1 + 3–7 re-expressed against the **native** OS frame (its
      min/max/close + drag + edge-resize) + splash + brand icon; the frameless / custom-titlebar
      / `js_api` / `window.pywebview`-gated language removed. Update all references to the old
      slug — leg `07-hat-and-gui-behavior-test.md`, the flight DD6/Verification/legs list, and
      the flight log — to the new slug.
- [ ] `the-one-app` byte-behaves like F6 + splash + icon; `serve`/`chat`/`version` unaffected.

## Verification Steps

- `.venv/bin/python -m pytest tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_focus.py tests/test_window_state.py -x --timeout=30`
- `grep -n "frameless" the_one/interfaces/desktop/shell.py` → `frameless=False`.
- `grep -rn "win-controls\|pywebview-drag-region\|_watchBridge\|_WindowApi\|js_api" the_one/ tests/` → only intentional/removed; no dead refs.
- **Windows re-HAT (operator, after rebuild):** native frame with brand icon + title; native
  min/max/close/drag/resize all work; native X → hides to tray; tray Quit exits; splash shows
  the logo + dismisses; window-state restore + theme persist (F6 regression).

## Implementation Guidance

1. **shell.py** — set `_create_kwargs = {"frameless": False, "resizable": True}`. Remove
   `js_api=api` from the `create_window` call; remove the `api = self._window_api` and
   `api._window = main_win` lines; remove the `_WindowApi` class (shell.py:285–328) and the
   `self._window_api = _WindowApi(self)` attribute in `__init__`. KEEP `self._window = main_win`
   and `_desktop_window = main_win`. Also **scrub the now-stale `_boot` comments/docstring**:
   drop the "Leg-2 kwargs", `easy_drag`/`js_api`/`pywebview-drag-region` comment lines
   (shell.py:664–668) and the step that sets `api._window` from the `_boot` docstring. Leave the
   splash/`_boot`/`_destroy_splash`/`_close_to_tray`/`_on_closing` logic intact — `_on_closing`
   stays wired to `main_win.events.closing` exactly as now (native X → `_on_closing` →
   `_close_to_tray`, verified independent of the js_api removal).
2. **app.js** — revert `renderTopBar()` to the F6 version (banner img + `.app-topbar-actions`
   nav buttons only). Remove the `windowControlsHtml` block and the `_watchBridge` IIFE + its
   comment. Leave the rest of app.js untouched.
3. **components.css** — delete the `.pywebview-drag-region`, `.win-controls`, `.win-ctrl-btn`,
   `.win-ctrl-btn:hover/:focus-visible`, `.win-ctrl-close:hover` rules.
4. **Tests** — `git rm` `tests/test_desktop_chrome.py` and `tests/browser/test_window_chrome_dom.py`
   (entirely Leg-2-chrome specific). Flip the FIVE main-window `frameless` assertions to `False`
   (shell `:358,:460`; window_state `:342,:381,:487`); **leave the splash assertion `:322` at
   `True`**. Drop the `easy_drag`/`js_api` assertions (shell `:359,:360,:462,:463` + the splash
   `js_api is None` at `:324`; window_state `:343,:344,:382,:383,:488,:489`). KEEP `resizable is
   True` at `:461`. Ensure no test imports `_WindowApi`.
5. **Behavior spec** — rename `tests/behavior/windows-desktop-chrome.md` →
   `tests/behavior/windows-native-frame-splash.md` (and the slug field inside). Fully revise:
   Intent + Observables + Out of Scope drop the frameless/custom-titlebar/`js_api`/
   `window.pywebview` language; Step 1 = native-framed window opens (OS title bar) after the
   splash; Steps 3–6 = the **native** title-bar min/max/close + drag + edge-resize; Step 7 =
   the **native X** hides to tray (F6 path). Keep Steps 2 (taskbar icon), 8–10 (Quit, browser
   mode, F6 regression). Update every reference to the old slug: leg
   `07-hat-and-gui-behavior-test.md`, the flight `flight.md` (DD6 / Verification / legs list),
   and `flight-log.md`.
6. Run the F6 suites + a broad smoke; confirm no dead references.

## Edge Cases

- **Native close → tray:** verify `_on_closing` is still added to `events.closing` (it is —
  unchanged); with a native frame the OS X fires `events.closing` → `_on_closing` → hide to
  tray (F6). Do NOT remove that wiring with the js_api removal.
- **`focus_window` / window-state:** both read `_desktop_window` / `self._window` — keep those
  assignments; only the `_WindowApi`/`js_api` plumbing goes.
- **Splash still frameless:** the splash window stays `frameless=True` (a brief borderless logo
  window is correct; it auto-dismisses). Only the MAIN window reverts to a native frame.
- **No browser-mode fallout:** removing the `window.pywebview`-gated controls means browser mode
  is trivially unchanged (it never showed them anyway).

## Files Affected

- `the_one/interfaces/desktop/shell.py` — frameless→False; remove `_WindowApi`/`js_api`.
- `the_one/interfaces/web/static/js/app.js` — revert `renderTopBar()`, remove `_watchBridge`.
- `the_one/interfaces/web/static/css/components.css` — remove win-controls/drag-region rules.
- `tests/test_desktop_chrome.py`, `tests/browser/test_window_chrome_dom.py` — removed.
- `tests/test_desktop_shell.py`, `tests/test_window_state.py` — 5 main-window frameless→False
  (splash stays True), drop js_api/easy_drag asserts, keep resizable assertion.
- `tests/behavior/windows-desktop-chrome.md` → **renamed** `tests/behavior/windows-native-frame-splash.md`,
  fully revised to the native frame.
- Reference updates for the slug rename: `legs/07-hat-and-gui-behavior-test.md`, `flight.md`
  (DD6 / Verification / legs list), `flight-log.md`.

---

## Post-Completion Checklist

**Per this flight's batched model — set status to `landed` (NOT `completed`); do NOT commit or
signal `[COMPLETE:leg]`. Re-HAT on Windows after rebuild before the flight lands.**

- [ ] All non-HAT acceptance criteria verified host-native
- [ ] Update flight-log.md with the implementation + the revised behavior-test spec
- [ ] Set this leg's status to `landed`; check off in flight.md
- [ ] Rebuild (Concourse #N) + operator re-HAT (native frame + splash + icon) before landing
