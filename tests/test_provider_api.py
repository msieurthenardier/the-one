"""Tests for LLM provider REST API endpoints."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


class _StubOpenAIError(Exception):
    """Stand-in for ``openai.OpenAIError`` used by the test_provider handler's
    expected-error catch branch."""


class _StubAnthropicError(Exception):
    """Stand-in for ``anthropic.AnthropicError`` used by the test_provider
    handler's expected-error catch branch."""


def _mock_openai_module() -> MagicMock:
    """Create a mock ``openai`` module with AsyncOpenAI."""
    mod = MagicMock()
    mock_client = AsyncMock()
    mod.AsyncOpenAI.return_value = mock_client
    # The api handler does `except openai.OpenAIError`, so the module must
    # expose a real exception class (MagicMock attributes aren't valid in
    # `except` clauses).
    mod.OpenAIError = _StubOpenAIError
    return mod


def _mock_anthropic_module() -> MagicMock:
    """Create a mock ``anthropic`` module with AsyncAnthropic."""
    mod = MagicMock()
    mock_client = AsyncMock()
    mod.AsyncAnthropic.return_value = mock_client
    # The api handler does `except anthropic.AnthropicError`, so the module
    # must expose a real exception class.
    mod.AnthropicError = _StubAnthropicError
    return mod


@pytest.fixture
async def client(tmp_path):
    """Create a test client with an isolated DB and test encryptor."""
    db_path = tmp_path / "test.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    # Create a test encryptor with a temp key file
    test_key = Fernet.generate_key()
    key_path = tmp_path / "test.key"
    key_path.write_bytes(test_key)
    test_encryptor = Encryptor(test_key, key_path=key_path)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=test_encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


# ── Masking helper ───────────────────────────────────────────────────────


class TestMaskApiKey:
    def test_mask_none(self) -> None:
        from the_one.interfaces.web.api import _mask_api_key

        assert _mask_api_key(None) is None

    def test_mask_empty(self) -> None:
        from the_one.interfaces.web.api import _mask_api_key

        assert _mask_api_key("") == ""

    def test_mask_short(self) -> None:
        from the_one.interfaces.web.api import _mask_api_key

        assert _mask_api_key("abc") == "***"
        assert _mask_api_key("abcd") == "***"

    def test_mask_long(self) -> None:
        from the_one.interfaces.web.api import _mask_api_key

        assert _mask_api_key("sk-1234567890") == "***...7890"


# ── Provider CRUD ────────────────────────────────────────────────────────


class TestProviderAPI:
    async def test_create_provider(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/providers",
            json={
                "name": "Local Ollama",
                "type": "ollama",
                "base_url": "http://localhost:11434/v1",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Local Ollama"
        assert data["type"] == "ollama"
        assert len(data["id"]) == 12

    async def test_create_provider_with_api_key(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/providers",
            json={
                "name": "OpenAI",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test1234567890",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # Response should have masked key
        assert data["api_key"] == "***...7890"

    async def test_list_providers(self, client: AsyncClient) -> None:
        await client.post(
            "/api/providers",
            json={"name": "P1", "type": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        await client.post(
            "/api/providers",
            json={"name": "P2", "type": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        resp = await client.get("/api/providers")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "P1" in names
        assert "P2" in names

    async def test_get_provider(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "Test",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-secretkey1234",
            },
        )
        provider_id = create_resp.json()["id"]

        resp = await client.get(f"/api/providers/{provider_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test"
        # Key must be masked in GET response
        assert data["api_key"] == "***...1234"

    async def test_get_provider_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/providers/nonexistent")
        assert resp.status_code == 404

    async def test_update_provider(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/providers",
            json={"name": "Before", "type": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        provider_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/providers/{provider_id}",
            json={"name": "After", "type": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    async def test_update_provider_not_found(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/providers/nonexistent",
            json={"name": "X", "type": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        assert resp.status_code == 404

    async def test_update_preserves_masked_key(self, client: AsyncClient) -> None:
        """PUT with the __MASKED__ sentinel should preserve the original stored key."""
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "Test",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-mysecretkey9999",
            },
        )
        provider_id = create_resp.json()["id"]

        # Update with the masked sentinel — original should be preserved
        resp = await client.put(
            f"/api/providers/{provider_id}",
            json={
                "name": "Updated",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "__MASKED__",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
        # The masked response should reflect the ORIGINAL stored key's last-4
        # (not the literal sentinel string).
        assert resp.json()["api_key"] == "***...9999"

        # Verify a fresh GET shows the same mask — confirms the stored value is
        # still the original, not the sentinel literal.
        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.json()["api_key"] == "***...9999"

    async def test_update_replaces_key_when_not_masked(self, client: AsyncClient) -> None:
        """PUT with a non-sentinel api_key should replace the stored key."""
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "Test",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-mysecretkey9999",
            },
        )
        provider_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/providers/{provider_id}",
            json={
                "name": "Updated",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-newkey7777",
            },
        )
        assert resp.status_code == 200
        # The masked response should reflect the NEW stored key's last-4.
        assert resp.json()["api_key"] == "***...7777"

        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.json()["api_key"] == "***...7777"

    async def test_delete_provider(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/providers",
            json={"name": "ToDelete", "type": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        provider_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/providers/{provider_id}")
        assert resp.status_code == 200

        resp = await client.get(f"/api/providers/{provider_id}")
        assert resp.status_code == 404

    async def test_delete_provider_not_found(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/providers/nonexistent")
        assert resp.status_code == 404

    async def test_get_provider_no_api_key(self, client: AsyncClient) -> None:
        """Provider without an API key should return null for api_key."""
        create_resp = await client.post(
            "/api/providers",
            json={"name": "NoKey", "type": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        provider_id = create_resp.json()["id"]

        resp = await client.get(f"/api/providers/{provider_id}")
        assert resp.json()["api_key"] is None


# ── Encryption rotation ────────────────────────────────────────────────


class TestEncryptionRotation:
    async def test_rotate_key(self, client: AsyncClient) -> None:
        """After rotation, the API key should still be retrievable (masked)."""
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "RotateTest",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-rotationtest5678",
            },
        )
        provider_id = create_resp.json()["id"]

        # Rotate
        resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        # Verify the key is still accessible (masked correctly)
        resp = await client.get(f"/api/providers/{provider_id}")
        assert resp.status_code == 200
        assert resp.json()["api_key"] == "***...5678"

    async def test_rotate_empty_table(self, client: AsyncClient) -> None:
        """Rotation with no providers should succeed as a no-op."""
        resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_rotate_multiple_providers(self, client: AsyncClient) -> None:
        """Rotation should re-encrypt all provider API keys."""
        ids = []
        for i, suffix in enumerate(["aaaa", "bbbb", "cccc"]):
            create_resp = await client.post(
                "/api/providers",
                json={
                    "name": f"Provider{i}",
                    "type": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": f"sk-multirotate{suffix}",
                },
            )
            ids.append(create_resp.json()["id"])

        resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200

        for pid, suffix in zip(ids, ["aaaa", "bbbb", "cccc"]):
            resp = await client.get(f"/api/providers/{pid}")
            assert resp.status_code == 200
            assert resp.json()["api_key"] == f"***...{suffix}"

    async def test_rotate_preserves_key_on_db_failure(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Verify a DB commit failure leaves the rotation half-undone safely.

        After the simulated failure the on-disk key file, the cached encryptor,
        and the on-disk ciphertext must all be byte-identical to their
        pre-rotation state.
        """
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "FailureTest",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-failuretest9999",
            },
        )
        assert create_resp.status_code in (200, 201)
        provider_id = create_resp.json()["id"]

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()

        # The fixture's ASGITransport uses raise_app_exceptions=True (the
        # httpx default), so the simulated commit failure propagates out of
        # client.post as a RuntimeError. In production the exception would
        # surface as a 500 from FastAPI's default exception handler — the
        # invariants we care about (no key file write, no cached encryptor
        # mutation, on-disk ciphertext untouched) are the same in both paths.
        with (
            patch(
                "aiosqlite.Connection.commit",
                side_effect=RuntimeError("simulated DB failure"),
            ),
            pytest.raises(RuntimeError, match="simulated DB failure"),
        ):
            await client.post("/api/encryption/rotate")

        # (i) Key file byte-identical to its pre-rotation contents.
        assert key_path.read_bytes() == key_before

        # (ii) Masked tail still works (exercises the cached encryptor's
        # decrypt path — would fail if the cached _fernet was mutated).
        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["api_key"] == "***...9999"

        # (iii) Direct decrypt with the pre-rotation key bytes succeeds —
        # this catches a regression where on-disk ciphertext was rewritten
        # before the commit failed. Open a fresh connection because the
        # fixture closes its conn after yield.
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?", (provider_id,)
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None
        assert Fernet(key_before).decrypt(row["api_key"].encode()).decode() == "sk-failuretest9999"


# ── Provider helper ────────────────────────────────────────────────────


PROVIDER_FIXTURES = {
    "ollama": {
        "name": "Local Ollama",
        "type": "ollama",
        "base_url": "http://localhost:11434/v1",
    },
    "openai-compatible": {
        "name": "LM Studio",
        "type": "openai-compatible",
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio-key-1234",
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-openai-test-1234",
    },
    "anthropic": {
        "name": "Anthropic",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-ant-test-key-1234",
    },
}


async def _create_provider(client: AsyncClient, provider_type: str) -> str:
    """Create a provider of the given type and return its id."""
    resp = await client.post("/api/providers", json=PROVIDER_FIXTURES[provider_type])
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Connection test endpoint ───────────────────────────────────────────


class TestConnectionTest:
    """Tests for POST /api/providers/{id}/test."""

    async def test_ollama_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "Ollama" in data["detail"]

    async def test_ollama_failure(self, client: AsyncClient) -> None:
        import httpx as _httpx

        pid = await _create_provider(client, "ollama")
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=_httpx.ConnectError("refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "refused" in data["detail"]

    async def test_openai_compatible_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai-compatible")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_openai_compatible_failure(self, client: AsyncClient) -> None:
        import httpx as _httpx

        pid = await _create_provider(client, "openai-compatible")
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=_httpx.ConnectError("timeout"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_openai_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        mock_mod = _mock_openai_module()
        mock_mod.AsyncOpenAI.return_value.models.list = AsyncMock(return_value=MagicMock(data=[]))
        with patch.dict(sys.modules, {"openai": mock_mod}):
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "OpenAI" in resp.json()["detail"]

    async def test_openai_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        mock_mod = _mock_openai_module()
        mock_mod.AsyncOpenAI.return_value.models.list = AsyncMock(
            side_effect=mock_mod.OpenAIError("invalid api key")
        )
        with patch.dict(sys.modules, {"openai": mock_mod}):
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
        assert "invalid api key" in resp.json()["detail"]

    async def test_anthropic_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "anthropic")
        mock_mod = _mock_anthropic_module()
        mock_mod.AsyncAnthropic.return_value.models.list = AsyncMock(
            return_value=MagicMock(data=[])
        )
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "Anthropic" in resp.json()["detail"]

    async def test_anthropic_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "anthropic")
        mock_mod = _mock_anthropic_module()
        mock_mod.AsyncAnthropic.return_value.models.list = AsyncMock(
            side_effect=mock_mod.AnthropicError("auth failed")
        )
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
        assert "auth failed" in resp.json()["detail"]

    async def test_not_found(self, client: AsyncClient) -> None:
        resp = await client.post("/api/providers/nonexistent/test")
        assert resp.status_code == 404


# ── Model discovery endpoint ──────────────────────────────────────────


class TestModelDiscovery:
    """Tests for GET /api/providers/{id}/models."""

    async def test_ollama_models(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "models": [
                {"name": "qwen2.5:7b", "size": 4_500_000_000},
                {"name": "llama3:8b", "size": 5_000_000_000},
            ]
        }
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["id"] == "qwen2.5:7b"
        assert models[0]["name"] == "qwen2.5:7b"
        assert models[0]["size"] == 4_500_000_000

    async def test_ollama_models_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=ConnectionError("refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 502
        assert "refused" in resp.json()["detail"]

    async def test_openai_compatible_models(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai-compatible")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"id": "model-alpha"},
                {"id": "model-beta"},
            ]
        }
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["id"] == "model-alpha"
        assert models[1]["name"] == "model-beta"

    async def test_openai_compatible_models_failure(self, client: AsyncClient) -> None:
        """openai-compatible model discovery now raises HTTPException(502) on failure."""
        pid = await _create_provider(client, "openai-compatible")
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=ConnectionError("connection refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 502
        assert "connection refused" in resp.json()["detail"]

    async def test_openai_models(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        model_a = SimpleNamespace(id="gpt-4o")
        model_b = SimpleNamespace(id="gpt-4o-mini")
        mock_mod = _mock_openai_module()
        mock_mod.AsyncOpenAI.return_value.models.list = AsyncMock(
            return_value=MagicMock(data=[model_a, model_b])
        )
        with patch.dict(sys.modules, {"openai": mock_mod}):
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["id"] == "gpt-4o"
        assert models[1]["name"] == "gpt-4o-mini"

    async def test_openai_models_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        mock_mod = _mock_openai_module()
        mock_mod.AsyncOpenAI.return_value.models.list = AsyncMock(
            side_effect=Exception("rate limited")
        )
        with patch.dict(sys.modules, {"openai": mock_mod}):
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 502
        assert "rate limited" in resp.json()["detail"]

    async def test_anthropic_models(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "anthropic")
        model_a = SimpleNamespace(id="claude-sonnet-4-20250514", display_name="Claude Sonnet 4")
        model_b = SimpleNamespace(id="claude-haiku-4-20250514", display_name="Claude Haiku 4")
        mock_mod = _mock_anthropic_module()
        mock_mod.AsyncAnthropic.return_value.models.list = AsyncMock(
            return_value=MagicMock(data=[model_a, model_b])
        )
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["id"] == "claude-sonnet-4-20250514"
        assert models[0]["name"] == "Claude Sonnet 4"
        assert models[1]["name"] == "Claude Haiku 4"

    async def test_anthropic_models_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "anthropic")
        mock_mod = _mock_anthropic_module()
        mock_mod.AsyncAnthropic.return_value.models.list = AsyncMock(
            side_effect=Exception("auth error")
        )
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 502
        assert "auth error" in resp.json()["detail"]

    async def test_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/providers/nonexistent/models")
        assert resp.status_code == 404

    async def test_ollama_models_via_ollama_api(self, client: AsyncClient) -> None:
        """Verify the ollama branch now delegates to ollama_api.list_models."""
        pid = await _create_provider(client, "ollama")
        mock_models = [
            {"name": "qwen2.5:7b", "size": 4_500_000_000},
            {"name": "llama3:8b", "size": 5_000_000_000},
        ]
        with patch(
            "the_one.interfaces.web.api.ollama_api.list_models",
            new_callable=AsyncMock,
            return_value=mock_models,
        ):
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["id"] == "qwen2.5:7b"
        assert models[0]["size"] == 4_500_000_000

    async def test_ollama_models_via_ollama_api_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch(
            "the_one.interfaces.web.api.ollama_api.list_models",
            new_callable=AsyncMock,
            side_effect=ConnectionError("cannot connect"),
        ):
            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 502
        assert "cannot connect" in resp.json()["detail"]


# ── Ollama Model Lifecycle endpoints ──────────────────────────────────


class TestPullModel:
    """Tests for POST /api/providers/{id}/models/pull."""

    async def test_pull_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")

        async def _fake_pull(*_args, **_kwargs):
            yield {"status": "downloading", "completed": 50, "total": 100}
            yield {"status": "success"}

        with patch(
            "the_one.interfaces.web.api.ollama_api.pull_model",
            side_effect=_fake_pull,
        ):
            resp = await client.post(
                f"/api/providers/{pid}/models/pull", json={"model": "llama3:8b"}
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = [ln for ln in resp.text.split("\n") if ln.startswith("data: ")]
        assert len(lines) == 2
        import json as _json

        first = _json.loads(lines[0].removeprefix("data: "))
        assert first["status"] == "downloading"
        second = _json.loads(lines[1].removeprefix("data: "))
        assert second["status"] == "success"

    async def test_pull_upstream_error_mid_stream(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")

        async def _failing_pull(*_args, **_kwargs):
            yield {"status": "downloading", "completed": 10, "total": 100}
            raise ConnectionError("connection lost")

        with patch(
            "the_one.interfaces.web.api.ollama_api.pull_model",
            side_effect=_failing_pull,
        ):
            resp = await client.post(
                f"/api/providers/{pid}/models/pull", json={"model": "llama3:8b"}
            )
        assert resp.status_code == 200
        lines = [ln for ln in resp.text.split("\n") if ln.startswith("data: ")]
        assert len(lines) == 2
        import json as _json

        last = _json.loads(lines[-1].removeprefix("data: "))
        assert "error" in last

    async def test_pull_not_found(self, client: AsyncClient) -> None:
        resp = await client.post("/api/providers/nonexistent/models/pull", json={"model": "x"})
        assert resp.status_code == 404

    async def test_pull_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        resp = await client.post(f"/api/providers/{pid}/models/pull", json={"model": "x"})
        assert resp.status_code == 400
        assert "not 'ollama'" in resp.json()["detail"]

    async def test_pull_empty_model(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        resp = await client.post(f"/api/providers/{pid}/models/pull", json={"model": ""})
        assert resp.status_code == 400
        assert "Missing or empty" in resp.json()["detail"]


class TestDeleteModel:
    """Tests for POST /api/providers/{id}/models/delete."""

    async def test_delete_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch(
            "the_one.interfaces.web.api.ollama_api.delete_model",
            new_callable=AsyncMock,
        ):
            resp = await client.post(
                f"/api/providers/{pid}/models/delete", json={"model": "llama3:8b"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_delete_not_found(self, client: AsyncClient) -> None:
        resp = await client.post("/api/providers/nonexistent/models/delete", json={"model": "x"})
        assert resp.status_code == 404

    async def test_delete_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        resp = await client.post(f"/api/providers/{pid}/models/delete", json={"model": "x"})
        assert resp.status_code == 400

    async def test_delete_upstream_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch(
            "the_one.interfaces.web.api.ollama_api.delete_model",
            new_callable=AsyncMock,
            side_effect=ConnectionError("refused"),
        ):
            resp = await client.post(
                f"/api/providers/{pid}/models/delete", json={"model": "llama3:8b"}
            )
        assert resp.status_code == 502
        assert "refused" in resp.json()["detail"]

    async def test_delete_empty_model(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        resp = await client.post(f"/api/providers/{pid}/models/delete", json={"model": "  "})
        assert resp.status_code == 400


class TestLoadModel:
    """Tests for POST /api/providers/{id}/models/load."""

    async def test_load_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch(
            "the_one.interfaces.web.api.ollama_api.load_model",
            new_callable=AsyncMock,
        ):
            resp = await client.post(
                f"/api/providers/{pid}/models/load", json={"model": "llama3:8b"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_load_not_found(self, client: AsyncClient) -> None:
        resp = await client.post("/api/providers/nonexistent/models/load", json={"model": "x"})
        assert resp.status_code == 404

    async def test_load_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "anthropic")
        resp = await client.post(f"/api/providers/{pid}/models/load", json={"model": "x"})
        assert resp.status_code == 400

    async def test_load_upstream_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch(
            "the_one.interfaces.web.api.ollama_api.load_model",
            new_callable=AsyncMock,
            side_effect=ConnectionError("timeout"),
        ):
            resp = await client.post(
                f"/api/providers/{pid}/models/load", json={"model": "llama3:8b"}
            )
        assert resp.status_code == 502
        assert "timeout" in resp.json()["detail"]

    async def test_load_empty_model(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        resp = await client.post(f"/api/providers/{pid}/models/load", json={"model": ""})
        assert resp.status_code == 400


class TestUnloadModel:
    """Tests for POST /api/providers/{id}/models/unload."""

    async def test_unload_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch(
            "the_one.interfaces.web.api.ollama_api.unload_model",
            new_callable=AsyncMock,
        ):
            resp = await client.post(
                f"/api/providers/{pid}/models/unload", json={"model": "llama3:8b"}
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_unload_not_found(self, client: AsyncClient) -> None:
        resp = await client.post("/api/providers/nonexistent/models/unload", json={"model": "x"})
        assert resp.status_code == 404

    async def test_unload_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai-compatible")
        resp = await client.post(f"/api/providers/{pid}/models/unload", json={"model": "x"})
        assert resp.status_code == 400

    async def test_unload_upstream_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch(
            "the_one.interfaces.web.api.ollama_api.unload_model",
            new_callable=AsyncMock,
            side_effect=ConnectionError("refused"),
        ):
            resp = await client.post(
                f"/api/providers/{pid}/models/unload", json={"model": "llama3:8b"}
            )
        assert resp.status_code == 502
        assert "refused" in resp.json()["detail"]

    async def test_unload_empty_model(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        resp = await client.post(f"/api/providers/{pid}/models/unload", json={"model": ""})
        assert resp.status_code == 400


class TestModelStatus:
    """Tests for GET /api/providers/{id}/models/status."""

    async def test_status_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        mock_running = [
            {"name": "llama3:8b", "size": 5_000_000_000, "vram": 4_800_000_000},
        ]
        with patch(
            "the_one.interfaces.web.api.ollama_api.list_running",
            new_callable=AsyncMock,
            return_value=mock_running,
        ):
            resp = await client.get(f"/api/providers/{pid}/models/status")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "llama3:8b"

    async def test_status_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/providers/nonexistent/models/status")
        assert resp.status_code == 404

    async def test_status_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        resp = await client.get(f"/api/providers/{pid}/models/status")
        assert resp.status_code == 400

    async def test_status_upstream_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        with patch(
            "the_one.interfaces.web.api.ollama_api.list_running",
            new_callable=AsyncMock,
            side_effect=ConnectionError("refused"),
        ):
            resp = await client.get(f"/api/providers/{pid}/models/status")
        assert resp.status_code == 502
        assert "refused" in resp.json()["detail"]


# ── URL normalization utilities ───────────────────────────────────────


# ── Provider Deletion Protection ──────────────────────────────────────


class TestProviderDeletionProtection:
    """Tests for provider deletion protection and agents-by-provider endpoint."""

    async def _create_agent(self, client: AsyncClient, name: str, provider_id: str) -> None:
        resp = await client.post(
            "/api/agents",
            json={
                "name": name,
                "provider_config_id": provider_id,
                "llm_model": "test-model",
            },
        )
        assert resp.status_code == 201

    async def test_delete_blocked_by_agents(self, client: AsyncClient) -> None:
        """DELETE should return 409 when agents reference the provider."""
        pid = await _create_provider(client, "ollama")
        await self._create_agent(client, "agent-a", pid)

        resp = await client.delete(f"/api/providers/{pid}")
        assert resp.status_code == 409
        data = resp.json()
        assert "agent-a" in data["detail"]
        assert "Provider is used by agents" in data["detail"]

    async def test_delete_allowed_without_agents(self, client: AsyncClient) -> None:
        """DELETE should succeed (200) when no agents reference the provider."""
        pid = await _create_provider(client, "ollama")

        resp = await client.delete(f"/api/providers/{pid}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        # Verify it's actually gone
        resp = await client.get(f"/api/providers/{pid}")
        assert resp.status_code == 404

    async def test_agents_by_provider(self, client: AsyncClient) -> None:
        """GET /api/providers/{id}/agents should return agent names referencing the provider."""
        pid = await _create_provider(client, "ollama")
        await self._create_agent(client, "bot-alpha", pid)
        await self._create_agent(client, "bot-beta", pid)

        resp = await client.get(f"/api/providers/{pid}/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert sorted(data["agents"]) == ["bot-alpha", "bot-beta"]

    async def test_agents_by_provider_empty(self, client: AsyncClient) -> None:
        """GET /api/providers/{id}/agents should return empty list when no agents reference it."""
        pid = await _create_provider(client, "ollama")

        resp = await client.get(f"/api/providers/{pid}/agents")
        assert resp.status_code == 200
        assert resp.json() == {"agents": []}

    async def test_agents_by_provider_not_found(self, client: AsyncClient) -> None:
        """GET /api/providers/{id}/agents should return 404 for non-existent provider."""
        resp = await client.get("/api/providers/nonexistent/agents")
        assert resp.status_code == 404


# ── Ollama Library Search ─────────────────────────────────────────────


class TestOllamaLibrarySearch:
    """Tests for GET /api/ollama-library/search."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        """Reset the library cache before each test."""
        from the_one.interfaces.web import api as _api_mod

        _api_mod._library_cache["models"] = []
        _api_mod._library_cache["timestamp"] = 0.0
        yield
        _api_mod._library_cache["models"] = []
        _api_mod._library_cache["timestamp"] = 0.0

    def _mock_httpx(self, models: list[dict] | Exception):
        """Return a patch context that mocks httpx.AsyncClient for library fetch."""
        mock_resp = MagicMock()
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)

        if isinstance(models, Exception):
            instance.get = AsyncMock(side_effect=models)
        else:
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"models": models}
            instance.get = AsyncMock(return_value=mock_resp)

        return patch(
            "the_one.interfaces.web.api.httpx.AsyncClient",
            return_value=instance,
        )

    async def test_basic_search(self, client: AsyncClient) -> None:
        models = [
            {"name": "llama3:8b", "size": 5_000_000_000},
            {"name": "llama3:70b", "size": 40_000_000_000},
            {"name": "qwen2.5:7b", "size": 4_500_000_000},
        ]
        with self._mock_httpx(models):
            resp = await client.get("/api/ollama-library/search?q=llama")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "llama3:8b"
        assert data[1]["name"] == "llama3:70b"

    async def test_empty_query(self, client: AsyncClient) -> None:
        resp = await client.get("/api/ollama-library/search?q=")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_short_query(self, client: AsyncClient) -> None:
        resp = await client.get("/api/ollama-library/search?q=a")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_results_capped_at_30(self, client: AsyncClient) -> None:
        models = [{"name": f"model-x-{i}", "size": 100} for i in range(50)]
        with self._mock_httpx(models):
            resp = await client.get("/api/ollama-library/search?q=model-x")
        assert resp.status_code == 200
        assert len(resp.json()) == 30

    async def test_cache_hit(self, client: AsyncClient) -> None:
        models = [
            {"name": "llama3:8b", "size": 5_000_000_000},
            {"name": "qwen2.5:7b", "size": 4_500_000_000},
        ]
        mock_ctx = self._mock_httpx(models)
        with mock_ctx as mock_cls:
            resp1 = await client.get("/api/ollama-library/search?q=llama")
            resp2 = await client.get("/api/ollama-library/search?q=qwen")
            # httpx.AsyncClient should have been instantiated only once (first call)
            assert mock_cls.call_count == 1
        assert len(resp1.json()) == 1
        assert resp1.json()[0]["name"] == "llama3:8b"
        assert len(resp2.json()) == 1
        assert resp2.json()[0]["name"] == "qwen2.5:7b"

    async def test_http_error_no_cache(self, client: AsyncClient) -> None:
        """HTTP error with no cached data returns empty list."""
        with self._mock_httpx(ConnectionError("refused")):
            resp = await client.get("/api/ollama-library/search?q=llama")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_http_error_stale_cache_fallback(self, client: AsyncClient) -> None:
        """HTTP error with stale cache falls back to cached data."""
        from the_one.interfaces.web import api as _api_mod

        models = [
            {"name": "llama3:8b", "size": 5_000_000_000},
        ]
        # Pre-populate cache, then expire it
        with self._mock_httpx(models):
            await client.get("/api/ollama-library/search?q=llama")

        # Expire the cache
        _api_mod._library_cache["timestamp"] = 0.0

        # Now fetch fails — should fall back to stale cache
        with self._mock_httpx(ConnectionError("timeout")):
            resp = await client.get("/api/ollama-library/search?q=llama")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "llama3:8b"


class TestStripV1:
    """Tests for ollama_api.strip_v1()."""

    def test_strips_v1_suffix(self) -> None:
        from the_one.llm.ollama_api import strip_v1

        assert strip_v1("http://localhost:11434/v1") == "http://localhost:11434"

    def test_strips_v1_slash_suffix(self) -> None:
        from the_one.llm.ollama_api import strip_v1

        assert strip_v1("http://localhost:11434/v1/") == "http://localhost:11434"

    def test_bare_url_unchanged(self) -> None:
        from the_one.llm.ollama_api import strip_v1

        assert strip_v1("http://localhost:11434") == "http://localhost:11434"

    def test_strips_trailing_slash(self) -> None:
        from the_one.llm.ollama_api import strip_v1

        assert strip_v1("http://localhost:11434/") == "http://localhost:11434"

    def test_already_correct(self) -> None:
        from the_one.llm.ollama_api import strip_v1

        assert strip_v1("http://myhost:8080") == "http://myhost:8080"


class TestEnsureV1:
    """Tests for ollama_api.ensure_v1()."""

    def test_adds_v1_suffix(self) -> None:
        from the_one.llm.ollama_api import ensure_v1

        assert ensure_v1("http://localhost:11434") == "http://localhost:11434/v1"

    def test_already_has_v1(self) -> None:
        from the_one.llm.ollama_api import ensure_v1

        assert ensure_v1("http://localhost:11434/v1") == "http://localhost:11434/v1"

    def test_trailing_slash_gets_v1(self) -> None:
        from the_one.llm.ollama_api import ensure_v1

        assert ensure_v1("http://localhost:11434/") == "http://localhost:11434/v1"

    def test_v1_with_trailing_slash(self) -> None:
        from the_one.llm.ollama_api import ensure_v1

        assert ensure_v1("http://localhost:11434/v1/") == "http://localhost:11434/v1"
