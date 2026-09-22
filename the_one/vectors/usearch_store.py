"""``UsearchStore`` — the ``usearch``-HNSW-backed ``VectorStore`` (Flight 2
Leg 4, DD-3/DD-4; the operator's DD-9 choice, closed out by Leg 6).

One HNSW index per knowledge base, persisted as a sidecar file
``{data_dir}/vectors/{kb_id}.usearch``, with a registry table
``kb_vector_index``. The table was store-owned (created inside ``open()``)
through Legs 4-5 while the backend choice was still open, so a losing
backend would never leave a dead table in a frozen migration forever; now
that ``usearch`` has won DD-9's benchmark comparison, Leg 6 moved the DDL
into the v41 migration block (``the_one/db/schema.py``) and ``open()``
issues no DDL at all. ``kb_chunks`` is the source of truth; the sidecar
is a cache. ``generation`` is bumped after every
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
import os
import time
from collections.abc import AsyncIterable, Sequence
from pathlib import Path
from typing import Literal

import aiosqlite
import numpy as np
from usearch.index import Index

from the_one.config import settings
from the_one.db._write_lock import write_transaction
from the_one.db.models import now_iso
from the_one.vectors._store import (
    VectorStoreBusyError,
    VectorStoreError,
    VectorStoreStaleError,
    quantize_int8,
)

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
        # `get_vector_store()` but before `open()` must be honoured. No DDL
        # here since Leg 6: `kb_vector_index` moved into the v41 migration
        # block once `usearch` won DD-9's benchmark comparison — see
        # `the_one/db/schema.py`'s v41 block.
        self._data_dir = settings.data_dir / "vectors"
        self._data_dir.mkdir(parents=True, exist_ok=True)

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

    def _tmp_path_for(self, kb_id: str) -> Path:
        """Same-directory temp path for ``_save_atomically``'s
        write-then-replace. Containment is already enforced by
        ``_path_for``'s resolved-path assert, since this is derived from
        its validated result."""
        return self._path_for(kb_id).with_suffix(".usearch.tmp")

    async def _save_atomically(self, index: Index, kb_id: str) -> tuple[Path, int]:
        """Save ``index`` to ``kb_id``'s sidecar path atomically.

        Writes to a temporary file in the same directory, then
        ``os.replace``s it over the real path — a crash or exception
        mid-save never corrupts or truncates the previous sidecar, since
        the replace is the only step that touches the real path and it is
        atomic on both POSIX and Windows (verified: ``Index.restore``
        never memory-maps, so nothing keeps the destination file open for
        ``os.replace`` to fail against). On any failure before the
        replace, the temporary file is removed on a best-effort basis (a
        crash before this line leaves a ``.usearch.tmp`` file the next
        successful save simply overwrites — no cleanup pass needed) and
        the previous sidecar is left untouched. Returns the real path and
        the index length, for the caller's registry-row upsert.
        """
        path = self._path_for(kb_id)
        tmp = self._tmp_path_for(kb_id)
        try:
            await asyncio.to_thread(index.save, str(tmp))
            await asyncio.to_thread(os.replace, tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        return path, len(index)

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

        try:
            index = await asyncio.to_thread(Index.restore, str(path))
        except Exception as exc:
            # `Index.restore` raises three different exception types for
            # one condition depending on how the sidecar is corrupt
            # (`ValueError` on garbage bytes or an empty file, `RuntimeError`
            # on a truncated file — verified at Leg 6 design), so this must
            # catch the base `Exception`, not a specific class.
            entry.stale = True
            raise VectorStoreStaleError(
                self._stale_message(
                    kb_id, f"sidecar unreadable ({exc.__class__.__name__}: {exc}) at {path}"
                )
            ) from exc
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

    def _check_dim(self, vectors: np.ndarray, kb_id: str) -> None:
        """Squawk 0054: cheap shape-only guard (a ``.shape`` read, no copy)
        that ``vectors``' last axis matches ``self.dim``, called before
        quantisation/index insertion in ``upsert``, ``query``, and
        ``rebuild_from``. A wrong-width vector would otherwise reach
        ``usearch`` silently (or fail deep inside the C extension with an
        opaque error) instead of raising a clear, actionable ``ValueError``
        naming the expected/actual dim and the offending ``kb_id``.
        """
        width = vectors.shape[-1]
        if width != self.dim:
            raise ValueError(f"vector width {width} != expected dim {self.dim} for kb_id={kb_id!r}")

    async def upsert(self, kb_id: str, ids: Sequence[int], vectors: np.ndarray) -> None:
        id_list = list(ids)
        if not id_list:
            return
        self._check_dim(vectors, kb_id)
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

            # DD-7 (Flight 3 Leg 2): `dirty` is set BEFORE the mutation,
            # not after — a `to_thread` call that raises partway through
            # (e.g. after `remove` but during `add`) must still leave the
            # in-memory index marked dirty, since it may already have been
            # partially mutated. Setting `dirty` only after a successful
            # `to_thread` would let such a failure leave `dirty` False
            # with a silently-mutated index that the next `flush` skips.
            entry.dirty = True
            await asyncio.to_thread(_do_upsert, entry.index)

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
            # DD-7: same reordering rationale as `upsert` above — `dirty`
            # is set before the `to_thread` mutation, after the
            # `entry.index is None` early return (nothing to mark dirty
            # for an index that was never loaded).
            entry.dirty = True
            await asyncio.to_thread(entry.index.remove, keys)

    async def delete_kb(self, kb_id: str) -> None:
        # Guard-first (Leg 6, flight-end review condition #3): the
        # write_transaction that removes the registry row runs BEFORE any
        # in-memory or filesystem mutation. A caller who nests this call
        # inside their own `write_transaction` gets the re-entry
        # `RuntimeError` here, before anything has changed — not after the
        # in-memory entry was already popped and the sidecar already
        # unlinked (the pre-Leg-6 ordering, where the guard fired only
        # after the mutation had happened).
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM kb_vector_index WHERE kb_id = ?", (kb_id,))
        entry = self._kbs.get(kb_id)
        if entry is not None:
            async with entry.lock:
                self._kbs.pop(kb_id, None)
        path = self._path_for(kb_id)
        path.unlink(missing_ok=True)

    async def query(
        self, kb_id: str, vector: np.ndarray, k: int, *, timeout: float | None = None
    ) -> list[tuple[int, float]]:
        """Query ``kb_id``'s index for ``vector``'s ``k`` nearest neighbours.

        ``timeout`` is **keyword-only** (so an existing positional call like
        ``store.query("kb", vec, 1)`` keeps working, and no future caller
        can confuse it with ``k``) and bounds ONLY the wait to acquire
        ``entry.lock`` — never the work done while holding it (Flight 5
        Leg 1, DD-1). **This is a corrected design**: an earlier draft
        wrapped the whole call in ``asyncio.wait_for``, and a probe proved
        that wrong before it shipped — ``async with entry.lock: await
        asyncio.to_thread(entry.index.search, ...)`` means cancelling the
        outer await releases the caller AND the lock while the pool thread
        is still executing against ``entry.index``; the next holder
        (``upsert``, ``flush``, ``rebuild_from``) then mutates an index a
        live thread is reading. Measured: caller released and lock free at
        0.302s, next holder acquired at 0.302s, escaped thread still
        running until 1.502s. So the bound covers only the waiter: the
        timed acquire sits OUTSIDE the ``try`` below, and ``finally:
        entry.lock.release()`` therefore runs only when the lock was
        actually acquired — an acquire placed inside the ``try`` would
        raise ``RuntimeError: Lock is not acquired`` from the ``finally``
        on every timeout, masking the real ``VectorStoreBusyError``.
        Nothing in-lock is ever cancelled; a cold-start
        ``_ensure_loaded``/``Index.restore`` remains unbounded even with a
        ``timeout`` set, because it runs after the lock is already held.
        """
        self._check_dim(vector, kb_id)
        entry = self._entry(kb_id)
        if timeout is None:
            await entry.lock.acquire()
        else:
            start = time.monotonic()
            try:
                await asyncio.wait_for(entry.lock.acquire(), timeout=timeout)
            except TimeoutError:
                elapsed = time.monotonic() - start
                logger.warning(
                    "kb %s: query timed out waiting for the per-KB lock after "
                    "%.3fs (timeout=%.3fs) — a genuine deadlock now degrades "
                    "quietly, so treat this as the operator-visible signal",
                    kb_id,
                    elapsed,
                    timeout,
                )
                raise VectorStoreBusyError(
                    f"vector store busy for kb_id={kb_id!r}: could not acquire "
                    f"the per-KB lock within {timeout}s"
                ) from None
        try:
            await self._ensure_loaded(entry, kb_id, create=False)
            if entry.index is None or len(entry.index) == 0:
                return []
            vec = self._maybe_quantize(np.asarray(vector))
            matches = await asyncio.to_thread(entry.index.search, vec, k)
        finally:
            entry.lock.release()
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
        """Persist ``kb_id``'s in-memory index if dirty: an atomic save
        (``_save_atomically``) followed by a registry-row upsert.

        These are two separate steps, by design (DD-3): the registry write
        happens only after the sidecar replace succeeds. A crash between
        the two leaves the sidecar one generation ahead of the registry,
        which ``_ensure_loaded``'s count check reports as stale — this is
        a fail-safe window, recoverable by ``rebuild_from``, not a defect.

        On any failure inside ``_save_atomically`` (the save itself, or the
        ``os.replace``), the exception propagates out of this method, the
        previous sidecar is left untouched, and ``entry.dirty`` stays
        ``True`` — the ``= False`` line below is reached only after the
        registry row has landed — so the next ``flush()`` or ``close()``
        retries the save.
        """
        entry = self._kbs.get(kb_id)
        if entry is None or not entry.dirty:
            return
        async with entry.lock:
            if not entry.dirty or entry.index is None:
                entry.dirty = False
                return
            path, count = await self._save_atomically(entry.index, kb_id)
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
        self, kb_id: str, ids_and_vectors: AsyncIterable[tuple[Sequence[int], np.ndarray]]
    ) -> None:
        """Rebuild ``kb_id``'s index from scratch and clear any staleness.

        Flight 3's re-embed-every-chunk recovery path for a KB that
        ``_ensure_loaded`` marked stale. Builds a brand new index (never
        reuses a stale in-memory one), saves it, and upserts the registry
        row — clearing ``entry.stale`` on success.

        ``ids_and_vectors`` is an ``AsyncIterable`` (Flight 3 DD-6): a 3M-
        chunk knowledge base cannot be pre-embedded into memory (3M x 512 x
        4 bytes is 6 GB), so this iterates the caller's async generator
        (``async for``) while holding ``entry.lock`` for the whole rebuild.
        See the ``VectorStore`` Protocol docstring's no-call-back
        invariant: the generator may only read ``kb_chunks`` and embed —
        never call back into this store, which would deadlock against the
        lock held here.
        """
        entry = self._entry(kb_id)
        async with entry.lock:
            index = Index(ndim=self.dim, metric="cos", dtype=self.dtype)
            async for ids, vectors in ids_and_vectors:
                id_list = list(ids)
                if not id_list:
                    continue
                self._check_dim(vectors, kb_id)
                keys = np.asarray(id_list, dtype=np.uint64)
                vecs = self._maybe_quantize(np.asarray(vectors))
                await asyncio.to_thread(index.add, keys, vecs)

            path, count = await self._save_atomically(index, kb_id)
            await self._upsert_registry_row(kb_id, path, count)
            entry.index = index
            entry.dirty = False
            entry.stale = False

    async def close(self, *, skip_kb_ids: frozenset[str] | set[str] = frozenset()) -> None:
        """Flush every dirty knowledge base under its own ``try/except``
        (one failure never aborts the rest), except those named in
        ``skip_kb_ids`` — the vector-store shutdown hook's DD-3a cancel
        skip set (Mission 24 Flight 7 Leg 1). Does not clear ``self._kbs``
        or mark the store closed, so a second call re-flushes only the
        knowledge bases whose first flush failed (``flush``'s own
        not-dirty early return makes that a no-op otherwise)."""
        for kb_id in list(self._kbs.keys()):
            if kb_id in skip_kb_ids:
                continue
            try:
                await self.flush(kb_id)
            except Exception:
                logger.exception("usearch flush-on-close failed for kb %s", kb_id)
