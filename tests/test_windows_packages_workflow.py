"""Pins for the Windows packages workflow (Mission 32 Flight 4, leg 1).

The ``on:`` block of ``.github/workflows/windows-packages.yml`` is an interface: the default-branch
stub carries a byte-identical copy (GitHub validates dispatch inputs against that copy), and the
release workflow calls it. These tests fail on any drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "windows-packages.yml"
STUB = ROOT / "packaging" / "windows" / "probe" / "windows-packages.stub.yml"
PROBE = ROOT / "packaging" / "windows" / "probe" / "probe.ps1"
MODES = ["full", "lifecycle", "probe"]


def _on_block(path: Path) -> str:
    """The text from the top-level ``on:`` line up to the next top-level key."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^on:\n(?:[ \t]+.*\n|\n)*", text, re.M)
    assert m, f"{path} has no top-level on: block"
    return m.group(0).rstrip("\n") + "\n"


def _doc(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(doc: dict) -> dict:
    # YAML 1.1 reads the bare key `on` as True
    return doc["on"] if "on" in doc else doc[True]


def test_on_block_is_byte_identical_to_the_stub():
    assert _on_block(WORKFLOW) == _on_block(STUB)


def test_on_block_inputs_and_modes():
    on = _on(_doc(WORKFLOW))
    assert set(on) == {"workflow_dispatch", "workflow_call"}
    dispatch = on["workflow_dispatch"]["inputs"]
    call = on["workflow_call"]
    assert set(call) == {"inputs"}, "workflow_call deliberately has no outputs"
    assert dispatch["mode"]["type"] == "choice"
    assert dispatch["mode"]["options"] == MODES
    assert dispatch["mode"]["default"] == "full"
    assert call["inputs"]["mode"]["type"] == "string"
    assert call["inputs"]["mode"]["default"] == "full"
    for inputs in (dispatch, call["inputs"]):
        assert set(inputs) == {"version", "mode"}
        assert inputs["version"]["type"] == "string"
        assert inputs["version"]["required"] is False
        assert inputs["version"]["default"] == ""


def test_stub_parses_the_same():
    assert _on(_doc(STUB)) == _on(_doc(WORKFLOW))
    assert _doc(STUB)["name"] == "windows-packages"


def test_permissions_concurrency_and_bounds():
    doc = _doc(WORKFLOW)
    assert doc["permissions"] == {"contents": "read"}
    assert doc["concurrency"] == {"group": "windows-packages", "cancel-in-progress": False}
    for job in doc["jobs"].values():
        assert job["timeout-minutes"] <= 60
        assert job["runs-on"] == "windows-2022"
        for step in job["steps"]:
            assert "timeout-minutes" in step, f"step without its own timeout: {step.get('name')}"


def test_full_and_lifecycle_are_not_yet_implemented():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "lands in leg 3b" in text
    paths = next(s for s in _doc(WORKFLOW)["jobs"]["build"]["steps"] if s.get("name") == "Paths")[
        "run"
    ]
    m = re.search(r"full \| lifecycle\)([^;]*;\s*exit 1)", paths)
    assert m, "full and lifecycle must exit 1 until leg 3b"


def test_iscc_step_is_powershell_with_exit_code_checks():
    steps = _doc(WORKFLOW)["jobs"]["build"]["steps"]
    step = next(s for s in steps if s.get("id") == "iscc")
    assert step["shell"] == "pwsh"
    assert step["timeout-minutes"] >= 15
    run = step["run"]
    assert "$LASTEXITCODE" in run
    assert "Test-Path" in run
    assert "/DAppVersion=" in run and "//" not in run.replace("://", "")
    assert "6.1" in run or "$minor -lt 1" in run


def test_probe_bounds_itself_to_the_job_start():
    text = PROBE.read_text(encoding="utf-8")
    assert "M32_T0" in text
    assert "probe aborted" in text


def test_probe_driver_seeds_every_row_and_ends_with_done():
    text = PROBE.read_text(encoding="utf-8")
    for row in ("W1", "W2", "W3", "W4", "W5", "W6"):
        assert f"'{row}'" in text
    assert "not-run" in text
    assert "== probe done" in text
    assert "Finished server process" in text
    assert text.isascii(), "probe.ps1 must stay ASCII (Windows PowerShell 5 reads it as ANSI)"


def test_final_step_reads_the_summary_with_anchored_fail():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "grep -q '^FAIL'" in text
    assert "== probe done" in text
