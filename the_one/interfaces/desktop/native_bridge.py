"""Remove pywebview's native message handlers from the main window (Mission 35, F2 L8, DD13).

pywebview registers a script message handler on the main web view at construction
(``jsBridge`` on GTK and Cocoa, plus ``browserDelegate`` on Cocoa). A sandboxed
widget frame (``App.ui.widgetFrame``) can reach those through
``window.webkit.messageHandlers`` on WebKit, so the shell removes them once the page
has loaded. The-one uses nothing that travels over them: no ``js_api``, ``expose``,
``evaluate_js`` callback, ``window.dom`` event or ``alert`` (a guard test pins this).

``remove_native_handlers(window)`` returns ``"removed"``, ``"not-applicable"`` (Windows
and other backends: WebView2 has its own ``chrome.webview`` and is probed, not changed)
or ``"failed"`` and never raises. ``"removed"`` means the removal job ran on the UI
thread: the caller waits (bounded) for it. The result is stored in
``state.native_bridge`` for ``GET /api/window/state``.

The backend modules are imported lazily inside the seams, so this module imports on
every OS (the base install is GTK-free).
"""

from __future__ import annotations

import logging
import sys
import threading

from the_one.interfaces.desktop import macos_dock
from the_one.interfaces.desktop.session_state import state

log = logging.getLogger("the_one.interfaces.desktop.shell")

#: How long the caller waits for the UI-thread job (seconds).
JOB_BOUND = 2.0

GTK_HANDLERS = ("jsBridge",)
COCOA_HANDLERS = ("jsBridge", "browserDelegate")


def _backend() -> str:
    """``"gtk"``, ``"cocoa"`` or ``"other"``, read at call time."""
    if getattr(sys.modules.get("webview"), "renderer", None) == "gtkwebkit2":
        return "gtk"
    if sys.platform == "darwin":
        return "cocoa"
    return "other"


def _gtk_hop(job) -> None:
    """Run ``job()`` on the GTK main thread (``glib.idle_add``)."""
    if threading.current_thread() is threading.main_thread():
        job()
        return
    from webview.platforms import gtk as _gtkmod

    def _once():
        job()
        return False

    _gtkmod.glib.idle_add(_once)


def _gtk_remove(window) -> None:
    from webview.platforms import gtk as _gtkmod

    manager = _gtkmod.BrowserView.instances[window.uid].manager
    for name in GTK_HANDLERS:
        manager.unregister_script_message_handler(name)


def _cocoa_remove(window) -> None:
    from webview.platforms import cocoa as _cocoamod

    view = _cocoamod.BrowserView.instances[window.uid].webview
    controller = view.configuration().userContentController()
    for name in COCOA_HANDLERS:
        controller.removeScriptMessageHandlerForName_(name)


def _remove_on_ui_thread(backend: str, window) -> str:
    """Hop to the backend's UI thread, run the removal there, wait for it."""
    done = threading.Event()
    errors: list[BaseException] = []

    def _job():
        try:
            if backend == "gtk":
                _gtk_remove(window)
            else:
                _cocoa_remove(window)
        except BaseException as exc:  # noqa: BLE001 - reported, never raised into the shell
            errors.append(exc)
        finally:
            done.set()

    if backend == "gtk":
        _gtk_hop(_job)
    else:
        macos_dock._call_after(_job)
    if not done.wait(JOB_BOUND):
        log.error("native bridge removal did not run within %.1fs", JOB_BOUND)
        return "failed"
    if errors:
        log.error("native bridge removal raised: %r", errors[0], exc_info=errors[0])
        return "failed"
    return "removed"


def remove_native_handlers(window) -> str:
    """Remove the native message handlers once; store and return the outcome."""
    if state.native_bridge == "removed":
        return "removed"  # idempotent: pywebview registers them only in the constructor
    try:
        backend = _backend()
        if backend == "other":
            result = "not-applicable"
        else:
            result = _remove_on_ui_thread(backend, window)
    except Exception:
        log.error("native bridge removal failed", exc_info=True)
        result = "failed"
    state.native_bridge = result
    return result
