from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
import openai

from the_one.llm._streaming import _StreamAccumulator
from the_one.llm.base import (
    LLMProvider,
    Message,
    Role,
    StreamChunk,
    TokenUsage,
    ToolCall,
    build_user_message_content,
)
from the_one.llm.registry import register_provider

# Default timeout for openai SDK calls. SDK default is 600s, which means a
# stuck upstream model holds the WebSocket open for 10 minutes with no user
# feedback. 300s read covers slow reasoning models without leaving the user
# hanging indefinitely.
DEFAULT_OPENAI_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)


# F7 L04: bytes-per-token for the mid-stream usage byte-heuristic.
# Bytes-per-token average for OpenAI tokenisers (cl100k_base) is ~4.0
# across mixed English+code corpora.  The shared threshold (200 bytes)
# and accumulator logic live in ``the_one.llm._streaming``.
BYTES_PER_TOKEN_OPENAI = 4.0


# M08 F6.5 L01: per-model context-window lookup. OpenAI doesn't expose
# ``context_length`` via the ``/models`` API, so this is hand-maintained.
# Drifts as OpenAI ships new models — unknown models fall back to the
# class default (128k). Match is by PREFIX (longest-prefix wins).
# Canonical reference: https://platform.openai.com/docs/models
# Order doesn't matter for storage but matters for the longest-prefix-wins
# matcher below — explicit variants of ``gpt-4`` / ``gpt-3.5-turbo`` MUST
# appear so prefix-match doesn't collapse them onto the bare ``gpt-4``
# (8k) or ``gpt-3.5-turbo`` (16k) entry.
OPENAI_MODEL_CONTEXT: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4-32k": 32_768,
    "gpt-4-vision-preview": 128_000,
    "gpt-4-0125-preview": 128_000,
    "gpt-4-1106-preview": 128_000,
    "gpt-4": 8_192,  # legacy gpt-4 default; -0613 / -0314 dated variants
    "gpt-3.5-turbo-instruct": 4_096,
    "gpt-3.5-turbo-16k": 16_385,
    "gpt-3.5-turbo": 16_385,  # current gpt-3.5-turbo defaults to 16k (was 4k pre-2023)
    "o1": 200_000,
    "o3-mini": 200_000,
}


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
        **kwargs: Any,
    ):
        # NOTE: any new instance attribute added here MUST also be set in
        # OpenRouterProvider.__init__ (which deliberately does NOT call
        # super().__init__() — see test_instance_attribute_parity).
        super().__init__()
        self.model = model
        client_kwargs: dict[str, Any] = {
            "api_key": api_key or os.environ.get("OPENAI_API_KEY"),
            "timeout": timeout if timeout is not None else DEFAULT_OPENAI_TIMEOUT,
        }
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        self.client = openai.AsyncOpenAI(**client_kwargs)

    async def aclose(self) -> None:
        """Release the persistent OpenAI HTTP client.

        F05 L01: ``openai.AsyncOpenAI`` wraps an ``httpx.AsyncClient``
        whose ``aclose()`` is idempotent — safe to call multiple times.
        """
        await self.client.close()

    async def _resolve_max_context_tokens(self) -> None:
        # Longest-prefix match: sort keys descending by length so e.g.
        # ``gpt-4-turbo`` wins over ``gpt-4`` when ``self.model`` is
        # ``gpt-4-turbo-preview``. Note: ``OpenRouterProvider`` inherits
        # from this class but overrides this resolver — it does NOT use
        # the OpenAI prefix table.
        for prefix in sorted(OPENAI_MODEL_CONTEXT, key=len, reverse=True):
            if self.model.startswith(prefix):
                self.max_context_tokens = OPENAI_MODEL_CONTEXT[prefix]
                return
        # No match — leave at class default.

    def _bytes_per_token_for_interim(self) -> float:
        """F7 L04: provider-specific bytes-per-token for the mid-stream
        byte-heuristic. Subclasses override to swap in their tokeniser's
        average density (OpenRouter routes mostly-OpenAI-compat models so
        inherits the same value; Anthropic/Ollama use their own constants).
        """
        return BYTES_PER_TOKEN_OPENAI

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        await self._resolve_max_context_tokens_if_needed()
        api_messages = [self._to_api_message(m) for m in messages]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = [self.tool_schema(t) for t in tools]

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        usage = None
        if response.usage:
            usage = TokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )

        return Message.assistant(content=msg.content or "", tool_calls=tool_calls, usage=usage)

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        """Native OpenAI streaming via ``chat.completions.create(stream=True)``.

        ``stream_options={"include_usage": True}`` so the final metadata
        chunk carries the ``usage`` payload that the F4 telemetry overlay
        depends on (without it, the chunk after the deltas has empty usage).
        Tool-call deltas are accumulated by index and emitted on the final
        chunk; tool calls remain non-streamed per F4 design.
        """
        await self._resolve_max_context_tokens_if_needed()
        api_messages = [self._to_api_message(m) for m in messages]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = [self.tool_schema(t) for t in tools]

        stream = await self.client.chat.completions.create(**kwargs)

        content = ""
        usage: TokenUsage | None = None
        # F7 L04 / M12 F6 L1: shared accumulator for tool-call deltas and
        # mid-stream interim-usage emission.  ``bytes_per_token`` is resolved
        # at stream-open via ``_bytes_per_token_for_interim()`` so
        # OpenRouterProvider's override (BYTES_PER_TOKEN_OPENROUTER = 4.0)
        # still applies without baking a constant at import time.
        acc = _StreamAccumulator(bytes_per_token=self._bytes_per_token_for_interim())

        async for chunk in stream:
            if not chunk.choices:
                # Final metadata-only chunk with usage (when include_usage=True).
                if getattr(chunk, "usage", None):
                    usage = TokenUsage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                    )
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                content += delta.content
                yield StreamChunk(content=delta.content, is_final=False)
                interim = acc.maybe_emit_interim(delta.content)
                if interim:
                    yield interim
            if getattr(delta, "tool_calls", None):
                for tc_delta in delta.tool_calls:
                    acc.feed_tool_call_delta(
                        index=tc_delta.index,
                        id_str=tc_delta.id or "",
                        name_str=(tc_delta.function.name or "") if tc_delta.function else "",
                        arguments_str=(tc_delta.function.arguments or "")
                        if tc_delta.function
                        else "",
                    )

        tool_calls: list[ToolCall] = [
            ToolCall(id=e["id"], name=e["name"], arguments=e["arguments"])
            for e in acc.finalize_tool_calls()
        ]

        msg = Message.assistant(content=content, tool_calls=tool_calls, usage=usage)
        yield StreamChunk(
            content="",
            is_final=True,
            tool_calls=tool_calls,
            usage=usage,
            message=msg,
        )

    def _to_api_message(self, msg: Message) -> dict[str, Any]:
        if msg.role == Role.TOOL and msg.tool_result:
            return {
                "role": "tool",
                "tool_call_id": msg.tool_result.tool_call_id,
                "content": msg.tool_result.content,
            }
        if msg.role == Role.ASSISTANT and msg.tool_calls:
            return {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        # M11 F7 L4: project peer_name + channel_name as an inline prefix.
        # The helper handles all four absence variants; legacy back-compat
        # is preserved when both fields are None (byte-identical payload).
        # F6 DD §2 audit premise refined: the prefix IS the projection.
        return {"role": msg.role.value, "content": build_user_message_content(msg)}


register_provider("openai", OpenAIProvider)
