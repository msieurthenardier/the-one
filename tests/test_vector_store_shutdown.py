"""Tests for the vector-store shutdown hook (Mission 24 Flight 7 Leg 1,
DD-3/DD-3a): ``close_vector_store()`` in ``the_one/vectors/__init__.py``.

Coverage:
  AC-1  — exists in ``the_one.vectors``, exported via ``__all__``, async
  AC-2  — never builds a store when none exists (``_build_store`` spy)
  AC-3  — closes an existing store and clears the module cache, so a
          subsequent ``get_vector_store()`` builds afresh
  AC-8  — a dirty knowledge base with no worker is flushed by the hook
  AC-9  — a knowledge base named in ``skip_kb_ids`` is NOT flushed, and
          the skip is logged at WARNING naming the kb_id (DD-3a)
  AC-10 — calling the hook (and the underlying store's own ``close()``)
          twice is safe — including the "second close after a failed
          flush" case the Edge Cases section calls out explicitly

Follows the ``_isolate_singleton`` idiom from ``tests/test_vectors_dispatch.py``
and the ``_build`` / ``store``-fixture idiom from ``tests/test_vector_store.py``
(a fresh ``UsearchStore`` over the SAME connection is how persistence to
the sidecar + registry row is verified, since ``upsert`` without ``flush``
is invisible to a fresh instance by design).
"""

from __future__ import annotations

import inspect
import logging

import aiosqlite
import numpy as np
import pytest

from the_one import vectors as vectors_mod
from the_one.config import settings
from the_one.db._write_lock import reset_for_test as reset_write_lock
from the_one.db.schema import ensure_schema
from the_one.vectors import _reset_for_test, close_vector_store, get_vector_store
from the_one.vectors.usearch_store import UsearchStore

DIM = 512


def _unit_vectors(n: int, *, dim: int = DIM, seed: int = 99) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vecs = rng.normal(size=(n, dim)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs


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
def _isolate_singleton(conn, tmp_path, monkeypatch):
    """Route the dispatcher's ``get_connection()`` to this test's isolated
    connection, and ``settings.data_dir`` to a tmp dir — otherwise the
    first ``get_vector_store()`` call would touch the operator's real
    data directory. Mirrors ``tests/test_vectors_dispatch.py``."""

    async def _fake_get_connection():
        return conn

    monkeypatch.setattr(vectors_mod, "get_connection", _fake_get_connection)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    reset_write_lock()
    _reset_for_test()
    yield
    reset_write_lock()
    _reset_for_test()


# ── AC-1: exists, exported, async ──────────────────────────────────────────


class TestHookShape:
    def test_exported_and_async(self) -> None:
        assert "close_vector_store" in vectors_mod.__all__
        assert inspect.iscoroutinefunction(close_vector_store)


# ── AC-2: never builds a store to close it ─────────────────────────────────


class TestNeverBuildsToClose:
    async def test_noop_when_no_store_built(self, monkeypatch) -> None:
        build_calls = []
        original_build = vectors_mod._build_store

        def _spy_build(*args, **kwargs):
            build_calls.append((args, kwargs))
            return original_build(*args, **kwargs)

        monkeypatch.setattr(vectors_mod, "_build_store", _spy_build)

        assert vectors_mod._store is None
        await close_vector_store()

        assert build_calls == []
        assert vectors_mod._store is None


# ── AC-3: closes an existing store and clears the cache ────────────────────


class TestClosesAndClearsCache:
    async def test_closes_existing_store_and_clears_cache(self, monkeypatch) -> None:
        built = await get_vector_store()
        assert vectors_mod._store is built

        close_calls: list[frozenset] = []
        original_close = built.close

        async def _spy_close(*, skip_kb_ids=frozenset()):
            close_calls.append(frozenset(skip_kb_ids))
            await original_close(skip_kb_ids=skip_kb_ids)

        monkeypatch.setattr(built, "close", _spy_close)
        await close_vector_store()

        assert close_calls == [frozenset()]
        # AC-3: the cache is cleared, so a subsequent get_vector_store()
        # builds afresh rather than returning the closed instance.
        assert vectors_mod._store is None
        rebuilt = await get_vector_store()
        assert rebuilt is not built


# ── AC-8/AC-9: flush-with-skip behaviour ────────────────────────────────────


class TestFlushWithSkip:
    async def test_dirty_kb_with_no_worker_is_flushed(self, conn, tmp_path) -> None:
        """AC-8: this is the case no existing drain covers — a dirty
        knowledge base with no IndexingManager worker at all (e.g. the
        item-delete route's direct vector-store write)."""
        store = await get_vector_store()
        vecs = _unit_vectors(3)
        await store.upsert("kb-no-worker", [1, 2, 3], vecs)
        # Deliberately no flush() — the hook must be what flushes it.

        await close_vector_store()

        second = UsearchStore(conn, dtype="f16", dim=DIM)
        await second.open()
        assert await second.count("kb-no-worker") == 3
        assert (tmp_path / "vectors" / "kb-no-worker.usearch").exists()

    async def test_cancelled_kb_id_is_skipped_and_logged(
        self, conn, tmp_path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC-9: a knowledge base named in ``skip_kb_ids`` (DD-3a's
        cancel-fallback report) is left dirty by the hook — flushing it
        could race a still-running mutation and tear the index."""
        store = await get_vector_store()
        vecs = _unit_vectors(2)
        await store.upsert("kb-cancelled", [1, 2], vecs)

        with caplog.at_level(logging.WARNING, logger="the_one.vectors"):
            await close_vector_store(skip_kb_ids=frozenset({"kb-cancelled"}))

        second = UsearchStore(conn, dtype="f16", dim=DIM)
        await second.open()
        assert await second.count("kb-cancelled") == 0

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("kb-cancelled" in r.getMessage() for r in warnings)

    async def test_skip_set_does_not_affect_other_kbs(self, conn, tmp_path) -> None:
        """AC-9's skip must be precise: a different, non-skipped kb_id in
        the same store is still flushed."""
        store = await get_vector_store()
        await store.upsert("kb-cancelled", [1, 2], _unit_vectors(2, seed=1))
        await store.upsert("kb-clean", [101, 102], _unit_vectors(2, seed=2))

        await close_vector_store(skip_kb_ids=frozenset({"kb-cancelled"}))

        second = UsearchStore(conn, dtype="f16", dim=DIM)
        await second.open()
        assert await second.count("kb-cancelled") == 0
        assert await second.count("kb-clean") == 2


# ── AC-10: idempotency / calling twice is safe ─────────────────────────────


class TestCalledTwiceIsSafe:
    async def test_hook_called_twice_in_a_row_is_a_noop_second_time(self) -> None:
        await get_vector_store()
        await close_vector_store()
        assert vectors_mod._store is None
        # A second call finds no cached store — AC-2's no-build guarantee
        # applies here too, and this must not raise.
        await close_vector_store()
        assert vectors_mod._store is None

    async def test_second_close_after_a_failed_flush_recovers(
        self, conn, tmp_path, monkeypatch
    ) -> None:
        """Edge Cases: ``flush()`` early-returns on ``not entry.dirty``,
        so a retry only happens when the first attempt failed — AC-10
        asserts safety of that retry, not mere no-op-ness. The module
        cache-clear in ``close_vector_store()`` does not affect the
        underlying store OBJECT's own state, so a second ``close()`` call
        on that same object (as the object itself, not through a rebuilt
        ``get_vector_store()``) is what proves the recovery."""
        store = await get_vector_store()
        await store.upsert("kb-retry", [1, 2], _unit_vectors(2))

        original_flush = store.flush
        state = {"n": 0}

        async def _flaky_flush(kb_id):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("simulated flush failure")
            await original_flush(kb_id)

        monkeypatch.setattr(store, "flush", _flaky_flush)

        # First call: the per-KB flush raises inside close(); close()'s
        # own try/except logs it and does not propagate (DD-3 idempotency
        # discipline). The module cache is cleared regardless.
        await close_vector_store()
        assert vectors_mod._store is None
        assert state["n"] == 1

        # Second close() on the SAME store object (not a fresh
        # get_vector_store() build, which would lose the in-memory dirty
        # flag) succeeds this time — safe, and no longer a no-op, because
        # the failed first flush left the entry dirty.
        await store.close()
        assert state["n"] == 2

        second = UsearchStore(conn, dtype="f16", dim=DIM)
        await second.open()
        assert await second.count("kb-retry") == 2
