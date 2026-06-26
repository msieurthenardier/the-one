"""Native /api/chat generation path for real Ollama (M16 — num_ctx fix follow-up).

Real Ollama (provider type "ollama", ``native_api=True``) must generate via the
NATIVE ``/api/chat`` endpoint so ``options.num_ctx`` is honoured — the /v1
endpoint pins the runner at 4096 and kills long conversations. OpenAI-compatible
back-ends (``native_api=False``, the default) MUST stay on /v1.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from the_one.llm.base import Message
from the_one.llm.ollama_provider import OllamaProvider


def _native_provider(num_ctx: int | None = 32_768) -> OllamaProvider:
    """A native provider with context resolution pre-satisfied (no network)."""
    p = OllamaProvider(model="ministral-3:8b", base_url="http://localhost:11434", native_api=True)
    p._max_context_tokens_resolved = True
    p._runtime_num_ctx = num_ctx
    return p


async def _native_stream(chunks: list[dict[str, Any]]):
    for c in chunks:
        yield c


class TestNativeGating:
    def test_default_is_openai_compatible(self) -> None:
        # Default construction (e.g. type "openai-compatible") stays on /v1.
        assert OllamaProvider(model="m").native_api is False

    @pytest.mark.asyncio
    async def test_non_native_uses_v1_not_native(self) -> None:
        p = OllamaProvider(model="m", base_url="http://localhost:11434")
        p._max_context_tokens_resolved = True
        with (
            patch.object(p, "supports_tools", AsyncMock(return_value=True)),
            patch(
                "the_one.llm.ollama_api.chat_stream",
                return_value=_native_stream(
                    [
                        {"choices": [{"delta": {"content": "hi"}}]},
                        {
                            "choices": [{"delta": {}}],
                        },
                    ]
                ),
            ) as v1,
            patch("the_one.llm.ollama_api.chat_stream_native") as native,
        ):
            async for _ in p.stream(messages=[Message.user("hi")]):
                pass
        assert v1.called
        assert not native.called


class TestNativeStream:
    @pytest.mark.asyncio
    async def test_streams_content_and_usage_and_sends_num_ctx(self) -> None:
        p = _native_provider(32_768)
        captured: dict[str, Any] = {}

        def _fake(base_url, body, headers=None):
            captured["body"] = body
            return _native_stream(
                [
                    {"message": {"content": "Hel"}, "done": False},
                    {"message": {"content": "lo"}, "done": False},
                    {
                        "message": {"content": ""},
                        "done": True,
                        "prompt_eval_count": 12,
                        "eval_count": 3,
                    },
                ]
            )

        with (
            patch.object(p, "supports_tools", AsyncMock(return_value=True)),
            patch("the_one.llm.ollama_api.chat_stream_native", side_effect=_fake),
        ):
            text = ""
            final = None
            async for c in p.stream(messages=[Message.user("hi")]):
                if c.content:
                    text += c.content
                if c.is_final:
                    final = c

        assert text == "Hello"
        assert final is not None and final.usage is not None
        assert (final.usage.input_tokens, final.usage.output_tokens) == (12, 3)
        # The whole point: num_ctx is sent on the native request.
        assert captured["body"]["options"]["num_ctx"] == 32_768

    @pytest.mark.asyncio
    async def test_parses_native_tool_calls(self) -> None:
        p = _native_provider()
        chunks = [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_x",
                            "function": {"name": "get_weather", "arguments": {"city": "Paris"}},
                        }
                    ],
                },
                "done": False,
            },
            {"message": {"content": ""}, "done": True, "prompt_eval_count": 9, "eval_count": 5},
        ]
        with (
            patch.object(p, "supports_tools", AsyncMock(return_value=True)),
            patch("the_one.llm.ollama_api.chat_stream_native", return_value=_native_stream(chunks)),
        ):
            final = None
            async for c in p.stream(messages=[Message.user("weather?")]):
                if c.is_final:
                    final = c
        assert final is not None
        assert len(final.tool_calls) == 1
        tc = final.tool_calls[0]
        assert tc.name == "get_weather"
        assert tc.arguments == {"city": "Paris"}  # object, not a JSON string
        assert tc.id == "call_x"

    @pytest.mark.asyncio
    async def test_num_ctx_omitted_when_unknown(self) -> None:
        p = _native_provider(num_ctx=None)
        captured: dict[str, Any] = {}

        def _fake(base_url, body, headers=None):
            captured["body"] = body
            return _native_stream([{"message": {"content": "x"}, "done": True}])

        with (
            patch.object(p, "supports_tools", AsyncMock(return_value=True)),
            patch("the_one.llm.ollama_api.chat_stream_native", side_effect=_fake),
        ):
            async for _ in p.stream(messages=[Message.user("hi")]):
                pass
        assert "num_ctx" not in captured["body"]["options"]


class TestNativeComplete:
    @pytest.mark.asyncio
    async def test_complete_parses_message_and_usage(self) -> None:
        p = _native_provider()
        resp = {
            "message": {"role": "assistant", "content": "done"},
            "done": True,
            "prompt_eval_count": 20,
            "eval_count": 4,
        }
        with (
            patch.object(p, "supports_tools", AsyncMock(return_value=True)),
            patch("the_one.llm.ollama_api.chat_native", AsyncMock(return_value=resp)),
        ):
            msg = await p.complete(messages=[Message.user("hi")])
        assert msg.content == "done"
        assert msg.usage is not None
        assert (msg.usage.input_tokens, msg.usage.output_tokens) == (20, 4)


class TestNativeMessageProjection:
    def test_tool_result_has_no_tool_call_id(self) -> None:
        p = _native_provider()
        from the_one.llm.base import ToolResult

        m = Message.tool(ToolResult(tool_call_id="abc", content="result body"))
        native = p._to_native_message(m)
        assert native == {"role": "tool", "content": "result body"}
        assert "tool_call_id" not in native

    def test_assistant_tool_call_arguments_are_objects(self) -> None:
        p = _native_provider()
        from the_one.llm.base import ToolCall

        m = Message.assistant(
            content="", tool_calls=[ToolCall(id="i", name="f", arguments={"a": 1})]
        )
        native = p._to_native_message(m)
        assert native["tool_calls"][0]["function"]["arguments"] == {"a": 1}
        # Native shape: no top-level id/type, args not JSON-encoded.
        assert "id" not in native["tool_calls"][0]
