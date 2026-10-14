"""Knowledge-base fixtures indexed with the real IndexingManager and the bundled model.

This module is listed in ``tests/conftest.py::_EMBEDDING_REAL_LOAD_MODULES`` so the
autouse stub embedding backend (dim 8) does not replace the bundled model (dim 512).
Offline: the model is package data.
"""

from __future__ import annotations

import json
from pathlib import Path

import _evals_helpers as h
from _evals_helpers import make_tree, run

from evals import scripted
from evals.scripted import call, text

evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir


def records(run_dir: Path) -> list[dict]:
    return [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines() if x]


def transcript(run_dir: Path, stem: str) -> dict:
    return json.loads((run_dir / "transcripts" / f"{stem}.json").read_text())


def tool_results(tr: dict) -> list[dict]:
    return [m["tool_result"] for t in tr["turns"] for m in t["messages"] if m["role"] == "tool"]


def hook_for(factory):
    def hook(spec, base):
        return scripted.ScriptedProvider(factory(spec, base))

    return hook


KB_SCENARIO = """
id = "kb"
class = "improve"

[agent]
[[agent.kb]]
name = "Lighthouse Archive"
fixture = "lighthouse"

[[conversations]]
turns = ["Who keeps the Skerry lighthouse?"]

[[checks]]
name = "search_tools_used"
cell = "kb-find"

[[checks]]
name = "tool_called"
pattern = "kb__.*__search"
cell = "kb-find"

[[checks]]
name = "reply_matches"
pattern = "Odalys"
cell = "kb-answer"
"""


async def test_kb_fixture_indexed_found_via_search_tools_and_queried(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"kb": KB_SCENARIO})
    from evals.fixtures import kb_id_for
    from the_one.db.models import KnowledgeBase
    from the_one.knowledge.tool_provider import compute_tool_names

    kb_id = kb_id_for("lighthouse")
    tool_name = compute_tool_names(
        [KnowledgeBase(id=kb_id, name="Lighthouse Archive")], agent_name="x"
    )[kb_id]
    assert tool_name.startswith("kb__Lighthouse_Archive_")  # slug verbatim from the scenario name
    hook = hook_for(
        lambda spec, base: [
            call("search_tools", {"query": "lighthouse archive documents"}, call_id="k1"),
            call(tool_name, {"query": "lighthouse keeper"}, call_id="k2"),
            text("The keeper is Odalys Fenwick."),
        ]
    )
    code, run_dir = await run(tmp, sdir, hook, hook_kw={"index_timeout": 300.0})
    (rec,) = records(run_dir)
    assert rec["outcome"] == "pass", rec["checks"]
    assert rec["cells"] == {"kb-find": True, "kb-answer": True}
    tr = transcript(run_dir, "kb__gpt-oss__f0p0__a1")
    found, hits = tool_results(tr)
    assert tool_name in found["content"]  # discoverable through search_tools
    assert not hits["is_error"] and not hits["content"].startswith("[error]")
    assert "Odalys Fenwick" in hits["content"]
    assert (run_dir / "kb" / "lighthouse" / "keeper.md").exists()  # outside data/ and home/
    assert not (run_dir / "data").exists()


async def test_kb_checks_can_fail(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"kb": KB_SCENARIO})
    hook = hook_for(lambda spec, base: [text("The keeper is unknown.")])
    code, run_dir = await run(tmp, sdir, hook, hook_kw={"index_timeout": 300.0})
    (rec,) = records(run_dir)
    assert rec["outcome"] == "fail"
    assert rec["cells"] == {"kb-find": False, "kb-answer": False}
