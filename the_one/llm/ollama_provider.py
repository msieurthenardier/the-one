from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from the_one.llm import ollama_api
from the_one.llm.base import LLMProvider, Message, Role, StreamChunk, TokenUsage, ToolCall
from the_one.llm.registry import register_provider


class OllamaProvider(LLMProvider):
    """Ollama provider using its OpenAI-compatible /v1/chat/completions endpoint.

    Also works with any OpenAI-compatible local server (LM Studio, vLLM, llama.cpp, etc.)
    by setting a custom base_url.
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:11434/v1",
        **kwargs: Any,
    ):
        self.model = model
        self.base_url = ollama_api.ensure_v1(base_url or "http://localhost:11434/v1")

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        api_messages = [self._to_api_message(m) for m in messages]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = [self.tool_schema(t) for t in tools]

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]

        tool_calls = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", tc["function"]["name"]),
                        name=tc["function"]["name"],
                        arguments=args,
                    )
                )

        usage = None
        if "usage" in data:
            u = data["usage"]
            usage = TokenUsage(
                input_tokens=u.get("prompt_tokens", 0),
                output_tokens=u.get("completion_tokens", 0),
            )

        return Message.assistant(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage=usage,
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        """Native Ollama streaming via ``ollama_api.chat_stream`` SSE helper.

        The Ollama OpenAI-compatible endpoint emits the same chunk shape
        as OpenAI: ``choices[0].delta.{content,tool_calls}`` deltas + a
        final metadata chunk with ``usage``. Tool-call deltas are
        accumulated by index and emitted on the final StreamChunk.
        """
        api_messages = [self._to_api_message(m) for m in messages]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream_options": {"include_usage": True},
        }
        if tools:
            body["tools"] = [self.tool_schema(t) for t in tools]

        content = ""
        tool_calls_acc: dict[int, dict[str, str]] = {}
        usage: TokenUsage | None = None

        async for chunk_dict in ollama_api.chat_stream(self.base_url, body):
            choices = chunk_dict.get("choices") or []
            if not choices:
                if "usage" in chunk_dict:
                    u = chunk_dict["usage"]
                    usage = TokenUsage(
                        input_tokens=u.get("prompt_tokens", 0),
                        output_tokens=u.get("completion_tokens", 0),
                    )
                continue
            delta = choices[0].get("delta", {}) or {}
            text = delta.get("content")
            if text:
                content += text
                yield StreamChunk(content=text, is_final=False)
            for tc_delta in delta.get("tool_calls", []) or []:
                idx = tc_delta.get("index", 0)
                entry = tool_calls_acc.setdefault(
                    idx, {"id": "", "name": "", "arguments": ""}
                )
                if tc_delta.get("id"):
                    entry["id"] = tc_delta["id"]
                fn = tc_delta.get("function", {}) or {}
                if fn.get("name"):
                    entry["name"] = fn["name"]
                args = fn.get("arguments")
                if args is not None:
                    if isinstance(args, str):
                        entry["arguments"] += args
                    else:
                        # Ollama may emit arguments as a dict directly; serialise.
                        entry["arguments"] += json.dumps(args)
            # Some Ollama responses surface usage on the last data line that
            # ALSO carries choices (rather than a metadata-only trailer).
            if "usage" in chunk_dict and usage is None:
                u = chunk_dict["usage"]
                usage = TokenUsage(
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                )

        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_calls_acc.keys()):
            e = tool_calls_acc[idx]
            try:
                args_obj = json.loads(e["arguments"]) if e["arguments"] else {}
            except json.JSONDecodeError:
                args_obj = {}
            tool_calls.append(
                ToolCall(id=e["id"] or e["name"], name=e["name"], arguments=args_obj)
            )

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


register_provider("ollama", OllamaProvider)
