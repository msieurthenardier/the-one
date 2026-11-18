"""Fingerprints (DD15): stable, and sensitive to exactly the right changes."""

from __future__ import annotations

import copy
import shutil

import _evals_helpers as h
import pytest

from evals import fingerprint as fp
from evals import tokens
from evals.tokens import RawConfig

evals_isolation = h.evals_isolation


def raw(desc="Do a thing.", kb_desc="Search the KB."):
    def cfg(name):
        return RawConfig(
            name=name,
            system="BASE",
            schemas=[{"name": "a", "description": desc, "parameters": {"type": "object"}}],
            kb_schema=(
                {"name": "kb__x__search", "description": kb_desc, "parameters": {}}
                if name.startswith("all-on")
                else None
            ),
            persona="",
            rule_texts=[],
            note_texts=[],
            date_lines=[],
        )

    return {n: cfg(n) for n in tokens.ALL_CONFIGS}


def test_prompt_fingerprint_stable_and_sensitive():
    base = fp.prompt_fingerprint(raw())
    assert fp.prompt_fingerprint(raw()) == base
    assert fp.prompt_fingerprint(raw(desc="Do a thing!")) != base  # one word of a tool description
    assert fp.prompt_fingerprint(raw(kb_desc="Search the knowledge base.")) != base
    changed = raw()
    changed["tool-free"].system = "CHAT"
    assert fp.prompt_fingerprint(changed) != base
    # DD13: the connector-mapped variants are part of the fingerprint
    for variant in ("bare-connector", "all-on-connector"):
        changed = raw()
        changed[variant].schemas = []
        assert fp.prompt_fingerprint(changed) != base, variant
    assert set(raw()) >= {"bare-connector", "all-on-connector"}


def test_scenarios_fingerprint_follows_files(tmp_path):
    sdir = tmp_path / "scenarios"
    fx = tmp_path / "fixtures"
    judge = tmp_path / "judge"
    sdir.mkdir()
    (fx / "web").mkdir(parents=True)
    judge.mkdir()
    (sdir / "a.toml").write_text('id = "a"\n')
    (fx / "web" / "p.html").write_text("<p>x</p>")
    (judge / "rubrics.toml").write_text("r = 1\n")
    base = fp.scenarios_fingerprint(sdir, fx, judge)
    assert fp.scenarios_fingerprint(sdir, fx, judge) == base
    (sdir / "a.toml").write_text('id = "a"\n# edit\n')
    edited = fp.scenarios_fingerprint(sdir, fx, judge)
    assert edited != base
    (fx / "web" / "p.html").write_text("<p>y</p>")
    assert fp.scenarios_fingerprint(sdir, fx, judge) != edited
    third = fp.scenarios_fingerprint(sdir, fx, judge)
    (judge / "rubrics.toml").write_text("r = 2\n")
    assert fp.scenarios_fingerprint(sdir, fx, judge) != third
    shutil.rmtree(judge)
    assert fp.scenarios_fingerprint(sdir, fx, judge) != third  # a missing judge dir is a change


def test_models_fingerprint_covers_presets_effective_and_digest():
    presets = {"m": {"type": "ollama", "model": "x"}}
    eff = {"m": {"temperature": 0.0}}
    info = {"m": {"model_digest": "d1"}}
    base = fp.models_fingerprint(presets, eff, info)
    assert fp.models_fingerprint(copy.deepcopy(presets), eff, info) == base
    assert fp.models_fingerprint(presets, {"m": {"temperature": 0.7}}, info) != base
    assert fp.models_fingerprint(presets, eff, {"m": {"model_digest": "d2"}}) != base
    assert fp.models_fingerprint({"m": {"type": "ollama", "model": "y"}}, eff, info) != base


@pytest.mark.parametrize("change", ["none", "tool-description", "kb-description"])
async def test_measured_prompt_fingerprint_is_stable_and_follows_tool_text(
    evals_isolation, monkeypatch, change
):
    """The real three configurations, built twice: same hash; edit a description: new hash."""
    tmp = evals_isolation

    async def once(run):
        opts = tokens.MeasureOptions(counter=tokens.StandInCounter(), run_dir=tmp / run)
        return (await tokens.measure_prompt(opts))["fingerprints"]["prompt"]

    a = await once("m1")
    assert await once("m2") == a
    if change == "tool-description":
        from the_one.tools.time_tool import CurrentTimeTool

        monkeypatch.setattr(CurrentTimeTool, "description", "A changed description.")
    elif change == "kb-description":
        from the_one.knowledge import tool_provider

        monkeypatch.setattr(tool_provider, "build_description", lambda kb: "A changed KB tool.")
    if change != "none":
        assert await once("m3") != a


# ── Mission 36 F1 L09: the GleepGlorp set did not move the other sets' fingerprints ──

# Recorded before the GleepGlorp builder, measure directory and checks landed (the default
# measure-prompt document was also byte-identical before and after). A DELIBERATE platform prompt
# or scenario change moves these: re-record them together with the notes-* baselines.
DEFAULT_MEASURE_PROMPT_FINGERPRINT = (
    "1d02c15609fc99f0a4361aaff7cf46930852a5339e2e0c518f5661b42fe91a15"
)
OTHER_SETS_SCENARIO_FINGERPRINTS = {
    "scenarios": "fc6050eb85e8d443f0e6e3ea19c5fe666917fec9641aaa68fe3ef9926e8d1595",
    "routines/scenarios": "052f3a1e4366fdda1d5a9760abff9dd65952ddcabd39b97425ebdac673f97eed",
    "visuals/scenarios": "56204ab0016d40d8eda52f499cddabba704009c8bcc6543d9644212a8f8b0220",
    "widgets/scenarios": "7967952008c991095403dc4887271214e885454d792c9aaca7116fe388ed5f53",
}


async def test_default_measure_fingerprint_is_the_pre_gleepglorp_value(evals_isolation):
    """``evals/measure`` (the platform, routines, visuals and widgets sets' prompt) measures to
    the same prompt fingerprint it did before the GleepGlorp builder, so the ``notes-*`` baselines
    stay valid and ``compare --same-prompt`` keeps working for them."""
    opts = tokens.MeasureOptions(counter=tokens.StandInCounter(), run_dir=evals_isolation / "m")
    doc = await tokens.measure_prompt(opts)
    assert doc["fingerprints"]["prompt"] == DEFAULT_MEASURE_PROMPT_FINGERPRINT
    assert sorted(doc["configs"]) == sorted(
        [*tokens.CONFIGS, *tokens.CONNECTOR_VARIANTS, "routines-on"]
    )


def test_the_other_sets_scenario_fingerprints_are_unchanged():
    from pathlib import Path

    evals_dir = Path(fp.__file__).resolve().parent
    for rel, want in OTHER_SETS_SCENARIO_FINGERPRINTS.items():
        assert fp.scenarios_fingerprint((evals_dir / rel).resolve()) == want, rel
