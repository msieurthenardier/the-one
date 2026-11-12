"""macOS dock mode: the pure decisions, the terminate worker and the AppKit seams.

Mission 32, Flight 3, leg 4 (DD2-DD5). On macOS there is no tray: closing the
window hides it, the Dock icon brings it back, and every quit reaches the server
drain. This module is split in three so that almost all of it is testable on
Linux with fakes:

- a **pure decision core** (``on_close``, ``on_reopen``, ``on_terminate`` over a
  ``DockView`` snapshot), importable on any OS;
- ``TerminateWorker``: DD3's steps (boot wait, drain, flush, reply) with every
  external effect injected;
- the **named AppKit seams** (``_call_after``, ``_nsapp``, ``_native_window``,
  ``terminate_app``, ``reply_to_terminate``, ``activate``, ``native_visible``).
  Each imports ``AppKit``/``PyObjCTools`` lazily inside the function, so nothing
  here imports ``objc`` on Linux or Windows; tests replace the seams.

``install`` (Phase B) replaces ``BrowserView.AppDelegate`` with a subclass whose
callbacks are the plain functions ``handle_terminate`` / ``handle_reopen`` below
(leg 3b: route ``subclass``, ``applicationShouldTerminate:`` keeps the inherited
``I@:@`` prototype, reopen takes the protocol's ``B@:@B``), and holds an App Nap
activity token at module level.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from the_one.interfaces.desktop import widget_records
from the_one.interfaces.desktop.session_state import state

log = logging.getLogger("the_one.interfaces.desktop.shell")

# ``applicationShouldTerminate:`` answers (NSApplicationTerminateReply).
NS_TERMINATE_CANCEL = 0
NS_TERMINATE_NOW = 1
NS_TERMINATE_LATER = 2

# DD3 bounds: the boot wait is 5 s; the drain's own join is 60 s (inside
# ``_graceful_shutdown``). Both sit well inside ``takeover._TAKEOVER_WAIT_BOUND``.
BOOT_WAIT_BOUND = 5.0

# Bound on the cross-thread ``isVisible`` fallback read.
_VISIBLE_READ_TIMEOUT = 1.0


# -- the pure decision core ----------------------------------------------------


@dataclass(frozen=True)
class DockView:
    """An immutable snapshot of the lifecycle facts the decisions read."""

    really_quit: bool = False
    booting: bool = False
    has_window: bool = False  # ``state.desktop_window is not None`` (published)
    terminate_pending: bool = False
    has_server: bool = False  # ``state.server is not None`` (a local server to drain)
    native_window: bool = False  # a native window exists (published or not)


def snapshot(state, *, native_window: bool = False) -> DockView:
    """Take a ``DockView`` from a ``SessionState`` under its lock."""
    with state.lock:
        return DockView(
            really_quit=state.really_quit,
            booting=state.booting,
            has_window=state.desktop_window is not None,
            terminate_pending=state.terminate_pending,
            has_server=state.server is not None,
            native_window=native_window,
        )


def on_close(view: DockView) -> str:
    """The ``closing`` handler's decision: ``"hide"`` or ``"allow"`` the destroy.

    A failed hide is the caller's to turn into ``allow``.
    """
    if view.really_quit:
        return "allow"
    if view.has_window:
        return "hide"
    # A window not yet published (or booting): hide it when a native one exists.
    return "hide" if view.native_window else "allow"


def on_reopen(view: DockView) -> str:
    """The Dock-icon / ``open -a`` reopen decision: ``show``, ``defer`` or ``ignore``.

    ``show`` also deminiaturizes (a miniaturized window reports no visible windows).
    """
    if view.really_quit or view.terminate_pending:
        return "ignore"
    if view.booting and not view.has_window:
        return "defer"
    return "show"


def on_terminate(view: DockView) -> str:
    """``applicationShouldTerminate:``'s decision.

    ``already-pending`` (answer ``NSTerminateLater``, start nothing), ``reply-now``
    (a window-only client owns no server: ``NSTerminateNow``) or
    ``drain-then-reply`` (``NSTerminateLater`` and start the worker).
    """
    if view.terminate_pending:
        return "already-pending"
    if not view.has_server:
        return "reply-now"
    return "drain-then-reply"


def terminate_reply_code(decision: str) -> int:
    """The ``NSApplicationTerminateReply`` value for an ``on_terminate`` decision."""
    return NS_TERMINATE_NOW if decision == "reply-now" else NS_TERMINATE_LATER


# -- the terminate worker -------------------------------------------------------


class TerminateWorker:
    """DD3's worker: wait for the boot to stop, drain the server, flush, reply.

    Every effect is injected so a test drives it with fakes:

    - ``reply()``: answer ``replyToApplicationShouldTerminate:`` (main thread);
    - ``drain()``: ``_graceful_shutdown`` on the session's own server and thread;
    - ``boot_wait(timeout) -> bool``: wait on ``boot_stopped`` (True when set);
    - ``log_flush()``: flush (never close) the logging handlers;
    - ``clock()`` / ``sleep(s)``: time source (elapsed logging) and the pause
      before the one reply retry.

    Geometry is NOT read here: it is read in the delegate callback, on the main
    thread, before ``NSTerminateLater`` is returned. The worker holds no lock.
    The reply is sent even when the boot wait times out or the drain raises.
    """

    def __init__(
        self,
        reply: Callable[[], None],
        drain: Callable[[], None],
        boot_wait: Callable[[float], bool],
        log_flush: Callable[[], None],
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        boot_bound: float = BOOT_WAIT_BOUND,
        clear_records: Callable[[], object] | None = None,
    ) -> None:
        # M35 F2 L8: clears the widget crash records (bounded, never raises) between the
        # boot wait and the drain, while the page can still run a script.
        self._clear_records = clear_records
        self._reply = reply
        self._drain = drain
        self._boot_wait = boot_wait
        self._log_flush = log_flush
        self._clock = clock
        self._sleep = sleep
        self._boot_bound = boot_bound
        self.thread: threading.Thread | None = None

    def start(self) -> threading.Thread:
        """Run the worker on one daemon thread."""
        self.thread = threading.Thread(target=self.run, name="terminate-worker", daemon=True)
        self.thread.start()
        return self.thread

    def run(self) -> None:
        t0 = self._clock()
        try:
            if not self._boot_wait(self._boot_bound):
                log.warning("terminate: boot did not stop within %.1fs", self._boot_bound)
        except Exception:
            log.warning("terminate: boot wait raised", exc_info=True)
        if self._clear_records is not None:
            try:
                self._clear_records()
            except Exception:
                log.warning("terminate: clearing widget records raised", exc_info=True)
        try:
            log.info("terminate: drain started")
            self._drain()
            log.info("terminate: drain done in %.1fs", self._clock() - t0)
        except Exception:
            log.warning("terminate: drain raised — replying anyway", exc_info=True)
        log.info("terminate: reply sending")
        try:
            self._log_flush()
        except Exception:
            pass
        self._send_reply()

    def _send_reply(self) -> None:
        for attempt in (1, 2):
            try:
                self._reply()
                return
            except Exception:
                log.warning("terminate: reply failed (attempt %d)", attempt, exc_info=True)
                if attempt == 1:
                    self._sleep(0.5)


def flush_log_handlers() -> None:
    """Flush every handler on the root logger and the shell logger (never close)."""
    seen: set[int] = set()
    for lg in (logging.getLogger(), log):
        for handler in list(lg.handlers):
            if id(handler) in seen:
                continue
            seen.add(id(handler))
            try:
                handler.flush()
            except Exception:
                pass


# -- named AppKit seams (darwin only; tests replace these) -----------------------


def _call_after(fn, *args) -> None:
    """Run ``fn(*args)`` on the AppKit main thread (``AppHelper.callAfter``)."""
    from PyObjCTools import AppHelper

    AppHelper.callAfter(fn, *args)


def _nsapp():
    """The shared ``NSApplication``."""
    import AppKit

    return AppKit.NSApplication.sharedApplication()


def _native_window(window):
    """The ``NSWindow`` behind a pywebview window (pywebview sets ``window.native``)."""
    return window.native


def terminate_app() -> None:
    """``NSApp.terminate_(None)`` on the main thread (path T for self-started quits)."""
    _call_after(lambda: _nsapp().terminate_(None))


def reply_to_terminate(ok: bool = True) -> None:
    """``replyToApplicationShouldTerminate:`` on the main thread."""
    _call_after(lambda: _nsapp().replyToApplicationShouldTerminate_(bool(ok)))


def activate(window) -> None:
    """Show, deminiaturize and activate the app, always on the main thread.

    pywebview's Cocoa ``restore()`` calls ``deminiaturize_`` on the caller's
    thread, which the HTTP route's threadpool thread must not do.
    """

    def _job():
        try:
            nswin = _native_window(window)
            if nswin.isMiniaturized():
                nswin.deminiaturize_(None)
            nswin.makeKeyAndOrderFront_(None)
            _nsapp().activateIgnoringOtherApps_(True)
        except Exception:
            log.warning("activate: raised", exc_info=True)

    _call_after(_job)


def native_visible(window) -> bool | None:
    """The real ``NSWindow.isVisible()``; None when it cannot be read.

    Tries a direct read first (as pywebview's own ``get_size`` does), then falls
    back to a main-thread read with a bounded wait.
    """
    try:
        return bool(_native_window(window).isVisible())
    except Exception:
        log.debug("native_visible: direct read failed", exc_info=True)
    done = threading.Event()
    box: list = []

    def _job():
        try:
            box.append(bool(_native_window(window).isVisible()))
        except Exception:
            box.append(None)
        finally:
            done.set()

    try:
        _call_after(_job)
    except Exception:
        log.warning("native_visible: dispatch failed", exc_info=True)
        return None
    if not done.wait(_VISIBLE_READ_TIMEOUT):
        log.warning("native_visible: read timed out after %.1fs", _VISIBLE_READ_TIMEOUT)
        return None
    return box[0]


def order_out(window) -> None:
    """``orderOut:`` the window directly (path S, on the main thread; never raises)."""
    try:
        _native_window(window).orderOut_(None)
    except Exception:
        log.warning("path S: orderOut raised", exc_info=True)


# -- the delegate callbacks (plain functions; the ObjC subclass only forwards) -----


def handle_terminate(session) -> int:
    """``applicationShouldTerminate:`` body (main thread). Returns the reply code.

    Geometry is read HERE, on the main thread, before ``NSTerminateLater`` is
    returned, so the worker never touches AppKit state. Never raises: on an
    unexpected error it answers ``NSTerminateNow`` rather than hang the quit.
    """
    try:
        view = snapshot(state, native_window=getattr(session, "_window", None) is not None)
        decision = on_terminate(view)
        log.info("terminate: applicationShouldTerminate received (decision=%s)", decision)
        if decision == "drain-then-reply" and state.mark_terminate_pending():
            _start_terminate(session)
        return terminate_reply_code(decision)
    except Exception:
        log.exception("terminate: handler raised — answering NSTerminateNow")
        return NS_TERMINATE_NOW


def _start_terminate(session) -> None:
    from the_one.interfaces.desktop import chrome

    window = state.begin_quit()
    server, thread = state.server, state.thread
    chrome.deregister()
    if window is not None:
        try:
            session._save_current_geometry(window)
        except Exception:
            log.warning("terminate: geometry save raised", exc_info=True)
    TerminateWorker(
        reply=reply_to_terminate,
        drain=lambda: session._drain(server, thread),
        boot_wait=state.boot_stopped.wait,
        log_flush=flush_log_handlers,
        clear_records=lambda: widget_records.clear_widget_records(window or state.desktop_window),
    ).start()


def handle_reopen(session, has_visible_windows) -> bool:
    """``applicationShouldHandleReopen:hasVisibleWindows:`` body (main thread).

    Returns False (we handled it; AppKit's default would open an untitled window).
    """
    try:
        window = state.desktop_window
        decision = on_reopen(snapshot(state, native_window=window is not None))
        log.info("reopen: decision=%s hasVisibleWindows=%s", decision, bool(has_visible_windows))
        if decision == "show" and window is not None:
            activate(window)
    except Exception:
        log.warning("reopen: handler raised", exc_info=True)
    return False


# -- install (darwin only) -------------------------------------------------------

# The App Nap activity token. MODULE-LEVEL on purpose: a local would be released
# when ``install`` returns, which ends the activity (DD2).
_ACTIVITY_TOKEN = None
_INSTALLED_ROUTE: str | None = None
_DELEGATE_CLASS_NAME = "GleepGlorpAppDelegate"


def _protocol_signature(objc, selector: str) -> bytes | None:
    """The ``NSApplicationDelegate`` protocol's type encoding for an instance method."""
    want = selector.encode()
    proto = None
    try:
        proto = objc.protocolNamed("NSApplicationDelegate")
        desc = proto.descriptionForInstanceMethod_(want)
        if desc:
            got = desc[1] if isinstance(desc, tuple) else desc.get("type")
            if got:
                return got if isinstance(got, bytes) else str(got).encode()
    except Exception:
        log.debug("protocol descriptionForInstanceMethod_ failed", exc_info=True)
    try:
        for item in proto.instanceMethods() if proto is not None else ():
            if item.get("selector") == want:
                return item.get("typestr")
    except Exception:
        log.debug("protocol instanceMethods failed", exc_info=True)
    return None


def _reopen_signature(objc) -> bytes:
    """The reopen selector's encoding (``B@:@B``), frame offsets stripped."""
    import re

    got = _protocol_signature(objc, "applicationShouldHandleReopen:hasVisibleWindows:")
    if got:
        return re.sub(rb"[0-9]+", b"", got)
    return objc._C_NSBOOL + objc._C_ID + objc._C_SEL + objc._C_ID + objc._C_NSBOOL


def _install_delegate(session) -> str:  # pragma: no cover - needs AppKit
    """Replace ``BrowserView.AppDelegate`` with a subclass (leg 3b: route ``subclass``).

    ``applicationShouldTerminate_`` / ``applicationWillTerminate_`` are plain
    methods with NO explicit signature, so PyObjC uses the inherited prototype
    (``I@:@``, not ``Q@:@``). Reopen is not on pywebview's delegate: it takes the
    protocol's own encoding. Returns the route name, or "none" on failure.
    """
    import objc
    from webview.platforms.cocoa import BrowserView

    try:
        base = BrowserView.AppDelegate
        reopen_sig = _reopen_signature(objc)

        def _reopen(self, app, flag):
            return handle_reopen(session, flag)

        class GleepGlorpAppDelegate(base):  # noqa: N801 - the ObjC class name
            def applicationShouldTerminate_(self, app):  # noqa: N802
                return handle_terminate(session)

            def applicationWillTerminate_(self, note):  # noqa: N802
                log.info("terminate: applicationWillTerminate (AppKit exiting)")

            applicationShouldHandleReopen_hasVisibleWindows_ = objc.selector(  # noqa: N815
                _reopen,
                selector=b"applicationShouldHandleReopen:hasVisibleWindows:",
                signature=reopen_sig,
            )

        BrowserView.AppDelegate = GleepGlorpAppDelegate
        return "subclass"
    except Exception:
        log.warning("macos dock: delegate install failed — stock delegate", exc_info=True)
        return "none"


def _begin_activity():  # pragma: no cover - needs Foundation
    """Begin the App Nap activity (user-initiated, idle system sleep allowed)."""
    import Foundation

    return Foundation.NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
        Foundation.NSActivityUserInitiatedAllowingIdleSystemSleep,
        "GleepGlorp AI is serving its local app",
    )


def install(session) -> str:
    """Install dock mode (once, main thread, before ``webview.start``); returns the route."""
    global _ACTIVITY_TOKEN, _INSTALLED_ROUTE
    if _INSTALLED_ROUTE is not None:
        return _INSTALLED_ROUTE
    route = _install_delegate(session)
    try:
        _ACTIVITY_TOKEN = _begin_activity()
    except Exception:
        log.warning("macos dock: App Nap activity not started", exc_info=True)
    _INSTALLED_ROUTE = route
    log.info(
        "macos dock: delegate installed (route=%s, app nap activity %s)",
        route,
        "held" if _ACTIVITY_TOKEN is not None else "not held",
    )
    return route
