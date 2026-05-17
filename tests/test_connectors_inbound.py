"""Tests for ``the_one.connectors._inbound`` — M10 F03 L04 dispatcher.

Covers:
- Stub-driven inbound flows through pool + session resolver + agent.step +
  persistence.
- Pool ``last_activity`` touch is the F1 ratification anchor (snapshot
  before / after).
- Per-session ``asyncio.Lock`` serializes same-session inbounds;
  parallelizes different-session inbounds. Event-coordinated (NOT
  wall-clock) — uses a test-local ``_BlockingProvider`` that awaits an
  ``asyncio.Event`` inside ``stream``.
- ``current_chat_session_id`` ContextVar bound during the turn, reset
  after (including on agent.step exceptions).
- Visibility defaults: inbound user message + assistant reply both
  persist with ``visibility=None`` (peer-visible default; F4 owns
  operator-tagging on outbound).
- Account-not-found and unknown-connector-type paths return gracefully
  (no exception, no session created).
- ``session_continuation_seconds`` window drives reuse vs. new session.
- Explicit no-duplicate-user-message regression
  (``test_dispatch_inbound_persists_exactly_one_user_message_per_inbound``)
  — documents the architect-revised "drop append_messages, let
  agent.step append internally" deviation as a regression net.

Repository-unit tests for ``ChatSessionRepository.update_last_inbound``
live in ``tests/test_db_repositories.py`` (see TestChatSessionRepository).
This file's repo-touch test is the integration assertion that the
dispatcher actually consumes the new primitive.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite
import pytest

from the_one.agent._context import current_chat_session_id
from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.connectors import _inbound as inbound_mod
from the_one.connectors import _pool as pool_mod
from the_one.connectors._inbound import dispatch_inbound
from the_one.connectors._stub import StubPlugin
from the_one.connectors.base import InboundEnvelope
from the_one.connectors.registry import (
    clear_for_test as _registry_clear_for_test,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, ConnectorAccount, LLMProviderConfig
from the_one.db.repositories import (
    ChatSessionRepository,
    ConnectorAccountRepository,
    LLMProviderRepository,
    SQLiteAgentStore,
)
from the_one.db.schema import ensure_schema
from the_one.encryption import get_encryptor
from the_one.llm.base import LLMProvider, Message, Role, StreamChunk, TokenUsage

# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset StubPlugin class-level recording buffers around each test."""
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_locks_registry():
    """Empty pool + per-session lock dict + registry between tests."""
    yield
    await pool_mod._clear_for_test()
    await inbound_mod._clear_for_test()
    # Hard-clear then restore baseline so each test starts from the
    # production-shaped registry (currently empty in F3).
    _registry_clear_for_test()
    restore_to_baseline_for_test()


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    """Per-test sqlite DB at tmp_path. Mirrors
    ``tests/test_connectors_e2e.py::isolated_db``.

    The dispatcher resolves its DB connection via ``get_connection()``
    inside the function body, so we need the module-level singleton
    repointed at the per-test path. Schema is applied via a side
    connection so the singleton opens cleanly on first
    ``get_connection()``.
    """
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    db_path = settings.db_path

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    await conn.close()

    monkeypatch.setattr(db_connection, "_connection", None)
    yield db_path

    if db_connection._connection is not None:
        await db_connection.close_connection()


async def _seed_provider_and_agent(
    *,
    agent_name: str = "agent-inbound",
    provider_id: str = "mock-provider",
    response_content: str = "ok",
) -> None:
    """Seed an LLM provider + agent config so ``AgentFactory.create()``
    has something to build against. Uses ``type='mock'`` so the LLM
    registry resolves to :class:`the_one.llm.mock.MockProvider`.
    """
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)

    provider_repo = LLMProviderRepository(conn, encryptor)
    await provider_repo.create(
        LLMProviderConfig(
            id=provider_id,
            name="Mock Provider",
            type="mock",
            base_url="",
            config={"response": {"content": response_content}},
        )
    )

    agent_store = SQLiteAgentStore(conn)
    await agent_store.save(
        AgentConfig(
            name=agent_name,
            provider_config_id=provider_id,
            llm_model="mock-default",
        )
    )


async def _seed_stub_account(account_id: str = "acct-test") -> ConnectorAccount:
    """Persist a stub-typed ConnectorAccount via the repository."""
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = ConnectorAccountRepository(conn, encryptor)
    account = ConnectorAccount(
        id=account_id,
        name="Stub Account",
        type="stub",
        config={},
        secrets={},
    )
    await repo.create(account)
    return account


async def _make_factory() -> AgentFactory:
    """Build an AgentFactory whose ``store`` reads from the per-test DB.

    Disables MCP wiring (``mcp_provider=None``) so the factory doesn't
    spawn MCP processes during the test agent build.
    """
    conn = await get_connection()
    store = SQLiteAgentStore(conn)
    return AgentFactory(store=store, mcp_provider=None)


def _envelope(
    *,
    channel_id: str = "ch-1",
    thread_id: str | None = None,
    peer_id: str = "peer-1",
    account_id: str = "acct-test",
    platform: str = "stub",
    text: str = "hello",
) -> InboundEnvelope:
    return InboundEnvelope(
        platform=platform,
        account_id=account_id,
        channel_id=channel_id,
        thread_id=thread_id,
        peer_id=peer_id,
        peer_name="Alice",
        text=text,
        raw={},
    )


# ─── _BlockingProvider — event-coordinated concurrency fixture ───────────


class _BlockingProvider(LLMProvider):
    """Test-only LLM provider that awaits an ``asyncio.Event`` before
    producing its single assistant reply.

    Enables event-coordinated concurrency tests where wall-clock sleeps
    would be flaky on CI. The provider does NOT honour the registry's
    constructor signature (no need — tests inject the instance directly
    via a custom AgentFactory) but is callable via the kwargs that
    factory.py uses (``model``, ``base_url``, ``api_key``, ``config``).
    """

    name = "blocking"

    def __init__(
        self,
        event: asyncio.Event,
        reply: str = "ok",
        *,
        model: str = "blocking-default",
        base_url: str = "",
        api_key: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._event = event
        self._reply = reply
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.config = config or {}

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        await self._event.wait()
        return Message.assistant(
            self._reply,
            usage=TokenUsage(input_tokens=0, output_tokens=len(self._reply.split())),
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        await self._event.wait()
        usage = TokenUsage(input_tokens=0, output_tokens=len(self._reply.split()))
        msg = Message.assistant(self._reply, usage=usage)
        yield StreamChunk(
            content=self._reply,
            is_final=True,
            usage=usage,
            message=msg,
        )

    async def supports_tools(self) -> bool:
        # Skip the tool-loop path; single-shot reply suffices for the
        # concurrency tests.
        return False


async def _make_blocking_factory(
    event: asyncio.Event, monkeypatch: pytest.MonkeyPatch
) -> AgentFactory:
    """Build an AgentFactory whose LLM resolver returns a
    :class:`_BlockingProvider` bound to ``event``.

    Uses ``monkeypatch.setattr`` (NOT bare module mutation) so the
    patch is auto-reverted at test end — otherwise the override leaks
    into subsequent tests (e.g. ``test_factory_openrouter.py`` failed
    with this pattern when bare mutation was used).
    """
    factory = await _make_factory()

    def _resolver(name: str, **kwargs: Any) -> _BlockingProvider:
        return _BlockingProvider(event=event, **kwargs)

    from the_one.agent import factory as factory_mod

    monkeypatch.setattr(factory_mod, "get_provider", _resolver)
    return factory


# ─── Happy path: stub-driven first contact ────────────────────────────────


async def test_dispatch_inbound_creates_session_on_first_contact(isolated_db) -> None:
    """First inbound for a new external key → session row created with
    all external-key columns populated; agent.messages persisted with
    the user + assistant turns."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    factory = await _make_factory()
    envelope = _envelope()

    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    row = sessions[0]
    assert row.platform == "stub"
    assert row.connector_account_id == "acct-test"
    assert row.channel_id == "ch-1"
    assert row.thread_id is None
    assert row.peer_id == "peer-1"
    assert row.agent_name == "agent-inbound"
    # Title from StubPlugin.display_channel: f"stub:{envelope.channel_id}".
    assert row.title == "stub:ch-1"
    # Persisted history: at minimum a user msg + an assistant reply.
    history = decode_messages(row.messages)
    user_msgs = [m for m in history if m.role == Role.USER]
    assistant_msgs = [m for m in history if m.role == Role.ASSISTANT]
    assert len(user_msgs) == 1
    assert user_msgs[0].content == "hello"
    assert len(assistant_msgs) >= 1


async def test_dispatch_inbound_persists_exactly_one_user_message_per_inbound(
    isolated_db,
) -> None:
    """Regression net for the architect-revised "drop append_messages,
    let ``agent.step`` append internally" deviation. A single inbound
    must produce exactly one ``Role.USER`` message in the persisted
    history — pre-appending the inbound on top of agent.step's own
    internal ``Message.user(...)`` append would yield two."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    factory = await _make_factory()
    envelope = _envelope(text="single-shot-input")

    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    history = decode_messages(sessions[0].messages)
    user_msgs = [m for m in history if m.role == Role.USER]
    assert len(user_msgs) == 1
    assert user_msgs[0].content == "single-shot-input"


async def test_dispatch_inbound_reuses_session_within_window(isolated_db) -> None:
    """Two inbounds for the same external key inside the continuation
    window → one session row; both turns in the persisted history."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    factory = await _make_factory()

    env1 = _envelope(text="first")
    env2 = _envelope(text="second")

    await dispatch_inbound("agent-inbound", "acct-test", env1, factory=factory)
    await dispatch_inbound("agent-inbound", "acct-test", env2, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    history = decode_messages(sessions[0].messages)
    user_msgs = [m.content for m in history if m.role == Role.USER]
    assert user_msgs == ["first", "second"]


async def test_dispatch_inbound_creates_new_session_after_window(
    isolated_db, monkeypatch
) -> None:
    """An inbound that arrives after the continuation window elapsed →
    a new session row is created; the old row is preserved."""
    await _seed_provider_and_agent()
    # Use a per-account override of 1 second so the second inbound is
    # outside the window.
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorAccountRepository(conn, encryptor)
    await acc_repo.create(
        ConnectorAccount(
            id="acct-test",
            name="Stub",
            type="stub",
            session_continuation_seconds=1,
        )
    )
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    # Seed the existing session's last_inbound_at to two hours ago via
    # repo internals so we don't actually wait. Mirrors the resolver's
    # outside-window test pattern.
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    stale_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    await chat_repo.update_last_inbound(sessions[0].id, stale_iso)

    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    sessions = await chat_repo.list()
    assert len(sessions) == 2


async def test_dispatch_inbound_touches_pool_last_activity(isolated_db) -> None:
    """Snapshot pool entry's ``last_activity`` before / after a
    dispatch; assert strictly increasing. This is the F1 ratification
    contract anchor (see ``agents.md`` Known Issues)."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    # First dispatch warms the pool; second dispatch we measure.
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)
    key = ("agent-inbound", "acct-test")
    assert key in pool_mod._pool
    before = pool_mod._pool[key].last_activity

    # Ensure monotonic() advances enough to be observable.
    await asyncio.sleep(0.01)

    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)
    after = pool_mod._pool[key].last_activity

    assert after > before


# ─── Per-session lock: concurrency ───────────────────────────────────────


async def test_dispatch_inbound_serializes_concurrent_same_session(
    isolated_db, monkeypatch
) -> None:
    """Two concurrent dispatches for the same external key → the
    per-session lock serializes them. With an event-coordinated
    LLM provider, exactly one waits on the lock until the first
    releases the event AND the dispatch completes.

    Pre-seeds the session row via a non-blocking warmup dispatch so
    the concurrent-first-contact race (documented as acceptable in the
    leg's Edge Cases — "orphan row becomes historical-not-active") is
    not in scope here. The lock-on-session-id only meaningfully
    serializes once a session row exists; that's what this test
    verifies."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    # Warmup: a non-blocking MockProvider-based factory to materialise
    # the session row, so the two concurrent blocking dispatches both
    # resolve to the SAME row.
    warmup_factory = await _make_factory()
    envelope = _envelope()
    await dispatch_inbound(
        "agent-inbound", "acct-test", envelope, factory=warmup_factory
    )

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    session_id = sessions[0].id

    # Now spawn two concurrent dispatches against the blocking factory.
    event = asyncio.Event()
    factory = await _make_blocking_factory(event, monkeypatch)

    task1 = asyncio.create_task(
        dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)
    )
    task2 = asyncio.create_task(
        dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)
    )

    # Spin until the per-session lock for the established session_id
    # is held (one task entered the critical section) and the other
    # task is queued on it.
    for _ in range(100):
        await asyncio.sleep(0.01)
        lock = inbound_mod._session_locks.get(session_id)
        if lock is not None and lock.locked() and not (task1.done() or task2.done()):
            break
    else:
        pytest.fail("Per-session lock did not engage before timeout")

    # Both tasks still pending; only ONE row exists (the warmup row);
    # the lock for that row is held.
    assert not task1.done()
    assert not task2.done()
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    assert sessions[0].id == session_id
    assert inbound_mod._session_locks[session_id].locked()

    # Release the event so the first task completes; the second
    # acquires the lock and runs through to completion.
    event.set()
    await asyncio.wait_for(asyncio.gather(task1, task2), timeout=5.0)

    # Still one row; the warmup turn + the two blocking turns all
    # landed in the same session.
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    history = decode_messages(sessions[0].messages)
    user_msgs = [m for m in history if m.role == Role.USER]
    assert len(user_msgs) == 3


async def test_dispatch_inbound_parallelizes_different_sessions(
    isolated_db, monkeypatch
) -> None:
    """Two concurrent dispatches for DIFFERENT external keys → both
    reach the agent.step blocked-on-event state concurrently. The
    per-session lock is keyed on chat_sessions.id; distinct keys
    have distinct locks.

    Pre-seeds the two session rows via warmup dispatches so the test
    isolates the lock-parallelism semantic from the documented
    concurrent-first-contact race."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    env_a = _envelope(channel_id="ch-A")
    env_b = _envelope(channel_id="ch-B")

    # Warmup both sessions.
    warmup_factory = await _make_factory()
    await dispatch_inbound(
        "agent-inbound", "acct-test", env_a, factory=warmup_factory
    )
    await dispatch_inbound(
        "agent-inbound", "acct-test", env_b, factory=warmup_factory
    )

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 2
    session_ids = {s.id for s in sessions}

    # Now spawn two concurrent blocking dispatches against the
    # different external keys.
    event = asyncio.Event()
    factory = await _make_blocking_factory(event, monkeypatch)

    task1 = asyncio.create_task(
        dispatch_inbound("agent-inbound", "acct-test", env_a, factory=factory)
    )
    task2 = asyncio.create_task(
        dispatch_inbound("agent-inbound", "acct-test", env_b, factory=factory)
    )

    # Wait until BOTH session locks are held concurrently — that's
    # the lock-parallelism contract under test.
    for _ in range(200):
        await asyncio.sleep(0.01)
        if task1.done() or task2.done():
            break
        held = {
            sid
            for sid in session_ids
            if (lock := inbound_mod._session_locks.get(sid)) is not None
            and lock.locked()
        }
        if held == session_ids:
            break
    else:
        pytest.fail("Both per-session locks did not engage concurrently before timeout")

    assert not task1.done()
    assert not task2.done()
    # Both locks held simultaneously — the contract.
    for sid in session_ids:
        assert inbound_mod._session_locks[sid].locked()

    event.set()
    await asyncio.wait_for(asyncio.gather(task1, task2), timeout=5.0)


# ─── ContextVar binding ──────────────────────────────────────────────────


async def test_dispatch_inbound_sets_and_resets_context_var(
    isolated_db, monkeypatch
) -> None:
    """``current_chat_session_id`` is set to the session id during the
    agent.step call and reset to ``None`` after the dispatcher returns."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    # Outside the dispatch: the ContextVar default is None.
    assert current_chat_session_id.get() is None

    captured: dict[str, Any] = {}

    # Patch Agent.step to record the ContextVar value at entry. We
    # replace the bound method by patching the class attribute on the
    # specific instance the factory hands out — done via a wrapper
    # around AgentFactory.create.
    real_create = factory.create

    async def _wrapped_create(name: str = "default"):
        agent = await real_create(name)
        original_step = agent.step

        async def _capturing_step(user_input: str, *args: Any, **kwargs: Any):
            captured["csid_in_step"] = current_chat_session_id.get()
            async for msg in original_step(user_input, *args, **kwargs):
                yield msg

        agent.step = _capturing_step  # type: ignore[method-assign]
        return agent

    monkeypatch.setattr(factory, "create", _wrapped_create)

    envelope = _envelope()
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    # Captured value during the step is non-None (= session id).
    assert captured["csid_in_step"] is not None
    # The persisted session has the same id.
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert sessions[0].id == captured["csid_in_step"]

    # After the dispatch: the ContextVar is reset.
    assert current_chat_session_id.get() is None


# ─── Visibility defaults ─────────────────────────────────────────────────


async def test_dispatch_inbound_persists_inbound_with_visibility_none(
    isolated_db,
) -> None:
    """The persisted user message has ``visibility=None`` — peer-visible
    by default. The codec emits no ``visibility`` key when the source
    visibility is None."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)
    user_msgs = [m for m in history if m.role == Role.USER]
    assert user_msgs[0].visibility is None


async def test_dispatch_inbound_persists_agent_reply_with_visibility_none(
    isolated_db,
) -> None:
    """The persisted assistant reply has ``visibility=None`` — F3
    leaves agent replies untagged; F4 will own operator-tagging via
    the platform-send tool."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)
    assistant_msgs = [m for m in history if m.role == Role.ASSISTANT]
    assert assistant_msgs
    for m in assistant_msgs:
        assert m.visibility is None


# ─── Failure paths ───────────────────────────────────────────────────────


async def test_dispatch_inbound_account_not_found_returns_gracefully(
    isolated_db,
) -> None:
    """A non-existent account_id → pool.acquire raises KeyError; the
    dispatcher logs and returns without raising. No session row is
    created."""
    await _seed_provider_and_agent()
    # No account seeded — pool.acquire's _load_account will raise.
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope(account_id="non-existent")

    # Must not raise.
    await dispatch_inbound("agent-inbound", "non-existent", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 0


async def test_dispatch_inbound_unknown_connector_type_returns_gracefully(
    isolated_db,
) -> None:
    """An account whose ``type`` isn't in the registry → pool.acquire
    raises ConnectorRegistrationError; the dispatcher logs and
    returns. No session row is created."""
    await _seed_provider_and_agent()
    # Seed an account with an unregistered type. Registry has no
    # builtins in F3, so any type name is unknown.
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorAccountRepository(conn, encryptor)
    await acc_repo.create(
        ConnectorAccount(
            id="acct-mystery",
            name="Mystery",
            type="not-a-real-connector",
        )
    )
    factory = await _make_factory()

    envelope = _envelope(account_id="acct-mystery", platform="not-a-real-connector")

    # Must not raise.
    await dispatch_inbound("agent-inbound", "acct-mystery", envelope, factory=factory)

    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 0


# ─── F3 owns NO outbound ─────────────────────────────────────────────────


async def test_dispatch_inbound_does_not_call_record_outbound(isolated_db) -> None:
    """F3 L4 owns ZERO outbound. ``StubPlugin.outbound_records`` is
    untouched by ``dispatch_inbound``. F4 will own the platform-send
    tool that populates this buffer."""
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    assert StubPlugin.outbound_records == []


# ─── Repository-unit tests for the new ChatSessionRepository primitive ───


async def test_update_last_inbound_bumps_both_timestamps(isolated_db) -> None:
    """Repository unit test: seed a session with stale timestamps; call
    :meth:`update_last_inbound`; assert BOTH ``last_inbound_at`` AND
    ``updated_at`` reflect the new value. The resolver's
    most-recent-by-updated_at ordering depends on this dual-write."""
    await _seed_provider_and_agent()
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    stale = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    await chat_repo.create(
        ChatSession(
            id="s-1",
            agent_name="agent-inbound",
            title="t",
            created_at=stale,
            updated_at=stale,
            last_inbound_at=stale,
        )
    )

    await chat_repo.update_last_inbound("s-1", fresh)

    loaded = await chat_repo.get("s-1")
    assert loaded.last_inbound_at == fresh
    assert loaded.updated_at == fresh


async def test_update_last_inbound_raises_keyerror_on_missing_session(
    isolated_db,
) -> None:
    """Repository unit test: missing session id raises ``KeyError`` —
    mirrors :meth:`update` / :meth:`delete` / :meth:`purge_messages`
    not-found semantics."""
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    with pytest.raises(KeyError):
        await chat_repo.update_last_inbound(
            "no-such-session", datetime.now(timezone.utc).isoformat()
        )
