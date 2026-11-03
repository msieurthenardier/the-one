"""Sortie 09 leg 2: the per-agent MCP tool cache (DD4, DD5, DD7 cache-row deletes).

Covers ``has_credential_override``, ``AgentMcpToolCacheRepository`` and its race guard,
the three build-time readers, the Path A write, the deletes at the save/edit/reset hooks
and the additive ``mcp_tool_cache`` response field.
"""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet

from tests._agent_mcp_world import KEY1, KEY2, SID, world
from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.agent.factory import _build_source_index
from the_one.db.models import MCPSource
from the_one.db.repositories import (
    AgentMcpToolCacheRepository,
    MCPSourceRepository,
    SQLiteAgentStore,
    ToolConfigRepository,
)
from the_one.encryption import Encryptor
from the_one.mcp import _tool_provider as provider_mod
from the_one.mcp._overrides import has_credential_override
from the_one.mcp._tool_provider import MCPToolProvider
from the_one.self_configuration.projection import build_describe_my_capabilities

SHARED_TOOL = {"name": "shared_only", "description": "x", "input_schema": {"type": "object"}}


def _http(secrets=None) -> MCPSource:
    return MCPSource(
        id="s",
        name="srv",
        type="streamable-http",
        config={"url": "http://x/y"},
        secrets=secrets or {},
    )


def _stdio() -> MCPSource:
    return MCPSource(id="s", name="srv", type="stdio", config={"command": "echo"})


# --- AC1: has_credential_override --------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "source", "expected"),
    [
        (None, _http(), False),
        ({}, _http(), False),
        ({"enabled_tools": ["a"], "disabled_tools": ["b"]}, _http(), False),
        ({"headers": {"X-Key": "v"}}, _http(), True),
        ({"headers": {"X-Key": "   "}}, _http(), False),
        ({"headers": {}}, _http(), False),
        ({"bearer_token": "tok"}, _http(), True),
        ({"bearer_token": ""}, _http(), False),
        ({"bearer_token": None, "headers": None}, _http(), False),
        ({"env": {"K": "v"}}, _http(), False),
        ({"headers": {"X": "v"}}, _stdio(), False),
        ({"env": {"K": "v"}}, _stdio(), True),
        ({"env": {"K": ""}}, _stdio(), False),
        ({"bearer_token": "tok"}, _stdio(), False),
        # a source with OAuth state keeps the sign-in's Authorization
        ({"headers": {"authorization": "Bearer x"}}, _http({"access_token": "t"}), False),
        ({"headers": {"Authorization": "Bearer x"}}, _http({"access_token": "t"}), False),
        ({"bearer_token": "tok"}, _http({"access_token": "t"}), False),
        ({"headers": {"Authorization": "x", "X-Key": "v"}}, _http({"access_token": "t"}), True),
        ({"headers": {"Authorization": "Bearer x"}}, _http(), True),
    ],
)
def test_has_credential_override(entry, source, expected):
    assert has_credential_override(entry, source) is expected


# --- AC3: the repository and its race guard -----------------------------------------


@pytest.fixture
async def db(tmp_path):
    conn = await connect_template_db(tmp_path / "c.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "c.key")
    await MCPSourceRepository(conn, encryptor).create(_http())
    store = SQLiteAgentStore(conn, encryptor)
    await store.save(AgentConfig(name="a"))
    yield conn, store
    await conn.close()


TOOLS = [{"name": "echo", "description": "d", "input_schema": {"type": "object"}}]


async def test_get_put_delete_round_trip(db):
    conn, _ = db
    repo = AgentMcpToolCacheRepository(conn)
    assert await repo.get("a", "s") is None
    assert await repo.get_for_agent("a") == {}
    stamp = await repo.agent_updated_at("a")
    assert stamp is not None
    assert await repo.put_if_unchanged("a", "s", TOOLS, stamp) is True
    row = await repo.get("a", "s")
    assert row["tools"] == TOOLS and row["fetched_at"]
    assert (await repo.get_for_agent("a"))["s"]["tools"] == TOOLS
    await repo.delete("a", "s")
    assert await repo.get("a", "s") is None


async def test_put_replaces_the_row(db):
    conn, _ = db
    repo = AgentMcpToolCacheRepository(conn)
    stamp = await repo.agent_updated_at("a")
    await repo.put_if_unchanged("a", "s", TOOLS, stamp)
    await repo.put_if_unchanged("a", "s", [], stamp)
    assert (await repo.get("a", "s"))["tools"] == []


async def test_a_save_between_the_read_and_the_put_cancels_the_write(db):
    conn, store = db
    repo = AgentMcpToolCacheRepository(conn)
    stamp = await repo.agent_updated_at("a")
    await store.save(AgentConfig(name="a", description="edited"))  # bumps updated_at
    assert await repo.put_if_unchanged("a", "s", TOOLS, stamp) is False
    assert await repo.get("a", "s") is None


async def test_a_renamed_or_deleted_or_unknown_agent_writes_nothing(db):
    conn, store = db
    repo = AgentMcpToolCacheRepository(conn)
    stamp = await repo.agent_updated_at("a")
    assert await repo.put_if_unchanged("ghost", "s", TOOLS, stamp) is False
    assert await repo.put_if_unchanged("a", "s", TOOLS, None) is False
    assert await repo.agent_updated_at("ghost") is None
    await store.rename("a", "b")
    assert await repo.put_if_unchanged("a", "s", TOOLS, stamp) is False
    assert await repo.get_for_agent("a") == {}


async def test_an_unknown_source_writes_nothing(db):
    conn, _ = db
    repo = AgentMcpToolCacheRepository(conn)
    stamp = await repo.agent_updated_at("a")
    assert await repo.put_if_unchanged("a", "no-such-source", TOOLS, stamp) is False


async def test_rename_moves_rows_and_deletes_remove_them(db):
    conn, store = db
    repo = AgentMcpToolCacheRepository(conn)
    await repo.put_if_unchanged("a", "s", TOOLS, await repo.agent_updated_at("a"))
    await store.rename("a", "b")
    assert (await repo.get("b", "s"))["tools"] == TOOLS
    await repo.delete_for_source("s")
    assert await repo.get_for_agent("b") == {}
    await repo.put_if_unchanged("b", "s", TOOLS, await repo.agent_updated_at("b"))
    await store.delete("b")
    assert await repo.get_for_agent("b") == {}


# --- AC5/AC6: the readers ------------------------------------------------------------


@pytest.fixture
def world_(tmp_path, monkeypatch):
    return world(tmp_path, monkeypatch)


def _no_acquire(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("acquire must not be called")

    monkeypatch.setattr(provider_mod, "acquire", boom)


async def test_an_agent_with_no_override_uses_the_shared_cache_and_never_acquires(
    world_, monkeypatch
):
    async with world_ as w:
        await w.repo.merge_cache(SID, {"tools": [SHARED_TOOL]})
        await w.save_agent("plain")
        _no_acquire(monkeypatch)
        tools = await w.build_tools("plain")
        assert set(tools) == {"mcp__srv__shared_only"}
        assert w.tools_list_tails() == []  # the server was never asked


async def test_a_credentialed_agent_with_a_row_uses_it_and_never_acquires(world_, monkeypatch):
    async with world_ as w:
        await w.repo.merge_cache(SID, {"tools": [SHARED_TOOL]})
        await w.save_agent("a", KEY1)
        row = [{"name": "from_row", "description": "", "input_schema": {"type": "object"}}]
        stamp = await w.cache.agent_updated_at("a")
        assert await w.cache.put_if_unchanged("a", SID, row, stamp)
        _no_acquire(monkeypatch)
        assert set(await w.build_tools("a")) == {"mcp__srv__from_row"}


async def test_a_credentialed_agent_with_a_full_shared_cache_but_no_row_lists_live(world_):
    async with world_ as w:
        await w.repo.merge_cache(SID, {"tools": [SHARED_TOOL]})
        await w.save_agent("a", KEY1)
        tools = await w.build_tools("a")
        assert set(tools) == {"mcp__srv__echo"}  # its own listing, not the shared one
        assert w.tools_list_tails() == [KEY1[-4:]]


async def test_an_injected_credentialed_config_uses_the_shared_cache(world_, monkeypatch):
    async with world_ as w:
        await w.repo.merge_cache(SID, {"tools": [SHARED_TOOL]})
        cfg = AgentConfig(
            name="ghost",
            mcp_source_ids=[SID],
            mcp_overrides={"srv": {"headers": {"X-Api-Key": KEY1}}},
        )
        _no_acquire(monkeypatch)
        tools = await MCPToolProvider().get_tools_for_agent(cfg, agent_name="ghost")
        assert {t.name for t in tools} == {"mcp__srv__shared_only"}


async def test_path_a_fills_the_per_agent_row_with_the_pre_listing_stamp(world_):
    async with world_ as w:
        await w.save_agent("a", KEY2)
        assert await w.cache.get("a", SID) is None
        await w.build_tools("a")
        row = await w.cache.get("a", SID)
        assert {t["name"] for t in row["tools"]} == {"echo", "add"}
        assert set(row["tools"][0]) == {"name", "description", "input_schema"}
        # the shared cache is untouched
        assert (await w.repo.get(SID)).config.get("_cache", {}).get("tools") is None
        # the second build reads the row: no further tools/list
        before = len(w.tools_list_tails())
        await w.build_tools("a")
        assert len(w.tools_list_tails()) == before


async def test_a_save_during_the_listing_cancels_the_row_write(world_, monkeypatch):
    async with world_ as w:
        await w.save_agent("a", KEY1)
        real_acquire = provider_mod.acquire

        async def acquire_then_save(*a, **k):
            client = await real_acquire(*a, **k)
            # an agent save lands after the stamp was read and before the put
            store = SQLiteAgentStore(w.conn, w.encryptor)
            cfg = await store.load("a")
            await store.save(cfg.model_copy(update={"description": "edited meanwhile"}))
            return client

        monkeypatch.setattr(provider_mod, "acquire", acquire_then_save)
        tools = await w.build_tools("a")
        assert "mcp__srv__echo" in tools  # the build itself still works
        assert await w.cache.get("a", SID) is None


async def test_a_failed_listing_writes_nothing_and_skips_the_source(world_, caplog):
    async with world_ as w:
        await w.save_agent("a", "wrong-key-0000")  # the server answers a bare 401
        caplog.set_level(logging.WARNING)
        assert await w.build_tools("a") == {}
        assert await w.cache.get("a", SID) is None
        assert any("srv" in r.getMessage() and "skipping" in r.getMessage() for r in caplog.records)


async def test_search_index_reads_the_per_agent_row_and_skips_a_cold_one(world_, caplog):
    async with world_ as w:
        await w.repo.merge_cache(SID, {"tools": [SHARED_TOOL]})
        await w.save_agent("a", KEY1)
        cfg = await SQLiteAgentStore(w.conn, w.encryptor).load("a")
        caplog.set_level(logging.WARNING)
        index: dict = {}
        await _build_source_index(config=cfg, agent_name="a", source_index=index)
        assert index == {}  # cold row: the shared list is NOT used
        assert any("no cached tools" in r.getMessage() for r in caplog.records)

        await w.build_tools("a")  # fills the row
        await _build_source_index(config=cfg, agent_name="a", source_index=index)
        assert index["srv"]["tool_names_prefixed"] == ["mcp__srv__echo"]

        plain = AgentConfig(name="plain", mcp_source_ids=[SID])
        index2: dict = {}
        await _build_source_index(config=plain, agent_name="plain", source_index=index2)
        assert index2["srv"]["tool_names_prefixed"] == ["mcp__srv__shared_only"]


async def test_projection_reads_the_row_and_never_connects_on_a_cold_one(world_, monkeypatch):
    async with world_ as w:
        await w.repo.merge_cache(SID, {"tools": [SHARED_TOOL]})
        await w.save_agent("a", KEY2)
        cfg = await SQLiteAgentStore(w.conn, w.encryptor).load("a")
        tool_repo = ToolConfigRepository(w.conn, w.encryptor)
        _no_acquire(monkeypatch)

        cold = await build_describe_my_capabilities(
            cfg, tool_config_repo=tool_repo, mcp_repo=w.repo
        )
        assert cold["mcp_sources"] == [
            {"name": "srv", "type": "streamable-http", "tools": [], "tools_known": False}
        ]
        assert w.requests() == []  # read-only: it never connected

        stamp = await w.cache.agent_updated_at("a")
        rows = [{"name": "add", "description": "", "input_schema": {"type": "object"}}]
        await w.cache.put_if_unchanged("a", SID, rows, stamp)
        warm = await build_describe_my_capabilities(
            cfg, tool_config_repo=tool_repo, mcp_repo=w.repo
        )
        assert warm["mcp_sources"][0]["tools"] == ["add"]
        assert warm["mcp_sources"][0]["tools_known"] is True

        plain = AgentConfig(name="plain", mcp_source_ids=[SID])
        shared = await build_describe_my_capabilities(
            plain, tool_config_repo=tool_repo, mcp_repo=w.repo
        )
        assert shared["mcp_sources"][0]["tools"] == ["shared_only"]


# --- AC4: deletes at the hooks ---------------------------------------------------------


async def _seed_row(w, name):
    stamp = await w.cache.agent_updated_at(name)
    assert await w.cache.put_if_unchanged(name, SID, TOOLS, stamp)


async def test_a_credential_change_deletes_the_row_and_a_no_op_save_keeps_it(world_):
    async with world_ as w:
        await w.save_agent("a", KEY1)
        await _seed_row(w, "a")

        # round-trip the masked GET body: nothing changed, the row stays
        body = (await w.api.get("/api/agents/a")).json()
        assert (await w.api.put("/api/agents/a", json=body)).status_code == 200
        assert await w.cache.get("a", SID) is not None
        # a tool-filter-only change keeps it too
        body["mcp_overrides"]["srv"]["enabled_tools"] = ["echo"]
        assert (await w.api.put("/api/agents/a", json=body)).status_code == 200
        assert await w.cache.get("a", SID) is not None

        # a changed key drops it
        await w.save_agent("a", KEY2, method="put")
        assert await w.cache.get("a", SID) is None
        await _seed_row(w, "a")
        # a cleared key drops it
        body = (await w.api.get("/api/agents/a")).json()
        body["mcp_overrides"]["srv"]["headers"] = None
        assert (await w.api.put("/api/agents/a", json=body)).status_code == 200
        assert await w.cache.get("a", SID) is None


async def test_a_library_edit_or_reset_deletes_every_agents_row(world_):
    async with world_ as w:
        await w.save_agent("a", KEY1)
        await w.save_agent("b", KEY2)
        for n in ("a", "b"):
            await _seed_row(w, n)
        # rename only: nothing about the connection changed
        src = (await w.api.get(f"/api/mcp-sources/{SID}")).json()
        resp = await w.api.put(f"/api/mcp-sources/{SID}", json=dict(src, name="srv-renamed"))
        assert resp.status_code == 200
        assert await w.cache.get("a", SID) is not None
        # a config change drops both
        src = (await w.api.get(f"/api/mcp-sources/{SID}")).json()
        src["config"] = dict(src["config"], headers={"X-Api-Key": "", "X-New": ""})
        assert (await w.api.put(f"/api/mcp-sources/{SID}", json=src)).status_code == 200
        assert await w.cache.get("a", SID) is None and await w.cache.get("b", SID) is None
        # Reset connection drops them too
        for n in ("a", "b"):
            await _seed_row(w, n)
        assert (await w.api.delete(f"/api/mcp-sources/{SID}/connection")).status_code == 200
        assert await w.cache.get("a", SID) is None and await w.cache.get("b", SID) is None


# --- AC13: the response field ------------------------------------------------------------


async def test_single_agent_routes_carry_mcp_tool_cache_and_the_list_does_not(world_):
    async with world_ as w:
        created = await w.save_agent("a", KEY1)
        assert created["mcp_tool_cache"] == {}
        await w.build_tools("a")  # fills the row (Path A)
        got = (await w.api.get("/api/agents/a")).json()
        assert list(got["mcp_tool_cache"]) == [SID]
        entry = got["mcp_tool_cache"][SID]
        assert [t["name"] for t in entry["tools"]] == ["echo"] and entry["fetched_at"]
        # the update and rename responses carry it too
        put = await w.api.put("/api/agents/a", json=got)
        assert put.status_code == 200 and SID in put.json()["mcp_tool_cache"]
        ren = await w.api.post("/api/agents/a/rename", json={"new_name": "a2"})
        assert ren.status_code == 200 and SID in ren.json()["mcp_tool_cache"]
        listing = (await w.api.get("/api/agents")).json()
        assert all("mcp_tool_cache" not in row for row in listing)
        # a plain agent has the key, empty
        await w.save_agent("plain")
        assert (await w.api.get("/api/agents/plain")).json()["mcp_tool_cache"] == {}


async def test_a_get_body_sent_back_saves_and_the_derived_fields_are_ignored(world_):
    async with world_ as w:
        await w.save_agent("a", KEY1)
        await w.build_tools("a")
        body = (await w.api.get("/api/agents/a")).json()
        assert {"mcp_tool_cache", "notices", "kb_tool_names"} <= set(body)
        body["mcp_tool_cache"] = {SID: {"tools": [{"name": "planted"}], "fetched_at": "x"}}
        resp = await w.api.put("/api/agents/a", json=body)
        assert resp.status_code == 200, resp.text
        assert [t["name"] for t in resp.json()["mcp_tool_cache"][SID]["tools"]] == ["echo"]
        created = await w.api.post("/api/agents", json={**body, "name": "copy"})
        assert created.status_code == 201, created.text
        assert created.json()["mcp_tool_cache"] == {}  # the planted value was ignored
