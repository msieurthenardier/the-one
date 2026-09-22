"""Tests for ``scripts/bench_vector_store.py`` (M24 F02 L05, DD-8).

AC-2/AC-3/AC-7 unit coverage plus two end-to-end runs (AC-1 shape, AC-6's
real-corpus path). The real-corpus test relies on the suite-wide
``_stub_embedding_backend_by_default`` autouse fixture (``tests/conftest.py``)
patching ``LocalStaticBackend.load`` to the 8-dim ``StubEmbeddingBackend`` —
no injection flag needed, since the script takes ``dim`` from the loaded
backend rather than hard-coding it (AC-6).
"""

from __future__ import annotations

import ast
import asyncio
import math
from pathlib import Path

import numpy as np
import pytest

from scripts import bench_vector_store

# ── Squawk 0060: bench row parser + range assertions ──────────────────────
#
# The end-to-end tests below previously checked only that a data row existed
# and ended in ``| OK |`` — a regression that printed ``nan`` or swapped two
# columns still passed. ``_parse_bench_row`` splits a rendered markdown row
# into a dict keyed by the script's own ``_TABLE_HEADERS`` (imported, never
# duplicated, so a column reorder in the script is caught here too) and
# ``_assert_row_sane`` checks the numeric cells are well-formed and in range.


def _parse_bench_row(line: str) -> dict[str, str]:
    """Parse one rendered markdown table row (as produced by
    ``bench_vector_store.render_row``) into a dict keyed by column name."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    headers = bench_vector_store._TABLE_HEADERS
    assert len(cells) == len(headers), (
        f"row has {len(cells)} cells, expected {len(headers)} (headers: {headers}): {line!r}"
    )
    return dict(zip(headers, cells, strict=True))


def _assert_non_negative_float_cell(row: dict[str, str], key: str) -> float | None:
    """Assert ``row[key]`` is either ``"-"`` (legitimately not applicable —
    e.g. a build/latency/save/restore cell on a row where that measurement
    was never taken) or a finite, non-negative float. Returns the parsed
    float, or ``None`` for ``"-"``."""
    raw = row[key]
    if raw == "-":
        return None
    value = float(raw)
    assert not math.isnan(value), f"{key} is NaN: {row!r}"
    assert not math.isinf(value), f"{key} is infinite: {row!r}"
    assert value >= 0, f"{key} is negative ({value}): {row!r}"
    return value


def _assert_row_sane(row: dict[str, str]) -> None:
    """Assert a parsed bench row's numeric cells are well-formed and in
    range (Squawk 0060)."""
    assert row["status"] == "OK", f"expected status OK, got: {row!r}"

    build_s = _assert_non_negative_float_cell(row, "build_s")
    assert build_s is not None, f"build_s must not be '-' on an OK row: {row!r}"
    save_ms = _assert_non_negative_float_cell(row, "save_ms")
    assert save_ms is not None, f"save_ms must not be '-' on an OK row: {row!r}"
    restore_ms = _assert_non_negative_float_cell(row, "restore_ms")
    assert restore_ms is not None, f"restore_ms must not be '-' on an OK row: {row!r}"
    p50 = _assert_non_negative_float_cell(row, "p50_ms")
    assert p50 is not None, f"p50_ms must not be '-' on an OK row: {row!r}"
    p95 = _assert_non_negative_float_cell(row, "p95_ms")
    assert p95 is not None, f"p95_ms must not be '-' on an OK row: {row!r}"
    max_ms = _assert_non_negative_float_cell(row, "max_ms")
    assert max_ms is not None, f"max_ms must not be '-' on an OK row: {row!r}"

    assert p50 <= p95, f"p50 > p95: {row!r}"
    assert p95 <= max_ms, f"p95 > max: {row!r}"

    recall = float(row["recall@k"])
    assert not math.isnan(recall), f"recall is NaN: {row!r}"
    assert 0.0 <= recall <= 1.0, f"recall out of [0, 1] ({recall}): {row!r}"

    disk_mb = float(row["disk_MB"])
    assert not math.isnan(disk_mb), f"disk_MB is NaN: {row!r}"
    assert disk_mb > 0, f"disk_MB not positive ({disk_mb}): {row!r}"

    peak_rss = float(row["peak_rss_MB"])
    assert not math.isnan(peak_rss), f"peak_rss_MB is NaN: {row!r}"
    assert peak_rss > 0, f"peak_rss_MB not positive ({peak_rss}): {row!r}"


_GOOD_ROW_LINE = (
    "| usearch | f16 | 300 | 0.01 | 0.34 | 0.21 | 0.29 | 0.31 "
    "| 1.0000 | 111.11 | 11.60 | 1.68 | numkong=yes, simd=haswell | OK |"
)


def test_assert_row_sane_accepts_a_well_formed_row() -> None:
    _assert_row_sane(_parse_bench_row(_GOOD_ROW_LINE))  # must not raise


def test_assert_row_sane_rejects_nan_cell() -> None:
    corrupted = _GOOD_ROW_LINE.replace("| 0.29 |", "| nan |")
    assert corrupted != _GOOD_ROW_LINE
    with pytest.raises(AssertionError):
        _assert_row_sane(_parse_bench_row(corrupted))


def test_assert_row_sane_rejects_p50_greater_than_p95() -> None:
    # Swap p50_ms (0.21) and p95_ms (0.29) so p50 > p95.
    corrupted = (
        "| usearch | f16 | 300 | 0.01 | 0.34 | 0.29 | 0.21 | 0.31 "
        "| 1.0000 | 111.11 | 11.60 | 1.68 | numkong=yes, simd=haswell | OK |"
    )
    with pytest.raises(AssertionError):
        _assert_row_sane(_parse_bench_row(corrupted))


# ── AC-7: no raw usearch imports ──────────────────────────────────────────


def test_script_imports_no_raw_backend_symbols() -> None:
    """The script must exercise every cell through the Leg 4 store — never
    import a symbol from ``usearch`` directly (its version string is read
    via ``importlib.metadata`` instead)."""
    source = Path(bench_vector_store.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in ("usearch",):
                    banned.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in ("usearch",):
                banned.add(node.module or "")
    assert not banned, f"script must not import backend symbols directly: {banned}"


# ── AC-2: ground truth + recall metric ───────────────────────────────────


def _small_corpus(seed: int = 7, n: int = 37, dim: int = 16) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    vecs = rng.standard_normal((n, dim)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    ids = np.arange(1, n + 1, dtype=np.int64)
    return ids, vecs


def test_brute_force_streamed_merge_equals_single_pass_argsort() -> None:
    ids, vecs = _small_corpus()
    rng = np.random.default_rng(123)
    queries = rng.standard_normal((5, vecs.shape[1])).astype(np.float32)
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    k = 6

    # Single pass: exact argsort over the whole small corpus.
    sims = queries @ vecs.T
    single_pass = []
    for row in sims:
        order = np.argsort(-row)[:k]
        single_pass.append([(int(ids[i]), float(row[i])) for i in order])

    # Streamed: artificially small blocks of 10 to force multiple merges.
    def blocks():
        block_size = 10
        for start in range(0, len(ids), block_size):
            yield ids[start : start + block_size], vecs[start : start + block_size]

    streamed = bench_vector_store.brute_force_topk(queries, blocks(), k)

    for single_row, streamed_row in zip(single_pass, streamed, strict=True):
        single_ids = [i for i, _ in single_row]
        streamed_ids = [i for i, _ in streamed_row]
        assert set(single_ids) == set(streamed_ids)
        for (_, s_sim), (_, st_sim) in zip(single_row, streamed_row, strict=True):
            assert s_sim == pytest.approx(st_sim, abs=1e-5)


def test_recall_at_k_against_own_brute_force_result_is_one() -> None:
    ids, vecs = _small_corpus()
    rng = np.random.default_rng(9)
    queries = rng.standard_normal((3, vecs.shape[1])).astype(np.float32)
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    k = 5
    truth = bench_vector_store.brute_force_topk(queries, [(ids, vecs)], k)

    for row in truth:
        returned_ids = [i for i, _ in row]
        truth_ids = [i for i, _ in row]
        assert bench_vector_store.recall_at_k(returned_ids, truth_ids, k) == 1.0


def test_recall_at_k_shuffled_is_still_one() -> None:
    truth_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    shuffled = [10, 2, 8, 4, 6, 1, 7, 3, 9, 5]
    assert bench_vector_store.recall_at_k(shuffled, truth_ids, 10) == 1.0


def test_recall_at_k_half_replaced_is_half() -> None:
    truth_ids = list(range(1, 11))
    half_replaced = truth_ids[:5] + [901, 902, 903, 904, 905]
    assert bench_vector_store.recall_at_k(half_replaced, truth_ids, 10) == 0.5


# ── AC-3: the timed region excludes fixture work ─────────────────────────


class _SleepStore:
    """A stub store whose ``query`` sleeps a known duration — used to prove
    ``time_queries`` times only the ``query`` call, not surrounding setup."""

    def __init__(self, sleep_s: float) -> None:
        self.sleep_s = sleep_s

    async def query(self, kb_id: str, vector: np.ndarray, k: int) -> list[tuple[int, float]]:
        await asyncio.sleep(self.sleep_s)
        return [(1, 0.0)]


async def test_time_queries_times_only_the_query_call() -> None:
    # Fixture work done BEFORE calling time_queries — large, deliberately
    # slow-ish array construction that must not leak into the reported
    # durations.
    rng = np.random.default_rng(1)
    big_prep = rng.standard_normal((2000, 512))  # noqa: F841 — deliberately unused fixture cost
    query_vectors = [np.zeros(4, dtype=np.float32) for _ in range(4)]

    sleep_s = 0.03
    store = _SleepStore(sleep_s)
    durations_ns, results = await bench_vector_store.time_queries(store, "kb", query_vectors, k=1)

    assert len(durations_ns) == len(query_vectors) == len(results)
    for duration_ns in durations_ns:
        ms = duration_ns / 1e6
        # Generous bounds for CI jitter, but tight enough to catch the
        # fixture prep (which would add tens of ms) leaking into the timer.
        assert sleep_s * 1000 * 0.5 <= ms <= sleep_s * 1000 * 10


# ── AC-1: synthetic end-to-end smoke ──────────────────────────────────────


def test_end_to_end_synthetic_usearch_f16(tmp_path, capsys) -> None:
    out_file = tmp_path / "out.md"
    argv = [
        "--corpus",
        "synthetic",
        "--n",
        "2000",
        "--queries",
        "10",
        "--k",
        "5",
        "--cells",
        "usearch:f16",
        "--data-dir",
        str(tmp_path / "data"),
        "--out",
        str(out_file),
    ]
    exit_code = bench_vector_store.main(argv)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "usearch" in captured.out
    row_lines = [ln for ln in captured.out.splitlines() if ln.startswith("| usearch")]
    assert len(row_lines) == 1, f"expected exactly one data row, got: {row_lines!r}"
    _assert_row_sane(_parse_bench_row(row_lines[0]))
    assert out_file.exists()
    assert "usearch" in out_file.read_text(encoding="utf-8")


# ── AC-6: real-corpus end-to-end under the suite-wide stub backend ────────


# ── Leg 5 review fix (BLOCKING 1): per-cell process isolation ─────────────


def test_child_mode_emits_exactly_one_row_on_stdout(tmp_path, capsys) -> None:
    """A ``--child`` invocation's stdout contract is EXACTLY one rendered
    markdown table row — no host facts, no fingerprint, no corpus/progress
    logging (those still go to stderr, uncaptured by ``capsys.readouterr``'s
    ``.out``)."""
    argv = [
        "--corpus",
        "synthetic",
        "--n",
        "300",
        "--queries",
        "5",
        "--k",
        "3",
        "--cells",
        "usearch:f16",
        "--data-dir",
        str(tmp_path / "data"),
        "--child",
    ]
    exit_code = bench_vector_store.main(argv)
    assert exit_code == 0

    captured = capsys.readouterr()
    stdout_lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(stdout_lines) == 1, f"expected exactly one stdout line, got: {stdout_lines!r}"
    assert stdout_lines[0].startswith("| usearch | f16 |")
    _assert_row_sane(_parse_bench_row(stdout_lines[0]))


def test_child_mode_row_carries_the_backend_column(tmp_path, capsys) -> None:
    """AC-3 (DD-10): a `--child` invocation never calls `host_facts()` — its
    entire stdout is `render_row(rows[0])` — so the SIMD/numkong backend must
    survive as a per-cell COLUMN, not a host-level-only fact. This is the
    real remaining gap the leg's design review identified: the host-level
    field already existed (AC-2), but a forked child could not report it."""
    argv = [
        "--corpus",
        "synthetic",
        "--n",
        "300",
        "--queries",
        "5",
        "--k",
        "3",
        "--cells",
        "usearch:f16",
        "--data-dir",
        str(tmp_path / "data"),
        "--child",
    ]
    exit_code = bench_vector_store.main(argv)
    assert exit_code == 0

    captured = capsys.readouterr()
    stdout_lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(stdout_lines) == 1
    row = _parse_bench_row(stdout_lines[0])
    assert "usearch_acceleration" in bench_vector_store._TABLE_HEADERS
    assert "numkong=" in row["usearch_acceleration"]


def test_direct_invocation_row_also_carries_the_backend_column(tmp_path, capsys) -> None:
    """AC-2/AC-3: the same field appears in the parent's direct (non-child,
    non-multi-cell) path too — `host_facts()`'s host-level line AND the
    per-cell column both carry it; this test is the per-cell half."""
    argv = [
        "--corpus",
        "synthetic",
        "--n",
        "300",
        "--queries",
        "5",
        "--k",
        "3",
        "--cells",
        "usearch:f16",
        "--data-dir",
        str(tmp_path / "data"),
    ]
    exit_code = bench_vector_store.main(argv)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "usearch_acceleration" in captured.out  # host_facts() line
    row_lines = [ln for ln in captured.out.splitlines() if ln.startswith("| usearch")]
    assert len(row_lines) == 1
    row = _parse_bench_row(row_lines[0])
    assert "numkong=" in row["usearch_acceleration"]


def test_run_cell_records_degraded_backend_rather_than_erroring(tmp_path, monkeypatch) -> None:
    """AC-4: a run whose numkong import "fails" (simulated via the
    `tests/test_doctor.py::TestUsearchAcceleration` precedent —
    monkeypatching `USES_NUMKONG`) still completes with status OK and
    records the degraded backend string in the row, rather than erroring."""
    import usearch.compiled as compiled

    monkeypatch.setattr(compiled, "USES_NUMKONG", 0, raising=False)

    ids, vecs = _small_corpus(n=10, dim=8)
    truth = bench_vector_store.brute_force_topk(vecs[:2], [(ids, vecs)], k=3)

    row = asyncio.run(
        bench_vector_store.run_cell(
            "usearch",
            "f16",
            dim=8,
            n=10,
            batch_source=lambda: [(ids, vecs)],
            query_vectors=vecs[:2],
            truth=truth,
            k=3,
            data_dir=tmp_path,
        )
    )
    assert row["status"] == "OK"
    assert "numkong=no" in row["usearch_acceleration"]
    line = bench_vector_store.render_row(row)
    assert "numkong=no" in line


def test_child_mode_requires_exactly_one_cell(tmp_path) -> None:
    argv = [
        "--corpus",
        "synthetic",
        "--n",
        "300",
        "--cells",
        "usearch:f16,usearch:i8",
        "--data-dir",
        str(tmp_path / "data"),
        "--child",
    ]
    with pytest.raises(SystemExit):
        bench_vector_store.main(argv)


def test_multi_cell_run_dispatches_one_subprocess_per_cell_with_two_rows(tmp_path, capsys) -> None:
    """Real end-to-end sanity check (stub/small path): a two-cell run
    produces exactly two data rows, each with a real (non ``-``)
    ``peak_rss_MB`` reading from its own child process."""
    argv = [
        "--corpus",
        "synthetic",
        "--n",
        "300",
        "--queries",
        "5",
        "--k",
        "3",
        "--cells",
        "usearch:f16,usearch:i8",
        "--data-dir",
        str(tmp_path / "data"),
    ]
    exit_code = bench_vector_store.main(argv)
    assert exit_code == 0

    captured = capsys.readouterr()
    row_lines = [ln for ln in captured.out.splitlines() if ln.startswith("| usearch")]
    assert len(row_lines) == 2, f"expected two data rows, got: {row_lines!r}"

    parsed_rows = [_parse_bench_row(ln) for ln in row_lines]
    for row in parsed_rows:
        _assert_row_sane(row)  # covers "expected real (non '-') RSS values"


def test_multi_cell_run_preserves_distinct_per_cell_rss_unforced(
    tmp_path, monkeypatch, capsys
) -> None:
    """AC (Leg 5 review fix, BLOCKING 1): before this fix, ``peak_rss_MB``
    was a process-lifetime watermark shared across every cell of ONE
    process, so sequential cells in a multi-cell run reported IDENTICAL RSS
    (the flight-log tables' 1282.54/1282.54, 2927.72/2927.72 pairs). This
    test proves the fix directly at the dispatch seam: two isolated child
    processes reporting two DIFFERENT ``peak_rss_MB`` values must both
    survive into the final table unmodified — the parent's multi-cell
    dispatch (``_run_cell_subprocess`` per cell) never derives, shares, or
    overwrites one cell's row from another's. (A real two-subprocess run
    can legitimately report near-identical RSS for two tiny same-footprint
    cells — see the sibling test above for that end-to-end sanity check —
    so asserting real-world inequality here would be flaky; mocking the
    per-cell dispatch keeps this test deterministic while still exercising
    the exact code path the bug lived in.)"""
    fake_rows = {
        ("usearch", "f16"): (
            "| usearch | f16 | 300 | 0.01 | 0.34 | 0.21 | 0.29 | 0.31 "
            "| 1.0000 | 111.11 | 11.60 | 1.68 | numkong=yes, simd=haswell | OK |"
        ),
        ("usearch", "i8"): (
            "| usearch | i8 | 300 | 0.01 | 0.17 | 0.15 | 0.20 | 0.22 "
            "| 1.0000 | 222.22 | 8.02 | 1.16 | numkong=yes, simd=haswell | OK |"
        ),
    }

    def _fake_run_cell_subprocess(base_argv: list[str], cell: tuple[str, str]) -> str:
        return fake_rows[cell]

    monkeypatch.setattr(bench_vector_store, "_run_cell_subprocess", _fake_run_cell_subprocess)

    argv = [
        "--corpus",
        "synthetic",
        "--n",
        "300",
        "--queries",
        "5",
        "--k",
        "3",
        "--cells",
        "usearch:f16,usearch:i8",
        "--data-dir",
        str(tmp_path / "data"),
    ]
    exit_code = bench_vector_store.main(argv)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert fake_rows[("usearch", "f16")] in captured.out
    assert fake_rows[("usearch", "i8")] in captured.out


def test_run_cell_pre_cleanup_failure_yields_error_row_not_a_crash(tmp_path, monkeypatch) -> None:
    """Leg 5 review fix-now: a locked leftover file at pre-cleanup time must
    yield this cell an ERROR row, never raise out of ``run_cell`` and abort
    the whole invocation."""

    def _boom(db_path, vectors_dir, kb_id) -> None:
        raise OSError("simulated locked leftover file")

    monkeypatch.setattr(bench_vector_store, "_cleanup_cell_files", _boom)

    ids, vecs = _small_corpus(n=10, dim=8)
    truth = bench_vector_store.brute_force_topk(vecs[:2], [(ids, vecs)], k=3)

    row = asyncio.run(
        bench_vector_store.run_cell(
            "usearch",
            "f16",
            dim=8,
            n=10,
            batch_source=lambda: [(ids, vecs)],
            query_vectors=vecs[:2],
            truth=truth,
            k=3,
            data_dir=tmp_path,
        )
    )
    assert row["status"].startswith("ERROR")
    assert "simulated locked leftover file" in row["status"]


# ── AC-6: real-corpus end-to-end under the suite-wide stub backend ────────


def test_end_to_end_real_corpus_under_stub_backend(tmp_path, capsys) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    paragraph = "This is a benchmark test paragraph about static embeddings. " * 15
    (corpus_dir / "a.md").write_text(f"# A\n\n{paragraph}\n\n{paragraph}\n", encoding="utf-8")
    (corpus_dir / "b.md").write_text(f"# B\n\n{paragraph}\n\n{paragraph}\n", encoding="utf-8")
    (corpus_dir / "c.md").write_text(f"# C\n\n{paragraph}\n\n{paragraph}\n", encoding="utf-8")

    argv = [
        "--corpus",
        "real",
        "--k",
        "3",
        "--cells",
        "usearch:f16",
        "--data-dir",
        str(tmp_path / "data"),
        "--real-corpus-root",
        str(corpus_dir),
    ]
    exit_code = bench_vector_store.main(argv)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "real corpus: 3 files" in captured.out
    assert "usearch" in captured.out
