"""Tests for the A4 request-param wiring (M16 F11 L04): reasoning_effort /
response_format / stop into OllamaProvider's TWO wire dialects — the ``/v1``
OpenAI-compat path (``complete``'s ``payload`` / ``stream``'s ``body``) and
the native ``/api/chat`` path (``_native_options``/``_native_body``).

No network for the native-mapping tests (pure ``_native_body``/
``_native_options`` calls). The ``/v1`` config->wire tests use the
transport-mock idiom already established in ``tests/test_ollama_provider_auth.py``
(Ollama builds its ``httpx.AsyncClient`` inline — no injectable ``http_client``
— so the mock monkeypatches ``httpx.AsyncClient.__init__`` to inject a
``transport=httpx.MockTransport(handler)``), NOT the OpenAI injectable-client
approach from L03.

Covers:
- ``__init__`` A4 config reads (present + absent/None/non-dict/junk -> None),
  mirroring ``tests/test_anthropic_provider.py::test_init_reads_a4_config``.
- ``_v1_a4_kwargs()`` mapping: stop/effort passthrough, response_format
  json_object direct, json_schema re-wrap (synthesized + caller-supplied
  name), empty -> {}. Byte-for-byte the same mapping as
  ``OpenAIProvider._a4_request_kwargs``.
- native mapping: ``_native_options`` adds ``options["stop"]``;
  ``_native_body`` adds body-level ``think``/``format`` (both response_format
  variants), each present/absent per config.
- config->wire integration for the ``/v1`` path on BOTH ``complete()``/
  ``stream()`` via the ``httpx.AsyncClient.__init__`` monkeypatch idiom.
- No cross-path leakage: native body never carries ``reasoning_effort``/
  ``response_format``/top-level ``stop``; ``/v1`` payload never carries
  ``think``/``format``/``options.stop``.
- None-path: no config + the three A4 env vars unset -> neither path emits
  any of the three params.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from the_one.llm.base import Message
from the_one.llm.ollama_provider import OllamaProvider

_A4_ENV_VARS = (
    "THE_ONE_REASONING_EFFORT",
    "THE_ONE_RESPONSE_FORMAT",
    "THE_ONE_STOP",
)


def _delenv_a4(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _A4_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# __init__ reads — mirrors test_anthropic_provider.py:test_init_reads_a4_config
# ---------------------------------------------------------------------------


class TestInitReadsA4Config:
    def test_init_reads_a4_config(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(
            model="m",
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
    )
    def test_init_a4_config_none_when_absent_or_junk(self, monkeypatch, config):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", config=config)
        assert prov._reasoning_effort_config is None
        assert prov._response_format_config is None
        assert prov._stop_config is None

    def test_init_a4_config_none_when_kwarg_absent_entirely(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m")
        assert prov._reasoning_effort_config is None
        assert prov._response_format_config is None
        assert prov._stop_config is None


# ---------------------------------------------------------------------------
# _v1_a4_kwargs — mapping to OpenAI-compat shapes (same mapping as L03's
# OpenAIProvider._a4_request_kwargs)
# ---------------------------------------------------------------------------


class TestV1A4KwargsMapping:
    def test_stop_passthrough(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", config={"stop": ["</s>", "STOP"]})
        assert prov._v1_a4_kwargs() == {"stop": ["</s>", "STOP"]}

    def test_reasoning_effort_passthrough(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", config={"reasoning_effort": "high"})
        assert prov._v1_a4_kwargs() == {"reasoning_effort": "high"}

    def test_response_format_json_object(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", config={"response_format": {"type": "json_object"}})
        assert prov._v1_a4_kwargs() == {"response_format": {"type": "json_object"}}

    def test_response_format_json_schema_synthesizes_name(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(
            model="m",
            config={"response_format": {"type": "json_schema", "schema": {"type": "object"}}},
        )
        assert prov._v1_a4_kwargs() == {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": {"type": "object"}},
            }
        }

    def test_response_format_json_schema_honors_caller_name(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(
            model="m",
            config={
                "response_format": {
                    "type": "json_schema",
                    "schema": {"type": "object"},
                    "name": "foo",
                }
            },
        )
        assert prov._v1_a4_kwargs() == {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "foo", "schema": {"type": "object"}},
            }
        }

    def test_all_three_together(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(
            model="m",
            config={
                "stop": ["</s>"],
                "reasoning_effort": "medium",
                "response_format": {"type": "json_object"},
            },
        )
        assert prov._v1_a4_kwargs() == {
            "stop": ["</s>"],
            "reasoning_effort": "medium",
            "response_format": {"type": "json_object"},
        }

    def test_empty_when_nothing_configured(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m")
        assert prov._v1_a4_kwargs() == {}


# ---------------------------------------------------------------------------
# native mapping — direct _native_options/_native_body calls (pure, no
# transport)
# ---------------------------------------------------------------------------


class TestNativeOptionsStop:
    def test_stop_present_when_configured(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", native_api=True, config={"stop": ["</s>", "STOP"]})
        options = prov._native_options(0.0, 16384)
        assert options["stop"] == ["</s>", "STOP"]

    def test_stop_absent_when_unconfigured(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", native_api=True)
        options = prov._native_options(0.0, 16384)
        assert "stop" not in options


class TestNativeBodyThinkAndFormat:
    def _body(self, prov: OllamaProvider) -> dict[str, Any]:
        return prov._native_body([Message.user("hi")], None, 0.0, 16384)

    def test_think_present_when_effort_configured(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", native_api=True, config={"reasoning_effort": "high"})
        assert self._body(prov)["think"] == "high"

    def test_think_absent_when_unconfigured(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", native_api=True)
        assert "think" not in self._body(prov)

    def test_format_json_object_variant(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(
            model="m", native_api=True, config={"response_format": {"type": "json_object"}}
        )
        assert self._body(prov)["format"] == "json"

    def test_format_json_schema_variant_bare_schema(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(
            model="m",
            native_api=True,
            config={
                "response_format": {"type": "json_schema", "schema": {"type": "object", "x": 1}}
            },
        )
        # Native "format" is the BARE schema object, not a wrapper.
        assert self._body(prov)["format"] == {"type": "object", "x": 1}

    def test_format_absent_when_unconfigured(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", native_api=True)
        assert "format" not in self._body(prov)

    def test_none_path_native_body_carries_none_of_the_three(self, monkeypatch):
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(model="m", native_api=True)
        body = self._body(prov)
        assert "think" not in body
        assert "format" not in body
        assert "stop" not in body["options"]

    def test_no_v1_key_leakage_on_native_body(self, monkeypatch):
        """Native body/options never carry the /v1 shapes."""
        _delenv_a4(monkeypatch)
        prov = OllamaProvider(
            model="m",
            native_api=True,
            config={
                "reasoning_effort": "high",
                "response_format": {"type": "json_schema", "schema": {"type": "object"}},
                "stop": ["</s>"],
            },
        )
        body = self._body(prov)
        assert "reasoning_effort" not in body
        assert "response_format" not in body
        assert "stop" not in body  # top-level; belongs under options only
        assert body["options"]["stop"] == ["</s>"]
        assert body["think"] == "high"
        assert body["format"] == {"type": "object"}


# ---------------------------------------------------------------------------
# config->wire — /v1 path via the httpx.AsyncClient.__init__ monkeypatch
# idiom (test_ollama_provider_auth.py). Not the OpenAI injectable-client
# approach (Ollama builds its client inline).
# ---------------------------------------------------------------------------

_A4_CONFIG = {
    "reasoning_effort": "high",
    "response_format": {"type": "json_schema", "schema": {"type": "object"}, "name": "foo"},
    "stop": ["</s>"],
}


def _install_mock_transport(monkeypatch, handler) -> None:
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


def _record_body(request: httpx.Request, bodies: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        body = json.loads(request.content)
    except (ValueError, TypeError):
        body = {}
    bodies.append(body)
    return body


def _v1_complete_handler(bodies: list[dict[str, Any]]):
    """Handle /api/show (context resolver + supports_tools capability probe)
    and a non-streaming /v1/chat/completions response (for ``complete()``)."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/show"):
            # No "capabilities" key -> get_model_capabilities() returns None
            # -> supports_tools() fail-opens True; harmless for these tests
            # (they assert outbound payload, not recovery behavior).
            return httpx.Response(200, json={"model_info": {}})
        if path.endswith("/chat/completions"):
            _record_body(request, bodies)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )
        raise AssertionError(f"unexpected request path: {path}")

    return handler


def _v1_stream_handler(bodies: list[dict[str, Any]]):
    """Handle /api/show + an SSE /v1/chat/completions response (for
    ``stream()``)."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/show"):
            return httpx.Response(200, json={"model_info": {}})
        if path.endswith("/chat/completions"):
            _record_body(request, bodies)
            sse = (
                "data: "
                + json.dumps({"choices": [{"index": 0, "delta": {"content": "ok"}}]})
                + "\n\n"
                + "data: "
                + json.dumps({"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
                + "\n\n"
                + "data: [DONE]\n\n"
            )
            return httpx.Response(
                200,
                content=sse,
                headers={"content-type": "text/event-stream"},
            )
        raise AssertionError(f"unexpected request path: {path}")

    return handler


class TestConfigToWireV1:
    async def test_complete_sends_a4_params(self, monkeypatch):
        _delenv_a4(monkeypatch)
        bodies: list[dict[str, Any]] = []
        _install_mock_transport(monkeypatch, _v1_complete_handler(bodies))
        prov = OllamaProvider(
            model="a4-complete-model",
            base_url="http://localhost:11434/v1",
            config=_A4_CONFIG,
        )

        await prov.complete([Message.user("hi")])

        assert len(bodies) == 1
        body = bodies[0]
        assert body["stop"] == ["</s>"]
        assert body["reasoning_effort"] == "high"
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "foo", "schema": {"type": "object"}},
        }
        # No native-shape leakage on /v1.
        assert "think" not in body
        assert "format" not in body

    async def test_stream_sends_a4_params(self, monkeypatch):
        _delenv_a4(monkeypatch)
        bodies: list[dict[str, Any]] = []
        _install_mock_transport(monkeypatch, _v1_stream_handler(bodies))
        prov = OllamaProvider(
            model="a4-stream-model",
            base_url="http://localhost:11434/v1",
            config=_A4_CONFIG,
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
        assert "think" not in body
        assert "format" not in body

    async def test_complete_none_path_omits_a4_keys(self, monkeypatch):
        _delenv_a4(monkeypatch)
        bodies: list[dict[str, Any]] = []
        _install_mock_transport(monkeypatch, _v1_complete_handler(bodies))
        prov = OllamaProvider(model="a4-none-model", base_url="http://localhost:11434/v1")

        await prov.complete([Message.user("hi")])

        assert prov._v1_a4_kwargs() == {}
        body = bodies[0]
        assert "stop" not in body
        assert "reasoning_effort" not in body
        assert "response_format" not in body
