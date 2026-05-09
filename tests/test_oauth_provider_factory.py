"""Unit tests for the_one.mcp.oauth.provider_factory.build_oauth_provider_for_source."""

from __future__ import annotations

import aiosqlite
import httpx
import pytest
from cryptography.fernet import Fernet
from mcp.client.auth import OAuthClientProvider

from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.mcp.oauth import (
    ManualOAuthClientProvider,
    build_oauth_provider_for_source,
)


@pytest.fixture
async def repo_with_source(tmp_path):
    """An MCPSourceRepository + a streamable-http MCPSource with empty secrets."""
    db_path = tmp_path / "factory-test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

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
    """A1 — registration_method != 'manual' → ``OAuthClientProvider`` (DCR path)."""
    repo, source = repo_with_source
    source.secrets["dcr_credentials"] = {
        "client_id": "dcr-cid-1",
        "registration_method": "dcr",
    }
    result = build_oauth_provider_for_source(
        source, repo, "csid-1", source_id="src-factory-1"
    )
    assert result is not None
    # The DCR path returns the standard SDK provider, NOT our manual subclass.
    assert isinstance(result, OAuthClientProvider)
    assert not isinstance(result, ManualOAuthClientProvider)
    # And conforms to httpx.Auth (so callers can pass via auth=).
    assert isinstance(result, httpx.Auth)


async def test_factory_returns_manual_provider_for_manual_method(repo_with_source) -> None:
    """A1 — registration_method == 'manual' → ``ManualOAuthClientProvider``.

    The synthesized OAuthMetadata derives from the operator-supplied
    auth/token endpoints; no PRM/OASM discovery + no DCR happens at flow time.
    """
    repo, source = repo_with_source
    source.secrets["dcr_credentials"] = {
        "client_id": "manual-cid-1",
        "auth_endpoint": "https://github.com/login/oauth/authorize",
        "token_endpoint": "https://github.com/login/oauth/access_token",
        "registration_method": "manual",
    }
    result = build_oauth_provider_for_source(
        source, repo, "csid-1", source_id="src-factory-1"
    )
    assert result is not None
    assert isinstance(result, ManualOAuthClientProvider)
    # The synthesized OAuthMetadata carries the operator's endpoints.
    metadata = result._synthesized_oauth_metadata()
    assert str(metadata.authorization_endpoint) == "https://github.com/login/oauth/authorize"
    assert str(metadata.token_endpoint) == "https://github.com/login/oauth/access_token"


async def test_factory_wires_client_metadata_with_loopback_redirect(repo_with_source) -> None:
    """A1 — OAuthClientMetadata uses loopback redirect bound to settings.port,
    grant_types include refresh_token, response_types=['code'],
    token_endpoint_auth_method='none' (PKCE public-client per RFC 6749 §2.3.1).
    """
    from the_one.config import settings

    repo, source = repo_with_source
    source.secrets["dcr_credentials"] = {
        "client_id": "any-cid",
        "registration_method": "dcr",
    }
    result = build_oauth_provider_for_source(
        source, repo, "csid-1", source_id="src-factory-1"
    )
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
