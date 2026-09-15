"""Vector-store seam (Flight 2 Leg 4, DD-3/DD-4/DD-10/DD-13).

``VectorStore`` is a vectors-and-integer-ids-only Protocol: every id
crossing the seam is a ``kb_chunks.id`` value (``AUTOINCREMENT``, never
recycled — Leg 1, DD-5), and no chunk text or metadata ever crosses. Both
concrete backends (``SqliteVecStore``, ``UsearchStore``) satisfy this
Protocol STRUCTURALLY (``structural-Protocol-satisfaction`` — no
inheritance); ``isinstance(store, VectorStore)`` works because
``runtime_checkable`` checks member presence at call time.

**Contract**

- ``upsert(kb_id, ids, vectors)`` means "remove any of ``ids`` already
  present, then insert" — neither backend has a native upsert (an
  ``INSERT OR REPLACE`` into ``vec0`` fails its primary-key constraint;
  ``usearch.Index.add`` raises on a duplicate key).
- **Write ordering (DD-3)**: chunks + their FTS rows commit first (the
  chunk repository, Leg 2); vectors are written after, via this seam; an
  item's status flips to ``indexed`` only once the vectors have *landed*
  — see the ``flush`` rule below. A crash between the two leaves an item
  ``indexing`` (requeued by the DD-5 transition table), never an
  ``indexed`` item with no vectors.
- **``flush`` rule**: ``usearch`` cannot save its HNSW index on every
  ``upsert`` at scale (a save is O(N)), so "vectors landed" means
  *flushed*, not merely upserted — Flight 3's pipeline calls
  ``flush(kb_id)`` before it moves an item to ``indexed``.
  ``SqliteVecStore.flush`` is a no-op; its writes commit on ``upsert``.
  An ``upsert`` without a following ``flush``, observed through a FRESH
  ``UsearchStore`` instance (a process restart, or a second store built
  over the same connection), does not see the new vectors — documented
  behaviour, not a bug.
- **Both stores acquire the shared write lock themselves**
  (``the_one/db/_write_lock.py``, DD-13) for every one of their own
  writes. A caller must NEVER wrap a store call inside its own
  ``write_transaction`` block — the guard is not re-entrant and raises
  ``RuntimeError`` on same-task re-entry. This is also why the write
  ordering above is always two transactions, never one.
- ``query(kb_id, vector, k)`` returns ``(id, cosine_distance)`` pairs,
  best (smallest distance) first.
- **``vec0`` rowids are unique TABLE-WIDE, not per partition** (verified):
  a shared test suite exercising both ``kb_a`` and ``kb_b`` must use
  disjoint id ranges, exactly as production does (every id comes from one
  global ``kb_chunks.id`` sequence) — reusing an id across two KBs in a
  test raises ``UNIQUE constraint failed`` for the sqlite-vec cells while
  the usearch cells (keyed per-KB-index, not table-wide) pass, silently
  masking the difference.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import numpy as np


class VectorStoreError(Exception):
    """Raised when the vector store cannot be opened or used at all (e.g.
    the host's ``sqlite3`` build lacks ``enable_load_extension``)."""


class VectorStoreMismatchError(VectorStoreError):
    """Raised from ``open()`` when the live on-disk shape (the
    ``kb_vectors`` DDL, or a usearch registry row) disagrees with the
    configured ``knowledge.vector_store`` setting — dtype or dimension."""


class VectorStoreStaleError(VectorStoreError):
    """Raised by ``UsearchStore`` when a knowledge base's sidecar index
    file is missing, or disagrees with its registry row (count/dtype/dim)
    — every operation except ``rebuild_from`` and ``delete_kb`` refuses
    until the KB is rebuilt."""


@runtime_checkable
class VectorStore(Protocol):
    """Structural contract both ``SqliteVecStore`` and ``UsearchStore``
    satisfy without inheriting from this class. See the module docstring
    for the full contract (write ordering, ``flush``, the write-lock rule,
    the disjoint-id-range rule for tests)."""

    backend: str
    dtype: str
    dim: int

    async def open(self) -> None: ...

    async def upsert(self, kb_id: str, ids: Sequence[int], vectors: np.ndarray) -> None: ...

    async def delete(self, kb_id: str, ids: Sequence[int]) -> None: ...

    async def delete_kb(self, kb_id: str) -> None: ...

    async def query(self, kb_id: str, vector: np.ndarray, k: int) -> list[tuple[int, float]]: ...

    async def count(self, kb_id: str) -> int: ...

    async def flush(self, kb_id: str) -> None: ...

    async def close(self) -> None: ...


def quantize_int8(vectors: np.ndarray) -> np.ndarray:
    """Quantize (approximately) unit-norm float vectors to the int8 range
    both int8 cells share (sqlite-vec's ``int8`` column, usearch's ``i8``
    dtype) — shared here so the two backends quantise identically.

    ``np.clip(np.rint(v * 127), -127, 127).astype(np.int8)`` — the
    ``.astype(np.int8)`` cast is load-bearing: without it the array stays
    float and ``sqlite_vec.serialize_int8(q.tolist())`` raises
    ``struct.error`` (its ``pack("%sb", ...)`` format needs Python
    ``int``s, and a numpy float array's ``.tolist()`` yields Python
    floats, not ints, until the array itself is integer-typed).

    Input is documented to be (approximately) unit-norm; a non-unit-norm
    vector is clipped to +/-127 rather than re-normalized.
    """
    return np.clip(np.rint(vectors * 127), -127, 127).astype(np.int8)
