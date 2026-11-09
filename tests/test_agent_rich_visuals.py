"""M35 F1 L03 (DD11): the per-agent `rich_visuals` switch.

Model default, repository round trip (including the load-then-save regression), the
API create/update/omit/invalid shapes, and the self-configuration projection omission.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.repositories import (
    KnowledgeBaseRepository,
    LLMProviderRepository,
    SQLiteAgentStore,
)
from the_one.encryption import Encryptor
from the_one.self_configuration.projection import build_get_my_configuration


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "rv.db")
    yield c
    await c.close()


@pytest.fixture
async def client(tmp_path):
    c = await connect_template_db(tmp_path / "rv_api.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=c),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as http:
            yield http
    await c.close()


def test_model_default_is_on() -> None:
    assert AgentConfig(name="a").rich_visuals is True
    assert AgentConfig.model_validate({"name": "a"}).rich_visuals is True


async def test_repository_round_trip(conn) -> None:
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="off", rich_visuals=False))
    await store.save(AgentConfig(name="on", rich_visuals=True))
    assert (await store.load("off")).rich_visuals is False
    assert (await store.load("on")).rich_visuals is True


async def test_stored_false_survives_an_unrelated_save(conn) -> None:
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="a", rich_visuals=False))
    cfg = await store.load("a")
    cfg.description = "changed"
    await store.save(cfg)
    again = await store.load("a")
    assert again.description == "changed"
    assert again.rich_visuals is False


async def test_api_create_default_and_explicit(client) -> None:
    r = await client.post("/api/agents", json={"name": "d1", "description": "x"})
    assert r.status_code == 201 and r.json()["rich_visuals"] is True
    r = await client.post(
        "/api/agents", json={"name": "d2", "description": "x", "rich_visuals": False}
    )
    assert r.status_code == 201 and r.json()["rich_visuals"] is False
    assert (await client.get("/api/agents/d2")).json()["rich_visuals"] is False
    rows = {a["name"]: a for a in (await client.get("/api/agents")).json()}
    assert rows["d1"]["rich_visuals"] is True and rows["d2"]["rich_visuals"] is False


@pytest.mark.parametrize("start", [True, False])
async def test_api_put_omit_keeps_stored_value(client, start) -> None:
    await client.post("/api/agents", json={"name": "a", "rich_visuals": start})
    r = await client.put("/api/agents/a", json={"name": "a", "description": "changed"})
    assert r.status_code == 200, r.text
    assert r.json()["rich_visuals"] is start
    assert (await client.get("/api/agents/a")).json()["rich_visuals"] is start


async def test_api_put_sets_value(client) -> None:
    await client.post("/api/agents", json={"name": "a"})
    r = await client.put("/api/agents/a", json={"name": "a", "rich_visuals": False})
    assert r.status_code == 200 and r.json()["rich_visuals"] is False
    r = await client.put("/api/agents/a", json={"name": "a", "rich_visuals": True})
    assert r.status_code == 200 and r.json()["rich_visuals"] is True


@pytest.mark.parametrize("bad", ["abc", None])
async def test_api_put_invalid_is_422_without_echo(client, bad) -> None:
    await client.post("/api/agents", json={"name": "a", "rich_visuals": False})
    r = await client.put("/api/agents/a", json={"name": "a", "rich_visuals": bad})
    assert r.status_code == 422, r.text
    assert "rich_visuals" in r.text
    if bad:
        assert '"input"' not in r.text
    assert (await client.get("/api/agents/a")).json()["rich_visuals"] is False


async def test_api_create_invalid_is_422(client) -> None:
    r = await client.post("/api/agents", json={"name": "a", "rich_visuals": "abc"})
    assert r.status_code == 422


async def test_projection_omits_rich_visuals(conn) -> None:
    out = await build_get_my_configuration(
        AgentConfig(name="a", rich_visuals=False),
        provider_repo=LLMProviderRepository(conn, None),
        kb_repo=KnowledgeBaseRepository(conn),
    )
    assert "rich_visuals" not in out
    assert "visuals" not in str(out).lower()
