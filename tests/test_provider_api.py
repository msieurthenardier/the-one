"""Tests for LLM provider REST API endpoints."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router


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

        transport = ASGITransport(app=test_app, raise_app_exceptions=False)
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
        """PUT with a masked API key (***...) should preserve the original stored key."""
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

        # Update with masked key — original should be preserved
        resp = await client.put(
            f"/api/providers/{provider_id}",
            json={
                "name": "Updated",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "***...9999",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
        # The masked key in response should still match original
        assert resp.json()["api_key"] == "***...9999"

        # Verify the actual stored key is still the original (not the mask string)
        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.json()["api_key"] == "***...9999"

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


# ── Connection Test ────────────────────────────────────────────────────


class TestConnectionTest:
    """Tests for POST /api/providers/{id}/test with mocked HTTP calls."""

    async def _create_provider(self, client, **kwargs):
        resp = await client.post("/api/providers", json=kwargs)
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_ollama_success(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="Ollama", type="ollama", base_url="http://localhost:11434/v1"
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_ollama_failure(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="Ollama", type="ollama", base_url="http://localhost:11434/v1"
        )
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_openai_compatible_success(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="OAC", type="openai-compatible",
            base_url="http://localhost:8080/v1", api_key="sk-test12345678"
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_openai_compatible_failure(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="OAC", type="openai-compatible",
            base_url="http://localhost:8080/v1"
        )
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_openai_success(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="OpenAI", type="openai",
            base_url="https://api.openai.com/v1", api_key="sk-test12345678"
        )
        mock_models = MagicMock()
        mock_models.list = AsyncMock(return_value=MagicMock(data=[]))

        mock_openai = MagicMock()
        with patch.dict(sys.modules, {"openai": mock_openai}):
            mock_client = MagicMock()
            mock_client.models = mock_models
            mock_openai.AsyncOpenAI.return_value = mock_client

            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_openai_failure(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="OpenAI", type="openai",
            base_url="https://api.openai.com/v1", api_key="sk-bad12345678"
        )
        mock_openai = MagicMock()
        with patch.dict(sys.modules, {"openai": mock_openai}):
            mock_models = MagicMock()
            mock_models.list = AsyncMock(side_effect=Exception("auth failed"))
            mock_client = MagicMock()
            mock_client.models = mock_models
            mock_openai.AsyncOpenAI.return_value = mock_client

            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_anthropic_success(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="Anthropic", type="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-ant-12345678"
        )
        mock_models = MagicMock()
        mock_models.list = AsyncMock(return_value=MagicMock(data=[]))

        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            mock_client = MagicMock()
            mock_client.models = mock_models
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_anthropic_failure(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="Anthropic", type="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-ant-bad12345"
        )
        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            mock_models = MagicMock()
            mock_models.list = AsyncMock(side_effect=Exception("auth failed"))
            mock_client = MagicMock()
            mock_client.models = mock_models
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_not_found(self, client: AsyncClient) -> None:
        resp = await client.post("/api/providers/nonexistent/test")
        assert resp.status_code == 404


# ── Model Discovery ──────────────────────────────────────────────────


class TestModelDiscovery:
    """Tests for GET /api/providers/{id}/models with mocked HTTP calls."""

    async def _create_provider(self, client, **kwargs):
        resp = await client.post("/api/providers", json=kwargs)
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_ollama_models(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="Ollama", type="ollama", base_url="http://localhost:11434/v1"
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "models": [
                {"name": "qwen2.5:7b", "size": 4_000_000_000},
                {"name": "llama3:8b", "size": 5_000_000_000},
            ]
        }

        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["name"] == "qwen2.5:7b"
        assert models[1]["name"] == "llama3:8b"

    async def test_ollama_models_failure(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="Ollama", type="ollama", base_url="http://localhost:11434/v1"
        )
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/providers/{pid}/models")
        # Ollama model listing doesn't catch exceptions — should get 500
        assert resp.status_code == 500

    async def test_openai_compatible_models(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="OAC", type="openai-compatible",
            base_url="http://localhost:8080/v1"
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"id": "gpt-3.5-turbo"},
                {"id": "gpt-4"},
            ]
        }

        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["id"] == "gpt-3.5-turbo"

    async def test_openai_compatible_models_failure(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="OAC", type="openai-compatible",
            base_url="http://localhost:8080/v1"
        )
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/providers/{pid}/models")
        # openai-compatible now raises HTTPException(502) instead of returning []
        assert resp.status_code == 502

    async def test_openai_models(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="OpenAI", type="openai",
            base_url="https://api.openai.com/v1", api_key="sk-test12345678"
        )
        model1 = MagicMock()
        model1.id = "gpt-4o"
        model2 = MagicMock()
        model2.id = "gpt-4o-mini"
        mock_response = MagicMock(data=[model1, model2])

        mock_openai = MagicMock()
        with patch.dict(sys.modules, {"openai": mock_openai}):
            mock_client = MagicMock()
            mock_client.models = MagicMock()
            mock_client.models.list = AsyncMock(return_value=mock_response)
            mock_openai.AsyncOpenAI.return_value = mock_client

            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["id"] == "gpt-4o"

    async def test_openai_models_failure(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="OpenAI", type="openai",
            base_url="https://api.openai.com/v1", api_key="sk-bad12345678"
        )
        mock_openai = MagicMock()
        with patch.dict(sys.modules, {"openai": mock_openai}):
            mock_client = MagicMock()
            mock_client.models = MagicMock()
            mock_client.models.list = AsyncMock(side_effect=Exception("auth failed"))
            mock_openai.AsyncOpenAI.return_value = mock_client

            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 500

    async def test_anthropic_models(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="Anthropic", type="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-ant-12345678"
        )
        model1 = MagicMock()
        model1.id = "claude-sonnet-4-20250514"
        model1.display_name = "Claude Sonnet 4"
        model2 = MagicMock()
        model2.id = "claude-3-haiku-20240307"
        model2.display_name = "Claude 3 Haiku"
        mock_response = MagicMock(data=[model1, model2])

        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            mock_client = MagicMock()
            mock_client.models = MagicMock()
            mock_client.models.list = AsyncMock(return_value=mock_response)
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 2
        assert models[0]["id"] == "claude-sonnet-4-20250514"
        assert models[0]["name"] == "Claude Sonnet 4"

    async def test_anthropic_models_failure(self, client: AsyncClient) -> None:
        pid = await self._create_provider(
            client, name="Anthropic", type="anthropic",
            base_url="https://api.anthropic.com", api_key="sk-ant-bad12345"
        )
        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            mock_client = MagicMock()
            mock_client.models = MagicMock()
            mock_client.models.list = AsyncMock(side_effect=Exception("auth failed"))
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            resp = await client.get(f"/api/providers/{pid}/models")
        assert resp.status_code == 500

    async def test_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/providers/nonexistent/models")
        assert resp.status_code == 404


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
