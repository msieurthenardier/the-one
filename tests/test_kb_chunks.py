"""Tests for ``KBChunkRepository`` and the ``kb_chunks_fts`` sync it owns
(Flight 2 Leg 2, DD-5/DD-12).

Covers AC-1 through AC-7 of the leg spec: insert/replace atomicity (single-
task and concurrent), never-recycled ids, the keyword-search primitive
(``bm25`` ordering, KB scoping, operator-character quoting, ``k``), and the
rebuild/integrity-check pair's recovery from a deliberately desynchronised
index.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from tests._schema_template import connect_template_db
from the_one.db._kb_types import ChunkRecord
from the_one.db._write_lock import reset_for_test
from the_one.db.models import KBItem, KnowledgeBase
from the_one.db.repositories import (
    MAX_SEARCH_K,
    KBChunkRepository,
    KBItemRepository,
    KnowledgeBaseRepository,
)


@pytest.fixture(autouse=True)
def _reset_lock_state():
    """Mirrors ``tests/test_db_write_lock.py``'s ``_reset_lock_state`` —
    the write-transaction guard's lock/owner are module-level state shared
    across the whole test session."""
    reset_for_test()
    yield
    reset_for_test()


@pytest.fixture
async def conn(tmp_path):
    """Same idiom as ``tests/test_db_repositories.py`` (:55-80)."""

    db_path = tmp_path / "test.db"
    connection = await connect_template_db(db_path)
    yield connection
    await connection.close()


@pytest.fixture
def kb_repo(conn):
    return KnowledgeBaseRepository(conn)


@pytest.fixture
def kb_item_repo(conn):
    return KBItemRepository(conn)


@pytest.fixture
def chunk_repo(conn):
    return KBChunkRepository(conn)


async def _make_kb_and_item(
    kb_repo: KnowledgeBaseRepository,
    kb_item_repo: KBItemRepository,
    *,
    kb_id: str = "kb1",
    item_id: str = "item1",
) -> None:
    await kb_repo.create(KnowledgeBase(id=kb_id, name=kb_id))
    await kb_item_repo.create(KBItem(id=item_id, kb_id=kb_id, type="file", path_or_url="/a"))


async def _match_rowids(conn, token: str) -> list[int]:
    async with conn.execute(
        "SELECT rowid FROM kb_chunks_fts WHERE kb_chunks_fts MATCH ?", (token,)
    ) as cur:
        return [row[0] for row in await cur.fetchall()]


# ── AC-1: fresh insert preserves seq/offsets, ids MATCH-able immediately ───


class TestReplaceItemChunksInsert:
    async def test_inserts_preserve_seq_and_offsets_returns_ids_in_seq_order(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        chunks = [
            ChunkRecord(seq=0, text="zq7xkalpha first chunk", char_start=0, char_end=22),
            ChunkRecord(seq=1, text="zq7xkbeta second chunk", char_start=22, char_end=44),
        ]
        ids = await chunk_repo.replace_item_chunks("item1", "kb1", chunks)

        assert len(ids) == 2
        assert ids[0] < ids[1]  # never recycled, seq order == insertion order

        listed = await chunk_repo.list_for_item("item1")
        assert [(c.seq, c.text, c.char_start, c.char_end) for c in listed] == [
            (0, "zq7xkalpha first chunk", 0, 22),
            (1, "zq7xkbeta second chunk", 22, 44),
        ]

    async def test_every_returned_id_is_match_able_immediately(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        chunks = [
            ChunkRecord(seq=0, text="zq7xkalpha first chunk", char_start=0, char_end=22),
            ChunkRecord(seq=1, text="zq7xkbeta second chunk", char_start=22, char_end=44),
        ]
        ids = await chunk_repo.replace_item_chunks("item1", "kb1", chunks)

        assert await _match_rowids(conn, "zq7xkalpha") == [ids[0]]
        assert await _match_rowids(conn, "zq7xkbeta") == [ids[1]]

    async def test_empty_chunks_deletes_existing_and_returns_empty_list(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        await chunk_repo.replace_item_chunks(
            "item1", "kb1", [ChunkRecord(seq=0, text="zq7xkgone text", char_start=0, char_end=14)]
        )
        ids = await chunk_repo.replace_item_chunks("item1", "kb1", [])
        assert ids == []
        assert await chunk_repo.list_for_item("item1") == []
        assert await _match_rowids(conn, "zq7xkgone") == []


# ── AC-2: re-replace removes old rows + FTS, never recycles ids ───────────


class TestReplaceItemChunksReReplace:
    async def test_old_rows_and_fts_removed_new_ids_never_recycled_check_fts_true(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        old_ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [ChunkRecord(seq=0, text="zq7xkoldtoken text here", char_start=0, char_end=23)],
        )
        new_ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [ChunkRecord(seq=0, text="zq7xknewtoken different text", char_start=0, char_end=28)],
        )

        assert await _match_rowids(conn, "zq7xkoldtoken") == []
        assert await _match_rowids(conn, "zq7xknewtoken") == new_ids
        assert min(new_ids) > max(old_ids)
        assert await chunk_repo.check_fts() is True


# ── AC-3: single-task atomicity — a mid-batch failure rolls back cleanly ──


class TestReplaceItemChunksAtomicitySingleTask:
    async def test_duplicate_seq_mid_batch_rolls_back_leaves_previous_state_intact(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        previous_ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [ChunkRecord(seq=0, text="zq7xkkeep original text", char_start=0, char_end=23)],
        )

        bad_chunks = [
            ChunkRecord(seq=0, text="zq7xknew0 text", char_start=0, char_end=14),
            ChunkRecord(seq=1, text="zq7xknew1 text", char_start=14, char_end=28),
            ChunkRecord(seq=1, text="zq7xkdup text", char_start=28, char_end=41),  # dup seq
        ]
        with pytest.raises(sqlite3.IntegrityError):
            await chunk_repo.replace_item_chunks("item1", "kb1", bad_chunks)

        listed = await chunk_repo.list_for_item("item1")
        assert [(c.id, c.seq, c.text) for c in listed] == [
            (previous_ids[0], 0, "zq7xkkeep original text")
        ]
        assert await _match_rowids(conn, "zq7xkkeep") == previous_ids
        assert await _match_rowids(conn, "zq7xknew0") == []
        assert await chunk_repo.check_fts() is True


# ── AC-4: concurrent atomicity — A's failure never touches B's write ──────


class TestReplaceItemChunksAtomicityConcurrent:
    async def test_task_a_fails_task_b_plain_write_lands_a_state_untouched(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        previous_ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [ChunkRecord(seq=0, text="zq7xkkeep original text", char_start=0, char_end=23)],
        )

        async def task_a() -> None:
            bad_chunks = [
                ChunkRecord(seq=0, text="zq7xknew0 text", char_start=0, char_end=14),
                ChunkRecord(seq=1, text="zq7xknew1 text", char_start=14, char_end=28),
                # duplicate seq placed last — A fails only after its first
                # (successful) inserts, per the leg spec's AC-4 wording.
                ChunkRecord(seq=1, text="zq7xkdup text", char_start=28, char_end=41),
            ]
            with pytest.raises(sqlite3.IntegrityError):
                await chunk_repo.replace_item_chunks("item1", "kb1", bad_chunks)

        async def task_b() -> None:
            # Yield so both tasks are in flight and genuinely contend for
            # the write-transaction lock rather than running sequentially.
            await asyncio.sleep(0)
            await kb_repo.create(KnowledgeBase(id="kb-b", name="B side-write"))

        await asyncio.gather(task_a(), task_b())

        listed = await chunk_repo.list_for_item("item1")
        assert [(c.id, c.seq, c.text) for c in listed] == [
            (previous_ids[0], 0, "zq7xkkeep original text")
        ]
        assert await chunk_repo.check_fts() is True

        b_side = await kb_repo.get("kb-b")
        assert b_side.name == "B side-write"


# ── AC-5: search_keyword ────────────────────────────────────────────────


class TestSearchKeyword:
    async def test_returns_planted_chunk_first_scoped_to_kb_ordered_by_bm25(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo, kb_id="kb1", item_id="item1")
        await _make_kb_and_item(kb_repo, kb_item_repo, kb_id="kb2", item_id="item2")

        planted_ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(
                    seq=0,
                    text="zq7xkrare zq7xkrare mentioned twice for relevance padding words",
                    char_start=0,
                    char_end=10,
                ),
                ChunkRecord(
                    seq=1,
                    text="zq7xkrare mentioned once only in a longer padded chunk of filler text",
                    char_start=10,
                    char_end=20,
                ),
            ],
        )
        # Same token planted in a DIFFERENT KB — must never be returned.
        await chunk_repo.replace_item_chunks(
            "item2",
            "kb2",
            [ChunkRecord(seq=0, text="zq7xkrare other kb", char_start=0, char_end=10)],
        )

        results = await chunk_repo.search_keyword("kb1", "zq7xkrare", 10)

        result_ids = [r[0] for r in results]
        assert set(result_ids) == set(planted_ids)
        assert result_ids[0] == planted_ids[0]  # the double-mention chunk ranks best
        scores = [r[1] for r in results]
        assert scores == sorted(scores)  # bm25 ascending == best-first

    async def test_k_is_honoured(self, conn, kb_repo, kb_item_repo, chunk_repo) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=0, text="zq7xkmany one", char_start=0, char_end=10),
                ChunkRecord(seq=1, text="zq7xkmany two", char_start=10, char_end=20),
                ChunkRecord(seq=2, text="zq7xkmany three", char_start=20, char_end=30),
            ],
        )
        results = await chunk_repo.search_keyword("kb1", "zq7xkmany", 2)
        assert len(results) == 2

    async def test_operator_characters_are_quoted_and_do_not_raise(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        await chunk_repo.replace_item_chunks(
            "item1", "kb1", [ChunkRecord(seq=0, text="zq7xksafe text", char_start=0, char_end=10)]
        )
        # Every character/token the leg spec calls out as hazardous.
        results = await chunk_repo.search_keyword("kb1", 'zq7xksafe "quoted" * ( - OR NEAR', 10)
        assert isinstance(results, list)  # did not raise

    async def test_empty_or_whitespace_query_returns_empty_without_querying(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        assert await chunk_repo.search_keyword("kb1", "", 10) == []
        assert await chunk_repo.search_keyword("kb1", "   ", 10) == []

    async def test_k_below_one_raises(self, conn, kb_repo, kb_item_repo, chunk_repo) -> None:
        # Squawk 0054: `k` is bounded at the repository so every caller
        # inherits the guard. Without it, `k=0`/negative `k` reaches SQLite
        # as `LIMIT 0`/`LIMIT -1` (silently empty/unbounded) instead of
        # raising — this test fails without the added `k < 1` guard.
        await _make_kb_and_item(kb_repo, kb_item_repo)
        with pytest.raises(ValueError, match="k must be between"):
            await chunk_repo.search_keyword("kb1", "zq7xkmany", 0)
        with pytest.raises(ValueError, match="k must be between"):
            await chunk_repo.search_keyword("kb1", "zq7xkmany", -1)

    async def test_k_above_ceiling_raises(self, conn, kb_repo, kb_item_repo, chunk_repo) -> None:
        # Squawk 0054: an unbounded `k` is a resource-exhaustion vector
        # once this path is agent-controlled (Flight 5) — without the
        # `k > MAX_SEARCH_K` guard this call would reach SQLite unbounded
        # instead of raising, so this test fails without the fix.
        await _make_kb_and_item(kb_repo, kb_item_repo)
        with pytest.raises(ValueError, match="k must be between"):
            await chunk_repo.search_keyword("kb1", "zq7xkmany", MAX_SEARCH_K + 1)


# ── AC-6: KB and item delete cascade the FTS side too ──────────────────────


class TestCascadeDeleteFtsSync:
    async def test_kb_delete_leaves_zero_chunk_and_fts_rows_check_fts_true(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        ids = await chunk_repo.replace_item_chunks(
            "item1", "kb1", [ChunkRecord(seq=0, text="zq7xkdoomed text", char_start=0, char_end=10)]
        )

        await kb_repo.delete("kb1")

        async with conn.execute("SELECT COUNT(*) FROM kb_chunks") as cur:
            assert (await cur.fetchone())[0] == 0
        placeholders = ", ".join("?" for _ in ids)
        async with conn.execute(
            f"SELECT COUNT(*) FROM kb_chunks_fts WHERE rowid IN ({placeholders})", ids
        ) as cur:
            assert (await cur.fetchone())[0] == 0
        assert await _match_rowids(conn, "zq7xkdoomed") == []
        assert await chunk_repo.check_fts() is True

    async def test_item_delete_returns_removed_chunk_ids_and_cleans_fts(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [ChunkRecord(seq=0, text="zq7xkitemgone text", char_start=0, char_end=10)],
        )

        removed = await kb_item_repo.delete("item1")

        assert removed == ids
        async with conn.execute("SELECT COUNT(*) FROM kb_chunks") as cur:
            assert (await cur.fetchone())[0] == 0
        assert await _match_rowids(conn, "zq7xkitemgone") == []
        assert await chunk_repo.check_fts() is True


# ── AC-7: rebuild_fts / check_fts ───────────────────────────────────────


class TestRebuildAndCheckFts:
    async def test_check_fts_true_on_empty_index(self, conn, chunk_repo) -> None:
        assert await chunk_repo.check_fts() is True

    async def test_check_fts_true_on_synced_multi_row_index(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=0, text="zq7xkone text", char_start=0, char_end=10),
                ChunkRecord(seq=1, text="zq7xktwo text", char_start=10, char_end=20),
            ],
        )
        assert await chunk_repo.check_fts() is True

    async def test_check_fts_true_after_repository_driven_delete(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        await chunk_repo.replace_item_chunks(
            "item1", "kb1", [ChunkRecord(seq=0, text="zq7xkone text", char_start=0, char_end=10)]
        )
        await chunk_repo.delete_for_item("item1")
        assert await chunk_repo.check_fts() is True

    async def test_rebuild_recovers_a_raw_bypass_delete_desync(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [ChunkRecord(seq=0, text="zq7xkbypassed text", char_start=0, char_end=10)],
        )

        # Raw bypass delete — outside any repository, no matching FTS delete.
        await conn.execute("DELETE FROM kb_chunks WHERE id = ?", (ids[0],))
        await conn.commit()

        assert await chunk_repo.check_fts() is False

        await chunk_repo.rebuild_fts()

        assert await chunk_repo.check_fts() is True
        assert await _match_rowids(conn, "zq7xkbypassed") == []


# ── get_many / count_for_kb / delete_for_kb ─────────────────────────────


class TestGetManyAndCounts:
    async def test_get_many_preserves_caller_order_and_empty_list_short_circuits(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=0, text="zq7xkone text", char_start=0, char_end=10),
                ChunkRecord(seq=1, text="zq7xktwo text", char_start=10, char_end=20),
            ],
        )
        reversed_ids = list(reversed(ids))
        fetched = await chunk_repo.get_many(reversed_ids)
        assert [c.id for c in fetched] == reversed_ids
        assert await chunk_repo.get_many([]) == []

    async def test_count_for_kb_and_delete_for_kb(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=0, text="zq7xkone text", char_start=0, char_end=10),
                ChunkRecord(seq=1, text="zq7xktwo text", char_start=10, char_end=20),
            ],
        )
        assert await chunk_repo.count_for_kb("kb1") == 2
        removed = await chunk_repo.delete_for_kb("kb1")
        assert len(removed) == 2
        assert await chunk_repo.count_for_kb("kb1") == 0
        assert await chunk_repo.check_fts() is True


# ── list_for_item paging / ids_for_item / iter_for_kb (Flight 3 Leg 1, AC-5) ──


class TestChunkReadsPagingAndKeysetIteration:
    async def test_list_for_item_unchanged_when_called_positionally(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=0, text="zq7xkone text", char_start=0, char_end=10),
                ChunkRecord(seq=1, text="zq7xktwo text", char_start=10, char_end=20),
            ],
        )
        chunks = await chunk_repo.list_for_item("item1")
        assert [c.seq for c in chunks] == [0, 1]

    async def test_list_for_item_limit_and_offset_page(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=n, text=f"zq7xkchunk{n} text", char_start=n, char_end=n + 1)
                for n in range(5)
            ],
        )
        page1 = await chunk_repo.list_for_item("item1", limit=2)
        assert [c.seq for c in page1] == [0, 1]
        page2 = await chunk_repo.list_for_item("item1", limit=2, offset=2)
        assert [c.seq for c in page2] == [2, 3]
        rest = await chunk_repo.list_for_item("item1", offset=3)
        assert [c.seq for c in rest] == [3, 4]

    async def test_ids_for_item_seq_order_matches_replace_result(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await _make_kb_and_item(kb_repo, kb_item_repo)
        ids = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=0, text="zq7xkone text", char_start=0, char_end=10),
                ChunkRecord(seq=1, text="zq7xktwo text", char_start=10, char_end=20),
            ],
        )
        assert await chunk_repo.ids_for_item("item1") == ids

    async def test_iter_for_kb_yields_pages_across_multiple_items_ascending_id(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="kb1"))
        await kb_item_repo.create(KBItem(id="item1", kb_id="kb1", type="file", path_or_url="/a"))
        await kb_item_repo.create(KBItem(id="item2", kb_id="kb1", type="file", path_or_url="/b"))
        ids1 = await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=n, text=f"zq7xkitemonec{n} text", char_start=n, char_end=n + 1)
                for n in range(3)
            ],
        )
        ids2 = await chunk_repo.replace_item_chunks(
            "item2",
            "kb1",
            [
                ChunkRecord(seq=n, text=f"zq7xkitemtwoc{n} text", char_start=n, char_end=n + 1)
                for n in range(3)
            ],
        )

        pages = []
        async for page in chunk_repo.iter_for_kb("kb1", batch_size=2):
            pages.append([c.id for c in page])

        flat = [cid for page in pages for cid in page]
        assert flat == sorted(ids1 + ids2)
        assert all(len(p) <= 2 for p in pages)

    async def test_iter_for_kb_empty_kb_yields_nothing(self, conn, kb_repo, chunk_repo) -> None:
        await kb_repo.create(KnowledgeBase(id="kb1", name="kb1"))
        pages = [p async for p in chunk_repo.iter_for_kb("kb1")]
        assert pages == []

    async def test_iter_for_kb_holds_no_transaction_between_pages(
        self, conn, kb_repo, kb_item_repo, chunk_repo
    ) -> None:
        """No transaction is held between pages — a write issued between
        two ``__anext__`` calls must succeed, proving the generator does
        not hold the write lock across a `yield`."""
        await kb_repo.create(KnowledgeBase(id="kb1", name="kb1"))
        await kb_item_repo.create(KBItem(id="item1", kb_id="kb1", type="file", path_or_url="/a"))
        await chunk_repo.replace_item_chunks(
            "item1",
            "kb1",
            [
                ChunkRecord(seq=n, text=f"zq7xkiterc{n} text", char_start=n, char_end=n + 1)
                for n in range(3)
            ],
        )

        it = chunk_repo.iter_for_kb("kb1", batch_size=2)
        first_page = await it.__anext__()
        assert len(first_page) == 2

        await kb_item_repo.create(KBItem(id="item2", kb_id="kb1", type="file", path_or_url="/b"))

        second_page = await it.__anext__()
        assert len(second_page) == 1
        with pytest.raises(StopAsyncIteration):
            await it.__anext__()
