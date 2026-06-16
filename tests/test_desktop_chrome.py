"""Unit tests for the window-chrome js_api (_WindowApi) added in M15 F7 Leg 2.

Tests cover:
- _WindowApi.minimize() calls window.minimize()
- _WindowApi.toggle_maximize() toggles maximize / restore and tracks _is_maximized
- _WindowApi.close() routes to the shared _close_to_tray() path when tray active
- _WindowApi.close() routes to destroy + _really_quit when tray absent (_icon is None)
- _on_closing() hides when _close_to_tray() succeeds (unchanged path via shared method)

webview is NOT installed on this host — mocked via sys.modules injection (same
pattern as test_desktop_shell.py).
"""

from __future__ import annotations

import importlib
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def pystray_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a MagicMock for 'pystray' into sys.modules."""
    mock = MagicMock()
    monkeypatch.setitem(sys.modules, "pystray", mock)
    return mock


@pytest.fixture()
def pil_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a MagicMock for 'PIL' and 'PIL.Image' into sys.modules."""
    pil = MagicMock()
    monkeypatch.setitem(sys.modules, "PIL", pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", pil.Image)
    return pil


@pytest.fixture()
def webview_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a MagicMock for 'webview' into sys.modules."""
    mock = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", mock)
    return mock


@pytest.fixture()
def shell_module(
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    webview_mock: MagicMock,
) -> Any:
    """Return a freshly-reloaded desktop.shell module with all GUI mocks in place."""
    import the_one.interfaces.desktop.shell as shell_mod

    importlib.reload(shell_mod)
    return shell_mod


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_api_with_window(shell_module: Any) -> tuple[Any, MagicMock]:
    """Return (_WindowApi instance, mock_window) with the window wired up."""
    from the_one.interfaces.desktop.shell import DesktopSession, _WindowApi

    session = DesktopSession()
    api = session._window_api
    mock_window = MagicMock()
    api._window = mock_window
    shell_module._desktop_window = mock_window
    return api, mock_window


# ── _WindowApi.minimize ───────────────────────────────────────────────────────


def test_api_minimize_calls_window_minimize(shell_module: Any) -> None:
    """minimize() calls window.minimize() exactly once."""
    api, mock_window = _make_api_with_window(shell_module)
    api.minimize()
    mock_window.minimize.assert_called_once()


def test_api_minimize_noop_when_window_is_none(shell_module: Any) -> None:
    """minimize() is a no-op when _window is None (no crash)."""
    from the_one.interfaces.desktop.shell import DesktopSession

    session = DesktopSession()
    api = session._window_api
    # _window is None — must not raise
    api.minimize()


# ── _WindowApi.toggle_maximize ────────────────────────────────────────────────


def test_api_toggle_maximize_first_call_maximizes(shell_module: Any) -> None:
    """First toggle_maximize() call calls window.maximize() and sets _is_maximized=True."""
    api, mock_window = _make_api_with_window(shell_module)
    assert api._is_maximized is False

    api.toggle_maximize()

    mock_window.maximize.assert_called_once()
    mock_window.restore.assert_not_called()
    assert api._is_maximized is True


def test_api_toggle_maximize_second_call_restores(shell_module: Any) -> None:
    """Second toggle_maximize() call calls window.restore() and sets _is_maximized=False."""
    api, mock_window = _make_api_with_window(shell_module)

    api.toggle_maximize()  # → maximize
    api.toggle_maximize()  # → restore

    mock_window.maximize.assert_called_once()
    mock_window.restore.assert_called_once()
    assert api._is_maximized is False


def test_api_toggle_maximize_three_calls(shell_module: Any) -> None:
    """Three toggle calls: maximize → restore → maximize."""
    api, mock_window = _make_api_with_window(shell_module)

    api.toggle_maximize()  # maximize
    api.toggle_maximize()  # restore
    api.toggle_maximize()  # maximize again

    assert mock_window.maximize.call_count == 2
    assert mock_window.restore.call_count == 1
    assert api._is_maximized is True


def test_api_toggle_maximize_noop_when_window_is_none(shell_module: Any) -> None:
    """toggle_maximize() is a no-op when _window is None (no crash)."""
    from the_one.interfaces.desktop.shell import DesktopSession

    session = DesktopSession()
    api = session._window_api
    api.toggle_maximize()  # must not raise


# ── _WindowApi.close → close-to-tray when tray active ────────────────────────


def _make_splash_mock_chrome() -> MagicMock:
    """Return a mock splash window whose events.shown.wait() is a no-op."""
    splash = MagicMock()
    splash.events.shown.wait.return_value = True
    return splash


def test_api_close_hides_window_when_tray_active(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close() routes to close-to-tray path: hides the window when tray is active.

    Adapted for Leg 4 splash restructure: create_window is now called twice (splash
    + main window inside _boot).  The test captures js_api from the MAIN window call
    by filtering out None (the splash has no js_api).  _boot is extracted from
    webview.start() and invoked so the main-window creation and tray wiring run.
    """
    import the_one.interfaces.desktop.notice as notice_mod
    import the_one.interfaces.desktop.tray as tray_mod

    # Pre-mark notice to avoid the notify path.
    marker = tmp_path / ".close_to_tray_notice_shown"
    monkeypatch.setattr(notice_mod, "_marker_path", lambda: marker)
    marker.touch()

    mock_splash = _make_splash_mock_chrome()
    mock_window = MagicMock()
    mock_icon = MagicMock()
    monkeypatch.setattr(shell_module.settings, "data_dir", tmp_path)

    # Wire a real session so we can grab the _window_api after run.
    captured_api: list = []

    def _capture_create_window(*args, **kwargs):
        api = kwargs.get("js_api")
        if api is not None:
            captured_api.append(api)
        # Return splash for first call (no js_api), mock_window for second.
        return mock_splash if api is None else mock_window

    webview_mock.create_window.side_effect = _capture_create_window
    monkeypatch.setattr(tray_mod, "build_tray", lambda **kw: mock_icon)

    with patch.object(shell_module, "_select_port", return_value=(8484, False)):
        with patch.object(shell_module, "_webview_available", return_value=True):
            with patch.object(shell_module, "_graceful_shutdown"):
                with patch.object(shell_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server") as mock_srv_cls:
                            mock_srv_cls.return_value = MagicMock()
                            with patch("threading.Thread") as mock_thr_cls:
                                mock_thr_cls.return_value = MagicMock()
                                shell_module.run_desktop()

    # Invoke _boot so the main-window creation path runs.
    _boot = webview_mock.start.call_args.args[0]
    _boot(mock_splash)

    assert len(captured_api) == 1, "create_window must be called once with js_api (main window)"
    api = captured_api[0]

    # Calling close() on the api should hide the window (close-to-tray path).
    api.close()
    mock_window.hide.assert_called_once()
    # _really_quit must NOT be set (we're hiding, not destroying).
    assert shell_module._really_quit is False


# ── _WindowApi.close → destroy when tray absent (_icon is None) ──────────────


def test_api_close_destroys_when_tray_absent(
    shell_module: Any,
    webview_mock: MagicMock,
    pystray_mock: MagicMock,
    pil_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close() calls destroy() + sets _really_quit when _icon is None (no tray).

    When the tray failed to start, hiding into a non-existent tray would make
    the app unrecoverable.  The close() must fall back to a real destroy.

    Adapted for Leg 4 splash restructure: _boot is extracted from webview.start()
    and invoked so tray wiring (which now runs inside _boot) is exercised.
    """
    import the_one.interfaces.desktop.tray as tray_mod

    mock_splash = _make_splash_mock_chrome()
    mock_window = MagicMock()
    monkeypatch.setattr(shell_module.settings, "data_dir", tmp_path)

    captured_api: list = []

    def _capture_create_window(*args, **kwargs):
        api = kwargs.get("js_api")
        if api is not None:
            captured_api.append(api)
        return mock_splash if api is None else mock_window

    webview_mock.create_window.side_effect = _capture_create_window

    # Make build_tray raise — tray absent, _on_closing not registered.
    monkeypatch.setattr(
        tray_mod, "build_tray", MagicMock(side_effect=RuntimeError("no backend"))
    )

    with patch.object(shell_module, "_select_port", return_value=(8484, False)):
        with patch.object(shell_module, "_webview_available", return_value=True):
            with patch.object(shell_module, "_graceful_shutdown"):
                with patch.object(shell_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server") as mock_srv_cls:
                            mock_srv_cls.return_value = MagicMock()
                            with patch("threading.Thread") as mock_thr_cls:
                                mock_thr_cls.return_value = MagicMock()
                                shell_module.run_desktop()

    # Invoke _boot so tray wiring (build_tray raises → tray absent path) runs.
    _boot = webview_mock.start.call_args.args[0]
    _boot(mock_splash)

    assert len(captured_api) == 1
    api = captured_api[0]

    # _icon is None (tray failed) — close() must destroy and set _really_quit.
    api.close()
    mock_window.hide.assert_not_called()
    mock_window.destroy.assert_called_once()
    assert shell_module._really_quit is True
