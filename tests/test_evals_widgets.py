"""The widgets scenario set under ``evals/widgets/`` (M35 F2 L7). Offline: scripted provider only.

Beside ``evals/visuals/`` and ``evals/scenarios/``, never inside them: ``compare`` refuses a run
whose scenarios fingerprint differs from the baseline's.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import _evals_helpers as h
import pytest
from _evals_helpers import run

from evals import scripted
from evals.fixtures import FIXTURE_HOSTNAME
from evals.scenario import load_scenarios
from evals.scripted import text

evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir

WIDGETS = Path(__file__).resolve().parent.parent / "evals" / "widgets" / "scenarios"
FIXTURE_BASE = f"http://{FIXTURE_HOSTNAME}"
FENCE = r"(?m)^```[ \t]*widget\b"
EXPECTED = {
    "widget-when-asked": "improve",
    "widget-not-for-data": "hold",
    "no-widget-unasked": "hold",
}


def records(run_dir: Path) -> list[dict]:
    return [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines() if x]


@pytest.fixture(scope="module")
def loaded():
    return {s.id: s for s in load_scenarios(WIDGETS, fixtures_root=WIDGETS.parent / "fixtures")}


def test_three_scenarios_with_four_phrasings_and_five_facts(loaded):
    assert {k: v.klass for k, v in loaded.items()} == EXPECTED
    for sid, sc in loaded.items():
        assert sc.cell_classes() == {sid: EXPECTED[sid]}
        assert len(sc.phrasings) == 4 and len(sc.facts) == 5, sid
        convs = {
            tuple(tuple(c) for c in sc.instantiate(v, FIXTURE_BASE).conversations)
            for v in sc.variants()
        }
        assert len(convs) == 20, sid


def test_check_names_and_parameters(loaded):
    def decls(sid):
        sc = loaded[sid]
        return sc.instantiate(sc.variants()[0], FIXTURE_BASE).checks

    (d,) = decls("widget-when-asked")
    assert d.name == "reply_has_valid_widget" and d.params == {}
    chart, fence = decls("widget-not-for-data")
    assert chart.name == "reply_has_valid_chart"
    assert fence.name == "reply_not_matches" and fence.params["pattern"] == FENCE
    (d,) = decls("no-widget-unasked")
    assert d.name == "reply_not_matches" and d.params["pattern"] == FENCE


def test_fence_pattern_does_not_cross_a_newline():
    fence = re.compile(FENCE)
    assert fence.search("intro\n```widget\n<script></script>\n```")
    assert fence.search("```  widget\nx")
    assert not fence.search("```chart\n{}\n```\nwidget notes follow")


def test_user_turns_never_name_the_tag_or_ask_for_code(loaded):
    banned = re.compile(r"```|\bwidget\b|\bhtml\b|\bjavascript\b|\bscript\b", re.IGNORECASE)
    for sc in loaded.values():
        for v in sc.variants():
            for conv in sc.instantiate(v, FIXTURE_BASE).conversations:
                for turn in conv:
                    assert not banned.search(turn), (sc.id, turn)


def test_the_files_hold_no_loopback_address():
    for path in WIDGETS.glob("*.toml"):
        assert "127.0.0.1" not in path.read_text(), path.name


# ── the can-fail proof ────────────────────────────────────────────────────

BAR = '{"type": "bar", "x": {"values": ["a", "b"]}, "series": [{"values": [1, 2]}]}'
WIDGET = "<div id=o></div><script>requestAnimationFrame(function(){o.textContent='x'})</script>"


def _w(body: str) -> str:
    return f"Here you go.\n```widget\n{body}\n```\n"


def _c(body: str) -> str:
    return f"Here you go.\n```chart\n{body}\n```\n"


CASES = {
    "widget-when-asked": (
        _w(WIDGET),
        [
            ("no widget", "Sure, in words.", True),
            ("unclosed", "```widget\n" + WIDGET, True),
            ("external", _w('<script src="https://cdn.example/x.js"></script>'), True),
        ],
    ),
    "widget-not-for-data": (
        _c(BAR),
        [
            ("no chart", "Mostly bread.", True),
            ("a widget instead", _w(WIDGET), True),
            ("both", _c(BAR) + _w(WIDGET), True),
        ],
    ),
    "no-widget-unasked": ("A short explanation.", [("widget anyway", _w(WIDGET), True)]),
}


@pytest.mark.parametrize("sid", sorted(EXPECTED))
async def test_passing_reply_passes_and_each_violation_fails(evals_isolation, sid):
    ok, violations = CASES[sid]

    def reply_for(pi):
        return ok if pi == 0 else violations[pi - 1][1]

    def hook(spec, base):
        return scripted.ScriptedProvider([text(reply_for(spec.variant.phrasing_index))])

    _code, run_dir = await run(
        evals_isolation, WIDGETS, hook, scenarios=[sid], n=1 + len(violations)
    )
    recs = {r["variant"]: r for r in records(run_dir)}
    assert recs["f0p0"]["outcome"] == "pass", recs["f0p0"]["checks"]
    for pi, (label, _reply, _x) in enumerate(violations, start=1):
        rec = recs[f"f0p{pi}"]
        assert rec["outcome"] == "fail", (label, rec["outcome"], rec["reason"])
        assert not all(c["passed"] for c in rec["checks"]), (label, rec["checks"])
