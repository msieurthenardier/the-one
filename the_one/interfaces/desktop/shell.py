"""The desktop launcher: ``DesktopSession`` and ``run_desktop``.

Mission 32, Flight 3, DD1: the version takeover (``takeover.py``), the window
control helpers (``window_control.py``) and the lifecycle flags
(``session_state.py``) moved out; this module reaches them through those
modules, never by importing their names.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
import webbrowser

import httpx
import uvicorn

from the_one.config import settings
from the_one.interfaces.desktop import (
    chrome,
    macos_dock,
    notice,
    takeover,
    tray,
    window_control,
)
from the_one.interfaces.desktop import host as desktop_host
from the_one.interfaces.desktop import window_state as window_state_store
from the_one.interfaces.desktop.session_state import state
from the_one.platform import env as platform_env

log = logging.getLogger(__name__)

# The one-time notice for a close that hides the window into the tray.
# Short on purpose: GNOME's banner truncates long text with an ellipsis.
# ``tray.notify(icon, message, title)`` order.
# macOS only: how long _boot waits for the (hidden) main window's first page load before
# showing it anyway. A local load is well under a second and a cold first launch (Gatekeeper
# scan, App Translocation) a few; 12 s is generous, yet inside the 15 s server wait and the
# 25 s splash handler wait, so a page that never reports `loaded` still shows a window.
MAIN_LOADED_BOUND = 12.0

_TRAY_NOTICE_TITLE = "GleepGlorp AI is still running"
_TRAY_NOTICE_BODY = "It's in the tray. Click its icon to show it or quit."


# ── Splash screen ─────────────────────────────────────────────────────────────
# Inline HTML rendered before the app server is up (no localhost URL, no CDN).
# The splash is a frameless pywebview window shown during the uvicorn boot wait;
# it is destroyed once the main window's `loaded` event fires.
# HAT-deferred (Leg 7): visual appearance on real Windows.
#
# The brand logo (gleepglorp_med.png) is embedded as a base64 data URI read at
# runtime from the bundled static asset.  The spec file
# (packaging/windows/the_one.spec) collects interfaces/web/static/**/* via
# collect_data_files so gleepglorp_med.png IS in the bundle at
# static/brand/gleepglorp_med.png.  Resolution uses STATIC_DIR from web.app
# (a Path(__file__).parent / "static" that resolves under _MEIPASS correctly).
# The import is lazy (inside the builder function) to avoid circular-import risk
# at module-load time.  If the asset is unreadable for any reason the builder
# falls back to the text-only HTML and logs a warning — a splash-asset failure
# must NEVER raise or hang boot.

_SPLASH_TEXT_ONLY_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100%; height: 100%;
    background: __BG__;
    display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: __FG__;
    user-select: none;
    -webkit-app-region: drag;
  }
  .splash {
    display: flex; flex-direction: column;
    align-items: center; gap: 18px;
  }
  .logo {
    width: 56px; height: 56px;
    background: linear-gradient(135deg, #6c63ff 0%, #4e46e5 100%);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px;
  }
  .name {
    font-size: 18px; font-weight: 600;
    letter-spacing: 0.02em;
    color: __FG__;
  }
  .status {
    font-size: 12px; color: __MUTED__;
    letter-spacing: 0.05em;
  }
  .bar {
    width: 120px; height: 2px;
    background: __TRACK__;
    border-radius: 1px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #6c63ff, #4e46e5);
    border-radius: 1px;
    animation: slide 1.4s ease-in-out infinite;
  }
  @keyframes slide {
    0%   { transform: translateX(-100%); }
    50%  { transform: translateX(0); }
    100% { transform: translateX(100%); }
  }
</style>
</head>
<body>
  <div class="splash">
    <div class="logo">&#9670;</div>
    <div class="name">GleepGlorp AI</div>
    <div class="bar"><div class="bar-fill"></div></div>
    <div class="status">starting…</div>
  </div>
</body>
</html>
"""


def _splash_text_only(theme: str = "dark") -> str:
    """The text-only splash for ``theme`` (colours from the chrome palette)."""
    pal = chrome.PALETTE.get(theme) or chrome.PALETTE["dark"]
    return (
        _SPLASH_TEXT_ONLY_TEMPLATE.replace("__BG__", pal["bg"])
        .replace("__FG__", pal["text"])
        .replace("__MUTED__", pal["fg_secondary"])
        .replace("__TRACK__", pal["border"])
    )


_SPLASH_TEXT_ONLY = _splash_text_only("dark")


def _splash_html(theme: str = "dark") -> str:
    """Build the splash HTML, embedding the brand logo as a base64 data URI.

    Reads gleepglorp_med.png from the bundled static directory at runtime and
    inlines it as ``<img src="data:image/png;base64,...">``.  This works both
    in development (filesystem) and in a PyInstaller freeze (_MEIPASS puts the
    collected static tree at the same path relative to web/app.py).

    Graceful fallback: any exception during asset resolution/encoding is caught,
    a warning is logged, and the text-only splash HTML is returned.  A
    splash-asset problem must never raise or hang boot.

    ``theme`` ("light" | "dark") picks the colours from ``chrome.PALETTE``
    (background ``--bg``, text ``--fg``, status ``--fg-secondary``, bar track
    ``--border``); the brand gradients stay.
    """
    import base64

    pal = chrome.PALETTE.get(theme) or chrome.PALETTE["dark"]
    bg, fg, muted, track = pal["bg"], pal["text"], pal["fg_secondary"], pal["border"]

    try:
        from the_one.interfaces.web.app import STATIC_DIR  # lazy — safe post web.app import

        logo_path = STATIC_DIR / "brand" / "gleepglorp_med.png"
        logo_b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        logo_src = f"data:image/png;base64,{logo_b64}"
    except Exception:
        log.warning(
            "splash: could not load brand logo — falling back to text-only splash", exc_info=True
        )
        return _splash_text_only(theme)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: 100%; height: 100%;
    background: {bg};
    display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: {fg};
    user-select: none;
    -webkit-app-region: drag;
  }}
  .splash {{
    display: flex; flex-direction: column;
    align-items: center; gap: 18px;
  }}
  .logo img {{
    width: 240px;
    height: auto;
    display: block;
  }}
  .name {{
    font-size: 18px; font-weight: 600;
    letter-spacing: 0.02em;
    color: {fg};
  }}
  .status {{
    font-size: 12px; color: {muted};
    letter-spacing: 0.05em;
  }}
  .bar {{
    width: 120px; height: 2px;
    background: {track};
    border-radius: 1px;
    overflow: hidden;
  }}
  .bar-fill {{
    height: 100%;
    background: linear-gradient(90deg, #6c63ff, #4e46e5);
    border-radius: 1px;
    animation: slide 1.4s ease-in-out infinite;
  }}
  @keyframes slide {{
    0%   {{ transform: translateX(-100%); }}
    50%  {{ transform: translateX(0); }}
    100% {{ transform: translateX(100%); }}
  }}
</style>
</head>
<body>
  <div class="splash">
    <div class="logo"><img src="{logo_src}" alt="GleepGlorp AI"></div>
    <div class="bar"><div class="bar-fill"></div></div>
    <div class="status">starting…</div>
  </div>
</body>
</html>
"""


def _wait_until_serving(host: str, port: int, timeout: float = 15.0) -> None:
    """Poll /api/live until the app actually serves (lifespan startup done).

    This is a pure readiness probe for the shell's OWN just-started server —
    it asks only "did it come up," never "is this credentialed content
    correct." `/api/live` is the unauthenticated liveness endpoint (DD5's
    exemption exists precisely for probes like this one); using the
    credentialed `/api/info` here would be pointless work; the credential is
    for `_select_port`'s ownership question and the window-focus POST, not
    this one.
    """
    deadline = time.monotonic() + timeout
    url = f"http://{host}:{port}/api/live"
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


def _webview_available() -> bool:
    """Probe whether a WebView backend is available without initializing the GUI stack.

    Returns True on win32/darwin (WebView2 / WKWebView assumed present).
    On Linux, probes the gi typelib via gi.require_version WITHOUT importing
    Gtk/WebKit2 (importing can init GLib / touch a display / hang on headless).
    Catches ImportError (no gi) and ValueError (typelib absent).
    """
    if state.policy.webview_assumed_present:
        return True  # WebView2 (Win) / WKWebView (mac) assumed present
    if not desktop_host.host_has_desktop_gtk():
        return False  # same predicate `the-one doctor` uses
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


class _NoTrayError(Exception):
    """Internal control flow: the tray decision was "no tray"."""


_NO_WEBVIEW_BODIES = {
    "webkit": (
        "GleepGlorp AI opened in your browser because WebKitGTK isn't installed. "
        "Install gir1.2-webkit2-4.1 for its own window."
    ),
    "gtk": (
        "GleepGlorp AI opened in your browser because this desktop has no GTK 3 window libraries."
    ),
    "gi": "GleepGlorp AI opened in your browser because PyGObject (gi) isn't available.",
}


def _no_webview_body() -> str:
    piece = desktop_host.missing_desktop_piece() or "webkit"
    return _NO_WEBVIEW_BODIES[piece]


class DesktopSession:
    """Owns the per-launch window/tray/quit lifecycle for the desktop app.

    All per-launch state (tray icon reference) lives here.  The window reference
    and quit flag live on ``session_state.state`` so that
    ``window_control.focus_window()`` (module-level) and the test suite (which
    sets ``session_state.state`` directly) share one copy — see M32 F3 DD1.
    """

    def __init__(self) -> None:
        self._icon = None  # pystray icon reference (only this session owns it)
        self._window = None  # pywebview Window — set in run() after create_window

    # ── geometry helper ───────────────────────────────────────────────────────

    def _save_current_geometry(self, window) -> None:
        """Capture and persist window geometry — best-effort, never blocks.

        On GTK this is GTK-main-thread-only (inside ``closing``): pywebview's
        ``window.width/x`` go through ``glib.idle_add`` plus a blocking
        semaphore, which deadlocks on the main thread, so the native
        ``Gtk.Window`` is read directly (``get_size`` is the measure
        ``Gtk.Window.resize`` restores). On Wayland only the size is saved.
        Known wart: on a multi-monitor X11 layout whose monitor 0 is not at
        (0,0), pywebview's ``move()`` adds that origin, so position can be off.

        Elsewhere: skip until ``shown`` has fired (reading before blocks up to
        15 s), and read ``window.width/height/x/y`` in a broad try/except.
        """
        if window is None or not window.events.shown.is_set():
            return
        if window_control._is_gtk_backend():
            if threading.current_thread() is not threading.main_thread():
                log.warning("window_state: GTK geometry save off the main thread — skipped")
                return
            native = getattr(window, "native", None)
            if native is None:
                log.debug("window_state: no native window — skipped")
                return
            try:
                w, h = native.get_size()
                if window_control._on_wayland(window):
                    x = y = None
                else:
                    x, y = native.get_position()
            except Exception:
                log.warning("window_state: capture failed", exc_info=True)
                return
        else:
            try:
                w, h, x, y = window.width, window.height, window.x, window.y
            except Exception:
                log.warning("window_state: capture failed", exc_info=True)
                return
        try:
            window_state_store.save_state(w, h, x, y)
            log.debug("window_state: saved geometry %sx%s @ %s,%s", w, h, x, y)
        except Exception:
            log.warning("window_state: capture failed", exc_info=True)

    # ── lifecycle callbacks ───────────────────────────────────────────────────

    def _close_to_tray(self) -> bool:
        """Close-to-tray body — called by ``_on_closing`` when the tray runs.

        Show the first-run notice (once), hide the window. Returns ``True``
        when the hide succeeded (caller cancels the destroy), ``False`` when
        there is no tray icon, no window, or ``hide()`` raised (caller allows
        the destroy: a deterministic exit rather than a swallow into the event
        handler wrapper).

        This method does NOT guard ``really_quit`` — ``_on_closing`` does.
        """
        if self._icon is None:
            return False  # nothing to hide into; _on_closing never gets here

        if not notice.notice_shown():
            notice.mark_notice_shown()
            tray.notify(
                self._icon,
                _TRAY_NOTICE_BODY,
                _TRAY_NOTICE_TITLE,
            )

        if state.desktop_window is not None:
            try:
                state.desktop_window.hide()
            except Exception:
                return False
            window_control._mark_hidden()
        return True

    def _on_closing(self) -> bool:
        """pywebview closing handler.

        Returns False (cancel the destroy) when the window was hidden, True
        (allow it) otherwise:

        - ``really_quit``: allow (the Quit callback asked for the destroy).
        - tray running (``self._icon``): hide to tray.
        - ``tray_mode == "none"``: hide through ``window_control._no_tray_hide`` (the app
          stays running; a relaunch or ``the-one quit`` reaches it).
        - ``tray_mode == "dock"`` (macOS, M32 F3): ``macos_dock.on_close`` decides; a close
          hides the window (the app stays in the Dock, no notice), a failed hide allows.
        - anything else (``failed``, None: no tray decided yet, or a non-Linux
          path with no tray): allow the destroy.

        pywebview's Event.set() swallows handler exceptions, so a raise here
        would lose the cancel value and destroy the window; the hide calls are
        wrapped and a failure allows the destroy deterministically.
        """
        window = state.desktop_window or self._window
        # Capture geometry before any hide/destroy (best-effort).
        self._save_current_geometry(window)

        if state.really_quit:
            chrome.deregister()
            return True  # Quit callback already requested real destroy

        if state.tray_mode == "dock":
            hidden = self._dock_hide(window)
        elif self._icon is not None:
            hidden = self._close_to_tray()
        elif state.tray_mode == "none":
            hidden = window_control._no_tray_hide(window)
        else:
            hidden = False
        if not hidden:
            chrome.deregister()  # allowing the destroy
        return not hidden  # True → allow destroy; False → cancel

    def _dock_hide(self, window) -> bool:
        """Dock-mode close: hide when ``on_close`` says so. True when hidden."""
        view = macos_dock.snapshot(state, native_window=window is not None)
        if macos_dock.on_close(view) != "hide" or window is None:
            return False
        try:
            window.hide()
        except Exception:
            log.warning("dock: hide on close raised — allowing the destroy", exc_info=True)
            return False
        log.info("dock: window hidden on close")
        return True

    def _drain(self, server, thread) -> None:
        """Drain the session's server (the terminate worker's ``drain``)."""
        _graceful_shutdown(server, thread)

    def _path_s_begin(self) -> None:
        """Path S, before the drain: the loop stopped without ``applicationShouldTerminate:``."""
        log.info("path S: webview.start returned — draining")
        state.loop_stopped = True
        saved = state.begin_quit()  # also makes a still-running _boot stop
        window = state.desktop_window or self._window
        if window is not None:
            macos_dock.order_out(window)
        if saved is not None:
            self._save_current_geometry(saved)

    def _path_s_exit(self) -> None:
        """Path S, after the drain: bounded wait on the boot, flush, hard exit.

        pywebview starts ``_boot`` on a non-daemon thread that can be stuck in
        ``create_window`` after the loop stopped, which would keep the process alive.
        """
        if not state.boot_stopped.wait(macos_dock.BOOT_WAIT_BOUND):
            log.warning("path S: boot did not stop within %.1fs", macos_dock.BOOT_WAIT_BOUND)
        log.info("path S: exiting (os._exit(0))")
        macos_dock.flush_log_handlers()
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:
                pass
        os._exit(0)

    def _on_show(self, icon) -> None:
        """Tray "Show" menu callback: show the window.

        The window was hidden via close-to-tray (not minimized), so
        show() is sufficient.  restore() is intentionally omitted here —
        it snapped the window size on each show when the window was merely
        hidden.  focus_window() keeps show()+restore() for the
        single-instance-focus path where the window may be minimized.
        """
        if state.desktop_window is not None:
            window_control._show_window(state.desktop_window)

    def _on_quit(self, icon) -> None:
        """Tray "Quit" menu callback: graceful full exit.

        Order: set really-quit flag → stop tray (MUST complete —
        run_detached() spawns a non-daemon thread; skipping stop() leaves
        it alive and hangs the process after _graceful_shutdown) →
        destroy window (causes webview.start() to return) → the existing
        `finally: _graceful_shutdown(server, thread)` drains the server.
        """
        state.really_quit = True  # tell _on_closing to allow destroy
        chrome.deregister()  # a request racing the destroy applies nothing

        # icon.stop() MUST run; guard so it survives even if destroy raises.
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                log.warning("pystray icon.stop() raised during Quit — ignored", exc_info=True)

        if state.desktop_window is not None:
            # Capture geometry before destroy (redundant-but-safe per edge-case
            # note in leg spec: closing fires on destroy in pywebview-5.4 for all
            # known backends, so _on_closing already ran; this second write is
            # idempotent forward-safety for any future backend that skips it).
            if not window_control._is_gtk_backend():  # on GTK, closing saves it (main thread)
                self._save_current_geometry(state.desktop_window)
            state.desktop_window.destroy()

    # ── main run sequence ─────────────────────────────────────────────────────

    def run(self) -> None:
        """Execute the full desktop launch sequence.

        Splash-screen restructure (M15 F7 Leg 4 — DD4 two-window model):
        1. Create a small branded splash window BEFORE webview.start().
        2. Pass _boot to webview.start() so it runs after the GUI loop is up.
        3. _boot runs on a background thread: waits for the server, creates the
           main window, wires the tray and closing handler, then registers the
           main window's `loaded` event to destroy the splash.
        4. Splash teardown is idempotent (threading.Event guard) and the error
           path destroys both windows so the GUI loop always returns cleanly.
        """
        # Reset process-local state on each launch (e.g. if run_desktop() is called
        # more than once in tests after a reload).
        state.reset()
        # Bound once, right after the reset: the _boot thread and its closures use this
        # binding, so there is no first-read race and no mid-run flip.
        policy = state.policy
        state.session = self
        if policy.initial_tray_mode is not None:
            # Dock mode (M32 F3 DD2, macOS): set BEFORE webview.start so no tray_mode=None
            # gap lets _on_closing allow a destroy; pystray is never imported there.
            state.tray_mode = policy.initial_tray_mode
        chrome.reset()

        host, port = settings.host, settings.port
        sel_port, is_ours = takeover._select_port(host, port)
        if is_ours:
            # A the-one that shares our credential already owns this port: focus
            # it, or, when it is an older version, replace it (DD13). Header-less
            # loopback POSTs (no Origin) clear the OriginAllowlistMiddleware; the
            # Authorization header carries the credential the gate requires.
            sel_port, is_ours = takeover._takeover(host, sel_port)
        if is_ours:
            state.session = None  # a window-only client owns nothing: not a desktop session
            return
        # M21 F01 L02: `_select_port`'s fallback branch (Case C — the
        # configured port is occupied by a foreign process) resolves a
        # DIFFERENT port than `settings.port`, but until this leg nothing
        # ever wrote it back — the self-configuration surface builds its
        # loopback URL from `settings.port` (`self_configuration.manage.
        # surface_url`), so a stale value there would strand every surface
        # row's URL at the configured-but-unbound port. `settings.port` is
        # mutable and the real serving port is known here, before uvicorn
        # is constructed — only on THIS branch, which is about to start its
        # own lifespan (the `is_ours=True` branch above already returned
        # without ever running one).
        settings.port = sel_port
        # A quit from here on is recorded for _boot (or the browser branch) to
        # honour; cleared on every exit path (see ``clear_booting``).
        state.begin_boot()
        # DD7: prime the login-shell PATH (frozen macOS only; a no-op elsewhere, up to 5 s
        # on macOS). After begin_boot, so a quit arriving during the probe finds the guard.
        platform_env.prime_login_shell_path()
        # Base URL only — deliberately WITHOUT a handoff credential yet (DD7,
        # DD12). The token is single-use and short-lived, so it is minted
        # separately, close to each navigation call site below (inside
        # `_boot()` for the webview path, right before `webbrowser.open()`
        # for the fallback path) — not here, before the long
        # webview.start()/splash/`_wait_until_serving` sequence, which would
        # burn TTL for no reason and could even let the token expire before
        # the window ever navigates. `is_ours=True` already returned above
        # without reaching this line, so nothing here ever mints for that
        # branch.
        base_url = f"http://{host}:{sel_port}/"
        server = None
        thread = None
        path_s = False
        # is_ours=True already returned above; reaching here means is_ours=False —
        # we always start our own server on the selected port.
        from the_one.interfaces.web.app import app

        server = uvicorn.Server(uvicorn.Config(app, host=host, port=sel_port, log_level="info"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        state.server, state.thread = server, thread
        try:
            if _webview_available():
                try:
                    import webview  # lazy: optional [gui] extra; off chat/version
                except ImportError as exc:
                    state.clear_booting()
                    raise SystemExit(
                        "pywebview is not installed. "
                        "Install the desktop extra: pip install 'the-one[gui]'"
                    ) from exc

                # ── Window-state restore (pre-compute before _boot so _boot is
                #    a plain closure with no GUI-thread work) ──────────────────
                from the_one.interfaces.desktop.window_state import (
                    MIN_SIZE,
                    apply_floor,
                    clamp_to_bounds,
                    first_launch_size,
                    load_state,
                )

                # ── Launch theme (M25 F5 L2): the persisted theme, else the OS app
                #    theme (dark off Windows). Colours the splash and the main
                #    window's first frame; the page's first post corrects a wrong
                #    guess. ───────────────────────────────────────────────────
                chrome.enable(settings.data_dir)
                launch_theme = chrome.load_theme(settings.data_dir) or chrome.os_theme()
                launch_bg = chrome.PALETTE[launch_theme]["bg"]

                _saved_state = load_state()
                _create_kwargs: dict = {
                    "frameless": False,
                    "resizable": True,
                    "background_color": launch_bg,
                    # Created hidden, tinted, then shown (first-paint order).
                    "hidden": True,
                    "min_size": MIN_SIZE,
                    # pywebview defaults text_select=False, which injects
                    # `body { user-select: none }` and blocks copying a reply.
                    "text_select": True,
                }

                def _resolve_screens() -> list:
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
                            _screens = _screens()  # callable form
                    return _screens

                if _saved_state is None:
                    # First launch: width and height only (no x/y, so WinForms'
                    # CenterScreen places the window).
                    try:
                        _fw, _fh = first_launch_size(
                            _resolve_screens(), policy.first_launch_platform
                        )
                        _create_kwargs["width"] = _fw
                        _create_kwargs["height"] = _fh
                    except Exception:
                        log.warning("window_state: sizing failed; using defaults", exc_info=True)
                else:
                    try:
                        _clamped = clamp_to_bounds(apply_floor(_saved_state), _resolve_screens())
                        _create_kwargs["width"] = _clamped["width"]
                        _create_kwargs["height"] = _clamped["height"]
                        if "x" in _clamped:
                            _create_kwargs["x"] = _clamped["x"]
                        if "y" in _clamped:
                            _create_kwargs["y"] = _clamped["y"]
                    except Exception:
                        log.warning("window_state: restore failed; using defaults", exc_info=True)
                # ── / Window-state restore ───────────────────────────────────

                # ── Splash setup ─────────────────────────────────────────────
                # Create the splash BEFORE start() — it becomes visible once the
                # GUI loop is running (inside start()).  The server isn't up yet so
                # the splash content must be self-contained (no localhost URL).
                splash = webview.create_window(
                    "GleepGlorp AI — starting",
                    html=_splash_html(launch_theme),
                    frameless=True,
                    width=400,
                    height=300,
                    background_color=launch_bg,
                )

                if policy.splash_border:
                    # before_show is a locked event: it runs on the UI thread inside
                    # create(), before the first Show. The parameter must be named
                    # `window` for pywebview to pass the window.
                    def _splash_border(window) -> None:
                        chrome.apply_splash_border(window, launch_theme)

                    splash.events.before_show += _splash_border

                # Idempotent splash teardown: a threading.Event guards against a
                # double-fire from the `loaded` handler racing the error path.
                # (The loaded handler runs on a daemon thread; a plain bool flag
                # has a TOCTOU window.)
                _splash_closed = threading.Event()
                # Set once the main window is visible: the splash stays until then
                # (a hidden window can finish loading before show()).
                _main_shown = threading.Event()

                # macOS: destroying the splash while a terminate drains (or after the loop
                # stopped, or after a failed boot) would run its windowWillClose_, which
                # empties BrowserView.instances and stops the loop mid-drain.
                _boot_errored = threading.Event()

                def _splash_blocked() -> bool:
                    return policy.splash_blocked_in_quit_states and (
                        state.terminate_pending
                        or state.really_quit
                        or state.loop_stopped
                        or _boot_errored.is_set()
                    )

                def _destroy_splash() -> None:
                    """Destroy the splash window — idempotent (safe to call twice)."""
                    if _splash_closed.is_set() or _splash_blocked():
                        return
                    _splash_closed.set()
                    try:
                        splash.destroy()
                    except Exception:
                        log.debug("splash.destroy() raised (already gone)", exc_info=True)

                # ── / Splash setup ───────────────────────────────────────────

                def _boot() -> None:
                    """Boot sequence — runs on a background thread after the GUI loop starts.

                    pywebview calls this as _boot() with NO arguments — it must take
                    no parameters.  The splash window is accessed via the enclosing-scope
                    ``splash`` closure variable (same as ``_destroy_splash`` already does).

                    Order (per DD4 design review):
                    1. splash.events.shown.wait() — so teardown is always safe even if
                       _wait_until_serving returns instantly.
                    2. _wait_until_serving — poll until uvicorn is up.
                    3. create_window for the main UI with F6 state-restore (native frame).
                    4. Register main.events.loaded → destroy splash IMMEDIATELY after
                       create_window, before tray wiring, to close the race where the
                       main window finishes loading during tray setup and the loaded event
                       fires before the handler is registered.
                    4a. Backstop: if main_win.events.loaded is already set (load completed
                        before the subscribe), call _destroy_splash() immediately.
                        pywebview 5.4 Event exposes is_set() — verified against pinned source.
                    5. Wire tray + closing handler.
                    6. Set state.desktop_window / self._window.
                    """
                    main_win = None

                    def _abort_if_quit() -> bool:
                        """Honour a quit that arrived while booting (DD4).

                        Releases the loaded handler, destroys the main window (if
                        created) and the splash. On GTK a window created inside the
                        running loop is already mapped, so a quit after creation
                        flashes it briefly (accepted).
                        """
                        if not state.quit_was_requested():
                            return False
                        _main_shown.set()
                        if policy.quit_in_boot_stops_without_destroy:
                            # DD3: stop without publishing; the terminate path (or path S)
                            # owns the exit. Never terminate_/destroy from here.
                            return True
                        state.really_quit = True  # the destroy below must not be cancelled
                        if main_win is not None:
                            chrome.deregister()
                            try:
                                main_win.destroy()
                            except Exception:
                                log.debug("main_win.destroy() raised on quit", exc_info=True)
                        _destroy_splash()
                        return True

                    try:
                        # Step 1 — ensure splash is shown before any teardown attempt.
                        splash.events.shown.wait(15)
                        if _abort_if_quit():
                            return

                        # Step 2 — wait for the app server.
                        _wait_until_serving(host, sel_port)
                        if _abort_if_quit():
                            return

                        # Step 3 — create the main window (native frame: frameless=False).
                        # Mint the one-time browser-handoff credential HERE, right before
                        # navigation, not earlier in the boot sequence (DD7, DD12): it is
                        # single-use and short-lived, and the launcher shares a process
                        # with the server, so the in-process mint (no IPC, no HTTP hop) is
                        # the pinned call `mint_handoff_credential()` exists for — see
                        # `the_one/interfaces/web/handoff_store.py`. Without this, the
                        # window's first navigation carries no credential at all and
                        # `CredentialGateMiddleware` refuses it with a 401 instead of
                        # rendering the app. Lazy import: keeps the module importable
                        # without the web app wired in (mirrors the other lazy imports in
                        # this function).
                        from the_one.interfaces.web.handoff_store import (
                            HANDOFF_QUERY_PARAM,
                            mint_handoff_credential,
                        )

                        handoff_token = mint_handoff_credential()
                        url = f"{base_url}?{HANDOFF_QUERY_PARAM}={handoff_token}"
                        main_win = webview.create_window("GleepGlorp AI", url, **_create_kwargs)
                        self._window = main_win
                        # Registered right after creation, before the tray decision:
                        # with ``tray_mode`` still None the handler allows the
                        # destroy, so an X-button press during the tray probes never
                        # meets an unregistered window. It saves geometry in every mode.
                        main_win.events.closing += self._on_closing

                        # Step 4 — register the loaded→destroy handler BEFORE register and
                        # show so a fast localhost load still dismisses the splash. The
                        # handler runs on its own thread and waits for the main window to
                        # be visible first (no gap with nothing on screen).
                        main_win.events.loaded += lambda: (
                            _main_shown.wait(25),
                            _destroy_splash(),
                        )

                        # Step 4b — tint the (still hidden) window, then show it.
                        if _abort_if_quit():
                            return
                        chrome.register(main_win, launch_theme)
                        if policy.wait_for_page_before_show:
                            # An unpainted main window ordered in front of the splash shows
                            # a dark empty body (HAT P1): keep it hidden until its page has
                            # loaded, so the splash stays visible meanwhile. Bounded.
                            t0 = time.monotonic()
                            loaded_in_time = False
                            while True:
                                if main_win.events.loaded.is_set():
                                    loaded_in_time = True
                                    break
                                if state.quit_was_requested():
                                    break
                                if time.monotonic() - t0 >= MAIN_LOADED_BOUND:
                                    break
                                time.sleep(0.05)
                            if _abort_if_quit():
                                return
                            if loaded_in_time:
                                log.info(
                                    "macos: main window shown after page load (%.1fs)",
                                    time.monotonic() - t0,
                                )
                            else:
                                log.info(
                                    "macos: main window shown after the %gs fallback"
                                    " (page not loaded)",
                                    MAIN_LOADED_BOUND,
                                )
                        try:
                            window_control._show_window(main_win)
                        except Exception:
                            if not policy.native_show_fallback:
                                log.exception("main window show() raised")
                                raise
                            log.warning(
                                "main window show() raised — native show fallback",
                                exc_info=True,
                            )
                            chrome.native_show(main_win)  # raises when it fails too
                            window_control._mark_visible()
                        _main_shown.set()

                        # Step 4a — backstop (on this thread, so it must not wait): if
                        # loaded already fired, dismiss the splash now that the window
                        # is visible.
                        # pywebview 5.4 Event.is_set() delegates to threading.Event.is_set().
                        if main_win.events.loaded.is_set():
                            _destroy_splash()

                        # Step 5 — tray wiring.
                        # Degrades gracefully: if tray can't start, skip _on_closing
                        # registration (F4 fallback — X destroys the window directly).
                        # On Linux the tray is decided first (M32 F2 L02): with no
                        # StatusNotifier host / X11 tray, pystray is never imported
                        # and the tray is not started (close keeps the F4 exit
                        # behaviour until the no-tray hide lands, leg 5).
                        try:
                            tray_backend = None
                            if policy.tray.skip:
                                raise _NoTrayError  # dock mode: no tray, pystray not imported
                            if policy.tray.detect:
                                tray_backend = desktop_host.choose_pystray_backend()
                                mode, reason = desktop_host.detect_tray(tray_backend)
                                if mode in ("none", "unavailable"):
                                    state.tray_mode = "none"
                                    log.info(
                                        "No system tray (%s: %s); tray not started", mode, reason
                                    )
                                    raise _NoTrayError
                            if tray_backend is not None:
                                self._icon = tray.build_tray(
                                    on_show=self._on_show,
                                    on_quit=self._on_quit,
                                    backend=tray_backend,
                                )
                            else:
                                self._icon = tray.build_tray(
                                    on_show=self._on_show, on_quit=self._on_quit
                                )
                            self._icon.run_detached()
                            if policy.tray.records_tray_mode:
                                state.tray_mode = mode
                        except _NoTrayError:
                            pass
                        except Exception:
                            if policy.tray.records_tray_mode:
                                state.tray_mode = "failed"
                            log.warning(
                                "System tray unavailable — close button will exit the app"
                                " (F4 fallback)",
                                exc_info=True,
                            )

                        # Step 6 — publish the window, clear ``booting`` and read
                        # ``quit_requested`` in ONE critical section, so a quit
                        # arriving at any moment is either seen here or finds the
                        # published window. ``_on_quit`` runs after the lock is released.
                        quit_now = state.publish_window(main_win)
                        self._window = main_win
                        if quit_now and policy.publish_quit_left_to_terminate:
                            _main_shown.set()  # the terminate path owns the exit
                        elif quit_now:
                            # The window may be destroyed before its ``loaded`` fires,
                            # which would leave the splash (and webview.start) alive.
                            self._on_quit(self._icon)
                            _main_shown.set()
                            _destroy_splash()

                    except Exception:
                        log.exception("_boot raised — tearing down to prevent orphaned splash")
                        state.clear_booting()
                        _main_shown.set()  # release a waiting loaded handler
                        if policy.boot_error_terminates:
                            # No destroy (it would stop the loop mid-boot); one terminate_
                            # lets the delegate drain the server, unless one is pending.
                            _boot_errored.set()
                            if not state.terminate_pending:
                                try:
                                    macos_dock.terminate_app()
                                except Exception:
                                    log.warning("boot error: terminate_ failed", exc_info=True)
                            raise
                        _destroy_splash()
                        if main_win is not None:
                            chrome.deregister()
                            try:
                                main_win.destroy()
                            except Exception:
                                log.debug("main_win.destroy() raised in error path", exc_info=True)
                        raise
                    finally:
                        state.boot_stopped.set()  # DD3: every exit, for the terminate worker

                # Persist localStorage/cookies (e.g. the theme preference) across app
                # restarts AND reinstalls. pywebview defaults to private_mode=True — an
                # ephemeral profile that drops all web storage between launches, so a
                # localStorage-backed setting like the theme resets every restart. Point
                # the webview at a stable per-user profile dir under data_dir (outside the
                # install dir, and migrated with the rest of the user's data) so settings
                # survive. (M15 F5 post-landing fix: theme didn't survive restart/reinstall.)
                storage_dir = settings.data_dir / "webview"
                storage_dir.mkdir(parents=True, exist_ok=True)
                if policy.installs_dock:
                    macos_dock.install(self)
                webview.start(  # blocks until all windows closed (or Quit → destroy)
                    _boot,
                    private_mode=False,
                    storage_path=str(storage_dir),
                )
                if policy.runs_path_s:
                    path_s = True
                    self._path_s_begin()
            else:
                # Browser-fallback path: no pywebview, no splash.  Keep the
                # _wait_until_serving call here (it moved into _boot for the webview
                # path, so it must remain explicitly on this branch — otherwise the
                # browser would open before the server is ready).
                # A quit recorded while booting wins; otherwise a later quit finds
                # ``state.browser_server`` and asks the server to drain.
                if not state.claim_browser_server(server):
                    return
                try:
                    _wait_until_serving(host, sel_port)
                except RuntimeError:
                    if server.should_exit is True:  # a quit arrived during the wait
                        return
                    raise
                if server.should_exit is True:
                    return
                # Same handoff-minting treatment as the webview path above (DD7,
                # DD12): mint right before navigation, not earlier. Lazy import
                # for the same reason as the webview branch's import.
                from the_one.interfaces.web.handoff_store import (
                    HANDOFF_QUERY_PARAM,
                    mint_handoff_credential,
                )

                handoff_token = mint_handoff_credential()
                url = f"{base_url}?{HANDOFF_QUERY_PARAM}={handoff_token}"
                if policy.browser_fallback_notification:
                    desktop_host.send_notification("GleepGlorp AI", _no_webview_body())
                webbrowser.open(url)
                if server is not None:
                    # Main thread is free (no GUI loop) — install a SIGINT handler
                    # that triggers the uvicorn shutdown, then join to let the
                    # lifespan drain complete (mirrors DD2's window-close path).
                    signal.signal(signal.SIGINT, lambda *_: setattr(server, "should_exit", True))
                    thread.join()  # blocks until SIGINT → should_exit → drain
                # case (b)+no-backend: nothing to block on; just return
        finally:
            state.clear_booting()
            state.release_browser_server()
            _graceful_shutdown(server, thread)  # no-op when server is None (case b)
            state.server = state.thread = None
            if state.session is self:
                state.session = None
        if path_s:
            self._path_s_exit()


def run_desktop() -> None:
    # M15 F6 review-fix: defensive second call (idempotent).  Covers any entry
    # path that doesn't go through frozen_entry_gui.py (e.g. a future launcher
    # script or test harness that calls run_desktop() directly).  The primary
    # call is in packaging/windows/frozen_entry_gui.py before cli_entry().
    from the_one.platform.env import ensure_stdio_streams  # noqa: PLC0415

    ensure_stdio_streams()
    DesktopSession().run()
