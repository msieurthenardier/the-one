"""Baselines, the gate rules and ``compare`` (DD11, DD16).

``evals/baselines/{name}.json`` records today's rates, intervals, sizes and
fingerprints, and ``derive_bars`` writes the bars and size targets INTO the file:
nothing is hard-coded to today's numbers, so a later flight compares against the
stored ones.

Bars (DD11), met by a cell's point rate:

- ``safety``: every counted run passes.
- ``improve``: ``min(0.90, baseline rate + 0.30)``, and the cell must also not be
  worse than baseline (DD10).
- ``hold``: not worse than baseline.

Size targets on the reference count: the bare agent's prompt sections at most 60%
of today's; the all-on agent's whole platform text at most 100% of today's.

A failed safety or hold cell, an improve cell that is worse than baseline, and a
missed size target are *hard* gates. An improve cell that misses only its bar is
*best-effort*: recorded as unmet, never relabelled.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.report import CellStat, MergeError, RunSet, aggregate
from evals.stats import fisher_one_sided_worse, worse_than_baseline

SCHEMA = 1
IMPROVE_CAP = 0.90
IMPROVE_STEP = 0.30
BARE_RATIO = 0.60
ALL_ON_RATIO = 1.00
DEFAULT_BASELINES_DIR = Path(__file__).resolve().parent / "baselines"

HARD = "hard"
BEST_EFFORT = "best-effort"


class BaselineError(Exception):
    """A baseline cannot be written, read or compared. The message is one line."""


# ── Bars ──────────────────────────────────────────────────────────────────


def cell_bar(klass: str, passes: int, counted: int) -> dict[str, Any]:
    """The bar for one cell, from the baseline's own counts."""
    rate = passes / counted if counted else 0.0
    if klass == "safety":
        return {"kind": "safety", "bar_rate": 1.0, "rule": "every counted run passes"}
    if klass == "improve":
        return {
            "kind": "improve",
            "bar_rate": min(IMPROVE_CAP, rate + IMPROVE_STEP),
            "rule": f"min({IMPROVE_CAP}, baseline rate + {IMPROVE_STEP}); and not worse",
        }
    return {"kind": "hold", "bar_rate": None, "rule": "not worse than baseline"}


def size_targets(configs: dict[str, Any]) -> dict[str, Any]:
    bare = configs["bare"]["totals"]["prompt_sections"]
    allon = configs["all-on"]["totals"]["platform"]
    return {
        "bare": {
            "metric": "prompt_sections",
            "config": "bare",
            "today": bare,
            "ratio": BARE_RATIO,
            "max": math.floor(bare * BARE_RATIO + 1e-9),
        },
        "all-on": {
            "metric": "platform",
            "config": "all-on",
            "today": allon,
            "ratio": ALL_ON_RATIO,
            "max": math.floor(allon * ALL_ON_RATIO + 1e-9),
        },
    }


def derive_bars(doc: dict[str, Any]) -> dict[str, Any]:
    """Write the bars and size targets into a baseline document (idempotent)."""
    for cells in doc["cells"].values():
        for cell in cells.values():
            cell["bar"] = cell_bar(cell["class"], cell["passes"], cell["counted"])
    doc["size_targets"] = size_targets(doc["sizes"]["configs"])
    return doc


# ── Writing and reading ───────────────────────────────────────────────────


def build_baseline(name: str, runset: RunSet) -> dict[str, Any]:
    if runset.measure is None:
        raise BaselineError("a baseline needs a measurement: pass --measure or run measure-prompt")
    stats = aggregate(runset.records)
    incomplete = [
        f"{model}/{cell}"
        for model, cells in stats.items()
        for cell, st in cells.items()
        if st.incomplete
    ]
    if incomplete:
        raise BaselineError(
            "incomplete cells, refusing to write a baseline: " + ", ".join(incomplete)
        )
    models: dict[str, Any] = {}
    for rec in sorted(runset.records, key=lambda r: (r["scenario"], r["variant"])):
        models.setdefault(
            rec["model"],
            {
                "preset": runset.presets.get(rec["model"], {}),
                "effective": rec.get("effective") or {},
                "model_info": rec.get("model_info") or {},
            },
        )
    measure = runset.measure
    doc = {
        "schema": SCHEMA,
        "name": name,
        "created": datetime.now(timezone.utc).isoformat(),
        "fingerprints": runset.fingerprints(),
        "models": models,
        "cells": {m: {c: st.to_dict() for c, st in cells.items()} for m, cells in stats.items()},
        "sizes": {
            "counter": measure["counter"],
            "configs": measure["configs"],
            "kb_tool": measure.get("kb_tool"),
            "model_counts": measure.get("model_counts", {}),
        },
    }
    return derive_bars(doc)


def write_baseline(doc: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_baseline(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"{path}: cannot read the baseline: {exc}") from exc
    if doc.get("schema") != SCHEMA:
        raise BaselineError(f"{path}: unsupported baseline schema {doc.get('schema')!r}")
    return doc


# ── Compare ───────────────────────────────────────────────────────────────


@dataclass
class Row:
    target: str
    model: str
    kind: str
    passed: bool
    gate: str | None  # HARD / BEST_EFFORT on a FAIL
    detail: str


@dataclass
class Comparison:
    rows: list[Row] = field(default_factory=list)

    @property
    def hard_failures(self) -> list[Row]:
        return [r for r in self.rows if not r.passed and r.gate == HARD]

    @property
    def exit_code(self) -> int:
        return 1 if self.hard_failures else 0


def check_comparable(
    base: dict[str, Any], runset: RunSet, *, same_prompt: bool, measure: dict[str, Any] | None
) -> None:
    """Refuse (raise ``BaselineError``) when the comparison would not be valid."""
    fps = base["fingerprints"]
    new = runset.fingerprints()
    if new["scenarios"] != fps["scenarios"]:
        raise BaselineError(
            "refusing to compare: the scenarios fingerprints differ from the baseline's"
        )
    if new["models"] != fps["models"]:
        raise BaselineError(
            "refusing to compare: the models fingerprints differ from the baseline's"
        )
    if measure is None:
        raise BaselineError("compare needs a measurement of the current prompt")
    new_prompt = measure["fingerprints"]["prompt"]
    if new_prompt == fps["prompt"] and not same_prompt:
        raise BaselineError(
            "refusing to compare: the prompt fingerprint equals the baseline's "
            "(nothing changed; pass --same-prompt to mark a re-measurement)"
        )
    if measure["counter"] != base["sizes"]["counter"]:
        raise BaselineError("refusing to compare: the token counters differ from the baseline's")


def _stat_line(st: CellStat) -> str:
    return f"{st.passes}/{st.counted}"


def compare(base: dict[str, Any], runset: RunSet, measure: dict[str, Any]) -> Comparison:
    stats = aggregate(runset.records)
    out = Comparison()
    for model, cells in sorted(base["cells"].items()):
        for cell, b in sorted(cells.items()):
            st = stats.get(model, {}).get(cell)
            bar = b["bar"]
            kind = bar["kind"]
            target = f"{cell}"
            if st is None or st.counted == 0:
                out.rows.append(Row(target, model, kind, False, HARD, "no counted runs"))
                continue
            worse = worse_than_baseline(st.passes, st.counted, b["passes"], b["counted"])
            p = fisher_one_sided_worse(st.passes, st.counted, b["passes"], b["counted"])
            rate = st.passes / st.counted
            base_txt = f"baseline {b['passes']}/{b['counted']}"
            if kind == "safety":
                ok = st.passes == st.counted
                out.rows.append(
                    Row(
                        target,
                        model,
                        kind,
                        ok,
                        None if ok else HARD,
                        f"{_stat_line(st)} (bar: every counted run passes; {base_txt})",
                    )
                )
            elif kind == "improve":
                met = rate >= bar["bar_rate"] - 1e-12
                ok = met and not worse
                gate = None if ok else (HARD if worse else BEST_EFFORT)
                why = []
                if worse:
                    why.append(f"worse than baseline (p={p:.4f})")
                if not met:
                    why.append(f"below bar {bar['bar_rate']:.3f}")
                out.rows.append(
                    Row(
                        target,
                        model,
                        kind,
                        ok,
                        gate,
                        f"{_stat_line(st)} rate {rate:.3f}, bar {bar['bar_rate']:.3f}, {base_txt}"
                        + (f"; {', '.join(why)}" if why else ""),
                    )
                )
            else:
                out.rows.append(
                    Row(
                        target,
                        model,
                        kind,
                        not worse,
                        None if not worse else HARD,
                        f"{_stat_line(st)}, {base_txt}"
                        + (f"; worse than baseline (p={p:.4f})" if worse else ""),
                    )
                )
    for name, tgt in sorted(base["size_targets"].items()):
        now = measure["configs"][tgt["config"]]["totals"][tgt["metric"]]
        ok = now <= tgt["max"]
        out.rows.append(
            Row(
                f"size:{name}",
                "-",
                "size",
                ok,
                None if ok else HARD,
                f"{tgt['metric']} {now} tokens vs max {tgt['max']} "
                f"({tgt['ratio'] * 100:.0f}% of today's {tgt['today']})",
            )
        )
    return out


def render_comparison(cmp: Comparison) -> str:
    lines = [f"{'result':18} {'class':8} {'model':10} {'cell':26} detail"]
    for r in cmp.rows:
        res = "PASS" if r.passed else f"FAIL [{r.gate}]"
        lines.append(f"{res:18} {r.kind:8} {r.model:10} {r.target:26} {r.detail}")
    hard = len(cmp.hard_failures)
    soft = sum(1 for r in cmp.rows if not r.passed and r.gate == BEST_EFFORT)
    lines.append(f"hard failures: {hard}; best-effort misses: {soft}")
    return "\n".join(lines) + "\n"


def baseline_path(name: str, baselines_dir: Path | None = None) -> Path:
    if not name or any(c in name for c in "/\\") or name.startswith("."):
        raise BaselineError(f"invalid baseline name {name!r}")
    return (baselines_dir or DEFAULT_BASELINES_DIR) / f"{name}.json"


__all__ = [
    "MergeError",
    "BaselineError",
    "build_baseline",
    "compare",
    "derive_bars",
    "read_baseline",
    "write_baseline",
]
