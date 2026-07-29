"""Tests for LLMProviderRepository."""

from __future__ import annotations

import aiosqlite
import pytest
from cryptography.fernet import Fernet

from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import LLMProviderRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor


@pytest.fixture()
def encryptor(tmp_path):
    key = Fernet.generate_key()
    return Encryptor(key, key_path=tmp_path / "test.key")


@pytest.fixture()
async def repo(encryptor):
    """Yield a LLMProviderRepository backed by an in-memory DB."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await ensure_schema(conn)
    yield LLMProviderRepository(conn, encryptor)
    await conn.close()


def _make_provider(**overrides) -> LLMProviderConfig:
    defaults = {
        "id": "p1",
        "name": "Test Provider",
        "type": "openai-compatible",
        "base_url": "http://localhost:11434",
    }
    defaults.update(overrides)
    return LLMProviderConfig(**defaults)


# ── List ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_empty(repo):
    result = await repo.list()
    assert result == []


@pytest.mark.asyncio
async def test_list_returns_all_ordered_by_name(repo):
    await repo.create(_make_provider(id="p2", name="Bravo"))
    await repo.create(_make_provider(id="p1", name="Alpha"))
    result = await repo.list()
    assert [p.name for p in result] == ["Alpha", "Bravo"]


# ── Create + Get round-trip ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get_roundtrip(repo):
    provider = _make_provider()
    await repo.create(provider)
    fetched = await repo.get("p1")
    assert fetched.id == "p1"
    assert fetched.name == "Test Provider"
    assert fetched.type == "openai-compatible"
    assert fetched.base_url == "http://localhost:11434"


# ── API key encryption ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_key_encrypted_in_db(repo, encryptor):
    provider = _make_provider(api_key="sk-secret-123")
    await repo.create(provider)

    # Read raw DB value — should NOT be the plaintext
    async with repo.conn.execute("SELECT api_key FROM llm_providers WHERE id = ?", ("p1",)) as cur:
        row = await cur.fetchone()
    raw_value = row["api_key"]
    assert raw_value != "sk-secret-123"
    assert encryptor.decrypt(raw_value) == "sk-secret-123"

    # Get via repository — should return decrypted
    fetched = await repo.get("p1")
    assert fetched.api_key == "sk-secret-123"


@pytest.mark.asyncio
async def test_none_api_key_preserved(repo):
    provider = _make_provider(api_key=None)
    await repo.create(provider)
    fetched = await repo.get("p1")
    assert fetched.api_key is None


# ── Update ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_changes_fields(repo):
    await repo.create(_make_provider())
    original = await repo.get("p1")

    updated = _make_provider(name="Updated Name", base_url="http://new:1234")
    await repo.update(updated)
    fetched = await repo.get("p1")

    assert fetched.name == "Updated Name"
    assert fetched.base_url == "http://new:1234"
    assert fetched.updated_at > original.updated_at


@pytest.mark.asyncio
async def test_update_reencrypts_api_key(repo, encryptor):
    await repo.create(_make_provider(api_key="old-key"))
    await repo.update(_make_provider(api_key="new-key"))

    # Raw DB value should be the encrypted new key
    async with repo.conn.execute("SELECT api_key FROM llm_providers WHERE id = ?", ("p1",)) as cur:
        row = await cur.fetchone()
    assert encryptor.decrypt(row["api_key"]) == "new-key"

    fetched = await repo.get("p1")
    assert fetched.api_key == "new-key"


@pytest.mark.asyncio
async def test_update_nonexistent_raises(repo):
    with pytest.raises(KeyError, match="Provider not found"):
        await repo.update(_make_provider(id="nope"))


# ── Delete ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete(repo):
    await repo.create(_make_provider())
    await repo.delete("p1")
    result = await repo.list()
    assert result == []


@pytest.mark.asyncio
async def test_delete_nonexistent_raises(repo):
    with pytest.raises(KeyError, match="Provider not found"):
        await repo.delete("nope")


# ── Get non-existent ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_nonexistent_raises(repo):
    with pytest.raises(KeyError, match="Provider not found"):
        await repo.get("nope")


# ── Config dict stored as JSON ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_dict_roundtrip(repo):
    cfg = {"temperature": 0.7, "max_tokens": 4096, "nested": {"key": "value"}}
    await repo.create(_make_provider(config=cfg))
    fetched = await repo.get("p1")
    assert fetched.config == cfg


@pytest.mark.asyncio
async def test_empty_config_defaults_to_dict(repo):
    await repo.create(_make_provider())
    fetched = await repo.get("p1")
    assert fetched.config == {}


@pytest.mark.asyncio
async def test_config_num_ctx_roundtrip(repo):
    # F09-05: the per-provider Ollama runtime window rides in the free-form
    # config dict as ``config.num_ctx`` (no model/schema change). Verify it
    # persists + round-trips like any other config key.
    cfg = {"num_ctx": 16384}
    await repo.create(_make_provider(type="ollama", config=cfg))
    fetched = await repo.get("p1")
    assert fetched.config == cfg
    assert fetched.config["num_ctx"] == 16384

    # Update to a new window round-trips too.
    await repo.update(_make_provider(type="ollama", config={"num_ctx": 8192}))
    refetched = await repo.get("p1")
    assert refetched.config["num_ctx"] == 8192


# ── OAuth secrets blob (M19 F01 L01) ─────────────────────────────────────


_TOKEN_SET = {
    "access_token": "sk-ant-oat01-accesstoken123",
    "refresh_token": "sk-ant-ort01-refreshtoken456",
    "token_expires_at": 1785300000,
    "scope": "org:create_api_key user:profile user:inference",
    "token_type": "Bearer",
}


@pytest.mark.asyncio
async def test_secrets_ciphertext_at_rest(repo, encryptor):
    """The raw secrets column is ciphertext: not '{}', and no token
    substring appears in it. Decrypted read returns the original dict."""
    await repo.create(_make_provider(type="anthropic-plan", secrets=dict(_TOKEN_SET)))

    async with repo.conn.execute("SELECT secrets FROM llm_providers WHERE id = ?", ("p1",)) as cur:
        row = await cur.fetchone()
    raw_value = row["secrets"]
    assert raw_value != "{}"
    for token in (_TOKEN_SET["access_token"], _TOKEN_SET["refresh_token"]):
        assert token not in raw_value
    import json as _json

    assert _json.loads(encryptor.decrypt(raw_value)) == _TOKEN_SET

    fetched = await repo.get("p1")
    assert fetched.secrets == _TOKEN_SET


@pytest.mark.asyncio
async def test_secrets_default_empty_roundtrip(repo):
    await repo.create(_make_provider())
    fetched = await repo.get("p1")
    assert fetched.secrets == {}


@pytest.mark.asyncio
async def test_legacy_plaintext_secrets_row_reads_as_empty(repo):
    """A pre-migration row carries plaintext '{}' (the v33 column default).

    The tolerant InvalidToken decrypt reads it back as {} without raising."""
    await repo.conn.execute(
        "INSERT INTO llm_providers (id, name, type, base_url, api_key, config, secrets,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "legacy",
            "Legacy",
            "anthropic",
            "https://api.anthropic.com",
            None,
            "{}",
            "{}",
            "2026-01-01",
            "2026-01-01",
        ),
    )
    await repo.conn.commit()
    fetched = await repo.get("legacy")
    assert fetched.secrets == {}


@pytest.mark.asyncio
async def test_update_secrets_replaces_only_secrets(repo, encryptor):
    """update_secrets() writes the blob without touching other columns."""
    await repo.create(
        _make_provider(type="anthropic-plan", name="Plan", config={"thinking_enabled": True})
    )
    await repo.update_secrets("p1", dict(_TOKEN_SET))

    fetched = await repo.get("p1")
    assert fetched.secrets == _TOKEN_SET
    assert fetched.name == "Plan"
    assert fetched.config == {"thinking_enabled": True}

    # Rotated write replaces the whole blob.
    await repo.update_secrets("p1", {"access_token": "new-at"})
    refetched = await repo.get("p1")
    assert refetched.secrets == {"access_token": "new-at"}


@pytest.mark.asyncio
async def test_update_secrets_nonexistent_raises(repo):
    with pytest.raises(KeyError, match="Provider not found"):
        await repo.update_secrets("nope", {"access_token": "x"})


@pytest.mark.asyncio
async def test_full_update_persists_secrets_field(repo):
    """Model-level update() writes provider.secrets (used by the API's
    PUT preserve path, which pins managed keys from the stored row)."""
    await repo.create(_make_provider(type="anthropic-plan", secrets=dict(_TOKEN_SET)))
    updated = _make_provider(type="anthropic-plan", name="Renamed", secrets=dict(_TOKEN_SET))
    await repo.update(updated)
    fetched = await repo.get("p1")
    assert fetched.name == "Renamed"
    assert fetched.secrets == _TOKEN_SET
