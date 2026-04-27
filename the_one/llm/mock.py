from __future__ import annotations

import asyncio
from typing import Any

from the_one.llm.base import LLMProvider, Message, TokenUsage, ToolCall
from the_one.llm.registry import register_provider

_DEFAULT_RESPONSE = {"content": "Mock response from the mock provider."}


class MockProvider(LLMProvider):
    """Deterministic LLM provider for tests and offline dev work.

    Responses are sourced from the per-provider ``config`` dict::

        config = {
            "models": ["mock-fast", "mock-thinking"],   # surfaced to /api/providers/{id}/models
            "response": {                               # what complete() returns
                "content": "Hello from mock",
                "tool_calls": [
                    {"id": "1", "name": "tool_a", "arguments": {"x": 1}}
                ]
            }
        }

    If ``response`` is not set, returns a fixed default content.

    Gated at the API layer by ``THE_ONE_DEV_MODE`` — this class itself does
    not check the env var; it trusts that the only callers are paths that
    have already been gated (factory + tests).
    """

    name = "mock"

    def __init__(
        self,
        model: str = "mock-default",
        base_url: str = "",
        api_key: str | None = None,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.config = config or {}

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        # Optional latency simulation. Defaults to 0 so tests stay fast;
        # interactive dev sessions can pass `delay_ms` to exercise the
        # client-side "thinking…" indicator.
        delay_ms = self.config.get("delay_ms", 0)
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)
        response = self.config.get("response", _DEFAULT_RESPONSE)
        content = response.get("content", "")
        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], arguments=tc.get("arguments", {}))
            for tc in response.get("tool_calls", [])
        ]
        return Message.assistant(
            content=content,
            tool_calls=tool_calls,
            usage=TokenUsage(input_tokens=0, output_tokens=len(content.split())),
        )


register_provider("mock", MockProvider)
