from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import anthropic

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

# F7 L04: bytes-per-token for the mid-stream usage byte-heuristic.
# Anthropic's high-level ``client.messages.stream()`` context manager +
# ``stream.text_stream`` iterator (used in ``_stream_inner`` below) does
# NOT expose ``RawMessageDeltaEvent`` payloads with real interim usage;
# refactoring to raw-event iteration is too invasive for L04. Cycle-1
# decision: apply the byte heuristic uniformly across all providers and
# accept estimate-not-truth interim values for Anthropic during L04. A
# future flight can swap in raw-event iteration if higher fidelity is
# needed. 3.7 reflects Anthropic's tokeniser density (slightly denser
# than OpenAI's cl100k_base on English+code mixtures).
BYTES_PER_TOKEN_ANTHROPIC = 3.7
INTERIM_USAGE_BYTE_THRESHOLD_ANTHROPIC = 200


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    max_context_tokens = 200_000

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None, **kwargs: Any):
        super().__init__()
        self.model = model
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    async def _resolve_max_context_tokens(self) -> None:
        """No-op: all current Claude models share the 200k context window.

        Anthropic's Claude 3.5 (Sonnet/Haiku/Opus) and Claude 4.x family
        all have ``max_context_tokens = 200_000`` (matches the class-level
        default at line 28). When/if Anthropic ships a model with a
        different context window, populate ``self.max_context_tokens``
        here via a model-name table — mirror the pattern in
        ``the_one/llm/openai_provider.py``'s ``OPENAI_MODEL_CONTEXT``
        (or, if Anthropic exposes per-model metadata via the SDK, prefer
        a live lookup, mirroring ``openrouter_provider.py``).

        M08 F7 L05 (F6.5 debrief AI #2): explicit no-op replaces the
        prior implicit default-via-no-override pattern. Makes intent
        legible to future maintainers and gives them an obvious place
        to plug in a per-model table the day Anthropic ships a Claude
        model with a non-200k context window.
        """
        # Intentional no-op — see docstring.

    def _build_kwargs(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        system_prompt = ""
        api_messages = []
        for m in messages:
            if m.role == Role.SYSTEM:
                system_prompt = m.content
            else:
                api_messages.append(self._to_api_message(m))

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [self._to_anthropic_tool(t) for t in tools]
        return kwargs

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        await self._resolve_max_context_tokens_if_needed()
        kwargs = self._build_kwargs(messages, tools, temperature, max_tokens)

        try:
            response = await self.client.messages.create(**kwargs)
        except anthropic.BadRequestError as exc:
            # Newer Claude models (Opus 4.x, Sonnet 4.x) reject the
            # `temperature` parameter entirely. Retry once without it.
            if "temperature" in str(exc).lower():
                kwargs.pop("temperature", None)
                response = await self.client.messages.create(**kwargs)
            else:
                raise

        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

        usage = None
        if response.usage:
            usage = TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        return Message.assistant(content=content, tool_calls=tool_calls, usage=usage)

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        """Native Anthropic streaming via ``client.messages.stream``.

        Ports the F3 ``BadRequestError`` temperature-retry from ``complete()``.
        The retry is gated by ``yielded_any``: once any chunk has been
        emitted, retrying would duplicate output to the consumer. In
        practice, Anthropic raises BadRequestError on request submission
        (before any text deltas), so the gate is defence-in-depth.
        """
        await self._resolve_max_context_tokens_if_needed()
        kwargs = self._build_kwargs(messages, tools, temperature, max_tokens)
        yielded_any = False
        try:
            async for chunk in self._stream_inner(kwargs):
                yielded_any = True
                yield chunk
        except anthropic.BadRequestError as exc:
            if not yielded_any and "temperature" in str(exc).lower():
                kwargs.pop("temperature", None)
                async for chunk in self._stream_inner(kwargs):
                    yield chunk
            else:
                raise

    async def _stream_inner(self, kwargs: dict[str, Any]) -> AsyncIterator[StreamChunk]:
        # F7 L04: cumulative byte accumulator for mid-stream usage
        # emission. Anthropic-specific bytes-per-token; same threshold and
        # last-emitted-bytes pattern as OpenAI/Ollama. See module-level
        # BYTES_PER_TOKEN_ANTHROPIC docstring for the cycle-1 trade-off.
        accumulated_bytes = 0
        last_emitted_bytes = 0
        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(content=text, is_final=False)
                if text:
                    accumulated_bytes += len(text.encode("utf-8"))
                    if (
                        accumulated_bytes - last_emitted_bytes
                        >= INTERIM_USAGE_BYTE_THRESHOLD_ANTHROPIC
                    ):
                        yield StreamChunk(
                            content="",
                            is_final=False,
                            usage=TokenUsage(
                                input_tokens=0,
                                output_tokens=int(accumulated_bytes / BYTES_PER_TOKEN_ANTHROPIC),
                            ),
                        )
                        last_emitted_bytes = accumulated_bytes
            final = await stream.get_final_message()

        content = ""
        tool_calls: list[ToolCall] = []
        for block in final.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

        usage = None
        if final.usage:
            usage = TokenUsage(
                input_tokens=final.usage.input_tokens,
                output_tokens=final.usage.output_tokens,
            )

        msg = Message.assistant(content=content, tool_calls=tool_calls, usage=usage)
        yield StreamChunk(
            content="",
            is_final=True,
            tool_calls=tool_calls,
            usage=usage,
            message=msg,
        )

    def _to_anthropic_tool(self, tool_def: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": tool_def["name"],
            "description": tool_def["description"],
            "input_schema": tool_def["parameters"],
        }

    def _to_api_message(self, msg: Message) -> dict[str, Any]:
        if msg.role == Role.TOOL and msg.tool_result:
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_result.tool_call_id,
                        "content": msg.tool_result.content,
                        "is_error": msg.tool_result.is_error,
                    }
                ],
            }
        if msg.role == Role.ASSISTANT and msg.tool_calls:
            content: list[dict[str, Any]] = []
            if msg.content:
                content.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                )
            return {"role": "assistant", "content": content}
        # M11 F7 L4: project peer_name + channel_name as an inline prefix.
        # The helper handles all four absence variants; legacy back-compat
        # is preserved when both fields are None (byte-identical payload).
        # F6 DD §2 audit premise refined: the prefix IS the projection.
        # L4 contract: this branch passes through a string content; future
        # vision/multimodal would route via a separate content-list branch
        # and would NOT call build_user_message_content (it would build the
        # projection per content-block, or fall back to a different shape
        # per DD §5's divert criterion).
        return {"role": msg.role.value, "content": build_user_message_content(msg)}


register_provider("anthropic", AnthropicProvider)
