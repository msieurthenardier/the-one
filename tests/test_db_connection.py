"""Tests for database connection manager and schema creation."""

from __future__ import annotations

import os
import stat
from unittest.mock import patch

import pytest


@pytest.fixture
async def db_path(tmp_path):
    """Provide a temporary DB path and clean up connection after test."""
    path = tmp_path / "test.db"
    with patch("the_one.db.connection.settings") as mock_settings:
        mock_settings.db_path = path
        mock_settings.ensure_dirs = lambda: None
        # Reset singleton
        import the_one.db.connection as conn_mod

        conn_mod._connection = None
        yield path
        await conn_mod.close_connection()


class TestConnectionManager:
    async def test_get_connection_creates_db(self, db_path) -> None:
        from the_one.db.connection import get_connection

        conn = await get_connection()
        assert conn is not None
        assert db_path.exists()

    async def test_get_connection_returns_singleton(self, db_path) -> None:
        from the_one.db.connection import get_connection

        conn1 = await get_connection()
        conn2 = await get_connection()
        assert conn1 is conn2

    async def test_wal_mode_enabled(self, db_path) -> None:
        from the_one.db.connection import get_connection

        conn = await get_connection()
        async with conn.execute("PRAGMA journal_mode") as cur:
            row = await cur.fetchone()
            assert row[0] == "wal"

    async def test_foreign_keys_enabled(self, db_path) -> None:
        from the_one.db.connection import get_connection

        conn = await get_connection()
        async with conn.execute("PRAGMA foreign_keys") as cur:
            row = await cur.fetchone()
            assert row[0] == 1

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    async def test_db_file_permissions(self, db_path) -> None:
        """Squawk 0011 / GH #169: a freshly-created DB lands at 0o600, not
        the process umask (0o644 observed pre-fix)."""
        from the_one.db.connection import get_connection

        await get_connection()
        assert stat.S_IMODE(os.stat(db_path).st_mode) == 0o600

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    async def test_new_wal_shm_sidecars_inherit_0600(self, db_path) -> None:
        """SQLite creates -wal/-shm by copying the main DB file's mode bits
        (not the process umask), so once the DB itself is 0o600 the sidecars
        a real write creates come out 0o600 too — no separate handling needed
        for the fresh-install path."""
        from the_one.db.connection import get_connection

        conn = await get_connection()
        # Sidecars are created lazily on first write, not by PRAGMA alone.
        await conn.execute("CREATE TABLE IF NOT EXISTS _squawk_0011_probe (a)")
        await conn.commit()

        wal_path = db_path.with_name(db_path.name + "-wal")
        shm_path = db_path.with_name(db_path.name + "-shm")
        assert wal_path.exists()
        assert shm_path.exists()
        assert stat.S_IMODE(os.stat(wal_path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(shm_path).st_mode) == 0o600

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    async def test_tightens_existing_0644_wal_shm_sidecars(self, db_path) -> None:
        """Squawk 0011 / GH #169: leftover 0o644 -wal/-shm sidecars from a
        pre-fix install are reconciled to 0o600 by `get_connection()`'s
        post-PRAGMA reconcile pass."""
        from the_one.db.connection import get_connection

        db_path.touch()
        os.chmod(db_path, 0o644)
        wal_path = db_path.with_name(db_path.name + "-wal")
        shm_path = db_path.with_name(db_path.name + "-shm")
        wal_path.touch()
        shm_path.touch()
        os.chmod(wal_path, 0o644)
        os.chmod(shm_path, 0o644)

        await get_connection()

        assert stat.S_IMODE(os.stat(wal_path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(shm_path).st_mode) == 0o600

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    async def test_tightens_existing_0644_db_file(self, db_path) -> None:
        """Squawk 0011 / GH #169: a pre-fix install's world-readable (0o644)
        DB file is tightened to 0o600 on open, not just left alone because
        it already exists."""
        from the_one.db.connection import get_connection

        db_path.touch()
        os.chmod(db_path, 0o644)
        assert stat.S_IMODE(os.stat(db_path).st_mode) == 0o644

        await get_connection()

        assert stat.S_IMODE(os.stat(db_path).st_mode) == 0o600

    async def test_close_connection(self, db_path) -> None:
        import the_one.db.connection as conn_mod
        from the_one.db.connection import close_connection, get_connection

        await get_connection()
        await close_connection()
        assert conn_mod._connection is None


class TestSchemaCreation:
    async def test_ensure_schema_creates_tables(self, db_path) -> None:
        from the_one.db.connection import get_connection
        from the_one.db.schema import ensure_schema

        conn = await get_connection()
        await ensure_schema(conn)

        # Check all expected tables exist
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cur:
            tables = [row[0] for row in await cur.fetchall()]
        for expected in (
            "agents",
            "knowledge_bases",
            "kb_items",
            "mcp_sources",
            "chat_sessions",
            "schema_version",
        ):
            assert expected in tables

    async def test_schema_version_recorded(self, db_path) -> None:
        from the_one.db.connection import get_connection
        from the_one.db.schema import CURRENT_VERSION, ensure_schema

        conn = await get_connection()
        await ensure_schema(conn)

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
            assert row[0] == CURRENT_VERSION

    async def test_idempotent_schema_application(self, db_path) -> None:
        from the_one.db.connection import get_connection
        from the_one.db.schema import ensure_schema

        conn = await get_connection()
        await ensure_schema(conn)
        # Running again should not raise
        await ensure_schema(conn)
