from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from the_one.llm import ollama_api
from the_one.llm._streaming import _StreamAccumulator
from the_one.llm._toolcall_recovery import recover_and_strip
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
# Ollama hosts a heterogeneous mix of tokenisers (Llama 3, Qwen, Gemma,
# Mistral, etc.); 3.5 is the empirical mean across the most common
# instruction-tuned families. Tunable post-HAT.  The shared threshold
# (200 bytes) and accumulator logic live in ``the_one.llm._streaming``.
BYTES_PER_TOKEN_OLLAMA = 3.5

# Ollama runtime context window (``num_ctx``). Ollama's server default is 4096
# REGARDLESS of the model's advertised architectural window, and its
# OpenAI-compatible ``/v1`` endpoint ignores ``options.num_ctx`` — so without an
# explicit native-API pre-load (see ``ollama_api.load_model``) the runner
# truncates the prompt at 4096 tokens and a conversation dies once its history
# crosses that line. This is the window we actually load the runner at, and the
# value the governor + context gauge size against. Env-overridable so an
# operator with more VRAM can raise it (future: surface this in the UI per
# provider/model, with a per-agent override — see the recorded follow-up).
_NUM_CTX_ENV = "THE_ONE_OLLAMA_NUM_CTX"
_DEFAULT_NUM_CTX = 32_768


def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment at call time, else ``default``.

    Read at call time (not import time) so a test can monkeypatch
    ``os.environ`` without reloading the module — mirrors the governor's
    ``_env_int`` and the agent layer's ``_get_tool_call_timeout``.
    """
    raw = os.environ.get(name, "")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default


def _coerce_num_ctx(value: Any) -> int | None:
    """Coerce a free-form ``config.num_ctx`` value to a positive int, or None.

    The value rides in the provider's free-form ``config`` dict (persisted as
    JSON), so it may be absent, a string from a round-trip, a float, or junk.
    Anything that is not a positive integer (after a lenient string parse)
    collapses to ``None`` so the resolver falls back to env/default rather than
    crashing on a stray value. ``bool`` is rejected explicitly (it is an ``int``
    subclass but never a meaningful window).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def effective_num_ctx(advertised: int | None, configured: int | None = None) -> int | None:
    """Resolve the runtime ``num_ctx`` to load an Ollama model at.

    Precedence (low→high): default ``_DEFAULT_NUM_CTX`` (32768) → env
    ``THE_ONE_OLLAMA_NUM_CTX`` → per-provider ``configured`` (``config.num_ctx``).
    The chosen value is always clamped to the model's advertised architectural
    window so we never request more than the architecture supports, while the
    default caps well below huge advertised windows (e.g. ministral's 262144)
    that would allocate an impractical KV cache. The env value is read at call
    time. ``configured`` is coerced leniently (``_coerce_num_ctx``): a positive
    int (or numeric string) wins; junk / non-positive values are ignored and the
    env→default path applies, so a stray value in ``config`` never crashes here.

    Returns ``None`` when the advertised window is unknown / non-positive — the
    caller then leaves Ollama's own default untouched rather than guessing a
    window that might exceed what the model actually supports. This keeps the
    no-information path identical to historical behaviour.
    """
    if advertised is None or advertised <= 0:
        return None
    configured = _coerce_num_ctx(configured)
    if configured is not None:
        return min(configured, advertised)
    return min(_env_int(_NUM_CTX_ENV, _DEFAULT_NUM_CTX), advertised)


def _recover_into_tool_calls(content: str) -> tuple[str, list[ToolCall]]:
    """Recover text-form calls from ``content`` (DD2/DD4).

    Returns ``(stripped_content, tool_calls)``. When nothing is recovered,
    returns ``(content unchanged, [])``. Delegates all marker knowledge —
    recognition AND span stripping — to the kernel's ``recover_and_strip``;
    this helper's only added responsibility is mapping each recovered dict
    to a ``ToolCall`` with a synthesized stable id ``f"{name}_{index}"``.

    The synthesized id is deliberately more collision-safe than the adjacent
    structured path's bare-name fallback: two same-name recovered calls get
    distinct ids (``get_weather_0``, ``get_weather_1``). The kernel passes
    ``arguments`` through verbatim — including the ``__positional_args__``
    sentinel, which the dispatcher (not the provider) special-cases.
    """
    stripped, recovered = recover_and_strip(content)
    tool_calls = [
        ToolCall(id=f"{d['name']}_{i}", name=d["name"], arguments=d["arguments"])
        for i, d in enumerate(recovered)
    ]
    return stripped, tool_calls


class OllamaProvider(LLMProvider):
    """Ollama provider using its OpenAI-compatible /v1/chat/completions endpoint.

    Also works with any OpenAI-compatible local server (LM Studio, vLLM, llama.cpp, etc.)
    by setting a custom base_url.
    """

    name = "ollama"
    # M16 F08 L01 (MEDIUM-1): single public accessor (the governor + the
    # stream accumulator both read this), replacing the bare module-constant
    # passed only into ``_StreamAccumulator``.
    bytes_per_token = BYTES_PER_TOKEN_OLLAMA

    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:11434/v1",
        api_key: str | None = None,
        native_api: bool = False,
        **kwargs: Any,
    ):
        super().__init__()
        self.model = model
        self.base_url = ollama_api.ensure_v1(base_url or "http://localhost:11434/v1")
        self.api_key = api_key
        # ``native_api`` selects the wire protocol for generation:
        #   True  → real Ollama: generate via the NATIVE /api/chat endpoint so
        #           ``options.num_ctx`` is honoured (the /v1 endpoint ignores it
        #           and pins the runner at Ollama's 4096 default — the bug this
        #           class of provider must avoid).
        #   False → an OpenAI-compatible server (LM Studio, vLLM, llama.cpp;
        #           provider type "openai-compatible"): stay on /v1, no num_ctx.
        # The factory sets this from the provider config's ``type``. Defaults to
        # False so direct construction (tests, generic OpenAI-compatible
        # back-ends) keeps the historical /v1 behaviour.
        self.native_api = native_api
        # Per-provider runtime window override, read from the free-form provider
        # ``config`` dict (``config.num_ctx``) — the highest-precedence source
        # for ``effective_num_ctx`` (above env + default). Coerced to a positive
        # int or None so a stray non-int in ``config`` can't crash generation.
        # No model/schema change: this rides the same free-form config dict the
        # OpenRouter provider uses for ``referer``/``title``.
        config = kwargs.get("config")
        self._configured_num_ctx: int | None = (
            _coerce_num_ctx(config.get("num_ctx")) if isinstance(config, dict) else None
        )
        # Runtime ``num_ctx`` to send on native requests, resolved from the
        # model's advertised window + the per-provider override
        # (``effective_num_ctx``). None → omit num_ctx and let Ollama use its
        # default. Set in ``_resolve_max_context_tokens``; only consulted on the
        # native path.
        self._runtime_num_ctx: int | None = None

    def _auth_headers(self) -> dict[str, str]:
        """Return ``{Authorization: Bearer <key>}`` only when api_key is
        present and non-empty after strip. Empty / whitespace / None all
        produce ``{}`` so OSS Ollama (which rejects empty bearer) keeps
        working unchanged."""
        key = (self.api_key or "").strip()
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def _resolve_max_context_tokens(self) -> None:
        # Query Ollama's native /api/show endpoint and walk the
        # ``model_info`` map for a key ending in ``.context_length``.
        # Family-namespaced (e.g. ``qwen2.context_length``,
        # ``llama.context_length``). Failures (network, 404) propagate to
        # the wrapper which catches + logs + flips the sentinel.
        #
        # IMPORTANT: ``max_context_tokens`` for Ollama is the EFFECTIVE runtime
        # window (the ``num_ctx`` we load the runner at), NOT the model's
        # advertised architectural maximum. Ollama defaults num_ctx to 4096 and
        # the /v1 endpoint can't raise it, so the governor and the context gauge
        # must size against what we actually load (see ``effective_num_ctx`` and
        # ``_ensure_ollama_model_loaded`` in the web layer). When the advertised
        # window is unknown we leave the class default (no information → no
        # change), matching historical behaviour.
        data = await ollama_api.show_model(self.base_url, self.model)
        advertised = ollama_api.extract_ollama_context_length(data)
        # Per-provider ``config.num_ctx`` (if set) takes precedence over env +
        # default, then is clamped to the advertised window. Resolved here at
        # (re)load time; an already-running runner keeps its window until the
        # next (re)load (the web preload path reloads when the window differs).
        effective = effective_num_ctx(advertised, self._configured_num_ctx)
        # Record the runtime num_ctx (may be None) for the native generation
        # path, and surface it as max_context_tokens so the governor + the
        # context gauge size against the window we actually load.
        self._runtime_num_ctx = effective
        if effective is not None:
            self.max_context_tokens = effective
        # else: leave at class default; sentinel still flips in the wrapper.

    async def supports_tools(self) -> bool:
        """Returns False if the Ollama model is known not to advertise the
        ``tools`` capability via ``/api/show`` (e.g. Gemma variants). Returns
        True when capabilities can't be determined (network blip, model
        missing) so the request still goes out and any error surfaces with
        the improved 400-body diagnostic.
        """
        caps = await ollama_api.get_model_capabilities(self.base_url, self.model)
        return caps is None or "tools" in caps

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        await self._resolve_max_context_tokens_if_needed()
        if self.native_api:
            return await self._complete_native(messages, tools, temperature, max_tokens)
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

        async with httpx.AsyncClient(timeout=300, headers=self._auth_headers()) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            if resp.status_code >= 400:
                detail = resp.text.strip() or "(empty body)"
                raise httpx.HTTPStatusError(
                    f"Ollama returned {resp.status_code} from {resp.request.url}: {detail}",
                    request=resp.request,
                    response=resp,
                )
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

        content = msg.get("content") or ""
        # DD2 (updated by M16 F03 L08C): recover text-form calls only when
        # the structured tool_calls parse came back empty AND the model is
        # tool-capable. Tool-capable models that drop to text are still
        # recovered (DD2's real intent). Non-tool models (supports_tools=False)
        # are chat-only — their content passes through verbatim so a
        # spontaneously-emitted tool_code block is never parsed/stripped/
        # dispatched. supports_tools() fail-open=True means recovery stays on
        # under uncertainty (acceptable: fail toward prior behavior).
        if not tool_calls and await self.supports_tools():
            content, recovered = _recover_into_tool_calls(content)
            tool_calls = recovered

        return Message.assistant(
            content=content,
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
        await self._resolve_max_context_tokens_if_needed()
        if self.native_api:
            async for chunk in self._stream_native(messages, tools, temperature, max_tokens):
                yield chunk
            return
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
        usage: TokenUsage | None = None
        # F7 L04 / M12 F6 L1: shared accumulator for tool-call deltas and
        # mid-stream interim-usage emission (Ollama-specific bytes-per-token).
        acc = _StreamAccumulator(bytes_per_token=self.bytes_per_token)

        async for chunk_dict in ollama_api.chat_stream(
            self.base_url, body, headers=self._auth_headers()
        ):
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
                interim = acc.maybe_emit_interim(text)
                if interim:
                    yield interim
            for tc_delta in delta.get("tool_calls", []) or []:
                idx = tc_delta.get("index", 0)
                fn = tc_delta.get("function", {}) or {}
                args = fn.get("arguments")
                if args is not None:
                    if isinstance(args, str):
                        args_str = args
                    else:
                        # Ollama may emit arguments as a dict directly; serialise
                        # before handing the str increment to the accumulator.
                        args_str = json.dumps(args)
                else:
                    args_str = ""
                acc.feed_tool_call_delta(
                    index=idx,
                    id_str=tc_delta.get("id") or "",
                    name_str=fn.get("name") or "",
                    arguments_str=args_str,
                )
            # Some Ollama responses surface usage on the last data line that
            # ALSO carries choices (rather than a metadata-only trailer).
            if "usage" in chunk_dict and usage is None:
                u = chunk_dict["usage"]
                usage = TokenUsage(
                    input_tokens=u.get("prompt_tokens", 0),
                    output_tokens=u.get("completion_tokens", 0),
                )

        tool_calls: list[ToolCall] = [
            ToolCall(id=e["id"], name=e["name"], arguments=e["arguments"])
            for e in acc.finalize_tool_calls()
        ]
        # DD2/DD4 (updated by M16 F03 L08C): recover once on the fully-accumulated
        # content — after the streaming loop, never per-delta — only when no
        # structured tool_calls arrived AND the model is tool-capable. Recovery is
        # gated on supports_tools() to enforce chat-only behavior for non-tool models:
        # their content passes through verbatim (not stripped/dispatched). The interim
        # StreamChunks already yielded carry the raw, un-stripped content (intentional,
        # documented limitation); the final message below carries the stripped content +
        # recovered calls for tool-capable models. supports_tools() fail-open=True means
        # recovery stays on under network uncertainty (fail toward prior behavior).
        if not tool_calls and await self.supports_tools():
            content, recovered = _recover_into_tool_calls(content)
            tool_calls = recovered

        msg = Message.assistant(content=content, tool_calls=tool_calls, usage=usage)
        yield StreamChunk(
            content="",
            is_final=True,
            tool_calls=tool_calls,
            usage=usage,
            message=msg,
        )

    # ------------------------------------------------------------------
    # Native /api/chat path (real Ollama; honours num_ctx)
    # ------------------------------------------------------------------

    def _native_options(self, temperature: float, max_tokens: int) -> dict[str, Any]:
        """Build the native ``options`` map. ``num_ctx`` (the whole point of the
        native path) is included only when a runtime window was resolved."""
        options: dict[str, Any] = {"temperature": temperature, "num_predict": max_tokens}
        if self._runtime_num_ctx is not None:
            options["num_ctx"] = self._runtime_num_ctx
        return options

    def _native_body(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [self._to_native_message(m) for m in messages],
            "options": self._native_options(temperature, max_tokens),
        }
        # Native /api/chat accepts the SAME tool schema shape as OpenAI.
        if tools:
            body["tools"] = [self.tool_schema(t) for t in tools]
        return body

    def _to_native_message(self, msg: Message) -> dict[str, Any]:
        """Project a ``Message`` into Ollama's native /api/chat shape.

        Differs from ``_to_api_message`` (OpenAI/v1) in two ways: tool results
        carry no ``tool_call_id`` (native matches by position), and tool-call
        ``arguments`` are sent as a JSON OBJECT, not a JSON-encoded string.
        """
        if msg.role == Role.TOOL and msg.tool_result:
            return {"role": "tool", "content": msg.tool_result.content}
        if msg.role == Role.ASSISTANT and msg.tool_calls:
            return {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"function": {"name": tc.name, "arguments": tc.arguments}}
                    for tc in msg.tool_calls
                ],
            }
        return {"role": msg.role.value, "content": build_user_message_content(msg)}

    @staticmethod
    def _native_usage(data: dict[str, Any]) -> TokenUsage | None:
        """Native usage lives in ``prompt_eval_count`` / ``eval_count`` (on the
        terminal ``done`` object), not an OpenAI ``usage`` block."""
        if "prompt_eval_count" in data or "eval_count" in data:
            return TokenUsage(
                input_tokens=data.get("prompt_eval_count", 0) or 0,
                output_tokens=data.get("eval_count", 0) or 0,
            )
        return None

    @staticmethod
    def _parse_native_tool_calls(message: dict[str, Any]) -> list[ToolCall]:
        """Map native ``message.tool_calls`` → ``ToolCall``. Native arguments are
        objects (already parsed); tolerate a string form defensively. Synthesizes
        a stable id when the model omits one (mirrors the recovery path)."""
        out: list[ToolCall] = []
        for i, tc in enumerate(message.get("tool_calls") or []):
            fn = tc.get("function", {}) or {}
            name = fn.get("name") or ""
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            elif not isinstance(args, dict):
                args = {}
            out.append(ToolCall(id=tc.get("id") or f"{name}_{i}", name=name, arguments=args))
        return out

    async def _complete_native(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
    ) -> Message:
        data = await ollama_api.chat_native(
            self.base_url,
            self._native_body(messages, tools, temperature, max_tokens),
            headers=self._auth_headers(),
        )
        message = data.get("message", {}) or {}
        content = message.get("content") or ""
        tool_calls = self._parse_native_tool_calls(message)
        usage = self._native_usage(data)
        # Same text-form recovery contract as the /v1 path (DD2/DD4).
        if not tool_calls and await self.supports_tools():
            content, recovered = _recover_into_tool_calls(content)
            tool_calls = recovered
        return Message.assistant(content=content, tool_calls=tool_calls, usage=usage)

    async def _stream_native(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamChunk]:
        content = ""
        usage: TokenUsage | None = None
        native_tool_calls: list[dict[str, Any]] = []
        acc = _StreamAccumulator(bytes_per_token=self.bytes_per_token)
        async for chunk in ollama_api.chat_stream_native(
            self.base_url,
            self._native_body(messages, tools, temperature, max_tokens),
            headers=self._auth_headers(),
        ):
            message = chunk.get("message", {}) or {}
            text = message.get("content")
            if text:
                content += text
                yield StreamChunk(content=text, is_final=False)
                interim = acc.maybe_emit_interim(text)
                if interim:
                    yield interim
            # Native sends the full tool_calls array in one message object (not
            # streamed deltas), so capture-by-assignment is correct.
            if message.get("tool_calls"):
                native_tool_calls = message["tool_calls"]
            u = self._native_usage(chunk)
            if u is not None:
                usage = u
            if chunk.get("done"):
                break

        tool_calls = self._parse_native_tool_calls({"tool_calls": native_tool_calls})
        if not tool_calls and await self.supports_tools():
            content, recovered = _recover_into_tool_calls(content)
            tool_calls = recovered
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
        return {"role": msg.role.value, "content": build_user_message_content(msg)}


register_provider("ollama", OllamaProvider)
