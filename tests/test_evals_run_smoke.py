"""First end-to-end proof: one scripted run through the real factory and agent loop."""

from __future__ import annotations

import json

import _evals_helpers as h
from _evals_helpers import make_tree, run, script_hook, simple_scenario

from evals import scripted

evals_isolation = h.evals_isolation


async def test_text_only_run_passes_and_cleans_up(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    code, run_dir = await run(tmp, sdir, script_hook(scripted.text("hello there")))
    assert code == 0
    recs = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    assert len(recs) == 1
    assert recs[0]["outcome"] == "pass"
    assert recs[0]["execution_tools"] == "disabled"
    assert not (run_dir / "data").exists()
    assert (run_dir / "transcripts").is_dir()
