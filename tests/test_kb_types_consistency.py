"""Pin the KB item type/status representations to one source of truth.

Mirrors ``tests/test_provider_types_consistency.py``'s shape, with one
deliberate difference (Flight 2 Leg 1, DD-5): the SQLite CHECK constraints
on ``kb_items`` are FROZEN INLINE LITERALS in the v40 migration block, never
derived from ``the_one/db/_kb_types.py`` — schema history is append-only,
so a CHECK must never change out from under a database that already ran
it (see ``_kb_types.py``'s docstring and ``schema.py``'s v8 comment for the
full argument). So this file does NOT assert the CHECK's SQL text equals
the tuple (there is no such derivation to test); instead it proves the
CHECK behaviourally accepts every tuple member and rejects a bogus value,
on both columns.
"""

from __future__ import annotations

import sqlite3
from typing import get_args

import aiosqlite
import pytest

from the_one.db._kb_types import KB_ITEM_STATUSES, KB_ITEM_TYPES
from the_one.db.models import KBItem
from the_one.db.schema import ensure_schema


def test_kb_item_types_tuple_has_expected_members() -> None:
    assert set(KB_ITEM_TYPES) == {"file", "url", "folder"}


def test_kb_item_statuses_tuple_has_expected_members() -> None:
    assert set(KB_ITEM_STATUSES) == {"pending", "indexing", "indexed", "failed"}


def test_pydantic_type_literal_matches_kb_item_types() -> None:
    """(The model's import-time assertion already enforces this; the
    explicit test is for visibility in the suite output.)"""
    annotation = KBItem.model_fields["type"].annotation
    assert set(get_args(annotation)) == set(KB_ITEM_TYPES)


def test_pydantic_status_literal_matches_kb_item_statuses() -> None:
    annotation = KBItem.model_fields["status"].annotation
    assert set(get_args(annotation)) == set(KB_ITEM_STATUSES)


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "kb-types-check.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await ensure_schema(connection)
    await connection.execute("INSERT INTO knowledge_bases (id, name) VALUES ('kb1', 'KB1')")
    await connection.commit()
    yield connection
    await connection.close()


async def test_check_accepts_every_valid_type(conn) -> None:
    for i, type_ in enumerate(KB_ITEM_TYPES):
        await conn.execute(
            "INSERT INTO kb_items (id, kb_id, type, path_or_url) VALUES (?, 'kb1', ?, ?)",
            (f"type-{i}", type_, f"p{i}"),
        )
    await conn.commit()
    async with conn.execute("SELECT COUNT(*) FROM kb_items") as cur:
        row = await cur.fetchone()
    assert row[0] == len(KB_ITEM_TYPES)


async def test_check_accepts_every_valid_status(conn) -> None:
    for i, status in enumerate(KB_ITEM_STATUSES):
        await conn.execute(
            "INSERT INTO kb_items (id, kb_id, type, path_or_url, status) "
            "VALUES (?, 'kb1', 'file', ?, ?)",
            (f"status-{i}", f"p{i}", status),
        )
    await conn.commit()
    async with conn.execute("SELECT COUNT(*) FROM kb_items") as cur:
        row = await cur.fetchone()
    assert row[0] == len(KB_ITEM_STATUSES)


async def test_check_rejects_bogus_type(conn) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO kb_items (id, kb_id, type, path_or_url) VALUES ('bad', 'kb1', 'blob', 'p')"
        )


async def test_check_rejects_bogus_status(conn) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO kb_items (id, kb_id, type, path_or_url, status) "
            "VALUES ('bad', 'kb1', 'file', 'p', 'done')"
        )
