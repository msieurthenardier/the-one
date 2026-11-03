"""Unit tests for the Linux desktop-host helpers (M32 F2 L02): file-existence
GTK/WebKit check, pystray backend choice, tray detection, notifications.

No real D-Bus, X display or notifier is touched: every probe goes through an
injected seam.
"""

from __future__ import annotations

import sys
import threading
import time
import types

import pytest

from the_one.interfaces.desktop import host


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "PYSTRAY_BACKEND",
        "WAYLAND_DISPLAY",
        "DISPLAY",
        "DBUS_SESSION_BUS_ADDRESS",
        "XDG_RUNTIME_DIR",
        "GI_TYPELIB_PATH",
        "APPDIR",
    ):
        monkeypatch.delenv(k, raising=False)


# ── host_has_desktop_gtk ──────────────────────────────────────────────────────


def _fake_fs(monkeypatch, files, dirs=None):
    """files: set of absolute paths that exist; globs resolve against ``dirs``."""
    dirs = dirs or {}
    monkeypatch.setattr(host, "_exists", lambda p: p in files)
    monkeypatch.setattr(host, "_glob", lambda pat: dirs.get(pat, []))
    monkeypatch.setattr(host, "_ldconfig_lists_gtk", lambda: False)
    # `missing_desktop_piece` imports `gi` first; PyGObject comes from the `gui`
    # extra, which a plain `pip install -e '.[all-llms,dev]'` does not install.
    # These tests are about the file probes, so stand in for it.
    monkeypatch.setitem(sys.modules, "gi", types.ModuleType("gi"))


def test_gtk_and_webkit_present(monkeypatch):
    _fake_fs(
        monkeypatch,
        {
            "/usr/lib/x86_64-linux-gnu/libgtk-3.so.0",
            "/usr/lib/x86_64-linux-gnu/girepository-1.0/WebKit2-4.1.typelib",
        },
        {
            "/usr/lib/*-linux-gnu": ["/usr/lib/x86_64-linux-gnu"],
            "/usr/lib/*-linux-gnu/girepository-1.0": ["/usr/lib/x86_64-linux-gnu/girepository-1.0"],
        },
    )
    assert host.host_has_desktop_gtk() is True
    assert host.missing_desktop_piece() is None


def test_webkit_4_0_typelib_counts(monkeypatch):
    _fake_fs(
        monkeypatch,
        {"/usr/lib64/libgtk-3.so.0", "/usr/lib64/girepository-1.0/WebKit2-4.0.typelib"},
        {
            "/usr/lib64": ["/usr/lib64"],
            "/usr/lib64/girepository-1.0": ["/usr/lib64/girepository-1.0"],
        },
    )
    assert host.host_has_desktop_gtk() is True


def test_missing_webkit_reports_webkit(monkeypatch):
    _fake_fs(monkeypatch, {"/usr/lib64/libgtk-3.so.0"}, {"/usr/lib64": ["/usr/lib64"]})
    assert host.host_has_desktop_gtk() is False
    assert host.missing_desktop_piece() == "webkit"


def test_missing_gtk_reports_gtk(monkeypatch):
    _fake_fs(monkeypatch, set())
    assert host.host_has_desktop_gtk() is False
    assert host.missing_desktop_piece() == "gtk"


def test_ldconfig_fallback_finds_gtk(monkeypatch):
    _fake_fs(
        monkeypatch,
        {"/opt/gi/WebKit2-6.0.typelib"},
    )
    monkeypatch.setattr(host, "_ldconfig_lists_gtk", lambda: True)
    monkeypatch.setenv("GI_TYPELIB_PATH", "/opt/gi")
    assert host.host_has_desktop_gtk() is True


def test_gi_typelib_path_excludes_bundle_and_appdir(monkeypatch):
    _fake_fs(
        monkeypatch,
        {
            "/usr/lib64/libgtk-3.so.0",
            "/bundle/gi/WebKit2-4.1.typelib",
            "/app/gi/WebKit2-4.1.typelib",
        },
        {"/usr/lib64": ["/usr/lib64"]},
    )
    monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)
    monkeypatch.setenv("APPDIR", "/app")
    monkeypatch.setenv("GI_TYPELIB_PATH", "/bundle/gi:/app/gi")
    assert host.host_has_desktop_gtk() is False


def test_missing_piece_gi_when_gi_unimportable(monkeypatch):
    monkeypatch.setitem(sys.modules, "gi", None)
    assert host.missing_desktop_piece() == "gi"


def test_display_session(monkeypatch):
    assert host.display_session() is None
    monkeypatch.setenv("DISPLAY", ":0")
    assert host.display_session() == "x11"
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert host.display_session() == "wayland"


# ── choose_pystray_backend ────────────────────────────────────────────────────


def _fake_gi(monkeypatch, available):
    """Install a fake ``gi`` whose require_version accepts only ``available``."""
    gi = types.ModuleType("gi")

    def require_version(ns, ver):
        if (ns, ver) not in available:
            raise ValueError(f"Namespace {ns} not available")

    gi.require_version = require_version
    monkeypatch.setitem(sys.modules, "gi", gi)


def test_explicit_backend_wins(monkeypatch):
    monkeypatch.setenv("PYSTRAY_BACKEND", "dummy")
    assert host.choose_pystray_backend() == "dummy"


def test_ayatana_gives_appindicator(monkeypatch):
    _fake_gi(monkeypatch, {("Gtk", "3.0"), ("AyatanaAppIndicator3", "0.1")})
    assert host.choose_pystray_backend() == "appindicator"


def test_legacy_appindicator_gives_appindicator(monkeypatch):
    _fake_gi(monkeypatch, {("Gtk", "3.0"), ("AppIndicator3", "0.1")})
    assert host.choose_pystray_backend() == "appindicator"


def test_appindicator_without_gtk3_never_appindicator(monkeypatch):
    _fake_gi(monkeypatch, {("AyatanaAppIndicator3", "0.1")})
    monkeypatch.setenv("DISPLAY", ":0")
    assert host.choose_pystray_backend() == "xorg"


def test_x11_neither_gives_gtk(monkeypatch):
    _fake_gi(monkeypatch, {("Gtk", "3.0")})
    monkeypatch.setenv("DISPLAY", ":0")
    assert host.choose_pystray_backend() == "gtk"


def test_x11_no_gtk_gives_xorg(monkeypatch):
    _fake_gi(monkeypatch, set())
    monkeypatch.setenv("DISPLAY", ":0")
    assert host.choose_pystray_backend() == "xorg"


def test_wayland_neither_gives_none(monkeypatch):
    _fake_gi(monkeypatch, {("Gtk", "3.0")})
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert host.choose_pystray_backend() is None


def test_import_error_and_value_error_never_escape(monkeypatch):
    monkeypatch.setitem(sys.modules, "gi", None)  # ImportError on import
    monkeypatch.setenv("DISPLAY", ":0")
    assert host.choose_pystray_backend() == "xorg"
    gi = types.ModuleType("gi")

    def boom(ns, ver):
        raise ImportError("already loaded")

    gi.require_version = boom
    monkeypatch.setitem(sys.modules, "gi", gi)
    assert host.choose_pystray_backend() == "xorg"


def test_choose_never_sets_env(monkeypatch):
    import os

    _fake_gi(monkeypatch, {("Gtk", "3.0"), ("AyatanaAppIndicator3", "0.1")})
    host.choose_pystray_backend()
    assert "PYSTRAY_BACKEND" not in os.environ


# ── detect_tray ───────────────────────────────────────────────────────────────


def test_indicator_host_registered(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(host, "_indicator_probe", lambda: (True, "ok"))
    assert host.detect_tray("appindicator")[0] == "indicator"


def test_watcher_without_host_is_none(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(host, "_indicator_probe", lambda: (False, "no host"))
    assert host.detect_tray("appindicator") == ("none", "no host")


def test_no_session_bus_is_unavailable(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(host, "_indicator_probe", lambda: None)
    mode, reason = host.detect_tray("appindicator")
    assert (mode, reason) == ("unavailable", "no session bus")


def test_xembed_owner(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(host, "_xembed_probe", lambda: (True, "tray"))
    assert host.detect_tray("gtk")[0] == "xembed"
    monkeypatch.setattr(host, "_xembed_probe", lambda: (False, "none"))
    assert host.detect_tray("xorg")[0] == "none"


def test_wayland_never_runs_x11_check(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "w0")
    monkeypatch.setenv("DISPLAY", ":0")

    def boom():
        raise AssertionError("X11 check ran on Wayland")

    monkeypatch.setattr(host, "_xembed_probe", boom)
    assert host.detect_tray("gtk")[0] == "none"


def test_probe_exception_is_unavailable(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")

    def boom():
        raise RuntimeError("bus gone")

    monkeypatch.setattr(host, "_indicator_probe", boom)
    assert host.detect_tray("appindicator")[0] == "unavailable"
    monkeypatch.setattr(host, "_xembed_probe", boom)
    assert host.detect_tray("gtk")[0] == "unavailable"


def test_probe_timeout_is_unavailable(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(host, "_probe_timeout", 0.1)
    release = threading.Event()
    monkeypatch.setattr(host, "_indicator_probe", lambda: release.wait(5))
    t0 = time.monotonic()
    assert host.detect_tray("appindicator")[0] == "unavailable"
    assert time.monotonic() - t0 < 2
    release.set()


def test_no_bus_address_never_connects(monkeypatch, tmp_path):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))  # no bus socket inside

    def boom():
        raise AssertionError("connect attempted")

    monkeypatch.setattr(host, "_connect_session_bus", boom)
    mode, reason = host.detect_tray("appindicator")
    assert mode == "unavailable" and reason == "no session bus"


def test_none_dummy_and_foreign_backends(monkeypatch):
    assert host.detect_tray(None)[0] == "none"
    assert host.detect_tray("dummy")[0] == "none"
    assert host.detect_tray("win32")[0] == "unavailable"
    assert host.detect_tray("darwin")[0] == "unavailable"


def test_no_display_is_unavailable():
    assert host.detect_tray("appindicator")[0] == "unavailable"


# ── send_notification ─────────────────────────────────────────────────────────


def _run_and_wait(summary="s", body="b"):
    before = {t for t in threading.enumerate()}
    host.send_notification(summary, body)
    for t in threading.enumerate():
        if t not in before and t.name == "desktop-notify":
            t.join(5)


def test_notification_prefers_gio(monkeypatch):
    calls = []
    monkeypatch.setattr(host, "_notify_via_gio", lambda s, b: calls.append((s, b)) or True)
    monkeypatch.setattr(host, "_notify_via_cli", lambda s, b: pytest.fail("cli used"))
    _run_and_wait("hi", "there")
    assert calls == [("hi", "there")]


def test_notification_gio_failure_falls_back_and_never_raises(monkeypatch):
    def boom(s, b):
        raise RuntimeError("no bus")

    cli = []
    monkeypatch.setattr(host, "_notify_via_gio", boom)
    monkeypatch.setattr(host, "_notify_via_cli", lambda s, b: cli.append(1) or True)
    _run_and_wait()
    assert cli == [1]


def test_notification_no_gi_no_cli_only_logs(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "gi", None)
    monkeypatch.setitem(sys.modules, "gi.repository", None)
    monkeypatch.setattr(host.shutil, "which", lambda *a, **k: None)
    with caplog.at_level("INFO", logger=host.log.name):
        _run_and_wait("Title", "Body text")
    assert "Body text" in caplog.text


def test_notification_hung_backend_returns_at_once(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(host, "_notify_via_gio", lambda s, b: release.wait(5))
    t0 = time.monotonic()
    host.send_notification("a", "b")
    assert time.monotonic() - t0 < 0.5
    release.set()


def test_cli_uses_sanitized_env_and_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(host.shutil, "which", lambda name, path=None: "/usr/bin/" + name)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/frozen/lib")

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw

    monkeypatch.setattr(host.subprocess, "run", fake_run)
    assert host._notify_via_cli("S", "B") is True
    assert seen["kw"]["timeout"] == 3
    assert "LD_LIBRARY_PATH" not in seen["kw"]["env"]
    assert seen["cmd"][0].endswith("notify-send")
