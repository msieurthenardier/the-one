"""Unit tests for the F4 leg-04 streaming infrastructure.

Covers:
- StreamChunk default values
- LLMProvider.stream default impl (calls complete, yields one final chunk)
- MockProvider.stream with stream_chunks config
- MockProvider.stream falls back to default-impl when stream_chunks unset
- Anthropic streaming-path BadRequestError temperature retry (yielded_any guard)
- Agent.step uses streaming under the hood
- Agent.step calls on_chunk callback per content delta
- ollama_api.chat_stream parses SSE correctly
- Multi-iteration agent loop preserves chunks_seen invariant in app.py
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from tests.fixtures.tool_schemas import make_bad_request
from the_one.agent.core import Agent
from the_one.llm import ollama_api
from the_one.llm.base import LLMProvider, Message, Role, StreamChunk, TokenUsage, ToolCall
from the_one.llm.mock import MockProvider
from the_one.tools.base import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_iter_lines(items: list[str]):
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# StreamChunk dataclass
# ---------------------------------------------------------------------------


class TestStreamChunk:
    def test_default_values(self) -> None:
        chunk = StreamChunk()
        assert chunk.content == ""
        assert chunk.is_final is False
        assert chunk.tool_calls == []
        assert chunk.usage is None
        assert chunk.message is None


# ---------------------------------------------------------------------------
# Base class default stream() implementation
# ---------------------------------------------------------------------------


class _CompleteOnlyProvider(LLMProvider):
    """Minimal LLMProvider subclass that only implements complete().

    Exercises the base class's default stream() impl — should yield exactly
    one final chunk synthesised from the completed Message.
    """

    name = "complete-only"

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        return Message.assistant(
            content="single shot",
            tool_calls=[],
            usage=TokenUsage(input_tokens=1, output_tokens=2),
        )


class TestBaseStreamDefault:
    async def test_default_stream_yields_one_final_chunk(self) -> None:
        provider = _CompleteOnlyProvider()
        chunks = [c async for c in provider.stream(messages=[Message.user("hi")])]
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.is_final is True
        assert chunk.content == "single shot"
        assert chunk.message is not None
        assert chunk.message.content == "single shot"
        assert chunk.usage is not None
        assert chunk.usage.input_tokens == 1
        assert chunk.usage.output_tokens == 2


# ---------------------------------------------------------------------------
# Mock provider streaming
# ---------------------------------------------------------------------------


class TestMockStreamWithChunks:
    async def test_stream_chunks_yields_each_plus_final(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={"stream_chunks": ["Hello, ", "world", "!"], "delay_ms": 0},
        )
        chunks = [c async for c in provider.stream(messages=[Message.user("hi")])]
        # 3 content + 1 final
        assert len(chunks) == 4
        assert chunks[0].content == "Hello, "
        assert chunks[0].is_final is False
        assert chunks[1].content == "world"
        assert chunks[2].content == "!"
        assert chunks[3].is_final is True
        assert chunks[3].message is not None
        assert chunks[3].message.content == "Hello, world!"

    async def test_stream_chunks_with_tool_calls_in_response(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={
                "stream_chunks": ["a", "b"],
                "delay_ms": 0,
                "response": {
                    "content": "ignored — synthesized from chunks",
                    "tool_calls": [{"id": "tc1", "name": "echo", "arguments": {"text": "hi"}}],
                },
            },
        )
        chunks = [c async for c in provider.stream(messages=[Message.user("hi")])]
        assert len(chunks) == 3  # 2 deltas + 1 final
        final = chunks[-1]
        assert final.is_final is True
        assert final.message is not None
        assert final.message.content == "ab"
        assert len(final.tool_calls) == 1
        assert final.tool_calls[0].name == "echo"


class TestMockStreamFallback:
    async def test_no_stream_chunks_falls_back_to_default_impl(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={"response": {"content": "fallback content"}},
        )
        chunks = [c async for c in provider.stream(messages=[Message.user("hi")])]
        assert len(chunks) == 1
        assert chunks[0].is_final is True
        assert chunks[0].content == "fallback content"
        assert chunks[0].message is not None
        assert chunks[0].message.content == "fallback content"

    async def test_empty_stream_chunks_list_falls_back_to_default(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={"stream_chunks": [], "response": {"content": "x"}},
        )
        chunks = [c async for c in provider.stream(messages=[Message.user("hi")])]
        assert len(chunks) == 1
        assert chunks[0].is_final is True
        assert chunks[0].content == "x"


# ---------------------------------------------------------------------------
# Anthropic streaming BadRequestError temperature retry
# ---------------------------------------------------------------------------


class TestAnthropicStreamRetry:
    async def test_temperature_retry_yields_after_retry(self) -> None:
        from the_one.llm.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(model="claude-test", api_key="test-key")

        # Build a "successful" stream context-manager that yields one delta
        # plus a final message via get_final_message.
        async def _ok_text_stream():
            yield "hello"

        ok_stream_obj = MagicMock()
        ok_stream_obj.text_stream = _ok_text_stream()
        ok_final_msg = MagicMock()
        ok_final_msg.content = [MagicMock(type="text", text="hello")]
        ok_final_msg.usage = MagicMock(input_tokens=1, output_tokens=1)
        ok_stream_obj.get_final_message = AsyncMock(return_value=ok_final_msg)

        ok_cm = MagicMock()
        ok_cm.__aenter__ = AsyncMock(return_value=ok_stream_obj)
        ok_cm.__aexit__ = AsyncMock(return_value=False)

        call_count = {"n": 0}

        def _stream_factory(**kwargs: Any):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: raise BadRequestError mentioning "temperature"
                # BEFORE entering the context manager — synthesised by raising
                # in __aenter__.
                bad_cm = MagicMock()
                bad_cm.__aenter__ = AsyncMock(
                    side_effect=make_bad_request(
                        "Unsupported parameter: temperature must be omitted."
                    )
                )
                bad_cm.__aexit__ = AsyncMock(return_value=False)
                return bad_cm
            # Second call: success path
            return ok_cm

        provider.client.messages.stream = MagicMock(side_effect=_stream_factory)

        chunks = [c async for c in provider.stream(messages=[Message.user("hi")])]
        # 1 delta + 1 final = 2 chunks (only the retry attempt yields)
        assert len(chunks) == 2
        assert chunks[0].content == "hello"
        assert chunks[-1].is_final is True
        # Two attempts were made
        assert call_count["n"] == 2
        # Retry should have called stream() WITHOUT temperature kwarg.
        second_call_kwargs = provider.client.messages.stream.call_args_list[1].kwargs
        assert "temperature" not in second_call_kwargs

    async def test_non_temperature_bad_request_propagates(self) -> None:
        from the_one.llm.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(model="claude-test", api_key="test-key")

        bad_cm = MagicMock()
        bad_cm.__aenter__ = AsyncMock(side_effect=make_bad_request("Some unrelated 400 reason."))
        bad_cm.__aexit__ = AsyncMock(return_value=False)
        provider.client.messages.stream = MagicMock(return_value=bad_cm)

        with pytest.raises(anthropic.BadRequestError):
            async for _ in provider.stream(messages=[Message.user("hi")]):
                pass


# ---------------------------------------------------------------------------
# Agent.step streaming integration
# ---------------------------------------------------------------------------


class TestAgentStepStreaming:
    async def test_step_uses_streaming_yields_one_message(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={"stream_chunks": ["a", "b"], "delay_ms": 0},
        )
        agent = Agent(llm=provider, tools=ToolRegistry(), system_prompt="sys")
        messages = []
        async for m in agent.step("hi"):
            messages.append(m)
        # Exactly 1 assistant message yielded (synthesized final).
        assert len(messages) == 1
        assert messages[0].role == Role.ASSISTANT
        assert messages[0].content == "ab"

    async def test_step_invokes_on_chunk_per_chunk(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={"stream_chunks": ["a", "b"], "delay_ms": 0},
        )
        agent = Agent(llm=provider, tools=ToolRegistry(), system_prompt="sys")

        seen: list[str] = []

        async def _on_chunk(content: str) -> None:
            seen.append(content)

        async for _ in agent.step("hi", on_chunk=_on_chunk):
            pass
        assert seen == ["a", "b"]

    async def test_step_without_on_chunk_preserves_yield_contract(self) -> None:
        # Default-impl path (no stream_chunks) must still yield exactly one
        # assistant Message with the original complete()-equivalent content.
        provider = MockProvider(
            model="mock-default",
            config={"response": {"content": "default reply"}},
        )
        agent = Agent(llm=provider, tools=ToolRegistry(), system_prompt="sys")
        messages = []
        async for m in agent.step("hi"):
            messages.append(m)
        assert len(messages) == 1
        assert messages[0].content == "default reply"


# ---------------------------------------------------------------------------
# ollama_api.chat_stream SSE parser
# ---------------------------------------------------------------------------


class TestChatStreamSSE:
    async def test_parses_data_lines_and_terminates_on_done(self) -> None:
        sse_lines = [
            'data: {"choices":[{"delta":{"content":"Hi"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":" there"}}]}',
            "",
            'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}',
            "data: [DONE]",
        ]

        stream_resp = AsyncMock()
        stream_resp.status_code = 200
        stream_resp.raise_for_status = MagicMock()
        stream_resp.aiter_lines = lambda: _async_iter_lines(sse_lines)

        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_cm.__aexit__ = AsyncMock(return_value=False)

        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.stream = MagicMock(return_value=stream_cm)

        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            results = []
            async for chunk in ollama_api.chat_stream(
                "http://localhost:11434/v1", {"model": "x", "messages": []}
            ):
                results.append(chunk)

        # 3 data lines (excluding [DONE] terminator) become 3 yielded dicts.
        assert len(results) == 3
        assert results[0]["choices"][0]["delta"]["content"] == "Hi"
        assert results[1]["choices"][0]["delta"]["content"] == " there"
        assert results[2]["usage"]["prompt_tokens"] == 3

    async def test_skips_invalid_json_payload(self) -> None:
        sse_lines = [
            'data: {"choices":[{"delta":{"content":"a"}}]}',
            "data: not valid json",
            "data: [DONE]",
        ]
        stream_resp = AsyncMock()
        stream_resp.status_code = 200
        stream_resp.raise_for_status = MagicMock()
        stream_resp.aiter_lines = lambda: _async_iter_lines(sse_lines)
        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.stream = MagicMock(return_value=stream_cm)

        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            results = [
                c
                async for c in ollama_api.chat_stream(
                    "http://localhost:11434/v1", {"model": "x", "messages": []}
                )
            ]
        # The "not valid json" payload is silently skipped.
        assert len(results) == 1
        assert results[0]["choices"][0]["delta"]["content"] == "a"


# ---------------------------------------------------------------------------
# Multi-iteration chunks_seen invariant (the most subtle bit — leg test #9)
# ---------------------------------------------------------------------------


class _MultiIterLLM(LLMProvider):
    """LLM that streams chunks AND emits a tool_call on iteration 1, then
    streams chunks with no tool_call on iteration 2.

    Exercises the chunks_seen invariant: iteration 1 emits chunks (chunks_seen
    becomes True), then a tool call. The reset-at-end-of-block must take
    chunks_seen back to False so iteration 2's chunks fire `assistant_chunk`
    events without first wrongly emitting a legacy `assistant` event.
    """

    name = "multi-iter"

    def __init__(self) -> None:
        self.iteration = 0

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        # Default implementation never used in this test; stream() is the path.
        return Message.assistant(content="")

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ):
        self.iteration += 1
        if self.iteration == 1:
            # Stream "iter1-" + tool call on final
            yield StreamChunk(content="iter1-", is_final=False)
            tc = ToolCall(id="tc1", name="continue", arguments={"reason": "loop"})
            msg = Message.assistant(
                content="iter1-",
                tool_calls=[tc],
                usage=TokenUsage(input_tokens=0, output_tokens=1),
            )
            yield StreamChunk(
                content="",
                is_final=True,
                tool_calls=[tc],
                usage=msg.usage,
                message=msg,
            )
        else:
            # Iteration 2 — stream chunks, no tool call.
            yield StreamChunk(content="iter2-", is_final=False)
            msg = Message.assistant(
                content="iter2-",
                tool_calls=[],
                usage=TokenUsage(input_tokens=0, output_tokens=1),
            )
            yield StreamChunk(
                content="",
                is_final=True,
                tool_calls=[],
                usage=msg.usage,
                message=msg,
            )


class TestMultiIterationChunksSeenInvariant:
    """The Critical Invariant Test — see leg artifact test #9.

    Asserts the app.py `chunks_seen` flag is reset at end-of-iteration so a
    multi-iteration agent loop emits `assistant_chunk` events on every
    iteration (and skips the legacy `assistant` event on every iteration
    where chunks fired). Previously, resetting inside `if msg.content:`
    skipped the reset on tool-call-only responses; we reset unconditionally
    at the end of the Role.ASSISTANT block.
    """

    async def test_chunks_seen_resets_between_iterations(self) -> None:
        from the_one.interfaces.web.app import _process_and_broadcast

        # Build a fake Session that records emitted events and supplies an
        # Agent backed by _MultiIterLLM.
        agent = Agent(
            llm=_MultiIterLLM(),
            tools=ToolRegistry(),
            system_prompt="sys",
            max_iterations=3,
        )
        session = MagicMock()
        session.id = "sess-1"
        session.agent = agent
        session.add_event = MagicMock()
        # mimic the persistence write
        session.events = []

        emitted: list[dict[str, Any]] = []

        async def _fake_send_to_session(s, event, exclude=None):
            emitted.append(event)

        async def _fake_save(*args, **kwargs):
            pass

        async def _fake_ensure(s):
            pass

        with (
            patch(
                "the_one.interfaces.web.app._send_to_session",
                new=_fake_send_to_session,
            ),
            patch(
                "the_one.interfaces.web.app._save_session_to_db",
                new=_fake_save,
            ),
            patch(
                "the_one.interfaces.web.app._ensure_ollama_model_loaded",
                new=_fake_ensure,
            ),
        ):
            await _process_and_broadcast(session, "go")

        types = [e["type"] for e in emitted]
        # Iteration 1: assistant_chunk("iter1-"), usage event, tool_call
        # Iteration 2: assistant_chunk("iter2-"), usage event
        # Trailing: done
        # Specifically, NO `assistant` event must appear on either iteration —
        # both had chunks (chunks_seen=True for both).
        assert "assistant" not in types, f"Unexpected legacy `assistant` event in stream: {types}"
        assert types.count("assistant_chunk") == 2, (
            f"Expected 2 assistant_chunk events (one per iteration); got: {types}"
        )
        assert types[0] == "user"  # initial echo
        assert types[-1] == "done"
        # Iteration order: chunk -> usage -> tool_call -> chunk -> usage -> done
        chunk_idxs = [i for i, t in enumerate(types) if t == "assistant_chunk"]
        tc_idx = types.index("tool_call")
        assert chunk_idxs[0] < tc_idx < chunk_idxs[1]
