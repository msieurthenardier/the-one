"""Unit tests for the_one.mcp.oauth.provider_factory.build_oauth_provider_for_source."""

from __future__ import annotations

import asyncio

import httpx2
import pytest
from cryptography.fernet import Fernet
from mcp.client.auth import OAuthClientProvider

from tests._schema_template import connect_template_db
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import Encryptor
from the_one.mcp.oauth import (
    build_oauth_provider_for_source,
)


@pytest.fixture
async def repo_with_source(tmp_path):
    """An MCPSourceRepository + a streamable-http MCPSource with empty secrets."""
    db_path = tmp_path / "factory-test.db"
    conn = await connect_template_db(db_path)

    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    source = MCPSource(
        id="src-factory-1",
        name="Remote MCP",
        type="streamable-http",
        config={"url": "https://api.example.com/mcp"},
        secrets={},
    )
    await repo.create(source)
    try:
        yield repo, source
    finally:
        await conn.close()


async def test_factory_returns_none_when_dcr_credentials_absent(repo_with_source) -> None:
    """A1 — empty secrets / no client_id → None.

    Caller can then construct ``MCPClient(source, auth_provider=None)`` per
    the L4 contract, and the lazy-path 401 surfaces via ``MCPAuthRequired``.
    """
    repo, source = repo_with_source
    # Empty secrets
    result = build_oauth_provider_for_source(source, repo, "csid-1")
    assert result is None

    # dcr_credentials present but missing client_id
    source.secrets["dcr_credentials"] = {}
    result = build_oauth_provider_for_source(source, repo, "csid-1")
    assert result is None


async def test_factory_returns_oauth_client_provider_for_dcr(repo_with_source) -> None:
    """A1 — dcr_credentials present with client_id → ``OAuthClientProvider`` (DCR path)."""
    repo, source = repo_with_source
    source.secrets["dcr_credentials"] = {
        "client_id": "dcr-cid-1",
    }
    result = build_oauth_provider_for_source(source, repo, "csid-1", source_id="src-factory-1")
    assert result is not None
    # The DCR path returns the standard SDK provider.
    assert isinstance(result, OAuthClientProvider)
    # And conforms to httpx2.Auth (so callers can pass via auth=).
    assert isinstance(result, httpx2.Auth)


async def test_factory_wires_client_metadata_with_loopback_redirect(repo_with_source) -> None:
    """A1 — OAuthClientMetadata uses loopback redirect bound to settings.port,
    grant_types include refresh_token, response_types=['code'],
    token_endpoint_auth_method='none' (PKCE public-client per RFC 6749 §2.3.1).
    """
    from the_one.config import settings

    repo, source = repo_with_source
    source.secrets["dcr_credentials"] = {
        "client_id": "any-cid",
    }
    result = build_oauth_provider_for_source(source, repo, "csid-1", source_id="src-factory-1")
    assert result is not None
    cm = result.context.client_metadata
    assert cm.client_name == "the-one"
    assert cm.token_endpoint_auth_method == "none"
    assert "authorization_code" in cm.grant_types
    assert "refresh_token" in cm.grant_types
    assert cm.response_types == ["code"]
    assert len(cm.redirect_uris) == 1
    redirect = str(cm.redirect_uris[0])
    assert redirect.startswith(f"http://127.0.0.1:{settings.port}")
    assert redirect.endswith("/api/oauth/callback")


async def test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source(
    repo_with_source,
) -> None:
    """F6.5 L3 — ``allow_dcr_bootstrap=True`` constructs an
    ``OAuthClientProvider`` even when ``dcr_credentials`` is absent.

    The Test connection endpoint uses this path: an operator clicks Test on
    a freshly-saved source with no creds; the SDK runs DCR + auth in one
    round-trip; tokens persist. Without ``allow_dcr_bootstrap=True`` the
    factory returns None (the lazy 401 path), which is the chat-path default.
    """
    repo, source = repo_with_source
    # Negative control — same call without the bootstrap flag returns None
    # because ``dcr_credentials`` is absent. Documents the boundary in one
    # test.
    no_bootstrap = build_oauth_provider_for_source(source, repo, "test:src-factory-1")
    assert no_bootstrap is None

    # Bootstrap path — non-None ``OAuthClientProvider`` is returned even
    # though ``dcr_credentials`` is absent. Reached only when
    # ``allow_dcr_bootstrap=True`` AND ``chat_session_id`` is non-None
    # AND ``dcr_credentials`` is absent.
    result = build_oauth_provider_for_source(
        source,
        repo,
        "test:src-factory-1",
        source_id="src-factory-1",
        allow_dcr_bootstrap=True,
    )
    assert result is not None
    assert isinstance(result, OAuthClientProvider)


async def test_factory_threads_consent_url_future(repo_with_source) -> None:
    """F6.5 L3 — consent_url_future is forwarded to make_oauth_handlers.

    Verify by constructing a provider with a real future, then invoking
    the provider's redirect_handler with an auth URL that includes a
    state param, and confirming the future resolves with that URL.
    """
    repo, source = repo_with_source
    source.secrets["dcr_credentials"] = {"client_id": "dcr-cid-test"}

    consent_url_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    provider = build_oauth_provider_for_source(
        source,
        repo,
        "test:src-factory-1",
        source_id="src-factory-1",
        consent_url_future=consent_url_future,
    )
    assert provider is not None
    assert isinstance(provider, OAuthClientProvider)

    # Invoke the redirect_handler (accessible via the provider's context).
    auth_url = "https://example.com/auth?state=test-state-xyz&client_id=dcr-cid-test"
    await provider.context.redirect_handler(auth_url)

    assert consent_url_future.done()
    assert consent_url_future.result() == auth_url
