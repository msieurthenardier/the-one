from __future__ import annotations

import logging
import os
import re
import signal
import socket
import sys
import threading
import time
import webbrowser

import httpx
import uvicorn

from the_one import __version__
from the_one.api_credential import get_credential
from the_one.config import settings
from the_one.interfaces.desktop import chrome, notice, tray
from the_one.interfaces.desktop import host as desktop_host
from the_one.interfaces.desktop import window_state as window_state_store

log = logging.getLogger(__name__)

# ── Module-level lifecycle state (reset to these defaults each process launch) ──
# Set to True by the Quit tray-menu callback so the `closing` handler allows
# the window destroy instead of hiding it.
_really_quit: bool = False
# The pywebview Window object; populated in run_desktop() for use by callbacks.
_desktop_window = None
# How the tray was decided this launch: "indicator" | "xembed" | "none" |
# "failed" | None (Windows/macOS, or not decided yet). Reset at the top of run().
_tray_mode: str | None = None
# The running DesktopSession (set at the top of run(), cleared when it returns);
# quit_desktop() uses it from the HTTP route.
_session = None
# Visibility tracked by the shell for non-GTK backends (GTK reads get_visible()).
_tracked_visible: bool | None = None
# Pending quit and the boot race (DD4). Everything the quit route reads or the
# boot publishes is guarded by ``_window_lock``; ``_on_quit`` (which blocks on
# icon.stop() and destroy) is NEVER called while holding it.
_window_lock = threading.Lock()
# True from just after the ``is_ours`` return in run() until the window is
# published (step 6), the browser branch is entered, or run() ends.
_booting: bool = False
# A quit that arrived while ``_booting``; _boot honours it at each checkpoint.
_quit_requested: bool = False
# The uvicorn server while the browser-fallback branch is active.
_browser_server = None

# The one-time notice for a close with no tray to go back to.
# Short on purpose: GNOME's banner truncates long text with an ellipsis.
_NO_TRAY_NOTICE_SUMMARY = "GleepGlorp AI is still running"
_NO_TRAY_NOTICE_BODY = "Open it again to show it, or right-click its icon to quit."

# The one-time notice for a close that hides the window into the tray.
# Short for the same reason; ``tray.notify(icon, message, title)`` order.
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


# -- Version takeover (DD13) -------------------------------------------------
# Small, individually stubbable seams: the unit tests drive the whole takeover
# through them with no real clock, process or network.

_TAKEOVER_WAIT_BOUND = 75.0  # `_graceful_shutdown`'s 60 s join plus margin
_TAKEOVER_POLL = 0.5
_TAKEOVER_NOTICE_AFTER = 3.0


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _parse_version(text: str):
    """Parse ``X.Y.Z[.devN]`` into a sortable key, or None when it is not that.

    A ``.devN`` build sorts before its release (``0.11.9.dev1 < 0.11.9``) and dev
    numbers compare as integers (``dev9 < dev10``) -- the same order dpkg gives
    ``0.11.9~dev1``. ``packaging`` is not a declared dependency, so this is
    deliberately tiny; anything else (a local suffix, rc, junk) is None.
    """
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?", text.strip())
    if not m:
        return None
    major, minor, patch, dev = m.groups()
    # A release (no dev) sorts after every dev of the same X.Y.Z.
    return (int(major), int(minor), int(patch), (0, int(dev)) if dev is not None else (1, 0))


def _is_older(running: str | None, ours: str) -> bool:
    """True only when both parse and ``running`` is strictly older than ``ours``."""
    if running is None:
        return False
    a, b = _parse_version(running), _parse_version(ours)
    if a is None or b is None:
        return False
    return a < b


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_credential().encode()}"}


def _running_version(host: str, port: int) -> str | None:
    """The running instance's version from ``GET /api/info``, or None (unknown)."""
    try:
        r = httpx.get(f"http://{host}:{port}/api/info", headers=_auth_headers(), timeout=2.0)
        if r.status_code != 200:
            return None
        version = r.json().get("version")
        return version if isinstance(version, str) else None
    except (httpx.HTTPError, ValueError, AttributeError):
        return None


def _request_quit(host: str, port: int) -> dict | None:
    """``POST /api/window/quit``. Returns ``{"status": int, "body": dict|None}``.

    None on a connection error.
    """
    try:
        r = httpx.post(
            f"http://{host}:{port}/api/window/quit", headers=_auth_headers(), timeout=5.0
        )
    except httpx.HTTPError:
        return None
    try:
        body = r.json() if r.status_code == 200 else None
    except ValueError:
        body = None
    return {"status": r.status_code, "body": body if isinstance(body, dict) else None}


def _pid_alive(pid: int) -> bool:
    """Is process ``pid`` still running? Never ``os.kill`` on Windows, where any
    signal other than CTRL_C/CTRL_BREAK is ``TerminateProcess``."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        synchronize = 0x00100000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(synchronize, False, int(pid))
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_exit(pid: int, bound: float = _TAKEOVER_WAIT_BOUND) -> bool:
    """Wait until ``pid`` exits. True when it did, False at ``bound`` seconds."""
    start = _now()
    notified = False
    while _pid_alive(pid):
        elapsed = _now() - start
        if elapsed >= bound:
            return False
        if not notified and elapsed >= _TAKEOVER_NOTICE_AFTER:
            notified = True
            desktop_host.send_notification("GleepGlorp AI", "Updating GleepGlorp AI\u2026")
        _sleep(_TAKEOVER_POLL)
    return True


def _activation_token() -> str | None:
    token = os.environ.get("XDG_ACTIVATION_TOKEN") or os.environ.get("DESKTOP_STARTUP_ID")
    if token and len(token) <= 256 and not any(c.isspace() for c in token):
        return token
    return None


def _post_focus(host: str, port: int) -> None:
    """Raise the running instance's window, forwarding any activation token.

    A failed or rejected POST is tolerated (logged): the existing instance keeps
    running either way and this process is about to exit.
    """
    token = _activation_token()
    try:
        kwargs = {"json": {"activation_token": token}} if token else {}
        httpx.post(
            f"http://{host}:{port}/api/window/focus",
            headers=_auth_headers(),
            timeout=2.0,
            **kwargs,
        )
    except httpx.HTTPError:  # intentionally broad: ConnectError + TimeoutException
        log.warning("focus POST to running instance failed; exiting anyway")


def _takeover(host: str, port: int) -> tuple[int, bool]:
    """Handle an instance that shares our credential (DD13).

    Returns ``(port, True)`` to mean "done: a running instance was focused or
    left alone, exit" and ``(port, False)`` after an older instance was quit
    and the port re-selected ("start normally").
    """
    running = _running_version(host, port)
    if not _is_older(running, __version__):
        _post_focus(host, port)
        return port, True
    log.info("running GleepGlorp AI %s is older than %s; replacing it", running, __version__)
    answer = _request_quit(host, port)
    if answer is None:
        log.warning("quit request to the older instance failed; focusing it")
        _post_focus(host, port)
        return port, True
    status, body = answer["status"], answer["body"]
    if status in (401, 403):
        log.warning(
            "port %s answered %s to the quit request: another program, or a "
            "different credential, holds it",
            port,
            status,
        )
        return port, True
    if status in (404, 405):
        log.warning(
            "the running GleepGlorp AI has no quit route; restart GleepGlorp AI "
            "to finish the upgrade"
        )
        _post_focus(host, port)
        return port, True
    if status != 200 or body is None:
        log.warning("unexpected answer to the quit request (HTTP %s); focusing it", status)
        _post_focus(host, port)
        return port, True
    if body.get("quit") is not True:
        log.warning("a server-only instance holds the port; not replacing it")
        return port, True
    pid = body.get("pid")
    if type(pid) is not int or pid <= 0:
        log.warning("quit answer carries no valid pid; focusing the running instance")
        _post_focus(host, port)
        return port, True
    if not _wait_for_exit(pid):
        log.warning("the older instance (pid %s) did not exit in time; focusing it", pid)
        _post_focus(host, port)
        return port, True
    # Two near-simultaneous launches can still race here; documented.
    return _select_port(host, port)


def _select_port(host: str, port: int, retries: int = 3, delay: float = 0.3) -> tuple[int, bool]:
    """Select the port to use and determine if a the-one instance is already running.

    Returns (port_to_use, is_our_instance):
    - (port, False): port is free — start a new server on the configured port.
    - (port, True): a the-one that shares OUR credential is already answering
      on that port (DD4 case b, DD11) — do NOT start a second server.
    - (free_port, False): a foreign process holds the configured port (DD4 case c)
      — bind-0 a free port for this instance.

    Uses a connect-probe (not a bind-probe with SO_REUSEADDR, which gives a
    false "free" on a TIME_WAIT port). Includes a startup-retry so a the-one
    that just bound but hasn't finished lifespan startup (/api/info not yet 200)
    isn't misclassified as foreign.

    DD11: "ours" is credentialed. The prior version-only check (200 +
    matching `__version__`) misclassified a *different* instance running the
    same version against a *different* data directory as ours — version
    alone says nothing about which data directory (and therefore which
    credential) answered. Sending our own credential and treating a 200 as
    success is what "ours" should always have meant: the server on the other
    end validated the exact credential this process would also use, which
    only happens when it reads the same credential file. A foreign server
    that also 401s (wrong or absent credential) simply resolves to "not
    ours" — already the safe answer for the fall-through below.

    Edge case: no credential file exists yet (fresh machine, first launch).
    `get_credential()` creates one on first use rather than raising, so a
    missing-credential machine still gets a well-formed probe — and "cannot
    be ours" falls out naturally (nothing on a fresh machine could share a
    credential that didn't exist a moment ago).
    """
    auth_headers = {"Authorization": f"Bearer {get_credential().encode()}"}
    for attempt in range(retries):
        # (b) a the-one that shares OUR credential already answering?
        try:
            r = httpx.get(f"http://{host}:{port}/api/info", headers=auth_headers, timeout=1.0)
            if r.status_code == 200:
                return port, True
        except httpx.HTTPError:
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
    # (c) occupied by a foreign process, or by a the-one that never confirmed
    # OUR credential (a different data dir or a rotated credential): bind-0 a
    # free port. Ownership is decided by credential, never by version — a the-one
    # of another version that shares our credential answered (b) above.
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
    global _tracked_visible
    _tracked_visible = True


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
    window = _desktop_window
    if window is None:
        return None
    if not _is_gtk_backend():
        return _tracked_visible
    try:
        return _gtk_read(lambda: bool(window.native.get_visible()))
    except Exception:
        log.warning("window_visible: read failed", exc_info=True)
        return None


def _window_mapped() -> bool | None:
    window = _desktop_window
    if window is None or not _is_gtk_backend():
        return None
    try:
        return _gtk_read(lambda: bool(window.native.get_mapped()))
    except Exception:
        return None


def _mode() -> str | None:
    """The lifecycle mode: serve / quitting / window / booting / browser / None."""
    if _session is None:
        return "serve"
    if _really_quit:
        return "quitting"
    if _desktop_window is not None:
        return "window"
    if _booting:
        return "booting"
    if _browser_server is not None:
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
        "desktop": _desktop_window is not None,
        "mode": _mode(),
        "visible": visible,
        "mapped": mapped,
        "tray": _tray_mode,
        "version": __version__,
        "pid": os.getpid(),
    }


def quit_desktop() -> str | None:
    """Quit the desktop session (``POST /api/window/quit``).

    Returns the state acted on: ``"window"`` (the session's quit ran),
    ``"booting"`` (a quit is recorded and ``_boot`` honours it at its next
    checkpoint), ``"browser"`` (the fallback server was told to drain), or
    None when there is nothing to quit (``serve`` mode). The state is chosen
    under ``_window_lock``; the blocking quit runs after the lock is released.
    """
    global _quit_requested
    with _window_lock:
        session = _session
        if _desktop_window is not None and session is not None:
            if _really_quit:
                return "window"  # a quit is already under way; never destroy twice
            state = "window"
        elif _booting:
            _quit_requested = True
            return "booting"
        elif _browser_server is not None:
            _browser_server.should_exit = True
            return "browser"
        else:
            return None
    try:
        session._on_quit(session._icon)
        return state
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
    if _desktop_window is None:
        return False
    try:
        if activation_token and _is_gtk_backend():
            log.info("focus_window: activation token %s...", activation_token[:6])
            _gtk_activate(_desktop_window, activation_token)
            _mark_visible()
        else:
            _show_window(_desktop_window, restore=True)
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


def _clear_booting() -> None:
    global _booting
    with _window_lock:
        _booting = False


def _no_tray_hide(window=None) -> bool:
    """Hide the window for a close with no tray (``_tray_mode == "none"``).

    Hides, marks the tracked visibility False, then shows the one-time notice
    (its own marker, separate from the tray's). ``send_notification`` returns at
    once, so the GTK main thread never blocks (DD12). Returns False when there
    is no window or ``hide()`` raised (the caller then allows the destroy).
    """
    global _tracked_visible
    window = window or _desktop_window
    if window is None:
        return False
    try:
        window.hide()
    except Exception:
        log.warning("no-tray hide failed — allowing the close", exc_info=True)
        return False
    _tracked_visible = False
    try:
        if not notice.no_tray_notice_shown():
            notice.mark_no_tray_notice_shown()
            desktop_host.send_notification(_NO_TRAY_NOTICE_SUMMARY, _NO_TRAY_NOTICE_BODY)
    except Exception:
        log.debug("no-tray notice failed", exc_info=True)
    return True


class DesktopSession:
    """Owns the per-launch window/tray/quit lifecycle for the desktop app.

    All per-launch state (tray icon reference) lives here.  The window reference
    and quit flag are kept as module globals so that focus_window() (module-level)
    and the F6 test suite (which writes the module global directly) continue to
    work without change — see DD1 and the RESOLVED note in the leg spec.
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
        if _is_gtk_backend():
            if threading.current_thread() is not threading.main_thread():
                log.warning("window_state: GTK geometry save off the main thread — skipped")
                return
            native = getattr(window, "native", None)
            if native is None:
                log.debug("window_state: no native window — skipped")
                return
            try:
                w, h = native.get_size()
                if _on_wayland(window):
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

        This method does NOT guard ``_really_quit`` — ``_on_closing`` does.
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

        if _desktop_window is not None:
            try:
                _desktop_window.hide()
            except Exception:
                return False
        return True

    def _on_closing(self) -> bool:
        """pywebview closing handler.

        Returns False (cancel the destroy) when the window was hidden, True
        (allow it) otherwise:

        - ``_really_quit``: allow (the Quit callback asked for the destroy).
        - tray running (``self._icon``): hide to tray.
        - ``_tray_mode == "none"``: hide through ``_no_tray_hide`` (the app
          stays running; a relaunch or ``the-one quit`` reaches it).
        - anything else (``failed``, None: no tray decided yet, or a non-Linux
          path with no tray): allow the destroy.

        pywebview's Event.set() swallows handler exceptions, so a raise here
        would lose the cancel value and destroy the window; the hide calls are
        wrapped and a failure allows the destroy deterministically.
        """
        window = _desktop_window or self._window
        # Capture geometry before any hide/destroy (best-effort).
        self._save_current_geometry(window)

        if _really_quit:
            chrome.deregister()
            return True  # Quit callback already requested real destroy

        if self._icon is not None:
            hidden = self._close_to_tray()
        elif _tray_mode == "none":
            hidden = _no_tray_hide(window)
        else:
            hidden = False
        if not hidden:
            chrome.deregister()  # allowing the destroy
        return not hidden  # True → allow destroy; False → cancel

    def _on_show(self, icon) -> None:
        """Tray "Show" menu callback: show the window.

        The window was hidden via close-to-tray (not minimized), so
        show() is sufficient.  restore() is intentionally omitted here —
        it snapped the window size on each show when the window was merely
        hidden.  focus_window() keeps show()+restore() for the
        single-instance-focus path where the window may be minimized.
        """
        if _desktop_window is not None:
            _show_window(_desktop_window)

    def _on_quit(self, icon) -> None:
        """Tray "Quit" menu callback: graceful full exit.

        Order: set really-quit flag → stop tray (MUST complete —
        run_detached() spawns a non-daemon thread; skipping stop() leaves
        it alive and hangs the process after _graceful_shutdown) →
        destroy window (causes webview.start() to return) → the existing
        `finally: _graceful_shutdown(server, thread)` drains the server.
        """
        global _really_quit
        _really_quit = True  # tell _on_closing to allow destroy
        chrome.deregister()  # a request racing the destroy applies nothing

        # icon.stop() MUST run; guard so it survives even if destroy raises.
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                log.warning("pystray icon.stop() raised during Quit — ignored", exc_info=True)

        if _desktop_window is not None:
            # Capture geometry before destroy (redundant-but-safe per edge-case
            # note in leg spec: closing fires on destroy in pywebview-5.4 for all
            # known backends, so _on_closing already ran; this second write is
            # idempotent forward-safety for any future backend that skips it).
            if not _is_gtk_backend():  # on GTK, closing saves it (main thread)
                self._save_current_geometry(_desktop_window)
            _desktop_window.destroy()

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
        global _really_quit, _desktop_window, _tray_mode, _session, _tracked_visible
        global _booting, _quit_requested, _browser_server

        # Reset process-local state on each launch (e.g. if run_desktop() is called
        # more than once in tests after a reload).
        _really_quit = False
        _desktop_window = None
        _tray_mode = None
        _tracked_visible = None
        _booting = False
        _quit_requested = False
        _browser_server = None
        _session = self
        chrome.reset()

        host, port = settings.host, settings.port
        sel_port, is_ours = _select_port(host, port)
        if is_ours:
            # A the-one that shares our credential already owns this port: focus
            # it, or, when it is an older version, replace it (DD13). Header-less
            # loopback POSTs (no Origin) clear the OriginAllowlistMiddleware; the
            # Authorization header carries the credential the gate requires.
            sel_port, is_ours = _takeover(host, sel_port)
        if is_ours:
            _session = None  # a window-only client owns nothing: not a desktop session
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
        # honour; cleared on every exit path (see ``_clear_booting``).
        with _window_lock:
            _booting = True
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
        # is_ours=True already returned above; reaching here means is_ours=False —
        # we always start our own server on the selected port.
        from the_one.interfaces.web.app import app

        server = uvicorn.Server(uvicorn.Config(app, host=host, port=sel_port, log_level="info"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            if _webview_available():
                try:
                    import webview  # lazy: optional [gui] extra; off chat/version
                except ImportError as exc:
                    _clear_booting()
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
                        _fw, _fh = first_launch_size(_resolve_screens(), sys.platform)
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

                if sys.platform == "win32":
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

                def _destroy_splash() -> None:
                    """Destroy the splash window — idempotent (safe to call twice)."""
                    if _splash_closed.is_set():
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
                    6. Set _desktop_window / self._window.
                    """
                    global _desktop_window, _tray_mode, _booting
                    main_win = None

                    def _abort_if_quit() -> bool:
                        """Honour a quit that arrived while booting (DD4).

                        Releases the loaded handler, destroys the main window (if
                        created) and the splash. On GTK a window created inside the
                        running loop is already mapped, so a quit after creation
                        flashes it briefly (accepted).
                        """
                        global _really_quit
                        with _window_lock:
                            if not _quit_requested:
                                return False
                        _really_quit = True  # the destroy below must not be cancelled
                        _main_shown.set()
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
                        # with ``_tray_mode`` still None the handler allows the
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
                        try:
                            _show_window(main_win)
                        except Exception:
                            if sys.platform != "win32":
                                log.exception("main window show() raised")
                                raise
                            log.warning(
                                "main window show() raised — native show fallback",
                                exc_info=True,
                            )
                            chrome.native_show(main_win)  # raises when it fails too
                            _mark_visible()
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
                            if sys.platform.startswith("linux"):
                                tray_backend = desktop_host.choose_pystray_backend()
                                mode, reason = desktop_host.detect_tray(tray_backend)
                                if mode in ("none", "unavailable"):
                                    _tray_mode = "none"
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
                            if sys.platform.startswith("linux"):
                                _tray_mode = mode
                        except _NoTrayError:
                            pass
                        except Exception:
                            if sys.platform.startswith("linux"):
                                _tray_mode = "failed"
                            log.warning(
                                "System tray unavailable — close button will exit the app"
                                " (F4 fallback)",
                                exc_info=True,
                            )

                        # Step 6 — publish the window, clear ``_booting`` and read
                        # ``_quit_requested`` in ONE critical section, so a quit
                        # arriving at any moment is either seen here or finds the
                        # published window. ``_on_quit`` runs after the lock is released.
                        with _window_lock:
                            _desktop_window = main_win
                            self._window = main_win
                            _booting = False
                            quit_now = _quit_requested
                        if quit_now:
                            # The window may be destroyed before its ``loaded`` fires,
                            # which would leave the splash (and webview.start) alive.
                            self._on_quit(self._icon)
                            _main_shown.set()
                            _destroy_splash()

                    except Exception:
                        log.exception("_boot raised — tearing down to prevent orphaned splash")
                        _clear_booting()
                        _main_shown.set()  # release a waiting loaded handler
                        _destroy_splash()
                        if main_win is not None:
                            chrome.deregister()
                            try:
                                main_win.destroy()
                            except Exception:
                                log.debug("main_win.destroy() raised in error path", exc_info=True)
                        raise

                # Persist localStorage/cookies (e.g. the theme preference) across app
                # restarts AND reinstalls. pywebview defaults to private_mode=True — an
                # ephemeral profile that drops all web storage between launches, so a
                # localStorage-backed setting like the theme resets every restart. Point
                # the webview at a stable per-user profile dir under data_dir (outside the
                # install dir, and migrated with the rest of the user's data) so settings
                # survive. (M15 F5 post-landing fix: theme didn't survive restart/reinstall.)
                storage_dir = settings.data_dir / "webview"
                storage_dir.mkdir(parents=True, exist_ok=True)
                webview.start(  # blocks until all windows closed (or Quit → destroy)
                    _boot,
                    private_mode=False,
                    storage_path=str(storage_dir),
                )
            else:
                # Browser-fallback path: no pywebview, no splash.  Keep the
                # _wait_until_serving call here (it moved into _boot for the webview
                # path, so it must remain explicitly on this branch — otherwise the
                # browser would open before the server is ready).
                # A quit recorded while booting wins; otherwise a later quit finds
                # ``_browser_server`` and asks the server to drain.
                with _window_lock:
                    if _quit_requested:
                        _booting = False
                        return
                    _browser_server = server
                    _booting = False
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
                if sys.platform.startswith("linux"):
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
            _clear_booting()
            with _window_lock:
                _browser_server = None
            _graceful_shutdown(server, thread)  # no-op when server is None (case b)
            if _session is self:
                _session = None


def run_desktop() -> None:
    # M15 F6 review-fix: defensive second call (idempotent).  Covers any entry
    # path that doesn't go through frozen_entry_gui.py (e.g. a future launcher
    # script or test harness that calls run_desktop() directly).  The primary
    # call is in packaging/windows/frozen_entry_gui.py before cli_entry().
    from the_one.platform.env import ensure_stdio_streams  # noqa: PLC0415

    ensure_stdio_streams()
    DesktopSession().run()
