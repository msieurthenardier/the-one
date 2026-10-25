"""Linux desktop-host facts: GTK/WebKit presence, tray backend choice, tray
detection and desktop notifications (M32 F2 L02; flight DD3, DD11, DD14).

Everything here is cheap and defensive.  Nothing imports ``pystray`` (its
package ``__init__`` selects a backend at import time and can raise
``ValueError`` or open an X display), nothing ``dlopen``s GTK, and every
``gi``/``Xlib`` import is lazy.  The file-system, D-Bus and X seams are
module-level callables so unit tests need no real bus or display.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
import sys
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)

_GTK_SONAME = "libgtk-3.so.0"
_GTK_DIRS = (
    "/usr/lib/*-linux-gnu",
    "/lib/*-linux-gnu",
    "/usr/lib64",
    "/lib64",
    "/usr/lib",
    "/usr/local/lib",
)
_WEBKIT_TYPELIBS = ("WebKit2-4.1.typelib", "WebKit2-4.0.typelib", "WebKit2-6.0.typelib")
_TYPELIB_DIRS = (
    "/usr/lib/*-linux-gnu/girepository-1.0",
    "/usr/lib64/girepository-1.0",
    "/usr/lib/girepository-1.0",
)
_LDCONFIG = "/sbin/ldconfig"

# ── seams (tests monkeypatch these) ───────────────────────────────────────────
_glob: Callable[[str], list[str]] = glob.glob
_exists: Callable[[str], bool] = os.path.exists
_probe_timeout = 3.0


def _ldconfig_lists_gtk() -> bool:
    try:
        out = subprocess.run(
            [_LDCONFIG, "-p"], capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return _GTK_SONAME in out


def display_session() -> str | None:
    """``"wayland"``, ``"x11"`` or ``None`` (no display session)."""
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return None


def _host_has_gtk() -> bool:
    for pattern in _GTK_DIRS:
        for d in _glob(pattern):
            if _exists(os.path.join(d, _GTK_SONAME)):
                return True
    return _ldconfig_lists_gtk()


def _excluded_typelib_dir(path: str) -> bool:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle and os.path.abspath(path).startswith(os.path.abspath(bundle)):
        return True
    appdir = os.environ.get("APPDIR")
    return bool(appdir and os.path.abspath(path).startswith(os.path.abspath(appdir)))


def _host_has_webkit() -> bool:
    dirs: list[str] = []
    for pattern in _TYPELIB_DIRS:
        dirs.extend(_glob(pattern))
    for d in os.environ.get("GI_TYPELIB_PATH", "").split(os.pathsep):
        if d and not _excluded_typelib_dir(d):
            dirs.append(d)
    return any(_exists(os.path.join(d, name)) for d in dirs for name in _WEBKIT_TYPELIBS)


def host_has_desktop_gtk() -> bool:
    """True when the HOST (not the bundle) has GTK 3 and a WebKit2 typelib.

    A pure file-existence check: loads, imports and spawns nothing (except the
    absolute-path ``ldconfig -p`` fallback when no standard directory matched).
    """
    return _host_has_gtk() and _host_has_webkit()


def missing_desktop_piece() -> str | None:
    """Which piece is missing: ``"gi"``, ``"gtk"``, ``"webkit"`` or ``None``."""
    try:
        import gi  # noqa: F401
    except ImportError:
        return "gi"
    if not _host_has_gtk():
        return "gtk"
    if not _host_has_webkit():
        return "webkit"
    return None


# ── pystray backend choice ────────────────────────────────────────────────────


def _require(namespace: str, version: str) -> bool:
    try:
        import gi

        gi.require_version(namespace, version)
        return True
    except (ValueError, ImportError):
        return False


def choose_pystray_backend() -> str | None:
    """Pick a working pystray backend name (never sets ``PYSTRAY_BACKEND``)."""
    explicit = os.environ.get("PYSTRAY_BACKEND")
    if explicit:
        return explicit
    gtk3 = _require("Gtk", "3.0")
    if gtk3 and (_require("AyatanaAppIndicator3", "0.1") or _require("AppIndicator3", "0.1")):
        return "appindicator"
    if display_session() == "x11":
        return "gtk" if gtk3 else "xorg"
    return None


# ── session bus ───────────────────────────────────────────────────────────────


def _bus_address() -> str | None:
    addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if addr:
        return addr
    rt = os.environ.get("XDG_RUNTIME_DIR")
    if rt:
        sock = os.path.join(rt, "bus")
        if _exists(sock):
            return "unix:path=" + sock
    return None


def _connect_session_bus() -> Any | None:
    """Connect to the session bus without autolaunch; None when there is none."""
    address = _bus_address()
    if address is None:
        return None
    from gi.repository import Gio

    flags = (
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
    )
    return Gio.DBusConnection.new_for_address_sync(address, flags, None, None)


def _indicator_host_registered(conn: Any) -> tuple[bool, str]:
    """(registered, reason) for the StatusNotifier watcher on ``conn``."""
    from gi.repository import Gio, GLib

    reply = conn.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "NameHasOwner",
        GLib.Variant("(s)", ("org.kde.StatusNotifierWatcher",)),
        GLib.VariantType("(b)"),
        Gio.DBusCallFlags.NONE,
        1000,
        None,
    )
    if not reply.unpack()[0]:
        return False, "no StatusNotifier watcher on the session bus"
    prop = conn.call_sync(
        "org.kde.StatusNotifierWatcher",
        "/StatusNotifierWatcher",
        "org.freedesktop.DBus.Properties",
        "Get",
        GLib.Variant("(ss)", ("org.kde.StatusNotifierWatcher", "IsStatusNotifierHostRegistered")),
        GLib.VariantType("(v)"),
        Gio.DBusCallFlags.NONE,
        1000,
        None,
    )
    if prop.unpack()[0]:
        return True, "StatusNotifier host registered"
    return False, "no StatusNotifier host registered (no tray extension)"


def _xembed_tray_owned() -> tuple[bool, str]:
    from Xlib import display as xdisplay

    d = xdisplay.Display()
    try:
        screen = d.get_default_screen()
        atom = d.intern_atom("_NET_SYSTEM_TRAY_S%d" % screen)
        owner = d.get_selection_owner(atom)
        owned = owner != 0 and getattr(owner, "id", owner) != 0
    finally:
        d.close()
    if owned:
        return True, "X11 system tray present"
    return False, "no X11 system tray on this display"


# Seams for detect_tray: (bus connect + indicator probe) and X probe.


def _default_indicator_probe() -> tuple[bool, str] | None:
    """None means no session bus."""
    if _bus_address() is None:
        return None
    conn = _connect_session_bus()
    if conn is None:
        return None
    try:
        return _indicator_host_registered(conn)
    finally:
        try:
            conn.close_sync(None)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass


_indicator_probe: Callable[[], tuple[bool, str] | None] = _default_indicator_probe
_xembed_probe: Callable[[], tuple[bool, str]] = _xembed_tray_owned


def _bounded(fn: Callable[[], Any]) -> tuple[bool, Any]:
    """Run ``fn`` in a daemon thread; (finished_ok, value-or-exception)."""
    box: dict[str, Any] = {}

    def work() -> None:
        try:
            box["v"] = fn()
        except BaseException as exc:  # noqa: BLE001 - reported, never raised
            box["e"] = exc

    t = threading.Thread(target=work, daemon=True, name="host-probe")
    t.start()
    t.join(_probe_timeout)
    if t.is_alive():
        return False, TimeoutError("probe timed out")
    if "e" in box:
        return False, box["e"]
    return True, box.get("v")


def detect_tray(backend: str | None) -> tuple[str, str]:
    """Return ``(mode, reason)``: mode is indicator, xembed, none or unavailable."""
    if backend is None:
        return "none", "no tray backend for this session"
    if backend == "dummy":
        return "none", "dummy tray backend"
    if backend in ("win32", "darwin"):
        return "unavailable", f"{backend} tray backend on Linux"
    session = display_session()
    if session is None:
        return "unavailable", "no display session"
    if backend == "appindicator":
        ok, val = _bounded(lambda: _indicator_probe())
        if not ok:
            return "unavailable", f"tray probe failed ({type(val).__name__})"
        if val is None:
            return "unavailable", "no session bus"
        registered, reason = val
        return ("indicator" if registered else "none"), reason
    # gtk / xorg: XEmbed, X11 only
    if session != "x11":
        return "none", "XEmbed tray needs an X11 session"
    ok, val = _bounded(lambda: _xembed_probe())
    if not ok:
        return "unavailable", f"X display unreachable ({type(val).__name__})"
    owned, reason = val
    return ("xembed" if owned else "none"), reason


# ── notifications ─────────────────────────────────────────────────────────────

_notify_timeout_ms = 2000


def _notify_via_gio(summary: str, body: str) -> bool:
    """Synchronous Notify call; True when sent, False when ``gi`` is unusable."""
    try:
        from gi.repository import Gio, GLib
    except ImportError:
        return False
    conn = _connect_session_bus()
    if conn is None:
        raise RuntimeError("no session bus")
    conn.call_sync(
        "org.freedesktop.Notifications",
        "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications",
        "Notify",
        GLib.Variant(
            "(susssasa{sv}i)",
            ("GleepGlorp AI", 0, "", summary, body, [], {}, -1),
        ),
        GLib.VariantType("(u)"),
        Gio.DBusCallFlags.NONE,
        _notify_timeout_ms,
        None,
    )
    return True


def _notify_via_cli(summary: str, body: str) -> bool:
    from the_one.platform.env import _build_subprocess_env

    env = _build_subprocess_env()
    for key in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    exe = shutil.which("notify-send", path=env.get("PATH"))
    if exe:
        cmd = [exe, "-a", "GleepGlorp AI", summary, body]
    else:
        gdbus = shutil.which("gdbus", path=env.get("PATH"))
        if not gdbus:
            return False
        cmd = [
            gdbus, "call", "--session",
            "--dest", "org.freedesktop.Notifications",
            "--object-path", "/org/freedesktop/Notifications",
            "--method", "org.freedesktop.Notifications.Notify",
            "GleepGlorp AI", "0", "", summary, body, "[]", "{}", "-1",
        ]  # fmt: skip
    subprocess.run(cmd, env=env, capture_output=True, timeout=3, check=False)
    return True


def send_notification(summary: str, body: str) -> None:
    """Fire-and-forget desktop notification.  Never raises, never blocks."""

    def work() -> None:
        try:
            try:
                if _notify_via_gio(summary, body):
                    return
            except Exception:  # noqa: BLE001
                log.debug("gio notification failed", exc_info=True)
            if _notify_via_cli(summary, body):
                return
            log.info("%s: %s", summary, body)
        except Exception:  # noqa: BLE001
            log.debug("notification failed", exc_info=True)

    try:
        threading.Thread(target=work, daemon=True, name="desktop-notify").start()
    except Exception:  # noqa: BLE001
        log.debug("could not start notification thread", exc_info=True)
