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

from the_one.api_credential import get_credential
from the_one.config import settings

log = logging.getLogger(__name__)

# ── Module-level lifecycle state (reset to these defaults each process launch) ──
# Set to True by the Quit tray-menu callback so the `closing` handler allows
# the window destroy instead of hiding it.
_really_quit: bool = False
# The pywebview Window object; populated in run_desktop() for use by callbacks.
_desktop_window = None

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

_SPLASH_TEXT_ONLY = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100%; height: 100%;
    background: #0f1117;
    display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #e8eaf0;
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
    color: #e8eaf0;
  }
  .status {
    font-size: 12px; color: #6b7280;
    letter-spacing: 0.05em;
  }
  .bar {
    width: 120px; height: 2px;
    background: #1e2130;
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


def _splash_html() -> str:
    """Build the splash HTML, embedding the brand logo as a base64 data URI.

    Reads gleepglorp_med.png from the bundled static directory at runtime and
    inlines it as ``<img src="data:image/png;base64,...">``.  This works both
    in development (filesystem) and in a PyInstaller freeze (_MEIPASS puts the
    collected static tree at the same path relative to web/app.py).

    Graceful fallback: any exception during asset resolution/encoding is caught,
    a warning is logged, and the text-only splash HTML is returned.  A
    splash-asset problem must never raise or hang boot.
    """
    import base64

    try:
        from the_one.interfaces.web.app import STATIC_DIR  # lazy — safe post web.app import

        logo_path = STATIC_DIR / "brand" / "gleepglorp_med.png"
        logo_b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        logo_src = f"data:image/png;base64,{logo_b64}"
    except Exception:
        log.warning(
            "splash: could not load brand logo — falling back to text-only splash", exc_info=True
        )
        return _SPLASH_TEXT_ONLY

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: 100%; height: 100%;
    background: #0f1117;
    display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #e8eaf0;
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
    color: #e8eaf0;
  }}
  .status {{
    font-size: 12px; color: #6b7280;
    letter-spacing: 0.05em;
  }}
  .bar {{
    width: 120px; height: 2px;
    background: #1e2130;
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

    # ── lifecycle callbacks ───────────────────────────────────────────────────

    def _close_to_tray(self) -> bool:
        """Shared close-to-tray body — called by ``_on_closing``.

        When the tray is active (``self._icon is not None``): show the
        first-run notice (once), hide the window.  Returns ``True`` when
        the hide succeeded (caller should cancel the destroy), ``False``
        when hide() raised (caller should allow the destroy — deterministic
        exit rather than a silent swallow into the event handler wrapper).

        When the tray failed to start (``self._icon is None``): set
        ``_really_quit = True`` and call ``destroy()`` for a real exit —
        never hide into a non-existent tray (the app would become
        unrecoverable).  Returns ``False`` in this branch.

        IMPORTANT: this method does NOT guard ``_really_quit`` — that flag
        is only checked by ``_on_closing`` (the pywebview events.closing
        handler path, fired by the native OS X button).
        """
        if self._icon is None:
            # Tray failed to start — fall back to a real destroy so the user
            # can exit; hiding into a non-existent tray would make the app
            # unrecoverable.
            global _really_quit
            _really_quit = True
            if _desktop_window is not None:
                _desktop_window.destroy()
            return False

        # Show first-run notice (once only).
        from the_one.interfaces.desktop.notice import mark_notice_shown, notice_shown
        from the_one.interfaces.desktop.tray import notify

        if not notice_shown():
            mark_notice_shown()
            notify(
                self._icon,
                "GleepGlorp AI is still running in the system tray"
                " — Quit from the tray menu to exit",
                "GleepGlorp AI",
            )

        # Hide the window — returns True on success, False on failure.
        if _desktop_window is not None:
            try:
                _desktop_window.hide()
            except Exception:
                # hide() failed — allow the close rather than silently
                # swallowing into the event handler wrapper.
                return False
        return True

    def _on_closing(self) -> bool:
        """pywebview closing handler: hide to tray instead of destroying.

        Returns False (cancel destroy) when the tray is active and
        _really_quit is not set.  Returns True (allow destroy) when the
        Quit callback has already set _really_quit.

        IMPORTANT: pywebview's Event.set() wraps each handler in
        try/except and swallows exceptions — a raise inside this handler
        is silently ignored and the cancel return value is lost, which
        would destroy the window unexpectedly.  Mitigation: the
        window.hide() call is wrapped in try/except inside
        ``_close_to_tray``; on failure we return True (allow the close
        deterministically) rather than let an exception leak into the
        swallow.
        """
        # Capture geometry before any hide/destroy (best-effort).
        self._save_current_geometry(_desktop_window)

        if _really_quit:
            return True  # Quit callback already requested real destroy

        # Delegate to the shared close-to-tray body.
        # Returns True when hide succeeded (cancel destroy); False when
        # hide() raised or tray was absent (allow destroy).
        hidden = self._close_to_tray()
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
            _desktop_window.show()

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
        global _really_quit, _desktop_window

        # Reset process-local state on each launch (e.g. if run_desktop() is called
        # more than once in tests after a reload).
        _really_quit = False
        _desktop_window = None

        host, port = settings.host, settings.port
        sel_port, is_ours = _select_port(host, port)
        if is_ours:
            # A the-one that shares our credential already owns this port —
            # raise its window and exit instead of opening a duplicate (DD4).
            # Header-less loopback POST (no Origin header) clears the
            # OriginAllowlistMiddleware; the Authorization header carries the
            # credential the gate now requires on every non-exempt path,
            # including this one — easy to miss because this branch returns
            # early without ever opening a window. A failed/rejected focus
            # POST is tolerated (logged, not raised): the existing instance
            # keeps running either way, and this process is about to exit.
            try:
                httpx.post(
                    f"http://{host}:{sel_port}/api/window/focus",
                    headers={"Authorization": f"Bearer {get_credential().encode()}"},
                    timeout=2.0,
                )
            except httpx.HTTPError:  # intentionally broad — covers ConnectError + TimeoutException
                log.warning("focus POST to running instance failed; exiting anyway")
            return
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
                    raise SystemExit(
                        "pywebview is not installed. "
                        "Install the desktop extra: pip install 'the-one[gui]'"
                    ) from exc

                # ── Window-state restore (pre-compute before _boot so _boot is
                #    a plain closure with no GUI-thread work) ──────────────────
                from the_one.interfaces.desktop.window_state import (
                    clamp_to_bounds,
                    load_state,
                )

                _saved_state = load_state()
                _create_kwargs: dict = {
                    "frameless": False,
                    "resizable": True,
                }
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
                                _screens = _screens()  # callable form
                        _clamped = clamp_to_bounds(_saved_state, _screens)
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
                    html=_splash_html(),
                    frameless=True,
                    width=400,
                    height=300,
                )

                # Idempotent splash teardown: a threading.Event guards against a
                # double-fire from the `loaded` handler racing the error path.
                # (The loaded handler runs on a daemon thread; a plain bool flag
                # has a TOCTOU window.)
                _splash_closed = threading.Event()

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
                    global _desktop_window
                    main_win = None
                    try:
                        # Step 1 — ensure splash is shown before any teardown attempt.
                        splash.events.shown.wait(15)

                        # Step 2 — wait for the app server.
                        _wait_until_serving(host, sel_port)

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

                        # Step 4 — register the loaded→destroy handler BEFORE tray wiring
                        # so a fast localhost load that fires during tray setup still
                        # dismisses the splash.
                        main_win.events.loaded += lambda: _destroy_splash()

                        # Step 4a — backstop: if loaded already fired before we subscribed,
                        # dismiss the splash immediately.
                        # pywebview 5.4 Event.is_set() delegates to threading.Event.is_set().
                        if main_win.events.loaded.is_set():
                            _destroy_splash()

                        # Step 5 — tray wiring.
                        # Degrades gracefully: if tray can't start, skip _on_closing
                        # registration (F4 fallback — X destroys the window directly).
                        try:
                            from the_one.interfaces.desktop.tray import build_tray

                            self._icon = build_tray(on_show=self._on_show, on_quit=self._on_quit)
                            self._icon.run_detached()
                            main_win.events.closing += self._on_closing
                        except Exception:
                            log.warning(
                                "System tray unavailable — close button will exit the app"
                                " (F4 fallback)",
                                exc_info=True,
                            )

                        # Step 6 — publish window reference.
                        _desktop_window = main_win
                        self._window = main_win

                    except Exception:
                        log.exception("_boot raised — tearing down to prevent orphaned splash")
                        _destroy_splash()
                        if main_win is not None:
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
                _wait_until_serving(host, sel_port)
                # Same handoff-minting treatment as the webview path above (DD7,
                # DD12): mint right before navigation, not earlier. Lazy import
                # for the same reason as the webview branch's import.
                from the_one.interfaces.web.handoff_store import (
                    HANDOFF_QUERY_PARAM,
                    mint_handoff_credential,
                )

                handoff_token = mint_handoff_credential()
                url = f"{base_url}?{HANDOFF_QUERY_PARAM}={handoff_token}"
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


def run_desktop() -> None:
    # M15 F6 review-fix: defensive second call (idempotent).  Covers any entry
    # path that doesn't go through frozen_entry_gui.py (e.g. a future launcher
    # script or test harness that calls run_desktop() directly).  The primary
    # call is in packaging/windows/frozen_entry_gui.py before cli_entry().
    from the_one.platform.env import ensure_stdio_streams  # noqa: PLC0415

    ensure_stdio_streams()
    DesktopSession().run()
