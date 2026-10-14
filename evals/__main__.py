"""``python -m evals run ...``: the command line."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from evals import baseline as bl
from evals import report as rp
from evals import runner, tokens


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals", description="Prompt evals runner.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run scenarios against models in a scratch environment")
    run.add_argument("--models", type=_csv, help="comma-separated model presets (default: all)")
    run.add_argument("--scenarios", type=_csv, help="comma-separated scenario ids (default: all)")
    run.add_argument(
        "--scenarios-dir",
        type=Path,
        default=runner.DEFAULT_SCENARIOS_DIR,
        help="directory of scenario .toml files",
    )
    run.add_argument(
        "--fixtures-dir",
        type=Path,
        help="fixtures root with web/ and kb/ (default: <scenarios-dir>/../fixtures)",
    )
    run.add_argument(
        "--n", type=int, default=runner.DEFAULT_N, help="variants per scenario and model"
    )
    group = run.add_mutually_exclusive_group()
    group.add_argument("--run-dir", type=Path, help="run directory (default: evals/runs/<time>)")
    group.add_argument(
        "--resume", type=Path, help="resume a run directory: skip counted runs, redo the rest"
    )
    run.add_argument(
        "--plan-token-file",
        dest="token_file",
        type=Path,
        help="file holding the plan token (default: ~/.config/the-one-evals/plan-token)",
    )
    run.add_argument("--models-file", type=Path, help="alternative presets file")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned runs and LLM call count; build no agent",
    )

    mp = sub.add_parser(
        "measure-prompt",
        help="print the platform text's size by part for the bare, all-on and tool-free agents",
    )
    mp.add_argument("--with-model-counts", action="store_true", help="add each model's cold count")
    mp.add_argument("--models", type=_csv, help="comma-separated model presets (default: all)")
    mp.add_argument("--models-file", type=Path, help="alternative presets file")
    mp.add_argument("--plan-token-file", dest="token_file", type=Path, help="plan token file")
    mp.add_argument("--json", dest="json_out", type=Path, help="also write the measurement here")
    mp.add_argument(
        "--run-dir", type=Path, help="scratch directory (default: evals/runs/measure-<pid>)"
    )

    for name, help_ in (
        ("report", "merge run directories and write report.md"),
        ("baseline", "write evals/baselines/<name>.json from run directories"),
        ("compare", "compare run directories against a baseline"),
    ):
        sp = sub.add_parser(name, help=help_)
        if name == "baseline":
            sp.add_argument("name", help="baseline name (file name without .json)")
        if name == "compare":
            sp.add_argument("--baseline", type=Path, required=True, help="baseline JSON file")
            sp.add_argument(
                "--same-prompt",
                action="store_true",
                help="mark a re-measurement of the same prompt",
            )
        sp.add_argument("run_dirs", nargs="+", type=Path, metavar="run-dir")
        sp.add_argument(
            "--measure",
            type=Path,
            help="measure-prompt --json file (default: measure.json in the first run directory"
            + ("; else measured now)" if name == "compare" else ")"),
        )
        if name == "report":
            sp.add_argument("--out", type=Path, help="report path (default: <run-dir>/report.md)")
        if name == "baseline":
            sp.add_argument("--baselines-dir", type=Path, help="default: evals/baselines")

    db = sub.add_parser("derive-bars", help="(re)write the bars and size targets into a baseline")
    db.add_argument("baseline", type=Path, help="baseline JSON file")
    return parser


def _err(message: str) -> int:
    print(message, file=sys.stderr, flush=True)
    return 2


def _cmd_measure(args: argparse.Namespace) -> int:
    from evals.env import EvalRefusalError
    from evals.models import PresetError
    from evals.scenario import ScenarioError

    opts = tokens.MeasureOptions(
        with_model_counts=args.with_model_counts,
        models=args.models,
        models_file=args.models_file,
        token_file=args.token_file,
        json_out=args.json_out,
        run_dir=args.run_dir,
    )
    try:
        print("building the three agents (no model call)...", file=sys.stderr, flush=True)
        doc = asyncio.run(tokens.measure_prompt(opts))
    except tokens.TiktokenMissingError as exc:
        return _err(str(exc))
    except (EvalRefusalError, PresetError, ScenarioError) as exc:
        return _err(str(exc))
    print(tokens.render_tables(doc), end="")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    runset = rp.load_runs(args.run_dirs, args.measure)
    path = rp.write_report(runset, args.out)
    print(f"wrote {path}", file=sys.stderr, flush=True)
    print(rp.render_report(runset), end="")
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    runset = rp.load_runs(args.run_dirs, args.measure)
    doc = bl.build_baseline(args.name, runset)
    path = bl.write_baseline(doc, bl.baseline_path(args.name, args.baselines_dir))
    print(f"wrote {path}", file=sys.stderr, flush=True)
    return 0


def _cmd_derive(args: argparse.Namespace) -> int:
    doc = bl.derive_bars(bl.read_baseline(args.baseline))
    bl.write_baseline(doc, args.baseline)
    for model, cells in sorted(doc["cells"].items()):
        for cell, c in sorted(cells.items()):
            bar = c["bar"]
            rate = "n/a" if bar["bar_rate"] is None else f"{bar['bar_rate']:.3f}"
            print(f"{model:10} {cell:26} {bar['kind']:8} bar {rate}  ({bar['rule']})")
    for name, t in sorted(doc["size_targets"].items()):
        print(f"size:{name}  {t['metric']} max {t['max']} of today's {t['today']}")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    runset = rp.load_runs(args.run_dirs, args.measure)
    base = bl.read_baseline(args.baseline)
    measure = runset.measure
    if measure is None:
        print("measuring the current prompt (no model call)...", file=sys.stderr, flush=True)
        measure = asyncio.run(tokens.measure_prompt(tokens.MeasureOptions()))
        runset.measure, runset.prompt_fp = measure, measure["fingerprints"]["prompt"]
    bl.check_comparable(base, runset, same_prompt=args.same_prompt, measure=measure)
    cmp = bl.compare(base, runset, measure)
    print(bl.render_comparison(cmp), end="")
    return cmp.exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (rp.MergeError, bl.BaselineError) as exc:
        return _err(str(exc))


def _dispatch(args: argparse.Namespace) -> int:
    handlers = {
        "measure-prompt": _cmd_measure,
        "report": _cmd_report,
        "baseline": _cmd_baseline,
        "derive-bars": _cmd_derive,
        "compare": _cmd_compare,
    }
    if args.command in handlers:
        return handlers[args.command](args)
    opts = runner.RunOptions(
        models=args.models,
        scenarios=args.scenarios,
        scenarios_dir=args.scenarios_dir,
        fixtures_dir=args.fixtures_dir,
        n=args.n,
        run_dir=args.run_dir,
        resume=args.resume,
        token_file=args.token_file,
        models_file=args.models_file,
        dry_run=args.dry_run,
    )
    return asyncio.run(runner.run_invocation(opts))


if __name__ == "__main__":
    sys.exit(main())
