"""TokenStorage round-trip tests for MCPSourceTokenStorage."""

from __future__ import annotations

import time

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.mcp.oauth.storage import MCPSourceTokenStorage


@pytest.fixture
async def repo_with_source(tmp_path):
    """An MCPSourceRepository with one seeded streamable-http source."""
    db_path = tmp_path / "oauth-storage-test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    source = MCPSource(
        id="src-oauth-1",
        name="Remote MCP",
        type="streamable-http",
        config={"url": "https://api.example.com/mcp"},
        secrets={},
    )
    await repo.create(source)
    try:
        yield repo, "src-oauth-1"
    finally:
        await conn.close()


async def test_token_storage_full_contract(
    repo_with_source, monkeypatch
) -> None:
    """A2 — full TokenStorage contract:

      - get-when-absent → None;
      - set/get round-trip with all fields persists access_token,
        refresh_token, token_type, scope, and ``token_expires_at``
        (translated from ``expires_in``);
      - refresh-token rotation overwrites both tokens in one
        ``repo.update``;
      - ``set_tokens(expires_in=None)`` clears any prior epoch;
      - clock translation: write at t0 with ``expires_in=300``, read
        at t0+100 returns ``expires_in=200``;
      - malformed ``token_expires_at`` returns ``expires_in=None``
        rather than crashing;
      - partial state (no refresh_token persisted) round-trips with
        ``refresh_token=None``.
    """
    repo, sid = repo_with_source
    storage = MCPSourceTokenStorage(repo, sid)

    assert await storage.get_tokens() is None

    # Full set
    before = time.time()
    await storage.set_tokens(
        OAuthToken(
            access_token="acc-tok-1",
            token_type="Bearer",
            expires_in=300,
            refresh_token="ref-tok-1",
            scope="read write",
        )
    )
    after = time.time()
    src = await repo.get(sid)
    assert src.secrets["access_token"] == "acc-tok-1"
    assert src.secrets["refresh_token"] == "ref-tok-1"
    assert src.secrets["scope"] == "read write"
    assert src.secrets["token_type"] == "Bearer"
    assert before + 300 - 1 <= src.secrets["token_expires_at"] <= after + 300 + 1
    loaded = await storage.get_tokens()
    assert loaded is not None
    assert loaded.access_token == "acc-tok-1"
    assert loaded.refresh_token == "ref-tok-1"
    assert 295 <= (loaded.expires_in or 0) <= 301

    # Rotation overwrites both
    await storage.set_tokens(
        OAuthToken(
            access_token="new-acc", refresh_token="new-ref", expires_in=600
        )
    )
    loaded = await storage.get_tokens()
    assert loaded is not None
    assert loaded.access_token == "new-acc"
    assert loaded.refresh_token == "new-ref"
    assert 595 <= (loaded.expires_in or 0) <= 601

    # expires_in=None clears prior epoch.
    await storage.set_tokens(OAuthToken(access_token="t1", expires_in=None))
    src = await repo.get(sid)
    assert "token_expires_at" not in src.secrets

    # Clock translation
    fake_now = 1_700_000_000.0
    monkeypatch.setattr(
        "the_one.mcp.oauth.storage.time.time", lambda: fake_now
    )
    await storage.set_tokens(OAuthToken(access_token="a", expires_in=300))
    monkeypatch.setattr(
        "the_one.mcp.oauth.storage.time.time", lambda: fake_now + 100.0
    )
    loaded = await storage.get_tokens()
    assert loaded is not None
    assert loaded.expires_in == 200
    monkeypatch.undo()

    # Malformed token_expires_at + partial state (no refresh_token).
    src = await repo.get(sid)
    src.secrets = {"access_token": "acc-only", "token_expires_at": "not-a-number"}
    await repo.update(src)
    loaded = await storage.get_tokens()
    assert loaded is not None
    assert loaded.access_token == "acc-only"
    assert loaded.refresh_token is None
    assert loaded.expires_in is None


async def test_client_info_round_trip(repo_with_source) -> None:
    """A2 — get/set OAuthClientInformationFull through ``dcr_credentials``,
    with the ``registration_method`` discriminator default of ``"dcr"``.
    """
    repo, sid = repo_with_source
    storage = MCPSourceTokenStorage(repo, sid)

    assert await storage.get_client_info() is None

    info = OAuthClientInformationFull(
        client_id="cid-1",
        client_secret="sek-1",
        redirect_uris=["http://127.0.0.1:8484/api/oauth/callback"],
    )
    await storage.set_client_info(info)

    source = await repo.get(sid)
    assert isinstance(source.secrets["dcr_credentials"], dict)
    assert source.secrets["dcr_credentials"]["registration_method"] == "dcr"
    assert source.secrets["dcr_credentials"]["client_id"] == "cid-1"

    loaded = await storage.get_client_info()
    assert loaded is not None
    assert loaded.client_id == "cid-1"
    assert loaded.client_secret == "sek-1"
    assert str(loaded.redirect_uris[0]).startswith(
        "http://127.0.0.1:8484/api/oauth/callback"
    )
