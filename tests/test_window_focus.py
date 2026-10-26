"""Tests for the POST /api/window/focus endpoint and supporting focus_window() function.

Covers:
  - focus_window() returns True when a desktop window is registered (show + restore called).
  - focus_window() returns False (no-op) when no window is registered.
  - focus_window() returns False and logs when show()/restore() raise.
  - POST /api/window/focus returns 200 {"focused": true} when window is registered.
  - POST /api/window/focus returns 200 {"focused": false} when no window is registered.
  - A header-less POST to /api/window/focus is NOT rejected by OriginAllowlistMiddleware
    (returns 200, not 403).
  - run_desktop() on is_ours=True POSTs to /api/window/focus (no Origin header) and
    returns without creating a window.
  - run_desktop() on is_ours=True still returns cleanly even when httpx.post raises.

Uses starlette.testclient.TestClient (already transitive via FastAPI).
webview is NOT installed on this host — mocked via unittest.mock.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from tests._credential_helpers import auth_headers

# ``with TestClient(app)`` (endpoint tests below) drives the REAL lifespan to
# shutdown, which latches ``_shutting_down = True`` in the PTY session
# registry, MCP pool, and connector pool. Reset those process-globals after
# each test so later modules don't inherit the latch (M17 F1 L4
# ordering-flake fix; fixture lives in tests/conftest.py).
pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")

# ── focus_window() unit tests ─────────────────────────────────────────────────


def test_focus_window_returns_false_when_no_window() -> None:
    """focus_window() returns False when _desktop_window is None (serve mode / no window)."""
    from the_one.interfaces.desktop import window_control
    from the_one.interfaces.desktop.session_state import state

    state.desktop_window = None

    result = window_control.focus_window()

    assert result is False


def test_focus_window_calls_show_restore_and_returns_true() -> None:
    """focus_window() calls show() and restore() on the registered window and returns True."""
    from the_one.interfaces.desktop import window_control
    from the_one.interfaces.desktop.session_state import state

    mock_window = MagicMock()
    state.desktop_window = mock_window

    result = window_control.focus_window()

    assert result is True
    mock_window.show.assert_called_once()
    mock_window.restore.assert_called_once()


def test_focus_window_returns_false_and_logs_on_exception() -> None:
    """focus_window() catches show()/restore() exceptions, logs, and returns False."""
    from the_one.interfaces.desktop import window_control
    from the_one.interfaces.desktop.session_state import state

    mock_window = MagicMock()
    mock_window.show.side_effect = RuntimeError("show failed")
    state.desktop_window = mock_window

    result = window_control.focus_window()

    assert result is False


# ── POST /api/window/focus endpoint tests ─────────────────────────────────────


def test_window_focus_endpoint_returns_focused_true_when_window_registered() -> None:
    """POST /api/window/focus returns 200 {"focused": true} when focus_window() → True."""
    from the_one.interfaces.web.app import app

    with patch("the_one.interfaces.desktop.window_control.focus_window", return_value=True):
        with TestClient(app, headers=auth_headers()) as client:
            response = client.post("/api/window/focus")

    assert response.status_code == 200
    assert response.json() == {"focused": True}


def test_window_focus_endpoint_returns_focused_false_when_no_window() -> None:
    """POST /api/window/focus returns 200 {"focused": false} when focus_window() → False."""
    from the_one.interfaces.web.app import app

    with patch("the_one.interfaces.desktop.window_control.focus_window", return_value=False):
        with TestClient(app, headers=auth_headers()) as client:
            response = client.post("/api/window/focus")

    assert response.status_code == 200
    assert response.json() == {"focused": False}


def test_window_focus_endpoint_header_less_post_not_rejected() -> None:
    """A header-less POST to /api/window/focus is not rejected by OriginAllowlistMiddleware.

    The middleware gates state-mutating methods only when an Origin header IS present
    and not allow-listed. A header-less request (no Origin) passes through (DD4).
    """
    from the_one.interfaces.web.app import app

    with patch("the_one.interfaces.desktop.window_control.focus_window", return_value=False):
        with TestClient(app, headers=auth_headers()) as client:
            # Explicitly send no Origin header (TestClient default)
            response = client.post("/api/window/focus")

    assert response.status_code == 200, (
        f"Header-less POST should pass middleware but got {response.status_code}"
    )


# ── run_desktop() focus-and-exit branch tests ─────────────────────────────────


def test_run_desktop_is_ours_posts_focus_url_and_returns() -> None:
    """run_desktop() on is_ours=True POSTs to /api/window/focus and returns without a window."""
    import httpx

    import the_one.interfaces.desktop.shell as shell_mod
    import the_one.interfaces.desktop.takeover as takeover_mod

    webview_mock = MagicMock()
    sys.modules["webview"] = webview_mock

    try:
        with (
            patch.object(takeover_mod, "_select_port", return_value=(8484, True)),
            patch.object(takeover_mod, "_running_version", return_value=None),
        ):
            with patch.object(httpx, "post") as mock_post:
                with patch("uvicorn.Server") as mock_server_cls:
                    shell_mod.run_desktop()

        # No server started
        mock_server_cls.assert_not_called()

        # No window created
        webview_mock.create_window.assert_not_called()

        # httpx.post called with the focus endpoint URL
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.args[0] == "http://127.0.0.1:8484/api/window/focus"

        # No Origin header passed (header-less loopback POST)
        headers = call_args.kwargs.get("headers", {})
        assert "origin" not in {k.lower() for k in headers}

    finally:
        sys.modules.pop("webview", None)


def test_run_desktop_is_ours_returns_cleanly_when_post_raises() -> None:
    """run_desktop() exits cleanly (no window, no crash) when focus POST raises httpx.HTTPError."""
    import httpx

    import the_one.interfaces.desktop.shell as shell_mod
    import the_one.interfaces.desktop.takeover as takeover_mod

    webview_mock = MagicMock()
    sys.modules["webview"] = webview_mock

    try:
        with (
            patch.object(takeover_mod, "_select_port", return_value=(8484, True)),
            patch.object(takeover_mod, "_running_version", return_value=None),
        ):
            with patch.object(httpx, "post", side_effect=httpx.ConnectError("refused")):
                with patch("uvicorn.Server") as mock_server_cls:
                    # Must not raise
                    shell_mod.run_desktop()

        # Still no server, no window
        mock_server_cls.assert_not_called()
        webview_mock.create_window.assert_not_called()

    finally:
        sys.modules.pop("webview", None)


# ── activation token (M32 F2 L05 phase B) ─────────────────────────────────────


def test_focus_route_accepts_token_body_and_no_body() -> None:
    from the_one.interfaces.web.app import app

    with patch("the_one.interfaces.desktop.window_control.focus_window", return_value=True) as fw:
        with TestClient(app, headers=auth_headers()) as client:
            assert client.post("/api/window/focus").status_code == 200
            fw.assert_called_once_with()
            fw.reset_mock()
            r = client.post("/api/window/focus", json={"activation_token": "tok123"})
            assert r.status_code == 200
            fw.assert_called_once_with("tok123")
            fw.reset_mock()
            assert client.post("/api/window/focus", json={}).status_code == 200
            fw.assert_called_once_with()


@pytest.mark.parametrize(
    "token", ["has space", "x" * 257, "tab\there", "ctl\x01x", "nl\nx", "caf\u00e9"]
)
def test_focus_route_rejects_bad_token(token: str) -> None:
    from the_one.interfaces.web.app import app

    with patch("the_one.interfaces.desktop.window_control.focus_window", return_value=True) as fw:
        with TestClient(app, headers=auth_headers()) as client:
            r = client.post("/api/window/focus", json={"activation_token": token})
    assert r.status_code == 422
    fw.assert_not_called()


def test_focus_window_gtk_token_one_idle_set_startup_id_deiconify_present() -> None:
    import types

    from the_one.interfaces.desktop import window_control
    from the_one.interfaces.desktop.session_state import state

    idles: list = []
    gtkmod = types.SimpleNamespace(glib=types.SimpleNamespace(idle_add=idles.append))
    window = MagicMock()
    calls: list[str] = []
    window.native.set_startup_id.side_effect = lambda t: calls.append(f"sid:{t}")
    window.native.deiconify.side_effect = lambda: calls.append("deiconify")
    window.native.present.side_effect = lambda: calls.append("present")
    with (
        patch.object(state, "desktop_window", window),
        patch.object(window_control, "_is_gtk_backend", return_value=True),
        patch.dict(
            sys.modules,
            {"webview.platforms.gtk": gtkmod, "webview.platforms": MagicMock(gtk=gtkmod)},
        ),
    ):
        assert window_control.focus_window("TOKEN123") is True
        assert len(idles) == 1  # exactly one idle, nothing else queued
        window.show.assert_not_called()
        window.restore.assert_not_called()
        assert calls == []  # nothing ran before the idle
        assert idles[0]() is False
    assert calls == ["sid:TOKEN123", "deiconify", "present"]
    assert window.hidden is False


def test_focus_window_no_token_uses_plain_path() -> None:
    from the_one.interfaces.desktop import window_control
    from the_one.interfaces.desktop.session_state import state

    window = MagicMock()
    with (
        patch.object(state, "desktop_window", window),
        patch.object(window_control, "_is_gtk_backend", return_value=True),
    ):
        assert window_control.focus_window() is True
    window.show.assert_called_once()
    window.restore.assert_called_once()
