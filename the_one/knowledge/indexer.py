"""The per-item indexing pipeline (Flight 3 Leg 2, DD-5): ``index_item``
runs Flight 2's write ordering (chunks + FTS commit first, vectors after,
via the store) for the first time, ``FlushPolicy`` is the flush-cadence
policy object, and ``rebuild_kb`` is DD-6's stale-sidecar recovery.

**Nothing in this module runs unless a test or Leg 3's ``IndexingManager``
calls it** — no worker, no lifespan wiring, no route lives here.

See ``the_one/agents.md``'s "Knowledge indexing" section (Knowledge
storage) for the full contract: the eight ``index_item`` stages in order,
the "item stays ``indexing`` until the flush that covers it" rule,
``FlushPolicy``'s three constants and the resulting re-work window, zero-
norm/``truncated`` handling, ``rebuild_kb`` as the only stale recovery,
and the lock-ordering invariant.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np

from the_one.embeddings._backend import NORM_TOLERANCE, EmbeddingBackend
from the_one.knowledge.chunking import chunk_text
from the_one.knowledge.extractors import ExtractionError, extractor_for
from the_one.knowledge.settings import ChunkingSettings
from the_one.knowledge.walk import content_hash
from the_one.vectors._store import VectorStore, VectorStoreStaleError

if TYPE_CHECKING:
    import aiosqlite

    from the_one.db.models import KBItem
    from the_one.db.repositories import KBChunkRepository, KBItemRepository

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

MAX_FILE_BYTES = 10 * 1024 * 1024
EMBED_BATCH = 256
FLUSH_MIN_CHUNKS = 2000
FLUSH_MIN_SECONDS = 15.0
FLUSH_SAVE_MULTIPLIER = 10.0
_ERROR_MAX_CHARS = 1000
_BINARY_SNIFF_BYTES = 8192

# A genuine zero-norm row (the seam's documented zero-token edge — text
# that tokenises to nothing) has norm ~0; a unit row has norm ~1, so any
# threshold in (1e-6, 0.9) classifies identically. Reusing the seam's own
# tolerance constant here is deliberate rather than inventing a second one
# for the same distinction.
_ZERO_NORM_THRESHOLD = NORM_TOLERANCE

__all__ = [
    "MAX_FILE_BYTES",
    "EMBED_BATCH",
    "FLUSH_MIN_CHUNKS",
    "FLUSH_MIN_SECONDS",
    "FLUSH_SAVE_MULTIPLIER",
    "IndexContext",
    "ItemOutcome",
    "index_item",
    "FlushPolicy",
    "rebuild_kb",
    "is_binary_head",
]


def is_binary_head(path: Path) -> bool:
    """Heuristic binary-file detection: read up to ``_BINARY_SNIFF_BYTES``
    and check for any null byte. The ``the_one/tools/filesystem.py::
    _is_binary`` rule, re-implemented here (four lines) rather than
    imported — that helper is a tool-config concern, this is an indexing
    concern."""
    with path.open("rb") as f:
        chunk = f.read(_BINARY_SNIFF_BYTES)
    return b"\x00" in chunk


@dataclasses.dataclass
class IndexContext:
    """Everything ``index_item``/``rebuild_kb`` need, bundled by the
    caller (a test, or Leg 3's ``IndexingManager``)."""

    conn: aiosqlite.Connection
    item_repo: KBItemRepository
    chunk_repo: KBChunkRepository
    store: VectorStore
    backend: EmbeddingBackend
    chunking: ChunkingSettings
    should_stop: Callable[[], bool] = lambda: False
    embed_lock: asyncio.Lock | None = None
    embed_batch: int = EMBED_BATCH


@dataclasses.dataclass(frozen=True)
class ItemOutcome:
    """The result of one ``index_item`` call."""

    status: Literal["awaiting_flush", "failed", "stopped"]
    chunks: int
    vectors: int
    truncated: int
    error: str | None


class _Reject(Exception):  # noqa: N818 — named for the control-flow it signals, not the Error convention
    """Private to this module: raised during stages 2-8 for a condition
    the item should fail on with the raised message stored verbatim as
    `error` and no traceback logged — never escapes :func:`index_item`."""


async def _fail(ctx: IndexContext, item: KBItem, message: str) -> ItemOutcome:
    error = message[:_ERROR_MAX_CHARS]
    await ctx.item_repo.update_status(item.id, "failed", error=error)
    return ItemOutcome(status="failed", chunks=0, vectors=0, truncated=0, error=error)


async def index_item(item: KBItem, ctx: IndexContext) -> ItemOutcome:
    """Index one KB item end to end (Flight 3 DD-5's eight stages).

    Stage 1 (``pending -> indexing``) runs OUTSIDE the try below, so
    ``KBItemTransitionError``/``KeyError`` from an already-wrong-status or
    unknown item propagate to the caller rather than being swallowed as a
    per-item failure.
    """
    await ctx.item_repo.update_status(item.id, "indexing")

    try:
        # ── Stage 2: resolve + validate the source ──────────────────────
        if item.type != "file":
            raise _Reject(f"item type {item.type!r} is not indexable")

        path = Path(item.path_or_url)
        extractor = extractor_for(path)
        if extractor is None:
            raise _Reject(f"no extractor for suffix {path.suffix!r}")

        try:
            st = await asyncio.to_thread(path.stat)
        except FileNotFoundError:
            raise _Reject(f"file not found: {path}") from None

        if st.st_size > MAX_FILE_BYTES:
            raise _Reject("file exceeds the 10 MiB indexing cap")

        if await asyncio.to_thread(is_binary_head, path):
            raise _Reject("binary content")

        try:
            text = await asyncio.to_thread(extractor.extract, path)
        except ExtractionError as exc:
            raise _Reject(str(exc)) from exc

        # Two full reads and one head read, by design (recorded, not
        # optimised — see the leg's Implementation Guidance): the 8 KiB
        # sniff above, `extract`'s read, and this second streamed read.
        digest = await asyncio.to_thread(content_hash, path)

        # ── Stage 3: chunk ───────────────────────────────────────────────
        chunks = await asyncio.to_thread(
            chunk_text,
            text,
            size_chars=ctx.chunking.size_chars,
            overlap_chars=ctx.chunking.overlap_chars,
        )

        # ── Stage 4: replace chunks + FTS (one transaction) ─────────────
        old_ids = await ctx.chunk_repo.ids_for_item(item.id)
        ids = await ctx.chunk_repo.replace_item_chunks(item.id, item.kb_id, chunks)

        # ── Stage 5: delete stale vectors, after the chunk commit ───────
        if old_ids:
            await ctx.store.delete(item.kb_id, old_ids)

        # ── Stages 6-7: embed + upsert in batches ────────────────────────
        total_vectors = 0
        total_truncated = 0
        for batch_start in range(0, len(ids), ctx.embed_batch):
            if batch_start > 0 and ctx.should_stop():
                return ItemOutcome(
                    status="stopped",
                    chunks=len(ids),
                    vectors=total_vectors,
                    truncated=total_truncated,
                    error=None,
                )

            batch_ids = ids[batch_start : batch_start + ctx.embed_batch]
            batch_chunks = chunks[batch_start : batch_start + len(batch_ids)]
            batch_texts = [c.text for c in batch_chunks]

            lock_ctx = ctx.embed_lock if ctx.embed_lock is not None else contextlib.nullcontext()
            async with lock_ctx:
                result = await asyncio.to_thread(ctx.backend.embed, batch_texts)
                assert result.vectors.shape[0] == len(batch_texts), (
                    "embedding backend returned a different row count than inputs"
                )
                norms = np.linalg.norm(result.vectors, axis=1)
                keep = norms >= _ZERO_NORM_THRESHOLD
                kept_ids = [bid for bid, k in zip(batch_ids, keep, strict=True) if k]
                kept_vectors = result.vectors[keep]
                if kept_ids:
                    await ctx.store.upsert(item.kb_id, kept_ids, kept_vectors)

            total_vectors += len(kept_ids)
            total_truncated += result.truncated

        # ── Stage 8: record the dedup identity ───────────────────────────
        await ctx.item_repo.set_content_identity(
            item.id, content_hash=digest, size_bytes=st.st_size, mtime=st.st_mtime
        )

        if total_truncated:
            logger.info(
                "item %s: %d chunk(s) embedded from truncated text", item.id, total_truncated
            )

        return ItemOutcome(
            status="awaiting_flush",
            chunks=len(ids),
            vectors=total_vectors,
            truncated=total_truncated,
            error=None,
        )
    except (asyncio.CancelledError, VectorStoreStaleError):
        # CancelledError is a BaseException since 3.8 and would never
        # reach `except Exception` anyway; it is named here so a future
        # "simplification" does not drop the VectorStoreStaleError guard
        # that DOES need it (DD-6: the pass-level catch is Leg 3's).
        raise
    except _Reject as exc:
        return await _fail(ctx, item, str(exc))
    except Exception as exc:
        logger.exception("indexing %s failed", item.id)
        return await _fail(ctx, item, f"{type(exc).__name__}: {exc}")


@dataclasses.dataclass
class FlushPolicy:
    """The flush-cadence policy (DD-5): pure, clock-injected, and never
    calls the store itself — Leg 3's worker owns the actual ``flush()``
    call and the ``awaiting_flush`` list this policy's ``should_flush()``
    gates.

    Both bounds in :meth:`should_flush` are lower bounds, so the rule
    *delays* flushing: the save-multiplier term is what keeps an O(N)
    save from dominating a build (near the operator's ~10% overhead bar)
    and is also what sets the crash re-work window.
    """

    min_chunks: int = FLUSH_MIN_CHUNKS
    min_seconds: float = FLUSH_MIN_SECONDS
    save_multiplier: float = FLUSH_SAVE_MULTIPLIER
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        self.chunks_since_flush: int = 0
        self.last_flush_at: float = self.clock()
        self.last_flush_seconds: float = 0.0

    def record_chunks(self, n: int) -> None:
        self.chunks_since_flush += n

    def should_flush(self) -> bool:
        if self.chunks_since_flush < self.min_chunks:
            return False
        elapsed = self.clock() - self.last_flush_at
        return elapsed >= max(self.min_seconds, self.save_multiplier * self.last_flush_seconds)

    def record_flush(self, duration_seconds: float) -> None:
        self.chunks_since_flush = 0
        self.last_flush_at = self.clock()
        self.last_flush_seconds = duration_seconds


async def rebuild_kb(kb_id: str, ctx: IndexContext, *, reason: str) -> None:
    """DD-6's only ``VectorStoreStaleError`` recovery: re-embed every
    chunk of ``kb_id`` from ``kb_chunks`` and stream it into
    ``ctx.store.rebuild_from``.

    Takes **no** manager lock (DD-5's ordering note) and never calls back
    into the store from inside the generator (the no-call-back invariant
    on ``VectorStore.rebuild_from`` — this generator touches only
    ``ctx.chunk_repo.iter_for_kb`` and ``ctx.backend.embed``).
    """
    logger.warning("rebuilding vector index for kb %s: %s", kb_id, reason)

    async def _pages() -> AsyncIterator[tuple[list[int], np.ndarray]]:
        async for page in ctx.chunk_repo.iter_for_kb(kb_id, 1000):
            texts = [c.text for c in page]
            result = await asyncio.to_thread(ctx.backend.embed, texts)
            assert result.vectors.shape[0] == len(texts), (
                "embedding backend returned a different row count than inputs"
            )
            norms = np.linalg.norm(result.vectors, axis=1)
            keep = norms >= _ZERO_NORM_THRESHOLD
            ids = [c.id for c, k in zip(page, keep, strict=True) if k]
            vectors = result.vectors[keep]
            if ids:
                yield ids, vectors

    await ctx.store.rebuild_from(kb_id, _pages())
