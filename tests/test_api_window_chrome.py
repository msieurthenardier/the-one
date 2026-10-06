"""Routes POST/GET /api/window/chrome (M25 F5 L2)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from tests._credential_helpers import auth_headers

pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")


@pytest.fixture()
def client() -> Any:
    from the_one.interfaces.web.app import app

    with TestClient(app, headers=auth_headers()) as c:
        yield c


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_post_theme_without_desktop_session(client: Any, theme: str) -> None:
    r = client.post("/api/window/chrome", json={"theme": theme})
    assert r.status_code == 200
    assert r.json() == {"theme": theme, "desktop": False, "tinted": False}


@pytest.mark.parametrize("body", [{"theme": "blue"}, {}, {"theme": None}])
def test_post_invalid_body_is_422(client: Any, body: dict) -> None:
    assert client.post("/api/window/chrome", json=body).status_code == 422


def test_post_writes_no_file_without_a_desktop_session(client: Any, tmp_path: Any) -> None:
    from the_one.config import settings

    client.post("/api/window/chrome", json={"theme": "dark"})
    assert not (settings.data_dir / "window-chrome.json").exists()


@pytest.mark.parametrize("tinted", [True, False, "pending"])
def test_post_reports_tinted_from_set_window_theme(client: Any, tinted: Any) -> None:
    fake = {"theme": "dark", "desktop": True, "tinted": tinted}
    with patch("the_one.interfaces.desktop.shell.set_window_theme", return_value=fake) as m:
        r = client.post("/api/window/chrome", json={"theme": "dark"})
    m.assert_called_once_with("dark")
    assert r.status_code == 200 and r.json() == fake


def test_post_with_a_registered_window_reports_tinted(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from the_one.interfaces.desktop import chrome

    monkeypatch.setattr(chrome, "_native_enabled", lambda: True)
    monkeypatch.setattr(chrome, "windows_build", lambda: 26100)
    monkeypatch.setattr(chrome, "_hwnd_of", lambda f: 1)
    monkeypatch.setattr(chrome, "_dwm_set", lambda h, a, v: 0)
    monkeypatch.setattr(chrome, "_subscribe_activation", lambda *a: None)
    monkeypatch.setattr(chrome, "_invoke_ui", lambda f, fn: (fn(), "done")[1])
    win = type("W", (), {"native": type("F", (), {"IsDisposed": False})()})()
    chrome.register(win, "light")
    r = client.post("/api/window/chrome", json={"theme": "dark"})
    assert r.json()["tinted"] is True
    snap = client.get("/api/window/chrome").json()
    assert snap["last_applied"]["theme"] == "dark" and snap["pending"] is False


def test_get_returns_the_snapshot_shape(client: Any) -> None:
    r = client.get("/api/window/chrome")
    assert r.status_code == 200
    body = r.json()
    assert {"enabled", "registered", "requested", "pending", "last_applied", "supported"} <= set(
        body
    )
    assert body["pending"] is False and body["last_applied"] is None


def test_both_routes_require_a_credential() -> None:
    from the_one.interfaces.web.app import app

    with TestClient(app) as bare:
        assert bare.post("/api/window/chrome", json={"theme": "dark"}).status_code == 401
        assert bare.get("/api/window/chrome").status_code == 401
