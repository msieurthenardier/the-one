"""Unit tests for M08 F6.5 L01: per-model ``max_context_tokens`` resolution.

Covers:
- ``LLMProvider._resolve_max_context_tokens_if_needed`` idempotency / failure-
  path caching.
- ``OpenAIProvider`` prefix-table lookup including the cycle-1-flagged tricky
  models (``gpt-4-*-preview``, ``gpt-4-32k-0613``) that would otherwise
  collide with the bare ``gpt-4`` 8k entry.
- ``OllamaProvider`` resolver + the ``extract_ollama_context_length`` helper.
- ``OpenRouterProvider`` resolver wired to ``get_model_context_length``.
- ``AnthropicProvider`` class-default ``200_000`` survives the no-op default
  resolver.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from the_one.llm import ollama_api, openrouter_api
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.ollama_provider import OllamaProvider
from the_one.llm.openai_provider import OPENAI_MODEL_CONTEXT, OpenAIProvider
from the_one.llm.openrouter_provider import OpenRouterProvider

# ---------------------------------------------------------------------------
# extract_ollama_context_length — pure-function helper unit tests
# ---------------------------------------------------------------------------


class TestExtractOllamaContextLength:
    def test_qwen2_family(self) -> None:
        resp = {"model_info": {"qwen2.context_length": 32768, "qwen2.block_count": 28}}
        assert ollama_api.extract_ollama_context_length(resp) == 32768

    def test_llama_family(self) -> None:
        resp = {"model_info": {"llama.context_length": 8192}}
        assert ollama_api.extract_ollama_context_length(resp) == 8192

    def test_multi_segment_family(self) -> None:
        # Some hypothetical future model family with a dotted prefix.
        resp = {"model_info": {"foo.bar.context_length": 2048}}
        assert ollama_api.extract_ollama_context_length(resp) == 2048

    def test_no_context_length_key(self) -> None:
        resp = {"model_info": {"qwen2.attention.head_count": 32}}
        assert ollama_api.extract_ollama_context_length(resp) is None

    def test_empty_model_info(self) -> None:
        assert ollama_api.extract_ollama_context_length({"model_info": {}}) is None

    def test_missing_model_info(self) -> None:
        assert ollama_api.extract_ollama_context_length({}) is None

    def test_model_info_not_dict(self) -> None:
        assert ollama_api.extract_ollama_context_length({"model_info": "weird"}) is None

    def test_non_int_value(self) -> None:
        # Malformed shape — context_length suffix present but value isn't an int.
        resp = {"model_info": {"qwen2.context_length": "32768"}}
        assert ollama_api.extract_ollama_context_length(resp) is None


# ---------------------------------------------------------------------------
# OpenAI prefix-table lookup
# ---------------------------------------------------------------------------


class TestOpenAIPrefixLookup:
    """Prefix-match correctness — must defeat the legacy gpt-4 8k trap."""

    @pytest.mark.parametrize(
        "model, expected",
        [
            ("gpt-4o", 128_000),
            ("gpt-4o-2024-05-13", 128_000),  # prefix match for gpt-4o
            ("gpt-4-turbo", 128_000),
            ("gpt-4-turbo-preview", 128_000),  # prefix match for gpt-4-turbo (NOT gpt-4 8k)
            ("gpt-4-32k", 32_768),
            ("gpt-4-32k-0613", 32_768),  # prefix match (NOT bare gpt-4 8k)
            ("gpt-4-vision-preview", 128_000),  # explicit (NOT bare gpt-4 8k)
            ("gpt-4-1106-preview", 128_000),  # explicit (NOT bare gpt-4 8k)
            ("gpt-4-0125-preview", 128_000),  # explicit (NOT bare gpt-4 8k)
            ("gpt-4", 8_192),  # legacy default
            ("gpt-4-0613", 8_192),  # dated legacy variant
            ("gpt-3.5-turbo-instruct", 4_096),
            ("gpt-3.5-turbo-16k", 16_385),
            ("gpt-3.5-turbo", 16_385),
            ("gpt-3.5-turbo-0125", 16_385),  # newer 3.5-turbo dated variant
            ("o1", 200_000),
            ("o3-mini", 200_000),
        ],
    )
    async def test_resolves_model_context(self, model: str, expected: int) -> None:
        provider = OpenAIProvider(model=model, api_key="test-key")
        # Sanity: starts at class default before resolution.
        assert provider.max_context_tokens == 128_000
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == expected
        assert provider._max_context_tokens_resolved is True

    async def test_unknown_model_falls_back_to_class_default(self) -> None:
        provider = OpenAIProvider(model="my-finetune", api_key="test-key")
        await provider._resolve_max_context_tokens_if_needed()
        # No prefix match → class default 128k stays.
        assert provider.max_context_tokens == 128_000
        assert provider._max_context_tokens_resolved is True

    async def test_empty_model_string_falls_back(self) -> None:
        provider = OpenAIProvider(model="", api_key="test-key")
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 128_000

    async def test_idempotent_second_call_is_noop(self) -> None:
        provider = OpenAIProvider(model="gpt-4o", api_key="test-key")
        # First call resolves.
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 128_000
        # Mutate state to verify second call doesn't re-resolve.
        provider.max_context_tokens = 999
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 999  # sentinel short-circuit fired

    def test_table_contains_required_entries(self) -> None:
        # Guard against accidental deletions in future edits.
        for key in [
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-4-32k",
            "gpt-4-vision-preview",
            "gpt-4-0125-preview",
            "gpt-4-1106-preview",
            "gpt-4",
            "gpt-3.5-turbo-instruct",
            "gpt-3.5-turbo-16k",
            "gpt-3.5-turbo",
            "o1",
            "o3-mini",
        ]:
            assert key in OPENAI_MODEL_CONTEXT, f"missing required key: {key}"


# ---------------------------------------------------------------------------
# Ollama resolver
# ---------------------------------------------------------------------------


class TestOllamaResolver:
    async def test_success_path_sets_resolved_value(self) -> None:
        provider = OllamaProvider(model="qwen2.5:7b", base_url="http://test:11434")
        fake_response: dict[str, Any] = {
            "model_info": {"qwen2.context_length": 32768, "qwen2.block_count": 28},
        }
        with patch.object(
            ollama_api, "show_model", new=AsyncMock(return_value=fake_response)
        ) as mock:
            await provider._resolve_max_context_tokens_if_needed()
            assert provider.max_context_tokens == 32768
            assert provider._max_context_tokens_resolved is True
            mock.assert_awaited_once()

    async def test_failure_path_falls_back_and_caches(self) -> None:
        provider = OllamaProvider(model="qwen2.5:7b", base_url="http://test:11434")
        with patch.object(
            ollama_api,
            "show_model",
            new=AsyncMock(side_effect=httpx.HTTPError("boom")),
        ) as mock:
            await provider._resolve_max_context_tokens_if_needed()
            # Falls back to class default 128k.
            assert provider.max_context_tokens == 128_000
            assert provider._max_context_tokens_resolved is True
            # Second call must NOT retry the failing fetch.
            await provider._resolve_max_context_tokens_if_needed()
            assert mock.await_count == 1

    async def test_missing_context_length_leaves_default(self) -> None:
        provider = OllamaProvider(model="qwen2.5:7b", base_url="http://test:11434")
        fake_response: dict[str, Any] = {"model_info": {"qwen2.block_count": 28}}
        with patch.object(ollama_api, "show_model", new=AsyncMock(return_value=fake_response)):
            await provider._resolve_max_context_tokens_if_needed()
            assert provider.max_context_tokens == 128_000
            assert provider._max_context_tokens_resolved is True

    async def test_zero_or_negative_value_ignored(self) -> None:
        # Defensive: an int but non-positive shouldn't replace the default.
        provider = OllamaProvider(model="qwen2.5:7b", base_url="http://test:11434")
        fake_response: dict[str, Any] = {"model_info": {"qwen2.context_length": 0}}
        with patch.object(ollama_api, "show_model", new=AsyncMock(return_value=fake_response)):
            await provider._resolve_max_context_tokens_if_needed()
            assert provider.max_context_tokens == 128_000

    async def test_model_not_found_falls_back(self) -> None:
        provider = OllamaProvider(model="missing-model", base_url="http://test:11434")
        with patch.object(
            ollama_api,
            "show_model",
            new=AsyncMock(side_effect=ValueError("Model 'missing-model' not found")),
        ):
            await provider._resolve_max_context_tokens_if_needed()
            assert provider.max_context_tokens == 128_000
            assert provider._max_context_tokens_resolved is True


# ---------------------------------------------------------------------------
# OpenRouter resolver + helper
# ---------------------------------------------------------------------------


class _StubModelEntry:
    """Stand-in for ``OpenRouterModelEntry`` — only the fields used by the
    resolver need to be present. Avoids reaching into the pydantic model."""

    def __init__(self, model_id: str, context_length: int | None) -> None:
        self.id = model_id
        self.context_length = context_length


class TestOpenRouterResolver:
    async def test_success_path_sets_resolved_value(self) -> None:
        provider = OpenRouterProvider(model="anthropic/claude-3.5-sonnet", api_key="test-key")
        fake_models = [
            _StubModelEntry("openai/gpt-4o", 128_000),
            _StubModelEntry("anthropic/claude-3.5-sonnet", 200_000),
        ]
        with patch.object(
            openrouter_api,
            "list_models",
            new=AsyncMock(return_value=fake_models),
        ) as mock:
            await provider._resolve_max_context_tokens_if_needed()
            assert provider.max_context_tokens == 200_000
            assert provider._max_context_tokens_resolved is True
            mock.assert_awaited_once()

    async def test_failure_path_falls_back_and_caches(self) -> None:
        provider = OpenRouterProvider(model="anthropic/claude-3.5-sonnet", api_key="test-key")
        with patch.object(
            openrouter_api,
            "list_models",
            new=AsyncMock(side_effect=httpx.HTTPError("network down")),
        ) as mock:
            await provider._resolve_max_context_tokens_if_needed()
            # Falls back to class default 128k (OpenAIProvider inherits from
            # LLMProvider; no class-level override).
            assert provider.max_context_tokens == 128_000
            assert provider._max_context_tokens_resolved is True
            # Second call short-circuits (sentinel set in the resolver wrapper).
            await provider._resolve_max_context_tokens_if_needed()
            # ``list_models`` is wrapped by ``get_model_context_length`` which
            # ALWAYS calls it on the first resolver invocation, but the second
            # invocation must NOT touch the helper.
            assert mock.await_count == 1

    async def test_model_not_in_listing_falls_back(self) -> None:
        provider = OpenRouterProvider(model="not-in-listing", api_key="test-key")
        fake_models = [_StubModelEntry("openai/gpt-4o", 128_000)]
        with patch.object(
            openrouter_api,
            "list_models",
            new=AsyncMock(return_value=fake_models),
        ):
            await provider._resolve_max_context_tokens_if_needed()
            assert provider.max_context_tokens == 128_000

    async def test_null_context_length_falls_back(self) -> None:
        provider = OpenRouterProvider(model="weird/model", api_key="test-key")
        fake_models = [_StubModelEntry("weird/model", None)]
        with patch.object(
            openrouter_api,
            "list_models",
            new=AsyncMock(return_value=fake_models),
        ):
            await provider._resolve_max_context_tokens_if_needed()
            assert provider.max_context_tokens == 128_000

    async def test_get_model_context_length_returns_value(self) -> None:
        fake_models = [_StubModelEntry("foo/bar", 65_536)]
        with patch.object(
            openrouter_api,
            "list_models",
            new=AsyncMock(return_value=fake_models),
        ):
            result = await openrouter_api.get_model_context_length(
                "https://openrouter.ai/api/v1", None, "foo/bar"
            )
            assert result == 65_536

    async def test_get_model_context_length_fail_open(self) -> None:
        with patch.object(
            openrouter_api,
            "list_models",
            new=AsyncMock(side_effect=ValueError("bad shape")),
        ):
            result = await openrouter_api.get_model_context_length(
                "https://openrouter.ai/api/v1", None, "any/model"
            )
            assert result is None


# ---------------------------------------------------------------------------
# Anthropic — class default preserved
# ---------------------------------------------------------------------------


class TestAnthropicDefault:
    async def test_class_default_preserved_after_resolver(self) -> None:
        # AnthropicProvider does NOT override _resolve_max_context_tokens —
        # the class-level 200k is the resolved value.
        provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="test-key")
        assert provider.max_context_tokens == 200_000
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 200_000
        assert provider._max_context_tokens_resolved is True

    async def test_resolver_is_idempotent(self) -> None:
        provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="test-key")
        await provider._resolve_max_context_tokens_if_needed()
        # Mutate to a sentinel value and verify second call doesn't reset it
        # (proves the wrapper short-circuits past the no-op default).
        provider.max_context_tokens = 12345
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 12345
