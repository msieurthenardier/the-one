from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from the_one.llm.base import LLMProvider, Message, Role, StreamChunk, TokenUsage, ToolCall
from the_one.llm.registry import register_provider


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    max_context_tokens = 200_000

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None, **kwargs: Any):
        self.model = model
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

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
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input)
                )

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
        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(content=text, is_final=False)
            final = await stream.get_final_message()

        content = ""
        tool_calls: list[ToolCall] = []
        for block in final.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input)
                )

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
        return {"role": msg.role.value, "content": msg.content}


register_provider("anthropic", AnthropicProvider)
