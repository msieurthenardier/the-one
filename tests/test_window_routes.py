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
    from the_one.interfaces.desktop.session_state import state

    with (
        patch.object(state, "desktop_window", None),
        patch.object(state, "session", None),
        _client() as c,
    ):
        r = c.get("/api/window/state", headers=auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["desktop"] is False and body["mode"] == "serve"
    assert body["visible"] is None and body["pid"] == os.getpid()


def test_state_with_window():
    from the_one.interfaces.desktop import window_control
    from the_one.interfaces.desktop.session_state import state

    with (
        patch.object(state, "desktop_window", object()),
        patch.object(state, "session", object()),
        patch.object(window_control, "window_visible", return_value=True),
        patch.object(window_control, "_window_mapped", return_value=True),
        _client() as c,
    ):
        body = c.get("/api/window/state", headers=auth_headers()).json()
    assert body["desktop"] is True and body["mode"] == "window"
    assert body["visible"] is True and body["mapped"] is True


def test_quit_without_window_and_with():
    from the_one.interfaces.desktop import window_control
    from the_one.interfaces.desktop.session_state import state

    with patch.object(state, "desktop_window", None), _client() as c:
        r = c.post("/api/window/quit", headers=auth_headers())
    assert r.json() == {"quit": False, "pid": os.getpid(), "state": None}
    for tag in ("window", "booting", "browser"):
        with patch.object(window_control, "quit_desktop", return_value=tag), _client() as c:
            r = c.post("/api/window/quit", headers=auth_headers())
        assert r.json() == {"quit": True, "pid": os.getpid(), "state": tag}


def test_quit_never_500s_on_gui_error():
    from the_one.interfaces.desktop import window_control

    with (
        patch.object(window_control, "quit_desktop", side_effect=RuntimeError("gui")),
        _client() as c,
    ):
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
    from the_one.interfaces.desktop import window_control

    with (
        patch.object(window_control, "window_state", side_effect=RuntimeError("gui")),
        _client() as c,
    ):
        body = c.get("/api/window/state", headers=auth_headers()).json()
    assert body["mode"] == "serve" and body["desktop"] is False and body["pid"] == os.getpid()
