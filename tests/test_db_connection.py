"""Tests for database connection manager and schema creation."""

from __future__ import annotations

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
        for expected in ("agents", "knowledge_bases", "kb_items", "mcp_sources",
                         "chat_sessions", "schema_version"):
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
