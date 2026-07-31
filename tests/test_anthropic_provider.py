"""Tests for AnthropicProvider tool-schema sanitization + BadRequestError net.

Mocked-client unit suite for flight M16 F02 leg 02 (wire-into-anthropic-adapter).
No network: the SDK ``messages.create`` / ``messages.stream`` are replaced with
mocks, so these run host-native without a container.

Covers:
- Sanitize-before-send (DD1/DD2): top-level anyOf flattened, non-mutation at the
  adapter boundary, clean-schema passthrough.
- Drop-and-proceed (DD5): one bad tool dropped (rest sent), named+reason warning,
  all-tools-unsanitizable omits the ``tools`` key.
- BadRequestError → tool-name (DD6): temperature branch fires first, tools.N → name
  in complete() and stream(), index-shift maps post-drop, temperature-retry's
  second call name-maps (complete only), unparseable/out-of-range falls back to the
  original error, non-tools.N re-raised unchanged.
- No regression: streaming happy path still yields content + final tool-call chunk.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

import anthropic
import pytest

from tests.fixtures.tool_schemas import make_bad_request
from the_one.llm.anthropic_provider import (
    AnthropicProvider,
    _coerce_bool,
    resolve_extended_thinking,
)
from the_one.llm.base import (
    ContentBlock,
    ImageContent,
    Message,
    TextContent,
    ThinkingBlock,
    ToolCall,
    ToolResult,
)

_LOGGER_NAME = "the_one.llm.anthropic_provider"


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


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
    """Async callable recording the kwargs of each ``messages.create`` call.

    Optional ``side_effects`` is a list applied per call: an Exception is raised,
    anything else is returned. Falls back to ``default_response`` once exhausted.
    """

    def __init__(
        self,
        side_effects: list[Any] | None = None,
        default_response: Any = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._side_effects = list(side_effects or [])
        self._default = default_response if default_response is not None else _StubResponse()

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._side_effects:
            effect = self._side_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return effect
        return self._default


def _provider_with_create(monkeypatch, recorder: _CreateRecorder) -> AnthropicProvider:
    """Build a provider whose ``client.messages.create`` is the recorder."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(model="claude-test")
    monkeypatch.setattr(prov.client.messages, "create", recorder)
    return prov


def _user_msg() -> list[Message]:
    return [Message.user("hello")]


def _tool(name: str, parameters: dict | None) -> dict[str, Any]:
    return {"name": name, "description": f"desc for {name}", "parameters": parameters}


# --------------------------------------------------------------------------
# Sanitize-before-send (DD1/DD2)
# --------------------------------------------------------------------------


async def test_sanitize_press_key_anyof_no_top_level_anyof(monkeypatch):
    """A top-level anyOf (press_key fixture) is flattened: input_schema has no
    top-level anyOf and type == 'object'."""
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)
    press_key = _tool(
        "press_key",
        {
            "type": "object",
            "anyOf": [
                {"properties": {"key": {"type": "string"}}, "required": ["key"]},
                {"properties": {"combo": {"type": "string"}}, "required": ["combo"]},
            ],
        },
    )

    await prov.complete(_user_msg(), tools=[press_key])

    sent = rec.calls[0]["tools"]
    schema = sent[0]["input_schema"]
    assert "anyOf" not in schema
    assert schema["type"] == "object"
    assert "key" in schema["properties"] and "combo" in schema["properties"]


async def test_adapter_boundary_non_mutation(monkeypatch):
    """After a complete() call, the original tool ``parameters`` dict is
    is-identical and byte-unchanged (adapter never writes back)."""
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)
    params = {
        "type": "object",
        "anyOf": [
            {"properties": {"key": {"type": "string"}}, "required": ["key"]},
        ],
    }
    tool = _tool("press_key", params)
    original_params_obj = tool["parameters"]
    snapshot = copy.deepcopy(params)

    await prov.complete(_user_msg(), tools=[tool])

    # is-identical: the adapter did not re-assign into the source.
    assert tool["parameters"] is original_params_obj
    # byte-unchanged: the kernel deep-copied; the source is intact.
    assert tool["parameters"] == snapshot


async def test_clean_schema_passthrough(monkeypatch):
    """A clean flat-object schema passes through in substance (near no-op)."""
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)
    clean = _tool(
        "lookup",
        {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    )

    await prov.complete(_user_msg(), tools=[clean])

    schema = rec.calls[0]["tools"][0]["input_schema"]
    assert schema["type"] == "object"
    assert schema["properties"] == {"q": {"type": "string"}}
    assert schema["required"] == ["q"]


async def test_missing_parameters_key_becomes_object(monkeypatch):
    """A tool with no ``parameters`` key → input_schema {'type': 'object'}."""
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)
    tool = {"name": "noparams", "description": "d"}  # no "parameters"

    await prov.complete(_user_msg(), tools=[tool])

    assert rec.calls[0]["tools"][0]["input_schema"] == {"type": "object"}


# --------------------------------------------------------------------------
# Drop-and-proceed (DD5)
# --------------------------------------------------------------------------


async def test_one_bad_tool_dropped_rest_succeed(monkeypatch):
    """Three tools, middle one unsanitizable (bare top-level $ref): the two good
    tools are sent (by name), bad one absent, no exception bubbles out."""
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)
    tools = [
        _tool("good_a", {"type": "object", "properties": {"a": {"type": "string"}}}),
        _tool("bad", {"$ref": "#/$defs/Thing"}),  # bare $ref → unsanitizable
        _tool("good_b", {"type": "object", "properties": {"b": {"type": "string"}}}),
    ]

    await prov.complete(_user_msg(), tools=tools)

    sent = rec.calls[0]["tools"]
    names = [t["name"] for t in sent]
    assert names == ["good_a", "good_b"]


async def test_drop_warning_names_tool_and_reason(monkeypatch, caplog):
    """The drop emits a warning naming the tool AND including the reason."""
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)
    tools = [_tool("press_key", {"$ref": "#/$defs/Thing"})]

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        await prov.complete(_user_msg(), tools=tools)

    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    assert records, "expected a warning record from the adapter logger"
    # Search all records for the tool-drop warning (catalog-miss warning may
    # precede it now that the resolver logs on a cache miss for 'claude-test').
    drop_records = [r for r in records if "press_key" in r.getMessage()]
    assert drop_records, (
        f"expected a drop warning naming press_key; got: {[r.getMessage() for r in records]}"
    )
    msg = drop_records[0].getMessage()
    assert "press_key" in msg
    # reason text from the kernel (bare $ref branch)
    assert "$ref" in msg


async def test_all_tools_unsanitizable_omits_tools_key(monkeypatch):
    """All tools unsanitizable → kwargs has no 'tools' key; the turn still runs."""
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)
    tools = [
        _tool("bad1", {"$ref": "#/$defs/A"}),
        _tool("bad2", {"type": "string"}),  # non-object scalar → unsanitizable
    ]

    await prov.complete(_user_msg(), tools=tools)

    assert "tools" not in rec.calls[0]
    assert len(rec.calls) == 1  # call proceeded


# --------------------------------------------------------------------------
# BadRequestError → tool-name (DD6) — complete()
# --------------------------------------------------------------------------


async def test_temperature_branch_fires_first(monkeypatch):
    """A BadRequestError containing 'temperature' triggers the existing retry
    (temperature popped, second call succeeds, no name-mapping)."""
    rec = _CreateRecorder(
        side_effects=[make_bad_request("temperature: unsupported")],
        default_response=_StubResponse(),
    )
    prov = _provider_with_create(monkeypatch, rec)
    tools = [_tool("t", {"type": "object", "properties": {"x": {"type": "string"}}})]

    result = await prov.complete(_user_msg(), tools=tools)

    assert isinstance(result, Message)
    assert len(rec.calls) == 2  # original + retry
    assert "temperature" not in rec.calls[1]  # popped before retry


async def test_tools_n_maps_to_name_complete(monkeypatch):
    """A tools.N schema-400 is re-raised naming kwargs['tools'][N]['name']."""
    err = make_bad_request("tools.1.custom.input_schema: invalid")
    rec = _CreateRecorder(side_effects=[err])
    prov = _provider_with_create(monkeypatch, rec)
    tools = [
        _tool("first", {"type": "object", "properties": {"a": {"type": "string"}}}),
        _tool("second", {"type": "object", "properties": {"b": {"type": "string"}}}),
    ]

    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_user_msg(), tools=tools)

    msg = str(ei.value)
    assert "second" in msg  # tool name (index 1)
    assert "tools.1" in msg  # original error text preserved
    assert ei.value.__cause__ is err


async def test_index_shift_maps_post_drop_complete(monkeypatch):
    """With a tool dropped before the offending one, tools.1 maps against the
    post-drop list (names the right tool, not the pre-drop index-1 tool)."""
    err = make_bad_request("tools.1.custom.input_schema: invalid")
    rec = _CreateRecorder(side_effects=[err])
    prov = _provider_with_create(monkeypatch, rec)
    tools = [
        _tool("good_a", {"type": "object", "properties": {"a": {"type": "string"}}}),
        _tool("dropped", {"$ref": "#/$defs/X"}),  # dropped — shifts later indices
        _tool("good_b", {"type": "object", "properties": {"b": {"type": "string"}}}),
    ]

    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_user_msg(), tools=tools)

    # post-drop list is [good_a, good_b]; index 1 → "good_b"
    assert "good_b" in str(ei.value)


async def test_temperature_retry_second_call_name_maps_complete(monkeypatch):
    """First 400 on temperature, retry 400s on tools.N → retry failure is also
    name-mapped (complete() only)."""
    temp_err = make_bad_request("temperature: unsupported")
    tools_err = make_bad_request("tools.0.custom.input_schema: invalid")
    rec = _CreateRecorder(side_effects=[temp_err, tools_err])
    prov = _provider_with_create(monkeypatch, rec)
    tools = [_tool("only_tool", {"type": "object", "properties": {"x": {"type": "string"}}})]

    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_user_msg(), tools=tools)

    assert "only_tool" in str(ei.value)
    assert ei.value.__cause__ is tools_err
    assert len(rec.calls) == 2


async def test_unparseable_index_falls_back_to_original_complete(monkeypatch):
    """A tools.N error whose index is out of range → original error re-raised
    unchanged (no name-mapping, no IndexError)."""
    err = make_bad_request("tools.9.custom.input_schema: invalid")
    rec = _CreateRecorder(side_effects=[err])
    prov = _provider_with_create(monkeypatch, rec)
    tools = [_tool("only", {"type": "object", "properties": {"x": {"type": "string"}}})]

    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_user_msg(), tools=tools)

    assert ei.value is err  # the exact original, unchanged


async def test_non_tools_n_reraised_unchanged_complete(monkeypatch):
    """A non-temperature, non-tools.N BadRequestError is re-raised unchanged."""
    err = make_bad_request("messages.0: something unrelated")
    rec = _CreateRecorder(side_effects=[err])
    prov = _provider_with_create(monkeypatch, rec)
    tools = [_tool("t", {"type": "object", "properties": {"x": {"type": "string"}}})]

    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_user_msg(), tools=tools)

    assert ei.value is err


# --------------------------------------------------------------------------
# Streaming helpers + tests
# --------------------------------------------------------------------------


class _AsyncTextStream:
    """Async iterator over text deltas."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._texts:
            raise StopAsyncIteration
        return self._texts.pop(0)


class _StreamCM:
    """Async-context-manager stand-in for ``client.messages.stream(**kwargs)``.

    Exposes an async ``text_stream`` and an awaitable ``get_final_message()``.
    If ``raise_on_enter`` is set, raises it from ``__aenter__`` (models a
    submission-time 400, which arrives before any delta).
    """

    def __init__(
        self,
        texts: list[str],
        final: Any,
        raise_on_enter: BaseException | None = None,
    ) -> None:
        self._texts = texts
        self._final = final
        self._raise_on_enter = raise_on_enter

    async def __aenter__(self):
        if self._raise_on_enter is not None:
            raise self._raise_on_enter
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    @property
    def text_stream(self) -> _AsyncTextStream:
        return _AsyncTextStream(list(self._texts))

    async def get_final_message(self) -> Any:
        return self._final


class _StreamRecorder:
    """Sync callable (matches the SDK's ``messages.stream``) returning a CM per call.

    ``factories`` is a list of zero-arg callables producing the CM for each call.
    """

    def __init__(self, factories: list[Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._factories = list(factories)

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        factory = self._factories.pop(0)
        return factory()


def _provider_with_stream(monkeypatch, recorder: _StreamRecorder) -> AnthropicProvider:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(model="claude-test")
    monkeypatch.setattr(prov.client.messages, "stream", recorder)
    return prov


async def test_streaming_happy_path_smoke(monkeypatch):
    """A normal (no-400) stream yields content chunks + a final tool-call chunk."""
    final = _StubResponse(
        content=[
            _StubContentBlock("text", text="hello world"),
            _StubContentBlock("tool_use", id="tu_1", name="do_thing", input={"x": 1}),
        ],
        usage=None,
    )
    rec = _StreamRecorder([lambda: _StreamCM(["hello ", "world"], final)])
    prov = _provider_with_stream(monkeypatch, rec)
    tools = [_tool("do_thing", {"type": "object", "properties": {"x": {"type": "integer"}}})]

    chunks = [c async for c in prov.stream(_user_msg(), tools=tools)]

    content = "".join(c.content for c in chunks if not c.is_final)
    assert "hello world" in content
    final_chunks = [c for c in chunks if c.is_final]
    assert len(final_chunks) == 1
    assert final_chunks[0].tool_calls
    assert final_chunks[0].tool_calls[0].name == "do_thing"


async def test_tools_n_maps_to_name_stream(monkeypatch):
    """A submission-time tools.N 400 in stream() is re-raised naming the tool."""
    err = make_bad_request("tools.1.custom.input_schema: invalid")
    rec = _StreamRecorder([lambda: _StreamCM([], None, raise_on_enter=err)])
    prov = _provider_with_stream(monkeypatch, rec)
    tools = [
        _tool("alpha", {"type": "object", "properties": {"a": {"type": "string"}}}),
        _tool("beta", {"type": "object", "properties": {"b": {"type": "string"}}}),
    ]

    with pytest.raises(anthropic.BadRequestError) as ei:
        async for _ in prov.stream(_user_msg(), tools=tools):
            pass

    msg = str(ei.value)
    assert "beta" in msg
    assert "tools.1" in msg
    assert ei.value.__cause__ is err


async def test_non_tools_n_reraised_unchanged_stream(monkeypatch):
    """A non-temperature, non-tools.N 400 in stream() is re-raised unchanged."""
    err = make_bad_request("messages.0: unrelated")
    rec = _StreamRecorder([lambda: _StreamCM([], None, raise_on_enter=err)])
    prov = _provider_with_stream(monkeypatch, rec)
    tools = [_tool("t", {"type": "object", "properties": {"x": {"type": "string"}}})]

    with pytest.raises(anthropic.BadRequestError) as ei:
        async for _ in prov.stream(_user_msg(), tools=tools):
            pass

    assert ei.value is err


async def test_temperature_branch_fires_first_stream(monkeypatch):
    """A submission-time temperature 400 in stream() triggers the retry; the
    retry's stream succeeds (temperature popped)."""
    temp_err = make_bad_request("temperature: unsupported")
    final = _StubResponse(content=[_StubContentBlock("text", text="ok")], usage=None)
    rec = _StreamRecorder(
        [
            lambda: _StreamCM([], None, raise_on_enter=temp_err),
            lambda: _StreamCM(["ok"], final),
        ]
    )
    prov = _provider_with_stream(monkeypatch, rec)
    tools = [_tool("t", {"type": "object", "properties": {"x": {"type": "string"}}})]

    chunks = [c async for c in prov.stream(_user_msg(), tools=tools)]

    assert any("ok" in c.content for c in chunks if not c.is_final)
    assert len(rec.calls) == 2
    assert "temperature" not in rec.calls[1]


# --------------------------------------------------------------------------
# M16 F10 L03: extended-thinking on/off resolver (unit)
# --------------------------------------------------------------------------


def test_coerce_bool_real_bools_pass_through():
    assert _coerce_bool(True) is True
    assert _coerce_bool(False) is False


def test_coerce_bool_truthy_strings():
    for v in ("1", "true", "TRUE", "yes", "on", " On "):
        assert _coerce_bool(v) is True


def test_coerce_bool_falsy_strings():
    for v in ("0", "false", "FALSE", "no", "off", ""):
        assert _coerce_bool(v) is False


def test_coerce_bool_ints():
    assert _coerce_bool(1) is True
    assert _coerce_bool(5) is True
    assert _coerce_bool(0) is False


def test_coerce_bool_unrecognized_and_other_types_none():
    assert _coerce_bool(None) is None
    assert _coerce_bool("abc") is None
    assert _coerce_bool("maybe") is None
    assert _coerce_bool(1.5) is None
    assert _coerce_bool([]) is None


def test_resolve_extended_thinking_config_true(monkeypatch):
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    assert resolve_extended_thinking(True) is True


def test_resolve_extended_thinking_config_wins_over_env(monkeypatch):
    monkeypatch.setenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", "false")
    # configured True takes precedence over a falsy env
    assert resolve_extended_thinking(True) is True


def test_resolve_extended_thinking_config_false_short_circuits(monkeypatch):
    monkeypatch.setenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", "true")
    # explicit config False must NOT fall through to a truthy env
    assert resolve_extended_thinking(False) is False


def test_resolve_extended_thinking_falls_through_to_env(monkeypatch):
    monkeypatch.setenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", "1")
    assert resolve_extended_thinking(None) is True
    monkeypatch.setenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", "0")
    assert resolve_extended_thinking(None) is False


def test_resolve_extended_thinking_default_off_when_unset(monkeypatch):
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    assert resolve_extended_thinking(None) is False


def test_resolve_extended_thinking_env_junk_off(monkeypatch):
    monkeypatch.setenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", "not-a-bool")
    assert resolve_extended_thinking(None) is False


# --------------------------------------------------------------------------
# M16 F10 L03: __init__ config read
# --------------------------------------------------------------------------


def _provider_with_create_config(monkeypatch, recorder, config) -> AnthropicProvider:
    """Build a config-bearing provider whose ``messages.create`` is the recorder."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(model="claude-test", config=config)
    monkeypatch.setattr(prov.client.messages, "create", recorder)
    return prov


def test_init_reads_thinking_enabled_from_config(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(model="claude-test", config={"thinking_enabled": True})
    assert prov._thinking_enabled_config is True


def test_init_thinking_enabled_none_when_absent_or_non_dict(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert AnthropicProvider(model="claude-test")._thinking_enabled_config is None
    assert AnthropicProvider(model="claude-test", config=None)._thinking_enabled_config is None
    assert AnthropicProvider(model="claude-test", config="nope")._thinking_enabled_config is None
    assert AnthropicProvider(model="claude-test", config={})._thinking_enabled_config is None


def test_init_thinking_enabled_false_preserved(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(model="claude-test", config={"thinking_enabled": False})
    assert prov._thinking_enabled_config is False


# --------------------------------------------------------------------------
# M16 F10 L03: _build_kwargs adaptive enablement / suppression
# --------------------------------------------------------------------------


async def test_thinking_enabled_sets_adaptive_no_temperature_force(monkeypatch):
    """config thinking_enabled=True → adaptive; no budget_tokens; temperature and
    max_tokens LEFT at the caller's values (DD6 forcing is gone)."""
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rec = _CreateRecorder()
    prov = _provider_with_create_config(monkeypatch, rec, {"thinking_enabled": True})

    await prov.complete(_user_msg(), temperature=0.0, max_tokens=16384)

    sent = rec.calls[0]
    assert sent["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert "budget_tokens" not in sent["thinking"]
    # Load-bearing proof DD6's forcing is gone: caller's values untouched.
    assert sent["temperature"] == 0.0
    assert sent["max_tokens"] == 16384


async def test_thinking_disabled_passthrough_byte_identical(monkeypatch):
    """No config → no thinking key; temperature/max_tokens are the caller's values."""
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)  # no config

    await prov.complete(_user_msg(), temperature=0.3, max_tokens=1234)

    sent = rec.calls[0]
    assert "thinking" not in sent
    assert sent["temperature"] == 0.3
    assert sent["max_tokens"] == 1234


async def test_thinking_enabled_false_disables_passthrough(monkeypatch):
    monkeypatch.setenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", "true")
    rec = _CreateRecorder()
    # config False = explicit disable; must NOT fall through to a truthy env.
    prov = _provider_with_create_config(monkeypatch, rec, {"thinking_enabled": False})

    await prov.complete(_user_msg(), temperature=0.3, max_tokens=1234)

    sent = rec.calls[0]
    assert "thinking" not in sent
    assert sent["temperature"] == 0.3
    assert sent["max_tokens"] == 1234


async def test_enable_thinking_false_suppresses(monkeypatch):
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rec = _CreateRecorder()
    prov = _provider_with_create_config(monkeypatch, rec, {"thinking_enabled": True})

    await prov.complete(_user_msg(), temperature=0.3, max_tokens=1234, enable_thinking=False)

    sent = rec.calls[0]
    assert "thinking" not in sent
    assert sent["temperature"] == 0.3


async def test_enable_thinking_none_uses_configured_enable(monkeypatch):
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rec = _CreateRecorder()
    prov = _provider_with_create_config(monkeypatch, rec, {"thinking_enabled": True})

    await prov.complete(_user_msg(), enable_thinking=None)

    assert rec.calls[0]["thinking"] == {"type": "adaptive", "display": "summarized"}


# --------------------------------------------------------------------------
# M16 F10 L02: capture on complete()
# --------------------------------------------------------------------------


async def test_complete_captures_thinking_block(monkeypatch):
    resp = _StubResponse(
        content=[
            _StubContentBlock("thinking", thinking="reasoning...", signature="sig-123"),
            _StubContentBlock("text", text="the answer"),
            _StubContentBlock("tool_use", id="tu_1", name="do_thing", input={"x": 1}),
        ],
        usage=None,
    )
    rec = _CreateRecorder(default_response=resp)
    prov = _provider_with_create(monkeypatch, rec)

    msg = await prov.complete(_user_msg())

    assert len(msg.thinking) == 1
    assert msg.thinking[0].type == "thinking"
    assert msg.thinking[0].thinking == "reasoning..."
    assert msg.thinking[0].signature == "sig-123"
    # text and tool_use handling unchanged
    assert msg.content == "the answer"
    assert msg.tool_calls[0].name == "do_thing"


async def test_complete_captures_redacted_thinking_block(monkeypatch):
    resp = _StubResponse(
        content=[
            _StubContentBlock("redacted_thinking", data="opaque-blob"),
            _StubContentBlock("text", text="hi"),
        ],
        usage=None,
    )
    rec = _CreateRecorder(default_response=resp)
    prov = _provider_with_create(monkeypatch, rec)

    msg = await prov.complete(_user_msg())

    assert len(msg.thinking) == 1
    blk = msg.thinking[0]
    assert blk.type == "redacted_thinking"
    assert blk.data == "opaque-blob"
    assert blk.thinking is None
    assert blk.signature is None


async def test_complete_no_thinking_blocks_empty_list(monkeypatch):
    resp = _StubResponse(content=[_StubContentBlock("text", text="plain")], usage=None)
    rec = _CreateRecorder(default_response=resp)
    prov = _provider_with_create(monkeypatch, rec)

    msg = await prov.complete(_user_msg())

    assert msg.thinking == []
    assert msg.content == "plain"


# --------------------------------------------------------------------------
# M16 F10 L02: capture on the streaming path
# --------------------------------------------------------------------------


async def test_stream_captures_thinking_in_final_message(monkeypatch):
    final = _StubResponse(
        content=[
            _StubContentBlock("thinking", thinking="stream reasoning", signature="sig-s"),
            _StubContentBlock("text", text="hello world"),
        ],
        usage=None,
    )
    rec = _StreamRecorder([lambda: _StreamCM(["hello ", "world"], final)])
    prov = _provider_with_stream(monkeypatch, rec)

    chunks = [c async for c in prov.stream(_user_msg())]

    # No thinking text leaks into the streamed content deltas.
    streamed = "".join(c.content for c in chunks if not c.is_final)
    assert "hello world" in streamed
    assert "stream reasoning" not in streamed
    # The final chunk's synthesized message carries the thinking block.
    final_chunks = [c for c in chunks if c.is_final]
    assert len(final_chunks) == 1
    msg = final_chunks[0].message
    assert len(msg.thinking) == 1
    assert msg.thinking[0].type == "thinking"
    assert msg.thinking[0].signature == "sig-s"


# --------------------------------------------------------------------------
# M16 F10 L02: non-thinking-model error is non-fatal (plain re-raise)
# --------------------------------------------------------------------------


async def test_non_thinking_model_error_reraised_unchanged(monkeypatch):
    """A BadRequestError naming an unsupported-thinking/model condition (not
    temperature, not tools.N) propagates cleanly out of complete()."""
    err = make_bad_request("messages: thinking is not supported for model claude-test-nonthinking")
    rec = _CreateRecorder(side_effects=[err])
    prov = _provider_with_create_config(monkeypatch, rec, {"thinking_enabled": True})

    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_user_msg())

    assert ei.value is err


async def test_non_thinking_model_error_reraised_unchanged_stream(monkeypatch):
    err = make_bad_request("messages: thinking is not supported for model claude-test-nonthinking")
    rec = _StreamRecorder([lambda: _StreamCM([], None, raise_on_enter=err)])
    prov = AnthropicProvider(model="claude-test", config={"thinking_enabled": True})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(prov.client.messages, "stream", rec)

    with pytest.raises(anthropic.BadRequestError) as ei:
        async for _ in prov.stream(_user_msg()):
            pass

    assert ei.value is err


# --------------------------------------------------------------------------
# M16 F10 L02: inference-suppression (classifier passes enable_thinking=False)
# --------------------------------------------------------------------------


async def test_inference_style_suppression_sends_no_thinking(monkeypatch):
    """A thinking-enabled Anthropic provider driven the way the connector
    classifier drives it (enable_thinking=False, max_tokens=10) records NO
    thinking kwarg — the cheap probe never pays the thinking premium."""
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rec = _CreateRecorder()
    prov = _provider_with_create_config(monkeypatch, rec, {"thinking_enabled": True})

    await prov.complete(
        messages=_user_msg(),
        tools=None,
        temperature=0.0,
        max_tokens=10,
        enable_thinking=False,
    )

    sent = rec.calls[0]
    assert "thinking" not in sent
    assert sent["max_tokens"] == 10


# --------------------------------------------------------------------------
# M16 F10 L04: thinking replay in _to_api_message (DD8: replay-on / strip-off)
# --------------------------------------------------------------------------


def _replay_provider(monkeypatch) -> AnthropicProvider:
    """A bare provider for direct ``_to_api_message`` projection unit tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    return AnthropicProvider(model="claude-test")


def _indices(content: list[dict[str, Any]], block_type: str) -> list[int]:
    return [i for i, b in enumerate(content) if b.get("type") == block_type]


def test_replay_on_orders_thinking_before_text_and_tool_use(monkeypatch):
    """thinking_active=True → content is [thinking, text, tool_use], with the
    thinking block byte-faithful (signature intact) and strictly before tool_use."""
    prov = _replay_provider(monkeypatch)
    msg = Message.assistant(
        "ans",
        tool_calls=[ToolCall(id="tu_1", name="do_thing", arguments={"x": 1})],
        thinking=[ThinkingBlock(type="thinking", thinking="reasoned", signature="sig123")],
    )

    out = prov._to_api_message(msg, thinking_active=True)

    content = out["content"]
    assert content[0] == {"type": "thinking", "thinking": "reasoned", "signature": "sig123"}
    assert content[1] == {"type": "text", "text": "ans"}
    assert content[2] == {"type": "tool_use", "id": "tu_1", "name": "do_thing", "input": {"x": 1}}
    # Explicit ordering lock: thinking strictly precedes tool_use.
    assert _indices(content, "thinking")[0] < _indices(content, "tool_use")[0]


def test_replay_on_two_blocks_preserve_stored_order(monkeypatch):
    """Two stored blocks project at content[0]/content[1] in stored order."""
    prov = _replay_provider(monkeypatch)
    msg = Message.assistant(
        "ans",
        tool_calls=[ToolCall(id="tu_1", name="do_thing", arguments={})],
        thinking=[
            ThinkingBlock(type="thinking", thinking="first", signature="sigA"),
            ThinkingBlock(type="thinking", thinking="second", signature="sigB"),
        ],
    )

    content = prov._to_api_message(msg, thinking_active=True)["content"]

    assert content[0] == {"type": "thinking", "thinking": "first", "signature": "sigA"}
    assert content[1] == {"type": "thinking", "thinking": "second", "signature": "sigB"}


def test_replay_on_redacted_block_emits_only_data(monkeypatch):
    """A redacted_thinking block projects {"type":"redacted_thinking","data":...}
    with no thinking/signature keys."""
    prov = _replay_provider(monkeypatch)
    msg = Message.assistant(
        "ans",
        tool_calls=[ToolCall(id="tu_1", name="do_thing", arguments={})],
        thinking=[ThinkingBlock(type="redacted_thinking", data="opaque-bytes")],
    )

    content = prov._to_api_message(msg, thinking_active=True)["content"]

    assert content[0] == {"type": "redacted_thinking", "data": "opaque-bytes"}
    assert "thinking" not in content[0]
    assert "signature" not in content[0]


def test_strip_off_default_byte_identical_to_no_thinking(monkeypatch):
    """DD8: thinking_active=False (the default) strips stored thinking — the
    projection is byte-identical to a message that never had thinking."""
    prov = _replay_provider(monkeypatch)
    with_thinking = Message.assistant(
        "ans",
        tool_calls=[ToolCall(id="tu_1", name="do_thing", arguments={"x": 1})],
        thinking=[ThinkingBlock(type="thinking", thinking="reasoned", signature="sig123")],
    )
    without_thinking = Message.assistant(
        "ans",
        tool_calls=[ToolCall(id="tu_1", name="do_thing", arguments={"x": 1})],
    )

    off = prov._to_api_message(with_thinking, thinking_active=False)
    # default arg is also False — single-arg legacy callers strip too.
    off_default = prov._to_api_message(with_thinking)
    baseline = prov._to_api_message(without_thinking, thinking_active=True)

    assert off == baseline == off_default
    assert off["content"] == [
        {"type": "text", "text": "ans"},
        {"type": "tool_use", "id": "tu_1", "name": "do_thing", "input": {"x": 1}},
    ]


def test_thinking_only_turn_active_builds_thinking_then_text(monkeypatch):
    """An assistant turn with thinking but no tool_calls enters the widened
    branch ONLY when thinking_active — projecting [thinking, text]."""
    prov = _replay_provider(monkeypatch)
    msg = Message.assistant(
        "ans",
        thinking=[ThinkingBlock(type="thinking", thinking="reasoned", signature="sig123")],
    )

    out = prov._to_api_message(msg, thinking_active=True)

    assert out["content"] == [
        {"type": "thinking", "thinking": "reasoned", "signature": "sig123"},
        {"type": "text", "text": "ans"},
    ]


def test_thinking_only_turn_off_falls_to_plain_string_branch(monkeypatch):
    """The same thinking-only turn with thinking_active=False falls through to
    the plain-string branch (unchanged legacy projection)."""
    prov = _replay_provider(monkeypatch)
    msg = Message.assistant(
        "ans",
        thinking=[ThinkingBlock(type="thinking", thinking="reasoned", signature="sig123")],
    )

    out = prov._to_api_message(msg, thinking_active=False)

    assert out == {"role": "assistant", "content": "ans"}


def test_empty_thinking_tool_turn_is_no_op(monkeypatch):
    """An assistant tool turn with empty thinking + thinking_active=True projects
    [text, tool_use] — no empty/None thinking noise."""
    prov = _replay_provider(monkeypatch)
    msg = Message.assistant(
        "ans",
        tool_calls=[ToolCall(id="tu_1", name="do_thing", arguments={})],
    )

    content = prov._to_api_message(msg, thinking_active=True)["content"]

    assert content == [
        {"type": "text", "text": "ans"},
        {"type": "tool_use", "id": "tu_1", "name": "do_thing", "input": {}},
    ]


def _thinking_tool_history() -> list[Message]:
    """[user, assistant(thinking+tool_calls), tool_result] — the criterion #1
    follow-up shape that 400s unless thinking is replayed before tool_use."""
    return [
        Message.user("do the thing"),
        Message.assistant(
            "working on it",
            tool_calls=[ToolCall(id="tu_1", name="do_thing", arguments={"x": 1})],
            thinking=[ThinkingBlock(type="thinking", thinking="reasoned", signature="sig123")],
        ),
        Message.tool(ToolResult(tool_call_id="tu_1", content="done")),
    ]


def _assistant_entry(messages: list[dict[str, Any]]) -> dict[str, Any]:
    return next(m for m in messages if m["role"] == "assistant")


async def test_end_to_end_replay_on_records_thinking_before_tool_use(monkeypatch):
    """DD8 replay-on end-to-end: a thinking-enabled provider records the assistant
    entry with thinking-before-tool_use AND kwargs["thinking"] == adaptive."""
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rec = _CreateRecorder()
    prov = _provider_with_create_config(monkeypatch, rec, {"thinking_enabled": True})

    await prov.complete(_thinking_tool_history())

    sent = rec.calls[0]
    assert sent["thinking"] == {"type": "adaptive", "display": "summarized"}
    assistant = _assistant_entry(sent["messages"])
    content = assistant["content"]
    thinking_idx = _indices(content, "thinking")
    tool_idx = _indices(content, "tool_use")
    assert thinking_idx and tool_idx
    assert thinking_idx[0] < tool_idx[0]
    assert content[thinking_idx[0]] == {
        "type": "thinking",
        "thinking": "reasoned",
        "signature": "sig123",
    }


async def test_end_to_end_strip_off_records_no_thinking(monkeypatch):
    """Hermetic DD8 strip-off end-to-end: the same history with thinking disabled
    records an assistant entry with NO thinking block AND no "thinking" kwarg."""
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)  # no thinking config

    await prov.complete(_thinking_tool_history())

    sent = rec.calls[0]
    assert "thinking" not in sent
    assistant = _assistant_entry(sent["messages"])
    assert _indices(assistant["content"], "thinking") == []


async def test_end_to_end_enable_thinking_false_strips_replay(monkeypatch):
    """A thinking-enabled provider with enable_thinking=False on the call strips
    replay too (mid-session disable): no thinking block, no thinking kwarg."""
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    rec = _CreateRecorder()
    prov = _provider_with_create_config(monkeypatch, rec, {"thinking_enabled": True})

    await prov.complete(_thinking_tool_history(), enable_thinking=False)

    sent = rec.calls[0]
    assert "thinking" not in sent
    assistant = _assistant_entry(sent["messages"])
    assert _indices(assistant["content"], "thinking") == []


# --------------------------------------------------------------------------
# M16 F11 L02 (A4): reasoning_effort / response_format / stop wiring
# --------------------------------------------------------------------------


def test_init_reads_a4_config(monkeypatch):
    """__init__ coerces the three A4 config keys into instance attrs."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(
        model="claude-test",
        config={
            "reasoning_effort": "high",
            "response_format": {"type": "json_schema", "schema": {"type": "object"}},
            "stop": ["</s>"],
        },
    )
    assert prov._reasoning_effort_config == "high"
    assert prov._response_format_config == {"type": "json_schema", "schema": {"type": "object"}}
    assert prov._stop_config == ["</s>"]


def test_init_a4_config_none_when_absent_or_non_dict(monkeypatch):
    """Absent/None/non-dict/junk config coerces all three A4 attrs to None,
    never raising (mirrors test_init_thinking_enabled_none_when_absent_or_non_dict)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    for prov in (
        AnthropicProvider(model="claude-test"),
        AnthropicProvider(model="claude-test", config=None),
        AnthropicProvider(model="claude-test", config="nope"),
        AnthropicProvider(model="claude-test", config={}),
        AnthropicProvider(model="claude-test", config={"reasoning_effort": True}),
    ):
        assert prov._reasoning_effort_config is None
        assert prov._response_format_config is None
        assert prov._stop_config is None


def _prov_with_config(config: dict[str, Any] | None) -> AnthropicProvider:
    return AnthropicProvider(model="claude-test", api_key="x", config=config)


async def test_build_kwargs_stop_wired():
    """resolve_stop non-empty -> kwargs['stop_sequences']; unset -> key absent."""
    prov = _prov_with_config({"stop": ["</s>", "STOP"]})
    kwargs = prov._build_kwargs([Message.user("hi")], None, 0.0, 16384)
    assert kwargs["stop_sequences"] == ["</s>", "STOP"]

    prov_unset = _prov_with_config(None)
    kwargs_unset = prov_unset._build_kwargs([Message.user("hi")], None, 0.0, 16384)
    assert "stop_sequences" not in kwargs_unset


async def test_build_kwargs_reasoning_effort_wired():
    """resolve_reasoning_effort non-empty -> output_config['effort']; unset -> no effort key."""
    prov = _prov_with_config({"reasoning_effort": "high"})
    kwargs = prov._build_kwargs([Message.user("hi")], None, 0.0, 16384)
    assert kwargs["output_config"]["effort"] == "high"

    prov_unset = _prov_with_config(None)
    kwargs_unset = prov_unset._build_kwargs([Message.user("hi")], None, 0.0, 16384)
    assert "output_config" not in kwargs_unset


async def test_build_kwargs_response_format_json_schema_wired():
    """Canonical json_schema -> output_config['format'] verbatim (type + schema)."""
    prov = _prov_with_config(
        {"response_format": {"type": "json_schema", "schema": {"type": "object"}}}
    )
    kwargs = prov._build_kwargs([Message.user("hi")], None, 0.0, 16384)
    assert kwargs["output_config"]["format"] == {
        "type": "json_schema",
        "schema": {"type": "object"},
    }


async def test_build_kwargs_response_format_json_object_noop_warns(caplog):
    """Canonical json_object sets no output_config['format'] on Anthropic and
    logs a warning naming the reason (no bare JSON mode on this surface)."""
    prov = _prov_with_config({"response_format": {"type": "json_object"}})
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        kwargs = prov._build_kwargs([Message.user("hi")], None, 0.0, 16384)

    assert "output_config" not in kwargs
    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    assert any("json_schema-only" in r.message or "json_schema" in r.message for r in records)


async def test_build_kwargs_output_config_omitted_when_empty():
    """Neither effort nor format set -> no output_config key at all (never empty)."""
    prov = _prov_with_config({})
    kwargs = prov._build_kwargs([Message.user("hi")], None, 0.0, 16384)
    assert "output_config" not in kwargs


async def test_build_kwargs_effort_coexists_with_thinking(monkeypatch):
    """thinking_enabled + reasoning_effort both present -> both kwargs['thinking']
    and kwargs['output_config']['effort'] set, neither clobbers the other."""
    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    prov = _prov_with_config({"thinking_enabled": True, "reasoning_effort": "high"})
    kwargs = prov._build_kwargs([Message.user("hi")], None, 0.0, 16384)
    assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kwargs["output_config"]["effort"] == "high"


async def test_build_kwargs_a4_none_path_no_config_no_env(monkeypatch):
    """No A4 config and no A4 env -> neither stop_sequences nor output_config appears."""
    monkeypatch.delenv("THE_ONE_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("THE_ONE_RESPONSE_FORMAT", raising=False)
    monkeypatch.delenv("THE_ONE_STOP", raising=False)
    prov = _prov_with_config(None)
    kwargs = prov._build_kwargs([Message.user("hi")], None, 0.0, 16384)
    assert "stop_sequences" not in kwargs
    assert "output_config" not in kwargs


async def test_temperature_retry_preserves_a4_kwargs(monkeypatch):
    """The temperature-retry only pops 'temperature'; the retried call still
    carries stop_sequences and output_config from A4 config."""
    rec = _CreateRecorder(
        side_effects=[make_bad_request("temperature: unsupported")],
        default_response=_StubResponse(),
    )
    prov = _provider_with_create_config(
        monkeypatch, rec, {"stop": ["</s>"], "reasoning_effort": "high"}
    )

    result = await prov.complete(_user_msg())

    assert isinstance(result, Message)
    assert len(rec.calls) == 2  # original + retry
    retried = rec.calls[1]
    assert "temperature" not in retried
    assert retried["stop_sequences"] == ["</s>"]
    assert retried["output_config"]["effort"] == "high"


# --------------------------------------------------------------------------
# M16 F12 L04: image projection in _to_api_message's USER-turn list branch
# --------------------------------------------------------------------------


def test_image_projection_base64_and_url_blocks(monkeypatch):
    """A list-content USER message maps text/base64-image/url-image blocks
    to Anthropic's native content-block shape, in order."""
    prov = _replay_provider(monkeypatch)
    blocks: list[ContentBlock] = [
        TextContent(text="hi"),
        ImageContent(media_type="image/png", data="BASE64"),
        ImageContent(media_type="image/jpeg", url="https://x/y.jpg"),
    ]
    msg = Message.user(blocks)

    out = prov._to_api_message(msg)

    assert out == {
        "role": "user",
        "content": [
            {"type": "text", "text": "hi"},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": "BASE64"},
            },
            {
                "type": "image",
                "source": {"type": "url", "url": "https://x/y.jpg"},
            },
        ],
    }


def test_image_projection_base64_preferred_over_url(monkeypatch):
    """DD5: when an ImageContent carries both data and url, base64 wins."""
    prov = _replay_provider(monkeypatch)
    msg = Message.user([ImageContent(media_type="image/png", data="BASE64", url="https://x/y.png")])

    content = prov._to_api_message(msg)["content"]

    assert content == [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "BASE64"},
        }
    ]


def test_image_projection_prefix_block_mapped_natively(monkeypatch):
    """With peer_name/channel_name set on a list-content USER message, the
    projected content begins with a native text block carrying the DD4
    bracket prefix, followed by the user's own blocks."""
    prov = _replay_provider(monkeypatch)
    msg = Message.user(
        [TextContent(text="hello"), ImageContent(media_type="image/png", data="BASE64")],
        peer_name="alice",
        channel_name="general",
    )

    content = prov._to_api_message(msg)["content"]

    assert content[0] == {"type": "text", "text": "[from alice in #general]:"}
    assert content[1] == {"type": "text", "text": "hello"}
    assert content[2] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "BASE64"},
    }


def test_str_content_projection_byte_identical(monkeypatch):
    """The plain str-content path is untouched by the DD4 fork — same output
    as before the multimodal branch existed."""
    prov = _replay_provider(monkeypatch)
    msg = Message.user("hello there", peer_name="bob")

    out = prov._to_api_message(msg)

    assert out == {"role": "user", "content": "[from bob]: hello there"}


def test_str_content_projection_no_peer_channel_byte_identical(monkeypatch):
    """Legacy no-prefix str path stays a plain string, unaffected by the fork."""
    prov = _replay_provider(monkeypatch)
    msg = Message.user("plain text")

    out = prov._to_api_message(msg)

    assert out == {"role": "user", "content": "plain text"}


# --------------------------------------------------------------------------
# AnthropicPlanProvider skeleton (M19 F01 L01 — DD-4, Leg-1 half)
# --------------------------------------------------------------------------


def test_plan_provider_registry_construction_bearer_mode(monkeypatch):
    """get_provider('anthropic-plan', ...) returns an AnthropicPlanProvider
    whose client is in bearer mode (auth_token set, x-api-key path unused)
    with the OAuth beta header, and which stored provider_config_id."""
    # Env must not be able to flip the client into x-api-key mode.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-must-not-leak")

    from the_one.llm import get_provider
    from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider

    provider = get_provider(
        "anthropic-plan",
        model="claude-sonnet-4-6",
        api_key=None,
        config={"thinking_enabled": True},
        provider_config_id="prov-123",
        access_token="test-token",
    )
    assert isinstance(provider, AnthropicPlanProvider)
    assert isinstance(provider, AnthropicProvider)  # inherits the full adapter
    assert provider.name == "anthropic-plan"
    assert provider.provider_config_id == "prov-123"
    assert provider.client.auth_token == "test-token"
    assert provider.client.api_key is None, "x-api-key path must be unused (env must not leak)"
    assert provider.client.default_headers.get("anthropic-beta") == "oauth-2025-04-20"
    # Parent config parsing still runs (skeleton overrides client build only).
    assert provider._thinking_enabled_config is True


def test_plan_provider_constructs_without_access_token(monkeypatch):
    """No-token construction succeeds — client carries auth_token=None and
    fails at request time (no raise requirement in Leg 1)."""
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider

    provider = AnthropicPlanProvider(model="claude-sonnet-4-6")
    assert provider.client.auth_token is None
    assert provider.client.api_key is None
    assert provider.provider_config_id is None


def test_plan_provider_ignores_stored_api_key(monkeypatch):
    """A config-stored api_key arg is deliberately ignored — plan providers
    authenticate with the OAuth bearer token only."""
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider

    provider = AnthropicPlanProvider(
        model="claude-sonnet-4-6", api_key="sk-stored", access_token="tok"
    )
    assert provider.client.api_key is None
    assert provider.client.auth_token == "tok"


# --------------------------------------------------------------------------
# _before_request hook (M19 F01 L02 — DD-3/DD-4, Leg-2 half)
# --------------------------------------------------------------------------


class _FakeCredentialSource:
    """Stand-in for ``plan_credentials.PlanCredentialSource``."""

    def __init__(self, token: str | None = "tok-from-source", error: Exception | None = None):
        self.token = token
        self.error = error
        self.calls = 0

    async def get_access_token(self) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.token  # type: ignore[return-value]


def _plan_provider(monkeypatch, **kwargs):
    from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    return AnthropicPlanProvider(model="claude-test", **kwargs)


async def test_before_request_noop_on_api_key_provider(monkeypatch):
    """The parent hook is a no-op returning None — API-key provider behavior
    unchanged."""
    prov = _provider_with_create(monkeypatch, _CreateRecorder())
    assert await prov._before_request() is None


async def test_complete_awaits_before_request_hook(monkeypatch):
    """``complete()`` awaits the hook before touching the SDK client."""
    rec = _CreateRecorder()
    prov = _provider_with_create(monkeypatch, rec)
    order: list[str] = []

    async def _hook() -> None:
        order.append("hook")
        assert rec.calls == [], "hook must run before the SDK call"

    monkeypatch.setattr(prov, "_before_request", _hook)
    await prov.complete(_user_msg())
    assert order == ["hook"]
    assert len(rec.calls) == 1


async def test_stream_awaits_hook_at_first_iteration(monkeypatch):
    """``stream()`` is an async generator: creating it does NOT run the hook;
    the hook (and any error it raises) surfaces at first iteration. Pinned so
    nobody 'fixes' this into an eager coroutine."""
    prov = _provider_with_create(monkeypatch, _CreateRecorder())
    calls: list[str] = []

    async def _hook() -> None:
        calls.append("hook")
        raise RuntimeError("hook error surfaces during iteration")

    monkeypatch.setattr(prov, "_before_request", _hook)
    gen = prov.stream(_user_msg())
    assert calls == [], "generator creation must not run the hook"
    with pytest.raises(RuntimeError, match="during iteration"):
        await gen.__anext__()
    assert calls == ["hook"]


async def test_plan_static_token_short_circuits_source(monkeypatch):
    """Explicit ``access_token`` kwarg wins: the registry is never consulted
    (conformance/test back-door precedence)."""
    prov = _plan_provider(monkeypatch, access_token="static-tok", provider_config_id="prov-1")

    def _boom(_pid):
        raise AssertionError("registry must not be consulted for static-token providers")

    monkeypatch.setattr("the_one.llm.plan_credentials.get_credential_source", _boom)
    await prov._before_request()
    assert prov.client.auth_token == "static-tok"


async def test_plan_before_request_applies_token_in_place(monkeypatch):
    """The hook mutates ``client.auth_token`` on the SAME client instance —
    no rebuild (DD-4 in-place decision)."""
    prov = _plan_provider(monkeypatch, provider_config_id="prov-1")
    client_before = prov.client
    fake = _FakeCredentialSource(token="tok-fresh")
    monkeypatch.setattr("the_one.llm.plan_credentials.get_credential_source", lambda _pid: fake)
    await prov._before_request()
    assert prov.client is client_before
    assert prov.client.auth_token == "tok-fresh"
    assert fake.calls == 1


async def test_plan_auth_token_mutation_premise_pin(monkeypatch):
    """SDK-premise pin (anthropic 0.96.0, verified at design review): the
    bearer header is generated per-request from ``client.auth_token``
    (``_bearer_auth`` property via ``_build_headers``) — nothing is cached at
    construction, so in-place mutation takes effect WITHOUT rebuilding the
    client. If an SDK upgrade caches auth at construction, this fails."""
    prov = _plan_provider(monkeypatch, access_token="tok-A", provider_config_id="p1")
    client = prov.client
    assert client.auth_headers == {"Authorization": "Bearer tok-A"}
    client.auth_token = "tok-B"
    assert client.auth_headers == {"Authorization": "Bearer tok-B"}, (
        "anthropic SDK no longer reads auth_token per-request — the in-place "
        "mutation strategy in AnthropicPlanProvider._before_request is broken; "
        "switch to rebuild-and-close (see M19 F01 DD-4)"
    )
    # And the header actually rides a built request, not just the property.
    request = client._build_request(
        __import__("anthropic")._models.FinalRequestOptions(method="post", url="/v1/messages")
    )
    assert request.headers["Authorization"] == "Bearer tok-B"


async def test_plan_reauth_error_propagates_from_complete(monkeypatch):
    """The typed re-auth error from the source surfaces out of ``complete()``
    (not swallowed, not converted into a bare SDK auth error)."""
    from the_one.llm.plan_credentials import ReauthRequiredError

    prov = _plan_provider(monkeypatch, provider_config_id="prov-1")
    fake = _FakeCredentialSource(error=ReauthRequiredError("prov-1"))
    monkeypatch.setattr("the_one.llm.plan_credentials.get_credential_source", lambda _pid: fake)
    with pytest.raises(ReauthRequiredError) as excinfo:
        await prov.complete(_user_msg())
    assert excinfo.value.provider_id == "prov-1"
    assert "re-authentication" in str(excinfo.value)


async def test_plan_reauth_error_surfaces_during_stream_iteration(monkeypatch):
    from the_one.llm.plan_credentials import ReauthRequiredError

    prov = _plan_provider(monkeypatch, provider_config_id="prov-1")
    fake = _FakeCredentialSource(error=ReauthRequiredError("prov-1"))
    monkeypatch.setattr("the_one.llm.plan_credentials.get_credential_source", lambda _pid: fake)
    gen = prov.stream(_user_msg())  # creating the generator must not raise
    with pytest.raises(ReauthRequiredError):
        await gen.__anext__()


async def test_plan_without_token_or_config_id_raises_reauth(monkeypatch):
    """A plan provider with neither a static token nor a provider_config_id
    fails actionably at ``_before_request`` time — never a bare SDK auth
    error at the wire."""
    from the_one.llm.plan_credentials import ReauthRequiredError

    prov = _plan_provider(monkeypatch)
    with pytest.raises(ReauthRequiredError) as excinfo:
        await prov.complete(_user_msg())
    assert "Administration" in str(excinfo.value)
