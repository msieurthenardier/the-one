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


# ── Provider URL safety validation ─────────────────────────────────────


class TestProviderUrlValidation:
    """Tests for ``_is_safe_provider_url`` enforcement on the three save paths.

    Contract:
      - ``https://`` always passes.
      - ``http://`` passes iff host is ``localhost``/``127.0.0.1``/``::1``
        or ends in ``.localdomain``.
      - ``mock`` and ``ollama`` types skip validation.
      - Failures return 422 (refusal, not warning — pinned contract).
      - Update path validates the RESOLVED ``base_url`` so an unchanged
        ``http://example.com`` cannot survive a touched-elsewhere update
        that uses ``__MASKED__`` to preserve the api_key.
    """

    async def test_create_openai_compatible_http_non_localhost_rejected(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/providers",
            json={
                "name": "Risky",
                "type": "openai-compatible",
                "base_url": "http://example.com:5000",
                "api_key": "sk-leak-bait",
            },
        )
        assert resp.status_code == 422
        assert "cleartext" in resp.json()["detail"].lower()

    async def test_create_ollama_localhost_passes(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/providers",
            json={
                "name": "OllamaOK",
                "type": "ollama",
                "base_url": "http://localhost:11434",
            },
        )
        assert resp.status_code == 201

    async def test_create_ollama_non_localhost_passes(self, client: AsyncClient) -> None:
        """Ollama skips validation entirely; non-localhost http is allowed."""
        resp = await client.post(
            "/api/providers",
            json={
                "name": "OllamaRemote",
                "type": "ollama",
                "base_url": "http://host.docker.internal:11434",
            },
        )
        assert resp.status_code == 201

    async def test_create_openai_compatible_localhost_passes(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/providers",
            json={
                "name": "LMStudio",
                "type": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key": "lm-studio-key",
            },
        )
        assert resp.status_code == 201

    async def test_create_openai_https_passes(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/providers",
            json={
                "name": "OpenAI",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test1234",
            },
        )
        assert resp.status_code == 201

    async def test_update_to_unsafe_url_rejected(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "Safe",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-key1234",
            },
        )
        pid = create_resp.json()["id"]
        resp = await client.put(
            f"/api/providers/{pid}",
            json={
                "name": "Safe",
                "type": "openai",
                "base_url": "http://example.com:5000",
                "api_key": "__MASKED__",
            },
        )
        assert resp.status_code == 422

    async def test_update_with_masked_key_validates_resolved_base_url(
        self, client: AsyncClient
    ) -> None:
        """A pre-existing http://example.com survives validation only because
        ``create_provider`` would have rejected it. We force-insert one via the
        repository to simulate legacy data, then verify ``update_provider`` —
        even one that only renames the provider and sends ``__MASKED__`` for
        api_key — refuses on the resolved (post-merge) base_url.

        Uses the API module's already-patched ``get_connection`` /
        ``get_encryptor`` references so the legacy row lands in the
        fixture's isolated DB rather than the operator's real one.
        """
        from the_one.db.models import LLMProviderConfig
        from the_one.db.repositories import LLMProviderRepository
        from the_one.interfaces.web import api as api_mod

        conn = await api_mod.get_connection()
        encryptor = api_mod.get_encryptor(api_mod.settings.data_dir)
        repo = LLMProviderRepository(conn, encryptor)
        legacy = LLMProviderConfig(
            id="legacy-leak",
            name="Legacy",
            type="openai-compatible",
            base_url="http://example.com:5000",
            api_key="sk-legacy",
        )
        await repo.create(legacy)

        # Now: an update that only renames + preserves the masked api_key
        # MUST still 422 because the resolved base_url is the unchanged
        # legacy http://example.com:5000.
        resp = await client.put(
            f"/api/providers/{legacy.id}",
            json={
                "name": "Renamed",
                "type": "openai-compatible",
                "base_url": "http://example.com:5000",
                "api_key": "__MASKED__",
            },
        )
        assert resp.status_code == 422

    async def test_test_provider_against_legacy_unsafe_stored_url_rejected(
        self, client: AsyncClient
    ) -> None:
        """``test_provider`` is the belt-and-suspenders gate for legacy data."""
        from the_one.db.models import LLMProviderConfig
        from the_one.db.repositories import LLMProviderRepository
        from the_one.interfaces.web import api as api_mod

        conn = await api_mod.get_connection()
        encryptor = api_mod.get_encryptor(api_mod.settings.data_dir)
        repo = LLMProviderRepository(conn, encryptor)
        legacy = LLMProviderConfig(
            id="legacy-test",
            name="LegacyTest",
            type="openai-compatible",
            base_url="http://example.com:5000",
            api_key="sk-legacy-test",
        )
        await repo.create(legacy)

        resp = await client.post(f"/api/providers/{legacy.id}/test")
        assert resp.status_code == 422
        assert "cleartext" in resp.json()["detail"].lower()

    async def test_is_safe_provider_url_helper_unit(self) -> None:
        """Direct unit coverage for the helper itself."""
        from the_one.interfaces.web.api import _is_safe_provider_url

        # https always passes
        ok, msg = _is_safe_provider_url("https://api.openai.com/v1")
        assert ok and msg is None

        # http localhost variants pass
        for url in (
            "http://localhost:8080",
            "http://127.0.0.1:5000",
            "http://[::1]:9999",
            "http://box.localdomain:1234",
        ):
            ok, msg = _is_safe_provider_url(url)
            assert ok, f"expected pass for {url!r}, got {msg}"

        # http non-localhost fails
        ok, msg = _is_safe_provider_url("http://example.com:5000")
        assert not ok
        assert msg and "cleartext" in msg.lower()

        # unsupported scheme fails
        ok, msg = _is_safe_provider_url("ftp://example.com")
        assert not ok
        assert msg and "ftp" in msg.lower()


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
        # Filtered by substring "llama" then sorted alphabetically — `:7` <
        # `:8` so the 70b variant sorts before 8b.
        assert [m["name"] for m in data] == ["llama3:70b", "llama3:8b"]

    async def test_empty_query_returns_full_library(self, client: AsyncClient) -> None:
        # Empty q lists the full library (used to populate the Pull Model
        # dropdown). Result is alphabetically sorted.
        models = [
            {"name": "qwen2.5:7b", "size": 4_500_000_000},
            {"name": "llama3:8b", "size": 5_000_000_000},
        ]
        with self._mock_httpx(models):
            resp = await client.get("/api/ollama-library/search?q=")
        assert resp.status_code == 200
        assert [m["name"] for m in resp.json()] == ["llama3:8b", "qwen2.5:7b"]

    async def test_short_query_still_filters(self, client: AsyncClient) -> None:
        # The legacy `len(q) < 2` short-circuit was removed when the dropdown
        # replaced the typeahead — single-char queries now filter normally.
        models = [
            {"name": "llama3:8b", "size": 1},
            {"name": "qwen2.5:7b", "size": 1},
        ]
        with self._mock_httpx(models):
            resp = await client.get("/api/ollama-library/search?q=q")
        assert resp.status_code == 200
        assert [m["name"] for m in resp.json()] == ["qwen2.5:7b"]

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


# ── Mock provider gating + types endpoint ─────────────────────────────────


class TestProviderTypesEndpoint:
    """Tests for GET /api/providers/types (dev-mode-aware list)."""

    async def test_returns_5_types_when_dev_mode_off(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        data = resp.json()
        values = [t["value"] for t in data]
        assert set(values) == {"ollama", "openai-compatible", "openai", "anthropic", "openrouter"}
        # Each entry has the expected shape
        for entry in data:
            assert set(entry.keys()) == {"value", "label"}

    async def test_returns_6_types_when_dev_mode_on(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        values = [t["value"] for t in resp.json()]
        assert "mock" in values
        assert "openrouter" in values
        assert len(values) == 6

    async def test_types_route_does_not_collide_with_id_route(self, client: AsyncClient) -> None:
        """Regression: /providers/types must be registered before /providers/{id}.

        If route ordering is reversed, FastAPI matches /providers/types
        as a get_provider call with provider_id="types" and returns 404.
        This test pins the ordering invariant.
        """
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200, (
            "GET /providers/types returned non-200 — route may have been reordered "
            "behind /providers/{provider_id}"
        )
        # Confirm body shape — not just a 200 from some other path
        assert isinstance(resp.json(), list)


class TestMockProviderGating:
    """Tests for THE_ONE_DEV_MODE gating on mock-typed creates and updates."""

    async def test_create_mock_rejected_when_dev_mode_off(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            resp = await client.post(
                "/api/providers",
                json={"name": "Mock", "type": "mock", "base_url": ""},
            )
        assert resp.status_code == 400
        assert "DEV_MODE" in resp.json()["detail"]

    async def test_create_mock_accepted_when_dev_mode_on(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            resp = await client.post(
                "/api/providers",
                json={"name": "Mock", "type": "mock", "base_url": ""},
            )
        assert resp.status_code == 201
        assert resp.json()["type"] == "mock"

    async def test_update_to_mock_rejected_when_dev_mode_off(self, client: AsyncClient) -> None:
        # Create an ollama provider first (no dev_mode required)
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            create_resp = await client.post(
                "/api/providers",
                json={"name": "P", "type": "ollama", "base_url": "http://localhost:11434/v1"},
            )
            assert create_resp.status_code == 201
            provider_id = create_resp.json()["id"]
            resp = await client.put(
                f"/api/providers/{provider_id}",
                json={"name": "P", "type": "mock", "base_url": ""},
            )
        assert resp.status_code == 400
        assert "DEV_MODE" in resp.json()["detail"]


class TestMockProviderRoutes:
    """Tests for mock-type branches in test_provider and list_provider_models."""

    async def test_test_provider_mock_returns_ok(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            create_resp = await client.post(
                "/api/providers",
                json={"name": "M", "type": "mock", "base_url": ""},
            )
            provider_id = create_resp.json()["id"]
            resp = await client.post(f"/api/providers/{provider_id}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "Mock" in body["detail"]

    async def test_list_models_mock_default(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            create_resp = await client.post(
                "/api/providers",
                json={"name": "M", "type": "mock", "base_url": ""},
            )
            provider_id = create_resp.json()["id"]
            resp = await client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 1
        assert models[0]["id"] == "mock-default"
        assert models[0]["name"] == "mock-default"

    async def test_list_models_mock_configured(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            create_resp = await client.post(
                "/api/providers",
                json={
                    "name": "M",
                    "type": "mock",
                    "base_url": "",
                    "config": {"models": ["mock-fast", "mock-thinking"]},
                },
            )
            provider_id = create_resp.json()["id"]
            resp = await client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert ids == ["mock-fast", "mock-thinking"]


class TestOpenRouterTypes:
    @pytest.mark.asyncio
    async def test_types_includes_openrouter(self, client) -> None:
        resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        types = resp.json()
        values = {t["value"] for t in types}
        assert "openrouter" in values


class TestOpenRouterValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_referer",
        [
            "https://x.com\r\nX-Injected: 1",
            "https://x.com\nX-Injected: 1",
            "https://x.com\x00",
            "not-a-url",
            "ftp://example.com",
            # Whitespace-in-host (truthy netloc, but not a real host).
            "https:// invalid host /path",
            # Uppercase host — refused outright (not silently downcased).
            "https://EXAMPLE.com",
            # Netloc collapses to whitespace-only.
            "http://  ",
        ],
    )
    async def test_referer_invalid_rejected_with_422(self, client, bad_referer) -> None:
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"referer": bad_referer},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_title",
        [
            "with\r\nbreak",
            "with\nbreak",
            "with\x00null",
            "x" * 65,
        ],
    )
    async def test_title_invalid_rejected_with_422(self, client, bad_title) -> None:
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"title": bad_title},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_round_trip_omits_empty_config_keys(self, client) -> None:
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"referer": "", "title": ""},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code in (200, 201), resp.text
        prov_id = resp.json()["id"]

        get_resp = await client.get(f"/api/providers/{prov_id}")
        cfg = get_resp.json()["config"]
        assert "referer" not in cfg
        assert "title" not in cfg

    @pytest.mark.asyncio
    async def test_round_trip_preserves_valid_config(self, client) -> None:
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"referer": "https://myapp.example", "title": "MyApp"},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code in (200, 201), resp.text
        prov_id = resp.json()["id"]

        get_resp = await client.get(f"/api/providers/{prov_id}")
        cfg = get_resp.json()["config"]
        assert cfg.get("referer") == "https://myapp.example"
        assert cfg.get("title") == "MyApp"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("non_string_referer", [42, ["x"], {"a": 1}])
    async def test_referer_non_string_rejected_with_422(self, client, non_string_referer) -> None:
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"referer": non_string_referer},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("non_string_title", [42, ["x"], {"a": 1}])
    async def test_title_non_string_rejected_with_422(self, client, non_string_title) -> None:
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"title": non_string_title},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code == 422, resp.text


# ── api_key normalization at the Pydantic layer ──────────────────────────


class TestApiKeyNormalization:
    """Provider api_key is stripped to canonical form by the Pydantic
    validator on ``LLMProviderConfig`` — the SAME canonical form for the
    `/test`, `/models`, chat-create-time, and CRUD paths. Pre-normalization
    each path stripped (or didn't strip) on its own which produced the
    "works in /test, fails in chat" class of bug.

    The model-level test pins the unit contract; the round-trip test pins
    the API surface stores the canonical form (so a later GET masks the
    stripped key, not the leading-spaces literal).
    """

    def test_pydantic_strips_whitespace(self) -> None:
        from the_one.db.models import LLMProviderConfig

        cfg = LLMProviderConfig(
            id="x",
            name="X",
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key="  sk-x  ",
        )
        assert cfg.api_key == "sk-x"

    def test_pydantic_empty_after_strip_becomes_none(self) -> None:
        from the_one.db.models import LLMProviderConfig

        cfg = LLMProviderConfig(
            id="x",
            name="X",
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key="   ",
        )
        assert cfg.api_key is None

    def test_pydantic_none_stays_none(self) -> None:
        from the_one.db.models import LLMProviderConfig

        cfg = LLMProviderConfig(
            id="x",
            name="X",
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key=None,
        )
        assert cfg.api_key is None

    @pytest.mark.asyncio
    async def test_create_strips_whitespace_round_trip(
        self, client: AsyncClient
    ) -> None:
        """A POST with leading/trailing whitespace should mask to the stripped
        last-4 (``sk-x`` → ``***``), not to ``  sk-x  ``."""
        resp = await client.post(
            "/api/providers",
            json={
                "name": "Whitespace",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "  sk-roundtrip-key  ",
            },
        )
        assert resp.status_code == 201, resp.text
        provider_id = resp.json()["id"]
        # Mask format ``***...XXXX`` reads from the canonical (stripped) key.
        assert resp.json()["api_key"] == "***...-key"

        # GET reflects the stored canonical form.
        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.json()["api_key"] == "***...-key"

    @pytest.mark.asyncio
    async def test_create_whitespace_only_stored_as_none(
        self, client: AsyncClient
    ) -> None:
        """A POST with only whitespace must be stored as NULL — masking returns
        ``None`` rather than ``"   "`` or ``""``."""
        resp = await client.post(
            "/api/providers",
            json={
                "name": "WhitespaceOnly",
                "type": "ollama",
                "base_url": "http://localhost:11434/v1",
                "api_key": "   ",
            },
        )
        assert resp.status_code == 201, resp.text
        provider_id = resp.json()["id"]
        assert resp.json()["api_key"] is None

        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.json()["api_key"] is None

    @pytest.mark.asyncio
    async def test_masked_sentinel_path_unchanged(self, client: AsyncClient) -> None:
        """The ``__MASKED__`` sentinel path runs BEFORE Pydantic validates the
        new value (api.py:849-852) — the sentinel is replaced by the existing
        stored key (already canonical) and re-validated. This test pins that
        the canonical-storage and sentinel-preserve paths compose correctly:
        a saved ``  sk-y  `` lands as ``sk-y``, and a subsequent rename via
        ``__MASKED__`` keeps it as ``sk-y``."""
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "Sentinel",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "  sk-sentinel-key  ",
            },
        )
        provider_id = create_resp.json()["id"]
        # Stored key is canonical: last-4 of "sk-sentinel-key" is "-key".
        assert create_resp.json()["api_key"] == "***...-key"

        update_resp = await client.put(
            f"/api/providers/{provider_id}",
            json={
                "name": "Renamed",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "__MASKED__",
            },
        )
        assert update_resp.status_code == 200
        # Same canonical mask survives the masked-update.
        assert update_resp.json()["api_key"] == "***...-key"


# ── /test endpoint status semantics + /models error differentiation ───


class TestOpenRouterTestEndpointStatus:
    """The /providers/{id}/test endpoint must distinguish three states for
    openrouter: ok (key valid), warning (reachable, no key), error (auth
    failure or upstream failure). The JS handler renders each state with
    a distinct chip — green ✓ vs amber ⚠ vs red ✗ — so the operator
    knows whether the provider is ready for chat.
    """

    async def test_no_key_returns_warning_not_ok(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.llm import openrouter_api

        async def fake_list(base_url, api_key):
            assert api_key in (None, "")
            return [openrouter_api.OpenRouterModelEntry(id="x/y")]

        monkeypatch.setattr(openrouter_api, "list_models", fake_list)

        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "OR",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
            },
        )
        provider_id = create_resp.json()["id"]
        resp = await client.post(f"/api/providers/{provider_id}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "warning", body
        assert "Add an API key" in body["detail"]

    async def test_key_set_returns_ok(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.llm import openrouter_api

        async def fake_verify(base_url, api_key):
            return {"data": {"label": "test", "limit": 1}}

        async def fake_list(base_url, api_key):
            return [openrouter_api.OpenRouterModelEntry(id="x/y")]

        monkeypatch.setattr(openrouter_api, "verify_key", fake_verify)
        monkeypatch.setattr(openrouter_api, "list_models", fake_list)

        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "OR",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-or-x",
            },
        )
        provider_id = create_resp.json()["id"]
        resp = await client.post(f"/api/providers/{provider_id}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok", body

    async def test_value_error_returns_error_with_contract_violation_detail(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """ValueError from /models shape check must NOT collapse to a
        generic error — the detail must explicitly call out the API
        contract violation so the operator knows it's not a network
        problem."""
        from the_one.llm import openrouter_api

        async def fake_list(base_url, api_key):
            raise ValueError("Unexpected payload shape")

        monkeypatch.setattr(openrouter_api, "list_models", fake_list)

        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "OR",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
            },
        )
        provider_id = create_resp.json()["id"]
        resp = await client.post(f"/api/providers/{provider_id}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "contract violation" in body["detail"].lower()


class TestOpenRouterModelsEndpointErrorMapping:
    """/api/providers/{id}/models must distinguish exception classes —
    network unreachable (502), auth failure (401), timeout (504),
    contract violation (500). Pre-fix all four collapsed to '502
    OpenRouter unreachable: ...' which misled operators into
    troubleshooting non-existent network problems."""

    async def _create_or(self, client: AsyncClient) -> str:
        resp = await client.post(
            "/api/providers",
            json={
                "name": "OR",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "k",
            },
        )
        return resp.json()["id"]

    async def test_value_error_maps_to_500_with_contract_violation_detail(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from the_one.llm import openrouter_api

        async def fake_list(base_url, api_key):
            raise ValueError("Unexpected 'data' shape")

        monkeypatch.setattr(openrouter_api, "list_models", fake_list)
        provider_id = await self._create_or(client)
        resp = await client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 500
        assert "contract violation" in resp.json()["detail"].lower()

    async def test_timeout_maps_to_504(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        import httpx

        from the_one.llm import openrouter_api

        async def fake_list(base_url, api_key):
            raise httpx.TimeoutException("read timeout")

        monkeypatch.setattr(openrouter_api, "list_models", fake_list)
        provider_id = await self._create_or(client)
        resp = await client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()

    async def test_http_status_error_mirrors_upstream_status(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        import httpx

        from the_one.llm import openrouter_api

        async def fake_list(base_url, api_key):
            req = httpx.Request("GET", "https://openrouter.ai/api/v1/models")
            resp = httpx.Response(401, request=req, text="invalid api key")
            raise httpx.HTTPStatusError("401", request=req, response=resp)

        monkeypatch.setattr(openrouter_api, "list_models", fake_list)
        provider_id = await self._create_or(client)
        resp = await client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 401
        assert "401" in resp.json()["detail"]

    async def test_request_error_maps_to_502_unreachable(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        import httpx

        from the_one.llm import openrouter_api

        async def fake_list(base_url, api_key):
            raise httpx.ConnectError("DNS failure")

        monkeypatch.setattr(openrouter_api, "list_models", fake_list)
        provider_id = await self._create_or(client)
        resp = await client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 502
        assert "unreachable" in resp.json()["detail"].lower()


# ── update_provider config-revalidation behavior ──────────────────────


class TestUpdateProviderConfigRevalidation:
    """update_provider re-validates the openrouter config ONLY when
    'config' is in the request body. Without this, a name-only rename
    would re-validate the existing stored config — and if validation
    rules tightened, an unrelated field change could 422 on a previously
    valid stored value. Validate-on-write, not validate-on-rebroadcast.
    """

    async def test_name_only_update_does_not_revalidate_config(
        self, client: AsyncClient
    ) -> None:
        # Create with a valid config.
        create = await client.post(
            "/api/providers",
            json={
                "name": "OR",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "k",
                "config": {"referer": "https://valid.example", "title": "App"},
            },
        )
        assert create.status_code in (200, 201), create.text
        pid = create.json()["id"]

        # Name-only PUT with masked api_key — config NOT in body.
        upd = await client.put(
            f"/api/providers/{pid}",
            json={
                "name": "Renamed",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "__MASKED__",
            },
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["name"] == "Renamed"

    async def test_invalid_config_in_body_returns_422_and_preserves_existing(
        self, client: AsyncClient
    ) -> None:
        create = await client.post(
            "/api/providers",
            json={
                "name": "OR",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "k",
                "config": {"referer": "https://valid.example"},
            },
        )
        pid = create.json()["id"]

        # PUT with masked key + invalid referer — should 422.
        upd = await client.put(
            f"/api/providers/{pid}",
            json={
                "name": "OR",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "__MASKED__",
                "config": {"referer": "javascript:alert(1)"},
            },
        )
        assert upd.status_code == 422, upd.text

        # Config and key on disk unchanged.
        get_resp = await client.get(f"/api/providers/{pid}")
        body = get_resp.json()
        assert body["config"]["referer"] == "https://valid.example"
