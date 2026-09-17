"""Tests for ``the_one/knowledge/retrieval.py`` (Mission 24, Flight 5, Leg 1).

Covers AC-1 through AC-24 of the leg spec: the module's shape (frozen
dataclasses, the ``search`` signature), the empty-query guard, the
candidate-depth formula, reciprocal rank fusion with the reserved-slot
rule and its five named exact-term tests, the three crash windows, and
all four degrade causes.

Most tests use hand-written stub doubles for ``chunk_repo``/``item_repo``/
``store``/``backend`` — the whole point of ``search`` taking every
dependency as a plain argument (DD-1) is that fusion is unit-testable
with no agent, no registry, no DB and no LLM. A few tests that pin a
genuinely DB-backed behaviour (FTS5's implicit AND) use the real
``KBChunkRepository``/``KBItemRepository`` against an isolated sqlite
connection, mirroring ``tests/test_kb_chunks.py``'s fixture shape.
"""

from __future__ import annotations

import dataclasses
import inspect
import logging

import aiosqlite
import pytest

from tests._embedding_stub import StubEmbeddingBackend
from the_one.db._kb_types import ChunkRecord
from the_one.db._write_lock import reset_for_test
from the_one.db.models import KBChunk, KBItem, KnowledgeBase
from the_one.db.repositories import KBChunkRepository, KBItemRepository, KnowledgeBaseRepository
from the_one.db.schema import ensure_schema
from the_one.knowledge import retrieval
from the_one.knowledge.retrieval import (
    RRF_K,
    SEMANTIC_QUERY_TIMEOUT,
    SearchHit,
    SearchResult,
    _candidate_k,
    search,
)
from the_one.vectors._store import VectorStoreBusyError, VectorStoreStaleError

# ── Module-level stub doubles ───────────────────────────────────────────


def _chunk(
    chunk_id: int,
    *,
    item_id: str = "item1",
    kb_id: str = "kb1",
    seq: int = 0,
    text: str = "chunk text",
    char_start: int = 0,
    char_end: int = 10,
) -> KBChunk:
    return KBChunk(
        id=chunk_id,
        item_id=item_id,
        kb_id=kb_id,
        seq=seq,
        text=text,
        char_start=char_start,
        char_end=char_end,
    )


def _item(
    item_id: str = "item1",
    *,
    kb_id: str = "kb1",
    path: str = "/docs/a.txt",
    status: str = "indexed",
) -> KBItem:
    return KBItem(id=item_id, kb_id=kb_id, type="file", path_or_url=path, status=status)


class _RaisingBackend:
    """AC-2: raises if ``embed`` is ever called."""

    model_id = "raising"
    dim = 8

    def embed(self, texts):
        raise AssertionError(f"backend.embed must not be called; got texts={texts!r}")


class _RaisingStore:
    """AC-2: raises if ``query`` is ever called."""

    backend = "raising"
    dtype = "f16"
    dim = 8

    async def query(self, kb_id, vector, k, *, timeout=None):
        raise AssertionError("store.query must not be called for an empty query")


class _RaisingChunkRepo:
    """AC-2: raises if either method is ever called."""

    async def search_keyword(self, kb_id, query, k):
        raise AssertionError("chunk_repo.search_keyword must not be called for an empty query")

    async def get_many(self, ids):
        raise AssertionError("chunk_repo.get_many must not be called for an empty query")


class _RaisingItemRepo:
    """AC-2: raises if ``get`` is ever called."""

    async def get(self, item_id):
        raise AssertionError("item_repo.get must not be called for an empty query")


@dataclasses.dataclass
class _StubStore:
    """Controllable semantic-side double. ``hits`` is a list of
    ``(chunk_id, distance)`` best-first; ``exc``, if set, is raised
    instead of returning."""

    hits: list[tuple[int, float]] = dataclasses.field(default_factory=list)
    exc: BaseException | None = None
    calls: list[tuple] = dataclasses.field(default_factory=list)

    async def query(self, kb_id, vector, k, *, timeout=None):
        self.calls.append((kb_id, k, timeout))
        if self.exc is not None:
            raise self.exc
        return list(self.hits)


@dataclasses.dataclass
class _StubChunkRepo:
    """Controllable keyword-side + resolution double."""

    keyword_hits: list[tuple[int, float]] = dataclasses.field(default_factory=list)
    keyword_exc: BaseException | None = None
    chunks_by_id: dict[int, KBChunk] = dataclasses.field(default_factory=dict)
    calls: list[tuple] = dataclasses.field(default_factory=list)

    async def search_keyword(self, kb_id, query, k):
        self.calls.append(("search_keyword", kb_id, query, k))
        if self.keyword_exc is not None:
            raise self.keyword_exc
        return list(self.keyword_hits)

    async def get_many(self, ids):
        self.calls.append(("get_many", list(ids)))
        return [self.chunks_by_id[i] for i in ids if i in self.chunks_by_id]


@dataclasses.dataclass
class _StubItemRepo:
    """Controllable item-path-resolution double. ``missing_ids`` simulates
    an item deleted between ``get_many`` and this lookup (AC-6b)."""

    items_by_id: dict[str, KBItem] = dataclasses.field(default_factory=dict)
    missing_ids: frozenset[str] = frozenset()
    calls: list[str] = dataclasses.field(default_factory=list)

    async def get(self, item_id):
        self.calls.append(item_id)
        if item_id in self.missing_ids:
            raise KeyError(item_id)
        return self.items_by_id[item_id]


def _backend() -> StubEmbeddingBackend:
    return StubEmbeddingBackend(dim=8)


# ── AC-1: module shape ──────────────────────────────────────────────────


class TestModuleShape:
    def test_search_hit_is_frozen_with_expected_fields(self) -> None:
        assert dataclasses.is_dataclass(SearchHit)
        assert SearchHit.__dataclass_fields__["chunk_id"] is not None
        fields = {f.name for f in dataclasses.fields(SearchHit)}
        assert fields == {
            "chunk_id",
            "item_id",
            "path",
            "seq",
            "char_start",
            "char_end",
            "text",
            "score",
        }
        hit = SearchHit(
            chunk_id=1, item_id="i", path="/a", seq=0, char_start=0, char_end=1, text="t", score=1.0
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            hit.score = 2.0  # type: ignore[misc]

    def test_search_result_is_frozen_with_hits_and_degraded(self) -> None:
        assert dataclasses.is_dataclass(SearchResult)
        fields = {f.name for f in dataclasses.fields(SearchResult)}
        assert fields == {"hits", "degraded"}
        result = SearchResult(hits=[], degraded=None)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.degraded = "x"  # type: ignore[misc]

    def test_search_signature(self) -> None:
        sig = inspect.signature(search)
        params = sig.parameters
        expected = ["kb_id", "query", "limit", "chunk_repo", "item_repo", "store", "backend"]
        assert list(params) == expected
        assert params["limit"].kind == inspect.Parameter.KEYWORD_ONLY
        assert params["chunk_repo"].kind == inspect.Parameter.KEYWORD_ONLY
        assert params["item_repo"].kind == inspect.Parameter.KEYWORD_ONLY
        assert params["store"].kind == inspect.Parameter.KEYWORD_ONLY
        assert params["backend"].kind == inspect.Parameter.KEYWORD_ONLY

    def test_no_wait_for_anywhere_in_the_module(self) -> None:
        # AC-3, widened at leg design review (cycle-1 finding #2): the
        # assertion is that the literal string "wait_for" appears NOWHERE
        # in the module — not merely absent from the same statement as
        # `store.query` — since a deadline wrapped around the `gather` or
        # around `search`'s whole body reproduces the same measured
        # lock-release hazard.
        import pathlib

        source = pathlib.Path(retrieval.__file__).read_text()
        assert "wait_for" not in source


# ── AC-4: candidate depth ───────────────────────────────────────────────


class TestCandidateK:
    def test_floor_applies_to_small_limits(self) -> None:
        assert _candidate_k(1) == 25
        assert _candidate_k(5) == 25

    def test_multiplier_applies_in_the_middle(self) -> None:
        assert _candidate_k(10) == 50

    def test_ceiling_applies_to_large_limits(self) -> None:
        assert _candidate_k(20) == 100
        assert _candidate_k(1000) == 100


# ── AC-2: empty query touches nothing ───────────────────────────────────


class TestEmptyQueryGuard:
    async def test_empty_string_touches_nothing(self) -> None:
        result = await search(
            "kb1",
            "",
            limit=5,
            chunk_repo=_RaisingChunkRepo(),
            item_repo=_RaisingItemRepo(),
            store=_RaisingStore(),
            backend=_RaisingBackend(),
        )
        assert result == SearchResult(hits=[], degraded=None)

    async def test_whitespace_only_touches_nothing(self) -> None:
        result = await search(
            "kb1",
            "   \t\n  ",
            limit=5,
            chunk_repo=_RaisingChunkRepo(),
            item_repo=_RaisingItemRepo(),
            store=_RaisingStore(),
            backend=_RaisingBackend(),
        )
        assert result == SearchResult(hits=[], degraded=None)


# ── AC-3: timeout is passed into store.query ────────────────────────────


class TestSemanticTimeoutPassedIn:
    async def test_store_query_called_with_the_module_timeout(self) -> None:
        store = _StubStore(hits=[(1, 0.1)])
        chunk_repo = _StubChunkRepo(chunks_by_id={1: _chunk(1)})
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        await search(
            "kb1",
            "hello",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )

        assert len(store.calls) == 1
        kb_id, k, timeout = store.calls[0]
        assert kb_id == "kb1"
        assert timeout == SEMANTIC_QUERY_TIMEOUT


# ── AC-5/AC-6/AC-6b: the three crash windows ────────────────────────────


class TestCrashWindows:
    async def test_window_a_keyword_only_indexing_item_returned_unmarked(self) -> None:
        # A chunk present only in the keyword list (its item still
        # `indexing`, vectors not landed) is returned, ranked by RRF,
        # unmarked — no status field exists on SearchHit at all.
        store = _StubStore(hits=[])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(1, -5.0)], chunks_by_id={1: _chunk(1, item_id="item1")}
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item("item1", status="indexing")})

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert result.degraded is None
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_window_b_vector_id_with_no_chunk_row_shortens_result(self) -> None:
        # The sidecar still holds a vector id `kb_chunks` no longer has a
        # row for — get_many drops it, the fused list is simply shorter.
        store = _StubStore(hits=[(1, 0.1), (2, 0.2)])
        chunk_repo = _StubChunkRepo(
            # Only chunk 1 exists; id 2 is the "ghost" vector id.
            chunks_by_id={1: _chunk(1)},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert result.degraded is None
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_window_6b_item_deleted_between_get_many_and_item_lookup(self) -> None:
        # A third crash window (AC-6b): the item vanished between the
        # chunk fetch and the per-item path lookup. Tolerated by dropping
        # the affected hit, mirroring get_many's own missing-id tolerance
        # — never an unhandled KeyError out of search.
        store = _StubStore(hits=[(1, 0.1), (2, 0.2)])
        chunk_repo = _StubChunkRepo(
            chunks_by_id={
                1: _chunk(1, item_id="item1"),
                2: _chunk(2, item_id="item-deleted"),
            },
        )
        item_repo = _StubItemRepo(
            items_by_id={"item1": _item("item1")},
            missing_ids=frozenset({"item-deleted"}),
        )

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert result.degraded is None
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_window_6b_logs_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        store = _StubStore(hits=[(1, 0.1)])
        chunk_repo = _StubChunkRepo(chunks_by_id={1: _chunk(1, item_id="item-deleted")})
        item_repo = _StubItemRepo(missing_ids=frozenset({"item-deleted"}))

        with caplog.at_level(logging.DEBUG, logger="the_one.knowledge.retrieval"):
            result = await search(
                "kb1",
                "term",
                limit=5,
                chunk_repo=chunk_repo,
                item_repo=item_repo,
                store=store,
                backend=_backend(),
            )
        assert result.hits == []
        assert any("item-deleted" in rec.message for rec in caplog.records)

    async def test_chunk_of_non_indexed_item_returned_unmarked(self) -> None:
        # AC-6: a chunk whose item is not `indexed` (here: `pending`) is
        # returned unmarked — SearchHit has no per-hit status field, so
        # this is a structural guarantee plus a behavioural one (not
        # filtered out).
        store = _StubStore(hits=[(1, 0.1)])
        chunk_repo = _StubChunkRepo(chunks_by_id={1: _chunk(1)})
        item_repo = _StubItemRepo(items_by_id={"item1": _item(status="pending")})

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert [h.chunk_id for h in result.hits] == [1]
        assert not hasattr(result.hits[0], "status")


# ── AC-7 through AC-11: fusion and the reserved-slot rule ──────────────


class TestFusionAndReservedSlot:
    async def test_ac10_test1_keyword_only_rare_hit_present_and_absent_from_semantic_only(
        self,
    ) -> None:
        # A keyword-only rare-identifier hit ranked outside the semantic
        # candidate window is in the fused result and absent from the
        # semantic-only result.
        store = _StubStore(hits=[(2, 0.1), (3, 0.2)])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(1, -9.0)],
            chunks_by_id={1: _chunk(1), 2: _chunk(2), 3: _chunk(3)},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        fused = await search(
            "kb1",
            "rareidentifier",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        fused_ids = {h.chunk_id for h in fused.hits}
        assert 1 in fused_ids

        # semantic-only: no keyword hits at all.
        chunk_repo_no_kw = _StubChunkRepo(chunks_by_id={2: _chunk(2), 3: _chunk(3)})
        semantic_only = await search(
            "kb1",
            "rareidentifier",
            limit=5,
            chunk_repo=chunk_repo_no_kw,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert 1 not in {h.chunk_id for h in semantic_only.hits}

    async def test_ac10_test2_both_list_outranks_one_list_at_equal_ranks(self) -> None:
        # Written at limit >= 2. A chunk in both lists at rank 1 on each
        # side outranks a chunk appearing only in one list at rank 1.
        store = _StubStore(hits=[(1, 0.1)])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(1, -9.0), (2, -8.0)],
            chunks_by_id={1: _chunk(1), 2: _chunk(2)},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=2,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert [h.chunk_id for h in result.hits][0] == 1

    async def test_ac10_test3_limit1_tie_keyword_side_wins(self) -> None:
        # limit=1, a keyword-only rank-1 hit ties a semantic-only rank-1
        # hit: the keyword hit wins via the tie-break, not the reserved
        # slot (guarded off at limit=1).
        store = _StubStore(hits=[(2, 0.1)])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(1, -9.0)],
            chunks_by_id={1: _chunk(1), 2: _chunk(2)},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=1,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_ac10_test4_strict_bar_exact_term_survives_five_both_list_crowders(
        self,
    ) -> None:
        # The pass bar the flight names explicitly: candidate_k=25,
        # limit=5, five both-list chunks ahead of a keyword-only
        # exact-term hit. Plain RRF fails this (the five both-list chunks
        # each score >= 2/61, the keyword-only hit scores 1/66) — the
        # reserved slot is what makes it pass.
        both_list_ids = [10, 11, 12, 13, 14]
        store = _StubStore(hits=[(cid, 0.1 * i) for i, cid in enumerate(both_list_ids, start=1)])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(cid, -9.0 + i) for i, cid in enumerate(both_list_ids, start=1)]
            + [(99, -1.0)],  # rank 6: the keyword-only exact-term hit
            chunks_by_id={cid: _chunk(cid) for cid in [*both_list_ids, 99]},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "exactterm",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert len(result.hits) == 5
        assert 99 in {h.chunk_id for h in result.hits}, (
            "the exact-term hit must survive the reserved-slot rule at the strict bar"
        )

    async def test_ac9_reserved_hit_takes_last_position_and_logs_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        both_list_ids = [10, 11, 12, 13, 14]
        store = _StubStore(hits=[(cid, 0.1 * i) for i, cid in enumerate(both_list_ids, start=1)])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(cid, -9.0 + i) for i, cid in enumerate(both_list_ids, start=1)]
            + [(99, -1.0)],
            chunks_by_id={cid: _chunk(cid) for cid in [*both_list_ids, 99]},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        with caplog.at_level(logging.DEBUG, logger="the_one.knowledge.retrieval"):
            result = await search(
                "kb1",
                "exactterm",
                limit=5,
                chunk_repo=chunk_repo,
                item_repo=item_repo,
                store=store,
                backend=_backend(),
            )
        assert result.hits[-1].chunk_id == 99
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("99" in r.message for r in debug_records)

    async def test_ac10_test5_sentence_shaped_query_zeroes_the_keyword_side(self) -> None:
        # FTS5's implicit AND: a sentence-shaped query containing the rare
        # identifier returns zero keyword hits, against a real
        # KBChunkRepository/sqlite FTS5 index.
        conn = await aiosqlite.connect(":memory:")
        try:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            await ensure_schema(conn)
            reset_for_test()

            kb_repo = KnowledgeBaseRepository(conn)
            item_repo_real = KBItemRepository(conn)
            chunk_repo_real = KBChunkRepository(conn)

            await kb_repo.create(KnowledgeBase(id="kb1", name="kb1"))
            await item_repo_real.create(_item("item1", path="/a"))
            await chunk_repo_real.replace_item_chunks(
                "item1",
                "kb1",
                [
                    ChunkRecord(
                        seq=0,
                        text="the zq7xkexact identifier appears in this chunk alone",
                        char_start=0,
                        char_end=10,
                    )
                ],
            )

            # The bare identifier finds it.
            bare = await chunk_repo_real.search_keyword("kb1", "zq7xkexact", 10)
            assert len(bare) == 1

            # A sentence-shaped query containing the identifier does not —
            # FTS5 implicit AND requires every whitespace-split term to
            # match, and this sentence's other words are absent from the
            # chunk.
            sentence = await chunk_repo_real.search_keyword(
                "kb1", "please find the file about zq7xkexact now", 10
            )
            assert sentence == []
        finally:
            await conn.close()
            reset_for_test()

    async def test_ac11_limit1_guard_both_list_winner_not_evicted(self) -> None:
        # AC-11: at limit=1 with a both-list winner AND a keyword-only hit
        # available, the both-list winner is NOT evicted by the reserved
        # slot (guarded off at limit=1 — DD-3's `limit >= 2` clause).
        store = _StubStore(hits=[(1, 0.1)])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(1, -9.0), (2, -8.0)],
            chunks_by_id={1: _chunk(1), 2: _chunk(2)},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=1,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_reserved_slot_guard_empty_keyword_only_does_not_raise(self) -> None:
        # A guard case (DD-3 cycle-3 finding #3): the keyword-only set is
        # empty (every keyword hit is also a semantic hit) — the trigger
        # must not fire, and `keyword_only[0]` must never be reached.
        store = _StubStore(hits=[(1, 0.1), (2, 0.2)])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(1, -9.0), (2, -8.0)],  # both also in the semantic list
            chunks_by_id={1: _chunk(1), 2: _chunk(2)},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=2,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert {h.chunk_id for h in result.hits} == {1, 2}

    async def test_reserved_slot_guard_one_sided_result_untouched(self) -> None:
        # Guard: a one-sided result (semantic list empty) never triggers
        # the reserved slot — it is already whatever the one side returned.
        store = _StubStore(hits=[])
        chunk_repo = _StubChunkRepo(
            keyword_hits=[(1, -9.0), (2, -8.0), (3, -7.0)],
            chunks_by_id={1: _chunk(1), 2: _chunk(2), 3: _chunk(3)},
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=2,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert [h.chunk_id for h in result.hits] == [1, 2]


# ── AC-12 through AC-16: degradation ────────────────────────────────────


class TestDegradation:
    async def test_stale_error_degrades_to_semantic_index_rebuilding(self) -> None:
        store = _StubStore(exc=VectorStoreStaleError("stale"))
        chunk_repo = _StubChunkRepo(keyword_hits=[(1, -9.0)], chunks_by_id={1: _chunk(1)})
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert result.degraded == "semantic index rebuilding"
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_busy_error_degrades_to_semantic_index_busy(self) -> None:
        store = _StubStore(exc=VectorStoreBusyError("busy"))
        chunk_repo = _StubChunkRepo(keyword_hits=[(1, -9.0)], chunks_by_id={1: _chunk(1)})
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert result.degraded == "semantic index busy"
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_unexpected_semantic_exception_degrades_to_unavailable(self) -> None:
        # A `_check_dim`-style ValueError, or any exception not among the
        # two named types, must degrade rather than reach fusion as a
        # value (which would fail with an opaque TypeError).
        store = _StubStore(exc=ValueError("dim mismatch"))
        chunk_repo = _StubChunkRepo(keyword_hits=[(1, -9.0)], chunks_by_id={1: _chunk(1)})
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert result.degraded == "semantic index unavailable"
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_keyword_slot_exception_degrades_to_keyword_unavailable(self) -> None:
        store = _StubStore(hits=[(1, 0.1)])
        chunk_repo = _StubChunkRepo(
            keyword_exc=RuntimeError("fts corrupt"), chunks_by_id={1: _chunk(1)}
        )
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        assert result.degraded == "keyword index unavailable"
        assert [h.chunk_id for h in result.hits] == [1]

    async def test_both_slots_failing_raises_the_semantic_exception(self) -> None:
        semantic_exc = ValueError("semantic broke")
        store = _StubStore(exc=semantic_exc)
        chunk_repo = _StubChunkRepo(keyword_exc=RuntimeError("keyword broke"))
        item_repo = _StubItemRepo()

        with pytest.raises(ValueError, match="semantic broke"):
            await search(
                "kb1",
                "term",
                limit=5,
                chunk_repo=chunk_repo,
                item_repo=item_repo,
                store=store,
                backend=_backend(),
            )


# ── DD-1: no empty-KB short-circuit ─────────────────────────────────────


class TestNoEmptyKbShortCircuit:
    async def test_no_count_for_kb_attribute_access_on_chunk_repo(self) -> None:
        # Cycle 2 removed the `count_for_kb` fast path entirely — a stub
        # repo with no `count_for_kb` method at all must still work, since
        # `search` never calls it.
        class _NoCountForKbChunkRepo:
            async def search_keyword(self, kb_id, query, k):
                return []

            async def get_many(self, ids):
                return []

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=_NoCountForKbChunkRepo(),
            item_repo=_StubItemRepo(),
            store=_StubStore(hits=[]),
            backend=_backend(),
        )
        assert result == SearchResult(hits=[], degraded=None)


# ── AC-7: RRF score formula ──────────────────────────────────────────────


class TestScoreFormula:
    async def test_both_list_score_is_sum_of_both_reciprocal_ranks(self) -> None:
        store = _StubStore(hits=[(1, 0.1)])
        chunk_repo = _StubChunkRepo(keyword_hits=[(1, -9.0)], chunks_by_id={1: _chunk(1)})
        item_repo = _StubItemRepo(items_by_id={"item1": _item()})

        result = await search(
            "kb1",
            "term",
            limit=5,
            chunk_repo=chunk_repo,
            item_repo=item_repo,
            store=store,
            backend=_backend(),
        )
        expected = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 1)
        assert result.hits[0].score == pytest.approx(expected)
