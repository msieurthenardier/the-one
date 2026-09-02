"""Tests for ``the_one.connectors.inbound`` — admission, pairing, ``/new``,
reply policy, session resolution, concurrency, and the full stub round
trip (DD-1, DD-3, DD-4, DD-5, DD-6). Mission 23 Flight 2 Leg 1.

Session-resolution scenarios are ported from the pre-reset
``tests/test_connectors_session.py`` (git ref ``138025e^``), trimmed of
the plugin ``normalize_session_key`` / ``display_channel`` hooks DD-5
deliberately does not resurrect — this design keys directly off the
envelope's own fields.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from conftest import FakeLLM

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory, set_factory
from the_one.config import settings
from the_one.connectors import registry
from the_one.connectors.base import ChannelTarget, ConnectorClientError, InboundEnvelope, PeerTarget
from the_one.connectors.inbound import (
    _DEFAULT_CONTINUATION_SECONDS,
    _resolve_continuation_seconds,
    dispatch_inbound,
    is_admitted,
    resolve_session,
    should_reply,
)
from the_one.connectors.manager import ConnectorManager, set_manager
from the_one.connectors.stub import StubPlugin
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, Connector, LLMProviderConfig
from the_one.db.repositories import (
    ChatSessionRepository,
    ConnectorRepository,
    LLMProviderRepository,
    SQLiteAgentStore,
)
from the_one.encryption import get_encryptor
from the_one.llm.base import OPERATOR_VISIBILITY, Message, Role, ToolCall
from the_one.sessions import session_locks


def _envelope(**overrides) -> InboundEnvelope:
    base = dict(
        platform="stub",
        connector_id="conn-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        peer_name="Alice",
        text="hello",
        is_dm=False,
        mentions_bot=False,
    )
    base.update(overrides)
    return InboundEnvelope(**base)


def _connector(config: dict | None = None, **kwargs) -> Connector:
    return Connector(id="conn-1", name="Test", type="stub", config=config or {}, **kwargs)


@pytest.fixture(autouse=True)
def _reset_stub_and_registry():
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    yield
    StubPlugin.reset_for_test()
    registry.clear_for_test()
    set_factory(None)
    set_manager(None)


# ── admission (pure function) ────────────────────────────────────────────


def test_is_admitted_true_for_allowlisted_peer() -> None:
    conn = _connector({"allowlist": {"peers": ["peer-1"]}})
    assert is_admitted(conn, _envelope(peer_id="peer-1", channel_id="unknown-ch")) is True


def test_is_admitted_true_for_allowlisted_channel() -> None:
    conn = _connector({"allowlist": {"channels": ["ch-1"]}})
    assert is_admitted(conn, _envelope(peer_id="unknown-peer", channel_id="ch-1")) is True


def test_is_admitted_false_for_unknown_peer_and_channel() -> None:
    conn = _connector({"allowlist": {"peers": ["someone-else"], "channels": ["other-ch"]}})
    assert is_admitted(conn, _envelope(peer_id="peer-1", channel_id="ch-1")) is False


def test_is_admitted_false_with_no_allowlist_at_all() -> None:
    conn = _connector({})
    assert is_admitted(conn, _envelope()) is False


# ── reply policy matrix (DD-6) ───────────────────────────────────────────


def test_should_reply_true_for_dm() -> None:
    conn = _connector({})
    assert should_reply(conn, _envelope(is_dm=True, mentions_bot=False)) is True


def test_should_reply_true_for_mention() -> None:
    conn = _connector({})
    assert should_reply(conn, _envelope(is_dm=False, mentions_bot=True)) is True


def test_should_reply_true_for_always_listen_channel() -> None:
    conn = _connector({"always_listen": ["ch-1"]})
    envelope = _envelope(is_dm=False, mentions_bot=False, channel_id="ch-1")
    assert should_reply(conn, envelope) is True


def test_should_reply_false_when_none_apply() -> None:
    conn = _connector({"always_listen": ["other-ch"]})
    assert (
        should_reply(conn, _envelope(is_dm=False, mentions_bot=False, channel_id="ch-1")) is False
    )


def test_should_reply_false_paired_peer_non_always_listen_channel_no_mention() -> None:
    """Edge case: paired ≠ always answered."""
    conn = _connector({"allowlist": {"peers": ["peer-1"]}})
    envelope = _envelope(peer_id="peer-1", is_dm=False, mentions_bot=False, channel_id="ch-1")
    assert is_admitted(conn, envelope) is True
    assert should_reply(conn, envelope) is False


# ── continuation-seconds resolution ──────────────────────────────────────


def test_resolve_continuation_seconds_override_beats_env_and_default(monkeypatch) -> None:
    monkeypatch.setenv("THE_ONE_SESSION_CONTINUATION_SECONDS", "120")
    assert _resolve_continuation_seconds(override=60) == 60


def test_resolve_continuation_seconds_env_beats_default(monkeypatch) -> None:
    monkeypatch.setenv("THE_ONE_SESSION_CONTINUATION_SECONDS", "120")
    assert _resolve_continuation_seconds() == 120


def test_resolve_continuation_seconds_default_when_no_env(monkeypatch) -> None:
    monkeypatch.delenv("THE_ONE_SESSION_CONTINUATION_SECONDS", raising=False)
    assert _resolve_continuation_seconds() == _DEFAULT_CONTINUATION_SECONDS == 86400


def test_resolve_continuation_seconds_non_int_env_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("THE_ONE_SESSION_CONTINUATION_SECONDS", "not-a-number")
    assert _resolve_continuation_seconds() == _DEFAULT_CONTINUATION_SECONDS


def test_resolve_continuation_seconds_env_read_at_call_time(monkeypatch) -> None:
    monkeypatch.delenv("THE_ONE_SESSION_CONTINUATION_SECONDS", raising=False)
    assert _resolve_continuation_seconds() == 86400
    monkeypatch.setenv("THE_ONE_SESSION_CONTINUATION_SECONDS", "3600")
    assert _resolve_continuation_seconds() == 3600


# ── DB-backed fixtures ────────────────────────────────────────────────────


@pytest.fixture
async def conn(isolated_db):
    return await get_connection()


@pytest.fixture
def chat_repo(conn) -> ChatSessionRepository:
    return ChatSessionRepository(conn)


@pytest.fixture
def conn_repo(conn) -> ConnectorRepository:
    return ConnectorRepository(conn, get_encryptor(settings.data_dir))


@pytest.fixture
async def seeded_agent(conn) -> str:
    await SQLiteAgentStore(conn).save(AgentConfig(name="bot"))
    return "bot"


# ── resolve_session — ported scenarios (DD-5) ────────────────────────────


async def test_resolve_session_creates_new_row_on_first_contact(chat_repo, seeded_agent) -> None:
    envelope = _envelope(channel_id="ch-1", thread_id=None, peer_id="peer-1")
    connector = _connector()

    before = datetime.now(timezone.utc)
    session = await resolve_session(envelope, connector, chat_repo, agent_name=seeded_agent)
    after = datetime.now(timezone.utc)

    assert session.agent_name == "bot"
    assert session.platform == "stub"
    assert session.connector_id == "conn-1"
    assert session.channel_id == "ch-1"
    assert session.thread_id is None
    assert session.peer_id == "peer-1"
    assert session.session_metadata is None
    assert session.messages == "[]"
    assert session.title == "ch-1"
    assert len(session.id) == 32
    parsed = datetime.fromisoformat(session.last_inbound_at)
    assert before <= parsed <= after

    loaded = await chat_repo.get(session.id)
    assert loaded.id == session.id


async def test_resolve_session_dm_title(chat_repo, seeded_agent) -> None:
    envelope = _envelope(is_dm=True, peer_name="Bob", channel_id="dm-bob")
    session = await resolve_session(envelope, _connector(), chat_repo, agent_name=seeded_agent)
    assert session.title == "DM: Bob"


async def test_resolve_session_reuses_row_within_window(chat_repo, seeded_agent) -> None:
    envelope = _envelope()
    connector = _connector()

    first = await resolve_session(envelope, connector, chat_repo, agent_name=seeded_agent)
    second = await resolve_session(envelope, connector, chat_repo, agent_name=seeded_agent)

    assert second.id == first.id
    assert len(await chat_repo.list()) == 1


async def test_resolve_session_creates_new_row_outside_window(chat_repo, seeded_agent) -> None:
    envelope = _envelope()
    connector = _connector(session_continuation_seconds=1)

    stale_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    stale = ChatSession(
        id="stale-1",
        agent_name=seeded_agent,
        title="stale-title",
        platform="stub",
        connector_id="conn-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        last_inbound_at=stale_iso,
        created_at=stale_iso,
        updated_at=stale_iso,
    )
    await chat_repo.create(stale)

    fresh = await resolve_session(envelope, connector, chat_repo, agent_name=seeded_agent)

    assert fresh.id != "stale-1"
    old = await chat_repo.get("stale-1")
    assert old.title == "stale-title"
    assert len(await chat_repo.list()) == 2


async def test_resolve_session_per_thread_distinct(chat_repo, seeded_agent) -> None:
    connector = _connector()
    s_a = await resolve_session(
        _envelope(thread_id="A"), connector, chat_repo, agent_name=seeded_agent
    )
    s_b = await resolve_session(
        _envelope(thread_id="B"), connector, chat_repo, agent_name=seeded_agent
    )
    assert s_a.id != s_b.id


async def test_resolve_session_peer_id_stored_but_not_in_lookup(chat_repo, seeded_agent) -> None:
    connector = _connector()
    s1 = await resolve_session(
        _envelope(peer_id="peer-A"), connector, chat_repo, agent_name=seeded_agent
    )
    s2 = await resolve_session(
        _envelope(peer_id="peer-B"), connector, chat_repo, agent_name=seeded_agent
    )
    assert s2.id == s1.id
    loaded = await chat_repo.get(s1.id)
    assert loaded.peer_id == "peer-A"


async def test_resolve_session_skips_reuse_when_ended_at_is_set(chat_repo, seeded_agent) -> None:
    envelope = _envelope()
    connector = _connector(session_continuation_seconds=86400)

    recent_iso = datetime.now(timezone.utc).isoformat()
    ended = ChatSession(
        id="ended-1",
        agent_name=seeded_agent,
        title="prior",
        platform="stub",
        connector_id="conn-1",
        channel_id="ch-1",
        thread_id=None,
        peer_id="peer-1",
        last_inbound_at=recent_iso,
        created_at=recent_iso,
        updated_at=recent_iso,
        session_metadata={"ended_at": recent_iso},
    )
    await chat_repo.create(ended)

    fresh = await resolve_session(envelope, connector, chat_repo, agent_name=seeded_agent)
    assert fresh.id != "ended-1"
    assert len(await chat_repo.list()) == 2


# ── /new interception ──────────────────────────────────────────────────


async def test_new_ends_session_next_inbound_gets_fresh_row(
    chat_repo, conn_repo, seeded_agent
) -> None:
    connector = _connector({"allowlist": {"channels": ["ch-1"]}, "always_listen": ["ch-1"]})
    await conn_repo.create(connector)

    original = await resolve_session(_envelope(), connector, chat_repo, agent_name=seeded_agent)

    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager()
    await dispatch_inbound("conn-1", _envelope(text="/new"), manager=mgr)

    reloaded = await chat_repo.get(original.id)
    assert "ended_at" in (reloaded.session_metadata or {})

    fresh = await resolve_session(_envelope(), connector, chat_repo, agent_name=seeded_agent)
    assert fresh.id != original.id


async def test_new_from_unpaired_peer_is_silent(chat_repo, conn_repo) -> None:
    """Admission runs FIRST — unknown senders get silence even for commands."""
    connector = _connector({"allowlist": {}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager()

    await dispatch_inbound("conn-1", _envelope(text="/new"), manager=mgr)
    assert await chat_repo.list() == []


# ── pairing, end to end through dispatch_inbound ─────────────────────────


async def test_pairing_correct_code_persists_allowlist_and_consumes(conn_repo) -> None:
    connector = _connector({"allowlist": {}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager()
    code = mgr.generate_pairing_code("conn-1")

    await dispatch_inbound(
        "conn-1", _envelope(is_dm=True, text=code, peer_id="peer-1"), manager=mgr
    )

    reloaded = await conn_repo.get("conn-1")
    assert reloaded.config["allowlist"]["peers"] == ["peer-1"]
    # Consumed — a second use by a DIFFERENT unlisted peer is silent.
    await dispatch_inbound(
        "conn-1", _envelope(is_dm=True, text=code, peer_id="peer-2"), manager=mgr
    )
    reloaded_again = await conn_repo.get("conn-1")
    assert reloaded_again.config["allowlist"]["peers"] == ["peer-1"]


async def test_pairing_wrong_code_persists_nothing(conn_repo) -> None:
    connector = _connector({"allowlist": {}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager()
    mgr.generate_pairing_code("conn-1")

    await dispatch_inbound(
        "conn-1", _envelope(is_dm=True, text="wrong-code", peer_id="peer-1"), manager=mgr
    )
    reloaded = await conn_repo.get("conn-1")
    assert reloaded.config.get("allowlist", {}).get("peers", []) == []


async def test_pairing_expired_code_persists_nothing(conn_repo, monkeypatch) -> None:
    import time as time_mod

    connector = _connector({"allowlist": {}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager()
    code = mgr.generate_pairing_code("conn-1")

    real_now = time_mod.monotonic()
    monkeypatch.setattr(time_mod, "monotonic", lambda: real_now + 700)
    await dispatch_inbound(
        "conn-1", _envelope(is_dm=True, text=code, peer_id="peer-1"), manager=mgr
    )
    reloaded = await conn_repo.get("conn-1")
    assert reloaded.config.get("allowlist", {}).get("peers", []) == []


# ── concurrency: session_locks serialize inbound vs. a concurrent write ──


async def test_dispatch_inbound_serializes_via_session_locks(
    conn_repo, chat_repo, seeded_agent
) -> None:
    connector = _connector({"default_agent": "bot", "allowlist": {"channels": ["ch-1"]}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager()

    envelope = _envelope(channel_id="ch-1", mentions_bot=True)
    # Pre-create the session row so the test knows its id in advance.
    session_row = await resolve_session(envelope, connector, chat_repo, agent_name="bot")

    order: list[str] = []
    started = asyncio.Event()
    release = asyncio.Event()

    class SlowLLM(FakeLLM):
        async def complete(self, *args, **kwargs):
            order.append("dispatch-in-lock")
            started.set()
            await release.wait()
            return await super().complete(*args, **kwargs)

    fake_llm = SlowLLM(responses=[Message.assistant(content="ok")])

    async def _operator_write() -> None:
        await started.wait()
        async with session_locks[session_row.id]:
            order.append("operator-acquired")

    with patch("the_one.agent.factory.get_provider", lambda name, **kw: fake_llm):
        provider_repo = LLMProviderRepository(conn_repo.conn, conn_repo.encryptor)
        await provider_repo.create(
            LLMProviderConfig(id="prov-1", name="p", type="ollama", base_url="http://x")
        )
        agent_store = SQLiteAgentStore(conn_repo.conn)
        cfg = AgentConfig(name="bot", provider_config_id="prov-1")
        await agent_store.save(cfg)
        set_factory(AgentFactory(store=agent_store))

        dispatch_task = asyncio.create_task(dispatch_inbound("conn-1", envelope, manager=mgr))
        operator_task = asyncio.create_task(_operator_write())

        await started.wait()
        await asyncio.sleep(0.05)
        assert "operator-acquired" not in order  # blocked behind the held lock

        release.set()
        await asyncio.gather(dispatch_task, operator_task)

    assert order == ["dispatch-in-lock", "operator-acquired"]


# ── full stub round trip (acceptance criterion #1) ───────────────────────


async def test_round_trip_paired_peer_gets_reply(conn_repo, chat_repo) -> None:
    """Also the DD-10 skip-rule proof: this turn's successful
    ``send_to_platform_channel`` result must suppress ``_auto_deliver_reply``
    for the turn's trailing plain-text message (``done``) — exactly one
    outbound record (the tool's own), and ``done`` stays operator-only."""
    connector = _connector({"default_agent": "bot", "allowlist": {"peers": ["peer-1"]}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())

    provider_repo = LLMProviderRepository(conn_repo.conn, conn_repo.encryptor)
    await provider_repo.create(
        LLMProviderConfig(id="prov-1", name="p", type="ollama", base_url="http://x")
    )
    agent_store = SQLiteAgentStore(conn_repo.conn)
    await agent_store.save(AgentConfig(name="bot", provider_config_id="prov-1"))

    reply = Message.assistant(
        content="",
        tool_calls=[
            ToolCall(
                id="tc1",
                name="send_to_platform_channel",
                arguments={
                    "target": {"connector_id": "conn-1", "peer_id": "peer-1"},
                    "content": "hi back",
                },
            )
        ],
    )
    done = Message.assistant(content="done")
    fake_llm = FakeLLM(responses=[reply, done])

    with patch("the_one.agent.factory.get_provider", lambda name, **kw: fake_llm):
        set_factory(AgentFactory(store=agent_store))
        mgr = ConnectorManager(poll_interval=0.01)
        set_manager(mgr)
        encryptor = get_encryptor(settings.data_dir)
        mgr.start(connector, encryptor)
        await asyncio.sleep(0.05)

        envelope = _envelope(is_dm=True, peer_id="peer-1", channel_id="dm-peer-1")
        await StubPlugin.push_inbound("conn-1", envelope)

        await mgr.drain()

    assert len(StubPlugin.outbound_records) == 1
    target, content = StubPlugin.outbound_records[0]
    assert content == "hi back"
    assert target.peer_id == "peer-1"

    sessions = await chat_repo.list()
    persisted = decode_messages(sessions[0].messages)
    assistant_messages = [m for m in persisted if m.role == Role.ASSISTANT]
    assert [m.content for m in assistant_messages][-1] == "done"
    # DD-10 skip rule: the turn already tool-sent successfully, so the
    # trailing plain-text "done" is NOT separately auto-delivered — it
    # stays operator-only, and outbound gained no second record for it.
    assert assistant_messages[-1].visibility == OPERATOR_VISIBILITY


async def test_round_trip_peer_message_persists_attribution(conn_repo, chat_repo) -> None:
    """M23 F02 L03 (behavior-test fix): the persisted USER message from a
    peer's inbound DM carries ``peer_name`` — the Chat UI's ``msg-from-peer``
    / visually-hidden ``From {peer}: `` attribution rendering (pinned
    against SEEDED data by
    ``tests/browser/test_flow_chat_peer_attribution.py``) depends on this
    field being set by the LIVE dispatch pipeline, not just by hand-built
    fixtures. Regression test for behavior-test run
    ``2026-08-31-21-37-14`` checkpoint 5: ``dispatch_inbound`` persisted
    inbound messages with ``peer_name=None``, so the seeded-data browser
    test passed while the real pipeline's output could not render
    attribution at all.
    """
    connector = _connector({"default_agent": "bot", "allowlist": {"peers": ["peer-1"]}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())

    provider_repo = LLMProviderRepository(conn_repo.conn, conn_repo.encryptor)
    await provider_repo.create(
        LLMProviderConfig(id="prov-1", name="p", type="ollama", base_url="http://x")
    )
    agent_store = SQLiteAgentStore(conn_repo.conn)
    await agent_store.save(AgentConfig(name="bot", provider_config_id="prov-1"))
    fake_llm = FakeLLM(responses=[Message.assistant(content="hi there")])

    with patch("the_one.agent.factory.get_provider", lambda name, **kw: fake_llm):
        set_factory(AgentFactory(store=agent_store))
        mgr = ConnectorManager()
        envelope = _envelope(
            is_dm=True,
            peer_id="peer-1",
            peer_name="Alice",
            channel_id="dm-peer-1",
            text="hello?",
        )
        await dispatch_inbound("conn-1", envelope, manager=mgr)

    sessions = await chat_repo.list()
    assert len(sessions) == 1
    persisted = decode_messages(sessions[0].messages)
    user_messages = [m for m in persisted if m.role == Role.USER]
    assert len(user_messages) == 1
    assert user_messages[0].content == "hello?"
    assert user_messages[0].peer_name == "Alice"
    # bind_peer_name touches ONLY messages[pre_step_len] (Role.USER) — the
    # assistant reply must be left alone (disjoint from tag_post_step_visibility's
    # own Role.USER-skipping contract).
    assistant_messages = [m for m in persisted if m.role == Role.ASSISTANT]
    assert assistant_messages and all(m.peer_name is None for m in assistant_messages)


async def test_round_trip_unknown_peer_no_reply_nothing_persisted(conn_repo, chat_repo) -> None:
    connector = _connector({"default_agent": "bot", "allowlist": {"peers": ["someone-else"]}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager(poll_interval=0.01)
    set_manager(mgr)
    encryptor = get_encryptor(settings.data_dir)
    mgr.start(connector, encryptor)
    await asyncio.sleep(0.05)

    envelope = _envelope(peer_id="unknown-peer", channel_id="unknown-ch")
    await StubPlugin.push_inbound("conn-1", envelope)

    await mgr.drain()

    assert StubPlugin.outbound_records == []
    assert await chat_repo.list() == []


async def test_unknown_command_reaches_agent_as_text(conn_repo) -> None:
    """``/foo`` (not ``/new``) is not intercepted — the agent sees it."""
    connector = _connector({"default_agent": "bot", "allowlist": {"channels": ["ch-1"]}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())

    provider_repo = LLMProviderRepository(conn_repo.conn, conn_repo.encryptor)
    await provider_repo.create(
        LLMProviderConfig(id="prov-1", name="p", type="ollama", base_url="http://x")
    )
    agent_store = SQLiteAgentStore(conn_repo.conn)
    await agent_store.save(AgentConfig(name="bot", provider_config_id="prov-1"))
    fake_llm = FakeLLM(responses=[Message.assistant(content="ok")])

    with patch("the_one.agent.factory.get_provider", lambda name, **kw: fake_llm):
        set_factory(AgentFactory(store=agent_store))
        mgr = ConnectorManager()
        envelope = _envelope(channel_id="ch-1", mentions_bot=True, text="/foo bar baz")
        await dispatch_inbound("conn-1", envelope, manager=mgr)

    assert len(fake_llm.calls) == 1
    # ``fake_llm.calls[0]["messages"]`` is a reference to ``agent.messages``,
    # which ``agent.step`` keeps mutating after the call — so the LAST
    # element by the time we inspect it is the assistant reply, not the
    # user turn that triggered it. Filter for the user message instead.
    user_messages = [m for m in fake_llm.calls[0]["messages"] if m.role == Role.USER]
    assert user_messages[-1].content == "/foo bar baz"


# ── DD-10: auto-reply mechanical fallback ────────────────────────────────


async def _seed_provider_and_agent(conn_repo, agent_store) -> None:
    provider_repo = LLMProviderRepository(conn_repo.conn, conn_repo.encryptor)
    await provider_repo.create(
        LLMProviderConfig(id="prov-1", name="p", type="ollama", base_url="http://x")
    )
    await agent_store.save(AgentConfig(name="bot", provider_config_id="prov-1"))


async def test_auto_reply_delivers_plain_text_channel_target_with_thread_id(
    conn_repo, chat_repo
) -> None:
    """(a) A plain-text reply on a channel turn auto-delivers via the stub
    plugin's live client — the outbound record carries a ``ChannelTarget``
    with the envelope's own ``channel_id``/``thread_id``, and the persisted
    assistant message is peer-visible."""
    connector = _connector(
        {"default_agent": "bot", "allowlist": {"channels": ["ch-1"]}, "always_listen": ["ch-1"]}
    )
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    agent_store = SQLiteAgentStore(conn_repo.conn)
    await _seed_provider_and_agent(conn_repo, agent_store)
    fake_llm = FakeLLM(responses=[Message.assistant(content="the answer is 4")])

    with patch("the_one.agent.factory.get_provider", lambda name, **kw: fake_llm):
        set_factory(AgentFactory(store=agent_store))
        mgr = ConnectorManager(poll_interval=0.01)
        set_manager(mgr)
        encryptor = get_encryptor(settings.data_dir)
        mgr.start(connector, encryptor)
        await asyncio.sleep(0.05)

        envelope = _envelope(
            channel_id="ch-1",
            thread_id="thread-9",
            is_dm=False,
            mentions_bot=False,
            text="what is 2+2?",
        )
        await StubPlugin.push_inbound("conn-1", envelope)
        await mgr.drain()

    assert len(StubPlugin.outbound_records) == 1
    target, content = StubPlugin.outbound_records[0]
    assert content == "the answer is 4"
    assert isinstance(target, ChannelTarget)
    assert target.connector_id == "conn-1"
    assert target.channel_id == "ch-1"
    assert target.thread_id == "thread-9"

    sessions = await chat_repo.list()
    assert len(sessions) == 1
    persisted = decode_messages(sessions[0].messages)
    assistant_messages = [m for m in persisted if m.role == Role.ASSISTANT]
    assert len(assistant_messages) == 1
    assert assistant_messages[0].content == "the answer is 4"
    assert assistant_messages[0].visibility is None


async def test_auto_reply_delivers_plain_text_dm_peer_target(conn_repo, chat_repo) -> None:
    """(b) A DM envelope resolves a ``PeerTarget`` (not ``ChannelTarget``)."""
    connector = _connector({"default_agent": "bot", "allowlist": {"peers": ["peer-1"]}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    agent_store = SQLiteAgentStore(conn_repo.conn)
    await _seed_provider_and_agent(conn_repo, agent_store)
    fake_llm = FakeLLM(responses=[Message.assistant(content="hi there")])

    with patch("the_one.agent.factory.get_provider", lambda name, **kw: fake_llm):
        set_factory(AgentFactory(store=agent_store))
        mgr = ConnectorManager(poll_interval=0.01)
        set_manager(mgr)
        encryptor = get_encryptor(settings.data_dir)
        mgr.start(connector, encryptor)
        await asyncio.sleep(0.05)

        envelope = _envelope(is_dm=True, peer_id="peer-1", channel_id="dm-peer-1", text="hello?")
        await StubPlugin.push_inbound("conn-1", envelope)
        await mgr.drain()

    assert len(StubPlugin.outbound_records) == 1
    target, content = StubPlugin.outbound_records[0]
    assert content == "hi there"
    assert isinstance(target, PeerTarget)
    assert target.connector_id == "conn-1"
    assert target.peer_id == "peer-1"

    sessions = await chat_repo.list()
    persisted = decode_messages(sessions[0].messages)
    assistant_messages = [m for m in persisted if m.role == Role.ASSISTANT]
    assert assistant_messages[0].visibility is None


async def test_auto_reply_no_live_client_stays_operator_only_no_raise(conn_repo, chat_repo) -> None:
    """(d) Delivery failure — no live client registered for the connector
    (``manager.client_for`` returns ``None``) — logs and leaves the text
    operator-only; ``dispatch_inbound`` does not raise, and the turn is
    still persisted."""
    connector = _connector({"default_agent": "bot", "allowlist": {"peers": ["peer-1"]}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    agent_store = SQLiteAgentStore(conn_repo.conn)
    await _seed_provider_and_agent(conn_repo, agent_store)
    fake_llm = FakeLLM(responses=[Message.assistant(content="hi there")])

    with patch("the_one.agent.factory.get_provider", lambda name, **kw: fake_llm):
        set_factory(AgentFactory(store=agent_store))
        mgr = ConnectorManager()  # never started — client_for("conn-1") is None
        envelope = _envelope(is_dm=True, peer_id="peer-1", channel_id="dm-peer-1", text="hello?")
        await dispatch_inbound("conn-1", envelope, manager=mgr)  # must not raise

    assert StubPlugin.outbound_records == []
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    persisted = decode_messages(sessions[0].messages)
    assistant_messages = [m for m in persisted if m.role == Role.ASSISTANT]
    assert assistant_messages[0].content == "hi there"
    assert assistant_messages[0].visibility == OPERATOR_VISIBILITY


async def test_auto_reply_send_raises_connector_client_error_stays_operator_only(
    conn_repo, chat_repo
) -> None:
    """(d) Delivery failure — a live client whose ``send()`` raises
    ``ConnectorClientError`` — also logs and leaves the text operator-only,
    with no raise and the turn still persisted."""
    connector = _connector({"default_agent": "bot", "allowlist": {"peers": ["peer-1"]}})
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    StubPlugin.send_should_raise = ConnectorClientError("platform unreachable")
    agent_store = SQLiteAgentStore(conn_repo.conn)
    await _seed_provider_and_agent(conn_repo, agent_store)
    fake_llm = FakeLLM(responses=[Message.assistant(content="hi there")])

    with patch("the_one.agent.factory.get_provider", lambda name, **kw: fake_llm):
        set_factory(AgentFactory(store=agent_store))
        mgr = ConnectorManager(poll_interval=0.01)
        set_manager(mgr)
        encryptor = get_encryptor(settings.data_dir)
        mgr.start(connector, encryptor)
        await asyncio.sleep(0.05)

        envelope = _envelope(is_dm=True, peer_id="peer-1", channel_id="dm-peer-1", text="hello?")
        await StubPlugin.push_inbound("conn-1", envelope)
        await mgr.drain()  # must not raise

    assert StubPlugin.outbound_records == []
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    persisted = decode_messages(sessions[0].messages)
    assistant_messages = [m for m in persisted if m.role == Role.ASSISTANT]
    assert assistant_messages[0].content == "hi there"
    assert assistant_messages[0].visibility == OPERATOR_VISIBILITY


async def test_silence_paths_never_auto_deliver(conn_repo, chat_repo) -> None:
    """(e) Unadmitted sender, ``should_reply`` false, and ``/new`` all
    short-circuit ``dispatch_inbound`` before ``agent.step`` ever runs —
    no possible auto-delivery, and nothing outbound or persisted."""
    connector = _connector(
        {
            "default_agent": "bot",
            "allowlist": {"peers": ["peer-1"], "channels": ["ch-1"]},
            # ch-1 is admitted (on the allowlist) but NOT always-listen, and
            # the envelopes below never set mentions_bot/is_dm for it — so
            # should_reply is False for that channel.
            "always_listen": ["other-ch"],
        }
    )
    await conn_repo.create(connector)
    registry.register_for_test("stub", StubPlugin())
    mgr = ConnectorManager()

    # Unadmitted sender: silence at the admission gate.
    await dispatch_inbound(
        "conn-1", _envelope(peer_id="unknown-peer", channel_id="unknown-ch"), manager=mgr
    )
    # Admitted channel, but should_reply() is False (no mention/always-listen/dm).
    await dispatch_inbound(
        "conn-1",
        _envelope(channel_id="ch-1", is_dm=False, mentions_bot=False),
        manager=mgr,
    )
    # ``/new`` is intercepted before should_reply is even consulted.
    await dispatch_inbound(
        "conn-1", _envelope(is_dm=True, peer_id="peer-1", text="/new"), manager=mgr
    )

    assert StubPlugin.outbound_records == []
    assert await chat_repo.list() == []
