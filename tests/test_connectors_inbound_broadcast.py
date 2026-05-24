"""Tests for ``the_one.connectors._inbound``'s F5 L6 broadcast surface.

After ``dispatch_inbound`` persists a connector-driven turn, it projects
the newly-appended messages into UI events and pushes them to live WS
subscribers via :func:`the_one.sessions.broadcast_to_session`. The
broadcast runs INSIDE the per-session lock, AFTER persistence. Zero
subscribers is a clean no-op (existing dispatcher tests at
``tests/test_connectors_inbound.py`` cover that path byte-identically).

This file covers the WITH-subscribers contract:

- Per-message broadcast when subscribed (one event per new Message).
- Zero-subscriber no-op (back-compat pin).
- Visibility carried on broadcast events (with the leg-3 helper's
  send-success carve-out → omitted-``visibility`` contract).
- Broadcast runs AFTER persistence (ordering, deterministic via
  list-mutation).
- Broadcast exception isolation (dead WS doesn't bubble out).
- Multi-turn ``parent_message_id`` non-collision (the codec
  ``index_offset`` regression net).
"""

from __future__ import annotations

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
from the_one.connectors.registry import (
    clear_for_test as _registry_clear_for_test,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.connection import get_connection
from the_one.db.repositories import ChatSessionRepository
from the_one.llm.base import Message, ToolCall
from the_one.sessions import add_subscriber
from the_one.sessions import clear_for_test as _clear_session_registry

# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset StubPlugin class-level recording buffers around each test."""
    StubPlugin.reset_for_test()
    yield
    StubPlugin.reset_for_test()


@pytest.fixture(autouse=True)
async def _clear_pool_locks_registry():
    """Empty pool + per-session lock dict + subscribers + registry
    between tests.

    Mirrors the pattern from ``tests/test_connectors_inbound.py:94`` so
    the neutral session registries (lock + subscriber sets) stay
    isolated test-to-test. Without ``clear_for_test`` here a subscriber
    registered in test N would still be in the registry for test N+1
    and broadcast events would leak across tests.
    """
    yield
    await pool_mod._clear_for_test()
    await inbound_mod._clear_for_test()
    _clear_session_registry()
    _registry_clear_for_test()
    restore_to_baseline_for_test()


# ─── FakeWS — captures payloads passed to send_json ──────────────────────


class _FakeWS:
    """Stand-in for a ``starlette.WebSocket`` with an ``async send_json``.

    Captures every payload the dispatcher emits into ``self.payloads``
    so tests can assert on event counts, types, and visibility keys.
    """

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


class _RaisingWS:
    """Stand-in WS whose ``send_json`` always raises.

    Exercise the broadcast-exception-isolation contract: the per-WS
    try/except inside ``broadcast_to_session`` discards the dead WS;
    the dispatcher does NOT propagate the failure.
    """

    def __init__(self, exc: BaseException | None = None) -> None:
        self._exc = exc or RuntimeError("ws is dead")
        self.send_calls = 0

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.send_calls += 1
        raise self._exc


# ─── Helper: drive a single inbound and return (session_id, fake_ws) ─────


async def _dispatch_and_collect(
    *,
    factory: Any,
    envelope_text: str = "hello",
    subscribe_before_dispatch: bool = True,
) -> tuple[str, _FakeWS]:
    """Bootstrap one inbound and (optionally) attach a ``_FakeWS`` to
    the session it will resolve to BEFORE driving the dispatch.

    Returns the session_id (so callers can re-subscribe / re-dispatch
    on the same session) and the fake WS that captured the broadcast
    payloads.

    The dispatch must run AFTER the subscriber is registered because
    ``broadcast_to_session`` reads a snapshot of the subscriber set
    each call — subscribing post-dispatch would catch zero broadcasts.

    To know the session_id ahead of time we run a non-blocking warmup
    dispatch with no subscriber, look up the row the resolver created,
    register the fake WS against THAT id, then run the dispatch under
    test. The warmup dispatch's broadcast goes nowhere (zero subs at
    the moment it fires).
    """
    warmup_factory = await _make_factory()
    await dispatch_inbound("acct-test", _envelope(), factory=warmup_factory)
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1
    session_id = sessions[0].id

    fake_ws = _FakeWS()
    if subscribe_before_dispatch:
        add_subscriber(session_id, fake_ws)

    await dispatch_inbound("acct-test",
        _envelope(text=envelope_text),
        factory=factory,
    )
    return session_id, fake_ws


# ─── Test: per-message broadcast when subscribed ─────────────────────────


async def test_dispatch_inbound_broadcasts_per_message_when_subscribed(
    isolated_db,
) -> None:
    """A live WS subscriber receives one ``send_json`` per new
    Message: the peer's USER (codec-projected from the message
    ``agent.step`` appends internally) + the assistant's plain-text
    reply.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    _, fake_ws = await _dispatch_and_collect(factory=factory, envelope_text="ping")

    # Two events: user (peer inbound) + assistant (mock reply "ok").
    assert len(fake_ws.payloads) == 2
    types = [p["type"] for p in fake_ws.payloads]
    assert types == ["user", "assistant"]
    # The peer inbound's text is what the dispatcher passed to agent.step.
    user_event = fake_ws.payloads[0]
    assert user_event["content"] == "ping"
    # The assistant event's content comes from the mock provider.
    assistant_event = fake_ws.payloads[1]
    assert assistant_event["content"] == "ok"


# ─── Test: zero-subscriber no-op ─────────────────────────────────────────


async def test_dispatch_inbound_zero_subscribers_is_noop(isolated_db) -> None:
    """No subscribers registered → dispatch completes cleanly; no
    exception, no observable broadcast side effect. Pins back-compat
    with the dispatcher's pre-L6 behavior.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    # Drive the dispatcher with no add_subscriber call — must not raise.
    await dispatch_inbound("acct-test", _envelope(), factory=factory)

    # Sanity: the dispatcher still did its work (session row + history
    # exist). The point is the broadcast layer is a clean no-op.
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    assert len(sessions) == 1


# ─── Test: visibility carried on broadcast events ────────────────────────


async def test_dispatch_inbound_broadcasts_carry_visibility(
    isolated_db, monkeypatch
) -> None:
    """An assistant-with-tool_calls (``send_to_platform_channel``) +
    successful TOOL result drives the broadcast through every
    visibility branch:

    - USER event (peer inbound, ``visibility=None`` per leg-3 USER
      skip): ``"visibility"`` key OMITTED from the event payload.
    - The assistant has empty ``content`` (LLM emits ONLY tool calls
      here) — the codec's ``if msg.content:`` skips the
      assistant-content event entirely.
    - TOOL_CALL event (visibility inherited from the assistant
      Message → ``OPERATOR_VISIBILITY``): ``"visibility" ==
      "operator"``.
    - TOOL_RESULT event (leg-3 send-success carve-out →
      ``visibility=None``): ``"visibility"`` key OMITTED.

    Assertions use ``"visibility" not in event`` (NOT
    ``event.get("visibility") is None``) to pin the contract that the
    codec omits the key, rather than emitting an explicit-null value.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

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

    _, fake_ws = await _dispatch_and_collect(factory=factory)

    # Event sequence (in order, exact contents):
    # 1. user      (peer inbound; no visibility key)
    # 2. tool_call (the send_to_platform_channel; visibility=operator)
    # 3. tool_result (the platform-send success; no visibility key)
    # 4. assistant "done" (the final plain-text turn-ender; visibility=operator)
    # The assistant-with-empty-content message produces no assistant event
    # (the codec's `if msg.content:` skip).
    types = [p["type"] for p in fake_ws.payloads]
    assert types == ["user", "tool_call", "tool_result", "assistant"], (
        f"unexpected event sequence: {types}"
    )

    user_event, tool_call_event, tool_result_event, assistant_event = (
        fake_ws.payloads
    )

    # USER: visibility key omitted (peer-visible default).
    assert "visibility" not in user_event

    # TOOL_CALL: visibility = "operator" (carried from the assistant
    # Message that emitted the call — tagged by tag_post_step_visibility).
    assert tool_call_event["visibility"] == OPERATOR_VISIBILITY
    assert tool_call_event["name"] == "send_to_platform_channel"

    # TOOL_RESULT: visibility key omitted (leg-3 carve-out tagged the
    # tool message as visibility=None, codec omits the key).
    assert "visibility" not in tool_result_event
    assert tool_result_event["content"].startswith(PLATFORM_SEND_OK_PREFIX)

    # Final assistant text turn-ender: visibility = "operator".
    assert assistant_event["visibility"] == OPERATOR_VISIBILITY
    assert assistant_event["content"] == "done"


# ─── Test: broadcast runs AFTER persistence ──────────────────────────────


async def test_dispatch_inbound_broadcasts_after_persistence(
    isolated_db, monkeypatch
) -> None:
    """The broadcast loop runs AFTER ``chat_repo.update`` completes.

    Wrap ``ChatSessionRepository.update`` so it appends ``"persist"``
    to a shared ordered list on call; the fake WS's ``send_json``
    appends ``"broadcast"``. The resulting list must start with
    ``"persist"`` and have every subsequent entry be ``"broadcast"``
    (one per broadcast event).

    M10 F8 L11 HAT Fix #4: auto-relay is opted OUT here because it
    issues a second ``chat_repo.update`` (re-persisting the assistant
    reply with flipped visibility) after the broadcast loop —
    confounding the persist/broadcast ordering count. The
    persist-then-broadcast ordering contract is verified on the pure
    inbound path; the auto-relay re-persist's relative ordering is
    not under test here.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account(
        config={"auto_relay_platform_replies": False}
    )
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    order: list[str] = []

    from the_one.db import repositories as _repos_mod

    real_update = _repos_mod.ChatSessionRepository.update

    async def _tracking_update(self, session, *args, **kwargs):
        order.append("persist")
        return await real_update(self, session, *args, **kwargs)

    monkeypatch.setattr(
        _repos_mod.ChatSessionRepository, "update", _tracking_update
    )

    # Subclass FakeWS to record into the shared order list.
    class _OrderingWS:
        async def send_json(self, payload: dict[str, Any]) -> None:
            order.append("broadcast")

    warmup_factory = await _make_factory()
    await dispatch_inbound("acct-test", _envelope(), factory=warmup_factory)
    # The warmup dispatch's "persist" is in `order` once.
    assert order == ["persist"]

    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    session_id = sessions[0].id

    ordering_ws = _OrderingWS()
    add_subscriber(session_id, ordering_ws)

    await dispatch_inbound("acct-test", _envelope(text="ping"), factory=factory)

    # After the second dispatch: another "persist" is recorded, then
    # one "broadcast" per new message in the turn (here: USER + ASSISTANT).
    # The first element from the warmup remains.
    assert order[0] == "persist", order
    # The second-dispatch persist call lands BEFORE any broadcast entry.
    second_persist_idx = order.index("persist", 1)
    # No "broadcast" entry exists before the second "persist".
    assert "broadcast" not in order[1:second_persist_idx]
    # Every entry AFTER the second persist is a broadcast (per-message).
    tail = order[second_persist_idx + 1 :]
    assert tail, "expected at least one broadcast after the second persist"
    assert all(x == "broadcast" for x in tail), tail


# ─── Test: broadcast exception isolation ─────────────────────────────────


async def test_dispatch_inbound_broadcast_exception_does_not_corrupt_state(
    isolated_db,
) -> None:
    """A subscriber whose ``send_json`` raises must not propagate the
    exception past the dispatcher.

    ``broadcast_to_session`` wraps each per-WS send in a try/except and
    treats raisers as dead subscribers; the dispatcher inherits that
    safety. The dispatcher's persistence and ContextVar-reset paths
    must still complete cleanly.
    """
    await _seed_provider_and_agent()
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)
    factory = await _make_factory()

    warmup_factory = await _make_factory()
    await dispatch_inbound("acct-test", _envelope(), factory=warmup_factory)
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    session_id = sessions[0].id

    raising_ws = _RaisingWS()
    add_subscriber(session_id, raising_ws)

    # No exception bubbles to the caller.
    await dispatch_inbound("acct-test", _envelope(text="ping"), factory=factory)

    # The raising WS got at least one send_json attempt.
    assert raising_ws.send_calls >= 1
    # The dispatcher still persisted the turn.
    sessions = await chat_repo.list()
    assert len(sessions) == 1


# ─── Test: multi-turn parent_message_id non-collision ────────────────────


async def test_dispatch_inbound_multi_turn_parent_message_ids_do_not_collide(
    isolated_db, monkeypatch
) -> None:
    """Two consecutive inbound turns on the SAME session_id, each
    emitting an assistant-with-tool_calls, must produce DISTINCT
    ``parent_message_id`` values in the broadcast stream.

    Regression net for the codec ``index_offset`` fix: without the
    offset, both turns would emit ``replay-msg-0`` for their assistant-
    with-tool_calls (the dispatcher passes ``agent.messages[pre_step_len:]``
    so the slice always starts at relative index 0). The frontend's
    ``getOrCreateTrace(parent_message_id)`` would then bucket the
    second turn's tool_call/tool_result into the first turn's trace
    shell. The codec ``index_offset=pre_step_len`` keyword-only
    parameter shifts the index to the message's absolute position in
    the session's history.
    """
    await _seed_provider_and_agent(connector_account_ids=["acct-test"])
    await _seed_stub_account()
    register_for_test("stub", StubPlugin)

    # Two turns; each turn = assistant-with-tool_calls (platform send)
    # + plain-text turn-ender.
    tc1 = ToolCall(
        id="tc-send-1",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "ch-1"},
            "content": "turn1",
        },
    )
    tc2 = ToolCall(
        id="tc-send-2",
        name="send_to_platform_channel",
        arguments={
            "target": {"account_id": "acct-test", "channel_id": "ch-1"},
            "content": "turn2",
        },
    )
    responses = [
        # Turn 1
        Message.assistant(content="", tool_calls=[tc1]),
        Message.assistant(content="end1"),
        # Turn 2
        Message.assistant(content="", tool_calls=[tc2]),
        Message.assistant(content="end2"),
    ]
    factory = await _make_scripted_factory(
        responses, monkeypatch, connector_account_ids=["acct-test"]
    )

    # Warmup so the session row exists; register subscriber against it.
    warmup_factory = await _make_factory()
    await dispatch_inbound("acct-test", _envelope(), factory=warmup_factory)
    conn = await get_connection()
    chat_repo = ChatSessionRepository(conn)
    sessions = await chat_repo.list()
    session_id = sessions[0].id

    fake_ws = _FakeWS()
    add_subscriber(session_id, fake_ws)

    # Turn 1
    await dispatch_inbound("acct-test", _envelope(text="t1"), factory=factory)
    # Turn 2 — same session_id, same factory (the scripted provider's
    # responses iterator carries through to entries 2,3).
    await dispatch_inbound("acct-test", _envelope(text="t2"), factory=factory)

    # Collect every parent_message_id the dispatcher broadcasted across
    # BOTH turns. The events for the tool_call + tool_result of each
    # turn share a parent_message_id; ACROSS turns they MUST differ.
    pmids = [
        p["parent_message_id"]
        for p in fake_ws.payloads
        if "parent_message_id" in p
    ]
    # At least one pmid per turn (tool_call + tool_result each cite one).
    assert len(pmids) >= 2, fake_ws.payloads
    # All pmid VALUES are distinct across turns. (Within a single turn
    # the tool_call + tool_result share a pmid; across turns the pmids
    # must differ. So the unique-set should have exactly 2 entries:
    # one per turn.)
    assert len(set(pmids)) == 2, (
        f"parent_message_ids collided across turns: {pmids}"
    )
