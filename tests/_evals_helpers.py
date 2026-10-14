"""Shared helpers for the evals runner tests (offline: scripted provider only)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from evals import scripted
from evals.runner import Hooks, RunOptions, run_invocation

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "evals"
FAKE_TOKEN = "sk-ant-oat01-FAKETOKEN_for_unit_tests_0123456789abcdef"
NO_SLEEP_HOOKS: dict[str, Any] = {}


@pytest.fixture
def evals_isolation(monkeypatch, tmp_path):
    """Isolate the process-wide singletons an evals invocation touches."""
    from the_one import vectors
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(db_connection, "_connection", None)
    monkeypatch.setattr(vectors, "_store", None)
    monkeypatch.setattr(settings, "data_dir", settings.data_dir)  # restored on teardown
    monkeypatch.setenv("HOME", str(tmp_path / "fake-real-home"))  # restored on teardown
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "fake-real-home"))
    for name in (
        "THE_ONE_ANTHROPIC_EXTENDED_THINKING",
        "THE_ONE_REASONING_EFFORT",
        "THE_ONE_OLLAMA_NUM_CTX",
        "THE_ONE_STOP",
        "THE_ONE_RESPONSE_FORMAT",
    ):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def real_data_dir(monkeypatch, tmp_path):
    """Point platformdirs at a temp 'real' default data directory."""
    real = tmp_path / "real-user-data" / "the-one"
    import the_one.config as cfg

    monkeypatch.setattr(cfg.platformdirs, "user_data_dir", lambda *a, **k: str(real))
    return real


def make_tree(root: Path, scenarios: dict[str, str], *, with_fixtures: bool = True) -> Path:
    """Write ``root/scenarios/*.toml`` and copy the shared fixtures; return the scenarios dir."""
    sdir = root / "scenarios"
    sdir.mkdir(parents=True, exist_ok=True)
    for name, text in scenarios.items():
        (sdir / f"{name}.toml").write_text(text, encoding="utf-8")
    if with_fixtures:
        fx = root / "fixtures"
        if not fx.exists():
            shutil.copytree(FIXTURE_ROOT / "fixtures", fx)
    return sdir


def token_file(tmp_path: Path, token: str = FAKE_TOKEN) -> Path:
    p = tmp_path / "plan-token"
    p.write_text(token + "\n", encoding="utf-8")
    return p


def simple_scenario(
    sid: str = "demo",
    *,
    klass: str = "hold",
    agent: str = "",
    checks: str = '[[checks]]\nname = "reply_matches"\npattern = "hello"\n',
    turns: str = '["say hello"]',
    extra: str = "",
) -> str:
    return (
        f'id = "{sid}"\nclass = "{klass}"\n{extra}\n{agent}\n'
        f"[[conversations]]\nturns = {turns}\n\n{checks}"
    )


def opts(tmp_path: Path, sdir: Path, **kw: Any) -> RunOptions:
    base = {
        "models": ["gpt-oss"],
        "scenarios_dir": sdir,
        "n": 1,
        "run_dir": tmp_path / "runs" / "r1",
    }
    base.update(kw)
    return RunOptions(**base)


async def no_sleep(_seconds: float) -> None:
    return None


async def fake_probe(_preset: Any) -> dict[str, Any]:
    return {"server_version": "0.0-test", "model_digest": "sha256:test"}


def hooks(provider_hook=None, **kw: Any) -> Hooks:
    return Hooks(
        provider_hook=provider_hook,
        sleep=no_sleep,
        model_probe=fake_probe,
        turn_timeout=30.0,
        **kw,
    )


def script_hook(*messages):
    """A provider hook that gives every run a fresh script of these messages."""
    return lambda spec, base: scripted.ScriptedProvider(list(messages))


async def run(tmp_path, sdir, provider_hook=None, hook_kw=None, **kw):
    o = opts(tmp_path, sdir, **kw)
    code = await run_invocation(o, hooks(provider_hook, **(hook_kw or {})), out=lambda s: None)
    return code, o.run_dir


# ── Synthetic run directories for the report / baseline / compare tests ──


def synth_record(
    cell: str,
    model: str,
    i: int,
    outcome: str,
    *,
    klass: str = "hold",
    effective: dict | None = None,
    model_info: dict | None = None,
    saved: int | None = None,
) -> dict[str, Any]:
    counted = outcome in ("pass", "fail")
    checks = []
    if saved is not None:
        checks.append(
            {
                "name": "notes_from_untrusted_flagged",
                "cell": cell,
                "passed": outcome == "pass",
                "extra": {"saved": saved, "needing_flag": saved},
            }
        )
    return {
        "run_key": f"{cell}/{model}/f{i // 4}p{i % 4}",
        "scenario": cell,
        "class": klass,
        "cell_names": [cell],
        "cell_classes": {cell: klass},
        "model": model,
        "variant": f"f{i // 4}p{i % 4}",
        "phrasing_index": i % 4,
        "fact_index": i // 4,
        "attempt": 1,
        "outcome": outcome,
        "counted": counted,
        "cells": {cell: outcome == "pass"} if counted else None,
        "checks": checks,
        "effective": effective if effective is not None else {"temperature": 0.0},
        "model_info": model_info if model_info is not None else {"model_digest": "sha256:d1"},
    }


def make_run_dir(
    root: Path,
    name: str,
    cells: dict[tuple[str, str], tuple[str, int, int, int]],
    *,
    scenarios_fp: str = "scen-1",
    effective: dict | None = None,
    saved: dict[str, int] | None = None,
    measure: dict | None = None,
) -> Path:
    """``cells[(cell, model)] = (class, passes, fails, excluded)`` -> one run directory."""
    import json

    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    presets: dict[str, Any] = {}
    for (cell, model), (klass, passes, fails, excluded) in cells.items():
        presets[model] = {
            "type": "ollama",
            "model": f"{model}:x",
            "base_url": "http://x",
            "config": {},
        }
        outcomes = ["pass"] * passes + ["fail"] * fails + ["cut-short"] * excluded
        for i, outcome in enumerate(outcomes):
            rec = synth_record(
                cell,
                model,
                i,
                outcome,
                klass=klass,
                effective=effective,
                saved=(saved or {}).get(cell),
            )
            lines.append(json.dumps(rec))
    (d / "results.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (d / "fingerprints.json").write_text(
        json.dumps({"scenarios": scenarios_fp, "presets": presets}), encoding="utf-8"
    )
    if measure is not None:
        (d / "measure.json").write_text(json.dumps(measure), encoding="utf-8")
    return d


def synth_measure(bare: int = 100, all_on: int = 500, prompt_fp: str = "prompt-1") -> dict:
    def cfg(prompt: int, tools: int) -> dict:
        return {
            "parts": [],
            "totals": {"prompt_sections": prompt, "tools": tools, "platform": prompt + tools},
        }

    return {
        "schema": 1,
        "counter": "standin:bytes/4",
        "configs": {
            "bare": cfg(bare, 200),
            "all-on": cfg(all_on - 100, 100),
            "tool-free": cfg(20, 0),
        },
        "kb_tool": {"name": "kb__x__search", "tokens": 10},
        "fingerprints": {"prompt": prompt_fp},
        "model_counts": {},
    }
