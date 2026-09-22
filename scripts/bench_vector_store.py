"""Benchmark the two DD-9 ``usearch`` cells through the Leg 4 seam.

Flight 2 Leg 5 (M24 F02 L05, DD-8/DD-9), re-targeted to ``usearch`` only in
Leg 6 (M24 F02 L06) after the operator's DD-9 decision removed the losing
candidate from the closure. Produces the numbers the operator's store
decision rested on and continues to measure the surviving backend: for
each of
``usearch/f16`` and ``usearch/i8`` — build wall time, on-disk bytes, query
latency (p50/p95/max at k=10), recall@k against an exact float32 brute-force
ground truth, peak RSS (a per-cell **process** peak — see "Per-cell process
isolation" below), and ``save``/``restore + one k=10 query`` wall time
(usearch loads its index lazily, so the first post-restore query's own cost
is necessarily folded in — there is no pure-restore entry point to time
separately).

**Per-cell process isolation (Leg 5 review fix, BLOCKING 1)**:
``peak_rss_MB`` is read via ``resource.getrusage(...).ru_maxrss`` (POSIX) /
``GetProcessMemoryInfo`` (Windows) — both a process-LIFETIME watermark that
never resets mid-process. Running every cell sequentially in one process
therefore let later cells inherit an earlier cell's watermark (only the
first cell of an invocation ever read clean). Fix: a multi-cell invocation
runs each cell in its own child process — ``sys.executable`` re-invoking
this same script with ``--cells <one cell>`` plus a hidden ``--child`` flag
and the same ``--seed``/``--data-dir``/corpus arguments — so every cell's
``peak_rss_MB`` is that cell's own clean process-peak. A ``--child``
invocation regenerates the synthetic corpus (or re-embeds the real corpus —
no caching between children; ~30s extra per cell on Linux, acceptable, per
the leg's own trade-off note) identically from the shared inputs, runs
exactly that one cell, and prints ONLY that cell's already-rendered markdown
table row on stdout (everything else — host facts, fingerprint, corpus/
progress logging — is suppressed on the child's stdout; its stderr streams
through uncaptured so build/insert progress stays visible). A genuinely
single-cell invocation never forks a child; it stays in-process exactly as
before this fix.

Every cell is exercised **through the landed ``VectorStore`` seam**
(``the_one/vectors/``) — ``open``/``upsert``/``flush``/``query``/``close`` —
never through raw ``usearch`` calls (this module imports no symbol from the
package directly; its version string is read via ``importlib.metadata``
instead, so the only thing this script "knows" about it is its PyPI
version).

Two corpora:

- ``--corpus synthetic``: a seeded 64-centroid Gaussian mixture (sigma=0.3),
  512-dim, unit-normalised, generated and inserted in 100k batches so the
  process never holds the full float32 matrix. Recall here is *index/
  quantisation* recall — how much of the exact top-k an approximate HNSW
  index returns (or loses to int8 quantisation).
- ``--corpus real``: the repository's own markdown (``docs/``, ``missions/``,
  ``the_one/agents.md``, ``README.md``), chunked by the DD-7 chunker and
  embedded by the DD-1 backend (``LocalStaticBackend.load()`` — one load,
  batches of 1,000; **dim is taken from the loaded backend, never hard-
  coded**, which is what lets this path run under the suite-wide pytest
  stub (dim=8) with no injection flag). Recall here is the retrieval-
  relevant figure DD-4's 0.95 floor applies to.

Each cell gets a fresh on-disk DB file and sidecar directory; both are
deleted as soon as the cell's row is recorded, so a multi-cell invocation at
the largest N needs the disk space of only one cell, not both — a
free-space guard skips (never crashes) a cell whose estimated footprint
exceeds ``shutil.disk_usage(data_dir).free``.

Exit code is always 0 on completion — the printed numbers are the
deliverable, not a pass/fail gate. A per-cell exception is caught, reported
as an ``ERROR`` row, and does not abort the remaining cells.

Usage::

    python scripts/bench_vector_store.py --corpus synthetic --n 20000 --queries 50
    python scripts/bench_vector_store.py --corpus synthetic --n 1000000 --out /tmp/bench/1m.md
    python scripts/bench_vector_store.py --corpus synthetic --n 3000000 \\
        --cells usearch:f16,usearch:i8 --data-dir /tmp/the-one-bench
    python scripts/bench_vector_store.py --corpus real --data-dir /tmp/the-one-bench
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import hashlib
import io
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path

import aiosqlite
import numpy as np

from the_one.config import settings
from the_one.db._write_lock import reset_for_test as reset_write_lock
from the_one.db.schema import ensure_schema
from the_one.diagnostics import _peak_rss_bytes, _usearch_acceleration
from the_one.knowledge.chunking import chunk_text
from the_one.knowledge.settings import ChunkingSettings
from the_one.vectors import _reset_for_test as reset_vectors_module
from the_one.vectors.usearch_store import UsearchStore

# ── Constants ────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]

ALL_CELLS: list[tuple[str, str]] = [
    ("usearch", "f16"),
    ("usearch", "i8"),
]

# DD-8/AC-4's free-space guard. ``usearch/i8``'s base was RAISED from the
# original spec's literal 512 B/vector to 660 B/vector after the Linux 1M run
# (Leg 5) measured ~660.6 B/vector there — a 1.29x ratio against 512, above
# the _FREE_SPACE_MARGIN below, exactly the edge case the leg spec flagged
# ("if the Linux 1M int8 rows show a ratio above 1.25x, raise the guard's
# multiplier before the Windows 3M run rather than trust it blindly").
_BYTES_PER_VECTOR: dict[tuple[str, str], int] = {
    ("usearch", "f16"): 1024,
    ("usearch", "i8"): 660,
}
_FREE_SPACE_MARGIN = 1.25

SYN_DIM = 512
N_CENTROIDS = 64
CENTROID_SIGMA = 0.3
QUERY_SIGMA = 0.05
DEFAULT_SYN_BATCH = 100_000

_DEFAULT_CHUNKING = ChunkingSettings()
_KB_ID = "bench"


# ── Host facts ───────────────────────────────────────────────────────────


def _package_version(name: str) -> str:
    """Return ``name``'s installed version via ``importlib.metadata`` — never
    ``import``s the package itself (AC-7: this script imports no symbol from
    ``usearch`` except a version string)."""
    try:
        import importlib.metadata as _md

        return _md.version(name)
    except Exception as exc:  # noqa: BLE001 — a version string, never a gate
        return f"unavailable ({exc.__class__.__name__})"


def _ram_info() -> tuple[int | None, int | None, str | None]:
    """Return ``(total_bytes, available_bytes, reason_if_unavailable)``.

    Windows: ``GlobalMemoryStatusEx`` with declared ``argtypes``/``restype``
    (the Flight 1 HANDLE lesson — an undeclared restype truncates the HANDLE
    on a 64-bit process). POSIX: ``os.sysconf`` for total, ``/proc/meminfo``'s
    ``MemAvailable`` for available (best-effort — absent on macOS/BSD).
    """
    if os.name == "nt":
        try:

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MemoryStatusEx)]
            kernel32.GlobalMemoryStatusEx.restype = ctypes.c_int
            if not kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return (
                    None,
                    None,
                    f"GlobalMemoryStatusEx failed, GetLastError={ctypes.get_last_error()}",
                )
            return int(stat.ullTotalPhys), int(stat.ullAvailPhys), None
        except Exception as exc:  # noqa: BLE001 — advisory, never a failure
            return None, None, f"{exc.__class__.__name__}: {exc}"

    try:
        total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except Exception as exc:  # noqa: BLE001
        return None, None, f"{exc.__class__.__name__}: {exc}"

    available = None
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
                    break
    except OSError:
        pass
    return int(total), available, None


def host_facts(data_dir: Path) -> dict[str, str]:
    """Host facts printed at the top of every run (DD-8 read path)."""
    total_ram, avail_ram, ram_reason = _ram_info()
    free_disk = shutil.disk_usage(data_dir).free
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "sqlite_version": sqlite3.sqlite_version,
        "usearch_version": _package_version("usearch"),
        "cpu_count": str(os.cpu_count()),
        "ram_total_gb": f"{total_ram / 1e9:.2f}" if total_ram is not None else "unavailable",
        "ram_available_gb": f"{avail_ram / 1e9:.2f}" if avail_ram is not None else "unavailable",
        "ram_unavailable_reason": ram_reason or "",
        "free_disk_gb_at_data_dir": f"{free_disk / 1e9:.2f}",
        "usearch_acceleration": _usearch_acceleration(),
    }


def render_host_facts(facts: dict[str, str]) -> str:
    lines = ["## Host facts", ""]
    for key, value in facts.items():
        if key == "ram_unavailable_reason" and not value:
            continue
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines) + "\n"


# ── Synthetic corpus (AC-5) ───────────────────────────────────────────────


def make_synthetic_batches(
    seed: int,
    n: int,
    *,
    dim: int = SYN_DIM,
    batch_size: int = DEFAULT_SYN_BATCH,
    sigma: float = CENTROID_SIGMA,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield ``(ids, vectors)`` batches of a seeded Gaussian-mixture,
    unit-normalised, float32 synthetic corpus. ``ids`` are ``1..n``.

    Deterministic: a fresh ``np.random.default_rng(seed)`` is created on
    every call, so calling this twice with identical arguments reproduces
    the identical sequence of batches (and therefore the identical
    centroids) — the same seed reproduces the same vectors on any platform,
    and calling it again (e.g. once for ground truth, once per cell to
    insert) never requires holding the full corpus in RAM.
    """
    rng = np.random.default_rng(seed)
    centroids = rng.standard_normal((N_CENTROIDS, dim)).astype(np.float32)
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)

    start = 0
    while start < n:
        length = min(batch_size, n - start)
        centroid_ids = rng.integers(0, N_CENTROIDS, size=length)
        vecs = centroids[centroid_ids] + (
            rng.standard_normal((length, dim)).astype(np.float32) * sigma
        )
        vecs = vecs.astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        ids = np.arange(start + 1, start + length + 1, dtype=np.int64)
        yield ids, vecs
        start += length


def _batch0_fingerprint(seed: int, n: int, dim: int, *, batch_size: int = DEFAULT_SYN_BATCH) -> str:
    """SHA-256 of the first batch's raw bytes — printed with every synthetic
    table so a same-seed run on another platform can be checked for an
    identical corpus (AC-5)."""
    batches = make_synthetic_batches(seed, n, dim=dim, batch_size=batch_size)
    _, vecs0 = next(batches)
    batches.close()
    return hashlib.sha256(vecs0.tobytes()).hexdigest()


def make_queries(
    seed: int,
    n: int,
    n_queries: int,
    *,
    dim: int = SYN_DIM,
    batch_size: int = DEFAULT_SYN_BATCH,
    sigma_query: float = QUERY_SIGMA,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(source_ids, query_vectors)``: ``n_queries`` corpus members
    (the first ``n_queries`` ids of the deterministic batch-0, which are
    always present in the corpus by construction) perturbed by
    ``sigma_query`` and re-normalised — so each query has a genuine near
    neighbour (its own perturbed source, expected to be the top-1 result;
    by design, not a bug — see the module docstring's edge-case note).
    """
    n_queries = max(0, min(n_queries, n))
    batches = make_synthetic_batches(seed, n, dim=dim, batch_size=batch_size)
    ids0, vecs0 = next(batches)
    batches.close()
    source_ids = ids0[:n_queries]
    source_vecs = vecs0[:n_queries]

    # A separate substream (seed + 1) for the perturbation noise, so the
    # query-generation draws never consume the corpus generator's own RNG
    # state (which would change later batches were this called first).
    rng = np.random.default_rng(seed + 1)
    noise = rng.standard_normal(source_vecs.shape).astype(np.float32) * sigma_query
    query_vecs = (source_vecs + noise).astype(np.float32)
    norms = np.linalg.norm(query_vecs, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    query_vecs /= norms
    return source_ids, query_vecs


# ── Ground truth + recall (AC-2) ─────────────────────────────────────────


def brute_force_topk(
    query_vectors: np.ndarray,
    batches: Iterable[tuple[np.ndarray, np.ndarray]],
    k: int,
) -> list[list[tuple[int, float]]]:
    """Exact top-``k`` ``(id, cosine_similarity)`` per query, best first,
    streamed over ``batches`` (each an ``(ids, unit-vectors)`` pair) via a
    per-block ``argpartition`` merged into a running top-``k`` — the process
    never holds more than one block plus the running result at once.

    ``query_vectors`` must already be unit-normalised float32 (cosine
    similarity reduces to a dot product). A block smaller than ``k`` is
    clamped (the "argpartition on fewer than k candidates" edge case).
    """
    n_queries = query_vectors.shape[0]
    running_ids = np.zeros((n_queries, 0), dtype=np.int64)
    running_sims = np.zeros((n_queries, 0), dtype=np.float32)

    for ids, vecs in batches:
        block_len = len(ids)
        if block_len == 0:
            continue
        block_k = min(k, block_len)
        sims = query_vectors @ vecs.T  # (Q, block_len)
        if block_k < block_len:
            part = np.argpartition(-sims, block_k - 1, axis=1)[:, :block_k]
        else:
            part = np.tile(np.arange(block_len), (n_queries, 1))
        cand_sims = np.take_along_axis(sims, part, axis=1)
        cand_ids = np.asarray(ids, dtype=np.int64)[part]

        merged_ids = np.concatenate([running_ids, cand_ids], axis=1)
        merged_sims = np.concatenate([running_sims, cand_sims], axis=1)
        keep = min(k, merged_sims.shape[1])
        order = np.argpartition(-merged_sims, keep - 1, axis=1)[:, :keep]
        running_ids = np.take_along_axis(merged_ids, order, axis=1)
        running_sims = np.take_along_axis(merged_sims, order, axis=1)

    result: list[list[tuple[int, float]]] = []
    for row_ids, row_sims in zip(running_ids, running_sims, strict=True):
        order = np.argsort(-row_sims)
        result.append([(int(row_ids[i]), float(row_sims[i])) for i in order])
    return result


def recall_at_k(returned_ids: Sequence[int], truth_ids: Sequence[int], k: int) -> float:
    """Set-intersection recall: the fraction of the top-``k`` truth set that
    ``returned_ids`` also contains. A shuffled-but-otherwise-correct result
    yields the same score as the truth's own order (set semantics, not
    positional) — a half-replaced result yields exactly 0.5."""
    if k <= 0:
        return 0.0
    return len(set(returned_ids) & set(truth_ids)) / k


# ── Query timing (AC-3) ───────────────────────────────────────────────────


async def time_queries(
    store: object,
    kb_id: str,
    query_vectors: np.ndarray,
    k: int,
) -> tuple[list[int], list[list[tuple[int, float]]]]:
    """Time each single ``store.query()`` call with
    ``time.perf_counter_ns()``, running the whole ``Q``-query loop **twice**
    and returning only the second pass's durations (nanoseconds) and
    results (worker-noise/cache-warm precedent — AC-3).

    The timed region is exactly the ``await store.query(...)`` call — vector
    generation and normalisation happen before this function is ever
    called. For an int8 cell the store's internal quantisation of the query
    vector happens inside ``store.query`` and is therefore inside the timed
    region by design (the landed API takes a float vector; there is no
    pre-quantised entry point).
    """
    durations_ns: list[int] = []
    last_results: list[list[tuple[int, float]]] = []
    for _pass in range(2):
        durations_ns = []
        last_results = []
        for vector in query_vectors:
            t0 = time.perf_counter_ns()
            results = await store.query(kb_id, vector, k)
            t1 = time.perf_counter_ns()
            durations_ns.append(t1 - t0)
            last_results.append(results)
    return durations_ns, last_results


# ── Store construction / cleanup ──────────────────────────────────────────


def _build_store(backend: str, dtype: str, conn: aiosqlite.Connection, dim: int):
    return UsearchStore(conn, dtype=dtype, dim=dim)


def _cleanup_cell_files(db_path: Path, vectors_dir: Path, kb_id: str) -> None:
    """Delete a cell's DB file, ``-wal``/``-shm`` sidecars, and usearch
    sidecar file — called AFTER the owning connection/store is closed
    (unlinking a file SQLite still holds open raises ``PermissionError`` /
    WinError 32 on Windows)."""
    for candidate in (
        db_path,
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
    ):
        if candidate.exists():
            candidate.unlink()
    sidecar = vectors_dir / f"{kb_id}.usearch"
    if sidecar.exists():
        sidecar.unlink()


# ── One cell ───────────────────────────────────────────────────────────


async def run_cell(
    backend: str,
    dtype: str,
    *,
    dim: int,
    n: int,
    batch_source: Callable[[], Iterable[tuple[np.ndarray, np.ndarray]]],
    query_vectors: np.ndarray,
    truth: list[list[tuple[int, float]]],
    k: int,
    data_dir: Path,
) -> dict[str, object]:
    """Build, insert, flush, query and tear down one DD-4 cell — entirely
    through the Leg 4 ``VectorStore`` seam. Returns one result row.

    ``batch_source`` is a zero-argument callable returning a FRESH iterable
    of ``(ids, vectors)`` batches each call (the synthetic generator is
    re-invoked per cell rather than cached, so the process never holds the
    full corpus for more than one cell at a time).
    """
    row: dict[str, object] = {"backend": backend, "dtype": dtype, "n": n}
    # AC-3 (DD-10): a `--child` invocation never calls `host_facts()` — its
    # entire stdout contract is one rendered `render_row(rows[0])` line — so
    # the SIMD/numkong backend must be threaded as a per-cell COLUMN rather
    # than a host-level-only fact. Set unconditionally, before the
    # free-space guard/try block below, so it survives onto SKIPPED and
    # ERROR rows too (`row` is mutated in place, not rebuilt on that path).
    # `_usearch_acceleration()` is documented "never raises".
    row["usearch_acceleration"] = _usearch_acceleration()

    bytes_per_vec = _BYTES_PER_VECTOR[(backend, dtype)]
    needed = int(n * bytes_per_vec * _FREE_SPACE_MARGIN)
    free = shutil.disk_usage(data_dir).free
    if free < needed:
        row["status"] = f"SKIPPED (need ~{needed / 1e9:.2f} GB, free {free / 1e9:.2f} GB)"
        return row

    reset_write_lock()
    reset_vectors_module()

    db_path = data_dir / f"bench_{backend}_{dtype}.db"
    vectors_dir = data_dir / "vectors"
    conn: aiosqlite.Connection | None = None

    try:
        # Leg 5 review fix-now: the pre-cleanup call moves INSIDE the try —
        # a locked leftover file (e.g. a Windows sharing violation from a
        # prior interrupted run) must yield this cell an ERROR row rather
        # than raising out of `run_cell` and aborting every remaining cell.
        _cleanup_cell_files(db_path, vectors_dir, _KB_ID)

        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        store = _build_store(backend, dtype, conn, dim)
        await store.open()

        t_build0 = time.perf_counter()
        inserted = 0
        for batch_no, (ids, vecs) in enumerate(batch_source()):
            await store.upsert(_KB_ID, ids.tolist(), vecs)
            inserted += len(ids)
            print(
                f"    [{backend}/{dtype}] inserted {inserted:,}/{n:,} (batch {batch_no + 1})",
                file=sys.stderr,
            )
        row["build_s"] = time.perf_counter() - t_build0
        row["inserted"] = inserted

        t0 = time.perf_counter_ns()
        await store.flush(_KB_ID)
        save_ms = (time.perf_counter_ns() - t0) / 1e6

        sidecar = vectors_dir / f"{_KB_ID}.usearch"
        row["disk_mb"] = (sidecar.stat().st_size if sidecar.exists() else 0) / 1024 / 1024

        # Restore timing must load from disk: close the first store
        # (dropping its in-memory cache) before constructing the second.
        await store.close()
        query_store = _build_store(backend, dtype, conn, dim)
        await query_store.open()
        t0 = time.perf_counter_ns()
        await query_store.query(_KB_ID, query_vectors[0], k)
        restore_ms = (time.perf_counter_ns() - t0) / 1e6

        row["save_ms"] = save_ms
        row["restore_ms"] = restore_ms

        durations_ns, last_results = await time_queries(query_store, _KB_ID, query_vectors, k)
        ms = np.asarray(durations_ns, dtype=np.float64) / 1e6
        row["p50_ms"] = float(np.percentile(ms, 50))
        row["p95_ms"] = float(np.percentile(ms, 95))
        row["max_ms"] = float(ms.max())

        recalls = []
        for i, results in enumerate(last_results):
            returned_ids = [rid for rid, _ in results]
            truth_ids = [tid for tid, _ in truth[i]]
            recalls.append(recall_at_k(returned_ids, truth_ids, k))
        row["recall"] = float(np.mean(recalls)) if recalls else float("nan")

        peak, peak_reason = _peak_rss_bytes()
        row["peak_rss_mb"] = (peak / 1024 / 1024) if peak is not None else None
        row["peak_rss_reason"] = peak_reason

        await query_store.close()
        row["status"] = "OK"
    except Exception as exc:  # noqa: BLE001 — never crash mid-run; report and move on
        row["status"] = f"ERROR ({exc.__class__.__name__}: {exc})"
    finally:
        if conn is not None:
            await conn.close()
        try:
            _cleanup_cell_files(db_path, vectors_dir, _KB_ID)
        except OSError as exc:  # noqa: BLE001 — same rationale as the pre-cleanup above:
            # a locked leftover file on the way OUT must not crash a run that
            # otherwise already recorded (or errored) this cell's row.
            print(
                f"    [{backend}/{dtype}] post-cell cleanup failed (leaving stale files): "
                f"{exc.__class__.__name__}: {exc}",
                file=sys.stderr,
            )

    return row


# ── Real corpus (AC-6) ────────────────────────────────────────────────────


def _real_corpus_files(real_corpus_root: Path | None) -> list[Path]:
    """The four-root file list (``docs/``, ``missions/``,
    ``the_one/agents.md``, ``README.md``), or every ``*.md`` under
    ``real_corpus_root`` when given (the unit test's injection point — a
    single directory of small markdown files stands in for the repository).
    """
    if real_corpus_root is not None:
        return sorted(real_corpus_root.rglob("*.md"))
    files: list[Path] = []
    for root_name in ("docs", "missions"):
        root = _REPO_ROOT / root_name
        if root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    for extra in (_REPO_ROOT / "the_one" / "agents.md", _REPO_ROOT / "README.md"):
        if extra.is_file():
            files.append(extra)
    return files


def collect_real_corpus_chunks(
    real_corpus_root: Path | None,
    *,
    size_chars: int = _DEFAULT_CHUNKING.size_chars,
    overlap_chars: int = _DEFAULT_CHUNKING.overlap_chars,
) -> tuple[list[Path], list[tuple[str, int, str]]]:
    """Chunk every real-corpus file with the DD-7 chunker. Returns
    ``(files, chunks)`` where each chunk is ``(file, seq, text)``."""
    files = _real_corpus_files(real_corpus_root)
    chunks: list[tuple[str, int, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for record in chunk_text(text, size_chars=size_chars, overlap_chars=overlap_chars):
            chunks.append((str(path), record.seq, record.text))
    return files, chunks


def embed_in_batches(
    backend: object, texts: list[str], *, batch_size: int = 1000
) -> tuple[np.ndarray, int]:
    """Embed ``texts`` in batches of ``batch_size`` via ``backend.embed()``.
    Returns ``(vectors, truncated_total)``."""
    dim = backend.dim  # type: ignore[attr-defined]
    if not texts:
        return np.zeros((0, dim), dtype=np.float32), 0
    chunks: list[np.ndarray] = []
    truncated = 0
    for start in range(0, len(texts), batch_size):
        result = backend.embed(texts[start : start + batch_size])  # type: ignore[attr-defined]
        chunks.append(result.vectors)
        truncated += result.truncated
    return np.concatenate(chunks, axis=0), truncated


def _id_batches(ids: np.ndarray, vectors: np.ndarray, batch_size: int = 1000):
    for start in range(0, len(ids), batch_size):
        yield ids[start : start + batch_size], vectors[start : start + batch_size]


async def run_real(
    cells: list[tuple[str, str]],
    *,
    k: int,
    data_dir: Path,
    real_corpus_root: Path | None,
) -> list[dict[str, object]]:
    from the_one.embeddings.local import LocalStaticBackend

    files, chunks = collect_real_corpus_chunks(real_corpus_root)
    print(f"real corpus: {len(files)} files, {len(chunks)} chunks")

    query_positions = list(range(0, len(chunks), 125))[:200]
    query_set = set(query_positions)
    corpus_items = [c for i, c in enumerate(chunks) if i not in query_set]
    query_items = [chunks[i] for i in query_positions]
    print(f"held out {len(query_items)} query chunks, {len(corpus_items)} corpus chunks embedded")

    backend = LocalStaticBackend.load()
    dim = backend.dim

    corpus_vectors, truncated_corpus = embed_in_batches(backend, [t for _, _, t in corpus_items])
    query_vectors, truncated_queries = embed_in_batches(backend, [t for _, _, t in query_items])
    print(
        f"embedded {len(corpus_items)} corpus chunks + {len(query_items)} queries "
        f"at dim={dim} (truncated: {truncated_corpus + truncated_queries})"
    )

    ids = np.arange(1, len(corpus_items) + 1, dtype=np.int64)
    n = len(ids)

    print("computing exact ground truth (brute force, real corpus)…")
    truth = brute_force_topk(query_vectors, _id_batches(ids, corpus_vectors), k)

    rows = []
    for cell_backend, dtype in cells:
        print(f"== cell {cell_backend}/{dtype} ==", file=sys.stderr)

        def batch_source(ids=ids, vecs=corpus_vectors):
            return _id_batches(ids, vecs)

        row = await run_cell(
            cell_backend,
            dtype,
            dim=dim,
            n=n,
            batch_source=batch_source,
            query_vectors=query_vectors,
            truth=truth,
            k=k,
            data_dir=data_dir,
        )
        rows.append(row)
    return rows


# ── Synthetic corpus orchestration ────────────────────────────────────────


async def run_synthetic(
    cells: list[tuple[str, str]],
    *,
    n: int,
    n_queries: int,
    k: int,
    seed: int,
    data_dir: Path,
) -> tuple[list[dict[str, object]], str]:
    dim = SYN_DIM
    source_ids, query_vectors = make_queries(seed, n, n_queries, dim=dim)
    fingerprint = _batch0_fingerprint(seed, n, dim)
    print(f"synthetic fingerprint (batch0 sha256): {fingerprint}")
    print(f"synthetic corpus: n={n:,}, queries={len(source_ids)}, dim={dim}, seed={seed}")
    print("computing exact ground truth (brute force, synthetic)…")
    truth = brute_force_topk(query_vectors, make_synthetic_batches(seed, n, dim=dim), k)

    rows = []
    for backend, dtype in cells:
        print(f"== cell {backend}/{dtype} ==", file=sys.stderr)

        def batch_source(seed=seed, n=n, dim=dim):
            return make_synthetic_batches(seed, n, dim=dim)

        row = await run_cell(
            backend,
            dtype,
            dim=dim,
            n=n,
            batch_source=batch_source,
            query_vectors=query_vectors,
            truth=truth,
            k=k,
            data_dir=data_dir,
        )
        rows.append(row)
    return rows, fingerprint


# ── Rendering ──────────────────────────────────────────────────────────


# "peak_rss_MB" is a per-cell PROCESS peak (Leg 5 review fix, BLOCKING 1) —
# a multi-cell run isolates each cell in its own child process specifically
# so this column reads a clean watermark per row rather than a cross-cell
# monotonic leftover (see the module docstring's "Per-cell process
# isolation" note).
# "restore_ms" times ONE post-restore k=10 query, not a bare restore —
# usearch loads its index lazily (see UsearchStore), so the first query
# after a fresh Index.restore() necessarily folds the restore cost and that
# query's own cost together; there is no pure-restore entry point to time
# separately.
_TABLE_HEADERS = [
    "backend",
    "dtype",
    "n",
    "build_s",
    "disk_MB",
    "p50_ms",
    "p95_ms",
    "max_ms",
    "recall@k",
    "peak_rss_MB",
    "save_ms",
    "restore_ms",
    "usearch_acceleration",
    "status",
]


def _table_header_lines(title: str) -> list[str]:
    return [
        f"### {title}",
        "",
        "| " + " | ".join(_TABLE_HEADERS) + " |",
        "|" + "|".join(["---"] * len(_TABLE_HEADERS)) + "|",
    ]


def render_row(row: dict[str, object]) -> str:
    """Render one result row as a single markdown table line.

    This is the exact string a ``--child`` subprocess prints on stdout
    (Leg 5 review fix, BLOCKING 1) — the parent's per-cell dispatch path
    collects these lines directly rather than reconstructing them from a
    re-parsed row, and ``render_table`` below uses it for the in-process
    (single-cell) path.
    """

    def fmt(value: object, nd: int = 2) -> str:
        if value is None:
            return "-"
        if isinstance(value, float) and np.isnan(value):
            return "-"
        return f"{value:.{nd}f}"

    status = str(row.get("status", "OK"))
    # AC-3: the backend column is rendered on EVERY row — OK, SKIPPED and
    # ERROR alike — since `run_cell` sets it unconditionally before the
    # free-space guard. `"-"` only if the caller synthesized a row dict that
    # never went through `run_cell` at all (e.g. `_run_cell_subprocess`'s own
    # child-exit-failure row).
    accel = str(row.get("usearch_acceleration", "-"))
    if status != "OK":
        cells_out = (
            [str(row["backend"]), str(row["dtype"]), str(row["n"])] + ["-"] * 9 + [accel, status]
        )
    else:
        cells_out = [
            str(row["backend"]),
            str(row["dtype"]),
            str(row.get("inserted", row["n"])),
            fmt(row.get("build_s"), 2),
            fmt(row.get("disk_mb"), 2),
            fmt(row.get("p50_ms"), 3),
            fmt(row.get("p95_ms"), 3),
            fmt(row.get("max_ms"), 3),
            fmt(row.get("recall"), 4),
            fmt(row.get("peak_rss_mb"), 2),
            fmt(row.get("save_ms"), 3),
            fmt(row.get("restore_ms"), 3),
            accel,
            "OK",
        ]
    return "| " + " | ".join(cells_out) + " |"


def render_table(rows: list[dict[str, object]], title: str) -> str:
    lines = _table_header_lines(title)
    for row in rows:
        lines.append(render_row(row))
    return "\n".join(lines) + "\n"


def _render_table_from_lines(row_lines: list[str], title: str) -> str:
    """Assemble a full table from already-rendered per-cell row lines.

    The multi-cell (per-cell-subprocess) dispatch path's counterpart to
    ``render_table``: each child process has already rendered its own row
    via ``render_row``, so the parent only assembles the header + those
    lines rather than re-deriving them from row dicts.
    """
    lines = _table_header_lines(title) + list(row_lines)
    return "\n".join(lines) + "\n"


# ── CLI ────────────────────────────────────────────────────────────────


def parse_cells(spec: str | None) -> list[tuple[str, str]]:
    if not spec:
        return list(ALL_CELLS)
    cells: list[tuple[str, str]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        backend, _, dtype = part.partition(":")
        if (backend, dtype) not in ALL_CELLS:
            valid = ", ".join(f"{b}:{d}" for b, d in ALL_CELLS)
            raise SystemExit(f"invalid --cells entry {part!r} — must be one of: {valid}")
        cells.append((backend, dtype))
    return cells


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--corpus", choices=["synthetic", "real"], default="synthetic")
    parser.add_argument(
        "--n", type=int, default=1_000_000, help="synthetic corpus size (ignored for --corpus real)"
    )
    parser.add_argument(
        "--queries", type=int, default=200, help="synthetic query count (ignored for --corpus real)"
    )
    parser.add_argument(
        "--cells", type=str, default=None, help="comma list of backend:dtype (default: both)"
    )
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--seed", type=int, default=2024)
    parser.add_argument(
        "--data-dir", type=Path, default=None, help="default: a fresh temp directory"
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="also append the markdown output to this file"
    )
    parser.add_argument("--real-corpus-root", type=Path, default=None, help=argparse.SUPPRESS)
    # Hidden — the per-cell-subprocess dispatch path's own re-invocation
    # flag (Leg 5 review fix, BLOCKING 1). Never set by a human caller; see
    # the module docstring's "Per-cell process isolation" note.
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    return parser


async def _run_locally_async(
    args: argparse.Namespace, cells: list[tuple[str, str]], data_dir: Path
) -> tuple[list[dict[str, object]], str | None, str]:
    if args.corpus == "synthetic":
        rows, fingerprint = await run_synthetic(
            cells,
            n=args.n,
            n_queries=args.queries,
            k=args.k,
            seed=args.seed,
            data_dir=data_dir,
        )
        fp_part = f"synthetic fingerprint (batch0 sha256): `{fingerprint}`\n"
        title = f"Synthetic corpus (N={args.n:,}, k={args.k})"
    else:
        rows = await run_real(
            cells, k=args.k, data_dir=data_dir, real_corpus_root=args.real_corpus_root
        )
        fp_part = None
        title = f"Real corpus (k={args.k})"
    return rows, fp_part, title


def _run_locally(
    args: argparse.Namespace, cells: list[tuple[str, str]], data_dir: Path
) -> tuple[list[dict[str, object]], str | None, str]:
    """Run ``cells`` (one or more) fully in-process — the pre-Leg-5 design,
    still used for a genuinely single-cell invocation and, with stdout
    redirected, for a ``--child`` invocation."""
    original_data_dir = settings.data_dir
    try:
        settings.data_dir = data_dir  # UsearchStore.open() resolves this at open() time
        return asyncio.run(_run_locally_async(args, cells, data_dir))
    finally:
        settings.data_dir = original_data_dir


def _child_base_argv(args: argparse.Namespace, data_dir: Path) -> list[str]:
    """The argv a per-cell child subprocess is re-invoked with (everything
    except ``--cells``/``--child``, which the caller appends)."""
    argv = [
        "--corpus",
        args.corpus,
        "--k",
        str(args.k),
        "--seed",
        str(args.seed),
        "--data-dir",
        str(data_dir),
    ]
    if args.corpus == "synthetic":
        argv += ["--n", str(args.n), "--queries", str(args.queries)]
    elif args.real_corpus_root is not None:
        argv += ["--real-corpus-root", str(args.real_corpus_root)]
    return argv


def _run_cell_subprocess(base_argv: list[str], cell: tuple[str, str]) -> str:
    """Run one DD-4 cell in a fresh child process (Leg 5 review fix,
    BLOCKING 1) and return its already-rendered markdown table row.

    The child is this same script, re-invoked with ``base_argv`` plus
    ``--cells <cell> --child`` — it re-derives the identical corpus from
    the shared seed/inputs, runs exactly one cell, and prints ONLY that
    cell's row on stdout (captured here). The child's stderr is left
    uncaptured (inherited) so build/insert progress streams through live.
    """
    backend, dtype = cell
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        *base_argv,
        "--cells",
        f"{backend}:{dtype}",
        "--child",
    ]
    completed = subprocess.run(argv, stdout=subprocess.PIPE, text=True)
    stdout_lines = [ln for ln in (completed.stdout or "").splitlines() if ln.strip()]
    if completed.returncode != 0 or not stdout_lines:
        detail = (
            f"child exited {completed.returncode}"
            if completed.returncode != 0
            else "child produced no stdout"
        )
        return render_row(
            {"backend": backend, "dtype": dtype, "n": 0, "status": f"ERROR ({detail})"}
        )
    return stdout_lines[-1]


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    data_dir: Path = args.data_dir or Path(tempfile.mkdtemp(prefix="bench-vector-store-"))
    data_dir.mkdir(parents=True, exist_ok=True)
    cells = parse_cells(args.cells)

    if args.child:
        if len(cells) != 1:
            raise SystemExit("--child requires exactly one --cells entry")
        # Suppress everything this cell's run would otherwise print to
        # stdout (fingerprint, corpus/progress logging) — a --child
        # invocation's stdout contract is EXACTLY one rendered row line.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rows, _fp_part, _title = _run_locally(args, cells, data_dir)
        print(render_row(rows[0]))
        return 0

    facts = host_facts(data_dir)
    output_parts = [render_host_facts(facts)]
    print(render_host_facts(facts))

    if len(cells) > 1:
        # BLOCKING 1 fix: isolate each cell's peak-RSS watermark in its own
        # child process — see the module docstring's "Per-cell process
        # isolation" note.
        if args.corpus == "synthetic":
            fingerprint = _batch0_fingerprint(args.seed, args.n, SYN_DIM)
            print(f"synthetic fingerprint (batch0 sha256): {fingerprint}")
            print(
                f"synthetic corpus: n={args.n:,}, queries={args.queries}, "
                f"dim={SYN_DIM}, seed={args.seed}"
            )
            output_parts.append(f"synthetic fingerprint (batch0 sha256): `{fingerprint}`\n")
            title = f"Synthetic corpus (N={args.n:,}, k={args.k})"
        else:
            title = f"Real corpus (k={args.k})"
        child_argv = _child_base_argv(args, data_dir)
        row_lines = [_run_cell_subprocess(child_argv, cell) for cell in cells]
        table = _render_table_from_lines(row_lines, title)
    else:
        rows, fp_part, title = _run_locally(args, cells, data_dir)
        if fp_part:
            output_parts.append(fp_part)
        table = render_table(rows, title=title)

    output_parts.append(table)
    print(table)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(output_parts))
            fh.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
