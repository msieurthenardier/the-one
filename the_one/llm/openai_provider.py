from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import openai

from the_one.llm.base import LLMProvider, Message, Role, StreamChunk, TokenUsage, ToolCall
from the_one.llm.registry import register_provider


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None, **kwargs: Any):
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
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
        tool_calls_acc: dict[int, dict[str, str]] = {}
        usage: TokenUsage | None = None

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
            if getattr(delta, "tool_calls", None):
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    entry = tool_calls_acc.setdefault(
                        idx, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            entry["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_calls_acc.keys()):
            e = tool_calls_acc[idx]
            try:
                args = json.loads(e["arguments"]) if e["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=e["id"] or e["name"], name=e["name"], arguments=args))

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
        return {"role": msg.role.value, "content": msg.content}


register_provider("openai", OpenAIProvider)
