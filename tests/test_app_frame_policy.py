"""M35 F2 L1 (DD3, AC7): ``GET /`` carries ``frame-src 'none'; child-src 'none'`` so a widget
frame cannot navigate itself; the OAuth callback page (inline scripts) carries no such header."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from tests._credential_helpers import auth_headers
from the_one.interfaces.web import app as app_mod
from the_one.interfaces.web.app import FRAME_POLICY, app

pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")


def test_constant_is_exactly_the_two_directives() -> None:
    assert FRAME_POLICY == "frame-src 'none'; child-src 'none'"


@pytest.mark.parametrize("dev_mode", [False, True])
def test_index_carries_the_frame_policy_and_keeps_no_store(monkeypatch, dev_mode) -> None:
    monkeypatch.setattr(app_mod.settings, "dev_mode", dev_mode)
    app_mod._production_index_html.cache_clear()
    try:
        with TestClient(app, headers=auth_headers()) as client:
            response = client.get("/")
    finally:
        app_mod._production_index_html.cache_clear()
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == FRAME_POLICY
    assert response.headers["cache-control"] == "no-store"


def test_oauth_callback_has_no_csp_header() -> None:
    with TestClient(app, headers=auth_headers()) as client:
        response = client.get("/api/oauth/callback", params={"state": "nope", "code": "c"})
    assert "content-security-policy" not in response.headers
