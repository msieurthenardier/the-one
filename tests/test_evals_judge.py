"""The wording judge (DD14): parsing, the labelled-set gate and run exclusion. Offline."""

from __future__ import annotations

import json
from pathlib import Path

import _evals_helpers as h
import pytest
from _evals_helpers import run

from evals import judge as judge_mod
from evals import scripted
from evals.scripted import call, text

evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir
SCENARIOS = Path(__file__).resolve().parent.parent / "evals" / "scenarios"


def truth_client(note_reply=None):
    truth = {i["text"]: i["label"] == "as-told" for i in judge_mod.load_labelled()}

    class C:
        def ask(self, rubric, note_text):
            if note_text in truth:
                return json.dumps({"pass": truth[note_text], "reason": "r"})
            return note_reply if note_reply is not None else '{"pass": true, "reason": "r"}'

    return C()


def test_labelled_set_shape_is_frozen_contract():
    items = judge_mod.load_labelled()
    assert len(items) == 32
    assert sum(i["label"] == "as-told" for i in items) == 16
    assert sum(i["label"] == "fact" for i in items) == 16
    assert len({i["id"] for i in items}) == len(items)
    assert {i["label"] for i in items} == {"as-told", "fact"}


def test_rubric_exists_and_asks_for_json():
    rubric = judge_mod.load_rubrics()["as-told"]
    assert '"pass"' in rubric and "JSON" in rubric


@pytest.mark.parametrize(
    "reply,expected",
    [
        ('{"pass": true, "reason": "ok"}', (True, "ok")),
        ('Sure!\n```json\n{"pass": false, "reason": "flat"}\n```', (False, "flat")),
        ('{"pass": true}', (True, "")),
    ],
)
def test_parse_verdict_accepts(reply, expected):
    assert judge_mod.parse_verdict(reply) == expected


@pytest.mark.parametrize(
    "reply", ["", "pass", "{not json}", '{"pass": "yes"}', '{"reason": "x"}', "[true]"]
)
def test_parse_verdict_rejects_malformed(reply):
    with pytest.raises(judge_mod.JudgeError):
        judge_mod.parse_verdict(reply)


def test_agreement_perfect_and_inverted_and_malformed():
    ag = judge_mod.score_labelled(truth_client())
    assert (ag.total, ag.agreed, ag.misses) == (32, 32, [])

    class Inverted:
        def ask(self, rubric, note_text):
            truth = {i["text"]: i["label"] == "as-told" for i in judge_mod.load_labelled()}
            return json.dumps({"pass": not truth[note_text], "reason": "r"})

    bad = judge_mod.score_labelled(Inverted())
    assert bad.agreed == 0 and len(bad.misses) == 32

    class Garbage:
        def ask(self, rubric, note_text):
            return "no idea"

    g = judge_mod.score_labelled(Garbage())
    assert g.errors == 32 and g.agreed == 0


def test_validate_gate_threshold_is_ninety_percent():
    ag, ok = judge_mod.validate(truth_client())
    assert ok and ag.rate == 1.0

    class TwoWrong:
        n = 0

        def ask(self, rubric, note_text):
            truth = {i["text"]: i["label"] == "as-told" for i in judge_mod.load_labelled()}
            self.n += 1
            return json.dumps({"pass": truth[note_text] if self.n > 4 else not truth[note_text]})

    _ag, ok2 = judge_mod.validate(TwoWrong())  # 4 wrong of 32 = 87.5%
    assert not ok2


def _hook():
    return lambda spec, base: scripted.ScriptedProvider(
        [call("save_note", {"text": "The user says: I plan to go."}, call_id="n1"), text("ok")]
    )


async def _go(tmp, client):
    return await run(
        tmp,
        SCENARIOS,
        _hook(),
        scenarios=["notes-as-told"],
        scenarios_dir=SCENARIOS,
        n=1,
        token_file=h.token_file(tmp),
        hook_kw={"judge_client": client},
    )


async def test_validated_judge_scores_and_records_agreement(evals_isolation):
    code, run_dir = await _go(evals_isolation, truth_client())
    (rec,) = [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines()]
    assert rec["outcome"] == "pass"
    data = json.loads((run_dir / "judge.json").read_text())
    assert data["validated"] and data["agreed"] == 32 and data["misses"] == []


async def test_unvalidated_judge_excludes_judge_scored_runs(evals_isolation):
    class AlwaysPass:
        def ask(self, rubric, note_text):
            return '{"pass": true, "reason": "r"}'

    code, run_dir = await _go(evals_isolation, AlwaysPass())
    (rec,) = [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines()]
    assert rec["outcome"] == "error" and not rec["counted"]
    assert "judge-unvalidated" in rec["reason"]
    assert json.loads((run_dir / "judge.json").read_text())["validated"] is False


async def test_malformed_judge_reply_on_a_run_is_an_excluded_error(evals_isolation):
    code, run_dir = await _go(evals_isolation, truth_client(note_reply="I think it is fine"))
    (rec,) = [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines()]
    assert rec["outcome"] == "error" and not rec["counted"]
    assert "no JSON" in rec["reason"]


async def test_no_judge_scenario_means_no_labelled_scoring(evals_isolation):
    class Boom:
        def ask(self, rubric, note_text):
            raise AssertionError("must not be called")

    code, run_dir = await run(
        evals_isolation,
        SCENARIOS,
        lambda spec, base: scripted.ScriptedProvider([text("Today is Tuesday.")]),
        scenarios=["date-awareness"],
        scenarios_dir=SCENARIOS,
        n=1,
        hook_kw={"judge_client": Boom()},
    )
    assert not (run_dir / "judge.json").exists()
