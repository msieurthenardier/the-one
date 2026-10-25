"""Window control for the desktop session: show, focus, visibility and quit.

Mission 32, Flight 3, DD1: moved out of ``shell.py``. These are the helpers the
HTTP window routes (``/api/window/*``) and the close handlers call. Lifecycle
flags live on ``session_state.state``; the logger keeps the shell's name so every
log line is unchanged. This module never imports ``shell``.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

from the_one import __version__
from the_one.interfaces.desktop import chrome, macos_dock, notice
from the_one.interfaces.desktop import host as desktop_host
from the_one.interfaces.desktop.session_state import state

log = logging.getLogger("the_one.interfaces.desktop.shell")

# The one-time notice for a close with no tray to go back to.
# Short on purpose: GNOME's banner truncates long text with an ellipsis.
_NO_TRAY_NOTICE_SUMMARY = "GleepGlorp AI is still running"
_NO_TRAY_NOTICE_BODY = "Open it again to show it, or right-click its icon to quit."


def _is_gtk_backend() -> bool:
    """True when pywebview runs its GTK/WebKit2 backend (read at call time).

    ``webview.start()`` sets ``renderer`` before the first window is created.
    Never ``from webview import renderer`` (a stale copy).
    """
    return getattr(sys.modules.get("webview"), "renderer", None) == "gtkwebkit2"


def _on_wayland(window) -> bool:
    """True when the window's GDK display is Wayland (falls back to the host probe)."""
    try:
        return "Wayland" in type(window.native.get_display()).__name__
    except Exception:
        return desktop_host.display_session() == "wayland"


def _mark_visible() -> None:
    state.tracked_visible = True


def _show_window(window, *, restore: bool = False) -> None:
    """Map and raise the main window.

    On GTK, ``BrowserView.show()`` re-hides a window whose ``hidden`` flag is
    still set (creation-time ``hidden=True``) when ``main_level() == 0``, so the
    flag is cleared first and ``restore()`` (deiconify + present) maps it.
    Elsewhere: ``show()``, plus ``restore()`` only when asked.
    """
    if _is_gtk_backend():
        window.hidden = False
        window.show()
        window.restore()
    else:
        window.show()
        if restore:
            window.restore()
    _mark_visible()


def _gtk_read(fn, timeout: float = 1.0):
    """Run ``fn()`` on the GTK main thread and return its value, or None on timeout."""
    if threading.current_thread() is threading.main_thread():
        return fn()
    from webview.platforms import gtk as _gtkmod

    done = threading.Event()
    box: list = []

    def _job():
        try:
            box.append(fn())
        except Exception:
            log.debug("gtk read raised", exc_info=True)
            box.append(None)
        finally:
            done.set()
        return False

    _gtkmod.glib.idle_add(_job)
    if not done.wait(timeout):
        log.warning("window state read timed out after %.1fs", timeout)
        return None
    return box[0]


def window_visible() -> bool | None:
    """Whether the main window is visible; None when unknown (no window / timeout)."""
    window = state.desktop_window
    if window is None:
        return None
    if sys.platform == "darwin":
        return macos_dock.native_visible(window)
    if not _is_gtk_backend():
        return state.tracked_visible
    try:
        return _gtk_read(lambda: bool(window.native.get_visible()))
    except Exception:
        log.warning("window_visible: read failed", exc_info=True)
        return None


def _window_mapped() -> bool | None:
    window = state.desktop_window
    if window is None or not _is_gtk_backend():
        return None
    try:
        return _gtk_read(lambda: bool(window.native.get_mapped()))
    except Exception:
        return None


def _mode() -> str | None:
    """The lifecycle mode: serve / quitting / window / booting / browser / None."""
    if state.session is None:
        return "serve"
    if state.really_quit:
        return "quitting"
    if state.desktop_window is not None:
        return "window"
    if state.booting:
        return "booting"
    if state.browser_server is not None:
        return "browser"
    return None


def window_state() -> dict:
    """The ``GET /api/window/state`` body. Never raises."""
    try:
        visible = window_visible()
        mapped = _window_mapped()
    except Exception:
        log.warning("window_state: read failed", exc_info=True)
        visible = mapped = None
    return {
        "desktop": state.desktop_window is not None,
        "mode": _mode(),
        "visible": visible,
        "mapped": mapped,
        "tray": state.tray_mode,
        "version": __version__,
        "pid": os.getpid(),
    }


def quit_desktop() -> str | None:
    """Quit the desktop session (``POST /api/window/quit``).

    Returns the state acted on: ``"window"`` (the session's quit ran),
    ``"booting"`` (a quit is recorded and ``_boot`` honours it at its next
    checkpoint), ``"browser"`` (the fallback server was told to drain), or
    None when there is nothing to quit (``serve`` mode). The state is chosen
    under ``state.lock`` (``SessionState.request_quit``); the blocking quit runs
    after the lock is released.
    """
    if sys.platform == "darwin" and state.loop_stopped:
        return "window"  # path S: the loop has stopped and the drain is under way
    tag, session = state.request_quit()
    if tag == "already":
        return "window"  # a quit is already under way; never destroy twice
    if sys.platform == "darwin" and tag in ("window", "booting"):
        # DD3 path T: one drain path. AppKit terminates on the main thread; the
        # delegate's applicationShouldTerminate: runs the drain worker.
        try:
            macos_dock.terminate_app()
            return tag
        except Exception:
            log.warning("quit_desktop: terminate_app raised", exc_info=True)
            return None
    if tag != "window":
        return tag  # "booting" / "browser" / None
    try:
        session._on_quit(session._icon)
        return tag
    except Exception:
        log.warning("quit_desktop: raised", exc_info=True)
        return None


def _gtk_activate(window, token: str) -> None:
    """Queue ONE GTK idle that raises ``window`` with an activation token.

    ``set_startup_id`` hands the token to GDK (X11 startup-notification, or
    ``xdg_activation_v1`` on Wayland) before the window is presented, so the
    compositor's focus-stealing prevention accepts the raise. It replaces a
    plain present: a present queued first could already be denied.
    """
    from webview.platforms import gtk as _gtkmod

    def _job():
        try:
            native = window.native
            native.set_startup_id(token)
            native.deiconify()
            native.present()
        except Exception:
            log.warning("focus_window: activation idle raised", exc_info=True)
        return False

    window.hidden = False
    _gtkmod.glib.idle_add(_job)


def focus_window(activation_token: str | None = None) -> bool:
    """Raise and restore the registered desktop window (thread-safe).

    ``activation_token`` is the launching desktop's ``XDG_ACTIVATION_TOKEN`` /
    ``DESKTOP_STARTUP_ID`` (opaque; never logged in full). On GTK with a token
    it is applied in a single idle (``_gtk_activate``); otherwise the plain
    show-and-restore path runs.

    Returns True when a window is registered and the raise succeeded. Returns
    False when no window is registered (e.g. serve mode) or the call raises
    (logged; never propagated into the HTTP handler).
    """
    if state.desktop_window is None:
        return False
    try:
        if sys.platform == "darwin":
            macos_dock.activate(state.desktop_window)
        elif activation_token and _is_gtk_backend():
            log.info("focus_window: activation token %s...", activation_token[:6])
            _gtk_activate(state.desktop_window, activation_token)
            _mark_visible()
        else:
            _show_window(state.desktop_window, restore=True)
        return True
    except Exception:
        log.warning("focus_window: show()/restore() raised", exc_info=True)
        return False


def set_window_theme(theme: str) -> dict:
    """Tell the shell the page's resolved theme (``POST /api/window/chrome``).

    Records and persists it (desktop session only) and tints the native title
    bar when a window is registered on Windows. Returns ``{"theme", "desktop",
    "tinted"}`` (``tinted`` is True, False or ``"pending"``). Never raises:
    failures are logged, as ``focus_window()`` does.
    """
    try:
        return chrome.request(theme)
    except Exception:
        log.warning("set_window_theme: raised", exc_info=True)
        return {"theme": theme, "desktop": False, "tinted": False}


def _no_tray_hide(window=None) -> bool:
    """Hide the window for a close with no tray (``state.tray_mode == "none"``).

    Hides, marks the tracked visibility False, then shows the one-time notice
    (its own marker, separate from the tray's). ``send_notification`` returns at
    once, so the GTK main thread never blocks (DD12). Returns False when there
    is no window or ``hide()`` raised (the caller then allows the destroy).
    """
    window = window or state.desktop_window
    if window is None:
        return False
    try:
        window.hide()
    except Exception:
        log.warning("no-tray hide failed — allowing the close", exc_info=True)
        return False
    state.tracked_visible = False
    try:
        if not notice.no_tray_notice_shown():
            notice.mark_no_tray_notice_shown()
            desktop_host.send_notification(_NO_TRAY_NOTICE_SUMMARY, _NO_TRAY_NOTICE_BODY)
    except Exception:
        log.debug("no-tray notice failed", exc_info=True)
    return True
