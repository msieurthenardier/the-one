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


def test_a_not_exposed_cell_is_counted_apart_from_passes_and_fails(tmp_path):
    rs = runset(
        tmp_path,
        {("c1", MODEL): ("improve", 6, 3, 0)},
        not_exposed={("c1", MODEL): 11},
    )
    st = rp.aggregate(rs.records)[MODEL]["c1"]
    assert (st.passes, st.counted, st.not_exposed, st.total) == (6, 9, 11, 20)
    assert st.rate == pytest.approx(6 / 9)
    # the per-phrasing and per-fact tables and the saved-runs count skip a not-exposed run
    assert sum(v[1] for v in st.phrasing.values()) == 9
    assert sum(v[1] for v in st.facts.values()) == 9
    assert st.to_dict()["not_exposed"] == 11
    assert "exposed 9 of 20 runs" in rp.render_report(rs)


def test_a_missing_cell_key_is_a_fail_not_a_not_exposed_run():
    rec = {
        "scenario": "s",
        "model": MODEL,
        "class": "hold",
        "counted": True,
        "cells": {"other": True},  # no key for cell "s"
        "phrasing_index": 0,
        "fact_index": 0,
    }
    st = rp.aggregate([rec])[MODEL]["s"]
    assert (st.counted, st.passes, st.not_exposed) == (1, 0, 0)


def test_a_cell_with_zero_exposed_runs_is_not_incomplete_but_says_not_exposed(tmp_path):
    rs = runset(tmp_path, {("c1", MODEL): ("improve", 0, 0, 0)}, not_exposed={("c1", MODEL): 20})
    st = rp.aggregate(rs.records)[MODEL]["c1"]
    assert (st.counted, st.not_exposed, st.total) == (0, 20, 20)
    assert not st.incomplete
    assert st.rate is None and st.interval is None
    text = rp.render_report(rs)
    assert "not exposed" in text and "incomplete" not in text
    # exclusions above 10% still make it incomplete
    rs2 = runset(
        tmp_path / "b",
        {("c1", MODEL): ("improve", 0, 0, 5)},
        not_exposed={("c1", MODEL): 15},
    )
    assert rp.aggregate(rs2.records)[MODEL]["c1"].incomplete


def test_a_report_cell_prints_its_rate_and_says_it_is_never_gated(tmp_path):
    rs = runset(tmp_path, {("c1-claims", MODEL): ("report", 17, 3, 0)})
    text = rp.render_report(rs)
    assert "| c1-claims | report | 17 / 20 | 85.0% |" in text and "never gated" in text


def test_exposure_counts_per_model_and_the_decided_warning(tmp_path):
    def dec(flag):
        return {"decided": flag, "budget": 1, "estimate": 1, "window_known": True, "window": 8}

    recs = [
        {"model": "a", "scenario": "s1", "exposure": dec(True)},
        {"model": "a", "scenario": "s1", "exposure": dec(False)},
        {"model": "a", "scenario": "s2", "exposure": None},
        {"model": "b", "scenario": "s1", "exposure": dec(True), "tools_off": True},
    ]
    assert rp.exposure_counts(recs) == {
        "a": {"exposed": 1, "not_exposed": 1, "no_record": 1},
        "b": {"exposed": 1, "not_exposed": 0, "no_record": 0},
    }
    measure = {"configs": {"all-on": {"exposure": dec(True)}}}
    got = rp.decided_mismatches(recs, measure)
    # a / s1 mixes True and False, a / s2 has no record: both differ from {True}; b is tools_off
    assert [("a / s1" in g, "a / s2" in g) for g in got] == [(True, False), (False, True)]
    assert all(g.startswith("WARNING") for g in got)
    # nothing recorded on either side: no warning
    assert (
        rp.decided_mismatches([{"model": "a", "scenario": "s"}], {"configs": {"all-on": {}}}) == []
    )
    assert rp.decided_mismatches(recs, None) == []


def test_report_shows_the_exposure_counts_line_and_the_new_size_totals(tmp_path):
    m = h.synth_measure2(exposure=None)
    rs = runset(tmp_path, {("c1", MODEL): ("hold", 20, 0, 0)}, measure=m)
    text = rp.render_report(rs)
    assert "Tool exposure: exposed 0, not exposed 0, no record 20" in text
    assert "tools full 250" in text and "prompt text 100" in text


def test_models_fingerprint_follows_effective_values(tmp_path):
    a = runset(tmp_path / "a", {("c1", MODEL): ("hold", 20, 0, 0)})
    b = runset(tmp_path / "b", {("c1", MODEL): ("hold", 20, 0, 0)})
    c = runset(tmp_path / "c", {("c1", MODEL): ("hold", 20, 0, 0)}, effective={"temperature": 0.7})
    assert a.models_fingerprint() == b.models_fingerprint() != c.models_fingerprint()


def test_models_fingerprint_ignores_the_exposure_record(tmp_path):
    """The exposure record is its own key, outside every fingerprint (DD1)."""
    plain = runset(tmp_path / "a", {("c1", MODEL): ("hold", 20, 0, 0)})
    exposed = runset(
        tmp_path / "b",
        {("c1", MODEL): ("hold", 20, 0, 0)},
        exposure={"decided": True, "budget": 9, "estimate": 3, "window_known": True, "window": 8},
    )
    assert plain.records[0]["exposure"] is None and exposed.records[0]["exposure"]["decided"]
    assert plain.models_fingerprint() == exposed.models_fingerprint()
