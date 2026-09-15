"""Tests for the vector-store dispatcher (Flight 2 Leg 4, DD-3, AC-9).

``get_vector_store()`` is async (a documented departure from
``create_pty_session``'s sync dispatch shape — DD-3) because the backend
choice is a DB record (``knowledge.vector_store``). These tests patch the
dispatcher module's own ``get_connection`` reference so the singleton
production connection (which would otherwise touch the operator's real
data directory) is never actually created.
"""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest

from the_one.config import settings
from the_one.db._write_lock import reset_for_test as reset_write_lock
from the_one.db.repositories import AppMetadataRepository
from the_one.db.schema import ensure_schema
from the_one.knowledge.settings import VECTOR_STORE_KEY, VectorStoreSettings
from the_one.vectors import _build_store, _reset_for_test, get_vector_store
from the_one.vectors.usearch_store import UsearchStore


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


@pytest.fixture(autouse=True)
def _isolate_singleton(conn, monkeypatch):
    """Route the dispatcher's ``get_connection()`` to this test's isolated
    connection instead of the real production singleton — otherwise the
    first call would create/open the operator's actual data-dir database
    file as a side effect of running this test."""

    async def _fake_get_connection():
        return conn

    monkeypatch.setattr("the_one.vectors.get_connection", _fake_get_connection)
    reset_write_lock()
    _reset_for_test()
    yield
    reset_write_lock()
    _reset_for_test()


class TestDispatch:
    async def test_defaults_to_usearch_when_record_absent(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        built = await get_vector_store()
        assert isinstance(built, UsearchStore)
        assert built.backend == "usearch"
        assert built.dtype == "f16"

    async def test_stored_i8_record_builds_an_i8_store(self, conn, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        repo = AppMetadataRepository(conn)
        await repo.set(
            VECTOR_STORE_KEY,
            VectorStoreSettings(backend="usearch", dtype="i8").model_dump_json(),
        )
        built = await get_vector_store()
        assert isinstance(built, UsearchStore)
        assert built.dtype == "i8"

    async def test_returns_usearch_when_record_says_so(self, conn, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        repo = AppMetadataRepository(conn)
        await repo.set(
            VECTOR_STORE_KEY,
            VectorStoreSettings(backend="usearch", dtype="f16").model_dump_json(),
        )
        built = await get_vector_store()
        assert isinstance(built, UsearchStore)
        assert built.dtype == "f16"

    async def test_same_instance_on_repeated_calls(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = await get_vector_store()
        second = await get_vector_store()
        assert first is second

    async def test_reset_for_test_builds_anew(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = await get_vector_store()
        _reset_for_test()
        second = await get_vector_store()
        assert first is not second

    async def test_concurrent_first_callers_build_exactly_once(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        import the_one.vectors as vectors_module

        calls = {"n": 0}
        real_build_store = vectors_module._build_store

        def _counting_build_store(vector_store_settings, conn):
            calls["n"] += 1
            return real_build_store(vector_store_settings, conn)

        monkeypatch.setattr(vectors_module, "_build_store", _counting_build_store)

        first, second = await asyncio.gather(get_vector_store(), get_vector_store())
        assert first is second
        assert calls["n"] == 1

    async def test_data_dir_is_resolved_at_open_not_at_construction(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        """AC-9's last clause: a `settings.data_dir` monkeypatch applied
        AFTER `_build_store()` but BEFORE `open()` must be honoured — the
        store built directly (bypassing `get_vector_store()`'s own
        immediate `open()` call) so the two steps can be separated."""
        monkeypatch.setattr(settings, "data_dir", tmp_path / "before")
        built = _build_store(VectorStoreSettings(backend="usearch", dtype="f16"), conn)

        monkeypatch.setattr(settings, "data_dir", tmp_path / "after")
        await built.open()

        assert built._data_dir == tmp_path / "after" / "vectors"
