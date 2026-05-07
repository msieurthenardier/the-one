"""Tests for OpenRouterProvider."""

from __future__ import annotations

import httpx
import pytest

from the_one.llm.base import Message, Role


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Each test starts with no OPENAI_API_KEY / OPENROUTER_API_KEY in env."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


class TestNoLeakInvariant:
    def test_no_leak_with_api_key_none(self, monkeypatch):
        from the_one.llm.openrouter_provider import _NO_KEY_PLACEHOLDER, OpenRouterProvider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        prov = OpenRouterProvider(model="m", api_key=None)
        # No-leak invariant: when no openrouter key is set, we MUST pass a
        # non-empty placeholder (NOT the OpenAI env value) so the SDK skips
        # its env fallback.
        assert prov.client.api_key == _NO_KEY_PLACEHOLDER

    def test_no_leak_with_empty_string_api_key(self, monkeypatch):
        from the_one.llm.openrouter_provider import _NO_KEY_PLACEHOLDER, OpenRouterProvider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        prov = OpenRouterProvider(model="m", api_key="")
        # Empty string is treated identically to "no key set" — same placeholder.
        assert prov.client.api_key == _NO_KEY_PLACEHOLDER

    def test_uses_openrouter_env_when_arg_none(self, monkeypatch):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        prov = OpenRouterProvider(model="m", api_key=None)
        assert prov.client.api_key == "sk-or-env"

    def test_explicit_arg_wins_over_env(self, monkeypatch):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
        prov = OpenRouterProvider(model="m", api_key="sk-explicit")
        assert prov.client.api_key == "sk-explicit"


class TestBaseUrl:
    def test_default_base_url(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x")
        assert "openrouter.ai/api/v1" in str(prov.client.base_url)

    def test_custom_base_url_honored(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x", base_url="https://example.com/api/v1")
        assert "example.com/api/v1" in str(prov.client.base_url)


class TestRankingHeaders:
    def test_referer_header_set_when_config_referer(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(
            model="m", api_key="x", config={"referer": "https://myapp.example"}
        )
        assert prov.client.default_headers.get("HTTP-Referer") == "https://myapp.example"

    def test_title_header_set_when_config_title(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x", config={"title": "MyApp"})
        assert prov.client.default_headers.get("X-Title") == "MyApp"

    def test_no_ranking_headers_when_config_empty(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x", config={})
        assert "HTTP-Referer" not in prov.client.default_headers
        assert "X-Title" not in prov.client.default_headers

    def test_no_ranking_headers_when_config_keys_empty_string(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x", config={"referer": "", "title": ""})
        assert "HTTP-Referer" not in prov.client.default_headers
        assert "X-Title" not in prov.client.default_headers


class TestInstanceAttributeParity:
    def test_subclass_has_all_parent_instance_attrs(self):
        """If OpenAIProvider.__init__ ever adds a new self.X, this test fails
        and forces the OpenRouterProvider author to mirror or refactor."""
        from the_one.llm.openai_provider import OpenAIProvider
        from the_one.llm.openrouter_provider import OpenRouterProvider

        parent = OpenAIProvider(model="m", api_key="x")
        sub = OpenRouterProvider(model="m", api_key="x")
        parent_attrs = set(vars(parent).keys())
        sub_attrs = set(vars(sub).keys())
        missing = parent_attrs - sub_attrs
        assert missing == set(), (
            f"OpenRouterProvider missing parent attrs {missing}. "
            "Mirror in __init__ or refactor toward env_var_name pattern."
        )


@pytest.mark.asyncio
class TestStreaming:
    async def test_stream_without_trailing_usage_chunk(self):
        """If upstream omits the trailing usage chunk, stream must not crash
        and final StreamChunk must report usage=None."""
        import openai

        from the_one.llm.openrouter_provider import OpenRouterProvider

        # Synthesize an SSE stream that ends with a content delta but NO
        # trailing usage chunk and NO empty-choices metadata chunk.
        sse_body = 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=sse_body,
                headers={"content-type": "text/event-stream"},
            )

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        # Construct provider, then swap the SDK's underlying http client
        prov = OpenRouterProvider(model="m", api_key="x")
        prov.client = openai.AsyncOpenAI(
            api_key="x", base_url=str(prov.client.base_url), http_client=client
        )

        chunks = []
        async for chunk in prov.stream([Message(role=Role.USER, content="hi")]):
            chunks.append(chunk)
        assert chunks, "stream returned no chunks"
        assert chunks[-1].is_final is True
        assert chunks[-1].usage is None
