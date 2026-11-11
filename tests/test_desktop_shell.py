"""Launcher-core unit tests for the_one/interfaces/desktop/shell.py.

webview is NOT installed on this host — it is mocked via sys.modules injection
so the tests exercise the launcher logic without any GUI dependency.

Do NOT import webview at the module top level.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from the_one.interfaces.desktop import takeover, window_control
from the_one.interfaces.desktop.session_state import state

# The harness patches ``threading.Thread``; tests that need a real one use this.
_RealThread = threading.Thread

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

    from the_one.interfaces.desktop.takeover import _select_port

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
    from the_one.interfaces.desktop.takeover import _select_port

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

    from the_one.interfaces.desktop.takeover import _select_port

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

    from the_one.interfaces.desktop.takeover import _select_port

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
    from the_one.interfaces.desktop.takeover import _select_port

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

    with patch.object(takeover, "_select_port", return_value=(8484, False)):
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
    assert splash_call.kwargs.get("text_select") is not True
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
    assert main_call.kwargs["text_select"] is True  # DD17: copy a reply

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

    with patch.object(takeover, "_select_port", return_value=(8484, False)):
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
    # (plus the native-bridge removal handler where the policy removes it, M35 F2 L8).
    expected = 1 + int(state.policy.removes_native_bridge)
    assert len(loaded_event._handlers) == expected, (
        "main_win.events.loaded += handler must be registered to destroy splash"
    )
    # Firing the loaded event must call splash.destroy() (the idempotent teardown).
    loaded_event.fire()
    mock_splash.destroy.assert_called_once()


@pytest.mark.parametrize("flag", [True, False])
def test_boot_registers_native_bridge_removal_only_when_policy_says(
    flag: bool,
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The removal is its OWN ``loaded`` handler (not folded into the splash lambda),
    registered on the main window only when ``removes_native_bridge`` is true."""
    import dataclasses

    import the_one.interfaces.desktop.shell as launcher_module
    from the_one.interfaces.desktop import native_bridge

    monkeypatch.setattr(launcher_module.settings, "data_dir", tmp_path)
    from the_one.interfaces.desktop import boot_policy

    chosen = dataclasses.replace(boot_policy.LINUX, removes_native_bridge=flag)
    monkeypatch.setattr(boot_policy, "current", lambda: chosen)  # run() resets state
    removed: list = []
    monkeypatch.setattr(
        native_bridge, "remove_native_handlers", lambda win: removed.append(win) or "removed"
    )

    mock_splash = _make_splash_mock()
    mock_main_window = MagicMock()
    loaded_event = _EventCapture()
    mock_main_window.events.loaded = loaded_event
    webview_mock.create_window.side_effect = [mock_splash, mock_main_window]

    with patch.object(takeover, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_module, "_webview_available", return_value=True):
            with patch.object(launcher_module, "_graceful_shutdown"):
                with patch.object(launcher_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server", return_value=MagicMock()):
                            with patch("threading.Thread", return_value=MagicMock()):
                                launcher_module.run_desktop()
                                _boot = webview_mock.start.call_args.args[0]
                                webview_mock.create_window.side_effect = None
                                webview_mock.create_window.return_value = mock_main_window
                                with patch(
                                    "the_one.interfaces.desktop.tray.build_tray",
                                    return_value=MagicMock(),
                                ):
                                    _boot()

    assert len(loaded_event._handlers) == (2 if flag else 1)
    loaded_event.fire()
    assert removed == ([mock_main_window] if flag else [])
    # A platform that removes nothing records "not-applicable" (not "pending").
    assert state.native_bridge == ("pending" if flag else "not-applicable")


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

    with patch.object(takeover, "_select_port", return_value=(8484, False)):
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

    with patch.object(takeover, "_select_port", return_value=(8484, False)):
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

    with (
        patch.object(takeover, "_select_port", return_value=(settings.port, True)),
        patch.object(takeover, "_running_version", return_value=None),
    ):
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

    with patch.object(takeover, "_select_port", return_value=(settings.port, False)):
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

    with (
        patch.object(takeover, "_select_port", return_value=(settings.port, True)),
        patch.object(takeover, "_running_version", return_value=None),
    ):
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
    with patch.object(takeover, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_mod, "_webview_available", return_value=True):
            with patch.object(launcher_mod, "_wait_until_serving"):
                with patch("the_one.interfaces.web.app.app", MagicMock()):
                    with patch("uvicorn.Server", return_value=MagicMock()):
                        with patch("threading.Thread", return_value=MagicMock()):
                            with patch("builtins.__import__", side_effect=_import_raiser):
                                with pytest.raises(SystemExit, match="pywebview is not installed"):
                                    launcher_mod.run_desktop()


# ── settings.port write-back (M21 F01 L02 Edge Case) ──────────────────────


def test_run_writes_settings_port_from_select_port_fallback_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_select_port`'s fallback branch (Case C — configured port occupied
    by a foreign process) resolves a DIFFERENT port than `settings.port`.
    The self-configuration surface builds its loopback URL from
    `settings.port` (`self_configuration.manage.surface_url`); leaving it
    stale would strand every surface row's URL. `run()` must write the
    resolved port back onto `settings.port` immediately after
    `_select_port` resolves, on the branch that will actually serve.
    """
    import signal as signal_mod
    import webbrowser as webbrowser_mod

    import the_one.interfaces.desktop.shell as launcher_module
    from the_one.config import settings

    configured_port = settings.port
    # Ensures teardown restores `settings.port` to its pre-test value even
    # though the code under test mutates it directly (not via monkeypatch)
    # — monkeypatch.setattr snapshots the CURRENT value at call time and
    # restores exactly that at teardown, regardless of later direct writes.
    monkeypatch.setattr(settings, "port", configured_port)
    resolved_port = _free_port()
    assert resolved_port != configured_port

    mock_thread = MagicMock()
    mock_server = MagicMock()

    with patch.object(takeover, "_select_port", return_value=(resolved_port, False)):
        with patch.object(launcher_module, "_webview_available", return_value=False):
            with patch.object(launcher_module, "_graceful_shutdown"):
                with patch.object(launcher_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server", return_value=mock_server):
                            with patch("threading.Thread", return_value=mock_thread):
                                with patch.object(webbrowser_mod, "open"):
                                    with patch.object(signal_mod, "signal"):
                                        mock_thread.join.return_value = None
                                        launcher_module.run_desktop()

    assert settings.port == resolved_port


def test_run_case_b_is_ours_does_not_write_settings_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `is_ours=True` branch returns before ever serving a lifespan —
    it must NOT write `settings.port`, since this process attaches to (at
    most) an existing window rather than starting its own server."""
    import httpx

    import the_one.interfaces.desktop.shell as launcher_module
    from the_one.config import settings

    original_port = settings.port
    monkeypatch.setattr(settings, "port", original_port)
    foreign_resolved_port = _free_port()
    assert foreign_resolved_port != original_port

    with patch.object(takeover, "_select_port", return_value=(foreign_resolved_port, True)):
        with patch.object(httpx, "post"):
            with patch("uvicorn.Server") as mock_server_cls:
                launcher_module.run_desktop()

    mock_server_cls.assert_not_called()
    assert settings.port == original_port


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
    logo_path = brand_dir / "gleepglorp_splash.png"
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

    STATIC_DIR is pointed at an empty tmp directory so the brand/gleepglorp_splash.png
    path does not exist.  The builder must NOT raise — it logs a warning and returns
    the text-only fallback constant.
    """
    import the_one.interfaces.desktop.shell as launcher_module
    import the_one.interfaces.web.app as web_app_module

    # Point STATIC_DIR at an empty directory — no brand/gleepglorp_splash.png inside.
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


# ── Window chrome: first paint, launch theme, splash, deregister (M25 F5 L2) ──


def _boot_harness(
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    platform: str | None = None,
    os_theme: str = "dark",
    show_side_effect: Any = None,
    loaded_is_set: bool = False,
    pre_boot: Any = None,
    expect_raises: type[BaseException] | None = None,
) -> types_ns:
    """Run ``run_desktop()`` then ``_boot()`` against mocks; return what was seen.

    ``chrome.register`` / ``apply_splash_border`` / ``native_show`` / ``os_theme`` are
    stubbed so no real pythonnet or winreg code runs against MagicMock windows even
    when ``sys.platform`` is patched to win32.
    """
    import the_one.interfaces.desktop.shell as launcher_module
    from the_one.interfaces.desktop import chrome

    monkeypatch.setattr(launcher_module.settings, "data_dir", tmp_path)
    if platform is not None:
        monkeypatch.setattr(sys, "platform", platform)

    order: list[str] = []
    monkeypatch.setattr(chrome, "os_theme", lambda: os_theme)
    monkeypatch.setattr(chrome, "register", lambda w, t: order.append(f"register:{t}"))
    border_calls: list[Any] = []
    monkeypatch.setattr(chrome, "apply_splash_border", lambda w, t: border_calls.append((w, t)))
    native_calls: list[Any] = []
    monkeypatch.setattr(chrome, "native_show", lambda w: native_calls.append(w))

    mock_splash = _make_splash_mock()
    mock_splash.events.before_show = _EventCapture()
    mock_main = MagicMock()
    loaded = _EventCapture()
    loaded.is_set_value = loaded_is_set
    mock_main.events.loaded = loaded

    def _show() -> None:
        order.append("show")
        if show_side_effect is not None:
            show_side_effect(mock_splash, loaded)

    mock_main.show.side_effect = _show
    webview_mock.create_window.side_effect = [mock_splash, mock_main]
    ns = types_ns(
        order=order,
        splash=mock_splash,
        main=mock_main,
        loaded=loaded,
        border_calls=border_calls,
        native_calls=native_calls,
        launcher=launcher_module,
        chrome=chrome,
    )
    with patch.object(takeover, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_module, "_webview_available", return_value=True):
            with patch.object(launcher_module, "_graceful_shutdown"):
                with patch.object(launcher_module, "_wait_until_serving"):
                    with patch("the_one.interfaces.web.app.app", MagicMock()):
                        with patch("uvicorn.Server", return_value=MagicMock()):
                            with patch("threading.Thread", return_value=MagicMock()):
                                launcher_module.run_desktop()
                                ns.start_call = webview_mock.start.call_args
                                ns.splash_call = webview_mock.create_window.call_args_list[0]
                                if pre_boot is not None:
                                    pre_boot(ns)
                                boot = webview_mock.start.call_args.args[0]
                                webview_mock.create_window.side_effect = [mock_main]
                                with patch(
                                    "the_one.interfaces.desktop.tray.build_tray",
                                    return_value=MagicMock(),
                                ):
                                    if expect_raises is None:
                                        boot()
                                    else:
                                        with pytest.raises(expect_raises):
                                            boot()
    ns.main_call = webview_mock.create_window.call_args_list[-1]
    return ns


class types_ns:  # noqa: N801 - tiny attribute bag
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


def test_main_window_created_hidden_with_launch_background(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, os_theme="dark")
    assert ns.main_call.kwargs["hidden"] is True
    assert ns.main_call.kwargs["text_select"] is True
    assert ns.main_call.kwargs["background_color"] == "#101114"
    assert ns.main_call.kwargs["frameless"] is False
    assert ns.main_call.kwargs["resizable"] is True


def test_launch_theme_from_file_else_os_theme(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from the_one.interfaces.desktop import chrome

    chrome.save_theme(tmp_path, "light")
    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, os_theme="dark")
    assert ns.main_call.kwargs["background_color"] == "#ffffff"
    assert "register:light" in ns.order
    assert ns.splash_call.kwargs["background_color"] == "#ffffff"


def test_launch_theme_without_file_follows_os_theme(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, os_theme="light")
    assert ns.main_call.kwargs["background_color"] == "#ffffff"
    assert "register:light" in ns.order
    # run() enabled the chrome state with the data dir (requests persist from now on).
    assert ns.chrome.snapshot()["enabled"] is True


def test_register_runs_after_create_window_before_show(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_handlers: list[int] = []

    def _show(splash: Any, loaded: Any) -> None:
        seen_handlers.append(len(loaded._handlers))

    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, show_side_effect=_show)
    assert ns.order == ["register:dark", "show"]
    ns.main.show.assert_called_once()
    # The loaded handler was subscribed before register and show.
    # (the splash handler, plus the native-bridge removal where the policy has it)
    assert seen_handlers == [1 + int(state.policy.removes_native_bridge)]


def test_splash_gets_themed_html_and_background(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, os_theme="light")
    html = ns.splash_call.kwargs["html"]
    assert "#ffffff" in html and "#101114" not in html and "#0f1117" not in html
    assert ns.splash_call.kwargs["background_color"] == "#ffffff"
    # Linux: no splash border handler.
    assert ns.splash.events.before_show._handlers == []


def test_splash_border_handler_on_windows(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, platform="win32", os_theme="dark")
    handlers = ns.splash.events.before_show._handlers
    assert len(handlers) == 1
    import inspect

    assert list(inspect.signature(handlers[0]).parameters) == ["window"]
    marker = object()
    handlers[0](marker)
    assert ns.border_calls == [(marker, "dark")]


def test_show_raising_falls_back_to_native_show_on_windows(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(splash: Any, loaded: Any) -> None:
        raise RuntimeError("shown wait timed out")

    ns = _boot_harness(
        webview_mock, tmp_path, monkeypatch, platform="win32", show_side_effect=_boom
    )
    assert ns.native_calls == [ns.main]
    ns.splash.destroy.assert_not_called()  # loaded not fired: the splash stays


def test_native_fallback_failing_takes_the_error_path(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from the_one.interfaces.desktop import chrome

    def _boom(splash: Any, loaded: Any) -> None:
        raise RuntimeError("shown wait timed out")

    def _pre(ns: Any) -> None:
        monkeypatch.setattr(
            chrome, "native_show", lambda w: (_ for _ in ()).throw(RuntimeError("no native"))
        )

    ns = _boot_harness(
        webview_mock,
        tmp_path,
        monkeypatch,
        platform="win32",
        show_side_effect=_boom,
        pre_boot=_pre,
        expect_raises=RuntimeError,
    )
    ns.splash.destroy.assert_called_once()
    ns.main.destroy.assert_called_once()


def test_show_raising_off_windows_has_no_native_fallback(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(splash: Any, loaded: Any) -> None:
        raise RuntimeError("show failed")

    ns = _boot_harness(
        webview_mock,
        tmp_path,
        monkeypatch,
        platform="linux",
        show_side_effect=_boom,
        expect_raises=RuntimeError,
    )
    assert ns.native_calls == []
    ns.splash.destroy.assert_called_once()
    ns.main.destroy.assert_called_once()


def test_splash_survives_until_show_returns_when_loaded_already_set(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    during_show: list[int] = []

    def _show(splash: Any, loaded: Any) -> None:
        during_show.append(splash.destroy.call_count)

    ns = _boot_harness(
        webview_mock, tmp_path, monkeypatch, loaded_is_set=True, show_side_effect=_show
    )
    assert during_show == [0]
    ns.splash.destroy.assert_called_once()  # the backstop, after show() returned


def test_splash_survives_a_loaded_that_fires_before_show_returns(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    threads: list[Any] = []
    during_show: list[int] = []

    def _show(splash: Any, loaded: Any) -> None:
        t = _RealThread(target=loaded.fire)  # the handler runs on its own thread
        t.start()
        threads.append(t)
        t.join(timeout=0.3)  # it is blocked waiting for the main window to be shown
        during_show.append(splash.destroy.call_count)

    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, show_side_effect=_show)
    threads[0].join(timeout=5)
    assert during_show == [0]
    ns.splash.destroy.assert_called_once()


def test_every_desktop_notice_fits_a_gnome_banner() -> None:
    """Squawk 0254: GNOME truncates long notification text; each title and body <= 60."""
    import the_one.interfaces.desktop.shell as shell_mod

    texts: dict[str, str] = {}
    for mod in (shell_mod, window_control):
        for name, value in vars(mod).items():
            if "NOTICE" not in name and "NO_WEBVIEW" not in name:
                continue
            if isinstance(value, str):
                texts[f"{mod.__name__}.{name}"] = value
            elif isinstance(value, dict):
                texts.update({f"{mod.__name__}.{name}[{k}]": v for k, v in value.items()})
    assert len(texts) >= 8  # tray, no-tray and the three no-webview bodies plus titles
    too_long = {k: len(v) for k, v in texts.items() if len(v) > 60}
    assert not too_long, too_long


def test_tray_quit_before_publish_destroys_the_window(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Squawk 0264: a tray Quit between the tray start and the publish is not lost."""
    import the_one.interfaces.desktop.shell as launcher_module

    real_publish = state.publish_window
    seen: list[bool] = []

    def _quit_then_publish(window: Any) -> bool:
        # the tray's Quit, just before step 6
        launcher_module.DesktopSession()._on_quit(None)
        seen.append(state.quit_requested)
        return real_publish(window)

    def _pre(ns: Any) -> None:
        monkeypatch.setattr(state, "publish_window", _quit_then_publish)

    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, platform="linux", pre_boot=_pre)
    assert seen == [True]
    ns.main.destroy.assert_called_once()  # publish saw the quit and ran _on_quit
    ns.splash.destroy.assert_called()


def test_deregister_before_destroy_in_on_quit(monkeypatch: pytest.MonkeyPatch) -> None:
    import the_one.interfaces.desktop.shell as shell_mod

    events: list[str] = []
    monkeypatch.setattr(shell_mod.chrome, "deregister", lambda: events.append("deregister"))
    win = MagicMock()
    win.destroy.side_effect = lambda: events.append("destroy")
    monkeypatch.setattr(state, "desktop_window", win)
    monkeypatch.setattr(state, "really_quit", False)
    shell_mod.DesktopSession()._on_quit(MagicMock())
    assert events == ["deregister", "destroy"]


def test_deregister_in_on_closing_allow_destroy_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    import the_one.interfaces.desktop.shell as shell_mod

    events: list[str] = []
    monkeypatch.setattr(shell_mod.chrome, "deregister", lambda: events.append("deregister"))
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    monkeypatch.setattr(state, "desktop_window", win)

    # really-quit return
    monkeypatch.setattr(state, "really_quit", True)
    assert shell_mod.DesktopSession()._on_closing() is True
    assert events == ["deregister"]

    # hide fails -> allow destroy
    events.clear()
    monkeypatch.setattr(state, "really_quit", False)
    sess = shell_mod.DesktopSession()
    sess._icon = MagicMock()
    win.hide.side_effect = RuntimeError("hide failed")
    monkeypatch.setattr("the_one.interfaces.desktop.notice.notice_shown", lambda: True)
    assert sess._on_closing() is True
    assert events == ["deregister"]

    # hide succeeds -> cancel the destroy, no deregister
    events.clear()
    win.hide.side_effect = None
    assert sess._on_closing() is False
    assert events == []


def test_close_to_tray_without_icon_is_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    """The old ``_icon is None`` -> destroy() branch is gone (M32 F2 L05)."""
    import the_one.interfaces.desktop.shell as shell_mod

    win = MagicMock()
    monkeypatch.setattr(state, "desktop_window", win)
    sess = shell_mod.DesktopSession()
    sess._icon = None
    assert sess._close_to_tray() is False
    win.destroy.assert_not_called()
    win.hide.assert_not_called()


def test_set_window_theme_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import the_one.interfaces.desktop.shell as shell_mod

    assert window_control.set_window_theme("dark") == {
        "theme": "dark",
        "desktop": False,
        "tinted": False,
    }

    def boom(theme: str) -> dict:
        raise RuntimeError("x")

    monkeypatch.setattr(shell_mod.chrome, "request", boom)
    assert window_control.set_window_theme("light")["tinted"] is False


@pytest.mark.parametrize(
    "theme,bg,fg", [("light", "#ffffff", "#18181b"), ("dark", "#101114", "#ededf0")]
)
def test_splash_html_is_themed(
    theme: str, bg: str, fg: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import the_one.interfaces.desktop.shell as launcher_module
    import the_one.interfaces.web.app as web_app_module

    (tmp_path / "brand").mkdir()
    (tmp_path / "brand" / "gleepglorp_splash.png").write_bytes(b"png")
    monkeypatch.setattr(web_app_module, "STATIC_DIR", tmp_path)
    for html in (
        launcher_module._splash_html(theme),
        launcher_module._splash_text_only(theme),
    ):
        assert bg in html and fg in html
        assert "#0f1117" not in html and "#6b7280" not in html and "#1e2130" not in html
    # The default keeps today's no-argument callers working (dark).
    assert "#101114" in launcher_module._splash_html()


# ── M32 F2 L02: _webview_available shares the host predicate (AC7) ───────────


@pytest.mark.parametrize("host_gtk", [True, False])
@pytest.mark.parametrize("webkit_ok", [True, False])
def test_webview_available_requires_host_gtk_and_typelib(
    monkeypatch: pytest.MonkeyPatch, host_gtk: bool, webkit_ok: bool
) -> None:
    import types

    import the_one.interfaces.desktop.host as host_mod
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(host_mod, "host_has_desktop_gtk", lambda: host_gtk)
    fake_gi = types.ModuleType("gi")

    def require_version(ns, ver):
        if not webkit_ok:
            raise ValueError("no typelib")

    fake_gi.require_version = require_version
    monkeypatch.setitem(sys.modules, "gi", fake_gi)
    assert launcher_module._webview_available() is (host_gtk and webkit_ok)


# ── M32 F2 L02: the no-WebKit browser notice (AC6) ────────────────────────────


def _run_fallback(monkeypatch: pytest.MonkeyPatch, platform: str, piece, events: list) -> None:
    import signal as signal_mod
    import webbrowser as webbrowser_mod

    import the_one.interfaces.desktop.host as host_mod
    import the_one.interfaces.desktop.shell as launcher_module
    from the_one.config import settings

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(host_mod, "missing_desktop_piece", lambda: piece)
    monkeypatch.setattr(
        host_mod,
        "send_notification",
        lambda summary, body: events.append(("notify", summary, body)),
    )
    with (
        patch.object(takeover, "_select_port", return_value=(settings.port, False)),
        patch.object(launcher_module, "_webview_available", return_value=False),
        patch.object(launcher_module, "_graceful_shutdown"),
        patch.object(launcher_module, "_wait_until_serving"),
        patch("the_one.interfaces.web.app.app", MagicMock()),
        patch("uvicorn.Server", return_value=MagicMock()),
        patch("threading.Thread", return_value=MagicMock()),
        patch.object(webbrowser_mod, "open", side_effect=lambda u: events.append(("open", u))),
        patch.object(signal_mod, "signal"),
    ):
        launcher_module.run_desktop()


@pytest.mark.parametrize(
    "piece,needle",
    [
        ("webkit", "gir1.2-webkit2-4.1"),
        ("gtk", "no GTK 3 window libraries"),
        ("gi", "PyGObject (gi)"),
    ],
)
def test_fallback_notifies_before_opening_browser(
    monkeypatch: pytest.MonkeyPatch, piece: str, needle: str
) -> None:
    events: list = []
    _run_fallback(monkeypatch, "linux", piece, events)
    kinds = [e[0] for e in events]
    assert kinds == ["notify", "open"]
    assert events[0][1] == "GleepGlorp AI opened in your browser"
    assert needle in events[0][2]
    assert len(events[0][2]) <= 60  # GNOME's banner truncates longer text (squawk 0254)


def test_fallback_on_win32_sends_no_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []
    _run_fallback(monkeypatch, "win32", None, events)
    assert [e[0] for e in events] == ["open"]


pytestmark = pytest.mark.usefixtures("stub_desktop_host")


# ── M32 F2 L05 phase A: close states, markers, imports, quit, boot race ──────


@pytest.fixture()
def shell_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Any):
    """The real shell module with the lifecycle state reset and a scratch data dir."""
    import the_one.interfaces.desktop.shell as shell_mod

    monkeypatch.setattr(shell_mod.settings, "data_dir", tmp_path)
    state.reset()  # the lifecycle flags live on session_state.state (M32 F3 DD1)
    monkeypatch.setattr(window_control, "_is_gtk_backend", lambda: False)
    return shell_mod


def _notes(monkeypatch: pytest.MonkeyPatch) -> list:
    import the_one.interfaces.desktop.host as host_mod

    calls: list = []
    monkeypatch.setattr(host_mod, "send_notification", lambda s, b: calls.append((s, b)))
    return calls


def test_none_mode_close_hides_and_notices_once(shell_state, monkeypatch, tmp_path) -> None:
    calls = _notes(monkeypatch)
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    monkeypatch.setattr(state, "desktop_window", win)
    monkeypatch.setattr(state, "tray_mode", "none")
    sess = shell_state.DesktopSession()
    assert sess._on_closing() is False  # cancel the destroy
    win.hide.assert_called_once()
    win.destroy.assert_not_called()
    assert state.tracked_visible is False
    assert len(calls) == 1
    assert calls[0][0] == "GleepGlorp AI is still running"
    assert calls[0][1] == "Open it again to show it, or right-click its icon to quit."
    assert len(calls[0][1]) <= 60
    assert (tmp_path / ".no_tray_notice_shown").exists()
    assert not (tmp_path / ".close_to_tray_notice_shown").exists()
    # a second close hides again without a second notice
    assert sess._on_closing() is False
    assert win.hide.call_count == 2 and len(calls) == 1


def test_none_mode_hide_failure_allows_destroy(shell_state, monkeypatch) -> None:
    calls = _notes(monkeypatch)
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    win.hide.side_effect = RuntimeError("gone")
    monkeypatch.setattr(state, "desktop_window", win)
    monkeypatch.setattr(state, "tray_mode", "none")
    assert shell_state.DesktopSession()._on_closing() is True
    assert calls == []


@pytest.mark.parametrize("mode", ["failed", None])
def test_failed_or_undecided_tray_allows_destroy(shell_state, monkeypatch, mode) -> None:
    calls = _notes(monkeypatch)
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    monkeypatch.setattr(state, "desktop_window", win)
    monkeypatch.setattr(state, "tray_mode", mode)
    assert shell_state.DesktopSession()._on_closing() is True
    win.hide.assert_not_called()
    assert calls == []


def test_really_quit_allows_destroy_in_none_mode(shell_state, monkeypatch) -> None:
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    monkeypatch.setattr(state, "desktop_window", win)
    monkeypatch.setattr(state, "tray_mode", "none")
    monkeypatch.setattr(state, "really_quit", True)
    assert shell_state.DesktopSession()._on_closing() is True
    win.hide.assert_not_called()


def test_notice_markers_are_separate(monkeypatch, tmp_path) -> None:
    from the_one.config import settings
    from the_one.interfaces.desktop import notice

    monkeypatch.setattr(settings, "data_dir", tmp_path / "fresh")
    assert not notice.no_tray_notice_shown() and not notice.notice_shown()
    notice.mark_no_tray_notice_shown()  # creates the data dir
    assert notice.no_tray_notice_shown() and not notice.notice_shown()
    notice.mark_notice_shown()
    assert (tmp_path / "fresh" / ".no_tray_notice_shown").exists()
    assert (tmp_path / "fresh" / ".close_to_tray_notice_shown").exists()


def test_notification_never_blocks_the_close(shell_state, monkeypatch) -> None:
    """The real send_notification returns at once (daemon thread), even if gio hangs."""
    import time

    import the_one.interfaces.desktop.host as host_mod

    release = threading.Event()
    monkeypatch.setattr(host_mod, "_notify_via_gio", lambda s, b: release.wait(10))
    win = MagicMock()
    win.events.shown.is_set.return_value = False
    monkeypatch.setattr(state, "desktop_window", win)
    monkeypatch.setattr(state, "tray_mode", "none")
    t0 = time.monotonic()
    try:
        assert shell_state.DesktopSession()._on_closing() is False
        assert time.monotonic() - t0 < 1.0
    finally:
        release.set()


def test_close_path_functions_have_no_imports() -> None:
    """DD12: a .deb upgrade replaces the bundle under a running process, so the
    close and quit path must not import anything lazily."""
    import ast
    import inspect

    import the_one.interfaces.desktop.shell as shell_mod

    # The close and quit path spans both modules since M32 F3 DD1.
    trees = [
        ast.parse(inspect.getsource(shell_mod)),
        ast.parse(inspect.getsource(window_control)),
    ]
    wanted = {
        "_on_closing",
        "_no_tray_hide",
        "_save_current_geometry",
        "quit_desktop",
        "window_state",
        "_close_to_tray",
    }
    seen = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
                seen.add(node.name)
                bad = [n for n in ast.walk(node) if isinstance(n, (ast.Import, ast.ImportFrom))]
                assert not bad, f"{node.name} contains an import"
    assert seen == wanted


def test_pystray_not_imported_by_shell_module_import() -> None:
    import subprocess

    out = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; import the_one.interfaces.desktop.shell; "
            "print('pystray' in sys.modules, 'webview' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
    )
    assert out.stdout.strip().endswith("False False"), out.stderr[-500:]


def test_closing_registered_before_tray_decision(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import the_one.interfaces.desktop.host as host_mod

    order: list[str] = []

    class _Closing:
        def __iadd__(self, handler):
            order.append("closing-registered")
            return self

    def _pre_boot(ns) -> None:
        ns.main.events.closing = _Closing()
        monkeypatch.setattr(
            host_mod,
            "detect_tray",
            lambda backend: (order.append("tray-decided"), ("none", "x"))[1],
        )

    _boot_harness(webview_mock, tmp_path, monkeypatch, pre_boot=_pre_boot)
    assert order[:2] == ["closing-registered", "tray-decided"]


# quit_desktop: one case per state ---------------------------------------------


def test_quit_desktop_window_runs_quit_outside_the_lock(shell_state, monkeypatch) -> None:
    held: list[bool] = []
    sess = MagicMock()
    sess._icon = "icon"
    sess._on_quit.side_effect = lambda icon: held.append(state.lock.locked())
    monkeypatch.setattr(state, "session", sess)
    monkeypatch.setattr(state, "desktop_window", MagicMock())
    assert window_control.quit_desktop() == "window"
    sess._on_quit.assert_called_once_with("icon")
    assert held == [False]


def test_quit_desktop_repeat_does_not_destroy_again(shell_state, monkeypatch) -> None:
    sess = MagicMock()
    monkeypatch.setattr(state, "session", sess)
    monkeypatch.setattr(state, "desktop_window", MagicMock())
    monkeypatch.setattr(state, "really_quit", True)
    assert window_control.quit_desktop() == "window"
    sess._on_quit.assert_not_called()


def test_quit_desktop_window_quit_raising_returns_none(shell_state, monkeypatch) -> None:
    sess = MagicMock()
    sess._on_quit.side_effect = RuntimeError("boom")
    monkeypatch.setattr(state, "session", sess)
    monkeypatch.setattr(state, "desktop_window", MagicMock())
    assert window_control.quit_desktop() is None


def test_quit_desktop_booting_records_the_request(shell_state, monkeypatch) -> None:
    monkeypatch.setattr(state, "session", MagicMock())
    monkeypatch.setattr(state, "booting", True)
    assert window_control.quit_desktop() == "booting"
    assert state.quit_requested is True
    assert window_control.quit_desktop() == "booting"  # idempotent


def test_quit_desktop_browser_drains_the_server(shell_state, monkeypatch) -> None:
    server = MagicMock()
    server.should_exit = False
    monkeypatch.setattr(state, "session", MagicMock())
    monkeypatch.setattr(state, "browser_server", server)
    assert window_control.quit_desktop() == "browser"
    assert server.should_exit is True


def test_quit_desktop_serve_is_none(shell_state) -> None:
    assert window_control.quit_desktop() is None
    assert state.quit_requested is False


def test_mode_values(shell_state, monkeypatch) -> None:
    assert window_control.window_state()["mode"] == "serve"
    monkeypatch.setattr(state, "session", MagicMock())
    assert window_control.window_state()["mode"] is None
    monkeypatch.setattr(state, "booting", True)
    assert window_control.window_state()["mode"] == "booting"
    monkeypatch.setattr(state, "booting", False)
    monkeypatch.setattr(state, "browser_server", MagicMock())
    assert window_control.window_state()["mode"] == "browser"
    monkeypatch.setattr(state, "desktop_window", MagicMock())
    assert window_control.window_state()["mode"] == "window"
    monkeypatch.setattr(state, "really_quit", True)
    assert window_control.window_state()["mode"] == "quitting"
    monkeypatch.setattr(state, "session", None)
    assert window_control.window_state()["mode"] == "serve"


# The boot race: a quit at each _boot checkpoint ---------------------------------


def _quit_at(checkpoint: str, webview_mock, tmp_path, monkeypatch):
    """Run _boot with a booting quit arriving at ``checkpoint``."""
    import the_one.interfaces.desktop.host as host_mod

    def _quit_now(*_a, **_k):
        state.booting = True
        assert window_control.quit_desktop() == "booting"
        state.booting = False

    class _Loaded(_EventCapture):
        def __iadd__(self, handler):
            if checkpoint == "before-show":
                _quit_now()
            return super().__iadd__(handler)

    def _pre_boot(ns) -> None:
        if checkpoint == "after-splash":
            ns.splash.events.shown.wait.side_effect = _quit_now
        elif checkpoint == "after-server":
            ns.launcher._wait_until_serving.side_effect = _quit_now
        elif checkpoint == "before-show":
            ns.main.events.loaded = _Loaded()
        elif checkpoint == "step-6":
            monkeypatch.setattr(
                host_mod, "detect_tray", lambda backend: (_quit_now(), ("indicator", "x"))[1]
            )

    return _boot_harness(webview_mock, tmp_path, monkeypatch, pre_boot=_pre_boot)


@pytest.mark.parametrize("checkpoint", ["after-splash", "after-server", "before-show", "step-6"])
def test_boot_race_quit_is_honoured(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, checkpoint: str
) -> None:
    ns = _quit_at(checkpoint, webview_mock, tmp_path, monkeypatch)
    assert state.really_quit is True
    ns.splash.destroy.assert_called_once()
    if checkpoint in ("after-splash", "after-server"):
        ns.main.show.assert_not_called()
        ns.main.destroy.assert_not_called()  # never created
        webview_mock.create_window.assert_called_once()
    else:
        ns.main.destroy.assert_called_once()
    if checkpoint == "step-6":
        # the window was published, then the quit ran right after the lock
        assert state.desktop_window is ns.main
    else:
        assert state.desktop_window is None
    assert state.lock.locked() is False


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_quit_after_publish_before_page_loaded_destroys_the_splash(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    """Release dry run 40263206440 (L8/L9): a quit that arrives after the window is
    published but before its page's ``loaded`` fired destroyed only the main window.
    ``loaded`` never fires for a destroyed window, so the splash stayed alive,
    ``webview.start`` never returned and the server never drained."""
    sessions: list = []
    import the_one.interfaces.desktop.shell as launcher_module

    launcher_run = launcher_module.DesktopSession.run

    def _capturing_run(self):
        sessions.append(self)
        return launcher_run(self)

    monkeypatch.setattr(launcher_module.DesktopSession, "run", _capturing_run)
    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, platform=platform)
    assert state.desktop_window is ns.main and ns.loaded.is_set_value is False
    ns.splash.destroy.assert_not_called()  # the page has not loaded: the splash is up
    state.session = sessions[0]  # run() cleared it when the mocked start returned
    assert window_control.quit_desktop() == "window"
    ns.main.destroy.assert_called_once()
    ns.splash.destroy.assert_called_once()  # else webview.start() never returns


def test_boot_without_quit_publishes_and_clears_booting(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns = _boot_harness(webview_mock, tmp_path, monkeypatch)
    assert state.desktop_window is ns.main
    assert state.booting is False and state.really_quit is False
    ns.main.destroy.assert_not_called()


def test_booting_set_before_server_start_and_cleared_after_run(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}
    import the_one.interfaces.desktop.shell as shell_mod

    def _server(*a, **k):
        seen["booting_at_server"] = state.booting
        return MagicMock()

    monkeypatch.setattr(shell_mod.settings, "data_dir", tmp_path)
    webview_mock.create_window.side_effect = [_make_splash_mock()]
    with (
        patch.object(takeover, "_select_port", return_value=(8486, False)),
        patch.object(shell_mod, "_webview_available", return_value=True),
        patch.object(shell_mod, "_graceful_shutdown"),
        patch("the_one.interfaces.web.app.app", MagicMock()),
        patch("uvicorn.Server", side_effect=_server),
        patch("threading.Thread", return_value=MagicMock()),
    ):
        shell_mod.run_desktop()
    assert seen["booting_at_server"] is True
    assert state.booting is False  # run()'s finally


def test_missing_pywebview_clears_booting(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    import the_one.interfaces.desktop.shell as shell_mod

    monkeypatch.setitem(sys.modules, "webview", None)  # import raises ImportError
    monkeypatch.setattr(shell_mod.settings, "data_dir", tmp_path)
    with (
        patch.object(takeover, "_select_port", return_value=(8486, False)),
        patch.object(shell_mod, "_webview_available", return_value=True),
        patch.object(shell_mod, "_graceful_shutdown"),
        patch("the_one.interfaces.web.app.app", MagicMock()),
        patch("uvicorn.Server", return_value=MagicMock()),
        patch("threading.Thread", return_value=MagicMock()),
        pytest.raises(SystemExit),
    ):
        shell_mod.run_desktop()
    assert state.booting is False


def test_boot_error_clears_booting(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _pre_boot(ns) -> None:
        state.booting = True
        ns.launcher._wait_until_serving.side_effect = RuntimeError("no server")

    _boot_harness(
        webview_mock, tmp_path, monkeypatch, pre_boot=_pre_boot, expect_raises=RuntimeError
    )
    assert state.booting is False


# The browser-fallback branch ----------------------------------------------------


def test_browser_branch_records_server_and_honours_a_quit_during_the_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import webbrowser as webbrowser_mod

    import the_one.interfaces.desktop.shell as shell_mod

    opened: list = []
    seen: dict = {}
    server = MagicMock()
    server.should_exit = False

    def _wait(host, port, timeout=15.0):
        seen["mode"] = window_control.window_state()["mode"]
        seen["state"] = window_control.quit_desktop()  # the quit arrives mid-wait
        raise RuntimeError("server did not become ready")  # the drain made it fail

    monkeypatch.setattr(webbrowser_mod, "open", lambda u: opened.append(u))
    with (
        patch.object(takeover, "_select_port", return_value=(8486, False)),
        patch.object(shell_mod, "_webview_available", return_value=False),
        patch.object(shell_mod, "_graceful_shutdown"),
        patch.object(shell_mod, "_wait_until_serving", side_effect=_wait),
        patch("the_one.interfaces.web.app.app", MagicMock()),
        patch("uvicorn.Server", return_value=server),
        patch("threading.Thread", return_value=MagicMock()),
    ):
        shell_mod.run_desktop()
    assert seen == {"mode": "browser", "state": "browser"}
    assert opened == []
    assert server.should_exit is True
    assert state.browser_server is None  # cleared by run()'s finally


def test_browser_branch_entry_honours_a_quit_recorded_while_booting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import webbrowser as webbrowser_mod

    import the_one.interfaces.desktop.shell as shell_mod

    opened: list = []
    monkeypatch.setattr(webbrowser_mod, "open", lambda u: opened.append(u))
    wait = MagicMock()

    def _server(*a, **k):
        # a quit arrives while the server is being created (booting)
        assert window_control.quit_desktop() == "booting"
        return MagicMock()

    with (
        patch.object(takeover, "_select_port", return_value=(8486, False)),
        patch.object(shell_mod, "_webview_available", return_value=False),
        patch.object(shell_mod, "_graceful_shutdown"),
        patch.object(shell_mod, "_wait_until_serving", wait),
        patch("the_one.interfaces.web.app.app", MagicMock()),
        patch("uvicorn.Server", side_effect=_server),
        patch("threading.Thread", return_value=MagicMock()),
    ):
        shell_mod.run_desktop()
    wait.assert_not_called()
    assert opened == []


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_non_darwin_shows_immediately_without_waiting_for_loaded(
    webview_mock: MagicMock,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    platform: str,
) -> None:
    """HAT P1 is darwin-only: other platforms show before `loaded` (unchanged ordering)."""
    caplog.set_level("INFO")
    ns = _boot_harness(webview_mock, tmp_path, monkeypatch, platform=platform, loaded_is_set=False)
    assert ns.order.count("show") == 1
    assert not [r for r in caplog.records if r.getMessage().startswith("macos: main")]


# ── splash HTML size (squawk 0263) ───────────────────────────────────────────

# WebView2's NavigateToString rejects HTML over ~2 MB, which the full 1024 px logo
# (2.3 M characters as a data URI) overran on Windows. The ceiling is far under that
# limit yet leaves room for a 2x-density logo; a regression to a big asset trips it.
_SPLASH_HTML_CEILING = 256 * 1024


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_splash_html_stays_under_navigate_to_string_limit(theme: str) -> None:
    from the_one.interfaces.desktop.shell import _splash_html

    html = _splash_html(theme)
    assert len(html) < _SPLASH_HTML_CEILING
    assert 'src="data:image/png;base64,' in html  # the logo is still embedded


def test_destroy_splash_claims_teardown_atomically(
    webview_mock: MagicMock, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two threads calling the session's splash teardown destroy the window once."""
    import the_one.interfaces.desktop.shell as launcher_module

    monkeypatch.setattr(launcher_module.settings, "data_dir", tmp_path)
    splash = _make_splash_mock()
    gate = threading.Barrier(2, timeout=5)
    calls: list[int] = []

    def _slow_destroy() -> None:
        calls.append(1)
        gate.wait()  # hold the first caller inside destroy() until the second has run

    splash.destroy.side_effect = _slow_destroy
    webview_mock.create_window.side_effect = [splash, MagicMock()]
    session = launcher_module.DesktopSession()
    with patch.object(takeover, "_select_port", return_value=(8484, False)):
        with patch.object(launcher_module, "_webview_available", return_value=True):
            with patch.object(launcher_module, "_graceful_shutdown"):
                with patch("the_one.interfaces.web.app.app", MagicMock()):
                    with patch("uvicorn.Server", return_value=MagicMock()):
                        with patch("threading.Thread", return_value=MagicMock()):
                            session.run()
    assert session._destroy_splash is not None
    results = [_RealThread(target=session._destroy_splash) for _ in range(2)]
    for t in results:
        t.start()
    # the second caller must return without destroying; release the first one
    for t in results:
        t.join(0.5)
    try:
        gate.wait(timeout=1)
    except threading.BrokenBarrierError:
        pass
    for t in results:
        t.join(5)
    assert len(calls) == 1
