"""Launcher-core unit tests for the_one/interfaces/desktop/shell.py.

webview is NOT installed on this host — it is mocked via sys.modules injection
so the tests exercise the launcher logic without any GUI dependency.

Do NOT import webview at the module top level.
"""

from __future__ import annotations

import socket
import sys
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────


def _free_port() -> int:
    """Return an OS-allocated free TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ── trivial ASGI app for the readiness-poll success test ─────────────────────


async def _trivial_asgi(scope, receive, send) -> None:
    """A bare ASGI app that returns HTTP 200 at /api/info (and 404 elsewhere)."""
    if scope["type"] != "http":
        return
    path = scope.get("path", "")
    if path == "/api/info":
        body = b'{"version":"0","base_prompt":""}'
        status = 200
    else:
        body = b"not found"
        status = 404
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send({"type": "http.response.body", "body": body})


# ── webview mock fixture ──────────────────────────────────────────────────────


@pytest.fixture()
def webview_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Inject a MagicMock for 'webview' into sys.modules.

    The launcher's ``run()`` does ``import webview`` lazily inside the
    function body.  Inserting the mock before the call means the lazy
    import resolves to the mock, not a real webview (which isn't installed).
    The fixture cleans up after itself via monkeypatch.
    """
    mock = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", mock)
    return mock


# ── _wait_until_serving ───────────────────────────────────────────────────────


def test_wait_until_serving_returns_when_server_ready() -> None:
    """_wait_until_serving returns once the server answers 200 at /api/info."""
    import uvicorn

    from the_one.interfaces.desktop.shell import _wait_until_serving

    port = _free_port()
    config = uvicorn.Config(_trivial_asgi, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        # Give the server a moment to bind, then poll (timeout = 15s)
        _wait_until_serving("127.0.0.1", port, timeout=15.0)
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)


def test_wait_until_serving_raises_on_timeout() -> None:
    """_wait_until_serving raises RuntimeError when nothing is listening."""
    from the_one.interfaces.desktop.shell import _wait_until_serving

    port = _free_port()  # nothing listening on this port
    with pytest.raises(RuntimeError, match="did not become ready"):
        _wait_until_serving("127.0.0.1", port, timeout=0.2)


# ── _graceful_shutdown ────────────────────────────────────────────────────────


def test_graceful_shutdown_sets_should_exit_and_joins() -> None:
    """_graceful_shutdown sets server.should_exit=True and calls thread.join."""
    from the_one.interfaces.desktop.shell import _graceful_shutdown

    fake_server: Any = MagicMock()
    fake_thread: Any = MagicMock()

    _graceful_shutdown(fake_server, fake_thread, timeout=5.0)

    assert fake_server.should_exit is True
    fake_thread.join.assert_called_once_with(timeout=5.0)


def test_graceful_shutdown_noop_with_server_none() -> None:
    """_graceful_shutdown returns immediately (no-op) when server is None."""
    from the_one.interfaces.desktop.shell import _graceful_shutdown

    fake_thread: Any = MagicMock()

    # Must not raise, and must not touch thread at all
    _graceful_shutdown(None, fake_thread)

    fake_thread.join.assert_not_called()


# ── _select_port ──────────────────────────────────────────────────────────────


def test_select_port_case_a_free_port() -> None:
    """_select_port returns (configured_port, False) when nothing is listening."""
    import httpx

    from the_one.interfaces.desktop.shell import _select_port

    port = _free_port()  # nothing listening — port is free

    # Patch httpx so the /api/info probe raises ConnectError (nothing there)
    with patch.object(httpx, "get", side_effect=httpx.ConnectError("refused")):
        result_port, is_ours = _select_port("127.0.0.1", port, retries=1, delay=0.0)

    assert result_port == port
    assert is_ours is False


def test_select_port_case_b_our_instance() -> None:
    """_select_port returns (configured_port, True) when our the-one answers /api/info."""
    import httpx

    from the_one import __version__
    from the_one.interfaces.desktop.shell import _select_port

    port = _free_port()

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"version": __version__, "base_prompt": ""}

    with patch.object(httpx, "get", return_value=fake_response):
        result_port, is_ours = _select_port("127.0.0.1", port, retries=1, delay=0.0)

    assert result_port == port
    assert is_ours is True


def test_select_port_case_c_foreign_process() -> None:
    """_select_port returns a bind-0 free port with False when a foreign process holds the port."""
    import httpx

    from the_one.interfaces.desktop.shell import _select_port

    # Bind a socket to simulate a foreign process holding the port
    occupied_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied_sock.bind(("127.0.0.1", 0))
    occupied_sock.listen(1)
    occupied_port = occupied_sock.getsockname()[1]

    try:
        # Patch httpx to return a non-the-one response (foreign process)
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"version": "9999.0.0", "base_prompt": ""}

        with patch.object(httpx, "get", return_value=fake_response):
            result_port, is_ours = _select_port("127.0.0.1", occupied_port, retries=1, delay=0.0)
    finally:
        occupied_sock.close()

    # Should have picked a different free port
    assert result_port != occupied_port
    assert is_ours is False


# ── _webview_available ────────────────────────────────────────────────────────


def test_webview_available_returns_true_on_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """_webview_available returns True on win32 without any gi check."""
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(sys, "platform", "win32")
    # Remove gi from sys.modules to confirm it's never imported
    monkeypatch.delitem(sys.modules, "gi", raising=False)

    assert launcher_module._webview_available() is True


def test_webview_available_returns_true_on_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    """_webview_available returns True on darwin without any gi check."""
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delitem(sys.modules, "gi", raising=False)

    assert launcher_module._webview_available() is True


def test_webview_available_returns_false_when_gi_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_webview_available returns False on Linux when gi is not installed."""
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(sys, "platform", "linux")
    # Simulate gi not installed: inject a module that raises ImportError on import
    monkeypatch.setitem(sys.modules, "gi", None)  # None entry → ImportError on import

    assert launcher_module._webview_available() is False


def test_webview_available_returns_false_when_webkit_typelib_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_webview_available returns False on Linux when gi is present but WebKit2 typelib missing."""
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(sys, "platform", "linux")

    fake_gi = MagicMock()
    fake_gi.require_version.side_effect = ValueError("no typelib")
    monkeypatch.setitem(sys.modules, "gi", fake_gi)

    assert launcher_module._webview_available() is False


def test_webview_available_returns_true_when_webkit_typelib_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_webview_available returns True on Linux when gi + WebKit2 typelib present."""
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(sys, "platform", "linux")

    fake_gi = MagicMock()
    fake_gi.require_version.return_value = None  # success (no exception)
    monkeypatch.setitem(sys.modules, "gi", fake_gi)

    assert launcher_module._webview_available() is True


# ── run() ─────────────────────────────────────────────────────────────────────


def test_run_calls_create_window_start_and_graceful_shutdown(
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() creates a window, starts webview, and calls _graceful_shutdown."""
    import the_one.interfaces.desktop.shell as launcher_module

    # Redirect data_dir so the webview-profile mkdir lands in a tmp dir, not the
    # real per-user data location.
    monkeypatch.setattr(launcher_module.settings, "data_dir", tmp_path)

    with patch.object(launcher_module, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_module, "_webview_available", return_value=True):
            with patch.object(launcher_module, "_graceful_shutdown") as mock_shutdown:
                with patch.object(launcher_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server") as mock_server_cls:
                            mock_server = MagicMock()
                            mock_server_cls.return_value = mock_server
                            with patch("threading.Thread") as mock_thread_cls:
                                mock_thread = MagicMock()
                                mock_thread_cls.return_value = mock_thread
                                launcher_module.run_desktop()

    # webview.create_window was called once with the expected title
    webview_mock.create_window.assert_called_once()
    call_args = webview_mock.create_window.call_args
    assert call_args.args[0] == "GleepGlorp AI"
    # Native frame (title bar), no browser chrome — DD8.
    assert call_args.kwargs.get("frameless") is False

    # webview.start was called (blocks main thread in production; is a no-op mock here)
    webview_mock.start.assert_called_once()
    # Persistence config (M15 F5 post-landing fix): start() must run with a
    # NON-private profile pinned to a stable per-user storage_path, so localStorage
    # (e.g. the theme preference) survives restarts/reinstalls. Default
    # private_mode=True would drop it every launch.
    start_kwargs = webview_mock.start.call_args.kwargs
    assert start_kwargs.get("private_mode") is False
    assert start_kwargs.get("storage_path") == str(tmp_path / "webview")
    assert (tmp_path / "webview").is_dir()

    # _graceful_shutdown was called exactly once
    mock_shutdown.assert_called_once()


def test_run_case_b_posts_focus_and_returns_without_window(
    webview_mock: MagicMock,
) -> None:
    """run() case (b): is_ours=True → POSTs /api/window/focus and returns; no window created."""
    import httpx

    from the_one.config import settings
    import the_one.interfaces.desktop.shell as launcher_module

    expected_url = f"http://{settings.host}:{settings.port}/api/window/focus"

    with patch.object(launcher_module, "_select_port", return_value=(settings.port, True)):
        with patch.object(httpx, "post") as mock_post:
            with patch("uvicorn.Server") as mock_server_cls:
                launcher_module.run_desktop()

    # No uvicorn.Server should have been constructed (returned before server start)
    mock_server_cls.assert_not_called()

    # No window created — returned before create_window
    webview_mock.create_window.assert_not_called()

    # httpx.post called with the focus URL; no Origin header (header-less loopback)
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args.args[0] == expected_url
    # Verify no Origin header was passed (default: no headers kwarg, or empty headers)
    headers = call_args.kwargs.get("headers", {})
    assert "origin" not in {k.lower() for k in headers}


def test_run_fallback_calls_webbrowser_open_and_joins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() with no WebView backend: webbrowser.open called; SIGINT handler installed; joined."""
    import signal as signal_mod
    import webbrowser as webbrowser_mod

    from the_one.config import settings
    import the_one.interfaces.desktop.shell as launcher_module

    expected_url = f"http://{settings.host}:{settings.port}/"

    mock_thread = MagicMock()
    mock_server = MagicMock()

    with patch.object(launcher_module, "_select_port", return_value=(settings.port, False)):
        with patch.object(launcher_module, "_webview_available", return_value=False):
            with patch.object(launcher_module, "_graceful_shutdown"):
                with patch.object(launcher_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server", return_value=mock_server):
                            with patch("threading.Thread", return_value=mock_thread):
                                with patch.object(webbrowser_mod, "open") as mock_open:
                                    with patch.object(signal_mod, "signal") as mock_signal:
                                        # Make thread.join a no-op so the test doesn't block
                                        mock_thread.join.return_value = None
                                        launcher_module.run_desktop()

    # webbrowser.open called with the local URL
    mock_open.assert_called_once_with(expected_url)

    # signal.signal was called to install SIGINT handler
    mock_signal.assert_called_once()
    assert mock_signal.call_args.args[0] == signal_mod.SIGINT

    # thread.join was called (blocks until SIGINT → drain)
    mock_thread.join.assert_called_once()


def test_run_case_b_is_ours_posts_focus_and_returns_no_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() case (b): is_ours=True → POSTs focus and returns; no browser, no server."""
    import httpx
    import webbrowser as webbrowser_mod

    from the_one.config import settings
    import the_one.interfaces.desktop.shell as launcher_module

    with patch.object(launcher_module, "_select_port", return_value=(settings.port, True)):
        with patch.object(httpx, "post") as mock_post:
            with patch("uvicorn.Server") as mock_server_cls:
                with patch.object(webbrowser_mod, "open") as mock_open:
                    launcher_module.run_desktop()

    # No server constructed, no browser opened
    mock_server_cls.assert_not_called()
    mock_open.assert_not_called()

    # Focus POST was issued
    mock_post.assert_called_once()


def test_run_raises_system_exit_when_webview_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() raises SystemExit with a helpful message when webview is absent."""
    # Ensure webview is NOT in sys.modules (simulate missing [gui] extra)
    monkeypatch.delitem(sys.modules, "webview", raising=False)

    # If webview is installed on this host, the test can't meaningfully run;
    # but we also need to ensure the lazy import inside run() raises ImportError.
    # We do that by monkeypatching the built-in __import__ for "webview" only.
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__  # type: ignore[attr-defined]

    def _import_raiser(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "webview":
            raise ImportError("No module named 'webview'")
        return real_import(name, *args, **kwargs)

    # Reload the module fresh to avoid any cached module-level state
    import importlib

    import the_one.interfaces.desktop.shell as launcher_mod

    importlib.reload(launcher_mod)

    # Post-refactor: import webview is inside `if _webview_available():` — patch
    # _webview_available to return True so the import is actually reached.
    with patch.object(launcher_mod, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_mod, "_webview_available", return_value=True):
            with patch.object(launcher_mod, "_wait_until_serving"):
                with patch("the_one.interfaces.web.app.app", MagicMock()):
                    with patch("uvicorn.Server", return_value=MagicMock()):
                        with patch("threading.Thread", return_value=MagicMock()):
                            with patch("builtins.__import__", side_effect=_import_raiser):
                                with pytest.raises(SystemExit, match="pywebview is not installed"):
                                    launcher_mod.run_desktop()
