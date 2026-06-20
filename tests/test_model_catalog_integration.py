"""Integration tests for M16 F05 L06 — offline-restart survival and composition.

These tests prove the flight's headline guarantees end-to-end:

1. **Offline-restart survival**: with no cache and no network, a freshly-
   constructed provider resolves the catalog's window (1M for claude-sonnet-4-6,
   128k for gpt-4o) — from the bundled seed, not the class default (200k).

2. **No-network on the resolve path**: OpenAI/Anthropic resolve makes no HTTP
   call — monkeypatching `httpx.AsyncClient.send` (and `httpx.Client.send`) to
   raise confirms the resolve still succeeds from the seed.

3. **Shipped-model coverage**: parametrized conformance test asserts
   `context_window_for` returns the expected non-None window for the app's
   default and representative models.

4. **Catalog-driven through the endpoint (composition)**: the
   `/api/agents/{name}/context-window` endpoint returns the catalog-driven value
   when backed by a real AnthropicProvider whose resolver runs against the
   catalog — exercising the true restart code path
   (endpoint → resolver → catalog → seed).

5. **Hermeticity**: autouse fixture resets the catalog memo before and after
   every test so suite-order cannot contaminate results.
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.config import settings
from the_one.llm import model_catalog as _model_catalog_mod
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.model_catalog import _reset_for_tests, context_window_for
from the_one.llm.openai_provider import OpenAIProvider
from the_one.interfaces.web.api import router


# ---------------------------------------------------------------------------
# Hermeticity — autouse reset so suite order cannot contaminate
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_catalog_memo():
    """Force a fresh catalog load (from seed) before and after every test."""
    _reset_for_tests(None)
    yield
    _reset_for_tests(None)


# ---------------------------------------------------------------------------
# ASGI test client — mirrors test_api_context_window.py
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Bare ASGI test client around the api router — no DB needed because
    the endpoint's only DB-touching call is ``AgentFactory.create()``,
    which we patch wholesale per test.
    """
    test_app = FastAPI()
    test_app.include_router(router)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Offline-restart survival
# ---------------------------------------------------------------------------


class TestOfflineRestartSurvival:
    """With no cache (empty tmp_path data_dir) and no network, a freshly-
    constructed provider still resolves the catalog's window from the bundled
    seed — NOT from the class default.
    """

    async def test_anthropic_resolves_from_seed_no_cache(
        self, monkeypatch, tmp_path
    ) -> None:
        """AnthropicProvider(claude-sonnet-4-6) → 1_000_000 from bundled seed.

        The class default is 200_000. Getting 1_000_000 proves the seed drove
        the resolution, not the class default.
        """
        # Point data_dir at an empty dir — no cache file present.
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        # Force a fresh seed load on the next lookup.
        _reset_for_tests(None)

        provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="x")
        await provider._resolve_max_context_tokens_if_needed()

        assert provider.max_context_tokens == 1_000_000, (
            f"Expected 1_000_000 (seed value), got {provider.max_context_tokens}. "
            "The resolve must have used the class default (200_000) rather than the "
            "bundled seed — check that the seed carries claude-sonnet-4-6 and that "
            "data_dir was correctly pointed at an empty tmp_path."
        )

    async def test_openai_resolves_from_seed_no_cache(
        self, monkeypatch, tmp_path
    ) -> None:
        """OpenAIProvider(gpt-4o) → 128_000 from bundled seed."""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        _reset_for_tests(None)

        provider = OpenAIProvider(model="gpt-4o", api_key="x")
        await provider._resolve_max_context_tokens_if_needed()

        assert provider.max_context_tokens == 128_000, (
            f"Expected 128_000 (seed value), got {provider.max_context_tokens}."
        )


# ---------------------------------------------------------------------------
# 2. No-network on the resolve path
# ---------------------------------------------------------------------------


class TestNoNetworkOnResolvePath:
    """Patching httpx.AsyncClient.send (and httpx.Client.send) to raise confirms
    the OpenAI/Anthropic resolve path makes no HTTP call.

    Note: we patch `.send` (not `.__init__`) because AnthropicProvider.__init__
    constructs an anthropic.AsyncAnthropic → httpx.AsyncClient at instantiation.
    Patching __init__ to raise would break construction before the test reaches
    resolve. Patching .send leaves construction intact and only fails if a real
    HTTP request is attempted.
    """

    async def test_anthropic_resolve_makes_no_http_call(
        self, monkeypatch, tmp_path
    ) -> None:
        """AnthropicProvider resolve does not issue any HTTP request."""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        _reset_for_tests(None)

        send_called = []

        def _raise_on_send(*args, **kwargs):
            send_called.append(("sync", args, kwargs))
            raise AssertionError("httpx.Client.send was called — resolve path hit the network")

        async def _araise_on_send(*args, **kwargs):
            send_called.append(("async", args, kwargs))
            raise AssertionError("httpx.AsyncClient.send was called — resolve path hit the network")

        with (
            patch("httpx.AsyncClient.send", new=_araise_on_send),
            patch("httpx.Client.send", new=_raise_on_send),
        ):
            provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="x")
            await provider._resolve_max_context_tokens_if_needed()

        assert not send_called, f"Unexpected HTTP calls: {send_called}"
        assert provider.max_context_tokens == 1_000_000, (
            f"Expected 1_000_000 from seed, got {provider.max_context_tokens}"
        )

    async def test_openai_resolve_makes_no_http_call(
        self, monkeypatch, tmp_path
    ) -> None:
        """OpenAIProvider resolve does not issue any HTTP request."""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        _reset_for_tests(None)

        send_called = []

        def _raise_on_send(*args, **kwargs):
            send_called.append(("sync", args, kwargs))
            raise AssertionError("httpx.Client.send called")

        async def _araise_on_send(*args, **kwargs):
            send_called.append(("async", args, kwargs))
            raise AssertionError("httpx.AsyncClient.send called")

        with (
            patch("httpx.AsyncClient.send", new=_araise_on_send),
            patch("httpx.Client.send", new=_raise_on_send),
        ):
            provider = OpenAIProvider(model="gpt-4o", api_key="x")
            await provider._resolve_max_context_tokens_if_needed()

        assert not send_called, f"Unexpected HTTP calls: {send_called}"
        assert provider.max_context_tokens == 128_000


# ---------------------------------------------------------------------------
# 3. Shipped-model coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider_name, model_id, expected_window",
    [
        # OpenAI defaults and representative families
        ("openai", "gpt-4o", 128_000),
        ("openai", "o1", 200_000),
        # Anthropic defaults and representative families
        ("anthropic", "claude-sonnet-4-6", 1_000_000),
        ("anthropic", "claude-3-5-haiku-latest", 200_000),
    ],
)
def test_shipped_model_coverage(
    provider_name: str, model_id: str, expected_window: int
) -> None:
    """catalog resolves the expected window for models the app ships/defaults to.

    Drives the assertion through context_window_for so the full lookup chain
    (seed → exact-or-prefix match) is exercised, not just a dict lookup.
    """
    result = context_window_for(provider_name, model_id)
    assert result is not None, (
        f"context_window_for({provider_name!r}, {model_id!r}) returned None — "
        "model is missing from the seed."
    )
    assert result == expected_window, (
        f"context_window_for({provider_name!r}, {model_id!r}) = {result}, "
        f"expected {expected_window}"
    )


# ---------------------------------------------------------------------------
# 4. Catalog-driven through the endpoint (composition)
# ---------------------------------------------------------------------------


class TestEndpointComposition:
    """The /api/agents/{name}/context-window endpoint returns the catalog-driven
    value when backed by a real provider whose resolver runs against the catalog.

    Design: patch AgentFactory.create to return a SimpleNamespace wrapping a
    real AnthropicProvider. The endpoint (api.py:472-473) reads ONLY:
      - agent.llm._resolve_max_context_tokens_if_needed()  (async, no-arg)
      - agent.llm.max_context_tokens  (int)
    No other attributes are accessed — so SimpleNamespace is sufficient.

    The provider's resolver reads the local catalog; no API key, no network call.
    """

    async def test_endpoint_returns_catalog_value(
        self, client: AsyncClient, monkeypatch, tmp_path
    ) -> None:
        """GET /api/agents/myagent/context-window returns 1_000_000 (seed-driven).

        monkeypatch data_dir to an empty tmp_path so there is no ambient cache —
        the seed is the only source, proving the full restart code path.
        """
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        # Reset memo AFTER patching data_dir so the next lookup loads from seed.
        _reset_for_tests(None)

        real_provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="x")
        fake_agent = types.SimpleNamespace(llm=real_provider)

        with patch(
            "the_one.agent.factory.AgentFactory.create",
            new=AsyncMock(return_value=fake_agent),
        ):
            resp = await client.get("/api/agents/myagent/context-window")

        assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"
        payload = resp.json()
        assert payload == {"max_context_tokens": 1_000_000}, (
            f"Expected catalog-driven 1_000_000, got {payload}. "
            "If this is 200_000, the class default (not catalog) drove the result."
        )
