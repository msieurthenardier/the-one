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
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message

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
