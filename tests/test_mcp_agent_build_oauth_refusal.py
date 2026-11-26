"""Squawk 0422: an agent-build connection refuses the OAuth consent wait at once.

An agent build has no chat to sign in through, so a 401 whose refresh fails must
not park in ``callback_handler`` until the connect timeout. A real chat csid
still waits for the operator's consent. Both run against the in-repo
``OAuthASStub`` (refresh refused) with the PRODUCTION handlers.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from tests._mcp_signin_helpers import MemoryStorage, http_source
from tests.fixtures.oauth import OAuthASStub
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPAuthRequired
from the_one.mcp.oauth import _state
from the_one.mcp.oauth.handlers import (
    agent_build_csid,
    is_agent_build_csid,
    make_oauth_handlers,
)


@pytest.fixture(autouse=True)
def _reset_oauth_state():
    _state._pending.clear()
    yield
    _state._pending.clear()


def _stale_provider(base_url: str, csid: str) -> OAuthClientProvider:
    redirect, callback = make_oauth_handlers(
        chat_session_id=csid,
        source_id="src-oauth",
        tool_call_id=None,
        resource_metadata_url=None,
        source_name="oauth-stub",
    )
    storage = MemoryStorage(
        OAuthToken(
            access_token="expired-access-token",
            token_type="Bearer",
            refresh_token="revoked-refresh-token",
            expires_in=3600,
        )
    )
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
    provider = OAuthClientProvider(
        server_url=f"{base_url}/mcp",
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect,
        callback_handler=callback,
    )
    # Locally valid, server-revoked: the first request goes out with the stale
    # token, the 401 starts the authorization flow.
    provider.context.token_expiry_time = time.time() + 3600
    return provider


def test_agent_build_csid_helper_round_trips() -> None:
    assert agent_build_csid("abc") == "agent_build:abc"
    assert is_agent_build_csid(agent_build_csid("abc"))
    assert not is_agent_build_csid("test:abc")
    assert not is_agent_build_csid("0123456789ab")


async def test_agent_build_401_with_failed_refresh_raises_auth_required_fast() -> None:
    with OAuthASStub(refresh_status=400) as stub:
        provider = _stale_provider(stub.base_url, agent_build_csid("src-oauth"))
        client = MCPClient(http_source(stub.base_url), auth_provider=provider)  # 30 s default
        started = time.monotonic()
        with pytest.raises(MCPAuthRequired):
            await client.connect()
        assert time.monotonic() - started < 2.0
    # No consent state was left pending for a flow that cannot complete.
    assert not _state._pending


async def test_real_chat_csid_still_waits_for_the_consent_code() -> None:
    with OAuthASStub(refresh_status=400) as stub:
        provider = _stale_provider(stub.base_url, "0123456789ab")
        client = MCPClient(http_source(stub.base_url), auth_provider=provider)
        task = asyncio.ensure_future(client.connect())
        try:
            await asyncio.sleep(1.0)
            assert not task.done()  # parked awaiting the operator's code
            assert _state._pending  # the consent state is registered
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
