"""Sortie 11 AC1: ``context_window_known`` is True only where a resolver read real metadata."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx

from the_one.llm import ollama_api, openrouter_api
from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import LLMProvider
from the_one.llm.mock import MockProvider
from the_one.llm.ollama_provider import OllamaProvider
from the_one.llm.openai_provider import OpenAIProvider
from the_one.llm.openrouter_provider import OpenRouterProvider


def test_the_base_default_is_not_known() -> None:
    assert LLMProvider.context_window_known is False
    assert MockProvider().context_window_known is False


class TestOllama:
    async def test_native_with_a_resolved_window_is_known(self) -> None:
        provider = OllamaProvider(model="m", base_url="http://test:11434", native_api=True)
        assert provider.context_window_known is False  # before any lookup
        shown: dict[str, Any] = {"model_info": {"qwen2.context_length": 32768}}
        with patch.object(ollama_api, "show_model", new=AsyncMock(return_value=shown)):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.context_window_known is True

    async def test_openai_compatible_stays_unknown_even_with_a_show_answer(self) -> None:
        provider = OllamaProvider(model="m", base_url="http://test:11434", native_api=False)
        shown: dict[str, Any] = {"model_info": {"qwen2.context_length": 32768}}
        with patch.object(ollama_api, "show_model", new=AsyncMock(return_value=shown)):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 32768
        assert provider.context_window_known is False

    async def test_native_without_a_window_in_the_answer_is_unknown(self) -> None:
        provider = OllamaProvider(model="m", base_url="http://test:11434", native_api=True)
        shown: dict[str, Any] = {"model_info": {"qwen2.block_count": 28}}
        with patch.object(ollama_api, "show_model", new=AsyncMock(return_value=shown)):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.context_window_known is False

    async def test_a_failed_lookup_is_unknown(self) -> None:
        provider = OllamaProvider(model="m", base_url="http://test:11434", native_api=True)
        boom = AsyncMock(side_effect=httpx.HTTPError("boom"))
        with patch.object(ollama_api, "show_model", new=boom):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.context_window_known is False


class TestCatalogProviders:
    async def test_anthropic_catalog_hit_is_known(self) -> None:
        provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="k")
        with patch("the_one.llm.anthropic_provider.context_window_for", return_value=1_000_000):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 1_000_000
        assert provider.context_window_known is True

    async def test_anthropic_catalog_miss_is_unknown(self) -> None:
        provider = AnthropicProvider(model="claude-unlisted", api_key="k")
        with patch("the_one.llm.anthropic_provider.context_window_for", return_value=None):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 200_000
        assert provider.context_window_known is False

    async def test_the_plan_provider_inherits_the_rule(self) -> None:
        assert issubclass(AnthropicPlanProvider, AnthropicProvider)
        assert (
            AnthropicPlanProvider._resolve_max_context_tokens
            is AnthropicProvider._resolve_max_context_tokens
        )

    async def test_openai_catalog_hit_is_known(self) -> None:
        provider = OpenAIProvider(model="gpt-4o", api_key="k")
        with patch("the_one.llm.openai_provider.context_window_for", return_value=128_000):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.context_window_known is True

    async def test_openai_catalog_miss_is_unknown(self) -> None:
        provider = OpenAIProvider(model="not-listed", api_key="k")
        with patch("the_one.llm.openai_provider.context_window_for", return_value=None):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.context_window_known is False


class _Entry:
    def __init__(self, model_id: str, context_length: int | None) -> None:
        self.id = model_id
        self.context_length = context_length


class TestOpenRouter:
    async def test_a_positive_context_length_is_known(self) -> None:
        provider = OpenRouterProvider(model="a/b", api_key="k")
        listed = AsyncMock(return_value=[_Entry("a/b", 64_000)])
        with patch.object(openrouter_api, "list_models", new=listed):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.max_context_tokens == 64_000
        assert provider.context_window_known is True

    async def test_a_missing_model_is_unknown(self) -> None:
        provider = OpenRouterProvider(model="a/missing", api_key="k")
        listed = AsyncMock(return_value=[_Entry("a/b", 64_000)])
        with patch.object(openrouter_api, "list_models", new=listed):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.context_window_known is False

    async def test_a_non_positive_length_is_unknown(self) -> None:
        provider = OpenRouterProvider(model="a/b", api_key="k")
        listed = AsyncMock(return_value=[_Entry("a/b", 0)])
        with patch.object(openrouter_api, "list_models", new=listed):
            await provider._resolve_max_context_tokens_if_needed()
        assert provider.context_window_known is False
