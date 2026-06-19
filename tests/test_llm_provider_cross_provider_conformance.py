"""Cross-provider tool-use round-trip conformance tests.

M16 F04 L02: pins the canonical ``request → tool_call → tool_result →
final-answer`` round-trip across {Anthropic, OpenAI, Ollama, Mock} at the
``LLMProvider`` contract (DD1 — NOT through the agent loop). One canonical
provider-neutral script (DD2 — a tool def + a turn-1 ``ToolCall`` expectation +
a synthesized ``ToolResult`` + a turn-2 final-answer expectation) drives every
provider through both ``complete()`` and ``stream()``, plus the
``tools=None``/``tools=[]`` plain-text path.

Each provider reaches the canonical shape over a different wire dialect; the
two-turn queue is built per-provider by the scripted-transport harness in
``tests/fixtures/scripted_transport.py``. Assertions read the canonical
``Message``/``ToolCall``/``ToolResult`` objects, not wire bytes (mirroring
``test_llm_provider_cross_provider_history.py``'s structural style).

Hermetic: no network, no credentials. Runs under ``make test-unit``'s default
deselection (no ``@pytest.mark.live``).
"""

from __future__ import annotations

import copy
import logging

import anthropic
import pytest

from tests.fixtures.scripted_transport import (
    CannedTurn,
    make_anthropic,
    make_mock,
    make_ollama,
    make_openai,
    make_openrouter,
)
from tests.fixtures.tool_schemas import (
    PRESS_KEY_INPUT_SCHEMA,
    UNSANITIZABLE_ANYOF_SCHEMA,
    make_bad_request,
)
from the_one.llm.base import Message, ToolCall, ToolResult

# ---------------------------------------------------------------------------
# The one canonical provider-neutral script (DD2)
# ---------------------------------------------------------------------------

TOOL_DEF = {
    "name": "get_weather",
    "description": "Look up the current weather for a city.",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
    },
}

EXPECTED_TOOL_NAME = "get_weather"
EXPECTED_TOOL_ID = "tc_1"
EXPECTED_ARGS = {"city": "Paris"}
TOOL_RESULT_CONTENT = "It is 18C and sunny in Paris."
FINAL_ANSWER = "The weather in Paris is 18C and sunny."

# Turn 1 emits a tool call (no final content); turn 2 is the plain-text answer.
TURN_1 = CannedTurn(tool_calls=[(EXPECTED_TOOL_ID, EXPECTED_TOOL_NAME, EXPECTED_ARGS)])
TURN_2 = CannedTurn(content=FINAL_ANSWER)

# No-tools path: a single plain-text turn.
PLAIN_TURN = CannedTurn(content=FINAL_ANSWER)


# ---------------------------------------------------------------------------
# Per-provider harness factories (uniform signature)
# ---------------------------------------------------------------------------
#
# Ollama needs the ``monkeypatch`` fixture (no persistent client to replace),
# so every factory takes ``(turns, monkeypatch, streaming)`` for a uniform
# parametrized call site; the others ignore ``monkeypatch``.


def _anthropic_factory(turns, monkeypatch, *, streaming=False):
    return make_anthropic(turns, streaming=streaming)


def _openai_factory(turns, monkeypatch, *, streaming=False):
    return make_openai(turns, streaming=streaming)


def _ollama_factory(turns, monkeypatch, *, streaming=False):
    return make_ollama(turns, monkeypatch, streaming=streaming)


def _mock_factory(turns, monkeypatch, *, streaming=False):
    return make_mock(turns, streaming=streaming)


PROVIDER_FACTORIES = [
    pytest.param(_anthropic_factory, id="anthropic"),
    pytest.param(_openai_factory, id="openai"),
    pytest.param(_ollama_factory, id="ollama"),
    pytest.param(_mock_factory, id="mock"),
]


# ---------------------------------------------------------------------------
# Provider-neutral round-trip drivers
# ---------------------------------------------------------------------------


async def _drive_complete_roundtrip(scripted) -> None:
    """Run the two-turn round-trip over ``complete()`` and assert canonical shape."""
    prov = scripted.provider
    user = Message.user("What's the weather in Paris?")

    # Turn 1: provider emits a tool call.
    m1 = await prov.complete([user], tools=[TOOL_DEF])
    assert isinstance(m1, Message)
    assert len(m1.tool_calls) == 1
    tc = m1.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.name == EXPECTED_TOOL_NAME
    assert tc.arguments == EXPECTED_ARGS

    # Build the canonical tool result and advance single-response providers.
    result = ToolResult(tool_call_id=tc.id, content=TOOL_RESULT_CONTENT)
    tool_msg = Message.tool(result)
    scripted.reconfigure(TURN_2)

    # Turn 2: provider emits the final plain-text answer, no tool calls.
    m2 = await prov.complete([user, m1, tool_msg], tools=[TOOL_DEF])
    assert isinstance(m2, Message)
    assert m2.tool_calls == []
    assert m2.content == FINAL_ANSWER
    assert m2.content

    # Tight guard: the stateful handler / queue advanced exactly twice.
    assert scripted.call_count() == 2


async def _collect_final_chunk(stream_iter):
    chunks = [c async for c in stream_iter]
    final = [c for c in chunks if c.is_final]
    assert len(final) == 1, f"expected exactly one final chunk, got {len(final)}"
    return final[0], chunks


async def _drive_stream_roundtrip(scripted) -> None:
    """Run the two-turn round-trip over ``stream()`` and assert on the final chunk."""
    prov = scripted.provider
    user = Message.user("What's the weather in Paris?")

    # Turn 1: tool call surfaces on the final StreamChunk.
    final1, _ = await _collect_final_chunk(prov.stream([user], tools=[TOOL_DEF]))
    assert final1.message is not None
    assert isinstance(final1.message, Message)
    assert len(final1.tool_calls) == 1
    assert final1.tool_calls == final1.message.tool_calls
    tc = final1.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.name == EXPECTED_TOOL_NAME
    assert tc.arguments == EXPECTED_ARGS

    result = ToolResult(tool_call_id=tc.id, content=TOOL_RESULT_CONTENT)
    tool_msg = Message.tool(result)
    scripted.reconfigure(TURN_2)

    # Turn 2: final answer, no tool calls.
    final2, _ = await _collect_final_chunk(
        prov.stream([user, final1.message, tool_msg], tools=[TOOL_DEF])
    )
    assert final2.message is not None
    assert final2.tool_calls == []
    assert final2.message.tool_calls == []
    assert final2.message.content == FINAL_ANSWER
    assert final2.message.content

    assert scripted.call_count() == 2


# ---------------------------------------------------------------------------
# complete() round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", PROVIDER_FACTORIES)
async def test_complete_roundtrip(factory, monkeypatch):
    scripted = factory([TURN_1, TURN_2], monkeypatch)
    await _drive_complete_roundtrip(scripted)


# ---------------------------------------------------------------------------
# stream() round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", PROVIDER_FACTORIES)
async def test_stream_roundtrip(factory, monkeypatch):
    scripted = factory([TURN_1, TURN_2], monkeypatch, streaming=True)
    await _drive_stream_roundtrip(scripted)


# ---------------------------------------------------------------------------
# tools=None / tools=[] plain-text path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", PROVIDER_FACTORIES)
@pytest.mark.parametrize("tools", [None, []], ids=["tools_none", "tools_empty"])
async def test_complete_no_tools_plaintext(factory, tools, monkeypatch):
    scripted = factory([PLAIN_TURN], monkeypatch)
    prov = scripted.provider
    user = Message.user("Just say something.")

    m = await prov.complete([user], tools=tools)
    assert isinstance(m, Message)
    assert m.tool_calls == []
    assert m.content == FINAL_ANSWER
    assert m.content
    assert scripted.call_count() == 1


@pytest.mark.parametrize("factory", PROVIDER_FACTORIES)
@pytest.mark.parametrize("tools", [None, []], ids=["tools_none", "tools_empty"])
async def test_stream_no_tools_plaintext(factory, tools, monkeypatch):
    scripted = factory([PLAIN_TURN], monkeypatch, streaming=True)
    prov = scripted.provider
    user = Message.user("Just say something.")

    final, _ = await _collect_final_chunk(prov.stream([user], tools=tools))
    assert final.message is not None
    assert final.tool_calls == []
    assert final.message.tool_calls == []
    assert final.message.content == FINAL_ANSWER
    assert final.message.content
    assert scripted.call_count() == 1


# ===========================================================================
# #122 schema guards (M16 F04 L03)
# ===========================================================================
#
# DD4: co-located in this regression-net module — the cross-provider tool-use
# coverage gaps the Flight-2 debrief assigned to Flight 4, plus the DD6
# error-format pin and the DD3 forward-with-WARN asymmetry pin.

_TOP_LEVEL_COMBINATORS = ("anyOf", "oneOf", "allOf")


def _press_key_tool_def() -> dict:
    """A fresh ``press_key`` tool def each call.

    Deep-copies the shared ``PRESS_KEY_INPUT_SCHEMA`` constant so a provider
    that sanitizes in place (none do — the kernel deep-copies — but belt-and-
    braces) can never mutate the module-level fixture across cases.
    """
    return {
        "name": "press_key",
        "description": "Press a keyboard key in the target tab.",
        "parameters": copy.deepcopy(PRESS_KEY_INPUT_SCHEMA),
    }


# ---------------------------------------------------------------------------
# 1. Cross-provider same-schema: sanitized (Anthropic, OpenRouter anthropic/*)
#    vs. verbatim (OpenAI, Ollama, OpenRouter non-anthropic/*).
# ---------------------------------------------------------------------------


def test_cross_provider_same_schema_sanitized_vs_verbatim():
    """The single #122 trigger (`PRESS_KEY_INPUT_SCHEMA`, top-level `anyOf`),
    fed through every provider's tool-schema path, is sanitized only on the two
    Anthropic-backed routes and left verbatim on the OpenAI-compat backends.

    Anthropic's sanitize seam is ``_to_anthropic_tool`` (not ``tool_schema``);
    OpenRouter's is ``tool_schema`` gated on the ``anthropic/*`` prefix; OpenAI,
    Ollama, and non-``anthropic/*`` OpenRouter inherit the base verbatim
    ``tool_schema``.
    """
    from the_one.llm.anthropic_provider import AnthropicProvider
    from the_one.llm.ollama_provider import OllamaProvider
    from the_one.llm.openai_provider import OpenAIProvider
    from the_one.llm.openrouter_provider import OpenRouterProvider

    # --- Sanitized routes: no top-level combinator, top-level type:object. ---
    anthropic_schema = AnthropicProvider(model="claude-test", api_key="x")._to_anthropic_tool(
        _press_key_tool_def()
    )["input_schema"]
    assert all(c not in anthropic_schema for c in _TOP_LEVEL_COMBINATORS)
    assert anthropic_schema["type"] == "object"

    or_anthropic_schema = OpenRouterProvider(
        model="anthropic/claude-3.5-haiku", api_key="x"
    ).tool_schema(_press_key_tool_def())["function"]["parameters"]
    assert all(c not in or_anthropic_schema for c in _TOP_LEVEL_COMBINATORS)
    assert or_anthropic_schema["type"] == "object"

    # --- Verbatim routes: the top-level `anyOf` combinator is preserved. ---
    openai_schema = OpenAIProvider(model="gpt-4o", api_key="x").tool_schema(
        _press_key_tool_def()
    )["function"]["parameters"]
    assert "anyOf" in openai_schema

    ollama_schema = OllamaProvider(
        model="qwen2.5:7b", base_url="http://t:11434"
    ).tool_schema(_press_key_tool_def())["function"]["parameters"]
    assert "anyOf" in ollama_schema

    or_openai_schema = OpenRouterProvider(model="openai/gpt-4o", api_key="x").tool_schema(
        _press_key_tool_def()
    )["function"]["parameters"]
    assert "anyOf" in or_openai_schema


# ---------------------------------------------------------------------------
# 2. OpenRouter anthropic/* complete()/stream() smoke — and the sent tool was
#    sanitized end-to-end (not just via the standalone tool_schema()).
# ---------------------------------------------------------------------------


def _press_key_sent_params(request_bodies) -> dict:
    """Pull the single sent tool's ``parameters`` from a captured turn-1 body."""
    assert request_bodies, "handler captured no request bodies"
    tools = request_bodies[0].get("tools")
    assert tools and len(tools) == 1, f"expected one sent tool, got {tools!r}"
    return tools[0]["function"]["parameters"]


async def test_openrouter_anthropic_complete_smoke_sanitizes():
    """OpenRouter ``anthropic/*`` ``complete()`` round-trips to the canonical
    ``Message``/``ToolCall`` shape, and the tool schema actually put on the wire
    was sanitized (no top-level combinator) — proving the ``anthropic/*``
    sanitize ran through ``complete()``, not only the standalone test."""
    scripted = make_openrouter([TURN_1, TURN_2])
    prov = scripted.provider
    tool = _press_key_tool_def()
    user = Message.user("press a key")

    m1 = await prov.complete([user], tools=[tool])
    assert isinstance(m1, Message)
    assert len(m1.tool_calls) == 1
    tc = m1.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.name == EXPECTED_TOOL_NAME
    assert tc.arguments == EXPECTED_ARGS

    result = ToolResult(tool_call_id=tc.id, content=TOOL_RESULT_CONTENT)
    m2 = await prov.complete([user, m1, Message.tool(result)], tools=[tool])
    assert isinstance(m2, Message)
    assert m2.tool_calls == []
    assert m2.content == FINAL_ANSWER
    assert scripted.call_count() == 2

    # The sent schema was sanitized on this route.
    sent_params = _press_key_sent_params(scripted.request_bodies)
    assert all(c not in sent_params for c in _TOP_LEVEL_COMBINATORS)
    assert sent_params["type"] == "object"


async def test_openrouter_anthropic_stream_smoke_sanitizes():
    """OpenRouter ``anthropic/*`` ``stream()`` round-trips to the canonical
    shape, and the sent tool schema was sanitized end-to-end."""
    scripted = make_openrouter([TURN_1, TURN_2], streaming=True)
    prov = scripted.provider
    tool = _press_key_tool_def()
    user = Message.user("press a key")

    final1, _ = await _collect_final_chunk(prov.stream([user], tools=[tool]))
    assert final1.message is not None
    assert len(final1.tool_calls) == 1
    tc = final1.tool_calls[0]
    assert tc.name == EXPECTED_TOOL_NAME
    assert tc.arguments == EXPECTED_ARGS

    result = ToolResult(tool_call_id=tc.id, content=TOOL_RESULT_CONTENT)
    final2, _ = await _collect_final_chunk(
        prov.stream([user, final1.message, Message.tool(result)], tools=[tool])
    )
    assert final2.message is not None
    assert final2.tool_calls == []
    assert final2.message.content == FINAL_ANSWER
    assert scripted.call_count() == 2

    sent_params = _press_key_sent_params(scripted.request_bodies)
    assert all(c not in sent_params for c in _TOP_LEVEL_COMBINATORS)
    assert sent_params["type"] == "object"


# ---------------------------------------------------------------------------
# 3. Anthropic stream() temperature-retry → tools.N → tool-name mapping.
# ---------------------------------------------------------------------------


class _RaisingStreamCM:
    """An async-CM whose ``__aenter__`` raises the given exception (pre-delta)."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *exc) -> bool:
        return False


async def test_anthropic_stream_temp_retry_maps_tools_index_to_name():
    """A ``stream()`` whose first submission 400s on ``temperature`` and whose
    retry 400s on ``tools.1.custom.input_schema`` raises a ``BadRequestError``
    naming the tool at index 1 — the ``stream()``-side temp-retry→tools.N
    sub-path (the ``complete()``-side equivalent is already covered)."""
    from the_one.llm.anthropic_provider import AnthropicProvider

    prov = AnthropicProvider(model="claude-test", api_key="x")

    tool0 = {
        "name": "tool_zero",
        "description": "d0",
        "parameters": {"type": "object", "properties": {}},
    }
    tool1 = {
        "name": "tool_one",
        "description": "d1",
        "parameters": {"type": "object", "properties": {}},
    }

    cms = [
        _RaisingStreamCM(make_bad_request("temperature: unsupported")),
        _RaisingStreamCM(make_bad_request("tools.1.custom.input_schema: invalid")),
    ]
    calls: list[dict] = []

    def _stream(**kwargs):
        calls.append(kwargs)
        return cms.pop(0)

    prov.client.messages.stream = _stream  # type: ignore[assignment]

    with pytest.raises(anthropic.BadRequestError) as excinfo:
        async for _ in prov.stream([Message.user("hi")], tools=[tool0, tool1]):
            pass

    assert "tool_one" in str(excinfo.value)
    # Both attempts ran; the retry dropped the temperature kwarg.
    assert len(calls) == 2
    assert "temperature" not in calls[1]


# ---------------------------------------------------------------------------
# 4. DD6 error-format pin: _TOOLS_INDEX_RE matches the known first-party format.
# ---------------------------------------------------------------------------


def test_tools_index_re_matches_known_format():
    """Pin the Anthropic first-party schema-400 error format the ``tools.N``
    → tool-name mapping depends on, so a drift in that wire string surfaces as
    a red test rather than a silently-unnamed tool error."""
    from the_one.llm.anthropic_provider import _TOOLS_INDEX_RE

    m = _TOOLS_INDEX_RE.search("tools.0.custom.input_schema: invalid")
    assert m is not None
    assert m.group(1) == "0"
    assert _TOOLS_INDEX_RE.search("messages.0: unrelated") is None


# ---------------------------------------------------------------------------
# 5. Forward-with-WARN asymmetry (DD3): OpenRouter anthropic/* forwards the
#    unsanitizable schema + WARNs; Anthropic-direct drops it + WARNs.
# ---------------------------------------------------------------------------


def test_unsanitizable_schema_forward_with_warn_vs_drop(caplog):
    """Same genuinely-unsanitizable schema, divergent route handling: on the
    OpenRouter ``anthropic/*`` route ``tool_schema`` forwards it unmodified with
    a WARN; on the Anthropic-direct route ``_build_kwargs`` drops the sole tool
    (omitting ``tools``) with a WARN. The documented #122 minimal-scope
    asymmetry (DD3 vs. DD5)."""
    from the_one.llm.anthropic_provider import AnthropicProvider
    from the_one.llm.openrouter_provider import OpenRouterProvider

    td = {
        "name": "t",
        "description": "d",
        "parameters": copy.deepcopy(UNSANITIZABLE_ANYOF_SCHEMA),
    }

    # --- OpenRouter anthropic/*: forwarded unmodified + WARN. ---
    orp = OpenRouterProvider(model="anthropic/claude-3.5-haiku", api_key="x")
    with caplog.at_level(logging.WARNING, logger="the_one.llm.openrouter_provider"):
        result = orp.tool_schema(copy.deepcopy(td))
    assert result["function"]["parameters"] == UNSANITIZABLE_ANYOF_SCHEMA
    or_warns = [
        r for r in caplog.records if r.name == "the_one.llm.openrouter_provider"
    ]
    assert or_warns, "expected a WARN on the OpenRouter forward path"

    caplog.clear()

    # --- Anthropic-direct: dropped (no "tools" key) + WARN. ---
    aprov = AnthropicProvider(model="claude-test", api_key="x")
    with caplog.at_level(logging.WARNING, logger="the_one.llm.anthropic_provider"):
        kwargs = aprov._build_kwargs([Message.user("hi")], [copy.deepcopy(td)], 0.0, 16)
    assert "tools" not in kwargs
    a_warns = [r for r in caplog.records if r.name == "the_one.llm.anthropic_provider"]
    assert a_warns, "expected a WARN on the Anthropic drop path"


# ===========================================================================
# 6. #105 fixtured loose-format recovery row (M16 F04 L04, DD5)
# ===========================================================================
#
# The hermetic counterpart to the live ``gemma-tool-use-recovery`` behavior
# test: Ollama's ``complete()``/``stream()`` recover a recorded loose-format
# emission (a ```tool fenced Python call, returned with NO structured
# ``tool_calls``) into a structured ``ToolCall`` at the LLMProvider contract
# (provider-level — ``_recover_into_tool_calls`` → ``recover_and_strip``), then
# round-trip a real ``ToolResult`` to a turn-2 final answer.
#
# This is a STANDALONE Ollama-only row, NOT a parametrized matrix entry: the
# matrix uses a structured turn-1, whereas this row's turn-1 is content-only and
# its assertions (recovered synthesized id ``get_weather_0``, ``content == ""``,
# kwargs-form ``arguments == {"city": "Paris"}``) are Ollama-recovery-specific.

# Verbatim from ``tests/test_toolcall_recovery.py:22`` (Flight 1 spike, live
# gemma3:4b): a ```tool fenced Python call returned with ``tool_calls: null``.
# Re-declared (not imported) to keep test-module-to-test-module imports clean;
# the source comment guards against drift. Kwargs form — recovers to named args
# at the provider level (NOT the positional ```tool_code shell form, which parks
# args under POSITIONAL_ARGS_KEY for the dispatcher; out of scope per DD1).
GEMMA_FIXTURE = "```tool\nget_weather(city='Paris')\n```"

# What GEMMA_FIXTURE recovers to (test_toolcall_recovery.py:30-33).
RECOVERED_TOOL_NAME = "get_weather"
RECOVERED_ARGS = {"city": "Paris"}
# The recovery path synthesizes the id as f"{name}_{index}" (ollama_provider.py:48)
# → "get_weather_0", NOT the structured-path "tc_1". Asserted, never hardcoded
# into the ToolResult below — that is read off the recovered call.
RECOVERED_ID = "get_weather_0"
RECOVERY_FINAL_ANSWER = "It is sunny in Paris."


async def test_ollama_recovery_roundtrip_complete(monkeypatch):
    """#105 recovery over ``OllamaProvider.complete()``: a content-only turn-1
    carrying ``GEMMA_FIXTURE`` (no structured ``tool_calls``) drives the
    provider's ``_recover_into_tool_calls`` path, recovering a structured
    ``ToolCall`` with the fence stripped from ``content``; a real ``ToolResult``
    then round-trips to a turn-2 final answer."""
    # Turn 1 is CONTENT-ONLY — no tool_calls — so make_ollama emits a message
    # with a falsy tool_calls and the provider's recovery path fires.
    turn1 = CannedTurn(content=GEMMA_FIXTURE)
    turn2 = CannedTurn(content=RECOVERY_FINAL_ANSWER)
    scripted = make_ollama([turn1, turn2], monkeypatch)
    ollama = scripted.provider
    tool = dict(TOOL_DEF)
    user = Message.user("weather in Paris?")

    m1 = await ollama.complete([user], tools=[tool])
    assert isinstance(m1, Message)
    assert len(m1.tool_calls) == 1
    tc = m1.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.name == RECOVERED_TOOL_NAME
    assert tc.arguments == RECOVERED_ARGS  # kwargs form, no POSITIONAL_ARGS_KEY
    assert tc.id == RECOVERED_ID  # synthesized "get_weather_0", not "tc_1"
    assert m1.content == ""  # the fence was the whole message; stripped to ""

    # Read the recovered id off the call — do NOT hardcode the structured "tc_1".
    result = ToolResult(tool_call_id=tc.id, content="sunny, 22C")
    m2 = await ollama.complete([user, m1, Message.tool(result)], tools=[tool])
    assert isinstance(m2, Message)
    assert m2.tool_calls == []
    assert m2.content == RECOVERY_FINAL_ANSWER
    assert m2.content


async def test_ollama_recovery_roundtrip_stream(monkeypatch):
    """#105 recovery over ``OllamaProvider.stream()``: same recovery round-trip,
    asserting on the FINAL chunk only. Interim chunks carry the raw, un-stripped
    content (documented asymmetry at ollama_provider.py:261-266); the final
    chunk's message carries the stripped content + recovered ToolCall."""
    turn1 = CannedTurn(content=GEMMA_FIXTURE)
    turn2 = CannedTurn(content=RECOVERY_FINAL_ANSWER)
    scripted = make_ollama([turn1, turn2], monkeypatch, streaming=True)
    ollama = scripted.provider
    tool = dict(TOOL_DEF)
    user = Message.user("weather in Paris?")

    final1, _ = await _collect_final_chunk(ollama.stream([user], tools=[tool]))
    assert final1.message is not None
    assert isinstance(final1.message, Message)
    assert len(final1.tool_calls) == 1
    assert final1.tool_calls == final1.message.tool_calls
    tc = final1.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.name == RECOVERED_TOOL_NAME
    assert tc.arguments == RECOVERED_ARGS
    assert tc.id == RECOVERED_ID
    assert final1.message.content == ""  # stripped on the final chunk

    result = ToolResult(tool_call_id=tc.id, content="sunny, 22C")
    final2, _ = await _collect_final_chunk(
        ollama.stream([user, final1.message, Message.tool(result)], tools=[tool])
    )
    assert final2.message is not None
    assert final2.tool_calls == []
    assert final2.message.tool_calls == []
    assert final2.message.content == RECOVERY_FINAL_ANSWER
    assert final2.message.content
