"""Model presets, provider rows, effective values, Ollama server info (DD4). Offline."""

from __future__ import annotations

import httpx
import pytest

from evals import models


def test_shipped_presets():
    presets = models.load_presets()
    assert list(presets) == ["haiku", "qwen3-4b", "lfm3", "gpt-oss"]
    haiku, gpt = presets["haiku"], presets["gpt-oss"]
    for name, model in (
        ("qwen3-4b", "qwen3:4b-instruct-2507-q4_K_M"),
        ("lfm3", "lfm3:1.7b-q4_K_M"),
    ):
        p = presets[name]
        assert (p.type, p.model, p.base_url) == ("ollama", model, "http://localhost:11434")
        assert p.config == {"num_ctx": 16384} and p.default is True
    assert gpt.default is False and haiku.default is True
    assert (haiku.type, haiku.model) == ("anthropic-plan-token", "claude-haiku-4-5-20251001")
    assert (gpt.type, gpt.model, gpt.base_url) == (
        "ollama",
        "gpt-oss:20b",
        "http://localhost:11434",
    )
    assert haiku.needs_token and not gpt.needs_token
    assert haiku.provider_id == "ev-haiku"


def test_select_presets_and_unknown_name():
    presets = models.load_presets()
    assert [p.name for p in models.select_presets(presets, ["gpt-oss"])] == ["gpt-oss"]
    # no names: only the default presets, in file order (gpt-oss is not one)
    assert [p.name for p in models.select_presets(presets, None)] == ["haiku", "qwen3-4b", "lfm3"]
    assert [p.name for p in models.select_presets(presets, [])] == ["haiku", "qwen3-4b", "lfm3"]
    with pytest.raises(models.PresetError, match="unknown model preset 'nope'"):
        models.select_presets(presets, ["nope"])


def test_run_with_no_models_plans_only_the_default_presets_and_by_name_still_selects_gpt_oss(
    tmp_path,
):
    from _evals_helpers import make_tree, opts, simple_scenario

    from evals import runner

    sdir = make_tree(tmp_path, {"demo": simple_scenario()})
    plan = runner.build_plan(opts(tmp_path, sdir, models=None))
    assert [p.name for p in plan.presets] == ["haiku", "qwen3-4b", "lfm3"]
    assert {s.model for s in plan.specs} == {"haiku", "qwen3-4b", "lfm3"}
    assert "gpt-oss" in plan.all_presets  # loaded, just not selected
    named = runner.build_plan(opts(tmp_path, sdir, models=["gpt-oss"]))
    assert [p.name for p in named.presets] == ["gpt-oss"]


def test_default_field_parses_and_a_non_boolean_is_refused(tmp_path):
    f = tmp_path / "m.toml"
    base = 'type = "ollama"\nmodel = "m"\nbase_url = "http://x"\n'
    f.write_text(f"[a]\n{base}\n[b]\n{base}default = false\n")
    loaded = models.load_presets(f)
    assert loaded["a"].default is True and loaded["b"].default is False
    assert [p.name for p in models.select_presets(loaded, None)] == ["a"]
    assert [p.name for p in models.select_presets(loaded, ["b"])] == ["b"]  # by name still works
    f.write_text(f'[a]\n{base}default = "no"\n')
    with pytest.raises(models.PresetError, match=r"a.default: must be true or false"):
        models.load_presets(f)


def test_default_is_not_part_of_the_preset_fingerprint():
    from evals.fingerprint import preset_dict

    presets = models.load_presets()
    p = presets["gpt-oss"]
    flipped = models.Preset(p.name, p.type, p.model, p.base_url, dict(p.config), default=True)
    assert preset_dict(p) == preset_dict(flipped)
    assert "default" not in preset_dict(p)


def test_bad_presets_file(tmp_path):
    f = tmp_path / "m.toml"
    f.write_text('[x]\ntype = "ollama"\n')
    with pytest.raises(models.PresetError, match=r"m.toml: x.model: is required"):
        models.load_presets(f)


def test_provider_row_carries_the_token_only_for_token_presets():
    presets = models.load_presets()
    row = models.provider_row(presets["haiku"], "tok-123")
    assert row.type == "anthropic-plan-token" and row.api_key == "tok-123"
    assert models.provider_row(presets["gpt-oss"], "tok-123").api_key is None
    with pytest.raises(models.PresetError, match="needs the plan token"):
        models.provider_row(presets["haiku"], None)


def test_effective_values_read_from_real_providers(monkeypatch):
    from the_one.llm import get_provider

    for name in (
        "THE_ONE_ANTHROPIC_EXTENDED_THINKING",
        "THE_ONE_REASONING_EFFORT",
        "THE_ONE_OLLAMA_NUM_CTX",
    ):
        monkeypatch.delenv(name, raising=False)
    plan = get_provider("anthropic-plan-token", model="m", access_token="fake")
    assert models.effective_values(plan) == {
        "thinking": False,
        "reasoning_effort": None,
        "num_ctx": None,
        "temperature": 0.0,
    }
    ollama = get_provider(
        "ollama",
        model="gpt-oss:20b",
        base_url="http://localhost:11434",
        native_api=True,
        config={"num_ctx": 8192, "reasoning_effort": "high"},
    )
    eff = models.effective_values(ollama)
    assert eff["num_ctx"] == 8192
    assert eff["reasoning_effort"] == "high"
    assert eff["temperature"] == 0.0
    assert eff["thinking"] is None  # not exposed by this provider: recorded honestly as None


def test_effective_thinking_is_model_aware(monkeypatch):
    from the_one.llm import get_provider

    monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)
    cfg = {"thinking_enabled": True}
    old = get_provider(
        "anthropic-plan-token", model="claude-haiku-4-5", access_token="f", config=cfg
    )
    new = get_provider(
        "anthropic-plan-token", model="claude-sonnet-4-6", access_token="f", config=cfg
    )
    assert models.effective_values(old)["thinking"] is False
    assert models.effective_values(new)["thinking"] is True


async def test_ollama_server_info_digest_and_version():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.3"})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"digest": "sha256:abc"})
        return httpx.Response(404)

    info = await models.ollama_server_info(
        "http://localhost:11434/v1", "gpt-oss:20b", transport=httpx.MockTransport(handler)
    )
    assert info == {"server_version": "0.12.3", "model_digest": "sha256:abc"}


async def test_ollama_server_info_digest_falls_back_to_tags_and_failures_are_none():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "gpt-oss:20b", "digest": "d1"}]})
        return httpx.Response(500)

    info = await models.ollama_server_info(
        "http://localhost:11434", "gpt-oss:20b", transport=httpx.MockTransport(handler)
    )
    assert info == {"server_version": None, "model_digest": "d1"}

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    gone = await models.ollama_server_info(
        "http://localhost:11434", "m", transport=httpx.MockTransport(down)
    )
    assert gone == {"server_version": None, "model_digest": None}
