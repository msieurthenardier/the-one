from __future__ import annotations

import json
from typing import Any

import httpx

from the_one.llm.base import LLMProvider, Message, Role, TokenUsage, ToolCall
from the_one.llm.registry import register_provider


class OllamaProvider(LLMProvider):
    """Ollama provider using its OpenAI-compatible /v1/chat/completions endpoint.

    Also works with any OpenAI-compatible local server (LM Studio, vLLM, llama.cpp, etc.)
    by setting a custom base_url.
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434/v1",
        **kwargs: Any,
    ):
        self.model = model
        url = (base_url or "http://localhost:11434/v1").rstrip("/")
        # Ensure /v1 suffix for OpenAI-compatible endpoint
        if not url.endswith("/v1"):
            url = f"{url}/v1"
        self.base_url = url

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
