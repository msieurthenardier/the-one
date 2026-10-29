"""Routine marker on ``Message`` (Mission 33 F1 L3, AC1-AC2)."""

from __future__ import annotations

import pytest

from the_one.db.codec import message_from_dict, message_to_dict, messages_to_ui_events
from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message
from the_one.llm.ollama_provider import OllamaProvider
from the_one.llm.openai_provider import OpenAIProvider
from the_one.llm.openrouter_provider import OpenRouterProvider


def _marked() -> Message:
    return Message.user("run it", routine_id="r1", routine_name="Morning")


def test_user_factory_accepts_marker():
    m = _marked()
    assert (m.routine_id, m.routine_name) == ("r1", "Morning")


def test_codec_round_trip():
    d = message_to_dict(_marked())
    assert d["routine_id"] == "r1" and d["routine_name"] == "Morning"
    back = message_from_dict(d)
    assert (back.routine_id, back.routine_name) == ("r1", "Morning")


def test_codec_omits_when_unset_and_legacy_decodes_none():
    d = message_to_dict(Message.user("hi"))
    assert "routine_id" not in d and "routine_name" not in d
    back = message_from_dict(d)
    assert back.routine_id is None and back.routine_name is None


def test_ui_events_carry_marker_only_when_set():
    marked, plain = messages_to_ui_events([_marked(), Message.user("hi")])[:2]
    assert marked["routine_id"] == "r1" and marked["routine_name"] == "Morning"
    assert "routine_id" not in plain and "routine_name" not in plain


def _providers():
    return [
        OpenAIProvider(model="gpt-4o", api_key="x"),
        OpenRouterProvider(model="m", api_key="x"),
        OllamaProvider(model="m", base_url="http://localhost:11434/v1"),
    ]


@pytest.mark.parametrize("prov", _providers(), ids=lambda p: type(p).__name__)
def test_openai_family_payload_unchanged(prov):
    plain = Message.user("run it")
    assert prov._to_api_message(_marked()) == prov._to_api_message(plain)


def test_ollama_native_payload_unchanged():
    prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1")
    assert prov._to_native_message(_marked()) == prov._to_native_message(Message.user("run it"))


def test_anthropic_payload_unchanged():
    plain = Message.user("run it")
    for cls in (AnthropicProvider, AnthropicPlanProvider):
        try:
            prov = cls(model="claude-haiku-4-5", api_key="x")
        except TypeError:
            prov = cls(model="claude-haiku-4-5", token="x")
        assert prov._to_api_message(_marked()) == prov._to_api_message(plain)
