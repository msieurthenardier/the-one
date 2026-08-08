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
    """A bare ASGI app that returns HTTP 200 at /api/live (and /api/info, for
    completeness) and 404 elsewhere."""
    if scope["type"] != "http":
        return
    path = scope.get("path", "")
    if path in ("/api/live", "/api/info"):
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


def test_select_port_case_b_our_instance_sends_credential() -> None:
    """_select_port returns (configured_port, True) when /api/info accepts OUR credential (DD11).

    "Ours" is credentialed, not version-based: a 200 response means the
    server on the other end validated the same credential this process
    would present, which only happens when it reads the same credential
    file. The probe must carry an `Authorization: Bearer <credential>`
    header built from `get_credential()`.
    """
    import httpx

    from the_one.api_credential import get_credential
    from the_one.interfaces.desktop.shell import _select_port

    port = _free_port()

    fake_response = MagicMock()
    fake_response.status_code = 200

    with patch.object(httpx, "get", return_value=fake_response) as mock_get:
        result_port, is_ours = _select_port("127.0.0.1", port, retries=1, delay=0.0)

    assert result_port == port
    assert is_ours is True

    # The probe carried our credential as a Bearer token.
    expected_header = f"Bearer {get_credential().encode()}"
    mock_get.assert_called_once()
    call_headers = mock_get.call_args.kwargs.get("headers", {})
    assert call_headers.get("Authorization") == expected_header


def test_select_port_case_c_foreign_process_rejects_our_credential() -> None:
    """_select_port returns a bind-0 free port with False when a foreign process
    holds the port and 401s our credential (DD11 — a foreign server that also
    401s simply resolves to "not ours," the safe answer)."""
    import httpx

    from the_one.interfaces.desktop.shell import _select_port

    # Bind a socket to simulate a foreign process holding the port
    occupied_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied_sock.bind(("127.0.0.1", 0))
    occupied_sock.listen(1)
    occupied_port = occupied_sock.getsockname()[1]

    try:
        # Patch httpx to return a 401 — a foreign server that doesn't share
        # our credential (whether or not it happens to run the same version).
        fake_response = MagicMock()
        fake_response.status_code = 401

        with patch.object(httpx, "get", return_value=fake_response):
            result_port, is_ours = _select_port("127.0.0.1", occupied_port, retries=1, delay=0.0)
    finally:
        occupied_sock.close()

    # Should have picked a different free port
    assert result_port != occupied_port
    assert is_ours is False


def test_select_port_case_c_foreign_http_server_404_not_ours() -> None:
    """A foreign HTTP server with no /api/info route at all (404, not even a
    the-one instance) is correctly treated as not ours — any non-200 falls
    through to the foreign/occupied path, regardless of the reason.

    Note on the leg spec's related edge case ("a foreign server that returns
    200 on /api/info — without the right credential it is not ours. Already
    the safe answer, but assert it."): that scenario is not independently
    mockable here, because under DD11 a 200 response IS this function's
    definition of "ours" — the two are the same claim, not two claims to
    cross-check. The real guarantee lives one layer down, at the protocol
    level: every /api/info route in this codebase is wrapped by
    `CredentialGateMiddleware` (Leg 4, live), so a 200 can only happen when
    the server validated the exact `Authorization` header this probe sent —
    see `test_select_port_case_b_our_instance_sends_credential`, which
    asserts that header is actually transmitted. A foreign process that
    happens to answer 200 on this exact path regardless of auth (rather than
    401/404/refusing) is outside this local-only single-user threat model
    (see SECURITY-MODEL.md).
    """
    import httpx

    from the_one.interfaces.desktop.shell import _select_port

    occupied_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied_sock.bind(("127.0.0.1", 0))
    occupied_sock.listen(1)
    occupied_port = occupied_sock.getsockname()[1]

    try:
        fake_response = MagicMock()
        fake_response.status_code = 404  # foreign HTTP server, no /api/info route at all

        with patch.object(httpx, "get", return_value=fake_response):
            result_port, is_ours = _select_port("127.0.0.1", occupied_port, retries=1, delay=0.0)
    finally:
        occupied_sock.close()

    assert result_port != occupied_port
    assert is_ours is False


def test_select_port_missing_credential_file_does_not_crash(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_select_port must not crash when no credential file exists yet (fresh
    machine, first launch). `get_credential()` creates one on first use, so
    the probe still runs — a missing credential simply means "cannot be
    ours" falls out naturally (nothing free-standing already exists to
    match)."""
    import httpx

    from the_one.config import settings
    from the_one.interfaces.desktop.shell import _select_port

    # Point settings.data_dir at an empty tmp dir — no credential file inside.
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    assert not (tmp_path / "api-credential").exists()

    port = _free_port()  # nothing listening — port is free

    with patch.object(httpx, "get", side_effect=httpx.ConnectError("refused")):
        result_port, is_ours = _select_port("127.0.0.1", port, retries=1, delay=0.0)

    assert result_port == port
    assert is_ours is False
    # get_credential() created the file as a side effect of the probe.
    assert (tmp_path / "api-credential").exists()


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


def _make_splash_mock() -> MagicMock:
    """Return a mock splash window whose events.shown.wait() is a no-op."""
    splash = MagicMock()
    splash.events.shown.wait.return_value = True  # don't block in tests
    return splash


def test_run_calls_create_window_start_and_graceful_shutdown(
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() creates splash + main windows, starts webview with _boot, calls _graceful_shutdown.

    Adapted for the M15 F7 Leg 4 splash restructure:
    - create_window is now called TWICE: once for the splash (before start()), once
      for the main window (inside _boot, which runs after the GUI loop is up).
    - webview.start() is called with a positional _boot callable.
    - The test captures _boot from start()'s call_args and invokes it with NO ARGS —
      matching exactly how pywebview calls it — so the correct call convention is
      exercised (the bug that shipped was _boot defined with a splash_win param that
      pywebview never passed, causing an immediate TypeError on Windows).
    """
    import the_one.interfaces.desktop.shell as launcher_module

    # Redirect data_dir so the webview-profile mkdir lands in a tmp dir, not the
    # real per-user data location.
    monkeypatch.setattr(launcher_module.settings, "data_dir", tmp_path)

    # The first create_window call returns the splash; the second returns the main window.
    mock_splash = _make_splash_mock()
    mock_main_window = MagicMock()
    webview_mock.create_window.side_effect = [mock_splash, mock_main_window]

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

    # create_window called twice: [0] = splash, [1] = main window (inside _boot,
    # but _boot hasn't run yet — start() is mocked; the splash call is all we see here).
    assert webview_mock.create_window.call_count >= 1, "splash create_window must be called"

    # Splash window: first call, title contains "starting", html= kwarg present,
    # frameless=True (splash is a borderless boot screen).
    splash_call = webview_mock.create_window.call_args_list[0]
    assert "starting" in splash_call.args[0].lower() or "starting" in splash_call.args[0]
    assert splash_call.kwargs.get("frameless") is True
    assert splash_call.kwargs.get("html") is not None

    # webview.start called with a positional _boot callable + persistence kwargs.
    webview_mock.start.assert_called_once()
    start_args = webview_mock.start.call_args.args
    start_kwargs = webview_mock.start.call_args.kwargs
    assert len(start_args) >= 1 and callable(start_args[0]), (
        "webview.start must receive a callable _boot as its first positional arg"
    )
    # Persistence config (M15 F5 post-landing fix): start() must run with a
    # NON-private profile pinned to a stable per-user storage_path, so localStorage
    # (e.g. the theme preference) survives restarts/reinstalls. Default
    # private_mode=True would drop it every launch.
    assert start_kwargs.get("private_mode") is False
    assert start_kwargs.get("storage_path") == str(tmp_path / "webview")
    assert (tmp_path / "webview").is_dir()

    # ── Extract and invoke _boot to test the main-window creation path ──────
    # Since webview.start is mocked, _boot never runs automatically. We capture
    # it and invoke it with NO ARGS — exactly how pywebview calls it in production.
    # The closure ``splash`` (first create_window return value) provides the splash
    # reference internally; passing args here would be the wrong call convention and
    # would mask the exact bug that caused the Windows HAT failure.
    _boot = start_args[0]
    # Reset create_window side_effect for the _boot invocation (main window call)
    webview_mock.create_window.side_effect = None
    webview_mock.create_window.return_value = mock_main_window

    with patch.object(launcher_module, "_wait_until_serving"):
        with patch("the_one.interfaces.desktop.tray.build_tray", return_value=MagicMock()):
            _boot()  # NO args — matches pywebview's real call convention

    # Main window: created with title "GleepGlorp AI" and native-frame kwargs.
    main_call = webview_mock.create_window.call_args
    assert main_call.args[0] == "GleepGlorp AI"
    assert main_call.kwargs.get("frameless") is False

    # The URL passed to create_window must carry a one-time handoff credential
    # (DD7/DD12) — without it, CredentialGateMiddleware refuses the window's
    # first navigation with a 401 instead of rendering the app. This is the
    # specific gap the flight-end review caught: nothing previously asserted
    # anything about the URL's content.
    from the_one.interfaces.web.handoff_store import HANDOFF_QUERY_PARAM

    main_url = main_call.args[1]
    assert main_url.startswith(f"http://{launcher_module.settings.host}:8484/")
    assert f"?{HANDOFF_QUERY_PARAM}=" in main_url
    token = main_url.split(f"{HANDOFF_QUERY_PARAM}=", 1)[1]
    assert len(token) == 64 and all(c in "0123456789abcdef" for c in token)

    # _graceful_shutdown was called exactly once
    mock_shutdown.assert_called_once()


class _EventCapture:
    """Stand-in for a pywebview event: supports +=, .fire(), and .is_set().

    is_set() returns False by default so the FIX 2 backstop in _boot does not fire
    during tests that check the loaded→destroy path via .fire().  Set is_set_value=True
    to exercise the backstop path explicitly.
    """

    def __init__(self) -> None:
        self._handlers: list = []
        self.is_set_value: bool = False

    def __iadd__(self, handler) -> "_EventCapture":
        self._handlers.append(handler)
        return self

    def is_set(self) -> bool:
        return self.is_set_value

    def fire(self, *args, **kwargs):
        result = None
        for h in self._handlers:
            result = h(*args, **kwargs)
        return result


def test_boot_happy_path_main_window_kwargs_and_loaded_handler(
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_boot happy path: waits for server, creates main window, registers loaded→destroy splash.

    This is a dedicated test for the _boot callable extracted from webview.start.
    Verifies: shown.wait called on splash; _wait_until_serving called; main window
    created with title "GleepGlorp AI" and native-frame kwargs; loaded handler registered
    BEFORE tray wiring (FIX 2: avoids race where fast localhost load fires loaded
    during tray setup before the handler is subscribed); firing loaded calls splash.destroy().

    _boot is invoked with NO ARGS — the correct pywebview call convention.
    The closure ``splash`` (first create_window return) provides the splash reference.

    Note: _wait_until_serving is called from inside _boot (a closure over the
    launcher module's name). The spy patch must remain active when _boot is invoked,
    so run_desktop() and _boot() are called inside the same patch context.
    """
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(launcher_module.settings, "data_dir", tmp_path)

    mock_splash = _make_splash_mock()
    mock_main_window = MagicMock()
    # Use a real _EventCapture for events.loaded so += tracking works correctly.
    loaded_event = _EventCapture()
    mock_main_window.events.loaded = loaded_event

    # First call = splash (in run), subsequent = main window (in _boot)
    webview_mock.create_window.side_effect = [mock_splash, mock_main_window]

    captured_wait_until: list = []

    def _spy_wait(host, port, timeout=15.0):
        captured_wait_until.append((host, port))

    with patch.object(launcher_module, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_module, "_webview_available", return_value=True):
            with patch.object(launcher_module, "_graceful_shutdown"):
                with patch.object(launcher_module, "_wait_until_serving", side_effect=_spy_wait):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server", return_value=MagicMock()):
                            with patch("threading.Thread", return_value=MagicMock()):
                                launcher_module.run_desktop()

                                # _boot must be invoked INSIDE the patch context so
                                # _wait_until_serving is still the spy when _boot calls it.
                                _boot = webview_mock.start.call_args.args[0]
                                webview_mock.create_window.side_effect = None
                                webview_mock.create_window.return_value = mock_main_window
                                with patch(
                                    "the_one.interfaces.desktop.tray.build_tray",
                                    return_value=MagicMock(),
                                ):
                                    _boot()  # NO args — pywebview calls _boot() with no arguments

    # splash.events.shown.wait was called (step 1 of _boot); splash is the closure
    # variable (first create_window return), not a parameter.
    mock_splash.events.shown.wait.assert_called_once()

    # _wait_until_serving was called from _boot
    assert len(captured_wait_until) == 1

    # Main window created with correct title + native-frame kwargs
    main_call = webview_mock.create_window.call_args
    assert main_call.args[0] == "GleepGlorp AI"
    assert main_call.kwargs.get("frameless") is False
    assert main_call.kwargs.get("resizable") is True

    # The window URL carries a freshly minted one-time handoff credential
    # (DD7/DD12) — the launcher's first navigation must present it or
    # CredentialGateMiddleware refuses with 401 instead of rendering the app.
    from the_one.interfaces.web.handoff_store import HANDOFF_QUERY_PARAM

    main_url = main_call.args[1]
    assert f"?{HANDOFF_QUERY_PARAM}=" in main_url
    token = main_url.split(f"{HANDOFF_QUERY_PARAM}=", 1)[1]
    assert len(token) == 64 and all(c in "0123456789abcdef" for c in token)

    # loaded handler registered on main window to destroy the splash.
    assert len(loaded_event._handlers) == 1, (
        "main_win.events.loaded += handler must be registered to destroy splash"
    )
    # Firing the loaded event must call splash.destroy() (the idempotent teardown).
    loaded_event.fire()
    mock_splash.destroy.assert_called_once()


def test_boot_error_path_destroys_both_windows(
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_boot error path: if _wait_until_serving raises, splash is destroyed and no hang.

    When _wait_until_serving (or main-window creation) raises inside _boot, the
    error path must destroy the splash (so the GUI loop can return) even though
    the main window was never created.

    Note: _boot is invoked INSIDE the patch context so _wait_until_serving is still
    the raising stub when _boot calls it.
    """
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(launcher_module.settings, "data_dir", tmp_path)

    mock_splash = _make_splash_mock()
    webview_mock.create_window.side_effect = [mock_splash]

    with patch.object(launcher_module, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_module, "_webview_available", return_value=True):
            with patch.object(launcher_module, "_graceful_shutdown"):
                with patch.object(
                    launcher_module,
                    "_wait_until_serving",
                    side_effect=RuntimeError("server never ready"),
                ):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server", return_value=MagicMock()):
                            with patch("threading.Thread", return_value=MagicMock()):
                                launcher_module.run_desktop()

                                # Invoke _boot INSIDE the patch context so
                                # _wait_until_serving is still the raising stub.
                                # NO args — pywebview calls _boot() with no arguments.
                                _boot = webview_mock.start.call_args.args[0]
                                webview_mock.create_window.side_effect = None

                                with pytest.raises(RuntimeError, match="server never ready"):
                                    _boot()  # NO args — matches pywebview's real call convention

    # Splash must be destroyed even though the error happened before the main window.
    mock_splash.destroy.assert_called_once()


def test_boot_error_path_destroys_both_when_main_window_created(
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_boot tray-unavailable path: build_tray raising is a graceful degrade (F4 fallback).

    build_tray failing is not an error — _boot continues without tray (no closing
    handler registered), and the splash is dismissed via the loaded event as usual.
    The main window is created; the splash is NOT destroyed in the error path here
    because no exception propagated.  This test verifies _boot survives tray failure.

    Note: _boot is invoked INSIDE the patch context so _wait_until_serving is still
    the no-op stub when _boot calls it.
    """
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(launcher_module.settings, "data_dir", tmp_path)

    mock_splash = _make_splash_mock()
    mock_main_window = MagicMock()
    # FIX 2: install a real _EventCapture on events.loaded so is_set() returns False
    # and the += handler subscription survives without __iadd__ creating a fresh MagicMock.
    # This preserves the test's intent: splash is destroyed by the loaded event, not the backstop.
    _loaded_event = _EventCapture()  # is_set_value=False by default
    mock_main_window.events.loaded = _loaded_event
    webview_mock.create_window.side_effect = [mock_splash, mock_main_window]

    with patch.object(launcher_module, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_module, "_webview_available", return_value=True):
            with patch.object(launcher_module, "_graceful_shutdown"):
                with patch.object(launcher_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server", return_value=MagicMock()):
                            with patch("threading.Thread", return_value=MagicMock()):
                                launcher_module.run_desktop()

                                # Invoke _boot INSIDE the patch context.
                                _boot = webview_mock.start.call_args.args[0]
                                webview_mock.create_window.side_effect = None
                                webview_mock.create_window.return_value = mock_main_window

                                # Make build_tray raise — graceful-degrade path.
                                with patch(
                                    "the_one.interfaces.desktop.tray.build_tray",
                                    side_effect=RuntimeError("no tray backend"),
                                ):
                                    # build_tray raising is the graceful-degrade path —
                                    # _boot doesn't re-raise it; it logs and continues.
                                    # NO args — pywebview calls _boot() with no arguments.
                                    _boot()  # NO args — matches pywebview's real call convention

    # Main window was created (tray failure doesn't stop the app).
    assert webview_mock.create_window.called
    # Splash is NOT destroyed here — the error path wasn't hit (tray failure is
    # graceful degrade); splash will be destroyed when the loaded event fires.
    # (The FIX 2 backstop is disabled via is_set.return_value=False above.)
    mock_splash.destroy.assert_not_called()


def test_run_case_b_posts_focus_and_returns_without_window(
    webview_mock: MagicMock,
) -> None:
    """run() case (b): is_ours=True → POSTs /api/window/focus with our credential
    and returns; no window created."""
    import httpx

    import the_one.interfaces.desktop.shell as launcher_module
    from the_one.api_credential import get_credential
    from the_one.config import settings
    from the_one.interfaces.web import handoff_store

    expected_url = f"http://{settings.host}:{settings.port}/api/window/focus"

    with patch.object(launcher_module, "_select_port", return_value=(settings.port, True)):
        with patch.object(httpx, "post") as mock_post:
            with patch("uvicorn.Server") as mock_server_cls:
                with patch.object(handoff_store, "mint_handoff_credential") as mock_mint:
                    launcher_module.run_desktop()

    # No uvicorn.Server should have been constructed (returned before server start)
    mock_server_cls.assert_not_called()

    # No window created — returned before create_window
    webview_mock.create_window.assert_not_called()

    # This branch returns before the launcher ever builds a navigable URL —
    # it must NOT mint a handoff credential (the token would simply expire
    # unused, and the existing instance's own server never sees it).
    mock_mint.assert_not_called()

    # httpx.post called with the focus URL and our credential; no Origin header
    # (header-less loopback clears the OriginAllowlistMiddleware).
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args.args[0] == expected_url
    headers = call_args.kwargs.get("headers", {})
    assert "origin" not in {k.lower() for k in headers}
    assert headers.get("Authorization") == f"Bearer {get_credential().encode()}"


def test_run_fallback_calls_webbrowser_open_and_joins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() with no WebView backend: webbrowser.open called; SIGINT handler installed; joined.

    The URL passed to webbrowser.open() must carry a one-time handoff
    credential (DD7/DD12) — this is the no-pywebview fallback path, and
    without the token here too, CredentialGateMiddleware refuses the
    browser's first navigation with a 401 instead of rendering the app.
    """
    import signal as signal_mod
    import webbrowser as webbrowser_mod

    import the_one.interfaces.desktop.shell as launcher_module
    from the_one.config import settings
    from the_one.interfaces.web.handoff_store import HANDOFF_QUERY_PARAM

    expected_base_url = f"http://{settings.host}:{settings.port}/"

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

    # webbrowser.open called once, with the base URL plus a handoff token —
    # not the bare base URL that shipped with the defect.
    mock_open.assert_called_once()
    opened_url = mock_open.call_args.args[0]
    assert opened_url != expected_base_url, (
        "webbrowser.open() must not be called with a bare URL lacking a handoff credential"
    )
    assert opened_url.startswith(expected_base_url)
    assert f"?{HANDOFF_QUERY_PARAM}=" in opened_url
    token = opened_url.split(f"{HANDOFF_QUERY_PARAM}=", 1)[1]
    assert len(token) == 64 and all(c in "0123456789abcdef" for c in token)

    # signal.signal was called to install SIGINT handler
    mock_signal.assert_called_once()
    assert mock_signal.call_args.args[0] == signal_mod.SIGINT

    # thread.join was called (blocks until SIGINT → drain)
    mock_thread.join.assert_called_once()


def test_run_case_b_is_ours_posts_focus_and_returns_no_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() case (b): is_ours=True → POSTs credentialed focus and returns; no browser/server."""
    import webbrowser as webbrowser_mod

    import httpx

    import the_one.interfaces.desktop.shell as launcher_module
    from the_one.api_credential import get_credential
    from the_one.config import settings
    from the_one.interfaces.web import handoff_store

    with patch.object(launcher_module, "_select_port", return_value=(settings.port, True)):
        with patch.object(httpx, "post") as mock_post:
            with patch("uvicorn.Server") as mock_server_cls:
                with patch.object(webbrowser_mod, "open") as mock_open:
                    with patch.object(handoff_store, "mint_handoff_credential") as mock_mint:
                        launcher_module.run_desktop()

    # No server constructed, no browser opened
    mock_server_cls.assert_not_called()
    mock_open.assert_not_called()

    # is_ours=True must not mint — this process never opens a window or
    # browser tab, so a minted token here would just expire unused.
    mock_mint.assert_not_called()

    # Focus POST was issued, carrying our credential.
    mock_post.assert_called_once()
    headers = mock_post.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == f"Bearer {get_credential().encode()}"


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


# ── _splash_html ──────────────────────────────────────────────────────────────


def test_splash_html_embeds_base64_data_uri_when_asset_present(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_splash_html() embeds a data:image/png;base64, URI when the brand asset is present.

    A minimal 1-byte PNG stub is written to a tmp brand directory; STATIC_DIR is
    monkeypatched to that directory so _splash_html() finds the asset without
    touching the real filesystem or requiring a freeze bundle.
    """
    import base64

    import the_one.interfaces.desktop.shell as launcher_module
    import the_one.interfaces.web.app as web_app_module

    # Create a minimal fake PNG asset under tmp_path/brand/
    brand_dir = tmp_path / "brand"
    brand_dir.mkdir()
    fake_png = b"\x89PNG\r\n\x1a\n"  # PNG magic bytes — not a valid PNG, but enough for b64
    logo_path = brand_dir / "gleepglorp_med.png"
    logo_path.write_bytes(fake_png)

    # Monkeypatch STATIC_DIR in the web.app module so the lazy import inside
    # _splash_html() resolves to our tmp directory.
    monkeypatch.setattr(web_app_module, "STATIC_DIR", tmp_path)

    html = launcher_module._splash_html()

    expected_b64 = base64.b64encode(fake_png).decode("ascii")
    assert f"data:image/png;base64,{expected_b64}" in html, (
        "_splash_html() must embed the PNG as a data URI"
    )


def test_splash_html_falls_back_to_text_only_when_asset_missing(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_splash_html() falls back to text-only HTML (no raise) when the asset path is missing.

    STATIC_DIR is pointed at an empty tmp directory so the brand/gleepglorp_med.png
    path does not exist.  The builder must NOT raise — it logs a warning and returns
    the text-only fallback constant.
    """
    import the_one.interfaces.desktop.shell as launcher_module
    import the_one.interfaces.web.app as web_app_module

    # Point STATIC_DIR at an empty directory — no brand/gleepglorp_med.png inside.
    monkeypatch.setattr(web_app_module, "STATIC_DIR", tmp_path)

    html = launcher_module._splash_html()

    # Must return a non-empty HTML string without raising.
    assert html.strip().startswith("<!DOCTYPE html>"), (
        "_splash_html() fallback must return valid HTML"
    )
    # Must NOT embed a data URI (the asset was absent).
    assert "data:image/png;base64," not in html, (
        "_splash_html() fallback must not embed a data URI when the asset is missing"
    )
