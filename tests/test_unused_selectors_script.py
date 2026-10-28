"""Smoke test for scripts/unused_selectors.py over a tiny fixture tree."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "unused_selectors.py"


def _load():
    spec = importlib.util.spec_from_file_location("unused_selectors", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reports_unused_dynamic_and_skips_used(tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "css").mkdir(parents=True)
    (static / "js").mkdir()
    (tmp_path / "tests").mkdir()
    sheet = static / "css" / "a.css"
    sheet.write_text(
        "/* .commented-out {} */\n"
        ".used-one { margin: 0.5em; }\n"
        ".orphan-one:not(.used-one) { color: red; }\n"
        ".badge--fancy { color: blue; }\n"
        "@media (min-width: 10px) { .used-two { color: red; } }\n"
    )
    (static / "js" / "x.js").write_text(
        "// .orphan-one in a comment does not count\n"
        "el.className = 'used-one';\n"
        "el.className = 'badge badge--' + kind;\n"
        "el.className = 'used-two';\n"
    )
    mod = _load()
    unused, dynamic = mod.find_unused([sheet], static=static, tests=tmp_path / "tests")[sheet]
    assert unused == ["orphan-one"]
    assert dynamic == ["badge--fancy"]


def test_testids_and_behavior_run_logs_are_not_users(tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "css").mkdir(parents=True)
    (static / "js").mkdir()
    runs = tmp_path / "tests" / "behavior" / "spec" / "runs"
    runs.mkdir(parents=True)
    sheet = static / "css" / "a.css"
    sheet.write_text(".only-a-testid { x: 1; }\n.only-in-a-log { x: 1; }\n.banner-warn { x: 1; }\n")
    (static / "js" / "x.js").write_text(
        "el.setAttribute('data-testid', 'y'); // data-testid=\"only-a-testid\"\n"
    )
    (tmp_path / "tests" / "t.py").write_text("loc('[data-testid=\"only-a-testid\"]')\n")
    (runs / "r.md").write_text("saw .only-in-a-log on screen\n")
    mod = _load()
    unused, dynamic = mod.find_unused([sheet], static=static, tests=tmp_path / "tests")[sheet]
    assert unused == ["only-a-testid", "only-in-a-log"]
    assert dynamic == ["banner-warn"]


def test_cli_runs_and_exits_zero() -> None:
    css = "the_one/interfaces/web/static/css/studio.css"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), css],
        cwd=SCRIPT.parent.parent,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "unused (" in proc.stdout
