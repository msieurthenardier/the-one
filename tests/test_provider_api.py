"""Tests for LLM provider REST API endpoints."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
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
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
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

    async def test_update_with_invalid_type_rejected(self, client: AsyncClient) -> None:
        """Squawk 0013: an unknown ``type`` literal must 422, not silently
        bypass validation via ``model_copy(update=...)`` and corrupt the row."""
        create_resp = await client.post(
            "/api/providers",
            json={"name": "Before", "type": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        provider_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/providers/{provider_id}",
            json={
                "name": "After",
                "type": "not-a-real-provider-type",
                "base_url": "http://localhost:11434/v1",
            },
        )
        assert resp.status_code == 422

        # The stored row must be unchanged — not a half-applied merge.
        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.json()["name"] == "Before"
        assert get_resp.json()["type"] == "ollama"

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

    async def test_create_anthropic_persists_thinking_enabled(self, client: AsyncClient) -> None:
        """POST an anthropic provider with config.thinking_enabled=true → GET
        round-trips the flag (F10-06). config is opaque passthrough — no
        backend schema for the key."""
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "Claude",
                "type": "anthropic",
                "base_url": "https://api.anthropic.com",
                "api_key": "sk-ant-secret1234",
                "config": {"thinking_enabled": True},
            },
        )
        assert create_resp.status_code == 201
        provider_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["config"]["thinking_enabled"] is True

    async def test_update_masked_key_preserves_thinking_config(self, client: AsyncClient) -> None:
        """PUT an anthropic provider with a MASKED api_key and a full config
        (thinking_enabled + a second key) → the stored api_key is preserved
        and BOTH config keys round-trip. model_copy(update=data) replaces the
        config dict wholesale, so the client must re-send every config key it
        wants preserved — this test pins that client-re-send contract."""
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "Claude",
                "type": "anthropic",
                "base_url": "https://api.anthropic.com",
                "api_key": "sk-ant-secret5555",
                "config": {"thinking_enabled": False},
            },
        )
        assert create_resp.status_code == 201
        provider_id = create_resp.json()["id"]

        # PUT with the masked sentinel + a full config re-send (both keys).
        put_resp = await client.put(
            f"/api/providers/{provider_id}",
            json={
                "name": "Claude",
                "type": "anthropic",
                "base_url": "https://api.anthropic.com",
                "api_key": "__MASKED__",
                "config": {"thinking_enabled": True, "num_ctx": 4096},
            },
        )
        assert put_resp.status_code == 200
        # Stored api_key preserved (masked response reflects the ORIGINAL key).
        assert put_resp.json()["api_key"] == "***...5555"

        get_resp = await client.get(f"/api/providers/{provider_id}")
        data = get_resp.json()
        assert data["config"]["thinking_enabled"] is True
        assert data["config"]["num_ctx"] == 4096
        assert data["api_key"] == "***...5555"

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
        assert resp.json() == {"status": "ok", "key_file": "promoted"}

        # Verify the key is still accessible (masked correctly)
        resp = await client.get(f"/api/providers/{provider_id}")
        assert resp.status_code == 200
        assert resp.json()["api_key"] == "***...5678"

    async def test_rotate_empty_table(self, client: AsyncClient) -> None:
        """Rotation with no providers should succeed as a no-op."""
        resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "key_file": "promoted"}

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

        # (i-b) The staged sidecar is discarded on rollback (AC2).
        from the_one.encryption import next_key_path

        assert not next_key_path(key_path).exists()

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

    async def test_rotate_discards_pending_key_on_cancellation(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """A BaseException (CancelledError) inside write_transaction must
        still discard the staged sidecar key.

        Mirrors test_rotate_preserves_key_on_db_failure above, but the
        simulated failure is `asyncio.CancelledError` — a BaseException,
        not an Exception subclass — raised from `commit()` (the same seam
        the sibling test patches). `write_transaction`'s guard
        (the_one/db/_write_lock.py:73) rolls back on BaseException; before
        squawk 0057's fix, the endpoint's `except Exception` clause around
        the transaction block would NOT catch this, so
        `encryptor.discard_pending_key()` would never run and the staged
        `.next` sidecar would be left on disk despite the rollback. This
        test fails without that fix.
        """
        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "CancelTest",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-canceltest9999",
            },
        )
        assert create_resp.status_code in (200, 201)
        provider_id = create_resp.json()["id"]

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()

        with (
            patch(
                "aiosqlite.Connection.commit",
                side_effect=asyncio.CancelledError(),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await client.post("/api/encryption/rotate")

        # (i) Key file byte-identical to its pre-rotation contents.
        assert key_path.read_bytes() == key_before

        # (i-b) The staged sidecar is discarded despite the BaseException
        # (the fix under test — squawk 0057).
        from the_one.encryption import next_key_path

        assert not next_key_path(key_path).exists()

        # (ii) Masked tail still works (cached encryptor untouched).
        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["api_key"] == "***...9999"

    async def test_rotate_mcp_source_secrets(self, client: AsyncClient) -> None:
        """After rotation, MCP source secrets still decrypt under the new key."""
        create_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "github-mcp"},
                "secrets": {"GITHUB_TOKEN": "ghp_rotationtest5678"},
            },
        )
        assert create_resp.status_code in (200, 201)
        sid = create_resp.json()["id"]

        resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "key_file": "promoted"}

        # GET-after-rotate proves the cached encryptor decrypts under the new key
        get_resp = await client.get(f"/api/mcp-sources/{sid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["secrets"]["GITHUB_TOKEN"] == "***...5678"

    async def test_rotate_mixed_providers_and_mcps(self, client: AsyncClient) -> None:
        """One rotation re-encrypts both surfaces atomically."""
        prov_resp = await client.post(
            "/api/providers",
            json={
                "name": "MixedProv",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-mixedrotateprovider",
            },
        )
        pid = prov_resp.json()["id"]

        mcp_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "MixedMCP",
                "type": "streamable-http",
                "config": {"url": "https://mcp.example.com"},
                "secrets": {"AUTH": "bearer-mixedrotatemcptoken"},
            },
        )
        sid = mcp_resp.json()["id"]

        rot_resp = await client.post("/api/encryption/rotate")
        assert rot_resp.status_code == 200
        assert rot_resp.json() == {"status": "ok", "key_file": "promoted"}

        # Both surfaces still decrypt under the new key
        prov_get = await client.get(f"/api/providers/{pid}")
        assert prov_get.json()["api_key"] == "***...ider"
        mcp_get = await client.get(f"/api/mcp-sources/{sid}")
        assert mcp_get.json()["secrets"]["AUTH"] == "***...oken"

    async def test_rotate_preserves_mcp_secrets_on_db_failure(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """A DB commit failure during rotation leaves MCP ciphertext intact.

        Mirrors test_rotate_preserves_key_on_db_failure for the MCP surface:
        on-disk key file unchanged, cached encryptor unchanged, on-disk
        ciphertext unchanged, direct decrypt with the pre-rotation key
        still yields the original plaintext.
        """
        import json as _json

        create_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "FailMCP",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": "preservedmcpsecretvalue"},
            },
        )
        sid = create_resp.json()["id"]

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()

        # Capture pre-rotation ciphertext directly from the DB so we can
        # assert it's byte-identical post-failure.
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                row = await cur.fetchone()
            ct_before = row["secrets"]
        finally:
            await direct_conn.close()

        with (
            patch(
                "aiosqlite.Connection.commit",
                side_effect=RuntimeError("simulated DB failure"),
            ),
            pytest.raises(RuntimeError, match="simulated DB failure"),
        ):
            await client.post("/api/encryption/rotate")

        # (i) Key file byte-identical to its pre-rotation contents
        assert key_path.read_bytes() == key_before

        # (i-b) The staged sidecar is discarded on rollback (AC2).
        from the_one.encryption import next_key_path

        assert not next_key_path(key_path).exists()

        # (ii) Cached encryptor still decrypts (proves install_key NOT called)
        get_resp = await client.get(f"/api/mcp-sources/{sid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["secrets"]["K"] == "***...alue"

        # (iii) On-disk ciphertext byte-identical (catches a regression where
        # the UPDATE loop wrote new ciphertext before the commit failed)
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None
        assert row["secrets"] == ct_before
        # Direct decrypt with the pre-rotation key still works on disk ciphertext
        decrypted = Fernet(key_before).decrypt(row["secrets"].encode()).decode()
        assert _json.loads(decrypted) == {"K": "preservedmcpsecretvalue"}

    async def test_rotate_connector_secrets(self, client: AsyncClient, tmp_path: Path) -> None:
        """After rotation, connectors.secrets still decrypts under
        the new key — re-encrypted atomically with llm_providers.api_key
        and mcp_sources.secrets in the same single commit.

        Mirrors test_rotate_mcp_source_secrets at line 612. Seeds via raw
        SQL because Flight 1 ships no REST routes for the connectors table —
        those land in Flight 2. The seeding pattern mirrors the existing
        migration-residue test's "fresh aiosqlite connection on the test
        DB" idiom for cross-connection commit visibility.
        """
        import json as _json

        # Seed a connectors row directly via SQL. Open a fresh
        # connection on the same DB the API fixture is using (path is
        # ``tmp_path / "test.db"``) — proven cross-connection commit
        # visibility ordering with the existing MCP rotation tests.
        seed_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        seed_conn.row_factory = aiosqlite.Row
        try:
            # Read the test encryptor's key from the on-disk key file the
            # client fixture created and encrypt secrets in-process.
            key_before = (tmp_path / "test.key").read_bytes()
            ciphertext = (
                Fernet(key_before)
                .encrypt(_json.dumps({"BOT_TOKEN": "rotationtest5678"}).encode())
                .decode()
            )
            await seed_conn.execute(
                "INSERT INTO connectors (id, type, config, secrets) VALUES (?, ?, ?, ?)",
                ("acct-rotate", "stub", "{}", ciphertext),
            )
            await seed_conn.commit()
        finally:
            await seed_conn.close()

        resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "key_file": "promoted"}

        # The key file has been replaced; read the new key and verify the
        # stored ciphertext decrypts under it (proves the row was re-
        # encrypted in the rotation transaction's third UPDATE loop).
        key_after = (tmp_path / "test.key").read_bytes()
        assert key_after != key_before

        verify_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        verify_conn.row_factory = aiosqlite.Row
        try:
            async with verify_conn.execute(
                "SELECT secrets FROM connectors WHERE id = ?", ("acct-rotate",)
            ) as cur:
                row = await cur.fetchone()
        finally:
            await verify_conn.close()
        assert row is not None
        decrypted = Fernet(key_after).decrypt(row["secrets"].encode()).decode()
        assert _json.loads(decrypted) == {"BOT_TOKEN": "rotationtest5678"}

    async def test_rotate_preserves_connector_secrets_on_db_failure(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """A DB commit failure during rotation leaves all three corpora
        byte-identical — llm_providers.api_key, mcp_sources.secrets, AND
        connectors.secrets roll back together.

        Mirrors test_rotate_preserves_mcp_secrets_on_db_failure at line 669
        — ``unittest.mock.patch("aiosqlite.Connection.commit", side_effect=
        RuntimeError(...))`` is the canonical pattern that exercises the
        full try/UPDATE-loops/commit/except/rollback contract. Patching
        earlier UPDATE statements would not fire because the rotation
        handler gets its own connection via ``get_connection()``.
        """
        import json as _json

        # Seed one row in each of the three encrypted corpora via the
        # public API where possible (llm_providers, mcp_sources) and raw
        # SQL for the connectors table (no REST route in Flight 1).
        prov_resp = await client.post(
            "/api/providers",
            json={
                "name": "FailMix",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-preservetokenabcd",
            },
        )
        assert prov_resp.status_code in (200, 201)
        pid = prov_resp.json()["id"]

        mcp_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "FailMixMCP",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": "preservedmcpvalue"},
            },
        )
        assert mcp_resp.status_code in (200, 201)
        sid = mcp_resp.json()["id"]

        # Seed connectors row with encrypted secrets via a fresh
        # aiosqlite connection (no REST route until Flight 2).
        key_before = (tmp_path / "test.key").read_bytes()
        conn_ct_before = (
            Fernet(key_before)
            .encrypt(_json.dumps({"BOT_TOKEN": "preservedconnectorvalue"}).encode())
            .decode()
        )
        seed_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        seed_conn.row_factory = aiosqlite.Row
        try:
            await seed_conn.execute(
                "INSERT INTO connectors (id, type, config, secrets) VALUES (?, ?, ?, ?)",
                ("conn-preserve", "stub", "{}", conn_ct_before),
            )
            await seed_conn.commit()
        finally:
            await seed_conn.close()

        # Capture pre-rotation ciphertext directly from the DB for each
        # corpus so we can assert byte-equality post-failure.
        snapshot_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        snapshot_conn.row_factory = aiosqlite.Row
        try:
            async with snapshot_conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?", (pid,)
            ) as cur:
                llm_ct_before = (await cur.fetchone())["api_key"]
            async with snapshot_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                mcp_ct_before = (await cur.fetchone())["secrets"]
            async with snapshot_conn.execute(
                "SELECT secrets FROM connectors WHERE id = ?", ("conn-preserve",)
            ) as cur:
                conn_ct_actual_before = (await cur.fetchone())["secrets"]
        finally:
            await snapshot_conn.close()
        assert conn_ct_actual_before == conn_ct_before

        # Inject failure at the commit boundary. All three UPDATE loops
        # run, then commit raises, then the rollback in the except path
        # restores all three corpora atomically.
        with (
            patch(
                "aiosqlite.Connection.commit",
                side_effect=RuntimeError("simulated DB failure"),
            ),
            pytest.raises(RuntimeError, match="simulated DB failure"),
        ):
            await client.post("/api/encryption/rotate")

        # (i) Key file byte-identical to its pre-rotation contents
        assert (tmp_path / "test.key").read_bytes() == key_before

        # (i-b) The staged sidecar is discarded on rollback (AC2).
        from the_one.encryption import next_key_path

        assert not next_key_path(tmp_path / "test.key").exists()

        # (ii) Cached encryptor still decrypts (proves install_key NOT called).
        # We exercise the LLM + MCP surfaces via the API; for connector
        # accounts (no REST route yet) we open a fresh connection and
        # decrypt with the pre-rotation key directly.
        prov_get = await client.get(f"/api/providers/{pid}")
        assert prov_get.status_code == 200
        assert prov_get.json()["api_key"] == "***...abcd"

        mcp_get = await client.get(f"/api/mcp-sources/{sid}")
        assert mcp_get.status_code == 200
        assert mcp_get.json()["secrets"]["K"] == "***...alue"

        # (iii) On-disk ciphertext byte-identical for ALL THREE corpora —
        # catches a regression where any UPDATE loop wrote new ciphertext
        # before the commit failed.
        post_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        post_conn.row_factory = aiosqlite.Row
        try:
            async with post_conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?", (pid,)
            ) as cur:
                assert (await cur.fetchone())["api_key"] == llm_ct_before
            async with post_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                assert (await cur.fetchone())["secrets"] == mcp_ct_before
            async with post_conn.execute(
                "SELECT secrets FROM connectors WHERE id = ?", ("conn-preserve",)
            ) as cur:
                assert (await cur.fetchone())["secrets"] == conn_ct_before
        finally:
            await post_conn.close()

        # Direct decrypt with the pre-rotation key still works on disk
        # ciphertext for the connector row (closes the loop: not just byte-
        # equality but functional decryptability under the original key).
        decrypted = Fernet(key_before).decrypt(conn_ct_before.encode()).decode()
        assert _json.loads(decrypted) == {"BOT_TOKEN": "preservedconnectorvalue"}

    async def test_rotate_with_migration_residue_mcp_row(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """A v10-migrated row with plaintext '{}' rotates without crashing.

        Pre-L2 rows + v10-migration-residue rows have secrets='{}' (the
        column default — plaintext, not ciphertext). Rotation must tolerate
        these via the same InvalidToken-swallow semantic as
        MCPSourceRepository._ciphertext_to_secrets, and normalize them to
        proper ciphertext as a side-effect.

        Pattern: create the row through the API (so it's established via the
        fixture's cached connection — guaranteed visible to subsequent API
        reads), then reach in via a fresh aiosqlite connection to OVERWRITE
        the secrets column with literal '{}' (simulating migration-residue).
        This is the inverse of the existing failure-path test's pattern
        (write via API conn, read via fresh conn) — same proven cross-
        connection commit-visibility ordering.
        """
        # Step 1: create the row through the API. This goes through the L2
        # repository's encrypted-write path and the row is established via
        # the fixture's cached connection.
        create_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "Residue",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {},  # The L2 repo encrypts '{}' as proper ciphertext
            },
        )
        assert create_resp.status_code in (200, 201)
        sid = create_resp.json()["id"]

        # Step 2: open a fresh aiosqlite connection and overwrite the secrets
        # column with literal '{}', simulating a migration-residue row that
        # has never been written by the L2 repo. The fresh connection's
        # commit is visible to the API's cached connection on its next
        # SELECT (standard SQLite cross-connection visibility — proven by
        # the existing test_rotate_preserves_key_on_db_failure pattern).
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            await direct_conn.execute(
                "UPDATE mcp_sources SET secrets = '{}' WHERE id = ?",
                (sid,),
            )
            await direct_conn.commit()
        finally:
            await direct_conn.close()

        # Pre-rotation: residue row reads as empty secrets (tolerant decode)
        pre_get = await client.get(f"/api/mcp-sources/{sid}")
        assert pre_get.status_code == 200
        assert pre_get.json()["secrets"] == {}

        # Rotate — must NOT crash on the residue row
        rot_resp = await client.post("/api/encryption/rotate")
        assert rot_resp.status_code == 200
        assert rot_resp.json() == {"status": "ok", "key_file": "promoted"}

        # Post-rotation: residue row reads as empty secrets, AND the on-disk
        # column is no longer the literal '{}' — it's proper Fernet
        # ciphertext for the JSON string '{}'
        post_get = await client.get(f"/api/mcp-sources/{sid}")
        assert post_get.status_code == 200
        assert post_get.json()["secrets"] == {}

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None
        assert row["secrets"] != "{}"  # Normalized to ciphertext
        # New key on disk decrypts the normalized ciphertext to '{}'
        new_key = (tmp_path / "test.key").read_bytes()
        assert Fernet(new_key).decrypt(row["secrets"].encode()) == b"{}"

    async def test_rotate_dual_surface_atomicity_on_db_failure(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """A commit failure rolls back BOTH surfaces atomically.

        Populates both an LLM provider AND an MCP source, simulates
        aiosqlite.Connection.commit failure, and asserts that the on-disk
        ciphertext on BOTH surfaces is byte-identical to its pre-rotation
        contents. This is the dual-surface counterpart of the existing
        test_rotate_preserves_key_on_db_failure (LLM-only) and the new
        test_rotate_preserves_mcp_secrets_on_db_failure (MCP-only) —
        proves the single-try / single-commit / single-rollback structure
        rolls back BOTH UPDATE loops together.
        """
        prov_resp = await client.post(
            "/api/providers",
            json={
                "name": "DualFailProv",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-dualfailureprovider",
            },
        )
        pid = prov_resp.json()["id"]

        mcp_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "DualFailMCP",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": "dualfailuremcpsecret"},
            },
        )
        sid = mcp_resp.json()["id"]

        # Capture pre-rotation ciphertext for both surfaces
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?", (pid,)
            ) as cur:
                prov_ct_before = (await cur.fetchone())["api_key"]
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                mcp_ct_before = (await cur.fetchone())["secrets"]
        finally:
            await direct_conn.close()

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()

        with (
            patch(
                "aiosqlite.Connection.commit",
                side_effect=RuntimeError("simulated DB failure"),
            ),
            pytest.raises(RuntimeError, match="simulated DB failure"),
        ):
            await client.post("/api/encryption/rotate")

        # (i) Key file untouched
        assert key_path.read_bytes() == key_before

        # (i-b) The staged sidecar is discarded on rollback (AC2).
        from the_one.encryption import next_key_path

        assert not next_key_path(key_path).exists()

        # (ii) BOTH on-disk ciphertexts byte-identical to pre-rotation
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?", (pid,)
            ) as cur:
                assert (await cur.fetchone())["api_key"] == prov_ct_before
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                assert (await cur.fetchone())["secrets"] == mcp_ct_before
        finally:
            await direct_conn.close()

        # (iii) Cached encryptor still decrypts both surfaces (proves
        # install_key was NOT called — masked tail equality round-trips
        # through the cached encryptor)
        prov_get = await client.get(f"/api/providers/{pid}")
        assert prov_get.json()["api_key"] == "***...ider"
        mcp_get = await client.get(f"/api/mcp-sources/{sid}")
        assert mcp_get.json()["secrets"]["K"] == "***...cret"

    # ── M21 F01 L01: agents.tool_overrides / agents.mcp_overrides join
    # the rotation transaction as the fifth surface (flight-log Decision D1).

    async def test_rotate_agent_overrides(self, client: AsyncClient, tmp_path: Path) -> None:
        """After rotation, an agent's tool_overrides/mcp_overrides still
        decrypt under the new key and NOT the old key."""
        import json as _json

        from cryptography.fernet import InvalidToken

        create_resp = await client.post(
            "/api/agents",
            json={
                "name": "rotate-agent",
                "tool_overrides": {"shell": {"timeout": 30}},
                "mcp_overrides": {"github": {"bearer_token": "rotationtestbearer"}},
            },
        )
        assert create_resp.status_code == 201

        key_before = (tmp_path / "test.key").read_bytes()

        rot_resp = await client.post("/api/encryption/rotate")
        assert rot_resp.status_code == 200
        assert rot_resp.json() == {"status": "ok", "key_file": "promoted"}

        key_after = (tmp_path / "test.key").read_bytes()
        assert key_after != key_before

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT tool_overrides, mcp_overrides FROM agents WHERE name = ?",
                ("rotate-agent",),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None

        # Old key can no longer decrypt (re-encrypted under the new key).
        with pytest.raises(InvalidToken):
            Fernet(key_before).decrypt(row["tool_overrides"].encode())
        with pytest.raises(InvalidToken):
            Fernet(key_before).decrypt(row["mcp_overrides"].encode())

        # New key decrypts to the original values.
        assert _json.loads(Fernet(key_after).decrypt(row["tool_overrides"].encode())) == {
            "shell": {"timeout": 30}
        }
        assert _json.loads(Fernet(key_after).decrypt(row["mcp_overrides"].encode())) == {
            "github": {"bearer_token": "rotationtestbearer"}
        }

        # GET-after-rotate proves the cached encryptor decrypts under the
        # new key end-to-end (mirrors test_rotate_mcp_source_secrets).
        get_resp = await client.get("/api/agents/rotate-agent")
        assert get_resp.status_code == 200
        assert get_resp.json()["mcp_overrides"]["github"]["bearer_token"] == "***...arer"

    async def test_rotate_normalizes_legacy_plaintext_agent_row(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """A legacy row whose columns hold plaintext JSON (pre-leg data,
        NOT the migration-residue '{}' default) rotates without crashing
        and is normalized to proper ciphertext — mirrors
        test_rotate_with_migration_residue_mcp_row, but agents legacy
        plaintext is real operator data, not an empty-default residue."""
        import json as _json

        seed_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        seed_conn.row_factory = aiosqlite.Row
        try:
            await seed_conn.execute(
                "INSERT INTO agents (name, tool_overrides, mcp_overrides) VALUES (?, ?, ?)",
                (
                    "legacy-plaintext-agent",
                    _json.dumps({"shell": {"timeout": 45}}),
                    _json.dumps({"github": {"bearer_token": "legacyplaintexttoken"}}),
                ),
            )
            await seed_conn.commit()
        finally:
            await seed_conn.close()

        # Pre-rotation: the API's tolerant decode reads the legacy
        # plaintext intact.
        pre_get = await client.get("/api/agents/legacy-plaintext-agent")
        assert pre_get.status_code == 200
        assert pre_get.json()["tool_overrides"] == {"shell": {"timeout": 45}}

        rot_resp = await client.post("/api/encryption/rotate")
        assert rot_resp.status_code == 200
        assert rot_resp.json() == {"status": "ok", "key_file": "promoted"}

        post_get = await client.get("/api/agents/legacy-plaintext-agent")
        assert post_get.status_code == 200
        assert post_get.json()["tool_overrides"] == {"shell": {"timeout": 45}}

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT tool_overrides FROM agents WHERE name = ?",
                ("legacy-plaintext-agent",),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None
        with pytest.raises(_json.JSONDecodeError):
            _json.loads(row["tool_overrides"])  # normalized to ciphertext
        new_key = (tmp_path / "test.key").read_bytes()
        assert _json.loads(Fernet(new_key).decrypt(row["tool_overrides"].encode())) == {
            "shell": {"timeout": 45}
        }

    async def test_rotate_agent_with_null_columns_stays_null(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """An agent whose override columns are both NULL rotates without
        writing an encrypted "null" — the columns stay SQL NULL."""
        create_resp = await client.post("/api/agents", json={"name": "null-columns-agent"})
        assert create_resp.status_code == 201

        rot_resp = await client.post("/api/encryption/rotate")
        assert rot_resp.status_code == 200

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT tool_overrides, mcp_overrides FROM agents WHERE name = ?",
                ("null-columns-agent",),
            ) as cur:
                row = await cur.fetchone()
        finally:
            await direct_conn.close()
        assert row is not None
        assert row["tool_overrides"] is None
        assert row["mcp_overrides"] is None

    async def test_rotate_preserves_agent_overrides_on_db_failure(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """A DB commit failure during rotation leaves the agents columns
        byte-identical, alongside the other four surfaces — the
        commit-patch shape (mirrors test_rotate_preserves_mcp_secrets_on_db_failure)."""
        create_resp = await client.post(
            "/api/agents",
            json={
                "name": "fail-agent",
                "mcp_overrides": {"github": {"bearer_token": "preserveagenttoken"}},
            },
        )
        assert create_resp.status_code == 201

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT mcp_overrides FROM agents WHERE name = ?", ("fail-agent",)
            ) as cur:
                ct_before = (await cur.fetchone())["mcp_overrides"]
        finally:
            await direct_conn.close()

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

        # (i-b) The staged sidecar is discarded on rollback (AC2).
        from the_one.encryption import next_key_path

        assert not next_key_path(key_path).exists()

        # (ii) Cached encryptor still decrypts (proves install_key NOT called).
        get_resp = await client.get("/api/agents/fail-agent")
        assert get_resp.status_code == 200
        assert get_resp.json()["mcp_overrides"]["github"]["bearer_token"] == "***...oken"

        # (iii) On-disk ciphertext byte-identical.
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT mcp_overrides FROM agents WHERE name = ?", ("fail-agent",)
            ) as cur:
                assert (await cur.fetchone())["mcp_overrides"] == ct_before
        finally:
            await direct_conn.close()

    async def test_rotate_agents_update_failure_rolls_back_other_surfaces(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Placement test: a failure injected specifically into the
        `UPDATE agents` statement rolls back an MCP source's ciphertext
        and the on-disk key file — proving the agents UPDATE loop sits
        INSIDE the same `try:` block as the other four surfaces (a
        commit-patch test alone cannot prove ordering/placement, only
        that a failure somewhere rolls everything back)."""
        mcp_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "PlacementMCP",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": "placementtestmcpsecret"},
            },
        )
        assert mcp_resp.status_code in (200, 201)
        sid = mcp_resp.json()["id"]

        agent_resp = await client.post(
            "/api/agents",
            json={
                "name": "placement-agent",
                "mcp_overrides": {"github": {"bearer_token": "placementagenttoken"}},
            },
        )
        assert agent_resp.status_code == 201

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                mcp_ct_before = (await cur.fetchone())["secrets"]
        finally:
            await direct_conn.close()

        real_execute = aiosqlite.Connection.execute

        def _raising_execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and sql.strip().startswith("UPDATE agents"):
                raise RuntimeError("simulated agents UPDATE failure")
            return real_execute(self, sql, *args, **kwargs)

        with (
            patch("aiosqlite.Connection.execute", _raising_execute),
            pytest.raises(RuntimeError, match="simulated agents UPDATE failure"),
        ):
            await client.post("/api/encryption/rotate")

        # Key file untouched — the failure happened before commit.
        assert key_path.read_bytes() == key_before

        # The MCP source's ciphertext is untouched (rollback covered it too).
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM mcp_sources WHERE id = ?", (sid,)
            ) as cur:
                assert (await cur.fetchone())["secrets"] == mcp_ct_before
        finally:
            await direct_conn.close()

        # Cached encryptor still decrypts the MCP source (install_key NOT called).
        mcp_get = await client.get(f"/api/mcp-sources/{sid}")
        assert mcp_get.json()["secrets"]["K"] == "***...cret"

    # ── Leg 1 (M22 F01): two-phase sidecar handoff, seven corpora ──────

    async def test_rotate_staging_failure_returns_500(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """AC1: if staging the `.next` sidecar raises, the route returns
        500, the DB is unchanged, the canonical key file is byte-identical,
        and no `.next` or `.tmp.*` file remains."""
        from the_one.encryption import next_key_path

        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "StageFailTest",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-stagefailure1234",
            },
        )
        assert create_resp.status_code in (200, 201)
        provider_id = create_resp.json()["id"]

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()

        with patch(
            "the_one.encryption._write_key_atomic",
            side_effect=OSError("simulated disk full"),
        ):
            resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 500

        # DB unchanged, canonical key file unchanged, no sidecar / temp files.
        assert key_path.read_bytes() == key_before
        assert not next_key_path(key_path).exists()
        leftovers = [p for p in tmp_path.iterdir() if p.name not in ("test.key", "test.db")]
        assert leftovers == [], f"unexpected leftover files: {leftovers}"

        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["api_key"] == "***...1234"

    async def test_rotate_promote_failure_stays_staged_and_reconciles(
        self, client: AsyncClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC4: with `os.replace` failing only for the promotion (dst ==
        key_path), the route still returns 200 with
        `{"status": "ok", "key_file": "staged"}`, the provider's key
        remains retrievable (masked), the canonical key file still holds
        the OLD key, `.next` holds the NEW key, and an ERROR-level log
        names the reached state. The startup reconcile then promotes it."""
        import logging

        from the_one.db.key_reconcile import reconcile_pending_key
        from the_one.encryption import Encryptor, next_key_path

        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "PromoteFailTest",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-promotefailure5678",
            },
        )
        assert create_resp.status_code in (200, 201)
        provider_id = create_resp.json()["id"]

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()
        next_path = next_key_path(key_path)

        real_replace = os.replace

        def fake_replace(src, dst, *args, **kwargs):
            if Path(dst) == key_path:
                raise OSError("simulated ENOSPC on promote")
            return real_replace(src, dst, *args, **kwargs)

        with caplog.at_level(logging.ERROR, logger="the_one.interfaces.web.api"):
            with patch("the_one.encryption.os.replace", fake_replace):
                resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "key_file": "staged"}

        # Canonical key file still holds the OLD key; `.next` holds the NEW key.
        assert key_path.read_bytes() == key_before
        assert next_path.exists()
        new_key = next_path.read_bytes()
        assert new_key != key_before

        # ERROR log names the reached state.
        assert any(
            record.levelno == logging.ERROR and "promot" in record.getMessage().lower()
            for record in caplog.records
        )

        # The provider's key remains retrievable (masked) — the DB already
        # committed under the new key, and the cached encryptor's
        # install_key ran, so reads succeed even though promotion failed.
        get_resp = await client.get(f"/api/providers/{provider_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["api_key"] == "***...5678"

        # The startup reconcile promotes the leftover sidecar on next start.
        fresh_encryptor = Encryptor(key_before, key_path=key_path, pending_key=new_key)
        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            outcome = await reconcile_pending_key(direct_conn, fresh_encryptor)
        finally:
            await direct_conn.close()
        assert outcome == "promoted"
        assert key_path.read_bytes() == new_key
        assert not next_path.exists()

    async def test_rotate_happy_path_logs_info_with_fingerprint(
        self, client: AsyncClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC5: the happy path logs one INFO line with per-corpus row
        counts and a key fingerprint — never key bytes — and leaves no
        `.next` sidecar behind."""
        import hashlib
        import logging

        from the_one.encryption import next_key_path

        create_resp = await client.post(
            "/api/providers",
            json={
                "name": "LogFingerprintTest",
                "type": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-logfingerprint0001",
            },
        )
        assert create_resp.status_code in (200, 201)

        key_path = tmp_path / "test.key"

        with caplog.at_level(logging.INFO, logger="the_one.interfaces.web.api"):
            resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "key_file": "promoted"}

        new_key = key_path.read_bytes()
        fingerprint = hashlib.sha256(new_key).hexdigest()[:8]

        info_records = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "encryption key rotated" in r.getMessage()
        ]
        assert len(info_records) == 1
        message = info_records[0].getMessage()
        assert fingerprint in message
        assert "key_file=promoted" in message
        # Never log key bytes.
        assert new_key.decode() not in message

        assert not next_key_path(key_path).exists()

    async def test_rotate_tool_config_secret(self, client: AsyncClient, tmp_path: Path) -> None:
        """AC9: tool_configs.secrets rotates inside the same transaction —
        still readable via ToolConfigRepository after rotation."""
        from the_one.db.repositories import ToolConfigRepository
        from the_one.encryption import Encryptor

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()
        seed_encryptor = Encryptor(key_before, key_path=key_path)

        seed_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        seed_conn.row_factory = aiosqlite.Row
        try:
            tool_repo = ToolConfigRepository(seed_conn, seed_encryptor)
            await tool_repo.upsert(
                "web_search",
                {"engine": "brave"},
                secrets={"BRAVE_API_KEY": "toolconfigsecretvalue"},
            )
        finally:
            await seed_conn.close()

        resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "key_file": "promoted"}

        key_after = key_path.read_bytes()
        assert key_after != key_before

        verify_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        verify_conn.row_factory = aiosqlite.Row
        try:
            verify_repo = ToolConfigRepository(verify_conn, Encryptor(key_after, key_path=key_path))
            row = await verify_repo.get("web_search")
        finally:
            await verify_conn.close()
        assert row.secrets == {"BRAVE_API_KEY": "toolconfigsecretvalue"}

    async def test_rotate_external_credential_secret(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """AC9: agent_external_credentials.secret rotates inside the same
        transaction — load_all() still returns the plaintext secret
        component after rotation."""
        from the_one.db.repositories import AgentExternalCredentialRepository
        from the_one.encryption import Encryptor

        mcp_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "ExtCredParent",
                "type": "stdio",
                "config": {"command": "x"},
            },
        )
        assert mcp_resp.status_code in (200, 201)
        source_id = mcp_resp.json()["id"]

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()
        seed_encryptor = Encryptor(key_before, key_path=key_path)

        seed_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        seed_conn.row_factory = aiosqlite.Row
        try:
            ext_repo = AgentExternalCredentialRepository(seed_conn, seed_encryptor)
            await ext_repo.create(
                source_id=source_id,
                label="test-credential",
                identifier="ext_testidentifier",
                secret="extcredentialsecretvalue",
            )
        finally:
            await seed_conn.close()

        resp = await client.post("/api/encryption/rotate")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "key_file": "promoted"}

        key_after = key_path.read_bytes()
        assert key_after != key_before

        verify_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        verify_conn.row_factory = aiosqlite.Row
        try:
            verify_repo = AgentExternalCredentialRepository(
                verify_conn, Encryptor(key_after, key_path=key_path)
            )
            rows = await verify_repo.load_all()
        finally:
            await verify_conn.close()
        assert ("ext_testidentifier", source_id, "extcredentialsecretvalue") in rows

    async def test_rotate_tool_configs_update_failure_rolls_back(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """AC9 rollback: a failure injected into the `UPDATE tool_configs`
        statement rolls back the whole transaction, following the
        `test_rotate_agents_update_failure_rolls_back_other_surfaces`
        template."""
        from the_one.db.repositories import ToolConfigRepository
        from the_one.encryption import Encryptor, next_key_path

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()
        seed_encryptor = Encryptor(key_before, key_path=key_path)

        seed_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        seed_conn.row_factory = aiosqlite.Row
        try:
            tool_repo = ToolConfigRepository(seed_conn, seed_encryptor)
            await tool_repo.upsert(
                "web_search",
                {"engine": "brave"},
                secrets={"BRAVE_API_KEY": "rollbacktoolsecret"},
            )
        finally:
            await seed_conn.close()

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM tool_configs WHERE name = ?", ("web_search",)
            ) as cur:
                ct_before = (await cur.fetchone())["secrets"]
        finally:
            await direct_conn.close()

        real_execute = aiosqlite.Connection.execute

        def _raising_execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and sql.strip().startswith("UPDATE tool_configs"):
                raise RuntimeError("simulated tool_configs UPDATE failure")
            return real_execute(self, sql, *args, **kwargs)

        with (
            patch("aiosqlite.Connection.execute", _raising_execute),
            pytest.raises(RuntimeError, match="simulated tool_configs UPDATE failure"),
        ):
            await client.post("/api/encryption/rotate")

        assert key_path.read_bytes() == key_before
        assert not next_key_path(key_path).exists()

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secrets FROM tool_configs WHERE name = ?", ("web_search",)
            ) as cur:
                assert (await cur.fetchone())["secrets"] == ct_before
        finally:
            await direct_conn.close()

    async def test_rotate_external_credentials_update_failure_rolls_back(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """AC9 rollback: a failure injected into the
        `UPDATE agent_external_credentials` statement rolls back the
        whole transaction."""
        from the_one.db.repositories import AgentExternalCredentialRepository
        from the_one.encryption import Encryptor, next_key_path

        mcp_resp = await client.post(
            "/api/mcp-sources",
            json={
                "name": "ExtCredRollbackParent",
                "type": "stdio",
                "config": {"command": "x"},
            },
        )
        assert mcp_resp.status_code in (200, 201)
        source_id = mcp_resp.json()["id"]

        key_path = tmp_path / "test.key"
        key_before = key_path.read_bytes()
        seed_encryptor = Encryptor(key_before, key_path=key_path)

        seed_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        seed_conn.row_factory = aiosqlite.Row
        try:
            ext_repo = AgentExternalCredentialRepository(seed_conn, seed_encryptor)
            await ext_repo.create(
                source_id=source_id,
                label="rollback-credential",
                identifier="ext_rollbackidentifier",
                secret="rollbackextsecret",
            )
        finally:
            await seed_conn.close()

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secret FROM agent_external_credentials WHERE identifier = ?",
                ("ext_rollbackidentifier",),
            ) as cur:
                ct_before = (await cur.fetchone())["secret"]
        finally:
            await direct_conn.close()

        real_execute = aiosqlite.Connection.execute

        def _raising_execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and sql.strip().startswith("UPDATE agent_external_credentials"):
                raise RuntimeError("simulated ext credential UPDATE failure")
            return real_execute(self, sql, *args, **kwargs)

        with (
            patch("aiosqlite.Connection.execute", _raising_execute),
            pytest.raises(RuntimeError, match="simulated ext credential UPDATE failure"),
        ):
            await client.post("/api/encryption/rotate")

        assert key_path.read_bytes() == key_before
        assert not next_key_path(key_path).exists()

        direct_conn = await aiosqlite.connect(str(tmp_path / "test.db"))
        direct_conn.row_factory = aiosqlite.Row
        try:
            async with direct_conn.execute(
                "SELECT secret FROM agent_external_credentials WHERE identifier = ?",
                ("ext_rollbackidentifier",),
            ) as cur:
                assert (await cur.fetchone())["secret"] == ct_before
        finally:
            await direct_conn.close()


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
        # F5 L01.5: short-circuit get_model_capabilities so we don't fall
        # through to show_model's mocked-incomplete .post() chain, which
        # left auto-AsyncMock coroutines un-awaited (RuntimeWarning at
        # ollama_api.py:123 resp.json() returning a coroutine, since
        # AsyncMock auto-attributes are AsyncMocks). The dangling coroutine
        # wedged pytest-asyncio's loop teardown for ~90s on every broad
        # pytest run since F1. See mission KI "post-summary teardown wedge".
        #
        # F4 L5 (M10) AsyncMock-warning closure: F6.5 L04 added a sibling
        # ``get_model_context_length`` call in ``list_provider_models``
        # that ALSO falls through to ``show_model``'s mocked-incomplete
        # ``.post()`` chain. The F5 L01.5 short-circuit closed only the
        # capabilities path; the context-length path kept emitting
        # ``AsyncMockMixin._execute_mock_call was never awaited`` warnings.
        # Short-circuit context-length too — same shape, returning None
        # is fail-open (the chip just doesn't render).
        with (
            patch("the_one.interfaces.web.api.httpx.AsyncClient") as mock_httpx_client,
            patch(
                "the_one.interfaces.web.api.ollama_api.get_model_capabilities",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "the_one.interfaces.web.api.ollama_api.get_model_context_length",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
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
        assert models[0]["context_length"] == 128000

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
        # Catalog-sourced per model: claude-sonnet-4-20250514 is 200k per models.dev
        # (the old hand-authored seed over-reported via a claude-sonnet-4 prefix at 1M;
        # the regenerated authoritative seed carries the correct 200k value).
        # claude-haiku-4-20250514 is absent → honest null (UI renders no chip).
        assert models[0]["context_length"] == 200000
        assert models[1]["context_length"] is None

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

_LIBRARY_HTML_FIXTURE = Path(__file__).parent / "fixtures" / "ollama_library_excerpt.html"


class TestOllamaLibrarySearch:
    """Tests for GET /api/ollama-library/search and /size (the thin routes)."""

    @pytest.fixture(autouse=True)
    def _reset_catalog(self, tmp_path):
        from the_one.llm import ollama_library

        ollama_library._reset_for_tests(cache_path=tmp_path / "ollama-sizes.json")
        yield
        ollama_library._reset_for_tests(cache_path=None)

    def _mock_httpx(
        self,
        tags: list[str] | Exception,
        html: str | Exception | None = None,
        manifests: dict[str, int] | None = None,
    ):
        """Route each upstream URL explicitly through ``httpx.MockTransport``.

        ``tags`` is the ``/api/tags`` name list (or an exception to raise); ``html`` the
        ``/library`` page (``None`` or an exception means that source fails);
        ``manifests`` maps ``name:tag`` to a registry status (default 200 with 1000 B).
        Patches the catalog module's client factory, not the global ``httpx`` module.
        """
        manifests = manifests or {}

        def handler(request: httpx.Request) -> httpx.Response:
            url = request.url
            if url.host == "ollama.com" and url.path == "/library":
                if html is None:
                    return httpx.Response(500)
                if isinstance(html, Exception):
                    raise html
                return httpx.Response(200, text=html)
            if url.host == "ollama.com" and url.path == "/api/tags":
                if isinstance(tags, Exception):
                    raise tags
                return httpx.Response(200, json={"models": [{"name": n} for n in tags]})
            m = re.fullmatch(r"/v2/library/([^/]+)/manifests/([^/]+)", url.path)
            assert url.host == "registry.ollama.ai" and m, f"unexpected request {url}"
            code = manifests.get(f"{m.group(1)}:{m.group(2)}", 200)
            if code != 200:
                return httpx.Response(code)
            return httpx.Response(200, json={"config": {"size": 485}, "layers": [{"size": 1000}]})

        real = httpx.AsyncClient
        return patch(
            "the_one.llm.ollama_library._new_client",
            lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
        )

    async def test_new_shape_and_model_name_sort(self, client: AsyncClient) -> None:
        html = _LIBRARY_HTML_FIXTURE.read_text()
        with self._mock_httpx([], html=html):
            resp = await client.get("/api/ollama-library/search")
        assert resp.status_code == 200
        data = resp.json()
        assert data["loading"] is False
        names = [m["name"] for m in data["models"]]
        for m in data["models"]:
            assert set(m) == {"name", "size", "status"}
        # `1b` before `12b` (tag order kept), models grouped alphabetically.
        assert names.index("gemma3:1b") < names.index("gemma3:12b")
        assert names.index("gemma3:27b") < names.index("llama3.2:1b")
        by_name = {m["name"]: m for m in data["models"]}
        assert by_name["llama3.2:3b"] == {"name": "llama3.2:3b", "size": 1485, "status": "ok"}

    async def test_sort_does_not_interleave_prefixed_models(self, client: AsyncClient) -> None:
        html = (
            '<li  class="flex items-baseline"><a href="/library/llama3.2-vision">'
            '<span class="text-blue-600">11b</span></a></li>'
            '<li  class="flex items-baseline"><a href="/library/llama3.2">'
            '<span class="text-blue-600">1b</span><span class="text-blue-600">3b</span></a></li>'
        )
        with self._mock_httpx([], html=html):
            resp = await client.get("/api/ollama-library/search")
        assert [m["name"] for m in resp.json()["models"]] == [
            "llama3.2:1b",
            "llama3.2:3b",
            "llama3.2-vision:11b",
        ]

    async def test_cloud_missing_and_unknown_statuses(self, client: AsyncClient) -> None:
        html = _LIBRARY_HTML_FIXTURE.read_text()
        manifests = {"kimi-k3:latest": 404, "qwen3:0.6b": 404, "qwen3:1.7b": 503}
        with self._mock_httpx(["kimi-k3"], html=html, manifests=manifests):
            resp = await client.get("/api/ollama-library/search")
        by_name = {m["name"]: m for m in resp.json()["models"]}
        assert by_name["kimi-k3"]["status"] == "cloud" and by_name["kimi-k3"]["size"] is None
        assert by_name["qwen3:0.6b"]["status"] == "missing"
        assert by_name["qwen3:1.7b"]["status"] == "unknown"

    async def test_q_filters_case_insensitively(self, client: AsyncClient) -> None:
        with self._mock_httpx([], html=_LIBRARY_HTML_FIXTURE.read_text()):
            resp = await client.get("/api/ollama-library/search?q=GEMMA3")
        names = [m["name"] for m in resp.json()["models"]]
        assert names and all(n.startswith("gemma3:") for n in names)

    async def test_results_not_capped(self, client: AsyncClient) -> None:
        # Issue #93: every matching model must be reachable.
        html = "".join(
            f'<li  class="flex items-baseline"><a href="/library/model-x-{i:03d}">x</a></li>'
            for i in range(50)
        )
        with self._mock_httpx([], html=html):
            resp = await client.get("/api/ollama-library/search?q=model-x")
        assert len(resp.json()["models"]) == 50

    async def test_second_search_is_served_from_the_cache(self, client: AsyncClient) -> None:
        html = _LIBRARY_HTML_FIXTURE.read_text()
        with self._mock_httpx([], html=html) as _:
            await client.get("/api/ollama-library/search")
        # No patch active: a warm cache must not need the network at all.
        resp = await client.get("/api/ollama-library/search?q=qwen3")
        assert resp.status_code == 200
        assert resp.json()["models"] and resp.json()["loading"] is False

    async def test_both_sources_down_returns_empty(self, client: AsyncClient) -> None:
        with self._mock_httpx(ConnectionError("refused"), html=ConnectionError("down")):
            resp = await client.get("/api/ollama-library/search")
        assert resp.status_code == 200
        assert resp.json() == {"loading": False, "models": []}

    async def test_page_down_serves_api_tags_names(self, client: AsyncClient) -> None:
        with self._mock_httpx(["kimi-k3", "gpt-oss:20b"], html=None):
            resp = await client.get("/api/ollama-library/search")
        assert sorted(m["name"] for m in resp.json()["models"]) == ["gpt-oss:20b", "kimi-k3"]

    async def test_size_route_ok_and_bare_name_echo(self, client: AsyncClient) -> None:
        with self._mock_httpx([]):
            resp = await client.get("/api/ollama-library/size?model=nomic-embed-text")
        assert resp.status_code == 200
        assert resp.json() == {"name": "nomic-embed-text", "size": 1485, "status": "ok"}

    async def test_size_route_unknown_status(self, client: AsyncClient) -> None:
        with self._mock_httpx([], manifests={"m:1b": 503}):
            resp = await client.get("/api/ollama-library/size?model=m:1b")
        assert resp.status_code == 200
        assert resp.json() == {"name": "m:1b", "size": None, "status": "unknown"}

    @pytest.mark.parametrize("model", ["", "A/b", "x:a b", "ns/x:1b", "x:"])
    async def test_size_route_rejects_invalid_model_with_string_detail(
        self, client: AsyncClient, model: str
    ) -> None:
        resp = await client.get("/api/ollama-library/size", params={"model": model})
        assert resp.status_code == 422
        assert isinstance(resp.json()["detail"], str)


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

    async def test_returns_6_types_when_dev_mode_off(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        data = resp.json()
        values = [t["value"] for t in data]
        # anthropic-plan is NOT dev-gated (M19 F01 L03) — present with dev off.
        assert set(values) == {
            "ollama",
            "openai-compatible",
            "openai",
            "anthropic",
            "anthropic-plan",
            "openrouter",
        }
        # Each entry has the expected shape
        for entry in data:
            assert set(entry.keys()) == {"value", "label"}

    async def test_anthropic_plan_label_is_parenthetical(self, client: AsyncClient) -> None:
        """The picker label follows the "Mock (dev)" parenthetical precedent."""
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        labels = {t["value"]: t["label"] for t in resp.json()}
        assert labels["anthropic-plan"] == "Anthropic (Plan)"

    async def test_returns_7_types_when_dev_mode_on(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        values = [t["value"] for t in resp.json()]
        assert "mock" in values
        assert "openrouter" in values
        assert "anthropic-plan" in values
        assert len(values) == 7

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
    async def test_create_strips_whitespace_round_trip(self, client: AsyncClient) -> None:
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
    async def test_create_whitespace_only_stored_as_none(self, client: AsyncClient) -> None:
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

    async def test_no_key_returns_warning_not_ok(self, client: AsyncClient, monkeypatch) -> None:
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

    async def test_key_set_returns_ok(self, client: AsyncClient, monkeypatch) -> None:
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

    async def test_timeout_maps_to_504(self, client: AsyncClient, monkeypatch) -> None:
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


# ── anthropic-plan secrets contract + OAuth endpoints (M19 F01 L01) ──────


@pytest.fixture
async def plan_env(tmp_path):
    """Like ``client`` but also exposes the DB connection and encryptor so
    tests can assert on ciphertext-at-rest / stored token values (which the
    API deliberately never returns)."""
    db_path = tmp_path / "test.db"

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

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
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
            yield SimpleNamespace(client=c, conn=conn, encryptor=test_encryptor)

    await conn.close()


_PLAN_PROVIDER_BODY = {
    "name": "Claude Plan",
    "type": "anthropic-plan",
    "base_url": "https://api.anthropic.com",
}


def _plan_token_set(**overrides):
    from the_one.llm.anthropic_oauth import TokenSet

    defaults = {
        "access_token": "sk-ant-oat01-planaccess",
        "refresh_token": "sk-ant-ort01-planrefresh",
        "token_expires_at": 1785300000,
        "scope": "org:create_api_key user:profile user:inference",
        "token_type": "Bearer",
    }
    defaults.update(overrides)
    return TokenSet(**defaults)


async def _read_stored_secrets(env, provider_id: str) -> dict:
    import json as _json

    async with env.conn.execute(
        "SELECT secrets FROM llm_providers WHERE id = ?", (provider_id,)
    ) as cur:
        row = await cur.fetchone()
    raw = row["secrets"]
    if raw == "{}":
        return {}
    return _json.loads(env.encryptor.decrypt(raw))


async def _signed_in_plan_provider(env, token_set=None) -> str:
    """Create a plan provider and complete /oauth/start + /oauth/code with a
    mocked token-endpoint exchange. Returns the provider id."""
    create = await env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
    assert create.status_code == 201, create.text
    provider_id = create.json()["id"]

    start = await env.client.post(f"/api/providers/{provider_id}/oauth/start")
    assert start.status_code == 200, start.text

    exchange = AsyncMock(return_value=token_set or _plan_token_set())
    with patch("the_one.llm.anthropic_oauth.exchange_code", exchange):
        code_resp = await env.client.post(
            f"/api/providers/{provider_id}/oauth/code", json={"code": "consent-code-1"}
        )
    assert code_resp.status_code == 200, code_resp.text
    return provider_id


class TestPlanProviderSecretsContract:
    async def test_create_forces_empty_secrets(self, plan_env) -> None:
        """POST with a client-supplied secrets payload stores {} — token
        material cannot enter via create."""
        resp = await plan_env.client.post(
            "/api/providers",
            json={
                **_PLAN_PROVIDER_BODY,
                "secrets": {"access_token": "smuggled", "refresh_token": "smuggled2"},
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "secrets" not in body
        assert body["oauth_active"] is False
        assert await _read_stored_secrets(plan_env, body["id"]) == {}

    async def test_get_strips_secrets_and_exposes_oauth_active(self, plan_env) -> None:
        provider_id = await _signed_in_plan_provider(plan_env)
        resp = await plan_env.client.get(f"/api/providers/{provider_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "secrets" not in body
        assert body["oauth_active"] is True
        # No token substring anywhere in the response.
        assert "planaccess" not in resp.text
        assert "planrefresh" not in resp.text

    async def test_oauth_active_false_for_legacy_types(self, plan_env) -> None:
        """The field appears for ALL providers and is False for non-plan
        types (frontend ignores unknown fields today)."""
        resp = await plan_env.client.post(
            "/api/providers",
            json={
                "name": "Anthropic API",
                "type": "anthropic",
                "base_url": "https://api.anthropic.com",
                "api_key": "sk-ant-key",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["oauth_active"] is False
        assert "secrets" not in body

        listed = await plan_env.client.get("/api/providers")
        for item in listed.json():
            assert "secrets" not in item
            assert item["oauth_active"] is False

    async def test_oauth_active_requires_both_tokens(self, plan_env) -> None:
        """Pin the chosen rule: access_token AND refresh_token (stricter
        than MCP's any-key rule)."""
        provider_id = await _signed_in_plan_provider(
            plan_env, token_set=_plan_token_set(refresh_token=None)
        )
        resp = await plan_env.client.get(f"/api/providers/{provider_id}")
        assert resp.json()["oauth_active"] is False

    async def test_put_without_secrets_preserves_managed_keys(self, plan_env) -> None:
        provider_id = await _signed_in_plan_provider(plan_env)
        stored_before = await _read_stored_secrets(plan_env, provider_id)

        resp = await plan_env.client.put(
            f"/api/providers/{provider_id}",
            json={**_PLAN_PROVIDER_BODY, "name": "Renamed Plan"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Plan"
        assert resp.json()["oauth_active"] is True
        assert await _read_stored_secrets(plan_env, provider_id) == stored_before

    async def test_put_cannot_overwrite_managed_keys(self, plan_env) -> None:
        provider_id = await _signed_in_plan_provider(plan_env)
        stored_before = await _read_stored_secrets(plan_env, provider_id)

        resp = await plan_env.client.put(
            f"/api/providers/{provider_id}",
            json={
                **_PLAN_PROVIDER_BODY,
                "secrets": {
                    "access_token": "attacker-at",
                    "refresh_token": "attacker-rt",
                    "token_expires_at": 1,
                },
            },
        )
        assert resp.status_code == 200
        assert await _read_stored_secrets(plan_env, provider_id) == stored_before

    async def test_put_cannot_seed_managed_keys(self, plan_env) -> None:
        """A PUT on a never-signed-in provider cannot plant token material."""
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]

        resp = await plan_env.client.put(
            f"/api/providers/{provider_id}",
            json={
                **_PLAN_PROVIDER_BODY,
                "secrets": {"access_token": "seeded", "refresh_token": "seeded2"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["oauth_active"] is False
        assert await _read_stored_secrets(plan_env, provider_id) == {}


class TestPlanOAuthEndpoints:
    async def test_start_returns_authorize_url(self, plan_env) -> None:
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]

        resp = await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")
        assert resp.status_code == 200
        url = resp.json()["authorize_url"]
        assert url.startswith("https://claude.ai/oauth/authorize?")
        assert "client_id=9d1c250a-e61b-44d9-88ed-5944d1962f5e" in url
        assert "code_challenge_method=S256" in url
        assert "state=" in url

    async def test_start_unknown_provider_404(self, plan_env) -> None:
        resp = await plan_env.client.post("/api/providers/nope/oauth/start")
        assert resp.status_code == 404

    async def test_start_non_plan_type_409(self, plan_env) -> None:
        create = await plan_env.client.post(
            "/api/providers",
            json={
                "name": "Anthropic API",
                "type": "anthropic",
                "base_url": "https://api.anthropic.com",
            },
        )
        provider_id = create.json()["id"]
        resp = await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")
        assert resp.status_code == 409
        assert "anthropic-plan" in resp.json()["detail"]

    async def test_code_without_start_409(self, plan_env) -> None:
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        resp = await plan_env.client.post(
            f"/api/providers/{provider_id}/oauth/code", json={"code": "abc"}
        )
        assert resp.status_code == 409
        assert "Start the sign-in flow" in resp.json()["detail"]

    async def test_code_exchange_persists_and_returns_masked_provider(self, plan_env) -> None:
        provider_id = await _signed_in_plan_provider(plan_env)
        stored = await _read_stored_secrets(plan_env, provider_id)
        assert stored["access_token"] == "sk-ant-oat01-planaccess"
        assert stored["refresh_token"] == "sk-ant-ort01-planrefresh"
        assert stored["token_expires_at"] == 1785300000

        resp = await plan_env.client.get(f"/api/providers/{provider_id}")
        assert resp.json()["oauth_active"] is True

    async def test_code_exchange_receives_pending_verifier_and_state(self, plan_env) -> None:
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        start = await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")
        url = start.json()["authorize_url"]

        exchange = AsyncMock(return_value=_plan_token_set())
        with patch("the_one.llm.anthropic_oauth.exchange_code", exchange):
            resp = await plan_env.client.post(
                f"/api/providers/{provider_id}/oauth/code", json={"code": "  the-code  "}
            )
        assert resp.status_code == 200
        args, kwargs = exchange.call_args
        assert args == ("the-code",)
        # The verifier's S256 challenge and the state are the ones in the
        # authorize URL this flow handed out.
        from urllib.parse import parse_qs, urlparse

        from the_one.llm.anthropic_oauth import derive_challenge

        params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert derive_challenge(kwargs["verifier"]) == params["code_challenge"]
        assert kwargs["state"] == params["state"]

    async def test_code_hash_state_form_accepted(self, plan_env) -> None:
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        start = await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")
        from urllib.parse import parse_qs, urlparse

        state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]

        exchange = AsyncMock(return_value=_plan_token_set())
        with patch("the_one.llm.anthropic_oauth.exchange_code", exchange):
            resp = await plan_env.client.post(
                f"/api/providers/{provider_id}/oauth/code",
                json={"code": f"the-code#{state}"},
            )
        assert resp.status_code == 200
        assert exchange.call_args.args == ("the-code",)

    async def test_code_state_mismatch_400_no_exchange(self, plan_env) -> None:
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")

        exchange = AsyncMock(return_value=_plan_token_set())
        with patch("the_one.llm.anthropic_oauth.exchange_code", exchange):
            resp = await plan_env.client.post(
                f"/api/providers/{provider_id}/oauth/code",
                json={"code": "the-code#wrong-state"},
            )
        assert resp.status_code == 400
        exchange.assert_not_called()
        assert await _read_stored_secrets(plan_env, provider_id) == {}

    async def test_repeated_start_invalidates_older_window(self, plan_env) -> None:
        """A second /start replaces the pending state; a code pasted from
        the FIRST window (carrying its state) is rejected with guidance."""
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        first = await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")
        from urllib.parse import parse_qs, urlparse

        first_state = parse_qs(urlparse(first.json()["authorize_url"]).query)["state"][0]
        await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")

        exchange = AsyncMock(return_value=_plan_token_set())
        with patch("the_one.llm.anthropic_oauth.exchange_code", exchange):
            resp = await plan_env.client.post(
                f"/api/providers/{provider_id}/oauth/code",
                json={"code": f"old-code#{first_state}"},
            )
        assert resp.status_code == 400
        assert "most recently opened" in resp.json()["detail"]
        exchange.assert_not_called()

    async def test_invalid_code_surfaces_actionable_400(self, plan_env) -> None:
        from the_one.llm.anthropic_oauth import OAuthExchangeError

        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")

        exchange = AsyncMock(
            side_effect=OAuthExchangeError(
                "OAuth code exchange failed: token endpoint returned HTTP 400.",
                status_code=400,
                body='{"error": "invalid_grant"}',
            )
        )
        with patch("the_one.llm.anthropic_oauth.exchange_code", exchange):
            resp = await plan_env.client.post(
                f"/api/providers/{provider_id}/oauth/code", json={"code": "expired-code"}
            )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "restart the sign-in flow" in detail

    async def test_empty_code_422(self, plan_env) -> None:
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")
        resp = await plan_env.client.post(
            f"/api/providers/{provider_id}/oauth/code", json={"code": "   "}
        )
        assert resp.status_code == 422

    async def test_provider_deleted_between_start_and_code_404(self, plan_env) -> None:
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")
        delete = await plan_env.client.delete(f"/api/providers/{provider_id}")
        assert delete.status_code == 200

        resp = await plan_env.client.post(
            f"/api/providers/{provider_id}/oauth/code", json={"code": "abc"}
        )
        assert resp.status_code == 404


class TestPlanSecretsRotation:
    async def test_rotation_preserves_plan_tokens(self, plan_env) -> None:
        """llm_providers.secrets is the fourth rotation surface: stored plan
        tokens must decrypt under the post-rotation key. (If rotation missed
        the surface, the tolerant decrypt would read {} and oauth_active
        would flip false — and the raw-DB assertion would fail outright.)"""
        provider_id = await _signed_in_plan_provider(plan_env)
        stored_before = await _read_stored_secrets(plan_env, provider_id)
        assert stored_before["access_token"] == "sk-ant-oat01-planaccess"

        resp = await plan_env.client.post("/api/encryption/rotate")
        assert resp.status_code == 200

        # install_key() mutated the shared encryptor to the new key, so this
        # decrypts the raw column under the POST-rotation key.
        stored_after = await _read_stored_secrets(plan_env, provider_id)
        assert stored_after == stored_before

        get_resp = await plan_env.client.get(f"/api/providers/{provider_id}")
        assert get_resp.json()["oauth_active"] is True

    async def test_rotation_normalizes_plaintext_residue_row(self, plan_env) -> None:
        """A migration-residue row (plaintext '{}') survives rotation via the
        tolerant decrypt and is normalized to ciphertext for {}."""
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        # Simulate v33-migrated residue: plaintext '{}' in the raw column.
        await plan_env.conn.execute(
            "UPDATE llm_providers SET secrets = '{}' WHERE id = ?", (provider_id,)
        )
        await plan_env.conn.commit()

        resp = await plan_env.client.post("/api/encryption/rotate")
        assert resp.status_code == 200

        async with plan_env.conn.execute(
            "SELECT secrets FROM llm_providers WHERE id = ?", (provider_id,)
        ) as cur:
            raw = (await cur.fetchone())["secrets"]
        assert raw != "{}"
        assert plan_env.encryptor.decrypt(raw) == "{}"

        get_resp = await plan_env.client.get(f"/api/providers/{provider_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["oauth_active"] is False


# ── anthropic-plan /test, /models, reset + eviction (M19 F01 L02) ────────


def _plan_repo(env):
    """Real repository over the plan_env conn/encryptor — the same rows the
    API handlers see."""
    from the_one.db.repositories import LLMProviderRepository

    return LLMProviderRepository(env.conn, env.encryptor)


@pytest.fixture
def plan_source_env(plan_env, monkeypatch):
    """plan_env + the credential source wired to the SAME test DB.

    The source's lazy ``_provider_repo`` normally builds over the singleton
    connection; point it at the fixture repo, and reset the process-wide
    source registry around the test.
    """
    from the_one.llm import plan_credentials

    repo = _plan_repo(plan_env)

    async def _test_repo():
        return repo

    monkeypatch.setattr(plan_credentials, "_provider_repo", _test_repo)
    plan_credentials._reset_for_tests()
    yield plan_env
    plan_credentials._reset_for_tests()


def _fresh_plan_token_set():
    import time as _time

    return _plan_token_set(token_expires_at=int(_time.time()) + 3600)


class TestPlanConnectionTest:
    """POST /providers/{id}/test for anthropic-plan (DD-5 + /test contract)."""

    async def test_success_uses_accessor_token(self, plan_source_env) -> None:
        env = plan_source_env
        provider_id = await _signed_in_plan_provider(env, token_set=_fresh_plan_token_set())
        mock_mod = _mock_anthropic_module()
        mock_mod.AsyncAnthropic.return_value.models.list = AsyncMock(
            return_value=MagicMock(data=[])
        )
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await env.client.post(f"/api/providers/{provider_id}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "plan" in resp.json()["detail"].lower()
        # Bearer mode with the fresh accessor token + OAuth beta header.
        _, kwargs = mock_mod.AsyncAnthropic.call_args
        assert kwargs["auth_token"] == "sk-ant-oat01-planaccess"
        assert kwargs["api_key"] is None
        assert kwargs["default_headers"] == {"anthropic-beta": "oauth-2025-04-20"}

    async def test_reauth_required_is_200_with_status(self, plan_source_env) -> None:
        """Established /test contract: HTTP 200 + status field with the
        distinct ``reauth_required`` value and an actionable detail — NOT a
        4xx (deliberate alignment with the 200-on-provider-failure family)."""
        env = plan_source_env
        create = await env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]  # no tokens stored

        mock_mod = _mock_anthropic_module()
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await env.client.post(f"/api/providers/{provider_id}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "reauth_required"
        assert "Administration" in body["detail"]
        mock_mod.AsyncAnthropic.assert_not_called()

    async def test_upstream_error_is_status_error(self, plan_source_env) -> None:
        env = plan_source_env
        provider_id = await _signed_in_plan_provider(env, token_set=_fresh_plan_token_set())
        mock_mod = _mock_anthropic_module()
        mock_mod.AsyncAnthropic.return_value.models.list = AsyncMock(
            side_effect=mock_mod.AnthropicError("plan token rejected")
        )
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await env.client.post(f"/api/providers/{provider_id}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
        assert "plan token rejected" in resp.json()["detail"]


class TestPlanModelDiscovery:
    """GET /providers/{id}/models for anthropic-plan (DD-5)."""

    async def test_live_listing_with_accessor_token(self, plan_source_env) -> None:
        env = plan_source_env
        provider_id = await _signed_in_plan_provider(env, token_set=_fresh_plan_token_set())
        model_a = SimpleNamespace(id="claude-sonnet-4-20250514", display_name="Claude Sonnet 4")
        mock_mod = _mock_anthropic_module()
        mock_mod.AsyncAnthropic.return_value.models.list = AsyncMock(
            return_value=MagicMock(data=[model_a])
        )
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await env.client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert models == [
            {
                "id": "claude-sonnet-4-20250514",
                "name": "Claude Sonnet 4",
                # Context window resolved via provider name "anthropic".
                "context_length": 200000,
            }
        ]
        _, kwargs = mock_mod.AsyncAnthropic.call_args
        assert kwargs["auth_token"] == "sk-ant-oat01-planaccess"

    async def test_live_failure_falls_back_to_static_catalog(self, plan_source_env) -> None:
        env = plan_source_env
        provider_id = await _signed_in_plan_provider(env, token_set=_fresh_plan_token_set())
        mock_mod = _mock_anthropic_module()
        mock_mod.AsyncAnthropic.return_value.models.list = AsyncMock(
            side_effect=mock_mod.AnthropicError("plan tokens can't list models")
        )
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await env.client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 200
        models = resp.json()

        from the_one.llm.model_catalog import models_for

        catalog = models_for("anthropic")
        assert catalog, "static anthropic catalog section must not be empty"
        assert models == [
            {"id": mid, "name": mid, "context_length": window}
            for mid, window in sorted(catalog.items())
        ]

    async def test_reauth_required_also_serves_static_fallback(self, plan_source_env) -> None:
        """The Studio picker always has options — even when the provider
        needs re-auth, /models serves the catalog fallback (the re-auth
        affordance lives on /test + oauth_active, not here)."""
        env = plan_source_env
        create = await env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]  # no tokens stored

        mock_mod = _mock_anthropic_module()
        with patch.dict(sys.modules, {"anthropic": mock_mod}):
            resp = await env.client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 200
        assert len(resp.json()) > 0
        mock_mod.AsyncAnthropic.assert_not_called()


class TestPlanOAuthReset:
    """DELETE /providers/{id}/oauth — the Leg-3 reset control's backend."""

    async def test_reset_clears_managed_keys_and_flips_oauth_active(self, plan_env) -> None:
        provider_id = await _signed_in_plan_provider(plan_env)
        assert (await _read_stored_secrets(plan_env, provider_id))["access_token"]

        resp = await plan_env.client.delete(f"/api/providers/{provider_id}/oauth")
        assert resp.status_code == 200
        body = resp.json()
        assert body["oauth_active"] is False
        assert "secrets" not in body
        assert await _read_stored_secrets(plan_env, provider_id) == {}

        get_resp = await plan_env.client.get(f"/api/providers/{provider_id}")
        assert get_resp.json()["oauth_active"] is False

    async def test_reset_preserves_unmanaged_secret_keys(self, plan_env) -> None:
        """The reset is surgical: only OAuth-managed keys are cleared."""
        provider_id = await _signed_in_plan_provider(plan_env)
        repo = _plan_repo(plan_env)
        stored = await _read_stored_secrets(plan_env, provider_id)
        stored["future_unmanaged_key"] = "survives"
        await repo.update_secrets(provider_id, stored)

        resp = await plan_env.client.delete(f"/api/providers/{provider_id}/oauth")
        assert resp.status_code == 200
        assert await _read_stored_secrets(plan_env, provider_id) == {
            "future_unmanaged_key": "survives"
        }

    async def test_reset_evicts_pending_verifier(self, plan_env) -> None:
        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")

        resp = await plan_env.client.delete(f"/api/providers/{provider_id}/oauth")
        assert resp.status_code == 200

        code_resp = await plan_env.client.post(
            f"/api/providers/{provider_id}/oauth/code", json={"code": "abc"}
        )
        assert code_resp.status_code == 409  # no pending flow anymore

    async def test_reset_evicts_credential_source(self, plan_env) -> None:
        from the_one.llm import plan_credentials

        provider_id = await _signed_in_plan_provider(plan_env)
        plan_credentials._reset_for_tests()
        before = plan_credentials.get_credential_source(provider_id)
        resp = await plan_env.client.delete(f"/api/providers/{provider_id}/oauth")
        assert resp.status_code == 200
        after = plan_credentials.get_credential_source(provider_id)
        assert before is not after
        plan_credentials._reset_for_tests()

    async def test_reset_unknown_provider_404(self, plan_env) -> None:
        resp = await plan_env.client.delete("/api/providers/nope/oauth")
        assert resp.status_code == 404

    async def test_reset_non_plan_type_409(self, plan_env) -> None:
        create = await plan_env.client.post(
            "/api/providers",
            json={
                "name": "Anthropic API",
                "type": "anthropic",
                "base_url": "https://api.anthropic.com",
            },
        )
        provider_id = create.json()["id"]
        resp = await plan_env.client.delete(f"/api/providers/{provider_id}/oauth")
        assert resp.status_code == 409


class TestPlanCredentialSourceEvictionWiring:
    """DD-3 invalidation contract: PUT, DELETE, and a fresh /oauth/code
    exchange each evict the cached credential source."""

    async def test_put_evicts_source(self, plan_env) -> None:
        from the_one.llm import plan_credentials

        provider_id = await _signed_in_plan_provider(plan_env)
        plan_credentials._reset_for_tests()
        before = plan_credentials.get_credential_source(provider_id)
        resp = await plan_env.client.put(
            f"/api/providers/{provider_id}", json={"name": "Renamed Plan"}
        )
        assert resp.status_code == 200
        assert plan_credentials.get_credential_source(provider_id) is not before
        plan_credentials._reset_for_tests()

    async def test_delete_evicts_source(self, plan_env) -> None:
        from the_one.llm import plan_credentials

        provider_id = await _signed_in_plan_provider(plan_env)
        plan_credentials._reset_for_tests()
        before = plan_credentials.get_credential_source(provider_id)
        resp = await plan_env.client.delete(f"/api/providers/{provider_id}")
        assert resp.status_code == 200
        assert plan_credentials.get_credential_source(provider_id) is not before
        plan_credentials._reset_for_tests()

    async def test_fresh_sign_in_evicts_source(self, plan_env) -> None:
        """A successful /oauth/code exchange over a cached source evicts it,
        so the next consumer reads the just-persisted token set instead of
        relying on re-read adoption."""
        from the_one.llm import plan_credentials

        create = await plan_env.client.post("/api/providers", json=_PLAN_PROVIDER_BODY)
        provider_id = create.json()["id"]
        plan_credentials._reset_for_tests()
        before = plan_credentials.get_credential_source(provider_id)

        await plan_env.client.post(f"/api/providers/{provider_id}/oauth/start")
        exchange = AsyncMock(return_value=_plan_token_set())
        with patch("the_one.llm.anthropic_oauth.exchange_code", exchange):
            resp = await plan_env.client.post(
                f"/api/providers/{provider_id}/oauth/code", json={"code": "consent-code"}
            )
        assert resp.status_code == 200
        assert plan_credentials.get_credential_source(provider_id) is not before
        plan_credentials._reset_for_tests()


class TestCreateProviderValidation:
    """Squawks 0112 / 0081: a missing field is a 422, never a 500."""

    async def test_missing_base_url_returns_422(self, client: AsyncClient) -> None:
        resp = await client.post("/api/providers", json={"name": "p", "type": "openai"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, list)
        assert any("base_url" in item["loc"] for item in detail)

    async def test_422_does_not_echo_api_key(self, client: AsyncClient) -> None:
        secret = "sk-super-secret-value-123456"
        resp = await client.post(
            "/api/providers", json={"name": "p", "type": "openai", "api_key": secret}
        )
        assert resp.status_code == 422
        assert secret not in resp.text
