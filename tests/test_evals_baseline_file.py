"""The committed M30 baseline file loads and holds every DD16 field."""

import json
from pathlib import Path

BASELINE = Path(__file__).resolve().parent.parent / "evals" / "baselines" / "m30-today.json"


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
