"""Malformed JSON bodies are a plain 422, never a 500 (squawk 0184)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router

BAD = b'{"secret-marker": '
PLAIN = "Request body is not valid JSON."


@pytest.fixture
async def client(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
    ):
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            yield c
    await conn.close()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", "/api/knowledge-settings"),
        ("POST", "/api/agents"),
        ("POST", "/api/providers"),
    ],
)
async def test_malformed_json_is_422(client: AsyncClient, method: str, path: str) -> None:
    r = await client.request(
        method, path, content=BAD, headers={"content-type": "application/json"}
    )
    assert r.status_code == 422
    assert r.json() == {"detail": PLAIN}
    assert "secret-marker" not in r.text


@pytest.mark.parametrize("body", ["[]", "5", '"x"', "null"])
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", "/api/knowledge-settings"),
        ("POST", "/api/agents"),
        ("POST", "/api/providers"),
        ("POST", "/api/knowledge-bases"),
        ("POST", "/api/mcp-sources"),
        ("POST", "/api/connectors"),
    ],
)
async def test_non_object_json_is_422(
    client: AsyncClient, method: str, path: str, body: str
) -> None:
    r = await client.request(
        method, path, content=body, headers={"content-type": "application/json"}
    )
    assert r.status_code == 422
    assert r.json() == {"detail": "Request body must be a JSON object."}


async def test_time_settings_keeps_its_own_sentence(client: AsyncClient) -> None:
    r = await client.put(
        "/api/time-settings", content=BAD, headers={"content-type": "application/json"}
    )
    assert r.status_code == 422
    assert r.json() == {"detail": "Body must be a JSON object."}


async def test_unauthenticated_malformed_request_stays_401() -> None:
    from the_one.interfaces.web.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.put(
            "/api/knowledge-settings", content=BAD, headers={"content-type": "application/json"}
        )
    assert r.status_code == 401
