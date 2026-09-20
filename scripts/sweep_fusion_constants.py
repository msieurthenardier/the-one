"""Fusion sensitivity sweep over ``RRF_K`` / ``candidate_k`` (M24 F07 L03,
DD-4). AC-14/AC-15/AC-16/AC-17.

**What this answers**: whether the shipped fusion constants in
``the_one/knowledge/retrieval.py`` (``RRF_K``, the ``_candidate_k``
formula, and the Flight 5 DD-3 reserved-slot rule) are *load-bearing*
(the returned top-``limit`` set moves materially when they move) or
*arbitrary* (it does not), against a real corpus with real keyword and
semantic indexes wired through ``retrieval.search()`` end to end.

**What this does NOT answer (DD-4's boundary — read before trusting a
number below)**: there is no query-relevance ground truth anywhere in
this tree, so this sweep never claims one value is *better* than
another. It reports a sensitivity surface — rank churn against the
shipped constants, the reserved slot's fire rate, and an overlap curve —
never a recommendation. A genuine quality regression in fusion (the
right chunks silently start ranking worse) would NOT be caught by this
sweep; it would need real relevance judgments this project does not have.

**Wiring (AC-14 Implementation Guidance 6b)**: a real ``UsearchStore`` +
real ``KBChunkRepository`` + real ``IndexingManager``, driven over the
repository's own ``docs/`` and ``missions/`` folders — the same fixture
shape as ``tests/test_kb_manager.py`` (``conn`` / ``store`` / ``backend``
/ ``_make_manager``), because ``IndexingManager`` is the production code
that already keeps vector ids and chunk ids aligned. This is deliberately
NOT ``bench_vector_store.py``'s raw-vector path (no ``kb_chunks``, no
FTS5) and NOT ``tests/test_kb_retrieval.py``'s stub-store fixture (never
demonstrates real-store-plus-real-repo with aligned ids).

Embeddings run through a small in-script stand-in mirroring
``tests/_embedding_stub.py::StubEmbeddingBackend`` (deterministic,
hash-seeded, dim=8) rather than the real ``LocalStaticBackend`` — the
sweep measures fusion ARITHMETIC (how RRF combines two rank lists), not
embedding quality, and DD-4 already rules out any relevance claim this
script could otherwise buy with a slower real model. `scripts/` must stay
free of a runtime dependency on `tests/`, so the stub is reimplemented
here rather than imported.

Queries are drawn FROM the corpus itself: every ``--query-stride``'th
indexed chunk's first ``--query-chars`` characters become one query
string, so each query is guaranteed real content with genuine keyword
and semantic neighbours in the same corpus (mirrors
``bench_vector_store.py::run_real``'s own held-out-chunk approach for
its query set).

Instrumentation is entirely non-invasive: ``RRF_K`` is a module global
read at call time inside ``_fuse``; ``candidate_k`` is swept by
monkeypatching ``retrieval._candidate_k`` itself (Implementation Guidance
6a) rather than the three constants it derives from. The reserved slot's
fire rate is read off ``retrieval.logger`` (it already logs at DEBUG
exactly when the rule fires) via a counting ``logging.Handler`` — no
product code changes.

Usage::

    python scripts/sweep_fusion_constants.py
    python scripts/sweep_fusion_constants.py --roots docs,missions --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import shutil
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
import numpy as np

from the_one.config import settings
from the_one.db.models import KBItem, KnowledgeBase
from the_one.db.repositories import KBChunkRepository, KBItemRepository, KnowledgeBaseRepository
from the_one.db.schema import ensure_schema
from the_one.embeddings._backend import EmbedResult
from the_one.knowledge import retrieval
from the_one.knowledge.manager import IndexingManager
from the_one.vectors import _reset_for_test as reset_vectors_module
from the_one.vectors.usearch_store import UsearchStore

_REPO_ROOT = Path(__file__).resolve().parents[1]
_KB_ID = "sweep"
_STUB_DIM = 8


# ── Self-contained embedding stub (mirrors tests/_embedding_stub.py) ──────


class _StubEmbeddingBackend:
    """Deterministic, hash-seeded unit vectors — reimplemented here (not
    imported from ``tests/``) so ``scripts/`` carries no runtime dependency
    on the test tree. See module docstring: the sweep measures fusion
    arithmetic, not embedding quality, so a real model buys nothing here."""

    def __init__(self, dim: int = _STUB_DIM) -> None:
        self.model_id = "sweep-stub-embedding-backend"
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> EmbedResult:
        texts = list(texts)
        if not texts:
            return EmbedResult(np.zeros((0, self.dim), dtype=np.float32), 0)
        rows = [self._vector_for(t) for t in texts]
        return EmbedResult(np.stack(rows).astype(np.float32), 0)

    def _vector_for(self, text: str) -> np.ndarray:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        rng = np.random.default_rng(int(digest, 16))
        vector = rng.standard_normal(self.dim)
        norm = np.linalg.norm(vector)
        if norm == 0.0:  # pragma: no cover
            vector[0] = 1.0
            norm = 1.0
        return (vector / norm).astype(np.float32)


# ── Corpus indexing (real IndexingManager, per Implementation Guidance 6b) ─


async def _build_indexed_corpus(
    data_dir: Path, roots: list[str]
) -> tuple[aiosqlite.Connection, KBChunkRepository]:
    """Index ``roots`` (directory names relative to the repo root) into a
    fresh DB + ``UsearchStore`` via a real ``IndexingManager`` pass —
    the same fixture shape as ``tests/test_kb_manager.py``."""
    db_path = data_dir / "sweep.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    original_data_dir = settings.data_dir
    settings.data_dir = data_dir
    store = UsearchStore(conn, dtype="f16", dim=_STUB_DIM)
    await store.open()

    kb_repo = KnowledgeBaseRepository(conn)
    item_repo = KBItemRepository(conn)
    chunk_repo = KBChunkRepository(conn)
    backend = _StubEmbeddingBackend(dim=_STUB_DIM)

    kb = KnowledgeBase(id=_KB_ID, name=_KB_ID)
    await kb_repo.create(kb)

    for i, root_name in enumerate(roots):
        root = _REPO_ROOT / root_name
        if not root.is_dir():
            print(f"skipping missing root: {root}", file=sys.stderr)
            continue
        await item_repo.create(
            KBItem(id=f"folder{i}", kb_id=_KB_ID, type="folder", path_or_url=str(root))
        )

    async def _conn_factory():
        return conn

    async def _store_factory():
        return store

    def _backend_factory():
        return backend

    manager = IndexingManager(
        conn_factory=_conn_factory,
        store_factory=_store_factory,
        backend_factory=_backend_factory,
    )
    manager.request_index(_KB_ID)
    await manager.wait_until_idle(_KB_ID, timeout=1800.0)
    await store.flush(_KB_ID)
    # The worker task is event-woken and long-lived by design (mirrors
    # production's one-task-per-KB shape) — stop it explicitly once this
    # one-shot indexing pass is done, or asyncio warns about a pending task
    # destroyed at process exit.
    await manager.stop(_KB_ID)

    n_chunks = await chunk_repo.count_for_kb(_KB_ID)
    print(f"indexed {n_chunks:,} chunks from roots={roots}", file=sys.stderr)

    settings.data_dir = original_data_dir
    return conn, chunk_repo


async def _sample_queries(
    chunk_repo: KBChunkRepository, *, stride: int, query_chars: int, max_queries: int
) -> list[str]:
    """Every ``stride``'th indexed chunk's first ``query_chars`` characters
    becomes one query string — real corpus content with guaranteed keyword
    and semantic neighbours (mirrors ``bench_vector_store.py``'s own
    held-out-chunk query construction)."""
    queries: list[str] = []
    seen = 0
    async for batch in chunk_repo.iter_for_kb(_KB_ID, batch_size=500):
        for chunk in batch:
            if seen % stride == 0:
                text = chunk.text.strip().replace("\n", " ")[:query_chars]
                if text:
                    queries.append(text)
            seen += 1
            if len(queries) >= max_queries:
                return queries
    return queries


# ── Fire-rate instrumentation (non-invasive — reads the existing log line) ─


class _FireCounter(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "reserved keyword slot fired" in record.getMessage():
            self.count += 1


# ── One grid cell ───────────────────────────────────────────────────────


@dataclass
class CellResult:
    rrf_k: int
    candidate_k: int
    n_queries: int
    fire_rate: float
    mean_overlap: float
    exact_match_rate: float


async def _run_cell(
    *,
    rrf_k: int,
    candidate_k: int,
    queries: list[str],
    limit: int,
    conn: aiosqlite.Connection,
    chunk_repo: KBChunkRepository,
    item_repo: KBItemRepository,
    store: UsearchStore,
    backend: _StubEmbeddingBackend,
    baseline: dict[str, list[int]] | None,
) -> tuple[CellResult, dict[str, list[int]]]:
    original_rrf_k = retrieval.RRF_K
    original_candidate_k = retrieval._candidate_k
    handler = _FireCounter()
    retrieval.logger.addHandler(handler)
    retrieval.logger.setLevel(logging.DEBUG)
    retrieval.RRF_K = rrf_k
    retrieval._candidate_k = lambda limit, _ck=candidate_k: _ck  # noqa: ARG005

    results: dict[str, list[int]] = {}
    try:
        for q in queries:
            res = await retrieval.search(
                _KB_ID,
                q,
                limit=limit,
                chunk_repo=chunk_repo,
                item_repo=item_repo,
                store=store,
                backend=backend,
            )
            results[q] = [hit.chunk_id for hit in res.hits]
    finally:
        retrieval.RRF_K = original_rrf_k
        retrieval._candidate_k = original_candidate_k
        retrieval.logger.removeHandler(handler)

    overlaps = []
    exact = 0
    if baseline is not None:
        for q, ids in results.items():
            base_ids = baseline.get(q, [])
            if not base_ids:
                continue
            overlap = len(set(ids) & set(base_ids)) / max(len(base_ids), 1)
            overlaps.append(overlap)
            if ids == base_ids:
                exact += 1
    mean_overlap = float(np.mean(overlaps)) if overlaps else 1.0
    exact_rate = (exact / len(overlaps)) if overlaps else 1.0

    cell = CellResult(
        rrf_k=rrf_k,
        candidate_k=candidate_k,
        n_queries=len(queries),
        fire_rate=handler.count / len(queries) if queries else 0.0,
        mean_overlap=mean_overlap,
        exact_match_rate=exact_rate,
    )
    return cell, results


# ── CLI / orchestration ────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("--roots", type=str, default="docs,missions")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--query-stride", type=int, default=40)
    p.add_argument("--query-chars", type=int, default=80)
    p.add_argument("--max-queries", type=int, default=60)
    p.add_argument(
        "--rrf-k-grid", type=str, default="10,30,60,100,200", help="comma list, 60 is shipped"
    )
    p.add_argument(
        "--candidate-k-grid",
        type=str,
        default="10,25,50,100,200",
        help="comma list; 50 is what _candidate_k(limit=10) computes today",
    )
    p.add_argument("--data-dir", type=Path, default=None)
    return p


async def _main_async(args: argparse.Namespace) -> int:
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    rrf_grid = [int(x) for x in args.rrf_k_grid.split(",") if x.strip()]
    ck_grid = [int(x) for x in args.candidate_k_grid.split(",") if x.strip()]

    data_dir = args.data_dir or Path(tempfile.mkdtemp(prefix="sweep-fusion-"))
    data_dir.mkdir(parents=True, exist_ok=True)
    reset_vectors_module()

    conn, chunk_repo = await _build_indexed_corpus(data_dir, roots)
    item_repo = KBItemRepository(conn)
    backend = _StubEmbeddingBackend(dim=_STUB_DIM)
    store = UsearchStore(conn, dtype="f16", dim=_STUB_DIM)
    await store.open()

    queries = await _sample_queries(
        chunk_repo,
        stride=args.query_stride,
        query_chars=args.query_chars,
        max_queries=args.max_queries,
    )
    print(f"sampled {len(queries)} queries (stride={args.query_stride})", file=sys.stderr)
    if not queries:
        print("no queries sampled — corpus too small or empty; aborting", file=sys.stderr)
        return 1

    shipped_rrf_k = retrieval.RRF_K
    shipped_candidate_k = retrieval._candidate_k(args.limit)
    print(
        f"shipped constants: RRF_K={shipped_rrf_k}, "
        f"candidate_k(limit={args.limit})={shipped_candidate_k}",
        file=sys.stderr,
    )

    baseline_cell, baseline_results = await _run_cell(
        rrf_k=shipped_rrf_k,
        candidate_k=shipped_candidate_k,
        queries=queries,
        limit=args.limit,
        conn=conn,
        chunk_repo=chunk_repo,
        item_repo=item_repo,
        store=store,
        backend=backend,
        baseline=None,
    )

    print("\n### Fusion sensitivity sweep (DD-4 — no relevance claim; see module docstring)\n")
    print(f"- corpus roots: {roots}")
    print(f"- queries sampled from corpus: {len(queries)} (stride={args.query_stride})")
    print(f"- limit: {args.limit}")
    print(
        f"- shipped constants: RRF_K={shipped_rrf_k}, "
        f"candidate_k(limit={args.limit})={shipped_candidate_k}"
    )
    print(
        f"- shipped-constants reserved-slot fire rate: "
        f"{baseline_cell.fire_rate:.3f} ({baseline_cell.n_queries} queries)\n"
    )
    print(
        "| RRF_K | candidate_k | fire_rate | mean_overlap_vs_shipped "
        "| exact_match_rate_vs_shipped |"
    )
    print("|---|---|---|---|---|")
    print(
        f"| {shipped_rrf_k} (shipped) | {shipped_candidate_k} (shipped) | "
        f"{baseline_cell.fire_rate:.3f} | 1.000 | 1.000 |"
    )

    for rrf_k in rrf_grid:
        for candidate_k in ck_grid:
            if rrf_k == shipped_rrf_k and candidate_k == shipped_candidate_k:
                continue
            cell, _ = await _run_cell(
                rrf_k=rrf_k,
                candidate_k=candidate_k,
                queries=queries,
                limit=args.limit,
                conn=conn,
                chunk_repo=chunk_repo,
                item_repo=item_repo,
                store=store,
                backend=backend,
                baseline=baseline_results,
            )
            print(
                f"| {rrf_k} | {candidate_k} | {cell.fire_rate:.3f} | "
                f"{cell.mean_overlap:.3f} | {cell.exact_match_rate:.3f} |"
            )

    await store.close()
    await conn.close()
    shutil.rmtree(data_dir, ignore_errors=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
