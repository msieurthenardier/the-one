# Leg: tray-selection-and-doctor

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
On Linux, the app decides whether a tray exists before it imports pystray. When there is one, it picks a working pystray backend itself. It says plainly (a desktop notification) when WebKitGTK is missing and it falls back to the browser. `the-one doctor` gains advisory `sandbox:` and `tray:` lines, and a desktop-shell gate that tells "this bundle is broken" from "this host has no desktop GTK or no display".

## Context
- **Flight DDs:** DD3 (the tray decision first; backend choice; tray-host detection), DD11 (the `doctor` lines; the host-GTK-first desktop-shell rule; never the word "skipped"), DD14 (the no-WebKit notice).
- **Not this leg:**
  - The no-tray hide, quit, state route and version takeover (legs 3 and 5). In this leg a "no tray" decision only means the tray is not started, and closing keeps today's exit behaviour (the F4 path) until leg 5. Log that interim state in the flight log.
  - The GTK close and show fixes (leg 3).
- **Runs beside leg 1,** which touches only `packaging/`. This leg touches only `the_one/`, `tests/` and docs. Neither touches the other's files. Both append to the flight log: add only your own `### tray-selection-and-doctor` section under Leg Progress, through a single edit, and never rewrite other sections.
- **Flight 1 facts:**
  - A missing Ayatana typelib makes `import pystray` raise `ValueError` (`pystray/__init__.py::backend` catches only `ImportError`; `pystray/_appindicator.py:22-28`).
  - Stock Ubuntu 26.04 has a StatusNotifier host (its AppIndicator extension); stock Debian 13 GNOME has none.
  - pystray's `_xorg` opens an X display at import time (`pystray/_xorg.py:36`).
  - `doctor` needs `xvfb` today for the desktop-shell gate under the gtk backend.
- **The Windows CI lanes grep `desktop shell: OK`** (`.github/workflows/windows-installer.yml:108`, and the Concourse Windows tasks; grep `ci/` too). On Windows nothing in this leg may change the gate's text or outcome.

## Inputs
- `the_one/interfaces/desktop/tray.py` (`build_tray`, lazy `import pystray`)
- `the_one/interfaces/desktop/shell.py`:
  - `_webview_available`;
  - `DesktopSession.run` step 5 (tray wiring);
  - the browser-fallback `else` branch.
- `the_one/diagnostics.py`:
  - `_probe_desktop_shell`;
  - `run_doctor` (gates list, then `runtimes:` advisory lines).
- `the_one/platform/sandbox/factory.py::get_sandbox_backend` (the selection order and reasons)
- `tests/test_desktop_tray.py`, `tests/test_desktop_shell.py`, `tests/test_doctor.py`, `tests/test_sandbox_factory.py`

## Outputs
- **A Linux desktop-host helper module** under `the_one/interfaces/desktop/`. Suggested names: `host.py` for the host facts and `notify.py` for notifications; the Developer may choose others and records them. It provides:
  - `display_session()`: whether `WAYLAND_DISPLAY` or `DISPLAY` is set, and which session type (`wayland` or `x11`).
  - `host_has_desktop_gtk()`: a pure file-existence check that loads, imports and spawns nothing.
    - **GTK:** `libgtk-3.so.0` exists in a standard library directory: `/usr/lib/*-linux-gnu/`, `/lib/*-linux-gnu/`, `/usr/lib64/`, `/lib64/`, `/usr/lib/`, `/usr/local/lib/`. If none matches, parse `/sbin/ldconfig -p` by absolute path, with a timeout.
    - **WebKit:** a `WebKit2-4.1.typelib`, `WebKit2-4.0.typelib` or `WebKit2-6.0.typelib` exists. That is the same set today's `_webview_available` accepts, so Ubuntu 22.04's 4.0 keeps its window. The search covers the host typelib directories (`/usr/lib/*-linux-gnu/girepository-1.0`, `/usr/lib64/girepository-1.0`, `/usr/lib/girepository-1.0`, by glob, so no architecture is hardcoded) and any directories in a host-set `GI_TYPELIB_PATH`, excluding the AppImage fallback directory and anything under `sys._MEIPASS`.
    - **Never** `ctypes.util.find_library` (it needs `ldconfig` on `PATH` and sees PyInstaller's `_internal` first). **Never** `dlopen` GTK.
    - The file-system seam is injectable.
  - `choose_pystray_backend()`, in this order:
    1. an explicit `PYSTRAY_BACKEND` wins;
    2. else `appindicator`, if `gi.require_version("Gtk", "3.0")` succeeds **and** `gi.require_version("AyatanaAppIndicator3", "0.1")` or `("AppIndicator3", "0.1")` succeeds. pystray's `_appindicator` requires Gtk 3.0 first, unguarded;
    3. else `gtk`, if on an X11 session and `gi.require_version("Gtk", "3.0")` succeeds;
    4. else `xorg`, if on an X11 session;
    5. else `None`.

    Every `require_version` call catches `ValueError` and `ImportError`. It **never sets** `PYSTRAY_BACKEND`; it only returns a name.
  - `detect_tray(backend)`, which returns `"indicator"`, `"xembed"`, `"none"` or `"unavailable"`, each with a short reason:
    - `appindicator`: the session bus has an owner for `org.kde.StatusNotifierWatcher` (`org.freedesktop.DBus.NameHasOwner`), **and** that watcher's `IsStatusNotifierHostRegistered` property is true. Synchronous Gio D-Bus calls with a short timeout (≤ 1 s each).
    - `gtk`/`xorg`: an X11 session only, and `_NET_SYSTEM_TRAY_S<screen>` has a selection owner (python-xlib 0.33, already in the closure).
    - `None` (no usable backend): `"none"`, reason "no tray backend for this session".
    - An explicit `dummy`: `"none"`. Explicit `win32` or `darwin` on Linux: `"unavailable"`.
    - No session bus, no display, or `gi` not importable: `"unavailable"` with the reason ("no session bus", "no display session", …).
    - **No bus autolaunch.** If `DBUS_SESSION_BUS_ADDRESS` is unset and `$XDG_RUNTIME_DIR/bus` does not exist, return `"unavailable — no session bus"` at once. Otherwise connect with `Gio.DBusConnection.new_for_address_sync(address, AUTHENTICATION_CLIENT | MESSAGE_BUS_CONNECTION, …)`, never `Gio.bus_get_sync` (which can autolaunch `dbus-launch` and has no timeout).
    - The whole probe runs in a worker thread joined with a bound (about 3 s). A timeout gives `"unavailable"`. Synchronous GDBus from `_boot`'s non-main thread is safe, because GDBus uses its own worker thread.

    Injectable seams (callables) so unit tests need no D-Bus and no X.
  - `send_notification(summary, body)`: returns at once, never raises, and never blocks the caller. The work runs in a daemon thread:
    - **With `gi`:** a **synchronous** `org.freedesktop.Notifications.Notify` `call_sync` with a timeout of about 2 s, on a connection made as in `detect_tray` (no autolaunch). No Gio async: the browser-fallback branch has no main loop, so an async call would never complete.
    - **Without `gi`:** `gdbus call …` or `notify-send`, if either is on `PATH`, run through `subprocess.run(..., timeout=3)`, which kills it on timeout. It runs with the sanitized child environment (`the_one.platform.env`'s `_build_subprocess_env`/`clean_subprocess_env`), never the frozen `LD_LIBRARY_PATH`.
    - Otherwise it logs only.
- **`tray.py`:** `build_tray(*, on_show, on_quit, backend=None)`. When `backend` is given and `PYSTRAY_BACKEND` is unset, it sets `PYSTRAY_BACKEND` to it immediately before `import pystray`.
  - The shell passes the backend it already chose for `detect_tray`, so the decision is made once. It passes `backend=` **only when it is not None**, so the existing test fakes `_fake_build_tray(*, on_show, on_quit)` (`tests/test_desktop_tray.py`) keep working under the AC0 stub (`choose_pystray_backend` returns None).
  - The env var then stays set for the process, which is accepted: pystray reads it once, at its first import.
  - `build_tray` is never called when the decision is "no tray".
  - Tests use `monkeypatch.setenv`/`delenv` for it.
- **`shell.py`:**
  - In `DesktopSession.run` step 5 (Linux only), call `detect_tray(choose_pystray_backend())` before `build_tray`. On `"none"` or `"unavailable"`, do not build or start the tray, record the mode, and log one INFO line.
  - On `"indicator"`/`"xembed"`, behave as today.
  - Windows (and macOS) behave exactly as today, with no probe.
  - Record the decision in a module-level `_tray_mode` (`"indicator" | "xembed" | "none" | "failed" | None`), which leg 3's state route will read. It is reset to `None` at the top of `run()`, as `_really_quit` is.
    - Windows and macOS: it stays `None`.
    - `"indicator"`/`"xembed"`: set only **after** `run_detached()` succeeds.
    - `"failed"`: set in the existing except.
    - `"none"`: set at decision time.
  - `shell.py` reaches the host helpers as `host.fn(...)` at call time, not `from host import fn` at module top, so tests can monkeypatch the host module even after the fixtures `importlib.reload(shell)`.
  - Make `_webview_available()` on Linux require `host_has_desktop_gtk()` as well as today's `gi.require_version("WebKit2", …)` check, so the app and `doctor` share one predicate.
  - In the browser-fallback branch on Linux, call `send_notification("GleepGlorp AI", <body>)` before `webbrowser.open(url)`. The body names the missing piece:
  - no WebKit2 typelib: "GleepGlorp AI opened in your browser because WebKitGTK isn't installed. Install gir1.2-webkit2-4.1 for its own window.";
  - no GTK at all: "GleepGlorp AI opened in your browser because this desktop has no GTK 3 window libraries.";
  - PyGObject unavailable (a source install): "GleepGlorp AI opened in your browser because PyGObject (gi) isn't available."

  A small `missing_desktop_piece()` helper in the host module returns which applies.
- **`diagnostics.py`:**
  - **`_probe_desktop_shell`, rewritten:**
    - **Not Linux:** today's logic, byte-identical in outcome and wording.
    - **Linux, not frozen:** the existing code path, unchanged; the existing tests pin it. The new split applies only when `is_frozen()` and Linux.
    - **Linux, frozen:**
      **pystray's package `__init__` runs `backend()` on any import of `pystray` or a submodule** (`Icon = backend().Icon`). That raises `ValueError` with no Gtk typelib, and opens the X display under `_xorg`. So branches 1 and 2 **never import any `pystray` module**. `find_spec("pystray._x")` also imports the parent, so it is banned too.

      1. If `not host_has_desktop_gtk()`: import `PIL` and the tray module (lazy, so it imports no pystray), and check the bundle has pystray with `bundle_has_modules()` below. Everything present gives `OK — no desktop GTK on this host; the app opens in the browser`. A missing module, or an `ImportError` from `PIL` or the tray module, gives FAIL naming it.
      2. Elif `display_session()` is none: the same bundle check, plus `gi` and `webview`'s GTK platform module checked by `bundle_has_modules()` and never imported. All present gives `OK — no display session; tray not probed`; a missing one gives FAIL naming it.
      3. Else (GTK and a display): `backend = choose_pystray_backend()`.
         - If `backend` is None: report `OK — no tray backend for this session (no AppIndicator, Wayland); PIL importable` after importing `PIL` and the tray module only, never pystray.
         - Otherwise: import `PIL`, then `pystray` with `PYSTRAY_BACKEND=backend`, set and restored around the import (`os.environ` saved and restored in a `finally`), then the tray module. Any exception gives FAIL with the error. Success gives `OK — pystray (<backend>) + PIL importable`.

      **`bundle_has_modules(names)`** answers "is module X in this frozen bundle?" without importing a package `__init__`. For a dotted name:
      1. `spec = importlib.util.find_spec(top)`, which imports nothing for a top-level name;
      2. `locations = spec.submodule_search_locations`;
      3. for each further segment, check that it appears in `pkgutil.iter_modules(locations)`; if it is a package and more segments follow, descend with `locations = [os.path.join(loc, seg) for loc in locations]`.

      Under PyInstaller, `PyiFrozenFinder` handles `iter_modules` on those virtual paths. The leg's tests verify this on the dev host's real `pystray` package without importing `pystray/__init__`. If the PYZ case cannot be confirmed by unit test, record that it is verified in leg 1's frozen bare-host run (AC8 there showed the gate's output) and in the hosted run.

      The word "skipped" never appears in any Linux frozen detail.
  - **Two advisory lines,** printed after the gate lines in their own block, never in `gates`:
    - `sandbox: bubblewrap`, or `sandbox: passthrough — <reason>`, from a new `describe_selection()` in `sandbox/factory.py`. It returns `(backend_name, reason)` using exactly `get_sandbox_backend()`'s order, and shares its helpers so the two cannot drift. It emits no log and reuses the userns probe cache.
    - `tray: <mode> — <reason>` (Linux), consistent with the desktop-shell branch:
      - `tray: none — no desktop GTK on this host` when `not host_has_desktop_gtk()`;
      - `tray: none — no display session` with no display;
      - only with GTK and a display does it run `choose_pystray_backend()` and `detect_tray()`.

      On other platforms: `tray: system tray (Windows)` / `tray: not probed (macOS)`.
  - Exit code, gate names and gate count are unchanged.
- **Tests** (new or extended): `tests/test_desktop_host.py` (or named after the module), `tests/test_desktop_tray.py`, `tests/test_desktop_shell.py`, `tests/test_doctor.py`, `tests/test_sandbox_factory.py`.
- **Docs:** a short paragraph in `the_one/agents.md`'s Desktop launcher section, additive (shared with Mission 31). The CLAUDE.md doctor gate prose is untouched except one additive sentence naming the two advisory lines.

## Acceptance Criteria
- [ ] **AC0 — existing tests keep their meaning.** Tests that run `_boot`/`DesktopSession.run` on Linux with a mocked `build_tray` must not hit the real probes. These include:
  - `tests/test_desktop_tray.py::_run_desktop_with_tray` and its users;
  - the `_boot` tests in `tests/test_window_state.py`;
  - the browser-fallback tests in `tests/test_desktop_shell.py`;
  - the fake-`gi` `_webview_available` tests;
  - the `run_doctor` tests that run real probes.

  A shared fixture stubs the probes in those modules: `detect_tray` → `"indicator"`, `choose_pystray_backend` → `None`, `host_has_desktop_gtk` → `True`, `send_notification` → no-op. Use `tests/conftest.py`, or per-module autouse fixtures, applied only where a test does not set its own. No test opens a real D-Bus connection or X display, and no test spawns `notify-send`/`gdbus`. The existing assertions are unchanged, apart from adding `host_has_desktop_gtk=True` to the fake-`gi` `_webview_available` tests. The fixture also resets `shell._tray_mode`.
- [ ] **AC1 — backend choice.** Unit tests, through injected or monkeypatched `gi.require_version` and the environment, prove:
  - an explicit `PYSTRAY_BACKEND` is respected;
  - Ayatana present gives `appindicator`;
  - only the legacy AppIndicator present gives `appindicator`;
  - neither, on X11, gives `gtk`;
  - neither, with Gtk unavailable on X11, gives `xorg`;
  - neither, on Wayland with no `DISPLAY`, gives `None`;
  - a `ValueError` from `require_version` never escapes;
  - `choose_pystray_backend()` never sets `PYSTRAY_BACKEND`;
  - an AppIndicator typelib without Gtk 3.0 never gives `appindicator`.
- [ ] **AC2 — tray detection.** Unit tests with injected D-Bus and X seams prove:
  - watcher owned and host registered gives `indicator`;
  - watcher owned but no host registered gives `none`;
  - no watcher gives `none`;
  - no session bus gives `unavailable`;
  - X11 with a tray owner gives `xembed`;
  - X11 without one gives `none`;
  - a Wayland session never runs the X11 check.

  A D-Bus timeout or exception gives `unavailable`, not a raise. With `DBUS_SESSION_BUS_ADDRESS` unset and no `$XDG_RUNTIME_DIR/bus`, the result is `unavailable` and no connection is attempted: the connect seam is never called. `detect_tray(None)` gives `none`, as does an explicit `dummy`.
- [ ] **AC3 — no pystray import without a tray.** A unit test (which deletes any earlier `pystray` entry from `sys.modules` with `monkeypatch.delitem`, so it is restored afterwards) proves that when `detect_tray` returns `none` or `unavailable`, `DesktopSession` step 5 never calls `build_tray`, and `pystray` is not imported (it is absent from `sys.modules`, since the test removes it first). `_tray_mode` records the mode. On `win32` (a monkeypatched `sys.platform`), the probe is never called and today's path runs. The existing tray tests still pass.
- [ ] **AC4 — the desktop-shell gate split.** Unit tests cover each branch, with `is_frozen`, `host_has_desktop_gtk`, `display_session` and `find_spec` stubbed:
  - frozen Linux without GTK: OK, with the browser wording, **and** `pystray` is not imported. A stub `pystray` module in `sys.modules` whose import raises `ValueError` proves this: it is never touched;
  - frozen Linux without GTK, with pystray missing from the bundle: FAIL;
  - frozen Linux with GTK and no display, all specs found: OK "no display session";
  - the same with one module missing: FAIL naming it, again with no `pystray` import;
  - frozen Linux with GTK, a display and no backend (Wayland, no AppIndicator): OK "no tray backend", with no `pystray` import;
  - `PYSTRAY_BACKEND` is restored after branch 3, whatever its value before;
  - frozen Linux with GTK and a display, where the backend import raises: FAIL;
  - non-frozen: today's outputs;
  - `win32`: today's outputs, byte-identical.

  No Linux frozen detail contains "skipped".
- [ ] **AC5 — advisory lines.** `run_doctor` output contains a `sandbox:` line and a `tray:` line, after the gate lines and outside the gates. Unit tests stub `describe_selection` for each factory reason: test bypass, non-Linux, bwrap missing, userns unavailable, userns probe error, and bubblewrap. Each line's text names its reason.
  - `describe_selection()` and `get_sandbox_backend()` agree, through one parametrized test over the same stubbed conditions.
  - `describe_selection()` logs nothing and leaves `_LOGGED` unchanged.
  - Both new lines encode in cp1252, since the Windows doctor's stdout codec once crashed on `→`. Use `—`, never `→`.
  - Exit code and the 12 gate names are unchanged.
- [ ] **AC6 — the no-WebKit notice.**
  - **Notification sent:** a unit test runs the browser-fallback branch on `linux`, with `_webview_available` False and stubbed `send_notification`, `webbrowser.open` and the server. `send_notification` is called once, with the body for the missing piece (each of the three bodies covered), before `webbrowser.open`.
  - **Not sent:** on `win32`, and on the webview path.
  - **`send_notification` itself, never raising or blocking:** a test with Gio failing; one with `gi` unimportable and no `gdbus`/`notify-send` (it only logs); and one with a hung backend (it returns within the bound).
- [ ] **AC7 — `_webview_available` and `doctor` agree.** A unit test shows `_webview_available()` on Linux returns False when `host_has_desktop_gtk()` is False, even if `gi.require_version("WebKit2")` would succeed, and True only when both hold.
- [ ] **AC8 — a real-host smoke on this dev host** (Ubuntu 24.04 under WSLg: has GTK and WebKit, no Ayatana, and probably no StatusNotifier host):
  - `.venv/bin/the-one doctor` prints `sandbox:` and `tray:` lines with plausible values;
  - `desktop shell` reads as today for a non-frozen run;
  - exit 0.

  Run it with `THE_ONE_DATA_DIR` set to a scratch dir under `$HOME` and `THE_ONE_PORT=8496`. `doctor` starts no server, but set both anyway.

  Also run it once with `DBUS_SESSION_BUS_ADDRESS` unset and `XDG_RUNTIME_DIR` pointed at an empty scratch dir. That must print `tray: unavailable — no session bus`, exit 0, and start no `dbus-daemon`: compare `pgrep -u "$USER" dbus-daemon` before and after, reading only, never killing.

  Record the output in the flight log.
- [ ] **AC9 — gates.**
  - `make test-unit` passes; record counts and skips against the expected 12.
  - `ruff check` and `ruff format --check` pass on `the_one/ tests/ scripts/ evals/`.
  - `git diff --stat` touches only `the_one/`, `tests/`, `the_one/agents.md`, CLAUDE.md (at most one additive sentence) and this flight's log.

## Verification Steps
- AC1-AC7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_desktop_host.py tests/test_desktop_tray.py tests/test_desktop_shell.py tests/test_doctor.py tests/test_sandbox_factory.py -x --timeout 30`
- AC8: the `doctor` output captured into the flight log.
- AC9: `make test-unit`, `ruff`, `git diff --stat`.

## Implementation Guidance
1. **Write the host module first,** with injectable seams (module-level callables or keyword arguments), so tests need no D-Bus or X.
   - **One shared connect helper** serves both `detect_tray` and `send_notification`. The address is `$DBUS_SESSION_BUS_ADDRESS` if set, else `"unix:path=" + $XDG_RUNTIME_DIR + "/bus"`, but only after `os.path.exists` confirms that socket; with neither, it returns no connection. It connects with `Gio.DBusConnection.new_for_address_sync(address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)`. It **never** uses `Gio.bus_get_sync`.
   - The probe runs in a `daemon=True` worker thread joined with a bound. On timeout the result is discarded and the answer is `unavailable`. The X11 `Display()` call runs inside the same bounded worker, because an unreachable TCP `DISPLAY` can hang.
   - Then `connection.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner", GLib.Variant("(s)", ("org.kde.StatusNotifierWatcher",)), GLib.VariantType("(b)"), Gio.DBusCallFlags.NONE, 1000, None)`.
   - Then `org.freedesktop.DBus.Properties.Get("org.kde.StatusNotifierWatcher", "IsStatusNotifierHostRegistered")` on `/StatusNotifierWatcher`, with reply type `GLib.VariantType("(v)")`. Unwrap the variant to get the boolean.
   - Every `gi` import is lazy, inside the function.
2. **The X11 check:** `Xlib.display.Display()`, then `get_selection_owner(intern_atom("_NET_SYSTEM_TRAY_S%d" % screen))` (non-zero means owned), then close the display. Only when `display_session()` is X11.
3. **`choose_pystray_backend`:** only on Linux. `gi.require_version` raises `ValueError` for a missing namespace, and `ImportError` (or `ValueError`) once a different version of the namespace is already loaded. Guard both. It returns a name and sets nothing.
4. **Wire `tray.py`:** the `backend` keyword, as in Outputs. Keep the import lazy.
5. **Wire `shell.py` step 5.** Keep the existing try/except around build and start for the `"failed"` mode (set `_tray_mode = "failed"` in the except).
6. **The `diagnostics.py` rewrite.** Keep the non-Linux and non-frozen paths byte-identical (tests pin them).
7. **`describe_selection()` in `factory.py`.** Refactor the selection order into one private helper that returns `(backend_class_name, reason_key, human_reason)`. Then `get_sandbox_backend()` logs and instantiates from it, and `describe_selection()` returns it without logging. The log-once texts and levels must stay the same (`tests/test_sandbox_factory.py` pins them).
8. **The notice in the browser-fallback branch,** Linux only.
9. **Tests, then the AC8 smoke, then `make test-unit`.**
10. **The flight-log entry** under Leg Progress. Note the interim "no tray means close exits" state until leg 5.

## Edge Cases
- **`gi` importable, but no Gtk typelib on the host** (a bare host with the AppImage's fallback girepository): `choose_pystray_backend` must not raise. `require_version("Gtk")` inside pystray would raise `ValueError`, which is why the probe runs first.
- **`DISPLAY` set but the X server is unreachable:** `Xlib.display.Display()` raises. That counts as `unavailable`, not a crash.
- **`WAYLAND_DISPLAY` and `DISPLAY` both set** (XWayland on GNOME): the session is `wayland`. Never run the XEmbed check there; it would see XWayland's tray owner, if any.
- **The dev host under WSLg:** probably has no StatusNotifierWatcher, so the decision is `none` or `unavailable`. That is expected; record it.
- **`describe_selection()` while a test-bypass env is set:** it reports `passthrough — test bypass`, matching `get_sandbox_backend()`.
- **`webview.platforms.gtk`:** never imported by `doctor` branch 2. The bundle check uses `bundle_has_modules`, since importing it pulls in `gi` and GTK.
- **Python 3.11:** CI runs 3.11. Use nothing newer than 3.11, and don't rely on a 3.12 `asyncio`/`typing` behaviour (squawk 0251's lesson).

## Files Affected
- `the_one/interfaces/desktop/host.py` (new; name at the Developer's choice), `the_one/interfaces/desktop/notify.py` (new, or merged into the same module)
- `the_one/interfaces/desktop/tray.py`, `the_one/interfaces/desktop/shell.py`
- `the_one/diagnostics.py`, `the_one/platform/sandbox/factory.py`
- `tests/test_desktop_host.py` (new), `tests/test_desktop_tray.py`, `tests/test_desktop_shell.py`, `tests/test_doctor.py`, `tests/test_sandbox_factory.py`, `tests/test_window_state.py`, `tests/conftest.py` (the AC0 fixture, if shared)
- `the_one/agents.md` (additive), `CLAUDE.md` (at most one additive sentence)
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section only)

## Citation Audit
Checked at `980415e`:
- `tray.py::build_tray`: `import pystray` inside the function. Verified.
- `shell.py::_webview_available`: win32/darwin give True; Linux tries `gi.require_version("WebKit2", ver)` for 4.1/4.0/6.0. Verified.
- `shell.py::DesktopSession.run` step 5: `build_tray`, `run_detached()`, `events.closing += _on_closing` in a try; the except logs the F4 fallback. Verified.
- `shell.py` browser-fallback `else`: `_wait_until_serving`, mint the handoff, `webbrowser.open(url)`, then `thread.join()`. Verified.
- `diagnostics.py::_probe_desktop_shell`: imports PIL, pystray, then the tray module; frozen means `ImportError` is a FAIL; the generic `except` is "unexpected error". Verified.
- `diagnostics.py::run_doctor`: `gates` list of 12; then `runtimes:` lines; `RESULT`. Verified.
- `factory.py::get_sandbox_backend`: test bypass → non-Linux → bwrap missing → userns unavailable → userns error → bubblewrap; log-once keys. Verified.
- `.github/workflows/windows-installer.yml:108`: `grep -q "desktop shell: OK"`. Verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
