"""Tests for LLM provider REST API endpoints."""

from __future__ import annotations

import sys
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


def _mock_openai_module() -> MagicMock:
    """Create a mock ``openai`` module with AsyncOpenAI."""
    mod = MagicMock()
    mock_client = AsyncMock()
    mod.AsyncOpenAI.return_value = mock_client
    return mod


def _mock_anthropic_module() -> MagicMock:
    """Create a mock ``anthropic`` module with AsyncAnthropic."""
    mod = MagicMock()
    mock_client = AsyncMock()
    mod.AsyncAnthropic.return_value = mock_client
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
        pid = await _create_provider(client, "ollama")
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=ConnectionError("refused"))
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
        pid = await _create_provider(client, "openai-compatible")
        with patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=ConnectionError("timeout"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_client.return_value = instance
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_openai_success(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        mock_mod = _mock_openai_module()
        mock_mod.AsyncOpenAI.return_value.models.list = AsyncMock(
            return_value=MagicMock(data=[])
        )
        with patch.dict(sys.modules, {"openai": mock_mod}):
            resp = await client.post(f"/api/providers/{pid}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "OpenAI" in resp.json()["detail"]

    async def test_openai_failure(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        mock_mod = _mock_openai_module()
        mock_mod.AsyncOpenAI.return_value.models.list = AsyncMock(
            side_effect=Exception("invalid api key")
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
            side_effect=Exception("auth failed")
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
        resp = await client.post(
            "/api/providers/nonexistent/models/pull", json={"model": "x"}
        )
        assert resp.status_code == 404

    async def test_pull_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        resp = await client.post(
            f"/api/providers/{pid}/models/pull", json={"model": "x"}
        )
        assert resp.status_code == 400
        assert "not 'ollama'" in resp.json()["detail"]

    async def test_pull_empty_model(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "ollama")
        resp = await client.post(
            f"/api/providers/{pid}/models/pull", json={"model": ""}
        )
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
        resp = await client.post(
            "/api/providers/nonexistent/models/delete", json={"model": "x"}
        )
        assert resp.status_code == 404

    async def test_delete_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai")
        resp = await client.post(
            f"/api/providers/{pid}/models/delete", json={"model": "x"}
        )
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
        resp = await client.post(
            f"/api/providers/{pid}/models/delete", json={"model": "  "}
        )
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
        resp = await client.post(
            "/api/providers/nonexistent/models/load", json={"model": "x"}
        )
        assert resp.status_code == 404

    async def test_load_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "anthropic")
        resp = await client.post(
            f"/api/providers/{pid}/models/load", json={"model": "x"}
        )
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
        resp = await client.post(
            f"/api/providers/{pid}/models/load", json={"model": ""}
        )
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
        resp = await client.post(
            "/api/providers/nonexistent/models/unload", json={"model": "x"}
        )
        assert resp.status_code == 404

    async def test_unload_wrong_type(self, client: AsyncClient) -> None:
        pid = await _create_provider(client, "openai-compatible")
        resp = await client.post(
            f"/api/providers/{pid}/models/unload", json={"model": "x"}
        )
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
        resp = await client.post(
            f"/api/providers/{pid}/models/unload", json={"model": ""}
        )
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
