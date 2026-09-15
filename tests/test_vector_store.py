"""Shared ``VectorStore`` Protocol test suite (Flight 2 Leg 4, DD-3/DD-4/DD-10).

Parametrised over the four backend x dtype cells (sqlite-vec float32/int8,
usearch f16/i8) via the ``store`` fixture so the two concrete backends
cannot diverge on the shared contract. Backend-specific behaviour
(extension-loading discipline, DDL mismatch detection, usearch sidecar
staleness) gets its own dedicated test class below the shared suite.

Per the leg spec's disjoint-id-range edge case: ``vec0`` rowids are unique
TABLE-WIDE, not per partition, so any test exercising two knowledge bases
in the same store uses disjoint id ranges (e.g. ``kb_a`` 1-50, ``kb_b``
101-150) — reusing an id across two KBs would raise ``UNIQUE constraint
failed`` for the sqlite-vec cells while the usearch cells (keyed per-KB
index, not table-wide) pass, silently masking the difference.
"""

from __future__ import annotations

import asyncio
import types

import aiosqlite
import numpy as np
import pytest

from the_one.config import settings
from the_one.db._write_lock import reset_for_test as reset_write_lock
from the_one.db._write_lock import write_transaction
from the_one.db.schema import ensure_schema
from the_one.vectors import _reset_for_test as reset_vectors_module
from the_one.vectors._store import (
    VectorStore,
    VectorStoreError,
    VectorStoreMismatchError,
    VectorStoreStaleError,
)
from the_one.vectors.sqlite_vec_store import SqliteVecStore
from the_one.vectors.usearch_store import UsearchStore

DIM = 512


def _unit_vectors(n: int, *, dim: int = DIM, seed: int = 2024) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vecs = rng.normal(size=(n, dim)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Module-local autouse reset (per the leg spec's test guidance):
    both the write-lock's module state and the dispatcher's singleton
    cache must not leak between tests in this file."""
    reset_write_lock()
    reset_vectors_module()
    yield
    reset_write_lock()
    reset_vectors_module()


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


CELLS = [
    ("sqlite-vec", "float32"),
    ("sqlite-vec", "int8"),
    ("usearch", "f16"),
    ("usearch", "i8"),
]


def _build(backend: str, dtype: str, conn, dim: int = DIM):
    if backend == "usearch":
        return UsearchStore(conn, dtype=dtype, dim=dim)
    return SqliteVecStore(conn, dtype=dtype, dim=dim)


@pytest.fixture(params=CELLS, ids=[f"{b}-{d}" for b, d in CELLS])
async def store(request, conn, tmp_path, monkeypatch):
    backend, dtype = request.param
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    built = _build(backend, dtype, conn)
    await built.open()
    return built


# ── AC-1: structural Protocol satisfaction ────────────────────────────────


class TestProtocolSatisfaction:
    def test_sqlite_vec_satisfies_protocol_structurally(self) -> None:
        built = SqliteVecStore(object(), dtype="float32")
        assert isinstance(built, VectorStore)
        assert VectorStore not in SqliteVecStore.__bases__

    def test_usearch_satisfies_protocol_structurally(self) -> None:
        built = UsearchStore(object(), dtype="f16")
        assert isinstance(built, VectorStore)
        assert VectorStore not in UsearchStore.__bases__


# ── AC-2: the shared 50-vector suite, every cell ──────────────────────────


class TestSharedProtocolSuite:
    async def test_query_returns_self_first_for_every_vector(self, store) -> None:
        vecs = _unit_vectors(50)
        ids = list(range(1, 51))
        await store.upsert("kb", ids, vecs)
        for i, vec_id in enumerate(ids):
            results = await store.query("kb", vecs[i], 1)
            assert results[0][0] == vec_id, f"vector {i} did not return itself first"

    async def test_query_k10_returns_10_nondecreasing_distances(self, store) -> None:
        vecs = _unit_vectors(50)
        ids = list(range(1, 51))
        await store.upsert("kb", ids, vecs)
        results = await store.query("kb", vecs[0], 10)
        assert len(results) == 10
        distances = [d for _, d in results]
        assert distances == sorted(distances)

    async def test_count_after_upsert(self, store) -> None:
        vecs = _unit_vectors(50)
        ids = list(range(1, 51))
        await store.upsert("kb", ids, vecs)
        assert await store.count("kb") == 50


# ── AC-3: upsert-replaces, delete, delete_kb ──────────────────────────────


class TestUpsertReplaceAndDelete:
    async def test_upsert_of_existing_id_replaces_its_vector(self, store) -> None:
        vecs = _unit_vectors(3)
        ids = [1, 2, 3]
        await store.upsert("kb", ids, vecs)

        new_vecs = _unit_vectors(3, seed=999)
        await store.upsert("kb", [ids[0]], new_vecs[:1])

        results = await store.query("kb", new_vecs[0], 1)
        assert results[0][0] == ids[0]
        assert await store.count("kb") == 3

    async def test_delete_removes_the_id(self, store) -> None:
        vecs = _unit_vectors(3)
        ids = [1, 2, 3]
        await store.upsert("kb", ids, vecs)

        await store.delete("kb", [ids[0]])

        assert await store.count("kb") == 2
        results = await store.query("kb", vecs[0], 3)
        assert ids[0] not in [r[0] for r in results]

    async def test_delete_kb_empties_the_partition(self, store) -> None:
        vecs = _unit_vectors(3)
        ids = [1, 2, 3]
        await store.upsert("kb", ids, vecs)

        await store.delete_kb("kb")

        assert await store.count("kb") == 0
        assert await store.query("kb", vecs[0], 10) == []


# ── AC-4: KB isolation ─────────────────────────────────────────────────────


class TestKbIsolation:
    async def test_identical_vectors_never_cross_kbs(self, store) -> None:
        vecs = _unit_vectors(5)
        # Disjoint id ranges — see module docstring.
        ids_a = [1, 2, 3, 4, 5]
        ids_b = [101, 102, 103, 104, 105]
        await store.upsert("kb_a", ids_a, vecs)
        await store.upsert("kb_b", ids_b, vecs)

        results_a = await store.query("kb_a", vecs[0], 10)
        results_b = await store.query("kb_b", vecs[0], 10)

        assert {r[0] for r in results_a} <= set(ids_a)
        assert {r[0] for r in results_b} <= set(ids_b)
        assert await store.count("kb_a") == 5
        assert await store.count("kb_b") == 5


# ── AC-5: reopen ───────────────────────────────────────────────────────────


class TestReopen:
    async def test_second_instance_over_same_connection_answers_same_queries(
        self, store, conn, tmp_path
    ) -> None:
        vecs = _unit_vectors(5)
        ids = [1, 2, 3, 4, 5]
        await store.upsert("kb", ids, vecs)
        await store.flush("kb")
        await store.close()

        second = _build(store.backend, store.dtype, conn)
        await second.open()

        results = await second.query("kb", vecs[0], 1)
        assert results[0][0] == ids[0]
        assert await second.count("kb") == 5

        if store.backend == "usearch":
            sidecar = tmp_path / "vectors" / "kb.usearch"
            assert sidecar.exists()
            async with conn.execute(
                "SELECT count FROM kb_vector_index WHERE kb_id = ?", ("kb",)
            ) as cur:
                row = await cur.fetchone()
            assert row["count"] == 5


# ── AC-6: SqliteVecStore.open() extension-loading discipline ─────────────


class TestSqliteVecOpenBehavior:
    async def test_open_loads_vec0_on_the_connection(self, conn, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        built = SqliteVecStore(conn, dtype="float32", dim=8)
        await built.open()
        async with conn.execute("SELECT vec_version()") as cur:
            row = await cur.fetchone()
        assert row is not None

    async def test_extension_loading_is_disabled_after_open(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        built = SqliteVecStore(conn, dtype="float32", dim=8)
        await built.open()

        import sqlite_vec

        with pytest.raises(Exception):  # noqa: B017 — sqlite3.OperationalError via aiosqlite
            await conn.load_extension(str(sqlite_vec.loadable_path()))

    async def test_open_is_idempotent(self, conn, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        built = SqliteVecStore(conn, dtype="float32", dim=8)
        await built.open()
        await built.open()  # must not raise, must not reload the extension

    async def test_two_concurrent_opens_load_the_extension_once(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        built = SqliteVecStore(conn, dtype="float32", dim=8)
        calls: list[bool] = []
        real_enable = conn.enable_load_extension

        async def _counting_enable(flag: bool):
            calls.append(flag)
            return await real_enable(flag)

        monkeypatch.setattr(conn, "enable_load_extension", _counting_enable)
        await asyncio.gather(built.open(), built.open())
        assert calls.count(True) == 1

    async def test_missing_enable_load_extension_raises_vector_store_error(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        # Same module-swap technique as
        # tests/test_doctor.py::TestProbeSqliteVec — sqlite3.Connection is
        # an immutable C type, so the missing-method build is simulated by
        # swapping the module reference the store reads.
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        stripped = types.SimpleNamespace(Connection=type("Connection", (), {}))
        monkeypatch.setattr("the_one.vectors.sqlite_vec_store.sqlite3", stripped)

        built = SqliteVecStore(conn, dtype="float32", dim=8)
        with pytest.raises(VectorStoreError, match="knowledge.vector_store"):
            await built.open()


# ── AC-7: mismatch detection ───────────────────────────────────────────────


class TestMismatchDetection:
    async def test_dtype_mismatch_raises(self, conn, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = SqliteVecStore(conn, dtype="float32", dim=8)
        await first.open()

        second = SqliteVecStore(conn, dtype="int8", dim=8)
        with pytest.raises(VectorStoreMismatchError) as exc_info:
            await second.open()
        assert "knowledge.vector_store" in str(exc_info.value)

    async def test_dim_mismatch_raises(self, conn, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = SqliteVecStore(conn, dtype="float32", dim=8)
        await first.open()

        second = SqliteVecStore(conn, dtype="float32", dim=16)
        with pytest.raises(VectorStoreMismatchError):
            await second.open()

    async def test_mismatch_message_names_both_shapes_from_live_ddl(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        """The check reads `sqlite_master`, not just the constructor args —
        verified by asserting the live DDL text appears in the error."""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = SqliteVecStore(conn, dtype="float32", dim=8)
        await first.open()

        second = SqliteVecStore(conn, dtype="int8", dim=8)
        with pytest.raises(VectorStoreMismatchError) as exc_info:
            await second.open()
        message = str(exc_info.value)
        assert "embedding float[8]" in message  # the LIVE ddl (first store's)
        assert "int8" in message  # the configured (second store's) dtype


# ── Leg 5 review fix (BLOCKING 2): usearch path-traversal guard ───────────


class TestUsearchPathTraversalGuard:
    """``UsearchStore._path_for`` builds a filesystem path from ``kb_id``.
    ``KnowledgeBase.id`` is validated to a filename-safe charset at the
    model layer (``the_one/db/models.py``), but this store must not trust
    that every caller went through that validator — it asserts the
    resolved candidate path stays under its own data dir, defence in
    depth, even for a ``kb_id`` a validator bypass would have let through.
    """

    async def test_path_traversal_kb_id_raises_even_if_model_validator_bypassed(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        store = UsearchStore(conn, dtype="f16", dim=8)
        await store.open()

        with pytest.raises(VectorStoreError):
            store._path_for("../../../evil")

    async def test_conforming_kb_id_still_resolves_under_data_dir(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        store = UsearchStore(conn, dtype="f16", dim=8)
        await store.open()

        path = store._path_for("kb1")
        assert path.is_relative_to((tmp_path / "vectors").resolve())
        assert path.name == "kb1.usearch"


# ── AC-8: usearch staleness ────────────────────────────────────────────────


class TestUsearchStaleness:
    async def test_upsert_without_flush_invisible_to_a_fresh_instance(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = UsearchStore(conn, dtype="f16", dim=8)
        await first.open()
        vecs = _unit_vectors(1, dim=8)
        await first.upsert("kb", [1], vecs)
        # No flush() — nothing is persisted to the registry or sidecar.

        second = UsearchStore(conn, dtype="f16", dim=8)
        await second.open()
        assert await second.count("kb") == 0

    async def test_tampered_registry_count_raises_stale(self, conn, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = UsearchStore(conn, dtype="f16", dim=8)
        await first.open()
        vecs = _unit_vectors(3, dim=8)
        await first.upsert("kb", [1, 2, 3], vecs)
        await first.flush("kb")

        await conn.execute("UPDATE kb_vector_index SET count = count + 1 WHERE kb_id = ?", ("kb",))
        await conn.commit()

        second = UsearchStore(conn, dtype="f16", dim=8)
        await second.open()
        with pytest.raises(VectorStoreStaleError):
            await second.query("kb", vecs[0], 1)

        # rebuild_from clears the staleness and answers correctly again.
        await second.rebuild_from("kb", [([1, 2, 3], vecs)])
        results = await second.query("kb", vecs[0], 1)
        assert results[0][0] == 1

    async def test_missing_sidecar_file_raises_stale(self, conn, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = UsearchStore(conn, dtype="i8", dim=8)
        await first.open()
        vecs = _unit_vectors(2, dim=8)
        await first.upsert("kb", [1, 2], vecs)
        await first.flush("kb")

        (tmp_path / "vectors" / "kb.usearch").unlink()

        second = UsearchStore(conn, dtype="i8", dim=8)
        await second.open()
        with pytest.raises(VectorStoreStaleError):
            await second.count("kb")

    async def test_flush_is_what_advances_generation_and_count(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        built = UsearchStore(conn, dtype="f16", dim=8)
        await built.open()
        vecs = _unit_vectors(2, dim=8)
        await built.upsert("kb", [1, 2], vecs)

        async with conn.execute("SELECT * FROM kb_vector_index WHERE kb_id = ?", ("kb",)) as cur:
            assert await cur.fetchone() is None  # nothing persisted before flush

        await built.flush("kb")
        async with conn.execute(
            "SELECT count, generation FROM kb_vector_index WHERE kb_id = ?", ("kb",)
        ) as cur:
            row = await cur.fetchone()
        assert row["count"] == 2
        assert row["generation"] == 1

        await built.upsert("kb", [3], vecs[:1])
        await built.flush("kb")
        async with conn.execute(
            "SELECT count, generation FROM kb_vector_index WHERE kb_id = ?", ("kb",)
        ) as cur:
            row2 = await cur.fetchone()
        assert row2["count"] == 3
        assert row2["generation"] == 2


# ── AC-10: write-lock re-entry ─────────────────────────────────────────────


class TestNoReentry:
    async def test_upsert_from_inside_callers_transaction_raises(self, store) -> None:
        vecs = _unit_vectors(1)
        with pytest.raises(RuntimeError):
            async with write_transaction(store.conn):
                await store.upsert("kb", [1], vecs)
