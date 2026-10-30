"""Envelope-free connector delivery primitives (Mission 33 Flight 1 leg 2).

Part 1 characterizes ``inbound._auto_deliver_reply`` / ``_send_step_limit_line``
(they pass before and after the extraction). Part 2 tests the primitives in
``the_one.connectors.delivery`` directly.
"""

from __future__ import annotations

import importlib

import pytest

from the_one.connectors import inbound
from the_one.connectors.base import (
    ChannelTarget,
    ConnectorClientError,
    InboundEnvelope,
    PeerTarget,
    keying_to_target,
)
from the_one.db.models import ChatSession, Connector
from the_one.llm.base import OPERATOR_VISIBILITY, Message, Role, ToolCall, ToolResult


class _Client:
    def __init__(self, exc: Exception | None = None):
        self.sent: list[tuple[object, str]] = []
        self.exc = exc

    async def send(self, target, content):
        if self.exc is not None:
            raise self.exc
        self.sent.append((target, content))


class _Manager:
    def __init__(self, client: _Client | None):
        self.client = client

    def client_for(self, connector_id):
        return self.client


def _env(**kw) -> InboundEnvelope:
    base = dict(
        platform="stub",
        connector_id="conn-1",
        channel_id="ch-1",
        thread_id="t-9",
        peer_id="peer-1",
        peer_name="Alice",
        text="hi",
        is_dm=False,
        mentions_bot=False,
    )
    base.update(kw)
    return InboundEnvelope(**base)


def _final(text="the reply") -> Message:
    return Message(role=Role.ASSISTANT, content=text, visibility=OPERATOR_VISIBILITY)


def _turn(*extra: Message) -> list[Message]:
    return [Message(role=Role.USER, content="q", visibility=OPERATOR_VISIBILITY), *extra]


def _tool_send(ok: bool) -> list[Message]:
    call = Message(
        role=Role.ASSISTANT,
        content="",
        tool_calls=[ToolCall(id="c1", name="send_to_platform_channel", arguments={})],
    )
    body = "[platform-send-ok] sent" if ok else "[error] nope"
    res = Message(role=Role.TOOL, content=body, tool_result=ToolResult("c1", body))
    return [call, res]


def _d():
    return importlib.import_module("the_one.connectors.delivery")


async def _auto(msgs, env, mgr):
    await inbound._auto_deliver_reply(msgs, 0, env, "conn-1", mgr)


# ---- Part 1: characterization through the inbound wrappers -----------------


async def test_char_no_assistant_message():
    c = _Client()
    await _auto(_turn(), _env(), _Manager(c))
    assert c.sent == []


@pytest.mark.parametrize("content", [""])
async def test_char_empty_final(content):
    c = _Client()
    msgs = _turn(Message(role=Role.ASSISTANT, content=content, visibility=OPERATOR_VISIBILITY))
    await _auto(msgs, _env(), _Manager(c))
    assert c.sent == []
    assert msgs[-1].visibility == OPERATOR_VISIBILITY


async def test_char_generic_exception_stays_operator_only():
    c = _Client(RuntimeError("boom"))
    msgs = _turn(_final())
    await _auto(msgs, _env(), _Manager(c))
    assert msgs[-1].visibility == OPERATOR_VISIBILITY


async def test_char_skip_after_successful_tool_send():
    c = _Client()
    msgs = _turn(*_tool_send(True), _final())
    await _auto(msgs, _env(), _Manager(c))
    assert c.sent == []
    assert msgs[-1].visibility == OPERATOR_VISIBILITY


async def test_char_failed_tool_send_still_delivers():
    c = _Client()
    msgs = _turn(*_tool_send(False), _final())
    await _auto(msgs, _env(), _Manager(c))
    assert [s[1] for s in c.sent] == ["the reply"]
    assert msgs[-1].visibility is None


async def test_char_step_limit_line_sends_and_swallows():
    c = _Client()
    await inbound._send_step_limit_line(_env(), "conn-1", _Manager(c))
    assert c.sent == [(ChannelTarget("conn-1", "ch-1", "t-9"), inbound.STEP_LIMIT_LINE)]
    await inbound._send_step_limit_line(_env(), "conn-1", _Manager(None))
    await inbound._send_step_limit_line(_env(), "conn-1", _Manager(_Client(RuntimeError("x"))))


# ---- Part 2: the primitives -------------------------------------------------


async def test_deliver_outcomes():
    d = _d()
    ch = ChannelTarget("conn-1", "ch-1", "t-9")
    c = _Client()
    assert await d.deliver_final_reply(_turn(), 0, ch, "conn-1", _Manager(c)) is None
    assert c.sent == []  # no assistant text: nothing to send
    msgs = _turn(*_tool_send(True), _final())
    await d.deliver_final_reply(msgs, 0, ch, "conn-1", _Manager(c))
    assert c.sent == []  # already sent through the tool
    assert msgs[-1].visibility == OPERATOR_VISIBILITY
    msgs = _turn(_final())
    await d.deliver_final_reply(msgs, 0, ch, "conn-1", _Manager(None))  # no client: no raise
    assert msgs[-1].visibility == OPERATOR_VISIBILITY
    for exc in (ConnectorClientError("down"), ValueError("bad")):
        msgs = _turn(_final("SECRET"))
        await d.deliver_final_reply(msgs, 0, ch, "conn-1", _Manager(_Client(exc)))
        assert msgs[-1].visibility == OPERATOR_VISIBILITY  # a failed send never raises
    msgs = _turn(_final())
    await d.deliver_final_reply(msgs, 0, ch, "conn-1", _Manager(c))
    assert c.sent == [(ch, "the reply")] and msgs[-1].visibility is None


@pytest.mark.parametrize(
    "target", [ChannelTarget("conn-1", "ch-1", "t-1"), PeerTarget("conn-1", "p-1")]
)
async def test_sends_to_exact_target(target):
    c = _Client()
    await _d().deliver_final_reply(_turn(_final()), 0, target, "conn-1", _Manager(c))
    assert c.sent == [(target, "the reply")]


async def test_step_limit_line_direct():
    d = _d()
    c = _Client()
    tgt = PeerTarget("conn-1", "p-1")
    await d.send_step_limit_line(tgt, "conn-1", _Manager(c))
    assert c.sent == [(tgt, d.STEP_LIMIT_LINE)]
    await d.send_step_limit_line(tgt, "conn-1", _Manager(None))
    await d.send_step_limit_line(tgt, "conn-1", _Manager(_Client(ConnectorClientError("e"))))
    await d.send_step_limit_line(tgt, "conn-1", _Manager(_Client(RuntimeError("e"))))


def _row(**kw) -> ChatSession:
    base = dict(id="s", agent_name="a", connector_id="conn-1")
    base.update(kw)
    return ChatSession(**base)


def test_keying_shapes():
    assert keying_to_target(_row(channel_id="D1")) == ChannelTarget("conn-1", "D1")
    assert keying_to_target(_row(channel_id="")) == ChannelTarget("conn-1", "")
    assert keying_to_target(_row(channel_id=None, peer_id="p")) == PeerTarget("conn-1", "p")
    assert keying_to_target(_row(connector_id=None)) is None


def _conn(**cfg) -> Connector:
    return Connector(id="conn-1", name="T", type="stub", config=cfg)


def test_authorized_agent_for():
    f = _d().authorized_agent_for
    c = _conn(channel_map={"ch-1": "mapped"}, default_agent="dflt")
    assert f(c, channel_id="ch-1") == "mapped"
    assert f(c, channel_id="other") == "dflt"
    assert f(c, channel_id="") == "dflt"
    assert f(c, channel_id=None) == "dflt"
    assert f(_conn(), channel_id="x") is None
    assert f(_conn(channel_map={"ch-1": "m"}), channel_id=None) is None
