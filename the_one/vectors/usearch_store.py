"""``UsearchStore`` — the ``usearch``-HNSW-backed ``VectorStore`` (Flight 2
Leg 4, DD-3/DD-4).

One HNSW index per knowledge base, persisted as a sidecar file
``{data_dir}/vectors/{kb_id}.usearch``, with a store-owned registry table
``kb_vector_index`` created by ``open()`` (store-owned rather than
migration-owned — Leg 6 moves the DDL into a versioned migration only if
this backend wins DD-9's benchmark comparison). ``kb_chunks`` is the source
of truth; the sidecar is a cache. ``generation`` is bumped after every
successful ``flush``; a mismatch between the registry row and the restored
index (missing file, wrong count, wrong dtype/dim) marks the knowledge base
stale — every read/write except ``rebuild_from`` and ``delete_kb`` then
raises ``VectorStoreStaleError`` until the caller rebuilds it.

**Per-KB concurrency**: an in-memory ``dict[kb_id, _KbIndex]`` holds one
``asyncio.Lock`` per knowledge base so unrelated KBs never block each
other. The dict entry (and its lock) is get-or-created SYNCHRONOUSLY via
``dict.setdefault`` — with no ``await`` between the membership check and
the insert — before anything ever awaits on the lock; the lock cannot
guard its own creation, so the synchronous ``setdefault`` is what makes
concurrent first-touches of the same ``kb_id`` safe.

**``flush`` is what advances ``generation`` and ``count``** (DD-3): an
``upsert`` marks the in-memory index dirty and saves nothing to disk;
``upsert`` without a following ``flush``, observed through a fresh store
instance (a different connection-holder, or this store reopened), does
not see the new vectors. This is documented behaviour, not a bug — Leg 4's
benchmark cost of a ``save()`` at scale is why ``usearch`` cannot save on
every ``upsert``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

import aiosqlite
import numpy as np
from usearch.index import Index

from the_one.config import settings
from the_one.db._write_lock import write_transaction
from the_one.db.models import now_iso
from the_one.vectors._store import VectorStoreError, VectorStoreStaleError, quantize_int8

logger = logging.getLogger(__name__)

_VALID_DTYPES = ("f16", "i8")


@dataclasses.dataclass
class _KbIndex:
    """Per-knowledge-base in-memory state."""

    index: Index | None
    lock: asyncio.Lock
    dirty: bool = False
    stale: bool = False


class UsearchStore:
    """``VectorStore`` over one ``usearch`` HNSW index per knowledge base.

    Structurally satisfies the ``VectorStore`` Protocol (no inheritance,
    per ``structural-Protocol-satisfaction``).
    """

    backend = "usearch"

    def __init__(
        self,
        conn: aiosqlite.Connection,
        *,
        dtype: Literal["f16", "i8"],
        dim: int = 512,
    ) -> None:
        if dtype not in _VALID_DTYPES:
            raise ValueError(f"UsearchStore dtype must be one of {_VALID_DTYPES}, got {dtype!r}")
        self.conn = conn
        self.dtype = dtype
        self.dim = dim
        self._data_dir: Path | None = None
        self._kbs: dict[str, _KbIndex] = {}

    async def open(self) -> None:
        # `data_dir` is resolved HERE, not at construction (DD-3) — a
        # test's `settings.data_dir` monkeypatch applied after
        # `get_vector_store()` but before `open()` must be honoured.
        self._data_dir = settings.data_dir / "vectors"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        async with write_transaction(self.conn):
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS kb_vector_index ("
                "kb_id TEXT PRIMARY KEY, "
                "path TEXT NOT NULL, "
                "count INTEGER NOT NULL, "
                "generation INTEGER NOT NULL, "
                "dtype TEXT NOT NULL, "
                "dim INTEGER NOT NULL, "
                "updated_at TEXT NOT NULL)"
            )

    def _path_for(self, kb_id: str) -> Path:
        assert self._data_dir is not None, "UsearchStore.open() was never called"
        candidate = (self._data_dir / f"{kb_id}.usearch").resolve()
        # Leg 5 review fix (BLOCKING 2), defence in depth: `KnowledgeBase.id`
        # is validated to a filename-safe charset at the model layer
        # (`the_one/db/models.py`), but this store must not trust that a
        # caller always went through that validator — assert the resolved
        # candidate never escapes `self._data_dir` (e.g. via a `kb_id` of
        # `"../../../evil"`) before it is ever used to open/create a file.
        data_dir_resolved = self._data_dir.resolve()
        if not candidate.is_relative_to(data_dir_resolved):
            raise VectorStoreError(
                f"refusing to build a vector-store path outside {data_dir_resolved} "
                f"for kb_id={kb_id!r}"
            )
        return candidate

    def _entry(self, kb_id: str) -> _KbIndex:
        """Get-or-create the in-memory entry for ``kb_id``.

        Synchronous and lock-free by design: ``dict.setdefault`` has no
        ``await`` between its membership check and its insert, so two
        concurrent first-touches of the same ``kb_id`` still land on the
        SAME ``_KbIndex`` (and therefore the same lock) rather than racing
        to create two independent ones.
        """
        return self._kbs.setdefault(kb_id, _KbIndex(index=None, lock=asyncio.Lock()))

    async def _registry_row(self, kb_id: str) -> aiosqlite.Row | None:
        async with self.conn.execute(
            "SELECT path, count, generation, dtype, dim FROM kb_vector_index WHERE kb_id = ?",
            (kb_id,),
        ) as cur:
            return await cur.fetchone()

    async def _ensure_loaded(self, entry: _KbIndex, kb_id: str, *, create: bool) -> None:
        """Load ``entry.index`` from the registry/sidecar if not already
        loaded. Must be called while holding ``entry.lock``.

        Marks ``entry.stale`` and raises ``VectorStoreStaleError`` on any
        of: a registry row whose sidecar file is missing, an index whose
        length disagrees with the registry's ``count``, or a registry row
        whose ``dtype``/``dim`` disagree with this store's configuration.
        A KB with no registry row at all is simply empty (not stale); a
        fresh index is created only when ``create`` is true.
        """
        if entry.stale:
            raise VectorStoreStaleError(self._stale_message(kb_id, "previously detected as stale"))
        if entry.index is not None:
            return

        row = await self._registry_row(kb_id)
        if row is None:
            if create:
                entry.index = Index(ndim=self.dim, metric="cos", dtype=self.dtype)
            return

        path = Path(row["path"])
        if not path.exists():
            entry.stale = True
            raise VectorStoreStaleError(self._stale_message(kb_id, f"sidecar file missing: {path}"))

        index = await asyncio.to_thread(Index.restore, str(path))
        if len(index) != row["count"]:
            entry.stale = True
            raise VectorStoreStaleError(
                self._stale_message(
                    kb_id, f"index length {len(index)} != registry count {row['count']}"
                )
            )
        if row["dtype"] != self.dtype or row["dim"] != self.dim:
            entry.stale = True
            raise VectorStoreStaleError(
                self._stale_message(
                    kb_id,
                    f"registry dtype/dim ({row['dtype']}/{row['dim']}) != configured "
                    f"({self.dtype}/{self.dim})",
                )
            )
        entry.index = index

    @staticmethod
    def _stale_message(kb_id: str, reason: str) -> str:
        return (
            f"usearch index for knowledge base {kb_id!r} is stale ({reason}) — "
            "call rebuild_from() to recover"
        )

    def _maybe_quantize(self, vectors: np.ndarray) -> np.ndarray:
        vectors = np.asarray(vectors, dtype=np.float32)
        if self.dtype == "i8":
            return quantize_int8(vectors)
        return vectors

    async def upsert(self, kb_id: str, ids: Sequence[int], vectors: np.ndarray) -> None:
        id_list = list(ids)
        if not id_list:
            return
        # Acquire-and-release (DD-13): this enforces the no-nesting rule
        # (a caller who wraps this call in its OWN `write_transaction` gets
        # the `RuntimeError` re-entry guard, never a silent bypass) without
        # holding the single process-wide write lock for the duration of
        # the in-memory index mutation below, which never touches SQL —
        # only `flush()`/`delete_kb()` persist anything through this lock.
        async with write_transaction(self.conn):
            pass
        entry = self._entry(kb_id)
        async with entry.lock:
            await self._ensure_loaded(entry, kb_id, create=True)
            assert entry.index is not None
            keys = np.asarray(id_list, dtype=np.uint64)
            vecs = self._maybe_quantize(np.asarray(vectors))

            def _do_upsert(index: Index) -> None:
                # `remove` of an absent key returns without raising
                # (verified) — safe to call unconditionally rather than
                # checking `contains` first.
                index.remove(keys)
                index.add(keys, vecs)

            await asyncio.to_thread(_do_upsert, entry.index)
            entry.dirty = True

    async def delete(self, kb_id: str, ids: Sequence[int]) -> None:
        id_list = list(ids)
        if not id_list:
            return
        # Same acquire-and-release rationale as `upsert` above.
        async with write_transaction(self.conn):
            pass
        entry = self._entry(kb_id)
        async with entry.lock:
            await self._ensure_loaded(entry, kb_id, create=False)
            if entry.index is None:
                return
            keys = np.asarray(id_list, dtype=np.uint64)
            await asyncio.to_thread(entry.index.remove, keys)
            entry.dirty = True

    async def delete_kb(self, kb_id: str) -> None:
        entry = self._kbs.get(kb_id)
        if entry is not None:
            async with entry.lock:
                self._kbs.pop(kb_id, None)
        path = self._path_for(kb_id)
        if path.exists():
            path.unlink()
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM kb_vector_index WHERE kb_id = ?", (kb_id,))

    async def query(self, kb_id: str, vector: np.ndarray, k: int) -> list[tuple[int, float]]:
        entry = self._entry(kb_id)
        async with entry.lock:
            await self._ensure_loaded(entry, kb_id, create=False)
            if entry.index is None or len(entry.index) == 0:
                return []
            vec = self._maybe_quantize(np.asarray(vector))
            matches = await asyncio.to_thread(entry.index.search, vec, k)
        return [
            (int(key), float(dist))
            for key, dist in zip(matches.keys, matches.distances, strict=True)
        ]

    async def count(self, kb_id: str) -> int:
        entry = self._entry(kb_id)
        async with entry.lock:
            await self._ensure_loaded(entry, kb_id, create=False)
            if entry.index is None:
                return 0
            return len(entry.index)

    async def flush(self, kb_id: str) -> None:
        entry = self._kbs.get(kb_id)
        if entry is None or not entry.dirty:
            return
        async with entry.lock:
            if not entry.dirty or entry.index is None:
                entry.dirty = False
                return
            path = self._path_for(kb_id)
            await asyncio.to_thread(entry.index.save, str(path))
            count = len(entry.index)
            await self._upsert_registry_row(kb_id, path, count)
            entry.dirty = False

    async def _upsert_registry_row(self, kb_id: str, path: Path, count: int) -> None:
        row = await self._registry_row(kb_id)
        generation = (row["generation"] + 1) if row is not None else 1
        async with write_transaction(self.conn):
            await self.conn.execute(
                "INSERT INTO kb_vector_index"
                "(kb_id, path, count, generation, dtype, dim, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(kb_id) DO UPDATE SET "
                "path = excluded.path, count = excluded.count, generation = excluded.generation, "
                "dtype = excluded.dtype, dim = excluded.dim, updated_at = excluded.updated_at",
                (kb_id, str(path), count, generation, self.dtype, self.dim, now_iso()),
            )

    async def rebuild_from(
        self, kb_id: str, ids_and_vectors: Iterable[tuple[Sequence[int], np.ndarray]]
    ) -> None:
        """Rebuild ``kb_id``'s index from scratch and clear any staleness.

        Flight 3's re-embed-every-chunk recovery path for a KB that
        ``_ensure_loaded`` marked stale. Builds a brand new index (never
        reuses a stale in-memory one), saves it, and upserts the registry
        row — clearing ``entry.stale`` on success.
        """
        entry = self._entry(kb_id)
        async with entry.lock:
            index = Index(ndim=self.dim, metric="cos", dtype=self.dtype)
            for ids, vectors in ids_and_vectors:
                id_list = list(ids)
                if not id_list:
                    continue
                keys = np.asarray(id_list, dtype=np.uint64)
                vecs = self._maybe_quantize(np.asarray(vectors))
                await asyncio.to_thread(index.add, keys, vecs)

            path = self._path_for(kb_id)
            await asyncio.to_thread(index.save, str(path))
            count = len(index)
            await self._upsert_registry_row(kb_id, path, count)
            entry.index = index
            entry.dirty = False
            entry.stale = False

    async def close(self) -> None:
        for kb_id in list(self._kbs.keys()):
            try:
                await self.flush(kb_id)
            except Exception:
                logger.exception("usearch flush-on-close failed for kb %s", kb_id)
