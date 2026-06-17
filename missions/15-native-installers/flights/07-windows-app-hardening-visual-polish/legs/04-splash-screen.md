# Leg: splash-screen

**Status**: completed
**Flight**: [Windows Native App Hardening — Visual Polish](../flight.md)

## Objective

Show a small branded splash window while uvicorn boots, and dismiss it when the main UI is
ready — so launch doesn't present a blank/absent window during the readiness wait.

## Spike result (2026-06-16) — VIABLE, proceed with the pywebview splash

The DD4 two-window model was confirmed on the real Windows install (operator spike, all four
modes passed): two pywebview windows coexist on one GUI loop, the splash dismisses on the main
window's `loaded` event, the process exits cleanly, and the error path tears down without
hanging. The early `E_UNEXPECTED` failures were a **non-writable relative `storage_path`** (run
from `C:\Python311`), NOT a multi-window or runtime problem — the real app already uses an
absolute writable profile (`settings.data_dir / "webview"`). **Implement DD4 (not the divert)
with the fixes below.** Confirmed implementation requirements from the design review:
- **Error path destroys BOTH windows** (splash AND main if it exists) — destroying only the
  splash hangs the loop when the main window already exists.
- **Idempotent splash teardown guarded by a `threading.Event`** (the `loaded` handler runs on a
  daemon thread and may race the error path — a plain bool flag has a TOCTOU).
- **`splash.events.shown.wait(...)` as the first line of `_boot`** — so teardown is always safe
  (splash initialized) even if `_wait_until_serving` returns instantly.
- **Preserve `private_mode=False` + the absolute `storage_path`** on `webview.start`.
- **Browser-fallback `_wait_until_serving`** — moving the wait into `_boot` removes it from the
  no-webview path; either keep a `_wait_until_serving` call there or document the behavior change.

## Context

- **DD4** (flight): the splash is a **second frameless pywebview window** shown during the boot
  wait; the main window is created once serving; the splash closes on the **main window's
  `loaded` event**; a guard ensures the splash always closes even if the main window errors.
- **DD7**: verify pywebview API runtime forms (multi-window, `webview.start(func=…)`, the
  `loaded` event) against the real install; mock the real form in tests.
- Builds on the post-Leg-2 `DesktopSession.run()`.

### The GUI-loop constraint (why `run()` must restructure)

Today `run()` calls `_wait_until_serving(host, port)` **synchronously before** the webview
block, then `webview.start()` (which runs the GUI loop and **blocks**). A pywebview window only
renders once the GUI loop is running — so a splash created before `webview.start()` cannot be
visible *during* the wait unless the wait itself runs **inside** the GUI loop.

pywebview's documented pattern: `webview.start(func, ...)` runs `func` on a **background
thread after the GUI loop starts**, and `create_window` may be called from that thread to add
windows to the running loop. So the splash leg restructures `run()` to:

1. Create the **splash** window first (frameless, small, brand-styled), *before* `start()`.
2. Pass a `_boot` callable to `webview.start(_boot, …)`. `_boot` runs after the loop is up:
   `_wait_until_serving` → create the **main** window (with the Leg-2 `js_api`/frameless/etc.)
   → wire tray + `closing` → register the main window's **`loaded`** event to **destroy the
   splash** → set `_desktop_window`/`self._window`/`api._window`.
3. **Error-path guard**: if `_wait_until_serving` or main-window creation raises inside `_boot`,
   the splash **must still be destroyed** (and the loop torn down so the app doesn't hang
   showing only the splash). Wrap `_boot`'s body so the except path destroys the splash and
   exits the loop deterministically.

### Spike — HAT-only (cannot run on this Linux dev host)

pywebview is not installed here. Whether **two windows coexist on one GUI loop**, whether the
splash **closes reliably on `loaded`**, and the **error-path teardown** can only be observed on
the real installed pywebview on Windows (operator HAT, Leg 7). This leg implements the DD4
primary design and HAT-verifies it. **Divert (DD4 "divert if")**: if the HAT shows two
pywebview windows can't coexist (or the splash won't close), fall back to a lighter
native/static splash or defer the splash — re-decide with the operator and log it.

## Inputs

- `the_one/interfaces/desktop/shell.py` — post-Leg-2 `DesktopSession.run()` with the
  synchronous `_wait_until_serving` (line ~374) then the `create_window`/tray/`webview.start`
  block. The main-window create + tray wiring + `webview.start(private_mode=False,
  storage_path=…)` is what moves into `_boot`.
- Brand assets: `the_one/interfaces/web/static/brand/` (`gleepglorp_icon.png`, `icon-512.png`,
  etc.). The splash content references one of these.
- `tests/test_desktop_shell.py::test_run_calls_create_window_start_and_graceful_shutdown` —
  asserts `create_window` called **once** with title "GleepGlorp AI" and `start` called with
  `private_mode=False`, `storage_path=…`. **This restructure changes both** (create_window now
  called twice; start now also takes the `_boot` func) — the test must be adapted.
- `tests/test_window_state.py`, `tests/test_desktop_tray.py` — also drive `run()` with mocked
  webview and assert on window/closing wiring; adapt where the `_boot` indirection requires.

## Outputs

- `DesktopSession.run()` restructured: splash window created, `webview.start(_boot, …)`,
  main-window creation + tray wiring + `_wait_until_serving` inside `_boot`, splash dismissed
  on the main window's `loaded` event, error-path splash teardown.
- A splash content source (inline `html=` with brand styling, or a bundled splash asset) that
  renders without the app server (the server isn't up yet).
- Unit tests (mocked webview) covering: splash created before `start`; `start` called with a
  func; `_boot` waits-until-serving then creates the main window; the main window's `loaded`
  handler destroys the splash; the error path destroys the splash.

## Acceptance Criteria

- [ ] On desktop launch, a **splash window** is created (frameless, small, brand-styled) and
      `webview.start` is invoked with a `_boot` callable (the documented run-after-loop-start
      pattern). The splash content renders **without** the app server (inline HTML or a bundled
      asset — not a `localhost` URL that isn't serving yet).
- [ ] `_boot` runs `_wait_until_serving`, then creates the **main** window with the **same
      Leg-2 kwargs** (`frameless=True, resizable=True, easy_drag=False, js_api=api`) and the F6
      window-state-restore kwargs, wires the tray + `closing` handler exactly as today, and
      sets `_desktop_window` / `self._window` / `api._window`.
- [ ] The splash is **dismissed when the main UI is ready** — the main window's `loaded` event
      destroys the splash. (Acceptable variation per flight: dismiss on `loaded` vs on
      `_wait_until_serving` completion — pick whichever is cleaner; default to `loaded`.)
- [ ] **Error-path guard**: if `_wait_until_serving` or main-window creation raises inside
      `_boot`, the splash is still destroyed and the GUI loop is torn down (no orphaned splash,
      no hang). Covered by a unit test.
- [ ] The `webview.start` persistence config is preserved — `private_mode=False` and the
      `storage_path` under `data_dir/webview` still apply to the main window.
- [ ] All desktop suites green host-native after adapting the launch tests to the
      splash/`_boot` structure: `test_desktop_shell.py`, `test_desktop_tray.py`,
      `test_window_focus.py`, `test_window_state.py`.
- [ ] No regression in F6/Leg-2 behavior: close-to-tray, Quit, focus, window-state restore,
      the frameless chrome, and the `js_api` all still work (the wiring just moved into `_boot`).
- [ ] `serve` / `chat` / `version` and the browser-fallback path (`_webview_available()` False)
      are unchanged — the splash is webview-only.

## Verification Steps

- `.venv/bin/python -m pytest tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_focus.py tests/test_window_state.py tests/test_desktop_chrome.py -x --timeout=30`
- A new unit test for the `_boot` happy path (waits, creates main, registers `loaded`→splash
  destroy) and the error path (raise inside `_boot` → splash destroyed).
- **HAT-deferred** (Leg 7, real Windows): splash actually appears on launch, dismisses when the
  UI is ready, and never orphans on a boot error.

## Implementation Guidance

1. **Read the pinned pywebview 5.4** `webview.start(func=…, args=…)` + multi-window + `loaded`
   event semantics from source (as the Leg-2 reviews did). Confirm: `start(func)` runs `func`
   on a background thread after the loop init; `create_window` works from that thread; the
   `loaded` event exists on a Window. Mock those exact forms.
2. **Splash window** — `webview.create_window(title, html=SPLASH_HTML, frameless=True,
   width=…, height=…, on_top=True?)`. SPLASH_HTML is brand-styled (app name + logo). For the
   logo, prefer an approach that survives the freeze: inline base64 of a small brand PNG, or a
   `file://` path validated at the freeze leg (Leg 5). Avoid depending on the not-yet-serving
   localhost. Keep it small and dependency-free.
3. **`_boot(window=splash)` callable** — moves `_wait_until_serving`, the main `create_window`,
   the tray wiring, and the `_desktop_window`/`self._window`/`api._window` assignment inside it.
   Register `main.events.loaded += lambda: _destroy_splash(splash)` (idempotent destroy). On any
   exception: log, destroy the splash, and tear down (destroy whatever exists so `start()`
   returns) — the `finally: _graceful_shutdown` still runs.
4. **`webview.start(_boot, private_mode=False, storage_path=str(storage_dir))`** — keep the
   persistence config. The `storage_dir.mkdir(...)` stays before `start`.
5. **Idempotent splash teardown** — guard `_destroy_splash` so a double fire (loaded + error
   path) doesn't raise; track a `_splash_closed` flag or wrap in try/except.
6. **Adapt the launch tests** — `test_run_calls_create_window_start_and_graceful_shutdown` now
   sees two `create_window` calls (assert the MAIN one carries title "GleepGlorp AI" + the
   Leg-2 kwargs; the splash one is frameless + html) and `start` called with a positional func.
   Since `start` is mocked (doesn't actually run `_boot`), the test must **invoke the captured
   `_boot`** to exercise the main-window creation, or assert `_boot` wiring separately. Keep the
   `private_mode`/`storage_path` assertions on `start`'s kwargs.

## Edge Cases

- **`start(func)` mock doesn't run `func`** — in tests `webview.start` is a MagicMock, so
  `_boot` never runs unless the test calls it. Structure the test to capture and invoke `_boot`
  with a mock splash so the main-window creation path is covered.
- **Main window errors before `loaded`** — error-path guard destroys the splash (criterion
  above). Without it the GUI loop would hang showing only the splash.
- **Tray-unavailable** — unchanged: inside `_boot`, if `build_tray` raises, `_on_closing` is
  not registered (F6 fallback). The splash logic is independent of the tray.
- **Browser-fallback path** (`_webview_available()` False) — no webview, no splash; unchanged.
- **`is_ours=True` early return** — returns before any window; no splash. Unchanged.
- **Freeze (Leg 5)** — the splash's HTML/asset must be in the bundle; Leg 5 confirms the splash
  asset is collected (note this dependency in the flight log for Leg 5).

## Files Affected

- `the_one/interfaces/desktop/shell.py` — `run()` restructured for the splash + `_boot`; a
  splash-HTML constant or asset reference; `_destroy_splash` helper.
- `tests/test_desktop_shell.py` — adapt the launch test to two windows + `start(func)`; add
  `_boot` happy/error path tests.
- `tests/test_window_state.py`, `tests/test_desktop_tray.py` — adapt where `_boot` indirection
  requires (the closing/window-state wiring now runs inside `_boot`).

---

## Post-Completion Checklist

**Per this flight's batched model — set status to `landed` (NOT `completed`); do NOT commit or
signal `[COMPLETE:leg]`.**

- [x] All non-HAT acceptance criteria verified host-native
- [x] HAT-deferred items (splash appears/dismisses/never-orphans) listed in the flight-log entry
- [x] Leg-5 dependency noted (splash asset must be in the freeze bundle — SPLASH_HTML is pure
      inline HTML/CSS; no bundle asset entry needed)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`; check off this leg in flight.md
