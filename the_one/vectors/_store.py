"""Vector-store seam (Flight 2 Leg 4, DD-3/DD-4/DD-10/DD-13; ``usearch``-only
since Leg 6, DD-9).

``VectorStore`` is a vectors-and-integer-ids-only Protocol: every id
crossing the seam is a ``kb_chunks.id`` value (``AUTOINCREMENT``, never
recycled — Leg 1, DD-5), and no chunk text or metadata ever crosses.
``UsearchStore`` satisfies this Protocol STRUCTURALLY
(``structural-Protocol-satisfaction`` — no inheritance);
``isinstance(store, VectorStore)`` works because ``runtime_checkable``
checks member presence at call time.

**Contract**

- ``upsert(kb_id, ids, vectors)`` means "remove any of ``ids`` already
  present, then insert" — ``usearch.Index.add`` raises on a duplicate key
  (no native upsert).
- **Write ordering (DD-3)**: chunks + their FTS rows commit first (the
  chunk repository, Leg 2); vectors are written after, via this seam; an
  item's status flips to ``indexed`` only once the vectors have *landed*
  — see the ``flush`` rule below. A crash between the two leaves an item
  ``indexing`` (requeued by the DD-5 transition table), never an
  ``indexed`` item with no vectors.
- **``flush`` rule**: ``usearch`` cannot save its HNSW index on every
  ``upsert`` at scale (a save is O(N)), so "vectors landed" means
  *flushed*, not merely upserted — Flight 3's pipeline calls
  ``flush(kb_id)`` before it moves an item to ``indexed``. An ``upsert``
  without a following ``flush``, observed through a FRESH ``UsearchStore``
  instance (a process restart, or a second store built over the same
  connection), does not see the new vectors — documented behaviour, not a
  bug.
- **The store acquires the shared write lock itself**
  (``the_one/db/_write_lock.py``, DD-13) for every one of its own writes.
  A caller must NEVER wrap a store call inside its own
  ``write_transaction`` block — the guard is not re-entrant and raises
  ``RuntimeError`` on same-task re-entry. This is also why the write
  ordering above is always two transactions, never one.
- ``query(kb_id, vector, k)`` returns ``(id, cosine_distance)`` pairs,
  best (smallest distance) first.
- **Dimension guard (squawk 0054)**: a vector whose last dimension
  != ``dim`` raises ``ValueError`` naming the expected/actual dim and the
  ``kb_id`` — checked in ``upsert``, ``query``, and ``rebuild_from``,
  before quantisation.
- **Ids are disjoint across knowledge bases by convention, not by a
  per-partition namespace**: every id comes from one global
  ``kb_chunks.id`` (``AUTOINCREMENT``) sequence, so two knowledge bases
  never share an id even though each ``usearch`` index is a separate
  per-KB sidecar file. A shared test suite exercising both ``kb_a`` and
  ``kb_b`` must still use disjoint id ranges to mirror production, even
  though a per-KB index would not itself raise on a repeated id across
  two different KBs.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Sequence
from typing import Protocol, runtime_checkable

import numpy as np


class VectorStoreError(Exception):
    """Raised when the vector store cannot be opened or used at all (e.g.
    the host's ``sqlite3`` build lacks ``enable_load_extension``)."""


class VectorStoreStaleError(VectorStoreError):
    """Raised by ``UsearchStore`` when a knowledge base's sidecar index
    file is missing, or disagrees with its registry row (count/dtype/dim)
    — every operation except ``rebuild_from`` and ``delete_kb`` refuses
    until the KB is rebuilt."""


@runtime_checkable
class VectorStore(Protocol):
    """Structural contract ``UsearchStore`` satisfies without inheriting
    from this class — the seam keeps this shape for a future second
    backend. See the module docstring for the full contract (write
    ordering, ``flush``, the write-lock rule, the disjoint-id-range rule
    for tests)."""

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

    async def rebuild_from(
        self, kb_id: str, ids_and_vectors: AsyncIterable[tuple[Sequence[int], np.ndarray]]
    ) -> None:
        """Rebuild ``kb_id``'s index from scratch, streamed, and clear any
        staleness (Flight 3 DD-6's ``VectorStoreStaleError`` recovery — the
        pipeline cannot pre-embed a whole knowledge base into memory).

        **No-call-back invariant**: the store iterates ``ids_and_vectors``
        (an ``async for``) while holding its per-KB lock, so the caller's
        generator may only READ ``kb_chunks`` and embed — it must never
        call back into this store (``count``, ``flush``, another
        ``upsert``, …), which would deadlock against the very lock this
        method holds. A backend that needs no rebuild may implement this
        as a no-op that clears staleness.
        """
        ...

    async def close(self) -> None: ...


def quantize_int8(vectors: np.ndarray) -> np.ndarray:
    """Quantize (approximately) unit-norm float vectors to the int8 range
    ``UsearchStore``'s ``i8`` dtype cell uses.

    ``np.clip(np.rint(v * 127), -127, 127).astype(np.int8)`` — the
    ``.astype(np.int8)`` cast is load-bearing: ``usearch.Index.add`` does
    NOT raise on a float array holding already-quantised integer values —
    it silently re-scales a float input into the index's ``i8`` range a
    second time, corrupting the stored vector (verified: an un-cast float
    array and its ``.astype(np.int8)`` twin land as visibly different
    stored values through ``Index.get``). Passing an already-``int8``
    array skips that second scaling.

    Input is documented to be (approximately) unit-norm; a non-unit-norm
    vector is clipped to +/-127 rather than re-normalized.
    """
    return np.clip(np.rint(vectors * 127), -127, 127).astype(np.int8)
