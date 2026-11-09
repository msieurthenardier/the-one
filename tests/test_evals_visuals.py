"""Rich visuals in the evals (M35 F1 L4): the ``rich_visuals`` agent key and the four
scenarios under ``evals/visuals/``. Offline: scripted provider only.

The scenarios live beside, not inside, ``evals/scenarios/``: ``compare`` refuses a run whose
scenarios fingerprint differs from the baseline's, and ``s11-platform`` pins the original set.
"""

from __future__ import annotations

import json
from pathlib import Path

import _evals_helpers as h
import pytest
from _evals_helpers import make_tree, run, simple_scenario

from evals import scripted
from evals.fixtures import FIXTURE_HOSTNAME
from evals.scenario import ScenarioError, load_scenarios, parse_scenario
from evals.scripted import text

evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir

VISUALS = Path(__file__).resolve().parent.parent / "evals" / "visuals" / "scenarios"
FIXTURE_BASE = f"http://{FIXTURE_HOSTNAME}"
EXPECTED = {
    "chart-when-asked": "improve",
    "chart-fits-timeseries": "improve",
    "chart-fits-shares": "improve",
    "no-chart-unasked": "hold",
}


def records(run_dir: Path) -> list[dict]:
    return [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines() if x]


# ── the scenario key ──────────────────────────────────────────────────────


def test_rich_visuals_is_an_optional_boolean_agent_key(tmp_path):
    on = tmp_path / "on.toml"
    on.write_text(simple_scenario(agent="[agent]\nrich_visuals = false\n"))
    assert parse_scenario(on).rich_visuals is False
    bad = tmp_path / "bad.toml"
    bad.write_text(simple_scenario(agent='[agent]\nrich_visuals = "no"\n'))
    with pytest.raises(ScenarioError, match="rich_visuals"):
        parse_scenario(bad)
    absent = tmp_path / "absent.toml"
    absent.write_text(simple_scenario())
    assert parse_scenario(absent).rich_visuals is None  # omitted: the product default (on)


def _hook(messages):
    made = []

    def hook(spec, base):
        prov = scripted.ScriptedProvider(list(messages))
        made.append(prov)
        return prov

    hook.made = made
    return hook


def _system(hook) -> str:
    return hook.made[0].calls[0]["messages"][0].content


@pytest.mark.parametrize(
    ("agent", "has_section"),
    [
        ("", True),
        ("[agent]\nrich_visuals = true\n", True),
        ("[agent]\nrich_visuals = false\n", False),
    ],
)
async def test_the_harness_builds_the_agent_with_the_scenarios_switch(
    evals_isolation, agent, has_section
):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"vis": simple_scenario("vis", agent=agent)})
    hook = _hook([text("hello")])
    await run(tmp, sdir, hook)
    assert ("`chart`" in _system(hook)) is has_section


# ── the scenario set ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def loaded():
    return {s.id: s for s in load_scenarios(VISUALS, fixtures_root=VISUALS.parent / "fixtures")}


def test_four_scenarios_with_four_phrasings_and_five_facts(loaded):
    assert {k: v.klass for k, v in loaded.items()} == EXPECTED
    for sid, sc in loaded.items():
        assert sc.cell_classes() == {sid: EXPECTED[sid]}
        assert len(sc.phrasings) == 4 and len(sc.facts) == 5, sid
        convs = {
            tuple(tuple(c) for c in sc.instantiate(v, FIXTURE_BASE).conversations)
            for v in sc.variants()
        }
        assert len(convs) == 20, sid


def test_check_parameters(loaded):
    def decl(sid):
        sc = loaded[sid]
        (d,) = sc.instantiate(sc.variants()[0], FIXTURE_BASE).checks
        return d

    assert decl("chart-when-asked").name == "reply_has_valid_chart"
    assert "types" not in decl("chart-when-asked").params
    assert decl("chart-fits-timeseries").params == {"types": ["line", "area"]}
    assert decl("chart-fits-shares").params == {"types": ["pie", "bar"]}
    d = decl("no-chart-unasked")
    assert d.name == "reply_not_matches" and d.params["pattern"] == r"(?m)^```\s*chart\b"


def test_user_turns_never_name_the_tag_or_ask_for_json(loaded):
    import re

    banned = re.compile(r"```|\bjson\b|\btool\b|\bsystem prompt\b", re.IGNORECASE)
    for sc in loaded.values():
        for v in sc.variants():
            for conv in sc.instantiate(v, FIXTURE_BASE).conversations:
                for turn in conv:
                    assert not banned.search(turn), (sc.id, turn)


def test_the_files_hold_no_loopback_address():
    for path in VISUALS.glob("*.toml"):
        assert "127.0.0.1" not in path.read_text(), path.name


# ── the can-fail proof ────────────────────────────────────────────────────

BAR = '{"type": "bar", "x": {"values": ["a", "b"]}, "series": [{"values": [1, 2]}]}'
LINE = '{"type": "line", "x": {"values": [1, 2]}, "series": [{"values": [3, 4]}]}'
PIE = '{"type": "pie", "x": {"values": ["a", "b"]}, "series": [{"values": [1, 2]}]}'


def _fenced(body: str) -> str:
    return f"Here you go.\n```chart\n{body}\n```\n"


CASES = {
    "chart-when-asked": (
        _fenced(BAR),
        [("no chart", "Sure, in words.", True), ("invalid", _fenced('{"type": "bar"}'), True)],
    ),
    "chart-fits-timeseries": (
        _fenced(LINE),
        [("a pie", _fenced(PIE), True), ("no chart", "It rose.", True)],
    ),
    "chart-fits-shares": (
        _fenced(PIE),
        [("a line", _fenced(LINE), True), ("no chart", "Mostly bread.", True)],
    ),
    "no-chart-unasked": ("A short explanation.", [("charts anyway", _fenced(BAR), True)]),
}


async def _drive(tmp, sid, reply_for, n):
    def hook(spec, base):
        return scripted.ScriptedProvider([text(reply_for(spec.variant.phrasing_index))])

    return await run(tmp, VISUALS, hook, scenarios=[sid], n=n)


@pytest.mark.parametrize("sid", sorted(EXPECTED))
async def test_passing_reply_passes_and_each_violation_fails(evals_isolation, sid):
    ok, violations = CASES[sid]

    def reply_for(pi):
        return ok if pi == 0 else violations[pi - 1][1]

    _code, run_dir = await _drive(evals_isolation, sid, reply_for, 1 + len(violations))
    recs = {r["variant"]: r for r in records(run_dir)}
    assert recs["f0p0"]["outcome"] == "pass", recs["f0p0"]["checks"]
    for pi, (label, _reply, _x) in enumerate(violations, start=1):
        rec = recs[f"f0p{pi}"]
        assert rec["outcome"] == "fail", (label, rec["outcome"], rec["reason"])
        assert [c["passed"] for c in rec["checks"]] == [False], (label, rec["checks"])
