"""GleepGlorp's settings, routes, provider usage and retention (M36 F1 L03)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db.models import ChatSession
from the_one.db.repositories import AppMetadataRepository, ChatSessionRepository
from the_one.encryption import Encryptor
from the_one.gleepglorp import (
    SETTING_KEY,
    GleepGlorpSettings,
    load_settings,
    save_settings,
)
from the_one.gleepglorp import state as derive_state
from the_one.retention import run_purge_sweep

_PROVIDER = {"type": "ollama", "base_url": "http://localhost:11434/v1", "name": "P"}


@pytest.fixture
async def conn(tmp_path):
    connection = await connect_template_db(tmp_path / "test.db")
    yield connection
    await connection.close()


@pytest.fixture
async def client(conn, tmp_path):
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as c:
            yield c


async def _provider(client) -> str:
    resp = await client.post("/api/providers", json=_PROVIDER)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _body(**over):
    base = {
        "enabled": True,
        "provider_config_id": None,
        "model": None,
        "web_access": True,
        "memory": True,
        "retention_days": 30,
    }
    return {**base, **over}


class TestGet:
    async def test_defaults(self, client) -> None:
        resp = await client.get("/api/gleepglorp")
        assert resp.status_code == 200
        assert resp.json() == {**_body(), "state": "needs_model", "web_search_available": True}

    async def test_a_bad_stored_value_loads_as_the_defaults(self, client, conn, caplog) -> None:
        await AppMetadataRepository(conn).set(SETTING_KEY, '{"retention_days": "soon"}')
        with caplog.at_level("WARNING"):
            resp = await client.get("/api/gleepglorp")
        assert resp.status_code == 200
        assert resp.json() == {**_body(), "state": "needs_model", "web_search_available": True}
        assert "invalid" in caplog.text


class TestState:
    async def test_the_four_states(self, client, conn) -> None:
        pid = await _provider(client)
        off = await client.put("/api/gleepglorp", json=_body(enabled=False))
        assert off.json()["state"] == "off"
        needs = await client.put("/api/gleepglorp", json=_body(provider_config_id=pid))
        assert needs.json()["state"] == "needs_model"
        ready = await client.put("/api/gleepglorp", json=_body(provider_config_id=pid, model="m1"))
        assert ready.status_code == 200
        assert ready.json() == {
            **_body(provider_config_id=pid, model="m1"),
            "state": "ready",
            "web_search_available": True,
        }
        await conn.execute("DELETE FROM llm_providers WHERE id = ?", (pid,))
        await conn.commit()
        assert (await client.get("/api/gleepglorp")).json()["state"] == "provider_missing"

    async def test_off_wins_over_everything(self, conn) -> None:
        s = GleepGlorpSettings(enabled=False, provider_config_id="gone", model="m")
        assert await derive_state(conn, s) == "off"


class TestPutRefuses:
    @staticmethod
    def _loc(resp) -> list:
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        for row in detail:
            assert set(row) == {"type", "loc", "msg"}
        return [row["loc"] for row in detail]

    @pytest.mark.parametrize("body", [[], "text", 5, None])
    async def test_not_an_object(self, client, body) -> None:
        assert self._loc(await client.put("/api/gleepglorp", json=body)) == [[]]

    async def test_malformed_json(self, client) -> None:
        resp = await client.put(
            "/api/gleepglorp", content=b'{"x": ', headers={"content-type": "application/json"}
        )
        assert self._loc(resp) == [[]]

    async def test_unknown_key(self, client) -> None:
        resp = await client.put("/api/gleepglorp", json=_body(speed=9))
        assert self._loc(resp) == [["speed"]]

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("enabled", "yes"),
            ("web_access", 1),
            ("memory", None),
            ("retention_days", "30"),
            ("retention_days", 30.5),
            ("model", 5),
            ("provider_config_id", 5),
        ],
    )
    async def test_wrong_type(self, client, key, value) -> None:
        resp = await client.put("/api/gleepglorp", json=_body(**{key: value}))
        assert self._loc(resp) == [[key]]
        assert (await client.get("/api/gleepglorp")).json() == {
            **_body(),
            "state": "needs_model",
            "web_search_available": True,
        }

    @pytest.mark.parametrize("days", [0, -1, 366, 10_000])
    async def test_retention_out_of_range(self, client, days) -> None:
        resp = await client.put("/api/gleepglorp", json=_body(retention_days=days))
        assert self._loc(resp) == [["retention_days"]]

    @pytest.mark.parametrize("days", [1, 365])
    async def test_retention_bounds_are_allowed(self, client, days) -> None:
        resp = await client.put("/api/gleepglorp", json=_body(retention_days=days))
        assert resp.status_code == 200
        assert resp.json()["retention_days"] == days

    async def test_unknown_provider(self, client) -> None:
        resp = await client.put("/api/gleepglorp", json=_body(provider_config_id="nope"))
        assert self._loc(resp) == [["provider_config_id"]]

    async def test_model_without_provider(self, client) -> None:
        resp = await client.put("/api/gleepglorp", json=_body(model="m1"))
        assert self._loc(resp) == [["model"]]


async def test_a_refused_put_stores_nothing(client, conn) -> None:
    await client.put("/api/gleepglorp", json=_body(retention_days=0))
    assert await AppMetadataRepository(conn).get(SETTING_KEY) is None


async def test_the_routes_need_the_credential() -> None:
    from the_one.interfaces.web.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/gleepglorp")).status_code == 401
        assert (await c.put("/api/gleepglorp", json=_body())).status_code == 401


class TestProviderUsage:
    async def test_the_provider_agents_list_names_gleepglorp(self, client) -> None:
        pid = await _provider(client)
        assert (await client.get(f"/api/providers/{pid}/agents")).json() == {"agents": []}
        await client.put("/api/gleepglorp", json=_body(provider_config_id=pid, model="m"))
        resp = await client.get(f"/api/providers/{pid}/agents")
        assert resp.json() == {"agents": ["GleepGlorp"]}

    async def test_deleting_the_provider_is_a_409_naming_gleepglorp(self, client) -> None:
        pid = await _provider(client)
        await client.put("/api/gleepglorp", json=_body(provider_config_id=pid, model="m"))
        resp = await client.delete(f"/api/providers/{pid}")
        assert resp.status_code == 409
        assert "GleepGlorp" in resp.json()["detail"]
        # Pointing GleepGlorp elsewhere frees the provider.
        await client.put("/api/gleepglorp", json=_body())
        assert (await client.delete(f"/api/providers/{pid}")).status_code == 200


class TestForcedProviderDelete:
    """DELETE /api/providers/{id}?force=true: the operator override (HAT, M36 F1)."""

    @staticmethod
    async def _agent(conn, name, pid, model="m1") -> None:
        from the_one.agent.config import AgentConfig
        from the_one.db.repositories import SQLiteAgentStore

        await SQLiteAgentStore(conn).save(
            AgentConfig(name=name, provider_config_id=pid, llm_model=model)
        )

    @staticmethod
    async def _agent_row(conn, name):
        async with conn.execute(
            "SELECT provider_config_id, llm_model FROM agents WHERE name = ?", (name,)
        ) as cur:
            return tuple(await cur.fetchone())

    async def test_without_force_is_still_a_409_and_changes_nothing(self, client, conn) -> None:
        pid = await _provider(client)
        await self._agent(conn, "a1", pid)
        resp = await client.delete(f"/api/providers/{pid}")
        assert resp.status_code == 409
        assert await self._agent_row(conn, "a1") == (pid, "m1")
        assert (await client.delete(f"/api/providers/{pid}?force=false")).status_code == 409

    async def test_force_clears_agents_and_gleepglorp_and_deletes(self, client, conn) -> None:
        pid = await _provider(client)
        other = await _provider(client)
        await self._agent(conn, "a1", pid)
        await self._agent(conn, "keep", other, "m2")
        await client.put("/api/gleepglorp", json=_body(provider_config_id=pid, model="m"))
        resp = await client.delete(f"/api/providers/{pid}?force=true")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"status": "ok", "cleared": ["GleepGlorp", "a1"]}
        assert await self._agent_row(conn, "a1") == (None, "")
        assert await self._agent_row(conn, "keep") == (other, "m2")
        s = await load_settings(conn)
        assert (s.provider_config_id, s.model) == (None, None)
        assert (await client.get(f"/api/providers/{other}/agents")).json() == {"agents": ["keep"]}
        assert (await client.get("/api/gleepglorp")).json()["state"] == "needs_model"
        assert not await provider_gone_check(conn, pid)

    async def test_force_on_an_unused_provider_just_deletes(self, client, conn) -> None:
        pid = await _provider(client)
        resp = await client.delete(f"/api/providers/{pid}?force=true")
        assert resp.json() == {"status": "ok", "cleared": []}

    async def test_a_failed_delete_rolls_everything_back(self, client, conn) -> None:
        pid = await _provider(client)
        await self._agent(conn, "a1", pid)
        await client.put("/api/gleepglorp", json=_body(provider_config_id=pid, model="m"))
        await conn.execute(
            "CREATE TRIGGER block_delete BEFORE DELETE ON llm_providers "
            "BEGIN SELECT RAISE(ABORT, 'no'); END"
        )
        await conn.commit()
        with pytest.raises(Exception):  # noqa: B017 - the ASGI app re-raises the DB error
            await client.delete(f"/api/providers/{pid}?force=true")
        assert await self._agent_row(conn, "a1") == (pid, "m1")
        s = await load_settings(conn)
        assert (s.provider_config_id, s.model) == (pid, "m")

    async def test_gleepglorp_changed_only_when_gleepglorp_was_affected(self, client, conn) -> None:
        sent: list[dict] = []

        async def fake(msg):
            sent.append(msg)

        with patch("the_one.sessions.broadcast_to_all", fake):
            pid = await _provider(client)
            await self._agent(conn, "a1", pid)
            assert (await client.delete(f"/api/providers/{pid}?force=true")).status_code == 200
            assert sent == []
            pid2 = await _provider(client)
            await client.put("/api/gleepglorp", json=_body(provider_config_id=pid2, model="m"))
            sent.clear()
            assert (await client.delete(f"/api/providers/{pid2}?force=true")).status_code == 200
            assert [m["type"] for m in sent] == ["gleepglorp_changed"]
            assert sent[0]["state"] == "needs_model"

    async def test_the_setting_is_read_inside_the_transaction(self, client, conn) -> None:
        """Review fix: a GleepGlorp setting that no longer names the provider (changed after
        the route's pre-check) is not rewritten; one that does keeps its other fields."""
        from the_one.db.repositories import LLMProviderRepository

        pid = await _provider(client)
        other = await _provider(client)
        await client.put("/api/gleepglorp", json=_body(provider_config_id=other, model="m"))
        before = await load_settings(conn)
        repo = LLMProviderRepository(conn, None)  # type: ignore[arg-type]  # no secrets touched
        assert await repo.delete_forcing(pid) is False
        assert await load_settings(conn) == before  # untouched: it names `other`
        await client.put(
            "/api/gleepglorp", json=_body(provider_config_id=other, model="m", retention_days=7)
        )
        assert await repo.delete_forcing(other) is True
        s = await load_settings(conn)
        assert (s.provider_config_id, s.model, s.retention_days) == (None, None, 7)

    async def test_malformed_force_is_422(self, client) -> None:
        pid = await _provider(client)
        assert (await client.delete(f"/api/providers/{pid}?force=maybe")).status_code == 422
        assert (await client.get(f"/api/providers/{pid}/agents")).status_code == 200


async def provider_gone_check(conn, pid) -> bool:
    async with conn.execute("SELECT 1 FROM llm_providers WHERE id = ?", (pid,)) as cur:
        return await cur.fetchone() is not None


class TestRetention:
    @staticmethod
    def _aged(days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    async def _chat(self, repo, sid, agent, days) -> None:
        when = self._aged(days)
        await repo.create(ChatSession(id=sid, agent_name=agent, created_at=when, updated_at=when))

    async def test_sweep_applies_gleepglorp_retention(self, conn) -> None:
        from the_one.agent.config import AgentConfig
        from the_one.db.repositories import SQLiteAgentStore

        await save_settings(conn, GleepGlorpSettings(retention_days=7))
        await SQLiteAgentStore(conn).save(AgentConfig(name="a", chat_history_retention_days=3))
        repo = ChatSessionRepository(conn)
        await self._chat(repo, "gg-old", "GleepGlorp", 10)
        await self._chat(repo, "gg-new", "GleepGlorp", 2)
        await self._chat(repo, "a-old", "a", 5)  # older than a's 3 days, younger than 7
        await self._chat(repo, "other", "stranger", 400)  # no agents row: untouched

        result = await run_purge_sweep(conn)

        assert sorted(result["ids"]) == ["a-old", "gg-old"]
        assert result["deleted"] == 2
        assert {s.id for s in await repo.list()} == {"gg-new", "other"}

    async def test_sweep_applies_while_gleepglorp_is_off(self, conn) -> None:
        await save_settings(conn, GleepGlorpSettings(enabled=False, retention_days=7))
        repo = ChatSessionRepository(conn)
        await self._chat(repo, "gg-old", "GleepGlorp", 10)
        result = await run_purge_sweep(conn)
        assert result["ids"] == ["gg-old"]

    async def test_sweep_uses_the_default_window_with_no_setting(self, conn) -> None:
        repo = ChatSessionRepository(conn)
        await self._chat(repo, "gg-old", "GleepGlorp", 31)
        await self._chat(repo, "gg-new", "GleepGlorp", 29)
        result = await run_purge_sweep(conn)
        assert result["ids"] == ["gg-old"]


class _Sock:
    """A registered socket that records what `broadcast_to_all` sends it."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def send_text(self, text: str) -> None:
        self.texts.append(text)


class TestChangedPush:
    """M36 F1 L04: a saved change reaches every open socket; a refused one sends nothing."""

    @pytest.fixture
    def sock(self):
        from the_one.sessions import _broadcast

        s = _Sock()
        _broadcast.add_socket(s)
        yield s
        _broadcast.remove_socket(s)

    async def test_a_save_pushes_the_state_and_the_get_shape(self, client, sock) -> None:
        import json

        pid = await _provider(client)
        body = _body(provider_config_id=pid, model="m1")
        assert (await client.put("/api/gleepglorp", json=body)).status_code == 200
        frames = [json.loads(t) for t in sock.texts]
        assert frames == [
            {
                "type": "gleepglorp_changed",
                "state": "ready",
                "settings": {**body, "state": "ready", "web_search_available": True},
            }
        ]

    async def test_a_refused_save_pushes_nothing(self, client, sock) -> None:
        resp = await client.put("/api/gleepglorp", json=_body(retention_days=0))
        assert resp.status_code == 422
        assert sock.texts == []


async def test_save_and_load_round_trip(conn) -> None:
    s = GleepGlorpSettings(
        enabled=False, provider_config_id="p", model="m", web_access=False, retention_days=9
    )
    await save_settings(conn, s)
    assert await load_settings(conn) == s
