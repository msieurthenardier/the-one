"""Platform-text parts, the three real configurations, cold counts (DD12). Offline.

Listed in ``tests/conftest.py::_EMBEDDING_REAL_LOAD_MODULES``: the all-on
configuration indexes a knowledge base with the bundled model. The counter is the
deterministic stand-in; tiktoken is never imported here.
"""

from __future__ import annotations

import json
import sys

import _evals_helpers as h
import httpx
import pytest

from evals import tokens
from evals.tokens import StandInCounter, extract_parts

evals_isolation = h.evals_isolation
C = StandInCounter()


def names(parts):
    return [p.name for p in parts]


def test_standin_counter_is_deterministic():
    assert C.count("") == 0
    assert C.count("abcd") == 1 and C.count("abcde") == 2
    assert C.count("é") == C.count("é")


def test_schema_text_is_deterministic_and_covers_name_description_parameters():
    a = {"name": "t", "description": "d", "parameters": {"b": 1, "a": {"y": 2, "x": 3}}}
    b = {"name": "t", "description": "d", "parameters": {"a": {"x": 3, "y": 2}, "b": 1}}
    assert tokens.schema_text(a) == tokens.schema_text(b)
    assert tokens.schema_text(a).startswith("t\nd\n")
    wrapped = {"type": "function", "function": a}
    assert tokens.schema_text(wrapped) == tokens.schema_text(a)


def test_extract_parts_pure_attribution_and_other():
    from the_one.agent.config import BASE_PROMPT, compose_system_prompt
    from the_one.db._rules import RULES_HEADING

    date = "Today is Monday."
    system = (
        compose_system_prompt(BASE_PROMPT, "", rules=["RULE-A"], notes=None, date_line=date)
        + "\n\n---\n\nA stray layer."
    )
    schemas = [{"name": "x", "description": "d", "parameters": {}}]
    parts = extract_parts(system, schemas, C, rule_texts=["RULE-A"], date_lines=[date])
    assert names(parts) == ["base_prompt", "rules_layer", "date_line", "other", "tool:x"]
    by = {p.name: p for p in parts}
    assert by["base_prompt"].tokens == C.count(BASE_PROMPT)
    # the rules layer is counted without the rule's own text
    layer = system.split("\n\n---\n\n")[1]
    assert layer.startswith(RULES_HEADING)
    assert by["rules_layer"].tokens == C.count(layer.replace("RULE-A", ""))
    assert by["other"].tokens == C.count("A stray layer.")
    assert tokens.totals(parts)["platform"] == sum(p.tokens for p in parts)


def test_extract_parts_persona_is_operator_text_and_unknown_prefix_is_other():
    from the_one.agent.config import BASE_PROMPT, compose_system_prompt

    system = compose_system_prompt(BASE_PROMPT, "I am Penny.", rules=[], notes=None)
    parts = extract_parts(system, [], C, persona="I am Penny.")
    assert names(parts) == ["base_prompt"]
    parts = extract_parts("something else entirely", [], C)
    assert names(parts) == ["other"]


async def build(tmp, run="m"):
    opts = tokens.MeasureOptions(counter=C, run_dir=tmp / run)
    return await tokens.measure_prompt(opts)


async def test_three_configurations_parts_sum_and_attribution(evals_isolation):
    doc = await build(evals_isolation)
    cfgs = doc["configs"]
    assert set(cfgs) == {"bare", "all-on", "tool-free"}
    for name, cfg in cfgs.items():
        parts = cfg["parts"]
        assert "other" not in [p["name"] for p in parts], name  # everything is attributed
        t = cfg["totals"]
        assert t["platform"] == sum(p["tokens"] for p in parts)
        assert t["prompt_sections"] == sum(p["tokens"] for p in parts if p["group"] == "prompt")
        assert t["tools"] == sum(p["tokens"] for p in parts if p["group"] == "tools")

    bare = [p["name"] for p in cfgs["bare"]["parts"]]
    assert bare[:2] == ["base_prompt", "date_line"]
    assert {"tool:search_tools", "tool:continue", "tool:current_time"} <= set(bare)
    assert "rules_layer" not in bare and "notes_layer" not in bare

    allon = [p["name"] for p in cfgs["all-on"]["parts"]]
    assert allon[:4] == ["base_prompt", "rules_layer", "notes_layer", "date_line"]
    assert {"tool:save_note", "tool:update_note", "tool:forget_note"} <= set(allon)
    # the KB search tool is not in the starting set, but is measured on its own
    assert not [n for n in allon if n.startswith("tool:kb__")]
    assert doc["kb_tool"]["name"].startswith("kb__") and doc["kb_tool"]["tokens"] > 0

    free = cfgs["tool-free"]
    assert [p["name"] for p in free["parts"]] == ["chat_only_prompt", "date_line"]
    assert free["totals"]["tools"] == 0
    # tool-free is far smaller than bare (the degraded prompt, no catalog)
    assert free["totals"]["platform"] < cfgs["bare"]["totals"]["prompt_sections"]


def test_note_and_rule_texts_do_not_change_their_layers_count():
    from the_one.agent.config import BASE_PROMPT, RenderedNote, compose_system_prompt

    def parts_for(rule: str, note: str):
        system = compose_system_prompt(
            BASE_PROMPT, "", rules=[rule], notes=[RenderedNote(1, note)], date_line="D"
        )
        return {
            p.name: p.tokens
            for p in extract_parts(
                system, [], C, rule_texts=[rule], note_texts=[note], date_lines=["D"]
            )
        }

    short = parts_for("r", "n")
    long = parts_for("a much longer rule text " * 5, "a much longer note text " * 9)
    assert short["rules_layer"] == long["rules_layer"]
    assert short["notes_layer"] == long["notes_layer"]


async def test_measure_is_deterministic_and_leaves_nothing_behind(evals_isolation):
    tmp = evals_isolation
    a = await build(tmp, "m1")
    b = await build(tmp, "m2")
    assert a == b
    assert not (tmp / "m1").exists() and not (tmp / "m2").exists()


async def test_json_out_is_written(evals_isolation):
    tmp = evals_isolation
    out = tmp / "out" / "measure.json"
    opts = tokens.MeasureOptions(counter=C, run_dir=tmp / "m", json_out=out)
    doc = await tokens.measure_prompt(opts)
    assert json.loads(out.read_text()) == doc


def test_missing_tiktoken_gives_a_one_line_hint(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # import raises ImportError
    with pytest.raises(tokens.TiktokenMissingError) as exc:
        tokens.TiktokenCounter(tmp_path / "cache")
    assert "\n" not in str(exc.value) and ".[evals]" in str(exc.value)


def test_tiktoken_cache_dir_is_set_before_use(monkeypatch, tmp_path):
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)

    class FakeEnc:
        def encode(self, text, disallowed_special=()):
            return list(text)

    class FakeTik:
        @staticmethod
        def get_encoding(name):
            import os

            assert os.environ["TIKTOKEN_CACHE_DIR"] == str(tmp_path / "c")  # already set
            assert name == "o200k_base"
            return FakeEnc()

    monkeypatch.setitem(sys.modules, "tiktoken", FakeTik)
    counter = tokens.TiktokenCounter(tmp_path / "c")
    assert counter.count("abc") == 3 and counter.name == "tiktoken:o200k_base"


async def test_ollama_unload_polls_until_gone():
    seen = []
    loaded = [True, True, False]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/generate":
            assert json.loads(request.content) == {"model": "m", "keep_alive": 0}
            return httpx.Response(200, json={})
        models = [{"name": "m"}] if loaded.pop(0) else []
        return httpx.Response(200, json={"models": models})

    sleeps = []

    async def sleep(s):
        sleeps.append(s)

    await tokens.ollama_unload(
        "http://x:1", "m", transport=httpx.MockTransport(handler), sleep=sleep
    )
    assert seen[0] == ("POST", "/api/generate")
    assert [p for _m, p in seen[1:]] == ["/api/ps"] * 3
    assert len(sleeps) == 2


async def test_ollama_unload_times_out():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"models": [{"name": "m"}]})

    t = [0.0]

    def clock():
        t[0] += 30.0
        return t[0]

    async def sleep(_s):
        return None

    with pytest.raises(RuntimeError, match="still loaded"):
        await tokens.ollama_unload(
            "http://x:1", "m", transport=httpx.MockTransport(handler), sleep=sleep, clock=clock
        )


async def test_model_counts_unload_before_each_ollama_measurement(evals_isolation):
    """Fakes only: a scripted provider stands in for the model; the unload hook is recorded."""
    from evals import scripted

    unloads, infos = [], []

    async def unload(preset):
        unloads.append(preset.name)

    async def info(preset):
        infos.append(preset.name)
        return {"server_version": "0.0-test"}

    opts = tokens.MeasureOptions(
        counter=C,
        run_dir=evals_isolation / "m",
        with_model_counts=True,
        models=["gpt-oss"],
        unload=unload,
        server_info=info,
        model_hook=lambda spec, base: scripted.ScriptedProvider(
            [scripted.text("ok", input_tokens=1234)]
        ),
    )
    doc = await tokens.measure_prompt(opts)
    entry = doc["model_counts"]["gpt-oss"]
    assert entry["input_tokens"] == {"bare": 1234, "all-on": 1234, "tool-free": 1234}
    assert entry["server"] == {"server_version": "0.0-test"}
    assert unloads == ["gpt-oss"] * 3 and infos == ["gpt-oss"]


def test_render_tables_lists_totals_and_fingerprint():
    doc = {
        "counter": "standin",
        "configs": {
            "bare": {
                "parts": [{"name": "base_prompt", "group": "prompt", "tokens": 5, "chars": 20}],
                "totals": {"prompt_sections": 5, "tools": 0, "platform": 5},
            }
        },
        "kb_tool": None,
        "fingerprints": {"prompt": "abc"},
        "model_counts": {
            "m": {"input_tokens": {"bare": 7, "all-on": 9, "tool-free": 3}, "server": {}}
        },
    }
    out = tokens.render_tables(doc)
    assert "base_prompt" in out and "platform text total" in out and "abc" in out
    assert "m: bare=7, all-on=9, tool-free=3" in out
