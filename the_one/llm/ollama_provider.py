from __future__ import annotations

import json
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

    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:11434/v1",
        api_key: str | None = None,
        **kwargs: Any,
    ):
        super().__init__()
        self.model = model
        self.base_url = ollama_api.ensure_v1(base_url or "http://localhost:11434/v1")
        self.api_key = api_key

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
        data = await ollama_api.show_model(self.base_url, self.model)
        resolved = ollama_api.extract_ollama_context_length(data)
        if resolved is not None and resolved > 0:
            self.max_context_tokens = resolved
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
        # DD2: recover text-form calls only when the structured tool_calls
        # parse came back empty. DD4: the recognized block is stripped from
        # the returned content.
        if not tool_calls:
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
        acc = _StreamAccumulator(bytes_per_token=BYTES_PER_TOKEN_OLLAMA)

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
        # DD2/DD4: recover once on the fully-accumulated content — after the
        # streaming loop, never per-delta — only when no structured tool_calls
        # arrived. The interim StreamChunks already yielded carry the raw,
        # un-stripped content (intentional, documented limitation); the final
        # message below carries the stripped content + recovered calls, which
        # is what the session persists and the agent loop dispatches.
        if not tool_calls:
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
