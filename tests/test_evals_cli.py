"""The measurement subcommands, the run record additions and the developer surface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _evals_helpers as h
import pytest
from _evals_helpers import make_tree, run, script_hook, simple_scenario

from evals import __main__ as cli
from evals import scripted, tokens

evals_isolation = h.evals_isolation
ROOT = Path(__file__).resolve().parent.parent
M = "haiku"
CELLS = {
    ("hold-ok", M): ("hold", 18, 2, 0),
    ("imp-low", M): ("improve", 10, 10, 0),
    ("safe-19", M): ("safety", 19, 1, 0),
}


def test_run_help_and_subcommands_listed():
    out = subprocess.run(
        [sys.executable, "-m", "evals", "--help"], capture_output=True, text=True, cwd=ROOT
    ).stdout
    for name in (
        "run",
        "measure-prompt",
        "report",
        "baseline",
        "derive-bars",
        "compare",
        "selftest",
    ):
        assert name in out
    run_help = subprocess.run(
        [sys.executable, "-m", "evals", "run", "--help"], capture_output=True, text=True, cwd=ROOT
    )
    assert run_help.returncode == 0 and "--dry-run" in run_help.stdout


def test_make_eval_target_and_lint_paths():
    dry = subprocess.run(
        ["make", "-n", "eval", "ARGS=run --help"], capture_output=True, text=True, cwd=ROOT
    ).stdout
    assert "-m evals run --help" in dry
    helptext = subprocess.run(["make", "help"], capture_output=True, text=True, cwd=ROOT).stdout
    assert "eval" in helptext
    for path in ("Makefile", "ci/tasks/lint.yml", "CLAUDE.md"):
        assert "scripts/ evals/" in (ROOT / path).read_text(), path


def test_evals_extra_is_pinned_and_locked():
    text = (ROOT / "pyproject.toml").read_text()
    assert 'evals = ["tiktoken>=0.14,<0.15"]' in text
    assert 'name = "tiktoken"' in (ROOT / "uv.lock").read_text()


def test_tiktoken_is_only_imported_lazily():
    for mod in (ROOT / "evals").glob("*.py"):
        for line in mod.read_text().splitlines():
            if line.startswith(("import tiktoken", "from tiktoken")):
                pytest.fail(f"{mod.name}: module-level tiktoken import")


def test_measure_prompt_without_tiktoken_exits_with_one_line_hint(monkeypatch, capsys):
    def boom(*a, **k):
        raise tokens.TiktokenMissingError(
            'tiktoken is not installed: run pip install -e ".[evals]"'
        )

    monkeypatch.setattr(tokens, "TiktokenCounter", boom)
    assert cli.main(["measure-prompt"]) == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert ".[evals]" in err[-1] and "tiktoken" in err[-1]


def test_derive_bars_command_rewrites_the_file(tmp_path, capsys):
    d = h.make_run_dir(tmp_path, "r", CELLS, measure=h.synth_measure())
    out = tmp_path / "bl"
    assert cli.main(["baseline", "t", str(d), "--baselines-dir", str(out)]) == 0
    path = out / "t.json"
    doc = json.loads(path.read_text())
    for cells in doc["cells"].values():
        for c in cells.values():
            c.pop("bar")
    doc.pop("size_targets")
    path.write_text(json.dumps(doc))
    capsys.readouterr()
    assert cli.main(["derive-bars", str(path)]) == 0
    printed = capsys.readouterr().out
    assert "safe-19" in printed and "size:bare" in printed
    back = json.loads(path.read_text())
    assert back["cells"][M]["imp-low"]["bar"]["bar_rate"] == pytest.approx(0.8)
    assert back["size_targets"]["bare"]["max"] == 60


def test_report_command_writes_report_md(tmp_path, capsys):
    d = h.make_run_dir(tmp_path, "r", CELLS, measure=h.synth_measure())
    assert cli.main(["report", str(d)]) == 0
    assert (d / "report.md").is_file()
    assert "| imp-low | improve | 10 / 20 |" in capsys.readouterr().out


def test_compare_command_exit_codes_and_refusals(tmp_path, capsys):
    d = h.make_run_dir(tmp_path, "r", CELLS, measure=h.synth_measure())
    out = tmp_path / "bl"
    assert cli.main(["baseline", "t", str(d), "--baselines-dir", str(out)]) == 0
    base = str(out / "t.json")
    # unchanged prompt without --same-prompt: refused, exit 2
    assert cli.main(["compare", "--baseline", base, str(d)]) == 2
    assert "prompt fingerprint equals" in capsys.readouterr().err
    # a self-compare fails its hard gates (19/20 safety, bare size): exit 1
    assert cli.main(["compare", "--baseline", base, "--same-prompt", str(d)]) == 1
    text = capsys.readouterr().out
    assert "FAIL [hard]" in text and "FAIL [best-effort]" in text
    # an improved run on a changed prompt passes every gate: exit 0
    better = {k: (v[0], 20, 0, 0) for k, v in CELLS.items()}
    m = h.synth_measure(bare=50, all_on=400, prompt_fp="p2")
    d2 = h.make_run_dir(tmp_path, "r2", better, measure=m)
    assert cli.main(["compare", "--baseline", base, str(d2)]) == 0
    assert "hard failures: 0" in capsys.readouterr().out


def test_baseline_refuses_incomplete_cells_via_cli(tmp_path, capsys):
    d = h.make_run_dir(tmp_path, "r", {("c", M): ("hold", 10, 5, 5)}, measure=h.synth_measure())
    assert cli.main(["baseline", "t", str(d), "--baselines-dir", str(tmp_path / "bl")]) == 2
    assert "incomplete" in capsys.readouterr().err
    assert not (tmp_path / "bl" / "t.json").exists()


# ── run records feed the report ───────────────────────────────────────────

TWO_CELLS = """
[[conversations]]
turns = ["say hello"]

[[checks]]
name = "reply_matches"
pattern = "hello"
cell = "alpha"

[[checks]]
name = "reply_matches"
pattern = "nomatch"
cell = "beta"
class = "improve"
"""


async def test_run_records_cells_classes_and_fingerprints(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(
        tmp,
        {"two": 'id = "two"\nclass = "hold"\n' + TWO_CELLS},
    )
    code, run_dir = await run(tmp, sdir, script_hook(scripted.text("hello there")))
    assert code == 0
    rec = json.loads((run_dir / "results.jsonl").read_text().splitlines()[0])
    assert rec["cell_names"] == ["alpha", "beta"]
    assert rec["cell_classes"] == {"alpha": "hold", "beta": "improve"}
    assert rec["cells"] == {"alpha": True, "beta": False}
    fps = json.loads((run_dir / "fingerprints.json").read_text())
    assert len(fps["scenarios"]) == 64
    assert fps["presets"]["gpt-oss"]["model"] == "gpt-oss:20b"
    # the whole record chain feeds the report
    from evals import report as rp

    (run_dir / "measure.json").write_text(json.dumps(h.synth_measure()), encoding="utf-8")
    rs = rp.load_runs([run_dir])
    stats = rp.aggregate(rs.records)["gpt-oss"]
    assert (stats["alpha"].passes, stats["beta"].passes) == (1, 0)
    assert stats["beta"].klass == "improve"


async def test_resume_refuses_changed_scenarios(evals_isolation):
    tmp = evals_isolation
    sdir = make_tree(tmp, {"demo": simple_scenario()})
    code, run_dir = await run(tmp, sdir, script_hook(scripted.text("hello there")))
    assert code == 0
    (sdir / "demo.toml").write_text(simple_scenario() + "\n# edited\n", encoding="utf-8")
    code2, _ = await run(
        tmp, sdir, script_hook(scripted.text("hello there")), run_dir=None, resume=run_dir
    )
    assert code2 == 2


def test_derive_bars_size_ratio_flag_reaches_the_file(tmp_path, capsys):
    d = h.make_run_dir(tmp_path, "r", CELLS)
    out = tmp_path / "bl"
    assert cli.main(["baseline", "t", str(d), "--baselines-dir", str(out)]) == 0
    path = out / "t.json"
    assert cli.main(["derive-bars", str(path), "--size-ratio", "1.0"]) == 0
    assert json.loads(path.read_text())["size_targets"]["bare"]["max"] == 100
    assert cli.main(["derive-bars", str(path)]) == 0
    assert json.loads(path.read_text())["size_targets"]["bare"]["max"] == 60


def test_compare_and_report_refuse_a_directory_without_measure_json(tmp_path, capsys):
    d = h.make_run_dir(tmp_path, "r", CELLS, measure=False)
    good = h.make_run_dir(tmp_path, "g", CELLS)
    out = tmp_path / "bl"
    assert cli.main(["baseline", "t", str(good), "--baselines-dir", str(out)]) == 0
    capsys.readouterr()
    base = str(out / "t.json")
    for argv in (["compare", "--baseline", base, str(d)], ["report", str(d)]):
        assert cli.main(argv) == 2
        err = capsys.readouterr().err.strip()
        assert "\n" not in err and str(d) in err and "no measure.json" in err


def test_compare_warns_on_stderr_whenever_measure_is_given(tmp_path, capsys):
    good = h.make_run_dir(tmp_path, "g", CELLS)
    out = tmp_path / "bl"
    assert cli.main(["baseline", "t", str(good), "--baselines-dir", str(out)]) == 0
    m = tmp_path / "m.json"
    m.write_text(json.dumps(h.synth_measure(bare=50, all_on=400, prompt_fp="p2")))
    bare_dir = h.make_run_dir(tmp_path, "nm", CELLS, measure=False)
    capsys.readouterr()
    cli.main(["compare", "--baseline", str(out / "t.json"), "--measure", str(m), str(bare_dir)])
    err = capsys.readouterr().err
    assert err.startswith("warning: --measure") and "overrides" in err
    # without --measure there is no warning
    cli.main(["compare", "--baseline", str(out / "t.json"), str(good)])
    assert "warning" not in capsys.readouterr().err


def test_mixed_prompt_fingerprints_across_directories_are_refused(tmp_path):
    from evals import report as rp

    a = h.make_run_dir(tmp_path, "a", {("c", M): ("hold", 5, 0, 0)}, measure=h.synth_measure())
    b = h.make_run_dir(
        tmp_path, "b", {("d", M): ("hold", 5, 0, 0)}, measure=h.synth_measure(prompt_fp="p2")
    )
    with pytest.raises(rp.MergeError, match="prompt fingerprints differ"):
        rp.load_runs([a, b])
