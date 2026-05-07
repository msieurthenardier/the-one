"""Tests for LLM provider registry."""

from __future__ import annotations

from typing import Any

import pytest

from the_one.llm import registry as llm_registry
from the_one.llm.base import LLMProvider, Message


class _DummyProvider(LLMProvider):
    """Minimal LLM provider for testing registration."""

    name = "dummy"

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        return {"role": "assistant", "content": "dummy"}


@pytest.fixture(autouse=True)
def _clean_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate each test from provider state pollution."""
    monkeypatch.setattr(llm_registry, "_providers", {})


class TestRegisterProvider:
    def test_register_and_get(self) -> None:
        llm_registry.register_provider("test-prov", _DummyProvider)
        provider = llm_registry.get_provider("test-prov")
        assert isinstance(provider, _DummyProvider)

    def test_get_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            llm_registry.get_provider("nonexistent")


class TestLazyLoading:
    def test_get_ollama_lazy_loads(self) -> None:
        """get_provider('ollama') should lazy-import the ollama module."""
        provider = llm_registry.get_provider("ollama", model="test-model")
        assert provider is not None
        # After lazy load, 'ollama' should be in the providers dict
        assert "ollama" in llm_registry._providers


class TestOpenAIProviderBaseURL:
    def test_openai_provider_accepts_base_url(self) -> None:
        """OpenAIProvider must thread base_url into the AsyncOpenAI client."""
        from the_one.llm.openai_provider import OpenAIProvider

        prov = OpenAIProvider(
            model="gpt-4o",
            api_key="sk-test",
            base_url="https://example.com/v1",
        )
        # openai SDK exposes the resolved base_url on the client
        assert str(prov.client.base_url).rstrip("/") == "https://example.com/v1"

    def test_openai_provider_default_base_url(self) -> None:
        """Without base_url the SDK uses the OpenAI default."""
        from the_one.llm.openai_provider import OpenAIProvider

        prov = OpenAIProvider(model="gpt-4o", api_key="sk-test")
        # The SDK default is https://api.openai.com/v1
        assert "openai.com" in str(prov.client.base_url)
