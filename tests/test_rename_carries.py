"""Sortie 06 leg 2 — renames carry what refers to the renamed row (DD8).

Agent rename -> connector bindings; MCP-server rename -> attached agents'
overrides and disabled tools; the KB tool-name helper.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import Connector, KnowledgeBase, MCPSource
from the_one.db.repositories import ConnectorRepository, MCPSourceRepository, SQLiteAgentStore
from the_one.encryption import Encryptor
from the_one.knowledge.kb_rename import carry_kb_rename
from the_one.mcp.rename_references import carry_mcp_rename


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
    ):
        app = shared_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as client:
            yield SimpleNamespace(
                client=client,
                conn=conn,
                store=SQLiteAgentStore(conn, enc),
                mcp=MCPSourceRepository(conn, enc),
                connectors=ConnectorRepository(conn, enc),
            )
    await conn.close()


def _source(sid: str, name: str) -> MCPSource:
    return MCPSource(id=sid, name=name, type="streamable-http", config={"url": "http://x/mcp"})


async def _agent(env, name: str, **kw) -> AgentConfig:
    cfg = AgentConfig(name=name, **kw)
    await env.store.save(cfg)
    return cfg


# ── agent rename -> connectors ───────────────────────────────────────────


class TestAgentRenameConnectors:
    async def _connector(self, env, cid: str, config: dict) -> None:
        await env.connectors.create(
            Connector(id=cid, name=cid, type="stub", config=config, secrets={"token": "s3cret"})
        )

    async def test_route_rewrites_default_and_channel_map(self, env) -> None:
        await _agent(env, "a")
        await self._connector(
            env,
            "c1",
            {"default_agent": "a", "channel_map": {"x": "a", "y": "other"}, "enabled": True},
        )
        await self._connector(env, "c2", {"default_agent": "other", "channel_map": {"x": "z"}})
        await self._connector(env, "c3", {"channel_map": {"x": "a"}})
        before = {c.id: c.updated_at for c in [await env.connectors.get("c2")]}

        resp = await env.client.post("/api/agents/a/rename", json={"new_name": "b"})
        assert resp.status_code == 200, resp.text

        c1 = await env.connectors.get("c1")
        assert c1.config == {
            "default_agent": "b",
            "channel_map": {"x": "b", "y": "other"},
            "enabled": True,
        }
        assert c1.secrets == {"token": "s3cret"}
        c3 = await env.connectors.get("c3")
        assert c3.config == {"channel_map": {"x": "b"}}
        c2 = await env.connectors.get("c2")
        assert c2.config == {"default_agent": "other", "channel_map": {"x": "z"}}
        assert c2.updated_at == before["c2"]

    async def test_malformed_connector_is_skipped(self, env, caplog) -> None:
        await _agent(env, "a")
        await self._connector(env, "good", {"default_agent": "a"})
        await self._connector(env, "bad", {})
        await env.conn.execute("UPDATE connectors SET config = ? WHERE id = ?", ("not json", "bad"))
        await env.conn.commit()
        with caplog.at_level(logging.WARNING):
            await env.store.rename("a", "b")
        assert (await env.connectors.get("good")).config == {"default_agent": "b"}
        assert any("malformed connector row" in r.getMessage() for r in caplog.records)
        assert await env.store.exists("b")


# ── list_by_mcp_source ───────────────────────────────────────────────────


async def test_list_by_mcp_source_is_exact(env) -> None:
    await _agent(env, "one", mcp_source_ids=["abc"])
    await _agent(env, "two", mcp_source_ids=["abcd", "zzz"])
    await _agent(env, "none")
    assert await env.store.list_by_mcp_source("abc") == ["one"]
    assert await env.store.list_by_mcp_source("abcd") == ["two"]
    assert await env.store.list_by_mcp_source("ab") == []


# ── carry_mcp_rename ─────────────────────────────────────────────────────


class TestCarryMcpRename:
    async def _carry(self, env, sid, old, new):
        return await carry_mcp_rename(sid, old, new, agent_store=env.store, mcp_repo=env.mcp)

    async def test_moves_override_and_disabled_tools(self, env) -> None:
        await env.mcp.create(_source("s1", "new name"))
        await _agent(
            env,
            "a",
            mcp_source_ids=["s1", "s1"],
            mcp_overrides={"old": {"tools": {"t": False}}},
            disabled_tools=["mcp__old__t", "keep", "mcp__old__u"],
        )
        await _agent(env, "unattached", mcp_overrides={"old": {"x": 1}})
        assert await self._carry(env, "s1", "old", "new name") == []
        cfg = await env.store.load("a")
        assert cfg.mcp_overrides == {"new name": {"tools": {"t": False}}}
        assert cfg.disabled_tools == ["mcp__new_name__t", "keep", "mcp__new_name__u"]
        assert (await env.store.load("unattached")).mcp_overrides == {"old": {"x": 1}}

    async def test_shared_name_copies_and_adds(self, env) -> None:
        await env.mcp.create(_source("s1", "new"))
        await env.mcp.create(_source("s2", "old"))
        await _agent(
            env,
            "a",
            mcp_source_ids=["s1", "s2"],
            mcp_overrides={"old": {"v": 1}},
            disabled_tools=["mcp__old__t"],
        )
        await self._carry(env, "s1", "old", "new")
        cfg = await env.store.load("a")
        assert cfg.mcp_overrides == {"old": {"v": 1}, "new": {"v": 1}}
        assert cfg.disabled_tools == ["mcp__old__t", "mcp__new__t"]

    async def test_existing_new_override_is_not_clobbered(self, env) -> None:
        await env.mcp.create(_source("s1", "new"))
        await _agent(
            env, "a", mcp_source_ids=["s1"], mcp_overrides={"old": {"v": 1}, "new": {"v": 2}}
        )
        await self._carry(env, "s1", "old", "new")
        assert (await env.store.load("a")).mcp_overrides == {"old": {"v": 1}, "new": {"v": 2}}

    async def test_nothing_to_change_is_not_saved(self, env, monkeypatch) -> None:
        await env.mcp.create(_source("s1", "new"))
        await _agent(env, "a", mcp_source_ids=["s1"], disabled_tools=["mcp__other__t"])
        saves: list[str] = []
        original = SQLiteAgentStore.save

        async def _tracked(self, cfg):
            saves.append(cfg.name)
            return await original(self, cfg)

        monkeypatch.setattr(SQLiteAgentStore, "save", _tracked)
        await self._carry(env, "s1", "old", "new")
        await self._carry(env, "s1", "same", "same")
        assert saves == []

    async def test_same_normalised_prefix_leaves_disabled_tools(self, env) -> None:
        await env.mcp.create(_source("s1", "a b"))
        await _agent(
            env,
            "a",
            mcp_source_ids=["s1"],
            disabled_tools=["mcp__a_b__t"],
            mcp_overrides={"a/b": {"v": 1}},
        )
        await self._carry(env, "s1", "a/b", "a b")
        cfg = await env.store.load("a")
        assert cfg.disabled_tools == ["mcp__a_b__t"]
        assert cfg.mcp_overrides == {"a b": {"v": 1}}

    async def test_failure_for_one_agent_does_not_stop_the_rest(self, env, caplog) -> None:
        await env.mcp.create(_source("s1", "new"))
        await _agent(env, "bad", mcp_source_ids=["s1"], mcp_overrides={"old": {"v": 1}})
        await _agent(env, "good", mcp_source_ids=["s1"], mcp_overrides={"old": {"v": 1}})
        await env.conn.execute("UPDATE agents SET mcp_overrides = 'garbage' WHERE name = 'bad'")
        await env.conn.commit()
        with caplog.at_level(logging.WARNING):
            failed = await self._carry(env, "s1", "old", "new")
        assert failed == ["bad"]
        assert (await env.store.load("good")).mcp_overrides == {"new": {"v": 1}}
        assert any("'bad'" in r.getMessage() for r in caplog.records)

    async def test_enumeration_failure_is_swallowed(self, env, caplog) -> None:
        class Broken:
            async def list_by_mcp_source(self, _):
                raise RuntimeError("boom")

        with caplog.at_level(logging.WARNING):
            out = await carry_mcp_rename("s1", "a", "b", agent_store=Broken(), mcp_repo=env.mcp)
        assert out == []
        assert any("enumerate" in r.getMessage() for r in caplog.records)

    async def test_route_carries_and_survives_a_failing_agent(self, env, caplog) -> None:
        await env.mcp.create(_source("s1", "old"))
        await _agent(env, "bad", mcp_source_ids=["s1"], mcp_overrides={"old": {"v": 1}})
        await _agent(
            env,
            "good",
            mcp_source_ids=["s1"],
            mcp_overrides={"old": {"v": 1}},
            disabled_tools=["mcp__old__t"],
        )
        await env.conn.execute("UPDATE agents SET mcp_overrides = 'garbage' WHERE name = 'bad'")
        await env.conn.commit()
        with caplog.at_level(logging.WARNING):
            resp = await env.client.put("/api/mcp-sources/s1", json={"name": "  fresh  "})
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "fresh"
        good = await env.store.load("good")
        assert good.mcp_overrides == {"fresh": {"v": 1}}
        assert good.disabled_tools == ["mcp__fresh__t"]
        assert any("'bad'" in r.getMessage() for r in caplog.records)

    async def test_route_without_rename_touches_no_agent(self, env, monkeypatch) -> None:
        await env.mcp.create(_source("s1", "same"))
        await _agent(env, "a", mcp_source_ids=["s1"])
        loads: list[str] = []
        original = SQLiteAgentStore.load

        async def _tracked(self, name):
            loads.append(name)
            return await original(self, name)

        monkeypatch.setattr(SQLiteAgentStore, "load", _tracked)
        resp = await env.client.put("/api/mcp-sources/s1", json={"name": "same"})
        assert resp.status_code == 200
        assert loads == []


# ── carry_kb_rename ──────────────────────────────────────────────────────


class TestCarryKbRename:
    async def test_helper_rewrites_outside_a_request(self, env) -> None:
        from the_one.knowledge.tool_provider import compute_tool_names

        old = KnowledgeBase(id="kb1", name="Docs")
        new = KnowledgeBase(id="kb1", name="Manuals")
        old_tool = compute_tool_names([old], agent_name="x")["kb1"]
        new_tool = compute_tool_names([new], agent_name="x")["kb1"]
        await _agent(env, "a", kb_ids=["kb1"], disabled_tools=[old_tool])

        async def _store():
            return env.store

        await carry_kb_rename(old, new, get_agent_store=_store)
        assert (await env.store.load("a")).disabled_tools == [new_tool]

    async def test_unchanged_slug_never_acquires_the_store(self) -> None:
        async def _boom():
            raise AssertionError("store acquired")

        await carry_kb_rename(
            KnowledgeBase(id="kb1", name="My Notes"),
            KnowledgeBase(id="kb1", name="My/Notes"),
            get_agent_store=_boom,
        )

    async def test_acquisition_failure_warns(self, caplog) -> None:
        async def _boom():
            raise RuntimeError("down")

        with caplog.at_level(logging.WARNING):
            await carry_kb_rename(
                KnowledgeBase(id="kb1", name="Docs"),
                KnowledgeBase(id="kb1", name="Manuals"),
                get_agent_store=_boom,
            )
        assert any("kb1" in r.getMessage() and "acquire" in r.getMessage() for r in caplog.records)

    async def test_compute_failure_warns_and_never_raises(self, caplog, monkeypatch) -> None:
        import the_one.knowledge.tool_provider as tp

        def _boom(*a, **k):
            raise RuntimeError("derive failed")

        monkeypatch.setattr(tp, "compute_tool_names", _boom)

        async def _store():
            raise AssertionError("store acquired")

        with caplog.at_level(logging.WARNING):
            await carry_kb_rename(
                KnowledgeBase(id="kb1", name="Docs"),
                KnowledgeBase(id="kb1", name="Manuals"),
                get_agent_store=_store,
            )
        assert any(
            r.levelno == logging.WARNING and "kb1" in r.getMessage() and "derived" in r.getMessage()
            for r in caplog.records
        )
