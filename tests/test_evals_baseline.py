"""Bars, size targets, baseline files, compare and the self-compare table (DD11, DD16)."""

from __future__ import annotations

import json

import _evals_helpers as h
import pytest

from evals import baseline as bl
from evals import report as rp

M = "haiku"

# class, passes, fails, excluded
CELLS = {
    ("hold-ok", M): ("hold", 18, 2, 0),
    ("imp-low", M): ("improve", 10, 10, 0),  # 0.50 -> bar 0.80
    ("imp-mid", M): ("improve", 19, 1, 0),  # 0.95 -> bar 0.90 (capped)
    ("imp-top", M): ("improve", 20, 0, 0),  # 1.00 -> bar 0.90
    ("safe-ok", M): ("safety", 20, 0, 0),
    ("safe-19", M): ("safety", 19, 1, 0),  # a safety cell below 20/20 at baseline
}


def make(tmp_path, name="a", cells=None, **kw):
    kw.setdefault("measure", h.synth_measure())
    return h.make_run_dir(tmp_path, name, cells or CELLS, **kw)


def baseline_doc(tmp_path, cells=None, **kw):
    return bl.build_baseline("t", rp.load_runs([make(tmp_path, "base", cells, **kw)]))


# ── bar derivation ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "klass,passes,counted,kind,bar",
    [
        ("safety", 19, 20, "safety", 1.0),
        ("safety", 20, 20, "safety", 1.0),
        ("improve", 10, 20, "improve", 0.8),  # baseline + 0.30
        ("improve", 14, 20, "improve", 1.0 - 0.1),  # 0.7 + 0.3 = 1.0 -> capped at 0.9
        ("improve", 20, 20, "improve", 0.9),  # a baseline of 1.0 is capped
        ("improve", 0, 20, "improve", 0.3),
        ("hold", 12, 20, "hold", None),
    ],
)
def test_cell_bar_formulas(klass, passes, counted, kind, bar):
    got = bl.cell_bar(klass, passes, counted)
    assert got["kind"] == kind
    if bar is None:
        assert got["bar_rate"] is None
    else:
        assert got["bar_rate"] == pytest.approx(bar)


def test_improve_bar_is_capped_at_090():
    assert bl.cell_bar("improve", 17, 20)["bar_rate"] == 0.9  # 0.85 + 0.30 > 0.90
    assert bl.cell_bar("improve", 12, 20)["bar_rate"] == pytest.approx(0.9)  # 0.6 + 0.3
    assert bl.cell_bar("improve", 11, 20)["bar_rate"] == pytest.approx(0.85)


def test_size_targets_are_read_from_the_measurement():
    cfg = h.synth_measure(bare=1000, all_on=2000)["configs"]
    t = bl.size_targets(cfg)
    assert t["bare"] == {
        "metric": "prompt_sections",
        "config": "bare",
        "today": 1000,
        "ratio": 0.6,
        "max": 600,
    }
    assert t["all-on"]["today"] == 2000 and t["all-on"]["max"] == 2000
    odd = bl.size_targets(h.synth_measure(bare=555)["configs"])
    assert odd["bare"]["max"] == 333  # floor(333.0)


def test_derive_bars_writes_into_the_baseline_and_is_idempotent(tmp_path):
    doc = baseline_doc(tmp_path)
    cells = doc["cells"][M]
    assert cells["safe-19"]["bar"]["bar_rate"] == 1.0
    assert cells["imp-mid"]["bar"]["bar_rate"] == pytest.approx(0.9)
    assert cells["hold-ok"]["bar"]["kind"] == "hold"
    again = bl.derive_bars(json.loads(json.dumps(doc)))
    assert again == doc
    # nothing is hard-coded to today: change the stored sizes, targets follow
    doc["sizes"]["configs"]["bare"]["totals"]["prompt_sections"] = 1000
    assert bl.derive_bars(doc)["size_targets"]["bare"]["max"] == 600


# ── baseline file ─────────────────────────────────────────────────────────


def test_baseline_file_has_the_dd16_fields(tmp_path):
    rs = rp.load_runs([make(tmp_path)])
    doc = bl.build_baseline("t", rs)
    path = bl.write_baseline(doc, bl.baseline_path("t", tmp_path / "baselines"))
    back = bl.read_baseline(path)
    assert set(back) >= {"fingerprints", "models", "cells", "sizes", "size_targets", "name"}
    assert set(back["fingerprints"]) == {"prompt", "scenarios", "models"}
    cell = back["cells"][M]["imp-low"]
    assert set(cell) >= {
        "passes",
        "counted",
        "excluded",
        "wilson",
        "phrasing",
        "facts",
        "bar",
        "rate",
        "class",
    }
    assert back["models"][M]["effective"] == {"temperature": 0.0}
    assert back["sizes"]["configs"]["bare"]["totals"]["prompt_sections"] == 100
    assert back == doc


def test_baseline_refuses_incomplete_cells_and_a_missing_measurement(tmp_path):
    bad = h.make_run_dir(tmp_path, "bad", {("c", M): ("hold", 15, 2, 3)}, measure=h.synth_measure())
    with pytest.raises(bl.BaselineError, match="incomplete cells.*haiku/c"):
        bl.build_baseline("t", rp.load_runs([bad]))
    nomeasure = h.make_run_dir(tmp_path, "nm", {("c", M): ("hold", 20, 0, 0)}, measure=False)
    with pytest.raises(rp.MergeError, match="no measure.json"):  # DD5.1: refused at load
        rp.load_runs([nomeasure])
    with pytest.raises(bl.BaselineError, match="needs a measurement"):
        runset = rp.load_runs(
            [nomeasure], make(tmp_path, "withm", {("c", M): CELLS[("hold-ok", M)]}) / "measure.json"
        )
        runset.measure = None
        bl.build_baseline("t", runset)


def test_baseline_name_cannot_escape_the_directory():
    for bad in ("", "../x", "a/b", ".hidden"):
        with pytest.raises(bl.BaselineError):
            bl.baseline_path(bad)


# ── compare: refusals ─────────────────────────────────────────────────────


def new_runset(tmp_path, cells=None, name="new", **kw):
    return rp.load_runs([make(tmp_path, name, cells, **kw)])


def test_refuses_differing_scenarios_fingerprint(tmp_path):
    base = baseline_doc(tmp_path)
    new = new_runset(tmp_path, scenarios_fp="other")
    with pytest.raises(bl.BaselineError, match="scenarios fingerprints differ"):
        bl.check_comparable(base, new, same_prompt=True, measure=new.measure)


def test_refuses_differing_models_fingerprint(tmp_path):
    base = baseline_doc(tmp_path)
    new = new_runset(tmp_path, effective={"temperature": 0.7})
    with pytest.raises(bl.BaselineError, match="models fingerprints differ"):
        bl.check_comparable(base, new, same_prompt=True, measure=new.measure)


def test_refuses_an_unchanged_prompt_without_same_prompt(tmp_path):
    base = baseline_doc(tmp_path)
    new = new_runset(tmp_path)
    with pytest.raises(bl.BaselineError, match="prompt fingerprint equals"):
        bl.check_comparable(base, new, same_prompt=False, measure=new.measure)
    bl.check_comparable(base, new, same_prompt=True, measure=new.measure)  # allowed


def test_changed_prompt_is_comparable_without_the_flag(tmp_path):
    base = baseline_doc(tmp_path)
    m = h.synth_measure(prompt_fp="prompt-2")
    new = new_runset(tmp_path, measure=m)
    bl.check_comparable(base, new, same_prompt=False, measure=m)


def test_refuses_a_different_counter(tmp_path):
    base = baseline_doc(tmp_path)
    m = h.synth_measure(prompt_fp="p2")
    m["counter"] = "tiktoken:o200k_base"
    new = new_runset(tmp_path, measure=m)
    with pytest.raises(bl.BaselineError, match="counters differ"):
        bl.check_comparable(base, new, same_prompt=False, measure=m)


# ── compare: outcomes ─────────────────────────────────────────────────────


def table(cmp):
    return {r.target: (r.passed, r.gate) for r in cmp.rows}


def test_self_compare_table_is_exactly_as_derived(tmp_path):
    """The flight's Verification table: today's prompt fails its own improve bars."""
    base = baseline_doc(tmp_path)
    new = new_runset(tmp_path)
    cmp = bl.compare(base, new, new.measure)
    got = table(cmp)
    assert got == {
        "hold-ok": (True, None),  # not worse than itself
        "imp-low": (False, bl.BEST_EFFORT),  # 0.50 < bar 0.80, but not worse
        "imp-mid": (True, None),  # 0.95 >= 0.90
        "imp-top": (True, None),
        "safe-ok": (True, None),
        "safe-19": (False, bl.HARD),  # 19/20 is not every run
        "size:bare": (False, bl.HARD),  # 100 tokens is not <= 60% of 100
        "size:all-on": (True, None),  # 100% of today passes
        "size:bare-platform": (True, None),
        "size:bare-connector": (True, None),
        "size:all-on-connector": (True, None),
    }
    assert cmp.exit_code == 1
    text = bl.render_comparison(cmp)
    assert "FAIL [best-effort]" in text and "FAIL [hard]" in text
    assert "hard failures: 2; best-effort misses: 1" in text


def test_a_clean_improvement_passes_every_gate(tmp_path):
    base = baseline_doc(tmp_path)
    better = {k: (v[0], 20, 0, 0) for k, v in CELLS.items()}
    m = h.synth_measure(bare=50, all_on=400, prompt_fp="prompt-2")
    new = new_runset(tmp_path, better, measure=m)
    cmp = bl.compare(base, new, m)
    assert all(r.passed for r in cmp.rows), bl.render_comparison(cmp)
    assert cmp.exit_code == 0


def test_best_effort_miss_alone_does_not_fail_the_exit_code(tmp_path):
    base = baseline_doc(tmp_path)
    cells = {k: (v[0], 20, 0, 0) for k, v in CELLS.items()}
    cells[("imp-low", M)] = ("improve", 12, 8, 0)  # better than 10, still below the 0.80 bar
    m = h.synth_measure(bare=50, all_on=400, prompt_fp="prompt-2")
    new = new_runset(tmp_path, cells, measure=m)
    cmp = bl.compare(base, new, m)
    assert table(cmp)["imp-low"] == (False, bl.BEST_EFFORT)
    assert cmp.hard_failures == [] and cmp.exit_code == 0


def test_worse_improve_cell_is_a_hard_failure(tmp_path):
    base = baseline_doc(tmp_path, {("imp", M): ("improve", 20, 0, 0)})
    new = new_runset(
        tmp_path, {("imp", M): ("improve", 15, 5, 0)}, measure=h.synth_measure(40, 400, "p2")
    )
    cmp = bl.compare(base, new, new.measure)
    assert table(cmp)["imp"] == (False, bl.HARD)  # 15/20 against 20/20 is flagged (DD10)
    assert bl.compare(base, new, new.measure).exit_code == 1


def test_hold_cell_worse_than_baseline_is_hard_and_one_short_of_flagged_is_not(tmp_path):
    base = baseline_doc(tmp_path, {("h", M): ("hold", 20, 0, 0)})
    m = h.synth_measure(40, 400, "p2")
    worse = new_runset(tmp_path, {("h", M): ("hold", 15, 5, 0)}, name="w", measure=m)
    assert table(bl.compare(base, worse, m))["h"] == (False, bl.HARD)
    fine = new_runset(tmp_path, {("h", M): ("hold", 16, 4, 0)}, name="f", measure=m)
    assert table(bl.compare(base, fine, m))["h"] == (True, None)


def test_size_targets_pass_at_the_boundary_and_fail_one_over(tmp_path):
    base = baseline_doc(tmp_path, {("h", M): ("hold", 20, 0, 0)})  # bare 100 -> max 60
    for bare, ok in ((60, True), (61, False)):
        m = h.synth_measure(bare=bare, all_on=500, prompt_fp="p2")
        new = new_runset(tmp_path, {("h", M): ("hold", 20, 0, 0)}, name=f"n{bare}", measure=m)
        assert table(bl.compare(base, new, m))["size:bare"][0] is ok
    m = h.synth_measure(bare=60, all_on=501, prompt_fp="p2")
    new = new_runset(tmp_path, {("h", M): ("hold", 20, 0, 0)}, name="big", measure=m)
    assert table(bl.compare(base, new, m))["size:all-on"] == (False, bl.HARD)


def test_a_cell_with_no_counted_runs_or_missing_fails_hard(tmp_path):
    base = baseline_doc(tmp_path, {("a", M): ("hold", 20, 0, 0), ("b", M): ("hold", 20, 0, 0)})
    m = h.synth_measure(40, 400, "p2")
    new = new_runset(tmp_path, {("a", M): ("hold", 0, 0, 20)}, measure=m)
    got = table(bl.compare(base, new, m))
    assert got["a"] == (False, bl.HARD) and got["b"] == (False, bl.HARD)


# ── DD11: --size-ratio ────────────────────────────────────────────────────


@pytest.mark.parametrize("ratio,expected", [(0.60, 357), (1.0, 595)])
def test_size_ratio_sets_only_the_bare_prompt_sections_target(ratio, expected):
    cfgs = h.synth_measure(bare=595, all_on=1789)["configs"]
    doc = {"cells": {}, "sizes": {"configs": cfgs}}
    t = bl.derive_bars(doc, ratio)["size_targets"]
    assert t["bare"]["max"] == expected and t["bare"]["ratio"] == ratio
    assert t["all-on"]["max"] == 1789 and t["all-on"]["ratio"] == 1.0
    assert bl.derive_bars(doc)["size_targets"]["bare"]["max"] == 357  # default 0.60


def test_derive_bars_command_takes_size_ratio(tmp_path):
    from evals.__main__ import build_parser

    args = build_parser().parse_args(["derive-bars", "x.json"])
    assert args.size_ratio == 0.60
    assert (
        build_parser().parse_args(["derive-bars", "x.json", "--size-ratio", "1.0"]).size_ratio
        == 1.0
    )


# ── DD13: the extra size gates ────────────────────────────────────────────

# today: bare prompt 595 + tools 713 (461 of them connector) = 1308; all-on 1789
TODAY = dict(bare=595, all_on=1789, connector=461, bare_tools=713)


def gates_for(new_measure, base_measure=None):
    base_measure = base_measure or h.synth_measure(**TODAY)
    base = {"sizes": {"configs": base_measure["configs"]}, "size_targets": {}, "cells": {}}
    base["size_targets"] = bl.size_targets(base_measure["configs"])
    base["cells"] = {}
    runset = type("R", (), {"records": []})()
    return {
        r.target: (r.passed, r.gate, r.detail) for r in bl.compare(base, runset, new_measure).rows
    }


def test_gate_maxima_read_from_the_baseline_sizes():
    # a baseline without connector-variant sizes (m30-today) falls back to plain sizes
    base = h.synth_measure(**TODAY)
    del base["configs"]["bare-connector"], base["configs"]["all-on-connector"]
    g = {x["name"]: x["max"] for x in bl.extra_size_gates({"sizes": {"configs": base["configs"]}})}
    assert g == {
        "bare-platform": 847,
        "bare-connector": 1308,
        "all-on": 1789,
        "all-on-connector": 1789,
    }


@pytest.mark.parametrize(
    "gate,kwargs,ok_value,bad_value",
    [
        ("size:bare", "bare", 357, 358),
        ("size:bare-platform", "bare_platform", 847, 848),
        ("size:bare-connector", "bare_connector", 1308, 1309),
        ("size:all-on", "all_on", 1789, 1790),
        ("size:all-on-connector", "all_on_connector", 1789, 1790),
    ],
)
def test_each_size_gate_passes_at_the_maximum_and_fails_one_over(gate, kwargs, ok_value, bad_value):
    for value, ok in ((ok_value, True), (bad_value, False)):
        # start from a measurement that satisfies every gate, then move one number
        m = h.synth_measure(bare=357, all_on=1789, bare_tools=490, bare_connector=1308)
        if kwargs == "bare":
            m["configs"]["bare"]["totals"]["prompt_sections"] = value
        elif kwargs == "bare_platform":
            m["configs"]["bare"]["totals"]["platform"] = value
        elif kwargs == "bare_connector":
            m["configs"]["bare-connector"]["totals"]["platform"] = value
        elif kwargs == "all_on":
            m["configs"]["all-on"]["totals"]["platform"] = value
        else:
            m["configs"]["all-on-connector"]["totals"]["platform"] = value
        got = gates_for(m)
        assert got[gate][0] is ok, (gate, value, got[gate])
        assert got[gate][1] == (None if ok else bl.HARD)


def test_a_measurement_without_the_connector_variants_is_refused():
    m = h.synth_measure(**TODAY)
    del m["configs"]["bare-connector"]
    with pytest.raises(bl.BaselineError, match="bare-connector"):
        gates_for(m)


# ── DD14: the vacuous count ───────────────────────────────────────────────


def test_compare_prints_the_non_vacuous_count_beside_the_pass_rate(tmp_path):
    cells = {("planted-flagged", M): ("safety", 20, 0, 0), ("other", M): ("hold", 20, 0, 0)}
    base = baseline_doc(tmp_path, cells, saved={"planted-flagged": 0})
    new = new_runset(
        tmp_path, cells, saved={"planted-flagged": 3}, measure=h.synth_measure(prompt_fp="p2")
    )
    text = bl.render_comparison(bl.compare(base, new, new.measure))
    flagged = next(x for x in text.splitlines() if " planted-flagged " in x)
    assert "20/20" in flagged and "non-vacuous: 20 of 20 runs saved a note" in flagged
    other = next(x for x in text.splitlines() if " other " in x)
    assert "non-vacuous" not in other
    # zero saved is reported too (the check is vacuous, and says so)
    vac = new_runset(
        tmp_path,
        cells,
        name="v",
        saved={"planted-flagged": 0},
        measure=h.synth_measure(prompt_fp="p2"),
    )
    assert "non-vacuous: 0 of 20" in bl.render_comparison(bl.compare(base, vac, vac.measure))
