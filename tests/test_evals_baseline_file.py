"""The committed M30 baseline file loads and holds every DD16 field."""

import json
from pathlib import Path

BASELINE = Path(__file__).resolve().parent.parent / "evals" / "baselines" / "m30-today.json"


BASELINES = BASELINE.parent
CELL_KEYS = {
    "passes",
    "counted",
    "excluded",
    "wilson",
    "phrasing",
    "facts",
    "bar",
    "class",
    "not_exposed",
    "incomplete",
}
SIZE_TARGET_KEYS = {
    f"{config}:{part}"
    for config in ("bare", "all-on", "bare-connector", "all-on-connector", "tool-free")
    for part in ("prompt-text", "tools")
}


def _check_s11(name: str, cell_count: int):
    b = json.loads((BASELINES / f"{name}.json").read_text())
    assert b["schema"] == 2
    assert set(b["fingerprints"]) == {"prompt", "scenarios", "models"}
    assert set(b["models"]) == {"haiku", "qwen3-4b", "lfm3"}
    for model in ("qwen3-4b", "lfm3"):
        assert set(b["models"][model]["model_info"]) >= {"model_digest", "server_version"}
    for m in b["models"].values():
        assert "effective" in m and "preset" in m
    assert set(b["cells"]) == {"haiku", "qwen3-4b", "lfm3"}
    for model, cells in b["cells"].items():
        assert len(cells) == cell_count, model
        for cell, c in cells.items():
            assert CELL_KEYS <= set(c), (model, cell)
            assert not c["incomplete"], (model, cell)
            assert c["counted"] + c["excluded"] + c["not_exposed"] == 20, (model, cell)
    assert set(b["size_targets"]) == SIZE_TARGET_KEYS


def test_s11_platform_has_every_field():
    _check_s11("s11-platform", 17)


def test_s11_routines_has_every_field():
    _check_s11("s11-routines", 5)


def test_m30_today_has_every_dd16_field():
    b = json.loads(BASELINE.read_text())
    assert set(b["fingerprints"]) == {"prompt", "scenarios", "models"}
    assert set(b["models"]) == {"haiku", "gpt-oss"}
    for m in b["models"].values():
        assert "effective" in m and "preset" in m
    assert set(b["models"]["gpt-oss"]["model_info"]) >= {"model_digest", "server_version"}
    for model, cells in b["cells"].items():
        assert len(cells) == 14, model
        for name, c in cells.items():
            for key in (
                "passes",
                "counted",
                "excluded",
                "wilson",
                "phrasing",
                "facts",
                "bar",
                "class",
            ):
                assert key in c, (model, name, key)
            assert not c["incomplete"], (model, name)
            assert c["counted"] + c["excluded"] == 20
    assert set(b["size_targets"]) == {"bare", "all-on"}
    for model in ("haiku", "gpt-oss"):
        assert set(b["sizes"]["model_counts"][model]["input_tokens"]) == {
            "bare",
            "all-on",
            "tool-free",
        }
    assert set(b["sizes"]["configs"]) == {"bare", "all-on", "tool-free"}
