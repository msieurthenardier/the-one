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
        # 80 minutes: lifecycle.ps1 bounds itself to M32_T0 + 4080 s and leaves 12 minutes for the
        # summary, the upload and the verdict (the arithmetic is in the workflow header and lib.ps1)
        assert job["timeout-minutes"] <= 90
        assert job["runs-on"] == "windows-2022"
        for step in job["steps"]:
            assert "timeout-minutes" in step, f"step without its own timeout: {step.get('name')}"


def _steps() -> dict[str, dict]:
    steps = _doc(WORKFLOW)["jobs"]["build"]["steps"]
    return {s.get("name") or s["uses"]: s for s in steps}


def test_full_and_lifecycle_modes_are_accepted_and_probe_is_not():
    paths = _steps()["Paths"]["run"]
    assert re.search(r"^\s*full \| lifecycle\) ;;", paths, re.M), "full and lifecycle must pass"
    assert "lands in leg 3b" not in WORKFLOW.read_text(encoding="utf-8")
    assert "unknown mode" in paths


def test_job_bound_arithmetic_is_consistent():
    # the job cap, the lifecycle bound (lib.ps1) and the reserve the header promises
    job = _doc(WORKFLOW)["jobs"]["build"]
    lib = (ROOT / "packaging" / "windows" / "lib.ps1").read_text(encoding="utf-8")
    bound = int(re.search(r"\$script:JobBoundSeconds = (\d+)", lib).group(1))
    assert job["timeout-minutes"] * 60 - bound >= 11 * 60
    lifecycle_step = _steps()["Installer lifecycle (L1-L9)"]
    assert lifecycle_step["timeout-minutes"] * 60 > bound - 30 * 60
    assert lifecycle_step["timeout-minutes"] < job["timeout-minutes"]


def test_build_steps_use_the_one_recipe():
    steps = _steps()
    n = steps["Build N"]
    assert n["shell"] == "pwsh"
    assert "packaging/windows/build.ps1 -Version $env:M32_VERSION -Out $env:M32_OUT" in n["run"]
    assert "-ReuseVenv" not in n["run"]
    nxt = steps["Build N+1"]
    assert nxt["if"] == "${{ inputs.mode == 'lifecycle' }}"
    assert "-Version $env:M32_NEXT -Out $env:M32_OUT -ReuseVenv" in nxt["run"]
    versions = steps["Versions"]["run"]
    assert "packaging/render.py --next-version" in versions
    assert "pip install -e" not in WORKFLOW.read_text(encoding="utf-8")


def test_frozen_smoke_asserts_the_staged_version_with_the_stage_on_pythonpath():
    run = _steps()["Frozen serve and single-instance probe"]["run"]
    assert "$env:PYTHONPATH = $mStage" in run
    assert "stage-windows-$($env:M32_VERSION)" in run
    assert "venv/Scripts/python.exe" in run
    assert "smoke.py info $env:M32_VERSION" in run
    assert "smoke.py single-instance" in run
    assert "Stop-Process -Id $mServe.Id" in run, "teardown kills the recorded pid only"
    assert "taskkill" not in run
    smoke = (ROOT / "packaging" / "windows" / "smoke.py").read_text(encoding="utf-8")
    assert '"info"' in smoke and "_select_port" in smoke
    body = smoke.split('"""', 2)[2]  # past the docstring
    assert "__version__" not in body, "the staged version is the input, not whatever is imported"


def test_installer_artifact_is_n_only_for_fourteen_days():
    steps = _steps()
    up = steps["Upload the installer"]
    assert up["uses"].startswith("actions/upload-artifact@")
    assert up["with"]["name"] == "windows-installer"
    assert up["with"]["retention-days"] == 14
    assert up["with"]["path"] == "${{ env.M32_SETUP_N }}"
    assert "M32_SETUP_NEXT" not in str(up)
    logs = steps["Upload logs and evidence"]
    assert logs["with"]["name"] == "windows-packages-logs"
    assert logs["if"] == "${{ always() }}"
    names = list(steps)
    assert names.index("Upload the installer") < names.index("Build N+1")


def test_self_tests_run_before_the_build():
    steps = list(_steps())
    run = _steps()["Self tests (build.ps1, lib.ps1, lifecycle.ps1)"]["run"]
    for script in ("build.ps1", "lib.ps1", "lifecycle.ps1"):
        assert f"./packaging/windows/{script} -SelfTest" in run
    assert steps.index("Self tests (build.ps1, lib.ps1, lifecycle.ps1)") < steps.index("Build N")


def test_lifecycle_step_and_verdict():
    steps = _steps()
    life = steps["Installer lifecycle (L1-L9)"]
    assert life["if"] == "${{ inputs.mode == 'lifecycle' }}"
    assert "packaging/windows/lifecycle.ps1" in life["run"]
    for arg in ("-InstallerN $env:M32_SETUP_N", "-InstallerNext $env:M32_SETUP_NEXT"):
        assert arg in life["run"]
    verdict = steps["Lifecycle verdict"]
    assert "always()" in verdict["if"] and "lifecycle" in verdict["if"]
    assert "== lifecycle done" in verdict["run"]
    assert "grep -q '^FAIL'" in verdict["run"]
    # PowerShell may write CRLF; every anchored grep must strip CR first
    for line in verdict["run"].splitlines():
        if "grep -q '^" in line:
            assert "tr -d '\\r'" in line, line
    order = list(steps)
    assert order.index("Upload logs and evidence") < order.index("Lifecycle verdict")


def test_uninstall_key_has_two_closing_braces():
    for path in (ROOT / "packaging" / "windows" / "lib.ps1",):
        text = path.read_text(encoding="utf-8")
        assert "{CAEEFB46-2698-4048-AD9F-0120D0B7174A}}_is1" in text
    assert "{CAEEFB46-2698-4048-AD9F-0120D0B7174A}_is1" not in (
        ROOT / "packaging" / "windows" / "lib.ps1"
    ).read_text(encoding="utf-8")


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


def test_probe_mode_is_retired_and_its_build_steps_are_gone():
    # Leg 3a: the probe built with the unstaged recipe and /DAppVersion, both gone since the
    # product .iss/spec are staged. The mode exits 1 with the retirement notice; nothing in the
    # workflow passes the removed define or runs the spec unstaged.
    text = WORKFLOW.read_text(encoding="utf-8")
    paths = next(s for s in _doc(WORKFLOW)["jobs"]["build"]["steps"] if s.get("name") == "Paths")[
        "run"
    ]
    m = re.search(r"probe\)([^\n]*exit 1)", paths)
    assert m, "probe must exit 1"
    assert "retired after leg 1" in m.group(1)
    assert "40246340174" in m.group(1)
    assert "/DAppVersion" not in text
    assert "the-one.spec" not in text
    names = [s.get("name") for s in _doc(WORKFLOW)["jobs"]["build"]["steps"]]
    assert "Premise probe" not in names


def test_probe_main_section_does_not_shadow_script_variables():
    # `$rows` at script scope IS `$script:Rows` (names are case-insensitive): dispatch 2 was lost
    # to that. The real guard is the AST check inside `probe.ps1 -SelfTest`; this is a cheap pin.
    text = PROBE.read_text(encoding="utf-8")
    main = text[text.index("# Main\n") :]
    assert not re.search(r"^\s*\$rows\b", main, re.M | re.I)
    assert "$mPlan" in main
