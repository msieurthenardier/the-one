"""Tests for the_one.db.key_reconcile — the startup rotation-sidecar reconcile."""

from __future__ import annotations

import aiosqlite
import pytest
from cryptography.fernet import Fernet

from the_one.db.key_reconcile import reconcile_pending_key, sample_ciphertexts
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor


@pytest.fixture
async def conn():
    connection = await aiosqlite.connect(":memory:")
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


class TestSampleCiphertexts:
    async def test_returns_values_from_every_present_corpus(self, conn) -> None:
        key = Fernet.generate_key()
        enc = Encryptor(key)
        repo = MCPSourceRepository(conn, enc)
        await repo.create(MCPSource(id="m1", name="mcp-1", type="stdio", secrets={"token": "shh"}))

        samples = await sample_ciphertexts(conn)
        assert len(samples) >= 1
        # Every returned sample decrypts under this key (the row we seeded).
        for s in samples:
            enc.decrypt(s)

    async def test_skips_missing_tables(self) -> None:
        # A bare connection with only `mcp_sources` created — every other
        # corpus table is absent and must be skipped, not raise.
        connection = await aiosqlite.connect(":memory:")
        connection.row_factory = aiosqlite.Row
        await connection.execute("CREATE TABLE mcp_sources (id TEXT PRIMARY KEY, secrets TEXT)")
        await connection.execute(
            "INSERT INTO mcp_sources (id, secrets) VALUES ('m1', 'only-this-one')"
        )
        await connection.commit()

        samples = await sample_ciphertexts(connection)
        assert samples == ["only-this-one"]
        await connection.close()


class TestReconcilePendingKey:
    async def test_absent_without_pending_key_no_queries(self, conn) -> None:
        key = Fernet.generate_key()
        enc = Encryptor(key)
        assert enc.pending_key is None

        outcome = await reconcile_pending_key(conn, enc)
        assert outcome == "absent"

    async def test_promotes_when_a_row_decrypts_under_pending(self, conn, tmp_path) -> None:
        key_path = tmp_path / "encryption.key"
        old_key = Fernet.generate_key()
        key_path.write_bytes(old_key)
        enc = Encryptor(old_key, key_path=key_path)

        new_key = Fernet.generate_key()
        enc.stage_pending_key(new_key)

        # Seed a row already re-encrypted under the new (pending) key —
        # simulating a commit that landed before the crash.
        new_enc = Encryptor(new_key)
        repo = MCPSourceRepository(conn, new_enc)
        await repo.create(MCPSource(id="m1", name="mcp-1", type="stdio", secrets={"token": "shh"}))

        outcome = await reconcile_pending_key(conn, enc)
        assert outcome == "promoted"
        assert enc.pending_key is None
        assert key_path.read_bytes() == new_key
