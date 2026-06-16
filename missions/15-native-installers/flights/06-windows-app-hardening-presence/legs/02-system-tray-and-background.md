# Leg: system-tray-and-background

**Status**: completed
**Flight**: [Windows Native App Hardening — Desktop Presence & Lifecycle](../flight.md)

## Objective

Add a system-tray icon with a Show/Quit menu and make the window's close button
**hide to the tray** (app keeps serving) instead of exiting — with a one-time first-run
notice — so the installed app runs as an always-on background desktop app; Quit (tray
menu) is the only real exit and drives the F4 graceful server drain.

## Context

- Flight DD2: **pystray on a detached thread; pywebview owns the main thread.** This is
  the flight's named lead risk — the tray loop and pywebview's GUI loop coexisting on
  one process. This leg **opens with that coexistence spike** before wiring the full
  feature.
- Flight DD3: **close-to-tray + first-run notice; Quit from the tray menu.**
- Leg 1 created `the_one/interfaces/desktop/` with `run_desktop()` in `shell.py` (the
  migrated F4 launcher). Today `run_desktop()` does `try: webview.start() finally:
  _graceful_shutdown(server, thread)` and the window's X **destroys** the window
  (ending `webview.start()`), which the `finally` then drains.
- **Empirical GUI/tray proof is deferred** (DD6): this host is headless Linux (no GTK,
  no Windows tray). Leg 2's tests are **mocked-GUI unit tests**; the real coexistence +
  tray behavior is proven by Leg 5 (frozen `windows-2022` packaged-smoke) and Leg 6
  (operator HAT / `windows-desktop-presence` behavior test).

## Inputs

- `the_one/interfaces/desktop/shell.py` — `run_desktop()` + `_graceful_shutdown` (Leg 1).
- `the_one/config.py:settings` — `settings.data_dir` (platformdirs per-user dir) for
  the first-run-notice marker.
- `the_one/interfaces/web/app.py:80 — "STATIC_DIR = Path(__file__).parent / 'static'"`
  — the pattern for resolving bundled assets; the tray icon is
  `the_one/interfaces/web/static/brand/gleepglorp_icon.png` (ships in the freeze — F5
  already bundles web static).
- `pystray` + `Pillow` — added to `[gui]` in Leg 1.
- pywebview `Window` event/method surface: `window.events.closing` (a handler returning
  `False` cancels the close), `window.hide()`, `window.show()`, `window.restore()`,
  `window.destroy()`.

## Outputs

- `the_one/interfaces/desktop/tray.py` — new; builds the pystray `Icon` (image from the
  brand PNG via Pillow) with a Show/Quit menu, a `notify()` wrapper, and a graceful
  "tray unavailable" path.
- `the_one/interfaces/desktop/shell.py` — `run_desktop()` extended: register the
  `closing` → hide-to-tray handler (unless quitting), start the tray detached, and wire
  Quit → teardown. Module-level lifecycle state (`_really_quit`, the window ref).
- `the_one/interfaces/desktop/notice.py` — new (separate, independently testable);
  first-run notice marker read/write under `data_dir`.
- `tests/test_desktop_tray.py` — new; mocked-GUI unit tests.

## Acceptance Criteria

- [ ] **Spike resolved + recorded:** the leg's flight-log entry states the chosen tray
      thread model — pystray `Icon.run_detached()` (DD2 default) vs. a daemon
      `threading.Thread(target=icon.run)` — and the marshalling rule (tray callbacks
      call pywebview's thread-safe `window.show/restore/hide/destroy` from the tray
      thread; no native-handle access). The spike checklist also records: (a) `hide()`
      is callable synchronously from inside the `closing` handler; (b) `destroy()` is
      callable from pystray's win32 message-loop thread; (c) `run_detached()` works on
      Windows without the macOS-only `darwin_nsapplication` arg. The full empirical
      coexistence proof is logged as deferred to Leg 5/6 (no GUI on this host).
- [ ] Clicking the window close (X) **hides** the window and the app **keeps serving**:
      a `closing` handler calls `window.hide()` and returns `False` (cancels destroy)
      whenever the "really quit" flag is unset. (Unit-tested with a mock window:
      handler returns `False` + `hide()` called.)
- [ ] **First-run notice:** the *first* close-to-tray shows a tray notification
      ("GleepGlorp AI is still running in the system tray — Quit from the tray menu to
      exit") and persists a marker under `settings.data_dir`; subsequent closes are
      silent. (Unit-tested with a temp `data_dir` + mock icon: notify called once,
      marker created; second call: no notify.) The notify wrapper is called as
      `notify(icon, message, title)` — `message` is the body, `title` the balloon title
      (pystray's `Icon.notify(message, title=None)`); assert the mock call's arg order.
- [ ] **Tray menu:** the tray exposes **Show** (→ `window.show()` + `window.restore()`)
      and **Quit**. (Unit-tested: building the tray yields a menu with those two items
      wired to the right callbacks; pystray mocked.)
- [ ] **Quit drives teardown in order:** the Quit callback sets the really-quit flag,
      stops the tray icon (`icon.stop()`), and destroys the window (`window.destroy()`),
      after which `webview.start()` returns and the existing `finally:
      _graceful_shutdown(server, thread)` drains the server. (Unit-tested: call order
      asserted with mocks, **including that `icon.stop()` is still called when
      `window.destroy()` raises** — `run_detached()` spawns a *non-daemon* thread, so a
      skipped `icon.stop()` would strand it and hang the `finally` drain; wrap the
      teardown so `icon.stop()` cannot be skipped.)
- [ ] **Tray-unavailable degrade:** if the tray fails to construct/start (no backend,
      import error), the app logs a warning and **does not register the `closing`
      handler at all** — so the window's X falls through to pywebview's default destroy
      (F4 behavior); the app does NOT crash. (Unit-tested: tray-build raising →
      run_desktop proceeds, no `closing` handler registered, normal close works.)
- [ ] The tray icon image resolves to the existing brand PNG
      (`…/web/static/brand/gleepglorp_icon.png` exists). (Unit-tested: resolved path
      exists.)
- [ ] `pystray`/`Pillow`/`webview` are imported **lazily** (inside functions), mirroring
      F4's lazy `import webview`, so importing `desktop.tray`/`desktop.shell` does not
      require a GUI stack; tests inject mocks via `sys.modules`.
- [ ] `tests/test_desktop_tray.py` passes host-native; the Leg-1 launcher tests
      (`tests/test_desktop_shell.py`) still pass (no regression).

## Verification Steps

- `python -m pytest tests/test_desktop_tray.py tests/test_desktop_shell.py -x --timeout=30 -q`
  (host-native — NOT docker) — all green.
- `python -c "import the_one.interfaces.desktop.tray, the_one.interfaces.desktop.shell; print('import ok')"`
  — imports succeed WITHOUT pystray/webview installed/initialized (lazy imports).
- `python -c "from pathlib import Path; import the_one.interfaces.web as w; p=Path(w.__file__).parent/'static'/'brand'/'gleepglorp_icon.png'; print('icon ok', p.exists())"`
  — prints `icon ok True`.
- `git diff --stat` — changes scoped to `the_one/interfaces/desktop/` + `tests/`.

## Implementation Guidance

1. **Spike first (document, then build).** Confirm against the installed pywebview
   (read the library if needed) that `window.events.closing` exists and a handler
   returning `False` cancels the close, and that `hide/show/restore/destroy` are
   thread-safe. **Note (from design review of pywebview's `Event.set`):** the `closing`
   event runs handlers synchronously and **swallows handler exceptions** — if
   `window.hide()` raises inside `_on_closing`, the cancel is lost and the window
   destroys silently. So the spike records (a) `hide()` callable from inside `closing`,
   (b) `destroy()` callable from pystray's win32 thread, (c) `run_detached()` on Windows
   needs no `darwin_nsapplication` arg. Choose `Icon.run_detached()` (DD2 default)
   unless the read shows a reason to use a daemon thread. Record the choice + the
   marshalling rule in the flight log; empirical coexistence proof defers to Leg 5/6.

2. **`tray.py`** — lazy `import pystray` and `from PIL import Image` inside the builder.
   - `_load_icon_image()` → resolve `Path(the_one.interfaces.web.__file__).parent /
     "static" / "brand" / "gleepglorp_icon.png"`, `Image.open(...)`.
   - `build_tray(*, on_show, on_quit) -> Icon`: `pystray.Icon("the-one",
     _load_icon_image(), "GleepGlorp AI", menu=pystray.Menu(MenuItem("Show", on_show,
     default=True), MenuItem("Quit", on_quit)))`.
   - `notify(icon, message, title)`: wrapper over `icon.notify(message, title)`.

3. **`shell.py` lifecycle wiring** in `run_desktop()` (after the window is created,
   before `webview.start()`):
   - Module-level `_really_quit = False` and a window reference.
   - `_on_closing()`: if `_really_quit` → return `True` (allow destroy). Else → show
     the first-run notice if not yet shown, then **`window.hide()` wrapped in
     try/except — on a hide failure, return `True`** (allow the close rather than let
     pywebview silently swallow the exception and destroy anyway); on success return
     `False` (cancel).
   - `on_show()`: `window.show(); window.restore()`.
   - `on_quit()`: set `_really_quit = True`; **`icon.stop()` guarded in try/except (it
     MUST run — `run_detached()`'s thread is non-daemon, so a skipped `stop()` hangs the
     process)**; then `window.destroy()`.
   - **Only if the tray started OK:** register `window.events.closing += _on_closing`.
   - Keep the existing `try: webview.start() finally: _graceful_shutdown(server,
     thread)` — `webview.start()` now returns only on a real Quit (destroy), and the
     `finally` drains. (This IS the deferred Leg-1 teardown re-home: close no longer
     ends the app; Quit does.)
   - Wrap tray build/start in `try/except`: on failure, log a warning and **do NOT
     register `_on_closing`** — the window's X then falls through to pywebview's default
     destroy (F4 fallback). No `_really_quit`-equivalent hack needed; the absence of the
     handler IS the fallback.

4. **First-run notice marker** (`notice.py`) — `data_dir / ".close_to_tray_notice_shown"`
   (presence = shown). `notice_shown()` / `mark_notice_shown()` helpers. The marker
   helper **must `settings.data_dir.mkdir(parents=True, exist_ok=True)` itself before
   writing** — do NOT assume `settings.ensure_dirs()` has run (it's called from the DB/
   agent paths, not from `run_desktop()`, so on a fresh install the X may be hit before
   `data_dir` exists).

5. **Tests** (`tests/test_desktop_tray.py`) — install mock `pystray`/`webview`/`PIL`
   in `sys.modules` (mirror `test_desktop_shell.py`'s webview-mock fixture). Cover the
   acceptance behaviors above. Use a `monkeypatch` of `settings.data_dir` to a
   `tmp_path` for the notice-marker tests. **Reset the module-level `_really_quit` (and
   re-import/reset any accumulated `closing` handlers) in setup/teardown** so cross-test
   state doesn't leak (the flag is process-global).

## Edge Cases

- **Quit while hidden:** `on_quit` must work whether the window is visible or hidden —
  `window.destroy()` works in both states; no need to `show()` first.
- **Tray backend missing on the host:** covered by the degrade path (criterion 6) — do
  not let a tray failure take down the app.
- **Double-close / re-entrancy:** once `_really_quit` is set, a second `closing` is
  allowed through; idempotent.
- **`closing` handler return contract:** pywebview cancels the close when the handler
  returns `False` (falsy). Returning `None` does NOT cancel — be explicit, return
  `False`/`True`.
- **Exception swallowed in `closing` (design-review medium):** pywebview's `Event.set`
  wraps each handler in `try/except` and continues — a raise inside `_on_closing` is
  logged-and-ignored, so the cancel is lost and the window destroys. Mitigation: the
  `window.hide()` try/except returns `True` on failure (deterministic close) instead of
  leaking an exception into the swallow.
- **`run_detached()` non-daemon hang (design-review low):** pystray's win32
  `run_detached` starts a non-daemon thread, so if `icon.stop()` is ever skipped the
  process won't exit and the `finally` drain blocks forever. Mitigation: `icon.stop()`
  is guarded and always runs in `on_quit`.
- **Notice marker race:** single-process, single-window — no concurrency concern.
- No DB/schema; the only persisted state is the boolean notice marker (a file's
  existence) — trivially reachable, no FK/cache contract. The new `_really_quit`
  in-memory flag is process-local and reset each launch.

## Files Affected

- `the_one/interfaces/desktop/tray.py` — new.
- `the_one/interfaces/desktop/shell.py` — `run_desktop()` extended with tray + close-to-tray + Quit teardown.
- `the_one/interfaces/desktop/notice.py` *(or helper in shell.py)* — first-run marker.
- `tests/test_desktop_tray.py` — new.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (`test_desktop_tray.py` + `test_desktop_shell.py`, host-native)
- [ ] Update flight-log.md with the leg progress entry (incl. the spike outcome)
- [ ] Set this leg's status to `landed` (completion/commit deferred to flight-end review)
- [ ] Check off this leg in flight.md *(deferred to flight-end commit)*

## Citation Audit

3 code-location citations verified against current code at leg-design time
(2026-06-15): `the_one/interfaces/web/app.py:80` ("STATIC_DIR = Path(__file__).parent
/ 'static'") — OK; `the_one/interfaces/web/static/brand/gleepglorp_icon.png` — OK
(file exists, confirmed via `ls`); `the_one/config.py:settings.data_dir` — OK
(platformdirs default-factory). pywebview event/method names (`events.closing`,
`hide/show/restore/destroy`) are library API to be confirmed against the installed
pywebview during implementation (noted in the spike step), not repo citations.
