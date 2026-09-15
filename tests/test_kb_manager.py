"""Tests for ``the_one/knowledge/manager.py`` (Flight 3 Leg 3, DD-7):
``IndexingManager``'s worker pass, folder walk/reconcile, flush cadence
integration, cooperative stop + cancel fallback, stale-sidecar recovery,
``drain`` concurrency, and ``start_all``.

Every seam-consumer test here runs against
``tests/_embedding_stub.py::StubEmbeddingBackend`` and a real
``UsearchStore`` on ``tmp_path`` — never a real model load (confined to
``tests/test_doctor_embedding_model.py``) and never wall-clock sleeps for
test-side synchronisation (``wait_until_idle``/events only; a plain
``time.sleep`` is used only inside the fake-slow backends below, which run
under ``asyncio.to_thread`` exactly like the real embedding backend).
"""

from __future__ import annotations

import asyncio
import queue
import time

import aiosqlite
import pytest

from tests._embedding_stub import StubEmbeddingBackend
from the_one.config import settings
from the_one.db._kb_types import ChunkRecord, KBItemTransitionError
from the_one.db._write_lock import reset_for_test as reset_write_lock
from the_one.db._write_lock import write_transaction
from the_one.db.models import KBItem, KnowledgeBase
from the_one.db.repositories import (
    AppMetadataRepository,
    KBChunkRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
)
from the_one.db.schema import ensure_schema
from the_one.knowledge import manager as manager_mod
from the_one.knowledge.indexer import FlushPolicy, IndexContext
from the_one.knowledge.manager import IndexingManager, _WorkerEntry
from the_one.knowledge.settings import (
    VECTOR_STORE_KEY,
    ChunkingSettings,
    KnowledgeSettings,
    save_knowledge_settings,
)
from the_one.knowledge.walk import DiscoveredFile, ReconcilePlan, content_hash
from the_one.vectors import _reset_for_test as reset_vectors_module
from the_one.vectors._store import VectorStoreStaleError
from the_one.vectors.usearch_store import UsearchStore


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Mirrors ``tests/test_kb_indexer.py``'s autouse reset."""
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


def _make_conn_factory(conn):
    async def _f():
        return conn

    return _f


def _make_store_factory(store):
    async def _f():
        return store

    return _f


def _make_backend_factory(backend):
    def _f():
        return backend

    return _f


async def _make_kb(kb_repo, kb_id: str = "kb1") -> KnowledgeBase:
    kb = KnowledgeBase(id=kb_id, name=kb_id)
    await kb_repo.create(kb)
    return kb


async def _set_small_chunking(conn) -> None:
    """Small chunking settings so short fixture text produces several
    chunks — used by tests that need multi-batch items."""
    await save_knowledge_settings(
        conn, KnowledgeSettings(chunking=ChunkingSettings(size_chars=200, overlap_chars=20))
    )


def _make_manager(conn, store, backend, **kwargs) -> IndexingManager:
    return IndexingManager(
        conn_factory=_make_conn_factory(conn),
        store_factory=_make_store_factory(store),
        backend_factory=_make_backend_factory(backend),
        **kwargs,
    )


def _make_text(num_paragraphs: int = 8, para_chars: int = 150, *, doc: int = 0) -> str:
    return "\n\n".join(
        f"doc{doc} paragraph {i} " + ("x" * para_chars) for i in range(num_paragraphs)
    )


class _StoreSlot:
    """A mutable indirection so a test can swap the store an in-progress
    manager's NEXT ``_resources()``/``_flush()`` call resolves — simulates
    "a fresh store instance" (a process restart) without breaking a
    single pass's own store continuity (production's real
    ``get_vector_store()`` singleton never changes mid-pass either)."""

    def __init__(self, store) -> None:
        self.store = store

    async def __call__(self):
        return self.store


# ── AC-1: manager shape / lifecycle basics ─────────────────────────────────


class TestManagerLifecycleBasics:
    def test_state_of_never_started_kb_is_idle(self) -> None:
        manager = IndexingManager()
        assert manager.state("nope") == "idle"

    async def test_wait_until_idle_of_never_started_kb_returns_immediately(self) -> None:
        manager = IndexingManager()
        await manager.wait_until_idle("nope", timeout=1.0)

    async def test_stop_of_unknown_kb_is_a_noop(self) -> None:
        manager = IndexingManager()
        await manager.stop("nope")  # must not raise

    async def test_module_accessor_round_trips(self) -> None:
        manager = IndexingManager()
        assert manager_mod.get_manager() is None
        manager_mod.set_manager(manager)
        try:
            assert manager_mod.get_manager() is manager
        finally:
            manager_mod.set_manager(None)


# ── AC-2: the pass ───────────────────────────────────────────────────────


class TestPass:
    async def test_folder_fixture_indexes_every_file(
        self, conn, kb_repo, item_repo, chunk_repo, store, backend, tmp_path
    ) -> None:
        kb = await _make_kb(kb_repo)
        folder = tmp_path / "docs"
        folder.mkdir()
        (folder / "a.txt").write_text("hello world")
        (folder / "b.md").write_text("# heading\n\nbody text")

        await item_repo.create(
            KBItem(id="folder1", kb_id=kb.id, type="folder", path_or_url=str(folder))
        )

        manager = _make_manager(conn, store, backend)
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)

        assert manager.state(kb.id) == "idle"
        folder_item = await item_repo.get("folder1")
        assert folder_item.status == "indexed"
        assert folder_item.indexed_at is not None

        children = await item_repo.list_children("folder1")
        assert len(children) == 2
        for child in children:
            assert child.status == "indexed"
            assert child.content_hash is not None

        assert await chunk_repo.count_for_kb(kb.id) > 0

    async def test_dormant_url_folder_and_broken_file_still_reaches_idle(
        self, conn, kb_repo, item_repo, store, backend, tmp_path, monkeypatch
    ) -> None:
        kb = await _make_kb(kb_repo)
        await item_repo.create(
            KBItem(id="url1", kb_id=kb.id, type="url", path_or_url="https://example.com")
        )
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()
        await item_repo.create(
            KBItem(id="folder1", kb_id=kb.id, type="folder", path_or_url=str(empty_folder))
        )
        broken_path = tmp_path / "broken.txt"
        broken_path.write_text("hello")
        await item_repo.create(
            KBItem(id="broken", kb_id=kb.id, type="file", path_or_url=str(broken_path))
        )

        real_update_status = KBItemRepository.update_status

        async def _flaky_update_status(self, item_id, status, *, error=None):
            if item_id == "broken" and status == "indexing":
                raise KBItemTransitionError("pending->indexing (simulated)")
            return await real_update_status(self, item_id, status, error=error)

        monkeypatch.setattr(KBItemRepository, "update_status", _flaky_update_status)

        manager = _make_manager(conn, store, backend)
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)

        assert manager.state(kb.id) == "idle"
        # "broken" never left pending — the KBItemTransitionError was
        # caught and logged, not left to crash the pass.
        broken = await item_repo.get("broken")
        assert broken.status == "pending"
        url_item = await item_repo.get("url1")
        assert url_item.status == "pending"  # dormant, never touched

    async def test_bounded_fallback_indexes_good_items_past_a_stuck_cluster(
        self, conn, kb_repo, item_repo, store, backend, tmp_path, monkeypatch
    ) -> None:
        """AC-2: pending_page=2, three items that can never leave pending
        (an "indexing" transition monkeypatched to raise for them) and two
        good items — both good items must index within a single pass, via
        the one-full-read-per-pass bounded fallback."""
        kb = await _make_kb(kb_repo)
        stuck_ids = {"stuck0", "stuck1", "stuck2"}
        for sid in sorted(stuck_ids):
            path = tmp_path / f"{sid}.txt"
            path.write_text("stuck content")
            await item_repo.create(KBItem(id=sid, kb_id=kb.id, type="file", path_or_url=str(path)))
        good_ids = ["good0", "good1"]
        for gid in good_ids:
            path = tmp_path / f"{gid}.txt"
            path.write_text(f"good content for {gid}")
            await item_repo.create(KBItem(id=gid, kb_id=kb.id, type="file", path_or_url=str(path)))

        real_update_status = KBItemRepository.update_status

        async def _flaky_update_status(self, item_id, status, *, error=None):
            if item_id in stuck_ids and status == "indexing":
                raise KBItemTransitionError("pending->indexing (simulated stuck)")
            return await real_update_status(self, item_id, status, error=error)

        monkeypatch.setattr(KBItemRepository, "update_status", _flaky_update_status)

        manager = _make_manager(conn, store, backend, pending_page=2)
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)

        assert manager.state(kb.id) == "idle"
        for gid in good_ids:
            good = await item_repo.get(gid)
            assert good.status == "indexed", f"{gid} should have indexed in this pass"
        for sid in stuck_ids:
            stuck = await item_repo.get(sid)
            assert stuck.status == "pending"


# ── AC-2: reconcile application ─────────────────────────────────────────


class TestApplyReconcile:
    def _ctx(self, conn, item_repo, chunk_repo, store, backend) -> IndexContext:
        return IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=store,
            backend=backend,
            chunking=ChunkingSettings(),
        )

    async def test_new_files_create_pending_children_with_null_identity(
        self, conn, kb_repo, item_repo, chunk_repo, store, backend, tmp_path
    ) -> None:
        kb = await _make_kb(kb_repo)
        await item_repo.create(
            KBItem(id="folder1", kb_id=kb.id, type="folder", path_or_url=str(tmp_path))
        )
        ctx = self._ctx(conn, item_repo, chunk_repo, store, backend)
        manager = IndexingManager()

        disc = DiscoveredFile(path=str(tmp_path / "new.txt"), size_bytes=10, mtime=123.0)
        plan = ReconcilePlan(new=[disc], removed=[], changed=[], unchanged=0)
        await manager._apply_reconcile(kb.id, "folder1", plan, ctx)

        children = await item_repo.list_children("folder1")
        assert len(children) == 1
        child = children[0]
        assert child.path_or_url == disc.path
        assert child.status == "pending"
        assert child.size_bytes is None
        assert child.mtime is None
        assert child.content_hash is None

    async def test_removed_files_delete_item_and_call_store_delete(
        self, conn, kb_repo, item_repo, chunk_repo, store, backend, tmp_path
    ) -> None:
        kb = await _make_kb(kb_repo)
        await item_repo.create(
            KBItem(id="folder1", kb_id=kb.id, type="folder", path_or_url=str(tmp_path))
        )
        gone_path = tmp_path / "gone.txt"
        await item_repo.create(
            KBItem(
                id="gone", kb_id=kb.id, parent_id="folder1", type="file", path_or_url=str(gone_path)
            )
        )
        ids = await chunk_repo.replace_item_chunks(
            "gone", kb.id, [ChunkRecord(seq=0, text="bye", char_start=0, char_end=3)]
        )

        deletes: list[tuple[str, list[int]]] = []
        real_delete = store.delete

        async def _spy_delete(kb_id, item_ids):
            deletes.append((kb_id, list(item_ids)))
            return await real_delete(kb_id, item_ids)

        store.delete = _spy_delete

        ctx = self._ctx(conn, item_repo, chunk_repo, store, backend)
        manager = IndexingManager()

        removed_item = await item_repo.get("gone")
        plan = ReconcilePlan(new=[], removed=[removed_item], changed=[], unchanged=0)
        await manager._apply_reconcile(kb.id, "folder1", plan, ctx)

        with pytest.raises(KeyError):
            await item_repo.get("gone")
        assert deletes == [(kb.id, ids)]

    async def test_changed_and_different_requeues_only_from_indexed_or_failed(
        self, conn, kb_repo, item_repo, chunk_repo, store, backend, tmp_path
    ) -> None:
        kb = await _make_kb(kb_repo)
        await item_repo.create(
            KBItem(id="folder1", kb_id=kb.id, type="folder", path_or_url=str(tmp_path))
        )
        ctx = self._ctx(conn, item_repo, chunk_repo, store, backend)
        manager = IndexingManager()

        for item_id, start_status in (
            ("indexed_item", "indexed"),
            ("failed_item", "failed"),
            ("pending_item", "pending"),
        ):
            path = tmp_path / f"{item_id}.txt"
            path.write_text("new content on disk")
            await item_repo.create(
                KBItem(
                    id=item_id,
                    kb_id=kb.id,
                    parent_id="folder1",
                    type="file",
                    path_or_url=str(path),
                )
            )
            if start_status != "pending":
                async with write_transaction(conn):
                    await conn.execute(
                        "UPDATE kb_items SET status=? WHERE id=?", (start_status, item_id)
                    )
            await item_repo.set_content_identity(
                item_id, content_hash="stale-old-hash", size_bytes=1, mtime=1.0
            )
            st = path.stat()
            disc = DiscoveredFile(path=str(path), size_bytes=st.st_size, mtime=st.st_mtime)
            item = await item_repo.get(item_id)
            plan = ReconcilePlan(new=[], removed=[], changed=[(item, disc)], unchanged=0)
            await manager._apply_reconcile(kb.id, "folder1", plan, ctx)

        indexed_after = await item_repo.get("indexed_item")
        assert indexed_after.status == "pending"
        failed_after = await item_repo.get("failed_item")
        assert failed_after.status == "pending"
        pending_after = await item_repo.get("pending_item")
        assert pending_after.status == "pending"  # untouched, no transition attempted

    async def test_changed_but_identical_updates_identity_without_status_change(
        self, conn, kb_repo, item_repo, chunk_repo, store, backend, tmp_path
    ) -> None:
        kb = await _make_kb(kb_repo)
        await item_repo.create(
            KBItem(id="folder1", kb_id=kb.id, type="folder", path_or_url=str(tmp_path))
        )
        path = tmp_path / "same.txt"
        path.write_text("identical content")
        digest = content_hash(path)
        await item_repo.create(
            KBItem(
                id="same_item",
                kb_id=kb.id,
                parent_id="folder1",
                type="file",
                path_or_url=str(path),
            )
        )
        async with write_transaction(conn):
            await conn.execute("UPDATE kb_items SET status='indexed' WHERE id=?", ("same_item",))
        await item_repo.set_content_identity(
            "same_item", content_hash=digest, size_bytes=1, mtime=1.0
        )

        ctx = self._ctx(conn, item_repo, chunk_repo, store, backend)
        manager = IndexingManager()
        item = await item_repo.get("same_item")
        st = path.stat()
        disc = DiscoveredFile(path=str(path), size_bytes=st.st_size, mtime=st.st_mtime)
        plan = ReconcilePlan(new=[], removed=[], changed=[(item, disc)], unchanged=0)
        await manager._apply_reconcile(kb.id, "folder1", plan, ctx)

        after = await item_repo.get("same_item")
        assert after.status == "indexed"  # untouched — not re-indexed
        assert after.content_hash == digest
        assert after.size_bytes == disc.size_bytes
        assert after.mtime == disc.mtime


# ── AC-3: flush and flip ────────────────────────────────────────────────


class TestFlushAndFlip:
    async def test_small_gates_flush_per_item(
        self, conn, kb_repo, item_repo, chunk_repo, store, backend, tmp_path
    ) -> None:
        kb = await _make_kb(kb_repo)
        for name in ("one", "two"):
            path = tmp_path / f"{name}.txt"
            path.write_text(f"short content {name}")
            await item_repo.create(KBItem(id=name, kb_id=kb.id, type="file", path_or_url=str(path)))

        flush_calls: list[str] = []
        real_flush = store.flush

        async def _spy_flush(kb_id):
            flush_calls.append(kb_id)
            return await real_flush(kb_id)

        store.flush = _spy_flush

        manager = _make_manager(
            conn,
            store,
            backend,
            flush_min_chunks=1,
            flush_min_seconds=0.0,
            flush_save_multiplier=0.0,
        )
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)

        assert len(flush_calls) >= 2
        for name in ("one", "two"):
            item = await item_repo.get(name)
            assert item.status == "indexed"

    async def test_large_gates_flush_once_at_pass_end(
        self, conn, kb_repo, item_repo, chunk_repo, store, backend, tmp_path
    ) -> None:
        kb = await _make_kb(kb_repo)
        for name in ("one", "two"):
            path = tmp_path / f"{name}.txt"
            path.write_text(f"short content {name}")
            await item_repo.create(KBItem(id=name, kb_id=kb.id, type="file", path_or_url=str(path)))

        flush_calls: list[str] = []
        real_flush = store.flush

        async def _spy_flush(kb_id):
            flush_calls.append(kb_id)
            return await real_flush(kb_id)

        store.flush = _spy_flush

        manager = _make_manager(
            conn,
            store,
            backend,
            flush_min_chunks=1_000_000,
            flush_min_seconds=1_000_000.0,
            flush_save_multiplier=1_000_000.0,
        )
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)

        assert len(flush_calls) == 1
        for name in ("one", "two"):
            item = await item_repo.get(name)
            assert item.status == "indexed"


# ── AC-4: stale recovery ─────────────────────────────────────────────────


class _AlwaysStaleStore:
    """A store whose ``upsert``/``delete`` always raise
    ``VectorStoreStaleError`` and whose ``rebuild_from`` always raises —
    the AC-4 "rebuild itself raises" test needs no real staleness
    mechanics, just a store that guarantees both."""

    backend = "always-stale"
    dtype = "f16"
    dim = 8

    async def open(self) -> None:
        return None

    async def upsert(self, kb_id, ids, vectors) -> None:
        raise VectorStoreStaleError("simulated stale for rebuild-failure test")

    async def delete(self, kb_id, ids) -> None:
        return None

    async def delete_kb(self, kb_id) -> None:
        return None

    async def query(self, kb_id, vector, k):
        return []

    async def count(self, kb_id) -> int:
        return 0

    async def flush(self, kb_id) -> None:
        return None

    async def rebuild_from(self, kb_id, ids_and_vectors) -> None:
        raise RuntimeError("simulated rebuild failure")

    async def close(self) -> None:
        return None


class TestStaleRecovery:
    async def test_deleted_sidecar_is_rebuilt_and_pass_restarts_to_indexed(
        self, conn, kb_repo, item_repo, chunk_repo, backend, tmp_path, monkeypatch, caplog
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        kb = await _make_kb(kb_repo)
        for name in ("one", "two"):
            path = tmp_path / f"{name}.txt"
            path.write_text(f"content for {name}")
            await item_repo.create(KBItem(id=name, kb_id=kb.id, type="file", path_or_url=str(path)))

        store1 = UsearchStore(conn, dtype="f16", dim=8)
        await store1.open()
        slot = _StoreSlot(store1)

        manager = IndexingManager(
            conn_factory=_make_conn_factory(conn),
            store_factory=slot,
            backend_factory=_make_backend_factory(backend),
        )
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)
        assert manager.state(kb.id) == "idle"
        for name in ("one", "two"):
            assert (await item_repo.get(name)).status == "indexed"

        # Simulate a process restart discovering the sidecar gone: delete
        # the file and swap in a FRESH UsearchStore instance (an existing
        # store instance's per-KB entry is cached in memory and would
        # never re-check the sidecar).
        sidecar = tmp_path / "vectors" / f"{kb.id}.usearch"
        assert sidecar.exists()
        sidecar.unlink()
        store2 = UsearchStore(conn, dtype="f16", dim=8)
        await store2.open()
        slot.store = store2

        # An operator's scope=all reindex (or the equivalent direct call)
        # is what would organically re-touch the store for an already-
        # indexed KB — this is the real trigger DD-6 describes.
        await item_repo.requeue_for_reindex(kb.id)

        with caplog.at_level("WARNING"):
            manager.request_index(kb.id)
            await manager.wait_until_idle(kb.id, timeout=10.0)

        assert manager.state(kb.id) == "idle"
        for name in ("one", "two"):
            assert (await item_repo.get(name)).status == "indexed"

        expected_count = await chunk_repo.count_for_kb(kb.id)
        assert await store2.count(kb.id) == expected_count
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any("rebuilding vector index" in r.message for r in warnings)

    async def test_rebuild_failure_fails_current_item_and_stops_then_recovers(
        self, conn, kb_repo, item_repo, backend, tmp_path, caplog
    ) -> None:
        kb = await _make_kb(kb_repo)
        path = tmp_path / "doc.txt"
        path.write_text("some content")
        await item_repo.create(KBItem(id="item1", kb_id=kb.id, type="file", path_or_url=str(path)))

        always_stale = _AlwaysStaleStore()
        manager = IndexingManager(
            conn_factory=_make_conn_factory(conn),
            store_factory=_make_store_factory(always_stale),
            backend_factory=_make_backend_factory(backend),
        )

        with caplog.at_level("ERROR"):
            manager.request_index(kb.id)
            await manager.wait_until_idle(kb.id, timeout=10.0)

        assert manager.state(kb.id) == "stopped"
        item = await item_repo.get("item1")
        assert item.status == "failed"
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert errors

        # A later request_index restarts the worker rather than staying
        # permanently wedged — swap in a working store first.
        real_store = UsearchStore(conn, dtype="f16", dim=8)
        await real_store.open()
        manager._store_factory = _make_store_factory(real_store)  # test-only swap
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)
        assert manager.state(kb.id) == "idle"


# ── AC-5: cooperative stop and the cancel fallback ──────────────────────


class _SlowBackend:
    """``embed()`` puts a sentinel on ``started`` (a thread-safe queue)
    before a real (short) blocking sleep — a test awaits ``started`` via
    ``asyncio.to_thread`` rather than a wall-clock sleep of its own."""

    dim = 8

    def __init__(self, delay: float = 0.05) -> None:
        self.model_id = "slow-stub"
        self._delay = delay
        self._stub = StubEmbeddingBackend(dim=8)
        self.started: queue.Queue = queue.Queue()

    def embed(self, texts):
        self.started.put(None)
        time.sleep(self._delay)
        return self._stub.embed(texts)


class _BlockingBackend:
    """``embed()`` ignores cooperative stop entirely — blocks far past
    any reasonable ``stop_timeout`` (AC-5's cancel-fallback test hook)."""

    dim = 8

    def __init__(self, delay: float = 2.0) -> None:
        self.model_id = "blocking-stub"
        self._delay = delay
        self._stub = StubEmbeddingBackend(dim=8)
        self.started = queue.Queue()

    def embed(self, texts):
        self.started.put(None)
        time.sleep(self._delay)
        return self._stub.embed(texts)


class TestCooperativeStopAndCancelFallback:
    async def test_cooperative_stop_finishes_current_items_chunks_and_flushes_prior(
        self, conn, kb_repo, item_repo, chunk_repo, store, tmp_path
    ) -> None:
        await _set_small_chunking(conn)
        kb = await _make_kb(kb_repo)

        # "a" is a single-batch item that completes (and, with a small
        # flush gate, self-flushes) before "b" — the slow item — starts.
        path_a = tmp_path / "a.txt"
        path_a.write_text("short")
        item_a = KBItem(id="a", kb_id=kb.id, type="file", path_or_url=str(path_a))
        await item_repo.create(item_a)

        path_b = tmp_path / "b.txt"
        path_b.write_text(_make_text(num_paragraphs=8))
        item_b = KBItem(id="b", kb_id=kb.id, type="file", path_or_url=str(path_b))
        await item_repo.create(item_b)

        backend = _SlowBackend(delay=0.05)
        manager = IndexingManager(
            conn_factory=_make_conn_factory(conn),
            store_factory=_make_store_factory(store),
            backend_factory=_make_backend_factory(backend),
            embed_batch=1,
            flush_min_chunks=1,
            flush_min_seconds=0.0,
            flush_save_multiplier=0.0,
            stop_timeout=5.0,
            shutdown_flush_timeout=5.0,
        )
        manager.request_index(kb.id)

        # "a"'s one embed call, then "b"'s first embed call.
        await asyncio.to_thread(backend.started.get, True, 5.0)
        await asyncio.to_thread(backend.started.get, True, 5.0)

        start = time.monotonic()
        await manager.stop(kb.id)
        elapsed = time.monotonic() - start
        assert elapsed < 3.0, "cooperative stop should return well within the budget"

        stored_a = await item_repo.get("a")
        assert stored_a.status == "indexed"
        stored_b = await item_repo.get("b")
        assert stored_b.status == "indexing"
        b_chunks = await chunk_repo.list_for_item("b")
        assert len(b_chunks) > 0  # chunks committed even though not flushed

        # A later request_index requeues and finishes "b".
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)
        stored_b_after = await item_repo.get("b")
        assert stored_b_after.status == "indexed"

    async def test_cancel_fallback_leaves_item_indexing_and_next_pass_finishes_it(
        self, conn, kb_repo, item_repo, chunk_repo, store, tmp_path
    ) -> None:
        kb = await _make_kb(kb_repo)
        path = tmp_path / "doc.txt"
        path.write_text("content that ignores stop")
        await item_repo.create(KBItem(id="item1", kb_id=kb.id, type="file", path_or_url=str(path)))

        blocking_backend = _BlockingBackend(delay=2.0)
        manager = IndexingManager(
            conn_factory=_make_conn_factory(conn),
            store_factory=_make_store_factory(store),
            backend_factory=_make_backend_factory(blocking_backend),
            stop_timeout=0.2,
        )
        manager.request_index(kb.id)
        await asyncio.to_thread(blocking_backend.started.get, True, 5.0)

        await manager.stop(kb.id)
        assert manager.state(kb.id) == "stopped"
        stuck = await item_repo.get("item1")
        assert stuck.status == "indexing"

        fast_backend = StubEmbeddingBackend(dim=8)
        manager._backend_factory = _make_backend_factory(fast_backend)  # test-only swap
        manager.request_index(kb.id)
        await manager.wait_until_idle(kb.id, timeout=10.0)

        finished = await item_repo.get("item1")
        assert finished.status == "indexed"


# ── AC-6: drain ──────────────────────────────────────────────────────────


class TestDrain:
    async def test_drain_stops_workers_concurrently(self) -> None:
        manager = IndexingManager()

        async def _pretend_worker(entry: _WorkerEntry) -> None:
            await asyncio.sleep(0.3)
            entry.state = "idle"
            entry.idle.set()

        for kb_id in ("kb-a", "kb-b", "kb-c"):
            entry = _WorkerEntry(
                task=None,
                wake=asyncio.Event(),
                idle=asyncio.Event(),
                stop_requested=False,
                state="running",
                awaiting_flush=[],
                policy=FlushPolicy(),
            )
            entry.task = asyncio.create_task(_pretend_worker(entry))
            manager._entries[kb_id] = entry

        start = time.monotonic()
        await manager.drain()
        elapsed = time.monotonic() - start

        assert elapsed < 0.9, "concurrent drain should be well under the serial 3x0.3s bound"
        assert manager._entries == {}

    async def test_drain_of_empty_manager_is_a_noop(self) -> None:
        manager = IndexingManager()
        await manager.drain()  # must not raise
        assert manager._entries == {}


# ── AC-7: start_all ──────────────────────────────────────────────────────


class TestStartAll:
    async def test_requeues_stranded_across_kbs_and_resumes_them_to_indexed(
        self, conn, kb_repo, item_repo, store, backend, tmp_path
    ) -> None:
        kb1 = await _make_kb(kb_repo, "kb1")
        kb2 = await _make_kb(kb_repo, "kb2")

        for kb, name in ((kb1, "i1"), (kb2, "i2")):
            path = tmp_path / f"{name}.txt"
            path.write_text(f"content {name}")
            await item_repo.create(KBItem(id=name, kb_id=kb.id, type="file", path_or_url=str(path)))

        async with write_transaction(conn):
            await conn.execute("UPDATE kb_items SET status='indexing' WHERE id IN ('i1', 'i2')")

        manager = _make_manager(conn, store, backend)
        await manager.start_all()
        await manager.wait_until_idle(kb1.id, timeout=10.0)
        await manager.wait_until_idle(kb2.id, timeout=10.0)

        assert (await item_repo.get("i1")).status == "indexed"
        assert (await item_repo.get("i2")).status == "indexed"

    async def test_vector_store_settings_written_only_if_absent(
        self, conn, kb_repo, store, backend
    ) -> None:
        from the_one.knowledge.settings import VectorStoreSettings

        meta_repo = AppMetadataRepository(conn)
        existing = VectorStoreSettings(dtype="i8", dim=8, model_id="some-other-model")
        raw_before = existing.model_dump_json()
        await meta_repo.set(VECTOR_STORE_KEY, raw_before)

        manager = _make_manager(conn, store, backend)
        await manager.start_all()

        raw_after = await meta_repo.get(VECTOR_STORE_KEY)
        assert raw_after == raw_before  # byte-identical — never overwritten

    async def test_vector_store_settings_written_when_absent(
        self, conn, kb_repo, store, backend
    ) -> None:
        meta_repo = AppMetadataRepository(conn)
        assert await meta_repo.get(VECTOR_STORE_KEY) is None

        manager = _make_manager(conn, store, backend)
        await manager.start_all()

        raw_after = await meta_repo.get(VECTOR_STORE_KEY)
        assert raw_after is not None
        assert '"backend":"usearch"' in raw_after or '"backend": "usearch"' in raw_after

    async def test_kb_with_no_folders_or_pending_items_gets_no_worker(
        self, conn, kb_repo, store, backend
    ) -> None:
        kb = await _make_kb(kb_repo)
        manager = _make_manager(conn, store, backend)
        await manager.start_all()
        assert manager.state(kb.id) == "idle"
