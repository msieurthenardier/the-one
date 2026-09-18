"""Knowledge-base retrieval and fusion (Mission 24, Flight 5, Leg 1;
DD-1/DD-2/DD-3).

Fuses the vector store's semantic hits with ``kb_chunks_fts``'s keyword
hits by reciprocal rank, so a query naming an exact term the embedding
model ranks poorly still finds it. A module with no agent, tool, or
registry in sight (DD-1) — :func:`search` takes every dependency as a
plain argument, so it is unit-testable with stub repositories/store/backend
and reused unchanged by Flight 6's inventory rendering.

**No lock is ever taken by this module.** Query embedding
(:data:`the_one.embeddings._backend.EmbeddingBackend.embed`) runs
synchronously under ``asyncio.to_thread`` and takes no lock at all — DD-2
measured it at **p50 0.08ms / p95 0.17ms** on this host's bundled
``potion-retrieval-32M``, discounted per the project's standing
Linux-benchmark rule (unpinned ``TOKENIZERS_PARALLELISM``/rayon/BLAS
thread counts) but structurally platform-independent regardless: the
encode path is tokenize -> numpy fancy-index gather -> mean -> L2
normalise, which mutates no model state and reaches no BLAS/OMP kernel, so
there is nothing for a thread-count environment variable to change. Eight
concurrent ``embed`` calls returned bit-identical vectors to a serial
baseline, which is why this path never takes
``IndexingManager``'s embed lock (that lock serialises embed-**plus**-
upsert across per-KB workers, not the read-only encode itself).

**The store's per-KB lock is a different matter.** ``UsearchStore.query``
takes ``entry.lock`` — the same lock ``upsert``, ``flush`` and
``rebuild_from`` hold, the last across a whole knowledge-base rebuild — so
a query concurrent with one of those waits on it. See
``the_one/agents.md``'s "Knowledge storage" section for the durable record
of this consequence beside the two crash windows below. That wait is what
:data:`SEMANTIC_QUERY_TIMEOUT` bounds, passed **into** ``store.query`` as
its keyword-only ``timeout``, which bounds only the wait to *acquire* that
lock (the waiter), never the work done while holding it (the holder) — see
``UsearchStore.query``'s own docstring for the measured hazard that rules
out any alternative that cancels the call itself.

**No overall retrieval deadline wraps any awaited call in this module** —
not the ``store.query`` call, not the ``gather``, not this module's own
``search``. The store does its search work inside its per-KB lock; a
deadline wrapped around any of those three levels cancels the awaiting
coroutine, which releases the lock while a pool thread is still reading
the index underneath it — measured: caller and lock released at 0.302s,
the escaped thread still running at 1.502s. The bound belongs exactly
once, on the lock acquisition inside ``UsearchStore.query`` itself; this
module has no legitimate use for a cancelling timeout primitive, so its
absence is checked as an invariant of the whole module, not just of the
call site.

**Choosing** :data:`SEMANTIC_QUERY_TIMEOUT`: against Flight 2's measured
Windows figures (~1.8s per 256-vector upsert batch at 1M chunks, 10-12s
per flush at 1M, ~24s at 3M), any value below flush duration means a query
concurrent with a flush degrades to keyword-only rather than waiting out
the flush — the intended trade, since a few seconds of extra agent latency
is worse than a keyword-only answer, and the reserved keyword slot (DD-3)
keeps the exact-term guarantee alive through the degrade.

**Two crash windows are tolerated by construction, not by a check** (as
recorded in ``the_one/agents.md``): (a) FTS5 can return chunks of an item
still ``indexing`` whose vectors have not landed yet — they surface with a
keyword rank only, which reciprocal rank fusion handles natively; (b) a
saved sidecar can still hold ids a re-index has since deleted from
``kb_chunks`` — :meth:`the_one.db.repositories.KBChunkRepository.get_many`
silently drops them, so the fused list is simply shorter. A third window,
found at leg design review — an item deleted between the chunk fetch and
the per-item path lookup — is tolerated the same way: ``item_repo.get``'s
``KeyError`` is caught and the affected hit dropped, mirroring
``get_many``'s own missing-id tolerance.

A chunk belonging to an item that is not yet ``indexed`` is returned
**unmarked** — no per-hit status field exists on :class:`SearchHit` — a
deliberate choice (operator's call), not an oversight: the chunk's text is
already committed and real.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import TYPE_CHECKING

from the_one.vectors._store import VectorStoreBusyError, VectorStoreStaleError

if TYPE_CHECKING:
    from the_one.db.repositories import KBChunkRepository, KBItemRepository
    from the_one.embeddings._backend import EmbeddingBackend
    from the_one.vectors._store import VectorStore

logger = logging.getLogger(__name__)

# DD-3: the constant from reciprocal rank fusion's original publication.
RRF_K = 60

# DD-1: candidate_k = min(max(limit * _CANDIDATE_K_MULTIPLIER,
# _CANDIDATE_K_FLOOR), _CANDIDATE_K_CEILING) — deep enough that a hit
# ranked poorly by one side still reaches fusion, shallow enough that
# `get_many` and the per-item path lookups stay trivial, and well inside
# `search_keyword`'s MAX_SEARCH_K (1,000) ceiling.
_CANDIDATE_K_MULTIPLIER = 5
_CANDIDATE_K_FLOOR = 25
_CANDIDATE_K_CEILING = 100

# DD-1: bounds only `UsearchStore.query`'s per-KB LOCK ACQUISITION (the
# waiter), never the search work itself (the holder — see the module
# docstring and `UsearchStore.query`'s own docstring). Chosen below the
# Flight 2 Windows flush duration (10-12s at 1M chunks) so a query
# concurrent with a flush degrades to keyword-only rather than waiting out
# the flush; a few seconds of extra latency is worse than blocking the
# agent's turn, and the reserved keyword slot (DD-3) keeps the exact-term
# guarantee alive through the degrade.
SEMANTIC_QUERY_TIMEOUT = 2.0


@dataclasses.dataclass(frozen=True)
class SearchHit:
    """One fused, resolved retrieval hit — a chunk plus its citation
    metadata and fused RRF score."""

    chunk_id: int
    item_id: str
    path: str
    seq: int
    char_start: int
    char_end: int
    text: str
    score: float


@dataclasses.dataclass(frozen=True)
class SearchResult:
    """The result of :func:`search`: the fused, resolved hits, plus an
    optional ``degraded`` reason string (DD-1's four causes) that must
    travel with the hits rather than being inferred by the caller."""

    hits: list[SearchHit]
    degraded: str | None


@dataclasses.dataclass(frozen=True)
class _FusedCandidate:
    """Internal fusion-stage record — never crosses out of this module.

    ``in_keyword_list`` / ``in_semantic_list`` carry the raw list
    membership. DD-3 uses these two facts in TWO deliberately distinct
    senses, named differently so they cannot drift together:
    ``in_keyword_list`` (a both-list hit counts) drives the tie-break sort
    key; "keyword-only" (a both-list hit does NOT count — present in the
    keyword list AND absent from the semantic list) drives the reserved-
    slot trigger and displacer, computed at the call site rather than
    stored as a field.
    """

    chunk_id: int
    score: float
    in_keyword_list: bool
    in_semantic_list: bool


def _candidate_k(limit: int) -> int:
    return min(max(limit * _CANDIDATE_K_MULTIPLIER, _CANDIDATE_K_FLOOR), _CANDIDATE_K_CEILING)


def _fuse(semantic_ids: list[int], keyword_ids: list[int], limit: int) -> list[_FusedCandidate]:
    """Reciprocal rank fusion (DD-3) plus the reserved-slot rule.

    ``score(chunk) = sum over the lists it appears in of 1 / (RRF_K +
    rank)``, ranks 1-based, read directly from each list's position (both
    arrive best-first — the two backends' native scores are on unrelated,
    incomparable scales, so nothing is normalised). Sort key ``(-score,
    in_keyword_list desc, chunk_id asc)``: ties break toward the keyword
    side first, then ascending ``chunk_id``, so the exact-term criterion
    never turns on a coin-flip tie-break.

    The reserved-slot rule, implemented literally from DD-3's pseudocode
    (prose ambiguity here produced two high-severity review findings
    across design cycles, so the code shape is authoritative): one result
    slot is reserved for the keyword-only side whenever both lists are
    non-empty, the keyword-only set is non-empty, `limit >= 2`, and no
    keyword-only hit already made the top `limit` on score alone. When it
    fires, the reserved hit takes the displaced hit's position — last —
    since that is the lowest-scoring hit by construction and the context
    governor truncates from the head.
    """
    scores: dict[int, float] = {}
    in_keyword: set[int] = set()
    in_semantic: set[int] = set()
    for rank, chunk_id in enumerate(semantic_ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        in_semantic.add(chunk_id)
    for rank, chunk_id in enumerate(keyword_ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        in_keyword.add(chunk_id)

    candidates = [
        _FusedCandidate(
            chunk_id=chunk_id,
            score=score,
            in_keyword_list=chunk_id in in_keyword,
            in_semantic_list=chunk_id in in_semantic,
        )
        for chunk_id, score in scores.items()
    ]
    fused = sorted(candidates, key=lambda c: (-c.score, not c.in_keyword_list, c.chunk_id))
    top = fused[:limit]

    # "Keyword-only" here means present in the keyword list AND ABSENT
    # from the semantic list — the OTHER sense from `in_keyword_list`
    # above, where a both-list hit counts. A both-list hit does not count
    # as keyword representation for this rule; getting this backwards
    # makes the rule a no-op in the one case it exists for (DD-3 test 4).
    keyword_only = [c for c in fused if c.in_keyword_list and not c.in_semantic_list]

    if (
        limit >= 2
        and keyword_ids  # guard: the keyword list is non-empty
        and semantic_ids  # guard: the semantic list is non-empty
        and keyword_only  # guard: at least one keyword-only hit exists to reserve
        and not any(hit in keyword_only for hit in top)  # the trigger itself
    ):
        displaced = top[-1]
        replacement = keyword_only[0]
        logger.debug(
            "reserved keyword slot fired: displaced chunk_id=%s, reserved for chunk_id=%s",
            displaced.chunk_id,
            replacement.chunk_id,
        )
        top[-1] = replacement

    return top


async def search(
    kb_id: str,
    query: str,
    *,
    limit: int,
    chunk_repo: "KBChunkRepository",
    item_repo: "KBItemRepository",
    store: "VectorStore",
    backend: "EmbeddingBackend",
) -> SearchResult:
    """Fuse ``store``'s semantic hits with ``chunk_repo``'s keyword hits
    for ``query`` against ``kb_id``, returning the top ``limit`` results.

    An empty or whitespace-only ``query`` returns an empty
    :class:`SearchResult` immediately, touching neither ``backend``,
    ``store`` nor ``chunk_repo``/``item_repo`` — embedding an empty string
    produces a near-zero vector whose neighbours are meaningless, and
    ``search_keyword`` would short-circuit the same way regardless.

    Order of work (DD-1's authoritative ordering): embed the query
    (synchronous, under ``asyncio.to_thread``, no lock — see the module
    docstring); run the semantic and keyword calls concurrently under
    ``asyncio.gather(..., return_exceptions=True)`` — load-bearing, not a
    style choice: a plain ``gather`` would propagate the first exception
    and leave the sibling's result unretrieved, so a degrade handler would
    have no keyword hits to fall back to; fuse by reciprocal rank and take
    the top ``limit``; resolve the surviving ids to full chunk rows via
    ``chunk_repo.get_many`` (order-preserving, silently drops ids with no
    row — crash window (b)); resolve each hit's item path, memoised per
    distinct ``item_id`` within the call, tolerating a `KeyError` from a
    concurrently deleted item (the third crash window, dropping that hit
    rather than crashing the whole query).

    Degradation (DD-1's four causes, all logged at WARNING and returned
    via ``SearchResult.degraded`` rather than raised):
    ``VectorStoreStaleError`` -> ``"semantic index rebuilding"``;
    ``VectorStoreBusyError`` -> ``"semantic index busy"``; any other
    semantic-slot exception -> ``"semantic index unavailable"`` (never
    reaches fusion as a value); a keyword-slot exception ->
    ``"keyword index unavailable"``, with semantic-only hits returned.
    Both slots failing raises the **semantic** slot's exception,
    deterministically rather than depending on ``gather`` ordering.
    """
    stripped = query.strip()
    if not stripped:
        return SearchResult(hits=[], degraded=None)

    candidate_k = _candidate_k(limit)

    embed_result = await asyncio.to_thread(backend.embed, [stripped])
    vector = embed_result.vectors[0]

    semantic_result, keyword_result = await asyncio.gather(
        store.query(kb_id, vector, candidate_k, timeout=SEMANTIC_QUERY_TIMEOUT),
        chunk_repo.search_keyword(kb_id, stripped, candidate_k),
        return_exceptions=True,
    )

    degraded: str | None = None
    semantic_failed = isinstance(semantic_result, BaseException)
    keyword_failed = isinstance(keyword_result, BaseException)

    if semantic_failed and keyword_failed:
        # Both slots failed: raise the semantic slot's exception,
        # deterministically — never dependent on gather ordering.
        raise semantic_result

    if semantic_failed:
        exc = semantic_result
        if isinstance(exc, VectorStoreStaleError):
            degraded = "semantic index rebuilding"
        elif isinstance(exc, VectorStoreBusyError):
            degraded = "semantic index busy"
        else:
            degraded = "semantic index unavailable"
        logger.warning(
            "kb %s: semantic query failed (%s: %s); degrading to keyword-only results",
            kb_id,
            type(exc).__name__,
            exc,
        )
        semantic_result = []

    if keyword_failed:
        exc = keyword_result
        degraded = "keyword index unavailable"
        logger.warning(
            "kb %s: keyword query failed (%s: %s); degrading to semantic-only results",
            kb_id,
            type(exc).__name__,
            exc,
        )
        keyword_result = []

    semantic_ids = [chunk_id for chunk_id, _ in semantic_result]
    keyword_ids = [chunk_id for chunk_id, _ in keyword_result]

    fused = _fuse(semantic_ids, keyword_ids, limit)
    score_by_id = {c.chunk_id: c.score for c in fused}
    ordered_ids = [c.chunk_id for c in fused]

    chunks = await chunk_repo.get_many(ordered_ids)
    chunk_by_id = {c.id: c for c in chunks}

    item_paths: dict[str, str | None] = {}
    hits: list[SearchHit] = []
    for chunk_id in ordered_ids:
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None:
            # Crash window (b): the sidecar still held this id, but
            # `kb_chunks` no longer has a row for it.
            continue
        if chunk.item_id not in item_paths:
            try:
                item = await item_repo.get(chunk.item_id)
                item_paths[chunk.item_id] = item.path_or_url
            except KeyError:
                # The third crash window (AC-6b, found at leg design
                # review): the item was deleted between `get_many` above
                # and this lookup — two separate awaits on the one
                # process-wide connection with an event-loop yield
                # between them. Drop the hit rather than crash the query,
                # mirroring `get_many`'s own missing-id tolerance.
                logger.debug(
                    "kb %s: item %s missing for chunk %s (deleted between "
                    "get_many and the per-item lookup); dropping hit",
                    kb_id,
                    chunk.item_id,
                    chunk_id,
                )
                item_paths[chunk.item_id] = None
        path = item_paths[chunk.item_id]
        if path is None:
            continue
        hits.append(
            SearchHit(
                chunk_id=chunk.id,
                item_id=chunk.item_id,
                path=path,
                seq=chunk.seq,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                text=chunk.text,
                score=score_by_id[chunk_id],
            )
        )

    return SearchResult(hits=hits, degraded=degraded)
