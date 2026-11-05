"""Sortie 06 leg 4 — the startup repair of names that break the rule (DD11-DD12)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db, copy_template
from the_one.agent.config import AgentConfig
from the_one.db.models import Connector, KnowledgeBase, LLMProviderConfig, MCPSource
from the_one.db.name_repair import repair_unsafe_names
from the_one.db.repositories import (
    ConnectorRepository,
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)
from the_one.encryption import Encryptor
from the_one.knowledge.tool_provider import compute_tool_names
from the_one.mcp._tool import _normalize_source_name

SURFACE_NAME = "self-configuration (ops/bot)"
LONG = "L" * 70


async def _insert_agent_children(conn, agent: str) -> None:
    await conn.execute("INSERT INTO chat_sessions (id, agent_name) VALUES ('s1', ?)", (agent,))
    await conn.execute(
        "INSERT INTO agent_rules (id, agent_name, text, position, created_at, updated_at) "
        "VALUES ('r1', ?, 'rule', 0, 't', 't')",
        (agent,),
    )
    await conn.execute(
        "INSERT INTO agent_routines (id, agent_name, name, prompt, schedule, "
        "created_at, updated_at) VALUES ('rt1', ?, 'daily', 'p', '{}', 't', 't')",
        (agent,),
    )
    await conn.execute(
        "INSERT INTO agent_notes (id, agent_name, number, text, origin_kind, created_at, "
        "updated_at, updated_by) VALUES ('n1', ?, 1, 'note', 'web', 't', 't', 'agent')",
        (agent,),
    )
    await conn.execute(
        "INSERT INTO agent_revisions (id, agent_name, field, proposed_value, base_value, "
        "status, source, created_at) VALUES ('v1', ?, 'description', 'p', 'b', 'applied', "
        "'self', 't')",
        (agent,),
    )
    await conn.commit()


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    ns = SimpleNamespace(
        conn=conn,
        store=SQLiteAgentStore(conn, enc),
        mcp=MCPSourceRepository(conn, enc),
        kb=KnowledgeBaseRepository(conn),
        providers=LLMProviderRepository(conn, enc),
        connectors=ConnectorRepository(conn, enc),
    )
    yield ns
    await conn.close()


async def _repair(env):
    return await repair_unsafe_names(
        env.conn, agent_store=env.store, mcp_repo=env.mcp, kb_repo=env.kb
    )


async def _seed(env) -> SimpleNamespace:
    kb = KnowledgeBase(id="kb1", name="My\u202eNotes")
    await env.kb.create(kb)
    old_tool = compute_tool_names([kb], agent_name="x")["kb1"]
    src = MCPSource(
        id="m1", name="team/tools", type="streamable-http", config={"url": "http://x/mcp"}
    )
    await env.mcp.create(src)
    await env.mcp.create(
        MCPSource(
            id="surf",
            name=SURFACE_NAME,
            type="streamable-http",
            config={"url": "http://x/mcp", "self_configuration": {"agent": "ops/bot"}},
        )
    )
    await env.store.save(
        AgentConfig(
            name="ops/bot",
            mcp_source_ids=["m1"],
            mcp_overrides={"team/tools": {"timeout": 5}},
            kb_ids=["kb1"],
            disabled_tools=["mcp__team_tools__x", old_tool],
        )
    )
    await env.store.save(AgentConfig(name="ops bot"))
    await env.store.save(AgentConfig(name=".."))
    await env.store.save(AgentConfig(name="default"))
    await env.store.save(AgentConfig(name="  fine  "))
    await env.store.save(AgentConfig(name=LONG))
    await _insert_agent_children(env.conn, "ops/bot")
    await env.connectors.create(
        Connector(
            id="c1",
            name="c1",
            type="stub",
            config={"default_agent": "ops/bot", "channel_map": {"x": "ops/bot"}},
        )
    )
    await env.providers.create(
        LLMProviderConfig(
            id="p1", name="Local/Ollama", type="ollama", base_url="http://localhost:11434"
        )
    )
    return SimpleNamespace(kb=kb, old_tool=old_tool)


async def _names(env, table: str) -> set[str]:
    async with env.conn.execute(f"SELECT name FROM {table}") as cur:
        return {r["name"] for r in await cur.fetchall()}


async def test_repairs_every_kind_and_carries_references(env, caplog) -> None:
    seeded = await _seed(env)
    with caplog.at_level(logging.WARNING):
        done = await _repair(env)

    assert set(done) == {
        ("agent", "ops/bot", "ops bot 2"),
        ("agent", "..", "Renamed agent"),
        ("agent", LONG, "L" * 64),
        ("mcp_source", "team/tools", "team tools"),
        ("knowledge_base", "My\u202eNotes", "MyNotes"),
        ("provider", "Local/Ollama", "Local Ollama"),
    }
    agents = await _names(env, "agents")
    assert {"ops bot", "ops bot 2", "Renamed agent", "default", "  fine  ", "L" * 64} <= agents
    assert "ops/bot" not in agents

    # references follow
    cfg = await env.store.load("ops bot 2")
    assert cfg.mcp_overrides == {"team tools": {"timeout": 5}}
    new_tool = compute_tool_names(
        [seeded.kb.model_copy(update={"name": "MyNotes"})], agent_name="x"
    )["kb1"]
    assert new_tool != seeded.old_tool
    assert new_tool in cfg.disabled_tools and seeded.old_tool not in cfg.disabled_tools
    assert f"mcp__{_normalize_source_name('team tools')}__x" in cfg.disabled_tools
    for table in (
        "chat_sessions",
        "agent_rules",
        "agent_notes",
        "agent_revisions",
        "agent_routines",
    ):
        async with env.conn.execute(f"SELECT agent_name FROM {table}") as cur:
            assert [r["agent_name"] for r in await cur.fetchall()] == ["ops bot 2"]
    conn = await env.connectors.get("c1")
    assert conn.config == {"default_agent": "ops bot 2", "channel_map": {"x": "ops bot 2"}}
    # surface marker followed the agent; the surface row itself was left alone
    surf = await env.mcp.get("surf")
    assert surf.name == SURFACE_NAME
    assert surf.config["self_configuration"] == {"agent": "ops bot 2"}
    assert await _names(env, "knowledge_bases") == {"MyNotes"}
    assert await _names(env, "llm_providers") == {"Local Ollama"}

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    for kind, old, new in done:
        word = {"mcp_source": "MCP server", "knowledge_base": "knowledge base"}.get(kind, kind)
        assert any(f"renamed {word} {old!r} to {new!r}" in m for m in messages), (kind, old, new)


async def test_repair_carries_an_mcp_rename_into_secrets_allowed_tools(env) -> None:
    """Sortie 10 DD3: the startup repair's MCP rename moves secrets' allowed tools too."""
    from the_one.db.repositories import SecretRepository

    await _seed(env)
    secrets = SecretRepository(env.conn, env.mcp.encryptor)
    s = await secrets.create(
        "Vault",
        "",
        [f"mcp__{_normalize_source_name('team/tools')}__typeText", "write_file"],
        [{"key": "k", "value": "kval-123"}],
    )
    await _repair(env)
    assert (await secrets.get(s.id)).allowed_tools == [
        f"mcp__{_normalize_source_name('team tools')}__typeText",
        "write_file",
    ]


async def test_second_pass_does_nothing(env, caplog) -> None:
    await _seed(env)
    await _repair(env)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        assert await _repair(env) == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_clean_database_does_nothing(env) -> None:
    await env.store.save(AgentConfig(name="fine"))
    assert await _repair(env) == []


async def test_two_bad_names_repairing_alike_are_numbered(env) -> None:
    await env.store.save(AgentConfig(name="a/b"))
    await env.store.save(AgentConfig(name="a\\b"))
    done = await _repair(env)
    assert sorted(new for _, _, new in done) == ["a b", "a b 2"]


async def test_provider_other_columns_are_untouched(env) -> None:
    await env.providers.create(
        LLMProviderConfig(
            id="p1",
            name="a/b",
            type="openai",
            base_url="https://api.example.com",
            api_key="sk-secret",
            config={"k": 1},
        )
    )
    sql = "SELECT id, type, base_url, api_key, config, secrets FROM llm_providers"
    async with env.conn.execute(sql) as cur:
        before = [tuple(r) for r in await cur.fetchall()]
    await _repair(env)
    async with env.conn.execute(sql) as cur:
        assert [tuple(r) for r in await cur.fetchall()] == before
    assert await _names(env, "llm_providers") == {"a b"}


async def test_cascade_failure_keeps_the_rename(env, caplog, monkeypatch) -> None:
    await env.store.save(AgentConfig(name="a/b"))

    async def boom(*a, **k):
        raise RuntimeError("undecryptable")

    monkeypatch.setattr("the_one.db.name_repair.cascade_rename", boom)
    with caplog.at_level(logging.WARNING):
        done = await _repair(env)
    assert done == [("agent", "a/b", "a b")]
    assert await _names(env, "agents") == {"a b"}
    assert any("surface marker may" in r.getMessage() for r in caplog.records)


async def test_one_failing_row_does_not_stop_the_rest(env, caplog) -> None:
    await env.store.save(AgentConfig(name="bad/one"))
    await env.store.save(AgentConfig(name="bad/two"))
    real = env.store.rename

    async def rename(old, new):
        if old == "bad/one":
            raise RuntimeError("injected")
        await real(old, new)

    env.store.rename = rename
    with caplog.at_level(logging.WARNING):
        done = await _repair(env)
    assert done == [("agent", "bad/two", "bad two")]
    assert await _names(env, "agents") == {"bad/one", "bad two"}
    assert any("bad/one" in r.getMessage() for r in caplog.records)


async def test_undecryptable_mcp_source_is_skipped(env, caplog) -> None:
    await env.mcp.create(
        MCPSource(
            id="m1",
            name="a/b",
            type="streamable-http",
            config={"url": "http://x/mcp"},
            secrets={"token": "t"},
        )
    )
    await env.mcp.create(
        MCPSource(id="m2", name="c/d", type="streamable-http", config={"url": "http://x/mcp"})
    )
    foreign = env.mcp.encryptor.encrypt("not json")
    await env.conn.execute("UPDATE mcp_sources SET secrets = ? WHERE id = 'm1'", (foreign,))
    await env.conn.commit()
    with caplog.at_level(logging.WARNING):
        done = await _repair(env)
    assert done == [("mcp_source", "c/d", "c d")]
    assert await _names(env, "mcp_sources") == {"a/b", "c d"}


# ── lifespan ─────────────────────────────────────────────────────────────

pytestmark_lifespan = pytest.mark.usefixtures("reset_lifespan_singletons")


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    copy_template(settings.db_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    yield tmp_path
    monkeypatch.setattr(db_connection, "_connection", None)


@pytest.mark.usefixtures("reset_lifespan_singletons")
async def test_lifespan_repairs_before_serving(_isolated_data_dir) -> None:
    import aiosqlite
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from the_one.config import settings
    from the_one.interfaces.web.app import app

    async with aiosqlite.connect(str(settings.db_path)) as db:
        await db.execute("INSERT INTO agents (name) VALUES ('ops/bot')")
        await db.execute("INSERT INTO knowledge_bases (id, name) VALUES ('kb1', 'My/Notes')")
        await db.execute(
            "INSERT INTO mcp_sources (id, name, type, config) "
            "VALUES ('m1', 'team/tools', 'streamable-http', ?)",
            (json.dumps({"url": "http://x/mcp"}),),
        )
        await db.execute(
            "INSERT INTO llm_providers (id, name, type, base_url) "
            "VALUES ('p1', 'Local/Ollama', 'ollama', 'http://localhost:11434')"
        )
        await db.commit()

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers=auth_headers(),
        ) as client:
            assert (await client.get("/api/agents/ops bot")).status_code == 200
            listed = await client.get("/api/agents")
            assert "ops bot" in [a["name"] for a in listed.json()]
            kbs = await client.get("/api/knowledge-bases")
            assert [k["name"] for k in kbs.json()] == ["My Notes"]
            mcps = await client.get("/api/mcp-sources")
            assert "team tools" in [m["name"] for m in mcps.json()]
            provs = await client.get("/api/providers")
            assert [p["name"] for p in provs.json()] == ["Local Ollama"]
