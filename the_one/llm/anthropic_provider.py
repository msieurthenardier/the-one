from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from the_one.llm._schema_sanitize import UnsanitizableToolSchema, sanitize_tool_schema
from the_one.llm.model_catalog import context_window_for
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

logger = logging.getLogger(__name__)

# DD6: Anthropic schema-validation 400s name the offending tool by *index*
# (e.g. "tools.1.custom.input_schema: ..."). This regex pulls that index so
# we can map it to the tool's name in the post-drop ``kwargs["tools"]`` list.
_TOOLS_INDEX_RE = re.compile(r"tools\.(\d+)\.")


def _name_offending_tool(
    exc: anthropic.BadRequestError,
    sent_tools: list[dict[str, Any]] | None,
) -> anthropic.BadRequestError | None:
    """Map a ``tools.N`` schema-400 onto the offending tool's name.

    Returns a new ``anthropic.BadRequestError`` whose message names the tool
    at index ``N`` in ``sent_tools`` (the post-drop list actually sent), or
    ``None`` when no mapping applies (no index in the message, no sent tools,
    or the index is out of range). The new exception reuses the caught
    exception's ``response``/``body`` (required keyword-only args on the SDK),
    so the public exception type stays ``BadRequestError`` and callers
    catching it keep working. The original ``tools.N`` text is quoted intact.
    """
    m = _TOOLS_INDEX_RE.search(str(exc))
    if not m:
        return None
    idx = int(m.group(1))
    if sent_tools and 0 <= idx < len(sent_tools):
        name = sent_tools[idx].get("name", "<unnamed>")
        return anthropic.BadRequestError(
            f"Anthropic rejected tool {name!r}'s input_schema (original error: {exc})",
            response=exc.response,
            body=exc.body,
        )
    return None


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
# The shared threshold (200 bytes) and emitter logic live in
# ``the_one.llm._streaming``; only the per-provider density lives here.
BYTES_PER_TOKEN_ANTHROPIC = 3.7


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
        # Catalog-sourced (M16 F05): replaces the prior no-op that assumed all
        # Claude models share 200k — false now that current models are natively
        # 1M. 200k stays the conservative fallback on a catalog miss. No
        # `context-1m` beta header is sent (DD4 — catalog reports the real window;
        # current Claude models are natively 1M).
        window = context_window_for("anthropic", self.model)
        if window is not None:
            self.max_context_tokens = window
        else:
            logger.warning(
                "anthropic: no catalog context window for model %r; using default %d",
                self.model,
                self.max_context_tokens,
            )

    async def aclose(self) -> None:
        """Release the persistent Anthropic HTTP client.

        F05 L01: ``anthropic.AsyncAnthropic.close()`` is async and
        idempotent — safe to call multiple times.
        """
        await self.client.close()

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
            # DD5: sanitize each tool's input_schema immediately before send;
            # drop (don't crash on) a genuinely-unsanitizable tool with a named
            # warning. The post-drop ``sent_tools`` list is the single source of
            # truth for tool ordering (DD6 maps a ``tools.N`` 400 against it).
            sent_tools = []
            for t in tools:
                try:
                    sent_tools.append(self._to_anthropic_tool(t))
                except UnsanitizableToolSchema as exc:
                    logger.warning(
                        "Dropping tool %r from Anthropic request: unsanitizable input_schema (%s)",
                        t.get("name", "<unnamed>"),
                        exc.reason,
                    )
            if sent_tools:
                kwargs["tools"] = sent_tools
            # else: omit "tools" entirely — never send an empty list (SDK may
            # reject it; omitting is strictly more conservative).
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
            # Ordered checks (load-bearing): (1) temperature retry first
            # (unchanged), (2) tools.N → tool-name mapping (DD6), (3) plain
            # re-raise otherwise.
            if "temperature" in str(exc).lower():
                # Newer Claude models (Opus 4.x, Sonnet 4.x) reject the
                # `temperature` parameter entirely. Retry once without it.
                kwargs.pop("temperature", None)
                try:
                    response = await self.client.messages.create(**kwargs)
                except anthropic.BadRequestError as exc2:
                    # The retry can itself 400 on a tool schema — map it too.
                    named = _name_offending_tool(exc2, kwargs.get("tools"))
                    raise (named or exc2) from exc2
            else:
                named = _name_offending_tool(exc, kwargs.get("tools"))
                raise (named or exc) from exc

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
            # Mirror complete()'s ordered checks: temperature retry first
            # (gated by yielded_any), then tools.N → tool-name (DD6), then
            # plain re-raise. Streaming 400s arrive pre-delta, so the
            # temperature-retry → tools.N sub-path is defence-in-depth.
            if not yielded_any and "temperature" in str(exc).lower():
                kwargs.pop("temperature", None)
                try:
                    async for chunk in self._stream_inner(kwargs):
                        yield chunk
                except anthropic.BadRequestError as exc2:
                    named = _name_offending_tool(exc2, kwargs.get("tools"))
                    raise (named or exc2) from exc2
            else:
                named = _name_offending_tool(exc, kwargs.get("tools"))
                raise (named or exc) from exc

    async def _stream_inner(self, kwargs: dict[str, Any]) -> AsyncIterator[StreamChunk]:
        # F7 L04 / M12 F6 L1: shared byte-emitter for mid-stream usage
        # emission. Anthropic only uses the emitter half of
        # ``_StreamAccumulator`` — tool calls arrive whole via
        # ``get_final_message``, not as streaming deltas. See module-level
        # BYTES_PER_TOKEN_ANTHROPIC docstring for the cycle-1 trade-off.
        acc = _StreamAccumulator(bytes_per_token=BYTES_PER_TOKEN_ANTHROPIC)
        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(content=text, is_final=False)
                if text:
                    interim = acc.maybe_emit_interim(text)
                    if interim:
                        yield interim
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
        # DD1/DD2: normalize the input_schema on a deep copy (the kernel
        # deep-copies internally — the source ``parameters`` is never mutated).
        # ``.get("parameters")`` (not a subscript) so a tool with no parameters
        # key flows to the kernel as None → {"type": "object"}.
        return {
            "name": tool_def["name"],
            "description": tool_def["description"],
            "input_schema": sanitize_tool_schema(tool_def.get("parameters")),
        }

    def _to_api_message(self, msg: Message) -> dict[str, Any]:
        if msg.role == Role.TOOL and msg.tool_result:
            # M11 F8 L2: ``ToolResult.__post_init__`` normalizes non-str
            # content to JSON-str at construction, so ``msg.tool_result.content``
            # is always ``str`` here. The F7 12.l per-encoder coercion is
            # no longer needed — the canonical-shape invariant lives at the
            # dataclass boundary. See ``the_one/agents.md`` →
            # ``provider-shape-portability``.
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
