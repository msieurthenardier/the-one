"""Squawk 0444: a stored, expired access token is refreshed, not sent.

Every connection builds a fresh provider. The SDK's ``_initialize`` loads stored
tokens without learning their expiry, so an expired token was sent, 401ed and went
straight to interactive sign-in. ``TheOneOAuthClientProvider`` seeds the expiry on
load. Observed end to end against the in-repo ``OAuthASStub``.
"""

from __future__ import annotations

import time

import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from tests._mcp_signin_helpers import MemoryStorage, http_source
from tests.fixtures.oauth import OAuthASStub
from the_one.mcp.client import MCPClient
from the_one.mcp.oauth import _state
from the_one.mcp.oauth.provider import TheOneOAuthClientProvider


@pytest.fixture(autouse=True)
def _reset_oauth_state():
    _state._pending.clear()
    yield
    _state._pending.clear()


class _SignInRequestedError(Exception):
    """Raised by the callback handler when interactive authorization is reached."""


def _provider(
    base_url: str, token: OAuthToken, *, interactive_expected: bool = False
) -> tuple[TheOneOAuthClientProvider, MemoryStorage, list[str]]:
    redirects: list[str] = []

    async def redirect(url: str) -> None:
        redirects.append(url)

    async def callback() -> tuple[str, str | None]:
        if interactive_expected:
            raise _SignInRequestedError
        raise AssertionError("interactive authorization must not run")

    storage = MemoryStorage(token)
    storage.client_info = OAuthClientInformationFull(
        client_id="stub-client-1",
        redirect_uris=["http://127.0.0.1:1/api/oauth/callback"],
        token_endpoint_auth_method="none",
    )
    metadata = OAuthClientMetadata(
        client_name="the-one",
        redirect_uris=["http://127.0.0.1:1/api/oauth/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    provider = TheOneOAuthClientProvider(
        server_url=f"{base_url}/mcp",
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect,
        callback_handler=callback,
    )
    return provider, storage, redirects


async def test_expired_stored_token_is_refreshed_not_sent() -> None:
    with OAuthASStub() as stub:
        token = OAuthToken(
            access_token="expired-access-token",
            token_type="Bearer",
            refresh_token="stored-refresh-token",
            expires_in=0,  # what MCPSourceTokenStorage returns for a past token_expires_at
        )
        provider, storage, redirects = _provider(stub.base_url, token)
        client = MCPClient(http_source(stub.base_url), auth_provider=provider)
        await client.connect()
        try:
            assert "refresh_token" in stub.token_requests
            assert "authorization_code" not in stub.token_requests
            # The expired token never reached the MCP endpoint.
            assert stub.mcp_requests
            assert all(authorized for _method, authorized in stub.mcp_requests)
            assert redirects == []
            assert storage.tokens is not None
            assert storage.tokens.access_token == "stub-access-token"
        finally:
            await client.disconnect()


async def test_expired_stored_token_is_invalid_right_after_initialize(monkeypatch) -> None:
    # A frozen clock (a coarse one, as on Windows): no movement between seeding and the
    # check, so the expiry must be strictly in the past, not ``now + 0``.
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0)
    token = OAuthToken(
        access_token="expired-access-token",
        token_type="Bearer",
        refresh_token="stored-refresh-token",
        expires_in=0,
    )
    provider, _storage, _redirects = _provider("http://127.0.0.1:1", token)
    await provider._initialize()
    assert provider.context.token_expiry_time
    assert provider.context.is_token_valid() is False
    assert provider.context.can_refresh_token()


async def test_failed_refresh_falls_through_to_interactive_authorization() -> None:
    with OAuthASStub(refresh_status=400) as stub:
        token = OAuthToken(
            access_token="expired-access-token",
            token_type="Bearer",
            refresh_token="revoked-refresh-token",
            expires_in=0,
        )
        provider, _storage, redirects = _provider(stub.base_url, token, interactive_expected=True)
        client = MCPClient(http_source(stub.base_url), auth_provider=provider)
        with pytest.raises(BaseException) as excinfo:  # noqa: PT011
            await client.connect()
        assert "refresh_token" in stub.token_requests
        assert "authorization_code" not in stub.token_requests
        assert redirects, f"redirect handler not invoked (raised {excinfo.value!r})"


async def test_stored_token_without_expiry_is_sent_as_is() -> None:
    with OAuthASStub() as stub:
        token = OAuthToken(
            access_token="stub-access-token",
            token_type="Bearer",
            refresh_token="stored-refresh-token",
            expires_in=None,
        )
        provider, _storage, redirects = _provider(stub.base_url, token)
        client = MCPClient(http_source(stub.base_url), auth_provider=provider)
        await client.connect()
        try:
            assert stub.token_requests == []
            assert stub.mcp_requests
            assert all(authorized for _method, authorized in stub.mcp_requests)
            assert redirects == []
            assert provider.context.token_expiry_time is None
        finally:
            await client.disconnect()


async def test_unexpired_stored_token_is_used_without_refresh() -> None:
    with OAuthASStub() as stub:
        token = OAuthToken(
            access_token="stub-access-token",
            token_type="Bearer",
            refresh_token="stored-refresh-token",
            expires_in=3600,
        )
        provider, _storage, redirects = _provider(stub.base_url, token)
        client = MCPClient(http_source(stub.base_url), auth_provider=provider)
        started = time.time()
        await client.connect()
        try:
            assert stub.token_requests == []
            assert all(authorized for _method, authorized in stub.mcp_requests)
            assert redirects == []
            assert provider.context.token_expiry_time is not None
            assert provider.context.token_expiry_time >= started + 3500
        finally:
            await client.disconnect()
