"""Tests for ``SendToPlatformChannelTool`` — DD-4 binding-derived
authorization matrix, plus the shared-constant pin test (Flight 1
debrief landmine: ``llm/base.py``'s hardcoded tool name + prefix must
match this module's constants). Mission 23 Flight 2 Leg 1.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from the_one.agent._context import current_chat_session_id
from the_one.agent.config import AgentConfig
from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.base import ChannelTarget, PeerTarget
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, Connector
from the_one.db.repositories import ChatSessionRepository, ConnectorRepository, SQLiteAgentStore
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


def test_shared_constants_pin_inbound_literals() -> None:
    """DD-10 (Mission 23 Flight 3): ``connectors/inbound.py``'s auto-reply
    skip rule needs the same two literals, inlined for the same layering
    reason (``tools/`` depends on ``connectors/``, so ``connectors/``
    importing back from ``tools/`` would cycle). Pins the module-level
    literals stay in sync with this module's exported constants."""
    from the_one.connectors import inbound

    assert inbound._SEND_TO_PLATFORM_CHANNEL_TOOL_NAME == SEND_TO_PLATFORM_CHANNEL_TOOL_NAME
    assert inbound._PLATFORM_SEND_OK_PREFIX == PLATFORM_SEND_OK_PREFIX


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


@pytest.fixture
async def chat_repo(isolated_db) -> ChatSessionRepository:
    conn = await get_connection()
    return ChatSessionRepository(conn)


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


async def _seed_session(chat_repo: ChatSessionRepository, **overrides: object) -> ChatSession:
    """Create a ``chat_sessions`` row for a DD-11 default-resolution test.
    ``agent_name`` FKs to ``agents`` (schema NOT NULL/REFERENCES), so this
    also seeds a matching agent row -- unrelated to the tool-calling
    ``agent_name`` the test passes to ``_tool()``."""
    base: dict = dict(
        id="sess-1",
        agent_name="session-owner",
        title="t",
        connector_id=None,
        channel_id=None,
        thread_id=None,
        peer_id=None,
    )
    base.update(overrides)
    await SQLiteAgentStore(chat_repo.conn).save(AgentConfig(name=base["agent_name"]))
    session = ChatSession(**base)
    await chat_repo.create(session)
    return session


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


# ── DD-11: target defaults to the session's own binding ──────────────────


def test_schema_target_optional() -> None:
    """(f) ``target`` is no longer in the schema's ``required`` list;
    ``content`` still is."""
    schema = _tool("default").to_schema()
    assert schema["parameters"]["required"] == ["content"]
    assert "target" in schema["parameters"]["properties"]


async def test_default_target_channel_keyed_session(conn_repo, chat_repo) -> None:
    """(a) omitted target, channel-keyed session -> ChannelTarget incl.
    thread_id passthrough."""
    connector = Connector(id="c1", name="t", type="stub", config={"default_agent": "default"})
    await conn_repo.create(connector)
    await _connected_manager(connector)
    await _seed_session(
        chat_repo, id="sess-a", connector_id="c1", channel_id="ch-1", thread_id="th-1"
    )

    token = current_chat_session_id.set("sess-a")
    try:
        result = await _tool("default").execute(content="hi")
    finally:
        current_chat_session_id.reset(token)

    assert result.startswith(PLATFORM_SEND_OK_PREFIX)
    assert StubPlugin.outbound_records[0][0] == ChannelTarget(
        connector_id="c1", channel_id="ch-1", thread_id="th-1"
    )


async def test_default_target_peer_keyed_session(conn_repo, chat_repo) -> None:
    """(b) omitted target, DM/peer-keyed session (no channel_id) -> PeerTarget."""
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={"default_agent": "default", "allowlist": {"peers": ["peer-1"]}},
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)
    await _seed_session(chat_repo, id="sess-b", connector_id="c1", peer_id="peer-1")

    token = current_chat_session_id.set("sess-b")
    try:
        result = await _tool("default").execute(content="hi")
    finally:
        current_chat_session_id.reset(token)

    assert result.startswith(PLATFORM_SEND_OK_PREFIX)
    assert StubPlugin.outbound_records[0][0] == PeerTarget(connector_id="c1", peer_id="peer-1")


async def test_default_target_no_session_context_errors() -> None:
    """(c) omitted target, no session context at all -> error, no send."""
    token = current_chat_session_id.set(None)
    try:
        result = await _tool("default").execute(content="hi")
    finally:
        current_chat_session_id.reset(token)

    assert "[error]" in result
    assert "no active session context" in result
    assert StubPlugin.outbound_records == []


async def test_default_target_unknown_session_id_errors(isolated_db) -> None:
    """A session id set on the ContextVar that no longer resolves in the DB
    (e.g. a stale/garbage-collected id) behaves the same as no session
    context — a clear error, never a crash."""
    token = current_chat_session_id.set("does-not-exist")
    try:
        result = await _tool("default").execute(content="hi")
    finally:
        current_chat_session_id.reset(token)

    assert "[error]" in result
    assert "no active session context" in result
    assert StubPlugin.outbound_records == []


async def test_default_target_non_connector_session_errors(chat_repo) -> None:
    """(d) omitted target, non-connector session (keying columns None) ->
    error, no send."""
    await _seed_session(chat_repo, id="sess-c", connector_id=None)

    token = current_chat_session_id.set("sess-c")
    try:
        result = await _tool("default").execute(content="hi")
    finally:
        current_chat_session_id.reset(token)

    assert "[error]" in result
    assert "not bound to a platform conversation" in result
    assert StubPlugin.outbound_records == []


async def test_default_target_connector_session_no_keying_errors(chat_repo) -> None:
    """Defensive edge case: a connector_id-bearing row with neither
    channel_id nor peer_id set is treated the same as non-connector-bound
    (shouldn't occur via ``resolve_session`` in practice, but the tool must
    not guess)."""
    await _seed_session(chat_repo, id="sess-d", connector_id="c1")

    token = current_chat_session_id.set("sess-d")
    try:
        result = await _tool("default").execute(content="hi")
    finally:
        current_chat_session_id.reset(token)

    assert "[error]" in result
    assert "not bound to a platform conversation" in result


async def test_default_target_channel_authorization_enforced(conn_repo, chat_repo) -> None:
    """(e) a defaulted channel target still runs the existing authorization
    check -- an unauthorized agent is refused the same as an explicit
    target would be."""
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={"default_agent": "default", "channel_map": {"ch-1": "agent-a"}},
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)
    await _seed_session(chat_repo, id="sess-e", connector_id="c1", channel_id="ch-1")

    token = current_chat_session_id.set("sess-e")
    try:
        result = await _tool("someone-else").execute(content="hi")
    finally:
        current_chat_session_id.reset(token)

    assert "[error]" in result
    assert StubPlugin.outbound_records == []


async def test_default_target_dm_authorization_enforced(conn_repo, chat_repo) -> None:
    """(e) a defaulted DM target still runs the allowlist check -- a peer
    that fell off the allowlist is refused the same as an explicit target."""
    connector = Connector(
        id="c1",
        name="t",
        type="stub",
        config={"default_agent": "default", "allowlist": {"peers": ["someone-else"]}},
    )
    await conn_repo.create(connector)
    await _connected_manager(connector)
    await _seed_session(chat_repo, id="sess-f", connector_id="c1", peer_id="peer-1")

    token = current_chat_session_id.set("sess-f")
    try:
        result = await _tool("default").execute(content="hi")
    finally:
        current_chat_session_id.reset(token)

    assert "[error]" in result
    assert "not on the allowlist" in result
    assert StubPlugin.outbound_records == []


async def test_explicit_target_still_works_channel(conn_repo, chat_repo) -> None:
    """(e) explicit target unchanged -- even with an active (unrelated)
    session context, an explicit target overrides defaulting entirely."""
    connector = Connector(id="c1", name="t", type="stub", config={"default_agent": "default"})
    await conn_repo.create(connector)
    await _connected_manager(connector)
    await _seed_session(chat_repo, id="sess-g", connector_id="c1", channel_id="other-ch")

    token = current_chat_session_id.set("sess-g")
    try:
        result = await _tool("default").execute(
            target={"connector_id": "c1", "channel_id": "ch-1"}, content="hi"
        )
    finally:
        current_chat_session_id.reset(token)

    assert result.startswith(PLATFORM_SEND_OK_PREFIX)
    assert StubPlugin.outbound_records[0][0] == ChannelTarget(
        connector_id="c1", channel_id="ch-1", thread_id=None
    )


# ── AC-7: keying_to_target — the DD-8 extraction's own unit tests ────────


def _keying_session(**overrides: object) -> ChatSession:
    base: dict = dict(
        id="sess-x",
        agent_name="bot",
        title="t",
        connector_id=None,
        channel_id=None,
        thread_id=None,
        peer_id=None,
    )
    base.update(overrides)
    return ChatSession(**base)


def test_keying_to_target_peer_keyed() -> None:
    from the_one.connectors.base import keying_to_target

    session = _keying_session(connector_id="c1", peer_id="peer-1")
    assert keying_to_target(session) == PeerTarget(connector_id="c1", peer_id="peer-1")


def test_keying_to_target_channel_keyed() -> None:
    from the_one.connectors.base import keying_to_target

    session = _keying_session(connector_id="c1", channel_id="ch-1")
    assert keying_to_target(session) == ChannelTarget(
        connector_id="c1", channel_id="ch-1", thread_id=None
    )


def test_keying_to_target_channel_keyed_with_thread() -> None:
    from the_one.connectors.base import keying_to_target

    session = _keying_session(connector_id="c1", channel_id="ch-1", thread_id="th-1")
    assert keying_to_target(session) == ChannelTarget(
        connector_id="c1", channel_id="ch-1", thread_id="th-1"
    )


def test_keying_to_target_non_connector_session_returns_none() -> None:
    from the_one.connectors.base import keying_to_target

    session = _keying_session(connector_id=None)
    assert keying_to_target(session) is None


def test_keying_to_target_degenerate_connector_bound_keyless_returns_none() -> None:
    """The degenerate branch that moved here from
    ``connector_send.py``'s old inline implementation: connector_id set,
    but neither channel_id nor peer_id — the helper must not guess."""
    from the_one.connectors.base import keying_to_target

    session = _keying_session(connector_id="c1")
    assert keying_to_target(session) is None


def test_keying_to_target_channel_takes_priority_over_peer() -> None:
    """Mirrors resolve_session's keying: channel_id is the primary
    keying column, so a row carrying both resolves to a ChannelTarget."""
    from the_one.connectors.base import keying_to_target

    session = _keying_session(connector_id="c1", channel_id="ch-1", peer_id="peer-1")
    assert keying_to_target(session) == ChannelTarget(
        connector_id="c1", channel_id="ch-1", thread_id=None
    )
