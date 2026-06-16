from __future__ import annotations

import logging
import signal
import socket
import sys
import threading
import time
import webbrowser

import httpx
import uvicorn

from the_one import __version__
from the_one.config import settings

log = logging.getLogger(__name__)

# ── Module-level lifecycle state (reset to these defaults each process launch) ──
# Set to True by the Quit tray-menu callback so the `closing` handler allows
# the window destroy instead of hiding it.
_really_quit: bool = False
# The pywebview Window object; populated in run_desktop() for use by callbacks.
_desktop_window = None


def _wait_until_serving(host: str, port: int, timeout: float = 15.0) -> None:
    """Poll /api/info until the app actually serves (lifespan startup done)."""
    deadline = time.monotonic() + timeout
    url = f"http://{host}:{port}/api/info"
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    raise RuntimeError(f"server did not become ready at {url} within {timeout}s")


def _graceful_shutdown(server, thread, timeout: float = 60.0) -> None:
    """Drive uvicorn's lifespan shutdown to completion. No-op if no local
    server (a window-only client owns nothing to drain — DD4 case b)."""
    # Callers pass BOTH server+thread, or NEITHER (DD4 case b: a window-only
    # client owns no local server). No-op on `server is None`.
    if server is None:
        return
    server.should_exit = True
    thread.join(timeout=timeout)


def _select_port(host: str, port: int, retries: int = 3, delay: float = 0.3) -> tuple[int, bool]:
    """Select the port to use and determine if a the-one instance is already running.

    Returns (port_to_use, is_our_instance):
    - (port, False): port is free — start a new server on the configured port.
    - (port, True): a the-one of OUR version is already answering on that port
      (DD4 case b) — do NOT start a second server.
    - (free_port, False): a foreign process holds the configured port (DD4 case c)
      — bind-0 a free port for this instance.

    Uses a connect-probe (not a bind-probe with SO_REUSEADDR, which gives a
    false "free" on a TIME_WAIT port). Includes a startup-retry so a the-one
    that just bound but hasn't finished lifespan startup (/api/info not yet 200)
    isn't misclassified as foreign.
    """
    for attempt in range(retries):
        # (b) a the-one of OUR version already answering?
        # json() raises JSONDecodeError (a ValueError subclass) on a non-JSON 200.
        try:
            r = httpx.get(f"http://{host}:{port}/api/info", timeout=1.0)
            if r.status_code == 200 and r.json().get("version") == __version__:
                return port, True
        except (httpx.HTTPError, ValueError):
            pass
        # Is ANYTHING listening? connect-probe — no bind race.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            occupied = s.connect_ex((host, port)) == 0
        if not occupied:
            return port, False  # (a) free — fast path, no retry
        if attempt < retries - 1:
            # occupied-not-(yet)-ours: a starting the-one? give it the startup window
            time.sleep(delay)
    # (c) occupied by a foreign process (or a the-one that never confirmed) →
    # a different the-one VERSION lands here too (→ a 2nd instance on a free
    # port; the existing one is untouched — intended upgrade-coexist behavior)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1], False


def _webview_available() -> bool:
    """Probe whether a WebView backend is available without initializing the GUI stack.

    Returns True on win32/darwin (WebView2 / WKWebView assumed present).
    On Linux, probes the gi typelib via gi.require_version WITHOUT importing
    Gtk/WebKit2 (importing can init GLib / touch a display / hang on headless).
    Catches ImportError (no gi) and ValueError (typelib absent).
    """
    if sys.platform in ("win32", "darwin"):
        return True  # WebView2 (Win) / WKWebView (mac) assumed present
    try:
        import gi
    except ImportError:
        return False
    for ver in ("4.1", "4.0", "6.0"):  # Ubuntu 22.04 has 4.0; newer 4.1; GTK4 6.0
        try:
            gi.require_version("WebKit2", ver)
            return True  # typelib present — do NOT import Gtk/WebKit2
        except ValueError:
            continue
    return False


def focus_window() -> bool:
    """Raise and restore the registered desktop window (thread-safe).

    Returns True when a window is registered and show()/restore() succeeded.
    Returns False when no window is registered (e.g. serve mode) or the call
    raises (logged; never propagated into the HTTP handler).
    """
    if _desktop_window is None:
        return False
    try:
        _desktop_window.show()
        _desktop_window.restore()
        return True
    except Exception:
        log.warning("focus_window: show()/restore() raised", exc_info=True)
        return False


def run_desktop() -> None:
    global _really_quit, _desktop_window

    # M15 F6 review-fix: defensive second call (idempotent).  Covers any entry
    # path that doesn't go through frozen_entry_gui.py (e.g. a future launcher
    # script or test harness that calls run_desktop() directly).  The primary
    # call is in packaging/windows/frozen_entry_gui.py before cli_entry().
    from the_one.platform.env import ensure_stdio_streams  # noqa: PLC0415

    ensure_stdio_streams()

    # Reset process-local state on each launch (e.g. if run_desktop() is called
    # more than once in tests after a reload).
    _really_quit = False
    _desktop_window = None

    host, port = settings.host, settings.port
    sel_port, is_ours = _select_port(host, port)
    if is_ours:
        # A the-one of our version already owns this port — raise its window
        # and exit instead of opening a duplicate (DD4). Header-less loopback
        # POST (no Origin header) clears the OriginAllowlistMiddleware.
        try:
            httpx.post(f"http://{host}:{sel_port}/api/window/focus", timeout=2.0)
        except httpx.HTTPError:  # intentionally broad — covers ConnectError + TimeoutException
            log.warning("focus POST to running instance failed; exiting anyway")
        return
    url = f"http://{host}:{sel_port}/"
    server = None
    thread = None
    # is_ours=True already returned above; reaching here means is_ours=False —
    # we always start our own server on the selected port.
    from the_one.interfaces.web.app import app

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=sel_port, log_level="info"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_until_serving(host, sel_port)
    try:
        if _webview_available():
            try:
                import webview  # lazy: optional [gui] extra; off chat/version
            except ImportError as exc:
                raise SystemExit(
                    "pywebview is not installed. "
                    "Install the desktop extra: pip install 'the-one[gui]'"
                ) from exc

            # ── Window-state restore ─────────────────────────────────────────
            # Load the saved geometry (if any), clamp to current screen bounds,
            # then pass width/height/x/y into create_window so the window reopens
            # where the user left it.  If no state exists, fall through to
            # create_window with only F4 defaults (no extra kwargs).
            from the_one.interfaces.desktop.window_state import (
                clamp_to_bounds,
                load_state,
            )

            _saved_state = load_state()
            _create_kwargs: dict = {"frameless": False}
            if _saved_state is not None:
                try:
                    # The installed pywebview exposes `webview.screens` as a
                    # proxy_tools lazy property that *already evaluates to* the
                    # list of Screen objects — it is NOT callable.  Other builds
                    # (editable source installs, future versions) may expose it as
                    # a function.  Resolve robustly so both forms work.
                    _screens = webview.screens
                    if not isinstance(_screens, (list, tuple)):
                        try:
                            _screens = list(_screens)  # proxy-list / iterable → materialise
                        except TypeError:
                            _screens = _screens()      # callable form
                    _clamped = clamp_to_bounds(_saved_state, _screens)
                    _create_kwargs["width"] = _clamped["width"]
                    _create_kwargs["height"] = _clamped["height"]
                    if "x" in _clamped:
                        _create_kwargs["x"] = _clamped["x"]
                    if "y" in _clamped:
                        _create_kwargs["y"] = _clamped["y"]
                except Exception:
                    log.warning("window_state: restore failed; using defaults", exc_info=True)

            # frameless=False (explicit): native OS frame (title bar + app name)
            # and NO browser chrome (no URL bar — it's not a browser). DD8's
            # "transparent web-underneath" = absence of browser chrome, not a
            # borderless window. Explicit guards against a pywebview default change.
            # ── / Window-state restore ───────────────────────────────────────────
            _desktop_window = webview.create_window("GleepGlorp AI", url, **_create_kwargs)

            # ── Tray lifecycle wiring ────────────────────────────────────────────
            # Build the pystray icon and wire the close-to-tray + Quit callbacks.
            # This entire block degrades gracefully on failure: if the tray can't
            # start (no backend, import error), we log a warning and skip
            # registering the `closing` handler — the window's X then falls back
            # to pywebview's default destroy (F4 behavior).

            _icon = None  # tray icon reference, used by on_quit / on_show

            def _save_current_geometry(window) -> None:
                """Capture and persist window geometry — best-effort, never blocks.

                Guards:
                1. Skip if ``shown`` event hasn't fired yet — reading width/x/y
                   before the window has shown triggers ``shown.wait(15)`` internally,
                   which would block the GUI thread up to 15 s during close.
                2. Wrap geometry reads in try/except — they are GUI-backed properties
                   in pywebview 5; ``getattr(..., None)`` would NOT catch a
                   GUI-not-ready error, but a broad except does.
                """
                if not window.events.shown.is_set():
                    return
                try:
                    w, h, x, y = window.width, window.height, window.x, window.y
                except Exception:
                    log.warning("window_state: capture failed", exc_info=True)
                    return
                from the_one.interfaces.desktop.window_state import save_state
                try:
                    save_state(w, h, x, y)
                    log.debug("window_state: saved geometry %sx%s @ %s,%s", w, h, x, y)
                except Exception:
                    log.warning("window_state: capture failed", exc_info=True)

            def _on_closing() -> bool:
                """pywebview closing handler: hide to tray instead of destroying.

                Returns False (cancel destroy) when the tray is active and
                _really_quit is not set.  Returns True (allow destroy) when the
                Quit callback has already set _really_quit.

                IMPORTANT: pywebview's Event.set() wraps each handler in
                try/except and swallows exceptions — a raise inside this handler
                is silently ignored and the cancel return value is lost, which
                would destroy the window unexpectedly.  Mitigation: the
                window.hide() call is wrapped in try/except; on failure we return
                True (allow the close deterministically) rather than let an
                exception leak into the swallow.
                """
                # Capture geometry before any hide/destroy (best-effort).
                _save_current_geometry(_desktop_window)

                if _really_quit:
                    return True  # Quit callback already requested real destroy

                # Show first-run notice (once only).
                from the_one.interfaces.desktop.notice import mark_notice_shown, notice_shown
                from the_one.interfaces.desktop.tray import notify

                if not notice_shown():
                    mark_notice_shown()
                    if _icon is not None:
                        notify(
                            _icon,
                            "GleepGlorp AI is still running in the system tray"
                            " — Quit from the tray menu to exit",
                            "GleepGlorp AI",
                        )

                # Hide the window (cancel the close).
                try:
                    _desktop_window.hide()
                except Exception:
                    # hide() failed — allow the close rather than silently
                    # swallowing into the event handler wrapper.
                    return True

                return False  # cancel destroy — app keeps serving

            def _on_show(icon) -> None:
                """Tray "Show" menu callback: show the window.

                The window was hidden via close-to-tray (not minimized), so
                show() is sufficient.  restore() is intentionally omitted here —
                it snapped the window size on each show when the window was merely
                hidden.  focus_window() keeps show()+restore() for the
                single-instance-focus path where the window may be minimized.
                """
                if _desktop_window is not None:
                    _desktop_window.show()

            def _on_quit(icon) -> None:
                """Tray "Quit" menu callback: graceful full exit.

                Order: set really-quit flag → stop tray (MUST complete —
                run_detached() spawns a non-daemon thread; skipping stop() leaves
                it alive and hangs the process after _graceful_shutdown) →
                destroy window (causes webview.start() to return) → the existing
                `finally: _graceful_shutdown(server, thread)` drains the server.
                """
                global _really_quit
                _really_quit = True  # tell _on_closing to allow destroy

                # icon.stop() MUST run; guard so it survives even if destroy raises.
                try:
                    icon.stop()
                except Exception:
                    log.warning("pystray icon.stop() raised during Quit — ignored", exc_info=True)

                if _desktop_window is not None:
                    # Capture geometry before destroy (redundant-but-safe per edge-case
                    # note in leg spec: closing fires on destroy in pywebview-5.4 for all
                    # known backends, so _on_closing already ran; this second write is
                    # idempotent forward-safety for any future backend that skips it).
                    _save_current_geometry(_desktop_window)
                    _desktop_window.destroy()

            # Try to start the tray icon on a detached thread (DD2).
            try:
                from the_one.interfaces.desktop.tray import build_tray

                _icon = build_tray(on_show=_on_show, on_quit=_on_quit)
                _icon.run_detached()  # non-blocking; starts background thread
                # Only register the closing handler when the tray is active.
                _desktop_window.events.closing += _on_closing
            except Exception:
                log.warning(
                    "System tray unavailable — close button will exit the app (F4 fallback)",
                    exc_info=True,
                )
                # _on_closing NOT registered → window's X uses pywebview default destroy.

            # ── / Tray lifecycle wiring ──────────────────────────────────────────

            # Persist localStorage/cookies (e.g. the theme preference) across app
            # restarts AND reinstalls. pywebview defaults to private_mode=True — an
            # ephemeral profile that drops all web storage between launches, so a
            # localStorage-backed setting like the theme resets every restart. Point
            # the webview at a stable per-user profile dir under data_dir (outside the
            # install dir, and migrated with the rest of the user's data) so settings
            # survive. (M15 F5 post-landing fix: theme didn't survive restart/reinstall.)
            storage_dir = settings.data_dir / "webview"
            storage_dir.mkdir(parents=True, exist_ok=True)
            webview.start(  # blocks until window closes (or Quit → destroy)
                private_mode=False,
                storage_path=str(storage_dir),
            )
        else:
            webbrowser.open(url)
            if server is not None:
                # Main thread is free (no GUI loop) — install a SIGINT handler
                # that triggers the uvicorn shutdown, then join to let the
                # lifespan drain complete (mirrors DD2's window-close path).
                signal.signal(signal.SIGINT, lambda *_: setattr(server, "should_exit", True))
                thread.join()  # blocks until SIGINT → should_exit → drain
            # case (b)+no-backend: nothing to block on; just return
    finally:
        _graceful_shutdown(server, thread)  # no-op when server is None (case b)
