from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from the_one.llm._request_params import (
    _coerce_effort,
    _coerce_response_format,
    _coerce_stop,
    resolve_reasoning_effort,
    resolve_response_format,
    resolve_stop,
)
from the_one.llm._schema_sanitize import UnsanitizableToolSchema, sanitize_tool_schema
from the_one.llm._streaming import _StreamAccumulator
from the_one.llm.base import (
    ContentBlock,
    ImageContent,
    LLMProvider,
    Message,
    Role,
    StreamChunk,
    TextContent,
    ThinkingBlock,
    TokenUsage,
    ToolCall,
    build_user_message_content,
)
from the_one.llm.model_catalog import context_window_for
from the_one.llm.registry import register_provider

logger = logging.getLogger(__name__)

# DD6: Anthropic schema-validation 400s name the offending tool by *index*
# (e.g. "tools.1.custom.input_schema: ..."). This regex pulls that index so
# we can map it to the tool's name in the post-drop ``kwargs["tools"]`` list.
_TOOLS_INDEX_RE = re.compile(r"tools\.(\d+)\.")

# Squawk 0009: a drifted/out-of-range anthropic SDK can drop a sampling kwarg
# (e.g. ``temperature``) from ``messages.create``/``messages.stream``, raising a
# ``TypeError: ... got an unexpected keyword argument '<name>'`` at call time
# (before any 400 / any stream delta). This pulls the offending parameter name so
# the provider can strip it and retry once, degrading gracefully rather than
# crashing the first chat turn on a frozen build that shipped an untested SDK.
_UNEXPECTED_KWARG_RE = re.compile(r"unexpected keyword argument '([^']+)'")


# Sortie 14 DD1: prompt caching. One constant feeds BOTH markers (the system block
# and the top-level automatic breakpoint) so their TTLs can never differ -
# Anthropic 400s a longer-TTL entry that comes after a shorter one. Copied per
# request so no caller can mutate the shared dict.
_CACHE_CONTROL: dict[str, str] = {"type": "ephemeral"}


def _cache_int(value: Any) -> int:
    """A cache count counts only when it is a real ``int``; None, missing or a test
    ``MagicMock`` count as 0 (sortie 14 DD2)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _usage_from_sdk(u: Any) -> TokenUsage:
    """Map an SDK ``usage`` to ``TokenUsage`` (sortie 14 DD2).

    With caching on, the SDK's ``input_tokens`` is only the uncached remainder, so
    ``TokenUsage.input_tokens`` (the whole prompt, as every consumer reads it) is
    ``input + cache_creation + cache_read``. When both cache counts are 0 the SDK's
    raw ``input_tokens`` object is returned unchanged.
    """
    write = _cache_int(getattr(u, "cache_creation_input_tokens", None))
    read = _cache_int(getattr(u, "cache_read_input_tokens", None))
    raw_input = u.input_tokens
    if write == 0 and read == 0:
        return TokenUsage(input_tokens=raw_input, output_tokens=u.output_tokens)
    return TokenUsage(
        input_tokens=_cache_int(raw_input) + write + read,
        output_tokens=u.output_tokens,
        cache_read_tokens=read,
        cache_write_tokens=write,
    )


def _unexpected_kwarg_name(exc: TypeError) -> str | None:
    """Extract the parameter name from an ``unexpected keyword argument '<name>'``
    ``TypeError`` message, or ``None`` when the message doesn't match that shape."""
    m = _UNEXPECTED_KWARG_RE.search(str(exc))
    return m.group(1) if m else None


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


# M16 F10 L03 (adaptive pivot): extended-thinking on/off resolver. Sonnet 4.6+
# reject the Leg 02 per-token budget wire format (400); ``thinking:
# {"type": "adaptive"}`` is the correct on-mode. The per-provider config surface
# is now a BOOLEAN (``config["thinking_enabled"]``, the exact key Leg 06's admin
# toggle writes), coerced leniently from a free-form JSON/env value. ``effort``
# is deferred to A4.
_EXTENDED_THINKING_ENV = "THE_ONE_ANTHROPIC_EXTENDED_THINKING"


def _coerce_bool(value: Any) -> bool | None:
    """Coerce a free-form config/env value to bool, or None when unset/unrecognized.

    Handles real bools, ints, and the common string encodings a JSON config
    round-trip or an env var produces. None (unset) lets the resolver fall
    through.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):  # bool already handled above
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
        return None
    return None


def resolve_extended_thinking(configured: bool | None) -> bool:
    """Precedence: per-provider config → env THE_ONE_ANTHROPIC_EXTENDED_THINKING → default False."""
    if configured is not None:
        return configured
    env = _coerce_bool(os.environ.get(_EXTENDED_THINKING_ENV))
    return env if env is not None else False


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
    # M16 F08 L01 (MEDIUM-1): single public accessor (the governor + the
    # stream accumulator both read this), replacing the bare module-constant
    # passed only into ``_StreamAccumulator``.
    bytes_per_token = BYTES_PER_TOKEN_ANTHROPIC

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None, **kwargs: Any):
        super().__init__()
        self.model = model
        self.client = self._build_client(api_key)
        # M16 F10 L03 (adaptive pivot): per-provider extended-thinking on/off,
        # read from the free-form ``config`` dict (``config["thinking_enabled"]``
        # — the exact key Leg 06's admin toggle writes). Coerced to ``bool | None``
        # so a stray value can't crash generation; ``None`` (absent/non-dict/junk)
        # falls through to env → default off in ``resolve_extended_thinking``.
        config = kwargs.get("config")
        self._thinking_enabled_config: bool | None = (
            _coerce_bool(config.get("thinking_enabled")) if isinstance(config, dict) else None
        )
        # M16 F11 L02 (A4): the three cross-provider request params, coerced
        # here (canonical-or-None) and resolved (config → env → default) at
        # each ``_build_kwargs`` call — mirrors the ``_thinking_enabled_config``
        # read above.
        _cfg = config if isinstance(config, dict) else {}
        self._reasoning_effort_config = _coerce_effort(_cfg.get("reasoning_effort"))
        self._response_format_config = _coerce_response_format(_cfg.get("response_format"))
        self._stop_config = _coerce_stop(_cfg.get("stop"))
        # Sortie 14 DD5: set on the first cache_control refusal; this instance then
        # stops adding cache markers. Never persisted - a rebuilt agent tries again.
        self._cache_disabled = False

    def _build_client(self, api_key: str | None) -> anthropic.AsyncAnthropic:
        """Construct the SDK client. Seam for subclasses (M19 F01 DD-4):
        ``AnthropicPlanProvider`` overrides this to build a bearer-token
        (``auth_token``) client with the OAuth beta header instead of the
        ``x-api-key`` client below. Behavior-preserving extraction — the
        body is byte-identical to the previous inline construction."""
        return anthropic.AsyncAnthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    async def _before_request(self) -> None:
        """Pre-request hook, awaited at the top of ``complete()`` and ``stream()``.

        M19 F01 DD-4: a deliberate no-op here — the API-key provider's
        behavior is unchanged. ``AnthropicPlanProvider`` overrides this to
        ensure a fresh OAuth access token before every request. The hook
        exists because the SDK client is built eagerly in a sync
        ``__init__`` (no seam to ``await`` a refresh) and the only other
        async pre-call hook (``_resolve_max_context_tokens_if_needed``)
        swallows all exceptions, which would silently eat the typed
        re-auth-required error.

        Note: ``stream()`` is an async generator, so for streaming this
        hook runs at FIRST ITERATION (generators execute lazily) and any
        error it raises surfaces during iteration — that is the intended
        contract; do not convert ``stream()`` to an eager coroutine.
        """
        return None

    async def _resolve_max_context_tokens(self) -> None:
        # Catalog-sourced (M16 F05): replaces the prior no-op that assumed all
        # Claude models share 200k — false now that current models are natively
        # 1M. 200k stays the conservative fallback on a catalog miss. No
        # `context-1m` beta header is sent (DD4 — catalog reports the real window;
        # current Claude models are natively 1M).
        window = context_window_for("anthropic", self.model)
        if window is not None:
            self.max_context_tokens = window
            self.context_window_known = True
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
        enable_thinking: bool | None = None,
    ) -> dict[str, Any]:
        # M16 F10 L03 (adaptive pivot): resolve thinking on/off ONCE, before the
        # message loop. Hoisted so Leg 04 can thread ``thinking_active`` into
        # ``_to_api_message`` for reasoning replay (DD8) and set enablement below.
        thinking_active = (
            resolve_extended_thinking(self._thinking_enabled_config)
            and enable_thinking is not False
        )
        system_prompt = ""
        api_messages = []
        for m in messages:
            if m.role == Role.SYSTEM:
                system_prompt = m.content
            else:
                api_messages.append(self._to_api_message(m, thinking_active))

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            if self._cache_disabled:
                kwargs["system"] = system_prompt
            else:
                # DD1: render order is tools -> system -> messages, so this marker
                # caches the tool schemas and the system prompt together.
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": dict(_CACHE_CONTROL),
                    }
                ]
        if not self._cache_disabled:
            # DD1: top-level automatic caching follows the end of the conversation.
            kwargs["cache_control"] = dict(_CACHE_CONTROL)
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

        # M16 F10 L03 (adaptive pivot): single enforcement site for extended
        # thinking. Adaptive-only — Sonnet 4.6+ reject the Leg 02 per-token budget
        # wire format (400); ``adaptive`` is the on-mode. No temperature/max_tokens
        # forcing: adaptive has no token budget to leave headroom above, and newer
        # models reject the ``temperature`` parameter anyway (the existing
        # temperature-retry at ``complete``/``stream`` handles that). ``effort``
        # deferred to A4.
        if thinking_active:
            # DD3: request "summarized" display explicitly. On Sonnet 5,
            # Opus 4.8/4.7, and Fable 5, ``thinking.display`` DEFAULTS to
            # "omitted" — the API returns thinking blocks with an EMPTY
            # ``thinking`` text field (only ``signature`` populated, for replay),
            # so the web-UI reasoning disclosure has nothing to show. Setting
            # "summarized" surfaces readable reasoning text. The ``signature`` is
            # identical across display modes, so replay/capture are unaffected.
            # No per-model branching: "summarized" is valid on all adaptive
            # models; on Opus 4.6 / Sonnet 4.6 it's already the default and
            # setting it explicitly is harmless.
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}

        # M16 F11 L02 (A4): stop / reasoning_effort / structured output from
        # config surface. Independent top-level params — compose alongside
        # `thinking` above, don't replace it (Wire-Format Premise, flight-log).
        stop = resolve_stop(self._stop_config)
        if stop:
            kwargs["stop_sequences"] = stop
        output_config: dict[str, Any] = {}
        effort = resolve_reasoning_effort(self._reasoning_effort_config)
        if effort:
            output_config["effort"] = effort
        rf = resolve_response_format(self._response_format_config)
        if rf:
            if rf.get("type") == "json_schema" and rf.get("schema") is not None:
                output_config["format"] = {"type": "json_schema", "schema": rf["schema"]}
            else:
                logger.warning(
                    "anthropic: response_format %r has no Anthropic surface "
                    "(structured output is json_schema-only); ignoring.",
                    rf.get("type"),
                )
        if output_config:
            kwargs["output_config"] = output_config
        return kwargs

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        *,
        enable_thinking: bool | None = None,
    ) -> Message:
        await self._before_request()
        await self._resolve_max_context_tokens_if_needed()
        kwargs = self._build_kwargs(messages, tools, temperature, max_tokens, enable_thinking)

        # Sortie 14 DD5: a bounded attempt loop. Each strip (temperature, a named
        # unexpected kwarg, the cache markers) removes its key and re-runs the whole
        # attempt; a strip fires only while its key is still in kwargs, so a repeat
        # failure naming an already-stripped key falls through to the re-raise.
        while True:
            try:
                response = await self.client.messages.create(**kwargs)
                break
            except anthropic.BadRequestError as exc:
                if self._strip_for_bad_request(exc, kwargs):
                    continue
                # tools.N -> tool-name mapping (DD6), else plain re-raise.
                named = _name_offending_tool(exc, kwargs.get("tools"))
                raise (named or exc) from exc
            except TypeError as exc:
                if self._strip_for_type_error(exc, kwargs):
                    continue
                raise

        content = ""
        tool_calls = []
        # M16 F10 L02 (DD1/DD2): capture signed thinking / redacted_thinking
        # blocks in content order (Anthropic emits thinking before tool_use;
        # Leg 04 replay preserves that ordering on the next request).
        thinking_blocks: list[ThinkingBlock] = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
            elif block.type == "thinking":
                thinking_blocks.append(
                    ThinkingBlock(
                        type="thinking",
                        thinking=block.thinking,
                        signature=block.signature,
                    )
                )
            elif block.type == "redacted_thinking":
                thinking_blocks.append(ThinkingBlock(type="redacted_thinking", data=block.data))

        usage = None
        if response.usage:
            usage = _usage_from_sdk(response.usage)

        return Message.assistant(
            content=content, tool_calls=tool_calls, usage=usage, thinking=thinking_blocks
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
        *,
        enable_thinking: bool | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Native Anthropic streaming via ``client.messages.stream``.

        Ports the F3 ``BadRequestError`` temperature-retry from ``complete()``.
        The retry is gated by ``yielded_any``: once any chunk has been
        emitted, retrying would duplicate output to the consumer. In
        practice, Anthropic raises BadRequestError on request submission
        (before any text deltas), so the gate is defence-in-depth.
        """
        await self._before_request()
        await self._resolve_max_context_tokens_if_needed()
        kwargs = self._build_kwargs(messages, tools, temperature, max_tokens, enable_thinking)
        yielded_any = False
        # Sortie 14 DD5: same bounded strip loop as complete(), gated by
        # yielded_any - once a chunk has been emitted a retry would duplicate
        # output, so the failure goes straight to the tools.N mapping / re-raise.
        while True:
            try:
                async for chunk in self._stream_inner(kwargs):
                    yielded_any = True
                    yield chunk
                return
            except anthropic.BadRequestError as exc:
                if not yielded_any and self._strip_for_bad_request(exc, kwargs):
                    continue
                named = _name_offending_tool(exc, kwargs.get("tools"))
                raise (named or exc) from exc
            except TypeError as exc:
                # A signature TypeError is raised at submission, before any delta.
                if not yielded_any and self._strip_for_type_error(exc, kwargs):
                    continue
                raise

    def _strip_cache_markers(self, kwargs: dict[str, Any]) -> bool:
        """Drop both cache markers from ``kwargs`` and disable caching on this
        instance. Returns False (nothing done) when no top-level marker is present."""
        if "cache_control" not in kwargs:
            return False
        kwargs.pop("cache_control", None)
        system = kwargs.get("system")
        if isinstance(system, list) and system:
            kwargs["system"] = system[0]["text"]
        self._cache_disabled = True
        logger.warning(
            "anthropic: the endpoint or SDK refused cache_control; retrying without "
            "prompt caching (disabled for this provider instance)"
        )
        return True

    def _strip_for_bad_request(
        self, exc: anthropic.BadRequestError, kwargs: dict[str, Any]
    ) -> bool:
        """Strip the key a 400 names, once. True when kwargs changed (re-run)."""
        text = str(exc).lower()
        if "temperature" in text and "temperature" in kwargs:
            # Newer Claude models (Opus 4.x, Sonnet 4.x) reject `temperature`.
            kwargs.pop("temperature", None)
            return True
        if "cache_control" in text:
            return self._strip_cache_markers(kwargs)
        return False

    def _strip_for_type_error(self, exc: TypeError, kwargs: dict[str, Any]) -> bool:
        """Squawk 0009: SDK signature drift - strip the unexpected kwarg the
        TypeError names, only when it is a key we sent. ``cache_control`` takes the
        full cache strip so an old SDK pays one failed attempt per instance."""
        name = _unexpected_kwarg_name(exc)
        if name is None or name not in kwargs:
            return False
        if name == "cache_control":
            return self._strip_cache_markers(kwargs)
        logger.warning(
            "anthropic: installed SDK rejected %r as an unexpected keyword "
            "argument; retrying without it — the bundled anthropic version "
            "may be out of range (expected <0.97)",
            name,
        )
        kwargs.pop(name, None)
        return True

    async def _stream_inner(self, kwargs: dict[str, Any]) -> AsyncIterator[StreamChunk]:
        # F7 L04 / M12 F6 L1: shared byte-emitter for mid-stream usage
        # emission. Anthropic only uses the emitter half of
        # ``_StreamAccumulator`` — tool calls arrive whole via
        # ``get_final_message``, not as streaming deltas. See module-level
        # BYTES_PER_TOKEN_ANTHROPIC docstring for the cycle-1 trade-off.
        acc = _StreamAccumulator(bytes_per_token=self.bytes_per_token)
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
        # M16 F10 L02 (DD2): thinking is read WHOLE from the final message — the
        # ``text_stream`` loop above stays untouched, so no thinking text leaks
        # into the streamed content deltas. Same capture as ``complete()``.
        thinking_blocks: list[ThinkingBlock] = []
        for block in final.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
            elif block.type == "thinking":
                thinking_blocks.append(
                    ThinkingBlock(
                        type="thinking",
                        thinking=block.thinking,
                        signature=block.signature,
                    )
                )
            elif block.type == "redacted_thinking":
                thinking_blocks.append(ThinkingBlock(type="redacted_thinking", data=block.data))

        usage = None
        if final.usage:
            usage = _usage_from_sdk(final.usage)

        msg = Message.assistant(
            content=content, tool_calls=tool_calls, usage=usage, thinking=thinking_blocks
        )
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

    def _thinking_block_to_api(self, tb: ThinkingBlock) -> dict[str, Any]:
        # M16 F10 L04: emit the stored block in Anthropic's content-block shape,
        # signatures intact. Only set sub-fields are included (a redacted block
        # has no thinking/signature). The stored ThinkingBlock is already
        # API-shaped (Leg 01), so this is a faithful projection, not a re-mapping.
        # The API 400s if a replayed thinking block is modified — copy
        # signature/data verbatim; never truncate, re-encode, or re-order.
        d: dict[str, Any] = {"type": tb.type}
        if tb.thinking is not None:
            d["thinking"] = tb.thinking
        if tb.signature is not None:
            d["signature"] = tb.signature
        if tb.data is not None:
            d["data"] = tb.data
        return d

    def _content_block_to_api(self, b: ContentBlock) -> dict[str, Any]:
        # M16 F12 L04 (DD4/DD5): map a single ContentBlock to Anthropic's
        # native content-block shape. TextContent -> {type:text}; ImageContent
        # -> {type:image, source:{...}}, preferring base64 (DD5 universal
        # path) over url when both are set.
        if isinstance(b, TextContent):
            return {"type": "text", "text": b.text}
        assert isinstance(b, ImageContent)
        if b.data is not None:
            source: dict[str, Any] = {
                "type": "base64",
                "media_type": b.media_type,
                "data": b.data,
            }
        else:
            source = {"type": "url", "url": b.url}
        return {"type": "image", "source": source}

    def _to_api_message(self, msg: Message, thinking_active: bool = False) -> dict[str, Any]:
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
        if msg.role == Role.ASSISTANT and (msg.tool_calls or (thinking_active and msg.thinking)):
            content: list[dict[str, Any]] = []
            # M16 F10 L04 (DD8): replay thinking (signatures intact) ONLY when
            # thinking is active on THIS request; thinking must precede
            # text/tool_use or Anthropic 400s the follow-up turn. When thinking
            # is off, this loop is skipped → stored thinking is stripped,
            # byte-identical to the pre-L03 projection.
            if thinking_active:
                for tb in msg.thinking:
                    content.append(self._thinking_block_to_api(tb))
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
        # M16 F12 L04 (DD4 supersedes the old L4 comment): build_user_message_content
        # is now shape-aware (str | list[ContentBlock]) and IS called on every
        # USER/SYSTEM turn. The str path below is byte-identical to before; the
        # list path (multimodal — images, plus the DD4 prefix TextContent) maps
        # each block to its native Anthropic content-block shape.
        projected = build_user_message_content(msg)
        if isinstance(projected, list):
            return {
                "role": msg.role.value,
                "content": [self._content_block_to_api(b) for b in projected],
            }
        return {"role": msg.role.value, "content": projected}


register_provider("anthropic", AnthropicProvider)
