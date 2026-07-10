from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
import openai

from the_one.llm._request_params import (
    _coerce_effort,
    _coerce_response_format,
    _coerce_stop,
    resolve_reasoning_effort,
    resolve_response_format,
    resolve_stop,
)
from the_one.llm._streaming import _StreamAccumulator
from the_one.llm.base import (
    ContentBlock,
    ImageContent,
    LLMProvider,
    Message,
    Role,
    StreamChunk,
    TextContent,
    TokenUsage,
    ToolCall,
    build_user_message_content,
)
from the_one.llm.model_catalog import context_window_for
from the_one.llm.registry import register_provider

logger = logging.getLogger(__name__)

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


class OpenAIProvider(LLMProvider):
    name = "openai"
    # M16 F08 L01: explicit (equals the base 4.0 default; OpenRouter inherits).
    bytes_per_token = BYTES_PER_TOKEN_OPENAI

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
        self._read_a4_config(kwargs.get("config"))

    def _read_a4_config(self, config: Any) -> None:
        """Read the A4 request params (reasoning_effort / response_format / stop)
        from the free-form provider ``config`` into canonical-or-None instance
        attrs. Called from BOTH OpenAIProvider.__init__ and (because it skips
        super().__init__) OpenRouterProvider.__init__ — keeps the instance-attr
        parity contract (test_subclass_has_all_parent_instance_attrs) satisfied."""
        _cfg = config if isinstance(config, dict) else {}
        self._reasoning_effort_config = _coerce_effort(_cfg.get("reasoning_effort"))
        self._response_format_config = _coerce_response_format(_cfg.get("response_format"))
        self._stop_config = _coerce_stop(_cfg.get("stop"))

    def _a4_request_kwargs(self) -> dict[str, Any]:
        """A4 request-kwargs addition, native OpenAI shapes (Wire-Format Premise,
        flight-log.md): ``stop``->``stop``, effort->``reasoning_effort``,
        json_object passthrough, json_schema re-wrapped with a required ``name``
        (caller-supplied or synthesized ``"response"``). Returns ``{}`` when
        nothing is configured."""
        out: dict[str, Any] = {}
        stop = resolve_stop(self._stop_config)
        if stop:
            out["stop"] = stop
        effort = resolve_reasoning_effort(self._reasoning_effort_config)
        if effort:
            out["reasoning_effort"] = effort
        rf = resolve_response_format(self._response_format_config)
        if rf:
            if rf.get("type") == "json_object":
                out["response_format"] = {"type": "json_object"}
            elif rf.get("type") == "json_schema" and rf.get("schema") is not None:
                out["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": rf.get("name") or "response", "schema": rf["schema"]},
                }
        return out

    async def aclose(self) -> None:
        """Release the persistent OpenAI HTTP client.

        F05 L01: ``openai.AsyncOpenAI`` wraps an ``httpx.AsyncClient``
        whose ``aclose()`` is idempotent — safe to call multiple times.
        """
        await self.client.close()

    async def _resolve_max_context_tokens(self) -> None:
        # Catalog-sourced (M16 F05 L03): replaces the OPENAI_MODEL_CONTEXT prefix
        # table. OpenRouterProvider overrides this method and is unaffected.
        window = context_window_for("openai", self.model)
        if window is not None:
            self.max_context_tokens = window
        else:
            logger.warning(
                "openai: no catalog context window for model %r; using default %d",
                self.model,
                self.max_context_tokens,
            )

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        *,
        enable_thinking: bool | None = None,  # M16 F10 L02 (DD5): accepted, ignored.
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
        kwargs.update(self._a4_request_kwargs())

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
        *,
        enable_thinking: bool | None = None,  # M16 F10 L02 (DD5): accepted, ignored.
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
        kwargs.update(self._a4_request_kwargs())

        stream = await self.client.chat.completions.create(**kwargs)

        content = ""
        usage: TokenUsage | None = None
        # F7 L04 / M12 F6 L1: shared accumulator for tool-call deltas and
        # mid-stream interim-usage emission.  M16 F08 L01 (MEDIUM-1): the
        # bytes-per-token value now comes from the SINGLE public
        # ``self.bytes_per_token`` accessor (the governor reads the same one),
        # so OpenRouter's override (BYTES_PER_TOKEN_OPENROUTER = 4.0) still
        # applies without a parallel ``_bytes_per_token_for_interim`` that can
        # drift.
        acc = _StreamAccumulator(bytes_per_token=self.bytes_per_token)

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
        # M16 F12 L05 (DD4): build_user_message_content is now shape-aware
        # (str | list[ContentBlock]) and IS called on every USER/SYSTEM turn.
        # The str path below is byte-identical to before; the list path
        # (multimodal — images, plus the DD4 prefix TextContent) maps each
        # block to an OpenAI content part via _content_block_to_api.
        projected = build_user_message_content(msg)
        if isinstance(projected, list):
            return {
                "role": msg.role.value,
                "content": [self._content_block_to_api(b) for b in projected],
            }
        return {"role": msg.role.value, "content": projected}

    def _content_block_to_api(self, b: ContentBlock) -> dict[str, Any]:
        # M16 F12 L05 (DD4/DD5): map a single ContentBlock to an OpenAI
        # content part. TextContent -> {type:text}; ImageContent ->
        # {type:image_url, image_url:{url}}, preferring a base64 data: URI
        # (DD5 universal path) over a plain url when both are set.
        #
        # Forward-note: this is the identical OpenAI-compat mapping Ollama
        # /v1 needs (L06) — lift to a shared `to_openai_compat_content`
        # helper at rule-of-three (A4 precedent); L07's conformance matrix
        # asserts OpenAI and Ollama-/v1 emit identical shapes in the meantime.
        if isinstance(b, TextContent):
            return {"type": "text", "text": b.text}
        assert isinstance(b, ImageContent)
        url = f"data:{b.media_type};base64,{b.data}" if b.data is not None else b.url
        return {"type": "image_url", "image_url": {"url": url}}


register_provider("openai", OpenAIProvider)
