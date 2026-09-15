"""Shared ``VectorStore`` Protocol test suite (Flight 2 Leg 4, DD-3/DD-4/DD-10;
``usearch``-only since Leg 6, DD-9).

Parametrised over the two usearch dtype cells (f16/i8) via the ``store``
fixture — the seam keeps its parametrised shape for a future second
backend. Backend-specific behaviour (sidecar staleness, atomic save,
delete_kb guard ordering) gets its own dedicated test class below the
shared suite.

Ids are disjoint across knowledge bases by convention, not by a
per-partition namespace: every id comes from one global ``kb_chunks.id``
(``AUTOINCREMENT``) sequence, so any test exercising two knowledge bases
in the same store uses disjoint id ranges (e.g. ``kb_a`` 1-50, ``kb_b``
101-150) to mirror production, even though a per-KB ``usearch`` index
would not itself raise on a repeated id across two different KBs.
"""

from __future__ import annotations

from pathlib import Path

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
    VectorStoreStaleError,
)
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
    ("usearch", "f16"),
    ("usearch", "i8"),
]


def _build(backend: str, dtype: str, conn, dim: int = DIM):
    return UsearchStore(conn, dtype=dtype, dim=dim)


@pytest.fixture(params=CELLS, ids=[f"{b}-{d}" for b, d in CELLS])
async def store(request, conn, tmp_path, monkeypatch):
    backend, dtype = request.param
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    built = _build(backend, dtype, conn)
    await built.open()
    return built


# ── AC-1: structural Protocol satisfaction ────────────────────────────────


class TestProtocolSatisfaction:
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

    async def test_query_top_hit_distance_matches_independent_cosine_distance(self, store) -> None:
        """Squawk 0058(c): ``query()``'s distances were only ever asserted
        non-decreasing, never against an independently computed cosine
        distance. For unit-norm vectors, cosine distance is
        ``1 - dot(query, vector)``; this computes that independently in
        float32 (never through the store) and compares it to the top
        hit's returned distance.

        Query vectors are drawn from a SEPARATE seed than the stored set
        (never a stored vector itself) so the comparison is never the
        degenerate self-distance case (~0 regardless of dtype, since a
        vector always matches itself best even after quantisation).

        Tolerance is dtype-dependent (empirically measured across several
        seed pairs, 512-dim, 10 stored x 10 query vectors):

        - ``f16``: usearch stores/searches in IEEE half precision;
          observed top-hit error topped out ~3e-5. ``1e-3`` is ~30x that
          margin.
        - ``i8``: ``quantize_int8`` rounds each component to one of 254
          signed-byte levels spanning [-1, 1] — for 512-dim unit vectors
          (component magnitude ~1/sqrt(512) ~= 0.044) this is much
          coarser than f16. Observed top-hit error topped out ~7e-3.
          ``2e-2`` is ~3x that margin — tight enough to catch a
          materially wrong distance computation (e.g. a wrong ``metric``
          or a broken quantisation scale, empirically produces errors
          ~0.9) while tolerating i8's real quantisation noise.
        """
        tolerance = {"f16": 1e-3, "i8": 2e-2}[store.dtype]
        stored = _unit_vectors(10, seed=4242)
        ids = list(range(1, 11))
        await store.upsert("kb", ids, stored)

        queries = _unit_vectors(10, seed=7373)
        for q in queries:
            results = await store.query("kb", q, 1)
            assert len(results) == 1
            top_id, top_dist = results[0]
            top_vec = stored[top_id - 1]
            expected_dist = 1.0 - float(np.dot(q, top_vec))
            assert top_dist == pytest.approx(expected_dist, abs=tolerance), (
                f"returned distance {top_dist} vs independently computed cosine "
                f"distance {expected_dist} (dtype={store.dtype})"
            )


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

    async def test_tampered_registry_dtype_raises_stale(self, conn, tmp_path, monkeypatch) -> None:
        """AC-8/squawk 0058(b): a registry row whose ``dtype`` disagrees
        with the store's configuration raises ``VectorStoreStaleError`` on
        the next read (``_ensure_loaded``'s
        ``row["dtype"] != self.dtype`` branch), and ``rebuild_from``
        recovers."""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = UsearchStore(conn, dtype="f16", dim=8)
        await first.open()
        vecs = _unit_vectors(3, dim=8)
        await first.upsert("kb", [1, 2, 3], vecs)
        await first.flush("kb")

        await conn.execute("UPDATE kb_vector_index SET dtype = 'i8' WHERE kb_id = ?", ("kb",))
        await conn.commit()

        second = UsearchStore(conn, dtype="f16", dim=8)
        await second.open()
        with pytest.raises(VectorStoreStaleError):
            await second.query("kb", vecs[0], 1)

        # rebuild_from clears the staleness and answers correctly again.
        await second.rebuild_from("kb", [([1, 2, 3], vecs)])
        results = await second.query("kb", vecs[0], 1)
        assert results[0][0] == 1

    async def test_tampered_registry_dim_raises_stale(self, conn, tmp_path, monkeypatch) -> None:
        """AC-8/squawk 0058(b): a registry row whose ``dim`` disagrees
        with the store's configuration raises ``VectorStoreStaleError`` on
        the next read (``_ensure_loaded``'s ``row["dim"] != self.dim``
        branch), and ``rebuild_from`` recovers."""
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        first = UsearchStore(conn, dtype="f16", dim=8)
        await first.open()
        vecs = _unit_vectors(3, dim=8)
        await first.upsert("kb", [1, 2, 3], vecs)
        await first.flush("kb")

        await conn.execute("UPDATE kb_vector_index SET dim = dim + 1 WHERE kb_id = ?", ("kb",))
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


# ── AC-6: atomic sidecar save ────────────────────────────────────────────


class TestAtomicSave:
    async def test_failed_save_leaves_previous_sidecar_and_registry_intact_then_retries(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        from usearch.index import Index

        monkeypatch.setattr(settings, "data_dir", tmp_path)
        store = UsearchStore(conn, dtype="f16", dim=8)
        await store.open()
        vecs = _unit_vectors(4, dim=8)

        await store.upsert("kb", [1, 2, 3], vecs[:3])
        await store.flush("kb")  # succeeds — the "previous good" sidecar/registry

        sidecar = tmp_path / "vectors" / "kb.usearch"
        assert sidecar.exists()
        previous_bytes = sidecar.read_bytes()

        async with conn.execute(
            "SELECT count, generation FROM kb_vector_index WHERE kb_id = ?", ("kb",)
        ) as cur:
            row_before = await cur.fetchone()
        assert row_before["count"] == 3
        assert row_before["generation"] == 1

        await store.upsert("kb", [4], vecs[3:4])
        entry = store._entry("kb")
        assert entry.dirty is True

        # Record every path `Index.save` is actually invoked with, for both
        # the failing and the succeeding flush below — a review fix
        # (flight-end review, Leg 6): asserting these are the
        # `.usearch.tmp` sidecar path, never the real sidecar path, is what
        # actually proves `_save_atomically`'s write-then-replace shape.
        # The prior version of this test raised from a `Index.save` stand-in
        # that performed no I/O and never inspected its argument, so it
        # would have passed unchanged against a pre-Leg-6 implementation
        # that called `index.save(path)` directly on the real sidecar path.
        recorded_save_paths: list[str] = []
        real_save = Index.save

        def _boom_save(self, path_or_buffer=None, *args, **kwargs):
            recorded_save_paths.append(path_or_buffer)
            raise RuntimeError("disk full (simulated)")

        def _spy_save(self, path_or_buffer=None, *args, **kwargs):
            recorded_save_paths.append(path_or_buffer)
            return real_save(self, path_or_buffer, *args, **kwargs)

        with monkeypatch.context() as m:
            m.setattr(Index, "save", _boom_save)
            with pytest.raises(RuntimeError, match="disk full"):
                await store.flush("kb")

        # Previous sidecar untouched; no .tmp file left behind.
        assert sidecar.read_bytes() == previous_bytes
        assert list((tmp_path / "vectors").glob("*.usearch.tmp")) == []

        # Registry row unchanged at its previous generation.
        async with conn.execute(
            "SELECT count, generation FROM kb_vector_index WHERE kb_id = ?", ("kb",)
        ) as cur:
            row_after = await cur.fetchone()
        assert row_after["count"] == 3
        assert row_after["generation"] == 1

        # `entry.dirty` stays True so the next flush retries.
        assert entry.dirty is True

        # A second flush, with the failing monkeypatch swapped for a spy
        # that still calls through to the real `Index.save`, succeeds and
        # advances the registry.
        with monkeypatch.context() as m:
            m.setattr(Index, "save", _spy_save)
            await store.flush("kb")
        assert entry.dirty is False
        async with conn.execute(
            "SELECT count, generation FROM kb_vector_index WHERE kb_id = ?", ("kb",)
        ) as cur:
            row_final = await cur.fetchone()
        assert row_final["count"] == 4
        assert row_final["generation"] == 2

        # The discriminating assertions: every recorded `Index.save` call
        # (failing flush + succeeding flush) targeted the same-directory
        # `.usearch.tmp` sidecar, and the real sidecar path was never
        # passed to `Index.save` directly — only true under
        # `_save_atomically`'s write-then-`os.replace` shape, not a direct
        # `index.save(path)` call on the real sidecar path.
        assert len(recorded_save_paths) == 2
        for recorded in recorded_save_paths:
            recorded_path = Path(recorded)
            assert recorded_path.name == "kb.usearch.tmp"
            assert recorded_path.parent == sidecar.parent
            assert recorded_path != sidecar
        assert str(sidecar) not in recorded_save_paths


# ── AC-7: corrupt sidecar -> stale ────────────────────────────────────────


class TestCorruptSidecar:
    async def _flush_real_sidecar(
        self, conn, tmp_path, monkeypatch
    ) -> tuple[UsearchStore, np.ndarray]:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        store = UsearchStore(conn, dtype="f16", dim=8)
        await store.open()
        vecs = _unit_vectors(3, dim=8)
        await store.upsert("kb", [1, 2, 3], vecs)
        await store.flush("kb")
        return store, vecs

    async def test_garbage_bytes_raise_stale_on_every_read_and_write(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        await self._flush_real_sidecar(conn, tmp_path, monkeypatch)
        sidecar = tmp_path / "vectors" / "kb.usearch"
        sidecar.write_bytes(b"not a usearch index, just garbage bytes" * 4)

        second = UsearchStore(conn, dtype="f16", dim=8)
        await second.open()
        with pytest.raises(VectorStoreStaleError):
            await second.count("kb")
        with pytest.raises(VectorStoreStaleError):
            await second.query("kb", _unit_vectors(1, dim=8)[0], 1)
        with pytest.raises(VectorStoreStaleError):
            await second.upsert("kb", [4], _unit_vectors(1, dim=8))

    async def test_truncated_file_raises_stale(self, conn, tmp_path, monkeypatch) -> None:
        await self._flush_real_sidecar(conn, tmp_path, monkeypatch)
        sidecar = tmp_path / "vectors" / "kb.usearch"
        original = sidecar.read_bytes()
        sidecar.write_bytes(original[: len(original) // 2])

        second = UsearchStore(conn, dtype="f16", dim=8)
        await second.open()
        with pytest.raises(VectorStoreStaleError):
            await second.count("kb")

    async def test_empty_file_raises_stale(self, conn, tmp_path, monkeypatch) -> None:
        await self._flush_real_sidecar(conn, tmp_path, monkeypatch)
        sidecar = tmp_path / "vectors" / "kb.usearch"
        sidecar.write_bytes(b"")

        second = UsearchStore(conn, dtype="f16", dim=8)
        await second.open()
        with pytest.raises(VectorStoreStaleError):
            await second.count("kb")

    async def test_rebuild_from_recovers_after_corruption(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        _, vecs = await self._flush_real_sidecar(conn, tmp_path, monkeypatch)
        sidecar = tmp_path / "vectors" / "kb.usearch"
        sidecar.write_bytes(b"garbage")

        second = UsearchStore(conn, dtype="f16", dim=8)
        await second.open()
        with pytest.raises(VectorStoreStaleError):
            await second.count("kb")

        await second.rebuild_from("kb", [([1, 2, 3], vecs)])
        results = await second.query("kb", vecs[0], 1)
        assert results[0][0] == 1
        async with conn.execute(
            "SELECT count FROM kb_vector_index WHERE kb_id = ?", ("kb",)
        ) as cur:
            row = await cur.fetchone()
        assert row["count"] == 3


# ── AC-8: delete_kb guard-first ───────────────────────────────────────────


class TestDeleteKbGuardFirst:
    async def test_nested_delete_kb_raises_before_any_mutation(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        store = UsearchStore(conn, dtype="f16", dim=8)
        await store.open()
        vecs = _unit_vectors(2, dim=8)
        await store.upsert("kb", [1, 2], vecs)
        await store.flush("kb")

        sidecar = tmp_path / "vectors" / "kb.usearch"
        assert sidecar.exists()

        with pytest.raises(RuntimeError):
            async with write_transaction(conn):
                await store.delete_kb("kb")

        # Nothing mutated: sidecar still exists, registry row still
        # present, count still answers through the same store instance.
        assert sidecar.exists()
        async with conn.execute("SELECT * FROM kb_vector_index WHERE kb_id = ?", ("kb",)) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert await store.count("kb") == 2


# ── AC-10: write-lock re-entry ─────────────────────────────────────────────


class TestNoReentry:
    async def test_upsert_from_inside_callers_transaction_raises(self, store) -> None:
        vecs = _unit_vectors(1)
        with pytest.raises(RuntimeError):
            async with write_transaction(store.conn):
                await store.upsert("kb", [1], vecs)


# ── Squawk 0054: vector-dimension guard ────────────────────────────────────


class TestDimensionGuard:
    """``upsert``/``query``/``rebuild_from`` must reject a vector whose
    last axis differs from ``self.dim`` with ``ValueError`` naming both
    the expected and actual dim plus the ``kb_id``, checked before
    quantisation ever runs. Parametrised over both usearch dtype cells via
    the ``store`` fixture (``dim=DIM=512``).

    Without the added ``_check_dim`` guard, each of these calls would
    either reach ``usearch``'s C extension with mismatched data (silent
    garbage) or fail with whatever unrelated low-level exception the
    extension happens to raise for a shape it rejects — not a
    ``ValueError`` naming the dims — so every test below fails without the
    fix.
    """

    async def test_upsert_wrong_width_raises_naming_both_dims(self, store) -> None:
        wrong = _unit_vectors(2, dim=8)
        with pytest.raises(ValueError, match=str(DIM)) as exc_info:
            await store.upsert("kb", [1, 2], wrong)
        message = str(exc_info.value)
        assert "8" in message
        assert "kb" in message

    async def test_query_wrong_width_raises_naming_both_dims(self, store) -> None:
        wrong = _unit_vectors(1, dim=8)[0]
        with pytest.raises(ValueError, match=str(DIM)) as exc_info:
            await store.query("kb", wrong, 1)
        message = str(exc_info.value)
        assert "8" in message
        assert "kb" in message

    async def test_rebuild_from_wrong_width_raises_naming_both_dims(self, store) -> None:
        wrong = _unit_vectors(2, dim=8)
        with pytest.raises(ValueError, match=str(DIM)) as exc_info:
            await store.rebuild_from("kb", [([1, 2], wrong)])
        message = str(exc_info.value)
        assert "8" in message
        assert "kb" in message
