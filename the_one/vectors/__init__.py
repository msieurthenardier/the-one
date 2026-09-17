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
"""

from __future__ import annotations

import asyncio

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

__all__ = [
    "VectorStore",
    "VectorStoreBusyError",
    "VectorStoreError",
    "VectorStoreStaleError",
    "quantize_int8",
    "get_vector_store",
]

_store: VectorStore | None = None
_lock = asyncio.Lock()


def _build_store(
    vector_store_settings: VectorStoreSettings, conn: aiosqlite.Connection
) -> VectorStore:
    """Construct (but do not open) the backend named by ``vector_store_settings``.

    Lazy-imported, the ``create_pty_session`` dispatch shape. This is the
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


def _reset_for_test() -> None:
    """Clear the cached store. Test fixtures only.

    Mirrors ``the_one/embeddings/__init__.py``'s ``_reset_for_test`` and
    ``the_one/platform/sandbox/factory.py``'s reset seam.
    """
    global _store
    _store = None
