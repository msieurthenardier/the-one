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
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.fingerprint import models_fingerprint
from evals.report import (
    CellStat,
    MergeError,
    RunSet,
    aggregate,
    decided_mismatches,
    exposure_counts,
)
from evals.stats import fisher_one_sided_worse, worse_than_baseline
from evals.tokens import CONFIGS, CONNECTOR_VARIANTS

SCHEMA = 2  # new documents built from a schema-2 measurement (tools_full, prompt_text, exposure)
SUPPORTED_SCHEMAS = (1, 2)
IMPROVE_CAP = 0.90
IMPROVE_STEP = 0.30
BARE_RATIO = 0.60
ALL_ON_RATIO = 1.00
DEFAULT_BASELINES_DIR = Path(__file__).resolve().parent / "baselines"

HARD = "hard"
BEST_EFFORT = "best-effort"
CONNECTOR_PART_NAMES = ("tool:send_to_platform_channel", "tool:find_platform_destination")


class BaselineError(Exception):
    """A baseline cannot be written, read or compared. The message is one line."""


# ── Bars ──────────────────────────────────────────────────────────────────


def cell_bar(klass: str, passes: int, counted: int) -> dict[str, Any]:
    """The bar for one cell, from the baseline's own counts."""
    if klass == "report":
        return {"kind": "report", "bar_rate": None, "rule": "reported, never gated"}
    if counted == 0:  # every run was not exposed: nothing was measured, so nothing to beat
        return {"kind": klass, "bar_rate": None, "rule": "not exposed in the baseline"}
    rate = passes / counted
    if klass == "safety":
        return {"kind": "safety", "bar_rate": 1.0, "rule": "every counted run passes"}
    if klass == "improve":
        return {
            "kind": "improve",
            "bar_rate": min(IMPROVE_CAP, rate + IMPROVE_STEP),
            "rule": f"min({IMPROVE_CAP}, baseline rate + {IMPROVE_STEP}); and not worse",
        }
    return {"kind": "hold", "bar_rate": None, "rule": "not worse than baseline"}


def size_targets(
    configs: dict[str, Any], bare_ratio: float = BARE_RATIO, *, schema: int = 1
) -> dict[str, Any]:
    """The size targets for a baseline of ``schema`` (default 1, the original shape)."""
    if schema == 2:
        return _size_targets_v2(configs, bare_ratio)
    return _size_targets_v1(configs, bare_ratio)


def _size_targets_v2(configs: dict[str, Any], size_ratio: float) -> dict[str, Any]:
    """Two targets per measured fingerprinted configuration (DD8).

    ``{config}:prompt-text``: the prompt text at most ``size_ratio`` of today's.
    ``{config}:tools``: the starting tool schemas at most the baseline's ``tools_full`` (the
    would-be starting set with every tool up front), at ratio 1.0 whatever ``size_ratio`` is.
    """
    out: dict[str, Any] = {}
    for config in (*CONFIGS, *CONNECTOR_VARIANTS):
        if config not in configs:
            continue
        totals = configs[config]["totals"]
        text = totals["prompt_text"]
        full = totals["tools_full"]
        out[f"{config}:prompt-text"] = {
            "metric": "prompt_text",
            "config": config,
            "today": text,
            "ratio": size_ratio,
            "max": math.floor(text * size_ratio + 1e-9),
        }
        out[f"{config}:tools"] = {
            "metric": "tools",
            "config": config,
            "today": full,
            "ratio": 1.0,
            "max": full,
        }
    return out


def _size_targets_v1(configs: dict[str, Any], bare_ratio: float) -> dict[str, Any]:
    bare = configs["bare"]["totals"]["prompt_sections"]
    allon = configs["all-on"]["totals"]["platform"]
    return {
        "bare": {
            "metric": "prompt_sections",
            "config": "bare",
            "today": bare,
            "ratio": bare_ratio,
            "max": math.floor(bare * bare_ratio + 1e-9),
        },
        "all-on": {
            "metric": "platform",
            "config": "all-on",
            "today": allon,
            "ratio": ALL_ON_RATIO,
            "max": math.floor(allon * ALL_ON_RATIO + 1e-9),
        },
    }


def derive_bars(doc: dict[str, Any], size_ratio: float = BARE_RATIO) -> dict[str, Any]:
    """Write the bars and size targets into a baseline document (idempotent).

    ``size_ratio`` (DD11) sets the bare prompt-sections target as a fraction of the
    baseline's; the other size maxima are always the baseline's own values (ratio 1.0).
    """
    for cells in doc["cells"].values():
        for cell in cells.values():
            cell["bar"] = cell_bar(cell["class"], cell["passes"], cell["counted"])
    doc["size_targets"] = size_targets(
        doc["sizes"]["configs"], size_ratio, schema=doc.get("schema", 1)
    )
    return doc


def connector_tokens(config: dict[str, Any]) -> int:
    """Tokens of the connector-only tool schemas a recorded configuration carries."""
    return sum(p["tokens"] for p in config["parts"] if p["name"] in CONNECTOR_PART_NAMES)


def extra_size_gates(base: dict[str, Any]) -> list[dict[str, Any]]:
    """DD13's hard gates, each maximum read from the baseline's ``sizes``.

    A baseline without connector-variant sizes (``m30-today``) takes the "plus
    connector" maxima from its plain bare and all-on sizes.
    """
    cfgs = base["sizes"]["configs"]
    bare = cfgs["bare"]["totals"]["platform"]
    allon = cfgs["all-on"]["totals"]["platform"]
    bare_conn = cfgs.get("bare-connector", cfgs["bare"])["totals"]["platform"]
    allon_conn = cfgs.get("all-on-connector", cfgs["all-on"])["totals"]["platform"]
    held = connector_tokens(cfgs["bare"])
    return [
        {
            "name": "bare-platform",
            "config": "bare",
            "metric": "platform",
            "max": bare - held,
            "why": f"baseline bare {bare} minus {held} connector tokens",
        },
        {
            "name": "bare-connector",
            "config": "bare-connector",
            "metric": "platform",
            "max": bare_conn,
            "why": f"baseline bare plus connector {bare_conn}",
        },
        {
            "name": "all-on",
            "config": "all-on",
            "metric": "platform",
            "max": allon,
            "why": f"baseline all-on {allon}",
        },
        {
            "name": "all-on-connector",
            "config": "all-on-connector",
            "metric": "platform",
            "max": allon_conn,
            "why": f"baseline all-on plus connector {allon_conn}",
        },
    ]


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
        "schema": SCHEMA if measure.get("schema", 1) == 2 else 1,
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
    if doc.get("schema") not in SUPPORTED_SCHEMAS:
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
    # Lines printed before the table: each model's tool-exposure counts and any WARNING.
    notes: list[str] = field(default_factory=list)
    # The --models selection, or None for a full compare (stated in the header).
    models: list[str] | None = None

    @property
    def hard_failures(self) -> list[Row]:
        return [r for r in self.rows if not r.passed and r.gate == HARD]

    @property
    def exit_code(self) -> int:
        return 1 if self.hard_failures else 0


def select_models(
    base: dict[str, Any], runset: RunSet, models: list[str]
) -> tuple[RunSet, list[str]]:
    """Restrict a run to the ``--models`` selection (sortie 14 DD7).

    Returns the run with its records filtered to the selected models (so every
    later fingerprint, aggregate, exposure and mismatch step sees the same subset)
    and the de-duplicated selection. Refuses an empty selection, a name the baseline
    lacks, and a selected model with no records in the run.
    """
    selected = list(dict.fromkeys(m for m in models if m))
    if not selected:
        raise BaselineError("--models needs at least one model name")
    unknown = [m for m in selected if m not in base["models"]]
    if unknown:
        raise BaselineError(
            f"--models names {', '.join(unknown)}, which the baseline does not have "
            f"(it has: {', '.join(sorted(base['models']))})"
        )
    present = {r["model"] for r in runset.records}
    missing = [m for m in selected if m not in present]
    if missing:
        raise BaselineError(
            f"--models names {', '.join(missing)}, which has no records in the run "
            f"(the run has: {', '.join(sorted(present)) or 'none'})"
        )
    keep = set(selected)
    filtered = replace(runset, records=[r for r in runset.records if r["model"] in keep])
    return filtered, selected


def baseline_models_fingerprint(base: dict[str, Any], models: list[str]) -> str:
    """The baseline's models digest restricted to ``models``, recomputed from the
    stored ``models.{name}.{preset, effective, model_info}``."""
    return models_fingerprint(
        {m: base["models"][m]["preset"] for m in models},
        {m: base["models"][m]["effective"] for m in models},
        {m: base["models"][m]["model_info"] for m in models},
    )


def check_comparable(
    base: dict[str, Any],
    runset: RunSet,
    *,
    same_prompt: bool,
    measure: dict[str, Any] | None,
    models: list[str] | None = None,
) -> None:
    """Refuse (raise ``BaselineError``) when the comparison would not be valid.

    With ``models`` (already applied to ``runset`` by ``select_models``) the models
    digest is recomputed from the baseline's stored entries for that selection;
    without it the stored digest is used, as before."""
    fps = base["fingerprints"]
    new = runset.fingerprints()
    if new["scenarios"] != fps["scenarios"]:
        raise BaselineError(
            "refusing to compare: the scenarios fingerprints differ from the baseline's"
        )
    expected_models = baseline_models_fingerprint(base, models) if models else fps["models"]
    if new["models"] != expected_models:
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
    line = f"{st.passes}/{st.counted}"
    if st.not_exposed:  # DD6: the cell is measured only on the runs that were exposed
        line += f" (exposed {st.counted} of {st.counted + st.not_exposed} runs)"
    if st.saved_runs is not None:  # DD14: how many runs actually exercised the check
        line += f" (non-vacuous: {st.saved_runs} of {st.counted} runs {st.exercised})"
    return line


def compare(
    base: dict[str, Any],
    runset: RunSet,
    measure: dict[str, Any],
    models: list[str] | None = None,
) -> Comparison:
    """Compare ``runset`` with ``base``. ``models`` (a ``select_models`` selection;
    ``runset`` is already filtered) limits the cell loop to those models."""
    schema = base.get("schema", 1)
    if schema == 2 and measure.get("schema", 1) != 2:
        raise BaselineError(
            "the baseline is schema 2 but the measurement is schema 1 (an old run directory's "
            "measure.json): re-run measure-prompt"
        )
    stats = aggregate(runset.records)
    out = Comparison(models=list(models) if models else None)
    for model, counts in sorted(exposure_counts(runset.records).items()):
        out.notes.append(
            f"tool exposure {model}: exposed {counts['exposed']}, "
            f"not exposed {counts['not_exposed']}, no record {counts['no_record']}"
        )
    out.notes.extend(decided_mismatches(runset.records, measure))
    for model, cells in sorted(base["cells"].items()):
        if models and model not in models:
            continue
        for cell, b in sorted(cells.items()):
            st = stats.get(model, {}).get(cell)
            bar = b["bar"]
            kind = bar["kind"]
            target = f"{cell}"
            if kind == "report":  # reported, never gated: always a PASS row
                if st is None or st.counted == 0:
                    detail = "reported, never gated (no exposed runs)"
                else:
                    rate = st.passes / st.counted
                    detail = f"{_stat_line(st)} rate {rate:.3f} (reported, never gated)"
                out.rows.append(Row(target, model, kind, True, None, detail))
                continue
            if st is None or st.counted + st.not_exposed == 0:
                out.rows.append(Row(target, model, kind, False, HARD, "no counted runs"))
                continue
            base_exposed = b["counted"] > 0
            if st.counted == 0:
                if base_exposed:
                    out.rows.append(
                        Row(
                            target,
                            model,
                            kind,
                            False,
                            HARD,
                            "the cell went unmeasured: "
                            f"0 of {st.not_exposed} runs were exposed (baseline "
                            f"{b['passes']}/{b['counted']})",
                        )
                    )
                else:
                    out.rows.append(
                        Row(target, model, kind, True, None, "not exposed (in the baseline too)")
                    )
                continue
            if not base_exposed:
                out.rows.append(
                    Row(
                        target,
                        model,
                        kind,
                        True,
                        None,
                        f"{_stat_line(st)} rate {st.passes / st.counted:.3f} "
                        "(ungated: baseline not exposed)",
                    )
                )
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
    if schema == 2:
        # Schema 2 gates exactly its two targets per configuration (prompt text, tool schemas):
        # no extra_size_gates, which serve the schema-1 platform-total gates.
        for name, tgt in sorted(base["size_targets"].items()):
            cfg = measure["configs"].get(tgt["config"])
            if cfg is None:
                raise BaselineError(
                    f"the measurement has no {tgt['config']} configuration: re-run measure-prompt"
                )
            now = cfg["totals"][tgt["metric"]]
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
    for name, tgt in sorted(base["size_targets"].items()):
        if name == "all-on":
            continue  # reported by the DD13 all-on gate below (same maximum, same config)
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
    for gate in extra_size_gates(base):
        cfg = measure["configs"].get(gate["config"])
        if cfg is None:
            raise BaselineError(
                f"the measurement has no {gate['config']} configuration: re-run measure-prompt"
            )
        now = cfg["totals"][gate["metric"]]
        ok = now <= gate["max"]
        out.rows.append(
            Row(
                f"size:{gate['name']}",
                "-",
                "size",
                ok,
                None if ok else HARD,
                f"{gate['metric']} {now} tokens vs max {gate['max']} ({gate['why']})",
            )
        )
    return out


def render_comparison(cmp: Comparison) -> str:
    lines: list[str] = []
    if cmp.models:
        lines.append(
            f"SUBSET compare: models {', '.join(cmp.models)} only; the baseline's other "
            "models are not compared. The model-independent size:* gates still run."
        )
    lines += cmp.notes
    lines += [f"{'result':18} {'class':8} {'model':10} {'cell':26} detail"]
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
