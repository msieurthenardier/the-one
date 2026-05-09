"""Tests for the FastAPI ``/api/oauth/manual-register`` route (F5 L5)."""

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
    """FastAPI client + DB-backed MCPSourceRepository wired into the API."""
    db_path = tmp_path / "manual-register.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    # Seed one source so the success path has a target.
    await repo.create(
        MCPSource(
            id="src-mr-1",
            name="Source for manual-register",
            type="streamable-http",
            config={"url": "https://api.example.com/mcp"},
        )
    )

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, repo

    await conn.close()


async def test_manual_register_persists_dcr_credentials(client_and_repo) -> None:
    """A2 — POST persists the four-key dcr_credentials blob with
    ``registration_method='manual'`` + an iso-stamped ``registered_at``.
    """
    c, repo = client_and_repo
    resp = await c.post(
        "/api/oauth/manual-register",
        json={
            "source_id": "src-mr-1",
            "client_id": "operator-cid-1",
            "auth_endpoint": "https://github.com/login/oauth/authorize",
            "token_endpoint": "https://github.com/login/oauth/access_token",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "registered"
    assert body["source_id"] == "src-mr-1"

    src = await repo.get("src-mr-1")
    dcr = src.secrets["dcr_credentials"]
    assert dcr["client_id"] == "operator-cid-1"
    assert dcr["auth_endpoint"] == "https://github.com/login/oauth/authorize"
    assert dcr["token_endpoint"] == "https://github.com/login/oauth/access_token"
    assert dcr["registration_method"] == "manual"
    # registered_at is an iso-stamped UTC timestamp
    assert "T" in dcr["registered_at"]
    assert dcr["registered_at"].endswith("+00:00")


async def test_manual_register_400_on_missing_fields(client_and_repo) -> None:
    """A2 — 400 with descriptive detail when any required field is missing."""
    c, _repo = client_and_repo
    # Missing token_endpoint
    resp = await c.post(
        "/api/oauth/manual-register",
        json={
            "source_id": "src-mr-1",
            "client_id": "x",
            "auth_endpoint": "https://example.com/authorize",
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "token_endpoint" in detail


async def test_manual_register_404_on_unknown_source(client_and_repo) -> None:
    """A2 — 404 with descriptive detail when source_id does not exist."""
    c, _repo = client_and_repo
    resp = await c.post(
        "/api/oauth/manual-register",
        json={
            "source_id": "src-does-not-exist",
            "client_id": "x",
            "auth_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
        },
    )
    assert resp.status_code == 404
    assert "src-does-not-exist" in resp.json()["detail"]
