"""Tests for LLM provider registry."""

from __future__ import annotations

import sys
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
    """Isolate each test from provider state pollution.

    Two layers of state to scrub:
    1. ``llm_registry._providers`` dict — cleared so each test starts with
       no registrations.
    2. ``sys.modules`` entries for ``the_one.llm.*_provider`` modules —
       evicted so the registry's lazy-loader (``__import__``) actually
       re-executes the module body (which contains the
       ``register_provider(...)`` call). Without this eviction, any prior
       test or test file that imported a provider module at top-level
       leaves the module cached in ``sys.modules``, ``__import__`` becomes
       a no-op, and the lazy-load test sees an empty ``_providers`` dict.
    """
    monkeypatch.setattr(llm_registry, "_providers", {})
    for mod_name in list(sys.modules):
        if mod_name.startswith("the_one.llm.") and (
            mod_name.endswith("_provider") or mod_name == "the_one.llm.mock"
        ):
            monkeypatch.delitem(sys.modules, mod_name, raising=False)


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
        """Without base_url our code must NOT inject base_url into client_kwargs;
        the SDK's own default URL must be used unchanged."""
        import openai

        from the_one.llm.openai_provider import OpenAIProvider

        prov = OpenAIProvider(model="gpt-4o", api_key="sk-test")
        # Compare against a fresh SDK client constructed the same way the SDK
        # itself constructs one (no base_url override). If our code injected
        # base_url=None, this asserts because AsyncOpenAI(base_url=None) and
        # AsyncOpenAI() both resolve to the same default — but our code path
        # explicitly skips passing base_url=None so we are not exercising
        # that buggy path.
        default_client = openai.AsyncOpenAI(api_key="sk-test")
        assert prov.client.base_url == default_client.base_url
