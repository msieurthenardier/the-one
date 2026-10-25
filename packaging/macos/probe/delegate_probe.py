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
import re
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
    proto_name = "NSApplicationDelegate"
    sel_term = "applicationShouldTerminate:"
    sel_reopen = "applicationShouldHandleReopen:hasVisibleWindows:"
    sel_will = "applicationWillTerminate:"

    def protocol_signature(selector):
        """The protocol's type encoding for an instance method, read from the runtime (or None)."""
        try:
            proto = objc.protocolNamed(proto_name)
        except Exception as exc:  # noqa: BLE001
            log("protocol %s lookup failed: %r" % (proto_name, exc))
            return None
        want = selector.encode() if isinstance(selector, str) else selector
        try:
            desc = proto.descriptionForInstanceMethod_(want)
            if desc:
                return desc[1] if isinstance(desc, tuple) else desc.get("type")
        except Exception as exc:  # noqa: BLE001
            log("protocol descriptionForInstanceMethod_ failed: %r" % (exc,))
        try:
            for item in proto.instanceMethods():
                name = item.get("selector") if hasattr(item, "get") else None
                if name == want:
                    return item.get("typestr")
        except Exception as exc:  # noqa: BLE001
            log("protocol instanceMethods failed: %r" % (exc,))
        return None

    def inherited_signature(selector):
        """Signature from the superclass's own method, else the protocol's, else None."""
        py_name = selector.replace(":", "_")
        existing = getattr(base, py_name, None)
        got = getattr(existing, "signature", None)
        if got:
            return got, "superclass"
        got = protocol_signature(selector)
        if got:
            if isinstance(got, str):
                got = got.encode()
            got = re.sub(rb"[0-9]+", b"", got)  # drop the frame offsets a protocol may carry
            return got, "protocol"
        return None, "none"

    sig_term, src_term = inherited_signature(sel_term)
    sig_reopen, src_reopen = inherited_signature(sel_reopen)
    sig_will, src_will = inherited_signature(sel_will)
    if sig_reopen is None:
        # last resort, still from the runtime's own type constants rather than a literal string
        sig_reopen = objc._C_NSBOOL + objc._C_ID + objc._C_SEL + objc._C_ID + objc._C_NSBOOL
        src_reopen = "objc type constants (BOOL return, id, BOOL)"
    log(
        "resolved signatures: terminate=%r (%s) reopen=%r (%s) willTerminate=%r (%s)"
        % (sig_term, src_term, sig_reopen, src_reopen, sig_will, src_will)
    )

    def logged(label, sel):
        log("signature %s=%s" % (label, sig(sel)))

    route = "none (stock delegate)"
    try:

        class M32ProbeAppDelegate(base):
            # no explicit signature: PyObjC takes the inherited prototype
            def applicationShouldTerminate_(self, app):
                return should_terminate(self, app)

            def applicationWillTerminate_(self, note):
                return will_terminate(self, note)

            # not defined by pywebview's delegate: pass the protocol's own type encoding
            applicationShouldHandleReopen_hasVisibleWindows_ = objc.selector(  # noqa: N815
                should_reopen, selector=sel_reopen.encode(), signature=sig_reopen
            )

        logged(
            "subclass applicationShouldTerminate_", M32ProbeAppDelegate.applicationShouldTerminate_
        )
        logged("subclass applicationWillTerminate_", M32ProbeAppDelegate.applicationWillTerminate_)
        logged(
            "subclass applicationShouldHandleReopen_hasVisibleWindows_",
            M32ProbeAppDelegate.applicationShouldHandleReopen_hasVisibleWindows_,
        )
        BrowserView.AppDelegate = M32ProbeAppDelegate
        route = "subclass"
    except Exception:  # noqa: BLE001
        log("route subclass failed:\n%s" % traceback.format_exc())
        try:
            adds = [
                objc.selector(should_terminate, selector=sel_term.encode(), signature=sig_term)
                if sig_term
                else None,
                objc.selector(should_reopen, selector=sel_reopen.encode(), signature=sig_reopen),
                objc.selector(will_terminate, selector=sel_will.encode(), signature=sig_will)
                if sig_will
                else None,
            ]
            if adds[0] is None:
                raise RuntimeError("no applicationShouldTerminate: signature from the runtime")
            objc.classAddMethods(base, [a for a in adds if a is not None])
            route = "classAddMethods"
        except Exception:  # noqa: BLE001
            log("route classAddMethods failed:\n%s" % traceback.format_exc())
    logged("superclass applicationShouldTerminate_", base.applicationShouldTerminate_)
    log("route: %s" % route)
    log(
        "pywebview=%s pyobjc=%s"
        % (getattr(webview, "__version__", "?"), getattr(objc, "__version__", "?"))
    )

    if mode == "--selftest":
        if route == "none (stock delegate)":
            log("selftest FAILED: no delegate route installed (exit 3)")
            print("selftest FAILED route=%s" % route)
            return 3
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

    def log_delegate(where):
        try:
            log(
                "NSApp.delegate().className() at %s = %s"
                % (where, AppKit.NSApp.delegate().className())
            )
        except Exception as exc:  # noqa: BLE001
            log("NSApp.delegate read failed at %s: %r" % (where, exc))

    def on_shown():
        log("window shown event")
        log_delegate("shown")

    def on_loaded():
        log(
            "window loaded event (first paint of the data URL: %.3f s after process start)"
            % (time.monotonic() - START)
        )
        log_delegate("loaded")

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
