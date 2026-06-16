# Leg: desktop-session-refactor

**Status**: landed
**Flight**: [Windows Native App Hardening — Visual Polish](../flight.md)

## Objective

Extract F6's procedural `run_desktop()` into a `DesktopSession` class that owns the
per-launch window/tray/quit lifecycle state and callbacks — with **zero behavior change** —
so the splash/chrome/js_api state that F7 adds (and the mac/Linux port) has a class to live on.

## Context

- **DD1** (flight): `run_desktop()` → `DesktopSession`, scaffold-first, no behavior change.
  The four nested closures in the ~250-line `run_desktop` are hard to unit-test directly
  and hard to make platform-conditional; F7 piles on more lifecycle state (splash window,
  `js_api`), which belongs on a class.
- **F6 lesson**: do the refactor *before* the visual work, with the F6 desktop suites as
  the regression net (adapted to the class).
- This is the **first leg** of F7 and a pure structural change. Later legs (chrome, splash,
  freeze/icon) build on the class this leg creates.

## Inputs

What exists before this leg runs (current `main` + F6):

- `the_one/interfaces/desktop/shell.py` (381 lines) — module-level `_really_quit` and
  `_desktop_window` globals; module-level helpers `_wait_until_serving`, `_graceful_shutdown`,
  `_select_port`, `_webview_available`, `focus_window`; the procedural `run_desktop()` with
  four nested closures (`_save_current_geometry`, `_on_closing`, `_on_show`, `_on_quit`).
- `tests/test_desktop_shell.py` — patches `shell._select_port` / `_webview_available` /
  `_graceful_shutdown` / `_wait_until_serving` (via `patch.object(launcher_module, ...)`),
  calls `run_desktop()`, asserts `create_window`/`start`/`_graceful_shutdown` behavior.
- `tests/test_desktop_tray.py` — `_run_desktop_with_tray()` helper runs `run_desktop()` with
  mocks; fires the registered `closing` handler; **sets `shell_module._really_quit = True`
  directly** and asserts the closing handler honors it; asserts `_on_closing` registered once.
- `tests/test_window_focus.py` — patches `the_one.interfaces.desktop.shell.focus_window`;
  **assigns `shell_mod._desktop_window = mock_window` directly** then calls `focus_window()`;
  exercises `focus_window()` (show+restore, no-op when no window, swallows exceptions) and
  `POST /api/window/focus`; asserts `run_desktop()` on `is_ours=True` POSTs focus and returns
  with no window.
- `tests/test_window_state.py` — also calls `run_desktop()` (in helpers) and fires the real
  `_on_closing` handler end-to-end (e.g. `test_on_closing_saves_geometry` expects
  `result is False` because `_really_quit` starts False on a fresh launch). Part of the F6
  regression net — must stay green after the refactor.

## Outputs

- `the_one/interfaces/desktop/shell.py` refactored: a `DesktopSession` class holding the
  per-launch instance state and the four callbacks as methods; `run_desktop()` reduced to a
  thin `DesktopSession().run()`.
- The F6 test suites adapted (where the class structure requires) and green.
- No change to any other module, no change to `the-one app` / `serve` / `chat` / `version`
  runtime behavior.

## Acceptance Criteria

- [x] `DesktopSession` class exists in `shell.py`, owning the per-launch lifecycle: the
      window reference, the tray icon reference, the `_really_quit` flag, and the
      `_save_current_geometry` / `_on_closing` / `_on_show` / `_on_quit` callbacks as methods
      (or bound closures created in `run()`), plus the create-window / tray-wiring / start /
      graceful-shutdown sequence in a `run()` method.
- [x] `run_desktop()` remains a **module-level function** that is a thin
      `DesktopSession().run()` (or equivalent), preserving the existing entry contract.
- [x] The four stateless helpers **stay module-level functions**: `_select_port`,
      `_wait_until_serving`, `_graceful_shutdown`, `_webview_available` — unchanged signatures
      (the F6 tests patch them on the module; `the_one/interfaces/app.py` re-exports them).
- [x] `focus_window` **stays a module-level symbol** importable as
      `from the_one.interfaces.desktop.shell import focus_window` (used by `web/app.py:1643`
      and patched by `test_window_focus.py`). It raises/restores the live window by **reading
      the module-level `_desktop_window` global** — which the session writes on window
      creation. (This is the only resolution compatible with `test_window_focus.py`, which
      assigns `shell_mod._desktop_window = mock_window` directly and then calls
      `focus_window()`; a delegate-to-session-instance approach would silently break it.)
- [x] The `POST /api/window/focus` → `focus_window` round-trip still returns
      `{"focused": true}` when a window is registered and `{"focused": false}` otherwise
      (regression checkpoint per DD1).
- [x] `the_one/interfaces/app.py` back-compat shim still imports cleanly (`run`,
      `_select_port`, `_webview_available`, `_wait_until_serving`, `_graceful_shutdown`).
- [x] The adapted F6 desktop suites pass: `tests/test_desktop_shell.py`,
      `tests/test_desktop_tray.py`, `tests/test_window_focus.py`, `tests/test_window_state.py`
      — all green host-native.
- [x] No behavior change: the close-to-tray / Quit / first-run-notice / window-state-restore /
      single-instance-focus / browser-fallback paths behave exactly as F6.

## Verification Steps

- `docker`-free host-native pytest (per crew prompt: `docker exec the-one pytest …` is the
  documented runner, but this host runs host-native — use the host pytest):
  `pytest tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_focus.py tests/test_window_state.py -x --timeout=30`
- `python -c "from the_one.interfaces.app import run, _select_port, _webview_available, _wait_until_serving, _graceful_shutdown"` — shim imports clean.
- `python -c "from the_one.interfaces.desktop.shell import focus_window, run_desktop, DesktopSession"` — symbols present.
- `grep -n "frameless" tests/test_desktop_shell.py` still asserts `frameless is False` (no
  chrome change yet — that's Leg 2).

## Implementation Guidance

1. **Introduce `DesktopSession`** — instance attributes initialized in `__init__` (or at
   the top of `run()`): `self._desktop_window = None`, `self._icon = None`,
   `self._really_quit = False`, and (forward-looking, optional this leg) placeholders the
   later legs will use. Move the create-window / window-state-restore / tray-wiring /
   `webview.start()` / `finally: _graceful_shutdown(...)` sequence into `run()`.
2. **Convert the four closures to methods**: `_save_current_geometry(self, window)`,
   `_on_closing(self) -> bool`, `_on_show(self, icon)`, `_on_quit(self, icon)`. They read/write
   `self._really_quit` / `self._desktop_window` / `self._icon` instead of closure/global state.
   Register `self._desktop_window.events.closing += self._on_closing` exactly as today
   (only inside the tray-active branch).
3. **RESOLVED — keep `_desktop_window` and `_really_quit` as module globals the session
   reads/writes** (design-review decision; DD1 explicitly sanctions the module-global form).
   This keeps the F6 suites unchanged. Concretely:
   - `focus_window()` reads the module-level `_desktop_window` (as today). The session writes
     `_desktop_window` (via `global _desktop_window`) when it creates the window, and resets
     it to `None` at the top of `run()`. `test_window_focus.py` assigns
     `shell_mod._desktop_window = mock_window` directly and calls `focus_window()` — only the
     module-global read keeps that green.
   - `_really_quit` stays a module global. The `_on_closing` method reads it; the `_on_quit`
     method writes it (`global _really_quit; _really_quit = True`). Two F6 tests touch it on
     the module: `test_desktop_tray.py:333` **writes** `shell_module._really_quit = True`
     before firing `_on_closing` (expects `True`), and `test_desktop_tray.py:500` **reads**
     `assert shell_module._really_quit is True` after `_on_quit` fires. Both directions must
     work — i.e. the method must read AND write the module global, not instance state.
   - `_icon` may be instance state on the session (no test patches it on the module); the
     `_on_closing`/`_on_quit`/`_on_show` methods reach it via `self._icon`.
4. **Keep the class strictly minimal** — only the F6 lifecycle this leg needs. Do NOT stub
   forward-looking splash / `js_api` placeholders; later legs add their own attributes. The
   methods are `_save_current_geometry(self, window)`, `_on_closing(self) -> bool`,
   `_on_show(self, icon)`, `_on_quit(self, icon)`; `run()` holds the create-window /
   window-state-restore / tray-wiring / `webview.start()` / `finally: _graceful_shutdown`
   sequence; the browser-fallback and `is_ours` early-return paths stay in `run()` too.
5. **`run_desktop()` stays the entry point** — `def run_desktop() -> None:` keeps the
   `ensure_stdio_streams()` defensive call at the **outermost entry** (before constructing the
   session — matches current placement, lowest risk), then `DesktopSession().run()`.
6. **Run the adapted suites** scoped to the three desktop test files first; then a broader
   smoke (`pytest -q -x --timeout=30 -k "desktop or window or interface"`) before handoff.

## Edge Cases

- **`_desktop_window = None` reset per launch** — the module currently resets globals at the
  top of `run_desktop()` so a second call in tests starts clean. The session gets fresh
  instance state per `DesktopSession()`, which is *better*; ensure any retained module global
  (`_desktop_window` / `_active_session`) is also reset on each `run()` so a stale window from
  a prior test launch can't leak into `focus_window()`.
- **Tray-unavailable fallback** — when `build_tray` raises, `_on_closing` must NOT be
  registered (window X uses pywebview default destroy). Preserve this branch exactly.
- **`is_ours=True` path** returns before any window/server — must not construct a session
  window or touch globals (keep the early-return shape).
- **Browser-fallback path** (`_webview_available()` False) — no window, installs SIGINT
  handler, joins thread. Preserve.

## Files Affected

- `the_one/interfaces/desktop/shell.py` — refactor to `DesktopSession`; keep module-level
  `run_desktop`, `focus_window`, and the four stateless helpers.
- `tests/test_desktop_shell.py` — adapt only if the class structure requires (e.g. if
  `_really_quit`/window reach changes); otherwise leave as-is.
- `tests/test_desktop_tray.py` — adapt the `_really_quit` reach if option (b) is chosen.
- `tests/test_window_focus.py` — unchanged (assigns module-global `_desktop_window`, patches
  `shell.focus_window`); verify green.
- `tests/test_window_state.py` — should be unchanged (fresh-session `_really_quit` is False);
  verify green.
- `the_one/interfaces/desktop/__init__.py` / `the_one/interfaces/app.py` — should need **no**
  change; verify imports still resolve.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:** *(NB: in this flight, code review
+ commit are deferred to the end of the last autonomous leg per the agentic-workflow batched
model — the Developer updates status to `landed` and updates the flight log, but does NOT
commit or signal `[COMPLETE:leg]` per leg.)*

- [x] All acceptance criteria verified
- [x] Adapted F6 desktop suites passing host-native
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (NOT `completed` — commit is batched)
- [x] Check off this leg in flight.md
