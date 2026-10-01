"""Unit tests for the WebKitGTK probe's production-safety refusals (M25 F1 L1)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "webkitgtk_probe", Path(__file__).parent.parent / "scripts" / "webkitgtk_probe.py"
)
probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8484/", "http://localhost:8484/#admin", "https://x.test:8484"]
)
def test_refuses_production_port(url: str, tmp_path: Path) -> None:
    with pytest.raises(probe.ProbeError, match="8484"):
        probe.check_safety(url, tmp_path / "scratch", default_dir=tmp_path / "default")


def test_refuses_default_data_dir(tmp_path: Path) -> None:
    default = tmp_path / "default"
    default.mkdir()
    with pytest.raises(probe.ProbeError, match="default data directory"):
        probe.check_safety("http://127.0.0.1:8485/", default / ".." / "default", default)


def test_accepts_dev_instance(tmp_path: Path) -> None:
    probe.check_safety("http://127.0.0.1:8485/", tmp_path / "scratch", tmp_path / "default")


def test_setup_script_is_repeatable_and_ordered(tmp_path: Path) -> None:
    a = tmp_path / "a.js"
    b = tmp_path / "b.js"
    a.write_text("var x = 1;")
    b.write_text("var y = 2;")
    args = probe.parse_args(
        [
            "--url",
            "http://127.0.0.1:8485/",
            "--data-dir",
            "/x",
            "--setup-script",
            str(a),
            "--setup-script",
            str(b),
        ]
    )
    assert args.setup_script == [a, b]
    wrapped = probe.load_setup_scripts(args.setup_script)
    assert len(wrapped) == 2 and "var x = 1;" in wrapped[0] and "var y = 2;" in wrapped[1]
    assert all(w.rstrip().endswith("return true;\n})()") for w in wrapped)  # ends in true


def test_setup_script_default_is_empty() -> None:
    args = probe.parse_args(["--url", "http://127.0.0.1:8485/", "--data-dir", "/x"])
    assert args.setup_script == []


def test_setup_script_missing_file_is_refused_before_any_webview(tmp_path: Path) -> None:
    with pytest.raises(probe.ProbeError, match="not an existing file"):
        probe.load_setup_scripts([tmp_path / "nope.js"])
    with pytest.raises(probe.ProbeError, match="not an existing file"):
        probe.load_setup_scripts([tmp_path])  # a directory is not a file


def test_main_refuses_missing_setup_script_without_gtk(tmp_path: Path, capsys) -> None:
    code = probe.main(
        [
            "--url",
            "http://127.0.0.1:8485/",
            "--data-dir",
            str(tmp_path / "scratch"),
            "--setup-script",
            str(tmp_path / "nope.js"),
        ]
    )
    assert code == 2
    assert "not an existing file" in capsys.readouterr().err
