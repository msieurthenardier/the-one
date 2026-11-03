"""Vector-store dispatch + process-wide singleton (Flight 2 Leg 4, DD-3;
``usearch``-only since Leg 6, DD-9).

Mirrors ``the_one/embeddings/__init__.py``'s ``get_embedding_backend()``
double-checked-locking shape, but ``get_vector_store()`` is ASYNC — a
documented departure from ``create_pty_session``'s sync dispatch
(``the_one/platform/pty.py:130-163``), because the vector-store choice is
a DB record (``knowledge.vector_store``) that can only be read with an
``await``.

``_build_store()`` is a named seam: it constructs (but does not open) the
backend named by a ``VectorStoreSettings``, lazy-importing the backend
module (one today; the seam keeps its shape for a future second one).
Tests targeting the delete-route wiring (AC-11) monkeypatch this exact
function to inject a recording stub store that satisfies ``VectorStore``
structurally.

``get_vector_store()`` reads the setting, builds the store, ``open()``s
it, and caches the result — callers never need to call ``open()``
themselves. ``_reset_for_test()`` clears the cache: ``data_dir`` is
resolved inside ``UsearchStore.open()``, so a test's
``settings.data_dir`` monkeypatch applied AFTER an earlier test already
cached a store would otherwise never take effect (and could write
sidecars into the operator's real data directory).

``close_vector_store()`` (Mission 24 Flight 7 Leg 1, DD-3/DD-3a) is the
shutdown-side mirror: it closes the cached store IF ONE WAS BUILT and
never builds one to close it — an instance that never touched a
knowledge base has ``_store is None`` and this returns without touching
disk. Shares ``_clear_cache()`` with ``_reset_for_test()`` rather than
letting the two cache-clears drift.
"""

from __future__ import annotations

import asyncio
import logging

import aiosqlite

from the_one.db.connection import get_connection
from the_one.knowledge.settings import VectorStoreSettings, load_vector_store_settings
from the_one.vectors._store import (
    VectorStore,
    VectorStoreBusyError,
    VectorStoreError,
    VectorStoreStaleError,
    quantize_int8,
)

logger = logging.getLogger(__name__)

__all__ = [
    "VectorStore",
    "VectorStoreBusyError",
    "VectorStoreError",
    "VectorStoreStaleError",
    "quantize_int8",
    "get_vector_store",
    "close_vector_store",
]

_store: VectorStore | None = None
_lock = asyncio.Lock()


def _build_store(
    vector_store_settings: VectorStoreSettings, conn: aiosqlite.Connection
) -> VectorStore:
    """Construct (but do not open) the one production backend, ``UsearchStore``.

    ``dtype`` and ``dim`` come from ``vector_store_settings``; its ``.backend``
    is not read (there is only one backend, so it is not yet a dispatch key).
    Lazy-imported. This is the
    named seam AC-11's test monkeypatches to inject a recording stub
    store.
    """
    from the_one.vectors.usearch_store import UsearchStore

    return UsearchStore(conn, dtype=vector_store_settings.dtype, dim=vector_store_settings.dim)


async def get_vector_store() -> VectorStore:
    """Return the process-wide vector store, building + opening it on
    first call. Double-checked under ``_lock`` so two concurrent first
    callers still build (and open) exactly once."""
    global _store
    if _store is not None:
        return _store
    async with _lock:
        if _store is None:
            conn = await get_connection()
            vector_store_settings = await load_vector_store_settings(conn)
            store = _build_store(vector_store_settings, conn)
            await store.open()
            _store = store
        return _store


def _clear_cache() -> None:
    """Drop the cached store reference. Shared by ``_reset_for_test()`` and
    ``close_vector_store()`` so the two cache-clears cannot drift apart."""
    global _store
    _store = None


def _reset_for_test() -> None:
    """Clear the cached store. Test fixtures only.

    Mirrors ``the_one/embeddings/__init__.py``'s ``_reset_for_test`` and
    ``the_one/platform/sandbox/factory.py``'s reset seam.
    """
    _clear_cache()


async def close_vector_store(*, skip_kb_ids: frozenset[str] | set[str] = frozenset()) -> None:
    """Shutdown hook (Mission 24 Flight 7 Leg 1, DD-3/DD-3a). Closes the
    process-wide vector store if one was built; NEVER calls
    ``get_vector_store()`` and so never builds one just to close it — when
    ``_store is None`` (no knowledge base was ever touched this process)
    this returns immediately, with no disk access at all.

    ``skip_kb_ids`` names knowledge bases whose most recent
    ``IndexingManager.stop()`` took the cancel fallback (DD-3a,
    ``IndexingManager.cancelled_kb_ids()``): cancelling that task releases
    the per-KB lock while the worker thread may still be mutating the
    index (``usearch_store.py``'s ``upsert`` holds the lock across an
    ``asyncio.to_thread`` call), so flushing one right after would race a
    live mutation and tear the on-disk index. Each skipped kb_id is
    logged at WARNING so the lost write is visible rather than silent —
    it is recoverable by re-indexing; a torn index is not.

    Idempotent: closing an already-closed (or never-opened) store is a
    no-op, and a second call after a failed flush only re-flushes the
    knowledge bases that failed (``UsearchStore.flush``'s own
    not-dirty early return).
    """
    global _store
    if _store is None:
        return
    for kb_id in skip_kb_ids:
        logger.warning(
            "vector store shutdown: kb_id=%s not flushed — a cancelled "
            "mutation may still be running (DD-3a)",
            kb_id,
        )
    store = _store
    await store.close(skip_kb_ids=frozenset(skip_kb_ids))
    _clear_cache()
