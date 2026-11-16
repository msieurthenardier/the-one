"""Sortie 17: extended thinking follows the model.

The adaptive-thinking option is sent only to models that support it; a 400 that says
the model cannot think strips thinking in place, once, and is remembered per process.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

import anthropic
import pytest

from tests.fixtures.tool_schemas import make_bad_request
from tests.test_anthropic_provider import (
    _CreateRecorder,
    _StreamCM,
    _StreamRecorder,
    _StubContentBlock,
    _StubResponse,
    _tool,
    _user_msg,
)
from the_one.llm import anthropic_provider as ap
from the_one.llm.anthropic_plan_provider import (
    AnthropicPlanProvider,
    AnthropicPlanTokenProvider,
)
from the_one.llm.anthropic_provider import AnthropicProvider, supports_adaptive_thinking
from the_one.llm.base import Message, ThinkingBlock, ToolCall, ToolResult

SQUAWK_400 = (
    "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
    "'message': 'adaptive thinking is not supported on this model'}}"
)
TEMP_400 = "temperature may only be set to 1 when thinking is enabled"
REPLAY_400 = "a final assistant message must start with a thinking block"
ON = {"thinking_enabled": True}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    ap._clear_no_thinking_models()
    yield
    ap._clear_no_thinking_models()


# ---- the rule (criteria 1, 2) ------------------------------------------------

_CATALOG = json.loads(
    (Path(__file__).parent.parent / "the_one/llm/data/model_catalog.json").read_text()
)["providers"]["anthropic"]

_EXPECTED = {
    "claude-3-5-haiku-20241022": False,
    "claude-3-5-haiku-latest": False,
    "claude-3-5-sonnet-20240620": False,
    "claude-3-5-sonnet-20241022": False,
    "claude-3-7-sonnet-20250219": False,
    "claude-3-haiku-20240307": False,
    "claude-3-opus-20240229": False,
    "claude-3-sonnet-20240229": False,
    "claude-fable-5": True,
    "claude-fable-5-1": True,
    "claude-haiku-4-5": False,
    "claude-haiku-4-5-20251001": False,
    "claude-haiku-5-5": True,
    "claude-opus-4-0": False,
    "claude-opus-4-1": False,
    "claude-opus-4-1-20250805": False,
    "claude-opus-4-20250514": False,
    "claude-opus-4-5": False,
    "claude-opus-4-5-20251101": False,
    "claude-opus-4-6": True,
    "claude-opus-4-7": True,
    "claude-opus-4-8": True,
    "claude-opus-5": True,
    "claude-opus-5-5": True,
    "claude-sonnet-4-0": False,
    "claude-sonnet-4-20250514": False,
    "claude-sonnet-4-5": False,
    "claude-sonnet-4-5-20250929": False,
    "claude-sonnet-4-6": True,
    "claude-sonnet-5": True,
    "claude-sonnet-5-5": True,
}


def test_expected_table_covers_the_catalog():
    assert set(_EXPECTED) == set(_CATALOG)


@pytest.mark.parametrize("model,expected", sorted(_EXPECTED.items()))
def test_catalog_ids(model, expected):
    assert supports_adaptive_thinking(model) is expected


@pytest.mark.parametrize(
    "model,expected",
    [
        ("claude-test", True),
        ("", True),
        ("  Claude-Sonnet-4-5  ", True),
        ("claude-sonnet-4-10", True),
        ("claude-sonnet-4-9-latest", True),
        ("claude-sonnet-4-5-latest", False),
        ("claude-sonnet-4-20250514", False),
        ("claude-3-future-model", False),
    ],
)
def test_edge_ids(model, expected):
    assert supports_adaptive_thinking(model) is expected


def test_remembered_model_is_false():
    assert supports_adaptive_thinking("claude-test") is True
    ap._NO_THINKING_MODELS.add("claude-test")
    assert supports_adaptive_thinking("claude-test") is False


# ---- _build_kwargs (criterion 3) ---------------------------------------------


def _history() -> list[Message]:
    return [
        Message.user("go"),
        Message.assistant(
            "working",
            tool_calls=[ToolCall(id="tu_1", name="t", arguments={})],
            thinking=[
                ThinkingBlock(type="thinking", thinking="r", signature="s"),
                ThinkingBlock(type="redacted_thinking", data="blob"),
            ],
        ),
        Message.tool(ToolResult(tool_call_id="tu_1", content="done")),
    ]


def _block_types(kwargs) -> set[str]:
    out: set[str] = set()
    for m in kwargs["messages"]:
        if isinstance(m["content"], list):
            out |= {b["type"] for b in m["content"]}
    return out


def _make(cls, model):
    if cls is AnthropicProvider:
        return AnthropicProvider(model=model, api_key="sk-test", config=ON)
    return cls(model=model, access_token="tok", config=ON)


CLASSES = [AnthropicProvider, AnthropicPlanProvider, AnthropicPlanTokenProvider]


@pytest.mark.parametrize("cls", CLASSES)
def test_incapable_model_gets_no_thinking_and_no_blocks(cls):
    kw = _make(cls, "claude-haiku-4-5")._build_kwargs(_history(), None, 0.0, 100)
    assert "thinking" not in kw
    assert not ({"thinking", "redacted_thinking"} & _block_types(kw))


@pytest.mark.parametrize("cls", CLASSES)
def test_capable_model_unchanged(cls):
    kw = _make(cls, "claude-sonnet-4-6")._build_kwargs(_history(), None, 0.0, 100)
    assert kw["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert {"thinking", "redacted_thinking"} <= _block_types(kw)


def test_enable_thinking_false_still_wins():
    prov = _make(AnthropicProvider, "claude-sonnet-4-6")
    kw = prov._build_kwargs(_history(), None, 0.0, 100, False)
    assert "thinking" not in kw


# ---- the strip (criteria 4-9) ------------------------------------------------


def _prov(monkeypatch, model="claude-test", **rec_kw):
    prov = AnthropicProvider(model=model, api_key="sk-test", config=ON)
    rec = _CreateRecorder(**rec_kw)
    monkeypatch.setattr(prov.client.messages, "create", rec)
    return prov, rec


def _ok_stream():
    final = _StubResponse(content=[_StubContentBlock("text", text="ok")], usage=None)
    return lambda: _StreamCM(["ok"], final)


def _err_stream(msg):
    return lambda: _StreamCM([], None, raise_on_enter=make_bad_request(msg))


async def test_complete_strips_thinking_and_remembers(monkeypatch, caplog):
    prov, rec = _prov(monkeypatch, side_effects=[make_bad_request(SQUAWK_400)])
    history = _history()
    before = copy.deepcopy(history)
    with caplog.at_level(logging.WARNING, logger="the_one.llm.anthropic_provider"):
        out = await prov.complete(history)
    assert out.content == "ok"
    assert len(rec.calls) == 2
    assert "thinking" in rec.calls[0]
    assert "thinking" not in rec.calls[1]
    assert not ({"thinking", "redacted_thinking"} & _block_types(rec.calls[1]))
    assert "claude-test" in ap._NO_THINKING_MODELS
    assert len([r for r in caplog.records if "adaptive thinking" in r.message]) == 1
    assert history == before  # stored messages untouched (criterion 9)


async def test_second_not_supported_is_reraised_complete(monkeypatch):
    err2 = make_bad_request(SQUAWK_400)
    prov, rec = _prov(monkeypatch, side_effects=[make_bad_request(SQUAWK_400), err2])
    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_user_msg())
    assert ei.value is err2
    assert len(rec.calls) == 2


async def test_second_not_supported_is_reraised_stream(monkeypatch):
    prov = AnthropicProvider(model="claude-test", api_key="sk-test", config=ON)
    rec = _StreamRecorder([_err_stream(SQUAWK_400), _err_stream(SQUAWK_400)])
    monkeypatch.setattr(prov.client.messages, "stream", rec)
    with pytest.raises(anthropic.BadRequestError):
        [c async for c in prov.stream(_user_msg())]
    assert len(rec.calls) == 2


async def test_stream_strips_thinking_then_succeeds(monkeypatch):
    prov = AnthropicProvider(model="claude-test", api_key="sk-test", config=ON)
    rec = _StreamRecorder([_err_stream(SQUAWK_400), _ok_stream()])
    monkeypatch.setattr(prov.client.messages, "stream", rec)
    chunks = [c async for c in prov.stream(_history())]
    assert any("ok" in c.content for c in chunks if not c.is_final)
    assert "thinking" in rec.calls[0] and "thinking" not in rec.calls[1]
    assert not ({"thinking", "redacted_thinking"} & _block_types(rec.calls[1]))


async def test_temperature_then_thinking_composes_complete(monkeypatch):
    prov, rec = _prov(
        monkeypatch,
        side_effects=[make_bad_request("temperature: unsupported"), make_bad_request(SQUAWK_400)],
    )
    out = await prov.complete(_user_msg(), tools=[_tool("t", {"type": "object", "properties": {}})])
    assert out.content == "ok"
    assert len(rec.calls) == 3
    assert "temperature" not in rec.calls[2] and "thinking" not in rec.calls[2]
    assert "temperature" not in rec.calls[1] and "thinking" in rec.calls[1]


async def test_temperature_then_thinking_composes_stream(monkeypatch):
    prov = AnthropicProvider(model="claude-test", api_key="sk-test", config=ON)
    rec = _StreamRecorder(
        [_err_stream("temperature: unsupported"), _err_stream(SQUAWK_400), _ok_stream()]
    )
    monkeypatch.setattr(prov.client.messages, "stream", rec)
    [c async for c in prov.stream(_user_msg())]
    assert len(rec.calls) == 3
    assert "temperature" not in rec.calls[2] and "thinking" not in rec.calls[2]


async def test_temperature_400_leaves_thinking(monkeypatch):
    prov, rec = _prov(monkeypatch, side_effects=[make_bad_request(TEMP_400)])
    await prov.complete(_user_msg())
    assert "temperature" not in rec.calls[1]
    assert "thinking" in rec.calls[1]
    assert not ap._NO_THINKING_MODELS


async def test_replay_400_is_reraised_and_not_remembered(monkeypatch):
    err = make_bad_request(REPLAY_400)
    prov, rec = _prov(monkeypatch, side_effects=[err])
    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_user_msg())
    assert ei.value is err
    assert len(rec.calls) == 1
    assert not ap._NO_THINKING_MODELS


async def test_new_instance_starts_without_thinking_after_remembered(monkeypatch):
    prov, _ = _prov(monkeypatch, side_effects=[make_bad_request(SQUAWK_400)])
    await prov.complete(_user_msg())
    prov2, rec2 = _prov(monkeypatch)
    await prov2.complete(_user_msg())
    assert len(rec2.calls) == 1
    assert "thinking" not in rec2.calls[0]


async def test_thinking_only_assistant_message_is_dropped(monkeypatch):
    """A thinking-only assistant message has no content left after the strip; the
    API rejects an empty content list, so the message is dropped."""
    history = [
        Message.user("a"),
        Message.assistant(
            "", thinking=[ThinkingBlock(type="thinking", thinking="r", signature="s")]
        ),
        Message.user("b"),
    ]
    prov, rec = _prov(monkeypatch, side_effects=[make_bad_request(SQUAWK_400)])
    await prov.complete(history)
    assert [m["role"] for m in rec.calls[0]["messages"]] == ["user", "assistant", "user"]
    assert [m["role"] for m in rec.calls[1]["messages"]] == ["user", "user"]
    assert all(m["content"] != [] for m in rec.calls[1]["messages"])


@pytest.mark.parametrize("cls", [AnthropicPlanProvider, AnthropicPlanTokenProvider])
async def test_plan_provider_retry_never_reaches_translation(monkeypatch, cls):
    prov = cls(model="claude-test", access_token="tok", config=ON)
    rec = _CreateRecorder(side_effects=[make_bad_request(SQUAWK_400)])
    monkeypatch.setattr(prov.client.messages, "create", rec)
    out = await prov.complete(_user_msg())
    assert out.content == "ok"
    assert len(rec.calls) == 2 and "thinking" not in rec.calls[1]
