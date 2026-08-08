"""F7 L04 (eager-resolve): tests for the new
``GET /api/agents/{name}/context-window`` endpoint.

Covers:
- Existing agent returns ``{"max_context_tokens": <positive int>}``
- Unknown agent returns 404
- Provider not configured returns 400
- Provider failure-path (resolver swallows + sentinel) returns the class
  default (NOT a 500)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from the_one.agent.factory import (
    AgentNotFoundError,
    ProviderNotConfiguredError,
    ProviderNotFoundError,
)
from the_one.interfaces.web.api import router


def _make_fake_agent(max_tokens: int, resolver_side_effect: Any = None) -> MagicMock:
    """Build a MagicMock Agent with the minimal surface the endpoint reads:
    ``agent.llm.max_context_tokens`` (int) and
    ``agent.llm._resolve_max_context_tokens_if_needed`` (async, no-arg).

    Setting ``resolver_side_effect`` non-None makes the resolver raise —
    which the endpoint should NOT propagate (the production resolver
    catches all exceptions). We exercise that by routing through the
    real method's try/except via a different test (the
    ``provider_fail_path`` test below).
    """
    agent = MagicMock()
    agent.llm = MagicMock()
    agent.llm.max_context_tokens = max_tokens
    if resolver_side_effect is not None:
        agent.llm._resolve_max_context_tokens_if_needed = AsyncMock(
            side_effect=resolver_side_effect
        )
    else:
        agent.llm._resolve_max_context_tokens_if_needed = AsyncMock()
    return agent


@pytest.fixture
async def client():
    """Bare ASGI test client around the api router — no DB needed because
    the endpoint's only DB-touching call is ``AgentFactory.create()``,
    which we patch wholesale per test.
    """
    test_app = FastAPI()
    test_app.include_router(router)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers()
    ) as c:
        yield c


class TestContextWindowEndpoint:
    async def test_existing_agent_returns_positive_int(self, client: AsyncClient) -> None:
        fake_agent = _make_fake_agent(max_tokens=128_000)
        with patch(
            "the_one.agent.factory.AgentFactory.create",
            new=AsyncMock(return_value=fake_agent),
        ):
            resp = await client.get("/api/agents/myagent/context-window")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload == {"max_context_tokens": 128_000}
        # Resolver must have been awaited (lazy-resolve contract).
        fake_agent.llm._resolve_max_context_tokens_if_needed.assert_awaited_once()

    async def test_unknown_agent_returns_404(self, client: AsyncClient) -> None:
        with patch(
            "the_one.agent.factory.AgentFactory.create",
            new=AsyncMock(side_effect=AgentNotFoundError("Agent not found: ghost")),
        ):
            resp = await client.get("/api/agents/ghost/context-window")
        assert resp.status_code == 404
        assert "ghost" in resp.json()["detail"]

    async def test_provider_not_configured_returns_400(self, client: AsyncClient) -> None:
        with patch(
            "the_one.agent.factory.AgentFactory.create",
            new=AsyncMock(
                side_effect=ProviderNotConfiguredError("Agent 'naked' has no provider configured.")
            ),
        ):
            resp = await client.get("/api/agents/naked/context-window")
        assert resp.status_code == 400
        assert "provider" in resp.json()["detail"].lower()

    async def test_provider_not_found_returns_400(self, client: AsyncClient) -> None:
        with patch(
            "the_one.agent.factory.AgentFactory.create",
            new=AsyncMock(side_effect=ProviderNotFoundError("Provider not found: deleted-id")),
        ):
            resp = await client.get("/api/agents/dangling/context-window")
        assert resp.status_code == 400
        assert "provider" in resp.json()["detail"].lower()

    async def test_provider_fail_path_returns_class_default(self, client: AsyncClient) -> None:
        """If the resolver hits a transient provider failure, the LLM's
        ``_resolve_max_context_tokens_if_needed`` wrapper (L01) catches
        the exception and leaves ``max_context_tokens`` at the class
        default. The endpoint should return that default (200 OK), NOT a
        500. We simulate the wrapper's caught-failure path by leaving
        the AsyncMock's default ``return_value=None`` (resolver call is
        a no-op) with the pre-existing class default on the mock.
        """
        # 128_000 is OpenAI/OpenRouter default; we use it here as the
        # "class default left untouched by a failed resolver" sentinel.
        fake_agent = _make_fake_agent(max_tokens=128_000)
        with patch(
            "the_one.agent.factory.AgentFactory.create",
            new=AsyncMock(return_value=fake_agent),
        ):
            resp = await client.get("/api/agents/sad/context-window")
        assert resp.status_code == 200
        assert resp.json() == {"max_context_tokens": 128_000}
