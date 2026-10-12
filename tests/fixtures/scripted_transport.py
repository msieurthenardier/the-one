"""Scripted-transport harness for the cross-provider conformance suite (M16 F04 L02).

Each real provider reaches the canonical ``Message``/``ToolCall``/``ToolResult``
shape over a different wire dialect, and the two-turn ``request → tool_call →
tool_result → final-answer`` round-trip is queued differently per provider:

- **Anthropic** — a native recorder with ``side_effects=[turn1, turn2]`` popped
  per call (mirrors ``test_anthropic_provider.py``'s ``_CreateRecorder`` /
  ``_StreamRecorder``; the stub shapes are copied here so this harness stays
  import-stable regardless of that working-tree-modified file's state).
- **OpenAI** — an ``httpx.MockTransport`` with a **stateful** handler: the same
  ``/chat/completions`` path is hit both turns, so the handler holds a call
  counter and serves turn-1 (tool_call-emitting) then turn-2 (final answer). The
  transport is injected by replacing ``prov.client`` with an ``AsyncOpenAI``
  wrapping an ``httpx.AsyncClient(transport=...)`` (instance-only, no global patch).
- **Ollama** — ``OllamaProvider`` holds no persistent client, so ``complete()``
  is driven by monkeypatching ``httpx.AsyncClient.__init__`` to force the mock
  transport (handler also serves ``/api/show`` → ``{"model_info": {}}`` for the
  context-length resolver), and ``stream()`` by monkeypatching
  ``the_one.llm.ollama_api.chat_stream`` with a stateful async-generator factory.
- **Mock** — no transport; reconfigured between turns (``MockProvider`` returns
  the same ``config["response"]`` on every call, so turn 2 needs a fresh config).

Each constructor returns a ``ScriptedProvider`` wrapping the provider instance
plus a zero-arg ``call_count()`` accessor (asserted ``== 2`` at round-trip end as
a guard against a stateless-handler regression that would silently re-serve turn-1).

Consumers import the absolute package form (matching ``--import-mode=importlib``)::

    from tests.fixtures.scripted_transport import (
        CannedTurn, make_anthropic, make_anthropic_plan, make_openai,
        make_openrouter, make_ollama, make_mock,
    )

Legs 03 (#122 guards) and 04 (#105 recovery row + live tier) reuse this harness,
so the module path is a contract. Leg 03 adds ``make_openrouter`` (an
``OpenAIProvider``-subclass route with the live network context-resolver defused)
for the ``anthropic/*`` ``complete()``/``stream()`` sanitize smoke; leg 04
inherits it.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Provider-neutral canned turn + harness handle
# ---------------------------------------------------------------------------


@dataclass
class CannedTurn:
    """One scripted assistant turn, provider-neutral.

    A turn either emits tool calls (turn 1) or a plain-text final answer
    (turn 2). ``tool_calls`` is a list of ``(id, name, arguments)`` triples;
    ``content`` is the assistant text.
    """

    content: str = ""
    tool_calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)


@dataclass
class ScriptedProvider:
    """A harness-built provider plus a call-count accessor.

    ``provider`` is the real provider instance, configured to serve the
    scripted turns in order via ``complete()``/``stream()``. ``call_count``
    returns how many model invocations the harness has observed (asserted
    ``== 2`` at round-trip end). ``reconfigure`` is provider-specific glue
    that re-points a single-response provider (Mock) at the next turn; for
    the stateful providers it is a no-op.
    """

    provider: Any
    call_count: Callable[[], int]
    reconfigure: Callable[[CannedTurn], None] = lambda _turn: None
    # Sent request bodies, turn by turn, uniformly exposed across all four
    # request-capable constructors (M16 F11 L05): OpenAI/OpenRouter/Ollama
    # populate parsed JSON bodies from their MockTransport handler (Ollama
    # path-filtered to exclude ``/api/show``); Anthropic exposes its
    # ``_CreateRecorder``/``_StreamRecorder`` kwargs dicts directly (the kwargs
    # ARE the sent request — ``output_config``/``stop_sequences`` ride as
    # native keys). Lets a caller assert on the *sent* wire payload (e.g. the
    # sanitized tool schema on the OpenRouter ``anthropic/*`` route, or the A4
    # config→wire matrix). ``None`` only for Mock (no request path).
    request_bodies: list[dict[str, Any]] | None = None


# ===========================================================================
# Anthropic — native recorder with side_effects queue (copied stub shapes)
# ===========================================================================


class _StubContentBlock:
    """Minimal stand-in for an Anthropic response content block."""

    def __init__(self, type_: str, **kwargs: Any) -> None:
        self.type = type_
        for k, v in kwargs.items():
            setattr(self, k, v)


class _StubResponse:
    """Minimal stand-in for the non-streaming ``messages.create`` response."""

    def __init__(self, content: list[Any] | None = None, usage: Any = None) -> None:
        self.content = content if content is not None else [_StubContentBlock("text", text="ok")]
        self.usage = usage


class _CreateRecorder:
    """Async callable popping ``side_effects`` per ``messages.create`` call."""

    def __init__(self, side_effects: list[Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._side_effects = list(side_effects)

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        effect = self._side_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


class _AsyncTextStream:
    """Async iterator over text deltas."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)

    def __aiter__(self) -> _AsyncTextStream:
        return self

    async def __anext__(self) -> str:
        if not self._texts:
            raise StopAsyncIteration
        return self._texts.pop(0)


class _StreamCM:
    """Async-context-manager stand-in for ``client.messages.stream(**kwargs)``."""

    def __init__(self, texts: list[str], final: Any) -> None:
        self._texts = texts
        self._final = final

    async def __aenter__(self) -> _StreamCM:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    @property
    def text_stream(self) -> _AsyncTextStream:
        return _AsyncTextStream(list(self._texts))

    async def get_final_message(self) -> Any:
        return self._final


class _StreamRecorder:
    """Sync callable (matches the SDK's ``messages.stream``) returning a CM per call."""

    def __init__(self, factories: list[Callable[[], Any]]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._factories = list(factories)

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        factory = self._factories.pop(0)
        return factory()


def _anthropic_response_for(turn: CannedTurn) -> _StubResponse:
    blocks: list[_StubContentBlock] = []
    if turn.content:
        blocks.append(_StubContentBlock("text", text=turn.content))
    for tc_id, name, args in turn.tool_calls:
        blocks.append(_StubContentBlock("tool_use", id=tc_id, name=name, input=args))
    if not blocks:
        blocks.append(_StubContentBlock("text", text=""))
    return _StubResponse(content=blocks)


def make_anthropic(
    turns: list[CannedTurn], *, streaming: bool = False, config: dict | None = None
) -> ScriptedProvider:
    """Build an AnthropicProvider serving ``turns`` via a side-effects queue.

    ``streaming=True`` wires ``messages.stream`` instead of ``messages.create``;
    the text deltas for each turn are the turn's ``content`` (split into one
    delta) and the final message carries the tool_use/text blocks.

    ``config`` (M16 F11 L05, A4 matrix): threaded straight into the
    ``AnthropicProvider`` constructor's free-form ``config`` kwarg (read by
    ``_read_a4_config``). ``None`` (the default) preserves existing call sites.
    """
    from the_one.llm.anthropic_provider import AnthropicProvider

    prov = AnthropicProvider(model="claude-test", api_key="sk-test", config=config)
    return _wire_anthropic(prov, turns, streaming=streaming)


def make_anthropic_plan(
    turns: list[CannedTurn], *, streaming: bool = False, config: dict | None = None
) -> ScriptedProvider:
    """Build an AnthropicPlanProvider serving ``turns`` (M19 F01 L02).

    Constructed with a static ``access_token`` (the documented test/back-door
    feed — explicit token wins over credential-source resolution, so
    ``_before_request`` short-circuits and no registry/DB is touched) plus a
    dummy ``provider_config_id``. Same recorder wiring as ``make_anthropic``
    — the plan provider inherits the whole request path, only client
    construction and the pre-request token hook differ.
    """
    from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider

    prov = AnthropicPlanProvider(
        model="claude-test",
        access_token="conformance-token",
        provider_config_id="plan-conformance",
        config=config,
    )
    return _wire_anthropic(prov, turns, streaming=streaming)


def make_anthropic_plan_token(
    turns: list[CannedTurn], *, streaming: bool = False, config: dict | None = None
) -> ScriptedProvider:
    """Build an AnthropicPlanTokenProvider serving ``turns`` (sortie 03).

    Synthetic token; no credential source and no provider_config_id.
    """
    from the_one.llm.anthropic_plan_provider import AnthropicPlanTokenProvider

    prov = AnthropicPlanTokenProvider(
        model="claude-test",
        access_token="sk-ant-oat01-test-conformance",
        config=config,
    )
    return _wire_anthropic(prov, turns, streaming=streaming)


def _wire_anthropic(prov: Any, turns: list[CannedTurn], *, streaming: bool) -> ScriptedProvider:
    """Attach the create/stream recorder queue to an Anthropic-family provider."""
    if streaming:

        def _factory(t: CannedTurn) -> Callable[[], Any]:
            final = _anthropic_response_for(t)
            texts = [t.content] if t.content else []
            return lambda: _StreamCM(texts, final)

        recorder: Any = _StreamRecorder([_factory(t) for t in turns])
        prov.client.messages.stream = recorder  # type: ignore[assignment]
    else:
        recorder = _CreateRecorder([_anthropic_response_for(t) for t in turns])
        prov.client.messages.create = recorder  # type: ignore[assignment]

    # A4 matrix (L05): the recorded ``create``/``stream`` kwargs ARE the sent
    # request — ``output_config``/``stop_sequences`` (when present) are keys
    # in each dict, so exposing ``recorder.calls`` directly as
    # ``request_bodies`` gives the A4 test the same uniform accessor the
    # transport-backed providers use.
    return ScriptedProvider(
        provider=prov, call_count=lambda: len(recorder.calls), request_bodies=recorder.calls
    )


# ===========================================================================
# OpenAI — stateful MockTransport handler, instance-client replacement
# ===========================================================================


def _openai_complete_body(turn: CannedTurn) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": turn.content or None}
    if turn.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
            for tc_id, name, args in turn.tool_calls
        ]
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "gpt-test",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _openai_stream_body(turn: CannedTurn) -> str:
    """SSE body for one streamed turn (content delta(s) + tool_call deltas)."""
    lines: list[str] = []
    if turn.content:
        lines.append(
            "data: " + json.dumps({"choices": [{"index": 0, "delta": {"content": turn.content}}]})
        )
    for idx, (tc_id, name, args) in enumerate(turn.tool_calls):
        delta = {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": idx,
                                "id": tc_id,
                                "type": "function",
                                "function": {"name": name, "arguments": json.dumps(args)},
                            }
                        ]
                    },
                }
            ]
        }
        lines.append("data: " + json.dumps(delta))
    # Final metadata-only chunk carrying usage (include_usage=True path).
    lines.append(
        "data: "
        + json.dumps({"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    )
    lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


def make_openai(
    turns: list[CannedTurn], *, streaming: bool = False, config: dict | None = None
) -> ScriptedProvider:
    """Build an OpenAIProvider whose ``/chat/completions`` serves ``turns`` in order.

    The handler is stateful — a call counter routes the first hit to turn-1 and
    the second to turn-2 on the same path. ``call_count()`` exposes the counter
    so the round-trip can assert it reached exactly 2.

    ``config`` (M16 F11 L05, A4 matrix): threaded into the ``OpenAIProvider``
    constructor's free-form ``config`` kwarg. ``None`` (the default) preserves
    existing call sites. The handler also appends each parsed request body to
    ``request_bodies`` (mirroring ``make_openrouter``) so a caller can assert
    on the sent wire payload.
    """
    import openai

    from the_one.llm.openai_provider import OpenAIProvider

    counter = {"n": 0}
    request_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            request_bodies.append(json.loads(request.content))
        except (ValueError, TypeError):
            request_bodies.append({})
        idx = counter["n"]
        counter["n"] += 1
        turn = turns[idx]
        if streaming:
            return httpx.Response(
                200,
                content=_openai_stream_body(turn),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=_openai_complete_body(turn))

    transport = httpx.MockTransport(handler)
    prov = OpenAIProvider(model="gpt-test", api_key="x", config=config)
    prov.client = openai.AsyncOpenAI(
        api_key="x",
        base_url=str(prov.client.base_url),
        http_client=httpx.AsyncClient(transport=transport),
    )
    return ScriptedProvider(
        provider=prov, call_count=lambda: counter["n"], request_bodies=request_bodies
    )


# ===========================================================================
# OpenRouter — OpenAIProvider subclass; same transport injection + a defused
# network context-resolver (the anthropic/* route is the #122 sanitize seam).
# ===========================================================================


def make_openrouter(
    turns: list[CannedTurn],
    *,
    model: str = "anthropic/claude-3.5-haiku",
    streaming: bool = False,
    config: dict | None = None,
) -> ScriptedProvider:
    """Build an OpenRouterProvider whose ``/chat/completions`` serves ``turns``.

    ``OpenRouterProvider`` is an ``OpenAIProvider`` subclass, so the same
    stateful-handler + instance-client-replacement injection ``make_openai``
    uses works verbatim — only the constructed provider type (and, for the
    ``anthropic/*`` route, the ``tool_schema`` sanitize seam) differ.

    **Network context-resolver defused (required for hermeticity).**
    ``OpenRouterProvider._resolve_max_context_tokens`` calls
    ``openrouter_api.get_model_context_length`` over the network via its *own*
    ``httpx.AsyncClient`` — NOT the injected ``MockTransport``. ``complete()``/
    ``stream()`` would attempt a real call (swallowed by the base wrapper, so the
    test would not *fail*, but it breaks the suite's hermetic guarantee). We
    pre-flip the ``_max_context_tokens_resolved`` sentinel so the resolver is
    never invoked — no monkeypatch needed, keeping this constructor's signature
    monkeypatch-free for leg 04's reuse.

    The handler exposes ``request_bodies`` via the ``ScriptedProvider`` (parsed
    turn-by-turn) so a caller can assert the *sent* tool schema was sanitized on
    the ``anthropic/*`` route — proving the sanitize ran end-to-end through
    ``complete()``/``stream()``, not just via the standalone ``tool_schema()``.

    ``config`` (M16 F11 L05, A4 matrix): threaded into the
    ``OpenRouterProvider`` constructor's explicit ``config`` param (DD5's
    OpenRouter config→wire assertion). ``None`` (the default) preserves
    existing call sites.
    """
    import openai

    from the_one.llm.openrouter_provider import OpenRouterProvider

    counter = {"n": 0}
    request_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            request_bodies.append(json.loads(request.content))
        except (ValueError, TypeError):
            request_bodies.append({})
        idx = counter["n"]
        counter["n"] += 1
        turn = turns[idx]
        if streaming:
            return httpx.Response(
                200,
                content=_openai_stream_body(turn),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=_openai_complete_body(turn))

    transport = httpx.MockTransport(handler)
    prov = OpenRouterProvider(model=model, api_key="x", config=config)
    prov.client = openai.AsyncOpenAI(
        api_key="x",
        base_url=str(prov.client.base_url),
        http_client=httpx.AsyncClient(transport=transport),
    )
    # Defuse the live context-resolver: pretend resolution already happened so
    # the OpenRouter override (a real network call on its own client) never runs.
    prov._max_context_tokens_resolved = True

    return ScriptedProvider(
        provider=prov, call_count=lambda: counter["n"], request_bodies=request_bodies
    )


# ===========================================================================
# Ollama — stateful handler (complete) / stateful chat_stream (stream)
# ===========================================================================


def _ollama_complete_body(turn: CannedTurn) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": turn.content}
    if turn.tool_calls:
        message["tool_calls"] = [
            {"id": tc_id, "type": "function", "function": {"name": name, "arguments": args}}
            for tc_id, name, args in turn.tool_calls
        ]
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def _ollama_stream_chunks(turn: CannedTurn) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    if turn.content:
        chunks.append({"choices": [{"delta": {"content": turn.content}}]})
    for idx, (tc_id, name, args) in enumerate(turn.tool_calls):
        chunks.append(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": idx,
                                    "id": tc_id,
                                    "function": {"name": name, "arguments": json.dumps(args)},
                                }
                            ]
                        }
                    }
                ]
            }
        )
    chunks.append({"usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    return chunks


def make_ollama(
    turns: list[CannedTurn],
    monkeypatch: Any,
    *,
    streaming: bool = False,
    config: dict | None = None,
) -> ScriptedProvider:
    """Build an OllamaProvider serving ``turns`` in order.

    ``OllamaProvider`` builds a fresh ``httpx.AsyncClient`` per ``complete()``
    call and has no persistent client, so the transport is injected via a
    ``httpx.AsyncClient.__init__`` monkeypatch (auto-undone by the fixture).
    The handler also serves ``/api/show`` → ``{"model_info": {}}`` for the
    context-length resolver AND (M16 F03 L08C's recovery gate) the
    ``supports_tools()`` capabilities lookup — both hit the same endpoint. For
    ``stream()``, ``the_one.llm.ollama_api.chat_stream`` is monkeypatched with
    a stateful async-generator factory.

    ``config`` (M16 F11 L05, A4 matrix): threaded into the ``OllamaProvider``
    constructor's free-form ``config`` kwarg. ``None`` (the default) preserves
    existing call sites.

    **Request capture (path-filtered).** ``complete()`` POSTs to ``/api/show``
    both before (context-length resolve) and, on a plain-text turn, after
    (``supports_tools()``) the real ``/chat/completions`` call — a blanket
    capture would land the A4 body at the wrong index. So capture is gated to
    the ``/chat/completions`` path only (mirroring the existing turn-counter's
    ``/api/show`` special-case below); the ``stream()`` path never hits
    ``/api/show`` at this seam, so ``fake_chat_stream`` captures unconditionally.
    """
    from the_one.llm.ollama_provider import OllamaProvider

    counter = {"n": 0}
    request_bodies: list[dict[str, Any]] = []

    if streaming:
        from the_one.llm import ollama_api

        async def fake_chat_stream(
            base_url: str, body: Any, headers: Any = None
        ) -> AsyncIterator[dict[str, Any]]:
            request_bodies.append(body)
            idx = counter["n"]
            counter["n"] += 1
            for chunk in _ollama_stream_chunks(turns[idx]):
                yield chunk

        monkeypatch.setattr(ollama_api, "chat_stream", fake_chat_stream)
    else:

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/api/show"):
                return httpx.Response(200, json={"model_info": {}})
            try:
                request_bodies.append(json.loads(request.content))
            except (ValueError, TypeError):
                request_bodies.append({})
            idx = counter["n"]
            counter["n"] += 1
            return httpx.Response(200, json=_ollama_complete_body(turns[idx]))

        original_init = httpx.AsyncClient.__init__

        def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1", config=config)
    return ScriptedProvider(
        provider=prov, call_count=lambda: counter["n"], request_bodies=request_bodies
    )


# ===========================================================================
# Mock — no transport; reconfigured between turns
# ===========================================================================


def _mock_config_for(turn: CannedTurn, *, streaming: bool = False) -> dict[str, Any]:
    response: dict[str, Any] = {"content": turn.content}
    if turn.tool_calls:
        response["tool_calls"] = [
            {"id": tc_id, "name": name, "arguments": args} for tc_id, name, args in turn.tool_calls
        ]
    config: dict[str, Any] = {"response": response}
    if streaming and turn.content:
        config["stream_chunks"] = [turn.content]
    return config


def make_mock(turns: list[CannedTurn], *, streaming: bool = False) -> ScriptedProvider:
    """Build a MockProvider configured for turn-1.

    ``MockProvider`` returns the same ``config["response"]`` on every call, so
    the harness exposes ``reconfigure(turn)`` (and increments a call counter on
    each (re)configuration) to point the provider at the next turn before the
    second ``complete()``/``stream()``.
    """
    from the_one.llm.mock import MockProvider

    counter = {"n": 0}
    prov = MockProvider(model="mock-test", config=_mock_config_for(turns[0], streaming=streaming))
    counter["n"] += 1

    def reconfigure(turn: CannedTurn) -> None:
        prov.config = _mock_config_for(turn, streaming=streaming)
        counter["n"] += 1

    return ScriptedProvider(provider=prov, call_count=lambda: counter["n"], reconfigure=reconfigure)
