"""Tests for OAuth-managed secrets GET-strip + PUT-preserve protection."""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


@pytest.fixture
async def client_and_repo(tmp_path):
    """FastAPI client paired with a back-channel repo for direct seeding/inspection.

    Both share the same connection + encryptor so writes via ``repo``
    are visible via the API and vice-versa. The repo is the deliberate
    bypass for assertions: GET strips the managed keys from the
    response, so verifying preservation requires reading the row
    directly.
    """
    db_path = tmp_path / "secrets.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)

    with (
        patch(
            "the_one.interfaces.web.api.get_connection", return_value=conn
        ),
        patch(
            "the_one.interfaces.web.api.get_encryptor", return_value=encryptor
        ),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, repo

    await conn.close()


async def _seed(repo: MCPSourceRepository, sid: str, secrets: dict) -> None:
    src = MCPSource(
        id=sid,
        name="Remote",
        type="streamable-http",
        config={"url": "https://api.example.com/mcp"},
        secrets=secrets,
    )
    await repo.create(src)


async def test_get_strips_managed_keys_and_masks_oauth_client_secret(
    client_and_repo,
) -> None:
    """A10 — GET response omits all 4 managed keys, masks oauth_client_secret."""
    client, repo = client_and_repo
    await _seed(
        repo,
        "src-A",
        {
            "access_token": "acc-tok-real",
            "refresh_token": "ref-tok-real",
            "token_expires_at": 1_700_000_000.0,
            "dcr_credentials": {"client_id": "cid", "client_secret": "csek"},
            "oauth_client_secret": "client-sek-very-real",
        },
    )

    resp = await client.get("/api/mcp-sources/src-A")
    assert resp.status_code == 200
    payload_secrets = resp.json()["secrets"]

    for key in (
        "access_token",
        "refresh_token",
        "token_expires_at",
        "dcr_credentials",
    ):
        assert key not in payload_secrets

    assert payload_secrets["oauth_client_secret"] == "***...real"
    assert "acc-tok-real" not in resp.text
    assert "ref-tok-real" not in resp.text
    assert "client-sek-very-real" not in resp.text


async def test_put_preservation_against_attacker_and_innocent_payloads(
    client_and_repo,
) -> None:
    """A11a + A11b — PUT preserves all 4 OAuth-managed keys regardless
    of what the operator sends. Verified via back-channel ``repo.get``
    (deliberate API-bypass — GET strips the managed keys).

    A11a: attacker payload {"access_token": "evil", "refresh_token": "evil"}.
    A11b: innocent payload {"oauth_client_secret": "__MASKED__"}.
    """
    client, repo = client_and_repo
    await _seed(
        repo,
        "src-B",
        {
            "access_token": "real-acc",
            "refresh_token": "real-ref",
            "token_expires_at": 1_700_000_000.0,
            "dcr_credentials": {"client_id": "cid"},
            "oauth_client_secret": "preserved-client-sek",
        },
    )

    # A11a: attacker payload
    resp = await client.put(
        "/api/mcp-sources/src-B",
        json={
            "name": "Remote",
            "type": "streamable-http",
            "config": {"url": "https://api.example.com/mcp"},
            "secrets": {
                "access_token": "attacker-acc",
                "refresh_token": "attacker-ref",
            },
        },
    )
    assert resp.status_code == 200
    stored = await repo.get("src-B")
    assert stored.secrets["access_token"] == "real-acc"
    assert stored.secrets["refresh_token"] == "real-ref"
    assert stored.secrets["token_expires_at"] == 1_700_000_000.0
    assert stored.secrets["dcr_credentials"] == {"client_id": "cid"}

    # A11b: innocent payload — oauth_client_secret sentinel preserves
    # AND managed keys preserve too. Use a fresh source since the
    # A11a PUT above dropped oauth_client_secret per REST replace
    # semantics for non-managed keys.
    await _seed(
        repo,
        "src-B2",
        {
            "access_token": "real-acc-2",
            "refresh_token": "real-ref-2",
            "token_expires_at": 1_700_000_001.0,
            "dcr_credentials": {"client_id": "cid-2"},
            "oauth_client_secret": "preserved-client-sek",
        },
    )
    resp = await client.put(
        "/api/mcp-sources/src-B2",
        json={
            "name": "Remote",
            "type": "streamable-http",
            "config": {"url": "https://api.example.com/mcp"},
            "secrets": {"oauth_client_secret": "__MASKED__"},
        },
    )
    assert resp.status_code == 200
    stored = await repo.get("src-B2")
    assert stored.secrets["access_token"] == "real-acc-2"
    assert stored.secrets["refresh_token"] == "real-ref-2"
    assert stored.secrets["token_expires_at"] == 1_700_000_001.0
    assert stored.secrets["dcr_credentials"] == {"client_id": "cid-2"}
    assert stored.secrets["oauth_client_secret"] == "preserved-client-sek"


async def test_put_drops_managed_key_when_source_has_none(
    client_and_repo,
) -> None:
    """A11c — PUT with a managed-key value on a source without one drops it.

    No-managed-keys-leak path: only the OAuth flow may write managed
    keys; an operator PUT can never introduce them via the API.
    """
    client, repo = client_and_repo
    await _seed(repo, "src-D", {"oauth_client_secret": "real-client-sek"})

    resp = await client.put(
        "/api/mcp-sources/src-D",
        json={
            "name": "Remote",
            "type": "streamable-http",
            "config": {"url": "https://api.example.com/mcp"},
            "secrets": {
                "access_token": "evil-acc",
                "oauth_client_secret": "__MASKED__",
            },
        },
    )
    assert resp.status_code == 200
    stored = await repo.get("src-D")
    assert "access_token" not in stored.secrets
    assert stored.secrets["oauth_client_secret"] == "real-client-sek"
