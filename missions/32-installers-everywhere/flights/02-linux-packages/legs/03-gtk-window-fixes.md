# Leg: gtk-window-fixes

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Make the desktop window's close and show paths correct under pywebview's GTK backend (DD12):
- closing never deadlocks;
- showing actually maps the window;
- geometry is saved in the same measure it is restored, size only on Wayland (DD7).

Add the two routes later legs build on: `GET /api/window/state`, which reads visibility from GTK itself, and a minimal `POST /api/window/quit`. Prove all of it with a real-GTK smoke test of a built package, because fakes cannot see either trap.

## Context
- **Flight DDs:** DD12 (the two traps and their fixes, the smoke test), DD7 (Wayland geometry), DD4 (the route shapes; this leg ships the "window registered or not" part of quit, and leg 5 the rest).
- **The traps, both verified against pywebview 5.4 source in design review:**
  1. **Close deadlock.** `events.closing` is a locked event (`webview/window.py`: `Event(self, True)`), run synchronously on the GTK main thread from `delete-event` (`platforms/gtk.py::BrowserView.close_window`). `destroy()` reaches `close_window` through `glib.idle_add` (`platforms/gtk.py::destroy_window`), so `closing` always runs on the GTK main thread. `DesktopSession._on_closing` calls `_save_current_geometry` first, which reads `window.width/height/x/y`. On GTK those go to `get_size`/`get_position` (`glib.idle_add` plus a blocking `Semaphore.acquire()`), so on the main thread the idle never runs.
  2. **Show re-hides.** `BrowserView.show()` does `show_all()`, then `if gtk.main_level() == 0: if self.pywebview_window.hidden: self.window.hide()`. Under `Gtk.Application.run()` `main_level()` is 0. `Window.hidden` is set at creation (`shell.py` creates the main window with `"hidden": True`) and never cleared. Only `restore()` (`deiconify` + `present`) maps the window.
- **State after leg 2** (uncommitted, in this worktree):
  - `shell.py` has `_tray_mode`; it imports the host helpers as `desktop_host`.
  - In step 5, on Linux, a "none"/"unavailable" decision raises `_NoTrayError` and **registers no `closing` handler**. In that mode closing destroys the window, and geometry is never saved.
  - `_on_quit(icon)` still calls `icon.stop()` unguarded.
- **Not this leg (leg 5):**
  - no-tray hiding and its notice;
  - `the-one quit` (the CLI);
  - the quit route's booting, browser and serve states, and `pid`;
  - the focus route's activation token;
  - the version takeover.
- **Builds and harness:** leg 1 reworked `packaging/linux/build.sh` (the pinned container) and `packaging/spike/{check.sh,inner.sh,score.py}`. **This leg's smoke test runs after leg 1 has landed**, against a package built by that `build.sh` from this worktree (the staged copy includes this leg's `the_one/` changes), in `m32/ubuntu-26.04:baseline` and `m32/debian-13:baseline`.

## Inputs
- `the_one/interfaces/desktop/shell.py`:
  - `_save_current_geometry`, `_on_closing`, `_close_to_tray`, `_on_show`, `_on_quit`;
  - `focus_window`;
  - `run()` and `_boot` steps 4b, 5 and 6;
  - `_tray_mode`.
- `the_one/interfaces/desktop/window_state.py::save_state` (x/y optional)
- `the_one/interfaces/web/app.py`:
  - `window_focus` (`async def`);
  - `window_chrome_post` (a plain `def`, the pattern to follow).
- `tests/test_desktop_shell.py`, `tests/test_desktop_tray.py`, `tests/test_window_state.py`, `tests/test_window_focus.py`, `tests/conftest.py::stub_desktop_host`
- `packaging/linux/build.sh` and `packaging/spike/*` from leg 1

## Outputs
- **`shell.py`:**
  - **GTK detection,** one helper: `_is_gtk_backend()` returns `getattr(sys.modules.get("webview"), "renderer", None) == "gtkwebkit2"`, read at call time. `webview.start()` sets `renderer` before the first window is created, so the value is valid in `_boot`, `closing` and the routes. Never `from webview import renderer` (a stale copy), and no `sys.platform`/`guilib` alternative (`PYWEBVIEW_GUI=qt` would fool it). Unit tests monkeypatch `shell._is_gtk_backend`.
  - **Wayland detection for geometry:** `_on_wayland(window)` returns True when `type(window.native.get_display()).__name__` contains `Wayland` (GDK's `GdkWaylandDisplay`). Only if that read fails does it fall back to `desktop_host.display_session() == "wayland"`. `WAYLAND_DISPLAY` alone is wrong under `GDK_BACKEND=x11`/XWayland.
  - **`_save_current_geometry(window)`:**
    - **On GTK:** never touch `window.width/height/x/y`. Its docstring states the contract: GTK main thread only (inside `closing`). A defensive check (`threading.current_thread() is threading.main_thread()`) logs and skips if it is ever called elsewhere. It keeps today's `window.events.shown.is_set()` guard (`shown` fires at creation, so real saves are not skipped). It reads `window.native.get_size()` (the same measure `Gtk.Window.resize` restores) and, when not `_on_wayland(window)`, `window.native.get_position()`. On Wayland it passes `x=None, y=None` to `save_state`.
      - Known wart, not fixed: on a multi-monitor X11 layout whose monitor 0 is not at (0,0), pywebview's `move()` adds that monitor's origin, so position can be off by the offset. Record it only.
    - **Elsewhere (Windows):** today's code, unchanged.
  - **`_on_closing`:**
    - **Always registered** on the main window, whatever the tray outcome, so geometry is saved in every mode.
    - **Behaviour:**
      - save geometry (above);
      - if `_really_quit`: deregister and allow;
      - if a tray is running (`self._icon is not None`): today's close-to-tray hide;
      - otherwise (no tray, or tray failed): `chrome.deregister()` and **allow** the destroy. Interim until leg 5 adds the no-tray hide; it never calls `destroy()` from inside the handler.
    - The step-5 registration line moves out of the tray `try` so it runs in every branch.
  - **`_on_quit(icon)`:** guards `icon is None` around `icon.stop()` only. It still sets `_really_quit` and calls `destroy()`; the guard never returns early. On GTK it skips its own pre-destroy geometry save (`closing` saves; calling the blocking getters from a non-main thread is safe, but redundant).
  - **The show path maps the window on GTK.** Before the first `main_win.show()` in step 4b, set `main_win.hidden = False`; then `show()` keeps `show_all()`. Wrap this in `_show_window(window)`, used by step 4b, `_on_show` (tray "Show") and `focus_window`.
    - **On GTK**, it sets `hidden = False`, then calls `show()` and `restore()`. `restore` is `deiconify` + `present`, which maps and raises.
    - **On Windows**, it is today's behaviour: step 4b `show()` and its native fallback; `_on_show` `show()`; `focus_window` `show()` + `restore()`.
  - **Visibility, read from GTK:**
    - **On GTK,** `window_visible()` returns `Gtk.Window.get_visible()` read on the GTK thread, through pywebview's own `webview.platforms.gtk.glib.idle_add`. The shell never imports `gi` itself. The idle stores the value and sets a `threading.Event`, and the caller waits at most 1 s, holding no lock. A timeout returns `None`, never blocks longer, and logs. When already on the main thread (`threading.current_thread() is threading.main_thread()`), it reads directly. `get_visible()` is the flag `show`/`hide` set, and so exactly the signal trap 2 breaks. Also report `mapped` (`get_mapped()`) read in the same idle; leg 5's hide checks may use it.
    - **On other backends,** the shell tracks it: set True after a successful show, False after a hide.
  - **`window_state()` → dict:**
    - `desktop`: `_desktop_window is not None`;
    - `mode`: `"window"` when a window is registered, else `None` (leg 5 adds `booting`/`browser`/`serve`);
    - `visible`: `window_visible()`, or `None` when there is no window or the 1 s read timed out (callers poll; `None` is not a failure);
    - `mapped`: GTK `get_mapped()`, or `None` (other backends, no window, timeout);
    - `tray`: `_tray_mode`;
    - `version`: `__version__`;
    - `pid`: `os.getpid()`.
  - **`quit_desktop()` → bool:** if a window is registered, run the current session's `_on_quit(self._icon)` and return True; else return False.
    - The current `DesktopSession` is kept in a module-level `_session`, set at the top of `run()` and reset when it returns.
    - Callable from any thread: `_on_quit` sets flags and calls `destroy()`, which pywebview dispatches to the GTK thread.
- **`app.py`:**
  - `GET /api/window/state` (plain `def`), returning `window_state()`.
  - `POST /api/window/quit` (plain `def`), returning `{"quit": quit_desktop(), "pid": os.getpid()}`.
  - Both lazy-import the shell like `window_focus`, sit behind the existing credential gate and Origin allowlist with no exemption, and catch everything (log, never 500 from a GUI error: return `quit: false`).
  - `window_focus` becomes a plain `def`. It calls `_shown_call` wrappers that can wait up to 20 s, and must not block the event loop.
- **`SECURITY-MODEL.md`:** one line in the routes or authentication section: the two new window routes are credential-gated like `/api/window/focus`. `quit` stops a desktop session the caller could already control, and grants nothing new.
- **Tests (unit):**
  - `tests/test_window_focus.py` style, a new `tests/test_window_routes.py` (or extend). Each route with and without a window, and with the credential missing (401).
  - In `test_desktop_shell.py`/`test_desktop_tray.py`:
    - the `_on_closing` modes (tray: hide; no tray: allow destroy; really-quit: allow);
    - GTK geometry reading `window.native` and never `window.width` (a fake whose `width` property raises proves it);
    - Wayland passes `None` for x/y;
    - `_show_window` clears `hidden` and calls `restore` on GTK, and leaves Windows unchanged;
    - `_on_quit(None)` raises nothing;
    - `window_visible()`'s 1 s bound with a never-run idle.
- **The real-GTK smoke test** (packaging-side, not in the unit tier): `packaging/spike/gtk-smoke.sh` (host side) plus an inner script.
  - **Scaffolding:** its own scaffolding, not `check.sh`/`inner.sh` (which are tied to the N/N+1 gate and layout), but reusing their pieces by copy: `useradd tester`, the `rt()` helper, the env block (`GDK_BACKEND=x11 PYWEBVIEW_GUI=gtk` plus the `WEBKIT_*`/`LIBGL` workarounds), `apt-get update`, and `dbus-run-session`.
  - **Container:** named `m32-gtk-smoke-<distro>`, removed at the end, with no `--privileged` and no `--network host`. It needs network for `apt-get install -y python3-xlib`, a harness-only package (Debian 13 main; Ubuntu 26.04 universe). Check `apt-cache policy python3-xlib` first and record it.
  - **Display:** a private `Xvfb :99 -screen 0 1920x1080x24`, with no window manager. Not WSLg.
  - **Run as** `tester`, with a scratch data dir and ports in 8490-8492.

  The steps:
  1. `the-one app` started in the background; wait for `/api/live`. Grep `app.log` for the tray decision line (`No system tray`), and record the mode.
  2. Poll `GET /api/window/state` until `visible: true` (within 20 s; `None` means poll again). Confirm through `xwininfo -root -tree` that the toplevel titled **exactly** `"GleepGlorp AI"` is `IsViewable`. The splash is titled `"GleepGlorp AI — starting"`, so match exactly. **This is trap 2's proof.**
  3. **Close with a real `WM_DELETE_WINDOW`**, run by `/usr/bin/python3` with python3-xlib, never the bundle's Python. A `ClientMessage` to that toplevel: `type=WM_PROTOCOLS`, format 32, data `[WM_DELETE_WINDOW, CurrentTime, 0, 0, 0]`, `event_mask=0`, then flush. Never `xdotool windowclose`, which destroys rather than deletes. The mode is `none`, so the interim behaviour is "close exits".
     - Assert the process exits within 15 s: no deadlock, **trap 1's proof**.
     - Assert `window-state.json` exists, with width and height.
  4. Relaunch; record the toplevel's `xwininfo` size as **S1** (the first launch seeds from the default size). Close again. Relaunch; record **S2**. Close a third time.
     - Assert S1 == S2: no growth, and the X window's outer size includes a fixed CSD margin, so compare X sizes with X sizes.
     - Assert the second and third saves wrote the same `window-state.json` width and height.
  5. Relaunch. `POST /api/window/quit` with the credential returns `{"quit": true, "pid": <the app's pid>}`, and the process exits within 15 s.
  6. Run once on each baseline. Evidence (logs, `xwininfo` before and after, state JSON) to `$HOME/the-one-m32-evidence/f2/leg3/<distro>/`.
- **The Flight 1 control** (`$HOME/the-one-m32-build/packages/gleepglorp-ai_0.11.8_amd64.deb`, read only). That build has no state or quit route, so the harness marks steps 2's route check and 5 "n/a on control" when the route answers 404. Trap 2 is shown by `xwininfo` reporting the toplevel `IsUnMapped` after boot with no focus request (Flight 1 already recorded this as finding 5). Trap 1 can only show if the old code registered `closing`, which it did only with a tray running. Record the control's tray line; under Xvfb with no tray host the old code probably had none, so trap 1 may not be reproducible on the control.

## Acceptance Criteria
- [ ] **AC1** — geometry on GTK: `_on_closing` reads geometry through `window.native` only on GTK; Wayland saves no position; Windows is unchanged. Unit tests prove all three, with a fake whose `width`/`x` properties raise if touched on GTK.
- [ ] **AC2** — `_on_closing` is registered in every tray mode, and its three outcomes are unit-tested. `_on_quit(None)` is safe.
- [ ] **AC3** — the show path: `_show_window` clears `hidden` and calls `show()` + `restore()` on GTK. Step 4b, `_on_show` and `focus_window` all use it. Windows' step 4b keeps its native fallback, and the existing Windows-path tests pass unchanged.
- [ ] **AC4** — routes:
  - `GET /api/window/state` and `POST /api/window/quit` behave as specified, with and without a window;
  - 401 without a credential;
  - plain `def`s;
  - `window_focus` is now a plain `def`, and `tests/test_window_focus.py` still passes;
  - the visibility read is bounded at 1 s (a unit test with an idle that never runs returns `None` in ≤ 1.5 s).
- [ ] **AC5** — the real-GTK smoke test passes on `ubuntu-26.04-baseline` and `debian-13-baseline`:
  - the window maps (state `visible: true` and `IsViewable`);
  - a `WM_DELETE_WINDOW` close exits within 15 s with geometry saved;
  - a relaunch restores size;
  - `POST /api/window/quit` exits within 15 s.

  - Size stays stable across relaunches (S1 == S2, and equal saved sizes).
  - The Flight 1 control shows trap 2 (`IsUnMapped` with no focus request). That is enough to prove the test can see a trap. Trap 1 on the control is recorded as reproduced or not, with the control's tray mode as the reason.
- [ ] **AC6** — `SECURITY-MODEL.md` line added.
- [ ] **AC7** — gates:
  - `make test-unit` passes (expected 12 skips);
  - `ruff check`/`ruff format --check` clean;
  - `shellcheck` clean on the smoke scripts;
  - no `m32-` container left running;
  - no port 8484/8485 used;
  - the operator data dir is untouched.
  - The browser lane covering the desktop/window API, if any test calls `/api/window/*` (grep first), passes with `THE_ONE_TEST_NETNS=1`.

## Verification Steps
- AC1-AC4 (the code half, done first; the harness half depends on leg 1's `build.sh` and comes second): `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_desktop_shell.py tests/test_desktop_tray.py tests/test_window_state.py tests/test_window_focus.py tests/test_window_routes.py -x --timeout 30`
- AC5: `packaging/spike/gtk-smoke.sh <distro> --deb <path>` output and evidence; the Flight 1 control run.
- AC6: `git diff SECURITY-MODEL.md`.
- AC7: `make test-unit`, `ruff`, `shellcheck`, `docker ps -a --filter name=m32-`.

## Implementation Guidance
1. Read the pywebview 5.4 GTK sources named in Context, and confirm the two traps for yourself before changing code.
2. Write the shell changes (`_is_gtk_backend`, geometry, `_on_closing` registration, `_show_window`, `window_visible`, `window_state`, `quit_desktop`, `_session`), keeping the Windows paths byte-identical in behaviour.
3. Add the routes, and convert `window_focus` to a plain `def`.
4. Unit tests. The `stub_desktop_host` fixture from leg 2 keeps D-Bus and X out; extend it if `display_session` needs stubbing for the Wayland test.
5. Build a `.deb` with leg 1's `build.sh` (`M32_BUILD=$HOME/the-one-m32-build/f2`, a scratch version such as `0.11.9.dev3` so it never collides with leg 1's N/N+1 packages). Write and run the smoke harness on both baselines. Run the Flight 1 control.
6. `make test-unit`; the flight-log section `### gtk-window-fixes`.

## Edge Cases
- **`window.native` is None** (the window was never created, or already destroyed): skip the save, logging at debug.
- **`get_position()` on Wayland** returns (0, 0); never store it (AC1).
- **`_on_closing` re-entered during `destroy()`** (the `delete-event` from `destroy`): `_really_quit` is already set by `_on_quit`, so it allows. No-tray mode has no flag, but the handler only allows, so re-entry is harmless.
- **`window_visible()` called from the GTK thread itself** (for example from a future `closing` path): reading directly avoids deadlocking on its own idle.
- **Splash window:** `_show_window` applies only to the main window; the splash keeps its own path.
- **Windows:** the WinForms `show()` path has the native fallback (`chrome.native_show`). Leave it exactly as is; only Linux GTK takes the new path. `tests/test_desktop_tray.py`'s "show callback calls `window.show()` but NOT `restore()`" encodes Windows behaviour: those tests stub `_is_gtk_backend` False (add it if missing), and a new GTK test asserts `restore` there.
- **The browser lanes:** the only browser hit on `/api/window` is the `/api/window/chrome` mock in `test_flow_settings_window_chrome_signal.py` (the `settings` lane). Run that lane once (`THE_ONE_TEST_NETNS=1`) for AC7.

## Files Affected
- `the_one/interfaces/desktop/shell.py`
- `the_one/interfaces/web/app.py`
- `SECURITY-MODEL.md`
- `tests/test_desktop_shell.py`, `tests/test_desktop_tray.py`, `tests/test_window_state.py`, `tests/test_window_focus.py`, `tests/test_window_routes.py` (new), `tests/conftest.py` (if the fixture grows)
- `packaging/spike/gtk-smoke.sh` (new) and its inner script
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section)

## Citation Audit
Checked against the worktree after leg 2 landed (uncommitted):
- `shell.py::_save_current_geometry`: reads `window.width, window.height, window.x, window.y`, guarded by `events.shown`. Verified.
- `shell.py::_on_show`: `show()` only. `focus_window`: `show()` then `restore()`. Verified.
- `shell.py` step 4b: `main_win.show()`, with the win32 native fallback. Verified.
- `shell.py` step 5: `_NoTrayError` for none/unavailable; `events.closing += self._on_closing` only after `run_detached()`. Verified.
- `shell.py::_on_quit`: `icon.stop()` inside a try with no None guard; saves geometry, then `destroy()`. Verified.
- `webview/platforms/gtk.py`:
  - `BrowserView.show` (`show_all`; `main_level()==0` and `hidden` → `hide()`), verified;
  - `restore` (idle `deiconify` + `present`), verified;
  - `destroy_window` (`idle_add(close_window)`), verified;
  - `get_size`/`get_position` (idle + `Semaphore.acquire`), verified;
  - `self.pywebview_window.native = self.window` (line 70), verified.
- `webview/window.py`: `events.closing = Event(self, True)`, verified; `Window.show/hide` are `@_shown_call`, verified.
- `app.py::window_focus`: `async def`. `window_chrome_post`: plain `def`. Verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
