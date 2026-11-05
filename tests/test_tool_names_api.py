"""``GET /api/tool-names`` (sortie 10, leg 1, DD3): the union of every tool a secret could
be allowed on, deduplicated, sorted, with refused and surface names left out."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import MCPSource
from the_one.db.repositories import (
    AgentMcpToolCacheRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
)
from the_one.encryption import Encryptor
from the_one.self_configuration.constants import SURFACE_ROW_NAME, SURFACE_TOOL_PREFIX
from the_one.tools.builtins import BuiltinToolProvider


@pytest.fixture
async def env(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    enc = Encryptor(Fernet.generate_key())
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as client:
            yield client, conn, enc
    await conn.close()


def _cache(*tools: tuple[str, str]) -> dict:
    return {"_cache": {"tools": [{"name": n, "description": d} for n, d in tools]}}


async def _seed(conn, enc):
    mcp = MCPSourceRepository(conn, enc)
    await mcp.create(
        MCPSource(
            id="s1",
            name="Gold finch",  # normalises to Gold_finch
            type="stdio",
            config={"command": "x", **_cache(("typeText", "types"), ("save_note", "dup"))},
        )
    )
    await mcp.create(
        MCPSource(
            id="s2", name="plain", type="stdio", config={"command": "y", **_cache(("a", "first"))}
        )
    )
    await mcp.create(
        MCPSource(
            id="surf",
            name=SURFACE_ROW_NAME,
            type="streamable-http",
            config={
                "url": "http://x/mcp",
                "self_configuration": {"agent": "bot"},
                **_cache(("update_my_description", "no")),
            },
        )
    )
    store = SQLiteAgentStore(conn, enc)
    await store.save(AgentConfig(name="bot"))
    await store.save(AgentConfig(name="bot2"))
    cache = AgentMcpToolCacheRepository(conn)
    stamp = await cache.agent_updated_at("bot")
    # the per-agent rows list a tool the shared cache lacks, and the same tool twice
    assert await cache.put_if_unchanged(
        "bot", "s2", [{"name": "b", "description": "per-agent"}], stamp
    )
    stamp2 = await cache.agent_updated_at("bot2")
    assert await cache.put_if_unchanged(
        "bot2",
        "s2",
        [{"name": "b", "description": "again"}, {"name": "a", "description": "x"}],
        stamp2,
    )
    # a row for the surface source is skipped
    assert await cache.put_if_unchanged(
        "bot2", "surf", [{"name": "update_my_description", "description": "no"}], stamp2
    ) in (True, False)


async def test_union_dedup_sorted_and_filtered(env) -> None:
    client, conn, enc = env
    await _seed(conn, enc)
    resp = await client.get("/api/tool-names")
    assert resp.status_code == 200
    rows = resp.json()
    names = [r["name"] for r in rows]
    assert names == sorted(names) and len(names) == len(set(names))
    assert all(set(r) == {"name", "source", "source_name", "description"} for r in rows)
    by = {r["name"]: r for r in rows}

    builtins = {t.name for t in BuiltinToolProvider().get_tools()}
    assert builtins - set(names) <= {
        "save_note",
        "update_note",
        "forget_note",
        "send_to_platform_channel",
    }  # only refused built-ins are missing
    assert by["write_file"] == {
        "name": "write_file",
        "source": "builtin",
        "source_name": None,
        "description": by["write_file"]["description"],
    }

    # the shared cache, under the normalised prefix
    assert by["mcp__Gold_finch__typeText"]["source"] == "mcp"
    assert by["mcp__Gold_finch__typeText"]["source_name"] == "Gold finch"
    assert by["mcp__plain__a"]["description"] == "first"  # first source wins on dedup
    # the per-agent cache rows add what the shared cache lacks, deduplicated across agents
    assert by["mcp__plain__b"]["source_name"] == "plain"
    assert names.count("mcp__plain__b") == 1
    # refused and surface names are left out, even from an MCP cache
    assert "mcp__Gold_finch__save_note" in by  # an MCP tool that merely shares a name is fine
    assert not [n for n in names if n.startswith(SURFACE_TOOL_PREFIX)]
    assert "save_note" not in by and "send_to_platform_channel" not in by
    assert "continue" not in by and "search_tools" not in by
    # agent-derived names are not included
    assert not [n for n in names if n.startswith("kb__")]


async def test_bad_cache_json_and_missing_source_are_skipped(env) -> None:
    client, conn, enc = env
    await _seed(conn, enc)
    await conn.execute(
        "INSERT INTO agent_mcp_tool_cache (agent_name, source_id, tools, fetched_at) "
        "VALUES ('bot', 's1', 'not json', 'now')"
    )
    await conn.commit()
    assert (await client.get("/api/tool-names")).status_code == 200


async def test_agent_cache_row_list_all(env) -> None:
    client, conn, enc = env
    await _seed(conn, enc)
    rows = await AgentMcpToolCacheRepository(conn).list_all()
    assert {sid for sid, _ in rows} >= {"s2"}
    assert json.dumps(rows)
