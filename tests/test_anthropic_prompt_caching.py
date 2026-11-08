"""Sortie 14: Anthropic prompt caching in ``AnthropicProvider``.

Offline. Covers the DD1 breakpoints, the DD2 usage mapping and the DD5
strip-and-retry ladder (complete and stream), over the three provider types.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import anthropic
import pytest

from tests.fixtures.tool_schemas import make_bad_request
from tests.test_anthropic_provider import (
    _CreateRecorder,
    _provider_with_create,
    _provider_with_stream,
    _StreamCM,
    _StreamRecorder,
    _StubContentBlock,
    _StubResponse,
    _tool,
)
from the_one.llm.anthropic_provider import (
    _CACHE_CONTROL,
    AnthropicProvider,
    _usage_from_sdk,
)
from the_one.llm.base import Message, TokenUsage

_LOGGER = "the_one.llm.anthropic_provider"
_TOOLS = [_tool("t", {"type": "object", "properties": {"x": {"type": "string"}}})]


def _msgs(system: str | None = "be brief") -> list[Message]:
    out = [Message.system(system)] if system else []
    return out + [Message.user("hello")]


def _sdk_usage(**kw: Any) -> Any:
    return SimpleNamespace(**kw)


# --------------------------------------------------------------------------
# DD1: breakpoints
# --------------------------------------------------------------------------


def test_build_kwargs_marks_system_and_top_level(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(model="claude-test")
    kw = prov._build_kwargs(_msgs(), _TOOLS, 0.0, 100)
    assert kw["system"] == [
        {"type": "text", "text": "be brief", "cache_control": {"type": "ephemeral"}}
    ]
    assert kw["cache_control"] == {"type": "ephemeral"}


def test_build_kwargs_no_system_still_sends_top_level(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(model="claude-test")
    kw = prov._build_kwargs(_msgs(None), None, 0.0, 100)
    assert "system" not in kw
    assert kw["cache_control"] == {"type": "ephemeral"}


def test_both_markers_carry_equal_values_from_one_constant(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    prov = AnthropicProvider(model="claude-test")
    kw = prov._build_kwargs(_msgs(), None, 0.0, 100)
    assert kw["system"][0]["cache_control"] == kw["cache_control"] == _CACHE_CONTROL
    # copies, not the shared constant
    assert kw["cache_control"] is not _CACHE_CONTROL
    assert kw["system"][0]["cache_control"] is not kw["cache_control"]


def test_three_provider_types_build_identical_kwargs(monkeypatch):
    from the_one.llm.anthropic_plan_provider import (
        AnthropicPlanProvider,
        AnthropicPlanTokenProvider,
    )

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    plain = AnthropicProvider(model="claude-test", api_key="sk-test")
    plan = AnthropicPlanProvider(model="claude-test", access_token="oauth-tok")
    token = AnthropicPlanTokenProvider(model="claude-test", access_token="tok")
    built = [p._build_kwargs(_msgs(), _TOOLS, 0.0, 100) for p in (plain, plan, token)]
    assert built[0] == built[1] == built[2]
    assert "cache_control" in built[0]


# --------------------------------------------------------------------------
# DD2: usage mapping
# --------------------------------------------------------------------------


def test_usage_mapping_sums_whole_prompt():
    u = _usage_from_sdk(
        _sdk_usage(
            input_tokens=3,
            output_tokens=9,
            cache_creation_input_tokens=323,
            cache_read_input_tokens=8628,
        )
    )
    assert u.input_tokens == 3 + 323 + 8628
    assert u.cache_write_tokens == 323
    assert u.cache_read_tokens == 8628
    assert u.output_tokens == 9


@pytest.mark.parametrize("junk", [None, "n/a", 1.5, MagicMock()])
def test_non_int_cache_fields_count_as_zero(junk):
    u = _usage_from_sdk(
        _sdk_usage(
            input_tokens=11,
            output_tokens=2,
            cache_creation_input_tokens=junk,
            cache_read_input_tokens=junk,
        )
    )
    assert u == TokenUsage(11, 2, 0, 0)


def test_missing_cache_attributes_count_as_zero():
    assert _usage_from_sdk(_sdk_usage(input_tokens=5, output_tokens=1)) == TokenUsage(5, 1)


def test_zero_cache_returns_raw_input_object_unchanged():
    raw = object()
    mock_usage = MagicMock(input_tokens=raw, output_tokens=1)
    assert _usage_from_sdk(mock_usage).input_tokens is raw


def test_positional_token_usage_still_works():
    u = TokenUsage(3, 4)
    assert (u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cache_write_tokens) == (
        3,
        4,
        0,
        0,
    )


async def test_complete_maps_cache_usage(monkeypatch):
    usage = _sdk_usage(
        input_tokens=3,
        output_tokens=5,
        cache_creation_input_tokens=100,
        cache_read_input_tokens=900,
    )
    prov = _provider_with_create(
        monkeypatch, _CreateRecorder(default_response=_StubResponse(usage=usage))
    )
    msg = await prov.complete(_msgs(), tools=_TOOLS)
    assert msg.usage == TokenUsage(1003, 5, 900, 100)


async def test_stream_maps_cache_usage(monkeypatch):
    usage = _sdk_usage(
        input_tokens=3,
        output_tokens=5,
        cache_creation_input_tokens=100,
        cache_read_input_tokens=900,
    )
    final = _StubResponse(content=[_StubContentBlock("text", text="ok")], usage=usage)
    prov = _provider_with_stream(monkeypatch, _StreamRecorder([lambda: _StreamCM(["ok"], final)]))
    chunks = [c async for c in prov.stream(_msgs(), tools=_TOOLS)]
    assert chunks[-1].usage == TokenUsage(1003, 5, 900, 100)


# --------------------------------------------------------------------------
# DD5: strip ladder, complete
# --------------------------------------------------------------------------


def _cache_400() -> anthropic.BadRequestError:
    return make_bad_request("cache_control: Extra inputs are not permitted")


def _type_error(name: str) -> TypeError:
    return TypeError(f"create() got an unexpected keyword argument '{name}'")


async def test_complete_cache_400_strips_markers_and_restores_system(monkeypatch, caplog):
    rec = _CreateRecorder(side_effects=[_cache_400()])
    prov = _provider_with_create(monkeypatch, rec)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        await prov.complete(_msgs(), tools=_TOOLS)
    assert len(rec.calls) == 2
    assert "cache_control" in rec.calls[0]
    assert "cache_control" not in rec.calls[1]
    assert rec.calls[1]["system"] == "be brief"
    assert prov._cache_disabled is True
    assert any("cache_control" in r.getMessage() for r in caplog.records if r.name == _LOGGER)


async def test_complete_cache_400_without_system_leaves_system_alone(monkeypatch):
    rec = _CreateRecorder(side_effects=[_cache_400()])
    prov = _provider_with_create(monkeypatch, rec)
    await prov.complete(_msgs(None), tools=_TOOLS)
    assert "system" not in rec.calls[1]
    assert "cache_control" not in rec.calls[1]


async def test_complete_type_error_cache_control_strips_and_disables(monkeypatch):
    rec = _CreateRecorder(side_effects=[_type_error("cache_control")])
    prov = _provider_with_create(monkeypatch, rec)
    await prov.complete(_msgs(), tools=_TOOLS)
    assert len(rec.calls) == 2
    assert "cache_control" not in rec.calls[1]
    assert rec.calls[1]["system"] == "be brief"
    assert prov._cache_disabled is True


async def test_complete_temperature_400_strips_only_temperature(monkeypatch):
    rec = _CreateRecorder(side_effects=[make_bad_request("temperature: unsupported")])
    prov = _provider_with_create(monkeypatch, rec)
    await prov.complete(_msgs(), tools=_TOOLS)
    assert "temperature" not in rec.calls[1]
    assert "cache_control" in rec.calls[1]  # caching untouched
    assert prov._cache_disabled is False


async def test_complete_type_error_other_kwarg_still_strips(monkeypatch):
    rec = _CreateRecorder(side_effects=[_type_error("temperature")])
    prov = _provider_with_create(monkeypatch, rec)
    await prov.complete(_msgs(), tools=_TOOLS)
    assert "temperature" not in rec.calls[1]
    assert "cache_control" in rec.calls[1]


async def test_complete_unrelated_type_error_reraises(monkeypatch):
    rec = _CreateRecorder(side_effects=[TypeError("boom")])
    prov = _provider_with_create(monkeypatch, rec)
    with pytest.raises(TypeError, match="boom"):
        await prov.complete(_msgs(), tools=_TOOLS)
    assert len(rec.calls) == 1


async def test_complete_type_error_cache_then_temperature_400_succeeds(monkeypatch):
    """The composition the old nested retry could not do: an old SDK without
    ``cache_control`` AND a model that rejects ``temperature``."""
    rec = _CreateRecorder(
        side_effects=[_type_error("cache_control"), make_bad_request("temperature: unsupported")]
    )
    prov = _provider_with_create(monkeypatch, rec)
    msg = await prov.complete(_msgs(), tools=_TOOLS)
    assert isinstance(msg, Message)
    assert len(rec.calls) == 3
    assert "cache_control" not in rec.calls[2]
    assert "temperature" not in rec.calls[2]


async def test_complete_repeat_temperature_400_reraises_not_loops(monkeypatch):
    err1 = make_bad_request("temperature: unsupported")
    err2 = make_bad_request("tools.0.custom.input_schema: temperature bad")
    rec = _CreateRecorder(side_effects=[err1, err2])
    prov = _provider_with_create(monkeypatch, rec)
    with pytest.raises(anthropic.BadRequestError) as ei:
        await prov.complete(_msgs(), tools=_TOOLS)
    assert len(rec.calls) == 2
    assert "'t'" in str(ei.value)  # tools.N mapping applied to the final 400


async def test_complete_repeat_cache_400_reraises_not_loops(monkeypatch):
    rec = _CreateRecorder(side_effects=[_cache_400(), _cache_400()])
    prov = _provider_with_create(monkeypatch, rec)
    with pytest.raises(anthropic.BadRequestError):
        await prov.complete(_msgs(), tools=_TOOLS)
    assert len(rec.calls) == 2


async def test_cache_disabled_persists_across_calls(monkeypatch):
    rec = _CreateRecorder(side_effects=[_cache_400()])
    prov = _provider_with_create(monkeypatch, rec)
    await prov.complete(_msgs(), tools=_TOOLS)
    await prov.complete(_msgs(), tools=_TOOLS)
    assert len(rec.calls) == 3  # 1 failed + 1 retry + 1 clean next call
    assert "cache_control" not in rec.calls[2]
    assert rec.calls[2]["system"] == "be brief"


# --------------------------------------------------------------------------
# DD5: strip ladder, stream
# --------------------------------------------------------------------------


def _ok_cm() -> _StreamCM:
    final = _StubResponse(content=[_StubContentBlock("text", text="ok")], usage=None)
    return _StreamCM(["ok"], final)


async def _drain(prov: AnthropicProvider, messages: list[Message] | None = None) -> list[Any]:
    return [c async for c in prov.stream(messages or _msgs(), tools=_TOOLS)]


async def test_stream_cache_400_strips_and_retries(monkeypatch):
    rec = _StreamRecorder([lambda: _StreamCM([], None, raise_on_enter=_cache_400()), _ok_cm])
    prov = _provider_with_stream(monkeypatch, rec)
    await _drain(prov)
    assert len(rec.calls) == 2
    assert "cache_control" not in rec.calls[1]
    assert rec.calls[1]["system"] == "be brief"
    assert prov._cache_disabled is True


async def test_stream_type_error_cache_control_strips_and_retries(monkeypatch):
    rec = _StreamRecorder(
        [lambda: _StreamCM([], None, raise_on_enter=_type_error("cache_control")), _ok_cm]
    )
    prov = _provider_with_stream(monkeypatch, rec)
    await _drain(prov)
    assert "cache_control" not in rec.calls[1]
    assert prov._cache_disabled is True


async def test_stream_type_error_cache_then_temperature_400_succeeds(monkeypatch):
    rec = _StreamRecorder(
        [
            lambda: _StreamCM([], None, raise_on_enter=_type_error("cache_control")),
            lambda: _StreamCM(
                [], None, raise_on_enter=make_bad_request("temperature: unsupported")
            ),
            _ok_cm,
        ]
    )
    prov = _provider_with_stream(monkeypatch, rec)
    chunks = await _drain(prov)
    assert chunks[-1].is_final
    assert len(rec.calls) == 3
    assert "cache_control" not in rec.calls[2]
    assert "temperature" not in rec.calls[2]


async def test_stream_repeat_400_reraises_with_tool_name(monkeypatch):
    rec = _StreamRecorder(
        [
            lambda: _StreamCM([], None, raise_on_enter=make_bad_request("temperature: no")),
            lambda: _StreamCM(
                [], None, raise_on_enter=make_bad_request("tools.0.custom: temperature bad")
            ),
        ]
    )
    prov = _provider_with_stream(monkeypatch, rec)
    with pytest.raises(anthropic.BadRequestError) as ei:
        await _drain(prov)
    assert len(rec.calls) == 2
    assert "'t'" in str(ei.value)


class _MidStreamFailCM(_StreamCM):
    """Yields one text delta, then raises a cache 400 mid-stream."""

    @property
    def text_stream(self):
        async def gen():
            yield "partial"
            raise _cache_400()

        return gen()


async def test_stream_never_retries_after_a_yielded_chunk(monkeypatch):
    rec = _StreamRecorder([lambda: _MidStreamFailCM([], None), _ok_cm])
    prov = _provider_with_stream(monkeypatch, rec)
    seen: list[str] = []
    with pytest.raises(anthropic.BadRequestError):
        async for c in prov.stream(_msgs(), tools=_TOOLS):
            seen.append(c.content)
    assert seen == ["partial"]
    assert len(rec.calls) == 1
    assert prov._cache_disabled is False


async def test_stream_cache_disabled_persists(monkeypatch):
    rec = _StreamRecorder(
        [lambda: _StreamCM([], None, raise_on_enter=_cache_400()), _ok_cm, _ok_cm]
    )
    prov = _provider_with_stream(monkeypatch, rec)
    await _drain(prov)
    await _drain(prov)
    assert len(rec.calls) == 3
    assert "cache_control" not in rec.calls[2]
