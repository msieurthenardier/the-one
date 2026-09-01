"""Tests for ``SendToPlatformChannelTool`` — DD-4 binding-derived
authorization matrix, plus the shared-constant pin test (Flight 1
debrief landmine: ``llm/base.py``'s hardcoded tool name + prefix must
match this module's constants). Mission 23 Flight 2 Leg 1.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.base import ChannelTarget, PeerTarget
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.db.connection import get_connection
from the_one.db.models import Connector
from the_one.db.repositories import ConnectorRepository
from the_one.encryption import get_encryptor
from the_one.tools.connector_send import (
    PLATFORM_SEND_OK_PREFIX,
    SEND_TO_PLATFORM_CHANNEL_TOOL_NAME,
    SendToPlatformChannelTool,
)


def test_shared_constants_pin_llm_base_literals() -> None:
    """The Flight 1 debrief landmine: ``llm/base.py``'s
    ``tag_post_step_visibility`` hardcodes the tool name and the
    success-prefix as inline literals (layering forbids ``llm/`` importing
    ``tools/``). This test pins that both literals still equal this
    module's exported constants, by inspecting the function's source."""
    from the_one.llm.base import tag_post_step_visibility

    source = inspect.getsource(tag_post_step_visibility)
    assert f'"{SEND_TO_PLATFORM_CHANNEL_TOOL_NAME}"' in source
    assert f'"{PLATFORM_SEND_OK_PREFIX}"' in source


# Edge Cases (leg spec): "Stub in unit tests must not leak tasks" — every
# manager created via ``_connected_manager`` below is drained in this
# fixture's teardown, mirroring the explicit start/stop discipline the
# manager-lifecycle tests use directly.
_created_managers: list[ConnectorManager] = []


@pytest.fixture(autouse=True)
async def _reset():
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    yield
    for mgr in _created_managers:
        await mgr.drain()
    _created_managers.clear()
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    set_manager(None)


@pytest.fixture
async def conn_repo(isolated_db) -> ConnectorRepository:
    conn = await get_connection()
    return ConnectorRepository(conn, get_encryptor(settings.data_dir))


async def _connected_manager(connector: Connector) -> ConnectorManager:
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager(poll_interval=0.01)
    _created_managers.append(mgr)
    set_manager(mgr)
    mgr.start(connector, get_encryptor(settings.data_dir))
    await asyncio.sleep(0.05)
    return mgr


def _tool(agent_name: str) -> SendToPlatformChannelTool:
    return SendToPlatformChannelTool(agent_name=agent_name)


async def test_mapped_channel_mapped_agent_allowed(conn_repo) -> None:
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={"default_agent": "default", "channel_map": {"ch-1": "agent-a"}},
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)

    result = await _tool("agent-a").execute(
        target={"connector_id": "c1", "channel_id": "ch-1"}, content="hi"
    )
    assert result.startswith(PLATFORM_SEND_OK_PREFIX)
    assert StubPlugin.outbound_records[0][0] == ChannelTarget(
        connector_id="c1", channel_id="ch-1", thread_id=None
    )


async def test_mapped_channel_other_agent_refused_incl_default(conn_repo) -> None:
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={"default_agent": "default", "channel_map": {"ch-1": "agent-a"}},
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)

    for other in ("default", "agent-b"):
        result = await _tool(other).execute(
            target={"connector_id": "c1", "channel_id": "ch-1"}, content="hi"
        )
        assert "[error]" in result
    assert StubPlugin.outbound_records == []


async def test_unmapped_channel_default_agent_allowed(conn_repo) -> None:
    connector = Connector(id="c1", name="t", type="stub", config={"default_agent": "default"})
    await conn_repo.create(connector)
    await _connected_manager(connector)

    result = await _tool("default").execute(
        target={"connector_id": "c1", "channel_id": "unmapped-ch"}, content="hi"
    )
    assert result.startswith(PLATFORM_SEND_OK_PREFIX)


async def test_unmapped_channel_non_default_agent_refused(conn_repo) -> None:
    connector = Connector(id="c1", name="t", type="stub", config={"default_agent": "default"})
    await conn_repo.create(connector)
    await _connected_manager(connector)

    result = await _tool("someone-else").execute(
        target={"connector_id": "c1", "channel_id": "unmapped-ch"}, content="hi"
    )
    assert "[error]" in result
    assert StubPlugin.outbound_records == []


async def test_dm_default_agent_allowlisted_peer_allowed(conn_repo) -> None:
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={"default_agent": "default", "allowlist": {"peers": ["peer-1"]}},
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)

    result = await _tool("default").execute(
        target={"connector_id": "c1", "peer_id": "peer-1"}, content="hi"
    )
    assert result.startswith(PLATFORM_SEND_OK_PREFIX)
    assert StubPlugin.outbound_records[0][0] == PeerTarget(connector_id="c1", peer_id="peer-1")


async def test_dm_default_agent_non_allowlisted_peer_refused(conn_repo) -> None:
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={"default_agent": "default", "allowlist": {"peers": ["someone-else"]}},
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)

    result = await _tool("default").execute(
        target={"connector_id": "c1", "peer_id": "peer-1"}, content="hi"
    )
    assert "[error]" in result
    assert StubPlugin.outbound_records == []


async def test_dm_non_default_agent_refused(conn_repo) -> None:
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={"default_agent": "default", "allowlist": {"peers": ["peer-1"]}},
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)

    result = await _tool("someone-else").execute(
        target={"connector_id": "c1", "peer_id": "peer-1"}, content="hi"
    )
    assert "[error]" in result
    assert StubPlugin.outbound_records == []


async def test_dangling_default_agent_unmapped_and_dm_refused_but_mapped_still_ok(
    conn_repo,
) -> None:
    """A dangling ``default_agent`` (renamed/deleted) refuses unmapped-channel
    and DM sends, but a mapped-channel send by the mapped agent still
    succeeds — resolution never touches ``default_agent`` for a mapped
    channel."""
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={
            "default_agent": "gone-agent",
            "channel_map": {"ch-1": "agent-a"},
            "allowlist": {"peers": ["peer-1"]},
        },
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)

    unmapped = await _tool("agent-a").execute(
        target={"connector_id": "c1", "channel_id": "other-ch"}, content="hi"
    )
    assert "[error]" in unmapped
    dm = await _tool("agent-a").execute(
        target={"connector_id": "c1", "peer_id": "peer-1"}, content="hi"
    )
    assert "[error]" in dm

    mapped = await _tool("agent-a").execute(
        target={"connector_id": "c1", "channel_id": "ch-1"}, content="hi"
    )
    assert mapped.startswith(PLATFORM_SEND_OK_PREFIX)


async def test_result_carries_platform_send_ok_prefix(conn_repo) -> None:
    connector = Connector(id="c1", name="t", type="stub", config={"default_agent": "default"})
    await conn_repo.create(connector)
    await _connected_manager(connector)

    result = await _tool("default").execute(
        target={"connector_id": "c1", "channel_id": "ch-1"}, content="hello"
    )
    assert result.startswith(PLATFORM_SEND_OK_PREFIX)


async def test_target_requires_exactly_one_of_channel_or_peer() -> None:
    tool = _tool("default")
    both = await tool.execute(
        target={"connector_id": "c1", "channel_id": "ch-1", "peer_id": "p1"}, content="hi"
    )
    assert "[error]" in both
    neither = await tool.execute(target={"connector_id": "c1"}, content="hi")
    assert "[error]" in neither


async def test_unknown_connector_refused(conn_repo) -> None:
    tool = _tool("default")
    result = await tool.execute(
        target={"connector_id": "does-not-exist", "channel_id": "ch-1"}, content="hi"
    )
    assert "[error]" in result


def test_tool_name_pinned() -> None:
    assert SendToPlatformChannelTool.name == SEND_TO_PLATFORM_CHANNEL_TOOL_NAME
    assert SendToPlatformChannelTool.name == "send_to_platform_channel"
