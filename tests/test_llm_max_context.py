"""Unit tests for M08 F6.5 L01 / M16 F05: per-model ``max_context_tokens`` resolution.

Covers:
- ``LLMProvider._resolve_max_context_tokens_if_needed`` idempotency / failure-
  path caching.
- ``OpenAIProvider`` prefix-table lookup including the cycle-1-flagged tricky
  models (``gpt-4-*-preview``, ``gpt-4-32k-0613``) that would otherwise
  collide with the bare ``gpt-4`` 8k entry.
- ``OllamaProvider`` resolver + the ``extract_ollama_context_length`` helper.
- ``OpenRouterProvider`` resolver wired to ``get_model_context_length``.
- ``AnthropicProvider`` catalog-sourced resolver: reports the real per-model
  context window (e.g. 1M for current Claude models); ``200_000`` is the
  conservative class-default fallback on a catalog miss (M16 F05, DD4).
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from the_one.llm import ollama_api, openrouter_api
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.model_catalog import _OPENAI_FLOOR, _reset_for_tests, context_window_for
from the_one.llm.ollama_provider import OllamaProvider
from the_one.llm.openai_provider import OpenAIProvider
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

    @pytest.fixture(autouse=True)
    def _reset_catalog_memo(self) -> None:
        """Reset the model_catalog memo before and after each test in this class.

        Prevents a prior test's injected catalog from leaking into subsequent
        tests. Both setup and teardown reset to None so the seed is reloaded
        fresh on the next lookup.
        """
        _reset_for_tests(None)
        yield
        _reset_for_tests(None)

    # ``gpt-4-turbo-preview`` → 128000 exercises the longest-prefix sort-order:
    # the catalog must sort keys descending by length so ``gpt-4-turbo`` (12 chars)
    # beats ``gpt-4`` (5 chars) when both are prefixes of the query string.
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

    async def test_resolver_reads_catalog_not_table(self) -> None:
        # Inject a catalog that gives gpt-4o a distinct window (222_222). The
        # injected value proves catalog-sourcing: if the resolver fell back to
        # any hardcoded value it would not return 222_222.
        _reset_for_tests({"providers": {"openai": {"gpt-4o": 222_222}}})
        provider = OpenAIProvider(model="gpt-4o", api_key="x")
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 222_222

    async def test_miss_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        # Inject a catalog that has no entry for the queried model. The resolver
        # must log a WARNING and leave the class default (128k) unchanged.
        _reset_for_tests({"providers": {"openai": {}}})
        provider = OpenAIProvider(model="unknown-model-xyz", api_key="x")
        with caplog.at_level(logging.WARNING, logger="the_one.llm.openai_provider"):
            await provider._resolve_max_context_tokens_if_needed()
        assert any(
            "no catalog context window" in record.message and record.levelno == logging.WARNING
            for record in caplog.records
        ), f"Expected a WARNING about missing catalog entry; got: {caplog.records}"
        assert provider.max_context_tokens == 128_000

    def test_floor_covers_required_models(self) -> None:
        # Guard: every _OPENAI_FLOOR key must resolve via the catalog to a
        # positive int — ensures the catalog seed covers the historical floor.
        for key in _OPENAI_FLOOR:
            result = context_window_for("openai", key)
            assert isinstance(result, int) and result > 0, (
                f"catalog did not resolve openai/{key} to a positive int; got {result!r}"
            )


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

    async def test_huge_advertised_window_clamped_to_runtime_default(self) -> None:
        # The reported bug: a model advertises a 262144 window but Ollama runs it
        # at num_ctx=4096. max_context_tokens must be the EFFECTIVE runtime window
        # we load (32768 default), not the advertised architectural maximum — so
        # the governor and the context gauge size against reality.
        provider = OllamaProvider(model="ministral-3:8b", base_url="http://test:11434")
        fake_response: dict[str, Any] = {"model_info": {"mistral3.context_length": 262_144}}
        with patch.object(ollama_api, "show_model", new=AsyncMock(return_value=fake_response)):
            await provider._resolve_max_context_tokens_if_needed()
            assert provider.max_context_tokens == 32_768


class TestEffectiveNumCtx:
    """``effective_num_ctx`` — runtime num_ctx clamp (pure helper)."""

    def test_clamps_huge_advertised_to_default(self) -> None:
        from the_one.llm.ollama_provider import effective_num_ctx

        assert effective_num_ctx(262_144) == 32_768

    def test_small_advertised_passes_through(self) -> None:
        from the_one.llm.ollama_provider import effective_num_ctx

        # A model whose architecture is smaller than the default is never
        # inflated past what it supports.
        assert effective_num_ctx(8_192) == 8_192

    def test_unknown_advertised_returns_none(self) -> None:
        from the_one.llm.ollama_provider import effective_num_ctx

        assert effective_num_ctx(None) is None
        assert effective_num_ctx(0) is None
        assert effective_num_ctx(-5) is None

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from the_one.llm.ollama_provider import effective_num_ctx

        monkeypatch.setenv("THE_ONE_OLLAMA_NUM_CTX", "16384")
        assert effective_num_ctx(262_144) == 16_384
        # Still clamped to the model's advertised window when that is smaller.
        assert effective_num_ctx(8_192) == 8_192

    def test_env_override_invalid_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from the_one.llm.ollama_provider import effective_num_ctx

        monkeypatch.setenv("THE_ONE_OLLAMA_NUM_CTX", "not-a-number")
        assert effective_num_ctx(262_144) == 32_768
        monkeypatch.setenv("THE_ONE_OLLAMA_NUM_CTX", "-1")
        assert effective_num_ctx(262_144) == 32_768


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
# Anthropic — catalog-sourced resolver (M16 F05)
# ---------------------------------------------------------------------------


class TestAnthropicDefault:
    @pytest.fixture(autouse=True)
    def _reset_catalog_memo(self) -> None:
        """Reset the model_catalog memo before and after each test in this class.

        Prevents a prior test's injected catalog from leaking into subsequent
        tests. Both setup and teardown reset to None so the seed is reloaded
        fresh on the next lookup.
        """
        _reset_for_tests(None)
        yield
        _reset_for_tests(None)

    async def test_resolves_native_1m_from_catalog(self) -> None:
        # Pre-resolution: class default 200k is the starting value.
        provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="test-key")
        assert provider.max_context_tokens == 200_000
        # After resolution: catalog reports 1M for claude-sonnet-4-6 (M16 F05 seed).
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 1_000_000
        assert provider._max_context_tokens_resolved is True

    async def test_resolver_is_idempotent(self) -> None:
        provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="test-key")
        # First resolve sets 1M (from catalog seed for claude-sonnet-4-6).
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 1_000_000
        # Mutate to a sentinel value and verify second call doesn't re-resolve
        # (proves the wrapper short-circuits after the first resolution).
        provider.max_context_tokens = 12345
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 12345  # sentinel short-circuit fired

    async def test_resolver_reads_catalog(self) -> None:
        # Inject a catalog with a custom model to prove the resolver sources
        # from the catalog, not a hardcoded table.
        _reset_for_tests({"providers": {"anthropic": {"claude-x": 333_333}}})
        provider = AnthropicProvider(model="claude-x", api_key="x")
        await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 333_333

    async def test_miss_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        # Inject a catalog with no entry for the queried model. The resolver
        # must log a WARNING and leave the 200k class default unchanged.
        _reset_for_tests({"providers": {"anthropic": {}}})
        provider = AnthropicProvider(model="unknown-claude", api_key="x")
        with caplog.at_level(logging.WARNING, logger="the_one.llm.anthropic_provider"):
            await provider._resolve_max_context_tokens_if_needed()
        assert any(
            "no catalog context window" in record.message and record.levelno == logging.WARNING
            for record in caplog.records
        ), f"Expected a WARNING about missing catalog entry; got: {caplog.records}"
        assert provider.max_context_tokens == 200_000
