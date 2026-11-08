"""``compare --models``: a subset compare against a baseline (sortie 14 DD7). Offline."""

from __future__ import annotations

import json
from pathlib import Path

import _evals_helpers as h
import pytest

from evals import baseline as bl
from evals import report as rp
from evals.__main__ import main

S11 = Path(__file__).resolve().parent.parent / "evals" / "baselines" / "s11-platform.json"

CELLS = {
    ("hold-a", "haiku"): ("hold", 18, 2, 0),
    ("hold-a", "other"): ("hold", 10, 10, 0),
}
HAIKU_ONLY = {k: v for k, v in CELLS.items() if k[1] == "haiku"}


def make(tmp_path, name, cells):
    return h.make_run_dir(tmp_path, name, cells, measure=h.synth_measure())


def baseline_and_run(tmp_path, base_cells=CELLS, run_cells=CELLS):
    base = bl.build_baseline("t", rp.load_runs([make(tmp_path, "base", base_cells)]))
    run = rp.load_runs([make(tmp_path, "new", run_cells)])
    return base, run


def test_recomputed_full_set_digest_equals_the_stored_one_for_s11():
    base = json.loads(S11.read_text(encoding="utf-8"))
    assert (
        bl.baseline_models_fingerprint(base, list(base["models"]))
        == (base["fingerprints"]["models"])
    )


def test_recomputed_haiku_digest_equals_a_haiku_only_runset_digest():
    base = json.loads(S11.read_text(encoding="utf-8"))
    entry = base["models"]["haiku"]
    records = [
        {
            "scenario": "s",
            "variant": "v",
            "model": "haiku",
            "effective": entry["effective"],
            "model_info": entry["model_info"],
        }
    ]
    runset = rp.RunSet(
        dirs=[], records=records, scenarios_fp=None, presets={"haiku": entry["preset"]}
    )
    assert bl.baseline_models_fingerprint(base, ["haiku"]) == runset.models_fingerprint()


def test_subset_compare_drops_unselected_cells_and_states_the_selection(tmp_path):
    base, run = baseline_and_run(tmp_path)
    run, sel = bl.select_models(base, run, ["haiku"])
    bl.check_comparable(base, run, same_prompt=True, measure=run.measure, models=sel)
    cmp = bl.compare(base, run, run.measure, models=sel)
    assert {r.model for r in cmp.rows if r.kind != "size"} == {"haiku"}
    text = bl.render_comparison(cmp)
    assert "SUBSET compare: models haiku only" in text
    assert not any(
        "other" in line for line in text.splitlines() if line.startswith(("PASS", "FAIL"))
    )


def test_full_compare_is_unchanged_without_models(tmp_path):
    base, run = baseline_and_run(tmp_path)
    bl.check_comparable(base, run, same_prompt=True, measure=run.measure)
    cmp = bl.compare(base, run, run.measure)
    assert {r.model for r in cmp.rows if r.kind != "size"} == {"haiku", "other"}
    assert "SUBSET" not in bl.render_comparison(cmp)


def test_a_superset_run_is_filtered_quietly(tmp_path):
    base, run = baseline_and_run(tmp_path, base_cells=HAIKU_ONLY)
    with pytest.raises(bl.BaselineError, match="models fingerprints differ"):
        bl.check_comparable(base, run, same_prompt=True, measure=run.measure)
    run, sel = bl.select_models(base, run, ["haiku"])
    assert {r["model"] for r in run.records} == {"haiku"}
    bl.check_comparable(base, run, same_prompt=True, measure=run.measure, models=sel)
    cmp = bl.compare(base, run, run.measure, models=sel)
    assert not any("other" in n for n in cmp.notes)


def test_refuses_a_name_the_baseline_lacks(tmp_path):
    base, run = baseline_and_run(tmp_path)
    with pytest.raises(bl.BaselineError, match="nope.*baseline does not have"):
        bl.select_models(base, run, ["haiku", "nope"])


def test_refuses_a_selected_model_with_no_records_in_the_run(tmp_path):
    base, run = baseline_and_run(tmp_path, run_cells=HAIKU_ONLY)
    with pytest.raises(bl.BaselineError, match="other.*no records in the run"):
        bl.select_models(base, run, ["other"])


def test_refuses_an_empty_selection_and_deduplicates(tmp_path):
    base, run = baseline_and_run(tmp_path)
    with pytest.raises(bl.BaselineError, match="at least one model"):
        bl.select_models(base, run, [])
    _, sel = bl.select_models(base, run, ["haiku", "haiku"])
    assert sel == ["haiku"]


def test_cli_models_flag_runs_a_subset_compare(tmp_path, capsys):
    base, _ = baseline_and_run(tmp_path)
    base_path = tmp_path / "base.json"
    bl.write_baseline(base, base_path)
    run_dir = str(tmp_path / "new")
    common = ["compare", run_dir, "--baseline", str(base_path), "--same-prompt"]
    rc = main([*common, "--models", "haiku"])
    assert "SUBSET compare" in capsys.readouterr().out
    assert rc in (0, 1)
    assert main([*common, "--models", ""]) == 2
