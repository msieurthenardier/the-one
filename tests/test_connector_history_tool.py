"""Tests for ``FetchChannelHistoryTool`` (DD-8). Mission 23 Flight 2 Leg 1."""

from __future__ import annotations

import asyncio

import pytest

from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.base import HistoryMessage
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.db.connection import get_connection
from the_one.db.models import Connector
from the_one.db.repositories import ConnectorRepository
from the_one.encryption import get_encryptor
from the_one.tools.connector_history import FetchChannelHistoryTool

# Edge Cases (leg spec): "Stub in unit tests must not leak tasks" — every
# manager created via ``_connected_manager`` below is drained in this
# fixture's teardown.
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


async def test_history_returns_last_n(conn_repo) -> None:
    connector = Connector(id="c1", name="t", type="stub", config={"default_agent": "default"})
    await conn_repo.create(connector)
    await _connected_manager(connector)
    StubPlugin.history_response = [
        HistoryMessage(peer_id="p1", peer_name="Alice", content="hi", ts="t1"),
        HistoryMessage(peer_id="p1", peer_name="Alice", content="there", ts="t2"),
    ]

    tool = FetchChannelHistoryTool(agent_name="default")
    result = await tool.execute(target={"connector_id": "c1", "channel_id": "ch-1"}, limit=1)
    assert "Alice" in result
    assert result.count("Alice") == 1  # limit=1 honored


async def test_history_not_supported_for_client_without_hook(conn_repo, monkeypatch) -> None:
    """A plugin/client without the OPTIONAL ``history`` hook (DD-8) gets a
    clean "not supported" result rather than an ``AttributeError``."""
    from the_one.connectors.stub import StubClient

    monkeypatch.delattr(StubClient, "history")

    connector = Connector(id="c1", name="t", type="stub", config={"default_agent": "default"})
    await conn_repo.create(connector)
    await _connected_manager(connector)

    tool = FetchChannelHistoryTool(agent_name="default")
    result = await tool.execute(target={"connector_id": "c1", "channel_id": "ch-1"})
    assert "not supported" in result


async def test_history_authorization_reused_from_send(conn_repo) -> None:
    connector = Connector(id="c1", name="t", type="stub", config={"default_agent": "default"})
    await conn_repo.create(connector)
    await _connected_manager(connector)

    tool = FetchChannelHistoryTool(agent_name="not-the-default")
    result = await tool.execute(target={"connector_id": "c1", "channel_id": "ch-1"})
    assert "[error]" in result


async def test_history_unknown_connector_refused(conn_repo) -> None:
    tool = FetchChannelHistoryTool(agent_name="default")
    result = await tool.execute(target={"connector_id": "does-not-exist", "channel_id": "ch-1"})
    assert "[error]" in result
