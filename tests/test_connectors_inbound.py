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

import pytest

# F4 L5 (M10 F3 debrief carry-forward): the in-file helpers
# (``isolated_db``, ``_seed_provider_and_agent``, ``_seed_stub_account``,
# ``_make_factory``, ``_envelope``, ``_ScriptedProvider``,
# ``_make_scripted_factory``) moved to ``tests/_connector_dispatch_helpers``
# when ``tests/test_connectors_e2e_platform_send.py`` became the THIRD
# consumer. Pytest only auto-discovers fixtures from ``conftest.py``, so
# the ``isolated_db`` fixture must be explicitly imported into this module
# for tests here to consume it as a function argument.
from tests._connector_dispatch_helpers import (
    StubPluginWithResolver,
    _envelope,
    _make_factory,
    _make_scripted_factory,
    _ScriptedProvider,  # noqa: F401 — kept for downstream-test access
    _seed_provider_and_agent,
    _seed_stub_account,
)
from the_one.agent._context import current_chat_session_id
from the_one.agent.factory import AgentFactory
from the_one.config import settings
from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
from the_one.connectors import _inbound as inbound_mod
from the_one.connectors import _pool as pool_mod
from the_one.connectors._inbound import dispatch_inbound
from the_one.connectors._stub import StubPlugin
from the_one.connectors.base import Deny, NeedsPairing, Permit
from the_one.connectors.errors import ConnectorConnectionError
from the_one.connectors.registry import (
    clear_for_test as _registry_clear_for_test,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.models import ChatSession, ConnectorAccount
from the_one.db.repositories import (
    ChatSessionRepository,
    ConnectorAccountRepository,
)
from the_one.encryption import get_encryptor
from the_one.llm.base import LLMProvider, Message, Role, StreamChunk, TokenUsage, ToolCall
from the_one.sessions import clear_for_test as _clear_session_registry
from the_one.sessions import session_locks

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
    # F5 L2: also clear the neutral session registries (shared lock +
    # subscribers). The inbound _clear_for_test delegates to the lock
    # registry already, but the convenience helper also clears
    # subscribers and keeps the call symmetrical with other autouse
    # fixtures.
    _clear_session_registry()
    # Hard-clear then restore baseline so each test starts from the
    # production-shaped registry (currently empty in F3).
    _registry_clear_for_test()
    restore_to_baseline_for_test()


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

    await dispatch_inbound("acct-test", envelope, factory=factory)

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

    await dispatch_inbound("acct-test", envelope, factory=factory)

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

    await dispatch_inbound("acct-test", env1, factory=factory)
    await dispatch_inbound("acct-test", env2, factory=factory)

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
    await dispatch_inbound("acct-test", envelope, factory=factory)

    # Seed the existing session's last_inbound_at to two hours ago via
    # repo internals so we don't actually wait. Mirrors the resolver's
    # outside-window test pattern.
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    stale_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    await chat_repo.update_last_inbound(sessions[0].id, stale_iso)

    await dispatch_inbound("acct-test", envelope, factory=factory)

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
    await dispatch_inbound("acct-test", envelope, factory=factory)
    # M10 F8 L11 HAT Fix #6: pool keys on the connector sentinel,
    # not the agent name — all agents attached to one account share
    # one gateway connection.
    key = (pool_mod._ACCOUNT_POOL_AGENT_SLOT, "acct-test")
    assert key in pool_mod._pool
    before = pool_mod._pool[key].last_activity

    # Ensure monotonic() advances enough to be observable.
    await asyncio.sleep(0.01)

    await dispatch_inbound("acct-test", envelope, factory=factory)
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
    await dispatch_inbound("acct-test", envelope, factory=warmup_factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    session_id = sessions[0].id

    # Now spawn two concurrent dispatches against the blocking factory.
    event = asyncio.Event()
    factory = await _make_blocking_factory(event, monkeypatch)

    task1 = asyncio.create_task(
        dispatch_inbound("acct-test", envelope, factory=factory)
    )
    task2 = asyncio.create_task(
        dispatch_inbound("acct-test", envelope, factory=factory)
    )

    # Spin until the per-session lock for the established session_id
    # is held (one task entered the critical section) and the other
    # task is queued on it.
    for _ in range(100):
        await asyncio.sleep(0.01)
        lock = session_locks.get(session_id)
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
    assert session_locks[session_id].locked()

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
    await dispatch_inbound("acct-test", env_a, factory=warmup_factory)
    await dispatch_inbound("acct-test", env_b, factory=warmup_factory)

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
        dispatch_inbound("acct-test", env_a, factory=factory)
    )
    task2 = asyncio.create_task(
        dispatch_inbound("acct-test", env_b, factory=factory)
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
            if (lock := session_locks.get(sid)) is not None
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
        assert session_locks[sid].locked()

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
    await dispatch_inbound("acct-test", envelope, factory=factory)

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
    visibility is None.

    F4 L4: USER messages are skipped by the visibility-tagging pass —
    the peer inbound stays ``visibility=None``.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)
    user_msgs = [m for m in history if m.role == Role.USER]
    assert user_msgs[0].visibility is None


async def test_dispatch_inbound_persists_agent_reply_with_visibility_operator(
    isolated_db,
) -> None:
    """The persisted assistant reply has ``visibility="operator"`` —
    F4 L4 owns operator-tagging; the dispatcher's post-step pass tags
    every non-USER new message in a connector-attached session as
    operator-only by default. The successful-platform-send-tool_result
    carve-out is exercised in
    ``test_dispatch_inbound_tags_successful_send_tool_result_as_platform_visible``.

    M10 F8 L11 HAT Fix #4: auto-relay is opted OUT here so this test
    continues to exercise the pre-auto-relay operator-tagging branch in
    isolation. The auto-relay-flips-visibility branch is covered by the
    new dedicated tests in this file.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account(
        config={"auto_relay_platform_replies": False}
    )
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)
    assistant_msgs = [m for m in history if m.role == Role.ASSISTANT]
    assert assistant_msgs
    for m in assistant_msgs:
        assert m.visibility == OPERATOR_VISIBILITY


# ─── F4 L4 visibility-tagging coverage ───────────────────────────────────


async def test_dispatch_inbound_tags_assistant_text_as_operator(
    isolated_db,
) -> None:
    """Plain-text assistant reply (no tool call) → ``visibility="operator"``.

    The default branch of the F4 L4 tagging pass: every non-USER new
    message in a connector-attached session is operator-only unless the
    successful-platform-send carve-out fires.

    M10 F8 L11 HAT Fix #4: auto-relay is opted OUT here so this test
    pins the pre-auto-relay tagging pass in isolation. The
    auto-relay-flips-plaintext-to-platform-visible branch is covered
    separately.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account(
        config={"auto_relay_platform_replies": False}
    )
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)
    assistant_msgs = [m for m in history if m.role == Role.ASSISTANT]
    assert assistant_msgs
    for m in assistant_msgs:
        # Plain-text reply (no tool_calls); falls through to the default
        # OPERATOR_VISIBILITY branch.
        assert m.tool_calls == []
        assert m.visibility == OPERATOR_VISIBILITY


async def test_dispatch_inbound_tags_successful_send_tool_result_as_platform_visible(
    isolated_db, monkeypatch
) -> None:
    """A successful ``send_to_platform_channel`` tool_result → ``visibility=None``.

    The carve-out fires when ALL THREE of: ``Role.TOOL``, parent
    tool_call name == ``"send_to_platform_channel"``, ``content``
    starts with :data:`PLATFORM_SEND_OK_PREFIX`. The assistant message
    that REQUESTED the tool call stays ``OPERATOR_VISIBILITY``.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    # Iteration 1: assistant requests platform-send.
    # Iteration 2: assistant emits plain text to end the turn.
    tc = ToolCall(
        id="tc-send-1",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "ch-1"},
            "content": "hello peer",
        },
    )
    responses = [
        Message.assistant(content="", tool_calls=[tc]),
        Message.assistant(content="done"),
    ]
    factory = await _make_scripted_factory(
        responses, monkeypatch, connector_account_ids=["acct-test"]
    )

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    # The stub recorded the outbound — confirms the tool actually fired.
    assert len(StubPlugin.outbound_records) == 1

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)

    # Assistant message that carried the tool_call → OPERATOR (per the
    # default branch — it's not a USER message and not a tool_result).
    assistant_with_call = [
        m for m in history if m.role == Role.ASSISTANT and m.tool_calls
    ]
    assert assistant_with_call
    for m in assistant_with_call:
        assert m.visibility == OPERATOR_VISIBILITY

    # Tool_result for the platform-send → visibility=None (peer-visible).
    tool_msgs = [m for m in history if m.role == Role.TOOL]
    assert tool_msgs
    send_results = [
        m
        for m in tool_msgs
        if m.tool_result is not None
        and m.content.startswith(PLATFORM_SEND_OK_PREFIX)
    ]
    assert send_results, "expected a successful platform-send tool_result"
    for m in send_results:
        assert m.visibility is None


async def test_dispatch_inbound_tags_failed_send_tool_result_as_operator(
    isolated_db, monkeypatch
) -> None:
    """A failed ``send_to_platform_channel`` tool_result → ``OPERATOR_VISIBILITY``.

    When the platform send raises, the tool returns an
    ``[error] ConnectorConnectionError: ...`` envelope WITHOUT the
    :data:`PLATFORM_SEND_OK_PREFIX`. The prefix-check sub-predicate
    fails → the tool_result drops through to the default
    ``OPERATOR_VISIBILITY`` branch.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    StubPlugin.send_should_raise = ConnectorConnectionError("test failure")

    tc = ToolCall(
        id="tc-send-fail",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "ch-1"},
            "content": "hello peer",
        },
    )
    responses = [
        Message.assistant(content="", tool_calls=[tc]),
        Message.assistant(content="done"),
    ]
    factory = await _make_scripted_factory(
        responses, monkeypatch, connector_account_ids=["acct-test"]
    )

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)

    tool_msgs = [m for m in history if m.role == Role.TOOL]
    assert tool_msgs
    for m in tool_msgs:
        # Failure envelope does NOT carry the success prefix.
        assert not m.content.startswith(PLATFORM_SEND_OK_PREFIX)
        assert m.visibility == OPERATOR_VISIBILITY


async def test_dispatch_inbound_tagging_uses_tool_result_tool_call_id_correlation(
    isolated_db, monkeypatch
) -> None:
    """Correlation is by (tool_call_id → tool_name), not by content prefix.

    Drive an assistant message with TWO tool_calls: one to
    ``send_to_platform_channel`` (success) and one to a non-platform-
    send in-test tool that ALSO returns a string starting with
    :data:`PLATFORM_SEND_OK_PREFIX`. Only the platform-send's
    tool_result gets ``visibility=None`` — the in-test tool's
    tool_result keeps ``OPERATOR_VISIBILITY`` because the name-check
    sub-predicate fails despite the prefix-check passing.

    This is a regression net against a future mis-simplification that
    drops the name check and decides visibility purely on the content
    prefix.
    """
    from the_one.tools.base import Tool

    class _FakePrefixTool(Tool):
        name = "fake_prefix_tool"
        description = "Returns a string starting with the platform-send prefix."
        parameters = {"type": "object", "properties": {}, "required": []}

        async def execute(self, **_kwargs: Any) -> str:  # type: ignore[override]
            return f"{PLATFORM_SEND_OK_PREFIX} but-not-really-a-platform-send"

    class _FakePrefixProvider:
        """Minimal ToolProvider that yields :class:`_FakePrefixTool`."""

        @property
        def name(self) -> str:
            return "fake-prefix"

        def get_tools(
            self,
            tool_configs: dict[str, dict] | None = None,
            agent_overrides: dict[str, dict] | None = None,
            agent_name: str | None = None,
        ) -> list[Tool]:
            return [_FakePrefixTool()]

    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    tc_send = ToolCall(
        id="tc-send-corr",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "ch-1"},
            "content": "hello peer",
        },
    )
    tc_fake = ToolCall(
        id="tc-fake-corr",
        name="fake_prefix_tool",
        arguments={},
    )
    responses = [
        Message.assistant(content="", tool_calls=[tc_send, tc_fake]),
        Message.assistant(content="done"),
    ]
    factory = await _make_scripted_factory(
        responses,
        monkeypatch,
        extra_tool_providers=[_FakePrefixProvider()],
        connector_account_ids=["acct-test"],
    )

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)

    tool_msgs = [m for m in history if m.role == Role.TOOL]
    # Both tool_results should be present.
    by_id = {m.tool_result.tool_call_id: m for m in tool_msgs if m.tool_result}
    assert "tc-send-corr" in by_id
    assert "tc-fake-corr" in by_id

    # The platform-send tool_result → visibility=None (carve-out fires).
    send_msg = by_id["tc-send-corr"]
    assert send_msg.content.startswith(PLATFORM_SEND_OK_PREFIX)
    assert send_msg.visibility is None

    # The fake-prefix tool_result → OPERATOR_VISIBILITY, even though
    # its content starts with PLATFORM_SEND_OK_PREFIX. The carve-out
    # requires name == "send_to_platform_channel" AS WELL — not just
    # the prefix.
    fake_msg = by_id["tc-fake-corr"]
    assert fake_msg.content.startswith(PLATFORM_SEND_OK_PREFIX)
    assert fake_msg.visibility == OPERATOR_VISIBILITY


async def test_dispatch_inbound_continue_tool_call_is_operator_visible(
    isolated_db, monkeypatch
) -> None:
    """The agent's virtual ``continue`` tool_call → ``OPERATOR_VISIBILITY``.

    ``continue`` synthesises its own tool_result inside
    :meth:`Agent._dispatch_tool_calls` (no real tool dispatch). The
    synthesised tool_result is a ``Role.TOOL`` message; its parent
    tool_call name is ``"continue"`` — NOT ``"send_to_platform_channel"``
    — so the carve-out predicate fails on the name check, and the
    tool_result falls through to the default operator branch.

    Pins the default-branch path for the ``continue`` signal so a future
    refactor that special-cases continue handling doesn't accidentally
    promote it to platform-visible.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    tc = ToolCall(
        id="tc-cont-1",
        name="continue",
        arguments={"reason": "keep going"},
    )
    responses = [
        Message.assistant(content="", tool_calls=[tc]),
        Message.assistant(content="done"),
    ]
    factory = await _make_scripted_factory(
        responses, monkeypatch, connector_account_ids=["acct-test"]
    )

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)

    # The continue tool_result is the synthesised Role.TOOL message
    # whose parent tool_call id matches the continue ToolCall above.
    tool_msgs = [
        m
        for m in history
        if m.role == Role.TOOL
        and m.tool_result is not None
        and m.tool_result.tool_call_id == "tc-cont-1"
    ]
    assert tool_msgs, "expected the continue's synthesised tool_result"
    for m in tool_msgs:
        assert m.visibility == OPERATOR_VISIBILITY

    # The assistant message that emitted the continue tool_call also
    # gets OPERATOR_VISIBILITY (default branch — not a USER message).
    assistant_with_continue = [
        m
        for m in history
        if m.role == Role.ASSISTANT
        and any(c.name == "continue" for c in m.tool_calls)
    ]
    assert assistant_with_continue
    for m in assistant_with_continue:
        assert m.visibility == OPERATOR_VISIBILITY


# ─── Failure paths ───────────────────────────────────────────────────────


async def test_dispatch_inbound_account_not_found_returns_gracefully(
    isolated_db,
) -> None:
    """A non-existent account_id → no agents are attached → the F7 L3
    transitional helper returns ``None`` → the dispatcher logs and
    returns without raising, BEFORE pool.acquire. No session row is
    created.

    M10 F7 L3: the failure source shifted from "pool.acquire raises
    KeyError on missing account row" to "no attached agents → helper
    returns ``None`` → early silent return." The observable outcome
    (no exception, no session) is byte-identical."""
    await _seed_provider_and_agent()
    # No account seeded — pool.acquire's _load_account will raise.
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope(account_id="non-existent")

    # Must not raise.
    await dispatch_inbound("non-existent", envelope, factory=factory)

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 0


async def test_dispatch_inbound_unknown_connector_type_returns_gracefully(
    isolated_db,
) -> None:
    """An account whose ``type`` isn't in the registry → no agents are
    attached to that account → the F7 L3 transitional helper returns
    ``None`` → the dispatcher logs and returns BEFORE pool.acquire.
    No session row is created.

    M10 F7 L3: the failure source shifted from "pool.acquire raises
    ConnectorRegistrationError on unknown type" to "no attached agents
    → helper returns ``None`` → early silent return." The observable
    outcome (no exception, no session) is byte-identical.

    M10 F8 L2: the Pydantic Literal narrowing now rejects bogus type
    names at the model edge, so the test seeds a ``'stub'``-typed account
    AND clears the registry (the production registry registers
    ``'discord'`` only; ``'stub'`` is test-only via
    :func:`register_for_test`). With ``register_for_test`` never called
    here, the dispatcher encounters an account whose type is unknown to
    the registry — exercising the same gracefully-handle-unknown-type
    path the test was designed for, just via the post-F8 carve-out
    instead of an unconstrained type string.
    """
    from the_one.connectors.registry import clear_for_test

    await _seed_provider_and_agent()
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorAccountRepository(conn, encryptor)
    await acc_repo.create(
        ConnectorAccount(
            id="acct-mystery",
            name="Mystery",
            type="stub",
        )
    )
    # Wipe the registry so dispatch encounters "type unknown" on the
    # ``stub``-typed account. Note that the production registry would
    # carry ``'discord'`` at this point; ``clear_for_test`` is a hard
    # clear that drops it for the duration of this test.
    clear_for_test()
    factory = await _make_factory()

    envelope = _envelope(account_id="acct-mystery", platform="stub")

    # Must not raise.
    await dispatch_inbound("acct-mystery", envelope, factory=factory)

    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 0


# ─── F3 owns NO outbound ─────────────────────────────────────────────────


async def test_dispatch_inbound_does_not_call_record_outbound(isolated_db) -> None:
    """F3 L4 owns ZERO outbound. ``StubPlugin.outbound_records`` is
    untouched by ``dispatch_inbound``. F4 will own the platform-send
    tool that populates this buffer.

    M10 F8 L11 HAT Fix #4: auto-relay (default-on) is opted OUT here so
    the F3-era invariant ("dispatcher itself does not own platform
    outbound") still holds when explicitly disabled. The
    auto-relay-default-on path that DOES drive ``client.send`` from the
    dispatcher is covered by
    ``test_auto_relay_default_on_platform_inbound_invokes_client_send``.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account(
        config={"auto_relay_platform_replies": False}
    )
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    assert StubPlugin.outbound_records == []


# ─── M10 F8 L11 HAT Fix #4: auto-relay platform replies ──────────────────


async def test_auto_relay_default_on_platform_inbound_invokes_client_send(
    isolated_db,
) -> None:
    """Default-on auto-relay: a platform inbound where the agent
    produces a plaintext reply (without calling ``send_to_platform_channel``)
    triggers the dispatcher's mechanical ``client.send`` on behalf of
    the agent. ``StubPlugin.outbound_records`` captures the relayed
    content.

    The persisted assistant message's visibility flips from
    ``OPERATOR_VISIBILITY`` (default of the F4 L4 tagging pass) to
    ``None`` (platform-visible) — because the message DID make it to
    peers via this relay, the Chat UI must render it correctly as a
    platform-bound reply.
    """
    await _seed_provider_and_agent(response_content="hi from agent")
    # Default config — no opt-out — so auto-relay default-True fires.
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    # Auto-relay went through StubClient.send → recorded on StubPlugin.
    assert len(StubPlugin.outbound_records) == 1
    target, content = StubPlugin.outbound_records[0]
    assert target.channel_id == envelope.channel_id
    assert target.thread_id == envelope.thread_id
    assert content == "hi from agent"

    # The persisted assistant reply is now platform-visible (visibility
    # flipped from OPERATOR_VISIBILITY → None by the auto-relay branch).
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)
    assistant_msgs = [m for m in history if m.role == Role.ASSISTANT]
    plaintext_replies = [
        m for m in assistant_msgs if not m.tool_calls and m.content
    ]
    assert plaintext_replies, "expected a plaintext assistant reply"
    for m in plaintext_replies:
        assert m.visibility is None, (
            "auto-relayed plaintext reply must be platform-visible "
            "(visibility=None)"
        )


async def test_auto_relay_off_platform_inbound_does_not_invoke_client_send(
    isolated_db,
) -> None:
    """Opt-out: ``account.config["auto_relay_platform_replies"] = False``
    disables the auto-relay. The agent's plaintext reply stays
    operator-only and the dispatcher does NOT call ``client.send``.

    The pre-Fix-#4 invariant (agent must explicitly invoke
    ``send_to_platform_channel`` to reach peers) is preserved on the
    opt-out path.
    """
    await _seed_provider_and_agent(response_content="silent reply")
    await _seed_stub_account(
        config={"auto_relay_platform_replies": False}
    )
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    assert StubPlugin.outbound_records == []

    # Reply stays operator-only.
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)
    plaintext_replies = [
        m for m in history
        if m.role == Role.ASSISTANT and not m.tool_calls and m.content
    ]
    assert plaintext_replies
    for m in plaintext_replies:
        assert m.visibility == OPERATOR_VISIBILITY


async def test_auto_relay_skips_when_agent_already_called_tool(
    isolated_db, monkeypatch
) -> None:
    """When the agent invokes ``send_to_platform_channel`` during the
    step, the auto-relay branch detects the tool call in the new
    messages and skips — avoiding a double-send to peers.

    The platform-send tool's own outbound (recorded once) IS captured
    by ``StubPlugin.outbound_records``; the dispatcher MUST NOT add a
    second record.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    # Iter1: assistant invokes the platform-send tool.
    # Iter2: assistant emits final plaintext to end the turn.
    tc = ToolCall(
        id="tc-send-no-double",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "ch-1"},
            "content": "agent-deliberate send",
        },
    )
    responses = [
        Message.assistant(content="", tool_calls=[tc]),
        Message.assistant(content="done"),
    ]
    factory = await _make_scripted_factory(
        responses, monkeypatch, connector_account_ids=["acct-test"]
    )

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    # Exactly ONE outbound — from the platform-send tool. The auto-relay
    # branch detected the tool call and skipped its own client.send.
    assert len(StubPlugin.outbound_records) == 1
    _target, content = StubPlugin.outbound_records[0]
    assert content == "agent-deliberate send"


async def test_auto_relay_skips_when_agent_reply_is_empty(
    isolated_db, monkeypatch
) -> None:
    """When the agent produces no plaintext (e.g. only tool calls and
    a final empty assistant message), the auto-relay branch finds no
    candidate reply and skips — no spurious empty-content outbound.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    # The scripted provider returns an assistant with empty content
    # and no tool calls — the agent ends the turn with nothing to say.
    responses = [Message.assistant(content="")]
    factory = await _make_scripted_factory(
        responses, monkeypatch, connector_account_ids=["acct-test"]
    )

    envelope = _envelope()
    await dispatch_inbound("acct-test", envelope, factory=factory)

    # No outbound recorded — auto-relay had nothing to relay.
    assert StubPlugin.outbound_records == []


async def test_auto_relay_handles_client_send_exception_gracefully(
    isolated_db,
) -> None:
    """``client.send`` raising mid-relay must be logged + swallowed —
    the inbound is still considered handled (the dispatcher returns
    cleanly), and the agent's reply is preserved as operator-only
    (the visibility flip never happens because the send raised before
    it).
    """
    await _seed_provider_and_agent(response_content="reply text")
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    # Make StubClient.send raise on every call.
    StubPlugin.send_should_raise = ConnectorConnectionError(
        "auto-relay send failure"
    )
    factory = await _make_factory()

    envelope = _envelope()
    # Must NOT raise — auto-relay swallows the failure.
    await dispatch_inbound("acct-test", envelope, factory=factory)

    # No outbound recorded (the raise pre-empts record_outbound).
    assert StubPlugin.outbound_records == []

    # Reply stays in history with operator-only visibility (the flip
    # never ran because the send raised before it).
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    history = decode_messages(sessions[0].messages)
    plaintext_replies = [
        m for m in history
        if m.role == Role.ASSISTANT and not m.tool_calls and m.content
    ]
    assert plaintext_replies
    for m in plaintext_replies:
        assert m.visibility == OPERATOR_VISIBILITY


async def test_auto_relay_does_not_fire_on_operator_console_inbound(
    isolated_db, monkeypatch
) -> None:
    """Operator-typed inbound (Chat UI WS path) does NOT route through
    ``dispatch_inbound`` — it goes through
    :func:`_spawn_message_processing` in ``interfaces/web/app.py``,
    which has NO auto-relay code. By construction the agent's plaintext
    reply stays in the operator console and the auto-relay branch
    cannot fire.

    Pins this structural separation as a regression net so a future
    "unify the two entry points" refactor doesn't accidentally route
    operator-typed input through the auto-relay branch.
    """
    from the_one.db.models import ChatSession
    from the_one.interfaces.web import app as web_app
    from the_one.interfaces.web.app import (
        _get_or_restore_session,
        _spawn_message_processing,
    )

    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    # Auto-relay is default-on — explicit no-config-override below.
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    async def _noop(*args, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(web_app, "_send_to_session", _noop)
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop)

    # Seed a connector-attached chat session.
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    session_id = "cs-auto-relay-operator-typed"
    await chat_repo.create(
        ChatSession(
            id=session_id,
            agent_name="agent-inbound",
            title="connector session",
            platform="stub",
            connector_account_id="acct-test",
            channel_id="ch-1",
            thread_id=None,
            peer_id="peer-1",
            messages="[]",
        )
    )

    factory = await _make_scripted_factory(
        [Message.assistant(content="operator-only reply")],
        monkeypatch,
        connector_account_ids=["acct-test"],
    )
    web_app._state["factory"] = factory

    try:
        restored = await _get_or_restore_session(session_id)
        assert restored.session is not None
        await _spawn_message_processing(
            restored.session,
            "operator types here",
            source="web",
            exclude_user_echo=None,
        )

        # No auto-relay outbound — the operator-typed path has no
        # auto-relay logic. ``client.send`` was never called from this
        # entry point.
        assert StubPlugin.outbound_records == []
    finally:
        web_app._sessions.clear()


# ─── M10 F8 L11 HAT Fix #6: multi-agent auto-relay shares one client ─────


async def test_multi_agent_auto_relay_shares_one_pool_client(
    isolated_db,
) -> None:
    """Auto-relay's pool acquire goes through ``account_acquire`` so
    every agent attached to one connector account relays via the SAME
    ``ConnectorClient`` instance.

    The dispatcher's step-10 acquire and the step-12 auto-relay
    acquire both resolve to the same warm pool entry — one gateway
    connection, one client object, regardless of which agent's
    plaintext reply is being relayed.
    """
    # Seed two agents sharing one account.
    await _seed_provider_and_agent(
        agent_name="alpha",
        response_content="alpha reply",
        connector_account_ids=["acct-test"],
    )
    from the_one.agent.config import AgentConfig
    from the_one.db.repositories import SQLiteAgentStore

    conn = await get_connection()
    agent_store = SQLiteAgentStore(conn)
    await agent_store.save(
        AgentConfig(
            name="bravo",
            provider_config_id="mock-provider",
            llm_model="mock-default",
            connector_account_ids=["acct-test"],
        )
    )

    # Routing rule: ch-1 → bravo; ch-2 falls back to alpha (alphabetical).
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorAccountRepository(conn, encryptor)
    await acc_repo.create(
        ConnectorAccount(
            id="acct-test",
            name="Stub Routing",
            type="stub",
            config={
                "routing": {
                    "rules": [
                        {"scope": "channel", "match": ["ch-1"], "agent": "bravo"},
                    ],
                    "default": None,
                },
            },
        )
    )
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    # Drive both inbounds — both should auto-relay (default-on).
    await dispatch_inbound(
        "acct-test", _envelope(channel_id="ch-1"), factory=factory
    )
    await dispatch_inbound(
        "acct-test", _envelope(channel_id="ch-2"), factory=factory
    )

    # Both relays landed via StubPlugin.outbound_records (mock provider
    # produces ``"ok"`` by default — bravo's agent config uses the same
    # mock provider so its content is also ``"ok"``).
    assert len(StubPlugin.outbound_records) == 2

    # plugin.connect was called exactly ONCE — the second auto-relay
    # acquire reused the warm pool entry. This is the structural
    # invariant Fix #6 enforces.
    assert StubPlugin.connect_calls == [("acct-test", "stub")]

    # Pool has exactly one entry, sentinel-keyed.
    keys_for_account = [
        k for k in pool_mod._pool if k[1] == "acct-test"
    ]
    assert len(keys_for_account) == 1
    assert keys_for_account[0] == (
        pool_mod._ACCOUNT_POOL_AGENT_SLOT,
        "acct-test",
    )


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


# ─── M10 F06 L2: TestF6Gating — resolver consult + pairing + audit ───────


class TestF6Gating:
    """Coverage for the F6 leg-2 dispatcher gating block.

    The block lives between ``resolve_session`` and the per-session
    lock in ``the_one/connectors/_inbound.py``. The resolver hook is
    consulted via ``getattr(plugin, "resolve", _default_permit)``;
    outcomes are ``Permit`` / ``NeedsPairing`` / ``Deny``. Every gate
    decision writes an audit entry to ``session_metadata["audit"]``
    with uniform shape ``{"outcome", "peer_id", "ts", "reason"}``.

    ``last_inbound_at`` is intentionally NOT bumped on Deny /
    NeedsPairing-failure — those branches return BEFORE entering the
    per-session lock that owns the ``update_last_inbound`` call.
    """

    @pytest.fixture(autouse=True)
    def _reset_resolver_stub_state(self):
        """Reset the variant stub's class-level resolver state per test."""
        StubPluginWithResolver.reset_for_test()
        yield
        StubPluginWithResolver.reset_for_test()

    @staticmethod
    async def _audit_entries(session_id: str) -> list[dict[str, Any]]:
        """Helper: fetch the audit list from a session's metadata."""
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        session = await chat_repo.get(session_id)
        if session.session_metadata is None:
            return []
        return session.session_metadata.get("audit", [])

    @staticmethod
    async def _list_first_session() -> ChatSession:
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        sessions = await chat_repo.list()
        assert len(sessions) == 1
        return sessions[0]

    async def test_stub_without_resolve_permits_via_default_fallback(
        self, isolated_db
    ) -> None:
        """``StubPlugin`` (no ``resolve``) hits ``_default_permit`` →
        dispatch proceeds; audit entry shows ``outcome=permit`` with
        ``reason=None`` (uniform shape for the leg-4 renderer).
        """
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        envelope = _envelope()
        await dispatch_inbound("acct-test", envelope, factory=factory)

        session = await self._list_first_session()
        history = decode_messages(session.messages)
        # agent.step ran — both a USER and an ASSISTANT message landed.
        assert any(m.role == Role.USER for m in history)
        assert any(m.role == Role.ASSISTANT for m in history)
        audit = await self._audit_entries(session.id)
        assert len(audit) == 1
        assert audit[0]["outcome"] == "permit"
        assert audit[0]["peer_id"] == "peer-1"
        assert audit[0]["reason"] is None
        assert "ts" in audit[0]

    async def test_permit_outcome_dispatches_and_writes_audit(
        self, isolated_db
    ) -> None:
        """The variant stub returning ``Permit()`` dispatches normally
        and the audit log records the outcome with ``reason=None``."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        StubPluginWithResolver.resolve_outcome = Permit()
        register_for_test("stub", StubPluginWithResolver)

        factory = await _make_factory()
        envelope = _envelope(text="hi there")
        await dispatch_inbound("acct-test", envelope, factory=factory)

        # Resolver was consulted once with the expected args.
        assert StubPluginWithResolver.resolve_calls == [("acct-test", "peer-1")]

        session = await self._list_first_session()
        history = decode_messages(session.messages)
        user_msgs = [m for m in history if m.role == Role.USER]
        assert len(user_msgs) == 1
        # The envelope text was NOT mutated on the Permit path.
        assert user_msgs[0].content == "hi there"

        audit = await self._audit_entries(session.id)
        assert len(audit) == 1
        assert audit[0] == {
            "outcome": "permit",
            "peer_id": "peer-1",
            "ts": audit[0]["ts"],
            "reason": None,
        }

    async def test_needs_pairing_with_valid_prefix_strips_persists_dispatches(
        self, isolated_db
    ) -> None:
        """NeedsPairing + ``PAIR X hello`` against ``pairing.code='X'``:
        strips the prefix, persists ``peer_id`` into the allowlist,
        records ``outcome=permit, reason=paired``, and dispatches with
        the CLEANED text.
        """
        await _seed_provider_and_agent()
        # Seed an account with the pairing config configured.
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Pairing",
                type="stub",
                config={
                    "pairing": {
                        "code": "X",
                        "issued_at": "2026-05-18T00:00:00+00:00",
                    },
                },
            )
        )
        StubPluginWithResolver.resolve_outcome = NeedsPairing(
            reason="unknown_peer"
        )
        register_for_test("stub", StubPluginWithResolver)

        factory = await _make_factory()
        envelope = _envelope(text="PAIR X hello")
        await dispatch_inbound("acct-test", envelope, factory=factory)

        # Account row reflects the persisted allowlist mutation.
        refreshed = await acc_repo.get("acct-test")
        allowlist = refreshed.config.get("allowlist")
        assert allowlist is not None
        assert "peer-1" in allowlist["peers"]
        assert allowlist["channels"] == []

        # The user message persisted is the CLEANED text (prefix stripped).
        session = await self._list_first_session()
        history = decode_messages(session.messages)
        user_msgs = [m for m in history if m.role == Role.USER]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "hello"

        audit = await self._audit_entries(session.id)
        assert len(audit) == 1
        assert audit[0]["outcome"] == "permit"
        assert audit[0]["reason"] == "paired"
        assert audit[0]["peer_id"] == "peer-1"

    async def test_needs_pairing_with_invalid_prefix_denies_silently(
        self, isolated_db
    ) -> None:
        """NeedsPairing + ``PAIR wrong hello`` (wrong code): silent
        deny — audit logged, allowlist unchanged, agent.step did NOT
        run (no assistant message in history).
        """
        await _seed_provider_and_agent()
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Pairing",
                type="stub",
                config={
                    "pairing": {
                        "code": "X",
                        "issued_at": "2026-05-18T00:00:00+00:00",
                    },
                },
            )
        )
        StubPluginWithResolver.resolve_outcome = NeedsPairing(
            reason="unknown_peer"
        )
        register_for_test("stub", StubPluginWithResolver)

        factory = await _make_factory()
        envelope = _envelope(text="PAIR wrong hello")
        await dispatch_inbound("acct-test", envelope, factory=factory)

        # Allowlist is unchanged (absent in the original config).
        refreshed = await acc_repo.get("acct-test")
        assert refreshed.config.get("allowlist") is None

        # Session was materialised (for the audit target) but no
        # agent.step turn landed — no USER / ASSISTANT messages.
        session = await self._list_first_session()
        history = decode_messages(session.messages)
        assert all(m.role not in (Role.USER, Role.ASSISTANT) for m in history)

        audit = await self._audit_entries(session.id)
        assert len(audit) == 1
        assert audit[0]["outcome"] == "deny"
        # The dispatcher prefers the NeedsPairing.reason when non-empty.
        assert audit[0]["reason"] == "unknown_peer"
        assert audit[0]["peer_id"] == "peer-1"

    async def test_needs_pairing_with_no_prefix_denies(
        self, isolated_db
    ) -> None:
        """NeedsPairing + ``hello`` (no prefix at all): same silent
        deny semantics, audit logged."""
        await _seed_provider_and_agent()
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Pairing",
                type="stub",
                config={
                    "pairing": {
                        "code": "X",
                        "issued_at": "2026-05-18T00:00:00+00:00",
                    },
                },
            )
        )
        StubPluginWithResolver.resolve_outcome = NeedsPairing(reason="")
        register_for_test("stub", StubPluginWithResolver)

        factory = await _make_factory()
        envelope = _envelope(text="hello")
        await dispatch_inbound("acct-test", envelope, factory=factory)

        session = await self._list_first_session()
        history = decode_messages(session.messages)
        assert all(m.role not in (Role.USER, Role.ASSISTANT) for m in history)

        audit = await self._audit_entries(session.id)
        assert len(audit) == 1
        assert audit[0]["outcome"] == "deny"
        # Empty NeedsPairing.reason → fallback marker "invalid_pairing".
        assert audit[0]["reason"] == "invalid_pairing"

    async def test_deny_outcome_logs_and_returns(self, isolated_db) -> None:
        """``Deny`` outcome: audit logged with the deny reason; the
        dispatcher returns WITHOUT entering the per-session lock — so
        ``agent.step`` does not run and no USER/ASSISTANT messages
        accumulate.
        """
        await _seed_provider_and_agent()
        await _seed_stub_account()
        StubPluginWithResolver.resolve_outcome = Deny(reason="blocked")
        register_for_test("stub", StubPluginWithResolver)

        factory = await _make_factory()
        envelope = _envelope()
        await dispatch_inbound("acct-test", envelope, factory=factory)

        session = await self._list_first_session()
        history = decode_messages(session.messages)
        assert all(m.role not in (Role.USER, Role.ASSISTANT) for m in history)

        audit = await self._audit_entries(session.id)
        assert len(audit) == 1
        assert audit[0]["outcome"] == "deny"
        assert audit[0]["reason"] == "blocked"
        assert audit[0]["peer_id"] == "peer-1"

    async def test_pairing_persistence_survives_fresh_repo_fetch(
        self, isolated_db
    ) -> None:
        """After successful pairing the peer is persisted: a fresh
        :class:`ConnectorAccountRepository` instance built off the same
        DB connection sees ``peer_id`` in ``config['allowlist']['peers']``.

        Mirrors the F4 e2e pattern: rebuild the repo from the existing
        connection (no actual process restart).
        """
        await _seed_provider_and_agent()
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Pairing",
                type="stub",
                config={
                    "pairing": {
                        "code": "X",
                        "issued_at": "2026-05-18T00:00:00+00:00",
                    },
                },
            )
        )
        StubPluginWithResolver.resolve_outcome = NeedsPairing(
            reason="unknown_peer"
        )
        register_for_test("stub", StubPluginWithResolver)

        factory = await _make_factory()
        envelope = _envelope(text="PAIR X hello")
        await dispatch_inbound("acct-test", envelope, factory=factory)

        # Rebuild the repo from the existing connection — simulates a
        # fresh process boot reading the persisted row.
        fresh_repo = ConnectorAccountRepository(conn, encryptor)
        refreshed = await fresh_repo.get("acct-test")
        allowlist = refreshed.config.get("allowlist")
        assert allowlist is not None
        assert "peer-1" in allowlist["peers"]

    async def test_audit_entries_accrue_across_sequential_inbounds(
        self, isolated_db
    ) -> None:
        """Three sequential inbounds → three audit entries, preserved
        in insertion order."""
        await _seed_provider_and_agent()
        await _seed_stub_account()
        StubPluginWithResolver.resolve_outcome = Permit()
        register_for_test("stub", StubPluginWithResolver)

        factory = await _make_factory()
        for text in ("first", "second", "third"):
            await dispatch_inbound("acct-test",
                _envelope(text=text),
                factory=factory,
            )

        session = await self._list_first_session()
        audit = await self._audit_entries(session.id)
        assert len(audit) == 3
        for entry in audit:
            assert entry["outcome"] == "permit"
            assert entry["peer_id"] == "peer-1"
            assert entry["reason"] is None


# ─────────────────────────────────────────────────────────────────
# M10 F7 L5: routing + command-intercept integration
# ─────────────────────────────────────────────────────────────────


class TestF7RoutingIntegration:
    """Coverage for the F7 L5 dispatcher integration: routing engine
    consult + audit-log + system-outbound for no-eligible + command
    parse + intercept (placeholder fall-through pinned for L5).

    Mirrors :class:`TestF6Gating`'s shape — class-level grouping for
    a single feature stripe; per-test stub-state reset is handled by
    the module-level autouse fixtures.

    Helpers:
    - :meth:`_seed_two_agents` — provisions two agents sharing one
      mock provider so the routing engine has at least two candidates
      for the rule-walk / override / first-eligible / ACL-fallback
      branches.
    - :meth:`_routing_entries` — fetches the ``"routing"`` audit list
      off the resolved session's metadata.
    - :meth:`_RecordingFactory` — wraps an :class:`AgentFactory` and
      records every ``factory.create(name)`` call so the dispatcher's
      choice of routed agent can be asserted directly.
    """

    @staticmethod
    async def _seed_two_agents(
        *,
        alpha_acls: dict[str, list[str] | None] | None = None,
        bravo_acls: dict[str, list[str] | None] | None = None,
    ) -> None:
        """Seed two agents (``alpha``, ``bravo``) sharing one mock
        provider; both attached to ``acct-test``.

        Per-agent ACLs accept the inner-dict shape consumed by L2's
        :func:`admits_inbound` (must carry the ``"peers"`` and
        ``"channels"`` keys when provided).
        """
        await _seed_provider_and_agent(
            agent_name="alpha",
            provider_id="mock-provider",
            connector_account_ids=["acct-test"],
        )
        # Second agent reuses the same provider row — direct
        # ``agent_store.save`` avoids the duplicate-provider-row insert
        # that calling ``_seed_provider_and_agent`` twice would attempt.
        from the_one.agent.config import AgentConfig
        from the_one.db.repositories import SQLiteAgentStore

        conn = await get_connection()
        agent_store = SQLiteAgentStore(conn)
        await agent_store.save(
            AgentConfig(
                name="bravo",
                provider_config_id="mock-provider",
                llm_model="mock-default",
                connector_account_ids=["acct-test"],
                connector_acls=(
                    {"acct-test": bravo_acls} if bravo_acls is not None else None
                ),
            )
        )
        if alpha_acls is not None:
            # Re-save alpha with the requested ACL — :meth:`save` is
            # ``INSERT … ON CONFLICT UPDATE`` so it doubles as an update.
            await agent_store.save(
                AgentConfig(
                    name="alpha",
                    provider_config_id="mock-provider",
                    llm_model="mock-default",
                    connector_account_ids=["acct-test"],
                    connector_acls={"acct-test": alpha_acls},
                )
            )

    @staticmethod
    async def _routing_entries(session_id: str) -> list[dict[str, Any]]:
        """Helper: fetch the ``routing`` audit list from session metadata."""
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        session = await chat_repo.get(session_id)
        if session.session_metadata is None:
            return []
        return session.session_metadata.get("routing", [])

    @staticmethod
    async def _first_session_id() -> str:
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        sessions = await chat_repo.list()
        assert len(sessions) == 1
        return sessions[0].id

    class _RecordingFactory:
        """Wraps an :class:`AgentFactory` and records every
        ``create(name)`` call so tests can assert which agent was built.

        Implements the same ``async def create(name)`` shape as
        :class:`AgentFactory` — the dispatcher only calls ``.create``
        on the factory, so structural compat is sufficient.
        """

        def __init__(self, inner: AgentFactory) -> None:
            self._inner = inner
            self.created_with: list[str] = []

        async def create(self, name: str = "default"):
            self.created_with.append(name)
            return await self._inner.create(name)

    # ── Routing-match ─────────────────────────────────────────────────

    async def test_dispatch_inbound_routes_to_agent_per_rule_match(
        self, isolated_db
    ) -> None:
        """Routing engine's rule-walk step 2 picks ``bravo`` on ch-1
        when the rules list pins that scope-match. The audit-log entry
        records the rule index, scope, match, and ``reason=rule-match``."""
        await self._seed_two_agents()
        # Account with routing rules: ch-1 → bravo.
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Routing",
                type="stub",
                config={
                    "routing": {
                        "rules": [
                            {"scope": "channel", "match": ["ch-1"], "agent": "bravo"},
                        ],
                        "default": None,
                    },
                },
            )
        )
        register_for_test("stub", StubPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        envelope = _envelope()
        await dispatch_inbound("acct-test", envelope, factory=factory)

        # The dispatcher built bravo, not alpha (alphabetically-first).
        assert factory.created_with == ["bravo"]

        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["agent"] == "bravo"
        assert entry["rule_index"] == 0
        assert entry["scope"] == "channel"
        assert entry["match"] == "ch-1"
        assert entry["reason"] == "rule-match"
        assert entry["disposition"] == "stepped"
        assert "ts" in entry

    # ── Override ──────────────────────────────────────────────────────

    async def test_dispatch_inbound_routing_override_short_circuits_rule_walk(
        self, isolated_db
    ) -> None:
        """A pre-seeded ``session_metadata["routing_override"] = "alpha"``
        wins over a rule that would otherwise pick ``bravo``. Audit
        reason is ``"override"``; the override is consumed via the new
        :meth:`ChatSessionRepository.set_session_metadata_key` primitive."""
        await self._seed_two_agents()
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Routing",
                type="stub",
                config={
                    "routing": {
                        "rules": [
                            {"scope": "channel", "match": ["ch-1"], "agent": "bravo"},
                        ],
                        "default": None,
                    },
                },
            )
        )
        register_for_test("stub", StubPlugin)

        # Warmup dispatch materialises the session row so the override
        # write target exists; warmup intentionally routes by rule
        # (no override yet) — produces ONE prior routing audit entry
        # we filter on in the assertion.
        inner = await _make_factory()
        warmup_factory = self._RecordingFactory(inner)
        await dispatch_inbound(
            "acct-test", _envelope(text="warmup"), factory=warmup_factory
        )
        session_id = await self._first_session_id()

        # Write the override via the new primitive — this is the path
        # F7 L6's ``/talk-to`` handler will exercise.
        chat_repo = ChatSessionRepository(conn)
        await chat_repo.set_session_metadata_key(
            session_id, "routing_override", "alpha"
        )

        # Second inbound — the override should now drive routing.
        factory = self._RecordingFactory(inner)
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        assert factory.created_with == ["alpha"]

        routing = await self._routing_entries(session_id)
        # Two entries: warmup (rule-match) + override-driven.
        assert len(routing) == 2
        override_entry = routing[-1]
        assert override_entry["agent"] == "alpha"
        assert override_entry["reason"] == "override"
        assert override_entry["disposition"] == "stepped"

    # ── Default fallback ─────────────────────────────────────────────

    async def test_dispatch_inbound_falls_back_to_default_when_no_rule_matches(
        self, isolated_db
    ) -> None:
        """No rules / no override / per-account default = ``alpha`` →
        routing step 3 picks ``alpha``. Audit ``reason="default"``."""
        await self._seed_two_agents()
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Routing",
                type="stub",
                config={"routing": {"rules": [], "default": "alpha"}},
            )
        )
        register_for_test("stub", StubPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        assert factory.created_with == ["alpha"]

        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["agent"] == "alpha"
        assert entry["reason"] == "default"
        assert entry["scope"] == "default"
        assert entry["rule_index"] is None
        assert entry["match"] is None
        assert entry["disposition"] == "stepped"

    # ── First-eligible-alphabetical fallback ─────────────────────────

    async def test_dispatch_inbound_falls_back_to_first_eligible_when_no_default(
        self, isolated_db
    ) -> None:
        """No rules, no default, two eligible agents → routing step 4
        picks ``alpha`` (alphabetically-first). Audit ``reason=
        "first-eligible"``."""
        await self._seed_two_agents()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        assert factory.created_with == ["alpha"]

        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["agent"] == "alpha"
        assert entry["reason"] == "first-eligible"
        assert entry["disposition"] == "stepped"

    # ── No-eligible (peer-error via system-outbound) ─────────────────

    async def test_dispatch_inbound_no_eligible_emits_peer_error_via_system_outbound(
        self, isolated_db
    ) -> None:
        """One attached agent with an ACL that denies the peer → routing
        engine returns ``decision.agent=None`` → dispatcher emits the
        peer-facing "No agents available for this conversation." via
        the system-outbound path (``account_acquire → client.send``).
        ``agent.step`` does NOT run."""
        # Single agent with peers ACL that denies the peer.
        await _seed_provider_and_agent(
            agent_name="alpha", connector_account_ids=["acct-test"]
        )
        # Update alpha with the denying ACL.
        conn = await get_connection()
        from the_one.agent.config import AgentConfig
        from the_one.db.repositories import SQLiteAgentStore

        agent_store = SQLiteAgentStore(conn)
        await agent_store.save(
            AgentConfig(
                name="alpha",
                provider_config_id="mock-provider",
                llm_model="mock-default",
                connector_account_ids=["acct-test"],
                connector_acls={
                    "acct-test": {"peers": [], "channels": None}
                },
            )
        )
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        # agent.step never ran — no AgentFactory.create call.
        assert factory.created_with == []

        # System-outbound emitted exactly one peer-facing error.
        assert len(StubPlugin.outbound_records) == 1
        target, content = StubPlugin.outbound_records[0]
        assert target.channel_id == "ch-1"
        assert target.thread_id is None
        assert content == "No agents available for this conversation."

        # Routing audit entry pins the no-eligible disposition.
        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["agent"] is None
        assert entry["reason"] == "no-eligible-agent"
        assert entry["disposition"] == "no-eligible"

    # ── No-attached-agents (silent return; no audit entry) ───────────

    async def test_dispatch_inbound_no_attached_agents_silent_return_no_peer_error(
        self, isolated_db
    ) -> None:
        """Agent attached to NO accounts → step 4 returns empty list →
        silent return BEFORE ``resolve_session``: no exception, no
        peer-facing error, no chat_sessions row, no routing audit.
        Preserves L3's silent-ignore semantic."""
        await _seed_provider_and_agent(
            agent_name="alpha", connector_account_ids=[]
        )
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        # Must not raise.
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        assert factory.created_with == []
        assert StubPlugin.outbound_records == []

        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        sessions = await chat_repo.list()
        assert len(sessions) == 0

    # ── Command intercept (L6 wired) ─────────────────────────────────

    async def test_dispatch_inbound_command_text_intercepted_after_L6(
        self, isolated_db
    ) -> None:
        """M10 F7 L6: ``/agents`` is now intercepted by
        :func:`_dispatch_builtin_command` — the L5 placeholder is
        replaced with the six v1 handler implementations. The
        dispatcher emits the command response via the system-outbound
        path (captured by :attr:`StubPlugin.outbound_records`); audit
        ``disposition="command-intercepted"``; ``agent.step`` does NOT
        run.

        Rewrite of the L5-pinned
        ``test_dispatch_inbound_command_text_falls_through_to_agent_step_in_L5``
        — the L5 test asserted the placeholder semantic (fall-through);
        L6's leg rewrites it to the post-L6 semantic (intercept).
        """
        await _seed_provider_and_agent(
            agent_name="alpha", connector_account_ids=["acct-test"]
        )
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        envelope = _envelope(text="/agents")
        await dispatch_inbound("acct-test", envelope, factory=factory)

        # agent.step did NOT run — the command was intercepted before
        # the per-session lock + step.
        assert factory.created_with == []

        # The session row's messages stayed empty (no user message
        # persisted, no assistant reply).
        session_id = await self._first_session_id()
        conn = await get_connection()
        chat_repo = ChatSessionRepository(conn)
        session = await chat_repo.get(session_id)
        history = decode_messages(session.messages)
        assert history == []

        # System-outbound captured the /agents response text.
        assert len(StubPlugin.outbound_records) == 1
        target, content = StubPlugin.outbound_records[0]
        assert target.channel_id == envelope.channel_id
        assert target.thread_id == envelope.thread_id
        # The response lists the alphabetically-first attached agent.
        assert content == (
            "Agents available to you on this account:\n- alpha"
        )

        # Audit-log entry records the intercept disposition.
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        assert routing[0]["disposition"] == "command-intercepted"
        assert routing[0]["agent"] == "alpha"

    # ── Pool-failure-overload (routed agent, post-routing) ───────────

    async def test_dispatch_inbound_pool_failure_at_step_10_logs_no_eligible_disposition(
        self, isolated_db, monkeypatch
    ) -> None:
        """Routing picks ``alpha`` via first-eligible-alphabetical, but
        ``account_acquire(…)`` raises ``ConnectorRegistrationError``
        → dispatcher returns; audit entry carries the routing
        ``reason="first-eligible"`` AND the overloaded ``disposition=
        "no-eligible"`` (pool-failure-overload). Pins the documented
        overload behaviour so a future refactor doesn't silently flip
        it.

        Pool key is ``(_ACCOUNT_POOL_AGENT_SLOT, account_id)`` (M11 F2 L2;
        formerly the F8 L11 sentinel-wrapper retrofit) not
        ``(agent_name, account_id)`` — the test monkeypatches
        ``account_acquire`` on the inbound module instead of the bare
        ``agent_acquire``.
        """
        await _seed_provider_and_agent(
            agent_name="alpha", connector_account_ids=["acct-test"]
        )
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        # Monkeypatch the account_acquire used INSIDE _inbound to raise.
        from the_one.connectors import _inbound as inbound_mod_local
        from the_one.connectors.errors import ConnectorRegistrationError

        async def _raising_account_acquire(account_id: str):
            raise ConnectorRegistrationError(
                f"forced for account={account_id}"
            )

        monkeypatch.setattr(
            inbound_mod_local, "account_acquire", _raising_account_acquire
        )

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        # agent.step never ran — pool failed before the lock + step.
        assert factory.created_with == []

        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        # The routing decision itself was first-eligible — that's what
        # the audit log preserves; the disposition overload tells the
        # operator the inbound went unanswered because the pool failed.
        assert entry["agent"] == "alpha"
        assert entry["reason"] == "first-eligible"
        assert entry["disposition"] == "no-eligible"

    # ── No-eligible emit failure swallowed ───────────────────────────

    async def test_dispatch_inbound_no_eligible_system_outbound_emit_failure_is_swallowed(
        self, isolated_db
    ) -> None:
        """``client.send`` raising during the no-eligible peer-error
        emission is logged + swallowed; the dispatcher returns cleanly
        and the audit entry still records ``disposition="no-eligible"``.
        Pins the swallow-and-log contract."""
        await _seed_provider_and_agent(
            agent_name="alpha", connector_account_ids=["acct-test"]
        )
        # Update alpha to deny the peer so routing returns
        # decision.agent=None.
        conn = await get_connection()
        from the_one.agent.config import AgentConfig
        from the_one.db.repositories import SQLiteAgentStore

        agent_store = SQLiteAgentStore(conn)
        await agent_store.save(
            AgentConfig(
                name="alpha",
                provider_config_id="mock-provider",
                llm_model="mock-default",
                connector_account_ids=["acct-test"],
                connector_acls={
                    "acct-test": {"peers": [], "channels": None}
                },
            )
        )
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)
        # Configure the stub's send to raise.
        StubPlugin.send_should_raise = ConnectorConnectionError(
            "emit failed"
        )

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        # Must NOT raise.
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        # agent.step never ran; no outbound recorded (send raised
        # before the record_outbound call); audit still pinned.
        assert factory.created_with == []
        assert StubPlugin.outbound_records == []

        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["agent"] is None
        assert entry["reason"] == "no-eligible-agent"
        assert entry["disposition"] == "no-eligible"

    # ── ACL-denied routed agent falls back to next eligible ──────────

    async def test_dispatch_inbound_acl_denied_routed_agent_falls_back_to_next_eligible(
        self, isolated_db
    ) -> None:
        """Two attached agents (``alpha``, ``bravo``). ``alpha``'s ACL
        denies the peer; routing engine's step 4
        (first-eligible-alphabetical) walks past ``alpha``, picks
        ``bravo``. ``agent.step`` runs on ``bravo``; audit ``reason=
        "first-eligible"``, ``agent="bravo"``.

        The engine's ACL admission check on step 4 is exercised end-
        to-end through the dispatcher — the L5 dispatcher does NOT
        re-check ACL on the engine's output (the engine already did)."""
        await self._seed_two_agents(
            alpha_acls={"peers": [], "channels": None}
        )
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        assert factory.created_with == ["bravo"]

        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["agent"] == "bravo"
        assert entry["reason"] == "first-eligible"
        assert entry["disposition"] == "stepped"

    # ── M10 F8 L1 — CommandHandler plugin-consult ────────────────────

    async def test_dispatch_inbound_plugin_handle_command_intercepts_before_builtin(
        self, isolated_db, monkeypatch
    ) -> None:
        """M10 F8 L1: the dispatcher's step-11 plugin-consult sub-step
        runs BEFORE ``_dispatch_builtin_command``. When the plugin's
        ``handle_command`` returns a non-None :class:`CommandResponse`,
        the dispatcher emits it via the system-outbound path, audit-
        logs ``disposition="command-intercepted"`` + ``intercept_source=
        "plugin"``, and short-circuits the built-in handler.

        Asserts: (i) plugin response emitted via outbound;
        (ii) ``_dispatch_builtin_command`` was NOT invoked;
        (iii) audit-log carries the plugin intercept-source key.
        """
        from the_one.connectors.base import CommandResponse

        await _seed_provider_and_agent(
            agent_name="alpha", connector_account_ids=["acct-test"]
        )
        await _seed_stub_account()

        class _CommandHandlingStub(StubPlugin):
            """Stub variant adding the ``handle_command`` hook."""

            handle_command_calls: list[tuple[str, list[str]]] = []

            async def handle_command(
                self, envelope, command_name, args
            ):
                _CommandHandlingStub.handle_command_calls.append(
                    (command_name, list(args))
                )
                return CommandResponse(text="plugin-intercepted-response")

        register_for_test("stub", _CommandHandlingStub)

        # Spy on the built-in dispatcher to assert it was NOT called.
        from the_one.connectors import _inbound as inbound_mod_local
        builtin_calls: list[tuple[str, list[str]]] = []

        async def _spy_builtin(command_name, args, context):
            builtin_calls.append((command_name, list(args)))
            return None

        # The dispatcher imports ``_dispatch_builtin_command`` via a
        # function-local import inside ``dispatch_inbound``. Patch the
        # source module attribute so the dispatcher's function-local
        # import binds to the spy.
        from the_one.connectors import _commands as commands_mod
        monkeypatch.setattr(
            commands_mod, "_dispatch_builtin_command", _spy_builtin
        )

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        envelope = _envelope(text="/agents")
        await dispatch_inbound("acct-test", envelope, factory=factory)

        # agent.step did NOT run — the command was intercepted by the
        # plugin's handle_command at step 11 before the per-session
        # lock + step.
        assert factory.created_with == []

        # Plugin's handle_command was consulted with the right command.
        assert _CommandHandlingStub.handle_command_calls == [
            ("agents", [])
        ]

        # The built-in handler was NEVER invoked — the plugin's non-
        # None response short-circuited the dispatcher.
        assert builtin_calls == []

        # System-outbound captured the plugin's response text.
        assert len(StubPlugin.outbound_records) == 1
        target, content = StubPlugin.outbound_records[0]
        assert target.channel_id == envelope.channel_id
        assert target.thread_id == envelope.thread_id
        assert content == "plugin-intercepted-response"

        # Audit-log entry records the plugin intercept-source key.
        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["disposition"] == "command-intercepted"
        assert entry["intercept_source"] == "plugin"
        assert entry["agent"] == "alpha"

    async def test_dispatch_inbound_plugin_handle_command_returning_none_falls_through_to_builtin(
        self, isolated_db
    ) -> None:
        """M10 F8 L1: when the plugin's ``handle_command`` returns
        ``None``, the dispatcher falls through to the built-in handler.
        The built-in's response emits with ``intercept_source=
        "builtin"`` — sibling discriminator to the plugin path.

        Asserts: (i) plugin's ``handle_command`` was consulted but
        returned ``None``; (ii) the built-in handler ran and produced
        the ``/agents`` response (the alphabetically-first attached
        agent's slug); (iii) audit-log carries ``intercept_source=
        "builtin"``.
        """
        await _seed_provider_and_agent(
            agent_name="alpha", connector_account_ids=["acct-test"]
        )
        await _seed_stub_account()

        class _NoneReturningPlugin(StubPlugin):
            """Stub variant whose ``handle_command`` returns ``None``."""

            handle_command_calls: list[tuple[str, list[str]]] = []

            async def handle_command(
                self, envelope, command_name, args
            ):
                _NoneReturningPlugin.handle_command_calls.append(
                    (command_name, list(args))
                )
                return None

        register_for_test("stub", _NoneReturningPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)
        envelope = _envelope(text="/agents")
        await dispatch_inbound("acct-test", envelope, factory=factory)

        # agent.step did NOT run — the built-in handler short-
        # circuited after the plugin returned None.
        assert factory.created_with == []

        # Plugin's handle_command was consulted.
        assert _NoneReturningPlugin.handle_command_calls == [
            ("agents", [])
        ]

        # The built-in /agents handler ran and produced its standard
        # response.
        assert len(StubPlugin.outbound_records) == 1
        _, content = StubPlugin.outbound_records[0]
        assert content == (
            "Agents available to you on this account:\n- alpha"
        )

        # Audit-log entry records the builtin intercept-source key.
        session_id = await self._first_session_id()
        routing = await self._routing_entries(session_id)
        assert len(routing) == 1
        entry = routing[0]
        assert entry["disposition"] == "command-intercepted"
        assert entry["intercept_source"] == "builtin"
        assert entry["agent"] == "alpha"

    # ── M10 F8 L11 HAT Fix #6 — multi-agent connector-account sharing ──

    async def test_multi_agent_routing_shares_pool_entry(
        self, isolated_db
    ) -> None:
        """Multi-agent routing on a single connector account uses ONE
        pool entry — the account-shared sentinel keying.

        Background: pre-Fix-#6 the pool keyed on
        ``(agent_name, account_id)``, so two agents attached to the
        same Discord bot spawned two ``plugin.connect`` calls and two
        gateway WebSockets with the SAME bot token. Discord rejects
        the second IDENTIFY on a duplicate token, breaking multi-
        agent routing on a single connector account at the structural
        level.

        Post-Fix-#6: every connector-side caller routes through
        :func:`account_acquire` which keys on the
        ``_ACCOUNT_POOL_AGENT_SLOT`` instead of the routed
        agent's name. This test attaches TWO agents to one account,
        drives routing through each in turn (rule-match then alpha-
        fallback on a separate channel), and asserts that the pool
        ends up with EXACTLY ONE entry for that account.
        """
        await self._seed_two_agents()
        # Account with a rule that pins ch-1 → bravo; ch-2 falls back
        # to first-eligible-alphabetical (alpha).
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Routing",
                type="stub",
                config={
                    "routing": {
                        "rules": [
                            {"scope": "channel", "match": ["ch-1"], "agent": "bravo"},
                        ],
                        "default": None,
                    },
                },
            )
        )
        register_for_test("stub", StubPlugin)

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)

        # First inbound: ch-1 routes to bravo (rule-match).
        await dispatch_inbound(
            "acct-test", _envelope(channel_id="ch-1"), factory=factory
        )
        # Second inbound: ch-2 falls back to alpha (alphabetical).
        await dispatch_inbound(
            "acct-test", _envelope(channel_id="ch-2"), factory=factory
        )

        # Both agents were exercised through the routing layer.
        assert set(factory.created_with) == {"alpha", "bravo"}

        # Pool has exactly ONE entry for the account, keyed on the
        # connector sentinel — NOT one per (agent, account).
        keys_for_account = [
            k for k in pool_mod._pool if k[1] == "acct-test"
        ]
        assert len(keys_for_account) == 1, keys_for_account
        assert keys_for_account[0] == (
            pool_mod._ACCOUNT_POOL_AGENT_SLOT,
            "acct-test",
        )

    async def test_multi_agent_routing_single_plugin_connect_call(
        self, isolated_db
    ) -> None:
        """M10 F8 L11 HAT Fix #6: regardless of how many agents route
        through one connector account, the plugin's ``connect`` is
        called exactly ONCE for that account.

        This is the load-bearing invariant for Discord (and any other
        gateway-style protocol): one IDENTIFY frame per bot token.
        """
        await self._seed_two_agents()
        # No rules → both channels fall back to first-eligible (alpha)
        # unless we override per-channel. Use a rule to drive bravo on
        # ch-1 so both agents are actually exercised.
        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        acc_repo = ConnectorAccountRepository(conn, encryptor)
        await acc_repo.create(
            ConnectorAccount(
                id="acct-test",
                name="Stub Routing",
                type="stub",
                config={
                    "routing": {
                        "rules": [
                            {"scope": "channel", "match": ["ch-1"], "agent": "bravo"},
                            {"scope": "channel", "match": ["ch-2"], "agent": "alpha"},
                        ],
                        "default": None,
                    },
                },
            )
        )
        register_for_test("stub", StubPlugin)

        # StubPlugin.connect_calls is a ClassVar list that the autouse
        # ``_reset_stub_state`` fixture clears between tests.
        assert StubPlugin.connect_calls == []

        inner = await _make_factory()
        factory = self._RecordingFactory(inner)

        # Drive two inbounds; each routes to a different agent.
        await dispatch_inbound(
            "acct-test", _envelope(channel_id="ch-1"), factory=factory
        )
        await dispatch_inbound(
            "acct-test", _envelope(channel_id="ch-2"), factory=factory
        )

        # Both agents stepped — routing fired for both.
        assert set(factory.created_with) == {"alpha", "bravo"}

        # plugin.connect was called exactly ONCE for the account.
        # The second routing dispatch reuses the warm pool entry.
        assert StubPlugin.connect_calls == [("acct-test", "stub")]

    async def test_dispatch_inbound_pool_key_uses_connector_sentinel(
        self, isolated_db
    ) -> None:
        """Single-agent regression: even with one attached agent, the
        pool entry keys on ``_ACCOUNT_POOL_AGENT_SLOT`` — not on
        the routed agent's name. Pins the keying invariant so a
        future refactor cannot silently fall back to the bare
        ``acquire(agent_name, account_id)`` shape that pre-Fix-#6
        broke multi-agent routing on a single bot token.
        """
        await _seed_provider_and_agent()
        await _seed_stub_account()
        register_for_test("stub", StubPlugin)

        factory = await _make_factory()
        await dispatch_inbound("acct-test", _envelope(), factory=factory)

        # The agent's name does NOT appear in the pool keys.
        agent_keyed = [
            k for k in pool_mod._pool
            if k[0] != pool_mod._ACCOUNT_POOL_AGENT_SLOT
            and k[1] == "acct-test"
        ]
        assert agent_keyed == [], agent_keyed
        # The sentinel-keyed entry exists.
        assert (
            pool_mod._ACCOUNT_POOL_AGENT_SLOT,
            "acct-test",
        ) in pool_mod._pool
