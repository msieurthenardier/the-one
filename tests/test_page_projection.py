"""The page on a user message: step, projection, adapters and codec (M36 F3 L4, AC1-AC3)."""

from __future__ import annotations

import json

import pytest
from conftest import FakeLLM

from the_one.agent.core import Agent
from the_one.db.codec import message_from_dict, message_to_dict, messages_to_ui_events
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message, Role, TextContent, build_user_message_content
from the_one.llm.ollama_provider import OllamaProvider
from the_one.llm.openai_provider import OpenAIProvider
from the_one.tools.base import ToolRegistry

LINE = "Library › MCP servers › New MCP server"


def _agent() -> Agent:
    return Agent(
        llm=FakeLLM([Message.assistant("ok"), Message.assistant("ok2")]),
        tools=ToolRegistry(),
        system_prompt="t",
    )


# --- AC1: the core keyword -------------------------------------------------------------


async def test_step_stores_the_page_on_the_appended_user_message():
    agent = _agent()
    async for _ in agent.step("hi", page={"line": "X"}):
        pass
    user = [m for m in agent.messages if m.role == Role.USER]
    assert user[0].page == {"line": "X"}


async def test_step_without_a_page_leaves_it_none():
    agent = _agent()
    async for _ in agent.step("hi"):
        pass
    user = [m for m in agent.messages if m.role == Role.USER]
    assert user[0].page is None


# --- AC2: the projection ---------------------------------------------------------------


def test_str_content_with_a_page_leads_with_the_line():
    msg = Message.user("hello")
    msg.page = {"line": LINE}
    assert build_user_message_content(msg) == f"[Page: {LINE}]\nhello"


def test_page_then_peer_order():
    msg = Message.user("hello", peer_name="p")
    msg.page = {"line": "L"}
    assert build_user_message_content(msg) == "[Page: L]\n[from p]: hello"


def test_list_content_with_a_page_prepends_a_text_block():
    msg = Message.user([TextContent(text="look")])
    msg.page = {"line": "L"}
    out = build_user_message_content(msg)
    assert isinstance(out, list)
    assert out[0] == TextContent(text="[Page: L]")
    assert out[1:] == [TextContent(text="look")]


def test_list_content_page_comes_before_the_peer_block():
    msg = Message.user([TextContent(text="look")], peer_name="p")
    msg.page = {"line": "L"}
    out = build_user_message_content(msg)
    assert [b.text for b in out] == ["[Page: L]", "[from p]:", "look"]


def test_no_page_is_byte_identical():
    assert build_user_message_content(Message.user("hello")) == "hello"
    assert build_user_message_content(Message.user("hello", peer_name="p")) == "[from p]: hello"
    blocks = [TextContent(text="x")]
    out = build_user_message_content(Message.user(blocks))
    assert out == blocks and out is not blocks


# --- AC2: four adapters, two turns, str and list ---------------------------------------


def _turns(content):
    first = Message.user(content() if callable(content) else content)
    first.page = {"line": LINE}
    second = Message.user(content() if callable(content) else content)
    return first, second


def _anthropic(m):
    return AnthropicProvider(model="claude-sonnet-4-6", api_key="k")._to_api_message(m)


def _openai(m):
    return OpenAIProvider(model="gpt-4o", api_key="k")._to_api_message(m)


def _ollama_native(m):
    return OllamaProvider(model="q", base_url="http://t:11434")._to_native_message(m)


def _ollama_v1(m):
    return OllamaProvider(model="q", base_url="http://t:11434")._to_api_message(m)


@pytest.mark.parametrize("adapter", [_anthropic, _openai, _ollama_native, _ollama_v1])
@pytest.mark.parametrize("kind", ["str", "list"])
def test_adapter_carries_the_page_on_its_turn_only(adapter, kind):
    def content():
        return "hello" if kind == "str" else [TextContent(text="hello")]

    with_page, without = _turns(content)
    marked = json.dumps(adapter(with_page))
    plain = json.dumps(adapter(without))
    assert f"[Page: {LINE}]" in marked.replace("\\u203a", "›")
    assert "[Page:" not in plain
    # and byte-identical on every later request
    assert json.dumps(adapter(with_page)) == marked


# --- AC3: the codec --------------------------------------------------------------------


def test_a_page_round_trips():
    msg = Message.user("hi")
    msg.page = {"line": LINE}
    d = message_to_dict(msg)
    assert d["page"] == {"line": LINE}
    assert message_from_dict(d).page == {"line": LINE}


@pytest.mark.parametrize("raw", [None, "x", 5, [], {}, {"line": 3}, {"nope": "x"}])
def test_a_bad_stored_page_decodes_to_none(raw):
    d = message_to_dict(Message.user("hi"))
    d["page"] = raw
    assert message_from_dict(d).page is None


def test_no_page_emits_no_key():
    assert "page" not in message_to_dict(Message.user("hi"))


def test_only_the_line_is_stored():
    msg = Message.user("hi")
    msg.page = {"line": LINE, "descriptor": {"destination": "library"}}
    assert message_to_dict(msg)["page"] == {"line": LINE}


def test_ui_events_carry_page_on_that_user_event_only():
    plain = Message.user("a")
    paged = Message.user("b")
    paged.page = {"line": LINE}
    events = messages_to_ui_events([plain, Message.assistant("x"), paged, Message.assistant("y")])
    users = [e for e in events if e["type"] == "user"]
    assert "page" not in users[0]
    assert users[1]["page"] == {"line": LINE}
    assert all("page" not in e for e in events if e["type"] != "user")


def test_a_stored_page_keeps_its_line_after_a_rename():
    # The projection never resolves: the stored line is the bytes the model sees.
    msg = Message.user("hi")
    msg.page = {"line": "Agents › Old name › Tools"}
    back = message_from_dict(message_to_dict(msg))
    assert build_user_message_content(back) == "[Page: Agents › Old name › Tools]\nhi"
