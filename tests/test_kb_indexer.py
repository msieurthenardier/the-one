"""Tests for ``the_one/knowledge/indexer.py`` (Flight 3 Leg 2, DD-5/DD-6):
``index_item``'s eight-stage happy path and every failure path, zero-norm
and ``truncated`` handling, the cooperative-stop seam, ``FlushPolicy``, and
``rebuild_kb``.

Every seam-consumer test here runs against ``tests/_embedding_stub.py::
StubEmbeddingBackend`` — never a real model load (confined to
``tests/test_doctor_embedding_model.py``, per ``the_one/agents.md``).
"""

from __future__ import annotations

import asyncio
import contextlib
import time

import aiosqlite
import numpy as np
import pytest

from tests._embedding_stub import StubEmbeddingBackend
from the_one.config import settings
from the_one.db._kb_types import ChunkRecord, KBItemTransitionError
from the_one.db._write_lock import reset_for_test as reset_write_lock
from the_one.db.models import KBItem, KnowledgeBase
from the_one.db.repositories import KBChunkRepository, KBItemRepository, KnowledgeBaseRepository
from the_one.db.schema import ensure_schema
from the_one.embeddings._backend import EmbedResult
from the_one.knowledge import indexer as indexer_module
from the_one.knowledge.indexer import FlushPolicy, IndexContext, index_item, rebuild_kb
from the_one.knowledge.settings import ChunkingSettings
from the_one.vectors import _reset_for_test as reset_vectors_module
from the_one.vectors._store import VectorStoreStaleError
from the_one.vectors.usearch_store import UsearchStore


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Mirrors ``tests/test_vector_store.py``'s autouse reset — the
    write-lock's module state and the vector-store dispatcher's singleton
    cache must not leak between tests."""
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


@pytest.fixture
def kb_repo(conn):
    return KnowledgeBaseRepository(conn)


@pytest.fixture
def item_repo(conn):
    return KBItemRepository(conn)


@pytest.fixture
def chunk_repo(conn):
    return KBChunkRepository(conn)


@pytest.fixture
async def store(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    built = UsearchStore(conn, dtype="f16", dim=8)
    await built.open()
    return built


@pytest.fixture
def backend():
    return StubEmbeddingBackend(dim=8)


@pytest.fixture
def chunking():
    # Small so a handful-of-paragraphs fixture file produces several
    # chunks — the leg spec's fixture shape.
    return ChunkingSettings(size_chars=200, overlap_chars=20)


@pytest.fixture
def ctx(conn, item_repo, chunk_repo, store, backend, chunking):
    return IndexContext(
        conn=conn,
        item_repo=item_repo,
        chunk_repo=chunk_repo,
        store=store,
        backend=backend,
        chunking=chunking,
    )


async def _make_kb_and_item(
    conn,
    path,
    *,
    kb_id: str = "kb1",
    item_id: str = "item1",
    item_type: str = "file",
) -> KBItem:
    kb_repo = KnowledgeBaseRepository(conn)
    item_repo = KBItemRepository(conn)
    await kb_repo.create(KnowledgeBase(id=kb_id, name=kb_id))
    item = KBItem(id=item_id, kb_id=kb_id, type=item_type, path_or_url=str(path))
    await item_repo.create(item)
    return item


def _make_text(num_paragraphs: int = 6, para_chars: int = 150, *, doc: int = 0) -> str:
    """`doc` distinguishes otherwise-identical paragraph text across
    multiple fixture files in the same test — `StubEmbeddingBackend` is a
    deterministic hash of text, so two files with byte-identical content
    would embed to byte-identical vectors, producing ties a nearest-
    neighbour query cannot resolve by id."""
    return "\n\n".join(
        f"doc{doc} paragraph {i} " + ("x" * para_chars) for i in range(num_paragraphs)
    )


class RecordingStore:
    """A structural ``VectorStore`` recording every call — AC-4/AC-6/AC-7's
    exact-ids and batch-count assertions."""

    backend = "recording"
    dtype = "f16"
    dim = 8

    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[int], np.ndarray]] = []
        self.deletes: list[tuple[str, list[int]]] = []
        self.flushes: list[str] = []

    async def open(self) -> None:
        return None

    async def upsert(self, kb_id: str, ids, vectors: np.ndarray) -> None:
        self.upserts.append((kb_id, list(ids), np.asarray(vectors).copy()))

    async def delete(self, kb_id: str, ids) -> None:
        self.deletes.append((kb_id, list(ids)))

    async def delete_kb(self, kb_id: str) -> None:
        return None

    async def query(self, kb_id: str, vector: np.ndarray, k: int):
        return []

    async def count(self, kb_id: str) -> int:
        return sum(len(ids) for _, ids, _ in self.upserts if _ == kb_id)

    async def flush(self, kb_id: str) -> None:
        self.flushes.append(kb_id)

    async def rebuild_from(self, kb_id: str, ids_and_vectors) -> None:
        async for _ids, _vectors in ids_and_vectors:
            pass

    async def close(self) -> None:
        return None


class _OnlyRebuildStore:
    """AC-10: a store stub that raises on any call other than
    ``rebuild_from`` — proves ``rebuild_kb``'s generator touches only
    ``ctx.chunk_repo.iter_for_kb`` and ``ctx.backend.embed``."""

    backend = "only-rebuild"
    dtype = "f16"
    dim = 8

    def __init__(self) -> None:
        self.pages: list[tuple[list[int], np.ndarray]] = []

    async def open(self) -> None:
        raise AssertionError("open should not be called")

    async def upsert(self, *args, **kwargs) -> None:
        raise AssertionError("upsert should not be called")

    async def delete(self, *args, **kwargs) -> None:
        raise AssertionError("delete should not be called")

    async def delete_kb(self, *args, **kwargs) -> None:
        raise AssertionError("delete_kb should not be called")

    async def query(self, *args, **kwargs):
        raise AssertionError("query should not be called")

    async def count(self, *args, **kwargs) -> int:
        raise AssertionError("count should not be called")

    async def flush(self, *args, **kwargs) -> None:
        raise AssertionError("flush should not be called")

    async def close(self) -> None:
        raise AssertionError("close should not be called")

    async def rebuild_from(self, kb_id: str, ids_and_vectors) -> None:
        async for ids, vectors in ids_and_vectors:
            self.pages.append((list(ids), np.asarray(vectors).copy()))


# ── AC-4: happy path ────────────────────────────────────────────────────


class TestHappyPath:
    async def test_index_item_end_to_end(self, conn, ctx, chunk_repo, tmp_path) -> None:
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)

        outcome = await index_item(item, ctx)

        assert outcome.status == "awaiting_flush"
        assert outcome.error is None
        assert outcome.chunks > 1
        assert outcome.vectors == outcome.chunks
        assert outcome.truncated == 0

        item_repo = ctx.item_repo
        stored = await item_repo.get(item.id)
        assert stored.status == "indexing"  # the flip to `indexed` is Leg 3's
        assert stored.content_hash is not None
        assert stored.size_bytes == path.stat().st_size
        assert stored.mtime is not None

        assert await ctx.store.count(item.kb_id) == outcome.chunks
        rows = await chunk_repo.list_for_item(item.id)
        assert len(rows) == outcome.chunks
        assert [r.seq for r in rows] == list(range(outcome.chunks))

    async def test_reindex_deletes_old_ids_and_new_ids_are_disjoint(
        self, conn, item_repo, chunk_repo, chunking, backend, tmp_path
    ) -> None:
        recording = RecordingStore()
        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=recording,
            backend=backend,
            chunking=chunking,
        )
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)

        first = await index_item(item, ctx)
        assert not recording.deletes  # no old ids on the first index
        first_ids = {i for _, ids, _ in recording.upserts for i in ids}
        assert first_ids  # sanity: the first index actually upserted something

        # Move back to pending (mirrors the worker's reindex path) so a
        # second `index_item` call is a legal `pending -> indexing`.
        await item_repo.update_status(item.id, "pending")
        item = await item_repo.get(item.id)

        second = await index_item(item, ctx)

        assert len(recording.deletes) == 1, "re-index must call store.delete exactly once"
        deleted_kb, deleted_ids = recording.deletes[0]
        assert deleted_kb == item.kb_id
        # The exact old ids are deleted — nothing more, nothing less.
        assert set(deleted_ids) == first_ids
        assert first.chunks == second.chunks

        all_upsert_ids = {i for _, ids, _ in recording.upserts for i in ids}
        second_only_ids = all_upsert_ids - first_ids
        # New (second-index) ids are disjoint from the deleted old ids —
        # AUTOINCREMENT never recycles.
        assert second_only_ids.isdisjoint(first_ids)
        assert len(second_only_ids) == second.vectors


# ── AC-5: failure paths ─────────────────────────────────────────────────


class TestFailurePaths:
    async def test_missing_file_names_the_path(self, conn, ctx) -> None:
        missing = "/nonexistent/path/does-not-exist.txt"
        item = await _make_kb_and_item(conn, missing)

        outcome = await index_item(item, ctx)

        assert outcome.status == "failed"
        assert missing in outcome.error
        stored = await ctx.item_repo.get(item.id)
        assert stored.status == "failed"
        assert stored.error == outcome.error
        assert not await ctx.chunk_repo.list_for_item(item.id)

    async def test_file_over_cap_rejected(self, conn, ctx, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(indexer_module, "MAX_FILE_BYTES", 10)
        path = tmp_path / "big.txt"
        path.write_text("x" * 20)
        item = await _make_kb_and_item(conn, path)

        outcome = await index_item(item, ctx)

        assert outcome.status == "failed"
        assert outcome.error == "file exceeds the 10 MiB indexing cap"
        assert not await ctx.chunk_repo.list_for_item(item.id)

    async def test_binary_content_rejected(self, conn, ctx, tmp_path) -> None:
        path = tmp_path / "bin.txt"
        path.write_bytes(b"hello\x00world")
        item = await _make_kb_and_item(conn, path)

        outcome = await index_item(item, ctx)

        assert outcome.status == "failed"
        assert outcome.error == "binary content"
        assert not await ctx.chunk_repo.list_for_item(item.id)

    async def test_extractor_error_message_passed_through(self, conn, ctx, tmp_path) -> None:
        from the_one.knowledge.extractors import ExtractionError, register, unregister

        class _BoomExtractor:
            name = "boom"
            extensions = frozenset({".boom"})

            def extract(self, path):
                raise ExtractionError("boom: could not parse")

        register(_BoomExtractor())
        try:
            path = tmp_path / "doc.boom"
            path.write_text("irrelevant")
            item = await _make_kb_and_item(conn, path)

            outcome = await index_item(item, ctx)
        finally:
            unregister("boom")

        assert outcome.status == "failed"
        assert outcome.error == "boom: could not parse"
        assert not await ctx.chunk_repo.list_for_item(item.id)

    async def test_no_extractor_for_suffix_names_it(self, conn, ctx, tmp_path) -> None:
        path = tmp_path / "doc.no_such_ext"
        item = await _make_kb_and_item(conn, path)

        outcome = await index_item(item, ctx)

        assert outcome.status == "failed"
        assert ".no_such_ext" in outcome.error
        assert not await ctx.chunk_repo.list_for_item(item.id)

    @pytest.mark.parametrize("item_type", ["folder", "url"])
    async def test_non_file_item_type_rejected_without_crashing(
        self, conn, ctx, tmp_path, item_type
    ) -> None:
        path = tmp_path / "whatever"
        item = await _make_kb_and_item(conn, path, item_type=item_type)

        outcome = await index_item(item, ctx)

        assert outcome.status == "failed"
        assert "not indexable" in outcome.error
        assert not await ctx.chunk_repo.list_for_item(item.id)

    async def test_generic_exception_caught_with_type_prefix_and_traceback_logged(
        self, conn, ctx, tmp_path, monkeypatch, caplog
    ) -> None:
        def _boom(*args, **kwargs):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(indexer_module, "chunk_text", _boom)
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)

        with caplog.at_level("ERROR"):
            outcome = await index_item(item, ctx)

        assert outcome.status == "failed"
        assert outcome.error == "RuntimeError: kaboom"
        assert any(
            record.levelname == "ERROR" and record.exc_info is not None for record in caplog.records
        )

    async def test_error_message_truncated_to_1000_chars(
        self, conn, ctx, tmp_path, monkeypatch
    ) -> None:
        def _boom(*args, **kwargs):
            raise RuntimeError("x" * 2000)

        monkeypatch.setattr(indexer_module, "chunk_text", _boom)
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)

        outcome = await index_item(item, ctx)

        assert outcome.status == "failed"
        assert len(outcome.error) == 1000

    async def test_vector_store_stale_error_propagates(
        self, conn, item_repo, chunk_repo, chunking, backend, tmp_path
    ) -> None:
        class _StaleStore(RecordingStore):
            async def upsert(self, kb_id, ids, vectors) -> None:
                raise VectorStoreStaleError("stale for test")

        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=_StaleStore(),
            backend=backend,
            chunking=chunking,
        )
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)

        with pytest.raises(VectorStoreStaleError):
            await index_item(item, ctx)

        stored = await item_repo.get(item.id)
        # chunks committed, item stays `indexing` — never `failed`.
        assert stored.status == "indexing"

    async def test_cancelled_error_propagates(self, conn, ctx, tmp_path, monkeypatch) -> None:
        def _raise_cancelled(texts):
            raise asyncio.CancelledError()

        monkeypatch.setattr(ctx.backend, "embed", _raise_cancelled)
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)

        with pytest.raises(asyncio.CancelledError):
            await index_item(item, ctx)

    async def test_kb_item_transition_error_from_stage_1_propagates(
        self, conn, ctx, tmp_path
    ) -> None:
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)
        # First call moves pending -> indexing; the item is now stuck at
        # `indexing` (never reaches `failed`/`indexed` since we bypass the
        # rest of the pipeline) — a second direct call hits
        # `indexing -> indexing`, which `KB_ITEM_TRANSITIONS` disallows.
        await ctx.item_repo.update_status(item.id, "indexing")

        with pytest.raises(KBItemTransitionError):
            await index_item(item, ctx)

    async def test_key_error_from_stage_1_propagates(self, conn, ctx, tmp_path) -> None:
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = KBItem(id="never-created", kb_id="nope", type="file", path_or_url=str(path))

        with pytest.raises(KeyError):
            await index_item(item, ctx)


# ── AC-6: zero-norm and truncated rows ──────────────────────────────────


class TestZeroNormAndTruncated:
    async def test_zero_norm_row_excluded_from_upsert(
        self, conn, item_repo, chunk_repo, tmp_path
    ) -> None:
        fixed_chunks = [
            ChunkRecord(seq=0, text="alpha", char_start=0, char_end=5),
            ChunkRecord(seq=1, text="beta", char_start=6, char_end=10),
            ChunkRecord(seq=2, text="gamma", char_start=11, char_end=16),
        ]

        class _OneZeroRowBackend:
            model_id = "one-zero-row"
            dim = 8

            def embed(self, texts):
                inner = StubEmbeddingBackend(dim=8).embed(texts)
                vectors = inner.vectors.copy()
                vectors[0] = 0.0
                return EmbedResult(vectors, inner.truncated)

        recording = RecordingStore()
        chunking = ChunkingSettings(size_chars=200, overlap_chars=20)
        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=recording,
            backend=_OneZeroRowBackend(),
            chunking=chunking,
        )
        with pytest.MonkeyPatch.context() as m:
            m.setattr(indexer_module, "chunk_text", lambda *a, **k: fixed_chunks)
            path = tmp_path / "doc.txt"
            path.write_text("irrelevant — chunk_text is patched")
            item = await _make_kb_and_item(conn, path)
            outcome = await index_item(item, ctx)

        assert outcome.chunks == 3
        assert outcome.vectors == 2
        rows = await chunk_repo.list_for_item(item.id)
        assert len(rows) == 3

        upserted_ids = {i for _, ids, _ in recording.upserts for i in ids}
        all_ids = {r.id for r in rows}
        zero_row_id = rows[0].id  # seq 0 == the zero row
        assert zero_row_id not in upserted_ids
        assert upserted_ids == all_ids - {zero_row_id}

    async def test_truncated_counted_and_logged(
        self, conn, item_repo, chunk_repo, tmp_path, caplog
    ) -> None:
        fixed_chunks = [
            ChunkRecord(seq=0, text="x" * 60, char_start=0, char_end=60),
            ChunkRecord(seq=1, text="y" * 60, char_start=60, char_end=120),
            ChunkRecord(seq=2, text="short", char_start=120, char_end=125),
        ]
        chunking = ChunkingSettings(size_chars=200, overlap_chars=20)
        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=RecordingStore(),
            backend=StubEmbeddingBackend(dim=8, truncate_over_chars=50),
            chunking=chunking,
        )
        with pytest.MonkeyPatch.context() as m:
            m.setattr(indexer_module, "chunk_text", lambda *a, **k: fixed_chunks)
            path = tmp_path / "doc.txt"
            path.write_text("irrelevant — chunk_text is patched")
            item = await _make_kb_and_item(conn, path)
            with caplog.at_level("INFO"):
                outcome = await index_item(item, ctx)

        assert outcome.truncated == 2
        assert any(
            record.levelname == "INFO"
            and item.id in record.getMessage()
            and "2" in record.getMessage()
            for record in caplog.records
        )


# ── AC-7: cooperative stop + embed_lock ──────────────────────────────────


class TestCooperativeStop:
    async def test_should_stop_checked_only_after_first_batch(
        self, conn, item_repo, chunk_repo, backend, tmp_path
    ) -> None:
        chunking = ChunkingSettings(size_chars=200, overlap_chars=20)
        recording = RecordingStore()
        calls = {"n": 0}

        def _should_stop() -> bool:
            calls["n"] += 1
            return calls["n"] >= 1  # stop as soon as it is ever consulted

        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=recording,
            backend=backend,
            chunking=chunking,
            should_stop=_should_stop,
            embed_batch=1,
        )
        # `_make_text()`'s default (6 paragraphs, 150 chars each) produces
        # several chunks at size_chars=200 — several batches at embed_batch=1.
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)

        outcome = await index_item(item, ctx)

        assert outcome.status == "stopped"
        assert outcome.chunks > 1
        assert len(recording.upserts) == 1  # only the first (unchecked) batch ran
        stored = await item_repo.get(item.id)
        assert stored.status == "indexing"
        # Chunks were committed even though embedding stopped early.
        assert len(await chunk_repo.list_for_item(item.id)) == outcome.chunks

    async def test_embed_lock_released_between_batches(
        self, conn, item_repo, chunk_repo, tmp_path
    ) -> None:
        chunking = ChunkingSettings(size_chars=200, overlap_chars=20)

        class _SlowBackend:
            model_id = "slow"
            dim = 8

            def embed(self, texts):
                time.sleep(0.01)
                return StubEmbeddingBackend(dim=8).embed(texts)

        lock = asyncio.Lock()
        acquisitions: list[float] = []
        stop_waiter = asyncio.Event()

        async def _waiter() -> None:
            while not stop_waiter.is_set():
                async with lock:
                    acquisitions.append(time.monotonic())
                await asyncio.sleep(0.001)

        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=RecordingStore(),
            backend=_SlowBackend(),
            chunking=chunking,
            embed_lock=lock,
            embed_batch=1,
        )
        path = tmp_path / "doc.txt"
        path.write_text(_make_text())
        item = await _make_kb_and_item(conn, path)

        waiter_task = asyncio.create_task(_waiter())
        try:
            outcome = await index_item(item, ctx)
        finally:
            stop_waiter.set()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(waiter_task, timeout=1)

        assert outcome.status == "awaiting_flush"
        assert outcome.chunks > 1
        # The waiter acquired the lock more than once during the run,
        # proving it was released between batches rather than held for
        # the whole item.
        assert len(acquisitions) >= 2


# ── AC-8: FlushPolicy ─────────────────────────────────────────────────────


class TestFlushPolicy:
    def test_no_flush_before_min_chunks(self) -> None:
        clock = {"t": 0.0}
        policy = FlushPolicy(min_chunks=2000, min_seconds=15.0, clock=lambda: clock["t"])
        policy.record_chunks(1999)
        clock["t"] = 1000.0
        assert policy.should_flush() is False

    def test_no_flush_before_min_seconds(self) -> None:
        clock = {"t": 0.0}
        policy = FlushPolicy(min_chunks=2000, min_seconds=15.0, clock=lambda: clock["t"])
        policy.record_chunks(5000)
        clock["t"] = 10.0
        assert policy.should_flush() is False
        clock["t"] = 15.0
        assert policy.should_flush() is True

    def test_after_flush_no_further_flush_until_save_multiplier_window_elapses(self) -> None:
        clock = {"t": 0.0}
        policy = FlushPolicy(
            min_chunks=2000, min_seconds=15.0, save_multiplier=10.0, clock=lambda: clock["t"]
        )
        policy.record_chunks(5000)
        clock["t"] = 15.0
        assert policy.should_flush() is True
        policy.record_flush(duration_seconds=5.0)  # last_flush_seconds = 5 -> window = 50s

        policy.record_chunks(20000)  # 10x min_chunks
        clock["t"] = 15.0 + 49.0
        assert policy.should_flush() is False
        clock["t"] = 15.0 + 50.0
        assert policy.should_flush() is True

    def test_module_constants_are_the_defaults(self) -> None:
        policy = FlushPolicy()
        assert policy.min_chunks == indexer_module.FLUSH_MIN_CHUNKS == 2000
        assert policy.min_seconds == indexer_module.FLUSH_MIN_SECONDS == 15.0
        assert policy.save_multiplier == indexer_module.FLUSH_SAVE_MULTIPLIER == 10.0


# ── AC-10: rebuild_kb ─────────────────────────────────────────────────────


class TestRebuildKb:
    async def test_rebuild_recovers_a_stale_kb(
        self, conn, item_repo, chunk_repo, chunking, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        store = UsearchStore(conn, dtype="f16", dim=8)
        await store.open()
        backend = StubEmbeddingBackend(dim=8)
        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=store,
            backend=backend,
            chunking=chunking,
        )

        kb_id = "kb-stale"
        await KnowledgeBaseRepository(conn).create(KnowledgeBase(id=kb_id, name=kb_id))
        item_ids = []
        for n in range(3):
            path = tmp_path / f"doc{n}.txt"
            path.write_text(_make_text(num_paragraphs=3, para_chars=80, doc=n))
            item = KBItem(id=f"item{n}", kb_id=kb_id, type="file", path_or_url=str(path))
            await item_repo.create(item)
            await index_item(item, ctx)
            item_ids.append(item.id)
        await store.flush(kb_id)

        total_chunks = 0
        known_chunk = None
        for item_id in item_ids:
            rows = await chunk_repo.list_for_item(item_id)
            total_chunks += len(rows)
            if known_chunk is None and rows:
                known_chunk = rows[0]

        # Destroy the sidecar so a fresh store detects staleness on first touch.
        (tmp_path / "vectors" / f"{kb_id}.usearch").unlink()
        fresh_store = UsearchStore(conn, dtype="f16", dim=8)
        await fresh_store.open()
        with pytest.raises(VectorStoreStaleError):
            await fresh_store.count(kb_id)

        rebuild_ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=fresh_store,
            backend=backend,
            chunking=chunking,
        )
        await rebuild_kb(kb_id, rebuild_ctx, reason="test stale recovery")

        assert await fresh_store.count(kb_id) == total_chunks

        assert known_chunk is not None
        query_vec = backend.embed([known_chunk.text]).vectors[0]
        results = await fresh_store.query(kb_id, query_vec, 1)
        assert results[0][0] == known_chunk.id

    async def test_rebuild_kb_generator_touches_only_chunk_repo_and_backend(
        self, conn, item_repo, chunk_repo, chunking, backend, tmp_path
    ) -> None:
        kb_id = "kb-touch"
        path = tmp_path / "doc.txt"
        path.write_text(_make_text(num_paragraphs=4, para_chars=60))
        real_store = RecordingStore()
        seed_ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=real_store,
            backend=backend,
            chunking=chunking,
        )
        item = await _make_kb_and_item(conn, path, kb_id=kb_id, item_id="item-touch")
        await index_item(item, seed_ctx)
        rows = await chunk_repo.list_for_item(item.id)
        assert rows

        only_rebuild = _OnlyRebuildStore()
        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=only_rebuild,
            backend=backend,
            chunking=chunking,
        )

        await rebuild_kb(kb_id, ctx, reason="unit test")

        total_ids = sum(len(ids) for ids, _ in only_rebuild.pages)
        assert total_ids == len(rows)

    async def test_rebuild_kb_on_empty_kb_yields_nothing(
        self, conn, item_repo, chunk_repo, chunking, backend, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        store = UsearchStore(conn, dtype="f16", dim=8)
        await store.open()
        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=store,
            backend=backend,
            chunking=chunking,
        )

        await rebuild_kb("empty-kb", ctx, reason="empty kb test")

        assert await store.count("empty-kb") == 0
