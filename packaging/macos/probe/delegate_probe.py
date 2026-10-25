# ruff: noqa: N802  (Objective-C selector names)
"""Probe app for the macOS premises (Mission 32 Flight 3, leg 2; DD4, DD3, DD9).

Build-time tooling: no product code, never imported by ``the_one/``. Frozen by ``probe.spec``
into ``M32 Probe.app`` and driven by ``probe.sh`` on the hosted macOS runner.

It answers, with pywebview 5.4's Cocoa backend and nothing else:

* does a subclass of ``BrowserView.AppDelegate`` take effect (``BrowserView.AppDelegate`` is read
  in ``BrowserView.__init__``), and does the ``NSUInteger`` return type of
  ``applicationShouldTerminate_`` survive (the signature is logged at startup);
* does ``NSTerminateLater`` plus a deferred ``replyToApplicationShouldTerminate_`` terminate;
* does the reopen handler fire on ``open -a`` (P4);
* how long does a data-URL window take to paint, with no server (P1 control);
* how long does ``webview.start`` take to return after the last window is destroyed from a
  worker thread (P9).

Modes (argv[1]): ``wait`` (default), ``destroy`` (P9), ``--selftest`` (imports, subclass
definition, signature log, exit 0, no window). Every line goes, flushed, to
``~/Library/Logs/m32-probe/probe.log``. Exit paths log whether ``applicationShouldTerminate_``
ran first: a "terminate" line means path T, ``webview.start`` returning with none means path S.
"""

import os
import sys
import threading
import time
import traceback

LOG_DIR = os.path.expanduser("~/Library/Logs/m32-probe")
LOG_PATH = os.path.join(LOG_DIR, "probe.log")
START = time.monotonic()
_LOCK = threading.Lock()


def log(msg):
    line = "%9.3f [%s] %s\n" % (time.monotonic() - START, threading.current_thread().name, msg)
    with _LOCK:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(LOG_PATH, "a") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            pass
        sys.stderr.write(line)
        sys.stderr.flush()


def main(argv):
    mode = argv[1] if len(argv) > 1 and not argv[1].startswith("-psn") else "wait"
    log("start pid=%d mode=%s sys.executable=%s" % (os.getpid(), mode, sys.executable))
    if sys.platform != "darwin":
        log("not darwin: this probe only runs on macOS")
        print("delegate_probe: macOS only", file=sys.stderr)
        return 2

    # after webview has imported its Cocoa backend (module-level activation policy and ATS key)
    import AppKit
    import Foundation
    import objc
    import WebKit  # noqa: F401  (hidden-import check for the selftest)
    import webview
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    state = {"terminate_seen": False}

    def sig(sel):
        try:
            return repr(getattr(sel, "signature", None))
        except Exception as exc:  # noqa: BLE001
            return "unreadable: %r" % (exc,)

    def later_reply(app):
        time.sleep(3)
        log("terminate: replying True after 3 s")
        AppHelper.callAfter(app.replyToApplicationShouldTerminate_, True)

    def should_terminate(self, app):
        state["terminate_seen"] = True
        log("terminate: applicationShouldTerminate_ called; returning NSTerminateLater (2)")
        threading.Thread(
            target=later_reply, args=(app,), name="terminate-worker", daemon=True
        ).start()
        return AppKit.NSTerminateLater

    def should_reopen(self, app, flag):
        log("reopen: applicationShouldHandleReopen called hasVisibleWindows=%s" % bool(flag))
        return False

    def will_terminate(self, note):
        log("willTerminate: applicationWillTerminate_ (AppKit reached its exit)")

    base = BrowserView.AppDelegate
    route = "none (stock delegate)"
    try:

        class M32ProbeAppDelegate(base):
            applicationShouldTerminate_ = objc.selector(  # noqa: N815
                should_terminate, selector=b"applicationShouldTerminate:", signature=b"Q@:@"
            )

            def applicationShouldHandleReopen_hasVisibleWindows_(self, app, flag):
                return should_reopen(self, app, flag)

            def applicationWillTerminate_(self, note):
                return will_terminate(self, note)

        log(
            "signature subclass applicationShouldTerminate_=%s"
            % sig(M32ProbeAppDelegate.applicationShouldTerminate_)
        )
        BrowserView.AppDelegate = M32ProbeAppDelegate
        route = "subclass"
    except Exception:  # noqa: BLE001
        log("route subclass failed:\n%s" % traceback.format_exc())
        try:
            objc.classAddMethods(
                base,
                [
                    objc.selector(
                        should_terminate,
                        selector=b"applicationShouldTerminate:",
                        signature=b"Q@:@",
                    ),
                    objc.selector(
                        should_reopen,
                        selector=b"applicationShouldHandleReopen:hasVisibleWindows:",
                        signature=b"c@:@c",
                    ),
                    objc.selector(
                        will_terminate,
                        selector=b"applicationWillTerminate:",
                        signature=b"v@:@",
                    ),
                ],
            )
            route = "classAddMethods"
        except Exception:  # noqa: BLE001
            log("route classAddMethods failed:\n%s" % traceback.format_exc())
    log(
        "signature superclass applicationShouldTerminate_=%s"
        % sig(base.applicationShouldTerminate_)
    )
    log("route: %s" % route)
    log(
        "pywebview=%s pyobjc=%s"
        % (getattr(webview, "__version__", "?"), getattr(objc, "__version__", "?"))
    )

    if mode == "--selftest":
        log("selftest ok route=%s" % route)
        print("selftest ok route=%s" % route)
        return 0

    log("argv=%s" % list(Foundation.NSProcessInfo.processInfo().arguments()))
    log("env PATH=%s SHELL=%s" % (os.environ.get("PATH"), os.environ.get("SHELL")))
    log("env M32_PROBE_ENV=%s" % os.environ.get("M32_PROBE_ENV"))

    html = "data:text/html,<body style='font:24px sans-serif'><h1>M32 probe</h1>%d</body>" % int(
        time.time()
    )
    window = webview.create_window("M32 Probe", url=html, width=640, height=400)

    def on_shown():
        log("window shown event")

    def on_loaded():
        log(
            "window loaded event (first paint of the data URL: %.3f s after process start)"
            % (time.monotonic() - START)
        )
        try:
            delegate = AppKit.NSApp.delegate()
            log("NSApp.delegate class=%s" % delegate.className())
        except Exception as exc:  # noqa: BLE001
            log("NSApp.delegate read failed: %r" % (exc,))

    def on_closed():
        log("window closed event")

    window.events.shown += on_shown
    window.events.closed += on_closed
    window.events.loaded += on_loaded

    def worker():
        if mode != "destroy":
            return
        time.sleep(5)
        t0 = time.monotonic()
        log("destroy: worker calling window.destroy()")
        state["destroy_at"] = t0
        window.destroy()
        # webview.start returning is logged on the main thread; give it 20 s, then report
        time.sleep(20)
        log("destroy: webview.start did not return within 20 s of destroy() (hang)")
        os._exit(3)

    t_start = time.monotonic()
    log("webview.start begin")
    webview.start(worker)
    ended = time.monotonic()
    if "destroy_at" in state:
        log(
            "destroy: webview.start returned %.3f s after window.destroy()"
            % (ended - state["destroy_at"])
        )
    log(
        "webview.start returned after %.3f s; terminate_seen=%s"
        % (ended - t_start, state["terminate_seen"])
    )
    log(
        "exit path %s"
        % (
            "T (applicationShouldTerminate_ ran)"
            if state["terminate_seen"]
            else "S (start returned, no terminate)"
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
