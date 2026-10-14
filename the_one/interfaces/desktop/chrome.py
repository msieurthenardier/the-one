"""Window chrome: the native title bar takes the workbench's colours (M25 F5 L2).

The page tells the shell its resolved theme over ``POST /api/window/chrome``;
this module holds the state behind that route, persists the theme for the next
launch's first frame, and (Windows 11 only) tints the native caption through
``DwmSetWindowAttribute``.

No GUI import happens at module top level, so the web app and the unit tests
import it everywhere. Every ``ctypes``, ``winreg`` and pythonnet use is lazy
and Windows-gated, and every one sits behind a small named seam
(``_invoke_ui``, ``_hwnd_of``, ``_dwm_set``, ``_subscribe_activation``,
``_native_enabled``) that the tests replace.

Contract in brief (``the_one/agents.md`` "Window chrome (M25 F5)"):

* One module lock guards STATE only. It is never held across a UI-thread
  invoke, a window ``show()`` or a Win32 call.
* Every DWM apply runs on the WinForms UI thread: the activation handlers are
  already on it, other threads go through ``form.BeginInvoke`` with a bounded
  wait (``_UI_WAIT_MS``). The apply reads the latest requested theme and the
  tracked activation state AT APPLY TIME, so racing requests converge.
* Nothing here ever raises into an HTTP handler or a WinForms event.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Palette (pinned to tokens.css by tests/test_window_chrome.py) ────────────
PALETTE: dict[str, dict[str, str]] = {
    "light": {
        "caption": "#fafafa",  # --surface
        "text": "#18181b",  # --fg
        "text_inactive": "#65656e",  # --fg-muted
        "border": "#e4e4e7",  # --border
        "bg": "#ffffff",  # --bg
        "fg_secondary": "#52525b",  # --fg-secondary
    },
    "dark": {
        "caption": "#17181c",
        "text": "#ededf0",
        "text_inactive": "#8f9199",
        "border": "#26272c",
        "bg": "#101114",
        "fg_secondary": "#adafb7",
    },
}

THEMES = ("light", "dark")

# DWM attribute ids.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
# First Windows 11 build: the colour attributes exist from here on.
COLOR_ATTRS_MIN_BUILD = 22000

CHROME_FILE = "window-chrome.json"

# Bound on how long a request thread waits for the UI thread (milliseconds).
_UI_WAIT_MS = 2000


def colorref(hex_color: str) -> int:
    """``#rrggbb`` to a COLORREF ``0x00BBGGRR``."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def windows_build() -> int | None:
    """The running OS build (kernel32's file build), None off Windows."""
    getver = getattr(sys, "getwindowsversion", None)
    if getver is None:
        return None
    try:
        return int(getver().platform_version[2])
    except Exception:
        return None


def attribute_plan(theme: str, active: bool, build: int | None) -> list[tuple[str, int, int]]:
    """The DWM attributes to set: ``(name, attribute id, value)``. Pure."""
    if build is None or theme not in PALETTE:
        return []
    pal = PALETTE[theme]
    plan: list[tuple[str, int, int]] = [
        ("dark_mode", DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if theme == "dark" else 0)
    ]
    if build >= COLOR_ATTRS_MIN_BUILD:
        plan.append(("border", DWMWA_BORDER_COLOR, colorref(pal["border"])))
        plan.append(("caption", DWMWA_CAPTION_COLOR, colorref(pal["caption"])))
        text_key = "text" if active else "text_inactive"
        plan.append(("text", DWMWA_TEXT_COLOR, colorref(pal[text_key])))
    return plan


def _dwm_set(hwnd: int, attribute: int, value: int) -> int:
    """One ``DwmSetWindowAttribute`` call with a 4-byte value; returns the HRESULT."""
    import ctypes
    from ctypes import wintypes

    dwmapi = ctypes.WinDLL("dwmapi")
    fn = dwmapi.DwmSetWindowAttribute
    fn.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    fn.restype = ctypes.c_long
    val = ctypes.c_uint32(value & 0xFFFFFFFF)
    return int(fn(hwnd, attribute, ctypes.byref(val), 4))


def apply_title_bar(hwnd: int, theme: str, active: bool, build: int | None) -> dict[str, int]:
    """Apply the plan to a window handle; returns each attribute's HRESULT."""
    results: dict[str, int] = {}
    for name, attribute, value in attribute_plan(theme, active, build):
        try:
            results[name] = _dwm_set(hwnd, attribute, value)
        except Exception:
            log.warning("chrome: DwmSetWindowAttribute(%s) raised", name, exc_info=True)
            results[name] = -1
    return results


def os_theme() -> str:
    """The OS app theme (``AppsUseLightTheme``): dark when unreadable or off Windows."""
    try:
        import winreg  # type: ignore[import-not-found]

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            try:
                winreg.CloseKey(key)
            except Exception:
                log.debug("chrome: winreg.CloseKey failed", exc_info=True)
        return "light" if int(value) == 1 else "dark"
    except Exception:
        log.debug("chrome: OS theme detection failed; falling back to dark", exc_info=True)
        return "dark"


# ── Persistence ──────────────────────────────────────────────────────────────


def _chrome_path(data_dir: Any) -> Path:
    return Path(data_dir) / CHROME_FILE


def load_theme(data_dir: Any) -> str | None:
    """The persisted launch theme, or None (missing, corrupt or invalid file)."""
    try:
        data = json.loads(_chrome_path(data_dir).read_text(encoding="utf-8"))
    except Exception:
        return None
    theme = data.get("theme") if isinstance(data, dict) else None
    return theme if theme in THEMES else None


def save_theme(data_dir: Any, theme: str) -> None:
    """Write ``window-chrome.json`` atomically (temp file, then ``os.replace``)."""
    path = _chrome_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".window-chrome-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"theme": theme}, fh)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── State (one lock, state only) ─────────────────────────────────────────────

_lock = threading.Lock()
_file_lock = threading.Lock()  # serialises the theme-file write only; never held with _lock


class _State:
    def __init__(self) -> None:
        self.enabled = False
        self.data_dir: Any = None
        self.persisted: str | None = None
        self.requested: str | None = None
        self.launch_theme: str | None = None
        self.window: Any = None
        self.closing = False
        self.active = True
        self.last_applied: dict[str, Any] | None = None
        self.build: int | None = None
        self.req_seq = 0
        self.applied_seq = 0


_s = _State()


def reset() -> None:
    """Forget everything (each launch starts clean; tests use it too)."""
    global _s
    with _lock:
        _s = _State()


def enable(data_dir: Any) -> None:
    """A desktop session is running in this process: requests persist from now on."""
    with _lock:
        _s.enabled = True
        _s.data_dir = data_dir
        _s.persisted = load_theme(data_dir)


def _native_enabled() -> bool:
    return sys.platform == "win32"


# ── The UI-thread seams ──────────────────────────────────────────────────────


def _invoke_ui(form: Any, fn: Any) -> str:
    """Run ``fn`` on the form's UI thread. Returns ``"done"``, ``"pending"`` or ``"error"``.

    On the UI thread already: a direct call. Elsewhere: ``BeginInvoke`` and a
    bounded wait (``_UI_WAIT_MS``). On a timeout the posted apply still runs
    when the UI thread gets to it. ``EndInvoke`` runs (in a ``finally``) once
    the wait returned True, which releases the async result.
    """
    try:
        from System import Func, Type  # type: ignore[import-not-found]

        if not form.InvokeRequired:
            fn()
            return "done"
        ar = form.BeginInvoke(Func[Type](fn))
    except Exception:
        log.warning("chrome: BeginInvoke failed (form gone?)", exc_info=True)
        return "error"
    try:
        done = bool(ar.AsyncWaitHandle.WaitOne(_UI_WAIT_MS))
    except Exception:
        log.warning("chrome: waiting for the UI thread raised", exc_info=True)
        return "error"
    if not done:
        return "pending"
    try:
        form.EndInvoke(ar)
    except Exception:
        log.warning("chrome: EndInvoke raised", exc_info=True)
        return "error"
    return "done"


def _hwnd_of(form: Any) -> int | None:
    """The form's HWND, read only when it exists and is live; None otherwise."""
    if form.IsDisposed or not form.IsHandleCreated:
        return None
    hwnd = int(form.Handle.ToInt64())
    import ctypes

    if not ctypes.windll.user32.IsWindow(hwnd):
        return None
    return hwnd


def _form_gone(form: Any) -> bool:
    try:
        return bool(form.IsDisposed)
    except Exception:
        return True


def _subscribe_activation(form: Any, on_activated: Any, on_deactivate: Any) -> None:
    form.Activated += on_activated
    form.Deactivate += on_deactivate


# ── Apply ────────────────────────────────────────────────────────────────────


def _record(seq: int, queued_at: float, theme: str, active: bool, results: Any, error: Any) -> None:
    with _lock:
        _s.last_applied = {
            "theme": theme,
            "active": active,
            "results": results,
            "error": error,
            "queued_at": queued_at,
            "applied_at": time.time(),
        }
        if seq > _s.applied_seq:
            _s.applied_seq = seq


def _ui_apply(window: Any, queued_at: float) -> None:
    """The apply, on the UI thread. Catches everything: an exception inside a
    ``BeginInvoke``d delegate would reach ``Application.ThreadException``."""
    theme, active, seq = "dark", True, 0
    try:
        with _lock:
            if _s.closing or _s.window is not window:
                log.info("chrome: apply skipped (window deregistered)")
                return
            theme = _s.requested or _s.launch_theme or "dark"
            active = _s.active
            seq = _s.req_seq
            build = _s.build
        form = window.native
        hwnd = _hwnd_of(form)
        if hwnd is None:
            log.info("chrome: apply skipped (no live window handle)")
            return
        results = apply_title_bar(hwnd, theme, active, build)
        _record(seq, queued_at, theme, active, results, None)
        bad = {k: v for k, v in results.items() if v != 0}
        if bad:
            log.warning("chrome: DwmSetWindowAttribute non-zero HRESULTs: %s", bad)
    except Exception as exc:
        log.warning("chrome: apply raised", exc_info=True)
        try:
            _record(seq, queued_at, theme, active, {}, f"{type(exc).__name__}: {exc}")
        except Exception:
            log.debug("chrome: recording the apply failure raised", exc_info=True)


def _dispatch(window: Any) -> bool | str:
    """Queue an apply for ``window``; ``True`` applied, ``False`` not, ``"pending"``."""
    if not _native_enabled():
        return False
    with _lock:
        if _s.closing or _s.window is not window:
            return False
        theme = _s.requested or _s.launch_theme
        seq = _s.req_seq
    form = window.native
    if _form_gone(form):
        log.info("chrome: apply skipped (form disposed)")
        return False
    queued_at = time.time()
    outcome = _invoke_ui(form, lambda: _ui_apply(window, queued_at))
    if outcome == "pending":
        log.warning("chrome: UI thread did not apply %s within %sms; pending", theme, _UI_WAIT_MS)
        return "pending"
    if outcome != "done":
        return False
    with _lock:
        la = _s.last_applied
        ok = (
            la is not None
            and la.get("error") is None
            and bool(la.get("results"))
            and all(v == 0 for v in la["results"].values())
            and _s.applied_seq >= seq
        )
    return ok


def request(theme: str) -> dict[str, Any]:
    """Record a requested theme (the page's POST). Never raises."""
    window = None
    with _lock:
        _s.requested = theme
        _s.req_seq += 1
        desktop = _s.enabled
        window = _s.window
    if desktop:
        with _file_lock:
            with _lock:
                latest = _s.requested
                write_dir = _s.data_dir
                needed = _s.enabled and latest is not None and _s.persisted != latest
            if needed:
                try:
                    save_theme(write_dir, latest)
                    with _lock:
                        _s.persisted = latest
                except Exception:
                    log.warning("chrome: could not write %s", CHROME_FILE, exc_info=True)
    tinted: bool | str = False
    if window is not None:
        try:
            tinted = _dispatch(window)
        except Exception:
            log.warning("chrome: dispatch raised", exc_info=True)
            tinted = False
    return {"theme": theme, "desktop": desktop, "tinted": tinted}


def register(window: Any, launch_theme: str) -> bool | str:
    """Register the main window (before ``show()``) and apply the theme.

    The requested theme wins over the launch theme when a post beat us here.
    Off Windows this only stores the window and never touches ``native``.
    """
    with _lock:
        _s.window = window
        _s.closing = False
        _s.launch_theme = launch_theme
        _s.build = windows_build()
        _s.req_seq += 1
    if not _native_enabled():
        return False
    try:
        _subscribe_activation(window.native, _on_activated, _on_deactivate)
    except Exception:
        log.warning("chrome: could not subscribe to activation events", exc_info=True)
    try:
        return _dispatch(window)
    except Exception:
        log.warning("chrome: registration apply raised", exc_info=True)
        return False


def _set_active(active: bool) -> None:
    with _lock:
        _s.active = active
        window = _s.window
        gone = _s.closing
    if window is None or gone or not _native_enabled():
        return
    _ui_apply(window, time.time())  # already on the UI thread


def _on_activated(*_: Any) -> None:
    try:
        _set_active(True)
    except Exception:
        log.warning("chrome: Activated handler raised", exc_info=True)


def _on_deactivate(*_: Any) -> None:
    try:
        _set_active(False)
    except Exception:
        log.warning("chrome: Deactivate handler raised", exc_info=True)


def deregister() -> None:
    """Idempotent. Called before every destroy path: later requests apply nothing."""
    with _lock:
        _s.closing = True
        _s.window = None


def apply_splash_border(window: Any, theme: str) -> None:
    """The splash's border colour, from its ``before_show`` (UI thread). Never raises."""
    try:
        if not _native_enabled():
            return
        build = windows_build()
        if build is None or build < COLOR_ATTRS_MIN_BUILD or theme not in PALETTE:
            return
        hwnd = int(window.native.Handle.ToInt64())
        _dwm_set(hwnd, DWMWA_BORDER_COLOR, colorref(PALETTE[theme]["border"]))
    except Exception:
        log.warning("chrome: splash border failed", exc_info=True)


def native_show(window: Any) -> None:
    """Windows-only native show fallback (``form.Show(); form.Activate()`` on the
    UI thread). Raises when it cannot complete."""

    def _show() -> None:
        form = window.native
        form.Show()
        form.Activate()

    outcome = _invoke_ui(window.native, _show)
    if outcome != "done":
        raise RuntimeError(f"native show did not complete ({outcome})")


def snapshot() -> dict[str, Any]:
    """The read-back for ``GET /api/window/chrome``."""
    with _lock:
        registered = _s.window is not None and not _s.closing
        build = _s.build
        return {
            "enabled": _s.enabled,
            "registered": registered,
            "requested": _s.requested,
            "launch_theme": _s.launch_theme,
            "persisted": _s.persisted,
            "active": _s.active,
            "build": build,
            "supported": build is not None and build >= COLOR_ATTRS_MIN_BUILD,
            "pending": registered and _s.req_seq > _s.applied_seq,
            "last_applied": dict(_s.last_applied) if _s.last_applied else None,
        }
