"""Async SQLite connection manager — singleton, WAL mode, foreign keys."""

from __future__ import annotations

import aiosqlite

from the_one.config import settings

_connection: aiosqlite.Connection | None = None


async def get_connection() -> aiosqlite.Connection:
    """Return the singleton database connection, creating it if needed."""
    global _connection
    if _connection is None:
        settings.ensure_dirs()
        _connection = await aiosqlite.connect(str(settings.db_path))
        _connection.row_factory = aiosqlite.Row
        await _connection.execute("PRAGMA journal_mode=WAL")
        await _connection.execute("PRAGMA foreign_keys=ON")
    return _connection


async def close_connection() -> None:
    """Close the singleton connection if open."""
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None


async def init_db() -> None:
    """Initialize the database: ensure connection and apply schema."""
    from the_one.db.schema import ensure_schema

    conn = await get_connection()
    await ensure_schema(conn)
