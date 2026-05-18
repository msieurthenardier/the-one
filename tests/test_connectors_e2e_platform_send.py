"""End-to-end tests for M10 F4 — platform-send tool + outbound routing.

Pins the mission's two state-machine invariants end-to-end:

- Mission criterion #13 (enabled state): when the platform-send tool is
  operator-enabled, an inbound peer message that drives the agent to
  call ``send_to_platform_channel`` produces a real outbound delivery,
  the tool_result is tagged ``visibility=None`` (peer-visible), and the
  assistant message that requested the tool call is tagged
  ``visibility=OPERATOR_VISIBILITY``.
- Mission criterion #14 (disabled state): when the platform-send tool
  is operator-disabled, an inbound peer message produces NO outbound
  delivery, the inbound user message persists with ``visibility=None``,
  the agent's assistant reply persists with ``visibility=OPERATOR_VISIBILITY``,
  and the agent's loaded-schemas set does NOT include
  ``send_to_platform_channel``.

Plus three regression nets the F4 flight mandated:

- ``test_e2e_target_validation_rejects_unattached_account`` (criterion
  #15): the platform-send tool's account-scope check rejects targets
  whose ``account_id`` is not in the agent's attached set.
- ``test_e2e_pool_acquire_touches_last_activity_on_outbound``: the F3
  ratification's ``last_activity`` touch is the F1 anchor; F3's inbound
  path verified this; F4's outbound path needs its own verification.
- ``test_e2e_plugin_resolve_failure_dispatcher_logs_and_returns``: the
  dispatcher's "deliberately redundant" plugin-resolve catch at
  ``_inbound.py:143-152`` is the F1 debrief carry-forward — the catch
  is dead in the happy path but the regression net pins reachability
  so a future pool refactor that changes the error surface doesn't
  strand the dispatcher with an unhandled unknown-type path.

Helpers (``isolated_db``, ``_seed_provider_and_agent``, ``_seed_stub_account``,
``_make_factory``, ``_envelope``, ``_ScriptedProvider``,
``_make_scripted_factory``) live in
``tests/_connector_dispatch_helpers`` — extracted by F4 L5 once this
file became the THIRD consumer (per F3 debrief).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from tests._connector_dispatch_helpers import (
    _envelope,
    _make_factory,
    _make_scripted_factory,
    _seed_provider_and_agent,
    _seed_stub_account,
)
from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
from the_one.connectors import _inbound as inbound_mod
from the_one.connectors import _pool as pool_mod
from the_one.connectors._inbound import dispatch_inbound
from the_one.connectors._stub import StubPlugin
from the_one.connectors.errors import ConnectorRegistrationError
from the_one.connectors.registry import clear_for_test as _registry_clear_for_test
from the_one.connectors.registry import register_for_test, restore_to_baseline_for_test
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.repositories import ChatSessionRepository, ToolConfigRepository
from the_one.llm.base import Message, Role, ToolCall
from the_one.sessions import clear_for_test as _clear_session_registry

# ─── Autouse cleanup ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset StubPlugin class-level recording buffers around each test."""
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_locks_registry():
    """Empty pool + per-session lock dict + registry between tests.

    Mirrors the autouse cleanup at ``tests/test_connectors_inbound.py``.
    """
    yield
    await pool_mod._clear_for_test()
    await inbound_mod._clear_for_test()
    # F5 L2: also clear the neutral session registries (shared lock +
    # subscribers).
    _clear_session_registry()
    _registry_clear_for_test()
    restore_to_baseline_for_test()


# ─── Test 1 — enabled state delivers (mission criterion #13) ─────────────


async def test_e2e_enabled_state_platform_send_delivers(
    isolated_db, monkeypatch
) -> None:
    """When the platform-send tool is operator-enabled and the agent is
    connector-attached, an inbound that drives the agent to call
    ``send_to_platform_channel`` delivers content to the platform.

    Asserts the full enabled-state contract:
    - ``StubPlugin.outbound_records`` contains exactly the expected target +
      content pair.
    - The assistant tool_call message has ``visibility=OPERATOR_VISIBILITY``.
    - The successful platform-send tool_result has ``visibility=None``.
    - The agent's loaded schemas (factory-time snapshot) include
      ``send_to_platform_channel`` (F4 L3 carve-out fired).
    - The agent's system prompt contains the enabled-tool directive.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    # Iter 1: tool_call for platform-send. Iter 2: plain-text end.
    tc = ToolCall(
        id="tc-send-1",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "c1"},
            "content": "hello peer",
        },
    )
    responses = [
        Message.assistant(content="", tool_calls=[tc]),
        Message.assistant(content="done"),
    ]
    factory = await _make_scripted_factory(responses, monkeypatch)

    # Sanity check the agent's loaded schemas + system prompt BEFORE
    # dispatch — this exercises the same factory.create the dispatcher
    # invokes per turn, so it's representative.
    agent = await factory.create("agent-inbound")
    schema_names = {s["name"] for s in agent._loaded_schemas}
    assert "send_to_platform_channel" in schema_names, schema_names
    assert "send_to_platform_channel" in agent.system_prompt or (
        "`send_to_platform_channel` tool" in agent.system_prompt
    )

    envelope = _envelope(channel_id="c1")
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    # Outbound recorded with the expected target + content.
    assert len(StubPlugin.outbound_records) == 1
    target, content = StubPlugin.outbound_records[0]
    assert target.channel_id == "c1"
    assert target.thread_id is None
    assert content == "hello peer"

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    history = decode_messages(sessions[0].messages)

    # Assistant tool_call message → OPERATOR_VISIBILITY.
    assistant_with_call = [
        m for m in history if m.role == Role.ASSISTANT and m.tool_calls
    ]
    assert assistant_with_call
    for m in assistant_with_call:
        assert m.visibility == OPERATOR_VISIBILITY

    # Successful platform-send tool_result → visibility=None.
    tool_msgs = [m for m in history if m.role == Role.TOOL]
    send_results = [
        m
        for m in tool_msgs
        if m.tool_result is not None
        and m.content.startswith(PLATFORM_SEND_OK_PREFIX)
    ]
    assert send_results, "expected a successful platform-send tool_result"
    for m in send_results:
        assert m.visibility is None


# ─── Test 2 — disabled state: inbound received, no outbound (criterion #14) ─


async def test_e2e_disabled_state_inbound_received_no_outbound(
    isolated_db, monkeypatch
) -> None:
    """When the platform-send tool is operator-DISABLED but the agent is
    connector-attached, the inbound flow stays intact (the user message
    persists peer-visible; the assistant reply persists operator-only),
    but NO outbound delivery occurs and the tool is absent from the
    agent's loaded schemas.

    The agent's system prompt carries the DISABLED-tool directive so
    the model is informed that its replies stay local.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    # Operator-disable the tool before dispatch.
    conn = await get_connection()
    tool_repo = ToolConfigRepository(conn)
    # Note (reviewer-surfaced footgun): upsert's ON CONFLICT writes
    # config=excluded.config, so passing config={} on a re-enable would
    # overwrite any pre-existing config dict to empty. For
    # send_to_platform_channel there is no operator-tunable config
    # (Config is _EmptyConfig), so config={} is safe — but a future
    # flight that adds a real config payload must read the existing
    # config first and pass it back.
    await tool_repo.upsert(name="send_to_platform_channel", config={}, enabled=False)

    # Tool is disabled — the scripted provider returns plain text only.
    # If a tool_call were emitted, the agent's tool registry would not
    # find the tool (the factory filters it out at registry-build time).
    responses = [Message.assistant(content="silent assistant reply")]
    factory = await _make_scripted_factory(responses, monkeypatch)

    # Sanity check: the agent's loaded schemas do NOT include the tool;
    # the system prompt contains the DISABLED-tool directive substring.
    agent = await factory.create("agent-inbound")
    schema_names = {s["name"] for s in agent._loaded_schemas}
    assert "send_to_platform_channel" not in schema_names, schema_names
    # The DISABLED directive contains a stable substring.
    assert "platform-send capability is currently DISABLED" in agent.system_prompt

    envelope = _envelope()
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    # No outbound delivery occurred.
    assert StubPlugin.outbound_records == []

    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    history = decode_messages(sessions[0].messages)

    # Inbound USER message persisted with visibility=None (peer-visible).
    user_msgs = [m for m in history if m.role == Role.USER]
    assert user_msgs
    for m in user_msgs:
        assert m.visibility is None

    # Assistant reply persisted with OPERATOR_VISIBILITY.
    assistant_msgs = [m for m in history if m.role == Role.ASSISTANT]
    assert assistant_msgs
    for m in assistant_msgs:
        assert m.visibility == OPERATOR_VISIBILITY


# ─── Test 3 — re-enable restores outbound mid-test (criterion #14) ───────


async def test_e2e_disabled_to_enabled_re_dispatch_restores_outbound(
    isolated_db, monkeypatch
) -> None:
    """Mission criterion #14 final clause: re-enabling the operator
    switch restores outbound without re-configuring the connector
    account or restarting any session.

    Sequence:
    1. Operator-disable the tool, dispatch first inbound → zero outbound.
    2. Flip the operator switch via ``ToolConfigRepository.upsert(...,
       enabled=True)``.
    3. Dispatch a SECOND inbound: ``factory.create`` rebuilds the agent
       (per F3 L4 dispatcher contract), the carve-out now fires, the
       agent calls the tool, ``outbound_records`` captures the delivery.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    conn = await get_connection()
    tool_repo = ToolConfigRepository(conn)
    await tool_repo.upsert(name="send_to_platform_channel", config={}, enabled=False)

    # First dispatch: tool is disabled, plain-text reply only. Use a
    # factory that yields plain text.
    first_factory = await _make_scripted_factory(
        [Message.assistant(content="cannot reach platform")], monkeypatch
    )

    envelope = _envelope(channel_id="c1")
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=first_factory)
    assert StubPlugin.outbound_records == []

    # Operator flips the switch mid-session (NO restart of the
    # StubPlugin, NO re-seeding of the account, NO monkey-patching the
    # tool's enabled state — just the operator config row).
    await tool_repo.upsert(name="send_to_platform_channel", config={}, enabled=True)

    # Second dispatch — build a fresh scripted factory whose provider
    # emits a tool_call (separate factory needed because the scripted
    # provider's response index is per-instance and each
    # ``factory.create()`` builds a fresh provider; the monkeypatch on
    # ``get_provider`` is rebound by the new factory). The dispatcher's
    # call to ``factory.create()`` re-reads the agent + ToolConfig rows,
    # so the carve-out fires and the tool is back in the registry.
    tc = ToolCall(
        id="tc-send-re",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "c1"},
            "content": "now I can reach peers",
        },
    )
    second_factory = await _make_scripted_factory(
        [
            Message.assistant(content="", tool_calls=[tc]),
            Message.assistant(content="reply delivered"),
        ],
        monkeypatch,
    )

    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=second_factory)

    assert len(StubPlugin.outbound_records) == 1
    target, content = StubPlugin.outbound_records[0]
    assert target.channel_id == "c1"
    assert content == "now I can reach peers"


# ─── Test 4 — target-validation rejects unattached account (criterion #15) ─


async def test_e2e_target_validation_rejects_unattached_account(
    isolated_db, monkeypatch
) -> None:
    """The platform-send tool's account-scope check rejects targets
    whose ``account_id`` is not in the agent's attached set.

    Asserts:
    - The tool_result content starts with the constraint envelope.
    - NO pool acquire was attempted on the wrong account (pool_acquire
      patched to count calls per account_id).
    - ``StubPlugin.outbound_records`` does NOT contain the failed
      delivery.
    """
    # Agent attached to acct-A only.
    await _seed_provider_and_agent(connector_account_ids=["acct-A"])
    await _seed_stub_account("acct-A")
    await _seed_stub_account("acct-B")
    register_for_test("stub", StubPlugin)

    # The agent will try to send to acct-B (not in its attached set).
    tc = ToolCall(
        id="tc-send-wrong",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-B", "channel_id": "c1"},
            "content": "should be rejected",
        },
    )
    responses = [
        Message.assistant(content="", tool_calls=[tc]),
        Message.assistant(content="done"),
    ]
    factory = await _make_scripted_factory(responses, monkeypatch)

    # Wrap pool_acquire to count per-(agent, account) calls so we can
    # assert the wrong-account target never reached the pool. We patch
    # at the SQLite-tool's module-local binding (`the_one.tools.connector_send.pool_acquire`)
    # since the tool captured the function reference at import time.
    from the_one.tools import connector_send as tool_mod

    acquire_calls: list[tuple[str, str]] = []
    original_acquire = tool_mod.pool_acquire

    async def _counting_acquire(agent_name: str, account_id: str):
        acquire_calls.append((agent_name, account_id))
        return await original_acquire(agent_name, account_id)

    monkeypatch.setattr(tool_mod, "pool_acquire", _counting_acquire)

    envelope = _envelope(account_id="acct-A", channel_id="c1")
    await dispatch_inbound("agent-inbound", "acct-A", envelope, factory=factory)

    # The tool's account-scope short-circuit returns the constraint
    # envelope BEFORE pool_acquire is called.
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    history = decode_messages(sessions[0].messages)
    tool_msgs = [m for m in history if m.role == Role.TOOL]
    assert tool_msgs
    constraint_msgs = [
        m for m in tool_msgs
        if m.content.startswith("[error] [constraint] account_id 'acct-B' is "
                                "not attached to this agent")
    ]
    assert constraint_msgs, [m.content for m in tool_msgs]

    # The wrong account_id never reached the platform-send tool's pool
    # acquire; the dispatcher's own pool acquire fired for acct-A (the
    # inbound's account_id).
    wrong_acquires = [c for c in acquire_calls if c[1] == "acct-B"]
    assert wrong_acquires == [], wrong_acquires

    # No platform delivery happened for the rejected target.
    assert not any(
        c == "should be rejected" for _t, c in StubPlugin.outbound_records
    )


# ─── Test 5 — pool acquire touches last_activity on outbound ─────────────


async def test_e2e_pool_acquire_touches_last_activity_on_outbound(
    isolated_db, monkeypatch
) -> None:
    """The F3 ratification's ``last_activity`` touch is the F1 Known-Issue
    anchor. F3's inbound path verifies it
    (``test_dispatch_inbound_touches_pool_last_activity``); F4's
    outbound path needs its own verification — the platform-send tool's
    ``pool_acquire`` call must touch the same ``_RegistryEntry.last_activity``.

    Asserts ``after > before`` on the pool entry's ``last_activity``
    snapshotted around the second dispatch (the first dispatch warms
    the pool so the entry exists).
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    tc = ToolCall(
        id="tc-send-touch",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "c1"},
            "content": "touch",
        },
    )
    # Two complete turns so we can dispatch twice.
    responses = [
        # Turn 1 — warm the pool via the dispatcher's pool acquire +
        # the tool's pool acquire.
        Message.assistant(content="", tool_calls=[tc]),
        Message.assistant(content="done"),
        # Turn 2 — measure the touch on the outbound path.
        Message.assistant(content="", tool_calls=[tc]),
        Message.assistant(content="done"),
    ]
    factory = await _make_scripted_factory(responses, monkeypatch)

    envelope = _envelope(channel_id="c1")
    # Turn 1: warm the pool.
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)
    key = ("agent-inbound", "acct-test")
    assert key in pool_mod._pool
    before = pool_mod._pool[key].last_activity

    # Ensure monotonic() advances enough to be observable.
    import asyncio

    await asyncio.sleep(0.01)

    # Turn 2: the agent calls the tool, which calls pool_acquire which
    # bumps last_activity.
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)
    after = pool_mod._pool[key].last_activity

    assert after > before


# ─── Test 6 — plugin-resolve failure (F1 debrief carry-forward) ──────────


async def test_e2e_plugin_resolve_failure_dispatcher_logs_and_returns(
    isolated_db, monkeypatch, caplog
) -> None:
    """The dispatcher's "deliberately redundant" plugin-resolve catch at
    ``_inbound.py:143-152`` is dead in the happy path (the pool acquire
    would have already raised on an unknown type). This regression net
    covers the catch by patching the dispatcher's MODULE-LOCAL
    ``registry`` binding (acquired via ``from the_one.connectors import
    ... registry`` at ``_inbound.py:34``) with a fake whose ``resolve``
    raises ``ConnectorRegistrationError``. The pool's
    ``_resolve_plugin`` binding (captured via ``from
    the_one.connectors.registry import resolve as _resolve_plugin`` at
    ``_pool.py:62``) is UNAFFECTED by this patch — so the pool acquire
    succeeds (real plugin resolves) and the dispatcher's
    ``registry.resolve(account.type)`` at ``_inbound.py:140`` hits the
    patched version and raises. This is the intended isolation: the
    catch becomes reachable in a test without compromising the pool.

    Asserts:
    - The function returns cleanly (no exception bubbles up).
    - A WARNING/ERROR log entry mentioning the failed-resolve type was
      emitted (captured via ``caplog``).
    - NO new ``chat_sessions`` row was created — the dispatcher returned
      before reaching session resolution.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    # Build a fake-registry object with a failing resolve. Patch the
    # MODULE-local binding in ``_inbound`` — NOT the registry module's
    # ``resolve`` function. The pool's captured ``_resolve_plugin``
    # reference stays intact so pool_acquire succeeds; only the
    # dispatcher's second resolve hits the patched code.
    def _failing_resolve(connector_type: str):
        raise ConnectorRegistrationError(connector_type, "test failure")

    fake_registry = SimpleNamespace(resolve=_failing_resolve)
    monkeypatch.setattr(inbound_mod, "registry", fake_registry)

    # Capture WARNING and ERROR records from the dispatcher's logger.
    caplog.set_level(logging.WARNING, logger="the_one.connectors._inbound")

    envelope = _envelope()
    # Must NOT raise — the dispatcher's redundant catch swallows the
    # ConnectorRegistrationError and returns.
    await dispatch_inbound("agent-inbound", "acct-test", envelope, factory=factory)

    # A log entry mentioning the failed resolve was emitted.
    resolve_log_records = [
        r for r in caplog.records
        if "unknown connector type" in r.getMessage()
        or "test failure" in r.getMessage()
    ]
    assert resolve_log_records, [r.getMessage() for r in caplog.records]

    # No chat_sessions row was created — the dispatcher returned before
    # the session-resolution step.
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 0


# ─── End ─────────────────────────────────────────────────────────────────


# Silence the unused-import linters for the _ScriptedProvider re-export.
_: Any = None
