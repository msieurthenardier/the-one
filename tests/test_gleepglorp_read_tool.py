"""``read_app_config``, GleepGlorp's one read tool (M36 F1 L05)."""

from __future__ import annotations

import json

import pytest

from tests._gleepglorp_seed import SEEDS, seed
from the_one.agent.taint import TRUSTED_TOOL_NAMES
from the_one.gleepglorp import views
from the_one.gleepglorp.read_tool import READ_APP_CONFIG_TOOL_NAME, ReadAppConfigTool


@pytest.fixture
async def tool(tmp_path, monkeypatch):
    ns = await seed(tmp_path)

    async def _conn():
        return ns.conn

    from the_one.config import settings

    monkeypatch.setattr("the_one.db.connection.get_connection", _conn)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield ReadAppConfigTool(agent_name="GleepGlorp")
    await ns.conn.close()


def test_shape() -> None:
    t = ReadAppConfigTool()
    schema = t.to_schema()
    assert schema["name"] == "read_app_config" == READ_APP_CONFIG_TOOL_NAME
    props = schema["parameters"]["properties"]
    assert props["kind"]["enum"] == list(views.KINDS) and len(props["kind"]["enum"]) == 10
    assert schema["parameters"]["required"] == ["kind"]
    assert "name" in props
    assert len(t.description) < 600  # short: Leg 7 measures it
    # A read of configuration that can carry operator- or server-written text stays untrusted.
    assert READ_APP_CONFIG_TOOL_NAME not in TRUSTED_TOOL_NAMES


async def test_list_and_detail_are_compact_json(tool) -> None:
    listing = await tool.execute(kind="agents")
    assert ", " not in listing.split('"summary"')[0]  # compact separators
    data = json.loads(listing)
    assert {e["name"] for e in data} == {"plain", "wide"}
    detail = json.loads(await tool.execute(kind="agents", name="wide"))
    assert detail["name"] == "wide"
    assert json.loads(await tool.execute(kind="overview", name="ignored"))["counts"]["agents"] == 2
    assert json.loads(await tool.execute(kind="routines", name="wide"))["agent"] == "wide"


async def test_bad_input_is_a_plain_message_never_an_exception(tool) -> None:
    assert "Valid kinds" in await tool.execute(kind="chats")
    assert "Valid kinds" in await tool.execute()
    assert "Valid kinds" in await tool.execute(kind=None)
    assert "name must be a string" in await tool.execute(kind="agents", name=3)
    unknown = await tool.execute(kind="mcp_servers", name="nope")
    assert "Valid names" in unknown and "Docs server" in unknown
    assert "agent name" in await tool.execute(kind="routines")
    # An empty name is no name: the list.
    assert json.loads(await tool.execute(kind="agents", name=""))[0]["name"]


async def test_the_tool_never_raises_when_a_view_does(tool, monkeypatch) -> None:
    async def boom(*_a, **_k):
        raise RuntimeError(f"explodes with {SEEDS['library_secret_value']}")

    monkeypatch.setattr(views, "read", boom)
    out = await tool.execute(kind="agents")
    assert out == "Could not read agents right now."
    assert SEEDS["library_secret_value"] not in out  # the exception text is not echoed


async def test_secret_parity_through_the_tool(tool) -> None:
    """The same parity assertion through the tool's own entry point and serialization."""
    outputs = []
    for kind in views.KINDS:
        listing = await tool.execute(kind=kind)
        outputs.append(listing)
        try:
            names = [e["name"] for e in json.loads(listing)]
        except (ValueError, TypeError):
            names = []
        if kind == "routines":
            names = ["wide", "plain"]
        if kind in {"overview", "settings"}:
            names = []
        for n in names:
            outputs.append(await tool.execute(kind=kind, name=n))
        outputs.append(await tool.execute(kind=kind, name="no-such-thing"))
    blob = "\n".join(outputs)
    assert len(outputs) > 40
    assert [label for label, v in SEEDS.items() if v in blob or v[-4:] in blob] == []
