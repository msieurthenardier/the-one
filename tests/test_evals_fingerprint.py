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
