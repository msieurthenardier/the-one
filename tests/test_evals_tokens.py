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
from tests._platform_prompt_pins import PLATFORM_TOOL_FREE_PIN as PLATFORM_TOOL_FREE
from tests._platform_prompt_pins import PLATFORM_TOOLS_ALL_ON_PIN as PLATFORM_TOOLS
from the_one.agent.platform_prompt import Capabilities, sections_for

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


def test_separator_matches_the_products_layer_separator():
    from the_one.agent.config import compose_system_prompt

    assert compose_system_prompt("A", "B") == f"A{tokens.SEPARATOR}B"
    assert compose_system_prompt("A", "", date_line="D") == f"A{tokens.SEPARATOR}D"


def compose(persona="", rules=(), notes=None, date="Today is Monday."):
    from the_one.agent.config import compose_system_prompt

    return compose_system_prompt(
        PLATFORM_TOOLS, persona, rules=list(rules), notes=notes, date_line=date
    )


def test_extract_parts_bare_all_on_tool_free_and_persona_attribution():
    from the_one.agent.config import RenderedNote

    schemas = [{"name": "x", "description": "d", "parameters": {}}]
    # bare: platform, date
    parts = extract_parts(compose(), schemas, C, date_lines=["Today is Monday."])
    assert names(parts) == ["platform", "date_line", "tool:x"]
    assert parts[0].tokens == C.count(PLATFORM_TOOLS)
    # all-on: rules and notes layers, operator texts subtracted
    sys_all = compose(rules=["RULE-A"], notes=[RenderedNote(1, "NOTE-A")])
    parts = extract_parts(
        sys_all,
        [],
        C,
        rule_texts=["RULE-A"],
        note_texts=["NOTE-A"],
        date_lines=["Today is Monday."],
    )
    assert names(parts) == ["platform", "rules_layer", "notes_layer", "date_line"]
    layers = sys_all.split(tokens.SEPARATOR)
    by = {p.name: p for p in parts}
    assert by["rules_layer"].tokens == C.count(layers[1].replace("RULE-A", ""))
    assert by["notes_layer"].tokens == C.count(layers[2].replace("NOTE-A", ""))
    # tool-free: the chat-only prompt is just another platform text
    from the_one.agent.config import compose_system_prompt

    free = compose_system_prompt(PLATFORM_TOOL_FREE, "", date_line="Today is Monday.")
    parts = extract_parts(free, [], C, date_lines=["Today is Monday."])
    assert names(parts) == ["platform", "date_line"]
    assert parts[0].tokens == C.count(PLATFORM_TOOL_FREE)
    # persona: operator text, not counted
    parts = extract_parts(
        compose(persona="I am Penny."),
        [],
        C,
        persona="I am Penny.",
        date_lines=["Today is Monday."],
    )
    assert names(parts) == ["platform", "date_line"]
    assert all("unattributed" != n for n in names(parts))


def test_a_persona_containing_the_separator_does_not_confuse_the_split():
    persona = f"First half.{tokens.SEPARATOR}Second half."
    system = compose(persona=persona, rules=["RULE-A"])
    parts = extract_parts(
        system,
        [],
        C,
        persona=persona,
        rule_texts=["RULE-A"],
        date_lines=["Today is Monday."],
    )
    assert names(parts) == ["platform", "rules_layer", "date_line"]


def test_a_notes_layer_with_no_notes_counts_as_platform_text():
    system = compose(notes=[])
    assert "No saved notes yet." in system
    parts = extract_parts(system, [], C, notes_present=True, date_lines=["Today is Monday."])
    assert names(parts) == ["platform", "notes_layer", "date_line"]
    notes = next(p for p in parts if p.name == "notes_layer")
    assert notes.tokens == C.count(system.split(tokens.SEPARATOR)[1])


def test_extra_layers_become_unattributed_and_the_section_hook_replaces_the_platform_part():
    system = compose() + tokens.SEPARATOR + "A stray layer."
    parts = extract_parts(system, [], C, date_lines=["Today is Monday."])
    assert names(parts) == ["platform", "date_line", "unattributed"]
    assert parts[-1].tokens == C.count("A stray layer.")
    split = extract_parts(
        compose(),
        [],
        C,
        date_lines=["Today is Monday."],
        platform_sections=lambda text: [("one", text[:10]), ("two", text[10:])],
    )
    assert names(split) == ["one", "two", "date_line"]
    assert extract_parts("something else entirely", [], C)[0].name == "platform"


async def build(tmp, run="m"):
    opts = tokens.MeasureOptions(counter=C, run_dir=tmp / run)
    return await tokens.measure_prompt(opts)


async def test_three_configurations_parts_sum_and_attribution(evals_isolation):
    doc = await build(evals_isolation)
    cfgs = doc["configs"]
    assert set(cfgs) == set(tokens.ALL_CONFIGS)
    for name, cfg in cfgs.items():
        parts = cfg["parts"]
        assert "unattributed" not in [p["name"] for p in parts], name  # everything is attributed
        t = cfg["totals"]
        assert t["platform"] == sum(p["tokens"] for p in parts)
        assert t["prompt_sections"] == sum(p["tokens"] for p in parts if p["group"] == "prompt")
        assert t["tools"] == sum(p["tokens"] for p in parts if p["group"] == "tools")

    bare = [p["name"] for p in cfgs["bare"]["parts"]]
    # The measured agents carry no execution tools; only all-on has a knowledge base.
    sec_ids = [sid for sid, _ in sections_for(Capabilities(knowledge=False, exec_tools=False))]
    assert "execution" not in sec_ids
    assert bare[: len(sec_ids)] == sec_ids and bare[len(sec_ids)] == "date_line"
    assert {"tool:search_tools", "tool:continue", "tool:current_time"} <= set(bare)
    assert "rules_layer" not in bare and "notes_layer" not in bare

    allon = [p["name"] for p in cfgs["all-on"]["parts"]]
    assert allon[len(sec_ids) : len(sec_ids) + 3] == ["rules_layer", "notes_layer", "date_line"]
    assert {"tool:save_note", "tool:update_note", "tool:forget_note"} <= set(allon)
    # the KB search tool is measured on its own; its label follows the configuration: the
    # measured all-on agent is exposed (sortie 11), so the tool is in its starting set
    in_set = [n for n in allon if n.startswith("tool:kb__")]
    assert doc["kb_tool"]["name"].startswith("kb__") and doc["kb_tool"]["tokens"] > 0
    assert doc["kb_tool"]["in_starting_set"] is bool(in_set) is True
    assert "(in the starting set)" in tokens.render_tables(doc)

    free = cfgs["tool-free"]
    free_ids = [sid for sid, _ in sections_for(Capabilities(tools=False))]
    assert [p["name"] for p in free["parts"]] == [*free_ids, "date_line"]
    assert free["totals"]["tools"] == 0
    # tool-free is far smaller than bare (the degraded prompt, no catalog)
    assert free["totals"]["platform"] < cfgs["bare"]["totals"]["prompt_sections"]


def test_note_and_rule_texts_do_not_change_their_layers_count():
    from the_one.agent.config import RenderedNote, compose_system_prompt

    def parts_for(rule: str, note: str):
        system = compose_system_prompt(
            PLATFORM_TOOLS, "", rules=[rule], notes=[RenderedNote(1, note)], date_line="D"
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
    assert entry["input_tokens"] == {
        "bare": 1234,
        "all-on": 1234,
        "tool-free": 1234,
        "routines-on": 1234,  # M33 F2 L4
    }
    assert entry["server"] == {"server_version": "0.0-test"}
    assert unloads == ["gpt-oss"] * 4 and infos == ["gpt-oss"]


async def test_model_counts_with_no_models_selects_the_default_presets(evals_isolation):
    """``measure-prompt --with-model-counts`` with no ``--models`` takes the default presets."""
    from evals import scripted

    async def unload(preset):
        return None

    async def info(preset):
        return {}

    opts = tokens.MeasureOptions(
        counter=C,
        run_dir=evals_isolation / "m",
        with_model_counts=True,
        models=None,
        token_file=h.token_file(evals_isolation),
        unload=unload,
        server_info=info,
        model_hook=lambda spec, base: scripted.ScriptedProvider([scripted.text("ok")]),
    )
    doc = await tokens.measure_prompt(opts)
    assert list(doc["model_counts"]) == ["haiku", "qwen3-4b", "lfm3"]  # not gpt-oss


# ── sortie 11 leg 1: tools_full, prompt_text, exposure, the pinned window (DD8, DD1) ──


def test_tool_exposure_record_contract():
    import ast
    import dataclasses
    from pathlib import Path

    from the_one.agent.tool_exposure import ToolExposure

    assert [f.name for f in dataclasses.fields(ToolExposure)] == [
        "decided",
        "budget",
        "estimate",
        "window_known",
        "window",
    ]
    e = ToolExposure(decided=True, budget=None, estimate=7, window_known=False, window=None)
    assert e.to_dict() == {
        "decided": True,
        "budget": None,
        "estimate": 7,
        "window_known": False,
        "window": None,
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.decided = False  # type: ignore[misc]
    root = Path(__file__).resolve().parent.parent / "the_one"
    tree = ast.parse((root / "agent" / "tool_exposure.py").read_text())
    for node in ast.walk(tree):  # a leaf: nothing from the_one, only the standard library
        if isinstance(node, ast.ImportFrom):
            assert node.module in ("__future__", "dataclasses", "typing"), node.module
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith("the_one") for a in node.names)
    users = sorted(
        p.name
        for p in root.rglob("*.py")
        if p.name != "tool_exposure.py" and "tool_exposure" in p.read_text()
    )
    assert users == ["factory.py", "pending.py"]  # the decision and the settle re-render


def _raw(**kw):
    base = dict(
        name="c",
        system="",
        schemas=[],
        kb_schema=None,
        persona="",
        rule_texts=[],
        note_texts=[],
        date_lines=[],
    )
    return tokens.RawConfig(**{**base, **kw})


def _s(name, size=1):
    return {"name": name, "description": "d" * size, "parameters": {}}


def test_tools_full_is_the_starting_set_plus_the_rest_of_the_registry_in_order():
    rc = _raw(
        schemas=[_s("search_tools"), _s("continue"), _s("fetch_url")],
        registry_schemas=[
            _s("search_tools"),
            _s("save_note"),
            _s("continue"),
            _s("send_to_platform_channel"),
            _s("find_platform_destination"),
            _s("fetch_channel_history"),
            _s("fetch_url"),
            _s("kb__x__search"),
        ],
    )
    names = [tokens.schema_name(s) for s in tokens.tools_full_schemas(rc)]
    # starting names first, then registry extras in registry order; connector tools left out
    assert names == ["search_tools", "continue", "fetch_url", "save_note", "kb__x__search"]
    bound = _raw(**{**rc.__dict__, "connector_bound": True})
    assert [tokens.schema_name(s) for s in tokens.tools_full_schemas(bound)] == [
        "search_tools",
        "continue",
        "fetch_url",
        "save_note",
        "send_to_platform_channel",
        "find_platform_destination",
        "fetch_channel_history",
        "kb__x__search",
    ]
    assert tokens.EXPOSURE_CONNECTOR_TOOLS == (
        "send_to_platform_channel",
        "find_platform_destination",
        "fetch_channel_history",
    )
    # ``search_tools`` is never ADDED from the registry (an exposed starting set may lack it)
    exposed = _raw(
        schemas=[_s("fetch_url")], registry_schemas=[_s("search_tools"), _s("fetch_url")]
    )
    assert [tokens.schema_name(s) for s in tokens.tools_full_schemas(exposed)] == ["fetch_url"]
    # a tools_off scenario still has a built registry, but its set is empty
    off = _raw(**{**rc.__dict__, "tools_off": True})
    assert tokens.tools_full_schemas(off) == []


async def test_measurement_is_schema_two_and_every_configuration_carries_the_new_keys(
    evals_isolation,
):
    doc = await build(evals_isolation)
    assert doc["schema"] == 2
    for name, cfg in doc["configs"].items():
        t = cfg["totals"]
        assert {"prompt_sections", "tools", "platform"} <= set(t)  # existing keys keep meaning
        assert t["prompt_text"] == t["platform"] - t["tools"], name
        assert isinstance(t["tools_full"], int) and "tools_full_names" in cfg, name
        assert "exposure" in cfg, name
        assert cfg["exposure"] is not None, name  # the factory records a decision on every agent
        if name != "tool-free":
            assert cfg["exposure"]["decided"] is True, name
        starting = [p["name"][5:] for p in cfg["parts"] if p["group"] == "tools"]
        if name == "tool-free":
            assert t["tools_full"] == 0 and cfg["tools_full_names"] == []
        else:
            assert cfg["tools_full_names"][: len(starting)] == starting, name
            assert t["tools_full"] >= t["tools"], name
    connector = set(tokens.EXPOSURE_CONNECTOR_TOOLS)
    assert not connector & set(doc["configs"]["bare"]["tools_full_names"])
    assert not connector & set(doc["configs"]["all-on"]["tools_full_names"])
    for name in ("bare-connector", "all-on-connector"):
        assert connector <= set(doc["configs"][name]["tools_full_names"]), name
    # all-on's registry holds its knowledge-base search tool; the agent is exposed, so it is in
    # the starting set and the would-be set equals the actual one
    allon = doc["configs"]["all-on"]
    assert any(n.startswith("kb__") for n in allon["tools_full_names"])
    assert allon["totals"]["tools_full"] == allon["totals"]["tools"]
    # the fingerprint hashes only the rendered prompt, schemas and kb tool: unchanged by these keys
    assert doc["fingerprints"]["prompt"]


async def test_exposure_parity_starting_schemas_equal_the_would_be_full_set(evals_isolation):
    """DD8: for every decided configuration (tool-free is exempt: its model gets no tools),
    the schemas the agent starts with are exactly the would-be full set."""
    doc = await build(evals_isolation)
    assert doc["configs"]["all-on"]["exposure"]["decided"] is True  # at the pinned 16384 window
    checked = 0
    for name, cfg in doc["configs"].items():
        if name == "tool-free" or not cfg["exposure"]["decided"]:
            continue
        starting = [p["name"][5:] for p in cfg["parts"] if p["group"] == "tools"]
        assert starting == cfg["tools_full_names"], name
        assert cfg["totals"]["tools"] == cfg["totals"]["tools_full"], name
        checked += 1
    assert checked == len(doc["configs"]) - 1


async def test_the_eval_agents_are_exposed_at_16384_and_all_on_is_not_at_4096_or_8192(
    evals_isolation, monkeypatch
):
    """AC12b: the budget measured offline with the real tool classes, at the defaults."""
    doc = await build(evals_isolation)
    for name in ("all-on", "all-on-connector", "routines-on"):
        e = doc["configs"][name]["exposure"]
        assert e["decided"] is True, name
        assert e["window"] == 16384 and e["budget"] == 4096, name
        assert e["estimate"] <= e["budget"], name
    for window in (4096, 8192):
        monkeypatch.setattr(tokens, "MEASURE_WINDOW", window)
        small = await build(evals_isolation, run=f"w{window}")
        e = small["configs"]["all-on"]["exposure"]
        assert e["decided"] is False and e["budget"] == window // 4, window
        assert e["estimate"] > e["budget"], window
        # not exposed: the starting set is today's discovery set, smaller than the full set
        t = small["configs"]["all-on"]["totals"]
        assert t["tools"] < t["tools_full"], window


def test_measure_window_is_the_smallest_default_ollama_num_ctx_and_the_provider_density():
    from evals.models import load_presets, select_presets
    from the_one.llm.ollama_provider import OllamaProvider

    ollama = [p for p in select_presets(load_presets(), None) if p.type == "ollama"]
    assert ollama, "the default presets include local models"
    assert tokens.MEASURE_WINDOW == min(p.config["num_ctx"] for p in ollama)
    assert tokens.MEASURE_BYTES_PER_TOKEN == OllamaProvider.bytes_per_token


async def test_measure_prompt_pins_the_scripted_provider_and_other_use_keeps_defaults(
    evals_isolation, monkeypatch
):
    from evals import scripted
    from the_one.llm.base import LLMProvider

    made = []

    class Spy(scripted.ScriptedProvider):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            made.append(self)

    monkeypatch.setattr(scripted, "ScriptedProvider", Spy)
    await build(evals_isolation)
    assert made, "measure-prompt built scripted providers"
    for p in made:
        assert p.max_context_tokens == tokens.MEASURE_WINDOW == 16384
        assert p.bytes_per_token == tokens.MEASURE_BYTES_PER_TOKEN == 3.5
        assert p.context_window_known is True
    # the same class built anywhere else keeps the base class defaults (no pin)
    plain = scripted.ScriptedProvider([])
    assert plain.max_context_tokens == LLMProvider.max_context_tokens == 128_000
    assert plain.bytes_per_token == LLMProvider.bytes_per_token == 4.0
    assert "context_window_known" not in vars(plain)


async def test_measure_prompt_builds_its_harness_with_no_fixture_server_or_self_test(
    evals_isolation, monkeypatch
):
    from evals.harness import Harness

    def must_not_run(*a, **k):
        raise AssertionError("measure-prompt must not use the fixture host rewrite")

    monkeypatch.setattr("evals.harness.fixture_host_patch", must_not_run)
    monkeypatch.setattr(Harness, "_self_test", must_not_run)
    doc = await build(evals_isolation)
    assert doc["schema"] == 2


async def test_the_exposure_record_the_agent_carries_reaches_run_and_transcript_records(
    evals_isolation, monkeypatch
):
    """The first conversation's record is stored as ``exposure``, outside ``effective``."""
    from _evals_helpers import make_tree, run

    from evals import scripted
    from the_one.agent.core import Agent
    from the_one.agent.tool_exposure import ToolExposure

    reads = []

    def record(self):
        reads.append(1)
        return ToolExposure(len(reads) == 1, 1000, 50 * len(reads), True, 16384)

    # the factory also assigns the attribute, so the property accepts (and ignores) a write
    monkeypatch.setattr(
        Agent, "tool_exposure", property(record, lambda self, value: None), raising=False
    )
    two_conversations = (
        'id = "demo"\nclass = "hold"\n\n'
        '[[conversations]]\nturns = ["a"]\n\n[[conversations]]\nturns = ["b"]\n\n'
        '[[checks]]\nname = "reply_matches"\npattern = "ok"\n'
    )
    sdir = make_tree(evals_isolation, {})
    (sdir / "demo.toml").write_text(two_conversations)

    def hook(spec, base):
        return scripted.ScriptedProvider([scripted.text("ok"), scripted.text("ok")])

    code, run_dir = await run(evals_isolation, sdir, hook)
    assert code == 0
    (rec,) = [json.loads(x) for x in (run_dir / "results.jsonl").read_text().splitlines()]
    want = {"decided": True, "budget": 1000, "estimate": 50, "window_known": True, "window": 16384}
    assert rec["exposure"] == want and rec["tools_off"] is False
    assert "exposure" not in rec["effective"]
    tr = json.loads((run_dir / "transcripts" / "demo__gpt-oss__f0p0__a1.json").read_text())
    assert tr["exposure"] == want and tr["tools_off"] is False and "exposure" not in tr["effective"]
    assert len(reads) == 1  # read once per run, at the first conversation's create


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


async def test_connector_variants_are_built_mapped_then_unmapped(evals_isolation, monkeypatch):
    """DD13: each variant gets a distinct agent name; the row exists only while it is measured."""
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorRepository

    seen: list[tuple[str, list[str], list[str]]] = []
    real = tokens.connector_row

    def spy(agent_name):
        cm = real(agent_name)

        class Wrap:
            async def __aenter__(self):
                row = await cm.__aenter__()
                seen.append((agent_name, await _ids(), []))
                return row

            async def __aexit__(self, *exc):
                await cm.__aexit__(*exc)
                seen[-1][2].extend(await _ids())

        return Wrap()

    async def _ids():
        from the_one.config import settings
        from the_one.encryption import get_encryptor

        repo = ConnectorRepository(await get_connection(), get_encryptor(settings.data_dir))
        return [c.config["default_agent"] for c in await repo.list()]

    monkeypatch.setattr(tokens, "connector_row", spy)
    doc = await build(evals_isolation)
    assert [s[0] for s in seen] == [
        "ev-measure-bare-measure-f0p0-90",
        "ev-measure-all-on-measure-f0p0-91",
    ]
    for name, during, after in seen:
        assert during == [name] and after == []  # inserted for the run, deleted after
    assert len({s[0] for s in seen}) == 2
    # the plain bare and all-on are never mapped, and the scripts match (all-on searches)
    assert "bare-connector" in doc["configs"] and "all-on-connector" in doc["configs"]
    assert tokens._script_for("all-on-connector", "q")[0].tool_calls  # search_tools script
    assert not hasattr(tokens._script_for("bare-connector", "q")[0], "tool_calls") or not (
        tokens._script_for("bare-connector", "q")[0].tool_calls
    )


def test_platform_prompt_sections_split_matches_the_whole_count():
    from evals.tokens import platform_prompt_sections
    from the_one.agent.platform_prompt import render_platform, render_tool_free

    for text, caps in (
        (render_platform(Capabilities.all_on()), Capabilities.all_on()),
        (render_tool_free(Capabilities.all_on()), Capabilities(tools=False)),
    ):
        assert platform_prompt_sections(text) == sections_for(caps)
        parts = extract_parts(text, [], C, platform_sections=platform_prompt_sections)
        assert [p.name for p in parts] == [sid for sid, _ in sections_for(caps)]
        assert sum(p.tokens for p in parts) == C.count(text)
        assert sum(p.chars for p in parts) == len(text)
    assert platform_prompt_sections("custom text") == [("platform", "custom text")]


def test_platform_prompt_sections_handle_every_conditional_render(caplog):
    import itertools

    from evals.tokens import platform_prompt_sections
    from the_one.agent.platform_prompt import render_platform

    combos = [
        Capabilities(tools=True, knowledge=kb, exec_tools=ex, time_tool=tt)
        for kb, ex, tt in itertools.product((True, False), repeat=3)
    ] + [Capabilities(tools=False)]
    for caps in combos:
        text = render_platform(caps)
        parts = extract_parts(text, [], C, platform_sections=platform_prompt_sections)
        assert "platform" not in [p.name for p in parts], caps
        assert sum(p.tokens for p in parts) == C.count(text), caps
        assert sum(p.chars for p in parts) == len(text), caps
    caplog.clear()
    with caplog.at_level("WARNING"):
        assert platform_prompt_sections("custom text") == [("platform", "custom text")]
    assert "matches no capability combination" in caplog.text


def test_unattributable_platform_text_fails_measurement_loudly():
    import pytest

    from evals.tokens import (
        PlatformAttributionError,
        RawConfig,
        measure_configs,
        platform_prompt_sections,
    )
    from the_one.agent.platform_prompt import render_platform

    with pytest.raises(PlatformAttributionError):
        platform_prompt_sections("custom text", strict=True)
    ok = render_platform(Capabilities.all_on())
    rc = RawConfig("c", ok, [], None, "", [], [], [])
    assert "totals" in measure_configs({"c": rc}, C)["c"]
    bad = RawConfig("c", "custom text", [], None, "", [], [], [])
    with pytest.raises(PlatformAttributionError):
        measure_configs({"c": bad}, C)


def test_tool_free_notes_variant_needs_no_extra_matching():
    from the_one.agent.config import RenderedNote, compose_system_prompt

    free = compose_system_prompt(
        PLATFORM_TOOL_FREE,
        "",
        notes=[RenderedNote(1, "a note", False)],
        date_line="D",
        tools=False,
    )
    parts = extract_parts(free, [], C, note_texts=["a note"], date_lines=["D"], notes_present=True)
    names = [p.name for p in parts]
    assert names[-2:] == ["notes_layer", "date_line"]
    assert "unattributed" not in names


def test_sections_that_tile_the_platform_text_are_counted_cumulatively():
    class Pairwise:
        name = "pairwise"

        def count(self, text: str) -> int:  # merges across a boundary: not additive
            return len(text) // 2

    parts = extract_parts(
        "abc",
        [],
        Pairwise(),
        platform_sections=lambda t: [("a", t[:1]), ("b", t[1:2]), ("c", t[2:])],
    )
    assert sum(p.tokens for p in parts) == Pairwise().count("abc") == 1


async def test_routines_on_adds_the_four_schemas_and_leaves_the_prompt_fingerprint(
    evals_isolation,
):
    """M33 F2 L4: the extra configuration is measured but outside the prompt fingerprint."""
    doc = await build(evals_isolation, "r1")
    on, base = doc["configs"]["routines-on"], doc["configs"]["all-on"]
    assert on["totals"]["tools"] > base["totals"]["tools"]
    assert on["totals"]["prompt_sections"] == base["totals"]["prompt_sections"]
    assert "routines-on" in tokens.EXTRA_CONFIGS
    assert (await build(evals_isolation, "r2"))["fingerprints"] == doc["fingerprints"]
