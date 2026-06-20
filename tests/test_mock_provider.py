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


# ---------------------------------------------------------------------------
# M16 F06 L03 — input_tokens config seam contract
# ---------------------------------------------------------------------------
# These tests lock the backward-compatible test seam: config["input_tokens"]
# is emitted in both complete() and stream(); default (no config) stays 0 so
# all existing usage-accounting tests are unaffected.


class TestMockProviderInputTokensSeam:
    """Seam contract: config["input_tokens"] flows through to usage."""

    async def test_complete_default_input_tokens_is_zero(self) -> None:
        """No config → input_tokens defaults to 0 (backward-compat guard)."""
        provider = MockProvider(model="mock-default")
        msg = await provider.complete(messages=[Message.user("hi")])
        assert msg.usage is not None
        assert msg.usage.input_tokens == 0

    async def test_complete_config_input_tokens_flows_through(self) -> None:
        """config={"input_tokens": N} → complete() emits usage.input_tokens == N."""
        provider = MockProvider(model="mock-default", config={"input_tokens": 42})
        msg = await provider.complete(messages=[Message.user("hi")])
        assert msg.usage is not None
        assert msg.usage.input_tokens == 42

    async def test_stream_default_input_tokens_is_zero(self) -> None:
        """No config → stream() final chunk usage.input_tokens defaults to 0."""
        provider = MockProvider(
            model="mock-default",
            config={"stream_chunks": ["hello ", "world"]},
        )
        final_chunk = None
        async for chunk in provider.stream(messages=[Message.user("hi")]):
            if chunk.is_final:
                final_chunk = chunk
        assert final_chunk is not None
        assert final_chunk.usage is not None
        assert final_chunk.usage.input_tokens == 0

    async def test_stream_config_input_tokens_flows_through(self) -> None:
        """config={"input_tokens": N, "stream_chunks": [...]} → final chunk emits N."""
        provider = MockProvider(
            model="mock-default",
            config={"input_tokens": 99, "stream_chunks": ["hello ", "world"]},
        )
        final_chunk = None
        async for chunk in provider.stream(messages=[Message.user("hi")]):
            if chunk.is_final:
                final_chunk = chunk
        assert final_chunk is not None
        assert final_chunk.usage is not None
        assert final_chunk.usage.input_tokens == 99

    async def test_stream_fallback_path_default_input_tokens_is_zero(self) -> None:
        """stream() no-stream_chunks fallback path: usage.input_tokens == 0 by default."""
        # No stream_chunks → falls through to complete() delegation path
        provider = MockProvider(model="mock-default")
        final_chunk = None
        async for chunk in provider.stream(messages=[Message.user("hi")]):
            if chunk.is_final:
                final_chunk = chunk
        assert final_chunk is not None
        assert final_chunk.usage is not None
        assert final_chunk.usage.input_tokens == 0

    async def test_stream_fallback_path_config_input_tokens_flows_through(self) -> None:
        """stream() no-stream_chunks fallback: config input_tokens flows via complete()."""
        provider = MockProvider(model="mock-default", config={"input_tokens": 77})
        final_chunk = None
        async for chunk in provider.stream(messages=[Message.user("hi")]):
            if chunk.is_final:
                final_chunk = chunk
        assert final_chunk is not None
        assert final_chunk.usage is not None
        assert final_chunk.usage.input_tokens == 77
