from __future__ import annotations

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


def run() -> None:
    host, port = settings.host, settings.port
    sel_port, is_ours = _select_port(host, port)
    url = f"http://{host}:{sel_port}/"
    server = None
    thread = None
    if not is_ours:
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
            # frameless=False (explicit): native OS frame (title bar + app name)
            # and NO browser chrome (no URL bar — it's not a browser). DD8's
            # "transparent web-underneath" = absence of browser chrome, not a
            # borderless window. Explicit guards against a pywebview default change.
            webview.create_window("GleepGlorp AI", url, frameless=False)
            webview.start()  # blocks until window closes
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
