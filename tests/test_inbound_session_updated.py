"""``dispatch_inbound`` tells a chat's subscribers when a connector turn ends
(sortie 05 leg 3, DD5): one ``session_updated`` frame per resolved session,
sent after the per-session lock is released, on every exit path."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from conftest import FakeLLM

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory, set_factory
from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.base import InboundEnvelope
from the_one.connectors.inbound import dispatch_inbound
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.db.connection import get_connection
from the_one.db.models import Connector, LLMProviderConfig
from the_one.db.repositories import (
    ChatSessionRepository,
    ConnectorRepository,
    LLMProviderRepository,
    SQLiteAgentStore,
)
from the_one.encryption import get_encryptor
from the_one.llm.base import Message
from the_one.sessions import add_subscriber, remove_subscriber, session_locks


def _envelope(**overrides) -> InboundEnvelope:
    base = dict(
        platform="stub",
        connector_id="conn-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        peer_name="Alice",
        text="hello",
        is_dm=True,
        mentions_bot=False,
    )
    base.update(overrides)
    return InboundEnvelope(**base)


class _WS:
    """A subscriber that records each frame and the lock state at send time."""

    def __init__(self, raises: bool = False) -> None:
        self.frames: list[tuple[dict, bool]] = []
        self.raises = raises
        self.session_id: str | None = None

    async def send_json(self, payload: dict) -> None:
        if self.raises:
            raise RuntimeError("socket closed")
        locked = session_locks[payload["session_id"]].locked()
        self.frames.append((payload, locked))


@pytest.fixture(autouse=True)
def _reset():
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    yield
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    set_factory(None)
    set_manager(None)


@pytest.fixture
async def repos(isolated_db):
    conn = await get_connection()
    return ConnectorRepository(conn, get_encryptor(settings.data_dir)), ChatSessionRepository(conn)


async def _setup(conn_repo, *, agent: bool = True, allow: str = "peer-1"):
    connector = Connector(
        id="conn-1",
        name="Test",
        type="stub",
        config={"default_agent": "bot", "allowlist": {"peers": [allow]}},
    )
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    provider_repo = LLMProviderRepository(conn_repo.conn, conn_repo.encryptor)
    await provider_repo.create(
        LLMProviderConfig(id="prov-1", name="p", type="ollama", base_url="http://x")
    )
    store = SQLiteAgentStore(conn_repo.conn)
    if agent:
        await store.save(AgentConfig(name="bot", provider_config_id="prov-1"))
    return store


async def _run(store, llm, ws_list, envelope=None):
    """Dispatch one envelope with each ``ws`` subscribed to the chat it will land in."""
    mgr = ConnectorManager()
    from the_one.connectors import inbound as inbound_mod

    real = inbound_mod.resolve_session

    async def spying(*a, **kw):
        row = await real(*a, **kw)
        for ws in ws_list:
            add_subscriber(row.id, ws)
            ws.session_id = row.id
        return row

    with (
        patch("the_one.agent.factory.get_provider", lambda name, **kw: llm),
        patch.object(inbound_mod, "resolve_session", spying),
    ):
        set_factory(AgentFactory(store=store))
        try:
            await dispatch_inbound("conn-1", envelope or _envelope(), manager=mgr)
        finally:
            for ws in ws_list:
                if ws.session_id:
                    remove_subscriber(ws.session_id, ws)


async def test_success_sends_one_frame_after_lock_release(repos):
    conn_repo, chat_repo = repos
    store = await _setup(conn_repo)
    ws = _WS()
    await _run(store, FakeLLM(responses=[Message.assistant(content="hi")]), [ws])
    assert len(ws.frames) == 1
    frame, locked = ws.frames[0]
    assert frame == {"type": "session_updated", "session_id": ws.session_id}
    assert locked is False
    assert not session_locks[ws.session_id].locked()


async def test_factory_create_failure_still_sends(repos):
    conn_repo, _ = repos
    store = await _setup(conn_repo, agent=False)  # AgentNotFoundError on create
    ws = _WS()
    await _run(store, FakeLLM(responses=[]), [ws])
    assert len(ws.frames) == 1
    assert ws.frames[0][1] is False


async def test_raising_step_still_sends(repos):
    conn_repo, _ = repos
    store = await _setup(conn_repo)

    class Raising(FakeLLM):
        async def complete(self, *args, **kwargs):
            raise RuntimeError("boom")

    ws = _WS()
    await _run(store, Raising(responses=[]), [ws])
    assert len(ws.frames) == 1
    assert ws.frames[0][1] is False


async def test_failing_subscriber_does_not_break_dispatch(repos):
    conn_repo, _ = repos
    store = await _setup(conn_repo)
    bad, good = _WS(raises=True), _WS()
    await _run(store, FakeLLM(responses=[Message.assistant(content="hi")]), [bad, good])
    assert len(good.frames) == 1


async def test_broadcast_error_is_suppressed(repos):
    conn_repo, _ = repos
    store = await _setup(conn_repo)

    async def boom(*a, **kw):
        raise RuntimeError("broadcast exploded")

    with patch("the_one.connectors.inbound.broadcast_to_session", boom):
        await _run(store, FakeLLM(responses=[Message.assistant(content="hi")]), [])


async def test_not_admitted_sends_nothing(repos):
    conn_repo, _ = repos
    store = await _setup(conn_repo, allow="someone-else")
    ws = _WS()
    await _run(store, FakeLLM(responses=[]), [ws])
    assert ws.frames == []
    assert ws.session_id is None


async def test_cancelled_error_propagates(repos):
    conn_repo, _ = repos
    store = await _setup(conn_repo)

    class Cancelling(FakeLLM):
        async def complete(self, *args, **kwargs):
            raise asyncio.CancelledError()

    ws = _WS()
    with pytest.raises(asyncio.CancelledError):
        await _run(store, Cancelling(responses=[]), [ws])


# ── M31 F6 L10b: the connector turn seam (busy push, turn counter) ──────────


async def _turn_counts_and_pushes(repos, *, agent: bool, llm):
    from the_one.db import _session_changes
    from the_one.sessions import is_session_processing, turn_seq

    conn_repo, _ = repos
    store = await _setup(conn_repo, agent=agent)
    pushes: list[tuple[bool, str]] = []
    ws = _WS()

    def listener() -> None:
        sid = ws.session_id
        if sid:
            pushes.append((is_session_processing(sid), turn_seq(sid)))

    _session_changes.add_listener(listener)
    try:
        await _run(store, llm, [ws])
    finally:
        _session_changes.remove_listener(listener)
    return ws, pushes


async def test_a_connector_turn_pushes_at_start_and_after_release_and_bumps(repos):
    ws, pushes = await _turn_counts_and_pushes(
        repos, agent=True, llm=FakeLLM(responses=[Message.assistant(content="hi")])
    )
    ends = [p for p in pushes if not p[0] and p[1].endswith(":1")]
    starts = [p for p in pushes if p[0]]
    assert starts and starts[0][1].endswith(":0")
    assert ends, pushes  # the end push reads an idle session with the bumped counter


async def test_a_connector_early_return_does_not_bump(repos):
    ws, pushes = await _turn_counts_and_pushes(
        repos,
        agent=False,
        llm=FakeLLM(responses=[]),  # AgentNotFoundError: early return
    )
    from the_one.sessions import turn_seq

    assert turn_seq(ws.session_id).endswith(":0")
    assert all(p[1].endswith(":0") for p in pushes), pushes


# ── Sortie 07 DD7: any other build failure ──────────────────────────────────


async def test_an_unmapped_build_failure_is_logged_with_the_agent_and_returns(repos, caplog):
    """A build exception that is not one of the three factory errors is logged with the
    agent name and ends the dispatch cleanly: nothing raised, no bump, the end frame sent."""
    from the_one.sessions import turn_seq

    conn_repo, _ = repos
    store = await _setup(conn_repo)
    ws = _WS()
    caplog.set_level("ERROR", logger="the_one.connectors.inbound")

    async def kaboom(self, name, *a, **kw):
        raise RuntimeError("kaboom")

    with patch.object(AgentFactory, "create", kaboom):
        await _run(store, FakeLLM(responses=[]), [ws])

    records = [r for r in caplog.records if "failed to build agent" in r.getMessage()]
    assert len(records) == 1
    assert "'bot'" in records[0].getMessage()
    assert records[0].exc_info is not None
    assert len(ws.frames) == 1 and ws.frames[0][1] is False
    assert turn_seq(ws.session_id).endswith(":0")
    assert not session_locks[ws.session_id].locked()


# ── Sortie 10 DD7 (AC13): a connector turn reaches the secrets hook ─────────


async def test_connector_turn_reaches_the_secrets_hook(repos):
    """A tool call that writes a secret placeholder, from an agent with no grants, gets the
    "not granted" refusal in the stored chat: the factory-built Agent has a resolver and the
    connector path runs through ``_execute_tool``."""
    from the_one.db.codec import decode_messages
    from the_one.db.repositories import SecretRepository
    from the_one.llm.base import Role, ToolCall

    conn_repo, chat_repo = repos
    store = await _setup(conn_repo)
    await SecretRepository(conn_repo.conn, conn_repo.encryptor).create(
        "Home", "", ["current_time"], [{"key": "home_city", "value": "Springfield-77"}]
    )
    ws = _WS()
    call = ToolCall(id="c1", name="current_time", arguments={"x": "{{secret:home_city}}"})
    llm = FakeLLM(responses=[Message.assistant("", tool_calls=[call]), Message.assistant("ok")])
    await _run(store, llm, [ws])
    row = await chat_repo.get(ws.session_id)
    tool_msgs = [m for m in decode_messages(row.messages) if m.role == Role.TOOL]
    assert [m.tool_result.content for m in tool_msgs] == [
        "Secret `home_city` is not granted to this agent."
    ]


async def test_connector_turn_fills_a_granted_secret_and_masks_the_result(repos):
    """Squawk 0331 (3): with the grant and the tool allowed, a connector turn fills the
    value into the tool call (current_time echoes a bad zone in its error), the stored
    result masks it, and the stored tool call keeps the placeholder."""
    from the_one.db.codec import decode_messages
    from the_one.db.repositories import SecretRepository
    from the_one.llm.base import Role, ToolCall

    conn_repo, chat_repo = repos
    store = await _setup(conn_repo)
    secret = await SecretRepository(conn_repo.conn, conn_repo.encryptor).create(
        "Home", "", ["current_time"], [{"key": "home_city", "value": "Springfield-77"}]
    )
    await store.save(AgentConfig(name="bot", provider_config_id="prov-1", secret_ids=[secret.id]))
    ws = _WS()
    call = ToolCall(id="c1", name="current_time", arguments={"zone": "{{secret:home_city}}"})
    llm = FakeLLM(responses=[Message.assistant("", tool_calls=[call]), Message.assistant("ok")])
    await _run(store, llm, [ws])
    row = await chat_repo.get(ws.session_id)
    msgs = decode_messages(row.messages)
    tool_msgs = [m for m in msgs if m.role == Role.TOOL]
    assert len(tool_msgs) == 1
    content = tool_msgs[0].tool_result.content
    assert "Unknown time zone '[secret:home_city]'" in content, content
    assert "Springfield-77" not in content and "{{secret" not in content
    stored_calls = [tc for m in msgs for tc in (m.tool_calls or [])]
    assert [tc.arguments for tc in stored_calls] == [{"zone": "{{secret:home_city}}"}]
