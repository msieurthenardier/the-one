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
from the_one.llm.base import Message, ThinkingBlock, ToolCall, ToolResult

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
