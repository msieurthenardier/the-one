from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from the_one.llm.base import (
    LLMProvider,
    Message,
    Role,
    StreamChunk,
    ThinkingBlock,
    TokenUsage,
    ToolCall,
)
from the_one.llm.registry import register_provider

_DEFAULT_RESPONSE = {"content": "Mock response from the mock provider."}


def _thinking_from_response(response: dict[str, Any]) -> list[ThinkingBlock]:
    """M16 F10 L05 dev-mode seam: parse an optional ``response["thinking"]``
    (a list of block dicts, e.g. ``{"type": "thinking", "thinking": "..."}``)
    into ``ThinkingBlock``s on the synthesized assistant Message — mirroring how
    the mock already reads ``response["tool_calls"]``. Lets a browser test drive
    the real thinking-disclosure path end-to-end with no live Anthropic key.
    """
    return [ThinkingBlock(**b) for b in response.get("thinking", [])]


def _selected_response(config: dict[str, Any], messages: list[Message]) -> dict[str, Any]:
    """Pick the scripted response for this request.

    With ``config["responses"]`` (a non-empty list of response dicts), the
    entry is chosen statelessly from the request: its index is the number of
    tool-role messages after the last user message, clamped to the last entry.
    A new user message therefore restarts the script at entry 0. Without
    ``responses`` this is exactly ``config["response"]`` (or the default).
    """
    responses = config.get("responses")
    if responses:
        tool_messages = 0
        for message in reversed(messages):
            if message.role == Role.USER:
                break
            if message.role == Role.TOOL:
                tool_messages += 1
        return responses[min(tool_messages, len(responses) - 1)]
    return config.get("response", _DEFAULT_RESPONSE)


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
            },
            "stream_chunks": ["Hello, ", "world", "!"], # optional; if set, stream() yields each
            "delay_ms": 200,                            # optional; latency between chunks/complete
            "input_tokens": 0,                          # optional; default 0; emitted as the
                                                        # usage input_tokens in complete() and
                                                        # stream(). Set to N>0 in tests that need
                                                        # a meaningful last_usage snapshot (e.g.
                                                        # the M16 F06 L03 round-trip test).
        }

    ``responses`` (optional, a non-empty list of dicts shaped like ``response``)
    scripts a sequence: the entry is chosen statelessly from the request, as the
    number of tool-role messages after the last user message, clamped to the last
    entry (so a new user message restarts at entry 0). With ``stream_chunks`` the
    selected entry's ``tool_calls`` and ``thinking`` ride the final chunk. Absent,
    ``response`` applies unchanged. Dev-mode only by documentation: the provider
    type itself is already dev-mode gated.

    If ``response`` is not set, returns a fixed default content.
    If ``stream_chunks`` is unset/empty, ``stream`` falls back to the default
    one-chunk-equals-complete-output path (mirrors the base class default impl
    but expressed inline for clarity — no async-generator delegation overhead).

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
        # Initialise per-instance provider state (sentinel for lazy resolver).
        # LLMProvider.__init__ cannot be called here because this subclass
        # overrides __init__ to accept model/config; call the extracted helper
        # per the base-class contract (see LLMProvider._init_provider_state
        # docstring at base.py).
        self._init_provider_state()

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        *,
        enable_thinking: bool | None = None,  # M16 F10 L02 (DD5): accepted, ignored.
    ) -> Message:
        # Optional latency simulation. Defaults to 0 so tests stay fast;
        # interactive dev sessions can pass `delay_ms` to exercise the
        # client-side "thinking…" indicator.
        delay_ms = self.config.get("delay_ms", 0)
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)
        response = _selected_response(self.config, messages)
        content = response.get("content", "")
        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], arguments=tc.get("arguments", {}))
            for tc in response.get("tool_calls", [])
        ]
        return Message.assistant(
            content=content,
            tool_calls=tool_calls,
            thinking=_thinking_from_response(response),
            usage=TokenUsage(
                input_tokens=self.config.get("input_tokens", 0),
                output_tokens=len(content.split()),
            ),
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        *,
        enable_thinking: bool | None = None,  # M16 F10 L02 (DD5): accepted, ignored.
    ) -> AsyncIterator[StreamChunk]:
        """Streaming implementation honouring ``config['stream_chunks']``.

        When ``stream_chunks`` is set (non-empty list), yields each chunk with
        ``delay_ms`` between chunks; the final chunk synthesises a Message
        with the accumulated content + the configured ``response.tool_calls``.
        When ``stream_chunks`` is unset/empty, falls back to the default-impl
        path: call ``self.complete()``, yield one final chunk. This mirrors
        the base class default (NOT a ``super().stream(...)`` delegation —
        we inline for clarity).
        """
        stream_chunks = self.config.get("stream_chunks") or []
        if not stream_chunks:
            # Default-impl path: one chunk = full content (mirrors complete()).
            msg = await self.complete(messages, tools, temperature, max_tokens)
            yield StreamChunk(
                content=msg.content,
                is_final=True,
                tool_calls=msg.tool_calls,
                usage=msg.usage,
                message=msg,
            )
            return

        delay_ms = self.config.get("delay_ms", 0)
        response = _selected_response(self.config, messages)
        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], arguments=tc.get("arguments", {}))
            for tc in response.get("tool_calls", [])
        ]
        accumulated = ""
        for i, chunk_text in enumerate(stream_chunks):
            if delay_ms and i > 0:
                await asyncio.sleep(delay_ms / 1000)
            accumulated += chunk_text
            yield StreamChunk(content=chunk_text, is_final=False)

        # Final chunk — synthesize the Message
        usage = TokenUsage(
            input_tokens=self.config.get("input_tokens", 0),
            output_tokens=len(accumulated.split()),
        )
        msg = Message.assistant(
            content=accumulated,
            tool_calls=tool_calls,
            thinking=_thinking_from_response(response),
            usage=usage,
        )
        yield StreamChunk(
            content="",
            is_final=True,
            tool_calls=tool_calls,
            usage=usage,
            message=msg,
        )


register_provider("mock", MockProvider)
