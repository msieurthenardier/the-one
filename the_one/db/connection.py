"""Async SQLite connection manager — singleton, WAL mode, foreign keys."""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

from the_one.config import settings

_connection: aiosqlite.Connection | None = None


def _create_or_tighten_db_file(db_path: Path) -> None:
    """Ensure *db_path* exists and is mode ``0o600`` before ``aiosqlite`` opens it.

    Squawk 0011 / GH #169: the process umask otherwise leaves a fresh DB file
    world-readable (``0o644`` observed). ``os.open(..., O_CREAT, 0o600)``
    creates a new file at ``0o600`` directly — no write-then-chmod window —
    mirroring the no-window pattern ``the_one/api_credential.py`` uses.
    ``O_CREAT`` alone (no ``O_EXCL``) is deliberate: a pre-existing DB file
    from before this fix must be reused, not replaced, so the explicit
    ``os.chmod`` below also tightens that case (``O_CREAT`` doesn't change
    the mode of a file that already exists). On Windows ``os.chmod`` is a
    no-op against ACLs — see ``SECURITY-MODEL.md`` "Secrets".
    """
    fd = os.open(str(db_path), os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    os.chmod(db_path, 0o600)


def _tighten_wal_shm_modes(db_path: Path) -> None:
    """Reconcile ``-wal``/``-shm`` sidecar modes to ``0o600`` if present.

    Called after ``PRAGMA journal_mode=WAL`` activates, since the sidecars
    don't exist (and can't be chmod'd) until WAL mode creates them.
    """
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.exists():
            os.chmod(sidecar, 0o600)


async def get_connection() -> aiosqlite.Connection:
    """Return the singleton database connection, creating it if needed."""
    global _connection
    if _connection is None:
        settings.ensure_dirs()
        db_path = settings.db_path
        _create_or_tighten_db_file(db_path)
        _connection = await aiosqlite.connect(str(db_path))
        _connection.row_factory = aiosqlite.Row
        await _connection.execute("PRAGMA journal_mode=WAL")
        await _connection.execute("PRAGMA foreign_keys=ON")
        _tighten_wal_shm_modes(db_path)
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
