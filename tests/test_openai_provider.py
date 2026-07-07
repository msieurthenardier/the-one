"""Tests for the A4 request-param wiring (M16 F11 L03): reasoning_effort /
response_format / stop into OpenAIProvider's two request sites, plus the
config->attr read shared with OpenRouterProvider (which skips
super().__init__() and therefore needs its own call to the same helper).

No network: OpenAI's persistent ``client`` is replaced with an
``AsyncOpenAI`` wrapping an ``httpx.MockTransport`` (the exact pattern
``tests/fixtures/scripted_transport.py::make_openai`` uses internally) so
these run host-native without a container. Per the leg's Implementation
Guidance, the shared conformance harness is NOT expanded here (that's L05) —
these tests build providers directly.

Covers:
- ``_read_a4_config`` config->attr reads for BOTH OpenAIProvider and
  OpenRouterProvider (present + absent/None/non-dict/junk -> None).
- ``_a4_request_kwargs`` mapping: stop/effort passthrough, response_format
  json_object direct, json_schema re-wrap (synthesized + caller-supplied
  name), empty -> {}.
- config->wire integration for BOTH providers on BOTH complete()/stream().
- None-path: no config + the three A4 env vars unset -> _a4_request_kwargs()
  is {} and neither request site adds the three keys.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import openai
import pytest

from the_one.llm.base import Message
from the_one.llm.openai_provider import OpenAIProvider
from the_one.llm.openrouter_provider import OpenRouterProvider

_A4_ENV_VARS = (
    "THE_ONE_REASONING_EFFORT",
    "THE_ONE_RESPONSE_FORMAT",
    "THE_ONE_STOP",
)


def _delenv_a4(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _A4_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# _read_a4_config — __init__ reads, both providers
# ---------------------------------------------------------------------------


class TestInitReadsA4Config:
    def test_openai_reads_a4_config(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(
            model="gpt-4o",
            api_key="x",
            config={
                "reasoning_effort": "high",
                "response_format": {"type": "json_schema", "schema": {"type": "object"}},
                "stop": ["</s>"],
            },
        )
        assert prov._reasoning_effort_config == "high"
        assert prov._response_format_config == {
            "type": "json_schema",
            "schema": {"type": "object"},
        }
        assert prov._stop_config == ["</s>"]

    @pytest.mark.parametrize(
        "config",
        [None, "nope", {}, {"reasoning_effort": True}],
        ids=["absent-none", "non-dict-str", "empty-dict", "junk-bool"],
    )
    def test_openai_a4_config_none_when_absent_or_junk(self, monkeypatch, config):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(model="gpt-4o", api_key="x", config=config)
        assert prov._reasoning_effort_config is None
        assert prov._response_format_config is None
        assert prov._stop_config is None

    def test_openai_a4_config_none_when_kwarg_absent_entirely(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(model="gpt-4o", api_key="x")
        assert prov._reasoning_effort_config is None
        assert prov._response_format_config is None
        assert prov._stop_config is None

    def test_openrouter_reads_a4_config(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenRouterProvider(
            model="m",
            api_key="x",
            config={
                "reasoning_effort": "high",
                "response_format": {"type": "json_schema", "schema": {"type": "object"}},
                "stop": ["</s>"],
            },
        )
        assert prov._reasoning_effort_config == "high"
        assert prov._response_format_config == {
            "type": "json_schema",
            "schema": {"type": "object"},
        }
        assert prov._stop_config == ["</s>"]

    @pytest.mark.parametrize(
        "config",
        [None, "nope", {}, {"reasoning_effort": True}],
        ids=["absent-none", "non-dict-str", "empty-dict", "junk-bool"],
    )
    def test_openrouter_a4_config_none_when_absent_or_junk(self, monkeypatch, config):
        _delenv_a4(monkeypatch)
        prov = OpenRouterProvider(model="m", api_key="x", config=config)
        assert prov._reasoning_effort_config is None
        assert prov._response_format_config is None
        assert prov._stop_config is None

    def test_openrouter_a4_config_none_when_kwarg_absent_entirely(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenRouterProvider(model="m", api_key="x")
        assert prov._reasoning_effort_config is None
        assert prov._response_format_config is None
        assert prov._stop_config is None


# ---------------------------------------------------------------------------
# _a4_request_kwargs — mapping to native OpenAI shapes
# ---------------------------------------------------------------------------


class TestA4RequestKwargsMapping:
    def test_stop_passthrough(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(model="gpt-4o", api_key="x", config={"stop": ["</s>", "STOP"]})
        assert prov._a4_request_kwargs() == {"stop": ["</s>", "STOP"]}

    def test_reasoning_effort_passthrough(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(model="gpt-4o", api_key="x", config={"reasoning_effort": "high"})
        assert prov._a4_request_kwargs() == {"reasoning_effort": "high"}

    def test_response_format_json_object(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(
            model="gpt-4o", api_key="x", config={"response_format": {"type": "json_object"}}
        )
        assert prov._a4_request_kwargs() == {"response_format": {"type": "json_object"}}

    def test_response_format_json_schema_synthesizes_name(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(
            model="gpt-4o",
            api_key="x",
            config={"response_format": {"type": "json_schema", "schema": {"type": "object"}}},
        )
        assert prov._a4_request_kwargs() == {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": {"type": "object"}},
            }
        }

    def test_response_format_json_schema_honors_caller_name(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(
            model="gpt-4o",
            api_key="x",
            config={
                "response_format": {
                    "type": "json_schema",
                    "schema": {"type": "object"},
                    "name": "my_schema",
                }
            },
        )
        assert prov._a4_request_kwargs() == {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "my_schema", "schema": {"type": "object"}},
            }
        }

    def test_all_three_together(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(
            model="gpt-4o",
            api_key="x",
            config={
                "stop": ["</s>"],
                "reasoning_effort": "medium",
                "response_format": {"type": "json_object"},
            },
        )
        assert prov._a4_request_kwargs() == {
            "stop": ["</s>"],
            "reasoning_effort": "medium",
            "response_format": {"type": "json_object"},
        }

    def test_empty_when_nothing_configured(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(model="gpt-4o", api_key="x")
        assert prov._a4_request_kwargs() == {}


# ---------------------------------------------------------------------------
# config->wire — direct provider construction + injected httpx.MockTransport
# (the make_openai internal pattern, scripted_transport.py ~:300-307). Not
# the shared harness (make_openai/make_openrouter accept no `config` kwarg).
# ---------------------------------------------------------------------------


def _recording_transport() -> tuple[httpx.MockTransport, list[dict[str, Any]]]:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            bodies.append(json.loads(request.content))
        except (ValueError, TypeError):
            bodies.append({})
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": "gpt-test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    return httpx.MockTransport(handler), bodies


def _inject_transport(prov: OpenAIProvider) -> list[dict[str, Any]]:
    """Replace ``prov.client`` with an AsyncOpenAI wrapping a recording
    MockTransport — the exact pattern ``make_openai`` uses internally
    (scripted_transport.py ~:300-307)."""
    transport, bodies = _recording_transport()
    prov.client = openai.AsyncOpenAI(
        api_key="x",
        base_url=str(prov.client.base_url),
        http_client=httpx.AsyncClient(transport=transport),
    )
    return bodies


_A4_CONFIG = {
    "reasoning_effort": "high",
    "response_format": {"type": "json_schema", "schema": {"type": "object"}, "name": "foo"},
    "stop": ["</s>"],
}


class TestConfigToWireOpenAI:
    async def test_complete_sends_a4_params(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(model="gpt-4o", api_key="x", config=_A4_CONFIG)
        bodies = _inject_transport(prov)

        await prov.complete([Message.user("hi")])

        assert len(bodies) == 1
        body = bodies[0]
        assert body["stop"] == ["</s>"]
        assert body["reasoning_effort"] == "high"
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "foo", "schema": {"type": "object"}},
        }

    async def test_stream_sends_a4_params(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(model="gpt-4o", api_key="x", config=_A4_CONFIG)
        transport, bodies = _recording_transport()

        def stream_handler(request: httpx.Request) -> httpx.Response:
            try:
                bodies.append(json.loads(request.content))
            except (ValueError, TypeError):
                bodies.append({})
            sse = (
                "data: "
                + json.dumps({"choices": [{"index": 0, "delta": {"content": "ok"}}]})
                + "\n\n"
                + "data: "
                + json.dumps({"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
                + "\n\n"
                + "data: [DONE]\n\n"
            )
            return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

        prov.client = openai.AsyncOpenAI(
            api_key="x",
            base_url=str(prov.client.base_url),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(stream_handler)),
        )

        chunks = [c async for c in prov.stream([Message.user("hi")])]
        assert len(chunks) >= 1
        assert len(bodies) == 1
        body = bodies[0]
        assert body["stop"] == ["</s>"]
        assert body["reasoning_effort"] == "high"
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "foo", "schema": {"type": "object"}},
        }

    async def test_complete_none_path_omits_a4_keys(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OpenAIProvider(model="gpt-4o", api_key="x")
        bodies = _inject_transport(prov)

        await prov.complete([Message.user("hi")])

        assert prov._a4_request_kwargs() == {}
        body = bodies[0]
        assert "stop" not in body
        assert "reasoning_effort" not in body
        assert "response_format" not in body


class TestConfigToWireOpenRouter:
    """DD5: OpenRouter overrides neither complete() nor stream(), so once
    OpenAI's request assembly forwards the A4 params they are inherited for
    free — asserted here as config->wire, not attribute-existence alone."""

    def _build(self, monkeypatch, config: dict[str, Any] | None) -> OpenRouterProvider:
        _delenv_a4(monkeypatch)
        prov = OpenRouterProvider(model="m", api_key="x", config=config)
        # Hermeticity: OpenRouterProvider._resolve_max_context_tokens hits the
        # network via its own client, not the injected MockTransport (mirrors
        # scripted_transport.py::make_openrouter). Pre-flip the sentinel.
        prov._max_context_tokens_resolved = True
        return prov

    async def test_complete_sends_a4_params(self, monkeypatch):
        prov = self._build(monkeypatch, _A4_CONFIG)
        bodies = _inject_transport(prov)

        await prov.complete([Message.user("hi")])

        assert len(bodies) == 1
        body = bodies[0]
        assert body["stop"] == ["</s>"]
        assert body["reasoning_effort"] == "high"
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "foo", "schema": {"type": "object"}},
        }

    async def test_stream_sends_a4_params(self, monkeypatch):
        prov = self._build(monkeypatch, _A4_CONFIG)
        transport, bodies = _recording_transport()

        def stream_handler(request: httpx.Request) -> httpx.Response:
            try:
                bodies.append(json.loads(request.content))
            except (ValueError, TypeError):
                bodies.append({})
            sse = (
                "data: "
                + json.dumps({"choices": [{"index": 0, "delta": {"content": "ok"}}]})
                + "\n\n"
                + "data: "
                + json.dumps({"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
                + "\n\n"
                + "data: [DONE]\n\n"
            )
            return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

        prov.client = openai.AsyncOpenAI(
            api_key="x",
            base_url=str(prov.client.base_url),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(stream_handler)),
        )

        chunks = [c async for c in prov.stream([Message.user("hi")])]
        assert len(chunks) >= 1
        assert len(bodies) == 1
        body = bodies[0]
        assert body["stop"] == ["</s>"]
        assert body["reasoning_effort"] == "high"
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "foo", "schema": {"type": "object"}},
        }

    async def test_complete_none_path_omits_a4_keys(self, monkeypatch):
        prov = self._build(monkeypatch, None)
        bodies = _inject_transport(prov)

        await prov.complete([Message.user("hi")])

        assert prov._a4_request_kwargs() == {}
        body = bodies[0]
        assert "stop" not in body
        assert "reasoning_effort" not in body
        assert "response_format" not in body
