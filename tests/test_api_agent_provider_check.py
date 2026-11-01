"""Squawk 0277: an agent's unknown provider id is a 422 on the field, not a 500."""

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

MSG = [
    {
        "type": "value_error",
        "loc": ["provider_config_id"],
        "msg": "That model provider doesn't exist.",
    }
]


@pytest.fixture
async def client(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            c.conn = conn  # type: ignore[attr-defined]
            yield c
    await conn.close()


async def _provider(client) -> str:
    resp = await client.post(
        "/api/providers",
        json={"name": "p", "type": "openai-compatible", "base_url": "http://localhost:11434/v1"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _count(client) -> int:
    async with client.conn.execute("SELECT COUNT(*) FROM agents") as cur:
        return (await cur.fetchone())[0]


@pytest.mark.parametrize("bad", ["", "no-such-provider"])
async def test_create_with_bad_provider_is_422_and_no_row(client, bad) -> None:
    resp = await client.post("/api/agents", json={"name": "a", "provider_config_id": bad})
    assert resp.status_code == 422 and resp.json()["detail"] == MSG
    assert await _count(client) == 0


async def test_create_without_provider_and_with_real_provider(client) -> None:
    assert (await client.post("/api/agents", json={"name": "none"})).status_code == 201
    explicit = await client.post("/api/agents", json={"name": "null", "provider_config_id": None})
    assert explicit.status_code == 201
    pid = await _provider(client)
    resp = await client.post("/api/agents", json={"name": "real", "provider_config_id": pid})
    assert resp.status_code == 201 and resp.json()["provider_config_id"] == pid


async def test_update_unknown_provider_is_422_and_row_unchanged(client) -> None:
    pid = await _provider(client)
    await client.post("/api/agents", json={"name": "a", "provider_config_id": pid})
    resp = await client.put("/api/agents/a", json={"provider_config_id": "ghost"})
    assert resp.status_code == 422 and resp.json()["detail"] == MSG
    assert (await client.get("/api/agents/a")).json()["provider_config_id"] == pid


async def test_update_round_trips_a_deleted_provider(client) -> None:
    pid = await _provider(client)
    await client.post("/api/agents", json={"name": "a", "provider_config_id": pid})
    await client.conn.execute("PRAGMA foreign_keys=OFF")
    await client.conn.execute("DELETE FROM llm_providers WHERE id = ?", (pid,))
    await client.conn.commit()
    got = (await client.get("/api/agents/a")).json()
    got["description"] = "still editable"
    resp = await client.put("/api/agents/a", json=got)
    assert resp.status_code == 200 and resp.json()["provider_config_id"] == pid
    # Choosing a different (unknown) provider is still checked.
    got["provider_config_id"] = "other-ghost"
    assert (await client.put("/api/agents/a", json=got)).status_code == 422
