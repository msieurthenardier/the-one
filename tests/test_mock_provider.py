"""Unit tests for MockProvider."""

from __future__ import annotations

from the_one.llm import get_provider
from the_one.llm.base import Message, Role
from the_one.llm.mock import MockProvider


class TestMockProviderBehavior:
    async def test_default_response_when_no_config(self) -> None:
        provider = MockProvider(model="mock-default")
        msg = await provider.complete(messages=[Message.user("hi")])
        assert msg.role == Role.ASSISTANT
        assert "Mock" in msg.content
        assert msg.tool_calls == []

    async def test_scripted_text_response(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={"response": {"content": "Hello from script"}},
        )
        msg = await provider.complete(messages=[Message.user("hi")])
        assert msg.content == "Hello from script"
        assert msg.tool_calls == []

    async def test_scripted_tool_call_response(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={
                "response": {
                    "content": "",
                    "tool_calls": [{"id": "tc1", "name": "echo", "arguments": {"text": "hi"}}],
                }
            },
        )
        msg = await provider.complete(messages=[Message.user("hi")])
        assert msg.content == ""
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "tc1"
        assert msg.tool_calls[0].name == "echo"
        assert msg.tool_calls[0].arguments == {"text": "hi"}

    async def test_registry_returns_mock_provider(self) -> None:
        provider = get_provider("mock", model="mock-default")
        assert isinstance(provider, MockProvider)
        assert provider.name == "mock"

    def test_max_context_tokens_inherits_default(self) -> None:
        provider = MockProvider(model="mock-default")
        assert provider.max_context_tokens == 128_000
