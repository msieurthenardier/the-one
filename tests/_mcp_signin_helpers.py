"""Shared helpers for the real-fixture MCP sign-in tests (Mission 29, DD1/DD2).

Builds an ``OAuthClientProvider`` against the in-repo ``OAuthASStub`` with an
in-memory token store and the PRODUCTION redirect/callback handlers
(``make_oauth_handlers``). The consent redirect is completed in-process through
``the_one.mcp.oauth._state.resolve`` (what ``GET /api/oauth/callback`` calls), so
``MCPClient.connect`` can finish a whole sign-in without a browser.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import httpx2
from asgi_lifespan import LifespanManager
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from the_one.db.models import MCPSource
from the_one.mcp.oauth import _state
from the_one.mcp.oauth.handlers import make_oauth_handlers
from the_one.mcp.transports import streamable_http as _sh


@asynccontextmanager
async def serve_asgi(monkeypatch, wrapper):
    """Serve an ASGI ``wrapper`` through the transport's test seam
    (wrapper -> ``LifespanManager`` -> ``httpx2.ASGITransport`` ->
    ``_test_http_client_override``). Yields the httpx2 client."""
    async with LifespanManager(wrapper):
        client = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=wrapper), base_url="http://localhost"
        )
        monkeypatch.setattr(_sh, "_test_http_client_override", client)
        try:
            yield client
        finally:
            await client.aclose()


class MemoryStorage(TokenStorage):
    def __init__(self, tokens: OAuthToken | None = None) -> None:
        self.tokens = tokens
        self.client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


def http_source(base_url: str, name: str = "oauth-stub") -> MCPSource:
    return MCPSource(
        id="src-oauth",
        name=name,
        type="streamable-http",
        config={"url": f"{base_url}/mcp", "headers": {}},
        secrets={},
    )


def build_provider(
    base_url: str,
    *,
    iss="match",
    storage: MemoryStorage | None = None,
) -> tuple[OAuthClientProvider, MemoryStorage]:
    """A provider whose consent redirect is auto-completed via ``_state.resolve``.

    ``iss`` is the RFC 9207 value the (simulated) callback route forwards:
    ``"match"`` (the stub's base URL as the SDK sees it), ``None`` (omitted) or
    any other string (a mismatch).
    """
    storage = storage or MemoryStorage()
    redirect, callback = make_oauth_handlers(
        chat_session_id="test-session",
        source_id="src-oauth",
        tool_call_id=None,
        resource_metadata_url=None,
        source_name="oauth-stub",
    )

    async def redirect_and_complete(authorization_url: str) -> None:
        await redirect(authorization_url)
        state = parse_qs(urlsplit(authorization_url).query)["state"][0]
        issuer = base_url if iss == "match" else iss

        def _complete() -> None:
            _state.resolve(state, "fake-auth-code", state, issuer)

        asyncio.get_running_loop().call_soon(_complete)

    metadata = OAuthClientMetadata(
        client_name="the-one",
        redirect_uris=["http://127.0.0.1:1/api/oauth/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    provider = OAuthClientProvider(
        server_url=f"{base_url}/mcp",
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect_and_complete,
        callback_handler=callback,
    )
    return provider, storage
