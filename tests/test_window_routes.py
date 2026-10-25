"""Tests for GET /api/window/state and POST /api/window/quit (M32 F2 L03)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from tests._credential_helpers import auth_headers

pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")


def _client():
    from the_one.interfaces.web.app import app

    return TestClient(app)


def test_state_without_window():
    import the_one.interfaces.desktop.shell as shell

    with (
        patch.object(shell, "_desktop_window", None),
        patch.object(shell, "_session", None),
        _client() as c,
    ):
        r = c.get("/api/window/state", headers=auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["desktop"] is False and body["mode"] == "serve"
    assert body["visible"] is None and body["pid"] == os.getpid()


def test_state_with_window():
    import the_one.interfaces.desktop.shell as shell

    with (
        patch.object(shell, "_desktop_window", object()),
        patch.object(shell, "_session", object()),
        patch.object(shell, "window_visible", return_value=True),
        patch.object(shell, "_window_mapped", return_value=True),
        _client() as c,
    ):
        body = c.get("/api/window/state", headers=auth_headers()).json()
    assert body["desktop"] is True and body["mode"] == "window"
    assert body["visible"] is True and body["mapped"] is True


def test_quit_without_window_and_with():
    import the_one.interfaces.desktop.shell as shell

    with patch.object(shell, "_desktop_window", None), _client() as c:
        r = c.post("/api/window/quit", headers=auth_headers())
    assert r.json() == {"quit": False, "pid": os.getpid(), "state": None}
    for state in ("window", "booting", "browser"):
        with patch.object(shell, "quit_desktop", return_value=state), _client() as c:
            r = c.post("/api/window/quit", headers=auth_headers())
        assert r.json() == {"quit": True, "pid": os.getpid(), "state": state}


def test_quit_never_500s_on_gui_error():
    import the_one.interfaces.desktop.shell as shell

    with patch.object(shell, "quit_desktop", side_effect=RuntimeError("gui")), _client() as c:
        r = c.post("/api/window/quit", headers=auth_headers())
    assert r.status_code == 200 and r.json()["quit"] is False


def test_credential_required():
    with _client() as c:
        assert c.get("/api/window/state").status_code == 401
        assert c.post("/api/window/quit").status_code == 401


def test_routes_are_plain_defs():
    import inspect

    from the_one.interfaces.web import app as appmod

    for fn in (appmod.window_state_get, appmod.window_quit, appmod.window_focus):
        assert not inspect.iscoroutinefunction(fn)


def test_state_except_fallback_reports_serve():
    import the_one.interfaces.desktop.shell as shell

    with patch.object(shell, "window_state", side_effect=RuntimeError("gui")), _client() as c:
        body = c.get("/api/window/state", headers=auth_headers()).json()
    assert body["mode"] == "serve" and body["desktop"] is False and body["pid"] == os.getpid()
