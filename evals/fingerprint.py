"""Fingerprints (DD15): hashes of rendered output, not of constant names.

- ``prompt``: SHA-256 of the rendered platform text and starting tool schemas for the
  fixed bare, all-on and tool-free configurations (built exactly as
  ``measure-prompt`` builds them), plus the all-on agent's knowledge-base search
  tool schema. It survives Flight 2 replacing the prompt constants.
- ``scenarios``: the scenario files, fixtures and judge files (sorted relative
  paths plus contents).
- ``models``: the presets plus each model's recorded effective values and digest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_JUDGE_DIR = PACKAGE_DIR / "judge"


def _digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def prompt_fingerprint(raw: dict[str, Any]) -> str:
    """``raw`` maps a configuration name to its ``tokens.RawConfig``."""
    return _digest(
        {
            name: {"system": rc.system, "schemas": rc.schemas, "kb_schema": rc.kb_schema}
            for name, rc in sorted(raw.items())
        }
    )


def _tree(root: Path, pattern: str = "*") -> list[tuple[str, str]]:
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob(pattern)):
        if p.is_file() and "__pycache__" not in p.parts:
            out.append((p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()))
    return out


def scenarios_fingerprint(
    scenarios_dir: Path, fixtures_dir: Path | None = None, judge_dir: Path | None = None
) -> str:
    fixtures = fixtures_dir if fixtures_dir is not None else scenarios_dir.parent / "fixtures"
    judge = judge_dir if judge_dir is not None else DEFAULT_JUDGE_DIR
    return _digest(
        {
            "scenarios": _tree(scenarios_dir, "*.toml"),
            "fixtures": _tree(fixtures),
            "judge": _tree(judge),
        }
    )


def models_fingerprint(
    presets: dict[str, dict[str, Any]],
    effective: dict[str, dict[str, Any]],
    model_info: dict[str, dict[str, Any]],
) -> str:
    return _digest({"presets": presets, "effective": effective, "model_info": model_info})


def preset_dict(preset: Any) -> dict[str, Any]:
    return {
        "type": preset.type,
        "model": preset.model,
        "base_url": preset.base_url,
        "config": dict(preset.config),
    }
