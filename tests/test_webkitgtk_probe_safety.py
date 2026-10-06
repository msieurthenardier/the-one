"""Unit tests for the WebKitGTK probe's production-safety refusals (M25 F1 L1) and
its key-injection CLI (M25 F4 L7: port 8485 is refused too; ``--press-keys``)."""

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


@pytest.mark.parametrize("url", ["http://127.0.0.1:8485/", "http://localhost:8485/#chats"])
def test_refuses_the_preview_port(url: str, tmp_path: Path) -> None:
    with pytest.raises(probe.ProbeError, match="8485.*preview instance"):
        probe.check_safety(url, tmp_path / "scratch", default_dir=tmp_path / "default")


def test_refuses_default_data_dir(tmp_path: Path) -> None:
    default = tmp_path / "default"
    default.mkdir()
    with pytest.raises(probe.ProbeError, match="default data directory"):
        probe.check_safety("http://127.0.0.1:8486/", default / ".." / "default", default)


def test_accepts_dev_instance(tmp_path: Path) -> None:
    probe.check_safety("http://127.0.0.1:8486/", tmp_path / "scratch", tmp_path / "default")


def test_setup_script_is_repeatable_and_ordered(tmp_path: Path) -> None:
    a = tmp_path / "a.js"
    b = tmp_path / "b.js"
    a.write_text("var x = 1;")
    b.write_text("var y = 2;")
    args = probe.parse_args(
        [
            "--url",
            "http://127.0.0.1:8486/",
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
    args = probe.parse_args(["--url", "http://127.0.0.1:8486/", "--data-dir", "/x"])
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
            "http://127.0.0.1:8486/",
            "--data-dir",
            str(tmp_path / "scratch"),
            "--setup-script",
            str(tmp_path / "nope.js"),
        ]
    )
    assert code == 2
    assert "not an existing file" in capsys.readouterr().err


def test_key_flags_default_to_none() -> None:
    args = probe.parse_args(["--url", "http://127.0.0.1:8486/", "--data-dir", "/x"])
    assert args.press_keys == [] and args.assert_selector is None and args.focus_selector is None
    assert args.key_method == "event" and args.assert_timeout == 5.0


def test_key_flags_parse() -> None:
    args = probe.parse_args(
        [
            "--url",
            "http://127.0.0.1:8486/#agents",
            "--data-dir",
            "/x",
            "--press-keys",
            "ctrl+k",
            "--press-keys",
            "Escape",
            "--key-method",
            "gtk-test",
            "--focus-selector",
            "[data-testid=agents-filter]",
            "--assert-selector",
            "[data-testid=jump-to]",
        ]
    )
    assert args.press_keys == ["ctrl+k", "Escape"] and args.key_method == "gtk-test"
    assert args.focus_selector == "[data-testid=agents-filter]"
    assert args.assert_selector == "[data-testid=jump-to]"


@pytest.mark.parametrize(
    ("combo", "want"),
    [
        ("ctrl+k", (["CONTROL_MASK"], "k")),
        ("Control+Shift+K", (["CONTROL_MASK", "SHIFT_MASK"], "K")),
        ("alt+super+k", (["MOD1_MASK", "SUPER_MASK"], "k")),
        ("Escape", ([], "Escape")),
    ],
)
def test_parse_key_combo(combo: str, want: tuple) -> None:
    assert probe.parse_key_combo(combo) == want


@pytest.mark.parametrize("combo", ["", "ctrl+", "+k", "hyper+k", "ctrl++k"])
def test_parse_key_combo_rejects_a_bad_combo(combo: str) -> None:
    with pytest.raises(probe.ProbeError, match="--press-keys"):
        probe.parse_key_combo(combo)


def test_main_refuses_a_bad_combo_before_any_gtk(tmp_path: Path, capsys) -> None:
    code = probe.main(
        [
            "--url",
            "http://127.0.0.1:8486/",
            "--data-dir",
            str(tmp_path / "scratch"),
            "--press-keys",
            "hyper+k",
        ]
    )
    assert code == 2
    assert "unknown modifier" in capsys.readouterr().err
