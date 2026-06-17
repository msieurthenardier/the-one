# Flight: Windows Native App Hardening — Visual Polish

**Status**: completed

> **PIVOT during execution (2026-06-16) — DD3 divert to DD2-alt (themed native frame).** The
> frameless custom-chrome approach (DD2/DD3 below, and Leg 2) was abandoned after the HAT showed
> it fights Windows WebView2 (drag/resize/js_api inert on edgechromium). The shipped window is a
> **native OS frame** (`frameless=False`, the F4/F6 known-good window) + the launch splash + the
> brand icon. DD2/DD3 and the frameless checkpoints below are preserved as the original plan;
> the live record is the flight-log "PIVOT" entry + Leg 8 (`themed-native-frame`). HAT passed on
> build #22 (run log: `tests/behavior/windows-native-frame-splash/runs/2026-06-17-00-47-21.md`).

**Mission**: [Native Desktop Installers](../../mission.md)

## Contributing to Criteria

- [x] *(Re-scope addition, 2026-06-15)* The installed Windows app behaves like a
      polished, always-on desktop app — this flight delivers the **visual** half: a launch
      **splash**, a **branded native window** (DD2-alt — native OS frame + brand title-bar/taskbar
      icon; the originally-planned frameless custom titlebar was diverted), and **icon/branding**
      polish. *(HAT-passed; `windows-native-frame-splash` Witnessed behavior-test backed)*

> The presence/lifecycle half (tray, background-run, single-instance focus,
> window-state) landed in **F6**. F7 extends the F6 desktop-shell.

---

## Pre-Flight

### Objective

Make the installed Windows app *look* finished. First, refactor F6's `run_desktop()`
into a **`DesktopSession` class** (no behavior change) that owns the window/tray/quit
lifecycle state — the structure the F6 debrief recommended before the visual work (and
the mac/Linux port) piles more lifecycle state on. Then, on that class: a **launch
splash** shown while uvicorn boots and dismissed when the UI is ready; **custom window
chrome** — `frameless=True` with a themed HTML titlebar merged into the web UI's
existing `#app-topbar` (vanilla JS, no build step), with min/max/close (close →
F6 close-to-tray) and a drag region, shown only inside the native window; and a proper
**app/taskbar icon** baked into the frozen `exe_gui`.

### Open Questions

- [x] Window chrome approach? → **Frameless + custom titlebar** merged into `#app-topbar`
      (operator, 2026-06-15).
- [x] `DesktopSession` refactor — here or separate? → **Folded into F7** as the
      scaffold-first leg (operator, 2026-06-15).
- [ ] **Does `frameless=True` + `resizable=True` keep edge-resize on the installed
      pywebview/winforms, or must resize be re-implemented?** → **Chrome-leg spike**
      (the lead risk). If resize is lost, it splits into a `window-resize` leg.
- [ ] How does the installed pywebview expose **`js_api`** (the titlebar buttons → window
      methods) and the **drag region** (CSS `pywebview-drag-region` class vs `easy_drag`)?
      → verify at the chrome-leg spike against the real install (the F6 "verify runtime
      form" lesson).
- [ ] Can two pywebview windows (splash + main) coexist on the one GUI loop, and does the
      splash close reliably even if the main window errors? → splash-leg spike.

### Design Decisions

**DD1 — Refactor `run_desktop()` → a `DesktopSession` class (scaffold-first, no behavior change).**
- Choice: extract the per-launch **lifecycle** into a `DesktopSession` class owning the
  instance state (`_desktop_window`, `_icon`, `_really_quit`, and now `_splash_window`,
  the `js_api`) and the **callbacks** (`_on_closing`/`_on_show`/`_on_quit`/
  `_save_current_geometry`) as methods. `run_desktop()` becomes a thin
  `DesktopSession().run()`.
- **Module-level surface MUST survive (cross-module + test contract — architect medium):**
  the stateless helpers `_select_port`, `_wait_until_serving`, `_graceful_shutdown`,
  `_webview_available` **stay module-level functions** (they're stateless utilities; the
  F6 tests call them standalone and patch them on the module). **`focus_window` stays a
  module-level symbol** — `web/app.py:1643` imports it (`from …desktop.shell import
  focus_window`); it delegates to the **live session's** window (via a module-level
  reference to the active `DesktopSession`, or by keeping `_desktop_window` a module global
  the session writes). The `app.py` back-compat shim and the `run_desktop` name keep
  working.
- **No behavior change** — F6's HAT-passed behavior is byte-identical; only the structure
  changes. A regression checkpoint asserts the **`/api/window/focus` → `focus_window`
  round-trip** still works after the refactor.
- Rationale: F6 debrief — the four nested closures in a ~180-line `run_desktop` are hard
  to unit-test directly and hard to make platform-conditional; F7 adds *more* lifecycle
  state (splash, js_api) that belongs on a class; the mac/Linux port needs
  platform-conditional callbacks. Do it now, before piling on.
- Trade-off: a sizable diff with no user-visible change — exactly why it's a standalone
  scaffold leg with the F6 desktop suites as the regression net (adapted to the class).

**DD2 — Frameless window + themed titlebar in `#app-topbar` (vanilla JS, desktop-only).**
- Choice: `create_window(..., frameless=True)`; the web UI's existing
  `<header id="app-topbar">` gains window-control buttons (minimize / maximize-restore /
  close) and a **drag region**, rendered **only when running inside the native window**.
  The buttons call a **`js_api`** exposed to the window; **close → F6 close-to-tray** (same
  path as the old X), maximize toggles, minimize minimizes.
- **Drag region must not swallow clicks (architect low):** the drag region overlays the
  *same* `#app-topbar` that `app.js`'s `renderTopBar()` rebuilds with nav-button click
  handlers — a drag region makes children non-interactive unless exempted. Give **both the
  existing nav buttons AND the new window controls explicit `no-drag`**; the behavior test
  asserts the nav buttons still fire under the drag region.
- **Gate on `pywebviewready`, not a one-shot check (architect suggestion):** `window.pywebview`
  may be injected *after* `DOMContentLoaded`/`renderTopBar()` in pywebview 5.x. Render the
  controls on the **`pywebviewready` event** (and re-check on render) so a render that ran
  before the bridge existed still draws them. (Verify the injection timing at the spike.)
- Rationale: the operator chose full custom chrome; `#app-topbar` already exists (no new
  layout), and `window.pywebview` detection keeps browser-mode unchanged (no fake
  controls in a real browser). No build step (constraint) — plain JS/CSS.
- Trade-off: a frameless window must re-create what the OS frame gave for free
  (drag-move, the controls, and **resize** — DD3). More surface, all HAT-verified.

**DD3 — Window resize on the frameless window (the lead risk — spike first).**
- Choice: open the chrome leg with a spike: does `frameless=True, resizable=True` still
  give Windows edge-resize on the installed pywebview? If **yes** → set `resizable=True`
  and done. If **no** → re-implement edge-resize (JS edge-grips → a `js_api` resize, or a
  Win32 `WM_NCHITTEST` hit-test) as a split-out `window-resize` leg.
- Rationale: frameless windows commonly lose resize borders on Windows; this is the
  flight's biggest unknown and must be resolved empirically before the chrome design locks
  (F6 "verify the runtime, don't assume the API" lesson).
- Trade-off: if resize must be hand-rolled, that's real work; the spike de-risks the
  estimate before committing.

**DD4 — Splash = a second pywebview window during the boot wait.**
- Choice: before/around `_wait_until_serving`, show a small **frameless splash window**
  (brand logo from `static/brand/`, e.g. `gleepglorp_icon.png`/`icon-512.png`); create the
  main window once serving; **close the splash on the main window's `loaded` event**.
  Guard so the splash always closes even if the main window errors (no orphaned splash).
- Rationale: reuses the existing readiness wait as the splash's lifetime; one stack
  (pywebview), consistent with everything else.
- Trade-off: two windows on one GUI loop — verified at the splash spike; the close-on-load
  wiring + error-path teardown are the care points.

**DD5 — App/taskbar icon baked into the frozen `exe_gui` (regenerate the `.ico` to 256).**
- Choice: set `icon='installer-assets/the-one.ico'` on the **`exe_gui`** `EXE(...)` in
  `the-one.spec` (currently no `icon=` → generic PyInstaller icon; the relative path is
  from the spec's `packaging/windows/` dir). On Windows the window + taskbar icon derive
  from the exe.
- **Regenerate the `.ico` first (architect high):** the current
  `installer-assets/the-one.ico` holds only **16/32/48** — no 256, so the large-icon /
  Alt-Tab / high-DPI taskbar path upscales 48→256 and looks soft, partly defeating "looks
  finished." Regenerate from the existing `static/brand/icon-512.png` master to include
  **256 (and 64/128)**; re-point the installer's icon too if it improves there.
- Rationale: smallest correct fix that actually looks crisp.
- Trade-off: none material; verified in the HAT (taskbar shows a crisp brand icon).

**DD6 — Verification: unit tests for the wiring + operator HAT + a Witnessed behavior test.**
- Choice: pytest covers the deterministic seams — the `DesktopSession` callbacks (the F6
  suites, adapted), the `js_api` methods (minimize/toggle-maximize/close call the right
  window methods; close routes to close-to-tray), the titlebar's `window.pywebview`
  conditional-render logic, the splash create/dismiss wiring. The **native + visual**
  surface — frameless drag/resize, the controls' real effect, the splash actually
  appearing/dismissing, the taskbar icon, "does it look finished" — has **no CI
  apparatus** (only a human on Windows can *act*: click/drag/resize, and *observe*: the
  native window's response + the visuals; chrome-devtools can drive the HTML buttons but
  cannot observe native min/max/drag/resize). So: an **operator HAT** + a new
  **`windows-native-frame-splash`** Witnessed behavior-test spec, run on the real frozen build.
- Rationale: same DD6 calculus as F6, which caught five bugs; visual polish is even more
  HAT-dependent.
- Trade-off: the visuals aren't CI-regression-gated; the HAT-before-merge gate covers it
  per release (F6's proven protocol).

**DD7 — Verify every new pywebview API against a real install before locking (F6 lesson).**
- Choice: `frameless`, `js_api`, the drag-region mechanism, multi-window, the `loaded`
  event, `resizable` semantics — each verified against the installed pywebview at the
  relevant leg's spike (read the source AND check the runtime *type/form*, not just the
  API name). Tests mock the **real runtime form** (e.g. an attribute that holds a value vs
  a callable), not the assumed signature.
- Rationale: F6's worst bug (`webview.screens()` — a proxy-list, not a function) came from
  assuming an API shape the mock then reinforced. F7 touches more pywebview surface; this
  is the explicit guard.
- Trade-off: a little spike time per API; cheap vs a HAT-cycle rediscovery.

### Prerequisites

- [x] F6 landed (tray/background/focus/window-state, the `DesktopSession` base
      `run_desktop()`) — **met** (F6 completed + merged to `main`, 2026-06-15).
- [x] The web UI has an `#app-topbar` host element and a no-build-step vanilla-JS
      convention — **met** (`interfaces/web/static/index.html`).
- [x] Brand assets for splash + icon — **met** (`static/brand/*`, `installer-assets/the-one.ico`).
- [ ] pywebview `frameless`/`resizable`/`js_api`/drag/multi-window/`loaded` runtime
      behavior — **verify at the chrome + splash spikes** (DD3/DD7).
- [ ] HAT apparatus: the Concourse `windows-installer` pipeline temporarily repointed to
      `flight/07` (as in F6) to build the frozen artifact; operator's Windows box. — ready
      (same apparatus as F6; revert pipeline to `main` after).

### Pre-Flight Checklist

- [ ] All open questions resolved (three are scoped leg spikes — chrome resize, js_api/drag, splash multi-window)
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined (pytest + HAT + `windows-native-frame-splash` behavior test)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

Refactor first (Leg 1): `run_desktop()` → `DesktopSession` with the F6 lifecycle as
methods; `run_desktop()`/`app.py` shim unchanged; F6 desktop suites adapted to the class,
behavior identical. Then build on the class:

- **Chrome (Leg 2)**: spike `frameless+resizable` resize behavior; set `frameless=True`;
  add a `js_api` (minimize / toggle-maximize / close→close-to-tray) to `create_window`;
  add the titlebar controls + drag region to `#app-topbar`, rendered only when
  `window.pywebview` is present; wire the buttons to `pywebview.api`.
- **Resize (Leg 3, conditional)**: if the spike shows resize is lost, re-implement
  edge-resize; else fold into Leg 2 as `resizable=True`.
- **Splash (Leg 4)**: a frameless splash window during the boot wait, closed on the main
  window's `loaded` event, with an error-path teardown guard.
- **Freeze + icon (Leg 5)**: `icon=the-one.ico` on `exe_gui`; confirm the titlebar/splash
  web assets are in the bundle (web static is already collected); packaged-smoke.
- **HAT (Leg 6)**: operator HAT + `windows-native-frame-splash` behavior test on the frozen build.

### Checkpoints

- [x] `DesktopSession` class in place; `the-one app` behaves byte-identically to F6
      (tray, close-to-tray, focus, window-state all still pass); F6 suites green;
      **`focus_window` stays module-level + the `/api/window/focus` round-trip works**.
- [ ] Frameless window with the themed titlebar; min/max/close work (close → tray); drag
      moves the window **and the existing nav buttons still fire** (no-drag); controls
      render only inside the native window (browser unchanged); the `frameless`/`js_api`/
      drag runtime-forms were verified against the real install + mocked as the real type.
- [ ] Window resizes (via `resizable` or the re-implemented grips).
- [ ] Splash shows during boot and dismisses when the UI loads; no orphaned splash on error.
- [ ] Frozen app launches with the brand taskbar icon; chrome/splash don't break the freeze.
      *(Host portion done: .ico has 256/128/64, exe_gui has icon=, spec py_compiles. Packaged-smoke Windows-gated — Leg 7.)*
- [ ] Operator HAT + `windows-native-frame-splash` pass on the real install.

### Adaptation Criteria

**Divert if**:
- The chrome spike shows frameless resize *and* a hand-rolled resize are both infeasible
  / janky on the installed pywebview → fall back to **DD2-alt: a themed native frame**
  (keep the OS frame; style the title + icon only). Log the spike result and re-decide
  with the operator.
- Two pywebview windows can't coexist on the GUI loop → drop the pywebview splash for a
  lighter native/static splash (or defer splash).

**Acceptable variations**:
- Maximize as a true OS-maximize vs a manual "fill work-area" — whichever the spike shows
  is reliable frameless.
- Splash dismiss on `loaded` vs on the existing `_wait_until_serving` completion —
  whichever is cleaner on the real build.
- Resize as `resizable=True` (if it works) vs JS edge-grips vs Win32 hit-test.

### Legs

> **Note:** Tentative; planned one at a time. Leg 3 (`window-resize`) is conditional on
> the Leg-2 spike.

- [x] `desktop-session-refactor` — `run_desktop()` → `DesktopSession` class; no behavior
      change; F6 desktop suites adapted + green.
- [x] `window-chrome` *(lead risk — opens with the frameless-resize + js_api/drag spike)* —
      `frameless=True`; titlebar controls + drag in `#app-topbar` (vanilla JS,
      `window.pywebview`-gated); `js_api` min/max/close (close → close-to-tray).
- [—] `window-resize` *(conditional — NOT NEEDED)* — mooted by the DD3 divert: the native
      OS frame (Leg 8) provides edge-resize, so no hand-rolled resize was required.
- [x] `splash-screen` — frameless splash during the boot wait; dismissed on the main
      window `loaded`; error-path teardown guard. *Landed (host-native). HAT-deferred:
      splash actually appears/dismisses/never-orphans on real Windows (Leg 7).*
- [x] `freeze-and-icon` — **regenerate `the-one.ico` to include 256/128/64** (from
      `static/brand/icon-512.png`); set `icon='installer-assets/the-one.ico'` on `exe_gui`;
      confirm chrome/splash assets in the bundle; packaged-smoke on the `windows-2022` runner.
      *Host-runnable portion landed. Windows-gated remainder (packaged-smoke: icon renders on
      window/taskbar; chrome/splash web assets verified in bundle) tracked for Leg 7 HAT.*
- [x] `docs` — update `agents.md`/`README.md`/`CLAUDE.md`/`packaging/windows/README.md` for
      the shipped shape: `DesktopSession` lifecycle, native OS frame (`frameless=False`),
      launch splash, brand `.ico`; pywebview/WebView2 frameless footgun note; `regenerate_icon.py`
      discoverable from the packaging README. *(Separate leg — per F6 debrief lesson. Landed.)*
- [x] `themed-native-frame` — revert main window to `frameless=False`; remove `_WindowApi`/`js_api`/
      win-controls/`_watchBridge`; keep splash + brand icon; update tests + behavior spec →
      `windows-native-frame-splash`. *Landed (host-native tests green).*
- [x] `hat-and-gui-behavior-test` *(interactive — PASSED build #22)* — operator HAT + `/behavior-test
      windows-native-frame-splash` on the frozen build.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed (Leg 3 `window-resize` mooted by the DD3 divert — native frame resizes)
- [ ] Code merged — draft PR open on `flight/07-windows-app-hardening-visual-polish`, marked
      ready after the HAT pass; merge pending review
- [x] Tests passing (host-native pytest 68 green; `windows-2022` packaged-smoke green — build #22)
- [x] Documentation updated (agents.md / README / CLAUDE.md / packaging/windows/README.md:
      DesktopSession lifecycle, native OS frame, launch splash, brand `.ico`,
      pywebview/WebView2 frameless footgun note, `regenerate_icon.py` reference)

### Verification

- **CI / host-native**: the adapted F6 suites + new `js_api`/titlebar/splash unit tests
  pass; `serve`/`chat`/`version` byte-identical; `windows-2022` packaged-smoke builds +
  launches the frozen app with the brand icon.
- **Operator HAT + Witnessed behavior test** (`/behavior-test windows-native-frame-splash`):
  on the real installed app — native OS title bar with brand name + icon; native min/max/
  close/drag/resize work; native X hides to tray; splash shows on launch and dismisses when
  ready; taskbar shows the brand icon; no regression in the F6 behaviors. Run-log path
  recorded in the flight log.
