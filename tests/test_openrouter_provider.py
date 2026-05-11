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
        """Behavior contract: when neither the explicit arg nor
        OPENROUTER_API_KEY is set, the SDK client's api_key MUST be
        non-empty (so the SDK skips its OPENAI_API_KEY env fallback) AND
        MUST NOT equal the leaked OPENAI_API_KEY value.

        See ``test_no_leak_uses_documented_placeholder`` for the
        sentinel-equality contract.
        """
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        prov = OpenRouterProvider(model="m", api_key=None)
        # Behavior assertion (no-leak): non-empty AND not the OpenAI env value.
        assert prov.client.api_key, "api_key must be non-empty so the SDK skips env fallback"
        assert prov.client.api_key != "sk-leaked", "OpenAI env value leaked into OpenRouter client"

    def test_no_leak_uses_documented_placeholder(self, monkeypatch):
        """Sentinel-equality contract: pin the public placeholder string so
        operators reading server logs see a consistent identifier."""
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        prov = OpenRouterProvider(model="m", api_key=None)
        assert prov.client.api_key == OpenRouterProvider._NO_KEY_PLACEHOLDER

    def test_no_leak_with_empty_string_api_key(self, monkeypatch):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        prov = OpenRouterProvider(model="m", api_key="")
        # Empty string is treated identically to "no key set" — same placeholder.
        assert prov.client.api_key == OpenRouterProvider._NO_KEY_PLACEHOLDER

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


class TestTimeout:
    """The openai SDK's default 600s timeout means a stuck upstream model
    holds the WebSocket open for 10 minutes with no user feedback. The
    provider applies a sensible default and accepts an override."""

    def test_default_timeout_applied(self):
        from the_one.llm.openai_provider import DEFAULT_OPENAI_TIMEOUT
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x")
        # The openai SDK exposes the configured timeout on the client.
        # Read tolerates either dict or httpx.Timeout shape.
        assert prov.client.timeout.read == DEFAULT_OPENAI_TIMEOUT.read

    def test_explicit_timeout_overrides_default(self):
        import httpx

        from the_one.llm.openrouter_provider import OpenRouterProvider

        custom = httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0)
        prov = OpenRouterProvider(model="m", api_key="x", timeout=custom)
        assert prov.client.timeout.read == 5.0


class TestRankingHeaders:
    """Ranking headers identify *the app* (the-one), not the operator, so
    they're hardcoded constants in openrouter_provider.py — always sent,
    never operator-configurable. The ``config`` kwarg is accepted for
    factory uniformity but ignored."""

    def test_referer_header_hardcoded_to_app_url(self):
        from the_one.llm.openrouter_provider import _APP_URL, OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x")
        assert prov.client.default_headers.get("HTTP-Referer") == _APP_URL

    def test_title_header_hardcoded_to_app_name(self):
        from the_one.llm.openrouter_provider import _APP_NAME, OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x")
        assert prov.client.default_headers.get("X-Title") == _APP_NAME

    def test_config_kwarg_is_ignored(self):
        """Pre-rebrand: operators used to supply config.referer/config.title.
        Those keys are now ignored — verifies hardcoded values still win."""
        from the_one.llm.openrouter_provider import _APP_NAME, _APP_URL, OpenRouterProvider

        prov = OpenRouterProvider(
            model="m",
            api_key="x",
            config={"referer": "https://attacker.example", "title": "Pwned"},
        )
        assert prov.client.default_headers.get("HTTP-Referer") == _APP_URL
        assert prov.client.default_headers.get("X-Title") == _APP_NAME


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
class TestSupportsTools:
    """Capability gate: OpenRouterProvider.supports_tools must consult
    the OpenRouter ``/models`` listing so tool-less models are run as
    plain chat instead of failing at the wire."""

    async def test_returns_false_when_model_lacks_tools(self, monkeypatch):
        from the_one.llm import openrouter_api
        from the_one.llm.openrouter_provider import OpenRouterProvider

        openrouter_api._models_cache.clear()

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "google/gemma-2", "supported_parameters": ["temperature"]}
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        prov = OpenRouterProvider(model="google/gemma-2", api_key="k")
        assert await prov.supports_tools() is False

    async def test_returns_true_when_model_lists_tools(self, monkeypatch):
        from the_one.llm import openrouter_api
        from the_one.llm.openrouter_provider import OpenRouterProvider

        openrouter_api._models_cache.clear()

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "anthropic/claude-3.5", "supported_parameters": ["tools"]}
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        prov = OpenRouterProvider(model="anthropic/claude-3.5", api_key="k")
        assert await prov.supports_tools() is True

    async def test_returns_true_when_capabilities_unknown(self, monkeypatch):
        """Fail-open: network error / 5xx / model-missing all → True so the
        request still goes out and surfaces the real error."""
        from the_one.llm import openrouter_api
        from the_one.llm.openrouter_provider import OpenRouterProvider

        openrouter_api._models_cache.clear()

        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        transport = httpx.MockTransport(handler)
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = transport
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        prov = OpenRouterProvider(model="x/y", api_key="k")
        assert await prov.supports_tools() is True

    async def test_no_placeholder_leak_to_capability_lookup(self, monkeypatch):
        """When api_key is unset, the provider must call
        ``get_model_capabilities`` with ``None`` (NOT the bearer
        placeholder) — /models is publicly accessible and a placeholder
        in the auth header would just waste a cache slot."""
        from the_one.llm import openrouter_api
        from the_one.llm.openrouter_provider import OpenRouterProvider

        openrouter_api._models_cache.clear()
        captured_keys: list[str | None] = []

        async def fake_get_caps(base_url, api_key, model):
            captured_keys.append(api_key)
            return None

        monkeypatch.setattr(openrouter_api, "get_model_capabilities", fake_get_caps)
        prov = OpenRouterProvider(model="x/y", api_key=None)
        await prov.supports_tools()
        assert captured_keys == [None]


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
