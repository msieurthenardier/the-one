"""Provenance of what GleepGlorp reads, per output path (M36 F2 L3, DD9).

A value is ``outside`` when an agent or a server can write it, ``operator`` when only the
operator's credential-gated routes can. ``read_app_config`` marks a result with only operator
paths, and the taint rule trusts exactly those results.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests._gleepglorp_seed import SEEDS, seed
from the_one.agent.config import AgentConfig
from the_one.agent.taint import OPERATOR_TYPED_MARK
from the_one.db.repositories import SQLiteAgentStore
from the_one.gleepglorp import views
from the_one.gleepglorp.read_tool import ReadAppConfigTool
from the_one.gleepglorp.views import (
    ALLOWED,
    KINDS,
    LIST_KINDS,
    OPERATOR_PATHS,
    OUTSIDE_PATHS,
    is_operator_only,
    path_provenance,
    walk_paths,
)


@pytest.fixture
async def world(tmp_path, monkeypatch):
    ns = await seed(tmp_path)

    async def _conn():
        return ns.conn

    from the_one.config import settings

    monkeypatch.setattr("the_one.db.connection.get_connection", _conn)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield ns
    await ns.conn.close()


async def read(world, kind: str, name: str | None = None, *, fields_only: bool = False):
    return await views.read_with_provenance(
        world.conn, world.enc, kind, name, fields_only=fields_only
    )


async def every_output(world) -> list[tuple[str, Any]]:
    """Every kind's list, and every named detail (agents also fields-only)."""
    out: list[tuple[str, Any]] = []
    for kind in KINDS:
        if kind == "routines":
            for agent in ("wide", "plain"):
                out.append((kind, (await read(world, kind, agent))[0]))
            continue
        data, _ = await read(world, kind)
        out.append((kind, data))
        if kind in LIST_KINDS:
            for entry in data:
                if entry["name"] != "…":
                    out.append((kind, (await read(world, kind, entry["name"]))[0]))
    for agent in ("wide", "plain"):
        out.append(("agents", (await read(world, "agents", agent, fields_only=True))[0]))
    return out


# --- the declared tables cannot drift -----------------------------------------------------


def test_no_path_is_declared_both_operator_and_outside() -> None:
    assert set(OPERATOR_PATHS) == set(OUTSIDE_PATHS) == set(KINDS)
    for kind in KINDS:
        assert not (OPERATOR_PATHS[kind] & OUTSIDE_PATHS[kind]), kind
        for path in OPERATOR_PATHS[kind] | OUTSIDE_PATHS[kind]:
            assert path.startswith(f"{kind}."), path


def test_every_list_and_detail_key_is_covered_by_a_table() -> None:
    declared = {p for k in KINDS for p in OPERATOR_PATHS[k] | OUTSIDE_PATHS[k]}
    for kind in KINDS:
        for level in ("list", "detail"):
            for key in ALLOWED[kind][level]:
                path = f"{kind}.{level}.{key}"
                covered = path_provenance(kind, path) is not None
                has_children = any(d.startswith((path + ".", path + "[")) for d in declared)
                assert covered or has_children, f"{path} is in neither table"


def test_every_nested_key_names_a_declared_path_or_sits_under_one() -> None:
    for kind in KINDS:
        declared = OPERATOR_PATHS[kind] | OUTSIDE_PATHS[kind]
        last = {d.replace("]", "").replace("[", ".").split(".")[-1] for d in declared}
        for key in ALLOWED[kind]["nested"]:
            # A nested key is a leaf name in some declared path, or its parent is declared
            # whole (a prefix that covers everything beneath it).
            assert key in last or any(path_provenance(kind, f"{d}.{key}") for d in declared), (
                f"{kind}: nested key {key!r} is not covered"
            )


_L = frozenset({"name", "summary"})
# The reviewed key sets of the kinds that used to be trusted by a whole-kind prefix. A new
# key in ``ALLOWED`` fails here until someone classifies it in the provenance tables and
# updates this pin on purpose.
REVIEWED_ALLOWED: dict[str, dict[str, frozenset[str]]] = {
    "overview": {
        "list": frozenset(),
        "detail": frozenset({"gleepglorp", "time_zone", "counts", "names"}),
    },
    "providers": {
        "list": _L | {"id"},
        "detail": frozenset(
            {
                "id",
                "name",
                "type",
                "address",
                "oauth_active",
                "agents",
                "used_by_gleepglorp",
                "options",
                "key_stored",
            }
        ),
    },
    "knowledge_bases": {
        "list": _L | {"id"},
        "detail": frozenset(
            {"id", "name", "description", "folders", "items", "latest_indexed", "indexer", "agents"}
        ),
    },
    "connectors": {
        "list": _L,
        "detail": frozenset({"name", "type", "enabled", "default_agent", "channel_bindings"}),
    },
    "secrets": {
        "list": _L | {"id"},
        "detail": frozenset({"id", "name", "description", "keys", "allowed_tools", "agents"}),
    },
    "built_in_tools": {
        "list": _L,
        "detail": frozenset({"name", "enabled", "summary", "settings"}),
    },
    "settings": {"list": frozenset(), "detail": frozenset({"time_zone", "knowledge_indexing"})},
    "fields": {"list": _L, "detail": frozenset({"name", "fields"})},
}


def test_the_formerly_broad_kinds_have_a_reviewed_key_set() -> None:
    for kind, levels in REVIEWED_ALLOWED.items():
        for level, keys in levels.items():
            assert ALLOWED[kind][level] == keys, (
                f"{kind}.{level} changed: classify the new key in OPERATOR_PATHS or "
                "OUTSIDE_PATHS, then update REVIEWED_ALLOWED"
            )


def test_no_whole_kind_prefix_is_declared_operator() -> None:
    """A bare ``{kind}.list`` / ``{kind}.detail`` would trust every future key."""
    for kind in KINDS:
        for path in OPERATOR_PATHS[kind]:
            assert path not in {f"{kind}.list", f"{kind}.detail"}, path


async def test_every_emitted_path_is_declared(world) -> None:
    for kind, data in await every_output(world):
        for path, _ in walk_paths(kind, data):
            assert path_provenance(kind, path) is not None, f"{path} is in neither table"


def test_an_undeclared_path_is_outside_so_the_result_is_not_marked() -> None:
    assert path_provenance("agents", "agents.detail.surprise") is None
    assert is_operator_only("agents", {"name": "x", "surprise": "text"}) is False
    assert is_operator_only("agents", {"name": "x", "model": "m"}) is True
    # Empty values carry no outside text.
    assert (
        is_operator_only("agents", {"name": "x", "description": "", "system_prompt": None}) is True
    )
    assert is_operator_only("agents", {"name": "x", "rules": []}) is True


# --- the outside sets, pinned ----------------------------------------------------------------


async def outside_paths(world, kind: str, name: str | None, **kw) -> set[str]:
    data, _ = await read(world, kind, name, **kw)
    return {
        p
        for p, v in walk_paths(kind, data)
        if path_provenance(kind, p) != "operator"
        or (p in views.OUTSIDE_VALUE_PREFIXES and str(v).startswith("mcp__"))
    }


async def test_the_outside_set_of_the_agent_view(world) -> None:
    assert await outside_paths(world, "agents", "wide") == {
        "agents.detail.description",
        "agents.detail.system_prompt",
        "agents.detail.rules[].text",
    }
    assert await outside_paths(world, "agents", "wide", fields_only=True) == set()
    assert await outside_paths(world, "agents", None) == set()


async def test_the_outside_set_of_the_routines_view(world) -> None:
    assert await outside_paths(world, "routines", "wide") == {
        "routines.detail.routines[].name",
        "routines.detail.routines[].prompt",
    }
    assert await outside_paths(world, "routines", "plain") == set()


async def test_the_outside_set_of_the_mcp_view(world) -> None:
    http = await outside_paths(world, "mcp_servers", "Docs server")
    assert http == {
        "mcp_servers.detail.tools[].name",
        "mcp_servers.detail.tools[].description",
        "mcp_servers.detail.connection.protocol_version",
        "mcp_servers.detail.connection.auth_posture",
    }
    # The stdio server has no cached tools or protocol values: nothing outside.
    assert await outside_paths(world, "mcp_servers", "Local tool") == set()
    assert await outside_paths(world, "mcp_servers", None) == set()


async def test_server_named_tools_in_an_agents_tool_lists_are_outside(world) -> None:
    await SQLiteAgentStore(world.conn, world.enc).save(
        AgentConfig(
            name="tooled",
            enabled_tools=["shell", "mcp__docs__search"],
            disabled_tools=["web_fetch"],
        )
    )
    paths = await outside_paths(world, "agents", "tooled")
    assert paths == {"agents.detail.enabled_tools[]"}
    await SQLiteAgentStore(world.conn, world.enc).save(
        AgentConfig(name="tooled2", enabled_tools=["shell"], disabled_tools=["mcp__x__y"])
    )
    assert await outside_paths(world, "agents", "tooled2") == {"agents.detail.disabled_tools[]"}
    _, only = await read(world, "agents", "tooled2")
    assert only is False
    await SQLiteAgentStore(world.conn, world.enc).save(
        AgentConfig(name="tooled3", enabled_tools=["shell"], disabled_tools=["web_fetch"])
    )
    assert (await read(world, "agents", "tooled3"))[1] is True


# --- the view changes ------------------------------------------------------------------------


async def test_the_agents_list_summary_is_operator_fields_only(world) -> None:
    data, only = await read(world, "agents")
    by = {e["name"]: e["summary"] for e in data}
    assert by["wide"] == "gpt-x, all tools, 2 MCP servers"
    assert by["plain"] == "m, all tools, 0 MCP servers"
    assert "The wide agent" not in json.dumps(data)  # the description is not in the list
    assert only is True
    await SQLiteAgentStore(world.conn, world.enc).save(AgentConfig(name="bare"))
    data, _ = await read(world, "agents")
    assert {e["name"]: e["summary"] for e in data}["bare"] == "no model, all tools, 0 MCP servers"


async def test_rules_gain_a_number_and_fields_only_drops_the_free_text(world) -> None:
    from the_one.db.repositories import AgentRuleRepository

    await AgentRuleRepository(world.conn).create("wide", "Second rule.")
    full, only = await read(world, "agents", "wide")
    assert [r["number"] for r in full["rules"]] == [1, 2] and only is False
    assert full["description"] and full["system_prompt"]
    slim, only = await read(world, "agents", "wide", fields_only=True)
    assert slim["rules"] == [{"number": 1, "enabled": True}, {"number": 2, "enabled": True}]
    assert "description" not in slim and "system_prompt" not in slim and only is True
    # Every other kind ignores the flag.
    for kind, name in (("overview", None), ("providers", "OpenAI main"), ("routines", "wide")):
        assert (await read(world, kind, name, fields_only=True))[0] == (
            await read(world, kind, name)
        )[0]


async def test_fields_only_through_the_tool_has_no_free_text_or_secret(world) -> None:
    tool = ReadAppConfigTool(agent_name="GleepGlorp")
    out = await tool.execute(kind="agents", name="wide", fields_only=True)
    assert out.startswith(OPERATOR_TYPED_MARK + "\n")
    assert "You are the wide agent" not in out and "Always answer briefly" not in out
    assert "fields_only" in ReadAppConfigTool.description
    assert tool.to_schema()["parameters"]["properties"]["fields_only"] == {"type": "boolean"}
    # A non-boolean value is ignored, never trusted.
    assert "You are the wide agent" in await tool.execute(
        kind="agents", name="wide", fields_only="true"
    )


async def test_secret_parity_holds_for_every_form_and_the_mark(world) -> None:
    blob = "\n".join(json.dumps(data) for _, data in await every_output(world))
    assert [label for label, v in SEEDS.items() if v in blob or v[-4:] in blob] == []


# --- which reads are operator-only (the AC5 table) -------------------------------------------


async def test_which_reads_carry_the_mark(world) -> None:
    tool = ReadAppConfigTool(agent_name="GleepGlorp")

    async def marked(kind: str, name: str | None = None, **kw: Any) -> bool:
        args: dict[str, Any] = {"kind": kind, **kw}
        if name is not None:
            args["name"] = name
        return (await tool.execute(**args)).startswith(OPERATOR_TYPED_MARK + "\n")

    expected_marked = [
        ("agents", None, {}),
        ("agents", "wide", {"fields_only": True}),
        ("agents", "plain", {}),  # no description, prompt or rules
        ("mcp_servers", None, {}),
        ("mcp_servers", "Local tool", {}),  # stdio, no cached tools or connection values
        ("routines", "plain", {}),  # no routines
        ("overview", None, {}),
        ("providers", None, {}),
        ("providers", "OpenAI main", {}),
        ("knowledge_bases", None, {}),
        ("knowledge_bases", "Docs KB", {}),
        ("connectors", None, {}),
        ("connectors", "Team Discord", {}),
        ("secrets", None, {}),
        ("secrets", "github", {}),
        ("built_in_tools", None, {}),
        ("built_in_tools", "web_search", {}),
        ("settings", None, {}),
        ("fields", None, {}),
        ("fields", "agent", {}),
    ]
    for kind, name, kw in expected_marked:
        assert await marked(kind, name, **kw), (kind, name, kw)

    expected_unmarked = [
        ("agents", "wide", {}),
        ("mcp_servers", "Docs server", {}),
        ("routines", "wide", {}),
    ]
    for kind, name, kw in expected_unmarked:
        assert not await marked(kind, name, **kw), (kind, name, kw)


async def test_an_agent_with_free_text_set_is_unmarked_and_one_without_is_marked(world) -> None:
    store = SQLiteAgentStore(world.conn, world.enc)
    await store.save(AgentConfig(name="prompted", system_prompt="Be nice."))
    assert (await read(world, "agents", "prompted"))[1] is False
    await store.save(AgentConfig(name="described", description="About."))
    assert (await read(world, "agents", "described"))[1] is False
    await store.save(AgentConfig(name="empty"))
    assert (await read(world, "agents", "empty"))[1] is True


async def test_failures_and_plain_messages_carry_no_mark(world) -> None:
    tool = ReadAppConfigTool(agent_name="GleepGlorp")
    for kwargs in (
        {"kind": "agents", "name": "no-such"},
        {"kind": "routines"},
        {"kind": "nope"},
        {"kind": "agents", "name": 3},
    ):
        out = await tool.execute(**kwargs)
        assert OPERATOR_TYPED_MARK not in out, kwargs
