"""``IndexingManager`` — one long-lived, event-woken worker task per
knowledge base (Flight 3 Leg 3, DD-7).

Modelled on ``the_one/connectors/manager.py``'s ``ConnectorManager``: a
``dict[kb_id, _WorkerEntry]``, a module-level ``_manager`` singleton
published at lifespan startup via :func:`set_manager` and resolved by
routes via :func:`get_manager`.

**Lock ordering invariant (DD-5 of Flight 2, restated here as the
authoritative statement for this module)**: **manager lock -> store
per-KB lock -> write lock** is the only permitted nesting order. No code
may acquire the manager lock (``IndexingManager._embed_lock``, held
around the embed-plus-upsert pair inside ``index_item``/``rebuild_kb``)
or a store per-KB lock while holding the write lock, and no code may
acquire the manager lock while holding a per-KB lock.
``UsearchStore.upsert``/``.delete`` acquire **and release** the shared
write lock (the empty-transaction shim) *before* taking the store's
per-KB lock, and touch no SQL inside it — they do not nest; only
``flush`` and ``rebuild_from`` genuinely nest per-KB lock -> write lock.
``rebuild_from`` holds the per-KB lock across the caller's generator, so
``rebuild_kb``'s generator (``the_one/knowledge/indexer.py``) takes
**no** manager lock — the one place embedding runs unserialised across
knowledge bases, accepted because a rebuild is exceptional.

**Worker pass** (``_pass``, run inside ``_run``'s per-KB task): (1)
``requeue_stranded(kb_id)`` and clear ``entry.awaiting_flush`` — the
resume-not-restart primitive; (2) walk + reconcile every ``folder`` item
of the KB (``_walk_one_folder`` / ``_apply_reconcile``); (3) drain
``pending`` ``file`` items (``_drain_pending``), flushing on the
``FlushPolicy`` cadence; (4) a final flush if anything is still
``awaiting_flush``. ``_run``'s own ``try/except/else`` around ``_pass``
is what flips ``entry.state``/``entry.idle`` on normal completion — never
a ``finally``, since a ``finally`` would flip ``idle`` true for an
instant mid-restart of a stale-sidecar rebuild and race a
``wait_until_idle`` caller into a false idle (design review, high).

See ``the_one/agents.md``'s "Knowledge indexing" section for the full
contract this module implements.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from the_one.db._kb_types import KBItemTransitionError
from the_one.db.connection import get_connection
from the_one.db.models import KBItem
from the_one.db.repositories import (
    AppMetadataRepository,
    KBChunkRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
)
from the_one.embeddings import get_embedding_backend
from the_one.embeddings.local import EMBEDDING_MODEL_DIRNAME
from the_one.knowledge.extractors import supported_extensions
from the_one.knowledge.indexer import (
    EMBED_BATCH,
    FLUSH_MIN_CHUNKS,
    FLUSH_MIN_SECONDS,
    FLUSH_SAVE_MULTIPLIER,
    FlushPolicy,
    IndexContext,
    index_item,
    rebuild_kb,
)
from the_one.knowledge.settings import (
    VECTOR_STORE_KEY,
    VectorStoreSettings,
    load_knowledge_settings,
    save_vector_store_settings,
    walk_skip_counters_key,
)
from the_one.knowledge.walk import content_hash, plan_reconcile, walk_folder
from the_one.vectors import get_vector_store
from the_one.vectors._store import VectorStore, VectorStoreStaleError

if TYPE_CHECKING:
    import aiosqlite

    from the_one.embeddings._backend import EmbeddingBackend

logger = logging.getLogger(__name__)

# ── Constants (constructor-overridable for tests) ──────────────────────────

PENDING_PAGE = 500
STOP_TIMEOUT = 20.0
SHUTDOWN_FLUSH_TIMEOUT = 20.0

__all__ = [
    "IndexingManager",
    "PENDING_PAGE",
    "STOP_TIMEOUT",
    "SHUTDOWN_FLUSH_TIMEOUT",
    "set_manager",
    "get_manager",
]


@dataclasses.dataclass
class _WorkerEntry:
    """Per-knowledge-base worker bookkeeping. ``awaiting_flush`` lives here
    (not in ``_run``'s locals) because the manager reads and clears it
    from ``stop()`` after the worker task is gone. ``current_item_id`` is
    the item a pass is currently on — used only by the stale-rebuild
    failure path to mark that one item ``failed``."""

    task: asyncio.Task | None
    wake: asyncio.Event
    idle: asyncio.Event
    stop_requested: bool
    state: str
    awaiting_flush: list[str]
    policy: FlushPolicy
    current_item_id: str | None = None


class IndexingManager:
    """One supervised worker task per knowledge base. See the module
    docstring for the pass shape, the lock order, and the idle/state
    bookkeeping rule."""

    def __init__(
        self,
        *,
        embed_batch: int = EMBED_BATCH,
        flush_min_chunks: int = FLUSH_MIN_CHUNKS,
        flush_min_seconds: float = FLUSH_MIN_SECONDS,
        flush_save_multiplier: float = FLUSH_SAVE_MULTIPLIER,
        pending_page: int = PENDING_PAGE,
        stop_timeout: float = STOP_TIMEOUT,
        shutdown_flush_timeout: float = SHUTDOWN_FLUSH_TIMEOUT,
        conn_factory: Callable[[], Awaitable[aiosqlite.Connection]] = get_connection,
        store_factory: Callable[[], Awaitable[VectorStore]] = get_vector_store,
        backend_factory: Callable[[], EmbeddingBackend] = get_embedding_backend,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._embed_batch = embed_batch
        self._flush_min_chunks = flush_min_chunks
        self._flush_min_seconds = flush_min_seconds
        self._flush_save_multiplier = flush_save_multiplier
        self._pending_page = pending_page
        self._stop_timeout = stop_timeout
        self._shutdown_flush_timeout = shutdown_flush_timeout
        self._conn_factory = conn_factory
        self._store_factory = store_factory
        self._backend_factory = backend_factory
        self._clock = clock
        self._entries: dict[str, _WorkerEntry] = {}
        # The one manager-wide lock passed as ctx.embed_lock (DD-5 of
        # Flight 2): serialises the embed-plus-upsert pair across every
        # knowledge base's worker so two CPU-bound embed threads never
        # race the same model concurrently.
        self._embed_lock = asyncio.Lock()
        # Mission 24 Flight 7 Leg 1, DD-3a: per-kb_id verdict of whether the
        # MOST RECENT stop() took the cancel fallback. Deliberately a
        # manager-level dict, NOT a _WorkerEntry field — drain() clears
        # _entries (below) immediately after gathering every stop(), which
        # would wipe a flag stored there before the shutdown hook (the one
        # reader that matters) ever gets to read it. Overwritten on every
        # stop() call in both directions (never accumulated): a clean stop
        # for a kb_id clears any prior cancelled verdict for that same
        # kb_id, because a kb_id can cancel once and then index cleanly for
        # hours before shutdown — an append-only report would keep skipping
        # it and lose that later, genuinely safe-to-flush write.
        self._cancel_report: dict[str, bool] = {}

    # ── lifecycle ────────────────────────────────────────────────────────

    def start(self, kb_id: str) -> None:
        """Create kb_id's worker task if absent or done. A no-op if a
        live task already exists."""
        entry = self._entries.get(kb_id)
        if entry is None:
            entry = _WorkerEntry(
                task=None,
                wake=asyncio.Event(),
                idle=asyncio.Event(),
                stop_requested=False,
                state="idle",
                awaiting_flush=[],
                policy=FlushPolicy(
                    min_chunks=self._flush_min_chunks,
                    min_seconds=self._flush_min_seconds,
                    save_multiplier=self._flush_save_multiplier,
                    clock=self._clock,
                ),
            )
            # A never-started KB reads idle (wait_until_idle must not hang).
            entry.idle.set()
            self._entries[kb_id] = entry
        if entry.task is None or entry.task.done():
            entry.stop_requested = False
            entry.task = asyncio.create_task(self._run(kb_id, entry))

    def request_index(self, kb_id: str) -> None:
        """Start kb_id's worker if needed, then wake it. Coalesced: a
        request arriving mid-pass is picked up by the loop's next
        iteration, never lost.

        ``idle`` is cleared HERE, synchronously, before ``wake`` is set —
        not left for the worker task to clear on its next scheduling turn.
        Without this, a caller doing ``request_index(); await
        wait_until_idle()`` back-to-back can race a freshly-created (or
        freshly-restarted) task that has not run yet: its entry's ``idle``
        is still set from creation/the prior pass, so ``wait_until_idle``
        would return immediately instead of waiting for the pass this
        call just requested."""
        self.start(kb_id)
        entry = self._entries[kb_id]
        entry.idle.clear()
        entry.wake.set()

    def state(self, kb_id: str) -> str:
        entry = self._entries.get(kb_id)
        if entry is None:
            return "idle"
        return entry.state

    async def wait_until_idle(self, kb_id: str, timeout: float = 10.0) -> None:
        """Test helper: await kb_id's idle event. A KB with no entry at
        all is vacuously idle."""
        entry = self._entries.get(kb_id)
        if entry is None:
            return
        await asyncio.wait_for(entry.idle.wait(), timeout)

    async def stop(self, kb_id: str) -> None:
        """Cooperative stop with a cancel fallback (DD-7). A no-op for an
        unknown kb_id."""
        entry = self._entries.get(kb_id)
        if entry is None:
            return
        entry.stop_requested = True
        entry.wake.set()
        cancelled = False
        try:
            await asyncio.wait_for(asyncio.shield(entry.task), self._stop_timeout)
        except TimeoutError:
            entry.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await entry.task
            cancelled = True

        # DD-3a: the write site is symmetric — this line runs on every
        # stop(), so a cancel re-asserts the verdict just as a clean stop
        # clears it. The report answers "how did the most recent stop end",
        # never "has this kb_id ever cancelled".
        self._cancel_report[kb_id] = cancelled

        if cancelled:
            # The cancel fallback never flushes (a cancelled to_thread
            # mutation may still be running — DD-7) and nothing else
            # would update a stale running/rebuilding word.
            entry.state = "stopped"
        elif entry.awaiting_flush:
            try:
                await asyncio.wait_for(self._flush(kb_id, entry), self._shutdown_flush_timeout)
            except Exception:
                logger.exception(
                    "kb %s: shutdown flush failed; awaiting items left indexing", kb_id
                )
        # In every case, unblock any wait_until_idle caller.
        entry.idle.set()

    def cancelled_kb_ids(self) -> frozenset[str]:
        """kb_ids whose most recent ``stop()`` took the cancel fallback
        (DD-3a) — read by the vector-store shutdown hook
        (``the_one.vectors.close_vector_store``) to skip a flush that could
        race a still-running mutation and tear the on-disk index.

        Survives ``drain()``: backed by ``self._cancel_report``, a
        manager-level dict independent of ``self._entries`` (which
        ``drain()`` clears). See ``self._cancel_report``'s own comment for
        why a ``_WorkerEntry`` field would be the wrong home."""
        return frozenset(
            kb_id for kb_id, was_cancelled in self._cancel_report.items() if was_cancelled
        )

    async def drain(self) -> None:
        """Stop every worker concurrently, then forget them all."""
        await asyncio.gather(
            *(self.stop(kb_id) for kb_id in list(self._entries)), return_exceptions=True
        )
        self._entries.clear()

    async def start_all(self) -> None:
        """Lifespan startup (DD-7): requeue every stranded item across all
        knowledge bases, write the first-index vector-store settings
        record if absent, then start+request-index every KB that has at
        least one folder or at least one pending file item."""
        conn = await self._conn_factory()
        item_repo = KBItemRepository(conn)
        kb_repo = KnowledgeBaseRepository(conn)
        await item_repo.requeue_stranded()

        meta_repo = AppMetadataRepository(conn)
        if await meta_repo.get(VECTOR_STORE_KEY) is None:
            store = await self._store_factory()
            await save_vector_store_settings(
                conn,
                VectorStoreSettings(
                    backend=store.backend,
                    dtype=store.dtype,
                    dim=store.dim,
                    model_id=EMBEDDING_MODEL_DIRNAME,
                ),
            )

        for kb in await kb_repo.list():
            has_folders = bool(await item_repo.list_folders(kb.id))
            has_pending = bool(
                await item_repo.list_by_status(kb.id, "pending", limit=1, type="file")
            )
            if has_folders or has_pending:
                self.request_index(kb.id)

    # ── worker loop ──────────────────────────────────────────────────────

    async def _run(self, kb_id: str, entry: _WorkerEntry) -> None:
        while True:
            await entry.wake.wait()
            entry.wake.clear()
            if entry.stop_requested:
                return
            entry.idle.clear()
            try:
                await self._pass(kb_id, entry)
            except VectorStoreStaleError as exc:
                entry.state = "rebuilding"
                try:
                    ctx = await self._resources(kb_id, entry)
                    await rebuild_kb(kb_id, ctx, reason=str(exc))
                except Exception:
                    logger.exception("kb %s: stale-sidecar rebuild failed", kb_id)
                    if entry.current_item_id is not None:
                        with contextlib.suppress(Exception):
                            conn = await self._conn_factory()
                            await KBItemRepository(conn).update_status(
                                entry.current_item_id,
                                "failed",
                                error="vector store rebuild failed",
                            )
                    entry.state = "stopped"
                    entry.idle.set()
                    return
                # Restart: the next loop iteration re-runs the pass, whose
                # own requeue_stranded returns the interrupted item(s) to
                # pending (a direct retry in place would raise
                # KBItemTransitionError("indexing->indexing"), DD-6).
                entry.wake.set()
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("kb %s: indexing pass failed", kb_id)
                entry.state = "stopped"
                entry.idle.set()
                return
            else:
                # No `finally`: idle is flipped only on this normal-
                # completion path (see module docstring).
                entry.state = "idle"
                entry.idle.set()

    async def _resources(self, kb_id: str, entry: _WorkerEntry) -> IndexContext:
        conn = await self._conn_factory()
        item_repo = KBItemRepository(conn)
        chunk_repo = KBChunkRepository(conn)
        store = await self._store_factory()
        backend = await asyncio.to_thread(self._backend_factory)
        chunking = (await load_knowledge_settings(conn)).chunking
        return IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=store,
            backend=backend,
            chunking=chunking,
            should_stop=lambda: entry.stop_requested,
            embed_lock=self._embed_lock,
            embed_batch=self._embed_batch,
        )

    async def _pass(self, kb_id: str, entry: _WorkerEntry) -> None:
        entry.state = "running"
        entry.current_item_id = None
        ctx = await self._resources(kb_id, entry)

        await ctx.item_repo.requeue_stranded(kb_id)
        entry.awaiting_flush.clear()

        for folder in await ctx.item_repo.list_folders(kb_id):
            await self._walk_one_folder(kb_id, folder, ctx)

        await self._drain_pending(kb_id, ctx, entry)

        if entry.awaiting_flush:
            await self._flush(kb_id, entry)

    # ── walk + reconcile ─────────────────────────────────────────────────

    async def _cycle_folder_to_pending(self, ctx: IndexContext, item: KBItem) -> KBItem:
        """A re-walk moves the folder -> pending only from indexed/failed
        (DD-3); a folder already at pending (startup requeue, scope=all
        re-index, or a first walk) proceeds directly — pending->pending
        would raise KBItemTransitionError."""
        if item.status in ("indexed", "failed"):
            return await ctx.item_repo.update_status(item.id, "pending")
        return item

    async def _walk_one_folder(self, kb_id: str, folder: KBItem, ctx: IndexContext) -> None:
        folder = await self._cycle_folder_to_pending(ctx, folder)
        try:
            folder = await ctx.item_repo.update_status(folder.id, "indexing")
        except KBItemTransitionError:
            logger.exception("kb %s: folder %s could not enter indexing", kb_id, folder.id)
            return

        root = Path(folder.path_or_url)
        try:
            result = await asyncio.to_thread(walk_folder, root, extensions=supported_extensions())
        except OSError as exc:
            # Children are left exactly as they are — an unplugged drive
            # must not delete an index; the next successful walk re-syncs.
            await ctx.item_repo.update_status(folder.id, "failed", error=str(exc))
            logger.warning("kb %s: folder %s walk failed: %s", kb_id, folder.id, exc)
            return

        existing = await ctx.item_repo.list_children(folder.id)
        plan = plan_reconcile(result.files, existing)
        await self._apply_reconcile(kb_id, folder.id, plan, ctx)
        await ctx.item_repo.update_status(folder.id, "indexed")

        # DD-7 (Flight 7 Leg 2, AC-8): persist this pass's skip counters so
        # they survive a process restart — the walk already counts them
        # (`result.skipped_dirs`/`.skipped_entries`); this is the missing
        # persistence half. Written through the shared key helper
        # (AC-11b) so the read site (`get_kb_status`) and both cleanup
        # sites (`delete_kb_item`, `delete_knowledge_base`) can never drift
        # from where this actually wrote.
        #
        # Squawk 0148: the delete paths clear this key once, at delete time
        # (app_metadata sits outside the kb_items FK cascade), so a write
        # landing after the folder was deleted would orphan the row for
        # good. Re-check the folder still exists and skip the write if not.
        # Residual window: a delete committed on another connection between
        # this get and the set can still orphan one row (no cross-table
        # transaction without new repo API); the check closes the realistic
        # case of a delete during the walk/reconcile.
        meta_repo = AppMetadataRepository(ctx.conn)
        try:
            await ctx.item_repo.get(folder.id)
        except KeyError:
            folder_gone = True
        else:
            folder_gone = False
        if not folder_gone:
            await meta_repo.set(
                walk_skip_counters_key(folder.id),
                json.dumps(
                    {"skipped_dirs": result.skipped_dirs, "skipped_entries": result.skipped_entries}
                ),
            )
        logger.info(
            "kb %s: folder %s walk: %d new, %d changed, %d removed, %d unchanged "
            "(skipped_dirs=%d, skipped_entries=%d)",
            kb_id,
            folder.id,
            len(plan.new),
            len(plan.changed),
            len(plan.removed),
            plan.unchanged,
            result.skipped_dirs,
            result.skipped_entries,
        )

    async def _apply_reconcile(self, kb_id: str, folder_id: str, plan, ctx: IndexContext) -> None:
        if plan.new:
            # size_bytes/mtime left None so the first index sets identity.
            new_items = [
                KBItem(
                    id=uuid.uuid4().hex[:12],
                    kb_id=kb_id,
                    parent_id=folder_id,
                    type="file",
                    path_or_url=disc.path,
                )
                for disc in plan.new
            ]
            await ctx.item_repo.create_many(new_items)

        if plan.removed:
            removed_ids: list[int] = []
            for item in plan.removed:
                removed_ids.extend(await ctx.item_repo.delete(item.id))
            if removed_ids:
                await ctx.store.delete(kb_id, removed_ids)

        for item, disc in plan.changed:
            digest = await asyncio.to_thread(content_hash, Path(disc.path))
            if digest != item.content_hash:
                if item.status in ("indexed", "failed"):
                    await ctx.item_repo.update_status(item.id, "pending")
                # item.status == "pending": leave alone, this pass will
                # index it anyway.
            else:
                await ctx.item_repo.set_content_identity(
                    item.id, content_hash=digest, size_bytes=disc.size_bytes, mtime=disc.mtime
                )

    # ── drain ────────────────────────────────────────────────────────────

    async def _drain_pending(self, kb_id: str, ctx: IndexContext, entry: _WorkerEntry) -> None:
        attempted: set[str] = set()
        fallback_used = False
        while True:
            page = await ctx.item_repo.list_by_status(
                kb_id, "pending", limit=self._pending_page, type="file"
            )
            un_attempted = [item for item in page if item.id not in attempted]
            if un_attempted:
                if await self._drain_batch(kb_id, ctx, entry, un_attempted, attempted):
                    return
                continue

            if len(page) == self._pending_page and not fallback_used:
                # A cluster of >= pending_page rows stuck at pending would
                # otherwise occupy the oldest window forever and starve
                # later rows within this pass. Bounded to one full read.
                fallback_used = True
                full_page = await ctx.item_repo.list_by_status(kb_id, "pending", type="file")
                un_attempted = [item for item in full_page if item.id not in attempted]
                if not un_attempted:
                    return
                if await self._drain_batch(kb_id, ctx, entry, un_attempted, attempted):
                    return
                continue

            return

    async def _drain_batch(
        self,
        kb_id: str,
        ctx: IndexContext,
        entry: _WorkerEntry,
        items: list[KBItem],
        attempted: set[str],
    ) -> bool:
        """Index each of ``items``. Returns True iff the caller should
        leave the drain (a stopped outcome)."""
        for item in items:
            attempted.add(item.id)
            entry.current_item_id = item.id
            try:
                outcome = await index_item(item, ctx)
            except (KBItemTransitionError, KeyError):
                logger.exception(
                    "kb %s: indexing item %s could not transition; leaving it for a later pass",
                    kb_id,
                    item.id,
                )
                continue

            if outcome.status == "awaiting_flush":
                entry.awaiting_flush.append(item.id)
                entry.policy.record_chunks(outcome.chunks)
                if entry.policy.should_flush():
                    await self._flush(kb_id, entry)
            elif outcome.status == "stopped":
                return True
        return False

    # ── flush ────────────────────────────────────────────────────────────

    async def _flush(self, kb_id: str, entry: _WorkerEntry) -> None:
        """Time store.flush(kb_id), record it on the policy, then flip
        every awaiting id indexing -> indexed. If the flush itself raises
        (including VectorStoreStaleError), awaiting_flush is left
        untouched and the exception propagates — items stay indexing for
        the next requeue_stranded to pick up."""
        store = await self._store_factory()
        start = self._clock()
        await store.flush(kb_id)
        entry.policy.record_flush(self._clock() - start)

        ids = list(entry.awaiting_flush)
        entry.awaiting_flush.clear()
        conn = await self._conn_factory()
        item_repo = KBItemRepository(conn)
        for item_id in ids:
            try:
                await item_repo.update_status(item_id, "indexed")
            except (KBItemTransitionError, KeyError):
                logger.exception(
                    "kb %s: item %s failed to flip to indexed after flush", kb_id, item_id
                )


_manager: IndexingManager | None = None


def set_manager(manager: IndexingManager | None) -> None:
    """Install the application :class:`IndexingManager`. Lifespan-only."""
    global _manager
    _manager = manager


def get_manager() -> IndexingManager | None:
    """Return the running :class:`IndexingManager`, or ``None`` pre-startup."""
    return _manager
