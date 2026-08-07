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
    import importlib

    import the_one.interfaces.desktop.shell as shell_mod

    importlib.reload(shell_mod)
    shell_mod._desktop_window = None

    result = shell_mod.focus_window()

    assert result is False


def test_focus_window_calls_show_restore_and_returns_true() -> None:
    """focus_window() calls show() and restore() on the registered window and returns True."""
    import importlib

    import the_one.interfaces.desktop.shell as shell_mod

    importlib.reload(shell_mod)
    mock_window = MagicMock()
    shell_mod._desktop_window = mock_window

    result = shell_mod.focus_window()

    assert result is True
    mock_window.show.assert_called_once()
    mock_window.restore.assert_called_once()


def test_focus_window_returns_false_and_logs_on_exception() -> None:
    """focus_window() catches show()/restore() exceptions, logs, and returns False."""
    import importlib

    import the_one.interfaces.desktop.shell as shell_mod

    importlib.reload(shell_mod)
    mock_window = MagicMock()
    mock_window.show.side_effect = RuntimeError("show failed")
    shell_mod._desktop_window = mock_window

    result = shell_mod.focus_window()

    assert result is False


# ── POST /api/window/focus endpoint tests ─────────────────────────────────────


def test_window_focus_endpoint_returns_focused_true_when_window_registered() -> None:
    """POST /api/window/focus returns 200 {"focused": true} when focus_window() → True."""
    from the_one.interfaces.web.app import app

    with patch("the_one.interfaces.desktop.shell.focus_window", return_value=True):
        with TestClient(app, headers=auth_headers()) as client:
            response = client.post("/api/window/focus")

    assert response.status_code == 200
    assert response.json() == {"focused": True}


def test_window_focus_endpoint_returns_focused_false_when_no_window() -> None:
    """POST /api/window/focus returns 200 {"focused": false} when focus_window() → False."""
    from the_one.interfaces.web.app import app

    with patch("the_one.interfaces.desktop.shell.focus_window", return_value=False):
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

    with patch("the_one.interfaces.desktop.shell.focus_window", return_value=False):
        with TestClient(app, headers=auth_headers()) as client:
            # Explicitly send no Origin header (TestClient default)
            response = client.post("/api/window/focus")

    assert response.status_code == 200, (
        f"Header-less POST should pass middleware but got {response.status_code}"
    )


# ── run_desktop() focus-and-exit branch tests ─────────────────────────────────


def test_run_desktop_is_ours_posts_focus_url_and_returns() -> None:
    """run_desktop() on is_ours=True POSTs to /api/window/focus and returns without a window."""
    import importlib

    import httpx

    import the_one.interfaces.desktop.shell as shell_mod

    importlib.reload(shell_mod)

    webview_mock = MagicMock()
    sys.modules["webview"] = webview_mock

    try:
        with patch.object(shell_mod, "_select_port", return_value=(8484, True)):
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
    import importlib

    import httpx

    import the_one.interfaces.desktop.shell as shell_mod

    importlib.reload(shell_mod)

    webview_mock = MagicMock()
    sys.modules["webview"] = webview_mock

    try:
        with patch.object(shell_mod, "_select_port", return_value=(8484, True)):
            with patch.object(httpx, "post", side_effect=httpx.ConnectError("refused")):
                with patch("uvicorn.Server") as mock_server_cls:
                    # Must not raise
                    shell_mod.run_desktop()

        # Still no server, no window
        mock_server_cls.assert_not_called()
        webview_mock.create_window.assert_not_called()

    finally:
        sys.modules.pop("webview", None)
