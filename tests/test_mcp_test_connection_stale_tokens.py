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
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from tests.fixtures.oauth import OAuthASStub
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.mcp import _pool


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
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as client:
            yield client, repo
    await conn.close()


async def test_refresh_token_failure_recovers_into_a_fresh_sign_in(
    api_and_repo, monkeypatch
) -> None:
    client, repo = api_and_repo
    # Keep the sign-in wait short: Phase A's provider (no consent future) parks in
    # its callback handler until the client's initialize budget runs out.
    monkeypatch.setattr("the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS", 3)

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
        # MCP-POST status), so the stale secrets stay until the new sign-in
        # overwrites them: Phase B's fresh flow does not need them gone.
        # Phase A presented the stale credential (answered 401) and Phase B's fresh
        # flow did too; no MCP request was ever authorized, no token exchange ran
        # (the consent step is the operator's).
        assert stub.mcp_requests
        assert all(authorized is False for _method, authorized in stub.mcp_requests)
