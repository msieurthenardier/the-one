"""Unit tests for the UI capture tool's production-safety refusals (M31 F1 L03).

No app start, no browser: the default data dir is injected.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "ui_capture", Path(__file__).parent.parent / "scripts" / "ui_capture.py"
)
cap = importlib.util.module_from_spec(_SPEC)
sys.modules["ui_capture"] = cap  # dataclasses resolve their module by name
_SPEC.loader.exec_module(cap)


def _check(tmp_path: Path, **over) -> None:
    kwargs = {
        "port": 8490,
        "data_dir": tmp_path / "scratch" / "data",
        "out_dir": tmp_path / "out",
        "default_dir": tmp_path / "default",
        "env_data_dirs": [tmp_path / "envdir"],
        "repo_root": tmp_path / "repo",
    }
    kwargs.update(over)
    cap.check_capture_safety(**kwargs)


def test_accepts_a_clean_configuration(tmp_path: Path) -> None:
    _check(tmp_path)


@pytest.mark.parametrize("port", [8484, 8485])
def test_refuses_the_protected_ports(tmp_path: Path, port: int) -> None:
    with pytest.raises(cap.CaptureError, match=str(port)):
        _check(tmp_path, port=port)


@pytest.mark.parametrize("port", [80, 8000, 8486, 8489])
def test_refuses_ports_below_8490(tmp_path: Path, port: int) -> None:
    with pytest.raises(cap.CaptureError, match="8490 or higher"):
        _check(tmp_path, port=port)


def test_accepts_8490_and_above(tmp_path: Path) -> None:
    _check(tmp_path, port=8491)
    _check(tmp_path, port=40000)


def test_refuses_the_default_data_dir_and_anything_inside(tmp_path: Path) -> None:
    default = tmp_path / "default"
    with pytest.raises(cap.CaptureError, match="default data directory"):
        _check(tmp_path, data_dir=default / ".." / "default")
    with pytest.raises(cap.CaptureError, match="default data directory"):
        _check(tmp_path, data_dir=default / "nested" / "deeper")


def test_refuses_a_data_dir_containing_the_default(tmp_path: Path) -> None:
    with pytest.raises(cap.CaptureError, match="default data directory"):
        _check(tmp_path, data_dir=tmp_path)


def test_refuses_an_env_data_dir_and_anything_inside(tmp_path: Path) -> None:
    env_dir = tmp_path / "envdir"
    with pytest.raises(cap.CaptureError, match="THE_ONE_DATA_DIR"):
        _check(tmp_path, data_dir=env_dir)
    with pytest.raises(cap.CaptureError, match="THE_ONE_DATA_DIR"):
        _check(tmp_path, data_dir=env_dir / "x")


def test_refuses_an_out_dir_inside_the_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    with pytest.raises(cap.CaptureError, match="inside the repo"):
        _check(tmp_path, out_dir=repo / "tmp-capture")
    with pytest.raises(cap.CaptureError, match="inside the repo"):
        _check(tmp_path, out_dir=repo)


def test_collect_env_data_dirs_reads_environment_and_dotenv_text(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "# THE_ONE_DATA_DIR=/commented\n"
        "OTHER=1\n"
        'THE_ONE_DATA_DIR="/from/dotenv"\n'
        "export THE_ONE_DATA_DIR=/exported\n"
    )
    found = cap.collect_env_data_dirs({"THE_ONE_DATA_DIR": "/from/env"}, tmp_path)
    assert found == [Path("/from/env"), Path("/from/dotenv"), Path("/exported")]


def test_collect_env_data_dirs_without_either_source(tmp_path: Path) -> None:
    assert cap.collect_env_data_dirs({}, tmp_path) == []


def test_surface_table_lists_every_skipped_surface_with_a_reason() -> None:
    names = [s.name for s in cap.SURFACES]
    assert len(names) == len(set(names))
    for s in cap.SURFACES:
        if s.skipped:
            assert s.skipped.strip()
        else:
            assert s.hash and s.ready
    assert {"provider-create", "ollama-models-panel", "flash-after-save"} <= set(names)
    for ptype in cap.PROVIDERS:
        assert f"provider-edit-{ptype}" in names


# --keep-running (M31 F4 L01) goes through the same refusals before anything starts.


def _no_start(*_a, **_k):
    raise AssertionError("the instance must not start when a refusal applies")


def test_keep_running_refuses_a_protected_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cap, "pick_port", lambda: 8484)
    monkeypatch.setattr(cap, "start_instance", _no_start)
    with pytest.raises(cap.CaptureError, match="8484"):
        cap.run(["--keep-running"])


def test_keep_running_refuses_a_scratch_dir_inside_the_default_data_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The scratch tree lives under ~/.cache/the-one-ui-capture: a "default" that
    # contains it must be refused.
    monkeypatch.setattr(cap, "default_data_dir", lambda: Path.home() / ".cache")
    monkeypatch.setattr(cap, "start_instance", _no_start)
    with pytest.raises(cap.CaptureError, match="default data directory"):
        cap.run(["--keep-running"])


def test_keep_running_takes_no_out_and_out_still_needs_a_dir() -> None:
    with pytest.raises(cap.CaptureError, match="takes no --out"):
        cap.run(["--keep-running", "--out", "/tmp/x"])
    with pytest.raises(cap.CaptureError, match="--out DIR is required"):
        cap.run([])


def test_time_mask_pins_the_meridiem(tmp_path: Path) -> None:
    """The shape-preserving time mask must not keep the real AM/PM: it flips with the
    time of day a capture runs ("12:00 AM" vs "12:00 PM" read as a run-to-run difference)."""
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = cap.MASK_JS
    start = js.index("const MON")
    end = js.index("\n  ];", start) + len("\n  ];")
    script = (
        js[start:end]
        + "\nconst run = (s) => TIME_RULES.reduce((o, [re, fn]) => o.replace(re, fn), s);"
        + "\nconsole.log(JSON.stringify(process.argv.slice(2).map(run)));"
    )
    path = tmp_path / "mask.js"
    path.write_text(script)
    inputs = ["Indexed 3:04 AM", "Indexed 11:59 PM", "at 9:30PM", "14:05", "Mar 4, 3:04 AM"]
    out = subprocess.run(
        [node, str(path), *inputs], capture_output=True, text=True, check=True
    ).stdout
    masked = json.loads(out)
    assert masked[0] == "Indexed 12:00 PM"
    assert masked[1].endswith("12:00 PM")
    assert masked[2] == "at 12:00PM"
    assert masked[3] == "12:00"
    assert masked[4] == "Mar 1, 12:00 PM"
