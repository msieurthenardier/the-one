"""DD1 / AC8: Test connection's stale-token recovery against a REAL fixture.

``POST /api/mcp-sources/{id}/test/connect`` Phase A tries the stored tokens. When
the authorization server refuses the stored refresh token, the client cannot
connect; the route clears the stale OAuth state (``looks_like_token_failure``) or
falls through on ``MCPAuthRequired``, then Phase B kicks a fresh sign-in and the
endpoint answers ``auth_required`` with a consent URL. mcp 2.x reshaped the inputs
of that recovery (no HTTPStatusError, a failed flow can surface as a bare
CancelledError), so it is observed here end to end rather than inferred.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from tests.fixtures.oauth import OAuthASStub
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import Encryptor
from the_one.mcp import _pool


def _assert_stale_tokens_gone(stored: MCPSource) -> None:
    """The three token keys are gone. ``dcr_credentials`` was cleared too, and
    Phase B's fresh client registration then wrote a NEW record (the SDK's full
    ``OAuthClientInformationFull`` dump, which the seeded 3-key record is not)."""
    for key in ("access_token", "refresh_token", "token_expires_at"):
        assert key not in stored.secrets, key
    dcr = stored.secrets.get("dcr_credentials")
    assert dcr is None or "application_type" in dcr, dcr


def _stale_secrets() -> dict:
    return {
        "dcr_credentials": {
            "client_id": "stub-client-1",
            "redirect_uris": ["http://127.0.0.1:8484/api/oauth/callback"],
            "token_endpoint_auth_method": "none",
        },
        "access_token": "expired-access-token",
        "refresh_token": "revoked-refresh-token",
        "token_expires_at": time.time() + 3600,
    }


@pytest.fixture(autouse=True)
async def _clear_pool():
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()


@pytest.fixture
async def api_and_repo(tmp_path):
    conn = await connect_template_db(tmp_path / "stale-tokens.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        app = shared_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as client:
            yield client, repo
    await conn.close()


async def test_refresh_token_failure_recovers_into_a_fresh_sign_in(
    api_and_repo, monkeypatch
) -> None:
    client, repo = api_and_repo
    # Phase A's provider is non-interactive (sortie 22): its redirect handler refuses at
    # once, so this budget is only a backstop. Phase B (interactive) waits for consent.
    monkeypatch.setattr("the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS", 1.5)

    with OAuthASStub(refresh_status=400) as stub:
        await repo.create(
            MCPSource(
                id="src-stale",
                name="stale",
                type="streamable-http",
                config={"url": f"{stub.base_url}/mcp", "_cache": {"auth_posture": "oauth"}},
                secrets={
                    "dcr_credentials": {
                        "client_id": "stub-client-1",
                        "redirect_uris": ["http://127.0.0.1:8484/api/oauth/callback"],
                        "token_endpoint_auth_method": "none",
                    },
                    "access_token": "expired-access-token",
                    "refresh_token": "revoked-refresh-token",
                    "token_expires_at": time.time() + 3600,  # locally valid, server-revoked
                },
            )
        )
        resp = await client.post("/api/mcp-sources/src-stale/test/connect")

        assert resp.status_code == 200
        body = resp.json()
        # Recovery observed: Phase B ran and surfaced a consent URL for a new sign-in.
        assert body["status"] == "auth_required", body
        assert body["consent_url"].startswith(f"{stub.base_url}/authorize")
        # The refresh was really attempted and refused.
        # The recovery took the MCPAuthRequired fall-through (the 401 is the last
        # MCP-POST status) and cleared the four OAuth-managed secrets from the
        # stored row (DD7), so the new sign-in starts from a fresh registration.
        stored = await repo.get("src-stale")
        _assert_stale_tokens_gone(stored)
        # Phase A presented the stale credential (answered 401) and Phase B's fresh
        # flow did too; no MCP request was ever authorized, no token exchange ran
        # (the consent step is the operator's).
        assert stub.mcp_requests
        assert all(authorized is False for _method, authorized in stub.mcp_requests)


async def test_override_url_is_not_persisted_by_the_clear_and_phase_b_targets_it(
    api_and_repo, monkeypatch
) -> None:
    """DD7: the clear re-reads the stored row, so a request-body override (an
    unsaved URL) is never written back, yet Phase B signs in against the override."""
    client, repo = api_and_repo
    monkeypatch.setattr("the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS", 1.5)

    with OAuthASStub() as stored_stub, OAuthASStub() as override_stub:
        stored_config = {"url": f"{stored_stub.base_url}/mcp", "_cache": {"auth_posture": "oauth"}}
        await repo.create(
            MCPSource(
                id="src-override",
                name="override",
                type="streamable-http",
                config=dict(stored_config),
                secrets=_stale_secrets(),
            )
        )
        resp = await client.post(
            "/api/mcp-sources/src-override/test/connect",
            json={"config": {"url": f"{override_stub.base_url}/mcp"}},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["status"] == "auth_required", body
        # Phase B's consent flow targets the override URL.
        assert body["consent_url"].startswith(f"{override_stub.base_url}/authorize")
        assert stored_stub.mcp_requests == []
        stored = await repo.get("src-override")
        # The unsaved URL never reached the stored row...
        assert stored.config == stored_config
        # ...but the stale OAuth secrets did leave it.
        _assert_stale_tokens_gone(stored)
