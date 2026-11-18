"""Merging run directories, per-cell aggregation and ``report.md`` (DD16).

A *cell* is a scored behaviour for one model; one run can score several cells
(``kb-find`` and ``kb-answer`` come from the same runs). Only counted runs
(``pass``/``fail``) enter a pass rate; ``cut-short`` and ``error`` runs are
excluded and reported beside it, and a cell whose exclusions exceed 10% of its
runs, or which has no counted run, is ``incomplete``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals import outcomes as oc
from evals.fingerprint import models_fingerprint
from evals.stats import wilson

INCOMPLETE_ABOVE = 0.10
NOTES_FLAG_CHECK = "notes_from_untrusted_flagged"
ROUTINE_FLAG_CHECK = "routine_flagged_if_scheduled"


class MergeError(Exception):
    """Run directories cannot be merged or read. The message is one line."""


@dataclass
class CellStat:
    cell: str
    model: str
    klass: str
    passes: int = 0
    counted: int = 0
    excluded: int = 0
    total: int = 0
    # Counted runs that were not exposed to what the cell measures (``exposed_if``, DD6): the
    # cell's value is ``None``, neither a pass nor a fail, and outside ``counted``.
    not_exposed: int = 0
    phrasing: dict[str, list[int]] = field(default_factory=dict)  # index -> [passes, counted]
    facts: dict[str, list[int]] = field(default_factory=dict)
    saved_runs: int | None = None  # runs that saved a note (notes_from_untrusted_flagged cells)
    exercised: str = "saved a note"  # what a non-vacuous run did (routine cells: scheduled one)

    @property
    def rate(self) -> float | None:
        return self.passes / self.counted if self.counted else None

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson(self.passes, self.counted) if self.counted else None

    @property
    def excluded_rate(self) -> float:
        return self.excluded / self.total if self.total else 0.0

    @property
    def incomplete(self) -> bool:
        # A cell with zero exposed runs is not incomplete: it has nothing to measure.
        return self.counted + self.not_exposed == 0 or self.excluded_rate > INCOMPLETE_ABOVE

    def to_dict(self) -> dict[str, Any]:
        iv = self.interval
        return {
            "class": self.klass,
            "passes": self.passes,
            "counted": self.counted,
            "excluded": self.excluded,
            "not_exposed": self.not_exposed,
            "total": self.total,
            "rate": self.rate,
            "wilson": list(iv) if iv else None,
            "excluded_rate": round(self.excluded_rate, 6),
            "incomplete": self.incomplete,
            "phrasing": self.phrasing,
            "facts": self.facts,
            "saved_runs": self.saved_runs,
        }


@dataclass
class RunSet:
    """Final records merged from one or more run directories."""

    dirs: list[Path]
    records: list[dict[str, Any]]
    scenarios_fp: str | None
    presets: dict[str, dict[str, Any]]
    prompt_fp: str | None = None  # from a measure.json beside the runs, if any
    measure: dict[str, Any] | None = None

    def models(self) -> list[str]:
        return sorted({r["model"] for r in self.records})

    def models_fingerprint(self) -> str:
        effective: dict[str, Any] = {}
        info: dict[str, Any] = {}
        for rec in sorted(self.records, key=lambda r: (r["scenario"], r["variant"])):
            effective.setdefault(rec["model"], rec.get("effective") or {})
            info.setdefault(rec["model"], rec.get("model_info") or {})
        presets = {m: self.presets.get(m, {}) for m in self.models()}
        return models_fingerprint(presets, effective, info)

    def fingerprints(self) -> dict[str, str | None]:
        return {
            "prompt": self.prompt_fp,
            "scenarios": self.scenarios_fp,
            "models": self.models_fingerprint(),
        }


def load_measure(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MergeError(f"{path}: cannot read the measurement file: {exc}") from exc


def load_runs(run_dirs: list[Path], measure_path: Path | None = None) -> RunSet:
    """Merge run directories. Refuses differing ``scenarios``/``prompt`` fingerprints."""
    if not run_dirs:
        raise MergeError("no run directories given")
    records: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str], Path] = {}
    scen: dict[str, Path] = {}
    prompts: dict[str, Path] = {}
    presets: dict[str, dict[str, Any]] = {}
    measure: dict[str, Any] | None = None
    for d in run_dirs:
        if not (d / "results.jsonl").is_file():
            raise MergeError(f"{d}: not a run directory (no results.jsonl)")
        store = oc.ResultStore(d, None)
        for key, rec in store.finals().items():
            if key in seen:
                raise MergeError(f"run {'/'.join(key)} appears in both {seen[key]} and {d}")
            seen[key] = d
            records.append(rec)
        fp_path = d / "fingerprints.json"
        if fp_path.is_file():
            fp = json.loads(fp_path.read_text(encoding="utf-8"))
            if fp.get("scenarios"):
                scen.setdefault(fp["scenarios"], d)
            for name, body in fp.get("presets", {}).items():
                if name in presets and presets[name] != body:
                    raise MergeError(f"model preset {name!r} differs between run directories")
                presets[name] = body
        else:
            raise MergeError(f"{d}: no fingerprints.json (not written by `evals run`)")
        if measure_path is None and not (d / "measure.json").is_file():
            raise MergeError(
                f"{d}: no measure.json (run `python -m evals measure-prompt --json "
                f"{d}/measure.json` for the prompt these runs used, or pass --measure)"
            )
        if (d / "measure.json").is_file() and measure_path is None:
            m = load_measure(d / "measure.json")
            prompts.setdefault(m["fingerprints"]["prompt"], d)
            measure = measure or m
    if len(scen) > 1:
        raise MergeError("scenarios fingerprints differ between run directories")
    if len(prompts) > 1:
        raise MergeError("prompt fingerprints differ between run directories")
    if measure_path is not None:
        measure = load_measure(measure_path)
    return RunSet(
        dirs=list(run_dirs),
        records=records,
        scenarios_fp=next(iter(scen), None),
        presets=presets,
        prompt_fp=measure["fingerprints"]["prompt"] if measure else None,
        measure=measure,
    )


def _bump(table: dict[str, list[int]], key: int | None, passed: bool) -> None:
    row = table.setdefault(str(key), [0, 0])
    row[0] += int(passed)
    row[1] += 1


def aggregate(records: list[dict[str, Any]]) -> dict[str, dict[str, CellStat]]:
    """``{model: {cell: CellStat}}`` from final records."""
    out: dict[str, dict[str, CellStat]] = {}
    for rec in records:
        names = rec.get("cell_names") or [rec["scenario"]]
        classes = rec.get("cell_classes") or {}
        for cell in names:
            st = out.setdefault(rec["model"], {}).get(cell)
            if st is None:
                st = CellStat(cell, rec["model"], classes.get(cell, rec.get("class", "hold")))
                out[rec["model"]][cell] = st
            st.total += 1
            if not rec.get("counted"):
                st.excluded += 1
                continue
            cells = rec.get("cells") or {}
            if cell in cells and cells[cell] is None:  # a missing key stays distinct (a fail)
                st.not_exposed += 1
                continue
            passed = bool(cells.get(cell, False))
            st.counted += 1
            st.passes += int(passed)
            _bump(st.phrasing, rec.get("phrasing_index"), passed)
            _bump(st.facts, rec.get("fact_index"), passed)
            for chk in rec.get("checks", []):
                if chk.get("name") in (NOTES_FLAG_CHECK, ROUTINE_FLAG_CHECK) and (
                    chk.get("cell") == cell
                ):
                    extra = chk.get("extra") or {}
                    if chk["name"] == ROUTINE_FLAG_CHECK:
                        st.exercised = "scheduled a routine"
                    saved = int(extra.get("scheduled" if "scheduled" in extra else "saved", 0))
                    st.saved_runs = (st.saved_runs or 0) + (1 if saved > 0 else 0)
    return out


def exposure_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per model, how many runs' agents had every tool schema up front (``exposed``), had
    discovery (``not exposed``) or carry no exposure record (``no record``)."""
    out: dict[str, dict[str, int]] = {}
    for rec in records:
        row = out.setdefault(rec["model"], {"exposed": 0, "not_exposed": 0, "no_record": 0})
        exp = rec.get("exposure")
        if not exp:
            row["no_record"] += 1
        elif exp.get("decided"):
            row["exposed"] += 1
        else:
            row["not_exposed"] += 1
    return out


def decided_mismatches(records: list[dict[str, Any]], measure: dict[str, Any] | None) -> list[str]:
    """One line per model and scenario whose runs' exposure ``decided`` differs from the
    measurement's ``all-on`` configuration (``tools_off`` scenarios excluded). A missing record
    reads as ``None``, so a measurement and runs that both carry none never differ."""
    if not measure:
        return []
    cfg = (measure.get("configs") or {}).get("all-on") or {}
    if not cfg:
        return []  # a measure directory of its own (the GleepGlorp set's) has no all-on agent
    want = (cfg.get("exposure") or {}).get("decided")
    seen: dict[tuple[str, str], set[bool | None]] = {}
    for rec in records:
        if rec.get("tools_off"):
            continue
        got = (rec.get("exposure") or {}).get("decided")
        seen.setdefault((rec["model"], rec["scenario"]), set()).add(got)
    lines = []
    for (model, scenario), values in sorted(seen.items()):
        if values != {want}:
            shown = ", ".join(sorted(str(v) for v in values))
            lines.append(
                f"WARNING: {model} / {scenario}: runs decided {shown} but the measurement's "
                f"all-on agent decided {want}"
            )
    return lines


def _exposure_line(counts: dict[str, int]) -> str:
    return (
        f"Tool exposure: exposed {counts['exposed']}, not exposed {counts['not_exposed']}, "
        f"no record {counts['no_record']}"
    )


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _counts(table: dict[str, list[int]]) -> str:
    return " ".join(f"{k}:{v[0]}/{v[1]}" for k, v in sorted(table.items(), key=lambda kv: kv[0]))


def _noun(st: CellStat) -> str:
    return "scheduled" if st.exercised == "scheduled a routine" else "saved"


def cell_note(st: CellStat) -> str:
    notes = []
    if st.counted == 0 and st.not_exposed:
        notes.append("not exposed")
    elif st.counted == 0:
        notes.append("n/a: no counted runs")
    elif st.not_exposed:
        notes.append(f"exposed {st.counted} of {st.counted + st.not_exposed} runs")
    if st.klass == "report":
        notes.append("reported, never gated")
    if st.incomplete:
        notes.append("incomplete")
    if st.saved_runs is not None and st.counted:
        if st.saved_runs == 0 and st.passes == st.counted:
            notes.append(f"pass (vacuous: 0 of {st.counted} {_noun(st)})")
        else:
            notes.append(f"non-vacuous: {st.saved_runs} of {st.counted} runs {st.exercised}")
    return "; ".join(notes)


def render_report(runset: RunSet) -> str:
    stats = aggregate(runset.records)
    lines = ["# Prompt evals report", ""]
    fps = runset.fingerprints()
    lines.append("Run directories: " + ", ".join(d.name for d in runset.dirs))
    for k in ("prompt", "scenarios", "models"):
        lines.append(f"- {k} fingerprint: `{fps[k] or 'not measured'}`")
    lines.append("")
    exposure = exposure_counts(runset.records)
    warnings = decided_mismatches(runset.records, runset.measure)
    if warnings:
        lines += [*warnings, ""]
    for model in sorted(stats):
        lines += [f"## {model}", ""]
        if model in exposure:
            lines += [_exposure_line(exposure[model]), ""]
        lines.append("| cell | class | passes / counted | rate | Wilson 95% | excluded | note |")
        lines.append("|---|---|---|---|---|---|---|")
        for cell, st in sorted(stats[model].items()):
            iv = st.interval
            interval = f"{_pct(iv[0])} to {_pct(iv[1])}" if iv else "n/a"
            lines.append(
                f"| {cell} | {st.klass} | {st.passes} / {st.counted} | {_pct(st.rate)} | "
                f"{interval} | {st.excluded} ({_pct(st.excluded_rate)}) | {cell_note(st)} |"
            )
        lines += ["", "Per-phrasing and per-fact counts (informational, not a gate):", ""]
        for cell, st in sorted(stats[model].items()):
            by_phrasing = _counts(st.phrasing) or "n/a"
            by_fact = _counts(st.facts) or "n/a"
            lines.append(f"- {cell}: phrasing {by_phrasing}; fact {by_fact}")
        lines.append("")
    lines += render_parts(runset.measure)
    return "\n".join(lines).rstrip() + "\n"


def render_parts(measure: dict[str, Any] | None) -> list[str]:
    lines = ["## Platform text by part", ""]
    if not measure:
        return lines + [
            "Not measured: run `python -m evals measure-prompt --json <run-dir>/measure.json`.",
            "",
        ]
    lines.append(f"Counter: {measure['counter']}")
    for name, cfg in measure["configs"].items():
        t = cfg["totals"]
        extra = ""
        if "tools_full" in t:
            extra = f", prompt text {t.get('prompt_text')}, tools full {t['tools_full']}"
        lines += [
            "",
            f"### {name} (prompt sections {t['prompt_sections']}, tools {t['tools']}, "
            f"platform total {t['platform']}{extra})",
            "",
            "| part | group | tokens |",
            "|---|---|---|",
        ]
        lines += [f"| {p['name']} | {p['group']} | {p['tokens']} |" for p in cfg["parts"]]
    lines.append("")
    return lines


def write_report(runset: RunSet, out: Path | None = None) -> Path:
    path = out or (runset.dirs[0] / "report.md")
    path.write_text(render_report(runset), encoding="utf-8")
    return path
