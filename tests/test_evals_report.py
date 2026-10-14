"""Merging run directories, cell aggregation and report.md (DD16). Offline, synthetic runs."""

from __future__ import annotations

import _evals_helpers as h
import pytest

from evals import report as rp
from evals.stats import wilson

MODEL = "haiku"


def runset(tmp_path, cells, **kw):
    d = h.make_run_dir(tmp_path, "r1", cells, **kw)
    return rp.load_runs([d])


def test_cell_counts_rate_interval_and_exclusions(tmp_path):
    rs = runset(tmp_path, {("c1", MODEL): ("hold", 15, 3, 2)})
    st = rp.aggregate(rs.records)[MODEL]["c1"]
    assert (st.passes, st.counted, st.excluded, st.total) == (15, 18, 2, 20)
    assert st.rate == pytest.approx(15 / 18)
    assert st.interval == pytest.approx(wilson(15, 18))
    assert st.excluded_rate == pytest.approx(0.10)
    assert not st.incomplete  # exactly 10% is not above 10%
    # per-phrasing and per-fact counts add up to the counted runs
    assert sum(v[1] for v in st.phrasing.values()) == 18
    assert sum(v[1] for v in st.facts.values()) == 18
    assert sum(v[0] for v in st.phrasing.values()) == 15


def test_incomplete_when_exclusions_exceed_ten_percent_or_nothing_counted(tmp_path):
    rs = runset(
        tmp_path,
        {("over", MODEL): ("hold", 15, 2, 3), ("none", MODEL): ("hold", 0, 0, 20)},
    )
    stats = rp.aggregate(rs.records)[MODEL]
    assert stats["over"].incomplete
    none = stats["none"]
    assert none.counted == 0 and none.incomplete
    assert none.rate is None and none.interval is None  # n/a, no division by zero
    text = rp.render_report(rs)
    assert "n/a" in text and "incomplete" in text


def test_vacuous_safety_pass_is_reported(tmp_path):
    rs = runset(
        tmp_path,
        {("planted-flagged", MODEL): ("safety", 20, 0, 0)},
        saved={"planted-flagged": 0},
    )
    assert "pass (vacuous: 0 of 20 saved)" in rp.render_report(rs)
    rs2 = runset(
        tmp_path / "b",
        {("planted-flagged", MODEL): ("safety", 20, 0, 0)},
        saved={"planted-flagged": 3},
    )
    st = rp.aggregate(rs2.records)[MODEL]["planted-flagged"]
    assert st.saved_runs == 20  # every record carried saved=3
    assert "non-vacuous: 20 of 20 runs saved a note" in rp.render_report(rs2)


def test_report_has_cells_fingerprints_and_parts(tmp_path):
    rs = runset(
        tmp_path,
        {("c1", MODEL): ("improve", 10, 10, 0)},
        measure=h.synth_measure(),
    )
    text = rp.render_report(rs)
    assert "| c1 | improve | 10 / 20 | 50.0% |" in text
    assert "scenario" in text.lower()
    assert "### bare" in text and "standin" in text
    path = rp.write_report(rs)
    assert path.read_text() == text and path.name == "report.md"


def test_merge_two_directories_one_per_model(tmp_path):
    a = h.make_run_dir(tmp_path, "a", {("c1", "haiku"): ("hold", 20, 0, 0)})
    b = h.make_run_dir(tmp_path, "b", {("c1", "gpt-oss"): ("hold", 18, 2, 0)})
    rs = rp.load_runs([a, b])
    assert rs.models() == ["gpt-oss", "haiku"]
    assert set(rs.presets) == {"haiku", "gpt-oss"}


def test_merge_refuses_differing_scenarios_fingerprints(tmp_path):
    a = h.make_run_dir(tmp_path, "a", {("c1", "haiku"): ("hold", 20, 0, 0)}, scenarios_fp="s1")
    b = h.make_run_dir(tmp_path, "b", {("c1", "gpt-oss"): ("hold", 20, 0, 0)}, scenarios_fp="s2")
    with pytest.raises(rp.MergeError, match="scenarios fingerprints differ"):
        rp.load_runs([a, b])


def test_merge_refuses_differing_prompt_fingerprints(tmp_path):
    a = h.make_run_dir(
        tmp_path,
        "a",
        {("c1", "haiku"): ("hold", 20, 0, 0)},
        measure=h.synth_measure(prompt_fp="p1"),
    )
    b = h.make_run_dir(
        tmp_path,
        "b",
        {("c1", "gpt-oss"): ("hold", 20, 0, 0)},
        measure=h.synth_measure(prompt_fp="p2"),
    )
    with pytest.raises(rp.MergeError, match="prompt fingerprints differ"):
        rp.load_runs([a, b])


def test_merge_refuses_a_run_in_two_directories_and_a_non_run_directory(tmp_path):
    a = h.make_run_dir(tmp_path, "a", {("c1", "haiku"): ("hold", 20, 0, 0)})
    b = h.make_run_dir(tmp_path, "b", {("c1", "haiku"): ("hold", 20, 0, 0)})
    with pytest.raises(rp.MergeError, match="appears in both"):
        rp.load_runs([a, b])
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(rp.MergeError, match="not a run directory"):
        rp.load_runs([empty])


def test_models_fingerprint_follows_effective_values(tmp_path):
    a = runset(tmp_path / "a", {("c1", MODEL): ("hold", 20, 0, 0)})
    b = runset(tmp_path / "b", {("c1", MODEL): ("hold", 20, 0, 0)})
    c = runset(tmp_path / "c", {("c1", MODEL): ("hold", 20, 0, 0)}, effective={"temperature": 0.7})
    assert a.models_fingerprint() == b.models_fingerprint() != c.models_fingerprint()
