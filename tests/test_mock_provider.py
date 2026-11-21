"""Unit tests for MockProvider."""

from __future__ import annotations

from the_one.llm import get_provider
from the_one.llm.base import Message, Role, ToolResult
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


# ---------------------------------------------------------------------------
# M36 F3 L9 — config["responses"]: a stateless scripted sequence
# ---------------------------------------------------------------------------

_FILL_CALL = {"id": "tc1", "name": "fill_form", "arguments": {"kind": "agent"}}
_SEQUENCE = [
    {"content": "", "tool_calls": [_FILL_CALL]},
    {"content": "second"},
    {"content": "last"},
]


def _tool_msg(call_id: str = "tc1") -> Message:
    return Message.tool(ToolResult(tool_call_id=call_id, content="ok"))


class TestMockProviderResponses:
    async def test_sequence_follows_tool_messages_after_last_user(self) -> None:
        provider = MockProvider(config={"responses": _SEQUENCE})
        history = [Message.user("go")]
        first = await provider.complete(messages=history)
        assert [tc.name for tc in first.tool_calls] == ["fill_form"]
        history += [first, _tool_msg()]
        second = await provider.complete(messages=history)
        assert second.content == "second"
        assert second.tool_calls == []

    async def test_clamps_to_the_last_entry(self) -> None:
        provider = MockProvider(config={"responses": _SEQUENCE})
        history = [Message.user("go")] + [_tool_msg(str(i)) for i in range(6)]
        msg = await provider.complete(messages=history)
        assert msg.content == "last"

    async def test_new_user_message_restarts_at_zero(self) -> None:
        provider = MockProvider(config={"responses": _SEQUENCE})
        history = [Message.user("go"), _tool_msg(), _tool_msg("2"), Message.user("again")]
        msg = await provider.complete(messages=history)
        assert [tc.name for tc in msg.tool_calls] == ["fill_form"]

    async def test_absent_responses_is_unchanged(self) -> None:
        provider = MockProvider(config={"response": {"content": "fixed"}})
        history = [Message.user("go"), _tool_msg()]
        assert (await provider.complete(messages=history)).content == "fixed"

    async def test_empty_responses_falls_back_to_response(self) -> None:
        provider = MockProvider(config={"responses": [], "response": {"content": "fixed"}})
        assert (await provider.complete(messages=[Message.user("go")])).content == "fixed"

    async def test_stream_without_chunks_uses_the_selected_entry(self) -> None:
        provider = MockProvider(config={"responses": _SEQUENCE})
        chunks = [c async for c in provider.stream(messages=[Message.user("go")])]
        assert [tc.name for tc in chunks[-1].tool_calls] == ["fill_form"]
        history = [Message.user("go"), _tool_msg()]
        chunks = [c async for c in provider.stream(messages=history)]
        assert chunks[-1].content == "second"

    async def test_stream_chunks_carry_the_selected_entry_tool_calls(self) -> None:
        provider = MockProvider(config={"responses": _SEQUENCE, "stream_chunks": ["a", "b"]})
        chunks = [c async for c in provider.stream(messages=[Message.user("go")])]
        final = chunks[-1]
        assert final.is_final
        assert [tc.name for tc in final.tool_calls] == ["fill_form"]
        assert final.message is not None
        assert [tc.name for tc in final.message.tool_calls] == ["fill_form"]
        # Later in the turn the selected entry has no tool calls.
        history = [Message.user("go"), _tool_msg()]
        chunks = [c async for c in provider.stream(messages=history)]
        assert chunks[-1].tool_calls == []
